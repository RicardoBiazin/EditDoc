"""Ponte do spike B: Documento <-> QTextDocument (PySide6). So para o T6.

Tri-state via QTextFormat.hasProperty: propriedade ausente = None; presente = valor.
Quebra de linha interna: '\n' <-> U+2028 (separador de linha do Qt).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QTextBlockFormat,  # noqa: E402
                           QTextCharFormat, QTextCursor, QTextDocument, QTextFormat)

from modelo import Documento, Paragrafo, Run  # noqa: E402

PX_POR_TWIP = 1 / 15  # 1 twip = 1/20 pt; 1 pt = 96/72 px

_ALINH_PARA_QT = {
    "esquerda": Qt.AlignmentFlag.AlignLeft,
    "centro": Qt.AlignmentFlag.AlignHCenter,
    "direita": Qt.AlignmentFlag.AlignRight,
    "justificado": Qt.AlignmentFlag.AlignJustify,
}
_ALINH_QT_PARA = {v: k for k, v in _ALINH_PARA_QT.items()}
P = QTextFormat.Property


def garantir_app() -> QGuiApplication:
    return QGuiApplication.instance() or QGuiApplication([])


def modelo_para_qt(doc: Documento) -> QTextDocument:
    garantir_app()
    qdoc = QTextDocument()
    cur = QTextCursor(qdoc)
    for i, p in enumerate(doc.paragrafos):
        if i > 0:
            cur.insertBlock()
        bf = QTextBlockFormat()
        if p.alinhamento is not None:
            bf.setAlignment(_ALINH_PARA_QT[p.alinhamento])
        if p.recuo_esquerdo_tw is not None:
            bf.setLeftMargin(p.recuo_esquerdo_tw * PX_POR_TWIP)
        if p.recuo_primeira_linha_tw is not None:
            bf.setTextIndent(p.recuo_primeira_linha_tw * PX_POR_TWIP)
        if p.espaco_antes_tw is not None:
            bf.setTopMargin(p.espaco_antes_tw * PX_POR_TWIP)
        if p.espaco_depois_tw is not None:
            bf.setBottomMargin(p.espaco_depois_tw * PX_POR_TWIP)
        cur.setBlockFormat(bf)
        for r in p.runs:
            cf = QTextCharFormat()
            if r.negrito is not None:
                cf.setFontWeight(QFont.Weight.Bold if r.negrito else QFont.Weight.Normal)
            if r.italico is not None:
                cf.setFontItalic(r.italico)
            if r.sublinhado is not None:
                # setFontUnderline(False) NAO grava "sem sublinhado": o estilo explicito e necessario.
                cf.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline if r.sublinhado
                                     else QTextCharFormat.UnderlineStyle.NoUnderline)
            if r.tamanho_pt_meio is not None:
                cf.setFontPointSize(r.tamanho_pt_meio / 2)
            if r.fonte:
                cf.setFontFamilies([r.fonte])
            if r.cor_hex is not None:
                cf.setForeground(QBrush(QColor("#" + r.cor_hex)))
            if r.texto:
                cur.insertText(r.texto.replace("\n", " "), cf)
    return qdoc


def _twips(px: float) -> int:
    return round(px * 15)


def qt_para_modelo(qdoc: QTextDocument) -> Documento:
    paras: list[Paragrafo] = []
    blk = qdoc.begin()
    while blk.isValid():
        bf = blk.blockFormat()
        p = Paragrafo()
        if bf.hasProperty(P.BlockAlignment):
            p.alinhamento = _ALINH_QT_PARA.get(bf.alignment())
        if bf.hasProperty(P.BlockLeftMargin):
            p.recuo_esquerdo_tw = _twips(bf.leftMargin())
        if bf.hasProperty(P.TextIndent):
            p.recuo_primeira_linha_tw = _twips(bf.textIndent())
        if bf.hasProperty(P.BlockTopMargin):
            p.espaco_antes_tw = _twips(bf.topMargin())
        if bf.hasProperty(P.BlockBottomMargin):
            p.espaco_depois_tw = _twips(bf.bottomMargin())
        it = blk.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                cf = frag.charFormat()
                run = Run(texto=frag.text().replace(" ", "\n"))
                if cf.hasProperty(P.FontWeight):
                    run.negrito = cf.fontWeight() >= 600
                if cf.hasProperty(P.FontItalic):
                    run.italico = cf.fontItalic()
                if cf.hasProperty(P.TextUnderlineStyle):
                    run.sublinhado = (cf.underlineStyle()
                                      != QTextCharFormat.UnderlineStyle.NoUnderline)
                if cf.hasProperty(P.FontPointSize):
                    run.tamanho_pt_meio = round(cf.fontPointSize() * 2)
                if cf.hasProperty(P.FontFamilies):
                    fams = cf.fontFamilies()
                    run.fonte = fams[0] if fams else None
                elif cf.hasProperty(P.FontFamily):
                    run.fonte = cf.fontFamily()
                if cf.hasProperty(P.ForegroundBrush):
                    run.cor_hex = cf.foreground().color().name()[1:].upper()
                p.runs.append(run)
            it += 1
        paras.append(p)
        blk = blk.next()
    return Documento(paragrafos=paras)
