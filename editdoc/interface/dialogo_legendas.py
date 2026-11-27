"""Referencias > Legendas (0.1.37): Inserir Legenda, Inserir Indice de Ilustracoes e Referencia
cruzada. Os dialogos so' perguntam; quem aplica e' `edicao/legendas.py`, `edicao/sumario.py` e
`edicao/referencias.py`, cada um num passo de desfazer.
"""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QLineEdit, QListWidget, QVBoxLayout)

from editdoc.edicao import referencias as ed_ref
from editdoc.modelo import legendas as mod

#: Posicao da legenda: (chave, texto). Tabela leva a legenda em cima, como no Word.
POSICOES = (("acima", "Acima do item selecionado"), ("abaixo", "Abaixo do item selecionado"))


def _botoes(dialogo: QDialog, ok: str) -> QDialogButtonBox:
    botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
    botoes.button(QDialogButtonBox.StandardButton.Ok).setText(ok)
    botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
    botoes.accepted.connect(dialogo.accept)
    botoes.rejected.connect(dialogo.reject)
    return botoes


class DialogoLegenda(QDialog):
    """Rotulo (editavel: um rotulo novo vale), posicao, texto e "sem o rotulo"."""

    def __init__(self, pai, rotulos: list[str], proximos: dict[str, int],
                 rotulo: str = "Figura", posicao: str | None = None) -> None:
        super().__init__(pai)
        self.setWindowTitle("Inserir Legenda")
        self._proximos = proximos
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.exemplo = QLabel()
        self.exemplo.setAccessibleName("Legenda que será inserida")
        form.addRow("&Legenda:", self.exemplo)
        self.rotulo = QComboBox()
        self.rotulo.setEditable(True)
        self.rotulo.setAccessibleName("Rótulo da legenda")
        self.rotulo.lineEdit().setMaxLength(mod.ROTULO_MAXIMO)
        self.rotulo.addItems(rotulos)
        form.addRow("&Rótulo:", self.rotulo)
        self.posicao = QComboBox()
        self.posicao.setAccessibleName("Posição da legenda")
        for chave, texto in POSICOES:
            self.posicao.addItem(texto, chave)
        form.addRow("&Posição:", self.posicao)
        self.texto = QLineEdit()
        self.texto.setAccessibleName("Texto da legenda")
        self.texto.setMaxLength(mod.TEXTO_MAXIMO)
        self.texto.setToolTip("O que vem depois do número. Sem pontuação no começo, entra \" – \".")
        form.addRow("&Texto depois do número:", self.texto)
        layout.addLayout(form)
        self.sem_rotulo = QCheckBox("&Excluir o rótulo da legenda")
        self.sem_rotulo.setAccessibleName("Excluir o rótulo da legenda")
        layout.addWidget(self.sem_rotulo)
        layout.addWidget(_botoes(self, "Inserir"))
        self.rotulo.setCurrentText(rotulo)
        self._posicao_escolhida = posicao is not None
        self.posicao.setCurrentIndex(0 if (posicao or self._padrao(rotulo)) == "acima" else 1)
        self.rotulo.currentTextChanged.connect(self._mudou_rotulo)
        self.texto.textChanged.connect(self._exemplo)
        self.sem_rotulo.toggled.connect(self._exemplo)
        self.posicao.activated.connect(self._escolheu_posicao)
        self._exemplo()

    @staticmethod
    def _padrao(rotulo: str) -> str:
        return "acima" if rotulo.lower() == "tabela" else "abaixo"

    def _escolheu_posicao(self, _i: int) -> None:
        self._posicao_escolhida = True

    def _mudou_rotulo(self, _texto: str) -> None:
        if not self._posicao_escolhida:
            self.posicao.setCurrentIndex(0 if self._padrao(self.rotulo.currentText()) == "acima"
                                         else 1)
        self._exemplo()

    def _exemplo(self, *_args) -> None:
        rotulo = mod.rotulo_valido(self.rotulo.currentText())
        n = self._proximos.get(rotulo.lower(), 1)
        inicio = "" if self.sem_rotulo.isChecked() else f"{rotulo} "
        self.exemplo.setText(f"{inicio}{n}{mod.texto_depois_do_numero(self.texto.text())}")

    def escolha(self) -> dict:
        return {"rotulo": mod.rotulo_valido(self.rotulo.currentText()),
                "posicao": self.posicao.currentData(), "texto": self.texto.text(),
                "com_rotulo": not self.sem_rotulo.isChecked()}


def pedir_legenda(pai, rotulos: list[str], proximos: dict[str, int], rotulo: str = "Figura",
                  posicao: str | None = None) -> dict | None:
    dialogo = DialogoLegenda(pai, rotulos, proximos, rotulo, posicao)
    try:
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialogo.escolha()
    finally:
        dialogo.deleteLater()


class DialogoIndiceDeFiguras(QDialog):
    """O rotulo das legendas que o indice lista."""

    def __init__(self, pai, rotulos: list[str]) -> None:
        super().__init__(pai)
        self.setWindowTitle("Inserir Índice de Ilustrações")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.rotulo = QComboBox()
        self.rotulo.setAccessibleName("Rótulo da legenda do índice")
        self.rotulo.addItems(rotulos)
        form.addRow("&Rótulo da legenda:", self.rotulo)
        layout.addLayout(form)
        layout.addWidget(_botoes(self, "Inserir"))

    def escolha(self) -> str:
        return self.rotulo.currentText()


def pedir_indice_de_figuras(pai, rotulos: list[str]) -> str | None:
    dialogo = DialogoIndiceDeFiguras(pai, rotulos)
    try:
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialogo.escolha()
    finally:
        dialogo.deleteLater()


class DialogoReferencia(QDialog):
    """Tipo, o que mostrar, o item e "como hiperlink"."""

    def __init__(self, pai, doc) -> None:
        super().__init__(pai)
        self.setWindowTitle("Referência cruzada")
        self._doc = doc
        self._alvos: list = []
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.tipo = QComboBox()
        self.tipo.setAccessibleName("Tipo de referência")
        for chave, texto in ed_ref.tipos(doc):
            self.tipo.addItem(texto, chave)
        form.addRow("&Tipo de referência:", self.tipo)
        self.mostrar = QComboBox()
        self.mostrar.setAccessibleName("Inserir referência para")
        form.addRow("Inserir referência &para:", self.mostrar)
        layout.addLayout(form)
        rotulo_itens = QLabel("Para qual &item:")
        layout.addWidget(rotulo_itens)
        self.itens = QListWidget()
        self.itens.setAccessibleName("Item da referência")
        rotulo_itens.setBuddy(self.itens)
        layout.addWidget(self.itens)
        self.hiperlink = QCheckBox("Inserir como &hiperlink")
        self.hiperlink.setAccessibleName("Inserir como hiperlink")
        self.hiperlink.setChecked(True)
        layout.addWidget(self.hiperlink)
        botoes = _botoes(self, "Inserir")
        self._ok = botoes.button(QDialogButtonBox.StandardButton.Ok)
        layout.addWidget(botoes)
        self.tipo.currentIndexChanged.connect(self._mudou_tipo)
        self.itens.currentRowChanged.connect(self._atualizar_ok)
        self.itens.itemDoubleClicked.connect(lambda _i: self.accept() if self._ok.isEnabled()
                                             else None)
        self._mudou_tipo()

    def _mudou_tipo(self, *_args) -> None:
        chave = self.tipo.currentData()
        self.mostrar.clear()
        self.itens.clear()
        self._alvos = []
        if chave is not None:
            for k, texto in ed_ref.opcoes_de(chave):
                self.mostrar.addItem(texto, k)
            self._alvos = ed_ref.alvos(self._doc, chave)
            self.itens.addItems([a.descricao for a in self._alvos])
            if self._alvos:
                self.itens.setCurrentRow(0)
        self._atualizar_ok()

    def _atualizar_ok(self, *_args) -> None:
        self._ok.setEnabled(self.itens.currentRow() >= 0 and self.mostrar.count() > 0)

    def escolha(self):
        i = self.itens.currentRow()
        if i < 0 or i >= len(self._alvos):
            return None
        return self._alvos[i], self.mostrar.currentData(), self.hiperlink.isChecked()


def pedir_referencia(pai, doc):
    dialogo = DialogoReferencia(pai, doc)
    try:
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialogo.escolha()
    finally:
        dialogo.deleteLater()
