"""Spike A: cabecalho e rodape em documentos separados do corpo.

O rodape tem o modelo "Pagina {n} de {total}". Para cada pagina o texto e
substituido no proprio documento do rodape e pintado no lugar da margem
inferior. O documento do cabecalho e estatico.
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (QAbstractTextDocumentLayout, QColor, QFont, QPalette,
                           QTextDocument, QTextOption)

from layout_paginado import criar_dispositivo_layout


class CabecalhoRodape:
    def __init__(self, layout, texto_cabecalho: str = "EditDoc - spike de paginacao",
                 modelo_rodape: str = "Página {n} de {total}"):
        self.layout = layout
        self.modelo_rodape = modelo_rodape
        # Os devices ficam ao lado dos documentos (mesmo motivo de LayoutPaginado).
        self._dispositivo = criar_dispositivo_layout()
        self.doc_cabecalho = self._novo_documento()
        self.doc_cabecalho.setPlainText(texto_cabecalho)
        self.doc_rodape = self._novo_documento()

    def _novo_documento(self) -> QTextDocument:
        d = QTextDocument()
        d.setDocumentMargin(0)
        fonte = QFont("Arial")
        fonte.setPointSizeF(9)
        d.setDefaultFont(fonte)
        d.setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignCenter))
        d.documentLayout().setPaintDevice(self._dispositivo)
        d.setTextWidth(self.layout.config.larg_corpo)
        return d

    def texto_rodape(self, n: int, total: int) -> str:
        return self.modelo_rodape.format(n=n, total=total)

    def desenhar(self, painter, n: int, total: int) -> None:
        """Pinta cabecalho e rodape da pagina n (0-based) de `total`.

        O painter ja vem com a transformacao da folha (coordenadas de twip).
        """
        cfg = self.layout.config
        larg = float(cfg.larg_corpo)
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Text, QColor(0x55, 0x55, 0x55))

        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette = pal
        ctx.cursorPosition = -1

        # cabecalho: faixa entre a borda superior e o corpo
        painter.save()
        painter.translate(cfg.margem_esq, cfg.margem_sup * 0.35)
        painter.setClipRect(QRectF(0, 0, larg, cfg.margem_sup * 0.4))
        ctx.clip = QRectF(0, 0, larg, cfg.margem_sup * 0.4)
        self.doc_cabecalho.documentLayout().draw(painter, ctx)
        painter.restore()

        # rodape: texto com o numero da pagina
        self.doc_rodape.setPlainText(self.texto_rodape(n + 1, total))
        painter.save()
        y0 = cfg.altura - cfg.margem_inf * 0.6
        altura_rod = cfg.margem_inf * 0.4
        painter.translate(cfg.margem_esq, y0)
        painter.setClipRect(QRectF(0, 0, larg, altura_rod))
        ctx.clip = QRectF(0, 0, larg, altura_rod)
        self.doc_rodape.documentLayout().draw(painter, ctx)
        painter.restore()

    def fechar(self):
        for d in (self.doc_cabecalho, self.doc_rodape):
            d.documentLayout().setPaintDevice(None)
        self._dispositivo = None
