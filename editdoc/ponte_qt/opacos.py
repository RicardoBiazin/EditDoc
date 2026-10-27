"""Objetos opacos no QTextDocument (0.1.2): um marcador no lugar, que nao se edita.

O objeto (caixa de texto, forma, grafico, SmartArt, objeto OLE, imagem flutuante,
equacao) e' o caractere de objeto (U+FFFC) com um formato de objeto proprio
(TIPO_OPACO) e a chave do registro numa propriedade de usuario. O XML e as partes ficam
no registro, nunca no Qt: o desfazer devolve o formato com a chave, e a chave acha o
objeto de novo. E' o mesmo arranjo das imagens (`imagens.py`).

Caixa de texto editavel (0.1.5): a caixa na linha aparece do tamanho do wp:extent, com o
texto de dentro composto por um QTextDocument proprio (`_documento_da_caixa`), o mesmo
catalogo de estilos e de listas do corpo.

Objeto flutuante (0.1.7, `flutuantes.py`): imagem, caixa, forma e grupo com wp:anchor (ou VML
absoluto) sao pintados na posicao da pagina, fora daqui; o caractere nao ocupa lugar no
texto, ou e' o float do Qt que reserva o espaco que o texto contorna (ObjectIndex no
formato). So' o flutuante que nao se le volta a etiqueta.

Imagem na linha em EMF, WMF, TIFF ou SVG (0.1.5): a previa renderizada por `vetoriais.py`
ocupa o lugar inteiro, como uma imagem comum (sem quadro e sem rotulo). Se a previa falha,
volta o quadro.

Na tela: o objeto na linha (com wp:extent) vira um quadro do tamanho dele, com o rotulo,
o comeco do texto da caixa e a previa, quando ha' uma imagem que o Qt le. A equacao vira
uma etiqueta do tamanho do texto. Apagar remove o objeto inteiro, como um caractere;
digitar nao entra nele.

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
from editdoc.modelo.unidades import EMU_POR_PX, EMU_POR_TWIP

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
    fmt = formato_de_opaco(base or QTextCharFormat(), obj)
    # Flutuante que empurra o texto (0.1.7): entra como float do Qt (ver flutuantes.py).
    from editdoc.ponte_qt import flutuantes
    if obj.flutuante and flutuantes.inserir_com_reserva(cursor, fmt, obj, registrar(obj)):
        return
    cursor.insertText(CARACTERE_OBJETO, fmt)


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
        if mod_imagem.formato_de(obj.previa):
            _PREVIAS[chave] = previa(obj.previa)
        else:
            # EMF, WMF, TIFF, SVG (0.1.5): renderizado so' para a tela, o PDF e a impressao.
            from editdoc.ponte_qt import vetoriais
            tamanho_doc = None
            if obj.largura_emu and obj.altura_emu:
                tamanho_doc = (obj.largura_emu / EMU_POR_PX, obj.altura_emu / EMU_POR_PX)
            _PREVIAS[chave] = vetoriais.renderizar(obj.previa, tamanho_doc=tamanho_doc)
    img = _PREVIAS[chave]
    return None if img.isNull() else img


def mostra_como_imagem(obj: ObjetoOpaco | None, chave) -> QImage | None:
    """A previa, se o objeto e' uma imagem na linha que a tela mostra inteira (0.1.5)."""
    if obj is None or obj.tipo != "imagem" or obj.flutuante or not obj.largura_emu \
            or not obj.altura_emu or not isinstance(chave, str):
        return None
    return _previa(chave, obj)


#: chave da caixa -> (documento do Qt com o texto, altura do texto em twips)
_CAIXAS: dict = {}
#: Margem interna padrao da caixa (wps:bodyPr lIns/tIns: 0,1 polegada).
_MARGEM_CAIXA_TW = 144


def _dispositivo_1440():
    from PySide6.QtGui import QImage as _QImage
    img = _QImage(1, 1, _QImage.Format.Format_ARGB32_Premultiplied)
    dpm = round(1440 / 0.0254)
    img.setDotsPerMeterX(dpm)
    img.setDotsPerMeterY(dpm)
    return img


def _documento_da_caixa(doc: QTextDocument, obj: ObjetoOpaco, chave: str, largura_tw: float):
    """O texto da caixa composto na largura dela, ou None (caixa so' de leitura, forma)."""
    if obj is None or obj.tipo != "caixa_de_texto" or not obj.largura_emu or not obj.altura_emu:
        return None
    corpo = getattr(doc, "_doc_estilos", None) or doc
    item = (chave, id(corpo), doc.defaultFont().toString(), round(largura_tw))
    if item in _CAIXAS:
        return _CAIXAS[item]
    if len(_CAIXAS) > 32:
        _CAIXAS.clear()
    from editdoc.formato_docx import caixas
    from editdoc.ponte_qt import estilos as pq_estilos
    from editdoc.ponte_qt import listas as pq_listas
    from editdoc.ponte_qt import para_qt
    from editdoc.ponte_qt.imagens import DocumentoQt
    analise = caixas.analisar(obj, pq_estilos.catalogo(corpo), pq_listas.catalogo(corpo))
    if not analise.editavel:
        _CAIXAS[item] = None
        return None
    mini = DocumentoQt()
    mini._doc_estilos = corpo
    mini._dispositivo = _dispositivo_1440()
    mini.documentLayout().setPaintDevice(mini._dispositivo)
    mini.setDocumentMargin(0)
    mini.setDefaultFont(doc.defaultFont())
    mini.setTextWidth(max(largura_tw - 2 * _MARGEM_CAIXA_TW, 200.0))
    para_qt.preencher_blocos(mini, analise.blocos)
    altura = mini.documentLayout().documentSize().height()
    _CAIXAS[item] = (mini, altura, _texto_claro(mini))
    return _CAIXAS[item]


def _texto_claro(mini: QTextDocument) -> bool:
    """Todo o texto da caixa e' claro (branco sobre uma forma escura, que a tela nao junta):
    a caixa ganha um fundo escuro, senao o texto some na folha branca."""
    visto = False
    bloco = mini.begin()
    while bloco.isValid():
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.text().strip():
                cf = frag.charFormat()
                if not cf.hasProperty(QTextFormat.Property.ForegroundBrush) or                         cf.foreground().color().lightness() < 200:
                    return False
                visto = True
            it += 1
        bloco = bloco.next()
    return visto


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
    largura = doc.pageSize().width() - float(getattr(doc, "_desvio_tw", 0.0))
    if largura <= 0:
        largura = doc.textWidth()
    return largura if largura > 0 else _CORPO_PADRAO_TW


def tamanho(doc: QTextDocument, fmt: QTextFormat) -> tuple[QSizeF, bool]:
    """(tamanho em unidades de layout, e' etiqueta). Etiqueta: flutuante, equacao ou sem medida."""
    obj = objeto_de(fmt)
    chave = fmt.property(PROP_OPACO)
    if obj is not None and obj.flutuante:
        from editdoc.ponte_qt import flutuantes
        if flutuantes.info(obj, chave if isinstance(chave, str) else None) is not None:
            # 0.1.7: o objeto e' pintado na posicao da pagina; no texto nao ocupa lugar.
            return QSizeF(0.0, 0.0), False
    metrica = QFontMetricsF(_fonte(doc, fmt))
    disponivel = max(_largura_disponivel(doc), 1.0)
    altura_linha = metrica.height()
    if obj is None:
        return QSizeF(altura_linha, altura_linha), True
    chave = fmt.property(PROP_OPACO)
    if obj.tipo == "caixa_de_texto" and obj.largura_emu and obj.altura_emu and isinstance(chave, str):
        largura = min(obj.largura_emu / EMU_POR_TWIP, disponivel)
        caixa = _documento_da_caixa(doc, obj, chave, largura)
        if caixa is not None:
            # Pelo menos o tamanho da caixa; o texto que passa dela faz a caixa crescer, como
            # o "ajustar a forma ao texto" do Word.
            altura = max(obj.altura_emu / EMU_POR_TWIP, caixa[1] + 2 * _MARGEM_CAIXA_TW * 0.5)
            return QSizeF(max(largura, altura_linha * 2), min(max(altura, altura_linha * 1.3),
                                                              _ALTURA_MAXIMA_TW)), False
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
            if fmt.objectIndex() >= 0:
                # Float do Qt (0.1.7): o tamanho e' a reserva de espaco que o texto contorna.
                from editdoc.ponte_qt import flutuantes
                return flutuantes.gerente(doc).reserva(pos, fmt)
            return tamanho(doc, fmt)[0]
        except Exception:  # noqa: BLE001 - chamado pelo Qt no meio do layout
            log.exception("tamanho do objeto opaco")
            return QSizeF(1.0, 1.0)

    def drawObject(self, painter, rect, doc, pos, fmt) -> None:  # noqa: N802 - nome do Qt
        try:
            obj = objeto_de(fmt)
            if obj is not None and obj.flutuante:
                from editdoc.ponte_qt import flutuantes
                if flutuantes.eh_flutuante(fmt):
                    return  # 0.1.7: pintado na posicao da pagina (flutuantes.desenhar_pagina)
            imagem = mostra_como_imagem(obj, fmt.property(PROP_OPACO))
            if imagem is not None:
                painter.drawImage(QRectF(rect), imagem)
                return
            if _desenhar_caixa(painter, QRectF(rect), doc, obj, fmt):
                return
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


def _desenhar_caixa(painter, rect: QRectF, doc, obj, fmt) -> bool:
    """A caixa de texto editavel: contorno fino e o texto de dentro. False se nao for."""
    chave = fmt.property(PROP_OPACO)
    if obj is None or obj.tipo != "caixa_de_texto" or not isinstance(chave, str):
        return False
    caixa = _documento_da_caixa(doc, obj, chave, rect.width())
    if caixa is None:
        return False
    mini, _altura, claro = caixa
    from PySide6.QtGui import QAbstractTextDocumentLayout
    from editdoc.ponte_qt import listas as pq_listas
    from editdoc.ponte_qt import propriedades as pq_props
    painter.save()
    caneta = QPen(QColor(0x9a, 0xa3, 0xad))
    caneta.setWidthF(10.0)
    painter.setPen(caneta)
    painter.setBrush(QColor(0x5f, 0x6b, 0x7a) if claro else Qt.BrushStyle.NoBrush)
    painter.drawRect(rect)
    painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
    painter.translate(rect.left() + _MARGEM_CAIXA_TW, rect.top() + _MARGEM_CAIXA_TW * 0.5)
    contexto = QAbstractTextDocumentLayout.PaintContext()
    contexto.cursorPosition = -1
    contexto.palette.setColor(contexto.palette.ColorRole.Text, QColor(0, 0, 0))
    mini.documentLayout().draw(painter, contexto)
    pq_listas.desenhar_rotulos(painter, mini, None)
    pq_props.desenhar(painter, mini, None)
    painter.restore()
    return True


def registrar_manipulador(doc: QTextDocument) -> ManipuladorDeOpaco:
    """Registra o manipulador no layout do documento. Quem chama guarda a referencia."""
    manipulador = ManipuladorDeOpaco(doc)
    doc.documentLayout().registerHandler(TIPO_OPACO, manipulador)
    return manipulador
