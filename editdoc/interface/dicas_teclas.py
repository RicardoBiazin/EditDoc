"""Teclado na faixa de opcoes (M8): Alt ou F10, dicas de tecla e setas, como no Word.

- Alt sozinho (apertar e soltar, sem outra tecla no meio) ou F10 leva o foco a' faixa e
  mostra as dicas de tecla: uma letra em cada aba e no botao Arquivo ("A"), e 1 e 2 no
  Desfazer e no Refazer. A letra de uma aba abre a aba e mostra as letras dos botoes
  dela; a letra de um botao executa o comando e devolve o foco ao documento. Uma dica de
  duas letras filtra as outras a' primeira letra digitada.
- Com o foco na faixa, as setas andam: esquerda e direita trocam de aba (na barra de
  abas) ou de botao; para baixo entra nos botoes; para cima, da primeira linha, volta as
  abas. Enter ou Espaco aperta o botao (ou abre o menu dele). Tab e Shift+Tab andam na
  ordem de leitura. Esc volta um nivel; no ultimo, devolve o foco ao documento.
- Clicar em qualquer lugar sai do modo.
- F6 e Shift+F6 andam entre as regioes da janela: documento, faixa, barra de busca,
  paineis de navegacao e de estilos (quando abertos) e o zoom da barra de status.

Os botoes da faixa nao pegam foco no clique (o teclado continua no documento), mas
pegam pelo teclado (`Qt.TabFocus`). O documento fica com o Tab dele: `focusNextPrevChild`
da VistaPaginas devolve False, entao Tab no texto continua sendo tabulacao.

AltGr (Ctrl+Alt no Windows) nao conta como Alt sozinho: o teclado ABNT2 usa AltGr para
digitar, e as dicas nao podem aparecer no meio de um "/" ou de um "°".
"""

from __future__ import annotations

import unicodedata

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox, QApplication, QComboBox,
                               QLabel, QLineEdit, QToolButton, QWidget)

from editdoc.interface import acessibilidade

Key = Qt.Key
#: Letras das abas, na ordem de faixa.ABAS (a contextual do cabecalho por ultimo).
LETRAS_DAS_ABAS = {"Página Inicial": "P", "Inserir": "N", "Layout": "L", "Exibir": "E",
                   "Cabeçalho e Rodapé": "H"}
_SETAS = (Key.Key_Left, Key.Key_Right, Key.Key_Up, Key.Key_Down)
#: Controles que usam as setas eles mesmos (mudar valor, mover o cursor do texto).
_USAM_SETAS = (QComboBox, QAbstractSpinBox, QLineEdit)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))


def atribuir_codigos(nomes: list[str], usados: set[str] | None = None) -> list[str]:
    """Um codigo por nome: a primeira letra livre do nome; sem letra livre, letra + digito.

    Funcao pura, para o teste. Codigos sempre em maiusculas, sem acento e unicos.
    """
    usados = set(usados or ())
    saida = []
    for nome in nomes:
        letras = [c for c in _sem_acento(nome).upper() if "A" <= c <= "Z"]
        codigo = next((c for c in letras if c not in usados), None)
        if codigo is None:
            base = letras[0] if letras else "X"
            n = 1
            while f"{base}{n}" in usados:
                n += 1
            codigo = f"{base}{n}"
        usados.add(codigo)
        saida.append(codigo)
    return saida


class TecladoFaixa(QObject):
    def __init__(self, janela) -> None:
        super().__init__(janela)
        self._janela = janela
        self._faixa = janela.faixa
        self._painel = janela.painel
        self.ativo = False
        #: "abas" (dicas das abas e do topo), "botoes" (dicas da aba aberta) ou None.
        self.nivel: str | None = None
        self._alt_sozinho = False
        self._digitado = ""
        self._dicas: list[tuple[str, QWidget, QLabel]] = []
        for widget in self._faixa.findChildren(QAbstractButton):
            acessibilidade.tornar_alcancavel(widget)
        app = QApplication.instance()
        app.installEventFilter(self)
        janela.destroyed.connect(lambda *_: self._desligar(app))

    def _desligar(self, app) -> None:
        try:
            app.removeEventFilter(self)
        except RuntimeError:
            pass

    # -- consulta ---------------------------------------------------------------------
    def focaveis(self) -> list[QWidget]:
        """Os controles da aba aberta que o teclado alcanca, na ordem de leitura."""
        pagina = self._faixa._conteudo.currentWidget()
        achados = []
        for w in pagina.findChildren(QWidget):
            if not isinstance(w, acessibilidade.INTERATIVOS):
                continue
            pai = w.parentWidget()
            if isinstance(pai, (QComboBox, QAbstractSpinBox)):
                continue  # a linha de edicao de dentro do combo
            if not (w.isVisible() and w.isEnabled()
                    and w.focusPolicy() & Qt.FocusPolicy.TabFocus):
                continue
            achados.append(w)
        return sorted(achados, key=self._ordem)

    def _ordem(self, w: QWidget) -> tuple:
        origem = w.mapTo(self._faixa, QPoint(0, 0))
        grupo = w
        while grupo is not None and grupo.parentWidget() is not self._faixa._conteudo.currentWidget():
            grupo = grupo.parentWidget()
        x_grupo = grupo.x() if grupo is not None else 0
        return (x_grupo, origem.y() // 12, origem.x())

    def do_topo(self) -> list[QWidget]:
        return [w for w in self._faixa.topo_widgets if w.isVisible()]

    def dicas_visiveis(self) -> dict[str, QWidget]:
        return {codigo: w for codigo, w, rotulo in self._dicas if rotulo.isVisible()}

    # -- entrar e sair ----------------------------------------------------------------
    def entrar(self) -> None:
        self.ativo = True
        self._faixa._abas.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._mostrar_abas()

    def sair(self, devolver: bool = True) -> None:
        self.ativo = False
        self._esconder()
        self.nivel = None
        if devolver:
            self._painel.setFocus(Qt.FocusReason.ShortcutFocusReason)

    # -- dicas ----------------------------------------------------------------------
    def _rotulo(self, codigo: str, alvo: QWidget) -> QLabel:
        rotulo = QLabel(codigo, self._janela)
        rotulo.setObjectName("dicaTecla")
        rotulo.setStyleSheet("#dicaTecla { background: #fff8d0; color: #000000; "
                             "border: 1px solid #5a5a5a; padding: 0 3px; font-size: 8pt; }")
        rotulo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        rotulo.adjustSize()
        centro = alvo.mapTo(self._janela, QPoint(alvo.width() // 2, alvo.height()))
        rotulo.move(centro.x() - rotulo.width() // 2, centro.y() - rotulo.height() // 2)
        rotulo.show()
        rotulo.raise_()
        return rotulo

    def _esconder(self) -> None:
        for _c, _w, rotulo in self._dicas:
            rotulo.hide()
            rotulo.deleteLater()
        self._dicas = []
        self._digitado = ""

    def _mostrar_abas(self) -> None:
        self._esconder()
        self.nivel = "abas"
        barra = self._faixa._abas
        for i in range(barra.count()):
            if not barra.isTabVisible(i):
                continue
            nome = barra.tabText(i)
            codigo = LETRAS_DAS_ABAS.get(nome)
            if codigo is None:
                continue
            ancora = _AncoraDeAba(barra, i)
            self._dicas.append((codigo, ancora, self._rotulo(codigo, ancora.widget_para_posicao())))
        for codigo, w in zip(("A", "1", "2"), self.do_topo()):
            self._dicas.append((codigo, w, self._rotulo(codigo, w)))

    def _mostrar_botoes(self) -> None:
        self._esconder()
        self.nivel = "botoes"
        alvos = self.focaveis()
        nomes = [acessibilidade.nome_acessivel(w) or "X" for w in alvos]
        for codigo, w in zip(atribuir_codigos(nomes), alvos):
            self._dicas.append((codigo, w, self._rotulo(codigo, w)))

    def _letra(self, texto: str) -> bool:
        """Uma letra digitada com as dicas na tela. True se ela era de alguma dica."""
        tecla = _sem_acento(texto).upper()
        if not tecla or not tecla.isalnum():
            return False
        digitado = self._digitado + tecla
        candidatos = [(c, w, r) for c, w, r in self._dicas if c.startswith(digitado)]
        if not candidatos:
            return False
        exato = next(((c, w) for c, w, _r in candidatos if c == digitado), None)
        if exato is not None:
            self._digitado = ""
            self._ativar(exato[1])
            return True
        self._digitado = digitado
        for c, _w, rotulo in self._dicas:
            rotulo.setVisible(c.startswith(digitado))
        return True

    def _ativar(self, alvo) -> None:
        if isinstance(alvo, _AncoraDeAba):
            self._faixa._abas.setCurrentIndex(alvo.indice)
            self._faixa._abas.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self._mostrar_botoes()
            return
        if isinstance(alvo, (QComboBox, QAbstractSpinBox, QLineEdit)):
            self.sair(devolver=False)
            alvo.setFocus(Qt.FocusReason.ShortcutFocusReason)
            return
        self.sair(devolver=True)
        apertar(alvo)

    # -- setas ------------------------------------------------------------------------
    def _navegar(self, foco: QWidget, tecla) -> bool:
        barra = self._faixa._abas
        alvos = self.focaveis()
        if foco is barra:
            if tecla == Key.Key_Down and alvos:
                self._ir(alvos[0])
                return True
            return False  # esquerda e direita: a propria barra troca de aba
        if foco not in alvos:
            topo = self.do_topo()
            if foco in topo and tecla in (Key.Key_Left, Key.Key_Right):
                i = topo.index(foco) + (1 if tecla == Key.Key_Right else -1)
                self._ir(topo[i] if 0 <= i < len(topo) else barra)
                return True
            if foco in topo and tecla == Key.Key_Down:
                self._ir(barra)
                return True
            return False
        i = alvos.index(foco)
        if tecla in (Key.Key_Left, Key.Key_Right):
            j = i + (1 if tecla == Key.Key_Right else -1)
            if 0 <= j < len(alvos):
                self._ir(alvos[j])
            return True
        vizinho = self._vizinho(foco, alvos, para_baixo=(tecla == Key.Key_Down))
        if vizinho is not None:
            self._ir(vizinho)
        elif tecla == Key.Key_Up:
            self._ir(barra)
        return True

    def _vizinho(self, foco: QWidget, alvos: list[QWidget], para_baixo: bool) -> QWidget | None:
        r = foco.rect().translated(foco.mapTo(self._faixa, QPoint(0, 0)))
        melhor, distancia = None, None
        for w in alvos:
            if w is foco:
                continue
            o = w.rect().translated(w.mapTo(self._faixa, QPoint(0, 0)))
            dy = o.center().y() - r.center().y()
            if (para_baixo and dy <= 4) or (not para_baixo and dy >= -4):
                continue
            d = abs(o.center().x() - r.center().x()) + 3 * abs(dy)
            if distancia is None or d < distancia:
                melhor, distancia = w, d
        return melhor

    def _ir(self, widget: QWidget) -> None:
        widget.setFocus(Qt.FocusReason.TabFocusReason)

    def _tab(self, foco: QWidget, para_tras: bool) -> bool:
        ordem = [*self.do_topo(), self._faixa._abas, *self.focaveis()]
        if foco not in ordem:
            return False
        i = (ordem.index(foco) + (-1 if para_tras else 1)) % len(ordem)
        self._ir(ordem[i])
        return True

    # -- F6: regioes da janela ------------------------------------------------------------
    def regioes(self) -> list[QWidget]:
        """Documento, faixa, barra de busca e paineis visiveis, na ordem do F6 (como no Word)."""
        j = self._janela
        candidatos = [self._painel, self._faixa._abas]
        if j.barra_busca.isVisible():
            candidatos.append(j.barra_busca._procurar)
        if j.dock_navegacao.isVisible():
            candidatos.append(j.navegacao.arvore)
        if j.dock_estilos.isVisible():
            candidatos.append(j.painel_estilos.lista)
        candidatos.append(j.controle_zoom)
        return [w for w in candidatos if w.isVisible()]

    def _proxima_regiao(self, foco: QWidget | None, para_tras: bool) -> bool:
        regioes = self.regioes()
        atual = 0
        for i, w in enumerate(regioes):
            alvo = foco
            while alvo is not None and alvo is not w:
                alvo = alvo.parentWidget()
            if alvo is w:
                atual = i
                break
        destino = regioes[(atual + (-1 if para_tras else 1)) % len(regioes)]
        if destino is self._faixa._abas:
            self.entrar()
        else:
            if self.ativo:
                self.sair(devolver=False)
            alvo = destino
            if destino is self._janela.controle_zoom:
                # O controle de zoom nao pega foco: os botoes dele, sim.
                alvo = next((b for b in destino.findChildren(QAbstractButton)
                             if b.focusPolicy() & Qt.FocusPolicy.TabFocus), destino)
            alvo.setFocus(Qt.FocusReason.TabFocusReason)
        return True

    # -- eventos ----------------------------------------------------------------------
    def _na_janela(self, obj) -> bool:
        return isinstance(obj, QWidget) and obj.window() is self._janela

    def _na_faixa(self, widget: QWidget | None) -> bool:
        while widget is not None:
            if widget is self._faixa:
                return True
            widget = widget.parentWidget()
        return False

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 - nome do Qt
        tipo = ev.type()
        if tipo == QEvent.Type.MouseButtonPress and self.ativo and self._na_janela(obj):
            self.sair(devolver=False)
            return False
        if tipo == QEvent.Type.FocusIn and self.ativo and self._na_janela(obj):
            if not self._na_faixa(obj):
                # O foco saiu da faixa (clique no documento, F6, um painel): o modo acaba.
                self.sair(devolver=False)
            return False
        if tipo not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        foco = QApplication.focusWidget()
        # O filtro do aplicativo ve o evento uma vez por widget da cadeia: so' o do foco conta.
        if obj is not foco or not self._na_janela(obj):
            return False
        tecla = ev.key()
        mods = ev.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        if tipo == QEvent.Type.KeyRelease:
            if tecla == Key.Key_Alt and self._alt_sozinho:
                self._alt_sozinho = False
                if self.ativo:
                    self.sair()
                else:
                    self.entrar()
                return True
            return False
        # KeyPress
        if tecla == Key.Key_Alt:
            # O Qt 6 inverte o bit do proprio Alt em modifiers() na tecla Alt: o que conta e'
            # nao haver Ctrl, Shift nem Win junto (AltGr chega como Ctrl+Alt).
            outros = mods & ~Qt.KeyboardModifier.AltModifier
            self._alt_sozinho = (outros == Qt.KeyboardModifier.NoModifier
                                 and not ev.isAutoRepeat())
            return False
        self._alt_sozinho = False
        if tecla == Key.Key_F10 and mods == Qt.KeyboardModifier.NoModifier:
            if self.ativo:
                self.sair()
            else:
                self.entrar()
            return True
        if tecla == Key.Key_F6 and mods in (Qt.KeyboardModifier.NoModifier,
                                            Qt.KeyboardModifier.ShiftModifier):
            return self._proxima_regiao(
                foco, para_tras=bool(mods & Qt.KeyboardModifier.ShiftModifier))
        if not self._na_faixa(foco):
            return False
        if tecla == Key.Key_Escape:
            if self.nivel == "botoes":
                self._faixa._abas.setFocus(Qt.FocusReason.ShortcutFocusReason)
                self._mostrar_abas()
            else:
                self.sair()
            return True
        if self._dicas and mods in (Qt.KeyboardModifier.NoModifier,
                                    Qt.KeyboardModifier.ShiftModifier) and ev.text():
            if not isinstance(foco, _USAM_SETAS) and self._letra(ev.text()):
                return True
        if tecla in (Key.Key_Tab, Key.Key_Backtab) and not (mods & Qt.KeyboardModifier.ControlModifier):
            self._esconder()
            return self._tab(foco, para_tras=(tecla == Key.Key_Backtab
                                              or bool(mods & Qt.KeyboardModifier.ShiftModifier)))
        if tecla in _SETAS and not isinstance(foco, _USAM_SETAS):
            self._esconder()
            return self._navegar(foco, tecla)
        if (tecla in (Key.Key_Return, Key.Key_Enter, Key.Key_Space)
                and isinstance(foco, QAbstractButton)):
            self.sair(devolver=True)
            apertar(foco)
            return True
        return False


class _AncoraDeAba:
    """Uma aba da barra como alvo de dica (a aba nao e' um widget)."""

    def __init__(self, barra, indice: int) -> None:
        self.barra = barra
        self.indice = indice
        self._ponto = _PontoDaAba(barra, indice)

    def widget_para_posicao(self):
        return self._ponto


class _PontoDaAba:
    """Imita o pedaco de QWidget que `_rotulo` usa para posicionar a dica sob a aba."""

    def __init__(self, barra, indice: int) -> None:
        self._barra = barra
        self._r = barra.tabRect(indice)

    def width(self) -> int:
        return self._r.width()

    def height(self) -> int:
        return self._r.height()

    def mapTo(self, destino, ponto):  # noqa: N802 - mesmo nome do Qt
        return self._barra.mapTo(destino, self._r.topLeft() + ponto)


def apertar(botao: QAbstractButton) -> None:
    """Aperta o botao como o Espaco faria; botao de menu abre o menu (depois, fora do filtro)."""
    if isinstance(botao, QToolButton) and botao.menu() is not None and \
            botao.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup:
        QTimer.singleShot(0, botao.showMenu)
        return
    botao.click()
