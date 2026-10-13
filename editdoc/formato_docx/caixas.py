"""Texto das caixas de texto (0.1.5): ler para editar e regravar dentro do objeto opaco. Sem Qt.

A caixa de texto continua um objeto opaco (`opacos.py`): a forma (posicao, tamanho, cor,
contorno, quebra de texto) volta byte a byte. So' o conteudo do w:txbxContent muda, e nas
DUAS representacoes quando o objeto tem mc:AlternateContent: o wps:txbx do Choice (DrawingML)
e o v:textbox do Fallback (VML), que o Word grava com o mesmo texto.

`analisar` diz se a caixa pode ser editada e devolve os blocos (o modelo de sempre:
paragrafos, runs, formatacao, extras, listas, links). So' e' editavel o que o EditDoc sabe
regravar sem perda: paragrafos com texto, tabulacao, quebra de linha, hiperlinks e a
formatacao (inclusive a preservada). Tabela, imagem, forma ou caixa dentro da caixa, campo,
controle de conteudo, marcador, nota, comentario, equacao e revisao deixam a caixa so' para
leitura, com o motivo. E mais uma trava: o conteudo lido e' regravado e relido na hora; se
nao volta igual, a caixa fica so' para leitura ("o EditDoc nao regravaria sem perda").

O marcador oculto "_GoBack" (o Word o poe no ultimo ponto editado) nao conta: sai na edicao.

`regravar` troca o conteudo de cada w:txbxContent de primeiro nivel pelo XML que o escritor
gera dos blocos, refaz as relacoes dos links (rIds novos "rIdCx", sem colidir com os do
objeto) e o resumo da tela.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace

from lxml import etree

from editdoc.formato_docx import opacos
from editdoc.formato_docx.avisos import Coletor
from editdoc.formato_docx.nomes import MC_NS, R_NS, RT, W, q
from editdoc.modelo.documento import (Documento, ObjetoOpaco, Paragrafo, Tabela, normalizar,
                                      paragrafos_de)

RT_HIPERLINK = RT + "hyperlink"
_TXBX = q("txbxContent")
#: Filhos de w:p que a caixa editavel pode ter.
_NO_PARAGRAFO = {"pPr", "r", "hyperlink", "proofErr", "bookmarkStart", "bookmarkEnd",
                 "permStart", "permEnd"}
#: Filhos de w:r que a caixa editavel pode ter.
_NO_RUN = {"rPr", "t", "tab", "br", "cr", "noBreakHyphen", "softHyphen",
           "lastRenderedPageBreak"}
_MOTIVOS = {
    "tbl": "tem uma tabela",
    "drawing": "tem uma imagem ou forma dentro",
    "pict": "tem uma imagem ou forma dentro",
    "object": "tem um objeto incorporado",
    "AlternateContent": "tem uma imagem ou forma dentro",
    "fldChar": "tem um campo",
    "instrText": "tem um campo",
    "fldSimple": "tem um campo",
    "sdt": "tem um controle de conteúdo",
    "footnoteReference": "tem uma nota de rodapé",
    "endnoteReference": "tem uma nota de fim",
    "commentReference": "tem um comentário",
    "commentRangeStart": "tem um comentário",
    "ins": "tem alterações controladas",
    "del": "tem alterações controladas",
    "moveFrom": "tem alterações controladas",
    "moveTo": "tem alterações controladas",
    "oMath": "tem uma equação",
    "oMathPara": "tem uma equação",
    "sym": "tem um símbolo de fonte especial",
    "bookmarkStart": "tem um marcador",
}


@dataclass
class Analise:
    """Resultado de `analisar`: editavel, o motivo de nao ser, e os blocos lidos."""
    editavel: bool
    motivo: str = ""
    blocos: list | None = None
    texto: str = ""  # texto simples da caixa (para o modo so' leitura)


def _parse(xml: bytes):
    return etree.fromstring(xml, opacos.parser_seguro())


def conteudos(el) -> list:
    """Os w:txbxContent de primeiro nivel do objeto (nao os de uma caixa dentro de caixa)."""
    saida = []
    for t in el.iter(_TXBX):
        pai = t.getparent()
        dentro = False
        while pai is not None:
            if pai.tag == _TXBX:
                dentro = True
                break
            pai = pai.getparent()
        if not dentro:
            saida.append(t)
    return saida


def _principal(el):
    """O w:txbxContent que o Word mostra: o do Choice (ou o primeiro)."""
    for t in conteudos(el):
        pai = t.getparent()
        while pai is not None and pai.tag != "{%s}Fallback" % MC_NS:
            pai = pai.getparent()
        if pai is None:
            return t
    lista = conteudos(el)
    return lista[0] if lista else None


def _texto_simples(caixa) -> str:
    linhas = []
    for p in caixa.iter(q("p")):
        partes = []
        for x in p.iter(q("t"), q("tab"), q("br")):
            if x.getparent() is None or x.getparent().tag != q("r"):
                continue  # w:tab de w:tabs (a definicao da tabulacao), nao o caractere
            if x.tag == q("t"):
                partes.append(x.text or "")
            elif x.tag == q("tab"):
                partes.append("\t")
            else:
                partes.append("\n")
        linhas.append("".join(partes))
    return "\n".join(linhas)


def _motivo(caixa) -> str:
    """Por que o conteudo nao e' editavel ("" se e')."""
    for x in caixa.iter():
        if not isinstance(x.tag, str) or x is caixa:
            continue
        qn = etree.QName(x)
        loc = qn.localname
        if loc in _MOTIVOS and not (loc == "bookmarkStart" and (x.get(q("name")) or "") == "_GoBack"):
            if loc in ("ins", "del") and x.getparent() is not None and x.getparent().tag == q("rPr"):
                return _MOTIVOS[loc]
            return _MOTIVOS[loc]
        pai = x.getparent()
        if pai is caixa and x.tag != q("p"):
            return _MOTIVOS.get(loc, "tem um conteúdo que o EditDoc não edita")
        if pai is not None and pai.tag == q("p") and loc not in _NO_PARAGRAFO:
            return "tem um conteúdo que o EditDoc não edita"
        if pai is not None and pai.tag == q("r") and loc not in _NO_RUN:
            return "tem um conteúdo que o EditDoc não edita"
        if x.tag == q("br") and (x.get(q("type")) or "textWrapping") != "textWrapping":
            return "tem uma quebra de página ou de coluna"
    return ""


def _sem_goback(caixa):
    copia = copy.deepcopy(caixa)
    marcados = [x for x in copia.iter(q("bookmarkStart")) if x.get(q("name")) == "_GoBack"]
    ids = {x.get(q("id")) for x in marcados}
    for x in marcados:
        x.getparent().remove(x)
    for x in list(copia.iter(q("bookmarkEnd"))):
        if x.get(q("id")) in ids:
            x.getparent().remove(x)
    return copia


def _ler_blocos(caixa, obj: ObjetoOpaco, estilos, numeracao) -> tuple[list, Coletor]:
    from editdoc.formato_docx import leitor
    coletor = Coletor()
    ctx = leitor._Contexto(coletor, numeracao)
    if estilos is not None:
        ctx.estilos = estilos
    ctx.relacoes = {rid: (tipo, alvo, externo) for rid, tipo, alvo, externo in obj.relacoes}
    ctx.capturador = None
    blocos: list = []
    leitor._blocos(caixa, blocos, ctx)
    leitor._fechar_historia(blocos, ctx)
    return blocos, coletor


def _comparavel(blocos, estilos, numeracao) -> list:
    return normalizar(Documento(paragrafos=copy.deepcopy(blocos), estilos=estilos,
                                numeracao=numeracao)).paragrafos


def analisar(obj: ObjetoOpaco | None, estilos=None, numeracao=None) -> Analise:
    """Se a caixa pode ser editada no EditDoc, e o conteudo dela em blocos do modelo."""
    if obj is None or obj.tipo != "caixa_de_texto":
        return Analise(False, "não é uma caixa de texto")
    try:
        el = _parse(obj.xml)
    except (etree.LxmlError, ValueError):
        return Analise(False, "o XML da caixa não pôde ser lido")
    caixa = _principal(el)
    if caixa is None:
        return Analise(False, "a forma não tem texto")
    texto = _texto_simples(caixa)
    motivo = _motivo(caixa)
    if motivo:
        return Analise(False, f"A caixa {motivo}, e o EditDoc não regravaria isso sem perda.",
                       texto=texto)
    try:
        blocos, coletor = _ler_blocos(_sem_goback(caixa), obj, estilos, numeracao)
    except Exception:  # noqa: BLE001 - conteudo estranho: so' leitura, nunca corromper
        return Analise(False, "O conteúdo da caixa não pôde ser lido para edição.", texto=texto)
    if any(a.perde_ao_salvar for a in coletor.avisos()):
        return Analise(False, "A caixa tem formatação que o EditDoc não regravaria sem perda.",
                       texto=texto)
    if any(isinstance(b, Tabela) for b in blocos) or any(
            r.eh_objeto() or r.campo is not None or r.marca is not None
            for p in paragrafos_de(blocos) for r in p.runs):
        return Analise(False, "A caixa tem um conteúdo que o EditDoc não edita.", texto=texto)
    if not blocos:
        blocos = [Paragrafo()]
    # A trava final: regravar e reler na hora tem de dar o mesmo conteudo.
    try:
        novo = regravar(obj, blocos, estilos, numeracao, conferir=False)
        relido, _c = _ler_blocos(_principal(_parse(novo.xml)), novo, estilos, numeracao)
    except Exception:  # noqa: BLE001
        return Analise(False, "O EditDoc não conseguiu regravar a caixa sem perda.", texto=texto)
    if _comparavel(relido, estilos, numeracao) != _comparavel(blocos, estilos, numeracao):
        return Analise(False, "O EditDoc não regravaria esta caixa sem perda.", texto=texto)
    return Analise(True, "", blocos, texto)


class _RelacoesDaCaixa:
    """rIds novos para os links da caixa, sem colidir com os do objeto."""

    def __init__(self, usados: set[str]) -> None:
        self._usados = set(usados)
        self._por_alvo: dict = {}
        self.itens: list[tuple] = []
        self._n = 1

    def adicionar(self, tipo: str, alvo: str, externo: bool = False) -> str:
        chave = (tipo, alvo, externo)
        if chave not in self._por_alvo:
            while f"rIdCx{self._n}" in self._usados:
                self._n += 1
            rid = f"rIdCx{self._n}"
            self._usados.add(rid)
            self._por_alvo[chave] = rid
            self.itens.append((rid, tipo, alvo, externo))
        return self._por_alvo[chave]


def regravar(obj: ObjetoOpaco, blocos: list, estilos=None, numeracao=None,
             conferir: bool = True) -> ObjetoOpaco:
    """O objeto com o conteudo das caixas trocado pelos blocos. O resto do XML fica igual.

    Levanta ValueError se os blocos tem o que a caixa nao aceita (tabela, imagem, objeto,
    campo, marca) ou se a releitura nao confere."""
    from editdoc.formato_docx import escritor
    from editdoc.formato_docx.avisos import Coletor as _Coletor
    if any(isinstance(b, Tabela) for b in blocos):
        raise ValueError("tabela na caixa de texto")
    for p in paragrafos_de(blocos):
        if any(r.eh_objeto() or r.campo is not None or r.marca is not None for r in p.runs):
            raise ValueError("imagem, objeto, campo ou marca na caixa de texto")
    el = _parse(obj.xml)
    caixas = conteudos(el)
    if not caixas:
        raise ValueError("objeto sem w:txbxContent")
    rids_antes = set(opacos.referencias(el))
    ctx = escritor._Ctx(_Coletor(), estilos, None)
    ctx.numeracao = numeracao
    relacoes = _RelacoesDaCaixa(rids_antes | {r[0] for r in obj.relacoes})
    ctx.relacoes = relacoes
    ctx.em_tabela = 1  # caixa: sem o docDefaults por baixo, como a celula (base dos extras)
    modelo = etree.Element(_TXBX, nsmap={"w": W, "r": R_NS})
    escritor._blocos(modelo, normalizar(Documento(paragrafos=list(blocos), estilos=estilos,
                                                  numeracao=numeracao)).paragrafos,
                     ctx, em_celula=True)
    for caixa in caixas:
        for f in list(caixa):
            caixa.remove(f)
        for f in modelo:
            caixa.append(copy.deepcopy(f))
    usados = set(opacos.referencias(el))
    novas = [r for r in obj.relacoes if r[0] in usados]
    novas += [r for r in relacoes.itens if r[0] in usados]
    item = next((f for f in el if f.tag != q("rPr")), el)
    resultado = replace(obj, xml=etree.tostring(el), relacoes=tuple(novas),
                        resumo=opacos.resumo(item))
    if conferir:
        analise = analisar(resultado, estilos, numeracao)
        if not analise.editavel or _comparavel(analise.blocos, estilos, numeracao) != \
                _comparavel(blocos, estilos, numeracao):
            raise ValueError("a caixa regravada nao confere com o texto editado")
    return resultado
