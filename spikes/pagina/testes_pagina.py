"""Suite do Spike A (visao em paginas sobre QTextDocument).

Uso:
  .venv\\Scripts\\python.exe spikes\\pagina\\testes_pagina.py            (todos)
  .venv\\Scripts\\python.exe spikes\\pagina\\testes_pagina.py C1 C4      (um subconjunto)
  QT_SCALE_FACTOR=1.5 ...testes_pagina.py C10                             (HiDPI)

Teclas e mouse sao enviados com QTest.keyClick / mouseClick. Os numeros
impressos saem das medidas; um criterio nao e ajustado para passar.
"""
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import time
import hashlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6 import QtWidgets
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import (QColor, QImage, QPainter, QTextBlockFormat, QTextCharFormat, QTextImageFormat,
                           QTextCursor, QTextDocument, QTextDocumentFragment, QTextFrameFormat,
                           QTextLength, QTextTable, QTextTableFormat, QTransform, QFont, QTextOption)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from layout_paginado import LayoutPaginado, ConfigPagina, TWIPS_POR_PX96, criar_dispositivo_layout
from cabecalho_rodape import CabecalhoRodape
from vista import VistaPaginas, desenhar_conteudo_folha, COR_SELECAO
from exportacao import exportar_pdf, criar_previa, contar_paginas_pdf, pintar_pagina_em

SAIDA = os.environ.get(
    "SPIKE_SAIDA",
    os.path.join(tempfile.gettempdir(), "editdoc-spike-pagina"),
)
os.makedirs(SAIDA, exist_ok=True)

M = QTextCursor.MoveOperation
MODO_SEL = QTextCursor.MoveMode.KeepAnchor
CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
NADA = Qt.KeyboardModifier.NoModifier
ESQ = Qt.MouseButton.LeftButton

RESULTADOS = []
PALAVRAS = ("documento texto página relatório ação coração pagamento fórmula alteração contábil "
            "código acentuação têxtil órgão índice após então configuração parágrafo quebra tabela "
            "célula edição revisão conteúdo número ordem").split()


def p95(v):
    v = sorted(v)
    return v[max(0, math.ceil(0.95 * len(v)) - 1)]


def registrar(cid, medido, passa, obs=""):
    RESULTADOS.append({"id": cid, "medido": medido, "passa": passa, "obs": obs})
    marca = "PASSA" if passa else ("PENDENTE MANUAL" if passa is None else "FALHA")
    print(f"{cid} | {medido} | {marca}" + (f" | {obs}" if obs else ""), flush=True)


def frase(rng, n):
    return " ".join(rng.choice(PALAVRAS) for _ in range(n)).capitalize() + "."


def construir_documento(paragrafos: int, tabelas: int, seed: int = 7, cor_cabecalho=None):
    """Documento gerado por codigo: paragrafos com 4 a 9 frases e tabelas 6x3 com cabecalho."""
    rng = random.Random(seed)
    lay = LayoutPaginado()
    cur = QTextCursor(lay.doc)
    intervalo = max(1, paragrafos // (tabelas + 1)) if tabelas else 0
    feitas = 0
    for i in range(paragrafos):
        cur.movePosition(M.End)
        cur.insertText(" ".join(frase(rng, rng.randint(8, 16)) for _ in range(rng.randint(4, 9))))
        cur.insertBlock()
        if tabelas and intervalo and (i + 1) % intervalo == 0 and feitas < tabelas:
            cur.movePosition(M.End)
            inserir_tabela(cur, lay, rng, linhas=6, colunas=3, cor_cabecalho=cor_cabecalho)
            feitas += 1
    return lay


def inserir_tabela(cur, lay, rng, linhas=6, colunas=3, cor_cabecalho=None, texto_longo=False):
    fmt = QTextTableFormat()
    fmt.setBorder(0.75)
    fmt.setCellPadding(3)
    fmt.setCellSpacing(0)
    fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
    fmt.setHeaderRowCount(1)
    tab = cur.insertTable(linhas, colunas, fmt)
    for r in range(linhas):
        for c in range(colunas):
            cel = tab.cellAt(r, c)
            if r == 0 and cor_cabecalho is not None:
                cf = cel.format()
                cf.setBackground(cor_cabecalho)
                cel.setFormat(cf)
            n_frases = rng.randint(2, 4) if texto_longo else 1
            txt = " ".join(frase(rng, rng.randint(6, 12)) for _ in range(n_frases))
            celcur = QTextCursor(lay.doc)
            celcur.setPosition(cel.firstCursorPosition().position())
            celcur.insertText(f"L{r}C{c}: " + txt)
    cur.setPosition(tab.lastPosition() if hasattr(tab, "lastPosition") else cur.position())
    cur.movePosition(M.End)
    return tab


def calibrar_paragrafos_100() -> int:
    """Numero de paragrafos que da ~100 paginas (calibracao, sem cronometrar)."""
    base = 400
    lay = construir_documento(base, 10)
    paginas = lay.numero_paginas()
    lay.fechar()
    return max(50, int(round(base * 100 / max(1, paginas))))


_ALVO_100 = None


def documento_100_paginas():
    global _ALVO_100
    if _ALVO_100 is None:
        _ALVO_100 = calibrar_paragrafos_100()
    lay = construir_documento(_ALVO_100, 10)
    return lay, _ALVO_100


def linhas_cruzando(lay, hb=None):
    """Conta linhas do documento que atravessam uma fronteira de pagina."""
    hb = hb or lay.hb
    ruins = 0
    total = 0
    b = lay.doc.firstBlock()
    while b.isValid():
        lo = b.layout()
        o = lay.origem_bloco(b)
        for j in range(lo.lineCount()):
            ln = lo.lineAt(j)
            topo = o.y() + ln.y()
            base = topo + ln.height()
            total += 1
            if math.floor(topo / hb + 1e-9) != math.floor((base - 1e-6) / hb):
                ruins += 1
        b = b.next()
    return ruins, total


def clicar_pos(vista, pos: int, shift: bool = False):
    """Clique real (QTest) no ponto do texto em `pos`, rolando se preciso."""
    r = vista.layout_pag.retangulo_cursor(pos)
    vista.garantir_visivel(r)
    pt = vista.doc_para_widget(QPointF(r.x(), r.center().y()))
    QTest.mouseClick(vista.viewport(), ESQ, SHIFT if shift else NADA, _ponto(pt))


def digitar(vista, texto: str) -> None:
    """Digita texto. ASCII vai por QTest.keyClick. Acentos vao por QKeyEvent com text().

    Achado: QTest.keyClick com caractere nao ASCII insere 0xC3 (primeiro byte UTF-8),
    e QTest.keyClicks com texto acentuado derruba o processo (exit 127). O evento
    com text() e o que o Windows entrega ao Qt depois de uma tecla morta.
    """
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    for ch in texto:
        if ord(ch) < 128:
            QTest.keyClick(vista, ch)
        else:
            QApplication.sendEvent(vista, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_unknown, NADA, ch))


def _ponto(p: QPointF):
    from PySide6.QtCore import QPoint
    return QPoint(int(round(p.x())), int(round(p.y())))


def nova_vista(lay, cab=None, w=1200, h=800):
    v = VistaPaginas(lay, cab)
    v.definir_piscar(False)
    v.resize(w, h)
    v.show()
    app.processEvents()
    return v


def cor_perto(c: QColor, alvo: QColor, tol: int = 10) -> bool:
    return (abs(c.red() - alvo.red()) <= tol and abs(c.green() - alvo.green()) <= tol
            and abs(c.blue() - alvo.blue()) <= tol)


def contar_cor(img: QImage, rect: QRectF, alvo: QColor, tol: int = 10) -> int:
    x0, y0 = max(0, int(rect.left())), max(0, int(rect.top()))
    x1, y1 = min(img.width(), int(rect.right())), min(img.height(), int(rect.bottom()))
    n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if cor_perto(img.pixelColor(x, y), alvo, tol):
                n += 1
    return n


# --------------------------------------------------------------------------- C1
def c1():
    global _ALVO_100
    if _ALVO_100 is None:
        _ALVO_100 = calibrar_paragrafos_100()
    t0 = time.perf_counter()
    lay = construir_documento(_ALVO_100, 10)
    t_build = time.perf_counter() - t0
    t1 = time.perf_counter()
    paginas = lay.numero_paginas()
    t_layout = time.perf_counter() - t1
    linhas = linhas_cruzando(lay)[1]
    tabelas = sum(1 for _ in _tabelas(lay))
    t_inicial = t_build + t_layout
    v = nova_vista(lay, CabecalhoRodape(lay))

    # edicao no meio: clique real, depois keyClick cronometrado
    rng = random.Random(3)
    n_doc = lay.doc.characterCount() - 1
    tempos = []
    for _ in range(100):
        p = rng.randrange(n_doc // 4, 3 * n_doc // 4)
        clicar_pos(v, p)
        app.processEvents()
        t = time.perf_counter()
        QTest.keyClick(v, Qt.Key.Key_X)
        tempos.append((time.perf_counter() - t) * 1000)
        QTest.keyClick(v, Qt.Key.Key_Backspace)
    edit_p95 = p95(tempos)

    # pintura de um quadro por zoom
    cpu_antes = bench_cpu()
    pintura = {}
    pintura_med = {}
    pe_p95 = {}
    for z in (0.25, 1.0, 4.0):
        v.definir_zoom(z)
        v.rolar_para_pagina(paginas // 2)
        app.processEvents()
        v.grab()  # aquecimento (fontes e caches de glifo)
        fr = []
        pe = []
        for _ in range(30):
            t = time.perf_counter()
            v.grab()
            fr.append((time.perf_counter() - t) * 1000)
            t = time.perf_counter()
            v.viewport().repaint()  # so o paintEvent do viewport, sem a captura
            pe.append((time.perf_counter() - t) * 1000)
        pintura[z] = round(p95(fr), 2)
        pintura_med[z] = round(sorted(fr)[len(fr) // 2], 2)
        pe_p95[z] = round(p95(pe), 2)

    orfas, viuvas = contar_orfas_viuvas(lay)
    ok = (t_inicial < 1.0 and edit_p95 < 50.0 and all(x < 16.0 for x in pintura.values()))
    cpu_depois = bench_cpu()
    pe_txt = (f"paintEvent sincrono p95 25%={pe_p95[0.25]} / 100%={pe_p95[1.0]} / 400%={pe_p95[4.0]} ms; "
              f"referencia de CPU (3M somas) antes {cpu_antes:.0f} ms, depois {cpu_depois:.0f} ms")
    registrar("C1", (f"{paginas} pag, {linhas} linhas, {tabelas} tabelas | layout inicial {t_inicial:.3f} s "
                     f"(build {t_build:.3f} + layout {t_layout:.3f}) | edicao p95 {edit_p95:.1f} ms | "
                     f"pintura p95 25%={pintura[0.25]} ms (med {pintura_med[0.25]}), 100%={pintura[1.0]} ms "
                     f"(med {pintura_med[1.0]}), 400%={pintura[4.0]} ms (med {pintura_med[4.0]})"),
              ok, f"pintura = viewport.grab() 1200x800, 30 quadros; {pe_txt}; orfas (1a linha no fim da pagina) {orfas}, "
                  f"viuvas (ultima linha sozinha no topo) {viuvas}")
    return {"paginas": paginas, "linhas": linhas, "tabelas": tabelas, "layout_inicial_s": t_inicial,
            "edicao_p95_ms": edit_p95, "pintura_p95_ms": pintura}


def contar_orfas_viuvas(lay):
    """Paragrafos com 2+ linhas que deixam uma linha sozinha numa pagina (Qt nao faz controle)."""
    orfas = viuvas = 0
    b = lay.doc.firstBlock()
    while b.isValid():
        lo = b.layout()
        n = lo.lineCount()
        if n >= 2 and b.textList() is None:
            o = lay.origem_bloco(b)
            pag = [lay.pagina_de_y(o.y() + lo.lineAt(j).y()) for j in range(n)]
            if pag[0] != pag[1]:
                orfas += 1
            if pag[-2] != pag[-1]:
                viuvas += 1
        b = b.next()
    return orfas, viuvas


def bench_cpu() -> float:
    """Referencia de velocidade da maquina no momento (3 M de somas em Python), em ms."""
    t = time.perf_counter()
    acc = 0
    for i in range(3000000):
        acc += i
    return (time.perf_counter() - t) * 1000


def _tabelas(lay):
    """Tabelas do documento (QTextFrame que e QTextTable)."""
    out = []
    for f in lay.doc.rootFrame().childFrames():
        if isinstance(f, QTextTable):
            out.append(f)
    if not out:
        # fallback: varredura de frames filhos de frames filhos
        pilha = list(lay.doc.rootFrame().childFrames())
        while pilha:
            f = pilha.pop()
            if isinstance(f, QTextTable):
                out.append(f)
            pilha.extend(f.childFrames())
    return out


# --------------------------------------------------------------------------- C2
def c2():
    lay = documento_100_paginas()[0]
    v = nova_vista(lay, CabecalhoRodape(lay))
    rng = random.Random(11)
    ruins_total = 0
    ruins_final = 0
    total_linhas = 0
    for _ in range(100):
        n_doc = lay.doc.characterCount() - 1
        clicar_pos(v, rng.randrange(0, n_doc))
        acao = rng.random()
        if acao < 0.5:
            digitar(v, "".join(rng.choice("abcdefghijklmnopqrstuvwxyz ãéçõ") for _ in range(rng.randint(3, 40))))
        elif acao < 0.7:
            QTest.keyClick(v, Qt.Key.Key_Return)
        elif acao < 0.85:
            QTest.keyClick(v, Qt.Key.Key_Backspace)
        else:
            QTest.keyClick(v, Qt.Key.Key_Delete)
        app.processEvents()
        r, t = linhas_cruzando(lay)
        ruins_total += r
        total_linhas = t
    ruins_final = linhas_cruzando(lay)[0]
    paginas = lay.numero_paginas()
    # controle negativo: fronteira deslocada 73 twips TEM de acusar linhas cruzando
    controle_neg = linhas_cruzando(lay, hb=lay.hb + 73)[0]
    ok = ruins_total == 0 and controle_neg > 0
    registrar("C2", (f"100 edicoes: {ruins_total} linhas cruzando (somadas as 100 verificacoes); "
                     f"final {ruins_final}; {total_linhas} linhas, {paginas} pag; "
                     f"controle negativo (fronteira +73 tw) acusa {controle_neg}"), ok)
    return {"linhas_cruzando_soma": ruins_total, "linhas_cruzando_final": ruins_final}


# --------------------------------------------------------------------------- C3
def c3(zooms=(0.25, 1.0, 4.0), n=1000):
    lay = documento_100_paginas()[0]
    v = nova_vista(lay, CabecalhoRodape(lay))
    rng = random.Random(5)
    total_falhas = 0
    detalhe = {}
    for z in zooms:
        v.definir_zoom(z)
        falhas = 0
        maior = 0
        fracionarias = 0
        for _ in range(n):
            o_x = rng.uniform(0, max(1.0, v.horizontalScrollBar().maximum() + 1))
            o_y = rng.uniform(0, max(1.0, v.verticalScrollBar().maximum() + 1))
            v.definir_origem(o_x, o_y)
            o = v.origem()
            if (o.x() % 1) > 1e-9 or (o.y() % 1) > 1e-9:
                fracionarias += 1
            p = rng.randrange(0, lay.doc.characterCount() - 1)
            r = lay.retangulo_cursor(p)
            w = v.doc_para_widget(QPointF(r.x(), r.center().y()))
            p2 = v.posicao_em(w)
            d = abs(p2 - p)
            maior = max(maior, d)
            if d > 1:
                falhas += 1
        detalhe[z] = (falhas, maior, fracionarias)
        total_falhas += falhas
    # controle negativo: deslocar o ponto 3 linhas para baixo TEM de quebrar a volta
    v.definir_zoom(1.0)
    v.definir_origem(0, 0)
    fal_ctl = 0
    for _ in range(300):
        p = rng.randrange(0, lay.doc.characterCount() - 1)
        r = lay.retangulo_cursor(p)
        w = v.doc_para_widget(QPointF(r.x(), r.center().y()))
        w2 = QPointF(w.x(), w.y() + 3 * 246 * v.escala())
        if abs(v.posicao_em(w2) - p) > 1:
            fal_ctl += 1
    ctl_ok = fal_ctl > 0
    ok = total_falhas == 0 and ctl_ok
    partes = ", ".join(f"{int(z*100)}%: {detalhe[z][0]} falhas (maior dif {detalhe[z][1]}, "
                       f"origem fracionaria em {detalhe[z][2]}/{n})" for z in zooms)
    registrar("C3", f"{n*len(zooms)} ida-e-volta | {partes} | controle (3 linhas de deslocamento) acusa {fal_ctl}/300", ok)
    return {"falhas": {str(z): detalhe[z][0] for z in zooms}}


# --------------------------------------------------------------------------- C4
def c4():
    lay = documento_100_paginas()[0]
    v = nova_vista(lay, CabecalhoRodape(lay))
    v.definir_zoom(1.0)
    hb = lay.hb
    v.rolar_para_pagina(1)
    app.processEvents()
    p_ini = lay.doc.documentLayout().hitTest(QPointF(lay.config.larg_corpo / 2, 1 * hb + 1500), Qt.FuzzyHit)
    clicar_pos(v, p_ini)
    v.rolar_para_pagina(6)
    app.processEvents()
    p_fim = lay.doc.documentLayout().hitTest(QPointF(lay.config.larg_corpo / 2, 6 * hb + 1500), Qt.FuzzyHit)
    QTest.mouseClick(v.viewport(), ESQ, SHIFT, _ponto(v.doc_para_widget(QPointF(lay.config.larg_corpo / 2, 6 * hb + 1500))))
    app.processEvents()
    cur = v.controle.cursor
    sel_ok = cur.hasSelection()
    pag_ini = lay.pagina_de_y(lay.doc.documentLayout().blockBoundingRect(lay.doc.findBlock(min(cur.anchor(), cur.position()))).top())
    pag_fim = lay.pagina_de_y(lay.doc.documentLayout().blockBoundingRect(lay.doc.findBlock(max(cur.anchor(), cur.position()))).top())
    # pixels azuis por pagina (cada pagina visivel no viewport, pela area do corpo)
    azuis = {}
    for n in range(0, 8):
        v.rolar_para_pagina(n)
        app.processEvents()
        img = v.grab().toImage()
        r = v.retangulo_folha_logico(n)
        corpo = QRectF(r.left() + lay.config.margem_esq * v.escala(), r.top() + lay.config.margem_sup * v.escala(),
                       lay.config.larg_corpo * v.escala(), lay.config.alt_corpo * v.escala())
        azuis[n + 1] = contar_cor(img, corpo, COR_SELECAO)
    paginas_pintadas = [k for k in range(2, 8) if azuis[k] > 0]
    fora = [azuis[1], azuis[8]]
    pintou = len(paginas_pintadas) == 6 and all(x == 0 for x in fora)
    # Ctrl+C
    esperado = cur.selectedText().replace("\u2029", "\n")
    QTest.keyClick(v, Qt.Key.Key_C, CTRL)
    app.processEvents()
    copiado = QApplication.clipboard().text().replace("\u2029", "\n")
    texto_ok = copiado == esperado
    # tabela: copiar de tabela e colar mantendo estrutura
    tab_ok, tab_obs = c4_tabela_colada()
    ok = sel_ok and pag_ini == 1 and pag_fim == 6 and pintou and texto_ok and tab_ok
    registrar("C4", (f"selecao pag {pag_ini+1}..{pag_fim+1}; pixels azuis por pagina 1..8 = "
                     f"{[azuis[k] for k in range(1, 9)]}; Ctrl+C igual: {texto_ok} ({len(copiado)} car); "
                     f"tabela: {tab_obs}"), ok)
    return {"pag_ini": pag_ini + 1, "pag_fim": pag_fim + 1, "azuis": azuis, "texto_ok": texto_ok,
            "tabela_ok": tab_ok}


def c4_tabela_colada():
    lay = LayoutPaginado()
    cur = QTextCursor(lay.doc)
    cur.insertText("Antes da tabela.")
    cur.insertBlock()
    rng = random.Random(2)
    inserir_tabela(cur, lay, rng, linhas=3, colunas=3)
    cur.movePosition(M.End)
    cur.insertText("Depois da tabela.")
    v = nova_vista(lay)
    tabs = _tabelas(lay)
    if not tabs:
        return False, "sem tabela no documento"
    t0 = tabs[0]
    ini = t0.cellAt(0, 0).firstCursorPosition().position()
    fim = t0.cellAt(2, 2).lastCursorPosition().position()
    v.controle.cursor.setPosition(ini)
    v.controle.cursor.setPosition(fim, MODO_SEL)
    QTest.keyClick(v, Qt.Key.Key_C, CTRL)
    app.processEvents()
    html_copiado = QApplication.clipboard().mimeData().html()
    v.controle.cursor.setPosition(lay.doc.characterCount() - 1)
    QTest.keyClick(v, Qt.Key.Key_V, CTRL)
    app.processEvents()
    tabs2 = _tabelas(lay)
    ok = len(tabs2) == 2 and tabs2[1].rows() == 3 and tabs2[1].columns() == 3
    obs = f"tabelas apos colar={len(tabs2)}, colado {tabs2[-1].rows() if tabs2 else 0}x{tabs2[-1].columns() if tabs2 else 0}"
    return ok, obs


# --------------------------------------------------------------------------- C5
def c5():
    registrar("C5", "PENDENTE MANUAL (ver RESULTADO.md, roteiro)", None,
              "nao automatizavel: teclas mortas do teclado ABNT2 e AltGr chegam pelo sistema")


# --------------------------------------------------------------------------- C6
def c6():
    lay = documento_100_paginas()[0]
    v = nova_vista(lay, CabecalhoRodape(lay))
    rng = random.Random(21)
    clicar_pos(v, lay.doc.characterCount() // 3)
    app.processEvents()
    lay.doc.clearUndoRedoStacks()
    html0 = lay.doc.toHtml()
    caret0 = v.controle.cursor.position()
    operacoes = {"digitar": 0, "colar": 0, "quebra": 0, "negrito": 0, "enter": 0}
    digitar(v, "inicio")
    operacoes["digitar"] += 1
    for i in range(49):
        acao = rng.choice(["digitar", "colar", "quebra", "negrito", "enter"])
        if acao == "digitar":
            digitar(v, "palavra" + str(i) + " ")
        elif acao == "colar":
            QApplication.clipboard().setText(f"trecho colado {i}\nsegunda linha")
            QTest.keyClick(v, Qt.Key.Key_V, CTRL)
        elif acao == "quebra":
            QTest.keyClick(v, Qt.Key.Key_Return, CTRL)
        elif acao == "negrito":
            for _ in range(5):
                QTest.keyClick(v, Qt.Key.Key_Left, SHIFT)
            QTest.keyClick(v, Qt.Key.Key_B, CTRL)
        else:
            QTest.keyClick(v, Qt.Key.Key_Return)
        operacoes[acao] += 1
        app.processEvents()
    html_final = lay.doc.toHtml()
    paginas_depois = lay.numero_paginas()
    n = 0
    while lay.doc.isUndoAvailable() and n < 2000:
        QTest.keyClick(v, Qt.Key.Key_Z, CTRL)
        n += 1
    app.processEvents()
    igual = lay.doc.toHtml() == html0
    caret_depois = v.controle.cursor.position()
    caret_ok = caret_depois == caret0
    # bonus: refazer tudo devolve o estado final
    m = 0
    while lay.doc.isRedoAvailable() and m < 2000:
        QTest.keyClick(v, Qt.Key.Key_Y, CTRL)
        m += 1
    refeito = lay.doc.toHtml() == html_final
    ok = igual and caret_ok
    registrar("C6", (f"50 operacoes {operacoes} ({paginas_depois} pag no fim); "
                     f"desfazer {n}x: HTML igual={igual}, caret {caret_depois} "
                     f"(inicial {caret0}, ok={caret_ok}); refazer igual={refeito}"), ok)
    return {"html_igual": igual, "caret_ok": caret_ok, "refazer_igual": refeito}


# --------------------------------------------------------------------------- C7
def c7():
    lay = documento_100_paginas()[0]
    cab = CabecalhoRodape(lay)
    n_tela = lay.numero_paginas()
    prev = criar_previa(lay, cab)
    prev.resize(900, 700)
    prev.show()
    app.processEvents()
    prev.updatePreview()
    app.processEvents()
    n_prev = prev.pageCount()
    caminho = os.path.join(SAIDA, "c7_documento.pdf")
    n_pdf_escrito = exportar_pdf(lay, cab, caminho)
    n_pdf_bytes = contar_paginas_pdf(caminho)

    # pagina 1: caminho de tela (widget real, zoom 156,25% = 150 dpi) x impressao 150 dpi
    dpi = 150
    v = nova_vista(lay, cab, w=1400, h=1900)
    v.mostrar_caret = False
    dpr = v.viewport().devicePixelRatioF()
    # 150 dpi de dispositivo: zoom logico = (150/96)/dpr, pois o grab devolve pixels x dpr
    v.definir_zoom(dpi / 96.0 / dpr)
    v.rolar_para_pagina(0)
    v.horizontalScrollBar().setValue(0)
    app.processEvents()
    tela_full = v.viewport().grab().toImage()
    r = v.retangulo_folha_logico(0)
    lw = round(lay.config.largura * dpi / 1440.0)
    lh = round(lay.config.altura * dpi / 1440.0)
    x0, y0 = int(round(r.left() * dpr)), int(round(r.top() * dpr))  # recorte em pixels de dispositivo
    tela = tela_full.copy(x0, y0, lw, lh)
    impressao = QImage(lw, lh, QImage.Format.Format_ARGB32)
    impressao.fill(QColor(255, 255, 255))
    impressao.setDotsPerMeterX(round(dpi / 0.0254))
    impressao.setDotsPerMeterY(round(dpi / 0.0254))
    p = QPainter(impressao)
    pintar_pagina_em(p, lay, cab, 0, dpi)
    p.end()
    total = lw * lh
    limites = {}
    for lim in (16, 32):
        diff = 0
        for y in range(lh):
            for x in range(lw):
                a, b = tela.pixelColor(x, y), impressao.pixelColor(x, y)
                if max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())) > lim:
                    diff += 1
        limites[lim] = 100.0 * diff / total
    tela.save(os.path.join(SAIDA, "c7_tela_p1.png"))
    impressao.save(os.path.join(SAIDA, "c7_impressao_p1.png"))
    # controle negativo: a tela da pagina 1 contra a impressao da pagina 2 TEM de diferir
    neg = QImage(lw, lh, QImage.Format.Format_ARGB32)
    neg.fill(QColor(255, 255, 255))
    neg.setDotsPerMeterX(round(dpi / 0.0254))
    neg.setDotsPerMeterY(round(dpi / 0.0254))
    pn = QPainter(neg)
    pintar_pagina_em(pn, lay, cab, 1, dpi)
    pn.end()
    dif_neg = sum(1 for y in range(0, lh, 3) for x in range(0, lw, 3)
                  if tela.pixelColor(x, y) != neg.pixelColor(x, y))
    ok = (n_tela == n_prev == n_pdf_bytes == n_pdf_escrito) and limites[32] < 2.0 and dif_neg > 0
    registrar("C7", (f"DPR={dpr}; paginas: tela {n_tela}, previa {n_prev}, PDF {n_pdf_bytes} (bytes; escrito {n_pdf_escrito}); "
                     f"pixels diferentes pag 1 @150dpi: {limites[16]:.2f}% (dif>16) / {limites[32]:.2f}% (dif>32)"),
              ok, f"limiar dif>32 fixado antes de medir; controle negativo (pag 1 x pag 2) acusa {dif_neg} amostras")
    return {"paginas": {"tela": n_tela, "previa": n_prev, "pdf": n_pdf_bytes}, "pixels_pct": limites}


# --------------------------------------------------------------------------- C8
def c8():
    lay = documento_100_paginas()[0]
    cab = CabecalhoRodape(lay)
    v = nova_vista(lay, cab)
    erros = 0
    erros_pix = 0
    checagens = 0

    def checar(rotulo):
        nonlocal erros, erros_pix, checagens
        N = lay.numero_paginas()
        s_ = 150 / 1440.0
        cfg = lay.config
        larg = round(cfg.larg_corpo * s_)
        alt = round(cfg.margem_inf * 0.4 * s_) + 2
        y_rod = cfg.altura - cfg.margem_inf * 0.6
        for n in range(N):
            esperado = f"Página {n+1} de {N}"
            if cab.texto_rodape(n + 1, N) != esperado:
                erros += 1
            # faixa do rodape pintada pelo caminho real (cab.desenhar) x referencia
            t = QTransform().scale(s_, s_).translate(0, -y_rod)
            img = QImage(larg, alt, QImage.Format.Format_ARGB32)
            img.fill(QColor(255, 255, 255))
            pa = QPainter(img)
            pa.setWorldTransform(t)
            cab.desenhar(pa, n, N)
            pa.end()
            img_ref = QImage(larg, alt, QImage.Format.Format_ARGB32)
            img_ref.fill(QColor(255, 255, 255))
            pr = QPainter(img_ref)
            pr.setWorldTransform(t)
            pr.translate(cfg.margem_esq, y_rod)
            doc_ref = _doc_rodape_referencia(cab, esperado)
            doc_ref.documentLayout().draw(pr, _ctx_rodape(cab, cfg))
            pr.end()
            diff = 0
            for y in range(alt):
                for x in range(larg):
                    if img.pixel(x, y) != img_ref.pixel(x, y):
                        diff += 1
            if diff:
                erros_pix += 1
            checagens += 1

    # controle negativo: "de N+1" tem de diferir de "de N" em pixel
    cfg_ = lay.config
    s_ = 150 / 1440.0
    t_ = QTransform().scale(s_, s_).translate(0, -(cfg_.altura - cfg_.margem_inf * 0.6))
    im_a = QImage(round(cfg_.larg_corpo * s_), round(cfg_.margem_inf * 0.4 * s_) + 2, QImage.Format.Format_ARGB32)
    im_b = QImage(im_a.width(), im_a.height(), QImage.Format.Format_ARGB32)
    for im_, txt_ in ((im_a, "Página 1 de 96"), (im_b, "Página 1 de 97")):
        im_.fill(QColor(255, 255, 255))
        pr_ = QPainter(im_)
        pr_.setWorldTransform(t_)
        pr_.translate(cfg_.margem_esq, cfg_.altura - cfg_.margem_inf * 0.6)
        doc_tmp = _doc_rodape_referencia(cab, txt_)  # guardado: temporario morreria antes do draw
        doc_tmp.documentLayout().draw(pr_, _ctx_rodape(cab, cfg_))
        pr_.end()
    dif_neg_c8 = sum(1 for y in range(im_a.height()) for x in range(im_a.width()) if im_a.pixel(x, y) != im_b.pixel(x, y))
    checar("inicial")
    # quebra de pagina no meio: total de paginas muda
    clicar_pos(v, lay.doc.characterCount() // 2)
    QTest.keyClick(v, Qt.Key.Key_Return, CTRL)
    app.processEvents()
    checar("depois da quebra")

    # custo por pagina de cabecalho+rodape (cada chamada re-layout o rodape)
    cfg = lay.config
    s = 150 / 1440.0
    img = QImage(round(cfg.largura * s), round(cfg.altura * s), QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    img.setDotsPerMeterX(round(150 / 0.0254))
    img.setDotsPerMeterY(round(150 / 0.0254))
    N = lay.numero_paginas()
    tempos = []
    p = QPainter(img)
    p.setWorldTransform(QTransform().scale(s, s))
    for n in range(N):
        t0 = time.perf_counter()
        cab.desenhar(p, n, N)
        tempos.append((time.perf_counter() - t0) * 1000)
    p.end()
    media = sum(tempos) / len(tempos)
    maximo = max(tempos)
    p95_c8 = p95(tempos)
    ok = erros == 0 and erros_pix == 0 and media <= 1.0 and dif_neg_c8 > 0
    registrar("C8", (f"{checagens} checagens (2 estados): erros de texto {erros}, paginas com pixel diferente "
                     f"{erros_pix}; custo por pagina media {media:.3f} ms, p95 {p95_c8:.3f} ms, max {maximo:.3f} ms ({N} pag); "
                     f"controle negativo 'de 96' x 'de 97' acusa {dif_neg_c8} pixels"), ok)
    return {"erros_texto": erros, "erros_pixel": erros_pix, "custo_medio_ms": media, "custo_max_ms": maximo}


def _ctx_rodape(cab, cfg):
    from PySide6.QtGui import QAbstractTextDocumentLayout, QPalette
    from PySide6.QtCore import QRectF as R
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Text, QColor(0x55, 0x55, 0x55))
    ctx = QAbstractTextDocumentLayout.PaintContext()
    ctx.palette = pal
    ctx.cursorPosition = -1
    altura_rod = cfg.margem_inf * 0.4
    ctx.clip = R(0, 0, cfg.larg_corpo, altura_rod)
    return ctx


def _doc_rodape_referencia(cab, texto):
    """Documento novo com o texto esperado, mesmas fontes e alinhamento (referencia)."""
    d = QTextDocument()
    d.setDocumentMargin(0)
    f = QFont("Arial")
    f.setPointSizeF(9)
    d.setDefaultFont(f)
    d.setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignCenter))
    d.documentLayout().setPaintDevice(cab._dispositivo)
    d.setTextWidth(cab.layout.config.larg_corpo)
    d.setPlainText(texto)
    return d


# --------------------------------------------------------------------------- C9
def c9():
    lay = documento_100_paginas()[0]
    v = nova_vista(lay, CabecalhoRodape(lay))
    blocos = []
    b = lay.doc.firstBlock()
    k = 0
    while b.isValid():
        if k % max(1, lay.doc.blockCount() // 40) == 0:
            blocos.append(b.layout().position())
        b = b.next()
        k += 1
    n0 = lay.numero_paginas()
    pos0 = [QPointF(x) for x in blocos]
    tempos = []
    for z in (0.25, 4.0, 1.0, 0.5, 2.0, 0.25):
        t = time.perf_counter()
        v.definir_zoom(z)
        tempos.append((time.perf_counter() - t) * 1000)
    # posicoes de paragrafo: comparar layout.position de cada bloco amostrado
    b = lay.doc.firstBlock()
    k = 0
    idx = 0
    iguais = True
    while b.isValid():
        if k % max(1, lay.doc.blockCount() // 40) == 0:
            if (b.layout().position().x(), b.layout().position().y()) != (pos0[idx].x(), pos0[idx].y()):
                iguais = False
            idx += 1
        b = b.next()
        k += 1
    maior = max(tempos)
    ok = maior < 10.0 and iguais and lay.numero_paginas() == n0
    registrar("C9", (f"troca de zoom max {maior:.2f} ms (mediana {sorted(tempos)[len(tempos)//2]:.2f} ms); "
                     f"paginas {n0} -> {lay.numero_paginas()}; posicoes de {len(pos0)} paragrafos iguais={iguais}"), ok)
    return {"zoom_max_ms": maior, "posicoes_iguais": iguais, "paginas": lay.numero_paginas()}


# --------------------------------------------------------------------------- C10
def c10():
    dpr_esperado = float(os.environ.get("QT_SCALE_FACTOR", "1") or 1)
    lay = documento_100_paginas()[0]
    v = nova_vista(lay, CabecalhoRodape(lay), w=1000, h=700)
    v.mostrar_caret = False
    v.definir_zoom(1.0)
    v.rolar_para_pagina(0)
    app.processEvents()
    dpr = v.viewport().devicePixelRatioF()
    # 1) bordas da folha em pixel de dispositivo inteiro
    img = v.viewport().grab().toImage()
    r = v.retangulo_folha_logico(0)
    x0 = round(r.left() * dpr)
    y0 = round(r.top() * dpr)
    dx = int(round(r.right() * dpr))
    # borda crisp: ao longo da folha, a coluna x0 e branca pura e a x0-1 e fundo/sombra pura;
    # a linha y0 e branca pura e a y0-1 nao e branca (sem pixel intermediario)
    x1 = int(round(r.right() * dpr))
    y1 = int(round(r.bottom() * dpr))
    branco = QColor(255, 255, 255)
    cores_fora = {QColor(0xB9, 0xBE, 0xC6).rgb(), QColor(0x80, 0x86, 0x90).rgb()}
    violacoes = 0
    amostras = 0
    for y in range(y0 + 1, min(y1, img.height()) - 1, 5):
        amostras += 1
        if img.pixelColor(x0, y) != branco:
            violacoes += 1
        if img.pixel(x0 - 1, y) not in cores_fora and img.pixelColor(x0 - 1, y) != branco:
            violacoes += 1
    for x in range(x0 + 1, min(x1, img.width()) - 1, 5):
        amostras += 1
        if img.pixelColor(x, y0) != branco:
            violacoes += 1
    borda_ok = violacoes == 0 and amostras > 100
    # 2) hit-test em pontos fixos: saida independente do DPR (hash)
    pontos = [QPointF(20 + 47.3 * i, 30 + 61.7 * j) for i in range(14) for j in range(20)]
    saida = [v.posicao_em(p) for p in pontos]
    h = hashlib.sha256(json.dumps(saida).encode()).hexdigest()[:16]
    # 3) hit-test ida-volta sob DPR
    rng = random.Random(9)
    falhas = 0
    for _ in range(300):
        p = rng.randrange(0, lay.doc.characterCount() - 1)
        rr = lay.retangulo_cursor(p)
        w = v.doc_para_widget(QPointF(rr.x(), rr.center().y()))
        if abs(v.posicao_em(w) - p) > 1:
            falhas += 1
    ok = abs(dpr - dpr_esperado) < 1e-6 and borda_ok and falhas == 0
    registrar("C10", (f"DPR={dpr} (esperado {dpr_esperado}); borda da folha em pixel inteiro={borda_ok} "
                      f"({amostras} amostras, {violacoes} violacoes); "
                      f"hit-test ida-volta falhas {falhas}/300; hash mapeamento fixo {h} (igual entre DPRs = inalterado)"),
              ok)
    return {"dpr": dpr, "borda_ok": borda_ok, "falhas": falhas, "hash_mapeamento": h}


# --------------------------------------------------------------------------- C11
def c11():
    lay = LayoutPaginado()
    cur = QTextCursor(lay.doc)
    rng = random.Random(4)
    # texto antes para a tabela comecar perto do fim da pagina 1
    for _ in range(40):
        cur.insertText(frase(rng, 14))
        cur.insertBlock()
    inserir_tabela(cur, lay, rng, linhas=30, colunas=3, cor_cabecalho=QColor(255, 0, 0), texto_longo=True)
    cur.movePosition(M.End)
    cur.insertText("Fim do documento.")
    cab = CabecalhoRodape(lay)
    v = nova_vista(lay, cab)
    v.definir_zoom(0.25)
    N = lay.numero_paginas()
    tabs = _tabelas(lay)
    t = tabs[0]
    # a) cabecalho repetido. A tabela comeca no meio da pagina 2 (indice 1): la
    #    aparece o cabecalho original. Na pagina 3 (indice 2) o cabecalho tem de
    #    repetir NO TOPO do corpo. Mede-se a posicao do vermelho em twips do corpo.
    s = 150 / 1440.0
    cfg = lay.config
    vermelho = QColor(255, 0, 0)
    repeticoes = []
    topo_vermelho = []
    for n in range(min(3, N)):
        im = QImage(round(cfg.largura * s), round(cfg.altura * s), QImage.Format.Format_ARGB32)
        im.fill(QColor(255, 255, 255))
        im.setDotsPerMeterX(round(150 / 0.0254))
        im.setDotsPerMeterY(round(150 / 0.0254))
        pa = QPainter(im)
        desenhar_conteudo_folha(pa, lay, n, QTransform().scale(s, s), None)
        pa.end()
        corpo = QRectF(cfg.margem_esq * s, cfg.margem_sup * s, cfg.larg_corpo * s, cfg.alt_corpo * s)
        repeticoes.append(contar_cor(im, corpo, vermelho, tol=40))
        ys = [y for y in range(int(corpo.top()), int(corpo.bottom()))
              for x in range(int(corpo.left()), int(corpo.right()), 4)
              if cor_perto(im.pixelColor(x, y), vermelho, 40)]
        topo_vermelho.append(round((min(ys) - corpo.top()) / s) if ys else None)
    header_ok = (len(repeticoes) == 3 and repeticoes[1] > 0 and repeticoes[2] > 0
                 and topo_vermelho[2] is not None and topo_vermelho[2] < 600)
    # b) linha dividida: alguma celula com inicio e fim em paginas diferentes
    divididas = 0
    for r_ in range(t.rows()):
        for c_ in range(t.columns()):
            cel = t.cellAt(r_, c_)
            pi = lay.pagina_do_cursor(cel.firstCursorPosition().position())
            pf = lay.pagina_do_cursor(cel.lastCursorPosition().position())
            if pf != pi:
                divididas += 1
    # c) Tab navega entre celulas
    v.controle.cursor.setPosition(t.cellAt(0, 0).firstCursorPosition().position())
    seq = []
    for _ in range(4):
        QTest.keyClick(v, Qt.Key.Key_Tab)
        cel = t.cellAt(v.controle.cursor.position())
        seq.append((cel.row(), cel.column()))
    tab_ok = seq == [(0, 1), (0, 2), (1, 0), (1, 1)]
    # d) clique perto da fronteira (zoom 25%, as duas bordas visiveis)
    hb = lay.hb
    v.rolar_para_pagina(0)
    app.processEvents()
    x_meio = cfg.larg_corpo / 2
    ptA = v.doc_para_widget(QPointF(x_meio, hb - 40))
    QTest.mouseClick(v.viewport(), ESQ, NADA, _ponto(ptA))
    pa_ = lay.pagina_do_cursor(v.controle.cursor.position())
    ptB = v.doc_para_widget(QPointF(x_meio, hb + 40))
    QTest.mouseClick(v.viewport(), ESQ, NADA, _ponto(ptB))
    pb_ = lay.pagina_do_cursor(v.controle.cursor.position())
    borda_ok = (pa_ == 0 and pb_ == 1)
    ok = header_ok and divididas > 0 and tab_ok and borda_ok
    registrar("C11", (f"cabecalho: pixels vermelhos pag 1..3 {repeticoes}, topo do vermelho na pag 3 a "
                      f"{topo_vermelho[2]} tw do corpo; celulas divididas entre "
                      f"paginas: {divididas}; Tab: {seq} ok={tab_ok}; clique na fronteira: "
                      f"acima->pag {pa_+1}, abaixo->pag {pb_+1} ok={borda_ok}"), ok)
    return {"cabecalho_repetido": repeticoes, "celulas_divididas": divididas, "tab_ok": tab_ok,
            "fronteira_ok": borda_ok, "paginas": N}


# --------------------------------------------------------------------------- C12
def c12():
    lay = LayoutPaginado()
    v = nova_vista(lay, CabecalhoRodape(lay))
    grande = QImage(3000, 3000, QImage.Format.Format_RGB32)
    grande.fill(QColor(30, 90, 160))
    w, h = v.controle.inserir_imagem("grande", grande, 3000, 3000)
    cfg = lay.config
    lim_w, lim_h = cfg.larg_corpo / 15.0, (cfg.alt_corpo - 400) / 15.0
    cab_ok = w <= lim_w + 1e-6 and h <= lim_h + 1e-6
    # o bloco da imagem cabe numa unica pagina
    bloco = lay.doc.findBlock(v.controle.cursor.position() - 1)
    lo = bloco.layout()
    linha = lo.lineAt(0)
    r_linha = lay.retangulo_linha(bloco, linha)
    uma_pagina = lay.pagina_de_y(r_linha.top()) == lay.pagina_de_y(r_linha.bottom() - 1)
    # digitar logo depois da imagem: texto nao deve herdar o objeto (fato 10)
    cur_antes = v.controle.cursor.position()
    digitar(v, "abc")
    app.processEvents()
    cur = QTextCursor(lay.doc)
    cur.setPosition(cur_antes + 1)
    tipo = cur.charFormat().objectType()
    herdou = tipo != QTextFormat_NoObject()
    # controle: imagem sem limite estoura a pagina
    lay2 = LayoutPaginado()
    c2_ = QTextCursor(lay2.doc)
    fmt = QTextImageFormat()
    lay2.doc.addResource(QTextDocument.ResourceType.ImageResource, "sem_limite", grande)
    fmt.setName("sem_limite")
    fmt.setWidth(3000)
    fmt.setHeight(3000)
    c2_.insertImage(fmt)
    b2 = lay2.doc.firstBlock()
    r2 = lay2.retangulo_linha(b2, b2.layout().lineAt(0))
    estoura = lay2.pagina_de_y(r2.top()) != lay2.pagina_de_y(r2.bottom() - 1) or r2.height() > lay2.hb
    # campo (propriedade de formato): o caminho cru herda, o controle nao pode herdar
    from PySide6.QtGui import QTextFormat as QTF
    from controle import PROP_CAMPO
    lay_c = LayoutPaginado()
    vc = nova_vista(lay_c)
    fcampo = QTextCharFormat()
    fcampo.setProperty(PROP_CAMPO, "campo:NOME")
    vc.controle.cursor.insertText("NOME", fcampo)
    fim_c = vc.controle.cursor.position()
    digitar(vc, "abc")
    cc = QTextCursor(lay_c.doc)
    cc.setPosition(fim_c + 1)
    herdou_campo = cc.charFormat().hasProperty(PROP_CAMPO)
    lay_r = LayoutPaginado()
    cr = QTextCursor(lay_r.doc)
    cr.insertText("NOME", fcampo)
    fim_r = cr.position()
    cr.insertText("abc")
    cr2 = QTextCursor(lay_r.doc)
    cr2.setPosition(fim_r + 1)
    herdou_cru = cr2.charFormat().hasProperty(PROP_CAMPO)
    ok = cab_ok and uma_pagina and not herdou and not herdou_campo and herdou_cru
    registrar("C12", (f"imagem 3000x3000 px -> {w:.0f}x{h:.0f} px96 (limite {lim_w:.0f}x{lim_h:.0f}); "
                      f"linha da imagem em uma pagina: {uma_pagina}; texto depois da imagem herdou objeto: {herdou}; "
                      f"campo (propriedade): caminho cru herda={herdou_cru}, controle herda={herdou_campo}; "
                      f"sem limite: altura da linha {r2.height():.0f} tw > corpo {lay2.hb:.0f} -> estoura={estoura}"), ok)
    return {"largura_px": w, "altura_px": h, "uma_pagina": uma_pagina, "herdou": herdou, "sem_limite_estoura": estoura}


def QTextFormat_NoObject():
    from PySide6.QtGui import QTextFormat
    return QTextFormat.ObjectTypes.NoObject


# --------------------------------------------------------------------------- C13
def c13_filho(modo: str, n: int = 100) -> int:
    """Processo filho: cria e destroi n documentos no modo pedido.

    ingenuo      QImage de device local, sem dono: morre ao sair da funcao
    pdf_ingenuo  QPdfWriter de device local, sem dono
    seguro       QImage de device guardado no LayoutPaginado + fechar() antes de destruir
    pdf_seguro   QPdfWriter guardado no mesmo objeto, desligado antes de destruir
    Em todos, depois da criacao ha uma EDICAO que forca novo layout (le metricas do device).
    """
    from PySide6.QtGui import QPdfWriter, QPainter as QP
    caminho_pdf = os.path.join(SAIDA, "c13_tmp.pdf")
    for i in range(n):
        if modo == "ingenuo":
            doc = _doc_ingenuo(QImage)
            doc.setPlainText("texto " * 300)
            doc.pageCount()
            del doc
        elif modo == "pdf_ingenuo":
            doc = _doc_ingenuo(lambda: QPdfWriter(caminho_pdf))
            doc.setPlainText("texto " * 300)
            doc.pageCount()
            del doc
        elif modo == "seguro":
            lay = LayoutPaginado()
            cur = QTextCursor(lay.doc)
            cur.insertText("Teste de ciclo de vida " * 40)
            lay.numero_paginas()
            cur.insertText("mais texto " * 40)
            lay.numero_paginas()
            lay.fechar()
            del lay
        elif modo == "pdf_seguro":
            w = QPdfWriter(caminho_pdf)
            w.setResolution(1440)
            lay = LayoutPaginado()
            lay.doc.documentLayout().setPaintDevice(w)
            cur = QTextCursor(lay.doc)
            cur.insertText("Teste de ciclo de vida " * 40)
            lay.numero_paginas()
            lay.fechar()
            del lay
            del w
        elif modo == "pintor_aberto":
            # CONTROLE (reproduz o achado): device destruido com QPainter ainda ativo
            from PySide6.QtGui import QImage as QI
            dev = QI(800, 600, QI.Format.Format_ARGB32)
            pt = QP(dev)
            pt.drawText(10, 20, "abc")
            del dev
            del pt
        elif modo == "seguro_pintor":
            # padrao de producao: device guardado, painter fechado antes, fechar() ao final
            from PySide6.QtGui import QImage as QI, QTransform as QT
            lay = LayoutPaginado()
            cur = QTextCursor(lay.doc)
            cur.insertText("Teste de ciclo de vida " * 40)
            lay.numero_paginas()
            img = QI(400, 500, QI.Format.Format_ARGB32)
            img.fill(0xFFFFFFFF)
            pt = QP(img)
            try:
                desenhar_conteudo_folha(pt, lay, 0, QT().scale(0.03, 0.03))
            finally:
                pt.end()
            del pt
            del img
            lay.fechar()
            del lay
        else:
            raise SystemExit("modo invalido")
    return 0


def _doc_ingenuo(fabrica_device):
    """Documento cujo device de layout NAO e guardado: o padrao que pode quebrar."""
    d = QTextDocument()
    d.setDocumentMargin(0)

    def montar():
        dev = fabrica_device()
        if isinstance(dev, QImage):
            dpm = round(1440 / 0.0254)
            dev.setDotsPerMeterX(dpm)
            dev.setDotsPerMeterY(dpm)
        d.documentLayout().setPaintDevice(dev)

    montar()  # o device local morre aqui; o layout ainda aponta para ele
    d.setPageSize(QSizeF_(9072, 14004))
    cur = QTextCursor(d)
    cur.insertText("texto " * 300)
    d.pageCount()
    return d


def QSizeF_(w, h):
    from PySide6.QtCore import QSizeF
    return QSizeF(w, h)


def c13():
    import subprocess
    resultados = {}
    for modo in ("seguro", "pdf_seguro", "seguro_pintor", "ingenuo", "pdf_ingenuo", "pintor_aberto"):
        codigo = subprocess.run([sys.executable, os.path.abspath(__file__), "--filho", modo],
                                capture_output=True, text=True, timeout=900)
        resultados[modo] = codigo.returncode
    seguros = ("seguro", "pdf_seguro", "seguro_pintor")
    seguro_ok = all(resultados[m] == 0 for m in seguros)
    controle_reproduz = resultados["pintor_aberto"] != 0
    partes = "; ".join(f"{m}: exit {c}{' (SEGFAULT)' if c not in (0,) else ''}" for m, c in resultados.items())
    registrar("C13", f"100 documentos por modo, processo isolado | {partes}", seguro_ok and controle_reproduz,
              f"modos de producao sem crash; controle 'pintor_aberto' reproduz o segfault: {controle_reproduz}")
    return resultados


# --------------------------------------------------------------------------- main
TESTES = {"C1": c1, "C2": c2, "C3": c3, "C4": c4, "C5": c5, "C6": c6, "C7": c7, "C8": c8,
          "C9": c9, "C10": c10, "C11": c11, "C12": c12, "C13": c13}

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--filho":
        sys.exit(c13_filho(sys.argv[2]))
    pedidos = [a.upper() for a in sys.argv[1:]] or list(TESTES)
    dados = {}
    for cid in pedidos:
        t0 = time.perf_counter()
        try:
            dados[cid] = TESTES[cid]()
        except Exception as e:  # noqa
            registrar(cid, f"ERRO {type(e).__name__}: {e}", False)
            dados[cid] = {"erro": str(e)}
        print(f"   ({cid} levou {time.perf_counter()-t0:.1f} s)", flush=True)
    nome = f"resultados_dpr{os.environ.get('QT_SCALE_FACTOR', '1')}.json"
    with open(os.path.join(SAIDA, nome), "w", encoding="utf-8") as f:
        json.dump({"resultados": RESULTADOS, "dados": dados}, f, ensure_ascii=False, indent=1, default=str)
    print("saida:", os.path.join(SAIDA, nome))
