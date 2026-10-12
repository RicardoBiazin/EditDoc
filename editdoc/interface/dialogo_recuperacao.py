"""Dialogo "Recuperação de documentos" (M8): as copias que sobraram de uma queda.

Mostrado na abertura do programa quando ha' copia orfa (e por Arquivo > Recuperar
documentos). Nao e' modal: o usuario pode trabalhar com ele aberto, como o painel do
Word. Cada copia pode ser aberta (vira uma janela com o documento alterado, sem
caminho: salvar pede o lugar), salva como .docx ou descartada. Fechar o dialogo
deixa as que sobraram para a proxima vez.

Quem executa e' o gerente de janelas (`acoes`): o dialogo so' mostra e repassa.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout, QWidget)

from editdoc import APP
from editdoc.recuperacao import Copia

TITULO = "Recuperação de documentos"


def descrever(copia: Copia) -> str:
    origem = copia.caminho_original or "documento que ainda não tinha sido salvo"
    return f"{copia.nome}  ({copia.hora_legivel()})\n{origem}"


class DialogoRecuperacao(QDialog):
    def __init__(self, copias: list[Copia], acoes: dict[str, Callable[[Copia], bool]],
                 pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self._acoes = acoes
        self.setWindowTitle(f"{TITULO} - {APP}")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setAccessibleName(TITULO)
        explicacao = QLabel(
            "O EditDoc foi fechado sem salvar estes documentos. As cópias abaixo são as "
            "últimas gravadas pela recuperação automática. Abra para continuar o trabalho, "
            "salve a cópia como um arquivo .docx ou descarte. As que ficarem na lista "
            "serão oferecidas de novo na próxima vez.")
        explicacao.setWordWrap(True)
        self.lista = QListWidget()
        self.lista.setAccessibleName("Cópias de recuperação")
        self.lista.setAccessibleDescription("Documentos que podem ser recuperados, do mais novo "
                                            "para o mais antigo")
        explicacao.setBuddy(self.lista)
        for copia in copias:
            item = QListWidgetItem(descrever(copia))
            item.setData(Qt.ItemDataRole.UserRole, copia)
            item.setToolTip(copia.caminho_original or copia.nome)
            self.lista.addItem(item)
        self.lista.itemDoubleClicked.connect(lambda _i: self._executar("abrir"))
        self.botao_abrir = QPushButton("&Abrir")
        self.botao_salvar = QPushButton("&Salvar como...")
        self.botao_descartar = QPushButton("&Descartar")
        self.botao_fechar = QPushButton("&Fechar")
        for botao, descricao in (
                (self.botao_abrir, "Abrir a cópia selecionada numa janela"),
                (self.botao_salvar, "Gravar a cópia selecionada como um arquivo .docx"),
                (self.botao_descartar, "Apagar a cópia selecionada"),
                (self.botao_fechar, "Fechar; as cópias que sobrarem ficam para a próxima vez")):
            botao.setAccessibleName(botao.text().replace("&", "").replace("...", ""))
            botao.setAccessibleDescription(descricao)
            botao.setToolTip(descricao)
        self.botao_abrir.clicked.connect(lambda: self._executar("abrir"))
        self.botao_salvar.clicked.connect(lambda: self._executar("salvar_como"))
        self.botao_descartar.clicked.connect(lambda: self._executar("descartar"))
        self.botao_fechar.clicked.connect(self.close)
        self.botao_abrir.setDefault(True)

        botoes = QHBoxLayout()
        for botao in (self.botao_abrir, self.botao_salvar, self.botao_descartar):
            botoes.addWidget(botao)
        botoes.addStretch(1)
        botoes.addWidget(self.botao_fechar)
        vertical = QVBoxLayout(self)
        vertical.addWidget(explicacao)
        vertical.addWidget(self.lista, 1)
        vertical.addLayout(botoes)
        self.resize(560, 320)
        if self.lista.count():
            self.lista.setCurrentRow(0)
        self.lista.setFocus()

    def copias(self) -> list[Copia]:
        return [self.lista.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lista.count())]

    def selecionar(self, indice: int) -> None:
        self.lista.setCurrentRow(indice)

    def _executar(self, acao: str) -> bool:
        item = self.lista.currentItem()
        if item is None:
            return False
        copia = item.data(Qt.ItemDataRole.UserRole)
        feito = bool(self._acoes[acao](copia))
        if feito:
            self.lista.takeItem(self.lista.row(item))
            if self.lista.count() == 0:
                self.close()
            else:
                self.lista.setCurrentRow(0)
        return feito

    def abrir(self) -> bool:
        return self._executar("abrir")

    def salvar_como(self) -> bool:
        return self._executar("salvar_como")

    def descartar(self) -> bool:
        return self._executar("descartar")
