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
        # Estrutura: tabela nova no meio (17 -> 18 trechos) e desfeita, sem remontar tudo.
        from PySide6.QtGui import QTextCursor
        total = len(lay._trechos)
        c = QTextCursor(doc.findBlock(td._ponto(painel, "plano_item")))
        lay.refeitos = 0
        c.insertTable(2, 2)
        checa_igual(len(lay._trechos), total + 1, "tabela nova no primeiro nivel: um trecho a mais")
        checa(lay.refeitos <= 3, f"so' os trechos tocados sao montados de novo ({lay.refeitos})")
        checa_igual(diferentes(doc), 0, "tabela nova: as mesmas linhas")
        lay.refeitos = 0
        doc.undo()
        checa_igual(len(lay._trechos), total, "desfeita: os trechos de antes")
        checa(lay.refeitos <= 3, f"desfeita sem remontar tudo ({lay.refeitos})")
        checa_igual(diferentes(doc), 0, "desfeita: as mesmas linhas")
        # Documento inteiro "sujo" sem mudar o texto (o realce das revisoes): sem remontar.
        lay.refeitos = 0
        doc.markContentsDirty(0, doc.characterCount())
        checa(lay.refeitos == 0, f"markContentsDirty do documento inteiro nao remonta ({lay.refeitos})")
        checa_igual(diferentes(doc), 0, "e as linhas continuam as mesmas")
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


def testar_controle_ligado() -> None:
    secao("layout por trechos com Controlar alteracoes: a celula remarcada a cada tecla")
    from editdoc.formato_docx.escritor import escrever
    from editdoc.formato_docx.leitor import ler
    modelo, _ = ler(td.documento_plano())
    modelo.controlar_alteracoes = True
    painel = td._painel(escrever(modelo))
    try:
        doc = painel.documento_corpo()
        lay = doc.documentLayout()
        for ponto in ("plano_terco", "plano_item"):
            _ir(painel, td._ponto(painel, ponto))
            lay.refeitos = 0
            for _ in range(8):
                QTest.keyClick(painel, Qt.Key.Key_A)
            QTest.keyClick(painel, Qt.Key.Key_Backspace)
            checa(lay.refeitos == 0, f"{ponto}: digitar rastreado nao remonta trecho ({lay.refeitos})")
            checa_igual(diferentes(doc), 0, f"{ponto}: digitar rastreado, as mesmas linhas")
        for _ in range(25):
            painel.undo()
        checa_igual(diferentes(doc), 0, "desfazer: as mesmas linhas")
    finally:
        td._fechar(painel)


def main() -> int:
    usar_fonte_windows()
    usar_fontes_do_documento()
    testar_posicoes()
    testar_controle_ligado()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
