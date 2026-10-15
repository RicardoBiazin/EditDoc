"""Controle de alteracoes na janela (0.1.13): a aba Revisão, o modo de exibicao, o painel.

A janela cria um `ControleDeRevisoes` e liga a ele os ganchos da aba Revisão (os comandos sao
de `interface/comandos.py`). O painel lateral dos comentarios (0.1.6) virou um painel com duas
abas: "Comentários" e "Revisões" (`painel_revisoes.py`). O modo de exibicao vale para a janela:
corpo, cabecalhos e rodapes e notas; trocar o modo refaz o realce (nao mexe no documento, no
desfazer nem no "alterado").
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QInputDialog, QTabWidget

from editdoc.edicao import revisoes as ed
from editdoc.interface.painel_revisoes import PainelRevisoes
from editdoc.modelo.revisoes import NOMES_DOS_MODOS
from editdoc.ponte_qt import revisoes as pq

#: Pausa depois da ultima tecla antes de refazer a lista de revisoes.
ATRASO_LISTA_MS = 600
#: Modo -> id da acao.
ACAO_DO_MODO = {"simples": "modo_simples", "todas": "modo_todas", "final": "modo_sem",
                "original": "modo_original"}


class ControleDeRevisoes(QObject):

    def __init__(self, janela) -> None:
        super().__init__(janela)
        self.janela = janela
        self.painel = janela.painel
        self.lista = PainelRevisoes()
        self.abas = QTabWidget()
        self.abas.setAccessibleName("Comentários e revisões")
        self.abas.addTab(janela.painel_comentarios, "Comentários")
        self.abas.addTab(self.lista, "Revisões")
        janela.dock_comentarios.setWidget(self.abas)
        janela.dock_comentarios.setWindowTitle("Comentários e revisões")
        self._itens: list = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(ATRASO_LISTA_MS)
        self._timer.timeout.connect(self.atualizar_lista)
        self.painel.textChanged.connect(self._timer.start)
        self.painel.cursorPositionChanged.connect(self._destacar)
        self.lista.selecionado.connect(self._escolhido)
        self.lista.aceitar.connect(lambda i: self._resolver_da_lista(i, True))
        self.lista.rejeitar.connect(lambda i: self._resolver_da_lista(i, False))
        self.abas.currentChanged.connect(lambda _i: self._sintonizar_acoes())
        self.modo = "todas"
        c = janela.comandos
        c.acao("modo_todas").setChecked(True)
        c.acao("imprimir_marcacoes").setChecked(True)
        self.painel.layout_pag.imprimir_marcacoes = True
        self.definir_autor(janela._autor_comentario()[0])

    # -- ganchos da aba Revisao -------------------------------------------------------------
    def ganchos(self) -> dict:
        return {"controlar": self.alternar_controle, "modo": self.definir_modo,
                "imprimir_marcas": self.alternar_imprimir, "aceitar": lambda: self.atual(True),
                "rejeitar": lambda: self.atual(False),
                "aceitar_todas": lambda: self.todas(True),
                "rejeitar_todas": lambda: self.todas(False),
                "aceitar_autor": lambda: self.do_autor(True),
                "rejeitar_autor": lambda: self.do_autor(False),
                "revisao_anterior": lambda: self.ir(False),
                "revisao_proxima": lambda: self.ir(True),
                "painel_revisoes": self.alternar_painel}

    def definir_autor(self, nome: str) -> None:
        """O autor das revisoes novas (o das Opcoes, como o dos comentarios)."""
        self.painel.autor_revisao = nome

    def _mensagem(self, texto: str) -> None:
        self.janela.statusBar().showMessage(texto, 6000)

    def alternar_controle(self) -> None:
        ligado = not ed.controle_ligado(self.painel)
        ed.definir_controle(self.painel, ligado)
        self._mensagem("Controlar alterações ligado: o que você mudar fica marcado."
                       if ligado else "Controlar alterações desligado.")
        self._sintonizar_acoes()

    def alternar_imprimir(self) -> None:
        layout = self.painel.layout_pag
        layout.imprimir_marcacoes = not getattr(layout, "imprimir_marcacoes", True)
        self._sintonizar_acoes()

    def definir_modo(self, modo: str) -> None:
        """Marcacao simples, Toda a marcacao, Sem marcacao ou Original (para a janela)."""
        self.modo = modo
        mudou = False
        docs = self._documentos()
        alterados = [d.isModified() for d in docs]
        for doc in docs:
            mudou = pq.definir_modo(doc, modo) or mudou
        if mudou:
            self._depois_de_mudar()
        # O modo e' so' a aparencia: o "alterado" de cada documento fica como estava.
        for d, alterado in zip(docs, alterados):
            if d.isModified() != alterado:
                d.setModified(alterado)
        self._mensagem(f"Exibir para revisão: {NOMES_DOS_MODOS[modo]}.")
        self._sintonizar_acoes()

    def _documentos(self) -> list:
        layout = self.painel.layout_pag
        docs = [layout.doc] + [f.doc for f in layout.faixas.todas()]
        docs += [d.doc for d in layout.notas.todos()]
        return docs

    def _depois_de_mudar(self) -> None:
        """O layout mudou sem mudar o documento (modo) ou mudou muito (aceitar todas). O
        "alterado" de cada documento fica como estava: refazer as secoes ajusta o layout, nao
        o texto."""
        p = self.painel
        docs = self._documentos()
        alterados = [d.isModified() for d in docs]
        try:
            p.layout_pag.atualizar_secoes(forcar=True)
        except TypeError:
            p.layout_pag.atualizar_secoes()
        for d, alterado in zip(docs, alterados):
            if d.isModified() != alterado:
                d.setModified(alterado)
        p._limpar_cache()
        p._altura_doc_anterior = None
        p._atualizar_geometria()
        p.paginaAlterada.emit()
        p.viewport().update()

    def alternar_painel(self) -> None:
        dock = self.janela.dock_comentarios
        if dock.isHidden() or self.abas.currentWidget() is not self.lista:
            dock.show()
            self.abas.setCurrentWidget(self.lista)
            self.atualizar_lista()
        else:
            dock.hide()
        self._sintonizar_acoes()

    # -- aceitar, rejeitar, navegar ---------------------------------------------------------
    def atual(self, aceitar: bool) -> bool:
        """A alteracao do cursor, ou as da selecao; depois vai para a proxima."""
        c = self.painel.textCursor()
        item = ed.no_cursor(self.painel)
        if c.hasSelection() and (item is None or (item.inicio, item.fim) != (
                c.selectionStart(), c.selectionEnd())):
            res = ed.resolver(self.painel, aceitar,
                              intervalo=(c.selectionStart(), c.selectionEnd()))
        elif item is not None:
            res = ed.resolver(self.painel, aceitar, item=item)
        else:
            self._mensagem("Não há alteração no cursor.")
            return False
        self._informar(res, aceitar)
        if res.resolvidas and ed.listar(self.painel.document()):
            ed.ir(self.painel, True)
        return bool(res.resolvidas)

    def todas(self, aceitar: bool, autor: str | None = None) -> int:
        total = ed.Resultado()
        for doc in ed.documentos(self.painel):
            res = ed.resolver(self.painel, aceitar, autor_=autor, doc=doc)
            total.resolvidas += res.resolvidas
            total.so_aceitar += res.so_aceitar
        self._informar(total, aceitar)
        return total.resolvidas

    def do_autor(self, aceitar: bool) -> int:
        autores = sorted({i.autor for doc in ed.documentos(self.painel) for i in ed.listar(doc)})
        if not autores:
            self._mensagem("Não há alterações no documento.")
            return 0
        autor = self.janela._escolher_autor(autores, "Aceitar" if aceitar else "Rejeitar")
        if autor is None:
            return 0
        return self.todas(aceitar, autor)

    def _informar(self, res, aceitar: bool) -> None:
        self._depois_de_mudar()
        self.atualizar_lista()
        verbo = "aceita" if aceitar else "rejeitada"
        partes = []
        if res.resolvidas:
            n = res.resolvidas
            partes.append(f"{n} alteraç{'ão' if n == 1 else 'ões'} "
                          f"{verbo}{'' if n == 1 else 's'}.")
        if res.so_aceitar:
            partes.append(f"{res.so_aceitar} alteração(ões) não puderam ser resolvidas no EditDoc "
                          "(célula sozinha inserida ou excluída, mescla de células ou numeração "
                          "antiga) e ficaram como estavam.")
        if not partes:
            partes.append("Nenhuma alteração para resolver.")
        self._mensagem(" ".join(partes))

    def ir(self, proxima: bool) -> None:
        if ed.ir(self.painel, proxima) is None:
            self._mensagem("Não há alterações no documento.")
        self.painel.setFocus()

    def _resolver_da_lista(self, indice: int, aceitar: bool) -> None:
        if 0 <= indice < len(self._itens):
            res = ed.resolver(self.painel, aceitar, item=self._itens[indice])
            self._informar(res, aceitar)

    def _escolhido(self, indice: int) -> None:
        if 0 <= indice < len(self._itens):
            # A linha escolhida no painel manda: o cursor que muda nao destaca outra linha
            # (duas revisoes no mesmo trecho, a do texto e a da linha da tabela).
            self._escolhendo = True
            try:
                ed.selecionar(self.painel, self._itens[indice])
            finally:
                self._escolhendo = False

    # -- lista e estado ---------------------------------------------------------------------
    def atualizar_lista(self) -> None:
        doc = self.painel.documento_corpo()
        if self.janela.dock_comentarios.isHidden():
            self._itens = ed.listar(doc)
            return
        self._itens = ed.listar(doc)
        self.lista.atualizar(self._itens, (doc.revision(), len(self._itens)))
        self._destacar()

    def _destacar(self) -> None:
        if getattr(self, "_escolhendo", False) or self.janela.dock_comentarios.isHidden() or not pq.tem_revisoes(
                self.painel.documento_corpo()) or self.painel.document() is not \
                self.painel.documento_corpo():
            return
        item = ed.no_cursor(self.painel)
        indice = next((i for i, x in enumerate(self._itens) if item is not None
                       and (x.inicio, x.fim, x.tipo) == (item.inicio, item.fim, item.tipo)), None)
        self.lista.destacar(indice)

    def ao_carregar(self) -> None:
        """Documento novo na janela: o modo da janela vale para ele; o painel aparece se o
        documento tem alteracoes."""
        for doc in self._documentos():
            pq.definir_modo(doc, self.modo)
        corpo = self.painel.documento_corpo()
        self.atualizar_lista()
        if self._itens:
            self.janela.dock_comentarios.show()
            if not self.janela.painel_comentarios.cartoes:
                self.abas.setCurrentWidget(self.lista)
            self.atualizar_lista()
        self._sintonizar_acoes()
        if ed.controle_ligado(self.painel):
            self._mensagem("Este documento está com Controlar alterações ligado.")
        _ = corpo

    def _sintonizar_acoes(self) -> None:
        c = self.janela.comandos
        c.acao("controlar_alteracoes").setChecked(ed.controle_ligado(self.painel))
        c.acao(ACAO_DO_MODO[self.modo]).setChecked(True)
        c.acao("imprimir_marcacoes").setChecked(
            bool(getattr(self.painel.layout_pag, "imprimir_marcacoes", True)))
        c.acao("painel_revisoes").setChecked(
            not self.janela.dock_comentarios.isHidden() and self.abas.currentWidget() is self.lista)

    def sintonizar(self) -> None:
        """Chamado pela janela a cada mudanca de cursor: barato."""
        self._sintonizar_acoes()
        c = self.janela.comandos
        tem = pq.tem_revisoes(self.painel.document())
        no_cursor = tem and (self.painel.textCursor().hasSelection()
                             or ed.no_cursor(self.painel) is not None)
        for i in ("aceitar_revisao", "rejeitar_revisao"):
            c.acao(i).setEnabled(bool(no_cursor))

    def texto_para_contar(self) -> str:
        """O texto que a contagem de palavras ve: o do modo (em Toda a marcacao, o final)."""
        doc = self.painel.documento_corpo()
        if not pq.tem_revisoes(doc):
            return self.painel.toPlainText()
        return ed.texto_no_modo(doc, ed.modo_para_copiar(doc))


def escolher_autor(pai, autores: list[str], verbo: str) -> str | None:
    """Dialogo para escolher o autor (Aceitar/Rejeitar todas de um autor)."""
    autor, ok = QInputDialog.getItem(pai, f"{verbo} todas de um autor",
                                     f"{verbo} todas as alterações de:", autores, 0, False)
    return autor if ok and autor else None
