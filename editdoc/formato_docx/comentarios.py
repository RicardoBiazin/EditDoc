"""Comentarios no pacote (0.1.6): as partes estendidas, a pessoa nova e o validador. Sem Qt.

O comments.xml e' lido e escrito pelo leitor e pelo escritor de sempre (o conteudo de um
comentario sao paragrafos: formatacao, links, campos e marcadores). Aqui ficam:

- a leitura do commentsExtended.xml (w15:commentEx: paraId -> pai e "done"), do
  commentsIds.xml (w16cid: paraId -> durableId) e do commentsExtensible.xml (w16cex:
  durableId -> dateUtc);
- a escrita dessas tres partes. Sem mudanca, voltam os bytes de origem; com mudanca, a raiz
  de origem fica (namespaces, mc:Ignorable) e as entradas sao refeitas, reaproveitando o
  elemento de origem de cada comentario (atributos que o EditDoc nao conhece ficam);
- `preparar`: o que o escritor e a conferencia fazem antes de gravar (paraId e durableId de
  quem nao tem; o autor novo no people.xml preservado, sem repetir quem ja' esta');
- `validar`: comentarios coerentes entre as partes. Cada ancora (inicio, fim, referencia)
  cita um w:comment que existe; cada comentario tem uma referencia so'; inicio antes do fim;
  ids unicos; o commentsExtended cita paraIds que existem no comments.xml, e o pai tambem; o
  commentsIds tem durableIds unicos; o commentsExtensible cita durableIds do commentsIds.
"""

from __future__ import annotations

import copy
from dataclasses import replace

from lxml import etree

from editdoc.formato_docx.nomes import MC_NS, RT, W, W14_NS, q
from editdoc.modelo.comentarios import Comentarios, completar, estado

W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"
W16CID_NS = "http://schemas.microsoft.com/office/word/2016/wordml/cid"
W16CEX_NS = "http://schemas.microsoft.com/office/word/2018/wordml/cex"

RT_COMENTARIOS = RT + "comments"
RT_ESTENDIDO = "http://schemas.microsoft.com/office/2011/relationships/commentsExtended"
RT_IDS = "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds"
RT_EXTENSIVEL = "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible"
_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml."
CT_COMENTARIOS = _CT + "comments+xml"
CT_ESTENDIDO = _CT + "commentsExtended+xml"
CT_IDS = _CT + "commentsIds+xml"
CT_EXTENSIVEL = _CT + "commentsExtensible+xml"
CT_PESSOAS = _CT + "people+xml"

PARTE_COMENTARIOS = "word/comments.xml"
PARTE_ESTENDIDO = "word/commentsExtended.xml"
PARTE_IDS = "word/commentsIds.xml"
PARTE_EXTENSIVEL = "word/commentsExtensible.xml"
#: Nomes que o escritor usa (a parte preservada do pacote que cair num deles e' renomeada).
PARTES = (PARTE_COMENTARIOS, PARTE_ESTENDIDO, PARTE_IDS, PARTE_EXTENSIVEL)

#: Sufixo do Type da relacao -> chave em `Comentarios.tipos_rel`.
SUFIXOS = {"comments": "comentarios", "commentsExtended": "estendido", "commentsIds": "ids",
           "commentsExtensible": "extensivel"}
_RT_PADRAO = {"comentarios": RT_COMENTARIOS, "estendido": RT_ESTENDIDO, "ids": RT_IDS,
              "extensivel": RT_EXTENSIVEL}


def _parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                           huge_tree=False, remove_blank_text=False)


def _xml(raiz) -> bytes:
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)


def _sim(valor: str | None) -> bool:
    return (valor or "").strip().lower() in ("1", "true", "on")


# -- leitura ---------------------------------------------------------------------------

def ler_estendido(raiz) -> dict[str, tuple[str | None, bool]]:
    """paraId -> (paraId do pai ou None, resolvido)."""
    saida: dict = {}
    if raiz is None:
        return saida
    for el in raiz.iter("{%s}commentEx" % W15_NS):
        para = el.get("{%s}paraId" % W15_NS)
        if para and para not in saida:
            saida[para.upper()] = ((el.get("{%s}paraIdParent" % W15_NS) or "").upper() or None,
                                   _sim(el.get("{%s}done" % W15_NS)))
    return saida


def ler_ids(raiz) -> dict[str, str]:
    """paraId -> durableId."""
    saida: dict = {}
    if raiz is None:
        return saida
    for el in raiz.iter("{%s}commentId" % W16CID_NS):
        para = (el.get("{%s}paraId" % W16CID_NS) or "").upper()
        duravel = (el.get("{%s}durableId" % W16CID_NS) or "").upper()
        if para and duravel and para not in saida:
            saida[para] = duravel
    return saida


def ler_extensivel(raiz) -> dict[str, str]:
    """durableId -> dateUtc."""
    saida: dict = {}
    if raiz is None:
        return saida
    for el in raiz.iter("{%s}commentExtensible" % W16CEX_NS):
        duravel = (el.get("{%s}durableId" % W16CEX_NS) or "").upper()
        data = el.get("{%s}dateUtc" % W16CEX_NS)
        if duravel and data and duravel not in saida:
            saida[duravel] = data
    return saida


def para_id_do_comentario(comentario_el) -> str | None:
    """O w14:paraId do ultimo paragrafo do w:comment (a chave das partes estendidas)."""
    paragrafos = comentario_el.findall(".//" + q("p"))
    if not paragrafos:
        return None
    valor = paragrafos[-1].get("{%s}paraId" % W14_NS)
    return valor.upper() if valor else None


# -- escrita ---------------------------------------------------------------------------

def quais_partes(cat: Comentarios | None) -> set[str]:
    """As partes estendidas que o arquivo gravado leva: as que o de origem tinha e, se o
    EditDoc criou, editou, respondeu ou resolveu, as tres (como o Word grava)."""
    if cat is None or not cat.itens:
        return set()
    saida = {k for k, v in (("estendido", cat.xml_estendido), ("ids", cat.xml_ids),
                            ("extensivel", cat.xml_extensivel)) if v is not None}
    originais = {e[0]: e for e in cat.originais}
    # Mudou o que as partes estendidas dizem (comentario novo ou excluido, resposta, resolvido):
    # as tres vao, como o Word grava. Editar so' o texto nao muda essas partes.
    mexeu = any(originais.get(c.id) != estado(c) for c in cat.itens) \
        or set(originais) != {c.id for c in cat.itens}
    if mexeu:
        saida |= {"estendido", "ids", "extensivel"}
    return saida


def tipo_rel(cat: Comentarios, chave: str) -> str:
    return cat.tipos_rel.get(chave) or _RT_PADRAO[chave]


def _raiz(dados: bytes | None, tag: str, prefixo: str, ns: str):
    if dados:
        try:
            raiz = etree.fromstring(dados, _parser())
            if raiz.tag == tag:
                return raiz
        except (etree.LxmlError, ValueError):
            pass
    raiz = etree.Element(tag, nsmap={prefixo: ns, "mc": MC_NS})
    raiz.set("{%s}Ignorable" % MC_NS, prefixo)
    return raiz


def _refazer(raiz, filho: str, chave: str, entradas: list[dict]) -> bytes:
    """Troca os filhos `filho` da raiz pelas entradas, reaproveitando o elemento de origem
    que tem o mesmo valor de `chave` (os atributos que o EditDoc nao conhece ficam)."""
    antigos: dict = {}
    for el in list(raiz):
        if el.tag == filho:
            valor = (el.get(chave) or "").upper()
            antigos.setdefault(valor, el)
            raiz.remove(el)
    novos = []
    for atributos in entradas:
        el = antigos.pop(atributos[chave].upper(), None)
        el = copy.deepcopy(el) if el is not None else etree.Element(filho)
        for nome, valor in atributos.items():
            if valor is None:
                el.attrib.pop(nome, None)
            else:
                el.set(nome, valor)
        novos.append(el)
    # As entradas vao antes de qualquer outro filho de origem (extLst, que vem no fim).
    for i, el in enumerate(novos):
        raiz.insert(i, el)
    return _xml(raiz)


def _entradas_estendido(cat: Comentarios) -> list[dict]:
    paras = {c.id: c.para_id for c in cat.itens}
    p = "{%s}" % W15_NS
    saida = []
    for c in cat.itens:
        if not c.para_id:
            continue
        pai = paras.get(c.pai) if c.pai is not None else None
        saida.append({p + "paraId": c.para_id, p + "paraIdParent": pai,
                      p + "done": "1" if c.resolvido else "0"})
    return saida


def xml_estendido(cat: Comentarios) -> bytes:
    entradas = _entradas_estendido(cat)
    if cat.xml_estendido is not None:
        atual = ler_estendido(etree.fromstring(cat.xml_estendido, _parser()))
        p = "{%s}" % W15_NS
        derivado = {e[p + "paraId"]: (e[p + "paraIdParent"], e[p + "done"] == "1") for e in entradas}
        ordem_orig = [(el.get(p + "paraId") or "").upper() for el in etree.fromstring(
            cat.xml_estendido, _parser()).iter(p + "commentEx")]
        if atual == derivado and ordem_orig == [e[p + "paraId"] for e in entradas]:
            return cat.xml_estendido
    raiz = _raiz(cat.xml_estendido, "{%s}commentsEx" % W15_NS, "w15", W15_NS)
    return _refazer(raiz, "{%s}commentEx" % W15_NS, "{%s}paraId" % W15_NS, entradas)


def _entradas_ids(cat: Comentarios) -> list[dict]:
    p = "{%s}" % W16CID_NS
    return [{p + "paraId": c.para_id, p + "durableId": c.duravel}
            for c in cat.itens if c.para_id and c.duravel]


def xml_ids(cat: Comentarios) -> bytes:
    entradas = _entradas_ids(cat)
    p = "{%s}" % W16CID_NS
    if cat.xml_ids is not None:
        atual = [((el.get(p + "paraId") or "").upper(), (el.get(p + "durableId") or "").upper())
                 for el in etree.fromstring(cat.xml_ids, _parser()).iter(p + "commentId")]
        if atual == [(e[p + "paraId"], e[p + "durableId"]) for e in entradas]:
            return cat.xml_ids
    raiz = _raiz(cat.xml_ids, "{%s}commentsIds" % W16CID_NS, "w16cid", W16CID_NS)
    return _refazer(raiz, "{%s}commentId" % W16CID_NS, "{%s}paraId" % W16CID_NS, entradas)


def _entradas_extensivel(cat: Comentarios) -> list[dict]:
    p = "{%s}" % W16CEX_NS
    return [{p + "durableId": c.duravel, p + "dateUtc": c.data_utc}
            for c in cat.itens if c.duravel and c.data_utc]


def xml_extensivel(cat: Comentarios) -> bytes:
    entradas = _entradas_extensivel(cat)
    p = "{%s}" % W16CEX_NS
    if cat.xml_extensivel is not None:
        atual = [((el.get(p + "durableId") or "").upper(), el.get(p + "dateUtc"))
                 for el in etree.fromstring(cat.xml_extensivel, _parser()).iter(p + "commentExtensible")]
        if atual == [(e[p + "durableId"], e[p + "dateUtc"]) for e in entradas]:
            return cat.xml_extensivel
    raiz = _raiz(cat.xml_extensivel, "{%s}commentsExtensible" % W16CEX_NS, "w16cex", W16CEX_NS)
    return _refazer(raiz, "{%s}commentExtensible" % W16CEX_NS, "{%s}durableId" % W16CEX_NS,
                    entradas)


def pessoas_com(dados: bytes, autores: list[str]) -> bytes | None:
    """O people.xml de origem com os autores que faltam no fim (w15:person com presenceInfo
    "None", como o Word grava para conta local). None se ninguem falta. As entradas de origem,
    inclusive as repetidas, ficam como vieram."""
    try:
        raiz = etree.fromstring(dados, _parser())
    except (etree.LxmlError, ValueError):
        return None
    if raiz.tag != "{%s}people" % W15_NS:
        return None
    p = "{%s}" % W15_NS
    presentes = {el.get(p + "author") for el in raiz.iter(p + "person")}
    faltam = []
    for autor in autores:
        if autor and autor not in presentes and autor not in faltam:
            faltam.append(autor)
    if not faltam:
        return None
    for autor in faltam:
        pessoa = etree.SubElement(raiz, p + "person")
        pessoa.set(p + "author", autor)
        presenca = etree.SubElement(pessoa, p + "presenceInfo")
        presenca.set(p + "providerId", "None")
        presenca.set(p + "userId", autor)
    return _xml(raiz)


def preparar(doc):
    """Antes de gravar (o escritor e a conferencia, depois de `marcas.equilibrar`): paraId,
    durableId e dateUtc de quem nao tem, se as partes estendidas vao junto; e o autor novo no
    people.xml preservado. Devolve o mesmo documento se nada muda."""
    cat = doc.comentarios
    if cat is None or not cat.itens:
        return doc
    partes = quais_partes(cat)
    novo_cat = completar(cat, bool(partes), "ids" in partes, "extensivel" in partes)
    pacote = doc.pacote
    de_origem = {e[0] for e in cat.originais}
    novos_autores = [c.autor for c in novo_cat.itens if c.original is None or c.id not in de_origem]
    if novos_autores and pacote is not None:
        for i, parte in enumerate(pacote.partes):
            if parte.tipo_conteudo != CT_PESSOAS:
                continue
            dados = pessoas_com(parte.dados, novos_autores)
            if dados is not None:
                partes_novas = list(pacote.partes)
                partes_novas[i] = replace(parte, dados=dados)
                pacote = replace(pacote, partes=tuple(partes_novas))
            break
    if novo_cat is cat and pacote is doc.pacote:
        return doc
    saida = copy.copy(doc)
    saida.comentarios = novo_cat
    saida.pacote = pacote
    return saida


# -- validador -------------------------------------------------------------------------

def _ancoras(raiz) -> list[tuple[str, str]]:
    nomes = {q("commentRangeStart"): "inicio", q("commentRangeEnd"): "fim",
             q("commentReference"): "referencia"}
    return [(nomes[el.tag], el.get(q("id")) or "") for el in raiz.iter(*nomes)]


def validar(partes: dict[str, bytes]) -> list[str]:
    """Comentarios coerentes entre o document.xml e as quatro partes (ver o topo)."""
    problemas: list[str] = []
    doc = partes.get("word/document.xml")
    if doc is None:
        return problemas
    raiz_doc = etree.fromstring(doc, _parser())
    ancoras = _ancoras(raiz_doc)
    xml = partes.get(PARTE_COMENTARIOS)
    if xml is None:
        if ancoras:
            problemas.append(f"comentario: {len(ancoras)} ancora(s) sem word/comments.xml")
        for nome in (PARTE_ESTENDIDO, PARTE_IDS, PARTE_EXTENSIVEL):
            if nome in partes:
                problemas.append(f"{nome} sem word/comments.xml")
        return problemas
    raiz = etree.fromstring(xml, _parser())
    ids: list[str] = []
    paras: set[str] = set()
    for c in raiz.findall(q("comment")):
        ident = c.get(q("id"))
        if ident is None or not ident.lstrip("-").isdigit():
            problemas.append(f"w:comment sem w:id numerico: {ident!r}")
            continue
        if ident in ids:
            problemas.append(f"w:comment com w:id repetido: {ident}")
        ids.append(ident)
        for p in c.iter(q("p")):
            valor = p.get("{%s}paraId" % W14_NS)
            if valor:
                paras.add(valor.upper())
    vistos: dict = {}
    for i, (tipo, ident) in enumerate(ancoras):
        if ident not in ids:
            problemas.append(f"comentario: ancora ({tipo}) cita w:id {ident!r} que nao existe")
            continue
        if (tipo, ident) in vistos:
            problemas.append(f"comentario {ident}: mais de uma ancora de {tipo}")
        vistos[(tipo, ident)] = i
    for ident in ids:
        if ("referencia", ident) not in vistos:
            problemas.append(f"comentario {ident}: sem commentReference no texto")
        inicio, fim = vistos.get(("inicio", ident)), vistos.get(("fim", ident))
        if (inicio is None) != (fim is None):
            problemas.append(f"comentario {ident}: commentRangeStart sem commentRangeEnd (ou o contrario)")
        elif inicio is not None and inicio > fim:
            problemas.append(f"comentario {ident}: commentRangeEnd antes do commentRangeStart")
    estendido = partes.get(PARTE_ESTENDIDO)
    if estendido is not None:
        entradas = ler_estendido(etree.fromstring(estendido, _parser()))
        for para, (pai, _feito) in entradas.items():
            if para not in paras:
                problemas.append(f"commentsExtended: paraId {para} sem paragrafo no comments.xml")
            if pai is not None and pai not in entradas:
                problemas.append(f"commentsExtended: paraIdParent {pai} nao existe")
    duraveis: set[str] = set()
    ids_xml = partes.get(PARTE_IDS)
    if ids_xml is not None:
        p = "{%s}" % W16CID_NS
        for el in etree.fromstring(ids_xml, _parser()).iter(p + "commentId"):
            para = (el.get(p + "paraId") or "").upper()
            duravel = (el.get(p + "durableId") or "").upper()
            if para not in paras:
                problemas.append(f"commentsIds: paraId {para} sem paragrafo no comments.xml")
            if not duravel or duravel in duraveis:
                problemas.append(f"commentsIds: durableId vazio ou repetido: {duravel!r}")
            duraveis.add(duravel)
    extensivel = partes.get(PARTE_EXTENSIVEL)
    if extensivel is not None and ids_xml is not None:
        for duravel in ler_extensivel(etree.fromstring(extensivel, _parser())):
            if duravel not in duraveis:
                problemas.append(f"commentsExtensible: durableId {duravel} nao esta' no commentsIds")
    return problemas


def ancoras_validas(raiz) -> bool:
    """Para os testes: o document.xml tem ancoras de comentario."""
    return bool(_ancoras(raiz))


__all__ = ["preparar", "validar", "quais_partes", "xml_estendido", "xml_ids", "xml_extensivel",
           "pessoas_com", "ler_estendido", "ler_ids", "ler_extensivel", "W", "W15_NS"]
