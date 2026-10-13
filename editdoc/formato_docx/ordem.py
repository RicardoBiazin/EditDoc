"""Regras que o Word exige e que o XML bem formado nao garante. Sem Qt.

O Word abre com reparo, ou pede "Modo de Compatibilidade", quando:

- os filhos de `w:pPr` e `w:rPr` estao fora da ordem do esquema;
- um `w:t` com espaco nas pontas nao tem `xml:space="preserve"` (o Word apaga o espaco);
- um `r:id` aponta para relacao inexistente, ou uma parte nao tem tipo de conteudo;
- sobra uma parte sem relacao que a alcance.

Nenhuma dessas falhas aparece no round-trip do modelo nem no python-docx: por isso
o validador roda nos testes e tambem antes de cada gravacao.

Objetos opacos (0.1.2): o que esta' dentro de uma caixa de texto, de um
mc:AlternateContent, de um w:pict, de um w:object ou de uma equacao veio do arquivo de
origem e volta como veio. As regras de ordem, de xml:space, de tabela, de campo e de
estilo valem para o que o EditDoc escreve, entao pulam esses trechos. O que vale para o
documento inteiro continua valendo la' dentro: wp:docPr com id unico, r:id com relacao
na propria parte (inclusive o o:relid do VML), e as partes do grafico e do SmartArt
tambem tem os r:id conferidos.

Campos, marcadores e hiperlinks (0.1.3): begin, separate e end equilibrados na parte
inteira (o campo pode atravessar paragrafos), o codigo no paragrafo do begin; marcadores
com id e nome unicos e em pares; o r:id do w:hyperlink aponta para relacao externa do tipo
hyperlink.

As listas de ordem sao as do esquema transitional, conferidas contra a ordem de
sucessores do python-docx 1.2.0 (spikes/docx, fato 10).
"""

from __future__ import annotations

import posixpath
import re

from lxml import etree

from editdoc.formato_docx.nomes import (CT_XML, MATH_NS, MC_NS, NS_EXTENSOES, O_NS, PKG_CT,
                                        PKG_REL, R_NS, W, XML_NS, q)

#: Filhos de rPr e pPr de outro namespace que o document.xml pode ter (0.1.5): as extensoes
#: do Word que os extras preservam (w14:ligatures, w14:textOutline...).
_EXTENSOES = {"{%s}" % uri for uri in NS_EXTENSOES.values()}

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
#: Tabelas (M4): propriedades da tabela e da celula, na ordem do esquema transitional.
ORDEM_TBLPR = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
               "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders",
               "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription",
               "tblPrChange"]
ORDEM_TCPR = ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap",
              "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark", "headers",
              "cellIns", "cellDel", "cellMerge", "tcPrChange"]
ORDEM_BORDAS = ["top", "left", "start", "bottom", "right", "end", "insideH", "insideV",
                "tl2br", "tr2bl"]
_ORDENS = {"pPr": ORDEM_PPR, "rPr": ORDEM_RPR, "tblPr": ORDEM_TBLPR, "tcPr": ORDEM_TCPR,
           "tblBorders": ORDEM_BORDAS, "tcBorders": ORDEM_BORDAS}
#: Publico para o saneamento do styles.xml (formato_docx/estilos.py).
ORDENS = _ORDENS

XML_PARTES = ("word/document.xml", "word/styles.xml", "word/numbering.xml",
              "word/settings.xml", "docProps/core.xml", "docProps/app.xml")
#: Partes de cabecalho e rodape (M5): word/header1.xml, word/footer2.xml...
_FAIXA = re.compile(r"word/(header|footer)\d+\.xml")


def eh_faixa(nome: str) -> bool:
    return _FAIXA.fullmatch(nome) is not None


#: Elementos cujo conteudo veio do arquivo de origem como objeto opaco (0.1.2).
_CONTEINERES_OPACOS = (q("txbxContent"), "{%s}AlternateContent" % MC_NS, q("pict"), q("object"),
                       "{%s}oMath" % MATH_NS, "{%s}oMathPara" % MATH_NS)


#: Filhos de w:r que fazem do run inteiro (o rPr tambem) um objeto vindo do arquivo.
_ITENS_DE_OBJETO = {q("drawing"), q("pict"), q("object"), "{%s}AlternateContent" % MC_NS}


def dentro_de_opacos(raiz) -> set:
    """Os elementos de objetos opacos: o conteudo dos conteineres e o run inteiro (com o
    rPr de origem, que pode ter filho de outro namespace) de desenho, VML ou OLE."""
    saida: set = set()
    for conteiner in raiz.iter(*_CONTEINERES_OPACOS):
        if conteiner in saida:
            continue
        saida.update(conteiner.iter())
    for run in raiz.iter(q("r")):
        if run not in saida and any(f.tag in _ITENS_DE_OBJETO for f in run):
            saida.update(run.iter())
    return saida


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


def validar_ordem(raiz, estrangeiros: bool = False) -> list[str]:
    """Filhos de pPr, rPr, tblPr, tcPr e das bordas fora da ordem do esquema, ou desconhecidos.

    estrangeiros: aceita filho de outro namespace (w14:ligatures...), que o Word grava no
    styles.xml e declara em mc:Ignorable. So' vale para o styles.xml, que volta do arquivo
    de origem; no document.xml o EditDoc nunca grava esses elementos.
    """
    problemas: list[str] = []
    opacos = dentro_de_opacos(raiz)
    for elemento in raiz.iter(*(q(nome) for nome in _ORDENS)):
        if elemento in opacos:
            continue
        ordem = _ORDENS[_nome(elemento)]
        pai = _nome(elemento)
        indices = []
        for filho in elemento:
            if isinstance(filho.tag, str) and not filho.tag.startswith("{%s}" % W) and (
                    estrangeiros or filho.tag.split("}", 1)[0] + "}" in _EXTENSOES):
                continue
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
    opacos = dentro_de_opacos(raiz)
    for t in raiz.iter(q("t"), q("delText"), q("instrText")):
        if t in opacos:
            continue
        texto = t.text or ""
        if texto != texto.strip() and t.get("{%s}space" % XML_NS) != "preserve":
            problemas.append(f"{_nome(t)} com espaco nas pontas sem xml:space=\"preserve\": {texto[:20]!r}")
    return problemas


def validar_estrutura(raiz) -> list[str]:
    """Regras de tabela e de imagem que o Word exige e o XML bem formado nao garante.

    - w:tbl comeca com tblPr e tblGrid e tem ao menos uma linha;
    - cada linha ocupa exatamente as colunas da grade (soma dos gridSpan);
    - w:tc termina em w:p (sem isso o Word abre com reparo);
    - o corpo nao termina em tabela;
    - cada wp:docPr tem id unico (tambem nos objetos opacos), e cada imagem tem tamanho
      positivo (a forma pode ter altura zero: uma linha reta).
    """
    problemas: list[str] = []
    opacos = dentro_de_opacos(raiz)
    for tbl in raiz.iter(q("tbl")):
        if tbl in opacos:
            continue
        filhos = [f for f in tbl if isinstance(f.tag, str)]
        nomes = [_nome(f) for f in filhos]
        if nomes[:2] != ["tblPr", "tblGrid"]:
            problemas.append(f"tbl sem tblPr e tblGrid no inicio: {nomes[:3]}")
            continue
        grade = len(filhos[1].findall(q("gridCol")))
        linhas = [f for f in filhos if f.tag == q("tr")]
        if not linhas:
            problemas.append("tbl sem nenhuma linha")
        for i, tr in enumerate(linhas):
            soma = 0
            for tc in tr.findall(q("tc")):
                span = tc.find(q("tcPr") + "/" + q("gridSpan"))
                soma += int(span.get(q("val"))) if span is not None else 1
            if soma != grade:
                problemas.append(f"linha {i + 1} da tabela ocupa {soma} colunas, a grade tem {grade}")
    for tc in raiz.iter(q("tc")):
        if tc in opacos:
            continue
        blocos = [f for f in tc if isinstance(f.tag, str) and _nome(f) != "tcPr"]
        if not blocos or _ultimo_bloco(blocos[-1]).tag != q("p"):
            problemas.append("tc nao termina em paragrafo")
    if raiz.tag in (q("hdr"), q("ftr")):
        # Cabecalho e rodape: ao menos um paragrafo, e terminam em paragrafo (como a celula).
        blocos = [f for f in raiz if isinstance(f.tag, str)]
        if not blocos or _ultimo_bloco(blocos[-1]).tag != q("p"):
            problemas.append(f"{_nome(raiz)} nao termina em paragrafo")
    problemas += _validar_campos(raiz, opacos)
    problemas += validar_marcadores(raiz, opacos)
    corpo = raiz.find(q("body"))
    if corpo is not None:
        blocos = [f for f in corpo if isinstance(f.tag, str) and _nome(f) != "sectPr"]
        if blocos and blocos[-1].tag == q("tbl"):
            problemas.append("o corpo termina em tabela (falta o paragrafo final)")
    ids: set[str] = set()
    wp = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
    for doc_pr in raiz.iter("{%s}docPr" % wp):
        ident = doc_pr.get("id", "")
        if ident in ids:
            problemas.append(f"wp:docPr com id repetido: {ident}")
        ids.add(ident)
    for extent in raiz.iter("{%s}extent" % wp):
        quadro = extent.getparent()
        figura = quadro is not None and quadro.find(
            "{%s}graphic/{%s}graphicData[@uri='%s']" % (_A, _A, _PIC)) is not None
        try:
            cx, cy = int(extent.get("cx", "0")), int(extent.get("cy", "0"))
            ok = (cx > 0 and cy > 0) if figura else (cx >= 0 and cy >= 0)
        except ValueError:
            ok = False
        if not ok:
            problemas.append("imagem com tamanho invalido (wp:extent)")
    return problemas


def _ultimo_bloco(el):
    """O bloco que fecha: o proprio, ou (controle de conteudo de bloco, 0.1.5) o ultimo de
    dentro do w:sdtContent, como o Word grava o controle que envolve o paragrafo da celula."""
    while el.tag == q("sdt"):
        conteudo = el.find(q("sdtContent"))
        filhos = [f for f in conteudo if isinstance(f.tag, str)] if conteudo is not None else []
        if not filhos:
            return el
        el = filhos[-1]
    return el


_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"


def _paragrafo_de(el):
    pai = el.getparent()
    while pai is not None and pai.tag != q("p"):
        pai = pai.getparent()
    return pai


def _validar_campos(raiz, opacos: set | None = None) -> list[str]:
    """Campo complexo: begin, separate e end na ordem e aninhados certo na parte inteira.

    Desde a 0.1.3 o campo pode comecar num paragrafo e terminar em outro (o sumario), mas o
    codigo (begin, instrText e separate) fica no paragrafo do begin. Um end sem begin, ou um
    begin sem end, faz o Word engolir o texto seguinte como instrucao. Os campos de dentro de
    uma caixa de texto preservada sao do arquivo de origem e ficam de fora.
    """
    opacos = dentro_de_opacos(raiz) if opacos is None else opacos
    problemas: list[str] = []
    pilha: list[list] = []  # [fase, paragrafo do begin]
    for el in raiz.iter(q("fldChar"), q("instrText")):
        if el in opacos:
            continue
        p = _paragrafo_de(el)
        if el.tag == q("instrText"):
            if not pilha or pilha[-1][0] != "codigo":
                problemas.append("instrText fora do codigo de um campo (fldChar)")
            elif pilha[-1][1] is not p:
                problemas.append("instrucao de campo (fldChar) em outro paragrafo")
            continue
        tipo = el.get(q("fldCharType"))
        if tipo == "begin":
            if pilha and pilha[-1][0] == "codigo" and pilha[-1][1] is not p:
                problemas.append("campo (fldChar) aninhado no codigo de outro paragrafo")
            pilha.append(["codigo", p])
        elif tipo == "separate":
            if not pilha or pilha[-1][0] != "codigo":
                problemas.append("campo (fldChar) com separate fora de lugar")
            elif pilha[-1][1] is not p:
                problemas.append("campo (fldChar) com separate em outro paragrafo")
            else:
                pilha[-1][0] = "resultado"
        elif tipo == "end":
            if not pilha:
                problemas.append("campo (fldChar) com end sem begin")
            else:
                pilha.pop()
        else:
            problemas.append(f"fldChar com tipo invalido: {tipo!r}")
    if pilha:
        problemas.append(f"campo (fldChar) sem end: {len(pilha)} aberto(s)")
    return problemas


def validar_marcadores(raiz, opacos: set | None = None) -> list[str]:
    """Marcadores (0.1.3): id unico, nome unico e nao vazio, cada inicio com o seu fim."""
    opacos = dentro_de_opacos(raiz) if opacos is None else opacos
    problemas: list[str] = []
    abertos: dict[str, str] = {}
    ids: set[str] = set()
    nomes: set[str] = set()
    for el in raiz.iter(q("bookmarkStart"), q("bookmarkEnd")):
        if el in opacos:
            continue
        ident = el.get(q("id"))
        if el.tag == q("bookmarkStart"):
            nome = el.get(q("name"))
            if ident is None or ident in ids:
                problemas.append(f"bookmarkStart com id repetido ou ausente: {ident!r}")
            if not nome or nome in nomes:
                problemas.append(f"bookmarkStart com nome repetido ou vazio: {nome!r}")
            ids.add(ident)
            nomes.add(nome)
            abertos[ident] = nome
        elif ident not in abertos:
            problemas.append(f"bookmarkEnd sem bookmarkStart: {ident!r}")
        else:
            del abertos[ident]
    if abertos:
        problemas.append(f"bookmarkStart sem bookmarkEnd: {sorted(abertos.values())[:3]}")
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


_RELID_O = "{%s}relid" % O_NS
_HIPERLINK = q("hyperlink")
_RID = "{%s}id" % R_NS
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)


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
        # Todo r:id usado tem de ter relacao na propria parte: no corpo, no cabecalho e
        # nas partes XML dos objetos opacos (grafico, SmartArt). O o:relid do VML tambem.
        if atual in XML_PARTES or eh_faixa(atual) or atual.lower().endswith(".xml"):
            raiz = etree.fromstring(partes[atual], _PARSER)
            for el in raiz.iter():
                if not isinstance(el.tag, str):
                    continue
                for chave, valor in el.attrib.items():
                    if (chave.startswith("{%s}" % R_NS) or chave == _RELID_O) \
                            and valor not in relacoes:
                        problemas.append(f"{atual}: r:id '{valor}' sem relacao")
                    elif el.tag == _HIPERLINK and chave == _RID and (
                            not relacoes[valor][2] or not relacoes[valor][0].endswith("/hyperlink")):
                        # 0.1.3: o endereco do link e' relacao externa do tipo hyperlink.
                        problemas.append(f"{atual}: hiperlink '{valor}' nao aponta para "
                                         "relacao externa do tipo hyperlink")

    for nome in partes:
        if nome == "[Content_Types].xml" or nome.endswith(".rels"):
            continue
        if nome not in alcancadas:
            problemas.append(f"parte orfa (nenhuma relacao a alcanca): {nome}")
    return problemas


def validar_partes_xml(partes: dict[str, bytes]) -> list[str]:
    """Ordem e xml:space em todas as partes do pacote que sao WordprocessingML."""
    problemas: list[str] = []
    nomes = ["word/document.xml", "word/styles.xml", "word/numbering.xml"]
    nomes += sorted(n for n in partes if eh_faixa(n))
    for nome in nomes:
        if nome in partes:
            raiz = etree.fromstring(partes[nome])
            # styles.xml e numbering.xml voltam do arquivo de origem (0.1.4: o numbering tambem),
            # com filhos de outro namespace (w14...) que o Word declara em mc:Ignorable.
            problemas += [f"{nome}: {p}" for p in validar_ordem(
                raiz, nome in ("word/styles.xml", "word/numbering.xml"))]
            problemas += [f"{nome}: {p}" for p in validar_xml_space(raiz)]
            if nome == "word/document.xml" or eh_faixa(nome):
                problemas += [f"{nome}: {p}" for p in validar_estrutura(raiz)]
            if nome == "word/document.xml":
                problemas += [f"{nome}: {p}" for p in validar_secao(raiz)]
    return problemas


#: Ordem dos filhos de w:sectPr (CT_SectPr). As referencias de cabecalho e rodape vem antes.
ORDEM_SECTPR = ["headerReference", "footerReference", "footnotePr", "endnotePr", "type", "pgSz",
                "pgMar", "paperSrc", "pgBorders", "lnNumType", "pgNumType", "cols", "formProt",
                "vAlign", "noEndnote", "titlePg", "textDirection", "bidi", "rtlGutter", "docGrid",
                "printerSettings", "sectPrChange"]


def validar_secao(raiz) -> list[str]:
    """Filhos do sectPr na ordem do esquema (headerReference e footerReference se misturam)."""
    problemas: list[str] = []
    for sect in raiz.iter(q("sectPr")):
        indices = []
        for f in sect:
            nome = _nome(f)
            if nome not in ORDEM_SECTPR:
                problemas.append(f"sectPr: filho desconhecido '{nome}'")
                continue
            # header e footer formam um grupo so' (xsd:choice): mesma posicao.
            indices.append((0 if nome == "footerReference" else ORDEM_SECTPR.index(nome), nome))
        for (i1, n1), (i2, n2) in zip(indices, indices[1:]):
            if i2 < i1:
                problemas.append(f"sectPr: '{n2}' aparece depois de '{n1}' (fora de ordem)")
    return problemas


def validar_estilos(partes: dict[str, bytes]) -> list[str]:
    """Todo w:pStyle e w:rStyle (M6) aponta para um estilo do styles.xml, do tipo certo.

    O Word troca a referencia quebrada pelo Normal sem avisar: o paragrafo perde o estilo
    calado. O escritor so' grava estilo que esta' no catalogo; isto prova.
    """
    if "word/styles.xml" not in partes:
        return []
    estilos = etree.fromstring(partes["word/styles.xml"])
    tipos = {s.get(q("styleId")): s.get(q("type")) or "paragraph"
             for s in estilos.iter(q("style"))}
    problemas: list[str] = []
    nomes = ["word/document.xml"] + sorted(n for n in partes if eh_faixa(n))
    for nome in nomes:
        if nome not in partes:
            continue
        raiz = etree.fromstring(partes[nome])
        opacos = dentro_de_opacos(raiz)
        for tag, tipo in (("pStyle", "paragraph"), ("rStyle", "character")):
            for el in raiz.iter(q(tag)):
                if el in opacos:
                    continue  # caixa de texto preservada: o estilo e' o do arquivo de origem
                sid = el.get(q("val"))
                if tipos.get(sid) != tipo:
                    problemas.append(f"{nome}: {tag} '{sid}' sem estilo de {tipo} no styles.xml")
    return problemas


def validar(partes: dict[str, bytes]) -> list[str]:
    """Tudo: pacote e partes. Lista vazia quando o arquivo esta' de acordo."""
    from editdoc.formato_docx import numeracao  # import tardio: numeracao usa as ordens daqui
    return (validar_pacote(partes) + validar_partes_xml(partes) + validar_estilos(partes)
            + numeracao.validar(partes))
