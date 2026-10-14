"""Painel de comentarios (0.1.6): o "Mostrar comentarios" do Word, num QDockWidget a direita.

Um cartao por conversa, na ordem do texto: autor, data, o texto do comentario e as respostas
logo abaixo, recuadas; a conversa resolvida aparece esmaecida, com "Resolvido". Clicar no
cartao seleciona o trecho comentado; o cursor num trecho comentado destaca o cartao. Os botoes
de cada cartao (Responder, Editar, Resolver ou Reabrir, Excluir) pedem a janela, que tem os
dialogos. Tudo com nome para o leitor de tela (a suite de acessibilidade varre o painel).

O texto do cartao e' HTML montado aqui, com o texto escapado (o comentario e' dado do arquivo,
nunca marcacao): negrito, italico, sublinhado e o link como texto sublinhado (o rotulo nao abre
endereco nenhum).
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from editdoc.modelo.comentarios import Comentario, Comentarios, data_para_tela
from editdoc.modelo.documento import Paragrafo

#: Quantos caracteres do comentario entram no nome falado do cartao.
RESUMO = 120


def html_do_conteudo(c: Comentario) -> str:
    partes = []
    for p in c.paragrafos:
        if not isinstance(p, Paragrafo):
            partes.append("<i>[tabela]</i>")
            continue
        trechos = []
        for r in p.runs:
            if r.marca is not None:
                continue
            if r.eh_objeto():
                trechos.append("<i>[objeto]</i>")
                continue
            t = html.escape(r.texto).replace("\n", "<br>")
            if r.negrito:
                t = f"<b>{t}</b>"
            if r.italico:
                t = f"<i>{t}</i>"
            if r.sublinhado or r.link is not None:
                t = f"<u>{t}</u>"
            trechos.append(t)
        partes.append("".join(trechos) or "&nbsp;")
    return "<br>".join(partes)


def _botao(texto: str, nome: str) -> QPushButton:
    b = QPushButton(texto)
    b.setAccessibleName(nome)
    b.setToolTip(nome)
    b.setFlat(True)
    b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    b.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return b


class CartaoComentario(QFrame):
    """Uma conversa: o comentario do topo e as respostas."""

    clicado = Signal(int)

    def __init__(self, raiz: Comentario, respostas: list[Comentario], painel: "PainelComentarios") -> None:
        super().__init__()
        self.ident = raiz.id
        self.resolvido = raiz.resolvido
        self.setObjectName("cartao_comentario")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        vertical = QVBoxLayout(self)
        vertical.setContentsMargins(8, 6, 8, 6)
        vertical.setSpacing(3)
        self.rotulos: list[QLabel] = []
        for i, c in enumerate([raiz, *respostas]):
            bloco = QWidget()
            linhas = QVBoxLayout(bloco)
            linhas.setContentsMargins(16 if i else 0, 0, 0, 0)
            linhas.setSpacing(1)
            topo = QLabel(f"<b>{html.escape(c.autor or 'Autor desconhecido')}</b>"
                          f"&nbsp;&nbsp;<span style='color:palette(mid)'>"
                          f"{html.escape(data_para_tela(c.data))}</span>")
            topo.setTextFormat(Qt.TextFormat.RichText)
            texto = QLabel(html_do_conteudo(c))
            texto.setTextFormat(Qt.TextFormat.RichText)
            texto.setWordWrap(True)
            texto.setOpenExternalLinks(False)
            texto.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            resumo = c.texto().replace("\n", " ")[:RESUMO]
            texto.setAccessibleName(f"{'Resposta' if i else 'Comentário'} de {c.autor}: {resumo}")
            linhas.addWidget(topo)
            linhas.addWidget(texto)
            vertical.addWidget(bloco)
            self.rotulos.append(texto)
        self.estado = QLabel("Resolvido" if raiz.resolvido else "")
        self.estado.setVisible(raiz.resolvido)
        vertical.addWidget(self.estado)
        botoes = QHBoxLayout()
        botoes.setSpacing(2)
        autor = raiz.autor or "autor desconhecido"
        self.responder = _botao("Responder", f"Responder ao comentário de {autor}")
        self.editar = _botao("Editar", f"Editar o comentário de {autor}")
        self.resolver = _botao("Reabrir" if raiz.resolvido else "Resolver",
                               f"{'Reabrir' if raiz.resolvido else 'Resolver'} a conversa de {autor}")
        self.excluir = _botao("Excluir", f"Excluir o comentário de {autor} e as respostas")
        for b in (self.responder, self.editar, self.resolver, self.excluir):
            botoes.addWidget(b)
        botoes.addStretch(1)
        vertical.addLayout(botoes)
        self.responder.clicked.connect(lambda: painel.responder.emit(self.ident))
        self.editar.clicked.connect(lambda: painel.editar.emit(self.ident))
        self.resolver.clicked.connect(lambda: painel.resolver.emit(self.ident, not self.resolvido))
        self.excluir.clicked.connect(lambda: painel.excluir.emit(self.ident))
        nome = f"Comentário de {raiz.autor}, {data_para_tela(raiz.data)}"
        if respostas:
            nome += f", {len(respostas)} resposta{'s' if len(respostas) > 1 else ''}"
        if raiz.resolvido:
            nome += ", resolvido"
        self.setAccessibleName(nome)
        self.setAccessibleDescription(raiz.texto().replace("\n", " ")[:RESUMO])
        self.destacar(False)

    def destacar(self, ligado: bool) -> None:
        self.ativo = ligado
        borda = "2px solid palette(highlight)" if ligado else "1px solid palette(mid)"
        opacidade = "color: palette(mid);" if self.resolvido and not ligado else ""
        self.setStyleSheet(f"QFrame#cartao_comentario {{ border: {borda}; border-radius: 4px; "
                           f"{opacidade} }}")

    def mousePressEvent(self, ev) -> None:  # noqa: N802 - nome do Qt
        self.clicado.emit(self.ident)
        super().mousePressEvent(ev)


class PainelComentarios(QWidget):
    """Lista de cartoes. Sinais com o id do comentario do topo da conversa."""

    selecionado = Signal(int)
    responder = Signal(int)
    editar = Signal(int)
    resolver = Signal(int, bool)
    excluir = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setAccessibleName("Painel de comentários")
        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setAccessibleName("Lista de comentários")
        self._lista = QWidget()
        self._vertical = QVBoxLayout(self._lista)
        self._vertical.setContentsMargins(6, 6, 6, 6)
        self._vertical.setSpacing(6)
        self._vazio = QLabel("Nenhum comentário no documento.")
        self._vazio.setWordWrap(True)
        self._vertical.addWidget(self._vazio)
        self._vertical.addStretch(1)
        self._area.setWidget(self._lista)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._area)
        self.cartoes: dict[int, CartaoComentario] = {}
        self._assinatura = None
        self._ativo: int | None = None

    def atualizar(self, cat: Comentarios, ordem: list[int], assinatura=None) -> None:
        """Refaz os cartoes (so' se o catalogo ou a ordem mudou)."""
        chave = (assinatura, tuple(ordem))
        if assinatura is not None and chave == self._assinatura:
            return
        self._assinatura = chave
        for cartao in self.cartoes.values():
            self._vertical.removeWidget(cartao)
            cartao.deleteLater()
        self.cartoes = {}
        raizes = []
        for ident in ordem:
            raiz = cat.raiz(ident)
            if raiz not in raizes and cat.obter(raiz) is not None:
                raizes.append(raiz)
        for i, raiz in enumerate(raizes):
            respostas = [cat.obter(x) for x in cat.descendentes(raiz)[1:]]
            respostas = [r for r in respostas if r is not None]
            cartao = CartaoComentario(cat.obter(raiz), respostas, self)
            cartao.clicado.connect(self.selecionado)
            self._vertical.insertWidget(i, cartao)
            self.cartoes[raiz] = cartao
        self._vazio.setVisible(not raizes)
        self.destacar(self._ativo, cat)

    def destacar(self, ident: int | None, cat: Comentarios | None = None) -> None:
        """Destaca o cartao da conversa de `ident` (o comentario do cursor)."""
        raiz = cat.raiz(ident) if (cat is not None and ident is not None) else ident
        self._ativo = raiz
        for chave, cartao in self.cartoes.items():
            ligado = chave == raiz
            if ligado != getattr(cartao, "ativo", None):
                cartao.destacar(ligado)
        if raiz in self.cartoes:
            self._area.ensureWidgetVisible(self.cartoes[raiz])

    def cartao_ativo(self) -> int | None:
        return next((k for k, c in self.cartoes.items() if getattr(c, "ativo", False)), None)
