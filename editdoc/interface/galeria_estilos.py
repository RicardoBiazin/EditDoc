"""Galeria de estilos (M6): miniaturas na Pagina Inicial, como a do Word.

Cada miniatura e' um botao com a amostra "AaBbCcDd" desenhada com a aparencia do estilo
(fonte, tamanho limitado a caber, negrito, italico, sublinhado e cor) e o nome embaixo.
O estilo do cursor fica marcado. A galeria mostra quantas miniaturas couberem
(`mostrar`); as setas rolam e o botao de expandir abre todas, com os comandos
"Criar um estilo", "Limpar toda a formatacao" e o painel de estilos.

Recolhida (faixa estreita), vira o botao "Estilos" com um menu: os mesmos estilos e os
mesmos comandos (`GrupoGaleria`).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLabel, QMenu,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget, QWidgetAction)

from editdoc.modelo.estilos import Estilo, Estilos

#: Tamanho da miniatura, em px logicos.
LARGURA_MINIATURA = 72
ALTURA_MINIATURA = 50
ESPACO = 2
LARGURA_SETAS = 18
AMOSTRA = "AaBbCcDd"
#: Corpo maximo da amostra: um Titulo de 28 pt nao cabe na miniatura.
PONTOS_MAXIMOS = 14.0
PONTOS_MINIMOS = 7.0


def miniatura(estilo: Estilo, estilos: Estilos, fonte_padrao: QFont,
              largura: int = LARGURA_MINIATURA, altura: int = ALTURA_MINIATURA,
              dpr: float = 1.0) -> QPixmap:
    """A amostra do estilo e o nome, num pixmap. Funcao pura de pintura: testavel sem janela."""
    if estilo.tipo == "caractere":
        car = estilos.base_de_caractere(None, estilo.id)
    else:
        _par, car = estilos.resolver_paragrafo(estilo.id)
    pm = QPixmap(round(largura * dpr), round(altura * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(QColor(255, 255, 255))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    fonte = QFont(fonte_padrao)
    if car.get("fonte"):
        fonte.setFamilies([car["fonte"]])
    pontos = (car.get("tamanho_meio_pt") or round(fonte_padrao.pointSizeF() * 2) or 22) / 2
    # Escala da miniatura: 11 pt vira ~9 pt; o maior fica no teto, como no Word.
    fonte.setPointSizeF(min(PONTOS_MAXIMOS, max(PONTOS_MINIMOS, pontos * 0.8)))
    fonte.setBold(bool(car.get("negrito")))
    fonte.setItalic(bool(car.get("italico")))
    fonte.setUnderline(bool(car.get("sublinhado")))
    fonte.setStrikeOut(bool(car.get("tachado")))
    p.setFont(fonte)
    cor = QColor("#" + car["cor_hex"]) if car.get("cor_hex") else QColor(0, 0, 0)
    p.setPen(cor)
    area = QRectF(3, 2, largura - 6, altura - 18)
    p.drawText(area, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), AMOSTRA)
    rotulo = QFont(QApplication.font())
    rotulo.setPointSizeF(7.5)
    p.setFont(rotulo)
    p.setPen(QColor(0x40, 0x40, 0x40))
    nome = p.fontMetrics().elidedText(estilo.nome_exibido(), Qt.TextElideMode.ElideRight,
                                      largura - 6)
    p.drawText(QRectF(3, altura - 16, largura - 6, 14),
               int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), nome)
    p.end()
    return pm


class BotaoEstilo(QToolButton):
    """Uma miniatura: clique aplica; menu de contexto atualiza ou modifica o estilo."""

    def __init__(self, sid: str, nome: str, pixmap: QPixmap, galeria: "GaleriaEstilos") -> None:
        super().__init__()
        self.sid = sid
        self._galeria = galeria
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(LARGURA_MINIATURA, ALTURA_MINIATURA))
        self.setToolTip(nome)
        self.setAccessibleName(f"Estilo {nome}")
        self.setAccessibleDescription(f"Aplicar o estilo {nome}; menu de contexto para "
                                      "atualizar ou modificar")
        self.clicked.connect(lambda: galeria.escolhido.emit(self.sid))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def _menu(self, _ponto) -> None:
        menu = QMenu(self)
        nome = self.toolTip()
        menu.addAction(f"Atualizar {nome} para corresponder à seleção",
                       lambda: self._galeria.pedido_atualizar.emit(self.sid))
        menu.addAction("Modificar...", lambda: self._galeria.pedido_modificar.emit(self.sid))
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))


def _seta(texto: str, dica: str) -> QToolButton:
    b = QToolButton()
    b.setText(texto)
    b.setToolTip(dica)
    b.setAccessibleName(dica)
    b.setAutoRaise(True)
    b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    fonte = b.font()
    fonte.setPointSizeF(max(6.0, fonte.pointSizeF() - 2))
    b.setFont(fonte)
    return b


_MEDIDAS: dict[str, int] = {}


def _medidas() -> tuple[int, int]:
    """(largura de uma miniatura, largura da coluna de setas), medidas no estilo da tela."""
    if not _MEDIDAS:
        b = QToolButton()
        b.setAutoRaise(True)
        b.setCheckable(True)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        b.setIconSize(QSize(LARGURA_MINIATURA, ALTURA_MINIATURA))
        b.setIcon(QIcon(QPixmap(LARGURA_MINIATURA, ALTURA_MINIATURA)))
        _MEDIDAS["botao"] = b.sizeHint().width()
        _MEDIDAS["seta"] = max(_seta(t, "").sizeHint().width() for t in ("▲", "▼", "▾"))
        b.deleteLater()
    return _MEDIDAS["botao"], _MEDIDAS["seta"]


class GaleriaEstilos(QWidget):
    escolhido = Signal(str)
    pedido_atualizar = Signal(str)
    pedido_modificar = Signal(str)

    def __init__(self, acoes_extras: list[QAction] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._acoes_extras = list(acoes_extras or [])
        self._botoes: list[BotaoEstilo] = []
        self._itens: list[tuple[str, str, QPixmap]] = []
        self._inicio = 0
        self._quantos = 5
        self._atual: str | None = None
        self._assinatura = None
        linha = QHBoxLayout(self)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(0)
        self._area = QWidget()
        self._linha_botoes = QHBoxLayout(self._area)
        self._linha_botoes.setContentsMargins(0, 0, 0, 0)
        self._linha_botoes.setSpacing(ESPACO)
        linha.addWidget(self._area)
        setas = QVBoxLayout()
        setas.setContentsMargins(0, 0, 0, 0)
        setas.setSpacing(0)
        self._acima = _seta("▲", "Linha anterior de estilos")
        self._abaixo = _seta("▼", "Próxima linha de estilos")
        self._mais = _seta("▾", "Mais estilos")
        self._acima.clicked.connect(lambda: self.rolar(-1))
        self._abaixo.clicked.connect(lambda: self.rolar(1))
        self._mais.clicked.connect(self.abrir_tudo)
        for b in (self._acima, self._abaixo, self._mais):
            setas.addWidget(b)
        linha.addLayout(setas)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._menu_tudo: QMenu | None = None

    # -- conteudo -------------------------------------------------------------
    def definir_estilos(self, estilos: Estilos, fonte_padrao: QFont, assinatura=None) -> None:
        """Refaz as miniaturas dos estilos rapidos. Sem mudanca de catalogo, nao faz nada."""
        if assinatura is not None and assinatura == self._assinatura:
            return
        self._assinatura = assinatura
        dpr = self.devicePixelRatioF() or 1.0
        self._itens = [(e.id, e.nome_exibido(), miniatura(e, estilos, fonte_padrao, dpr=dpr))
                       for e in estilos.rapidos()]
        for b in self._botoes:
            self._linha_botoes.removeWidget(b)
            b.deleteLater()
        self._botoes = [BotaoEstilo(sid, nome, pm, self) for sid, nome, pm in self._itens]
        for b in self._botoes:
            self._linha_botoes.addWidget(b)
        self._menu_tudo = None
        self._inicio = min(self._inicio, max(0, len(self._botoes) - 1))
        self._aplicar_janela()
        self.marcar(self._atual)

    def ids(self) -> list[str]:
        return [sid for sid, _n, _p in self._itens]

    def quantidade(self) -> int:
        return len(self._itens)

    # -- tamanho e rolagem ----------------------------------------------------
    @staticmethod
    def largura_para(n: int) -> int:
        """Largura da galeria com `n` miniaturas visiveis (n >= 1)."""
        botao, seta = _medidas()
        return n * botao + (n - 1) * ESPACO + seta

    def mostrar(self, n: int) -> None:
        self._quantos = max(1, int(n))
        self._aplicar_janela()

    def visiveis(self) -> list[str]:
        return [b.sid for b in self._botoes if not b.isHidden()]

    def rolar(self, linhas: int) -> None:
        if not self._botoes:
            return
        passo = self._quantos
        maximo = max(0, len(self._botoes) - self._quantos)
        self._inicio = min(max(0, self._inicio + linhas * passo), maximo)
        self._aplicar_janela()

    def _aplicar_janela(self) -> None:
        n = self._quantos
        maximo = max(0, len(self._botoes) - n)
        self._inicio = min(self._inicio, maximo)
        for i, b in enumerate(self._botoes):
            b.setVisible(self._inicio <= i < self._inicio + n)
        self._acima.setEnabled(self._inicio > 0)
        self._abaixo.setEnabled(self._inicio < maximo)
        botao, _seta_l = _medidas()
        self._area.setFixedWidth(max(0, n * botao + (n - 1) * ESPACO))
        self.setFixedWidth(self.largura_para(n))
        self.updateGeometry()

    # -- estilo atual ---------------------------------------------------------
    def marcar(self, sid: str | None) -> None:
        """Marca a miniatura do estilo do cursor e rola ate' ela, se estiver fora da vista."""
        self._atual = sid
        indice = None
        for i, b in enumerate(self._botoes):
            b.setChecked(b.sid == sid)
            if b.sid == sid:
                indice = i
        if indice is not None and not (self._inicio <= indice < self._inicio + self._quantos):
            self._inicio = (indice // self._quantos) * self._quantos
            self._aplicar_janela()

    def atual(self) -> str | None:
        """O estilo marcado (o do cursor), se estiver na galeria."""
        for b in self._botoes:
            if b.isChecked():
                return b.sid
        return None

    def botao(self, sid: str) -> BotaoEstilo | None:
        return next((b for b in self._botoes if b.sid == sid), None)

    # -- tudo -------------------------------------------------------------------
    def menu_tudo(self) -> QMenu:
        """O menu do botao de expandir: todas as miniaturas e os comandos de estilo."""
        if self._menu_tudo is None:
            menu = QMenu(self)
            grade = QWidget()
            g = QGridLayout(grade)
            g.setContentsMargins(4, 4, 4, 4)
            g.setSpacing(ESPACO)
            colunas = 5
            for i, (sid, nome, pm) in enumerate(self._itens):
                b = QToolButton()
                b.setIcon(QIcon(pm))
                b.setIconSize(QSize(LARGURA_MINIATURA, ALTURA_MINIATURA))
                b.setToolTip(nome)
                b.setAccessibleName(f"Estilo {nome}")
                b.setAutoRaise(True)
                b.setCheckable(True)
                b.setChecked(sid == self._atual)
                b.setProperty("sid", sid)
                b.clicked.connect(lambda _=False, s=sid, m=menu: (m.close(), self.escolhido.emit(s)))
                g.addWidget(b, i // colunas, i % colunas)
            acao = QWidgetAction(menu)
            acao.setDefaultWidget(grade)
            menu.addAction(acao)
            menu.addSeparator()
            for a in self._acoes_extras:
                menu.addAction(a)
            self._menu_tudo = menu
        else:
            for b in self._menu_tudo.findChildren(QToolButton):
                b.setChecked(b.property("sid") == self._atual)
        return self._menu_tudo

    def abrir_tudo(self) -> None:
        self.menu_tudo().popup(self.mapToGlobal(self.rect().bottomLeft()))


class GrupoGaleria(QWidget):
    """O grupo "Estilos" da faixa: a galeria, ou (recolhido) o botao com menu."""

    def __init__(self, galeria: GaleriaEstilos, acoes_extras: list[QAction]) -> None:
        super().__init__()
        self.galeria = galeria
        self._acoes_extras = list(acoes_extras)
        self._botao = QToolButton()
        self._botao.setText("Estilos ▾")
        self._botao.setToolTip("Estilos")
        self._botao.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._botao.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._botao.setAutoRaise(True)
        self._botao.setAccessibleName("Estilos")
        self._botao.setAccessibleDescription("Abre o menu com todos os estilos rápidos")
        self._botao.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._menu = QMenu(self._botao)
        self._menu.aboutToShow.connect(self._encher_menu)
        self._botao.setMenu(self._menu)
        self._titulo = QLabel("Estilos")
        self._titulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._titulo.setStyleSheet("font-size: 8pt;")
        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        linha.addWidget(galeria)
        linha.addWidget(self._botao)
        vertical = QVBoxLayout(self)
        vertical.setContentsMargins(6, 2, 6, 0)
        vertical.setSpacing(0)
        vertical.addLayout(linha)
        vertical.addWidget(self._titulo)
        self._n = 5
        self.definir(5)

    def _encher_menu(self) -> None:
        self._menu.clear()
        atual = self.galeria._atual
        for sid, nome, pm in self.galeria._itens:
            acao = self._menu.addAction(QIcon(pm), nome)
            acao.setCheckable(True)
            acao.setChecked(sid == atual)
            acao.triggered.connect(lambda _=False, s=sid: self.galeria.escolhido.emit(s))
        self._menu.addSeparator()
        for a in self._acoes_extras:
            self._menu.addAction(a)

    def menu_recolhido(self) -> QMenu:
        self._encher_menu()
        return self._menu

    def largura(self, n: int) -> int:
        """Largura do grupo com n miniaturas (0 = recolhido no botao)."""
        if n <= 0:
            conteudo = self._botao.sizeHint().width()
        else:
            conteudo = GaleriaEstilos.largura_para(n)
        return max(self._titulo.sizeHint().width(), conteudo) + 12

    def definir(self, n: int) -> None:
        self._n = max(0, int(n))
        self.galeria.setVisible(self._n > 0)
        self._botao.setVisible(self._n == 0)
        if self._n > 0:
            self.galeria.mostrar(self._n)

    def miniaturas(self) -> int:
        return self._n
