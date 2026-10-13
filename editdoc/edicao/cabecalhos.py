"""Comandos de cabecalho, rodape e numero de pagina (M5).

Cada comando e' um passo de desfazer no documento que ele muda: o campo no cursor
entra no documento ativo (corpo ou cabecalho em edicao); o numero de pagina entra
em cada variante do cabecalho (ou rodape) que aparece no documento.

"Número de Página" nao apaga o que ja' existe no cabecalho: se ele tem texto, o
numero entra num paragrafo novo no fim (no Word, a galeria troca o conteudo; aqui
se preferiu nao perder texto).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextBlockFormat, QTextCharFormat, QTextCursor

from editdoc.ponte_qt import campos, marcas, opacos

_ALINHAMENTO = {
    "esquerda": Qt.AlignmentFlag.AlignLeft,
    "centro": Qt.AlignmentFlag.AlignHCenter,
    "direita": Qt.AlignmentFlag.AlignRight,
}


def _resultado(painel, instrucao: str) -> str:
    """Valor guardado no arquivo para o campo novo: o da pagina do caret, ou o total."""
    contexto = campos.ContextoDeCampos()
    contexto.pagina = painel.configuracao_pagina()
    contexto.total = painel.total_de_paginas()
    return contexto.valor(instrucao, painel.pagina_atual())


def inserir_campo_no_cursor(painel, instrucao: str) -> None:
    """PAGE ou NUMPAGES no cursor, com a formatacao do cursor. Um passo de desfazer."""
    cursor = painel.textCursor()
    base = QTextCharFormat(cursor.charFormat())
    for propriedade in (*campos.PROPS_DE_CAMPO, *opacos.PROPS_DE_OPACO, *marcas.PROPS_DE_MARCA):
        base.clearProperty(propriedade)
    if base.isImageFormat():
        base = QTextCharFormat()
    cursor.beginEditBlock()
    if cursor.hasSelection():
        cursor.removeSelectedText()
    campos.inserir_campo(cursor, instrucao, _resultado(painel, instrucao), base)
    cursor.endEditBlock()
    painel.setTextCursor(cursor)


def inserir_numero_de_pagina(painel, onde: str, alinhamento: str, com_total: bool = False) -> None:
    """Numero da pagina no cabecalho ("cabecalho") ou no rodape ("rodape").

    Entra em cada variante que aparece (padrao; primeira e par quando ligadas), com o
    alinhamento pedido: so' o numero, ou "Página X de Y". Depois o cabecalho fica em
    edicao, como no Word.
    """
    faixas = painel.layout_pag.faixas
    pagina = painel.configuracao_pagina()
    for tipo in faixas.tipos_ativos(pagina):
        faixa = faixas.obter(onde, tipo, criar=True)
        cursor = QTextCursor(faixa.doc)
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.beginEditBlock()
        if not faixa.vazia():
            cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())
        formato = QTextBlockFormat(cursor.blockFormat())
        formato.setAlignment(_ALINHAMENTO[alinhamento])
        cursor.setBlockFormat(formato)
        texto = QTextCharFormat()
        if com_total:
            cursor.insertText("Página ", texto)
        campos.inserir_campo(cursor, "PAGE", "1", texto)
        if com_total:
            cursor.insertText(" de ", texto)
            campos.inserir_campo(cursor, "NUMPAGES", str(painel.total_de_paginas()), texto)
        cursor.endEditBlock()
    painel.entrar_na_faixa(onde, painel.pagina_atual())


def remover(painel, onde: str) -> None:
    """Esvazia todas as variantes do cabecalho (ou rodape). Um passo de desfazer em cada."""
    for faixa in painel.layout_pag.faixas.todas():
        if faixa.onde != onde or faixa.vazia():
            continue
        cursor = QTextCursor(faixa.doc)
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.removeSelectedText()
        cursor.setBlockFormat(QTextBlockFormat())
        cursor.setCharFormat(QTextCharFormat())
        cursor.endEditBlock()
    painel.viewport().update()
