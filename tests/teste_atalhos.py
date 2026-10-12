"""Atalhos de teclado com teclas reais (QTest.keyClick), nunca chamando o metodo direto.

Regra do CLAUDE.md: testar o metodo nao e' testar a tecla. Aqui cada atalho e'
apertado no painel e o efeito e' conferido no documento.
"""

from __future__ import annotations

from ajudantes import (checa, checa_igual, drenar_eventos, pular, preparar_qt,
                       resumir, secao, usar_fonte_windows)

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402

from editdoc import configuracao  # noqa: E402
from editdoc.edicao.estado import ler  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402

CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


def _janela() -> JanelaPrincipal:
    usar_fonte_windows(9)
    janela = JanelaPrincipal(configuracao.padrao())
    janela.show()
    drenar_eventos()
    janela.painel.setFocus()
    return janela


def _selecionar_tudo(painel) -> None:
    cursor = painel.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    painel.setTextCursor(cursor)


def testar_formatacao_por_atalho() -> None:
    secao("formatacao por atalho, com desfazer")
    janela = _janela()
    painel = janela.painel
    QTest.keyClicks(painel, "abc")
    _selecionar_tudo(painel)
    QTest.keyClick(painel, Qt.Key.Key_B, CTRL)
    drenar_eventos()
    checa(ler(painel).negrito, "Ctrl+B deixa a selecao em negrito")
    checa(janela.comandos.acao("negrito").isChecked(), "e a faixa mostra o N marcado")

    QTest.keyClick(painel, Qt.Key.Key_Z, CTRL)
    drenar_eventos()
    checa(not ler(painel).negrito, "Ctrl+Z desfaz o negrito")
    checa_igual(painel.toPlainText(), "abc", "e o texto continua o mesmo")

    _selecionar_tudo(painel)
    QTest.keyClick(painel, Qt.Key.Key_I, CTRL)
    checa(ler(painel).italico, "Ctrl+I deixa em italico")
    QTest.keyClick(painel, Qt.Key.Key_U, CTRL)
    checa(ler(painel).sublinhado, "Ctrl+U sublinha")
    # Fechar com alteracao pendente abriria o dialogo de descarte: um modal
    # trava a suite. O documento e' declarado salvo antes; o fechamento com
    # alteracao esta' em tests/teste_documento.py.
    janela.painel.document().setModified(False)
    janela.close()


def testar_paragrafo_por_atalho() -> None:
    secao("paragrafo por atalho")
    janela = _janela()
    painel = janela.painel
    QTest.keyClicks(painel, "um")
    QTest.keyClick(painel, Qt.Key.Key_Return)
    QTest.keyClicks(painel, "dois")
    _selecionar_tudo(painel)
    QTest.keyClick(painel, Qt.Key.Key_E, CTRL)
    checa_igual(ler(painel).alinhamento, "centro", "Ctrl+E centraliza")
    QTest.keyClick(painel, Qt.Key.Key_J, CTRL)
    checa_igual(ler(painel).alinhamento, "justificado", "Ctrl+J justifica")
    QTest.keyClick(painel, Qt.Key.Key_L, CTRL)
    checa_igual(ler(painel).alinhamento, "esquerda", "Ctrl+L alinha a esquerda")
    QTest.keyClick(painel, Qt.Key.Key_5, CTRL)
    checa_igual(ler(painel).espacamento, 150, "Ctrl+5 espacamento 1,5")
    QTest.keyClick(painel, Qt.Key.Key_2, CTRL)
    checa_igual(ler(painel).espacamento, 200, "Ctrl+2 espacamento 2,0")
    QTest.keyClick(painel, Qt.Key.Key_1, CTRL)
    checa_igual(ler(painel).espacamento, 100, "Ctrl+1 espacamento simples")
    QTest.keyClick(painel, Qt.Key.Key_L, CTRL | SHIFT)
    checa(ler(painel).marcadores, "Ctrl+Shift+L liga marcadores")
    # Fechar com alteracao pendente abriria o dialogo de descarte: um modal
    # trava a suite. O documento e' declarado salvo antes; o fechamento com
    # alteracao esta' em tests/teste_documento.py.
    janela.painel.document().setModified(False)
    janela.close()


def testar_busca_por_atalho() -> None:
    secao("Ctrl+F e Ctrl+H abrem a barra certa")
    janela = _janela()
    painel = janela.painel
    QTest.keyClick(painel, Qt.Key.Key_F, CTRL)
    drenar_eventos()
    checa(janela.barra_busca.isVisible(), "Ctrl+F mostra a barra de localizar")
    checa(not janela.barra_busca._substituto.isVisible(),
          "Ctrl+F nao mostra o campo de substituir")
    painel.setFocus()
    QTest.keyClick(painel, Qt.Key.Key_H, CTRL)
    drenar_eventos()
    checa(janela.barra_busca._substituto.isVisible(), "Ctrl+H mostra o campo de substituir")
    # Fechar com alteracao pendente abriria o dialogo de descarte: um modal
    # trava a suite. O documento e' declarado salvo antes; o fechamento com
    # alteracao esta' em tests/teste_documento.py.
    janela.painel.document().setModified(False)
    janela.close()


def testar_teclas_comuns() -> None:
    secao("teclas comuns continuam funcionando e nao disparam comando")
    janela = _janela()
    painel = janela.painel
    QTest.keyClicks(painel, "um dois")
    checa_igual(painel.toPlainText(), "um dois", "digitar ASCII entra no documento")
    QTest.keyClick(painel, Qt.Key.Key_Backspace)
    checa_igual(painel.toPlainText(), "um doi", "Backspace apaga")
    QTest.keyClick(painel, Qt.Key.Key_Q, CTRL)
    checa(not ler(painel).negrito and painel.toPlainText() == "um doi",
          "contraprova: Ctrl+Q, sem atalho, nao muda nada")
    # Fechar com alteracao pendente abriria o dialogo de descarte: um modal
    # trava a suite. O documento e' declarado salvo antes; o fechamento com
    # alteracao esta' em tests/teste_documento.py.
    janela.painel.document().setModified(False)
    janela.close()


def main() -> int:
    testar_formatacao_por_atalho()
    testar_paragrafo_por_atalho()
    testar_busca_por_atalho()
    testar_teclas_comuns()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
