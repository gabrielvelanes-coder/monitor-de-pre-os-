"""Relevância = participação do item dentro da PRÓPRIA classificação, não
uma curva ABC genérica sobre o catálogo inteiro (pedido do Gabriel:
"quais são os itens que sao mais relevantes na classificação x o todo").
Calculado direto da venda real do período (mais atual que a Curva Valor/
Qtd. do cadastro do ERP, que é uma foto de quando o cadastro foi tirado)."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Sum

from apps.produtos.models import Produto
from apps.vendas.models import VendaItem

# Relevância e Custo x Margem agregam ~665 mil linhas de VendaItem a cada
# carregamento -- 37s sem cache (achado 16/09/26, Gabriel reclamou de
# lentidão). Esse dado só muda quando alguém roda `importar_vendas`
# manualmente (não em tempo real), então cache com TTL alto + invalidação
# explícita no fim do importador (`cache.clear()`) é seguro -- nunca fica
# velho além do que o próprio Gabriel espera.
_CACHE_TTL_SEGUNDOS = 3600


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
    chave_cache = f"relevancia:{ano_mes_de}:{ano_mes_ate}:{bandeira}:{cidade}:{corte_relevante_pct}"
    cacheado = cache.get(chave_cache)
    if cacheado is not None:
        return cacheado

    qs = VendaItem.objects.filter(produto__isnull=False)
    if ano_mes_de:
        qs = qs.filter(ano_mes__gte=ano_mes_de)
    if ano_mes_ate:
        qs = qs.filter(ano_mes__lte=ano_mes_ate)
    if bandeira:
        qs = qs.filter(loja__bandeira=bandeira)
    if cidade:
        qs = qs.filter(loja__cidade=cidade)

    # ACHADO 16/09/26: essa função somava as ~665 mil linhas de VendaItem
    # em PYTHON (loop linha a linha, criando 1 objeto Django por linha) --
    # 37s pra carregar a tela. Com 156 mil linhas (início do projeto) não
    # dava pra notar; foi ficando mais lento a cada importação de mês
    # novo. Trocado pra `.values().annotate(Sum())` SÓ por produto_id
    # (sem juntar com Produto na mesma query -- juntar as 2 tabelas no
    # GROUP BY obrigava o SQLite a usar B-tree temporário pra ordenar
    # classificação/descrição, mais lento) + 1 busca em lote de Produto
    # depois. ~4,7s (era 37s) só nessa função; com cache abaixo, só paga
    # esse custo 1x por combinação de filtro.
    linhas = list(qs.values("produto_id").annotate(venda=Sum("venda"), itens=Sum("itens")))
    produtos = {
        p["id"]: p
        for p in Produto.objects.filter(id__in=[l["produto_id"] for l in linhas]).values(
            "id", "classificacao", "descricao"
        )
    }

    por_classificacao: dict[str, list[dict]] = defaultdict(list)
    for l in linhas:
        produto = produtos.get(l["produto_id"], {})
        classificacao = produto.get("classificacao") or "(sem classificação)"
        por_classificacao[classificacao].append({
            "produto_id": l["produto_id"],
            "descricao": produto.get("descricao", ""),
            "venda": l["venda"] or Decimal("0"),
            "itens": l["itens"] or Decimal("0"),
        })

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
    cache.set(chave_cache, resultado, _CACHE_TTL_SEGUNDOS)
    return resultado


def itens_relevantes(top_n: int = 100) -> list[dict]:
    """União do Top N por faturamento (venda R$) com o Top N por unidades
    (itens) -- cada métrica pega um motivo de importância diferente (achado
    17/09/26: só 34% de sobreposição entre os dois top-100 -- MOUNJARO fatura
    muito com poucas unidades, LOSARTANA vende dezenas de milhares de
    unidades a preço baixo cada). Fonte pro robô saber quais itens merecem
    busca de preço prioritária todo dia (ver `exportar_itens_relevantes`)."""
    linhas = list(
        VendaItem.objects.filter(produto__isnull=False)
        .values("produto_id")
        .annotate(venda=Sum("venda"), itens=Sum("itens"))
    )
    produtos = {
        p["id"]: p
        for p in Produto.objects.filter(id__in=[l["produto_id"] for l in linhas]).values(
            "id", "ean", "descricao"
        )
    }
    for l in linhas:
        produto = produtos.get(l["produto_id"], {})
        l["ean"] = produto.get("ean", "")
        l["descricao"] = produto.get("descricao", "")

    linhas_com_ean = [l for l in linhas if l["ean"] and l["ean"] != "nan"]
    top_faturamento = sorted(linhas_com_ean, key=lambda l: l["venda"], reverse=True)[:top_n]
    top_unidades = sorted(linhas_com_ean, key=lambda l: l["itens"], reverse=True)[:top_n]

    origem_por_ean: dict[str, set[str]] = defaultdict(set)
    dados_por_ean: dict[str, dict] = {}
    for l in top_faturamento:
        origem_por_ean[l["ean"]].add("faturamento")
        dados_por_ean[l["ean"]] = l
    for l in top_unidades:
        origem_por_ean[l["ean"]].add("unidades")
        dados_por_ean[l["ean"]] = l

    resultado = []
    for ean, origens in origem_por_ean.items():
        l = dados_por_ean[ean]
        resultado.append({
            "ean": ean,
            "descricao": l["descricao"],
            "venda": l["venda"] or Decimal("0"),
            "itens": l["itens"] or Decimal("0"),
            "origem": "ambos" if len(origens) == 2 else next(iter(origens)),
        })
    resultado.sort(key=lambda i: i["venda"], reverse=True)
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
    chave_cache = f"custo_margem:{ano_mes_de}:{ano_mes_ate}:{bandeira}:{cidade}"
    cacheado = cache.get(chave_cache)
    if cacheado is not None:
        return cacheado

    qs = _filtrar_vendas(ano_mes_de, ano_mes_ate, bandeira, cidade)
    por_loja = _agregar(qs, ["loja_id", "loja__nome", "loja__bandeira", "loja__cidade", "loja__ativa"])
    por_bandeira = _agregar(qs, ["loja__bandeira"])
    por_cidade = _agregar(qs, ["loja__cidade"])
    geral = qs.aggregate(venda=Sum("venda"), custo=Sum("custo"), lucro=Sum("lucro"))
    geral["margem_pct"] = round(geral["lucro"] / geral["venda"] * 100, 1) if geral.get("venda") else None
    resultado = {"por_loja": por_loja, "por_bandeira": por_bandeira, "por_cidade": por_cidade, "geral": geral}
    cache.set(chave_cache, resultado, _CACHE_TTL_SEGUNDOS)
    return resultado
