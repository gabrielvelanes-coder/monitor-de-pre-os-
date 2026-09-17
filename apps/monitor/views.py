from io import StringIO

from django.contrib import messages
from django.core.management import call_command
from django.shortcuts import redirect, render
from django.urls import reverse

from .services import (
    carregar_itens_relevantes,
    info_sincronizacao,
    montar_comparativo,
    montar_curvas_quantidade_por_loja,
    opcoes_filtro_comparativo,
    resolver_loja_filtro,
    svg_sparkline_quantidade,
)


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

    # pros cartões (Itens comparados/Mais caros/Sem concorrente) virarem
    # link de filtro -- mantém os outros filtros, troca só "situacao".
    querystring_base_cartao = request.GET.copy()
    querystring_base_cartao.pop("detalhe", None)
    querystring_base_cartao.pop("situacao", None)
    _base = querystring_base_cartao.urlencode()
    _prefixo = f"{_base}&" if _base else ""
    link_cartao_todos = f"?{_base}"
    link_cartao_mais_caros = f"?{_prefixo}situacao=mais_caro"
    link_cartao_sem_concorrente = f"?{_prefixo}situacao=sem_concorrente"

    opcoes = opcoes_filtro_comparativo(classificacao)
    cidades, bandeiras = opcoes["cidades"], opcoes["bandeiras"]
    classificacoes, subclassificacoes = opcoes["classificacoes"], opcoes["subclassificacoes"]
    bairros, lojas = opcoes["bairros"], opcoes["lojas"]

    loja_id_int = int(loja_id) if loja_id else None
    cidade_loja, bandeira_loja = resolver_loja_filtro(loja_id_int, lojas)
    if loja_id_int and cidade_loja:
        cidade, bandeira = cidade_loja, bandeira_loja

    linhas = montar_comparativo(
        cidade=cidade, bandeira=bandeira, classificacao=classificacao,
        subclassificacao=subclassificacao, situacao=situacao,
        loja_id=loja_id_int, bairro=bairro,
    )
    # cartões sempre mostram o panorama geral (sem o filtro de situação),
    # mesmo quando a tabela está filtrada por um deles -- senão clicar no
    # cartão "sem concorrente" faria o próprio cartão "itens comparados"
    # virar 485 também, perdendo a noção do total.
    linhas_para_cartoes = linhas if not situacao else montar_comparativo(
        cidade=cidade, bandeira=bandeira, classificacao=classificacao,
        subclassificacao=subclassificacao, situacao=None,
        loja_id=loja_id_int, bairro=bairro,
    )

    # curva de quantidade vendida, 1 sparkline POR LOJA (só pra a linha
    # com "ver detalhes" aberto -- não faz sentido calcular pra tabela
    # inteira toda vez). Grava direto em cada "nossas_lojas" da linha
    # aberta (`nl["tendencia"]`) pra o template acessar sem precisar de
    # lookup de dict por chave variável, que o Django template não faz.
    if detalhe:
        linha_detalhe = next((l for l in linhas if l["chave"] == detalhe), None)
        if linha_detalhe:
            loja_ids = [nl["loja_id"] for nl in linha_detalhe["nossas_lojas"] if nl["loja_id"]]
            curvas = montar_curvas_quantidade_por_loja(linha_detalhe["ean"], loja_ids)
            for nl in linha_detalhe["nossas_lojas"]:
                nl["tendencia"] = svg_sparkline_quantidade(curvas.get(nl["loja_id"], []))

    context = {
        **info_sincronizacao(),
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
        "link_cartao_todos": link_cartao_todos,
        "link_cartao_mais_caros": link_cartao_mais_caros,
        "link_cartao_sem_concorrente": link_cartao_sem_concorrente,
        "total": len(linhas_para_cartoes),
        "mais_caros": sum(1 for l in linhas_para_cartoes if (l["diferenca_pct"] or 0) > 0),
        "sem_comparacao": sum(1 for l in linhas_para_cartoes if l["diferenca_pct"] is None),
    }
    return render(request, "monitor/monitor_preco.html", context)


def itens_relevantes(request):
    """Mesmo comparativo do Monitor de Preço (`montar_comparativo`),
    filtrado só pros itens mais relevantes em venda (Top faturamento + Top
    unidades, ver `apps.vendas.services.itens_relevantes` /
    `manage.py exportar_itens_relevantes`) -- é o que alimenta a fila
    prioritária do robô, então essa tela é "como estamos de preço nos
    itens que o robô está tratando com prioridade"."""
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

    itens_relevantes_lista = carregar_itens_relevantes()
    eans_relevantes = {i["ean"] for i in itens_relevantes_lista}
    info_por_ean = {i["ean"]: i for i in itens_relevantes_lista}

    opcoes = opcoes_filtro_comparativo(classificacao)
    cidades, bandeiras = opcoes["cidades"], opcoes["bandeiras"]
    classificacoes, subclassificacoes = opcoes["classificacoes"], opcoes["subclassificacoes"]
    bairros, lojas = opcoes["bairros"], opcoes["lojas"]

    loja_id_int = int(loja_id) if loja_id else None
    cidade_loja, bandeira_loja = resolver_loja_filtro(loja_id_int, lojas)
    if loja_id_int and cidade_loja:
        cidade, bandeira = cidade_loja, bandeira_loja

    linhas = []
    eans_com_captacao: set[str] = set()
    if eans_relevantes:
        linhas = montar_comparativo(
            cidade=cidade, bandeira=bandeira, classificacao=classificacao,
            subclassificacao=subclassificacao, situacao=situacao,
            loja_id=loja_id_int, bairro=bairro, eans=eans_relevantes,
        )
        for l in linhas:
            info = info_por_ean.get(l["ean"], {})
            l["origem"] = info.get("origem")

        # cobertura sempre olha o panorama geral (sem o filtro de situação)
        # -- mesmo espírito dos cartões do Monitor de Preço, senão filtrar
        # por "mais caro" faria a cobertura parecer pior do que é de verdade.
        linhas_cobertura = linhas if not situacao else montar_comparativo(
            cidade=cidade, bandeira=bandeira, classificacao=classificacao,
            subclassificacao=subclassificacao, loja_id=loja_id_int, bairro=bairro,
            eans=eans_relevantes,
        )
        eans_com_captacao = {l["ean"] for l in linhas_cobertura}

    if detalhe:
        linha_detalhe = next((l for l in linhas if l["chave"] == detalhe), None)
        if linha_detalhe:
            loja_ids = [nl["loja_id"] for nl in linha_detalhe["nossas_lojas"] if nl["loja_id"]]
            curvas = montar_curvas_quantidade_por_loja(linha_detalhe["ean"], loja_ids)
            for nl in linha_detalhe["nossas_lojas"]:
                nl["tendencia"] = svg_sparkline_quantidade(curvas.get(nl["loja_id"], []))

    context = {
        **info_sincronizacao(),
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
        "total_relevantes": len(eans_relevantes),
        "total_com_captacao": len(eans_com_captacao),
        "exportado_ainda": bool(itens_relevantes_lista),
    }
    return render(request, "monitor/itens_relevantes.html", context)
