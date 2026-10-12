"""Modelo do documento: dados puros, sem Qt e sem lxml.

Convencao tri-state, em todos os campos opcionais: None = "herda" (o arquivo nao
diz nada); False ou 0 = "desligado" de forma explicita. None nunca vira False.

Unidades: tamanho em meio-ponto (`w:sz`); recuos e espacos em twips (1/20 de
ponto). Espacamento entre linhas em porcentagem (100 = simples). Imagens em EMU
(914400 por polegada). Bordas em oitavos de ponto (`w:sz` de borda).

Estrutura (M4): `Documento.paragrafos` e' a lista dos blocos do corpo, na ordem do
arquivo. Cada bloco e' um `Paragrafo` ou uma `Tabela` (o nome do campo vem do M2,
quando so' havia paragrafo). Uma celula de tabela tem os seus proprios blocos, e
pode conter outra tabela.

Imagem na linha do texto: um `Run` com `imagem` e o texto CARACTERE_OBJETO
(U+FFFC, o mesmo caractere que o Qt usa para o objeto). Assim o texto do
paragrafo conta a imagem, e a conferencia do arquivo gravado ve a imagem sumir.

`normalizar` funde runs vizinhos de mesma formatacao e descarta runs vazios.
Dois documentos com o mesmo texto e a mesma formatacao so' sao iguais depois de
normalizados: o Qt e o XML podem dividir o mesmo texto em runs diferentes. Ela
tambem deixa a tabela na forma que o Word exige: toda celula termina em
paragrafo, e o corpo nao termina em tabela.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from typing import Literal, Union

from editdoc.modelo.pagina import Pagina

Alinhamento = Literal["esquerda", "centro", "direita", "justificado"]
Numeracao = Literal["marcadores", "numeracao"]
EstiloBorda = Literal["simples", "dupla", "pontilhada", "tracejada", "nenhuma"]

#: Caractere que ocupa o lugar da imagem no texto (o Qt usa o mesmo).
CARACTERE_OBJETO = chr(0xFFFC)


@dataclass
class Imagem:
    """Imagem na linha do texto. `dados` sao os bytes originais, intocados."""
    dados: bytes
    formato: str  # "png", "jpeg", "gif" ou "bmp" (modelo/imagem.py)
    largura_emu: int
    altura_emu: int
    descricao: str = ""  # texto alternativo (wp:docPr descr)


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
    # Run de imagem: texto == CARACTERE_OBJETO e a formatacao de texto nao se aplica.
    imagem: Imagem | None = None


def run_de_imagem(imagem: Imagem) -> Run:
    return Run(texto=CARACTERE_OBJETO, imagem=imagem)


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
    # Quebra de pagina antes deste paragrafo (Ctrl+Enter). No .docx ela e' um
    # w:br type="page" no inicio do paragrafo. Ausente = sem quebra.
    quebra_antes: bool = False


@dataclass
class Borda:
    estilo: EstiloBorda = "simples"
    oitavos_pt: int = 4  # 4 = 0,5 pt, a borda padrao do Word
    cor_hex: str | None = None  # None = automatica (preta)


@dataclass
class BordasTabela:
    """Bordas da tabela inteira: as quatro de fora e as de dentro (entre celulas)."""
    sup: Borda | None = None
    inf: Borda | None = None
    esq: Borda | None = None
    dir: Borda | None = None
    horizontal: Borda | None = None  # w:insideH
    vertical: Borda | None = None  # w:insideV


@dataclass
class BordasCelula:
    """Borda propria de uma celula, que vence a da tabela naquele lado."""
    sup: Borda | None = None
    inf: Borda | None = None
    esq: Borda | None = None
    dir: Borda | None = None


@dataclass
class Celula:
    blocos: list["Bloco"] = field(default_factory=list)
    colunas: int = 1  # w:gridSpan: quantas colunas da grade a celula ocupa
    # Mescla vertical (w:vMerge): "inicio" abre, "continua" e' coberta pela de cima.
    mescla_vertical: Literal["inicio", "continua"] | None = None
    bordas: BordasCelula | None = None
    sombreamento_hex: str | None = None  # cor de fundo, "RRGGBB"
    alinhamento_vertical: Literal["topo", "centro", "base"] | None = None


@dataclass
class Linha:
    celulas: list[Celula] = field(default_factory=list)
    cabecalho: bool = False  # w:tblHeader: repete no alto de cada pagina
    altura_tw: int | None = None  # w:trHeight (guardada; a tela nao aplica)
    altura_exata: bool = False  # hRule="exact"; senao, "atLeast"


@dataclass
class Tabela:
    linhas: list[Linha] = field(default_factory=list)
    colunas_tw: list[int] = field(default_factory=list)  # w:tblGrid
    bordas: BordasTabela | None = None
    alinhamento: Literal["esquerda", "centro", "direita"] | None = None
    recuo_tw: int | None = None  # w:tblInd
    # w:tblW como o arquivo diz: ("dxa", twips), ("pct", 50 avos de %) ou ("auto", 0).
    largura: tuple[str, int] | None = None
    layout_fixo: bool | None = None  # w:tblLayout type="fixed"
    # Margens internas padrao das celulas (w:tblCellMar), em twips: sup, esq, inf, dir.
    margens_celula_tw: tuple[int, int, int, int] | None = None


Bloco = Union[Paragrafo, Tabela]


@dataclass
class Documento:
    # Blocos do corpo: Paragrafo ou Tabela (ver a nota no topo do modulo).
    paragrafos: list[Bloco] = field(default_factory=list)
    pagina: Pagina = field(default_factory=Pagina)
    titulo: str = ""
    autor: str = ""
    criado_em: str | None = None  # ISO 8601 UTC, ex. "2026-10-11T12:00:00Z"
    modificado_em: str | None = None


def _formato_de(run: Run) -> tuple:
    """Tudo o que define a aparencia do run, menos o texto."""
    return tuple(getattr(run, f.name) for f in fields(Run) if f.name != "texto")


def _normalizar_paragrafo(paragrafo: Paragrafo) -> None:
    fundidos: list[Run] = []
    for run in paragrafo.runs:
        if run.imagem is not None:
            # Imagem nunca funde: duas imagens iguais lado a lado sao duas imagens.
            fundidos.append(run)
            continue
        if run.texto == "":
            continue
        anterior = fundidos[-1] if fundidos else None
        if anterior is not None and anterior.imagem is None and \
                _formato_de(anterior) == _formato_de(run):
            anterior.texto += run.texto
        else:
            fundidos.append(run)
    paragrafo.runs = fundidos


def bordas_padrao() -> BordasTabela:
    """As bordas do "Table Grid" do Word: linha simples de 0,5 pt em volta e por dentro.

    E' o que vale quando `Tabela.bordas` e' None (tabela criada no EditDoc).
    """
    return BordasTabela(sup=Borda(), inf=Borda(), esq=Borda(), dir=Borda(),
                        horizontal=Borda(), vertical=Borda())


def _normalizar_blocos(blocos: list[Bloco], em_celula: bool) -> None:
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            # Formas equivalentes no arquivo: o escritor grava sempre os seis lados da
            # borda e a largura (tblW), e so' grava o layout quando ele e' fixo.
            if bloco.bordas is None:
                bloco.bordas = bordas_padrao()
            if bloco.largura is None:
                bloco.largura = ("auto", 0)
            if not bloco.layout_fixo:
                bloco.layout_fixo = None
            for linha in bloco.linhas:
                for celula in linha.celulas:
                    _normalizar_blocos(celula.blocos, em_celula=True)
        else:
            _normalizar_paragrafo(bloco)
    # A forma que o Word exige: celula termina em paragrafo; o corpo tambem.
    if em_celula and (not blocos or isinstance(blocos[-1], Tabela)):
        blocos.append(Paragrafo())
    elif not em_celula and blocos and isinstance(blocos[-1], Tabela):
        blocos.append(Paragrafo())


def normalizar(documento: Documento) -> Documento:
    """Copia do documento com runs vizinhos fundidos, runs vazios descartados e as
    tabelas na forma canonica (celula e corpo terminam em paragrafo)."""
    saida = copy.deepcopy(documento)
    _normalizar_blocos(saida.paragrafos, em_celula=False)
    return saida


def paragrafos_de(blocos: list[Bloco]):
    """Todos os paragrafos, na ordem de leitura, inclusive os de dentro de tabela."""
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            for linha in bloco.linhas:
                for celula in linha.celulas:
                    yield from paragrafos_de(celula.blocos)
        else:
            yield bloco


def tabelas_de(blocos: list[Bloco]):
    """Todas as tabelas, inclusive as aninhadas, na ordem de leitura."""
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            yield bloco
            for linha in bloco.linhas:
                for celula in linha.celulas:
                    yield from tabelas_de(celula.blocos)


def colunas_da_linha(linha: Linha) -> int:
    return sum(max(1, c.colunas) for c in linha.celulas)
