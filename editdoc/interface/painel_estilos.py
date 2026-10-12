"""Painel de estilos (M6): a lista completa, como o Alt+Ctrl+Shift+S do Word.

Fica num QDockWidget opcional. Mostra todos os estilos de paragrafo e de caractere que
nao sao ocultos, em ordem alfabetica do nome na tela, com o do cursor marcado. Clique
aplica. Os botoes embaixo sao os mesmos comandos da faixa (Criar, Modificar, Limpar).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QListWidget, QListWidgetItem, QVBoxLayout,
                               QWidget)

from editdoc.modelo.estilos import Estilos

#: Corpo maximo da visualizacao na lista.
PONTOS_MAXIMOS = 14.0


class PainelEstilos(QWidget):
    escolhido = Signal(str)

    def __init__(self, botoes: list[QWidget] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.lista = QListWidget()
        self.lista.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lista.itemClicked.connect(self._clicado)
        self.visualizar = QCheckBox("Mostrar visualização")
        self.visualizar.setToolTip("Mostrar cada nome com a aparência do estilo")
        self.visualizar.toggled.connect(lambda _v: self._encher())
        self._estilos: Estilos | None = None
        self._fonte_padrao = QFont()
        self._assinatura = None
        self._atual: str | None = None
        vertical = QVBoxLayout(self)
        vertical.setContentsMargins(4, 4, 4, 4)
        vertical.addWidget(self.lista, 1)
        vertical.addWidget(self.visualizar)
        if botoes:
            linha = QHBoxLayout()
            for b in botoes:
                linha.addWidget(b)
            linha.addStretch(1)
            vertical.addLayout(linha)

    def definir_estilos(self, estilos: Estilos, fonte_padrao: QFont, assinatura=None) -> None:
        if assinatura is not None and assinatura == self._assinatura:
            return
        self._assinatura = assinatura
        self._estilos = estilos
        self._fonte_padrao = QFont(fonte_padrao)
        self._encher()

    def _encher(self) -> None:
        self.lista.clear()
        estilos = self._estilos
        if estilos is None:
            return
        for e in estilos.visiveis():
            marca = "a" if e.tipo == "caractere" else "¶"
            item = QListWidgetItem(f"{e.nome_exibido()}    {marca}")
            item.setData(Qt.ItemDataRole.UserRole, e.id)
            item.setToolTip(f"{e.nome_exibido()} (estilo de "
                            f"{'caractere' if e.tipo == 'caractere' else 'parágrafo'})")
            if self.visualizar.isChecked():
                car = (estilos.base_de_caractere(None, e.id) if e.tipo == "caractere"
                       else estilos.resolver_paragrafo(e.id)[1])
                fonte = QFont(self._fonte_padrao)
                if car.get("fonte"):
                    fonte.setFamilies([car["fonte"]])
                pontos = (car.get("tamanho_meio_pt") or 22) / 2
                fonte.setPointSizeF(min(PONTOS_MAXIMOS, pontos))
                fonte.setBold(bool(car.get("negrito")))
                fonte.setItalic(bool(car.get("italico")))
                fonte.setUnderline(bool(car.get("sublinhado")))
                item.setFont(fonte)
                if car.get("cor_hex"):
                    item.setForeground(QColor("#" + car["cor_hex"]))
            self.lista.addItem(item)
        self.marcar(self._atual)

    def ids(self) -> list[str]:
        return [self.lista.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lista.count())]

    def marcar(self, sid: str | None) -> None:
        self._atual = sid
        self.lista.blockSignals(True)
        self.lista.clearSelection()
        for i in range(self.lista.count()):
            item = self.lista.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == sid:
                item.setSelected(True)
                self.lista.setCurrentItem(item)
                self.lista.scrollToItem(item)
                break
        self.lista.blockSignals(False)

    def atual(self) -> str | None:
        item = self.lista.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None and item.isSelected() else None

    def _clicado(self, item: QListWidgetItem) -> None:
        self.escolhido.emit(item.data(Qt.ItemDataRole.UserRole))
