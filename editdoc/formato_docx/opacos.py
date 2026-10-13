"""Objetos opacos (0.1.2): o que o EditDoc nao edita, mas preserva. Sem Qt.

Caixa de texto, forma, grupo, tela de desenho, grafico, SmartArt, objeto OLE, tinta,
imagem flutuante ou em formato que a tela nao mostra (EMF, WMF, SVG, VML, vinculada) e
equacao. Antes da 0.1.2 tudo isso saia do arquivo ao salvar.

Leitura (`Capturador`): o XML do objeto e' guardado como veio (um w:r so' com o rPr e o
objeto, ou o m:oMath), com as declaracoes de namespace da raiz, mais o fecho das partes
que ele usa (imagens de dentro da forma, grafico e planilha, partes do SmartArt,
embeddings), cada uma com as suas relacoes e o seu tipo de conteudo. Referencia quebrada,
parte proibida ou limite estourado: o objeto nao e' preservado (aviso com perda).

Mudancas no XML guardado, com aviso: referencia a nota de rodape, nota de fim e
comentario dentro da caixa sai (essas partes nao voltam ao arquivo: a referencia ficaria
pendurada). Desde a 0.1.4 o `w:numPr` dentro da caixa fica, porque o numbering.xml de
origem volta inteiro; so' sai (aviso LISTA_EM_CAIXA) quando o arquivo nao tem numeracao
que possa ser lida.

Escrita (`GravadorOpacos`): o XML volta igual, com os rIds da parte hospedeira
renumerados. Cada parte ganha um nome livre (o de origem, se ninguem usa), as relacoes
dela (alvo recalculado, Id mantido: o XML da parte nao muda) e um Override proprio. Parte
sem relacoes e de mesmo conteudo e' gravada uma vez so'. Id repetido entre objetos
(wp:docPr, w14:paraId, anchorId) e' trocado no objeto que chega depois; dentro de um
mesmo objeto o Choice e o Fallback repetem o mesmo id de proposito, e ficam iguais.

`assinatura` e' o que a conferencia compara: o XML com os rIds trocados pelo conteudo
que eles apontam, sem depender dos nomes nem dos ids renumerados.
"""

from __future__ import annotations

import copy
import hashlib
import posixpath
import re

from lxml import etree

from editdoc.formato_docx.nomes import (A_NS, CT_DIAGRAMA_DADOS, DSP_NS, MATH_NS, MC_NS, O_NS,
                                        PIC_NS, R_NS, URI_DIAGRAMA, URI_GRAFICO, V_NS, W, W14_NS,
                                        WP14_NS, WP_NS, WPC_NS, WPG_NS, WPI_NS, WPS_NS, q)
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.documento import ObjetoOpaco, ParteOpaca

LIMITES = {
    #: objetos opacos por documento (corpo, cabecalhos e rodapes)
    "opacos": 2000,
    #: XML de um objeto (a caixa de texto com o texto dentro)
    "opaco_bytes": 4 * 1024 * 1024,
    #: XML de todos os objetos somados
    "opacos_bytes": 64 * 1024 * 1024,
    #: partes no fecho de um objeto (grafico + planilha + estilos + imagens...)
    "opaco_partes": 64,
    #: niveis de relacao a partir do objeto (documento -> grafico -> planilha = 2)
    "opaco_niveis": 6,
}

#: Itens de w:r que viram objeto opaco.
ITENS_DE_RUN = (q("drawing"), q("pict"), q("object"))
#: Itens de paragrafo que viram objeto opaco.
ITENS_DE_PARAGRAFO = ("{%s}oMath" % MATH_NS, "{%s}oMathPara" % MATH_NS)
_AC = "{%s}AlternateContent" % MC_NS
_CHOICE = "{%s}Choice" % MC_NS
_RELID_O = "{%s}relid" % O_NS
_PREFIXO_R = "{%s}" % R_NS
#: Referencias a partes que nao voltam ao arquivo: saem de dentro do objeto, com aviso.
_REFERENCIAS_SOLTAS = {q("footnoteReference"): "NOTA", q("endnoteReference"): "NOTA",
                       q("commentReference"): "COMENTARIO", q("commentRangeStart"): None,
                       q("commentRangeEnd"): None}
#: Tipos de conteudo que um objeto nunca leva junto (partes que o EditDoc escreve, ou
#: que pertencem ao documento inteiro).
_CT_PROIBIDOS = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "application/vnd.ms-word.document.macroEnabled.main+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.webSettings+xml",
    "application/vnd.openxmlformats-officedocument.theme+xml",
    "application/vnd.openxmlformats-package.core-properties+xml",
    "application/vnd.openxmlformats-officedocument.extended-properties+xml",
    "application/vnd.openxmlformats-officedocument.custom-properties+xml",
    "application/vnd.openxmlformats-package.relationships+xml",
    "application/vnd.ms-office.vbaProject",
    # Controles ActiveX (0.1.3): rodam codigo no Word; o objeto que os usa nao e' preservado.
    "application/vnd.ms-office.activeX+xml",
    "application/vnd.ms-office.activeX",
}
#: Nomes que o escritor usa (ou pode usar) para as partes dele.
_NOMES_DO_ESCRITOR = re.compile(
    r"(\[Content_Types\]\.xml|_rels/.*|.*\.rels|word/(document|styles|numbering|settings)\.xml"
    r"|word/(header|footer)\d+\.xml|word/theme/theme1\.xml|docProps/.*)", re.IGNORECASE)
_MEDIDA_VML = re.compile(r"(?:^|;)\s*(width|height)\s*:\s*([0-9.]+)\s*(pt|in|cm|mm|px)?", re.I)
_EMU_POR_UNIDADE = {"pt": 12700, "in": 914400, "cm": 360000, "mm": 36000, "px": 9525, None: 9525}
_EMU_MAXIMO = 176 * 360000  # o maior papel (176 cm), como no leitor
_RESUMO_MAXIMO = 80


def parser_seguro() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                           huge_tree=False, remove_blank_text=False)


def _local(el) -> tuple[str, str]:
    if not isinstance(el.tag, str):
        return "", ""
    qn = etree.QName(el)
    return qn.namespace or "", qn.localname


def contem_objeto(el) -> bool:
    """mc:AlternateContent de run que tem desenho, VML ou OLE em algum ramo."""
    return any(x.tag in ITENS_DE_RUN for x in el.iter())


def _ramo_principal(item):
    """No AlternateContent, o Choice (o que o Word mostra); fora dele, o proprio item."""
    if item.tag == _AC:
        escolha = next((x for x in item if x.tag == _CHOICE and len(x)), None)
        if escolha is not None:
            return escolha
    return item


# -- classificacao e medidas ---------------------------------------------------------

def classificar(item) -> str:
    """Tipo do objeto (chave de ROTULOS_OPACOS), pelo ramo que o Word mostra."""
    if item.tag in ITENS_DE_PARAGRAFO:
        return "equacao"
    base = _ramo_principal(item)
    locais: set[tuple[str, str]] = set()
    uris: set[str] = set()
    for x in base.iter():
        ns, loc = _local(x)
        if not loc:
            continue
        locais.add((ns, loc))
        if loc == "graphicData":
            uris.add(x.get("uri") or "")
    nomes = {loc for _ns, loc in locais}
    espacos = {ns for ns, _loc in locais}
    if "txbxContent" in nomes or (V_NS, "textbox") in locais:
        return "caixa_de_texto"
    if URI_GRAFICO in uris or any("chartex" in u.lower() for u in uris):
        return "grafico"
    if URI_DIAGRAMA in uris:
        return "smartart"
    if (O_NS, "OLEObject") in locais or base.tag == q("object") or (W, "object") in locais:
        return "objeto"
    if WPC_NS in espacos:
        return "desenho"
    if WPG_NS in espacos or (V_NS, "group") in locais:
        return "grupo"
    if WPI_NS in espacos or "contentPart" in nomes:
        return "tinta"
    if WPS_NS in espacos:
        return "forma"
    if (PIC_NS, "pic") in locais or (V_NS, "imagedata") in locais:
        return "imagem"
    if V_NS in espacos:
        return "forma"
    return "objeto"


def codigo_do_aviso(tipo: str, flutuante: bool) -> str:
    """Aviso (sem perda) de cada tipo de objeto preservado."""
    if tipo in ("caixa_de_texto", "forma", "grupo", "desenho"):
        return "CAIXA_DE_TEXTO"
    if tipo == "equacao":
        return "EQUACAO"
    if tipo == "imagem":
        return "IMAGEM_FLUTUANTE" if flutuante else "IMAGEM_FORMATO"
    return "OBJETO"


def resumo(item) -> str:
    """Inicio do texto da caixa (ou da equacao), para o marcador da tela."""
    base = _ramo_principal(item)
    if item.tag in ITENS_DE_PARAGRAFO:
        blocos = [base]
        marca = "{%s}t" % MATH_NS
    else:
        caixa = next(base.iter(q("txbxContent")), None)
        if caixa is None:
            return ""
        blocos = list(caixa.iter(q("p")))
        marca = q("t")
    partes: list[str] = []
    tamanho = 0
    for bloco in blocos:
        # Cada paragrafo da caixa separado por espaco; o texto de dentro, colado.
        texto = "".join(x.text or "" for x in bloco.iter(marca)
                        if x.getparent() is not None and (marca != q("t") or _paragrafo_de(x) is bloco))
        partes.append(texto)
        tamanho += len(texto)
        if tamanho > _RESUMO_MAXIMO * 2:
            break
    texto = " ".join(" ".join(partes).split())
    return texto if len(texto) <= _RESUMO_MAXIMO else texto[:_RESUMO_MAXIMO - 1] + "…"


def _paragrafo_de(el):
    """O w:p mais proximo acima de `el` (caixa dentro de caixa tem paragrafos aninhados)."""
    pai = el.getparent()
    while pai is not None and pai.tag != q("p"):
        pai = pai.getparent()
    return pai


def _emu(valor) -> int | None:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= _EMU_MAXIMO else None


def medidas(item) -> tuple[int | None, int | None, bool]:
    """(largura, altura em EMU, flutuante) do objeto, pelo DrawingML ou pelo estilo VML."""
    if item.tag in ITENS_DE_PARAGRAFO:
        return None, None, False
    base = _ramo_principal(item)
    for quadro in base.iter("{%s}inline" % WP_NS, "{%s}anchor" % WP_NS):
        extent = quadro.find("{%s}extent" % WP_NS)
        cx = _emu(extent.get("cx")) if extent is not None else None
        cy = _emu(extent.get("cy")) if extent is not None else None
        return cx, cy, quadro.tag == "{%s}anchor" % WP_NS
    for x in base.iter():
        ns, _loc = _local(x)
        estilo = x.get("style") if ns == V_NS else None
        if not estilo:
            continue
        valores = {}
        for nome, numero, unidade in _MEDIDA_VML.findall(estilo):
            try:
                valores[nome.lower()] = round(float(numero) * _EMU_POR_UNIDADE[
                    unidade.lower() if unidade else None])
            except (ValueError, KeyError):
                continue
        flutuante = "position:absolute" in estilo.replace(" ", "").lower()
        return (_emu(valores.get("width")), _emu(valores.get("height")), flutuante)
    return None, None, False


def referencias(el) -> list[str]:
    """rIds usados no XML, na ordem: atributos r:* e o:relid (VML)."""
    vistos: list[str] = []
    for x in el.iter():
        if not isinstance(x.tag, str):
            continue
        for chave, valor in x.attrib.items():
            if (chave.startswith(_PREFIXO_R) or chave == _RELID_O) and valor not in vistos:
                vistos.append(valor)
    return vistos


def _blips(item) -> list[str]:
    """rIds das imagens que a tela pode mostrar como previa (blip ou imagedata)."""
    base = _ramo_principal(item)
    saida = []
    for blip in base.iter("{%s}blip" % A_NS):
        rid = blip.get("{%s}embed" % R_NS)
        if rid:
            saida.append(rid)
    for dado in base.iter("{%s}imagedata" % V_NS):
        rid = dado.get("{%s}id" % R_NS) or dado.get(_RELID_O)
        if rid:
            saida.append(rid)
    return saida


# -- leitura -------------------------------------------------------------------------

class Capturador:
    """Transforma o item do arquivo em ObjetoOpaco, com o fecho das partes.

    `ler_parte(nome)` le com os limites do leitor; `relacoes_de(parte)` devolve
    rId -> (tipo, alvo resolvido, externo); `tipo_de(nome)` o tipo de conteudo (Override
    ou Default), ou None; `parse(dados, nome)` e' o parse seguro do leitor.
    """

    def __init__(self, lim: dict, coletor, nomes: set[str], ler_parte, relacoes_de, tipo_de,
                 parse, cache: dict) -> None:
        self.lim = {**LIMITES, **{k: v for k, v in lim.items() if k in LIMITES}}
        self.coletor = coletor
        self.nomes = nomes
        self.ler_parte = ler_parte
        self.relacoes_de = relacoes_de
        self.tipo_de = tipo_de
        self.parse = parse
        self.cache = cache  # nome -> bytes (o mesmo das imagens do leitor)
        self.contagem = 0
        self.bytes_total = 0
        self._rels: dict[str, dict] = {}
        #: numIds do numbering.xml lido (0.1.4); None = sem numeracao (o numPr da caixa sai)
        self.listas_validas: set | None = None

    def _relacoes(self, parte: str) -> dict:
        if parte not in self._rels:
            self._rels[parte] = self.relacoes_de(parte)
        return self._rels[parte]

    def _ler(self, nome: str) -> bytes:
        if nome not in self.cache:
            self.cache[nome] = self.ler_parte(nome)
        return self.cache[nome]

    def _fechar(self, nome: str, partes: dict, nivel: int) -> bool:
        """Poe `nome` e o que ele usa em `partes`. False se algo nao puder ir junto."""
        if nome in partes:
            return True
        if nivel > self.lim["opaco_niveis"] or len(partes) >= self.lim["opaco_partes"]:
            return False
        if nome not in self.nomes or _NOMES_DO_ESCRITOR.fullmatch(nome):
            return False
        tipo = self.tipo_de(nome)
        if not tipo or tipo in _CT_PROIBIDOS:
            return False
        partes[nome] = None  # marca: um ciclo de relacoes para aqui
        dados = self._ler(nome)
        relacoes = []
        for rid, (tipo_rel, alvo, externo) in sorted(self._relacoes(nome).items()):
            relacoes.append((rid, tipo_rel, alvo, externo))
            if not externo and not self._fechar(alvo, partes, nivel + 1):
                return False
        refs: tuple = ()
        if tipo == CT_DIAGRAMA_DADOS:
            raiz = self.parse(dados, nome)
            refs = tuple(dict.fromkeys(
                x.get("relId") for x in raiz.iter("{%s}dataModelExt" % DSP_NS) if x.get("relId")))
        partes[nome] = ParteOpaca(nome=nome, tipo_conteudo=tipo, dados=dados,
                                  relacoes=tuple(relacoes), refs_hospedeiro=refs)
        return True

    def capturar(self, item, rpr, relacoes_host: dict, ignoraveis: tuple) -> ObjetoOpaco | None:
        """O objeto preservado, ou None se ele nao puder voltar ao arquivo inteiro."""
        if self.contagem >= self.lim["opacos"]:
            return None
        if item.tag in ITENS_DE_PARAGRAFO:
            el = etree.fromstring(etree.tostring(item), parser_seguro())
        else:
            # Um w:r so' com o rPr e o objeto, com os namespaces em uso na raiz de origem
            # (o mc:Choice Requires="wps" precisa do prefixo, que nao e' usado em nome).
            el = etree.Element(q("r"), nsmap=item.nsmap)
            if rpr is not None:
                el.append(copy.deepcopy(rpr))
            el.append(copy.deepcopy(item))
        for x in list(el.iter(*_REFERENCIAS_SOLTAS)):
            codigo = _REFERENCIAS_SOLTAS[x.tag]
            if codigo:
                self.coletor.somar(codigo)
            x.getparent().remove(x)
        if self.listas_validas is None:
            # Sem numeracao lida (o arquivo nao tem, ou passou dos limites): o numId da caixa
            # apontaria para lista que nao volta ao arquivo. Desde a 0.1.4, com a numeracao
            # lida, o numPr fica (o numbering.xml de origem volta inteiro).
            listas = list(el.iter(q("numPr")))
            for x in listas:
                x.getparent().remove(x)
            if listas:
                self.coletor.somar("LISTA_EM_CAIXA", len(listas))
        xml = etree.tostring(el)
        if len(xml) > self.lim["opaco_bytes"] or \
                self.bytes_total + len(xml) > self.lim["opacos_bytes"]:
            return None
        partes: dict = {}
        relacoes: list[tuple] = []
        rids = referencias(el)
        for rid in rids:
            rel = relacoes_host.get(rid)
            if rel is None:
                return None
            tipo, alvo, externo = rel
            if not externo and not self._fechar(alvo, partes, 1):
                return None
            relacoes.append((rid, tipo, alvo, externo))
        # SmartArt: o desenho do diagrama e' relacao do documento, apontada de dentro da
        # parte de dados (dsp:dataModelExt relId), nao do XML do objeto.
        for parte in list(partes.values()):
            for rid in parte.refs_hospedeiro:
                rel = relacoes_host.get(rid)
                if rel is None or rid in rids:
                    continue
                tipo, alvo, externo = rel
                if not externo and not self._fechar(alvo, partes, 1):
                    return None
                rids.append(rid)
                relacoes.append((rid, tipo, alvo, externo))
        tipo_obj = classificar(item)
        largura, altura, flutuante = medidas(item)
        previa = None
        if tipo_obj == "imagem":
            for rid in _blips(item):
                rel = relacoes_host.get(rid)
                parte = partes.get(rel[1]) if rel is not None and not rel[2] else None
                if parte is not None and mod_imagem.formato_de(parte.dados):
                    dims = mod_imagem.dimensoes(parte.dados)
                    if dims and dims[0] > 0 and dims[1] > 0 and mod_imagem.decodificavel(*dims):
                        previa = parte.dados
                        break
        self.contagem += 1
        self.bytes_total += len(xml)
        return ObjetoOpaco(xml=xml, tipo=tipo_obj, resumo=resumo(item), flutuante=flutuante,
                           largura_emu=largura, altura_emu=altura, relacoes=tuple(relacoes),
                           partes=tuple(partes[n] for n in sorted(partes)),
                           ignoraveis=tuple(ignoraveis), previa=previa)


def ignoraveis_da_raiz(raiz) -> tuple:
    """(prefixo, namespace) do mc:Ignorable da raiz, so' os prefixos declarados."""
    valor = raiz.get("{%s}Ignorable" % MC_NS) or ""
    mapa = raiz.nsmap
    return tuple((p, mapa[p]) for p in valor.split() if p in mapa and mapa[p])


# -- escrita -------------------------------------------------------------------------

#: Atributos de id que tem de ser unicos no documento: classe -> nomes de atributo.
_IDS = {
    "docPr": ("id",),  # so' no wp:docPr
    "paraId": ("{%s}paraId" % W14_NS,),
    "anchorId": ("{%s}anchorId" % WP14_NS, "{%s}anchorId" % W14_NS),
}
_DOCPR = "{%s}docPr" % WP_NS


def _ids_do_objeto(el) -> dict[str, list]:
    """classe -> [(elemento, atributo, valor)], na ordem do documento."""
    saida: dict[str, list] = {c: [] for c in _IDS}
    for x in el.iter():
        if not isinstance(x.tag, str):
            continue
        if x.tag == _DOCPR and x.get("id") is not None:
            saida["docPr"].append((x, "id", x.get("id")))
        for classe in ("paraId", "anchorId"):
            for atributo in _IDS[classe]:
                valor = x.get(atributo)
                if valor is not None:
                    saida[classe].append((x, atributo, valor))
    return saida


class GravadorOpacos:
    """Grava os objetos opacos de um documento: XML, partes, relacoes e tipos."""

    def __init__(self, usados: set[str], rels_xml, caminho_dos_rels) -> None:
        #: nomes de parte ja' tomados (compartilhado com as imagens do escritor)
        self.usados = usados
        self._rels_xml = rels_xml
        self._caminho_dos_rels = caminho_dos_rels
        self.partes: list[tuple[str, bytes]] = []
        self.tipos: list[tuple[str, str]] = []
        self._folhas: dict[tuple[str, str], str] = {}
        self._reservados: dict[str, set[str]] = {c: set() for c in _IDS}
        self._ids: dict[str, set[str]] = {c: set() for c in _IDS}
        self._proximo_docpr = 1
        self._proximo_hex = 0x10000001
        #: namespaces e prefixos ignoraveis que a raiz de cada parte precisa declarar
        self.espacos: dict[str, str] = {}
        self.ignoraveis: list[str] = []

    def preparar(self, objetos, nsmap_base: dict) -> None:
        """Antes de gravar: os ids que os objetos ja' usam e os namespaces da raiz."""
        for obj in objetos:
            el = etree.fromstring(obj.xml, parser_seguro())
            for classe, itens in _ids_do_objeto(el).items():
                self._reservados[classe].update(v for _x, _a, v in itens)
            # A raiz da parte declara os namespaces da raiz de origem (wps, wpg, v, o, w14...),
            # como o Word faz: o mc:Choice Requires="wps" acha o prefixo ja' na raiz.
            for prefixo, uri in el.nsmap.items():
                if prefixo and prefixo not in nsmap_base and self.espacos.get(prefixo, uri) == uri:
                    self.espacos[prefixo] = uri
            for prefixo, uri in obj.ignoraveis:
                if nsmap_base.get(prefixo, uri) != uri or self.espacos.get(prefixo, uri) != uri:
                    continue
                if prefixo not in nsmap_base:
                    self.espacos[prefixo] = uri
                if prefixo not in self.ignoraveis:
                    self.ignoraveis.append(prefixo)

    def id_de_desenho(self) -> int:
        """wp:docPr id para uma imagem do EditDoc, sem colidir com os dos objetos."""
        while (str(self._proximo_docpr) in self._reservados["docPr"]
               or str(self._proximo_docpr) in self._ids["docPr"]):
            self._proximo_docpr += 1
        n = self._proximo_docpr
        self._ids["docPr"].add(str(n))
        self._proximo_docpr += 1
        return n

    def _id_novo(self, classe: str) -> str:
        if classe == "docPr":
            return str(self.id_de_desenho())
        while True:
            valor = f"{self._proximo_hex:08X}"
            self._proximo_hex += 1
            if valor not in self._reservados[classe] and valor not in self._ids[classe]:
                self._ids[classe].add(valor)
                return valor

    def _ids_unicos(self, el) -> None:
        for classe, itens in _ids_do_objeto(el).items():
            proprios = {v for _x, _a, v in itens}
            trocar = {v: self._id_novo(classe) for v in sorted(proprios) if v in self._ids[classe]}
            for x, atributo, valor in itens:
                if valor in trocar:
                    x.set(atributo, trocar[valor])
            self._ids[classe].update(trocar.get(v, v) for v in proprios)

    def _nome_livre(self, nome: str) -> str:
        if _NOMES_DO_ESCRITOR.fullmatch(nome) or not nome:
            nome = "word/objetos/" + (posixpath.basename(nome) or "parte")
        candidato = nome
        raiz, extensao = posixpath.splitext(nome)
        k = 2
        tomados = {u.lower() for u in self.usados}
        while candidato.lower() in tomados:
            candidato = f"{raiz}_{k}{extensao}"
            k += 1
        self.usados.add(candidato)
        return candidato

    def _alocar(self, nome: str, partes: dict, memo: dict, pendentes: list) -> str:
        if nome in memo:
            return memo[nome]
        parte = partes[nome]
        folha = not parte.relacoes and not parte.refs_hospedeiro
        chave = (parte.tipo_conteudo, hashlib.sha256(parte.dados).hexdigest())
        if folha and chave in self._folhas:
            memo[nome] = self._folhas[chave]
            return memo[nome]
        novo = self._nome_livre(nome)
        memo[nome] = novo
        if folha:
            self._folhas[chave] = novo
        pendentes.append((nome, novo))
        for _rid, _tipo, alvo, externo in parte.relacoes:
            if not externo:
                self._alocar(alvo, partes, memo, pendentes)
        return novo

    def escrever(self, obj: ObjetoOpaco, adicionar_relacao, pasta_host: str = "word"):
        """O elemento do objeto (w:r, m:oMath ou m:oMathPara), pronto para o paragrafo.

        `adicionar_relacao(tipo, alvo, externo)` devolve o rId na parte hospedeira.
        """
        el = etree.fromstring(obj.xml, parser_seguro())
        partes = {p.nome: p for p in obj.partes}
        memo: dict[str, str] = {}
        pendentes: list[tuple[str, str]] = []
        mapa: dict[str, str] = {}
        for rid, tipo, alvo, externo in obj.relacoes:
            if externo:
                mapa[rid] = adicionar_relacao(tipo, alvo, True)
            else:
                novo = self._alocar(alvo, partes, memo, pendentes)
                mapa[rid] = adicionar_relacao(tipo, relativo(novo, pasta_host), False)
        for x in el.iter():
            if not isinstance(x.tag, str):
                continue
            for chave, valor in list(x.attrib.items()):
                if (chave.startswith(_PREFIXO_R) or chave == _RELID_O) and valor in mapa:
                    x.set(chave, mapa[valor])
        self._ids_unicos(el)
        self._gravar_pendentes(pendentes, partes, memo, mapa)
        return el

    def _gravar_pendentes(self, pendentes, partes, memo, mapa) -> None:
        for origem, novo in pendentes:
            parte = partes[origem]
            dados = parte.dados
            if parte.refs_hospedeiro:
                dados = _trocar_relid(dados, mapa)
            itens = []
            for rid, tipo, alvo, externo in parte.relacoes:
                if externo:
                    itens.append((rid, tipo, alvo, "External"))
                else:
                    itens.append((rid, tipo, relativo(memo[alvo], posixpath.dirname(novo))))
            self.partes.append((novo, dados))
            if itens:
                self.partes.append((self._caminho_dos_rels(novo), self._rels_xml(itens)))
            self.tipos.append(("/" + novo, parte.tipo_conteudo))

    def gravar_fecho(self, relacoes, partes_tuple, pasta_host: str = "word") -> list[tuple]:
        """As partes que uma parte do EditDoc cita (as imagens dos marcadores de figura do
        numbering.xml, 0.1.4), com o Id de origem mantido. Devolve os itens do .rels."""
        partes = {p.nome: p for p in partes_tuple}
        memo: dict[str, str] = {}
        pendentes: list[tuple[str, str]] = []
        itens = []
        for rid, tipo, alvo, externo in relacoes:
            if externo:
                itens.append((rid, tipo, alvo, "External"))
            elif alvo in partes:
                novo = self._alocar(alvo, partes, memo, pendentes)
                itens.append((rid, tipo, relativo(novo, pasta_host)))
        self._gravar_pendentes(pendentes, partes, memo, {})
        return itens


def relativo(alvo: str, pasta: str) -> str:
    """Caminho de `alvo` visto de `pasta`, os dois relativos a raiz do pacote.

    (posixpath.relpath passa pelo os.getcwd, que no Windows e' um caminho com barra
    invertida.)"""
    a = [x for x in alvo.split("/") if x]
    b = [x for x in pasta.split("/") if x]
    i = 0
    while i < min(len(a) - 1, len(b)) and a[i] == b[i]:
        i += 1
    return "/".join([".."] * (len(b) - i) + a[i:])


def _trocar_relid(dados: bytes, mapa: dict[str, str]) -> bytes:
    """A parte de dados do SmartArt com o relId do dataModelExt renumerado."""
    raiz = etree.fromstring(dados, parser_seguro())
    mudou = False
    for x in raiz.iter("{%s}dataModelExt" % DSP_NS):
        valor = x.get("relId")
        if valor in mapa and mapa[valor] != valor:
            x.set("relId", mapa[valor])
            mudou = True
    if not mudou:
        return dados
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)


# -- assinatura (conferencia) ----------------------------------------------------------

def _assinatura_parte(nome: str, partes: dict, pilha: frozenset, memo: dict) -> str:
    if nome in memo:
        return memo[nome]
    if nome in pilha:
        return "ciclo"
    parte = partes.get(nome)
    if parte is None:
        return "ausente"
    dados = parte.dados
    if parte.refs_hospedeiro:
        raiz = etree.fromstring(dados, parser_seguro())
        for x in raiz.iter("{%s}dataModelExt" % DSP_NS):
            if x.get("relId") is not None:
                x.set("relId", "")
        dados = etree.tostring(raiz, method="c14n")
    filhos = sorted((rid, tipo, alvo if externo else
                     _assinatura_parte(alvo, partes, pilha | {nome}, memo))
                    for rid, tipo, alvo, externo in parte.relacoes)
    h = hashlib.sha256()
    h.update(parte.tipo_conteudo.encode())
    h.update(hashlib.sha256(dados).digest())
    h.update(repr(filhos).encode())
    memo[nome] = h.hexdigest()[:32]
    return memo[nome]


def assinatura(obj: ObjetoOpaco) -> str:
    """O objeto sem os nomes de parte, os rIds e os ids renumerados: o que tem de voltar."""
    el = etree.fromstring(obj.xml, parser_seguro())
    partes = {p.nome: p for p in obj.partes}
    memo: dict[str, str] = {}
    destino = {}
    for rid, tipo, alvo, externo in obj.relacoes:
        destino[rid] = f"{tipo}|" + (f"externo:{alvo}" if externo else
                                    _assinatura_parte(alvo, partes, frozenset(), memo))
    for x in el.iter():
        if not isinstance(x.tag, str):
            continue
        for chave, valor in list(x.attrib.items()):
            if chave.startswith(_PREFIXO_R) or chave == _RELID_O:
                x.set(chave, destino.get(valor, "sem-relacao"))
    for itens in _ids_do_objeto(el).values():
        for x, atributo, _valor in itens:
            x.set(atributo, "id")
    h = hashlib.sha256(etree.tostring(el, method="c14n", exclusive=True))
    h.update(repr(sorted(set(destino.values()))).encode())
    return f"{obj.tipo}:{h.hexdigest()[:32]}"
