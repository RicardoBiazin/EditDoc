"""Leitor minimo de PDF para os testes do M7. So' a biblioteca padrao (re e zlib).

O PySide6-Essentials nao traz o QtPdf, e a suite nao instala biblioteca de PDF. O
QPdfWriter grava um PDF simples: objetos `N 0 obj ... endobj`, conteudo com
FlateDecode, fontes Type0 (Identity-H) com ToUnicode. Isto basta para ler de volta:

- paginas na ordem do /Pages, com MediaBox;
- texto de cada pagina: os glifos de `<hex> Tj` (e de arrays TJ), traduzidos pelo
  ToUnicode da fonte selecionada com `Tf`;
- dicionario /Info (titulo, autor, criador), em UTF-16 com BOM ou PDFDocEncoding;
- fontes embutidas (FontFile2/FontFile3) e imagens (XObject /Image).

Nao e' um leitor geral: e' o que precisa para conferir o que o EditDoc escreve.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field

_OBJ = re.compile(rb"(\d+)\s+0\s+obj\b(.*?)endobj", re.S)
CRLF = bytes((13, 10))
_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\n?endstream", re.S)


@dataclass
class PaginaPdf:
    mediabox: tuple[float, float, float, float]
    texto: str
    fontes: list[str] = field(default_factory=list)
    imagens: int = 0

    @property
    def largura_pt(self) -> float:
        return self.mediabox[2] - self.mediabox[0]

    @property
    def altura_pt(self) -> float:
        return self.mediabox[3] - self.mediabox[1]


@dataclass
class DocumentoPdf:
    paginas: list[PaginaPdf]
    info: dict[str, str]
    fontes_embutidas: int
    fontes_sem_arquivo: list[str]
    conteudo_bruto: bytes

    @property
    def texto(self) -> str:
        return "\n".join(p.texto for p in self.paginas)


def _objetos(dados: bytes) -> dict[int, bytes]:
    return {int(m.group(1)): m.group(2) for m in _OBJ.finditer(dados)}


def _fluxo(corpo: bytes, objetos: dict[int, bytes] | None = None) -> bytes:
    """Conteudo do stream, pelo /Length (direto ou indireto): o dado comprimido pode
    terminar em byte de fim de linha, e cortar pelo "endstream" o estragaria."""
    m = _STREAM.search(corpo)
    if m is None:
        return b""
    bruto = m.group(1)
    tamanho = re.search(rb"/Length\s+(\d+)(\s+0\s+R)?", corpo.split(b"stream", 1)[0])
    if tamanho is not None:
        n = int(tamanho.group(1))
        if tamanho.group(2) and objetos is not None:
            n = int(objetos.get(n, b"-1").strip() or -1)
        inicio = corpo.find(b"stream") + len(b"stream")
        inicio += 2 if corpo[inicio:inicio + 2] == CRLF else 1
        if n >= 0:
            bruto = corpo[inicio:inicio + n]
    if b"/FlateDecode" in corpo.split(b"stream", 1)[0]:
        return zlib.decompress(bruto)
    return bruto


def _ref(corpo: bytes, chave: bytes) -> int | None:
    m = re.search(rb"/" + chave + rb"\s+(\d+)\s+0\s+R", corpo)
    return int(m.group(1)) if m else None


def _cadeia_pdf(bruto: bytes) -> str:
    """Conteudo de (...) do PDF: escapes, e UTF-16BE quando comeca com o BOM."""
    saida = bytearray()
    i = 0
    while i < len(bruto):
        c = bruto[i]
        if c == 0x5C and i + 1 < len(bruto):  # barra invertida
            prox = bruto[i + 1]
            mapa = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12,
                    ord("("): 40, ord(")"): 41, 0x5C: 0x5C}
            if prox in mapa:
                saida.append(mapa[prox])
                i += 2
                continue
            m = re.match(rb"[0-7]{1,3}", bruto[i + 1:i + 4])
            if m:
                saida.append(int(m.group(0), 8) & 0xFF)
                i += 1 + len(m.group(0))
                continue
            i += 1
            continue
        saida.append(c)
        i += 1
    if saida.startswith(b"\xfe\xff"):
        return bytes(saida[2:]).decode("utf-16-be", "replace")
    return bytes(saida).decode("latin-1")


def _info(dados: bytes, objetos: dict[int, bytes]) -> dict[str, str]:
    m = re.search(rb"/Info\s+(\d+)\s+0\s+R", dados)
    if m is None:
        return {}
    corpo = objetos.get(int(m.group(1)), b"")
    saida = {}
    for chave in (b"Title", b"Author", b"Creator", b"Producer", b"Subject"):
        mm = re.search(rb"/" + chave + rb"\s*\(((?:\\.|[^\\)])*)\)", corpo, re.S)
        if mm:
            saida[chave.decode()] = _cadeia_pdf(mm.group(1))
    return saida


def _cmap(texto: bytes) -> dict[int, str]:
    mapa: dict[int, str] = {}
    for bloco in re.findall(rb"beginbfchar(.*?)endbfchar", texto, re.S):
        for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", bloco):
            mapa[int(a, 16)] = bytes.fromhex(b.decode()).decode("utf-16-be", "replace")
    for bloco in re.findall(rb"beginbfrange(.*?)endbfrange", texto, re.S):
        for a, b, c in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
                                  bloco):
            base = bytes.fromhex(c.decode()).decode("utf-16-be", "replace")
            for k, codigo in enumerate(range(int(a, 16), int(b, 16) + 1)):
                mapa[codigo] = chr(ord(base[-1]) + k) if base else ""
        for a, b, lista in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", bloco,
                                      re.S):
            alvos = re.findall(rb"<([0-9A-Fa-f]+)>", lista)
            for k, codigo in enumerate(range(int(a, 16), int(b, 16) + 1)):
                if k < len(alvos):
                    mapa[codigo] = bytes.fromhex(alvos[k].decode()).decode("utf-16-be", "replace")
    return mapa


def _dicionario_de(corpo: bytes, chave: bytes, objetos: dict[int, bytes]) -> bytes:
    """O dicionario /Chave << ... >> direto, ou o objeto apontado por /Chave N 0 R."""
    ref = _ref(corpo, chave)
    if ref is not None:
        return objetos.get(ref, b"")
    m = re.search(rb"/" + chave + rb"\s*<<(.*?)>>", corpo, re.S)
    return m.group(1) if m else b""


def _texto_do_conteudo(conteudo: bytes, mapas: dict[bytes, dict[int, str]]) -> str:
    saida: list[str] = []
    mapa: dict[int, str] = {}
    for m in re.finditer(rb"/(\w+)\s+[\d.]+\s+Tf|<([0-9A-Fa-f]*)>\s*Tj|\[(.*?)\]\s*TJ|(ET)",
                         conteudo, re.S):
        if m.group(1) is not None:
            mapa = mapas.get(m.group(1), {})
        elif m.group(2) is not None:
            saida.append(_glifos(m.group(2), mapa))
        elif m.group(3) is not None:
            for hexa in re.findall(rb"<([0-9A-Fa-f]*)>", m.group(3)):
                saida.append(_glifos(hexa, mapa))
        else:
            saida.append("\n")
    return "".join(saida)


def _glifos(hexa: bytes, mapa: dict[int, str]) -> str:
    h = hexa.decode()
    return "".join(mapa.get(int(h[i:i + 4], 16), "�") for i in range(0, len(h) - 3, 4))


def ler_pdf(dados: bytes) -> DocumentoPdf:
    objetos = _objetos(dados)
    raiz = objetos.get(_ref(dados[dados.rfind(b"trailer"):], b"Root") or -1, b"")
    pages = objetos.get(_ref(raiz, b"Pages") or -1, b"")
    kids = re.search(rb"/Kids\s*\[(.*?)\]", pages, re.S)
    ids = [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", kids.group(1))] if kids else []
    cache_cmap: dict[int, dict[int, str]] = {}
    paginas: list[PaginaPdf] = []
    todas_fontes: set[int] = set()
    bruto_total = bytearray()
    for pid in ids:
        corpo = objetos[pid]
        mb = re.search(rb"/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]",
                       corpo)
        mediabox = tuple(float(x) for x in mb.groups()) if mb else (0.0, 0.0, 0.0, 0.0)
        recursos = _dicionario_de(corpo, b"Resources", objetos)
        fontes = _dicionario_de(recursos, b"Font", objetos)
        mapas: dict[bytes, dict[int, str]] = {}
        nomes: list[str] = []
        for nome, fid in re.findall(rb"/(\w+)\s+(\d+)\s+0\s+R", fontes):
            fid = int(fid)
            todas_fontes.add(fid)
            fobj = objetos.get(fid, b"")
            base = re.search(rb"/BaseFont\s*/([^\s/>]+)", fobj)
            nomes.append(base.group(1).decode() if base else "?")
            tu = _ref(fobj, b"ToUnicode")
            if tu is not None and tu not in cache_cmap:
                cache_cmap[tu] = _cmap(_fluxo(objetos.get(tu, b""), objetos))
            mapas[nome] = cache_cmap.get(tu, {}) if tu is not None else {}
        xobjs = _dicionario_de(recursos, b"XObject", objetos)
        imagens = sum(1 for _n, xid in re.findall(rb"/(\w+)\s+(\d+)\s+0\s+R", xobjs)
                      if b"/Subtype /Image" in objetos.get(int(xid), b"").split(b"stream")[0])
        conteudos = re.search(rb"/Contents\s+(\d+)\s+0\s+R", corpo)
        conteudo = _fluxo(objetos.get(int(conteudos.group(1)), b""), objetos) if conteudos else b""
        bruto_total += conteudo
        paginas.append(PaginaPdf(mediabox=mediabox, texto=_texto_do_conteudo(conteudo, mapas),
                                 fontes=nomes, imagens=imagens))
    embutidas = 0
    sem_arquivo: list[str] = []
    for corpo in objetos.values():
        if b"/Type /FontDescriptor" in corpo:
            nome = re.search(rb"/FontName\s*/([^\s/>]+)", corpo)
            if re.search(rb"/FontFile[23]?\s+\d+\s+0\s+R", corpo):
                embutidas += 1
            else:
                sem_arquivo.append(nome.group(1).decode() if nome else "?")
    return DocumentoPdf(paginas=paginas, info=_info(dados, objetos), fontes_embutidas=embutidas,
                        fontes_sem_arquivo=sem_arquivo, conteudo_bruto=bytes(bruto_total))


def sem_espacos(texto: str) -> str:
    """Texto sem espacos nem quebras: os glifos vem um a um, e o espaco pode faltar."""
    return re.sub(r"\s+", "", texto)
