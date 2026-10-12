"""Spike A: visao em folhas A4 sobre o LayoutPaginado.

- desenhar_conteudo_folha(): UNICA funcao que pinta uma folha. Tela, PDF e
  pre-visualizacao chamam esta mesma funcao (criterio C7).
- VistaPaginas: QAbstractScrollArea. Folhas em fundo cinza, zoom por escala
  (sem relayout), mapeamento doc<->widget por formula, hit-test pelo Qt.
"""
import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QAbstractTextDocumentLayout as Layout, QColor, QPainter,
                           QPalette, QTextCharFormat, QTextCursor, QTransform)
from PySide6.QtWidgets import QAbstractScrollArea

from controle import ControleTexto

GAP_PX = 24.0          # vao entre folhas a 100%
MARGEM_PAINEL_PX = 24.0
ZOOM_MIN = 0.25
ZOOM_MAX = 4.0
COR_FUNDO = QColor(0xB9, 0xBE, 0xC6)
COR_SOMBRA = QColor(0x80, 0x86, 0x90)
COR_SELECAO = QColor(0, 120, 215)
COR_CARET = QColor(0, 0, 0)


def _paleta() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
    p.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Highlight, COR_SELECAO)
    return p


PALETA_TEXTO = _paleta()


def desenhar_conteudo_folha(painter, layout, n, transf, cabecalho=None,
                            selecao=None, caret=None, espessura_caret=1.0):
    """Pinta o corpo da pagina n, cabecalho/rodape e (opcional) selecao e caret.

    transf: QTransform que leva coordenadas de folha (twips, origem no canto
    superior esquerdo da folha) para coordenadas do painter.
    selecao: QTextCursor com selecao ou None.
    caret: QRectF em coordenadas do documento ou None.
    """
    cfg = layout.config
    hb = layout.hb
    painter.save()
    painter.setWorldTransform(transf)
    painter.translate(cfg.margem_esq, cfg.margem_sup)
    painter.setClipRect(QRectF(0, 0, cfg.larg_corpo, cfg.alt_corpo))
    painter.translate(0, -n * hb)

    ctx = Layout.PaintContext()
    ctx.clip = QRectF(0, n * hb, cfg.larg_corpo, hb)
    ctx.palette = PALETA_TEXTO
    ctx.cursorPosition = -1
    if selecao is not None and selecao.hasSelection():
        sel = Layout.Selection()
        sel.cursor = QTextCursor(selecao)
        fmt = QTextCharFormat()
        fmt.setBackground(COR_SELECAO)
        sel.format = fmt
        ctx.selections = [sel]
    layout.doc.documentLayout().draw(painter, ctx)

    if caret is not None and n * hb <= caret.top() < (n + 1) * hb:
        painter.fillRect(QRectF(caret.x(), caret.y(), espessura_caret, caret.height()), COR_CARET)
    painter.restore()

    if cabecalho is not None:
        painter.save()
        painter.setWorldTransform(transf)
        cabecalho.desenhar(painter, n, layout.numero_paginas())
        painter.restore()


class VistaPaginas(QAbstractScrollArea):
    def __init__(self, layout, cabecalho=None, parent=None):
        super().__init__(parent)
        self.layout_pag = layout
        self.cabecalho = cabecalho
        self._zoom = 1.0
        self._esq_folha = 0.0
        self._cw = 0.0
        self._ch = 0.0
        self._frac = QPointF(0.0, 0.0)  # parte fracionaria da origem (ver definir_origem)
        self.controle = ControleTexto(layout, self)
        self.controle.mudou.connect(self._apos_edicao)
        self.controle.altura_visivel = self._altura_visivel_tw
        self._caret_on = True
        self.mostrar_caret = True  # desligado nas comparacoes de pixel (C7)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._alternar_caret)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(False)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._atualizar_geometria()

    # ----- escala, geometria e mapeamento --------------------------------
    def zoom(self) -> float:
        return self._zoom

    def escala(self) -> float:
        """Pixels logicos por twip."""
        return self._zoom / 15.0

    def definir_zoom(self, z: float) -> None:
        self._zoom = min(max(float(z), ZOOM_MIN), ZOOM_MAX)
        self._atualizar_geometria()
        self.viewport().update()

    def _pitch(self) -> float:
        cfg = self.layout_pag.config
        return cfg.altura * self.escala() + GAP_PX * self._zoom

    def _atualizar_geometria(self) -> None:
        cfg = self.layout_pag.config
        n = self.layout_pag.numero_paginas()
        esc = self.escala()
        w = cfg.largura * esc
        h = cfg.altura * esc
        gap = GAP_PX * self._zoom
        vw = self.viewport().width()
        vh = self.viewport().height()
        self._cw = max(w + 2 * MARGEM_PAINEL_PX, float(vw))
        self._ch = n * (h + gap) + gap
        self._esq_folha = (self._cw - w) / 2.0
        hb = self.horizontalScrollBar()
        vb = self.verticalScrollBar()
        hb.setRange(0, max(0, math.ceil(self._cw - vw)))
        hb.setPageStep(max(1, vw))
        hb.setSingleStep(max(1, int(40 * self._zoom)))
        vb.setRange(0, max(0, math.ceil(self._ch - vh)))
        vb.setPageStep(max(1, vh))
        vb.setSingleStep(max(1, int(40 * self._zoom)))

    def origem(self) -> QPointF:
        return QPointF(self.horizontalScrollBar().value() + self._frac.x(),
                       self.verticalScrollBar().value() + self._frac.y())

    def definir_origem(self, x: float, y: float) -> None:
        """Ajusta a rolagem para uma origem possivelmente fracionaria.

        Qt guarda rolagem em inteiros. A parte fracionaria fica nesta classe e
        entra no mapeamento; a pintura usa a origem arredondada ao pixel.
        """
        ix, iy = math.floor(x), math.floor(y)
        self._frac = QPointF(x - ix, y - iy)
        self.horizontalScrollBar().setValue(int(ix))
        self.verticalScrollBar().setValue(int(iy))
        self.viewport().update()

    def doc_para_widget(self, d: QPointF) -> QPointF:
        """Ponto do documento -> ponto logico do viewport (formula)."""
        cfg = self.layout_pag.config
        esc = self.escala()
        n = self.layout_pag.pagina_de_y(d.y())
        ty = d.y() - n * self.layout_pag.hb + cfg.margem_sup
        tx = d.x() + cfg.margem_esq
        o = self.origem()
        x = self._esq_folha + tx * esc - o.x()
        y = GAP_PX * self._zoom + n * self._pitch() + ty * esc - o.y()
        return QPointF(x, y)

    def widget_para_doc(self, p: QPointF) -> QPointF:
        """Ponto logico do viewport -> ponto do documento (formula inversa)."""
        cfg = self.layout_pag.config
        esc = self.escala()
        o = self.origem()
        cx = p.x() + o.x() - self._esq_folha
        cy = p.y() + o.y()
        gap = GAP_PX * self._zoom
        pitch = self._pitch()
        n = int(math.floor((cy - gap) / pitch))
        n = min(max(n, 0), self.layout_pag.numero_paginas() - 1)
        sy = cy - (gap + n * pitch)
        tx = cx / esc
        ty = sy / esc
        return QPointF(tx - cfg.margem_esq, ty - cfg.margem_sup + n * self.layout_pag.hb)

    def posicao_em(self, p: QPointF) -> int:
        """Posicao do texto sob um ponto do viewport.

        Hit-test do Qt (FuzzyHit) e depois restrito a pagina clicada: um clique
        no espaco em branco de uma pagina nao pode cair na pagina vizinha.
        """
        d = self.widget_para_doc(p)
        n = self.layout_pag.pagina_de_y(d.y())
        pos = self.layout_pag.doc.documentLayout().hitTest(d, Qt.FuzzyHit)
        if self.layout_pag.pagina_do_cursor(pos) != n:
            pos = self.layout_pag.ajustar_para_pagina(pos, n)
        return pos

    def retangulo_folha_logico(self, n: int):
        """Retangulo da folha n em coordenadas logicas do viewport (sem arredondar)."""
        cfg = self.layout_pag.config
        esc = self.escala()
        o = self.origem()
        x0 = self._esq_folha - o.x()
        y0 = GAP_PX * self._zoom + n * self._pitch() - o.y()
        return QRectF(x0, y0, cfg.largura * esc, cfg.altura * esc)

    def rolar_para_pagina(self, n: int) -> None:
        self.verticalScrollBar().setValue(int(GAP_PX * self._zoom + n * self._pitch() - 8))

    def garantir_visivel(self, r: QRectF) -> None:
        """Rola o minimo para que o retangulo (doc) apareca no viewport."""
        tl = self.doc_para_widget(r.topLeft())
        br = self.doc_para_widget(r.bottomRight())
        vp = self.viewport().rect()
        vb = self.verticalScrollBar()
        hb = self.horizontalScrollBar()
        if tl.y() < 0:
            vb.setValue(vb.value() + int(math.floor(tl.y())) - 16)
        elif br.y() > vp.height():
            vb.setValue(vb.value() + int(math.ceil(br.y() - vp.height())) + 16)
        if tl.x() < 0:
            hb.setValue(hb.value() + int(math.floor(tl.x())) - 16)
        elif br.x() > vp.width():
            hb.setValue(hb.value() + int(math.ceil(br.x() - vp.width())) + 16)
        self.viewport().update()

    def _altura_visivel_tw(self) -> float:
        return self.viewport().height() / self.escala()

    # ----- ciclo de edicao e caret ----------------------------------------
    def definir_piscar(self, ligado: bool) -> None:
        if ligado:
            self._timer.start(530)
        else:
            self._timer.stop()
            self._caret_on = True

    def _alternar_caret(self):
        self._caret_on = not self._caret_on
        self.viewport().update()

    def _apos_edicao(self):
        self._caret_on = True
        self._atualizar_geometria()
        r = self.layout_pag.retangulo_cursor(self.controle.cursor.position())
        self.garantir_visivel(r)
        self.viewport().update()

    # ----- eventos ----------------------------------------------------------
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._atualizar_geometria()

    def scrollContentsBy(self, dx, dy):
        self.viewport().update()

    def focusNextPrevChild(self, proximo):
        # Tab e Shift+Tab sao do editor (navegacao de celulas), nao do foco da janela
        return False

    def keyPressEvent(self, ev):
        if not self.controle.tecla(ev):
            super().keyPressEvent(ev)
            return
        ev.accept()

    def mousePressEvent(self, ev):
        self.setFocus()
        p = ev.position()
        pos = self.posicao_em(p)
        self.controle.clicar(pos, bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier))
        self._apos_edicao()
        ev.accept()

    def mouseMoveEvent(self, ev):
        if self.controle.arrastando():
            self.controle.arrastar(self.posicao_em(ev.position()))
            self._apos_edicao()
        ev.accept()

    def mouseReleaseEvent(self, ev):
        self.controle.soltar()
        ev.accept()

    def paintEvent(self, ev):
        vp = self.viewport()
        p = QPainter(vp)
        p.fillRect(vp.rect(), COR_FUNDO)
        dpr = vp.devicePixelRatioF()
        cfg = self.layout_pag.config
        n_total = self.layout_pag.numero_paginas()
        pitch = self._pitch()
        o = self.origem()
        i0 = max(0, int(math.floor((o.y() - GAP_PX * self._zoom) / pitch)))
        i1 = min(n_total - 1, int(math.floor((o.y() + vp.height()) / pitch)) + 1)
        esc = self.escala()
        caret = None
        if self.mostrar_caret and self.controle.tem_foco_visivel() and self._caret_on:
            caret = self.layout_pag.retangulo_cursor(self.controle.cursor.position())
        espessura = 1.0 / (esc * dpr)  # 1 pixel de dispositivo em unidades de twip
        for n in range(i0, i1 + 1):
            r = self.retangulo_folha_logico(n)
            # bordas em pixel de dispositivo inteiro
            x0 = round(r.left() * dpr) / dpr
            y0 = round(r.top() * dpr) / dpr
            x1 = round(r.right() * dpr) / dpr
            y1 = round(r.bottom() * dpr) / dpr
            sombra = 2.0 / dpr
            p.fillRect(QRectF(x0 + sombra, y0 + sombra, x1 - x0, y1 - y0), COR_SOMBRA)
            p.fillRect(QRectF(x0, y0, x1 - x0, y1 - y0), QColor(255, 255, 255))
            t = QTransform()
            t.translate(x0, y0)
            t.scale(esc, esc)
            desenhar_conteudo_folha(p, self.layout_pag, n, t, self.cabecalho,
                                    selecao=self.controle.cursor if self.controle.cursor.hasSelection() else None,
                                    caret=caret, espessura_caret=espessura)
        p.end()
