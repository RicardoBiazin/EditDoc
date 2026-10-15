"""Localizar e substituir sobre o QTextDocument.

Busca em texto simples, sem expressao regular: e' o que o M1 promete. Palavra
inteira e maiusculas/minusculas sao as duas opcoes.

Limitacao que o Qt impoe: a busca nao atravessa quebra de paragrafo. Um termo
que cruza dois paragrafos nao e' encontrado.

Alteracoes controladas (0.1.13): a busca ve o que o modo de exibicao mostra (o trecho que tem
texto escondido no modo, como o excluido em "Sem marcacao", nao e' achado), e substituir com
o controle ligado e' exclusao mais insercao do autor.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextDocument
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
    achado = _achar(doc, texto, editor.textCursor(), flags)
    if achado.isNull():
        comeco = QTextCursor(doc)
        comeco.movePosition(QTextCursor.MoveOperation.End if para_tras
                            else QTextCursor.MoveOperation.Start)
        achado = _achar(doc, texto, comeco, flags)
    if achado.isNull():
        return False
    editor.setTextCursor(achado)
    return True


def _achar(doc: QTextDocument, texto: str, de, flags) -> QTextCursor:
    """`doc.find`, pulando a ocorrencia que tem texto escondido no modo das revisoes."""
    from editdoc.ponte_qt import revisoes as pq_revisoes
    achado = doc.find(texto, de, flags)
    if achado.isNull() or not pq_revisoes.tem_revisoes(doc):
        return achado
    for _ in range(100000):
        if achado.isNull() or not pq_revisoes.intervalos_ocultos(
                doc, achado.selectionStart(), achado.selectionEnd()):
            return achado
        achado = doc.find(texto, achado, flags)
    return QTextCursor()


def _trocar(editor, cursor: QTextCursor, substituto: str) -> None:
    """Troca a selecao do cursor pelo substituto (0.1.13: com o controle de alteracoes ligado,
    a selecao vira exclusao e o substituto, insercao do autor)."""
    from editdoc.edicao import revisoes as ed_revisoes
    if not ed_revisoes.controle_ligado(editor):
        cursor.insertText(substituto)
        return
    formato = QTextCharFormat(cursor.charFormat())
    ed_revisoes.apagar_intervalo(editor, cursor.document(), cursor.selectionStart(),
                                 cursor.selectionEnd())
    # O cursor acompanha o documento: o fim da selecao e' o fim do trecho (excluido ou nao).
    cursor.setPosition(min(cursor.selectionEnd(), cursor.document().characterCount() - 1))
    ajuste = ed_revisoes.formato_para_digitar(editor, formato)
    cursor.insertText(substituto, ajuste if ajuste is not None else formato)


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
        _trocar(editor, cursor, substituto)
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
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
        achado = _achar(doc, texto, posicao, flags)
        if achado.isNull():
            break
        _trocar(editor, achado, substituto)
        posicao = QTextCursor(doc)
        posicao.setPosition(achado.position())
        trocas += 1
    editor_cursor.endEditBlock()
    return trocas
