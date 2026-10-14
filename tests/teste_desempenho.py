"""Desempenho da digitacao num documento pesado (0.1.8): o gate do M3 num "manual" gerado em codigo.

O manual sintetico imita o real que passava do gate na 0.1.7 (fora do repositorio): capa com
imagem de pagina inteira atras do texto e caixas de texto, cabecalho da primeira pagina vazio e
o padrao com imagem, sumario com links, PAGEREF e pontilhado, e corpo comprido. As verificacoes
que nao dependem do relogio vem primeiro (sao as que pegam a regressao em qualquer maquina):

- conferencia dos floats: a linha que o Qt desce de pagina ao lado de um float nao e' refeita a
  cada tecla (era refeita 6 vezes, com o documento inteiro conferido, a cada tecla);
- tiles por tecla: digitar no paragrafo da capa (um bloco da altura da folha) refaz so' a faixa
  da linha, e nao a folha inteira;
- a tela com cache e' igual a' tela refeita do zero, tecla a tecla (letra, quebra de linha,
  Backspace que puxa palavra, Enter), na capa, no sumario e no corpo;
- objetos flutuantes e cabecalho/rodape pintados uma vez e reaproveitados na tela; o PDF e a
  impressao continuam pintando de verdade;
- pontilhado da tabulacao num drawText so'; tamanho das marcas guardado por fonte;
- p95 da digitacao (80 teclas, cada uma com a pintura) na capa, no sumario e no corpo: no gate
  (16 ms) ou, numa maquina mais lenta, perto do p95 de um documento simples do mesmo tamanho.

Cada verificacao estrutural tem a contraprova: com a correcao desligada, ela acusa.
"""

from __future__ import annotations

import time

from ajudantes import (checa, checa_igual, drenar_eventos, preparar_qt, resumir, secao,
                       usar_fonte_windows, usar_fontes_do_documento)
import fixtures_docx as fx

preparar_qt()

import teste_flutuantes as tf  # noqa: E402  (fixtures de objeto flutuante em codigo)
from PySide6.QtGui import QTextDocument  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402
from editdoc.modelo.pagina import Pagina  # noqa: E402

EMU = 635  # EMU por twip
PAGINA_MANUAL = Pagina(margem_sup_tw=1134, margem_inf_tw=1134, margem_esq_tw=839,
                       margem_dir_tw=567, cabecalho_tw=397, rodape_tw=493,
                       primeira_diferente=True)
GATE_MS = 16.0


def _p95(valores):
    valores = sorted(valores)
    return valores[min(len(valores) - 1, round(0.95 * (len(valores) - 1)))]


def _docx(corpo_xml: str, base: Documento, relacoes, partes) -> bytes:
    return fx.docx_com_corpo_de_objetos(corpo_xml, relacoes, partes, (), (("png", "image/png"),),
                                        documento=base)


def _sumario(linhas: int) -> str:
    tab = ('<w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9000"/></w:tabs></w:pPr>')
    corpo = ('<w:p><w:r><w:t>Sumário</w:t></w:r></w:p><w:p>' + tab + fx._fld("begin")
             + fx._instr(' TOC \\o "1-3" \\h \\z \\u ') + fx._fld("separate")
             + fx._linha_do_sumario("_Toc0", "Introdução ao sistema", "3") + '</w:p>')
    for i in range(1, linhas):
        corpo += ('<w:p>' + tab + fx._linha_do_sumario(f"_Toc{i}", f"Seção {i} do manual", str(3 + i))
                  + '</w:p>')
    return corpo + '<w:p>' + fx._fld("end") + '</w:p>'


def manual_sintetico(paragrafos: int = 260) -> bytes:
    """Capa com objetos, sumario e corpo; cabecalho da primeira pagina vazio."""
    texto = [Paragrafo(runs=[Run(f"Parágrafo {i}. {tf.TEXTO}")]) for i in range(paragrafos)]
    base = Documento(
        pagina=PAGINA_MANUAL, paragrafos=texto,
        cabecalhos={"primeira": [Paragrafo()],
                    "padrao": [Paragrafo(runs=[fx.run_de_imagem(fx.imagem(fx.png(80, 20), 4.0, 1.0)),
                                               Run("  Manual do sistema")]),
                               Paragrafo(runs=[Run("Documentação")])]},
        rodapes={"padrao": [Paragrafo(runs=[Run("Página "), Run("1", campo="PAGE")])]})
    w, h = PAGINA_MANUAL.largura_tw, PAGINA_MANUAL.altura_tw
    capa = ('<w:p>'
            + tf.ancora(91, tf.URI_IMAGEM, tf.figura("rId81", w * EMU, h * EMU), w * EMU, h * EMU,
                        h=("page", "posOffset", 0), v=("page", "posOffset", 0),
                        quebra="<wp:wrapNone/>", atras=True)
            # O titulo empurra o texto do paragrafo para baixo dele (wrapTopAndBottom): o bloco da
            # ancora fica quase da altura da folha, como no manual real.
            + tf.ancora(92, tf.URI_FORMA, tf.forma(8000 * EMU, 11000 * EMU, cor="FFFFFF",
                                                   texto="Manual do sistema"),
                        8000 * EMU, 11000 * EMU, h=("page", "posOffset", 3400 * EMU),
                        v=("paragraph", "posOffset", 720 * EMU), quebra="<wp:wrapTopAndBottom/>")
            + tf.ancora(93, tf.URI_FORMA, tf.forma(3400 * EMU, 900 * EMU, texto="Portal"),
                        3400 * EMU, 900 * EMU, h=("page", "posOffset", 840 * EMU),
                        v=("page", "posOffset", 15500 * EMU), quebra="<wp:wrapNone/>")
            + '</w:p>')
    rels = [("rId81", fx.RT_IMAGEM, "media/capa.png")]
    partes = {"word/media/capa.png": fx.png(600, 850, (170, 20, 60))}
    return _docx(capa + _sumario(12), base, rels, partes)


def documento_simples(paragrafos: int = 260) -> bytes:
    texto = [Paragrafo(runs=[Run(f"Parágrafo {i}. {tf.TEXTO}")]) for i in range(paragrafos)]
    return _docx("<w:p><w:r><w:t>Primeiro.</w:t></w:r></w:p>", Documento(paragrafos=texto),
                 (), {})


def _painel(docx: bytes):
    painel = tf._painel()
    tf._carregar(painel, docx)
    painel.show()
    drenar_eventos()
    painel.viewport().grab()
    return painel


def _fechar(painel) -> None:
    painel.documento_corpo().setModified(False)
    painel.close()
    drenar_eventos()


def _ponto(painel, nome: str) -> int:
    doc = painel.documento_corpo()
    if nome == "capa":
        b = doc.firstBlock()
        return b.position() + b.length() - 1
    b = doc.firstBlock()
    alvo = "Seção 4" if nome == "sumario" else "Parágrafo 120."
    while b.isValid() and alvo not in b.text():
        b = b.next()
    return b.position() + 6


def _ir(painel, pos: int) -> None:
    c = painel.textCursor()
    c.setPosition(pos)
    painel.setTextCursor(c)
    painel.setFocus()
    painel.viewport().grab()


def _tecla(painel, tecla=None) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.keyClick(painel, tecla if tecla is not None else Qt.Key.Key_A)


# -- conferencia dos floats -------------------------------------------------------------------

def _irredutivel() -> bytes:
    """Float que ocupa a pagina quase toda a' direita: o texto corre na faixa estreita da esquerda
    e a linha que nao cabe no pe' da pagina desce com a largura estreita (o Qt nao a refaz)."""
    largura, altura = 9026 - 2500, 14500
    corpo = ("<w:p>" + tf.ancora(90, tf.URI_FORMA, tf.forma(largura * EMU, altura * EMU),
                                 largura * EMU, altura * EMU, h=("margin", "align", "right"),
                                 v=("paragraph", "posOffset", 0))
             + "<w:r><w:t>Capa.</w:t></w:r></w:p>"
             + "".join(f"<w:p><w:r><w:t>Linha {i} {tf.TEXTO}</w:t></w:r></w:p>" for i in range(30)))
    return tf.doc_do_corpo(corpo)


def _refeitos_por_tecla(painel, teclas: int = 10) -> float:
    """Quantas vezes por tecla a conferencia manda o Qt refazer um trecho (markContentsDirty)."""
    from editdoc.ponte_qt.imagens import DocumentoQt
    doc = painel.documento_corpo()
    b = doc.findBlockByNumber(20)
    _ir(painel, b.position() + 5)
    conta = [0]

    def contar(self, *a):
        conta[0] += 1
        return QTextDocument.markContentsDirty(self, *a)

    DocumentoQt.markContentsDirty = contar
    try:
        for _ in range(teclas):
            _tecla(painel)
            painel.viewport().grab()
    finally:
        del DocumentoQt.markContentsDirty
    for _ in range(teclas):
        painel.undo()
    return conta[0] / teclas


def testar_conferencia() -> None:
    secao("conferencia dos floats: a linha que o Qt nao refaz e' aceita, nao refeita a cada tecla")
    from editdoc.ponte_qt import flutuantes as pq_flutuantes
    painel = _painel(_irredutivel())
    g = painel.layout_pag.flutuantes
    checa(bool(g._aceitas), "a fixture reproduz a linha que desce de pagina com a largura estreita "
                           f"(blocos aceitos: {sorted(g._aceitas)})")
    por_tecla = _refeitos_por_tecla(painel)
    checa(por_tecla <= 0.5, f"o Qt nao refaz o trecho a cada tecla ({por_tecla:.1f} refacoes por "
                            "tecla; eram 6 na 0.1.7, com o documento inteiro conferido)")
    _fechar(painel)
    # Contraprova: a linha nunca reconhecida como aceita (assinatura sempre nova) volta a ser
    # refeita a cada tecla.
    original = pq_flutuantes._marca_das_linhas
    pq_flutuantes._marca_das_linhas = lambda bloco, r: object()
    try:
        painel = _painel(_irredutivel())
        sabotado = _refeitos_por_tecla(painel)
        _fechar(painel)
    finally:
        pq_flutuantes._marca_das_linhas = original
    checa(sabotado >= 1.0, f"contraprova: sem aceitar, {sabotado:.1f} refacoes por tecla")


# -- tiles por tecla --------------------------------------------------------------------------

def _tiles_por_tecla(painel, pos: int, teclas: int = 8) -> float:
    from editdoc.interface import vista_paginas as vp
    _ir(painel, pos)
    _tecla(painel)
    painel.viewport().grab()
    conta = [0]
    original = vp.desenhar_folha

    def contar(*a, **k):
        conta[0] += 1
        return original(*a, **k)

    vp.desenhar_folha = contar
    try:
        for _ in range(teclas):
            _tecla(painel)
            painel.viewport().grab()
    finally:
        vp.desenhar_folha = original
    for _ in range(teclas + 1):
        painel.undo()
    painel.viewport().grab()
    return conta[0] / teclas


def testar_tiles() -> None:
    secao("tiles por tecla: so' a faixa da linha sai do cache, nao o bloco inteiro")
    painel = _painel(manual_sintetico())
    capa = _tiles_por_tecla(painel, _ponto(painel, "capa"))
    corpo = _tiles_por_tecla(painel, _ponto(painel, "corpo"))
    # 1000 px de largura: 4 tiles por fileira. A linha cabe numa fileira, as vezes em duas.
    checa(capa <= 8.0, f"capa (bloco da altura da folha): {capa:.1f} tiles por tecla (a folha "
                       "inteira, 16 ou mais, na 0.1.7)")
    checa(corpo <= 8.0, f"corpo: {corpo:.1f} tiles por tecla")
    from editdoc.interface import vista_paginas as vp
    original = vp.VistaPaginas._linhas_da_mudanca
    vp.VistaPaginas._linhas_da_mudanca = lambda self, pos: None
    try:
        sabotado = _tiles_por_tecla(painel, _ponto(painel, "capa"))
    finally:
        vp.VistaPaginas._linhas_da_mudanca = original
    checa(sabotado > capa + 4, f"contraprova: invalidando o bloco inteiro, a capa refaz "
                               f"{sabotado:.1f} tiles por tecla")
    _fechar(painel)


# -- cache igual ao quadro novo --------------------------------------------------------------

def _diferentes(a, b) -> int:
    if a.size() != b.size():
        return -1
    n = 0
    for y in range(0, a.height(), 2):
        for x in range(0, a.width(), 2):
            if a.pixel(x, y) != b.pixel(x, y):
                n += 1
    return n


def _sequencia_confere(painel, pos: int, teclas) -> int:
    """Quantas teclas deixaram a tela com cache diferente da tela refeita do zero."""
    _ir(painel, pos)
    ruins = 0
    for k in teclas:
        _tecla(painel, k)
        com = painel.viewport().grab().toImage()
        painel._limpar_cache()
        sem = painel.viewport().grab().toImage()
        if _diferentes(com, sem):
            ruins += 1
    for _ in teclas:
        painel.undo()
    painel.viewport().grab()
    return ruins


def testar_cache_igual() -> None:
    secao("a tela com cache e' igual a' refeita do zero, tecla a tecla")
    from PySide6.QtCore import Qt
    K = Qt.Key
    teclas = ([K.Key_A] * 6 + [K.Key_Space] + [K.Key_B] * 24 + [K.Key_Backspace] * 6 + [K.Key_Return]
              + [K.Key_C] * 2 + [K.Key_Backspace] * 3)
    painel = _painel(manual_sintetico())
    for nome in ("capa", "sumario", "corpo"):
        ruins = _sequencia_confere(painel, _ponto(painel, nome), teclas)
        checa_igual(ruins, 0, f"{nome}: {len(teclas)} teclas (letra, quebra de linha, Backspace, "
                              "Enter) sem nada velho na tela")
    from editdoc.interface import vista_paginas as vp
    original = vp.VistaPaginas._invalidar_faixa
    vp.VistaPaginas._invalidar_faixa = lambda self, y0, y1: None
    try:
        sabotado = _sequencia_confere(painel, _ponto(painel, "corpo"), teclas[:8])
    finally:
        vp.VistaPaginas._invalidar_faixa = original
    checa(sabotado > 0, f"contraprova: sem invalidar, {sabotado} teclas deixam a tela velha")
    _fechar(painel)


# -- objetos e faixas pintados uma vez --------------------------------------------------------

def testar_caches_de_pintura() -> None:
    secao("objetos flutuantes e cabecalho/rodape: pintados uma vez na tela; o PDF pinta de verdade")
    from PySide6.QtGui import QColor, QImage, QPainter
    from editdoc.interface import impressao
    from editdoc.interface import vista_paginas as vp
    from editdoc.ponte_qt import flutuantes as pq_flutuantes
    painel = _painel(manual_sintetico())
    pintados = [0]
    original = pq_flutuantes.pintar

    def contar(*a, **k):
        pintados[0] += 1
        return original(*a, **k)

    pq_flutuantes.pintar = contar
    faixas = [0]
    original_faixas = vp.desenhar_faixas

    def contar_faixas(*a, **k):
        faixas[0] += 1
        return original_faixas(*a, **k)

    vp.desenhar_faixas = contar_faixas
    try:
        painel._cache.clear()  # so' os tiles: os objetos e as faixas ja' pintados ficam
        painel._bytes_no_cache = 0
        painel.viewport().grab()
        checa_igual(pintados[0], 0, "refazer os tiles da capa nao pinta de novo os objetos")
        checa_igual(faixas[0], 0, "um quadro novo nao pinta de novo o cabecalho e o rodape")
        img = QImage(800, 1130, QImage.Format.Format_ARGB32)
        img.fill(QColor(255, 255, 255))
        p = QPainter(img)
        impressao.pintar_pagina(p, painel.layout_pag, 0, painel.total_de_paginas(),
                                impressao.transformacao(96, 96))
        p.end()
        checa(pintados[0] >= 3, f"a folha do PDF pinta os objetos de verdade ({pintados[0]} pinturas)")
    finally:
        pq_flutuantes.pintar = original
        vp.desenhar_faixas = original_faixas
    # O cabecalho e' refeito quando muda.
    faixa = painel.layout_pag.faixas.obter("cabecalho", "padrao")
    painel.rolar_para_pagina(1)
    antes = painel.viewport().grab().toImage()
    from PySide6.QtGui import QTextCursor
    c = QTextCursor(faixa.doc)
    c.movePosition(QTextCursor.MoveOperation.End)
    c.insertText(" MUDOU")
    depois = painel.viewport().grab().toImage()
    checa(_diferentes(antes, depois) > 0, "o cabecalho que mudou aparece mudado (a chave tem a revisao)")
    faixa.doc.undo()
    # Mesmo desenho que a pintura direta (a diferenca de meio pixel no texto nao conta).
    painel.rolar_para_pagina(0)
    painel._limpar_cache()
    com = painel.viewport().grab().toImage()
    orig_tela = pq_flutuantes._pintar_na_tela
    orig_faixa = vp.VistaPaginas._faixa_da_tela
    from PySide6.QtGui import QTransform

    def direto(self, pp, m, n, x0, y0, n_total, onde, parte):
        t = QTransform().translate(x0, y0).scale(m.escala, m.escala)
        vp.desenhar_faixas(pp, self.layout_pag, n, t, n_total, vp.OPACIDADE_FAIXA,
                           marcas=self._marcas, parte=parte, so=onde)

    pq_flutuantes._pintar_na_tela = lambda *a, **k: False
    vp.VistaPaginas._faixa_da_tela = direto
    try:
        painel._limpar_cache()
        sem = painel.viewport().grab().toImage()
    finally:
        pq_flutuantes._pintar_na_tela = orig_tela
        vp.VistaPaginas._faixa_da_tela = orig_faixa
    grandes = 0
    for y in range(0, com.height(), 2):
        for x in range(0, com.width(), 2):
            a, b = QColor(com.pixel(x, y)), QColor(sem.pixel(x, y))
            if max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())) > 40:
                grandes += 1
    total = (com.width() // 2) * (com.height() // 2)
    checa(grandes <= total * 0.002, f"a tela com os caches e' a da pintura direta ({grandes} de "
                                    f"{total} pixels diferem mais que 40 niveis)")
    _fechar(painel)


# -- pontilhado e marcas -----------------------------------------------------------------------

class _PintorDeMentira:
    """Registra as chamadas que `_preenchimentos` faz."""

    def __init__(self) -> None:
        self.textos: list[str] = []

    def setFont(self, _f) -> None:  # noqa: N802
        pass

    def setPen(self, _c) -> None:  # noqa: N802
        pass

    def drawText(self, _p, texto) -> None:  # noqa: N802
        self.textos.append(texto)


def testar_pontilhado_e_marcas() -> None:
    secao("pontilhado da tabulacao num drawText so'; tamanho das marcas guardado por fonte")
    from PySide6.QtGui import QFont
    from editdoc.formato_docx.propriedades import aparencia_paragrafo
    from editdoc.ponte_qt import marcas as pq_marcas
    from editdoc.ponte_qt import propriedades as pq_props
    painel = _painel(manual_sintetico(20))
    doc = painel.documento_corpo()
    b = doc.firstBlock()
    while b.isValid() and "Seção 4" not in b.text():
        b = b.next()
    ap = aparencia_paragrafo(pq_props.extras_de_ppr(b.blockFormat()))
    pintor = _PintorDeMentira()
    pq_props._preenchimentos(pintor, b, ap)
    checa(len(pintor.textos) == 1 and len(pintor.textos[0]) > 10 and set(pintor.textos[0]) == {"."},
          f"um drawText com o pontilhado inteiro ({[len(t) for t in pintor.textos]} pontos)")
    # Marcas: o tamanho guardado e' o calculado, e muda com a fonte padrao.
    pos = next(k for k in range(b.position(), b.position() + b.length() - 1)
               if pq_marcas.eh_marca(_formato(doc, k)))
    fmt = _formato(doc, pos)
    manipulador = doc._manipulador_marcas
    pq_marcas._TAMANHOS.clear()
    guardado = manipulador.intrinsicSize(doc, pos, fmt)
    from PySide6.QtGui import QFontMetricsF
    from editdoc.ponte_qt.campos import fonte_de
    m = QFontMetricsF(fonte_de(doc, fmt))
    checa(abs(guardado.width() - max(m.height() * 0.22, 1.0)) < 1e-6
          and abs(guardado.height() - max(m.ascent(), 1.0)) < 1e-6,
          "o tamanho da marca guardado e' o mesmo da conta direta")
    checa(manipulador.intrinsicSize(doc, pos, fmt) == guardado, "o segundo pedido vem do cache")
    fonte = QFont(doc.defaultFont())
    fonte.setPointSizeF(fonte.pointSizeF() * 2)
    doc.setDefaultFont(fonte)
    maior = manipulador.intrinsicSize(doc, pos, fmt)
    m2 = QFontMetricsF(fonte_de(doc, fmt))
    checa(abs(maior.height() - max(m2.ascent(), 1.0)) < 1e-6,
          "trocar a fonte padrao troca o tamanho (a chave tem a fonte padrao)")
    _fechar(painel)


def _formato(doc, pos):
    from editdoc.ponte_qt import links
    return links.formato_em(doc, pos)


# -- p95 --------------------------------------------------------------------------------------

def _p95_digitando(painel, pos: int, teclas: int = 80) -> float:
    _ir(painel, pos)
    for _ in range(5):
        _tecla(painel)
        painel.viewport().grab()
    tempos = []
    for _ in range(teclas):
        t = time.perf_counter()
        _tecla(painel)
        painel.viewport().grab()
        tempos.append((time.perf_counter() - t) * 1000)
    for _ in range(teclas + 5):
        painel.undo()
    painel.viewport().grab()
    return _p95(tempos)


#: Quanto o manual pode custar a mais que o documento simples medido na mesma hora, numa maquina
#: mais lenta que a do gate. Medido nesta maquina, a frio: o manual custa ~2x o simples (sumario
#: com links, PAGEREF e pontilhado; capa com objetos). Na 0.1.7 o sumario custava 20x (94 ms).
FATOR_DO_SIMPLES = 2.5


def testar_p95() -> None:
    secao("p95 da digitacao (80 teclas com a pintura): capa, sumario e corpo")
    manual, simples = manual_sintetico(), documento_simples()

    def medir(docx: bytes, nome: str) -> float:
        # Um painel por medida, fechado e destruido depois: um segundo painel aberto (com o
        # caret piscando e pintura pendente) entra na conta do outro (medido: o dobro).
        painel = _painel(docx)
        try:
            return _p95_digitando(painel, _ponto(painel, nome))
        finally:
            _fechar(painel)
            painel.deleteLater()
            drenar_eventos()

    for nome in ("capa", "sumario", "corpo"):
        # Duas tentativas: a maquina de desenvolvimento roda outras coisas, e um pico de carga
        # no meio das 80 teclas nao e' o editor. A referencia e' medida logo antes, na mesma hora.
        for tentativa in range(2):
            referencia = medir(simples, "corpo")
            p95 = medir(manual, nome)
            limite = max(GATE_MS, referencia * FATOR_DO_SIMPLES + 2.0)
            if p95 <= limite:
                break
        print(f"         {nome}: p95 {p95:.1f} ms (documento simples: {referencia:.1f} ms; "
              f"tentativa {tentativa + 1})")
        checa(p95 <= limite, f"{nome}: p95 {p95:.1f} ms no gate ({GATE_MS:.0f} ms) ou ate' "
                             f"{FATOR_DO_SIMPLES}x o documento simples ({referencia:.1f} ms)")


def main() -> int:
    # As fontes do Windows antes de qualquer documento, como no gate: o fallback do offscreen e'
    # duas vezes mais largo e quebra linha a toda hora; carregadas depois, o Qt continua com o
    # fallback que ja' tinha escolhido (medido: o p95 dobra).
    usar_fonte_windows()
    usar_fontes_do_documento()
    # O relogio primeiro: as conferencias de pixel abaixo esquentam a maquina (medido: o p95 do
    # documento simples vai de 5 para 10 ms depois delas).
    testar_p95()
    testar_conferencia()
    testar_tiles()
    testar_cache_igual()
    testar_caches_de_pintura()
    testar_pontilhado_e_marcas()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
