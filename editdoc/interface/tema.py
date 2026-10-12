"""Tema claro, escuro ou o do Windows (M8), pelo esquema de cores do Qt.

`QStyleHints.setColorScheme` (Qt 6.8 em diante) troca a paleta dos estilos que a
seguem (windows11 e fusion no Windows) sem stylesheet. A folha continua branca e o
texto preto: o documento e' papel, como no Word com o tema escuro. Na plataforma
offscreen (testes) o Qt aceita a chamada e nao muda nada; o pedido fica numa
propriedade do aplicativo para quem quiser conferir.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

ESQUEMAS = {"claro": Qt.ColorScheme.Light, "escuro": Qt.ColorScheme.Dark}


def aplicar(nome: str, app: QApplication | None = None) -> str:
    """Aplica o tema ('sistema', 'claro' ou 'escuro'; outro vira 'sistema'). Devolve o aplicado."""
    app = app or QApplication.instance()
    if app is None:
        return "sistema"
    nome = nome if nome in ESQUEMAS else "sistema"
    dicas = app.styleHints()
    try:
        if nome == "sistema":
            dicas.unsetColorScheme()
        else:
            dicas.setColorScheme(ESQUEMAS[nome])
    except AttributeError:  # Qt sem a API (anterior ao 6.8): fica o do sistema
        nome = "sistema"
    app.setProperty("editdoc_tema", nome)
    return nome
