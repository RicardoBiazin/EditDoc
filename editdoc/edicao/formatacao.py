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
    """Limpar toda a formatacao (M6): o paragrafo volta ao Normal e o texto ao estilo dele.

    Antes do M6 gravava a fonte padrao como formatacao explicita; agora tira a formatacao
    direta, que e' o que o Word faz (ver edicao/estilos.py).
    """
    from editdoc.edicao import estilos
    estilos.limpar_formatacao(editor)


def limpar_caractere(editor: QTextEdit) -> None:
    """Ctrl+Espaco: so' a formatacao de caractere volta ao estilo do paragrafo."""
    from editdoc.edicao import estilos
    estilos.limpar_caractere(editor)


# -- paragrafo ----------------------------------------------------------------

def alinhar(editor: QTextEdit, alinhamento: Qt.AlignmentFlag) -> None:
    formato = QTextBlockFormat()
    formato.setAlignment(alinhamento)
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    cursor.mergeBlockFormat(formato)
    cursor.endEditBlock()


def alterar_recuo(editor: QTextEdit, delta_tw: float) -> None:
    """Soma `delta_tw` twips ao recuo esquerdo (a unidade do recuo no bloco, 0.1.4)."""
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    for bloco in _blocos_da_selecao(editor):
        formato = bloco.blockFormat()
        formato.setLeftMargin(max(0.0, formato.leftMargin() + delta_tw))
        QTextCursor(bloco).setBlockFormat(formato)
    cursor.endEditBlock()


def definir_paragrafo(editor: QTextEdit, *, antes_tw: int | None = None,
                      depois_tw: int | None = None, esquerdo_tw: int | None = None,
                      direito_tw: int | None = None, primeira_tw: int | None = None) -> None:
    """Espacamento antes e depois e recuos dos paragrafos da selecao (aba Layout, M6).

    So' muda o que vier. Um passo de desfazer. Valores em twips.
    """
    formato = QTextBlockFormat()
    # Espaco antes e depois em px96 (o Qt escala); recuos em twips (o Qt nao escala, 0.1.4).
    if antes_tw is not None:
        formato.setTopMargin(max(0, antes_tw) / 15.0)
    if depois_tw is not None:
        formato.setBottomMargin(max(0, depois_tw) / 15.0)
    if esquerdo_tw is not None:
        formato.setLeftMargin(float(esquerdo_tw))
    if direito_tw is not None:
        formato.setRightMargin(float(direito_tw))
    if primeira_tw is not None:
        formato.setTextIndent(float(primeira_tw))
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    cursor.mergeBlockFormat(formato)
    if primeira_tw is not None:
        # Item de lista: o recuo pedido e' o de verdade; o visual volta no ajuste da lista.
        from editdoc.ponte_qt.listas import PROP_RECUO_REAL
        for bloco in _blocos_da_selecao(editor):
            bf = bloco.blockFormat()
            if bf.hasProperty(PROP_RECUO_REAL):
                bf.clearProperty(PROP_RECUO_REAL)
                QTextCursor(bloco).setBlockFormat(bf)
    cursor.endEditBlock()
    if hasattr(editor, "_depois_de_formato"):
        editor._depois_de_formato()


def definir_espacamento(editor: QTextEdit, percentual: int) -> None:
    formato = QTextBlockFormat()
    formato.setLineHeight(float(percentual), _PROPORCIONAL)
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    cursor.mergeBlockFormat(formato)
    cursor.endEditBlock()


_MARCAS = (QTextListFormat.Style.ListDisc, QTextListFormat.Style.ListCircle,
           QTextListFormat.Style.ListSquare)


def alternar_lista(editor: QTextEdit, estilo: QTextListFormat.Style) -> None:
    """Liga a lista do estilo dado, ou desliga se a selecao ja esta nela (um passo de desfazer).

    Desde a 0.1.4 a lista nao e' mais um QTextList: o estilo do Qt so' escolhe entre marcadores
    (disco, circulo, quadrado) e numeracao, e quem faz e' `edicao/listas.py`.
    """
    from editdoc.edicao import listas
    if estilo in _MARCAS:
        chave = {QTextListFormat.Style.ListCircle: "vazado",
                 QTextListFormat.Style.ListSquare: "quadrado"}.get(estilo, "redondo")
        listas.alternar_marcadores(editor, chave)
    else:
        chave = {QTextListFormat.Style.ListLowerAlpha: "letra_minuscula",
                 QTextListFormat.Style.ListUpperAlpha: "letra_maiuscula",
                 QTextListFormat.Style.ListLowerRoman: "romano_minusculo",
                 QTextListFormat.Style.ListUpperRoman: "romano_maiusculo"}.get(estilo, "decimal_ponto")
        listas.alternar_numeracao(editor, chave)


def alterar_recuo_ou_nivel(editor: QTextEdit, aumentar: bool) -> None:
    """Aumentar/Diminuir recuo: num item de lista muda o nivel (0.1.4), como no Word;
    fora de lista soma ou tira 720 twips do recuo esquerdo."""
    from editdoc.edicao import listas
    from editdoc.modelo.unidades import RECUO_PADRAO_TW
    blocos = _blocos_da_selecao(editor)
    if blocos and all(listas.eh_item(editor, b) for b in blocos):
        listas.mudar_nivel(editor, 1 if aumentar else -1)
        return
    alterar_recuo(editor, RECUO_PADRAO_TW if aumentar else -RECUO_PADRAO_TW)
