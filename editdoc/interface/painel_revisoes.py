"""Lista de revisoes (0.1.13): a aba "Revisões" do painel lateral, ao lado dos comentarios.

Uma linha por alteracao, na ordem do texto: o tipo (Inserção, Exclusão, Formatação...), o
autor, a data e o comeco do trecho. Clicar seleciona o trecho no documento; os botoes Aceitar e
Rejeitar valem para a linha escolhida. Tudo com nome para o leitor de tela. O texto da linha e'
texto puro (o trecho vem do arquivo, nunca e' marcacao).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from editdoc.modelo.comentarios import data_para_tela

#: Quantas linhas no maximo (documento com muitas revisoes: o resto pela navegacao).
LIMITE_DE_LINHAS = 5000


class PainelRevisoes(QWidget):
    """Sinais com o indice da revisao na lista que a janela passou em `atualizar`."""

    selecionado = Signal(int)
    aceitar = Signal(int)
    rejeitar = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setAccessibleName("Painel de revisões")
        self._resumo = QLabel("Nenhuma alteração no documento.")
        self._resumo.setWordWrap(True)
        self.lista = QListWidget()
        self.lista.setAccessibleName("Lista de alterações")
        self.lista.setWordWrap(True)
        self.lista.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.botao_aceitar = QPushButton("Aceitar")
        self.botao_aceitar.setAccessibleName("Aceitar a alteração escolhida")
        self.botao_rejeitar = QPushButton("Rejeitar")
        self.botao_rejeitar.setAccessibleName("Rejeitar a alteração escolhida")
        botoes = QHBoxLayout()
        botoes.addWidget(self.botao_aceitar)
        botoes.addWidget(self.botao_rejeitar)
        botoes.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._resumo)
        layout.addWidget(self.lista, 1)
        layout.addLayout(botoes)
        self.lista.currentRowChanged.connect(self._escolhida)
        self.lista.itemActivated.connect(lambda item: self.selecionado.emit(self.lista.row(item)))
        self.botao_aceitar.clicked.connect(lambda: self._botao(self.aceitar))
        self.botao_rejeitar.clicked.connect(lambda: self._botao(self.rejeitar))
        self._assinatura = None
        self._atualizando = False
        self._escolhida(-1)

    def _escolhida(self, linha: int) -> None:
        ok = linha >= 0
        self.botao_aceitar.setEnabled(ok)
        self.botao_rejeitar.setEnabled(ok)
        if ok and not self._atualizando:
            self.selecionado.emit(linha)

    def _botao(self, sinal) -> None:
        linha = self.lista.currentRow()
        if linha >= 0:
            sinal.emit(linha)

    def atualizar(self, itens: list, assinatura=None) -> None:
        """Refaz a lista (so' se a assinatura mudou)."""
        if assinatura is not None and assinatura == self._assinatura:
            return
        self._assinatura = assinatura
        self._atualizando = True
        try:
            atual = self.lista.currentRow()
            self.lista.clear()
            for item in itens[:LIMITE_DE_LINHAS]:
                data = data_para_tela(item.data) if item.data else ""
                autor = item.autor or "Autor desconhecido"
                topo = f"{item.nome_do_tipo()} — {autor}" + (f", {data}" if data else "")
                texto = item.texto.strip()
                linha = QListWidgetItem(f"{topo}\n{texto}" if texto else topo)
                linha.setData(Qt.ItemDataRole.AccessibleTextRole,
                              f"{item.nome_do_tipo()} de {autor}" + (f", {data}" if data else "")
                              + (f": {texto}" if texto else ""))
                self.lista.addItem(linha)
            n = len(itens)
            if n == 0:
                self._resumo.setText("Nenhuma alteração no documento.")
            else:
                autores = len({i.autor for i in itens})
                self._resumo.setText(f"{n} alteraç{'ão' if n == 1 else 'ões'} de {autores} "
                                     f"autor{'' if autores == 1 else 'es'}"
                                     + (" (as primeiras na lista)" if n > LIMITE_DE_LINHAS else ""))
            if 0 <= atual < self.lista.count():
                self.lista.setCurrentRow(atual)
        finally:
            self._atualizando = False
        linha = self.lista.currentRow()
        self.botao_aceitar.setEnabled(linha >= 0)
        self.botao_rejeitar.setEnabled(linha >= 0)

    def destacar(self, indice: int | None) -> None:
        """Marca a linha da revisao do cursor (sem mexer no documento)."""
        self._atualizando = True
        try:
            if indice is None or indice >= self.lista.count():
                self.lista.setCurrentRow(-1)
            else:
                self.lista.setCurrentRow(indice)
                self.lista.scrollToItem(self.lista.item(indice))
        finally:
            self._atualizando = False
        linha = self.lista.currentRow()
        self.botao_aceitar.setEnabled(linha >= 0)
        self.botao_rejeitar.setEnabled(linha >= 0)
