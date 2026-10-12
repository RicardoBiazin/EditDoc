"""Mantem a faixa em sintonia com o cursor, sem laco e sem trabalho a toa.

Cada mudanca de cursor ou de formato so' agenda uma atualizacao (QTimer de zero
ms). Varias mudancas seguidas viram uma atualizacao so', no proximo ciclo de
eventos.

Atualizar os botoes com setChecked nao dispara `triggered`, so' `toggled`. Os
executores ligam-se a `triggered`, por isso atualizar a faixa nao executa comando
nenhum.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QSignalBlocker, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QComboBox, QFontComboBox, QTextEdit

from editdoc.edicao.estado import ler
from editdoc.interface.comandos import ALINHAMENTOS, ESPACAMENTOS, Comandos


class AtualizadorDeEstado(QObject):
    def __init__(self, editor: QTextEdit, comandos: Comandos,
                 familia: QFontComboBox, tamanho: QComboBox) -> None:
        super().__init__(editor)
        self._editor = editor
        self._comandos = comandos
        self._familia = familia
        self._tamanho = tamanho
        self._agendado = False

        editor.cursorPositionChanged.connect(self._agendar)
        editor.currentCharFormatChanged.connect(self._agendar)
        editor.undoAvailable.connect(comandos.acao("desfazer").setEnabled)
        editor.redoAvailable.connect(comandos.acao("refazer").setEnabled)
        editor.copyAvailable.connect(self._copia_disponivel)
        self.atualizar()

    def _copia_disponivel(self, disponivel: bool) -> None:
        self._comandos.acao("recortar").setEnabled(disponivel)
        self._comandos.acao("copiar").setEnabled(disponivel)

    def _agendar(self) -> None:
        if not self._agendado:
            self._agendado = True
            QTimer.singleShot(0, self._executar_agendado)

    def _executar_agendado(self) -> None:
        self._agendado = False
        self.atualizar()

    def atualizar(self) -> None:
        estado = ler(self._editor)
        c = self._comandos
        valores = {
            "negrito": estado.negrito,
            "italico": estado.italico,
            "sublinhado": estado.sublinhado,
            "tachado": estado.tachado,
            "subscrito": estado.subscrito,
            "sobrescrito": estado.sobrescrito,
            "marcadores": estado.marcadores,
            "numeracao": estado.numeracao,
        }
        for id_, valor in valores.items():
            c.acao(id_).setChecked(valor)
        for id_ in ALINHAMENTOS:
            c.acao(id_).setChecked(ALINHAMENTOS[id_] == _alinhamento_de(estado.alinhamento))
        for id_, percentual in ESPACAMENTOS.items():
            c.acao(id_).setChecked(percentual == estado.espacamento)

        with QSignalBlocker(self._familia), QSignalBlocker(self._tamanho):
            if estado.familia and self._familia.currentFont().family() != estado.familia:
                self._familia.setCurrentFont(QFont(estado.familia))
            texto = f"{estado.tamanho:g}"
            if self._tamanho.currentText() != texto:
                self._tamanho.setCurrentText(texto)


def _alinhamento_de(nome: str) -> Qt.AlignmentFlag:
    return {
        "esquerda": Qt.AlignmentFlag.AlignLeft,
        "centro": Qt.AlignmentFlag.AlignHCenter,
        "direita": Qt.AlignmentFlag.AlignRight,
        "justificado": Qt.AlignmentFlag.AlignJustify,
    }[nome]
