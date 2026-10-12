"""Regras que o Word exige e que o XML bem formado nao garante. Sem Qt.

O Word abre com reparo, ou pede "Modo de Compatibilidade", quando:

- os filhos de `w:pPr` e `w:rPr` estao fora da ordem do esquema;
- um `w:t` com espaco nas pontas nao tem `xml:space="preserve"` (o Word apaga o espaco);
- um `r:id` aponta para relacao inexistente, ou uma parte nao tem tipo de conteudo;
- sobra uma parte sem relacao que a alcance.

Nenhuma dessas falhas aparece no round-trip do modelo nem no python-docx: por isso
o validador roda nos testes e tambem antes de cada gravacao.

As listas de ordem sao as do esquema transitional, conferidas contra a ordem de
sucessores do python-docx 1.2.0 (spikes/docx, fato 10).
"""

from __future__ import annotations

import posixpath

from lxml import etree

from editdoc.formato_docx.nomes import CT_XML, PKG_CT, PKG_REL, R_NS, W, XML_NS, q

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
#: Ordem de `w:lvl` (numeracao): o escritor monta lvl com estes filhos.
ORDEM_LVL = ["start", "numFmt", "lvlRestart", "pStyle", "isLgl", "suff", "lvlText",
             "lvlPicBulletId", "legacy", "lvlJc", "pPr", "rPr"]

XML_PARTES = ("word/document.xml", "word/styles.xml", "word/numbering.xml",
              "word/settings.xml", "docProps/core.xml", "docProps/app.xml")


def ordenar_filhos(elemento, ordem: list[str]) -> None:
    """Reordena os filhos de `elemento` conforme `ordem`, de forma estavel."""
    indice = {q(nome): i for i, nome in enumerate(ordem)}
    filhos = list(elemento)
    for f in filhos:
        if f.tag not in indice:
            raise ValueError(f"filho inesperado em {etree.QName(elemento).localname}: {f.tag}")
    filhos.sort(key=lambda f: indice[f.tag])
    for f in filhos:
        elemento.remove(f)
    for f in filhos:
        elemento.append(f)


def _nome(el) -> str:
    return etree.QName(el).localname


def validar_ordem(raiz) -> list[str]:
    """Filhos de pPr e rPr fora da ordem do esquema, ou desconhecidos."""
    problemas: list[str] = []
    for elemento in raiz.iter(q("pPr"), q("rPr")):
        ordem = ORDEM_PPR if elemento.tag == q("pPr") else ORDEM_RPR
        pai = _nome(elemento)
        indices = []
        for filho in elemento:
            if filho.tag != q(_nome(filho)) or _nome(filho) not in ordem:
                problemas.append(f"{pai}: filho desconhecido '{_nome(filho)}'")
                continue
            indices.append((ordem.index(_nome(filho)), _nome(filho)))
        for (i1, n1), (i2, n2) in zip(indices, indices[1:]):
            if i2 < i1:
                problemas.append(f"{pai}: '{n2}' aparece depois de '{n1}' (fora de ordem)")
    return problemas


def validar_xml_space(raiz) -> list[str]:
    """Texto com espaco nas pontas precisa de xml:space="preserve"."""
    problemas: list[str] = []
    for t in raiz.iter(q("t"), q("delText")):
        texto = t.text or ""
        if texto != texto.strip() and t.get("{%s}space" % XML_NS) != "preserve":
            problemas.append(f"{_nome(t)} com espaco nas pontas sem xml:space=\"preserve\": {texto[:20]!r}")
    return problemas


def _extensao(nome: str) -> str:
    """Extensao em minusculas, com '.rels' tratado como extensao (posixpath nao o faz)."""
    base = posixpath.basename(nome)
    return base.rsplit(".", 1)[1].lower() if "." in base else ""


def _relacoes(dados: bytes, base: str) -> dict[str, tuple[str, str, bool]]:
    """Id -> (tipo, alvo resolvido, externo). `base` e' a pasta de onde os alvos saem:
    a pasta da parte de origem, ou a raiz do pacote para _rels/.rels."""
    raiz = etree.fromstring(dados)
    saida: dict[str, tuple[str, str, bool]] = {}
    for rel in raiz:
        externo = rel.get("TargetMode") == "External"
        alvo = rel.get("Target", "")
        if not externo:
            alvo = alvo[1:] if alvo.startswith("/") else posixpath.normpath(posixpath.join(base, alvo))
        saida[rel.get("Id", "")] = (rel.get("Type", ""), alvo, externo)
    return saida


def caminho_dos_rels(parte: str) -> str:
    pasta, nome = posixpath.split(parte)
    return posixpath.join(pasta, "_rels", nome + ".rels")


def validar_pacote(partes: dict[str, bytes]) -> list[str]:
    """Integridade OPC: relacoes resolvidas, tipos de conteudo, partes orfas e r:id."""
    problemas: list[str] = []
    if "[Content_Types].xml" not in partes:
        return ["[Content_Types].xml ausente"]
    ct = etree.fromstring(partes["[Content_Types].xml"])
    padroes = {f"." + d.get("Extension", "").lower(): d.get("ContentType")
               for d in ct.iter("{%s}Default" % PKG_CT)}
    sobrescritas = {o.get("PartName"): o.get("ContentType")
                    for o in ct.iter("{%s}Override" % PKG_CT)}

    for nome in partes:
        if nome == "[Content_Types].xml" or ("/" + nome) in sobrescritas:
            continue
        tipo = padroes.get("." + _extensao(nome))
        if tipo is None:
            problemas.append(f"parte sem tipo de conteudo: {nome}")
        elif tipo == CT_XML:
            # O Default "xml" cobre a parte, mas com tipo generico: o Word nao acha o conteudo.
            problemas.append(f"parte sem tipo especifico (cai em application/xml): {nome}")
    for nome in sobrescritas:
        if nome.lstrip("/") not in partes:
            problemas.append(f"Override aponta para parte inexistente: {nome}")

    if "_rels/.rels" not in partes:
        return problemas + ["_rels/.rels ausente"]

    alcancadas: set[str] = set()
    pilha = []
    for tipo, alvo, externo in _relacoes(partes["_rels/.rels"], "").values():
        if externo:
            continue
        if alvo not in partes:
            problemas.append(f"relacao do pacote aponta para parte inexistente: {alvo}")
        else:
            pilha.append(alvo)
    while pilha:
        atual = pilha.pop()
        if atual in alcancadas:
            continue
        alcancadas.add(atual)
        rels = caminho_dos_rels(atual)
        relacoes = _relacoes(partes[rels], posixpath.dirname(atual)) if rels in partes else {}
        for tipo, alvo, externo in relacoes.values():
            if externo:
                continue
            if alvo not in partes:
                problemas.append(f"relacao de {atual} aponta para parte inexistente: {alvo}")
            else:
                pilha.append(alvo)
        # Todo r:id usado no corpo tem de ter relacao na propria parte.
        if atual in XML_PARTES:
            raiz = etree.fromstring(partes[atual])
            for el in raiz.iter():
                for chave, valor in el.attrib.items():
                    if chave.startswith("{%s}" % R_NS) and valor not in relacoes:
                        problemas.append(f"{atual}: r:id '{valor}' sem relacao")

    for nome in partes:
        if nome == "[Content_Types].xml" or nome.endswith(".rels"):
            continue
        if nome not in alcancadas:
            problemas.append(f"parte orfa (nenhuma relacao a alcanca): {nome}")
    return problemas


def validar_partes_xml(partes: dict[str, bytes]) -> list[str]:
    """Ordem e xml:space em todas as partes do pacote que sao WordprocessingML."""
    problemas: list[str] = []
    for nome in ("word/document.xml", "word/styles.xml", "word/numbering.xml"):
        if nome in partes:
            raiz = etree.fromstring(partes[nome])
            problemas += [f"{nome}: {p}" for p in validar_ordem(raiz)]
            problemas += [f"{nome}: {p}" for p in validar_xml_space(raiz)]
    return problemas


def validar(partes: dict[str, bytes]) -> list[str]:
    """Tudo: pacote e partes. Lista vazia quando o arquivo esta' de acordo."""
    return validar_pacote(partes) + validar_partes_xml(partes)
