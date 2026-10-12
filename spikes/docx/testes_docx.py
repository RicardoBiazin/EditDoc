"""Suite do SPIKE B (EditDoc): .docx com lxml + zipfile proprios, modelo puro, QTextDocument.

Rodar (sem gerar __pycache__ no repo):
    C:\\DEV\\EditDoc\\.venv\\Scripts\\python.exe -B C:\\DEV\\EditDoc\\spikes\\docx\\testes_docx.py
Sabotagem (deve FALHAR na regra de xml:space):
    ... testes_docx.py --sabotar sem_xml_space
Saidas (.docx e resumo.json) vao para EDITDOC_SPIKE_SAIDAS ou para o scratchpad.
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import io
import json
import os
import posixpath
import re
import subprocess
import sys
import time
import warnings
import zipfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lxml import etree  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import escritor  # noqa: E402
import leitor  # noqa: E402
from leitor import ErroDocx  # noqa: E402
from modelo import Documento, Paragrafo, Run  # noqa: E402

SCRATCH = Path(r"C:\Users\GRRR03~1\AppData\Local\Temp\claude\g--Drives-compartilhados-Ricardo-Biazin-Python"
               r"\a62504b4-5c1f-485b-a564-e5755b35ed5a\scratchpad\spike-docx")
SAIDAS_BASE = Path(os.environ.get("EDITDOC_SPIKE_SAIDAS", str(SCRATCH)))
SAIDAS = SAIDAS_BASE

W = escritor.W
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MiB = 1024 * 1024
META_TEMPO_S = 5.0
LIMITE_HOSTIL_S = 2.0

# Referencia independente da ordem (fato 10). Conferida contra os successors do python-docx 1.2.0.
REF_PPR = ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl",
           "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens",
           "kinsoku", "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN",
           "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind", "contextualSpacing",
           "mirrorIndents", "suppressOverlap", "jc", "textDirection", "textAlignment",
           "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr", "pPrChange"]
REF_RPR = ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike",
           "outline", "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden",
           "color", "spacing", "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect",
           "bdr", "shd", "fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout",
           "specVanish", "oMath"]
_CTRL_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]")

_G = None
RES: dict[str, dict] = {}


def Q(local: str) -> str:
    return "{%s}%s" % (W, local)


def grupo(nome: str, titulo: str) -> None:
    global _G
    _G = nome
    RES.setdefault(nome, {"titulo": titulo, "ok": 0, "falha": 0, "m": {}})
    print(f"\n=== {nome} {titulo}")


def checa(cond, msg: str) -> bool:
    r = RES[_G]
    if cond:
        r["ok"] += 1
        print(f"  OK    {msg}")
    else:
        r["falha"] += 1
        print(f"  FALHA {msg}")
    return bool(cond)


def medida(chave: str, valor) -> None:
    RES[_G]["m"][chave] = valor


# ----------------------------------------------------------------- fixtures

def fixture() -> Documento:
    R, P = Run, Paragrafo
    paras = [
        P(alinhamento="centro", espaco_antes_tw=240, espaco_depois_tw=120,
          runs=[R("Relatório de São Paulo", negrito=True, tamanho_pt_meio=32, fonte="Arial",
                  cor_hex="1F3864")]),
        P(alinhamento="justificado", recuo_primeira_linha_tw=720, runs=[
            R("Olá, coração! Ação à vista, não é? Até já. ", negrito=None, italico=None),
            R("negrito e itálico", negrito=True, italico=True),
            R(" sublinhado", sublinhado=True),
            R(" sem sublinhado", sublinhado=False),
            R(" tamanho 12,5", tamanho_pt_meio=25),
            R(" normal explícito", negrito=False, italico=False, sublinhado=None),
        ]),
        P(alinhamento="direita", recuo_esquerdo_tw=1440,
          runs=[R("Tab:\tfim; quebra:\nsegunda linha ")]),
        P(alinhamento="esquerda", recuo_esquerdo_tw=720, recuo_primeira_linha_tw=-360,
          runs=[R("Suspenso: deslocamento negativo", fonte="Times New Roman", cor_hex="C00000")]),
        P(runs=[]),
        P(runs=[R(" espaço nas pontas ")]),
        P(runs=[R("Emoji 😀 e foguete 🚀 fora do BMP", negrito=True)]),
        P(runs=[R("Ç ç Ã ã À à Õ õ Ê ê — “aspas” ‘x’ €")]),
        P(espaco_antes_tw=0, espaco_depois_tw=0, runs=[R("   ")]),
        P(alinhamento="justificado", runs=[R("Último: ", italico=True), R("sem formatação explícita")]),
    ]
    return Documento(paragrafos=paras, titulo="Relatório São Paulo — teste",
                     autor="José da Conceição", criado_em="2026-10-11T12:00:00Z",
                     modificado_em="2026-10-11T12:30:00Z")


def modelo_perf(n: int = 6000) -> Documento:
    paras = []
    alin = ["esquerda", "justificado", "centro", "direita"]
    for i in range(n):
        runs = [
            Run(f"Parágrafo {i}: texto de teste com acentos ção. ", negrito=(i % 2 == 0), tamanho_pt_meio=22),
            Run("parte B itálico ", italico=True, fonte="Arial"),
            Run(f"fim {i}\t", sublinhado=False, cor_hex="003366"),
        ]
        paras.append(Paragrafo(runs=runs, alinhamento=alin[i % 4],
                               recuo_primeira_linha_tw=720 if i % 3 == 0 else None,
                               espaco_depois_tw=120))
    return Documento(paragrafos=paras, titulo="Perf", autor="Teste",
                     criado_em="2026-10-11T12:00:00Z", modificado_em="2026-10-11T12:00:00Z")


def primeira_diferenca(a: Documento, b: Documento) -> str:
    if len(a.paragrafos) != len(b.paragrafos):
        return f"paragrafos {len(a.paragrafos)} x {len(b.paragrafos)}"
    for i, (pa, pb) in enumerate(zip(a.paragrafos, b.paragrafos)):
        if pa != pb:
            for c in dataclasses.fields(Paragrafo):
                if c.name != "runs" and getattr(pa, c.name) != getattr(pb, c.name):
                    return f"par {i} {c.name}: {getattr(pa, c.name)!r} x {getattr(pb, c.name)!r}"
            if len(pa.runs) != len(pb.runs):
                return f"par {i} n_runs {len(pa.runs)} x {len(pb.runs)}"
            for j, (ra, rb) in enumerate(zip(pa.runs, pb.runs)):
                if ra != rb:
                    return f"par {i} run {j}: {ra} x {rb}"
    for c in ("titulo", "autor", "criado_em", "modificado_em"):
        if getattr(a, c) != getattr(b, c):
            return f"{c}: {getattr(a, c)!r} x {getattr(b, c)!r}"
    return "?"


def _base_entradas() -> list[tuple[str, bytes]]:
    dados = escritor.escrever_docx(fixture())
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        return [(i.filename, z.read(i.filename)) for i in z.infolist()]


def _montar(entradas, metodo=zipfile.ZIP_DEFLATED) -> bytes:
    """Monta um ZIP com nomes exatos. ZipInfo.filename e trocado depois de criado para
    nao sofrer a normalizacao de separador do Windows (teste de barra invertida)."""
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(buf, "w") as z:
            for nome, dados in entradas:
                info = zipfile.ZipInfo("x")
                info.filename = nome
                info.compress_type = metodo
                info.external_attr = 0o600 << 16
                z.writestr(info, dados)
    return buf.getvalue()


# ----------------------------------------------------------------- T1

def t1() -> None:
    grupo("T1", "round-trip do modelo (modelo -> bytes -> modelo)")
    doc = fixture()
    dados, av_w = escritor.escrever_docx_com_avisos(doc)
    doc2, av_r = leitor.ler_docx(dados)
    nruns = sum(len(p.runs) for p in doc.paragrafos)
    checa(doc2 == doc, f"modelo igual apos ida e volta ({len(doc.paragrafos)} paragrafos, {nruns} runs)"
          + ("" if doc2 == doc else f"; primeira diferenca: {primeira_diferenca(doc, doc2)}"))
    checa(av_w == [] and av_r == [], f"sem avisos na gravacao e na leitura (gravacao={av_w}, leitura={av_r})")
    d3 = Documento(paragrafos=[Paragrafo(runs=[Run("a\x01b\r\nc\rd")])])
    r3, _ = leitor.ler_docx(escritor.escrever_docx(d3))
    checa(r3.paragrafos[0].runs[0].texto == "ab\nc\nd",
          "controle invalido removido; CRLF e CR viram quebra de linha (perda documentada)")
    (SAIDAS / "fixture_t1.docx").write_bytes(dados)
    medida("paragrafos", len(doc.paragrafos))
    medida("runs", nruns)
    medida("bytes_docx", len(dados))


# ----------------------------------------------------------------- T2

def t2() -> None:
    grupo("T2", "python-docx como oraculo independente (so leitura)")
    import docx as pdocx
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_UNDERLINE

    doc = fixture()
    dados = escritor.escrever_docx(doc)
    pd = pdocx.Document(io.BytesIO(dados))
    pars = pd.paragraphs
    checa(len(pars) == len(doc.paragrafos), f"python-docx enxerga {len(pars)} paragrafos")
    AL = {WD_ALIGN_PARAGRAPH.LEFT: "esquerda", WD_ALIGN_PARAGRAPH.CENTER: "centro",
          WD_ALIGN_PARAGRAPH.RIGHT: "direita", WD_ALIGN_PARAGRAPH.JUSTIFY: "justificado",
          None: None}
    diverg: list[str] = []
    n = 0

    def cmp(rotulo, esperado, lido):
        nonlocal n
        n += 1
        if esperado != lido:
            diverg.append(f"{rotulo}: esperado {esperado!r}, python-docx {lido!r}")

    def tw(L):  # 1 twip = 635 EMU
        return None if L is None else round(L / 635)

    for i, (pm, pp) in enumerate(zip(doc.paragrafos, pars)):
        pf = pp.paragraph_format
        cmp(f"p{i}.alinhamento", pm.alinhamento, AL.get(pp.alignment, "??"))
        cmp(f"p{i}.recuo_esq", pm.recuo_esquerdo_tw, tw(pf.left_indent))
        cmp(f"p{i}.recuo_1a", pm.recuo_primeira_linha_tw, tw(pf.first_line_indent))
        cmp(f"p{i}.antes", pm.espaco_antes_tw, tw(pf.space_before))
        cmp(f"p{i}.depois", pm.espaco_depois_tw, tw(pf.space_after))
        if len(pp.runs) != len(pm.runs):
            cmp(f"p{i}.n_runs", len(pm.runs), len(pp.runs))
            continue
        for j, (rm, rp) in enumerate(zip(pm.runs, pp.runs)):
            u = rp.underline
            cmp(f"p{i}r{j}.texto", rm.texto, rp.text)
            cmp(f"p{i}r{j}.negrito", rm.negrito, rp.bold)
            cmp(f"p{i}r{j}.italico", rm.italico, rp.italic)
            cmp(f"p{i}r{j}.sublinhado", rm.sublinhado, None if u is None else (u != WD_UNDERLINE.NONE))
            cmp(f"p{i}r{j}.tamanho", rm.tamanho_pt_meio,
                None if rp.font.size is None else round(rp.font.size.pt * 2))
            cmp(f"p{i}r{j}.fonte", rm.fonte, rp.font.name)
            cor = rp.font.color.rgb
            cmp(f"p{i}r{j}.cor", rm.cor_hex, None if cor is None else str(cor).upper())
    checa(not diverg, f"python-docx concorda em {n} verificacoes de run e paragrafo"
          + ("" if not diverg else f"; {len(diverg)} divergencias, ex.: {diverg[:3]}"))
    checa(pd.core_properties.title == doc.titulo and pd.core_properties.author == doc.autor,
          "python-docx le titulo e autor")
    medida("verificacoes", n)
    medida("divergencias", len(diverg))


# ----------------------------------------------------------------- T3

def partes_xml(dados: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        return {i.filename: z.read(i.filename) for i in z.infolist()
                if i.filename.endswith(".xml") and i.filename != "[Content_Types].xml"}


def validar_xml(partes: dict[str, bytes]) -> list[str]:
    viol: list[str] = []
    for nome, dados in partes.items():
        raiz = etree.fromstring(dados)
        for el in raiz.iter():
            if not isinstance(el.tag, str):
                continue
            if el.tag == Q("t"):
                txt = el.text or ""
                if txt != txt.strip() and el.get(XML_SPACE) != "preserve":
                    viol.append(f"{nome}: w:t com espaco nas pontas sem xml:space: {txt!r}")
                if _CTRL_XML.search(txt):
                    viol.append(f"{nome}: caractere de controle invalido em w:t")
                continue
            if el.tag == Q("pPr"):
                ref, rot = REF_PPR, "pPr"
            elif el.tag == Q("rPr"):
                ref, rot = REF_RPR, "rPr"
            else:
                continue
            idx = {Q(x): i for i, x in enumerate(ref)}
            ultimo = -1
            for f in el:
                if not isinstance(f.tag, str):
                    continue
                loc = etree.QName(f).localname
                if f.tag not in idx:
                    viol.append(f"{nome}: <{rot}> com filho desconhecido <{loc}>")
                    continue
                i = idx[f.tag]
                if i <= ultimo:
                    viol.append(f"{nome}: <{rot}> tem <{loc}> depois de <{ref[ultimo]}> (ordem ou duplicata)")
                ultimo = max(ultimo, i)
    return viol


def _ordem_pydocx() -> dict | None:
    """Le a ordem do proprio python-docx pelo codigo-fonte (ast): a tupla `_tag_seq` de
    parfmt.py (pPr) e font.py (rPr). Nao usa atributo de classe, que o modulo nao expoe.
    None se nao achar."""
    try:
        import ast
        import docx.oxml.text.font as fnt_mod
        import docx.oxml.text.parfmt as pf_mod
    except Exception:
        return None

    def ler(caminho: str):
        arvore = ast.parse(Path(caminho).read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_tag_seq"
                                                  for t in no.targets):
                return [s.split(":")[-1] for s in ast.literal_eval(no.value)]
        return None

    ppr, rpr = ler(pf_mod.__file__), ler(fnt_mod.__file__)
    return None if ppr is None or rpr is None else {"pPr": ppr, "rPr": rpr}


def t3(sabotado: bool) -> None:
    grupo("T3", "validador de ordem pPr/rPr e regra de xml:space")
    dados = escritor.escrever_docx(fixture())
    partes = partes_xml(dados)
    viol = validar_xml(partes)
    checa(not viol, f"fixture sem violacao de ordem nem de xml:space ({len(viol)} violacoes)"
          + ("" if not viol else f"; ex.: {viol[0]}"))
    ref_pd = _ordem_pydocx()
    if ref_pd is None:
        print("  NAO VERIFICADO: _tag_seq do python-docx nao localizado em tempo de execucao")
    else:
        checa(ref_pd == {"pPr": REF_PPR, "rPr": REF_RPR},
              "lista de ordem do validador igual a do python-docx 1.2.0")

    # Contraprova 1: <b> depois de <i> tem de ser acusado.
    raiz = etree.fromstring(partes["word/document.xml"])
    p = etree.Element(Q("p"))
    r = etree.SubElement(p, Q("r"))
    rpr = etree.SubElement(r, Q("rPr"))
    etree.SubElement(rpr, Q("i"))
    etree.SubElement(rpr, Q("b"))
    etree.SubElement(r, Q("t")).text = "x"
    raiz.find(Q("body")).insert(0, p)
    ruim = dict(partes)
    ruim["word/document.xml"] = etree.tostring(raiz)
    v2 = validar_xml(ruim)
    checa(any("tem <b> depois de <i>" in v for v in v2),
          f"contraprova: <b> depois de <i> e acusado ({len(v2)} violacao(oes))")

    # Contraprova 2: escritor sem xml:space tem de ser acusado.
    with mock.patch.object(escritor, "_marcar_espaco", lambda t, texto: None):
        dados_sab = escritor.escrever_docx(fixture())
    v3 = validar_xml(partes_xml(dados_sab))
    checa(len(v3) > 0, f"contraprova: escritor sem xml:space e acusado ({len(v3)} violacoes)")
    medida("violacoes_fixture", len(viol))
    medida("violacoes_contraprova_ordem", len(v2))
    medida("violacoes_sabotagem_xmlspace", len(v3))
    if sabotado:
        print("  (modo sabotado ativo: a checagem da fixture acima deve FALHAR)")


# ----------------------------------------------------------------- T4

def checar_pacote(dados: bytes) -> tuple[list[str], dict]:
    viol: list[str] = []
    z = zipfile.ZipFile(io.BytesIO(dados))
    infos = [i for i in z.infolist() if not i.is_dir()]
    nomes = [i.filename for i in infos]
    nomes_set = set(nomes)
    ct = etree.fromstring(z.read("[Content_Types].xml"))
    defaults, overrides = {}, {}
    for el in ct:
        loc = etree.QName(el).localname
        if loc == "Default":
            defaults[el.get("Extension").lower()] = el.get("ContentType")
        elif loc == "Override":
            overrides[el.get("PartName")] = el.get("ContentType")
    for n in nomes:
        if n == "[Content_Types].xml":
            continue
        ext = n.rsplit(".", 1)[-1].lower() if "." in posixpath.basename(n) else ""
        if "/" + n not in overrides and ext not in defaults:
            viol.append(f"sem Content_Type: {n}")
    for pn in overrides:
        if pn[1:] not in nomes_set:
            viol.append(f"Override sem parte: {pn}")

    rels_por_origem: dict[str, dict[str, str]] = {}
    rel_files = [n for n in nomes if n.endswith(".rels")]
    alvos_ok = 0
    for rn in rel_files:
        base_dir = posixpath.dirname(posixpath.dirname(rn))
        bn = posixpath.basename(rn)
        origem = "" if bn == ".rels" else posixpath.join(base_dir, bn[:-5])
        alvos = {}
        for rel in etree.fromstring(z.read(rn)):
            if rel.get("TargetMode") == "External":
                continue
            alvo = rel.get("Target")
            caminho = alvo[1:] if alvo.startswith("/") else posixpath.normpath(posixpath.join(base_dir, alvo))
            alvos[rel.get("Id")] = caminho
            if caminho in nomes_set:
                alvos_ok += 1
            else:
                viol.append(f"rel quebrada em {rn}: {rel.get('Id')} -> {caminho}")
        rels_por_origem[origem] = alvos

    alcancadas: set[str] = set()
    fila = [""]
    visitadas: set[str] = set()
    while fila:
        o = fila.pop()
        if o in visitadas:
            continue
        visitadas.add(o)
        for caminho in rels_por_origem.get(o, {}).values():
            if caminho not in alcancadas:
                alcancadas.add(caminho)
                fila.append(caminho)
    for n in nomes:
        if n == "[Content_Types].xml" or n.endswith(".rels"):
            continue
        if n not in alcancadas:
            viol.append(f"parte orfa: {n}")

    for n in nomes:
        if not n.endswith(".xml") or n == "[Content_Types].xml":
            continue
        alvos = rels_por_origem.get(n, {})
        for el in etree.fromstring(z.read(n)).iter():
            if not isinstance(el.tag, str):
                continue
            for att, val in el.attrib.items():
                if att.startswith("{%s}" % R_NS) and val not in alvos:
                    viol.append(f"r:id {val} sem relacionamento em {n}")
    return viol, {"partes": len(nomes), "rels": len(rel_files), "alvos": alvos_ok}


def t4() -> None:
    grupo("T4", "integridade do pacote OPC")
    base = _base_entradas()
    viol, info = checar_pacote(_montar(base))
    checa(not viol, f"todo rId resolve, toda parte tem Content_Type, nenhuma parte orfa "
          f"({info['partes']} partes, {info['rels']} .rels, {info['alvos']} alvos resolvidos)"
          + ("" if not viol else f"; ex.: {viol[:2]}"))
    v_orfa = checar_pacote(_montar(base + [("word/orfa.xml", b"<x/>")]))[0]
    v_ct = checar_pacote(_montar(base + [("extra/dados.bin", b"x")]))[0]
    v_rel = checar_pacote(_montar([e for e in base if e[0] != "word/styles.xml"]))[0]
    checa(any("parte orfa: word/orfa.xml" in v for v in v_orfa)
          and any("sem Content_Type: extra/dados.bin" in v for v in v_ct)
          and any("rel quebrada" in v for v in v_rel),
          "contraprovas: parte orfa, parte sem Content_Type e rel quebrada sao acusadas")
    medida("partes", info["partes"])
    medida("alvos_resolvidos", info["alvos"])
    medida("violacoes_fixture", len(viol))


# ----------------------------------------------------------------- T5

def _billion_payload() -> bytes:
    ent = '<!ENTITY lol "lol">'
    for i in range(1, 10):  # lol1 = 10 x &lol;  lol2 = 10 x &lol1;  ... lol9 (10^9 "lol")
        ref = "&lol;" if i == 1 else f"&lol{i - 1};"
        ent += f'<!ENTITY lol{i} "' + ref * 10 + '">'
    return ('<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE w:document [' + ent + ']>'
            f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>&lol9;</w:t></w:r></w:p>'
            '</w:body></w:document>').encode()


def _camada_lxml_sem_scanner() -> tuple[str, float]:
    """Mede o lxml sozinho (sem a checagem de DOCTYPE), como segunda barreira.
    Devolve (texto para o relatorio, maior tempo gasto)."""
    partes = []
    maior = 0.0
    for resolver in (False, True):
        t0 = time.perf_counter()
        try:
            parser = etree.XMLParser(resolve_entities=resolver, no_network=True, load_dtd=False,
                                     huge_tree=False)
            raiz = etree.fromstring(_billion_payload(), parser)
            t = raiz.find(".//" + Q("t"))
            tam = len(t.text) if (t is not None and t.text) else 0
            dt = time.perf_counter() - t0
            partes.append(f"resolve={resolver}: aceitou, texto={tam} chars, {dt:.3f}s")
        except etree.LxmlError as e:
            dt = time.perf_counter() - t0
            partes.append(f"resolve={resolver}: recusou em {dt:.3f}s ({str(e)[:60]})")
        maior = max(maior, dt)
    return " | ".join(partes), maior


def t5() -> None:
    grupo("T5", "arquivos hostis gerados por codigo")
    base = _base_entradas()
    doc_xml = dict(base)["word/document.xml"]
    sub = lambda nome, novo, metodo=zipfile.ZIP_DEFLATED: _montar(  # noqa: E731
        [(n, novo if n == nome else d) for n, d in base], metodo)
    casos = [
        ("DOCTYPE", lambda: sub("word/document.xml", doc_xml.replace(
            b"?>", b'?><!DOCTYPE w:document SYSTEM "http://127.0.0.1:9/x.dtd">', 1)), "XML_DOCTYPE_PROIBIDO"),
        ("billion laughs", lambda: sub("word/document.xml", _billion_payload()), "XML_DOCTYPE_PROIBIDO"),
        ("entrada '../'", lambda: _montar(base + [("../evil.xml", b"<x/>")]), "ZIP_NOME_INVALIDO"),
        ("entrada absoluta '/word/evil.xml'", lambda: _montar(base + [("/word/evil.xml", b"<x/>")]),
         "ZIP_NOME_INVALIDO"),
        ("entrada 'C:/evil.xml'", lambda: _montar(base + [("C:/evil.xml", b"<x/>")]), "ZIP_NOME_INVALIDO"),
        ("barra invertida 'word\\evil.xml'", lambda: _montar(base + [("word\\evil.xml", b"<x/>")]),
         "ZIP_NOME_INVALIDO"),
        ("bomba: 100 MiB de zeros", lambda: sub("word/document.xml", b"\x00" * (100 * MiB)),
         "ZIP_RAZAO_ABSURDA"),
        ("document.xml acima de 128 MiB descompactados",
         lambda: sub("word/document.xml", base64.b64encode(os.urandom(97 * MiB))), "ZIP_TAMANHO_EXCEDIDO"),
        ("XML malformado", lambda: sub("word/document.xml", b"<w:document xmlns:w='x'><w:body>"),
         "XML_MALFORMADO"),
        ("arquivo que nao e ZIP", lambda: b"isto nao e zip", "ZIP_INVALIDO"),
        ("extra: 5009 entradas", lambda: _montar(base + [(f"extra/{i}.txt", b"x") for i in range(5001)]),
         "ZIP_MUITAS_ENTRADAS"),
        ("extra: aninhamento de 1000 niveis",
         lambda: sub("word/document.xml", f'<w:document xmlns:w="{W}"><w:body>'.encode()
                     + b"<x>" * 1000 + b"</x>" * 1000 + b"</w:body></w:document>"), "XML_MALFORMADO"),
        ("extra: UTF-16 com BOM", lambda: sub("word/document.xml", doc_xml.decode().encode("utf-16")),
         "XML_CODIFICACAO_NAO_SUPORTADA"),
        ("extra: nome duplicado", lambda: _montar(base + [("word/document.xml", doc_xml)]),
         "ZIP_NOME_DUPLICADO"),
        ("extra: metodo bzip2", lambda: sub("word/document.xml", doc_xml, zipfile.ZIP_BZIP2),
         "ZIP_COMPRESSAO_NAO_SUPORTADA"),
        ("extra: parte document.xml ausente", lambda: _montar([e for e in base if e[0] != "word/document.xml"]),
         "ZIP_PARTE_AUSENTE"),
    ]
    maior = 0.0
    for nome, gerar, esperado in casos:
        dados = gerar()
        t0 = time.perf_counter()
        try:
            leitor.ler_docx(dados)
            codigo = "SEM_ERRO"
        except ErroDocx as e:
            codigo = e.codigo
        except BaseException as e:  # nada pode vazar
            codigo = "EXCECAO_VAZOU:" + type(e).__name__
        dt = time.perf_counter() - t0
        maior = max(maior, dt)
        checa(codigo == esperado and dt < LIMITE_HOSTIL_S,
              f"{nome}: {codigo} em {dt:.3f} s" + ("" if codigo == esperado else f" (esperado {esperado})"))
        del dados
    texto_lxml, dt_lxml = _camada_lxml_sem_scanner()
    print(f"  INFO  camada lxml sem a checagem de DOCTYPE: {texto_lxml}")
    checa(dt_lxml < LIMITE_HOSTIL_S, f"lxml sozinho tambem termina em < {LIMITE_HOSTIL_S:.0f} s no billion laughs")
    medida("lxml_sozinho", texto_lxml)
    medida("casos", len(casos))
    medida("maior_tempo_s", round(maior, 3))


# ----------------------------------------------------------------- T6

def _normalizar(doc: Documento) -> Documento:
    """Funde runs vizinhos de mesma formatacao e descarta run vazio (o Qt faz o mesmo)."""
    chave = lambda r: (r.negrito, r.italico, r.sublinhado, r.tamanho_pt_meio, r.fonte, r.cor_hex)  # noqa: E731
    paras = []
    for p in doc.paragrafos:
        novos: list[Run] = []
        for r in p.runs:
            if r.texto == "":
                continue
            if novos and chave(novos[-1]) == chave(r):
                novos[-1] = dataclasses.replace(novos[-1], texto=novos[-1].texto + r.texto)
            else:
                novos.append(dataclasses.replace(r))
        paras.append(dataclasses.replace(p, runs=novos))
    return dataclasses.replace(doc, paragrafos=paras)


def _medir_margens_qt() -> str:
    from PySide6.QtGui import QTextBlockFormat, QTextCursor, QTextDocument
    import ponte_qt as pq
    pq.garantir_app()
    qd = QTextDocument()
    qd.setTextWidth(600)
    cur = QTextCursor(qd)
    cur.insertText("um")
    bf = QTextBlockFormat()
    bf.setBottomMargin(240 * pq.PX_POR_TWIP)  # 16 px
    cur.setBlockFormat(bf)
    cur.insertBlock()
    cur.insertText("dois")
    bf2 = QTextBlockFormat()
    bf2.setTopMargin(240 * pq.PX_POR_TWIP)  # 16 px
    cur.setBlockFormat(bf2)
    lay = qd.documentLayout()
    r1 = lay.blockBoundingRect(qd.findBlock(0))
    r2 = lay.blockBoundingRect(qd.findBlock(qd.characterCount() - 2))
    gap = r2.top() - r1.bottom()
    return f"espaco entre blocos = {gap:.1f} px (margens de 16 px + 16 px: soma=32, maior=16)"


def t6() -> None:
    grupo("T6", "mapeamento para QTextDocument (PySide6, offscreen)")
    import ponte_qt as pq
    from PySide6.QtGui import QTextFormat
    doc = fixture()
    qd = pq.modelo_para_qt(doc)
    back = pq.qt_para_modelo(qd)
    norm_doc, norm_back = _normalizar(doc), _normalizar(back)
    runs_orig = sum(len(p.runs) for p in doc.paragrafos)
    runs_norm = sum(len(p.runs) for p in norm_doc.paragrafos)
    runs_qt = sum(len(p.runs) for p in back.paragrafos)
    # Metadados (titulo, autor, datas) nao existem no QTextDocument: comparacao so de paragrafos.
    checa(norm_back.paragrafos == norm_doc.paragrafos,
          f"paragrafos: modelo -> QTextDocument -> modelo igual apos normalizar runs vizinhos "
          f"({runs_orig} runs -> {runs_norm} normalizados -> {runs_qt} lidos do Qt)")
    print("  INFO  fora do mapeamento: titulo, autor, criado_em, modificado_em (QTextDocument nao os carrega)")
    # Fusao de runs vizinhos de mesma formatacao: medida, nao corrigida.
    par2 = Documento(paragrafos=[Paragrafo(runs=[Run("a", negrito=True), Run("b", negrito=True),
                                                  Run("c", negrito=False)])])
    back2 = pq.qt_para_modelo(pq.modelo_para_qt(par2))
    print(f"  INFO  runs vizinhos iguais (a,b negrito; c sem negrito): 3 -> "
          f"{len(back2.paragrafos[0].runs)} lidos do Qt; textos {[r.texto for r in back2.paragrafos[0].runs]}")
    # Divergencias por campo
    campos: dict[str, list[str]] = {}
    if len(norm_doc.paragrafos) != len(norm_back.paragrafos):
        campos.setdefault("n_paragrafos", []).append("diferente")
    for i, (pa, pb) in enumerate(zip(norm_doc.paragrafos, norm_back.paragrafos)):
        for c in ("alinhamento", "recuo_esquerdo_tw", "recuo_primeira_linha_tw", "espaco_antes_tw",
                  "espaco_depois_tw"):
            if getattr(pa, c) != getattr(pb, c):
                campos.setdefault(c, []).append(f"p{i} {getattr(pa, c)!r}->{getattr(pb, c)!r}")
        for j, (ra, rb) in enumerate(zip(pa.runs, pb.runs)):
            for c in ("texto", "negrito", "italico", "sublinhado", "tamanho_pt_meio", "fonte", "cor_hex"):
                if getattr(ra, c) != getattr(rb, c):
                    campos.setdefault(c, []).append(f"p{i}r{j} {getattr(ra, c)!r}->{getattr(rb, c)!r}")
    for c, ex in campos.items():
        print(f"  GAP   {c}: {len(ex)} divergencia(s), ex.: {ex[0]}")
    exatos = [c for c in ("alinhamento", "recuo_esquerdo_tw", "recuo_primeira_linha_tw", "espaco_antes_tw",
                          "espaco_depois_tw", "texto", "negrito", "italico", "sublinhado", "tamanho_pt_meio",
                          "fonte", "cor_hex") if c not in campos]
    checa(len(exatos) == 12, f"campos mapeados sem perda: {', '.join(exatos)}")
    # Propriedades do QTextDocument: tri-state
    p_none = pq.modelo_para_qt(Documento(paragrafos=[Paragrafo(runs=[Run("a", negrito=None), Run("b", negrito=False)])]))
    b = p_none.begin()
    it = b.begin()
    f1 = it.fragment().charFormat()
    it += 1
    f2 = it.fragment().charFormat()
    checa(not f1.hasProperty(QTextFormat.Property.FontWeight) and f2.hasProperty(QTextFormat.Property.FontWeight),
          "tri-state de negrito preservado no Qt: None = propriedade ausente; False = peso 400 explicito")
    com_quebra = [i for i, p in enumerate(doc.paragrafos) if any("\n" in r.texto for r in p.runs)]
    checa(all(any("\n" in r.texto for r in back.paragrafos[i].runs) for i in com_quebra),
          "quebra de linha interna: '\\n' vira U+2028 no Qt e volta para '\\n' na leitura")
    # toPlainText() converte U+2028 em '\n': a checagem tem de ler o texto do bloco.
    textos_blocos = [qd.findBlockByNumber(i).text() for i in range(qd.blockCount())]
    checa(any("\u2028" in t for t in textos_blocos), "gravado no Qt: quebra interna e U+2028 no texto do bloco")
    margens = _medir_margens_qt()
    print(f"  INFO  margens verticais (fato 3, nao corrigido): {margens}")
    medida("runs_modelo", runs_orig)
    medida("runs_normalizados", runs_norm)
    medida("runs_lidos_qt", runs_qt)
    medida("campos_com_gap", sorted(campos.keys()))
    medida("margens", margens)


# ----------------------------------------------------------------- T7

def _rss_mb():
    if os.name != "nt":
        return None, None
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        return None, None
    return round(pmc.WorkingSetSize / MiB, 1), round(pmc.PeakWorkingSetSize / MiB, 1)


def _modo_perf(fase: str, caminho: str) -> None:
    """Executa uma fase isolada (processo novo) e imprime JSON com tempo e RSS."""
    base_mb, _ = _rss_mb()
    if fase == "escrever":
        doc = modelo_perf()
        antes, _ = _rss_mb()
        t0 = time.perf_counter()
        dados = escritor.escrever_docx(doc)
        dt = time.perf_counter() - t0
        _, pico = _rss_mb()
        Path(caminho).write_bytes(dados)
        h = hashlib.sha256(repr(doc).encode()).hexdigest()[:16]
        out = {"s": round(dt, 3), "bytes": len(dados), "rss_base_mb": base_mb, "rss_antes_mb": antes,
               "pico_mb": pico, "hash": h, "paragrafos": len(doc.paragrafos),
               "runs": sum(len(p.runs) for p in doc.paragrafos)}
    else:
        dados = Path(caminho).read_bytes()
        antes, _ = _rss_mb()
        t0 = time.perf_counter()
        doc, av = leitor.ler_docx(dados)
        dt = time.perf_counter() - t0
        _, pico = _rss_mb()
        h = hashlib.sha256(repr(doc).encode()).hexdigest()[:16]
        out = {"s": round(dt, 3), "bytes": len(dados), "rss_base_mb": base_mb, "rss_antes_mb": antes,
               "pico_mb": pico, "hash": h, "paragrafos": len(doc.paragrafos),
               "runs": sum(len(p.runs) for p in doc.paragrafos), "avisos": av}
    print(json.dumps(out))


def _subproc(fase: str, caminho: Path) -> dict:
    r = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--perf", fase, str(caminho)],
                       capture_output=True, text=True, timeout=600, cwd=str(HERE))
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def t7() -> None:
    grupo("T7", "desempenho: 6000 paragrafos x 3 runs (18000 runs), processo isolado")
    arq = SAIDAS / "perf_6000x3.docx"
    w = _subproc("escrever", arq)
    r = _subproc("ler", arq)
    checa(w["s"] <= META_TEMPO_S, f"gravar em {w['s']} s (meta <= {META_TEMPO_S:.0f} s)")
    checa(r["s"] <= META_TEMPO_S, f"ler em {r['s']} s (meta <= {META_TEMPO_S:.0f} s)")
    checa(w["hash"] == r["hash"] and r["avisos"] == [],
          f"modelo lido igual ao gravado (hash {w['hash']}), sem avisos")
    with zipfile.ZipFile(arq) as z:
        info = z.getinfo("word/document.xml")
        razao = round(info.file_size / info.compress_size, 1)
    medida("gravar_s", w["s"])
    medida("ler_s", r["s"])
    medida("pico_gravar_mb", w["pico_mb"])
    medida("pico_ler_mb", r["pico_mb"])
    medida("rss_base_mb", w["rss_base_mb"])
    medida("bytes_docx", w["bytes"])
    medida("razao_compressao_document_xml", razao)
    print(f"  INFO  RSS base {w['rss_base_mb']} MB; pico gravar {w['pico_mb']} MB "
          f"(antes {w['rss_antes_mb']}); pico ler {r['pico_mb']} MB (antes {r['rss_antes_mb']}); "
          f"document.xml comprime {razao}x")


# ----------------------------------------------------------------- T8

def t8() -> None:
    grupo("T8", "idempotencia: ida, volta e segunda ida")
    doc = fixture()
    doc = dataclasses.replace(doc, criado_em=None, modificado_em=None)
    b1 = escritor.escrever_docx(doc)
    d1, _ = leitor.ler_docx(b1)
    b2 = escritor.escrever_docx(d1)
    d2, _ = leitor.ler_docx(b2)
    checa(d1 == d2, "segunda ida produz o mesmo modelo")
    checa(b1 == b2, f"segunda gravacao byte a byte igual a primeira ({len(b1)} bytes)")
    (SAIDAS / "t8_ida1.docx").write_bytes(b1)
    (SAIDAS / "t8_ida2.docx").write_bytes(b2)
    medida("modelo_igual", d1 == d2)
    medida("bytes_iguais", b1 == b2)


# ----------------------------------------------------------------- main

def main() -> int:
    global SAIDAS
    ap = argparse.ArgumentParser()
    ap.add_argument("--perf", nargs=2, metavar=("FASE", "ARQUIVO"))
    ap.add_argument("--sabotar", choices=["sem_xml_space"])
    args = ap.parse_args()
    if args.perf:
        _modo_perf(*args.perf)
        return 0

    sabotado = args.sabotar is not None
    SAIDAS = SAIDAS_BASE / ("sabotado" if sabotado else "")
    SAIDAS.mkdir(parents=True, exist_ok=True)
    patch = None
    if args.sabotar == "sem_xml_space":
        patch = mock.patch.object(escritor, "_marcar_espaco", lambda t, texto: None)
        patch.start()
        print("MODO SABOTAGEM: escritor grava w:t sem xml:space")

    t0 = time.perf_counter()
    for f in (t1, t2, lambda: t3(sabotado), t4, t5, t6, t7, t8):
        try:
            f()
        except Exception as e:  # um teste quebrado nao pode esconder os outros
            print(f"  FALHA excecao inesperada: {type(e).__name__}: {e}")
            RES[_G]["falha"] += 1
    if patch:
        patch.stop()

    total_ok = sum(v["ok"] for v in RES.values())
    total_falha = sum(v["falha"] for v in RES.values())
    print("\n=== RESUMO")
    for k, v in RES.items():
        status = "PASSA" if v["falha"] == 0 else "FALHA"
        print(f"  {k} {status:5} ok={v['ok']} falha={v['falha']}  {v['titulo']}")
    print(f"\nTOTAL: {total_ok} OK, {total_falha} FALHA  (suite em {time.perf_counter() - t0:.1f} s)")
    (SAIDAS / "resumo.json").write_text(json.dumps(RES, ensure_ascii=False, indent=2, default=str),
                                        encoding="utf-8")
    print(f"resumo: {SAIDAS / 'resumo.json'}")
    return 0 if total_falha == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
