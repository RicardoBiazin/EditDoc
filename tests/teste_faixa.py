"""Faixa de opcoes: recolhimento responsivo de 1920 a 820 px, estado acompanha o cursor."""

from __future__ import annotations

import time

from ajudantes import (checa, checa_igual, drenar_eventos, pular, preparar_qt,
                       resumir, secao, usar_fonte_windows)
from ajudantes import RAIZ  # noqa: F401 - garante o sys.path do projeto

from editdoc.interface.planejamento import recolher_grupos

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtCore import QPoint, QRect  # noqa: E402
from PySide6.QtGui import QTextCharFormat, QTextCursor, QFont  # noqa: E402
from PySide6.QtWidgets import QComboBox, QFontComboBox, QLabel, QToolButton  # noqa: E402

from editdoc import configuracao  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402

LARGURAS = (1920, 1400, 1200, 1000, 820)


def testar_planejamento() -> None:
    secao("planejamento: quem recolhe e em que ordem (funcao pura)")
    exp = [100, 100, 100, 100]
    rec = [30, 30, 30, 30]
    ordem = [0, 1, 2, 3]
    checa_igual(recolher_grupos(exp, rec, ordem, 400), [False, False, False, False],
                "tudo cabe: nada recolhe")
    checa_igual(recolher_grupos(exp, rec, ordem, 350), [True, False, False, False],
                "recolhe so' o primeiro da ordem quando isso basta")
    checa_igual(recolher_grupos(exp, rec, ordem, 200), [True, True, True, False],
                "recolhe na ordem ate caber")
    checa_igual(recolher_grupos(exp, rec, ordem, 10), [True, True, True, True],
                "se nada cabe, tudo recolhe")
    checa_igual(recolher_grupos(exp, rec, [3, 2, 1, 0], 350), [False, False, False, True],
                "a ordem da lista manda, nao o indice")
    checa_igual(recolher_grupos(exp, rec, [2], 200), [False, False, True, False],
                "contraprova: so' recolhe quem esta na ordem")


def _janela() -> JanelaPrincipal:
    usar_fonte_windows(9)
    janela = JanelaPrincipal(configuracao.padrao())
    janela.show()
    drenar_eventos()
    return janela


def _cortados(janela: JanelaPrincipal) -> list[str]:
    """Widgets visiveis cortados. Lista vazia = nada cortado.

    Cortado quer dizer duas coisas: passa da borda da faixa, ou foi espremido
    abaixo do minimo que precisa para mostrar o proprio texto. O Qt espreme os
    botoes em vez de empurra-los para fora, entao olhar so' a borda deixaria
    passar um botao com o texto cortado.
    """
    faixa = janela.faixa
    largura = faixa.width()
    saida = []
    for tipo in (QToolButton, QComboBox, QFontComboBox, QLabel):
        for widget in faixa.findChildren(tipo):
            if not widget.isVisibleTo(faixa):
                continue
            inicio = widget.mapTo(faixa, QPoint(0, 0))
            caixa = QRect(inicio, widget.size())
            fora = caixa.left() < 0 or caixa.right() > largura
            espremido = widget.width() < widget.minimumSizeHint().width()
            if fora or espremido:
                rotulo = widget.text() if isinstance(widget, (QToolButton, QLabel)) else ""
                saida.append(f"{type(widget).__name__}:{rotulo or widget.objectName()}")
    return saida


def testar_recolhimento() -> None:
    secao("recolhimento real: 1920 a 820 px, nada cortado")
    janela = _janela()
    faixa = janela.faixa
    minimo = faixa.minimumWidth()
    checa(minimo <= 820, f"a faixa cabe em 820 px (minimo {minimo} px)")

    resultados = {}
    for largura in LARGURAS:
        janela.resize(largura, 800)
        drenar_eventos()
        resultados[largura] = faixa.recolhidos()
        cortados = _cortados(janela)
        checa(not cortados,
              f"em {largura} px nenhum botao fica cortado (cortados: {cortados})")

    checa_igual(resultados[1920], [False, False, False, False],
                "em 1920 px todos os grupos estao expandidos")
    checa(any(resultados[820]), "em 820 px pelo menos um grupo esta recolhido")
    checa(not resultados[820][1],
          "a fonte e o tamanho nunca recolhem (grupo de fonte continua expandido em 820 px)")
    checa(resultados[1400][3] and not resultados[1400][2],
          "em 1400 px so' Edicao recolhe: ordem de prioridade")

    # Contraprova: a janela nao encolhe abaixo do minimo dos filhos, entao a
    # faixa e' forcada a 420 px diretamente. O detector tem de acusar corte.
    faixa.setFixedWidth(420)
    drenar_eventos()
    checa(bool(_cortados(janela)),
          "contraprova: faixa de 420 px (abaixo do minimo) e' acusada como cortada")
    faixa.setMinimumWidth(minimo)
    faixa.setMaximumWidth(16777215)
    drenar_eventos()
    checa(not _cortados(janela), "de volta ao tamanho normal, nada mais aparece cortado")
    # Fechar com alteracao pendente abriria o dialogo de descarte: um modal
    # trava a suite. O documento e' declarado salvo antes; o fechamento com
    # alteracao esta' em tests/teste_documento.py.
    janela.painel.document().setModified(False)
    janela.close()


def testar_estado_acompanha_cursor() -> None:
    secao("estado da faixa acompanha o cursor")
    janela = _janela()
    painel = janela.painel
    painel.clear()
    cursor = painel.textCursor()
    fmt_normal = QTextCharFormat()
    fmt_negrito = QTextCharFormat()
    fmt_negrito.setFontWeight(QFont.Weight.Bold)
    cursor.insertText("normal ", fmt_normal)
    cursor.insertText("negrito", fmt_negrito)
    drenar_eventos()

    acao = janela.comandos.acao("negrito")
    cursor = painel.textCursor()
    cursor.setPosition(3)
    painel.setTextCursor(cursor)
    drenar_eventos()
    checa_igual(acao.isChecked(), False, "dentro do texto normal, N nao fica marcado")

    cursor.setPosition(10)
    painel.setTextCursor(cursor)
    drenar_eventos()
    checa_igual(acao.isChecked(), True, "dentro do negrito, N fica marcado")

    cursor.setPosition(3)
    painel.setTextCursor(cursor)
    drenar_eventos()
    checa_igual(acao.isChecked(), False, "voltando ao normal, N desmarca")

    checa(janela.comandos.acao("desfazer").isEnabled(), "desfazer habilitado depois de editar")
    painel.document().clearUndoRedoStacks()
    drenar_eventos()
    checa(not janela.comandos.acao("desfazer").isEnabled(),
          "desfazer desabilita quando nao ha o que desfazer")
    # Fechar com alteracao pendente abriria o dialogo de descarte: um modal
    # trava a suite. O documento e' declarado salvo antes; o fechamento com
    # alteracao esta' em tests/teste_documento.py.
    janela.painel.document().setModified(False)
    janela.close()


def testar_custo_da_atualizacao() -> None:
    secao("custo da atualizacao da faixa")
    janela = _janela()
    painel = janela.painel
    painel.setPlainText("texto de teste " * 2000)
    atualizador = janela.atualizador
    tempos = []
    for i in range(1000):
        cursor = painel.textCursor()
        cursor.setPosition((i * 37) % painel.document().characterCount())
        painel.setTextCursor(cursor)
        inicio = time.perf_counter()
        atualizador.atualizar()
        tempos.append(time.perf_counter() - inicio)
    media_ms = sum(tempos) / len(tempos) * 1000
    print(f"  (media de atualizacao: {media_ms:.3f} ms em 1000 movimentos)")
    checa(media_ms < 1.0, f"atualizar a faixa leva menos de 1 ms em media ({media_ms:.3f} ms)")
    # Fechar com alteracao pendente abriria o dialogo de descarte: um modal
    # trava a suite. O documento e' declarado salvo antes; o fechamento com
    # alteracao esta' em tests/teste_documento.py.
    janela.painel.document().setModified(False)
    janela.close()


def main() -> int:
    testar_planejamento()
    testar_recolhimento()
    testar_estado_acompanha_cursor()
    testar_custo_da_atualizacao()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
