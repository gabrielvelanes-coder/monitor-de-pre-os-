"""Lógica de comparação nosso-preço x concorrência — sem nenhuma sugestão
ou recomendação de preço, só monitoramento (pedido explícito do Gabriel:
"não quero trabalhar com recomendação de preço, apenas monitorar e
comparar com o meu")."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from decimal import Decimal

from apps.captacao.models import PrecoCaptado
from apps.produtos.models import Produto


def _distancia_km(lat1, lon1, lat2, lon2) -> float | None:
    """Haversine simples (raio da Terra ~6371km) -- sem dependência nova."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    raio = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return round(2 * raio * math.asin(math.sqrt(a)), 1)


def montar_comparativo(
    cidade: str | None = None,
    bandeira: str | None = None,
    classificacao: str | None = None,
    subclassificacao: str | None = None,
    situacao: str | None = None,  # "mais_caro" | "mais_barato" | None
) -> list[dict]:
    """1 linha por EAN visto em pelo menos 1 das nossas bandeiras, com o
    preço nosso (média das nossas lojas daquela bandeira/cidade) contra o
    MENOR preço achado entre os concorrentes rastreados na mesma cidade.
    Cada linha carrega também a lista completa de nossas lojas e de
    concorrentes envolvidos (loja/estabelecimento, preço, distância) --
    não só o resumo -- pra dar pra ver especificamente quem é quem, não só
    a rede/bandeira."""
    nossos_qs = PrecoCaptado.objects.filter(rede__tipo="nossa", preco__isnull=False)
    conc_qs = PrecoCaptado.objects.filter(rede__tipo="concorrente", preco__isnull=False)
    if cidade:
        nossos_qs = nossos_qs.filter(cidade_busca=cidade)
        conc_qs = conc_qs.filter(cidade_busca=cidade)
    if bandeira:
        nossos_qs = nossos_qs.filter(rede__nome=bandeira)

    nossos_qs = nossos_qs.select_related("rede", "loja")
    conc_qs = conc_qs.select_related("rede")

    eans_envolvidos = set(nossos_qs.values_list("ean", flat=True))
    produto_por_ean = {
        p.ean: p for p in Produto.objects.filter(ean__in=eans_envolvidos).exclude(ean="")
    } if eans_envolvidos else {}

    if classificacao:
        eans_envolvidos &= {ean for ean, p in produto_por_ean.items() if p.classificacao == classificacao}
        nossos_qs = nossos_qs.filter(ean__in=eans_envolvidos)
    if subclassificacao:
        eans_envolvidos &= {ean for ean, p in produto_por_ean.items() if p.subclassificacao == subclassificacao}
        nossos_qs = nossos_qs.filter(ean__in=eans_envolvidos)

    # (ean, cidade) -> registros nossos (várias lojas da mesma bandeira
    # podem aparecer na mesma cidade, cada uma 1 linha do robô)
    nossos: dict[tuple[str, str], list[PrecoCaptado]] = defaultdict(list)
    titulos: Counter = Counter()
    for p in nossos_qs:
        nossos[(p.ean, p.cidade_busca)].append(p)
        if p.titulo:
            titulos[(p.ean, p.titulo)] += 1

    concorrentes: dict[tuple[str, str], list[PrecoCaptado]] = defaultdict(list)
    for p in conc_qs:
        concorrentes[(p.ean, p.cidade_busca)].append(p)

    titulo_por_ean: dict[str, str] = {}
    for (ean, titulo), _n in titulos.most_common():
        titulo_por_ean.setdefault(ean, titulo)

    linhas = []
    for (ean, cid), nossos_precos in nossos.items():
        nosso_medio = sum(p.preco for p in nossos_precos) / len(nossos_precos)

        nossas_lojas = []
        for p in nossos_precos:
            tem_geo = p.loja and p.loja.lat is not None
            nossas_lojas.append({
                "loja": p.loja.nome if p.loja else None,
                "preco": p.preco,
                "distancia_centro": p.distancia,
                "_lat": p.loja.lat if tem_geo else None,
                "_lon": p.loja.lon if tem_geo else None,
            })
        nossas_lojas.sort(key=lambda x: x["preco"])

        # referência de distância real: a 1ª loja nossa vinculada (geocodificada)
        ref_lat = ref_lon = None
        for nl in nossas_lojas:
            if nl["_lat"] is not None:
                ref_lat, ref_lon = nl["_lat"], nl["_lon"]
                break

        concorrentes_linha = []
        for p in concorrentes.get((ean, cid), []):
            concorrentes_linha.append({
                "rede": p.rede.nome if p.rede else "",
                "estabelecimento": p.estabelecimento,
                "preco": p.preco,
                "distancia_centro": p.distancia,
                "distancia_km": _distancia_km(ref_lat, ref_lon, p.lat, p.lon),
            })
        concorrentes_linha.sort(key=lambda x: x["preco"])

        if concorrentes_linha:
            menor = concorrentes_linha[0]
            diferenca_pct = ((nosso_medio - menor["preco"]) / menor["preco"] * 100) if menor["preco"] else None
        else:
            menor, diferenca_pct = None, None

        if situacao == "mais_caro" and not (diferenca_pct is not None and diferenca_pct > 0):
            continue
        if situacao == "mais_barato" and not (diferenca_pct is not None and diferenca_pct <= 0):
            continue

        produto = produto_por_ean.get(ean)
        linhas.append({
            "ean": ean,
            "cidade": cid,
            "titulo": titulo_por_ean.get(ean, ""),
            "classificacao": produto.classificacao if produto else "",
            "subclassificacao": produto.subclassificacao if produto else "",
            "nosso_preco": round(nosso_medio, 2),
            "nossas_lojas": nossas_lojas,
            "concorrente_mais_barato": menor["estabelecimento"] if menor else None,
            "concorrente_rede": menor["rede"] if menor else None,
            "preco_concorrente": menor["preco"] if menor else None,
            "distancia_km_concorrente": menor["distancia_km"] if menor else None,
            "concorrentes": concorrentes_linha,
            "n_concorrentes": len(concorrentes_linha),
            "diferenca_pct": round(diferenca_pct, 1) if diferenca_pct is not None else None,
        })

    # mais caro que a concorrência primeiro -- é o que precisa de atenção
    linhas.sort(key=lambda l: (l["diferenca_pct"] is None, -(l["diferenca_pct"] or 0)))
    return linhas
