"""Visao em folhas A4: desenha as paginas, faz a rolagem e o zoom. Nao edita.

A edicao (caret, teclado, mouse, desfazer) e' de PainelDocumento, que herda desta
classe. Aqui fica o que e' so' de pintura e de geometria.

Cada folha e' pintada pela mesma funcao (`desenhar_folha`) que o PDF usaria, e o
zoom so' muda a escala: nunca refaz o layout.

Cache de tiles (medido no Gate do M3, docs/SPIKES.md):
  - a folha e' cortada em tiles de TILE_PX pixels logicos, na coordenada da propria
    pagina; cada tile e' um QPixmap no DPR da tela;
  - uma mudanca no texto invalida so' os tiles tocados pela altura alterada; se a
    altura total do documento mudou, invalida tudo abaixo do ponto da mudanca;
  - o cache tem teto de memoria; zoom, DPR e configuracao de pagina limpam tudo;
  - com selecao, a folha e' pintada direto (a selecao nao e' cacheada).
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
from editdoc.modelo.folhas import (MARGEM_DO_PAINEL_PX, PASSO_DA_RODA_PX, Mapa,
                                   alinhar_ao_dispositivo, limitar_zoom, passo_de_zoom,
                                   teto_de_zoom)

TILE_PX = 256
LIMITE_DO_CACHE_BYTES = 64 * 1024 * 1024
PERIODO_DO_CARET_MS = 530

COR_FUNDO = QColor(0xB9, 0xBE, 0xC6)
COR_SOMBRA = QColor(0x80, 0x86, 0x90)
COR_FOLHA = QColor(255, 255, 255)
COR_SELECAO = QColor(0, 120, 215)
COR_CARET = QColor(0, 0, 0)
COR_QUEBRA = QColor(0x70, 0x76, 0x80)
_QUEBRA_ANTES = QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore

PALETA_TEXTO = QPalette()
PALETA_TEXTO.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
PALETA_TEXTO.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
PALETA_TEXTO.setColor(QPalette.ColorRole.Highlight, COR_SELECAO)


def desenhar_folha(painter, layout: LayoutPaginado, n: int, transf: QTransform,
                   corpo_recorte=None, selecao=None) -> None:
    """Pinta o corpo da pagina n. Funcao unica de pintura de folha.

    transf leva twips da folha (origem no canto superior esquerdo da folha) para o
    painter. corpo_recorte: (x, y, w, h) em twips do corpo, para pintar so' um tile;
    None pinta o corpo inteiro. selecao: QTextCursor com selecao, ou None.
    """
    cfg = layout.pagina
    hb = layout.hb
    corpo_w, corpo_h = cfg.corpo_largura_tw(), cfg.corpo_altura_tw()
    if corpo_recorte is None:
        recorte = QRectF(0, 0, corpo_w, corpo_h)
    else:
        recorte = QRectF(*corpo_recorte).intersected(QRectF(0, 0, corpo_w, corpo_h))
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
    if selecao is not None and selecao.hasSelection():
        sel = QAbstractTextDocumentLayout.Selection()
        sel.cursor = QTextCursor(selecao)
        fmt = QTextCharFormat()
        fmt.setBackground(COR_SELECAO)
        sel.format = fmt
        ctx.selections = [sel]
    layout.doc.documentLayout().draw(painter, ctx)
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

    def mapa(self) -> Mapa:
        """Mapeamento atual entre documento e viewport (ver modelo/folhas.py)."""
        return self._mapa()

    def _mapa(self) -> Mapa:
        vp = self.viewport()
        return Mapa(pagina=self.layout_pag.pagina, zoom=self._zoom,
                    largura_viewport=float(vp.width()), altura_viewport=float(vp.height()),
                    origem_x=float(self.horizontalScrollBar().value()),
                    origem_y=float(self.verticalScrollBar().value()))

    def _atualizar_geometria(self) -> None:
        vp = self.viewport()
        m = self.mapa()
        largura = max(m.largura_folha + 2 * MARGEM_DO_PAINEL_PX, float(vp.width()))
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
            topo = min(dl.blockBoundingRect(doc.findBlock(p)).top() for p, _ in pendencias)
            self._invalidar_faixa(topo, math.inf)
            return
        pos, adicionado = pendencias[0]
        topo = dl.blockBoundingRect(doc.findBlock(pos)).top()
        base = dl.blockBoundingRect(doc.findBlock(pos + adicionado)).bottom()
        self._invalidar_faixa(topo, base)

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
                                      tw, tw))
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

    def rolar_para_pagina(self, n: int) -> None:
        m = self.mapa()
        self.verticalScrollBar().setValue(int(m.vao + n * m.passo_vertical - 8))

    # ----- pintura --------------------------------------------------------
    def paintEvent(self, ev) -> None:
        self._aplicar_pendencias()
        vp = self.viewport()
        p = QPainter(vp)
        p.fillRect(vp.rect(), COR_FUNDO)
        dpr = vp.devicePixelRatioF()
        m = self.mapa()
        n_total = self._paginas()
        i0 = max(0, math.floor((m.origem_y - m.vao) / m.passo_vertical))
        i1 = min(n_total - 1, math.floor((m.origem_y + vp.height() - m.vao) / m.passo_vertical) + 1)
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
                desenhar_folha(p, self.layout_pag, n, t, selecao=selecao)
            else:
                nx = math.ceil(m.largura_folha / TILE_PX)
                ny = math.ceil(m.altura_folha / TILE_PX)
                for j in range(ny):
                    for i in range(nx):
                        alvo = QRectF(x0 + i * TILE_PX, y0 + j * TILE_PX, TILE_PX, TILE_PX)
                        if alvo.intersects(visivel):
                            p.drawPixmap(QPointF(alvo.x(), alvo.y()),
                                         self._tile(n, i, j, dpr, m))
            p.restore()
        self._desenhar_quebras(p, m, i0, i1, n_total)
        self._desenhar_caret(p, m, dpr, n_total)
        p.end()

    def _desenhar_caret(self, p: QPainter, m: Mapa, dpr: float, n_total: int) -> None:
        pos = self._posicao_caret()
        if pos is None or not self._caret_ligado or not self.hasFocus():
            return
        c = self.layout_pag.retangulo_cursor(pos)
        x, y = m.doc_para_tela(c.x(), c.y(), n_total)
        x, y = alinhar_ao_dispositivo(x, dpr), alinhar_ao_dispositivo(y, dpr)
        p.fillRect(QRectF(x, y, 1.0 / dpr, c.height() * m.escala), COR_CARET)

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

