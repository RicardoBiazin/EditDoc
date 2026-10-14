"""Mover e redimensionar objetos com o mouse e o teclado, e a quebra de texto (0.1.9).

- XML (sem Qt): posOffset e extent contra o oraculo em EMU, o align vira posOffset, o resto do
  objeto igual em c14n (com contraprova), grupo com chOff/chExt intactos, as sete quebras,
  wp:inline <-> wp:anchor com os atributos do esquema, VML (style e w10:wrap), limites e o
  validador (que acusa o caso proposital);
- arraste na VistaPaginas com QTest (press, move, release): o XML gravado, o contorno fantasma
  durante o arraste (o objeto so' muda ao soltar), o texto que volta a contornar, desfazer e
  refazer num passo, Shift trava a proporcao, a alca do lado, setas e Ctrl+setas, Esc;
- reancorar ao arrastar para outra pagina; objeto preservado na linha com alcas; imagem na linha
  (M4) que continua redimensionando;
- quebra de texto (galeria e dialogo): as sete, linha <-> flutuante (a imagem do EditDoc vira
  objeto e volta a ser imagem), gravar com validador e conferencia pos-gravacao;
- cabecalho em edicao: o objeto se seleciona, arrasta e desfaz no cabecalho;
- desempenho: o arraste (mover o mouse e pintar) fica no gate de 16 ms.
"""

from __future__ import annotations

import statistics
import time

from ajudantes import checa, checa_igual, drenar_eventos, preparar_qt, resumir, secao
import teste_flutuantes as tf

preparar_qt()

from lxml import etree  # noqa: E402
from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx import posicao  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.formato_docx.nomes import WP_NS  # noqa: E402
from editdoc.modelo import flutuantes as mf  # noqa: E402
from editdoc.modelo.documento import paragrafos_de  # noqa: E402
from editdoc.modelo.pagina import Pagina  # noqa: E402

A4 = Pagina()
WP = "{%s}%%s" % WP_NS
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}%s"
ESQ = Qt.MouseButton.LeftButton
NADA = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


# -- utilidades ---------------------------------------------------------------------------

def _objetos(modelo):
    return [r.objeto for p in paragrafos_de(modelo.paragrafos) for r in p.runs if r.objeto]


def _raiz(xml: bytes):
    return etree.fromstring(xml)


def _sem_posicao_e_tamanho(xml: bytes) -> bytes:
    """O XML sem o que mover e redimensionar podem mudar: positionH/V, simplePos, extent, o
    a:ext do xfrm de cima, o style do VML. O resto tem de ficar igual (c14n)."""
    raiz = _raiz(xml)
    for tag in ("positionH", "positionV"):
        for el in list(raiz.iter(WP % tag)):
            el.getparent().replace(el, etree.Element(WP % tag))
    for el in raiz.iter(WP % "extent", WP % "simplePos"):
        el.attrib.clear()
    for el in raiz.iter(A % "xfrm"):
        pai = el.getparent()
        if pai is not None and etree.QName(pai).localname in ("spPr", "grpSpPr") and \
                etree.QName(pai.getparent()).localname in ("pic", "wsp", "wgp"):
            for ext in el.findall(A % "ext"):
                ext.attrib.clear()
    for el in raiz.iter():
        if isinstance(el.tag, str) and el.get("style") is not None and \
                etree.QName(el).namespace == "urn:schemas-microsoft-com:vml":
            el.set("style", "")
    return etree.tostring(raiz, method="c14n")


def _pos(xml: bytes, eixo: str) -> tuple:
    raiz = _raiz(xml)
    el = next(raiz.iter(WP % ("positionH" if eixo == "h" else "positionV")))
    filho = next(iter(el))
    return el.get("relativeFrom"), etree.QName(filho).localname, (filho.text or "").strip()


def _extent(xml: bytes) -> tuple:
    el = next(_raiz(xml).iter(WP % "extent"))
    return int(el.get("cx")), int(el.get("cy"))


def _xfrm_ext(xml: bytes) -> tuple:
    raiz = _raiz(xml)
    for el in raiz.iter(A % "xfrm"):
        pai = el.getparent()
        if etree.QName(pai).localname in ("spPr", "grpSpPr"):
            ext = el.find(A % "ext")
            return int(ext.get("cx")), int(ext.get("cy"))
    return None


def _painel():
    return tf._painel()


def _carregar(painel, docx: bytes):
    return tf._carregar(painel, docx)


def _clique(painel, ponto) -> None:
    QTest.mouseClick(painel.viewport(), ESQ, NADA, QPoint(round(ponto.x()), round(ponto.y())))


def _arrastar(painel, de: QPointF, para: QPointF, mods=NADA, passos: int = 6,
              antes_de_soltar=None) -> None:
    vp = painel.viewport()
    a = QPoint(round(de.x()), round(de.y()))
    b = QPoint(round(para.x()), round(para.y()))
    QTest.mousePress(vp, ESQ, mods, a)
    for i in range(1, passos + 1):
        p = QPoint(round(a.x() + (b.x() - a.x()) * i / passos),
                   round(a.y() + (b.y() - a.y()) * i / passos))
        QTest.mouseMove(vp, p)
    if antes_de_soltar is not None:
        antes_de_soltar()
    QTest.mouseRelease(vp, ESQ, mods, b)
    drenar_eventos(2)


def _objeto_do_corpo(painel, n: int = 0):
    from editdoc.ponte_qt import opacos as pq_opacos
    doc = painel.documento_corpo()
    pos = pq_opacos.posicoes_de_opacos(doc)[n]
    return pos, pq_opacos.objeto_de(tf.pf_formato(doc, pos)) if hasattr(tf, "pf_formato") else \
        _obj(doc, pos)


def _obj(doc, pos):
    from editdoc.ponte_qt import links as pq_links
    from editdoc.ponte_qt import opacos as pq_opacos
    return pq_opacos.objeto_de(pq_links.formato_em(doc, pos))


def _primeiro_opaco(doc):
    from editdoc.ponte_qt import opacos as pq_opacos
    pos = pq_opacos.posicoes_de_opacos(doc)[0]
    return pos, _obj(doc, pos)


# -- XML, sem Qt --------------------------------------------------------------------------

def _xml_de(corpo: str, rels=(), partes=None) -> list:
    modelo, _ = ler(tf.doc_do_corpo(corpo, rels, partes))
    return _objetos(modelo)


def testar_xml() -> None:
    secao("XML: posOffset e extent contra o oraculo, o resto igual em c14n")
    cx, cy = 2880 * 635, 2000 * 635
    caixa = tf.ancora(95, tf.URI_FORMA, tf.forma(cx, cy, "FF8800", texto="Caixa"), cx, cy,
                      h=("margin", "align", "center"), v=("paragraph", "posOffset", 0))
    obj = _xml_de('<w:p>' + caixa + '<w:r><w:t>x</w:t></w:r></w:p>')[0]
    novo = posicao.aplicar(obj.xml, posicao.Mudanca(h=("margin", 635000), v=("paragraph", -127000),
                                                    tamanho=(1000000, 500000)))
    checa_igual(_pos(novo, "h"), ("margin", "posOffset", "635000"),
                "o align vira posOffset (EMU) no mesmo relativeFrom, como o Word")
    checa_igual(_pos(novo, "v"), ("paragraph", "posOffset", "-127000"),
                "posOffset vertical negativo e' valido (ST_PositionOffset)")
    checa_igual(_extent(novo), (1000000, 500000), "wp:extent com o tamanho novo")
    checa_igual(_xfrm_ext(novo), (1000000, 500000), "e o a:ext do wps:spPr acompanha")
    checa_igual(_sem_posicao_e_tamanho(novo), _sem_posicao_e_tamanho(obj.xml),
                "o resto do objeto fica identico em c14n")
    sabotado = novo.replace(b'FF8800', b'FF8801')
    checa(_sem_posicao_e_tamanho(sabotado) != _sem_posicao_e_tamanho(obj.xml),
          "contraprova: o comparador acusa uma mudanca fora da posicao (a cor)")
    checa_igual(posicao.aplicar(novo, posicao.Mudanca(h=("margin", 635000))), novo,
                "a mesma posicao de novo nao muda nada (bytes iguais)")
    obj2 = posicao.objeto_com(obj, posicao.Mudanca(tamanho=(1000000, 500000)))
    checa_igual((obj2.largura_emu, obj2.altura_emu, obj2.flutuante), (1000000, 500000, True),
                "objeto_com refaz as medidas que o leitor tiraria")

    secao("XML: grupo mantem chOff/chExt; linha reta mantem o lado zero; simplePos")
    grp = tf.ancora(96, tf.URI_GRUPO, tf.grupo(914400, 914400), 914400, 914400)
    obj = _xml_de('<w:p>' + grp + '</w:p>')[0]
    novo = posicao.aplicar(obj.xml, posicao.Mudanca(tamanho=(1828800, 457200)))
    raiz = _raiz(novo)
    xf = next(raiz.iter(A % "xfrm"))
    checa_igual((xf.find(A % "ext").get("cx"), xf.find(A % "ext").get("cy")), ("1828800", "457200"),
                "o a:ext do grpSpPr muda")
    checa_igual((xf.find(A % "chOff").attrib, xf.find(A % "chExt").attrib),
                ({"x": "1000", "y": "1000"}, {"cx": "1000", "cy": "1000"}),
                "chOff e chExt ficam: os filhos escalam com o grupo")
    checa_igual(_sem_posicao_e_tamanho(novo), _sem_posicao_e_tamanho(obj.xml),
                "o resto do grupo fica identico em c14n")
    linha = tf.ancora(97, tf.URI_FORMA, tf.forma(914400, 0, prst="line"), 914400, 0)
    obj = _xml_de('<w:p>' + linha + '</w:p>')[0]
    novo = posicao.aplicar(obj.xml, posicao.Mudanca(tamanho=(1828800, 500000)))
    checa_igual(_extent(novo), (1828800, 0), "linha reta: o lado zero continua zero")
    simples = tf.ancora(98, tf.URI_FORMA, tf.forma(914400, 914400), 914400, 914400).replace(
        'simplePos="0"', 'simplePos="1"').replace('<wp:simplePos x="0" y="0"/>',
                                                  '<wp:simplePos x="100" y="200"/>')
    obj = _xml_de('<w:p>' + simples + '</w:p>')[0]
    novo = posicao.aplicar(obj.xml, posicao.Mudanca(simples=(3000, 4000)))
    sp = next(_raiz(novo).iter(WP % "simplePos"))
    checa_igual((sp.get("x"), sp.get("y")), ("3000", "4000"), "simplePos=1: muda o wp:simplePos")

    secao("XML: as sete quebras, e wp:inline <-> wp:anchor com o minimo do esquema")
    obj = _xml_de('<w:p>' + caixa + '</w:p>')[0]
    esperados = {"quadrado": ("wrapSquare", "0"), "comprimido": ("wrapTight", "0"),
                 "atraves": ("wrapThrough", "0"), "superior_inferior": ("wrapTopAndBottom", "0"),
                 "atras": ("wrapNone", "1"), "frente": ("wrapNone", "0")}
    for quebra, (tag, atras) in esperados.items():
        novo = posicao.aplicar(obj.xml, posicao.Mudanca(quebra=quebra))
        anc = next(_raiz(novo).iter(WP % "anchor"))
        wraps = [etree.QName(f).localname for f in anc if etree.QName(f).localname.startswith("wrap")]
        checa_igual((wraps, anc.get("behindDoc")), ([tag], atras), f"{quebra}: {tag}, behindDoc={atras}")
        checa_igual(posicao.estado(novo).quebra, quebra, f"{quebra}: o estado lido volta igual")
        if tag in ("wrapTight", "wrapThrough"):
            checa(anc.find(WP % tag).find(WP % "wrapPolygon") is not None,
                  f"{tag} leva o wp:wrapPolygon que o esquema exige")
        checa_igual(posicao.problemas(_raiz(novo)), [], f"{quebra}: o validador aceita")
    na_linha = posicao.aplicar(obj.xml, posicao.Mudanca(quebra="linha"))
    raiz = _raiz(na_linha)
    checa(next(raiz.iter(WP % "anchor"), None) is None and next(raiz.iter(WP % "inline"), None) is not None,
          "Alinhado ao texto: wp:anchor vira wp:inline")
    inline = next(raiz.iter(WP % "inline"))
    checa_igual([etree.QName(f).localname for f in inline],
                ["extent", "effectExtent", "docPr", "cNvGraphicFramePr", "graphic"],
                "wp:inline com os filhos de CT_Inline, na ordem")
    de_volta = posicao.aplicar(na_linha, posicao.Mudanca(quebra="quadrado", z=251700000,
                                                         h=("column", 12700), v=("paragraph", 0)))
    anc = next(_raiz(de_volta).iter(WP % "anchor"))
    checa(all(anc.get(a) is not None for a in posicao.ATRIBUTOS_DA_ANCORA),
          "wp:inline -> wp:anchor com simplePos, relativeHeight, behindDoc, locked, layoutInCell, "
          "allowOverlap")
    checa_igual(anc.get("relativeHeight"), "251700000", "relativeHeight e' o pedido (unico)")
    checa_igual([etree.QName(f).localname for f in anc],
                ["simplePos", "positionH", "positionV", "extent", "effectExtent", "wrapSquare",
                 "docPr", "cNvGraphicFramePr", "graphic"], "wp:anchor com os filhos na ordem de CT_Anchor")
    checa_igual(posicao.problemas(_raiz(de_volta)), [], "o validador aceita o objeto convertido")
    checa_igual(etree.tostring(next(_raiz(de_volta).iter(A % "graphic")), method="c14n"),
                etree.tostring(next(_raiz(obj.xml).iter(A % "graphic")), method="c14n"),
                "o a:graphic (o desenho) atravessa as conversoes identico")

    secao("XML: VML (style e w10:wrap), o resto do estilo na ordem")
    vml = _xml_de('<w:p>' + tf.VML_ABSOLUTO + '</w:p>')[0]
    novo = posicao.aplicar(vml.xml, posicao.Mudanca(h=("page", 2 * 914400), v=("page", 914400),
                                                    tamanho=(914400, 457200)))
    estilo = next(x for x in _raiz(novo).iter() if isinstance(x.tag, str) and x.get("style")).get("style")
    checa_igual(estilo, "position:absolute;margin-left:144pt;margin-top:72pt;width:72pt;"
                        "height:36pt;z-index:251660000;mso-position-horizontal-relative:page;"
                        "mso-position-vertical-relative:page",
                "VML: margin-left/top e width/height em pt, o resto do estilo na mesma ordem")
    checa_igual(_sem_posicao_e_tamanho(novo), _sem_posicao_e_tamanho(vml.xml),
                "VML: o resto do objeto identico em c14n")
    atras = posicao.aplicar(vml.xml, posicao.Mudanca(quebra="atras"))
    checa(posicao.estado(atras).quebra == "atras" and "z-index:-251660000" in atras.decode(),
          "VML atras do texto: z-index negativo")
    quadrado = posicao.aplicar(vml.xml, posicao.Mudanca(quebra="quadrado"))
    checa('type="square"' in quadrado.decode(), "VML quadrado: w10:wrap type=square")

    secao("limites: ST_PositionOffset, ST_PositiveCoordinate e o teto")
    obj = _xml_de('<w:p>' + caixa + '</w:p>')[0]
    longe = posicao.aplicar(obj.xml, posicao.Mudanca(h=("page", 10 ** 12), v=("page", -10 ** 12),
                                                     tamanho=(-5, 10 ** 15)))
    checa_igual(_pos(longe, "h")[2], str(mf.POSICAO_MAXIMA_EMU), "posOffset limitado a +55,88 cm")
    checa_igual(_pos(longe, "v")[2], str(-mf.POSICAO_MAXIMA_EMU), "e a -55,88 cm")
    checa_igual(_extent(longe), (mf.TAMANHO_MINIMO_EMU, mf.TAMANHO_MAXIMO_EMU),
                "extent nunca negativo (minimo 1 px96) nem acima do maior papel")
    checa_igual(posicao.problemas(_raiz(longe)), [], "o validador aceita os limites")
    ruim = obj.xml.replace(b'relativeHeight="251659264" ', b"").replace(
        b"<wp:posOffset>0</wp:posOffset>", b"<wp:posOffset>99999999999</wp:posOffset>")
    problemas = posicao.problemas(_raiz(ruim))
    checa(any("relativeHeight" in p for p in problemas) and
          any("ST_PositionOffset" in p for p in problemas),
          f"contraprova: o validador acusa atributo faltando e posOffset fora da faixa ({problemas})")
    from editdoc.formato_docx.nomes import W
    corpo = etree.Element("{%s}document" % W)
    corpo.append(_raiz(ruim))
    checa(any("relativeHeight" in p for p in ordem.validar_estrutura(corpo)),
          "e o validador de estrutura (antes de gravar) junta essa conferencia")

    secao("conta: deslocamento_para e' o caminho de volta de retangulo")
    ref = mf.Referencia(pagina=A4, indice=0, paragrafo_y=3000.0, linha_y=3100.0,
                        coluna_x=1440.0, coluna_w=float(A4.corpo_largura_tw()), caractere_x=2000.0)
    for rel_h, rel_v in (("page", "page"), ("margin", "margin"), ("column", "paragraph"),
                         ("character", "line"), ("insideMargin", "topMargin")):
        h = mf.deslocamento_para("h", rel_h, ref, 5000.0)
        v = mf.deslocamento_para("v", rel_v, ref, 7000.0)
        anc = mf.Ancoragem(h_rel=rel_h, h_desloc=h, v_rel=rel_v, v_desloc=v, largura=635000,
                           altura=635000)
        x, y, _w, _h = mf.retangulo(anc, ref)
        checa((round(x), round(y)) == (5000, 7000),
              f"{rel_h}/{rel_v}: posOffset ({h}, {v}) volta ao ponto (5000, 7000) twips")
    checa_igual(mf.deslocamento_para("h", "margin", ref, 1440.0 + 1000.0), 1000 * 635,
                "oraculo: 1000 twips da margem = 635000 EMU")


# -- arraste ------------------------------------------------------------------------------------

def _doc_caixa(quebra='<wp:wrapSquare wrapText="bothSides"/>', h=("margin", "posOffset", 0),
               v=("paragraph", "posOffset", 0), cor="FF8800", texto="Caixa X", depois=0, uri=None,
               conteudo=None, cx=2880 * 635, cy=2000 * 635) -> bytes:
    obj = tf.ancora(95, uri or tf.URI_FORMA, conteudo or tf.forma(cx, cy, cor, texto=texto), cx, cy,
                    h=h, v=v, quebra=quebra, dist=(0, 0, 114300, 114300))
    corpo = '<w:p>' + obj + f'<w:r><w:t>{tf.TEXTO}{tf.TEXTO}</w:t></w:r></w:p>'
    corpo += "".join(f'<w:p><w:r><w:t>Paragrafo {i}. {tf.TEXTO}</w:t></w:r></w:p>'
                     for i in range(depois))
    return tf.doc_do_corpo(corpo)


def _abrir(docx: bytes):
    painel = _painel()
    _carregar(painel, docx)
    painel.show()
    drenar_eventos()
    painel.verticalScrollBar().setValue(0)
    drenar_eventos(2)
    return painel


def testar_arraste() -> None:
    secao("arraste: mover com o mouse grava o posOffset e o texto volta a contornar")
    painel = _abrir(_doc_caixa())
    doc = painel.documento_corpo()
    pos, obj0 = _primeiro_opaco(doc)
    r = painel.retangulo_flutuante_na_tela(pos)
    m = painel.mapa()
    checa(r is not None and r.width() > 20, f"a caixa aparece na tela ({r})")
    inicio = r.center()
    fim = QPointF(inicio.x() + 120, inicio.y() + 60)
    fantasmas = []
    xml_durante = []

    def durante():
        painel._limpar_cache()
        img = painel.viewport().grab().toImage()
        fantasmas.append(painel._retangulo_fantasma())
        xml_durante.append(_obj(doc, pos).xml)
        fantasmas.append(img)

    _arrastar(painel, inicio, fim, antes_de_soltar=durante)
    ghost = fantasmas[0]
    checa(ghost is not None and abs(ghost.left() - (r.left() + 120)) <= 1.5
          and abs(ghost.top() - (r.top() + 60)) <= 1.5,
          f"durante o arraste, o contorno fantasma acompanha o mouse ({ghost})")
    if ghost is not None:
        img = fantasmas[1]
        cor = img.pixelColor(round(ghost.left()), round(ghost.center().y()))
        checa((cor.red(), cor.green(), cor.blue()) == (0, 120, 215),
              f"o fantasma e' pintado (tracejado azul na borda: {cor.name()})")
    checa_igual(xml_durante[0], obj0.xml, "durante o arraste o objeto (e o texto) nao mudam")
    pos2, obj1 = _primeiro_opaco(doc)
    esperado_h = round(120 / m.escala * 635)
    esperado_v = round(60 / m.escala * 635)
    h = _pos(obj1.xml, "h")
    v = _pos(obj1.xml, "v")
    checa(h[0] == "margin" and abs(int(h[2]) - esperado_h) <= 700,
          f"posOffset horizontal = 120 px de tela em EMU (oraculo {esperado_h}, gravado {h})")
    checa(v[0] == "paragraph" and abs(int(v[2]) - esperado_v) <= 700,
          f"posOffset vertical = 60 px de tela em EMU (oraculo {esperado_v}, gravado {v})")
    checa_igual(_sem_posicao_e_tamanho(obj1.xml), _sem_posicao_e_tamanho(obj0.xml),
                "so' a posicao mudou no XML do objeto (c14n)")
    checa_igual(painel.flutuante_selecionado(), pos2, "o objeto continua selecionado")
    painel.layout_pag.atualizar_flutuantes()
    bloco = tf._bloco_com(doc, "Texto do paragrafo")
    linhas = tf._linhas(doc, bloco)
    x_novo = 120 / m.escala
    ao_lado = [l for l in linhas if 60 / m.escala + 100 < l[0] < 60 / m.escala + 1900]
    checa(ao_lado and all(abs(l[1] - (x_novo + 2880 + 180)) < 3 for l in ao_lado),
          f"o texto contorna o objeto no lugar novo (x = {[round(l[1]) for l in ao_lado][:3]}, "
          f"esperado {round(x_novo + 3060)})")
    com_cache = painel.viewport().grab().toImage()
    painel._limpar_cache()
    checa(com_cache == painel.viewport().grab().toImage(),
          "a tela depois de soltar e' igual ao quadro refeito sem cache")
    checa(doc.isModified(), "o documento fica alterado")
    painel.undo()
    drenar_eventos(4)
    checa_igual(_primeiro_opaco(doc)[1].xml, obj0.xml, "um desfazer devolve o XML de antes")
    checa(not doc.isModified(), "e o documento volta ao estado salvo (um passo por arraste)")
    painel.redo()
    drenar_eventos(4)
    checa_igual(_primeiro_opaco(doc)[1].xml, obj1.xml, "refazer devolve a posicao nova")
    painel.undo()
    drenar_eventos(4)

    secao("clique sem arrastar nao muda nada; Esc tira a selecao")
    r = painel.retangulo_flutuante_na_tela(pos)
    _clique(painel, r.center())
    checa_igual(_primeiro_opaco(doc)[1].xml, obj0.xml, "clique simples nao move o objeto")
    checa_igual(painel.flutuante_selecionado(), pos, "e seleciona")
    QTest.keyClick(painel, Qt.Key.Key_Escape)
    checa(painel.flutuante_selecionado() is None and not painel.textCursor().hasSelection(),
          "Esc tira a selecao do objeto")

    secao("setas: 1 px de tela; Ctrl+setas: passo fino; um desfazer por tecla")
    _clique(painel, r.center())
    QTest.keyClick(painel, Qt.Key.Key_Right)
    um_px = round(1 / m.escala * 635)
    h1 = int(_pos(_primeiro_opaco(doc)[1].xml, "h")[2])
    checa(abs(h1 - um_px) <= 2, f"seta para a direita: +1 px de tela ({h1} EMU, oraculo {um_px})")
    QTest.keyClick(painel, Qt.Key.Key_Down)
    v1 = int(_pos(_primeiro_opaco(doc)[1].xml, "v")[2])
    checa(abs(v1 - um_px) <= 2, f"seta para baixo: +1 px de tela ({v1} EMU)")
    QTest.keyClick(painel, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
    h2 = int(_pos(_primeiro_opaco(doc)[1].xml, "h")[2])
    fino = max(1.0, 1 / m.escala / 4) * 635
    checa(abs((h1 - h2) - fino) <= 2 and h1 - h2 < um_px,
          f"Ctrl+seta: passo fino ({h1 - h2} EMU, oraculo {round(fino)})")
    checa_igual(painel.flutuante_selecionado(), _primeiro_opaco(doc)[0],
                "o objeto continua selecionado depois das setas")
    painel.undo()
    drenar_eventos(2)
    checa_igual(int(_pos(_primeiro_opaco(doc)[1].xml, "h")[2]), h1, "desfazer volta uma tecla so'")
    painel.undo()
    painel.undo()
    drenar_eventos(4)
    checa_igual(_primeiro_opaco(doc)[1].xml, obj0.xml, "tres desfazer voltam as tres teclas")
    doc.setModified(False)
    painel.close()


def testar_redimensionar() -> None:
    secao("redimensionar: alca de canto e de lado; Shift trava a proporcao; imagem trava sempre")
    painel = _abrir(_doc_caixa(quebra="<wp:wrapNone/>"))
    doc = painel.documento_corpo()
    pos, obj0 = _primeiro_opaco(doc)
    r = painel.retangulo_flutuante_na_tela(pos)
    m = painel.mapa()
    _clique(painel, r.center())
    checa_igual(painel.alca_flutuante_em(r.bottomRight()), "se", "a alca do canto de baixo a direita")
    checa_igual(painel.alca_flutuante_em(QPointF(r.right(), r.center().y())), "e", "a alca do lado direito")
    _arrastar(painel, r.bottomRight(), QPointF(r.right() + 60, r.bottom() + 15))
    _p, obj1 = _primeiro_opaco(doc)
    cx, cy = _extent(obj1.xml)
    esperado = (round((2880 + 60 / m.escala) * 635), round((2000 + 15 / m.escala) * 635))
    checa(abs(cx - esperado[0]) <= 700 and abs(cy - esperado[1]) <= 700,
          f"forma, canto sem Shift: largura e altura livres ({(cx, cy)}, oraculo {esperado})")
    checa_igual(_xfrm_ext(obj1.xml), (cx, cy), "o a:ext do desenho acompanha o wp:extent")
    checa_igual(_sem_posicao_e_tamanho(obj1.xml), _sem_posicao_e_tamanho(obj0.xml),
                "so' posicao e tamanho mudam no XML (c14n)")
    painel.undo()
    drenar_eventos(2)
    checa_igual(_primeiro_opaco(doc)[1].xml, obj0.xml, "um desfazer devolve o tamanho")
    _clique(painel, r.center())
    _arrastar(painel, r.bottomRight(), QPointF(r.right() + 60, r.bottom() + 15), mods=SHIFT)
    cx, cy = _extent(_primeiro_opaco(doc)[1].xml)
    checa(abs(cx / cy - 2880 / 2000) < 0.01 and cx > 2880 * 635,
          f"com Shift a proporcao fica (largura/altura {cx / cy:.3f}, original {2880 / 2000:.3f})")
    painel.undo()
    drenar_eventos(2)
    _clique(painel, r.center())
    _arrastar(painel, QPointF(r.right(), r.center().y()), QPointF(r.right() + 40, r.center().y() + 30))
    cx, cy = _extent(_primeiro_opaco(doc)[1].xml)
    checa(abs(cy - 2000 * 635) <= 1 and abs(cx - round((2880 + 40 / m.escala) * 635)) <= 700,
          f"alca do lado: so' a largura muda ({cx}, {cy})")
    painel.undo()
    drenar_eventos(2)
    # Alca da esquerda em cima: o canto oposto fica parado (a posicao muda junto).
    _clique(painel, r.center())
    _arrastar(painel, r.topLeft(), QPointF(r.left() - 30, r.top() - 20))
    o = _primeiro_opaco(doc)[1].xml
    cx, cy = _extent(o)
    h = int(_pos(o, "h")[2])
    checa(abs(h - round(-30 / m.escala * 635)) <= 700 and
          abs(cx - round((2880 + 30 / m.escala) * 635)) <= 700,
          f"alca de cima a esquerda: o objeto cresce para fora e o canto oposto fica ({h}, {cx})")
    painel.undo()
    drenar_eventos(2)
    doc.setModified(False)
    painel.close()

    rels = [("rId81", tf.RT_IMAGEM, "media/flut1.png")]
    partes = {"word/media/flut1.png": tf.png_cor((0, 160, 0))}
    img = tf.ancora(81, tf.URI_IMAGEM, tf.figura("rId81", 1828800, 914400), 1828800, 914400,
                    h=("margin", "posOffset", 0), v=("paragraph", "posOffset", 0),
                    quebra="<wp:wrapNone/>")
    painel = _abrir(tf.doc_do_corpo('<w:p>' + img + '<w:r><w:t>Texto.</w:t></w:r></w:p>', rels, partes))
    doc = painel.documento_corpo()
    pos, obj0 = _primeiro_opaco(doc)
    r = painel.retangulo_flutuante_na_tela(pos)
    _clique(painel, r.center())
    _arrastar(painel, r.bottomRight(), QPointF(r.right() + 80, r.bottom() + 5))
    cx, cy = _extent(_primeiro_opaco(doc)[1].xml)
    checa(abs(cx / cy - 2.0) < 0.01 and cx > 1828800,
          f"imagem: o canto trava a proporcao sem Shift, como no Word ({cx / cy:.3f})")
    checa_igual(_xfrm_ext(_primeiro_opaco(doc)[1].xml), (cx, cy), "e o a:ext do pic:spPr acompanha")
    painel.undo()
    drenar_eventos(2)
    doc.setModified(False)
    painel.close()


def testar_reancorar() -> None:
    secao("reancorar: arrastar para outra pagina leva a ancora ao paragrafo de la'")
    painel = _abrir(_doc_caixa(quebra="<wp:wrapNone/>", depois=14))
    lay = painel.layout_pag
    doc = painel.documento_corpo()
    checa(lay.numero_paginas() >= 2, f"o documento tem {lay.numero_paginas()} paginas")
    pos, obj0 = _primeiro_opaco(doc)
    bloco0 = doc.findBlock(pos).blockNumber()
    # O objeto da pagina 1 e' arrastado para o alto da pagina 2 (fora da tela: o arraste vai
    # pelos metodos do painel que o mouse usa, com os pontos de tela de cada folha).
    painel._selecionar_objeto(pos)
    drenar_eventos(2)
    from editdoc.ponte_qt import flutuantes as pf
    m = painel.mapa()
    r = painel.retangulo_flutuante_na_tela(pos)
    alvo_tw = (1440.0, 3000.0)  # pagina 2, 3000 twips do alto da folha
    fx, fy, _fw, _fh = m.folha_na_tela(1)
    destino = QPointF(fx + alvo_tw[0] * m.escala + r.width() / 2,
                      fy + alvo_tw[1] * m.escala + r.height() / 2)
    painel._iniciar_arraste(pos, r.center(), None)
    painel._arraste["ativo"] = True
    painel._soltar_arraste(destino, NADA)
    drenar_eventos(4)
    pos2, obj1 = _primeiro_opaco(doc)
    n2, rect2 = pf.retangulo_de(doc, pos2)
    checa_igual(n2, 1, "o objeto esta' na pagina 2")
    checa(doc.findBlock(pos2).blockNumber() != bloco0 and
          lay.pagina_de_y(doc.documentLayout().blockBoundingRect(doc.findBlock(pos2)).top()) == 1,
          "a ancora foi para um paragrafo da pagina 2")
    checa(abs(rect2[1] - alvo_tw[1]) <= 3 and abs(rect2[0] - alvo_tw[0]) <= 3,
          f"no lugar onde foi solto ({tuple(round(v) for v in rect2[:2])}, alvo {alvo_tw})")
    checa_igual(_pos(obj1.xml, "v")[0], "paragraph", "o relativeFrom vertical do arquivo fica")
    dados = _gravar_e_conferir(painel, ler(_doc_caixa(quebra="<wp:wrapNone/>", depois=14))[0])
    modelo2 = ler(dados)[0]
    blocos = paragrafos_de(modelo2.paragrafos)
    com_objeto = [i for i, p in enumerate(blocos) if any(r.objeto for r in p.runs)]
    checa(com_objeto and com_objeto[0] > 0,
          f"gravado (validador e conferencia passam) e relido com o objeto no paragrafo {com_objeto}")
    checa_igual(_sem_posicao_e_tamanho(obj1.xml), _sem_posicao_e_tamanho(obj0.xml),
                "o XML so' muda na posicao (c14n)")
    painel.undo()
    drenar_eventos(4)
    pos3, obj3 = _primeiro_opaco(doc)
    checa(pos3 == pos and obj3.xml == obj0.xml, "um desfazer devolve ancora e posicao")
    doc.setModified(False)
    painel.close()


def testar_na_linha() -> None:
    secao("na linha: objeto preservado com alcas (wp:extent e xfrm); imagem do EditDoc segue")
    cx, cy = 1828800, 914400
    inline = ('<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
              f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
              '<wp:docPr id="70" name="Caixa na linha"/><wp:cNvGraphicFramePr/>'
              f'<a:graphic><a:graphicData uri="{tf.URI_FORMA}">'
              + tf.forma(cx, cy, "3366FF", texto="Na linha") +
              '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
    painel = _abrir(tf.doc_do_corpo('<w:p><w:r><w:t>Antes </w:t></w:r>' + inline
                                    + '<w:r><w:t> depois.</w:t></w:r></w:p>'))
    doc = painel.documento_corpo()
    pos, obj0 = _primeiro_opaco(doc)
    r = painel.retangulo_imagem_na_tela(pos)
    checa(r is not None and r.width() > 20, f"o objeto na linha tem retangulo na tela ({r})")
    _clique(painel, r.center())
    checa_igual(painel.objeto_na_linha_selecionado(), pos, "clique seleciona o objeto na linha")
    checa(painel.alca_em(r.bottomRight()) is not None, "e ele ganha as alcas")
    m = painel.mapa()
    _arrastar(painel, r.bottomRight(), QPointF(r.right() + 40, r.bottom() + 40))
    o = _primeiro_opaco(doc)[1].xml
    ncx, ncy = _extent(o)
    # Tolerancia de 1 px de tela: o QTest leva o mouse a pixel inteiro, e a alca fica no canto
    # fracionario do objeto.
    checa(abs(ncx - round((cx / 635 + 40 / m.escala) * 635)) <= round(635 / m.escala) and ncy != cy,
          f"wp:extent muda (sem Shift a caixa nao trava a proporcao: {ncx}, {ncy})")
    checa_igual(_xfrm_ext(o), (ncx, ncy), "o xfrm de dentro acompanha")
    checa_igual(_sem_posicao_e_tamanho(o), _sem_posicao_e_tamanho(obj0.xml), "o resto igual (c14n)")
    painel.undo()
    drenar_eventos(2)
    checa_igual(_primeiro_opaco(doc)[1].xml, obj0.xml, "um desfazer devolve")
    doc.setModified(False)
    painel.close()

    from editdoc.edicao import imagens as ed_imagens
    painel = _abrir(tf.doc_do_corpo('<w:p><w:r><w:t>Texto.</w:t></w:r></w:p>'))
    c = painel.textCursor()
    c.setPosition(0)
    painel.setTextCursor(c)
    ed_imagens.inserir_bytes(painel, tf.png_cor((200, 0, 0)))
    pos = painel.textCursor().position() - 1
    r = painel.retangulo_imagem_na_tela(pos)
    _clique(painel, r.center())
    antes = ed_imagens.tamanho_em_px(painel, pos)
    _arrastar(painel, r.bottomRight(), QPointF(r.right() + 30, r.bottom()))
    depois = ed_imagens.tamanho_em_px(painel, pos)
    checa(depois[0] > antes[0] and abs(depois[0] / depois[1] - antes[0] / antes[1]) < 0.02,
          f"imagem na linha (M4): a alca continua redimensionando com a proporcao ({antes} -> {depois})")
    painel.documento_corpo().setModified(False)
    painel.close()


def _gravar_e_conferir(painel, modelo_base) -> bytes:
    from dataclasses import replace

    from editdoc.ponte_qt import de_qt
    modelo = de_qt.extrair(painel.documento_corpo())
    modelo.pagina = replace(painel.configuracao_pagina())
    modelo.cabecalhos, modelo.rodapes = painel.faixas_do_modelo()
    modelo.pacote = modelo_base.pacote
    dados = escrever(modelo)  # o validador de ordem roda aqui dentro
    conferencia.conferir(dados, modelo)
    return dados


def testar_quebra() -> None:
    secao("quebra de texto: as sete pela galeria, com desfazer, gravar e conferir")
    docx = _doc_caixa()
    painel = _painel()
    modelo = _carregar(painel, docx)
    painel.show()
    drenar_eventos()
    doc = painel.documento_corpo()
    pos, obj0 = _primeiro_opaco(doc)
    for quebra in ("superior_inferior", "atras", "frente", "comprimido", "atraves", "quadrado"):
        painel._selecionar_objeto(_primeiro_opaco(doc)[0])
        checa(painel.definir_quebra_do_selecionado(quebra) or
              painel.quebra_do_selecionado() == quebra, f"quebra {quebra} aplicada")
        drenar_eventos(4)
        o = _primeiro_opaco(doc)[1]
        checa_igual(posicao.estado(o.xml).quebra, quebra, f"{quebra}: no XML")
        checa_igual(painel.quebra_do_selecionado(), quebra, f"{quebra}: a galeria marca a atual")
    painel.layout_pag.atualizar_flutuantes()
    bloco = tf._bloco_com(doc, "Texto do paragrafo")
    checa(tf._linhas(doc, bloco)[0][1] > 2000, "de volta a Quadrado: o texto contorna de novo")
    _gravar_e_conferir(painel, modelo)
    checa(True, "gravar: o validador e a conferencia pos-gravacao passam")

    secao("Alinhado ao texto e de volta: wp:anchor <-> wp:inline no documento")
    painel._selecionar_objeto(_primeiro_opaco(doc)[0])
    painel.definir_quebra_do_selecionado("linha")
    drenar_eventos(4)
    o = _primeiro_opaco(doc)[1]
    checa(posicao.estado(o.xml).na_linha and not o.flutuante, "a caixa fica na linha (wp:inline)")
    dados = _gravar_e_conferir(painel, modelo)
    relido = _objetos(ler(dados)[0])
    checa(len(relido) == 1 and not relido[0].flutuante, "gravada e relida na linha")
    painel._selecionar_objeto(_primeiro_opaco(doc)[0])
    painel.definir_quebra_do_selecionado("quadrado")
    drenar_eventos(4)
    o = _primeiro_opaco(doc)[1]
    anc = next(_raiz(o.xml).iter(WP % "anchor"), None)
    checa(anc is not None and all(anc.get(a) is not None for a in posicao.ATRIBUTOS_DA_ANCORA),
          "de volta a Quadrado: wp:anchor com os atributos do esquema")
    _gravar_e_conferir(painel, modelo)
    while doc.isUndoAvailable():
        painel.undo()
    drenar_eventos(4)
    checa_igual(_primeiro_opaco(doc)[1].xml, obj0.xml, "desfazer tudo devolve o objeto de origem")
    doc.setModified(False)
    painel.close()

    secao("imagem do EditDoc: na linha -> Quadrado (vira objeto) -> na linha (volta a imagem)")
    from editdoc.edicao import imagens as ed_imagens
    from editdoc.ponte_qt import opacos as pq_opacos
    painel = _painel()
    modelo = _carregar(painel, tf.doc_do_corpo('<w:p><w:r><w:t>Texto do paragrafo ' + tf.TEXTO
                                                + '</w:t></w:r></w:p>'))
    painel.show()
    drenar_eventos()
    doc = painel.documento_corpo()
    c = painel.textCursor()
    c.setPosition(0)
    painel.setTextCursor(c)
    ed_imagens.inserir_bytes(painel, tf.png_cor((0, 0, 200)))
    pos = 0
    painel._selecionar_objeto(pos)
    checa_igual(painel.quebra_do_selecionado(), "linha", "a imagem inserida esta' na linha")
    painel.definir_quebra_do_selecionado("quadrado")
    drenar_eventos(4)
    ops = pq_opacos.posicoes_de_opacos(doc)
    checa(len(ops) == 1 and _obj(doc, ops[0]).flutuante, "Quadrado: a imagem vira objeto flutuante")
    dados = _gravar_e_conferir(painel, modelo)
    relido = _objetos(ler(dados)[0])
    checa(len(relido) == 1 and relido[0].flutuante and relido[0].tipo == "imagem",
          "gravada e relida como imagem flutuante (wp:anchor)")
    painel._selecionar_objeto(ops[0])
    painel.definir_quebra_do_selecionado("linha")
    drenar_eventos(4)
    checa(not pq_opacos.posicoes_de_opacos(doc) and ed_imagens.formato_em(doc, ops[0]) is not None,
          "Alinhado ao texto: volta a ser imagem do EditDoc (o que o leitor le' de um wp:inline)")
    _gravar_e_conferir(painel, modelo)
    painel.undo()
    painel.undo()
    drenar_eventos(4)
    checa(ed_imagens.formato_em(doc, 0) is not None and not pq_opacos.posicoes_de_opacos(doc),
          "dois desfazer devolvem a imagem na linha de antes")
    doc.setModified(False)
    painel.close()

    secao("imagem flutuante com rotacao nao vira imagem na linha sem perda (recusa com motivo)")
    rels = [("rId81", tf.RT_IMAGEM, "media/flut1.png")]
    partes = {"word/media/flut1.png": tf.png_cor((0, 160, 0))}
    girada = tf.figura("rId81", 1828800, 914400).replace('<a:xfrm>', '<a:xfrm rot="5400000">')
    img = tf.ancora(81, tf.URI_IMAGEM, girada, 1828800, 914400, quebra="<wp:wrapNone/>")
    painel = _abrir(tf.doc_do_corpo('<w:p>' + img + '<w:r><w:t>T</w:t></w:r></w:p>', rels, partes))
    doc = painel.documento_corpo()
    recados = []
    painel.mensagem.connect(recados.append)
    pos, obj0 = _primeiro_opaco(doc)
    painel._selecionar_objeto(pos)
    checa(not painel.definir_quebra_do_selecionado("linha"), "a troca e' recusada")
    checa(recados and "girada" in recados[-1], f"com o motivo na barra de status ({recados})")
    checa_igual(_primeiro_opaco(doc)[1].xml, obj0.xml, "e o objeto fica como estava")
    painel.close()


def testar_dialogo() -> None:
    secao("dialogo Posicao e tamanho: valores, troca de referencia e aplicar num passo")
    from editdoc.interface import dialogo_posicao
    painel = _abrir(_doc_caixa(h=("margin", "posOffset", 360000), v=("paragraph", "posOffset", 180000)))
    doc = painel.documento_corpo()
    pos, obj0 = _primeiro_opaco(doc)
    painel._selecionar_objeto(pos)
    dados = painel.dados_de_posicao()
    checa(dados is not None and dados["quebra"] == "quadrado", "o dialogo recebe a quebra atual")
    dialogo = dialogo_posicao.DialogoPosicao(None, dados)
    checa_igual((round(dialogo.h.value(), 2), round(dialogo.v.value(), 2)), (1.0, 0.5),
                "posicao em cm relativa a' margem e ao paragrafo (oraculo: 1 cm, 0,5 cm)")
    checa_igual((round(dialogo.largura.value(), 2), round(dialogo.altura.value(), 2)),
                (round(2880 * 635 / 360000, 2), round(2000 * 635 / 360000, 2)), "tamanho em cm")
    dialogo.h_rel.setCurrentIndex(dialogo.h_rel.findData("page"))
    checa_igual(round(dialogo.h.value(), 2), round((1440 * 635 + 360000) / 360000, 2),
                "trocar a referencia para Pagina mostra o mesmo lugar medido da pagina")
    checa_igual(dialogo.escolha(), {"h": ("page", round(dialogo.h.value() * 360000))},
                "so' a referencia mudou: o dialogo devolve so' a posicao horizontal")
    dialogo.h.setValue(5.0)
    dialogo.travar.setChecked(True)
    dialogo.largura.setValue(10.0)
    escolha = dialogo.escolha()
    checa(abs(escolha["tamanho"][1] / escolha["tamanho"][0] - 2000 / 2880) < 0.01,
          "com a proporcao travada, a altura segue a largura")
    dialogo.quebra.setCurrentIndex(dialogo.quebra.findData("linha"))
    checa(not dialogo._grupo_pos.isEnabled(), "Alinhado ao texto desabilita a posicao")
    dialogo.quebra.setCurrentIndex(dialogo.quebra.findData("quadrado"))
    dialogo.deleteLater()
    painel.aplicar_posicao_tamanho({"h": ("page", 5 * 360000), "tamanho": (3600000, 1800000)})
    drenar_eventos(4)
    o = _primeiro_opaco(doc)[1].xml
    checa_igual((_pos(o, "h"), _extent(o)), (("page", "posOffset", "1800000"), (3600000, 1800000)),
                "aplicar: posOffset relativo a' pagina e o tamanho (EMU)")
    from editdoc.ponte_qt import flutuantes as pf
    n, rect = pf.retangulo_de(doc, _primeiro_opaco(doc)[0])
    checa(abs(rect[0] - 5 * 360000 / 635) < 1, f"na tela, o objeto a 5 cm da borda da pagina ({rect[0]:.0f})")
    painel.undo()
    drenar_eventos(2)
    checa_igual(_primeiro_opaco(doc)[1].xml, obj0.xml, "um desfazer devolve tudo")
    doc.setModified(False)
    painel.close()

    secao("janela: comandos de objeto habilitados so' com objeto selecionado; menu de contexto")
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    janela = JanelaPrincipal(configuracao.padrao())
    _carregar(janela.painel, _doc_caixa())
    janela.atualizador.atualizar()
    checa(not janela.comandos.acao("posicao_tamanho").isEnabled(), "sem objeto: Posicao desabilitada")
    pos, _o = _primeiro_opaco(janela.painel.documento_corpo())
    janela.painel._selecionar_objeto(pos)
    janela.atualizador.atualizar()
    checa(janela.comandos.acao("posicao_tamanho").isEnabled() and
          janela.comandos.acao("quebra_quadrado").isChecked(),
          "com o objeto: Posicao habilitada e Quadrado marcado na galeria")
    checa(len(janela.painel._acoes_quebra) == 7 and janela.painel._acao_posicao is not None,
          "o menu de contexto do objeto tem a galeria (7) e o dialogo")
    janela.comandos.acao("quebra_atras").trigger()
    drenar_eventos(4)
    checa_igual(janela.painel.quebra_do_selecionado(), "atras", "a acao da galeria troca a quebra")
    janela.painel.documento_corpo().setModified(False)
    janela.close()


def testar_cabecalho() -> None:
    secao("cabecalho em edicao: o objeto se seleciona, arrasta e desfaz no cabecalho")
    cab = ('<w:p>' + tf.ancora(93, tf.URI_FORMA, tf.forma(2880 * 635, 700 * 635, "003366"),
                               2880 * 635, 700 * 635, h=("page", "posOffset", 2000 * 635),
                               v=("page", "posOffset", 200 * 635), quebra="<wp:wrapNone/>")
           + '<w:r><w:t>Cabeçalho</w:t></w:r></w:p>')
    painel = _painel()
    _carregar(painel, tf.doc_do_corpo('<w:p><w:r><w:t>Corpo</w:t></w:r></w:p>', cabecalho=cab))
    painel.show()
    drenar_eventos()
    m = painel.mapa()
    fx, fy, _w, _h = m.folha_na_tela(0)
    centro = QPointF(fx + (2000 + 1440) * m.escala, fy + (200 + 350) * m.escala)
    _clique(painel, centro)
    checa(painel.flutuante_selecionado() is None, "fora da edicao do cabecalho, o objeto nao se seleciona")
    painel.entrar_na_faixa("cabecalho", 0)
    drenar_eventos(2)
    faixa = painel.editando_faixa()
    _clique(painel, centro)
    pos = painel.flutuante_selecionado()
    checa(pos is not None and painel.document() is faixa.doc,
          "na edicao, clique no objeto do cabecalho seleciona (no documento do cabecalho)")
    r = painel.retangulo_flutuante_na_tela(pos) if pos is not None else None
    checa(r is not None and abs(r.left() - (fx + 2000 * m.escala)) <= 1.5,
          f"contorno no lugar do objeto ({r})")
    obj0 = _obj(faixa.doc, pos) if pos is not None else None
    if r is not None:
        _arrastar(painel, r.center(), QPointF(r.center().x() + 90, r.center().y() + 30))
        pos2 = painel.flutuante_selecionado()
        o = _obj(faixa.doc, pos2 if pos2 is not None else pos)
        esperado = round((2000 + 90 / m.escala) * 635)
        h = _pos(o.xml, "h")
        checa(h[0] == "page" and abs(int(h[2]) - esperado) <= 700,
              f"arrastar grava o posOffset no cabecalho ({h}, oraculo {esperado})")
        checa_igual(_sem_posicao_e_tamanho(o.xml), _sem_posicao_e_tamanho(obj0.xml),
                    "o resto do objeto do cabecalho igual (c14n)")
        checa(painel.documento_corpo().isModified(), "o documento fica alterado")
        dados = _gravar_e_conferir(painel, ler(tf.doc_do_corpo(
            '<w:p><w:r><w:t>Corpo</w:t></w:r></w:p>', cabecalho=cab))[0])
        modelo2 = ler(dados)[0]
        obj_cab = [r.objeto for p in paragrafos_de(modelo2.cabecalhos["padrao"]) for r in p.runs
                   if r.objeto]
        checa(obj_cab and _pos(obj_cab[0].xml, "h") == h,
              "gravado com o cabecalho (validador e conferencia) e relido na posicao nova")
        _clique(painel, painel.retangulo_flutuante_na_tela(pos2).center() if pos2 is not None else centro)
        QTest.keyClick(painel, Qt.Key.Key_Down)
        checa(int(_pos(_obj(faixa.doc, pos2).xml, "v")[2]) > 200 * 635, "a seta move no cabecalho")
        painel.undo()
        painel.undo()
        drenar_eventos(2)
        checa_igual(_obj(faixa.doc, pos).xml, obj0.xml, "o desfazer do cabecalho devolve o objeto")
        QTest.keyClick(painel, Qt.Key.Key_Escape)
    painel.sair_da_faixa()
    painel.documento_corpo().setModified(False)
    painel.close()


def testar_vml() -> None:
    secao("VML absoluto: arrastar grava margin-left/top no style")
    painel = _abrir(tf.doc_do_corpo('<w:p>' + tf.VML_ABSOLUTO + '<w:r><w:t>Texto</w:t></w:r></w:p>'))
    doc = painel.documento_corpo()
    pos, obj0 = _primeiro_opaco(doc)
    r = painel.retangulo_flutuante_na_tela(pos)
    m = painel.mapa()
    checa(r is not None, f"o objeto VML aparece ({r})")
    _clique(painel, r.center())
    _arrastar(painel, r.center(), QPointF(r.center().x() + 40, r.center().y() + 20))
    o = _primeiro_opaco(doc)[1]
    est = posicao.estado(o.xml)
    from editdoc.formato_docx import flutuantes as fxml
    anc = fxml.ler(o.xml).ancoragem
    esperado = (round((72 * 20 + 40 / m.escala) * 635), round((36 * 20 + 20 / m.escala) * 635))
    checa(est.vml and abs(anc.h_desloc - esperado[0]) <= 1000 and abs(anc.v_desloc - esperado[1]) <= 1000,
          f"margin-left/top novos ({anc.h_desloc}, {anc.v_desloc}; oraculo {esperado}, "
          "VML em pt com 2 casas)")
    checa_igual(_sem_posicao_e_tamanho(o.xml), _sem_posicao_e_tamanho(obj0.xml),
                "o resto do VML igual (c14n)")
    painel.undo()
    drenar_eventos(2)
    checa_igual(_primeiro_opaco(doc)[1].xml, obj0.xml, "desfazer devolve o style de antes")
    doc.setModified(False)
    painel.close()


def _p95(valores):
    valores = sorted(valores)
    return valores[min(len(valores) - 1, round(0.95 * (len(valores) - 1)))]


def testar_desempenho() -> None:
    secao("desempenho: arrastar (mover o mouse e pintar o fantasma) fica no gate de 16 ms")
    painel = _abrir(_doc_caixa(depois=60))
    doc = painel.documento_corpo()
    pos, _o = _primeiro_opaco(doc)
    r = painel.retangulo_flutuante_na_tela(pos)
    vp = painel.viewport()
    _clique(painel, r.center())
    vp.grab()
    QTest.mousePress(vp, ESQ, NADA, r.center().toPoint())
    tempos = []
    for i in range(1, 61):
        t = time.perf_counter()
        QTest.mouseMove(vp, QPoint(round(r.center().x() + i * 2), round(r.center().y() + i)))
        vp.grab()
        tempos.append((time.perf_counter() - t) * 1000)
    QTest.mouseRelease(vp, ESQ, NADA, QPoint(round(r.center().x() + 120), round(r.center().y() + 60)))
    drenar_eventos(2)
    p95 = _p95(tempos)
    print(f"         arraste: p95 {p95:.1f} ms por quadro (mediana {statistics.median(tempos):.1f})")
    checa(p95 <= 16.0, f"o arraste fica no gate (p95 {p95:.1f} ms <= 16 ms)")
    doc.setModified(False)
    painel.close()


def main() -> int:
    testar_xml()
    testar_arraste()
    testar_redimensionar()
    testar_reancorar()
    testar_na_linha()
    testar_quebra()
    testar_dialogo()
    testar_cabecalho()
    testar_vml()
    testar_desempenho()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
