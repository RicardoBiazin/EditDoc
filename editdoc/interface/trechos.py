"""Layout por trechos (experimento, ramo experimento/tabelas; ligado por EDITDOC_TRECHOS=1).

O `QTextDocumentLayout` do Qt refaz TODAS as tabelas depois do ponto editado a cada tecla
(`layoutFlow`: `if (document->pageSize().height() > 0.0f) cd->sizeDirty = true;`, ver
docs/SPIKES.md, 0.1.14 e 0.1.15). Aqui o documento do usuario (D) continua um so' (edicao,
cursor, desfazer, localizar, gravacao), mas o layout dele e' este objeto, que pagina D em
pedacos: cada trecho e' um QTextDocument proprio (copia de D entre duas tabelas do primeiro
nivel, terminando numa tabela), com o layout paginado do Qt. A tecla refaz so' o trecho dela
(uma tabela no maximo).

Para o trecho k comecar na mesma altura da pagina em que comeca em D, ele leva no comeco um
espacador (tabela 1 x 1 sem borda, com a linha de altura fixa): o layout do Qt so' depende do y
em que o trecho comeca (o bloco logo depois de uma tabela nao soma margem com o anterior, e o
espacador tambem e' uma tabela). A referencia e' a primeira linha do bloco S_k (o primeiro do
trecho), que tambem esta' no fim do trecho k-1 como copia: o trecho k-1 diz onde S_k cai, e o
espacador do trecho k e' ajustado ate' S_k cair no mesmo lugar (medido no spike: as posicoes de
todas as linhas de todos os blocos iguais as do documento inteiro nos .docx de teste).

Os QTextLayout dos blocos de D sao preenchidos com as mesmas quebras de linha e posicoes do
trecho (o cursor, as setas e o codigo do EditDoc leem `block.layout()`); a pintura e o hitTest
vem do layout do trecho.
"""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (QAbstractTextDocumentLayout, QTextBlockFormat, QTextCursor,
                           QTextDocumentFragment, QTextFormat, QTextLength, QTextTable,
                           QTextTableFormat)


def ligado() -> bool:
    return os.environ.get("EDITDOC_TRECHOS") == "1"


def instalar(doc) -> "LayoutPorTrechos":
    """Troca o layout de `doc` (um DocumentoQt recem-criado) e registra de novo os manipuladores
    que o DocumentoQt registrou no layout antigo (o Qt apaga o antigo)."""
    lay = LayoutPorTrechos(doc)
    doc.setDocumentLayout(lay)
    from editdoc.ponte_qt import marcas, notas, opacos, secoes
    doc._manipulador_opacos = opacos.registrar_manipulador(doc)
    doc._manipulador_marcas = marcas.registrar_manipulador(doc)
    doc._manipulador_notas = notas.registrar_manipulador(doc)
    doc._manipulador_quebras = secoes.registrar_manipulador(doc)
    return lay


def _formato_em(doc, pos):
    """Formato do caractere em `pos` (pelo fragmento: QTextCursor.charFormat da' o de antes)."""
    b = doc.findBlock(pos)
    it = b.begin()
    while not it.atEnd():
        fr = it.fragment()
        if fr.position() <= pos < fr.position() + fr.length():
            return fr.charFormat()
        it += 1
    return None


def _delegado(original, d, trecho):
    """Manipulador do trecho que pergunta ao de D, com D e a posicao em D: os manipuladores do
    EditDoc guardam estado por documento (reserva dos flutuantes, valor do campo por pagina)."""
    from PySide6.QtGui import QPyTextObject

    class _Delegado(QPyTextObject):
        def intrinsicSize(self, _doc, pos, fmt):  # noqa: N802
            return original.intrinsicSize(d, trecho.para_d(pos), fmt)

        def drawObject(self, painter, rect, _doc, pos, fmt):  # noqa: N802
            original.drawObject(painter, rect, d, trecho.para_d(pos), fmt)

    return _Delegado()


_TIPOS = range(QTextFormat.ObjectTypes.UserObject.value, QTextFormat.ObjectTypes.UserObject.value + 16)


class _Trecho:
    __slots__ = ("ini", "fim", "doc", "off", "esp", "h", "desloc", "alvo", "topo", "cauda", "delegados")

    def __init__(self) -> None:
        self.ini = 0       # posicao em D do primeiro caractere (S_k)
        self.fim = 0       # posicao em D do comeco do trecho seguinte (S_k+1), ou o fim de D
        self.doc = None    # o QTextDocument do trecho
        self.off = 0       # posicao no trecho que corresponde a `ini`
        self.esp = None    # tabela espacadora (None no primeiro trecho ou sem espacador)
        self.h = 0.0       # altura pedida ao espacador (twips do layout)
        self.desloc = 0.0  # y em D = y no trecho + desloc (multiplo da altura da pagina)
        self.alvo = None   # y em D da 1a linha de S_k (a referencia)
        self.topo = 0.0    # y em D a partir do qual este trecho pinta
        self.cauda = -1    # posicao no trecho da copia de S_k+1 (-1: nao ha')

    def para_trecho(self, pos: int) -> int:
        return pos - self.ini + self.off

    def para_d(self, pos: int) -> int:
        return max(self.ini, pos - self.off + self.ini)


class LayoutPorTrechos(QAbstractTextDocumentLayout):
    def __init__(self, doc) -> None:
        super().__init__(doc)
        self._d = doc
        self._trechos: list[_Trecho] = []
        self._pendente = True
        self._montando = False
        self._bbr: dict = {}
        self._tamanho = QSizeF()
        self._paginas = 0
        #: contadores para medir (quantos trechos refeitos e reespacados por mudanca)
        self.refeitos = 0
        self.reespacados = 0

    # -- montagem ---------------------------------------------------------------------------

    def _novo_doc(self, trecho):
        from editdoc.ponte_qt.imagens import DocumentoQt
        d = self._d
        c = DocumentoQt()
        c.setUndoRedoEnabled(False)
        c.setDocumentMargin(d.documentMargin())
        c.setDefaultFont(d.defaultFont())
        c.setDefaultTextOption(d.defaultTextOption())
        c.setIndentWidth(d.indentWidth())
        lc = c.documentLayout()
        lc.setPaintDevice(self.paintDevice())
        trecho.delegados = []
        for t in _TIPOS:
            h = self.handlerForObject(t)
            if h is not None:
                dg = _delegado(h, d, trecho)
                trecho.delegados.append(dg)
                lc.registerHandler(t, dg)
        # O formato do quadro raiz guarda catalogos (estilos, notas): o layout nao o usa alem das
        # margens, que sao as do documento.
        c.rootFrame().setFrameFormat(d.rootFrame().frameFormat())
        c.setPageSize(d.pageSize())
        return c

    def _inicios(self) -> list[int]:
        d = self._d
        fim = d.characterCount() - 1
        # O bloco vazio depois da ultima tabela, quando e' o fim do documento, fica no trecho dela.
        return [0] + [p for p in (f.lastPosition() + 1 for f in d.rootFrame().childFrames()
                                  if isinstance(f, QTextTable)) if p < fim]

    def _montar_trecho(self, t: _Trecho) -> None:
        d = self._d
        c = self._novo_doc(t)
        fim_copia = min(t.fim, d.characterCount() - 1)
        t.cauda = -1
        if t.fim < d.characterCount() - 1:
            bS = d.findBlock(t.fim)
            fim_copia = bS.position() + bS.length() - 1
        cur = QTextCursor(d)
        cur.setPosition(t.ini)
        cur.setPosition(fim_copia, QTextCursor.MoveMode.KeepAnchor)
        frag = QTextDocumentFragment(cur)
        cc = QTextCursor(c)
        cc.beginEditBlock()
        cc.insertFragment(frag)
        primeiro = d.findBlock(t.ini)
        cc.setPosition(0)
        cc.setBlockFormat(primeiro.blockFormat())
        cc.setBlockCharFormat(primeiro.charFormat())
        t.off = 0
        t.esp = None
        if t.ini > 0:
            tf = QTextTableFormat()
            tf.setBorder(0)
            tf.setMargin(0)
            tf.setPadding(0)
            tf.setCellPadding(0)
            tf.setCellSpacing(0)
            tf.setWidth(QTextLength(QTextLength.Type.FixedLength, 10))
            t.esp = cc.insertTable(1, 1, tf)
            vazio = QTextCursor(c)
            vazio.setPosition(0)
            vazio.setBlockFormat(QTextBlockFormat())
            t.off = t.esp.lastPosition() + 1
            depois = QTextCursor(c)
            depois.setPosition(t.off)
            depois.setBlockFormat(primeiro.blockFormat())
            depois.setBlockCharFormat(primeiro.charFormat())
        if t.fim < d.characterCount() - 1:
            t.cauda = t.para_trecho(t.fim)
            bS = d.findBlock(t.fim)
            cauda = QTextCursor(c)
            cauda.setPosition(t.cauda)
            cauda.setBlockFormat(bS.blockFormat())
            cauda.setBlockCharFormat(bS.charFormat())
        # O que o fragmento nao leva: bloco escondido (revisoes "Sem marcacao") e os formatos
        # adicionais do realce (QSyntaxHighlighter), que ficam no QTextLayout do bloco de D.
        sujo = False
        b = d.findBlock(t.ini)
        while b.isValid() and b.position() <= fim_copia:
            fmts = b.layout().formats()
            vis = b.isVisible()
            if fmts or not vis:
                sujo = True
                cb = c.findBlock(t.para_trecho(b.position()))
                if fmts:
                    cb.layout().setFormats(fmts)
                if not vis:
                    cb.setVisible(False)
            b = b.next()
        cc.endEditBlock()
        if sujo:
            c.markContentsDirty(0, c.characterCount())
        t.doc = c
        self.refeitos += 1

    def _altura_espacador(self, t: _Trecho, h: float) -> None:
        cel = t.esp.cellAt(0, 0)
        cc = cel.firstCursorPosition()
        bf = QTextBlockFormat()
        escala = self.paintDevice().logicalDpiY() / 96.0 if self.paintDevice() else 1.0
        bf.setLineHeight(max(0.0, h) / escala, QTextBlockFormat.LineHeightTypes.FixedHeight.value)
        cc.setBlockFormat(bf)
        t.h = h

    @staticmethod
    def _y_linha0(doc, bloco) -> float | None:
        lay = bloco.layout()
        if not bloco.isVisible() or lay.lineCount() == 0:
            doc.documentLayout().blockBoundingRect(bloco)
            if not bloco.isVisible() or lay.lineCount() == 0:
                return None
        # O topo do bloco (nao o da 1a linha): e' o y do layout ao comecar S. A linha que nao cabe
        # no pe' da pagina desce DENTRO do bloco, e o topo do bloco fica na pagina de cima.
        return doc.documentLayout().blockBoundingRect(bloco).y()

    def _alvo_do_anterior(self, k: int) -> float | None:
        """y em D da 1a linha de S_k, pela copia no fim do trecho k-1."""
        a = self._trechos[k - 1]
        if a.cauda < 0:
            return None
        y = self._y_linha0(a.doc, a.doc.findBlock(a.cauda))
        return None if y is None else y + a.desloc

    def _espacar(self, k: int, alvo: float | None) -> None:
        t = self._trechos[k]
        H = self._d.pageSize().height()
        if k and t.esp is None and alvo is not None and alvo != t.alvo:
            self._montar_trecho(t)  # estava sem espacador (alto da pagina): volta a ter
            t.alvo = None
        if t.esp is None or alvo is None:
            t.alvo = alvo
            return
        base = math.floor(alvo / H)
        rel = alvo - base * H
        bT = t.doc.findBlock(t.off)
        a = self._trechos[k - 1]
        if not bT.text() and a.cauda >= 0:
            # O vazio logo depois da tabela fica na borda direita dela (o Qt o "esconde" ali):
            # o espacador tem a largura da tabela de cima, para o x do vazio bater.
            xs = a.doc.documentLayout().blockBoundingRect(a.doc.findBlock(a.cauda)).x()
            escala = self.paintDevice().logicalDpiY() / 96.0 if self.paintDevice() else 1.0
            tf = t.esp.format()
            if xs > 0 and abs(tf.width().rawValue() * escala - xs) > 0.5:
                tf.setWidth(QTextLength(QTextLength.Type.FixedLength, xs / escala))
                t.esp.setFormat(tf)
        h = rel if t.alvo is None else t.h + (alvo - t.alvo)
        if t.alvo is not None and base * H != t.desloc:
            h = rel
        ok = False
        for _ in range(8):
            self._altura_espacador(t, h)
            y = self._y_linha0(t.doc, bT)
            if y is None:
                break
            d = rel - y
            if abs(d) < 1.0:  # a altura fixa anda em passos de 1 twip (arredondamento do Qt)
                ok = True
                break
            h += d
        t.desloc = base * H
        if not ok:
            # S_k comeca no alto da pagina (o espacador nao chega a zero): trecho sem espacador.
            cur = QTextCursor(t.doc)
            cur.beginEditBlock()
            cur.setPosition(0)
            cur.setPosition(t.off, QTextCursor.MoveMode.KeepAnchor)
            cur.removeSelectedText()
            prim = self._d.findBlock(t.ini)
            cur.setPosition(0)
            cur.setBlockFormat(prim.blockFormat())
            cur.setBlockCharFormat(prim.charFormat())
            cur.endEditBlock()
            t.esp = None
            if t.cauda >= 0:
                t.cauda -= t.off
            t.off = 0
            y = self._y_linha0(t.doc, t.doc.findBlock(0)) or 0.0
            t.desloc = alvo - y
        t.alvo = alvo
        self.reespacados += 1

    def _montar(self) -> None:
        if self._montando:
            return
        self._bbr.clear()
        self._montando = True
        try:
            d = self._d
            ini = self._inicios()
            fins = ini[1:] + [d.characterCount()]
            self._trechos = []
            for a, b in zip(ini, fins):
                t = _Trecho()
                t.ini, t.fim = a, b
                self._trechos.append(t)
            for k, t in enumerate(self._trechos):
                self._montar_trecho(t)
                if k:
                    self._espacar(k, self._alvo_do_anterior(k))
                t.doc.documentLayout().documentSize()
                self._topo(k)
                self._copiar_blocos(t, None)
            self._pendente = False
            self._medir()
        finally:
            self._montando = False

    def _topo(self, k: int) -> None:
        t = self._trechos[k]
        if k == 0 or t.esp is None:
            t.topo = t.desloc if k else 0.0
            return
        # Pinta a partir do fim do espacador (o fim da tabela de cima, em D).
        r = t.doc.documentLayout().frameBoundingRect(t.esp)
        t.topo = r.bottom() + t.desloc

    def _medir(self) -> None:
        if not self._trechos:
            self._tamanho = QSizeF(self._d.pageSize().width(), 0)
            self._paginas = 0
            return
        u = self._trechos[-1]
        lu = u.doc.documentLayout()
        tam = lu.documentSize()
        largura = max(t.doc.documentLayout().documentSize().width() for t in self._trechos)
        antes = (self._tamanho, self._paginas)
        self._tamanho = QSizeF(largura, tam.height() + u.desloc)
        H = self._d.pageSize().height()
        self._paginas = lu.pageCount() + (int(round(u.desloc / H)) if H > 0 else 0)
        if antes[0] != self._tamanho:
            self.documentSizeChanged.emit(self._tamanho)
        if antes[1] != self._paginas:
            self.pageCountChanged.emit(self._paginas)

    # -- copia das linhas para os blocos de D ------------------------------------------------

    def _copiar_blocos(self, t: _Trecho, faixa) -> None:
        """Preenche o QTextLayout de cada bloco de D do trecho com as linhas do trecho.
        `faixa` (de, ate) em D: esses blocos sao refeitos sempre; os outros so' se mudaram."""
        self._bbr.clear()
        d = self._d
        raiz_t = t.doc.rootFrame()
        # Os blocos antes da mudanca nao mudam (o layout e' sequencial). Depois dela, o primeiro
        # bloco do primeiro nivel que ficou igual (mesmas linhas, mesma posicao) encerra: tudo o
        # que vem depois so' depende do y em que ele comeca.
        b = d.findBlock(max(t.ini, faixa[0] - 1) if faixa is not None else t.ini)
        while b.isValid() and b.position() < t.fim:
            cb = t.doc.findBlock(t.para_trecho(b.position()))
            depois = faixa is not None and b.position() > faixa[1]
            forcar = faixa is not None and not depois and b.position() + b.length() >= faixa[0]
            na_raiz = t.doc.frameAt(cb.position()) is raiz_t
            mudou = self._copiar(b, cb, t, na_raiz, forcar)
            if depois and na_raiz and not mudou:
                break
            b = b.next()

    def _copiar(self, db, cb, t: _Trecho, na_raiz: bool, forcar: bool) -> bool:
        """True se o bloco de D mudou (linhas ou posicao)."""
        ct, dt = cb.layout(), db.layout()
        if cb.text() != db.text():
            # O trecho saiu do passo com D (uma mudanca que a copia nao repetiu igual): linha de
            # outro texto derruba o cursorToX. Bloco sem linha e remontagem de tudo.
            dt.clearLayout()
            self._divergiu = True
            return True
        n = ct.lineCount()
        pos = ct.position()
        if na_raiz:
            pos = QPointF(pos.x(), pos.y() + t.desloc)
        if not forcar and dt.lineCount() == n:
            igual = True
            for i in range(n):
                a, b = ct.lineAt(i), dt.lineAt(i)
                if a.textStart() != b.textStart() or a.textLength() != b.textLength() or \
                        a.y() != b.y() or a.x() != b.x():
                    igual = False
                    break
            if igual:
                if dt.position() != pos:
                    dt.setPosition(pos)
                    return True
                return False
        dt.setTextOption(ct.textOption())
        dt.beginLayout()
        for i in range(n):
            cl = ct.lineAt(i)
            ln = dt.createLine()
            if not ln.isValid():
                break
            ln.setLeadingIncluded(cl.leadingIncluded())
            # A mesma largura da' as mesmas quebras (mesmo texto, formatos e dispositivo); quando
            # nao da' (objeto com outra largura), forca o numero de caracteres.
            alvo = cl.textLength()
            ln.setLineWidth(cl.width())
            if ln.textLength() != alvo:
                ln.setNumColumns(alvo, cl.width())
                if ln.textLength() != alvo:
                    ln.setNumColumns(max(1, 2 * alvo - ln.textLength()), cl.width())
            ln.setPosition(cl.position())
        dt.endLayout()
        dt.setPosition(pos)
        return True

    def resizeInlineObject(self, item, pos, formato):  # noqa: N802
        """Como o `QTextDocumentLayout::resizeInlineObject`: objeto de quadro flutuante nao ocupa
        lugar na linha (o QAbstractTextDocumentLayout poria a altura inteira dele na linha)."""
        f = formato.toCharFormat()
        h = self.handlerForObject(f.objectType())
        if h is None and f.objectType() == QTextFormat.ObjectTypes.ImageObject.value:
            # O manipulador de imagem do Qt mora no QTextDocumentLayout: usa o de um documento
            # auxiliar (ele le' a imagem no documento passado, D).
            if getattr(self, "_auxiliar", None) is None:
                from PySide6.QtGui import QTextDocument
                self._auxiliar = QTextDocument()
            h = self._auxiliar.documentLayout().handlerForObject(f.objectType())
        if h is None:
            return
        tam = h.intrinsicSize(self._d, pos, formato)
        quadro = self._d.objectForFormat(f)
        if quadro is not None and hasattr(quadro, "frameFormat") and \
                quadro.frameFormat().position() != quadro.frameFormat().Position.InFlow:
            tam = QSizeF(0, 0)
        item.setWidth(tam.width())
        if f.verticalAlignment() == f.VerticalAlignment.AlignMiddle:
            from PySide6.QtGui import QFontMetrics
            meio = QFontMetrics(f.font()).xHeight() / 2.0
            item.setAscent((tam.height() + meio) / 2.0)
            item.setDescent((tam.height() - meio) / 2.0)
        else:
            item.setDescent(0)
            item.setAscent(tam.height())

    # -- consultas ---------------------------------------------------------------------------

    def _garantir(self) -> None:
        if self._pendente and not self._montando:
            self._montar()

    def _dono(self, pos: int) -> int:
        tr = self._trechos
        lo, hi = 0, len(tr) - 1
        while lo < hi:
            m = (lo + hi + 1) // 2
            if tr[m].ini <= pos:
                lo = m
            else:
                hi = m - 1
        return lo

    def _dono_y(self, y: float) -> int:
        k = 0
        for i, t in enumerate(self._trechos):
            if t.topo <= y:
                k = i
            else:
                break
        return k

    def blockBoundingRect(self, bloco):  # noqa: N802
        if not bloco.isValid() or not bloco.isVisible() or self._d.pageSize().isNull():
            return QRectF()
        self._garantir()
        if not self._trechos:
            return QRectF()
        # Cache ate' a mudanca seguinte: o EditDoc pede o retangulo de cada bloco muitas vezes
        # por pintura, e aqui cada pedido e' uma chamada em Python.
        guardado = self._bbr.get(bloco.position())
        if guardado is not None and bloco.layout().lineCount():
            return QRectF(guardado)
        t = self._trechos[self._dono(bloco.position())]
        if t.doc is None:
            return QRectF()  # chamada de dentro da montagem (cursor de D)
        cb =t.doc.findBlock(t.para_trecho(bloco.position()))
        r = t.doc.documentLayout().blockBoundingRect(cb)
        if r.isNull():
            return r
        # Linhas que faltam (o Qt limpou o layout do bloco ao mudar o texto): so' se o trecho ja'
        # tem o mesmo texto. Dentro de um bloco de edicao aberto o trecho ainda e' o de antes, e
        # linhas de outro texto derrubam o processo no cursorToX (medido em teste_listas).
        if bloco.layout().lineCount() != cb.layout().lineCount() and cb.text() == bloco.text():
            self._copiar(bloco, cb, t, t.doc.frameAt(cb.position()) is t.doc.rootFrame(), True)
        r = r.translated(0, t.desloc)
        if not self._montando:
            self._bbr[bloco.position()] = QRectF(r)
        return r

    def frameBoundingRect(self, quadro):  # noqa: N802
        self._garantir()
        if quadro is self._d.rootFrame() or quadro.parentFrame() is None:
            return QRectF(QPointF(0, 0), self._tamanho)
        if not self._trechos:
            return QRectF()
        if not isinstance(quadro, QTextTable):
            # Quadro de objeto (flutuante): nao tem texto; acha pelo caractere da ancora.
            pos = self._ancoras().get(quadro.objectIndex())
            if pos is not None:
                t = self._trechos[self._dono(pos)]
                fmt = _formato_em(t.doc, t.para_trecho(pos))
                obj = t.doc.object(fmt.objectIndex()) if fmt is not None else None
                if obj is not None:
                    return t.doc.documentLayout().frameBoundingRect(obj).translated(0, t.desloc)
        t = self._trechos[self._dono(quadro.firstPosition())]
        p = t.para_trecho(quadro.firstPosition())
        f = t.doc.frameAt(p)
        while f is not None and f.firstPosition() != p:
            f = f.parentFrame()
        if f is None:
            return QRectF()
        return t.doc.documentLayout().frameBoundingRect(f).translated(0, t.desloc)

    def _ancoras(self) -> dict:
        """objectIndex -> posicao em D do caractere de objeto (cache pela revisao)."""
        rev = self._d.revision()
        if getattr(self, "_rev_ancoras", None) != rev:
            mapa = {}
            b = self._d.begin()
            while b.isValid():
                it = b.begin()
                while not it.atEnd():
                    fr = it.fragment()
                    idx = fr.charFormat().objectIndex()
                    if idx >= 0 and "￼" in fr.text():
                        mapa[idx] = fr.position()
                    it += 1
                b = b.next()
            self._mapa_ancoras = mapa
            self._rev_ancoras = rev
        return self._mapa_ancoras

    def documentSize(self):  # noqa: N802
        self._garantir()
        return QSizeF(self._tamanho)

    def pageCount(self):  # noqa: N802
        self._garantir()
        return self._paginas

    def hitTest(self, ponto, precisao):  # noqa: N802
        self._garantir()
        if not self._trechos:
            return -1
        k = self._dono_y(ponto.y())
        t = self._trechos[k]
        p = t.doc.documentLayout().hitTest(QPointF(ponto.x(), ponto.y() - t.desloc), precisao)
        if p < 0:
            return p
        if t.cauda >= 0 and p >= t.cauda:
            p = t.cauda - 1
        return t.para_d(p)

    def draw(self, painter, contexto):  # noqa: N802
        self._garantir()
        clip = contexto.clip
        tr = self._trechos
        for k, t in enumerate(tr):
            y0 = t.topo
            y1 = tr[k + 1].topo if k + 1 < len(tr) else float("inf")
            if clip.isValid() and (clip.bottom() < y0 or clip.top() >= y1):
                continue
            c2 = QAbstractTextDocumentLayout.PaintContext()
            c2.palette = contexto.palette
            c2.cursorPosition = -1
            if contexto.cursorPosition >= 0 and t.ini <= contexto.cursorPosition < t.fim:
                c2.cursorPosition = t.para_trecho(contexto.cursorPosition)
            faixa = QRectF(-1e7, y0, 2e7, min(y1, 1e9) - y0)
            c2.clip = (clip.intersected(faixa) if clip.isValid() else faixa).translated(0, -t.desloc)
            sels = []
            for s in contexto.selections:
                a, b = s.cursor.selectionStart(), s.cursor.selectionEnd()
                a, b = max(a, t.ini), min(b, t.fim)
                if a >= b and not (s.format.boolProperty(QTextFormat.Property.FullWidthSelection)
                                   and t.ini <= s.cursor.position() < t.fim):
                    continue
                n = QAbstractTextDocumentLayout.Selection()
                cc = QTextCursor(t.doc)
                if a < b:
                    cc.setPosition(t.para_trecho(a))
                    cc.setPosition(t.para_trecho(b), QTextCursor.MoveMode.KeepAnchor)
                else:
                    cc.setPosition(t.para_trecho(s.cursor.position()))
                n.cursor = cc
                n.format = s.format
                sels.append(n)
            c2.selections = sels
            painter.save()
            painter.setClipRect(faixa, Qt.ClipOperation.IntersectClip if painter.hasClipping()
                                else Qt.ClipOperation.ReplaceClip)
            painter.translate(0, t.desloc)
            t.doc.documentLayout().draw(painter, c2)
            painter.restore()

    # -- mudancas ----------------------------------------------------------------------------

    def documentChanged(self, de, removidos, inseridos):  # noqa: N802
        d = self._d
        self._bbr.clear()
        if self._montando:
            return
        total = d.characterCount()
        if self._pendente or not self._trechos or (de == 0 and inseridos >= total - 1) or \
                d.pageSize().isNull():
            if not self._pendente:
                self._motivo('inteiro', de, removidos, inseridos)
            self._invalidar()
            return
        self._divergiu = False
        if not self._mudanca(de, removidos, inseridos) or self._divergiu:
            if self._divergiu:
                self._motivo('divergiu', de, removidos, inseridos)
            self._invalidar()
            return
        self._medir()
        self.update[QRectF].emit(QRectF(0, 0, 1e9, 1e9))

    def _motivo(self, nome, *args) -> None:
        m = self.__dict__.setdefault('motivos', {})
        m.setdefault(nome, []).append(args)

    def _invalidar(self) -> None:
        # As linhas dos blocos de D ficam velhas: a consulta seguinte remonta tudo. Ate' la', bloco
        # sem linha (como o Qt deixa o bloco que mudou): linha de outro texto derruba o cursorToX.
        # O Qt ja' limpou as linhas dos blocos cujo texto mudou; os outros ficam com as linhas
        # de antes ate' a remontagem (na consulta seguinte, ou no laco de eventos).
        self._pendente = True
        # Como o QTextDocumentLayout, o layout fica pronto logo depois da mudanca: o EditDoc le'
        # `block.layout()` sem pedir o retangulo antes (com o bloco sem linha, o
        # `lineAt(lineCount() - 1)` de `retangulo_cursor_em` derruba o processo).
        if self._trechos and not self._d.pageSize().isNull() and not self._montando:
            self._montar()
            return
        if not getattr(self, "_agendado", False):
            from PySide6.QtCore import QTimer
            self._agendado = True
            QTimer.singleShot(0, self._remontar_agendado)

    def _remontar_agendado(self) -> None:
        self._agendado = False
        if self._pendente and not self._d.pageSize().isNull():
            self._montar()
        self.update[QRectF].emit(QRectF(0, 0, 1e9, 1e9))

    def _mudanca(self, de: int, removidos: int, inseridos: int) -> bool:
        """Repete a mudanca de D no trecho dela. False: estrutura mudou (refazer tudo)."""
        d = self._d
        ini = self._inicios()
        delta = inseridos - removidos
        tr = self._trechos
        if len(ini) != len(tr):
            self._motivo('tabelas', de, removidos, inseridos)
            return False
        k = self._dono(de)
        t = tr[k]
        fim_antigo = de + removidos
        # A mudanca tem de caber num trecho (sem atravessar o comeco do seguinte)...
        if k + 1 < len(tr) and fim_antigo >= tr[k + 1].ini and not (de == tr[k + 1].ini):
            self._motivo('atravessa', de, removidos, inseridos)
            return False
        # ... e nao mexer na fronteira das tabelas do primeiro nivel.
        for j in range(len(tr)):
            esperado = tr[j].ini + (delta if tr[j].ini > de else 0)
            if ini[j] != esperado:
                self._motivo('fronteira', de, removidos, inseridos)
                return False
        so_formato = removidos == inseridos and self._sincronizar_formatos(t, de, inseridos)
        if not so_formato and not self._repetir(t, de, removidos, inseridos):
            self._motivo('celula', de, removidos, inseridos)
            return False
        # A copia de S_k (fim do trecho k-1) muda junto quando a mudanca e' no 1o bloco.
        afetou_cauda_anterior = False
        if k > 0:
            a = tr[k - 1]
            bS = d.findBlock(t.ini)
            if de <= bS.position() + bS.length() and a.cauda >= 0:
                afetou_cauda_anterior = True
        for j in range(k + 1, len(tr)):
            tr[j].ini += delta
            tr[j].fim += delta
        t.fim += delta
        if t.cauda >= 0:
            t.cauda += delta
        t.doc.documentLayout().documentSize()
        self._copiar_blocos(t, (de, de + inseridos))
        if afetou_cauda_anterior:
            a = tr[k - 1]
            self._montar_trecho(a)
            if k - 1:
                a.alvo = None
                self._espacar(k - 1, self._alvo_do_anterior(k - 1))
            a.doc.documentLayout().documentSize()
            self._topo(k - 1)
            self._copiar_blocos(a, None)
            self._espacar(k, self._alvo_do_anterior(k))
            self._topo(k)
            self._copiar_blocos(t, None)
        # Cascata so' se o fim do trecho mudou de lugar.
        j = k + 1
        while j < len(tr):
            alvo = self._alvo_do_anterior(j)
            if alvo == tr[j].alvo:
                break
            self._espacar(j, alvo)
            tr[j].doc.documentLayout().documentSize()
            self._topo(j)
            self._copiar_blocos(tr[j], None)
            j += 1
        return True

    def _sincronizar_formatos(self, t: _Trecho, de: int, n: int) -> bool:
        """Mudanca so' de formato (mesmo texto, mesmo tamanho): copia formatos de bloco, de
        caractere, de tabela e de celula, sem trocar o texto (o formato de celula atravessa
        celulas, e trocar o texto ali partiria a grade). False: o texto nao e' o mesmo."""
        d, c = self._d, t.doc
        p = t.para_trecho(de)
        if p + n > c.characterCount() or de + n > d.characterCount():
            return False
        sd, sc = QTextCursor(d), QTextCursor(c)
        sd.setPosition(de)
        sd.setPosition(de + n, QTextCursor.MoveMode.KeepAnchor)
        sc.setPosition(p)
        sc.setPosition(p + n, QTextCursor.MoveMode.KeepAnchor)
        if sd.selectedText() != sc.selectedText():
            return False
        cur = QTextCursor(c)
        cur.beginEditBlock()
        b = d.findBlock(de)
        while b.isValid() and b.position() <= de + n:
            cb = c.findBlock(t.para_trecho(b.position()))
            bc = QTextCursor(cb)
            if cb.blockFormat() != b.blockFormat():
                bc.setBlockFormat(b.blockFormat())
            if cb.charFormat() != b.charFormat():
                bc.setBlockCharFormat(b.charFormat())
            if cb.isVisible() != b.isVisible():
                cb.setVisible(b.isVisible())
            fmts = b.layout().formats()
            if fmts != cb.layout().formats():
                cb.layout().setFormats(fmts)
            # Os fragmentos (posicao, tamanho, formato) iguais: nada a copiar no bloco.
            fd, fc_ = [], []
            it = b.begin()
            while not it.atEnd():
                fr = it.fragment()
                fd.append((t.para_trecho(fr.position()), fr.length(), fr.charFormat()))
                it += 1
            it = cb.begin()
            while not it.atEnd():
                fr = it.fragment()
                fc_.append((fr.position(), fr.length(), fr.charFormat()))
                it += 1
            if len(fd) == len(fc_) and all(
                    a[0] == z[0] and a[1] == z[1] and (a[2] == z[2] or a[2].objectIndex() >= 0)
                    for a, z in zip(fd, fc_)) and not any(a[2].objectIndex() >= 0 for a in fd):
                b = b.next()
                continue
            it = b.begin()
            while not it.atEnd():
                fr = it.fragment()
                cf = fr.charFormat()
                q = t.para_trecho(fr.position())
                if cf.objectIndex() >= 0:
                    # O indice do objeto e' de D: copia o formato do quadro, nao o indice.
                    od = d.object(cf.objectIndex())
                    fc = _formato_em(c, q)
                    oc = c.object(fc.objectIndex()) if fc is not None and fc.objectIndex() >= 0 else None
                    if od is not None and oc is not None and hasattr(od, "frameFormat") and \
                            oc.frameFormat() != od.frameFormat():
                        oc.setFrameFormat(od.frameFormat())
                else:
                    fc = _formato_em(c, q)
                    if fc is None or fc != cf:
                        s = QTextCursor(c)
                        s.setPosition(q)
                        s.setPosition(q + fr.length(), QTextCursor.MoveMode.KeepAnchor)
                        s.setCharFormat(cf)
                it += 1
            b = b.next()
        # Tabelas e celulas tocadas.
        vistas = set()
        b = d.findBlock(de)
        while b.isValid() and b.position() <= de + n:
            tab = QTextCursor(b).currentTable()
            if tab is not None and tab.firstPosition() not in vistas:
                vistas.add(tab.firstPosition())
                ct = QTextCursor(c)
                ct.setPosition(t.para_trecho(tab.firstPosition()))
                tc = ct.currentTable()
                if tc is not None and tc.rows() == tab.rows() and tc.columns() == tab.columns():
                    if tc.format() != tab.format():
                        tc.setFormat(tab.format())
                    for r in range(tab.rows()):
                        for col in range(tab.columns()):
                            a, z = tab.cellAt(r, col), tc.cellAt(r, col)
                            if a.isValid() and z.isValid() and a.format() != z.format():
                                z.setFormat(a.format().toTableCellFormat())
            b = b.next()
        cur.endEditBlock()
        c.markContentsDirty(p, max(1, n))
        return True

    def _repetir(self, t: _Trecho, de: int, removidos: int, inseridos: int) -> bool:
        """Aplica no trecho t a troca de [de, de+removidos) pelo texto de D em [de, de+inseridos).
        So' dentro de uma celula, ou fora de tabela sem tabela no meio."""
        d = self._d
        c = t.doc
        # Objeto com quadro (flutuante) entrando: o fragmento nao recria o quadro no trecho do
        # mesmo jeito (medido: o desfazer do Delete trazia o objeto sem o texto contornar).
        if inseridos:
            b = d.findBlock(de)
            while b.isValid() and b.position() <= de + inseridos:
                it = b.begin()
                while not it.atEnd():
                    fr = it.fragment()
                    if de <= fr.position() < de + inseridos and fr.charFormat().objectIndex() >= 0:
                        return False
                    it += 1
                b = b.next()
        a_d = QTextCursor(d)
        a_d.setPosition(de)
        b_d = QTextCursor(d)
        b_d.setPosition(min(de + inseridos, d.characterCount() - 1))
        ta, tb = a_d.currentTable(), b_d.currentTable()
        if (ta is None) != (tb is None):
            return False
        if ta is not None:
            if ta != tb or ta.cellAt(de) != tb.cellAt(b_d.position()):
                return False
        p = t.para_trecho(de)
        a_t = QTextCursor(c)
        a_t.setPosition(p)
        b_t = QTextCursor(c)
        b_t.setPosition(min(p + removidos, c.characterCount() - 1))
        sa, sb = a_t.currentTable(), b_t.currentTable()
        if (sa is None) != (sb is None) or (sa is not None and sa.cellAt(p) != sb.cellAt(b_t.position())):
            return False
        cur = QTextCursor(c)
        cur.beginEditBlock()
        if removidos:
            cur.setPosition(p)
            cur.setPosition(p + removidos, QTextCursor.MoveMode.KeepAnchor)
            cur.removeSelectedText()
        if inseridos:
            sel = QTextCursor(d)
            sel.setPosition(de)
            sel.setPosition(de + inseridos, QTextCursor.MoveMode.KeepAnchor)
            cur.setPosition(p)
            cur.insertFragment(QTextDocumentFragment(sel))
        # Formato de bloco, de caractere do bloco, visibilidade e realce de cada bloco tocado.
        b = d.findBlock(de)
        fim = de + inseridos
        while b.isValid() and b.position() <= fim:
            cb = c.findBlock(t.para_trecho(b.position()))
            bc = QTextCursor(cb)
            if cb.blockFormat() != b.blockFormat():
                bc.setBlockFormat(b.blockFormat())
            if cb.charFormat() != b.charFormat():
                bc.setBlockCharFormat(b.charFormat())
            if cb.isVisible() != b.isVisible():
                cb.setVisible(b.isVisible())
            fmts = b.layout().formats()
            if fmts != cb.layout().formats():
                cb.layout().setFormats(fmts)
            b = b.next()
        cur.endEditBlock()
        if inseridos == removidos:
            c.markContentsDirty(p, max(1, inseridos))
        return True
