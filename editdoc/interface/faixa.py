"""Faixa de opcoes: aba, grupos de botoes e recolhimento responsivo.

Cada grupo tem dois estados. Expandido: os botoes na linha. Recolhido: um botao
com menu, que oferece os mesmos comandos. Quando a janela estreita, os grupos
recolhem na ordem de prioridade (planejamento.recolher_grupos) ate caber. A
combinacao de fonte e tamanho nunca recolhe: e' a parte que o usuario mais usa.

Os botoes da faixa usam rotulos curtos. O texto completo do comando continua
no menu e na dica (tooltip). Botao nao usa setDefaultAction, porque o Qt copia
o texto da acao para o botao e nao deixa encurtar: cada botao sincroniza com a
acao por sinal.

Abas: Pagina Inicial, Inserir (M4: tabela e imagem; M5: cabecalho, rodape e numero
de pagina) e Layout (M3). A aba "Cabeçalho e Rodapé" (M5) so' aparece durante a
edicao do cabecalho, como a aba contextual do Word. Dois estados por grupo. O estado intermediario, com botoes menores em tres linhas, e as abas
contextuais (Layout da Tabela, Formato da Imagem) entram no M6; ate' la os
comandos de tabela ficam na aba Inserir e no menu de contexto.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QDoubleValidator
from PySide6.QtWidgets import (QComboBox, QFontComboBox, QFrame, QHBoxLayout, QLabel,
                               QMenu, QStackedWidget, QTabBar, QToolButton, QVBoxLayout,
                               QWidget, QWidgetAction)

from editdoc.edicao import formatacao, tabelas
from editdoc.interface.comandos import (FORMATO_DAS_ACOES, MARGENS_DAS_ACOES, PAPEL_DAS_ACOES,
                                        Comandos)
from editdoc.interface.planejamento import recolher_grupos
from editdoc.interface.seletor_grade import SeletorDeGrade

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
    "selecionar_tudo": "Selecionar", "quebra_pagina": "Quebra",
    "excluir_tabela": "Excluir tabela", "inserir_imagem": "Imagem",
    "tamanho_imagem": "Tamanho da imagem",
    "primeira_diferente": "Primeira página diferente",
    "pares_impares": "Pares e ímpares diferentes",
    "ir_cabecalho": "Ir para o cabeçalho", "ir_rodape": "Ir para o rodapé",
    "fechar_cabecalho": "Fechar cabeçalho e rodapé",
}

#: Nome da aba contextual do cabecalho e do rodape.
ABA_CABECALHO = "Cabeçalho e Rodapé"


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


def _menu_numero_de_pagina(comandos: Comandos) -> QToolButton:
    """Botao "Número de Página" com os submenus de posicao, campo no cursor e formato."""
    c = comandos
    botao = QToolButton()
    botao.setText("Número de Página ▾")
    botao.setToolTip("Número de página no cabeçalho ou no rodapé")
    botao.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    botao.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    botao.setAutoRaise(True)
    botao.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    menu = QMenu(botao)
    topo = menu.addMenu("Início da página")
    for id_ in ("numero_topo_esquerda", "numero_topo_centro", "numero_topo_direita"):
        topo.addAction(c.acao(id_))
    fim = menu.addMenu("Fim da página")
    for id_ in ("numero_rodape_esquerda", "numero_rodape_centro", "numero_rodape_direita",
                "numero_x_de_y"):
        fim.addAction(c.acao(id_))
    menu.addSeparator()
    menu.addAction(c.acao("campo_pagina"))
    menu.addAction(c.acao("campo_total"))
    menu.addSeparator()
    formato = menu.addMenu("Formato do número")
    for id_ in FORMATO_DAS_ACOES:
        formato.addAction(c.acao(id_))
    menu.addAction(c.acao("numero_inicial"))
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
    def __init__(self, comandos: Comandos, editor, botao_arquivo: QWidget | None = None) -> None:
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

        # Aba Layout: papel, orientacao, margens e quebra. Fica em outra aba, e nao no
        # grupo da Pagina Inicial, porque 298 px de grupo novo empurravam o recolhimento
        # da faixa (medido: a Fonte passava a recolher em 820 px).
        layout_linha = _linha([
            _menu("Tamanho", [c.acao(i) for i in PAPEL_DAS_ACOES]),
            _menu("Orientação", [c.acao("retrato"), c.acao("paisagem")]),
            _menu("Margens", [c.acao(i) for i in MARGENS_DAS_ACOES]),
            _botao(c, "quebra_pagina"),
        ])
        layout_linha.layout().setContentsMargins(MARGEM_FAIXA, 0, MARGEM_FAIXA, 0)

        # Aba Inserir (M4): tabela (grade de escolha ou dialogo), comandos de tabela e imagem.
        self.seletor_grade = SeletorDeGrade()
        self.seletor_grade.escolhido.connect(self._grade_escolhida)
        self._botao_tabela = QToolButton()
        self._botao_tabela.setText("Tabela ▾")
        self._botao_tabela.setToolTip("Inserir tabela")
        self._botao_tabela.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._botao_tabela.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._botao_tabela.setAutoRaise(True)
        self._botao_tabela.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.menu_tabela = QMenu(self._botao_tabela)
        grade_acao = QWidgetAction(self.menu_tabela)
        grade_acao.setDefaultWidget(self.seletor_grade)
        self.menu_tabela.addAction(grade_acao)
        self.menu_tabela.addAction(c.acao("inserir_tabela"))
        self._botao_tabela.setMenu(self.menu_tabela)
        inserir_linha = _linha([
            self._botao_tabela,
            _menu("Linhas e colunas", [c.acao(i) for i in (
                "inserir_linha_acima", "inserir_linha_abaixo", "inserir_coluna_esquerda",
                "inserir_coluna_direita", "excluir_linha", "excluir_coluna")]),
            _menu("Mesclar", [c.acao("mesclar_celulas"), c.acao("dividir_celula")]),
            _botao(c, "excluir_tabela"),
            _botao(c, "inserir_imagem"),
            _botao(c, "tamanho_imagem"),
            _menu("Cabeçalho", [c.acao("editar_cabecalho"), c.acao("remover_cabecalho")]),
            _menu("Rodapé", [c.acao("editar_rodape"), c.acao("remover_rodape")]),
            _menu_numero_de_pagina(c),
        ])
        inserir_linha.layout().addStretch(1)
        # Aba contextual do cabecalho e do rodape (M5): so' aparece na edicao.
        cabecalho_linha = _linha([
            _menu_numero_de_pagina(c),
            _botao(c, "primeira_diferente"),
            _botao(c, "pares_impares"),
            _botao(c, "ir_cabecalho"),
            _botao(c, "ir_rodape"),
            _botao(c, "fechar_cabecalho"),
        ])
        cabecalho_linha.layout().addStretch(1)
        cabecalho_linha.layout().setContentsMargins(MARGEM_FAIXA, 0, MARGEM_FAIXA, 0)
        inserir_linha.layout().setContentsMargins(MARGEM_FAIXA, 0, MARGEM_FAIXA, 0)

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        if botao_arquivo is not None:
            topo.addWidget(botao_arquivo)
        topo.addWidget(_botao(c, "desfazer"))
        topo.addWidget(_botao(c, "refazer"))
        self._abas = QTabBar()
        self._abas.addTab("Página Inicial")
        self._abas.addTab("Inserir")
        self._abas.addTab("Layout")
        self._abas.addTab(ABA_CABECALHO)
        self._abas.setTabVisible(3, False)
        self._abas.setExpanding(False)
        self._aba_antes_da_faixa = 0
        topo.addWidget(self._abas, 1)

        grupos = QHBoxLayout()
        grupos.setContentsMargins(0, 0, 0, 0)
        grupos.setSpacing(6)
        for grupo in self._grupos:
            grupos.addWidget(grupo)
        grupos.addStretch(1)
        pagina_inicial = QWidget()
        pagina_inicial.setLayout(grupos)

        self._conteudo = QStackedWidget()
        self._conteudo.addWidget(pagina_inicial)
        self._conteudo.addWidget(inserir_linha)
        self._conteudo.addWidget(layout_linha)
        self._conteudo.addWidget(cabecalho_linha)
        self._abas.currentChanged.connect(self._conteudo.setCurrentIndex)
        if hasattr(editor, "modoFaixaAlterado"):
            editor.modoFaixaAlterado.connect(self._modo_da_faixa)

        vertical = QVBoxLayout(self)
        vertical.setContentsMargins(MARGEM_FAIXA, 4, MARGEM_FAIXA, 4)
        vertical.setSpacing(2)
        vertical.addLayout(topo)
        vertical.addWidget(self._conteudo)

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

    def _modo_da_faixa(self) -> None:
        """Entrou na edicao do cabecalho: mostra a aba contextual; saiu: esconde e volta."""
        editando = self._editor.editando_faixa() is not None
        indice = 3
        if editando and not self._abas.isTabVisible(indice):
            self._aba_antes_da_faixa = self._abas.currentIndex()
            self._abas.setTabVisible(indice, True)
            self._abas.setCurrentIndex(indice)
        elif not editando and self._abas.isTabVisible(indice):
            if self._abas.currentIndex() == indice:
                self._abas.setCurrentIndex(self._aba_antes_da_faixa)
            self._abas.setTabVisible(indice, False)

    def aba_atual(self) -> str:
        return self._abas.tabText(self._abas.currentIndex())

    def abas_visiveis(self) -> list[str]:
        return [self._abas.tabText(i) for i in range(self._abas.count())
                if self._abas.isTabVisible(i)]

    def abrir_aba(self, nome: str) -> None:
        """Mostra a aba pelo nome ("Página Inicial", "Inserir", "Layout")."""
        for i in range(self._abas.count()):
            if self._abas.tabText(i) == nome:
                self._abas.setCurrentIndex(i)
                return

    # -- tabela ---------------------------------------------------------------

    def _grade_escolhida(self, linhas: int, colunas: int) -> None:
        self.menu_tabela.close()
        tabelas.inserir_tabela(self._editor, linhas, colunas)
        self._editor.setFocus()

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
