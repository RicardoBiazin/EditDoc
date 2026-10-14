"""Mantem a faixa em sintonia com o cursor, sem laco e sem trabalho a toa.

Cada mudanca de cursor ou de formato so' agenda uma atualizacao (QTimer de zero
ms). Varias mudancas seguidas viram uma atualizacao so', no proximo ciclo de
eventos.

Atualizar os botoes com setChecked nao dispara `triggered`, so' `toggled`. Os
executores ligam-se a `triggered`, por isso atualizar a faixa nao executa comando
nenhum.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, QSignalBlocker, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QComboBox, QFontComboBox, QTextEdit

from editdoc.edicao import imagens, tabelas
from editdoc.edicao.estado import ler
from editdoc.interface.comandos import (ALINHAMENTOS, COMENTARIO, EDICAO_DE_FAIXA, ESPACAMENTOS,
                                        LINK, LISTA_NUMERADA, TABELA, Comandos)
from editdoc.ponte_qt import links


class AtualizadorDeEstado(QObject):
    def __init__(self, editor: QTextEdit, comandos: Comandos,
                 familia: QFontComboBox, tamanho: QComboBox, ao_atualizar=None) -> None:
        super().__init__(editor)
        self._editor = editor
        self._comandos = comandos
        self._familia = familia
        self._tamanho = tamanho
        self._agendado = False
        #: Chamado no fim de cada atualizacao (M6: galeria, paineis, aba Layout).
        self._ao_atualizar = ao_atualizar

        editor.cursorPositionChanged.connect(self._agendar)
        editor.currentCharFormatChanged.connect(self._agendar)
        editor.undoAvailable.connect(comandos.acao("desfazer").setEnabled)
        editor.redoAvailable.connect(comandos.acao("refazer").setEnabled)
        editor.copyAvailable.connect(self._copia_disponivel)
        self.atualizar()

    def _copia_disponivel(self, disponivel: bool) -> None:
        self._comandos.acao("recortar").setEnabled(disponivel)
        self._comandos.acao("copiar").setEnabled(disponivel)

    def _agendar(self) -> None:
        if not self._agendado:
            self._agendado = True
            QTimer.singleShot(0, self._executar_agendado)

    def _executar_agendado(self) -> None:
        self._agendado = False
        self.atualizar()

    def atualizar(self) -> None:
        estado = ler(self._editor)
        c = self._comandos
        valores = {
            "negrito": estado.negrito,
            "italico": estado.italico,
            "sublinhado": estado.sublinhado,
            "tachado": estado.tachado,
            "subscrito": estado.subscrito,
            "sobrescrito": estado.sobrescrito,
            "marcadores": estado.marcadores,
            "numeracao": estado.numeracao,
        }
        for id_, valor in valores.items():
            c.acao(id_).setChecked(valor)
        for id_ in ALINHAMENTOS:
            c.acao(id_).setChecked(ALINHAMENTOS[id_] == _alinhamento_de(estado.alinhamento))
        for id_, percentual in ESPACAMENTOS.items():
            c.acao(id_).setChecked(percentual == estado.espacamento)

        # Tabela e imagem: o comando so' fica habilitado onde faz sentido.
        cursor = self._editor.textCursor()
        em_tabela = cursor.currentTable() is not None
        for id_ in TABELA:
            c.acao(id_).setEnabled(em_tabela)
        if em_tabela:
            c.acao("mesclar_celulas").setEnabled(tabelas.pode_mesclar(cursor))
            c.acao("dividir_celula").setEnabled(tabelas.pode_dividir(cursor))
        c.acao("tamanho_imagem").setEnabled(imagens.imagem_selecionada(self._editor) is not None)
        # Link (0.1.3): remover e abrir so' com o cursor num link.
        no_link = links.link_no_cursor(self._editor.document(), cursor) is not None
        for id_ in LINK:
            c.acao(id_).setEnabled(no_link)
        # Listas (0.1.4): reiniciar, continuar e definir valor so' num item numerado.
        for id_ in LISTA_NUMERADA:
            c.acao(id_).setEnabled(estado.numeracao)
        # Cabecalho e rodape (M5): fechar e ir para so' na edicao.
        editando = getattr(self._editor, "editando_faixa", lambda: None)() is not None
        for id_ in EDICAO_DE_FAIXA:
            c.acao(id_).setEnabled(editando)
        # Comentarios (0.1.6): no corpo; responder, editar, resolver e excluir so' num trecho
        # comentado. "Resolver" fica marcado na conversa resolvida.
        atual = None
        if hasattr(self._editor, "documento_corpo"):
            from editdoc.edicao import comentarios as ed_comentarios
            atual = ed_comentarios.no_cursor(self._editor)
            cat = ed_comentarios.catalogo(self._editor)
            c.acao("novo_comentario").setEnabled(not editando)
            tem = bool(cat.itens)
            for id_ in ("excluir_todos_comentarios", "comentario_anterior", "comentario_proximo"):
                c.acao(id_).setEnabled(tem)
            raiz = cat.obter(cat.raiz(atual)) if atual is not None else None
            c.acao("resolver_comentario").setChecked(bool(raiz is not None and raiz.resolvido))
        for id_ in COMENTARIO:
            c.acao(id_).setEnabled(atual is not None)

        with QSignalBlocker(self._familia), QSignalBlocker(self._tamanho):
            if estado.familia and self._familia.currentFont().family() != estado.familia:
                self._familia.setCurrentFont(QFont(estado.familia))
            texto = f"{estado.tamanho:g}"
            if self._tamanho.currentText() != texto:
                self._tamanho.setCurrentText(texto)
        if self._ao_atualizar is not None:
            self._ao_atualizar()


def _alinhamento_de(nome: str) -> Qt.AlignmentFlag:
    return {
        "esquerda": Qt.AlignmentFlag.AlignLeft,
        "centro": Qt.AlignmentFlag.AlignHCenter,
        "direita": Qt.AlignmentFlag.AlignRight,
        "justificado": Qt.AlignmentFlag.AlignJustify,
    }[nome]
