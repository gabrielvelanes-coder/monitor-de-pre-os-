"""Lógica de comparação nosso-preço x concorrência — sem nenhuma sugestão
ou recomendação de preço, só monitoramento (pedido explícito do Gabriel:
"não quero trabalhar com recomendação de preço, apenas monitorar e
comparar com o meu")."""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

from apps.captacao.models import PrecoCaptado


def montar_comparativo(cidade: str | None = None, bandeira: str | None = None) -> list[dict]:
    """1 linha por EAN visto em pelo menos 1 das nossas bandeiras, com o
    preço nosso (média das nossas lojas daquela bandeira/cidade — o robô
    não distingue qual loja física é qual, só a bandeira) contra o MENOR
    preço achado entre os concorrentes rastreados na mesma cidade."""
    nossos_qs = PrecoCaptado.objects.filter(rede__tipo="nossa", preco__isnull=False)
    conc_qs = PrecoCaptado.objects.filter(rede__tipo="concorrente", preco__isnull=False)
    if cidade:
        nossos_qs = nossos_qs.filter(cidade_busca=cidade)
        conc_qs = conc_qs.filter(cidade_busca=cidade)
    if bandeira:
        nossos_qs = nossos_qs.filter(rede__nome=bandeira)

    nossos_qs = nossos_qs.select_related("rede")
    conc_qs = conc_qs.select_related("rede")

    # (ean, cidade) -> lista de preços nossos (pode ter várias lojas da
    # mesma bandeira na mesma cidade, cada uma uma linha do robô)
    nossos: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    titulos: Counter = Counter()
    for p in nossos_qs:
        nossos[(p.ean, p.cidade_busca)].append(p.preco)
        if p.titulo:
            titulos[(p.ean, p.titulo)] += 1

    concorrentes: dict[tuple[str, str], list[tuple[Decimal, str]]] = defaultdict(list)
    for p in conc_qs:
        concorrentes[(p.ean, p.cidade_busca)].append((p.preco, p.rede.nome))

    titulo_por_ean: dict[str, str] = {}
    for (ean, titulo), _n in titulos.most_common():
        titulo_por_ean.setdefault(ean, titulo)

    linhas = []
    for (ean, cid), precos_nossos in nossos.items():
        nosso_medio = sum(precos_nossos) / len(precos_nossos)
        concorrencia = concorrentes.get((ean, cid), [])
        if concorrencia:
            menor_preco, nome_concorrente = min(concorrencia, key=lambda t: t[0])
            diferenca_pct = ((nosso_medio - menor_preco) / menor_preco * 100) if menor_preco else None
        else:
            menor_preco, nome_concorrente, diferenca_pct = None, None, None

        linhas.append({
            "ean": ean,
            "cidade": cid,
            "titulo": titulo_por_ean.get(ean, ""),
            "nosso_preco": round(nosso_medio, 2),
            "n_lojas_nossas": len(precos_nossos),
            "concorrente_mais_barato": nome_concorrente,
            "preco_concorrente": menor_preco,
            "n_concorrentes": len(concorrencia),
            "diferenca_pct": round(diferenca_pct, 1) if diferenca_pct is not None else None,
        })

    # mais caro que a concorrência primeiro -- é o que precisa de atenção
    linhas.sort(key=lambda l: (l["diferenca_pct"] is None, -(l["diferenca_pct"] or 0)))
    return linhas
