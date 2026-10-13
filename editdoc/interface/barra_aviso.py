"""Faixa amarela sob a faixa de opcoes: o que o arquivo tem e o programa nao edita.

Mostra a primeira linha dos avisos. "Detalhes" abre a lista completa numa caixa.
Fica ate' o usuario fechar, ou ate' um salvamento que resolve os avisos.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from editdoc.formato_docx.avisos import Aviso
from editdoc.interface import dialogos_modais

_COR = "#fff3c4"
_BORDA = "#d9b44a"
# O fundo e' sempre amarelo claro, entao o texto tem de ser sempre escuro. Sem
# isto, no tema escuro o rotulo herda o texto claro da paleta e some no amarelo.
_TEXTO = "#1f1f1f"
_ESTILO = (
    f"#barraAviso {{ background: {_COR}; border-bottom: 1px solid {_BORDA}; }}"
    f"#barraAviso QLabel {{ color: {_TEXTO}; background: transparent; }}"
    f"#barraAviso QPushButton {{ color: {_TEXTO}; background: #fffaf0;"
    f" border: 1px solid {_BORDA}; border-radius: 3px; padding: 2px 10px; }}"
    f"#barraAviso QPushButton:hover {{ background: #ffe9a8; }}"
    f"#barraAviso QPushButton:focus {{ border: 2px solid #8a6d00; }}")


class BarraAviso(QFrame):
    fechada = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("barraAviso")
        self.setStyleSheet(_ESTILO)
        self._avisos: list[Aviso] = []
        self._rotulo = QLabel()
        self._rotulo.setWordWrap(True)
        self._rotulo.setAccessibleName("Aviso do documento")
        self._detalhes = QPushButton("Detalhes")
        self._detalhes.setAccessibleDescription("Mostrar a lista completa de avisos")
        self._detalhes.clicked.connect(self._mostrar_detalhes)
        self._fechar = QPushButton("Fechar")
        self._fechar.setAccessibleName("Fechar o aviso")
        self._fechar.clicked.connect(self.fechar)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(8, 4, 8, 4)
        linha.addWidget(self._rotulo, 1)
        linha.addWidget(self._detalhes)
        linha.addWidget(self._fechar)
        self.hide()

    def mostrar(self, avisos: list[Aviso]) -> None:
        """Mostra a barra se houver avisos; sem avisos, esconde."""
        self._avisos = list(avisos)
        if not self._avisos:
            self.hide()
            return
        primeiro = self._avisos[0].texto
        mais = len(self._avisos) - 1
        sufixo = "" if mais == 0 else f" (mais {mais} aviso{'s' if mais > 1 else ''})"
        self._rotulo.setText(f"Este documento tem recursos que o EditDoc não edita nesta versão: "
                             f"{primeiro}{sufixo}")
        self.show()

    def avisos(self) -> list[Aviso]:
        return list(self._avisos)

    def texto_completo(self) -> str:
        return "\n".join(f"- {a.texto}" for a in self._avisos)

    def fechar(self) -> None:
        self.hide()
        self._avisos = []
        self.fechada.emit()

    def _mostrar_detalhes(self) -> None:
        dialogos_modais.mostrar_detalhes(
            self.window(), "Recursos que o EditDoc não edita", self.texto_completo())
