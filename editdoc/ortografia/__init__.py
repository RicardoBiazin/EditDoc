"""Corretor ortografico (0.1.36). Sem Qt.

O EditDoc nao embute dicionario nem biblioteca de correcao (nada GPL/AGPL no pacote, regra 5 do
CLAUDE.md): quem corrige e' a API de verificacao ortografica do proprio Windows
(`windows.CorretorWindows`, ISpellCheckerFactory por ctypes, Windows 8 ou mais novo). Ela usa os
idiomas que o usuario instalou e o dicionario pessoal dele. O texto verificado nunca sai do
computador: a API e' local.

Tudo o que o programa precisa do corretor esta em `Corretor`, de modo que os testes nao dependam
do dicionario da maquina: `CorretorFalso` e' uma implementacao em memoria, determinista, e a
fumaca da real so' roda quando o Windows a oferece (`tests/teste_ortografia.py`).

`criar_corretor()` e' a unica porta de entrada do programa: devolve o corretor do Windows ou None
(outro sistema, API ausente, ou `EDITDOC_CORRETOR=nenhum`). Nunca levanta: sem corretor, a
verificacao simplesmente fica desligada.
"""

from __future__ import annotations

import abc
import os
import re
import sys
from dataclasses import dataclass

from editdoc import log_interno

log = log_interno.obter(__name__)

#: Idioma quando o arquivo nao marca nenhum (w:lang ausente em todo lugar).
IDIOMA_PADRAO = "pt-BR"
#: Quantas sugestoes o menu mostra.
MAXIMO_DE_SUGESTOES = 5

_ETIQUETA = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8}){0,3}$")
#: Valores de w:lang que dizem "sem idioma": nao ha' o que verificar.
_SEM_IDIOMA = {"zxx", "und", "mis", "mul"}
#: Palavra: letras (qualquer alfabeto) com apostrofo no meio ("d'agua", "don't").
PALAVRA = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


class ErroDoCorretor(Exception):
    """O corretor falhou (API ausente, idioma nao instalado, chamada recusada)."""


@dataclass(frozen=True)
class Erro:
    """Um trecho errado: [ini, fim) no texto verificado (indices de str do Python).

    `acao`: "sugerir" (palavra desconhecida), "substituir" (o corretor ja' tem a troca, em
    `troca`) ou "excluir" (palavra repetida)."""
    ini: int
    fim: int
    acao: str = "sugerir"
    troca: str = ""


def normalizar_etiqueta(valor: str | None) -> str | None:
    """A etiqueta de idioma do w:lang ("pt-br", "PT_BR") na forma "pt-BR"; None se nao ha'
    idioma ("x-none", "zxx", vazio, lixo)."""
    if not valor or not isinstance(valor, str):
        return None
    valor = valor.strip()
    if not _ETIQUETA.match(valor) or valor.lower() in _SEM_IDIOMA:
        return None
    partes = valor.replace("_", "-").split("-")
    saida = [partes[0].lower()]
    for p in partes[1:]:
        if len(p) == 4 and p.isalpha():
            saida.append(p.title())
        elif (len(p) == 2 and p.isalpha()) or (len(p) == 3 and p.isdigit()):
            saida.append(p.upper())
        else:
            saida.append(p)
    return "-".join(saida)


class Corretor(abc.ABC):
    """O que o EditDoc pede a um corretor. Todas as chamadas vem da thread da interface."""

    #: Nome para o log e a barra de status ("Windows", "falso").
    nome = "corretor"

    @abc.abstractmethod
    def idiomas(self) -> list[str]:
        """Etiquetas dos idiomas instalados, na ordem em que o sistema os da'."""

    @abc.abstractmethod
    def suporta(self, idioma: str) -> bool:
        """Ha' dicionario para este idioma?"""

    @abc.abstractmethod
    def verificar(self, texto: str, idioma: str) -> list[Erro]:
        """Os trechos errados do texto, em ordem. Levanta `ErroDoCorretor` se falhar."""

    @abc.abstractmethod
    def sugerir(self, palavra: str, idioma: str) -> list[str]:
        """Trocas para a palavra, a melhor primeiro."""

    @abc.abstractmethod
    def adicionar(self, palavra: str, idioma: str) -> None:
        """Poe a palavra no dicionario pessoal."""


class CorretorFalso(Corretor):
    """Corretor em memoria para os testes: so' conhece as palavras dadas (sem diferenca de
    caixa), por idioma. `sugestoes` mapeia palavra errada -> trocas. Conta as chamadas."""

    nome = "falso"

    def __init__(self, palavras: dict | None = None, sugestoes: dict | None = None,
                 idiomas: tuple = ("pt-BR", "en-US"), repetidas: bool = False) -> None:
        # {"pt-BR": {"casa", ...}, "en-US": {...}}; um conjunto solto vale para todos.
        self.palavras = {k: {p.casefold() for p in v} for k, v in (palavras or {}).items()}
        self.sugestoes = dict(sugestoes or {})
        self._idiomas = list(idiomas)
        self.repetidas = repetidas
        self.adicionadas: list[tuple[str, str]] = []
        self.verificados: list[tuple[str, str]] = []
        self.chamadas_de_sugerir = 0
        self.quebra = False

    def idiomas(self) -> list[str]:
        return list(self._idiomas)

    def suporta(self, idioma: str) -> bool:
        return idioma in self._idiomas

    def verificar(self, texto: str, idioma: str) -> list[Erro]:
        if self.quebra:
            raise ErroDoCorretor("falha de proposito")
        self.verificados.append((texto, idioma))
        conhecidas = self.palavras.get(idioma, set())
        erros: list[Erro] = []
        anterior = None
        for m in PALAVRA.finditer(texto):
            chave = m.group().casefold()
            if self.repetidas and anterior == chave:
                erros.append(Erro(m.start(), m.end(), "excluir"))
            elif chave not in conhecidas:
                erros.append(Erro(m.start(), m.end()))
            anterior = chave
        return erros

    def sugerir(self, palavra: str, idioma: str) -> list[str]:
        self.chamadas_de_sugerir += 1
        return list(self.sugestoes.get(palavra, ()))

    def adicionar(self, palavra: str, idioma: str) -> None:
        self.adicionadas.append((palavra, idioma))
        self.palavras.setdefault(idioma, set()).add(palavra.casefold())


def corretor_desligado_de_proposito() -> bool:
    """`EDITDOC_CORRETOR=nenhum`: sem corretor e sem aviso (o usuario ou o teste pediu)."""
    return os.environ.get("EDITDOC_CORRETOR", "auto").strip().lower() in (
        "nenhum", "0", "off", "nao")


def criar_corretor() -> Corretor | None:
    """O corretor do Windows, ou None. `EDITDOC_CORRETOR=nenhum` o desliga (os testes de janela
    usam, para nao depender do dicionario da maquina)."""
    if corretor_desligado_de_proposito():
        return None
    if not sys.platform.startswith("win"):
        return None
    try:
        from editdoc.ortografia.windows import CorretorWindows
        return CorretorWindows()
    except Exception as erro:  # noqa: BLE001 - qualquer falha so' desliga a verificacao
        log.warning("corretor do Windows indisponivel: %s", erro)
        return None
