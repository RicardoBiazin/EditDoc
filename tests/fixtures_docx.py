"""Fixtures de .docx geradas por codigo. Nenhum .docx real entra no repositorio.

Tudo aqui e' montado em memoria ou em pasta temporaria. Os arquivos hostis
(DOCTYPE, bomba de compressao, nome com ../, OLE, Strict...) saem daqui.
"""

from __future__ import annotations

import io
import struct
import zipfile
import zlib

from editdoc.formato_docx.escritor import escrever
from editdoc.formato_docx.nomes import W_STRICT
from editdoc.modelo.documento import (Borda, BordasCelula, BordasTabela, Celula, Documento, Imagem,
                                      Linha, Paragrafo, Run, Tabela, run_de_imagem)


def documento_completo() -> Documento:
    """Uma amostra de cada recurso que o M2 modela."""
    return Documento(
        titulo="Amostra do EditDoc",
        autor="Teste",
        paragrafos=[
            Paragrafo(runs=[Run("Título: ação, coração, à vista, pão.", negrito=True,
                                tamanho_meio_pt=32, fonte="Arial")],
                      alinhamento="centro", espaco_depois_tw=240),
            Paragrafo(runs=[Run("Negrito ", negrito=True), Run("itálico ", italico=True),
                            Run("sublinhado ", sublinhado=True), Run("tachado", tachado=True)]),
            Paragrafo(runs=[Run("desligado", negrito=False, italico=False, sublinhado=False,
                                tachado=False), Run(" em vermelho", cor_hex="C00000")]),
            Paragrafo(runs=[Run("tamanho 9", tamanho_meio_pt=18),
                            Run(" e 14", tamanho_meio_pt=28, fonte="Courier New")]),
            Paragrafo(runs=[Run("base "), Run("sub", subscrito=True, sobrescrito=False),
                            Run(" base "), Run("sobre", subscrito=False, sobrescrito=True)]),
            Paragrafo(runs=[Run("emoji \U0001F600 fora do plano basico e tab\tdepois")]),
            Paragrafo(runs=[Run("quebra\nde linha dentro do paragrafo")]),
            Paragrafo(runs=[]),
            Paragrafo(runs=[Run("  espaços nas pontas  ")], alinhamento="justificado"),
            Paragrafo(runs=[Run("esquerda")], alinhamento="esquerda"),
            Paragrafo(runs=[Run("direita")], alinhamento="direita"),
            Paragrafo(runs=[Run("recuo de 720 e primeira linha de 360")],
                      recuo_esquerdo_tw=720, recuo_primeira_linha_tw=360),
            Paragrafo(runs=[Run("deslocamento suspenso")], recuo_esquerdo_tw=720,
                      recuo_primeira_linha_tw=-360),
            Paragrafo(runs=[Run("espacamento 120 antes e 60 depois")],
                      espaco_antes_tw=120, espaco_depois_tw=60),
            Paragrafo(runs=[Run("entre linhas 150%")], espacamento_linha_pct=150),
            Paragrafo(runs=[Run("marcador um")], numeracao="marcadores"),
            Paragrafo(runs=[Run("marcador dois")], numeracao="marcadores"),
            Paragrafo(runs=[Run("numero um")], numeracao="numeracao"),
            Paragrafo(runs=[Run("numero dois")], numeracao="numeracao"),
            Paragrafo(runs=[Run("texto depois das listas")]),
            Paragrafo(runs=[Run("numero recomeca")], numeracao="numeracao"),
        ],
    )


def documento_com_formatos_mistos() -> Documento:
    """Runs com None, False e True misturados no mesmo paragrafo."""
    return Documento(paragrafos=[
        Paragrafo(runs=[Run("a"), Run("b", negrito=False), Run("c", negrito=True),
                        Run("d", italico=True), Run("e", italico=False, sublinhado=True)]),
    ])


def documento_com_numeracao_separada() -> Documento:
    """Duas listas numeradas separadas por texto: a segunda recomeca em 1."""
    return Documento(paragrafos=[
        Paragrafo(runs=[Run("a")], numeracao="numeracao"),
        Paragrafo(runs=[Run("b")], numeracao="numeracao"),
        Paragrafo(runs=[Run("meio")]),
        Paragrafo(runs=[Run("c")], numeracao="numeracao"),
    ])


def png(largura: int, altura: int, cor: tuple[int, int, int] = (220, 30, 30)) -> bytes:
    """PNG RGB de uma cor so', montado byte a byte (sem Qt e sem Pillow)."""
    linhas = b"".join(b"\x00" + bytes(cor) * largura for _ in range(altura))

    def pedaco(tipo: bytes, dados: bytes) -> bytes:
        corpo = struct.pack(">I", len(dados)) + tipo + dados
        return corpo + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    cabecalho = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + pedaco(b"IHDR", cabecalho)
            + pedaco(b"IDAT", zlib.compress(linhas)) + pedaco(b"IEND", b""))


def gif(largura: int, altura: int, cor: tuple[int, int, int] = (220, 30, 30)) -> bytes:
    """GIF de uma cor so', montado byte a byte (o Qt le GIF, mas nao grava).

    LZW sem crescer a tabela: um codigo "limpar" antes de cada pixel mantem o codigo
    em 3 bits, o que qualquer decodificador aceita.
    """
    bits = []
    for _ in range(largura * altura):
        bits += [(4, 3), (0, 3)]  # limpar, indice 0
    bits.append((5, 3))  # fim
    acumulado = 0
    n = 0
    saida = bytearray()
    for valor, tamanho in bits:
        acumulado |= valor << n
        n += tamanho
        while n >= 8:
            saida.append(acumulado & 0xFF)
            acumulado >>= 8
            n -= 8
    if n:
        saida.append(acumulado & 0xFF)
    blocos = b"".join(bytes([len(saida[i:i + 255])]) + bytes(saida[i:i + 255])
                      for i in range(0, len(saida), 255))
    return (b"GIF89a" + struct.pack("<HHBBB", largura, altura, 0x80, 0, 0)
            + bytes(cor) + b"\x00\x00\x00"
            + b"\x2c" + struct.pack("<HHHHB", 0, 0, largura, altura, 0)
            + b"\x02" + blocos + b"\x00" + b"\x3b")


def png_declarando(largura: int, altura: int) -> bytes:
    """PNG cujo cabecalho DIZ ter largura x altura, com 1 linha de dados (arquivo hostil)."""
    base = bytearray(png(1, 1))
    base[16:24] = struct.pack(">II", largura, altura)
    crc = zlib.crc32(bytes(base[12:29])) & 0xFFFFFFFF
    base[29:33] = struct.pack(">I", crc)
    return bytes(base)


def imagem(dados: bytes | None = None, largura_cm: float = 4.0, altura_cm: float = 2.0,
           descricao: str = "") -> Imagem:
    dados = dados if dados is not None else png(40, 20)
    return Imagem(dados=dados, formato="png", largura_emu=round(largura_cm * 360000),
                  altura_emu=round(altura_cm * 360000), descricao=descricao)


def _cel(texto: str = "", **kw) -> Celula:
    return Celula(blocos=[Paragrafo(runs=[Run(texto)] if texto else [])], **kw)


def tabela_mesclada() -> Tabela:
    """3 x 3 com mescla horizontal (gridSpan) na 1a linha, vertical (vMerge) na 1a coluna,
    bordas proprias, sombreamento, alinhamento vertical, linha de cabecalho e altura."""
    return Tabela(
        colunas_tw=[3000, 2500, 3500],
        bordas=BordasTabela(sup=Borda("dupla", 8, "C00000"), inf=Borda(), esq=Borda(),
                            dir=Borda(), horizontal=Borda(), vertical=Borda("tracejada", 4)),
        linhas=[
            Linha(cabecalho=True, celulas=[_cel("Título mesclado", colunas=2,
                                                sombreamento_hex="D9E2F3"),
                                           _cel("C1", bordas=BordasCelula(inf=Borda("simples", 12, "0070C0")))]),
            Linha(altura_tw=600, celulas=[_cel("Mescla vertical", mescla_vertical="inicio",
                                               alinhamento_vertical="centro"),
                                          _cel("B2"), _cel("C2")]),
            Linha(celulas=[_cel(mescla_vertical="continua"), _cel("B3"),
                           _cel("C3", alinhamento_vertical="base")]),
        ])


def documento_com_tabela_e_imagem() -> Documento:
    """Amostra do M4: tabela mesclada, tabela aninhada, imagem no texto e na celula."""
    interna = Tabela(colunas_tw=[1200, 1200], linhas=[
        Linha(celulas=[_cel("in1"), _cel("in2")])])
    tabela = tabela_mesclada()
    tabela.linhas[1].celulas[1].blocos.append(interna)
    tabela.linhas[1].celulas[1].blocos.append(Paragrafo())
    tabela.linhas[1].celulas[2].blocos = [Paragrafo(runs=[run_de_imagem(
        imagem(png(30, 30, (30, 120, 220)), 1.5, 1.5, "quadrado azul"))])]
    return Documento(titulo="Amostra M4", autor="Teste", paragrafos=[
        Paragrafo(runs=[Run("Tabelas e imagens", negrito=True, tamanho_meio_pt=32)],
                  alinhamento="centro"),
        Paragrafo(runs=[Run("Imagem na linha: "), run_de_imagem(imagem(descricao="retângulo")),
                        Run(" e o texto continua.")]),
        tabela,
        Paragrafo(runs=[Run("Depois da tabela, uma lista:")]),
        Paragrafo(runs=[Run("item um")], numeracao="marcadores"),
        Paragrafo(runs=[Run("item dois")], numeracao="marcadores"),
    ])


def bytes_de(doc: Documento) -> bytes:
    return escrever(doc)


def zip_com(partes: list[tuple[str, bytes]]) -> bytes:
    """Pacote ZIP com nomes exatamente como dados (inclusive nomes hostis)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for nome, dados in partes:
            # ZipInfo(nome) trocaria '\' por '/' no Windows: o nome bruto e' fixado depois.
            info = zipfile.ZipInfo("x")
            info.filename = nome
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, dados)
    return buf.getvalue()


def partes_de(docx: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        return {n: z.read(n) for n in z.namelist()}


def montar(partes: dict[str, bytes]) -> bytes:
    return zip_com(list(partes.items()))


def com_parte(docx: bytes, nome: str, dados: bytes) -> bytes:
    """O mesmo .docx com uma parte trocada."""
    partes = partes_de(docx)
    partes[nome] = dados
    return montar(partes)


def sem_parte(docx: bytes, nome: str) -> bytes:
    partes = partes_de(docx)
    partes.pop(nome, None)
    return montar(partes)


def docx_hostil() -> dict[str, bytes]:
    """Casos hostis, cada um com o codigo de erro esperado. Gerados aqui, nunca lidos do disco."""
    base = bytes_de(documento_completo())
    doc_xml = partes_de(base)["word/document.xml"]
    laughs = (b'<?xml version="1.0"?>\n<!DOCTYPE lolz [\n'
              b'<!ENTITY lol "lol">\n'
              b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">\n'
              b'<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">\n'
              b']>\n<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              b'<w:body><w:p><w:r><w:t>&lol3;</w:t></w:r></w:p></w:body></w:document>')
    doctype_comum = doc_xml.replace(
        b"<w:document",
        b'<!DOCTYPE w:document [<!ENTITY ext SYSTEM "file:///C:/Windows/win.ini">]>\n<w:document', 1)
    profundo = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                b'<w:body>' + b"<w:sdt><w:sdtContent>" * 300 + b"<w:p/>"
                + b"</w:sdtContent></w:sdt>" * 300 + b"</w:body></w:document>")
    strict = doc_xml.replace(
        b'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"',
        ('xmlns:w="%s"' % W_STRICT).encode("ascii"), 1)
    return {
        "docx_bom": b"isto nao e um zip, so' texto" * 20,
        "ole_doc_antigo": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512,
        "doctype": com_parte(base, "word/document.xml", doctype_comum),
        "billion_laughs": com_parte(base, "word/document.xml", laughs),
        "xml_malformado": com_parte(base, "word/document.xml", b"<w:document><w:body><w:p>"),
        "profundidade": com_parte(base, "word/document.xml", profundo),
        "strict": com_parte(base, "word/document.xml", strict),
        "zip_com_dotdot": zip_com([("[Content_Types].xml", partes_de(base)["[Content_Types].xml"]),
                                   ("../fora.xml", b"<x/>"),
                                   ("word/document.xml", doc_xml)]),
        "barra_invertida": zip_com([("[Content_Types].xml", partes_de(base)["[Content_Types].xml"]),
                                    ("_rels\\.rels", b"<x/>"),
                                    ("word/document.xml", doc_xml)]),
        "bomba_compressao": zip_com([("_rels/.rels", partes_de(base)["_rels/.rels"]),
                                     ("word/document.xml",
                                      doc_xml[:200] + b" " + b"A" * (11 * 1024 * 1024))]),
    }


# -- cabecalho, rodape e campos (M5) ------------------------------------------------

_NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
RT_HEADER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
RT_FOOTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"
CT_HEADER = "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
CT_FOOTER = "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"


def parte_faixa(conteudo: str, raiz: str = "hdr") -> bytes:
    """XML de um cabecalho (hdr) ou rodape (ftr) com o conteudo dado."""
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:{raiz} xmlns:w="{_NS_W}" xmlns:r="{_NS_R}">{conteudo}</w:{raiz}>').encode("utf-8")


def docx_com_xml(corpo_xml: str, sect_xml: str = "", partes_extra: dict | None = None,
                 relacoes_extra=(), tipos_extra=(), settings_extra: str = "") -> bytes:
    """Um .docx valido com o corpo `corpo_xml`, como o Word grava.

    `sect_xml` entra no comeco do sectPr final (headerReference, titlePg vai no fim
    pelo proprio texto). `relacoes_extra`: (rId, tipo, alvo) no document.xml.rels;
    `tipos_extra`: (/parte, tipo de conteudo) no [Content_Types].
    """
    base = bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("x")])]))
    partes = partes_de(base)
    xml = partes["word/document.xml"].decode("utf-8")
    inicio = xml.index("<w:body>") + len("<w:body>")
    fim = xml.index("<w:sectPr>")
    xml = xml[:inicio] + corpo_xml + xml[fim:]
    final = xml.rindex("<w:sectPr>") + len("<w:sectPr>")  # o do fim do corpo
    xml = xml[:final] + sect_xml + xml[final:]
    partes["word/document.xml"] = xml.encode("utf-8")
    rels = partes["word/_rels/document.xml.rels"].decode("utf-8")
    novas = "".join(f'<Relationship Id="{i}" Type="{t}" Target="{a}"/>' for i, t, a in relacoes_extra)
    partes["word/_rels/document.xml.rels"] = rels.replace("</Relationships>",
                                                          novas + "</Relationships>").encode("utf-8")
    ct = partes["[Content_Types].xml"].decode("utf-8")
    novos = "".join(f'<Override PartName="{p}" ContentType="{t}"/>' for p, t in tipos_extra)
    partes["[Content_Types].xml"] = ct.replace("</Types>", novos + "</Types>").encode("utf-8")
    if settings_extra:
        cfg = partes["word/settings.xml"].decode("utf-8")
        marca = '<w:defaultTabStop w:val="708"/>'
        partes["word/settings.xml"] = cfg.replace(marca, marca + settings_extra).encode("utf-8")
    for nome, dados in (partes_extra or {}).items():
        partes[nome] = dados
    return montar(partes)


def campo_complexo(instrucao: str, resultado: str, rpr: str = "") -> str:
    """Runs de um campo complexo como o Word grava (begin, instrText, separate, resultado, end)."""
    r = lambda corpo: f"<w:r>{rpr}{corpo}</w:r>"  # noqa: E731
    return (r('<w:fldChar w:fldCharType="begin"/>')
            + r(f'<w:instrText xml:space="preserve"> {instrucao} </w:instrText>')
            + r('<w:fldChar w:fldCharType="separate"/>')
            + (r(f"<w:t>{resultado}</w:t>") if resultado else "")
            + r('<w:fldChar w:fldCharType="end"/>'))


def documento_com_cabecalhos(paginas_de_texto: int = 110) -> Documento:
    """Amostra do M5: capa (primeira pagina diferente), pares e impares, imagem e tabela no
    cabecalho, "Pagina X de Y" no rodape e campo de pagina no corpo."""
    from editdoc.modelo.pagina import Pagina
    corpo = [Paragrafo(runs=[Run("Cabeçalho e rodapé (M5)", negrito=True, tamanho_meio_pt=32)],
                       alinhamento="centro"),
             Paragrafo(runs=[Run("Esta frase está na página "), Run("1", campo="PAGE"),
                             Run(" de "), Run("4", campo="NUMPAGES"), Run(".")])]
    for i in range(paginas_de_texto):
        corpo.append(Paragrafo(runs=[Run(f"Parágrafo {i + 1}: texto para encher as páginas e "
                                         "mostrar o número de página mudando de folha para folha.")]))
    corpo.append(Paragrafo(runs=[Run("Última página: "), Run("4", campo="PAGE")]))
    tabela = Tabela(colunas_tw=[4513, 4513], linhas=[
        Linha(celulas=[_cel("Relatório"), _cel("Página par")])])
    return Documento(
        titulo="Amostra M5", autor="Teste",
        pagina=Pagina(primeira_diferente=True, pares_impares=True, cabecalho_tw=708, rodape_tw=708),
        paragrafos=corpo,
        cabecalhos={
            "primeira": [Paragrafo(runs=[Run("Capa: sem número de página", italico=True)],
                                   alinhamento="centro")],
            "padrao": [Paragrafo(runs=[run_de_imagem(imagem(png(40, 20, (30, 120, 220)), 1.0, 0.5,
                                                            "logotipo")),
                                       Run("  Cabeçalho das páginas ímpares")],
                                 alinhamento="direita")],
            "par": [tabela],
        },
        rodapes={
            "padrao": [Paragrafo(runs=[Run("Página "), Run("1", campo="PAGE"), Run(" de "),
                                       Run("4", campo="NUMPAGES")], alinhamento="centro")],
            "par": [Paragrafo(runs=[Run("1", campo="PAGE", negrito=True)], alinhamento="esquerda")],
        })


# -- estilos (M6) -------------------------------------------------------------------

_NS_EXTRA = ('xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
             'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
             'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" '
             'mc:Ignorable="w14 w15"')

#: styles.xml no formato que o Word grava: docDefaults com fonte de tema e w14, latentStyles,
#: estilos internos com id em portugues, estilo de caractere ligado, estilo de tabela,
#: estilo com lista (numPr), estilo que o editor nao usa e um filho que o validador recusa.
ESTILOS_DO_WORD = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{_NS_W}" xmlns:r="{_NS_R}" {_NS_EXTRA}>
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:asciiTheme="minorHAnsi" w:eastAsiaTheme="minorHAnsi" w:hAnsiTheme="minorHAnsi" w:cstheme="minorBidi"/><w:kern w:val="2"/><w:sz w:val="24"/><w:szCs w:val="24"/><w:lang w:val="pt-BR" w:eastAsia="en-US" w:bidi="ar-SA"/><w14:ligatures w14:val="standardContextual"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="278" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:latentStyles w:defLockedState="0" w:defUIPriority="99" w:defSemiHidden="0" w:defUnhideWhenUsed="0" w:defQFormat="0" w:count="376"><w:lsdException w:name="Normal" w:uiPriority="0" w:qFormat="1"/><w:lsdException w:name="heading 1" w:uiPriority="9" w:qFormat="1"/><w:lsdException w:name="heading 2" w:semiHidden="1" w:uiPriority="9" w:unhideWhenUsed="1" w:qFormat="1"/><w:lsdException w:name="Title" w:uiPriority="10" w:qFormat="1"/></w:latentStyles>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Ttulo1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:link w:val="Ttulo1Char"/><w:uiPriority w:val="9"/><w:qFormat/><w:rsid w:val="00A1B2C3"/><w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="360" w:after="80"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:rFonts w:asciiTheme="majorHAnsi" w:eastAsiaTheme="majorEastAsia" w:hAnsiTheme="majorHAnsi" w:cstheme="majorBidi"/><w:color w:val="0F4761" w:themeColor="accent1" w:themeShade="BF"/><w:sz w:val="40"/><w:szCs w:val="40"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Ttulo2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="9"/><w:unhideWhenUsed/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="160" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:color w:val="0F4761"/><w:sz w:val="32"/></w:rPr></w:style>
<w:style w:type="character" w:default="1" w:styleId="Fontepargpadro"><w:name w:val="Default Paragraph Font"/><w:uiPriority w:val="1"/><w:semiHidden/><w:unhideWhenUsed/></w:style>
<w:style w:type="table" w:default="1" w:styleId="Tabelanormal"><w:name w:val="Normal Table"/><w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/><w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
<w:style w:type="numbering" w:default="1" w:styleId="Semlista"><w:name w:val="No List"/><w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/></w:style>
<w:style w:type="character" w:customStyle="1" w:styleId="Ttulo1Char"><w:name w:val="Título 1 Char"/><w:basedOn w:val="Fontepargpadro"/><w:link w:val="Ttulo1"/><w:uiPriority w:val="9"/><w:rPr><w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi"/><w:color w:val="0F4761" w:themeColor="accent1" w:themeShade="BF"/><w:sz w:val="40"/></w:rPr></w:style>
<w:style w:type="character" w:customStyle="1" w:styleId="Destaque"><w:name w:val="Destaque"/><w:basedOn w:val="Fontepargpadro"/><w:uiPriority w:val="1"/><w:qFormat/><w:rPr><w:b/><w:color w:val="C00000"/></w:rPr></w:style>
<w:style w:type="paragraph" w:customStyle="1" w:styleId="MeuEstiloRaro"><w:name w:val="Meu Estilo Raro"/><w:basedOn w:val="Normal"/><w:pPr><w:pBdr><w:top w:val="single" w:sz="4" w:space="1" w:color="auto"/></w:pBdr><w:shd w:val="clear" w:color="auto" w:fill="E7E6E6"/><w:spacing w:after="0"/></w:pPr><w:rPr><w:caps/><w:spacing w:val="20"/><w14:shadow w14:blurRad="38100" w14:dist="19050" w14:dir="2700000" w14:sx="100000" w14:sy="100000" w14:kx="0" w14:ky="0" w14:algn="tl"><w14:srgbClr w14:val="000000"/></w14:shadow></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Commarcadores"><w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/><w:uiPriority w:val="99"/><w:unhideWhenUsed/><w:pPr><w:numPr><w:numId w:val="7"/></w:numPr><w:contextualSpacing/></w:pPr></w:style>
<w:style w:type="paragraph" w:customStyle="1" w:styleId="ComRevisao"><w:name w:val="Com Revisao"/><w:basedOn w:val="Normal"/><w:rPr><w:i/><w:rPrChange w:id="1" w:author="Fulano" w:date="2026-01-01T00:00:00Z"><w:rPr/></w:rPrChange></w:rPr></w:style>
<w:style w:type="table" w:styleId="TabeladeGrade1Clara"><w:name w:val="Grid Table 1 Light"/><w:basedOn w:val="Tabelanormal"/><w:uiPriority w:val="46"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="999999"/></w:tblBorders></w:tblPr><w:tblStylePr w:type="firstRow"><w:rPr><w:b/></w:rPr></w:tblStylePr></w:style>
</w:styles>"""

#: Tema com fontes que o EditDoc nao usa por padrao: prova que a fonte de tema e' resolvida.
TEMA_DO_WORD = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office">'
                '<a:themeElements><a:fontScheme name="Office">'
                '<a:majorFont><a:latin typeface="Cambria"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
                '<a:minorFont><a:latin typeface="Garamond"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
                '</a:fontScheme></a:themeElements></a:theme>')

NUMERACAO_DO_WORD = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     f'<w:numbering xmlns:w="{_NS_W}"><w:abstractNum w:abstractNumId="3">'
                     f'<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
                     f'<w:lvlText w:val="•"/></w:lvl></w:abstractNum>'
                     f'<w:num w:numId="7"><w:abstractNumId w:val="3"/></w:num></w:numbering>')

CORPO_COM_ESTILOS = (
    '<w:p><w:pPr><w:pStyle w:val="Ttulo1"/></w:pPr><w:r><w:t>Introdução</w:t></w:r></w:p>'
    '<w:p><w:r><w:t xml:space="preserve">Texto com </w:t></w:r>'
    '<w:r><w:rPr><w:rStyle w:val="Destaque"/></w:rPr><w:t>destaque</w:t></w:r>'
    '<w:r><w:t xml:space="preserve"> no meio.</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Ttulo2"/></w:pPr><w:r><w:t xml:space="preserve">Detalhe </w:t></w:r>'
    '<w:r><w:rPr><w:color w:val="FF0000"/></w:rPr><w:t>vermelho</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Commarcadores"/></w:pPr><w:r><w:t>item da lista</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:outlineLvl w:val="0"/></w:pPr><w:r><w:t>Anexo</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>fim</w:t></w:r></w:p>')

RT_TEMA = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
CT_TEMA = "application/vnd.openxmlformats-officedocument.theme+xml"


def docx_com_estilos_do_word(corpo_xml: str = CORPO_COM_ESTILOS,
                             estilos_xml: str = ESTILOS_DO_WORD) -> bytes:
    """Um .docx com o styles.xml, o tema e a numeracao no formato do Word."""
    return docx_com_xml(corpo_xml, partes_extra={
        "word/styles.xml": estilos_xml.encode("utf-8"),
        "word/numbering.xml": NUMERACAO_DO_WORD.encode("utf-8"),
        "word/theme/theme1.xml": TEMA_DO_WORD.encode("utf-8"),
    }, relacoes_extra=[("rId90", RT_TEMA, "theme/theme1.xml")],
        tipos_extra=[("/word/theme/theme1.xml", CT_TEMA)])

# -- impressao e PDF (M7) -----------------------------------------------------------------

def documento_m7(paginas_de_texto: int = 110):
    """Amostra do M7: a do M5 (capa, pares e impares, imagem e tabela no cabecalho,
    "Pagina X de Y" no rodape, campo no corpo) mais tabela mesclada e imagem no corpo."""
    doc = documento_com_cabecalhos(paginas_de_texto)
    doc.titulo = "Amostra M7: impressão e PDF"
    doc.autor = "Equipe EditDoc"
    extra = documento_com_tabela_e_imagem().paragrafos
    doc.paragrafos[2:2] = [Paragrafo(runs=[Run("Tabela e imagem no corpo, como saem no papel:")]),
                           *extra[1:]]
    return doc


# -- objetos opacos (0.1.2) ----------------------------------------------------------------

#: Namespaces que o Word declara na raiz e que os objetos usam.
NS_OBJETOS = {
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "v": "urn:schemas-microsoft-com:vml",
    "o": "urn:schemas-microsoft-com:office:office",
    "w10": "urn:schemas-microsoft-com:office:word",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}
_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
RT_GRAFICO = _RT + "chart"
RT_PACOTE = _RT + "package"
RT_IMAGEM = _RT + "image"
RT_OLE = _RT + "oleObject"
RT_HIPERLINK = _RT + "hyperlink"
RT_DGM_DADOS = _RT + "diagramData"
RT_DGM_LAYOUT = _RT + "diagramLayout"
RT_DGM_ESTILO = _RT + "diagramQuickStyle"
RT_DGM_CORES = _RT + "diagramColors"
RT_DGM_DESENHO = "http://schemas.microsoft.com/office/2007/relationships/diagramDrawing"
RT_ESTILO_GRAFICO = "http://schemas.microsoft.com/office/2011/relationships/chartStyle"
CT_GRAFICO = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"
CT_ESTILO_GRAFICO = "application/vnd.ms-office.chartstyle+xml"
CT_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CT_OLE = "application/vnd.openxmlformats-officedocument.oleObject"
CT_DGM = "application/vnd.openxmlformats-officedocument.drawingml.diagram"
CT_DGM_DESENHO = "application/vnd.ms-office.drawingml.diagramDrawing+xml"
URI_FORMA = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"


def _quadro(tipo: str, ident: int, uri: str, conteudo: str, cx: int = 2743200, cy: int = 914400,
            ancora_id: str = "") -> str:
    """w:drawing com wp:inline ou wp:anchor em volta de um a:graphicData."""
    extra = f' wp14:anchorId="{ancora_id}"' if ancora_id else ""
    pos = ""
    if tipo == "anchor":
        pos = ('<wp:simplePos x="0" y="0"/><wp:positionH relativeFrom="column"><wp:posOffset>914400'
               '</wp:posOffset></wp:positionH><wp:positionV relativeFrom="paragraph"><wp:posOffset>0'
               '</wp:posOffset></wp:positionV>')
        abre = (f'<wp:anchor distT="0" distB="0" distL="114300" distR="114300" simplePos="0" '
                f'relativeHeight="251659264" behindDoc="0" locked="0" layoutInCell="1" '
                f'allowOverlap="1"{extra}>')
        quebra = '<wp:wrapSquare wrapText="bothSides"/>'
    else:
        abre = f'<wp:inline distT="0" distB="0" distL="0" distR="0"{extra}>'
        quebra = ""
    return (f'<w:drawing>{abre}{pos}<wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:effectExtent l="0" t="0" r="0" b="0"/>{quebra}'
            f'<wp:docPr id="{ident}" name="Objeto {ident}"/><wp:cNvGraphicFramePr/>'
            f'<a:graphic><a:graphicData uri="{uri}">{conteudo}</a:graphicData></a:graphic>'
            f'</wp:{tipo}></w:drawing>')


def _paragrafos_da_caixa(para_ids=("1A2B3C4D", "1A2B3C4E"), extra: str = "") -> str:
    return (f'<w:p w14:paraId="{para_ids[0]}" w14:textId="77777777"><w:pPr><w:jc w:val="center"/>'
            '</w:pPr><w:r><w:rPr><w:b/><w14:ligatures w14:val="standard"/></w:rPr>'
            '<w:t>Texto da caixa</w:t></w:r></w:p>'
            f'<w:p w14:paraId="{para_ids[1]}" w14:textId="77777777"><w:r>'
            '<w:t xml:space="preserve">Segunda linha com </w:t></w:r>'
            f'<w:hyperlink r:id="rId60"><w:r><w:t>link</w:t></w:r></w:hyperlink>{extra}</w:p>')


def caixa_de_texto(ident: int = 101, para_ids=("1A2B3C4D", "1A2B3C4E"),
                   ancora_id: str = "5A1B2C3D", extra: str = "") -> str:
    """Caixa de texto DrawingML flutuante, com o VML de reserva, como o Word grava.

    O w14:paraId dos paragrafos e o anchorId se repetem no Choice e no Fallback, como no
    Word. `extra` entra no fim do segundo paragrafo (dentro dos dois ramos)."""
    paragrafos = _paragrafos_da_caixa(para_ids, extra)
    wsp = ('<wps:wsp><wps:cNvSpPr txBox="1"/><wps:spPr><a:xfrm><a:off x="0" y="0"/>'
           '<a:ext cx="2743200" cy="914400"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/>'
           f'</a:prstGeom></wps:spPr><wps:txbx><w:txbxContent>{paragrafos}</w:txbxContent>'
           '</wps:txbx><wps:bodyPr rot="0" vert="horz" wrap="square" anchor="t"><a:noAutofit/>'
           '</wps:bodyPr></wps:wsp>')
    escolha = _quadro("anchor", ident, URI_FORMA, wsp, ancora_id=ancora_id)
    reserva = ('<w:pict><v:shapetype id="_x0000_t202" coordsize="21600,21600" o:spt="202" '
               'path="m,l,21600r21600,l21600,xe"><v:stroke joinstyle="miter"/>'
               '<v:path gradientshapeok="t" o:connecttype="rect"/></v:shapetype>'
               f'<v:shape id="Caixa {ident}" o:spid="_x0000_s{ident}" type="#_x0000_t202" '
               'style="position:absolute;margin-left:72pt;margin-top:0;width:216pt;height:72pt;'
               f'z-index:251659264" w14:anchorId="{ancora_id}"><v:textbox><w:txbxContent>'
               f'{paragrafos}</w:txbxContent></v:textbox><w10:wrap type="square"/></v:shape></w:pict>')
    return ('<w:r><w:rPr><w:noProof/></w:rPr><mc:AlternateContent><mc:Choice Requires="wps">'
            f'{escolha}</mc:Choice><mc:Fallback>{reserva}</mc:Fallback></mc:AlternateContent></w:r>')


def forma_sem_texto(ident: int = 102) -> str:
    wsp = ('<wps:wsp><wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1828800" cy="0"/>'
           '</a:xfrm><a:prstGeom prst="line"><a:avLst/></a:prstGeom><a:ln w="12700"><a:solidFill>'
           '<a:srgbClr val="C00000"/></a:solidFill></a:ln></wps:spPr><wps:bodyPr/></wps:wsp>')
    # Linha reta: altura zero no wp:extent (o validador aceita na forma, nao na figura).
    return ('<w:r>' + _quadro("anchor", ident, URI_FORMA, wsp, cx=1828800, cy=0,
                              ancora_id="6B2C3D4E") + '</w:r>')


def grupo_de_formas(ident: int = 103) -> str:
    forma = ('<wps:wsp><wps:cNvPr id="{n}" name="R{n}"/><wps:cNvSpPr/><wps:spPr><a:xfrm>'
             '<a:off x="{x}" y="0"/><a:ext cx="457200" cy="457200"/></a:xfrm><a:prstGeom '
             'prst="ellipse"><a:avLst/></a:prstGeom></wps:spPr><wps:bodyPr/></wps:wsp>')
    wgp = ('<wpg:wgp><wpg:cNvGrpSpPr/><wpg:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1371600" '
           'cy="457200"/><a:chOff x="0" y="0"/><a:chExt cx="1371600" cy="457200"/></a:xfrm>'
           '</wpg:grpSpPr>' + forma.format(n=1, x=0) + forma.format(n=2, x=914400) + '</wpg:wgp>')
    return ('<w:r>' + _quadro("inline", ident, "http://schemas.microsoft.com/office/word/2010/"
                              "wordprocessingGroup", wgp, cx=1371600, cy=457200) + '</w:r>')


def grafico(ident: int = 104, rid: str = "rId50") -> str:
    conteudo = (f'<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
                f'r:id="{rid}"/>')
    return '<w:r>' + _quadro("inline", ident, "http://schemas.openxmlformats.org/drawingml/2006/chart",
                             conteudo, cx=5486400, cy=3200400) + '</w:r>'


GRAFICO_XML = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               b'<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
               b'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
               b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
               b'<c:chart><c:plotArea><c:layout/><c:barChart><c:barDir val="col"/>'
               b'<c:grouping val="clustered"/><c:ser><c:idx val="0"/><c:order val="0"/><c:val>'
               b'<c:numRef><c:f>Planilha1!$B$2:$B$3</c:f></c:numRef></c:val></c:ser></c:barChart>'
               b'</c:plotArea></c:chart><c:externalData r:id="rId1"><c:autoUpdate val="0"/>'
               b'</c:externalData></c:chartSpace>')
GRAFICO_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'<Relationship Id="rId1" Type="{RT_PACOTE}" Target="../embeddings/Planilha1.xlsx"/>'
                f'<Relationship Id="rId2" Type="{RT_ESTILO_GRAFICO}" Target="style1.xml"/>'
                '</Relationships>').encode("utf-8")
ESTILO_GRAFICO = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  b'<cs:chartStyle xmlns:cs="http://schemas.microsoft.com/office/drawing/2012/'
                  b'chartStyle" id="201"/>')
#: Nao e' um .xlsx de verdade: o EditDoc nunca abre a planilha, so' a leva junto.
PLANILHA = b"PK\x03\x04 planilha de exemplo do grafico \x00\x01\x02"


def imagem_flutuante(ident: int = 105, rid: str = "rId51") -> str:
    pic = ('<pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="foto.png"/><pic:cNvPicPr/></pic:nvPicPr>'
           f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch>'
           '</pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1440000" cy="720000"/>'
           '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>')
    return '<w:r>' + _quadro("anchor", ident, "http://schemas.openxmlformats.org/drawingml/2006/picture",
                             pic, cx=1440000, cy=720000, ancora_id="7C3D4E5F") + '</w:r>'


def objeto_ole() -> str:
    return ('<w:r><w:object w:dxaOrig="1440" w:dyaOrig="720">'
            '<v:shape id="_x0000_i1025" type="#_x0000_t75" style="width:72pt;height:36pt" o:ole="">'
            '<v:imagedata r:id="rId52" o:title=""/></v:shape>'
            '<o:OLEObject Type="Embed" ProgID="Package" ShapeID="_x0000_i1025" DrawAspect="Icon" '
            'ObjectID="_1700000000" r:id="rId53"/></w:object></w:r>')


EMF = b"\x01\x00\x00\x00" + b"\x00" * 36 + b" EMF" + b"\x00" * 60
OLE_BIN = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 120


def smartart(ident: int = 106) -> str:
    conteudo = ('<dgm:relIds xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" '
                'r:dm="rId54" r:lo="rId55" r:qs="rId56" r:cs="rId57"/>')
    return '<w:r>' + _quadro("inline", ident, "http://schemas.openxmlformats.org/drawingml/2006/diagram",
                             conteudo, cx=5486400, cy=3200400) + '</w:r>'


DGM_DADOS = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             b'<dgm:dataModel xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" '
             b'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
             b'<dgm:ptLst><dgm:pt modelId="{1}" type="doc"/></dgm:ptLst><dgm:extLst>'
             b'<a:ext uri="http://schemas.microsoft.com/office/drawing/2008/diagram">'
             b'<dsp:dataModelExt xmlns:dsp="http://schemas.microsoft.com/office/drawing/2008/diagram" '
             b'relId="rId58" minVer="http://schemas.openxmlformats.org/drawingml/2006/diagram"/>'
             b'</a:ext></dgm:extLst></dgm:dataModel>')
DGM_DESENHO = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               b'<dsp:drawing xmlns:dsp="http://schemas.microsoft.com/office/drawing/2008/diagram"/>')


def _dgm(raiz: str) -> bytes:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<dgm:{raiz} xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram"/>'
            ).encode("utf-8")


def imagem_vinculada(ident: int = 107) -> str:
    pic = ('<pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="vinculada.png"/><pic:cNvPicPr/>'
           '</pic:nvPicPr><pic:blipFill><a:blip r:link="rId59"/><a:stretch><a:fillRect/></a:stretch>'
           '</pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="720000" cy="720000"/>'
           '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>')
    return '<w:r>' + _quadro("inline", ident, "http://schemas.openxmlformats.org/drawingml/2006/picture",
                             pic, cx=720000, cy=720000) + '</w:r>'


EQUACAO_BLOCO = ('<m:oMathPara><m:oMath><m:r><m:t>x</m:t></m:r><m:r><m:t>=</m:t></m:r>'
                 '<m:f><m:num><m:r><m:t>a+b</m:t></m:r></m:num><m:den><m:r><m:t>2</m:t></m:r>'
                 '</m:den></m:f></m:oMath></m:oMathPara>')
EQUACAO_LINHA = ('<m:oMath><m:r><m:t>E=mc</m:t></m:r><m:sSup><m:e/><m:sup><m:r><m:t>2</m:t>'
                 '</m:r></m:sup></m:sSup></m:oMath>')
#: Retangulo VML no cabecalho (marca d agua, faixa lateral), sem relacao nenhuma.
RETANGULO_VML = ('<w:r><w:pict><v:rect id="Faixa" o:spid="_x0000_s2049" style="position:absolute;'
                 'margin-left:0;margin-top:0;width:20pt;height:70pt;z-index:-1" fillcolor="#be003e" '
                 'stroked="f"><w10:wrap anchorx="page"/></v:rect></w:pict></w:r>')

#: Os objetos de `docx_com_objetos`, na ordem do escritor (corpo, cabecalho): (tipo, flutuante).
OBJETOS_ESPERADOS = [("caixa_de_texto", True), ("forma", True), ("grupo", False),
                     ("grafico", False), ("imagem", True), ("objeto", False), ("smartart", False),
                     ("imagem", False), ("equacao", False), ("equacao", False), ("forma", True)]


def _com_namespaces(xml: str, raiz: str) -> str:
    decl = " ".join(f'xmlns:{k}="{v}"' for k, v in NS_OBJETOS.items() if f'xmlns:{k}=' not in xml)
    return xml.replace(f"<w:{raiz} ", f'<w:{raiz} {decl} mc:Ignorable="w14 wp14" ', 1)


def docx_com_corpo_de_objetos(corpo_xml: str, relacoes=(), partes_extra=None, tipos=(), padroes=(),
                              cabecalho_xml: str = "", documento: Documento | None = None) -> bytes:
    """Um .docx com `corpo_xml` no comeco do corpo e os namespaces do Word na raiz.

    O documento de base tem uma imagem do EditDoc (word/media/image1.png) e um cabecalho.
    `relacoes`: (rId, tipo, alvo[, "External"]) no document.xml.rels; `tipos`: Overrides;
    `padroes`: (extensao, tipo) dos Defaults; `cabecalho_xml`: paragrafo a mais no cabecalho.
    """
    doc = documento or Documento(
        paragrafos=[Paragrafo(runs=[Run("Imagem do EditDoc: "), run_de_imagem(imagem(png(40, 20)))]),
                    Paragrafo(runs=[Run("Fim do documento.")])],
        cabecalhos={"padrao": [Paragrafo(runs=[Run("Cabeçalho")])]})
    partes = partes_de(bytes_de(doc))
    xml = _com_namespaces(partes["word/document.xml"].decode("utf-8"), "document")
    inicio = xml.index("<w:body>") + len("<w:body>")
    partes["word/document.xml"] = (xml[:inicio] + corpo_xml + xml[inicio:]).encode("utf-8")
    if cabecalho_xml and "word/header1.xml" in partes:
        cab = _com_namespaces(partes["word/header1.xml"].decode("utf-8"), "hdr")
        partes["word/header1.xml"] = cab.replace("</w:hdr>", cabecalho_xml + "</w:hdr>").encode("utf-8")
    rels = partes["word/_rels/document.xml.rels"].decode("utf-8")
    novas = "".join(
        f'<Relationship Id="{r[0]}" Type="{r[1]}" Target="{r[2]}"'
        + (f' TargetMode="{r[3]}"' if len(r) > 3 else "") + "/>" for r in relacoes)
    partes["word/_rels/document.xml.rels"] = rels.replace("</Relationships>",
                                                          novas + "</Relationships>").encode("utf-8")
    ct = partes["[Content_Types].xml"].decode("utf-8")
    novos = "".join(f'<Default Extension="{e}" ContentType="{t}"/>' for e, t in padroes
                    if f'Extension="{e}"' not in ct)
    novos += "".join(f'<Override PartName="{p}" ContentType="{t}"/>' for p, t in tipos)
    partes["[Content_Types].xml"] = ct.replace("</Types>", novos + "</Types>").encode("utf-8")
    for nome, dados in (partes_extra or {}).items():
        partes[nome] = dados
    return montar(partes)


#: Relacoes, partes e tipos dos objetos de `docx_com_objetos`.
RELACOES_OBJETOS = [
    ("rId50", RT_GRAFICO, "charts/chart1.xml"),
    # A imagem flutuante usa a mesma parte que a imagem do EditDoc (word/media/image1.png):
    # na gravacao as duas disputam o nome.
    ("rId51", RT_IMAGEM, "media/image1.png"),
    ("rId52", RT_IMAGEM, "media/image3.emf"),
    ("rId53", RT_OLE, "embeddings/oleObject1.bin"),
    ("rId54", RT_DGM_DADOS, "diagrams/data1.xml"),
    ("rId55", RT_DGM_LAYOUT, "diagrams/layout1.xml"),
    ("rId56", RT_DGM_ESTILO, "diagrams/quickStyle1.xml"),
    ("rId57", RT_DGM_CORES, "diagrams/colors1.xml"),
    ("rId58", RT_DGM_DESENHO, "diagrams/drawing1.xml"),
    ("rId59", RT_IMAGEM, "http://exemplo.invalid/vinculada.png", "External"),
    ("rId60", RT_HIPERLINK, "https://exemplo.invalid/caixa", "External"),
]
PARTES_OBJETOS = {
    "word/charts/chart1.xml": GRAFICO_XML,
    "word/charts/_rels/chart1.xml.rels": GRAFICO_RELS,
    "word/charts/style1.xml": ESTILO_GRAFICO,
    "word/embeddings/Planilha1.xlsx": PLANILHA,
    "word/media/image3.emf": EMF,
    "word/embeddings/oleObject1.bin": OLE_BIN,
    "word/diagrams/data1.xml": DGM_DADOS,
    "word/diagrams/layout1.xml": _dgm("layoutDef"),
    "word/diagrams/quickStyle1.xml": _dgm("styleDef"),
    "word/diagrams/colors1.xml": _dgm("colorsDef"),
    "word/diagrams/drawing1.xml": DGM_DESENHO,
}
TIPOS_OBJETOS = [("/word/charts/chart1.xml", CT_GRAFICO),
                 ("/word/charts/style1.xml", CT_ESTILO_GRAFICO),
                 ("/word/diagrams/data1.xml", CT_DGM + "Data+xml"),
                 ("/word/diagrams/layout1.xml", CT_DGM + "Layout+xml"),
                 ("/word/diagrams/quickStyle1.xml", CT_DGM + "Style+xml"),
                 ("/word/diagrams/colors1.xml", CT_DGM + "Colors+xml"),
                 ("/word/diagrams/drawing1.xml", CT_DGM_DESENHO)]
PADROES_OBJETOS = [("xlsx", CT_XLSX), ("emf", "image/x-emf"), ("bin", CT_OLE)]


def docx_com_objetos() -> bytes:
    """Um de cada: caixa de texto (DrawingML + VML de reserva, com hiperlink), forma sem
    texto (linha), grupo, grafico (com planilha e estilo), imagem flutuante, objeto OLE,
    SmartArt (com o desenho apontado pelo relId do dataModelExt), imagem vinculada,
    equacao em bloco e na linha, e um retangulo VML no cabecalho."""
    corpo = (
        '<w:p><w:r><w:t xml:space="preserve">Antes da caixa </w:t></w:r>' + caixa_de_texto()
        + '<w:r><w:t xml:space="preserve"> depois da caixa.</w:t></w:r></w:p>'
        + '<w:p><w:r><w:t xml:space="preserve">Forma sem texto: </w:t></w:r>' + forma_sem_texto()
        + '</w:p>'
        + '<w:p>' + grupo_de_formas() + '<w:r><w:t xml:space="preserve"> grupo</w:t></w:r></w:p>'
        + '<w:p><w:r><w:t xml:space="preserve">Gráfico: </w:t></w:r>' + grafico() + '</w:p>'
        + '<w:p>' + imagem_flutuante() + '<w:r><w:t>Texto ao lado da imagem flutuante.</w:t>'
        '</w:r></w:p>'
        + '<w:p><w:r><w:t xml:space="preserve">Objeto OLE: </w:t></w:r>' + objeto_ole() + '</w:p>'
        + '<w:p>' + smartart() + '</w:p>'
        + '<w:p><w:r><w:t xml:space="preserve">Vinculada: </w:t></w:r>' + imagem_vinculada()
        + '</w:p>'
        + '<w:p>' + EQUACAO_BLOCO + '</w:p>'
        + '<w:p><w:r><w:t xml:space="preserve">Equação: </w:t></w:r>' + EQUACAO_LINHA
        + '<w:r><w:t xml:space="preserve"> fim.</w:t></w:r></w:p>')
    return docx_com_corpo_de_objetos(corpo, RELACOES_OBJETOS, PARTES_OBJETOS, TIPOS_OBJETOS,
                                     PADROES_OBJETOS, cabecalho_xml="<w:p>" + RETANGULO_VML + "</w:p>")


# -- partes do pacote, hiperlinks e campos (0.1.3) -----------------------------------------

_RT_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
RT_CUSTOM_XML = _RT_DOC + "customXml"
RT_CUSTOM_XML_PROPS = _RT_DOC + "customXmlProps"
RT_FONTES = _RT_DOC + "fontTable"
RT_FONTE = _RT_DOC + "font"
RT_WEB = _RT_DOC + "webSettings"
RT_NOTAS = _RT_DOC + "footnotes"
RT_NOTAS_FIM = _RT_DOC + "endnotes"
RT_PROPRIEDADES = _RT_DOC + "custom-properties"
RT_MINIATURA = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"
RT_MODELO = _RT_DOC + "attachedTemplate"
CT_CUSTOM_XML_PROPS = "application/vnd.openxmlformats-officedocument.customXmlProperties+xml"
CT_FONTES = "application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"
CT_FONTE = "application/vnd.openxmlformats-officedocument.obfuscatedFont"
CT_WEB = "application/vnd.openxmlformats-officedocument.wordprocessingml.webSettings+xml"
CT_NOTAS = "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
CT_NOTAS_FIM = "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"
CT_PROPRIEDADES = "application/vnd.openxmlformats-officedocument.custom-properties+xml"

_XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
_RELS = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
#: settings.xml como o Word grava: zoom, modelo anexado (relacao externa), rsids, compat com
#: compatSetting, docVars, notas (que citam as separadoras), mathPr e extensoes w14/w15.
SETTINGS_DO_WORD = (
    _XML + f'<w:settings xmlns:w="{_NS_W}" xmlns:r="{_NS_R}" '
    'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
    'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" mc:Ignorable="w14 w15">'
    '<w:zoom w:percent="120"/><w:proofState w:spelling="clean" w:grammar="clean"/>'
    '<w:attachedTemplate r:id="rId1"/>'
    '<w:defaultTabStop w:val="709"/><w:hyphenationZone w:val="425"/>'
    '<w:characterSpacingControl w:val="doNotCompress"/>'
    '<w:footnotePr><w:footnote w:id="-1"/><w:footnote w:id="0"/></w:footnotePr>'
    '<w:endnotePr><w:endnote w:id="-1"/><w:endnote w:id="0"/></w:endnotePr>'
    '<w:compat><w:useFELayout/><w:compatSetting w:name="compatibilityMode" '
    'w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>'
    '<w:docVars><w:docVar w:name="Protocolo" w:val="2026/0042"/></w:docVars>'
    '<w:rsids><w:rsidRoot w:val="00A1B2C3"/><w:rsid w:val="00A1B2C3"/><w:rsid w:val="00D4E5F6"/>'
    '</w:rsids><m:mathPr><m:mathFont m:val="Cambria Math"/></m:mathPr>'
    '<w:themeFontLang w:val="pt-BR"/><w:decimalSymbol w:val=","/><w:listSeparator w:val=";"/>'
    '<w14:docId w14:val="1A2B3C4D"/><w15:docId w15:val="{00000000-0000-0000-0000-000000000042}"/>'
    '</w:settings>')
SETTINGS_RELS = (_XML + _RELS + f'<Relationship Id="rId1" Type="{RT_MODELO}" '
                 'Target="file:///C:/Modelos/Oficio.dotx" TargetMode="External"/></Relationships>')
FONTES_DO_WORD = (_XML + f'<w:fonts xmlns:w="{_NS_W}" xmlns:r="{_NS_R}">'
                  '<w:font w:name="Calibri"><w:panose1 w:val="020F0502020204030204"/>'
                  '<w:charset w:val="00"/><w:family w:val="swiss"/><w:pitch w:val="variable"/></w:font>'
                  '<w:font w:name="Fonte Embutida"><w:charset w:val="00"/>'
                  '<w:embedRegular r:id="rId1" w:fontKey="{11111111-2222-3333-4444-555555555555}"/>'
                  '</w:font></w:fonts>')
FONTES_RELS = (_XML + _RELS + f'<Relationship Id="rId1" Type="{RT_FONTE}" '
               'Target="fonts/font1.odttf"/></Relationships>')
FONTE_EMBUTIDA = b"\x00\x01\x00\x00 fonte ofuscada de exemplo \xfe\xff" * 4
WEB_DO_WORD = (_XML + f'<w:webSettings xmlns:w="{_NS_W}"><w:optimizeForBrowser/>'
               '<w:allowPNG/></w:webSettings>')
NOTAS_SEPARADORAS = (_XML + f'<w:footnotes xmlns:w="{_NS_W}" xmlns:r="{_NS_R}">'
                     '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p>'
                     '</w:footnote><w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r>'
                     '<w:continuationSeparator/></w:r></w:p></w:footnote></w:footnotes>')
NOTAS_FIM_COM_REAL = (_XML + f'<w:endnotes xmlns:w="{_NS_W}" xmlns:r="{_NS_R}">'
                      '<w:endnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p>'
                      '</w:endnote><w:endnote w:type="continuationSeparator" w:id="0"><w:p><w:r>'
                      '<w:continuationSeparator/></w:r></w:p></w:endnote>'
                      '<w:endnote w:id="1"><w:p><w:r><w:t>Nota de fim de verdade.</w:t></w:r></w:p>'
                      '</w:endnote></w:endnotes>')
ITEM_CUSTOM_XML = (_XML + '<p:properties xmlns:p="http://schemas.microsoft.com/office/2006/metadata/'
                   'properties"><documentManagement><Setor>Faturamento</Setor></documentManagement>'
                   '</p:properties>')
ITEM_PROPS = (_XML + '<ds:datastoreItem ds:itemID="{AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE}" '
              'xmlns:ds="http://schemas.openxmlformats.org/officeDocument/2006/customXml">'
              '<ds:schemaRefs><ds:schemaRef ds:uri="http://schemas.microsoft.com/office/2006/'
              'metadata/properties"/></ds:schemaRefs></ds:datastoreItem>')
ITEM_RELS = (_XML + _RELS + f'<Relationship Id="rId1" Type="{RT_CUSTOM_XML_PROPS}" '
             'Target="itemProps1.xml"/></Relationships>')
PROPRIEDADES = (_XML + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
                'custom-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/'
                'docPropsVTypes"><property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" '
                'name="Cliente"><vt:lpwstr>Hospital Exemplo</vt:lpwstr></property></Properties>')
CORE_DO_WORD = (_XML + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
                'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>Relatório</dc:title>'
                '<dc:subject>Assunto do relatório</dc:subject><dc:creator>Fulana</dc:creator>'
                '<cp:keywords>faturamento; 2026</cp:keywords><cp:lastModifiedBy>Beltrano</cp:lastModifiedBy>'
                '<cp:revision>7</cp:revision><dcterms:created xsi:type="dcterms:W3CDTF">'
                '2026-01-02T03:04:00Z</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">'
                '2026-02-03T04:05:00Z</dcterms:modified><cp:category>Interno</cp:category>'
                '</cp:coreProperties>')
APP_DO_WORD = (_XML + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
               'extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/'
               'docPropsVTypes"><Template>Normal.dotm</Template><TotalTime>42</TotalTime>'
               '<Pages>1</Pages><Application>Microsoft Office Word</Application>'
               '<Company>Empresa Exemplo</Company><Manager>Gerente</Manager>'
               '<AppVersion>16.0000</AppVersion></Properties>')
MINIATURA = b"\xff\xd8\xff\xe0 miniatura jpeg de exemplo \xff\xd9"


def docx_com_pacote_do_word(corpo_xml: str = "<w:p><w:r><w:t>Texto.</w:t></w:r></w:p>",
                            notas_fim: str = NOTAS_FIM_COM_REAL, extra=None) -> bytes:
    """Um .docx com as partes que o Word grava e que o EditDoc nao edita: customXml (item,
    itemProps e relacoes), docProps/custom.xml, fontTable com fonte embutida, webSettings,
    notas (separadoras e uma nota de fim de verdade), settings.xml do Word (com relacao
    externa para o modelo), core.xml e app.xml do Word, e a miniatura. `extra`: partes a
    trocar (None tira a parte)."""
    partes = partes_de(bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("x")])])))
    xml = partes["word/document.xml"].decode("utf-8")
    inicio = xml.index("<w:body>") + len("<w:body>")
    fim = xml.index("<w:sectPr>")
    partes["word/document.xml"] = (xml[:inicio] + corpo_xml + xml[fim:]).encode("utf-8")
    rels = partes["word/_rels/document.xml.rels"].decode("utf-8")
    novas = "".join(f'<Relationship Id="{i}" Type="{t}" Target="{a}"/>' for i, t, a in (
        ("rId80", RT_CUSTOM_XML, "../customXml/item1.xml"), ("rId81", RT_FONTES, "fontTable.xml"),
        ("rId82", RT_WEB, "webSettings.xml"), ("rId83", RT_NOTAS, "footnotes.xml"),
        ("rId84", RT_NOTAS_FIM, "endnotes.xml")))
    partes["word/_rels/document.xml.rels"] = rels.replace(
        "</Relationships>", novas + "</Relationships>").encode("utf-8")
    pacote = partes["_rels/.rels"].decode("utf-8")
    pacote = pacote.replace(
        "</Relationships>",
        f'<Relationship Id="rId8" Type="{RT_PROPRIEDADES}" Target="docProps/custom.xml"/>'
        f'<Relationship Id="rId9" Type="{RT_MINIATURA}" Target="docProps/thumbnail.jpeg"/>'
        "</Relationships>")
    partes["_rels/.rels"] = pacote.encode("utf-8")
    ct = partes["[Content_Types].xml"].decode("utf-8")
    novos = ('<Default Extension="jpeg" ContentType="image/jpeg"/>'
             '<Default Extension="odttf" ContentType="' + CT_FONTE + '"/>'
             + "".join(f'<Override PartName="{p}" ContentType="{t}"/>' for p, t in (
                 ("/customXml/itemProps1.xml", CT_CUSTOM_XML_PROPS), ("/word/fontTable.xml", CT_FONTES),
                 ("/word/webSettings.xml", CT_WEB), ("/word/footnotes.xml", CT_NOTAS),
                 ("/word/endnotes.xml", CT_NOTAS_FIM), ("/docProps/custom.xml", CT_PROPRIEDADES))))
    partes["[Content_Types].xml"] = ct.replace("</Types>", novos + "</Types>").encode("utf-8")
    partes.update({
        "word/settings.xml": SETTINGS_DO_WORD.encode("utf-8"),
        "word/_rels/settings.xml.rels": SETTINGS_RELS.encode("utf-8"),
        "word/fontTable.xml": FONTES_DO_WORD.encode("utf-8"),
        "word/_rels/fontTable.xml.rels": FONTES_RELS.encode("utf-8"),
        "word/fonts/font1.odttf": FONTE_EMBUTIDA,
        "word/webSettings.xml": WEB_DO_WORD.encode("utf-8"),
        "word/footnotes.xml": NOTAS_SEPARADORAS.encode("utf-8"),
        "word/endnotes.xml": notas_fim.encode("utf-8"),
        "customXml/item1.xml": ITEM_CUSTOM_XML.encode("utf-8"),
        "customXml/itemProps1.xml": ITEM_PROPS.encode("utf-8"),
        "customXml/_rels/item1.xml.rels": ITEM_RELS.encode("utf-8"),
        "docProps/custom.xml": PROPRIEDADES.encode("utf-8"),
        "docProps/core.xml": CORE_DO_WORD.encode("utf-8"),
        "docProps/app.xml": APP_DO_WORD.encode("utf-8"),
        "docProps/thumbnail.jpeg": MINIATURA,
    })
    for nome, dados in (extra or {}).items():
        if dados is None:
            partes.pop(nome, None)
        else:
            partes[nome] = dados
    return montar(partes)


#: Estilos do Word com o estilo de caractere "Hyperlink" (azul sublinhado).
ESTILOS_COM_LINK = ESTILOS_DO_WORD.replace(
    "</w:styles>",
    '<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/>'
    '<w:basedOn w:val="Fontepargpadro"/><w:uiPriority w:val="99"/><w:unhideWhenUsed/>'
    '<w:rPr><w:color w:val="0563C1" w:themeColor="hyperlink"/><w:u w:val="single"/></w:rPr>'
    '</w:style></w:styles>')
RT_LINK = _RT_DOC + "hyperlink"


def _link_externo(rid: str, texto: str, extra: str = "") -> str:
    return (f'<w:hyperlink r:id="{rid}" w:history="1"{extra}><w:r><w:rPr><w:rStyle w:val="Hyperlink"/>'
            f'</w:rPr><w:t>{texto}</w:t></w:r></w:hyperlink>')


#: Corpo com link externo, link interno para marcador, marcador entre paragrafos, link com
#: dica e quadro, e link de e-mail.
CORPO_COM_LINKS = (
    '<w:p><w:r><w:t xml:space="preserve">Veja o </w:t></w:r>' + _link_externo("rId70", "site")
    + '<w:r><w:t xml:space="preserve"> e a </w:t></w:r>'
    '<w:hyperlink w:anchor="Conclusao" w:history="1"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/>'
    '</w:rPr><w:t>conclusão</w:t></w:r></w:hyperlink><w:r><w:t>.</w:t></w:r></w:p>'
    '<w:p>' + _link_externo("rId71", "dica", ' w:tooltip="Dica do link" w:tgtFrame="_blank"')
    + '<w:r><w:t xml:space="preserve"> e </w:t></w:r>' + _link_externo("rId72", "e-mail") + '</w:p>'
    '<w:bookmarkStart w:id="7" w:name="Entre"/><w:bookmarkEnd w:id="7"/>'
    '<w:p><w:bookmarkStart w:id="3" w:name="Conclusao"/><w:r><w:t>Conclusão</w:t></w:r>'
    '<w:bookmarkEnd w:id="3"/><w:r><w:t xml:space="preserve"> do texto.</w:t></w:r></w:p>')
RELACOES_LINKS = [("rId70", RT_LINK, "https://exemplo.invalid/pagina?a=1&amp;b=2", "External"),
                  ("rId71", RT_LINK, "https://exemplo.invalid/dica", "External"),
                  ("rId72", RT_LINK, "mailto:fulano@exemplo.invalid", "External")]


def docx_com_links(corpo_xml: str = CORPO_COM_LINKS, relacoes=None) -> bytes:
    """.docx com hiperlinks externos e internos, marcadores e o estilo Hyperlink."""
    partes = partes_de(docx_com_estilos_do_word(corpo_xml, ESTILOS_COM_LINK))
    rels = partes["word/_rels/document.xml.rels"].decode("utf-8")
    novas = "".join(f'<Relationship Id="{r[0]}" Type="{r[1]}" Target="{r[2]}" TargetMode="{r[3]}"/>'
                    for r in (RELACOES_LINKS if relacoes is None else relacoes))
    partes["word/_rels/document.xml.rels"] = rels.replace(
        "</Relationships>", novas + "</Relationships>").encode("utf-8")
    return montar(partes)


def _fld(tipo: str) -> str:
    return f'<w:r><w:fldChar w:fldCharType="{tipo}"/></w:r>'


def _instr(texto: str) -> str:
    return f'<w:r><w:instrText xml:space="preserve">{texto}</w:instrText></w:r>'


def _linha_do_sumario(ancora: str, titulo: str, pagina: str) -> str:
    return (f'<w:hyperlink w:anchor="{ancora}" w:history="1"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/>'
            f'</w:rPr><w:t>{titulo}</w:t></w:r><w:r><w:tab/></w:r>' + _fld("begin")
            + _instr(f" PAGEREF {ancora} \\h ") + _fld("separate")
            + f"<w:r><w:t>{pagina}</w:t></w:r>" + _fld("end") + "</w:hyperlink>")


#: Sumario (TOC) de tres paragrafos, com hiperlinks e PAGEREF dentro; os titulos com os
#: marcadores; REF, DATE (sujo), campo simples (AUTHOR), IF com PAGE no codigo, XE sem
#: resultado e um campo de formulario (FORMTEXT com w:ffData).
CORPO_COM_CAMPOS = (
    '<w:p>' + _fld("begin") + _instr(' TOC \\o "1-3" \\h \\z \\u ') + _fld("separate")
    + _linha_do_sumario("_Toc1", "Introdução", "1") + '</w:p>'
    '<w:p>' + _linha_do_sumario("_Toc2", "Conclusão", "2") + '</w:p>'
    '<w:p>' + _fld("end") + '</w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Ttulo1"/></w:pPr><w:bookmarkStart w:id="1" w:name="_Toc1"/>'
    '<w:r><w:t>Introdução</w:t></w:r><w:bookmarkEnd w:id="1"/></w:p>'
    '<w:p><w:r><w:t xml:space="preserve">Ver </w:t></w:r>' + _fld("begin")
    + _instr(" REF _Toc2 \\h ") + _fld("separate") + '<w:r><w:t>Conclusão</w:t></w:r>' + _fld("end")
    + '<w:r><w:t xml:space="preserve">, em </w:t></w:r>'
    '<w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>' + _instr(' DATE \\@ "dd/MM/yyyy" ')
    + _fld("separate") + '<w:r><w:t>12/10/2026</w:t></w:r>' + _fld("end")
    + '<w:r><w:t xml:space="preserve">, por </w:t></w:r>'
    '<w:fldSimple w:instr=" AUTHOR \\* MERGEFORMAT "><w:r><w:t>Fulana</w:t></w:r></w:fldSimple>'
    '<w:r><w:t>.</w:t></w:r></w:p>'
    '<w:p>' + _fld("begin") + _instr(" IF ") + _fld("begin") + _instr(" PAGE ") + _fld("separate")
    + '<w:r><w:t>1</w:t></w:r>' + _fld("end") + _instr(' = 1 "capa" "miolo" ') + _fld("separate")
    + '<w:r><w:t>capa</w:t></w:r>' + _fld("end")
    + '<w:r><w:t xml:space="preserve"> índice</w:t></w:r>' + _fld("begin")
    + _instr(' XE "Índice" ') + _fld("end") + '</w:p>'
    '<w:p><w:r><w:t xml:space="preserve">Nome: </w:t></w:r><w:r><w:fldChar w:fldCharType="begin">'
    '<w:ffData><w:name w:val="Texto1"/><w:enabled/><w:calcOnExit w:val="0"/><w:textInput/></w:ffData>'
    '</w:fldChar></w:r>' + _instr(" FORMTEXT ") + _fld("separate")
    + '<w:r><w:t>preencha</w:t></w:r>' + _fld("end") + '</w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Ttulo1"/></w:pPr><w:bookmarkStart w:id="2" w:name="_Toc2"/>'
    '<w:r><w:t>Conclusão</w:t></w:r><w:bookmarkEnd w:id="2"/></w:p>')


def docx_com_campos(corpo_xml: str = CORPO_COM_CAMPOS) -> bytes:
    """.docx com o sumario e os campos de CORPO_COM_CAMPOS (e o estilo Hyperlink)."""
    return docx_com_links(corpo_xml, relacoes=[])


# -- notas de rodape e de fim (0.1.10) ------------------------------------------------------

RT_NOTAS_RODAPE = _RT_DOC + "footnotes"
_ESTILOS_NOTAS = (
    '<w:style w:type="paragraph" w:styleId="Textodenotaderodap"><w:name w:val="footnote text"/>'
    '<w:basedOn w:val="Normal"/><w:link w:val="TextodenotaderodapChar"/><w:uiPriority w:val="99"/>'
    '<w:semiHidden/><w:unhideWhenUsed/><w:pPr><w:spacing w:after="0" w:line="240" '
    'w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>'
    '<w:style w:type="character" w:customStyle="1" w:styleId="TextodenotaderodapChar">'
    '<w:name w:val="Texto de nota de rodapé Char"/><w:basedOn w:val="Fontepargpadro"/>'
    '<w:link w:val="Textodenotaderodap"/><w:uiPriority w:val="99"/><w:semiHidden/>'
    '<w:rPr><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>'
    '<w:style w:type="character" w:styleId="Refdenotaderodap"><w:name w:val="footnote reference"/>'
    '<w:basedOn w:val="Fontepargpadro"/><w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/>'
    '<w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Textodenotadefim"><w:name w:val="endnote text"/>'
    '<w:basedOn w:val="Normal"/><w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/>'
    '<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
    '<w:rPr><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>'
    '<w:style w:type="character" w:styleId="Refdenotadefim"><w:name w:val="endnote reference"/>'
    '<w:basedOn w:val="Fontepargpadro"/><w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/>'
    '<w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>')
ESTILOS_COM_NOTAS = ESTILOS_DO_WORD.replace("</w:styles>", _ESTILOS_NOTAS + "</w:styles>")


def ref_nota(ident: int, tipo: str = "footnote", personalizada: str = "") -> str:
    """O run da referencia como o Word grava; `personalizada`: o simbolo (customMarkFollows)."""
    estilo = "Refdenotaderodap" if tipo == "footnote" else "Refdenotadefim"
    if personalizada:
        return (f'<w:r><w:rPr><w:rStyle w:val="{estilo}"/></w:rPr><w:{tipo}Reference '
                f'w:customMarkFollows="1" w:id="{ident}"/></w:r><w:r><w:rPr><w:rStyle '
                f'w:val="{estilo}"/></w:rPr><w:t>{personalizada}</w:t></w:r>')
    return (f'<w:r><w:rPr><w:rStyle w:val="{estilo}"/></w:rPr>'
            f'<w:{tipo}Reference w:id="{ident}"/></w:r>')


def nota_xml(ident: int, texto: str, tipo: str = "footnote", extra: str = "", marca: bool = True,
             para_id: str = "") -> str:
    """Um w:footnote (ou w:endnote) como o Word grava: o numero da nota, um espaco e o texto."""
    estilo_p = "Textodenotaderodap" if tipo == "footnote" else "Textodenotadefim"
    estilo_r = "Refdenotaderodap" if tipo == "footnote" else "Refdenotadefim"
    numero = (f'<w:r><w:rPr><w:rStyle w:val="{estilo_r}"/></w:rPr><w:{tipo}Ref/></w:r>'
              '<w:r><w:t xml:space="preserve"> </w:t></w:r>') if marca else ""
    pid = f' w14:paraId="{para_id}" w14:textId="77777777" w:rsidR="00A1B2C3"' if para_id else ""
    return (f'<w:{tipo} w:id="{ident}"><w:p{pid}><w:pPr><w:pStyle w:val="{estilo_p}"/></w:pPr>'
            f'{numero}<w:r><w:t xml:space="preserve">{texto}</w:t></w:r>{extra}</w:p></w:{tipo}>')


def parte_notas(tipo: str, notas: str) -> bytes:
    """footnotes.xml (tipo "footnote") ou endnotes.xml com as duas separadoras e `notas`."""
    raiz = "footnotes" if tipo == "footnote" else "endnotes"
    especiais = (f'<w:{tipo} w:type="separator" w:id="-1"><w:p><w:pPr><w:spacing w:after="0" '
                 f'w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:separator/></w:r></w:p>'
                 f'</w:{tipo}><w:{tipo} w:type="continuationSeparator" w:id="0"><w:p><w:pPr>'
                 '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r>'
                 f'<w:continuationSeparator/></w:r></w:p></w:{tipo}>')
    return (_XML + f'<w:{raiz} xmlns:w="{_NS_W}" xmlns:r="{_NS_R}" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
            f'{_NS_EXTRA}>{especiais}{notas}</w:{raiz}>').encode("utf-8")


def imagem_na_nota(rid: str, ident: int = 901) -> str:
    return ('<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            '<wp:extent cx="457200" cy="228600"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{ident}" name="Imagem {ident}"/><wp:cNvGraphicFramePr>'
            '<a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr><a:graphic>'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="nota.png"/><pic:cNvPicPr/>'
            f'</pic:nvPicPr><pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/>'
            '</a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="457200" '
            'cy="228600"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')


#: Corpo com duas notas de rodape, uma de fim, uma com marca personalizada e uma com link e
#: imagem.
CORPO_COM_NOTAS = (
    '<w:p><w:r><w:t xml:space="preserve">Texto com nota</w:t></w:r>' + ref_nota(1)
    + '<w:r><w:t xml:space="preserve"> e continua.</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>Outra</w:t></w:r>' + ref_nota(2)
    + '<w:r><w:t xml:space="preserve"> e uma nota de fim</w:t></w:r>' + ref_nota(1, "endnote")
    + '<w:r><w:t>.</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>Marca personalizada</w:t></w:r>' + ref_nota(3, personalizada="*")
    + '<w:r><w:t xml:space="preserve"> no fim.</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>Com link e imagem</w:t></w:r>' + ref_nota(4) + '</w:p>')

NOTAS_RODAPE_XML = (
    nota_xml(1, "Primeira nota de rodapé.", para_id="2A000001")
    + nota_xml(2, "Segunda nota.")
    + nota_xml(3, "* Nota de marca personalizada.", marca=False)
    + nota_xml(4, "Veja ", extra='<w:hyperlink r:id="rId1" w:history="1"><w:r><w:t>o site</w:t>'
               '</w:r></w:hyperlink><w:r><w:t xml:space="preserve"> e a figura </w:t></w:r>'
               + imagem_na_nota("rId2")))
NOTAS_FIM_XML = nota_xml(1, "Nota de fim.", "endnote")
SETTINGS_NOTAS_RODAPE = '<w:footnotePr><w:footnote w:id="-1"/><w:footnote w:id="0"/></w:footnotePr>'
SETTINGS_NOTAS_FIM = '<w:endnotePr><w:endnote w:id="-1"/><w:endnote w:id="0"/></w:endnotePr>'
RELS_NOTAS = (_XML + _RELS + f'<Relationship Id="rId1" Type="{RT_LINK}" '
              'Target="https://exemplo.invalid/nota" TargetMode="External"/>'
              f'<Relationship Id="rId2" Type="{_RT_DOC}image" Target="media/nota1.png"/>'
              '</Relationships>')


def docx_com_notas(corpo_xml: str = CORPO_COM_NOTAS, notas_xml: str = NOTAS_RODAPE_XML,
                   notas_fim_xml: str | None = NOTAS_FIM_XML, sect_xml: str = "",
                   rels_notas: str | None = RELS_NOTAS, settings_extra: str | None = None) -> bytes:
    """.docx com word/footnotes.xml (separadoras e as notas), word/endnotes.xml, os estilos de
    nota do Word, o settings.xml citando as separadoras (depois do defaultTabStop, como no
    esquema) e as relacoes da parte de notas (link e imagem). `notas_fim_xml` None: sem
    endnotes.xml."""
    relacoes = [("rId95", RT_NOTAS_RODAPE, "footnotes.xml")]
    tipos = [("/word/footnotes.xml", CT_NOTAS)]
    partes = {"word/footnotes.xml": parte_notas("footnote", notas_xml),
              "word/media/nota1.png": png(12, 6, (20, 120, 200)),
              "word/styles.xml": ESTILOS_COM_NOTAS.encode("utf-8")}
    if rels_notas:
        partes["word/_rels/footnotes.xml.rels"] = rels_notas.encode("utf-8")
    cfg = SETTINGS_NOTAS_RODAPE
    if notas_fim_xml is not None:
        relacoes.append(("rId96", RT_NOTAS_FIM, "endnotes.xml"))
        tipos.append(("/word/endnotes.xml", CT_NOTAS_FIM))
        partes["word/endnotes.xml"] = parte_notas("endnote", notas_fim_xml)
        cfg += SETTINGS_NOTAS_FIM
    docx = docx_com_xml(corpo_xml, sect_xml, partes, relacoes, tipos)
    p = partes_de(docx)
    config = p["word/settings.xml"].decode("utf-8")
    marca = "<w:characterSpacingControl"
    p["word/settings.xml"] = config.replace(
        marca, (cfg if settings_extra is None else settings_extra) + marca, 1).encode("utf-8")
    ct = p["[Content_Types].xml"].decode("utf-8")
    if 'Extension="png"' not in ct:
        p["[Content_Types].xml"] = ct.replace(
            "</Types>", '<Default Extension="png" ContentType="image/png"/></Types>').encode("utf-8")
    if not rels_notas:
        p.pop("word/media/nota1.png", None)
    return montar(p)
