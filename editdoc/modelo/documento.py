"""Modelo do documento: dados puros, sem Qt e sem lxml.

Convencao tri-state, em todos os campos opcionais: None = "herda" (o arquivo nao
diz nada); False ou 0 = "desligado" de forma explicita. None nunca vira False.

Unidades: tamanho em meio-ponto (`w:sz`); recuos e espacos em twips (1/20 de
ponto). Espacamento entre linhas em porcentagem (100 = simples).

`normalizar` funde runs vizinhos de mesma formatacao e descarta runs vazios.
Dois documentos com o mesmo texto e a mesma formatacao so' sao iguais depois de
normalizados: o Qt e o XML podem dividir o mesmo texto em runs diferentes.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from typing import Literal

Alinhamento = Literal["esquerda", "centro", "direita", "justificado"]
Numeracao = Literal["marcadores", "numeracao"]


@dataclass
class Run:
    texto: str = ""
    negrito: bool | None = None
    italico: bool | None = None
    sublinhado: bool | None = None
    tachado: bool | None = None
    subscrito: bool | None = None
    sobrescrito: bool | None = None
    tamanho_meio_pt: int | None = None  # 24 = 12 pt
    fonte: str | None = None
    cor_hex: str | None = None  # "RRGGBB", sem '#', em maiusculas


@dataclass
class Paragrafo:
    runs: list[Run] = field(default_factory=list)
    alinhamento: Alinhamento | None = None
    recuo_esquerdo_tw: int | None = None
    # Positivo = recuo da primeira linha; negativo = deslocamento suspenso.
    recuo_primeira_linha_tw: int | None = None
    espaco_antes_tw: int | None = None
    espaco_depois_tw: int | None = None
    numeracao: Numeracao | None = None
    # Porcentagem (100 = simples). Ausente no plano original; entrou no M2 porque
    # o editor ja aplica o espacamento e salvar sem ele perderia a formatacao.
    espacamento_linha_pct: int | None = None


@dataclass
class Documento:
    paragrafos: list[Paragrafo] = field(default_factory=list)
    titulo: str = ""
    autor: str = ""
    criado_em: str | None = None  # ISO 8601 UTC, ex. "2026-10-11T12:00:00Z"
    modificado_em: str | None = None


def _formato_de(run: Run) -> tuple:
    """Tudo o que define a aparencia do run, menos o texto."""
    return tuple(getattr(run, f.name) for f in fields(Run) if f.name != "texto")


def normalizar(documento: Documento) -> Documento:
    """Copia do documento com runs vizinhos fundidos e runs vazios descartados."""
    saida = copy.deepcopy(documento)
    for paragrafo in saida.paragrafos:
        fundidos: list[Run] = []
        for run in paragrafo.runs:
            if run.texto == "":
                continue
            if fundidos and _formato_de(fundidos[-1]) == _formato_de(run):
                fundidos[-1].texto += run.texto
            else:
                fundidos.append(run)
        paragrafo.runs = fundidos
    return saida
