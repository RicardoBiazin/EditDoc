"""Faixa de opcoes: aba, grupos de botoes e recolhimento responsivo.

Cada grupo tem dois estados. Expandido: os botoes na linha. Recolhido: um botao
com menu, que oferece os mesmos comandos. Quando a janela estreita, os grupos
recolhem na ordem de prioridade (planejamento.recolher_grupos) ate caber. A
combinacao de fonte e tamanho nunca recolhe: e' a parte que o usuario mais usa.

Os botoes da faixa usam rotulos curtos. O texto completo do comando continua
no menu e na dica (tooltip). Botao nao usa setDefaultAction, porque o Qt copia
o texto da acao para o botao e nao deixa encurtar: cada botao sincroniza com a
acao por sinal.

Limites do M1: uma aba (Pagina Inicial) e dois estados por grupo. O estado
intermediario, com botoes menores em tres linhas, e as abas contextuais entram
no M6.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QDoubleValidator
from PySide6.QtWidgets import (QComboBox, QFontComboBox, QFrame, QHBoxLayout, QLabel,
                               QMenu, QTabBar, QToolButton, QVBoxLayout, QWidget)

from editdoc.edicao import formatacao
from editdoc.interface.comandos import Comandos
from editdoc.interface.planejamento import recolher_grupos

TAMANHOS = (8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72)
MARGEM_FAIXA = 8
_RESPIRO_GRUPO = 12

#: Rotulo curto de cada botao. O que nao esta aqui usa o texto da acao.
ROTULOS = {
    "colar": "Colar", "recortar": "Recortar", "copiar": "Copiar",
    "negrito": "N", "italico": "I", "sublinhado": "S", "tachado": "Tachado",
    "subscrito": "X₂", "sobrescrito": "X²", "aumentar_fonte": "A▲",
    "diminuir_fonte": "A▼", "limpar_formatacao": "Limpar",
    "marcadores": "Marcadores", "numeracao": "Numeração",
    "diminuir_recuo": "◂ Recuo", "aumentar_recuo": "Recuo ▸",
    "alinhar_esquerda": "Esquerda", "centralizar": "Centro",
    "alinhar_direita": "Direita", "justificar": "Justificar",
    "localizar": "Localizar", "substituir": "Substituir",
    "selecionar_tudo": "Selecionar",
}


class BotaoAcao(QToolButton):
    """Botao da faixa ligado a um QAction: dispara a acao e reflete o estado dela."""

    def __init__(self, acao: QAction, rotulo: str | None = None) -> None:
        super().__init__()
        self._acao = acao
        self.setText(rotulo or acao.text())
        self.setToolTip(acao.toolTip())
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setAutoRaise(True)
        # Botao da faixa nao rouba o foco: o teclado continua no documento.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCheckable(acao.isCheckable())
        self.clicked.connect(acao.trigger)
        acao.changed.connect(self._sincronizar)
        self._sincronizar()

    def _sincronizar(self) -> None:
        self.setEnabled(self._acao.isEnabled())
        self.setChecked(self._acao.isChecked())


def _botao(comandos: Comandos, id_: str) -> BotaoAcao:
    return BotaoAcao(comandos.acao(id_), ROTULOS.get(id_))


def _menu(texto: str, acoes: list[QAction]) -> QToolButton:
    botao = QToolButton()
    botao.setText(f"{texto} ▾")
    botao.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    botao.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    botao.setAutoRaise(True)
    botao.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    menu = QMenu(botao)
    for acao in acoes:
        menu.addAction(acao)
    botao.setMenu(menu)
    return botao


def _linha(widgets: list[QWidget]) -> QWidget:
    corpo = QWidget()
    linha = QHBoxLayout(corpo)
    linha.setContentsMargins(0, 0, 0, 0)
    linha.setSpacing(2)
    for widget in widgets:
        linha.addWidget(widget)
    return corpo


class GrupoFaixa(QWidget):
    """Um grupo com titulo. `fixo` nunca recolhe; `corpo` e `menu` se alternam."""

    def __init__(self, titulo: str, corpo: QWidget, menu: QWidget,
                 fixo: QWidget | None = None) -> None:
        super().__init__()
        self._titulo = QLabel(titulo)
        self._titulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._titulo.setStyleSheet("color: palette(mid); font-size: 8pt;")
        self._corpo = corpo
        self._menu = menu
        self._fixo = fixo
        self._recolhido = False

        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(4)
        if fixo is not None:
            linha.addWidget(fixo)
        linha.addWidget(corpo)
        linha.addWidget(menu)

        vertical = QVBoxLayout(self)
        vertical.setContentsMargins(_RESPIRO_GRUPO // 2, 2, _RESPIRO_GRUPO // 2, 0)
        vertical.setSpacing(0)
        vertical.addLayout(linha)
        vertical.addWidget(self._titulo)
        self.recolher(False)

    def largura(self, recolhido: bool) -> int:
        """Largura que o grupo ocupa no estado pedido, sem depender de qual esta visivel."""
        corpo = self._menu if recolhido else self._corpo
        fixo = self._fixo.sizeHint().width() + 4 if self._fixo is not None else 0
        conteudo = fixo + corpo.sizeHint().width()
        return max(self._titulo.sizeHint().width(), conteudo) + _RESPIRO_GRUPO

    def recolher(self, valor: bool) -> None:
        self._recolhido = valor
        self._corpo.setVisible(not valor)
        self._menu.setVisible(valor)

    def recolhido(self) -> bool:
        return self._recolhido


class Faixa(QFrame):
    def __init__(self, comandos: Comandos, editor) -> None:
        super().__init__()
        self._editor = editor
        c = comandos
        self.setFrameShape(QFrame.Shape.NoFrame)

        # -- fonte: os dois controles ficam sempre visiveis
        self.familia = QFontComboBox()
        self.familia.setMaximumWidth(150)
        self.familia.currentFontChanged.connect(self._familia_escolhida)

        self.tamanho = QComboBox()
        self.tamanho.setEditable(True)
        self.tamanho.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.tamanho.addItems([f"{t:g}" for t in TAMANHOS])
        self.tamanho.setMaximumWidth(64)
        validador = QDoubleValidator(1.0, 400.0, 1)
        validador.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.tamanho.lineEdit().setValidator(validador)
        self.tamanho.activated.connect(self._tamanho_escolhido)
        self.tamanho.lineEdit().returnPressed.connect(self._tamanho_digitado)

        fonte_fixo = _linha([self.familia, self.tamanho])
        fonte_botoes = _linha([_botao(c, i) for i in (
            "negrito", "italico", "sublinhado", "tachado", "subscrito", "sobrescrito",
            "aumentar_fonte", "diminuir_fonte", "limpar_formatacao")])

        espacos = [c.acao(i) for i in ("espaco_1", "espaco_115", "espaco_15", "espaco_2")]
        paragrafo_botoes = _linha(
            [_botao(c, i) for i in (
                "marcadores", "numeracao", "diminuir_recuo", "aumentar_recuo",
                "alinhar_esquerda", "centralizar", "alinhar_direita", "justificar")]
            + [_menu("Espaçamento", espacos)])

        clipboard_botoes = _linha([_botao(c, i) for i in ("colar", "recortar", "copiar")])
        edicao_botoes = _linha([_botao(c, i) for i in (
            "localizar", "substituir", "selecionar_tudo")])

        clipboard = GrupoFaixa(
            "Área de transferência", clipboard_botoes,
            _menu("Transf.", [c.acao(i) for i in ("colar", "recortar", "copiar")]))
        fonte = GrupoFaixa(
            "Fonte", fonte_botoes,
            _menu("Fonte", [c.acao(i) for i in (
                "negrito", "italico", "sublinhado", "tachado", "subscrito", "sobrescrito",
                "aumentar_fonte", "diminuir_fonte", "limpar_formatacao")]),
            fixo=fonte_fixo)
        paragrafo = GrupoFaixa(
            "Parágrafo", paragrafo_botoes,
            _menu("Parágrafo", [c.acao(i) for i in (
                "marcadores", "numeracao", "diminuir_recuo", "aumentar_recuo",
                "alinhar_esquerda", "centralizar", "alinhar_direita", "justificar",
                "espaco_1", "espaco_115", "espaco_15", "espaco_2")]))
        edicao = GrupoFaixa(
            "Edição", edicao_botoes,
            _menu("Edição", [c.acao(i) for i in ("localizar", "substituir", "selecionar_tudo")]))

        self._grupos = [clipboard, fonte, paragrafo, edicao]
        # O primeiro da lista e' o primeiro a recolher.
        self._prioridade = [edicao, clipboard, paragrafo, fonte]

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        topo.addWidget(_botao(c, "desfazer"))
        topo.addWidget(_botao(c, "refazer"))
        abas = QTabBar()
        abas.addTab("Página Inicial")
        abas.setExpanding(False)
        topo.addWidget(abas, 1)

        grupos = QHBoxLayout()
        grupos.setContentsMargins(0, 0, 0, 0)
        grupos.setSpacing(6)
        for grupo in self._grupos:
            grupos.addWidget(grupo)
        grupos.addStretch(1)

        vertical = QVBoxLayout(self)
        vertical.setContentsMargins(MARGEM_FAIXA, 4, MARGEM_FAIXA, 4)
        vertical.setSpacing(2)
        vertical.addLayout(topo)
        vertical.addLayout(grupos)

        # A largura minima e' a de tudo recolhido: abaixo disso nada cabe.
        minimo = sum(g.largura(True) for g in self._grupos) + 2 * MARGEM_FAIXA
        self.setMinimumWidth(minimo)
        self.ajustar()

    # -- recolhimento -------------------------------------------------------

    def ajustar(self) -> None:
        disponivel = self.width() - 2 * MARGEM_FAIXA
        expandidos = [g.largura(False) for g in self._grupos]
        recolhidos = [g.largura(True) for g in self._grupos]
        ordem = [self._grupos.index(g) for g in self._prioridade]
        estados = recolher_grupos(expandidos, recolhidos, ordem, disponivel)
        for grupo, recolhido in zip(self._grupos, estados):
            grupo.recolher(recolhido)

    def recolhidos(self) -> list[bool]:
        return [g.recolhido() for g in self._grupos]

    def resizeEvent(self, evento) -> None:  # noqa: N802 - nome do Qt
        super().resizeEvent(evento)
        self.ajustar()

    # -- fonte --------------------------------------------------------------

    def _familia_escolhida(self, fonte) -> None:
        formatacao.definir_familia(self._editor, fonte.family())
        self._editor.setFocus()

    def _tamanho_escolhido(self, indice: int) -> None:
        self._aplicar_tamanho(self.tamanho.itemText(indice))

    def _tamanho_digitado(self) -> None:
        self._aplicar_tamanho(self.tamanho.currentText())

    def _aplicar_tamanho(self, texto: str) -> None:
        try:
            pontos = float(texto.replace(",", "."))
        except ValueError:
            return
        formatacao.definir_tamanho(self._editor, pontos)
        self._editor.setFocus()
