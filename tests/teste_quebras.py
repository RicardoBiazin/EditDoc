"""Quebra de pagina (Ctrl+Enter): entra no documento, aparece na tela e vai e volta pelo .docx.

Quebra e' um atributo do paragrafo (quebra_antes). No .docx ela e' um w:br type="page" no comeco
do paragrafo. A quebra no meio do texto parte o paragrafo, e isso fica registrado como perda de
estrutura (nao de aparencia).
"""

from __future__ import annotations

import re

import fixtures_docx as fx
from ajudantes import checa, checa_igual, drenar_eventos, pular, preparar_qt, resumir, secao, usar_fonte_windows

QT = preparar_qt()

from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402

BR_PAGINA = b'w:type="page"'


def _xml_com_corpo(paragrafos_xml: str) -> bytes:
    """Um .docx valido cujo corpo e' exatamente `paragrafos_xml` (sem sectPr extra)."""
    base = fx.bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("x")])]))
    xml = fx.partes_de(base)["word/document.xml"].decode("utf-8")
    inicio = xml.index("<w:body>") + len("<w:body>")
    fim = xml.index("<w:sectPr")
    novo = xml[:inicio] + paragrafos_xml + xml[fim:]
    return fx.com_parte(base, "word/document.xml", novo.encode("utf-8"))


def _textos(modelo) -> list[tuple[str, bool]]:
    return [("".join(r.texto for r in p.runs), p.quebra_antes) for p in modelo.paragrafos]


def testar_leitura_da_quebra() -> None:
    secao("leitura: w:br type=page vira quebra_antes, sem aviso")
    casos = {
        "meio do texto parte o paragrafo": (
            '<w:p><w:r><w:t>antes</w:t><w:br w:type="page"/><w:t>depois</w:t></w:r></w:p>',
            [("antes", False), ("depois", True)]),
        "quebra no comeco vira a propria quebra do paragrafo": (
            '<w:p><w:r><w:br w:type="page"/></w:r><w:r><w:t>depois</w:t></w:r></w:p>',
            [("depois", True)]),
        "paragrafo so' com a quebra": (
            '<w:p><w:r><w:br w:type="page"/></w:r></w:p>',
            [("", True)]),
        "duas quebras seguidas": (
            '<w:p><w:r><w:br w:type="page"/><w:br w:type="page"/><w:t>x</w:t></w:r></w:p>',
            [("", True), ("x", True)]),
        "pageBreakBefore no paragrafo": (
            '<w:p><w:pPr><w:pageBreakBefore/></w:pPr><w:r><w:t>topo</w:t></w:r></w:p>',
            [("topo", True)]),
    }
    for nome, (xml, esperado) in casos.items():
        modelo, avisos = ler(_xml_com_corpo(xml))
        checa_igual(_textos(modelo), esperado, f"{nome}")
        checa(not any(a.codigo == "QUEBRA_DE_PAGINA" for a in avisos),
              f"{nome}: a quebra de pagina nao gera aviso")

    # 0.1.12: a quebra de coluna virou marca no fluxo e volta ao arquivo (ate' a 0.1.11 saia,
    # com o aviso QUEBRA_DE_PAGINA). A contraprova passa a ser a quebra de tipo desconhecido.
    from editdoc.modelo.documento import MarcaQuebra
    modelo, avisos = ler(_xml_com_corpo(
        '<w:p><w:r><w:br w:type="column"/><w:t>coluna</w:t></w:r></w:p>'))
    checa(not any(a.codigo == "QUEBRA_DE_PAGINA" for a in avisos)
          and any(isinstance(r.marca, MarcaQuebra) for r in modelo.paragrafos[0].runs),
          "quebra de coluna vira marca no fluxo, sem aviso")
    modelo, avisos = ler(_xml_com_corpo(
        '<w:p><w:r><w:br w:type="estranho"/><w:t>x</w:t></w:r></w:p>'))
    checa(any(a.codigo == "QUEBRA_DE_PAGINA" for a in avisos),
          "contraprova: quebra de tipo desconhecido continua avisada")


def testar_escrita_e_volta() -> None:
    secao("escrita: quebra vira w:br type=page no comeco do paragrafo; volta igual")
    doc = Documento(paragrafos=[
        Paragrafo(runs=[Run("primeira pagina")]),
        Paragrafo(runs=[Run("segunda pagina")], quebra_antes=True),
        Paragrafo(runs=[Run("terceira")]),
    ])
    dados = escrever(doc)
    xml = fx.partes_de(dados)["word/document.xml"]
    checa_igual(len(re.findall(BR_PAGINA, xml)), 1, "uma quebra no documento gera um w:br type=page")
    lido, avisos = ler(dados)
    checa_igual(_textos(lido), _textos(doc), "a quebra volta no mesmo paragrafo")
    checa(not avisos, f"quebra representada nao gera aviso (avisos: {[a.codigo for a in avisos]})")
    segundo = escrever(lido)
    checa_igual(fx.partes_de(segundo)["word/document.xml"], xml,
                "escrever de novo gera o mesmo document.xml (idempotente)")
    sem = escrever(Documento(paragrafos=[Paragrafo(runs=[Run("sem quebra")])]))
    checa(BR_PAGINA not in fx.partes_de(sem)["word/document.xml"],
          "contraprova: documento sem quebra nao ganha w:br type=page")


def testar_tela() -> None:
    secao("tela: Ctrl+Enter cria a quebra, o caret confirma a pagina e a linha aparece")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from editdoc.interface.painel_documento import PainelDocumento
    from editdoc.interface.vista_paginas import COR_QUEBRA

    painel = PainelDocumento("Segoe UI", 11)
    painel.resize(1000, 800)
    painel.show()
    drenar_eventos(2)
    painel.setPlainText("Primeiro paragrafo da primeira pagina.")
    painel.moveCursor(painel.textCursor().MoveOperation.End)
    painel.setFocus()
    drenar_eventos(1)
    checa_igual(painel.total_de_paginas(), 1, "um paragrafo curto cabe numa pagina")
    QTest.keyClick(painel, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(painel, "Segunda pagina")
    drenar_eventos(2)
    checa_igual(painel.total_de_paginas(), 2, "Ctrl+Enter abre a segunda pagina")
    checa_igual(painel.pagina_atual(), 1, "o caret, depois da quebra, esta na pagina 2")
    flags = [b.blockFormat().pageBreakPolicy() for b in _blocos(painel.document())]
    checa(any(f == painel_quebra() for f in flags), "o bloco novo leva a quebra antes de si")

    painel.moveCursor(painel.textCursor().MoveOperation.Start)
    QTest.keyClick(painel, Qt.Key.Key_Return)
    drenar_eventos(2)
    checa_igual(painel.total_de_paginas(), 2,
                "contraprova: Enter comum nao cria pagina nova (ainda 2 paginas, nao 3)")

    # A linha tracejada fica no fim do paragrafo anterior, dentro do corpo.
    painel.setFocus()
    img = painel.viewport().grab().toImage()
    cor = COR_QUEBRA.rgb() & 0xFFFFFF
    n = _contar_cor(img, cor)
    checa(n > 20, f"a linha 'Quebra de pagina' aparece na tela ({n} pixels)")
    # 0.1.15: a lista dos blocos com quebra fica guardada enquanto se digita, e uma troca de
    # formato (a quebra tirada) a refaz.
    guardada = painel._quebras
    for _ in range(5):
        QTest.keyClick(painel, Qt.Key.Key_X)
        painel.viewport().grab()
    checa(painel._quebras is guardada, "digitar nao refaz a lista dos blocos com quebra")
    from PySide6.QtGui import QTextCursor, QTextFormat

    def tirar_quebra(p):
        doc = p.document()
        bloco = next(b for b in _blocos(doc) if b.blockFormat().pageBreakPolicy() == painel_quebra())
        c = QTextCursor(bloco)
        bf = bloco.blockFormat()
        bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_Auto)
        c.setBlockFormat(bf)

    tirar_quebra(painel)
    n = _contar_cor(painel.viewport().grab().toImage(), cor)
    checa_igual(n, 0, "tirada a quebra (troca de formato), a linha some")
    painel.document().undo()
    checa(_contar_cor(painel.viewport().grab().toImage(), cor) > 20,
          "desfeita a troca, a linha volta")
    # Contraprova: sem refazer a lista na troca de formato, a linha velha fica na tela.
    from editdoc.interface import vista_paginas as vp
    original = vp.VistaPaginas._mudou_texto

    def sem_invalidar(self, pos, removido, adicionado):
        guardar = self._quebras
        original(self, pos, removido, adicionado)
        self._quebras = guardar

    vp.VistaPaginas._mudou_texto = sem_invalidar
    painel.document().contentsChange.disconnect(painel._mudou_texto)
    painel.document().contentsChange.connect(painel._mudou_texto)
    try:
        tirar_quebra(painel)
        n = _contar_cor(painel.viewport().grab().toImage(), cor)
    finally:
        vp.VistaPaginas._mudou_texto = original
        painel.document().contentsChange.disconnect(painel._mudou_texto)
        painel.document().contentsChange.connect(painel._mudou_texto)
    checa(n > 20, f"contraprova: sem refazer a lista, a linha velha fica ({n} pixels)")
    painel.document().setModified(False)
    painel.close()

    sem = PainelDocumento("Segoe UI", 11)
    sem.resize(1000, 800)
    sem.show()
    drenar_eventos(2)
    sem.setPlainText("Primeiro paragrafo.\nSegundo paragrafo.")
    drenar_eventos(2)
    cor_sem = _contar_cor(sem.viewport().grab().toImage(), cor)
    checa_igual(cor_sem, 0, "contraprova: sem quebra, nenhum pixel da linha tracejada")
    sem.close()


def painel_quebra():
    from PySide6.QtGui import QTextFormat
    return QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore


def _blocos(doc):
    bloco = doc.begin()
    while bloco.isValid():
        yield bloco
        bloco = bloco.next()


def _contar_cor(img, cor: int) -> int:
    n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            if (img.pixel(x, y) & 0xFFFFFF) == cor:
                n += 1
    return n


def testar_ponte_qt() -> None:
    secao("ponte Qt: a quebra do modelo vira PageBreak_AlwaysBefore e volta")
    from editdoc.ponte_qt import de_qt, para_qt
    from PySide6.QtGui import QTextDocument

    modelo = Documento(paragrafos=[Paragrafo(runs=[Run("a")]),
                                   Paragrafo(runs=[Run("b")], quebra_antes=True)])
    doc = QTextDocument()
    para_qt.preencher(doc, modelo)
    checa_igual(de_qt.extrair(doc).paragrafos[1].quebra_antes, True,
                "de volta do Qt, a quebra continua no segundo paragrafo")
    checa_igual(de_qt.extrair(doc).paragrafos[0].quebra_antes, False,
                "contraprova: o primeiro paragrafo nao ganha quebra")


# ----- 0.1.22: o paragrafo que so' tem a quebra leva a quebra no fim dele --------------------

_SO_QUEBRA = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
_SECAO_NO_PARAGRAFO = ('<w:p><w:pPr><w:sectPr><w:type w:val="nextPage"/>'
                       '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" '
                       'w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/>'
                       '</w:sectPr></w:pPr></w:p>')


def _janela_de(corpo_xml: str):
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    j = JanelaPrincipal(configuracao.padrao())
    j.resize(1000, 800)
    j.show()
    modelo, avisos = ler(_xml_com_corpo(corpo_xml))
    j.carregar(modelo, avisos, None)
    drenar_eventos(2)
    j.painel.layout_pag.atualizar_secoes()
    drenar_eventos(1)
    return j


def _fechar(j) -> None:
    j.painel.documento_corpo().setModified(False)
    j.close()
    drenar_eventos(1)


def _bloco_com(doc, texto: str):
    bloco = doc.begin()
    while bloco.isValid():
        if bloco.text() == texto:
            return bloco
        bloco = bloco.next()
    raise AssertionError(f"bloco {texto!r} nao achado")


def testar_so_quebra_no_fim() -> None:
    secao("0.1.22: paragrafo so' com a quebra: a quebra fica no fim dele, e volta igual ao arquivo")
    from PySide6.QtGui import QTextDocument, QTextFormat

    from editdoc.ponte_qt import de_qt, para_qt
    modelo = Documento(paragrafos=[Paragrafo(runs=[Run("a")]),
                                   Paragrafo(runs=[], quebra_antes=True),
                                   Paragrafo(runs=[Run("b")])])
    doc = QTextDocument()
    para_qt.preencher(doc, modelo)
    checa_igual(_bloco_com(doc, "").blockFormat().pageBreakPolicy(),
                QTextFormat.PageBreakFlag.PageBreak_AlwaysAfter,
                "o paragrafo so' com a quebra leva a quebra no fim (AlwaysAfter)")
    checa_igual(_textos(de_qt.extrair(doc)), _textos(modelo),
                "de volta do Qt, o paragrafo so' com a quebra continua no mesmo lugar")
    dados = escrever(modelo)
    xml = fx.partes_de(dados)["word/document.xml"]
    checa_igual(len(re.findall(BR_PAGINA, xml)), 1, "o arquivo leva uma quebra so'")
    lido, avisos = ler(dados)
    checa_igual(_textos(lido), _textos(modelo), "o arquivo volta com o paragrafo so' com a quebra")
    checa(not avisos, "a quebra no fim nao gera aviso")
    checa_igual(fx.partes_de(escrever(lido))["word/document.xml"], xml,
                "gravar de novo gera o mesmo document.xml (c14n)")


def testar_so_quebra_no_meio() -> None:
    secao("0.1.22: so' a quebra, sem secao: o paragrafo vazio fica na pagina de cima")
    from PySide6.QtGui import QTextCursor, QTextFormat
    j = _janela_de('<w:p><w:r><w:t>primeiro</w:t></w:r></w:p>' + _SO_QUEBRA +
                   '<w:p><w:r><w:t>segundo</w:t></w:r></w:p>')
    try:
        lay = j.painel.layout_pag
        doc = lay.doc
        checa_igual(lay.numero_paginas(), 2, "a quebra so' separa duas paginas")
        checa_igual(lay.pagina_do_cursor(_bloco_com(doc, "").position()), 0,
                    "o paragrafo so' com a quebra fica na pagina de cima")
        checa_igual(lay.pagina_do_cursor(_bloco_com(doc, "segundo").position()), 1,
                    "o paragrafo de baixo comeca a pagina seguinte")
        # Contraprova: com a quebra ANTES do paragrafo vazio (a representacao de antes), ele vai
        # para o alto da pagina 2.
        vazio = _bloco_com(doc, "")
        bf = vazio.blockFormat()
        bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
        QTextCursor(vazio).setBlockFormat(bf)
        drenar_eventos(1)
        checa_igual(lay.pagina_do_cursor(_bloco_com(doc, "").position()), 1,
                    "contraprova: com a quebra antes, o paragrafo vazio vai para a pagina 2")
    finally:
        _fechar(j)


def testar_so_quebra_antes_de_secao() -> None:
    secao("0.1.22: so' a quebra e a quebra de secao seguinte: duas paginas, sem pagina em branco")
    from editdoc.interface.secoes import ConjuntoDeSecoes
    corpo = ('<w:p><w:r><w:t>capa</w:t></w:r></w:p>' + _SO_QUEBRA + _SECAO_NO_PARAGRAFO +
             '<w:p><w:r><w:t>miolo</w:t></w:r></w:p>')
    j = _janela_de(corpo)
    try:
        lay = j.painel.layout_pag
        doc = lay.doc
        checa_igual(lay.numero_paginas(), 2,
                    "capa, quebra e secao seguinte: duas paginas (sem pagina em branco no meio)")
        checa_igual(lay.pagina_do_cursor(_bloco_com(doc, "miolo").position()), 1,
                    "a secao seguinte comeca na pagina 2")
        # Contraprova: sem a supressao, a quebra da secao vem depois do paragrafo da quebra e a
        # pagina em branco aparece (3 paginas).
        original = ConjuntoDeSecoes._quebra_do_usuario_logo_antes
        ConjuntoDeSecoes._quebra_do_usuario_logo_antes = lambda self, pos: False
        try:
            lay.secoes.conferir_formatos(forcar=True)
            drenar_eventos(1)
            checa_igual(lay.numero_paginas(), 3,
                        "contraprova: sem a supressao, a pagina em branco aparece (3 paginas)")
        finally:
            ConjuntoDeSecoes._quebra_do_usuario_logo_antes = original
    finally:
        _fechar(j)


def testar_quebra_normal_sem_secao() -> None:
    secao("0.1.22: quebra normal sem secao: o texto com a quebra no fim termina a pagina")
    from PySide6.QtGui import QTextFormat
    j = _janela_de('<w:p><w:r><w:t>um</w:t><w:br w:type="page"/></w:r></w:p>'
                   '<w:p><w:r><w:t>dois</w:t></w:r></w:p>')
    try:
        lay = j.painel.layout_pag
        checa_igual(lay.numero_paginas(), 2, "o texto com a quebra gera duas paginas")
        checa_igual(lay.pagina_do_cursor(_bloco_com(lay.doc, "dois").position()), 1,
                    "o paragrafo seguinte comeca a pagina 2")
        # O leitor separa a quebra do fim do texto num paragrafo so' com ela (como ja' fazia).
        checa(bool(_bloco_com(lay.doc, "").blockFormat().pageBreakPolicy()
                   & QTextFormat.PageBreakFlag.PageBreak_AlwaysAfter),
              "a quebra no fim de 'um' fica no paragrafo so' com ela, no fim dele")
    finally:
        _fechar(j)


def testar_enter_copiar_rotulo_e_digitar() -> None:
    secao("0.1.22: Enter, copiar e colar, rotulo e digitar com a quebra so' no fim")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest

    from editdoc.ponte_qt import de_qt
    j = _janela_de('<w:p><w:r><w:t>primeiro</w:t></w:r></w:p>' + _SO_QUEBRA +
                   '<w:p><w:r><w:t>segundo</w:t></w:r></w:p>')
    painel = j.painel
    try:
        painel.setFocus()
        doc = painel.document()
        checa(_bloco_com(doc, "segundo").blockNumber() in painel._blocos_com_quebra(),
              "o rotulo 'Quebra de pagina' vale para o paragrafo so' com a quebra")
        # Enter no paragrafo so' com a quebra: a quebra fica nele; o paragrafo novo e' comum.
        painel.setTextCursor(QTextCursor(_bloco_com(doc, "")))
        QTest.keyClick(painel, Qt.Key.Key_Return)
        drenar_eventos(1)
        checa_igual([p.quebra_antes for p in de_qt.extrair(doc).paragrafos],
                    [False, True, False, False],
                    "Enter: a quebra fica no paragrafo vazio; o paragrafo novo nao leva quebra")
        # Copiar: o trecho com o paragrafo so' com a quebra (no meio dele) leva a quebra para o
        # colar. (Medido: selecionar so' a marca do paragrafo vazio, sem o texto seguinte, nao
        # leva o formato dele no HTML; isso nao e' coberto aqui.)
        cursor = QTextCursor(_bloco_com(doc, "primeiro"))
        cursor.setPosition(_bloco_com(doc, "segundo").position() + len("segundo"),
                           QTextCursor.MoveMode.KeepAnchor)
        painel.setTextCursor(cursor)
        painel.copy()
        painel.setTextCursor(QTextCursor(_bloco_com(doc, "segundo")))
        QTest.keyClick(painel, Qt.Key.Key_End)
        QTest.keyClick(painel, Qt.Key.Key_Return)
        painel.paste()
        drenar_eventos(2)
        quebras = sum(1 for p in de_qt.extrair(doc).paragrafos if p.quebra_antes)
        checa_igual(quebras, 2, "colar o paragrafo so' com a quebra traz a quebra junto")
        # Digitar no paragrafo so' com a quebra: o texto fica antes da quebra (no fim dele).
        painel.setTextCursor(QTextCursor(_bloco_com(doc, "")))
        QTest.keyClicks(painel, "xy")
        drenar_eventos(1)
        modelo = de_qt.extrair(doc)
        textos = [("".join(r.texto for r in p.runs), p.quebra_antes) for p in modelo.paragrafos]
        i = textos.index(("xy", False)) if ("xy", False) in textos else -1
        checa(i >= 0 and textos[i + 1] == ("", True),
              f"digitado no paragrafo com a quebra: o texto vem antes da quebra ({textos[:3]})")
        doc.setModified(False)
    finally:
        _fechar(j)


def main() -> int:
    testar_leitura_da_quebra()
    testar_escrita_e_volta()
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    if not usar_fonte_windows(9):
        return pular("Segoe UI nao esta instalada")
    testar_ponte_qt()
    testar_tela()
    testar_so_quebra_no_fim()
    testar_so_quebra_no_meio()
    testar_so_quebra_antes_de_secao()
    testar_quebra_normal_sem_secao()
    testar_enter_copiar_rotulo_e_digitar()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
