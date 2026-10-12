"""Painel de navegacao (M6): os titulos do documento, em arvore; clique leva ao titulo.

Titulo e' todo paragrafo com nivel de estrutura (o outlineLvl do estilo, como o Titulo 1,
ou o do proprio paragrafo). O nivel efetivo fica no formato do bloco
(ponte_qt/estilos.PROP_NIVEL): a lista sai do documento sem consultar o catalogo.

A lista e' refeita depois de uma pausa na digitacao (um QTimer), e o titulo em que o
cursor esta' fica marcado.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from editdoc.ponte_qt.estilos import nivel_do_bloco

#: Pausa depois da ultima tecla antes de refazer a lista.
ATRASO_MS = 300
#: Texto maximo de um titulo na lista.
TEXTO_MAXIMO = 120


def titulos_de(doc) -> list[tuple[int, int, str]]:
    """(nivel, posicao, texto) de cada titulo do documento, na ordem."""
    saida = []
    bloco = doc.firstBlock()
    while bloco.isValid():
        nivel = nivel_do_bloco(bloco)
        if nivel is not None:
            texto = bloco.text().replace(" ", " ").replace("￼", "").strip()
            if texto:
                saida.append((nivel, bloco.position(), texto[:TEXTO_MAXIMO]))
        bloco = bloco.next()
    return saida


class PainelNavegacao(QWidget):
    escolhido = Signal(int)

    def __init__(self, painel, parent=None) -> None:
        super().__init__(parent)
        self._painel = painel
        self.arvore = QTreeWidget()
        self.arvore.setHeaderHidden(True)
        self.arvore.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.arvore.itemClicked.connect(self._clicado)
        self._vazio = QLabel("Use os estilos de Título para que os títulos apareçam aqui.")
        self._vazio.setWordWrap(True)
        # Cor do texto da janela (M8): o cinza "mid" tinha contraste de 1,7 para 1.
        self._vazio.setWordWrap(True)
        vertical = QVBoxLayout(self)
        vertical.setContentsMargins(4, 4, 4, 4)
        vertical.addWidget(self.arvore, 1)
        vertical.addWidget(self._vazio)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(ATRASO_MS)
        self._timer.timeout.connect(self.atualizar)
        self._itens: list[tuple[int, QTreeWidgetItem]] = []
        painel.textChanged.connect(self._agendar)
        painel.cursorPositionChanged.connect(self.marcar_atual)
        self.atualizar()

    def _agendar(self) -> None:
        if self.isVisible():
            self._timer.start()

    def showEvent(self, ev) -> None:  # noqa: N802
        super().showEvent(ev)
        self.atualizar()

    def atualizar(self) -> None:
        """Refaz a arvore a partir dos titulos do corpo."""
        self.arvore.clear()
        self._itens = []
        pilha: list[tuple[int, QTreeWidgetItem]] = []
        for nivel, pos, texto in titulos_de(self._painel.documento_corpo()):
            while pilha and pilha[-1][0] >= nivel:
                pilha.pop()
            item = QTreeWidgetItem([texto])
            item.setData(0, Qt.ItemDataRole.UserRole, pos)
            item.setToolTip(0, texto)
            if pilha:
                pilha[-1][1].addChild(item)
            else:
                self.arvore.addTopLevelItem(item)
            pilha.append((nivel, item))
            self._itens.append((pos, item))
        self.arvore.expandAll()
        self._vazio.setVisible(not self._itens)
        self.marcar_atual()

    def textos(self) -> list[str]:
        return [item.text(0) for _pos, item in self._itens]

    def niveis(self) -> list[int]:
        """Profundidade de cada item na arvore (0 = no alto)."""
        saida = []
        for _pos, item in self._itens:
            d, pai = 0, item.parent()
            while pai is not None:
                d += 1
                pai = pai.parent()
            saida.append(d)
        return saida

    def marcar_atual(self) -> None:
        """Marca o ultimo titulo antes do cursor."""
        if not self._itens or not self.isVisible():
            return
        pos = self._painel.textCursor().position()
        atual = None
        for inicio, item in self._itens:
            if inicio <= pos:
                atual = item
            else:
                break
        self.arvore.blockSignals(True)
        self.arvore.setCurrentItem(atual) if atual is not None else self.arvore.clearSelection()
        self.arvore.blockSignals(False)

    def item_atual(self) -> str | None:
        item = self.arvore.currentItem()
        return item.text(0) if item is not None else None

    def ir_para(self, indice: int) -> None:
        """Como o clique no item `indice` (para os testes e para o teclado)."""
        self._clicado(self._itens[indice][1])

    def _clicado(self, item: QTreeWidgetItem, _coluna: int = 0) -> None:
        pos = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(pos, int):
            self.escolhido.emit(pos)
