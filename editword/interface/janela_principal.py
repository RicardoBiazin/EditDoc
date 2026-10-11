"""Janela principal.

Na 0.0.1 so' a casca existe: a faixa de opcoes, a visao em paginas e os comandos
entram nos marcos seguintes (ver docs/ARQUITETURA.md).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow

from editword import APP, VERSAO, recursos


class JanelaPrincipal(QMainWindow):
    def __init__(self, cfg: dict) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP} {VERSAO}")
        self.setWindowIcon(recursos.icone_do_aplicativo())
        self.resize(cfg["janela_largura"], cfg["janela_altura"])

        vazio = QLabel("Documento em branco")
        vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(vazio)
        self.statusBar().showMessage(f"{APP} {VERSAO}")
