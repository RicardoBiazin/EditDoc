"""Partes do pacote que o EditDoc nao edita e devolve ao arquivo (0.1.3). Sem Qt.

Antes da 0.1.3 o escritor gravava so' o que ele gera (documento, estilos, numeracao,
configuracoes refeitas, core e app novos), e o resto do pacote sumia sem aviso: as
propriedades personalizadas (docProps/custom.xml), os itens customXml (metadados do
SharePoint), a tabela de fontes, as configuracoes da Web, as notas separadoras e o
settings.xml do Word (compatibilidade, rsids, docVars, protecao).

Leitura (`capturar`): toda relacao do documento que nao e' citada no texto (r:id) e toda
relacao do pacote (_rels/.rels) e' classificada:

- o que o escritor grava (estilos, configuracoes, numeracao, tema simples, core, app);
- os comentarios (comments.xml e as tres partes estendidas), que desde a 0.1.6 o leitor e o
  escritor tratam (`formato_docx/comentarios.py`); o people.xml continua aqui, preservado;
- o que tem aviso proprio e nao volta: macros e personalizacoes de teclado e barras
  (MACROS), assinatura digital (ASSINATURA: deixaria de valer), a miniatura (MINIATURA:
  mostraria o conteudo antigo);
- notas de rodape e de fim: desde a 0.1.10 o leitor e o escritor as tratam
  (`formato_docx/notas.py`). Aqui so' fica a parte que o leitor nao conseguiu ler (acima dos
  limites, XML que nao abre): voltam as separadoras (o Word exige as que o settings.xml cita),
  e as notas de verdade tem o aviso NOTA, como ate' a 0.1.9;
- o resto volta byte a byte, com o fecho das relacoes (fontTable com as fontes embutidas,
  customXml com o itemProps, glossario, people.xml...). Parte que nao pode ir inteira
  (relacao quebrada, tipo proibido, XML invalido, limite) tem o aviso PARTE_PERDIDA.

O settings.xml original volta inteiro; o escritor so' troca o que o EditDoc controla
(w:evenAndOddHeaders, na ordem do esquema) e tira as referencias a notas que nao voltam. O
core.xml e o app.xml originais tambem voltam, com titulo, autor e datas (core) e o nome
do aplicativo (app) reescritos.

Escrita (`GravadorPacote`): cada parte fica com o nome de origem, se o escritor nao o usa;
as relacoes mantem o Id (o XML da parte nao muda) e tem o alvo recalculado; cada parte
ganha um Override com o tipo de origem.
"""

from __future__ import annotations

import hashlib
import posixpath
import re

from lxml import etree

from editdoc.formato_docx.nomes import CP, DC, DCT, EP, R_NS, W, XSI, q
from editdoc.formato_docx.opacos import parser_seguro, referencias, relativo
from editdoc.modelo.documento import PacoteOriginal, ParteOpaca

LIMITES = {
    #: partes preservadas no pacote (fecho de todas as relacoes)
    "pacote_partes": 1000,
    #: niveis de relacao a partir do documento ou do pacote
    "pacote_niveis": 6,
    #: bytes somados das partes preservadas
    "pacote_bytes": 256 * 1024 * 1024,
}

_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
#: Relacoes do documento que o escritor grava ele mesmo.
_ESCRITAS = {"styles", "settings", "numbering"}
#: Relacoes dos comentarios: o leitor e o escritor tratam (0.1.6); aqui ficam de fora.
_COMENTARIOS = {"comments", "commentsExtended", "commentsIds", "commentsExtensible"}
_MACROS = {"vbaProject", "keyMapCustomizations", "attachedToolbars", "vbaData", "wordVbaData"}
#: Relacoes de conteudo (citadas por r:id no texto). Sem citacao, nao aparecem no Word.
_CONTEUDO = {"image", "header", "footer", "hyperlink", "chart", "diagramData", "diagramLayout",
             "diagramQuickStyle", "diagramColors", "diagramDrawing", "oleObject", "package",
             "control", "aFChunk", "subDocument", "video", "audio", "media"}
_NOTAS = {"footnotes": "footnote", "endnotes": "endnote"}
#: Sufixo da relacao -> tipo do modelo (0.1.10).
_TIPO_DA_NOTA = {"footnotes": "rodape", "endnotes": "fim"}
#: Notas que o Word sempre tem e que o settings.xml cita (footnotePr/footnote).
_NOTAS_ESPECIAIS = {"separator", "continuationSeparator", "continuationNotice"}
#: Relacoes do pacote que o escritor grava.
_PACOTE_ESCRITAS = ("/officeDocument", "/core-properties", "/extended-properties")
#: Tipos de conteudo que nunca voltam: documento principal, macros, ActiveX e assinatura.
CT_PROIBIDOS = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "application/vnd.ms-word.document.macroEnabled.main+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
    "application/vnd.ms-word.template.macroEnabledTemplate.main+xml",
    "application/vnd.ms-office.vbaProject",
    "application/vnd.ms-office.vbaData+xml",
    "application/vnd.ms-word.vbaData+xml",
    "application/vnd.ms-office.activeX+xml",
    "application/vnd.ms-office.activeX",
    "application/vnd.ms-word.keyMapCustomizations+xml",
    "application/vnd.ms-word.attachedToolbars",
    "application/vnd.openxmlformats-package.digital-signature-xmlsignature+xml",
    "application/vnd.openxmlformats-package.digital-signature-origin",
    "application/vnd.openxmlformats-package.relationships+xml",
}
#: Nomes que o escritor usa para as partes dele (a parte preservada que cair num deles e'
#: renomeada).
_NOMES_DO_ESCRITOR = re.compile(
    r"(\[Content_Types\]\.xml|.*\.rels|word/(document|styles|numbering|settings)\.xml"
    r"|word/(header|footer)\d+\.xml|docProps/(core|app)\.xml"
    r"|word/comments(Extended|Ids|Extensible)?\.xml)", re.IGNORECASE)

#: Ordem dos filhos de w:settings (CT_Settings), para pôr o w:evenAndOddHeaders no lugar.
ORDEM_SETTINGS = [
    "writeProtection", "view", "zoom", "removePersonalInformation", "removeDateAndTime",
    "doNotDisplayPageBoundaries", "displayBackgroundShape", "printPostScriptOverText",
    "printFractionalCharacterWidth", "printFormsData", "embedTrueTypeFonts", "embedSystemFonts",
    "saveSubsetFonts", "saveFormsData", "mirrorMargins", "alignBordersAndEdges",
    "bordersDoNotSurroundHeader", "bordersDoNotSurroundFooter", "gutterAtTop",
    "hideSpellingErrors", "hideGrammaticalErrors", "activeWritingStyle", "proofState",
    "formsDesign", "attachedTemplate", "linkStyles", "stylePaneFormatFilter",
    "stylePaneSortMethod", "documentType", "mailMerge", "revisionView", "trackRevisions",
    "doNotTrackMoves", "doNotTrackFormatting", "documentProtection", "autoFormatOverride",
    "styleLockTheme", "styleLockQFSet", "defaultTabStop", "autoHyphenation",
    "consecutiveHyphenLimit", "hyphenationZone", "doNotHyphenateCaps", "showEnvelope",
    "summaryLength", "clickAndTypeStyle", "defaultTableStyle", "evenAndOddHeaders",
    "bookFoldRevPrinting", "bookFoldPrinting", "bookFoldPrintingSheets",
    "drawingGridHorizontalSpacing", "drawingGridVerticalSpacing",
    "displayHorizontalDrawingGridEvery", "displayVerticalDrawingGridEvery",
    "doNotUseMarginsForDrawingGridOrigin", "drawingGridHorizontalOrigin",
    "drawingGridVerticalOrigin", "doNotShadeFormData", "noPunctuationKerning",
    "characterSpacingControl", "printTwoOnOne", "strictFirstAndLastChars", "noLineBreaksAfter",
    "noLineBreaksBefore", "savePreviewPicture", "doNotValidateAgainstSchema", "saveInvalidXml",
    "ignoreMixedContent", "alwaysShowPlaceholderText", "doNotDemarcateInvalidXml",
    "saveXmlDataOnly", "useXSLTWhenSaving", "saveThroughXslt", "showXMLTags",
    "alwaysMergeEmptyNamespace", "updateFields", "hdrShapeDefaults", "footnotePr", "endnotePr",
    "compat", "docVars", "rsids", "mathPr", "attachedSchema", "themeFontLang",
    "clrSchemeMapping", "doNotIncludeSubdocsInStats", "doNotAutoCompressPictures",
    "forceUpgrade", "captions", "readModeInkLockDown", "smartTagType", "schemaLibrary",
    "shapeDefaults", "doNotEmbedSmartTags", "decimalSymbol", "listSeparator",
]
_INDICE_SETTINGS = {nome: i for i, nome in enumerate(ORDEM_SETTINGS)}


def _sufixo(tipo: str) -> str:
    return tipo.rstrip("/").rsplit("/", 1)[-1]


def _xml(raiz) -> bytes:
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)


# -- leitura -------------------------------------------------------------------------

class _Fecho:
    """Junta as partes que as relacoes preservadas alcancam, com os limites."""

    def __init__(self, lim: dict, nomes: set[str], ler_parte, relacoes_de, tipo_de, parse,
                 proibidos: set[str]) -> None:
        self.lim = {**LIMITES, **{k: v for k, v in lim.items() if k in LIMITES}}
        self.nomes = nomes
        self.ler_parte = ler_parte
        self.relacoes_de = relacoes_de
        self.tipo_de = tipo_de
        self.parse = parse
        #: partes que o escritor reescreve (documento, estilos, cabecalhos...)
        self.proibidos = proibidos
        self.partes: dict[str, ParteOpaca] = {}
        self.bytes = 0

    def _ler(self, nome: str, partes: dict, nivel: int) -> bool:
        if nome in self.partes or nome in partes:
            return True
        if nivel > self.lim["pacote_niveis"] or \
                len(self.partes) + len(partes) >= self.lim["pacote_partes"]:
            return False
        if nome not in self.nomes or nome in self.proibidos:
            return False
        tipo = self.tipo_de(nome)
        if not tipo or tipo in CT_PROIBIDOS:
            return False
        partes[nome] = None  # um ciclo de relacoes para aqui
        dados = self.ler_parte(nome)
        if not self._dados_validos(nome, tipo, dados, partes):
            return False
        relacoes = []
        for rid, (tipo_rel, alvo, externo) in sorted(self.relacoes_de(nome).items()):
            relacoes.append((rid, tipo_rel, alvo, externo))
            if not externo and not self._ler(alvo, partes, nivel + 1):
                return False
        partes[nome] = ParteOpaca(nome=nome, tipo_conteudo=tipo, dados=dados,
                                  relacoes=tuple(relacoes))
        return True

    def _dados_validos(self, nome: str, tipo: str, dados: bytes, partes: dict) -> bool:
        total = self.bytes + len(dados) + sum(len(p.dados) for p in partes.values() if p)
        if total > self.lim["pacote_bytes"]:
            return False
        if tipo.endswith("xml") or nome.lower().endswith(".xml"):
            try:
                self.parse(dados, nome)  # o parse seguro do leitor (sem DTD nem entidades)
            except Exception:  # noqa: BLE001 - XML que nao abre nao volta
                return False
        return True

    def fechar(self, alvo: str) -> bool:
        """Poe `alvo` e o que ele alcanca no fecho. False (nada muda) se algo nao pode ir."""
        partes: dict = {}
        if not self._ler(alvo, partes, 1):
            return False
        for nome, parte in partes.items():
            self.partes[nome] = parte
            self.bytes += len(parte.dados)
        return True

    def acrescentar(self, parte: ParteOpaca, alvos: list[str]) -> bool:
        """Parte ja' montada (notas filtradas) mais o fecho das relacoes dela."""
        partes: dict = {parte.nome: None}
        for alvo in alvos:
            if not self._ler(alvo, partes, 2):
                return False
        partes[parte.nome] = parte
        for nome, p in partes.items():
            self.partes[nome] = p
            self.bytes += len(p.dados)
        return True


def _notas_separadoras(dados: bytes, raiz, local: str) -> tuple[bytes, int]:
    """(XML com so' as notas separadoras, quantas notas de verdade sairam)."""
    reais = [n for n in raiz.findall(q(local)) if (n.get(q("type")) or "normal") not in _NOTAS_ESPECIAIS]
    if not reais:
        return dados, 0
    for n in reais:
        raiz.remove(n)
    return _xml(raiz), len(reais)


def _configuracoes(dados: bytes, relacoes: dict, fecho: _Fecho, coletor, parse,
                   nome: str) -> tuple[bytes, tuple]:
    """settings.xml e as relacoes dele. Relacao interna que nao pode voltar: o elemento que a
    cita sai do settings.xml, com aviso (senao o r:id ficaria sem relacao)."""
    mantidas = []
    perdidas = set()
    for rid, (tipo, alvo, externo) in sorted(relacoes.items()):
        if externo or fecho.fechar(alvo):
            mantidas.append((rid, tipo, alvo, externo))
        else:
            perdidas.add(rid)
    if not perdidas:
        return dados, tuple(mantidas)
    raiz = parse(dados, nome)
    for el in list(raiz.iter()):
        if not isinstance(el.tag, str):
            continue
        if any(k.startswith("{%s}" % R_NS) and v in perdidas for k, v in el.attrib.items()):
            filho = el
            while filho.getparent() is not None and filho.getparent() is not raiz:
                filho = filho.getparent()
            if filho.getparent() is raiz:
                raiz.remove(filho)
                coletor.somar("PARTE_PERDIDA")
    return _xml(raiz), tuple(mantidas)


def ordem_do_rid(item) -> tuple:
    """Chave de ordem de (rId, ...) pelo NUMERO do id: rId9 antes de rId10.

    A ordem das relacoes preservadas e' a ordem em que o escritor as numera. Ate' a 0.1.10 a
    ordem era a do texto ("rId10" < "rId9"): a parte que a primeira gravacao numerava rId10
    passava na frente na segunda, e cada gravacao trocava os ids de webSettings e fontTable.
    """
    rid = item[0]
    numero = rid.lstrip("rIdRID")
    return (rid[: len(rid) - len(numero)], int(numero) if numero.isdigit() else -1, rid)


def capturar(*, coletor, lim: dict, nomes: set[str], ler_parte, relacoes_de, tipo_de, parse,
             alvo_doc: str, rels_pacote: dict, rels_doc: dict, raiz_doc,
             tema_tratado: bool, proibidos: set[str], notas_lidas=frozenset()) -> PacoteOriginal:
    """O que o pacote tem fora do texto e volta ao arquivo. Ver o topo do modulo."""
    proibidos = set(proibidos) | {alvo_doc} | {
        alvo for tipo, alvo, externo in rels_pacote.values() if tipo.endswith(_PACOTE_ESCRITAS)}
    fecho = _Fecho(lim, nomes, ler_parte, relacoes_de, tipo_de, parse, proibidos)
    citados = set(referencias(raiz_doc))
    configuracoes = None
    rels_config: tuple = ()
    do_documento: list[tuple[str, str]] = []
    for rid, (tipo, alvo, externo) in sorted(rels_doc.items(), key=ordem_do_rid):
        sufixo = _sufixo(tipo)
        if rid in citados or sufixo in _CONTEUDO:
            continue  # o texto cita (imagem, cabecalho, link...) ou nao aparece no Word
        if sufixo == "settings":
            if not externo and alvo in nomes and configuracoes is None:
                dados = ler_parte(alvo)
                try:
                    parse(dados, alvo)
                except Exception:  # noqa: BLE001 - settings ilegivel: o escritor gera outro
                    coletor.somar("PARTE_PERDIDA")
                    continue
                configuracoes, rels_config = _configuracoes(dados, relacoes_de(alvo), fecho,
                                                            coletor, parse, alvo)
            continue
        if sufixo in _ESCRITAS or (sufixo == "theme" and tema_tratado):
            continue
        if sufixo in _COMENTARIOS:
            continue  # comentarios (0.1.6): o leitor os le, com os avisos do que nao vale
        if sufixo in _MACROS:
            if coletor.contagem("MACROS") == 0:
                coletor.somar("MACROS")
            continue
        if externo:
            do_documento.append((tipo, alvo, True))
            continue
        if sufixo in _NOTAS:
            if _TIPO_DA_NOTA[sufixo] in notas_lidas:
                continue  # 0.1.10: o leitor leu a parte; o escritor a grava
            if _notas(tipo, alvo, sufixo, fecho, coletor, ler_parte, relacoes_de, tipo_de, parse):
                do_documento.append((tipo, alvo, False))
            continue
        if fecho.fechar(alvo):
            do_documento.append((tipo, alvo, False))
        else:
            coletor.somar("PARTE_PERDIDA")
    propriedades = aplicativo = None
    do_pacote: list[tuple[str, str]] = []
    for rid, (tipo, alvo, externo) in sorted(rels_pacote.items(), key=ordem_do_rid):
        if tipo.endswith(_PACOTE_ESCRITAS):
            if tipo.endswith("/core-properties") and not externo and alvo in nomes:
                propriedades = _xml_valido(ler_parte(alvo), alvo, parse)
            elif tipo.endswith("/extended-properties") and not externo and alvo in nomes:
                aplicativo = _xml_valido(ler_parte(alvo), alvo, parse)
            continue
        if tipo.endswith("/thumbnail"):
            coletor.somar("MINIATURA")
            continue
        if "digital-signature" in tipo:
            coletor.somar("ASSINATURA")
            continue
        if externo:
            do_pacote.append((tipo, alvo, True))
        elif fecho.fechar(alvo):
            do_pacote.append((tipo, alvo, False))
        else:
            coletor.somar("PARTE_PERDIDA")
    return PacoteOriginal(configuracoes=configuracoes, relacoes_configuracoes=rels_config,
                          propriedades=propriedades, aplicativo=aplicativo,
                          do_documento=tuple(do_documento), do_pacote=tuple(do_pacote),
                          partes=tuple(fecho.partes[n] for n in sorted(fecho.partes)))


def _xml_valido(dados: bytes, nome: str, parse) -> bytes | None:
    try:
        parse(dados, nome)
    except Exception:  # noqa: BLE001 - a parte ilegivel e' gerada de novo pelo escritor
        return None
    return dados


def _notas(tipo, alvo, sufixo, fecho, coletor, ler_parte, relacoes_de, tipo_de, parse) -> bool:
    """Notas de rodape ou de fim: voltam as separadoras. True se a parte volta."""
    if alvo not in fecho.nomes or not tipo_de(alvo):
        coletor.somar("PARTE_PERDIDA")
        return False
    dados = ler_parte(alvo)
    try:
        raiz = parse(dados, alvo)
    except Exception:  # noqa: BLE001
        coletor.somar("PARTE_PERDIDA")
        return False
    filtrado, reais = _notas_separadoras(dados, raiz, _NOTAS[sufixo])
    if reais and coletor.contagem("NOTA") == 0:
        coletor.somar("NOTA", reais)
    usados = set(referencias(etree.fromstring(filtrado, parser_seguro())))
    relacoes = [(rid, t, a, e) for rid, (t, a, e) in sorted(relacoes_de(alvo).items()) if rid in usados]
    if usados - {r[0] for r in relacoes}:
        coletor.somar("PARTE_PERDIDA")
        return False
    parte = ParteOpaca(nome=alvo, tipo_conteudo=tipo_de(alvo), dados=filtrado,
                       relacoes=tuple(relacoes))
    if not fecho.acrescentar(parte, [a for _r, _t, a, e in relacoes if not e]):
        coletor.somar("PARTE_PERDIDA")
        return False
    return True


# -- escrita -------------------------------------------------------------------------

class GravadorPacote:
    """Nomes, relacoes, tipos e bytes das partes preservadas de um documento."""

    def __init__(self, pacote: PacoteOriginal | None, usados: set[str], rels_xml,
                 caminho_dos_rels) -> None:
        self.pacote = pacote
        self._rels_xml = rels_xml
        self._caminho_dos_rels = caminho_dos_rels
        #: nome de origem -> nome no arquivo gravado
        self.nomes: dict[str, str] = {}
        if pacote is None:
            return
        tomados = {u.lower() for u in usados}
        for parte in pacote.partes:
            nome = parte.nome
            candidato = nome
            raiz, extensao = posixpath.splitext(nome)
            k = 2
            while candidato.lower() in tomados or _NOMES_DO_ESCRITOR.fullmatch(candidato):
                candidato = f"{raiz}_{k}{extensao}"
                k += 1
            tomados.add(candidato.lower())
            usados.add(candidato)
            self.nomes[nome] = candidato

    def tem_relacao(self, sufixo: str) -> bool:
        return self.pacote is not None and any(
            _sufixo(t) == sufixo for t, _a, _e in self.pacote.do_documento)

    def relacoes_do_documento(self) -> list[tuple[str, str, bool]]:
        """(tipo, alvo relativo a word/, externo) para o document.xml.rels."""
        if self.pacote is None:
            return []
        return [(t, a if e else relativo(self.nomes[a], "word"), e)
                for t, a, e in self.pacote.do_documento]

    def relacoes_do_pacote(self) -> list[tuple[str, str, bool]]:
        if self.pacote is None:
            return []
        return [(t, a if e else self.nomes[a], e) for t, a, e in self.pacote.do_pacote]

    def relacoes_das_configuracoes(self) -> list[tuple]:
        if self.pacote is None or self.pacote.configuracoes is None:
            return []
        itens = []
        for rid, tipo, alvo, externo in self.pacote.relacoes_configuracoes:
            if externo:
                itens.append((rid, tipo, alvo, "External"))
            else:
                itens.append((rid, tipo, relativo(self.nomes[alvo], "word")))
        return itens

    def partes(self) -> list[tuple[str, bytes]]:
        if self.pacote is None:
            return []
        saida = []
        for parte in self.pacote.partes:
            novo = self.nomes[parte.nome]
            saida.append((novo, parte.dados))
            itens = []
            for rid, tipo, alvo, externo in parte.relacoes:
                if externo:
                    itens.append((rid, tipo, alvo, "External"))
                else:
                    itens.append((rid, tipo, relativo(self.nomes[alvo], posixpath.dirname(novo))))
            if itens:
                saida.append((self._caminho_dos_rels(novo), self._rels_xml(itens)))
        return saida

    def tipos(self) -> list[tuple[str, str]]:
        if self.pacote is None:
            return []
        return [("/" + self.nomes[p.nome], p.tipo_conteudo) for p in self.pacote.partes]

    # -- partes reescritas -------------------------------------------------------------

    def configuracoes(self, pares_impares: bool, notas: dict | None = None,
                      controlar: bool | None = None) -> bytes | None:
        """O settings.xml original com o que o EditDoc controla. None = gerar um novo.

        `controlar` (0.1.13): o w:trackRevisions (Revisao > Controlar alteracoes); None = como
        veio.

        `notas` (0.1.10): sufixo ("footnotes", "endnotes") -> ids das especiais que a parte
        gravada pelo escritor tem. O footnotePr cita as especiais que existem; a parte que nao
        volta (nem pelo escritor nem preservada) nao e' citada."""
        if self.pacote is None or self.pacote.configuracoes is None:
            return None
        dados = self.pacote.configuracoes
        raiz = etree.fromstring(dados, parser_seguro())
        mudou = False
        atual = raiz.find(q("evenAndOddHeaders"))
        ligado = atual is not None and (atual.get(q("val")) or "1").lower() not in ("0", "false", "off")
        if ligado != bool(pares_impares):
            mudou = True
            if atual is not None:
                raiz.remove(atual)
            if pares_impares:
                _inserir_em_ordem(raiz, etree.Element(q("evenAndOddHeaders")))
        if controlar is not None:
            atual = raiz.find(q("trackRevisions"))
            ligado = atual is not None and (atual.get(q("val")) or "1").lower() not in (
                "0", "false", "off")
            if ligado != bool(controlar):
                mudou = True
                if atual is not None:
                    raiz.remove(atual)
                if controlar:
                    _inserir_em_ordem(raiz, etree.Element(q("trackRevisions")))
        notas = notas or {}
        for sufixo, local in _NOTAS.items():
            if sufixo in notas:
                # Parte gravada pelo escritor (0.1.10): cita as especiais dela (separator e
                # continuationSeparator), na ordem do esquema.
                if _citar_especiais(raiz, local, notas[sufixo]):
                    mudou = True
                continue
            if self.tem_relacao(sufixo):
                continue
            # Notas que nao voltam: o settings.xml nao pode citar a separadora delas.
            pr = raiz.find(q(local + "Pr"))
            if pr is not None:
                for nota in pr.findall(q(local)):
                    pr.remove(nota)
                    mudou = True
        return _xml(raiz) if mudou else dados

    def propriedades(self, titulo: str, autor: str, criado: str, modificado: str) -> bytes | None:
        """O core.xml original com titulo, autor e datas do documento. None = gerar."""
        if self.pacote is None or self.pacote.propriedades is None:
            return None
        raiz = etree.fromstring(self.pacote.propriedades, parser_seguro())
        if raiz.tag != "{%s}coreProperties" % CP:
            return None
        for ns, local, valor in ((DC, "title", titulo), (DC, "creator", autor)):
            el = raiz.find("{%s}%s" % (ns, local))
            if el is None and valor:
                etree.SubElement(raiz, "{%s}%s" % (ns, local)).text = valor
            elif el is not None and (el.text or "") != valor:
                el.text = valor
        for local, valor in (("created", criado), ("modified", modificado)):
            el = raiz.find("{%s}%s" % (DCT, local))
            if el is None:
                el = etree.SubElement(raiz, "{%s}%s" % (DCT, local))
                el.set("{%s}type" % XSI, "dcterms:W3CDTF")
            el.text = valor
        return _xml(raiz)

    def aplicativo(self) -> bytes | None:
        """O app.xml original, com o EditDoc como aplicativo. None = gerar."""
        if self.pacote is None or self.pacote.aplicativo is None:
            return None
        raiz = etree.fromstring(self.pacote.aplicativo, parser_seguro())
        if raiz.tag != "{%s}Properties" % EP:
            return None
        app = raiz.find("{%s}Application" % EP)
        if app is None:
            app = etree.SubElement(raiz, "{%s}Application" % EP)
        app.text = "EditDoc"
        versao = raiz.find("{%s}AppVersion" % EP)
        if versao is not None:
            raiz.remove(versao)  # a versao era a do programa de origem
        return _xml(raiz)


def _citar_especiais(raiz, local: str, ids) -> bool:
    """O w:footnotePr do settings.xml cita exatamente as especiais `ids` (as que existem), na
    ordem: as citadas que existem ficam como estao; a que falta citar entra no fim. True se
    mudou."""
    ids = [str(int(i)) for i in ids]
    pr = raiz.find(q(local + "Pr"))
    citadas = [el.get(q("id")) for el in pr.findall(q(local))] if pr is not None else []
    if citadas == ids or (not ids and not citadas):
        return False
    if pr is None:
        pr = etree.Element(q(local + "Pr"))
        _inserir_em_ordem(raiz, pr)
    for el in pr.findall(q(local)):
        if el.get(q("id")) not in ids:
            pr.remove(el)
    presentes = [el.get(q("id")) for el in pr.findall(q(local))]
    for ident in ids:
        if ident not in presentes:
            etree.SubElement(pr, q(local)).set(q("id"), ident)
    return True


def _inserir_em_ordem(raiz, novo) -> None:
    """Poe `novo` entre os filhos de w:settings na ordem do esquema."""
    meu = _INDICE_SETTINGS[etree.QName(novo).localname]
    for i, filho in enumerate(raiz):
        if not isinstance(filho.tag, str):
            continue
        qn = etree.QName(filho)
        indice = _INDICE_SETTINGS.get(qn.localname) if qn.namespace in (W, None) or \
            qn.localname in ("mathPr", "schemaLibrary") else None
        if indice is None or indice > meu:
            raiz.insert(i, novo)
            return
    raiz.append(novo)


def assinatura(pacote: PacoteOriginal | None) -> tuple:
    """O que a conferencia compara: o conteudo das partes preservadas, sem os nomes."""
    if pacote is None:
        return (), ()
    partes = sorted((p.tipo_conteudo, hashlib.sha256(p.dados).hexdigest()[:24],
                     len(p.relacoes)) for p in pacote.partes)
    relacoes = sorted((t, e) for t, _a, e in (*pacote.do_documento, *pacote.do_pacote))
    return tuple(partes), tuple(relacoes)

