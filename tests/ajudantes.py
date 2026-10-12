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
    # A recuperacao automatica (M8) grava em %LOCALAPPDATA%: tambem vai para a pasta
    # descartavel, e a variavel propria aponta para dentro dela.
    os.environ["LOCALAPPDATA"] = str(pasta / "local")
    os.environ["EDITDOC_RECUPERACAO"] = str(pasta / "local" / "EditDoc" / "Recuperacao")
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
        # No offscreen, sair com algo na area de transferencia derruba o processo no fim
        # (acesso invalido, codigo 139), e o rodar_todos marca a suite como PROBLEMA.
        # Medido no M4; na plataforma windows nao acontece.
        atexit.register(_limpar_area_de_transferencia)
    return True


def _limpar_area_de_transferencia() -> None:
    try:
        from PySide6.QtWidgets import QApplication
        if QApplication.instance() is not None:
            QApplication.clipboard().clear()
    except Exception:  # noqa: BLE001 - fim de processo: nada a fazer
        pass


def pular(motivo: str) -> int:
    print(f"PULADO: {motivo}")
    return 0


def usar_fonte_windows(pontos: float = 9) -> bool:
    """Carrega o Segoe UI e o usa como fonte do aplicativo, como no Windows real.

    O offscreen nao tem fontes e cai num fallback cerca de duas vezes mais
    largo. Medir layout com ele daria numeros que nao valem para o usuario.
    Devolve False se a fonte nao existir, e quem chama decide o que fazer.
    """
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    caminho = pathlib.Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeui.ttf"
    if not caminho.is_file():
        return False
    ident = QFontDatabase.addApplicationFont(str(caminho))
    familias = QFontDatabase.applicationFontFamilies(ident) if ident >= 0 else []
    if not familias:
        return False
    QApplication.instance().setFont(QFont(familias[0], pontos))
    return True


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


def usar_fontes_do_documento() -> list[str]:
    """Carrega Calibri e as variantes de Segoe UI (negrito, italico) para o texto do documento.

    Sem a variante negrito, o Qt simula o negrito pintando o texto duas vezes, e o PDF
    traz cada glifo em dobro ("22" no lugar de "2"). So' as suites de impressao chamam:
    as outras medem larguras com a fonte que ja' tinham.
    """
    from PySide6.QtGui import QFontDatabase

    pasta = pathlib.Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    carregadas: list[str] = []
    for nome in ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf",
                 "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"):
        if (pasta / nome).is_file() and QFontDatabase.addApplicationFont(str(pasta / nome)) >= 0:
            carregadas.append(nome)
    return carregadas
