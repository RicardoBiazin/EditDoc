"""Conferencia do arquivo gravado, antes da troca atomica. Sem Qt.

A gravacao escreve o temporario, le de volta o que ficou no disco e compara com
o que o usuario viu: mesma estrutura (paragrafos, tabelas, linhas, celulas e
mesclas), mesmo texto, mesmas quebras e as mesmas imagens (pelos bytes). Um
arquivo que nao confere nao substitui o original.

Os dois lados passam por `normalizar`: o escritor completa a celula e o corpo
que terminam em tabela com um paragrafo vazio (o Word exige), e isso nao e'
diferenca.
"""

from __future__ import annotations

import hashlib

from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.escritor import texto_gravavel
from editdoc.modelo.documento import CARACTERE_OBJETO, Documento, Tabela, normalizar


class FalhaDeConferencia(Exception):
    """O arquivo gravado nao tem o mesmo texto que o documento."""


def texto_do_paragrafo(paragrafo) -> str:
    """Texto como vai para o arquivo. A imagem conta como CARACTERE_OBJETO."""
    return "".join(CARACTERE_OBJETO if r.imagem is not None else texto_gravavel(r.texto)[0]
                   for r in paragrafo.runs)


def _imagens(paragrafo) -> list[str]:
    return [hashlib.sha256(r.imagem.dados).hexdigest()[:16] + f"@{r.imagem.largura_emu}x"
            f"{r.imagem.altura_emu}" for r in paragrafo.runs if r.imagem is not None]


def _itens(blocos, saida: list, onde: str) -> None:
    """Sequencia comparavel: um item por paragrafo, tabela, linha e celula."""
    n_par = 0
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            saida.append((f"{onde}tabela", "tabela", len(bloco.linhas), len(bloco.colunas_tw)))
            for i, linha in enumerate(bloco.linhas):
                saida.append((f"{onde}linha {i + 1}", "linha", len(linha.celulas), linha.cabecalho))
                for j, celula in enumerate(linha.celulas):
                    lugar = f"{onde}celula {i + 1},{j + 1}: "
                    saida.append((lugar, "celula", celula.colunas, celula.mescla_vertical))
                    _itens(celula.blocos, saida, lugar)
            saida.append((f"{onde}fim da tabela", "fim"))
        else:
            n_par += 1
            saida.append((f"{onde}paragrafo {n_par}", "p", texto_do_paragrafo(bloco),
                          bloco.quebra_antes, tuple(_imagens(bloco))))


def conferir(dados: bytes, esperado: Documento) -> None:
    """Relê `dados` com o proprio leitor e compara estrutura, texto e imagens."""
    from editdoc.formato_docx.leitor import ler
    try:
        lido, _avisos = ler(dados)
    except ErroDocx as erro:
        raise FalhaDeConferencia(f"o arquivo gravado nao pode ser lido: {erro.codigo}") from None
    a: list = []
    b: list = []
    _itens(normalizar(esperado).paragrafos, a, "")
    _itens(normalizar(lido).paragrafos, b, "")
    n_a = sum(1 for x in a if x[1] == "p")
    n_b = sum(1 for x in b if x[1] == "p")
    if n_a != n_b:
        raise FalhaDeConferencia(f"paragrafos: esperado {n_a}, gravado {n_b}")
    for x, y in zip(a, b):
        if x[1:] == y[1:]:
            continue
        lugar = x[0]
        if x[1] == "p" and y[1] == "p":
            if x[2] != y[2]:
                raise FalhaDeConferencia(f"texto diferente no {lugar}")
            if x[3] != y[3]:
                raise FalhaDeConferencia(f"quebra de pagina diferente no {lugar}")
            raise FalhaDeConferencia(f"imagem diferente no {lugar}")
        raise FalhaDeConferencia(f"estrutura de tabela diferente em {lugar}")
    if len(a) != len(b):
        raise FalhaDeConferencia("estrutura de tabela diferente no fim do documento")
    if esperado.pagina != lido.pagina:
        raise FalhaDeConferencia("papel ou margens diferentes do documento")


def conferidor(esperado: Documento):
    """Funcao no formato que `gravacao.gravar_bytes(conferir=...)` espera."""
    def _conferir(dados: bytes) -> None:
        conferir(dados, esperado)
    return _conferir
