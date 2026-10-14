"""Galeria de estilos, painel de estilos e faixa final (M6).

A galeria mostra miniaturas com a aparencia do estilo e marca o estilo do cursor; o
clique aplica. A faixa, com as abas maiores, continua recolhendo sem cortar nada de
1920 a 820 px, em todas as abas.
"""

from __future__ import annotations

from ajudantes import (checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao,
                       usar_fonte_windows)

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

import copy  # noqa: E402

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QFont, QTextCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QComboBox, QFontComboBox, QLabel, QToolButton  # noqa: E402

from editdoc import configuracao  # noqa: E402
from editdoc.edicao import estilos as ed  # noqa: E402
from editdoc.interface.galeria_estilos import miniatura  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402
from editdoc.interface.planejamento import recolher_com_galeria  # noqa: E402
from editdoc.modelo.estilos import catalogo_padrao  # noqa: E402

CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
LARGURAS = (1920, 1400, 1200, 1000, 820)
# 0.1.6: a aba Revisao (comentarios) entrou entre Layout e Exibir, como no Word.
# Reescrita na 0.1.10: a aba Referencias (notas de rodape e de fim) entrou entre Layout e
# Revisao, na ordem do Word. A conferencia continua a mesma: todas as abas, nada cortado.
ABAS = ("Página Inicial", "Inserir", "Layout", "Referências", "Revisão", "Exibir")


def _janela() -> JanelaPrincipal:
    usar_fonte_windows(9)
    j = JanelaPrincipal(configuracao.padrao())
    j.show()
    drenar_eventos()
    j.painel.setFocus()
    return j


def _fechar(j) -> None:
    j.painel.documento_corpo().setModified(False)
    j.close()


def _tinta(img) -> int:
    n = 0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = img.pixelColor(x, y)
            if c.red() < 200 or c.green() < 200 or c.blue() < 200:
                n += 1
    return n


def testar_miniaturas() -> None:
    secao("miniaturas: a amostra tem a aparencia do estilo")
    usar_fonte_windows(9)
    cat = catalogo_padrao()
    fonte = QFont("Segoe UI", 11)
    normal = miniatura(cat.obter("Normal"), cat, fonte).toImage()
    titulo = miniatura(cat.obter("Heading1"), cat, fonte).toImage()
    checa(_tinta(normal) > 0 and _tinta(titulo) > 0, "as miniaturas nao sao brancas")
    checa(normal != titulo, "Titulo 1 e Normal tem miniaturas diferentes")
    checa(normal == miniatura(cat.obter("Normal"), cat, fonte).toImage(),
          "contraprova: o mesmo estilo da' a mesma miniatura")
    azul = 0
    for y in range(titulo.height()):
        for x in range(titulo.width()):
            c = titulo.pixelColor(x, y)
            if c.blue() > c.red() + 40:
                azul += 1
    checa(azul > 0, "a miniatura do Titulo 1 tem a cor azul do estilo")


def testar_planejamento() -> None:
    secao("planejamento com a galeria (funcao pura)")
    exp, rec = [100, 300, 300, 100], [50, 200, 60, 40]
    ordem = [3, 0, 2, 1]
    gal = [60, 90, 170, 250, 330, 410, 490]
    checa_igual(recolher_com_galeria(exp, rec, ordem, gal, 5, 2, 2000),
                ([False] * 4, 6), "tudo cabe: nada recolhe e a galeria cresce ate' o fim")
    estados, n = recolher_com_galeria(exp, rec, ordem, gal, 5, 2, 1100)
    checa(estados == [False, False, False, True] and n >= 2,
          "falta pouco: o grupo Edicao recolhe antes de a galeria encolher abaixo do minimo")
    estados, n = recolher_com_galeria(exp, rec, ordem, gal, 5, 2, 560)
    checa(n == 0 and not estados[1], "falta muito: a galeria vira botao antes de a Fonte recolher")
    checa_igual(recolher_com_galeria(exp, rec, ordem, gal, 5, 2, 10)[0], [True] * 4,
                "contraprova: nada cabe, tudo recolhe")


def testar_galeria_reflete_cursor() -> None:
    secao("galeria: estilo do cursor marcado, clique aplica")
    j = _janela()
    p = j.painel
    g = j.faixa.galeria
    rapidos = [e.id for e in catalogo_padrao().rapidos()]
    checa_igual(g.ids(), rapidos, "a galeria tem os estilos rapidos, na ordem do Word")
    QTest.keyClicks(p, "Capitulo")
    QTest.keyClick(p, Qt.Key.Key_Return)
    QTest.keyClicks(p, "texto forte")
    c = p.textCursor()
    c.setPosition(0)
    p.setTextCursor(c)
    QTest.keyClick(p, Qt.Key.Key_1, CTRL | ALT)
    drenar_eventos()
    checa_igual(g.atual(), "Heading1", "cursor no Titulo 1: a miniatura do Titulo 1 marcada")
    checa(g.botao("Heading1").isChecked() and not g.botao("Normal").isChecked(),
          "so' uma miniatura marcada")
    c.setPosition(12)
    p.setTextCursor(c)
    drenar_eventos()
    checa_igual(g.atual(), "Normal", "cursor no paragrafo Normal: Normal marcado")
    c.setPosition(15)
    c.setPosition(20, QTextCursor.MoveMode.KeepAnchor)
    p.setTextCursor(c)
    ed.aplicar_estilo(p, "Strong")
    c.setPosition(17)
    p.setTextCursor(c)
    drenar_eventos()
    checa_igual(g.atual(), "Strong", "dentro de texto Forte: Forte marcado")
    j.faixa.resize(1920, j.faixa.height())
    j.resize(1920, 800)
    drenar_eventos()
    b = g.botao("Quote")
    checa(b is not None and b.isVisible(), "a miniatura Citacao esta' visivel em 1920 px")
    c.setPosition(2)
    p.setTextCursor(c)
    QTest.mouseClick(b, Qt.MouseButton.LeftButton)
    drenar_eventos()
    checa_igual(ed.estilo_no_cursor(p)[0], "Quote", "clicar na miniatura aplica o estilo")
    checa_igual(g.atual(), "Quote", "e a galeria passa a marcar a Citacao")
    p.undo()
    g.mostrar(2)
    g.marcar("Strong")
    checa("Strong" in g.visiveis() and len(g.visiveis()) == 2,
          "com 2 miniaturas, marcar um estilo de fora rola a galeria ate' ele")
    antes = g.visiveis()
    g.rolar(-1)
    checa(g.visiveis() != antes, "a seta rola a galeria")
    menu = g.menu_tudo()
    textos = [a.text() for a in menu.actions() if a.text()]
    botoes = [b.property("sid") for b in menu.findChildren(QToolButton) if b.property("sid")]
    checa_igual(botoes, rapidos, "expandir mostra todas as miniaturas")
    checa(any("Criar um estilo" in t for t in textos) and any("Limpar toda" in t for t in textos),
          "e os comandos Criar um estilo e Limpar toda a formatacao")
    rec = j.faixa.grupo_estilos.menu_recolhido()
    nomes = [a.text() for a in rec.actions()]
    checa("Título 1" in nomes and "Forte" in nomes, "recolhida, o menu Estilos lista os mesmos estilos")
    _fechar(j)


def testar_galeria_acompanha_catalogo() -> None:
    secao("galeria e painel acompanham o catalogo (estilo novo, desfazer)")
    j = _janela()
    p = j.painel
    QTest.keyClicks(p, "abc")
    sid = ed.criar_da_selecao(p, "Novo Rapido")
    drenar_eventos()
    checa(sid in j.faixa.galeria.ids(), "o estilo criado entra na galeria")
    checa_igual(j.faixa.galeria.atual(), sid, "e fica marcado")
    p.undo()
    drenar_eventos()
    checa(sid not in j.faixa.galeria.ids(), "desfazer tira o estilo da galeria")
    _fechar(j)


def testar_painel_de_estilos() -> None:
    secao("painel de estilos: Ctrl+Alt+Shift+S, lista completa, clique aplica")
    j = _janela()
    p = j.painel
    checa(j.dock_estilos.isHidden(), "o painel nasce escondido")
    QTest.keyClick(p, Qt.Key.Key_S, CTRL | ALT | SHIFT)
    drenar_eventos()
    checa(not j.dock_estilos.isHidden(), "Ctrl+Alt+Shift+S mostra o painel")
    checa(j.comandos.acao("painel_estilos").isChecked(), "o botao Estilos fica marcado")
    ids = j.painel_estilos.ids()
    checa({"Normal", "Heading1", "Strong", "Quote"} <= set(ids), "a lista tem os estilos")
    item = next(j.painel_estilos.lista.item(i) for i in range(j.painel_estilos.lista.count())
                if j.painel_estilos.lista.item(i).data(Qt.ItemDataRole.UserRole) == "Heading2")
    QTest.keyClicks(p, "linha")
    r = j.painel_estilos.lista.visualItemRect(item)
    QTest.mouseClick(j.painel_estilos.lista.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, r.center())
    drenar_eventos()
    checa_igual(ed.estilo_no_cursor(p)[0], "Heading2", "clicar no item aplica o estilo")
    checa_igual(j.painel_estilos.atual(), "Heading2", "o item do estilo do cursor fica marcado")
    j.painel_estilos.visualizar.setChecked(True)
    checa(j.painel_estilos.lista.item(0).font().pointSizeF() > 0, "visualizacao liga sem erro")
    QTest.keyClick(p, Qt.Key.Key_S, CTRL | ALT | SHIFT)
    drenar_eventos()
    checa(j.dock_estilos.isHidden(), "o mesmo atalho esconde o painel")
    _fechar(j)


def _cortados(faixa) -> list[str]:
    largura = faixa.width()
    saida = []
    for tipo in (QToolButton, QComboBox, QFontComboBox, QLabel):
        for w in faixa.findChildren(tipo):
            if not w.isVisibleTo(faixa):
                continue
            caixa = QRect(w.mapTo(faixa, QPoint(0, 0)), w.size())
            if caixa.left() < 0 or caixa.right() > largura or w.width() < w.minimumSizeHint().width():
                saida.append(f"{type(w).__name__}:{w.text() if hasattr(w, 'text') else ''}")
    return saida


def testar_faixa_em_todas_as_abas() -> None:
    secao("faixa final: seis abas, nada cortado de 1920 a 820 px")
    j = _janela()
    faixa = j.faixa
    checa_igual(faixa.abas_visiveis(), list(ABAS),
                "abas Pagina Inicial, Inserir, Layout, Referencias, Revisao e Exibir")
    checa(faixa.minimumWidth() <= 820, f"a faixa cabe em 820 px (minimo {faixa.minimumWidth()})")
    miniaturas = {}
    fonte_recolhida = {}
    for aba in ABAS:
        faixa.abrir_aba(aba)
        for largura in LARGURAS:
            j.resize(largura, 800)
            drenar_eventos()
            cortados = _cortados(faixa)
            checa(not cortados, f"{aba}, {largura} px: nada cortado ({cortados})")
            if aba == "Página Inicial":
                miniaturas[largura] = faixa.miniaturas_visiveis()
                fonte_recolhida[largura] = faixa.recolhidos()[1]
    checa(miniaturas[1920] >= 5, f"em 1920 px a galeria mostra 5 ou mais miniaturas ({miniaturas[1920]})")
    checa(miniaturas[1400] >= 2, f"em 1400 px ainda ha' miniaturas ({miniaturas[1400]})")
    checa(not any(fonte_recolhida.values()),
          f"a galeria nunca faz a Fonte recolher ({miniaturas}, {fonte_recolhida})")
    checa_igual(miniaturas[820], 0, "em 820 px a galeria vira o botao Estilos")
    faixa.abrir_aba("Inserir")
    faixa.setFixedWidth(300)
    drenar_eventos()
    checa(bool(_cortados(faixa)), "contraprova: Inserir em 300 px e' acusada como cortada")
    faixa.setMinimumWidth(0)
    faixa.setMaximumWidth(16777215)
    _fechar(j)


def main() -> int:
    testar_miniaturas()
    testar_planejamento()
    testar_galeria_reflete_cursor()
    testar_galeria_acompanha_catalogo()
    testar_painel_de_estilos()
    testar_faixa_em_todas_as_abas()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
