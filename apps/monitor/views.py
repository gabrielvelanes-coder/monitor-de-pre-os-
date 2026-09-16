from io import StringIO

from django.contrib import messages
from django.core.management import call_command
from django.db.models import Max
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.captacao.models import PrecoCaptado
from apps.lojas.models import Loja
from apps.produtos.models import Produto

from .services import montar_comparativo


def sincronizar_agora(request):
    """Botão "Sincronizar agora" -- roda sincronizar_captacao (que já
    encadeia vincular_lojas_captacao e extrair_bairros_captacao) na hora,
    pra quem não quiser esperar a Tarefa Agendada ou não tiver uma
    configurada. Gabriel pediu depois de notar que a tela ficou 14h sem
    atualizar (16/09/26) sem nenhum aviso disso na cara."""
    saida = StringIO()
    try:
        call_command("sincronizar_captacao", stdout=saida)
        resumo = saida.getvalue().strip().splitlines()
        messages.success(request, resumo[0] if resumo else "Sincronizado.")
    except Exception as exc:
        messages.error(request, f"Falha ao sincronizar: {exc}")

    destino = request.META.get("HTTP_REFERER") or reverse("monitor:monitor_preco")
    return redirect(destino)


def monitor_preco(request):
    cidade = request.GET.get("cidade") or None
    bandeira = request.GET.get("bandeira") or None
    classificacao = request.GET.get("classificacao") or None
    subclassificacao = request.GET.get("subclassificacao") or None
    situacao = request.GET.get("situacao") or None
    loja_id = request.GET.get("loja") or None
    bairro = request.GET.get("bairro") or None
    detalhe = request.GET.get("detalhe") or None

    querystring = request.GET.copy()
    querystring.pop("detalhe", None)
    querystring_sem_detalhe = querystring.urlencode()

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

    loja_id_int = int(loja_id) if loja_id else None
    if loja_id_int:
        # a loja já implica cidade/bandeira -- mostra os dropdowns
        # refletindo a loja de verdade, não um valor da URL que o
        # serviço vai ignorar (evita a tela "mentir" sobre o filtro
        # aplicado -- ver bug corrigido em montar_comparativo).
        loja_escolhida = next((l for l in lojas if l["id"] == loja_id_int), None)
        if loja_escolhida:
            cidade, bandeira = loja_escolhida["cidade"], loja_escolhida["bandeira"]

    linhas = montar_comparativo(
        cidade=cidade, bandeira=bandeira, classificacao=classificacao,
        subclassificacao=subclassificacao, situacao=situacao,
        loja_id=loja_id_int, bairro=bairro,
    )

    ultima_sincronizacao = PrecoCaptado.objects.aggregate(m=Max("atualizado_em"))["m"]
    minutos_desde_sync = None
    if ultima_sincronizacao:
        minutos_desde_sync = int((timezone.now() - ultima_sincronizacao).total_seconds() // 60)

    context = {
        "ultima_sincronizacao": ultima_sincronizacao,
        "minutos_desde_sync": minutos_desde_sync,
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
        "loja_selecionada": loja_id_int,
        "bairro_selecionado": bairro,
        "detalhe_aberto": detalhe,
        "querystring_sem_detalhe": querystring_sem_detalhe,
        "total": len(linhas),
        "mais_caros": sum(1 for l in linhas if (l["diferenca_pct"] or 0) > 0),
        "sem_comparacao": sum(1 for l in linhas if l["diferenca_pct"] is None),
    }
    return render(request, "monitor/monitor_preco.html", context)
