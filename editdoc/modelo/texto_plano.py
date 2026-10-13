"""Exportar como texto sem formatacao (M7). Sem Qt.

Um paragrafo por linha. Tabela: uma linha por linha da tabela, celulas separadas por
tabulacao (o que se cola numa planilha). Imagem e objeto opaco nao viram texto. Campo sai com o ultimo
resultado guardado, como o texto que ele mostra.
"""

from __future__ import annotations

from editdoc.modelo.documento import CARACTERE_OBJETO, Documento, Paragrafo, Tabela

#: Fim de linha do Windows: o Bloco de Notas antigo mostra tudo numa linha com LF puro.
FIM_DE_LINHA = "\r\n"


def _texto_do_paragrafo(p: Paragrafo) -> str:
    texto = "".join(r.texto for r in p.runs if not r.eh_objeto())
    # U+2028 (quebra de linha manual) vira quebra de linha; objeto solto nao vira nada.
    return texto.replace(" ", FIM_DE_LINHA).replace(CARACTERE_OBJETO, "")


def _linhas(blocos) -> list[str]:
    saida: list[str] = []
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            for linha in bloco.linhas:
                celulas = [" ".join(_linhas(c.blocos)).replace("\t", " ") for c in linha.celulas]
                saida.append("\t".join(celulas))
        else:
            saida.append(_texto_do_paragrafo(bloco))
    return saida


def texto_do_documento(doc: Documento) -> str:
    """O corpo do documento como texto, com fim de linha do Windows."""
    return FIM_DE_LINHA.join(_linhas(doc.paragrafos)) + FIM_DE_LINHA
