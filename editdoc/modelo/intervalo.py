"""Intervalo de paginas e copias para imprimir e exportar (M7). Sem Qt.

O usuario escreve as paginas como no Word: "1-3, 5, 8-". Os numeros sao os das folhas
(a primeira folha e' 1), nao o numero formatado do rodape. Por dentro, as paginas sao
indices a partir de 0, como no layout.
"""

from __future__ import annotations

import re

#: Texto de intervalo acima disto e' recusado: ninguem digita isso a mao.
TAMANHO_MAXIMO = 500

_PARTE = re.compile(r"^(\d{1,6})?\s*(-)?\s*(\d{1,6})?$")


def analisar_intervalo(texto: str, total: int) -> list[int] | None:
    """'1-3, 5' -> [0, 1, 2, 4]. None se o texto e' invalido ou sai do documento.

    Aceita virgula ou ponto e virgula entre as partes; "3-" vai ate' a ultima pagina e
    "-3" comeca na primeira. Paginas repetidas saem uma vez, em ordem crescente.
    """
    if total < 1 or not texto or len(texto) > TAMANHO_MAXIMO:
        return None
    escolhidas: set[int] = set()
    for parte in re.split(r"[,;]", texto):
        parte = parte.strip()
        if not parte:
            continue
        m = _PARTE.match(parte)
        if m is None:
            return None
        ini, traco, fim = m.group(1), m.group(2), m.group(3)
        if traco is None:
            if ini is None or fim is not None:
                return None
            a = b = int(ini)
        else:
            if ini is None and fim is None:
                return None
            a = int(ini) if ini is not None else 1
            b = int(fim) if fim is not None else total
        if a < 1 or b > total or a > b:
            return None
        escolhidas.update(range(a - 1, b))
    return sorted(escolhidas) or None


def sequencia_de_copias(paginas: list[int], copias: int, agrupar: bool) -> list[int]:
    """A ordem das folhas para `copias` copias. Agrupadas: 1 2 3, 1 2 3; senao 1 1, 2 2, 3 3."""
    copias = max(1, int(copias))
    if agrupar:
        return list(paginas) * copias
    return [p for p in paginas for _ in range(copias)]


def descrever_paginas(paginas: list[int]) -> str:
    """[0, 1, 2, 4] -> '1-3, 5': o texto do intervalo, para mensagens."""
    partes: list[str] = []
    inicio = anterior = None
    for p in sorted(set(paginas)):
        if inicio is None:
            inicio = anterior = p
        elif p == anterior + 1:
            anterior = p
        else:
            partes.append(_trecho(inicio, anterior))
            inicio = anterior = p
    if inicio is not None:
        partes.append(_trecho(inicio, anterior))
    return ", ".join(partes)


def _trecho(a: int, b: int) -> str:
    return str(a + 1) if a == b else f"{a + 1}-{b + 1}"
