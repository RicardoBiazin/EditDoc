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
    ("teste_modelo.py",
     "contagem de palavras e unidades, sem Qt"),
    ("teste_formatacao.py",
     "formatacao, listas e alinhamento: um passo de desfazer por comando"),
    ("teste_busca.py",
     "localizar e substituir: ida, volta, palavra inteira e sem loop"),
    ("teste_faixa.py",
     "faixa: recolhimento de 1920 a 820 px e estado que acompanha o cursor"),
    ("teste_atalhos.py",
     "atalhos de teclado com teclas reais, nunca chamando o metodo"),
    ("teste_janela.py",
     "janela principal, contagem de palavras e autoverificacao do programa"),
    ("teste_idioma.py",
     "portugues do Brasil nos dialogos padrao do Qt"),
    ("teste_higiene.py",
     "sem eval/exec/pickle/shell=True; dependencias fixas; licenca"),
    ("teste_empacotamento.py",
     "build em cinco etapas; .spec aponta para o que existe"),
    ("teste_cli.py",
     "linha de comando: dispositivos do Windows recusados"),
    ("teste_instancia_unica.py",
     "instancia unica: a segunda entrega o caminho, a primeira recebe o sinal"),
    ("teste_gravacao.py",
     "gravacao atomica: falha injetada deixa o original intacto"),
    ("teste_associacao.py",
     "associar.ps1: BOM, OpenWithProgids e nenhum UserChoice"),
    ("teste_docx_modelo.py",
     "modelo -> .docx -> modelo: ida e volta, idempotencia e contraprova"),
    ("teste_docx_oraculo.py",
     "python-docx como oraculo de leitura: texto, formato, paragrafo e listas"),
    ("teste_docx_ordem.py",
     "ordem de pPr e rPr e xml:space, com sabotagens"),
    ("teste_docx_pacote.py",
     "integridade OPC: relacoes, tipos de conteudo e partes orfas"),
    ("teste_docx_qt.py",
     "ponte QTextDocument: ida e volta, sublinhado, listas e quebra de linha"),
    ("teste_seguranca.py",
     "arquivos hostis viram ErroDocx com codigo, em menos de 2 s"),
    ("teste_documento.py",
     "janelas: abrir, editar, salvar, perda, falha de gravacao, recentes"),
    ("teste_paginas.py",
     "pagina, zoom e mapa folha-tela sem Qt; layout com Segoe UI: fronteiras, paginas estaveis, hit-test"),
    ("teste_folhas.py",
     "folhas em pixels: retangulo, margem sem tinta, cache igual ao quadro novo"),
    ("teste_regua.py",
     "regua: margens e recuos; arrastar um marcador e' um passo de desfazer"),
    ("teste_zoom.py",
     "zoom sem relayout, Ctrl+roda, barra de status e selecao por mouse em varias paginas"),
    ("teste_quebras.py",
     "Ctrl+Enter: quebra no .docx e na tela; sem aviso quando a quebra e' representada"),
    ("teste_layout.py",
     "papel, orientacao e margens no sectPr e na janela; PAGINA so' com mais de uma secao"),
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
