"""Quebras de secao e de coluna no QTextDocument (0.1.12).

A quebra de secao e' o caractere de objeto (U+FFFC) no FIM do ultimo paragrafo da secao, com o
tipo de objeto TIPO_QUEBRA e, em JSON (PROP_QUEBRA), o id da secao no registro do documento
(`registro`). Como no Word, a marca de paragrafo daquele paragrafo E' a quebra: apagar o
caractere funde a secao com a seguinte (a de cima passa a ter as propriedades da de baixo, que
continuam no caractere seguinte, ou na ultima secao). Enter antes dele leva a quebra para o
paragrafo novo. O desfazer e' o do texto: o caractere entra e sai com o passo do usuario.

O registro (id -> `Secao`, sem o conteudo dos cabecalhos; `Secao.chaves` aponta para as faixas
do `ConjuntoDeFaixas`) fica no documento, fora do desfazer: o id do caractere nunca muda, entao
desfazer a remocao do caractere devolve a secao com as propriedades que ela tinha. A ultima
secao fica em `secao_final(doc)` (o papel dela continua sendo o `LayoutPaginado.pagina_arquivo`).

A quebra de coluna e' o mesmo objeto com {"coluna": true}: sem largura, volta ao arquivo como
w:br w:type="column" (a tela mostra uma coluna so').

As duas sao pintadas so' com as marcas de formatacao ligadas (`desenhar_marcas`): a linha dupla
pontilhada "Quebra de seção (Próxima página)" do Word.

Formatos derivados (feitos por `interface/secoes.py`, nunca pelo usuario):
- PROP_QUEBRA_SECAO no bloco (ou na tabela): a quebra de pagina que a secao seguinte pede
  (PageBreak_AlwaysAfter no paragrafo da quebra; PageBreak_AlwaysBefore na unidade seguinte,
  para a pagina em branco de evenPage/oddPage). Nao volta ao arquivo (`de_qt`);
- PROP_RECUO_SECAO (`ponte_qt/estilos.py`): o recuo direito escondido que estreita o texto de
  uma secao mais estreita que a mais larga (o QTextDocument tem uma largura so').
"""

from __future__ import annotations

import copy
import itertools
import json

from PySide6.QtCore import QSizeF
from PySide6.QtGui import QPyTextObject, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat

from editdoc import log_interno
from editdoc.modelo.documento import CARACTERE_OBJETO
from editdoc.modelo.secoes import Secao

log = log_interno.obter(__name__)

#: Tipo do objeto da quebra (UserObject + 6, o proximo livre depois da nota).
TIPO_QUEBRA = QTextFormat.ObjectTypes.UserObject.value + 6
_USUARIO = QTextFormat.Property.UserProperty.value
#: Caractere: {"secao": id} ou {"coluna": true}.
PROP_QUEBRA = _USUARIO + 35
#: Bloco ou tabela: a quebra de pagina e' derivada da secao (nao e' do usuario).
PROP_QUEBRA_SECAO = _USUARIO + 36
#: Quadro raiz: o id (no registro) da ultima secao trocada por uma edicao (inserir quebra de
#: secao muda o tipo dela). No quadro raiz, a troca entra no desfazer do passo aberto.
PROP_SECAO_FINAL = _USUARIO + 38
#: Propriedades que nao passam para o texto digitado depois da quebra.
PROPS_DE_QUEBRA = (QTextFormat.Property.ObjectType, PROP_QUEBRA)
_IDS = itertools.count(1)


# -- registro ----------------------------------------------------------------------------------

def registro(doc: QTextDocument) -> dict:
    """id -> Secao das secoes que terminam em paragrafo (as vivas e as que o desfazer devolve)."""
    reg = getattr(doc, "_secoes", None)
    if reg is None:
        reg = {}
        try:
            doc._secoes = reg
        except AttributeError:
            pass
    return reg


def secao_final(doc: QTextDocument) -> Secao:
    """Tipo, extras, XML de origem e cabecalhos (chaves) da ultima secao: a do registro que o
    quadro raiz aponta (depois de uma edicao), ou a do arquivo."""
    ident = doc.rootFrame().frameFormat().property(PROP_SECAO_FINAL)
    if isinstance(ident, str) and ident:
        achada = registro(doc).get(ident)
        if achada is not None:
            return achada
    final = getattr(doc, "_secao_final", None)
    if final is None:
        final = Secao()
        try:
            doc._secao_final = final
        except AttributeError:
            pass
    return final


def limpar(doc: QTextDocument) -> None:
    """Documento novo carregado: registro vazio."""
    try:
        doc._secoes = {}
        doc._secao_final = Secao()
        doc._cache_quebras = None
    except AttributeError:
        pass


def trocar_final(doc: QTextDocument, secao: Secao) -> str:
    """A ultima secao passa a ser `secao` (no desfazer do bloco de edicao aberto)."""
    ident = guardar(doc, secao)
    quadro = doc.rootFrame()
    ff = quadro.frameFormat()
    ff.setProperty(PROP_SECAO_FINAL, ident)
    quadro.setFrameFormat(ff)
    return ident


def trocar_secao_do_caractere(cursor: QTextCursor, pos: int, secao: Secao) -> str:
    """O caractere da quebra em `pos` passa a apontar para `secao` (nova entrada no registro):
    a troca e' de formato, entra no desfazer."""
    doc = cursor.document()
    ident = guardar(doc, secao)
    c = QTextCursor(doc)
    c.setPosition(pos)
    c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
    fmt = c.charFormat()
    for frag_fmt in (_formato_no(doc, pos),):
        if frag_fmt is not None:
            fmt = frag_fmt
    fmt.setProperty(PROP_QUEBRA, json.dumps({"secao": ident}))
    c.setCharFormat(fmt)
    return ident


def _formato_no(doc: QTextDocument, pos: int):
    bloco = doc.findBlock(pos)
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and frag.position() <= pos < frag.position() + frag.length():
            return QTextCharFormat(frag.charFormat())
        it += 1
    return None


def copia(secao: Secao, **mudancas) -> Secao:
    """Copia da secao (sem conteudo), com `mudancas` (tipo=...)."""
    nova = sem_conteudo(secao)
    for k, v in mudancas.items():
        setattr(nova, k, v)
    return nova


def novo_id(doc: QTextDocument) -> str:
    reg = registro(doc)
    while True:
        ident = f"s{next(_IDS)}"
        if ident not in reg:
            return ident


def guardar(doc: QTextDocument, secao: Secao, ident: str | None = None) -> str:
    """Poe a secao no registro (sem o conteudo dos cabecalhos). Devolve o id."""
    ident = ident or novo_id(doc)
    registro(doc)[ident] = sem_conteudo(secao)
    return ident


def sem_conteudo(secao: Secao) -> Secao:
    """Copia da secao sem os blocos dos cabecalhos (eles vivem nas faixas do layout)."""
    return Secao(pagina=copy.deepcopy(secao.pagina), tipo=secao.tipo, extras=secao.extras,
                 original=secao.original, chaves=dict(secao.chaves), colunas=secao.colunas)


# -- formato ---------------------------------------------------------------------------------

def eh_quebra(fmt: QTextFormat) -> bool:
    return fmt.objectType() == TIPO_QUEBRA


def dado_de(fmt: QTextFormat) -> dict | None:
    if not eh_quebra(fmt):
        return None
    try:
        dado = json.loads(str(fmt.property(PROP_QUEBRA)))
    except (TypeError, ValueError):
        return None
    return dado if isinstance(dado, dict) else None


def id_de(fmt: QTextFormat) -> str | None:
    """O id da secao, se o caractere e' quebra de secao."""
    dado = dado_de(fmt)
    ident = dado.get("secao") if dado else None
    return ident if isinstance(ident, str) and ident else None


def eh_coluna(fmt: QTextFormat) -> bool:
    dado = dado_de(fmt)
    return bool(dado and dado.get("coluna") is True)


def formato_de_quebra(base: QTextCharFormat | None, dado: dict) -> QTextCharFormat:
    cf = QTextCharFormat(base) if base is not None else QTextCharFormat()
    for prop in (QTextFormat.Property.ImageName, QTextFormat.Property.ImageWidth,
                 QTextFormat.Property.ImageHeight, QTextFormat.Property.TextToolTip,
                 QTextFormat.Property.AnchorHref, QTextFormat.Property.IsAnchor):
        cf.clearProperty(prop)
    cf.setObjectType(TIPO_QUEBRA)
    cf.setProperty(PROP_QUEBRA, json.dumps(dado))
    return cf


def inserir_secao(cursor: QTextCursor, secao: Secao, base: QTextCharFormat | None = None,
                  ident: str | None = None) -> str:
    """Insere a quebra de secao no cursor. Devolve o id da secao no registro."""
    doc = cursor.document()
    ident = guardar(doc, secao, ident)
    cursor.insertText(CARACTERE_OBJETO, formato_de_quebra(base, {"secao": ident}))
    return ident


def inserir_coluna(cursor: QTextCursor, base: QTextCharFormat | None = None) -> None:
    cursor.insertText(CARACTERE_OBJETO, formato_de_quebra(base, {"coluna": True}))


def secao_do_formato(doc: QTextDocument, fmt: QTextFormat) -> Secao | None:
    ident = id_de(fmt)
    return registro(doc).get(ident) if ident is not None else None


def _varrer(doc: QTextDocument, inicio: int = 0, fim: int | None = None) -> list:
    saida: list[tuple[int, str]] = []
    bloco = doc.findBlock(inicio) if inicio else doc.begin()
    while bloco.isValid():
        if fim is not None and bloco.position() > fim:
            break
        achadas = _quebras_do_bloco(bloco)
        if achadas and QTextCursor(bloco).currentTable() is None:
            saida.extend((p, i) for p, i in achadas
                         if p >= inicio and (fim is None or p < fim))
        bloco = bloco.next()
    return saida


def _mudou(doc: QTextDocument, pos: int, removidos: int, adicionados: int) -> None:
    """Acompanha a mudanca sem varrer o documento a cada tecla (como as marcas das notas): as
    quebras depois do trecho andam; quebra apagada ou trocada, ou trecho novo grande, refaz
    tudo na proxima consulta."""
    cache = getattr(doc, "_cache_quebras", None)
    if cache is None:
        return
    lista = cache[1]
    if any(pos <= p < pos + max(removidos, 1) for p, _i in lista) or adicionados > 100_000:
        doc._cache_quebras = None
        return
    delta = adicionados - removidos
    novas = [(p + delta if p >= pos + removidos else p, i) for p, i in lista]
    if adicionados and registro(doc):
        novas += _varrer(doc, pos, pos + adicionados)
        novas.sort(key=lambda x: x[0])
    doc._cache_quebras = ((doc.revision(), doc.characterCount()), novas)


def quebras_de_secao(doc: QTextDocument, fresco: bool = False) -> list[tuple[int, str]]:
    """(posicao, id) de cada quebra de secao do corpo, na ordem (fora de tabela). Em cache pela
    revisao e pelo tamanho, acompanhado pelo `contentsChange`; dentro de um bloco de edicao
    aberto a revisao nao muda: quem edita ali pede `fresco=True`."""
    if not getattr(doc, "_quebras_ligado", False):
        try:
            doc._quebras_ligado = True
        except AttributeError:
            return _varrer(doc) if registro(doc) else []
        doc.contentsChange.connect(lambda p, r, a, d=doc: _mudou(d, p, r, a))
    chave = (doc.revision(), doc.characterCount())
    cache = getattr(doc, "_cache_quebras", None)
    if not fresco and cache is not None and cache[0] == chave:
        return cache[1]
    saida = _varrer(doc) if registro(doc) else []
    doc._cache_quebras = (chave, saida)
    return saida


def _quebras_do_bloco(bloco) -> list[tuple[int, str]]:
    saida = []
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and eh_quebra(frag.charFormat()):
            ident = id_de(frag.charFormat())
            if ident is not None:
                saida.extend((frag.position() + i, ident)
                             for i, c in enumerate(frag.text()) if c == CARACTERE_OBJETO)
        it += 1
    return saida


def quebra_no_bloco(bloco) -> str | None:
    """O id da quebra de secao do bloco (a ultima, se houver mais de uma), ou None."""
    achadas = _quebras_do_bloco(bloco)
    return achadas[-1][1] if achadas else None


def posicao_da_quebra_no_bloco(bloco) -> int | None:
    achadas = _quebras_do_bloco(bloco)
    return achadas[-1][0] if achadas else None


def eh_derivada(fmt: QTextFormat) -> bool:
    return bool(fmt.property(PROP_QUEBRA_SECAO))


def quebra_so_depois(fmt: QTextFormat) -> bool:
    """Quebra de pagina do USUARIO que fica no fim do paragrafo (0.1.22): PageBreak_AlwaysAfter
    sem a quebra derivada da secao. O paragrafo que so' tem a quebra (w:br type="page") fica na
    pagina de cima, como no Word, e a pagina seguinte comeca no paragrafo de baixo. A quebra
    derivada da secao (PROP_QUEBRA_SECAO) e a do espacador das notas nao contam."""
    return bool(fmt.pageBreakPolicy() & QTextFormat.PageBreakFlag.PageBreak_AlwaysAfter) \
        and not eh_derivada(fmt)


# -- pintura ---------------------------------------------------------------------------------

class ManipuladorDeQuebra(QPyTextObject):
    """Sem largura e sem pintura: a linha da quebra sai com as marcas de formatacao."""

    def intrinsicSize(self, doc, pos, fmt) -> QSizeF:  # noqa: N802 - nome do Qt
        return QSizeF(0.0, 0.0)

    def drawObject(self, painter, rect, doc, pos, fmt) -> None:  # noqa: N802 - nome do Qt
        return


def registrar_manipulador(doc: QTextDocument) -> ManipuladorDeQuebra:
    manipulador = ManipuladorDeQuebra(doc)
    doc.documentLayout().registerHandler(TIPO_QUEBRA, manipulador)
    return manipulador
