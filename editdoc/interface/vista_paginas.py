"""Visao em folhas A4: desenha as paginas, faz a rolagem e o zoom. Nao edita.

A edicao (caret, teclado, mouse, desfazer) e' de PainelDocumento, que herda desta
classe. Aqui fica o que e' so' de pintura e de geometria.

Cada folha e' pintada pela mesma funcao (`desenhar_folha`) que o PDF e a impressora
usam (`interface/impressao.py`, M7), e o zoom so' muda a escala: nunca refaz o layout.

Cache de tiles (medido no Gate do M3, docs/SPIKES.md):
  - a folha e' cortada em tiles de TILE_PX pixels logicos, na coordenada da propria
    pagina; cada tile e' um QPixmap no DPR da tela;
  - uma mudanca no texto invalida so' os tiles tocados pela altura alterada; se a
    altura total do documento mudou, invalida tudo abaixo do ponto da mudanca;
  - o cache tem teto de memoria; zoom, DPR e configuracao de pagina limpam tudo;
  - com selecao, a folha e' pintada direto (a selecao nao e' cacheada).

Cabecalho e rodape (M5) nao entram no cache: sao pintados por cima dos tiles, em cada
pagina visivel (`desenhar_faixas`), porque o numero da pagina muda de folha para
folha. Fora da edicao saem esmaecidos (cinza claro), como no Word; na edicao, o
corpo e' que esmaece, e uma linha tracejada com rotulo marca a area.

Exibir (M6): marcas de formatacao (pilcrow, ponto no espaco, seta na tabulacao) sao
pintadas por cima do texto, na mesma funcao da folha, e entram no cache; ligar ou
desligar limpa o cache. Nao mudam o layout: o QTextOption do Qt com as marcas trocaria
a largura do texto e refaria a paginacao. "Varias paginas" poe as folhas lado a lado
(`Mapa.colunas`); os outros modos voltam a uma coluna.
"""

from __future__ import annotations

import math
from collections import OrderedDict

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QAbstractTextDocumentLayout, QColor, QPainter, QPalette,
                           QPen, QPixmap, QTextCharFormat, QTextCursor, QTextFormat,
                           QTransform)
from PySide6.QtWidgets import QAbstractScrollArea

from editdoc.interface.layout_paginado import LayoutPaginado
from editdoc.modelo.unidades import TWIPS_POR_PX
from editdoc.modelo.campos import tipo_da_pagina
from editdoc.modelo.pagina import Pagina
from editdoc.ponte_qt import comentarios as pq_comentarios
from editdoc.ponte_qt import listas as pq_listas
from editdoc.ponte_qt import propriedades as pq_props
from editdoc.modelo.folhas import (MARGEM_DO_PAINEL_PX, PASSO_DA_RODA_PX,
                                   VAO_ENTRE_FOLHAS_PX, Mapa, alinhar_ao_dispositivo,
                                   limitar_zoom, passo_de_zoom, teto_de_zoom)

TILE_PX = 256
LIMITE_DO_CACHE_BYTES = 64 * 1024 * 1024
PERIODO_DO_CARET_MS = 530

COR_FUNDO = QColor(0xB9, 0xBE, 0xC6)
COR_SOMBRA = QColor(0x80, 0x86, 0x90)
COR_FOLHA = QColor(255, 255, 255)
COR_SELECAO = QColor(0, 120, 215)
COR_CARET = QColor(0, 0, 0)
COR_QUEBRA = QColor(0x70, 0x76, 0x80)
#: Cabecalho e rodape fora da edicao: pintados com esta opacidade (cinza claro).
OPACIDADE_FAIXA = 0.45
#: Corpo durante a edicao do cabecalho: um veu branco por cima.
COR_VEU = QColor(255, 255, 255, 140)
COR_ROTULO_FAIXA = QColor(0x2B, 0x57, 0x9A)
#: Lado da alca de imagem desenhada, em px logicos.
ALCA_TELA_PX = 7.0
_QUEBRA_ANTES = QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore
#: Marcas de formatacao: a cor do Word.
COR_MARCAS = QColor(0x2B, 0x57, 0x9A)
#: Caracteres que ganham marca: espaco, espaco inseparavel, tabulacao e quebra de linha.
_MARCA_DO_CARACTERE = {" ": "·", "\u00a0": "°", "\t": "→", "\u2028": "↵"}


def desenhar_marcas(painter, doc, recorte: QRectF | None) -> None:
    """Pilcrow no fim de cada paragrafo, ponto em cada espaco e seta em cada tabulacao.

    Coordenadas do documento (twips), no painter ja' transformado. `recorte`: so' os
    blocos que cruzam esse retangulo (None = todos).
    """
    dl = doc.documentLayout()
    if recorte is not None:
        bloco = doc.findBlock(dl.hitTest(QPointF(0, recorte.top()), Qt.FuzzyHit))
        bloco = bloco.previous() if bloco.previous().isValid() else bloco
    else:
        bloco = doc.firstBlock()
    painter.save()
    painter.setPen(COR_MARCAS)
    fontes: dict[int, object] = {}
    while bloco.isValid():
        r = dl.blockBoundingRect(bloco)
        if recorte is not None and r.top() > recorte.bottom():
            # Dentro de tabela a ordem dos blocos nao e' a vertical: segue ate' o fim da tabela.
            if QTextCursor(bloco).currentTable() is None:
                break
        if recorte is None or r.intersects(recorte) or r.isEmpty():
            _marcas_do_bloco(painter, bloco, r, fontes)
        bloco = bloco.next()
    painter.restore()


def _fonte_da_marca(fontes: dict, cf, padrao) -> object:
    from PySide6.QtGui import QFont
    pontos = cf.fontPointSize() or padrao.pointSizeF() or 11.0
    chave = round(pontos * 2)
    fonte = fontes.get(chave)
    if fonte is None:
        fonte = QFont(padrao)
        # O layout e' em twips (1440 dpi): o corpo da letra em "pixels" e' pontos x 20.
        fonte.setPixelSize(max(1, round(pontos * 20)))
        fonte.setBold(False)
        fonte.setItalic(False)
        fontes[chave] = fonte
    return fonte


def _marcas_do_bloco(painter, bloco, r: QRectF, fontes: dict) -> None:
    lay = bloco.layout()
    if lay is None or lay.lineCount() == 0:
        return
    padrao = bloco.document().defaultFont()
    texto = bloco.text()
    for i, caractere in enumerate(texto):
        marca = _MARCA_DO_CARACTERE.get(caractere)
        if marca is None:
            continue
        linha = lay.lineForTextPosition(i)
        if not linha.isValid():
            continue
        x0, _ = linha.cursorToX(i)
        x1, _ = linha.cursorToX(i + 1)
        fonte = _fonte_da_marca(fontes, _formato_em(bloco, i), padrao)
        painter.setFont(fonte)
        meio = (x0 + x1) / 2.0
        larg = painter.fontMetrics().horizontalAdvance(marca)
        base = r.top() + linha.y() + linha.ascent()
        x = meio - larg / 2.0 if caractere != "\t" else min(x0, x1) + 20
        painter.drawText(QPointF(x, base), marca)
    linha = lay.lineAt(lay.lineCount() - 1)
    x, _ = linha.cursorToX(len(texto))
    cf = bloco.charFormat() if not texto else _formato_em(bloco, len(texto) - 1)
    painter.setFont(_fonte_da_marca(fontes, cf, padrao))
    painter.drawText(QPointF(r.left() + x + 20, r.top() + linha.y() + linha.ascent()), "¶")


def _formato_em(bloco, i: int):
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid():
            ini = frag.position() - bloco.position()
            if ini <= i < ini + frag.length():
                return frag.charFormat()
        it += 1
    return bloco.charFormat()

PALETA_TEXTO = QPalette()
PALETA_TEXTO.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
PALETA_TEXTO.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
PALETA_TEXTO.setColor(QPalette.ColorRole.Highlight, COR_SELECAO)


def desenhar_folha(painter, layout: LayoutPaginado, n: int, transf: QTransform,
                   corpo_recorte=None, selecao=None, marcas: bool = False,
                   comentarios: bool = False) -> None:
    """Pinta o corpo da pagina n. Funcao unica de pintura de folha.

    transf leva twips da folha (origem no canto superior esquerdo da folha) para o
    painter. corpo_recorte: (x, y, w, h) em twips do corpo, para pintar so' um tile;
    None pinta o corpo inteiro. selecao: QTextCursor com selecao, ou None.
    comentarios (0.1.6): o realce dos trechos comentados, so' na tela (a impressao e o PDF
    nao o passam).
    """
    cfg = layout.pagina
    hb = layout.hb
    corpo_h = cfg.corpo_altura_tw()
    # Na horizontal o recorte e' a folha inteira, nao so' o corpo (M8): a tabela mais larga
    # que o corpo (e o recuo negativo) entra na margem, como no Word. Na vertical continua
    # o corpo, que e' o que separa uma pagina da outra.
    permitido = QRectF(-cfg.margem_esq_tw, 0, float(cfg.largura_tw), corpo_h)
    if corpo_recorte is None:
        recorte = permitido
    else:
        recorte = QRectF(*corpo_recorte).intersected(permitido)
        if recorte.isEmpty():
            # Recorte fora do corpo (margem): nada a pintar. Um setClipRect vazio NAO recorta
            # nada, e o Qt pintaria a pagina inteira para jogar fora (medido: 45 ms por tile).
            return
    painter.save()
    painter.setWorldTransform(transf)
    painter.translate(cfg.margem_esq_tw, cfg.margem_sup_tw)
    painter.setClipRect(recorte)
    painter.translate(0, -n * hb)

    ctx = QAbstractTextDocumentLayout.PaintContext()
    ctx.clip = QRectF(recorte.x(), n * hb + recorte.y(), recorte.width(), recorte.height())
    ctx.palette = PALETA_TEXTO
    ctx.cursorPosition = -1
    selecoes = pq_comentarios.selecoes_de_realce(layout.doc) if comentarios else []
    if selecao is not None and selecao.hasSelection():
        sel = QAbstractTextDocumentLayout.Selection()
        sel.cursor = QTextCursor(selecao)
        fmt = QTextCharFormat()
        fmt.setBackground(COR_SELECAO)
        sel.format = fmt
        selecoes.append(sel)
    if selecoes:
        ctx.selections = selecoes
    layout.doc.documentLayout().draw(painter, ctx)
    # Numeros e marcadores das listas (0.1.4): pintados aqui, na funcao unica da folha.
    pq_listas.desenhar_rotulos(painter, layout.doc, ctx.clip)
    # Bordas de paragrafo e de trecho e preenchimento das tabulacoes (0.1.5).
    pq_props.desenhar(painter, layout.doc, ctx.clip)
    if marcas:
        desenhar_marcas(painter, layout.doc, ctx.clip)
    painter.restore()


def origem_da_faixa(pagina: Pagina, onde: str, altura_tw: float) -> tuple[float, float]:
    """Canto superior esquerdo do cabecalho (ou rodape) na folha, em twips.

    O cabecalho comeca a `cabecalho_tw` do alto da folha. O rodape termina a `rodape_tw`
    do pe' da folha e cresce para cima, como no Word.
    """
    if onde == "cabecalho":
        return float(pagina.margem_esq_tw), float(pagina.cabecalho_tw)
    return float(pagina.margem_esq_tw), float(pagina.altura_tw - pagina.rodape_tw - altura_tw)


def rotulo_da_faixa(onde: str, indice: int, pagina: Pagina) -> str:
    """O rotulo da area na edicao: "Cabeçalho", "Rodapé - Primeira página"..."""
    nome = "Cabeçalho" if onde == "cabecalho" else "Rodapé"
    tipo = tipo_da_pagina(indice, pagina)
    if tipo == "primeira":
        return f"{nome} - Primeira página"
    if pagina.pares_impares:
        return f"{nome} - Página par" if tipo == "par" else f"{nome} - Página ímpar"
    return nome


def desenhar_faixas(painter, layout: LayoutPaginado, n: int, transf: QTransform, total: int,
                    opacidade: float = 1.0, editada=None, selecao=None,
                    marcas: bool = False) -> None:
    """Pinta o cabecalho e o rodape da pagina n. Mesma funcao para a tela e para o PDF.

    transf leva twips da folha para o painter (como em desenhar_folha). `editada` e' a
    FaixaQt em edicao: ela recebe a selecao. Os campos ganham o numero da pagina n.
    """
    pagina = layout.pagina_arquivo
    for onde in ("cabecalho", "rodape"):
        faixa = layout.faixas.da_pagina(onde, n, pagina)
        if faixa is None:
            continue
        faixa.preparar(n, total, pagina)
        x, y = origem_da_faixa(pagina, onde, faixa.altura())
        painter.save()
        painter.setWorldTransform(transf)
        painter.translate(x, y)
        painter.setOpacity(opacidade)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette = PALETA_TEXTO
        ctx.cursorPosition = -1
        if faixa is editada and selecao is not None and selecao.hasSelection():
            sel = QAbstractTextDocumentLayout.Selection()
            sel.cursor = QTextCursor(selecao)
            fmt = QTextCharFormat()
            fmt.setBackground(COR_SELECAO)
            sel.format = fmt
            ctx.selections = [sel]
        faixa.doc.documentLayout().draw(painter, ctx)
        pq_listas.desenhar_rotulos(painter, faixa.doc, None)
        pq_props.desenhar(painter, faixa.doc, None)
        if marcas:
            desenhar_marcas(painter, faixa.doc, None)
        painter.restore()


class VistaPaginas(QAbstractScrollArea):
    zoomAlterado = Signal(float)

    def __init__(self, layout: LayoutPaginado, parent=None) -> None:
        super().__init__(parent)
        self.layout_pag = layout
        self._zoom = 1.0
        self._cache: OrderedDict = OrderedDict()
        self._bytes_no_cache = 0
        self._altura_doc_anterior: float | None = None
        self._pendencias: list[tuple[int, int]] = []
        self._caret_ligado = True
        #: Exibir (M6): marcas de formatacao e folhas lado a lado.
        self._marcas = False
        self._colunas = 1
        self._timer_caret = QTimer(self)
        self._timer_caret.timeout.connect(self._alternar_caret)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.verticalScrollBar().setSingleStep(PASSO_DA_RODA_PX)
        self.horizontalScrollBar().setSingleStep(PASSO_DA_RODA_PX)
        self.layout_pag.doc.contentsChange.connect(self._mudou_texto)
        self._atualizar_geometria()

    # ----- escala ---------------------------------------------------------
    def zoom(self) -> float:
        return self._zoom

    def dpr(self) -> float:
        return self.viewport().devicePixelRatioF()

    def teto_do_zoom(self) -> float:
        return teto_de_zoom(self.dpr())

    def definir_zoom(self, zoom: float, manter: QPointF | None = None) -> None:
        """Troca a escala. Nao refaz o layout. `manter`: ponto do viewport que fica parado."""
        novo = limitar_zoom(zoom, self.dpr())
        if abs(novo - self._zoom) < 1e-9:
            return
        ancora = None
        if manter is not None:
            ancora = self.mapa().tela_para_doc(manter.x(), manter.y(), self._paginas())
        self._zoom = novo
        self._limpar_cache()
        self._atualizar_geometria()
        if ancora is not None:
            x, y = self.mapa().doc_para_tela(ancora[0], ancora[1], self._paginas())
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() + round(x - manter.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() + round(y - manter.y()))
        self.viewport().update()
        self.zoomAlterado.emit(self._zoom)

    def _paginas(self) -> int:
        return self.layout_pag.numero_paginas()

    # ----- Exibir (M6) ----------------------------------------------------
    def marcas_visiveis(self) -> bool:
        return self._marcas

    def definir_marcas(self, ligado: bool) -> None:
        """Mostra ou esconde as marcas de formatacao. O cache de tiles e' refeito."""
        if bool(ligado) == self._marcas:
            return
        self._marcas = bool(ligado)
        self._limpar_cache()
        self.viewport().update()

    def colunas(self) -> int:
        return self._colunas

    def definir_colunas(self, colunas: int) -> None:
        colunas = max(1, int(colunas))
        if colunas == self._colunas:
            return
        self._colunas = colunas
        self._limpar_cache()
        self._atualizar_geometria()
        self.viewport().update()

    def _zoom_que_cabe(self, colunas: int, altura: bool) -> float:
        """Zoom em que `colunas` folhas cabem na largura (e, se `altura`, uma na altura)."""
        vp = self.viewport()
        cfg = self.layout_pag.pagina
        largura_px = cfg.largura_tw / TWIPS_POR_PX
        altura_px = cfg.altura_tw / TWIPS_POR_PX
        util = max(1.0, vp.width() - 2 * MARGEM_DO_PAINEL_PX)
        zoom = util / (colunas * largura_px + (colunas - 1) * VAO_ENTRE_FOLHAS_PX)
        if altura:
            zoom = min(zoom, max(1.0, float(vp.height())) / (altura_px + 2 * VAO_ENTRE_FOLHAS_PX))
        return zoom

    def zoom_modo(self, modo: str) -> None:
        """Exibir > Zoom: "100", "pagina" (uma pagina inteira), "varias" (duas lado a lado)
        ou "largura" (largura da pagina)."""
        pagina = self.pagina_atual() if hasattr(self, "pagina_atual") else 0
        if modo == "varias":
            self.definir_colunas(2)
            self.definir_zoom(self._zoom_que_cabe(2, altura=True))
        else:
            self.definir_colunas(1)
            if modo == "100":
                self.definir_zoom(1.0)
            elif modo == "pagina":
                self.definir_zoom(self._zoom_que_cabe(1, altura=True))
            else:
                self.definir_zoom(self._zoom_que_cabe(1, altura=False))
        self._atualizar_geometria()
        if modo in ("pagina", "varias"):
            self.rolar_para_pagina(pagina, folga=0)
        self.viewport().update()

    def mapa(self) -> Mapa:
        """Mapeamento atual entre documento e viewport (ver modelo/folhas.py)."""
        return self._mapa()

    def _mapa(self) -> Mapa:
        vp = self.viewport()
        return Mapa(pagina=self.layout_pag.pagina, zoom=self._zoom,
                    largura_viewport=float(vp.width()), altura_viewport=float(vp.height()),
                    origem_x=float(self.horizontalScrollBar().value()),
                    origem_y=float(self.verticalScrollBar().value()),
                    colunas=self._colunas)

    def _atualizar_geometria(self) -> None:
        vp = self.viewport()
        m = self.mapa()
        largura = max(m.largura_conteudo + 2 * MARGEM_DO_PAINEL_PX, float(vp.width()))
        altura = m.altura_total(self._paginas())
        hb = self.horizontalScrollBar()
        vb = self.verticalScrollBar()
        hb.setRange(0, max(0, math.ceil(largura - vp.width())))
        hb.setPageStep(max(1, vp.width()))
        vb.setRange(0, max(0, math.ceil(altura - vp.height())))
        vb.setPageStep(max(1, vp.height()))

    # ----- cache de tiles -------------------------------------------------
    def _limpar_cache(self) -> None:
        self._cache.clear()
        self._bytes_no_cache = 0
        self._pendencias = []

    def _invalidar_faixa(self, y0: float, y1: float) -> None:
        for chave in [k for k, v in self._cache.items() if v[2] > y0 and v[1] < y1]:
            _, _, _, nbytes = self._cache.pop(chave)
            self._bytes_no_cache -= nbytes

    def _mudou_texto(self, pos: int, removido: int, adicionado: int) -> None:
        """Anota a mudanca. A invalidacao e' feita na proxima pintura.

        Nao se pode ler a altura do documento aqui: no sinal o layout ainda nao foi refeito, e a
        altura lida seria a antiga (medido: a quebra de linha deixava tiles velhos na tela).
        """
        self._pendencias.append((pos, adicionado))
        self.viewport().update()

    def _aplicar_pendencias(self) -> None:
        """Invalida os tiles afetados pelas mudancas anotadas, com o layout ja refeito.

        Se a altura total mudou, tudo a partir da primeira linha alterada sai do cache (o
        texto de baixo se moveu). Se nao mudou, so' a faixa da linha alterada sai. Mais de
        uma mudanca na mesma pintura: vale o caso conservador, de cima para baixo.
        """
        if not self._pendencias:
            return
        doc = self.layout_pag.doc
        dl = doc.documentLayout()
        pendencias, self._pendencias = self._pendencias, []
        altura = dl.blockBoundingRect(doc.lastBlock()).bottom()
        anterior, self._altura_doc_anterior = self._altura_doc_anterior, altura
        if anterior is None or abs(altura - anterior) >= 0.5 or len(pendencias) > 1:
            topo = min(self._faixa_de(p, p)[0] for p, _ in pendencias)
            self._invalidar_faixa(topo, math.inf)
            return
        pos, adicionado = pendencias[0]
        topo, base = self._faixa_de(pos, pos + adicionado)
        self._invalidar_faixa(topo, base)

    def _faixa_de(self, inicio: int, fim: int) -> tuple[float, float]:
        """Faixa vertical (twips) afetada por uma mudanca entre `inicio` e `fim`.

        Dentro de tabela vale a tabela inteira (a de fora, se aninhada): a altura de uma
        linha muda as celulas vizinhas, e uma borda redesenhada muda a grade toda.
        """
        doc = self.layout_pag.doc
        dl = doc.documentLayout()
        topo = dl.blockBoundingRect(doc.findBlock(inicio)).top()
        base = dl.blockBoundingRect(doc.findBlock(fim)).bottom()
        cursor = QTextCursor(doc)
        cursor.setPosition(min(max(inicio, 0), doc.characterCount() - 1))
        quadro = cursor.currentFrame()
        externo = None
        while quadro is not None and quadro.parentFrame() is not None:
            externo = quadro
            quadro = quadro.parentFrame()
        if externo is not None:
            r = dl.frameBoundingRect(externo)
            topo, base = min(topo, r.top()), max(base, r.bottom())
        return topo, base

    def _tile(self, n: int, i: int, j: int, dpr: float, m: Mapa) -> QPixmap:
        chave = (n, i, j, self._zoom, dpr)
        entrada = self._cache.get(chave)
        if entrada is not None:
            self._cache.move_to_end(chave)
            return entrada[0]
        cfg = self.layout_pag.pagina
        e = m.escala
        tw = TILE_PX / e
        lado = round(TILE_PX * dpr)
        pm = QPixmap(lado, lado)
        pm.setDevicePixelRatio(dpr)
        pm.fill(COR_FOLHA)
        pintor = QPainter(pm)
        t = QTransform()
        t.translate(-i * TILE_PX, -j * TILE_PX)
        t.scale(e, e)
        desenhar_folha(pintor, self.layout_pag, n, t,
                       corpo_recorte=(i * tw - cfg.margem_esq_tw, j * tw - cfg.margem_sup_tw,
                                      tw, tw), marcas=self._marcas, comentarios=True)
        pintor.end()
        dy0 = n * self.layout_pag.hb + (j * tw - cfg.margem_sup_tw)
        nbytes = lado * lado * 4
        self._cache[chave] = (pm, dy0, dy0 + tw, nbytes)
        self._bytes_no_cache += nbytes
        while self._bytes_no_cache > LIMITE_DO_CACHE_BYTES and self._cache:
            _, valor = self._cache.popitem(last=False)
            self._bytes_no_cache -= valor[3]
        return pm

    # ----- caret e selecao (o painel informa) ------------------------------
    def _posicao_caret(self) -> int | None:
        """Posicao onde desenhar o caret, ou None para nao desenhar."""
        return None

    def _selecao_atual(self) -> QTextCursor | None:
        return None

    def _posicao_imagem_selecionada(self) -> int | None:
        """Imagem selecionada, para desenhar o quadro e as alcas (o painel informa)."""
        return None

    def _retangulo_redimensionando(self) -> QRectF | None:
        """Retangulo do arrasto de alca em andamento, em px do viewport (o painel informa)."""
        return None

    def retangulo_imagem_na_tela(self, pos: int) -> QRectF | None:
        """Retangulo da imagem em `pos`, em pixels do viewport."""
        r = self.layout_pag.retangulo_imagem(pos)
        if r is None:
            return None
        m = self._mapa()
        # Pelo canto de cima: a base da imagem pode cair exatamente na divisa da pagina.
        x0, y0 = m.doc_para_tela(r.left(), r.top(), self._paginas())
        return QRectF(x0, y0, r.width() * m.escala, r.height() * m.escala)

    def _faixa_editada(self):
        """(FaixaQt em edicao, cursor dela), ou None. O painel informa."""
        return None

    def _retangulo_do_caret(self, m: Mapa, n_total: int) -> QRectF | None:
        """Caret em px do viewport, ou None. O painel troca isto na edicao do cabecalho."""
        pos = self._posicao_caret()
        if pos is None:
            return None
        c = self.layout_pag.retangulo_cursor(pos)
        x, y = m.doc_para_tela(c.x(), c.y(), n_total)
        return QRectF(x, y, 1.0, c.height() * m.escala)

    def _alternar_caret(self) -> None:
        self._caret_ligado = not self._caret_ligado
        self.viewport().update()

    def definir_piscar(self, ligado: bool) -> None:
        if ligado:
            self._timer_caret.start(PERIODO_DO_CARET_MS)
        else:
            self._timer_caret.stop()
        self._caret_ligado = True
        self.viewport().update()

    def mostrar_caret_agora(self) -> None:
        """Caret aceso logo apos um movimento, como o QTextEdit faz."""
        self._caret_ligado = True
        if self._timer_caret.isActive():
            self._timer_caret.start(PERIODO_DO_CARET_MS)

    # ----- rolagem --------------------------------------------------------
    def garantir_visivel(self, r: QRectF) -> None:
        """Rola o minimo para que o retangulo (documento) apareca no viewport."""
        m = self.mapa()
        n = self._paginas()
        tl = m.doc_para_tela(r.left(), r.top(), n)
        br = m.doc_para_tela(r.right(), r.bottom(), n)
        vp = self.viewport()
        vb = self.verticalScrollBar()
        hb = self.horizontalScrollBar()
        if tl[1] < 0:
            vb.setValue(vb.value() + math.floor(tl[1]) - 16)
        elif br[1] > vp.height():
            vb.setValue(vb.value() + math.ceil(br[1] - vp.height()) + 16)
        if tl[0] < 0:
            hb.setValue(hb.value() + math.floor(tl[0]) - 16)
        elif br[0] > vp.width():
            hb.setValue(hb.value() + math.ceil(br[0] - vp.width()) + 16)
        self.viewport().update()

    def rolar_para_pagina(self, n: int, folga: float = 8) -> None:
        m = self.mapa()
        linha = max(0, int(n)) // max(1, m.colunas)
        self.verticalScrollBar().setValue(int(m.vao + linha * m.passo_vertical - folga))

    # ----- pintura --------------------------------------------------------
    def preparar_para_impressao(self) -> None:
        """Campos do corpo com o total atual antes de imprimir ou exportar (M7).

        Mesma conta da pintura: se os campos mudaram, o cache de tiles sai junto, senao a
        tela ficaria com o numero velho depois que a impressao refez o layout.
        """
        listas_mudaram = pq_listas.numerador_de(self.layout_pag.doc).atualizar()
        if self.layout_pag.atualizar_campos() or listas_mudaram:
            self._limpar_cache()
            self._altura_doc_anterior = None
            self.viewport().update()

    def paintEvent(self, ev) -> None:
        if self.layout_pag.atualizar_campos():
            # Total de paginas mudou e o corpo tem campo: o numero na tela muda.
            self._limpar_cache()
            self._altura_doc_anterior = None
        if pq_listas.numerador_de(self.layout_pag.doc).atualizar():
            # Um numero de lista mudou longe da edicao (Tab num item renumera os de baixo).
            self._limpar_cache()
            self._altura_doc_anterior = None
        self._aplicar_pendencias()
        vp = self.viewport()
        p = QPainter(vp)
        p.fillRect(vp.rect(), COR_FUNDO)
        dpr = vp.devicePixelRatioF()
        m = self.mapa()
        n_total = self._paginas()
        i0, i1 = m.paginas_visiveis(n_total)
        selecao = self._selecao_atual()
        com_selecao = selecao is not None and selecao.hasSelection()
        visivel = QRectF(0, 0, vp.width(), vp.height())
        for n in range(i0, i1 + 1):
            x, y, w, h = m.folha_na_tela(n)
            # bordas em pixel de dispositivo inteiro: o Qt nao pinta meio pixel
            x0, y0 = alinhar_ao_dispositivo(x, dpr), alinhar_ao_dispositivo(y, dpr)
            x1 = alinhar_ao_dispositivo(x + w, dpr)
            y1 = alinhar_ao_dispositivo(y + h, dpr)
            folha = QRectF(x0, y0, x1 - x0, y1 - y0)
            sombra = 2.0 / dpr
            p.fillRect(folha.translated(sombra, sombra), COR_SOMBRA)
            p.fillRect(folha, COR_FOLHA)
            p.save()
            p.setClipRect(folha)
            if com_selecao:
                t = QTransform().translate(x0, y0).scale(m.escala, m.escala)
                desenhar_folha(p, self.layout_pag, n, t, selecao=selecao, marcas=self._marcas,
                               comentarios=True)
            else:
                nx = math.ceil(m.largura_folha / TILE_PX)
                ny = math.ceil(m.altura_folha / TILE_PX)
                for j in range(ny):
                    for i in range(nx):
                        alvo = QRectF(x0 + i * TILE_PX, y0 + j * TILE_PX, TILE_PX, TILE_PX)
                        if alvo.intersects(visivel):
                            p.drawPixmap(QPointF(alvo.x(), alvo.y()),
                                         self._tile(n, i, j, dpr, m))
            self._pintar_faixas(p, m, n, x0, y0, n_total)
            p.restore()
        self._desenhar_quebras(p, m, i0, i1, n_total)
        self._desenhar_caret(p, m, dpr, n_total)
        self._desenhar_imagem_selecionada(p)
        p.end()

    def _pintar_faixas(self, p: QPainter, m: Mapa, n: int, x0: float, y0: float,
                       n_total: int) -> None:
        """Cabecalho e rodape da folha n, por cima dos tiles. Na edicao, o corpo esmaece."""
        editada = self._faixa_editada()
        t = QTransform().translate(x0, y0).scale(m.escala, m.escala)
        if editada is None:
            desenhar_faixas(p, self.layout_pag, n, t, n_total, OPACIDADE_FAIXA,
                            marcas=self._marcas)
            return
        faixa, cursor = editada
        efetiva = self.layout_pag.pagina
        corpo = QRectF(x0 + efetiva.margem_esq_tw * m.escala, y0 + efetiva.margem_sup_tw * m.escala,
                       efetiva.corpo_largura_tw() * m.escala, efetiva.corpo_altura_tw() * m.escala)
        p.fillRect(corpo, COR_VEU)
        desenhar_faixas(p, self.layout_pag, n, t, n_total, 1.0, faixa, cursor,
                        marcas=self._marcas)
        # Linha tracejada e rotulo no limite de cada area, em todas as paginas.
        p.save()
        fonte = p.font()
        fonte.setPointSizeF(8.0)
        p.setFont(fonte)
        metrica = p.fontMetrics()
        for onde, y_tw in (("cabecalho", efetiva.margem_sup_tw),
                           ("rodape", efetiva.altura_tw - efetiva.margem_inf_tw)):
            y = y0 + y_tw * m.escala
            p.setPen(QPen(COR_ROTULO_FAIXA, 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x0, y), QPointF(x0 + m.largura_folha, y))
            rotulo = rotulo_da_faixa(onde, n, self.layout_pag.pagina_arquivo)
            larg = metrica.horizontalAdvance(rotulo) + 10
            alto = metrica.height() + 2
            caixa = QRectF(x0 + 4, y if onde == "cabecalho" else y - alto, larg, alto)
            p.fillRect(caixa, QColor(0xDD, 0xE6, 0xF4))
            p.setPen(COR_ROTULO_FAIXA)
            p.drawText(caixa, Qt.AlignmentFlag.AlignCenter, rotulo)
        p.restore()

    def _desenhar_imagem_selecionada(self, p: QPainter) -> None:
        """Quadro e alcas nos quatro cantos da imagem selecionada; tracejado durante o arrasto."""
        pos = self._posicao_imagem_selecionada()
        if pos is None:
            return
        r = self.retangulo_imagem_na_tela(pos)
        if r is None:
            return
        p.save()
        p.setPen(QPen(COR_SELECAO, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        lado = ALCA_TELA_PX
        for canto in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
            alca = QRectF(canto.x() - lado / 2, canto.y() - lado / 2, lado, lado)
            p.fillRect(alca, COR_FOLHA)
            p.drawRect(alca)
        novo = self._retangulo_redimensionando()
        if novo is not None:
            p.setPen(QPen(COR_SELECAO, 1, Qt.PenStyle.DashLine))
            p.drawRect(novo)
        p.restore()

    def _desenhar_caret(self, p: QPainter, m: Mapa, dpr: float, n_total: int) -> None:
        if not self._caret_ligado or not self.hasFocus():
            return
        r = self._retangulo_do_caret(m, n_total)
        if r is None:
            return
        x, y = alinhar_ao_dispositivo(r.x(), dpr), alinhar_ao_dispositivo(r.y(), dpr)
        p.fillRect(QRectF(x, y, 1.0 / dpr, r.height()), COR_CARET)

    def _desenhar_quebras(self, p: QPainter, m: Mapa, i0: int, i1: int, n_total: int) -> None:
        """Linha tracejada 'Quebra de pagina' onde um paragrafo comeca numa pagina nova.

        A linha vai no fim do paragrafo anterior, que e' onde a quebra acontece. Fica
        dentro do corpo: nada e' pintado nas margens.
        """
        doc = self.layout_pag.doc
        dl = doc.documentLayout()
        topo = i0 * self.layout_pag.hb
        bloco = doc.findBlock(dl.hitTest(QPointF(0, topo), Qt.FuzzyHit))
        limite = (i1 + 1) * self.layout_pag.hb
        corpo_w = float(self.layout_pag.pagina.corpo_largura_tw())
        fonte = p.font()
        fonte.setPointSizeF(8.0)
        p.save()
        p.setFont(fonte)
        while bloco.isValid() and dl.blockBoundingRect(bloco).top() < limite:
            anterior = bloco.previous()
            tem_quebra = bool(bloco.blockFormat().pageBreakPolicy() & _QUEBRA_ANTES)
            if tem_quebra and anterior.isValid():
                y = dl.blockBoundingRect(anterior).bottom()
                xa, ya = m.doc_para_tela(0.0, y, n_total)
                xb, _ = m.doc_para_tela(corpo_w, y, n_total)
                p.setPen(QPen(COR_QUEBRA, 1, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(xa, ya), QPointF(xb, ya))
                rotulo = "Quebra de página"
                metrica = p.fontMetrics()
                larg = metrica.horizontalAdvance(rotulo) + 12
                meio = (xa + xb) / 2.0
                p.fillRect(QRectF(meio - larg / 2, ya - metrica.height() / 2, larg,
                                  metrica.height()), COR_FOLHA)
                p.setPen(COR_QUEBRA)
                p.drawText(QRectF(meio - larg / 2, ya - metrica.height() / 2, larg,
                                  metrica.height()), Qt.AlignmentFlag.AlignCenter, rotulo)
            bloco = bloco.next()
        p.restore()

    # ----- eventos de tela ------------------------------------------------
    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        if self._zoom > self.teto_do_zoom() + 1e-9:
            self._zoom = self.teto_do_zoom()
            self._limpar_cache()
            self.zoomAlterado.emit(self._zoom)
        self._atualizar_geometria()

    def scrollContentsBy(self, dx, dy) -> None:
        self.viewport().update()

    def focusNextPrevChild(self, proximo) -> bool:
        # Tab e' do editor (caractere de tabulacao), nao do foco da janela.
        return False

    def focusInEvent(self, ev) -> None:
        super().focusInEvent(ev)
        self.viewport().update()

    def focusOutEvent(self, ev) -> None:
        super().focusOutEvent(ev)
        self.viewport().update()

    def wheelEvent(self, ev) -> None:
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            aumentar = ev.angleDelta().y() > 0
            ancora = QPointF(ev.position())
            self.definir_zoom(passo_de_zoom(self._zoom, aumentar, self.dpr()), manter=ancora)
            ev.accept()
            return
        super().wheelEvent(ev)

