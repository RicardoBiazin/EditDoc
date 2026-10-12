"""Visao provisoria do documento: um QTextEdit com atalhos proprios.

A visao em paginas (M3) substitui este widget. Ate la, o editor e' o QTextEdit,
que ja traz o cursor, a selecao, o clipboard e o desfazer. O que ele nao traz e'
o atalho de comando: QTextEdit consome as teclas de edicao antes da janela
(ShortcutOverride). Por isso o painel procura o atalho no proprio keyPressEvent.
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QFont, QKeyEvent, QKeySequence
from PySide6.QtWidgets import QTextEdit, QWidget


class PainelDocumento(QTextEdit):
    def __init__(self, fonte: str, tamanho: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._acoes: list[QAction] = []
        self.setAcceptRichText(True)
        self.setUndoRedoEnabled(True)
        padrao = QFont(fonte)
        padrao.setPointSizeF(float(tamanho))
        self.document().setDefaultFont(padrao)
        self.setPlaceholderText("")

    def registrar_atalhos(self, acoes: list[QAction]) -> None:
        self._acoes = list(acoes)

    def keyPressEvent(self, evento: QKeyEvent) -> None:  # noqa: N802 - nome do Qt
        sequencia = QKeySequence(evento.keyCombination())
        for acao in self._acoes:
            if acao.isEnabled() and sequencia in acao.shortcuts():
                acao.trigger()
                evento.accept()
                return
        super().keyPressEvent(evento)
