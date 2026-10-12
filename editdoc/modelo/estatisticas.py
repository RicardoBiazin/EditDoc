"""Contagem de palavras e de caracteres do texto. Sem Qt.

Palavra e' qualquer sequencia separada por espaco em branco. As quebras que o Qt
usa para paragrafo (U+2029) e para linha (U+2028) contam como espaco e nao
entram na contagem de caracteres, como no Word.
"""

from __future__ import annotations

from dataclasses import dataclass

_QUEBRAS = (" ", " ", "\n", "\r")


@dataclass(frozen=True)
class Contagem:
    palavras: int
    caracteres: int
    caracteres_sem_espacos: int


def contar(texto: str) -> Contagem:
    quebras = sum(texto.count(q) for q in _QUEBRAS)
    return Contagem(
        palavras=len(texto.split()),
        caracteres=len(texto) - quebras,
        caracteres_sem_espacos=sum(1 for c in texto if not c.isspace()),
    )
