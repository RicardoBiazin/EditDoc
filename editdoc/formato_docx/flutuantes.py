"""Objetos flutuantes (0.1.7): ler do XML do objeto opaco a posicao e o desenho. Sem Qt.

So' leitura: o XML do objeto (o `w:r` guardado em `ObjetoOpaco.xml`) volta ao arquivo igual;
aqui so' se tira dele o que a tela precisa para pintar o objeto onde o Word pinta.

- `ler(xml)` devolve `Flutuante` (ancoragem + figura) ou None (objeto na linha, equacao).
  No mc:AlternateContent vale o ramo Choice (o DrawingML que o Word mostra); o VML do
  Fallback so' e' lido quando nao ha' DrawingML.
- A ancoragem do DrawingML vem do wp:anchor; a do VML, do atributo style (position:absolute,
  margin-left/top, mso-position-horizontal(-relative), width/height, z-index, w10:wrap).
- A figura (`Figura`) descreve o que pintar: imagem (rId do blip e recorte a:srcRect),
  forma (geometria predefinida a:prstGeom, preenchimento e contorno, inclusive pela
  referencia de estilo wps:style), caixa de texto (o mesmo, mais as margens internas do
  wps:bodyPr e o alinhamento vertical), grupo (os filhos com a:chOff/a:chExt) e o resto
  (grafico, SmartArt, tela de desenho), que a tela pinta com a previa ou um quadro rotulado.
- Cores: a:srgbClr, a:schemeClr (pelo tema do arquivo), a:sysClr, a:prstClr e os
  modificadores lumMod, lumOff, shade, tint e alpha; no VML, #rrggbb e os nomes basicos.
"""

from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass, field

from lxml import etree

from editdoc.formato_docx.nomes import (A_NS, MC_NS, PIC_NS, R_NS, V_NS, W, WP14_NS, WP_NS,
                                        WPC_NS, WPG_NS, WPS_NS, q)
from editdoc.modelo.flutuantes import Ancoragem

W10_NS = "urn:schemas-microsoft-com:office:word"
_AC = "{%s}AlternateContent" % MC_NS
_CHOICE = "{%s}Choice" % MC_NS
_FALLBACK = "{%s}Fallback" % MC_NS
_WP = "{%s}%%s" % WP_NS
_A = "{%s}%%s" % A_NS
_V = "{%s}%%s" % V_NS
#: Geometrias predefinidas que a tela desenha. As outras viram retangulo (limite registrado).
GEOMETRIAS = {"rect", "roundRect", "ellipse", "line", "straightConnector1", "triangle",
              "rtTriangle", "diamond", "parallelogram", "trapezoid", "pentagon", "hexagon",
              "octagon", "rightArrow", "leftArrow", "upArrow", "downArrow", "leftRightArrow",
              "chevron", "homePlate", "plus", "snip1Rect", "round1Rect", "round2SameRect",
              "flowChartProcess", "flowChartAlternateProcess", "flowChartDecision",
              "flowChartTerminator", "bentConnector3", "curvedConnector3", "frame"}
#: Espessura de linha das referencias de estilo do tema Office (lnStyleLst), em EMU.
_LINHA_DO_ESTILO = {1: 6350, 2: 12700, 3: 19050}
#: Cores do esquema padrao do Office (2013+), para arquivo sem tema.
CORES_PADRAO = {"dk1": "000000", "lt1": "FFFFFF", "dk2": "44546A", "lt2": "E7E6E6",
                "accent1": "4472C4", "accent2": "ED7D31", "accent3": "A5A5A5",
                "accent4": "FFC000", "accent5": "5B9BD5", "accent6": "70AD47",
                "hlink": "0563C1", "folHlink": "954F72"}
_MAPA_ESQUEMA = {"tx1": "dk1", "bg1": "lt1", "tx2": "dk2", "bg2": "lt2", "phClr": "accent1"}
_CORES_VML = {"black": "000000", "white": "FFFFFF", "red": "FF0000", "green": "008000",
              "lime": "00FF00", "blue": "0000FF", "yellow": "FFFF00", "gray": "808080",
              "grey": "808080", "silver": "C0C0C0", "maroon": "800000", "navy": "000080",
              "olive": "808000", "purple": "800080", "teal": "008080", "aqua": "00FFFF",
              "fuchsia": "FF00FF", "windowText": "000000", "window": "FFFFFF"}
_PRESET = {"black": "000000", "white": "FFFFFF", "red": "FF0000", "green": "008000",
           "blue": "0000FF", "yellow": "FFFF00", "gray": "808080", "darkGray": "A9A9A9",
           "lightGray": "D3D3D3", "orange": "FFA500"}
_MEDIDA = re.compile(r"^\s*(-?[0-9]*\.?[0-9]+)\s*(pt|in|cm|mm|px|emu)?\s*$", re.I)
_EMU_POR = {"pt": 12700, "in": 914400, "cm": 360000, "mm": 36000, "px": 9525, "emu": 1,
            None: 9525}
_EMU_MAX = 2000 * 360000  # 20 m: nada no papel passa disso


@dataclass(frozen=True)
class Cor:
    """Uma cor como o arquivo diz: tipo (srgb, esquema, sistema, preset) e modificadores."""
    tipo: str
    valor: str
    mods: tuple = ()


@dataclass
class Figura:
    """O que pintar. Medidas em EMU, na coordenada do pai (a do objeto: 0, 0, largura, altura).

    tipo: "imagem", "forma", "grupo" ou "outro". `texto`: a forma tem texto (w:txbxContent);
    `indice_texto` e' qual dos w:txbxContent de primeiro nivel do objeto (0 = o primeiro)."""
    tipo: str
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    geometria: str = "rect"
    ajustes: dict = field(default_factory=dict)
    rot: int = 0  # 60000 avos de grau
    flip_h: bool = False
    flip_v: bool = False
    preenchimento: Cor | None = None
    linha: Cor | None = None
    linha_larg: int = 9525
    linha_tracejada: str | None = None
    texto: bool = False
    indice_texto: int = 0
    margens: tuple = (91440, 45720, 91440, 45720)  # l, t, r, b
    ancora_texto: str = "t"
    quebra_texto: bool = True
    cor_texto: Cor | None = None
    rid: str | None = None
    recorte: tuple = (0, 0, 0, 0)  # l, t, r, b em milesimos de por cento
    filhos: list = field(default_factory=list)
    ch_off: tuple = (0, 0)
    ch_ext: tuple = (0, 0)
    rotulo: str = ""


@dataclass
class Flutuante:
    ancoragem: Ancoragem
    figura: Figura


# -- utilidades -------------------------------------------------------------------------

def _int(valor, padrao: int = 0) -> int:
    try:
        n = int(float(valor))
    except (TypeError, ValueError):
        return padrao
    return max(-_EMU_MAX, min(_EMU_MAX, n))


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _sim(valor, padrao: bool = False) -> bool:
    if valor is None:
        return padrao
    return str(valor).strip().lower() in ("1", "true", "t", "on")


def _ramo(item):
    """O ramo que o Word mostra: o Choice do AlternateContent (o primeiro com conteudo)."""
    for ac in item.iter(_AC):
        escolha = next((x for x in ac if x.tag == _CHOICE and len(x)), None)
        if escolha is not None:
            return escolha
    return item


def _sem_fallback(el):
    """Itera `el` sem entrar nos mc:Fallback (o VML repetido)."""
    pilha = [el]
    while pilha:
        x = pilha.pop()
        if x.tag == _FALLBACK:
            continue
        yield x
        pilha.extend(reversed([c for c in x if isinstance(c.tag, str)]))


# -- cores --------------------------------------------------------------------------------

def cor_de(pai) -> Cor | None:
    """A primeira cor DrawingML filha de `pai` (srgbClr, schemeClr, sysClr, prstClr, scrgbClr)."""
    if pai is None:
        return None
    for x in pai:
        loc = _local(x)
        mods = tuple((_local(m), _int(m.get("val"))) for m in x if isinstance(m.tag, str))
        if loc == "srgbClr":
            return Cor("srgb", (x.get("val") or "000000").upper(), mods)
        if loc == "schemeClr":
            return Cor("esquema", x.get("val") or "accent1", mods)
        if loc == "sysClr":
            return Cor("srgb", (x.get("lastClr") or "000000").upper(), mods)
        if loc == "prstClr":
            return Cor("srgb", _PRESET.get(x.get("val") or "", "000000"), mods)
        if loc == "scrgbClr":
            r, g, b = (min(100000, max(0, _int(x.get(c)))) for c in ("r", "g", "b"))
            return Cor("srgb", "%02X%02X%02X" % (round(r * 2.55e-3), round(g * 2.55e-3),
                                                 round(b * 2.55e-3)), mods)
        if loc == "hslClr":
            return Cor("srgb", "808080", mods)
    return None


def cor_vml(valor: str | None) -> Cor | None:
    """fillcolor/strokecolor do VML: "#rrggbb", "#rgb", "white", "black [3213]"..."""
    if not valor:
        return None
    v = valor.strip().split()[0] if valor.strip() else ""
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if re.fullmatch(r"[0-9a-fA-F]{6}", h):
            return Cor("srgb", h.upper())
        return None
    if v in _CORES_VML:
        return Cor("srgb", _CORES_VML[v])
    return None


def cores_do_tema(tema: bytes | None) -> dict:
    """{nome: "RRGGBB"} do a:clrScheme do theme1.xml; o padrao do Office no que faltar."""
    cores = dict(CORES_PADRAO)
    if not tema:
        return cores
    try:
        raiz = etree.fromstring(tema, etree.XMLParser(resolve_entities=False, no_network=True,
                                                      load_dtd=False))
    except (etree.LxmlError, ValueError):
        return cores
    esquema = next(raiz.iter(_A % "clrScheme"), None)
    if esquema is None:
        return cores
    for item in esquema:
        nome = _local(item)
        cor = cor_de(item)
        if nome and cor is not None and cor.tipo == "srgb":
            cores[nome] = cor.valor
    return cores


def _hex(valor: str) -> tuple[int, int, int]:
    try:
        return int(valor[0:2], 16), int(valor[2:4], 16), int(valor[4:6], 16)
    except (ValueError, IndexError):
        return 0, 0, 0


def resolver(cor: Cor | None, tema: dict | None = None) -> tuple[int, int, int, int] | None:
    """(r, g, b, alfa) de 0 a 255, com os modificadores aplicados. None = sem cor."""
    if cor is None:
        return None
    tema = tema or CORES_PADRAO
    if cor.tipo == "esquema":
        nome = _MAPA_ESQUEMA.get(cor.valor, cor.valor)
        r, g, b = _hex(tema.get(nome) or CORES_PADRAO.get(nome, "000000"))
    else:
        r, g, b = _hex(cor.valor)
    alfa = 255
    for nome, val in cor.mods:
        f = val / 100000.0
        if nome == "lumMod" or nome == "lumOff":
            hh, ll, ss = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
            ll = ll * f if nome == "lumMod" else ll + f
            ll = min(1.0, max(0.0, ll))
            rr, gg, bb = colorsys.hls_to_rgb(hh, ll, ss)
            r, g, b = round(rr * 255), round(gg * 255), round(bb * 255)
        elif nome == "shade":
            r, g, b = round(r * f), round(g * f), round(b * f)
        elif nome == "tint":
            r, g, b = (round(c + (255 - c) * (1 - f)) for c in (r, g, b))
        elif nome == "alpha":
            alfa = round(255 * min(1.0, max(0.0, f)))
    return (min(255, max(0, r)), min(255, max(0, g)), min(255, max(0, b)), alfa)


# -- DrawingML ----------------------------------------------------------------------------

def _ancoragem_drawingml(anc) -> Ancoragem:
    dados: dict = {}
    dados["dist"] = tuple(_int(anc.get(n)) for n in ("distT", "distB", "distL", "distR"))
    dados["atras"] = _sim(anc.get("behindDoc"))
    dados["z"] = _int(anc.get("relativeHeight"))
    dados["na_celula"] = _sim(anc.get("layoutInCell"), True)
    dados["sobrepor"] = _sim(anc.get("allowOverlap"), True)
    if _sim(anc.get("simplePos")):
        sp = anc.find(_WP % "simplePos")
        if sp is not None:
            dados["simples"] = (_int(sp.get("x")), _int(sp.get("y")))
    for eixo, nome in (("h", "positionH"), ("v", "positionV")):
        pos = anc.find(_WP % nome)
        if pos is None:
            continue
        dados[eixo + "_rel"] = pos.get("relativeFrom") or ("column" if eixo == "h" else "paragraph")
        for filho in pos:
            loc = _local(filho)
            if loc == "align":
                dados[eixo + "_alinh"] = (filho.text or "").strip() or None
            elif loc == "posOffset":
                dados[eixo + "_desloc"] = _int((filho.text or "0").strip())
            elif loc in ("pctPosHOffset", "pctPosVOffset"):
                dados[eixo + "_pct"] = _int((filho.text or "0").strip())
    ext = anc.find(_WP % "extent")
    if ext is not None:
        dados["largura"] = max(0, _int(ext.get("cx")))
        dados["altura"] = max(0, _int(ext.get("cy")))
    ef = anc.find(_WP % "effectExtent")
    if ef is not None:
        dados["efeito"] = tuple(_int(ef.get(n)) for n in ("l", "t", "r", "b"))
    for filho in anc:
        loc = _local(filho)
        if loc in ("wrapNone", "wrapSquare", "wrapTight", "wrapThrough", "wrapTopAndBottom"):
            dados["quebra"] = {"wrapNone": "none", "wrapSquare": "square", "wrapTight": "tight",
                               "wrapThrough": "through", "wrapTopAndBottom": "topbottom"}[loc]
            if filho.get("wrapText"):
                dados["lado"] = filho.get("wrapText")
            if loc in ("wrapSquare", "wrapTopAndBottom"):
                # As distancias do proprio wrap valem quando existem.
                d = list(dados.get("dist", (0, 0, 0, 0)))
                for i, n in enumerate(("distT", "distB", "distL", "distR")):
                    if filho.get(n) is not None:
                        d[i] = _int(filho.get(n))
                dados["dist"] = tuple(d)
    for nome, chave in (("sizeRelH", "largura"), ("sizeRelV", "altura")):
        rel = anc.find("{%s}%s" % (WP14_NS, nome))
        if rel is not None:
            pct = next((x for x in rel if _local(x) in ("pctWidth", "pctHeight")), None)
            valor = _int((pct.text or "0").strip()) if pct is not None else 0
            if valor > 0:
                dados["pct_" + chave] = valor
                dados["pct_" + chave + "_rel"] = rel.get("relativeFrom") or "margin"
    return Ancoragem(**dados)


def _xfrm(el) -> tuple:
    """(x, y, w, h, rot, flipH, flipV, chOff, chExt) de um a:xfrm (ou None)."""
    if el is None:
        return None
    off = el.find(_A % "off")
    ext = el.find(_A % "ext")
    ch_off = el.find(_A % "chOff")
    ch_ext = el.find(_A % "chExt")
    return (_int(off.get("x")) if off is not None else 0,
            _int(off.get("y")) if off is not None else 0,
            max(0, _int(ext.get("cx"))) if ext is not None else 0,
            max(0, _int(ext.get("cy"))) if ext is not None else 0,
            _int(el.get("rot")), _sim(el.get("flipH")), _sim(el.get("flipV")),
            (_int(ch_off.get("x")), _int(ch_off.get("y"))) if ch_off is not None else None,
            (_int(ch_ext.get("cx")), _int(ch_ext.get("cy"))) if ch_ext is not None else None)


def _preenchimento_e_linha(fig: Figura, sppr, estilo) -> None:
    """Preenchimento e contorno: o do spPr, senao o da referencia de estilo (wps:style)."""
    tem_preench = False
    if sppr is not None:
        for x in sppr:
            loc = _local(x)
            if loc == "noFill":
                fig.preenchimento, tem_preench = None, True
            elif loc == "solidFill":
                fig.preenchimento, tem_preench = cor_de(x), True
            elif loc == "gradFill":
                gs = next(x.iter(_A % "gs"), None)
                fig.preenchimento, tem_preench = cor_de(gs), True
            elif loc == "pattFill":
                fig.preenchimento, tem_preench = cor_de(x.find(_A % "fgClr")), True
            elif loc in ("blipFill", "grpFill"):
                fig.preenchimento, tem_preench = None, True
    ln = sppr.find(_A % "ln") if sppr is not None else None
    tem_linha = False
    if ln is not None:
        if ln.get("w") is not None:
            fig.linha_larg = max(0, _int(ln.get("w")))
        for x in ln:
            loc = _local(x)
            if loc == "noFill":
                fig.linha, tem_linha = None, True
            elif loc == "solidFill":
                fig.linha, tem_linha = cor_de(x), True
            elif loc == "gradFill":
                fig.linha, tem_linha = cor_de(next(x.iter(_A % "gs"), None)), True
            elif loc == "prstDash":
                valor = x.get("val") or "solid"
                fig.linha_tracejada = None if valor == "solid" else valor
    if estilo is not None:
        ref = estilo.find(_A % "fillRef")
        if not tem_preench and ref is not None and _int(ref.get("idx")) > 0:
            fig.preenchimento = cor_de(ref)
        ref = estilo.find(_A % "lnRef")
        if not tem_linha and ref is not None and _int(ref.get("idx")) > 0:
            fig.linha = cor_de(ref)
            if ln is None or ln.get("w") is None:
                fig.linha_larg = _LINHA_DO_ESTILO.get(_int(ref.get("idx")), 12700)
        ref = estilo.find(_A % "fontRef")
        if ref is not None:
            fig.cor_texto = cor_de(ref)


def _geometria(fig: Figura, sppr) -> None:
    if sppr is None:
        return
    prst = sppr.find(_A % "prstGeom")
    if prst is not None:
        fig.geometria = prst.get("prst") or "rect"
        for gd in prst.iter(_A % "gd"):
            fmla = gd.get("fmla") or ""
            if fmla.startswith("val "):
                fig.ajustes[gd.get("name") or ""] = _int(fmla[4:])
    elif sppr.find(_A % "custGeom") is not None:
        fig.geometria = "custom"


def _corpo_de_texto(fig: Figura, bodypr) -> None:
    if bodypr is None:
        return
    padrao = (91440, 45720, 91440, 45720)
    fig.margens = tuple(_int(bodypr.get(n), padrao[i]) if bodypr.get(n) is not None else padrao[i]
                        for i, n in enumerate(("lIns", "tIns", "rIns", "bIns")))
    fig.ancora_texto = {"ctr": "ctr", "b": "b", "dist": "ctr", "just": "ctr"}.get(
        bodypr.get("anchor") or "t", "t")
    fig.quebra_texto = (bodypr.get("wrap") or "square") != "none"


def _aplicar_xfrm(fig: Figura, xf, pai_w: int, pai_h: int) -> None:
    if xf is None:
        fig.w, fig.h = pai_w, pai_h
        return
    fig.x, fig.y, fig.w, fig.h, fig.rot, fig.flip_h, fig.flip_v = xf[:7]


class _Contador:
    def __init__(self) -> None:
        self.texto = 0


def _figura_de_forma(wsp, cont: _Contador, w: int, h: int) -> Figura:
    fig = Figura("forma")
    sppr = wsp.find("{%s}spPr" % WPS_NS)
    _aplicar_xfrm(fig, _xfrm(sppr.find(_A % "xfrm")) if sppr is not None else None, w, h)
    _geometria(fig, sppr)
    _preenchimento_e_linha(fig, sppr, wsp.find("{%s}style" % WPS_NS))
    _corpo_de_texto(fig, wsp.find("{%s}bodyPr" % WPS_NS))
    txbx = wsp.find("{%s}txbx" % WPS_NS)
    if txbx is not None and txbx.find(q("txbxContent")) is not None:
        fig.texto = True
        fig.indice_texto = cont.texto
        cont.texto += 1
    return fig


def _figura_de_imagem(pic, w: int, h: int) -> Figura:
    fig = Figura("imagem")
    sppr = pic.find("{%s}spPr" % PIC_NS)
    _aplicar_xfrm(fig, _xfrm(sppr.find(_A % "xfrm")) if sppr is not None else None, w, h)
    _geometria(fig, sppr)
    if sppr is not None:
        _preenchimento_e_linha(fig, sppr, None)
        fig.preenchimento = None
    blip_fill = pic.find("{%s}blipFill" % PIC_NS)
    if blip_fill is not None:
        blip = blip_fill.find(_A % "blip")
        if blip is not None:
            fig.rid = blip.get("{%s}embed" % R_NS)
        src = blip_fill.find(_A % "srcRect")
        if src is not None:
            fig.recorte = tuple(_int(src.get(n)) for n in ("l", "t", "r", "b"))
    return fig


def _figura_de_grupo(grp, cont: _Contador, w: int, h: int, sppr_tag: str) -> Figura:
    fig = Figura("grupo")
    gpr = grp.find(sppr_tag)
    xf = _xfrm(gpr.find(_A % "xfrm")) if gpr is not None else None
    _aplicar_xfrm(fig, xf, w, h)
    fig.ch_off = xf[7] if xf is not None and xf[7] is not None else (0, 0)
    fig.ch_ext = xf[8] if xf is not None and xf[8] is not None else (fig.w, fig.h)
    for filho in grp:
        loc = _local(filho)
        ns = etree.QName(filho).namespace if isinstance(filho.tag, str) else ""
        if loc == "wsp":
            fig.filhos.append(_figura_de_forma(filho, cont, fig.ch_ext[0], fig.ch_ext[1]))
        elif loc == "pic":
            fig.filhos.append(_figura_de_imagem(filho, fig.ch_ext[0], fig.ch_ext[1]))
        elif loc == "grpSp":
            fig.filhos.append(_figura_de_grupo(filho, cont, fig.ch_ext[0], fig.ch_ext[1],
                                               "{%s}grpSpPr" % ns))
        elif loc == "graphicFrame":
            sub = Figura("outro", rotulo="Objeto")
            xf2 = _xfrm(filho.find("{%s}xfrm" % ns))
            _aplicar_xfrm(sub, xf2, fig.ch_ext[0], fig.ch_ext[1])
            fig.filhos.append(sub)
    return fig


def _figura_drawingml(anc, largura: int, altura: int) -> Figura:
    dados = next(anc.iter(_A % "graphicData"), None)
    if dados is None:
        return Figura("outro", w=largura, h=altura, rotulo="Objeto")
    cont = _Contador()
    for filho in dados:
        loc = _local(filho)
        ns = etree.QName(filho).namespace if isinstance(filho.tag, str) else ""
        if loc == "wsp" and ns == WPS_NS:
            fig = _figura_de_forma(filho, cont, largura, altura)
        elif loc == "pic" and ns == PIC_NS:
            fig = _figura_de_imagem(filho, largura, altura)
        elif loc == "wgp" and ns == WPG_NS:
            fig = _figura_de_grupo(filho, cont, largura, altura, "{%s}grpSpPr" % WPG_NS)
        elif ns == WPC_NS:
            fig = Figura("outro", rotulo="Tela de desenho")
        else:
            continue
        # O objeto inteiro ocupa o wp:extent: o xfrm de cima so' da' rotacao e espelho.
        fig.x, fig.y, fig.w, fig.h = 0, 0, largura, altura
        return fig
    uri = dados.get("uri") or ""
    rotulo = "Gráfico" if "chart" in uri else "SmartArt" if "diagram" in uri else "Objeto"
    return Figura("outro", w=largura, h=altura, rotulo=rotulo)


# -- VML ----------------------------------------------------------------------------------

def estilo_vml(estilo: str) -> dict:
    """O atributo style do VML em dicionario (chaves em minusculas)."""
    saida = {}
    for parte in (estilo or "").split(";"):
        if ":" in parte:
            k, v = parte.split(":", 1)
            saida[k.strip().lower()] = v.strip()
    return saida


def medida_vml(valor: str | None) -> int | None:
    """"72pt", "1in", "2.5cm", "10px" ou numero em EMU; None se nao se le."""
    if valor is None:
        return None
    m = _MEDIDA.match(valor)
    if not m:
        return None
    try:
        return max(-_EMU_MAX, min(_EMU_MAX, round(float(m.group(1)) * _EMU_POR[
            m.group(2).lower() if m.group(2) else None])))
    except (ValueError, KeyError):
        return None


_H_REL_VML = {"margin": "margin", "page": "page", "text": "column", "char": "character",
              "left-margin-area": "leftMargin", "right-margin-area": "rightMargin",
              "inner-margin-area": "insideMargin", "outer-margin-area": "outsideMargin"}
_V_REL_VML = {"margin": "margin", "page": "page", "text": "paragraph", "line": "line",
              "top-margin-area": "topMargin", "bottom-margin-area": "bottomMargin",
              "inner-margin-area": "insideMargin", "outer-margin-area": "outsideMargin"}
_PCT_REL_VML = {"margin": "margin", "page": "page", "left-margin-area": "leftMargin",
                "right-margin-area": "rightMargin", "inner-margin-area": "insideMargin",
                "outer-margin-area": "outsideMargin", "top-margin-area": "topMargin",
                "bottom-margin-area": "bottomMargin"}


def _ancoragem_vml(forma, est: dict) -> Ancoragem:
    dados: dict = {"vml": True}
    x = (medida_vml(est.get("margin-left")) or 0) + (medida_vml(est.get("left")) or 0)
    y = (medida_vml(est.get("margin-top")) or 0) + (medida_vml(est.get("top")) or 0)
    dados["h_desloc"], dados["v_desloc"] = x, y
    dados["largura"] = max(0, medida_vml(est.get("width")) or 0)
    dados["altura"] = max(0, medida_vml(est.get("height")) or 0)
    alinh = est.get("mso-position-horizontal", "absolute")
    if alinh in ("left", "center", "right", "inside", "outside"):
        dados["h_alinh"] = alinh
    dados["h_rel"] = _H_REL_VML.get(est.get("mso-position-horizontal-relative", "text"), "column")
    alinh = est.get("mso-position-vertical", "absolute")
    if alinh in ("top", "center", "bottom", "inside", "outside"):
        dados["v_alinh"] = alinh
    dados["v_rel"] = _V_REL_VML.get(est.get("mso-position-vertical-relative", "text"), "paragraph")
    try:
        z = int(float(est.get("z-index", "0")))
    except ValueError:
        z = 0
    dados["z"] = z
    dados["atras"] = z < 0
    for chave, eixo in (("mso-width-percent", "largura"), ("mso-height-percent", "altura")):
        try:
            pct = int(float(est.get(chave, "0")))
        except ValueError:
            pct = 0
        if pct > 0:
            # Decimos de por cento no VML (1000 = 100%); o modelo usa milesimos.
            dados["pct_" + eixo] = pct * 100
            rel = est.get("mso-width-relative" if eixo == "largura" else "mso-height-relative")
            dados["pct_" + eixo + "_rel"] = _PCT_REL_VML.get(rel or "margin", "margin")
    dist = []
    for lado in ("top", "bottom", "left", "right"):
        valor = medida_vml(est.get("mso-wrap-distance-" + lado))
        dist.append(valor if valor is not None else (0 if lado in ("top", "bottom") else 114300))
    dados["dist"] = tuple(dist)
    quebra = forma.find("{%s}wrap" % W10_NS)
    if quebra is not None:
        tipo = quebra.get("type") or "none"
        dados["quebra"] = {"square": "square", "tight": "tight", "through": "through",
                           "topAndBottom": "topbottom"}.get(tipo, "none")
        lado = quebra.get("side")
        if lado in ("left", "right", "largest"):
            dados["lado"] = lado
    return Ancoragem(**dados)


_GEOMETRIA_VML = {"rect": "rect", "roundrect": "roundRect", "oval": "ellipse", "line": "line",
                  "image": "rect", "shape": "rect", "polyline": "custom", "arc": "custom",
                  "curve": "custom"}


def _figura_vml(forma, largura: int, altura: int, cont: _Contador) -> Figura:
    loc = _local(forma)
    imagem = forma.find(_V % "imagedata")
    fig = Figura("imagem" if imagem is not None and loc in ("shape", "image", "rect") else "forma",
                 w=largura, h=altura, geometria=_GEOMETRIA_VML.get(loc, "rect"))
    if imagem is not None:
        fig.rid = imagem.get("{%s}id" % R_NS) or imagem.get(
            "{urn:schemas-microsoft-com:office:office}relid")
        corte = [imagem.get(n) for n in ("cropleft", "croptop", "cropright", "cropbottom")]
        fig.recorte = tuple(_fracao_vml(c) for c in corte)
    preench = forma.find(_V % "fill")
    filled = forma.get("filled")
    if preench is not None and preench.get("on") is not None:
        filled = preench.get("on")
    cor = forma.get("fillcolor") or (preench.get("color") if preench is not None else None)
    if _sim(filled, True) and fig.tipo != "imagem":
        fig.preenchimento = cor_vml(cor) if cor else Cor("srgb", "FFFFFF")
    traco = forma.find(_V % "stroke")
    stroked = forma.get("stroked")
    if traco is not None and traco.get("on") is not None:
        stroked = traco.get("on")
    cor = forma.get("strokecolor") or (traco.get("color") if traco is not None else None)
    if _sim(stroked, True) and fig.tipo != "imagem":
        fig.linha = cor_vml(cor) if cor else Cor("srgb", "000000")
        peso = forma.get("strokeweight") or (traco.get("weight") if traco is not None else None)
        fig.linha_larg = medida_vml(peso) if peso else 9525
    caixa = forma.find(_V % "textbox")
    if caixa is not None and caixa.find(q("txbxContent")) is not None:
        fig.texto = True
        fig.indice_texto = cont.texto
        cont.texto += 1
        inset = [medida_vml(v) for v in (caixa.get("inset") or "").split(",")]
        padrao = (91440, 45720, 91440, 45720)
        fig.margens = tuple(inset[i] if i < len(inset) and inset[i] is not None else padrao[i]
                            for i in range(4))
    est = estilo_vml(forma.get("style") or "")
    fig.ancora_texto = {"middle": "ctr", "bottom": "b"}.get(est.get("v-text-anchor", "top"), "t")
    try:
        fig.rot = round(float(est.get("rotation", "0")) * 60000)
    except ValueError:
        fig.rot = 0
    fig.flip_h = "x" in est.get("flip", "")
    fig.flip_v = "y" in est.get("flip", "")
    return fig


def _fracao_vml(valor: str | None) -> int:
    """cropleft do VML ("0.1", "6554f" em 1/65536) em milesimos de por cento."""
    if not valor:
        return 0
    try:
        if valor.endswith("f"):
            return round(float(valor[:-1]) / 65536 * 100000)
        return round(float(valor) * 100000)
    except ValueError:
        return 0


# -- entrada ------------------------------------------------------------------------------

def _parse(xml: bytes):
    return etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True,
                                                 load_dtd=False, huge_tree=False))


def ler(xml: bytes) -> Flutuante | None:
    """A posicao e o desenho do objeto flutuante, ou None se o objeto nao flutua."""
    try:
        raiz = _parse(xml)
    except (etree.LxmlError, ValueError):
        return None
    ramo = _ramo(raiz)
    anc = next((x for x in _sem_fallback(ramo) if x.tag == _WP % "anchor"), None)
    if anc is not None:
        ancoragem = _ancoragem_drawingml(anc)
        return Flutuante(ancoragem, _figura_drawingml(anc, ancoragem.largura, ancoragem.altura))
    if next((x for x in _sem_fallback(ramo) if x.tag == _WP % "inline"), None) is not None:
        return None
    # VML: a primeira forma com position:absolute (fora do v:shapetype, que e' so' modelo).
    for forma in raiz.iter():
        if not isinstance(forma.tag, str) or etree.QName(forma).namespace != V_NS:
            continue
        if _local(forma) == "shapetype":
            continue
        est = estilo_vml(forma.get("style") or "")
        if est.get("position", "").lower() != "absolute":
            continue
        pai = forma.getparent()
        if pai is not None and etree.QName(pai).namespace == V_NS and _local(pai) == "group":
            continue  # filho de grupo: o grupo e' que se posiciona
        ancoragem = _ancoragem_vml(forma, est)
        cont = _Contador()
        if _local(forma) == "group":
            fig = Figura("outro", w=ancoragem.largura, h=ancoragem.altura,
                         rotulo="Grupo de formas")
        else:
            fig = _figura_vml(forma, ancoragem.largura, ancoragem.altura, cont)
        return Flutuante(ancoragem, fig)
    return None


def caixas_de_texto(xml: bytes) -> list:
    """Os w:txbxContent que a tela mostra, na ordem do indice_texto das figuras."""
    try:
        raiz = _parse(xml)
    except (etree.LxmlError, ValueError):
        return []
    ramo = _ramo(raiz)
    saida = []
    for x in _sem_fallback(ramo):
        if x.tag == q("txbxContent"):
            pai = x.getparent()
            dentro = False
            while pai is not None and pai is not ramo:
                if pai.tag == q("txbxContent"):
                    dentro = True
                    break
                pai = pai.getparent()
            if not dentro:
                saida.append(x)
    if not saida and ramo is not raiz:
        # So' VML (sem Choice com caixa): o v:textbox.
        saida = [x for x in raiz.iter(q("txbxContent"))][:1]
    return saida


__all__ = ["Cor", "Figura", "Flutuante", "ler", "resolver", "cores_do_tema", "caixas_de_texto",
           "estilo_vml", "medida_vml", "W"]
