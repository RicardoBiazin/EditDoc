"""Confere que o executavel ABRE a janela de verdade.

    .venv\\Scripts\\python.exe ferramentas\\fumaca_exe.py [caminho\\EditDoc.exe]

O --autoverificacao prova que os modulos estao dentro do .exe. Nao prova que o
programa sobe: um problema de DLL, de tema ou de manifesto so' aparece com o
processo rodando. Esta fumaca sobe o .exe com %APPDATA% isolado, espera uma
janela com titulo "EditDoc", e falha se o processo morrer antes, se a janela
nao aparecer em 30 s, ou se o log registrou excecao nao tratada.

So' a API do Windows via ctypes, sem Qt e sem pywin32, de proposito: a
ferramenta precisa funcionar mesmo com o venv do programa quebrado.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent
LIMITE_S = 30

user32 = ctypes.WinDLL("user32", use_last_error=True)
TipoJanela = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.EnumWindows.argtypes = [TipoJanela, wt.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]


def titulos_visiveis(pid: int) -> list[str]:
    achados: list[str] = []

    def visitar(hwnd, _lparam) -> bool:
        dono = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(dono))
        if dono.value == pid and user32.IsWindowVisible(hwnd):
            tamanho = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(tamanho + 1)
            user32.GetWindowTextW(hwnd, buffer, tamanho + 1)
            achados.append(buffer.value)
        return True

    user32.EnumWindows(TipoJanela(visitar), 0)
    return achados


def falha(mensagem: str) -> int:
    print("FALHA:", mensagem)
    return 1


def main(argv: list[str]) -> int:
    exe = pathlib.Path(argv[0]) if argv else RAIZ / "dist" / "EditDoc" / "EditDoc.exe"
    if not exe.is_file():
        return falha(f"{exe} nao existe")

    appdata = pathlib.Path(tempfile.mkdtemp(prefix="editdoc-fumaca-"))
    # %LOCALAPPDATA% tambem (M8): a abertura procura copias de recuperacao, e a fumaca nao
    # pode criar a pasta nem oferecer as copias do usuario.
    processo = subprocess.Popen([str(exe)], env=dict(
        os.environ, APPDATA=str(appdata), LOCALAPPDATA=str(appdata / "local"),
        EDITDOC_RECUPERACAO=str(appdata / "local" / "EditDoc" / "Recuperacao")))
    try:
        limite = time.monotonic() + LIMITE_S
        titulos: list[str] = []
        while True:
            if processo.poll() is not None:
                return falha(f"o processo terminou com codigo {processo.returncode} "
                             "antes de abrir a janela")
            titulos = titulos_visiveis(processo.pid)
            # "EditDoc" em qualquer posicao: o titulo da janela principal e'
            # "Documento em branco - EditDoc <versao>", nao so' "EditDoc ...".
            if any("EditDoc" in t for t in titulos):
                break
            if time.monotonic() > limite:
                return falha(f"nenhuma janela com 'EditDoc' no titulo apareceu em "
                             f"{LIMITE_S} s; titulos vistos: {titulos or 'nenhum'}")
            time.sleep(0.5)

        time.sleep(1.0)  # deixa o programa terminar de montar a tela
        if processo.poll() is not None:
            return falha("o processo morreu depois de abrir a janela "
                         f"(codigo {processo.returncode})")

        log = appdata / "EditDoc" / "editdoc.log"
        if log.is_file():
            texto = log.read_text(encoding="utf-8", errors="replace")
            if "EXCECAO NAO TRATADA" in texto:
                return falha("o log registrou excecao nao tratada:\n" + texto[-2000:])

        print("OK: a janela abriu:", ", ".join(titulos))
        return 0
    finally:
        if processo.poll() is None:
            processo.terminate()
            try:
                processo.wait(10)
            except subprocess.TimeoutExpired:
                processo.kill()
        shutil.rmtree(appdata, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
