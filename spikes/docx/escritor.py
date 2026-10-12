"""Escritor OOXML proprio do spike B: Documento -> bytes de .docx (lxml + zipfile).

Nao usa python-docx. Pacote minimo: Content_Types, _rels, document, styles,
settings (compat 15, pt-BR), core e app.
"""
from __future__ import annotations

import datetime as _dt
import io
import re
import zipfile

from lxml import etree

from modelo import Documento, Paragrafo, Run

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
PKG_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC = "http://purl.org/dc/elements/1.1/"
DCT = "http://purl.org/dc/terms/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
EP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

# Ordem obrigatoria dos filhos (fato 10; conferida contra os successors do python-docx 1.2.0).
ORDEM_PPR = [
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl",
    "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens",
    "kinsoku", "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN",
    "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind", "contextualSpacing",
    "mirrorIndents", "suppressOverlap", "jc", "textDirection", "textAlignment",
    "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange",
]
ORDEM_RPR = [
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike",
    "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden",
    "color", "spacing", "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect",
    "bdr", "shd", "fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout",
    "specVanish", "oMath",
]

_JC = {"esquerda": "left", "centro": "center", "direita": "right", "justificado": "both"}
# Controles invalidos em XML 1.0 e surrogates soltos (nao codificaveis em UTF-8).
_CONTROLE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿\ud800-\udfff]")
_SEPARADORES = re.compile(r"(\t|\n)")
_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_ZIP_DATA = (1980, 1, 1, 0, 0, 0)  # data fixa: saida byte-identica entre gravacoes


def _q(local: str) -> str:
    return "{%s}%s" % (W, local)


def ordenar_filhos(elemento, ordem: list[str]) -> None:
    """Reordena os filhos de `elemento` conforme `ordem` (estavel)."""
    indice = {_q(nome): i for i, nome in enumerate(ordem)}
    filhos = list(elemento)
    for f in filhos:
        if f.tag not in indice:
            raise ValueError(f"filho inesperado em {etree.QName(elemento).localname}: {f.tag}")
    filhos.sort(key=lambda f: indice[f.tag])
    for f in filhos:
        elemento.remove(f)
    for f in filhos:
        elemento.append(f)


def _marcar_espaco(t, texto: str) -> None:
    """xml:space="preserve" quando ha espaco nas pontas (fato 13). Ponto de sabotagem do teste."""
    if texto != texto.strip():
        t.set("{%s}space" % XML_NS, "preserve")


def _conteudo_run(r, texto: str, avisos: list[str]) -> None:
    limpo = texto.replace("\r\n", "\n").replace("\r", "\n")
    limpo, n = _CONTROLE.subn("", limpo)
    if n:
        avisos.append(f"CONTROLE_REMOVIDO:{n}")
    for parte in _SEPARADORES.split(limpo):
        if parte == "":
            continue
        if parte == "\t":
            etree.SubElement(r, _q("tab"))
        elif parte == "\n":
            etree.SubElement(r, _q("br"))
        else:
            t = etree.SubElement(r, _q("t"))
            _marcar_espaco(t, parte)
            t.text = parte


def _run(paragrafo_el, run: Run, avisos: list[str]) -> None:
    r = etree.SubElement(paragrafo_el, _q("r"))
    rpr = etree.Element(_q("rPr"))
    if run.sublinhado is not None:
        etree.SubElement(rpr, _q("u")).set(_q("val"), "single" if run.sublinhado else "none")
    if run.negrito is not None:
        b = etree.SubElement(rpr, _q("b"))
        if not run.negrito:
            b.set(_q("val"), "0")
    if run.italico is not None:
        i = etree.SubElement(rpr, _q("i"))
        if not run.italico:
            i.set(_q("val"), "0")
    if run.fonte:
        rf = etree.SubElement(rpr, _q("rFonts"))
        for atr in ("ascii", "hAnsi", "eastAsia", "cs"):
            rf.set(_q(atr), run.fonte)
    if run.cor_hex is not None:
        if not _HEX6.fullmatch(run.cor_hex):
            raise ValueError(f"cor_hex invalida: {run.cor_hex!r}")
        etree.SubElement(rpr, _q("color")).set(_q("val"), run.cor_hex.upper())
    if run.tamanho_pt_meio is not None:
        etree.SubElement(rpr, _q("sz")).set(_q("val"), str(int(run.tamanho_pt_meio)))
    if len(rpr):
        ordenar_filhos(rpr, ORDEM_RPR)
        r.append(rpr)
    _conteudo_run(r, run.texto, avisos)


def _paragrafo(body, p: Paragrafo, avisos: list[str]) -> None:
    pe = etree.SubElement(body, _q("p"))
    ppr = etree.Element(_q("pPr"))
    # Montado fora de ordem de proposito: ordenar_filhos e que garante a sequencia.
    if p.alinhamento is not None:
        etree.SubElement(ppr, _q("jc")).set(_q("val"), _JC[p.alinhamento])
    if p.recuo_esquerdo_tw is not None or p.recuo_primeira_linha_tw is not None:
        ind = etree.SubElement(ppr, _q("ind"))
        if p.recuo_esquerdo_tw is not None:
            ind.set(_q("left"), str(int(p.recuo_esquerdo_tw)))
        if p.recuo_primeira_linha_tw is not None:
            v = int(p.recuo_primeira_linha_tw)
            if v >= 0:
                ind.set(_q("firstLine"), str(v))
            else:
                ind.set(_q("hanging"), str(-v))
    if p.espaco_antes_tw is not None or p.espaco_depois_tw is not None:
        sp = etree.SubElement(ppr, _q("spacing"))
        if p.espaco_antes_tw is not None:
            sp.set(_q("before"), str(int(p.espaco_antes_tw)))
        if p.espaco_depois_tw is not None:
            sp.set(_q("after"), str(int(p.espaco_depois_tw)))
    if len(ppr):
        ordenar_filhos(ppr, ORDEM_PPR)
        pe.append(ppr)
    for run in p.runs:
        _run(pe, run, avisos)


def _xml(raiz) -> bytes:
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)


def _document_xml(doc: Documento, avisos: list[str]) -> bytes:
    raiz = etree.Element(_q("document"), nsmap={"w": W})
    body = etree.SubElement(raiz, _q("body"))
    for p in doc.paragrafos:
        _paragrafo(body, p, avisos)
    sect = etree.SubElement(body, _q("sectPr"))
    pg = etree.SubElement(sect, _q("pgSz"))
    pg.set(_q("w"), "11906")
    pg.set(_q("h"), "16838")
    mar = etree.SubElement(sect, _q("pgMar"))
    for nome, valor in (("top", 1417), ("right", 1134), ("bottom", 1134), ("left", 1701),
                        ("header", 708), ("footer", 708), ("gutter", 0)):
        mar.set(_q(nome), str(valor))
    return _xml(raiz)


def _styles_xml() -> bytes:
    raiz = etree.Element(_q("styles"), nsmap={"w": W})
    dd = etree.SubElement(raiz, _q("docDefaults"))
    rpd = etree.SubElement(dd, _q("rPrDefault"))
    rpr = etree.SubElement(rpd, _q("rPr"))
    rf = etree.SubElement(rpr, _q("rFonts"))
    for atr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rf.set(_q(atr), "Calibri")
    etree.SubElement(rpr, _q("sz")).set(_q("val"), "22")
    etree.SubElement(rpr, _q("szCs")).set(_q("val"), "22")
    lang = etree.SubElement(rpr, _q("lang"))
    lang.set(_q("val"), "pt-BR")
    lang.set(_q("eastAsia"), "pt-BR")
    lang.set(_q("bidi"), "ar-SA")

    def estilo(tipo, sid, nome, padrao=True, extra=()):
        s = etree.SubElement(raiz, _q("style"))
        s.set(_q("type"), tipo)
        if padrao:
            s.set(_q("default"), "1")
        s.set(_q("styleId"), sid)
        etree.SubElement(s, _q("name")).set(_q("val"), nome)
        for tag, val in extra:
            el = etree.SubElement(s, _q(tag))
            if val is not None:
                el.set(_q("val"), val)
        return s

    estilo("paragraph", "Normal", "Normal", extra=[("qFormat", None)])
    estilo("character", "DefaultParagraphFont", "Default Paragraph Font",
           extra=[("uiPriority", "1"), ("semiHidden", None), ("unhideWhenUsed", None)])
    tbl = estilo("table", "TableNormal", "Normal Table",
                 extra=[("uiPriority", "99"), ("semiHidden", None), ("unhideWhenUsed", None)])
    tp = etree.SubElement(tbl, _q("tblPr"))
    ti = etree.SubElement(tp, _q("tblInd"))
    ti.set(_q("w"), "0")
    ti.set(_q("type"), "dxa")
    cm = etree.SubElement(tp, _q("tblCellMar"))
    for lado, val in (("top", "0"), ("left", "108"), ("bottom", "0"), ("right", "108")):
        el = etree.SubElement(cm, _q(lado))
        el.set(_q("w"), val)
        el.set(_q("type"), "dxa")
    estilo("numbering", "NoList", "No List",
           extra=[("uiPriority", "99"), ("semiHidden", None), ("unhideWhenUsed", None)])
    return _xml(raiz)


def _settings_xml() -> bytes:
    raiz = etree.Element(_q("settings"), nsmap={"w": W})
    etree.SubElement(raiz, _q("zoom")).set(_q("percent"), "100")
    etree.SubElement(raiz, _q("defaultTabStop")).set(_q("val"), "708")
    etree.SubElement(raiz, _q("characterSpacingControl")).set(_q("val"), "doNotCompress")
    compat = etree.SubElement(raiz, _q("compat"))
    cs = etree.SubElement(compat, _q("compatSetting"))
    cs.set(_q("name"), "compatibilityMode")
    cs.set(_q("uri"), "http://schemas.microsoft.com/office/word")
    cs.set(_q("val"), "15")
    etree.SubElement(raiz, _q("themeFontLang")).set(_q("val"), "pt-BR")
    return _xml(raiz)


def _core_xml(doc: Documento, criado: str, modificado: str) -> bytes:
    raiz = etree.Element("{%s}coreProperties" % CP,
                         nsmap={"cp": CP, "dc": DC, "dcterms": DCT, "xsi": XSI})
    etree.SubElement(raiz, "{%s}title" % DC).text = doc.titulo or None
    etree.SubElement(raiz, "{%s}creator" % DC).text = doc.autor or None
    for tag, valor in (("created", criado), ("modified", modificado)):
        el = etree.SubElement(raiz, "{%s}%s" % (DCT, tag))
        el.set("{%s}type" % XSI, "dcterms:W3CDTF")
        el.text = valor
    return _xml(raiz)


def _app_xml() -> bytes:
    raiz = etree.Element("{%s}Properties" % EP, nsmap={None: EP})
    etree.SubElement(raiz, "{%s}Application" % EP).text = "EditDoc spike B"
    return _xml(raiz)


def _content_types_xml() -> bytes:
    raiz = etree.Element("{%s}Types" % PKG_CT, nsmap={None: PKG_CT})
    etree.SubElement(raiz, "{%s}Default" % PKG_CT, Extension="rels",
                     ContentType="application/vnd.openxmlformats-package.relationships+xml")
    etree.SubElement(raiz, "{%s}Default" % PKG_CT, Extension="xml", ContentType="application/xml")
    overrides = {
        "/word/document.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        "/word/styles.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml",
        "/word/settings.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml",
        "/docProps/core.xml": "application/vnd.openxmlformats-package.core-properties+xml",
        "/docProps/app.xml": "application/vnd.openxmlformats-officedocument.extended-properties+xml",
    }
    for parte, tipo in overrides.items():
        etree.SubElement(raiz, "{%s}Override" % PKG_CT, PartName=parte, ContentType=tipo)
    return _xml(raiz)


def _rels_xml(itens: list[tuple[str, str, str]]) -> bytes:
    raiz = etree.Element("{%s}Relationships" % PKG_REL, nsmap={None: PKG_REL})
    for rid, tipo, alvo in itens:
        etree.SubElement(raiz, "{%s}Relationship" % PKG_REL, Id=rid, Type=tipo, Target=alvo)
    return _xml(raiz)


_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
_RT_PKG = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"


def _agora_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _zip(partes: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for nome, dados in partes:
            info = zipfile.ZipInfo(nome, date_time=_ZIP_DATA)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            z.writestr(info, dados)
    return buf.getvalue()


def escrever_docx_com_avisos(doc: Documento) -> tuple[bytes, list[str]]:
    """Devolve (bytes do .docx, avisos da gravacao)."""
    avisos: list[str] = []
    agora = _agora_iso()
    criado = doc.criado_em or agora
    modificado = doc.modificado_em or agora
    partes = [
        ("[Content_Types].xml", _content_types_xml()),
        ("_rels/.rels", _rels_xml([
            ("rId1", _RT + "officeDocument", "word/document.xml"),
            ("rId2", _RT_PKG, "docProps/core.xml"),
            ("rId3", _RT + "extended-properties", "docProps/app.xml"),
        ])),
        ("word/document.xml", _document_xml(doc, avisos)),
        ("word/_rels/document.xml.rels", _rels_xml([
            ("rId1", _RT + "styles", "styles.xml"),
            ("rId2", _RT + "settings", "settings.xml"),
        ])),
        ("word/styles.xml", _styles_xml()),
        ("word/settings.xml", _settings_xml()),
        ("docProps/core.xml", _core_xml(doc, criado, modificado)),
        ("docProps/app.xml", _app_xml()),
    ]
    return _zip(partes), avisos


def escrever_docx(doc: Documento) -> bytes:
    return escrever_docx_com_avisos(doc)[0]
