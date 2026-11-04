"""Formulario do Office (0.1.32): tabelas de cabecalho e de grade com estilos e controles.

Estruturas de um modelo de "tarefas semanais" do Office, geradas por codigo:

- celula cujo primeiro paragrafo tem estilo com propriedade de caractere: o fundo, as bordas,
  o alinhamento vertical e a altura da linha (w:trHeight) da celula aparecem na tela e voltam
  ao arquivo. O Qt guarda o formato da celula no MESMO caractere que o formato de caractere do
  primeiro bloco; trocar este apagava aquele (a 0.1.31 perdia o w:shd ao salvar);
- maiusculas (w:caps), versalete e espacamento do rPr do ESTILO aparecem na tela, e o estilo
  filho com w:caps w:val="0" desliga; o arquivo gravado nao muda;
- a caixa de fonte com o texto sem familia propria mostra a fonte padrao do documento;
- controle de conteudo (w:sdt): o colchete aparece so' no controle do cursor, nunca no de
  aparencia oculta, e todos com as marcas de formatacao ligadas.

Cada verificacao tem contraprova (a sabotagem do conserto e' acusada).
"""

from __future__ import annotations

from ajudantes import checa, checa_igual, drenar_eventos, preparar_qt, resumir, secao
import fixtures_docx as fx

QT = preparar_qt()

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor, QTextDocument  # noqa: E402

from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo.documento import Tabela  # noqa: E402
from editdoc.ponte_qt import de_qt, marcas, para_qt  # noqa: E402

ESTILOS = (
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="Rotulo"><w:name w:val="Rotulo"/>'
    '<w:basedOn w:val="Normal"/><w:rPr><w:b/><w:caps/><w:color w:val="42159D"/>'
    '<w:spacing w:val="20"/><w:sz w:val="16"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="Valor"><w:name w:val="Valor"/>'
    '<w:basedOn w:val="Rotulo"/><w:rPr><w:caps w:val="0"/><w:sz w:val="24"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:customStyle="1" w:styleId="Simples"><w:name w:val="Simples"/>'
    '<w:basedOn w:val="Normal"/><w:rPr><w:smallCaps/></w:rPr></w:style>')


def _p(texto: str, estilo: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{estilo}"/></w:pPr>' if estilo else ""
    return f"<w:p>{ppr}<w:r><w:t>{texto}</w:t></w:r></w:p>"


def _sdt(texto: str, oculto: bool) -> str:
    aparencia = '<w15:appearance w15:val="hidden"/>' if oculto else ""
    return (f'<w:sdt><w:sdtPr><w:id w:val="{7000 + len(texto) + (1 if oculto else 0)}"/>'
            f'{aparencia}</w:sdtPr><w:sdtContent><w:r><w:t>{texto}</w:t></w:r></w:sdtContent>'
            '</w:sdt>')


SEM_BORDAS = ('<w:tblBorders><w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
              '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
              '<w:bottom w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
              '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
              '<w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
              '<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/></w:tblBorders>')

#: Cabecalho: titulo em mescla vertical; rotulo embaixo da linha 1, valor na linha 2.
CABECALHO = (
    f'<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>{SEM_BORDAS}<w:tblLayout w:type="fixed"/>'
    '</w:tblPr><w:tblGrid><w:gridCol w:w="4000"/><w:gridCol w:w="3000"/></w:tblGrid>'
    '<w:tr><w:trPr><w:trHeight w:val="729"/></w:trPr>'
    '<w:tc><w:tcPr><w:tcW w:w="4000" w:type="dxa"/><w:vMerge w:val="restart"/></w:tcPr>'
    f'{_p("Titulo", "Rotulo")}</w:tc>'
    '<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/><w:vAlign w:val="bottom"/></w:tcPr>'
    f'{_p("Nome:", "Rotulo")}</w:tc></w:tr>'
    '<w:tr><w:tc><w:tcPr><w:tcW w:w="4000" w:type="dxa"/><w:vMerge/></w:tcPr><w:p/></w:tc>'
    f'<w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/></w:tcPr>{_p("Fulano", "Valor")}</w:tc>'
    '</w:tr></w:tbl>')


def _celula_grade(texto: str, fundo: str, estilo: str | None, direita: int = 4) -> str:
    return ('<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/><w:tcBorders>'
            '<w:top w:val="single" w:sz="4" w:space="0" w:color="FF2E62"/>'
            f'<w:right w:val="single" w:sz="{direita}" w:space="0" w:color="FF2E62"/>'
            f'</w:tcBorders><w:shd w:val="clear" w:color="auto" w:fill="{fundo}"/></w:tcPr>'
            f'{_p(texto, estilo)}</w:tc>')


#: Grade: a primeira coluna e' o rotulo da linha (estilo com caractere), as outras sem estilo.
GRADE = (
    '<w:tbl><w:tblPr><w:tblW w:w="6000" w:type="dxa"/><w:tblLayout w:type="fixed"/></w:tblPr>'
    '<w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/>'
    '</w:tblGrid>'
    + "".join('<w:tr><w:trPr><w:cantSplit/><w:trHeight w:val="1400"/></w:trPr>'
              + _celula_grade("Classe", "FFABC0", "Rotulo", 18)
              + _celula_grade("texto", "FFD5DF", None)
              + _celula_grade("", "FFD5DF", None) + "</w:tr>" for _ in range(2))
    + "</w:tbl>")

CONTROLES = ("<w:p><w:r><w:t xml:space=\"preserve\">antes </w:t></w:r>" + _sdt("visivel", False)
             + '<w:r><w:t xml:space="preserve"> meio </w:t></w:r>' + _sdt("oculto", True)
             + "<w:r><w:t xml:space=\"preserve\"> fim</w:t></w:r></w:p>")


def formulario() -> bytes:
    dados = fx.docx_com_xml(CABECALHO + _p("") + GRADE + _p("Simples texto", "Simples")
                            + CONTROLES)
    partes = fx.partes_de(dados)
    estilos = partes["word/styles.xml"].decode("utf-8")
    partes["word/styles.xml"] = estilos.replace("</w:styles>", ESTILOS + "</w:styles>").encode()
    doc = partes["word/document.xml"].decode("utf-8")
    if "xmlns:w15=" not in doc:
        doc = doc.replace("<w:document ", '<w:document xmlns:w15="http://schemas.microsoft.com/'
                          'office/word/2012/wordml" ', 1)
    partes["word/document.xml"] = doc.encode("utf-8")
    return fx.montar(partes)


def _tabelas(modelo) -> list[Tabela]:
    return [b for b in modelo.paragrafos if isinstance(b, Tabela)]


def _celulas(modelo) -> list:
    return [(c.sombreamento_hex, c.bordas, c.alinhamento_vertical)
            for t in _tabelas(modelo) for linha in t.linhas for c in linha.celulas]


def _no_qt(modelo) -> QTextDocument:
    doc = QTextDocument()
    para_qt.preencher(doc, modelo)
    return doc


def testar_celula_com_estilo() -> None:
    secao("celula com paragrafo de estilo com caractere: fundo, bordas e alinhamento ficam")
    modelo, _ = ler(formulario())
    doc = _no_qt(modelo)
    cab, grade = doc.rootFrame().childFrames()[:2]
    rotulo = grade.cellAt(0, 0).format().toTableCellFormat()
    checa_igual(rotulo.background().color().name(), "#ffabc0",
                "o fundo da celula do rotulo (paragrafo com estilo de caractere) aparece")
    checa(rotulo.rightBorder() > 2.5, f"a borda direita grossa aparece ({rotulo.rightBorder():.2f})")
    checa_igual(cab.cellAt(0, 1).format().toTableCellFormat().verticalAlignment(),
                QTextCharFormat.VerticalAlignment.AlignBottom,
                "o rotulo do cabecalho fica embaixo da celula (w:vAlign bottom)")
    checa_igual(cab.cellAt(0, 0).rowSpan(), 2, "o titulo continua em mescla vertical")
    volta = de_qt.extrair(doc)
    checa_igual(_celulas(volta), _celulas(modelo),
                "fundo, bordas e alinhamento de todas as celulas voltam do Qt")
    xml = fx.partes_de(escrever(volta))["word/document.xml"].decode("utf-8")
    checa(xml.count('w:fill="FFABC0"') == 2 and xml.count('w:vAlign w:val="bottom"') == 1,
          "o arquivo gravado tem o fundo e o alinhamento (a 0.1.31 os perdia)")
    # Contraprova: sem juntar (trocar o formato do primeiro bloco, como ate' a 0.1.31).
    original = para_qt._comeco_de_celula
    para_qt._comeco_de_celula = lambda cursor: False
    try:
        sabotado = _no_qt(modelo)
    finally:
        para_qt._comeco_de_celula = original
    fmt = sabotado.rootFrame().childFrames()[1].cellAt(0, 0).format().toTableCellFormat()
    checa(fmt.background().style() == Qt.BrushStyle.NoBrush,
          "contraprova: trocando o formato do bloco o fundo some")
    checa(_celulas(de_qt.extrair(sabotado)) != _celulas(modelo),
          "contraprova: e a volta do Qt perde a celula")


def testar_altura_da_linha() -> None:
    secao("altura da linha (w:trHeight) com o rotulo de estilo na primeira celula")
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal

    import os

    def altura_da_grade() -> float:
        j = JanelaPrincipal(configuracao.padrao())
        j.resize(1100, 900)
        j.show()
        drenar_eventos()
        try:
            modelo, avisos = ler(formulario())
            j.carregar(modelo, avisos, None)
            drenar_eventos()
            doc = j.painel.documento_corpo()
            grade = doc.rootFrame().childFrames()[1]
            return doc.documentLayout().frameBoundingRect(grade).height()
        finally:
            j.painel.documento_corpo().setModified(False)
            j.close()
            drenar_eventos()

    altura = altura_da_grade()
    checa(altura >= 2 * 1400 - 2, f"duas linhas de 1400 twips: a grade tem {altura:.0f}")
    # Contraprova no layout do Qt (com o formato da celula apagado, o layout por trechos da
    # 0.1.31 caia ao abrir esta estrutura: docs/SPIKES.md, 0.1.32).
    original = para_qt._comeco_de_celula
    para_qt._comeco_de_celula = lambda cursor: False
    anterior = os.environ.get("EDITDOC_TRECHOS")
    os.environ["EDITDOC_TRECHOS"] = "0"
    try:
        sabotada = altura_da_grade()
    finally:
        para_qt._comeco_de_celula = original
        if anterior is None:
            os.environ.pop("EDITDOC_TRECHOS", None)
        else:
            os.environ["EDITDOC_TRECHOS"] = anterior
    checa(sabotada < 2 * 1000, f"contraprova: sem o formato da celula a linha encolhe ({sabotada:.0f})")


def _formato_do_texto(doc: QTextDocument, texto: str):
    b = doc.begin()
    while b.isValid():
        it = b.begin()
        while not it.atEnd():
            frag = it.fragment()
            it += 1
            if frag.isValid() and frag.text() == texto:
                return frag.charFormat()
        b = b.next()
        if not b.isValid():
            break
    # dentro das tabelas
    for quadro in doc.rootFrame().childFrames():
        cur = QTextCursor(doc)
        for pos in range(quadro.firstPosition(), quadro.lastPosition()):
            cur.setPosition(pos)
            bloco = cur.block()
            it = bloco.begin()
            while not it.atEnd():
                frag = it.fragment()
                it += 1
                if frag.isValid() and frag.text() == texto:
                    return frag.charFormat()
    raise AssertionError(f"trecho {texto!r} nao achado")


def testar_maiusculas_do_estilo() -> None:
    secao("w:caps, w:smallCaps e w:spacing do estilo aparecem na tela; o arquivo nao muda")
    dados = formulario()
    modelo, _ = ler(dados)
    doc = _no_qt(modelo)
    cap = QFont.Capitalization
    titulo = _formato_do_texto(doc, "Titulo")
    checa_igual(titulo.fontCapitalization(), cap.AllUppercase, "o estilo com w:caps: maiusculas")
    checa(abs(titulo.fontLetterSpacing() - 20 / 15) < 1e-6,
          f"e o espacamento de 1 pt do estilo ({titulo.fontLetterSpacing():.3f} px96)")
    checa_igual(_formato_do_texto(doc, "Fulano").fontCapitalization(), cap.MixedCase,
                "o estilo filho com w:caps w:val=\"0\" desliga as maiusculas da base")
    checa_igual(_formato_do_texto(doc, "Simples texto").fontCapitalization(), cap.SmallCaps,
                "w:smallCaps do estilo: versalete")
    checa_igual(_formato_do_texto(doc, " meio ").fontCapitalization(), cap.MixedCase,
                "contraprova: o texto sem estilo fica como esta'")
    gravado = escrever(de_qt.extrair(doc))
    xml = fx.partes_de(gravado)["word/document.xml"].decode("utf-8")
    checa("w:caps" not in xml and "w:smallCaps" not in xml and "w:spacing w:val" not in xml,
          "nada da aparencia do estilo vira formatacao direta no arquivo")
    # Trocar o estilo leva a aparencia junto (maiusculas saem com o estilo Normal).
    from editdoc.ponte_qt import estilos as pq_estilos
    res = pq_estilos.Resolvedor(pq_estilos.catalogo(doc))
    bloco = doc.findBlock(doc.rootFrame().childFrames()[0].cellAt(0, 0).firstPosition())
    cur = QTextCursor(doc)
    cur.beginEditBlock()
    pq_estilos.recompor_blocos(doc, [bloco], res, res, sid_novo=None)
    cur.endEditBlock()
    checa_igual(_formato_do_texto(doc, "Titulo").fontCapitalization(), cap.MixedCase,
                "trocado para o Normal, o titulo perde as maiusculas do estilo")
    # Contraprova: sem a aparencia no catalogo, nada de maiusculas.
    for e in modelo.estilos.itens.values():
        e.aparencia = {}
    checa_igual(_formato_do_texto(_no_qt(modelo), "Titulo").fontCapitalization(), cap.MixedCase,
                "contraprova: sem a aparencia do estilo o titulo fica como no texto")


def testar_fonte_na_caixa() -> None:
    secao("caixa de fonte: texto sem familia propria mostra a fonte padrao do documento")
    from editdoc.edicao import estado
    from editdoc.interface.painel_documento import PainelDocumento

    painel = PainelDocumento("Calibri", 11)
    painel.resize(800, 600)
    painel.show()
    drenar_eventos(2)
    try:
        painel.layout_pag.definir_fonte_padrao("Cambria", 11)
        painel.document().setPlainText("sem familia")
        checa_igual(estado.ler(painel).familia, "Cambria",
                    "o formato vazio mostra a fonte padrao do documento")
        cur = painel.textCursor()
        cur.select(QTextCursor.SelectionType.Document)
        fmt = cur.charFormat()
        fmt.setFontFamilies(["Arial"])
        cur.mergeCharFormat(fmt)
        painel.setTextCursor(cur)
        checa_igual(estado.ler(painel).familia, "Arial",
                    "contraprova: a familia propria do texto vence a padrao")
    finally:
        painel.document().setModified(False)
        painel.close()


def _tinta_de_controle(img) -> int:
    n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            # O colchete (6F8FB5) e' fino: misturado ao branco fica azulado claro; o texto e' preto.
            if c.blue() - c.red() > 20 and c.red() < 240:
                n += 1
    return n


def testar_controle_de_conteudo() -> None:
    secao("controle de conteudo: colchete so' no do cursor, nunca no oculto, todos com as marcas")
    from editdoc.interface.painel_documento import PainelDocumento
    from editdoc.modelo.documento import Documento, Paragrafo

    # O documento so' com o paragrafo dos controles (o w15 vem declarado no formulario).
    modelo, _ = ler(formulario())
    paragrafo = next(p for p in modelo.paragrafos if isinstance(p, Paragrafo)
                     and "".join(r.texto for r in p.runs).startswith("antes"))
    modelo.paragrafos = [paragrafo]
    painel = PainelDocumento("Calibri", 11)
    painel.resize(700, 300)
    painel.show()
    drenar_eventos(2)
    try:
        para_qt.preencher(painel.document(), Documento(paragrafos=[paragrafo],
                                                       estilos=modelo.estilos))
        doc = painel.document()
        texto = doc.begin().text()
        checa(marcas.tem_controles(doc), "o documento sabe que tem controle de conteudo")

        def tinta(pos: int, ligadas: bool = False) -> int:
            cur = painel.textCursor()
            cur.setPosition(pos)
            painel.setTextCursor(cur)
            painel.definir_marcas(ligadas)
            painel.clearFocus()
            drenar_eventos(2)
            return _tinta_de_controle(painel.viewport().grab().toImage())

        dentro = texto.index("visivel") + 2
        no_oculto = texto.index("oculto") + 2
        fora = 2
        checa_igual(marcas.controle_em(doc, fora), None, "fora de controle: nenhum ativo")
        par = marcas.controle_em(doc, dentro)
        checa(par is not None and par[0] < dentro <= par[1], f"o controle do cursor: {par}")
        checa_igual(marcas.controle_em(doc, no_oculto), None,
                    "o controle de aparencia oculta nunca e' o ativo")
        sem = tinta(fora)
        com = tinta(dentro)
        oculto = tinta(no_oculto)
        todas = tinta(fora, ligadas=True)
        checa(sem == 0, f"cursor fora: nenhum colchete ({sem} px)")
        checa(com > 0, f"cursor dentro do controle: o colchete dele aparece ({com} px)")
        checa(oculto == 0, f"cursor no controle oculto: nada aparece ({oculto} px)")
        checa(todas > com, f"marcas de formatacao ligadas: os dois controles aparecem ({todas} px)")
        checa(tinta(fora) == 0, "o cursor saiu: o colchete some de novo (cache refeito)")
        # Contraprova: com o controle sempre ativo o colchete aparece com o cursor fora.
        original = marcas._pintar_conteudo
        marcas._pintar_conteudo = lambda d, p: True
        try:
            painel._limpar_cache()
            checa(tinta(fora) > 0, "contraprova: pintando sempre, o colchete aparece fora")
        finally:
            marcas._pintar_conteudo = original
            painel._limpar_cache()
    finally:
        painel.definir_marcas(False)
        painel.document().setModified(False)
        painel.close()


def main() -> int:
    testar_celula_com_estilo()
    testar_maiusculas_do_estilo()
    if QT:
        testar_altura_da_linha()
        testar_fonte_na_caixa()
        testar_controle_de_conteudo()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
