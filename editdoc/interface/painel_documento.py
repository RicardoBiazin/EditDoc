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

from PySide6.QtCore import QMimeData, QPointF, Qt, Signal
from PySide6.QtGui import (QAction, QKeyEvent, QKeySequence, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextDocumentFragment, QTextFormat)
from PySide6.QtWidgets import QApplication, QMenu

from editdoc.interface.vista_paginas import VistaPaginas
from editdoc.interface.layout_paginado import LayoutPaginado
from editdoc.modelo.folhas import escala_do_zoom
from editdoc.modelo.pagina import Pagina

Mover = QTextCursor.MoveMode.MoveAnchor
Selecionar = QTextCursor.MoveMode.KeepAnchor
M = QTextCursor.MoveOperation
Key = Qt.Key
Ctrl = Qt.KeyboardModifier.ControlModifier
Alt = Qt.KeyboardModifier.AltModifier
Shift = Qt.KeyboardModifier.ShiftModifier
_QUEBRA = QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore
_SEM_QUEBRA = QTextFormat.PageBreakFlag.PageBreak_Auto


class PainelDocumento(VistaPaginas):
    textChanged = Signal()
    cursorPositionChanged = Signal()
    currentCharFormatChanged = Signal(QTextCharFormat)
    undoAvailable = Signal(bool)
    redoAvailable = Signal(bool)
    copyAvailable = Signal(bool)
    paginaAlterada = Signal()

    def __init__(self, fonte: str, tamanho: float, parent=None) -> None:
        layout = LayoutPaginado(Pagina(), fonte, float(tamanho))
        super().__init__(layout, parent)
        self._acoes: list[QAction] = []
        self._cursor = QTextCursor(layout.doc)
        self._arrastando = False
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
        md.setText(frag.toPlainText())
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
            frag = QTextDocumentFragment.fromHtml(md.html())
        else:
            frag = QTextDocumentFragment.fromPlainText(md.text())
        if self._cursor.hasSelection():
            self._cursor.removeSelectedText()
        self._cursor.insertFragment(frag)
        self._depois_de_mover()

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
        """Ctrl+Enter: o texto depois do caret comeca no topo da proxima pagina."""
        self._quebrar(quebra=True)

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

    def _inserir(self, texto: str) -> None:
        if self._cursor.hasSelection():
            self._cursor.removeSelectedText()
        self._cursor.insertText(texto)
        self._depois_de_mover()

    def _quebrar(self, quebra: bool) -> None:
        if self._cursor.hasSelection():
            self._cursor.removeSelectedText()
        bf = QTextBlockFormat(self._cursor.blockFormat())
        bf.setPageBreakPolicy(_QUEBRA if quebra else _SEM_QUEBRA)
        self._cursor.insertBlock(bf)
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
            else:
                return False
            return True

        if k in (Key.Key_Return, Key.Key_Enter):
            self._quebrar(quebra=False)
        elif k == Key.Key_Backspace:
            self._apagar(anterior=True)
        elif k == Key.Key_Delete:
            self._apagar(anterior=False)
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

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        self.setFocus()
        if ev.button() == Qt.MouseButton.LeftButton:
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
        if self._arrastando:
            self._cursor.setPosition(self.posicao_em(ev.position()), Selecionar)
            self._depois_de_mover()
        ev.accept()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
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
        menu.exec(ev.globalPos())

    # ----- foco ------------------------------------------------------------
    def focusInEvent(self, ev) -> None:  # noqa: N802
        super().focusInEvent(ev)
        self.definir_piscar(True)

    def focusOutEvent(self, ev) -> None:  # noqa: N802
        super().focusOutEvent(ev)
        self.definir_piscar(False)
