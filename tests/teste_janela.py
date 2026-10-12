"""Janela principal: monta, tem titulo e icone, e o programa passa na autoverificacao."""

from __future__ import annotations

import subprocess
import sys

from ajudantes import (RAIZ, checa, checa_igual, drenar_eventos, preparar_qt,
                       pular, resumir, secao)

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from editdoc import APP, VERSAO, configuracao  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402


def testar_janela() -> None:
    secao("janela principal")
    cfg = configuracao.padrao()
    cfg["janela_largura"] = 1000
    cfg["janela_altura"] = 700
    janela = JanelaPrincipal(cfg)
    checa_igual(janela.windowTitle(), f"{APP} {VERSAO}",
                "titulo traz o nome e a versao")
    checa(not janela.windowIcon().isNull(), "icone da janela carregado do .ico")
    checa_igual((janela.width(), janela.height()), (1000, 700),
                "tamanho vem da configuracao")
    checa(janela.centralWidget() is not None, "tem area central")
    checa(janela.statusBar() is not None, "tem barra de status")
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
    testar_autoverificacao()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
