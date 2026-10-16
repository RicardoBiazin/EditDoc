"""Fidelidade da gravacao (0.1.16): o arquivo salvo reabre com o mesmo layout.

- Arquivo sem styles.xml (o que outros programas geram, so' com o document.xml): o leitor usa o
  docDefaults do Word para esse caso (Times New Roman 10, sem espaco entre paragrafos, entrelinha
  simples) e o escritor grava esse docDefaults. Ate' a 0.1.15 o escritor gravava o do documento
  novo (8 pt depois, 1,08): a imagem da altura da pagina deixava de caber e o arquivo salvo
  reabria com mais paginas. Contraprova: com o escritor antigo, o salvo reabre com outro layout
  (o texto mais baixo, cada bloco com outra entrelinha) e a conferencia recusa o arquivo. Desde
  a 0.1.17 a linha da imagem com entrelinha multipla cresce so' o que o Word cresce (o multiplo
  da linha do texto), entao a imagem continua cabendo e o numero de paginas nao denuncia mais.
- Sem settings.xml, a tabulacao padrao gravada e' a que o leitor supos (720), nao 708.
- Conferencia pos-gravacao: compara a formatacao efetiva (docDefaults, estilo, lista e direta)
  de cada paragrafo, trecho de texto e tabela. Cada sabotagem do XML gravado (docDefaults,
  tamanho de um run, largura de coluna, recuo de paragrafo) e' acusada; o arquivo sem sabotagem
  passa; a formatacao direta igual a do estilo, que o escritor nao grava, passa.
- O custo da conferencia num documento grande fica medido (e limitado).
"""

from __future__ import annotations

import time

from ajudantes import (checa, checa_igual, checa_levanta, drenar_eventos, preparar_qt, pular,
                       resumir, secao)
import fixtures_docx as fx

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from editdoc import configuracao  # noqa: E402
from editdoc.formato_docx import conferencia  # noqa: E402
from editdoc.formato_docx import estilos as fx_estilos  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402
from editdoc.modelo.documento import (Celula, Documento, Linha, Paragrafo, Run,  # noqa: E402
                                      Tabela)
from editdoc.modelo.estilos import CARACTERE_SEM_ESTILOS, PARAGRAFO_SEM_ESTILOS  # noqa: E402
from editdoc.modelo.unidades import twips_de_px  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"

#: Corpo de uma A4 com margens de 2 cm: 16838 - 2 x 1134 twips; em EMU (635 por twip).
CORPO_EMU = (16838 - 2 * 1134) * 635


def _imagem(rid: str, ident: int, cy: int) -> str:
    return (f'<w:p><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="5400000" cy="{cy}"/><wp:docPr id="{ident}" name="Imagem {ident}"/>'
            f'<a:graphic><a:graphicData uri="{PIC}"><pic:pic><pic:nvPicPr>'
            f'<pic:cNvPr id="{ident}" name="f{ident}.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch>'
            f'</pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="5400000" '
            f'cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')


def docx_sem_estilos(linhas: int = 40) -> bytes:
    """Um .docx so' com o document.xml (sem styles.xml, sem settings.xml), como os conversores
    de PDF gravam: uma imagem da altura da pagina, linhas de texto com formatacao direta, uma
    quebra de pagina e outra imagem. Gerado aqui, sem nenhum arquivo real."""
    cy = int(CORPO_EMU * 0.95)  # cabe com entrelinha simples; com 1,08 passa do corpo
    texto = "".join(
        f'<w:p><w:pPr><w:spacing w:after="120"/></w:pPr><w:r><w:rPr>'
        f'<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="14"/></w:rPr>'
        f'<w:t xml:space="preserve">Linha {i} do relatorio convertido</w:t></w:r></w:p>'
        for i in range(linhas))
    corpo = (_imagem("rIdImg1", 1, cy) + texto
             + '<w:p><w:r><w:br w:type="page"/></w:r></w:p>' + _imagem("rIdImg1", 2, cy))
    documento = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 f'<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:wp="{WP}" xmlns:a="{A}" '
                 f'xmlns:pic="{PIC}"><w:body>{corpo}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                 f'<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
                 f'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')
    tipos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" '
             'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Default Extension="png" ContentType="image/png"/>'
             '<Override PartName="/word/document.xml" ContentType="application/'
             'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    rels_doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdImg1" Type="http://schemas.openxmlformats.org/officeDocument/'
                '2006/relationships/image" Target="media/imagem1.png"/></Relationships>')
    return fx.zip_com([("[Content_Types].xml", tipos.encode()), ("_rels/.rels", rels.encode()),
                       ("word/document.xml", documento.encode()),
                       ("word/_rels/document.xml.rels", rels_doc.encode()),
                       ("word/media/imagem1.png", fx.png(20, 30))])


def janela() -> JanelaPrincipal:
    j = JanelaPrincipal(configuracao.padrao())
    j.resize(1100, 900)
    j.show()
    drenar_eventos()
    return j


def fechar(j) -> None:
    j.painel.documento_corpo().setModified(False)
    j.close()
    drenar_eventos()


def abrir(j, dados: bytes) -> int:
    modelo, avisos = ler(dados)
    j.carregar(modelo, avisos, None)
    drenar_eventos()
    return j.painel.layout_pag.numero_paginas()


def fim_do_texto(j) -> float:
    """Onde termina (y, twips) a ultima linha de texto do relatorio convertido."""
    doc = j.painel.documento_corpo()
    dl = doc.documentLayout()
    ultimo = 0.0
    b = doc.begin()
    while b.isValid():
        if b.text().startswith("Linha "):
            ultimo = dl.blockBoundingRect(b).bottom()
        b = b.next()
    return ultimo


def formatos(j) -> list:
    """(margem de baixo, tipo e valor da entrelinha, fonte e tamanho do texto) de cada bloco."""
    doc = j.painel.documento_corpo()
    saida = []
    b = doc.begin()
    while b.isValid():
        f = b.blockFormat()
        saida.append((round(f.bottomMargin(), 2), f.lineHeightType(), round(f.lineHeight(), 2)))
        b = b.next()
    return saida


def testar_arquivo_sem_estilos() -> None:
    secao("arquivo sem styles.xml: o salvo reabre com as mesmas paginas")
    original = docx_sem_estilos()
    partes = fx.partes_de(original)
    checa("word/styles.xml" not in partes and "word/settings.xml" not in partes,
          "a fixture nao tem styles.xml nem settings.xml")
    modelo, _avisos = ler(original)
    checa_igual(modelo.estilos.padrao_paragrafo, PARAGRAFO_SEM_ESTILOS,
                "o leitor usa o docDefaults de paragrafo do Word para esse caso (0, simples)")
    checa_igual(modelo.estilos.padrao_caractere, CARACTERE_SEM_ESTILOS,
                "e o de caractere (Times New Roman 10)")
    j = janela()
    paginas_1 = abrir(j, original)
    checa_igual(paginas_1, 3, "o original abre com 3 paginas (imagem, texto, imagem)")
    fim_do_texto_1 = fim_do_texto(j)
    doc = j.painel.documento_corpo()
    checa_igual((doc.defaultFont().family(), doc.defaultFont().pointSizeF()),
                ("Times New Roman", 10.0), "a fonte do texto sem formatacao e' a do Word")
    checa_igual(twips_de_px(doc.begin().blockFormat().bottomMargin()), 0,
                "o paragrafo da imagem nao ganha espaco depois")
    formatos_1 = formatos(j)
    gravado = escrever(j._modelo_atual())
    partes = fx.partes_de(gravado)
    padroes = docdefaults(gravado)
    checa('w:after="160"' not in padroes and 'w:line="259"' not in padroes,
          "o docDefaults gravado nao traz o espacamento do documento novo")
    checa('w:after="0"' in padroes and 'w:line="240"' in padroes
          and 'w:ascii="Times New Roman"' in padroes and '<w:sz w:val="20"/>' in padroes,
          "o docDefaults gravado e' o que a tela usou (0, 240, Times New Roman 10)")
    conferencia.conferir(gravado, j._modelo_atual())
    checa(True, "a conferencia aceita o arquivo")
    paginas_2 = abrir(j, gravado)
    checa_igual(paginas_2, paginas_1, "o arquivo salvo reabre com as mesmas paginas")
    checa_igual(formatos(j), formatos_1, "e cada bloco com o mesmo espaco e a mesma entrelinha")
    regravado = escrever(j._modelo_atual())
    checa_igual(fx.partes_de(regravado)["word/styles.xml"], partes["word/styles.xml"],
                "a segunda gravacao da' o mesmo styles.xml")

    # Contraprova: o escritor da 0.1.15 (docDefaults do documento novo no arquivo sem styles).
    abrir(j, original)
    esperado = j._modelo_atual()
    base = fx_estilos.xml_base
    fx_estilos.xml_base = lambda fonte, tamanho, _paragrafo=None: base(fonte, tamanho)
    try:
        antigo = escrever(esperado)
    finally:
        fx_estilos.xml_base = base
    checa('w:after="160"' in docdefaults(antigo),
          "contraprova: o escritor antigo grava 8 pt depois")
    checa_levanta(conferencia.FalhaDeConferencia, conferencia.conferir,
                  "contraprova: a conferencia recusa o arquivo do escritor antigo",
                  antigo, esperado)
    abrir(j, antigo)
    # 0.1.17: a imagem da altura da pagina continua cabendo (ver o topo); o que muda e' o texto.
    checa(formatos(j) != formatos_1 and fim_do_texto(j) > fim_do_texto_1 + 100,
          f"contraprova: o arquivo do escritor antigo reabre com outro layout (o texto termina "
          f"em {fim_do_texto(j):.0f} e nao em {fim_do_texto_1:.0f})")
    fechar(j)


def testar_tabulacao_sem_settings() -> None:
    secao("arquivo sem settings.xml: a tabulacao padrao que o leitor supos volta ao arquivo")
    com_lista = fx.bytes_de(fx.documento_com_numeracao_separada())
    sem_settings = fx.sem_parte(com_lista, "word/settings.xml")
    modelo, _ = ler(sem_settings)
    checa_igual(modelo.numeracao.tab_padrao_tw, 720, "sem settings.xml o leitor supoe 720")
    gravado = fx.partes_de(escrever(modelo))["word/settings.xml"].decode("utf-8")
    checa('<w:defaultTabStop w:val="720"/>' in gravado, "e o settings.xml gravado traz 720")
    checa_igual(ler(escrever(modelo))[0].numeracao.tab_padrao_tw, 720, "o relido continua 720")
    modelo, _ = ler(com_lista)
    checa_igual(modelo.numeracao.tab_padrao_tw, 708, "contraprova: com o settings.xml, 708")


def docdefaults(dados: bytes) -> str:
    xml = fx.partes_de(dados)["word/styles.xml"].decode("utf-8")
    return xml[xml.index("<w:docDefaults>"):xml.index("</w:docDefaults>")]


def _sabotar(dados: bytes, parte: str, velho: str, novo: str) -> bytes:
    xml = fx.partes_de(dados)[parte].decode("utf-8")
    assert xml.count(velho) >= 1, velho
    return fx.com_parte(dados, parte, xml.replace(velho, novo, 1).encode("utf-8"))


def documento_formatado() -> Documento:
    def cel(texto):
        return Celula(blocos=[Paragrafo(runs=[Run(texto)])])
    return Documento(paragrafos=[
        Paragrafo(runs=[Run("Titulo", negrito=True, tamanho_meio_pt=32)], espaco_depois_tw=240),
        Paragrafo(runs=[Run("corpo com "), Run("trecho", italico=True, fonte="Arial",
                                                tamanho_meio_pt=20), Run(" no meio")],
                  recuo_esquerdo_tw=360),
        Tabela(colunas_tw=[3000, 4000], linhas=[Linha(celulas=[cel("a"), cel("b")])]),
        Paragrafo(runs=[Run("fim")])])


def testar_conferencia_da_formatacao() -> None:
    secao("conferencia: a formatacao efetiva que muda o layout")
    doc = documento_formatado()
    dados = escrever(doc)
    conferencia.conferir(dados, doc)
    checa(True, "o arquivo sem sabotagem passa")
    lido, _ = ler(dados)
    conferencia.conferir(escrever(lido), lido)
    checa(True, "o relido e regravado tambem passa (formatacao igual a do estilo nao conta)")
    casos = [
        ("word/styles.xml",
         '<w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="259" w:lineRule="auto"/>',
         '<w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>',
         "formatacao do paragrafo", "docDefaults de paragrafo"),
        ("word/document.xml", '<w:sz w:val="20"/>', '<w:sz w:val="22"/>',
         "formatacao do texto", "tamanho de um run"),
        ("word/document.xml", '<w:ind w:left="360"/>', '<w:ind w:left="720"/>',
         "formatacao do paragrafo", "recuo de um paragrafo"),
        ("word/document.xml", '<w:gridCol w:w="4000"/>', '<w:gridCol w:w="4400"/>',
         "formatacao da tabela", "largura de coluna"),
    ]
    for parte, velho, novo, mensagem, nome in casos:
        sabotado = _sabotar(dados, parte, velho, novo)
        try:
            conferencia.conferir(sabotado, doc)
            checa(False, f"sabotagem ({nome}) acusada")
        except conferencia.FalhaDeConferencia as erro:
            checa(mensagem in str(erro), f"sabotagem ({nome}) acusada: {erro}")


def testar_custo() -> None:
    secao("custo da conferencia num documento grande")
    paragrafos = []
    for i in range(3000):
        paragrafos.append(Paragrafo(runs=[Run(f"Paragrafo {i} com "), Run("negrito", negrito=True),
                                          Run(" e texto comum ate' o fim da linha.")]))
    doc = Documento(paragrafos=paragrafos)
    dados = escrever(doc)
    melhor = None
    for _ in range(3):
        inicio = time.perf_counter()
        conferencia.conferir(dados, doc)
        gasto = time.perf_counter() - inicio
        melhor = gasto if melhor is None else min(melhor, gasto)
    print(f"  conferencia de 3000 paragrafos: {melhor * 1000:.0f} ms")
    checa(melhor < 5.0, f"a conferencia de 3000 paragrafos leva menos de 5 s ({melhor:.2f} s)")


def main() -> int:
    testar_arquivo_sem_estilos()
    testar_tabulacao_sem_settings()
    testar_conferencia_da_formatacao()
    testar_custo()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
