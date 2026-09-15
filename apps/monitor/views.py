from django.shortcuts import render

from apps.captacao.models import PrecoCaptado
from apps.lojas.models import Loja
from apps.produtos.models import Produto

from .services import montar_comparativo


def monitor_preco(request):
    cidade = request.GET.get("cidade") or None
    bandeira = request.GET.get("bandeira") or None
    classificacao = request.GET.get("classificacao") or None
    subclassificacao = request.GET.get("subclassificacao") or None
    situacao = request.GET.get("situacao") or None
    loja_id = request.GET.get("loja") or None
    bairro = request.GET.get("bairro") or None

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
    subclassificacoes_qs = Produto.objects.exclude(subclassificacao="")
    if classificacao:
        # cascata: só as subclassificações que existem DENTRO da
        # classificação escolhida, não a lista inteira do catálogo --
        # Gabriel notou que escolher "GENÉRICOS" ainda mostrava
        # "ABSORVENTE"/"BALANÇA"/etc. sem relação nenhuma.
        subclassificacoes_qs = subclassificacoes_qs.filter(classificacao=classificacao)
    subclassificacoes = list(
        subclassificacoes_qs.values_list("subclassificacao", flat=True).distinct().order_by("subclassificacao")
    )
    bairros = list(
        PrecoCaptado.objects.exclude(bairro="")
        .values_list("bairro", flat=True).distinct().order_by("bairro")
    )
    lojas_com_dado = set(
        PrecoCaptado.objects.filter(rede__tipo="nossa", loja__isnull=False)
        .values_list("loja_id", flat=True).distinct()
    )
    lojas = [
        {"id": l.id, "nome": l.nome, "bandeira": l.bandeira, "cidade": l.cidade,
         "tem_dado": l.id in lojas_com_dado}
        for l in Loja.objects.filter(ativa=True).order_by("cidade", "nome")
    ]

    linhas = montar_comparativo(
        cidade=cidade, bandeira=bandeira, classificacao=classificacao,
        subclassificacao=subclassificacao, situacao=situacao,
        loja_id=int(loja_id) if loja_id else None, bairro=bairro,
    )

    context = {
        "linhas": linhas,
        "cidades": cidades,
        "bandeiras": bandeiras,
        "classificacoes": classificacoes,
        "subclassificacoes": subclassificacoes,
        "lojas": lojas,
        "bairros": bairros,
        "cidade_selecionada": cidade,
        "bandeira_selecionada": bandeira,
        "classificacao_selecionada": classificacao,
        "subclassificacao_selecionada": subclassificacao,
        "situacao_selecionada": situacao,
        "loja_selecionada": int(loja_id) if loja_id else None,
        "bairro_selecionado": bairro,
        "total": len(linhas),
        "mais_caros": sum(1 for l in linhas if (l["diferenca_pct"] or 0) > 0),
        "sem_comparacao": sum(1 for l in linhas if l["diferenca_pct"] is None),
    }
    return render(request, "monitor/monitor_preco.html", context)
