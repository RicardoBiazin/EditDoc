"""Ponto de entrada do EditDoc.

    python app.py
    python app.py arquivo.docx outro.docx
    python app.py --autoverificacao

Com arquivos na linha de comando, a instancia que ja esta aberta recebe os
caminhos e esta' sai; se nao ha nenhuma aberta, o programa abre uma janela por
arquivo.

--autoverificacao nao mostra janela para o usuario: importa os modulos
obrigatorios, carrega a traducao, faz uma ida-e-volta de .docx e constroi a janela
principal. O build.bat o roda dentro do .exe antes de entregar; se algo faltou no
empacotamento, aparece aqui. Sai com 0 quando passa e com 1 quando falha.
"""

from __future__ import annotations

import importlib
import os
import sys

from editdoc import APP, VERSAO, configuracao, idioma, log_interno, recursos

#: O que o executavel precisa ter embutido. Um modulo esquecido no `.spec` some
#: sem erro de empacotamento e so' quebra quando o programa usa essa parte.
OBRIGATORIOS = (
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
    "lxml.etree",
    "editdoc.configuracao",
    "editdoc.idioma",
    "editdoc.cli",
    "editdoc.instancia_unica",
    "editdoc.armazenamento.gravacao",
    "editdoc.formato_docx.leitor",
    "editdoc.formato_docx.escritor",
    "editdoc.formato_docx.conferencia",
    "editdoc.ponte_qt.para_qt",
    "editdoc.ponte_qt.de_qt",
    "editdoc.interface.janela_principal",
    "editdoc.interface.gerente",
)

AUMID = "RicardoBiazin.EditDoc"


def _identidade_na_barra_de_tarefas() -> None:
    """Sem um AppUserModelID proprio, o Windows pode agrupar o programa sob o
    python.exe e mostrar o icone errado na barra de tarefas."""
    if sys.platform != "win32":
        return
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(AUMID)


def _ida_e_volta_docx(falhas: list[str]) -> None:
    """Escreve um .docx e le de volta, sem Qt: pega lxml ou zipfile ausentes no .exe."""
    from editdoc.formato_docx.escritor import escrever
    from editdoc.formato_docx.leitor import ler
    from editdoc.modelo.documento import Documento, Paragrafo, Run

    try:
        ida = Documento(paragrafos=[Paragrafo(runs=[Run("autoverificacao", negrito=True)])])
        lido, _avisos = ler(escrever(ida))
        if [p.runs[0].texto for p in lido.paragrafos if p.runs] != ["autoverificacao"]:
            falhas.append("ida-e-volta do .docx nao confere")
    except Exception as erro:  # noqa: BLE001 - interessa o motivo, qualquer um
        falhas.append(f"ida-e-volta do .docx falhou: {erro}")


def autoverificacao() -> int:
    log = log_interno.obter("autoverificacao")
    falhas: list[str] = []

    for modulo in OBRIGATORIOS:
        try:
            importlib.import_module(modulo)
        except Exception as erro:  # noqa: BLE001 - interessa o motivo, qualquer um
            falhas.append(f"modulo {modulo} nao importa: {erro}")

    if not recursos.caminho("icone.ico").is_file():
        falhas.append("icone.ico nao esta' em editdoc/recursos")

    _ida_e_volta_docx(falhas)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    if "qtbase_pt_BR" not in idioma.instalar(app):
        falhas.append("traducao qtbase_pt_BR nao carregou: botoes sairiam em ingles")

    try:
        from editdoc.interface.janela_principal import JanelaPrincipal
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

    from editdoc import cli
    pedido = cli.analisar(argv)
    if pedido.ajuda:
        print(cli.AJUDA)
        return 0

    log_interno.configurar()
    log_interno.instalar_captura_de_erros()
    log_interno.registrar_partida(VERSAO)
    _identidade_na_barra_de_tarefas()
    log = log_interno.obter("app")
    for argumento, motivo in pedido.recusados:
        log.warning("argumento recusado: %r (%s)", argumento, motivo)

    from PySide6.QtWidgets import QApplication

    from editdoc import instancia_unica
    from editdoc.interface.gerente import GerenteDeJanelas

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP)
    app.setApplicationVersion(VERSAO)
    idioma.instalar(app)

    caminhos = [os.path.abspath(a) for a in pedido.arquivos]
    pedido_para_outra = {"arquivos": caminhos} if caminhos else {"novo": True}
    if instancia_unica.entregar(pedido_para_outra):
        log.info("pedido entregue a uma instancia ja aberta: saindo")
        return 0

    cfg = configuracao.carregar()
    gerente = GerenteDeJanelas(cfg, app)
    servidor = instancia_unica.Servidor(app)
    servidor.pedido_recebido.connect(gerente.receber_pedido)
    if not servidor.escutar():
        log.warning("outra instancia tem o canal: esta abre como janela comum")

    for caminho in caminhos:
        gerente.abrir(caminho)
    if not gerente.janelas():
        gerente.novo()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
