"""Comandos de formatacao sobre o editor (PainelDocumento, com a API do QTextEdit).

Cada funcao recebe o editor. Com selecao, o comando altera o texto selecionado,
e o comando inteiro e' UM passo de desfazer, mesmo quando mexe em varios
paragrafos. Sem selecao, muda o formato do proximo caractere digitado: isso nao
altera o texto e por isso nao entra no desfazer.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import (QFont, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextListFormat)
from PySide6.QtWidgets import QTextEdit

from editdoc.edicao.estado import ler

_PROPORCIONAL = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value


def _aplicar_caractere(editor: QTextEdit, formato: QTextCharFormat) -> None:
    cursor = editor.textCursor()
    if cursor.hasSelection():
        cursor.mergeCharFormat(formato)
    else:
        editor.mergeCurrentCharFormat(formato)


def _blocos_da_selecao(editor: QTextEdit) -> list:
    doc = editor.document()
    cursor = editor.textCursor()
    atual = doc.findBlock(cursor.selectionStart())
    ultimo = doc.findBlock(cursor.selectionEnd()).blockNumber()
    blocos = []
    while atual.isValid():
        blocos.append(atual)
        if atual.blockNumber() >= ultimo:
            break
        atual = atual.next()
    return blocos


# -- caractere ----------------------------------------------------------------

def alternar_negrito(editor: QTextEdit) -> None:
    formato = QTextCharFormat()
    ligado = ler(editor).negrito
    formato.setFontWeight(QFont.Weight.Normal if ligado else QFont.Weight.Bold)
    _aplicar_caractere(editor, formato)


def alternar_italico(editor: QTextEdit) -> None:
    formato = QTextCharFormat()
    formato.setFontItalic(not ler(editor).italico)
    _aplicar_caractere(editor, formato)


def alternar_sublinhado(editor: QTextEdit) -> None:
    # Limpar o sublinhado com setUnderlineStyle(NoUnderline), que e' explicito e nao
    # depende do formato herdado do vizinho.
    formato = QTextCharFormat()
    ligado = ler(editor).sublinhado
    formato.setUnderlineStyle(QTextCharFormat.UnderlineStyle.NoUnderline if ligado
                              else QTextCharFormat.UnderlineStyle.SingleUnderline)
    _aplicar_caractere(editor, formato)


def alternar_tachado(editor: QTextEdit) -> None:
    formato = QTextCharFormat()
    formato.setFontStrikeOut(not ler(editor).tachado)
    _aplicar_caractere(editor, formato)


def alternar_subscrito(editor: QTextEdit) -> None:
    estado = ler(editor)
    formato = QTextCharFormat()
    formato.setVerticalAlignment(
        QTextCharFormat.VerticalAlignment.AlignNormal if estado.subscrito
        else QTextCharFormat.VerticalAlignment.AlignSubScript)
    _aplicar_caractere(editor, formato)


def alternar_sobrescrito(editor: QTextEdit) -> None:
    estado = ler(editor)
    formato = QTextCharFormat()
    formato.setVerticalAlignment(
        QTextCharFormat.VerticalAlignment.AlignNormal if estado.sobrescrito
        else QTextCharFormat.VerticalAlignment.AlignSuperScript)
    _aplicar_caractere(editor, formato)


def definir_familia(editor: QTextEdit, nome: str) -> None:
    if not nome:
        return
    formato = QTextCharFormat()
    formato.setFontFamilies([nome])
    _aplicar_caractere(editor, formato)


def definir_tamanho(editor: QTextEdit, pontos: float) -> None:
    if pontos <= 0:
        return
    formato = QTextCharFormat()
    formato.setFontPointSize(pontos)
    _aplicar_caractere(editor, formato)


def alterar_tamanho(editor: QTextEdit, delta: float) -> None:
    definir_tamanho(editor, max(1.0, ler(editor).tamanho + delta))


def limpar_formatacao(editor: QTextEdit) -> None:
    padrao = editor.document().defaultFont()
    formato = QTextCharFormat()
    formato.setFontFamilies([padrao.family()])
    formato.setFontPointSize(padrao.pointSizeF())
    formato.setFontWeight(QFont.Weight.Normal)
    formato.setFontItalic(False)
    formato.setFontStrikeOut(False)
    formato.setUnderlineStyle(QTextCharFormat.UnderlineStyle.NoUnderline)
    formato.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
    cursor = editor.textCursor()
    if cursor.hasSelection():
        # setCharFormat substitui o formato inteiro, e nao so' mescla: e' o que
        # limpar significa.
        cursor.beginEditBlock()
        cursor.setCharFormat(formato)
        cursor.endEditBlock()
    else:
        editor.setCurrentCharFormat(formato)


# -- paragrafo ----------------------------------------------------------------

def alinhar(editor: QTextEdit, alinhamento: Qt.AlignmentFlag) -> None:
    formato = QTextBlockFormat()
    formato.setAlignment(alinhamento)
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    cursor.mergeBlockFormat(formato)
    cursor.endEditBlock()


def alterar_recuo(editor: QTextEdit, delta_px: float) -> None:
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    for bloco in _blocos_da_selecao(editor):
        formato = bloco.blockFormat()
        formato.setLeftMargin(max(0.0, formato.leftMargin() + delta_px))
        QTextCursor(bloco).setBlockFormat(formato)
    cursor.endEditBlock()


def definir_espacamento(editor: QTextEdit, percentual: int) -> None:
    formato = QTextBlockFormat()
    formato.setLineHeight(float(percentual), _PROPORCIONAL)
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    cursor.mergeBlockFormat(formato)
    cursor.endEditBlock()


def alternar_lista(editor: QTextEdit, estilo: QTextListFormat.Style) -> None:
    """Liga a lista do estilo dado, ou desliga se a selecao ja esta nela.

    Se a selecao esta numa lista de outro estilo, troca o estilo da lista.
    """
    blocos = _blocos_da_selecao(editor)
    lista = blocos[0].textList()
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    if lista is None:
        formato = QTextListFormat()
        formato.setStyle(estilo)
        cursor.createList(formato)
    elif lista.format().style() == estilo:
        for bloco in blocos:
            if bloco.textList() is not None:
                lista.remove(bloco)
    else:
        formato = lista.format()
        formato.setStyle(estilo)
        lista.setFormat(formato)
    cursor.endEditBlock()
