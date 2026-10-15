"""Notas de rodape e de fim no QTextDocument (0.1.10): marcas, catalogo e numero.

- A referencia no corpo e o numero da propria nota (w:footnoteRef, dentro do documento da
  nota) sao o caractere de objeto (U+FFFC) com um tipo proprio (TIPO_NOTA, UserObject + 5) e a
  `MarcaNota` em JSON (PROP_NOTA). O manipulador pinta o numero sobrescrito, calculado na hora:
  o mapa de numeros fica no documento do corpo (`_numeros_notas`, refeito pelo plano das notas,
  `interface/notas.py`); no documento da nota, o numero e' o da propria nota
  (`_numero_da_nota`). Mudar o numero refaz so' o layout das marcas (`markContentsDirty`): nao
  entra no desfazer nem marca o documento como alterado.
- O catalogo (`modelo/notas.py`) fica como o dos comentarios: o do arquivo num atributo do
  documento (`_notas_base`, com os bytes de origem) e o vigente no formato do quadro raiz
  (PROP_NOTAS, UserProperty + 32): chaves de um registro deste modulo (cada `Nota` e'
  imutavel; editar cria outra) e as propriedades. Entra no desfazer com o bloco de edicao.
- O espacador de pagina (PROP_QUEBRA_NOTA, UserProperty + 33): o bloco que a area das notas
  empurrou para a pagina seguinte tem PageBreak_AlwaysBefore com esta marca. Nao e' quebra do
  usuario: nao volta ao arquivo (`de_qt`), nao aparece como "Quebra de pagina", nao passa ao
  Enter nem ao copiar.
"""

from __future__ import annotations

import json
import uuid

from PySide6.QtCore import QPointF, QSizeF
from PySide6.QtGui import (QColor, QFontMetricsF, QPyTextObject, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextFormat)

from editdoc import log_interno
from editdoc.modelo.documento import CARACTERE_OBJETO, MarcaNota
from editdoc.modelo.notas import (TIPOS, Nota, Notas, PropriedadesNota, numeros,
                                  texto_do_simbolo)
from editdoc.ponte_qt.campos import fonte_de

log = log_interno.obter(__name__)

TIPO_NOTA = QTextFormat.ObjectTypes.UserObject.value + 5
_USUARIO = QTextFormat.Property.UserProperty.value
#: Caractere: a MarcaNota em JSON.
PROP_NOTA = _USUARIO + 31
#: Quadro raiz: as chaves das notas vigentes e as propriedades, em JSON.
PROP_NOTAS = _USUARIO + 32
#: Bloco (ou tabela): espacador da area das notas (ver o topo do modulo).
PROP_QUEBRA_NOTA = _USUARIO + 33
#: Celula (0.1.12): a linha da tabela tem acolchoamento de baixo a mais para a linha seguinte
#: descer para a pagina seguinte, numa secao mais baixa que a pagina do documento: "original;extra"
#: em px96. Nao e' do usuario (o de_qt nao le o acolchoamento).
PROP_LINHA_EMPURRADA = _USUARIO + 39
#: Propriedades que nao podem passar para o texto digitado depois da marca.
PROPS_DE_NOTA = (QTextFormat.Property.ObjectType, PROP_NOTA)
#: O numero sobrescrito ocupa esta fracao do corpo da letra.
ESCALA_SOBRESCRITO = 0.65

_REGISTRO: dict[str, Nota] = {}
_CHAVES: dict[int, str] = {}


def chave(n: Nota) -> str:
    k = _CHAVES.get(id(n))
    if k is None or _REGISTRO.get(k) is not n:
        k = uuid.uuid4().hex
        _REGISTRO[k] = n
        _CHAVES[id(n)] = k
    return k


def nota_da_chave(k: str) -> Nota | None:
    return _REGISTRO.get(k)


# -- marca -------------------------------------------------------------------------------

def json_da_marca(m: MarcaNota) -> str:
    return json.dumps({"nota": m.tipo, "id": int(m.id), "propria": m.propria,
                       "personalizada": m.personalizada, "simbolo": m.simbolo or ""},
                      ensure_ascii=False)


def marca_de_json(texto) -> MarcaNota | None:
    try:
        dado = json.loads(str(texto))
    except (TypeError, ValueError):
        return None
    if not isinstance(dado, dict) or dado.get("nota") not in TIPOS:
        return None
    ident = dado.get("id")
    if not isinstance(ident, int) or isinstance(ident, bool):
        return None
    simbolo = dado.get("simbolo")
    return MarcaNota(dado["nota"], ident, dado.get("propria") is True,
                     dado.get("personalizada") is True,
                     simbolo if isinstance(simbolo, str) and simbolo else None)


def eh_nota(fmt: QTextFormat) -> bool:
    return fmt.objectType() == TIPO_NOTA


def marca_de(fmt: QTextFormat) -> MarcaNota | None:
    if not eh_nota(fmt):
        return None
    return marca_de_json(fmt.property(PROP_NOTA))


def formato_de_marca(base: QTextCharFormat, m: MarcaNota) -> QTextCharFormat:
    cf = QTextCharFormat(base)
    for prop in (QTextFormat.Property.ImageName, QTextFormat.Property.ImageWidth,
                 QTextFormat.Property.ImageHeight, QTextFormat.Property.TextToolTip):
        cf.clearProperty(prop)
    cf.setObjectType(TIPO_NOTA)
    cf.setProperty(PROP_NOTA, json_da_marca(m))
    return cf


def inserir(cursor: QTextCursor, m: MarcaNota, base: QTextCharFormat | None = None) -> None:
    cursor.insertText(CARACTERE_OBJETO, formato_de_marca(base or QTextCharFormat(), m))


def _varrer(doc: QTextDocument, inicio: int = 0, fim: int | None = None) -> list:
    saida: list = []
    bloco = doc.findBlock(inicio) if inicio else doc.begin()
    while bloco.isValid():
        if fim is not None and bloco.position() > fim:
            break
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and eh_nota(frag.charFormat()):
                m = marca_de(frag.charFormat())
                if m is not None:
                    saida.extend((frag.position() + i, m) for i, c in enumerate(frag.text())
                                 if c == CARACTERE_OBJETO and frag.position() + i >= inicio
                                 and (fim is None or frag.position() + i < fim))
            it += 1
        bloco = bloco.next()
    return saida


def _mudou(doc: QTextDocument, pos: int, removidos: int, adicionados: int) -> None:
    """Acompanha a mudanca sem varrer o documento todo a cada tecla (como as ancoras dos
    comentarios): as marcas depois do trecho andam; marca apagada ou trocada (formato no trecho
    dela) ou trecho novo grande refaz tudo na proxima consulta."""
    cache = getattr(doc, "_marcas_notas_cache", None)
    if cache is None:
        return
    lista = cache[1]
    if any(pos <= p < pos + max(removidos, 1) for p, _m in lista) or adicionados > 100_000:
        doc._marcas_notas_cache = None
        return
    delta = adicionados - removidos
    novas = [(p + delta if p >= pos + removidos else p, m) for p, m in lista]
    if adicionados:
        novas += _varrer(doc, pos, pos + adicionados)
        novas.sort(key=lambda x: x[0])
    doc._marcas_notas_cache = ((doc.revision(), doc.characterCount()), novas)


def marcas(doc: QTextDocument) -> list[tuple[int, MarcaNota]]:
    """(posicao, marca) de cada marca de nota do documento (referencias e numeros proprios), em
    cache pela revisao e pelo tamanho e acompanhado pelo `contentsChange` (medido: varrer 300
    paragrafos a cada tecla custava 3 ms). Dentro de um bloco de edicao aberto a revisao nao
    muda: quem edita ali pede `fresco=True`."""
    if not getattr(doc, "_marcas_notas_ligado", False):
        doc._marcas_notas_ligado = True
        doc.contentsChange.connect(lambda p, r, a, d=doc: _mudou(d, p, r, a))
    chave_cache = (doc.revision(), doc.characterCount())
    cache = getattr(doc, "_marcas_notas_cache", None)
    if cache is not None and cache[0] == chave_cache:
        return cache[1]
    saida = _varrer(doc)
    doc._marcas_notas_cache = (chave_cache, saida)
    return saida


def referencias(doc: QTextDocument) -> list[tuple[int, MarcaNota]]:
    """So' as referencias (no corpo), na ordem do texto."""
    return [(p, m) for p, m in marcas(doc) if not m.propria]


# -- catalogo ----------------------------------------------------------------------------

def definir_base(doc: QTextDocument, cat: Notas | None) -> None:
    """O catalogo ao abrir. Nao entra no desfazer: tira a propriedade do quadro raiz."""
    doc._notas_base = cat
    doc._notas_cache = None
    doc._numeros_notas = {}
    quadro = doc.rootFrame()
    ff = quadro.frameFormat()
    if ff.hasProperty(PROP_NOTAS):
        ff.clearProperty(PROP_NOTAS)
        quadro.setFrameFormat(ff)
    if cat is not None:
        doc._numeros_notas = numeros_continuos(doc, cat)


def _pr_para_dict(pr: PropriedadesNota | None):
    if pr is None:
        return None
    return {"formato": pr.formato, "inicio": pr.inicio, "reinicio": pr.reinicio,
            "posicao": pr.posicao}


def _pr_de_dict(dado) -> PropriedadesNota | None:
    if not isinstance(dado, dict):
        return None
    inicio = dado.get("inicio")
    texto = lambda k: dado.get(k) if isinstance(dado.get(k), str) else None  # noqa: E731
    return PropriedadesNota(texto("formato"),
                            inicio if isinstance(inicio, int) and not isinstance(inicio, bool)
                            else None, texto("reinicio"), texto("posicao"))


def catalogo(doc: QTextDocument) -> Notas:
    """O catalogo vigente (vazio se o documento nao tem notas)."""
    base = getattr(doc, "_notas_base", None)
    bruto = doc.rootFrame().frameFormat().property(PROP_NOTAS)
    if not isinstance(bruto, str) or not bruto:
        return base if base is not None else Notas()
    cache = getattr(doc, "_notas_cache", None)
    if cache is not None and cache[0] == bruto and cache[1] is base:
        return cache[2]
    try:
        dado = json.loads(bruto)
    except ValueError:
        dado = {}
    itens = {}
    for tipo in TIPOS:
        chaves = dado.get(tipo) or []
        itens[tipo] = [_REGISTRO[k] for k in chaves if isinstance(k, str) and k in _REGISTRO]
    cat = (base if base is not None else Notas()).com_itens(itens)
    pr = dado.get("secao")
    if isinstance(pr, dict):
        cat.secao = {t: p for t in TIPOS if (p := _pr_de_dict(pr.get(t))) is not None}
    doc._notas_cache = (bruto, base, cat)
    return cat


def trocar(doc: QTextDocument, itens: dict, secao: dict | None = None) -> None:
    """Grava o catalogo novo no quadro raiz. Dentro de um beginEditBlock, fica no mesmo passo."""
    if secao is None:
        secao = catalogo(doc).secao
    dado = {t: [chave(n) for n in itens.get(t, [])] for t in TIPOS}
    dado["secao"] = {t: _pr_para_dict(p) for t, p in secao.items() if p is not None}
    quadro = doc.rootFrame()
    ff = quadro.frameFormat()
    ff.setProperty(PROP_NOTAS, json.dumps(dado))
    quadro.setFrameFormat(ff)


def assinatura(doc: QTextDocument) -> tuple:
    bruto = doc.rootFrame().frameFormat().property(PROP_NOTAS)
    return (id(getattr(doc, "_notas_base", None)), bruto if isinstance(bruto, str) else "")


def numeros_continuos(doc: QTextDocument, cat: Notas | None = None) -> dict:
    """Os numeros sem saber a pagina (reinicio por pagina vira continuo): o comeco, antes do
    primeiro plano."""
    cat = cat if cat is not None else catalogo(doc)
    refs = [(m.tipo, m.id, m.personalizada) for _p, m in referencias(doc)]
    return numeros(refs, {t: cat.propriedades(t) for t in TIPOS})


def texto_da_marca(doc: QTextDocument, m: MarcaNota) -> str:
    if m.personalizada:
        return texto_do_simbolo(m.simbolo) if m.simbolo else ""
    if m.propria:
        return getattr(doc, "_numero_da_nota", "") or ""
    return (getattr(doc, "_numeros_notas", None) or {}).get((m.tipo, m.id), "")


# -- manipulador -------------------------------------------------------------------------

_TAMANHOS: dict[tuple, tuple] = {}


def _fonte_e_altura(doc, fmt):
    fonte = fonte_de(doc, fmt)
    metrica_cheia = QFontMetricsF(fonte)
    sobrescrito = fmt.toCharFormat().verticalAlignment() == \
        QTextCharFormat.VerticalAlignment.AlignSuperScript
    if sobrescrito:
        fonte.setPixelSize(max(1, round(fonte.pixelSize() * ESCALA_SOBRESCRITO)))
    return fonte, metrica_cheia.ascent(), sobrescrito


class ManipuladorDeNota(QPyTextObject):
    """Tamanho e pintura das marcas de nota. Erro aqui nao derruba a pintura: vira log."""

    def intrinsicSize(self, doc, pos, fmt) -> QSizeF:  # noqa: N802 - nome do Qt
        try:
            m = marca_de(fmt)
            texto = texto_da_marca(doc, m) if m is not None else ""
            familias = fmt.property(QTextFormat.Property.FontFamilies)
            chave_doc = doc.chave_da_fonte() if hasattr(doc, "chave_da_fonte") \
                else doc.defaultFont().key()
            k = (chave_doc, texto, tuple(familias) if isinstance(familias, list) else familias,
                 fmt.property(QTextFormat.Property.FontPointSize),
                 fmt.property(QTextFormat.Property.FontWeight),
                 fmt.toCharFormat().verticalAlignment().value)
            tamanho = _TAMANHOS.get(k)
            if tamanho is None:
                fonte, ascent, _sob = _fonte_e_altura(doc, fmt)
                largura = QFontMetricsF(fonte).horizontalAdvance(texto) if texto else 0.0
                tamanho = (max(largura, 1.0), max(ascent, 1.0))
                if len(_TAMANHOS) > 1024:
                    _TAMANHOS.clear()
                _TAMANHOS[k] = tamanho
            return QSizeF(*tamanho)
        except Exception:  # noqa: BLE001 - chamado pelo Qt no meio do layout
            log.exception("tamanho da marca de nota")
            return QSizeF(1.0, 1.0)

    def drawObject(self, painter, rect, doc, pos, fmt) -> None:  # noqa: N802 - nome do Qt
        try:
            m = marca_de(fmt)
            if m is None:
                return
            texto = texto_da_marca(doc, m)
            if not texto:
                return
            fonte, _ascent, sobrescrito = _fonte_e_altura(doc, fmt)
            cf = fmt.toCharFormat()
            painter.save()
            painter.setFont(fonte)
            cor = cf.foreground().color() if cf.hasProperty(
                QTextFormat.Property.ForegroundBrush) else QColor(0, 0, 0)
            painter.setPen(cor)
            base = rect.top() + QFontMetricsF(fonte).ascent() if sobrescrito else rect.bottom()
            painter.drawText(QPointF(rect.left(), base), texto)
            painter.restore()
        except Exception:  # noqa: BLE001 - chamado pelo Qt no meio da pintura
            log.exception("pintura da marca de nota")


def registrar_manipulador(doc: QTextDocument) -> ManipuladorDeNota:
    manipulador = ManipuladorDeNota(doc)
    doc.documentLayout().registerHandler(TIPO_NOTA, manipulador)
    return manipulador


def refazer_marcas(doc: QTextDocument) -> None:
    """O numero mudou: mede de novo as marcas (sem desfazer, sem "alterado")."""
    for pos, _m in marcas(doc):
        doc.markContentsDirty(pos, 1)


# -- espacador ---------------------------------------------------------------------------

def eh_espacador(fmt: QTextFormat) -> bool:
    return bool(fmt.property(PROP_QUEBRA_NOTA))


def sem_espacador(fmt):
    """Copia do formato de bloco (ou de tabela) sem o espacador."""
    novo = type(fmt)(fmt)
    if novo.property(PROP_QUEBRA_NOTA):
        novo.clearProperty(PROP_QUEBRA_NOTA)
        # A quebra derivada da secao (0.1.12) fica: so' a do espacador sai.
        from editdoc.ponte_qt.secoes import PROP_QUEBRA_SECAO
        bits = novo.property(PROP_QUEBRA_SECAO)
        bits = bits if isinstance(bits, int) and not isinstance(bits, bool) else 0
        politica = QTextFormat.PageBreakFlag.PageBreak_Auto
        if bits & 1:
            politica |= QTextFormat.PageBreakFlag.PageBreak_AlwaysAfter
        if bits & 2:
            politica |= QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore
        novo.setPageBreakPolicy(politica)
    return novo
