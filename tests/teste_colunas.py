"""Colunas de texto iguais na tela, no PDF e na impressao (passos 2 e 3, docs/SPIKES.md).

Secao com w:cols (num, space, equalWidth) que comeca e termina em folha nova: a pagina do Qt tem
a largura da coluna e a folha junta N paginas do Qt lado a lado (`modelo/folhas.MapaFolhas`,
`GrupoDeColunas`). A secao continua com colunas no meio da folha (passo 4) continua em uma coluna
so', com o aviso COLUNAS (`teste_secoes.testar_continua_e_colunas`).

Fixtures em codigo (nenhum .docx no repositorio). Cada verificacao de tela tem contraprova.
"""

from __future__ import annotations

import math

from ajudantes import (checa, checa_igual, drenar_eventos, preparar_qt, resumir, secao,
                       usar_fontes_do_documento)
import fixtures_docx as fx

QT = preparar_qt()

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QTextCursor, QTransform  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from editdoc.formato_docx import secoes as fx_secoes  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo import secoes as mod_secoes  # noqa: E402
from editdoc.modelo.folhas import GrupoDeColunas, MapaFolhas  # noqa: E402
from editdoc.modelo.pagina import Pagina  # noqa: E402

TEXTO = ("Paragrafo {i} com texto bastante para quebrar a linha mais de uma vez na coluna "
         "estreita da folha.")
PGMAR = ('<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" '
         'w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>')
#: Corpo de 9026 twips (A4, margens de 1440): duas colunas de 4153 com 720 de vao.
CORPO_TW = 9026
ESPACO_TW = 720
COLUNA_TW = (CORPO_TW - ESPACO_TW) / 2


def _paragrafos(n: int, inicio: int = 0, extra: dict | None = None) -> str:
    extra = extra or {}
    return "".join(f"<w:p><w:r><w:t>{TEXTO.format(i=i)}</w:t></w:r>{extra.get(i, '')}</w:p>"
                   for i in range(inicio, inicio + n))


def _com_colunas(docx: bytes, num: int = 2, espaco: int = ESPACO_TW, sep: bool = False) -> bytes:
    """O sectPr final ganha o w:cols (no lugar do esquema: depois do pgMar)."""
    partes = fx.partes_de(docx)
    xml = partes["word/document.xml"].decode("utf-8")
    cols = f'<w:cols w:num="{num}" w:space="{espaco}"' + (' w:sep="1"' if sep else "") + "/>"
    fim = xml.rindex("</w:sectPr>")
    partes["word/document.xml"] = (xml[:fim] + cols + xml[fim:]).encode("utf-8")
    return fx.montar(partes)


def docx_colunas(paragrafos: int = 70, sep: bool = False, corpo: str | None = None) -> bytes:
    return _com_colunas(fx.docx_com_xml(corpo if corpo is not None else _paragrafos(paragrafos)),
                        sep=sep)


def docx_duas_secoes() -> bytes:
    """Secao 1 em uma coluna (8 paragrafos), quebra de proxima pagina, secao 2 em duas colunas."""
    meio = (f"<w:p><w:pPr><w:sectPr>{PGMAR}</w:sectPr></w:pPr><w:r><w:t>Fim da secao 1."
            "</w:t></w:r></w:p>")
    return docx_colunas(corpo=_paragrafos(8) + meio + _paragrafos(70, 100))


def _janela(docx: bytes, largura: int = 1100, altura: int = 900):
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    modelo, avisos = ler(docx)
    janela = JanelaPrincipal(configuracao.padrao())
    janela.resize(largura, altura)
    janela.show()
    janela.carregar(modelo, avisos, None)
    janela.painel.setFocus()
    drenar_eventos()
    janela.painel.viewport().grab()
    return janela


def _fechar(janela) -> None:
    janela.painel.sair_da_faixa()
    janela.painel.documento_corpo().setModified(False)
    janela.close()
    drenar_eventos()


def _bloco_na_pagina(lay, p: int, ultimo: bool = False):
    """O primeiro (ou o ultimo) bloco cujo topo cai na pagina do Qt p."""
    doc = lay.doc
    dl = doc.documentLayout()
    achado = None
    b = doc.begin()
    while b.isValid():
        if lay.mapa.pagina_de_y(dl.blockBoundingRect(b).top() + 1) == p and b.length() > 1:
            achado = b
            if not ultimo:
                return b
        b = b.next()
    return achado


def _tinta(img: QImage, x0: float, x1: float, y0: float, y1: float, dpr: float = 1.0,
           passo: int = 2, limite: int = 110) -> int:
    """Pixels escuros (texto) no retangulo (px logicos) da captura."""
    n = 0
    for y in range(max(0, int(y0 * dpr)), min(img.height(), int(y1 * dpr)), passo):
        for x in range(max(0, int(x0 * dpr)), min(img.width(), int(x1 * dpr)), passo):
            c = QColor(img.pixel(x, y))
            if c.red() < limite and c.green() < limite and c.blue() < limite:
                n += 1
    return n


def _colunas_na_tela(janela, n: int):
    """(x da coluna 1, x da coluna 2, x do vao, topo e pe' do corpo) da folha n, px do viewport."""
    m = janela.painel.mapa()
    lay = janela.painel.layout_pag
    x, y, _w, _h = m.folha_na_tela(n)
    ef = lay.efetiva_da(n)
    e = m.escala
    c1 = x + ef.margem_esq_tw * e
    c2 = x + (ef.margem_esq_tw + COLUNA_TW + ESPACO_TW) * e
    vao = x + (ef.margem_esq_tw + COLUNA_TW) * e
    return c1, c2, vao, y + ef.margem_sup_tw * e, y + (ef.margem_sup_tw + ef.corpo_altura_tw()) * e


# -- modelo ------------------------------------------------------------------------------------

def testar_mapa_de_folhas() -> None:
    secao("MapaFolhas: grupos de colunas (folha x pagina do Qt), identidade sem grupos")
    m = MapaFolhas.de_altura(1000.0)
    checa(not m.tem_colunas() and m.folha_da_pagina(7) == 7 and list(m.paginas_da_folha(7)) == [7]
          and m.deslocamento(7) == 0.0, "sem grupos: identidade")
    # Paginas 0-2 em uma coluna; 3-9 em duas (7 paginas -> 4 folhas); 10-11 em uma; 12-17 em 3.
    m.definir_grupos([GrupoDeColunas(3, 7, 2, 5000.0, 4000.0),
                      GrupoDeColunas(12, 6, 3, 3000.0, 2500.0)])
    folhas = [m.folha_da_pagina(p) for p in range(20)]
    checa_igual(folhas, [0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 9, 9, 9, 10, 10, 10, 11, 12],
                "folha de cada pagina do Qt")
    volta = [list(m.paginas_da_folha(n)) for n in range(13)]
    checa_igual(volta, [[0], [1], [2], [3, 4], [5, 6], [7, 8], [9], [10], [11], [12, 13, 14],
                        [15, 16, 17], [18], [19]], "paginas do Qt de cada folha (a volta)")
    checa(all(m.folha_da_pagina(p) == n for n in range(13) for p in m.paginas_da_folha(n)),
          "ida e volta coerentes")
    checa_igual([m.deslocamento(p) for p in (3, 4, 9, 10, 12, 13, 14)],
                [0.0, 5000.0, 0.0, 0.0, 0.0, 3000.0, 6000.0], "deslocamento da coluna")
    checa_igual(m.folhas_de_paginas(18), 11, "18 paginas do Qt formam 11 folhas")
    checa_igual([m.coluna_no_x(9, x) for x in (-100, 2000, 2700, 3200, 5900, 9000)],
                [12, 12, 12, 13, 14, 14], "coluna sob o x (o meio do vao divide)")
    checa_igual(m.folha_de_y(4500.0, 13), 3, "y na pagina 4 (coluna 2) -> folha 3")
    checa(not m.definir_grupos(m.grupos), "os mesmos grupos: nada muda")
    checa(m.definir_grupos([]) and m.folha_da_pagina(4) == 4, "sem grupos de novo: identidade")


def testar_quais_secoes_mostram() -> None:
    secao("colunas_na_tela: so' colunas iguais em secao que comeca e termina em folha nova")
    a4 = Pagina()
    casos = {
        "uma secao, duas colunas": ([(None, a4, (2, 720))], [True]),
        "continua no meio": ([(None, a4, None), ("continuous", a4, (2, 720))], [False, False]),
        "seguinte continua": ([(None, a4, (2, 720)), ("continuous", a4, (1, 0))], [False, False]),
        "proxima pagina": ([(None, a4, (1, 0)), ("nextPage", a4, (3, 360))], [False, True]),
        "proxima coluna": ([(None, a4, (1, 0)), ("nextColumn", a4, (2, 720))], [False, False]),
        "desiguais": ([(None, a4, None)], [False]),
        "estreitas demais": ([(None, a4, (40, 0))], [False]),
    }
    for nome, (entrada, esperado) in casos.items():
        checa_igual(mod_secoes.colunas_na_tela(entrada), esperado, nome)
    checa_igual(fx_secoes.colunas_iguais(None), (1, 0, False), "sem sectPr: uma coluna")
    sect = ('<w:sectPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:cols w:num="2" w:space="567" w:sep="1"/></w:sectPr>')
    checa_igual(fx_secoes.colunas_iguais(sect), (2, 567, True), "num, space e sep")
    desiguais = sect.replace('<w:cols w:num="2" w:space="567" w:sep="1"/>',
                             '<w:cols w:num="2" w:equalWidth="0"><w:col w:w="3000" w:space="500"/>'
                             '<w:col w:w="5000"/></w:cols>')
    checa(fx_secoes.colunas_iguais(desiguais) is None, "larguras diferentes: None (fica de fora)")


def testar_aviso_e_arquivo() -> None:
    secao("arquivo: sem aviso COLUNAS para a secao que a tela mostra; o w:cols volta igual")
    modelo, avisos = ler(docx_colunas(sep=True))
    checa_igual([a.codigo for a in avisos if a.codigo == "COLUNAS"], [],
                "secao de colunas em folha nova: sem aviso")
    gravado = escrever(modelo)
    xml = fx.partes_de(gravado)["word/document.xml"].decode("utf-8")
    origem = fx.partes_de(docx_colunas(sep=True))["word/document.xml"].decode("utf-8")

    def cols(texto):
        from lxml import etree
        raiz = etree.fromstring(texto.encode("utf-8"))
        el = raiz.find(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}cols")
        return etree.tostring(el, method="c14n")
    checa_igual(cols(xml), cols(origem), "o w:cols volta ao arquivo (c14n)")
    _m, avisos = ler(fx.docx_com_secao_continua())
    checa_igual([a.contagem for a in avisos if a.codigo == "COLUNAS"], [1],
                "contraprova: a secao continua de colunas mantem o aviso (passo 4)")


# -- tela ------------------------------------------------------------------------------------

def testar_layout_e_numeros() -> None:
    secao("layout: pagina do Qt na largura da coluna, folha = 2 paginas, PAGE e NUMPAGES")
    janela = _janela(docx_colunas())
    try:
        lay = janela.painel.layout_pag
        qt = lay.doc.pageCount()
        checa(lay.mapa.tem_colunas() and lay.secoes.lista[0].colunas == 2, "a secao tem 2 colunas")
        checa(qt >= 3, f"o texto ocupa {qt} paginas do Qt (colunas)")
        checa_igual(lay.numero_paginas(), math.ceil(qt / 2), "folhas = paginas do Qt / 2")
        checa(abs(lay.doc.pageSize().width() - COLUNA_TW) < 1, "pagina do Qt na largura da coluna")
        doc = lay.doc
        dl = doc.documentLayout()
        b, largas = doc.begin(), 0
        while b.isValid():
            r = dl.blockBoundingRect(b)
            for i in range(b.layout().lineCount()):
                ln = b.layout().lineAt(i)
                if r.left() + ln.x() + ln.naturalTextWidth() > COLUNA_TW + 1:
                    largas += 1
            b = b.next()
        checa_igual(largas, 0, "nenhuma linha passa da largura da coluna")
        # PAGE e NUMPAGES: a folha da coluna (o manipulador do campo do corpo).
        manip = lay._manipulador_campos
        y_col2 = lay.mapa.topo(1) + 100.0
        y_f2 = lay.mapa.topo(2) + 100.0
        checa_igual((manip._indice(100.0), manip._indice(y_col2), manip._indice(y_f2)), (0, 0, 1),
                    "PAGE: colunas 1 e 2 na folha 1, a pagina do Qt 2 na folha 2")
        checa_igual(lay.contexto_campos.total, lay.numero_paginas(), "NUMPAGES conta folhas")
        checa_igual(lay.pagina_de_y(y_col2), 0, "pagina_de_y da coluna 2 e' a folha 1")
        checa_igual(janela.painel.total_de_paginas(), lay.numero_paginas(),
                    "barra de status: total de folhas")
    finally:
        _fechar(janela)


def testar_tela_e_separador() -> None:
    secao("tela: tinta nas duas colunas, vao em branco; w:sep pinta a linha no meio do vao")
    for sep in (False, True):
        janela = _janela(docx_colunas(sep=sep))
        try:
            img = janela.painel.viewport().grab().toImage()
            c1, c2, vao, topo, pe = _colunas_na_tela(janela, 0)
            e = janela.painel.mapa().escala
            y1 = min(pe, img.height() - 2)
            col1 = _tinta(img, c1, c1 + COLUNA_TW * e, topo, y1)
            col2 = _tinta(img, c2, c2 + COLUNA_TW * e, topo, y1)
            meio = vao + ESPACO_TW * e / 2
            linha = _tinta(img, meio - 3, meio + 3, topo, y1, passo=1, limite=200)
            checa(col1 > 50 and col2 > 50, f"sep={sep}: texto na coluna 1 ({col1}) e 2 ({col2})")
            if sep:
                checa(linha > 20, f"w:sep: linha no meio do vao ({linha} pixels)")
            else:
                checa_igual(_tinta(img, vao + 3, vao + ESPACO_TW * e - 3, topo, y1, passo=1,
                                   limite=200), 0,
                            "sem w:sep: o vao fica em branco (contraprova da linha)")
        finally:
            _fechar(janela)
    # Contraprova da coluna 2: sem colunas (o mesmo texto), a faixa da coluna 2 tem texto de
    # uma linha so' (a coluna 1 ocupa a largura toda), e a 2a pagina do Qt vai para a folha 2.
    janela = _janela(fx.docx_com_xml(_paragrafos(70)))
    try:
        checa(not janela.painel.layout_pag.mapa.tem_colunas(), "contraprova: sem w:cols, sem grupos")
    finally:
        _fechar(janela)


def testar_caret_clique_setas() -> None:
    secao("caret, clique na coluna 2, setas e PageUp/PageDown")
    janela = _janela(docx_colunas())
    try:
        painel = janela.painel
        lay = painel.layout_pag
        # Caret num paragrafo da coluna 2.
        b = _bloco_na_pagina(lay, 1)
        cur = QTextCursor(lay.doc)
        cur.setPosition(b.position() + 3)
        painel.setTextCursor(cur)
        painel.verticalScrollBar().setValue(0)
        drenar_eventos()
        c1, c2, _vao, topo, _pe = _colunas_na_tela(janela, 0)
        m = painel.mapa()
        r = painel._retangulo_do_caret(m, painel._paginas())
        checa(r is not None and c2 - 2 <= r.x() <= c2 + COLUNA_TW * m.escala,
              f"caret na coluna 2 (x {r.x():.0f}, coluna em {c2:.0f})")
        # Ida e volta tela -> documento na coluna 2.
        xd, yd = m.tela_para_doc(c2 + 40, topo + 30, painel._paginas())
        checa(lay.mapa.pagina_de_y(yd) == 1 and 0 <= xd < COLUNA_TW, "o ponto da coluna 2 e' "
              "da pagina do Qt 1, com x dentro da coluna")
        xt, yt = m.doc_para_tela(xd, yd, painel._paginas())
        checa(abs(xt - (c2 + 40)) < 0.5 and abs(yt - (topo + 30)) < 0.5, "tela -> doc -> tela")
        # Clique na coluna 2 e na coluna 1 (o mouse de verdade).
        QTest.mouseClick(painel.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier(0),
                         QPointF(c2 + 40, topo + 30).toPoint())
        drenar_eventos()
        checa_igual(lay.pagina_qt_do_cursor(painel.textCursor().position()), 1,
                    "clique na coluna 2 poe o cursor na pagina do Qt 1")
        QTest.mouseClick(painel.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier(0),
                         QPointF(c1 + 40, topo + 30).toPoint())
        drenar_eventos()
        checa_igual(lay.pagina_qt_do_cursor(painel.textCursor().position()), 0,
                    "contraprova: clique na coluna 1 fica na pagina do Qt 0")
        # Seta para baixo na ultima linha da coluna 1 vai para o alto da coluna 2.
        ultimo = _bloco_na_pagina(lay, 0, ultimo=True)
        cur = QTextCursor(lay.doc)
        cur.setPosition(ultimo.position() + ultimo.length() - 1)
        painel.setTextCursor(cur)
        while lay.pagina_qt_do_cursor(painel.textCursor().position()) != 0:
            QTest.keyClick(painel, Qt.Key.Key_Up)
        antes = painel.textCursor().position()
        for _ in range(4):
            QTest.keyClick(painel, Qt.Key.Key_Down)
            if lay.pagina_qt_do_cursor(painel.textCursor().position()) == 1:
                break
        drenar_eventos()
        checa_igual(lay.pagina_qt_do_cursor(painel.textCursor().position()), 1,
                    "seta para baixo desce da coluna 1 para a coluna 2")
        r = painel._retangulo_do_caret(painel.mapa(), painel._paginas())
        c1b, c2b, *_ = _colunas_na_tela(janela, 0)
        checa(r is not None and r.x() >= c2b - 2, "o caret aparece na coluna 2 da tela")
        QTest.keyClick(painel, Qt.Key.Key_Up)
        checa(lay.pagina_qt_do_cursor(painel.textCursor().position()) == 0
              and painel.textCursor().position() <= antes + 200, "seta para cima volta a' coluna 1")
        # PageDown: uma altura de TELA (fica na coluna 1, mais abaixo); outro vai a' folha 2.
        cur = QTextCursor(lay.doc)
        cur.setPosition(0)
        painel.setTextCursor(cur)
        painel.verticalScrollBar().setValue(0)
        drenar_eventos()
        y0 = lay.retangulo_cursor(0).y()
        QTest.keyClick(painel, Qt.Key.Key_PageDown)
        pos1 = painel.textCursor().position()
        checa(lay.pagina_qt_do_cursor(pos1) == 0 and lay.retangulo_cursor(pos1).y() > y0 + 3000,
              "PageDown desce na coluna 1 (nao pula para a coluna 2 pelo y do documento)")
        for _ in range(3):
            QTest.keyClick(painel, Qt.Key.Key_PageDown)
            if lay.pagina_do_cursor(painel.textCursor().position()) >= 1:
                break
        pos2 = painel.textCursor().position()
        checa(lay.pagina_do_cursor(pos2) == 1 and lay.mapa.coluna_da_pagina(
            lay.pagina_qt_do_cursor(pos2)) == 0, "PageDown chega a' folha 2, na coluna 1")
        QTest.keyClick(painel, Qt.Key.Key_PageUp)
        checa(lay.pagina_do_cursor(painel.textCursor().position()) <= 1
              and painel.textCursor().position() < pos2, "PageUp volta")
    finally:
        _fechar(janela)


def testar_selecao() -> None:
    secao("selecao da coluna 1 ate' a coluna 2 pinta o realce nas duas")
    janela = _janela(docx_colunas())
    try:
        painel = janela.painel
        lay = painel.layout_pag
        painel.verticalScrollBar().setValue(0)
        drenar_eventos()
        c1, c2, _vao, topo, pe = _colunas_na_tela(janela, 0)
        e = painel.mapa().escala

        def azul(img) -> tuple[int, int]:
            def conta(x0):
                n = 0
                for y in range(int(topo), min(int(pe), img.height() - 1), 3):
                    for x in range(int(x0), int(x0 + COLUNA_TW * e), 3):
                        c = QColor(img.pixel(x, y))
                        if c.blue() > 180 and c.red() < 60:
                            n += 1
                return n
            return conta(c1), conta(c2)

        sem = azul(painel.viewport().grab().toImage())
        ini = _bloco_na_pagina(lay, 0)
        fim = _bloco_na_pagina(lay, 1)
        cur = QTextCursor(lay.doc)
        cur.setPosition(ini.position())
        cur.setPosition(fim.position() + fim.length() - 1, QTextCursor.MoveMode.KeepAnchor)
        painel.setTextCursor(cur)
        painel.verticalScrollBar().setValue(0)
        drenar_eventos()
        com = azul(painel.viewport().grab().toImage())
        checa(sem == (0, 0), f"contraprova: sem selecao, nada azul ({sem})")
        checa(com[0] > 20 and com[1] > 20, f"realce na coluna 1 e na coluna 2 ({com})")
    finally:
        _fechar(janela)


def testar_duas_secoes() -> None:
    secao("secao de uma coluna e depois secao de duas: folhas, PAGE e o mapa")
    janela = _janela(docx_duas_secoes())
    try:
        lay = janela.painel.layout_pag
        lista = lay.secoes.lista
        checa_igual([i.colunas for i in lista], [1, 2], "a 1a em uma coluna, a 2a em duas")
        g = lay.mapa.grupos
        checa(len(g) == 1 and g[0].pagina == lista[1].inicio, "o grupo comeca na folha da 2a secao")
        qt = lay.doc.pageCount()
        checa_igual(lay.numero_paginas(), lista[1].inicio + math.ceil((qt - g[0].pagina) / 2),
                    "folhas: as da 1a secao + as paginas da 2a / 2")
        checa_igual(sum(i.paginas for i in lista), lay.numero_paginas(), "secoes cobrem as folhas")
        n = lista[1].inicio
        checa_igual([p for p, _dx, _w in lay.mapa.colunas_da_folha(n)], [g[0].pagina, g[0].pagina + 1],
                    "a primeira folha da 2a secao mostra duas paginas do Qt")
        checa(lay.efetiva_da(0).corpo_largura_tw() == CORPO_TW, "a 1a secao na largura toda")
        b = _bloco_na_pagina(lay, 0)
        r = lay.doc.documentLayout().blockBoundingRect(b)
        checa(r.width() > COLUNA_TW + 1000, "o paragrafo da 1a secao usa a largura toda")
    finally:
        _fechar(janela)


def testar_notas_no_pe() -> None:
    secao("nota de rodape de uma referencia na coluna 2: no pe' da folha, na coluna 2")
    corpo = _paragrafos(70, extra={30: fx.ref_nota(1)})
    docx = _com_colunas(fx.docx_com_notas(corpo_xml=corpo, notas_xml=fx.nota_xml(1, "Nota da "
                        "coluna dois com texto."), notas_fim_xml=None))
    janela = _janela(docx)
    try:
        lay = janela.painel.layout_pag
        lay.atualizar_notas()
        paginas = sorted(lay.notas.paginas)
        checa(len(paginas) == 1, f"a nota fica numa pagina do Qt so' ({paginas})")
        p = paginas[0]
        n = lay.mapa.folha_da_pagina(p)
        fatias = lay.notas.paginas[p]
        checa(all(lay.mapa.topo(p) < f.y < lay.mapa.fim(p) for f in fatias),
              "a area de notas fica na faixa da coluna da referencia")
        # Pinta so' as notas da folha numa imagem branca: a tinta fica na coluna da referencia.
        from editdoc.interface.notas import desenhar_notas
        ef = lay.efetiva_da(n)
        img = QImage(ef.largura_tw // 10, ef.altura_tw // 10, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 255, 255))
        pintor = QPainter(img)
        desenhar_notas(pintor, lay, n, QTransform().scale(0.1, 0.1))
        pintor.end()
        dx = lay.mapa.deslocamento(p)
        x0 = (ef.margem_esq_tw + dx) / 10
        dentro = _tinta(img, x0, x0 + COLUNA_TW / 10, 0, img.height())
        fora_x = (ef.margem_esq_tw + (COLUNA_TW + ESPACO_TW if dx == 0 else 0)) / 10
        fora = _tinta(img, fora_x, fora_x + COLUNA_TW / 10, 0, img.height())
        checa(dentro > 5 and fora == 0, f"tinta da nota na coluna dela ({dentro}) e nao na outra "
                                        f"({fora})")
        checa(abs(lay.notas.todos()[0].doc.textWidth() - COLUNA_TW) < 2 or
              abs(lay.notas.todos()[0].doc.pageSize().width() - COLUNA_TW) < 2,
              "o documento da nota tem a largura da coluna")
        checa(dx > 0, "a referencia esta' na coluna 2 (a fixture)")
    finally:
        _fechar(janela)


def testar_pdf_e_impressao() -> None:
    secao("PDF e impressao: uma pagina por folha, com as duas colunas")
    import leitor_pdf
    from editdoc.interface import impressao
    usar_fontes_do_documento()
    janela = _janela(docx_colunas())
    try:
        lay = janela.painel.layout_pag
        total = lay.numero_paginas()
        meta = impressao.Metadados("Colunas", "Teste", "EditDoc")
        pdf = leitor_pdf.ler_pdf(impressao.gerar_pdf(lay, list(range(total)), meta))
        checa_igual(len(pdf.paginas), total, "uma pagina de PDF por folha")
        import re

        def numeros(texto):
            return set(re.findall(r"Paragrafo (\d+)", texto.replace("\t", " ")))

        def inteiros_na(p):
            """Numeros dos paragrafos que ficam inteiros na pagina do Qt p."""
            dl = lay.doc.documentLayout()
            saida, b = set(), lay.doc.begin()
            while b.isValid():
                r = dl.blockBoundingRect(b)
                if lay.mapa.pagina_de_y(r.top() + 1) == p == lay.mapa.pagina_de_y(r.bottom() - 1):
                    saida.add(b.text().split()[1])
                b = b.next()
            return saida
        pag1, pag2 = numeros(pdf.paginas[0].texto), numeros(pdf.paginas[1].texto)
        col2, folha2 = inteiros_na(1), inteiros_na(2)
        palavra2 = sorted(col2)[0]
        checa(col2 and col2 <= pag1, "a coluna 2 (pagina do Qt 1) sai inteira na pagina 1")
        checa(folha2 and folha2 <= pag2 and not folha2 & pag1,
              f"a pagina do Qt 2 sai na pagina 2 do PDF (contraprova: nao na 1) "
              f"{sorted(folha2)} {sorted(pag2)} {sorted(folha2 & pag1)}")
        import tempfile
        import pathlib
        with tempfile.TemporaryDirectory() as pasta:
            caminho = pathlib.Path(pasta) / "impresso.pdf"
            impressora = impressao.nova_impressora(pdf=True)
            impressora.setOutputFileName(str(caminho))
            enviadas = impressao.imprimir(impressora, lay, list(range(total)))
            dados = caminho.read_bytes()
        checa_igual(enviadas, total, "impressao: as folhas enviadas")
        impresso = leitor_pdf.ler_pdf(dados)
        checa(len(impresso.paginas) == total and f"Paragrafo {palavra2}" in
              impresso.paginas[0].texto.replace("\t", " "), "impressao: a coluna 2 na folha 1")
    finally:
        _fechar(janela)


def testar_quebra_de_coluna() -> None:
    secao("quebra de coluna (w:br type=column) no comeco do paragrafo: ele vai para a coluna 2")
    br = '<w:r><w:br w:type="column"/></w:r>'
    corpo = (_paragrafos(3) + f"<w:p>{br}<w:r><w:t>Comeca a segunda coluna.</w:t></w:r></w:p>"
             + _paragrafos(3, 10) + f"<w:p><w:r><w:t>Fim da coluna dois.</w:t></w:r>{br}</w:p>"
             + "<w:p><w:r><w:t>Terceira coluna.</w:t></w:r></w:p>")
    janela = _janela(docx_colunas(corpo=corpo))
    try:
        lay = janela.painel.layout_pag
        dl = lay.doc.documentLayout()

        def pagina(texto):
            b = lay.doc.begin()
            while b.isValid():
                if texto in b.text():
                    return lay.mapa.pagina_de_y(dl.blockBoundingRect(b).top() + 1)
                b = b.next()
            return None
        checa_igual(pagina("Comeca a segunda"), 1, "quebra no comeco: o paragrafo na coluna 2")
        checa_igual(pagina("Fim da coluna dois"), 1, "quebra no fim: o paragrafo fica")
        checa_igual(pagina("Terceira coluna"), 2, "e o seguinte vai para a coluna 3 (folha 2)")
        checa_igual(lay.numero_paginas(), 2, "duas folhas")
        # O que a janela grava (do Qt, com as quebras derivadas da tela nos blocos).
        gravado = escrever(janela._modelo_atual())
        xml = fx.partes_de(gravado)["word/document.xml"].decode("utf-8")
        checa(xml.count('w:type="column"') == 2 and 'w:type="page"' not in xml,
              "o arquivo volta com as duas quebras de coluna e sem quebra de pagina")
    finally:
        _fechar(janela)
    # Contraprova: sem colunas, a quebra de coluna nao quebra pagina.
    janela = _janela(fx.docx_com_xml(corpo))
    try:
        checa_igual(janela.painel.layout_pag.numero_paginas(), 1,
                    "contraprova: sem w:cols, tudo numa folha")
    finally:
        _fechar(janela)


def main() -> int:
    testar_mapa_de_folhas()
    testar_quais_secoes_mostram()
    testar_aviso_e_arquivo()
    testar_layout_e_numeros()
    testar_tela_e_separador()
    testar_caret_clique_setas()
    testar_selecao()
    testar_duas_secoes()
    testar_notas_no_pe()
    testar_pdf_e_impressao()
    testar_quebra_de_coluna()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
