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
from apps.vendas.models import AjusteItemMonitoramentoDiario, SelecaoItemRelevante, VendaItem

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


# Categorias do monitoramento diário fixo (pedido do Gabriel 19/09/26):
# nome de exibição -> (classificação exata, subclassificação exata ou None p/
# pegar a classificação toda, quantas vagas). Fraldas/Leites são
# subclassificação DENTRO de "MUNDO INFANTIL" no cadastro (confirmado no
# banco: 'FRALDA INFANTIL'/'LEITE'), então "Mundo Infantil" aqui é o RESTO da
# classificação, excluindo essas duas, senão o mesmo item apareceria em 2
# grupos. Ordem importa: cada grupo só pega itens que nenhum grupo anterior
# já pegou (evita duplicar EAN entre categorias).
_CATEGORIAS_MONITORAMENTO_DIARIO: list[tuple[str, str, str | None, int]] = [
    ("Genéricos", "GENÉRICOS", None, 10),
    ("Similares", "SIMILARES", None, 5),
    ("Propagado", "PROPAGADO", None, 5),
    ("Fraldas", "MUNDO INFANTIL", "FRALDA INFANTIL", 5),
    ("Leites", "MUNDO INFANTIL", "LEITE", 4),
    ("Mundo Infantil (resto)", "MUNDO INFANTIL", "__resto__", 4),
]
# Vagas extra pro top geral por unidades, fora de todas as categorias acima.
_VAGAS_TOP_GERAL_MONITORAMENTO_DIARIO = 2


def itens_monitoramento_diario() -> list[dict]:
    """Lista FIXA de 35 itens pro monitoramento diário de preço pedido pelo
    Gabriel (19/09/26): "todo dia ele pesquisa esses itens" pra acompanhar o
    valor de venda dia a dia -- diferente do `itens_relevantes` (Top 100
    geral por faturamento/unidades), aqui é Top N por UNIDADES vendidas
    dentro de categorias específicas escolhidas por ele (10 Genéricos, 5
    Similares, 5 Propagados, 5 Fraldas, 4 Leites, 4 resto de Mundo Infantil,
    + 2 top geral fora dessas categorias = 35). Critério "mais vendido" =
    unidades (não faturamento -- decisão explícita dele, os dois rankings
    divergem bastante, ver docstring de `itens_relevantes`). Fonte pra
    `exportar_itens_monitoramento_diario`, que alimenta a fila DIÁRIA
    (prioridade máxima) do robô -- ver `termos_diarios.py` do lado de lá."""
    linhas = list(
        VendaItem.objects.filter(produto__isnull=False)
        .values("produto_id")
        .annotate(venda=Sum("venda"), itens=Sum("itens"))
    )
    produtos = {
        p["id"]: p
        for p in Produto.objects.filter(id__in=[l["produto_id"] for l in linhas]).values(
            "id", "ean", "descricao", "classificacao", "subclassificacao"
        )
    }
    for l in linhas:
        produto = produtos.get(l["produto_id"], {})
        l["ean"] = produto.get("ean", "")
        l["descricao"] = produto.get("descricao", "")
        l["classificacao"] = produto.get("classificacao", "")
        l["subclassificacao"] = produto.get("subclassificacao", "")

    candidatos = [l for l in linhas if l["ean"] and l["ean"] != "nan"]
    candidatos_por_ean = {c["ean"]: c for c in candidatos}

    ajustes = list(AjusteItemMonitoramentoDiario.objects.filter(ativo=True))
    excluidos = {a.ean for a in ajustes if a.tipo == AjusteItemMonitoramentoDiario.EXCLUIR}
    inclusoes = [a for a in ajustes if a.tipo == AjusteItemMonitoramentoDiario.INCLUIR]

    usados: set[str] = set()
    resultado: list[dict] = []

    def _selecionar(nome_grupo: str, disponiveis: list[dict], n: int):
        # Item excluído não é reposto pelo próximo do ranking -- a vaga
        # some de propósito (senão o item trocado por escolha do Gabriel
        # voltaria sozinho via um "parecido" na próxima carga). Só conta
        # como "vaga perdida" quem de fato estaria no top-N deste grupo
        # SEM o ajuste (senão uma exclusão de outra categoria, presente
        # em `disponiveis` só porque esse grupo varre todo mundo -- caso
        # do "Top geral" -- encolheria um grupo que nem usaria aquele item).
        ordenados = sorted(disponiveis, key=lambda c: c["itens"] or 0, reverse=True)
        seria_selecionado = [c for c in ordenados if c["ean"] not in usados][:n]
        excluidos_do_grupo = sum(1 for c in seria_selecionado if c["ean"] in excluidos)
        n_efetivo = max(n - excluidos_do_grupo, 0)
        restantes = [c for c in ordenados if c["ean"] not in usados and c["ean"] not in excluidos]
        escolhidos = restantes[:n_efetivo]
        for c in escolhidos:
            usados.add(c["ean"])
            resultado.append({
                "ean": c["ean"],
                "descricao": c["descricao"],
                "categoria": nome_grupo,
                "venda": c["venda"] or Decimal("0"),
                "itens": c["itens"] or Decimal("0"),
            })

    for nome_grupo, classificacao, subclassificacao, n in _CATEGORIAS_MONITORAMENTO_DIARIO:
        if subclassificacao == "__resto__":
            excluidas = {sub for _, cl, sub, _ in _CATEGORIAS_MONITORAMENTO_DIARIO
                         if cl == classificacao and sub not in (None, "__resto__")}
            disponiveis = [c for c in candidatos
                           if c["classificacao"] == classificacao and c["subclassificacao"] not in excluidas]
        elif subclassificacao is None:
            disponiveis = [c for c in candidatos if c["classificacao"] == classificacao]
        else:
            disponiveis = [c for c in candidatos
                            if c["classificacao"] == classificacao and c["subclassificacao"] == subclassificacao]
        _selecionar(nome_grupo, disponiveis, n)

    _selecionar("Top geral (fora das categorias)", candidatos, _VAGAS_TOP_GERAL_MONITORAMENTO_DIARIO)

    for ajuste in inclusoes:
        if ajuste.ean in usados:
            continue
        candidato = candidatos_por_ean.get(ajuste.ean)
        if candidato:
            descricao, venda, itens = candidato["descricao"], candidato["venda"] or Decimal("0"), candidato["itens"] or Decimal("0")
        else:
            produto = Produto.objects.filter(ean=ajuste.ean).values("descricao").first()
            descricao, venda, itens = (produto or {}).get("descricao", ajuste.ean), Decimal("0"), Decimal("0")
        usados.add(ajuste.ean)
        resultado.append({
            "ean": ajuste.ean,
            "descricao": descricao,
            "categoria": ajuste.categoria or "Ajuste manual",
            "venda": venda,
            "itens": itens,
        })

    return resultado


def curva_quantidade_agregada(eans: list[str]) -> dict[str, list[dict]]:
    """Quantidade vendida (soma de `itens`) por mês, agregada em TODAS as
    lojas (rede inteira, não por loja individual) -- pedido explícito do
    Gabriel na tela "Selecionar Itens Relevantes" ("não precisa ser curva
    por loja, uma curva geral (da rede)"), diferente do padrão por-loja já
    usado no Monitor de Preço (`montar_curvas_quantidade_por_loja`). 1
    query agrupada por EAN+mês pra todos os candidatos de uma vez (são só
    ~166 itens), não 1 query por item."""
    if not eans:
        return {}
    dados = (
        VendaItem.objects.filter(produto__ean__in=eans)
        .values("produto__ean", "ano_mes")
        .annotate(total=Sum("itens"))
        .order_by("produto__ean", "ano_mes")
    )
    curvas: dict[str, list[dict]] = defaultdict(list)
    for d in dados:
        curvas[d["produto__ean"]].append({"mes": d["ano_mes"], "quantidade": float(d["total"] or 0)})
    return dict(curvas)


def eans_selecionados_relevantes(eans_candidatos: list[str]) -> set[str]:
    """Dos candidatos sugeridos, quais Gabriel decidiu acompanhar de
    verdade (tela "Selecionar Itens Relevantes") -- sem registro ainda
    conta como selecionado (candidato sugerido já é relevante até prova
    em contrário, ver docstring do model)."""
    if not eans_candidatos:
        return set()
    nao_selecionados = set(
        SelecaoItemRelevante.objects.filter(ean__in=eans_candidatos, selecionado=False)
        .values_list("ean", flat=True)
    )
    return set(eans_candidatos) - nao_selecionados


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
