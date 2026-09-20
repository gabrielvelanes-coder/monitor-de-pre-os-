from django.contrib import messages
from django.shortcuts import redirect, render

from apps.lojas.models import Loja
from apps.monitor.services import svg_sparkline_quantidade
from apps.vendas.models import SelecaoItemRelevante, VendaItem

from .services import (
    curva_quantidade_agregada,
    custo_margem_resumo,
    eans_selecionados_relevantes,
    itens_relevantes_com_manuais,
    relevancia_por_classificacao,
)


def relevancia(request):
    ano_mes_de = request.GET.get("de") or None
    ano_mes_ate = request.GET.get("ate") or None
    bandeira = request.GET.get("bandeira") or None
    cidade = request.GET.get("cidade") or None
    classificacao_escolhida = request.GET.get("classificacao") or None

    meses = list(VendaItem.objects.values_list("ano_mes", flat=True).distinct().order_by("ano_mes"))
    bandeiras = list(Loja.objects.exclude(bandeira="").values_list("bandeira", flat=True).distinct().order_by("bandeira"))
    cidades = list(Loja.objects.exclude(cidade="").values_list("cidade", flat=True).distinct().order_by("cidade"))

    dados = relevancia_por_classificacao(ano_mes_de, ano_mes_ate, bandeira, cidade)

    resumo = []
    for classificacao, itens in dados.items():
        relevantes = [i for i in itens if i["relevante"]]
        resumo.append({
            "classificacao": classificacao,
            "venda_total": sum(i["venda"] for i in itens),
            "n_itens": len(itens),
            "n_relevantes": len(relevantes),
            "top_item": itens[0]["descricao"] if itens else "",
        })
    resumo.sort(key=lambda r: r["venda_total"], reverse=True)

    context = {
        "meses": meses, "bandeiras": bandeiras, "cidades": cidades,
        "ano_mes_de": ano_mes_de, "ano_mes_ate": ano_mes_ate,
        "bandeira_selecionada": bandeira, "cidade_selecionada": cidade,
        "resumo": resumo,
        "classificacao_escolhida": classificacao_escolhida,
        "itens_detalhe": dados.get(classificacao_escolhida, []) if classificacao_escolhida else None,
    }
    return render(request, "vendas/relevancia.html", context)


def custo_margem(request):
    ano_mes_de = request.GET.get("de") or None
    ano_mes_ate = request.GET.get("ate") or None
    bandeira = request.GET.get("bandeira") or None
    cidade = request.GET.get("cidade") or None

    meses = list(VendaItem.objects.values_list("ano_mes", flat=True).distinct().order_by("ano_mes"))
    bandeiras = list(Loja.objects.exclude(bandeira="").values_list("bandeira", flat=True).distinct().order_by("bandeira"))
    cidades = list(Loja.objects.exclude(cidade="").values_list("cidade", flat=True).distinct().order_by("cidade"))

    dados = custo_margem_resumo(ano_mes_de, ano_mes_ate, bandeira, cidade)

    context = {
        "meses": meses, "bandeiras": bandeiras, "cidades": cidades,
        "ano_mes_de": ano_mes_de, "ano_mes_ate": ano_mes_ate,
        "bandeira_selecionada": bandeira, "cidade_selecionada": cidade,
        **dados,
    }
    return render(request, "vendas/custo_margem.html", context)


def selecao_itens_relevantes(request):
    """Gabriel escolhe, dentro dos candidatos sugeridos (Top faturamento +
    Top unidades, `services.itens_relevantes`), quais itens realmente
    quer acompanhar de preço todo dia -- pedido explícito (17/09/26):
    "você identifica quais itens são mais relevantes e eu escolho quais
    quero olhar". `manage.py exportar_itens_relevantes` usa só os
    selecionados daqui pra alimentar a fila prioritária do robô."""
    candidatos = itens_relevantes_com_manuais(top_n=100)
    eans = [c["ean"] for c in candidatos]

    if request.method == "POST":
        marcados = set(request.POST.getlist("selecionado"))
        for ean in eans:
            SelecaoItemRelevante.objects.update_or_create(
                ean=ean, defaults={"selecionado": ean in marcados},
            )
        messages.success(request, "Seleção de itens relevantes salva.")
        return redirect("vendas:selecao_itens_relevantes")

    selecionados = eans_selecionados_relevantes(eans)
    curvas = curva_quantidade_agregada(eans)

    linhas = [
        {
            **c,
            "selecionado": c["ean"] in selecionados,
            "curva": svg_sparkline_quantidade(curvas.get(c["ean"], [])),
        }
        for c in candidatos
    ]

    context = {
        "linhas": linhas,
        "n_selecionados": len(selecionados),
        "n_total": len(linhas),
    }
    return render(request, "vendas/selecao_itens_relevantes.html", context)
