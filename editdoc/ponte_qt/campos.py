"""Campos PAGE e NUMPAGES no QTextDocument (M5): objeto na linha, pintado na hora.

O campo e' o caractere de objeto (U+FFFC) com um formato de objeto proprio
(TIPO_CAMPO) e a instrucao numa propriedade de usuario. O Qt pede o tamanho e a
pintura a um manipulador registrado no layout do documento; o manipulador calcula o
texto pela pagina, de modo que o mesmo campo mostra 1 numa pagina e 2 na outra sem
mudar o documento (nem o desfazer, nem o "alterado").

O manipulador precisa herdar de QPyTextObject. Com `class X(QObject, QTextObjectInterface)`
o PySide 6.11 aceita o registerHandler mas o `handlerForObject` devolve None, e o
campo some sem erro (medido antes de escrever isto).

Onde o campo esta':
- no cabecalho e no rodape, o documento e' pintado uma vez por pagina, e o contexto
  diz qual pagina (`indice_fixo`); antes de pintar, o layout e' refeito
  (`markContentsDirty`, que nao toca no desfazer nem marca o documento como alterado);
- no corpo, a pagina vem da posicao do objeto (`hb`, a altura do corpo), e a largura
  e' a do maior valor possivel, para nao depender do layout que esta' sendo feito.

Unidades: o layout e' em twips (1440 dpi). A fonte do campo e' a do formato, com
tamanho em pixels de layout (pt x 20).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QSizeF
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QPyTextObject, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextFormat)

from editdoc import log_interno
from editdoc.modelo.campos import valor_do_campo
from editdoc.modelo.pagina import Pagina

log = log_interno.obter(__name__)

#: Tipo de objeto do campo no Qt (QTextFormat.UserObject + 1).
TIPO_CAMPO = QTextFormat.ObjectTypes.UserObject.value + 1
_USUARIO = QTextFormat.Property.UserProperty.value
#: Formato do campo: a instrucao ("PAGE", "NUMPAGES \\* roman"...). O mesmo numero de
#: `estilos.PROP_ESTILO`, mas aquele so' vai no formato de BLOCO: no caractere nao colide.
PROP_CAMPO = _USUARIO + 4
#: Formato do campo: o ultimo resultado guardado no arquivo (volta ao .docx).
#: Ate' a 0.1.10 era + 5, o mesmo numero de `estilos.PROP_ESTILO_CAR` no formato de caractere:
#: o resultado apagava o estilo de caractere do campo e, quando o resultado ("1") era o id de
#: um estilo do documento, virava esse estilo e a conferencia recusava o arquivo (0.1.11).
PROP_CAMPO_RESULTADO = _USUARIO + 34
#: Pixels de layout (twips) por ponto.
_TWIPS_POR_PONTO = 20
#: No corpo, a largura do campo e' a do maior valor entre as primeiras paginas.
_PAGINAS_PARA_LARGURA = 300
#: Propriedades do formato do campo que nao podem passar para o texto digitado depois dele.
PROPS_DE_CAMPO = (QTextFormat.Property.ObjectType, PROP_CAMPO, PROP_CAMPO_RESULTADO)


class ContextoDeCampos:
    """O que o campo precisa saber para se pintar: pagina, total e numeracao."""

    def __init__(self) -> None:
        self.pagina = Pagina()
        self.total = 1
        #: cabecalho e rodape: a pagina que esta' sendo pintada (a partir de 0)
        self.indice_fixo: int | None = None
        #: corpo: altura de uma pagina de corpo, em twips (a pagina sai da posicao)
        self.hb: float | None = None
        #: secoes (0.1.12): folha -> (indice na secao, pagina numerada da secao, paginas da
        #: secao); None com uma secao so'
        self.secoes = None

    def valor(self, instrucao: str, indice: int) -> str:
        if self.secoes is not None:
            try:
                n, pagina, paginas = self.secoes(max(0, indice))
            except (IndexError, ValueError):
                n, pagina, paginas = max(0, indice), self.pagina, self.total
            return valor_do_campo(instrucao, n, self.total, pagina, paginas)
        return valor_do_campo(instrucao, max(0, indice), self.total, self.pagina)

    def textos_para_largura(self, instrucao: str) -> list[str]:
        if self.indice_fixo is not None:
            return [self.valor(instrucao, self.indice_fixo)]
        quantas = max(1, min(self.total, _PAGINAS_PARA_LARGURA))
        return sorted({self.valor(instrucao, i) for i in range(quantas)})


def eh_campo(fmt: QTextFormat) -> bool:
    return fmt.objectType() == TIPO_CAMPO


def formato_de_campo(base: QTextCharFormat, instrucao: str, resultado: str) -> QTextCharFormat:
    """O formato do objeto: a formatacao de texto de `base` mais o tipo e a instrucao."""
    cf = QTextCharFormat(base)
    for prop in (QTextFormat.Property.ImageName, QTextFormat.Property.ImageWidth,
                 QTextFormat.Property.ImageHeight, QTextFormat.Property.TextToolTip):
        cf.clearProperty(prop)
    cf.setObjectType(TIPO_CAMPO)
    cf.setProperty(PROP_CAMPO, instrucao)
    cf.setProperty(PROP_CAMPO_RESULTADO, resultado)
    return cf


def inserir_campo(cursor: QTextCursor, instrucao: str, resultado: str = "1",
                  base: QTextCharFormat | None = None) -> None:
    """Insere o campo no cursor, com a formatacao `base` (ou a do cursor)."""
    fmt = base if base is not None else cursor.charFormat()
    cursor.insertText(chr(0xFFFC), formato_de_campo(fmt, instrucao, resultado))


def instrucao_de(fmt: QTextFormat) -> str:
    valor = fmt.property(PROP_CAMPO)
    return valor if isinstance(valor, str) else ""


def resultado_de(fmt: QTextFormat) -> str:
    # Texto vazio guardado como propriedade volta do PySide como lista vazia (medido).
    valor = fmt.property(PROP_CAMPO_RESULTADO)
    return valor if isinstance(valor, str) else ""


def fonte_de(doc: QTextDocument, fmt: QTextFormat) -> QFont:
    """Fonte do campo em pixels de layout: a do formato, completada pela padrao do documento."""
    fonte = fmt.toCharFormat().font().resolve(doc.defaultFont())
    pontos = fonte.pointSizeF()
    if pontos <= 0:
        pontos = doc.defaultFont().pointSizeF() if doc.defaultFont().pointSizeF() > 0 else 11.0
    fonte.setPixelSize(max(1, round(pontos * _TWIPS_POR_PONTO)))
    return fonte


class ManipuladorDeCampo(QPyTextObject):
    """Tamanho e pintura do campo. Erro aqui nao pode derrubar a pintura: vira log."""

    def __init__(self, contexto: ContextoDeCampos, pai=None) -> None:
        super().__init__(pai)
        self.contexto = contexto
        self._larguras: dict[tuple, float] = {}

    def _indice(self, y: float) -> int:
        ctx = self.contexto
        if ctx.indice_fixo is not None:
            return ctx.indice_fixo
        if ctx.hb and ctx.hb > 0:
            return max(0, math.floor(y / ctx.hb))
        return 0

    def intrinsicSize(self, doc, pos, fmt) -> QSizeF:  # noqa: N802 - nome do Qt
        try:
            fonte = fonte_de(doc, fmt)
            metrica = QFontMetricsF(fonte)
            textos = tuple(self.contexto.textos_para_largura(instrucao_de(fmt)))
            chave = (fonte.key(), textos)
            largura = self._larguras.get(chave)
            if largura is None:
                largura = max((metrica.horizontalAdvance(t) for t in textos), default=0.0)
                if len(self._larguras) > 256:
                    self._larguras.clear()
                self._larguras[chave] = largura
            # So' a subida: o objeto fica na linha de base, e o texto e' desenhado nela.
            return QSizeF(max(largura, 1.0), max(metrica.ascent(), 1.0))
        except Exception:  # noqa: BLE001 - chamado pelo Qt no meio do layout
            log.exception("tamanho do campo")
            return QSizeF(1.0, 1.0)

    def drawObject(self, painter, rect, doc, pos, fmt) -> None:  # noqa: N802 - nome do Qt
        try:
            texto = self.contexto.valor(instrucao_de(fmt), self._indice(rect.center().y()))
            cf = fmt.toCharFormat()
            painter.save()
            painter.setFont(fonte_de(doc, fmt))
            cor = cf.foreground().color() if cf.hasProperty(
                QTextFormat.Property.ForegroundBrush) else QColor(0, 0, 0)
            painter.setPen(cor)
            painter.drawText(QPointF(rect.left(), rect.bottom()), texto)
            painter.restore()
        except Exception:  # noqa: BLE001 - chamado pelo Qt no meio da pintura
            log.exception("pintura do campo")


def registrar(doc: QTextDocument, contexto: ContextoDeCampos | None = None) -> ManipuladorDeCampo:
    """Registra o manipulador no layout do documento. Quem chama guarda a referencia."""
    manipulador = ManipuladorDeCampo(contexto or ContextoDeCampos(), doc)
    doc.documentLayout().registerHandler(TIPO_CAMPO, manipulador)
    return manipulador


def posicoes_de_campos(doc: QTextDocument, limite: int = 100000) -> list[int]:
    """Posicoes dos campos do documento, inclusive dentro de tabela."""
    saida: list[int] = []
    bloco = doc.begin()
    while bloco.isValid() and len(saida) < limite:
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and eh_campo(frag.charFormat()):
                inicio = frag.position()
                saida.extend(inicio + i for i, c in enumerate(frag.text()) if c == chr(0xFFFC))
            it += 1
        bloco = bloco.next()
    return saida


def refazer_campos(doc: QTextDocument, posicoes: list[int] | None = None) -> None:
    """Pede ao Qt para medir de novo os campos (o valor mudou). Nao mexe no desfazer."""
    for pos in (posicoes if posicoes is not None else posicoes_de_campos(doc)):
        doc.markContentsDirty(pos, 1)
