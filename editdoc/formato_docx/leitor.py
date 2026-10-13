"""Bytes ou caminho de .docx -> (Documento, avisos). Sem Qt.

Ordem das defesas: entrada, formato antigo (OLE), pacote ZIP (contagem, nomes,
criptografia, metodo, tamanho declarado, razao de compressao, total), DOCTYPE
recusado antes do parse, codificacao UTF-8 so', lxml sem entidades externas, sem
rede, sem DTD e com profundidade limitada. Toda falha vira `ErroDocx` com codigo.

O que o programa nao modela NAO e' descartado em silencio: vira aviso (ver
`avisos.py`). Tabelas (M4) viram `Tabela`; a que passa dos limites, ou esta'
aninhada fundo demais, vira paragrafos com aviso. Imagens na linha (PNG, JPEG,
GIF, BMP) viram `Imagem` com os bytes originais. Caixa de texto, forma, grafico,
SmartArt, OLE, equacao, imagem flutuante e imagem de outro formato (0.1.2) viram
objeto opaco (`opacos.py`), que volta igual ao arquivo, com aviso sem perda. Campos
PAGE e NUMPAGES (M5) viram um `Run` com `campo`; os outros viram o texto que o Word
mostra, com aviso. Revisoes aceitas; exclusoes e controles de conteudo tem aviso.

Cabecalho e rodape (M5): os da ultima secao, com a heranca do Word (a secao sem
referencia herda a da anterior). Cada parte passa pelos mesmos limites do pacote e
mais um, de tamanho (`cabecalho_bytes`). Campo aninhado fundo demais
(`campo_profundidade`) nao e' interpretado: o texto fica, com aviso.

Estilos (M6): o styles.xml vira o catalogo (`formato_docx/estilos.py`), guardado no
Documento com o XML original. w:pStyle e w:rStyle viram `Paragrafo.estilo` e
`Run.estilo`; a formatacao lida no paragrafo e no run continua sendo so' a direta. A
lista que vem do estilo (numPr dentro do estilo) passa para o paragrafo. Referencia a
estilo que nao existe vira o aviso ESTILO.
"""

from __future__ import annotations

import io
import os
import posixpath
import re
import zipfile
from dataclasses import replace

from lxml import etree

from editdoc.formato_docx import estilos as fx_estilos
from editdoc.formato_docx import opacos
from editdoc.formato_docx.avisos import Aviso, Coletor
from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.nomes import (A_NS, CP, CT_DOCUMENTO_MACRO, DC, DCT, MATH_NS, MC_NS,
                                        PIC_NS, PKG_CT, R_NS, RT_STRICT, URI_IMAGEM, W,
                                        W_STRICT, WP_NS, q)
from editdoc.formato_docx.ordem import caminho_dos_rels
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.campos import (FORMATOS_NUMERO, INSTRUCAO_MAXIMA, NUMERO_INICIAL_MAXIMO,
                                   normalizar_instrucao, tipo_do_campo)
from editdoc.modelo.documento import (Bloco, Borda, BordasCelula, BordasTabela, Celula,
                                      Documento, Imagem, Linha, Paragrafo, Run, Tabela,
                                      colunas_da_linha, normalizar, run_de_imagem,
                                      run_de_objeto)
from editdoc.modelo.estilos import Estilos, catalogo_padrao
from editdoc.modelo.pagina import PAPEL_MAXIMO_TW, Pagina
from editdoc.modelo.unidades import EMU_POR_PX, EMU_POR_TWIP

LIMITES_PADRAO = {
    "entradas": 5000,
    "parte_bytes": 128 * 1024 * 1024,
    "total_bytes": 512 * 1024 * 1024,
    "razao_min_bytes": 10 * 1024 * 1024,  # so checa a razao acima deste tamanho
    "razao_max": 200,
    "profundidade": 256,
    # Tabelas (M4). O Qt refaz o layout da tabela inteira a cada tecla: medido,
    # cerca de 0,06 ms por celula (5000 celulas = 300 ms por tecla). Acima disto a
    # tabela vira paragrafos, com aviso. 63 colunas e' o maximo do proprio Word.
    "tabela_linhas": 2000,
    "tabela_colunas": 63,
    "tabela_celulas": 5000,
    "tabela_profundidade": 4,
    # Cabecalho e rodape (M5): cada parte e' pintada em toda pagina; uma parte enorme
    # deixaria a rolagem lenta. Acima disto a parte nao e' lida, com aviso.
    "cabecalho_bytes": 4 * 1024 * 1024,
    # Campo dentro de campo dentro de campo...: acima disto o campo nao e' interpretado.
    "campo_profundidade": 8,
    # Objetos opacos (0.1.2): quantos, o tamanho do XML e o fecho das partes.
    **opacos.LIMITES,
}

#: Tipo do .docx (w:type de headerReference) -> tipo do modelo.
_TIPO_FAIXA = {"default": "padrao", "first": "primeira", "even": "par"}

#: Maior medida aceita para imagem e coluna: o maior papel (176 cm).
_EMU_MAXIMO = PAPEL_MAXIMO_TW * EMU_POR_TWIP
_ESTILO_BORDA = {"single": "simples", "double": "dupla", "dotted": "pontilhada",
                 "dashed": "tracejada", "none": "nenhuma", "nil": "nenhuma"}
_LADOS_TABELA = (("top", "sup"), ("left", "esq"), ("start", "esq"), ("bottom", "inf"),
                 ("right", "dir"), ("end", "dir"), ("insideH", "horizontal"),
                 ("insideV", "vertical"))
_VALIGN = {"top": "topo", "center": "centro", "bottom": "base"}
_JC_TABELA = {"left": "esquerda", "start": "esquerda", "center": "centro",
              "right": "direita", "end": "direita"}
#: Filhos de tblPr, trPr e tcPr sem efeito visivel que o modelo nao usa.
_TBLPR_NEUTRAS = {"tblLook", "tblStyleRowBandSize", "tblStyleColBandSize", "tblOverlap",
                  "tblPrChange"}
_TRPR_NEUTRAS = {"cnfStyle", "divId", "cantSplit", "wBefore", "wAfter", "trPrChange"}
_TCPR_NEUTRAS = {"cnfStyle", "tcW", "noWrap", "tcFitText", "hideMark", "tcPrChange"}

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_DOCTYPE = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY|ELEMENT|ATTLIST|NOTATION)", re.IGNORECASE)
_ENCODING = re.compile(rb"""encoding\s*=\s*["']([A-Za-z0-9._-]+)["']""")
_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_JC = {"left": "esquerda", "start": "esquerda", "center": "centro",
       "right": "direita", "end": "direita", "both": "justificado"}

#: Propriedades de paragrafo sem efeito visivel que o modelo nao usa: sao ignoradas.
_PPR_NEUTRAS = {"widowControl", "keepNext", "keepLines", "suppressAutoHyphens", "kinsoku",
                "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN",
                "adjustRightInd", "snapToGrid", "textAlignment", "divId",
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


def _onoff_atr(el, nome: str) -> bool:
    """Atributo on/off ausente = falso (ao contrario do elemento on/off)."""
    v = _atr(el, nome)
    return v is not None and v.lower() in ("1", "true", "on")


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
    def __init__(self, coletor: Coletor, numeracao: dict[str, str | None],
                 lim: dict | None = None) -> None:
        self.coletor = coletor
        #: numId -> formato do nivel 0 ("bullet", "decimal", outro ou None)
        self.numeracao = numeracao
        #: sectPr contados: os de dentro de paragrafo mais o do fim do corpo
        self.secoes = 0
        #: pagina do sectPr final, ja validada; None se nao for representavel
        self.pagina_final: Pagina | None = None
        self.lim = {**LIMITES_PADRAO, **(lim or {})}
        #: relacoes do documento principal: rId -> (tipo, alvo resolvido, externo)
        self.relacoes: dict[str, tuple[str, str, bool]] = {}
        #: le uma parte do pacote (com os limites do leitor); None fora do _ler
        self.ler_parte = None
        self.nomes: set[str] = set()
        #: alvo -> bytes, para nao ler duas vezes a mesma imagem
        self.midias: dict[str, bytes] = {}
        #: estilos de tabela: styleId -> elemento w:style; e o id do padrao
        self.estilos_tabela: dict[str, object] = {}
        self.estilo_tabela_padrao: str | None = None
        #: profundidade de tabela atual (0 = corpo)
        self.nivel_tabela = 0
        #: catalogo de estilos (M6)
        self.estilos: Estilos = catalogo_padrao()
        #: campos complexos abertos (w:fldChar begin sem end), do de fora para o de dentro
        self.campos: list[dict] = []
        #: cabecalho e rodape herdados das secoes anteriores: (onde, tipo) -> rId
        self.faixas_herdadas: dict[tuple[str, str], str] = {}
        #: referencias de cada secao anterior, para saber se diferem das da ultima
        self.faixas_das_secoes: list[dict[tuple[str, str], str]] = []
        #: objetos opacos (0.1.2): quem captura, e o mc:Ignorable da parte que se le
        self.capturador: opacos.Capturador | None = None
        self.ignoraveis: tuple = ()


# -- objetos opacos -------------------------------------------------------------

def _opaco(item, rpr, ctx: _Contexto) -> Run | None:
    """O item (desenho, VML, OLE, AlternateContent, equacao) como objeto preservado.

    None, com aviso de perda, se o objeto nao puder voltar inteiro ao arquivo.
    """
    obj = None
    if ctx.capturador is not None:
        obj = ctx.capturador.capturar(item, rpr, ctx.relacoes, ctx.ignoraveis)
    if obj is None:
        ctx.coletor.somar("IMAGEM" if opacos.classificar(item) == "imagem" else "OBJETO_PERDIDO")
        return None
    ctx.coletor.somar(opacos.codigo_do_aviso(obj.tipo, obj.flutuante))
    return run_de_objeto(obj)


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
            fonte = fx_estilos.fonte_de_rfonts(f, ctx.estilos.fontes_tema)
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
            sid = _atr(f, "val")
            estilo = ctx.estilos.obter(sid)
            if estilo is not None and estilo.tipo == "caractere":
                run.estilo = sid
            elif sid not in (None, "DefaultParagraphFont"):
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
            direito = _atr(f, "right") or _atr(f, "end")
            if direito is not None:
                out["recuo_direito_tw"] = _inteiro(direito)
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
            sid = _atr(f, "val")
            estilo = ctx.estilos.obter(sid)
            if estilo is not None and estilo.tipo == "paragrafo":
                # O estilo padrao fica None: e' o que vale sem w:pStyle.
                out["estilo"] = None if sid == ctx.estilos.id_padrao() else sid
            elif sid is not None:
                c.somar("ESTILO")
        elif loc == "outlineLvl":
            nivel = _inteiro(_atr(f, "val"))
            if nivel is not None and 0 <= nivel <= 9:
                out["nivel"] = nivel
        elif loc == "sectPr":
            c.somar("SECAO")
            ctx.secoes += 1
            _faixas_da_secao(f, ctx, final=False)
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
        if nid == "0":
            out["_sem_lista"] = True  # numId 0 desliga a lista que viria do estilo
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


class _Pedacos:
    """Texto de um w:r em montagem. Uma imagem ou um objeto no meio fecha o trecho de texto."""

    def __init__(self, base: Run, saida: list[Run], rpr=None) -> None:
        self.base = base
        self.saida = saida
        self.partes: list[str] = []
        #: o w:rPr do run, que vai junto no XML do objeto opaco
        self.rpr = rpr

    def append(self, texto: str) -> None:
        self.partes.append(texto)

    def descarregar(self) -> None:
        texto = "".join(self.partes)
        self.partes = []
        if texto:
            self.saida.append(replace(self.base, texto=texto))

    def imagem(self, imagem: Imagem) -> None:
        self.descarregar()
        self.saida.append(run_de_imagem(imagem))

    def objeto(self, item, ctx: "_Contexto") -> None:
        self.descarregar()
        run = _opaco(item, self.rpr, ctx)
        if run is not None:
            self.saida.append(run)


def _ler_run(r, ctx: _Contexto, saida: list[Run]) -> None:
    run = Run()
    rpr = r.find(q("rPr"))
    if rpr is not None:
        _ler_rpr(rpr, run, ctx)
    pedacos = _Pedacos(run, saida, rpr)
    for f in r:
        ns, loc = _local(f)
        if loc is None:
            continue
        if ns == MC_NS and loc == "AlternateContent":
            if opacos.contem_objeto(f):
                # Forma ou caixa de texto com o VML de reserva: vai inteiro (0.1.2).
                pedacos.objeto(f, ctx)
                continue
            ramo = _escolha(f)
            if ramo is not None:
                for sub in ramo:
                    _ler_item_run(sub, pedacos, ctx)
            continue
        if ns != W:
            continue
        _ler_item_run(f, pedacos, ctx)
    pedacos.descarregar()


def _ler_item_run(f, partes: _Pedacos, ctx: _Contexto) -> None:
    c = ctx.coletor
    ns, loc = _local(f)
    if loc is None or ns != W:
        return
    if loc == "rPr":
        return  # lido antes, em _ler_run
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
        _fld_char(_atr(f, "fldCharType"), partes, ctx)
    elif loc == "instrText":
        if ctx.campos and ctx.campos[-1].get("fase") == "instr":
            topo = ctx.campos[-1]
            if sum(len(x) for x in topo["instr"]) <= INSTRUCAO_MAXIMA:
                topo["instr"].append(f.text or "")
            else:
                topo["longo"] = True
    elif loc == "fldData":
        return
    elif loc == "drawing":
        imagem = _ler_desenho(f, ctx)
        if imagem is not None:
            partes.imagem(imagem)
        else:
            partes.objeto(f, ctx)
    elif loc in ("pict", "object"):
        partes.objeto(f, ctx)
    elif loc == "commentReference":
        c.somar("COMENTARIO")
    elif loc in ("footnoteReference", "endnoteReference"):
        c.somar("NOTA")
    else:
        c.somar("ELEMENTO_DESCONHECIDO")


def _fld_char(tipo: str | None, partes: _Pedacos, ctx: _Contexto) -> None:
    """Campo complexo: begin, instrText, separate, resultado, end (podem estar em runs diferentes).

    PAGE e NUMPAGES com o begin e o end no mesmo paragrafo, sem campo dentro, viram um
    run com `campo`; o texto e' o resultado (o que o Word mostrava). O resto mantem o
    resultado como texto, e o aviso CAMPO diz que o campo se perde.
    """
    partes.descarregar()
    pilha = ctx.campos
    if tipo == "begin":
        if len(pilha) >= ctx.lim["campo_profundidade"]:
            pilha.append({"ignorado": True})
            return
        if pilha:
            pilha[-1]["aninhado"] = True
        pilha.append({"fase": "instr", "instr": [], "saida": partes.saida, "base": partes.base,
                      "inicio": None, "aninhado": False})
    elif tipo == "separate":
        if pilha and not pilha[-1].get("ignorado"):
            pilha[-1]["fase"] = "resultado"
            if pilha[-1]["saida"] is partes.saida:
                pilha[-1]["inicio"] = len(partes.saida)
            else:
                pilha[-1]["aninhado"] = True  # o resultado comeca em outro paragrafo
    elif tipo == "end":
        if not pilha:
            return
        campo = pilha.pop()
        if campo.get("ignorado"):
            ctx.coletor.somar("CAMPO")
            return
        instrucao = normalizar_instrucao("".join(campo["instr"]))
        saida = partes.saida
        inicio = campo["inicio"] if campo["inicio"] is not None else len(saida)
        resultado = saida[inicio:] if campo["saida"] is saida else []
        if (tipo_do_campo(instrucao) is None or campo.get("longo") or campo["aninhado"]
                or campo["saida"] is not saida or any(r.eh_objeto() or r.campo is not None
                                                      for r in resultado)):
            ctx.coletor.somar("CAMPO")
            return
        base = resultado[0] if resultado else campo["base"]
        texto = "".join(r.texto for r in resultado).replace("\f", "")
        del saida[inicio:]
        saida.append(replace(base, texto=texto, campo=instrucao, imagem=None))


def _medida_emu(valor: str | None) -> int | None:
    n = _inteiro(valor)
    return n if n is not None and 0 < n <= _EMU_MAXIMO else None


def _ler_desenho(drawing, ctx: _Contexto) -> Imagem | None:
    """w:drawing -> Imagem, ou None se nao for figura na linha que o EditDoc edita.

    So' wp:inline com PNG, JPEG, GIF ou BMP vira Imagem. O resto (imagem flutuante, EMF,
    SVG, imagem vinculada, forma, caixa de texto, grafico, SmartArt) volta None, e quem
    chama guarda o desenho como objeto opaco (0.1.2), que volta igual ao arquivo.
    """
    c = ctx.coletor
    quadro = None
    for filho in drawing:
        if _local(filho) in ((WP_NS, "inline"), (WP_NS, "anchor")):
            quadro = filho
            break
    if quadro is None or _local(quadro)[1] == "anchor":
        return None
    dados_graf = quadro.find("{%s}graphic/{%s}graphicData" % (A_NS, A_NS))
    if dados_graf is None or dados_graf.get("uri") != URI_IMAGEM:
        return None
    pic = dados_graf.find("{%s}pic" % PIC_NS)
    blip = pic.find("{%s}blipFill/{%s}blip" % (PIC_NS, A_NS)) if pic is not None else None
    rid = blip.get("{%s}embed" % R_NS) if blip is not None else None
    relacao = ctx.relacoes.get(rid or "")
    if relacao is None or relacao[2] or not relacao[0].endswith("/image") \
            or relacao[1] not in ctx.nomes or ctx.ler_parte is None:
        # Sem r:embed (so' r:link, imagem vinculada a arquivo externo) ou relacao quebrada:
        # o objeto opaco preserva a vinculada; a quebrada vira o aviso IMAGEM.
        return None
    alvo = relacao[1]
    _validar_nome(alvo)
    if alvo not in ctx.midias:
        ctx.midias[alvo] = ctx.ler_parte(alvo)
    dados = ctx.midias[alvo]
    formato = mod_imagem.formato_de(dados)
    dims = mod_imagem.dimensoes(dados, formato) if formato else None
    if formato is None or dims is None or dims[0] <= 0 or dims[1] <= 0:
        return None  # EMF, WMF, TIFF, SVG... ou imagem danificada: objeto opaco
    if not mod_imagem.decodificavel(*dims):
        c.somar("IMAGEM_GRANDE")
    extent = quadro.find("{%s}extent" % WP_NS)
    cx = _medida_emu(extent.get("cx")) if extent is not None else None
    cy = _medida_emu(extent.get("cy")) if extent is not None else None
    if cx is None or cy is None:
        # Sem tamanho valido: o da imagem a 96 dpi, limitado ao maior papel.
        escala = min(1.0, _EMU_MAXIMO / (max(dims) * EMU_POR_PX))
        cx = max(1, round(dims[0] * EMU_POR_PX * escala))
        cy = max(1, round(dims[1] * EMU_POR_PX * escala))
        c.somar("FORMATACAO")
    if blip.getparent() is not None:
        recorte = blip.getparent().find("{%s}srcRect" % A_NS)
        if recorte is not None and any((recorte.get(k) or "0") != "0" for k in "ltrb"):
            c.somar("FORMATACAO")  # recorte da imagem: o EditDoc mostra a imagem inteira
    xfrm = pic.find("{%s}spPr/{%s}xfrm" % (PIC_NS, A_NS))
    if xfrm is not None and (xfrm.get("rot") not in (None, "0") or xfrm.get("flipH") in ("1", "true")
                             or xfrm.get("flipV") in ("1", "true")):
        c.somar("FORMATACAO")  # rotacao ou espelhamento
    doc_pr = quadro.find("{%s}docPr" % WP_NS)
    descricao = (doc_pr.get("descr") or "") if doc_pr is not None else ""
    return Imagem(dados=dados, formato=formato, largura_emu=cx, altura_emu=cy,
                  descricao=descricao)


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
        if ns == MATH_NS and loc in ("oMath", "oMathPara"):
            # Equacao (OMML) fica no namespace m:, nao no w:. Antes do M4 o teste de
            # namespace a descartava sem aviso; desde a 0.1.2 ela e' preservada.
            run = _opaco(f, None, ctx)
            if run is not None:
                saida.append(run)
            continue
        if ns != W:
            continue
        if loc == "r":
            _ler_run(f, ctx, saida)
        elif loc == "hyperlink":
            c.somar("HIPERLINK")
            _runs_em(f, ctx, saida)
        elif loc == "fldSimple":
            instrucao = normalizar_instrucao(_atr(f, "instr") or "")
            dentro: list[Run] = []
            _runs_em(f, ctx, dentro)
            if tipo_do_campo(instrucao) is not None and not any(
                    r.eh_objeto() or r.campo is not None for r in dentro):
                base = dentro[0] if dentro else Run()
                texto = "".join(r.texto for r in dentro).replace("\f", "")
                saida.append(replace(base, texto=texto, campo=instrucao, imagem=None))
            else:
                c.somar("CAMPO")
                saida.extend(dentro)
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
            c.somar("OBJETO_PERDIDO")  # equacao no namespace errado: nao ha' o que preservar
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
    sem_lista = props.pop("_sem_lista", False)
    if "numeracao" not in props and not sem_lista:
        # Lista ligada pelo estilo (List Bullet...): vira lista do paragrafo, porque o
        # numbering.xml de origem nao volta ao arquivo.
        lista = ctx.estilos.numeracao_de(props.get("estilo") or ctx.estilos.id_padrao())
        if lista is not None:
            props["numeracao"] = lista
    runs: list[Run] = []
    _runs_em(p, ctx, runs)
    if ctx.nivel_tabela > 0:
        # Quebra de pagina dentro de celula: o EditDoc nao pagina dentro da tabela por
        # quebra manual. Vira quebra de linha, com aviso.
        quebras = sum(r.texto.count("\f") for r in runs if not r.eh_objeto())
        quebras += 1 if props.pop("quebra_antes", False) else 0
        if quebras:
            ctx.coletor.somar("QUEBRA_EM_TABELA", quebras)
            runs = [r if r.eh_objeto() else replace(r, texto=r.texto.replace("\f", "\n"))
                    for r in runs]
    saida = [Paragrafo(runs=[], **props)]
    for run in runs:
        if run.eh_objeto() or run.campo is not None:
            saida[-1].runs.append(run)
            continue
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


def _blocos(elemento, paras: list[Bloco], ctx: _Contexto, achatar: bool = False) -> None:
    """Blocos de `elemento` (corpo, celula, sdtContent...) para `paras`.

    `achatar`: a tabela vira paragrafos (tabela acima dos limites, ou aninhada fundo
    demais). E' o comportamento do M2, so' para o caso de excecao.
    """
    c = ctx.coletor
    for f in elemento:
        ns, loc = _local(f)
        if loc is None:
            continue
        if ns == MC_NS and loc == "AlternateContent":
            ramo = _escolha(f)
            if ramo is not None:
                _blocos(ramo, paras, ctx, achatar)
            continue
        if ns != W:
            continue
        if loc == "p":
            paras.extend(_paragrafos(f, ctx))
        elif loc == "tbl":
            if achatar:
                _blocos(f, paras, ctx, achatar=True)
                continue
            tabela = _tabela(f, ctx)
            if tabela is None:
                c.somar("TABELA")
                ctx.nivel_tabela += 1
                try:
                    _blocos(f, paras, ctx, achatar=True)
                finally:
                    ctx.nivel_tabela -= 1
            else:
                paras.append(tabela)
        elif loc in ("tr", "tc", "customXml", "smartTag", "sdtContent", "ins"):
            _blocos(f, paras, ctx, achatar)
        elif loc == "sdt":
            c.somar("CONTEUDO_CONTROLADO")
            conteudo = f.find(q("sdtContent"))
            if conteudo is not None:
                _blocos(conteudo, paras, ctx, achatar)
        elif loc in ("del", "moveFrom"):
            c.somar("REVISAO")
        elif loc in _IGNORADOS_BLOCO or loc == "tblPrEx":
            continue
        else:
            c.somar("ELEMENTO_DESCONHECIDO")


# -- tabelas ------------------------------------------------------------------

def _filhos_w(elemento, nome: str, ctx: _Contexto):
    """Filhos `w:nome`, desembrulhando sdt, customXml e AlternateContent (com aviso do sdt)."""
    for f in elemento:
        ns, loc = _local(f)
        if loc is None:
            continue
        if ns == MC_NS and loc == "AlternateContent":
            ramo = _escolha(f)
            if ramo is not None:
                yield from _filhos_w(ramo, nome, ctx)
        elif ns != W:
            continue
        elif loc == nome:
            yield f
        elif loc == "sdt":
            ctx.coletor.somar("CONTEUDO_CONTROLADO")
            conteudo = f.find(q("sdtContent"))
            if conteudo is not None:
                yield from _filhos_w(conteudo, nome, ctx)
        elif loc in ("customXml", "ins"):
            yield from _filhos_w(f, nome, ctx)


def _borda(el, ctx: _Contexto) -> Borda:
    valor = _atr(el, "val") or "single"
    estilo = _ESTILO_BORDA.get(valor)
    if estilo is None:
        # Estilo que o EditDoc nao desenha (ondulada, tripla, 3D...): vira simples.
        estilo = "simples"
        ctx.coletor.somar("FORMATACAO")
    tamanho = _inteiro(_atr(el, "sz"))
    tamanho = 4 if tamanho is None else min(max(tamanho, 1), 96)
    cor = _atr(el, "color")
    cor = cor.upper() if cor and _HEX6.fullmatch(cor) else None
    return Borda(estilo=estilo, oitavos_pt=tamanho, cor_hex=cor)


def _ler_bordas(el, alvo, ctx: _Contexto, lados=_LADOS_TABELA) -> None:
    """Preenche `alvo` (BordasTabela ou BordasCelula) com os lados de tblBorders/tcBorders."""
    for f in el:
        ns, loc = _local(f)
        if ns != W:
            continue
        campo = dict(lados).get(loc)
        if campo is not None and hasattr(alvo, campo):
            setattr(alvo, campo, _borda(f, ctx))
        elif loc in ("tl2br", "tr2bl"):
            ctx.coletor.somar("FORMATACAO")  # diagonal


def _estilo_de_tabela(ctx: _Contexto, sid: str | None):
    """Elementos w:style da cadeia basedOn do estilo de tabela, do proprio para a base."""
    cadeia = []
    vistos: set[str] = set()
    while sid and sid not in vistos and len(cadeia) < 8:
        vistos.add(sid)
        estilo = ctx.estilos_tabela.get(sid)
        if estilo is None:
            break
        cadeia.append(estilo)
        base = estilo.find(q("basedOn"))
        sid = _atr(base, "val") if base is not None else None
    return cadeia


def _bordas_do_estilo(ctx: _Contexto, sid: str | None) -> BordasTabela:
    bordas = BordasTabela()
    for estilo in reversed(_estilo_de_tabela(ctx, sid)):  # da base para o proprio
        tb = estilo.find(q("tblPr") + "/" + q("tblBorders"))
        if tb is not None:
            _ler_bordas(tb, bordas, ctx)
    return bordas


def _linhas_xml(tbl, ctx: _Contexto) -> list:
    return list(_filhos_w(tbl, "tr", ctx))


def _tabela(tbl, ctx: _Contexto) -> Tabela | None:
    """w:tbl -> Tabela. None se passar dos limites (quem chama achata, com aviso)."""
    c = ctx.coletor
    lim = ctx.lim
    if ctx.nivel_tabela >= lim["tabela_profundidade"]:
        return None
    linhas_xml = _linhas_xml(tbl, ctx)
    celulas_xml = [list(_filhos_w(tr, "tc", ctx)) for tr in linhas_xml]
    if (len(linhas_xml) > lim["tabela_linhas"]
            or sum(len(x) for x in celulas_xml) > lim["tabela_celulas"]
            or any(len(x) > lim["tabela_colunas"] for x in celulas_xml)):
        return None

    tabela = Tabela()
    # -- tblPr
    tbl_pr = tbl.find(q("tblPr"))
    estilo_id = ctx.estilo_tabela_padrao
    diretas = None
    if tbl_pr is not None:
        for f in tbl_pr:
            ns, loc = _local(f)
            if ns != W or loc is None:
                continue
            if loc == "tblStyle":
                estilo_id = _atr(f, "val")
            elif loc == "tblW":
                tipo = _atr(f, "type") or "dxa"
                valor = _inteiro(_atr(f, "w")) or 0
                if tipo in ("dxa", "pct", "auto") and 0 <= valor <= PAPEL_MAXIMO_TW:
                    tabela.largura = (tipo, valor)
            elif loc == "jc":
                valor = _JC_TABELA.get(_atr(f, "val") or "")
                if valor is None:
                    c.somar("FORMATACAO")
                tabela.alinhamento = valor
            elif loc == "tblInd":
                valor = _inteiro(_atr(f, "w"))
                if valor is not None and (_atr(f, "type") or "dxa") == "dxa" \
                        and abs(valor) <= PAPEL_MAXIMO_TW:
                    tabela.recuo_tw = valor
                elif valor:
                    c.somar("FORMATACAO")
            elif loc == "tblBorders":
                diretas = f
            elif loc == "tblLayout":
                tabela.layout_fixo = _atr(f, "type") == "fixed"
            elif loc == "tblCellMar":
                margens = {"top": 0, "left": 108, "bottom": 0, "right": 108}
                for m in f:
                    nome = {"start": "left", "end": "right"}.get(_local(m)[1], _local(m)[1])
                    valor = _inteiro(_atr(m, "w"))
                    if nome in margens and valor is not None and 0 <= valor <= 20000:
                        margens[nome] = valor
                tabela.margens_celula_tw = (margens["top"], margens["left"],
                                            margens["bottom"], margens["right"])
            elif loc in _TBLPR_NEUTRAS:
                continue
            else:
                # tblpPr (tabela flutuante), shd, tblCellSpacing, bidiVisual, legenda...
                c.somar("FORMATACAO")
    # Bordas efetivas: as do estilo (cadeia basedOn), depois as diretas. Lado sem
    # borda nenhuma fica explicito como "nenhuma": o escritor grava os seis lados.
    bordas = _bordas_do_estilo(ctx, estilo_id)
    if diretas is not None:
        _ler_bordas(diretas, bordas, ctx)
    for campo in ("sup", "inf", "esq", "dir", "horizontal", "vertical"):
        if getattr(bordas, campo) is None:
            setattr(bordas, campo, Borda(estilo="nenhuma", oitavos_pt=0))
    tabela.bordas = bordas
    cadeia = _estilo_de_tabela(ctx, estilo_id)
    if any(e.find(q("tblStylePr")) is not None or e.find(q("tcPr")) is not None
           or e.find(q("rPr")) is not None for e in cadeia):
        # Estilo com formatacao condicional (linha de cabecalho colorida, faixas...).
        c.somar("ESTILO")

    # -- tblGrid
    grade = tbl.find(q("tblGrid"))
    colunas: list[int] = []
    if grade is not None:
        for g in grade.findall(q("gridCol")):
            colunas.append(_inteiro(_atr(g, "w")) or 0)

    # -- linhas
    ctx.nivel_tabela += 1
    try:
        for tr, tcs in zip(linhas_xml, celulas_xml):
            tabela.linhas.append(_linha(tr, tcs, ctx))
    finally:
        ctx.nivel_tabela -= 1
    if not tabela.linhas:
        return None

    # Grade: tantas colunas quanto a linha mais larga; largura invalida vira a media.
    largura_max = max(colunas_da_linha(lin) for lin in tabela.linhas)
    if largura_max > lim["tabela_colunas"]:
        return None
    validas = [w for w in colunas if 0 < w <= PAPEL_MAXIMO_TW]
    padrao = round(sum(validas) / len(validas)) if validas else 9026 // max(1, largura_max)
    if len(validas) != len(colunas) or len(colunas) not in (0, largura_max):
        if colunas:
            c.somar("FORMATACAO")
    colunas = [w if 0 < w <= PAPEL_MAXIMO_TW else padrao for w in colunas]
    while len(colunas) < largura_max:
        colunas.append(padrao)
    tabela.colunas_tw = colunas[:max(largura_max, 1)]
    # Linha mais curta que a grade (w:gridBefore/gridAfter, ou celula faltando):
    # completa com celulas vazias, como o Word desenha.
    for linha in tabela.linhas:
        falta = len(tabela.colunas_tw) - colunas_da_linha(linha)
        if falta > 0:
            linha.celulas.append(Celula(blocos=[Paragrafo()], colunas=falta))
    return tabela


def _linha(tr, tcs: list, ctx: _Contexto) -> Linha:
    c = ctx.coletor
    linha = Linha()
    tr_pr = tr.find(q("trPr"))
    if tr_pr is not None:
        for f in tr_pr:
            ns, loc = _local(f)
            if ns != W or loc is None:
                continue
            if loc == "tblHeader":
                linha.cabecalho = _onoff(f)
            elif loc == "trHeight":
                valor = _inteiro(_atr(f, "val"))
                if valor is not None and 0 < valor <= PAPEL_MAXIMO_TW:
                    linha.altura_tw = valor
                    linha.altura_exata = _atr(f, "hRule") == "exact"
            elif loc in ("gridBefore", "gridAfter", "jc", "hidden", "tblCellSpacing"):
                c.somar("FORMATACAO")
            elif loc in ("ins", "del"):
                c.somar("REVISAO")
            elif loc in _TRPR_NEUTRAS:
                continue
            else:
                c.somar("FORMATACAO")
    for tc in tcs:
        celula = _celula(tc, ctx)
        if celula is None:
            # hMerge="continue" (mescla horizontal antiga): soma na celula anterior.
            if linha.celulas:
                linha.celulas[-1].colunas += 1
            continue
        linha.celulas.append(celula)
    return linha


def _celula(tc, ctx: _Contexto) -> Celula | None:
    c = ctx.coletor
    celula = Celula()
    tc_pr = tc.find(q("tcPr"))
    if tc_pr is not None:
        for f in tc_pr:
            ns, loc = _local(f)
            if ns != W or loc is None:
                continue
            if loc == "gridSpan":
                valor = _inteiro(_atr(f, "val"))
                celula.colunas = valor if valor is not None and 1 <= valor <= 63 else 1
            elif loc == "hMerge":
                if (_atr(f, "val") or "continue") == "continue":
                    return None
            elif loc == "vMerge":
                celula.mescla_vertical = "inicio" if _atr(f, "val") == "restart" else "continua"
            elif loc == "tcBorders":
                celula.bordas = BordasCelula()
                _ler_bordas(f, celula.bordas, ctx)
            elif loc == "shd":
                fill = _atr(f, "fill")
                if fill and _HEX6.fullmatch(fill):
                    celula.sombreamento_hex = fill.upper()
                elif fill not in (None, "auto"):
                    c.somar("FORMATACAO")
                if (_atr(f, "val") or "clear") not in ("clear", "nil"):
                    c.somar("FORMATACAO")  # padrao de hachura
            elif loc == "vAlign":
                celula.alinhamento_vertical = _VALIGN.get(_atr(f, "val") or "")
            elif loc in ("cellIns", "cellDel", "cellMerge"):
                c.somar("REVISAO")
            elif loc in _TCPR_NEUTRAS:
                continue
            else:
                c.somar("FORMATACAO")  # tcMar, textDirection...
    _blocos(tc, celula.blocos, ctx)
    if celula.mescla_vertical == "continua" and any(
            r.texto for p in celula.blocos if isinstance(p, Paragrafo) for r in p.runs):
        # O Word nao mostra o conteudo de celula coberta por mescla vertical.
        c.somar("CELULA_ESCONDIDA")
    if not celula.blocos or isinstance(celula.blocos[-1], Tabela):
        celula.blocos.append(Paragrafo())
    return celula


def _faixas_da_secao(sect, ctx: _Contexto, final: bool) -> dict[tuple[str, str], str]:
    """Referencias de cabecalho e rodape de uma secao: (onde, tipo) -> rId.

    Como no Word, a secao herda o que nao declara. A secao que nao e' a ultima so'
    acumula a heranca; a ultima devolve o que vale para o documento.
    """
    refs: dict[tuple[str, str], str] = {}
    for x in sect:
        ns, loc = _local(x)
        if ns != W or loc not in ("headerReference", "footerReference"):
            continue
        tipo = _TIPO_FAIXA.get(_atr(x, "type") or "default")
        rid = x.get(q("id", R_NS))
        if tipo is None or not rid:
            ctx.coletor.somar("CABECALHO_RODAPE")
            continue
        refs[("cabecalho" if loc == "headerReference" else "rodape", tipo)] = rid
    if not final:
        ctx.faixas_das_secoes.append(dict(refs))
        ctx.faixas_herdadas.update(refs)
        return refs
    efetivas = {**ctx.faixas_herdadas, **refs}
    if any(efetivas.get(k) != v for anteriores in ctx.faixas_das_secoes
           for k, v in anteriores.items()):
        ctx.coletor.somar("CABECALHO_SECAO")
    return efetivas


def _numeracao_da_secao(sect, pagina: Pagina, ctx: _Contexto) -> Pagina:
    """Primeira pagina diferente (w:titlePg) e numeracao (w:pgNumType) do sectPr."""
    titulo = sect.find(q("titlePg"))
    if titulo is not None:
        pagina = replace(pagina, primeira_diferente=_onoff(titulo))
    num = sect.find(q("pgNumType"))
    if num is not None:
        formato = _atr(num, "fmt")
        if formato is not None:
            if formato in FORMATOS_NUMERO:
                pagina = replace(pagina, formato_numero=formato)
            else:
                ctx.coletor.somar("NUMERO_PAGINA")  # chicago, ordinal, cardinalText...
        inicio = _atr(num, "start")
        if inicio is not None:
            valor = _inteiro(inicio)
            if valor is not None and 0 <= valor <= NUMERO_INICIAL_MAXIMO:
                pagina = replace(pagina, numero_inicial=valor)
            else:
                ctx.coletor.somar("NUMERO_PAGINA")
        if any(_atr(num, a) is not None for a in ("chapStyle", "chapSep")):
            ctx.coletor.somar("NUMERO_PAGINA")
    return pagina


def _ler_faixa(rid: str, onde: str, ctx: _Contexto, tamanho_de, relacoes_de) -> list[Bloco] | None:
    """Uma parte de cabecalho (w:hdr) ou rodape (w:ftr) -> blocos. None (com aviso) se falhar.

    A imagem do cabecalho usa as relacoes da propria parte, nao as do documento.
    """
    c = ctx.coletor
    relacao = ctx.relacoes.get(rid)
    esperado = "/header" if onde == "cabecalho" else "/footer"
    if relacao is None or relacao[2] or not relacao[0].endswith(esperado) \
            or relacao[1] not in ctx.nomes:
        c.somar("CABECALHO_RODAPE")
        return None
    alvo = relacao[1]
    _validar_nome(alvo)
    if tamanho_de(alvo) > ctx.lim["cabecalho_bytes"]:
        c.somar("CABECALHO_GRANDE")
        return None
    profundidade = ctx.lim["profundidade"]
    raiz = _parse(ctx.ler_parte(alvo), alvo, profundidade)
    if _local(raiz) != (W, "hdr" if onde == "cabecalho" else "ftr"):
        c.somar("CABECALHO_RODAPE")
        return None
    if _profundidade(raiz) > profundidade:
        raise ErroDocx("XML_PROFUNDIDADE_EXCEDIDA", alvo)
    relacoes_doc = ctx.relacoes
    ignoraveis_doc = ctx.ignoraveis
    ctx.relacoes = relacoes_de(alvo)
    ctx.ignoraveis = opacos.ignoraveis_da_raiz(raiz)
    try:
        blocos: list[Bloco] = []
        _blocos(raiz, blocos, ctx)
    finally:
        ctx.relacoes = relacoes_doc
        ctx.ignoraveis = ignoraveis_doc
    _fechar_campos(ctx)
    return blocos


def _fechar_campos(ctx: _Contexto) -> None:
    """Campo aberto que nunca fechou (arquivo cortado): o texto ficou, o campo nao."""
    for _campo in ctx.campos:
        ctx.coletor.somar("CAMPO")
    ctx.campos = []


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


def _tema_preservavel(raiz) -> bool:
    """O tema volta ao arquivo so' se nao aponta para nada (imagem de preenchimento...).

    Um r:id no tema exigiria as relacoes dele, que o EditDoc nao regrava.
    """
    return not any(chave.startswith("{%s}" % R_NS) for el in raiz.iter()
                   for chave in el.attrib)


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
        tipos_extensao = {}
        if "[Content_Types].xml" in nomes:
            ct = _parse(ler_parte("[Content_Types].xml"), "[Content_Types].xml", profundidade)
            for o in ct.iter("{%s}Override" % PKG_CT):
                tipos_parte[(o.get("PartName") or "").lstrip("/")] = o.get("ContentType")
            for d in ct.iter("{%s}Default" % PKG_CT):
                tipos_extensao[(d.get("Extension") or "").lower()] = d.get("ContentType")

        def tipo_de(parte: str) -> str | None:
            """Tipo de conteudo da parte: o Override, ou o Default da extensao."""
            if parte in tipos_parte:
                return tipos_parte[parte]
            base = posixpath.basename(parte)
            return tipos_extensao.get(base.rsplit(".", 1)[1].lower()) if "." in base else None
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

        def relacoes_de(parte: str) -> dict[str, tuple[str, str, bool]]:
            """Relacoes de uma parte: rId -> (tipo, alvo resolvido, externo)."""
            saida: dict[str, tuple[str, str, bool]] = {}
            rels = caminho_dos_rels(parte)
            if rels not in nomes:
                return saida
            base = posixpath.dirname(parte)
            for rel in _parse(ler_parte(rels), rels, profundidade):
                externo = rel.get("TargetMode") == "External"
                bruto = rel.get("Target", "")
                if externo:
                    alvo = bruto
                elif bruto.startswith("/"):
                    alvo = bruto[1:]
                else:
                    alvo = posixpath.normpath(posixpath.join(base, bruto))
                saida[rel.get("Id", "")] = (rel.get("Type", ""), alvo, externo)
            return saida

        def tamanho_de(parte: str) -> int:
            return z.getinfo(parte).file_size

        # Partes ligadas ao documento principal: numeracao, estilos, tema e configuracoes.
        numeracao: dict[str, str | None] = {}
        estilos = None
        dados_estilos = b""
        fontes_tema: dict = {}
        tema: bytes | None = None
        pares_impares = False
        relacoes = relacoes_de(alvo_doc)
        for tipo, alvo, externo in relacoes.values():
            if externo or alvo not in nomes:
                continue
            if tipo.endswith("/numbering"):
                _validar_nome(alvo)
                numeracao = _numeracao(_parse(ler_parte(alvo), alvo, profundidade))
            elif tipo.endswith("/styles"):
                _validar_nome(alvo)
                dados_estilos = ler_parte(alvo)
                estilos = _parse(dados_estilos, alvo, profundidade)
                if _profundidade(estilos) > profundidade:
                    raise ErroDocx("XML_PROFUNDIDADE_EXCEDIDA", alvo)
            elif tipo.endswith("/theme"):
                _validar_nome(alvo)
                dados_tema = ler_parte(alvo)
                raiz_tema = _parse(dados_tema, alvo, profundidade)
                fontes_tema = fx_estilos.fontes_do_tema(raiz_tema)
                if caminho_dos_rels(alvo) not in nomes and _tema_preservavel(raiz_tema):
                    tema = dados_tema
            elif tipo.endswith("/settings"):
                _validar_nome(alvo)
                config = _parse(ler_parte(alvo), alvo, profundidade)
                pares = config.find(q("evenAndOddHeaders"))
                pares_impares = pares is not None and _onoff(pares)

        ctx = _Contexto(coletor, numeracao, lim)
        ctx.relacoes = relacoes
        ctx.ler_parte = ler_parte
        ctx.nomes = nomes
        ctx.capturador = opacos.Capturador(
            ctx.lim, coletor, nomes, ler_parte, relacoes_de, tipo_de,
            lambda dados, nome: _parse(dados, nome, profundidade), ctx.midias)
        ctx.ignoraveis = opacos.ignoraveis_da_raiz(raiz)
        if estilos is not None:
            ctx.estilos, removidos = fx_estilos.ler_estilos(estilos, dados_estilos, fontes_tema,
                                                            numeracao, tema)
            if removidos:
                coletor.somar("FORMATACAO", removidos)
            for estilo in estilos.findall(q("style")):
                if _atr(estilo, "type") == "table" and _atr(estilo, "styleId"):
                    ctx.estilos_tabela[_atr(estilo, "styleId")] = estilo
                    if _onoff_atr(estilo, "default"):
                        ctx.estilo_tabela_padrao = _atr(estilo, "styleId")

        paras: list[Bloco] = []
        _blocos(corpo, paras, ctx)
        _fechar_campos(ctx)
        sect_final = corpo.find(q("sectPr"))
        refs_finais = dict(ctx.faixas_herdadas)
        if sect_final is not None:
            refs_finais = _faixas_da_secao(sect_final, ctx, final=True)
            ctx.pagina_final = _pagina_de(sect_final)
            if ctx.pagina_final is None:
                # Papel ou margem que nao cabe numa pagina util: o EditDoc
                # grava A4 com as margens padrao, e o aviso diz isso.
                coletor.somar("PAPEL_INVALIDO")
        pagina = ctx.pagina_final if ctx.pagina_final is not None else Pagina()
        if sect_final is not None:
            pagina = _numeracao_da_secao(sect_final, pagina, ctx)
        pagina = replace(pagina, pares_impares=pares_impares)
        cabecalhos: dict[str, list[Bloco]] = {}
        rodapes: dict[str, list[Bloco]] = {}
        for (onde, tipo), rid in sorted(refs_finais.items()):
            blocos = _ler_faixa(rid, onde, ctx, tamanho_de, relacoes_de)
            if blocos is not None:
                (cabecalhos if onde == "cabecalho" else rodapes)[tipo] = blocos
        total_secoes = ctx.secoes + (1 if sect_final is not None else 0)
        if total_secoes > 1:
            # Cada secao tem o seu papel e as suas margens; o EditDoc tem um so'.
            coletor.somar("PAGINA")

        meta = {"titulo": "", "autor": "", "criado_em": None, "modificado_em": None}
        if alvo_core and alvo_core in nomes:
            _validar_nome(alvo_core)
            meta = _core(ler_parte(alvo_core), profundidade)

    doc = normalizar(Documento(paragrafos=paras, pagina=pagina, cabecalhos=cabecalhos,
                               rodapes=rodapes, estilos=ctx.estilos, **meta))
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
