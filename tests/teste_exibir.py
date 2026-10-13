"""Aba Exibir e Layout (M6): zoom por modo, folhas lado a lado, regua, marcas de
formatacao, painel de navegacao e recuos/espacamento do paragrafo na aba Layout."""

from __future__ import annotations

from ajudantes import (checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao,
                       usar_fonte_windows)

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from editdoc import configuracao  # noqa: E402
from editdoc.edicao import estilos as ed  # noqa: E402
from editdoc.formato_docx.leitor import ler as ler_docx  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402
from editdoc.modelo.folhas import MARGEM_DO_PAINEL_PX, Mapa  # noqa: E402
from editdoc.modelo.pagina import TWIPS_POR_CM, Pagina  # noqa: E402

import fixtures_docx as fx  # noqa: E402

CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


def _janela(doc: Documento | None = None) -> JanelaPrincipal:
    usar_fonte_windows(9)
    j = JanelaPrincipal(configuracao.padrao())
    j.resize(1400, 900)
    j.show()
    drenar_eventos()
    if doc is not None:
        import pathlib
        j.carregar(doc, [], pathlib.Path("teste.docx"))
        drenar_eventos()
    j.painel.setFocus()
    return j


def _fechar(j) -> None:
    j.painel.documento_corpo().setModified(False)
    j.close()


def _longo(n: int = 120) -> Documento:
    return Documento(paragrafos=[Paragrafo(runs=[Run(f"Parágrafo {i}: texto para encher páginas "
                                                     "e mais páginas do documento.")])
                                 for i in range(n)])


def testar_mapa_em_colunas() -> None:
    secao("mapa com folhas lado a lado (sem Qt)")
    m1 = Mapa(Pagina(), 0.5, 1400, 900)
    m2 = Mapa(Pagina(), 0.5, 1400, 900, colunas=2)
    checa_igual(m2.altura_total(3), m2.vao + 2 * m2.passo_vertical, "3 paginas em 2 colunas: 2 linhas")
    x0, y0, _, _ = m2.folha_na_tela(0)
    x1, y1, _, _ = m2.folha_na_tela(1)
    checa(x1 > x0 and y1 == y0, "pagina 2 ao lado da 1, na mesma linha")
    checa_igual(m2.folha_na_tela(2)[0], x0, "pagina 3 na linha de baixo, primeira coluna")
    hb = m2.hb
    ponto = m2.doc_para_tela(500.0, hb + 300.0, 3)
    volta = m2.tela_para_doc(*ponto, 3)
    checa(abs(volta[0] - 500) < 1e-6 and abs(volta[1] - (hb + 300)) < 1e-6,
          "ida e volta tela-documento na pagina da segunda coluna")
    checa_igual(m1.folha_na_tela(1)[0], m1.folha_na_tela(0)[0],
                "contraprova: com uma coluna as folhas ficam uma embaixo da outra")


def testar_zoom_por_modo() -> None:
    secao("Exibir > Zoom: 100%, uma pagina, varias paginas e largura da pagina")
    j = _janela(_longo())
    p = j.painel
    vp = p.viewport()
    j.comandos.acao("zoom_largura").trigger()
    drenar_eventos()
    m = p.mapa()
    checa(abs(m.largura_folha - (vp.width() - 2 * MARGEM_DO_PAINEL_PX)) <= 2,
          f"largura da pagina: a folha ocupa a largura util ({m.largura_folha:.0f} de {vp.width()})")
    j.comandos.acao("zoom_pagina").trigger()
    drenar_eventos()
    m = p.mapa()
    x, y, w, h = m.folha_na_tela(p.pagina_atual())
    checa(y >= -1 and y + h <= vp.height() + 1 and x >= 0 and x + w <= vp.width(),
          "uma pagina: a folha inteira aparece na janela")
    j.comandos.acao("zoom_varias").trigger()
    drenar_eventos()
    m = p.mapa()
    checa_igual(p.colunas(), 2, "varias paginas: duas colunas")
    a, b = m.folha_na_tela(0), m.folha_na_tela(1)
    checa(b[0] > a[0] + a[2] - 1 and b[1] == a[1] and b[0] + b[2] <= vp.width(),
          "as duas primeiras folhas lado a lado, dentro da janela")
    alvo = QPointF(b[0] + b[2] / 2, b[1] + b[3] / 2)
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, alvo.toPoint())
    drenar_eventos()
    checa_igual(p.pagina_atual(), 1, "clique na folha da direita poe o cursor na pagina 2")
    j.comandos.acao("zoom_100").trigger()
    drenar_eventos()
    checa_igual((p.zoom(), p.colunas()), (1.0, 1), "100%: zoom 1 e uma coluna")
    _fechar(j)


def testar_regua() -> None:
    secao("mostrar e esconder a regua")
    j = _janela()
    checa(j.regua.isVisible(), "a regua nasce visivel")
    checa(j.comandos.acao("mostrar_regua").isChecked(), "e o botao Regua nasce marcado")
    j.comandos.acao("mostrar_regua").trigger()
    drenar_eventos()
    checa(not j.regua.isVisible() and not j.comandos.acao("mostrar_regua").isChecked(),
          "Regua desmarcada esconde a regua")
    j.comandos.acao("mostrar_regua").trigger()
    drenar_eventos()
    checa(j.regua.isVisible(), "e marcada mostra de novo")
    _fechar(j)


def _azuis(img) -> int:
    n = 0
    for y in range(0, img.height(), 1):
        for x in range(0, img.width(), 1):
            c = img.pixelColor(x, y)
            if c.blue() > c.red() + 50 and c.blue() > 100:
                n += 1
    return n


def testar_marcas() -> None:
    secao("marcas de formatacao: pintadas na visao, sem mudar o layout")
    j = _janela(Documento(paragrafos=[Paragrafo(runs=[Run("um dois\ttres")]),
                                      Paragrafo(runs=[Run("quatro cinco")])]))
    p = j.painel
    p.definir_zoom(1.5)
    drenar_eventos()
    paginas = p.total_de_paginas()
    altura = p.layout_pag.doc.documentLayout().documentSize().height()
    sem = _azuis(p.viewport().grab().toImage())
    QTest.keyClick(p, Qt.Key.Key_8, CTRL | SHIFT)
    drenar_eventos()
    checa(p.marcas_visiveis() and j.comandos.acao("marcas_formatacao").isChecked(),
          "Ctrl+Shift+8 liga as marcas, e o botao fica marcado")
    com = _azuis(p.viewport().grab().toImage())
    checa(com > sem + 20, f"com marcas aparecem pixels azuis ({sem} -> {com})")
    checa(p.layout_pag.doc.documentLayout().documentSize().height() == altura
          and p.total_de_paginas() == paginas, "o layout nao muda")
    QTest.keyClick(p, Qt.Key.Key_8, CTRL | SHIFT)
    drenar_eventos()
    depois = _azuis(p.viewport().grab().toImage())
    checa(depois <= sem + 2, f"contraprova: desligar tira as marcas, sem tile velho ({depois})")
    _fechar(j)


def testar_navegacao() -> None:
    secao("painel de navegacao: titulos dos estilos e do outlineLvl, clique leva ao titulo")
    doc, _ = ler_docx(fx.docx_com_estilos_do_word())
    j = _janela(doc)
    p = j.painel
    checa(j.dock_navegacao.isHidden(), "o painel nasce escondido")
    j.comandos.acao("painel_navegacao").trigger()
    drenar_eventos()
    nav = j.navegacao
    checa(not j.dock_navegacao.isHidden(), "Painel de Navegacao mostra o painel")
    checa_igual(nav.textos(), ["Introdução", "Detalhe vermelho", "Anexo"],
                "titulos do Titulo 1, do Titulo 2 e do outlineLvl direto")
    checa_igual(nav.niveis(), [0, 1, 0], "Titulo 2 fica dentro do Titulo 1")
    nav.ir_para(1)
    drenar_eventos()
    checa_igual(p.textCursor().block().text(), "Detalhe vermelho", "clicar leva o cursor ao titulo")
    checa_igual(nav.item_atual(), "Detalhe vermelho", "e o titulo atual fica marcado")
    c = p.textCursor()
    c.setPosition(p.documento_corpo().findBlockByNumber(1).position())
    p.setTextCursor(c)
    ed.aplicar_estilo(p, "heading 3")
    checa(nav._timer.isActive(), "a mudanca agenda a lista nova (refeita depois de uma pausa)")
    nav.atualizar()
    checa_igual(nav.textos(), ["Introdução", "Texto com destaque no meio.", "Detalhe vermelho", "Anexo"],
                "aplicar Titulo 3 poe o paragrafo na navegacao")
    ed.aplicar_estilo(p, "normal")
    nav.atualizar()
    checa_igual(len(nav.textos()), 3, "contraprova: voltar ao Normal tira da navegacao")
    _fechar(j)


def testar_layout_paragrafo() -> None:
    secao("aba Layout: recuos e espacamento do paragrafo, um passo de desfazer")
    j = _janela(Documento(paragrafos=[Paragrafo(runs=[Run("primeiro")]),
                                      Paragrafo(runs=[Run("segundo")], espaco_antes_tw=240)]))
    p = j.painel
    f = j.faixa
    f.abrir_aba("Layout")
    antes = p.documento_corpo().toHtml()
    f.espaco_depois.setValue(12)
    bloco = p.documento_corpo().firstBlock()
    checa_igual(round(bloco.blockFormat().bottomMargin() * 15), 240, "12 pt depois do paragrafo")
    p.undo()
    checa(p.documento_corpo().toHtml() == antes, "um desfazer devolve")
    c = p.textCursor()
    c.setPosition(0)
    p.setTextCursor(c)  # o desfazer move o cursor
    f.recuo_esquerdo.setValue(1.0)
    # 0.1.4: o recuo horizontal fica em twips no bloco (o Qt nao escala margem horizontal).
    checa_igual(round(bloco.blockFormat().leftMargin()), round(TWIPS_POR_CM), "recuo esquerdo de 1 cm")
    f.recuo_direito.setValue(2.0)
    checa_igual(round(bloco.blockFormat().rightMargin()), round(2 * TWIPS_POR_CM), "recuo direito de 2 cm")
    c = p.textCursor()
    c.setPosition(p.documento_corpo().lastBlock().position())
    p.setTextCursor(c)
    drenar_eventos()
    checa_igual((f.espaco_antes.value(), f.recuo_esquerdo.value()), (12.0, 0.0),
                "os campos mostram o paragrafo do cursor")
    from editdoc.ponte_qt import de_qt
    m = de_qt.extrair(p.documento_corpo()).paragrafos[0]
    checa_igual((m.recuo_esquerdo_tw, m.recuo_direito_tw), (round(TWIPS_POR_CM), round(2 * TWIPS_POR_CM)),
                "o recuo direito chega ao modelo")
    _fechar(j)


def main() -> int:
    testar_mapa_em_colunas()
    testar_zoom_por_modo()
    testar_regua()
    testar_marcas()
    testar_navegacao()
    testar_layout_paragrafo()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
