"""Editor do texto de um comentario (0.1.6): negrito, italico, sublinhado e links.

O texto vai num QTextEdit comum (documento proprio, pequeno, sem a visao em paginas: a
armadilha do QTextEdit sobre o documento paginado nao se aplica). `conteudo_de` devolve os
paragrafos do modelo; `preencher` faz o caminho de volta. So' e' editavel o que volta sem
perda (`edicao/comentarios.motivo_somente_leitura`): o resto abre so' para leitura, com o
motivo na tela.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel,
                               QTextEdit, QToolButton, QVBoxLayout, QWidget)

from editdoc.modelo.documento import Link, Paragrafo, Run

#: Tamanho maximo do texto de um comentario digitado no EditDoc (caracteres).
TEXTO_MAXIMO = 100_000
_SEPARADOR = " "


def preencher(editor: QTextEdit, paragrafos: tuple) -> None:
    """Poe os paragrafos do comentario no QTextEdit (so' texto, N/I/S e link)."""
    editor.clear()
    cursor = QTextCursor(editor.document())
    primeiro = True
    for p in paragrafos:
        if not isinstance(p, Paragrafo):
            continue
        if not primeiro:
            cursor.insertBlock()
        primeiro = False
        for r in p.runs:
            if r.marca is not None or r.eh_objeto():
                continue
            cf = QTextCharFormat()
            if r.negrito:
                cf.setFontWeight(QFont.Weight.Bold)
            if r.italico:
                cf.setFontItalic(True)
            if r.sublinhado:
                cf.setFontUnderline(True)
            if r.link is not None:
                cf.setAnchor(True)
                cf.setAnchorHref(r.link.href())
                cf.setFontUnderline(True)
                cf.setForeground(Qt.GlobalColor.blue)
            cursor.insertText(r.texto.replace("\n", _SEPARADOR), cf)
    editor.moveCursor(QTextCursor.MoveOperation.End)


def _link_de(href: str) -> Link | None:
    href = (href or "").strip()
    if not href:
        return None
    if href.startswith("#"):
        return Link(ancora=href[1:] or None)
    url, _, ancora = href.partition("#")
    return Link(url=url, ancora=ancora or None)


def conteudo_de(editor: QTextEdit) -> tuple:
    """Os paragrafos do QTextEdit, no modelo (o estilo do comentario entra depois)."""
    saida = []
    bloco = editor.document().begin()
    while bloco.isValid():
        p = Paragrafo()
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.text():
                cf = frag.charFormat()
                link = _link_de(cf.anchorHref()) if cf.isAnchor() else None
                r = Run(texto=frag.text().replace(_SEPARADOR, "\n"),
                        negrito=True if cf.fontWeight() >= 600 else None,
                        italico=True if cf.fontItalic() else None,
                        sublinhado=True if cf.fontUnderline() and link is None else None,
                        link=link)
                p.runs.append(r)
            it += 1
        saida.append(p)
        bloco = bloco.next()
    while len(saida) > 1 and not saida[-1].runs:
        saida.pop()
    return tuple(saida)


class DialogoComentario(QDialog):
    def __init__(self, titulo: str, paragrafos: tuple = (), somente_leitura: str = "",
                 pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self.setWindowTitle(titulo)
        self.setAccessibleName(titulo)
        self.resize(460, 260)
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setAccessibleName("Texto do comentário")
        self.editor.setTabChangesFocus(True)
        preencher(self.editor, paragrafos)
        barra = QHBoxLayout()
        self.botoes_formato: list[QToolButton] = []
        for rotulo, nome, atalho, funcao in (
                ("N", "Negrito", "Ctrl+B", self._negrito),
                ("I", "Itálico", "Ctrl+I", self._italico),
                ("S", "Sublinhado", "Ctrl+U", self._sublinhado),
                ("Link", "Inserir link no texto selecionado", "Ctrl+K", self._link)):
            b = QToolButton()
            b.setText(rotulo)
            b.setToolTip(f"{nome} ({atalho})")
            b.setAccessibleName(nome)
            b.setShortcut(QKeySequence(atalho))
            b.clicked.connect(funcao)
            barra.addWidget(b)
            self.botoes_formato.append(b)
        barra.addStretch(1)
        vertical = QVBoxLayout(self)
        self.motivo = QLabel(somente_leitura)
        self.motivo.setWordWrap(True)
        self.motivo.setVisible(bool(somente_leitura))
        vertical.addWidget(self.motivo)
        vertical.addLayout(barra)
        vertical.addWidget(self.editor, 1)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                  | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        self.botoes = botoes
        vertical.addWidget(botoes)
        if somente_leitura:
            self.editor.setReadOnly(True)
            for b in self.botoes_formato:
                b.setEnabled(False)
            botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Fechar")
            botoes.button(QDialogButtonBox.StandardButton.Cancel).hide()
        self.editor.setFocus()

    def _formato(self, aplicar) -> None:
        cursor = self.editor.textCursor()
        cf = QTextCharFormat()
        aplicar(cf, cursor.charFormat())
        if cursor.hasSelection():
            cursor.mergeCharFormat(cf)
        self.editor.mergeCurrentCharFormat(cf)

    def _negrito(self) -> None:
        self._formato(lambda cf, atual: cf.setFontWeight(
            QFont.Weight.Normal if atual.fontWeight() >= 600 else QFont.Weight.Bold))

    def _italico(self) -> None:
        self._formato(lambda cf, atual: cf.setFontItalic(not atual.fontItalic()))

    def _sublinhado(self) -> None:
        self._formato(lambda cf, atual: cf.setFontUnderline(not atual.fontUnderline()))

    def _link(self) -> None:
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return
        endereco, ok = QInputDialog.getText(self, "Link", "Endereço (http, https, mailto ou #marcador):")
        if ok:
            self.aplicar_link(endereco)

    def aplicar_link(self, endereco: str) -> None:
        """Poe (ou tira, com endereco vazio) o link no texto selecionado."""
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return
        cf = QTextCharFormat()
        endereco = endereco.strip()
        cf.setAnchor(bool(endereco))
        cf.setAnchorHref(endereco)
        cf.setFontUnderline(bool(endereco))
        if endereco:
            cf.setForeground(Qt.GlobalColor.blue)
        cursor.mergeCharFormat(cf)

    def conteudo(self) -> tuple:
        return conteudo_de(self.editor)


def pedir(pai: QWidget | None, titulo: str, paragrafos: tuple = (),
          somente_leitura: str = "") -> tuple | None:
    """Mostra o editor. Devolve os paragrafos (OK) ou None (cancelado, ou so' leitura)."""
    dialogo = DialogoComentario(titulo, paragrafos, somente_leitura, pai)
    if dialogo.exec() != QDialog.DialogCode.Accepted or somente_leitura:
        return None
    conteudo = dialogo.conteudo()
    texto = sum(len(r.texto) for p in conteudo for r in p.runs)
    if texto == 0 or texto > TEXTO_MAXIMO:
        return None
    return conteudo
