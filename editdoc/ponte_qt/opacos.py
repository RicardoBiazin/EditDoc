"""Objetos opacos no QTextDocument (0.1.2): um marcador no lugar, que nao se edita.

O objeto (caixa de texto, forma, grafico, SmartArt, objeto OLE, imagem flutuante,
equacao) e' o caractere de objeto (U+FFFC) com um formato de objeto proprio
(TIPO_OPACO) e a chave do registro numa propriedade de usuario. O XML e as partes ficam
no registro, nunca no Qt: o desfazer devolve o formato com a chave, e a chave acha o
objeto de novo. E' o mesmo arranjo das imagens (`imagens.py`).

Na tela: o objeto na linha (com wp:extent) vira um quadro do tamanho dele, com o rotulo,
o comeco do texto da caixa e a previa, quando ha' uma imagem que o Qt le. O flutuante e
a equacao viram uma etiqueta do tamanho do texto no ponto da ancora. Apagar remove o
objeto inteiro, como um caractere; digitar nao entra nele.

Copiar e colar: o HTML que o Qt gera nao leva o objeto (medido no Qt 6.11: o caractere
some do HTML), entao o que se cola sai sem ele. Nada de lixo no texto.

O manipulador herda de QPyTextObject (ver a armadilha em `campos.py`).
"""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPen, QPyTextObject,
                           QTextCharFormat, QTextCursor, QTextDocument, QTextFormat)

from editdoc import log_interno
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.documento import CARACTERE_OBJETO, ROTULOS_OPACOS, ObjetoOpaco
from editdoc.modelo.unidades import EMU_POR_TWIP

log = log_interno.obter(__name__)

#: Tipo de objeto do Qt (o campo e' UserObject + 1).
TIPO_OPACO = QTextFormat.ObjectTypes.UserObject.value + 2
#: Chave do objeto no registro. Longe das outras propriedades de usuario (+1 a +7).
PROP_OPACO = QTextFormat.Property.UserProperty.value + 20
#: Propriedades que nao podem passar para o texto digitado depois do objeto.
PROPS_DE_OPACO = (QTextFormat.Property.ObjectType, PROP_OPACO, QTextFormat.Property.TextToolTip)
#: Largura padrao do corpo (A4, margens Normal), para documento sem largura.
_CORPO_PADRAO_TW = 9026
_ALTURA_MAXIMA_TW = 20000
_TWIPS_POR_PONTO = 20

#: chave -> objeto. Sem limpeza: o desfazer pode trazer qualquer chave de volta.
_REGISTRO: dict[str, ObjetoOpaco] = {}
_PREVIAS: dict[str, QImage] = {}


def chave_de(obj: ObjetoOpaco) -> str:
    h = hashlib.sha256(obj.xml)
    for parte in obj.partes:
        h.update(parte.nome.encode())
        h.update(hashlib.sha256(parte.dados).digest())
    h.update(repr(obj.relacoes).encode())
    return "opaco:" + h.hexdigest()[:40]


def registrar(obj: ObjetoOpaco) -> str:
    chave = chave_de(obj)
    _REGISTRO.setdefault(chave, obj)
    return chave


def eh_opaco(fmt: QTextFormat) -> bool:
    return fmt.objectType() == TIPO_OPACO


def objeto_de(fmt: QTextFormat) -> ObjetoOpaco | None:
    chave = fmt.property(PROP_OPACO)
    return _REGISTRO.get(chave) if isinstance(chave, str) else None


def formato_de_opaco(base: QTextCharFormat, obj: ObjetoOpaco) -> QTextCharFormat:
    """O formato do objeto: a fonte de `base` (para a etiqueta) mais o tipo e a chave."""
    cf = QTextCharFormat(base)
    for prop in (QTextFormat.Property.ImageName, QTextFormat.Property.ImageWidth,
                 QTextFormat.Property.ImageHeight, QTextFormat.Property.TextToolTip):
        cf.clearProperty(prop)
    cf.setObjectType(TIPO_OPACO)
    cf.setProperty(PROP_OPACO, registrar(obj))
    rotulo = ROTULOS_OPACOS.get(obj.tipo, "Objeto")
    cf.setToolTip(f"{rotulo}: preservado, mas não editável nesta versão")
    return cf


def inserir(cursor: QTextCursor, obj: ObjetoOpaco, base: QTextCharFormat | None = None) -> None:
    cursor.insertText(CARACTERE_OBJETO, formato_de_opaco(base or QTextCharFormat(), obj))


def texto_do_rotulo(obj: ObjetoOpaco) -> str:
    rotulo = ROTULOS_OPACOS.get(obj.tipo, "Objeto")
    if obj.tipo == "imagem" and obj.flutuante:
        rotulo = "Imagem flutuante"
    return f"{rotulo}: {obj.resumo}" if obj.resumo else rotulo


def posicoes_de_opacos(doc: QTextDocument, limite: int = 100000) -> list[int]:
    """Posicoes dos objetos opacos do documento, inclusive dentro de tabela."""
    saida: list[int] = []
    bloco = doc.begin()
    while bloco.isValid() and len(saida) < limite:
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and eh_opaco(frag.charFormat()):
                inicio = frag.position()
                saida.extend(inicio + i for i, c in enumerate(frag.text()) if c == CARACTERE_OBJETO)
            it += 1
        bloco = bloco.next()
    return saida


def _previa(chave: str, obj: ObjetoOpaco) -> QImage | None:
    if obj.previa is None:
        return None
    if chave not in _PREVIAS:
        if len(_PREVIAS) > 64:
            _PREVIAS.clear()
        from editdoc.ponte_qt.imagens import previa  # import tardio: imagens importa este
        _PREVIAS[chave] = previa(obj.previa) if mod_imagem.formato_de(obj.previa) else QImage()
    img = _PREVIAS[chave]
    return None if img.isNull() else img


def _fonte(doc: QTextDocument, fmt: QTextFormat) -> QFont:
    """Fonte da etiqueta em pixels de layout (twips), um pouco menor que a do texto."""
    fonte = QFont(fmt.toCharFormat().font().resolve(doc.defaultFont()))
    pontos = fonte.pointSizeF()
    if pontos <= 0:
        pontos = doc.defaultFont().pointSizeF() if doc.defaultFont().pointSizeF() > 0 else 11.0
    fonte.setPixelSize(max(1, round(pontos * 0.85 * _TWIPS_POR_PONTO)))
    fonte.setBold(False)
    fonte.setItalic(False)
    fonte.setUnderline(False)
    fonte.setStrikeOut(False)
    return fonte


def _largura_disponivel(doc: QTextDocument) -> float:
    largura = doc.pageSize().width()
    if largura <= 0:
        largura = doc.textWidth()
    return largura if largura > 0 else _CORPO_PADRAO_TW


def tamanho(doc: QTextDocument, fmt: QTextFormat) -> tuple[QSizeF, bool]:
    """(tamanho em unidades de layout, e' etiqueta). Etiqueta: flutuante, equacao ou sem medida."""
    obj = objeto_de(fmt)
    metrica = QFontMetricsF(_fonte(doc, fmt))
    disponivel = max(_largura_disponivel(doc), 1.0)
    altura_linha = metrica.height()
    if obj is None:
        return QSizeF(altura_linha, altura_linha), True
    if obj.flutuante or obj.tipo == "equacao" or not obj.largura_emu or not obj.altura_emu:
        largura = metrica.horizontalAdvance(texto_do_rotulo(obj)) + altura_linha * 1.6
        if obj.previa is not None:
            largura += altura_linha * 1.3  # a miniatura vem antes do rotulo
        return QSizeF(min(largura, disponivel), altura_linha * 1.3), True
    largura = obj.largura_emu / EMU_POR_TWIP
    altura = obj.altura_emu / EMU_POR_TWIP
    if largura > disponivel:
        altura = altura * disponivel / largura
        largura = disponivel
    return QSizeF(max(largura, altura_linha * 2), min(max(altura, altura_linha * 1.3),
                                                      _ALTURA_MAXIMA_TW)), False


class ManipuladorDeOpaco(QPyTextObject):
    """Tamanho e pintura do marcador. Erro aqui nao pode derrubar a pintura: vira log."""

    def intrinsicSize(self, doc, pos, fmt) -> QSizeF:  # noqa: N802 - nome do Qt
        try:
            return tamanho(doc, fmt)[0]
        except Exception:  # noqa: BLE001 - chamado pelo Qt no meio do layout
            log.exception("tamanho do objeto opaco")
            return QSizeF(1.0, 1.0)

    def drawObject(self, painter, rect, doc, pos, fmt) -> None:  # noqa: N802 - nome do Qt
        try:
            obj = objeto_de(fmt)
            _tam, etiqueta = tamanho(doc, fmt)
            fonte = _fonte(doc, fmt)
            metrica = QFontMetricsF(fonte)
            painter.save()
            r = QRectF(rect).adjusted(metrica.height() * 0.08, metrica.height() * 0.08,
                                      -metrica.height() * 0.08, -metrica.height() * 0.08)
            caneta = QPen(QColor(0x5f, 0x6b, 0x7a))
            caneta.setStyle(Qt.PenStyle.DashLine)
            caneta.setWidthF(max(1.0, metrica.height() * 0.06))
            painter.setPen(caneta)
            painter.setBrush(QColor(0xee, 0xf1, 0xf5))
            raio = metrica.height() * 0.25
            painter.drawRoundedRect(r, raio, raio)
            texto = texto_do_rotulo(obj) if obj is not None else "Objeto"
            img = _previa(fmt.property(PROP_OPACO), obj) if obj is not None else None
            margem = metrica.height() * 0.3
            if img is not None:
                if etiqueta:
                    lado = r.height() - margem
                    alvo = QRectF(r.left() + margem * 0.5, r.top() + margem * 0.5, lado, lado)
                else:
                    alvo = r.adjusted(margem, metrica.height() + margem, -margem, -margem)
                if alvo.width() > 0 and alvo.height() > 0:
                    escala = min(alvo.width() / img.width(), alvo.height() / img.height())
                    w, h = img.width() * escala, img.height() * escala
                    painter.drawImage(QRectF(alvo.left(), alvo.top(), w, h), img)
            painter.setFont(fonte)
            painter.setPen(QColor(0x2b, 0x33, 0x3d))
            caixa_texto = r.adjusted(margem + (r.height() if etiqueta and img is not None else 0),
                                     0, -margem, 0)
            if not etiqueta:
                caixa_texto.setHeight(min(r.height(), metrica.height() * 1.4))
            elidido = metrica.elidedText(texto, Qt.TextElideMode.ElideRight, caixa_texto.width())
            painter.drawText(caixa_texto, int(Qt.AlignmentFlag.AlignVCenter
                                              | Qt.AlignmentFlag.AlignLeft), elidido)
            painter.restore()
        except Exception:  # noqa: BLE001 - chamado pelo Qt no meio da pintura
            log.exception("pintura do objeto opaco")


def registrar_manipulador(doc: QTextDocument) -> ManipuladorDeOpaco:
    """Registra o manipulador no layout do documento. Quem chama guarda a referencia."""
    manipulador = ManipuladorDeOpaco(doc)
    doc.documentLayout().registerHandler(TIPO_OPACO, manipulador)
    return manipulador
