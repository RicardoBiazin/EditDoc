"""Layout paginado: um QTextDocument cujo corpo tem o tamanho de uma pagina.

O QTextDocument quebra as linhas pela largura do corpo e empilha as paginas com
pageSize = (largura do corpo, altura do corpo) e documentMargin zero. A pagina n
ocupa, em coordenadas do documento, a faixa vertical [n*hb, (n+1)*hb).

O layout roda num dispositivo de 1440 dpi: uma unidade do Qt vira um twip, a
unidade do .docx. Qualquer outro dpi daria contagem de paginas diferente
(medido no Spike A, 3%).

O QTextEdit nao serve aqui: ele forca pageSize = (largura, -1) e apaga a
paginacao. Por isso o documento e' de um objeto proprio, e a visao e' outra.

O dispositivo fica guardado no objeto. Destrui-lo com um QPainter ativo derruba o
processo (medido no spike, C13): ele vive enquanto o layout viver.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSizeF
from PySide6.QtGui import QFont, QImage, QTextCursor, QTextDocument

from editdoc.modelo.pagina import Pagina
from editdoc.ponte_qt.imagens import DocumentoQt

DPI_LAYOUT = 1440


def criar_dispositivo_layout() -> QImage:
    """QImage 1x1 usada so' como dispositivo de layout, a 1440 dpi."""
    img = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
    dpm = round(DPI_LAYOUT / 0.0254)
    img.setDotsPerMeterX(dpm)
    img.setDotsPerMeterY(dpm)
    if img.logicalDpiX() != DPI_LAYOUT:
        raise RuntimeError(f"dispositivo de layout com {img.logicalDpiX()} dpi, "
                           f"esperado {DPI_LAYOUT}")
    return img


class LayoutPaginado:
    def __init__(self, pagina: Pagina, fonte: str, tamanho_pt: float) -> None:
        self._dispositivo: QImage | None = criar_dispositivo_layout()
        # DocumentoQt acha no registro a imagem colada de outra janela (ponte_qt/imagens.py).
        self.doc: QTextDocument = DocumentoQt()
        self.doc.setDocumentMargin(0)
        padrao = QFont(fonte)
        padrao.setPointSizeF(float(tamanho_pt))
        self.doc.setDefaultFont(padrao)
        self.doc.documentLayout().setPaintDevice(self._dispositivo)
        self.pagina = pagina
        self._aplicar()
        # Ajustar fonte e margem marca o documento como alterado. Um documento novo nasce limpo.
        self.doc.setModified(False)

    def _aplicar(self) -> None:
        self.doc.setPageSize(QSizeF(self.pagina.corpo_largura_tw(),
                                    self.pagina.corpo_altura_tw()))

    def definir_pagina(self, pagina: Pagina) -> None:
        """Troca papel ou margens: o documento e' refeito para o novo corpo."""
        self.pagina = pagina
        self._aplicar()

    @property
    def hb(self) -> float:
        """Altura de uma pagina de corpo, em unidades de layout (twips)."""
        return float(self.pagina.corpo_altura_tw())

    def numero_paginas(self) -> int:
        return max(1, self.doc.pageCount())

    def pagina_de_y(self, y: float) -> int:
        n = math.floor(y / self.hb)
        return min(max(n, 0), self.numero_paginas() - 1)

    def origem_bloco(self, bloco) -> QPointF:
        """Origem absoluta do bloco em coordenadas do documento.

        Usa blockBoundingRect: QTextLayout.position() e' relativo dentro de celula
        de tabela, e daria posicoes erradas (medido no spike, C3).
        """
        return QPointF(self.doc.documentLayout().blockBoundingRect(bloco).topLeft())

    def retangulo_cursor(self, pos: int) -> QRectF:
        """Caret de uma posicao, em coordenadas do documento."""
        cur = QTextCursor(self.doc)
        cur.setPosition(pos)
        bloco = cur.block()
        rel = pos - bloco.position()
        lay = bloco.layout()
        linha = lay.lineForTextPosition(rel)
        if not linha.isValid():
            linha = lay.lineAt(lay.lineCount() - 1)
        x, _ = linha.cursorToX(rel)
        o = self.origem_bloco(bloco)
        return QRectF(o.x() + x, o.y() + linha.y(), 1.0, linha.height())

    def retangulo_imagem(self, pos: int) -> QRectF | None:
        """Retangulo da imagem cujo caractere esta' em `pos`, em coordenadas do documento.

        A imagem fica na linha de base: o topo e' a base da linha menos a altura dela.
        O formato guarda o tamanho em px96; o layout e' em twips (x15).
        """
        cur = QTextCursor(self.doc)
        if pos < 0 or pos >= self.doc.characterCount() - 1:
            return None
        cur.setPosition(pos)
        cur.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
        fmt = cur.charFormat()
        if cur.selectedText() != chr(0xFFFC) or not fmt.isImageFormat():
            return None
        img = fmt.toImageFormat()
        bloco = self.doc.findBlock(pos)
        rel = pos - bloco.position()
        lay = bloco.layout()
        linha = lay.lineForTextPosition(rel)
        if not linha.isValid():
            return None
        x0, _ = linha.cursorToX(rel)
        x1, _ = linha.cursorToX(rel + 1)
        o = self.origem_bloco(bloco)
        altura = img.height() * 15.0
        largura = abs(x1 - x0) or img.width() * 15.0
        topo = o.y() + linha.y() + linha.ascent() - altura
        return QRectF(o.x() + min(x0, x1), topo, largura, altura)

    def pagina_do_cursor(self, pos: int) -> int:
        return self.pagina_de_y(self.retangulo_cursor(pos).center().y())

    def ajustar_para_pagina(self, pos: int, n: int) -> int:
        """Leva uma posicao vizinha ao texto mais proximo da pagina n.

        O hit-test do Qt (FuzzyHit) manda um clique no espaco em branco do fim da
        pagina n para a primeira linha da pagina n+1 (medido, C11). Aqui andamos
        pelo texto ate cair na pagina n.
        """
        cur = QTextCursor(self.doc)
        cur.setPosition(pos)
        for _ in range(400):
            pg = self.pagina_do_cursor(cur.position())
            if pg == n:
                return cur.position()
            if pg > n:
                cur.movePosition(QTextCursor.MoveOperation.StartOfLine)
                if cur.position() == 0:
                    return 0
                cur.movePosition(QTextCursor.MoveOperation.Left)
            else:
                cur.movePosition(QTextCursor.MoveOperation.EndOfLine)
                if not cur.movePosition(QTextCursor.MoveOperation.Right):
                    return cur.position()
        return cur.position()

    def fechar(self) -> None:
        """Solta o dispositivo antes de o documento morrer."""
        if self._dispositivo is not None:
            self.doc.documentLayout().setPaintDevice(None)
            self._dispositivo = None

    def __del__(self) -> None:
        # Sem isto o Python pode soltar o dispositivo antes do documento, que ainda
        # aponta para ele (ver a nota no topo do modulo).
        try:
            self.fechar()
        except Exception:  # noqa: BLE001 - destruicao nao pode levantar
            pass
