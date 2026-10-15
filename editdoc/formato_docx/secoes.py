"""Secoes no arquivo (0.1.12): ler e gravar cada w:sectPr, e o validador. Sem Qt.

Ate' a 0.1.11 so' o w:sectPr do fim do corpo valia (papel, margens, cabecalhos, numeracao) e os
de dentro dos paragrafos eram achatados, com os avisos SECAO, PAGINA e CABECALHO_SECAO. Agora
cada w:sectPr vira uma `Secao` (modelo/secoes.py):

- representado: as referencias de cabecalho e rodape (cada secao so' as que declara; a que
  falta vem da anterior), w:type, w:pgSz (w, h, orient), w:pgMar (os sete atributos),
  w:titlePg e w:pgNumType (fmt dos formatos que o EditDoc mostra, start valido);
- o resto (w:cols, w:lnNumType, w:vAlign, w:docGrid, w:pgBorders, w:formProt,
  w:textDirection, w:bidi, w:rtlGutter, w:paperSrc, w:noEndnote, w:printerSettings, o
  w:footnotePr/w:endnotePr das secoes do meio, chapStyle, o w:code do papel, os rsids...) fica
  em `Secao.extras` e volta igual.

Ao gravar, o escritor parte do w:sectPr de origem (`Secao.original`, a ordem e os atributos
que o arquivo tinha) e so' troca o que o modelo mudou: sem mudanca, a forma canonica sai igual.
O w:footnotePr/w:endnotePr da ULTIMA secao continua com as notas (0.1.10, `formato_docx/notas`).

Revisao: desde a 0.1.13 o w:sectPrChange fica nos extras (sem o w:id) e volta. Filho w:
desconhecido sai com
FORMATACAO; filho de outro namespace so' fica se for extensao do Word (w14, w15...). Arquivo
hostil: mais de SECOES_MAXIMAS secoes (as que passam viram uma so', aviso SECAO) e w:cols com
mais de COLUNAS_MAXIMAS colunas (as colunas saem, aviso FORMATACAO).
"""

from __future__ import annotations

import copy
from dataclasses import replace

from lxml import etree

from editdoc.formato_docx.nomes import NS_EXTENSOES, R_NS, W, q
from editdoc.formato_docx.ordem import ORDEM_SECTPR
from editdoc.modelo.campos import FORMATOS_NUMERO, NUMERO_INICIAL_MAXIMO
from editdoc.modelo.pagina import Pagina
from editdoc.modelo.secoes import COLUNAS_MAXIMAS, SECOES_MAXIMAS, TIPOS_SECAO, Secao

#: w:type do cabecalho/rodape -> tipo do modelo, e a volta.
TIPO_FAIXA = {"default": "padrao", "first": "primeira", "even": "par"}
FAIXA_TIPO = {v: k for k, v in TIPO_FAIXA.items()}
#: Atributos do w:pgMar e o campo de Pagina que cada um preenche.
MARGENS_XML = (("top", "margem_sup_tw"), ("right", "margem_dir_tw"),
               ("bottom", "margem_inf_tw"), ("left", "margem_esq_tw"),
               ("header", "cabecalho_tw"), ("footer", "rodape_tw"),
               ("gutter", "medianiz_tw"))
_REFERENCIAS = ("headerReference", "footerReference")
_NOTAS = ("footnotePr", "endnotePr")
_URIS_EXTENSOES = set(NS_EXTENSOES.values())
_PADRAO = Pagina()


def _local(el) -> tuple[str | None, str | None]:
    t = el.tag
    if not isinstance(t, str):
        return None, None
    if t.startswith("{"):
        ns, _, loc = t[1:].partition("}")
        return ns, loc
    return "", t


def _inteiro(valor: str | None) -> int | None:
    if valor is None:
        return None
    try:
        return int(valor)
    except ValueError:
        return None


def _onoff(el) -> bool:
    v = el.get(q("val"))
    return v is None or v.lower() not in ("0", "false", "off")


def _parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                           huge_tree=False)


def canonico(el) -> str:
    """O w:sectPr em c14n exclusivo (so' os namespaces usados), como texto."""
    return etree.tostring(el, method="c14n", exclusive=True).decode("utf-8")


def elemento(texto: str | None):
    """O w:sectPr de um texto canonico, ou um w:sectPr vazio."""
    if texto:
        try:
            el = etree.fromstring(texto.encode("utf-8"), _parser())
            if el.tag == q("sectPr"):
                return el
        except (etree.LxmlError, ValueError):
            pass
    return etree.Element(q("sectPr"), nsmap={"w": W})


def _vazio(el) -> bool:
    return len(el) == 0 and not el.attrib


#: Ordem dos atributos como o Word grava (o c14n os ordena; a gravacao volta a esta ordem).
_ORDEM_ATRIBUTOS = {
    "pgSz": ("w", "h", "orient", "code"),
    "pgMar": ("top", "right", "bottom", "left", "header", "footer", "gutter"),
    "pgNumType": ("fmt", "start", "chapStyle", "chapSep"),
}


def _ordenar_atributos(sect) -> None:
    for nome, ordem in _ORDEM_ATRIBUTOS.items():
        el = sect.find(q(nome))
        if el is None:
            continue
        atuais = dict(el.attrib)
        el.attrib.clear()
        for local in ordem:
            chave = q(local)
            if chave in atuais:
                el.set(chave, atuais.pop(chave))
        for chave, valor in atuais.items():
            el.set(chave, valor)


# -- leitura ---------------------------------------------------------------------------------

def _pagina(sect) -> Pagina | None:
    """Papel, orientacao e margens. None se nao for pagina util (PAPEL_INVALIDO)."""
    pagina = Pagina()
    pg = sect.find(q("pgSz"))
    if pg is not None:
        largura, altura = _inteiro(pg.get(q("w"))), _inteiro(pg.get(q("h")))
        if largura is None or altura is None:
            return None
        pagina.largura_tw, pagina.altura_tw = largura, altura
        pagina.paisagem = pg.get(q("orient")) == "landscape"
    mar = sect.find(q("pgMar"))
    if mar is not None:
        for nome_xml, campo in MARGENS_XML:
            valor = _inteiro(mar.get(q(nome_xml)))
            if valor is not None:
                setattr(pagina, campo, valor)
    return pagina if pagina.valida() else None


def _numeracao(sect, pagina: Pagina, coletor) -> Pagina:
    """w:titlePg e w:pgNumType. Formato que o EditDoc nao desenha aparece em decimal e volta
    ao arquivo como veio (aviso NUMERO_PAGINA, sem perda)."""
    titulo = sect.find(q("titlePg"))
    if titulo is not None:
        pagina = replace(pagina, primeira_diferente=_onoff(titulo))
    num = sect.find(q("pgNumType"))
    if num is not None:
        formato = num.get(q("fmt"))
        if formato is not None:
            if formato in FORMATOS_NUMERO:
                pagina = replace(pagina, formato_numero=formato)
            else:
                coletor.somar("NUMERO_PAGINA")
        inicio = num.get(q("start"))
        if inicio is not None:
            valor = _inteiro(inicio)
            if valor is not None and 0 <= valor <= NUMERO_INICIAL_MAXIMO:
                pagina = replace(pagina, numero_inicial=valor)
            else:
                coletor.somar("NUMERO_PAGINA")
    return pagina


def _limpar(sect, coletor, final: bool) -> None:
    """Tira de `sect` (uma copia) o que nao pode voltar: revisao, filho desconhecido, colunas
    acima do limite; e, da ultima secao, as propriedades das notas (tratadas pelas notas)."""
    for f in list(sect):
        ns, loc = _local(f)
        if loc is None:
            sect.remove(f)
            continue
        if ns == W:
            if loc == "sectPrChange":
                # Revisao das propriedades da secao (0.1.13): fica, sem o w:id (o escritor
                # numera), e volta ao arquivo.
                from editdoc.formato_docx import revisoes as fx_revisoes
                fx_revisoes.sem_ids(f)
            elif loc not in ORDEM_SECTPR:
                coletor.somar("FORMATACAO")
                sect.remove(f)
            elif final and loc in _NOTAS:
                sect.remove(f)
            elif loc == "cols" and not _colunas_validas(f):
                coletor.somar("FORMATACAO")
                sect.remove(f)
        elif ns not in _URIS_EXTENSOES:
            coletor.somar("FORMATACAO")
            sect.remove(f)


def _colunas_validas(cols) -> bool:
    num = cols.get(q("num"))
    if num is not None:
        n = _inteiro(num)
        if n is None or not 1 <= n <= COLUNAS_MAXIMAS:
            return False
    return len(cols.findall(q("col"))) <= COLUNAS_MAXIMAS


def colunas_de(sect) -> tuple[int, int]:
    """(numero de colunas, espaco em twips) do w:cols; (1, 0) sem colunas."""
    cols = sect.find(q("cols")) if sect is not None else None
    if cols is None:
        return 1, 0
    n = _inteiro(cols.get(q("num")))
    larguras = cols.findall(q("col"))
    if larguras and cols.get(q("equalWidth")) in ("0", "false", "off"):
        n = len(larguras)
    n = n if n is not None and n > 0 else max(1, len(larguras))
    return n, max(0, _inteiro(cols.get(q("space"))) or 0)


def extras_de(original) -> str | None:
    """O w:sectPr sem o que o modelo representa (ver o topo). None se nada sobra."""
    sect = copy.deepcopy(original)
    for f in list(sect):
        ns, loc = _local(f)
        if ns != W:
            continue
        if loc in ("type", "titlePg") + _REFERENCIAS:
            if loc != "type" or f.get(q("val")) in TIPOS_SECAO:
                sect.remove(f)
        elif loc == "pgSz":
            for nome in ("w", "h"):
                f.attrib.pop(q(nome), None)
            if f.get(q("orient")) in ("landscape", "portrait"):
                f.attrib.pop(q("orient"), None)
            if _vazio(f):
                sect.remove(f)
        elif loc == "pgMar":
            for nome, _campo in MARGENS_XML:
                f.attrib.pop(q(nome), None)
            if _vazio(f):
                sect.remove(f)
        elif loc == "pgNumType":
            if f.get(q("fmt")) in FORMATOS_NUMERO:
                f.attrib.pop(q("fmt"), None)
            inicio = _inteiro(f.get(q("start")))
            if inicio is not None and 0 <= inicio <= NUMERO_INICIAL_MAXIMO:
                f.attrib.pop(q("start"), None)
            if _vazio(f):
                sect.remove(f)
    return None if _vazio(sect) else canonico(sect)


def ler(sect, coletor, final: bool = False) -> tuple[Secao, dict]:
    """(Secao sem o conteudo dos cabecalhos, referencias (onde, tipo) -> rId).

    Papel ou margem que nao cabe numa pagina util: A4 com as margens padrao (PAPEL_INVALIDO).
    Referencia sem tipo conhecido ou sem r:id: CABECALHO_RODAPE."""
    refs: dict[tuple[str, str], str] = {}
    for x in sect:
        ns, loc = _local(x)
        if ns != W or loc not in _REFERENCIAS:
            continue
        tipo = TIPO_FAIXA.get(x.get(q("type")) or "default")
        rid = x.get("{%s}id" % R_NS)
        if tipo is None or not rid:
            coletor.somar("CABECALHO_RODAPE")
            continue
        refs[("cabecalho" if loc == "headerReference" else "rodape", tipo)] = rid
    limpo = copy.deepcopy(sect)
    for f in list(limpo):
        if _local(f)[0] == W and _local(f)[1] in _REFERENCIAS:
            limpo.remove(f)
    _limpar(limpo, coletor, final)
    pagina = _pagina(limpo)
    if pagina is None:
        coletor.somar("PAPEL_INVALIDO")
        pagina = Pagina()
    pagina = _numeracao(limpo, pagina, coletor)
    tipo = None
    el_tipo = limpo.find(q("type"))
    if el_tipo is not None:
        val = el_tipo.get(q("val"))
        if val in TIPOS_SECAO:
            tipo = val
        elif val is not None:
            coletor.somar("FORMATACAO")
            limpo.remove(el_tipo)
    secao = Secao(pagina=pagina, tipo=tipo, extras=extras_de(limpo),
                  original=canonico(limpo), colunas=colunas_de(limpo))
    if secao.colunas[0] > 1:
        coletor.somar("COLUNAS")
    return secao, refs


# -- escrita ---------------------------------------------------------------------------------

def _inserir_em_ordem(sect, filho) -> None:
    """Poe `filho` no lugar do esquema (CT_SectPr)."""
    nome = _local(filho)[1]
    indice = ORDEM_SECTPR.index(nome)
    for i, f in enumerate(sect):
        ns, loc = _local(f)
        if ns == W and loc in ORDEM_SECTPR and ORDEM_SECTPR.index(loc) > indice:
            sect.insert(i, filho)
            return
    sect.append(filho)


def _filho(sect, nome: str, criar: bool):
    el = sect.find(q(nome))
    if el is None and criar:
        el = etree.Element(q(nome))
        _inserir_em_ordem(sect, el)
    return el


def escrever(secao: Secao, pagina: Pagina, referencias=(), notas=()) -> "etree._Element":
    """O w:sectPr da secao: o de origem com o que o modelo mudou (ver o topo do modulo).

    `referencias`: (elemento, w:type, rId) na ordem; `notas`: os w:footnotePr/w:endnotePr da
    ultima secao (0.1.10). Levanta ValueError com formato de numero que o EditDoc nao grava."""
    sect = elemento(secao.original or secao.extras)
    for f in list(sect):
        ns, loc = _local(f)
        if ns == W and (loc in _REFERENCIAS or (notas and loc in _NOTAS)):
            sect.remove(f)
    # Tipo (w:type): como a secao comeca.
    el = sect.find(q("type"))
    if secao.tipo is None:
        if el is not None and el.get(q("val")) in TIPOS_SECAO:
            sect.remove(el)
    else:
        if secao.tipo not in TIPOS_SECAO:
            raise ValueError(f"tipo de secao invalido: {secao.tipo!r}")
        el = _filho(sect, "type", True)
        el.set(q("val"), secao.tipo)
    # Papel e orientacao.
    pg = _filho(sect, "pgSz", True)
    pg.set(q("w"), str(pagina.largura_tw))
    pg.set(q("h"), str(pagina.altura_tw))
    if pagina.paisagem:
        pg.set(q("orient"), "landscape")
    elif pg.get(q("orient")) == "landscape":
        pg.attrib.pop(q("orient"))
    # Margens: o arquivo de origem pode omitir atributos (vale o padrao); so' entra o que ele
    # tinha ou o que difere do padrao. Secao nova: os sete, como o escritor sempre gravou.
    mar = sect.find(q("pgMar"))
    fresca = mar is None
    mar = _filho(sect, "pgMar", True)
    for nome, campo in MARGENS_XML:
        valor = getattr(pagina, campo)
        if fresca or mar.get(q(nome)) is not None or valor != getattr(_PADRAO, campo):
            mar.set(q(nome), str(valor))
    # Numeracao de paginas.
    formato = pagina.formato_numero
    if formato not in FORMATOS_NUMERO:
        raise ValueError(f"formato de numero invalido: {formato!r}")
    num = sect.find(q("pgNumType"))
    tinha = num is not None
    if formato != "decimal" or pagina.numero_inicial is not None or tinha:
        num = _filho(sect, "pgNumType", True)
        atual = num.get(q("fmt"))
        if formato != "decimal":
            num.set(q("fmt"), formato)
        elif atual in FORMATOS_NUMERO and atual != "decimal":
            num.attrib.pop(q("fmt"))
        inicio_atual = _inteiro(num.get(q("start")))
        if pagina.numero_inicial is not None:
            num.set(q("start"), str(min(max(int(pagina.numero_inicial), 0),
                                        NUMERO_INICIAL_MAXIMO)))
        elif inicio_atual is not None and 0 <= inicio_atual <= NUMERO_INICIAL_MAXIMO:
            num.attrib.pop(q("start"))
        if not tinha and _vazio(num):
            sect.remove(num)
    # Primeira pagina diferente.
    titulo = sect.find(q("titlePg"))
    if pagina.primeira_diferente:
        if titulo is None:
            _filho(sect, "titlePg", True)
        elif not _onoff(titulo):
            titulo.attrib.pop(q("val"), None)
    elif titulo is not None and _onoff(titulo):
        sect.remove(titulo)
    # Notas (so' a ultima secao) e referencias de cabecalho e rodape, no lugar do esquema.
    for el_nota in notas:
        _inserir_em_ordem(sect, el_nota)
    for i, (nome, tipo, rid) in enumerate(referencias):
        ref = etree.Element(q(nome))
        ref.set(q("type"), tipo)
        ref.set("{%s}id" % R_NS, rid)
        sect.insert(i, ref)
    _ordenar_atributos(sect)
    return sect


# -- validador --------------------------------------------------------------------------------

def validar(partes: dict[str, bytes]) -> list[str]:
    """Secoes no document.xml (0.1.12):

    - o w:sectPr so' existe como ultimo filho do w:body ou ultimo filho do w:pPr de um paragrafo
      do corpo (fora de tabela; dentro de controle de conteudo de bloco vale);
    - cada referencia de cabecalho/rodape tem tipo valido, um so' por tipo, e o r:id aponta
      para uma relacao do tipo header/footer com a parte no pacote;
    - limites: no maximo SECOES_MAXIMAS secoes e COLUNAS_MAXIMAS colunas."""
    if "word/document.xml" not in partes:
        return []
    from editdoc.formato_docx.ordem import _relacoes, caminho_dos_rels
    raiz = etree.fromstring(partes["word/document.xml"], _parser())
    corpo = raiz.find(q("body"))
    if corpo is None:
        return []
    rels_nome = caminho_dos_rels("word/document.xml")
    relacoes = _relacoes(partes[rels_nome], "word") if rels_nome in partes else {}
    problemas: list[str] = []
    # O w:sectPr de dentro do w:sectPrChange (0.1.13) e' a secao de antes, nao uma secao.
    secoes = [x for x in raiz.iter(q("sectPr"))
              if x.getparent() is None or x.getparent().tag != q("sectPrChange")]
    if len(secoes) > SECOES_MAXIMAS + 1:  # as quebras e a ultima secao
        problemas.append(f"secoes demais: {len(secoes)} (maximo {SECOES_MAXIMAS + 1})")
    for sect in secoes:
        pai = sect.getparent()
        if pai is corpo:
            filhos = [f for f in corpo if isinstance(f.tag, str)]
            if filhos[-1] is not sect:
                problemas.append("sectPr do corpo nao e' o ultimo filho do w:body")
        elif pai is not None and pai.tag == q("pPr"):
            filhos = [f for f in pai if isinstance(f.tag, str)]
            if filhos[-1] is not sect:
                problemas.append("sectPr nao e' o ultimo filho do w:pPr")
            p = pai.getparent()
            acima = p.getparent() if p is not None else None
            while acima is not None and acima.tag in (q("sdtContent"), q("sdt")):
                acima = acima.getparent()
            if acima is not corpo:
                problemas.append("sectPr em paragrafo fora do corpo (tabela, caixa de texto...)")
        else:
            problemas.append("sectPr fora do lugar (nem no w:body nem no w:pPr)")
        vistos = set()
        for ref in sect:
            ns, loc = _local(ref)
            if ns != W or loc not in _REFERENCIAS:
                continue
            tipo = ref.get(q("type"))
            if tipo not in TIPO_FAIXA:
                problemas.append(f"{loc} com w:type invalido: {tipo!r}")
            if (loc, tipo) in vistos:
                problemas.append(f"{loc} repetido para o tipo {tipo!r} na mesma secao")
            vistos.add((loc, tipo))
            rid = ref.get("{%s}id" % R_NS)
            rel = relacoes.get(rid)
            esperado = "/header" if loc == "headerReference" else "/footer"
            if rel is None or rel[2] or not rel[0].endswith(esperado) or rel[1] not in partes:
                problemas.append(f"{loc} '{rid}' nao resolve para uma parte de "
                                 f"{'cabecalho' if esperado == '/header' else 'rodape'}")
        cols = sect.find(q("cols"))
        if cols is not None and not _colunas_validas(cols):
            problemas.append(f"w:cols acima do limite de {COLUNAS_MAXIMAS} colunas")
        tipo = sect.find(q("type"))
        if tipo is not None and tipo.get(q("val")) not in (None,) + TIPOS_SECAO:
            problemas.append(f"w:type invalido: {tipo.get(q('val'))!r}")
    return problemas
