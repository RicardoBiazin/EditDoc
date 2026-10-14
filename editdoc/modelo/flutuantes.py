"""Objetos flutuantes (0.1.7): onde o Word poe o objeto na pagina. Sem Qt e sem lxml.

O objeto flutuante (wp:anchor do DrawingML, ou VML com position:absolute) fica preso a um
paragrafo (a ancora), mas aparece numa posicao da pagina dada por:

- horizontal: `relativeFrom` (page, margin, column, character, leftMargin, rightMargin,
  insideMargin, outsideMargin) e um deslocamento (wp:posOffset, EMU) ou um alinhamento
  (wp:align: left, center, right, inside, outside);
- vertical: `relativeFrom` (page, margin, paragraph, line, topMargin, bottomMargin,
  insideMargin, outsideMargin) e deslocamento ou alinhamento (top, center, bottom, inside,
  outside);
- tamanho: wp:extent, ou a porcentagem do wp14:sizeRelH/sizeRelV quando ela existe;
- wp:simplePos (simplePos="1"): o canto do objeto direto em coordenadas da pagina.

A pagina do objeto e' a pagina onde esta' o paragrafo-ancora. A conta e' feita em twips, na
coordenada da folha (origem no canto superior esquerdo do papel), por `retangulo`. Quem chama
diz onde a ancora ficou (`Referencia`): o topo do paragrafo, o topo da linha, a coluna (a
celula de tabela, quando a ancora esta' numa) e o x do caractere.

Quebra de texto (`area_de_quebra`): o retangulo do objeto mais as distancias (distT/B/L/R) e o
effectExtent. wrapTight e wrapThrough sao tratados como wrapSquare (o contorno do poligono
nao e' seguido: limite registrado).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from editdoc.modelo.pagina import Pagina
from editdoc.modelo.unidades import EMU_POR_TWIP

#: Tipos de quebra de texto (wp:wrap*). "none" = sem quebra (na frente ou atras do texto).
QUEBRAS = ("none", "square", "tight", "through", "topbottom")
#: Os que reservam espaco ao lado ou acima e abaixo do objeto.
QUEBRAS_QUE_RESERVAM = ("square", "tight", "through", "topbottom")


@dataclass(frozen=True)
class Ancoragem:
    """A posicao e o tamanho de um objeto flutuante, como o arquivo diz. Medidas em EMU."""
    h_rel: str = "column"
    h_alinh: str | None = None
    h_desloc: int = 0
    #: wp14:pctPosHOffset (milesimos de por cento da referencia), quando o arquivo usa.
    h_pct: int | None = None
    v_rel: str = "paragraph"
    v_alinh: str | None = None
    v_desloc: int = 0
    v_pct: int | None = None
    #: wp:simplePos com simplePos="1": (x, y) do canto, na coordenada da pagina.
    simples: tuple | None = None
    largura: int = 0
    altura: int = 0
    #: wp14:pctWidth/pctHeight (em milesimos de por cento: 100000 = 100%) e a base.
    pct_largura: int = 0
    pct_largura_rel: str = "margin"
    pct_altura: int = 0
    pct_altura_rel: str = "margin"
    #: wp:effectExtent (l, t, r, b): sombra, brilho... que passam do tamanho.
    efeito: tuple = (0, 0, 0, 0)
    quebra: str = "none"
    #: wrapText: bothSides, left, right, largest.
    lado: str = "bothSides"
    #: distT, distB, distL, distR.
    dist: tuple = (0, 0, 0, 0)
    atras: bool = False
    #: Ordem z (relativeHeight, ou z-index do VML).
    z: int = 0
    na_celula: bool = True
    sobrepor: bool = True
    vml: bool = False

    def reserva_espaco(self) -> bool:
        return self.quebra in QUEBRAS_QUE_RESERVAM and not self.atras

    def lado_da_reserva(self, x0_tw: float, x1_tw: float, corpo_esq_tw: float,
                        corpo_dir_tw: float) -> str:
        """"esquerda" (o texto passa a direita do objeto) ou "direita". O Word com bothSides
        poe texto dos dois lados; aqui o texto fica do lado maior (limite registrado)."""
        if self.lado == "right":
            return "esquerda"
        if self.lado == "left":
            return "direita"
        livre_esq = x0_tw - corpo_esq_tw
        livre_dir = corpo_dir_tw - x1_tw
        return "esquerda" if livre_dir >= livre_esq else "direita"


@dataclass(frozen=True)
class Referencia:
    """Onde a ancora ficou, em twips na coordenada da folha.

    `indice` e' a pagina (a partir de 0): a pagina 0 e' impar (a primeira), e e' o que decide
    insideMargin e outsideMargin. `coluna_x`/`coluna_w`: a area de texto da coluna, ou da
    celula da tabela quando a ancora esta' numa (layoutInCell)."""
    pagina: Pagina
    indice: int = 0
    paragrafo_y: float = 0.0
    linha_y: float | None = None
    coluna_x: float | None = None
    coluna_w: float | None = None
    caractere_x: float | None = None


def _base_horizontal(rel: str, ref: Referencia, impar: bool) -> tuple[float, float]:
    """(x inicial, largura) da referencia horizontal, em twips da folha."""
    p = ref.pagina
    margem_esq = (0.0, float(p.margem_esq_tw))
    margem_dir = (float(p.largura_tw - p.margem_dir_tw), float(p.margem_dir_tw))
    if rel == "page":
        return 0.0, float(p.largura_tw)
    if rel == "margin":
        return float(p.margem_esq_tw), float(p.corpo_largura_tw())
    if rel == "leftMargin":
        return margem_esq
    if rel == "rightMargin":
        return margem_dir
    if rel == "insideMargin":
        return margem_esq if impar else margem_dir
    if rel == "outsideMargin":
        return margem_dir if impar else margem_esq
    if rel == "character" and ref.caractere_x is not None:
        return float(ref.caractere_x), 0.0
    # column (e o que nao se conhece): a coluna, ou a margem quando nao ha' coluna.
    if ref.coluna_x is not None:
        return float(ref.coluna_x), float(ref.coluna_w if ref.coluna_w is not None
                                          else p.corpo_largura_tw())
    return float(p.margem_esq_tw), float(p.corpo_largura_tw())


def _base_vertical(rel: str, ref: Referencia, impar: bool) -> tuple[float, float]:
    p = ref.pagina
    topo = (0.0, float(p.margem_sup_tw))
    base = (float(p.altura_tw - p.margem_inf_tw), float(p.margem_inf_tw))
    if rel == "page":
        return 0.0, float(p.altura_tw)
    if rel == "margin":
        return float(p.margem_sup_tw), float(p.corpo_altura_tw())
    if rel == "topMargin":
        return topo
    if rel == "bottomMargin":
        return base
    if rel == "insideMargin":
        return topo if impar else base
    if rel == "outsideMargin":
        return base if impar else topo
    if rel == "line" and ref.linha_y is not None:
        return float(ref.linha_y), 0.0
    # paragraph (e o que nao se conhece)
    return float(ref.paragrafo_y), 0.0


def tamanho_tw(anc: Ancoragem, ref: Referencia) -> tuple[float, float]:
    """(largura, altura) em twips: o wp:extent, ou a porcentagem do sizeRel quando ha'."""
    impar = ref.indice % 2 == 0
    largura = anc.largura / EMU_POR_TWIP
    altura = anc.altura / EMU_POR_TWIP
    if anc.pct_largura > 0:
        _x, w = _base_horizontal(anc.pct_largura_rel, ref, impar)
        largura = w * anc.pct_largura / 100000.0
    if anc.pct_altura > 0:
        _y, h = _base_vertical(anc.pct_altura_rel, ref, impar)
        altura = h * anc.pct_altura / 100000.0
    return max(largura, 0.0), max(altura, 0.0)


def retangulo(anc: Ancoragem, ref: Referencia) -> tuple[float, float, float, float]:
    """(x, y, largura, altura) do objeto, em twips na coordenada da folha."""
    largura, altura = tamanho_tw(anc, ref)
    if anc.simples is not None:
        return (anc.simples[0] / EMU_POR_TWIP, anc.simples[1] / EMU_POR_TWIP, largura, altura)
    impar = ref.indice % 2 == 0
    x0, w = _base_horizontal(anc.h_rel, ref, impar)
    alinh = anc.h_alinh
    if alinh == "inside":
        alinh = "left" if impar else "right"
    elif alinh == "outside":
        alinh = "right" if impar else "left"
    if alinh == "left":
        x = x0
    elif alinh == "right":
        x = x0 + w - largura
    elif alinh == "center":
        x = x0 + (w - largura) / 2.0
    elif anc.h_pct is not None:
        x = x0 + w * anc.h_pct / 100000.0
    else:
        x = x0 + anc.h_desloc / EMU_POR_TWIP
    y0, h = _base_vertical(anc.v_rel, ref, impar)
    alinh = anc.v_alinh
    if alinh == "inside":
        alinh = "top" if impar else "bottom"
    elif alinh == "outside":
        alinh = "bottom" if impar else "top"
    if alinh == "top":
        y = y0
    elif alinh == "bottom":
        y = y0 + h - altura
    elif alinh == "center":
        y = y0 + (h - altura) / 2.0
    elif anc.v_pct is not None:
        y = y0 + h * anc.v_pct / 100000.0
    else:
        y = y0 + anc.v_desloc / EMU_POR_TWIP
    return x, y, largura, altura


#: Limites de posicao e tamanho (0.1.9), em EMU. ST_PositionOffset e' xsd:int, mas o Word nao
#: aceita objeto a mais de 55,88 cm (22 polegadas) da referencia; ST_PositiveCoordinate vai de 0
#: a 27273042316900, e o teto razoavel e' o maior papel (176 cm). O menor lado e' 1 px96.
POSICAO_MAXIMA_EMU = 22 * 914400
TAMANHO_MAXIMO_EMU = 176 * 360000
TAMANHO_MINIMO_EMU = 9525


def limitar_posicao(emu: float) -> int:
    """Deslocamento (posOffset) dentro da faixa que o Word aceita."""
    return int(max(-POSICAO_MAXIMA_EMU, min(POSICAO_MAXIMA_EMU, round(emu))))


def limitar_tamanho(emu: float, zero: bool = False) -> int:
    """Lado do objeto (wp:extent): nunca negativo, nem acima do maior papel. `zero`: o lado era
    zero no arquivo (a linha reta tem cy="0") e continua zero."""
    if zero:
        return 0
    return int(max(TAMANHO_MINIMO_EMU, min(TAMANHO_MAXIMO_EMU, round(emu))))


def base(eixo: str, rel: str, ref: Referencia) -> float:
    """Origem (twips da folha) da referencia `rel` no eixo "h" ou "v" (0.1.9)."""
    impar = ref.indice % 2 == 0
    if eixo == "h":
        return _base_horizontal(rel, ref, impar)[0]
    return _base_vertical(rel, ref, impar)[0]


def deslocamento_para(eixo: str, rel: str, ref: Referencia, valor_tw: float) -> int:
    """posOffset (EMU) que poe o canto do objeto em `valor_tw` (twips da folha), relativo a
    `rel` (0.1.9): o caminho de volta de `retangulo`, para gravar a posicao nova."""
    return limitar_posicao((valor_tw - base(eixo, rel, ref)) * EMU_POR_TWIP)


def area_de_quebra(anc: Ancoragem, rect: tuple) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) que o texto contorna: o objeto, o effectExtent e as distancias."""
    x, y, w, h = rect
    el, et, er, eb = (v / EMU_POR_TWIP for v in anc.efeito)
    dt, db, dl, dr = (v / EMU_POR_TWIP for v in anc.dist)
    return (x - el - dl, y - et - dt, x + w + er + dr, y + h + eb + db)


@dataclass
class Posto:
    """Um objeto flutuante ja' posicionado numa pagina (o que a pintura usa)."""
    posicao: int  # no documento do Qt
    chave: str  # chave do objeto opaco no registro
    indice: int  # pagina
    rect: tuple  # (x, y, w, h) twips na folha
    z: int = 0
    atras: bool = False
    #: "corpo", "cabecalho" ou "rodape"
    historia: str = "corpo"
    extra: dict = field(default_factory=dict)


def ordem_de_pintura(postos: list[Posto]) -> list[Posto]:
    """Os de tras primeiro; em cada camada, pela ordem z (relativeHeight) e depois pela posicao."""
    return sorted(postos, key=lambda p: (not p.atras, p.z, p.posicao))
