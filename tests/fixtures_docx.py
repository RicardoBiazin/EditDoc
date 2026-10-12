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
