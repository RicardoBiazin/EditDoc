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

Cabecalho e rodape (M5): ficam em `faixas` (interface/cabecalhos.py), fora do corpo.
Duas paginas: `pagina_arquivo` e' a do arquivo (o que se grava e o que a faixa de
opcoes mostra); `pagina` e' a efetiva, com o corpo empurrado pelo cabecalho ou pelo
rodape que nao cabem na margem. Toda a geometria da tela usa a efetiva.

Campos no corpo: o contexto (`contexto_campos`) diz o total de paginas e a altura do
corpo; quando o total muda, os campos sao medidos de novo (`atualizar_campos`).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSizeF
from PySide6.QtGui import QFont, QImage, QTextCursor, QTextDocument

from editdoc.interface.cabecalhos import ConjuntoDeFaixas
from editdoc.modelo.pagina import Pagina, pagina_efetiva
from editdoc.ponte_qt import campos
from editdoc.ponte_qt import estilos as pq_estilos
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


def retangulo_cursor_em(doc: QTextDocument, pos: int) -> QRectF:
    """Caret de uma posicao, em coordenadas do documento `doc` (corpo, cabecalho ou rodape).

    Usa blockBoundingRect para a origem: QTextLayout.position() e' relativo dentro de
    celula de tabela (medido no spike, C3).
    """
    cur = QTextCursor(doc)
    cur.setPosition(min(max(pos, 0), doc.characterCount() - 1))
    bloco = cur.block()
    rel = cur.position() - bloco.position()
    lay = bloco.layout()
    linha = lay.lineForTextPosition(rel)
    if not linha.isValid():
        linha = lay.lineAt(lay.lineCount() - 1)
    if not linha.isValid():
        o = doc.documentLayout().blockBoundingRect(bloco).topLeft()
        return QRectF(o.x(), o.y(), 1.0, 1.0)
    x, _ = linha.cursorToX(rel)
    o = doc.documentLayout().blockBoundingRect(bloco).topLeft()
    return QRectF(o.x() + x, o.y() + linha.y(), 1.0, linha.height())


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
        self.pagina_arquivo = pagina
        self.pagina = pagina
        self.faixas = ConjuntoDeFaixas(padrao, pagina.corpo_largura_tw())
        self.faixas.doc_estilos = self.doc
        pq_estilos.definir_catalogo_base(self.doc, None)
        self.contexto_campos = campos.ContextoDeCampos()
        self._manipulador_campos = campos.registrar(self.doc, self.contexto_campos)
        self._chave_campos: tuple | None = None
        self._aplicar()
        # Ajustar fonte e margem marca o documento como alterado. Um documento novo nasce limpo.
        self.doc.setModified(False)

    def definir_fonte_padrao(self, familia: str, pontos: float) -> None:
        """Fonte do texto sem formatacao (o docDefaults do arquivo). Nao suja o documento."""
        fonte = QFont(familia)
        fonte.setPointSizeF(float(pontos))
        modificado = self.doc.isModified()
        self.doc.setDefaultFont(fonte)
        self.doc.setModified(modificado)
        self.faixas.definir_fonte(fonte)

    def _aplicar(self) -> None:
        self.doc.setPageSize(QSizeF(self.pagina.corpo_largura_tw(),
                                    self.pagina.corpo_altura_tw()))
        self.contexto_campos.hb = self.hb
        self.contexto_campos.pagina = self.pagina_arquivo
        self._chave_campos = None

    def definir_pagina(self, pagina: Pagina) -> None:
        """Troca papel ou margens: o documento e' refeito para o novo corpo."""
        self.pagina_arquivo = pagina
        self.faixas.definir_largura(pagina.corpo_largura_tw())
        self.pagina = self._efetiva()
        self._aplicar()

    def _efetiva(self) -> Pagina:
        cab, rod = self.faixas.alturas(self.pagina_arquivo)
        return pagina_efetiva(self.pagina_arquivo, cab, rod)

    def recalcular_margens(self) -> bool:
        """O cabecalho ou o rodape mudou de altura: o corpo desce ou sobe. True se mudou."""
        efetiva = self._efetiva()
        if efetiva == self.pagina:
            return False
        self.pagina = efetiva
        self._aplicar()
        return True

    def atualizar_campos(self) -> bool:
        """Total de paginas ou numeracao mudaram: mede de novo os campos do corpo.

        True se algum campo foi marcado para refazer (quem pinta limpa o cache).
        """
        ctx = self.contexto_campos
        total = self.numero_paginas()
        pagina = self.pagina_arquivo
        chave = (total, self.hb, pagina.formato_numero, pagina.numero_inicial)
        if chave == self._chave_campos:
            return False
        self._chave_campos = chave
        ctx.total, ctx.hb, ctx.pagina = total, self.hb, pagina
        posicoes = campos.posicoes_de_campos(self.doc)
        if not posicoes:
            return False
        campos.refazer_campos(self.doc, posicoes)
        return True

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
        return retangulo_cursor_em(self.doc, pos)

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
            self.faixas.limpar()
            self.doc.documentLayout().setPaintDevice(None)
            self._dispositivo = None

    def __del__(self) -> None:
        # Sem isto o Python pode soltar o dispositivo antes do documento, que ainda
        # aponta para ele (ver a nota no topo do modulo).
        try:
            self.fechar()
        except Exception:  # noqa: BLE001 - destruicao nao pode levantar
            pass
