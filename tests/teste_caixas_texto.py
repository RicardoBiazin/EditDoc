"""Texto das caixas de texto editavel (0.1.5).

- analise: a caixa DrawingML com o VML de reserva, texto formatado e link, e' editavel; a
  caixa com tabela, campo ou imagem dentro abre so' para leitura com o motivo; forma sem texto
  nao e' caixa; a trava de regravar-e-reler;
- regravar: o texto novo entra no Choice (wps:txbx) e no Fallback (v:textbox); o resto da
  forma fica identico (c14n fora do w:txbxContent); o link ganha relacao nova; o arquivo passa
  no validador e na conferencia, e reabre com o texto novo; tabela nos blocos e' recusada;
- tela: a caixa editavel aparece do tamanho do wp:extent, com o texto composto dentro; a
  so' leitura continua a etiqueta;
- edicao: duplo clique na caixa e Enter com a caixa selecionada abrem o dialogo (exec trocado
  pelo teste); confirmar troca o objeto num passo so' de desfazer; a caixa so' leitura nao muda
  nada; o aviso das caixas diz que o texto e' editavel.
"""

from __future__ import annotations

import copy

from ajudantes import checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import avisos as mod_avisos  # noqa: E402
from editdoc.formato_docx import caixas, conferencia, ordem  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo.documento import (Paragrafo, Run, Tabela, Linha, Celula,  # noqa: E402
                                      objetos_de, paragrafos_de)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS = {"w": W, "mc": MC}


def documento(caixa_xml: str):
    corpo = '<w:p><w:r><w:t xml:space="preserve">Antes </w:t></w:r>' + caixa_xml + \
        '<w:r><w:t xml:space="preserve"> depois.</w:t></w:r></w:p>'
    return fx.docx_com_corpo_de_objetos(corpo, fx.RELACOES_OBJETOS, fx.PARTES_OBJETOS,
                                        fx.TIPOS_OBJETOS, fx.PADROES_OBJETOS)


def a_caixa(modelo):
    return next(o for o in objetos_de(modelo) if o.tipo == "caixa_de_texto")


def fora_do_texto(xml: bytes) -> bytes:
    el = etree.fromstring(xml)
    for t in caixas.conteudos(el):
        for f in list(t):
            t.remove(f)
    return etree.tostring(el, method="c14n", exclusive=True)


TABELA_NA_CAIXA = ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid>'
                   '<w:gridCol w:w="2000"/></w:tblGrid><w:tr><w:tc><w:p><w:r><w:t>c</w:t></w:r></w:p>'
                   '</w:tc></w:tr></w:tbl>')


def caixa_com(conteudo: str) -> str:
    """A caixa da fixture com `conteudo` no lugar dos paragrafos (nos dois ramos)."""
    base = fx.caixa_de_texto()
    inicio = base.index("<w:txbxContent>") + len("<w:txbxContent>")
    fim = base.index("</w:txbxContent>")
    paragrafos = base[inicio:fim]
    return base.replace(paragrafos, conteudo)


def testar_analise() -> None:
    secao("analise: o que e' editavel e o que abre so' para leitura")
    modelo, avisos = ler(documento(fx.caixa_de_texto()))
    obj = a_caixa(modelo)
    analise = caixas.analisar(obj, modelo.estilos, modelo.numeracao)
    checa(analise.editavel, "caixa com Choice e Fallback, texto formatado e link: editavel")
    textos = ["".join(r.texto for r in p.runs) for p in analise.blocos]
    checa_igual(textos, ["Texto da caixa", "Segunda linha com link"], "os dois paragrafos da caixa")
    p0 = analise.blocos[0]
    checa(p0.alinhamento == "centro" and p0.runs[0].negrito is True
          and "ligatures" in (p0.runs[0].extras or ""),
          "a formatacao (centralizado, negrito, w14 preservado) vem junto")
    checa(analise.blocos[1].runs[-1].link is not None
          and analise.blocos[1].runs[-1].link.url == "https://exemplo.invalid/caixa",
          "o link da caixa vem com o endereco")
    for nome, conteudo, motivo in (
            ("tabela", TABELA_NA_CAIXA + "<w:p/>", "tabela"),
            ("campo", '<w:p><w:fldSimple w:instr="PAGE"><w:r><w:t>1</w:t></w:r></w:fldSimple></w:p>',
             "campo"),
            ("imagem", "<w:p>" + fx.forma_sem_texto(201) + "</w:p>", "imagem ou forma")):
        m, _ = ler(documento(caixa_com(conteudo)))
        a = caixas.analisar(a_caixa(m), m.estilos, m.numeracao)
        checa(not a.editavel and motivo in a.motivo,
              f"caixa com {nome} dentro: so' leitura, e o motivo diz '{motivo}'")
    forma = next(o for o in objetos_de(ler(fx.docx_com_objetos())[0]) if o.tipo == "forma")
    checa(not caixas.analisar(forma).editavel, "forma sem texto nao e' caixa editavel")
    checa_igual(caixas.analisar(a_caixa(ler(documento(caixa_com(TABELA_NA_CAIXA + "<w:p/>")))[0])).texto,
                "c\n", "o modo so' leitura mostra o texto da caixa")


def testar_regravar() -> None:
    secao("regravar: Choice e Fallback mudam, o resto da forma nao")
    modelo, _ = ler(documento(fx.caixa_de_texto()))
    obj = a_caixa(modelo)
    analise = caixas.analisar(obj, modelo.estilos, modelo.numeracao)
    blocos = copy.deepcopy(analise.blocos)
    blocos[0].runs[0].texto = "Título novo"
    blocos[1].runs.append(Run(" e mais", italico=True))
    blocos.append(Paragrafo(runs=[Run("Terceira linha")]))
    novo = caixas.regravar(obj, blocos, modelo.estilos, modelo.numeracao)
    xml = novo.xml.decode("utf-8")
    el = etree.fromstring(novo.xml)
    escolha = el.find(".//mc:Choice//w:txbxContent", NS)
    reserva = el.find(".//mc:Fallback//w:txbxContent", NS)
    checa("Título novo" in "".join(escolha.itertext()) and "Título novo" in "".join(reserva.itertext()),
          "o texto novo esta' no wps:txbx (Choice) e no v:textbox (Fallback)")
    checa(xml.count("Terceira linha") == 2 and xml.count("Texto da caixa") == 0,
          "o paragrafo novo nos dois ramos; o texto velho em nenhum")
    checa_igual(fora_do_texto(novo.xml), fora_do_texto(obj.xml),
                "fora do w:txbxContent o XML da forma e' identico (posicao, tamanho, cor, VML)")
    checa(novo.resumo.startswith("Título novo"), "o resumo da tela acompanha o texto novo")
    link = [r for r in novo.relacoes if r[1].endswith("/hyperlink")]
    checa(len(link) == 1 and link[0][2] == "https://exemplo.invalid/caixa" and link[0][3],
          "o link continua, numa relacao externa do objeto")
    for r in modelo.paragrafos[0].runs:
        if r.objeto is obj:
            r.objeto = novo
    dados = escrever(modelo)
    checa_igual(ordem.validar(fx.partes_de(dados)), [], "o arquivo gravado passa no validador")
    conferencia.conferir(dados, modelo)
    checa(True, "e na conferencia")
    relido, _ = ler(dados)
    textos = ["".join(r.texto for r in p.runs)
              for p in caixas.analisar(a_caixa(relido), relido.estilos, relido.numeracao).blocos]
    checa_igual(textos, ["Título novo", "Segunda linha com link e mais", "Terceira linha"],
                "reaberto, a caixa tem o texto editado")
    tabela = Tabela(linhas=[Linha(celulas=[Celula(blocos=[Paragrafo(runs=[Run("x")])])])],
                    colunas_tw=[2000])
    try:
        caixas.regravar(obj, [tabela, Paragrafo()], modelo.estilos, modelo.numeracao)
        checa(False, "tabela nos blocos e' recusada (ValueError)")
    except ValueError:
        checa(True, "tabela nos blocos e' recusada (ValueError)")


def testar_tela_e_edicao() -> None:
    secao("tela: a caixa editavel aparece do tamanho dela, com o texto dentro")
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog
    from editdoc.interface import dialogo_caixa
    from editdoc.interface.painel_documento import PainelDocumento
    from editdoc.modelo.unidades import EMU_POR_TWIP
    from editdoc.ponte_qt import de_qt, para_qt
    from editdoc.ponte_qt import opacos as pq_opacos

    modelo, _ = ler(documento(fx.caixa_de_texto()))
    painel = PainelDocumento("Calibri", 11)
    doc = painel.documento_corpo()
    para_qt.preencher(doc, modelo)
    painel.resize(900, 700)
    painel.show()
    drenar_eventos()
    pos = next(p for p in pq_opacos.posicoes_de_opacos(doc)
               if dialogo_caixa.caixa_em(doc, p) is not None)
    cf = dialogo_caixa.caixa_em(doc, pos)
    fmt = None
    from editdoc.ponte_qt import links as pq_links
    fmt = pq_links.formato_em(doc, pos)
    # 0.1.7: a caixa flutuante saiu do fluxo do texto (la' ela era desenhada do tamanho do
    # wp:extent, no ponto da ancora). Agora ela e' pintada na posicao da pagina, e o tamanho
    # dela na folha e' o que se confere; no texto o caractere nao ocupa lugar.
    tam, etiqueta = pq_opacos.tamanho(doc, fmt)
    painel.layout_pag.atualizar_flutuantes()
    postos = painel.layout_pag.flutuantes.postos(0)
    rect = next((pp.rect for pp in postos if pp.posicao == pos), None)
    checa(not etiqueta and rect is not None and abs(rect[2] - 2743200 / EMU_POR_TWIP) < 1
          and rect[3] >= 914400 / EMU_POR_TWIP - 1,
          "a caixa flutuante aparece com a largura do wp:extent e pelo menos a altura")
    caixa = pq_opacos._documento_da_caixa(doc, cf, fmt.property(pq_opacos.PROP_OPACO),
                                          rect[2] if rect else 2743200 / EMU_POR_TWIP)
    checa(caixa is not None and "Texto da caixa" in caixa[0].toPlainText(),
          "o texto da caixa e' composto num documento proprio para a tela")
    m, _ = ler(documento(caixa_com(TABELA_NA_CAIXA + "<w:p/>")))
    from editdoc.ponte_qt.imagens import DocumentoQt
    q = DocumentoQt()
    para_qt.preencher(q, m)
    p2 = pq_opacos.posicoes_de_opacos(q)[0]
    # 0.1.7: a caixa so' de leitura deixou de ser a etiqueta no texto: ela e' pintada na
    # posicao da pagina como a editavel, com o conteudo (aqui, a tabela) dentro. Continua
    # nao editavel (o duplo clique mostra o aviso, conferido em "so' leitura" abaixo).
    from editdoc.ponte_qt import flutuantes as pq_flutuantes
    f2 = pq_links.formato_em(q, p2)
    obj2 = pq_opacos.objeto_de(f2)
    texto2 = pq_flutuantes._texto(q, obj2, f2.property(pq_opacos.PROP_OPACO), 0, 4000.0, True)
    checa(not pq_opacos.tamanho(q, f2)[1] and pq_flutuantes.info(obj2) is not None
          and texto2 is not None and "c" in texto2[0].toPlainText(),
          "a caixa so' de leitura aparece na posicao dela, com o conteudo (a tabela) dentro")

    secao("edicao: duplo clique e Enter abrem o dialogo; confirmar e' um passo de desfazer")
    original = QDialog.exec
    chamadas = []

    def exec_editando(dialogo):
        chamadas.append(dialogo)
        dialogo.show()
        drenar_eventos(2)
        if dialogo.painel is None:
            return QDialog.DialogCode.Accepted
        d = dialogo.painel.documento_corpo()
        from PySide6.QtGui import QTextCursor
        c = QTextCursor(d)
        c.movePosition(QTextCursor.MoveOperation.End)
        c.insertText(" EDITADO")
        dialogo.hide()
        return QDialog.DialogCode.Accepted

    QDialog.exec = exec_editando
    try:
        r = painel.layout_pag.retangulo_cursor(pos)
        r2 = painel.layout_pag.retangulo_cursor(pos + 1)
        m_ = painel.mapa()
        x, y = m_.doc_para_tela((r.x() + r2.x()) / 2, r.y() + r.height() / 2, painel._paginas())
        QTest.mouseDClick(painel.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                          QPoint(round(x), round(y)))
        drenar_eventos()
        checa(len(chamadas) == 1 and chamadas[0].painel is not None,
              "duplo clique na caixa abre o editor do texto")
        novo = pq_opacos.objeto_de(pq_links.formato_em(doc, pos))
        texto = "".join(r.texto for p in caixas.analisar(novo).blocos for r in p.runs)
        checa(texto.endswith("link EDITADO") and novo is not cf,
              "confirmar troca o objeto: o texto editado esta' na caixa")
        painel.undo()
        checa(pq_opacos.objeto_de(pq_links.formato_em(doc, pos)) is cf, "um Ctrl+Z volta a caixa de antes")
        from PySide6.QtGui import QTextCursor
        c = painel.textCursor()
        c.setPosition(pos)
        c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
        painel.setTextCursor(c)
        QTest.keyClick(painel.viewport(), Qt.Key.Key_Return)
        drenar_eventos()
        checa(len(chamadas) == 2 and "EDITADO" in caixas.analisar(
            pq_opacos.objeto_de(pq_links.formato_em(doc, pos))).texto,
              "Enter com a caixa selecionada abre o editor (e nao parte o paragrafo)")
        checa_igual(len(de_qt.extrair(doc).paragrafos), len(modelo.paragrafos),
                    "o Enter nao criou paragrafo")
        q.setModified(False)
        painel_ro = PainelDocumento("Calibri", 11)
        para_qt.preencher(painel_ro.documento_corpo(), m)
        obj_ro = pq_opacos.objeto_de(pq_links.formato_em(painel_ro.documento_corpo(), p2))
        mudou = dialogo_caixa.editar(painel_ro, p2)
        checa(not mudou and chamadas[-1].painel is None
              and pq_opacos.objeto_de(pq_links.formato_em(painel_ro.documento_corpo(), p2)) is obj_ro,
              "a caixa so' de leitura abre o dialogo de leitura e nada muda")
        painel_ro.documento_corpo().setModified(False)
    finally:
        QDialog.exec = original
    texto_aviso = mod_avisos.construir("CAIXA_DE_TEXTO", 3).texto
    checa("pode ser editado" in texto_aviso and "não são editáveis" in texto_aviso
          and not mod_avisos.construir("CAIXA_DE_TEXTO", 3).perde_ao_salvar,
          "o aviso diz que o texto das caixas e' editavel e as formas nao, sem perda")
    doc.setModified(False)
    painel.close()
    drenar_eventos()


def main() -> int:
    if not QT:
        return pular("PySide6 nao instalado")
    testar_analise()
    testar_regravar()
    testar_tela_e_edicao()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
