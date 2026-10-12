"""Modelo -> bytes de .docx, com lxml e zipfile. Sem Qt.

O pacote tem o minimo que o Word aceita: Content_Types, relacoes, document,
styles, numbering, settings, core e app. A saida e' determinista (datas de zip
fixas), e cada gravacao passa pelo validador de `ordem` antes de sair: um
arquivo que o validador reprova nao e' devolvido.

Listas: marcadores usam sempre o numero 1. Cada grupo contiguo de numeracao
ganha um numero proprio, com reinicio em 1, para que duas listas separadas
nao continuem a contagem uma da outra.

Tabelas (M4): todas usam o estilo "Table Grid" (espacamento zero dentro da
celula, como o Word faz) e gravam os seis lados da borda de forma explicita, de
modo que o estilo nao muda a aparencia. Celula sempre termina em paragrafo, e o
corpo nao termina em tabela: o Word repara o arquivo que nao segue isso.

Imagens (M4): cada imagem distinta (por conteudo) vira uma parte em word/media,
com os bytes originais, uma relacao e um tipo de conteudo por extensao.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import io
import re
import zipfile

from lxml import etree

from editdoc.formato_docx import ordem
from editdoc.formato_docx.avisos import Aviso, Coletor
from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.padroes import (ESPACO_DEPOIS_PADRAO_TW, FONTE_PADRAO, LINHA_PADRAO,
                                         TAMANHO_PADRAO_MEIO_PT)
from editdoc.formato_docx.nomes import (A_NS, CP, CT_APP, CT_CONFIG, CT_CORE, CT_DOCUMENTO,
                                        CT_ESTILOS, CT_NUMERACAO, CT_RELS, CT_XML, DC,
                                        DCT, EP, PIC_NS, PKG_CT, PKG_REL, R_NS, RT, RT_CORE,
                                        RT_IMAGEM, URI_IMAGEM, W, WP_NS, XML_NS, XSI, q)
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.documento import (Bloco, Borda, Celula, Documento, Imagem, Paragrafo, Run,
                                      Tabela, bordas_padrao)

_JC = {"esquerda": "left", "centro": "center", "direita": "right", "justificado": "both"}
_JC_TABELA = {"esquerda": "left", "centro": "center", "direita": "right"}
_VALIGN = {"topo": "top", "centro": "center", "base": "bottom"}
_ESTILO_BORDA = {"simples": "single", "dupla": "double", "pontilhada": "dotted",
                 "tracejada": "dashed", "nenhuma": "nil"}
#: Estilo de tabela que toda tabela usa (o "Table Grid" do Word).
ESTILO_TABELA = "TableGrid"
#: Controles invalidos em XML 1.0, surrogates soltos, noncharacters e o caractere de
#: objeto (U+FFFC), que so' tem sentido num run de imagem.
_CONTROLE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffc\ufffe\uffff\ud800-\udfff]")
#: Tab e quebra de linha viram elementos; U+2028 (separador de linha do Qt) vira quebra.
_SEPARADORES = re.compile("(\t|\n|\u2028)")
_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_ZIP_DATA = (1980, 1, 1, 0, 0, 0)  # data fixa: saida igual entre gravacoes
_VERT = {"subscrito": "subscript", "sobrescrito": "superscript"}



def _agora_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _xml(raiz) -> bytes:
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)


class _Listas:
    """Numeros de lista: 1 para marcadores; um novo por grupo de numeracao."""

    def __init__(self) -> None:
        self._proximo = 2
        self._ultimo: str | None = None
        self._atual = 1
        self.numeracoes = 0  # quantos numIds de numeracao foram criados

    def numero(self, tipo: str) -> int:
        if tipo == "marcadores":
            self._ultimo = None
            return 1
        if self._ultimo != "numeracao":
            self._atual = self._proximo
            self._proximo += 1
            self.numeracoes += 1
        self._ultimo = "numeracao"
        return self._atual

    def encerrar(self) -> None:
        self._ultimo = None


def texto_gravavel(texto: str) -> tuple[str, int]:
    """Texto como vai para o arquivo: fim de linha normalizado, controles removidos.

    Devolve (texto, quantos caracteres de controle sairam). Quem confere o arquivo
    gravado usa a mesma funcao, para comparar o que e' comparavel.
    """
    limpo = texto.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROLE.subn("", limpo)


def _conteudo_run(r, texto: str, coletor: Coletor) -> None:
    limpo, n = texto_gravavel(texto)
    if n:
        coletor.somar("CONTROLE_REMOVIDO", n)
    for parte in _SEPARADORES.split(limpo):
        if parte == "":
            continue
        if parte == "\t":
            etree.SubElement(r, q("tab"))
        elif parte in ("\n", " "):
            etree.SubElement(r, q("br"))
        else:
            t = etree.SubElement(r, q("t"))
            if parte != parte.strip():
                t.set("{%s}space" % XML_NS, "preserve")
            t.text = parte


def _rpr(run: Run) -> etree._Element | None:
    rpr = etree.Element(q("rPr"))
    if run.fonte:
        rf = etree.SubElement(rpr, q("rFonts"))
        for atr in ("ascii", "hAnsi", "eastAsia", "cs"):
            rf.set(q(atr), run.fonte)
    if run.negrito is not None:
        b = etree.SubElement(rpr, q("b"))
        if not run.negrito:
            b.set(q("val"), "0")
    if run.italico is not None:
        i = etree.SubElement(rpr, q("i"))
        if not run.italico:
            i.set(q("val"), "0")
    if run.tachado is not None:
        s = etree.SubElement(rpr, q("strike"))
        if not run.tachado:
            s.set(q("val"), "0")
    if run.cor_hex is not None:
        if not _HEX6.fullmatch(run.cor_hex):
            raise ValueError(f"cor_hex invalida: {run.cor_hex!r}")
        etree.SubElement(rpr, q("color")).set(q("val"), run.cor_hex.upper())
    if run.tamanho_meio_pt is not None:
        valor = str(int(run.tamanho_meio_pt))
        etree.SubElement(rpr, q("sz")).set(q("val"), valor)
        etree.SubElement(rpr, q("szCs")).set(q("val"), valor)
    if run.sublinhado is not None:
        etree.SubElement(rpr, q("u")).set(q("val"), "single" if run.sublinhado else "none")
    alinhamento = None
    if run.subscrito:
        alinhamento = _VERT["subscrito"]
    elif run.sobrescrito:
        alinhamento = _VERT["sobrescrito"]
    elif run.subscrito is False or run.sobrescrito is False:
        alinhamento = "baseline"
    if alinhamento:
        etree.SubElement(rpr, q("vertAlign")).set(q("val"), alinhamento)
    if not len(rpr):
        return None
    ordem.ordenar_filhos(rpr, ordem.ORDEM_RPR)
    return rpr


class _Midias:
    """Imagens do documento: uma parte por conteudo distinto, com a sua relacao."""

    PRIMEIRO_RID = 4  # rId1 a rId3: estilos, configuracoes e numeracao

    def __init__(self) -> None:
        self._por_hash: dict[str, tuple[str, str]] = {}  # sha256 -> (rId, parte)
        self.partes: list[tuple[str, bytes]] = []
        self.relacoes: list[tuple[str, str, str]] = []
        self.extensoes: set[str] = set()
        self._proximo_id_desenho = 1

    def registrar(self, imagem: Imagem) -> tuple[str, str]:
        chave = hashlib.sha256(imagem.dados).hexdigest()
        if chave not in self._por_hash:
            extensao, _tipo = mod_imagem.FORMATOS[imagem.formato]
            n = len(self._por_hash) + 1
            rid = f"rId{self.PRIMEIRO_RID + n - 1}"
            parte = f"word/media/image{n}.{extensao}"
            self._por_hash[chave] = (rid, parte)
            self.partes.append((parte, imagem.dados))
            self.relacoes.append((rid, RT_IMAGEM, f"media/image{n}.{extensao}"))
            self.extensoes.add(extensao)
        return self._por_hash[chave]

    def id_de_desenho(self) -> int:
        n = self._proximo_id_desenho
        self._proximo_id_desenho += 1
        return n


class _Ctx:
    def __init__(self, coletor: Coletor) -> None:
        self.coletor = coletor
        self.listas = _Listas()
        self.midias = _Midias()


def _desenho(r, imagem: Imagem, ctx: _Ctx) -> None:
    """w:drawing/wp:inline com a figura, na ordem do esquema (a mesma do Word)."""
    if imagem.formato not in mod_imagem.FORMATOS:
        raise ValueError(f"formato de imagem invalido: {imagem.formato!r}")
    rid, parte = ctx.midias.registrar(imagem)
    ident = ctx.midias.id_de_desenho()
    cx, cy = str(int(imagem.largura_emu)), str(int(imagem.altura_emu))
    wp = lambda nome: "{%s}%s" % (WP_NS, nome)  # noqa: E731
    a = lambda nome: "{%s}%s" % (A_NS, nome)  # noqa: E731
    pic = lambda nome: "{%s}%s" % (PIC_NS, nome)  # noqa: E731
    desenho = etree.SubElement(r, q("drawing"))
    inline = etree.SubElement(desenho, wp("inline"), distT="0", distB="0", distL="0", distR="0")
    etree.SubElement(inline, wp("extent"), cx=cx, cy=cy)
    etree.SubElement(inline, wp("effectExtent"), l="0", t="0", r="0", b="0")
    doc_pr = etree.SubElement(inline, wp("docPr"), id=str(ident), name=f"Imagem {ident}")
    if imagem.descricao:
        limpo, _n = texto_gravavel(imagem.descricao)
        doc_pr.set("descr", limpo)
    quadro = etree.SubElement(inline, wp("cNvGraphicFramePr"))
    etree.SubElement(quadro, a("graphicFrameLocks"), noChangeAspect="1")
    grafico = etree.SubElement(inline, a("graphic"))
    dados = etree.SubElement(grafico, a("graphicData"), uri=URI_IMAGEM)
    figura = etree.SubElement(dados, pic("pic"))
    nv = etree.SubElement(figura, pic("nvPicPr"))
    etree.SubElement(nv, pic("cNvPr"), id="0", name=parte.rsplit("/", 1)[1])
    etree.SubElement(nv, pic("cNvPicPr"))
    preenchimento = etree.SubElement(figura, pic("blipFill"))
    etree.SubElement(preenchimento, a("blip")).set("{%s}embed" % R_NS, rid)
    esticar = etree.SubElement(preenchimento, a("stretch"))
    etree.SubElement(esticar, a("fillRect"))
    sp = etree.SubElement(figura, pic("spPr"))
    xfrm = etree.SubElement(sp, a("xfrm"))
    etree.SubElement(xfrm, a("off"), x="0", y="0")
    etree.SubElement(xfrm, a("ext"), cx=cx, cy=cy)
    geom = etree.SubElement(sp, a("prstGeom"), prst="rect")
    etree.SubElement(geom, a("avLst"))


def _paragrafo(body, p: Paragrafo, ctx: _Ctx) -> None:
    listas, coletor = ctx.listas, ctx.coletor
    pe = etree.SubElement(body, q("p"))
    ppr = etree.Element(q("pPr"))
    if p.numeracao is not None:
        num = etree.SubElement(ppr, q("numPr"))
        etree.SubElement(num, q("ilvl")).set(q("val"), "0")
        etree.SubElement(num, q("numId")).set(q("val"), str(listas.numero(p.numeracao)))
    else:
        listas.encerrar()
    if p.alinhamento is not None:
        etree.SubElement(ppr, q("jc")).set(q("val"), _JC[p.alinhamento])
    if p.recuo_esquerdo_tw is not None or p.recuo_primeira_linha_tw is not None:
        ind = etree.SubElement(ppr, q("ind"))
        if p.recuo_esquerdo_tw is not None:
            ind.set(q("left"), str(int(p.recuo_esquerdo_tw)))
        if p.recuo_primeira_linha_tw is not None:
            v = int(p.recuo_primeira_linha_tw)
            if v >= 0:
                ind.set(q("firstLine"), str(v))
            else:
                ind.set(q("hanging"), str(-v))
    if (p.espaco_antes_tw is not None or p.espaco_depois_tw is not None
            or p.espacamento_linha_pct is not None):
        sp = etree.SubElement(ppr, q("spacing"))
        if p.espaco_antes_tw is not None:
            sp.set(q("before"), str(int(p.espaco_antes_tw)))
        if p.espaco_depois_tw is not None:
            sp.set(q("after"), str(int(p.espaco_depois_tw)))
        if p.espacamento_linha_pct is not None:
            sp.set(q("line"), str(round(int(p.espacamento_linha_pct) * 240 / 100)))
            sp.set(q("lineRule"), "auto")
    if len(ppr):
        ordem.ordenar_filhos(ppr, ordem.ORDEM_PPR)
        pe.append(ppr)
    if p.quebra_antes:
        # Quebra de pagina: o paragrafo comeca no topo da proxima pagina.
        r_quebra = etree.SubElement(pe, q("r"))
        etree.SubElement(r_quebra, q("br")).set(q("type"), "page")
    for run in p.runs:
        if run.imagem is not None:
            r = etree.SubElement(pe, q("r"))
            _desenho(r, run.imagem, ctx)
            continue
        if run.texto == "":
            continue
        r = etree.SubElement(pe, q("r"))
        rpr = _rpr(run)
        if rpr is not None:
            r.append(rpr)
        _conteudo_run(r, run.texto, coletor)


def _borda_xml(pai, nome: str, borda: Borda) -> None:
    el = etree.SubElement(pai, q(nome))
    el.set(q("val"), _ESTILO_BORDA[borda.estilo])
    if borda.estilo == "nenhuma":
        return
    el.set(q("sz"), str(min(max(int(borda.oitavos_pt), 2), 96)))
    el.set(q("space"), "0")
    if borda.cor_hex is not None:
        if not _HEX6.fullmatch(borda.cor_hex):
            raise ValueError(f"cor de borda invalida: {borda.cor_hex!r}")
        el.set(q("color"), borda.cor_hex.upper())
    else:
        el.set(q("color"), "auto")


def _tabela(pai, tabela: Tabela, ctx: _Ctx) -> None:
    tbl = etree.SubElement(pai, q("tbl"))
    tbl_pr = etree.SubElement(tbl, q("tblPr"))
    etree.SubElement(tbl_pr, q("tblStyle")).set(q("val"), ESTILO_TABELA)
    largura = tabela.largura or ("auto", 0)
    tw = etree.SubElement(tbl_pr, q("tblW"))
    tw.set(q("w"), str(int(largura[1])))
    tw.set(q("type"), largura[0])
    if tabela.alinhamento is not None:
        etree.SubElement(tbl_pr, q("jc")).set(q("val"), _JC_TABELA[tabela.alinhamento])
    if tabela.recuo_tw is not None:
        ind = etree.SubElement(tbl_pr, q("tblInd"))
        ind.set(q("w"), str(int(tabela.recuo_tw)))
        ind.set(q("type"), "dxa")
    bordas = tabela.bordas or bordas_padrao()
    tb = etree.SubElement(tbl_pr, q("tblBorders"))
    for nome, campo in (("top", "sup"), ("left", "esq"), ("bottom", "inf"), ("right", "dir"),
                        ("insideH", "horizontal"), ("insideV", "vertical")):
        _borda_xml(tb, nome, getattr(bordas, campo) or Borda(estilo="nenhuma"))
    if tabela.layout_fixo:
        etree.SubElement(tbl_pr, q("tblLayout")).set(q("type"), "fixed")
    if tabela.margens_celula_tw is not None:
        mar = etree.SubElement(tbl_pr, q("tblCellMar"))
        for nome, valor in zip(("top", "left", "bottom", "right"), tabela.margens_celula_tw):
            m = etree.SubElement(mar, q(nome))
            m.set(q("w"), str(int(valor)))
            m.set(q("type"), "dxa")
    ordem.ordenar_filhos(tbl_pr, ordem.ORDEM_TBLPR)
    grade = etree.SubElement(tbl, q("tblGrid"))
    for w in tabela.colunas_tw:
        etree.SubElement(grade, q("gridCol")).set(q("w"), str(int(w)))
    for linha in tabela.linhas:
        tr = etree.SubElement(tbl, q("tr"))
        tr_pr = etree.Element(q("trPr"))
        if linha.altura_tw is not None:
            h = etree.SubElement(tr_pr, q("trHeight"))
            h.set(q("val"), str(int(linha.altura_tw)))
            h.set(q("hRule"), "exact" if linha.altura_exata else "atLeast")
        if linha.cabecalho:
            etree.SubElement(tr_pr, q("tblHeader"))
        if len(tr_pr):
            tr.append(tr_pr)
        coluna = 0
        for celula in linha.celulas:
            span = max(1, int(celula.colunas))
            largura_celula = sum(tabela.colunas_tw[coluna:coluna + span])
            coluna += span
            _celula(tr, celula, span, largura_celula, ctx)


def _celula(tr, celula: Celula, span: int, largura: int, ctx: _Ctx) -> None:
    tc = etree.SubElement(tr, q("tc"))
    tc_pr = etree.SubElement(tc, q("tcPr"))
    tcw = etree.SubElement(tc_pr, q("tcW"))
    tcw.set(q("w"), str(int(largura)))
    tcw.set(q("type"), "dxa")
    if span > 1:
        etree.SubElement(tc_pr, q("gridSpan")).set(q("val"), str(span))
    if celula.mescla_vertical == "inicio":
        etree.SubElement(tc_pr, q("vMerge")).set(q("val"), "restart")
    elif celula.mescla_vertical == "continua":
        etree.SubElement(tc_pr, q("vMerge"))
    if celula.bordas is not None:
        lados = [(n, getattr(celula.bordas, c)) for n, c in
                 (("top", "sup"), ("left", "esq"), ("bottom", "inf"), ("right", "dir"))]
        lados = [(n, b) for n, b in lados if b is not None]
        if lados:
            cb = etree.SubElement(tc_pr, q("tcBorders"))
            for nome, borda in lados:
                _borda_xml(cb, nome, borda)
    if celula.sombreamento_hex is not None:
        if not _HEX6.fullmatch(celula.sombreamento_hex):
            raise ValueError(f"sombreamento invalido: {celula.sombreamento_hex!r}")
        shd = etree.SubElement(tc_pr, q("shd"))
        shd.set(q("val"), "clear")
        shd.set(q("color"), "auto")
        shd.set(q("fill"), celula.sombreamento_hex.upper())
    if celula.alinhamento_vertical is not None:
        etree.SubElement(tc_pr, q("vAlign")).set(q("val"), _VALIGN[celula.alinhamento_vertical])
    ordem.ordenar_filhos(tc_pr, ordem.ORDEM_TCPR)
    _blocos(tc, celula.blocos, ctx, em_celula=True)


def _blocos(pai, blocos: list[Bloco], ctx: _Ctx, em_celula: bool) -> None:
    """Paragrafos e tabelas, na ordem. Celula e corpo terminam em paragrafo (o Word exige)."""
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            ctx.listas.encerrar()
            _tabela(pai, bloco, ctx)
        else:
            _paragrafo(pai, bloco, ctx)
    if not blocos or isinstance(blocos[-1], Tabela):
        if em_celula or blocos:
            etree.SubElement(pai, q("p"))


def _document_xml(doc: Documento, ctx: _Ctx) -> bytes:
    raiz = etree.Element(q("document"), nsmap={"w": W, "r": R_NS, "wp": WP_NS, "a": A_NS,
                                               "pic": PIC_NS})
    body = etree.SubElement(raiz, q("body"))
    _blocos(body, doc.paragrafos, ctx, em_celula=False)
    if not doc.paragrafos:
        etree.SubElement(body, q("p"))  # o Word exige ao menos um paragrafo
    pagina = doc.pagina
    sect = etree.SubElement(body, q("sectPr"))
    pg = etree.SubElement(sect, q("pgSz"))
    pg.set(q("w"), str(pagina.largura_tw))
    pg.set(q("h"), str(pagina.altura_tw))
    if pagina.paisagem:
        pg.set(q("orient"), "landscape")
    mar = etree.SubElement(sect, q("pgMar"))
    for nome, valor in (
            ("top", pagina.margem_sup_tw), ("right", pagina.margem_dir_tw),
            ("bottom", pagina.margem_inf_tw), ("left", pagina.margem_esq_tw),
            ("header", pagina.cabecalho_tw), ("footer", pagina.rodape_tw),
            ("gutter", pagina.medianiz_tw)):
        mar.set(q(nome), str(valor))
    return _xml(raiz)


def _styles_xml() -> bytes:
    raiz = etree.Element(q("styles"), nsmap={"w": W})
    dd = etree.SubElement(raiz, q("docDefaults"))
    rpd = etree.SubElement(dd, q("rPrDefault"))
    rpr = etree.SubElement(rpd, q("rPr"))
    rf = etree.SubElement(rpr, q("rFonts"))
    for atr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rf.set(q(atr), FONTE_PADRAO)
    etree.SubElement(rpr, q("sz")).set(q("val"), str(TAMANHO_PADRAO_MEIO_PT))
    etree.SubElement(rpr, q("szCs")).set(q("val"), str(TAMANHO_PADRAO_MEIO_PT))
    lang = etree.SubElement(rpr, q("lang"))
    lang.set(q("val"), "pt-BR")
    lang.set(q("eastAsia"), "pt-BR")
    lang.set(q("bidi"), "ar-SA")
    ppd = etree.SubElement(dd, q("pPrDefault"))
    sp = etree.SubElement(etree.SubElement(ppd, q("pPr")), q("spacing"))
    sp.set(q("after"), str(ESPACO_DEPOIS_PADRAO_TW))
    sp.set(q("line"), str(LINHA_PADRAO))
    sp.set(q("lineRule"), "auto")

    def estilo(tipo, sid, nome, extra=(), padrao=True):
        s = etree.SubElement(raiz, q("style"))
        s.set(q("type"), tipo)
        if padrao:
            s.set(q("default"), "1")
        s.set(q("styleId"), sid)
        etree.SubElement(s, q("name")).set(q("val"), nome)
        for tag, val in extra:
            el = etree.SubElement(s, q(tag))
            if val is not None:
                el.set(q("val"), val)
        return s

    estilo("paragraph", "Normal", "Normal", extra=[("qFormat", None)])
    estilo("character", "DefaultParagraphFont", "Default Paragraph Font",
           extra=[("uiPriority", "1"), ("semiHidden", None), ("unhideWhenUsed", None)])
    tbl = estilo("table", "TableNormal", "Normal Table",
                 extra=[("uiPriority", "99"), ("semiHidden", None), ("unhideWhenUsed", None)])
    tp = etree.SubElement(tbl, q("tblPr"))
    ti = etree.SubElement(tp, q("tblInd"))
    ti.set(q("w"), "0")
    ti.set(q("type"), "dxa")
    cm = etree.SubElement(tp, q("tblCellMar"))
    for lado, val in (("top", "0"), ("left", "108"), ("bottom", "0"), ("right", "108")):
        el = etree.SubElement(cm, q(lado))
        el.set(q("w"), val)
        el.set(q("type"), "dxa")
    estilo("numbering", "NoList", "No List",
           extra=[("uiPriority", "99"), ("semiHidden", None), ("unhideWhenUsed", None)])
    # "Table Grid": o estilo que o Word da' a tabela nova. Zera o espacamento dos
    # paragrafos dentro da celula (o padrao do documento tem 8 pt depois). As bordas
    # de cada tabela sao gravadas nela mesma; as daqui valem so' de referencia.
    grade = estilo("table", ESTILO_TABELA, "Table Grid",
                   extra=[("basedOn", "TableNormal"), ("uiPriority", "39")], padrao=False)
    gp = etree.SubElement(grade, q("pPr"))
    gsp = etree.SubElement(gp, q("spacing"))
    gsp.set(q("after"), "0")
    gsp.set(q("line"), "240")
    gsp.set(q("lineRule"), "auto")
    gt = etree.SubElement(grade, q("tblPr"))
    gb = etree.SubElement(gt, q("tblBorders"))
    for nome in ("top", "left", "bottom", "right", "insideH", "insideV"):
        _borda_xml(gb, nome, Borda())
    return _xml(raiz)


def _numbering_xml(numeracoes: int) -> bytes:
    raiz = etree.Element(q("numbering"), nsmap={"w": W})

    def abstrato(ident: int, formato: str, texto: str) -> None:
        a = etree.SubElement(raiz, q("abstractNum"))
        a.set(q("abstractNumId"), str(ident))
        etree.SubElement(a, q("multiLevelType")).set(q("val"), "singleLevel")
        lvl = etree.SubElement(a, q("lvl"))
        lvl.set(q("ilvl"), "0")
        etree.SubElement(lvl, q("start")).set(q("val"), "1")
        etree.SubElement(lvl, q("numFmt")).set(q("val"), formato)
        etree.SubElement(lvl, q("lvlText")).set(q("val"), texto)
        etree.SubElement(lvl, q("lvlJc")).set(q("val"), "left")
        ppr = etree.SubElement(lvl, q("pPr"))
        ind = etree.SubElement(ppr, q("ind"))
        ind.set(q("left"), "720")
        ind.set(q("hanging"), "360")
        rpr = etree.SubElement(lvl, q("rPr"))
        rf = etree.SubElement(rpr, q("rFonts"))
        rf.set(q("ascii"), "Calibri")
        rf.set(q("hAnsi"), "Calibri")

    abstrato(0, "bullet", "•")
    abstrato(1, "decimal", "%1.")
    num = etree.SubElement(raiz, q("num"))
    num.set(q("numId"), "1")
    etree.SubElement(num, q("abstractNumId")).set(q("val"), "0")
    for ident in range(2, 2 + numeracoes):
        num = etree.SubElement(raiz, q("num"))
        num.set(q("numId"), str(ident))
        etree.SubElement(num, q("abstractNumId")).set(q("val"), "1")
        sobre = etree.SubElement(num, q("lvlOverride"))
        sobre.set(q("ilvl"), "0")
        etree.SubElement(sobre, q("startOverride")).set(q("val"), "1")
    return _xml(raiz)


def _settings_xml() -> bytes:
    raiz = etree.Element(q("settings"), nsmap={"w": W})
    etree.SubElement(raiz, q("zoom")).set(q("percent"), "100")
    etree.SubElement(raiz, q("defaultTabStop")).set(q("val"), "708")
    etree.SubElement(raiz, q("characterSpacingControl")).set(q("val"), "doNotCompress")
    compat = etree.SubElement(raiz, q("compat"))
    cs = etree.SubElement(compat, q("compatSetting"))
    cs.set(q("name"), "compatibilityMode")
    cs.set(q("uri"), "http://schemas.microsoft.com/office/word")
    cs.set(q("val"), "15")
    etree.SubElement(raiz, q("themeFontLang")).set(q("val"), "pt-BR")
    return _xml(raiz)


def _core_xml(doc: Documento, criado: str, modificado: str) -> bytes:
    raiz = etree.Element("{%s}coreProperties" % CP,
                         nsmap={"cp": CP, "dc": DC, "dcterms": DCT, "xsi": XSI})
    if doc.titulo:
        etree.SubElement(raiz, "{%s}title" % DC).text = doc.titulo
    if doc.autor:
        etree.SubElement(raiz, "{%s}creator" % DC).text = doc.autor
    for tag, valor in (("created", criado), ("modified", modificado)):
        el = etree.SubElement(raiz, "{%s}%s" % (DCT, tag))
        el.set("{%s}type" % XSI, "dcterms:W3CDTF")
        el.text = valor
    return _xml(raiz)


def _app_xml() -> bytes:
    raiz = etree.Element("{%s}Properties" % EP, nsmap={None: EP})
    etree.SubElement(raiz, "{%s}Application" % EP).text = "EditDoc"
    return _xml(raiz)


def _content_types_xml(extensoes_de_imagem: set[str] = frozenset()) -> bytes:
    raiz = etree.Element("{%s}Types" % PKG_CT, nsmap={None: PKG_CT})
    etree.SubElement(raiz, "{%s}Default" % PKG_CT, Extension="rels", ContentType=CT_RELS)
    etree.SubElement(raiz, "{%s}Default" % PKG_CT, Extension="xml", ContentType=CT_XML)
    for formato, (extensao, tipo) in mod_imagem.FORMATOS.items():
        if extensao in extensoes_de_imagem:
            etree.SubElement(raiz, "{%s}Default" % PKG_CT, Extension=extensao, ContentType=tipo)
    overrides = {
        "/word/document.xml": CT_DOCUMENTO,
        "/word/styles.xml": CT_ESTILOS,
        "/word/numbering.xml": CT_NUMERACAO,
        "/word/settings.xml": CT_CONFIG,
        "/docProps/core.xml": CT_CORE,
        "/docProps/app.xml": CT_APP,
    }
    for parte, tipo in overrides.items():
        etree.SubElement(raiz, "{%s}Override" % PKG_CT, PartName=parte, ContentType=tipo)
    return _xml(raiz)


def _rels_xml(itens: list[tuple[str, str, str]]) -> bytes:
    raiz = etree.Element("{%s}Relationships" % PKG_REL, nsmap={None: PKG_REL})
    for rid, tipo, alvo in itens:
        etree.SubElement(raiz, "{%s}Relationship" % PKG_REL, Id=rid, Type=tipo, Target=alvo)
    return _xml(raiz)


def _zip(partes: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for nome, dados in partes:
            info = zipfile.ZipInfo(nome, date_time=_ZIP_DATA)
            # Imagem ja vem comprimida (PNG, JPEG, GIF): comprimir de novo so' gasta tempo.
            midia_comprimida = nome.startswith("word/media/") and not nome.endswith(".bmp")
            info.compress_type = zipfile.ZIP_STORED if midia_comprimida else zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            z.writestr(info, dados)
    return buf.getvalue()


def escrever_com_avisos(doc: Documento) -> tuple[bytes, list[Aviso]]:
    """Devolve (bytes do .docx, avisos da gravacao). Levanta ErroDocx se o validador reprovar."""
    coletor = Coletor()
    ctx = _Ctx(coletor)
    agora = _agora_iso()
    criado = doc.criado_em or agora
    modificado = doc.modificado_em or agora
    documento_xml = _document_xml(doc, ctx)
    partes = [
        ("[Content_Types].xml", _content_types_xml(ctx.midias.extensoes)),
        ("_rels/.rels", _rels_xml([
            ("rId1", RT + "officeDocument", "word/document.xml"),
            ("rId2", RT_CORE, "docProps/core.xml"),
            ("rId3", RT + "extended-properties", "docProps/app.xml"),
        ])),
        ("word/document.xml", documento_xml),
        ("word/_rels/document.xml.rels", _rels_xml([
            ("rId1", RT + "styles", "styles.xml"),
            ("rId2", RT + "settings", "settings.xml"),
            ("rId3", RT + "numbering", "numbering.xml"),
            *ctx.midias.relacoes,
        ])),
        ("word/styles.xml", _styles_xml()),
        ("word/numbering.xml", _numbering_xml(ctx.listas.numeracoes)),
        ("word/settings.xml", _settings_xml()),
        ("docProps/core.xml", _core_xml(doc, criado, modificado)),
        ("docProps/app.xml", _app_xml()),
        *ctx.midias.partes,
    ]
    mapa = dict(partes)
    problemas = ordem.validar(mapa)
    if problemas:
        raise ErroDocx("ESCRITA_INVALIDA", "; ".join(problemas[:3]))
    return _zip(partes), coletor.avisos()


def escrever(doc: Documento) -> bytes:
    return escrever_com_avisos(doc)[0]
