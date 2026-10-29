"""Geometria das folhas e do zoom, sem Qt.

Coordenadas do documento: twips, origem no canto superior esquerdo do CORPO da
primeira pagina. A pagina n ocupa a faixa vertical [n*hb, (n+1)*hb), onde hb e' a
altura do corpo. Coordenadas da tela: pixels logicos do viewport, com a rolagem
ja descontada.

Escala: zoom 1,0 = 100%, e' 1 px logico por 15 twips (96 dpi).

Colunas (M6, "Varias paginas"): com `colunas` > 1 as folhas ficam lado a lado, em
linhas; a pagina n fica na linha n // colunas e na coluna n % colunas. O documento
continua o mesmo: so' muda onde cada folha aparece na tela.

O teto de zoom depende da tela (ver `teto_de_zoom`): o Qt pinta texto por
caminho, e muito mais devagar, quando a escala total passa do limite de
ESCALA_DISPOSITIVO_MAXIMA. Medido no Gate do M3 (docs/SPIKES.md).

Secoes (0.1.12): cada folha pode ter o seu papel (`folhas`: n -> a pagina efetiva da folha, com
papel, margens e topo do corpo). A pagina do documento continua sendo a faixa [n*hb, (n+1)*hb),
com hb a maior altura de corpo (`hb_documento`). Folhas de tamanhos diferentes ficam uma
embaixo da outra, cada uma centrada; lado a lado, a linha tem a altura da maior folha dela.
Sem `folhas`, as contas sao as de sempre (todas iguais a `pagina`).

Folha x pagina do Qt (0.1.20): `MapaFolhas` e' a unica camada que converte y em folha e
folha em faixa do documento. Hoje a folha n e' a pagina n do QTextDocument; quem precisa
de `n * hb` ou de `floor(y / hb)` usa a camada, para a identidade ficar num lugar so'.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Callable
from dataclasses import dataclass, replace

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


@dataclass(frozen=True)
class GrupoDeColunas:
    """Uma secao de colunas iguais (colunas, passo 2): `paginas` paginas do Qt a partir de
    `pagina`, `colunas` por folha, lado a lado. A pagina do Qt tem a largura da coluna
    (`largura`, twips); a coluna c fica `c * passo` twips a direita da margem esquerda."""

    pagina: int
    paginas: int
    colunas: int
    passo: float
    largura: float
    separador: bool = False
    #: primeira folha do grupo (preenchida por `MapaFolhas.definir_grupos`)
    folha: int = 0

    @property
    def folhas(self) -> int:
        return -(-self.paginas // self.colunas)


class MapaFolhas:
    """Folha x pagina do QTextDocument (0.1.20, passo 1 das colunas: docs/SPIKES.md, 0.1.19).

    Folha: a pagina impressa ou visivel, com o cabecalho, o rodape e as margens da secao dela.
    Pagina do Qt: a unidade de paginacao do QTextDocument, a faixa [n*h, (n+1)*h) do documento,
    com h a altura de uma pagina (`altura`). Sem colunas as duas coincidem: a folha n e' a
    pagina n do Qt. Quem converte y em folha ou folha em faixa passa por esta classe, nunca por
    `n * hb` nem por `floor(y / hb)`.

    Colunas (passo 2): numa secao de N colunas iguais (`GrupoDeColunas`), a pagina do Qt e' uma
    coluna e a folha junta N paginas do Qt lado a lado. `topo(p)` e `fim(p)` continuam sendo a
    faixa da PAGINA DO QT p; a folha n mostra as paginas `paginas_da_folha(n)`, a coluna de cada
    uma deslocada `deslocamento(p)` twips. Sem grupos, tudo e' a identidade de antes.

    Sem Qt. `altura` e' chamada a cada conta, porque a altura muda com as secoes.
    """

    def __init__(self, altura: Callable[[], float]) -> None:
        self._altura = altura
        self._grupos: tuple[GrupoDeColunas, ...] = ()
        self._paginas_dos_grupos: list[int] = []

    @classmethod
    def de_altura(cls, altura: float) -> MapaFolhas:
        """Mapa de uma altura que nao muda durante a conta."""
        return cls(lambda: altura)

    @property
    def hb(self) -> float:
        return float(self._altura())

    # -- colunas (passo 2) ---------------------------------------------------------------------
    @property
    def grupos(self) -> tuple[GrupoDeColunas, ...]:
        return self._grupos

    def tem_colunas(self) -> bool:
        return bool(self._grupos)

    def definir_grupos(self, grupos) -> bool:
        """Troca os grupos de colunas (em ordem de pagina, sem sobreposicao). True se mudou."""
        novos: list[GrupoDeColunas] = []
        extra = 0  # folhas a menos que paginas, dos grupos anteriores
        for g in sorted(grupos, key=lambda g: g.pagina):
            if g.paginas <= 0 or g.colunas <= 1:
                continue
            if novos and g.pagina < novos[-1].pagina + novos[-1].paginas:
                continue
            g = replace(g, folha=g.pagina - extra)
            extra += g.paginas - g.folhas
            novos.append(g)
        novos_t = tuple(novos)
        if novos_t == self._grupos:
            return False
        self._grupos = novos_t
        self._paginas_dos_grupos = [g.pagina for g in novos_t]
        return True

    def _grupo_da_pagina(self, p: int):
        """(grupo, dentro): o ultimo grupo que comeca ate' a pagina p, e se p esta' nele."""
        i = bisect.bisect_right(self._paginas_dos_grupos, p) - 1
        if i < 0:
            return None, False
        g = self._grupos[i]
        return g, p < g.pagina + g.paginas

    def grupo_da_pagina(self, p: int) -> GrupoDeColunas | None:
        if not self._grupos:
            return None
        g, dentro = self._grupo_da_pagina(int(p))
        return g if dentro else None

    def coluna_da_pagina(self, p: int) -> int:
        """Indice da coluna (0 = a da esquerda) da pagina do Qt p na folha dela."""
        g = self.grupo_da_pagina(p)
        return (int(p) - g.pagina) % g.colunas if g is not None else 0

    def deslocamento(self, p: int) -> float:
        """Quanto a pagina do Qt p fica a direita da margem esquerda da folha (twips)."""
        g = self.grupo_da_pagina(p)
        return ((int(p) - g.pagina) % g.colunas) * g.passo if g is not None else 0.0

    def paginas_da_folha(self, n: int) -> range:
        """As paginas do Qt da folha n, da coluna da esquerda para a direita (as que existem ou
        existiriam: a ultima folha do grupo pode ter menos)."""
        n = int(n)
        if not self._grupos:
            return range(n, n + 1)
        antes = 0  # folhas a menos que paginas ate' aqui
        for g in self._grupos:
            if n < g.folha:
                break
            if n < g.folha + g.folhas:
                p0 = g.pagina + (n - g.folha) * g.colunas
                return range(p0, min(p0 + g.colunas, g.pagina + g.paginas))
            antes += g.paginas - g.folhas
        return range(n + antes, n + antes + 1)

    def primeira_pagina(self, n: int) -> int:
        return self.paginas_da_folha(n).start

    def topo_da_folha(self, n: int) -> float:
        """Y do topo da faixa da primeira pagina do Qt da folha n."""
        return self.topo(self.primeira_pagina(n))

    def colunas_da_folha(self, n: int) -> list[tuple[int, float, float | None]]:
        """[(pagina do Qt, deslocamento, largura da coluna ou None)] da folha n. Sem colunas,
        [(n, 0, None)]."""
        if not self._grupos:
            return [(int(n), 0.0, None)]
        paginas = self.paginas_da_folha(n)
        g = self.grupo_da_pagina(paginas.start)
        if g is None:
            return [(paginas.start, 0.0, None)]
        return [(p, (p - g.pagina) % g.colunas * g.passo, g.largura) for p in paginas]

    def coluna_no_x(self, n: int, x: float) -> int:
        """Pagina do Qt da folha n cuja coluna contem o x (twips do corpo, a partir da margem
        esquerda); fora das colunas, a mais perto."""
        cols = self.colunas_da_folha(n)
        if len(cols) == 1 or cols[0][2] is None:
            return cols[0][0]
        largura = cols[0][2]
        escolhida = cols[0][0]
        for p, dx, _w in cols:
            vao = (cols[1][1] - largura) if len(cols) > 1 else 0.0
            if x >= dx - vao / 2.0:
                escolhida = p
        return escolhida

    # -- faixas ---------------------------------------------------------------------------------
    def topo(self, n: int) -> float:
        """Y do topo da faixa da pagina do Qt n, no documento (sem colunas, a da folha n)."""
        return n * self.hb

    def fim(self, n: int) -> float:
        """Y do fim da faixa da pagina do Qt n."""
        return (n + 1) * self.hb

    def pagina_de_y(self, y: float, folga: float = 0.0) -> int:
        """Pagina do Qt do ponto y, sem limite. `folga` (1e-6) soma antes do piso: o ponto
        exatamente na divisa conta como da pagina de baixo, como antes."""
        return math.floor(y / self.hb + folga)

    def folha_de_y(self, y: float, folhas: int) -> int:
        """Folha do ponto y, limitada a [0, folhas - 1]."""
        if self._grupos:
            return min(max(self.folha_da_pagina(self.pagina_de_y(y)), 0), max(folhas - 1, 0))
        return min(max(self.pagina_de_y(y), 0), max(folhas - 1, 0))

    def folha_da_pagina(self, pagina: int) -> int:
        """Folha formada pela pagina do Qt (sem colunas, a mesma)."""
        if not self._grupos:
            return pagina
        g, dentro = self._grupo_da_pagina(int(pagina))
        if g is None:
            return pagina
        if dentro:
            return g.folha + (int(pagina) - g.pagina) // g.colunas
        return g.folha + g.folhas + (int(pagina) - g.pagina - g.paginas)

    def folhas_de_paginas(self, paginas: int) -> int:
        """Quantas folhas `paginas` paginas do Qt formam."""
        if not self._grupos or paginas <= 0:
            return paginas
        return self.folha_da_pagina(paginas - 1) + 1


@dataclass
class Mapa:
    """Converte entre documento (twips) e tela (px logicos) para uma pagina e um zoom."""

    pagina: Pagina
    zoom: float
    largura_viewport: float
    altura_viewport: float
    origem_x: float = 0.0
    origem_y: float = 0.0
    colunas: int = 1
    #: Topo do corpo na folha n, em twips (0.1.8): o cabecalho de cada pagina empurra o corpo
    #: dela. None = o `margem_sup_tw` da pagina, igual em todas.
    topo_da_pagina: Callable[[int], float] | None = None
    #: Secoes (0.1.12): n -> pagina efetiva da folha n (papel e margens); None = todas `pagina`.
    folhas: Callable[[int], Pagina] | None = None
    #: Altura de uma pagina do documento (a maior entre as secoes); None = a do corpo de `pagina`.
    hb_documento: float | None = None
    #: Colunas (passo 2): a camada do layout, com os grupos de colunas. None = identidade.
    camada: MapaFolhas | None = None

    def topo(self, n: int) -> float:
        if self.topo_da_pagina is not None:
            return float(self.topo_da_pagina(n))
        return float(self.pagina.margem_sup_tw)

    def pagina_da(self, n: int) -> Pagina:
        return self.folhas(n) if self.folhas is not None else self.pagina

    @property
    def escala(self) -> float:
        return escala_do_zoom(self.zoom)

    @property
    def hb(self) -> float:
        """Altura de uma pagina do documento, em twips."""
        if self.hb_documento is not None:
            return float(self.hb_documento)
        return float(self.pagina.corpo_altura_tw())

    @property
    def mapa_folhas(self) -> MapaFolhas:
        """A camada folha x pagina do Qt (0.1.20) sobre a altura desta geometria."""
        if self.camada is not None and self.camada.tem_colunas():
            return self.camada
        return MapaFolhas(lambda: self.hb)

    def _com_colunas(self) -> bool:
        return self.camada is not None and self.camada.tem_colunas()

    # -- folhas de tamanhos diferentes (0.1.12) -------------------------------------------------
    def _disposicao(self, paginas: int):
        """(x relativo a' esquerda do conteudo, y) de cada folha, as alturas das linhas e a largura
        do conteudo, para `paginas` folhas. Guardado no proprio mapa."""
        guardado = getattr(self, "_disp", None)
        if guardado is not None and guardado[0] == paginas:
            return guardado[1]
        colunas = max(1, int(self.colunas))
        e = self.escala
        tamanhos = [(self.pagina_da(n).largura_tw * e, self.pagina_da(n).altura_tw * e)
                    for n in range(max(paginas, 1))]
        linhas = [tamanhos[i:i + colunas] for i in range(0, len(tamanhos), colunas)]
        larguras = [sum(w for w, _h in linha) + (len(linha) - 1) * self.vao for linha in linhas]
        conteudo = max(larguras, default=self.largura_folha)
        ys, alturas = [], []
        y = self.vao
        posicoes = []
        for linha, largura in zip(linhas, larguras):
            altura = max(h for _w, h in linha)
            ys.append(y)
            alturas.append(altura)
            x = (conteudo - largura) / 2.0
            for w, _h in linha:
                posicoes.append((x, y))
                x += w + self.vao
            y += altura + self.vao
        disp = (posicoes, ys, alturas, conteudo, tamanhos, y)
        self._disp = (paginas, disp)
        return disp

    def _paginas_dispostas(self) -> int:
        return getattr(self, "_paginas_conhecidas", 1)

    def preparar(self, paginas: int) -> "Mapa":
        """Diz quantas folhas o documento tem (com `folhas`, as contas precisam)."""
        self._paginas_conhecidas = max(1, int(paginas))
        return self

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
    def passo_horizontal(self) -> float:
        """Distancia entre a esquerda de uma coluna de folhas e a da seguinte."""
        return self.largura_folha + self.vao

    @property
    def largura_conteudo(self) -> float:
        """Largura das folhas de uma linha, com os vaos entre elas."""
        if self.folhas is not None:
            return self._disposicao(self._paginas_dispostas())[3]
        n = max(1, int(self.colunas))
        return n * self.largura_folha + (n - 1) * self.vao

    @property
    def esquerda_folha(self) -> float:
        """X da primeira folha da linha, sem rolagem. Centralizada quando cabe no viewport."""
        largura = max(self.largura_conteudo + 2 * MARGEM_DO_PAINEL_PX, self.largura_viewport)
        return (largura - self.largura_conteudo) / 2.0

    def _linha_coluna(self, n: int) -> tuple[int, int]:
        return divmod(max(int(n), 0), max(1, int(self.colunas)))

    def pagina_no_ponto(self, x_tela: float, y_tela: float, paginas: int) -> int:
        """Pagina cuja faixa (linha e coluna) contem o ponto da tela, limitada ao documento."""
        if self.folhas is not None:
            posicoes, ys, alturas, _c, tamanhos, _fim = self._disposicao(paginas)
            cy = y_tela + self.origem_y
            linha = max(0, bisect.bisect_right(ys, cy + self.vao / 2.0) - 1)
            colunas = max(1, int(self.colunas))
            cx = x_tela + self.origem_x - self.esquerda_folha
            primeira = linha * colunas
            melhor = primeira
            for n in range(primeira, min(primeira + colunas, len(posicoes))):
                if cx >= posicoes[n][0] - self.vao / 2.0:
                    melhor = n
            return min(max(melhor, 0), max(paginas - 1, 0))
        cy = y_tela + self.origem_y
        linha = max(0, int(math.floor((cy - self.vao) / self.passo_vertical)))
        colunas = max(1, int(self.colunas))
        cx = x_tela + self.origem_x - self.esquerda_folha
        coluna = int(math.floor((cx + self.vao / 2.0) / self.passo_horizontal)) if colunas > 1 else 0
        coluna = min(max(coluna, 0), colunas - 1)
        return min(max(linha * colunas + coluna, 0), max(paginas - 1, 0))

    def paginas_visiveis(self, paginas: int) -> tuple[int, int]:
        """(primeira, ultima) pagina que pode aparecer no viewport."""
        colunas = max(1, int(self.colunas))
        if self.folhas is not None:
            _p, ys, alturas, _c, _t, _fim = self._disposicao(paginas)
            l0 = max(0, bisect.bisect_right(ys, self.origem_y) - 1)
            l1 = max(0, bisect.bisect_right(ys, self.origem_y + self.altura_viewport) - 1)
            return l0 * colunas, min(paginas - 1, (l1 + 1) * colunas - 1)
        l0 = max(0, math.floor((self.origem_y - self.vao) / self.passo_vertical))
        l1 = math.floor((self.origem_y + self.altura_viewport - self.vao) / self.passo_vertical) + 1
        return l0 * colunas, min(paginas - 1, (l1 + 1) * colunas - 1)

    def pagina_de_y(self, y_doc: float, paginas: int) -> int:
        """Pagina do ponto de documento, limitada a [0, paginas - 1]."""
        if self._com_colunas():
            return self.camada.folha_de_y(y_doc, paginas)
        n = self.mapa_folhas.pagina_de_y(y_doc)
        return min(max(n, 0), max(paginas - 1, 0))

    def folha_na_tela(self, n: int) -> tuple[float, float, float, float]:
        """(x, y, largura, altura) da folha n em px logicos do viewport."""
        if self.folhas is not None:
            disp = self._disposicao(max(self._paginas_dispostas(), int(n) + 1))
            posicoes, tamanhos = disp[0], disp[4]
            n = min(max(int(n), 0), len(posicoes) - 1)
            x, y = posicoes[n]
            w, h = tamanhos[n]
            return self.esquerda_folha + x - self.origem_x, y - self.origem_y, w, h
        linha, coluna = self._linha_coluna(n)
        return (self.esquerda_folha + coluna * self.passo_horizontal - self.origem_x,
                self.vao + linha * self.passo_vertical - self.origem_y,
                self.largura_folha, self.altura_folha)

    def doc_para_tela(self, x_doc: float, y_doc: float, paginas: int) -> tuple[float, float]:
        if self._com_colunas():
            return self._doc_para_tela_colunas(x_doc, y_doc, paginas)
        n = self.pagina_de_y(y_doc, paginas)
        cfg = self.pagina_da(n)
        tx = x_doc + cfg.margem_esq_tw
        ty = y_doc - self.mapa_folhas.topo(n) + self.topo(n)
        x0, y0, _l, _a = self.folha_na_tela(n)
        return x0 + tx * self.escala, y0 + ty * self.escala

    def tela_para_doc(self, x_tela: float, y_tela: float, paginas: int) -> tuple[float, float]:
        """Inversa de `doc_para_tela` para um ponto dentro da faixa da pagina."""
        n = self.pagina_no_ponto(x_tela, y_tela, paginas)
        cfg = self.pagina_da(n)
        x0, y0, _l, _a = self.folha_na_tela(n)
        tx = (x_tela - x0) / self.escala
        ty = (y_tela - y0) / self.escala
        if self._com_colunas():
            # Colunas (passo 2): a coluna sob o x escolhe a pagina do Qt da folha.
            camada = self.camada
            x_corpo = tx - cfg.margem_esq_tw
            p = camada.coluna_no_x(n, x_corpo)
            return x_corpo - camada.deslocamento(p), ty - self.topo(n) + camada.topo(p)
        return tx - cfg.margem_esq_tw, ty - self.topo(n) + self.mapa_folhas.topo(n)

    def _doc_para_tela_colunas(self, x_doc: float, y_doc: float,
                               paginas: int) -> tuple[float, float]:
        """Colunas (passo 2): a pagina do Qt do y da' a folha e a coluna (o deslocamento em x)."""
        camada = self.camada
        p = camada.pagina_de_y(y_doc)
        n = min(max(camada.folha_da_pagina(p), 0), max(paginas - 1, 0))
        if camada.folha_da_pagina(p) != n:
            p = camada.primeira_pagina(n)  # fora do documento: a primeira coluna da folha
        cfg = self.pagina_da(n)
        tx = x_doc + cfg.margem_esq_tw + camada.deslocamento(p)
        ty = y_doc - camada.topo(p) + self.topo(n)
        x0, y0, _l, _a = self.folha_na_tela(n)
        return x0 + tx * self.escala, y0 + ty * self.escala

    def altura_total(self, paginas: int) -> float:
        if self.folhas is not None:
            return self._disposicao(paginas)[5]
        linhas = math.ceil(max(paginas, 0) / max(1, int(self.colunas)))
        return self.vao + linhas * self.passo_vertical

    def y_da_linha(self, linha: int) -> float:
        """Topo da linha de folhas (sem rolagem), em px logicos."""
        if self.folhas is not None:
            ys = self._disposicao(self._paginas_dispostas())[1]
            return ys[min(max(0, linha), len(ys) - 1)] if ys else self.vao
        return self.vao + linha * self.passo_vertical
