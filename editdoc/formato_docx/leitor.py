"""Bytes ou caminho de .docx -> (Documento, avisos). Sem Qt.

Ordem das defesas: entrada, formato antigo (OLE), pacote ZIP (contagem, nomes,
criptografia, metodo, tamanho declarado, razao de compressao, total), DOCTYPE
recusado antes do parse, codificacao UTF-8 so', lxml sem entidades externas, sem
rede, sem DTD e com profundidade limitada. Toda falha vira `ErroDocx` com codigo.

O que o programa nao modela NAO e' descartado em silencio: vira aviso (ver
`avisos.py`). Tabela simples vira paragrafos, com aviso; campos viram o texto que
o Word mostra; revisoes aceitas; exclusoes e controles de conteudo tem aviso.
"""

from __future__ import annotations

import io
import os
import posixpath
import re
import zipfile

from lxml import etree

from editdoc.formato_docx.avisos import Aviso, Coletor
from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.padroes import (FONTE_PADRAO, LINHA_PADRAO,
                                         TAMANHO_PADRAO_MEIO_PT)
from editdoc.formato_docx.nomes import (CP, CT_DOCUMENTO_MACRO, DC, DCT, MC_NS, PKG_CT,
                                        RT_STRICT, W, W_STRICT, q)
from editdoc.formato_docx.ordem import caminho_dos_rels
from editdoc.modelo.documento import Documento, Paragrafo, Run, normalizar
from editdoc.modelo.pagina import Pagina

LIMITES_PADRAO = {
    "entradas": 5000,
    "parte_bytes": 128 * 1024 * 1024,
    "total_bytes": 512 * 1024 * 1024,
    "razao_min_bytes": 10 * 1024 * 1024,  # so checa a razao acima deste tamanho
    "razao_max": 200,
    "profundidade": 256,
}

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_DOCTYPE = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY|ELEMENT|ATTLIST|NOTATION)", re.IGNORECASE)
_ENCODING = re.compile(rb"""encoding\s*=\s*["']([A-Za-z0-9._-]+)["']""")
_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_JC = {"left": "esquerda", "start": "esquerda", "center": "centro",
       "right": "direita", "end": "direita", "both": "justificado"}

#: Propriedades de paragrafo sem efeito visivel que o modelo nao usa: sao ignoradas.
_PPR_NEUTRAS = {"widowControl", "keepNext", "keepLines", "suppressAutoHyphens", "kinsoku",
                "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN",
                "adjustRightInd", "snapToGrid", "textAlignment", "outlineLvl", "divId",
                "cnfStyle", "contextualSpacing", "textboxTightWrap", "rPr", "pPrChange",
                "suppressLineNumbers"}
#: Propriedades de run sem efeito visivel que o modelo nao usa.
_RPR_NEUTRAS = {"bCs", "iCs", "szCs", "lang", "noProof", "kern", "snapToGrid",
                "eastAsianLayout", "rtl", "cs", "specVanish", "oMath", "webHidden", "em"}

_CONTEINERES_INLINE = {"hyperlink", "fldSimple", "smartTag", "customXml", "dir", "bdo",
                       "moveTo", "ins"}
_IGNORADOS_INLINE = {"pPr", "bookmarkStart", "bookmarkEnd", "proofErr", "permStart",
                     "permEnd", "commentRangeStart", "commentRangeEnd", "lastRenderedPageBreak"}
_IGNORADOS_BLOCO = {"sectPr", "bookmarkStart", "bookmarkEnd", "permStart", "permEnd",
                    "tblPr", "tblGrid", "sdtPr", "sdtEndPr", "tcPr", "trPr"}


def _local(el) -> tuple[str | None, str | None]:
    """(namespace, nome local). None se for comentario ou instrucao de processamento."""
    t = el.tag
    if not isinstance(t, str):
        return None, None
    if t.startswith("{"):
        ns, _, loc = t[1:].partition("}")
        return ns, loc
    return "", t


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


def _validar_nome(nome: str) -> None:
    if (not nome or len(nome) > 512 or "\x00" in nome or "\\" in nome or ".." in nome
            or nome.startswith("/") or re.match(r"^[A-Za-z]:", nome)):
        raise ErroDocx("ZIP_NOME_INVALIDO", repr(nome)[:80])


def _parse(dados: bytes, nome: str, profundidade: int):
    if _DOCTYPE.search(dados):
        raise ErroDocx("XML_DOCTYPE_PROIBIDO", nome)
    if b"\x00" in dados[:4]:
        raise ErroDocx("XML_CODIFICACAO_NAO_SUPORTADA", f"{nome}: sem UTF-8")
    m = _ENCODING.search(dados[:200])
    if m and m.group(1).lower() not in (b"utf-8", b"utf8"):
        raise ErroDocx("XML_CODIFICACAO_NAO_SUPORTADA", f"{nome}: {m.group(1)!r}")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                             huge_tree=False)
    try:
        raiz = etree.fromstring(dados, parser)
    except (etree.LxmlError, ValueError) as erro:
        texto = str(erro).lower()
        if "depth" in texto or "profund" in texto:
            raise ErroDocx("XML_PROFUNDIDADE_EXCEDIDA", nome) from None
        raise ErroDocx("XML_MALFORMADO", f"{nome}") from None
    return raiz


class _Contexto:
    def __init__(self, coletor: Coletor, numeracao: dict[str, str | None]) -> None:
        self.coletor = coletor
        #: numId -> formato do nivel 0 ("bullet", "decimal", outro ou None)
        self.numeracao = numeracao
        #: sectPr contados: os de dentro de paragrafo mais o do fim do corpo
        self.secoes = 0
        #: pagina do sectPr final, ja validada; None se nao for representavel
        self.pagina_final: Pagina | None = None


# -- classificacao ------------------------------------------------------------

def _classificar_desenho(el) -> str:
    locais = {etree.QName(x).localname for x in el.iter() if isinstance(x.tag, str)}
    if "txbxContent" in locais:
        return "CAIXA_DE_TEXTO"
    if locais & {"blip", "imagedata", "pic", "chart"}:
        return "IMAGEM"
    if locais & {"wsp", "shape", "sp", "wgp", "grpSp"}:
        return "CAIXA_DE_TEXTO"
    return "OBJETO"


# -- propriedades -------------------------------------------------------------

def _ler_rpr(rpr, run: Run, ctx: _Contexto) -> None:
    c = ctx.coletor
    for f in rpr:
        ns, loc = _local(f)
        if ns != W or loc is None:
            continue
        if loc == "b":
            run.negrito = _onoff(f)
        elif loc == "i":
            run.italico = _onoff(f)
        elif loc == "u":
            v = _atr(f, "val")
            run.sublinhado = v != "none"
            if v not in (None, "single", "none"):
                c.somar("FORMATACAO")
        elif loc == "strike":
            run.tachado = _onoff(f)
        elif loc == "dstrike":
            run.tachado = _onoff(f)
            c.somar("FORMATACAO")
        elif loc == "vertAlign":
            v = _atr(f, "val")
            if v == "superscript":
                run.sobrescrito, run.subscrito = True, False
            elif v == "subscript":
                run.subscrito, run.sobrescrito = True, False
            elif v == "baseline":
                run.subscrito, run.sobrescrito = False, False
            else:
                c.somar("FORMATACAO")
        elif loc == "sz":
            run.tamanho_meio_pt = _inteiro(_atr(f, "val"))
        elif loc == "rFonts":
            fonte = _atr(f, "ascii") or _atr(f, "hAnsi")
            if fonte:
                run.fonte = fonte
        elif loc == "color":
            v = _atr(f, "val")
            if v and v.lower() != "auto":
                if _HEX6.fullmatch(v):
                    run.cor_hex = v.upper()
                else:
                    c.somar("FORMATACAO")
        elif loc == "rStyle":
            c.somar("ESTILO")
        elif loc in _RPR_NEUTRAS:
            continue
        else:
            c.somar("FORMATACAO")


def _ler_ppr(ppr, ctx: _Contexto) -> dict:
    c = ctx.coletor
    out: dict = {}
    for f in ppr:
        ns, loc = _local(f)
        if ns != W or loc is None:
            continue
        if loc == "jc":
            v = _atr(f, "val")
            if v in _JC:
                out["alinhamento"] = _JC[v]
            else:
                c.somar("FORMATACAO")
        elif loc == "ind":
            esq = _atr(f, "left") or _atr(f, "start")
            if esq is not None:
                out["recuo_esquerdo_tw"] = _inteiro(esq)
            if _atr(f, "firstLine") is not None:
                out["recuo_primeira_linha_tw"] = _inteiro(_atr(f, "firstLine"))
            elif _atr(f, "hanging") is not None:
                h = _inteiro(_atr(f, "hanging"))
                out["recuo_primeira_linha_tw"] = None if h is None else -h
            if _atr(f, "right") is not None or _atr(f, "end") is not None:
                c.somar("FORMATACAO")
        elif loc == "spacing":
            if _atr(f, "before") is not None:
                out["espaco_antes_tw"] = _inteiro(_atr(f, "before"))
            if _atr(f, "after") is not None:
                out["espaco_depois_tw"] = _inteiro(_atr(f, "after"))
            linha = _inteiro(_atr(f, "line"))
            if linha is not None:
                regra = _atr(f, "lineRule") or "auto"
                if regra == "auto":
                    out["espacamento_linha_pct"] = round(linha * 100 / 240)
                else:
                    c.somar("ESPACAMENTO_LINHA")
        elif loc == "numPr":
            _ler_numpr(f, out, ctx)
        elif loc == "pStyle":
            if _atr(f, "val") not in (None, "Normal"):
                c.somar("ESTILO")
        elif loc == "sectPr":
            c.somar("SECAO")
            ctx.secoes += 1
            _checar_secao(f, ctx)
        elif loc == "pageBreakBefore":
            out["quebra_antes"] = _onoff(f)
        elif loc in _PPR_NEUTRAS:
            continue
        else:
            c.somar("FORMATACAO")
    return out


def _escolha(alternativa):
    """Dentro de mc:AlternateContent, o ramo que o EditDoc entende: Choice ou Fallback."""
    for nome in ("Choice", "Fallback"):
        ramo = next((x for x in alternativa if _local(x) == (MC_NS, nome)), None)
        if ramo is not None:
            return ramo
    return None


def _ler_numpr(numpr, out: dict, ctx: _Contexto) -> None:
    c = ctx.coletor
    nid_el = numpr.find(q("numId"))
    nid = nid_el.get(q("val")) if nid_el is not None else None
    ilvl_el = numpr.find(q("ilvl"))
    ilvl = _inteiro(ilvl_el.get(q("val"))) if ilvl_el is not None else 0
    if nid in (None, "0"):
        return
    if ilvl and ilvl > 0:
        c.somar("LISTA_NIVEL")
    fmt = ctx.numeracao.get(nid)
    if fmt == "bullet":
        out["numeracao"] = "marcadores"
    else:
        out["numeracao"] = "numeracao"
        if fmt != "decimal":
            c.somar("LISTA")


def _ler_run(r, ctx: _Contexto, saida: list[Run]) -> None:
    c = ctx.coletor
    run = Run()
    partes: list[str] = []
    for f in r:
        ns, loc = _local(f)
        if loc is None:
            continue
        if ns == MC_NS and loc == "AlternateContent":
            ramo = _escolha(f)
            if ramo is not None:
                for sub in ramo:
                    _ler_item_run(sub, run, partes, ctx)
            continue
        if ns != W:
            continue
        _ler_item_run(f, run, partes, ctx)
    run.texto = "".join(partes)
    if run.texto:
        saida.append(run)


def _ler_item_run(f, run: Run, partes: list[str], ctx: _Contexto) -> None:
    c = ctx.coletor
    ns, loc = _local(f)
    if loc is None or ns != W:
        return
    if loc == "rPr":
        _ler_rpr(f, run, ctx)
    elif loc == "t":
        partes.append(f.text or "")
    elif loc == "delText":
        return
    elif loc == "tab":
        partes.append("\t")
    elif loc == "br":
        tipo = _atr(f, "type")
        if tipo in (None, "textWrapping"):
            partes.append("\n")
        elif tipo == "page":
            # Sentinela: _paragrafos transforma cada \f em quebra de pagina.
            # XML 1.0 nao aceita \f em w:t, entao ele so' vem daqui.
            partes.append("\f")
        else:
            c.somar("QUEBRA_DE_PAGINA")
    elif loc == "cr":
        partes.append("\n")
    elif loc == "noBreakHyphen":
        partes.append("-")
    elif loc == "softHyphen" or loc == "lastRenderedPageBreak":
        return
    elif loc == "fldChar":
        if _atr(f, "fldCharType") == "begin":
            c.somar("CAMPO")
    elif loc == "instrText" or loc == "fldData":
        return
    elif loc in ("drawing", "pict", "object"):
        c.somar(_classificar_desenho(f))
    elif loc == "commentReference":
        c.somar("COMENTARIO")
    elif loc in ("footnoteReference", "endnoteReference"):
        c.somar("NOTA")
    else:
        c.somar("ELEMENTO_DESCONHECIDO")


def _runs_em(elemento, ctx: _Contexto, saida: list[Run]) -> None:
    c = ctx.coletor
    for f in elemento:
        ns, loc = _local(f)
        if loc is None:
            continue
        if ns == MC_NS and loc == "AlternateContent":
            ramo = _escolha(f)
            if ramo is not None:
                _runs_em(ramo, ctx, saida)
            continue
        if ns != W:
            continue
        if loc == "r":
            _ler_run(f, ctx, saida)
        elif loc == "hyperlink":
            c.somar("HIPERLINK")
            _runs_em(f, ctx, saida)
        elif loc == "fldSimple":
            c.somar("CAMPO")
            _runs_em(f, ctx, saida)
        elif loc in ("ins", "moveTo"):
            c.somar("REVISAO")
            _runs_em(f, ctx, saida)
        elif loc in ("del", "moveFrom"):
            c.somar("REVISAO")
        elif loc == "sdt":
            c.somar("CONTEUDO_CONTROLADO")
            conteudo = f.find(q("sdtContent"))
            if conteudo is not None:
                _runs_em(conteudo, ctx, saida)
        elif loc in ("smartTag", "customXml", "dir", "bdo"):
            _runs_em(f, ctx, saida)
        elif loc in ("oMath", "oMathPara"):
            c.somar("EQUACAO")
        elif loc in _IGNORADOS_INLINE:
            continue
        else:
            c.somar("ELEMENTO_DESCONHECIDO")


def _paragrafos(p, ctx: _Contexto) -> list[Paragrafo]:
    """Um w:p vira um ou mais paragrafos do modelo.

    Quebra de pagina (w:br type="page") no inicio do paragrafo, ou paragrafo que
    contem so' a quebra, vira `quebra_antes` no proprio paragrafo. Quebra no meio
    do texto parte o paragrafo: a parte depois dela vira paragrafo novo, com as
    mesmas propriedades e `quebra_antes` ligado. O modelo nao diz "no meio": e'
    a unica mudanca de estrutura, e a aparencia nao muda.
    """
    props: dict = {}
    for f in p:
        ns, loc = _local(f)
        if ns == W and loc == "pPr":
            props = _ler_ppr(f, ctx)
    runs: list[Run] = []
    _runs_em(p, ctx, runs)
    saida = [Paragrafo(runs=[], **props)]
    for run in runs:
        for i, pedaco in enumerate(run.texto.split("\f")):
            if i > 0:
                atual = saida[-1]
                if atual.runs or atual.quebra_antes:
                    nova = Paragrafo(runs=[], **{k: v for k, v in props.items()
                                                 if k != "quebra_antes"})
                    nova.quebra_antes = True
                    saida.append(nova)
                else:
                    atual.quebra_antes = True
            if pedaco:
                saida[-1].runs.append(Run(**{**run.__dict__, "texto": pedaco}))
    return saida


def _blocos(elemento, paras: list[Paragrafo], ctx: _Contexto) -> None:
    c = ctx.coletor
    for f in elemento:
        ns, loc = _local(f)
        if loc is None:
            continue
        if ns == MC_NS and loc == "AlternateContent":
            ramo = _escolha(f)
            if ramo is not None:
                _blocos(ramo, paras, ctx)
            continue
        if ns != W:
            continue
        if loc == "p":
            paras.extend(_paragrafos(f, ctx))
        elif loc == "tbl":
            c.somar("TABELA")
            _blocos(f, paras, ctx)
        elif loc in ("tr", "tc", "customXml", "smartTag", "sdtContent", "ins"):
            _blocos(f, paras, ctx)
        elif loc == "sdt":
            c.somar("CONTEUDO_CONTROLADO")
            conteudo = f.find(q("sdtContent"))
            if conteudo is not None:
                _blocos(conteudo, paras, ctx)
        elif loc in ("del", "moveFrom"):
            c.somar("REVISAO")
        elif loc in _IGNORADOS_BLOCO:
            continue
        else:
            c.somar("ELEMENTO_DESCONHECIDO")


def _checar_secao(sect, ctx: _Contexto) -> None:
    """Cabecalho e rodape de uma secao (sectPr). Papel e margens: ver _pagina_de."""
    if any(_local(x)[1] in ("headerReference", "footerReference") for x in sect):
        ctx.coletor.somar("CABECALHO_RODAPE")


#: Atributos do w:pgMar e o campo de Pagina que cada um preenche.
_MARGENS_XML = (("top", "margem_sup_tw"), ("bottom", "margem_inf_tw"),
                ("left", "margem_esq_tw"), ("right", "margem_dir_tw"),
                ("header", "cabecalho_tw"), ("footer", "rodape_tw"),
                ("gutter", "medianiz_tw"))


def _pagina_de(sect) -> Pagina | None:
    """Papel, orientacao e margens do sectPr. None se nao houver pagina util."""
    pagina = Pagina()
    pg = sect.find(q("pgSz"))
    if pg is not None:
        largura, altura = _inteiro(_atr(pg, "w")), _inteiro(_atr(pg, "h"))
        if largura is None or altura is None:
            return None
        pagina.largura_tw, pagina.altura_tw = largura, altura
        pagina.paisagem = _atr(pg, "orient") == "landscape"
    mar = sect.find(q("pgMar"))
    if mar is not None:
        for nome_xml, campo in _MARGENS_XML:
            valor = _inteiro(_atr(mar, nome_xml))
            if valor is not None:
                setattr(pagina, campo, valor)
    return pagina if pagina.valida() else None


def _numeracao(raiz_num) -> dict[str, str | None]:
    formatos: dict[str, str | None] = {}
    for a in raiz_num.findall(q("abstractNum")):
        fmt = None
        for lvl in a.findall(q("lvl")):
            if lvl.get(q("ilvl")) == "0":
                nf = lvl.find(q("numFmt"))
                fmt = _atr(nf, "val") if nf is not None else None
                break
        formatos[a.get(q("abstractNumId")) or ""] = fmt
    saida: dict[str, str | None] = {}
    for n in raiz_num.findall(q("num")):
        ab = n.find(q("abstractNumId"))
        alvo = _atr(ab, "val") if ab is not None else None
        saida[n.get(q("numId")) or ""] = formatos.get(alvo or "")
    return saida


def _padrao_do_documento(raiz_estilos, coletor: Coletor) -> None:
    """Fonte e espacamento padrao diferentes do padrao do EditDoc: aviso."""
    dd = raiz_estilos.find(q("docDefaults"))
    if dd is None:
        return
    rpr = dd.find(q("rPrDefault") + "/" + q("rPr"))
    ppr = dd.find(q("pPrDefault") + "/" + q("pPr"))
    diferente = False
    if rpr is not None:
        sz = rpr.find(q("sz"))
        rf = rpr.find(q("rFonts"))
        if sz is not None and _atr(sz, "val") != str(TAMANHO_PADRAO_MEIO_PT):
            diferente = True
        if rf is not None and _atr(rf, "ascii") not in (None, FONTE_PADRAO):
            diferente = True
    if ppr is not None:
        sp = ppr.find(q("spacing"))
        if sp is not None:
            if _atr(sp, "after") is not None and _inteiro(_atr(sp, "after")) != 160:
                diferente = True
            if _atr(sp, "line") is not None and _inteiro(_atr(sp, "line")) != LINHA_PADRAO:
                diferente = True
    if diferente:
        coletor.somar("PADRAO_DO_DOCUMENTO")


def _core(dados: bytes, profundidade: int) -> dict:
    raiz = _parse(dados, "docProps/core.xml", profundidade)
    out = {"titulo": "", "autor": "", "criado_em": None, "modificado_em": None}
    mapa = {(DC, "title"): "titulo", (DC, "creator"): "autor",
            (DCT, "created"): "criado_em", (DCT, "modified"): "modificado_em"}
    for f in raiz:
        ns, loc = _local(f)
        chave = mapa.get((ns, loc))
        if chave:
            out[chave] = (f.text or "") if chave in ("titulo", "autor") else (f.text or None)
    return out


def _profundidade(raiz) -> int:
    """Maior profundidade da arvore. Iterativa, para nao estourar a pilha do Python."""
    maximo = 0
    pilha = [(raiz, 1)]
    while pilha:
        no, nivel = pilha.pop()
        maximo = max(maximo, nivel)
        for filho in no:
            pilha.append((filho, nivel + 1))
    return maximo


def _ler(dados: bytes, lim: dict) -> tuple[Documento, list[Aviso]]:
    if dados[:8] == _OLE:
        raise ErroDocx("FORMATO_DOC_ANTIGO")
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
    except (zipfile.BadZipFile, OSError, EOFError, ValueError):
        raise ErroDocx("ZIP_INVALIDO") from None
    coletor = Coletor()
    with z:
        infos = z.infolist()
        if len(infos) > lim["entradas"]:
            raise ErroDocx("ZIP_MUITAS_ENTRADAS", str(len(infos)))
        nomes: set[str] = set()
        brutos: set[str] = set()
        total_declarado = 0
        for info in infos:
            # No Windows o ZipInfo troca '\' por '/' em .filename: o nome bruto e' o que vale.
            bruto = info.orig_filename
            _validar_nome(bruto)
            _validar_nome(info.filename)
            nome = info.filename
            if bruto in brutos:
                raise ErroDocx("ZIP_NOME_DUPLICADO", bruto[:80])
            brutos.add(bruto)
            nomes.add(nome)
            if info.flag_bits & 0x1:
                raise ErroDocx("ZIP_CRIPTOGRAFADO", nome[:80])
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ErroDocx("ZIP_COMPRESSAO_NAO_SUPORTADA", nome[:60])
            if info.file_size > lim["parte_bytes"]:
                raise ErroDocx("ZIP_TAMANHO_EXCEDIDO", f"{nome[:60]} declarado={info.file_size}")
            if info.file_size >= lim["razao_min_bytes"] and (
                    info.compress_size == 0 or info.file_size / info.compress_size > lim["razao_max"]):
                raise ErroDocx("ZIP_RAZAO_ABSURDA", f"{nome[:60]}")
            total_declarado += info.file_size
            if total_declarado > lim["total_bytes"]:
                raise ErroDocx("ZIP_TOTAL_EXCEDIDO", str(total_declarado))

        consumido = 0

        def ler_parte(nome: str) -> bytes:
            nonlocal consumido
            if nome not in nomes:
                raise ErroDocx("ZIP_PARTE_AUSENTE", nome)
            with z.open(z.getinfo(nome)) as fh:
                conteudo = fh.read(lim["parte_bytes"] + 1)  # limite real, mesmo com cabecalho mentiroso
            if len(conteudo) > lim["parte_bytes"]:
                raise ErroDocx("ZIP_TAMANHO_EXCEDIDO", f"{nome} descompactado")
            consumido += len(conteudo)
            if consumido > lim["total_bytes"]:
                raise ErroDocx("ZIP_TOTAL_EXCEDIDO", "descompactado")
            return conteudo

        profundidade = lim["profundidade"]
        rels = _parse(ler_parte("_rels/.rels"), "_rels/.rels", profundidade)
        alvo_doc = alvo_core = None
        for rel in rels:
            tipo = rel.get("Type", "")
            alvo = rel.get("Target", "")
            alvo = alvo[1:] if alvo.startswith("/") else alvo
            if tipo.endswith("/officeDocument") or tipo.startswith(RT_STRICT):
                if tipo.startswith(RT_STRICT):
                    raise ErroDocx("FORMATO_STRICT")
                alvo_doc = alvo
            elif tipo.endswith("/core-properties"):
                alvo_core = alvo
        if not alvo_doc:
            raise ErroDocx("OPC_SEM_DOCUMENTO_PRINCIPAL")
        _validar_nome(alvo_doc)

        tipos_parte = {}
        if "[Content_Types].xml" in nomes:
            ct = _parse(ler_parte("[Content_Types].xml"), "[Content_Types].xml", profundidade)
            for o in ct.iter("{%s}Override" % PKG_CT):
                tipos_parte[(o.get("PartName") or "").lstrip("/")] = o.get("ContentType")
        if tipos_parte.get(alvo_doc) == CT_DOCUMENTO_MACRO:
            coletor.somar("MACROS")

        raiz = _parse(ler_parte(alvo_doc), alvo_doc, profundidade)
        if raiz.tag == q("document", W_STRICT):
            raise ErroDocx("FORMATO_STRICT")
        if _local(raiz) != (W, "document"):
            raise ErroDocx("XML_ESTRUTURA", "raiz do documento inesperada")
        if _profundidade(raiz) > profundidade:
            raise ErroDocx("XML_PROFUNDIDADE_EXCEDIDA", alvo_doc)
        corpo = raiz.find(q("body"))
        if corpo is None:
            raise ErroDocx("XML_ESTRUTURA", "w:body ausente")

        # Partes ligadas ao documento principal: numeracao e estilos.
        numeracao: dict[str, str | None] = {}
        estilos = None
        rels_doc = caminho_dos_rels(alvo_doc)
        if rels_doc in nomes:
            base = posixpath.dirname(alvo_doc)
            for rel in _parse(ler_parte(rels_doc), rels_doc, profundidade):
                tipo = rel.get("Type", "")
                alvo = posixpath.normpath(posixpath.join(base, rel.get("Target", "")))
                if tipo.endswith("/numbering") and alvo in nomes:
                    _validar_nome(alvo)
                    numeracao = _numeracao(_parse(ler_parte(alvo), alvo, profundidade))
                elif tipo.endswith("/styles") and alvo in nomes:
                    _validar_nome(alvo)
                    estilos = _parse(ler_parte(alvo), alvo, profundidade)

        ctx = _Contexto(coletor, numeracao)
        if estilos is not None:
            _padrao_do_documento(estilos, coletor)

        paras: list[Paragrafo] = []
        _blocos(corpo, paras, ctx)
        sect_final = corpo.find(q("sectPr"))
        if sect_final is not None:
            _checar_secao(sect_final, ctx)
            ctx.pagina_final = _pagina_de(sect_final)
            if ctx.pagina_final is None:
                # Papel ou margem que nao cabe numa pagina util: o EditDoc
                # grava A4 com as margens padrao, e o aviso diz isso.
                coletor.somar("PAPEL_INVALIDO")
        total_secoes = ctx.secoes + (1 if sect_final is not None else 0)
        if total_secoes > 1:
            # Cada secao tem o seu papel e as suas margens; o EditDoc tem um so'.
            coletor.somar("PAGINA")

        meta = {"titulo": "", "autor": "", "criado_em": None, "modificado_em": None}
        if alvo_core and alvo_core in nomes:
            _validar_nome(alvo_core)
            meta = _core(ler_parte(alvo_core), profundidade)

    pagina = ctx.pagina_final if ctx.pagina_final is not None else Pagina()
    doc = normalizar(Documento(paragrafos=paras, pagina=pagina, **meta))
    return doc, coletor.avisos()


def _bytes_de(origem) -> bytes:
    if isinstance(origem, (bytes, bytearray, memoryview)):
        return bytes(origem)
    if isinstance(origem, (str, os.PathLike)):
        try:
            with open(origem, "rb") as fh:
                return fh.read()
        except OSError:
            raise ErroDocx("ARQUIVO_ILEGIVEL") from None
    raise ErroDocx("ENTRADA_INVALIDA", type(origem).__name__)


def ler(origem, limites: dict | None = None) -> tuple[Documento, list[Aviso]]:
    """Le um .docx de bytes ou de caminho. Devolve (Documento, avisos).

    Qualquer falha levanta `ErroDocx`, com codigo. Nenhuma outra excecao sai daqui.
    """
    lim = {**LIMITES_PADRAO, **(limites or {})}
    try:
        return _ler(_bytes_de(origem), lim)
    except ErroDocx:
        raise
    except Exception:  # fronteira: quem chama nunca ve traceback
        raise ErroDocx("ERRO_INTERNO") from None
