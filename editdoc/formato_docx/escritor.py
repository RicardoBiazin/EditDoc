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
com os bytes originais e um tipo de conteudo por extensao. Cada parte que usa a
imagem (documento, cabecalho, rodape) tem a sua propria relacao para ela.

Cabecalho e rodape (M5): uma parte word/headerN.xml ou footerN.xml por tipo
(padrao, primeira, par), com relacao no documento, referencia no sectPr, tipo de
conteudo proprio e, se tiver imagem, relacoes proprias. `w:titlePg` no sectPr e
`w:evenAndOddHeaders` no settings.xml dizem qual vale em cada pagina.

Campos (M5): PAGE e NUMPAGES saem como campo complexo (fldChar begin, instrText,
separate, o ultimo resultado, end), que e' como o Word grava. O Word recalcula.

Estilos (M6): o styles.xml sai de formato_docx/estilos.py: o original do arquivo, com
os estilos alterados e novos reescritos. Paragrafo e run levam w:pStyle e w:rStyle so'
para estilo que esta' no catalogo (o validador confere). O tema do arquivo de origem
(theme1.xml) volta, para as fontes de tema dos estilos continuarem as mesmas.

Objetos opacos (0.1.2): caixa de texto, forma, grafico, SmartArt, OLE, imagem flutuante e
equacao voltam com o XML original e as partes que usam (formato_docx/opacos.py). A raiz
de cada parte declara os namespaces do mc:Ignorable de origem, e o wp:docPr id das
imagens do EditDoc nao colide com o dos objetos.

Pacote, hiperlinks e campos (0.1.3): as partes que o EditDoc nao edita voltam pelo
`pacote.GravadorPacote` (o settings.xml, o core.xml e o app.xml originais, com o que o
EditDoc controla reescrito, e o resto byte a byte). Runs vizinhos com o mesmo `Link` saem
num w:hyperlink (relacao externa nova na parte, sem colisao). As marcas de campo saem como
begin (com o codigo e os campos de dentro dele), separate e end; as de marcador, como
bookmarkStart e bookmarkEnd com id unico. `marcas.equilibrar` roda antes: o arquivo nunca
sai com begin sem end.
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import io
import re
import zipfile

from lxml import etree

from editdoc.formato_docx import estilos as fx_estilos
from editdoc.formato_docx import opacos, ordem
from editdoc.formato_docx import pacote as fx_pacote
from editdoc.formato_docx.avisos import Aviso, Coletor
from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.nomes import (A_NS, CP, CT_APP, CT_CABECALHO, CT_CONFIG, CT_CORE,
                                        CT_DOCUMENTO, CT_ESTILOS, CT_NUMERACAO, CT_RELS,
                                        CT_RODAPE, CT_XML, DC, DCT, EP, MC_NS, PIC_NS, PKG_CT, PKG_REL,
                                        R_NS, RT, RT_CABECALHO, RT_CORE, RT_IMAGEM, RT_RODAPE,
                                        URI_IMAGEM, W, WP_NS, XML_NS, XSI, q)
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.campos import FORMATOS_NUMERO, NUMERO_INICIAL_MAXIMO, tipo_do_campo
from editdoc.modelo import marcas
from editdoc.modelo.documento import (TIPOS_DE_FAIXA, Bloco, Borda, Campo, Celula, Documento,
                                      Imagem, Link, MarcaCampo, Marcador, Paragrafo, Run, Tabela,
                                      bordas_padrao, objetos_de)
from editdoc.modelo.estilos import catalogo_padrao

_JC = {"esquerda": "left", "centro": "center", "direita": "right", "justificado": "both"}
_JC_TABELA = {"esquerda": "left", "centro": "center", "direita": "right"}
_VALIGN = {"topo": "top", "centro": "center", "base": "bottom"}
_ESTILO_BORDA = {"simples": "single", "dupla": "double", "pontilhada": "dotted",
                 "tracejada": "dashed", "nenhuma": "nil"}
#: Estilo de tabela que toda tabela usa (o "Table Grid" do Word).
ESTILO_TABELA = fx_estilos.ESTILO_TABELA
#: Tema do arquivo de origem (M6).
CT_TEMA = "application/vnd.openxmlformats-officedocument.theme+xml"
PARTE_TEMA = "word/theme/theme1.xml"
#: Hiperlink externo (0.1.3): relacao com TargetMode="External".
RT_HIPERLINK = RT + "hyperlink"
#: Controles invalidos em XML 1.0, surrogates soltos, noncharacters e o caractere de
#: objeto (U+FFFC), que so' tem sentido num run de imagem.
_CONTROLE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffc\ufffe\uffff\ud800-\udfff]")
#: Tab e quebra de linha viram elementos; U+2028 (separador de linha do Qt) vira quebra.
_SEPARADORES = re.compile("(\t|\n|\u2028)")
_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_ZIP_DATA = (1980, 1, 1, 0, 0, 0)  # data fixa: saida igual entre gravacoes
_VERT = {"subscrito": "subscript", "sobrescrito": "superscript"}
#: Tipo do modelo -> w:type de headerReference/footerReference.
_TIPO_FAIXA = {"padrao": "default", "primeira": "first", "par": "even"}



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


def _rpr(run: Run, estilo: str | None = None) -> etree._Element | None:
    rpr = etree.Element(q("rPr"))
    if estilo:
        etree.SubElement(rpr, q("rStyle")).set(q("val"), estilo)
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


class _Relacoes:
    """Relacoes de uma parte (documento, cabecalho ou rodape), com rId sequencial."""

    def __init__(self, primeiro: int) -> None:
        self._proximo = primeiro
        self._por_alvo: dict[tuple[str, str, bool], str] = {}
        self.itens: list[tuple] = []

    def adicionar(self, tipo: str, alvo: str, externo: bool = False) -> str:
        chave = (tipo, alvo, externo)
        if chave not in self._por_alvo:
            rid = f"rId{self._proximo}"
            self._proximo += 1
            self._por_alvo[chave] = rid
            self.itens.append((rid, tipo, alvo, "External") if externo else (rid, tipo, alvo))
        return self._por_alvo[chave]


class _Midias:
    """Imagens do documento inteiro: uma parte em word/media por conteudo distinto."""

    PRIMEIRO_RID = 4  # rId1 a rId3 do documento: estilos, configuracoes e numeracao

    def __init__(self, usados: set[str], opacos_: opacos.GravadorOpacos) -> None:
        self._por_hash: dict[str, str] = {}  # sha256 -> alvo relativo a word/
        self.partes: list[tuple[str, bytes]] = []
        self.extensoes: set[str] = set()
        #: nomes de parte ja' tomados, compartilhado com as partes dos objetos opacos
        self._usados = usados
        self._opacos = opacos_

    def registrar(self, imagem: Imagem) -> str:
        """Alvo da imagem relativo a word/ ("media/image1.png"); cria a parte na primeira vez."""
        chave = hashlib.sha256(imagem.dados).hexdigest()
        if chave not in self._por_hash:
            extensao, _tipo = mod_imagem.FORMATOS[imagem.formato]
            n = len(self._por_hash) + 1
            tomados = {u.lower() for u in self._usados}
            while f"word/media/image{n}.{extensao}" in tomados:
                n += 1  # nome que a parte de um objeto opaco ja' usa
            self._usados.add(f"word/media/image{n}.{extensao}")
            self._por_hash[chave] = f"media/image{n}.{extensao}"
            self.partes.append((f"word/media/image{n}.{extensao}", imagem.dados))
            self.extensoes.add(extensao)
        return self._por_hash[chave]

    def id_de_desenho(self) -> int:
        """wp:docPr id: sequencial, pulando os que os objetos opacos ja' usam."""
        return self._opacos.id_de_desenho()


#: Partes que o escritor sempre grava: um objeto opaco nunca toma estes nomes.
_PARTES_FIXAS = {"[Content_Types].xml", "_rels/.rels", "word/document.xml",
                 "word/_rels/document.xml.rels", "word/styles.xml", "word/numbering.xml",
                 "word/settings.xml", "docProps/core.xml", "docProps/app.xml"}


class _Ctx:
    def __init__(self, coletor: Coletor, estilos=None, pacote=None) -> None:
        self.coletor = coletor
        self.listas = _Listas()
        usados = set(_PARTES_FIXAS)
        if estilos is not None and estilos.tema_original:
            usados.add(PARTE_TEMA)
        # Partes preservadas do pacote (0.1.3): tomam o nome primeiro, para manter o de origem.
        self.pacote = fx_pacote.GravadorPacote(pacote, usados, _rels_xml, ordem.caminho_dos_rels)
        #: marcadores (0.1.3): id sequencial no documento; nome -> id do inicio aberto
        self.proximo_marcador = 0
        self.ids_marcadores: dict[str, int] = {}
        self.opacos = opacos.GravadorOpacos(usados, _rels_xml, ordem.caminho_dos_rels)
        self.midias = _Midias(usados, self.opacos)
        #: relacoes da parte que esta' sendo escrita (troca no cabecalho e no rodape)
        self.relacoes = _Relacoes(_Midias.PRIMEIRO_RID)
        #: catalogo de estilos (M6): id -> tipo, e o id do estilo de paragrafo padrao
        self.estilos = estilos if estilos is not None else catalogo_padrao()
        self.tipos = {sid: e.tipo for sid, e in self.estilos.itens.items()}
        self.padrao = self.estilos.id_padrao()

    def estilo_de_paragrafo(self, sid: str | None) -> str | None:
        """O id para o w:pStyle, ou None (estilo padrao ou fora do catalogo)."""
        if not sid or sid == self.padrao or self.tipos.get(sid) != "paragrafo":
            return None
        return sid

    def estilo_de_caractere(self, sid: str | None) -> str | None:
        return sid if sid and self.tipos.get(sid) == "caractere" else None


def _desenho(r, imagem: Imagem, ctx: _Ctx) -> None:
    """w:drawing/wp:inline com a figura, na ordem do esquema (a mesma do Word)."""
    if imagem.formato not in mod_imagem.FORMATOS:
        raise ValueError(f"formato de imagem invalido: {imagem.formato!r}")
    alvo = ctx.midias.registrar(imagem)
    parte = "word/" + alvo
    rid = ctx.relacoes.adicionar(RT_IMAGEM, alvo)
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
    estilo = ctx.estilo_de_paragrafo(p.estilo)
    if estilo is not None:
        etree.SubElement(ppr, q("pStyle")).set(q("val"), estilo)
    if p.nivel is not None:
        etree.SubElement(ppr, q("outlineLvl")).set(q("val"), str(min(max(int(p.nivel), 0), 9)))
    if p.numeracao is not None:
        num = etree.SubElement(ppr, q("numPr"))
        etree.SubElement(num, q("ilvl")).set(q("val"), "0")
        etree.SubElement(num, q("numId")).set(q("val"), str(listas.numero(p.numeracao)))
    else:
        listas.encerrar()
    if p.alinhamento is not None:
        etree.SubElement(ppr, q("jc")).set(q("val"), _JC[p.alinhamento])
    if (p.recuo_esquerdo_tw is not None or p.recuo_primeira_linha_tw is not None
            or p.recuo_direito_tw is not None):
        ind = etree.SubElement(ppr, q("ind"))
        if p.recuo_esquerdo_tw is not None:
            ind.set(q("left"), str(int(p.recuo_esquerdo_tw)))
        if p.recuo_direito_tw is not None:
            ind.set(q("right"), str(int(p.recuo_direito_tw)))
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
    # Hiperlink (0.1.3): runs vizinhos com o mesmo destino ficam num w:hyperlink so'.
    destino = pe
    link_atual = None
    for i, run in enumerate(p.runs):
        if run.link != link_atual:
            link_atual = run.link
            destino = pe if run.link is None else _hiperlink(pe, run.link, ctx)
        if run.marca is not None:
            proximo = p.runs[i + 1] if i + 1 < len(p.runs) else None
            _marca(destino, run, proximo, ctx)
            continue
        if run.imagem is not None:
            r = etree.SubElement(destino, q("r"))
            _desenho(r, run.imagem, ctx)
            continue
        if run.objeto is not None:
            # Objeto opaco (0.1.2): o XML original, com os rIds desta parte.
            destino.append(ctx.opacos.escrever(run.objeto, ctx.relacoes.adicionar))
            continue
        if run.campo is not None:
            _campo(destino, run, coletor, ctx.estilo_de_caractere(run.estilo))
            continue
        if run.texto == "":
            continue
        r = etree.SubElement(destino, q("r"))
        rpr = _rpr(run, ctx.estilo_de_caractere(run.estilo))
        if rpr is not None:
            r.append(rpr)
        _conteudo_run(r, run.texto, coletor)


def _hiperlink(pe, link: Link, ctx: "_Ctx"):
    """w:hyperlink: r:id para o endereco externo (relacao TargetMode=External), w:anchor
    para o marcador, e os atributos que o arquivo trazia (dica, historico, quadro)."""
    h = etree.SubElement(pe, q("hyperlink"))
    if link.url is not None:
        url, _n = texto_gravavel(link.url)
        h.set("{%s}id" % R_NS, ctx.relacoes.adicionar(RT_HIPERLINK, url, True))
    for atributo, valor in (("anchor", link.ancora), ("tooltip", link.dica),
                            ("tgtFrame", link.quadro), ("docLocation", link.local)):
        if valor:
            h.set(q(atributo), texto_gravavel(valor)[0])
    if link.historico is not None:
        h.set(q("history"), "1" if link.historico else "0")
    return h


def _marca(destino, run: Run, proximo: Run | None, ctx: "_Ctx") -> None:
    """Marca de campo (begin com o codigo, ou end) ou de marcador (bookmarkStart/End)."""
    m = run.marca
    if isinstance(m, Marcador):
        if m.tipo == "inicio":
            ident = ctx.proximo_marcador
            ctx.proximo_marcador += 1
            ctx.ids_marcadores[m.nome] = ident
            el = etree.SubElement(destino, q("bookmarkStart"))
            el.set(q("id"), str(ident))
            el.set(q("name"), texto_gravavel(m.nome)[0])
        else:
            ident = ctx.ids_marcadores.pop(m.nome, None)
            if ident is not None:
                etree.SubElement(destino, q("bookmarkEnd")).set(q("id"), str(ident))
        return
    rpr = _rpr(run, ctx.estilo_de_caractere(run.estilo))
    if m.tipo == "fim":
        _run_de_campo(destino, rpr, "end")
        return
    campo = m.campo
    # Sem resultado no arquivo de origem (XE, TC...) e nada digitado entre as marcas: sem
    # o separate, como veio.
    fecha_logo = (proximo is not None and isinstance(proximo.marca, MarcaCampo)
                  and proximo.marca.tipo == "fim")
    _codigo_de_campo(destino, campo, rpr, sem_separador=campo.sem_resultado and fecha_logo)


def _run_de_campo(destino, rpr, tipo: str, campo: Campo | None = None):
    r = etree.SubElement(destino, q("r"))
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    if tipo == "begin" and campo is not None and campo.extra:
        fc = etree.fromstring(campo.extra, opacos.parser_seguro())
        for atributo in ("dirty", "fldLock"):
            fc.attrib.pop(q(atributo), None)
        r.append(fc)
    else:
        fc = etree.SubElement(r, q("fldChar"))
    fc.set(q("fldCharType"), tipo)
    if tipo == "begin" and campo is not None:
        if campo.sujo:
            fc.set(q("dirty"), "true")
        if campo.travado:
            fc.set(q("fldLock"), "true")
    return r


def _codigo_de_campo(destino, campo: Campo, rpr, sem_separador: bool) -> None:
    """begin, a instrucao (com os campos de dentro dela) e o separate."""
    _run_de_campo(destino, rpr, "begin", campo)
    for pedaco in campo.codigo:
        if isinstance(pedaco, Campo):
            # Campo dentro da instrucao (o PAGE de um IF): inteiro, com o ultimo resultado.
            _codigo_de_campo(destino, pedaco, rpr, sem_separador=pedaco.sem_resultado)
            if pedaco.resultado:
                r = etree.SubElement(destino, q("r"))
                if rpr is not None:
                    r.append(copy.deepcopy(rpr))
                t = etree.SubElement(r, q("t"))
                texto, _n = texto_gravavel(pedaco.resultado)
                if texto != texto.strip():
                    t.set("{%s}space" % XML_NS, "preserve")
                t.text = texto
            _run_de_campo(destino, rpr, "end")
            continue
        texto, _n = texto_gravavel(str(pedaco))
        if not texto:
            continue
        r = etree.SubElement(destino, q("r"))
        if rpr is not None:
            r.append(copy.deepcopy(rpr))
        instr = etree.SubElement(r, q("instrText"))
        instr.set("{%s}space" % XML_NS, "preserve")
        instr.text = texto
    if not sem_separador:
        _run_de_campo(destino, rpr, "separate")


def _campo(pe, run: Run, coletor: Coletor, estilo: str | None = None) -> None:
    """Campo complexo, como o Word grava: begin, instrucao, separate, resultado, end.

    Cada pedaco e' um w:r com a formatacao do campo, para que o numero recalculado pelo
    Word saia com a mesma fonte.
    """
    instrucao, _n = texto_gravavel(run.campo or "")
    if tipo_do_campo(instrucao) is None:
        raise ValueError(f"campo nao suportado: {run.campo!r}")
    rpr = _rpr(run, estilo)

    def novo_run():
        r = etree.SubElement(pe, q("r"))
        if rpr is not None:
            r.append(copy.deepcopy(rpr))
        return r

    etree.SubElement(novo_run(), q("fldChar")).set(q("fldCharType"), "begin")
    instr = etree.SubElement(novo_run(), q("instrText"))
    instr.set("{%s}space" % XML_NS, "preserve")
    instr.text = f" {instrucao} "
    etree.SubElement(novo_run(), q("fldChar")).set(q("fldCharType"), "separate")
    if run.texto:
        _conteudo_run(novo_run(), run.texto, coletor)
    etree.SubElement(novo_run(), q("fldChar")).set(q("fldCharType"), "end")


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


_NSMAP_PARTE = {"w": W, "r": R_NS, "wp": WP_NS, "a": A_NS, "pic": PIC_NS}


def _raiz_de_parte(nome: str, ctx: _Ctx):
    """Raiz de document, hdr ou ftr. Com objetos opacos, declara os namespaces da raiz de
    origem (wps, v, o, w14...) e o mc:Ignorable de origem (o Word exige o prefixo
    declarado no escopo)."""
    gravador = ctx.opacos
    if not gravador.ignoraveis and not gravador.espacos:
        return etree.Element(q(nome), nsmap=_NSMAP_PARTE)
    nsmap = {**_NSMAP_PARTE, **gravador.espacos}
    if gravador.ignoraveis:
        nsmap["mc"] = MC_NS
    raiz = etree.Element(q(nome), nsmap=nsmap)
    if gravador.ignoraveis:
        raiz.set("{%s}Ignorable" % MC_NS, " ".join(gravador.ignoraveis))
    return raiz


class _Faixas:
    """Partes de cabecalho e rodape ja escritas: (nome da parte, bytes, relacoes da parte)."""

    def __init__(self) -> None:
        self.partes: list[tuple[str, bytes]] = []
        self.tipos: list[tuple[str, str]] = []  # (/word/headerN.xml, tipo de conteudo)
        self.referencias: list[tuple[str, str, str]] = []  # (elemento, w:type, rId)


def _escrever_faixas(doc: Documento, ctx: _Ctx) -> _Faixas:
    """Cada cabecalho e rodape do modelo vira uma parte, na ordem padrao, primeira, par.

    As relacoes da parte (imagens) sao proprias; a relacao do documento para a parte
    entra nas relacoes do documento (ctx.relacoes), que ja' tem as imagens do corpo.
    """
    faixas = _Faixas()
    relacoes_doc = ctx.relacoes
    for onde, modelo, raiz_nome, prefixo, rt, ct, elemento in (
            ("cabecalho", doc.cabecalhos, "hdr", "header", RT_CABECALHO, CT_CABECALHO,
             "headerReference"),
            ("rodape", doc.rodapes, "ftr", "footer", RT_RODAPE, CT_RODAPE, "footerReference")):
        n = 0
        for tipo in TIPOS_DE_FAIXA:
            if tipo not in modelo:
                continue
            n += 1
            nome = f"{prefixo}{n}.xml"
            ctx.relacoes = _Relacoes(1)
            ctx.listas.encerrar()
            ctx.ids_marcadores = {}
            raiz = _raiz_de_parte(raiz_nome, ctx)
            _blocos(raiz, modelo[tipo], ctx, em_celula=True)  # termina em paragrafo
            faixas.partes.append((f"word/{nome}", _xml(raiz)))
            if ctx.relacoes.itens:
                faixas.partes.append((f"word/_rels/{nome}.rels", _rels_xml(ctx.relacoes.itens)))
            faixas.tipos.append((f"/word/{nome}", ct))
            rid = relacoes_doc.adicionar(rt, nome)
            faixas.referencias.append((elemento, _TIPO_FAIXA[tipo], rid))
    ctx.relacoes = relacoes_doc
    ctx.listas.encerrar()
    return faixas


def _document_xml(doc: Documento, ctx: _Ctx) -> tuple[bytes, _Faixas]:
    raiz = _raiz_de_parte("document", ctx)
    body = etree.SubElement(raiz, q("body"))
    _blocos(body, doc.paragrafos, ctx, em_celula=False)
    if not doc.paragrafos:
        etree.SubElement(body, q("p"))  # o Word exige ao menos um paragrafo
    faixas = _escrever_faixas(doc, ctx)
    pagina = doc.pagina
    sect = etree.SubElement(body, q("sectPr"))
    # EG_HdrFtrReferences vem antes de pgSz no CT_SectPr.
    for elemento, tipo, rid in faixas.referencias:
        ref = etree.SubElement(sect, q(elemento))
        ref.set(q("type"), tipo)
        ref.set("{%s}id" % R_NS, rid)
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
    if pagina.formato_numero != "decimal" or pagina.numero_inicial is not None:
        if pagina.formato_numero not in FORMATOS_NUMERO:
            raise ValueError(f"formato de numero invalido: {pagina.formato_numero!r}")
        num = etree.SubElement(sect, q("pgNumType"))
        if pagina.formato_numero != "decimal":
            num.set(q("fmt"), pagina.formato_numero)
        if pagina.numero_inicial is not None:
            num.set(q("start"), str(min(max(int(pagina.numero_inicial), 0), NUMERO_INICIAL_MAXIMO)))
    if pagina.primeira_diferente:
        etree.SubElement(sect, q("titlePg"))
    return _xml(raiz), faixas



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


def _settings_xml(pares_impares: bool = False) -> bytes:
    raiz = etree.Element(q("settings"), nsmap={"w": W})
    etree.SubElement(raiz, q("zoom")).set(q("percent"), "100")
    etree.SubElement(raiz, q("defaultTabStop")).set(q("val"), "708")
    if pares_impares:
        # Na ordem do CT_Settings: depois de defaultTabStop, antes de characterSpacingControl.
        etree.SubElement(raiz, q("evenAndOddHeaders"))
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


def _content_types_xml(extensoes_de_imagem: set[str] = frozenset(),
                       extras: list[tuple[str, str]] = ()) -> bytes:
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
    overrides.update(dict(extras))
    for parte, tipo in overrides.items():
        etree.SubElement(raiz, "{%s}Override" % PKG_CT, PartName=parte, ContentType=tipo)
    return _xml(raiz)


def _rels_xml(itens: list[tuple]) -> bytes:
    """Itens (Id, tipo, alvo) ou (Id, tipo, alvo, "External")."""
    raiz = etree.Element("{%s}Relationships" % PKG_REL, nsmap={None: PKG_REL})
    for rid, tipo, alvo, *modo in itens:
        rel = etree.SubElement(raiz, "{%s}Relationship" % PKG_REL, Id=rid, Type=tipo, Target=alvo)
        if modo:
            rel.set("TargetMode", modo[0])
    return _xml(raiz)


def _zip(partes: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for nome, dados in partes:
            info = zipfile.ZipInfo(nome, date_time=_ZIP_DATA)
            # Imagem ja vem comprimida (PNG, JPEG, GIF): comprimir de novo so' gasta tempo.
            midia_comprimida = nome.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))
            info.compress_type = zipfile.ZIP_STORED if midia_comprimida else zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            z.writestr(info, dados)
    return buf.getvalue()


def escrever_com_avisos(doc: Documento) -> tuple[bytes, list[Aviso]]:
    """Devolve (bytes do .docx, avisos da gravacao). Levanta ErroDocx se o validador reprovar."""
    coletor = Coletor()
    # Campos e marcadores (0.1.3): as marcas em pares. Campo que perdeu o inicio ou o fim
    # na edicao vira texto comum, com aviso; o arquivo nunca sai com begin sem end.
    doc, desfeitos = marcas.equilibrar(doc)
    if desfeitos["campos"]:
        coletor.somar("CAMPO_INCOMPLETO", desfeitos["campos"])
    if desfeitos["marcadores"]:
        coletor.somar("MARCADOR", desfeitos["marcadores"])
    ctx = _Ctx(coletor, doc.estilos, doc.pacote)
    ctx.opacos.preparar(objetos_de(doc), _NSMAP_PARTE)
    agora = _agora_iso()
    criado = doc.criado_em or agora
    modificado = doc.modificado_em or agora
    documento_xml, faixas = _document_xml(doc, ctx)
    tema = ctx.estilos.tema_original
    gravador = ctx.pacote
    extras_tipos = list(faixas.tipos) + list(ctx.opacos.tipos) + gravador.tipos()
    partes_tema: list[tuple[str, bytes]] = []
    if tema:
        # O tema volta para as fontes de tema (asciiTheme) dos estilos continuarem as mesmas.
        ctx.relacoes.adicionar(RT + "theme", "theme/theme1.xml")
        partes_tema.append((PARTE_TEMA, tema))
        extras_tipos.append(("/" + PARTE_TEMA, CT_TEMA))
    # Partes preservadas (0.1.3): fontTable, webSettings, customXml, notas separadoras...
    for tipo, alvo, externo in gravador.relacoes_do_documento():
        ctx.relacoes.adicionar(tipo, alvo, externo)
    rels_pacote = [
        ("rId1", RT + "officeDocument", "word/document.xml"),
        ("rId2", RT_CORE, "docProps/core.xml"),
        ("rId3", RT + "extended-properties", "docProps/app.xml"),
    ]
    for n, (tipo, alvo, externo) in enumerate(gravador.relacoes_do_pacote(), start=4):
        rels_pacote.append((f"rId{n}", tipo, alvo, "External") if externo else (f"rId{n}", tipo, alvo))
    configuracoes = gravador.configuracoes(doc.pagina.pares_impares) or \
        _settings_xml(doc.pagina.pares_impares)
    rels_configuracoes = gravador.relacoes_das_configuracoes()
    partes_configuracoes = [("word/_rels/settings.xml.rels", _rels_xml(rels_configuracoes))] \
        if rels_configuracoes else []
    partes = [
        ("[Content_Types].xml", _content_types_xml(ctx.midias.extensoes, extras_tipos)),
        ("_rels/.rels", _rels_xml(rels_pacote)),
        ("word/document.xml", documento_xml),
        ("word/_rels/document.xml.rels", _rels_xml([
            ("rId1", RT + "styles", "styles.xml"),
            ("rId2", RT + "settings", "settings.xml"),
            ("rId3", RT + "numbering", "numbering.xml"),
            *ctx.relacoes.itens,
        ])),
        *faixas.partes,
        ("word/styles.xml", fx_estilos.escrever_estilos(ctx.estilos)),
        *partes_tema,
        ("word/numbering.xml", _numbering_xml(ctx.listas.numeracoes)),
        ("word/settings.xml", configuracoes),
        *partes_configuracoes,
        ("docProps/core.xml", gravador.propriedades(doc.titulo, doc.autor, criado, modificado)
         or _core_xml(doc, criado, modificado)),
        ("docProps/app.xml", gravador.aplicativo() or _app_xml()),
        *ctx.midias.partes,
        *ctx.opacos.partes,
        *gravador.partes(),
    ]
    mapa = dict(partes)
    problemas = ordem.validar(mapa)
    if problemas:
        raise ErroDocx("ESCRITA_INVALIDA", "; ".join(problemas[:3]))
    return _zip(partes), coletor.avisos()


def escrever(doc: Documento) -> bytes:
    return escrever_com_avisos(doc)[0]
