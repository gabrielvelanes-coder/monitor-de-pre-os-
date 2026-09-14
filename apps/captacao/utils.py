"""Helpers puros de leitura/normalização — sem tocar no banco do robô."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def parse_preco_brl(texto: str | None) -> Decimal | None:
    """'R$ 1.234,56' -> Decimal('1234.56'). None se não der pra converter
    (preço vazio, "indisponível" etc. — comum quando o card não trouxe
    valor)."""
    if not texto:
        return None
    limpo = re.sub(r"[^\d,.]", "", str(texto)).strip()
    if not limpo:
        return None
    # formato BR: ponto = milhar, vírgula = decimal
    limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return Decimal(limpo)
    except InvalidOperation:
        return None


def identificar_rede(estabelecimento: str, redes_cache: list[tuple[int, list[str]]]) -> int | None:
    """`redes_cache` = [(rede_id, [substrings...]), ...] pré-carregado (evita
    1 query por linha ao sincronizar milhares de registros). Retorna o id
    da PRIMEIRA rede cujo substring bate, case-insensitive."""
    nome = (estabelecimento or "").upper()
    for rede_id, substrings in redes_cache:
        for sub in substrings:
            if sub.upper() in nome:
                return rede_id
    return None
