"""Barra de localizar e substituir, abaixo da faixa.

A barra so' emite sinais. Quem executa a busca e' a janela, que tem o editor.
Assim a barra fica testavel sem documento e a logica fica em edicao/busca.py.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QWidget)


class BarraBusca(QFrame):
    #: texto, maiusculas, palavra inteira, para tras
    procurar = Signal(str, bool, bool, bool)
    #: texto, substituto, maiusculas, palavra inteira
    substituir_um = Signal(str, str, bool, bool)
    substituir_tudo = Signal(str, str, bool, bool)
    fechada = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._procurar = QLineEdit()
        self._procurar.setPlaceholderText("Localizar")
        self._procurar.setAccessibleName("Texto a localizar")
        self._procurar.setClearButtonEnabled(True)
        self._procurar.returnPressed.connect(self._proxima)

        self._substituto = QLineEdit()
        self._substituto.setPlaceholderText("Substituir por")
        self._substituto.setAccessibleName("Substituir por")
        self._substituto.setClearButtonEnabled(True)

        self._maiusculas = QCheckBox("Diferenciar maiúsculas")
        self._palavra = QCheckBox("Palavra inteira")
        self._mensagem = QLabel("")
        self._mensagem.setMinimumWidth(160)
        self._mensagem.setAccessibleName("Resultado da busca")

        self._anterior = QPushButton("Anterior")
        self._anterior.clicked.connect(self._voltar)
        self._proxima_botao = QPushButton("Próxima")
        self._proxima_botao.clicked.connect(self._proxima)
        self._trocar = QPushButton("Substituir")
        self._trocar.clicked.connect(self._substituir_atual)
        self._trocar_tudo = QPushButton("Substituir tudo")
        self._trocar_tudo.clicked.connect(self._substituir_todas)
        self._fechar = QPushButton("Fechar")
        self._fechar.clicked.connect(self.fechar)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(8, 4, 8, 4)
        linha.addWidget(self._procurar, 2)
        linha.addWidget(self._substituto, 2)
        for widget in (self._anterior, self._proxima_botao, self._trocar,
                       self._trocar_tudo, self._maiusculas, self._palavra):
            linha.addWidget(widget)
        linha.addWidget(self._mensagem, 1)
        linha.addWidget(self._fechar)

    # -- uso ----------------------------------------------------------------

    def mostrar(self, substituir: bool) -> None:
        self._substituto.setVisible(substituir)
        self._trocar.setVisible(substituir)
        self._trocar_tudo.setVisible(substituir)
        self.show()
        self._procurar.setFocus()
        self._procurar.selectAll()
        self.dizer("")

    def fechar(self) -> None:
        self.hide()
        self.fechada.emit()

    def dizer(self, texto: str) -> None:
        self._mensagem.setText(texto)

    def texto(self) -> str:
        return self._procurar.text()

    def substituto(self) -> str:
        return self._substituto.text()

    def maiusculas(self) -> bool:
        return self._maiusculas.isChecked()

    def palavra_inteira(self) -> bool:
        return self._palavra.isChecked()

    # -- acoes --------------------------------------------------------------

    def _proxima(self) -> None:
        self.procurar.emit(self.texto(), self.maiusculas(), self.palavra_inteira(), False)

    def _voltar(self) -> None:
        self.procurar.emit(self.texto(), self.maiusculas(), self.palavra_inteira(), True)

    def _substituir_atual(self) -> None:
        self.substituir_um.emit(self.texto(), self.substituto(),
                                self.maiusculas(), self.palavra_inteira())

    def _substituir_todas(self) -> None:
        self.substituir_tudo.emit(self.texto(), self.substituto(),
                                  self.maiusculas(), self.palavra_inteira())

    def keyPressEvent(self, evento: QKeyEvent) -> None:  # noqa: N802 - nome do Qt
        if evento.key() == Qt.Key.Key_Escape:
            self.fechar()
            evento.accept()
            return
        super().keyPressEvent(evento)
