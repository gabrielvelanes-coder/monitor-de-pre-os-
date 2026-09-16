"""Lógica de comparação nosso-preço x concorrência — sem nenhuma sugestão
ou recomendação de preço, só monitoramento (pedido explícito do Gabriel:
"não quero trabalhar com recomendação de preço, apenas monitorar e
comparar com o meu")."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from decimal import Decimal

from django.utils import timezone

from apps.captacao.models import PrecoCaptado
from apps.lojas.models import Loja
from apps.produtos.models import Produto


def _dias_atras(dt) -> int | None:
    """Há quantos dias esse preço foi captado -- Gabriel pediu pra saber a
    idade do dado (1 dia, 2 dias, 10 dias...), não só o preço em si."""
    if dt is None:
        return None
    delta = timezone.now() - dt
    return max(delta.days, 0)


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
    loja_id: int | None = None,
    bairro: str | None = None,
) -> list[dict]:
    """1 linha por EAN visto em pelo menos 1 das nossas bandeiras, com o
    preço nosso (média das nossas lojas daquela bandeira/cidade -- ou o
    preço de 1 loja só, se `loja_id` for dado) contra o MENOR preço achado
    entre os concorrentes rastreados na mesma cidade. Cada linha carrega
    também a lista completa de nossas lojas e de concorrentes envolvidos
    (loja/estabelecimento, preço, distância) -- não só o resumo.

    Distância loja-nossa x concorrente só é mostrada no RESUMO da linha
    quando é inequívoca -- ou `loja_id` foi dado, ou todas as nossas lojas
    daquele EAN/cidade acabam sendo a MESMA loja física (comum hoje, já
    que só 14 das 24 lojas ativas têm captação vinculada). Quando 2+ lojas
    distintas estão envolvidas, o resumo fica sem número (evita distância
    enganosa) mas o detalhe expandido mostra a distância por loja."""
    nossos_qs = PrecoCaptado.objects.filter(rede__tipo="nossa", preco__isnull=False)
    conc_qs = PrecoCaptado.objects.filter(rede__tipo="concorrente", preco__isnull=False)
    if loja_id:
        # BUG REAL encontrado 15/09/26: escolher Loja + Cidade ao mesmo
        # tempo, com a loja sendo de OUTRA cidade, quebrava a comparação
        # inteira em silêncio -- nossos_qs ficava só com loja_id (cidade
        # real da loja), mas conc_qs aplicava o parâmetro `cidade` da URL
        # por fora, sem relação com a loja. Resultado: nenhum concorrente
        # nunca batia com nenhum EAN (chaves (ean, cidade) de universos
        # diferentes), "itens comparados" continuava normal mas "mais
        # caros" ia pra 0 sem nenhum aviso -- parecia que não tinha
        # concorrente na região, quando na verdade era o filtro quebrado.
        # Loja implica cidade/bandeira -- ignora os parâmetros da URL pra
        # cidade/bandeira quando uma loja está selecionada, e usa a
        # cidade REAL da loja pros concorrentes também.
        nossos_qs = nossos_qs.filter(loja_id=loja_id)
        loja_obj = Loja.objects.filter(id=loja_id).only("cidade").first()
        cidade = loja_obj.cidade if loja_obj else cidade
    else:
        if cidade:
            nossos_qs = nossos_qs.filter(cidade_busca=cidade)
        if bandeira:
            nossos_qs = nossos_qs.filter(rede__nome=bandeira)
    if cidade:
        conc_qs = conc_qs.filter(cidade_busca=cidade)
    if bairro:
        nossos_qs = nossos_qs.filter(bairro=bairro)
        conc_qs = conc_qs.filter(bairro=bairro)

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
                "loja_id": p.loja_id,
                "loja": p.loja.nome if p.loja else None,
                "preco": p.preco,
                "distancia_centro": p.distancia,
                "bairro": p.bairro,
                "dias_atras": _dias_atras(p.atualizado_em),
                "_lat": p.loja.lat if tem_geo else None,
                "_lon": p.loja.lon if tem_geo else None,
            })
        nossas_lojas.sort(key=lambda x: x["preco"])

        # lojas distintas com coordenada -- a distância do concorrente é
        # sempre a MENOR entre elas (loja nossa mais próxima), rotulada
        # com o nome dessa loja. Simplificado 15/09/26: a versão anterior
        # mostrava TODAS as combinações loja×concorrente quando havia 2+
        # lojas ("Loja 2: — · Loja 4: 0,5 km · Loja 3: —") -- Gabriel viu
        # e não conseguiu interpretar. Um número só, com rótulo, já
        # responde a pergunta real ("essa concorrência está perto de
        # alguma loja nossa?").
        lojas_geo = [(nl["loja"], nl["_lat"], nl["_lon"]) for nl in nossas_lojas if nl["_lat"] is not None]

        concorrentes_linha = []
        for p in concorrentes.get((ean, cid), []):
            item = {
                "rede": p.rede.nome if p.rede else "",
                "estabelecimento": p.estabelecimento,
                "preco": p.preco,
                "distancia_centro": p.distancia,
                "bairro": p.bairro,
                "dias_atras": _dias_atras(p.atualizado_em),
                "distancia_km": None,
                "distancia_precisa": None,
                "loja_mais_proxima": None,
            }
            distancias = [(nome, _distancia_km(lat, lon, p.lat, p.lon)) for nome, lat, lon in lojas_geo]
            distancias = [(nome, km) for nome, km in distancias if km is not None]
            if distancias:
                nome, km = min(distancias, key=lambda t: t[1])
                # ACHADO REAL 15/09/26: a Nominatim (geocodificação gratuita)
                # não resolve endereço no nível da rua pra boa parte dos
                # endereços de Itabuna/Ilhéus/Ipiaú -- cai pro centroide do
                # BAIRRO. Resultado: 5 das nossas lojas (e vários
                # concorrentes) geocodificam pro MESMO ponto exato (bairro
                # Centro), dando distância 0,0km entre coisas que na
                # verdade não sabemos a distância real. 0,0km aqui não é
                # "estão coladas", é "geocodificação sem precisão pra
                # medir" -- mostrado à parte, não como se fosse um número
                # confiável.
                item["distancia_km"] = km
                item["distancia_precisa"] = km > 0
                item["loja_mais_proxima"] = nome
            concorrentes_linha.append(item)
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
        if situacao == "sem_concorrente" and diferenca_pct is not None:
            continue

        produto = produto_por_ean.get(ean)
        linhas.append({
            "chave": f"{ean}|{cid}",
            "ean": ean,
            "cidade": cid,
            "titulo": titulo_por_ean.get(ean, ""),
            "classificacao": produto.classificacao if produto else "",
            "subclassificacao": produto.subclassificacao if produto else "",
            "nosso_preco": round(nosso_medio, 2),
            "nossas_lojas": nossas_lojas,
            "dias_atras_nosso": min((nl["dias_atras"] for nl in nossas_lojas), default=None),
            "concorrente_mais_barato": menor["estabelecimento"] if menor else None,
            "concorrente_rede": menor["rede"] if menor else None,
            "preco_concorrente": menor["preco"] if menor else None,
            "distancia_km_concorrente": menor["distancia_km"] if menor else None,
            "distancia_precisa_concorrente": menor["distancia_precisa"] if menor else None,
            "loja_mais_proxima": menor["loja_mais_proxima"] if menor else None,
            "dias_atras_concorrente": menor["dias_atras"] if menor else None,
            "concorrentes": concorrentes_linha,
            "n_concorrentes": len(concorrentes_linha),
            "tem_distancia_imprecisa": any(c["distancia_km"] == 0 for c in concorrentes_linha),
            "diferenca_pct": round(diferenca_pct, 1) if diferenca_pct is not None else None,
        })

    # mais caro que a concorrência primeiro -- é o que precisa de atenção
    linhas.sort(key=lambda l: (l["diferenca_pct"] is None, -(l["diferenca_pct"] or 0)))
    return linhas
