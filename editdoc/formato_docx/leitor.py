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
PAGE e NUMPAGES (M5) viram um `Run` com `campo`; desde a 0.1.3 os outros (TOC, REF, DATE,
IF...) viram marcas de inicio (com o codigo) e de fim no fluxo, com o resultado como texto
entre elas. Hiperlinks viram `Run.link`; marcadores, marcas no fluxo. O resto do pacote
(custom.xml, customXml, fontTable, webSettings, settings.xml...) vai para `Documento.pacote`
(`pacote.py`). Revisoes aceitas; exclusoes tem aviso.

0.1.5: as propriedades de run, de paragrafo e de tabela que o modelo nao representa vao para
os extras (`propriedades.py`) e voltam ao arquivo; o controle de conteudo de bloco e de
paragrafo vira marcas no fluxo (`MarcaConteudo`); o de linha ou celula de tabela continua
achatado, com aviso. Recorte de imagem (a:srcRect) vai para `Imagem.recorte`.

Cabecalho e rodape (M5): os da ultima secao, com a heranca do Word (a secao sem
referencia herda a da anterior). Cada parte passa pelos mesmos limites do pacote e
mais um, de tamanho (`cabecalho_bytes`). Campo aninhado fundo demais
(`campo_profundidade`) nao e' interpretado: o texto fica, com aviso.

Estilos (M6): o styles.xml vira o catalogo (`formato_docx/estilos.py`), guardado no
Documento com o XML original. w:pStyle e w:rStyle viram `Paragrafo.estilo` e
`Run.estilo`; a formatacao lida no paragrafo e no run continua sendo so' a direta.
Referencia a estilo que nao existe vira o aviso ESTILO.

Listas (0.1.4): o numbering.xml vira o catalogo de numeracao (`formato_docx/numeracao.py`),
que volta inteiro ao arquivo. O w:numPr do paragrafo vira `Paragrafo.lista` (numId) e
`Paragrafo.lista_nivel` (ilvl); o do estilo fica no estilo, e o paragrafo herda (antes da
0.1.4 a lista do estilo passava ao paragrafo, porque o numbering.xml de origem nao voltava).
numId que nao existe vira "sem lista" (aviso LISTA); ilvl fora de 0 a 8, o nivel mais
proximo (aviso LISTA_NIVEL).
"""

from __future__ import annotations

import io
import os
import posixpath
import re
import zipfile
from dataclasses import replace

from lxml import etree

from editdoc.formato_docx import comentarios as fx_comentarios
from editdoc.formato_docx import estilos as fx_estilos
from editdoc.formato_docx import numeracao as fx_numeracao
from editdoc.formato_docx import opacos
from editdoc.formato_docx import pacote as fx_pacote
from editdoc.formato_docx import propriedades as fx_props
from editdoc.formato_docx.avisos import Aviso, Coletor
from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.nomes import (A_NS, CP, CT_DOCUMENTO_MACRO, DC, DCT, MATH_NS, MC_NS,
                                        PIC_NS, PKG_CT, R_NS, RT_STRICT, URI_IMAGEM, W,
                                        W_STRICT, WP_NS, q)
from editdoc.formato_docx.ordem import caminho_dos_rels
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.campos import (FORMATOS_NUMERO, NUMERO_INICIAL_MAXIMO,
                                   normalizar_instrucao, tipo_do_campo)
from editdoc.modelo import comentarios as mod_comentarios
from editdoc.modelo.documento import (Bloco, Borda, BordasCelula, BordasTabela, Campo, Celula,
                                      Documento, Imagem, Linha, Link, MarcaCampo,
                                      MarcaComentario, MarcaConteudo, Marcador,
                                      Paragrafo, Run, Tabela, colunas_da_linha, normalizar,
                                      paragrafos_de, run_de_imagem, run_de_objeto)
from editdoc.modelo.estilos import Estilos, catalogo_padrao
from editdoc.modelo import numeracao as mod_numeracao
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
    # Campos, hiperlinks e marcadores (0.1.3): quantos por documento, e o tamanho da
    # instrucao e do endereco. Acima disto o campo (ou o link) fica so' como texto, com aviso.
    "campos": 20000,
    "instrucao_campo": 4096,
    "hiperlinks": 20000,
    "link_tamanho": 8192,
    "marcadores": 20000,
    # Controles de conteudo (w:sdt, 0.1.5) preservados por documento. Acima disto o controle
    # e' achatado (o texto fica), com aviso.
    "conteudos": 20000,
    # Objetos opacos (0.1.2): quantos, o tamanho do XML e o fecho das partes.
    **opacos.LIMITES,
    # Partes do pacote preservadas (0.1.3).
    **fx_pacote.LIMITES,
    # Numeracao de listas (0.1.4): definicoes, niveis e tamanho do texto do numero.
    **mod_numeracao.LIMITES,
    # Comentarios (0.1.6): quantos, o tamanho de cada um e do comments.xml, e respostas.
    **mod_comentarios.LIMITES,
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
#: Filhos de tblPr que o laco abaixo nao le: desde a 0.1.6 o tblLook e o tamanho das faixas
#: vao para os extras da tabela (e voltam); a revisao sai, com aviso.
_TBLPR_NEUTRAS = {"tblLook", "tblStyleRowBandSize", "tblStyleColBandSize", "tblPrChange"}

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_DOCTYPE = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY|ELEMENT|ATTLIST|NOTATION)", re.IGNORECASE)
_ENCODING = re.compile(rb"""encoding\s*=\s*["']([A-Za-z0-9._-]+)["']""")
_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_JC = {"left": "esquerda", "start": "esquerda", "center": "centro",
       "right": "direita", "end": "direita", "both": "justificado"}

#: Desde a 0.1.5 nao ha' propriedade de run ou de paragrafo "neutra" (ignorada): o que o
#: modelo nao representa vai para os extras (`propriedades.py`) e volta ao arquivo.

_CONTEINERES_INLINE = {"hyperlink", "fldSimple", "smartTag", "customXml", "dir", "bdo",
                       "moveTo", "ins"}
_IGNORADOS_INLINE = {"pPr", "proofErr", "permStart", "permEnd", "lastRenderedPageBreak"}
_IGNORADOS_BLOCO = {"sectPr", "permStart", "permEnd",
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
    def __init__(self, coletor: Coletor, numeracao=None, lim: dict | None = None) -> None:
        self.coletor = coletor
        #: catalogo de numeracao (0.1.4), ou None se o arquivo nao tem (ou nao pode ser lido)
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
        #: campos, hiperlinks e marcadores (0.1.3): contagens para os limites, marcadores
        #: abertos (w:id -> nome), nomes ja' usados, e os que estavam entre paragrafos
        self.total_campos = 0
        #: numero que liga a marca de inicio a de fim do mesmo campo
        self.pares = 0
        self.total_links = 0
        self.marcadores_ids: dict[str, str] = {}
        self.marcadores_nomes: set[str] = set()
        self.marcas_pendentes: list[Run] = []
        #: texto do codigo de campo que ja' tinha ido para o paragrafo (sai na limpeza)
        self.descartar: list[Run] = []
        #: controles de conteudo preservados (0.1.5)
        self.total_conteudos = 0
        #: comentarios (0.1.6): a historia que se le ("corpo", "faixa" ou "comentario") e os
        #: w:id lidos do comments.xml. Ancora fora do corpo (cabecalho, rodape, o proprio
        #: comentario) nao vale: o comentario sem referencia no corpo sai, com aviso.
        self.historia = "corpo"
        self.comentarios_ids: set[int] = set()

    def estilo_existe(self, sid, tipo: str) -> bool:
        """O estilo vale: existe com o tipo, ou (0.1.6) o arquivo o cita sem definir e a
        referencia passa a ser preservada (`Estilos.preservar_referencia`)."""
        return self.estilos.preservar_referencia(sid, tipo)


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
    codigo = opacos.codigo_do_aviso(obj.tipo, obj.flutuante, obj.previa is not None)
    if codigo is not None:
        ctx.coletor.somar(codigo)
    return run_de_objeto(obj)


# -- propriedades -------------------------------------------------------------

def _ler_rpr(rpr, run: Run, ctx: _Contexto) -> None:
    """O que o modelo representa vai para os campos do run; o resto, desde a 0.1.5, vai inteiro
    para `run.extras` (`propriedades.py`) e volta ao arquivo. So' o que o esquema nao tem (ou
    a revisao de formatacao) se perde, com aviso."""
    c = ctx.coletor
    fontes = ctx.estilos.fontes_tema
    for f in rpr:
        ns, loc = _local(f)
        if ns != W or loc is None:
            continue
        if loc == "b":
            run.negrito = _onoff(f)
        elif loc == "i":
            run.italico = _onoff(f)
        elif loc == "strike":
            run.tachado = _onoff(f)
        elif loc in ("u", "dstrike", "color", "vertAlign"):
            # Duplo, tema, sobrescrito estranho...: o modelo fica com o que entende e o
            # elemento original volta pelos extras.
            for campo, valor in fx_props.derivado_rpr(loc, f, fontes).items():
                setattr(run, campo, valor)
        elif loc == "sz":
            run.tamanho_meio_pt = _inteiro(_atr(f, "val"))
        elif loc == "rFonts":
            fonte = fx_props.derivado_rpr(loc, f, fontes)["fonte"]
            if fonte:
                run.fonte = fonte
        elif loc == "rStyle":
            # Estilo que o styles.xml nao define (o "CommentReference" latente do Word): desde
            # a 0.1.6 a referencia e' preservada. ESTILO so' para id invalido ou de outro tipo.
            sid = _atr(f, "val")
            if ctx.estilo_existe(sid, "caractere"):
                run.estilo = sid
            elif sid not in (None, "DefaultParagraphFont"):
                c.somar("ESTILO")
    run.extras = fx_props.ler_extras_rpr(rpr, fontes, c)


def _ler_ppr(ppr, ctx: _Contexto) -> dict:
    """Propriedades do paragrafo. Desde a 0.1.5 o que o modelo nao representa (tabulacoes,
    bordas, sombreamento, quadro, controle de linhas, a marca de paragrafo...) vai para
    `extras` e volta ao arquivo; a entrelinha exata ou minima tambem (antes saia simples)."""
    c = ctx.coletor
    out: dict = {}
    for f in ppr:
        ns, loc = _local(f)
        if ns != W or loc is None:
            continue
        if loc in ("jc", "ind", "spacing"):
            out.update({k: v for k, v in fx_props.derivado_ppr(loc, f).items() if v is not None})
        elif loc == "numPr":
            _ler_numpr(f, out, ctx)
        elif loc == "pStyle":
            sid = _atr(f, "val")
            if ctx.estilo_existe(sid, "paragrafo"):
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
    extras = fx_props.ler_extras_ppr(ppr, ctx.estilo_existe, c)
    if extras is not None:
        out["extras"] = extras
    return out


def _escolha(alternativa):
    """Dentro de mc:AlternateContent, o ramo que o EditDoc entende: Choice ou Fallback."""
    for nome in ("Choice", "Fallback"):
        ramo = next((x for x in alternativa if _local(x) == (MC_NS, nome)), None)
        if ramo is not None:
            return ramo
    return None


def _ler_numpr(numpr, out: dict, ctx: _Contexto) -> None:
    """w:numPr do paragrafo -> `lista` (numId) e `lista_nivel` (ilvl), os dois diretos (0.1.4).

    numId 0 desliga a lista que viria do estilo (fica 0). numId que o numbering.xml nao
    define (ou numeracao que nao pode ser lida): o Word nao numera, e o paragrafo fica sem
    lista, com aviso LISTA. ilvl fora de 0 a 8: o nivel mais proximo, com aviso LISTA_NIVEL.
    """
    c = ctx.coletor
    nid_el = numpr.find(q("numId"))
    if nid_el is not None:
        nid = _inteiro(nid_el.get(q("val")))
        if nid == 0:
            out["lista"] = 0
        elif nid is not None and ctx.numeracao is not None and nid in ctx.numeracao.instancias:
            out["lista"] = nid
        else:
            out["lista"] = 0
            c.somar("LISTA")
    ilvl_el = numpr.find(q("ilvl"))
    if ilvl_el is not None:
        ilvl = _inteiro(ilvl_el.get(q("val")))
        if ilvl is None or not 0 <= ilvl < mod_numeracao.NIVEIS:
            c.somar("LISTA_NIVEL")
            ilvl = 0 if ilvl is None else min(max(ilvl, 0), mod_numeracao.NIVEIS - 1)
        out["lista_nivel"] = ilvl


#: Destino do texto que esta' no codigo de um campo (entre o begin e o separate): nao
#: aparece no Word, e nao entra no fluxo.
_FORA_DO_FLUXO = object()


def _destino_do_texto(ctx: "_Contexto"):
    """None = o texto vai para o fluxo; um dict = o resultado de um campo de dentro da
    instrucao; _FORA_DO_FLUXO = o codigo de um campo (o Word nao mostra)."""
    if not ctx.campos:
        return None
    topo = ctx.campos[-1]
    if topo["fase"] == "instr":
        return _FORA_DO_FLUXO
    if topo["no_codigo"]:
        return topo
    return None


class _Pedacos:
    """Texto de um w:r em montagem. Uma imagem ou um objeto no meio fecha o trecho de texto."""

    def __init__(self, base: Run, saida: list[Run], rpr=None, ctx=None) -> None:
        self.base = base
        self.saida = saida
        self.partes: list[str] = []
        #: o w:rPr do run, que vai junto no XML do objeto opaco
        self.rpr = rpr
        self.ctx = ctx

    def append(self, texto: str) -> None:
        self.partes.append(texto)

    def descarregar(self) -> None:
        texto = "".join(self.partes)
        self.partes = []
        if not texto:
            return
        destino = _destino_do_texto(self.ctx) if self.ctx is not None else None
        if destino is None:
            self.saida.append(replace(self.base, texto=texto))
        elif destino is _FORA_DO_FLUXO:
            # Texto no codigo de um campo: o Word nao mostra. Fica no fluxo so' ate' o
            # codigo fechar (separate ou end); se o campo nunca fechar (arquivo cortado),
            # o texto continua no documento.
            run = replace(self.base, texto=texto)
            self.saida.append(run)
            dono = next(e for e in self.ctx.campos if e["fase"] == "instr")
            dono["provisorios"].append((self.saida, run))
        else:
            destino["resultado"].append(texto)

    def _no_fluxo(self) -> bool:
        if self.ctx is None or _destino_do_texto(self.ctx) is None:
            return True
        self.ctx.coletor.somar("CAMPO")  # objeto dentro do codigo de um campo
        return False

    def imagem(self, imagem: Imagem) -> None:
        self.descarregar()
        if self._no_fluxo():
            run = run_de_imagem(imagem)
            # O rPr do run da imagem (borda em volta, noProof) vai junto pelos extras (0.1.5).
            run.extras = self.base.extras
            self.saida.append(run)

    def objeto(self, item, ctx: "_Contexto") -> None:
        self.descarregar()
        if not self._no_fluxo():
            return
        run = _opaco(item, self.rpr, ctx)
        if run is not None:
            self.saida.append(run)


def _ler_run(r, ctx: _Contexto, saida: list[Run]) -> None:
    run = Run()
    rpr = r.find(q("rPr"))
    if rpr is not None:
        _ler_rpr(rpr, run, ctx)
    pedacos = _Pedacos(run, saida, rpr, ctx)
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
        _fld_char(f, partes, ctx)
    elif loc == "instrText":
        if ctx.campos and ctx.campos[-1]["fase"] == "instr":
            topo = ctx.campos[-1]
            if "rpr_codigo" not in topo:
                # 0.1.6: o rPr do run do codigo (o do primeiro instrText) volta ao arquivo.
                topo["rpr_codigo"] = fx_props.rpr_canonico(partes.rpr, ctx.estilo_existe)
            texto = f.text or ""
            topo["tamanho"] += len(texto)
            if topo["tamanho"] > ctx.lim["instrucao_campo"]:
                topo["ignorado"] = True  # instrucao enorme: arquivo estranho
            else:
                topo["codigo"].append(texto)
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
        # Comentario (0.1.6): a referencia vira marca no fluxo, com a formatacao do run (o
        # rStyle "CommentReference"). Fora do corpo, ou sem o comentario, nao vale.
        ident = _id_de_comentario(f, ctx)
        if ident is not None and _destino_do_texto(ctx) is None:
            partes.descarregar()
            partes.saida.append(replace(partes.base, texto="",
                                        marca=MarcaComentario("referencia", ident)))
    elif loc == "annotationRef":
        return  # a marca do inicio do comentario (dentro do comments.xml): o escritor a refaz
    elif loc in ("footnoteReference", "endnoteReference"):
        c.somar("NOTA")
    else:
        c.somar("ELEMENTO_DESCONHECIDO")


#: Marca de inicio ainda sem o codigo (o end nao chegou). Sobra so' em campo sem fim, e
#: `_limpar_marcas` a tira, com o aviso CAMPO.
def _marca_pendente() -> MarcaCampo:
    return MarcaCampo("inicio", None)


def _juntar_codigo(codigo: list) -> tuple:
    """Pedacos da instrucao com os textos vizinhos juntos (a gravacao faz um instrText por
    pedaco: a releitura da' o mesmo codigo)."""
    saida: list = []
    for pedaco in codigo:
        if isinstance(pedaco, str) and saida and isinstance(saida[-1], str):
            saida[-1] += pedaco
        elif pedaco != "":
            saida.append(pedaco)
    return tuple(saida)


def _fld_char(f, partes: _Pedacos, ctx: _Contexto) -> None:
    """Campo complexo: begin, instrText, separate, resultado, end (podem estar em runs e
    paragrafos diferentes).

    0.1.3: todo campo e' preservado. No fluxo, o begin vira uma marca de inicio com o
    codigo (`Campo`) e o end uma marca de fim; o resultado fica entre as duas, como texto
    editavel. Campo dentro da instrucao de outro (o PAGE de um IF) vai para o codigo do de
    fora. PAGE e NUMPAGES com o begin e o end no mesmo paragrafo, sem nada dentro, continuam
    um run com `campo` (o valor muda em cada pagina na tela). Acima dos limites (profundidade,
    quantidade, tamanho da instrucao) o campo nao e' preservado: o resultado fica como texto,
    com o aviso CAMPO.
    """
    tipo = _atr(f, "fldCharType")
    partes.descarregar()
    pilha = ctx.campos
    lim = ctx.lim
    if tipo == "begin":
        no_codigo = bool(pilha) and (pilha[-1]["fase"] == "instr" or pilha[-1]["no_codigo"])
        ignorado = (len(pilha) >= lim["campo_profundidade"] or ctx.total_campos >= lim["campos"]
                    or (no_codigo and pilha[-1]["ignorado"]))
        entrada = {"fase": "instr", "codigo": [], "no_codigo": no_codigo, "ignorado": ignorado,
                   "sujo": _onoff_atr(f, "dirty"), "travado": _onoff_atr(f, "fldLock"),
                   "extra": etree.tostring(f) if len(f) else b"", "resultado": [],
                   "separou": False, "tamanho": 0, "run": None, "saida": partes.saida,
                   "provisorios": [],
                   "rpr_begin": fx_props.rpr_canonico(partes.rpr, ctx.estilo_existe)}
        if not ignorado:
            ctx.total_campos += 1
            if not no_codigo:
                marca = replace(partes.base, texto="", marca=_marca_pendente())
                partes.saida.append(marca)
                entrada["run"] = marca
        pilha.append(entrada)
    elif tipo == "separate":
        if pilha and pilha[-1]["fase"] == "instr":
            pilha[-1]["fase"] = "resultado"
            pilha[-1]["separou"] = True
            pilha[-1]["rpr_separador"] = fx_props.rpr_canonico(partes.rpr, ctx.estilo_existe)
            _descartar_provisorios(pilha[-1], ctx)
    elif tipo == "end":
        if not pilha:
            return  # end sem begin: nao ha' campo a desfazer
        e = pilha.pop()
        _descartar_provisorios(e, ctx)
        if e["ignorado"]:
            if e["run"] is None:
                ctx.coletor.somar("CAMPO")
            # Com marca no fluxo, `_limpar_marcas` a tira e conta o aviso.
            return
        rpr_codigo = e.get("rpr_codigo")
        rpr_separador = e.get("rpr_separador")
        campo = Campo(codigo=_juntar_codigo(e["codigo"]), sujo=e["sujo"], travado=e["travado"],
                      sem_resultado=not e["separou"],
                      resultado="".join(e["resultado"]) if e["no_codigo"] else "",
                      extra=e["extra"],
                      rpr_codigo=rpr_codigo if rpr_codigo != e["rpr_begin"] else None,
                      rpr_separador=rpr_separador if rpr_separador != e["rpr_begin"] else None)
        if e["no_codigo"]:
            pai = pilha[-1] if pilha else None
            if pai is not None and pai["fase"] == "instr":
                pai["codigo"].append(campo)
            elif pai is not None:
                # Campo no resultado de um campo da instrucao: fica so' o texto.
                pai["resultado"].append(campo.resultado)
                ctx.coletor.somar("CAMPO")
            return
        inicio = e["run"]
        saida = partes.saida
        if _vira_campo_de_pagina(campo, inicio, e["saida"], saida):
            indice = next(i for i, r in enumerate(saida) if r is inicio)
            resultado = saida[indice + 1:]
            base = resultado[0] if resultado else inicio
            texto = "".join(r.texto for r in resultado).replace("\f", "")
            del saida[indice:]
            saida.append(replace(base, texto=texto, campo=normalizar_instrucao(campo.instrucao()),
                                 imagem=None, marca=None))
            return
        ctx.pares += 1
        inicio.marca = MarcaCampo("inicio", campo, ctx.pares)
        saida.append(replace(partes.base, texto="", marca=MarcaCampo("fim", par=ctx.pares)))


def _descartar_provisorios(entrada: dict, ctx: _Contexto) -> None:
    """O codigo do campo fechou: o texto que estava nele sai do fluxo."""
    for lista, run in entrada["provisorios"]:
        indice = next((i for i, r in enumerate(lista) if r is run), None)
        if indice is not None:
            del lista[indice]
        else:
            ctx.descartar.append(run)  # ja' foi para outro paragrafo: sai na limpeza
    entrada["provisorios"] = []


def _vira_campo_de_pagina(campo: Campo, inicio: Run, saida_inicio: list, saida: list) -> bool:
    """PAGE ou NUMPAGES simples: begin e end no mesmo paragrafo, resultado so' de texto."""
    if saida_inicio is not saida or not all(isinstance(x, str) for x in campo.codigo):
        return False
    if campo.sem_resultado or campo.extra or campo.travado:
        return False
    if tipo_do_campo(normalizar_instrucao(campo.instrucao())) is None:
        return False
    indice = next((i for i, r in enumerate(saida) if r is inicio), None)
    if indice is None:
        return False
    return not any(r.eh_objeto() or r.campo is not None or r.marca is not None or r.link is not None
                   for r in saida[indice + 1:])


def _limpar_marcas(blocos: list, ctx: _Contexto) -> None:
    """Tira as marcas de inicio de campo que nunca fecharam (arquivo cortado, ou campo
    acima dos limites): o resultado fica como texto, com o aviso CAMPO."""
    descartar = {id(r) for r in ctx.descartar}
    for p in paragrafos_de(blocos):
        if descartar:
            p.runs = [r for r in p.runs if id(r) not in descartar]
        if any(isinstance(r.marca, MarcaCampo) and r.marca.tipo == "inicio" and r.marca.campo is None
               for r in p.runs):
            novos = []
            for r in p.runs:
                if isinstance(r.marca, MarcaCampo) and r.marca.tipo == "inicio" \
                        and r.marca.campo is None:
                    ctx.coletor.somar("CAMPO")
                    continue
                novos.append(r)
            p.runs = novos


def _ler_link(h, ctx: _Contexto) -> Link | None:
    """O destino de um w:hyperlink. None (com aviso, se havia endereco) quando nao da' para
    guardar: relacao que nao existe ou acima do limite de links."""
    rid = h.get(q("id", R_NS))
    ancora = _atr(h, "anchor") or None
    url = None
    if rid:
        rel = ctx.relacoes.get(rid)
        if rel is not None and rel[2] and rel[0].endswith("/hyperlink") \
                and len(rel[1]) <= ctx.lim["link_tamanho"]:
            url = rel[1]
        else:
            ctx.coletor.somar("HIPERLINK")  # o endereco se perde (fica o marcador, se houver)
            if ancora is None:
                return None
    if url is None and ancora is None:
        return None
    if ancora is not None and len(ancora) > ctx.lim["link_tamanho"]:
        ctx.coletor.somar("HIPERLINK")
        return None
    if ctx.total_links >= ctx.lim["hiperlinks"]:
        ctx.coletor.somar("HIPERLINK")
        return None
    ctx.total_links += 1
    historico = _atr(h, "history")
    return Link(url=url, ancora=ancora, dica=_atr(h, "tooltip") or None,
                historico=None if historico is None else historico.lower() in ("1", "true", "on"),
                quadro=_atr(h, "tgtFrame") or None, local=_atr(h, "docLocation") or None)


def _marcador(f, loc: str, ctx: _Contexto, saida: list) -> None:
    """w:bookmarkStart e w:bookmarkEnd viram marcas no fluxo, pelo nome."""
    ident = _atr(f, "id")
    if loc == "bookmarkStart":
        nome = _atr(f, "name")
        if not nome or ident is None:
            return  # marcador sem nome nao e' alcancavel: nada se perde
        if (nome in ctx.marcadores_nomes or len(ctx.marcadores_nomes) >= ctx.lim["marcadores"]
                or len(nome) > 255):
            ctx.coletor.somar("MARCADOR")
            return
        ctx.marcadores_nomes.add(nome)
        ctx.marcadores_ids[ident] = nome
        saida.append(Run(marca=Marcador("inicio", nome)))
    else:
        nome = ctx.marcadores_ids.pop(ident, None) if ident is not None else None
        if nome is not None:
            saida.append(Run(marca=Marcador("fim", nome)))


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
    recorte = None
    if blip.getparent() is not None:
        src = blip.getparent().find("{%s}srcRect" % A_NS)
        if src is not None and any((src.get(k) or "0") != "0" for k in "ltrb"):
            # Recorte (0.1.5): guardado e aplicado na tela. Valor que nao e' numero, ou fora
            # de -1000% a 100%, nao vale: a imagem inteira, com aviso.
            valores = tuple(_inteiro(src.get(k) or "0") for k in "ltrb")
            if all(v is not None and -1000000 <= v <= 100000 for v in valores):
                recorte = valores
            else:
                c.somar("FORMATACAO")
    xfrm = pic.find("{%s}spPr/{%s}xfrm" % (PIC_NS, A_NS))
    if xfrm is not None and (xfrm.get("rot") not in (None, "0") or xfrm.get("flipH") in ("1", "true")
                             or xfrm.get("flipV") in ("1", "true")):
        c.somar("FORMATACAO")  # rotacao ou espelhamento
    doc_pr = quadro.find("{%s}docPr" % WP_NS)
    descricao = (doc_pr.get("descr") or "") if doc_pr is not None else ""
    return Imagem(dados=dados, formato=formato, largura_emu=cx, altura_emu=cy,
                  descricao=descricao, recorte=recorte)


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
            link = _ler_link(f, ctx)
            dentro: list[Run] = []
            _runs_em(f, ctx, dentro)
            if link is not None:
                for r in dentro:
                    if r.link is None and not isinstance(r.marca, MarcaConteudo):
                        r.link = link
            saida.extend(dentro)
        elif loc in ("bookmarkStart", "bookmarkEnd"):
            if _destino_do_texto(ctx) is None:
                _marcador(f, loc, ctx, saida)
        elif loc in ("commentRangeStart", "commentRangeEnd"):
            ident = _id_de_comentario(f, ctx)
            if ident is not None and _destino_do_texto(ctx) is None:
                saida.append(Run(marca=MarcaComentario(
                    "inicio" if loc == "commentRangeStart" else "fim", ident)))
        elif loc == "fldSimple":
            _campo_simples(f, ctx, saida)
        elif loc in ("ins", "moveTo"):
            c.somar("REVISAO")
            _runs_em(f, ctx, saida)
        elif loc in ("del", "moveFrom"):
            c.somar("REVISAO")
        elif loc == "sdt":
            _conteudo_de_run(f, ctx, saida)
        elif loc in ("smartTag", "customXml", "dir", "bdo"):
            _runs_em(f, ctx, saida)
        elif loc in ("oMath", "oMathPara"):
            c.somar("OBJETO_PERDIDO")  # equacao no namespace errado: nao ha' o que preservar
        elif loc in _IGNORADOS_INLINE:
            continue
        else:
            c.somar("ELEMENTO_DESCONHECIDO")


def _conteudo_de_run(f, ctx: _Contexto, saida: list) -> None:
    """w:sdt dentro do paragrafo (0.1.5): marcas de inicio (com o sdtPr) e de fim no fluxo, o
    conteudo entre elas. No codigo de um campo, ou acima do limite, o controle e' achatado
    (o texto fica), com aviso."""
    no_fluxo = _destino_do_texto(ctx) is None and ctx.total_conteudos < ctx.lim["conteudos"]
    conteudo = f.find(q("sdtContent"))
    dentro: list[Run] = []
    if conteudo is not None:
        _runs_em(conteudo, ctx, dentro)
    if not no_fluxo:
        ctx.coletor.somar("CONTEUDO_CONTROLADO")
        saida.extend(dentro)
        return
    ctx.total_conteudos += 1
    ctx.pares += 1
    props = fx_props.propriedades_de_sdt(f, ctx.estilo_existe, ctx.coletor)
    saida.append(Run(marca=MarcaConteudo("inicio", props, False, ctx.pares)))
    saida.extend(dentro)
    saida.append(Run(marca=MarcaConteudo("fim", par=ctx.pares)))


def _campo_simples(f, ctx: _Contexto, saida: list) -> None:
    """w:fldSimple. PAGE e NUMPAGES simples viram run com `campo`; o resto vira o mesmo
    campo complexo que o Word grava (marca de inicio, resultado, marca de fim)."""
    bruta = _atr(f, "instr") or ""
    instrucao = normalizar_instrucao(bruta)
    dentro: list[Run] = []
    _runs_em(f, ctx, dentro)
    if tipo_do_campo(instrucao) is not None and not any(
            r.eh_objeto() or r.campo is not None or r.marca is not None for r in dentro):
        base = dentro[0] if dentro else Run()
        texto = "".join(r.texto for r in dentro).replace("\f", "")
        saida.append(replace(base, texto=texto, campo=instrucao, imagem=None))
        return
    no_codigo = _destino_do_texto(ctx) is not None
    if (no_codigo or ctx.total_campos >= ctx.lim["campos"] or len(ctx.campos) >= ctx.lim["campo_profundidade"]
            or len(bruta) > ctx.lim["instrucao_campo"]):
        ctx.coletor.somar("CAMPO")
        if not no_codigo:
            saida.extend(dentro)
        return
    ctx.total_campos += 1
    base = next((r for r in dentro if r.marca is None and not r.eh_objeto()), Run())
    campo = Campo(codigo=(bruta,) if bruta else (), sujo=_onoff_atr(f, "dirty"),
                  travado=_onoff_atr(f, "fldLock"))
    neutro = replace(base, texto="", campo=None, imagem=None, objeto=None, marca=None, link=None)
    ctx.pares += 1
    saida.append(replace(neutro, marca=MarcaCampo("inicio", campo, ctx.pares)))
    saida.extend(dentro)
    saida.append(replace(neutro, marca=MarcaCampo("fim", par=ctx.pares)))


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
    # A lista ligada pelo estilo (List Bullet, Titulo numerado) fica no estilo: o paragrafo
    # herda (0.1.4). O numbering.xml de origem volta inteiro.
    # Marcadores que estavam entre paragrafos (no corpo ou na celula) entram no comeco deste.
    runs: list[Run] = ctx.marcas_pendentes
    ctx.marcas_pendentes = []
    _runs_em(p, ctx, runs)
    if ctx.nivel_tabela > 0:
        # Quebra de pagina dentro de celula: o EditDoc nao pagina dentro da tabela por
        # quebra manual. Vira quebra de linha, com aviso.
        quebras = sum(r.texto.count("\f") for r in runs if not r.eh_objeto())
        quebras += 1 if props.pop("quebra_antes", False) else 0
        if quebras:
            ctx.coletor.somar("QUEBRA_EM_TABELA", quebras)
            for r in runs:
                if not r.eh_objeto() and "\f" in r.texto:
                    r.texto = r.texto.replace("\f", "\n")  # no lugar: a marca de campo e' o mesmo objeto
    saida = [Paragrafo(runs=[], **props)]
    for run in runs:
        if run.eh_objeto() or run.campo is not None or run.marca is not None:
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
            _conteudo_de_bloco(f, paras, ctx, achatar)
        elif loc in ("del", "moveFrom"):
            c.somar("REVISAO")
        elif loc in ("bookmarkStart", "bookmarkEnd"):
            _marcador(f, loc, ctx, ctx.marcas_pendentes)
        elif loc in ("commentRangeStart", "commentRangeEnd"):
            # Ancora entre paragrafos (0.1.6): o fim fica no fim do paragrafo de cima; o
            # inicio, no comeco do paragrafo seguinte (como os marcadores).
            ident = _id_de_comentario(f, ctx)
            if ident is not None:
                marca = Run(marca=MarcaComentario(
                    "inicio" if loc == "commentRangeStart" else "fim", ident))
                if loc == "commentRangeEnd" and paras and isinstance(paras[-1], Paragrafo):
                    paras[-1].runs.append(marca)
                else:
                    ctx.marcas_pendentes.append(marca)
        elif loc in _IGNORADOS_BLOCO or loc == "tblPrEx":
            continue
        else:
            c.somar("ELEMENTO_DESCONHECIDO")


def _conteudo_de_bloco(f, paras: list, ctx: _Contexto, achatar: bool) -> None:
    """w:sdt que envolve paragrafos inteiros (o do sumario, 0.1.5): a marca de inicio entra no
    comeco do primeiro paragrafo e a de fim no fim do ultimo; o escritor grava o w:sdt por
    fora deles. Controle vazio, que comeca ou termina numa tabela, ou acima do limite, e'
    achatado (o conteudo fica), com aviso."""
    conteudo = f.find(q("sdtContent"))
    dentro: list[Bloco] = []
    if conteudo is not None:
        _blocos(conteudo, dentro, ctx, achatar)
    if (achatar or not dentro or not isinstance(dentro[0], Paragrafo)
            or not isinstance(dentro[-1], Paragrafo)
            or ctx.total_conteudos >= ctx.lim["conteudos"]):
        ctx.coletor.somar("CONTEUDO_CONTROLADO")
        paras.extend(dentro)
        return
    ctx.total_conteudos += 1
    ctx.pares += 1
    props = fx_props.propriedades_de_sdt(f, ctx.estilo_existe, ctx.coletor)
    dentro[0].runs.insert(0, Run(marca=MarcaConteudo("inicio", props, True, ctx.pares)))
    dentro[-1].runs.append(Run(marca=MarcaConteudo("fim", bloco=True, par=ctx.pares)))
    paras.extend(dentro)


def _fechar_historia(blocos: list, ctx: _Contexto) -> None:
    """Fim do corpo, de um cabecalho ou de um rodape: campos que nao fecharam, marcadores
    que ficaram entre paragrafos no fim (vao para o ultimo paragrafo)."""
    _fechar_campos(ctx)
    _limpar_marcas(blocos, ctx)
    ctx.descartar = []
    if ctx.marcas_pendentes:
        ultimo = None
        for p in paragrafos_de(blocos):
            ultimo = p
        if ultimo is None:
            ultimo = Paragrafo()
            blocos.append(ultimo)
        ultimo.runs.extend(ctx.marcas_pendentes)
        ctx.marcas_pendentes = []


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
                # 0.1.6: o estilo volta como veio (a referencia sem definicao tambem).
                if estilo_id != fx_estilos.ESTILO_TABELA and ctx.estilo_existe(estilo_id, "tabela"):
                    tabela.estilo = estilo_id  # "Table Grid" e' o None (o padrao do escritor)
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
                if loc == "tblPrChange":
                    c.somar("REVISAO")
                continue
            # tblpPr (tabela flutuante), shd, tblCellSpacing, bidiVisual, legenda...: desde a
            # 0.1.5 vao para os extras da tabela e voltam ao arquivo.
        tabela.extras = fx_props.ler_extras_tabela(tbl_pr)
    # Bordas efetivas: as do estilo (cadeia basedOn), depois as diretas. Lado sem
    # borda nenhuma fica explicito como "nenhuma": o escritor grava os seis lados.
    bordas = _bordas_do_estilo(ctx, estilo_id)
    if diretas is not None:
        _ler_bordas(diretas, bordas, ctx)
    for campo in ("sup", "inf", "esq", "dir", "horizontal", "vertical"):
        if getattr(bordas, campo) is None:
            setattr(bordas, campo, Borda(estilo="nenhuma", oitavos_pt=0))
    tabela.bordas = bordas
    # Formatacao condicional do estilo (linha de cabecalho, faixas...): desde a 0.1.6 o estilo e
    # o tblLook voltam ao arquivo; o fundo de cada celula vai para a tela (`_fundos_do_estilo`).
    cadeia = _estilo_de_tabela(ctx, estilo_id)

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
    if cadeia:
        _fundos_do_estilo(tabela, tbl_pr, cadeia)
    return tabela


#: Tipos de w:tblStylePr na ordem em que o Word os aplica (o de depois vence).
_ORDEM_CONDICIONAL = ("band1Vert", "band2Vert", "band1Horz", "band2Horz", "firstCol", "lastCol",
                      "firstRow", "lastRow", "nwCell", "neCell", "swCell", "seCell")
#: tblLook legado (w:val em hexa): bit -> atributo.
_LOOK_BITS = {0x0020: "firstRow", 0x0040: "lastRow", 0x0080: "firstColumn", 0x0100: "lastColumn",
              0x0200: "noHBand", 0x0400: "noVBand"}


def _look(tbl_pr) -> dict:
    """O que o w:tblLook liga. Sem ele, o padrao do Word para tabela nova (04A0)."""
    el = tbl_pr.find(q("tblLook")) if tbl_pr is not None else None
    saida = {"firstRow": True, "lastRow": False, "firstColumn": True, "lastColumn": False,
             "noHBand": False, "noVBand": True}
    if el is None:
        return saida
    val = _atr(el, "val")
    if val is not None and all(_atr(el, k) is None for k in saida):
        try:
            bits = int(val, 16)
        except ValueError:
            return saida
        return {nome: bool(bits & bit) for bit, nome in _LOOK_BITS.items()}
    for k in saida:
        v = _atr(el, k)
        if v is not None:
            saida[k] = v.lower() in ("1", "true", "on")
    return saida


def _fundos_do_estilo(tabela: Tabela, tbl_pr, cadeia: list) -> None:
    """O fundo que a formatacao condicional do estilo da' a cada celula (0.1.6), para a tela:
    o da tabela inteira, as faixas alternadas, a primeira e a ultima coluna e linha e os cantos,
    nessa ordem (o de depois vence), respeitando o tblLook. So' o sombreamento: o negrito do
    cabecalho viraria formatacao direta ao salvar (registrado como limite)."""
    look = _look(tbl_pr)
    banda_linhas = banda_colunas = 1
    fundos: dict = {}
    base = None
    for estilo in reversed(cadeia):  # da base para o proprio: o proprio vence
        tb = estilo.find(q("tblPr"))
        if tb is not None:
            for nome, alvo in (("tblStyleRowBandSize", "l"), ("tblStyleColBandSize", "c")):
                el = tb.find(q(nome))
                v = _inteiro(_atr(el, "val")) if el is not None else None
                if v is not None and 1 <= v <= 1000:
                    if alvo == "l":
                        banda_linhas = v
                    else:
                        banda_colunas = v
        shd = estilo.find(q("tcPr") + "/" + q("shd"))
        if shd is not None:
            base = fx_props.cor_de_sombreamento(shd)
        for cond in estilo.findall(q("tblStylePr")):
            tipo = _atr(cond, "type")
            shd = cond.find(q("tcPr") + "/" + q("shd"))
            if tipo in _ORDEM_CONDICIONAL and shd is not None:
                fundos[tipo] = fx_props.cor_de_sombreamento(shd)
    if base is None and not fundos:
        return
    if tbl_pr is not None:
        for nome in ("tblStyleRowBandSize", "tblStyleColBandSize"):
            el = tbl_pr.find(q(nome))
            v = _inteiro(_atr(el, "val")) if el is not None else None
            if v is not None and 1 <= v <= 1000:
                if nome == "tblStyleRowBandSize":
                    banda_linhas = v
                else:
                    banda_colunas = v
    n_linhas = len(tabela.linhas)
    n_colunas = len(tabela.colunas_tw)
    for r, linha in enumerate(tabela.linhas):
        coluna = 0
        for celula in linha.celulas:
            fim = coluna + max(1, celula.colunas) - 1
            primeira_l = look["firstRow"] and r == 0
            ultima_l = look["lastRow"] and r == n_linhas - 1
            primeira_c = look["firstColumn"] and coluna == 0
            ultima_c = look["lastColumn"] and fim == n_colunas - 1
            vale = set()
            if not look["noVBand"] and not primeira_c and not ultima_c:
                k = (coluna - (1 if look["firstColumn"] else 0)) // banda_colunas
                vale.add("band1Vert" if k % 2 == 0 else "band2Vert")
            if not look["noHBand"] and not primeira_l and not ultima_l:
                k = (r - (1 if look["firstRow"] else 0)) // banda_linhas
                vale.add("band1Horz" if k % 2 == 0 else "band2Horz")
            for nome, ok in (("firstCol", primeira_c), ("lastCol", ultima_c),
                             ("firstRow", primeira_l), ("lastRow", ultima_l),
                             ("nwCell", primeira_l and primeira_c), ("neCell", primeira_l and ultima_c),
                             ("swCell", ultima_l and primeira_c), ("seCell", ultima_l and ultima_c)):
                if ok:
                    vale.add(nome)
            fundo = base
            for tipo in _ORDEM_CONDICIONAL:
                if tipo in vale and tipo in fundos:
                    fundo = fundos[tipo]
            celula.fundo_estilo = fundo
            coluna = fim + 1


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
            elif loc in ("gridBefore", "gridAfter"):
                c.somar("FORMATACAO")  # a grade da linha: o leitor completa com celula vazia
            elif loc in ("ins", "del", "trPrChange"):
                c.somar("REVISAO")
            # cantSplit, jc, hidden, tblCellSpacing...: extras da linha (0.1.5).
        linha.extras = fx_props.ler_extras_tabela(tr_pr)
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
            elif loc in ("cellIns", "cellDel", "cellMerge", "tcPrChange"):
                c.somar("REVISAO")
            # tcMar, textDirection, noWrap...: extras da celula (0.1.5).
        celula.extras = fx_props.ler_extras_tabela(tc_pr)
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
    ctx.historia = "faixa"
    try:
        blocos: list[Bloco] = []
        _blocos(raiz, blocos, ctx)
    finally:
        ctx.relacoes = relacoes_doc
        ctx.ignoraveis = ignoraveis_doc
        ctx.historia = "corpo"
    _fechar_historia(blocos, ctx)
    return blocos


def _fechar_campos(ctx: _Contexto) -> None:
    """Campo aberto que nunca fechou (arquivo cortado): o texto ficou, o campo nao.

    O campo com marca de inicio no fluxo e' contado por `_limpar_marcas`, que tira a marca.
    """
    for campo in ctx.campos:
        if campo["run"] is None:
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


def _numeracao(dados: bytes, nome: str, ctx_lim: dict, coletor: Coletor, relacoes: dict,
               capturador) -> "mod_numeracao.Numeracao | None":
    """O catalogo do numbering.xml (0.1.4), com o fecho das imagens dos marcadores de figura.

    None (aviso LISTA nos itens que citam a numeracao) se a parte passa dos limites.
    """
    raiz = _parse(dados, nome, ctx_lim["profundidade"])
    if _profundidade(raiz) > ctx_lim["profundidade"]:
        raise ErroDocx("XML_PROFUNDIDADE_EXCEDIDA", nome)
    partes: dict = {}
    for _rid, (_tipo, alvo, externo) in relacoes.items():
        if not externo and capturador is not None:
            capturador._fechar(alvo, partes, 1)
    partes = {k: v for k, v in partes.items() if v is not None}
    try:
        cat = fx_numeracao.ler(dados, raiz, ctx_lim, relacoes, partes, coletor)
    except fx_numeracao.NumeracaoInvalida:
        return None
    usados = set()
    for el in etree.fromstring(cat.xml_original, etree.XMLParser(
            resolve_entities=False, no_network=True, load_dtd=False)).iter():
        for chave, valor in el.attrib.items():
            if chave.startswith("{%s}" % R_NS):
                usados.add(valor)
    cat.relacoes = tuple((rid, tipo, alvo, externo) for rid, (tipo, alvo, externo)
                         in sorted(relacoes.items()) if rid in usados)
    alcancadas: dict = {}
    for _rid, _tipo, alvo, externo in cat.relacoes:
        if not externo:
            _alcance(alvo, partes, alcancadas)
    cat.partes = tuple(alcancadas[n] for n in sorted(alcancadas))
    return cat


def _alcance(nome: str, partes: dict, saida: dict) -> None:
    if nome in saida or nome not in partes:
        return
    saida[nome] = partes[nome]
    for _rid, _tipo, alvo, externo in partes[nome].relacoes:
        if not externo:
            _alcance(alvo, partes, saida)


def _tab_padrao(config) -> int:
    """w:defaultTabStop do settings.xml (twips). Sem ele, 720, como o esquema."""
    el = config.find(q("defaultTabStop")) if config is not None else None
    valor = _inteiro(_atr(el, "val")) if el is not None else None
    return valor if valor is not None and 0 < valor <= 31680 else 720


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


# -- comentarios (0.1.6) ------------------------------------------------------------------

def _id_de_comentario(f, ctx: _Contexto) -> int | None:
    """O w:id da ancora, se ela vale: no corpo e citando um comentario lido."""
    ident = _inteiro(_atr(f, "id"))
    if ident is None or ctx.historia != "corpo" or ident not in ctx.comentarios_ids:
        return None
    return ident


def _r_ids(el) -> list[str]:
    return [valor for x in el.iter() if isinstance(x.tag, str)
            for chave, valor in x.attrib.items() if chave.startswith("{%s}" % R_NS)]


def _original_do_comentario(el, relacoes: dict) -> tuple[bytes | None, tuple]:
    """O XML de origem do comentario e as relacoes externas (links) que ele cita. Relacao
    interna (imagem) ou quebrada: o comentario e' gerado de novo pelo escritor."""
    usadas = []
    for rid in _r_ids(el):
        rel = relacoes.get(rid)
        if rel is None or not rel[2]:
            return None, ()
        if (rid, rel[0], rel[1]) not in usadas:
            usadas.append((rid, rel[0], rel[1]))
    return etree.tostring(el), tuple(usadas)


def _ler_comentarios(relacoes: dict, ctx: _Contexto, ler_parte, relacoes_de, tamanho_de,
                     profundidade: int):
    """word/comments.xml e as partes estendidas -> Comentarios (sem os que nao tem ancora: isso
    se ve depois do corpo). None se o documento nao tem comentarios."""
    alvos: dict = {}
    tipos: dict = {}
    for _rid, (tipo, alvo, externo) in sorted(relacoes.items()):
        chave = fx_comentarios.SUFIXOS.get(tipo.rstrip("/").rsplit("/", 1)[-1])
        if chave is None or externo or alvo not in ctx.nomes or chave in alvos:
            continue
        alvos[chave] = alvo
        tipos[chave] = tipo
    if "comentarios" not in alvos:
        return None
    c = ctx.coletor
    lim = ctx.lim
    alvo = alvos["comentarios"]
    _validar_nome(alvo)
    try:
        if tamanho_de(alvo) > lim["comentarios_bytes"]:
            raise ValueError("comments.xml grande demais")
        dados = ler_parte(alvo)
        raiz = _parse(dados, alvo, profundidade)
        if _local(raiz) != (W, "comments") or _profundidade(raiz) > profundidade:
            raise ValueError("comments.xml invalido")
    except (ErroDocx, ValueError):
        c.somar("COMENTARIO")
        return None
    elementos = [el for el in raiz if _local(el) == (W, "comment")]
    if len(elementos) > lim["comentarios"]:
        c.somar("COMENTARIO", len(elementos))
        return None

    def parte_estendida(chave):
        nome = alvos.get(chave)
        if nome is None:
            return None, None
        try:
            _validar_nome(nome)
            bruto = ler_parte(nome)
            return bruto, _parse(bruto, nome, profundidade)
        except ErroDocx:
            return None, None

    xml_est, raiz_est = parte_estendida("estendido")
    xml_ids, raiz_ids = parte_estendida("ids")
    xml_ext, raiz_ext = parte_estendida("extensivel")
    estendido = fx_comentarios.ler_estendido(raiz_est)
    duraveis = fx_comentarios.ler_ids(raiz_ids)
    datas_utc = fx_comentarios.ler_extensivel(raiz_ext)

    relacoes_doc, ignoraveis_doc = ctx.relacoes, ctx.ignoraveis
    ctx.relacoes = relacoes_de(alvo)
    ctx.ignoraveis = opacos.ignoraveis_da_raiz(raiz)
    ctx.historia = "comentario"
    itens: list = []
    pais: dict = {}
    try:
        for el in elementos:
            ident = _inteiro(_atr(el, "id"))
            tamanho = len(etree.tostring(el))
            if ident is None or ident in ctx.comentarios_ids or tamanho > lim["comentario_bytes"] \
                    or len(el.findall(q("p"))) > lim["comentario_paragrafos"]:
                c.somar("COMENTARIO")
                continue
            blocos: list[Bloco] = []
            _blocos(el, blocos, ctx)
            _fechar_historia(blocos, ctx)
            if not blocos:
                blocos = [Paragrafo()]
            blocos = normalizar(Documento(paragrafos=blocos)).paragrafos
            para = fx_comentarios.para_id_do_comentario(el)
            duravel = duraveis.get(para) if para else None
            pai_para, resolvido = estendido.get(para, (None, False)) if para else (None, False)
            ctx.comentarios_ids.add(ident)
            pais[ident] = pai_para
            original, rels_originais = _original_do_comentario(el, ctx.relacoes)
            itens.append(mod_comentarios.Comentario(
                id=ident, autor=(_atr(el, "author") or "")[:255],
                iniciais=(_atr(el, "initials") or "")[:9], data=(_atr(el, "date") or "")[:64],
                paragrafos=tuple(blocos), resolvido=resolvido, para_id=para,
                duravel=duravel, data_utc=datas_utc.get(duravel) if duravel else None,
                original=original, relacoes=rels_originais))
    finally:
        ctx.relacoes, ctx.ignoraveis = relacoes_doc, ignoraveis_doc
        ctx.historia = "corpo"
    # Respostas: paraIdParent -> o comentario daquele paraId. Ciclo ou fundo demais: sobe.
    por_para = {x.para_id: x.id for x in itens if x.para_id}
    ligados = {}
    for x in itens:
        pai = por_para.get(pais.get(x.id)) if pais.get(x.id) else None
        ligados[x.id] = pai if pai != x.id else None
    for x in itens:
        vistos = {x.id}
        atual = ligados[x.id]
        nivel = 0
        while atual is not None:
            if atual in vistos or nivel >= lim["comentario_profundidade"]:
                ligados[x.id] = None
                break
            vistos.add(atual)
            atual = ligados.get(atual)
            nivel += 1
    itens = [replace(x, pai=ligados[x.id]) for x in itens]
    return mod_comentarios.Comentarios(
        itens=itens, xml_comentarios=dados, xml_estendido=xml_est, xml_ids=xml_ids,
        xml_extensivel=xml_ext, originais=tuple(mod_comentarios.estado(x) for x in itens),
        tipos_rel=tipos)


def _comentarios_ancorados(cat, paras: list, coletor: Coletor):
    """So' ficam os comentarios com referencia no corpo; as ancoras dos outros saem. O que sai
    conta COMENTARIO (perda: o Word nao mostraria, mas o arquivo tinha)."""
    if cat is None:
        return None
    referidos = set()
    for p in paragrafos_de(paras):
        for r in p.runs:
            if isinstance(r.marca, MarcaComentario) and r.marca.tipo == "referencia":
                referidos.add(r.marca.id)
    fora = [x.id for x in cat.itens if x.id not in referidos]
    if fora:
        coletor.somar("COMENTARIO", len(fora))
        tirar = set(fora)
        for p in paragrafos_de(paras):
            if any(isinstance(r.marca, MarcaComentario) and r.marca.id in tirar for r in p.runs):
                p.runs = [r for r in p.runs if not (isinstance(r.marca, MarcaComentario)
                                                    and r.marca.id in tirar)]
        itens = [replace(x, pai=None if x.pai in tirar else x.pai)
                 for x in cat.itens if x.id not in tirar]
        cat = replace(cat, itens=itens)
    return cat if cat.itens else None


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
        numeracao = None
        dados_numeracao: tuple | None = None
        tab_padrao = 720
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
                dados_numeracao = (ler_parte(alvo), alvo)
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
                tab_padrao = _tab_padrao(config)
                pares = config.find(q("evenAndOddHeaders"))
                pares_impares = pares is not None and _onoff(pares)

        ctx = _Contexto(coletor, None, lim)
        ctx.relacoes = relacoes
        ctx.ler_parte = ler_parte
        ctx.nomes = nomes
        ctx.capturador = opacos.Capturador(
            ctx.lim, coletor, nomes, ler_parte, relacoes_de, tipo_de,
            lambda dados, nome: _parse(dados, nome, profundidade), ctx.midias)
        if dados_numeracao is not None:
            numeracao = _numeracao(dados_numeracao[0], dados_numeracao[1], ctx.lim, coletor,
                                   relacoes_de(dados_numeracao[1]), ctx.capturador)
            if numeracao is not None:
                numeracao.tab_padrao_tw = tab_padrao
        ctx.numeracao = numeracao
        # Lista dentro de caixa de texto: o numId continua valendo se a numeracao foi lida.
        ctx.capturador.listas_validas = None if numeracao is None else \
            set(numeracao.instancias)
        ctx.ignoraveis = opacos.ignoraveis_da_raiz(raiz)
        if estilos is not None:
            ctx.estilos, removidos = fx_estilos.ler_estilos(estilos, dados_estilos, fontes_tema,
                                                            numeracao, tema, coletor)
            if removidos:
                coletor.somar("FORMATACAO", removidos)
            for estilo in estilos.findall(q("style")):
                if _atr(estilo, "type") == "table" and _atr(estilo, "styleId"):
                    ctx.estilos_tabela[_atr(estilo, "styleId")] = estilo
                    if _onoff_atr(estilo, "default"):
                        ctx.estilo_tabela_padrao = _atr(estilo, "styleId")

        # Comentarios (0.1.6): o comments.xml antes do corpo (as ancoras citam os w:id).
        comentarios = _ler_comentarios(relacoes, ctx, ler_parte, relacoes_de, tamanho_de,
                                       profundidade)
        paras: list[Bloco] = []
        _blocos(corpo, paras, ctx)
        _fechar_historia(paras, ctx)
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

        # O resto do pacote (0.1.3): o que o EditDoc nao edita volta igual ao arquivo.
        reescritas = {alvo for tipo, alvo, externo in relacoes.values() if not externo and
                      tipo.rstrip("/").rsplit("/", 1)[-1] in ("styles", "numbering", "settings",
                                                               "header", "footer")}
        if tema is not None:
            reescritas |= {alvo for tipo, alvo, externo in relacoes.values()
                           if not externo and tipo.endswith("/theme")}
        pacote = fx_pacote.capturar(
            coletor=coletor, lim=lim, nomes=nomes, ler_parte=ler_parte, relacoes_de=relacoes_de,
            tipo_de=tipo_de, parse=lambda dados, nome: _parse(dados, nome, profundidade),
            alvo_doc=alvo_doc, rels_pacote=relacoes_de(""), rels_doc=relacoes, raiz_doc=raiz,
            tema_tratado=tema is not None, proibidos=reescritas)

    comentarios = _comentarios_ancorados(comentarios, paras, coletor)
    doc = normalizar(Documento(paragrafos=paras, pagina=pagina, cabecalhos=cabecalhos,
                               rodapes=rodapes, estilos=ctx.estilos, pacote=pacote,
                               numeracao=ctx.numeracao, comentarios=comentarios, **meta))
    mod_numeracao.tipos_dos_paragrafos(doc)
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
