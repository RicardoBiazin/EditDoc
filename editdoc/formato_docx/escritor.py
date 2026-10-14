"""Modelo -> bytes de .docx, com lxml e zipfile. Sem Qt.

O pacote tem o minimo que o Word aceita: Content_Types, relacoes, document,
styles, numbering, settings, core e app. A saida e' determinista (datas de zip
fixas), e cada gravacao passa pelo validador de `ordem` antes de sair: um
arquivo que o validador reprova nao e' devolvido.

Listas (0.1.4): o paragrafo grava o w:numPr que tem (`Paragrafo.lista` e `lista_nivel`), e
o numbering.xml sai do catalogo (`formato_docx/numeracao.py`): o original do arquivo, com as
definicoes que o EditDoc acrescentou no fim, e as imagens dos marcadores de figura com as
relacoes do numbering.xml. Paragrafo montado em codigo so' com o tipo (`numeracao`) ganha
numId por `modelo.numeracao.materializar`: um para os marcadores, um por grupo contiguo de
numeracao, reiniciando em 1 (o que o escritor fazia antes da 0.1.4).

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

Propriedades preservadas (0.1.5): o rPr e o pPr juntam o que o escritor gera do modelo com os
extras do arquivo de origem (`propriedades.montar_rpr`/`montar_ppr`), na ordem do esquema. O
controle de conteudo sai como w:sdt com o sdtPr de origem: o de paragrafo dentro do w:p, o de
bloco por fora dos paragrafos que envolve. Recorte de imagem (a:srcRect) volta ao blipFill.

Comentarios (0.1.6): as ancoras saem como w:commentRangeStart, w:commentRangeEnd e o run com
w:commentReference; o word/comments.xml tem cada w:comment (o XML de origem do que nao mudou,
o conteudo gerado pelo escritor de sempre no novo ou editado, com o w:annotationRef no
comeco e o w14:paraId no ultimo paragrafo), com as relacoes proprias (links). As partes
estendidas e o people.xml saem de `formato_docx/comentarios.py`. Sem mudanca nenhuma, o
comments.xml volta byte a byte. A referencia a estilo que o styles.xml de origem nao definia
(o "CommentReference" latente) volta como veio, e o validador a aceita.

Notas (0.1.10): a referencia sai como o run com w:footnoteReference (ou w:endnoteReference),
com o w:customMarkFollows e o run do simbolo quando a marca e' personalizada; o numero da
propria nota, como w:footnoteRef. As partes word/footnotes.xml e word/endnotes.xml: sem mudanca,
os bytes de origem (as relacoes mantem o Id); com mudanca, a raiz de origem com as notas
especiais, o XML de origem das notas que nao mudaram e o conteudo gerado das outras. O
footnotePr/endnotePr do sectPr volta (o de origem, se as propriedades nao mudaram), e o
settings.xml cita as especiais que a parte tem. `notas.preparar` roda antes (so' as notas com
referencia, ids unicos).
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import io
import re
import zipfile

from lxml import etree

from editdoc.formato_docx import comentarios as fx_comentarios
from editdoc.formato_docx import notas as fx_notas
from editdoc.formato_docx import estilos as fx_estilos
from editdoc.formato_docx import numeracao as fx_numeracao
from editdoc.formato_docx import opacos, ordem
from editdoc.formato_docx import pacote as fx_pacote
from editdoc.formato_docx import propriedades as fx_props
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
from editdoc.modelo import notas as mod_notas
from editdoc.formato_docx.nomes import W14_NS
from editdoc.modelo.documento import (TIPOS_DE_FAIXA, Bloco, Borda, Campo, Celula, Documento,
                                      Imagem, Link, MarcaCampo, MarcaComentario, MarcaConteudo,
                                      Marcador, MarcaNota, Paragrafo, Run, Tabela, bordas_padrao, objetos_de,
                                      paragrafos_de)
from editdoc.modelo.estilos import catalogo_padrao
from editdoc.modelo.numeracao import lista_efetiva, materializado, recuos_do_nivel

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


def _rpr(run: Run, estilo: str | None = None, ctx: "_Ctx | None" = None) -> etree._Element | None:
    """O w:rPr do run: o que o modelo diz, mais os extras do arquivo de origem (0.1.5)."""
    if ctx is None:
        return fx_props.montar_rpr(run, estilo)
    return fx_props.montar_rpr(run, estilo, ctx.bases_de_caractere(run.estilo),
                               ctx.estilos.fontes_tema, ctx.estilo_existe)


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

    def reservar(self, rid: str, tipo: str, alvo: str, externo: bool) -> None:
        """Relacao de origem que volta com o mesmo Id (0.1.10: a nota que nao mudou). As novas
        pulam os Ids reservados."""
        chave = (tipo, alvo, externo)
        self._por_alvo.setdefault(chave, rid)
        self.itens.append((rid, tipo, alvo, "External") if externo else (rid, tipo, alvo))
        if rid.startswith("rId") and rid[3:].isdigit():
            self._proximo = max(self._proximo, int(rid[3:]) + 1)

    def adicionar_com_id(self, preferido: str, tipo: str, alvo: str, externo: bool = False) -> str:
        """Como `adicionar`, mas com o Id de origem se ele ainda esta' livre (0.1.6: o link do
        comentario que volta com o XML de origem)."""
        chave = (tipo, alvo, externo)
        if chave in self._por_alvo:
            return self._por_alvo[chave]
        usados = {item[0] for item in self.itens}
        if not preferido or preferido in usados or (
                preferido.startswith("rId") and preferido[3:].isdigit()):
            return self.adicionar(tipo, alvo, externo)
        self._por_alvo[chave] = preferido
        self.itens.append((preferido, tipo, alvo, "External") if externo else (preferido, tipo, alvo))
        return preferido


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

    def registrar_bytes(self, dados: bytes) -> str:
        """A imagem de uma nota que volta com o XML de origem (0.1.10): mesma parte por conteudo."""
        formato = mod_imagem.formato_de(dados)
        if formato not in mod_imagem.FORMATOS:
            raise ValueError("imagem de nota em formato que o escritor nao grava")
        largura, altura = mod_imagem.dimensoes(dados, formato) or (1, 1)
        return self.registrar(Imagem(dados=dados, formato=formato, largura_emu=max(1, largura),
                                     altura_emu=max(1, altura)))


#: Partes que o escritor sempre grava: um objeto opaco nunca toma estes nomes.
_PARTES_FIXAS = {"[Content_Types].xml", "_rels/.rels", "word/document.xml",
                 "word/_rels/document.xml.rels", "word/styles.xml", "word/numbering.xml",
                 "word/settings.xml", "docProps/core.xml", "docProps/app.xml"}


class _Ctx:
    def __init__(self, coletor: Coletor, estilos=None, pacote=None,
                 comentarios: bool = False, partes_notas=()) -> None:
        self.coletor = coletor
        usados = set(_PARTES_FIXAS) | set(partes_notas)  # 0.1.10: o nome das partes de notas
        if comentarios:
            usados |= set(fx_comentarios.PARTES)  # 0.1.6: o pacote preservado nao toma o nome
        if estilos is not None and estilos.tema_original:
            usados.add(PARTE_TEMA)
        # Partes preservadas do pacote (0.1.3): tomam o nome primeiro, para manter o de origem.
        self.pacote = fx_pacote.GravadorPacote(pacote, usados, _rels_xml, ordem.caminho_dos_rels)
        #: marcadores (0.1.3): id sequencial no documento; nome -> id do inicio aberto
        self.proximo_marcador = 0
        self.ids_marcadores: dict[str, int] = {}
        #: ids de marcador que as notas de origem (0.1.10) ja' usam: os novos pulam
        self.marcadores_reservados: set[int] = set()
        self.opacos = opacos.GravadorOpacos(usados, _rels_xml, ordem.caminho_dos_rels)
        self.midias = _Midias(usados, self.opacos)
        #: relacoes da parte que esta' sendo escrita (troca no cabecalho e no rodape)
        self.relacoes = _Relacoes(_Midias.PRIMEIRO_RID)
        #: catalogo de estilos (M6): id -> tipo, e o id do estilo de paragrafo padrao
        self.estilos = estilos if estilos is not None else catalogo_padrao()
        self.tipos = {sid: e.tipo for sid, e in self.estilos.itens.items()}
        self.padrao = self.estilos.id_padrao()
        #: numeracao (0.1.4), para o recuo da lista na base do paragrafo (0.1.5)
        self.numeracao = None
        #: estilo do paragrafo que esta' sendo escrito e quantas tabelas por fora (0.1.5)
        self.estilo_par: str | None = None
        self.em_tabela = 0
        self._bases_car: dict = {}

    def estilo_existe(self, sid: str | None, tipo: str) -> bool:
        return bool(sid) and self.tipos.get(sid) == tipo

    def bases_de_caractere(self, sid_car: str | None) -> dict:
        """O que o run tem sem formatacao direta (paragrafo e estilo de caractere)."""
        chave = (self.estilo_par, sid_car)
        if chave not in self._bases_car:
            self._bases_car[chave] = self.estilos.base_de_caractere(*chave)
        return self._bases_car[chave]

    def bases_de_paragrafo(self, p: Paragrafo) -> dict:
        """O que o paragrafo tem sem formatacao direta: o estilo (com o docDefaults fora da
        tabela) e o recuo do nivel da lista, como a ponte Qt resolve."""
        sid = p.estilo or self.padrao
        par, _car = self.estilos.resolver_paragrafo(sid, com_padrao=not self.em_tabela)
        if self.numeracao is not None:
            efetiva = lista_efetiva(p.lista, p.lista_nivel, sid, self.estilos, self.numeracao)
            if efetiva is not None:
                par = {**par, **recuos_do_nivel(self.numeracao.nivel_de(*efetiva, self.estilos))}
        return par

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
    if imagem.recorte is not None and any(imagem.recorte):
        # Recorte (0.1.5): a:srcRect entre o blip e o stretch (CT_BlipFillProperties).
        recorte = etree.SubElement(preenchimento, a("srcRect"))
        for chave, valor in zip("ltrb", imagem.recorte):
            if int(valor):
                recorte.set(chave, str(int(valor)))
    esticar = etree.SubElement(preenchimento, a("stretch"))
    etree.SubElement(esticar, a("fillRect"))
    sp = etree.SubElement(figura, pic("spPr"))
    xfrm = etree.SubElement(sp, a("xfrm"))
    etree.SubElement(xfrm, a("off"), x="0", y="0")
    etree.SubElement(xfrm, a("ext"), cx=cx, cy=cy)
    geom = etree.SubElement(sp, a("prstGeom"), prst="rect")
    etree.SubElement(geom, a("avLst"))


def _paragrafo(body, p: Paragrafo, ctx: _Ctx) -> None:
    coletor = ctx.coletor
    pe = etree.SubElement(body, q("p"))
    estilo = ctx.estilo_de_paragrafo(p.estilo)
    ctx.estilo_par = p.estilo
    ppr = fx_props.montar_ppr(p, estilo, ctx.bases_de_paragrafo(p), ctx.estilo_existe)
    if ppr is not None:
        pe.append(ppr)
    if p.quebra_antes:
        # Quebra de pagina: o paragrafo comeca no topo da proxima pagina.
        r_quebra = etree.SubElement(pe, q("r"))
        etree.SubElement(r_quebra, q("br")).set(q("type"), "page")
    # Hiperlink (0.1.3): runs vizinhos com o mesmo destino ficam num w:hyperlink so'.
    # Controle de conteudo (0.1.5): o w:sdt do paragrafo abre e fecha nas marcas; o link
    # recomeca dentro dele.
    pilha = [pe]
    destino = pe
    link_atual = None
    for i, run in enumerate(p.runs):
        if isinstance(run.marca, MarcaConteudo):
            if run.marca.bloco:
                continue  # controle de bloco: por fora do paragrafo (_blocos)
            if run.marca.tipo == "inicio":
                sdt = etree.SubElement(pilha[-1], q("sdt"))
                for el in fx_props.elementos_de_sdt(run.marca.propriedades):
                    sdt.append(el)
                pilha.append(etree.SubElement(sdt, q("sdtContent")))
            elif len(pilha) > 1:
                pilha.pop()
            destino = pilha[-1]
            link_atual = None
            continue
        if run.link != link_atual:
            link_atual = run.link
            destino = pilha[-1] if run.link is None else _hiperlink(pilha[-1], run.link, ctx)
        if run.marca is not None:
            proximo = p.runs[i + 1] if i + 1 < len(p.runs) else None
            _marca(destino, run, proximo, ctx)
            continue
        if run.imagem is not None:
            r = etree.SubElement(destino, q("r"))
            if run.extras:
                rpr = fx_props.montar_rpr(Run(extras=run.extras), None)
                if rpr is not None:
                    r.append(rpr)
            _desenho(r, run.imagem, ctx)
            continue
        if run.objeto is not None:
            # Objeto opaco (0.1.2): o XML original, com os rIds desta parte.
            destino.append(ctx.opacos.escrever(run.objeto, ctx.relacoes.adicionar))
            continue
        if run.campo is not None:
            _campo(destino, run, coletor, ctx.estilo_de_caractere(run.estilo), ctx)
            continue
        if run.texto == "":
            continue
        r = etree.SubElement(destino, q("r"))
        rpr = _rpr(run, ctx.estilo_de_caractere(run.estilo), ctx)
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
    """Marca de campo (begin com o codigo, ou end) ou de marcador (bookmarkStart/End); desde a
    0.1.6, ancora de comentario."""
    m = run.marca
    if isinstance(m, MarcaComentario):
        if m.tipo == "referencia":
            r = etree.SubElement(destino, q("r"))
            rpr = _rpr(run, ctx.estilo_de_caractere(run.estilo), ctx)
            if rpr is not None:
                r.append(rpr)
            etree.SubElement(r, q("commentReference")).set(q("id"), str(int(m.id)))
        else:
            nome = "commentRangeStart" if m.tipo == "inicio" else "commentRangeEnd"
            etree.SubElement(destino, q(nome)).set(q("id"), str(int(m.id)))
        return
    if isinstance(m, MarcaNota):
        _referencia_de_nota(destino, run, m, ctx)
        return
    if isinstance(m, Marcador):
        if m.tipo == "inicio":
            while ctx.proximo_marcador in ctx.marcadores_reservados:
                ctx.proximo_marcador += 1
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
    rpr = _rpr(run, ctx.estilo_de_caractere(run.estilo), ctx)
    if m.tipo == "fim":
        _run_de_campo(destino, rpr, "end")
        return
    campo = m.campo
    # Sem resultado no arquivo de origem (XE, TC...) e nada digitado entre as marcas: sem
    # o separate, como veio.
    fecha_logo = (proximo is not None and isinstance(proximo.marca, MarcaCampo)
                  and proximo.marca.tipo == "fim")
    _codigo_de_campo(destino, campo, rpr, sem_separador=campo.sem_resultado and fecha_logo,
                     ctx=ctx)


def _referencia_de_nota(destino, run: Run, m: MarcaNota, ctx: "_Ctx") -> None:
    """A referencia da nota (0.1.10), ou o numero da propria nota dentro dela."""
    local = mod_notas.LOCAL[m.tipo]
    r = etree.SubElement(destino, q("r"))
    rpr = _rpr(run, ctx.estilo_de_caractere(run.estilo), ctx)
    if rpr is not None:
        r.append(rpr)
    if m.propria:
        etree.SubElement(r, q(local + "Ref"))
        return
    el = etree.SubElement(r, q(local + "Reference"))
    if m.personalizada:
        el.set(q("customMarkFollows"), "1")
    el.set(q("id"), str(int(m.id)))
    if m.personalizada and m.simbolo:
        simbolo = etree.SubElement(destino, q("r"))
        for f in fx_props.filhos_de(m.simbolo):
            simbolo.append(f)
        for x in list(simbolo.iter(q("rStyle"))):
            if not ctx.estilo_existe(x.get(q("val")), "caractere"):
                x.getparent().remove(x)


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


def _rpr_proprio(texto: str | None, rpr, ctx=None):
    """O rPr guardado de um run do codigo do campo (0.1.6), ou o do begin. O estilo citado que
    o catalogo nao tem mais sai (o validador recusaria)."""
    if not texto:
        return rpr
    el = etree.Element(q("rPr"))
    for f in fx_props.filhos_de(texto):
        el.append(f)
    if ctx is not None:
        for x in list(el.iter(q("rStyle"))):
            if not ctx.estilo_existe(x.get(q("val")), "caractere"):
                x.getparent().remove(x)
    return el if len(el) else None


def _codigo_de_campo(destino, campo: Campo, rpr, sem_separador: bool, ctx=None) -> None:
    """begin, a instrucao (com os campos de dentro dela) e o separate."""
    _run_de_campo(destino, rpr, "begin", campo)
    rpr_codigo = _rpr_proprio(campo.rpr_codigo, rpr, ctx)
    for pedaco in campo.codigo:
        if isinstance(pedaco, Campo):
            # Campo dentro da instrucao (o PAGE de um IF): inteiro, com o ultimo resultado.
            _codigo_de_campo(destino, pedaco, rpr, sem_separador=pedaco.sem_resultado, ctx=ctx)
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
        if rpr_codigo is not None:
            r.append(copy.deepcopy(rpr_codigo))
        instr = etree.SubElement(r, q("instrText"))
        instr.set("{%s}space" % XML_NS, "preserve")
        instr.text = texto
    if not sem_separador:
        _run_de_campo(destino, _rpr_proprio(campo.rpr_separador, rpr, ctx), "separate")


def _campo(pe, run: Run, coletor: Coletor, estilo: str | None = None, ctx=None) -> None:
    """Campo complexo, como o Word grava: begin, instrucao, separate, resultado, end.

    Cada pedaco e' um w:r com a formatacao do campo, para que o numero recalculado pelo
    Word saia com a mesma fonte.
    """
    instrucao, _n = texto_gravavel(run.campo or "")
    if tipo_do_campo(instrucao) is None:
        raise ValueError(f"campo nao suportado: {run.campo!r}")
    rpr = _rpr(run, estilo, ctx)

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
    # O estilo de origem volta (0.1.6, com a formatacao condicional dele); a tabela do EditDoc
    # usa o "Table Grid". As bordas continuam explicitas, entao a grade nao muda.
    estilo = tabela.estilo if tabela.estilo and ctx.tipos.get(tabela.estilo) == "tabela" \
        else ESTILO_TABELA
    etree.SubElement(tbl_pr, q("tblStyle")).set(q("val"), estilo)
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
    fx_props.montar_extras_tabela(tbl_pr, tabela.extras)  # 0.1.5
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
        fx_props.montar_extras_tabela(tr_pr, linha.extras)  # 0.1.5
        if len(tr_pr):
            tr.append(tr_pr)
        coluna = 0
        for celula in linha.celulas:
            span = max(1, int(celula.colunas))
            largura_celula = sum(tabela.colunas_tw[coluna:coluna + span])
            coluna += span
            ctx.em_tabela += 1
            try:
                _celula(tr, celula, span, largura_celula, ctx)
            finally:
                ctx.em_tabela -= 1


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
    fx_props.montar_extras_tabela(tc_pr, celula.extras)  # 0.1.5
    _blocos(tc, celula.blocos, ctx, em_celula=True)


def _blocos(pai, blocos: list[Bloco], ctx: _Ctx, em_celula: bool) -> None:
    """Paragrafos e tabelas, na ordem. Celula e corpo terminam em paragrafo (o Word exige).

    Controle de conteudo de bloco (0.1.5): a marca de inicio no paragrafo abre um w:sdt antes
    dele, e os blocos seguintes entram no w:sdtContent ate' o paragrafo com a marca de fim.
    `marcas.equilibrar` ja' deixou os pares na mesma lista de blocos e bem aninhados.
    """
    pilha = [pai]
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            _tabela(pilha[-1], bloco, ctx)
            continue
        for run in bloco.runs:
            m = run.marca
            if isinstance(m, MarcaConteudo) and m.bloco and m.tipo == "inicio":
                sdt = etree.SubElement(pilha[-1], q("sdt"))
                for el in fx_props.elementos_de_sdt(m.propriedades):
                    sdt.append(el)
                pilha.append(etree.SubElement(sdt, q("sdtContent")))
        _paragrafo(pilha[-1], bloco, ctx)
        for run in bloco.runs:
            m = run.marca
            if isinstance(m, MarcaConteudo) and m.bloco and m.tipo == "fim" and len(pilha) > 1:
                pilha.pop()
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
    # Notas (0.1.10): footnotePr e endnotePr, depois das referencias de cabecalho e rodape.
    cat = doc.notas
    if cat is not None:
        for tipo in mod_notas.TIPOS:
            pr = cat.secao.get(tipo)
            if pr is None:
                continue
            el = None
            original = cat.secao_xml.get(tipo)
            if original:
                candidato = etree.fromstring(original, opacos.parser_seguro())
                if fx_notas.ler_propriedades(candidato, tipo)[0] == pr:
                    el = candidato
            if el is None:
                el = fx_notas.elemento_de_propriedades(tipo, pr)
            if el is not None:
                sect.append(el)
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



def _comentarios_xml(doc: Documento, ctx: _Ctx) -> tuple[bytes, list]:
    """word/comments.xml (0.1.6) e as relacoes dele. Sem mudanca nenhuma, os bytes de origem."""
    cat = doc.comentarios
    originais = None
    if cat.xml_comentarios is not None and all(c.original is not None for c in cat.itens):
        raiz_orig = etree.fromstring(cat.xml_comentarios, opacos.parser_seguro())
        elementos = [el for el in raiz_orig if el.tag == q("comment")]
        originais = [(el.get(q("id")), fx_comentarios.para_id_do_comentario(el)) for el in elementos]
    if originais is not None and originais == [(str(c.id), c.para_id) for c in cat.itens] \
            and len(originais) == len(cat.itens):
        # Nada mudou: os bytes de origem e as relacoes (links) que eles citam, com o mesmo Id.
        rels = []
        for c in cat.itens:
            for rid, tipo, alvo in c.relacoes:
                if not any(r[0] == rid for r in rels):
                    rels.append((rid, tipo, alvo, "External"))
        return cat.xml_comentarios, rels
    gravador = ctx.opacos
    nsmap = {**_NSMAP_PARTE, **gravador.espacos, "w14": W14_NS, "mc": MC_NS}
    raiz = etree.Element(q("comments"), nsmap=nsmap)
    ignoraveis = list(gravador.ignoraveis)
    if "w14" not in ignoraveis:
        ignoraveis.append("w14")
    raiz.set("{%s}Ignorable" % MC_NS, " ".join(ignoraveis))
    relacoes_doc = ctx.relacoes
    ctx.relacoes = _Relacoes(1)
    ctx.ids_marcadores = {}
    estilo_ref = ctx.estilo_de_caractere("CommentReference")
    try:
        for c in cat.itens:
            if c.original is not None:
                el = etree.fromstring(c.original, opacos.parser_seguro())
                trocas = {rid: ctx.relacoes.adicionar_com_id(rid, tipo, alvo, True)
                          for rid, tipo, alvo in c.relacoes}
                for x in el.iter():
                    if not isinstance(x.tag, str):
                        continue
                    for chave, valor in list(x.attrib.items()):
                        if chave.startswith("{%s}" % R_NS) and valor in trocas:
                            x.set(chave, trocas[valor])
                raiz.append(el)
            else:
                el = etree.SubElement(raiz, q("comment"))
                el.set(q("id"), str(int(c.id)))
                el.set(q("author"), texto_gravavel(c.autor)[0])
                if c.data:
                    el.set(q("date"), texto_gravavel(c.data)[0])
                if c.iniciais:
                    el.set(q("initials"), texto_gravavel(c.iniciais)[0])
                _blocos(el, list(c.paragrafos) or [Paragrafo()], ctx, em_celula=True)
                primeiro = el.find(".//" + q("p"))
                if primeiro is not None:
                    # A marca do comeco do comentario, como o Word grava (depois do pPr).
                    r = etree.Element(q("r"))
                    if estilo_ref is not None:
                        etree.SubElement(etree.SubElement(r, q("rPr")), q("rStyle")).set(
                            q("val"), estilo_ref)
                    etree.SubElement(r, q("annotationRef"))
                    tem_ppr = len(primeiro) and primeiro[0].tag == q("pPr")
                    primeiro.insert(1 if tem_ppr else 0, r)
            paragrafos = el.findall(".//" + q("p"))
            if c.para_id and paragrafos:
                paragrafos[-1].set("{%s}paraId" % W14_NS, c.para_id)
        rels = list(ctx.relacoes.itens)
    finally:
        ctx.relacoes = relacoes_doc
    return _xml(raiz), rels


def _partes_de_comentarios(doc: Documento, ctx: _Ctx) -> tuple[list, list]:
    """(partes, tipos de conteudo) dos comentarios; as relacoes vao para o documento."""
    cat = doc.comentarios
    if cat is None or not cat.itens:
        return [], []
    partes: list = []
    tipos: list = []
    xml, rels = _comentarios_xml(doc, ctx)
    partes.append((fx_comentarios.PARTE_COMENTARIOS, xml))
    if rels:
        partes.append(("word/_rels/comments.xml.rels", _rels_xml(rels)))
    tipos.append(("/" + fx_comentarios.PARTE_COMENTARIOS, fx_comentarios.CT_COMENTARIOS))
    ctx.relacoes.adicionar(fx_comentarios.tipo_rel(cat, "comentarios"), "comments.xml")
    quais = fx_comentarios.quais_partes(cat)
    for chave, parte, ct, gerar in (
            ("estendido", fx_comentarios.PARTE_ESTENDIDO, fx_comentarios.CT_ESTENDIDO,
             fx_comentarios.xml_estendido),
            ("ids", fx_comentarios.PARTE_IDS, fx_comentarios.CT_IDS, fx_comentarios.xml_ids),
            ("extensivel", fx_comentarios.PARTE_EXTENSIVEL, fx_comentarios.CT_EXTENSIVEL,
             fx_comentarios.xml_extensivel)):
        if chave not in quais:
            continue
        partes.append((parte, gerar(cat)))
        tipos.append(("/" + parte, ct))
        ctx.relacoes.adicionar(fx_comentarios.tipo_rel(cat, chave), parte.split("/", 1)[1])
    return partes, tipos


def _partes_de_notas(doc: Documento, ctx: _Ctx, tipos: list) -> tuple[list, list, dict]:
    """(partes, tipos de conteudo, sufixo -> ids das especiais) das notas (0.1.10); as
    relacoes vao para o documento."""
    cat = doc.notas
    partes: list = []
    conteudo: list = []
    especiais_ids: dict = {}
    relacoes_doc = ctx.relacoes
    for tipo in tipos:
        local = mod_notas.LOCAL[tipo]
        nome = fx_notas.PARTES[tipo]
        especiais = cat.especiais.get(tipo) or []
        if not especiais and cat.xml.get(tipo) is None and cat.raizes.get(tipo) is None:
            especiais = [mod_notas.Especial(t, i, x) for t, i, x in fx_notas.especiais_padrao(tipo)]
        especiais_ids[fx_notas.RAIZES[tipo]] = [e.id for e in especiais
                                                 if e.tipo_nota != "continuationNotice"]
        rels = _Relacoes(1)
        if not mod_notas.mudou(cat, tipo):
            # Nada mudou: os bytes de origem, e as relacoes com o mesmo Id (a imagem vai para a
            # parte de midia do escritor; so' o alvo muda).
            dados = cat.xml[tipo]
            for rid, t, alvo, externo, bruto in cat.relacoes_parte.get(tipo, ()):
                rels.reservar(rid, t, alvo if externo else ctx.midias.registrar_bytes(bruto),
                              externo)
        else:
            gravador = ctx.opacos
            raiz = fx_notas.raiz_nova(tipo, cat.raizes.get(tipo), _NSMAP_PARTE, gravador.espacos,
                                      list(gravador.ignoraveis))
            for nota in cat.itens.get(tipo, []):
                for rid, t, alvo, externo, bruto in (nota.relacoes if nota.original else ()):
                    if not any(item[0] == rid for item in rels.itens):
                        rels.reservar(rid, t, alvo if externo else ctx.midias.registrar_bytes(bruto),
                                      externo)
            for e in especiais:
                raiz.append(etree.fromstring(e.xml, opacos.parser_seguro()))
            ctx.relacoes = rels
            ctx.ids_marcadores = {}
            try:
                for nota in cat.itens.get(tipo, []):
                    if nota.original is not None:
                        raiz.append(etree.fromstring(nota.original, opacos.parser_seguro()))
                        continue
                    el = etree.SubElement(raiz, q(local))
                    el.set(q("id"), str(int(nota.id)))
                    _blocos(el, list(nota.paragrafos) or [Paragrafo()], ctx, em_celula=True)
            finally:
                ctx.relacoes = relacoes_doc
            dados = _xml(raiz)
        partes.append((nome, dados))
        if rels.itens:
            partes.append((ordem.caminho_dos_rels(nome), _rels_xml(rels.itens)))
        conteudo.append(("/" + nome, fx_notas.CT_NOTAS[tipo]))
        relacoes_doc.adicionar(cat.tipos_rel.get(tipo) or fx_notas.RT_NOTAS[tipo],
                               nome.split("/", 1)[1])
    return partes, conteudo, especiais_ids


def _reservar_das_notas(cat, ctx: _Ctx) -> None:
    """Ids que o XML de origem das notas ja' usa (marcador, wp:docPr): o que o escritor gera
    no corpo pula esses (0.1.10)."""
    xmls = [n.original for n in cat.todas() if n.original is not None]
    xmls += [cat.xml[t] for t in mod_notas.TIPOS if cat.xml.get(t) is not None]
    wp = "{%s}docPr" % WP_NS
    for xml in xmls:
        el = etree.fromstring(xml, opacos.parser_seguro())
        for b in el.iter(q("bookmarkStart")):
            try:
                ctx.marcadores_reservados.add(int(b.get(q("id"))))
            except (TypeError, ValueError):
                pass
        ctx.opacos.reservar_docpr(d.get("id") for d in el.iter(wp))


def _settings_xml(pares_impares: bool = False, notas: dict | None = None) -> bytes:
    raiz = etree.Element(q("settings"), nsmap={"w": W})
    etree.SubElement(raiz, q("zoom")).set(q("percent"), "100")
    etree.SubElement(raiz, q("defaultTabStop")).set(q("val"), "708")
    if pares_impares:
        # Na ordem do CT_Settings: depois de defaultTabStop, antes de characterSpacingControl.
        etree.SubElement(raiz, q("evenAndOddHeaders"))
    etree.SubElement(raiz, q("characterSpacingControl")).set(q("val"), "doNotCompress")
    for sufixo, local in (("footnotes", "footnote"), ("endnotes", "endnote")):
        # Notas (0.1.10): as especiais da parte, como o Word grava (antes do compat).
        ids = (notas or {}).get(sufixo)
        if ids:
            pr = etree.SubElement(raiz, q(local + "Pr"))
            for ident in ids:
                etree.SubElement(pr, q(local)).set(q("id"), str(int(ident)))
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


def _extensoes_usadas(doc: Documento) -> dict[str, str]:
    """prefixo -> namespace das extensoes do Word nos extras e nos controles de conteudo."""
    saida: dict[str, str] = {}
    vistos: set = set()
    from editdoc.modelo.marcas import historias
    listas = list(historias(doc))
    if doc.comentarios is not None:
        # O conteudo gerado dos comentarios (0.1.6) tambem pode ter extensoes nos extras.
        listas += [list(c.paragrafos) for c in doc.comentarios.itens if c.original is None]
    if doc.notas is not None:
        listas += [list(n.paragrafos) for n in doc.notas.todas() if n.original is None]
    for blocos in listas:
        for p in paragrafos_de(blocos):
            textos = [p.extras] + [r.extras for r in p.runs]
            textos += [r.marca.propriedades.decode("utf-8") for r in p.runs
                       if isinstance(r.marca, MarcaConteudo) and r.marca.propriedades]
            textos += [x for r in p.runs if isinstance(r.marca, MarcaCampo) and r.marca.campo
                       for x in (r.marca.campo.rpr_codigo, r.marca.campo.rpr_separador) if x]
            for texto in textos:
                if texto and texto not in vistos and "xmlns:" in texto.replace('xmlns:w="', ""):
                    vistos.add(texto)
                    saida.update(fx_props.namespaces_usados(texto))
    return saida


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
    if desfeitos.get("conteudos"):
        coletor.somar("CONTEUDO_INCOMPLETO", desfeitos["conteudos"])
    if desfeitos.get("comentarios"):
        coletor.somar("COMENTARIO_INCOMPLETO", desfeitos["comentarios"])
    # Comentarios (0.1.6): paraId e durableId de quem nao tem; o autor novo no people.xml.
    doc = fx_comentarios.preparar(doc)
    # Notas (0.1.10): so' as com referencia no corpo, ids unicos.
    doc = mod_notas.preparar(doc)
    # Listas montadas em codigo so' com o tipo: numId e definicao (0.1.4).
    doc = materializado(doc)
    tem_comentarios = doc.comentarios is not None and bool(doc.comentarios.itens)
    tipos_notas = tipos_de_notas(doc)
    ctx = _Ctx(coletor, doc.estilos, doc.pacote, tem_comentarios,
               [fx_notas.PARTES[t] for t in tipos_notas])
    ctx.numeracao = doc.numeracao
    objetos = list(objetos_de(doc))
    if tem_comentarios:
        objetos += [r.objeto for c in doc.comentarios.itens if c.original is None
                    for p in paragrafos_de(list(c.paragrafos)) for r in p.runs
                    if r.objeto is not None]
    if doc.notas is not None:
        objetos += [r.objeto for n in doc.notas.todas() if n.original is None
                    for p in paragrafos_de(list(n.paragrafos)) for r in p.runs
                    if r.objeto is not None]
    ctx.opacos.preparar(objetos, _NSMAP_PARTE)
    if doc.notas is not None:
        _reservar_das_notas(doc.notas, ctx)
    # Extensoes do Word nos extras e nos controles de conteudo (w14, w15...): a raiz declara
    # e as poe no mc:Ignorable (0.1.5).
    ctx.opacos.declarar_extensoes(_extensoes_usadas(doc), _NSMAP_PARTE)
    agora = _agora_iso()
    criado = doc.criado_em or agora
    modificado = doc.modificado_em or agora
    documento_xml, faixas = _document_xml(doc, ctx)
    partes_comentarios, tipos_comentarios = _partes_de_comentarios(doc, ctx)
    partes_notas, tipos_conteudo_notas, especiais_notas = _partes_de_notas(doc, ctx, tipos_notas)
    tema = ctx.estilos.tema_original
    gravador = ctx.pacote
    extras_tipos = list(faixas.tipos) + list(ctx.opacos.tipos) + gravador.tipos() \
        + tipos_comentarios + tipos_conteudo_notas
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
    # Numeracao (0.1.4): o numbering.xml do catalogo e as imagens dos marcadores de figura,
    # com as relacoes do proprio numbering.xml (Id mantido: o XML nao muda).
    numeracao = doc.numeracao
    numbering_xml = fx_numeracao.escrever(numeracao)
    rels_numeracao = ctx.opacos.gravar_fecho(numeracao.relacoes, numeracao.partes) \
        if numeracao is not None and numeracao.relacoes else []
    partes_numeracao = [("word/_rels/numbering.xml.rels", _rels_xml(rels_numeracao))] \
        if rels_numeracao else []
    extras_tipos += [t for t in ctx.opacos.tipos if t not in extras_tipos]
    listas = set(numeracao.instancias) if numeracao is not None else set()
    configuracoes = gravador.configuracoes(doc.pagina.pares_impares, especiais_notas) or \
        _settings_xml(doc.pagina.pares_impares, especiais_notas)
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
        *partes_comentarios,
        *partes_notas,
        ("word/styles.xml", fx_estilos.escrever_estilos(ctx.estilos, listas)),
        *partes_tema,
        ("word/numbering.xml", numbering_xml),
        *partes_numeracao,
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
    problemas = ordem.validar(mapa, ctx.estilos.virtuais())
    if problemas:
        raise ErroDocx("ESCRITA_INVALIDA", "; ".join(problemas[:3]))
    return _zip(partes), coletor.avisos()


def tipos_de_notas(doc: Documento) -> list:
    """Os tipos de nota cuja parte o escritor grava (0.1.10): a que o arquivo tinha e o leitor
    leu, e a que ganhou nota no EditDoc. A parte que o leitor nao leu continua preservada pelo
    pacote (so' as separadoras), e o EditDoc nao cria nota desse tipo."""
    cat = doc.notas
    if cat is None:
        return []
    pacote = doc.pacote
    saida = []
    for tipo in mod_notas.TIPOS:
        sufixo = fx_notas.RAIZES[tipo]
        preservada = pacote is not None and any(
            t.rstrip("/").rsplit("/", 1)[-1] == sufixo for t, _a, _e in pacote.do_documento)
        if preservada:
            continue
        if tipo in cat.tipos_rel or cat.itens.get(tipo):
            saida.append(tipo)
    return saida


def escrever(doc: Documento) -> bytes:
    return escrever_com_avisos(doc)[0]
