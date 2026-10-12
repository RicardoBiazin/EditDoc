"""Localizar e substituir sobre o documento: ida, volta, palavra inteira e um passo de desfazer."""

from __future__ import annotations

import time

from ajudantes import preparar_qt, checa, checa_igual, pular, resumir, secao

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtGui import QTextCursor  # noqa: E402

from editdoc.edicao import busca  # noqa: E402
from editdoc.edicao.busca import Opcoes  # noqa: E402
from editdoc.interface.painel_documento import PainelDocumento  # noqa: E402


def novo(texto: str) -> PainelDocumento:
    painel = PainelDocumento("Calibri", 11)
    painel.setPlainText(texto)
    painel.document().clearUndoRedoStacks()
    painel.moveCursor(QTextCursor.MoveOperation.Start)
    return painel


def inicio_da_selecao(painel: PainelDocumento) -> int:
    return painel.textCursor().selectionStart()


def testar_localizar() -> None:
    secao("localizar: proxima, volta ao inicio e termo ausente")
    painel = novo("gato rato gato")
    checa(busca.localizar(painel, "gato", Opcoes()), "acha a primeira ocorrencia")
    checa_igual(inicio_da_selecao(painel), 0, "primeira ocorrencia na posicao 0")
    busca.localizar(painel, "gato", Opcoes())
    checa_igual(inicio_da_selecao(painel), 10, "a proxima e' a da posicao 10")
    busca.localizar(painel, "gato", Opcoes())
    checa_igual(inicio_da_selecao(painel), 0, "passou do fim: volta ao inicio")
    checa(not busca.localizar(painel, "zebra", Opcoes()), "termo ausente devolve False")
    checa(not busca.localizar(painel, "", Opcoes()), "termo vazio devolve False")


def testar_opcoes() -> None:
    secao("opcoes: maiusculas, palavra inteira e busca para tras")
    painel = novo("Gato gato GATO")
    busca.localizar(painel, "gato", Opcoes(maiusculas=True))
    checa_igual(inicio_da_selecao(painel), 5,
                "com maiusculas, so' acha 'gato' minusculo")
    painel = novo("Gato gato GATO")
    busca.localizar(painel, "gato", Opcoes())
    checa_igual(inicio_da_selecao(painel), 0, "sem a opcao, ignora maiusculas")

    painel = novo("gato gatos gato")
    busca.localizar(painel, "gato", Opcoes(palavra_inteira=True))
    checa_igual(inicio_da_selecao(painel), 0, "palavra inteira acha a primeira")
    busca.localizar(painel, "gato", Opcoes(palavra_inteira=True))
    checa_igual(inicio_da_selecao(painel), 11,
                "palavra inteira pula 'gatos' (contraprova: sem a opcao, pararia em 5)")

    painel = novo("gato rato gato")
    painel.moveCursor(QTextCursor.MoveOperation.End)
    busca.localizar(painel, "gato", Opcoes(), para_tras=True)
    checa_igual(inicio_da_selecao(painel), 10, "para tras comeca pela ultima")


def testar_substituir_atual() -> None:
    secao("substituir: troca a selecao e segue para a proxima")
    painel = novo("gato gato gato")
    busca.localizar(painel, "gato", Opcoes())
    busca.substituir_atual(painel, "gato", "cão", Opcoes())
    checa_igual(painel.toPlainText(), "cão gato gato",
                "substituir troca so' a ocorrencia selecionada")
    checa(painel.textCursor().hasSelection(), "depois de trocar, a proxima fica selecionada")


def testar_substituir_todas() -> None:
    secao("substituir tudo: contagem, texto e UM passo de desfazer")
    painel = novo("gato gato gato")
    trocas = busca.substituir_todas(painel, "gato", "cão", Opcoes())
    checa_igual(trocas, 3, "conta as tres trocas")
    checa_igual(painel.toPlainText(), "cão cão cão", "texto trocado")
    # Um desfazer tem de devolver as tres trocas. Contraprova: se cada troca
    # fosse um passo, um desfazer deixaria duas delas.
    painel.undo()
    checa_igual(painel.toPlainText(), "gato gato gato",
                "um unico desfazer devolve as tres trocas (substituir tudo e' um passo)")

    painel = novo("a a")
    inicio = time.monotonic()
    trocas = busca.substituir_todas(painel, "a", "aa", Opcoes())
    tempo = time.monotonic() - inicio
    checa_igual(trocas, 2, "substituto que contem o termo nao entra em loop")
    checa_igual(painel.toPlainText(), "aa aa", "o substituto fica como esta")
    checa(tempo < 2.0, f"termina em menos de 2 s (levou {tempo:.3f} s)")

    painel = novo("nada aqui")
    checa_igual(busca.substituir_todas(painel, "zebra", "x", Opcoes()), 0,
                "sem ocorrencias, nao troca nada")


def main() -> int:
    testar_localizar()
    testar_opcoes()
    testar_substituir_atual()
    testar_substituir_todas()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
