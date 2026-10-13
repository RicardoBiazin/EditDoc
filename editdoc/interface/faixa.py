"""Faixa de opcoes: abas, grupos de botoes e recolhimento responsivo.

Cada grupo tem dois estados. Expandido: os botoes (em uma ou duas linhas). Recolhido:
um botao com menu, que oferece os mesmos comandos. Quando a janela estreita, os grupos
recolhem na ordem de prioridade (planejamento) ate caber. A combinacao de fonte e
tamanho nunca recolhe: e' a parte que o usuario mais usa.

Os botoes da faixa usam rotulos curtos. O texto completo do comando continua
no menu e na dica (tooltip). Botao nao usa setDefaultAction, porque o Qt copia
o texto da acao para o botao e nao deixa encurtar: cada botao sincroniza com a
acao por sinal.

Abas (M6): Pagina Inicial (Area de transferencia, Fonte, Paragrafo, Estilos e Edicao),
Inserir (Paginas, Tabelas, Ilustracoes, Links, Cabecalho e Rodape), Layout (Configurar Pagina e
Paragrafo: recuos e espacamento) e Exibir (Mostrar e Zoom). A aba "Cabeçalho e Rodapé"
(M5) so' aparece durante a edicao do cabecalho, como a aba contextual do Word. Cada aba
tem o seu recolhimento; a largura minima da faixa e' a da aba mais larga toda recolhida.

Galeria de estilos (M6): na Pagina Inicial, mostra quantas miniaturas couberem. Ela tem
preferencia sobre o grupo Edicao, como no Word: com a janela estreitando, Edicao
recolhe antes de a galeria encolher (planejamento.recolher_com_galeria). As abas
contextuais de tabela e de imagem ficam para depois: os comandos de tabela estao na aba
Inserir e no menu de contexto.

Acessibilidade (M8): cada botao tem nome para o leitor de tela (a dica do comando, nunca o
rotulo curto) e pega foco pelo teclado (Alt ou F10, setas: `dicas_teclas.py`), mas nao no
clique. O titulo dos grupos usa a cor do texto da janela: o cinza "mid" de antes tinha
contraste de 1,6 para 1 sobre o fundo claro.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QDoubleValidator
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFontComboBox, QFrame, QHBoxLayout,
                               QLabel, QMenu, QStackedWidget, QTabBar, QToolButton, QVBoxLayout,
                               QWidget, QWidgetAction)

from editdoc.edicao import formatacao, tabelas
from editdoc.interface.comandos import (FORMATO_DAS_ACOES, MARGENS_DAS_ACOES, PAPEL_DAS_ACOES,
                                        Comandos)
from editdoc.interface.galeria_estilos import GaleriaEstilos, GrupoGaleria
from editdoc.interface.planejamento import recolher_com_galeria, recolher_grupos
from editdoc.interface.seletor_grade import SeletorDeGrade
from editdoc.modelo.pagina import TWIPS_POR_CM

TAMANHOS = (8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72)
MARGEM_FAIXA = 8
_RESPIRO_GRUPO = 12
#: Miniaturas que a galeria quer mostrar antes de o grupo Edicao recolher.
MINIATURAS_PREFERIDAS = 5
MINIATURAS_MINIMAS = 2

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
    "tamanho_imagem": "Tamanho da imagem", "inserir_link": "Link", "remover_link": "Remover link",
    "primeira_diferente": "Primeira página diferente",
    "pares_impares": "Pares e ímpares diferentes",
    "ir_cabecalho": "Ir para o cabeçalho", "ir_rodape": "Ir para o rodapé",
    "fechar_cabecalho": "Fechar cabeçalho e rodapé",
    "painel_estilos": "Estilos", "mostrar_regua": "Régua",
    "painel_navegacao": "Navegação", "marcas_formatacao": "¶",
}

#: Nome da aba contextual do cabecalho e do rodape.
ABA_CABECALHO = "Cabeçalho e Rodapé"
ABAS = ("Página Inicial", "Inserir", "Layout", "Exibir", ABA_CABECALHO)


class BotaoAcao(QToolButton):
    """Botao da faixa ligado a um QAction: dispara a acao e reflete o estado dela."""

    def __init__(self, acao: QAction, rotulo: str | None = None) -> None:
        super().__init__()
        self._acao = acao
        self.setText(rotulo or acao.text())
        self.setToolTip(acao.toolTip())
        nome = acao.property("nome_acessivel") or acao.text()
        self.setAccessibleName(str(nome))
        self.setAccessibleDescription(acao.toolTip())
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setAutoRaise(True)
        # Botao da faixa nao rouba o foco no clique: o teclado continua no documento. Pelo
        # teclado (Alt, F10, setas) ele e' alcancado (M8).
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCheckable(acao.isCheckable())
        self.clicked.connect(acao.trigger)
        acao.changed.connect(self._sincronizar)
        self._sincronizar()

    def _sincronizar(self) -> None:
        self.setEnabled(self._acao.isEnabled())
        self.setChecked(self._acao.isChecked())


def _botao(comandos: Comandos, id_: str) -> BotaoAcao:
    return BotaoAcao(comandos.acao(id_), ROTULOS.get(id_))


#: Nome falado do botao de menu cujo rotulo e' abreviado.
_NOMES_DE_MENU = {"Transf.": "Área de transferência"}


def _menu(texto: str, acoes: list[QAction]) -> QToolButton:
    botao = QToolButton()
    botao.setText(f"{texto} ▾")
    botao.setAccessibleName(_NOMES_DE_MENU.get(texto, texto))
    botao.setAccessibleDescription("Abre um menu com: " + ", ".join(
        str(a.property("nome_acessivel") or a.text()) for a in acoes))
    botao.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    botao.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    botao.setAutoRaise(True)
    botao.setFocusPolicy(Qt.FocusPolicy.TabFocus)
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
    botao.setAccessibleName("Número de Página")
    botao.setAccessibleDescription("Abre o menu de número de página: posição, campo e formato")
    botao.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    botao.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    botao.setAutoRaise(True)
    botao.setFocusPolicy(Qt.FocusPolicy.TabFocus)
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


def _duas_linhas(cima: list[QWidget], baixo: list[QWidget]) -> QWidget:
    """Corpo de grupo em duas linhas (o estado intermediario do Word)."""
    corpo = QWidget()
    vertical = QVBoxLayout(corpo)
    vertical.setContentsMargins(0, 0, 0, 0)
    vertical.setSpacing(1)
    for widgets in (cima, baixo):
        linha = _linha(widgets)
        linha.layout().addStretch(1)
        vertical.addWidget(linha)
    return corpo


class GrupoFaixa(QWidget):
    """Um grupo com titulo. `fixo` nunca recolhe; `corpo` e `menu` se alternam.

    Sem `menu`, o grupo nunca recolhe.
    """

    def __init__(self, titulo: str, corpo: QWidget, menu: QWidget | None,
                 fixo: QWidget | None = None) -> None:
        super().__init__()
        self._titulo = QLabel(titulo)
        self._titulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._titulo.setStyleSheet("font-size: 8pt;")
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
        if menu is not None:
            linha.addWidget(menu)

        vertical = QVBoxLayout(self)
        vertical.setContentsMargins(_RESPIRO_GRUPO // 2, 2, _RESPIRO_GRUPO // 2, 0)
        vertical.setSpacing(0)
        vertical.addLayout(linha)
        vertical.addWidget(self._titulo)
        self.recolher(False)

    def titulo(self) -> str:
        return self._titulo.text()

    def largura(self, recolhido: bool) -> int:
        """Largura que o grupo ocupa no estado pedido, sem depender de qual esta visivel."""
        corpo = self._menu if (recolhido and self._menu is not None) else self._corpo
        fixo = self._fixo.sizeHint().width() + 4 if self._fixo is not None else 0
        conteudo = fixo + corpo.sizeHint().width()
        return max(self._titulo.sizeHint().width(), conteudo) + _RESPIRO_GRUPO

    def recolher(self, valor: bool) -> None:
        valor = bool(valor) and self._menu is not None
        self._recolhido = valor
        self._corpo.setVisible(not valor)
        if self._menu is not None:
            self._menu.setVisible(valor)

    def recolhido(self) -> bool:
        return self._recolhido


class LinhaDeGrupos(QWidget):
    """O conteudo de uma aba: grupos lado a lado e a ordem em que recolhem.

    `galeria`: o grupo de estilos (so' na Pagina Inicial), que encolhe junto.
    """

    def __init__(self, grupos: list[GrupoFaixa], prioridade: list[GrupoFaixa],
                 galeria: GrupoGaleria | None = None, posicao_galeria: int = 0) -> None:
        super().__init__()
        self.grupos = grupos
        self.prioridade = prioridade
        self.galeria = galeria
        linha = QHBoxLayout(self)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(6)
        for i, grupo in enumerate(grupos):
            if galeria is not None and i == posicao_galeria:
                linha.addWidget(galeria)
            linha.addWidget(grupo)
        if galeria is not None and posicao_galeria >= len(grupos):
            linha.addWidget(galeria)
        linha.addStretch(1)

    def _espacos(self) -> int:
        n = len(self.grupos) + (1 if self.galeria is not None else 0)
        return 6 * max(0, n - 1)

    def minimo(self) -> int:
        """Largura com tudo recolhido."""
        total = sum(g.largura(True) for g in self.grupos) + self._espacos()
        if self.galeria is not None:
            total += self.galeria.largura(0)
        return total

    def ajustar(self, disponivel: int) -> None:
        disponivel -= self._espacos()
        expandidos = [g.largura(False) for g in self.grupos]
        recolhidos = [g.largura(True) for g in self.grupos]
        ordem = [self.grupos.index(g) for g in self.prioridade]
        if self.galeria is None:
            estados = recolher_grupos(expandidos, recolhidos, ordem, disponivel)
        else:
            maximo = max(1, self.galeria.galeria.quantidade())
            larguras = [self.galeria.largura(n) for n in range(maximo + 1)]
            estados, n = recolher_com_galeria(expandidos, recolhidos, ordem, larguras,
                                              min(MINIATURAS_PREFERIDAS, maximo),
                                              min(MINIATURAS_MINIMAS, maximo), disponivel)
            self.galeria.definir(n)
        for grupo, recolhido in zip(self.grupos, estados):
            grupo.recolher(recolhido)

    def recolhidos(self) -> list[bool]:
        return [g.recolhido() for g in self.grupos]


def _campo_medida(sufixo: str, maximo: float, passo: float, minimo: float = 0.0) -> QDoubleSpinBox:
    campo = QDoubleSpinBox()
    campo.setRange(minimo, maximo)
    campo.setDecimals(1 if sufixo == " pt" else 2)
    campo.setSingleStep(passo)
    campo.setSuffix(sufixo)
    campo.setKeyboardTracking(False)
    campo.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
    return campo


class Faixa(QFrame):
    def __init__(self, comandos: Comandos, editor, botao_arquivo: QWidget | None = None) -> None:
        super().__init__()
        self._editor = editor
        self._comandos = comandos
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

        self._abas = QTabBar()
        self._conteudo = QStackedWidget()
        self._linhas: list[LinhaDeGrupos | QWidget] = []
        self._pagina_inicial = self._montar_pagina_inicial(c)
        self._inserir = self._montar_inserir(c)
        self._layout = self._montar_layout(c)
        self._exibir = self._montar_exibir(c)
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
        self._cabecalho = cabecalho_linha
        # Compatibilidade (M1): os grupos da Pagina Inicial.
        self._grupos = self._pagina_inicial.grupos
        self._prioridade = self._pagina_inicial.prioridade

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        #: Arquivo, Desfazer e Refazer: o que fica acima das abas (dicas A, 1 e 2).
        self.topo_widgets: list[QWidget] = []
        if botao_arquivo is not None:
            topo.addWidget(botao_arquivo)
            self.topo_widgets.append(botao_arquivo)
        for id_ in ("desfazer", "refazer"):
            botao = _botao(c, id_)
            topo.addWidget(botao)
            self.topo_widgets.append(botao)
        for nome in ABAS:
            self._abas.addTab(nome)
        self._abas.setTabVisible(ABAS.index(ABA_CABECALHO), False)
        self._abas.setExpanding(False)
        self._aba_antes_da_faixa = 0
        topo.addWidget(self._abas, 1)

        for widget in (self._pagina_inicial, self._inserir, self._layout, self._exibir,
                       self._cabecalho):
            self._conteudo.addWidget(widget)
        self._abas.currentChanged.connect(self._conteudo.setCurrentIndex)
        if hasattr(editor, "modoFaixaAlterado"):
            editor.modoFaixaAlterado.connect(self._modo_da_faixa)

        vertical = QVBoxLayout(self)
        vertical.setContentsMargins(MARGEM_FAIXA, 4, MARGEM_FAIXA, 4)
        vertical.setSpacing(2)
        vertical.addLayout(topo)
        vertical.addWidget(self._conteudo)

        # A largura minima e' a da aba mais larga com tudo recolhido: abaixo disso nada cabe.
        minimo = max(linha.minimo() for linha in self._linhas_responsivas()) + 2 * MARGEM_FAIXA
        self.setMinimumWidth(minimo)
        self.ajustar()

    # -- abas -----------------------------------------------------------------
    def _montar_pagina_inicial(self, c: Comandos) -> LinhaDeGrupos:
        fonte_fixo = _linha([self.familia, self.tamanho])
        fonte_corpo = _duas_linhas(
            [_botao(c, i) for i in ("aumentar_fonte", "diminuir_fonte", "limpar_formatacao")],
            [_botao(c, i) for i in ("negrito", "italico", "sublinhado", "tachado", "subscrito",
                                    "sobrescrito")])
        espacos = [c.acao(i) for i in ("espaco_1", "espaco_115", "espaco_15", "espaco_2")]
        paragrafo_corpo = _duas_linhas(
            [_botao(c, i) for i in ("marcadores", "numeracao", "diminuir_recuo",
                                    "aumentar_recuo")] + [_menu("Espaçamento", espacos)],
            [_botao(c, i) for i in ("alinhar_esquerda", "centralizar", "alinhar_direita",
                                    "justificar", "marcas_formatacao")])
        clipboard = GrupoFaixa(
            "Área de transferência", _linha([_botao(c, i) for i in ("colar", "recortar", "copiar")]),
            _menu("Transf.", [c.acao(i) for i in ("colar", "recortar", "copiar")]))
        fonte = GrupoFaixa(
            "Fonte", fonte_corpo,
            _menu("Fonte", [c.acao(i) for i in (
                "negrito", "italico", "sublinhado", "tachado", "subscrito", "sobrescrito",
                "aumentar_fonte", "diminuir_fonte", "limpar_formatacao", "limpar_caractere")]),
            fixo=fonte_fixo)
        paragrafo = GrupoFaixa(
            "Parágrafo", paragrafo_corpo,
            _menu("Parágrafo", [c.acao(i) for i in (
                "marcadores", "numeracao", "diminuir_recuo", "aumentar_recuo",
                "alinhar_esquerda", "centralizar", "alinhar_direita", "justificar",
                "espaco_1", "espaco_115", "espaco_15", "espaco_2", "marcas_formatacao")]))
        edicao = GrupoFaixa(
            "Edição", _linha([_botao(c, i) for i in ("localizar", "substituir", "selecionar_tudo")]),
            _menu("Edição", [c.acao(i) for i in ("localizar", "substituir", "selecionar_tudo")]))
        extras = [c.acao(i) for i in ("criar_estilo", "modificar_estilo", "atualizar_estilo",
                                      "limpar_formatacao", "painel_estilos")]
        self.galeria = GaleriaEstilos(extras)
        self.grupo_estilos = GrupoGaleria(self.galeria, extras)
        linha = LinhaDeGrupos([clipboard, fonte, paragrafo, edicao],
                              # O primeiro da lista e' o primeiro a recolher.
                              [edicao, clipboard, paragrafo, fonte],
                              galeria=self.grupo_estilos, posicao_galeria=3)
        self._linhas.append(linha)
        return linha

    def _montar_inserir(self, c: Comandos) -> LinhaDeGrupos:
        # Tabela: grade de escolha ou dialogo.
        self.seletor_grade = SeletorDeGrade()
        self.seletor_grade.escolhido.connect(self._grade_escolhida)
        self._botao_tabela = QToolButton()
        self._botao_tabela.setText("Tabela ▾")
        self._botao_tabela.setToolTip("Inserir tabela")
        self._botao_tabela.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._botao_tabela.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._botao_tabela.setAutoRaise(True)
        self._botao_tabela.setAccessibleName("Tabela")
        self._botao_tabela.setAccessibleDescription("Abre a grade para escolher o tamanho da "
                                                    "tabela, ou o diálogo Inserir tabela")
        self._botao_tabela.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.menu_tabela = QMenu(self._botao_tabela)
        grade_acao = QWidgetAction(self.menu_tabela)
        grade_acao.setDefaultWidget(self.seletor_grade)
        self.menu_tabela.addAction(grade_acao)
        self.menu_tabela.addAction(c.acao("inserir_tabela"))
        self._botao_tabela.setMenu(self.menu_tabela)
        linhas_colunas = ("inserir_linha_acima", "inserir_linha_abaixo", "inserir_coluna_esquerda",
                          "inserir_coluna_direita", "excluir_linha", "excluir_coluna")
        paginas = GrupoFaixa("Páginas", _linha([_botao(c, "quebra_pagina")]),
                             _menu("Páginas", [c.acao("quebra_pagina")]))
        tabela = GrupoFaixa(
            "Tabelas", _duas_linhas(
                [self._botao_tabela, _botao(c, "excluir_tabela")],
                [_menu("Linhas e colunas", [c.acao(i) for i in linhas_colunas]),
                 _menu("Mesclar", [c.acao("mesclar_celulas"), c.acao("dividir_celula")])]),
            _menu("Tabelas", [c.acao(i) for i in ("inserir_tabela", *linhas_colunas,
                                                  "mesclar_celulas", "dividir_celula",
                                                  "excluir_tabela")]))
        ilustracoes = GrupoFaixa(
            "Ilustrações", _duas_linhas([_botao(c, "inserir_imagem")], [_botao(c, "tamanho_imagem")]),
            _menu("Ilustrações", [c.acao("inserir_imagem"), c.acao("tamanho_imagem")]))
        links = GrupoFaixa(
            "Links", _duas_linhas([_botao(c, "inserir_link")], [_botao(c, "remover_link")]),
            _menu("Links", [c.acao("inserir_link"), c.acao("remover_link"), c.acao("abrir_link")]))
        cabecalho = GrupoFaixa(
            "Cabeçalho e Rodapé", _duas_linhas(
                [_menu("Cabeçalho", [c.acao("editar_cabecalho"), c.acao("remover_cabecalho")]),
                 _menu("Rodapé", [c.acao("editar_rodape"), c.acao("remover_rodape")])],
                [_menu_numero_de_pagina(c)]),
            _menu("Cabeçalho e Rodapé", [c.acao(i) for i in (
                "editar_cabecalho", "remover_cabecalho", "editar_rodape", "remover_rodape",
                "numero_topo_centro", "numero_rodape_centro", "numero_x_de_y")]))
        linha = LinhaDeGrupos([paginas, tabela, ilustracoes, links, cabecalho],
                              [ilustracoes, links, paginas, tabela, cabecalho])
        linha.layout().setContentsMargins(MARGEM_FAIXA, 0, MARGEM_FAIXA, 0)
        self._linhas.append(linha)
        return linha

    def _montar_layout(self, c: Comandos) -> LinhaDeGrupos:
        pagina = GrupoFaixa(
            "Configurar Página", _duas_linhas(
                [_menu("Margens", [c.acao(i) for i in MARGENS_DAS_ACOES]),
                 _menu("Orientação", [c.acao("retrato"), c.acao("paisagem")])],
                [_menu("Tamanho", [c.acao(i) for i in PAPEL_DAS_ACOES]), _botao(c, "quebra_pagina")]),
            _menu("Página", [c.acao(i) for i in (*MARGENS_DAS_ACOES, "retrato", "paisagem",
                                                 *PAPEL_DAS_ACOES, "quebra_pagina")]))
        # Paragrafo: recuos (cm) e espacamento (pt) do paragrafo do cursor.
        self.recuo_esquerdo = _campo_medida(" cm", 20.0, 0.25, -5.0)
        self.recuo_direito = _campo_medida(" cm", 20.0, 0.25, -5.0)
        self.espaco_antes = _campo_medida(" pt", 400.0, 6.0)
        self.espaco_depois = _campo_medida(" pt", 400.0, 6.0)
        for campo, dica in ((self.recuo_esquerdo, "Recuo à esquerda"),
                            (self.recuo_direito, "Recuo à direita"),
                            (self.espaco_antes, "Espaçamento antes do parágrafo"),
                            (self.espaco_depois, "Espaçamento depois do parágrafo")):
            campo.setToolTip(dica)
            campo.setAccessibleName(dica)
            campo.valueChanged.connect(self._paragrafo_alterado)
        paragrafo = GrupoFaixa(
            "Parágrafo", _duas_linhas(
                [QLabel("Recuar:"), QLabel("Esquerda"), self.recuo_esquerdo, QLabel("Direita"),
                 self.recuo_direito],
                [QLabel("Espaçar:"), QLabel("Antes"), self.espaco_antes, QLabel("Depois"),
                 self.espaco_depois]),
            None)
        linha = LinhaDeGrupos([pagina, paragrafo], [pagina])
        linha.layout().setContentsMargins(MARGEM_FAIXA, 0, MARGEM_FAIXA, 0)
        self._linhas.append(linha)
        return linha

    def _montar_exibir(self, c: Comandos) -> LinhaDeGrupos:
        mostrar = GrupoFaixa(
            "Mostrar", _duas_linhas(
                [_botao(c, "mostrar_regua"), _botao(c, "painel_navegacao")],
                [_botao(c, "marcas_formatacao"), _botao(c, "painel_estilos")]),
            _menu("Mostrar", [c.acao(i) for i in ("mostrar_regua", "painel_navegacao",
                                                  "marcas_formatacao", "painel_estilos")]))
        zoom = GrupoFaixa(
            "Zoom", _duas_linhas(
                [_botao(c, "zoom_100"), _botao(c, "zoom_pagina"), _botao(c, "ampliar")],
                [_botao(c, "zoom_varias"), _botao(c, "zoom_largura"), _botao(c, "reduzir")]),
            _menu("Zoom", [c.acao(i) for i in ("zoom_100", "zoom_pagina", "zoom_varias",
                                               "zoom_largura", "ampliar", "reduzir")]))
        linha = LinhaDeGrupos([mostrar, zoom], [zoom, mostrar])
        linha.layout().setContentsMargins(MARGEM_FAIXA, 0, MARGEM_FAIXA, 0)
        self._linhas.append(linha)
        return linha

    def _linhas_responsivas(self) -> list[LinhaDeGrupos]:
        return [x for x in self._linhas if isinstance(x, LinhaDeGrupos)]

    # -- recolhimento -------------------------------------------------------
    def ajustar(self) -> None:
        disponivel = self.width() - 2 * MARGEM_FAIXA
        for linha in self._linhas_responsivas():
            margens = linha.layout().contentsMargins()
            linha.ajustar(disponivel - margens.left() - margens.right())

    def recolhidos(self) -> list[bool]:
        """Grupos da Pagina Inicial recolhidos (Area de transferencia, Fonte, Paragrafo, Edicao)."""
        return self._pagina_inicial.recolhidos()

    def recolhidos_da_aba(self, nome: str) -> list[bool]:
        for linha, aba in zip((self._pagina_inicial, self._inserir, self._layout, self._exibir),
                              ABAS):
            if aba == nome:
                return linha.recolhidos()
        return []

    def miniaturas_visiveis(self) -> int:
        """Quantas miniaturas a galeria mostra (0 = recolhida no botao Estilos)."""
        return self.grupo_estilos.miniaturas()

    def resizeEvent(self, evento) -> None:  # noqa: N802 - nome do Qt
        super().resizeEvent(evento)
        self.ajustar()

    def _modo_da_faixa(self) -> None:
        """Entrou na edicao do cabecalho: mostra a aba contextual; saiu: esconde e volta."""
        editando = self._editor.editando_faixa() is not None
        indice = ABAS.index(ABA_CABECALHO)
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
        """Mostra a aba pelo nome ("Página Inicial", "Inserir", "Layout", "Exibir")."""
        for i in range(self._abas.count()):
            if self._abas.tabText(i) == nome:
                self._abas.setCurrentIndex(i)
                return

    # -- layout: paragrafo ------------------------------------------------------
    def mostrar_paragrafo(self, esquerdo_tw: int, direito_tw: int, antes_tw: int,
                          depois_tw: int) -> None:
        """Valores do paragrafo do cursor nos campos (sem disparar a edicao)."""
        for campo, valor in ((self.recuo_esquerdo, esquerdo_tw / TWIPS_POR_CM),
                             (self.recuo_direito, direito_tw / TWIPS_POR_CM),
                             (self.espaco_antes, antes_tw / 20.0),
                             (self.espaco_depois, depois_tw / 20.0)):
            if abs(campo.value() - valor) > 1e-6:
                campo.blockSignals(True)
                campo.setValue(valor)
                campo.blockSignals(False)

    def _paragrafo_alterado(self, _valor=None) -> None:
        campo = self.sender()
        if campo is self.recuo_esquerdo:
            formatacao.definir_paragrafo(self._editor, esquerdo_tw=round(campo.value() * TWIPS_POR_CM))
        elif campo is self.recuo_direito:
            formatacao.definir_paragrafo(self._editor, direito_tw=round(campo.value() * TWIPS_POR_CM))
        elif campo is self.espaco_antes:
            formatacao.definir_paragrafo(self._editor, antes_tw=round(campo.value() * 20))
        elif campo is self.espaco_depois:
            formatacao.definir_paragrafo(self._editor, depois_tw=round(campo.value() * 20))

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
