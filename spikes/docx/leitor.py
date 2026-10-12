"""Leitor OOXML proprio do spike B: bytes de .docx -> Documento, com limites de seguranca.

Defesas, em ordem: limites de ZIP (entradas, tamanho declarado, razao de compressao,
total), nomes de entrada, metodo de compressao, bytes de DOCTYPE/ENTITY recusados antes
do parse, codificacao so UTF-8, lxml sem entidades externas, sem rede, sem DTD, sem
arvore enorme. Qualquer falha vira ErroDocx com .codigo; nada de traceback para quem chama.
"""
from __future__ import annotations

import io
import re
import zipfile

from lxml import etree

from modelo import Documento, Paragrafo, Run

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DC = "http://purl.org/dc/elements/1.1/"
DCT = "http://purl.org/dc/terms/"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

LIMITES_PADRAO = {
    "entradas": 5000,
    "parte_bytes": 128 * 1024 * 1024,
    "total_bytes": 512 * 1024 * 1024,
    "razao_min_bytes": 10 * 1024 * 1024,  # so checa razao acima deste tamanho
    "razao_max": 200,
}

_DOCTYPE = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY|ELEMENT|ATTLIST|NOTATION)", re.IGNORECASE)
_ENCODING = re.compile(rb"""encoding\s*=\s*["']([A-Za-z0-9._-]+)["']""")
_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_JC_LER = {"left": "esquerda", "start": "esquerda", "center": "centro",
           "right": "direita", "end": "direita", "both": "justificado"}
_FORMATO_PPR_OK = {"rPr", "sectPr", "pPrChange"}


class ErroDocx(Exception):
    def __init__(self, codigo: str, mensagem: str = ""):
        self.codigo = codigo
        self.mensagem = mensagem
        super().__init__(f"{codigo}: {mensagem}" if mensagem else codigo)


def _local(el) -> tuple[str | None, str | None]:
    t = el.tag
    if not isinstance(t, str):
        return None, None
    if t.startswith("{"):
        ns, _, loc = t[1:].partition("}")
        return ns, loc
    return "", t


def _a(el, ns: str, nome: str) -> str | None:
    return el.get("{%s}%s" % (ns, nome))


def _validar_nome(nome: str) -> None:
    if (not nome or len(nome) > 512 or "\x00" in nome or "\\" in nome or ".." in nome
            or nome.startswith("/") or re.match(r"^[A-Za-z]:", nome)):
        raise ErroDocx("ZIP_NOME_INVALIDO", repr(nome)[:80])


def _parse(dados: bytes, nome: str):
    if _DOCTYPE.search(dados):
        raise ErroDocx("XML_DOCTYPE_PROIBIDO", nome)
    if b"\x00" in dados[:4]:
        raise ErroDocx("XML_CODIFICACAO_NAO_SUPORTADA", f"{nome}: sem UTF-8 (NUL no inicio)")
    m = _ENCODING.search(dados[:200])
    if m and m.group(1).lower() not in (b"utf-8", b"utf8"):
        raise ErroDocx("XML_CODIFICACAO_NAO_SUPORTADA", f"{nome}: {m.group(1)!r}")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                             huge_tree=False)
    try:
        return etree.fromstring(dados, parser)
    except (etree.LxmlError, ValueError) as e:
        raise ErroDocx("XML_MALFORMADO", f"{nome}: {str(e)[:160]}") from None


def _onoff(el) -> bool:
    v = el.get(_a_name("val"))
    return v is None or v.lower() not in ("0", "false", "off")


def _a_name(nome: str) -> str:
    return "{%s}%s" % (W, nome)


def _inteiro(valor: str | None, codigo: str, avisos: list[str]) -> int | None:
    if valor is None:
        return None
    try:
        return int(valor)
    except ValueError:
        avisos.append(f"{codigo}:valor_invalido")
        return None


def _ler_rpr(rpr, run: Run, avisos: list[str]) -> None:
    for f in rpr:
        ns, loc = _local(f)
        if ns != W:
            continue
        if loc == "b":
            run.negrito = _onoff(f)
        elif loc == "i":
            run.italico = _onoff(f)
        elif loc == "u":
            v = f.get(_a_name("val"))
            run.sublinhado = not (v is not None and v == "none")
        elif loc == "sz":
            run.tamanho_pt_meio = _inteiro(f.get(_a_name("val")), "TAMANHO", avisos)
        elif loc == "rFonts":
            fonte = f.get(_a_name("ascii")) or f.get(_a_name("hAnsi"))
            if fonte:
                run.fonte = fonte
        elif loc == "color":
            v = f.get(_a_name("val"))
            if v and v.lower() != "auto" and _HEX6.fullmatch(v):
                run.cor_hex = v.upper()
            elif v and v.lower() != "auto":
                avisos.append(f"COR_INVALIDA:{v[:12]}")
        else:
            avisos.append(f"FORMATO_RUN_NAO_MODELADO:{loc}")


def _ler_run(r, avisos: list[str]) -> Run:
    run = Run()
    partes: list[str] = []
    for f in r:
        ns, loc = _local(f)
        if loc is None:
            continue
        if ns != W:
            avisos.append(f"ELEMENTO_ESTRANHO_NA_RUN:{ns}")
            continue
        if loc == "rPr":
            _ler_rpr(f, run, avisos)
        elif loc == "t":
            partes.append(f.text or "")
        elif loc == "tab":
            partes.append("\t")
        elif loc == "br":
            tipo = f.get(_a_name("type"))
            if tipo in (None, "textWrapping"):
                partes.append("\n")
            else:
                avisos.append(f"QUEBRA_{tipo.upper()}_IGNORADA")
        elif loc == "cr":
            partes.append("\n")
        elif loc == "noBreakHyphen":
            partes.append("-")
        elif loc == "softHyphen":
            pass
        else:
            avisos.append(f"ELEMENTO_RUN_NAO_SUPORTADO:{loc}")
    run.texto = "".join(partes)
    return run


_CONTEINERES_INLINE = {"hyperlink", "fldSimple", "smartTag", "ins", "sdt", "sdtContent",
                       "customXml"}


def _runs_em(elemento, avisos: list[str], saida: list[Run]) -> None:
    for f in elemento:
        ns, loc = _local(f)
        if loc is None:
            continue
        if ns != W:
            avisos.append(f"ELEMENTO_ESTRANHO:{ns}")
            continue
        if loc == "r":
            saida.append(_ler_run(f, avisos))
        elif loc in _CONTEINERES_INLINE:
            if loc != "ins":
                avisos.append(f"CONTEUDO_ACHATADO:{loc}")
            _runs_em(f, avisos, saida)
        elif loc == "del":
            avisos.append("TEXTO_EXCLUIDO_IGNORADO")
        elif loc in ("sdtPr", "pPr", "bookmarkStart", "bookmarkEnd", "proofErr",
                     "permStart", "permEnd", "commentRangeStart", "commentRangeEnd"):
            continue
        else:
            avisos.append(f"ELEMENTO_NAO_SUPORTADO:p/{loc}")


def _ler_ppr(ppr, avisos: list[str]) -> dict:
    out: dict = {}
    for f in ppr:
        ns, loc = _local(f)
        if ns != W or loc is None:
            continue
        if loc == "jc":
            v = f.get(_a_name("val"))
            if v in _JC_LER:
                out["alinhamento"] = _JC_LER[v]
            else:
                avisos.append(f"JUSTIFICACAO_NAO_MODELADA:{v}")
        elif loc == "ind":
            esq = f.get(_a_name("left")) or f.get(_a_name("start"))
            if esq is not None:
                out["recuo_esquerdo_tw"] = _inteiro(esq, "RECUO", avisos)
            if f.get(_a_name("firstLine")) is not None:
                out["recuo_primeira_linha_tw"] = _inteiro(f.get(_a_name("firstLine")), "RECUO", avisos)
            elif f.get(_a_name("hanging")) is not None:
                h = _inteiro(f.get(_a_name("hanging")), "RECUO", avisos)
                out["recuo_primeira_linha_tw"] = None if h is None else -h
        elif loc == "spacing":
            if f.get(_a_name("before")) is not None:
                out["espaco_antes_tw"] = _inteiro(f.get(_a_name("before")), "ESPACO", avisos)
            if f.get(_a_name("after")) is not None:
                out["espaco_depois_tw"] = _inteiro(f.get(_a_name("after")), "ESPACO", avisos)
        elif loc not in _FORMATO_PPR_OK:
            avisos.append(f"FORMATO_PARAGRAFO_NAO_MODELADO:{loc}")
    return out


def _paragrafo(p, avisos: list[str]) -> Paragrafo:
    runs: list[Run] = []
    props: dict = {}
    for f in p:
        ns, loc = _local(f)
        if loc == "pPr" and ns == W:
            props = _ler_ppr(f, avisos)
    _runs_em(p, avisos, runs)
    return Paragrafo(runs=runs, **props)


def _blocos(elemento, paras: list[Paragrafo], avisos: list[str]) -> None:
    for f in elemento:
        ns, loc = _local(f)
        if loc is None:
            continue
        if ns != W:
            avisos.append(f"ELEMENTO_ESTRANHO_NO_CORPO:{ns}")
            continue
        if loc == "p":
            paras.append(_paragrafo(f, avisos))
        elif loc == "tbl":
            avisos.append("TABELA_ACHATADA")
            _blocos(f, paras, avisos)
        elif loc in ("tr", "tc", "sdt", "sdtContent", "customXml", "smartTag"):
            if loc == "sdt":
                avisos.append("CONTEUDO_ACHATADO:sdt")
            _blocos(f, paras, avisos)
        elif loc in ("sectPr", "bookmarkStart", "bookmarkEnd", "tblPr", "tblGrid", "sdtPr",
                     "sdtEndPr", "tcPr", "trPr"):
            continue
        else:
            avisos.append(f"ELEMENTO_NAO_SUPORTADO:corpo/{loc}")


def _core(dados: bytes) -> dict:
    raiz = _parse(dados, "docProps/core.xml")
    out = {"titulo": "", "autor": "", "criado_em": None, "modificado_em": None}
    mapa = {(DC, "title"): "titulo", (DC, "creator"): "autor",
            (DCT, "created"): "criado_em", (DCT, "modified"): "modificado_em"}
    for f in raiz:
        ns, loc = _local(f)
        chave = mapa.get((ns, loc))
        if chave:
            out[chave] = (f.text or "") if chave in ("titulo", "autor") else (f.text or None)
    return out


def _ler(dados: bytes, lim: dict) -> tuple[Documento, list[str]]:
    avisos: list[str] = []
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
    except (zipfile.BadZipFile, OSError, EOFError, ValueError):
        raise ErroDocx("ZIP_INVALIDO", "nao e um pacote ZIP") from None
    with z:
        infos = z.infolist()
        if len(infos) > lim["entradas"]:
            raise ErroDocx("ZIP_MUITAS_ENTRADAS", str(len(infos)))
        nomes: set[str] = set()
        brutos: set[str] = set()
        total_declarado = 0
        for info in infos:
            # Valida o nome bruto: no Windows o ZipInfo troca '\' por '/' em .filename.
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
                raise ErroDocx("ZIP_COMPRESSAO_NAO_SUPORTADA", f"{nome[:60]} metodo={info.compress_type}")
            if info.file_size > lim["parte_bytes"]:
                raise ErroDocx("ZIP_TAMANHO_EXCEDIDO", f"{nome[:60]} declarado={info.file_size}")
            if info.file_size >= lim["razao_min_bytes"] and (
                    info.compress_size == 0 or info.file_size / info.compress_size > lim["razao_max"]):
                raise ErroDocx("ZIP_RAZAO_ABSURDA", f"{nome[:60]} {info.file_size}/{info.compress_size}")
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

        def resolver(alvo: str) -> str:
            return alvo[1:] if alvo.startswith("/") else alvo

        rels = _parse(ler_parte("_rels/.rels"), "_rels/.rels")
        alvo_doc = alvo_core = None
        for rel in rels:
            tipo = rel.get("Type", "")
            if tipo.endswith("/officeDocument"):
                alvo_doc = resolver(rel.get("Target", ""))
            elif tipo.endswith("/core-properties"):
                alvo_core = resolver(rel.get("Target", ""))
        if not alvo_doc:
            raise ErroDocx("OPC_SEM_DOCUMENTO_PRINCIPAL")
        _validar_nome(alvo_doc)

        raiz = _parse(ler_parte(alvo_doc), alvo_doc)
        corpo = raiz.find(_a_name("body")) if _local(raiz)[1] == "document" else None
        if corpo is None:
            raise ErroDocx("XML_ESTRUTURA", "w:document/w:body ausente")
        paras: list[Paragrafo] = []
        _blocos(corpo, paras, avisos)

        meta = {"titulo": "", "autor": "", "criado_em": None, "modificado_em": None}
        if alvo_core and alvo_core in nomes:
            _validar_nome(alvo_core)
            meta = _core(ler_parte(alvo_core))

    doc = Documento(paragrafos=paras, **meta)
    return doc, list(dict.fromkeys(avisos))


def ler_docx(dados: bytes, limites: dict | None = None) -> tuple[Documento, list[str]]:
    """Le um .docx. Devolve (Documento, avisos). Falhas viram ErroDocx com .codigo."""
    if not isinstance(dados, (bytes, bytearray, memoryview)):
        raise ErroDocx("ENTRADA_INVALIDA", type(dados).__name__)
    lim = {**LIMITES_PADRAO, **(limites or {})}
    try:
        return _ler(bytes(dados), lim)
    except ErroDocx:
        raise
    except Exception as e:  # fronteira: o chamador nunca ve traceback
        raise ErroDocx("ERRO_INTERNO", type(e).__name__) from None
