"""Acessibilidade (M8): nomes para o leitor de tela, o documento exposto e os anuncios.

TRES PARTES:

**Nomes.** Botao da faixa com rotulo curto ("N", "A▲", "¶") e' ilegivel para o leitor de
tela. `BotaoAcao` e os botoes de menu da faixa ja' nascem com nome e descricao (faixa.py);
`nomear_tudo` passa por todos os controles de uma janela ou dialogo e da' nome, pela dica
ou pelo texto, a quem ainda nao tem. `sem_nome` e' a mesma regra vista do teste: o que ela
devolve e' um controle que o leitor de tela anunciaria como "botao" e nada mais.

**O documento.** A VistaPaginas pinta o texto ela mesma: o Qt nao sabe que ali ha' um
editor. Uma fabrica de interfaces acessiveis (`QAccessible.installFactory`) expoe o painel
como texto editavel (papel EditableText), com o nome "Documento: <arquivo>", a descricao
"Página X de Y" e, como valor, o texto do paragrafo do cursor.

Limite medido no PySide6 6.11.2 (docs/SPIKES.md, M8): a QAccessibleTextInterface completa
nao pode ser feita em Python. O PySide nao exporta `selection()` nem `attributes()` (puros
no C++, com parametros de saida por ponteiro); o UIA do Windows chama os dois ao listar os
padroes do elemento, e o processo cai ("Fatal Python error: _PyThreadState_Attach"). Ler o
texto pelo TextPattern funcionou; listar os padroes, nao. Um leitor de tela faz os dois:
por isso o EditDoc expoe o paragrafo como valor, e nao o documento como texto navegavel.

**Anuncios.** Trocar de pagina com o cursor anuncia "Página X de Y"
(QAccessibleAnnouncementEvent, Qt 6.8 em diante), so' quando um leitor de tela esta' ativo.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible, QAccessibleEvent
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QAbstractSlider,
                               QAbstractSpinBox, QAccessibleWidget, QComboBox, QHeaderView,
                               QLineEdit, QScrollBar, QTabBar, QWidget)

#: Maior trecho do paragrafo exposto como valor (um paragrafo enorme nao trava o leitor).
VALOR_MAXIMO = 2000

_ATALHO_NA_DICA = re.compile(r"\s*\([^()]*\)\s*$")
_SETA = re.compile(r"\s*[▾▸◂▲▼]\s*")

#: Controles que o usuario opera: todos precisam de nome.
INTERATIVOS = (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit, QAbstractSlider,
               QAbstractItemView, QTabBar)


def limpar(texto: str) -> str:
    """Tira o atalho entre parenteses do fim, as setas de menu e o "&" de mnemonico."""
    texto = _ATALHO_NA_DICA.sub("", texto or "")
    texto = _SETA.sub(" ", texto).replace("&&", "\0").replace("&", "").replace("\0", "&")
    return " ".join(texto.split()).strip()


def nome_legivel(texto: str) -> bool:
    """Nome que o leitor de tela consegue dizer: ao menos duas letras."""
    return sum(1 for c in texto if c.isalpha()) >= 2


def nome_acessivel(widget: QWidget) -> str:
    """O nome que o leitor de tela vai anunciar (o da interface acessivel do Qt)."""
    interface = QAccessible.queryAccessibleInterface(widget)
    if interface is None or not interface.isValid():
        return widget.accessibleName()
    return interface.text(QAccessible.Text.Name) or ""


def nomear(widget: QWidget, nome: str, descricao: str = "") -> None:
    widget.setAccessibleName(nome)
    if descricao:
        widget.setAccessibleDescription(descricao)


def nomear_tudo(raiz: QWidget) -> None:
    """Da' nome, pela dica ou pelo texto, a todo controle de `raiz` que nao tem um legivel."""
    for widget in raiz.findChildren(QWidget):
        if not isinstance(widget, INTERATIVOS):
            continue
        if widget.accessibleName() and nome_legivel(widget.accessibleName()):
            continue
        dica = limpar(widget.toolTip())
        texto = limpar(widget.text()) if isinstance(widget, QAbstractButton) else ""
        candidato = dica if nome_legivel(dica) else texto
        if nome_legivel(candidato):
            widget.setAccessibleName(candidato)
            if dica and dica != candidato and not widget.accessibleDescription():
                widget.setAccessibleDescription(dica)


def _parte_interna(widget: QWidget) -> bool:
    """Peca de outro controle (a linha de edicao do combo, a barra de rolagem da lista,
    o cabecalho da arvore): o leitor de tela fala o controle de fora."""
    if isinstance(widget, (QScrollBar, QHeaderView)):
        return True
    pai = widget.parentWidget()
    while pai is not None:
        # (o botao de limpar dentro da linha de edicao tambem e' peca dela)
        if isinstance(pai, (QComboBox, QAbstractSpinBox, QLineEdit)):
            return True
        pai = pai.parentWidget()
    return False


def sem_nome(raiz: QWidget) -> list[QWidget]:
    """Controles interativos de `raiz` sem nome legivel para o leitor de tela."""
    faltam = []
    for widget in [raiz, *raiz.findChildren(QWidget)]:
        if not isinstance(widget, INTERATIVOS) or _parte_interna(widget):
            continue
        if not nome_legivel(nome_acessivel(widget)):
            faltam.append(widget)
    return faltam


# -- o documento -------------------------------------------------------------------------

class AcessivelDocumento(QAccessibleWidget):
    """O painel do documento para o leitor de tela: texto editavel, com o paragrafo atual."""

    def __init__(self, painel) -> None:
        super().__init__(painel, QAccessible.Role.EditableText, painel.accessibleName())
        self._painel = painel

    def text(self, tipo):  # noqa: D401 - nome do Qt
        painel = self._painel
        if tipo == QAccessible.Text.Name:
            return painel.accessibleName() or "Documento"
        if tipo == QAccessible.Text.Description:
            return painel.accessibleDescription()
        if tipo == QAccessible.Text.Value:
            return texto_do_paragrafo(painel)
        return super().text(tipo)


def texto_do_paragrafo(painel) -> str:
    """O texto do paragrafo do cursor (do cabecalho, na edicao dele), cortado em VALOR_MAXIMO."""
    try:
        texto = painel.textCursor().block().text()
    except RuntimeError:
        return ""
    texto = texto.replace(" ", "\n").replace("￼", " ")
    return texto[:VALOR_MAXIMO]


_fabrica_instalada = False


def _fabrica(chave: str, objeto):
    from editdoc.interface.painel_documento import PainelDocumento
    if isinstance(objeto, PainelDocumento):
        return AcessivelDocumento(objeto)
    return None


def instalar_fabrica() -> None:
    """Uma vez por processo: o painel do documento ganha a interface acessivel propria."""
    global _fabrica_instalada
    if not _fabrica_instalada:
        QAccessible.installFactory(_fabrica)
        _fabrica_instalada = True


def anunciar(widget: QWidget, texto: str) -> None:
    """Pede ao leitor de tela que leia `texto`. Guarda o ultimo anuncio (para os testes)."""
    widget.setProperty("editdoc_ultimo_anuncio", texto)
    if not QAccessible.isActive():
        return
    try:
        from PySide6.QtGui import QAccessibleAnnouncementEvent
        QAccessible.updateAccessibility(QAccessibleAnnouncementEvent(widget, texto))
    except ImportError:  # Qt anterior ao 6.8: avisa a mudanca de descricao
        QAccessible.updateAccessibility(QAccessibleEvent(widget, QAccessible.Event.DescriptionChanged))


def descrever_documento(janela) -> None:
    """Nome e descricao do painel: "Documento: Relatorio.docx", "Página 2 de 5"."""
    painel = janela.painel
    nome = janela._nome()
    painel.setAccessibleName(f"Documento: {nome}")
    atual, total = painel.pagina_atual() + 1, painel.total_de_paginas()
    faixa = painel.editando_faixa()
    onde = ""
    if faixa is not None:
        onde = "Editando o cabeçalho. " if faixa.onde == "cabecalho" else "Editando o rodapé. "
    painel.setAccessibleDescription(f"{onde}Página {atual} de {total}")


def _pagina_do_cursor(janela) -> None:
    painel = janela.painel
    chave = (painel.pagina_atual(), painel.total_de_paginas(), painel.editando_faixa() is None)
    if chave != getattr(janela, "_chave_anuncio", None):
        anterior = getattr(janela, "_chave_anuncio", None)
        janela._chave_anuncio = chave
        descrever_documento(janela)
        if anterior is not None:
            anunciar(painel, painel.accessibleDescription())
    if QAccessible.isActive():
        QAccessible.updateAccessibility(QAccessibleEvent(painel, QAccessible.Event.ValueChanged))


def preparar_janela(janela):
    """Nomes, documento, anuncios e teclado da faixa de uma JanelaPrincipal. Devolve o teclado."""
    from editdoc.interface.dicas_teclas import TecladoFaixa

    instalar_fabrica()
    painel = janela.painel
    nomear(janela.faixa.familia, "Fonte", "Fonte do texto selecionado")
    nomear(janela.faixa.tamanho, "Tamanho da fonte", "Tamanho do texto selecionado, em pontos")
    nomear(janela.faixa._abas, "Abas da faixa de opções",
           "Setas para a esquerda e a direita trocam de aba; seta para baixo entra nos botões")
    nomear(janela._rotulo_pagina, "Página atual")
    nomear(janela._rotulo_palavras, "Contagem de palavras")
    nomear(janela.statusBar(), "Barra de status")
    nomear(janela.navegacao.arvore, "Títulos do documento",
           "Escolha um título para levar o cursor até ele")
    nomear(janela.painel_estilos.lista, "Lista de estilos",
           "Escolha um estilo para aplicá-lo ao parágrafo do cursor")
    nomear(janela.faixa, "Faixa de opções", "Alt ou F10 leva o teclado para a faixa")
    for dock in (janela.dock_estilos, janela.dock_navegacao, janela.dock_comentarios):
        titulo = dock.windowTitle()
        for botao in dock.findChildren(QAbstractButton):
            if botao.objectName() == "qt_dockwidget_closebutton":
                nomear(botao, f"Fechar o painel {titulo}")
            elif botao.objectName() == "qt_dockwidget_floatbutton":
                nomear(botao, f"Soltar o painel {titulo}")
    painel.setAccessibleDescription("")
    nomear_tudo(janela)
    descrever_documento(janela)
    painel.cursorPositionChanged.connect(lambda: _pagina_do_cursor(janela))
    painel.paginaAlterada.connect(lambda: _pagina_do_cursor(janela))
    painel.modoFaixaAlterado.connect(lambda: _pagina_do_cursor(janela))
    _pagina_do_cursor(janela)
    return TecladoFaixa(janela)


def tornar_alcancavel(widget: QWidget) -> None:
    """Botao que nao rouba o foco no clique, mas e' alcancado pelo teclado (Tab e setas)."""
    if widget.focusPolicy() == Qt.FocusPolicy.NoFocus:
        widget.setFocusPolicy(Qt.FocusPolicy.TabFocus)
