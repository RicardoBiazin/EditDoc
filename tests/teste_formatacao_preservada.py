"""Formatacao sem perda e controles de conteudo (0.1.5).

- modelo e arquivo: rPr e pPr com o que o modelo nao representa (tabulacoes, bordas de
  paragrafo e de trecho, sombreamento, realce, maiusculas, espacamento, escala, idioma,
  sublinhado duplo, cor de tema, fonte de tema, szCs diferente, w14) e a marca de paragrafo
  voltam ao arquivo identicos (c14n), sem aviso; so' o filho que o esquema nao tem (aviso
  FORMATACAO) e a revisao de formatacao (REVISAO) saem; idempotencia; mudar uma propriedade
  representada troca so' ela; contraprova do validador com extras estragados;
- controles de conteudo: o de bloco (sumario, docPartObj) e o de paragrafo voltam com o
  sdtPr identico; o de bloco numa celula tambem; o de linha de tabela continua achatado com
  aviso; apagar uma ponta grava XML valido com CONTEUDO_INCOMPLETO; w:id repetido e' trocado;
- Qt: ida e volta pelo QTextDocument; a tela aplica realce, maiusculas, espacamento,
  tabulacoes, fundo do paragrafo e entrelinha exata; bordas de paragrafo pintadas
  (contraprova sem borda); digitar herda o rPr, Enter herda o pPr, copiar e colar leva os
  extras, Limpar formatacao os tira, desfazer volta tudo.
"""

from __future__ import annotations

import re

from ajudantes import checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx import propriedades as fx_props  # noqa: E402
from editdoc.formato_docx.erros import ErroDocx  # noqa: E402
from editdoc.formato_docx.escritor import escrever, escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo.documento import (Documento, MarcaConteudo, Paragrafo, Run,  # noqa: E402
                                      Tabela, normalizar, paragrafos_de)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
NS = {"w": W}

PPR = ('<w:pPr><w:keepNext/>'
       '<w:pBdr><w:top w:val="single" w:sz="8" w:space="1" w:color="C00000"/>'
       '<w:left w:val="single" w:sz="8" w:space="4" w:color="C00000"/>'
       '<w:bottom w:val="double" w:sz="6" w:space="1" w:color="auto"/>'
       '<w:right w:val="single" w:sz="8" w:space="4" w:color="C00000"/></w:pBdr>'
       '<w:shd w:val="clear" w:color="auto" w:fill="DDEEFF"/>'
       '<w:tabs><w:tab w:val="left" w:pos="2880"/><w:tab w:val="right" w:leader="dot" w:pos="8000"/>'
       '</w:tabs><w:spacing w:before="120" w:line="360" w:lineRule="exact"/>'
       '<w:ind w:left="720" w:leftChars="300"/><w:jc w:val="start"/>'
       '<w:rPr><w:b/><w:lang w:val="pt-BR"/></w:rPr></w:pPr>')
RPR = (f'<w:rPr><w:rFonts w:asciiTheme="minorHAnsi" w:hAnsiTheme="minorHAnsi"/><w:b/><w:bCs/>'
       '<w:caps/><w:color w:val="1F3864" w:themeColor="accent1" w:themeShade="80"/>'
       '<w:spacing w:val="20"/><w:w w:val="90"/><w:sz w:val="24"/><w:szCs w:val="20"/>'
       '<w:highlight w:val="yellow"/><w:u w:val="double"/>'
       '<w:bdr w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
       '<w:shd w:val="clear" w:color="auto" w:fill="FFF2CC"/><w:lang w:val="pt-BR"/>'
       f'<w14:ligatures xmlns:w14="{W14}" w14:val="standard"/></w:rPr>')
RPR2 = '<w:rPr><w:smallCaps/><w:dstrike/><w:noProof/></w:rPr>'
PERDAS = ('<w:p><w:pPr><w:pPrChange w:id="5" w:author="A"><w:pPr/></w:pPrChange></w:pPr>'
          '<w:r><w:rPr><w:i/><w:xyz/><w:rPrChange w:id="6" w:author="A"><w:rPr/></w:rPrChange>'
          '</w:rPr><w:t>perdas</w:t></w:r></w:p>')
CORPO = (f'<w:p>{PPR}<w:r>{RPR}<w:t xml:space="preserve">Primeiro trecho </w:t></w:r>'
         f'<w:r>{RPR2}<w:t>segundo</w:t></w:r><w:r><w:tab/><w:t>depois da tabulação</w:t></w:r></w:p>'
         + PERDAS)

SDT_BLOCO = ('<w:sdt><w:sdtPr><w:id w:val="77"/><w:docPartObj><w:docPartGallery '
             'w:val="Table of Contents"/><w:docPartUnique/></w:docPartObj></w:sdtPr><w:sdtEndPr/>'
             '<w:sdtContent><w:p><w:r><w:t>Sumário</w:t></w:r></w:p>'
             '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve">'
             ' TOC \\o "1-3" </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>'
             '<w:r><w:t>Item 1</w:t></w:r></w:p>'
             '<w:p><w:r><w:t>Item 2</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
             '</w:sdtContent></w:sdt>')
SDT_RUN = ('<w:p><w:r><w:t xml:space="preserve">Nome: </w:t></w:r><w:sdt><w:sdtPr>'
           '<w:rPr><w:b/></w:rPr><w:alias w:val="Nome"/><w:tag w:val="nome"/><w:id w:val="88"/>'
           '<w:text/></w:sdtPr><w:sdtContent><w:r><w:t>Fulano</w:t></w:r></w:sdtContent></w:sdt>'
           '<w:r><w:t xml:space="preserve"> fim</w:t></w:r></w:p>')
SDT_CELULA = ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid>'
              '<w:gridCol w:w="4000"/></w:tblGrid><w:tr><w:tc><w:tcPr><w:tcW w:w="4000" w:type="dxa"/>'
              '</w:tcPr><w:sdt><w:sdtPr><w:id w:val="99"/><w:richText/></w:sdtPr><w:sdtContent><w:p>'
              '<w:r><w:t>na célula</w:t></w:r></w:p></w:sdtContent></w:sdt></w:tc></w:tr></w:tbl>'
              '<w:p><w:r><w:t>depois da tabela</w:t></w:r></w:p>')
SDT_LINHA = ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid>'
             '<w:gridCol w:w="4000"/></w:tblGrid><w:sdt><w:sdtPr><w:id w:val="55"/></w:sdtPr>'
             '<w:sdtContent><w:tr><w:tc><w:tcPr><w:tcW w:w="4000" w:type="dxa"/></w:tcPr><w:p><w:r>'
             '<w:t>linha</w:t></w:r></w:p></w:tc></w:tr></w:sdtContent></w:sdt></w:tbl>'
             '<w:p><w:r><w:t>fim</w:t></w:r></w:p>')


def codigos(avisos) -> dict:
    return {a.codigo: a.contagem for a in avisos}


def xml_do_corpo(dados: bytes):
    return etree.fromstring(fx.partes_de(dados)["word/document.xml"])


def c14n(el) -> bytes:
    return etree.tostring(el, method="c14n", exclusive=True) if el is not None else b""


def original(xml: str, caminho: str):
    raiz = etree.fromstring(f'<w:body xmlns:w="{W}">{xml}</w:body>')
    return raiz.findall(caminho, NS)


# -- arquivo ------------------------------------------------------------------------------

def testar_arquivo() -> None:
    secao("arquivo: rPr e pPr que o modelo nao representa voltam identicos, sem aviso")
    entrada = fx.docx_com_xml(CORPO)
    modelo, avisos = ler(entrada)
    checa_igual(codigos(avisos), {"FORMATACAO": 1, "REVISAO": 2},
                "so' o filho fora do esquema (FORMATACAO) e a revisao de formatacao (REVISAO) "
                "dao aviso")
    p0 = modelo.paragrafos[0]
    checa(p0.extras is not None and all(n in p0.extras for n in ("pBdr", "tabs", "shd", "keepNext",
                                                                 "leftChars", "lineRule", "start")),
          "pPr: bordas, tabulacoes, sombreamento, keepNext e os detalhes de ind/spacing/jc nos extras")
    r0 = p0.runs[0]
    checa(r0.extras is not None and all(n in r0.extras for n in (
        "highlight", "caps", "w:spacing", "w:w ", "bdr", "shd", "lang", "bCs", "szCs", "themeColor",
        "double", "asciiTheme", "ligatures")),
          "rPr: realce, maiusculas, espacamento, escala, borda, sombreamento, idioma, bCs, szCs, "
          "cor de tema, sublinhado duplo, fonte de tema e w14 nos extras")
    checa(r0.negrito is True and r0.sublinhado is True and r0.cor_hex == "1F3864"
          and r0.tamanho_meio_pt == 24,
          "o que o modelo representa continua nos campos (negrito, sublinhado, cor, tamanho)")
    checa(p0.runs[1].tachado is True and "dstrike" in p0.runs[1].extras,
          "w:dstrike: tachado no modelo e o duplo nos extras")
    dados, avisos_g = escrever_com_avisos(modelo)
    checa(not avisos_g, "gravar nao da' aviso")
    checa_igual(ordem.validar(fx.partes_de(dados)), [], "o validador aceita o arquivo gravado")
    conferencia.conferir(dados, modelo)
    checa(True, "a conferencia aceita o arquivo gravado")
    corpo = xml_do_corpo(dados)
    p_gravado = corpo.find("w:body/w:p", NS)
    checa_igual(c14n(p_gravado.find("w:pPr", NS)), c14n(original(CORPO, "w:p/w:pPr")[0]),
                "pPr gravado identico ao de origem (c14n)")
    runs = p_gravado.findall("w:r", NS)
    checa_igual(c14n(runs[0].find("w:rPr", NS)), c14n(original(CORPO, "w:p/w:r/w:rPr")[0]),
                "rPr do primeiro trecho identico ao de origem (c14n), w14 incluido")
    checa_igual(c14n(runs[1].find("w:rPr", NS)), c14n(original(CORPO, "w:p/w:r/w:rPr")[1]),
                "rPr do segundo trecho (versalete, tachado duplo) identico")
    raiz = fx.partes_de(dados)["word/document.xml"].decode("utf-8")
    checa(re.search(r'mc:Ignorable="[^"]*\bw14\b', raiz) is not None and 'xmlns:w14=' in raiz[:2000],
          "a raiz declara o w14 e o poe no mc:Ignorable")
    perdas = corpo.findall("w:body/w:p", NS)[1]
    checa(perdas.find(".//w:xyz", NS) is None and perdas.find(".//w:rPrChange", NS) is None
          and perdas.find(".//w:pPrChange", NS) is None,
          "o filho fora do esquema e as revisoes de formatacao saem (como os avisos dizem)")

    secao("arquivo: idempotencia e mudanca de uma propriedade representada")
    relido, avisos2 = ler(dados)
    checa(not avisos2, "o arquivo gravado reabre sem aviso nenhum")
    checa_igual(normalizar(relido).paragrafos, normalizar(ler(dados)[0]).paragrafos,
                "releitura estavel")
    checa_igual(escrever(relido), escrever(ler(escrever(relido))[0]),
                "gravar, ler e gravar de novo da' os mesmos bytes")
    checa_igual([r.extras for r in relido.paragrafos[0].runs],
                [r.extras for r in modelo.paragrafos[0].runs], "os extras voltam iguais na releitura")
    relido.paragrafos[0].runs[0].sublinhado = False
    relido.paragrafos[0].runs[0].cor_hex = "00FF00"
    relido.paragrafos[0].alinhamento = "centro"
    rpr = xml_do_corpo(escrever(relido)).find("w:body/w:p/w:r/w:rPr", NS)
    checa(rpr.find("w:u", NS).get(f"{{{W}}}val") == "none",
          "sublinhado desligado: o w:u sai 'none' (o duplo cai)")
    cor = rpr.find("w:color", NS)
    checa(cor.get(f"{{{W}}}val") == "00FF00" and cor.get(f"{{{W}}}themeColor") is None,
          "cor trocada: sai a cor nova, sem o themeColor (o Word usaria o tema)")
    checa(rpr.find("w:highlight", NS) is not None and rpr.find("w:caps", NS) is not None
          and rpr.find("w:szCs", NS).get(f"{{{W}}}val") == "20",
          "o resto do rPr fica como estava")
    ppr = xml_do_corpo(escrever(relido)).find("w:body/w:p/w:pPr", NS)
    checa(ppr.find("w:jc", NS).get(f"{{{W}}}val") == "center" and ppr.find("w:tabs", NS) is not None,
          "alinhamento trocado: so' o jc muda, as tabulacoes ficam")

    secao("contraprova: extras estragados nao passam no validador")
    estragado = Paragrafo(runs=[Run("x", extras=f'<w:rPr xmlns:w="{W}"><w:naoexiste/></w:rPr>')])
    try:
        escrever(Documento(paragrafos=[estragado]))
        checa(False, "o validador recusa um rPr com filho desconhecido nos extras")
    except ErroDocx as erro:
        checa(erro.codigo == "ESCRITA_INVALIDA",
              "o validador recusa um rPr com filho desconhecido nos extras")
    checa(fx_props.canonico("rPr", []) is None, "extras vazios = None")


# -- controles de conteudo --------------------------------------------------------------

def _sdts(dados: bytes) -> list:
    return list(xml_do_corpo(dados).iter(f"{{{W}}}sdt"))


def testar_controles() -> None:
    secao("controles de conteudo: bloco (sumario) e paragrafo voltam com o sdtPr identico")
    entrada = fx.docx_com_xml(SDT_BLOCO + SDT_RUN + SDT_CELULA)
    modelo, avisos = ler(entrada)
    checa("CONTEUDO_CONTROLADO" not in codigos(avisos), "nenhum controle achatado, nenhum aviso")
    marcas = [(r.marca.tipo, r.marca.bloco) for p in paragrafos_de(modelo.paragrafos) for r in p.runs
              if isinstance(r.marca, MarcaConteudo)]
    checa_igual(marcas, [("inicio", True), ("fim", True), ("inicio", False), ("fim", False),
                         ("inicio", True), ("fim", True)],
                "marcas de inicio e fim: o sumario (bloco), o de paragrafo e o da celula")
    dados = escrever(modelo)
    checa_igual(ordem.validar(fx.partes_de(dados)), [], "o validador aceita (celula terminando em sdt)")
    conferencia.conferir(dados, modelo)
    checa(True, "a conferencia aceita")
    origem = etree.fromstring(f'<w:body xmlns:w="{W}">{SDT_BLOCO + SDT_RUN + SDT_CELULA}</w:body>')
    sdts_o = list(origem.iter(f"{{{W}}}sdt"))
    sdts_g = _sdts(dados)
    checa_igual(len(sdts_g), 3, "tres w:sdt no arquivo gravado")
    checa_igual([c14n(s.find("w:sdtPr", NS)) for s in sdts_g], [c14n(s.find("w:sdtPr", NS)) for s in sdts_o],
                "os tres sdtPr identicos aos de origem (c14n)")
    bloco = sdts_g[0]
    checa(bloco.getparent().tag == f"{{{W}}}body"
          and len(bloco.findall("w:sdtContent/w:p", NS)) == 3 and bloco.find("w:sdtEndPr", NS) is not None,
          "o sumario envolve os tres paragrafos inteiros, por fora deles, com o sdtEndPr")
    checa(sdts_g[1].getparent().tag == f"{{{W}}}p"
          and "".join(sdts_g[1].itertext()) == "Fulano",
          "o de paragrafo fica dentro do w:p, com o texto dele")
    checa(sdts_g[2].getparent().tag == f"{{{W}}}tc", "o da celula fica dentro do w:tc")
    relido, avisos2 = ler(dados)
    checa(not avisos2 and list(paragrafos_de(normalizar(relido).paragrafos))
          == list(paragrafos_de(normalizar(modelo).paragrafos)),
          "releitura igual (paragrafos, marcas e extras), sem aviso")

    secao("controles de conteudo: ponta apagada, id repetido, linha de tabela")
    sem_fim = ler(entrada)[0]
    ps = list(paragrafos_de(sem_fim.paragrafos))
    ps[2].runs = [r for r in ps[2].runs if not isinstance(r.marca, MarcaConteudo)]
    dados, avisos_g = escrever_com_avisos(sem_fim)
    checa(codigos(avisos_g).get("CONTEUDO_INCOMPLETO") == 1 and ordem.validar(fx.partes_de(dados)) == []
          and len(_sdts(dados)) == 2,
          "apagar o fim do sumario: o controle sai (o texto fica), XML valido, aviso com perda")
    conferencia.conferir(dados, sem_fim)
    checa(True, "a conferencia aceita o controle desfeito")
    checa(any(a.perde_ao_salvar for a in avisos_g if a.codigo == "CONTEUDO_INCOMPLETO"),
          "CONTEUDO_INCOMPLETO pede confirmacao de perda")
    duplo = ler(fx.docx_com_xml(SDT_RUN + SDT_RUN))[0]
    dados = escrever(duplo)
    ids = [s.find("w:sdtPr/w:id", NS).get(f"{{{W}}}val") for s in _sdts(dados)]
    checa(len(ids) == 2 and len(set(ids)) == 2 and "88" in ids, f"w:id repetido ganha outro numero ({ids})")
    conferencia.conferir(dados, duplo)
    checa(True, "e a conferencia aceita")
    modelo, avisos = ler(fx.docx_com_xml(SDT_LINHA))
    checa(codigos(avisos).get("CONTEUDO_CONTROLADO") == 1 and isinstance(modelo.paragrafos[0], Tabela),
          "controle em volta de linha de tabela: achatado, com aviso (a tabela fica)")


TABELA = ('<w:tbl><w:tblPr><w:tblpPr w:leftFromText="141" w:rightFromText="141" w:vertAnchor="text" '
          'w:tblpY="1"/><w:tblW w:w="0" w:type="auto"/><w:tblCellSpacing w:w="20" w:type="dxa"/>'
          '<w:shd w:val="clear" w:color="auto" w:fill="EEEEEE"/><w:tblCaption w:val="Legenda"/></w:tblPr>'
          '<w:tblGrid><w:gridCol w:w="3000"/></w:tblGrid><w:tr><w:trPr><w:cantSplit/><w:jc w:val="center"/>'
          '</w:trPr><w:tc><w:tcPr><w:tcW w:w="3000" w:type="dxa"/><w:tcMar><w:top w:w="100" w:type="dxa"/>'
          '</w:tcMar><w:textDirection w:val="btLr"/><w:noWrap/></w:tcPr><w:p><w:r><w:t>c</w:t></w:r></w:p>'
          '</w:tc></w:tr></w:tbl><w:p/>')


def testar_tabela() -> None:
    secao("tabela: tblPr, trPr e tcPr que o modelo nao representa voltam (0.1.5)")
    from editdoc.ponte_qt import de_qt, para_qt
    from editdoc.ponte_qt.imagens import DocumentoQt
    modelo, avisos = ler(fx.docx_com_xml(TABELA))
    checa(not codigos(avisos), "tabela flutuante, espacamento, sombreamento, legenda, linha que nao "
                               "se parte e margens e direcao do texto da celula: sem aviso")
    q = DocumentoQt()
    para_qt.preencher(q, modelo)
    volta = de_qt.extrair(q)
    t0, t1 = modelo.paragrafos[0], volta.paragrafos[0]
    checa(t1.extras == t0.extras and t1.linhas[0].extras == t0.linhas[0].extras
          and t1.linhas[0].celulas[0].extras == t0.linhas[0].celulas[0].extras and t0.extras,
          "os extras da tabela, da linha e da celula voltam do Qt iguais")
    corpo = xml_do_corpo(escrever(volta))
    tbl = corpo.find("w:body/w:tbl", NS)
    for caminho in ("w:tblPr/w:tblpPr", "w:tblPr/w:tblCellSpacing", "w:tblPr/w:shd",
                    "w:tblPr/w:tblCaption", "w:tr/w:trPr/w:cantSplit", "w:tr/w:trPr/w:jc",
                    "w:tr/w:tc/w:tcPr/w:tcMar", "w:tr/w:tc/w:tcPr/w:textDirection",
                    "w:tr/w:tc/w:tcPr/w:noWrap"):
        checa_igual(c14n(tbl.find(caminho, NS)), c14n(original(TABELA, "w:tbl/" + caminho)[0]),
                    f"{caminho.split('/')[-1]} identico ao de origem")
    checa_igual(ordem.validar(fx.partes_de(escrever(volta))), [], "o validador aceita (ordem do tblPr)")
    _m, avisos = ler(fx.docx_com_xml(TABELA.replace("<w:cantSplit/>", '<w:gridBefore w:val="1"/><w:cantSplit/>')))
    checa(codigos(avisos).get("FORMATACAO") == 1,
          "contraprova: gridBefore (muda a grade) continua com aviso FORMATACAO")


# -- Qt ---------------------------------------------------------------------------------

def testar_qt() -> None:
    secao("Qt: ida e volta, aparencia na tela")
    from PySide6.QtGui import QFont, QTextBlockFormat, QTextCursor
    from editdoc.ponte_qt import de_qt, para_qt
    from editdoc.ponte_qt import propriedades as pq_props
    from editdoc.ponte_qt.imagens import DocumentoQt

    modelo = ler(fx.docx_com_xml(CORPO + SDT_BLOCO + SDT_RUN))[0]
    q = DocumentoQt()
    para_qt.preencher(q, modelo)
    volta = de_qt.extrair(q)
    a = [(p.extras, [(r.extras, r.marca) for r in p.runs]) for p in paragrafos_de(normalizar(modelo).paragrafos)]
    b = [(p.extras, [(r.extras, r.marca) for r in p.runs]) for p in paragrafos_de(normalizar(volta).paragrafos)]
    checa_igual(b, a, "extras de paragrafo e de trecho e marcas de controle voltam do Qt iguais")
    bloco = q.begin()
    bf = bloco.blockFormat()
    checa(bf.background().color().name() == "#ddeeff", "sombreamento do paragrafo vira o fundo do bloco")
    tabs = bf.tabPositions()
    checa(len(tabs) == 2 and abs(tabs[0].position - (2880 - 720) / 15) < 0.01
          and abs(tabs[1].position - (8000 - 720) / 15) < 0.01,
          "tabulacoes em px96, contadas do recuo esquerdo (medido: o Qt escala x15)")
    checa(bf.lineHeightType() == QTextBlockFormat.LineHeightTypes.FixedHeight.value
          and abs(bf.lineHeight() - 360 / 15) < 0.01, "entrelinha exata vira altura fixa da linha")
    it = bloco.begin()
    cf = it.fragment().charFormat()
    checa(cf.background().color().name() == "#ffff00", "realce amarelo vira o fundo do texto")
    checa(cf.fontCapitalization() == QFont.Capitalization.AllUppercase, "w:caps: maiusculas")
    checa(abs(cf.fontLetterSpacing() - 20 / 15) < 0.01, "w:spacing: espacamento entre letras (twips/15)")
    checa(cf.fontStretch() == 90, "w:w: escala de 90%")

    secao("Qt: bordas de paragrafo pintadas (contraprova sem borda)")
    from PySide6.QtGui import QColor, QImage, QPainter
    from editdoc.interface.layout_paginado import LayoutPaginado

    def tinta(xml: str) -> int:
        doc = ler(fx.docx_com_xml(xml))[0]
        lay = LayoutPaginado(doc.pagina, "Calibri", 11.0)
        para_qt.preencher(lay.doc, doc)
        img = QImage(1200, 400, QImage.Format.Format_RGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.scale(0.1, 0.1)
        pq_props.desenhar(p, lay.doc, None)
        p.end()
        return sum(1 for y in range(0, 400, 2) for x in range(0, 1200, 2)
                   if img.pixelColor(x, y).red() > 150 and img.pixelColor(x, y).green() < 80)
    com = tinta(f'<w:p>{PPR}<w:r><w:t>caixa</w:t></w:r></w:p>')
    sem = tinta('<w:p><w:r><w:t>caixa</w:t></w:r></w:p>')
    checa(com > 20 and sem == 0, f"a borda vermelha aparece ({com} pontos) e sem pBdr nada ({sem})")

    secao("Qt: digitar herda o rPr, Enter herda o pPr, colar leva os extras, limpar tira")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from editdoc.edicao import formatacao as fmt
    from editdoc.interface.painel_documento import PainelDocumento

    painel = PainelDocumento("Calibri", 11)
    doc = painel.documento_corpo()
    para_qt.preencher(doc, ler(fx.docx_com_xml(f'<w:p>{PPR}<w:r>{RPR}<w:t>abc</w:t></w:r></w:p>'))[0])
    painel.show()
    drenar_eventos()
    c = painel.textCursor()
    c.setPosition(3)
    painel.setTextCursor(c)
    QTest.keyClick(painel.viewport(), Qt.Key.Key_X)
    p0 = de_qt.extrair(doc).paragrafos[0]
    checa(p0.runs and p0.runs[0].texto == "abcx" and "highlight" in (p0.runs[0].extras or ""),
          "a letra digitada no fim herda o rPr (realce) do trecho")
    c.setPosition(2)
    painel.setTextCursor(c)
    QTest.keyClick(painel.viewport(), Qt.Key.Key_Return)
    ps = de_qt.extrair(doc).paragrafos
    checa(len(ps) == 2 and ps[0].extras == ps[1].extras and "tabs" in (ps[1].extras or ""),
          "Enter no meio: os dois paragrafos ficam com o mesmo pPr (tabulacoes, bordas)")
    checa(ps[1].runs[0].extras == ps[0].runs[0].extras, "e o trecho partido mantem o rPr")
    painel.undo()
    checa_igual(len(de_qt.extrair(doc).paragrafos), 1, "Ctrl+Z junta de novo")
    c = painel.textCursor()
    c.setPosition(0)
    c.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
    painel.setTextCursor(c)
    painel.copy()
    c.movePosition(QTextCursor.MoveOperation.End)
    painel.setTextCursor(c)
    QTest.keyClick(painel.viewport(), Qt.Key.Key_Return)
    painel.paste()
    ps = de_qt.extrair(doc).paragrafos
    checa(len(ps) == 2 and ps[1].runs and ps[1].runs[0].texto == "abc"
          and ps[1].runs[0].extras == ps[0].runs[0].extras,
          "copiar e colar leva os extras do trecho (o HTML do Qt nao os levaria)")
    QApplication.clipboard().clear()
    c.select(QTextCursor.SelectionType.Document)
    painel.setTextCursor(c)
    fmt.limpar_formatacao(painel)
    ps = de_qt.extrair(doc).paragrafos
    checa(all(r.extras is None for p in ps for r in p.runs), "Limpar formatacao tira os extras do texto")
    cf = doc.begin().begin().fragment().charFormat()
    checa(cf.fontCapitalization() != QFont.Capitalization.AllUppercase
          and cf.background().color().name() != "#ffff00",
          "e a aparencia deles (maiusculas, realce)")
    painel.undo()
    ps = de_qt.extrair(doc).paragrafos
    checa(ps[0].runs and ps[0].runs[0].extras is not None, "Ctrl+Z devolve os extras")
    doc.setModified(False)
    painel.close()
    drenar_eventos()


def main() -> int:
    if not QT:
        return pular("PySide6 nao instalado")
    testar_arquivo()
    testar_controles()
    testar_tabela()
    testar_qt()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
