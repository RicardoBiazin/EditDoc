"""Faixa amarela sob a faixa de opcoes: o que salvar faria o arquivo perder.

Desde a 0.1.19 a faixa so' aparece com os avisos de PERDA (`perde_ao_salvar`): o que o Salvar
pede para confirmar. Recurso preservado e so' de leitura (caixa de texto, forma, equacao,
imagem flutuante, objeto opaco, revisao preservada) nao gera faixa. Esses avisos ficam em
`avisos()` e aparecem na lista completa, que abre por "Detalhes" da faixa e por
Arquivo > Objetos preservados (`mostrar_lista`).

A faixa fica ate' o usuario fechar, ou ate' um salvamento que resolve os avisos.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from editdoc.formato_docx.avisos import Aviso
from editdoc.interface import dialogos_modais

#: Titulo da caixa com a lista completa (faixa e menu usam o mesmo).
TITULO_LISTA = "Recursos que o EditDoc não edita"

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


def texto_da_lista(avisos: Iterable[Aviso]) -> str:
    """A lista completa de avisos, em dois grupos: o que sai do arquivo ao salvar, e o que
    nao se perde (preservado, so' de leitura ou mostrado de outro jeito)."""
    avisos = list(avisos)
    if not avisos:
        return "Este documento não tem recursos que o EditDoc não edita."
    com_perda = [a for a in avisos if a.perde_ao_salvar]
    sem_perda = [a for a in avisos if not a.perde_ao_salvar]
    partes: list[str] = []
    if com_perda:
        partes.append("Sai do arquivo ao salvar:")
        partes += [f"- {a.texto}" for a in com_perda]
    if sem_perda:
        if partes:
            partes.append("")
        partes.append("Não se perdem ao salvar:")
        partes += [f"- {a.texto}" for a in sem_perda]
    return "\n".join(partes)


def mostrar_lista(pai: QWidget | None, avisos: Iterable[Aviso]) -> None:
    """Abre a caixa com a lista completa (Arquivo > Objetos preservados e o Detalhes da faixa)."""
    dialogos_modais.mostrar_detalhes(pai, TITULO_LISTA, texto_da_lista(avisos))


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
        self._detalhes.setAccessibleDescription("Mostrar a lista completa de recursos do documento")
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
        """Guarda todos os avisos (a lista completa mostra todos). A faixa so' aparece se algum
        deles faz o salvar perder algo; sem isso, esconde."""
        self._avisos = list(avisos)
        com_perda = [a for a in self._avisos if a.perde_ao_salvar]
        if not com_perda:
            self.hide()
            return
        primeiro = com_perda[0].texto
        mais = len(com_perda) - 1
        sufixo = "" if mais == 0 else f" (mais {mais} aviso{'s' if mais > 1 else ''})"
        self._rotulo.setText(f"Este documento tem recursos que o EditDoc não edita nesta versão: "
                             f"{primeiro}{sufixo}")
        self.show()

    def avisos(self) -> list[Aviso]:
        """Todos os avisos recebidos, com e sem perda."""
        return list(self._avisos)

    def texto_da_faixa(self) -> str:
        """O texto que a faixa mostra (vazio quando ela esta' escondida)."""
        return self._rotulo.text() if not self.isHidden() else ""

    def texto_completo(self) -> str:
        """A lista completa, a mesma do botao Detalhes."""
        return texto_da_lista(self._avisos)

    def fechar(self) -> None:
        self.hide()
        self._avisos = []
        self.fechada.emit()

    def _mostrar_detalhes(self) -> None:
        mostrar_lista(self.window(), self._avisos)
