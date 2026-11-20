"""Regua horizontal: margens e recuos do paragrafo do caret.

A area do corpo aparece branca e as margens cinza. A escala e' em centimetros (ou em
polegadas, pela preferencia `unidade_regua`, M8), a partir da margem esquerda. Dois marcadores: o triangulo de cima e' o recuo da primeira
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
#: Twips por unidade da escala.
TWIPS_DA_UNIDADE = {"cm": TWIPS_POR_CM, "pol": 1440.0}


class Regua(QWidget):
    def __init__(self, painel, parent=None) -> None:
        super().__init__(parent)
        self._painel = painel
        self._arrasto: str | None = None
        self._valor = (0, 0)  # (recuo esquerdo, recuo da primeira linha), em twips
        self._unidade = "cm"
        self.setFixedHeight(ALTURA_PX)
        self.setToolTip("Régua: arraste os marcadores para mudar o recuo do parágrafo")
        self.setAccessibleName("Régua")
        self._descrever()
        painel.cursorPositionChanged.connect(self.update)
        painel.paginaAlterada.connect(self.update)
        painel.zoomAlterado.connect(self.update)
        painel.textChanged.connect(self.update)
        painel.horizontalScrollBar().valueChanged.connect(self.update)

    # ----- unidade (M8) -------------------------------------------------------
    def unidade(self) -> str:
        return self._unidade

    def definir_unidade(self, unidade: str) -> None:
        """'cm' ou 'pol'. Outra coisa fica em cm."""
        self._unidade = unidade if unidade in TWIPS_DA_UNIDADE else "cm"
        self._descrever()
        self.update()

    def _descrever(self) -> None:
        nome = "centímetros" if self._unidade == "cm" else "polegadas"
        self.setAccessibleDescription(
            f"Margens e recuos do parágrafo, em {nome}. Os recuos também mudam pela aba "
            "Layout, grupo Parágrafo, ou por Ctrl+M e Ctrl+Shift+M.")

    # ----- conversao ---------------------------------------------------------
    def _colunas(self):
        """(coluna do cursor, quantas, deslocamento da coluna, largura, passo) quando o cursor esta'
        numa secao de colunas (0.1.35); None sem colunas."""
        painel = self._painel
        lay = painel.layout_pag
        if not lay.mapa.tem_colunas() or not painel._no_corpo():
            return None
        pos = painel.textCursor().position()
        # A pintura pergunta uma vez por marca da escala: em cache por posicao e revisao.
        chave = (pos, lay.doc.revision(), lay.secoes.geracao, lay.doc.pageCount(), lay.mapa.grupos)
        guardado = getattr(self, "_col_cache", None)
        if guardado is not None and guardado[0] == chave:
            return guardado[1]
        p = lay.pagina_qt_do_cursor(pos)
        g = lay.mapa.grupo_da_pagina(p)
        valor = None if g is None else (lay.mapa.coluna_da_pagina(p), g.colunas,
                                        lay.mapa.deslocamento(p), g.largura, g.passo)
        self._col_cache = (chave, valor)
        return valor

    def _x_da_margem(self) -> float:
        """X, na regua, da margem esquerda da folha."""
        m = self._painel.mapa()
        margem = self._painel.configuracao_pagina().margem_esq_tw * m.escala
        if self._painel.layout_pag.secoes.multiplas():
            # Secoes (0.1.12): a folha do cursor (papeis diferentes ficam em x diferentes).
            x, _y, _w, _h = m.folha_na_tela(self._painel.pagina_atual())
            return x + margem
        return m.esquerda_folha - m.origem_x + margem

    def _x_do_corpo(self) -> float:
        """X, na regua, do inicio do texto onde esta' o cursor: a margem esquerda, ou a esquerda da
        coluna do cursor (0.1.35, os recuos contam da coluna)."""
        x = self._x_da_margem()
        col = self._colunas()
        if col is not None:
            x += col[2] * self._painel.mapa().escala
        return x

    def _largura_do_corpo(self) -> float:
        """Largura do texto onde esta' o cursor, em twips: o corpo, ou a coluna do cursor."""
        col = self._colunas()
        if col is not None:
            return col[3]
        return self._painel.configuracao_pagina().corpo_largura_tw()

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
        x0 = self._x_do_corpo()
        x1 = self._x_de_tw(self._largura_do_corpo())
        col = self._colunas()
        if col is None:
            p.fillRect(QRectF(x0, 0, x1 - x0, self.height()), COR_CORPO)
        else:
            # Colunas (0.1.35): cada coluna e' branca, o vao entre elas fica cinza como a margem.
            e = self._painel.mapa().escala
            base = self._x_da_margem()
            for i in range(col[1]):
                p.fillRect(QRectF(base + i * col[4] * e, 0, col[3] * e, self.height()), COR_CORPO)

        fonte = QFont(p.font())
        fonte.setPointSizeF(7.0)
        p.setFont(fonte)
        p.setPen(COR_MARCA)
        altura = self.height()
        passo = TWIPS_DA_UNIDADE[self._unidade]
        cm = -int(x0 // (passo * self._painel.mapa().escala)) - 1
        limite = int((self.width() - x0) / (passo * self._painel.mapa().escala)) + 1
        for k in range(max(cm, -200), min(limite, 200) + 1):
            x = self._x_de_tw(k * passo)
            if x < -2 or x > self.width() + 2:
                continue
            p.drawLine(QPointF(x, altura - 6), QPointF(x, altura - 1))
            meio = self._x_de_tw((k + 0.5) * passo)
            p.drawLine(QPointF(meio, altura - 3), QPointF(meio, altura - 1))
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
        tw = round(self._tw_de_x(ev.position().x()) / PASSO_TW) * PASSO_TW
        esquerdo, primeira = self._painel.recuos_do_paragrafo()
        if self._arrasto == "esquerdo":
            # O marcador de baixo leva o recuo esquerdo; a primeira linha acompanha.
            novo_esq = min(max(0, tw), self._largura_do_corpo())
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
