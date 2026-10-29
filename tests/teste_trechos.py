"""Experimento (ramo experimento/tabelas): layout do corpo por trechos entre tabelas.

`editdoc/interface/trechos.py` (ligado por EDITDOC_TRECHOS=1) pagina o corpo em pedacos, um
QTextDocument por trecho terminado numa tabela, para a tecla antes das tabelas nao refazer todas
as tabelas de baixo (docs/SPIKES.md, "experimento/tabelas"). Aqui, sem relogio:

- as posicoes de TODAS as linhas de TODOS os blocos (inclusive nas celulas) sao as do
  QTextDocumentLayout do Qt sobre o documento inteiro, ao abrir, depois de digitar antes das
  tabelas, numa celula e num item de lista, depois do Enter, do Backspace e do desfazer;
- a tecla antes das tabelas refaz no maximo dois trechos (o dela e o de baixo quando o fim muda);
- contraprova: um trecho deslocado de proposito e' acusado.
"""

from __future__ import annotations

import os

os.environ["EDITDOC_TRECHOS"] = "1"

from ajudantes import (checa, checa_igual, preparar_qt, resumir, secao,  # noqa: E402
                       usar_fonte_windows, usar_fontes_do_documento)

preparar_qt()

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QTextFormat  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

import teste_desempenho as td  # noqa: E402


def referencia(doc):
    """O mesmo conteudo num QTextDocument com o layout do Qt (o que o EditDoc usava)."""
    c = doc.clone()
    c.setDocumentMargin(doc.documentMargin())
    c.setDefaultFont(doc.defaultFont())
    c.setDefaultTextOption(doc.defaultTextOption())
    lc = c.documentLayout()
    lc.setPaintDevice(doc.documentLayout().paintDevice())
    base = QTextFormat.ObjectTypes.UserObject.value
    for t in range(base, base + 16):
        h = doc.documentLayout().handlerForObject(t)
        if h is not None:
            lc.registerHandler(t, h)
    c.setPageSize(doc.pageSize())
    lc.documentSize()
    return c


def diferentes(doc) -> int:
    ref = referencia(doc)
    ld, lr = doc.documentLayout(), ref.documentLayout()
    dif = 0
    b, r = doc.begin(), ref.begin()
    while b.isValid():
        rd, rr = ld.blockBoundingRect(b), lr.blockBoundingRect(r)
        td_, tr = b.layout(), r.layout()
        tol = 1.0 if b.text() else 1.5  # o vazio escondido depois da tabela: passo de 1 twip
        ok = abs(rd.y() - rr.y()) < tol and td_.lineCount() == tr.lineCount() and all(
            td_.lineAt(i).textStart() == tr.lineAt(i).textStart() and
            abs(td_.lineAt(i).y() - tr.lineAt(i).y()) < 1.0 for i in range(td_.lineCount()))
        dif += not ok
        b, r = b.next(), r.next()
    if ld.pageCount() != lr.pageCount():
        dif += 1
    return dif


def _ir(painel, pos):
    c = painel.textCursor()
    c.setPosition(pos)
    painel.setTextCursor(c)
    painel.setFocus()


def testar_posicoes() -> None:
    secao("layout por trechos: as mesmas linhas do layout do Qt, ao abrir, digitar e desfazer")
    painel = td._painel(td.documento_plano())
    try:
        doc = painel.documento_corpo()
        lay = doc.documentLayout()
        checa_igual(type(lay).__name__, "LayoutPorTrechos", "o corpo usa o layout por trechos")
        checa(len(lay._trechos) == 17, f"16 tabelas: 17 trechos ({len(lay._trechos)})")
        checa_igual(diferentes(doc), 0, "ao abrir: nenhuma linha em outro lugar")
        teclas = 0
        for ponto in ("plano_terco", "plano_celula", "plano_item"):
            _ir(painel, td._ponto(painel, ponto))
            lay.refeitos = lay.reespacados = 0
            for _ in range(12):
                QTest.keyClick(painel, Qt.Key.Key_A)
            teclas += 12
            checa(lay.refeitos == 0, f"{ponto}: digitar nao remonta trecho ({lay.refeitos})")
            checa(lay.reespacados <= 12 * 2, f"{ponto}: no maximo dois trechos por tecla "
                                              f"({lay.reespacados} reespacados em 12)")
            checa_igual(diferentes(doc), 0, f"{ponto}: 12 teclas, as mesmas linhas")
            QTest.keyClick(painel, Qt.Key.Key_Return)
            QTest.keyClick(painel, Qt.Key.Key_B)
            QTest.keyClick(painel, Qt.Key.Key_Backspace)
            QTest.keyClick(painel, Qt.Key.Key_Backspace)
            teclas += 4
            checa_igual(diferentes(doc), 0, f"{ponto}: Enter e Backspace, as mesmas linhas")
        for _ in range(teclas + 5):
            painel.undo()
        checa_igual(diferentes(doc), 0, "desfazer tudo: as mesmas linhas")
        # Contraprova: um trecho do meio deslocado de proposito.
        t = lay._trechos[8]
        t.desloc += 300
        lay._copiar_blocos(t, None)
        checa(diferentes(doc) > 0, "contraprova: trecho deslocado 300 twips e' acusado")
        t.desloc -= 300
        lay._copiar_blocos(t, None)
        checa_igual(diferentes(doc), 0, "e volta igual")
    finally:
        td._fechar(painel)


def main() -> int:
    usar_fonte_windows()
    usar_fontes_do_documento()
    testar_posicoes()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
