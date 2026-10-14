"""Objetos flutuantes (0.1.7): na posicao da pagina, com o texto em volta, como o Word.

- posicao sem Qt (`modelo/flutuantes.py`) contra um oraculo escrito a mao, em twips:
  relativeFrom page/margin/column/paragraph/insideMargin, posOffset, align, simplePos,
  sizeRel e a area de quebra com distancias e effectExtent;
- leitura do XML (`formato_docx/flutuantes.py`): wp:anchor, VML absoluto, imagem com
  recorte, caixa de texto com fundo e margens, forma behindDoc, grupo com chOff/chExt;
- tela: a pagina do objeto e' a da ancora; o texto contorna (x das linhas ao lado do
  objeto) com wrapSquare a esquerda e a direita, desce com wrapTopAndBottom e nao muda com
  wrapNone e behindDoc;
- pintura: behindDoc antes do texto, o da frente depois; a imagem na posicao certa na folha
  pintada pela funcao do PDF e no proprio PDF; o objeto do cabecalho em todas as paginas;
- ida e volta: o XML de cada objeto volta igual (c14n), passando pelo Qt;
- interacao: clique seleciona (contorno), Delete apaga e o texto volta a largura toda,
  Ctrl+Z traz de volta; duplo clique na caixa abre o editor;
- desempenho: digitar com e sem objetos flutuantes (gate do M3, p95).
"""

from __future__ import annotations

import re
import statistics
import time

from ajudantes import (checa, checa_igual, drenar_eventos, preparar_qt, resumir, secao,
                       usar_fontes_do_documento)
import fixtures_docx as fx

preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import flutuantes as fxml  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo import flutuantes as mf  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run, paragrafos_de  # noqa: E402
from editdoc.modelo.pagina import Pagina  # noqa: E402

URI_IMAGEM = "http://schemas.openxmlformats.org/drawingml/2006/picture"
URI_FORMA = fx.URI_FORMA
URI_GRUPO = "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
A4 = Pagina()  # 11906 x 16838, margens de 1440
TEXTO = ("Texto do paragrafo ao lado do objeto flutuante, comprido para quebrar em varias "
         "linhas e mostrar onde a linha comeca e onde termina. ") * 4


# -- fixtures em codigo -----------------------------------------------------------------

def ancora(ident: int, uri: str, conteudo: str, cx: int, cy: int,
           h=("margin", "posOffset", 0), v=("paragraph", "posOffset", 0),
           quebra='<wp:wrapSquare wrapText="bothSides"/>', atras: bool = False,
           z: int = 251659264, dist=(0, 0, 0, 0), efeito=(0, 0, 0, 0)) -> str:
    def pos(tag, rel, modo, val):
        return f'<wp:{tag} relativeFrom="{rel}"><wp:{modo}>{val}</wp:{modo}></wp:{tag}>'
    return ('<w:r><w:drawing>'
            f'<wp:anchor distT="{dist[0]}" distB="{dist[1]}" distL="{dist[2]}" distR="{dist[3]}" '
            f'simplePos="0" relativeHeight="{z}" behindDoc="{1 if atras else 0}" locked="0" '
            'layoutInCell="1" allowOverlap="1"><wp:simplePos x="0" y="0"/>'
            + pos("positionH", *h) + pos("positionV", *v)
            + f'<wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:effectExtent l="{efeito[0]}" t="{efeito[1]}" r="{efeito[2]}" b="{efeito[3]}"/>'
            f'{quebra}<wp:docPr id="{ident}" name="Objeto {ident}"/><wp:cNvGraphicFramePr/>'
            f'<a:graphic><a:graphicData uri="{uri}">{conteudo}</a:graphicData></a:graphic>'
            '</wp:anchor></w:drawing></w:r>')


def figura(rid: str, cx: int, cy: int, recorte: str = "") -> str:
    return ('<pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="f.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/>{recorte}<a:stretch><a:fillRect/></a:stretch>'
            f'</pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/>'
            '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>')


def forma(cx: int, cy: int, cor: str = "FF0000", prst: str = "rect", texto: str = "",
          ancora_texto: str = "t", linha: str = '<a:ln><a:noFill/></a:ln>') -> str:
    txbx = ""
    if texto:
        txbx = ('<wps:txbx><w:txbxContent><w:p><w:r><w:rPr><w:color w:val="FFFFFF"/></w:rPr>'
                f'<w:t>{texto}</w:t></w:r></w:p></w:txbxContent></wps:txbx>')
    return ('<wps:wsp><wps:cNvSpPr/><wps:spPr><a:xfrm><a:off x="0" y="0"/>'
            f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="{prst}"><a:avLst/>'
            f'</a:prstGeom><a:solidFill><a:srgbClr val="{cor}"/></a:solidFill>{linha}</wps:spPr>'
            f'{txbx}<wps:bodyPr lIns="182880" tIns="91440" rIns="182880" bIns="91440" '
            f'anchor="{ancora_texto}"/></wps:wsp>')


def grupo(cx: int, cy: int) -> str:
    filho = ('<wps:wsp><wps:cNvPr id="{n}" name="R{n}"/><wps:cNvSpPr/><wps:spPr><a:xfrm>'
             '<a:off x="{x}" y="{y}"/><a:ext cx="500" cy="500"/></a:xfrm><a:prstGeom prst="rect">'
             '<a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{cor}"/></a:solidFill>'
             '<a:ln><a:noFill/></a:ln></wps:spPr><wps:bodyPr/></wps:wsp>')
    return ('<wpg:wgp><wpg:cNvGrpSpPr/><wpg:grpSpPr><a:xfrm><a:off x="0" y="0"/>'
            f'<a:ext cx="{cx}" cy="{cy}"/><a:chOff x="1000" y="1000"/><a:chExt cx="1000" cy="1000"/>'
            '</a:xfrm></wpg:grpSpPr>'
            + filho.format(n=1, x=1000, y=1000, cor="0000FF")
            + filho.format(n=2, x=1500, y=1500, cor="00AA00") + '</wpg:wgp>')


VML_ABSOLUTO = ('<w:r><w:pict><v:rect id="Ret" o:spid="_x0000_s3001" style="position:absolute;'
                'margin-left:72pt;margin-top:36pt;width:144pt;height:72pt;z-index:251660000;'
                'mso-position-horizontal-relative:page;mso-position-vertical-relative:page" '
                'fillcolor="#00ff00" stroked="f"><w10:wrap type="none"/></v:rect></w:pict></w:r>')


def doc_do_corpo(corpo: str, relacoes=(), partes=None, cabecalho: str = "",
                 paragrafos_depois: int = 0) -> bytes:
    base = Documento(paragrafos=[Paragrafo(runs=[Run("Fim do documento.")])]
                     + [Paragrafo(runs=[Run(TEXTO)]) for _ in range(paragrafos_depois)],
                     cabecalhos={"padrao": [Paragrafo(runs=[Run("Cabeçalho")])]})
    return fx.docx_com_corpo_de_objetos(corpo, relacoes, partes or {}, (), (("png", "image/png"),),
                                        cabecalho_xml=cabecalho, documento=base)


def png_cor(cor: tuple) -> bytes:
    return fx.png(60, 30, cor)


RT_IMAGEM = fx.RT_IMAGEM


# -- posicao sem Qt ---------------------------------------------------------------------

def testar_posicao() -> None:
    secao("posicao sem Qt: oraculo em twips (A4, margens de 1440)")
    ref = mf.Referencia(pagina=A4, indice=0, paragrafo_y=3000.0, linha_y=3100.0,
                        coluna_x=1440.0, coluna_w=9026.0, caractere_x=5000.0)
    w, h = 1828800, 914400  # 2880 x 1440 twips
    casos = [
        ("pagina, align right/bottom", dict(h_rel="page", h_alinh="right", v_rel="page",
                                           v_alinh="bottom"), (11906 - 2880, 16838 - 1440)),
        ("margem + posOffset, pagina + posOffset", dict(h_rel="margin", h_desloc=914400,
                                                        v_rel="page", v_desloc=1270000),
         (1440 + 1440, 2000)),
        ("margem, align center/top", dict(h_rel="margin", h_alinh="center", v_rel="margin",
                                          v_alinh="top"), (1440 + (9026 - 2880) / 2, 1440)),
        ("coluna e paragrafo (posOffset negativo)", dict(h_rel="column", h_desloc=-635000,
                                                          v_rel="paragraph", v_desloc=635000),
         (1440 - 1000, 3000 + 1000)),
        ("linha e caractere", dict(h_rel="character", h_desloc=0, v_rel="line", v_desloc=0),
         (5000, 3100)),
        ("margem esquerda, align right", dict(h_rel="leftMargin", h_alinh="right",
                                              v_rel="bottomMargin", v_alinh="top"),
         (1440 - 2880, 16838 - 1440)),
        ("insideMargin na pagina impar = margem esquerda", dict(h_rel="insideMargin",
                                                                 h_alinh="left"), (0, 3000)),
        ("simplePos", dict(simples=(635000, 1270000)), (1000, 2000)),
    ]
    for nome, dados, (ex, ey) in casos:
        anc = mf.Ancoragem(largura=w, altura=h, **dados)
        x, y, lw, lh = mf.retangulo(anc, ref)
        checa_igual((round(x), round(y), round(lw), round(lh)), (round(ex), round(ey), 2880, 1440),
                    f"{nome}: ({round(ex)}, {round(ey)}) twips")
    par = mf.Referencia(pagina=A4, indice=1, paragrafo_y=3000.0)
    anc = mf.Ancoragem(largura=w, altura=h, h_rel="insideMargin", h_alinh="left")
    checa_igual(round(mf.retangulo(anc, par)[0]), 11906 - 1440,
                "insideMargin na pagina par = margem direita (11906 - 1440)")
    anc = mf.Ancoragem(largura=w, altura=h, h_rel="margin", h_alinh="inside")
    checa_igual(round(mf.retangulo(anc, par)[0]), 1440 + 9026 - 2880,
                "align inside na pagina par: encostado a direita da margem")
    anc = mf.Ancoragem(largura=w, altura=h, pct_largura=50000, pct_largura_rel="margin")
    checa_igual(round(mf.retangulo(anc, ref)[2]), 4513, "wp14:pctWidth 50% da margem = 4513 twips")
    anc = mf.Ancoragem(largura=w, altura=h, h_rel="margin", h_pct=25000)
    checa_igual(round(mf.retangulo(anc, ref)[0]), round(1440 + 9026 * 0.25),
                "wp14:pctPosHOffset 25% da margem")
    anc = mf.Ancoragem(largura=w, altura=h, dist=(63500, 127000, 190500, 254000),
                       efeito=(6350, 12700, 19050, 25400))
    rect = (1000.0, 2000.0, 2880.0, 1440.0)
    checa_igual(tuple(round(v) for v in mf.area_de_quebra(anc, rect)),
                (1000 - 10 - 300, 2000 - 20 - 100, 1000 + 2880 + 30 + 400, 2000 + 1440 + 40 + 200),
                "area de quebra: objeto + effectExtent + distT/B/L/R")
    # Contraprova: o oraculo acusa um alinhamento trocado.
    anc = mf.Ancoragem(largura=w, altura=h, h_rel="page", h_alinh="left", v_rel="page",
                       v_alinh="bottom")
    checa(round(mf.retangulo(anc, ref)[0]) != 11906 - 2880,
          "contraprova: align left na pagina nao da' o x do align right")
    checa(mf.Ancoragem(quebra="square").reserva_espaco()
          and not mf.Ancoragem(quebra="square", atras=True).reserva_espaco()
          and not mf.Ancoragem(quebra="none").reserva_espaco(),
          "reserva espaco: wrapSquare sim; behindDoc e wrapNone nao")
    checa_igual(mf.Ancoragem(lado="bothSides").lado_da_reserva(1440, 4000, 1440, 10466),
                "esquerda", "objeto encostado a esquerda: o texto passa a direita")
    checa_igual(mf.Ancoragem(lado="bothSides").lado_da_reserva(8000, 10466, 1440, 10466),
                "direita", "objeto encostado a direita: o texto passa a esquerda")


# -- leitura do XML -------------------------------------------------------------------------

def _r(xml_run: str) -> bytes:
    decl = " ".join(f'xmlns:{k}="{v}"' for k, v in fx.NS_OBJETOS.items())
    decl += f' xmlns:w="{fx._NS_W}" xmlns:r="{fx._NS_R}"'
    return xml_run.replace("<w:r>", f"<w:r {decl}>", 1).encode("utf-8")


def testar_leitura() -> None:
    secao("leitura do XML: wp:anchor, VML, figura, caixa, grupo, cores")
    xml = _r(ancora(5, URI_IMAGEM, figura("rId7", 1828800, 914400,
                                           '<a:srcRect l="10000" t="0" r="20000" b="5000"/>'),
                    1828800, 914400, h=("page", "align", "right"), v=("page", "align", "bottom"),
                    dist=(10, 20, 30, 40), efeito=(1, 2, 3, 4), z=7))
    fl = fxml.ler(xml)
    anc = fl.ancoragem
    checa_igual((anc.h_rel, anc.h_alinh, anc.v_rel, anc.v_alinh, anc.largura, anc.altura),
                ("page", "right", "page", "bottom", 1828800, 914400),
                "imagem: relativeFrom, align e extent")
    checa_igual((anc.dist, anc.efeito, anc.z, anc.quebra, anc.atras), ((10, 20, 30, 40), (1, 2, 3, 4),
                                                                      7, "square", False),
                "distancias, effectExtent, relativeHeight, wrapSquare")
    checa_igual((fl.figura.tipo, fl.figura.rid, fl.figura.recorte), ("imagem", "rId7", (10000, 0, 20000, 5000)),
                "figura: imagem com o rId do blip e o recorte a:srcRect")
    fl = fxml.ler(_r(ancora(6, URI_FORMA, forma(914400, 457200, "112233", texto="Oi", ancora_texto="ctr"),
                            914400, 457200, quebra="<wp:wrapTopAndBottom/>")))
    f = fl.figura
    checa_igual((f.tipo, f.texto, f.ancora_texto, f.margens, fxml.resolver(f.preenchimento)),
                ("forma", True, "ctr", (182880, 91440, 182880, 91440), (0x11, 0x22, 0x33, 255)),
                "caixa de texto: forma com texto, anchor ctr, margens do bodyPr, fundo 112233")
    checa_igual(fl.ancoragem.quebra, "topbottom", "wrapTopAndBottom")
    fl = fxml.ler(_r(ancora(7, URI_FORMA, forma(914400, 457200, prst="ellipse"), 914400, 457200,
                            quebra="<wp:wrapNone/>", atras=True)))
    checa((fl.ancoragem.atras, fl.figura.geometria, fl.ancoragem.quebra) == (True, "ellipse", "none"),
          "forma behindDoc: atras do texto, elipse, sem quebra")
    fl = fxml.ler(_r(ancora(8, URI_GRUPO, grupo(1828800, 1828800), 1828800, 1828800)))
    g = fl.figura
    checa_igual((g.tipo, len(g.filhos), g.ch_off, g.ch_ext, [(c.x, c.y, c.w) for c in g.filhos]),
                ("grupo", 2, (1000, 1000), (1000, 1000), [(1000, 1000, 500), (1500, 1500, 500)]),
                "grupo: dois filhos com xfrm na coordenada chOff/chExt")
    fl = fxml.ler(_r(VML_ABSOLUTO))
    a = fl.ancoragem
    checa_igual((a.vml, a.h_rel, a.v_rel, a.h_desloc, a.v_desloc, a.largura, a.altura,
                 fxml.resolver(fl.figura.preenchimento)),
                (True, "page", "page", 914400, 457200, 1828800, 914400, (0, 255, 0, 255)),
                "VML absoluto: margin-left/top, width/height, relativo a pagina, fillcolor")
    vml_atras = VML_ABSOLUTO.replace("z-index:251660000", "z-index:-5")
    checa(fxml.ler(_r(vml_atras)).ancoragem.atras, "VML com z-index negativo fica atras do texto")
    inline = _r('<w:r><w:drawing><wp:inline><wp:extent cx="1" cy="1"/><wp:docPr id="1" name="x"/>'
                '<a:graphic><a:graphicData uri="u"/></a:graphic></wp:inline></w:drawing></w:r>')
    checa(fxml.ler(inline) is None, "objeto na linha (wp:inline) nao e' flutuante")
    tema = fx.TEMA_DO_WORD.encode("utf-8") if isinstance(fx.TEMA_DO_WORD, str) else fx.TEMA_DO_WORD
    cores = fxml.cores_do_tema(tema)
    checa("accent1" in cores and len(cores["accent1"]) == 6, "cores do tema lidas do theme1.xml")
    escura = fxml.resolver(fxml.Cor("srgb", "808080", (("lumMod", 50000),)))
    checa(escura[0] < 0x80, "lumMod escurece a cor")


# -- tela -------------------------------------------------------------------------------------

def _painel():
    from editdoc.interface.painel_documento import PainelDocumento
    painel = PainelDocumento("Calibri", 11)
    painel.resize(1000, 800)
    return painel


def _carregar(painel, docx: bytes):
    from editdoc.ponte_qt import para_qt
    modelo, _ = ler(docx)
    para_qt.preencher(painel.documento_corpo(), modelo)
    painel.carregar_faixas(modelo)
    painel.definir_configuracao_pagina(modelo.pagina)
    para_qt.concluir_listas(painel.documento_corpo())
    painel.layout_pag.atualizar_flutuantes()
    return modelo


def _linhas(doc, bloco):
    dl = doc.documentLayout()
    r = dl.blockBoundingRect(bloco)
    lay = bloco.layout()
    return [(r.top() + lay.lineAt(i).y(), r.left() + lay.lineAt(i).x(), lay.lineAt(i).width())
            for i in range(lay.lineCount())]


def _bloco_com(doc, texto: str):
    b = doc.begin()
    while b.isValid():
        if texto in b.text():
            return b
        b = b.next()
    return None


def testar_tela() -> None:
    secao("tela: pagina da ancora, posicao e contorno do texto")
    from editdoc.ponte_qt import flutuantes as pf
    rels = [("rId81", RT_IMAGEM, "media/flut1.png")]
    partes = {"word/media/flut1.png": png_cor((0, 160, 0))}
    # Imagem relativa a pagina (align right/bottom), ancorada num paragrafo da segunda pagina.
    enchimento = "".join(f'<w:p><w:r><w:t>Paragrafo {i} {TEXTO}</w:t></w:r></w:p>' for i in range(14))
    corpo = (enchimento + '<w:p>' + ancora(81, URI_IMAGEM, figura("rId81", 1828800, 914400), 1828800,
                                            914400, h=("page", "align", "right"),
                                            v=("page", "align", "bottom"),
                                            quebra="<wp:wrapNone/>")
             + '<w:r><w:t>ANCORA NA PAGINA DOIS</w:t></w:r></w:p>')
    painel = _painel()
    _carregar(painel, doc_do_corpo(corpo, rels, partes))
    lay = painel.layout_pag
    doc = lay.doc
    bloco = _bloco_com(doc, "ANCORA NA PAGINA DOIS")
    pagina_ancora = lay.pagina_de_y(doc.documentLayout().blockBoundingRect(bloco).top())
    checa(pagina_ancora >= 1, f"a ancora esta' na pagina {pagina_ancora + 1}")
    postos = lay.flutuantes.postos(pagina_ancora)
    checa_igual([tuple(round(v) for v in p.rect) for p in postos],
                [(11906 - 2880, 16838 - 1440, 2880, 1440)],
                "a imagem fica na pagina da ancora, no canto de baixo a direita (oraculo)")
    checa(all(not lay.flutuantes.postos(n) for n in range(lay.numero_paginas()) if n != pagina_ancora),
          "e em nenhuma outra pagina")
    painel.close()

    secao("contorno: wrapSquare a esquerda e a direita, wrapTopAndBottom, wrapNone, behindDoc")
    largura_obj = 2880 * 635
    casos = {}
    for nome, h, quebra, atras in (
            ("esquerda", ("margin", "align", "left"), '<wp:wrapSquare wrapText="bothSides"/>', False),
            ("direita", ("margin", "align", "right"), '<wp:wrapSquare wrapText="bothSides"/>', False),
            ("cimabaixo", ("margin", "align", "center"), "<wp:wrapTopAndBottom/>", False),
            ("nenhuma", ("margin", "align", "left"), "<wp:wrapNone/>", False),
            ("atras", ("margin", "align", "left"), '<wp:wrapSquare wrapText="bothSides"/>', True)):
        corpo = ('<w:p>' + ancora(90, URI_FORMA, forma(largura_obj, 2000 * 635), largura_obj, 2000 * 635,
                                  h=h, v=("paragraph", "posOffset", 0), quebra=quebra, atras=atras,
                                  dist=(0, 0, 114300, 114300))
                 + f'<w:r><w:t>{TEXTO}{TEXTO}</w:t></w:r></w:p>')
        painel = _painel()
        _carregar(painel, doc_do_corpo(corpo))
        doc = painel.layout_pag.doc
        casos[nome] = _linhas(doc, _bloco_com(doc, "Texto do paragrafo"))
        painel.close()
    larg = A4.corpo_largura_tw()
    ao_lado = [l for l in casos["esquerda"] if l[0] < 2000]
    abaixo = [l for l in casos["esquerda"] if l[0] >= 2000]
    checa(ao_lado and all(abs(l[1] - (2880 + 180)) < 2 for l in ao_lado),
          f"wrapSquare a esquerda: as linhas ao lado comecam depois do objeto + distR "
          f"(x = {[round(l[1]) for l in ao_lado][:3]})")
    checa(abaixo and all(abs(l[1]) < 2 and abs(l[2] - larg) < 2 for l in abaixo),
          "abaixo do objeto, a linha volta a largura toda (x = 0)")
    ao_lado = [l for l in casos["direita"] if l[0] < 2000]
    checa(ao_lado and all(abs(l[1]) < 2 and l[2] <= larg - 2880 - 180 + 2 for l in ao_lado),
          "wrapSquare a direita: as linhas ao lado comecam em 0 e terminam antes do objeto - distL")
    primeira = casos["cimabaixo"][0]
    segunda = casos["cimabaixo"][1]
    checa(segunda[0] >= 2000 - 1 and abs(segunda[1]) < 2,
          f"wrapTopAndBottom: o texto desce para baixo do objeto (y = {round(segunda[0])})")
    checa(primeira[2] < 1 or primeira[0] >= 2000 - 1,
          "e nenhuma linha com texto fica ao lado dele")
    checa(all(abs(l[1]) < 2 for l in casos["nenhuma"]) and casos["nenhuma"][0][0] < 100,
          "wrapNone: o texto nao muda (x = 0, comeca no topo)")
    checa(all(abs(l[1]) < 2 for l in casos["atras"]),
          "behindDoc: o texto nao contorna (mesmo com wrapSquare no arquivo)")
    # Contraprova: o oraculo de contorno acusa o caso sem contorno.
    checa(not all(abs(l[1] - (2880 + 180)) < 2 for l in casos["nenhuma"] if l[0] < 2000),
          "contraprova: sem quebra, as linhas nao comecam depois do objeto")


# -- pintura ----------------------------------------------------------------------------------

def _folha(layout, n: int, dpi: float = 72.0):
    from PySide6.QtGui import QColor, QImage, QPainter
    from editdoc.interface import impressao
    impressao.preparar(layout)
    pg = layout.pagina_arquivo
    img = QImage(round(pg.largura_tw * dpi / 1440), round(pg.altura_tw * dpi / 1440),
                 QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    impressao.pintar_pagina(p, layout, n, layout.numero_paginas(), impressao.transformacao(dpi, dpi))
    p.end()
    return img


def _cor(img, x_tw: float, y_tw: float, dpi: float = 72.0):
    c = img.pixelColor(round(x_tw * dpi / 1440), round(y_tw * dpi / 1440))
    return c.red(), c.green(), c.blue()


def _escuro(rgb) -> bool:
    return max(rgb) < 110


def testar_pintura() -> None:
    secao("pintura: behindDoc antes do texto, a frente depois; imagem na posicao; PDF")
    usar_fontes_do_documento()
    # Texto grande na primeira linha; a forma cobre o topo do paragrafo.
    texto = '<w:r><w:rPr><w:sz w:val="72"/></w:rPr><w:t>HHHHHHHHHHHHHHHH</w:t></w:r>'
    resultados = {}
    for nome, atras, com_forma in (("sem", False, False), ("atras", True, True),
                                   ("frente", False, True)):
        obj = ancora(91, URI_FORMA, forma(9026 * 635, 1200 * 635, "FF0000"), 9026 * 635, 1200 * 635,
                     h=("margin", "posOffset", 0), v=("paragraph", "posOffset", 0),
                     quebra="<wp:wrapNone/>", atras=atras) if com_forma else ""
        painel = _painel()
        _carregar(painel, doc_do_corpo('<w:p>' + obj + texto + '</w:p>'))
        resultados[nome] = _folha(painel.layout_pag, 0, dpi=144)
        painel.close()
    sem = resultados["sem"]
    # Um ponto de tinta do texto dentro da area da forma (margem + topo do corpo).
    alvo = None
    for yy in range(1440 + 100, 1440 + 1150, 10):
        for xx in range(1440 + 50, 1440 + 4000, 10):
            if _escuro(_cor(sem, xx, yy, 144)):
                alvo = (xx, yy)
                break
        if alvo:
            break
    checa(alvo is not None, f"ha' tinta de texto na area da forma ({alvo})")
    if alvo:
        atras = _cor(resultados["atras"], *alvo, 144)
        frente = _cor(resultados["frente"], *alvo, 144)
        checa(_escuro(atras), f"behindDoc: a letra continua por cima da forma vermelha ({atras})")
        checa(frente[0] > 200 and frente[1] < 60 and frente[2] < 60,
              f"objeto na frente: a forma vermelha cobre a letra ({frente})")
        # Contraprova: o oraculo acusa a ordem trocada.
        checa(not _escuro(frente), "contraprova: na frente, a letra nao aparece")
        fundo = _cor(resultados["atras"], 1440 + 9000, 1440 + 1100, 144)
        checa(fundo[0] > 200 and fundo[1] < 60, f"fora das letras, o fundo e' a forma ({fundo})")

    rels = [("rId82", RT_IMAGEM, "media/flut2.png")]
    partes = {"word/media/flut2.png": png_cor((0, 0, 230))}
    obj = ancora(92, URI_IMAGEM, figura("rId82", 1828800, 914400), 1828800, 914400,
                 h=("page", "posOffset", 635000 * 3), v=("page", "posOffset", 635000 * 5),
                 quebra="<wp:wrapNone/>")
    painel = _painel()
    _carregar(painel, doc_do_corpo('<w:p>' + obj + '<w:r><w:t>Imagem</w:t></w:r></w:p>', rels, partes))
    img = _folha(painel.layout_pag, 0)
    dentro = _cor(img, 3000 + 1440, 5000 + 720)
    fora = _cor(img, 3000 - 200, 5000 + 720)
    checa(dentro[2] > 180 and dentro[0] < 60, f"a imagem azul esta' em (3000, 5000) twips ({dentro})")
    checa(fora == (255, 255, 255), f"e nao antes dela ({fora})")
    from editdoc.interface import impressao
    from leitor_pdf import ler_pdf
    pdf = ler_pdf(impressao.gerar_pdf(painel.layout_pag, [0], impressao.Metadados()))
    checa(pdf.paginas and pdf.paginas[0].imagens >= 1, "o PDF tem a imagem na pagina")
    # A matriz do Do da imagem. O QPdfWriter a 1440 dpi escreve em twips, com a origem no
    # alto da folha: "s 0 0 s x y cm" e depois "w 0 0 -h 0 h cm /Im Do".
    matrizes = re.findall(rb"([-\d.]+) 0 0 ([-\d.]+) ([-\d.]+) ([-\d.]+) cm\s+([-\d.]+) 0 0 "
                          rb"(-?[\d.]+) [-\d.]+ [-\d.]+ cm /\w+\s*Do", pdf.conteudo_bruto)
    checa(bool(matrizes), f"o PDF desenha a imagem com uma matriz ({len(matrizes)})")
    if matrizes:
        sx, sy, x, y, w, h = (float(v) for v in matrizes[-1])
        checa((round(x), round(y), round(sx * w), round(abs(sy * h))) == (3000, 5000, 2880, 1440),
              f"no PDF a imagem esta' em (3000, 5000) twips, 2880 x 1440 ({x}, {y}, {sx * w}, {sy * h})")
    painel.close()

    secao("cabecalho: objeto atras do texto, em todas as paginas")
    cab = ('<w:p>' + ancora(93, URI_FORMA, forma(11906 * 635, 1300 * 635, "003366"),
                            11906 * 635, 1300 * 635, h=("page", "posOffset", 0),
                            v=("page", "posOffset", 0), quebra="<wp:wrapNone/>", atras=True)
           + '<w:r><w:t>Cabeçalho</w:t></w:r></w:p>')
    painel = _painel()
    _carregar(painel, doc_do_corpo('<w:p><w:r><w:t>Corpo</w:t></w:r></w:p>', cabecalho=cab,
                                   paragrafos_depois=40))
    total = painel.layout_pag.numero_paginas()
    checa(total >= 2, f"o documento tem {total} paginas")
    for n in (0, total - 1):
        img = _folha(painel.layout_pag, n)
        c = _cor(img, 11000, 300)
        checa(c == (0, 0x33, 0x66), f"pagina {n + 1}: a faixa do cabecalho (003366) no topo ({c})")
        checa(_cor(img, 11000, 1500) == (255, 255, 255), f"pagina {n + 1}: e so' ate' a altura dela")
    painel.close()


# -- ida e volta ----------------------------------------------------------------------------------

def _c14n(xml: bytes) -> bytes:
    return etree.tostring(etree.fromstring(xml), method="c14n")


def testar_ida_e_volta() -> None:
    secao("ida e volta: XML de cada objeto igual (c14n), passando pelo Qt")
    from editdoc.ponte_qt import de_qt
    rels = [("rId81", RT_IMAGEM, "media/flut1.png")]
    partes = {"word/media/flut1.png": png_cor((0, 160, 0))}
    corpo = ('<w:p>' + ancora(81, URI_IMAGEM, figura("rId81", 1828800, 914400), 1828800, 914400)
             + '<w:r><w:t>Texto ao lado.</w:t></w:r>'
             + ancora(82, URI_FORMA, forma(914400, 914400, texto="Caixa"), 914400, 914400,
                      quebra="<wp:wrapTopAndBottom/>")
             + ancora(83, URI_FORMA, forma(914400, 914400, prst="ellipse"), 914400, 914400,
                      quebra="<wp:wrapNone/>", atras=True)
             + ancora(84, URI_GRUPO, grupo(914400, 914400), 914400, 914400) + VML_ABSOLUTO
             + '</w:p>')
    docx = doc_do_corpo(corpo, rels, partes)
    modelo, _ = ler(docx)
    objetos = [r.objeto for p in paragrafos_de(modelo.paragrafos) for r in p.runs if r.objeto]
    checa_igual(len(objetos), 5, "cinco objetos flutuantes lidos")
    checa(all(o.flutuante for o in objetos), "todos marcados como flutuantes")
    painel = _painel()
    _carregar(painel, docx)
    from editdoc.ponte_qt import flutuantes as pf
    from editdoc.ponte_qt import opacos as pq_opacos
    doc = painel.documento_corpo()
    com_quadro = [p for p in pq_opacos.posicoes_de_opacos(doc)
                  if pf._formato_em(doc, p).objectIndex() >= 0]
    checa_igual(len(com_quadro), 3, "imagem, caixa (topo e base) e grupo reservam espaco (float do Qt)")
    extraido = de_qt.extrair(doc) if hasattr(de_qt, "extrair") else None
    if extraido is None:
        extraido = Documento(paragrafos=de_qt.extrair_blocos(doc, A4.corpo_largura_tw()))
    voltaram = [r.objeto for p in paragrafos_de(extraido.paragrafos) for r in p.runs if r.objeto]
    checa_igual([_c14n(o.xml) for o in voltaram], [_c14n(o.xml) for o in objetos],
                "Qt -> modelo: o XML de cada objeto e' o mesmo (c14n), sem nada da tela")
    from editdoc.formato_docx import opacos as fx_opacos
    gravado = escrever(Documento(paragrafos=extraido.paragrafos, estilos=modelo.estilos,
                                 numeracao=modelo.numeracao, cabecalhos=modelo.cabecalhos,
                                 pagina=modelo.pagina))
    modelo2, _ = ler(gravado)
    objetos2 = [r.objeto for p in paragrafos_de(modelo2.paragrafos) for r in p.runs if r.objeto]
    checa_igual([fx_opacos.assinatura(o) for o in objetos2],
                [fx_opacos.assinatura(o) for o in objetos],
                "gravar e reler: cada objeto volta igual (c14n, com os rIds pelo conteudo)")
    # O XML gravado so' muda no rId (renumerado pelo escritor, como desde a 0.1.2).
    sem_rid = [re.sub(rb'r:embed="[^"]*"', b"", _c14n(o.xml)) for o in objetos2]
    checa_igual(sem_rid, [re.sub(rb'r:embed="[^"]*"', b"", _c14n(o.xml)) for o in objetos],
                "e o XML de cada objeto e' identico byte a byte fora o rId (c14n)")
    painel.close()


# -- interacao ------------------------------------------------------------------------------------

def testar_interacao() -> None:
    secao("interacao: clique seleciona, Delete apaga e o texto volta, desfazer traz de volta")
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    from editdoc.interface import dialogo_caixa
    from editdoc.ponte_qt import opacos as pq_opacos
    corpo = ('<w:p>' + ancora(95, URI_FORMA, forma(2880 * 635, 2000 * 635, "FF8800", texto="Caixa X"),
                              2880 * 635, 2000 * 635, h=("margin", "align", "left"),
                              v=("paragraph", "posOffset", 0), dist=(0, 0, 114300, 114300))
             + f'<w:r><w:t>{TEXTO}</w:t></w:r></w:p>')
    painel = _painel()
    _carregar(painel, doc_do_corpo(corpo))
    painel.show()
    drenar_eventos()
    doc = painel.documento_corpo()
    bloco = _bloco_com(doc, "Texto do paragrafo")
    checa(_linhas(doc, bloco)[0][1] > 2000, "antes: a primeira linha comeca depois da caixa")
    pos = pq_opacos.posicoes_de_opacos(doc)[0]
    r = painel.retangulo_flutuante_na_tela(pos)
    checa(r is not None and r.width() > 10, f"retangulo da caixa na tela ({r})")
    QTest.mouseClick(painel.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     r.center().toPoint())
    c = painel.textCursor()
    checa_igual((c.selectionStart(), c.selectionEnd()), (pos, pos + 1), "clique na caixa seleciona o objeto")
    painel._limpar_cache()
    img = painel.viewport().grab().toImage()
    # Reescrita na 0.1.9: o meio de cada lado ganhou uma alca de redimensionar (oito alcas, como
    # no Word), branca por dentro; o contorno e' conferido a um quarto da altura, entre as alcas.
    borda = img.pixelColor(round(r.left()), round(r.top() + r.height() / 4))
    checa((borda.red(), borda.green(), borda.blue()) == (0, 120, 215),
          f"o contorno de selecao aparece na borda do objeto ({borda.name()})")
    abriu = []
    original = dialogo_caixa.editar
    dialogo_caixa.editar = lambda editor, p: abriu.append(p) or False
    try:
        QTest.mouseDClick(painel.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                          r.center().toPoint())
    finally:
        dialogo_caixa.editar = original
    checa_igual(abriu, [pos], "duplo clique na caixa de texto abre o editor da caixa")
    QTest.mouseClick(painel.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     r.center().toPoint())
    QTest.keyClick(painel, Qt.Key.Key_Delete)
    drenar_eventos(4)
    painel.layout_pag.atualizar_flutuantes()
    checa_igual(len(pq_opacos.posicoes_de_opacos(doc)), 0, "Delete apaga o objeto")
    bloco = _bloco_com(doc, "Texto do paragrafo")
    checa(all(abs(l[1]) < 2 for l in _linhas(doc, bloco)),
          "sem o objeto, as linhas voltam a largura toda (o float orfao foi zerado)")
    checa(doc.isModified(), "o documento fica alterado")
    com_cache = painel.viewport().grab().toImage()
    painel._limpar_cache()
    checa(com_cache == painel.viewport().grab().toImage(),
          "a tela depois de apagar e' igual ao quadro refeito sem cache (nada velho nos tiles)")
    painel.undo()
    drenar_eventos(4)
    painel.layout_pag.atualizar_flutuantes()
    checa_igual(len(pq_opacos.posicoes_de_opacos(doc)), 1, "desfazer traz o objeto de volta")
    bloco = _bloco_com(doc, "Texto do paragrafo")
    checa(_linhas(doc, bloco)[0][1] > 2000, "e o texto volta a contornar")
    checa(not doc.isModified(), "um desfazer devolve o documento ao estado salvo")
    painel.redo()
    drenar_eventos(4)
    painel.layout_pag.atualizar_flutuantes()
    bloco = _bloco_com(doc, "Texto do paragrafo")
    checa(len(pq_opacos.posicoes_de_opacos(doc)) == 0
          and all(abs(l[1]) < 2 for l in _linhas(doc, bloco)),
          "refazer apaga de novo, e o texto volta a largura toda")
    painel.undo()
    drenar_eventos(4)
    # Backspace logo depois do objeto (sem selecao) tambem apaga: o Qt recusaria o caractere.
    c = painel.textCursor()
    c.setPosition(pos + 1)
    painel.setTextCursor(c)
    QTest.keyClick(painel, Qt.Key.Key_Backspace)
    drenar_eventos(4)
    checa_igual(len(pq_opacos.posicoes_de_opacos(doc)), 0, "Backspace logo depois do objeto o apaga")
    painel.undo()
    drenar_eventos(4)
    checa_igual(len(pq_opacos.posicoes_de_opacos(doc)), 1, "e desfazer o traz de volta")
    doc.setModified(False)
    painel.close()


# -- desempenho -----------------------------------------------------------------------------------

def _p95(valores):
    valores = sorted(valores)
    return valores[min(len(valores) - 1, round(0.95 * (len(valores) - 1)))]


def _medir_digitacao(docx: bytes, amostras: int = 60) -> float:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    painel = _painel()
    _carregar(painel, docx)
    painel.show()
    drenar_eventos()
    c = painel.textCursor()
    c.setPosition(5)
    painel.setTextCursor(c)
    painel.setFocus()
    painel.viewport().grab()
    tempos = []
    for _ in range(amostras):
        t = time.perf_counter()
        QTest.keyClick(painel, Qt.Key.Key_A)
        painel.viewport().grab()
        tempos.append((time.perf_counter() - t) * 1000)
    painel.documento_corpo().setModified(False)
    painel.close()
    return _p95(tempos)


def testar_desempenho() -> None:
    secao("desempenho: digitar com e sem objetos flutuantes (p95 de 60 teclas, com pintura)")
    texto = "".join(f'<w:p><w:r><w:t>Paragrafo {i}. {TEXTO}</w:t></w:r></w:p>' for i in range(120))
    rels = [("rId81", RT_IMAGEM, "media/flut1.png")]
    partes = {"word/media/flut1.png": png_cor((0, 160, 0))}
    objs = ("<w:p>" + ancora(81, URI_IMAGEM, figura("rId81", 1828800, 914400), 1828800, 914400,
                             h=("margin", "align", "left")) + "<w:r><w:t>Primeiro.</w:t></w:r></w:p>"
            + "<w:p>" + ancora(85, URI_FORMA, forma(1828800, 914400, texto="Caixa"), 1828800, 914400,
                               h=("margin", "align", "right")) + "<w:r><w:t>Segundo.</w:t></w:r></w:p>")
    sem = _medir_digitacao(doc_do_corpo("<w:p><w:r><w:t>Primeiro.</w:t></w:r></w:p>" + texto))
    com = _medir_digitacao(doc_do_corpo(objs + texto, rels, partes))
    print(f"         digitar: sem objetos p95 {sem:.1f} ms; com objetos p95 {com:.1f} ms")
    checa(com <= 16.0 or com <= sem * 1.5 + 2.0,
          f"com objetos flutuantes o p95 fica no gate (<= 16 ms) ou perto do sem objetos "
          f"({com:.1f} x {sem:.1f} ms)")


def main() -> int:
    testar_posicao()
    testar_leitura()
    testar_tela()
    testar_pintura()
    testar_ida_e_volta()
    testar_interacao()
    testar_desempenho()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
