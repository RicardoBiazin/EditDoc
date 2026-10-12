"""Geometria das folhas e do zoom, sem Qt.

Coordenadas do documento: twips, origem no canto superior esquerdo do CORPO da
primeira pagina. A pagina n ocupa a faixa vertical [n*hb, (n+1)*hb), onde hb e' a
altura do corpo. Coordenadas da tela: pixels logicos do viewport, com a rolagem
ja descontada.

Escala: zoom 1,0 = 100%, e' 1 px logico por 15 twips (96 dpi).

O teto de zoom depende da tela (ver `teto_de_zoom`): o Qt pinta texto por
caminho, e muito mais devagar, quando a escala total passa do limite de
ESCALA_DISPOSITIVO_MAXIMA. Medido no Gate do M3 (docs/SPIKES.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from editdoc.modelo.pagina import Pagina

ZOOM_MINIMO = 0.25
ZOOM_MAXIMO = 4.0
#: Escala total na tela (zoom x DPR). Acima disto o Qt pinta o texto por caminho quando a
#: fonte e' grande: com 14 pt a 300% a digitacao fica em 6 ms (p95); com 16 pt, em 24 ms.
#: Medido no Gate do M3 (docs/SPIKES.md). Com fonte de ate 14 pt, o teto cobre o texto.
ESCALA_DISPOSITIVO_MAXIMA = 3.0
#: Passos do controle de zoom; o teto da tela entra como ultimo passo.
PASSOS_DE_ZOOM = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0)
#: Vao entre folhas a 100%, em pixels logicos.
VAO_ENTRE_FOLHAS_PX = 24.0
#: Margem entre a folha e a borda do viewport, em pixels logicos.
MARGEM_DO_PAINEL_PX = 24.0
#: Um passo de roda: 3 linhas de 40 px, em pixels de tela, sem escala de zoom.
PASSO_DA_RODA_PX = 40
LINHAS_DA_RODA = 3


def teto_de_zoom(dpr: float) -> float:
    """Maior zoom permitido numa tela de DPR `dpr`, truncado a centesimos.

    DPR 1 -> 3,00; DPR 1,25 -> 2,40; DPR 1,5 -> 2,00; DPR 2 -> 1,50. Nunca abaixo do minimo.
    """
    teto = min(ZOOM_MAXIMO, ESCALA_DISPOSITIVO_MAXIMA / max(float(dpr), 1.0))
    return max(ZOOM_MINIMO, math.floor(teto * 100 + 1e-9) / 100)


def limitar_zoom(zoom: float, dpr: float) -> float:
    return min(max(float(zoom), ZOOM_MINIMO), teto_de_zoom(dpr))


def passo_de_zoom(zoom: float, aumentar: bool, dpr: float) -> float:
    """Proximo passo do controle, respeitando o teto da tela."""
    teto = teto_de_zoom(dpr)
    passos = sorted(set([p for p in PASSOS_DE_ZOOM if p <= teto] + [teto]))
    if aumentar:
        acima = [p for p in passos if p > zoom + 1e-9]
        return acima[0] if acima else teto
    abaixo = [p for p in passos if p < zoom - 1e-9]
    return abaixo[-1] if abaixo else ZOOM_MINIMO


def alinhar_ao_dispositivo(valor: float, dpr: float) -> float:
    """Arredonda uma coordenada logica para o pixel de dispositivo mais proximo.

    Bordas de folha em fracao de pixel saem borradas. Com DPR 1,5 o passo e' 2/3 de
    pixel logico; com DPR 2, meio pixel.
    """
    return round(valor * dpr) / dpr


def escala_do_zoom(zoom: float) -> float:
    """Pixels logicos por twip."""
    return zoom / 15.0


@dataclass
class Mapa:
    """Converte entre documento (twips) e tela (px logicos) para uma pagina e um zoom."""

    pagina: Pagina
    zoom: float
    largura_viewport: float
    altura_viewport: float
    origem_x: float = 0.0
    origem_y: float = 0.0

    @property
    def escala(self) -> float:
        return escala_do_zoom(self.zoom)

    @property
    def hb(self) -> float:
        """Altura de uma pagina de corpo, em twips."""
        return float(self.pagina.corpo_altura_tw())

    @property
    def vao(self) -> float:
        return VAO_ENTRE_FOLHAS_PX * self.zoom

    @property
    def passo_vertical(self) -> float:
        """Distancia entre o topo de uma folha e o topo da seguinte, em px logicos."""
        return self.pagina.altura_tw * self.escala + self.vao

    @property
    def largura_folha(self) -> float:
        return self.pagina.largura_tw * self.escala

    @property
    def altura_folha(self) -> float:
        return self.pagina.altura_tw * self.escala

    @property
    def esquerda_folha(self) -> float:
        """X da folha no conteudo, sem rolagem. Centralizada quando cabe no viewport."""
        largura = max(self.largura_folha + 2 * MARGEM_DO_PAINEL_PX, self.largura_viewport)
        return (largura - self.largura_folha) / 2.0

    def pagina_de_y(self, y_doc: float, paginas: int) -> int:
        """Pagina do ponto de documento, limitada a [0, paginas - 1]."""
        n = math.floor(y_doc / self.hb)
        return min(max(n, 0), max(paginas - 1, 0))

    def folha_na_tela(self, n: int) -> tuple[float, float, float, float]:
        """(x, y, largura, altura) da folha n em px logicos do viewport."""
        return (self.esquerda_folha - self.origem_x,
                self.vao + n * self.passo_vertical - self.origem_y,
                self.largura_folha, self.altura_folha)

    def doc_para_tela(self, x_doc: float, y_doc: float, paginas: int) -> tuple[float, float]:
        n = self.pagina_de_y(y_doc, paginas)
        cfg = self.pagina
        tx = x_doc + cfg.margem_esq_tw
        ty = y_doc - n * self.hb + cfg.margem_sup_tw
        x = self.esquerda_folha + tx * self.escala - self.origem_x
        y = self.vao + n * self.passo_vertical + ty * self.escala - self.origem_y
        return x, y

    def tela_para_doc(self, x_tela: float, y_tela: float, paginas: int) -> tuple[float, float]:
        """Inversa de `doc_para_tela` para um ponto dentro da faixa da pagina."""
        cfg = self.pagina
        cx = x_tela + self.origem_x - self.esquerda_folha
        cy = y_tela + self.origem_y
        n = int(math.floor((cy - self.vao) / self.passo_vertical))
        n = min(max(n, 0), max(paginas - 1, 0))
        sy = cy - (self.vao + n * self.passo_vertical)
        tx = cx / self.escala
        ty = sy / self.escala
        return tx - cfg.margem_esq_tw, ty - cfg.margem_sup_tw + n * self.hb

    def altura_total(self, paginas: int) -> float:
        return self.vao + paginas * self.passo_vertical
