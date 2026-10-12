"""Localizar e substituir sobre o QTextDocument.

Busca em texto simples, sem expressao regular: e' o que o M1 promete. Palavra
inteira e maiusculas/minusculas sao as duas opcoes.

Limitacao que o Qt impoe: a busca nao atravessa quebra de paragrafo. Um termo
que cruza dois paragrafos nao e' encontrado.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QTextEdit


@dataclass(frozen=True)
class Opcoes:
    maiusculas: bool = False
    palavra_inteira: bool = False


def _flags(opcoes: Opcoes, para_tras: bool = False) -> QTextDocument.FindFlag:
    flags = QTextDocument.FindFlag(0)
    if opcoes.maiusculas:
        flags |= QTextDocument.FindFlag.FindCaseSensitively
    if opcoes.palavra_inteira:
        flags |= QTextDocument.FindFlag.FindWholeWords
    if para_tras:
        flags |= QTextDocument.FindFlag.FindBackward
    return flags


def localizar(editor: QTextEdit, texto: str, opcoes: Opcoes,
              para_tras: bool = False) -> bool:
    """Seleciona a proxima ocorrencia (ou a anterior). Volta ao inicio/fim se preciso.

    Devolve False quando o texto nao existe no documento.
    """
    if not texto:
        return False
    doc = editor.document()
    flags = _flags(opcoes, para_tras)
    achado = doc.find(texto, editor.textCursor(), flags)
    if achado.isNull():
        comeco = QTextCursor(doc)
        comeco.movePosition(QTextCursor.MoveOperation.End if para_tras
                            else QTextCursor.MoveOperation.Start)
        achado = doc.find(texto, comeco, flags)
    if achado.isNull():
        return False
    editor.setTextCursor(achado)
    return True


def _selecao_coincide(cursor: QTextCursor, texto: str, opcoes: Opcoes) -> bool:
    if not cursor.hasSelection():
        return False
    selecionado = cursor.selectedText()
    if opcoes.maiusculas:
        return selecionado == texto
    return selecionado.casefold() == texto.casefold()


def substituir_atual(editor: QTextEdit, texto: str, substituto: str,
                     opcoes: Opcoes) -> bool:
    """Troca a selecao, se ela for uma ocorrencia, e vai para a proxima.

    Se a selecao nao e' uma ocorrencia, so' localiza. Devolve False se nao
    havia mais nada a localizar.
    """
    cursor = editor.textCursor()
    if _selecao_coincide(cursor, texto, opcoes):
        cursor.beginEditBlock()
        cursor.insertText(substituto)
        cursor.endEditBlock()
    return localizar(editor, texto, opcoes)


def substituir_todas(editor: QTextEdit, texto: str, substituto: str,
                     opcoes: Opcoes) -> int:
    """Troca todas as ocorrencias num unico passo de desfazer. Devolve quantas trocou.

    A busca continua depois do texto inserido. Sem isso, um substituto que
    contem o proprio termo ("a" -> "aa") seria encontrado de novo e trocado sem
    fim.
    """
    if not texto:
        return 0
    doc = editor.document()
    flags = _flags(opcoes)
    trocas = 0
    posicao = QTextCursor(doc)
    editor_cursor = QTextCursor(doc)
    editor_cursor.beginEditBlock()
    while True:
        achado = doc.find(texto, posicao, flags)
        if achado.isNull():
            break
        achado.insertText(substituto)
        posicao = QTextCursor(doc)
        posicao.setPosition(achado.position())
        trocas += 1
    editor_cursor.endEditBlock()
    return trocas
