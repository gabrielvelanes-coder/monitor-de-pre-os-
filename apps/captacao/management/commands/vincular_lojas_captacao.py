import re

from django.core.management.base import BaseCommand

from apps.captacao.models import PrecoCaptado
from apps.lojas.models import Loja

_REGEX_CEP = re.compile(r"\d{8},")
_REGEX_NUMERO = re.compile(r"\d+")
_REGEX_SN = re.compile(r"\bS[./]?N\b", re.IGNORECASE)
_PREFIXOS_LOGRADOURO = ("AVENIDA ", "AV ", "AV. ", "RUA ", "R ", "R. ", "PRACA ", "PRAÇA ", "PCA ")


def _numero_rua(endereco: str) -> str | None:
    """Primeiro número que aparece no endereço ANTES do CEP -- é o número
    do imóvel na maioria dos formatos vistos. BUG REAL corrigido 15/09/26:
    endereço 'S/N' (sem número) não tem dígito nenhum antes do CEP, mas a
    versão antiga buscava \\d+ na string INTEIRA e acabava casando os 8
    dígitos do CEP como se fosse o número da rua -- 209 registros de
    'AVENIDA AZIZ MARON S/N ... 45605412, ITABUNA' (Loja 4, que realmente
    não tem número no endereço) ficavam "sem candidata" por causa disso.
    Agora só procura número na parte ANTES do CEP; S/N vira None de
    verdade (cai no fallback por nome de rua)."""
    m_cep = _REGEX_CEP.search(endereco or "")
    prefixo = endereco[:m_cep.start()] if m_cep else (endereco or "")
    m = _REGEX_NUMERO.search(prefixo)
    return m.group() if m else None


def _numero_loja(endereco: str) -> str | None:
    """Número do endereço da Loja (cadastro) -- só tem 1 número normalmente
    (não tem CEP colado como no endereço do robô). BUG REAL corrigido
    15/09/26: comparar por SUBSTRING ('2' in 'PRAÇA JOSÉ BASTOS, 2 CENTRO')
    também batia contra qualquer outro número que CONTIVESSE o dígito '2'
    em outra posição ('128', '1299', '428A', '32') -- número curto (1-2
    dígitos) virava ambíguo por engano mesmo tendo 1 match exato de
    verdade. Agora extrai o número da loja e compara IGUALDADE, não
    substring.

    2º BUG REAL corrigido 20/09/26: Loja 08 tem endereço 'PRAÇA CAIRU, S/N
    LOJA 02 CENTRO' -- o '02' de "LOJA 02" (identificador interno, não
    número de rua) era lido como se fosse o número, escondendo que essa
    loja é S/N de verdade. Agora 'S/N' literal manda: se aparecer, a loja
    não tem número de rua, não importa que outro dígito sobre no texto."""
    if _REGEX_SN.search(endereco or ""):
        return None
    m = _REGEX_NUMERO.search(endereco or "")
    return m.group() if m else None


def _nome_rua(endereco: str) -> str:
    """Nome da rua/avenida, sem prefixo (AVENIDA/AV/RUA) e sem número --
    usado como fallback quando o endereço é 'S/N' dos dois lados (robô E
    cadastro), caso da Loja 4 ('AV AZIZ MARON, JEQUITIBÁ PLAZA' -- único
    endereço nosso sem número)."""
    texto = (endereco or "").upper()
    m_cep = _REGEX_CEP.search(texto)
    prefixo = texto[:m_cep.start()] if m_cep else texto
    # corta a partir do primeiro número (início do bairro), se tiver
    m_num = _REGEX_NUMERO.search(prefixo)
    if m_num:
        prefixo = prefixo[:m_num.start()]
    else:
        # sem número (S/N) -- corta a partir de "S/N" literal
        prefixo = re.split(r"\bS[./]?N\b", prefixo)[0]
    for p in _PREFIXOS_LOGRADOURO:
        if prefixo.startswith(p):
            prefixo = prefixo[len(p):]
            break
    return prefixo.strip().rstrip(",")


class Command(BaseCommand):
    help = (
        "Vincula cada PrecoCaptado de rede='nossa' a uma Loja específica, por "
        "heurística de endereço (número da rua) -- o robô só sabe a bandeira "
        "('DROGARIA VELANES'/'DROGARIA ULTRAPOPULAR'), não qual loja física. "
        "Best-effort: só vincula quando há exatamente 1 Loja candidata (mesma "
        "bandeira/cidade, mesmo número de rua); ambíguo ou sem candidata fica "
        "sem vínculo. Rodar depois de 'sincronizar_captacao' (ou via ele)."
    )

    def handle(self, *args, **options):
        pendentes = PrecoCaptado.objects.filter(rede__tipo="nossa", loja__isnull=True).select_related("rede")

        lojas_por_bandeira_cidade: dict[tuple[str, str], list[Loja]] = {}
        for loja in Loja.objects.exclude(bandeira="").exclude(cidade=""):
            lojas_por_bandeira_cidade.setdefault((loja.bandeira, loja.cidade), []).append(loja)

        vinculados, ambiguos, sem_candidata, sem_numero, vinculados_por_nome = 0, 0, 0, 0, 0
        for p in pendentes.iterator():
            candidatas = lojas_por_bandeira_cidade.get((p.rede.nome, p.cidade_busca), [])
            numero = _numero_rua(p.endereco)

            if numero:
                bateram = [l for l in candidatas if _numero_loja(l.endereco) == numero]
            else:
                # endereço S/N (sem número) -- só tenta candidata que
                # TAMBÉM não tem número, casando pelo nome da rua
                nome = _nome_rua(p.endereco)
                bateram = [
                    l for l in candidatas
                    if _numero_loja(l.endereco) is None and nome and nome in _nome_rua(l.endereco)
                ] if nome else []

            if len(bateram) == 1:
                p.loja = bateram[0]
                p.save(update_fields=["loja"])
                vinculados += 1
                if not numero:
                    vinculados_por_nome += 1
            elif len(bateram) > 1:
                ambiguos += 1
            elif not numero:
                sem_numero += 1
            else:
                sem_candidata += 1

        total = vinculados + ambiguos + sem_candidata + sem_numero
        self.stdout.write(self.style.SUCCESS(
            f"{vinculados} de {total} registro(s) vinculado(s) a uma loja "
            f"({vinculados_por_nome} deles por nome de rua, endereço 'S/N')."
        ))
        if ambiguos or sem_candidata or sem_numero:
            self.stdout.write(self.style.WARNING(
                f"Sem vínculo: {ambiguos} ambíguo(s) (mais de 1 loja batendo), "
                f"{sem_candidata} sem loja candidata (bandeira/cidade sem cadastro batendo), "
                f"{sem_numero} endereço 'S/N' sem loja candidata também sem número."
            ))
