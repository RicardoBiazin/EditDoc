"""Roda todas as suites e resume o resultado.

    .venv\\Scripts\\python.exe tests\\rodar_todos.py

Sem pytest, de proposito: cada suite roda num processo separado, entao um
travamento de Qt numa suite nao leva as outras junto.
"""

from __future__ import annotations

import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

#: Teto por suite. Um dialogo modal aberto sem ninguem para clicar bloqueia
#: para sempre; sem o limite a rodada ficaria pendurada em vez de apontar a suite.
LIMITE_POR_SUITE_S = 180

SUITES = [
    ("teste_base.py",
     "versao, configuracao, log e icone"),
    ("teste_janela.py",
     "janela principal e autoverificacao do programa"),
    ("teste_idioma.py",
     "portugues do Brasil nos dialogos padrao do Qt"),
    ("teste_higiene.py",
     "sem eval/exec/pickle/shell=True; dependencias fixas; licenca"),
    ("teste_empacotamento.py",
     "build em cinco etapas; .spec aponta para o que existe"),
]


def main() -> int:
    total_ok = total_falhas = 0
    quebradas: list[tuple[str, str]] = []

    ambiente = dict(os.environ)
    ambiente.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Sem isto, print de caractere acentuado quebra no console do Windows.
    ambiente["PYTHONIOENCODING"] = "utf-8"
    ambiente["PYTHONPATH"] = RAIZ + os.pathsep + ambiente.get("PYTHONPATH", "")

    for arquivo, descricao in SUITES:
        caminho = os.path.join(AQUI, arquivo)
        if not os.path.isfile(caminho):
            print("%-24s AUSENTE  %s" % (arquivo, descricao))
            quebradas.append((arquivo, "arquivo de teste nao encontrado"))
            continue
        try:
            proc = subprocess.run([sys.executable, "-u", caminho],
                                  capture_output=True, text=True,
                                  errors="replace", env=ambiente, cwd=RAIZ,
                                  timeout=LIMITE_POR_SUITE_S)
        except subprocess.TimeoutExpired as expirou:
            parcial = (expirou.stdout or "") + (expirou.stderr or "")
            print("%-24s  TRAVOU apos %ds  [PROBLEMA]  %s"
                  % (arquivo, LIMITE_POR_SUITE_S, descricao))
            quebradas.append((arquivo, "A SUITE TRAVOU (dialogo modal?)\n"
                              + parcial))
            continue
        saida = proc.stdout + proc.stderr
        ok = saida.count("\n  OK   ")
        falhas = saida.count("\n  FALHA")
        total_ok += ok
        total_falhas += falhas
        estado = ("pulado" if ("PULADO:" in saida and not ok and not falhas)
                  else ("ok" if proc.returncode == 0 else "PROBLEMA"))
        print("%-24s %3d ok  %d falhas  [%-8s]  %s"
              % (arquivo, ok, falhas, estado, descricao))
        if proc.returncode != 0:
            quebradas.append((arquivo, saida))

    print("-" * 74)
    # Suite com problema tem de aparecer no resumo: um erro de sintaxe num teste
    # faz a suite nao rodar, e um resumo verde sobre zero verificacoes e' mentira.
    # Inclui a suite que falhou (codigo de saida != 0), a que travou e a que
    # nao existe: as tres tem o mesmo efeito no resumo.
    resumo = "TOTAL: %d verificacoes ok, %d falhas" % (total_ok, total_falhas)
    if quebradas:
        resumo += "  +  %d SUITE(S) COM PROBLEMA: %s" % (
            len(quebradas), ", ".join(a for a, _ in quebradas))
    print(resumo)
    for arquivo, saida in quebradas:
        print("\n===== saida de %s =====" % arquivo)
        print(saida[-4000:])
    return 1 if (total_falhas or quebradas) else 0


if __name__ == "__main__":
    sys.exit(main())
