"""Propriedades de run (w:rPr) e de paragrafo (w:pPr) que o modelo nao representa (0.1.5). Sem Qt.

Ate' a 0.1.4 tudo o que o modelo nao tinha campo (tabulacoes, sombreamento, bordas, realce,
versalete, espacamento de caracteres, idioma...) saia do arquivo ao salvar, com o aviso
FORMATACAO ou sem aviso nenhum ("neutras"). Desde a 0.1.5 o leitor guarda o XML original
dessas propriedades em `Run.extras` e `Paragrafo.extras`, e o escritor as devolve junto com
as que ele gera, na ordem do esquema.

Tres classes de filho:

- representado: o modelo tem o campo e o escritor gera o elemento (w:b, w:i, w:strike, w:sz,
  w:rStyle; w:pStyle, w:outlineLvl, w:numPr). Nao vai para os extras;
- detalhe: o modelo tem o campo, mas o elemento traz mais do que ele (w:u duplo, w:dstrike,
  w:color com themeColor, w:rFonts com fonte de tema ou so' tres atributos, w:vertAlign
  estranho; w:jc "start", w:ind com leftChars, w:spacing com lineRule exato). O elemento
  original vai para os extras so' quando o escritor nao o geraria igual. Ao gravar, ele
  vence o gerado enquanto o campo do modelo continua com o valor que ele da' (ou herda do
  estilo o mesmo valor); se o usuario mudou o campo, sai o gerado e o detalhe cai;
- extra: o modelo nao tem o campo. Vai inteiro para os extras e volta igual.

w:szCs e' o caso especial: so' vai para os extras quando difere do w:sz, e entao o escritor
nao gera o seu.

Revisoes de formatacao (0.1.13): o w:rPrChange do run e o w:pPrChange do paragrafo sao lidos a
parte (`formato_docx/revisoes.py`, `Run.mudanca_formato`, `Paragrafo.mudanca_formato`); o
w:ins/w:del da marca de paragrafo vira `Paragrafo.marca_insercao/marca_exclusao`; o w:rPrChange
da marca de paragrafo fica nos extras (sem o w:id), e as revisoes de tabela, linha e celula
(w:tblPrChange, w:trPrChange, w:tcPrChange, w:ins/w:del da linha, w:cellIns/w:cellDel/
w:cellMerge) tambem, e voltam. Ate' a 0.1.12 tudo isso saia com o aviso REVISAO; hoje so' a
revisao fora do lugar do esquema (w:ins no rPr de um run) sai, com REVISAO. Filho w: que o
esquema nao tem sai
com FORMATACAO (perda de verdade). Filho de outro namespace so' fica se for das extensoes do
Word (w14, w15, w16...): a raiz da parte gravada declara o prefixo e o poe no mc:Ignorable.

Os extras sao texto (o Qt guarda numa propriedade de usuario): um w:rPr ou w:pPr com os
filhos, em forma canonica (c14n, so' os namespaces usados). A mesma forma sai da releitura
do arquivo gravado, entao a ida e volta e' estavel.

Controle de conteudo (w:sdt): `propriedades_de_sdt` guarda o w:sdtPr e o w:sdtEndPr na
mesma forma canonica, com o rPr de dentro na ordem do esquema.

`aparencia_run` e `aparencia_paragrafo` dizem o que a tela mostra dos extras (realce,
sombreamento, maiusculas, versalete, espacamento, bordas, tabulacoes, entrelinha exata).
"""

from __future__ import annotations

import copy
import functools
import re
from dataclasses import dataclass, field

from lxml import etree

from editdoc.formato_docx.nomes import NS_EXTENSOES, W, q
from editdoc.formato_docx.ordem import ORDEM_PPR, ORDEM_RPR

_URIS_EXTENSOES = set(NS_EXTENSOES.values())

#: rPr: representados (o modelo tem o campo e o escritor gera igual).
_RPR_REPRESENTADOS = {"b", "i", "strike", "sz", "rStyle"}
#: rPr: detalhe -> (campos do Run, nomes que o elemento substitui no gerado).
_RPR_DETALHES = {
    "u": (("sublinhado",), ("u",)),
    "dstrike": (("tachado",), ("strike", "dstrike")),
    "color": (("cor_hex",), ("color",)),
    "rFonts": (("fonte",), ("rFonts",)),
    "vertAlign": (("subscrito", "sobrescrito"), ("vertAlign",)),
}
#: pPr: representados (o modelo tem o campo).
_PPR_REPRESENTADOS = {"pStyle", "outlineLvl", "numPr", "pageBreakBefore"}
_PPR_DETALHES = {
    "jc": (("alinhamento",), ("jc",)),
    "ind": (("recuo_esquerdo_tw", "recuo_primeira_linha_tw", "recuo_direito_tw"), ("ind",)),
    "spacing": (("espaco_antes_tw", "espaco_depois_tw", "espacamento_linha_pct"), ("spacing",)),
}
#: Revisoes (0.1.13): rPrChange e pPrChange sao lidos a parte (`formato_docx/revisoes.py`); a
#: marca de paragrafo tem w:ins/w:del/w:moveFrom/w:moveTo (lidos a parte) e w:rPrChange (fica
#: nos extras). Fora desses lugares a revisao sai, com REVISAO.
_REVISOES = {"rPrChange", "pPrChange", "ins", "del", "moveFrom", "moveTo"}
_REVISOES_DA_MARCA = {"ins", "del", "moveFrom", "moveTo"}
#: O que o leitor trata a parte (quebra de secao no paragrafo).
_PPR_A_PARTE = {"sectPr"}

_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_JC = {"left": "esquerda", "start": "esquerda", "center": "centro",
       "right": "direita", "end": "direita", "both": "justificado"}
_JC_GERADO = {"esquerda": "left", "centro": "center", "direita": "right", "justificado": "both"}
_VERT = {"subscrito": "subscript", "sobrescrito": "superscript"}
_INDICE_RPR = {nome: i for i, nome in enumerate(ORDEM_RPR)}
_INDICE_PPR = {nome: i for i, nome in enumerate(ORDEM_PPR)}


def parser_seguro() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                           huge_tree=False, remove_blank_text=False)


def _local(el) -> tuple[str, str]:
    if not isinstance(el.tag, str):
        return "", ""
    qn = etree.QName(el)
    return qn.namespace or "", qn.localname


def _atr(el, nome: str) -> str | None:
    return el.get(q(nome))


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


# -- forma canonica ----------------------------------------------------------------------

def canonico(nome: str, filhos) -> str | None:
    """Os filhos dentro de um w:`nome`, em c14n, so' com os namespaces usados. None se vazio."""
    filhos = list(filhos)
    if not filhos:
        return None
    conteiner = etree.Element(q(nome), nsmap={"w": W})
    for f in filhos:
        conteiner.append(copy.deepcopy(f))
    etree.cleanup_namespaces(conteiner, top_nsmap={"w": W})
    return etree.tostring(conteiner, method="c14n").decode("utf-8")


@functools.lru_cache(maxsize=4096)
def _filhos_cache(texto: str) -> tuple:
    raiz = etree.fromstring(texto.encode("utf-8"), parser_seguro())
    return tuple(raiz)


def filhos_de(texto: str | None) -> list:
    """Copias dos filhos guardados nos extras (lista vazia se nada ou se ilegivel)."""
    if not texto:
        return []
    try:
        return [copy.deepcopy(f) for f in _filhos_cache(texto)]
    except (etree.LxmlError, ValueError):
        return []


def margens_da_celula_tw(texto: str | None) -> tuple | None:
    """(sup, esq, inf, dir) em twips do w:tcMar guardado nos extras da celula (0.1.25), ou None.

    O lado que o arquivo nao traz fica None: vale a margem da tabela, como no Word. O tcMar
    fica nos extras (o modelo nao o representa e o escritor o devolve como veio): a tela le
    daqui para a altura da celula, e o arquivo nao muda.
    """
    for f in filhos_de(texto):
        if _local(f) != (W, "tcMar"):
            continue
        lados: dict[str, int] = {}
        for nome, lado in (("top", "sup"), ("start", "esq"), ("left", "esq"),
                           ("bottom", "inf"), ("end", "dir"), ("right", "dir")):
            el = f.find(q(nome))
            valor = None if el is None else el.get(q("w"))
            if valor is not None and valor.lstrip("-").isdigit() and lado not in lados:
                lados[lado] = int(valor)
        return tuple(lados.get(lado) for lado in ("sup", "esq", "inf", "dir"))
    return None


def namespaces_usados(texto: str | None) -> dict[str, str]:
    """prefixo -> namespace das extensoes do Word usadas nos extras (para a raiz da parte)."""
    saida: dict[str, str] = {}
    for f in filhos_de(texto):
        for x in f.iter():
            if not isinstance(x.tag, str):
                continue
            nomes = [x.tag] + list(x.attrib)
            for nome in nomes:
                if nome.startswith("{"):
                    uri = nome[1:].split("}", 1)[0]
                    if uri in _URIS_EXTENSOES:
                        prefixo = next(p for p, u in NS_EXTENSOES.items() if u == uri)
                        saida[prefixo] = uri
    return saida


def _ordenar(elemento, indice: dict) -> None:
    """Filhos w: na ordem do esquema; os de extensao no fim, na ordem em que vieram."""
    filhos = list(elemento)
    w_ = [f for f in filhos if _local(f)[0] == W]
    outros = [f for f in filhos if _local(f)[0] != W]
    w_.sort(key=lambda f: indice.get(_local(f)[1], len(indice)))
    for f in filhos:
        elemento.remove(f)
    for f in w_ + outros:
        elemento.append(f)


def _sanear_rpr(rpr, estilo_existe, coletor=None, marca: bool = False) -> None:
    """rPr de dentro (marca de paragrafo, sdtPr): sem revisao, sem filho desconhecido, sem
    estilo inexistente, na ordem do esquema. `marca` (0.1.13): o rPr da marca de paragrafo,
    cujo w:ins/w:del o leitor ja' leu (sai daqui sem aviso) e cujo w:rPrChange fica (sem w:id)."""
    from editdoc.formato_docx import revisoes as fx_revisoes
    revisao = False
    for f in list(rpr):
        ns, loc = _local(f)
        if not loc:
            rpr.remove(f)
            continue
        if marca and ns == W and loc in _REVISOES_DA_MARCA:
            rpr.remove(f)
        elif marca and ns == W and loc == "rPrChange":
            fx_revisoes.sem_ids(f)
        elif ns == W and loc in _REVISOES:
            revisao = True
            rpr.remove(f)
        elif ns == W and loc not in _INDICE_RPR:
            rpr.remove(f)
            if coletor is not None:
                coletor.somar("FORMATACAO")
        elif ns != W and ns not in _URIS_EXTENSOES:
            rpr.remove(f)
        elif ns == W and loc == "rStyle" and estilo_existe is not None \
                and not estilo_existe(_atr(f, "val"), "caractere"):
            rpr.remove(f)
            if coletor is not None:
                coletor.somar("ESTILO")
    if revisao and coletor is not None:
        coletor.somar("REVISAO")
    _ordenar(rpr, _INDICE_RPR)


def rpr_canonico(rpr, estilo_existe=None, coletor=None) -> str | None:
    """Um w:rPr inteiro em forma canonica, saneado como o da marca de paragrafo (0.1.6: o rPr
    dos runs do codigo de um campo). None se vazio ou ausente."""
    if rpr is None:
        return None
    copia = copy.deepcopy(rpr)
    _sanear_rpr(copia, estilo_existe, coletor)
    return canonico("rPr", list(copia))


# -- derivados: o que o elemento poe no modelo --------------------------------------------

def derivado_rpr(loc: str, el, fontes_tema: dict) -> dict:
    """Campos do Run que o elemento w:`loc` define (a mesma regra do leitor)."""
    if loc == "u":
        return {"sublinhado": _atr(el, "val") != "none"}
    if loc == "dstrike":
        return {"tachado": _onoff(el)}
    if loc == "color":
        v = _atr(el, "val")
        return {"cor_hex": v.upper() if v and _HEX6.fullmatch(v) else None}
    if loc == "rFonts":
        from editdoc.formato_docx.estilos import fonte_de_rfonts
        return {"fonte": fonte_de_rfonts(el, fontes_tema) or None}
    if loc == "vertAlign":
        v = _atr(el, "val")
        if v == "superscript":
            return {"subscrito": False, "sobrescrito": True}
        if v == "subscript":
            return {"subscrito": True, "sobrescrito": False}
        if v == "baseline":
            return {"subscrito": False, "sobrescrito": False}
        return {"subscrito": None, "sobrescrito": None}
    return {}


def derivado_ppr(loc: str, el) -> dict:
    """Campos do Paragrafo que o elemento w:`loc` define (a mesma regra do leitor)."""
    if loc == "jc":
        return {"alinhamento": _JC.get(_atr(el, "val") or "")}
    if loc == "ind":
        out = {"recuo_esquerdo_tw": None, "recuo_primeira_linha_tw": None,
               "recuo_direito_tw": None}
        esq = _atr(el, "left") or _atr(el, "start")
        if esq is not None:
            out["recuo_esquerdo_tw"] = _inteiro(esq)
        if _atr(el, "firstLine") is not None:
            out["recuo_primeira_linha_tw"] = _inteiro(_atr(el, "firstLine"))
        elif _atr(el, "hanging") is not None:
            h = _inteiro(_atr(el, "hanging"))
            out["recuo_primeira_linha_tw"] = None if h is None else -h
        direito = _atr(el, "right") or _atr(el, "end")
        if direito is not None:
            out["recuo_direito_tw"] = _inteiro(direito)
        return out
    if loc == "spacing":
        out = {"espaco_antes_tw": _inteiro(_atr(el, "before")),
               "espaco_depois_tw": _inteiro(_atr(el, "after")),
               "espacamento_linha_pct": None}
        linha = _inteiro(_atr(el, "line"))
        if linha is not None and (_atr(el, "lineRule") or "auto") == "auto":
            out["espacamento_linha_pct"] = round(linha * 100 / 240)
        return out
    return {}


# -- gerados: o que o escritor grava a partir do modelo ------------------------------------

def elementos_rpr(run, estilo: str | None = None) -> list:
    """Os filhos de rPr que o escritor gera para o run (sem ordem)."""
    saida = []

    def novo(nome):
        el = etree.Element(q(nome))
        saida.append(el)
        return el

    if estilo:
        novo("rStyle").set(q("val"), estilo)
    if run.fonte:
        rf = novo("rFonts")
        for atr in ("ascii", "hAnsi", "eastAsia", "cs"):
            rf.set(q(atr), run.fonte)
    if run.negrito is not None:
        b = novo("b")
        if not run.negrito:
            b.set(q("val"), "0")
    if run.italico is not None:
        i = novo("i")
        if not run.italico:
            i.set(q("val"), "0")
    if run.tachado is not None:
        s = novo("strike")
        if not run.tachado:
            s.set(q("val"), "0")
    if run.cor_hex is not None:
        if not _HEX6.fullmatch(run.cor_hex):
            raise ValueError(f"cor_hex invalida: {run.cor_hex!r}")
        novo("color").set(q("val"), run.cor_hex.upper())
    if run.tamanho_meio_pt is not None:
        valor = str(int(run.tamanho_meio_pt))
        novo("sz").set(q("val"), valor)
        novo("szCs").set(q("val"), valor)
    if run.sublinhado is not None:
        novo("u").set(q("val"), "single" if run.sublinhado else "none")
    alinhamento = None
    if run.subscrito:
        alinhamento = _VERT["subscrito"]
    elif run.sobrescrito:
        alinhamento = _VERT["sobrescrito"]
    elif run.subscrito is False or run.sobrescrito is False:
        alinhamento = "baseline"
    if alinhamento:
        novo("vertAlign").set(q("val"), alinhamento)
    return saida


def elementos_ppr(p, estilo: str | None = None) -> list:
    """Os filhos de pPr que o escritor gera para o paragrafo (sem ordem)."""
    saida = []

    def novo(nome):
        el = etree.Element(q(nome))
        saida.append(el)
        return el

    if estilo is not None:
        novo("pStyle").set(q("val"), estilo)
    if p.nivel is not None:
        novo("outlineLvl").set(q("val"), str(min(max(int(p.nivel), 0), 9)))
    if p.lista is not None or p.lista_nivel is not None:
        num = novo("numPr")
        if p.lista_nivel is not None:
            etree.SubElement(num, q("ilvl")).set(q("val"), str(min(max(int(p.lista_nivel), 0), 8)))
        if p.lista is not None:
            etree.SubElement(num, q("numId")).set(q("val"), str(int(p.lista)))
    if p.alinhamento is not None:
        novo("jc").set(q("val"), _JC_GERADO[p.alinhamento])
    if (p.recuo_esquerdo_tw is not None or p.recuo_primeira_linha_tw is not None
            or p.recuo_direito_tw is not None):
        ind = novo("ind")
        if p.recuo_esquerdo_tw is not None:
            ind.set(q("left"), str(int(p.recuo_esquerdo_tw)))
        if p.recuo_direito_tw is not None:
            ind.set(q("right"), str(int(p.recuo_direito_tw)))
        if p.recuo_primeira_linha_tw is not None:
            v = int(p.recuo_primeira_linha_tw)
            if v >= 0:
                ind.set(q("firstLine"), str(v))
            else:
                ind.set(q("hanging"), str(-v))
    if (p.espaco_antes_tw is not None or p.espaco_depois_tw is not None
            or p.espacamento_linha_pct is not None):
        sp = novo("spacing")
        if p.espaco_antes_tw is not None:
            sp.set(q("before"), str(int(p.espaco_antes_tw)))
        if p.espaco_depois_tw is not None:
            sp.set(q("after"), str(int(p.espaco_depois_tw)))
        if p.espacamento_linha_pct is not None:
            sp.set(q("line"), str(round(int(p.espacamento_linha_pct) * 240 / 100)))
            sp.set(q("lineRule"), "auto")
    return saida


class _Campos:
    """Objeto com os campos de um dict (para gerar o elemento a partir do derivado)."""

    def __init__(self, campos: dict, padrao) -> None:
        self.__dict__.update({k: getattr(padrao, k) for k in vars(padrao)})
        self.__dict__.update(campos)


def _mesma_forma(a: list, b: list) -> bool:
    return canonico("x", a) == canonico("x", b)


# -- leitura --------------------------------------------------------------------------------

def ler_extras_rpr(rpr, fontes_tema: dict, coletor=None) -> str | None:
    """Os filhos do w:rPr de um run que o modelo nao representa, em forma canonica."""
    from editdoc.modelo.documento import Run
    guardar = []
    revisao = False
    sz = None
    for f in rpr:
        if _local(f) == (W, "sz"):
            sz = _atr(f, "val")
    for f in rpr:
        ns, loc = _local(f)
        if not loc:
            continue
        if ns != W:
            if ns in _URIS_EXTENSOES:
                guardar.append(f)
            continue  # outro namespace qualquer: o Word tambem o ignoraria
        if loc in _RPR_REPRESENTADOS or loc == "rPrChange":
            continue  # rPrChange: Run.mudanca_formato (0.1.13), lido pelo leitor
        if loc in _REVISOES:
            revisao = True
            continue
        if loc == "szCs":
            if not (sz is not None and dict(f.attrib) == {q("val"): sz}):
                guardar.append(f)
            continue
        if loc in _RPR_DETALHES:
            campos, nomes = _RPR_DETALHES[loc]
            derivado = derivado_rpr(loc, f, fontes_tema)
            gerado = [e for e in elementos_rpr(_Campos(derivado, Run())) if _local(e)[1] in nomes]
            if not _mesma_forma(gerado, [f]):
                guardar.append(f)
            continue
        if loc not in _INDICE_RPR:
            if coletor is not None:
                coletor.somar("FORMATACAO")
            continue
        guardar.append(f)
    if revisao and coletor is not None:
        coletor.somar("REVISAO")
    return canonico("rPr", guardar)


def ler_extras_ppr(ppr, estilo_existe=None, coletor=None) -> str | None:
    """Os filhos do w:pPr que o modelo nao representa, em forma canonica."""
    from editdoc.modelo.documento import Paragrafo
    guardar = []
    revisao = False
    for f in ppr:
        ns, loc = _local(f)
        if not loc:
            continue
        if ns != W:
            if ns in _URIS_EXTENSOES:
                guardar.append(f)
            continue
        if loc in _PPR_REPRESENTADOS or loc in _PPR_A_PARTE or loc == "pPrChange":
            continue  # pPrChange: Paragrafo.mudanca_formato (0.1.13), lido pelo leitor
        if loc in _REVISOES:
            revisao = True
            continue
        if loc in _PPR_DETALHES:
            _campos, nomes = _PPR_DETALHES[loc]
            derivado = derivado_ppr(loc, f)
            gerado = [e for e in elementos_ppr(_Campos(derivado, Paragrafo()))
                      if _local(e)[1] in nomes]
            if not _mesma_forma(gerado, [f]):
                guardar.append(f)
            continue
        if loc not in _INDICE_PPR:
            if coletor is not None:
                coletor.somar("FORMATACAO")
            continue
        if loc == "rPr":
            marca = copy.deepcopy(f)
            _sanear_rpr(marca, estilo_existe, coletor, marca=True)
            if len(marca):
                guardar.append(marca)
            continue
        guardar.append(f)
    if revisao and coletor is not None:
        coletor.somar("REVISAO")
    return canonico("pPr", guardar)


# -- escrita --------------------------------------------------------------------------------

def _confere(campos: dict, objeto, bases: dict) -> bool:
    """O modelo ainda tem o que o detalhe da'? None no modelo = herda do estilo, e vale se o
    estilo da' o mesmo (o Qt tira a formatacao direta igual a do estilo)."""
    for campo, valor in campos.items():
        atual = getattr(objeto, campo)
        if atual == valor:
            continue
        if atual is None and (valor is None or bases.get(campo) == valor):
            continue
        return False
    return True


def montar_rpr(run, estilo: str | None, bases: dict | None = None, fontes_tema: dict | None = None,
               estilo_existe=None):
    """O w:rPr do run: o que o escritor gera, com os extras de volta. None se vazio."""
    gerados = elementos_rpr(run, estilo)
    extras = filhos_de(getattr(run, "extras", None))
    bases = bases or {}
    fontes_tema = fontes_tema or {}
    finais = []
    for f in extras:
        ns, loc = _local(f)
        if ns == W and loc in _RPR_DETALHES:
            _campos, nomes = _RPR_DETALHES[loc]
            if _confere(derivado_rpr(loc, f, fontes_tema), run, bases):
                gerados = [g for g in gerados if _local(g)[1] not in nomes]
                finais.append(f)
            continue
        if ns == W and loc == "szCs":
            gerados = [g for g in gerados if _local(g)[1] != "szCs"]
        finais.append(f)
    rpr = etree.Element(q("rPr"))
    for f in gerados + finais:
        rpr.append(f)
    if not len(rpr):
        return None
    _sanear_estilos_extras(rpr, gerados, estilo_existe)
    _ordenar(rpr, _INDICE_RPR)
    return rpr


def _sanear_estilos_extras(el, gerados, estilo_existe) -> None:
    """Estilo citado dentro dos extras (a marca de paragrafo) que nao existe mais no catalogo
    sai: o Word cairia no Normal, e o validador recusa."""
    if estilo_existe is None:
        return
    for x in list(el.iter(q("rStyle"), q("pStyle"))):
        if any(x is g for g in gerados):
            continue
        tipo = "caractere" if x.tag == q("rStyle") else "paragrafo"
        if not estilo_existe(_atr(x, "val"), tipo):
            x.getparent().remove(x)


def montar_ppr(p, estilo: str | None, bases: dict | None = None, estilo_existe=None):
    """O w:pPr do paragrafo: o que o escritor gera, com os extras de volta. None se vazio."""
    gerados = elementos_ppr(p, estilo)
    extras = filhos_de(getattr(p, "extras", None))
    bases = bases or {}
    finais = []
    for f in extras:
        ns, loc = _local(f)
        if ns == W and loc in _PPR_DETALHES:
            _campos, nomes = _PPR_DETALHES[loc]
            if _confere(derivado_ppr(loc, f), p, bases):
                gerados = [g for g in gerados if _local(g)[1] not in nomes]
                finais.append(f)
            continue
        finais.append(f)
    ppr = etree.Element(q("pPr"))
    for f in gerados + finais:
        ppr.append(f)
    if not len(ppr):
        return None
    _sanear_estilos_extras(ppr, gerados, estilo_existe)
    _ordenar(ppr, _INDICE_PPR)
    return ppr


# -- tabela, linha e celula (0.1.5) -------------------------------------------------------

#: tblPr: o que o modelo representa (o estilo desde a 0.1.6, em `Tabela.estilo`) e o resto,
#: preservado. Desde a 0.1.6 o w:tblLook e o tamanho das faixas voltam: o estilo de origem
#: volta, e a formatacao condicional dele continua valendo.
_TBLPR_FORA = {"tblStyle", "tblW", "jc", "tblInd", "tblBorders", "tblLayout", "tblCellMar"}
#: trPr: tblHeader e trHeight estao no modelo; gridBefore/gridAfter/wBefore/wAfter mudam a
#: grade (o leitor completa a linha com celula vazia) e nao voltam.
_TRPR_FORA = {"tblHeader", "trHeight", "gridBefore", "gridAfter", "wBefore", "wAfter"}
_TCPR_FORA = {"tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "vAlign"}
_TABELA = {"tblPr": _TBLPR_FORA, "trPr": _TRPR_FORA, "tcPr": _TCPR_FORA}
#: Revisoes de tabela (0.1.13): ficam nos extras, sem o w:id (o escritor numera), e voltam.
_REVISOES_TABELA = {"tblPrChange", "trPrChange", "tcPrChange", "ins", "del", "cellIns", "cellDel",
                    "cellMerge"}


def ler_extras_tabela(el, coletor=None) -> str | None:
    """Os filhos de tblPr, trPr ou tcPr que o modelo nao representa (o leitor ja' avisou do
    que nao volta: grade alterada). Desde a 0.1.13 as revisoes ficam (sem o w:id)."""
    from editdoc.formato_docx import revisoes as fx_revisoes
    if el is None:
        return None
    nome = _local(el)[1]
    fora = _TABELA[nome]
    guardar = []
    for f in el:
        if _local(f)[0] != W or _local(f)[1] in fora:
            continue
        if _local(f)[1] in _REVISOES_TABELA:
            f = fx_revisoes.sem_ids(copy.deepcopy(f))
        guardar.append(f)
    return canonico(nome, guardar)


def montar_extras_tabela(el, extras: str | None) -> None:
    """Acrescenta os extras ao tblPr, trPr ou tcPr gerado (na ordem do esquema, quando ha')."""
    from editdoc.formato_docx.ordem import ORDENS
    filhos = filhos_de(extras)
    if not filhos:
        return
    nomes = {_local(f)[1] for f in el}
    for f in filhos:
        if _local(f)[1] not in nomes:
            el.append(f)
    ordem = ORDENS.get(_local(el)[1])
    if ordem is not None:
        _ordenar(el, {n: i for i, n in enumerate(ordem)})
    elif _local(el)[1] == "trPr":
        # CT_TrPr: as propriedades em qualquer ordem, depois w:ins, w:del e w:trPrChange (0.1.13).
        fim = {"ins": 0, "del": 1, "trPrChange": 2}
        filhos_el = list(el)
        finais = sorted((f for f in filhos_el if _local(f)[1] in fim), key=lambda f: fim[_local(f)[1]])
        for f in finais:
            el.remove(f)
            el.append(f)


# -- controle de conteudo -------------------------------------------------------------------

def propriedades_de_sdt(sdt, estilo_existe=None, coletor=None) -> bytes:
    """O w:sdtPr e o w:sdtEndPr do controle, em forma canonica (bytes)."""
    filhos = []
    for nome in ("sdtPr", "sdtEndPr"):
        el = sdt.find(q(nome))
        if el is None:
            continue
        el = copy.deepcopy(el)
        for rpr in el.findall(q("rPr")):
            _sanear_rpr(rpr, estilo_existe, coletor)
        filhos.append(el)
    texto = canonico("sdt", filhos)
    return texto.encode("utf-8") if texto else b""


def elementos_de_sdt(propriedades: bytes) -> list:
    """sdtPr e sdtEndPr prontos para o w:sdt gravado."""
    if not propriedades:
        return []
    return filhos_de(propriedades.decode("utf-8"))


_ID_SDT = re.compile(r'(<w:id w:val=")(-?\d+)(")')


def id_de_sdt(propriedades: bytes) -> int | None:
    m = _ID_SDT.search(propriedades.decode("utf-8", "replace")) if propriedades else None
    return int(m.group(2)) if m else None


def trocar_id_de_sdt(propriedades: bytes, novo: int) -> bytes:
    texto = propriedades.decode("utf-8")
    return _ID_SDT.sub(lambda m: f"{m.group(1)}{novo}{m.group(3)}", texto, count=1).encode("utf-8")


# -- aparencia na tela --------------------------------------------------------------------

_REALCE = {"black": "000000", "blue": "0000FF", "cyan": "00FFFF", "green": "00FF00",
           "magenta": "FF00FF", "red": "FF0000", "yellow": "FFFF00", "white": "FFFFFF",
           "darkBlue": "000080", "darkCyan": "008080", "darkGreen": "008000",
           "darkMagenta": "800080", "darkRed": "800000", "darkYellow": "808000",
           "darkGray": "808080", "lightGray": "C0C0C0"}
#: w:val de borda -> estilo de traco da tela.
_TRACOS = {"single": "simples", "thick": "simples", "double": "dupla", "dotted": "pontilhada",
           "dashed": "tracejada", "dashSmallGap": "tracejada", "dotDash": "tracejada",
           "dotDotDash": "tracejada", "triple": "dupla", "wave": "simples",
           "doubleWave": "dupla", "thinThickSmallGap": "dupla", "thickThinSmallGap": "dupla",
           "thinThickMediumGap": "dupla", "thickThinMediumGap": "dupla",
           "thinThickLargeGap": "dupla", "thickThinLargeGap": "dupla", "outset": "simples",
           "inset": "simples", "threeDEmboss": "simples", "threeDEngrave": "simples"}


@dataclass(frozen=True)
class BordaTela:
    """Um lado de borda para a tela: traco, espessura em oitavos de ponto, cor e distancia."""
    estilo: str
    oitavos_pt: int
    cor_hex: str | None
    espaco_pt: int


@dataclass(frozen=True)
class AparenciaRun:
    fundo: str | None = None  # "RRGGBB": realce, ou sombreamento
    maiusculas: bool = False
    versalete: bool = False
    espacamento_tw: int | None = None  # w:spacing (twips entre os caracteres)
    escala_pct: int | None = None  # w:w
    borda: BordaTela | None = None
    vazio: bool = True


@dataclass(frozen=True)
class AparenciaParagrafo:
    fundo: str | None = None
    #: (posicao em twips, tipo: esquerda/centro/direita/decimal/barra, preenchimento)
    tabulacoes: tuple = ()
    bordas: dict = field(default_factory=dict)  # top/left/bottom/right/between -> BordaTela
    #: ("exata" | "minima", altura em twips) do w:spacing com lineRule exact/atLeast
    linha: tuple | None = None
    vazio: bool = True


def cor_de_sombreamento(el) -> str | None:
    """A cor que um w:shd pinta (0.1.6: tambem o fundo condicional da tabela)."""
    return _cor_de_sombreamento(el)


def _cor_de_sombreamento(el) -> str | None:
    val = _atr(el, "val") or "clear"
    if val == "nil":
        return None
    fill = _atr(el, "fill")
    cor = _atr(el, "color")
    if val == "solid":
        return cor.upper() if cor and _HEX6.fullmatch(cor) else "000000"
    if fill and _HEX6.fullmatch(fill):
        return fill.upper()
    return None


def _borda_tela(el) -> BordaTela | None:
    val = _atr(el, "val") or "single"
    if val in ("nil", "none"):
        return None
    estilo = _TRACOS.get(val, "simples")
    tam = _inteiro(_atr(el, "sz"))
    tam = 4 if tam is None else min(max(tam, 2), 96)
    if val == "thick":
        tam = max(tam, 12)
    cor = _atr(el, "color")
    espaco = _inteiro(_atr(el, "space")) or 0
    return BordaTela(estilo, tam, cor.upper() if cor and _HEX6.fullmatch(cor) else None,
                     min(max(espaco, 0), 31))


@functools.lru_cache(maxsize=4096)
def aparencia_run(extras: str | None) -> AparenciaRun:
    if not extras:
        return AparenciaRun()
    fundo = sombra = None
    maiusculas = versalete = False
    espacamento = escala = None
    borda = None
    for f in filhos_de(extras):
        ns, loc = _local(f)
        if ns != W:
            continue
        if loc == "highlight":
            fundo = _REALCE.get(_atr(f, "val") or "")
        elif loc == "shd":
            sombra = _cor_de_sombreamento(f)
        elif loc == "caps":
            maiusculas = _onoff(f)
        elif loc == "smallCaps":
            versalete = _onoff(f)
        elif loc == "spacing":
            v = _inteiro(_atr(f, "val"))
            espacamento = None if v is None else min(max(v, -1584), 31680)
        elif loc == "w":
            v = _inteiro(_atr(f, "val"))
            escala = None if v is None else min(max(v, 1), 600)
        elif loc == "bdr":
            borda = _borda_tela(f)
    fundo = fundo or sombra
    vazio = not (fundo or maiusculas or versalete or espacamento or escala or borda)
    return AparenciaRun(fundo, maiusculas, versalete, espacamento, escala, borda, vazio)


_TIPOS_TAB = {"left": "esquerda", "start": "esquerda", "num": "esquerda", "center": "centro",
              "right": "direita", "end": "direita", "decimal": "decimal", "bar": "barra"}


@functools.lru_cache(maxsize=4096)
def aparencia_paragrafo(extras: str | None) -> AparenciaParagrafo:
    if not extras:
        return AparenciaParagrafo()
    fundo = None
    tabs: list = []
    bordas: dict = {}
    linha = None
    for f in filhos_de(extras):
        ns, loc = _local(f)
        if ns != W:
            continue
        if loc == "shd":
            fundo = _cor_de_sombreamento(f)
        elif loc == "tabs":
            for t in f:
                if _local(t) != (W, "tab"):
                    continue
                tipo = _TIPOS_TAB.get(_atr(t, "val") or "")
                pos = _inteiro(_atr(t, "pos"))
                if tipo is None or pos is None or not -31680 <= pos <= 31680:
                    continue  # "clear" tira a tabulacao do estilo, que a tela nao tem
                tabs.append((pos, tipo, _atr(t, "leader") or "none"))
            tabs.sort()
        elif loc == "pBdr":
            for lado in f:
                ns_l, nome = _local(lado)
                if ns_l != W:
                    continue
                nome = {"start": "left", "end": "right"}.get(nome, nome)
                if nome in ("top", "left", "bottom", "right", "between"):
                    b = _borda_tela(lado)
                    if b is not None:
                        bordas[nome] = b
        elif loc == "spacing":
            regra = _atr(f, "lineRule")
            valor = _inteiro(_atr(f, "line"))
            if regra in ("exact", "atLeast") and valor is not None and 0 < valor <= 31680:
                linha = ("exata" if regra == "exact" else "minima", valor)
    vazio = not (fundo or tabs or bordas or linha)
    return AparenciaParagrafo(fundo, tuple(tabs), bordas, linha, vazio)
