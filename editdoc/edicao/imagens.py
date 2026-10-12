"""Comandos de imagem sobre o editor (PainelDocumento, com a API do QTextEdit).

Inserir confere a imagem pelo cabecalho ANTES de decodificar (modelo/imagem.py):
formato aceito, dimensoes validas e o teto de pixels. A imagem entra no tamanho
natural (96 dpi), reduzida para caber na largura disponivel e na altura da pagina.

Redimensionar troca so' o tamanho do QTextImageFormat: os bytes nao mudam. E' um
passo de desfazer.
"""

from __future__ import annotations

from PySide6.QtGui import QImage, QTextCursor, QTextImageFormat

from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.documento import Imagem
from editdoc.modelo.pagina import PAPEL_MAXIMO_TW
from editdoc.modelo.unidades import EMU_POR_PX, px_de_twips
from editdoc.ponte_qt import imagens, para_qt

#: Menor lado da imagem, em px96 (cerca de 0,1 cm).
LADO_MINIMO_PX = 4.0
#: Maior lado: o maior papel.
LADO_MAXIMO_PX = px_de_twips(PAPEL_MAXIMO_TW)


class ImagemRecusada(ValueError):
    """A imagem nao pode entrar. A mensagem e' para o usuario, em portugues."""


def conferir(dados: bytes) -> tuple[str, tuple[int, int]]:
    """(formato, (largura, altura) em pixels), ou ImagemRecusada com o motivo."""
    if len(dados) > mod_imagem.BYTES_MAXIMOS:
        raise ImagemRecusada("A imagem tem mais de 64 MB.")
    formato = mod_imagem.formato_de(dados)
    if formato is None:
        raise ImagemRecusada("O EditDoc insere imagens PNG, JPEG, GIF e BMP. "
                             "Este arquivo não é de nenhum desses formatos.")
    dims = mod_imagem.dimensoes(dados, formato)
    if dims is None or dims[0] <= 0 or dims[1] <= 0:
        raise ImagemRecusada("O arquivo de imagem está danificado.")
    if not mod_imagem.decodificavel(*dims):
        raise ImagemRecusada(f"A imagem tem {dims[0]} x {dims[1]} pixels. O limite é "
                             "de 64 megapixels, e 30000 pixels em cada lado.")
    return formato, dims


def _largura_disponivel_px(editor, cursor: QTextCursor) -> float:
    pagina = editor.configuracao_pagina()
    tabela = cursor.currentTable()
    if tabela is None:
        return px_de_twips(pagina.corpo_largura_tw())
    celula = tabela.cellAt(cursor)
    restricoes = tabela.format().columnWidthConstraints()
    inicio, span = celula.column(), celula.columnSpan()
    largura = sum(r.rawValue() for r in restricoes[inicio:inicio + span])
    margens = para_qt.margens_da_tabela_em(tabela.format())
    return max(LADO_MINIMO_PX, largura - px_de_twips(margens[1] + margens[3]))


def tamanho_inicial(editor, cursor: QTextCursor, dims: tuple[int, int]) -> tuple[float, float]:
    """Tamanho natural a 96 dpi, reduzido para caber na largura e na altura disponiveis."""
    largura, altura = float(dims[0]), float(dims[1])
    max_l = _largura_disponivel_px(editor, cursor)
    max_a = px_de_twips(editor.configuracao_pagina().corpo_altura_tw()) * 0.9
    escala = min(1.0, max_l / largura, max_a / altura)
    return max(LADO_MINIMO_PX, largura * escala), max(LADO_MINIMO_PX, altura * escala)


def inserir_bytes(editor, dados: bytes, descricao: str = "") -> None:
    """Insere a imagem no cursor. ImagemRecusada se ela nao puder entrar."""
    formato, dims = conferir(dados)
    cursor = editor.textCursor()
    largura, altura = tamanho_inicial(editor, cursor, dims)
    cursor.beginEditBlock()
    if cursor.hasSelection():
        cursor.removeSelectedText()
    para_qt.inserir_imagem(cursor, Imagem(dados=bytes(dados), formato=formato,
                                          largura_emu=round(largura * EMU_POR_PX),
                                          altura_emu=round(altura * EMU_POR_PX),
                                          descricao=descricao))
    cursor.endEditBlock()
    editor.setTextCursor(cursor)


def inserir_qimage(editor, img: QImage) -> None:
    """Imagem da area de transferencia: entra como PNG."""
    if img.isNull():
        raise ImagemRecusada("A área de transferência não tem uma imagem válida.")
    inserir_bytes(editor, imagens.png_de(img))


def formato_em(doc, pos: int) -> QTextImageFormat | None:
    """O QTextImageFormat do caractere em `pos`, ou None se ali nao ha imagem."""
    if pos < 0 or pos >= doc.characterCount() - 1:
        return None
    cursor = QTextCursor(doc)
    cursor.setPosition(pos)
    cursor.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
    if cursor.selectedText() != chr(0xFFFC):
        return None
    fmt = cursor.charFormat()
    return fmt.toImageFormat() if fmt.isImageFormat() else None


def imagem_selecionada(editor) -> int | None:
    """Posicao da imagem quando a selecao e' exatamente uma imagem; senao None."""
    cursor = editor.textCursor()
    if not cursor.hasSelection() or cursor.selectionEnd() - cursor.selectionStart() != 1:
        return None
    pos = cursor.selectionStart()
    return pos if formato_em(editor.document(), pos) is not None else None


def tamanho_em_px(editor, pos: int) -> tuple[float, float] | None:
    fmt = formato_em(editor.document(), pos)
    if fmt is None:
        return None
    return fmt.width(), fmt.height()


def redimensionar(editor, pos: int, largura_px: float, altura_px: float) -> bool:
    """Novo tamanho da imagem em `pos`. Um passo de desfazer. A selecao fica na imagem."""
    if formato_em(editor.document(), pos) is None:
        return False
    largura = min(max(float(largura_px), LADO_MINIMO_PX), LADO_MAXIMO_PX)
    altura = min(max(float(altura_px), LADO_MINIMO_PX), LADO_MAXIMO_PX)
    cursor = QTextCursor(editor.document())
    cursor.setPosition(pos)
    cursor.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
    novo = QTextImageFormat()
    novo.setWidth(largura)
    novo.setHeight(altura)
    cursor.beginEditBlock()
    cursor.mergeCharFormat(novo)
    cursor.endEditBlock()
    editor.setTextCursor(cursor)
    return True


def cm_de_px(px: float) -> float:
    return px * 2.54 / 96


def px_de_cm(cm: float) -> float:
    return cm * 96 / 2.54
