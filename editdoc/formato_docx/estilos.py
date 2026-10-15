"""styles.xml <-> catalogo de estilos (M6). Sem Qt.

Leitura: cada w:style vira um `Estilo` com as propriedades que o EditDoc entende; o XML
inteiro fica guardado (`Estilos.xml_original`). Gravacao: parte do XML original (ou do
XML padrao, num documento novo) e so' reescreve os estilos alterados ou novos, e dentro
deles so' os atributos que mudaram. Assim um estilo que o editor nao usa, o
latentStyles, o docDefaults, os estilos de tabela e as extensoes do Word (w14, w15...)
voltam como vieram.

O `w:numPr` dentro de um estilo (Titulo numerado, List Bullet) fica no estilo desde a
0.1.4: o numbering.xml de origem volta inteiro, e o paragrafo do estilo herda a lista. So'
sai o numPr cujo numId o numbering.xml nao define (aviso LISTA). Antes da 0.1.4 o numPr
saia de todo estilo e a lista passava ao paragrafo.

Nunca volta igual, de proposito: filho de pPr ou rPr que o validador de ordem nao conhece
(w:rPrChange...) sai, com o aviso FORMATACAO; os conhecidos sao postos na ordem do esquema.
"""

from __future__ import annotations

import copy

from lxml import etree

from editdoc.formato_docx import ordem
from editdoc.formato_docx.nomes import A_NS, W, q
from editdoc.formato_docx.padroes import (ESPACO_DEPOIS_PADRAO_TW, FONTE_PADRAO, LINHA_PADRAO,
                                         TAMANHO_PADRAO_MEIO_PT)
from editdoc.modelo.documento import Borda
from editdoc.modelo.estilos import (CAMPOS_CARACTERE, CAMPOS_PARAGRAFO, Estilo, Estilos,
                                    catalogo_padrao, nivel_de_titulo)

#: Estilo de tabela que toda tabela usa (o "Table Grid" do Word).
ESTILO_TABELA = "TableGrid"

_TIPO_XML = {"paragraph": "paragrafo", "character": "caractere", "table": "tabela",
             "numbering": "numeracao"}
_TIPO_MODELO = {v: k for k, v in _TIPO_XML.items()}
_JC = {"left": "esquerda", "start": "esquerda", "center": "centro", "right": "direita",
       "end": "direita", "both": "justificado"}
_JC_XML = {"esquerda": "left", "centro": "center", "direita": "right", "justificado": "both"}
#: Filhos de w:style na ordem do CT_Style.
ORDEM_ESTILO = ["name", "aliases", "basedOn", "next", "link", "autoRedefine", "hidden",
                "uiPriority", "semiHidden", "unhideWhenUsed", "qFormat", "locked", "personal",
                "personalCompose", "personalReply", "rsid", "pPr", "rPr", "tblPr", "trPr", "tcPr",
                "tblStylePr"]
_HEX6 = set("0123456789ABCDEFabcdef")


def _atr(el, nome: str) -> str | None:
    return el.get(q(nome)) if el is not None else None


def _onoff(el) -> bool:
    v = _atr(el, "val")
    return v is None or v.lower() not in ("0", "false", "off")


def _inteiro(valor: str | None) -> int | None:
    if valor is None:
        return None
    try:
        return int(valor)
    except ValueError:
        return None


def _local(el) -> str | None:
    if not isinstance(el.tag, str):
        return None
    return etree.QName(el).localname if el.tag.startswith("{%s}" % W) else None


# -- tema ---------------------------------------------------------------------------

def fontes_do_tema(raiz_tema) -> dict:
    """{"major": ..., "minor": ...}: a fonte latina de titulo e de corpo do tema."""
    saida = {}
    for chave, nome in (("major", "majorFont"), ("minor", "minorFont")):
        latin = raiz_tema.find(".//{%s}%s/{%s}latin" % (A_NS, nome, A_NS))
        face = latin.get("typeface") if latin is not None else None
        if face:
            saida[chave] = face[:64]
    return saida


def fonte_de_rfonts(rf, fontes_tema: dict) -> str | None:
    """Nome da fonte de um w:rFonts: o explicito, ou o do tema (asciiTheme)."""
    if rf is None:
        return None
    nome = _atr(rf, "ascii") or _atr(rf, "hAnsi")
    if nome:
        return nome
    tema = _atr(rf, "asciiTheme") or _atr(rf, "hAnsiTheme")
    if tema:
        return fontes_tema.get("major" if tema.startswith("major") else "minor")
    return None


# -- leitura ---------------------------------------------------------------------------

def props_de_rpr(rpr, fontes_tema: dict) -> dict:
    """Propriedades de caractere que o EditDoc entende num w:rPr (sem avisos)."""
    out: dict = {}
    if rpr is None:
        return out
    for f in rpr:
        loc = _local(f)
        if loc == "b":
            out["negrito"] = _onoff(f)
        elif loc == "i":
            out["italico"] = _onoff(f)
        elif loc == "u":
            out["sublinhado"] = _atr(f, "val") != "none"
        elif loc in ("strike", "dstrike"):
            out["tachado"] = _onoff(f)
        elif loc == "vertAlign":
            v = _atr(f, "val")
            if v == "superscript":
                out["sobrescrito"], out["subscrito"] = True, False
            elif v == "subscript":
                out["subscrito"], out["sobrescrito"] = True, False
            elif v == "baseline":
                out["subscrito"], out["sobrescrito"] = False, False
        elif loc == "sz":
            v = _inteiro(_atr(f, "val"))
            if v is not None and 1 <= v <= 3276:
                out["tamanho_meio_pt"] = v
        elif loc == "rFonts":
            fonte = fonte_de_rfonts(f, fontes_tema)
            if fonte:
                out["fonte"] = fonte
        elif loc == "color":
            v = _atr(f, "val") or ""
            if len(v) == 6 and set(v) <= _HEX6:
                out["cor_hex"] = v.upper()
    return out


def props_de_ppr(ppr) -> dict:
    """Propriedades de paragrafo que o EditDoc entende num w:pPr, mais "nivel"."""
    out: dict = {}
    if ppr is None:
        return out
    for f in ppr:
        loc = _local(f)
        if loc == "jc":
            v = _JC.get(_atr(f, "val") or "")
            if v:
                out["alinhamento"] = v
        elif loc == "ind":
            esq = _atr(f, "left") or _atr(f, "start")
            if esq is not None:
                out["recuo_esquerdo_tw"] = _inteiro(esq)
            dir_ = _atr(f, "right") or _atr(f, "end")
            if dir_ is not None:
                out["recuo_direito_tw"] = _inteiro(dir_)
            if _atr(f, "firstLine") is not None:
                out["recuo_primeira_linha_tw"] = _inteiro(_atr(f, "firstLine"))
            elif _atr(f, "hanging") is not None:
                h = _inteiro(_atr(f, "hanging"))
                out["recuo_primeira_linha_tw"] = None if h is None else -h
        elif loc == "spacing":
            if _atr(f, "before") is not None:
                out["espaco_antes_tw"] = _inteiro(_atr(f, "before"))
            if _atr(f, "after") is not None:
                out["espaco_depois_tw"] = _inteiro(_atr(f, "after"))
            linha = _inteiro(_atr(f, "line"))
            if linha is not None and (_atr(f, "lineRule") or "auto") == "auto":
                out["espacamento_linha_pct"] = round(linha * 100 / 240)
        elif loc == "outlineLvl":
            v = _inteiro(_atr(f, "val"))
            if v is not None and 0 <= v <= 9:
                out["nivel"] = v
    return {k: v for k, v in out.items() if v is not None}


def _lista_do_estilo(ppr, numeracao, coletor) -> tuple[int | None, int | None, str | None]:
    """(numId, ilvl, tipo) do w:numPr de um estilo. numId que nao existe: sem lista (LISTA)."""
    num = ppr.find(q("numPr")) if ppr is not None else None
    if num is None:
        return None, None, None
    nid = _inteiro(_atr(num.find(q("numId")), "val"))
    ilvl = _inteiro(_atr(num.find(q("ilvl")), "val"))
    if ilvl is not None and not 0 <= ilvl <= 8:
        ilvl = min(max(ilvl, 0), 8)
        if coletor is not None:
            coletor.somar("LISTA_NIVEL")
    if nid is not None and nid != 0 and (numeracao is None or nid not in numeracao.instancias):
        if coletor is not None:
            coletor.somar("LISTA")
        return None, ilvl, None
    tipo = numeracao.tipo_de(nid, ilvl or 0) if numeracao is not None and nid else None
    return nid, ilvl, tipo


def ler_estilos(raiz, dados: bytes, fontes_tema: dict, numeracao=None,
                tema: bytes | None = None, coletor=None) -> tuple[Estilos, int]:
    """w:styles -> (catalogo, filhos de pPr/rPr que nao voltam ao arquivo).

    `numeracao` e' o catalogo do numbering.xml (0.1.4): o numPr do estilo vira
    `Estilo.lista` e `Estilo.lista_nivel`, e volta ao arquivo.
    """
    est = Estilos(itens={}, xml_original=dados, tema_original=tema, fontes_tema=dict(fontes_tema))
    dd = raiz.find(q("docDefaults"))
    if dd is not None:
        est.padrao_caractere = props_de_rpr(dd.find(q("rPrDefault") + "/" + q("rPr")), fontes_tema)
        est.padrao_paragrafo = props_de_ppr(dd.find(q("pPrDefault") + "/" + q("pPr")))
    for el in raiz.findall(q("style")):
        sid = _atr(el, "styleId")
        tipo = _TIPO_XML.get(_atr(el, "type") or "paragraph")
        if not sid or tipo is None or sid in est.itens or len(sid) > 253:
            continue
        nome_el = el.find(q("name"))
        nome = (_atr(nome_el, "val") or sid)[:253]

        def val(tag):
            filho = el.find(q(tag))
            return _atr(filho, "val") if filho is not None else None

        def tem(tag):
            filho = el.find(q(tag))
            return filho is not None and _onoff(filho)

        e = Estilo(id=sid, nome=nome, tipo=tipo, baseado_em=val("basedOn"), proximo=val("next"),
                   vinculado=val("link"), rapido=tem("qFormat"),
                   prioridade=_inteiro(val("uiPriority")), oculto=tem("semiHidden") or tem("hidden"),
                   revelar_ao_usar=tem("unhideWhenUsed"),
                   padrao=(_atr(el, "default") or "").lower() in ("1", "true", "on"),
                   personalizado=(_atr(el, "customStyle") or "").lower() in ("1", "true", "on"),
                   no_arquivo=True)
        if tipo in ("paragrafo", "caractere"):
            ppr = el.find(q("pPr")) if tipo == "paragrafo" else None
            par = props_de_ppr(ppr)
            e.nivel = par.pop("nivel", None)
            e.paragrafo = par
            e.caractere = props_de_rpr(el.find(q("rPr")), fontes_tema)
            if ppr is not None:
                e.lista, e.lista_nivel, e.numeracao = _lista_do_estilo(ppr, numeracao, coletor)
            if e.nivel is None and tipo == "paragrafo":
                # Titulo sem outlineLvl (arquivo de outro programa): o nome diz o nivel.
                e.nivel = nivel_de_titulo(nome)
        elif tipo == "numeracao":
            # Estilo de numeracao (w:numStyleLink de uma abstrata aponta para ele).
            e.lista, e.lista_nivel, _tipo = _lista_do_estilo(el.find(q("pPr")), numeracao, None)
        e.originais = {"paragrafo": dict(e.paragrafo), "caractere": dict(e.caractere),
                       "nivel": e.nivel, "lista": [e.lista, e.lista_nivel]}
        est.itens[sid] = e
    removidos = sanear(copy.deepcopy(raiz))
    return est, removidos


# -- saneamento ------------------------------------------------------------------------

#: Revisoes dentro de um estilo (0.1.13): continuam saindo, com FORMATACAO (as alteracoes
#: controladas que o EditDoc trata sao as do texto; o ORDEM_RPR passou a conhecer o rPrChange).
_REVISOES_NO_ESTILO = {"ins", "del", "moveFrom", "moveTo", "rPrChange", "pPrChange", "tblPrChange",
                       "tcPrChange", "trPrChange", "cellIns", "cellDel", "cellMerge"}


def sanear(raiz, listas: set | None = None) -> int:
    """Deixa pPr/rPr/tblPr/tcPr/bordas na ordem do esquema e tira o que o validador nao aceita.

    Filho de outro namespace (w14, w15) fica: o Word o grava e o declara em
    mc:Ignorable. `listas`: os numIds que o numbering.xml gravado define; o numPr de estilo
    que cita outro numId sai (o validador recusaria). None = nao mexe no numPr.
    Devolve quantos filhos foram tirados (fora o numPr).
    """
    removidos = 0
    for estilo in raiz.iter(q("style")):
        ppr = estilo.find(q("pPr"))
        if ppr is not None and listas is not None:
            for num in ppr.findall(q("numPr")):
                nid = _inteiro(_atr(num.find(q("numId")), "val"))
                if nid is not None and nid != 0 and nid not in listas:
                    ppr.remove(num)
    for nome, lista in ordem.ORDENS.items():  # pPr, rPr, tblPr, tcPr e bordas
        for el in raiz.iter(q(nome)):
            conhecidos = []
            estrangeiros = []
            for f in list(el):
                if not isinstance(f.tag, str):
                    el.remove(f)
                    continue
                if not f.tag.startswith("{%s}" % W):
                    estrangeiros.append(f)
                elif etree.QName(f).localname in lista and                         etree.QName(f).localname not in _REVISOES_NO_ESTILO:
                    conhecidos.append(f)
                else:
                    el.remove(f)
                    removidos += 1
                    continue
                el.remove(f)
            conhecidos.sort(key=lambda f: lista.index(etree.QName(f).localname))
            for f in conhecidos + estrangeiros:
                el.append(f)
    return removidos


# -- escrita ---------------------------------------------------------------------------

def _set(el, nome: str, valor) -> None:
    if valor is None:
        el.attrib.pop(q(nome), None)
    else:
        el.set(q(nome), str(valor))


def _filho(pai, nome: str, ordem_: list[str]):
    """O filho w:nome de `pai`, criado na posicao certa se faltar."""
    achado = pai.find(q(nome))
    if achado is not None:
        return achado
    novo = etree.SubElement(pai, q(nome))
    _reordenar(pai, ordem_)
    return novo


def _reordenar(el, lista: list[str]) -> None:
    conhecidos = [f for f in el if isinstance(f.tag, str) and f.tag.startswith("{%s}" % W)
                  and etree.QName(f).localname in lista]
    outros = [f for f in el if f not in conhecidos]
    conhecidos.sort(key=lambda f: lista.index(etree.QName(f).localname))
    for f in list(el):
        el.remove(f)
    for f in conhecidos + outros:
        el.append(f)


def _remover(pai, nome: str) -> None:
    for f in pai.findall(q(nome)):
        pai.remove(f)


def _vazio(el) -> bool:
    return len(el) == 0 and not el.attrib


def aplicar_ppr(ppr, props: dict, mudar: set[str]) -> None:
    """Grava em w:pPr os campos de `mudar` com os valores de `props` (None apaga)."""
    o = ordem.ORDEM_PPR
    if "alinhamento" in mudar:
        _remover(ppr, "jc")
        if props.get("alinhamento") is not None:
            _filho(ppr, "jc", o).set(q("val"), _JC_XML[props["alinhamento"]])
    ind_campos = {"recuo_esquerdo_tw", "recuo_direito_tw", "recuo_primeira_linha_tw"} & mudar
    if ind_campos:
        ind = _filho(ppr, "ind", o)
        if "recuo_esquerdo_tw" in mudar:
            ind.attrib.pop(q("start"), None)
            _set(ind, "left", props.get("recuo_esquerdo_tw"))
        if "recuo_direito_tw" in mudar:
            ind.attrib.pop(q("end"), None)
            _set(ind, "right", props.get("recuo_direito_tw"))
        if "recuo_primeira_linha_tw" in mudar:
            for a in ("firstLine", "hanging", "firstLineChars", "hangingChars"):
                ind.attrib.pop(q(a), None)
            v = props.get("recuo_primeira_linha_tw")
            if v is not None:
                _set(ind, "firstLine" if v >= 0 else "hanging", abs(int(v)))
        if _vazio(ind):
            ppr.remove(ind)
    sp_campos = {"espaco_antes_tw", "espaco_depois_tw", "espacamento_linha_pct"} & mudar
    if sp_campos:
        sp = _filho(ppr, "spacing", o)
        if "espaco_antes_tw" in mudar:
            for a in ("beforeLines", "beforeAutospacing"):
                sp.attrib.pop(q(a), None)
            _set(sp, "before", props.get("espaco_antes_tw"))
        if "espaco_depois_tw" in mudar:
            for a in ("afterLines", "afterAutospacing"):
                sp.attrib.pop(q(a), None)
            _set(sp, "after", props.get("espaco_depois_tw"))
        if "espacamento_linha_pct" in mudar:
            v = props.get("espacamento_linha_pct")
            _set(sp, "line", None if v is None else round(int(v) * 240 / 100))
            _set(sp, "lineRule", None if v is None else "auto")
        if _vazio(sp):
            ppr.remove(sp)
    if "nivel" in mudar:
        _remover(ppr, "outlineLvl")
        if props.get("nivel") is not None:
            _filho(ppr, "outlineLvl", o).set(q("val"), str(int(props["nivel"])))


def aplicar_rpr(rpr, props: dict, mudar: set[str]) -> None:
    """Grava em w:rPr os campos de `mudar` com os valores de `props` (None apaga)."""
    o = ordem.ORDEM_RPR

    def onoff(tag, valor, cs=None):
        _remover(rpr, tag)
        if cs:
            _remover(rpr, cs)
        if valor is not None:
            el = _filho(rpr, tag, o)
            if not valor:
                el.set(q("val"), "0")

    if "fonte" in mudar:
        _remover(rpr, "rFonts")
        if props.get("fonte"):
            rf = _filho(rpr, "rFonts", o)
            for a in ("ascii", "hAnsi", "eastAsia", "cs"):
                rf.set(q(a), props["fonte"])
    if "negrito" in mudar:
        onoff("b", props.get("negrito"), "bCs")
    if "italico" in mudar:
        onoff("i", props.get("italico"), "iCs")
    if "tachado" in mudar:
        _remover(rpr, "dstrike")
        onoff("strike", props.get("tachado"))
    if "cor_hex" in mudar:
        _remover(rpr, "color")  # leva junto themeColor, que venceria o valor novo
        if props.get("cor_hex"):
            _filho(rpr, "color", o).set(q("val"), props["cor_hex"].upper())
    if "tamanho_meio_pt" in mudar:
        _remover(rpr, "sz")
        _remover(rpr, "szCs")
        if props.get("tamanho_meio_pt") is not None:
            v = str(int(props["tamanho_meio_pt"]))
            _filho(rpr, "sz", o).set(q("val"), v)
            _filho(rpr, "szCs", o).set(q("val"), v)
    if "sublinhado" in mudar:
        _remover(rpr, "u")
        if props.get("sublinhado") is not None:
            _filho(rpr, "u", o).set(q("val"), "single" if props["sublinhado"] else "none")
    if {"subscrito", "sobrescrito"} & mudar:
        _remover(rpr, "vertAlign")
        sub, sob = props.get("subscrito"), props.get("sobrescrito")
        v = "subscript" if sub else "superscript" if sob else \
            "baseline" if (sub is False or sob is False) else None
        if v:
            _filho(rpr, "vertAlign", o).set(q("val"), v)


def _cabecalho_do_estilo(el, e: Estilo) -> None:
    """name, basedOn, next, link, uiPriority, semiHidden, unhideWhenUsed e qFormat."""
    el.set(q("type"), _TIPO_MODELO[e.tipo])
    el.set(q("styleId"), e.id)
    _set(el, "default", "1" if e.padrao else None)
    _set(el, "customStyle", "1" if e.personalizado else None)
    for tag, valor in (("name", e.nome), ("basedOn", e.baseado_em), ("next", e.proximo),
                       ("link", e.vinculado),
                       ("uiPriority", None if e.prioridade is None else str(e.prioridade))):
        _remover(el, tag)
        if valor:
            _filho(el, tag, ORDEM_ESTILO).set(q("val"), valor)
    for tag, ligado in (("semiHidden", e.oculto), ("unhideWhenUsed", e.revelar_ao_usar),
                        ("qFormat", e.rapido)):
        _remover(el, tag)
        if ligado:
            _filho(el, tag, ORDEM_ESTILO)


def _escrever_estilo(el, e: Estilo) -> None:
    """Atualiza (ou preenche) o elemento w:style com o Estilo. So' mexe no que mudou."""
    _cabecalho_do_estilo(el, e)
    if e.tipo not in ("paragrafo", "caractere"):
        return
    orig = e.originais if e.no_arquivo else {}
    par_orig = orig.get("paragrafo", {})
    car_orig = orig.get("caractere", {})
    par = dict(e.paragrafo)
    par["nivel"] = e.nivel
    mudar_par = {k for k in (*CAMPOS_PARAGRAFO, "nivel")
                 if par.get(k) != (orig.get("nivel") if k == "nivel" else par_orig.get(k))}
    mudar_car = {k for k in CAMPOS_CARACTERE if e.caractere.get(k) != car_orig.get(k)}
    lista_orig = tuple(orig.get("lista") or (None, None))
    mudar_lista = (e.lista, e.lista_nivel) != lista_orig
    if e.tipo == "paragrafo" and (mudar_par or mudar_lista or (e.extras and not e.no_arquivo)):
        ppr = _filho(el, "pPr", ORDEM_ESTILO)
        if not e.no_arquivo:
            for extra in e.extras:
                if extra in ordem.ORDEM_PPR and ppr.find(q(extra)) is None:
                    _filho(ppr, extra, ordem.ORDEM_PPR)
        aplicar_ppr(ppr, par, mudar_par)
        if mudar_lista:
            # Lista do estilo (0.1.4): a lista de titulos numerados liga Titulo 1 a 9.
            _remover(ppr, "numPr")
            if e.lista is not None or e.lista_nivel is not None:
                num = _filho(ppr, "numPr", ordem.ORDEM_PPR)
                if e.lista_nivel is not None:
                    etree.SubElement(num, q("ilvl")).set(q("val"), str(int(e.lista_nivel)))
                if e.lista is not None:
                    etree.SubElement(num, q("numId")).set(q("val"), str(int(e.lista)))
        if _vazio(ppr):
            el.remove(ppr)
    if mudar_car:
        rpr = _filho(el, "rPr", ORDEM_ESTILO)
        aplicar_rpr(rpr, e.caractere, mudar_car)
        if _vazio(rpr):
            el.remove(rpr)


def _xml(raiz) -> bytes:
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)


def _borda_xml(pai, nome: str, borda: Borda) -> None:
    el = etree.SubElement(pai, q(nome))
    el.set(q("val"), "single")
    el.set(q("sz"), str(borda.oitavos_pt))
    el.set(q("space"), "0")
    el.set(q("color"), "auto")


def _estilo_fixo(raiz, tipo, sid, nome, extra=(), padrao=True):
    s = etree.SubElement(raiz, q("style"))
    s.set(q("type"), tipo)
    if padrao:
        s.set(q("default"), "1")
    s.set(q("styleId"), sid)
    etree.SubElement(s, q("name")).set(q("val"), nome)
    for tag, val in extra:
        el = etree.SubElement(s, q(tag))
        if val is not None:
            el.set(q("val"), val)
    return s


def _estilo_grade(raiz):
    # "Table Grid": o estilo que o Word da' a tabela nova. Zera o espacamento dos
    # paragrafos dentro da celula (o padrao do documento tem 8 pt depois). As bordas
    # de cada tabela sao gravadas nela mesma; as daqui valem so' de referencia.
    grade = _estilo_fixo(raiz, "table", ESTILO_TABELA, "Table Grid",
                         extra=[("basedOn", "TableNormal"), ("uiPriority", "39")], padrao=False)
    gp = etree.SubElement(grade, q("pPr"))
    gsp = etree.SubElement(gp, q("spacing"))
    gsp.set(q("after"), "0")
    gsp.set(q("line"), "240")
    gsp.set(q("lineRule"), "auto")
    gt = etree.SubElement(grade, q("tblPr"))
    gb = etree.SubElement(gt, q("tblBorders"))
    for nome in ("top", "left", "bottom", "right", "insideH", "insideV"):
        _borda_xml(gb, nome, Borda())


def xml_base(fonte: str = FONTE_PADRAO,
             tamanho_meio_pt: int = TAMANHO_PADRAO_MEIO_PT) -> etree._Element:
    """styles.xml de documento novo, sem os estilos do catalogo: docDefaults e os fixos."""
    raiz = etree.Element(q("styles"), nsmap={"w": W})
    dd = etree.SubElement(raiz, q("docDefaults"))
    rpd = etree.SubElement(dd, q("rPrDefault"))
    rpr = etree.SubElement(rpd, q("rPr"))
    rf = etree.SubElement(rpr, q("rFonts"))
    for atr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rf.set(q(atr), fonte)
    etree.SubElement(rpr, q("sz")).set(q("val"), str(int(tamanho_meio_pt)))
    etree.SubElement(rpr, q("szCs")).set(q("val"), str(int(tamanho_meio_pt)))
    lang = etree.SubElement(rpr, q("lang"))
    lang.set(q("val"), "pt-BR")
    lang.set(q("eastAsia"), "pt-BR")
    lang.set(q("bidi"), "ar-SA")
    ppd = etree.SubElement(dd, q("pPrDefault"))
    sp = etree.SubElement(etree.SubElement(ppd, q("pPr")), q("spacing"))
    sp.set(q("after"), str(ESPACO_DEPOIS_PADRAO_TW))
    sp.set(q("line"), str(LINHA_PADRAO))
    sp.set(q("lineRule"), "auto")
    _estilo_fixo(raiz, "character", "DefaultParagraphFont", "Default Paragraph Font",
                 extra=[("uiPriority", "1"), ("semiHidden", None), ("unhideWhenUsed", None)])
    tbl = _estilo_fixo(raiz, "table", "TableNormal", "Normal Table",
                       extra=[("uiPriority", "99"), ("semiHidden", None), ("unhideWhenUsed", None)])
    tp = etree.SubElement(tbl, q("tblPr"))
    ti = etree.SubElement(tp, q("tblInd"))
    ti.set(q("w"), "0")
    ti.set(q("type"), "dxa")
    cm = etree.SubElement(tp, q("tblCellMar"))
    for lado, val in (("top", "0"), ("left", "108"), ("bottom", "0"), ("right", "108")):
        el = etree.SubElement(cm, q(lado))
        el.set(q("w"), val)
        el.set(q("type"), "dxa")
    _estilo_fixo(raiz, "numbering", "NoList", "No List",
                 extra=[("uiPriority", "99"), ("semiHidden", None), ("unhideWhenUsed", None)])
    _estilo_grade(raiz)
    return raiz


def _parse_seguro(dados: bytes):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                             huge_tree=False, remove_blank_text=False)
    return etree.fromstring(dados, parser)


def escrever_estilos(est: Estilos | None, listas: set | None = None) -> bytes:
    """O styles.xml do catalogo: o original com os estilos alterados e novos reescritos.

    `listas`: os numIds do numbering.xml gravado (o numPr de estilo que cita outro sai)."""
    est = est if est is not None else catalogo_padrao()
    if est.xml_original:
        raiz = _parse_seguro(est.xml_original)
    else:
        # Documento novo: o docDefaults e' o do catalogo (a fonte da preferencia, M8).
        raiz = xml_base(est.padrao_caractere.get("fonte") or FONTE_PADRAO,
                        est.padrao_caractere.get("tamanho_meio_pt") or TAMANHO_PADRAO_MEIO_PT)
    sanear(raiz, listas)
    por_id = {_atr(el, "styleId"): el for el in raiz.findall(q("style"))}
    for e in est.itens.values():
        el = por_id.get(e.id)
        if e.virtual and not e.alterado:
            continue  # referencia preservada (0.1.6): o arquivo nao tinha a definicao
        if el is not None and e.no_arquivo and not e.alterado:
            continue  # volta como veio
        if e.tipo not in ("paragrafo", "caractere"):
            continue  # tabela e numeracao: o EditDoc nao edita; ficam no XML original
        if el is None:
            el = etree.SubElement(raiz, q("style"))
            e_novo = copy.copy(e)
            e_novo.no_arquivo = False  # elemento novo: grava tudo
            _escrever_estilo(el, e_novo)
        else:
            _escrever_estilo(el, e)
        _reordenar(el, ORDEM_ESTILO)
    if ESTILO_TABELA not in por_id:
        _estilo_grade(raiz)
    return _xml(raiz)


def ids_definidos(dados: bytes) -> set[str]:
    """styleId de todos os w:style de um styles.xml (para o validador)."""
    raiz = _parse_seguro(dados)
    return {_atr(el, "styleId") for el in raiz.findall(q("style")) if _atr(el, "styleId")}
