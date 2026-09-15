"""Relevância = participação do item dentro da PRÓPRIA classificação, não
uma curva ABC genérica sobre o catálogo inteiro (pedido do Gabriel:
"quais são os itens que sao mais relevantes na classificação x o todo").
Calculado direto da venda real do período (mais atual que a Curva Valor/
Qtd. do cadastro do ERP, que é uma foto de quando o cadastro foi tirado)."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from apps.vendas.models import VendaItem


def relevancia_por_classificacao(
    ano_mes_de: str | None = None,
    ano_mes_ate: str | None = None,
    bandeira: str | None = None,
    cidade: str | None = None,
    corte_relevante_pct: Decimal = Decimal("80"),
) -> dict[str, list[dict]]:
    """1 grupo por Classificação, itens ordenados por venda desc, com % de
    participação e um corte acumulado (curva ABC dentro da classificação —
    'relevante' = está na fatia que soma até `corte_relevante_pct`% da
    classificação, sempre incluindo pelo menos o 1º item)."""
    qs = VendaItem.objects.filter(produto__isnull=False).select_related("produto")
    if ano_mes_de:
        qs = qs.filter(ano_mes__gte=ano_mes_de)
    if ano_mes_ate:
        qs = qs.filter(ano_mes__lte=ano_mes_ate)
    if bandeira:
        qs = qs.filter(loja__bandeira=bandeira)
    if cidade:
        qs = qs.filter(loja__cidade=cidade)

    # agrega em Python (não em SQL) pra já ter classificacao/descricao à
    # mão sem outra query -- catálogo cabe tranquilo em memória (~30k produtos)
    somas: dict[tuple[str, int], dict] = {}
    for v in qs.only("produto_id", "produto__classificacao", "produto__descricao", "venda", "itens"):
        chave = (v.produto.classificacao or "(sem classificação)", v.produto_id)
        item = somas.setdefault(chave, {
            "produto_id": v.produto_id,
            "descricao": v.produto.descricao,
            "venda": Decimal("0"),
            "itens": Decimal("0"),
        })
        item["venda"] += v.venda
        item["itens"] += v.itens

    por_classificacao: dict[str, list[dict]] = defaultdict(list)
    for (classificacao, _produto_id), item in somas.items():
        por_classificacao[classificacao].append(item)

    resultado: dict[str, list[dict]] = {}
    for classificacao, itens in por_classificacao.items():
        itens.sort(key=lambda i: i["venda"], reverse=True)
        total = sum(i["venda"] for i in itens) or Decimal("1")
        acumulado = Decimal("0")
        for i, item in enumerate(itens):
            item["pct_classificacao"] = round(item["venda"] / total * 100, 1)
            acumulado += item["pct_classificacao"]
            item["relevante"] = (i == 0) or (acumulado - item["pct_classificacao"] < corte_relevante_pct)
        resultado[classificacao] = itens
    return resultado


def _filtrar_vendas(
    ano_mes_de: str | None, ano_mes_ate: str | None, bandeira: str | None, cidade: str | None,
):
    qs = VendaItem.objects.all()
    if ano_mes_de:
        qs = qs.filter(ano_mes__gte=ano_mes_de)
    if ano_mes_ate:
        qs = qs.filter(ano_mes__lte=ano_mes_ate)
    if bandeira:
        qs = qs.filter(loja__bandeira=bandeira)
    if cidade:
        qs = qs.filter(loja__cidade=cidade)
    return qs


def _agregar(qs, campos: list[str]) -> list[dict]:
    """Soma venda/custo/lucro agrupado pelos `campos` dados (campos de Loja,
    via a FK) e calcula margem % (lucro/venda) -- ordenado com a menor
    margem primeiro (mesmo espírito do Monitor de Preço, "mais caro
    primeiro": só destaca, não sugere nada)."""
    linhas = list(qs.values(*campos).annotate(venda=Sum("venda"), custo=Sum("custo"), lucro=Sum("lucro")))
    for l in linhas:
        l["margem_pct"] = round(l["lucro"] / l["venda"] * 100, 1) if l["venda"] else None
    linhas.sort(key=lambda l: (l["margem_pct"] is None, l["margem_pct"]))
    return linhas


def custo_margem_resumo(
    ano_mes_de: str | None = None,
    ano_mes_ate: str | None = None,
    bandeira: str | None = None,
    cidade: str | None = None,
) -> dict:
    """Custo x Margem em 3 níveis (loja/bandeira/cidade) a partir do que já
    está em VendaItem (venda/custo/lucro, do relatório 'Análise de Venda por
    Item' do ERP) -- pedido do Gabriel, só leitura do que já vendeu, sem
    motor de sugestão."""
    qs = _filtrar_vendas(ano_mes_de, ano_mes_ate, bandeira, cidade)
    por_loja = _agregar(qs, ["loja_id", "loja__nome", "loja__bandeira", "loja__cidade", "loja__ativa"])
    por_bandeira = _agregar(qs, ["loja__bandeira"])
    por_cidade = _agregar(qs, ["loja__cidade"])
    geral = qs.aggregate(venda=Sum("venda"), custo=Sum("custo"), lucro=Sum("lucro"))
    geral["margem_pct"] = round(geral["lucro"] / geral["venda"] * 100, 1) if geral.get("venda") else None
    return {"por_loja": por_loja, "por_bandeira": por_bandeira, "por_cidade": por_cidade, "geral": geral}
