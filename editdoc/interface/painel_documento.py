"""Painel de edicao: a API do QTextEdit que os comandos usam, sobre a visao em paginas.

Os nomes ficam os do QTextEdit (textCursor, setTextCursor, document, undo, mergeCurrentCharFormat,
...) de proposito: formatacao, estado, busca, faixa e janela chamam esses nomes, e a
troca da visao provisoria pela visao em paginas (M3) nao reescreve nenhum deles.

Quem implementa aqui o caret, o teclado, o mouse, a selecao, o clipboard e o desfazer.
A pintura e' da VistaPaginas. Decisao e numeros em docs/SPIKES.md (Gate do M3): o
QTextEdit oculto, compartilhando o documento, troca o pageSize e apaga a paginacao.

Formato de digitacao: sem selecao, mergeCurrentCharFormat e setCurrentCharFormat mudam o
formato do PROXIMO caractere digitado, nao o da palavra sob o caret (medido com
QTextEdit antes de escrever isto).
"""

from __future__ import annotations

import re

from PySide6.QtCore import QMimeData, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QAction, QImage, QKeyEvent, QKeySequence, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextDocumentFragment, QTextFormat)
from PySide6.QtWidgets import QApplication, QMenu

from editdoc.edicao import imagens as ed_imagens
from editdoc.edicao import tabelas as ed_tabelas
from editdoc.interface.vista_paginas import VistaPaginas
from editdoc.interface.layout_paginado import LayoutPaginado
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.folhas import escala_do_zoom
from editdoc.modelo.pagina import Pagina
from editdoc.ponte_qt import imagens as pq_imagens
from editdoc.ponte_qt.para_qt import PROP_ESTRUTURAL

Mover = QTextCursor.MoveMode.MoveAnchor
Selecionar = QTextCursor.MoveMode.KeepAnchor
M = QTextCursor.MoveOperation
Key = Qt.Key
Ctrl = Qt.KeyboardModifier.ControlModifier
Alt = Qt.KeyboardModifier.AltModifier
Shift = Qt.KeyboardModifier.ShiftModifier
_QUEBRA = QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore
_SEM_QUEBRA = QTextFormat.PageBreakFlag.PageBreak_Auto
#: Propriedades de imagem que nao podem passar para o texto digitado depois dela.
_PROPS_IMAGEM = (QTextFormat.Property.ObjectType, QTextFormat.Property.ImageName,
                 QTextFormat.Property.ImageWidth, QTextFormat.Property.ImageHeight,
                 QTextFormat.Property.TextToolTip)
_IMG_HTML = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
#: Lado da alca de redimensionar imagem, em pixels de tela.
ALCA_PX = 8.0


def html_sem_imagens_de_fora(html: str) -> str:
    """Tira do HTML colado as imagens que nao vieram do EditDoc.

    Uma <img src="file:..."> ou "http:..." faria o Qt ler um arquivo local ou ficar
    com um quadro vazio. A imagem de fora entra pelo caminho da imagem (QImage), nao
    pelo HTML.
    """
    prefixo = f'src="{pq_imagens.ESQUEMA}:'
    return _IMG_HTML.sub(lambda m: m.group(0) if prefixo in m.group(0) else "", html)


class PainelDocumento(VistaPaginas):
    textChanged = Signal()
    cursorPositionChanged = Signal()
    currentCharFormatChanged = Signal(QTextCharFormat)
    undoAvailable = Signal(bool)
    redoAvailable = Signal(bool)
    copyAvailable = Signal(bool)
    paginaAlterada = Signal()
    #: Recado curto para a barra de status (imagem recusada ao colar, por exemplo).
    mensagem = Signal(str)

    def __init__(self, fonte: str, tamanho: float, parent=None) -> None:
        layout = LayoutPaginado(Pagina(), fonte, float(tamanho))
        super().__init__(layout, parent)
        self._acoes: list[QAction] = []
        self._acoes_contexto: list[QAction] = []
        self._cursor = QTextCursor(layout.doc)
        self._arrastando = False
        #: Arrasto de alca de imagem: (posicao, canto, retangulo inicial na tela) ou None.
        self._redim: tuple[int, str, QRectF] | None = None
        self._redim_atual: QRectF | None = None
        doc = layout.doc
        doc.contentsChanged.connect(self.textChanged)
        doc.undoAvailable.connect(self.undoAvailable)
        doc.redoAvailable.connect(self.redoAvailable)

    # ----- API do QTextEdit usada pelos comandos -------------------------
    def document(self) -> QTextDocument:
        return self.layout_pag.doc

    def textCursor(self) -> QTextCursor:
        return QTextCursor(self._cursor)

    def setTextCursor(self, cursor: QTextCursor) -> None:
        self._cursor = QTextCursor(cursor)
        self._depois_de_mover()

    def moveCursor(self, operacao, modo=Mover) -> None:
        self._cursor.movePosition(operacao, modo)
        self._depois_de_mover()

    def toPlainText(self) -> str:
        return self.layout_pag.doc.toPlainText()

    def setPlainText(self, texto: str) -> None:
        """Como o QTextEdit: o cursor vai para o inicio e o desfazer e' zerado."""
        self.layout_pag.doc.setPlainText(texto)
        self._cursor = QTextCursor(self.layout_pag.doc)
        self._depois_de_mover()

    def insertPlainText(self, texto: str) -> None:
        self._inserir(texto)

    def clear(self) -> None:
        self.layout_pag.doc.clear()
        self._cursor = QTextCursor(self.layout_pag.doc)
        self._depois_de_mover()

    def undo(self) -> None:
        if self.layout_pag.doc.isUndoAvailable():
            self.layout_pag.doc.undo(self._cursor)
            self._depois_de_mover()

    def redo(self) -> None:
        if self.layout_pag.doc.isRedoAvailable():
            self.layout_pag.doc.redo(self._cursor)
            self._depois_de_mover()

    def selectAll(self) -> None:
        self._cursor.select(QTextCursor.SelectionType.Document)
        self._depois_de_mover()

    def copy(self) -> None:
        if not self._cursor.hasSelection():
            return
        frag = QTextDocumentFragment(self._cursor)
        md = QMimeData()
        md.setHtml(frag.toHtml())
        md.setText(frag.toPlainText().replace(chr(0xFFFC), ""))
        pos = ed_imagens.imagem_selecionada(self)
        if pos is not None:
            # So' a imagem selecionada: outro programa recebe a imagem, nao o HTML.
            fmt = ed_imagens.formato_em(self.document(), pos)
            registro = pq_imagens.dados_de(fmt.name()) if fmt is not None else None
            if registro is not None:
                # Resolucao cheia para o outro programa; a previa so' se nao puder decodificar.
                dims = mod_imagem.dimensoes(registro[0])
                inteira = QImage.fromData(registro[0]) if dims and mod_imagem.decodificavel(*dims) \
                    else QImage()
                md.setImageData(inteira if not inteira.isNull() else pq_imagens.previa(registro[0]))
        QApplication.clipboard().setMimeData(md)

    def cut(self) -> None:
        self.copy()
        if self._cursor.hasSelection():
            self._cursor.removeSelectedText()
            self._depois_de_mover()

    def paste(self) -> None:
        md = QApplication.clipboard().mimeData()
        if md is None:
            return
        if md.hasHtml():
            html = html_sem_imagens_de_fora(md.html())
            frag = QTextDocumentFragment.fromHtml(html)
            if not frag.toPlainText().strip() and md.hasImage():
                self._colar_imagem(md)  # navegador: <img> de fora mais a propria imagem
                return
        elif md.hasImage():
            self._colar_imagem(md)
            return
        else:
            frag = QTextDocumentFragment.fromPlainText(md.text())
        self._cursor.beginEditBlock()
        if self._cursor.hasSelection():
            self._cursor.removeSelectedText()
        self._limpar_estrutural()
        self._cursor.insertFragment(frag)
        self._cursor.endEditBlock()
        # A tabela colada so' aparece em childFrames() depois do endEditBlock (medido). O
        # ajuste entra no mesmo passo de desfazer pelo joinPreviousEditBlock.
        self._cursor.joinPreviousEditBlock()
        ed_tabelas.ajustar_tabelas_coladas(self)
        self._cursor.endEditBlock()
        self._depois_de_mover()

    def _colar_imagem(self, md: QMimeData) -> None:
        try:
            ed_imagens.inserir_qimage(self, md.imageData())
        except ed_imagens.ImagemRecusada as erro:
            self.mensagem.emit(str(erro))

    def mergeCurrentCharFormat(self, formato: QTextCharFormat) -> None:
        self._cursor.mergeCharFormat(formato)
        self._depois_de_formato()

    def currentCharFormat(self) -> QTextCharFormat:
        return QTextCharFormat(self._cursor.charFormat())

    def setCurrentCharFormat(self, formato: QTextCharFormat) -> None:
        self._cursor.setCharFormat(formato)
        self._depois_de_formato()

    def registrar_atalhos(self, acoes: list[QAction]) -> None:
        self._acoes = list(acoes)

    def registrar_menu_contexto(self, acoes: list[QAction]) -> None:
        """Acoes extras do menu de contexto (tabela, imagem). So' as habilitadas aparecem."""
        self._acoes_contexto = list(acoes)

    def imagem_selecionada(self) -> int | None:
        """Posicao da imagem selecionada (selecao de exatamente uma imagem), ou None."""
        return ed_imagens.imagem_selecionada(self)

    # ----- pagina ---------------------------------------------------------
    def configuracao_pagina(self) -> Pagina:
        return self.layout_pag.pagina

    def definir_configuracao_pagina(self, pagina: Pagina) -> None:
        """Papel, orientacao ou margens. Refaz a paginacao; nao mexe no texto."""
        self.layout_pag.definir_pagina(pagina)
        self._limpar_cache()
        self._altura_doc_anterior = None
        self._atualizar_geometria()
        self.garantir_visivel(self.layout_pag.retangulo_cursor(self._cursor.position()))
        self.paginaAlterada.emit()
        self.viewport().update()

    def total_de_paginas(self) -> int:
        return self.layout_pag.numero_paginas()

    def pagina_atual(self) -> int:
        """Pagina do caret, a partir de 0."""
        return self.layout_pag.pagina_do_cursor(self._cursor.position())

    def recuos_do_paragrafo(self) -> tuple[int, int]:
        """(recuo esquerdo, recuo da primeira linha) do paragrafo do caret, em twips."""
        bf = self._cursor.block().blockFormat()
        return round(bf.leftMargin() * 15), round(bf.textIndent() * 15)

    def definir_recuos_do_paragrafo(self, esquerdo_tw: int, primeira_tw: int) -> None:
        """Um passo de desfazer: recuos do paragrafo do caret."""
        bf = QTextBlockFormat()
        bf.setLeftMargin(max(0.0, esquerdo_tw / 15.0))
        bf.setTextIndent(primeira_tw / 15.0)
        self._cursor.beginEditBlock()
        self._cursor.mergeBlockFormat(bf)
        self._cursor.endEditBlock()
        self._depois_de_formato()

    def inserir_quebra_de_pagina(self) -> None:
        """Ctrl+Enter: o texto depois do caret comeca no topo da proxima pagina.

        Dentro de tabela vira Enter comum: o EditDoc nao quebra pagina dentro de celula.
        """
        self._quebrar(quebra=self._cursor.currentTable() is None)

    # ----- estado e sinais internos ----------------------------------------
    def _depois_de_mover(self) -> None:
        self.mostrar_caret_agora()
        self.garantir_visivel(self.layout_pag.retangulo_cursor(self._cursor.position()))
        self.copyAvailable.emit(self._cursor.hasSelection())
        self.cursorPositionChanged.emit()
        self.currentCharFormatChanged.emit(self.currentCharFormat())
        self.viewport().update()

    def _depois_de_formato(self) -> None:
        self.currentCharFormatChanged.emit(self.currentCharFormat())
        self.viewport().update()

    def _posicao_caret(self) -> int | None:
        return self._cursor.position()

    def _selecao_atual(self) -> QTextCursor | None:
        return self._cursor

    def _posicao_imagem_selecionada(self) -> int | None:
        return self.imagem_selecionada()

    def _retangulo_redimensionando(self) -> QRectF | None:
        return self._redim_atual

    def _estrutural(self) -> bool:
        return bool(self._cursor.blockFormat().property(PROP_ESTRUTURAL))

    def _limpar_estrutural(self) -> None:
        """O bloco estrutural (o que o Qt exige antes da tabela) que recebe conteudo vira
        paragrafo comum: sem isto, apagado de novo, ele sumiria do arquivo."""
        if self._estrutural():
            bf = QTextBlockFormat(self._cursor.blockFormat())
            bf.clearProperty(PROP_ESTRUTURAL)
            self._cursor.setBlockFormat(bf)

    def _inserir(self, texto: str) -> None:
        estrutural = self._estrutural()
        if estrutural:
            self._cursor.beginEditBlock()
        if self._cursor.hasSelection():
            self._cursor.removeSelectedText()
        self._limpar_estrutural()
        formato = self._cursor.charFormat()
        if formato.isImageFormat():
            # Digitar logo depois de uma imagem: o texto nao herda o formato de imagem.
            limpo = QTextCharFormat(formato)
            for propriedade in _PROPS_IMAGEM:
                limpo.clearProperty(propriedade)
            self._cursor.insertText(texto, limpo)
        else:
            self._cursor.insertText(texto)
        if estrutural:
            self._cursor.endEditBlock()
        self._depois_de_mover()

    def _quebrar(self, quebra: bool) -> None:
        self._cursor.beginEditBlock()
        if self._cursor.hasSelection():
            self._cursor.removeSelectedText()
        self._limpar_estrutural()
        bf = QTextBlockFormat(self._cursor.blockFormat())
        bf.setPageBreakPolicy(_QUEBRA if quebra else _SEM_QUEBRA)
        self._cursor.insertBlock(bf)
        self._cursor.endEditBlock()
        self._depois_de_mover()

    def _tab_na_tabela(self, para_tras: bool) -> None:
        """Tab vai para a proxima celula e seleciona o conteudo dela, como no Word.
        Na ultima celula, Tab cria uma linha no fim. Shift+Tab volta."""
        tabela = self._cursor.currentTable()
        celula = tabela.cellAt(self._cursor)
        alvo = ed_tabelas.proxima_celula(tabela, celula, para_tras)
        if alvo is None:
            if not para_tras:
                ed_tabelas.acrescentar_linha_no_fim(self)
            return
        inicio = alvo.firstCursorPosition().position()
        fim = alvo.lastCursorPosition().position()
        self._cursor.setPosition(inicio)
        if fim > inicio:
            self._cursor.setPosition(fim, Selecionar)
        self._depois_de_mover()

    def _apagar(self, anterior: bool, palavra: bool = False) -> None:
        if self._cursor.hasSelection():
            self._cursor.removeSelectedText()
        elif palavra:
            self._cursor.movePosition(M.WordLeft if anterior else M.WordRight, Selecionar)
            self._cursor.removeSelectedText()
        elif anterior:
            self._cursor.deletePreviousChar()
        else:
            self._cursor.deleteChar()
        self._depois_de_mover()

    def _pagina_do_teclado(self, anterior: bool, modo) -> None:
        """PageUp/PageDown: anda uma altura de tela, mantendo a coluna do caret."""
        r = self.layout_pag.retangulo_cursor(self._cursor.position())
        altura = self.viewport().height() / escala_do_zoom(self._zoom)
        alvo = QPointF(r.x(), r.y() + (-altura if anterior else altura))
        pos = self.layout_pag.doc.documentLayout().hitTest(alvo, Qt.FuzzyHit)
        self._cursor.setPosition(pos, modo)
        self._depois_de_mover()

    # ----- teclado ---------------------------------------------------------
    def keyPressEvent(self, ev: QKeyEvent) -> None:  # noqa: N802 - nome do Qt
        sequencia = QKeySequence(ev.keyCombination())
        for acao in self._acoes:
            if acao.isEnabled() and sequencia in acao.shortcuts():
                acao.trigger()
                ev.accept()
                return
        if self._tecla(ev):
            ev.accept()
            return
        super().keyPressEvent(ev)

    def _tecla(self, ev: QKeyEvent) -> bool:
        """Teclas de edicao e navegacao. True se o evento foi tratado."""
        k = ev.key()
        mod = ev.modifiers()
        ctrl = bool(mod & Ctrl)
        alt = bool(mod & Alt)
        shift = bool(mod & Shift)
        modo = Selecionar if shift else Mover

        if ctrl and not alt:
            if k in (Key.Key_Return, Key.Key_Enter):
                self.inserir_quebra_de_pagina()
            elif k == Key.Key_Backspace:
                self._apagar(anterior=True, palavra=True)
            elif k == Key.Key_Delete:
                self._apagar(anterior=False, palavra=True)
            elif k == Key.Key_Home:
                self._cursor.movePosition(M.Start, modo)
                self._depois_de_mover()
            elif k == Key.Key_End:
                self._cursor.movePosition(M.End, modo)
                self._depois_de_mover()
            elif k == Key.Key_Left:
                self._cursor.movePosition(M.WordLeft, modo)
                self._depois_de_mover()
            elif k == Key.Key_Right:
                self._cursor.movePosition(M.WordRight, modo)
                self._depois_de_mover()
            elif k == Key.Key_A:
                self.selectAll()
            elif k == Key.Key_Tab:
                self._inserir("\t")  # Ctrl+Tab: tabulacao dentro da celula, como no Word
            else:
                return False
            return True

        if k in (Key.Key_Return, Key.Key_Enter):
            self._quebrar(quebra=False)
        elif k == Key.Key_Backspace:
            self._apagar(anterior=True)
        elif k == Key.Key_Delete:
            self._apagar(anterior=False)
        elif k in (Key.Key_Tab, Key.Key_Backtab) and self._cursor.currentTable() is not None:
            self._tab_na_tabela(para_tras=(k == Key.Key_Backtab or shift))
        elif k == Key.Key_Tab:
            self._inserir("\t")
        elif k == Key.Key_Left:
            self._cursor.movePosition(M.Left, modo)
            self._depois_de_mover()
        elif k == Key.Key_Right:
            self._cursor.movePosition(M.Right, modo)
            self._depois_de_mover()
        elif k == Key.Key_Up:
            self._cursor.movePosition(M.Up, modo)
            self._depois_de_mover()
        elif k == Key.Key_Down:
            self._cursor.movePosition(M.Down, modo)
            self._depois_de_mover()
        elif k == Key.Key_Home:
            self._cursor.movePosition(M.StartOfLine, modo)
            self._depois_de_mover()
        elif k == Key.Key_End:
            self._cursor.movePosition(M.EndOfLine, modo)
            self._depois_de_mover()
        elif k in (Key.Key_PageUp, Key.Key_PageDown):
            self._pagina_do_teclado(anterior=(k == Key.Key_PageUp), modo=modo)
        else:
            texto = ev.text()
            if not texto or not texto.isprintable() or ctrl:
                return False
            self._inserir(texto)
        return True

    def inputMethodEvent(self, ev) -> None:  # noqa: N802 - nome do Qt
        # Sem pre-edicao (IME de CJK nao e' alvo do M3): so' o texto confirmado entra.
        texto = ev.commitString()
        if texto:
            self._inserir(texto)
        ev.accept()

    # ----- mouse -----------------------------------------------------------
    def posicao_em(self, p: QPointF) -> int:
        """Posicao do texto sob um ponto do viewport. Fica na pagina clicada."""
        xd, yd = self._mapa().tela_para_doc(p.x(), p.y(), self._paginas())
        n = self.layout_pag.pagina_de_y(yd)
        pos = self.layout_pag.doc.documentLayout().hitTest(QPointF(xd, yd), Qt.FuzzyHit)
        if self.layout_pag.pagina_do_cursor(pos) != n:
            pos = self.layout_pag.ajustar_para_pagina(pos, n)
        return pos

    def imagem_em(self, p: QPointF) -> int | None:
        """Posicao da imagem sob o ponto do viewport, ou None."""
        pos = self.posicao_em(p)
        for k in (pos, pos - 1):
            r = self.retangulo_imagem_na_tela(k)
            if r is not None and r.contains(p):
                return k
        return None

    def alca_em(self, p: QPointF) -> tuple[int, str, QRectF] | None:
        """(imagem, canto, retangulo) se o ponto esta' numa alca da imagem selecionada."""
        pos = self.imagem_selecionada()
        if pos is None:
            return None
        r = self.retangulo_imagem_na_tela(pos)
        if r is None:
            return None
        for canto, ponto in (("sup_esq", r.topLeft()), ("sup_dir", r.topRight()),
                             ("inf_esq", r.bottomLeft()), ("inf_dir", r.bottomRight())):
            if abs(p.x() - ponto.x()) <= ALCA_PX and abs(p.y() - ponto.y()) <= ALCA_PX:
                return pos, canto, r
        return None

    def _retangulo_do_arrasto(self, p: QPointF) -> QRectF:
        """Novo retangulo da imagem durante o arrasto, com a proporcao travada.

        A imagem fica na linha de base: o canto de baixo a esquerda nao se move.
        """
        _pos, canto, r = self._redim
        if canto.endswith("dir"):
            largura = p.x() - r.left()
        else:
            largura = r.right() - p.x()
        largura = max(largura, 4.0)
        altura = largura * r.height() / max(r.width(), 1e-6)
        return QRectF(r.left(), r.bottom() - altura, largura, altura)

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        self.setFocus()
        if ev.button() == Qt.MouseButton.LeftButton:
            alca = self.alca_em(ev.position())
            if alca is not None:
                self._redim = alca
                self._redim_atual = QRectF(alca[2])
                self._arrastando = False
                ev.accept()
                return
            imagem = None if ev.modifiers() & Shift else self.imagem_em(ev.position())
            if imagem is not None:
                # Clique na imagem seleciona a imagem, como no Word.
                self._cursor.setPosition(imagem)
                self._cursor.setPosition(imagem + 1, Selecionar)
                self._arrastando = False
                self._depois_de_mover()
                ev.accept()
                return
            pos = self.posicao_em(ev.position())
            estender = bool(ev.modifiers() & Shift)
            self._cursor.setPosition(pos, Selecionar if estender else Mover)
            self._arrastando = True
            self._depois_de_mover()
        ev.accept()

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self._cursor.setPosition(self.posicao_em(ev.position()))
            self._cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            self._arrastando = False
            self._depois_de_mover()
        ev.accept()

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._redim is not None:
            self._redim_atual = self._retangulo_do_arrasto(ev.position())
            self.viewport().update()
        elif self._arrastando:
            self._cursor.setPosition(self.posicao_em(ev.position()), Selecionar)
            self._depois_de_mover()
        ev.accept()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if self._redim is not None:
            pos = self._redim[0]
            novo = self._retangulo_do_arrasto(ev.position())
            self._redim = self._redim_atual = None
            # Pixels de tela -> px96: a tela mostra m.escala pixels por twip, e 1 px96 = 15 twips.
            por_px96 = self._mapa().escala * 15.0
            ed_imagens.redimensionar(self, pos, novo.width() / por_px96, novo.height() / por_px96)
            self.viewport().update()
        self._arrastando = False
        ev.accept()

    def contextMenuEvent(self, ev) -> None:  # noqa: N802
        menu = QMenu(self)
        doc = self.layout_pag.doc
        menu.addAction("Desfazer", self.undo).setEnabled(doc.isUndoAvailable())
        menu.addAction("Refazer", self.redo).setEnabled(doc.isRedoAvailable())
        menu.addSeparator()
        menu.addAction("Recortar", self.cut).setEnabled(self._cursor.hasSelection())
        menu.addAction("Copiar", self.copy).setEnabled(self._cursor.hasSelection())
        menu.addAction("Colar", self.paste).setEnabled(QApplication.clipboard().mimeData() is not None)
        menu.addSeparator()
        menu.addAction("Selecionar tudo", self.selectAll)
        extras = [a for a in self._acoes_contexto if a.isEnabled()]
        if extras:
            menu.addSeparator()
            for acao in extras:
                menu.addAction(acao)
        menu.exec(ev.globalPos())

    # ----- foco ------------------------------------------------------------
    def focusInEvent(self, ev) -> None:  # noqa: N802
        super().focusInEvent(ev)
        self.definir_piscar(True)

    def focusOutEvent(self, ev) -> None:  # noqa: N802
        super().focusOutEvent(ev)
        self.definir_piscar(False)
