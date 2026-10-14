"""Comentarios no QTextDocument (0.1.6): o catalogo, as ancoras e o realce na tela.

- As ancoras (inicio, fim e referencia) sao marcas sem largura no texto (`ponte_qt/marcas.py`,
  TIPO_MARCADOR com o JSON da `MarcaComentario`): o teclado pula, o desfazer as devolve.
- O catalogo (`modelo/comentarios.py`) fica como os estilos e as listas: o do arquivo num
  atributo do documento (`_comentarios_base`, com os bytes das partes de origem) e o vigente
  no formato do quadro raiz (PROP_COMENTARIOS), que entra no desfazer junto com o bloco de
  edicao aberto (medido no Qt 6.11.2: a troca do formato do quadro raiz sozinha num bloco de
  edicao tambem vira um passo de desfazer e marca o documento como alterado). O JSON leva so'
  as chaves de um registro deste modulo: cada `Comentario` e' imutavel, e uma edicao cria
  outro (o desfazer volta a chave antiga, que continua no registro).
- O trecho comentado e' realcado pela pintura da folha (`selecoes_de_realce`), so' na tela:
  a impressao e o PDF nao passam o realce.
"""

from __future__ import annotations

import json
import uuid

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat

from editdoc.modelo.comentarios import Comentario, Comentarios
from editdoc.modelo.documento import CARACTERE_OBJETO, MarcaComentario
from editdoc.ponte_qt import marcas

#: Quadro raiz: as chaves dos comentarios vigentes, em JSON. Numero livre (ver CLAUDE.md).
PROP_COMENTARIOS = QTextFormat.Property.UserProperty.value + 30
#: Realce do trecho comentado na tela (amarelo claro) e do comentario resolvido (mais claro).
COR_REALCE = QColor(0xFF, 0xF1, 0x9C)
COR_REALCE_RESOLVIDO = QColor(0xF3, 0xF0, 0xE2)
COR_REALCE_ATIVO = QColor(0xFF, 0xD9, 0x5A)

_REGISTRO: dict[str, Comentario] = {}
_CHAVES: dict[int, str] = {}


def _chave(c: Comentario) -> str:
    k = _CHAVES.get(id(c))
    if k is None or _REGISTRO.get(k) is not c:
        k = uuid.uuid4().hex
        _REGISTRO[k] = c
        _CHAVES[id(c)] = k
    return k


def definir_base(doc: QTextDocument, cat: Comentarios | None) -> None:
    """O catalogo ao abrir. Nao entra no desfazer: tira a propriedade do quadro raiz."""
    doc._comentarios_base = cat
    doc._comentarios_cache = None
    doc._ancoras_cache = None
    quadro = doc.rootFrame()
    ff = quadro.frameFormat()
    if ff.hasProperty(PROP_COMENTARIOS):
        ff.clearProperty(PROP_COMENTARIOS)
        quadro.setFrameFormat(ff)


def catalogo(doc: QTextDocument) -> Comentarios:
    """O catalogo vigente (vazio se o documento nao tem comentarios)."""
    base = getattr(doc, "_comentarios_base", None)
    bruto = doc.rootFrame().frameFormat().property(PROP_COMENTARIOS)
    if not isinstance(bruto, str) or not bruto:
        return base if base is not None else Comentarios()
    cache = getattr(doc, "_comentarios_cache", None)
    if cache is not None and cache[0] == bruto and cache[1] is base:
        return cache[2]
    try:
        chaves = json.loads(bruto).get("itens") or []
    except (ValueError, AttributeError):
        chaves = []
    itens = [_REGISTRO[k] for k in chaves if isinstance(k, str) and k in _REGISTRO]
    cat = (base if base is not None else Comentarios()).com_itens(itens)
    doc._comentarios_cache = (bruto, base, cat)
    return cat


def trocar(doc: QTextDocument, itens: list[Comentario]) -> None:
    """Grava o catalogo novo no quadro raiz. Dentro de um beginEditBlock, fica no mesmo passo."""
    quadro = doc.rootFrame()
    ff = quadro.frameFormat()
    ff.setProperty(PROP_COMENTARIOS, json.dumps({"itens": [_chave(c) for c in itens]}))
    quadro.setFrameFormat(ff)


def assinatura(doc: QTextDocument) -> tuple:
    """Muda quando o catalogo ou o texto muda (o painel de comentarios redesenha)."""
    bruto = doc.rootFrame().frameFormat().property(PROP_COMENTARIOS)
    return (id(getattr(doc, "_comentarios_base", None)), bruto if isinstance(bruto, str) else "",
            doc.revision())


# -- ancoras ------------------------------------------------------------------------------

def _varrer(doc: QTextDocument, inicio: int = 0, fim: int | None = None) -> list:
    """As ancoras entre as posicoes `inicio` e `fim` (o documento todo, sem limites)."""
    saida: list = []
    bloco = doc.findBlock(inicio) if inicio else doc.begin()
    while bloco.isValid():
        if fim is not None and bloco.position() > fim:
            break
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and marcas.eh_marcador(frag.charFormat()):
                m = marcas.marca_de(frag.charFormat())
                if isinstance(m, MarcaComentario):
                    saida.extend((frag.position() + i, m) for i, c in enumerate(frag.text())
                                 if c == CARACTERE_OBJETO and inicio <= frag.position() + i
                                 and (fim is None or frag.position() + i < fim))
            it += 1
        bloco = bloco.next()
    return saida


def _mudou(doc: QTextDocument, pos: int, removidos: int, adicionados: int) -> None:
    """Acompanha a mudanca sem varrer o documento todo (a cada tecla): as ancoras depois do
    trecho andam; ancora apagada, ou um trecho novo grande, refaz tudo na proxima consulta."""
    cache = getattr(doc, "_ancoras_cache", None)
    if cache is None:
        return
    lista = cache[1]
    if any(pos <= p < pos + removidos for p, _m in lista) or adicionados > 100_000:
        doc._ancoras_cache = None
        return
    delta = adicionados - removidos
    novas = [(p + delta if p >= pos + removidos else p, m) for p, m in lista]
    if adicionados:
        novas += _varrer(doc, pos, pos + adicionados)
        novas.sort(key=lambda x: x[0])
    doc._ancoras_cache = ((doc.revision(), doc.characterCount()), novas)


def ancoras(doc: QTextDocument, fresco: bool = False) -> list[tuple[int, MarcaComentario]]:
    """(posicao, marca) de cada ancora de comentario, na ordem do texto.

    Em cache pela revisao e pelo tamanho do documento, acompanhado pelo `contentsChange` (sem
    varrer o documento a cada tecla: medido, 10 ms por varredura em 3000 paragrafos). Medido no
    Qt 6.11.2: dentro de um bloco de edicao aberto a revisao nao muda a cada passo e o sinal so'
    vem no fim; quem edita no meio do bloco pede `fresco=True` (senao apagaria a ancora pela
    posicao velha)."""
    if not getattr(doc, "_ancoras_ligado", False):
        doc._ancoras_ligado = True
        doc.contentsChange.connect(lambda p, r, a, d=doc: _mudou(d, p, r, a))
    chave = (doc.revision(), doc.characterCount())
    cache = getattr(doc, "_ancoras_cache", None)
    if not fresco and cache is not None and cache[0] == chave:
        return cache[1]
    saida = _varrer(doc)
    doc._ancoras_cache = (chave, saida)
    return saida


def posicoes(doc: QTextDocument, fresco: bool = False) -> dict[int, dict[str, int]]:
    """id -> {"inicio": pos, "fim": pos, "referencia": pos} (a primeira de cada tipo)."""
    saida: dict = {}
    for pos, m in ancoras(doc, fresco):
        saida.setdefault(m.id, {}).setdefault(m.tipo, pos)
    return saida


def trecho(doc: QTextDocument, ident: int) -> tuple[int, int] | None:
    """(inicio, fim) do texto comentado: depois da marca de inicio e antes da de fim. Sem as
    duas, o ponto da referencia (trecho vazio). None se o comentario nao esta' no texto."""
    p = posicoes(doc).get(ident)
    if not p:
        return None
    if "inicio" in p and "fim" in p and p["inicio"] < p["fim"]:
        return p["inicio"] + 1, p["fim"]
    if "referencia" in p:
        return p["referencia"], p["referencia"]
    return None


def ordem_no_texto(doc: QTextDocument, cat: Comentarios) -> list[int]:
    """Os ids dos comentarios ancorados, pela posicao no texto (o inicio, ou a referencia)."""
    p = posicoes(doc)
    ancorados = [c.id for c in cat.itens if c.id in p and "referencia" in p[c.id]]
    return sorted(ancorados, key=lambda i: (p[i].get("inicio", p[i]["referencia"]),
                                            cat.ids().index(i)))


def no_cursor(doc: QTextDocument, cat: Comentarios, pos: int) -> int | None:
    """O comentario do trecho onde esta' o cursor (o mais interno), ou o da referencia vizinha."""
    melhor = None
    for ident, p in posicoes(doc).items():
        if cat.obter(ident) is None:
            continue
        if "inicio" in p and "fim" in p and p["inicio"] < pos <= p["fim"]:
            if melhor is None or p["inicio"] > melhor[0]:
                melhor = (p["inicio"], ident)
    if melhor is not None:
        return melhor[1]
    for ident, p in posicoes(doc).items():
        if cat.obter(ident) is not None and p.get("referencia") in (pos, pos - 1):
            return ident
    return None


# -- realce ---------------------------------------------------------------------------------

def selecoes_de_realce(doc: QTextDocument, ativo: int | None = None) -> list:
    """Selecoes (QAbstractTextDocumentLayout.Selection) com o fundo dos trechos comentados."""
    from PySide6.QtGui import QAbstractTextDocumentLayout
    cat = catalogo(doc)
    if not cat.itens:
        return []
    saida = []
    for ident, p in posicoes(doc).items():
        c = cat.obter(ident)
        if c is None or "inicio" not in p or "fim" not in p or p["fim"] <= p["inicio"] + 1:
            continue
        cursor = QTextCursor(doc)
        cursor.setPosition(p["inicio"] + 1)
        cursor.setPosition(p["fim"], QTextCursor.MoveMode.KeepAnchor)
        sel = QAbstractTextDocumentLayout.Selection()
        sel.cursor = cursor
        fmt = QTextCharFormat()
        cor = COR_REALCE_ATIVO if ident == ativo else (
            COR_REALCE_RESOLVIDO if _resolvido(cat, c) else COR_REALCE)
        fmt.setBackground(cor)
        sel.format = fmt
        saida.append(sel)
    return saida


def _resolvido(cat: Comentarios, c: Comentario) -> bool:
    raiz = cat.obter(cat.raiz(c.id))
    return c.resolvido or (raiz is not None and raiz.resolvido)
