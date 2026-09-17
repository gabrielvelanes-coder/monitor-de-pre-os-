"""Lógica de comparação nosso-preço x concorrência — sem nenhuma sugestão
ou recomendação de preço, só monitoramento (pedido explícito do Gabriel:
"não quero trabalhar com recomendação de preço, apenas monitorar e
comparar com o meu")."""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from decimal import Decimal

from django.conf import settings
from django.db.models import Max, Sum
from django.utils import timezone
from django.utils.safestring import mark_safe

from apps.captacao.models import PrecoCaptado
from apps.lojas.models import Loja
from apps.produtos.models import Produto
from apps.vendas.models import VendaItem

_MESES_ABREV = {
    "01": "jan", "02": "fev", "03": "mar", "04": "abr", "05": "mai", "06": "jun",
    "07": "jul", "08": "ago", "09": "set", "10": "out", "11": "nov", "12": "dez",
}


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
    eans: set[str] | None = None,
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
    enganosa) mas o detalhe expandido mostra a distância por loja.

    `eans` (opcional): restringe a comparação a um conjunto de EANs --
    usado pela tela "Itens Relevantes" pra filtrar só os itens mais
    importantes em venda, sem duplicar toda essa lógica de comparação."""
    nossos_qs = PrecoCaptado.objects.filter(rede__tipo="nossa", preco__isnull=False)
    # rede__ativa=True -- Gabriel pediu (16/09/26) pra ver TODO concorrente
    # captado (não só os 6 curados originais), com opção de marcar/desmarcar
    # quem conta ("não existe isso de curado"). `descobrir_concorrentes`
    # cria 1 Rede por estabelecimento novo, sempre inativa até ele revisar
    # em Configuração de Concorrentes -- só as ativas entram aqui.
    conc_qs = PrecoCaptado.objects.filter(rede__tipo="concorrente", rede__ativa=True, preco__isnull=False)
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
    if eans:
        nossos_qs = nossos_qs.filter(ean__in=eans)
        conc_qs = conc_qs.filter(ean__in=eans)

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


def opcoes_filtro_comparativo(classificacao: str | None = None) -> dict:
    """Listas pros dropdowns de filtro do comparativo -- Monitor de Preço e
    Itens Relevantes usam exatamente as mesmas (mesmo universo de captação/
    cadastro), só o resultado final que muda. `subclassificacoes` vem em
    cascata dentro da `classificacao` escolhida (Gabriel notou que sem
    isso, escolher "GENÉRICOS" ainda mostrava subclassificação sem
    relação nenhuma)."""
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
    return {
        "cidades": cidades, "bandeiras": bandeiras, "classificacoes": classificacoes,
        "subclassificacoes": subclassificacoes, "bairros": bairros, "lojas": lojas,
    }


def resolver_loja_filtro(loja_id: int | None, lojas: list[dict]) -> tuple[str | None, str | None]:
    """Loja implica cidade/bandeira -- devolve (cidade, bandeira) da loja
    escolhida, pra os dropdowns refletirem o filtro de verdade em vez de
    um valor da URL que `montar_comparativo` vai ignorar (ver bug
    corrigido nela: cidade/bandeira da URL em conflito com a loja quebrava
    a comparação inteira em silêncio)."""
    if not loja_id:
        return None, None
    loja = next((l for l in lojas if l["id"] == loja_id), None)
    return (loja["cidade"], loja["bandeira"]) if loja else (None, None)


def info_sincronizacao() -> dict:
    """Há quanto tempo a captação foi sincronizada pela última vez -- usado
    pela barra "dado mais recente: há N min" no topo do Monitor de Preço e
    de Itens Relevantes (as duas dependem do mesmo `PrecoCaptado`, então é
    a mesma informação nas duas telas)."""
    ultima = PrecoCaptado.objects.aggregate(m=Max("atualizado_em"))["m"]
    minutos = int((timezone.now() - ultima).total_seconds() // 60) if ultima else None
    return {"ultima_sincronizacao": ultima, "minutos_desde_sync": minutos}


def carregar_itens_relevantes() -> list[dict]:
    """Lê o `_itens_relevantes.json` gravado por `manage.py
    exportar_itens_relevantes` na pasta do robo_cotacao -- lista dos itens
    mais relevantes em venda (Top faturamento + Top unidades, união) que
    alimenta a tela "Itens Relevantes" e a fila prioritária do robô. Vazio
    se o export nunca rodou ainda (tela mostra "sem dado", não quebra)."""
    caminho = settings.CAMINHO_ITENS_RELEVANTES_ROBO_COTACAO
    if not caminho.exists():
        return []
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f).get("itens", [])


def montar_curvas_quantidade_por_loja(ean: str, loja_ids: list[int]) -> dict[int, list[dict]]:
    """Quantidade vendida (soma de `itens`) por mês, 1 curva POR LOJA (não
    somada) -- Gabriel viu a curva agregada e perguntou "cadê a curva da
    Loja 2, Loja 4, Loja 3?" (16/09/26): queria comparar a tendência de
    cada loja lado a lado, não só o total do produto. 1 query só
    (agrupada por loja+mês), não 1 query por loja -- só chamada pra a
    linha que está com "ver detalhes" aberto."""
    if not loja_ids or not ean:
        return {}
    dados = (
        VendaItem.objects.filter(produto__ean=ean, loja_id__in=loja_ids)
        .values("loja_id", "ano_mes")
        .annotate(total=Sum("itens"))
        .order_by("loja_id", "ano_mes")
    )
    curvas: dict[int, list[dict]] = defaultdict(list)
    for d in dados:
        curvas[d["loja_id"]].append({"mes": d["ano_mes"], "quantidade": float(d["total"] or 0)})
    return dict(curvas)


def _caminho_suave(pontos_xy: list[tuple[float, float]]) -> str:
    """Comando de `<path d="...">` que passa suave pelos pontos (técnica
    de curva por ponto médio: cada ponto vira o "controle" da curva até o
    meio do caminho pro próximo) -- em vez de zigue-zague reto entre os
    pontos, fica com a cara de gráfico de verdade (Stripe/Linear-style)."""
    if len(pontos_xy) < 2:
        return ""
    x0, y0 = pontos_xy[0]
    d = f"M {x0:.1f},{y0:.1f}"
    for i in range(len(pontos_xy) - 1):
        xa, ya = pontos_xy[i]
        xb, yb = pontos_xy[i + 1]
        mx, my = (xa + xb) / 2, (ya + yb) / 2
        d += f" Q {xa:.1f},{ya:.1f} {mx:.1f},{my:.1f}"
    xl, yl = pontos_xy[-1]
    d += f" T {xl:.1f},{yl:.1f}"
    return d


def svg_sparkline_quantidade(pontos: list[dict]) -> str:
    """Sparkline compacta (SVG puro, sem lib nova -- mesma filosofia do
    Haversine em Python puro) da quantidade vendida por mês de 1 loja só,
    pensada pra caber numa célula da tabela "Nossas lojas" -- coloca a
    curva de cada loja lado a lado com a linha dela (Loja 2 x Loja 4 x
    Loja 3), sem precisar de legenda/cor por loja (o nome já está na
    linha da tabela). Curva suave + área em gradiente + brilho no ponto
    mais recente (16/09/26, pedido do Gabriel pra deixar o painel "mais
    tecnológico" -- antes era só uma linha reta fina sem nenhum relevo).
    Cor em hexadecimal fixo (não `var(--acento)`) porque atributo de
    apresentação SVG nem sempre resolve custom property de CSS entre
    navegadores. Mês corrente vem com marcador vazado (comparado com
    `timezone.now()`, não fixo em "setembro" -- continua valendo sozinho
    mês que vem) pra não parecer queda de venda quando é só o mês não ter
    terminado -- simplificação consciente: a versão anterior tracejava o
    último trecho da linha reta, mas com curva suave isolar só o último
    trecho pra tracejar exigiria reconstruir o path manualmente (a
    continuidade da curva depende do trecho anterior); o marcador vazado
    sozinho já comunica "parcial" sem essa complexidade extra."""
    if not pontos:
        return ""
    ACENTO, BG = "#5b8dee", "#0a0d13"
    LARG, ALT = 132, 34
    PAD_X, PAD_Y = 4, 6
    largura_util = LARG - 2 * PAD_X
    altura_util = ALT - 2 * PAD_Y

    maximo = max((p["quantidade"] for p in pontos), default=0) or 1
    mes_atual = timezone.now().strftime("%Y-%m")
    n = len(pontos)
    passo_x = largura_util / (n - 1) if n > 1 else 0

    coords = []
    for i, p in enumerate(pontos):
        x = PAD_X + i * passo_x
        y = PAD_Y + altura_util - (p["quantidade"] / maximo) * altura_util
        coords.append((x, y, p))

    grad_id = f"grad{id(pontos) % 100000}"
    partes = []

    if n > 1:
        linha = _caminho_suave([(x, y) for x, y, _ in coords])
        x0, _, _ = coords[0]
        xl, _, _ = coords[-1]
        area = f"{linha} L {xl:.1f},{ALT} L {x0:.1f},{ALT} Z"
        partes.append(
            f'<defs><linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="{ACENTO}" stop-opacity="0.35"/>'
            f'<stop offset="100%" stop-color="{ACENTO}" stop-opacity="0"/>'
            f'</linearGradient></defs>'
        )
        partes.append(f'<path d="{area}" fill="url(#{grad_id})"/>')
        partes.append(f'<path d="{linha}" fill="none" stroke="{ACENTO}" stroke-width="1.6" stroke-linecap="round"/>')

    for i, (x, y, p) in enumerate(coords):
        parcial = p["mes"] == mes_atual
        mes_label = _MESES_ABREV.get(p["mes"][-2:], p["mes"])
        titulo = f'{mes_label}/{p["mes"][:4]}{" (parcial)" if parcial else ""}: {p["quantidade"]:g} un.'
        if i == n - 1:
            # ponto mais recente -- halo de brilho por trás + marcador
            # maior (vazado se mês corrente/parcial)
            preenchido = "none" if parcial else BG
            partes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{ACENTO}" opacity="0.18"/>')
            partes.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{preenchido}" '
                f'stroke="{ACENTO}" stroke-width="1.8"><title>{titulo}</title></circle>'
            )
        else:
            partes.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="{ACENTO}" '
                f'stroke="{ACENTO}" stroke-width="1"><title>{titulo}</title></circle>'
            )

    svg = (
        f'<svg viewBox="0 0 {LARG} {ALT}" width="{LARG}" height="{ALT}" '
        f'role="img" aria-label="Tendência de quantidade vendida por mês">'
        + "".join(partes) + "</svg>"
    )
    return mark_safe(svg)
