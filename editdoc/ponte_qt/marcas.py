"""Marcas de campo e de marcador no QTextDocument (0.1.3).

Cada marca e' o caractere de objeto (U+FFFC) com um tipo de objeto proprio e a marca do
modelo em JSON numa propriedade de usuario:

- inicio e fim de campo (TIPO_MARCA_CAMPO): o resultado do campo e' o texto comum entre as
  duas, editavel. Na tela, um colchete fino e cinza em cada ponta mostra onde o campo
  comeca e termina (nao sai na impressao nem no PDF);
- inicio e fim de controle de conteudo (0.1.5, `MarcaConteudo`): o mesmo colchete do campo,
  em azul-acinzentado; o sdtPr vai no JSON (base64);
- inicio e fim de marcador (TIPO_MARCADOR): sem largura e sem pintura, como no Word com os
  marcadores ocultos. O painel pula essas marcas nas setas, no Backspace e no Delete, para
  que o usuario nao as apague sem ver;
- ancoras de comentario (0.1.6, `MarcaComentario`: inicio, fim e referencia): o mesmo objeto
  sem largura do marcador (e o mesmo pulo no teclado). O trecho comentado e' realcado pela
  pintura da folha na tela (`ponte_qt/comentarios.py`), nunca na impressao.

O HTML do Qt nao leva o objeto de tipo proprio (medido no 6.11 com os objetos opacos):
copiar e colar leva o texto do resultado, sem as marcas. O manipulador herda de
QPyTextObject (ver a armadilha em `campos.py`).
"""

from __future__ import annotations

import base64
import contextlib
import json

from PySide6.QtCore import QPointF, QSizeF
from PySide6.QtGui import (QColor, QFontMetricsF, QPen, QPyTextObject, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextFormat)

from editdoc import log_interno
from editdoc.modelo.documento import (CARACTERE_OBJETO, Campo, MarcaCampo, MarcaComentario,
                                      MarcaConteudo, Marcador)
from editdoc.ponte_qt.campos import fonte_de

log = log_interno.obter(__name__)

TIPO_MARCA_CAMPO = QTextFormat.ObjectTypes.UserObject.value + 3
TIPO_MARCADOR = QTextFormat.ObjectTypes.UserObject.value + 4
#: Formato da marca: a marca do modelo em JSON. Numero livre (ver CLAUDE.md).
PROP_MARCA = QTextFormat.Property.UserProperty.value + 22
#: Propriedades que nao podem passar para o texto digitado depois da marca.
PROPS_DE_MARCA = (QTextFormat.Property.ObjectType, PROP_MARCA)
#: Campo dentro de campo, no JSON: o mesmo limite do leitor.
_PROFUNDIDADE = 8

_impressao = {"ativa": False}


@contextlib.contextmanager
def sem_pintar_marcas():
    """Durante a impressao e o PDF os colchetes dos campos nao sao pintados."""
    anterior = _impressao["ativa"]
    _impressao["ativa"] = True
    try:
        yield
    finally:
        _impressao["ativa"] = anterior


# -- JSON ------------------------------------------------------------------------------

def _campo_para_dict(campo: Campo) -> dict:
    return {"codigo": [x if isinstance(x, str) else _campo_para_dict(x) for x in campo.codigo],
            "sujo": campo.sujo, "travado": campo.travado, "sem_resultado": campo.sem_resultado,
            "resultado": campo.resultado,
            "extra": base64.b64encode(campo.extra).decode("ascii") if campo.extra else "",
            "rpr_codigo": campo.rpr_codigo, "rpr_separador": campo.rpr_separador}


def _campo_de_dict(dado, nivel: int = 0) -> Campo | None:
    if not isinstance(dado, dict) or nivel > _PROFUNDIDADE:
        return None
    codigo = []
    for x in dado.get("codigo") or []:
        if isinstance(x, str):
            codigo.append(x)
        else:
            dentro = _campo_de_dict(x, nivel + 1)
            if dentro is None:
                return None
            codigo.append(dentro)
    try:
        extra = base64.b64decode(dado.get("extra") or "", validate=True)
    except (ValueError, TypeError):
        extra = b""
    resultado = dado.get("resultado")
    rpr_codigo, rpr_separador = dado.get("rpr_codigo"), dado.get("rpr_separador")
    return Campo(codigo=tuple(codigo), sujo=dado.get("sujo") is True,
                 travado=dado.get("travado") is True,
                 sem_resultado=dado.get("sem_resultado") is True,
                 resultado=resultado if isinstance(resultado, str) else "", extra=extra,
                 rpr_codigo=rpr_codigo if isinstance(rpr_codigo, str) and rpr_codigo else None,
                 rpr_separador=rpr_separador if isinstance(rpr_separador, str) and rpr_separador
                 else None)


def json_da_marca(marca) -> str:
    if isinstance(marca, MarcaComentario):
        return json.dumps({"comentario": marca.tipo, "id": int(marca.id)})
    if isinstance(marca, Marcador):
        return json.dumps({"marcador": marca.tipo, "nome": marca.nome}, ensure_ascii=False)
    if isinstance(marca, MarcaConteudo):
        return json.dumps({"conteudo": marca.tipo, "bloco": marca.bloco, "par": marca.par,
                           "props": base64.b64encode(marca.propriedades).decode("ascii")})
    dado = {"campo": marca.tipo, "par": marca.par}
    if marca.campo is not None:
        dado["codigo"] = _campo_para_dict(marca.campo)
    return json.dumps(dado, ensure_ascii=False)


def marca_de_json(texto):
    try:
        dado = json.loads(str(texto))
    except (TypeError, ValueError):
        return None
    if not isinstance(dado, dict):
        return None
    if dado.get("comentario") in ("inicio", "fim", "referencia"):
        ident = dado.get("id")
        if isinstance(ident, int) and not isinstance(ident, bool):
            return MarcaComentario(dado["comentario"], ident)
        return None
    if dado.get("marcador") in ("inicio", "fim") and isinstance(dado.get("nome"), str) \
            and dado["nome"]:
        return Marcador(dado["marcador"], dado["nome"])
    par = dado.get("par") if isinstance(dado.get("par"), int) else 0
    if dado.get("conteudo") in ("inicio", "fim"):
        try:
            props = base64.b64decode(dado.get("props") or "", validate=True)
        except (ValueError, TypeError):
            return None
        return MarcaConteudo(dado["conteudo"], props if dado["conteudo"] == "inicio" else b"",
                             dado.get("bloco") is True, par)
    if dado.get("campo") == "fim":
        return MarcaCampo("fim", par=par)
    if dado.get("campo") == "inicio":
        campo = _campo_de_dict(dado.get("codigo"))
        return MarcaCampo("inicio", campo, par) if campo is not None else None
    return None


# -- formato ---------------------------------------------------------------------------

def eh_marca(fmt: QTextFormat) -> bool:
    return fmt.objectType() in (TIPO_MARCA_CAMPO, TIPO_MARCADOR)


def eh_marcador(fmt: QTextFormat) -> bool:
    return fmt.objectType() == TIPO_MARCADOR


def marca_de(fmt: QTextFormat):
    if not eh_marca(fmt):
        return None
    return marca_de_json(fmt.property(PROP_MARCA))


def formato_de_marca(base: QTextCharFormat, marca) -> QTextCharFormat:
    cf = QTextCharFormat(base)
    for prop in (QTextFormat.Property.ImageName, QTextFormat.Property.ImageWidth,
                 QTextFormat.Property.ImageHeight, QTextFormat.Property.TextToolTip):
        cf.clearProperty(prop)
    cf.setObjectType(TIPO_MARCADOR if isinstance(marca, (Marcador, MarcaComentario))
                     else TIPO_MARCA_CAMPO)
    cf.setProperty(PROP_MARCA, json_da_marca(marca))
    return cf


def inserir(cursor: QTextCursor, marca, base: QTextCharFormat | None = None) -> None:
    cursor.insertText(CARACTERE_OBJETO, formato_de_marca(base or QTextCharFormat(), marca))


def posicoes_de_marcadores(doc: QTextDocument, nome: str | None = None) -> list[tuple[int, Marcador]]:
    """(posicao, marcador) de cada marca de marcador do documento (de um nome, se dado)."""
    saida = []
    bloco = doc.begin()
    while bloco.isValid():
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and eh_marcador(frag.charFormat()):
                m = marca_de(frag.charFormat())
                if isinstance(m, Marcador) and (nome is None or m.nome == nome):
                    saida.extend((frag.position() + i, m) for i, c in enumerate(frag.text())
                                 if c == CARACTERE_OBJETO)
            it += 1
        bloco = bloco.next()
    return saida


def nomes_de_marcadores(doc: QTextDocument) -> list[str]:
    nomes: list[str] = []
    for _pos, m in posicoes_de_marcadores(doc):
        if m.tipo == "inicio" and m.nome not in nomes:
            nomes.append(m.nome)
    return nomes


# -- pintura ---------------------------------------------------------------------------

class ManipuladorDeMarca(QPyTextObject):
    """Tamanho e pintura das marcas. Erro aqui nao pode derrubar a pintura: vira log."""

    def intrinsicSize(self, doc, pos, fmt) -> QSizeF:  # noqa: N802 - nome do Qt
        try:
            if fmt.objectType() == TIPO_MARCADOR:
                return QSizeF(0.0, 0.0)
            metrica = QFontMetricsF(fonte_de(doc, fmt))
            return QSizeF(max(metrica.height() * 0.22, 1.0), max(metrica.ascent(), 1.0))
        except Exception:  # noqa: BLE001 - chamado pelo Qt no meio do layout
            log.exception("tamanho da marca")
            return QSizeF(1.0, 1.0)

    def drawObject(self, painter, rect, doc, pos, fmt) -> None:  # noqa: N802 - nome do Qt
        try:
            if fmt.objectType() == TIPO_MARCADOR or _impressao["ativa"]:
                return
            marca = marca_de(fmt)
            if marca is None:
                return
            painter.save()
            caneta = QPen(QColor(0x6f, 0x8f, 0xb5) if isinstance(marca, MarcaConteudo)
                          else QColor(0x9a, 0xa3, 0xad))
            caneta.setWidthF(max(rect.width() * 0.18, 1.0))
            painter.setPen(caneta)
            topo, base = rect.top() + rect.height() * 0.05, rect.bottom() + rect.height() * 0.15
            perna = rect.width() * 0.6
            if marca.tipo == "inicio":
                x = rect.left() + rect.width() * 0.3
                pontos = [QPointF(x + perna, topo), QPointF(x, topo), QPointF(x, base),
                          QPointF(x + perna, base)]
            else:
                x = rect.right() - rect.width() * 0.3
                pontos = [QPointF(x - perna, topo), QPointF(x, topo), QPointF(x, base),
                          QPointF(x - perna, base)]
            for a, b in zip(pontos, pontos[1:]):
                painter.drawLine(a, b)
            painter.restore()
        except Exception:  # noqa: BLE001 - chamado pelo Qt no meio da pintura
            log.exception("pintura da marca")


def registrar_manipulador(doc: QTextDocument) -> ManipuladorDeMarca:
    """Registra o manipulador das duas marcas. Quem chama guarda a referencia."""
    manipulador = ManipuladorDeMarca(doc)
    doc.documentLayout().registerHandler(TIPO_MARCA_CAMPO, manipulador)
    doc.documentLayout().registerHandler(TIPO_MARCADOR, manipulador)
    return manipulador
