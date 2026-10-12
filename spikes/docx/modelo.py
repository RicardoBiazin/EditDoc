"""Modelo intermediario do spike B: dataclasses puras (sem Qt, sem lxml).

Convencao tri-state: None = "herda" (o arquivo nao diz nada); False = "desligado
explicitamente". None nunca e tratado como False.

Unidades: tamanho em meio-ponto (w:sz); recuos e espacos em twips (1/20 pt).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Alinhamento = Literal["esquerda", "centro", "direita", "justificado"]


@dataclass
class Run:
    texto: str = ""
    negrito: bool | None = None
    italico: bool | None = None
    sublinhado: bool | None = None
    tamanho_pt_meio: int | None = None  # 24 = 12 pt
    fonte: str | None = None
    cor_hex: str | None = None  # "RRGGBB", sem '#'


@dataclass
class Paragrafo:
    runs: list[Run] = field(default_factory=list)
    alinhamento: Alinhamento | None = None
    recuo_esquerdo_tw: int | None = None
    # positivo = recuo da primeira linha (w:firstLine); negativo = deslocamento suspenso (w:hanging)
    recuo_primeira_linha_tw: int | None = None
    espaco_antes_tw: int | None = None
    espaco_depois_tw: int | None = None


@dataclass
class Documento:
    paragrafos: list[Paragrafo] = field(default_factory=list)
    titulo: str = ""
    autor: str = ""
    criado_em: str | None = None  # ISO 8601 UTC, ex. "2026-10-11T12:00:00Z"; None = agora ao gravar
    modificado_em: str | None = None
