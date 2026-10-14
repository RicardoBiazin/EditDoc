"""Posicao, tamanho e quebra de texto de um objeto preservado (0.1.9). Sem Qt.

Mover ou redimensionar um objeto (com o mouse, o teclado ou o dialogo "Posicao e tamanho")
muda so' o que diz onde ele fica e de que tamanho e', dentro do XML guardado do objeto opaco
(`ObjetoOpaco.xml`). Todo o resto volta igual (c14n), como na 0.1.7.

DrawingML (wp:anchor e wp:inline):
- posicao: `wp:positionH/positionV` com um `wp:posOffset` (EMU). O `relativeFrom` fica o do
  arquivo quando quem chama passa o mesmo; o `wp:align` e o `wp14:pctPosHOffset` viram
  `wp:posOffset`, como o Word faz quando se arrasta um objeto alinhado. Com `simplePos="1"` muda
  o `wp:simplePos`.
- tamanho: `wp:extent`, e o `a:ext` do `a:xfrm` do desenho de cima (`pic:spPr`, `wps:spPr` ou,
  no grupo, `wpg:grpSpPr`, que mantem `chOff/chExt`: os filhos acompanham pela escala). O
  tamanho relativo (`wp14:pctWidth/pctHeight` maior que zero) passa a absoluto (zero).
- quebra: o elemento `wp:wrap*` e o `behindDoc`. Trocar entre "Alinhado ao texto" e as outras
  converte `wp:inline` em `wp:anchor` (com os atributos que o esquema exige: distancias,
  simplePos, relativeHeight unico, behindDoc, locked, layoutInCell, allowOverlap) e de volta. O
  `docPr`, o `cNvGraphicFramePr`, o `graphic`, o `effectExtent` e os ids `wp14` sao os mesmos.

VML (o objeto so' VML, e o `mc:Fallback` de um DrawingML, que o Word grava com o mesmo
desenho): o atributo `style` (`margin-left/top`, `width/height`, `mso-position-*`, `z-index`,
`position:absolute`) e o `w10:wrap`. Os outros itens do estilo ficam na ordem e com o texto de
origem.

Limites (`modelo/flutuantes.py`): deslocamento ate' 55,88 cm da referencia e tamanho de 1 px96
ao maior papel; o lado zero da linha reta continua zero.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, replace

from lxml import etree

from editdoc.formato_docx import flutuantes as fx
from editdoc.formato_docx import opacos
from editdoc.formato_docx.nomes import (A_NS, MC_NS, PIC_NS, R_NS, RT_IMAGEM, V_NS, W,
                                        WP14_NS, WP_NS, WPG_NS, WPS_NS, q)
from editdoc.modelo import flutuantes as mf
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.documento import Imagem, ObjetoOpaco, ParteOpaca

_WP = "{%s}%%s" % WP_NS
_A = "{%s}%%s" % A_NS
_W10 = "{%s}wrap" % fx.W10_NS
#: Quebras de texto da tela, na ordem da galeria do Word.
QUEBRAS = ("linha", "quadrado", "comprimido", "atraves", "superior_inferior", "atras", "frente")
ROTULOS_QUEBRA = {"linha": "Alinhado ao texto", "quadrado": "Quadrado", "comprimido": "Comprimido",
                  "atraves": "Através", "superior_inferior": "Superior e inferior",
                  "atras": "Atrás do texto", "frente": "Na frente do texto"}
_DML_DA_QUEBRA = {"quadrado": "wrapSquare", "comprimido": "wrapTight", "atraves": "wrapThrough",
                  "superior_inferior": "wrapTopAndBottom", "atras": "wrapNone",
                  "frente": "wrapNone"}
_QUEBRA_DO_DML = {"wrapSquare": "quadrado", "wrapTight": "comprimido", "wrapThrough": "atraves",
                  "wrapTopAndBottom": "superior_inferior"}
_VML_DA_QUEBRA = {"quadrado": "square", "comprimido": "tight", "atraves": "through",
                  "superior_inferior": "topAndBottom", "atras": "none", "frente": "none"}
_QUEBRA_DO_VML = {"square": "quadrado", "tight": "comprimido", "through": "atraves",
                  "topAndBottom": "superior_inferior"}
_WRAPS = ("wrapNone", "wrapSquare", "wrapTight", "wrapThrough", "wrapTopAndBottom")
#: relativeFrom do DrawingML -> mso-position-*-relative do VML.
_H_VML = {"margin": "margin", "page": "page", "column": "text", "character": "char",
          "leftMargin": "left-margin-area", "rightMargin": "right-margin-area",
          "insideMargin": "inner-margin-area", "outsideMargin": "outer-margin-area"}
_V_VML = {"margin": "margin", "page": "page", "paragraph": "text", "line": "line",
          "topMargin": "top-margin-area", "bottomMargin": "bottom-margin-area",
          "insideMargin": "inner-margin-area", "outsideMargin": "outer-margin-area"}
#: relativeHeight do primeiro objeto, como o Word (0xF000000).
Z_INICIAL = 251658240
_Z = re.compile(rb'relativeHeight="(\d+)"')
_INT32 = 2 ** 31 - 1


class PosicaoRecusada(ValueError):
    """A mudanca nao pode ser feita sem perda. A mensagem e' para o usuario."""


@dataclass(frozen=True)
class Mudanca:
    """O que muda. Medidas em EMU. None: fica como esta'."""
    #: (relativeFrom, posOffset)
    h: tuple | None = None
    v: tuple | None = None
    #: (x, y) do wp:simplePos, quando o objeto usa simplePos="1"
    simples: tuple | None = None
    #: (cx, cy)
    tamanho: tuple | None = None
    #: uma de QUEBRAS
    quebra: str | None = None
    #: relativeHeight do objeto que passa a flutuar (unico no documento)
    z: int | None = None


@dataclass(frozen=True)
class Estado:
    """Como o objeto esta' no arquivo: o que o dialogo mostra e o que o arraste respeita."""
    na_linha: bool
    quebra: str
    largura: int
    altura: int
    h_rel: str = "column"
    v_rel: str = "paragraph"
    vml: bool = False
    #: wp:anchor locked="1": a ancora nao muda de paragrafo
    travado: bool = False
    simples: bool = False
    imagem: bool = False


# -- leitura ------------------------------------------------------------------------------

def _parse(xml: bytes):
    return etree.fromstring(xml, opacos.parser_seguro())


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _quadro(raiz):
    """O wp:anchor ou wp:inline que o Word mostra (fora do mc:Fallback), ou None."""
    ramo = fx._ramo(raiz)
    for x in fx._sem_fallback(ramo):
        if x.tag in (_WP % "anchor", _WP % "inline"):
            return x
    return None


def _formas_vml(raiz) -> list:
    """As formas VML de cima (as que se posicionam): com style, fora do v:shapetype e com o pai
    fora do VML (o w:pict, o w:object)."""
    saida = []
    for x in raiz.iter():
        if not isinstance(x.tag, str) or etree.QName(x).namespace != V_NS:
            continue
        if _local(x) == "shapetype" or x.get("style") is None:
            continue
        pai = x.getparent()
        if pai is not None and isinstance(pai.tag, str) and etree.QName(pai).namespace == V_NS:
            continue
        saida.append(x)
    return saida


def _no_fallback(el) -> bool:
    pai = el.getparent()
    while pai is not None:
        if pai.tag == "{%s}Fallback" % MC_NS:
            return True
        pai = pai.getparent()
    return False


def _int(valor, padrao: int = 0) -> int:
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return padrao


def estado(xml: bytes) -> Estado | None:
    """Posicao, tamanho e quebra do objeto. None: o objeto nao tem posicao (equacao)."""
    try:
        raiz = _parse(xml)
    except (etree.LxmlError, ValueError):
        return None
    imagem = any(_local(x) == "pic" for x in raiz.iter()) and not any(
        _local(x) in ("wsp", "wgp", "txbxContent") for x in raiz.iter())
    quadro = _quadro(raiz)
    if quadro is not None:
        ext = quadro.find(_WP % "extent")
        largura = max(0, _int(ext.get("cx"))) if ext is not None else 0
        altura = max(0, _int(ext.get("cy"))) if ext is not None else 0
        if quadro.tag == _WP % "inline":
            return Estado(True, "linha", largura, altura, imagem=imagem)
        quebra = "frente"
        for filho in quadro:
            loc = _local(filho)
            if loc in _QUEBRA_DO_DML:
                quebra = _QUEBRA_DO_DML[loc]
        if fx._sim(quadro.get("behindDoc")):
            quebra = "atras"
        ph, pv = quadro.find(_WP % "positionH"), quadro.find(_WP % "positionV")
        return Estado(False, quebra, largura, altura,
                      h_rel=(ph.get("relativeFrom") if ph is not None else None) or "column",
                      v_rel=(pv.get("relativeFrom") if pv is not None else None) or "paragraph",
                      travado=fx._sim(quadro.get("locked")),
                      simples=fx._sim(quadro.get("simplePos")), imagem=imagem)
    formas = _formas_vml(raiz)
    if not formas:
        return None
    forma = formas[0]
    est = fx.estilo_vml(forma.get("style") or "")
    largura = max(0, fx.medida_vml(est.get("width")) or 0)
    altura = max(0, fx.medida_vml(est.get("height")) or 0)
    if est.get("position", "").lower() != "absolute":
        return Estado(True, "linha", largura, altura, vml=True, imagem=imagem)
    anc = fx._ancoragem_vml(forma, est)
    quebra = "atras" if anc.atras else {"square": "quadrado", "tight": "comprimido",
                                         "through": "atraves", "topbottom": "superior_inferior"
                                         }.get(anc.quebra, "frente")
    return Estado(False, quebra, largura, altura, h_rel=anc.h_rel, v_rel=anc.v_rel, vml=True,
                  imagem=imagem)


def z_de(xml: bytes) -> int | None:
    """O relativeHeight do objeto (o maior, se o XML tem mais de um), ou None."""
    valores = [int(m.group(1)) for m in _Z.finditer(xml)]
    return max(valores) if valores else None


# -- escrita: DrawingML -------------------------------------------------------------------

def _novo(tag: str, **atributos):
    el = etree.Element(tag)
    for chave, valor in atributos.items():
        el.set(chave, valor)
    return el


def _copiar_atributos_wp14(origem, destino) -> None:
    for chave, valor in origem.attrib.items():
        if chave.startswith("{%s}" % WP14_NS):
            destino.set(chave, valor)


def _para_ancora(inline, mud: Mudanca):
    """wp:inline -> wp:anchor, com o minimo que o esquema exige (CT_Anchor)."""
    anc = etree.Element(_WP % "anchor")
    for chave, valor in (("distT", "0"), ("distB", "0"), ("distL", "114300"), ("distR", "114300"),
                         ("simplePos", "0"),
                         ("relativeHeight", str(min(max(mud.z or Z_INICIAL, 0), 2 ** 32 - 1))),
                         ("behindDoc", "1" if mud.quebra == "atras" else "0"), ("locked", "0"),
                         ("layoutInCell", "1"), ("allowOverlap", "1")):
        anc.set(chave, valor)
    _copiar_atributos_wp14(inline, anc)
    anc.text, anc.tail = inline.text, inline.tail
    anc.append(_novo(_WP % "simplePos", x="0", y="0"))
    for tag, (rel, emu) in (("positionH", mud.h or ("column", 0)),
                            ("positionV", mud.v or ("paragraph", 0))):
        pos = _novo(_WP % tag, relativeFrom=rel)
        etree.SubElement(pos, _WP % "posOffset").text = str(mf.limitar_posicao(emu))
        anc.append(pos)
    ext = inline.find(_WP % "extent")
    anc.append(ext if ext is not None else _novo(_WP % "extent", cx="0", cy="0"))
    efeito = inline.find(_WP % "effectExtent")
    anc.append(efeito if efeito is not None else _novo(_WP % "effectExtent", l="0", t="0",
                                                       r="0", b="0"))
    anc.append(_novo(_WP % "wrapNone"))  # trocado em seguida por _quebra
    for nome in ("docPr", "cNvGraphicFramePr"):
        el = inline.find(_WP % nome)
        if el is not None:
            anc.append(el)
    grafico = inline.find(_A % "graphic")
    if grafico is not None:
        anc.append(grafico)
    inline.getparent().replace(inline, anc)
    return anc


def _para_linha(anc):
    """wp:anchor -> wp:inline (CT_Inline): extent, effectExtent, docPr, cNvGraphicFramePr,
    graphic. A posicao, a quebra e o tamanho relativo saem: na linha nao existem."""
    inline = etree.Element(_WP % "inline")
    for chave in ("distT", "distB", "distL", "distR"):
        inline.set(chave, "0")
    _copiar_atributos_wp14(anc, inline)
    inline.text, inline.tail = anc.text, anc.tail
    for nome in ("extent", "effectExtent", "docPr", "cNvGraphicFramePr"):
        el = anc.find(_WP % nome)
        if el is not None:
            inline.append(el)
    grafico = anc.find(_A % "graphic")
    if grafico is not None:
        inline.append(grafico)
    anc.getparent().replace(anc, inline)
    return inline


_POLIGONO = ((0, 0), (0, 21600), (21600, 21600), (21600, 0), (0, 0))


def _quebra(anc, quebra: str) -> None:
    """O wp:wrap* e o behindDoc da quebra pedida. O que ja' e' da mesma quebra fica igual."""
    tag = _WP % _DML_DA_QUEBRA[quebra]
    velho = next((f for f in anc if _local(f) in _WRAPS), None)
    if velho is None or velho.tag != tag:
        novo = etree.Element(tag)
        if tag in (_WP % "wrapSquare", _WP % "wrapTight", _WP % "wrapThrough"):
            novo.set("wrapText", (velho.get("wrapText") if velho is not None else None)
                     or "bothSides")
        if tag in (_WP % "wrapTight", _WP % "wrapThrough"):
            poligono = velho.find(_WP % "wrapPolygon") if velho is not None else None
            if poligono is not None:
                novo.append(copy.deepcopy(poligono))
            else:
                poligono = etree.SubElement(novo, _WP % "wrapPolygon", edited="0")
                for i, (x, y) in enumerate(_POLIGONO):
                    etree.SubElement(poligono, _WP % ("start" if i == 0 else "lineTo"),
                                     x=str(x), y=str(y))
        if velho is not None:
            novo.tail = velho.tail
            anc.replace(velho, novo)
        else:
            depois = anc.find(_WP % "effectExtent")
            if depois is None:
                depois = anc.find(_WP % "extent")
            depois.addnext(novo)
    atras = "1" if quebra == "atras" else "0"
    if (anc.get("behindDoc") or "0") not in (atras, "true" if atras == "1" else "false"):
        anc.set("behindDoc", atras)


def _tamanho(quadro, cx: int, cy: int) -> None:
    ext = quadro.find(_WP % "extent")
    if ext is None:
        return
    zero_l, zero_a = _int(ext.get("cx")) == 0, _int(ext.get("cy")) == 0
    cx, cy = mf.limitar_tamanho(cx, zero_l), mf.limitar_tamanho(cy, zero_a)
    ext.set("cx", str(cx))
    ext.set("cy", str(cy))
    dados = quadro.find("%s/%s" % (_A % "graphic", _A % "graphicData"))
    figura = next((f for f in dados if isinstance(f.tag, str)), None) if dados is not None else None
    if figura is not None:
        loc = _local(figura)
        ns = etree.QName(figura).namespace
        sppr = None
        if loc == "pic" and ns == PIC_NS:
            sppr = figura.find("{%s}spPr" % PIC_NS)
        elif loc == "wsp" and ns == WPS_NS:
            sppr = figura.find("{%s}spPr" % WPS_NS)
        elif loc == "wgp" and ns == WPG_NS:
            sppr = figura.find("{%s}grpSpPr" % WPG_NS)
        xfrm = sppr.find(_A % "xfrm") if sppr is not None else None
        a_ext = xfrm.find(_A % "ext") if xfrm is not None else None
        if a_ext is not None:
            a_ext.set("cx", str(cx))
            a_ext.set("cy", str(cy))
    for nome in ("pctWidth", "pctHeight"):
        for pct in quadro.iter("{%s}%s" % (WP14_NS, nome)):
            if _int((pct.text or "0").strip()) > 0:
                pct.text = "0"


def _posicao(anc, mud: Mudanca) -> None:
    if mud.simples is None and (mud.h is not None or mud.v is not None) and             fx._sim(anc.get("simplePos")):
        # A posicao pedida e' por referencia (o dialogo): o simplePos deixa de valer.
        anc.set("simplePos", "0")
    if mud.simples is not None and fx._sim(anc.get("simplePos")):
        sp = anc.find(_WP % "simplePos")
        if sp is not None:
            sp.set("x", str(max(0, min(_INT32, round(mud.simples[0])))))
            sp.set("y", str(max(0, min(_INT32, round(mud.simples[1])))))
    for tag, valor in (("positionH", mud.h), ("positionV", mud.v)):
        if valor is None:
            continue
        rel, emu = valor
        texto = str(mf.limitar_posicao(emu))
        pos = anc.find(_WP % tag)
        if pos is None:
            pos = _novo(_WP % tag, relativeFrom=rel)
            antes = anc.find(_WP % ("simplePos" if tag == "positionH" else "positionH"))
            antes.addnext(pos)
        if pos.get("relativeFrom") != rel:
            pos.set("relativeFrom", rel)
        filhos = [f for f in pos if isinstance(f.tag, str)]
        if len(filhos) == 1 and filhos[0].tag == _WP % "posOffset" and \
                (filhos[0].text or "").strip() == texto:
            continue
        for f in list(pos):
            pos.remove(f)
        pos.text = None
        etree.SubElement(pos, _WP % "posOffset").text = texto


def _aplicar_dml(quadro, mud: Mudanca) -> None:
    if mud.quebra == "linha" and quadro.tag == _WP % "anchor":
        quadro = _para_linha(quadro)
    elif mud.quebra not in (None, "linha") and quadro.tag == _WP % "inline":
        quadro = _para_ancora(quadro, mud)
    if quadro.tag == _WP % "anchor" and mud.quebra not in (None, "linha"):
        _quebra(quadro, mud.quebra)
    if mud.tamanho is not None:
        _tamanho(quadro, *mud.tamanho)
    if quadro.tag == _WP % "anchor":
        _posicao(quadro, mud)


# -- escrita: VML -------------------------------------------------------------------------

def _itens_do_estilo(estilo: str) -> list[list[str]]:
    """[[chave como veio, valor como veio], ...], na ordem do arquivo."""
    saida = []
    for parte in (estilo or "").split(";"):
        if ":" in parte:
            k, v = parte.split(":", 1)
            saida.append([k, v])
        elif parte.strip():
            saida.append([parte, None])
    return saida


def _juntar(itens) -> str:
    return ";".join(k if v is None else f"{k}:{v}" for k, v in itens)


def _achar(itens, chave: str):
    return next((i for i in itens if i[0].strip().lower() == chave), None)


def _definir(itens, chave: str, valor: str) -> None:
    item = _achar(itens, chave)
    if item is None:
        itens.append([chave, valor])
    elif item[1].strip() != valor:
        item[1] = valor


def _tirar(itens, *chaves: str) -> None:
    itens[:] = [i for i in itens if i[0].strip().lower() not in chaves]


def _pt(emu: float) -> str:
    texto = f"{emu / 12700:.2f}".rstrip("0").rstrip(".")
    return (texto if texto not in ("", "-0") else "0") + "pt"


def _aplicar_vml(forma, mud: Mudanca) -> None:
    itens = _itens_do_estilo(forma.get("style") or "")
    absoluto = (_achar(itens, "position") or ["", ""])[1].strip().lower() == "absolute"
    quebra_el = forma.find(_W10)
    if mud.quebra == "linha" and absoluto:
        _tirar(itens, "position", "margin-left", "margin-top", "left", "top", "z-index",
               "mso-position-horizontal", "mso-position-horizontal-relative",
               "mso-position-vertical", "mso-position-vertical-relative")
        if quebra_el is not None:
            forma.remove(quebra_el)
        absoluto = False
    elif mud.quebra not in (None, "linha") and not absoluto:
        itens.insert(0, ["position", "absolute"])
        _definir(itens, "margin-left", "0")
        _definir(itens, "margin-top", "0")
        _definir(itens, "z-index", str(mud.z or Z_INICIAL))
        absoluto = True
    if absoluto and mud.quebra not in (None, "linha"):
        z_item = _achar(itens, "z-index")
        z = _int(z_item[1]) if z_item is not None else 0
        if mud.quebra == "atras" and z >= 0:
            _definir(itens, "z-index", str(-(z or Z_INICIAL)))
        elif mud.quebra != "atras" and z < 0:
            _definir(itens, "z-index", str(-z))
        tipo = _VML_DA_QUEBRA[mud.quebra]
        if quebra_el is None and tipo != "none":
            prefixo = next((p for p, u in forma.nsmap.items() if u == fx.W10_NS), None)
            if prefixo is not None:
                quebra_el = etree.SubElement(forma, _W10)
        if quebra_el is not None and (quebra_el.get("type") or "none") != tipo:
            quebra_el.set("type", tipo)
    if mud.tamanho is not None:
        largura = fx.medida_vml((_achar(itens, "width") or ["", None])[1])
        altura = fx.medida_vml((_achar(itens, "height") or ["", None])[1])
        _definir(itens, "width", _pt(mf.limitar_tamanho(mud.tamanho[0], largura == 0)))
        _definir(itens, "height", _pt(mf.limitar_tamanho(mud.tamanho[1], altura == 0)))
        _tirar(itens, "mso-width-percent", "mso-height-percent")
    if absoluto:
        for eixo, valor, margem, extra, mapa in (
                ("horizontal", mud.h, "margin-left", "left", _H_VML),
                ("vertical", mud.v, "margin-top", "top", _V_VML)):
            if valor is None:
                continue
            rel, emu = valor
            alvo = mapa.get(rel)
            if alvo is None:
                continue
            relativo = "mso-position-%s-relative" % eixo
            atual = _achar(itens, relativo)
            padrao = "text"
            if (atual[1].strip() if atual is not None else padrao) != alvo:
                _definir(itens, relativo, alvo)
            alinhamento = _achar(itens, "mso-position-%s" % eixo)
            if alinhamento is not None and alinhamento[1].strip() != "absolute":
                alinhamento[1] = "absolute"
            desloc = fx.medida_vml((_achar(itens, extra) or ["", None])[1]) or 0
            _definir(itens, margem, _pt(mf.limitar_posicao(emu) - desloc))
    novo = _juntar(itens)
    if novo != (forma.get("style") or ""):
        forma.set("style", novo)


# -- entrada ------------------------------------------------------------------------------

def aplicar(xml: bytes, mud: Mudanca) -> bytes:
    """O XML do objeto com a posicao, o tamanho e a quebra de `mud`. O resto fica igual."""
    if mud.quebra is not None and mud.quebra not in QUEBRAS:
        raise ValueError(f"quebra desconhecida: {mud.quebra!r}")
    raiz = _parse(xml)
    quadro = _quadro(raiz)
    if quadro is not None:
        _aplicar_dml(quadro, mud)
    for forma in _formas_vml(raiz):
        if quadro is not None and not _no_fallback(forma):
            continue
        _aplicar_vml(forma, mud)
    return etree.tostring(raiz)


def objeto_com(obj: ObjetoOpaco, mud: Mudanca) -> ObjetoOpaco:
    """O objeto com o XML mudado, e as medidas que o leitor tiraria dele."""
    xml = aplicar(obj.xml, mud)
    el = _parse(xml)
    item = next((f for f in el if isinstance(f.tag, str) and f.tag != q("rPr")), el)
    largura, altura, flutuante = opacos.medidas(item)
    return replace(obj, xml=xml, largura_emu=largura, altura_emu=altura, flutuante=flutuante)


# -- imagem na linha do EditDoc <-> objeto --------------------------------------------------

_NSMAP_IMAGEM = {"w": W, "wp": WP_NS, "a": A_NS, "pic": PIC_NS, "r": R_NS}
_RID_IMAGEM = "rIdImg1"


def objeto_de_imagem(imagem: Imagem) -> ObjetoOpaco:
    """A imagem na linha (o `Imagem` do modelo) como objeto preservado com wp:inline, o mesmo
    desenho que o escritor grava. E' o caminho para ela virar flutuante (0.1.9)."""
    formato = mod_imagem.FORMATOS.get(imagem.formato)
    if formato is None:
        raise ValueError(f"formato de imagem invalido: {imagem.formato!r}")
    extensao, tipo = formato
    nome = f"word/media/editdoc_flutuante.{extensao}"
    cx, cy = str(int(imagem.largura_emu)), str(int(imagem.altura_emu))
    r = etree.Element(q("r"), nsmap=_NSMAP_IMAGEM)
    desenho = etree.SubElement(r, q("drawing"))
    inline = etree.SubElement(desenho, _WP % "inline", distT="0", distB="0", distL="0", distR="0")
    etree.SubElement(inline, _WP % "extent", cx=cx, cy=cy)
    etree.SubElement(inline, _WP % "effectExtent", l="0", t="0", r="0", b="0")
    doc_pr = etree.SubElement(inline, _WP % "docPr", id="1", name="Imagem 1")
    if imagem.descricao:
        doc_pr.set("descr", imagem.descricao)
    quadro = etree.SubElement(inline, _WP % "cNvGraphicFramePr")
    etree.SubElement(quadro, _A % "graphicFrameLocks", noChangeAspect="1")
    grafico = etree.SubElement(inline, _A % "graphic")
    dados = etree.SubElement(grafico, _A % "graphicData", uri=PIC_NS)
    pic = etree.SubElement(dados, "{%s}pic" % PIC_NS)
    nv = etree.SubElement(pic, "{%s}nvPicPr" % PIC_NS)
    etree.SubElement(nv, "{%s}cNvPr" % PIC_NS, id="0", name=nome.rsplit("/", 1)[1])
    etree.SubElement(nv, "{%s}cNvPicPr" % PIC_NS)
    preench = etree.SubElement(pic, "{%s}blipFill" % PIC_NS)
    etree.SubElement(preench, _A % "blip").set("{%s}embed" % R_NS, _RID_IMAGEM)
    if imagem.recorte is not None and any(imagem.recorte):
        recorte = etree.SubElement(preench, _A % "srcRect")
        for chave, valor in zip("ltrb", imagem.recorte):
            if int(valor):
                recorte.set(chave, str(int(valor)))
    etree.SubElement(etree.SubElement(preench, _A % "stretch"), _A % "fillRect")
    sp = etree.SubElement(pic, "{%s}spPr" % PIC_NS)
    xfrm = etree.SubElement(sp, _A % "xfrm")
    etree.SubElement(xfrm, _A % "off", x="0", y="0")
    etree.SubElement(xfrm, _A % "ext", cx=cx, cy=cy)
    etree.SubElement(etree.SubElement(sp, _A % "prstGeom", prst="rect"), _A % "avLst")
    return ObjetoOpaco(xml=etree.tostring(r), tipo="imagem", flutuante=False,
                       largura_emu=int(imagem.largura_emu), altura_emu=int(imagem.altura_emu),
                       relacoes=((_RID_IMAGEM, RT_IMAGEM, nome, False),),
                       partes=(ParteOpaca(nome=nome, tipo_conteudo=tipo, dados=imagem.dados),),
                       previa=imagem.dados)


#: Filhos que a imagem na linha do EditDoc regrava igual (o resto se perderia).
_SPPR_SIMPLES = {"xfrm", "prstGeom", "noFill"}
_BLIPFILL_SIMPLES = {"blip", "srcRect", "stretch"}


def imagem_de_objeto(obj: ObjetoOpaco) -> Imagem:
    """O objeto (uma figura PNG, JPEG, GIF ou BMP) como `Imagem` do modelo: e' o que o leitor
    faz de um wp:inline com figura assim, entao a imagem que fica "Alinhada ao texto" tem de
    virar isso, senao a conferencia pos-gravacao veria outra coisa. PosicaoRecusada se a figura
    tem o que a imagem do EditDoc nao guarda (borda, efeito, rotacao, espelho)."""
    raiz = _parse(obj.xml)
    item = next((f for f in raiz if isinstance(f.tag, str) and f.tag != q("rPr")), None)
    if item is None or item.tag != q("drawing"):
        raise PosicaoRecusada("A figura não é uma imagem simples.")
    pic = next(item.iter("{%s}pic" % PIC_NS), None)
    blip = next(item.iter(_A % "blip"), None)
    if pic is None or blip is None or blip.get("{%s}embed" % R_NS) is None:
        raise PosicaoRecusada("A figura não é uma imagem simples.")
    rid = blip.get("{%s}embed" % R_NS)
    alvo = next((a for r, _t, a, ext in obj.relacoes if r == rid and not ext), None)
    parte = next((p for p in obj.partes if p.nome == alvo), None) if alvo else None
    if parte is None:
        raise PosicaoRecusada("A imagem não está no arquivo.")
    formato = mod_imagem.formato_de(parte.dados)
    dims = mod_imagem.dimensoes(parte.dados, formato) if formato else None
    if formato is None or not dims or dims[0] <= 0 or dims[1] <= 0:
        raise PosicaoRecusada("A imagem está num formato (EMF, WMF, SVG, TIFF) que só fica "
                              "flutuante ou como objeto na linha.")
    sppr = pic.find("{%s}spPr" % PIC_NS)
    for filho in (sppr if sppr is not None else []):
        loc = _local(filho)
        if loc and loc not in _SPPR_SIMPLES:
            if loc == "ln" and filho.find(_A % "noFill") is not None:
                continue
            raise PosicaoRecusada("A imagem tem borda ou efeito que a imagem na linha do "
                                  "EditDoc não guarda. Use o Word para essa mudança.")
        if loc == "xfrm" and (_int(filho.get("rot")) or fx._sim(filho.get("flipH"))
                              or fx._sim(filho.get("flipV"))):
            raise PosicaoRecusada("A imagem está girada ou espelhada, e a imagem na linha do "
                                  "EditDoc não guarda isso. Use o Word para essa mudança.")
        if loc == "prstGeom" and filho.get("prst") not in (None, "rect"):
            raise PosicaoRecusada("A imagem tem um recorte em forma que a imagem na linha do "
                                  "EditDoc não guarda. Use o Word para essa mudança.")
    preench = blip.getparent()
    if any(_local(f) and _local(f) not in _BLIPFILL_SIMPLES for f in preench):
        raise PosicaoRecusada("A imagem tem um preenchimento que a imagem na linha do EditDoc "
                              "não guarda. Use o Word para essa mudança.")
    if any(_local(f) and _local(f) != "extLst" for f in blip):
        raise PosicaoRecusada("A imagem tem efeitos de cor que a imagem na linha do EditDoc "
                              "não guarda. Use o Word para essa mudança.")
    quadro = _quadro(raiz)
    ext = quadro.find(_WP % "extent") if quadro is not None else None
    cx = max(1, _int(ext.get("cx"))) if ext is not None else round(dims[0] * 9525)
    cy = max(1, _int(ext.get("cy"))) if ext is not None else round(dims[1] * 9525)
    recorte = None
    src = preench.find(_A % "srcRect")
    if src is not None and any((src.get(k) or "0") != "0" for k in "ltrb"):
        recorte = tuple(_int(src.get(k) or "0") for k in "ltrb")
    doc_pr = quadro.find(_WP % "docPr") if quadro is not None else None
    return Imagem(dados=parte.dados, formato=formato, largura_emu=cx, altura_emu=cy,
                  descricao=(doc_pr.get("descr") or "") if doc_pr is not None else "",
                  recorte=recorte)


def vira_imagem_na_linha(obj: ObjetoOpaco) -> bool:
    """Na linha, o leitor leria o objeto como imagem do EditDoc (`leitor._ler_desenho`): um
    w:drawing direto (sem mc:AlternateContent) com uma figura PNG, JPEG, GIF ou BMP embutida."""
    try:
        raiz = _parse(obj.xml)
    except (etree.LxmlError, ValueError):
        return False
    item = next((f for f in raiz if isinstance(f.tag, str) and f.tag != q("rPr")), None)
    if item is None or item.tag != q("drawing"):
        return False
    quadro = next((f for f in item if f.tag in (_WP % "anchor", _WP % "inline")), None)
    dados = quadro.find("%s/%s" % (_A % "graphic", _A % "graphicData")) if quadro is not None         else None
    if dados is None or dados.get("uri") != PIC_NS:
        return False
    blip = next(dados.iter(_A % "blip"), None)
    rid = blip.get("{%s}embed" % R_NS) if blip is not None else None
    alvo = next((a for r, _t, a, ext in obj.relacoes if r == rid and not ext), None)
    parte = next((p for p in obj.partes if p.nome == alvo), None) if alvo else None
    if parte is None:
        return False
    formato = mod_imagem.formato_de(parte.dados)
    dims = mod_imagem.dimensoes(parte.dados, formato) if formato else None
    return bool(formato and dims and dims[0] > 0 and dims[1] > 0)


def eh_imagem_simples(obj: ObjetoOpaco) -> bool:
    """O objeto e' uma figura que o leitor leria como imagem na linha (se estivesse na linha)."""
    try:
        imagem_de_objeto(obj)
    except (PosicaoRecusada, etree.LxmlError, ValueError):
        return False
    return True


# -- validacao ------------------------------------------------------------------------------

#: Atributos que o CT_Anchor exige.
ATRIBUTOS_DA_ANCORA = ("simplePos", "relativeHeight", "behindDoc", "locked", "layoutInCell",
                       "allowOverlap")
_COORDENADA_MAXIMA = 27273042316900


def problemas(raiz) -> list[str]:
    """O que o Word recusaria na posicao e no tamanho dos objetos de uma parte (validador)."""
    saida = []
    for anc in raiz.iter(_WP % "anchor"):
        faltam = [a for a in ATRIBUTOS_DA_ANCORA if anc.get(a) is None]
        if faltam:
            saida.append("wp:anchor sem " + ", ".join(faltam))
        if not any(_local(f) in _WRAPS for f in anc):
            saida.append("wp:anchor sem quebra de texto (wp:wrap*)")
        for tag in ("positionH", "positionV"):
            pos = anc.find(_WP % tag)
            if pos is None:
                saida.append(f"wp:anchor sem wp:{tag}")
                continue
            for desloc in pos.iter(_WP % "posOffset"):
                try:
                    valor = int((desloc.text or "").strip())
                except ValueError:
                    saida.append("wp:posOffset que nao e' inteiro")
                    continue
                if not -2 ** 31 <= valor <= _INT32:
                    saida.append("wp:posOffset fora de ST_PositionOffset")
    for ext in raiz.iter(_WP % "extent"):
        for chave in ("cx", "cy"):
            try:
                valor = int(ext.get(chave, ""))
            except ValueError:
                continue  # o validador de imagem ja' acusa
            if not 0 <= valor <= _COORDENADA_MAXIMA:
                saida.append("wp:extent fora de ST_PositiveCoordinate")
    return saida


__all__ = ["Mudanca", "Estado", "PosicaoRecusada", "QUEBRAS", "ROTULOS_QUEBRA", "aplicar",
           "estado", "objeto_com", "objeto_de_imagem", "imagem_de_objeto", "eh_imagem_simples",
           "vira_imagem_na_linha",
           "z_de", "problemas", "Z_INICIAL"]
