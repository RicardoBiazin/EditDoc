"""Grade de escolha de tabela (o "quadriculado" do botao Tabela do Word).

O mouse sobre a grade marca linhas x colunas; o clique devolve o tamanho. Fica dentro
de um QMenu (QWidgetAction). O rotulo em cima diz o tamanho marcado, em pt-BR.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

LINHAS = 8
COLUNAS = 10
CELULA_PX = 18
_MARGEM = 6
_ROTULO_PX = 22


class SeletorDeGrade(QWidget):
    escolhido = Signal(int, int)  # linhas, colunas

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self._marcado: tuple[int, int] = (0, 0)

    def sizeHint(self) -> QSize:  # noqa: N802 - nome do Qt
        return QSize(2 * _MARGEM + COLUNAS * CELULA_PX,
                     2 * _MARGEM + _ROTULO_PX + LINHAS * CELULA_PX)

    def marcado(self) -> tuple[int, int]:
        return self._marcado

    def rotulo(self) -> str:
        linhas, colunas = self._marcado
        if not linhas:
            return "Inserir tabela"
        return f"Tabela {colunas} x {linhas}"

    def celula_em(self, p: QPointF) -> tuple[int, int] | None:
        """(linhas, colunas) marcadas por um ponto da grade, contando de 1; None fora dela."""
        x = p.x() - _MARGEM
        y = p.y() - _MARGEM - _ROTULO_PX
        if x < 0 or y < 0:
            return None
        coluna, linha = int(x // CELULA_PX), int(y // CELULA_PX)
        if coluna >= COLUNAS or linha >= LINHAS:
            return None
        return linha + 1, coluna + 1

    def centro_da_celula(self, linhas: int, colunas: int) -> QPointF:
        """Ponto no meio da celula (linhas, colunas), contando de 1. Para os testes."""
        return QPointF(_MARGEM + (colunas - 0.5) * CELULA_PX,
                       _MARGEM + _ROTULO_PX + (linhas - 0.5) * CELULA_PX)

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        self._marcado = self.celula_em(ev.position()) or (0, 0)
        self.update()

    def leaveEvent(self, ev) -> None:  # noqa: N802
        self._marcado = (0, 0)
        self.update()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        celula = self.celula_em(ev.position())
        if celula is not None and ev.button() == Qt.MouseButton.LeftButton:
            self._marcado = (0, 0)
            self.escolhido.emit(*celula)
        ev.accept()

    def paintEvent(self, ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setPen(self.palette().text().color())
        p.drawText(QRectF(_MARGEM, _MARGEM, COLUNAS * CELULA_PX, _ROTULO_PX),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.rotulo())
        linhas, colunas = self._marcado
        destaque = QColor(0xCC, 0xE4, 0xF7)
        borda = QColor(0x80, 0x86, 0x90)
        for r in range(LINHAS):
            for c in range(COLUNAS):
                caixa = QRectF(_MARGEM + c * CELULA_PX + 1, _MARGEM + _ROTULO_PX + r * CELULA_PX + 1,
                               CELULA_PX - 3, CELULA_PX - 3)
                p.fillRect(caixa, destaque if (r < linhas and c < colunas) else QColor(255, 255, 255))
                p.setPen(QPen(QColor(0, 120, 215) if (r < linhas and c < colunas) else borda, 1))
                p.drawRect(caixa)
        p.end()
