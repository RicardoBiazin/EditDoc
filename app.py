"""Ponto de entrada do EditWord.

    python app.py
    python app.py --autoverificacao

--autoverificacao nao mostra janela para o usuario: importa os modulos
obrigatorios, carrega a traducao e o icone, e constroi a janela principal. O
build.bat o roda dentro do .exe antes de entregar; se algo faltou no
empacotamento, aparece aqui. Sai com 0 quando passa e com 1 quando falha.
"""

from __future__ import annotations

import importlib
import sys

from editword import APP, VERSAO, configuracao, idioma, log_interno, recursos

#: O que o executavel precisa ter embutido. Um modulo esquecido no `.spec` some
#: sem erro de empacotamento e so' quebra quando o programa usa essa parte.
OBRIGATORIOS = (
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "lxml.etree",
    "docx",
    "editword.configuracao",
    "editword.idioma",
    "editword.interface.janela_principal",
)

AUMID = "RicardoBiazin.EditWord"


def _identidade_na_barra_de_tarefas() -> None:
    """Sem um AppUserModelID proprio, o Windows pode agrupar o programa sob o
    python.exe e mostrar o icone errado na barra de tarefas."""
    if sys.platform != "win32":
        return
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(AUMID)


def autoverificacao() -> int:
    log = log_interno.obter("autoverificacao")
    falhas: list[str] = []

    for modulo in OBRIGATORIOS:
        try:
            importlib.import_module(modulo)
        except Exception as erro:  # noqa: BLE001 - interessa o motivo, qualquer um
            falhas.append(f"modulo {modulo} nao importa: {erro}")

    if not recursos.caminho("icone.ico").is_file():
        falhas.append("icone.ico nao esta' em editword/recursos")

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    if "qtbase_pt_BR" not in idioma.instalar(app):
        falhas.append("traducao qtbase_pt_BR nao carregou: botoes sairiam em ingles")

    try:
        from editword.interface.janela_principal import JanelaPrincipal
        JanelaPrincipal(configuracao.carregar()).close()
    except Exception as erro:  # noqa: BLE001
        falhas.append(f"janela principal nao constroi: {erro}")

    for falha in falhas:
        log.error("AUTOVERIFICACAO: %s", falha)
    if falhas:
        log.error("autoverificacao FALHOU (%d problema(s))", len(falhas))
        return 1
    log.info("autoverificacao OK: %s %s", APP, VERSAO)
    return 0


def main(argv: list[str]) -> int:
    if "--autoverificacao" in argv:
        return autoverificacao()

    log_interno.configurar()
    log_interno.instalar_captura_de_erros()
    log_interno.registrar_partida(VERSAO)
    _identidade_na_barra_de_tarefas()

    from PySide6.QtWidgets import QApplication

    from editword.interface.janela_principal import JanelaPrincipal

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP)
    app.setApplicationVersion(VERSAO)
    idioma.instalar(app)

    janela = JanelaPrincipal(configuracao.carregar())
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
