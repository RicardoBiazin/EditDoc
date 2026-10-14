"""Altura do cabecalho e do rodape por pagina (0.1.8): o corpo de cada folha comeca onde o
cabecalho DELA termina, como no Word.

Ate' a 0.1.7 o corpo usava a mesma altura em todas as paginas (a maior das variantes): na capa
de um manual com o cabecalho da primeira pagina vazio, o corpo (e os objetos ancorados nele)
comecava 0,6 cm abaixo do Word. Fixture em codigo: primeira pagina diferente com o cabecalho
dela vazio e o padrao alto; pares e impares com alturas diferentes; rodapes de alturas
diferentes. Oraculo em twips: topo = max(margem de cima, distancia do cabecalho + altura do
cabecalho da pagina), sem o pe' do corpo passar do rodape da pagina; a altura do corpo (`hb`) e'
a mesma em todas (o limite registrado em docs/ARQUITETURA.md).

- topo do corpo por pagina (layout, mapa da tela e folha do PDF) contra o oraculo;
- numero de paginas igual ao do layout com o cabecalho alto em todas (a capacidade nao muda);
- objeto flutuante relativo ao paragrafo na pagina 1 sobe junto com o corpo;
- clique (hit-test) e zona (cabecalho ou corpo) seguem o topo da pagina;
- tela (tiles) e PDF pintam o texto no topo da pagina;
- o cabecalho da primeira pagina que cresce empurra so' a primeira pagina;
- contraprova: com a altura unica de antes, as verificacoes acusam.
"""

from __future__ import annotations

import math

from ajudantes import (checa, checa_igual, drenar_eventos, preparar_qt, resumir, secao,
                       usar_fonte_windows, usar_fontes_do_documento)
import fixtures_docx as fx

preparar_qt()

import teste_flutuantes as tf  # noqa: E402  (fixtures de objeto flutuante em codigo)
from editdoc.modelo.campos import tipo_da_pagina  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402
from editdoc.modelo.pagina import Pagina  # noqa: E402

EMU = 635
LINHAS = 160
DESLOCAMENTO_TW = 500  # o objeto fica 500 twips abaixo do topo do paragrafo-ancora


def _linhas(n: int, rotulo: str) -> list[Paragrafo]:
    return [Paragrafo(runs=[Run(f"{rotulo} {i + 1}")]) for i in range(n)]


def _docx(variantes: bool = True) -> bytes:
    """`variantes`: primeira, par e padrao com alturas diferentes. Sem elas, o cabecalho alto
    (o padrao) e o rodape alto valem para todas as paginas: e' a referencia da capacidade."""
    if variantes:
        pagina = Pagina(primeira_diferente=True, pares_impares=True, cabecalho_tw=708,
                        rodape_tw=708)
        cabecalhos = {"primeira": [Paragrafo()], "padrao": _linhas(5, "Cabeçalho ímpar"),
                      "par": _linhas(3, "Cabeçalho par")}
        rodapes = {"padrao": _linhas(4, "Rodapé ímpar"), "par": _linhas(1, "Rodapé par")}
    else:
        pagina = Pagina(cabecalho_tw=708, rodape_tw=708)
        cabecalhos = {"padrao": _linhas(5, "Cabeçalho ímpar")}
        rodapes = {"padrao": _linhas(4, "Rodapé ímpar")}
    base = Documento(pagina=pagina, paragrafos=_linhas(LINHAS, "Linha do corpo"),
                     cabecalhos=cabecalhos, rodapes=rodapes)
    corpo = ("<w:p>"
             + tf.ancora(95, tf.URI_FORMA, tf.forma(2000 * EMU, 1000 * EMU), 2000 * EMU, 1000 * EMU,
                         h=("margin", "posOffset", 0),
                         v=("paragraph", "posOffset", DESLOCAMENTO_TW * EMU),
                         quebra="<wp:wrapNone/>")
             + tf.ancora(96, tf.URI_FORMA, tf.forma(1000 * EMU, 500 * EMU, cor="0000FF"),
                         1000 * EMU, 500 * EMU, h=("page", "posOffset", 300 * EMU),
                         v=("page", "posOffset", 300 * EMU), quebra="<wp:wrapNone/>")
             + "<w:r><w:t>Primeiro paragrafo, com os objetos.</w:t></w:r></w:p>")
    return fx.docx_com_corpo_de_objetos(corpo, (), {}, (), (), documento=base)


def _painel(docx: bytes):
    painel = tf._painel()
    painel.resize(900, 1300)
    tf._carregar(painel, docx)
    painel.show()
    drenar_eventos()
    painel.viewport().grab()
    return painel


def _fechar(painel) -> None:
    painel.documento_corpo().setModified(False)
    painel.close()
    drenar_eventos()


def oraculo(layout) -> dict:
    """Topo (e pe') do corpo por tipo de pagina, so' com as alturas das faixas e a pagina."""
    p = layout.pagina_arquivo
    alturas = {}
    for onde in ("cabecalho", "rodape"):
        for tipo in ("primeira", "par", "padrao"):
            faixa = layout.faixas.obter(onde, tipo)
            alturas[(onde, tipo)] = faixa.altura() if faixa is not None else 0.0

    def de_cima(h):
        return max(p.margem_sup_tw, p.cabecalho_tw + math.ceil(h)) if h > 0 else p.margem_sup_tw

    def de_baixo(h):
        return max(p.margem_inf_tw, p.rodape_tw + math.ceil(h)) if h > 0 else p.margem_inf_tw

    ativos = ["padrao"] + (["primeira"] if p.primeira_diferente else []) \
        + (["par"] if p.pares_impares else [])
    hb = p.altura_tw - max(de_cima(alturas[("cabecalho", t)]) for t in ativos) \
        - max(de_baixo(alturas[("rodape", t)]) for t in ativos)
    saida = {"hb": hb}
    for tipo in ("primeira", "par", "padrao"):
        topo = de_cima(alturas[("cabecalho", tipo)])
        pe_maximo = p.altura_tw - de_baixo(alturas[("rodape", tipo)])
        saida[tipo] = min(topo, pe_maximo - hb)
        saida[("pe", tipo)] = pe_maximo
    return saida


def erros_de_topo(painel, paginas=range(5)) -> list[str]:
    """O que nao bate com o oraculo: layout, mapa da tela e corpo dentro do rodape."""
    layout = painel.layout_pag
    esperado = oraculo(layout)
    erros = []
    if abs(layout.hb - esperado["hb"]) > 0.5:
        erros.append(f"hb {layout.hb} != {esperado['hb']}")
    m = painel.mapa()
    total = painel.total_de_paginas()
    for n in paginas:
        tipo = tipo_da_pagina(n, layout.pagina_arquivo)
        topo = esperado[tipo]
        if abs(layout.topo_da_pagina(n) - topo) > 0.5:
            erros.append(f"pagina {n + 1} ({tipo}): topo {layout.topo_da_pagina(n)} != {topo}")
        # Mapa da tela: o y do documento no topo da pagina n cai no topo do corpo da folha.
        _x, y = m.doc_para_tela(0.0, n * layout.hb + 1.0, total)
        _fx, fy, _fw, _fh = m.folha_na_tela(n)
        y_tw = (y - fy) / m.escala - 1.0
        if abs(y_tw - topo) > 1.0:
            erros.append(f"pagina {n + 1}: mapa da tela poe o topo em {y_tw:.0f} (esperado {topo})")
        if layout.topo_da_pagina(n) + layout.hb > esperado[("pe", tipo)] + 0.5:
            erros.append(f"pagina {n + 1}: o corpo passa do rodape")
    return erros


def testar_topo_por_pagina() -> None:
    secao("topo do corpo por pagina: primeira (cabecalho vazio), par e impar (alturas diferentes)")
    painel = _painel(_docx())
    layout = painel.layout_pag
    esperado = oraculo(layout)
    print(f"         oraculo (twips): primeira {esperado['primeira']}, par {esperado['par']}, "
          f"padrao {esperado['padrao']}, hb {esperado['hb']}")
    checa(esperado["primeira"] == 1440 and esperado["padrao"] > esperado["par"] > 1440,
          "a fixture tem tres topos diferentes (primeira na margem, padrao mais baixo que a par)")
    erros = erros_de_topo(painel)
    checa_igual(erros, [], "topo de cada pagina (layout e mapa da tela) igual ao oraculo, e o "
                           "corpo dentro do rodape da pagina")
    checa_igual(layout.efetiva_da(0).corpo_altura_tw(), layout.efetiva_da(2).corpo_altura_tw(),
                "a altura do corpo e' a mesma em todas as paginas (limite registrado)")
    # Contraprova: a altura unica de antes (a maior) acusa.
    original = type(layout).topo_da_pagina
    type(layout).topo_da_pagina = lambda self, n: float(self.pagina.margem_sup_tw)
    try:
        sabotado = erros_de_topo(painel)
    finally:
        type(layout).topo_da_pagina = original
    checa(any("pagina 1 (primeira)" in e for e in sabotado),
          f"contraprova: com a altura unica, a primeira pagina acusa ({len(sabotado)} erros)")
    _fechar(painel)


def testar_paginas() -> None:
    secao("numero de paginas: o mesmo do cabecalho alto em todas (a capacidade nao muda)")
    painel = _painel(_docx())
    total = painel.total_de_paginas()
    hb = painel.layout_pag.hb
    doc = painel.documento_corpo()
    dl = doc.documentLayout()
    # Passo de um paragrafo para o seguinte (linha mais o espaco depois do paragrafo).
    altura_linha = dl.blockBoundingRect(doc.findBlockByNumber(6)).top()         - dl.blockBoundingRect(doc.findBlockByNumber(5)).top()
    _fechar(painel)
    referencia = _painel(_docx(variantes=False))
    total_ref = referencia.total_de_paginas()
    hb_ref = referencia.layout_pag.hb
    _fechar(referencia)
    checa_igual(hb, hb_ref, "o corpo tem a altura do layout com o cabecalho e o rodape altos")
    checa_igual(total, total_ref, f"{total} paginas, como no layout de referencia")
    estimativa = math.ceil(LINHAS / math.floor(hb / altura_linha))
    checa(abs(total - estimativa) <= 1, f"e perto da conta a mao: {LINHAS} linhas de "
                                        f"{altura_linha:.0f} twips em {hb:.0f} por pagina "
                                        f"(~{estimativa})")


def testar_objeto_e_clique() -> None:
    secao("objeto relativo ao paragrafo sobe com o corpo; clique e zona seguem o topo da pagina")
    from PySide6.QtCore import QPointF, Qt
    from editdoc.modelo import flutuantes as mf
    painel = _painel(_docx())
    layout = painel.layout_pag
    esperado = oraculo(layout)
    g = layout.flutuantes
    itens = g.lista()
    checa_igual(len(itens), 2, "dois objetos na capa")
    rel_paragrafo = next(i for i in itens if i[4].ancoragem.v_rel == "paragraph")
    rel_pagina = next(i for i in itens if i[4].ancoragem.v_rel == "page")
    n, ref, _d = g.referencia(rel_paragrafo[0])
    _x, y, _w, _h = mf.retangulo(rel_paragrafo[4].ancoragem, ref)
    checa(n == 0 and abs(y - (esperado["primeira"] + DESLOCAMENTO_TW)) < 1.0,
          f"objeto relativo ao paragrafo: y = topo da primeira pagina + 500 ({y:.0f} twips; "
          f"esperado {esperado['primeira'] + DESLOCAMENTO_TW})")
    n2, ref2, _d2 = g.referencia(rel_pagina[0])
    _x2, y2, _w2, _h2 = mf.retangulo(rel_pagina[4].ancoragem, ref2)
    checa(abs(y2 - 300) < 1.0, f"objeto relativo a' pagina nao muda ({y2:.0f} twips)")

    m = painel.mapa()
    total = painel.total_de_paginas()

    def ponto(n, y_tw):
        fx_, fy, _fw, _fh = m.folha_na_tela(n)
        return QPointF(fx_ + 3000 * m.escala, fy + y_tw * m.escala)

    for n in (0, 1, 2):
        tipo = tipo_da_pagina(n, layout.pagina_arquivo)
        topo = esperado[tipo]
        pos = painel.posicao_em(ponto(n, topo + 60))
        primeira = layout.doc.documentLayout().hitTest(QPointF(10, n * layout.hb + 10),
                                                       Qt.HitTestAccuracy.FuzzyHit)
        bloco_clicado = layout.doc.findBlock(pos).blockNumber()
        bloco_topo = layout.doc.findBlock(primeira).blockNumber()
        checa_igual(bloco_clicado, bloco_topo,
                    f"pagina {n + 1} ({tipo}): clique logo abaixo do topo cai na primeira linha "
                    "da pagina")
        checa_igual(painel.zona_em(ponto(n, topo - 40))[0], "cabecalho",
                    f"pagina {n + 1}: logo acima do topo e' cabecalho")
        checa_igual(painel.zona_em(ponto(n, topo + 40))[0], "corpo",
                    f"pagina {n + 1}: logo abaixo do topo e' corpo")
    checa(painel.zona_em(ponto(2, 1500))[0] == "cabecalho",
          "pagina 3 (impar, cabecalho alto): abaixo da margem, ainda cabecalho")
    checa(total >= 3, f"a fixture tem paginas suficientes ({total})")
    _fechar(painel)


def _primeira_tinta(img, x0: int, x1: int, y_de: int) -> int | None:
    """Primeira linha (y) com pixel escuro entre x0 e x1, a partir de y_de."""
    from PySide6.QtGui import QColor
    for y in range(max(0, y_de), img.height()):
        for x in range(x0, x1, 2):
            c = QColor(img.pixel(x, y))
            if c.red() < 90 and c.green() < 90 and c.blue() < 90:
                return y
    return None


def testar_pintura() -> None:
    secao("tela e PDF: o texto do corpo aparece no topo da pagina")
    from PySide6.QtGui import QColor, QImage, QPainter
    from editdoc.interface import impressao
    usar_fonte_windows()
    usar_fontes_do_documento()
    painel = _painel(_docx())
    layout = painel.layout_pag
    esperado = oraculo(layout)
    doc = painel.documento_corpo()
    altura_linha = doc.documentLayout().blockBoundingRect(doc.findBlockByNumber(5)).height()
    dpi = 144
    por_tw = dpi / 1440.0
    p = layout.pagina_arquivo
    for n in (0, 1, 2):
        tipo = tipo_da_pagina(n, p)
        img = QImage(round(p.largura_tw * por_tw), round(p.altura_tw * por_tw),
                     QImage.Format.Format_ARGB32)
        img.fill(QColor(255, 255, 255))
        pintor = QPainter(img)
        impressao.pintar_pagina(pintor, layout, n, painel.total_de_paginas(),
                                impressao.transformacao(dpi, dpi))
        pintor.end()
        # Procura a tinta do corpo abaixo do cabecalho da propria pagina (o objeto e' vermelho).
        faixa = layout.faixas.obter("cabecalho", tipo)
        fim_cabecalho = p.cabecalho_tw + (faixa.altura() if faixa is not None else 0)
        x0 = round((p.margem_esq_tw + 40) * por_tw)
        y = _primeira_tinta(img, x0, x0 + 150, round((fim_cabecalho + 20) * por_tw))
        topo = esperado[tipo]
        achado = round(y / por_tw) if y is not None else None
        checa(y is not None and topo * por_tw - 2 <= y <= (topo + altura_linha) * por_tw,
              f"PDF, pagina {n + 1} ({tipo}): texto do corpo a partir de {topo} twips "
              f"(tinta em {achado})")
    # Tela: a folha 1 pelos tiles, a 100%.
    painel.definir_zoom(1.0)
    painel.rolar_para_pagina(0, folga=0)
    painel._limpar_cache()
    tela = painel.viewport().grab().toImage()
    m = painel.mapa()
    fx_, fy, _fw, _fh = m.folha_na_tela(0)
    x0 = round(fx_ + (p.margem_esq_tw + 40) * m.escala)
    y = _primeira_tinta(tela, x0, x0 + 100, round(fy + 20 * m.escala))
    y_tw = (y - fy) / m.escala if y is not None else None
    checa(y_tw is not None and esperado["primeira"] - 20 <= y_tw <= esperado["primeira"] + altura_linha,
          f"tela, pagina 1: texto do corpo a partir de {esperado['primeira']} twips "
          f"(tinta em {y_tw if y_tw is None else round(y_tw)})")
    _fechar(painel)


def testar_cabecalho_que_cresce() -> None:
    secao("o cabecalho da primeira pagina que cresce empurra so' a primeira pagina")
    from PySide6.QtGui import QTextCursor
    painel = _painel(_docx())
    layout = painel.layout_pag
    antes = [layout.topo_da_pagina(n) for n in range(4)]
    faixa = layout.faixas.obter("cabecalho", "primeira")
    c = QTextCursor(faixa.doc)
    c.movePosition(QTextCursor.MoveOperation.End)
    for i in range(4):
        c.insertText(f"Linha {i} da capa")
        c.insertBlock()
    drenar_eventos()
    depois = [layout.topo_da_pagina(n) for n in range(4)]
    esperado = oraculo(layout)
    checa(depois[0] > antes[0] and abs(depois[0] - esperado["primeira"]) < 0.5,
          f"primeira pagina desce de {antes[0]:.0f} para {depois[0]:.0f} twips (oraculo "
          f"{esperado['primeira']})")
    checa_igual(depois[1:], antes[1:], "as outras paginas ficam onde estavam")
    checa_igual(erros_de_topo(painel), [], "e tudo continua igual ao oraculo")
    faixa.doc.undo()
    drenar_eventos()
    _fechar(painel)


def main() -> int:
    testar_topo_por_pagina()
    testar_paginas()
    testar_objeto_e_clique()
    testar_pintura()
    testar_cabecalho_que_cresce()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
