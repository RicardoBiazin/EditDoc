"""Hiperlinks no QTextDocument (0.1.3).

O trecho do link tem no formato de caractere o que o Qt ja' entende (`setAnchor` e
`setAnchorHref`, que o HTML colado tambem traz) e, numa propriedade de usuario, o `Link`
do modelo em JSON (com a dica, o historico e o quadro do arquivo). A volta para o modelo
le o JSON; sem ele (link colado de uma pagina da Web), le o endereco do Qt.

A aparencia e' a do estilo de caractere "Hyperlink" do arquivo (azul sublinhado): o link
inserido no EditDoc recebe esse estilo, como no Word.
"""

from __future__ import annotations

import json

from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextDocument, QTextFormat

from editdoc.modelo.documento import Link

#: Formato de caractere: o Link do modelo, em JSON. Numero livre (ver CLAUDE.md).
PROP_LINK = QTextFormat.Property.UserProperty.value + 21
P = QTextFormat.Property
#: Propriedades que fazem do trecho um link (para tirar ao digitar depois dele).
PROPS_DE_LINK = (P.IsAnchor, P.AnchorHref, P.AnchorName, PROP_LINK)
#: Esquemas que o Ctrl+clique abre sem perguntar.
ESQUEMAS_SEGUROS = ("http", "https", "mailto")


def _json(link: Link) -> str:
    return json.dumps({"url": link.url, "ancora": link.ancora, "dica": link.dica,
                       "historico": link.historico, "quadro": link.quadro, "local": link.local},
                      sort_keys=True)


def _de_json(texto) -> Link | None:
    try:
        dado = json.loads(str(texto))
    except (TypeError, ValueError):
        return None
    if not isinstance(dado, dict):
        return None

    def texto_ou_none(chave):
        valor = dado.get(chave)
        return valor if isinstance(valor, str) and valor else None
    historico = dado.get("historico")
    link = Link(url=texto_ou_none("url"), ancora=texto_ou_none("ancora"),
                dica=texto_ou_none("dica"),
                historico=historico if isinstance(historico, bool) else None,
                quadro=texto_ou_none("quadro"), local=texto_ou_none("local"))
    return link if link.url or link.ancora else None


def com_link(cf: QTextCharFormat, link: Link | None) -> QTextCharFormat:
    """Copia do formato com o link (ou sem nenhum, se `link` for None)."""
    novo = QTextCharFormat(cf)
    if link is None:
        for prop in PROPS_DE_LINK:
            novo.clearProperty(prop)
        return novo
    novo.setAnchor(True)
    novo.setAnchorHref(link.href())
    novo.setProperty(PROP_LINK, _json(link))
    return novo


def link_de(cf: QTextFormat) -> Link | None:
    """O Link do trecho, ou None. Link sem JSON (HTML colado) vem do endereco do Qt."""
    if cf.hasProperty(PROP_LINK):
        link = _de_json(cf.property(PROP_LINK))
        if link is not None:
            return link
    ccf = cf.toCharFormat()
    if not ccf.isAnchor():
        return None
    href = ccf.anchorHref()
    if not href:
        return None
    if href.startswith("#"):
        return Link(ancora=href[1:]) if len(href) > 1 else None
    return Link(url=href, historico=True)


def formato_em(doc: QTextDocument, pos: int) -> QTextCharFormat | None:
    """O formato do caractere que comeca em `pos`; None fora do texto ou no fim de paragrafo.

    Pelo fragmento do bloco, nao pelo cursor: com selecao de um caractere, o
    `QTextCursor.charFormat()` no fim do paragrafo devolve o formato do primeiro caractere
    do paragrafo seguinte (medido no Qt 6.11), e a marca de la' parecia estar aqui.
    """
    if pos < 0 or pos >= doc.characterCount() - 1:
        return None
    bloco = doc.findBlock(pos)
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and frag.position() <= pos < frag.position() + frag.length():
            return frag.charFormat()
        it += 1
    return None


def link_em(doc: QTextDocument, pos: int) -> Link | None:
    cf = formato_em(doc, pos)
    return link_de(cf) if cf is not None else None


def trecho_do_link(doc: QTextDocument, pos: int) -> tuple[int, int, Link] | None:
    """(inicio, fim, link) do link que tem o caractere `pos`, dentro do paragrafo."""
    link = link_em(doc, pos)
    if link is None:
        return None
    bloco = doc.findBlock(pos)
    inicio, fim = pos, pos + 1
    limite_ini = bloco.position()
    limite_fim = bloco.position() + bloco.length() - 1
    while inicio > limite_ini and link_em(doc, inicio - 1) == link:
        inicio -= 1
    while fim < limite_fim and link_em(doc, fim) == link:
        fim += 1
    return inicio, fim, link


def link_no_cursor(doc: QTextDocument, cursor: QTextCursor) -> tuple[int, int, Link] | None:
    """O link sob o cursor: o caractere depois dele, ou o de antes (fim do link)."""
    if cursor.hasSelection():
        return trecho_do_link(doc, cursor.selectionStart())
    pos = cursor.position()
    return trecho_do_link(doc, pos) or (trecho_do_link(doc, pos - 1) if pos > 0 else None)


def esquema(url: str) -> str:
    """O esquema do endereco ("https", "mailto", "file"...), em minusculas; "" sem esquema."""
    antes, sep, _resto = url.strip().partition(":")
    if not sep or not antes or not antes[0].isalpha() or \
            not all(c.isalnum() or c in "+-." for c in antes):
        return ""
    return antes.lower()


def abre_sem_perguntar(url: str) -> bool:
    return esquema(url) in ESQUEMAS_SEGUROS


def endereco_normalizado(texto: str) -> str | None:
    """O endereco digitado no dialogo, como vai para o arquivo. None se vazio.

    "fulano@exemplo.com" vira mailto; "www.exemplo.com" (sem esquema) vira https; caminho do
    Windows vira file:///; espacos e acentos sao codificados (o Word recusa endereco com
    espaco cru). O esquema digitado e' mantido.
    """
    from PySide6.QtCore import QUrl

    texto = texto.strip()
    if not texto:
        return None
    if len(esquema(texto)) == 1 or texto.startswith("\\\\"):
        # Caminho do Windows (unidade C: ou caminho de rede): vira file:///.
        return QUrl.fromLocalFile(texto).toString(QUrl.ComponentFormattingOption.FullyEncoded)
    if not esquema(texto):
        if "@" in texto and "/" not in texto and " " not in texto:
            texto = "mailto:" + texto
        else:
            texto = "https://" + texto  # "exemplo.com.br/pagina", como o Word completa
    url = QUrl(texto, QUrl.ParsingMode.TolerantMode)
    if not url.isValid():
        return texto.replace(" ", "%20")
    return url.toString(QUrl.ComponentFormattingOption.FullyEncoded)
