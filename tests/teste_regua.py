"""Regua: marca as margens e os recuos do paragrafo; arrastar um marcador e' um passo de desfazer.

Os arrastos sao feitos com o mouse de verdade (QTest.mousePress, mouseMove, mouseRelease) na
regua. Cada arrasto tem uma contraprova: um clique longe dos marcadores nao pode mudar nada.
"""

from __future__ import annotations

from ajudantes import checa, checa_igual, drenar_eventos, pular, preparar_qt, resumir, secao, usar_fonte_windows

QT = preparar_qt()

from editdoc.modelo.pagina import TWIPS_POR_CM  # noqa: E402

TEXTO = "Primeiro paragrafo com texto suficiente para a regua.\nSegundo paragrafo curto."


def _painel():
    from PySide6.QtGui import QTextCursor

    from editdoc.interface.painel_documento import PainelDocumento

    painel = PainelDocumento("Segoe UI", 11)
    painel.resize(1000, 700)
    painel.show()
    drenar_eventos(2)
    painel.setPlainText(TEXTO)
    painel.moveCursor(QTextCursor.MoveOperation.Start)
    painel.document().clearUndoRedoStacks()
    painel.document().setModified(False)
    return painel


def _branco(cor: int) -> bool:
    return (cor & 0xFFFFFF) == 0xFFFFFF


def _cinza(cor: int) -> bool:
    c = cor & 0xFFFFFF
    return c != 0xFFFFFF and (c >> 16) > 0x80


def testar_marcas() -> None:
    secao("regua: margens e recuos aparecem nas posicoes certas")
    from editdoc.interface.regua import Regua

    painel = _painel()
    regua = Regua(painel)
    regua.resize(painel.width(), 22)
    regua.show()
    drenar_eventos(2)
    cfg = painel.configuracao_pagina()
    x0 = regua._x_de_tw(0)
    x1 = regua._x_de_tw(cfg.corpo_largura_tw())
    checa(x1 > x0 > 0, "a area do corpo tem largura positiva e comeca depois de zero")
    img = regua.grab().toImage()
    k = img.devicePixelRatio()  # a captura vem em pixels de dispositivo
    meio_y = round(11 * k)
    antes, depois = round(x0 * k) - 2, round(x0 * k) + 2
    checa(_cinza(img.pixel(antes, meio_y)) and _branco(img.pixel(depois, meio_y)),
          "a margem esquerda aparece cinza na regua, o corpo branco")
    checa(_cinza(img.pixel(round(x1 * k) + 2, meio_y)), "a margem direita aparece cinza na regua")

    checa_igual(painel.recuos_do_paragrafo(), (0, 0), "paragrafo sem recuo: marcadores na margem")
    painel.definir_recuos_do_paragrafo(1080, 0)
    checa(abs(regua._x_de_tw(1080) - (x0 + 1080 * painel.mapa().escala)) < 1e-6,
          "recuo de 1080 twips: o marcador vai para 1080 twips a partir da margem")
    checa_igual(painel.recuos_do_paragrafo(), (1080, 0), "o painel guarda o recuo pedido")
    painel.undo()
    checa_igual(painel.recuos_do_paragrafo(), (0, 0),
                "contraprova: desfazer o recuo devolve o marcador a margem")
    regua.close()
    painel.close()


def _arrastar(regua, x_inicio: int, y: int, x_fim: int) -> None:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    QTest.mousePress(regua, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(x_inicio, y))
    QTest.mouseMove(regua, QPoint(x_fim, y))
    QTest.mouseRelease(regua, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       QPoint(x_fim, y))
    drenar_eventos(1)


def testar_arrasto() -> None:
    secao("arrastar os marcadores muda o recuo, em um passo de desfazer")
    from editdoc.interface.regua import Regua

    painel = _painel()
    regua = Regua(painel)
    regua.resize(painel.width(), 22)
    regua.show()
    drenar_eventos(2)
    x0 = regua._x_do_corpo()
    passo = painel.mapa().escala
    um_cm_px = TWIPS_POR_CM * passo

    # marcador de baixo (recuo esquerdo): da margem para 2 cm
    _arrastar(regua, round(x0), 17, round(x0 + 2 * um_cm_px))
    checa_igual(painel.recuos_do_paragrafo(), (1170, 0),
                "arrastar o marcador de baixo ate 2 cm: recuo de 1170 twips (passo de 90)")
    checa_igual(painel.toPlainText(), TEXTO, "o texto nao muda ao mudar o recuo")
    painel.undo()
    checa_igual(painel.recuos_do_paragrafo(), (0, 0),
                "um desfazer devolve o recuo inteiro")
    checa_igual(painel.toPlainText(), TEXTO, "o desfazer deixa o texto como estava")

    # marcador de cima (primeira linha): so' o recuo da primeira linha muda
    _arrastar(regua, round(x0), 3, round(x0 + 1 * um_cm_px))
    checa_igual(painel.recuos_do_paragrafo(), (0, 540),
                "arrastar o marcador de cima ate 1 cm: so' a primeira linha recua (540 twips)")
    painel.undo()
    checa_igual(painel.recuos_do_paragrafo(), (0, 0), "um desfazer tambem devolve a primeira linha")

    # contraprova: clique longe dos marcadores nao muda nada
    _arrastar(regua, round(x0 + 300), 17, round(x0 + 500))
    checa_igual(painel.recuos_do_paragrafo(), (0, 0),
                "contraprova: arrasto longe dos marcadores nao muda o recuo")
    checa(not painel.document().isModified(),
          "contraprova: nada mudou, o documento continua limpo")
    regua.close()
    painel.close()


def testar_margens_na_regua() -> None:
    secao("margens novas aparecem na regua")
    from editdoc.modelo.pagina import Pagina

    painel = _painel()
    from editdoc.interface.regua import Regua

    regua = Regua(painel)
    regua.resize(painel.width(), 22)
    regua.show()
    drenar_eventos(2)
    antes = regua._x_do_corpo()
    painel.definir_configuracao_pagina(Pagina().com_margens(720, 720, 720, 720))
    drenar_eventos(2)
    depois = regua._x_do_corpo()
    esperado = (1440 - 720) * painel.mapa().escala
    checa(abs((antes - depois) - esperado) < 1e-6,
          "margem estreita: o corpo da regua anda 720 twips para a esquerda")
    regua.close()
    painel.close()


def main() -> int:
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    if not usar_fonte_windows(9):
        return pular("Segoe UI nao esta instalada")
    testar_marcas()
    testar_arrasto()
    testar_margens_na_regua()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
