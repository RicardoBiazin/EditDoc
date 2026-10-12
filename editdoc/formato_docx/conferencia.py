"""Conferencia do arquivo gravado, antes da troca atomica. Sem Qt.

A gravacao escreve o temporario, le de volta o que ficou no disco e compara com
o que o usuario viu: mesmo numero de paragrafos e mesmo texto. Um arquivo que nao
confere nao substitui o original.
"""

from __future__ import annotations

from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.escritor import texto_gravavel
from editdoc.modelo.documento import Documento


class FalhaDeConferencia(Exception):
    """O arquivo gravado nao tem o mesmo texto que o documento."""


def texto_do_paragrafo(paragrafo) -> str:
    return "".join(texto_gravavel(r.texto)[0] for r in paragrafo.runs)


def conferir(dados: bytes, esperado: Documento) -> None:
    """Relê `dados` com o proprio leitor e compara paragrafos e texto."""
    from editdoc.formato_docx.leitor import ler
    try:
        lido, _avisos = ler(dados)
    except ErroDocx as erro:
        raise FalhaDeConferencia(f"o arquivo gravado nao pode ser lido: {erro.codigo}") from None
    if len(lido.paragrafos) != len(esperado.paragrafos):
        raise FalhaDeConferencia(
            f"paragrafos: esperado {len(esperado.paragrafos)}, gravado {len(lido.paragrafos)}")
    for i, (a, b) in enumerate(zip(esperado.paragrafos, lido.paragrafos)):
        if texto_do_paragrafo(a) != texto_do_paragrafo(b):
            raise FalhaDeConferencia(f"texto diferente no paragrafo {i + 1}")
        if a.quebra_antes != b.quebra_antes:
            raise FalhaDeConferencia(f"quebra de pagina diferente no paragrafo {i + 1}")
    if esperado.pagina != lido.pagina:
        raise FalhaDeConferencia("papel ou margens diferentes do documento")


def conferidor(esperado: Documento):
    """Funcao no formato que `gravacao.gravar_bytes(conferir=...)` espera."""
    def _conferir(dados: bytes) -> None:
        conferir(dados, esperado)
    return _conferir
