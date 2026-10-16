"""Zoom e mouse em paginas: o zoom nao refaz o layout, Ctrl+roda e o controle da barra de status
mudam a escala, e clique, shift+clique e arrasto selecionam o texto certo em varias paginas.

Zoom: 25%, 100% e o teto de DPR 1 (300%). Cada troca tem uma contraprova.
"""

from __future__ import annotations

from ajudantes import checa, checa_igual, drenar_eventos, pular, preparar_qt, resumir, secao, usar_fonte_windows

QT = preparar_qt()

TEXTO = "\n".join(
    f"Paragrafo {i} com texto de tamanho suficiente para ocupar linhas inteiras da pagina, com acento "
    f"e palavras como documento, relatorio e revisao, para que o layout tenha varias paginas."
    for i in range(400))


def _painel():
    from editdoc.interface.painel_documento import PainelDocumento

    painel = PainelDocumento("Segoe UI", 11)
    painel.resize(1200, 640)
    painel.show()
    drenar_eventos(2)
    painel.setPlainText(TEXTO)
    # 0.1.17: as regras de paginacao do Word (viuvas e orfas) ajustam o layout na primeira
    # pintura; o teste compara com o layout ja' assentado.
    painel.layout_pag.atualizar_secoes()
    painel.document().clearUndoRedoStacks()
    painel.document().setModified(False)
    return painel


def _posicao_da_pagina(painel, n: int) -> int:
    """Uma posicao no comeco de um paragrafo que cai na pagina n (0-based)."""
    hb = painel.layout_pag.hb
    bloco = painel.document().begin()
    while bloco.isValid():
        if painel.layout_pag.origem_bloco(bloco).y() >= n * hb:
            return bloco.position() + 2
        bloco = bloco.next()
    raise AssertionError("nao ha paragrafo na pagina pedida")


def _tela_da_posicao(painel, pos: int):
    painel.garantir_visivel(painel.layout_pag.retangulo_cursor(pos))
    drenar_eventos(1)
    r = painel.layout_pag.retangulo_cursor(pos)
    x, y = painel.mapa().doc_para_tela(r.center().x(), r.center().y(), painel.total_de_paginas())
    return x, y


def testar_zoom_nao_refaz_layout() -> None:
    secao("zoom muda a escala, nao o layout: paginas e posicoes iguais")
    from PySide6.QtGui import QTextCursor

    painel = _painel()
    doc = painel.document()

    def assinatura():
        dl = doc.documentLayout()
        rects = []
        bloco = doc.begin()
        for _ in range(60):
            if not bloco.isValid():
                break
            r = dl.blockBoundingRect(bloco)
            rects.append((r.x(), r.y(), r.width(), r.height()))
            bloco = bloco.next()
        return doc.pageCount(), rects

    base = assinatura()
    for zoom in (0.25, 3.0, 0.25, 1.0, 2.0):
        painel.definir_zoom(zoom)
    checa_igual(assinatura(), base, "depois de trocar o zoom 5 vezes, paginas e posicoes sao as mesmas")
    checa_igual(painel.zoom(), min(2.0, painel.teto_do_zoom()),
                "o zoom pedido e' o zoom que vale (ate o teto da tela)")

    # Contraprova: mudar a pagina (margem) refaz o layout e tem de ser acusado.
    from editdoc.modelo.pagina import Pagina

    painel.definir_configuracao_pagina(Pagina().com_margens(4000, 4000, 1440, 1440))
    checa(assinatura() != base, "contraprova: mudar as margens refaz o layout e e' acusado")
    painel.definir_configuracao_pagina(Pagina())
    checa(assinatura() == base, "de volta a pagina padrao, o layout volta ao mesmo")
    cur = QTextCursor(doc)
    cur.movePosition(QTextCursor.MoveOperation.End)
    painel.setTextCursor(cur)
    painel.close()


def testar_ctrl_roda() -> None:
    secao("Ctrl+roda muda o zoom em passos; sem Ctrl a roda rola")
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    painel = _painel()
    vb = painel.verticalScrollBar()

    def roda(delta: int, ctrl: bool) -> None:
        modificador = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
        ev = QWheelEvent(QPointF(300, 300), QPointF(300, 300), QPoint(0, 0), QPoint(0, delta),
                         Qt.MouseButton.NoButton, modificador, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(painel.viewport(), ev)
        drenar_eventos(1)

    checa_igual(painel.zoom(), 1.0, "zoom inicial e' 100%")
    roda(120, ctrl=True)
    checa_igual(painel.zoom(), 1.25, "Ctrl+roda para cima amplia para o passo seguinte (125%)")
    roda(-120, ctrl=True)
    roda(-120, ctrl=True)
    checa_igual(painel.zoom(), 0.75, "Ctrl+roda para baixo reduz em passos (75%)")
    valor = vb.value()
    roda(-120, ctrl=False)
    checa(vb.value() > valor and painel.zoom() == 0.75,
          "sem Ctrl, a roda rola a pagina e nao muda o zoom")
    for _ in range(12):
        roda(120, ctrl=True)
    checa_igual(painel.zoom(), painel.teto_do_zoom(), "Ctrl+roda nao passa do teto da tela")
    checa(painel.zoom() <= painel.teto_do_zoom(), "contraprova: o teto e' o da tela, nao um numero solto")
    painel.close()


def testar_status_e_controle() -> None:
    secao("barra de status: pagina do caret e porcentagem do zoom")
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal

    janela = JanelaPrincipal(configuracao.padrao())
    janela.show()
    janela.resize(1200, 800)
    drenar_eventos(2)
    janela.painel.setPlainText(TEXTO)
    janela.painel.document().setModified(False)
    drenar_eventos(2)
    total = janela.painel.total_de_paginas()
    checa(total >= 5, f"o texto de teste tem varias paginas ({total})")
    pos = _posicao_da_pagina(janela.painel, 4)
    cur = janela.painel.textCursor()
    cur.setPosition(pos)
    janela.painel.setTextCursor(cur)
    drenar_eventos(2)
    checa_igual(janela._rotulo_pagina.text(), f"Página 5 de {total}",
                "a barra de status mostra a pagina do caret")
    cur.setPosition(0)
    janela.painel.setTextCursor(cur)
    drenar_eventos(2)
    checa_igual(janela._rotulo_pagina.text(), f"Página 1 de {total}",
                "contraprova: voltar ao inicio muda o rotulo para a pagina 1")
    checa(janela._rotulo_palavras.text().startswith("Palavras:"),
          "o rotulo de palavras continua na barra")

    janela.painel.definir_zoom(1.25)
    drenar_eventos(2)
    checa_igual(janela.controle_zoom._rotulo.text(), "125%", "o controle mostra 125%")
    janela.comandos.acao("ampliar").trigger()
    checa_igual(janela.painel.zoom(), 1.5, "Ampliar, pelo comando, vai ao passo seguinte")
    checa_igual(janela.controle_zoom._rotulo.text(), "150%", "o controle acompanha o comando")
    janela.comandos.acao("reduzir").trigger()
    janela.comandos.acao("reduzir").trigger()
    checa_igual(janela.painel.zoom(), 1.0, "Reduzir, pelo comando, desce dois passos")
    checa(janela.controle_zoom._barra.maximum() == round(janela.painel.teto_do_zoom() * 100),
          "o limite da barra de zoom e' o teto da tela")
    janela.painel.document().setModified(False)
    janela.close()


def testar_selecao_por_mouse() -> None:
    secao("clique, shift+clique e arrasto selecionam o texto certo em varias paginas e zooms")
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    painel = _painel()
    alvo = painel.viewport()
    for zoom in (0.25, 1.0, 3.0):
        painel.definir_zoom(zoom)
        for pagina in (1, 5, 9):
            p1 = _posicao_da_pagina(painel, pagina)
            p2 = p1 + 25
            x1, y1 = _tela_da_posicao(painel, p1)
            QTest.mouseClick(alvo, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                             QPoint(round(x1), round(y1)))
            drenar_eventos(1)
            cur = painel.textCursor()
            checa(not cur.hasSelection() and abs(cur.position() - p1) <= 1,
                  f"zoom {int(zoom * 100)}%, pagina {pagina + 1}: clique põe o caret a 1 caractere de {p1}")

            x2, y2 = _tela_da_posicao(painel, p2)
            QTest.mouseClick(alvo, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier,
                             QPoint(round(x2), round(y2)))
            drenar_eventos(1)
            cur = painel.textCursor()
            ini, fim = cur.selectionStart(), cur.selectionEnd()
            checa(abs(ini - p1) <= 1 and abs(fim - p2) <= 1,
                  f"zoom {int(zoom * 100)}%, pagina {pagina + 1}: shift+clique seleciona {p1}..{p2} "
                  f"(obtido {ini}..{fim})")

            # arrasto: pressiona em p1 e solta em p2
            QTest.mousePress(alvo, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                             QPoint(round(x1), round(y1)))
            QTest.mouseMove(alvo, QPoint(round(x2), round(y2)))
            QTest.mouseRelease(alvo, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                               QPoint(round(x2), round(y2)))
            drenar_eventos(1)
            cur = painel.textCursor()
            ini, fim = cur.selectionStart(), cur.selectionEnd()
            checa(abs(ini - p1) <= 1 and abs(fim - p2) <= 1,
                  f"zoom {int(zoom * 100)}%, pagina {pagina + 1}: arrasto seleciona {p1}..{p2} "
                  f"(obtido {ini}..{fim})")

    # contraprova: selecionar 25 caracteres na pagina 2 com um ponto deslocado de 3 linhas
    # da pagina 6 nao pode dar a mesma selecao
    painel.definir_zoom(1.0)
    p1 = _posicao_da_pagina(painel, 1)
    x1, y1 = _tela_da_posicao(painel, p1)
    QTest.mouseClick(alvo, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(round(x1), round(y1) + 400))
    drenar_eventos(1)
    checa(abs(painel.textCursor().position() - p1) > 1,
          "contraprova: um clique deslocado em y nao cai na mesma posicao")
    painel.document().setModified(False)
    painel.close()


def main() -> int:
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    if not usar_fonte_windows(9):
        return pular("Segoe UI nao esta instalada")
    testar_zoom_nao_refaz_layout()
    testar_ctrl_roda()
    testar_status_e_controle()
    testar_selecao_por_mouse()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
