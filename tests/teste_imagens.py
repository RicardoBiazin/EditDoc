"""Imagens na linha do texto (M4): cabecalho, .docx, ponte Qt, tela e edicao.

- formato e dimensoes lidos do cabecalho (PNG, JPEG, GIF, BMP), sem decodificar;
- ida e volta pelo .docx preserva os BYTES da imagem, o tamanho (EMU) e o texto
  alternativo; imagens iguais dividem uma parte de word/media;
- tipos de conteudo e relacoes corretos (validador do pacote e python-docx);
- imagem flutuante vira imagem na linha, com aviso, sem perder a imagem; formato
  que o EditDoc nao mostra (EMF...) vira aviso; imagem gigante fica no arquivo e
  aparece como quadro cinza;
- tela: a imagem aparece no tamanho certo e escala com o zoom;
- edicao: inserir, clicar seleciona, alca e dialogo redimensionam com a proporcao
  travada, colar da area de transferencia, desfazer e refazer.
"""

from __future__ import annotations

import hashlib
import io
import pathlib
import time

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt, pular,
                       resumir, secao, usar_fonte_windows)
import fixtures_docx as fx

QT = preparar_qt()

from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx.escritor import escrever, escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo import imagem as mod_imagem  # noqa: E402
from editdoc.modelo.documento import (CARACTERE_OBJETO, Documento, Paragrafo, Run,  # noqa: E402
                                      normalizar, paragrafos_de, run_de_imagem)

LIMITE_S = 2.0


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def imagens_de(doc: Documento) -> list:
    return [r.imagem for p in paragrafos_de(doc.paragrafos) for r in p.runs if r.imagem is not None]


def bytes_qt(formato: str, largura: int = 30, altura: int = 20, cor=(30, 160, 60)) -> bytes:
    """Imagem no formato pedido. O Qt grava PNG, JPEG e BMP; GIF ele so' le, e vem da fixture."""
    if formato == "gif":
        return fx.gif(largura, altura, cor)
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage

    img = QImage(largura, altura, QImage.Format.Format_RGB32)
    img.fill(QColor(*cor))
    dados = QByteArray()
    buf = QBuffer(dados)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, formato.upper())
    buf.close()
    return bytes(dados.data())


def docx_com_desenho(desenho_xml: str, alvo: str = "media/image1.png", dados: bytes | None = None,
                     tipo_rel: str = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                     extensao: str = "png", tipo_conteudo: str = "image/png") -> bytes:
    """.docx com um paragrafo 'antes [desenho] depois' e a imagem na relacao rId9."""
    base = fx.bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("x")])]))
    partes = fx.partes_de(base)
    xml = partes["word/document.xml"].decode("utf-8")
    xml = xml.replace("<w:document ", '<w:document xmlns:wp="http://schemas.openxmlformats.org/'
                      'drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/'
                      'drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/'
                      '2006/picture" ', 1) if "xmlns:wp" not in xml else xml
    inicio = xml.index("<w:body>") + len("<w:body>")
    fim = xml.index("<w:sectPr")
    corpo = (f'<w:p><w:r><w:t xml:space="preserve">antes </w:t></w:r><w:r>{desenho_xml}</w:r>'
             '<w:r><w:t xml:space="preserve"> depois</w:t></w:r></w:p>')
    partes["word/document.xml"] = (xml[:inicio] + corpo + xml[fim:]).encode("utf-8")
    rels = partes["word/_rels/document.xml.rels"].decode("utf-8")
    partes["word/_rels/document.xml.rels"] = rels.replace(
        "</Relationships>", f'<Relationship Id="rId9" Type="{tipo_rel}" Target="{alvo}"/>'
                            "</Relationships>").encode("utf-8")
    ct = partes["[Content_Types].xml"].decode("utf-8")
    if f'Extension="{extensao}"' not in ct:
        ct = ct.replace("<Override", f'<Default Extension="{extensao}" ContentType="{tipo_conteudo}"/>'
                        "<Override", 1)
    partes["[Content_Types].xml"] = ct.encode("utf-8")
    partes["word/" + alvo] = dados if dados is not None else fx.png(40, 20)
    return fx.montar(partes)


def desenho(quadro: str = "inline", cx: str = "1440000", cy: str = "720000", rid: str = "rId9",
            extra: str = "") -> str:
    ancora = ('<wp:simplePos x="0" y="0"/><wp:positionH relativeFrom="column"><wp:posOffset>0'
              '</wp:posOffset></wp:positionH><wp:positionV relativeFrom="paragraph"><wp:posOffset>0'
              '</wp:posOffset></wp:positionV>') if quadro == "anchor" else ""
    return (f'<w:drawing><wp:{quadro}>{ancora}<wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="7" name="Figura" descr="alt do Word"/>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="f"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/>{extra}<a:stretch><a:fillRect/></a:stretch>'
            '</pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="1" cy="1"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData>'
            f'</a:graphic></wp:{quadro}></w:drawing>')


# -- cabecalho ------------------------------------------------------------------

def testar_cabecalho() -> None:
    secao("formato e dimensoes pelo cabecalho, sem decodificar")
    casos = {"png": fx.png(37, 21)}
    if QT:
        for formato in ("jpeg", "gif", "bmp"):
            casos[formato] = bytes_qt(formato, 37, 21)
    for formato, dados in casos.items():
        checa_igual(mod_imagem.formato_de(dados), formato, f"{formato}: formato pelo numero magico")
        checa_igual(mod_imagem.dimensoes(dados), (37, 21), f"{formato}: 37 x 21 pelo cabecalho")
    checa_igual(mod_imagem.formato_de(b"\x01\x00\x00\x00 EMF qualquer"), None,
                "contraprova: EMF nao e' formato aceito")
    checa_igual(mod_imagem.dimensoes(b"\xff\xd8\xff\xe0\x00\x02"), None,
                "JPEG truncado nao tem dimensao (e nao trava)")
    inicio = time.perf_counter()
    lixo = b"\xff\xd8" + (b"\xff\xe1\x00\x02" * 200000)
    checa(mod_imagem.dimensoes(lixo) is None and time.perf_counter() - inicio < LIMITE_S,
          "JPEG com 200 mil segmentos vazios termina em menos de 2 s")
    checa(not mod_imagem.decodificavel(40000, 40000), "40000 x 40000 passa do teto de pixels")
    checa(mod_imagem.decodificavel(8000, 6000), "contraprova: foto de 48 megapixels cabe no teto")


# -- .docx --------------------------------------------------------------------

def testar_docx() -> None:
    secao(".docx: bytes intactos, tamanho em EMU, texto alternativo, media e tipos de conteudo")
    original = fx.png(40, 20)
    outra = fx.png(10, 10, (0, 0, 255))
    doc = Documento(paragrafos=[
        Paragrafo(runs=[Run("a "), run_de_imagem(fx.imagem(original, 4.0, 2.0, "retângulo")),
                        run_de_imagem(fx.imagem(original, 2.0, 1.0)), Run(" b")]),
        Paragrafo(runs=[run_de_imagem(fx.imagem(outra, 1.0, 1.0))]),
    ])
    dados, avisos_gravacao = escrever_com_avisos(doc)
    lido, avisos = ler(dados)
    checa(normalizar(doc).paragrafos == normalizar(lido).paragrafos, "modelo igual depois da volta")
    checa_igual(avisos + avisos_gravacao, [], "nenhum aviso ao gravar nem ao ler")
    imgs = imagens_de(lido)
    checa_igual([sha(i.dados) for i in imgs], [sha(original), sha(original), sha(outra)],
                "os bytes de cada imagem voltam identicos (sha256)")
    checa_igual([(i.largura_emu, i.altura_emu) for i in imgs],
                [(1440000, 720000), (720000, 360000), (360000, 360000)],
                "o tamanho de cada imagem volta em EMU")
    checa_igual(imgs[0].descricao, "retângulo", "o texto alternativo volta")
    partes = fx.partes_de(dados)
    midias = sorted(n for n in partes if n.startswith("word/media/"))
    checa_igual(midias, ["word/media/image1.png", "word/media/image2.png"],
                "imagens iguais dividem uma parte; a diferente tem a sua")
    checa_igual(partes["word/media/image1.png"], original, "a parte de midia tem os bytes originais")
    checa(b'Extension="png" ContentType="image/png"' in partes["[Content_Types].xml"],
          "Content_Types tem o tipo image/png")
    checa(b"relationships/image" in partes["word/_rels/document.xml.rels"],
          "a relacao da imagem e' do tipo image")
    checa_igual(ordem.validar(partes), [], "o pacote passa no validador")
    checa(escrever(lido) == escrever(ler(escrever(lido))[0]), "segunda ida produz os mesmos bytes")
    textos = ["".join(r.texto for r in p.runs) for p in lido.paragrafos]
    checa_igual(textos[0], f"a {CARACTERE_OBJETO}{CARACTERE_OBJETO} b",
                "a imagem ocupa um caractere de objeto no texto do paragrafo")

    import docx
    d = docx.Document(io.BytesIO(dados))
    formas = d.inline_shapes
    checa_igual(len(formas), 3, "python-docx ve tres imagens na linha")
    checa_igual((formas[0].width, formas[0].height), (1440000, 720000),
                "python-docx le o mesmo tamanho em EMU")
    rid = formas[0]._inline.graphic.graphicData.pic.blipFill.blip.embed
    checa_igual(d.part.related_parts[rid].blob, original, "python-docx acha os bytes originais pela relacao")

    if QT:
        for formato in ("jpeg", "gif", "bmp"):
            bruto = bytes_qt(formato)
            img = fx.imagem(bruto)
            img.formato = formato
            dados_f = escrever(Documento(paragrafos=[Paragrafo(runs=[run_de_imagem(img)])]))
            lido_f, avisos_f = ler(dados_f)
            ext = mod_imagem.FORMATOS[formato][0]
            checa(imagens_de(lido_f)[0].dados == bruto and not avisos_f
                  and f"word/media/image1.{ext}" in fx.partes_de(dados_f)
                  and ordem.validar(fx.partes_de(dados_f)) == [],
                  f"{formato}: bytes intactos, extensao .{ext} e pacote valido")

    adulterado = fx.com_parte(dados, "word/media/image2.png", fx.png(10, 10, (0, 255, 0)))
    try:
        conferencia.conferir(adulterado, doc)
        acusou = False
    except conferencia.FalhaDeConferencia:
        acusou = True
    checa(acusou, "contraprova: a conferencia acusa uma imagem trocada no arquivo gravado")


def testar_leitura_do_word() -> None:
    secao("leitura: flutuante vira na linha, EMF avisa, gigante fica, tamanho invalido, sem relacao")
    modelo, avisos = ler(docx_com_desenho(desenho()))
    imgs = imagens_de(modelo)
    checa(len(imgs) == 1 and not avisos, "wp:inline com PNG vira imagem, sem aviso")
    checa_igual((imgs[0].largura_emu, imgs[0].altura_emu, imgs[0].descricao),
                (1440000, 720000, "alt do Word"), "tamanho e texto alternativo do arquivo")

    modelo, avisos = ler(docx_com_desenho(desenho("anchor")))
    checa(len(imagens_de(modelo)) == 1 and any(a.codigo == "IMAGEM_FLUTUANTE" for a in avisos),
          "wp:anchor (flutuante) vira imagem na linha, com aviso IMAGEM_FLUTUANTE")

    emf = b"\x01\x00\x00\x00" + b"\x00" * 100
    modelo, avisos = ler(docx_com_desenho(desenho(), "media/image1.emf", emf, extensao="emf",
                                          tipo_conteudo="image/x-emf"))
    texto = "".join(r.texto for r in modelo.paragrafos[0].runs)
    checa(not imagens_de(modelo) and any(a.codigo == "IMAGEM" and a.perde_ao_salvar for a in avisos),
          "EMF: aviso IMAGEM, com perda ao salvar")
    checa_igual(texto, "antes  depois", "o texto em volta da imagem nao se perde")

    gigante = fx.png_declarando(40000, 40000)
    dados = docx_com_desenho(desenho(), dados=gigante)
    inicio = time.perf_counter()
    modelo, avisos = ler(dados)
    checa(len(imagens_de(modelo)) == 1 and any(a.codigo == "IMAGEM_GRANDE" and not a.perde_ao_salvar
                                               for a in avisos)
          and time.perf_counter() - inicio < LIMITE_S,
          "imagem de 40000 x 40000 px: fica no modelo, com aviso sem perda, rapido")
    regravado, _ = ler(escrever(modelo))
    checa_igual(sha(imagens_de(regravado)[0].dados), sha(gigante),
                "a imagem gigante volta ao arquivo com os mesmos bytes")

    modelo, avisos = ler(docx_com_desenho(desenho(cx="0", cy="99999999999")))
    img = imagens_de(modelo)[0]
    checa_igual((img.largura_emu, img.altura_emu), (40 * 9525, 20 * 9525),
                "tamanho invalido no wp:extent vira o tamanho da imagem a 96 dpi")

    modelo, avisos = ler(docx_com_desenho(desenho(rid="rId99")))
    checa(not imagens_de(modelo) and any(a.codigo == "IMAGEM" for a in avisos),
          "r:embed sem relacao: aviso IMAGEM, sem erro")
    modelo, avisos = ler(docx_com_desenho(desenho(), alvo="http://exemplo.invalid/x.png").replace(
        b'Target="http://exemplo.invalid/x.png"', b'Target="http://exemplo.invalid/x.png" TargetMode="External"'))
    checa(not imagens_de(modelo) and any(a.codigo == "IMAGEM" for a in avisos),
          "imagem vinculada a endereco externo: aviso IMAGEM, nada e' baixado")
    modelo, avisos = ler(docx_com_desenho(desenho(extra='<a:srcRect l="10000"/>')))
    checa(len(imagens_de(modelo)) == 1 and any(a.codigo == "FORMATACAO" for a in avisos),
          "imagem recortada fica, com aviso de formatacao (o recorte se perde)")


# -- Qt -----------------------------------------------------------------------

def testar_ponte_qt() -> None:
    secao("ponte Qt: QTextImageFormat no tamanho certo, bytes do registro, previa limitada")
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QTextDocument

    from editdoc.ponte_qt import de_qt, imagens, para_qt

    original = fx.png(40, 20)
    doc = Documento(paragrafos=[Paragrafo(runs=[Run("a"), run_de_imagem(fx.imagem(original, 4.0, 2.0)),
                                                run_de_imagem(fx.imagem(original, 4.0, 2.0))])])
    qdoc = QTextDocument()
    para_qt.preencher(qdoc, doc)
    volta = de_qt.extrair(qdoc)
    checa(normalizar(doc).paragrafos == normalizar(volta).paragrafos,
          "ida e volta pelo Qt igual, com duas imagens iguais lado a lado")
    it = qdoc.begin().begin()
    formatos = []
    while not it.atEnd():
        if it.fragment().charFormat().isImageFormat():
            formatos.append(it.fragment().charFormat().toImageFormat())
        it += 1
    largura_px = 4.0 * 360000 / 9525
    checa(formatos and abs(formatos[0].width() - largura_px) < 0.01,
          f"a largura no Qt e' 4 cm em px96 ({formatos[0].width():.2f})")
    checa_igual(sha(imagens_de(volta)[0].dados), sha(original), "os bytes voltam do registro")

    for formato in ("png", "jpeg", "gif", "bmp"):
        p = imagens.previa(bytes_qt(formato, 37, 21))
        checa_igual((p.width(), p.height()), (37, 21),
                    f"{formato}: o Qt decodifica a imagem (nao e' o quadro cinza)")
    grande = bytes_qt("png", 4000, 3000)
    previa = imagens.previa(grande)
    checa(max(previa.width(), previa.height()) <= imagens.LADO_PREVIA_PX,
          f"previa de 4000 x 3000 px reduzida ({previa.width()} x {previa.height()})")
    gigante = imagens.previa(fx.png_declarando(40000, 40000))
    checa(gigante.width() <= 64, "imagem acima do teto vira o quadro cinza, sem decodificar")
    outro = imagens.DocumentoQt()
    nome = imagens.registrar(original, "png")
    recurso = outro.resource(QTextDocument.ResourceType.ImageResource, QUrl(nome))
    checa(recurso is not None and not recurso.isNull(),
          "DocumentoQt acha no registro a imagem que nao esta' nos seus recursos")
    de_fora = outro.resource(QTextDocument.ResourceType.ImageResource,
                             QUrl("file:///C:/Windows/win.ini"))
    checa(de_fora is not None and de_fora.width() <= 64,
          "endereco de fora (file:) nunca e' lido: vira o quadro cinza")


def _painel():
    from editdoc.interface.painel_documento import PainelDocumento
    painel = PainelDocumento("Calibri", 11)
    painel.resize(1000, 800)
    painel.show()
    drenar_eventos(2)
    painel.setFocus()
    return painel


def _contar_cor(img, cor: tuple[int, int, int]) -> int:
    n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if abs(c.red() - cor[0]) < 8 and abs(c.green() - cor[1]) < 8 and abs(c.blue() - cor[2]) < 8:
                n += 1
    return n


def testar_tela_e_zoom() -> None:
    secao("tela: a imagem aparece no tamanho certo e escala com o zoom")
    from editdoc.edicao import imagens as ed_imagens

    painel = _painel()
    cor = (220, 30, 30)
    ed_imagens.inserir_bytes(painel, fx.png(96, 48, cor))
    painel.clearFocus()
    drenar_eventos(2)
    a100 = _contar_cor(painel.viewport().grab().toImage(), cor)
    checa(abs(a100 - 96 * 48) < 96 * 48 * 0.1,
          f"a 100% a imagem de 96 x 48 px ocupa ~4608 px na tela ({a100})")
    painel.definir_zoom(2.0)
    drenar_eventos(2)
    painel.verticalScrollBar().setValue(0)
    painel.horizontalScrollBar().setValue(0)
    drenar_eventos(2)
    a200 = _contar_cor(painel.viewport().grab().toImage(), cor)
    checa(abs(a200 - 4 * a100) < 4 * a100 * 0.1, f"a 200% a area quadruplica ({a200})")
    painel.document().setModified(False)
    painel.close()


def testar_edicao() -> None:
    secao("edicao: inserir, clicar seleciona, alca redimensiona, desfazer, colar, digitar depois")
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from editdoc.edicao import imagens as ed_imagens

    painel = _painel()
    QTest.keyClicks(painel, "antes ")
    ed_imagens.inserir_bytes(painel, fx.png(200, 100))
    QTest.keyClicks(painel, " depois")
    checa_igual(painel.toPlainText(), f"antes {CARACTERE_OBJETO} depois", "a imagem entra no cursor")
    imgs = [r for p in paragrafos_de(_modelo(painel).paragrafos) for r in p.runs if r.imagem]
    checa(imgs and imgs[-1].texto == CARACTERE_OBJETO and not _modelo(painel).paragrafos[0].runs[-1].imagem,
          "o texto digitado depois da imagem nao herda o formato de imagem")
    pos = 6
    r = painel.retangulo_imagem_na_tela(pos)
    checa(r is not None and abs(r.width() - 200) < 1 and abs(r.height() - 100) < 1,
          "a imagem tem 200 x 100 px na tela a 100%")
    QTest.mouseClick(painel.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     r.center().toPoint())
    checa_igual(painel.imagem_selecionada(), pos, "clicar na imagem seleciona a imagem")
    canto = r.bottomRight()
    destino = QPointF(canto.x() - 100, canto.y())
    QTest.mousePress(painel.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     canto.toPoint())
    QTest.mouseMove(painel.viewport(), destino.toPoint())
    QTest.mouseRelease(painel.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       destino.toPoint())
    tamanho = ed_imagens.tamanho_em_px(painel, pos)
    checa(abs(tamanho[0] - 100) < 1.5 and abs(tamanho[1] - 50) < 1.5,
          f"arrastar a alca para a metade da largura: 100 x 50 px, proporcao travada ({tamanho})")
    painel.undo()
    checa_igual(ed_imagens.tamanho_em_px(painel, pos), (200.0, 100.0),
                "um desfazer volta ao tamanho anterior")
    painel.redo()
    checa(abs(ed_imagens.tamanho_em_px(painel, pos)[0] - 100) < 1.5, "refazer aplica de novo")

    painel.setTextCursor(_selecao(painel, pos))
    painel.copy()
    md = QApplication.clipboard().mimeData()
    checa(md.hasImage() and md.hasHtml(), "copiar a imagem selecionada poe a imagem e o HTML")
    painel.moveCursor(painel.textCursor().MoveOperation.End)
    painel.paste()
    checa_igual(painel.toPlainText().count(CARACTERE_OBJETO), 2, "colar o que foi copiado duplica a imagem")
    imagens_modelo = imagens_de(_modelo(painel))
    checa(len(imagens_modelo) == 2 and imagens_modelo[0].dados == imagens_modelo[1].dados,
          "a copia colada tem os mesmos bytes")

    from PySide6.QtGui import QColor, QImage
    externa = QImage(64, 32, QImage.Format.Format_RGB32)
    externa.fill(QColor(10, 200, 10))
    QApplication.clipboard().setImage(externa)
    painel.paste()
    checa_igual(painel.toPlainText().count(CARACTERE_OBJETO), 3,
                "colar uma imagem de outro programa insere a imagem (como PNG)")
    checa_igual(imagens_de(_modelo(painel))[-1].formato, "png", "a imagem colada vira PNG")
    painel.undo()
    checa_igual(painel.toPlainText().count(CARACTERE_OBJETO), 2, "um desfazer tira a imagem colada")

    from editdoc.interface.painel_documento import html_sem_imagens_de_fora
    html = '<p>a<img src="file:///C:/x.png">b<img src="editdoc-img:abc.png" width="3"></p>'
    limpo = html_sem_imagens_de_fora(html)
    checa("file:" not in limpo and "editdoc-img:abc.png" in limpo,
          "HTML colado: imagem de fora sai, imagem do EditDoc fica")
    painel.document().setModified(False)
    painel.close()


def _selecao(painel, pos: int):
    cur = painel.textCursor()
    cur.setPosition(pos)
    cur.setPosition(pos + 1, cur.MoveMode.KeepAnchor)
    return cur


def _modelo(painel) -> Documento:
    from editdoc.ponte_qt import de_qt
    return de_qt.extrair(painel.document())


def testar_janela(tmp: pathlib.Path) -> None:
    secao("janela: inserir imagem de arquivo, dialogo de tamanho em cm, salvar e reabrir")
    from editdoc import configuracao
    from editdoc.edicao import imagens as ed_imagens
    from editdoc.interface import dialogos_modais
    from editdoc.interface.janela_principal import JanelaPrincipal

    usar_fonte_windows(9)
    janela = JanelaPrincipal(configuracao.padrao())
    janela.show()
    drenar_eventos()
    arquivo = tmp / "foto.jpg"
    jpeg = bytes_qt("jpeg", 300, 150)
    arquivo.write_bytes(jpeg)
    recusada = tmp / "falso.png"
    recusada.write_bytes(b"isto nao e' imagem")
    c = janela.comandos
    checa(not c.acao("tamanho_imagem").isEnabled(), "sem imagem selecionada, Tamanho fica desabilitado")
    originais = (dialogos_modais.pedir_arquivo_imagem, dialogos_modais.pedir_tamanho_imagem,
                 dialogos_modais.avisar)
    avisos: list[str] = []
    try:
        dialogos_modais.avisar = lambda _p, _t, texto: avisos.append(texto)
        dialogos_modais.pedir_arquivo_imagem = lambda _p: str(recusada)
        c.acao("inserir_imagem").trigger()
        checa(len(avisos) == 1 and "PNG, JPEG, GIF e BMP" in avisos[0]
              and CARACTERE_OBJETO not in janela.painel.toPlainText(),
              "arquivo que nao e' imagem: mensagem em portugues e nada inserido")
        dialogos_modais.pedir_arquivo_imagem = lambda _p: str(arquivo)
        c.acao("inserir_imagem").trigger()
        checa(CARACTERE_OBJETO in janela.painel.toPlainText(), "Imagem... insere o JPEG do arquivo")
        janela.painel.setTextCursor(_selecao(janela.painel, 0))
        drenar_eventos()
        checa(c.acao("tamanho_imagem").isEnabled(), "com a imagem selecionada, Tamanho habilita")
        pedidos = []

        def responder(_p, largura, altura):
            pedidos.append((largura, altura))
            return 4.0, 2.0

        dialogos_modais.pedir_tamanho_imagem = responder
        c.acao("tamanho_imagem").trigger()
    finally:
        (dialogos_modais.pedir_arquivo_imagem, dialogos_modais.pedir_tamanho_imagem,
         dialogos_modais.avisar) = originais
    checa(pedidos and abs(pedidos[0][0] - 300 * 2.54 / 96) < 0.01,
          f"o dialogo recebe o tamanho atual em cm ({pedidos[0][0]:.2f} cm)")
    largura, altura = ed_imagens.tamanho_em_px(janela.painel, 0)
    checa(abs(largura - 4.0 * 96 / 2.54) < 0.01 and abs(altura - 2.0 * 96 / 2.54) < 0.01,
          "o tamanho em cm do dialogo vira o tamanho da imagem")
    destino = tmp / "com_imagem.docx"
    original = dialogos_modais.pedir_salvar_arquivo
    try:
        dialogos_modais.pedir_salvar_arquivo = lambda *_a: str(destino)
        checa(janela.salvar_como(), "salvar o documento com a imagem")
    finally:
        dialogos_modais.pedir_salvar_arquivo = original
    modelo, avisos_leitura = ler(destino.read_bytes())
    img = imagens_de(modelo)[0]
    checa(img.dados == jpeg and img.formato == "jpeg", "o JPEG vai para o arquivo com os bytes do disco")
    checa_igual((img.largura_emu, img.altura_emu), (1440000, 720000), "4 x 2 cm em EMU no arquivo")
    checa_igual(avisos_leitura, [], "o arquivo com imagem abre sem aviso")
    checa_igual(ordem.validar(fx.partes_de(destino.read_bytes())), [], "o arquivo passa no validador")
    janela.painel.document().setModified(False)
    janela.close()


def main() -> int:
    testar_cabecalho()
    testar_docx()
    testar_leitura_do_word()
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    if not usar_fonte_windows(9):
        return pular("Segoe UI nao esta instalada")
    testar_ponte_qt()
    testar_tela_e_zoom()
    testar_edicao()
    with pasta_temporaria("editdoc-teste-imagens-") as tmp:
        testar_janela(tmp)
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
