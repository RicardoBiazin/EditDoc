"""Formatacao sobre o QTextEdit: cada comando muda o que deve, e um desfazer devolve tudo.

Nota sobre o desfazer: availableUndoSteps() conta comandos internos do
QTextDocument (cada bloco e cada troca de formato), nao acoes do usuario. Um
alinhamento em tres paragrafos gera varios. Por isso a checagem e' de
comportamento: um unico desfazer tem de devolver o documento ao estado anterior.
"""

from __future__ import annotations

from ajudantes import preparar_qt, checa, checa_igual, pular, resumir, secao

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QTextCursor, QTextListFormat  # noqa: E402

from editdoc.edicao import formatacao  # noqa: E402
from editdoc.edicao.estado import ler  # noqa: E402
from editdoc.interface.painel_documento import PainelDocumento  # noqa: E402


def novo_painel(texto: str) -> PainelDocumento:
    painel = PainelDocumento("Calibri", 11)
    painel.setPlainText(texto)
    painel.document().clearUndoRedoStacks()
    return painel


def selecionar(painel: PainelDocumento, inicio: int, fim: int) -> None:
    cursor = painel.textCursor()
    cursor.setPosition(inicio)
    cursor.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
    painel.setTextCursor(cursor)


def selecionar_tudo(painel: PainelDocumento) -> None:
    selecionar(painel, 0, len(painel.toPlainText()))


def _blocos(painel: PainelDocumento):
    bloco = painel.document().firstBlock()
    while bloco.isValid():
        yield bloco
        bloco = bloco.next()


def um_passo(painel: PainelDocumento, comando, mensagem: str) -> None:
    """Confere que o comando muda o documento e que UM desfazer devolve tudo.

    A contraprova e' o proprio teste: se o comando nao mudasse nada, o
    'mudou' falha. Se o desfazer nao devolvesse tudo, o 'voltou' falha.
    """
    antes = painel.document().toHtml()
    comando()
    mudou = painel.document().toHtml() != antes
    painel.undo()
    voltou = painel.document().toHtml() == antes
    checa(mudou and voltou, f"{mensagem} (mudou: {mudou}, um desfazer voltou tudo: {voltou})")


def testar_caractere() -> None:
    secao("caractere: negrito, italico, sublinhado, tachado, posicao e tamanho")
    painel = novo_painel("um dois tres")
    selecionar(painel, 3, 7)
    um_passo(painel, lambda: formatacao.alternar_negrito(painel),
             "negrito na selecao e' um passo de desfazer")

    selecionar(painel, 3, 7)
    formatacao.alternar_negrito(painel)
    checa(ler(painel).negrito, "negrito ligado na selecao")
    formatacao.alternar_negrito(painel)
    checa(not ler(painel).negrito, "alternar outra vez desliga (contraprova do alternar)")

    selecionar(painel, 0, 3)
    formatacao.alternar_italico(painel)
    checa(ler(painel).italico, "italico ligado")
    formatacao.alternar_sublinhado(painel)
    checa(ler(painel).sublinhado, "sublinhado ligado")
    formatacao.alternar_tachado(painel)
    checa(ler(painel).tachado, "tachado ligado")

    selecionar(painel, 4, 7)
    formatacao.alternar_subscrito(painel)
    checa(ler(painel).subscrito, "subscrito ligado")
    formatacao.alternar_sobrescrito(painel)
    checa(ler(painel).sobrescrito and not ler(painel).subscrito,
          "sobrescrito troca o subscrito")

    selecionar(painel, 4, 7)
    formatacao.definir_tamanho(painel, 20)
    checa_igual(ler(painel).tamanho, 20.0, "tamanho 20 pt na selecao")
    formatacao.alterar_tamanho(painel, 1)
    checa_igual(ler(painel).tamanho, 21.0, "aumentar o tamanho soma 1 pt")


def testar_limpar() -> None:
    secao("limpar formatacao devolve o padrao do documento")
    painel = novo_painel("negrito e italico")
    selecionar(painel, 0, 8)
    formatacao.alternar_negrito(painel)
    formatacao.alternar_italico(painel)
    formatacao.definir_tamanho(painel, 30)
    um_passo(painel, lambda: formatacao.limpar_formatacao(painel),
             "limpar formatacao e' um passo de desfazer")
    selecionar(painel, 0, 8)
    formatacao.limpar_formatacao(painel)
    estado = ler(painel)
    checa(not (estado.negrito or estado.italico), "limpar tira negrito e italico")
    checa_igual(estado.tamanho, 11.0, "limpar volta ao tamanho padrao do documento")


def testar_alinhamento() -> None:
    secao("alinhamento: tres paragrafos, um desfazer")
    painel = novo_painel("a\nb\nc")
    selecionar_tudo(painel)
    um_passo(painel, lambda: formatacao.alinhar(painel, Qt.AlignmentFlag.AlignHCenter),
             "centralizar tres paragrafos e' um passo de desfazer")
    selecionar_tudo(painel)
    formatacao.alinhar(painel, Qt.AlignmentFlag.AlignHCenter)
    centrados = [b.blockFormat().alignment() & Qt.AlignmentFlag.AlignHCenter
                 for b in _blocos(painel)]
    checa(all(centrados), "os tres paragrafos ficam centralizados")
    checa_igual(ler(painel).alinhamento, "centro", "a faixa le o alinhamento do inicio")


def testar_recuo_e_espacamento() -> None:
    secao("recuo e espacamento de linha")
    painel = novo_painel("a\nb")
    selecionar_tudo(painel)
    um_passo(painel, lambda: formatacao.alterar_recuo(painel, 48),
             "aumentar recuo nos dois paragrafos e' um passo de desfazer")
    selecionar_tudo(painel)
    formatacao.alterar_recuo(painel, 48)
    margens = [b.blockFormat().leftMargin() for b in _blocos(painel)]
    checa_igual(margens, [48.0, 48.0], "aumentar recuo soma 48 px nos dois paragrafos")
    formatacao.alterar_recuo(painel, -200)
    margens = [b.blockFormat().leftMargin() for b in _blocos(painel)]
    checa_igual(margens, [0.0, 0.0], "recuo nao fica negativo")

    selecionar_tudo(painel)
    um_passo(painel, lambda: formatacao.definir_espacamento(painel, 150),
             "espacamento e' um passo de desfazer")
    selecionar_tudo(painel)
    formatacao.definir_espacamento(painel, 150)
    checa_igual(ler(painel).espacamento, 150, "espacamento 1,5 nos paragrafos")
    formatacao.definir_espacamento(painel, 100)
    checa_igual(ler(painel).espacamento, 100,
                "contraprova: outro espacamento muda a leitura da faixa")


def testar_listas() -> None:
    secao("listas: liga, desliga e troca o estilo")
    painel = novo_painel("um\ndois")
    selecionar_tudo(painel)
    um_passo(painel,
             lambda: formatacao.alternar_lista(painel, QTextListFormat.Style.ListDisc),
             "ligar marcadores e' um passo de desfazer")
    selecionar_tudo(painel)
    formatacao.alternar_lista(painel, QTextListFormat.Style.ListDisc)
    checa(all(b.textList() is not None for b in _blocos(painel)),
          "marcadores nos dois paragrafos")
    checa(ler(painel).marcadores, "a faixa enxerga o marcador")

    formatacao.alternar_lista(painel, QTextListFormat.Style.ListDisc)
    checa(all(b.textList() is None for b in _blocos(painel)),
          "o mesmo comando desliga os marcadores")

    selecionar_tudo(painel)
    formatacao.alternar_lista(painel, QTextListFormat.Style.ListDecimal)
    checa(ler(painel).numeracao, "numeracao ligada")
    selecionar_tudo(painel)
    formatacao.alternar_lista(painel, QTextListFormat.Style.ListDecimal)
    checa(not ler(painel).numeracao, "contraprova: a numeracao desliga de novo")


def main() -> int:
    testar_caractere()
    testar_limpar()
    testar_alinhamento()
    testar_recuo_e_espacamento()
    testar_listas()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
