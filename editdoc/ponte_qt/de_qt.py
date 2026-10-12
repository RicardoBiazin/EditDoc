"""QTextDocument -> modelo. A volta de `para_qt`, sem perda do que o modelo guarda.

Runs vizinhos com a mesma formatacao ficam fundidos (o Qt ja os funde); quem
compara ida-e-volta usa `modelo.documento.normalizar` nos dois lados.
"""

from __future__ import annotations

from PySide6.QtGui import QTextBlockFormat, QTextCharFormat, QTextDocument, QTextFormat, QTextListFormat

from editdoc.modelo.documento import Documento, Paragrafo, Run
from editdoc.modelo.unidades import twips_de_px
from editdoc.ponte_qt.para_qt import LINHA_SEPARADORA

P = QTextFormat.Property
_PROPORCIONAL = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
_MARCAS = {
    QTextListFormat.Style.ListDisc,
    QTextListFormat.Style.ListCircle,
    QTextListFormat.Style.ListSquare,
}


def _alinhamento(bf: QTextBlockFormat) -> str | None:
    if not bf.hasProperty(P.BlockAlignment):
        return None
    from PySide6.QtCore import Qt
    flags = bf.alignment()
    if flags & Qt.AlignmentFlag.AlignHCenter:
        return "centro"
    if flags & Qt.AlignmentFlag.AlignRight:
        return "direita"
    if flags & Qt.AlignmentFlag.AlignJustify:
        return "justificado"
    if flags & Qt.AlignmentFlag.AlignLeft:
        return "esquerda"
    return None


def _run(frag_texto: str, cf: QTextCharFormat) -> Run:
    run = Run(texto=frag_texto.replace(LINHA_SEPARADORA, "\n"))
    if cf.hasProperty(P.FontWeight):
        run.negrito = cf.fontWeight() >= 600
    if cf.hasProperty(P.FontItalic):
        run.italico = cf.fontItalic()
    if cf.hasProperty(P.TextUnderlineStyle) or cf.hasProperty(P.FontUnderline):
        run.sublinhado = (cf.underlineStyle()
                          != QTextCharFormat.UnderlineStyle.NoUnderline)
    if cf.hasProperty(P.FontStrikeOut):
        run.tachado = cf.fontStrikeOut()
    if cf.hasProperty(P.TextVerticalAlignment):
        va = cf.verticalAlignment()
        run.subscrito = va == QTextCharFormat.VerticalAlignment.AlignSubScript
        run.sobrescrito = va == QTextCharFormat.VerticalAlignment.AlignSuperScript
    if cf.hasProperty(P.FontPointSize):
        run.tamanho_meio_pt = round(cf.fontPointSize() * 2)
    if cf.hasProperty(P.FontFamilies):
        fams = cf.fontFamilies()
        run.fonte = fams[0] if fams else None
    if cf.hasProperty(P.ForegroundBrush):
        run.cor_hex = cf.foreground().color().name()[1:].upper()
    return run


def _paragrafo(bloco) -> Paragrafo:
    bf = bloco.blockFormat()
    p = Paragrafo()
    p.alinhamento = _alinhamento(bf)
    if bf.hasProperty(P.BlockLeftMargin):
        p.recuo_esquerdo_tw = twips_de_px(bf.leftMargin())
    if bf.hasProperty(P.TextIndent):
        p.recuo_primeira_linha_tw = twips_de_px(bf.textIndent())
    if bf.hasProperty(P.BlockTopMargin):
        p.espaco_antes_tw = twips_de_px(bf.topMargin())
    if bf.hasProperty(P.BlockBottomMargin):
        p.espaco_depois_tw = twips_de_px(bf.bottomMargin())
    if (bf.hasProperty(P.LineHeight) and bf.lineHeightType() == _PROPORCIONAL):
        p.espacamento_linha_pct = round(bf.lineHeight())
    lista = bloco.textList()
    if lista is not None:
        p.numeracao = ("marcadores" if lista.format().style() in _MARCAS
                       else "numeracao")
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and frag.text():
            p.runs.append(_run(frag.text(), frag.charFormat()))
        it += 1
    return p


def extrair(documento_qt: QTextDocument) -> Documento:
    paragrafos: list[Paragrafo] = []
    bloco = documento_qt.begin()
    while bloco.isValid():
        paragrafos.append(_paragrafo(bloco))
        bloco = bloco.next()
    return Documento(paragrafos=paragrafos)
