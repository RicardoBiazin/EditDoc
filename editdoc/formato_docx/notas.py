"""Notas de rodape e de fim no pacote (0.1.10): partes, propriedades e validador. Sem Qt.

As partes word/footnotes.xml e word/endnotes.xml sao lidas pelo leitor de sempre (o conteudo
de uma nota sao paragrafos: formatacao, links, campos, imagens) e escritas pelo escritor de
sempre. Aqui ficam:

- as propriedades (`ler_propriedades`, `elemento_de_propriedades`): w:footnotePr e w:endnotePr
  (pos, numFmt, numStart, numRestart), no sectPr e no settings.xml;
- as notas especiais padrao (separator e continuationSeparator), para o documento que ganha a
  primeira nota no EditDoc;
- a parte gravada (`parte`): sem mudanca, os bytes de origem; com mudanca, a raiz de origem
  (namespaces, mc:Ignorable) com as especiais e as notas que nao mudaram com o XML de origem,
  e as outras geradas;
- `validar`: referencias e notas coerentes. Cada w:footnoteReference cita uma nota normal que
  existe; cada nota normal tem uma referencia so'; ids unicos e numericos; as especiais que o
  settings.xml cita existem; w:footnoteRef so' dentro de nota; nenhuma referencia dentro de
  nota, cabecalho ou rodape.
"""

from __future__ import annotations

from lxml import etree

from editdoc.formato_docx.nomes import MC_NS, R_NS, RT, W, q
from editdoc.modelo.notas import (ESPECIAIS, FORMATOS, LOCAL, POSICOES_FIM, POSICOES_RODAPE,
                                  REINICIOS, NUMERO_MAXIMO, PropriedadesNota)

RT_NOTAS = {"rodape": RT + "footnotes", "fim": RT + "endnotes"}
_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml."
CT_NOTAS = {"rodape": _CT + "footnotes+xml", "fim": _CT + "endnotes+xml"}
PARTES = {"rodape": "word/footnotes.xml", "fim": "word/endnotes.xml"}
#: Raiz da parte de cada tipo.
RAIZES = {"rodape": "footnotes", "fim": "endnotes"}
#: Sufixo do Type da relacao do documento -> tipo do modelo.
SUFIXOS = {"footnotes": "rodape", "endnotes": "fim"}
#: Ordem dos filhos de w:footnotePr/w:endnotePr (CT_FtnProps, CT_FtnDocProps).
ORDEM_PR = ["pos", "numFmt", "numStart", "numRestart", "footnote", "endnote"]
_NUM_FMT_VALIDOS = None  # qualquer ST_NumberFormat volta como veio (o leitor so' confere o tamanho)


def _parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                           huge_tree=False, remove_blank_text=False)


def _xml(raiz) -> bytes:
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)


def _inteiro(valor: str | None) -> int | None:
    try:
        return int(valor) if valor is not None else None
    except ValueError:
        return None


# -- propriedades ------------------------------------------------------------------------

def ler_propriedades(el, tipo: str) -> tuple[PropriedadesNota | None, bool]:
    """(propriedades, algo foi descartado). None se `el` e' None. Valor fora do esquema nao
    vale (o Word tambem o ignora)."""
    if el is None:
        return None, False
    formato = inicio = reinicio = posicao = None
    descartado = False
    for f in el:
        if not isinstance(f.tag, str):
            continue
        val = f.get(q("val"))
        if f.tag == q("numFmt"):
            if val and len(val) <= 64 and val.isascii() and val.isalnum():
                formato = val
            else:
                descartado = True
        elif f.tag == q("numStart"):
            n = _inteiro(val)
            if n is not None and 0 <= n <= NUMERO_MAXIMO:
                inicio = n
            else:
                descartado = True
        elif f.tag == q("numRestart"):
            if val in REINICIOS and not (tipo == "fim" and val == "eachPage"):
                reinicio = val
            else:
                descartado = True
        elif f.tag == q("pos"):
            validas = POSICOES_RODAPE + POSICOES_FIM if tipo == "rodape" else POSICOES_FIM
            if val in validas:
                posicao = val
            else:
                descartado = True
    return PropriedadesNota(formato, inicio, reinicio, posicao), descartado


def elemento_de_propriedades(tipo: str, pr: PropriedadesNota):
    """O w:footnotePr (ou w:endnotePr) do sectPr com o que `pr` diz. None se nada."""
    filhos = []
    if pr.posicao is not None:
        filhos.append(("pos", pr.posicao))
    if pr.formato is not None:
        filhos.append(("numFmt", pr.formato))
    if pr.inicio is not None:
        filhos.append(("numStart", str(int(pr.inicio))))
    if pr.reinicio is not None:
        filhos.append(("numRestart", pr.reinicio))
    if not filhos:
        return None
    el = etree.Element(q(LOCAL[tipo] + "Pr"), nsmap={"w": W})
    for nome, valor in filhos:
        etree.SubElement(el, q(nome)).set(q("val"), valor)
    return el


def canonico(el) -> bytes:
    return etree.tostring(el, method="c14n", exclusive=True)


def formato_mostrado(formato: str | None) -> bool:
    """O EditDoc desenha este formato (os outros aparecem em decimal)."""
    return formato is None or formato in FORMATOS


# -- especiais padrao -------------------------------------------------------------------------

def especial_padrao(tipo: str, tipo_nota: str, ident: int) -> bytes:
    """A nota separadora como o Word cria: um paragrafo sem espaco depois, com o separador."""
    local = LOCAL[tipo]
    el = etree.Element(q(local), nsmap={"w": W})
    el.set(q("type"), tipo_nota)
    el.set(q("id"), str(ident))
    p = etree.SubElement(el, q("p"))
    ppr = etree.SubElement(p, q("pPr"))
    sp = etree.SubElement(ppr, q("spacing"))
    sp.set(q("after"), "0")
    sp.set(q("line"), "240")
    sp.set(q("lineRule"), "auto")
    r = etree.SubElement(p, q("r"))
    etree.SubElement(r, q(tipo_nota))
    return etree.tostring(el)


def especiais_padrao(tipo: str):
    """As duas especiais que o Word cria e o settings.xml cita: (tipo, id, xml)."""
    return [("separator", -1, especial_padrao(tipo, "separator", -1)),
            ("continuationSeparator", 0, especial_padrao(tipo, "continuationSeparator", 0))]


def raiz_nova(tipo: str, raiz_origem: bytes | None, nsmap_base: dict, espacos: dict,
              ignoraveis: list):
    """A raiz da parte gravada: a de origem (namespaces e atributos, sem filhos) ou uma nova
    com os namespaces que os objetos e extensoes pedem."""
    if raiz_origem:
        origem = etree.fromstring(raiz_origem, _parser())
        nsmap = dict(origem.nsmap)
        for prefixo, uri in {**nsmap_base, **espacos}.items():
            if prefixo not in nsmap and uri not in nsmap.values():
                nsmap[prefixo] = uri
        raiz = etree.Element(origem.tag, nsmap=nsmap)
        for chave, valor in origem.attrib.items():
            raiz.set(chave, valor)
        presentes = (raiz.get("{%s}Ignorable" % MC_NS) or "").split()
        faltam = [p for p in ignoraveis if p not in presentes and p in nsmap]
        if faltam:
            if "mc" not in nsmap:
                pass  # sem o prefixo mc na raiz de origem: nao ha' como declarar sem trocar a raiz
            else:
                raiz.set("{%s}Ignorable" % MC_NS, " ".join(presentes + faltam))
        return raiz
    nsmap = {**nsmap_base, **espacos}
    if ignoraveis:
        nsmap["mc"] = MC_NS
    raiz = etree.Element(q(RAIZES[tipo]), nsmap=nsmap)
    if ignoraveis:
        raiz.set("{%s}Ignorable" % MC_NS, " ".join(ignoraveis))
    return raiz


def raiz_vazia(dados: bytes) -> bytes:
    """A raiz da parte de origem sem os filhos (os namespaces e o mc:Ignorable)."""
    origem = etree.fromstring(dados, _parser())
    copia = etree.Element(origem.tag, nsmap=origem.nsmap)
    for chave, valor in origem.attrib.items():
        copia.set(chave, valor)
    return etree.tostring(copia)


# -- validador -------------------------------------------------------------------------------

def _referencias(raiz, local: str) -> list[str]:
    return [el.get(q("id")) for el in raiz.iter(q(local + "Reference"))]


def validar(partes: dict[str, bytes]) -> list[str]:
    """Notas coerentes entre o document.xml, as partes de notas e o settings.xml."""
    problemas: list[str] = []
    doc = partes.get("word/document.xml")
    if doc is None:
        return problemas
    raiz_doc = etree.fromstring(doc, _parser())
    config = partes.get("word/settings.xml")
    raiz_cfg = etree.fromstring(config, _parser()) if config else None
    for tipo in ("rodape", "fim"):
        local = LOCAL[tipo]
        refs = _referencias(raiz_doc, local)
        xml = partes.get(PARTES[tipo])
        citadas_cfg = []
        if raiz_cfg is not None:
            pr = raiz_cfg.find(q(local + "Pr"))
            if pr is not None:
                citadas_cfg = [el.get(q("id")) for el in pr.findall(q(local))]
        if xml is None:
            if refs:
                problemas.append(f"{local}: {len(refs)} referencia(s) sem {PARTES[tipo]}")
            if citadas_cfg:
                problemas.append(f"settings.xml cita {local} sem {PARTES[tipo]}")
            continue
        raiz = etree.fromstring(xml, _parser())
        if raiz.tag != q(RAIZES[tipo]):
            problemas.append(f"{PARTES[tipo]}: raiz inesperada")
            continue
        ids: list[str] = []
        normais: list[str] = []
        for n in raiz.findall(q(local)):
            ident = n.get(q("id"))
            if ident is None or not ident.lstrip("-").isdigit():
                problemas.append(f"w:{local} sem w:id numerico: {ident!r}")
                continue
            if ident in ids:
                problemas.append(f"w:{local} com w:id repetido: {ident}")
            ids.append(ident)
            tipo_nota = n.get(q("type")) or "normal"
            if tipo_nota == "normal":
                normais.append(ident)
            elif tipo_nota not in ESPECIAIS:
                problemas.append(f"w:{local} {ident} com w:type desconhecido: {tipo_nota!r}")
            for proibido in ("footnoteReference", "endnoteReference"):
                if n.find(".//" + q(proibido)) is not None:
                    problemas.append(f"w:{local} {ident}: referencia a nota dentro de nota")
            if not len(n.findall(q("p"))) and n.find(q("tbl")) is None:
                problemas.append(f"w:{local} {ident} sem paragrafo")
        vistos: set[str] = set()
        for ident in refs:
            if ident not in normais:
                problemas.append(f"{local}Reference cita w:id {ident!r}, que nao e' nota normal")
            elif ident in vistos:
                problemas.append(f"{local} {ident}: mais de uma referencia no texto")
            vistos.add(ident)
        for ident in normais:
            if ident not in vistos:
                problemas.append(f"{local} {ident}: sem {local}Reference no texto")
        for ident in citadas_cfg:
            if ident not in ids:
                problemas.append(f"settings.xml cita a {local} especial {ident}, que nao existe")
    # Referencia de nota ou numero de nota fora do lugar.
    corpo = raiz_doc.find(q("body"))
    for local in ("footnoteRef", "endnoteRef"):
        if corpo is not None and corpo.find(".//" + q(local)) is not None:
            problemas.append(f"w:{local} no corpo (so' vale dentro da nota)")
    from editdoc.formato_docx.ordem import eh_faixa
    for nome in sorted(n for n in partes if eh_faixa(n)):
        raiz = etree.fromstring(partes[nome], _parser())
        for local in ("footnoteReference", "endnoteReference"):
            if raiz.find(".//" + q(local)) is not None:
                problemas.append(f"{nome}: referencia de nota no cabecalho ou rodape")
    return problemas


def r_ids(el) -> list[str]:
    return [valor for x in el.iter() if isinstance(x.tag, str)
            for chave, valor in x.attrib.items() if chave.startswith("{%s}" % R_NS)]
