"""Janela principal: titulo, faixa, contagem de palavras e autoverificacao do programa."""

from __future__ import annotations

import subprocess
import sys

from ajudantes import (RAIZ, checa, checa_igual, drenar_eventos, preparar_qt,
                       pular, resumir, secao)

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from editdoc import APP, VERSAO, configuracao  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402


def testar_janela() -> None:
    secao("janela principal")
    cfg = configuracao.padrao()
    cfg["janela_largura"] = 1000
    cfg["janela_altura"] = 700
    janela = JanelaPrincipal(cfg)
    checa_igual(janela.windowTitle(), f"Documento em branco - {APP} {VERSAO}",
                "titulo traz o nome, a versao e o documento")
    checa(not janela.windowIcon().isNull(), "icone da janela carregado do .ico")
    checa_igual((janela.width(), janela.height()), (1000, 700),
                "tamanho vem da configuracao")
    checa(janela.faixa is not None, "a faixa de opcoes existe")
    checa(janela.barra_busca.isHidden(), "a barra de busca comeca escondida")
    janela.close()
    drenar_eventos()


def testar_contagem_de_palavras() -> None:
    secao("barra de status: contagem de palavras")
    janela = JanelaPrincipal(configuracao.padrao())
    janela.show()
    checa_igual(janela._rotulo_palavras.text(), "Palavras: 0", "documento vazio: zero palavras")
    janela.painel.setPlainText("um dois tres")
    janela.atualizar_estatisticas()
    checa_igual(janela._rotulo_palavras.text(), "Palavras: 3", "tres palavras contadas")
    # setPlainText deixa o cursor no inicio: sem mover para o fim, o texto
    # digitado entraria na frente e a contagem nao mudaria.
    janela.painel.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClicks(janela.painel, " quatro")
    QTest.qWait(600)
    checa_igual(janela._rotulo_palavras.text(), "Palavras: 4",
                "depois de digitar e de uma pausa, a contagem atualiza sozinha")
    janela.close()
    drenar_eventos()


def testar_autoverificacao() -> None:
    secao("autoverificacao: o mesmo caminho que o build roda dentro do .exe")
    proc = subprocess.run(
        [sys.executable, str(RAIZ / "app.py"), "--autoverificacao"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, cwd=RAIZ)
    checa_igual(proc.returncode, 0, "app.py --autoverificacao sai com 0")
    if proc.returncode != 0:
        print(proc.stdout[-1500:], proc.stderr[-1500:])


def main() -> int:
    testar_janela()
    testar_contagem_de_palavras()
    testar_autoverificacao()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
