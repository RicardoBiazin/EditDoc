"""Utilidades comuns as suites de teste.

Formato de saida, igual ao do TextForgeEdit: o `rodar_todos.py` conta as
ocorrencias de "\\n  OK   " e "\\n  FALHA" na saida de cada suite, entao os
espacos importam.

    checa(cond, "descricao do que foi verificado")

No fim da suite, `resumir()` imprime o total e devolve o codigo de saida.

`preparar_qt()` define QT_QPA_PLATFORM=offscreen ANTES de importar PySide6 e
isola %APPDATA% do processo. Toda suite que usa Qt chama `preparar_qt()` antes
de qualquer import do projeto que arraste Qt.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import pathlib
import shutil
import sys
import tempfile
from typing import Iterator

RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

falhas: list[str] = []
_total = 0

# O console do Windows costuma ser cp1252. Um caractere fora dessa tabela
# derrubaria o runner no meio da suite, sem relatorio nenhum.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(errors="replace")
    except (AttributeError, OSError):
        pass


def checa(condicao: object, mensagem: str) -> bool:
    """Registra uma verificacao. Devolve o booleano, para encadear."""
    global _total
    _total += 1
    ok = bool(condicao)
    print(("  OK   " if ok else "  FALHA") + " " + mensagem)
    if not ok:
        falhas.append(mensagem)
    return ok


def checa_igual(obtido: object, esperado: object, mensagem: str) -> bool:
    """Como `checa`, mas mostra os dois valores quando falha."""
    if obtido == esperado:
        return checa(True, mensagem)
    return checa(False, f"{mensagem}\n         esperado: {esperado!r}"
                        f"\n         obtido:   {obtido!r}")


def checa_levanta(excecao: type[BaseException], funcao, mensagem: str,
                  *args, **kwargs) -> bool:
    try:
        funcao(*args, **kwargs)
    except excecao:
        return checa(True, mensagem)
    except BaseException as exc:  # noqa: BLE001 - o teste quer saber qual foi
        return checa(False, f"{mensagem} (levantou {exc.__class__.__name__})")
    return checa(False, f"{mensagem} (nao levantou nada)")


def secao(titulo: str) -> None:
    print(f"\n[{titulo}]")


def resumir() -> int:
    print()
    if falhas:
        print("FALHAS: %d de %d verificacoes" % (len(falhas), _total))
        for f in falhas:
            print("  - " + f.splitlines()[0])
    else:
        print("TODOS OS TESTES PASSARAM (%d verificacoes)" % _total)
    return 1 if falhas else 0


def isolar_appdata() -> None:
    """Aponta %APPDATA% para uma pasta descartavel, para o processo inteiro.

    Sem isto um teste de configuracao grava no config REAL do usuario, e o
    estrago atravessa processos: outra suite passa a ler a preferencia que esta
    escreveu. Fica aqui, e nao em cada teste, porque toda suite chama isto antes
    de qualquer coisa.
    """
    if os.environ.get("EDITDOC_APPDATA_ISOLADO"):
        return
    pasta = pathlib.Path(tempfile.mkdtemp(prefix="editdoc-appdata-suite-"))
    os.environ["APPDATA"] = str(pasta)
    os.environ["EDITDOC_APPDATA_ISOLADO"] = "1"
    atexit.register(shutil.rmtree, pasta, True)


def preparar_qt() -> bool:
    """Prepara uma QApplication invisivel. False se PySide6 nao esta instalado.

    Uma suite que precisa de Qt e nao o encontra deve imprimir PULADO e sair com
    0, nao falhar: assim o runner continua util numa maquina sem venv montado.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    isolar_appdata()
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return False
    if QApplication.instance() is None:
        QApplication([])
    return True


def pular(motivo: str) -> int:
    print(f"PULADO: {motivo}")
    return 0


def drenar_eventos(rodadas: int = 4) -> None:
    """Processa eventos ate' e inclusive os DeferredDelete, e coleta o lixo.

    `processEvents()` sozinho nao entrega DeferredDelete: o objeto de
    `deleteLater()` continua vivo.
    """
    import gc

    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    for _ in range(rodadas):
        QApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        gc.collect()


@contextlib.contextmanager
def pasta_temporaria(prefixo: str = "editdoc-teste-") -> Iterator[pathlib.Path]:
    """Pasta temporaria, apagada no fim mesmo se o teste estourar."""
    caminho = pathlib.Path(tempfile.mkdtemp(prefix=prefixo))
    try:
        yield caminho
    finally:
        shutil.rmtree(caminho, ignore_errors=True)
