"""Regua horizontal: margens e recuos do paragrafo do caret.

A area do corpo aparece branca e as margens cinza. A escala e' em centimetros, a
partir da margem esquerda. Dois marcadores: o triangulo de cima e' o recuo da primeira
linha; o de baixo, o recuo esquerdo. Arrastar um marcador muda o recuo, e ao soltar
a mudanca vira UM passo de desfazer (PainelDocumento.definir_recuos_do_paragrafo).

Os recuos sao em twips. O Qt guarda em pixels de 96 dpi (1 px = 15 twips); a conversao
e' feita no painel.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPolygonF
from PySide6.QtWidgets import QWidget

from editdoc.modelo.pagina import TWIPS_POR_CM

ALTURA_PX = 22
TOLERANCIA_PX = 6
#: Passo do arrasto: 1/16 de polegada (90 twips). O Word arredonda para uma faixa parecida.
PASSO_TW = 90

COR_MARGEM = QColor(0xD0, 0xD4, 0xDA)
COR_CORPO = QColor(255, 255, 255)
COR_MARCA = QColor(0x40, 0x46, 0x50)


class Regua(QWidget):
    def __init__(self, painel, parent=None) -> None:
        super().__init__(parent)
        self._painel = painel
        self._arrasto: str | None = None
        self._valor = (0, 0)  # (recuo esquerdo, recuo da primeira linha), em twips
        self.setFixedHeight(ALTURA_PX)
        self.setToolTip("Régua: arraste os marcadores para mudar o recuo do parágrafo")
        painel.cursorPositionChanged.connect(self.update)
        painel.paginaAlterada.connect(self.update)
        painel.zoomAlterado.connect(self.update)
        painel.textChanged.connect(self.update)
        painel.horizontalScrollBar().valueChanged.connect(self.update)

    # ----- conversao ---------------------------------------------------------
    def _x_do_corpo(self) -> float:
        """X, na regua, da margem esquerda (inicio do corpo)."""
        m = self._painel.mapa()
        return m.esquerda_folha - m.origem_x + self._painel.configuracao_pagina().margem_esq_tw * m.escala

    def _x_de_tw(self, tw: float) -> float:
        return self._x_do_corpo() + tw * self._painel.mapa().escala

    def _tw_de_x(self, x: float) -> float:
        return (x - self._x_do_corpo()) / self._painel.mapa().escala

    def _recuos_mostrados(self) -> tuple[int, int]:
        if self._arrasto is not None:
            return self._valor
        return self._painel.recuos_do_paragrafo()

    # ----- pintura -----------------------------------------------------------
    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), COR_MARGEM)
        cfg = self._painel.configuracao_pagina()
        x0 = self._x_do_corpo()
        x1 = self._x_de_tw(cfg.corpo_largura_tw())
        p.fillRect(QRectF(x0, 0, x1 - x0, self.height()), COR_CORPO)

        fonte = QFont(p.font())
        fonte.setPointSizeF(7.0)
        p.setFont(fonte)
        p.setPen(COR_MARCA)
        altura = self.height()
        cm = -int(x0 // (TWIPS_POR_CM * self._painel.mapa().escala)) - 1
        limite = int((self.width() - x0) / (TWIPS_POR_CM * self._painel.mapa().escala)) + 1
        for k in range(max(cm, -200), min(limite, 200) + 1):
            x = self._x_de_tw(k * TWIPS_POR_CM)
            if x < -2 or x > self.width() + 2:
                continue
            p.drawLine(QPointF(x, altura - 6), QPointF(x, altura - 1))
            if k > 0:
                p.drawText(QPointF(x + 2, altura - 7), str(k))
        esquerdo, primeira = self._recuos_mostrados()
        xe = self._x_de_tw(esquerdo)
        xp = self._x_de_tw(esquerdo + primeira)
        p.setPen(COR_MARCA)
        p.setBrush(COR_MARCA)
        p.drawPolygon(QPolygonF([QPointF(xp - 5, 0), QPointF(xp + 5, 0), QPointF(xp, 6)]))
        p.drawPolygon(QPolygonF([QPointF(xe - 5, altura), QPointF(xe + 5, altura),
                                 QPointF(xe, altura - 7)]))
        p.drawRect(QRectF(xe - 3, altura - 10, 6, 3))
        p.end()

    # ----- arrasto -----------------------------------------------------------
    def _marcador_sob(self, x: float, y: float) -> str | None:
        esquerdo, primeira = self._recuos_mostrados()
        xe = self._x_de_tw(esquerdo)
        xp = self._x_de_tw(esquerdo + primeira)
        meio = self.height() / 2
        if y <= meio and abs(x - xp) <= TOLERANCIA_PX:
            return "primeira"
        if y > meio and abs(x - xe) <= TOLERANCIA_PX:
            return "esquerdo"
        return None

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        marcador = self._marcador_sob(ev.position().x(), ev.position().y())
        if marcador is None:
            return
        self._arrasto = marcador
        self._valor = self._painel.recuos_do_paragrafo()
        ev.accept()

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._arrasto is None:
            return
        cfg = self._painel.configuracao_pagina()
        tw = round(self._tw_de_x(ev.position().x()) / PASSO_TW) * PASSO_TW
        esquerdo, primeira = self._painel.recuos_do_paragrafo()
        if self._arrasto == "esquerdo":
            # O marcador de baixo leva o recuo esquerdo; a primeira linha acompanha.
            novo_esq = min(max(0, tw), cfg.corpo_largura_tw())
            self._valor = (novo_esq, primeira)
        else:
            # O marcador de cima e' absoluto; no modelo o recuo da primeira linha e' relativo.
            relativo = tw - esquerdo
            self._valor = (esquerdo, relativo)
        self.update()
        ev.accept()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if self._arrasto is None:
            return
        esquerdo, primeira = self._valor
        self._arrasto = None
        self._painel.definir_recuos_do_paragrafo(esquerdo, primeira)
        ev.accept()
        self.update()
