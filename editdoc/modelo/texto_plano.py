"""Exportar como texto sem formatacao (M7). Sem Qt.

Um paragrafo por linha. Tabela: uma linha por linha da tabela, celulas separadas por
tabulacao (o que se cola numa planilha). Imagem e objeto opaco nao viram texto. Campo sai com o ultimo
resultado guardado, como o texto que ele mostra.

Listas (0.1.4): o item sai com o numero calculado como na tela ("1.1.", "a)", "•") e o
sufixo do nivel (tabulacao, espaco ou nada). O simbolo da fonte Symbol ou Wingdings sai como
o caractere Unicode parecido.
"""

from __future__ import annotations

from editdoc.modelo.documento import CARACTERE_OBJETO, Documento, Paragrafo, Tabela
from editdoc.modelo.numeracao import rotulos_do_documento, texto_visivel

#: Fim de linha do Windows: o Bloco de Notas antigo mostra tudo numa linha com LF puro.
FIM_DE_LINHA = "\r\n"


_SUFIXO = {"tab": "\t", "space": " ", "nothing": ""}


def _texto_do_paragrafo(p: Paragrafo, rotulos: dict | None = None) -> str:
    texto = "".join(r.texto for r in p.runs if not r.eh_objeto())
    rotulo = (rotulos or {}).get(id(p))
    if rotulo is not None and not rotulo.nivel.oculto:
        texto = texto_visivel(rotulo.texto) + _SUFIXO.get(rotulo.nivel.sufixo, "\t") + texto
    # U+2028 (quebra de linha manual) vira quebra de linha; objeto solto nao vira nada.
    return texto.replace(" ", FIM_DE_LINHA).replace(CARACTERE_OBJETO, "")


def _linhas(blocos, rotulos: dict | None = None) -> list[str]:
    saida: list[str] = []
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            for linha in bloco.linhas:
                celulas = [" ".join(_linhas(c.blocos, rotulos)).replace("\t", " ") for c in linha.celulas]
                saida.append("\t".join(celulas))
        else:
            saida.append(_texto_do_paragrafo(bloco, rotulos))
    return saida


def texto_do_documento(doc: Documento) -> str:
    """O corpo do documento como texto, com fim de linha do Windows."""
    return FIM_DE_LINHA.join(_linhas(doc.paragrafos, rotulos_do_documento(doc))) + FIM_DE_LINHA
