"""Spike A: layout paginado sobre um unico QTextDocument.

Unidade de layout = twip (1/1440 pol). O device de layout e uma QImage 1x1 com
1440 dpi, entao fontes e quebras de linha saem na mesma escala qualquer que seja
a tela ou a impressora de destino. Em coordenadas do documento, a pagina n ocupa
o intervalo Y [n*HB, (n+1)*HB), onde HB = altura do corpo (pageSize).
"""
import math
import os
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QFont, QFontDatabase, QImage, QTextCursor, QTextDocument

DPI_LAYOUT = 1440
FONTES_SISTEMA = ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf", "calibri.ttf", "calibrib.ttf")
_fontes_carregadas = False


def garantir_fontes() -> None:
    """Carrega as fontes do Windows se o banco do Qt estiver vazio.

    Achado: com QT_QPA_PLATFORM=offscreen, QFontDatabase.families() vem VAZIO
    neste PC. Sem fonte, cada caractere vira glifo de substituicao com avanco
    de 1 em (caixas na tela). Carregar os .ttf com addApplicationFont resolve.
    """
    global _fontes_carregadas
    if _fontes_carregadas:
        return
    _fontes_carregadas = True
    if QFontDatabase.families():
        return
    pasta = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    for arq in FONTES_SISTEMA:
        caminho = os.path.join(pasta, arq)
        if os.path.exists(caminho):
            QFontDatabase.addApplicationFont(caminho)


TWIPS_POR_PX96 = 15      # 1440 / 96: unidade de margens, recuos, imagens e padding
TWIPS_POR_PT = 20        # 1440 / 72


@dataclass(frozen=True)
class ConfigPagina:
    """Pagina em twips. Padrao: A4 com margem de 2,5 cm."""
    largura: int = 11906
    altura: int = 16838
    margem_esq: int = 1417
    margem_dir: int = 1417
    margem_sup: int = 1417
    margem_inf: int = 1417

    @property
    def larg_corpo(self) -> int:
        return self.largura - self.margem_esq - self.margem_dir

    @property
    def alt_corpo(self) -> int:
        return self.altura - self.margem_sup - self.margem_inf


def criar_dispositivo_layout() -> QImage:
    """QImage 1x1 usada so como device de layout, a 1440 dpi."""
    img = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
    dpm = round(DPI_LAYOUT / 0.0254)
    img.setDotsPerMeterX(dpm)
    img.setDotsPerMeterY(dpm)
    if img.logicalDpiX() != DPI_LAYOUT:
        raise RuntimeError(f"device de layout com {img.logicalDpiX()} dpi, esperado {DPI_LAYOUT}")
    return img


class LayoutPaginado:
    """Dono do QTextDocument de corpo e das consultas de pagina.

    O device de layout fica guardado no proprio objeto: se a QImage for coletada
    antes do documento, o layout seguinte le memoria liberada (ver C13).
    """

    def __init__(self, config: ConfigPagina | None = None, fonte: str = "Arial", tamanho_pt: float = 11):
        garantir_fontes()
        self.config = config or ConfigPagina()
        self._dispositivo = criar_dispositivo_layout()
        self.doc = QTextDocument()
        self.doc.setDocumentMargin(0)
        fonte_padrao = QFont(fonte)
        fonte_padrao.setPointSizeF(tamanho_pt)
        self.doc.setDefaultFont(fonte_padrao)
        self.doc.documentLayout().setPaintDevice(self._dispositivo)
        self.doc.setPageSize(QSizeF(self.config.larg_corpo, self.config.alt_corpo))

    # ----- paginacao -------------------------------------------------------
    @property
    def hb(self) -> float:
        """Altura de uma pagina de corpo em unidades de layout."""
        return float(self.config.alt_corpo)

    def numero_paginas(self) -> int:
        return max(1, self.doc.pageCount())

    def retangulo_corpo(self, n: int) -> QRectF:
        return QRectF(0.0, n * self.hb, float(self.config.larg_corpo), self.hb)

    def pagina_de_y(self, y: float) -> int:
        n = int(math.floor(y / self.hb))
        return min(max(n, 0), self.numero_paginas() - 1)

    # ----- geometria de linhas e cursor -----------------------------------
    def origem_bloco(self, bloco) -> QPointF:
        """Origem absoluta do bloco em coordenadas do documento.

        Usa blockBoundingRect().topLeft(). QTextLayout.position() NAO serve:
        em blocos de celula de tabela ela e relativa ao frame (achado em C3:
        498 de 1896 posicoes caiam fora). Somar as duas dobra o deslocamento (smoke).
        """
        return QPointF(self.doc.documentLayout().blockBoundingRect(bloco).topLeft())

    def retangulo_linha(self, bloco, linha) -> QRectF:
        o = self.origem_bloco(bloco)
        return QRectF(o.x() + linha.x(), o.y() + linha.y(), linha.naturalTextWidth(), linha.height())

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

    def pagina_do_cursor(self, pos: int) -> int:
        r = self.retangulo_cursor(pos)
        return self.pagina_de_y(r.center().y())

    def ajustar_para_pagina(self, pos: int, n: int) -> int:
        """Leva uma posicao vizinha ao texto mais proximo da pagina n.

        Achado (C11): o hit-test do Qt (FuzzyHit) manda um clique no espaco em
        branco do fim da pagina n para a primeira linha da pagina n+1, porque a
        linha seguinte esta mais perto. Aqui andamos pelo texto ate cair na pagina n.
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

    def fechar(self):
        """Solta o device antes de destruir o documento (ver C13)."""
        self.doc.documentLayout().setPaintDevice(None)
        self._dispositivo = None
