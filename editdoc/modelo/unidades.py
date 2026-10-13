"""Conversoes de unidade do editor. Sem Qt.

O OOXML fala em twips (1/20 de ponto). O layout do Qt, a 96 dpi, fala em px.
Um twip e' 1/15 de px96, e por isso px = twips / 15.
"""

from __future__ import annotations

TWIPS_POR_PX = 15
#: Imagens (DrawingML) medem em EMU: 914400 por polegada, 9525 por px96, 635 por twip.
EMU_POR_PX = 9525
EMU_POR_TWIP = 635
EMU_POR_CM = 360000

#: Passo do botao "aumentar recuo": 0,5 polegada a 96 dpi, o mesmo do Word.
RECUO_PADRAO_PX = 48
#: O mesmo passo em twips: e' nessa unidade que o recuo fica no formato do bloco (0.1.4).
RECUO_PADRAO_TW = 720


def px_de_twips(twips: float) -> float:
    return twips / TWIPS_POR_PX


def twips_de_px(px: float) -> int:
    return round(px * TWIPS_POR_PX)


def px_de_emu(emu: float) -> float:
    return emu / EMU_POR_PX


def emu_de_px(px: float) -> int:
    return round(px * EMU_POR_PX)


def px_de_oitavos_pt(oitavos: float) -> float:
    """Espessura de borda (w:sz, em oitavos de ponto) em px96: 1 pt = 4/3 px."""
    return oitavos / 8 * 96 / 72
