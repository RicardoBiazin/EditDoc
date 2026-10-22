"""Botao Arquivo da faixa: Novo, Abrir, Salvar, Salvar como, Abrir recente, Exportar,
Imprimir, Visualizar impressao, Recuperar documentos, Opcoes (M8), Fechar.

Os comandos sao os QAction de `comandos.py`, os mesmos do atalho. O submenu de
recentes se monta na hora em que abre, para refletir a lista atual.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

from editdoc.interface.comandos import Comandos


class BotaoArquivo(QToolButton):
    def __init__(self, comandos: Comandos, recentes: Callable[[], list[str]],
                 abrir_recente: Callable[[str], None], pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self._recentes_de = recentes
        self._abrir_recente = abrir_recente
        self.setText("Arquivo ▾")
        self.setToolTip("Arquivo: novo, abrir, salvar, exportar, imprimir e fechar")
        self.setAccessibleName("Arquivo")
        self.setAccessibleDescription("Menu Arquivo: novo, abrir, salvar, recentes, exportar, "
                                      "imprimir, recuperar documentos, opções e fechar")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        menu = QMenu(self)
        for id_ in ("novo", "abrir", "salvar", "salvar_como"):
            menu.addAction(comandos.acao(id_))
        self._menu_recentes = QMenu("Abrir recente", menu)
        self._menu_recentes.aboutToShow.connect(self._montar_recentes)
        menu.addMenu(self._menu_recentes)
        menu.addSeparator()
        self._menu_exportar = QMenu("Exportar", menu)
        for id_ in ("exportar_pdf", "exportar_txt"):
            self._menu_exportar.addAction(comandos.acao(id_))
        menu.addMenu(self._menu_exportar)
        for id_ in ("imprimir", "visualizar_impressao"):
            menu.addAction(comandos.acao(id_))
        menu.addSeparator()
        menu.addAction(comandos.acao("objetos_preservados"))
        menu.addAction(comandos.acao("recuperar"))
        menu.addAction(comandos.acao("opcoes"))
        menu.addSeparator()
        menu.addAction(comandos.acao("fechar"))
        self.setMenu(menu)

    def _montar_recentes(self) -> None:
        self._menu_recentes.clear()
        caminhos = self._recentes_de()
        if not caminhos:
            vazio = QAction("(nenhum)", self._menu_recentes)
            vazio.setEnabled(False)
            self._menu_recentes.addAction(vazio)
            return
        for caminho in caminhos:
            acao = QAction(os.path.basename(caminho), self._menu_recentes)
            acao.setToolTip(caminho)
            acao.setStatusTip(caminho)
            acao.triggered.connect(lambda _=False, p=caminho: self._abrir_recente(p))
            self._menu_recentes.addAction(acao)

    def menu_recentes(self) -> QMenu:
        return self._menu_recentes

    def menu_exportar(self) -> QMenu:
        return self._menu_exportar
