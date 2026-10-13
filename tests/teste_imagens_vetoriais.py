"""Imagens EMF, WMF, TIFF e SVG na tela (0.1.5).

- cabecalho: EMF e WMF desenhados pelo GDI agora (so' no Windows), EMF minimo montado byte a
  byte, TIFF e SVG: formato e tamanho; EMF cortado, com registro de tamanho impossivel, sem
  EMR_EOF ou com dimensoes enormes nao tem previa; limite de registros;
- leitura: a imagem na linha em EMF/WMF/TIFF/SVG tem previa e nao da' aviso; a danificada, a
  enorme e a vinculada a arquivo externo continuam o quadro, com o aviso IMAGEM_FORMATO (a
  vinculada com o nome do destino, nada lido do disco); VML com imagem embutida tem previa;
  os bytes voltam identicos ao arquivo;
- previa: as cores do desenho, a transparencia do EMF sem fundo, o SVG com referencia de fora
  ou DOCTYPE recusado, o limite de registros e de tempo para o laco do metafile;
- tela: a imagem aparece no lugar (pixel vermelho da elipse), e o quadro some;
- autoverificacao: acusa quando a previa nao sai (contraprova).
"""

from __future__ import annotations

import struct
import sys
import time

from ajudantes import checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao
import fixtures_docx as fx

QT = preparar_qt()

from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo import imagem as mod_imagem  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run, objetos_de  # noqa: E402

WINDOWS = sys.platform == "win32"
RT_IMAGEM = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"


def docx_com(item_xml: str, alvo: str, dados: bytes | None, extensao: str, tipo: str,
             externo: bool = False) -> bytes:
    """.docx com 'antes [item] depois' e a relacao rId9 para `alvo`."""
    base = fx.bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("x")])]))
    partes = fx.partes_de(base)
    xml = partes["word/document.xml"].decode("utf-8")
    inicio = xml.index("<w:body>") + len("<w:body>")
    fim = xml.index("<w:sectPr")
    corpo = (f'<w:p><w:r><w:t xml:space="preserve">antes </w:t></w:r><w:r>{item_xml}</w:r>'
             '<w:r><w:t xml:space="preserve"> depois</w:t></w:r></w:p>')
    partes["word/document.xml"] = (xml[:inicio] + corpo + xml[fim:]).encode("utf-8")
    modo = ' TargetMode="External"' if externo else ""
    rels = partes["word/_rels/document.xml.rels"].decode("utf-8")
    partes["word/_rels/document.xml.rels"] = rels.replace(
        "</Relationships>", f'<Relationship Id="rId9" Type="{RT_IMAGEM}" Target="{alvo}"{modo}/>'
                            "</Relationships>").encode("utf-8")
    ct = partes["[Content_Types].xml"].decode("utf-8")
    if f'Extension="{extensao}"' not in ct:
        ct = ct.replace("<Override", f'<Default Extension="{extensao}" ContentType="{tipo}"/><Override', 1)
    partes["[Content_Types].xml"] = ct.encode("utf-8")
    if dados is not None:
        partes["word/" + alvo] = dados
    return fx.montar(partes)


def desenho(atributo: str = "r:embed") -> str:
    return ('<w:drawing><wp:inline><wp:extent cx="1440000" cy="720000"/><wp:docPr id="7" name="F"/>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="f"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip {atributo}="rId9"/><a:stretch><a:fillRect/></a:stretch>'
            '</pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1" cy="1"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData>'
            '</a:graphic></wp:inline></w:drawing>')


VML = ('<w:pict xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">'
       '<v:shape id="_x0000_i1025" style="width:72pt;height:36pt"><v:imagedata r:id="rId9" o:title=""/>'
       '</v:shape></w:pict>')


def emf_minimo(quadro=(0, 0, 2540, 1270), registros_extra: int = 0, cortar: bool = False,
               tamanho_ruim: bool = False) -> bytes:
    """EMR_HEADER + (EMR_SETBKMODE...) + EMR_EOF, byte a byte."""
    corpo = b""
    for _ in range(registros_extra):
        corpo += struct.pack("<III", 18, 12, 1)  # EMR_SETBKMODE, 12 bytes
    eof = struct.pack("<IIIII", 14, 20, 0, 16, 20)
    total = 88 + len(corpo) + len(eof)
    cab = struct.pack("<II4i4i", 1, 88, 0, 0, 96, 48, *quadro)
    cab += b" EMF" + struct.pack("<IIIHHIII", 0x10000, total, 2 + registros_extra, 1, 0, 0, 0, 0)
    cab += struct.pack("<ii", 1920, 1080) + struct.pack("<ii", 508, 286)
    cab = cab[:88].ljust(88, b"\x00")
    dados = cab + corpo + eof
    if tamanho_ruim:
        dados = dados[:88] + struct.pack("<II", 18, 7) + dados[96:]
    if cortar:
        dados = dados[:-20]
        dados = dados[:48] + struct.pack("<I", len(dados)) + dados[52:]
    return dados


def tiff(cor: str = "#204080") -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage
    img = QImage(30, 10, QImage.Format.Format_RGB32)
    img.fill(QColor(cor))
    dados = QByteArray()
    buf = QBuffer(dados)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "TIFF")
    buf.close()
    return bytes(dados.data())


SVG = (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
       b'<rect width="40" height="20" fill="#00a000"/></svg>')


def testar_cabecalho() -> None:
    secao("cabecalho: formato, tamanho e estrutura, sem decodificar")
    minimo = emf_minimo()
    checa_igual((mod_imagem.formato_previa(minimo), mod_imagem.dimensoes_previa(minimo, "emf")),
                ("emf", (96, 48)), "EMF minimo (byte a byte): formato e 2,54 x 1,27 cm = 96 x 48 px")
    checa(mod_imagem.previa_possivel(minimo, True) == "emf", "EMF minimo tem previa no Windows")
    checa(mod_imagem.previa_possivel(minimo, False) is None, "fora do Windows o EMF fica o quadro")
    checa(mod_imagem.previa_possivel(emf_minimo(cortar=True), True) is None,
          "EMF cortado (sem EMR_EOF): sem previa")
    checa(mod_imagem.previa_possivel(emf_minimo(tamanho_ruim=True), True) is None,
          "EMF com registro de tamanho impossivel: sem previa")
    enorme = emf_minimo(quadro=(0, 0, 254000000, 254000000))
    checa(mod_imagem.previa_possivel(enorme, True) is None,
          "EMF com dimensoes enormes (2,5 km): sem previa")
    antes = mod_imagem.REGISTROS_MAXIMOS
    try:
        mod_imagem.REGISTROS_MAXIMOS = 10
        checa(mod_imagem.previa_possivel(emf_minimo(registros_extra=50), True) is None,
              "registros acima do limite: sem previa")
    finally:
        mod_imagem.REGISTROS_MAXIMOS = antes
    checa(mod_imagem.previa_possivel(emf_minimo(registros_extra=50), True) == "emf",
          "e dentro do limite, a mesma estrutura tem previa (contraprova)")
    t = tiff()
    checa_igual((mod_imagem.formato_previa(t), mod_imagem.dimensoes_previa(t, "tiff")),
                ("tiff", (30, 10)), "TIFF: formato e 30 x 10 pelo IFD")
    checa_igual(mod_imagem.formato_previa(SVG), "svg", "SVG pelo inicio do texto")
    checa(mod_imagem.formato_previa(fx.png(4, 4)) is None, "PNG nao e' formato de previa")
    if WINDOWS:
        from editdoc.ponte_qt import vetoriais
        for f in ("emf", "wmf"):
            d = vetoriais.metafile_de_exemplo(f)
            checa_igual((mod_imagem.formato_previa(d), mod_imagem.dimensoes_previa(d, f)),
                        (f, (151, 76)), f"{f.upper()} do GDI: 4 x 2 cm = 151 x 76 px")


def testar_leitura() -> None:
    secao("leitura: o que a tela mostra nao da' aviso; o que nao mostra, quadro com aviso")
    casos = [("TIFF", "media/i.tiff", tiff(), "tiff", "image/tiff", True),
             ("SVG", "media/i.svg", SVG, "svg", "image/svg+xml", True),
             ("EMF danificado", "media/i.emf", emf_minimo(cortar=True), "emf", "image/x-emf", False),
             ("EMF enorme", "media/i.emf", emf_minimo(quadro=(0, 0, 254000000, 254000000)), "emf",
              "image/x-emf", False)]
    if WINDOWS:
        from editdoc.ponte_qt import vetoriais
        casos += [("EMF", "media/i.emf", vetoriais.metafile_de_exemplo("emf"), "emf", "image/x-emf", True),
                  ("WMF", "media/i.wmf", vetoriais.metafile_de_exemplo("wmf"), "wmf", "image/x-wmf", True)]
    for nome, alvo, dados, ext, tipo, mostra in casos:
        modelo, avisos = ler(docx_com(desenho(), alvo, dados, ext, tipo))
        obj = next(objetos_de(modelo))
        codigos = {a.codigo for a in avisos}
        if mostra:
            checa(obj.previa == dados and "IMAGEM_FORMATO" not in codigos and not avisos,
                  f"{nome} na linha: previa e nenhum aviso")
        else:
            checa(obj.previa is None and "IMAGEM_FORMATO" in codigos,
                  f"{nome}: sem previa, aviso IMAGEM_FORMATO (o quadro)")
        saida = fx.partes_de(escrever(modelo))
        checa(dados in saida.values(), f"{nome}: os bytes voltam identicos ao arquivo")
    modelo, avisos = ler(docx_com(desenho("r:link"), "file:///C:/fotos/logo.emf", None, "emf",
                                  "image/x-emf", externo=True))
    obj = next(objetos_de(modelo))
    checa(obj.previa is None and obj.resumo == "vinculada a logo.emf"
          and any(a.codigo == "IMAGEM_FORMATO" for a in avisos),
          "vinculada a arquivo externo: quadro com o nome do destino, aviso, nada lido")
    modelo, avisos = ler(docx_com(VML, "media/i.png", fx.png(20, 10), "png", "image/png"))
    obj = next(objetos_de(modelo))
    checa(obj.tipo == "imagem" and obj.previa is not None,
          "VML com imagem embutida (v:imagedata): tem previa")
    texto = __import__("editdoc.formato_docx.avisos", fromlist=["x"]).construir("IMAGEM_FORMATO", 1).texto
    checa("vinculada" in texto and "EMF" not in texto and "preservada" in texto,
          "o aviso cita so' o que nao aparece (vinculada, danificada...), nao mais EMF/WMF/TIFF/SVG")


def testar_previa() -> None:
    secao("previa: cores, transparencia, SVG inseguro, limites")
    from editdoc.ponte_qt import vetoriais
    img = vetoriais.renderizar(tiff())
    checa(not img.isNull() and vetoriais.cor_dominante(img).name() == "#204080", "TIFF decodificado")
    img = vetoriais.renderizar(SVG)
    checa(not img.isNull() and vetoriais.cor_dominante(img).name() == "#00a000", "SVG renderizado")
    for nome, ruim in (("href de arquivo", SVG.replace(b"<rect", b'<image href="file:///C:/x.png"/><rect')),
                       ("url() de fora", SVG.replace(b'fill="#00a000"', b'style="fill:url(http://x/y)"')),
                       ("DOCTYPE", b'<!DOCTYPE svg [<!ENTITY a "b">]>' + SVG)):
        checa(vetoriais.renderizar(ruim).isNull(), f"SVG com {nome}: recusado, sem previa")
    checa(not vetoriais.svg_seguro(SVG.replace(b"<rect", b'<use href="outro.svg#x"/><rect'))
          and vetoriais.svg_seguro(SVG.replace(b"<rect", b'<use href="#x"/><rect')),
          "referencia interna (#x) passa; a de outro arquivo nao")
    if not WINDOWS:
        checa(vetoriais.renderizar(emf_minimo()).isNull(), "fora do Windows: EMF sem previa")
        return
    for f in ("emf", "wmf"):
        img = vetoriais.renderizar(vetoriais.metafile_de_exemplo(f))
        checa(not img.isNull() and vetoriais.cor_dominante(img).name() == "#e00000"
              and img.pixelColor(3, 3).name() == "#0040c0",
              f"{f.upper()}: elipse vermelha no meio, fundo azul no canto")
    img = vetoriais.renderizar(vetoriais.metafile_de_exemplo("emf", fundo=False))
    checa(img.pixelColor(3, 3).alpha() == 0 and vetoriais.cor_dominante(img).alpha() == 255,
          "EMF sem fundo: o canto e' transparente e a elipse opaca (o branco nao some)")
    checa(max(img.width(), img.height()) <= vetoriais.LADO_MAXIMO_PX,
          "o bitmap respeita o lado maximo, nao o que o arquivo declara")
    checa(vetoriais.renderizar(emf_minimo(cortar=True)).isNull(), "EMF danificado: sem previa")
    antes = vetoriais.REGISTROS_MAXIMOS
    try:
        vetoriais.REGISTROS_MAXIMOS = 3
        inicio = time.perf_counter()
        parado = vetoriais.renderizar(vetoriais.metafile_de_exemplo("emf"))
        checa(parado.isNull() and time.perf_counter() - inicio < 2,
              "o laco do metafile para no limite de registros, sem travar")
    finally:
        vetoriais.REGISTROS_MAXIMOS = antes
    antes = vetoriais.TEMPO_MAXIMO_S
    try:
        vetoriais.TEMPO_MAXIMO_S = -1
        checa(vetoriais.renderizar(vetoriais.metafile_de_exemplo("emf")).isNull(),
              "e no limite de tempo")
    finally:
        vetoriais.TEMPO_MAXIMO_S = antes


def testar_tela() -> None:
    secao("tela: a imagem aparece no lugar do quadro")
    from PySide6.QtGui import QColor, QImage, QPainter, QTransform
    from editdoc.interface.layout_paginado import LayoutPaginado
    from editdoc.interface.vista_paginas import desenhar_folha
    from editdoc.ponte_qt import para_qt

    def vermelhos(dados: bytes, ext: str) -> int:
        modelo, _ = ler(docx_com(desenho(), "media/i." + ext, dados, ext, "image/x-" + ext))
        lay = LayoutPaginado(modelo.pagina, "Calibri", 11.0)
        para_qt.preencher(lay.doc, modelo)
        img = QImage(600, 300, QImage.Format.Format_RGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        desenhar_folha(p, lay, 0, QTransform().scale(0.05, 0.05))
        p.end()
        return sum(1 for y in range(0, 300, 2) for x in range(0, 600, 2)
                   if img.pixelColor(x, y).red() > 180 and img.pixelColor(x, y).green() < 60)
    if WINDOWS:
        from editdoc.ponte_qt import vetoriais
        checa(vermelhos(vetoriais.metafile_de_exemplo("emf"), "emf") > 20,
              "EMF na linha: a elipse vermelha aparece na pagina")
        checa_igual(vermelhos(emf_minimo(cortar=True), "emf"), 0,
                    "contraprova: o EMF danificado nao pinta nada vermelho (o quadro)")
    else:
        checa(True, "fora do Windows: sem EMF na tela")


def testar_autoverificacao() -> None:
    secao("autoverificacao: confere a previa de TIFF, SVG, EMF e WMF (com contraprova)")
    import app
    from PySide6.QtGui import QImage
    from editdoc.ponte_qt import vetoriais
    falhas: list[str] = []
    app._previas_vetoriais(falhas)
    checa_igual(falhas, [], "a autoverificacao passa no ambiente da suite")
    original = vetoriais.renderizar
    try:
        vetoriais.renderizar = lambda *a, **k: QImage()
        falhas = []
        app._previas_vetoriais(falhas)
        checa(any("TIFF" in f for f in falhas) and any("SVG" in f for f in falhas),
              "contraprova: sem previa, a autoverificacao acusa TIFF e SVG")
    finally:
        vetoriais.renderizar = original
    checa("tiff" in app.FORMATOS_DE_IMAGEM, "o plugin do TIFF entra na lista conferida do .exe")


def main() -> int:
    if not QT:
        return pular("PySide6 nao instalado")
    testar_cabecalho()
    testar_leitura()
    testar_previa()
    testar_tela()
    testar_autoverificacao()
    drenar_eventos()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
