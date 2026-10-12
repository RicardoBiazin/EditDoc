"""Modelo -> QTextDocument. Preenche o documento existente, sem criar outro.

Tri-state: propriedade ausente no modelo (None) nao e' gravada no Qt, e o
`hasProperty` na volta distingue ausente de falso. Sublinhado limpa com
`NoUnderline`, explicito; texto inserido sem formato herda o vizinho.

Quebra de linha interna: "\n" no modelo vira U+2028 no Qt, e volta a "\n".
Listas: cada grupo contiguo de marcadores ou de numeracao vira um QTextList.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextListFormat)

from editdoc.modelo.documento import Documento
from editdoc.modelo.unidades import px_de_twips

LINHA_SEPARADORA = "\u2028"

_ALINHAMENTO = {
    "esquerda": Qt.AlignmentFlag.AlignLeft,
    "centro": Qt.AlignmentFlag.AlignHCenter,
    "direita": Qt.AlignmentFlag.AlignRight,
    "justificado": Qt.AlignmentFlag.AlignJustify,
}
_PROPORCIONAL = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value


def _formato_de_paragrafo(p) -> QTextBlockFormat:
    bf = QTextBlockFormat()
    if p.alinhamento is not None:
        bf.setAlignment(_ALINHAMENTO[p.alinhamento])
    if p.recuo_esquerdo_tw is not None:
        bf.setLeftMargin(px_de_twips(p.recuo_esquerdo_tw))
    if p.recuo_primeira_linha_tw is not None:
        bf.setTextIndent(px_de_twips(p.recuo_primeira_linha_tw))
    if p.espaco_antes_tw is not None:
        bf.setTopMargin(px_de_twips(p.espaco_antes_tw))
    if p.espaco_depois_tw is not None:
        bf.setBottomMargin(px_de_twips(p.espaco_depois_tw))
    if p.espacamento_linha_pct is not None:
        bf.setLineHeight(float(p.espacamento_linha_pct), _PROPORCIONAL)
    return bf


def _formato_de_run(r) -> QTextCharFormat:
    cf = QTextCharFormat()
    if r.negrito is not None:
        cf.setFontWeight(QFont.Weight.Bold if r.negrito else QFont.Weight.Normal)
    if r.italico is not None:
        cf.setFontItalic(r.italico)
    if r.sublinhado is not None:
        cf.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline if r.sublinhado
                             else QTextCharFormat.UnderlineStyle.NoUnderline)
    if r.tachado is not None:
        cf.setFontStrikeOut(r.tachado)
    if r.subscrito is not None or r.sobrescrito is not None:
        if r.subscrito:
            va = QTextCharFormat.VerticalAlignment.AlignSubScript
        elif r.sobrescrito:
            va = QTextCharFormat.VerticalAlignment.AlignSuperScript
        else:
            va = QTextCharFormat.VerticalAlignment.AlignNormal
        cf.setVerticalAlignment(va)
    if r.tamanho_meio_pt is not None:
        cf.setFontPointSize(r.tamanho_meio_pt / 2)
    if r.fonte:
        cf.setFontFamilies([r.fonte])
    if r.cor_hex is not None:
        cf.setForeground(QBrush(QColor("#" + r.cor_hex)))
    return cf


def preencher(documento_qt: QTextDocument, modelo: Documento) -> None:
    """Substitui o conteudo de `documento_qt` pelo do modelo. Limpa o desfazer."""
    documento_qt.clear()
    cursor = QTextCursor(documento_qt)
    for i, p in enumerate(modelo.paragrafos):
        if i > 0:
            cursor.insertBlock()
        cursor.setBlockFormat(_formato_de_paragrafo(p))
        for r in p.runs:
            if r.texto:
                cursor.insertText(r.texto.replace("\n", LINHA_SEPARADORA),
                                  _formato_de_run(r))
    _aplicar_listas(documento_qt, modelo)
    documento_qt.clearUndoRedoStacks()
    documento_qt.setModified(False)


def _aplicar_listas(documento_qt: QTextDocument, modelo: Documento) -> None:
    lista = None
    estilo_atual = None
    for i, p in enumerate(modelo.paragrafos):
        bloco = documento_qt.findBlockByNumber(i)
        if p.numeracao is None:
            lista = estilo_atual = None
            continue
        estilo = (QTextListFormat.Style.ListDisc if p.numeracao == "marcadores"
                  else QTextListFormat.Style.ListDecimal)
        if lista is None or estilo != estilo_atual:
            formato = QTextListFormat()
            formato.setStyle(estilo)
            lista = QTextCursor(bloco).createList(formato)
            estilo_atual = estilo
        else:
            lista.add(bloco)
