"""Conversoes de unidade do editor. Sem Qt.

O OOXML fala em twips (1/20 de ponto). O layout do Qt, a 96 dpi, fala em px.
Um twip e' 1/15 de px96, e por isso px = twips / 15.
"""

from __future__ import annotations

TWIPS_POR_PX = 15

#: Passo do botao "aumentar recuo": 0,5 polegada a 96 dpi, o mesmo do Word.
RECUO_PADRAO_PX = 48


def px_de_twips(twips: float) -> float:
    return twips / TWIPS_POR_PX


def twips_de_px(px: float) -> int:
    return round(px * TWIPS_POR_PX)
