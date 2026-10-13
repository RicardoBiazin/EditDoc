"""Ponte Qt: modelo -> QTextDocument -> modelo, igual depois de normalizar.

Cobre o que o Qt faz diferente do modelo: sublinhado (NoUnderline limpa; texto
inserido sem formato herda o sublinhado do vizinho, e a ponte nunca insere sem
formato), listas (numId no bloco, desde a 0.1.4), quebra de linha como U+2028, e
idempotencia.
Tem contraprova: um modelo alterado e' acusado.
"""

from __future__ import annotations

import dataclasses

from ajudantes import checa, checa_igual, pular, preparar_qt, resumir, secao
import fixtures_docx as fx

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextDocument, QTextListFormat  # noqa: E402

from editdoc.modelo.documento import Documento, Paragrafo, Run, normalizar  # noqa: E402
from editdoc.modelo.numeracao import texto_visivel  # noqa: E402
from editdoc.ponte_qt import de_qt, listas, para_qt  # noqa: E402

FIM_DE_LINHA_QT = " "


def ida_e_volta(modelo: Documento) -> Documento:
    qdoc = QTextDocument()
    para_qt.preencher(qdoc, modelo)
    return de_qt.extrair(qdoc)


def iguais(a: Documento, b: Documento) -> bool:
    return normalizar(a).paragrafos == normalizar(b).paragrafos


def testar_ida_e_volta() -> None:
    secao("ida e volta pelo QTextDocument, nas fixtures")
    casos = {
        "amostra completa": fx.documento_completo(),
        "formatos None, False e True": fx.documento_com_formatos_mistos(),
        "numeracao separada": fx.documento_com_numeracao_separada(),
        "documento vazio (um paragrafo sem texto)": Documento(paragrafos=[Paragrafo()]),
    }
    for nome, doc in casos.items():
        volta = ida_e_volta(doc)
        checa(iguais(doc, volta), f"{nome}: modelo igual depois da volta pelo Qt")
        checa(iguais(volta, ida_e_volta(volta)), f"{nome}: a segunda volta e' igual a primeira")


def testar_sublinhado() -> None:
    secao("sublinhado: None nao herda, False limpa, e texto sem formato herda o vizinho")
    doc = Documento(paragrafos=[Paragrafo(runs=[
        Run("liga", sublinhado=True), Run("desliga", sublinhado=False), Run("sem")])])
    volta = ida_e_volta(doc).paragrafos[0].runs
    checa_igual(volta[1].sublinhado, False, "o run desligado volta com sublinhado False")
    checa_igual(volta[2].sublinhado, None, "o run sem sublinhado volta como None, nao herda")
    qdoc = QTextDocument()
    cursor = QTextCursor(qdoc)
    liga = QTextCharFormat()
    liga.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
    cursor.insertText("a", liga)
    cursor.insertText("b")
    fragmentos = []
    it = qdoc.begin().begin()
    while not it.atEnd():
        fragmentos.append(it.fragment().text())
        it += 1
    checa_igual(fragmentos, ["ab"],
                "contraprova: texto inserido sem formato entra no trecho sublinhado")
    limpo = QTextCharFormat()
    limpo.setUnderlineStyle(QTextCharFormat.UnderlineStyle.NoUnderline)
    cursor.setPosition(0)
    cursor.setPosition(2, QTextCursor.MoveMode.KeepAnchor)
    cursor.mergeCharFormat(limpo)
    estilo = qdoc.begin().begin().fragment().charFormat().underlineStyle()
    checa(estilo == QTextCharFormat.UnderlineStyle.NoUnderline,
          "NoUnderline por merge limpa o sublinhado")


def testar_listas() -> None:
    # Reescrita na 0.1.4: a lista deixou de ser QTextList (que so' conta um nivel e so' tem
    # disco, circulo, quadrado e 1, 2, 3). As mesmas verificacoes, pela propriedade do bloco
    # (numId) e pelo numero que a tela pinta.
    secao("listas: marcadores e numeracao viram lista no bloco, com o numero calculado")
    doc = fx.documento_completo()
    qdoc = QTextDocument()
    para_qt.preencher(qdoc, doc)
    rotulos = listas.numerador_de(qdoc).rotulos()
    blocos = [qdoc.findBlockByNumber(i) for i in range(len(doc.paragrafos))]
    nums = [listas.lista_do_bloco(b.blockFormat())[0] for b in blocos]
    indices_marcadores = [i for i, p in enumerate(doc.paragrafos) if p.numeracao == "marcadores"]
    indices_numeracao = [i for i, p in enumerate(doc.paragrafos) if p.numeracao == "numeracao"]
    checa(all(i in rotulos for i in indices_marcadores), "marcadores sao itens de lista")
    checa(all(texto_visivel(rotulos[i].texto) == "•" for i in indices_marcadores),
          "marcadores mostram o ponto redondo")
    checa_igual([rotulos[i].texto for i in indices_numeracao], ["1.", "2.", "1."],
                "numeracao mostra 1., 2. e recomeca em 1. depois do texto")
    checa(nums[indices_marcadores[0]] == nums[indices_marcadores[1]],
          "dois marcadores seguidos formam uma so' lista")
    checa(nums[indices_numeracao[0]] != nums[indices_marcadores[0]],
          "marcador e numeracao nao se misturam")
    separado = fx.documento_com_numeracao_separada()
    qdoc2 = QTextDocument()
    para_qt.preencher(qdoc2, separado)
    rot2 = listas.numerador_de(qdoc2).rotulos()
    primeira = listas.lista_do_bloco(qdoc2.findBlockByNumber(0).blockFormat())[0]
    segunda = listas.lista_do_bloco(qdoc2.findBlockByNumber(3).blockFormat())[0]
    checa(primeira is not None and segunda is not None and primeira != segunda
          and rot2[3].texto == "1.", "duas numeracoes separadas por texto sao listas diferentes")
    checa(2 not in rot2, "paragrafo do meio nao e' lista")
    checa(qdoc2.findBlockByNumber(0).textList() is None, "contraprova: o Qt nao ve QTextList")


def testar_quebra_de_linha() -> None:
    secao("quebra de linha: U+2028 no bloco do Qt, barra-n no modelo")
    doc = Documento(paragrafos=[Paragrafo(runs=[Run("um\ndois")])])
    qdoc = QTextDocument()
    para_qt.preencher(qdoc, doc)
    checa(FIM_DE_LINHA_QT in qdoc.begin().text(), "o Qt guarda a quebra como U+2028 no bloco")
    checa_igual(de_qt.extrair(qdoc).paragrafos[0].runs[0].texto, "um\ndois",
                "a volta devolve a quebra como barra-n")


def testar_contraprova() -> None:
    secao("contraprova: um negrito trocado depois da volta e' acusado")
    doc = fx.documento_completo()
    volta = ida_e_volta(doc)
    alterado = dataclasses.replace(volta, paragrafos=[dataclasses.replace(p, runs=list(p.runs))
                                                       for p in volta.paragrafos])
    alterado.paragrafos[1].runs[0] = dataclasses.replace(alterado.paragrafos[1].runs[0],
                                                         negrito=False)
    checa(not iguais(doc, alterado), "a diferenca de negrito e' detectada")


def main() -> int:
    testar_ida_e_volta()
    testar_sublinhado()
    testar_listas()
    testar_quebra_de_linha()
    testar_contraprova()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
