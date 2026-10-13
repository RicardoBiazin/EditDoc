"""Comandos de hiperlink (0.1.3): inserir, editar e remover. Cada um e' um passo de desfazer.

O link inserido recebe o estilo de caractere "Hyperlink" do documento (azul sublinhado);
se o documento nao o tem, ele e' criado, como o Word faz com os estilos latentes. Remover o
link tira o destino e esse estilo; a formatacao direta do texto fica.

Se o texto exibido nao mudou, o link vai por cima do trecho, que mantem a formatacao
(negrito, imagem, objeto). Se mudou, o trecho e' trocado pelo texto novo, com a formatacao
do comeco do trecho.
"""

from __future__ import annotations

from PySide6.QtGui import QTextCharFormat, QTextCursor

from editdoc.edicao import estilos as ed_estilos
from editdoc.modelo.documento import Link
from editdoc.ponte_qt import campos, links, marcas, opacos
from editdoc.ponte_qt import estilos as pq

#: Nome canonico do estilo de caractere dos links.
ESTILO_LINK = "hyperlink"


def texto_do_trecho(doc, inicio: int, fim: int) -> str:
    c = QTextCursor(doc)
    c.setPosition(inicio)
    c.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
    return c.selectedText()


def _fragmentos(doc, inicio: int, fim: int):
    """(inicio, fim, formato) dos fragmentos no trecho, cortados nas pontas."""
    saida = []
    bloco = doc.findBlock(inicio)
    while bloco.isValid() and bloco.position() < fim:
        for a, b, cf in pq.trechos_do_bloco(bloco):
            a, b = max(a, inicio), min(b, fim)
            if a < b:
                saida.append((a, b, cf))
        bloco = bloco.next()
    return saida


def _eh_objeto(cf) -> bool:
    return (cf.isImageFormat() or campos.eh_campo(cf) or opacos.eh_opaco(cf)
            or marcas.eh_marca(cf))


def _sid_paragrafo(doc, pos: int) -> str | None:
    return pq.estilo_do_bloco(doc.findBlock(pos).blockFormat())


def _com_estilo(cf: QTextCharFormat, res_velho, res_novo, sid_par, sid_car) -> QTextCharFormat:
    """O formato recomposto para o estilo de caractere `sid_car` (None tira o estilo)."""
    atual = pq.estilo_do_caractere(cf)
    return pq.recompor_caractere(cf, res_velho.caractere(sid_par, atual),
                                 res_novo.caractere(sid_par, sid_car), sid_car)


def aplicar_link(editor, trecho: tuple[int, int] | None, texto: str, link: Link) -> None:
    """Insere (trecho None), poe o link num trecho, ou troca o texto e o link do trecho."""
    doc = editor.document()
    velho, novo, sid = ed_estilos._garantido(editor, ESTILO_LINK)
    res_v, res_n = pq.Resolvedor(velho), pq.Resolvedor(novo)
    cursor = editor.textCursor()
    c = QTextCursor(doc)
    c.beginEditBlock()
    if novo is not velho:
        pq.trocar_catalogo(doc, novo)
    if trecho is not None and texto == texto_do_trecho(doc, *trecho):
        for a, b, cf in _fragmentos(doc, *trecho):
            ncf = cf if _eh_objeto(cf) else _com_estilo(cf, res_v, res_n,
                                                        _sid_paragrafo(doc, a), sid)
            c.setPosition(a)
            c.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            c.setCharFormat(links.com_link(ncf, link))
        fim = trecho[1]
    else:
        pos = trecho[0] if trecho is not None else cursor.selectionStart()
        if trecho is not None:
            c.setPosition(trecho[0])
            c.setPosition(trecho[1], QTextCursor.MoveMode.KeepAnchor)
            base = QTextCharFormat(links.formato_em(doc, trecho[0]) or c.charFormat())
            c.removeSelectedText()
        else:
            c.setPosition(cursor.selectionStart())
            if cursor.hasSelection():
                c.setPosition(cursor.selectionEnd(), QTextCursor.MoveMode.KeepAnchor)
            base = QTextCharFormat(c.charFormat()) if not cursor.hasSelection() else \
                QTextCharFormat(links.formato_em(doc, cursor.selectionStart()) or c.charFormat())
            if c.hasSelection():
                c.removeSelectedText()
        for prop in (*campos.PROPS_DE_CAMPO, *opacos.PROPS_DE_OPACO, *marcas.PROPS_DE_MARCA,
                     *links.PROPS_DE_LINK):
            base.clearProperty(prop)
        if base.isImageFormat():
            base = QTextCharFormat()
        cf = _com_estilo(base, res_v, res_n, _sid_paragrafo(doc, pos), sid)
        c.setPosition(pos)
        c.insertText(texto, links.com_link(cf, link))
        fim = c.position()
    c.endEditBlock()
    cursor = QTextCursor(doc)
    cursor.setPosition(fim)
    editor.setTextCursor(cursor)


def remover_link(editor, trecho: tuple[int, int]) -> None:
    """Tira o link do trecho (e o estilo "Hyperlink"). A formatacao direta fica."""
    doc = editor.document()
    estilos = pq.catalogo(doc)
    hiper = estilos.por_nome(ESTILO_LINK)
    res = pq.Resolvedor(estilos)
    c = QTextCursor(doc)
    c.beginEditBlock()
    for a, b, cf in _fragmentos(doc, *trecho):
        ncf = links.com_link(cf, None)
        if not _eh_objeto(cf) and hiper is not None and pq.estilo_do_caractere(cf) == hiper.id:
            ncf = _com_estilo(ncf, res, res, _sid_paragrafo(doc, a), None)
        c.setPosition(a)
        c.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
        c.setCharFormat(ncf)
    c.endEditBlock()
    editor.setTextCursor(editor.textCursor())


def formato_para_digitar(doc, pos: int, cf: QTextCharFormat) -> QTextCharFormat:
    """Digitar logo depois de um link nao estende o link (como no Word): sem o destino e sem
    o estilo "Hyperlink". Dentro do link, o texto digitado faz parte dele."""
    link = links.link_de(cf)
    if link is None or links.link_em(doc, pos) == link:
        return cf
    novo = links.com_link(cf, None)
    estilos = pq.catalogo(doc)
    hiper = estilos.por_nome(ESTILO_LINK)
    if hiper is not None and pq.estilo_do_caractere(novo) == hiper.id:
        res = pq.Resolvedor(estilos)
        novo = _com_estilo(novo, res, res, _sid_paragrafo(doc, pos), None)
    return novo
