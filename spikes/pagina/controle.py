"""Spike A: controle de caret, teclado, selecao, clipboard e desfazer.

Tudo sobre um QTextCursor. A visao encaminha eventos de teclado e de mouse
(ja convertidos em posicao do documento) para ControleTexto.
"""
from PySide6.QtCore import QMimeData, QObject, QPointF, Qt, Signal
from PySide6.QtGui import (QFont, QImage, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextDocumentFragment, QTextFormat,
                           QTextImageFormat, QTextTable, QTextDocument)
from PySide6.QtWidgets import QApplication

KeyboardModifier = Qt.KeyboardModifier
# Propriedade de formato que marca um campo (ex.: NOME) no texto. Achado (fato 10):
# o texto digitado logo depois do campo HERDA a propriedade. Removida na digitacao.
PROP_CAMPO = QTextFormat.UserProperty + 1
Key = Qt.Key
MODO_MOVER = QTextCursor.MoveMode.MoveAnchor
MODO_SELECIONAR = QTextCursor.MoveMode.KeepAnchor


class ControleTexto(QObject):
    mudou = Signal()

    def __init__(self, layout, parent=None):
        super().__init__(parent)
        self.layout_pag = layout
        self.doc = layout.doc
        self.cursor = QTextCursor(self.doc)
        self._arrastando = False
        self._fmt_base = QTextCharFormat()
        self._fmt_base.setFont(QFont(self.doc.defaultFont()))
        # a visao substitui por uma funcao que devolve a altura visivel em twips
        self.altura_visivel = lambda: 0.0

    # ----- estado ------------------------------------------------------------
    def tem_foco_visivel(self) -> bool:
        return True

    def arrastando(self) -> bool:
        return self._arrastando

    # ----- mouse ---------------------------------------------------------------
    def clicar(self, pos: int, estender: bool = False) -> None:
        self.cursor.setPosition(pos, MODO_SELECIONAR if estender else MODO_MOVER)
        self._arrastando = True

    def arrastar(self, pos: int) -> None:
        self.cursor.setPosition(pos, MODO_SELECIONAR)

    def soltar(self) -> None:
        self._arrastando = False

    # ----- formato de digitacao (fato 10) -------------------------------------
    def _formato_digitacao(self) -> QTextCharFormat:
        fmt = QTextCharFormat(self.cursor.charFormat())
        # Depois de um objeto (imagem), o caret herda o formato do objeto.
        # Digitar sobre ele sairia como imagem: volta ao formato de texto.
        if fmt.objectType() != QTextFormat.ObjectTypes.NoObject:
            fmt = QTextCharFormat(self._fmt_base)
        # Depois de um campo, o texto novo nao pode continuar sendo o campo.
        if fmt.hasProperty(PROP_CAMPO):
            fmt.clearProperty(PROP_CAMPO)
        return fmt

    # ----- edicao --------------------------------------------------------------
    def _apagar_selecao(self) -> None:
        if self.cursor.hasSelection():
            self.cursor.removeSelectedText()

    def inserir_texto(self, texto: str) -> None:
        self._apagar_selecao()
        self.cursor.insertText(texto, self._formato_digitacao())

    def quebrar_bloco(self) -> None:
        self._apagar_selecao()
        bf = QTextBlockFormat(self.cursor.blockFormat())
        bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_Auto)
        self.cursor.insertBlock(bf, self._formato_digitacao())

    def quebra_de_pagina(self) -> None:
        """Ctrl+Enter: novo paragrafo que comeca no topo da proxima pagina."""
        self._apagar_selecao()
        bf = QTextBlockFormat(self.cursor.blockFormat())
        bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
        self.cursor.insertBlock(bf, self._formato_digitacao())

    def apagar_antes(self) -> None:
        if self.cursor.hasSelection():
            self.cursor.removeSelectedText()
        else:
            self.cursor.deletePreviousChar()

    def apagar_depois(self) -> None:
        if self.cursor.hasSelection():
            self.cursor.removeSelectedText()
        else:
            self.cursor.deleteChar()

    def alternar_negrito(self) -> None:
        negrito = self.cursor.charFormat().fontWeight() >= QFont.Weight.Bold
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal if negrito else QFont.Weight.Bold)
        self.cursor.mergeCharFormat(fmt)

    def inserir_imagem(self, nome: str, imagem: QImage, largura_px: float, altura_px: float):
        """Insere imagem reduzida (proporcao mantida) para caber no corpo.

        Imagem maior que a pagina estoura o layout (Qt nao a divide), entao o
        limite e aplicado ao inserir. Tamanhos em px96 (x15 = twips).
        Devolve (largura_px, altura_px) finais.
        """
        cfg = self.layout_pag.config
        max_w = cfg.larg_corpo / 15.0
        max_h = (cfg.alt_corpo - 400) / 15.0  # folga para a linha da imagem
        escala = min(1.0, max_w / largura_px, max_h / altura_px)
        w, h = largura_px * escala, altura_px * escala
        self._apagar_selecao()
        self.doc.addResource(QTextDocument.ResourceType.ImageResource, nome, imagem)
        fmt = QTextImageFormat()
        fmt.setName(nome)
        fmt.setWidth(w)
        fmt.setHeight(h)
        self.cursor.insertImage(fmt)
        self.mudou.emit()
        return w, h

    # ----- selecao -----------------------------------------------------------
    def selecionar_tudo(self) -> None:
        self.cursor.select(QTextCursor.SelectionType.Document)

    # ----- clipboard (mantem tabelas via HTML) ------------------------------
    def copiar(self) -> None:
        if not self.cursor.hasSelection():
            return
        frag = QTextDocumentFragment(self.cursor)
        md = QMimeData()
        md.setHtml(frag.toHtml())
        md.setText(frag.toPlainText())
        QApplication.clipboard().setMimeData(md)

    def recortar(self) -> None:
        self.copiar()
        if self.cursor.hasSelection():
            self.cursor.removeSelectedText()

    def colar(self) -> None:
        md = QApplication.clipboard().mimeData()
        if md is None:
            return
        if md.hasHtml():
            frag = QTextDocumentFragment.fromHtml(md.html())
        else:
            frag = QTextDocumentFragment.fromPlainText(md.text())
        self._apagar_selecao()
        self.cursor.insertFragment(frag)

    # ----- desfazer / refazer (fato: undo(cursor) posiciona o caret) ---------
    def desfazer(self) -> None:
        if self.doc.isUndoAvailable():
            self.doc.undo(self.cursor)

    def refazer(self) -> None:
        if self.doc.isRedoAvailable():
            self.doc.redo(self.cursor)

    # ----- tabelas -----------------------------------------------------------
    def _proxima_celula(self, anterior: bool) -> bool:
        tabela = self.cursor.currentTable()
        if tabela is None:
            return False
        celula = tabela.cellAt(self.cursor)
        r, c = celula.row(), celula.column()
        if anterior:
            if c > 0:
                c -= 1
            elif r > 0:
                r, c = r - 1, tabela.columns() - 1
            else:
                return True
        else:
            if c + 1 < tabela.columns():
                c += 1
            elif r + 1 < tabela.rows():
                r, c = r + 1, 0
            else:
                return True
        destino = tabela.cellAt(r, c)
        self.cursor.setPosition(destino.firstCursorPosition().position())
        return True

    # ----- teclado -----------------------------------------------------------
    def tecla(self, ev) -> bool:
        """Trata um QKeyEvent. Devolve True se o evento foi consumido."""
        k = ev.key()
        mod = ev.modifiers()
        ctrl = bool(mod & KeyboardModifier.ControlModifier)
        alt = bool(mod & KeyboardModifier.AltModifier)
        shift = bool(mod & KeyboardModifier.ShiftModifier)
        mode = MODO_SELECIONAR if shift else MODO_MOVER
        M = QTextCursor.MoveOperation

        if ctrl and not alt:
            if k == Key.Key_A:
                self.selecionar_tudo()
            elif k == Key.Key_Z and shift:
                self.refazer()
            elif k == Key.Key_Z:
                self.desfazer()
            elif k == Key.Key_Y:
                self.refazer()
            elif k == Key.Key_C:
                self.copiar()
            elif k == Key.Key_X:
                self.recortar()
            elif k == Key.Key_V:
                self.colar()
            elif k == Key.Key_B:
                self.alternar_negrito()
            elif k in (Key.Key_Return, Key.Key_Enter):
                self.quebra_de_pagina()
            elif k == Key.Key_Home:
                self.cursor.movePosition(M.Start, mode)
            elif k == Key.Key_End:
                self.cursor.movePosition(M.End, mode)
            elif k == Key.Key_Left:
                self.cursor.movePosition(M.WordLeft, mode)
            elif k == Key.Key_Right:
                self.cursor.movePosition(M.WordRight, mode)
            else:
                return False
            self.mudou.emit()
            return True

        if k in (Key.Key_Return, Key.Key_Enter):
            self.quebrar_bloco()
        elif k == Key.Key_Backspace:
            self.apagar_antes()
        elif k == Key.Key_Delete:
            self.apagar_depois()
        elif k == Key.Key_Tab:
            if self.cursor.currentTable() is not None:
                self._proxima_celula(anterior=shift)
            else:
                self.inserir_texto("\t")
        elif k == Key.Key_Backtab:
            if self.cursor.currentTable() is not None:
                self._proxima_celula(anterior=True)
        elif k == Key.Key_Left:
            self.cursor.movePosition(M.Left, mode)
        elif k == Key.Key_Right:
            self.cursor.movePosition(M.Right, mode)
        elif k == Key.Key_Up:
            self.cursor.movePosition(M.Up, mode)
        elif k == Key.Key_Down:
            self.cursor.movePosition(M.Down, mode)
        elif k == Key.Key_Home:
            self.cursor.movePosition(M.StartOfLine, mode)
        elif k == Key.Key_End:
            self.cursor.movePosition(M.EndOfLine, mode)
        elif k in (Key.Key_PageUp, Key.Key_PageDown):
            self._pagina(anterior=(k == Key.Key_PageUp), modo=mode)
        else:
            texto = ev.text()
            if not texto or not texto.isprintable():
                return False
            if ctrl and not alt:
                return False
            self.inserir_texto(texto)
        self.mudou.emit()
        return True

    def _pagina(self, anterior: bool, modo) -> None:
        """PageUp/PageDown: anda uma altura de tela, mantendo a coluna do caret."""
        r = self.layout_pag.retangulo_cursor(self.cursor.position())
        h = self.altura_visivel()
        alvo = QPointF(r.x(), r.y() + (-h if anterior else h))
        doc_layout = self.doc.documentLayout()
        pos = doc_layout.hitTest(alvo, Qt.FuzzyHit)
        self.cursor.setPosition(pos, modo)
