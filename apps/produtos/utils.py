"""Normalização de código de produto (EAN ou etiqueta interna) -- os 3
relatórios do ERP não usam o mesmo formato pro mesmo código (zero à
esquerda, .0 de float do Excel...), então toda comparação usa o conjunto
de chaves possíveis, não a string crua."""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation


def parse_decimal(valor) -> Decimal | None:
    """Valor numérico do pandas (float/NaN/str) -> Decimal com 2 casas, ou
    None se não der pra converter."""
    if valor is None:
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    try:
        return round(Decimal(str(valor)), 2)
    except (InvalidOperation, ValueError):
        return None


def chaves_possiveis(valor) -> set[str]:
    """'000912' -> {'000912', '912'}; 7891317039738 (int/float do Excel)
    -> {'7891317039738'}. Vazio/None -> conjunto vazio."""
    if valor is None:
        return set()
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    if not texto or texto.lower() == "nan":
        return set()
    chaves = {texto}
    if texto.isdigit():
        chaves.add(str(int(texto)))
    return chaves


def extrair_classificacao_nivel1(classificacao_completa: str) -> str:
    """'ARVORE NOVA > PROPAGADO > OTC/MIP' -> 'PROPAGADO'. Esse nível é o
    agrupador usado pra relevância (pedido do Gabriel: "quais são os itens
    mais relevantes na classificação x o todo") -- fino o suficiente pra
    comparar itens parecidos, grosso o suficiente pra não virar 1
    classificação por item."""
    partes = [p.strip() for p in (classificacao_completa or "").split(">")]
    return partes[1] if len(partes) > 1 else (partes[0] if partes else "")
