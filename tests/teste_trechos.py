"""Layout do corpo por trechos entre tabelas (0.1.31, o padrao em documento com tabela).

`editdoc/interface/trechos.py` pagina o corpo em pedacos, um QTextDocument por trecho terminado
numa tabela, para a tecla antes das tabelas nao refazer todas as tabelas de baixo (docs/SPIKES.md,
"experimento/tabelas" e "0.1.31"). EDITDOC_TRECHOS=0 volta ao layout do Qt. Aqui, sem relogio:

- o padrao: documento com tabela usa o layout por trechos, sem tabela o do Qt; com =0, o do Qt;

- as posicoes de TODAS as linhas de TODOS os blocos (inclusive nas celulas) sao as do
  QTextDocumentLayout do Qt sobre o documento inteiro, ao abrir, depois de digitar antes das
  tabelas, numa celula e num item de lista, depois do Enter, do Backspace e do desfazer;
- a tecla antes das tabelas refaz no maximo dois trechos (o dela e o de baixo quando o fim muda);
- contraprova: um trecho deslocado de proposito e' acusado.
"""

from __future__ import annotations

import os

os.environ.pop("EDITDOC_TRECHOS", None)  # o padrao (a passada com =0 e' testar_desligado)

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


def _folhas(layout, selecao=None, escala: float = 0.06) -> list:
    """Cada folha como sai no papel (a mesma pintura do PDF e da impressao) ou, com `selecao`,
    o corpo com a selecao pintada (a da tela), numa imagem."""
    from PySide6.QtGui import QImage, QPainter, QTransform
    from editdoc.interface import impressao
    from editdoc.interface.vista_paginas import desenhar_folha
    total = layout.numero_paginas()
    imagens = []
    for n in range(total):
        pag = layout.efetiva_da(n)
        img = QImage(int(pag.largura_tw * escala) + 1, int(pag.altura_tw * escala) + 1,
                     QImage.Format.Format_RGB32)
        img.fill(0xFFFFFFFF)
        p = QPainter(img)
        transf = QTransform.fromScale(escala, escala)
        if selecao is None:
            impressao.pintar_pagina(p, layout, n, total, transf)
        else:
            desenhar_folha(p, layout, n, transf, selecao=selecao)
        p.end()
        imagens.append(img)
    return imagens


#: O trecho comeca ate' 0,6 twip (0,03 pt) fora do lugar exato (o espacador do Qt anda em
#: passos inteiros): a letra e a borda da selecao podem cair no pixel vizinho. Medido: ate' 0,8%
#: das folhas do plano; um trecho fora 600 twips da' 3 a 10%.
PIXELS_DIFERENTES_MAX = 0.01


def _diferenca(a, b) -> float:
    """Fracao dos pixels com diferenca forte (> 64 num canal)."""
    if a.size() != b.size():
        return 1.0
    n = 0
    for y in range(a.height()):
        for x in range(a.width()):
            pa, pb = a.pixel(x, y), b.pixel(x, y)
            if pa != pb and max(abs(((pa >> s) & 255) - ((pb >> s) & 255)) for s in (0, 8, 16)) > 64:
                n += 1
    return n / float(a.width() * a.height())


def _comparar_pinturas(janela_ou_painel, rotulo: str, selecao=None) -> None:
    """Pinta com o layout por trechos e com o do Qt (o mesmo documento) e compara pixel a pixel."""
    from editdoc.interface import trechos
    painel = getattr(janela_ou_painel, "painel", janela_ou_painel)
    lay = painel.layout_pag
    doc = painel.documento_corpo()
    checa(trechos.em_trechos(doc), f"{rotulo}: com tabela, o layout e' o por trechos")
    sel = selecao(doc) if selecao else None
    com = _folhas(lay, sel)
    trechos.trocar(doc, False)
    sel = selecao(doc) if selecao else None
    sem = _folhas(lay, sel)
    trechos.trocar(doc, True)
    checa_igual(len(com), len(sem), f"{rotulo}: o mesmo numero de folhas")
    pior = max((_diferenca(a, b) for a, b in zip(com, sem)), default=0.0)
    checa(pior <= PIXELS_DIFERENTES_MAX, f"{rotulo}: folhas iguais (pior folha com {pior:.3%} dos "
                                          f"pixels diferentes; limite {PIXELS_DIFERENTES_MAX:.1%})")
    if selecao is None:
        # Contraprova: o trecho 3 deslocado 600 twips muda a pintura.
        t = doc.documentLayout()._trechos[min(3, len(doc.documentLayout()._trechos) - 1)]
        t.desloc += 600
        torto = _folhas(lay)
        t.desloc -= 600
        doc.documentLayout()._copiar_blocos(t, None)
        pior = max((_diferenca(a, b) for a, b in zip(torto, sem)), default=0.0)
        checa(pior > PIXELS_DIFERENTES_MAX, f"{rotulo}: contraprova, trecho deslocado 600 twips "
                                             f"passa do limite ({pior:.3%})")


def testar_pintura() -> None:
    secao("layout por trechos: papel (PDF e impressao), selecao entre trechos, colunas e secoes")
    from PySide6.QtGui import QTextCursor
    painel = td._painel(td.documento_plano())
    try:
        _comparar_pinturas(painel, "plano, papel")

        def atravessa(doc):
            lay = doc.documentLayout()
            ini = lay._trechos[2].ini - 40 if hasattr(lay, "_trechos") else 0
            from editdoc.interface import trechos
            t = trechos.LayoutPorTrechos  # noqa: F841
            c = QTextCursor(doc)
            c.setPosition(max(0, ini))
            c.setPosition(min(doc.characterCount() - 1, ini + 2500), QTextCursor.MoveMode.KeepAnchor)
            return c
        # A mesma faixa nos dois layouts: as posicoes de D nao mudam com a troca.
        faixa = {}

        def selecao(doc):
            if "c" not in faixa:
                faixa["c"] = atravessa(doc)
            c = QTextCursor(doc)
            c.setPosition(faixa["c"].selectionStart())
            c.setPosition(faixa["c"].selectionEnd(), QTextCursor.MoveMode.KeepAnchor)
            return c
        _comparar_pinturas(painel, "selecao atravessando tres trechos", selecao)
    finally:
        td._fechar(painel)
    # Colunas (0.1.29) com tabelas dentro do trecho, e duas secoes de papel diferente.
    import teste_colunas as tc
    tabela = ("<w:tbl><w:tblPr><w:tblW w:w=\"0\" w:type=\"auto\"/><w:tblBorders>"
              "<w:top w:val=\"single\" w:sz=\"4\"/><w:bottom w:val=\"single\" w:sz=\"4\"/>"
              "<w:insideH w:val=\"single\" w:sz=\"4\"/></w:tblBorders></w:tblPr>"
              "<w:tblGrid><w:gridCol w:w=\"2000\"/><w:gridCol w:w=\"2000\"/></w:tblGrid>"
              + "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>L{r}C{c}</w:t></w:r></w:p></w:tc>"
                                           for c in range(2)) + "</w:tr>" for r in range(8))
              + "</w:tbl>")
    corpo = tc._paragrafos(20) + tabela + tc._paragrafos(30, 20) + tabela + tc._paragrafos(30, 50)
    janela = tc._janela(tc.docx_colunas(corpo=corpo))
    try:
        _comparar_pinturas(janela, "duas colunas com tabelas")
    finally:
        tc._fechar(janela)
    paisagem = ("<w:p><w:pPr><w:sectPr><w:pgSz w:w=\"16838\" w:h=\"11906\" w:orient=\"landscape\"/>"
                "<w:pgMar w:top=\"1134\" w:right=\"1134\" w:bottom=\"1134\" w:left=\"1134\" "
                "w:header=\"709\" w:footer=\"709\" w:gutter=\"0\"/></w:sectPr></w:pPr>"
                "<w:r><w:t>Fim da secao paisagem.</w:t></w:r></w:p>")
    import fixtures_docx as fxd
    janela = tc._janela(fxd.docx_com_xml(tc._paragrafos(15) + tabela + paisagem + tc._paragrafos(40, 15)
                                         + tabela + tc._paragrafos(20, 60)))
    try:
        _comparar_pinturas(janela, "secao paisagem e secao retrato, com tabelas")
    finally:
        janela.painel.sair_da_faixa()
        janela.painel.documento_corpo().setModified(False)
        janela.close()


def testar_padrao_e_desligado() -> None:
    secao("0.1.31: por trechos e' o padrao com tabela; sem tabela e com EDITDOC_TRECHOS=0, o do Qt")
    from editdoc.interface import trechos
    checa(trechos.ligado(), "sem a variavel, ligado")
    painel = td._painel(td.documento_plano())
    try:
        checa(trechos.em_trechos(painel.documento_corpo()), "plano (16 tabelas): por trechos")
    finally:
        td._fechar(painel)
    painel = td._painel(td.documento_simples())
    try:
        checa(not trechos.em_trechos(painel.documento_corpo()), "documento sem tabela: o do Qt")
    finally:
        td._fechar(painel)
    os.environ["EDITDOC_TRECHOS"] = "0"
    try:
        checa(not trechos.ligado(), "EDITDOC_TRECHOS=0: desligado")
        painel = td._painel(td.documento_plano())
        try:
            checa(not trechos.em_trechos(painel.documento_corpo()),
                  "EDITDOC_TRECHOS=0: o plano fica no layout do Qt")
        finally:
            td._fechar(painel)
    finally:
        os.environ.pop("EDITDOC_TRECHOS", None)


def main() -> int:
    usar_fonte_windows()
    usar_fontes_do_documento()
    testar_padrao_e_desligado()
    testar_posicoes()
    testar_controle_ligado()
    testar_pintura()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
