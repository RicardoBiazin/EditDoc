"""Le, de uma vez, o formato que a faixa precisa mostrar.

Sem selecao, vale o formato do proximo caractere digitado (currentCharFormat).
Com selecao, vale o formato do primeiro caractere selecionado. Um trecho misto
(parte em negrito, parte nao) mostra o estado do inicio. Essa limitacao fica
registrada para o M6, quando o botao ganha estado parcial.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextBlockFormat, QTextCharFormat, QTextCursor, QTextListFormat
from PySide6.QtWidgets import QTextEdit

#: O Qt chama de negrito a partir de 600. O Word grava 700.
NEGRITO_MINIMO = 600

_PROPORCIONAL = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
_SEM_SUBLINHADO = QTextCharFormat.UnderlineStyle.NoUnderline


@dataclass(frozen=True)
class EstadoDoCursor:
    familia: str
    tamanho: float
    negrito: bool
    italico: bool
    sublinhado: bool
    tachado: bool
    subscrito: bool
    sobrescrito: bool
    alinhamento: str        # "esquerda", "centro", "direita" ou "justificado"
    espacamento: int        # porcentagem: 100, 115, 150, 200...
    marcadores: bool
    numeracao: bool


def ler(editor: QTextEdit) -> EstadoDoCursor:
    doc = editor.document()
    cursor = editor.textCursor()
    if cursor.hasSelection():
        inicio = cursor.selectionStart()
        ref = QTextCursor(doc)
        ref.setPosition(inicio)
        ref.setPosition(inicio + 1, QTextCursor.MoveMode.KeepAnchor)
        formato = ref.charFormat()
        bloco = doc.findBlock(inicio)
    else:
        formato = editor.currentCharFormat()
        bloco = cursor.block()

    bloco_fmt = bloco.blockFormat()
    lista = bloco.textList()
    # fontFamilies() devolve None quando nao ha familia. fontFamily() esta
    # depreciado e derruba o processo num formato vazio: nao usar.
    familias = formato.fontFamilies() or []
    tamanho = formato.fontPointSize() or doc.defaultFont().pointSizeF()
    va = formato.verticalAlignment()

    estilo = lista.format().style() if lista is not None else None
    marcas = {
        QTextListFormat.Style.ListDisc,
        QTextListFormat.Style.ListCircle,
        QTextListFormat.Style.ListSquare,
    }

    flags = bloco_fmt.alignment()
    if flags & Qt.AlignmentFlag.AlignHCenter:
        alinhamento = "centro"
    elif flags & Qt.AlignmentFlag.AlignRight:
        alinhamento = "direita"
    elif flags & Qt.AlignmentFlag.AlignJustify:
        alinhamento = "justificado"
    else:
        alinhamento = "esquerda"

    return EstadoDoCursor(
        familia=familias[0] if familias else "",
        tamanho=float(tamanho),
        negrito=formato.fontWeight() >= NEGRITO_MINIMO,
        italico=formato.fontItalic(),
        sublinhado=formato.fontUnderline() or formato.underlineStyle() != _SEM_SUBLINHADO,
        tachado=formato.fontStrikeOut(),
        subscrito=va == QTextCharFormat.VerticalAlignment.AlignSubScript,
        sobrescrito=va == QTextCharFormat.VerticalAlignment.AlignSuperScript,
        alinhamento=alinhamento,
        espacamento=round(bloco_fmt.lineHeight())
        if bloco_fmt.lineHeightType() == _PROPORCIONAL else 100,
        marcadores=estilo in marcas,
        numeracao=lista is not None and estilo not in marcas,
    )
