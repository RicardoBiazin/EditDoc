"""Janela manual do Spike A, para o teste MANUAL C5 (teclas mortas ABNT2, AltGr, Win+.).

Uso: .venv\\Scripts\\python.exe spikes\\pagina\\demo_manual.py
Nao e rodado pela suite. Abre uma janela real e espera o usuario digitar.
Nao importa testes_pagina: essa importacao forca o plugin offscreen.
"""
import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QTextCursor

from cabecalho_rodape import CabecalhoRodape
from layout_paginado import LayoutPaginado
from vista import VistaPaginas


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    lay = LayoutPaginado()
    cur = QTextCursor(lay.doc)
    for i in range(80):
        cur.insertText(f"Paragrafo {i}: digite aqui com o teclado ABNT2 e teste os acentos. " * 3)
        cur.insertBlock()
    vista = VistaPaginas(lay, CabecalhoRodape(lay))
    vista.setWindowTitle("Spike A: teste manual C5")
    vista.resize(1100, 800)
    vista.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
