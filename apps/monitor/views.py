from django.shortcuts import render

from apps.captacao.models import PrecoCaptado
from apps.produtos.models import Produto

from .services import montar_comparativo


def monitor_preco(request):
    cidade = request.GET.get("cidade") or None
    bandeira = request.GET.get("bandeira") or None
    classificacao = request.GET.get("classificacao") or None
    subclassificacao = request.GET.get("subclassificacao") or None
    situacao = request.GET.get("situacao") or None

    cidades = list(
        PrecoCaptado.objects.exclude(cidade_busca="")
        .values_list("cidade_busca", flat=True).distinct().order_by("cidade_busca")
    )
    bandeiras = list(
        PrecoCaptado.objects.filter(rede__tipo="nossa")
        .values_list("rede__nome", flat=True).distinct().order_by("rede__nome")
    )
    classificacoes = list(
        Produto.objects.exclude(classificacao="")
        .values_list("classificacao", flat=True).distinct().order_by("classificacao")
    )
    subclassificacoes = list(
        Produto.objects.exclude(subclassificacao="")
        .values_list("subclassificacao", flat=True).distinct().order_by("subclassificacao")
    )

    linhas = montar_comparativo(
        cidade=cidade, bandeira=bandeira, classificacao=classificacao,
        subclassificacao=subclassificacao, situacao=situacao,
    )

    context = {
        "linhas": linhas,
        "cidades": cidades,
        "bandeiras": bandeiras,
        "classificacoes": classificacoes,
        "subclassificacoes": subclassificacoes,
        "cidade_selecionada": cidade,
        "bandeira_selecionada": bandeira,
        "classificacao_selecionada": classificacao,
        "subclassificacao_selecionada": subclassificacao,
        "situacao_selecionada": situacao,
        "total": len(linhas),
        "mais_caros": sum(1 for l in linhas if (l["diferenca_pct"] or 0) > 0),
        "sem_comparacao": sum(1 for l in linhas if l["diferenca_pct"] is None),
    }
    return render(request, "monitor/monitor_preco.html", context)
