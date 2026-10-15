"""Alteracoes controladas no arquivo (0.1.13): leitura, escrita, numeracao dos w:id e validador.

Sem Qt. O leitor e o escritor chamam daqui o que e' comum:

- `revisao_de(el)`: o w:ins/w:del/w:moveFrom/w:moveTo (no run ou na marca de paragrafo) vira
  `Revisao` (autor, w:date, w16du:dateUtc). Autor longo demais, data estranha ou acima dos
  limites (`modelo/revisoes.LIMITES`): None, e quem chama faz como ate' a 0.1.12 (insercao
  aceita, exclusao fora), com o aviso REVISAO;
- `elemento_de(rev)`: o elemento para o escritor, sem w:id (a numeracao vem no fim);
- `canonico(el)`: w:rPrChange, w:pPrChange, w:tblGridChange e as revisoes guardadas nos extras
  em forma canonica (c14n exclusivo) SEM os w:id: a releitura do arquivo gravado da' o mesmo
  texto, e a conferencia compara sem depender da numeracao;
- `Numerador`: depois de montar cada parte, da' um w:id a cada revisao que nao tem, sem repetir
  os que ja' existem no pacote (comentarios, marcadores, revisoes dos comentarios e das notas
  de origem, objetos preservados). As pontas de um trecho de movimento (RangeStart/RangeEnd)
  recebem o mesmo numero (o escritor as liga por um atributo provisorio);
- `validar(partes)`: w:id das revisoes unicos (e diferentes dos de comentario e de marcador),
  w:del so' com w:delText/w:delInstrText (e w:t/w:instrText so' fora dele), cada
  moveFromRangeStart com o seu fim e um moveToRangeStart do mesmo nome (e o contrario).

Espaco de w:id: o esquema exige id unico entre as anotacoes do mesmo tipo; o Word numera
comentarios e revisoes numa sequencia so'. O EditDoc nao reaproveita, para revisao, nenhum
numero de comentario ou de marcador do documento (a escolha mais restrita, que vale nos dois
entendimentos).
"""

from __future__ import annotations

import copy
import re

from lxml import etree

from editdoc.formato_docx.nomes import NS_EXTENSOES, W, q
from editdoc.modelo.documento import MarcaMovimento, Revisao
from editdoc.modelo.revisoes import DATA_MAXIMA, LIMITES

W16DU = NS_EXTENSOES["w16du"]
#: Atributo provisorio que liga as pontas de um trecho de movimento ate' a numeracao.
PAR = "editdoc-par"

#: Elementos de revisao com w:id (CT_TrackChange e derivados, e os trechos de movimento).
TAGS_REVISAO = ("ins", "del", "moveFrom", "moveTo", "rPrChange", "pPrChange", "sectPrChange",
                "tblPrChange", "trPrChange", "tcPrChange", "tblGridChange", "tblPrExChange",
                "cellIns", "cellDel", "cellMerge", "numberingChange")
TAGS_MOVIMENTO = ("moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd")
_QN_REVISAO = {q(t) for t in TAGS_REVISAO}
_QN_MOVIMENTO = {q(t) for t in TAGS_MOVIMENTO}
_ID = q("id")
#: Revisoes no run (o conteiner) e o lado do modelo.
INSERCOES = ("ins", "moveTo")
EXCLUSOES = ("del", "moveFrom")

_NUMERO = re.compile(r'\bw:id="(-?\d+)"')


def parser_seguro() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                           huge_tree=False, remove_blank_text=False)


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _inteiro(valor) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


# -- leitura ---------------------------------------------------------------------------------

class Contagem:
    """Revisoes e autores ja' lidos (os limites valem para o documento inteiro)."""

    def __init__(self, lim: dict | None = None) -> None:
        self.lim = {**LIMITES, **(lim or {})}
        self.total = 0
        self.autores: set[str] = set()

    def aceita(self, autor: str) -> bool:
        if self.total >= self.lim["revisoes"] or len(autor) > self.lim["autor_revisao"]:
            return False
        if autor not in self.autores and len(self.autores) >= self.lim["autores_revisao"]:
            return False
        self.total += 1
        self.autores.add(autor)
        return True


def revisao_de(el, contagem: Contagem | None = None) -> Revisao | None:
    """O w:ins/w:del/w:moveFrom/w:moveTo como `Revisao`. None se nao pode ser guardada."""
    tipo = _local(el)
    if tipo not in ("ins", "del", "moveFrom", "moveTo"):
        return None
    autor = el.get(q("author")) or ""
    data = el.get(q("date"))
    utc = el.get("{%s}dateUtc" % W16DU)
    if (data is not None and len(data) > DATA_MAXIMA) or (utc is not None and len(utc) > DATA_MAXIMA):
        return None
    if contagem is not None and not contagem.aceita(autor):
        return None
    return Revisao(tipo, autor, data, utc, _inteiro(el.get(_ID)))


def movimento_de(el, contagem: Contagem | None = None) -> MarcaMovimento | None:
    """w:moveFromRangeStart/End, w:moveToRangeStart/End como marca (o par e' de quem chama)."""
    nome = _local(el)
    tipo = "de" if nome.startswith("moveFrom") else "para"
    if nome.endswith("End"):
        return MarcaMovimento(tipo, True)
    autor = el.get(q("author")) or ""
    data = el.get(q("date"))
    utc = el.get("{%s}dateUtc" % W16DU)
    if (data is not None and len(data) > DATA_MAXIMA) or (utc is not None and len(utc) > DATA_MAXIMA):
        return None
    if contagem is not None and not contagem.aceita(autor):
        return None
    fixos = {q("id"), q("name"), q("author"), q("date"), "{%s}dateUtc" % W16DU}
    outros = tuple(sorted((k, v) for k, v in el.attrib.items() if k not in fixos))
    return MarcaMovimento(tipo, False, el.get(q("name")) or "", autor, data, utc, outros)


def sem_ids(el):
    """Tira o w:id de todas as revisoes do elemento (e de dentro dele), no lugar."""
    for x in el.iter():
        if x.tag in _QN_REVISAO or x.tag in _QN_MOVIMENTO:
            x.attrib.pop(_ID, None)
    return el


def canonico(el) -> str:
    """O elemento inteiro (com os atributos) em c14n exclusivo, sem os w:id das revisoes."""
    copia = sem_ids(copy.deepcopy(el))
    return etree.tostring(copia, method="c14n", exclusive=True).decode("utf-8")


def elemento_canonico(texto: str | None):
    """O elemento de um texto de `canonico`, ou None se vazio ou ilegivel."""
    if not texto:
        return None
    try:
        return etree.fromstring(texto.encode("utf-8"), parser_seguro())
    except (etree.LxmlError, ValueError):
        return None


def tem_revisao(texto: str | None) -> bool:
    """O texto canonico (extras) tem algum elemento de revisao?"""
    return bool(texto) and any(f"<w:{t} " in texto or f"<w:{t}>" in texto or f"<w:{t}/>" in texto
                               for t in TAGS_REVISAO)


# -- escrita ---------------------------------------------------------------------------------

def atributos(el, rev: Revisao) -> None:
    """w:author, w:date e w16du:dateUtc da revisao no elemento. O w:id vem na numeracao: aqui
    fica vazio, so' para sair primeiro (como o Word grava)."""
    el.set(_ID, "")
    el.set(q("author"), rev.autor or "")
    if rev.data:
        el.set(q("date"), rev.data)
    if rev.data_utc:
        el.set("{%s}dateUtc" % W16DU, rev.data_utc)


def elemento_de(rev: Revisao, pai=None):
    el = etree.SubElement(pai, q(rev.tipo)) if pai is not None else etree.Element(q(rev.tipo))
    atributos(el, rev)
    return el


def elemento_de_movimento(m: MarcaMovimento, par: int):
    nome = ("moveFrom" if m.tipo == "de" else "moveTo") + ("RangeEnd" if m.fim else "RangeStart")
    el = etree.Element(q(nome))
    el.set(_ID, "")
    if not m.fim:
        el.set(q("name"), m.nome or "")
        if m.autor or m.data:
            el.set(q("author"), m.autor or "")
        if m.data:
            el.set(q("date"), m.data)
        if m.data_utc:
            el.set("{%s}dateUtc" % W16DU, m.data_utc)
        for chave, valor in m.outros:
            el.set(chave, valor)
    el.set(PAR, str(par))
    return el


def ids_em(textos) -> set[int]:
    """Todos os w:id numericos que aparecem nos textos XML (bytes ou str) dados."""
    saida: set[int] = set()
    for t in textos:
        if not t:
            continue
        if isinstance(t, bytes):
            t = t.decode("utf-8", "replace")
        saida.update(int(m.group(1)) for m in _NUMERO.finditer(t))
    return saida


class Numerador:
    """Numeros de w:id para as revisoes que o escritor grava, sem repetir `reservados`."""

    def __init__(self, reservados=(), inicio: int = 1) -> None:
        self.reservados = set(reservados)
        self.proximo = max(inicio, 1)
        self.dados: set[int] = set()

    def novo(self) -> int:
        while self.proximo in self.reservados or self.proximo in self.dados:
            self.proximo += 1
        n = self.proximo
        self.proximo += 1
        self.dados.add(n)
        return n

    def numerar(self, raiz, pular: set | None = None) -> None:
        """Da' w:id as revisoes sem numero (na ordem do documento) e liga as pontas dos
        movimentos pelo atributo provisorio. `pular`: elementos de objetos preservados."""
        pares: dict[tuple, int] = {}
        for el in raiz.iter():
            tag = el.tag
            if not isinstance(tag, str) or (pular and el in pular):
                continue
            if tag in _QN_REVISAO:
                if not el.get(_ID):
                    el.set(_ID, str(self.novo()))
            elif tag in _QN_MOVIMENTO:
                par = el.attrib.pop(PAR, None)
                if el.get(_ID):
                    continue
                grupo = "de" if "moveFrom" in tag else "para"
                chave = (grupo, par)
                if tag.endswith("RangeStart"):
                    pares[chave] = self.novo()
                    el.set(_ID, str(pares[chave]))
                else:
                    el.set(_ID, str(pares.pop(chave, None) or self.novo()))


# -- validador -------------------------------------------------------------------------------

_PARTES = ("word/document.xml", "word/comments.xml", "word/footnotes.xml", "word/endnotes.xml")
_FAIXA = re.compile(r"word/(header|footer)\d+\.xml")


def validar(partes: dict[str, bytes], preservados=()) -> list[str]:
    """Revisoes de todas as partes de texto (0.1.13). Ver o topo do modulo. `preservados`: os
    w:id que voltam com o XML de origem (podem se repetir como vieram)."""
    from editdoc.formato_docx.ordem import dentro_de_opacos
    preservados = {str(x) for x in preservados}
    problemas: list[str] = []
    ids_rev: dict[str, str] = {}
    ids_outros: set[str] = set()
    nomes = [n for n in _PARTES if n in partes] + sorted(n for n in partes if _FAIXA.fullmatch(n))
    raizes = []
    for nome in nomes:
        try:
            raiz = etree.fromstring(partes[nome], parser_seguro())
        except etree.LxmlError:
            continue
        raizes.append((nome, raiz, dentro_de_opacos(raiz)))
    for nome, raiz, opacos in raizes:
        for el in raiz.iter(q("bookmarkStart"), q("commentRangeStart"), q("commentReference"),
                            q("comment")):
            if el not in opacos and el.get(_ID) is not None:
                ids_outros.add(el.get(_ID))
    for nome, raiz, opacos in raizes:
        movimentos: dict[str, list] = {"moveFrom": [], "moveTo": []}
        abertos: dict[tuple, str] = {}
        for el in raiz.iter():
            if not isinstance(el.tag, str) or el in opacos:
                continue
            local = _local(el) if el.tag.startswith("{%s}" % W) else ""
            if local in TAGS_REVISAO or local in TAGS_MOVIMENTO:
                ident = el.get(_ID)
                if ident is None or not re.fullmatch(r"-?\d+", ident):
                    problemas.append(f"{nome}: w:{local} sem w:id numerico")
                    continue
                if local.endswith("RangeEnd"):
                    grupo = local[:-8]
                    if abertos.pop((grupo, ident), None) is None:
                        problemas.append(f"{nome}: w:{local} {ident} sem o inicio")
                    continue
                if ident in preservados:
                    pass
                elif ident in ids_rev:
                    problemas.append(f"{nome}: w:id {ident} repetido entre revisoes "
                                     f"(w:{local} e {ids_rev[ident]})")
                elif ident in ids_outros:
                    problemas.append(f"{nome}: w:id {ident} de revisao igual ao de um "
                                     "comentario ou marcador")
                ids_rev[ident] = f"w:{local}"
                if local.endswith("RangeStart"):
                    grupo = local[:-10]
                    abertos[(grupo, ident)] = el.get(q("name")) or ""
                    movimentos[grupo].append(el.get(q("name")) or "")
            elif local in ("t", "instrText"):
                if _dentro_de_exclusao(el):
                    problemas.append(f"{nome}: w:{local} dentro de w:del (tem de ser "
                                     f"w:del{local[0].upper()}{local[1:]})")
            elif local in ("delText", "delInstrText"):
                if not _dentro_de_exclusao(el):
                    problemas.append(f"{nome}: w:{local} fora de w:del")
        if abertos:
            problemas.append(f"{nome}: trecho de movimento sem fim: {sorted(abertos)[:3]}")
        de, para = sorted(movimentos["moveFrom"]), sorted(movimentos["moveTo"])
        if de != para:
            problemas.append(f"{nome}: origem e destino de movimento sem par "
                             f"({de[:3]} e {para[:3]})")
    return problemas


def _dentro_de_exclusao(el) -> bool:
    """O texto esta' num w:del (subindo ate' o paragrafo)."""
    pai = el.getparent()
    while pai is not None and pai.tag not in (q("p"), q("body")):
        if pai.tag == q("del"):
            return True
        pai = pai.getparent()
    return False


# -- formatacao de antes (rejeitar, modo Original, controle de alteracoes) -------------------

def run_da_mudanca(texto: str | None, estilos):
    """O `Run` (so' a formatacao) que o w:rPrChange guardado descreve, ou None. Usa a mesma
    leitura de rPr do leitor (estilos do documento para o w:rStyle)."""
    el = elemento_canonico(texto)
    if el is None or el.tag != q("rPrChange"):
        return None
    from editdoc.formato_docx import leitor
    from editdoc.formato_docx.avisos import Coletor
    from editdoc.modelo.documento import Run
    ctx = leitor._Contexto(Coletor())
    if estilos is not None:
        ctx.estilos = estilos
    run = Run()
    rpr = el.find(q("rPr"))
    if rpr is not None:
        leitor._ler_rpr(rpr, run, ctx)
    run.mudanca_formato = None
    return run


def paragrafo_da_mudanca(texto: str | None, estilos, numeracao=None) -> dict | None:
    """Os campos de `Paragrafo` que o w:pPrChange guardado descreve (o que o leitor tiraria do
    pPr de antes), ou None."""
    el = elemento_canonico(texto)
    if el is None or el.tag != q("pPrChange"):
        return None
    from editdoc.formato_docx import leitor
    from editdoc.formato_docx.avisos import Coletor
    ctx = leitor._Contexto(Coletor(), numeracao)
    if estilos is not None:
        ctx.estilos = estilos
    ppr = el.find(q("pPr"))
    if ppr is None:
        return {}
    props = leitor._ler_ppr(ppr, ctx)
    for chave in ("secao", "marca_insercao", "marca_exclusao", "mudanca_formato"):
        props.pop(chave, None)
    return props


def mudanca_de_run(run, estilo: str | None, autor: str, data: str | None) -> str:
    """O w:rPrChange (canonico, sem w:id) com a formatacao do `run` como a de antes."""
    from editdoc.formato_docx import propriedades as fx_props
    el = etree.Element(q("rPrChange"), nsmap={"w": W})
    el.set(q("author"), autor or "")
    if data:
        el.set(q("date"), data)
    rpr = fx_props.montar_rpr(run, estilo)
    el.append(rpr if rpr is not None else etree.Element(q("rPr")))
    return canonico(el)


def mudanca_de_paragrafo(p, estilo: str | None, autor: str, data: str | None) -> str:
    """O w:pPrChange (canonico, sem w:id) com as propriedades do paragrafo `p` como as de antes
    (so' as de CT_PPrBase: sem rPr, sectPr e revisoes)."""
    from editdoc.formato_docx import propriedades as fx_props
    el = etree.Element(q("pPrChange"), nsmap={"w": W})
    el.set(q("author"), autor or "")
    if data:
        el.set(q("date"), data)
    ppr = fx_props.montar_ppr(p, estilo)
    if ppr is None:
        ppr = etree.Element(q("pPr"))
    for f in list(ppr):
        if _local(f) in ("rPr", "sectPr", "pPrChange"):
            ppr.remove(f)
    el.append(ppr)
    return canonico(el)


def sem_elementos(texto: str | None, nomes) -> str | None:
    """Os extras canonicos (um w:trPr, w:tcPr, w:tblPr, w:pPr...) sem os elementos `nomes` (em
    qualquer nivel), na mesma forma canonica do leitor. None se ficar vazio."""
    el = elemento_canonico(texto)
    if el is None:
        return texto
    alvo = {q(n) for n in nomes}
    removidos = [x for x in el.iter() if x is not el and x.tag in alvo]
    if not removidos:
        return texto
    for x in removidos:
        if x.getparent() is not None:
            x.getparent().remove(x)
    for x in list(el.iter(q("rPr"))):
        if x is not el and len(x) == 0 and not x.attrib and x.getparent() is not None:
            x.getparent().remove(x)  # o rPr da marca de paragrafo que ficou vazio
    if len(el) == 0:
        return None
    from editdoc.formato_docx.propriedades import canonico as canonico_props
    return canonico_props(_local(el), list(el))


# -- o estado de antes (rejeitar, 0.1.14) ----------------------------------------------------

#: Marcas de revisao da celula (CT_TcPr): ficam como estao quando o tcPrChange e' rejeitado.
MARCAS_DE_CELULA = ("cellIns", "cellDel", "cellMerge")
#: Marcas de revisao da linha (CT_TrPr): idem para o trPrChange.
MARCAS_DE_LINHA = ("ins", "del")


def _contexto_de_leitura(estilos=None, numeracao=None):
    from editdoc.formato_docx import leitor
    from editdoc.formato_docx.avisos import Coletor
    ctx = leitor._Contexto(Coletor(), numeracao)
    if estilos is not None:
        ctx.estilos = estilos
    return ctx


def anterior(texto: str | None, mudanca: str, interno: str):
    """O elemento de antes (`interno`, um w:tblPr, w:trPr, w:tcPr, w:sectPr) guardado no
    `mudanca` (w:tblPrChange...) dos extras canonicos `texto`, ou None."""
    el = elemento_canonico(texto)
    if el is None:
        return None
    ch = el if el.tag == q(mudanca) else el.find(".//" + q(mudanca))
    if ch is None:
        return None
    dentro = ch.find(q(interno))
    return copy.deepcopy(dentro) if dentro is not None else etree.Element(q(interno))


def _com_marcas(base, atual, nomes) -> None:
    """Poe em `base` (o elemento de antes) as marcas `nomes` do elemento `atual`, no lugar delas
    no esquema (as marcas de revisao vem antes da mudanca de propriedades e depois do resto)."""
    if atual is None:
        return
    for x in list(base):
        if x.tag in {q(n) for n in nomes}:
            base.remove(x)
    for x in atual:
        if x.tag in {q(n) for n in nomes}:
            base.append(copy.deepcopy(x))


def tabela_da_mudanca(extras: str | None, colunas: list[int], estilos=None):
    """A `Tabela` (so' as propriedades, sem as linhas uteis) que o w:tblPr de antes descreve,
    com a grade `colunas`; None se nao ha' w:tblPrChange."""
    velho = anterior(extras, "tblPrChange", "tblPr")
    if velho is None:
        return None
    from editdoc.formato_docx import leitor
    tbl = etree.Element(q("tbl"), nsmap={"w": W})
    tbl.append(velho)
    grade = etree.SubElement(tbl, q("tblGrid"))
    for w in colunas:
        etree.SubElement(grade, q("gridCol")).set(q("w"), str(int(w)))
    tc = etree.SubElement(etree.SubElement(tbl, q("tr")), q("tc"))
    etree.SubElement(tc, q("p"))
    if len(colunas) > 1:
        tcpr = etree.Element(q("tcPr"))
        etree.SubElement(tcpr, q("gridSpan")).set(q("val"), str(len(colunas)))
        tc.insert(0, tcpr)
    return leitor._tabela(tbl, _contexto_de_leitura(estilos))


def grade_da_mudanca(mudanca_grade: str | None) -> list[int] | None:
    """As larguras (twips) da grade de antes, do w:tblGridChange guardado; None se ilegivel."""
    el = elemento_canonico(mudanca_grade)
    if el is None:
        return None
    grade = el.find(q("tblGrid"))
    if grade is None:
        return None
    larguras = []
    for g in grade.findall(q("gridCol")):
        try:
            larguras.append(int(g.get(q("w")) or "0"))
        except ValueError:
            return None
    return larguras or None


def linha_da_mudanca(extras_linha: str | None):
    """A `Linha` (cabecalho, altura, extras) que o w:trPr de antes descreve, com as marcas de
    linha inserida/excluida de agora; None se nao ha' w:trPrChange."""
    velho = anterior(extras_linha, "trPrChange", "trPr")
    if velho is None:
        return None
    _com_marcas(velho, elemento_canonico(extras_linha), MARCAS_DE_LINHA)
    from editdoc.formato_docx import leitor
    tr = etree.Element(q("tr"), nsmap={"w": W})
    tr.append(velho)
    return leitor._linha(tr, [], _contexto_de_leitura())


def celula_da_mudanca(extras_celula: str | None):
    """A `Celula` (sem o texto) que o w:tcPr de antes descreve, com as marcas de celula de agora
    (cellIns, cellDel, cellMerge); None se nao ha' w:tcPrChange."""
    velho = anterior(extras_celula, "tcPrChange", "tcPr")
    if velho is None:
        return None
    _com_marcas(velho, elemento_canonico(extras_celula), MARCAS_DE_CELULA)
    from editdoc.formato_docx import leitor
    tc = etree.Element(q("tc"), nsmap={"w": W})
    tc.append(velho)
    etree.SubElement(tc, q("p"))
    return leitor._celula(tc, _contexto_de_leitura())


def secao_da_mudanca(texto: str | None):
    """O w:sectPr de antes (do w:sectPrChange dos extras ou do original da secao), com as
    referencias de cabecalho e rodape de agora e, se o de antes nao tem papel ou margens, os de
    agora; None se nao ha' w:sectPrChange."""
    velho = anterior(texto, "sectPrChange", "sectPr")
    if velho is None:
        return None
    atual = elemento_canonico(texto)
    from editdoc.formato_docx import secoes as fx_secoes
    for nome in ("pgSz", "pgMar"):
        if velho.find(q(nome)) is None and atual is not None and atual.find(q(nome)) is not None:
            fx_secoes._inserir_em_ordem(velho, copy.deepcopy(atual.find(q(nome))))
    for x in list(velho):
        if x.tag in (q("headerReference"), q("footerReference"), q("sectPrChange")):
            velho.remove(x)
    return velho


def com_marca(texto: str | None, recipiente: str, rev: Revisao) -> str:
    """Os extras canonicos de um w:trPr ou w:tcPr (`recipiente`) com a marca `rev` (w:del na
    linha, w:cellDel na celula...), sem w:id, antes de uma mudanca de propriedades (o lugar do
    esquema). Uma marca do mesmo tipo que ja' estava e' trocada. (0.1.14: excluir linha e coluna
    com o controle ligado.)"""
    from editdoc.formato_docx.propriedades import canonico as canonico_props
    el = elemento_canonico(texto)
    filhos = list(el) if el is not None else []
    filhos = [f for f in filhos if f.tag != q(rev.tipo)]
    marca = elemento_de(rev)
    marca.attrib.pop(_ID, None)
    mudanca = q("trPrChange" if recipiente == "trPr" else "tcPrChange")
    i = next((k for k, f in enumerate(filhos) if f.tag == mudanca), len(filhos))
    filhos.insert(i, marca)
    return canonico_props(recipiente, filhos)


def secao_sem_mudanca(texto: str | None) -> str | None:
    """O w:sectPr canonico da secao (extras ou original) sem o w:sectPrChange."""
    el = elemento_canonico(texto)
    if el is None or el.find(q("sectPrChange")) is None:
        return texto
    for x in el.findall(q("sectPrChange")):
        el.remove(x)
    if len(el) == 0 and not el.attrib:
        return None  # como o leitor: extras vazios sao None
    from editdoc.formato_docx.secoes import canonico as canonico_secao
    return canonico_secao(el)
