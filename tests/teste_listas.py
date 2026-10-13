"""Listas (0.1.4): numbering.xml inteiro, numeros calculados como o Word, edicao e avisos.

As fixtures sao montadas aqui, em codigo (nenhum documento real no repositorio): um
numbering.xml no formato do Word (namespaces w15/w16cid, mc:Ignorable, durableId), com
titulos numerados por estilo (1, 1.1, 1.1.1), lista de varios niveis com reinicio e
w:lvlRestart, duas instancias que compartilham a abstrata, w:startOverride, w:lvlOverride
com w:lvl, romanos e letras, marcador Symbol/Wingdings, marcador de figura (w:numPicBullet
com a imagem nas relacoes do numbering.xml), w:isLgl, w:suff, lista em tabela e em caixa de
texto. Os numeros esperados (ORACULO) foram escritos a mao, um por paragrafo.
"""

from __future__ import annotations

import time

from ajudantes import (checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao,
                       usar_fontes_do_documento)
import fixtures_docx as fx

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from lxml import etree  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from editdoc.edicao import listas as ed_listas  # noqa: E402
from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx import numeracao as fx_numeracao  # noqa: E402
from editdoc.formato_docx.escritor import escrever, escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.interface.painel_documento import PainelDocumento  # noqa: E402
from editdoc.modelo import numeracao as mod  # noqa: E402
from editdoc.modelo.documento import Documento, objetos_de, paragrafos_de  # noqa: E402
from editdoc.modelo.texto_plano import texto_do_documento  # noqa: E402
from editdoc.ponte_qt import de_qt, para_qt  # noqa: E402
from editdoc.ponte_qt import listas as pl  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_NUMERACAO = (f'xmlns:w="{W}" xmlns:r="{R}" xmlns:v="urn:schemas-microsoft-com:vml" '
                'xmlns:o="urn:schemas-microsoft-com:office:office" '
                'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
                'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" '
                'xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid" '
                'mc:Ignorable="w15 w16cid"')


def q(nome: str) -> str:
    return "{%s}%s" % (W, nome)


def _lvl(ilvl, fmt, texto, inicio=1, jc="left", esq=None, desl=None, estilo=None, reinicio=None,
         suff=None, legal=False, fonte=None, figura=None, tabs=()) -> str:
    partes = [f'<w:lvl w:ilvl="{ilvl}">', f'<w:start w:val="{inicio}"/>', f'<w:numFmt w:val="{fmt}"/>']
    if reinicio is not None:
        partes.append(f'<w:lvlRestart w:val="{reinicio}"/>')
    if estilo:
        partes.append(f'<w:pStyle w:val="{estilo}"/>')
    if legal:
        partes.append('<w:isLgl/>')
    if suff:
        partes.append(f'<w:suff w:val="{suff}"/>')
    partes.append(f'<w:lvlText w:val="{texto}"/>')
    if figura is not None:
        partes.append(f'<w:lvlPicBulletId w:val="{figura}"/>')
    partes.append(f'<w:lvlJc w:val="{jc}"/>')
    if esq is not None or tabs:
        tab = "".join(f'<w:tab w:val="num" w:pos="{t}"/>' for t in tabs)
        partes.append("<w:pPr>" + (f"<w:tabs>{tab}</w:tabs>" if tabs else "")
                      + (f'<w:ind w:left="{esq}" w:hanging="{desl}"/>' if esq is not None else "")
                      + "</w:pPr>")
    if fonte:
        partes.append(f'<w:rPr><w:rFonts w:ascii="{fonte}" w:hAnsi="{fonte}" w:hint="default"/></w:rPr>')
    partes.append("</w:lvl>")
    return "".join(partes)


def _abstrata(ident, niveis, tipo="hybridMultilevel", extra="") -> str:
    return (f'<w:abstractNum w:abstractNumId="{ident}" w15:restartNumberingAfterBreak="0">'
            f'<w:nsid w:val="{0x1000 + ident:08X}"/><w:multiLevelType w:val="{tipo}"/>'
            f'<w:tmpl w:val="{0x2000 + ident:08X}"/>{extra}{"".join(niveis)}</w:abstractNum>')


def _num(ident, abstrata, sobrescritas="") -> str:
    return (f'<w:num w:numId="{ident}" w16cid:durableId="{100000 + ident}">'
            f'<w:abstractNumId w:val="{abstrata}"/>{sobrescritas}</w:num>')


SIMBOLO = ""
QUADRADO = ""

NUMERACAO = "".join([
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n',
    f"<w:numbering {NS_NUMERACAO}>",
    '<w:numPicBullet w:numPicBulletId="0"><w:pict><v:shape id="_x0000_i1025" '
    'type="#_x0000_t75" style="width:9pt;height:9pt" o:bullet="t"><v:imagedata r:id="rId1" '
    'o:title=""/></v:shape></w:pict></w:numPicBullet>',
    # 0: titulos numerados pelo estilo (1 / 1.1 / 1.1.1)
    _abstrata(0, [_lvl(0, "decimal", "%1", estilo="Heading1", esq=432, desl=432),
                  _lvl(1, "decimal", "%1.%2", estilo="Heading2", esq=576, desl=576),
                  _lvl(2, "decimal", "%1.%2.%3", estilo="Heading3", esq=720, desl=720)],
              "multilevel"),
    # 1: varios niveis com reinicio; o nivel 3 so' reinicia pelo nivel 1 (lvlRestart 1)
    _abstrata(1, [_lvl(0, "decimal", "%1.", esq=360, desl=360),
                  _lvl(1, "decimal", "%1.%2.", esq=792, desl=432),
                  _lvl(2, "decimal", "%1.%2.%3.", esq=1224, desl=504, reinicio=1)], "multilevel"),
    # 2: decimal simples, compartilhada por tres instancias
    _abstrata(2, [_lvl(0, "decimal", "%1.", esq=720, desl=360)]),
    # 3: romanos e letras
    _abstrata(3, [_lvl(0, "upperRoman", "%1.", esq=720, desl=360),
                  _lvl(1, "lowerLetter", "%2)", esq=1440, desl=360),
                  _lvl(2, "lowerRoman", "%3.", jc="right", esq=2160, desl=180)]),
    # 4: marcadores de fonte de simbolo
    _abstrata(4, [_lvl(0, "bullet", SIMBOLO, esq=720, desl=360, fonte="Symbol"),
                  _lvl(1, "bullet", "o", esq=1440, desl=360, fonte="Courier New"),
                  _lvl(2, "bullet", QUADRADO, esq=2160, desl=360, fonte="Wingdings")]),
    # 5: marcador de figura
    _abstrata(5, [_lvl(0, "bullet", SIMBOLO, esq=720, desl=360, fonte="Symbol", figura=0)]),
    # 6: isLgl (o nivel 2 mostra o romano de cima em decimal)
    _abstrata(6, [_lvl(0, "upperRoman", "%1.", esq=720, desl=360),
                  _lvl(1, "decimal", "%1.%2", esq=1440, desl=720, legal=True)]),
    # 7: sufixo espaco e nada
    _abstrata(7, [_lvl(0, "decimal", "%1.", esq=720, desl=360, suff="space"),
                  _lvl(1, "decimal", "(%2)", esq=1440, desl=360, suff="nothing")]),
    # 8: para a tabela
    _abstrata(8, [_lvl(0, "decimal", "%1)", esq=360, desl=360)]),
    _num(1, 0), _num(2, 1), _num(3, 2), _num(4, 2),
    _num(5, 2, '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="5"/></w:lvlOverride>'),
    _num(6, 3), _num(7, 4), _num(8, 5), _num(9, 6), _num(10, 7),
    _num(11, 2, '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/>'
         + _lvl(0, "lowerLetter", "%1)", esq=720, desl=360) + "</w:lvlOverride>"),
    _num(12, 8),
    "</w:numbering>",
])

RELS_NUMERACAO = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                  'relationships/image" Target="media/marcador.png"/></Relationships>')


def _estilo_titulo(n: int) -> str:
    return (f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/>'
            f'<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:uiPriority w:val="9"/><w:qFormat/>'
            f'<w:pPr><w:keepNext/><w:numPr><w:ilvl w:val="{n - 1}"/><w:numId w:val="1"/></w:numPr>'
            f'<w:outlineLvl w:val="{n - 1}"/></w:pPr><w:rPr><w:b/></w:rPr></w:style>')


ESTILOS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
           f'<w:styles xmlns:w="{W}"><w:docDefaults><w:rPrDefault><w:rPr>'
           '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>'
           '<w:pPrDefault><w:pPr><w:spacing w:after="160"/></w:pPr></w:pPrDefault></w:docDefaults>'
           '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
           '<w:qFormat/></w:style>'
           + "".join(_estilo_titulo(n) for n in (1, 2, 3)) +
           '<w:style w:type="numbering" w:default="1" w:styleId="NoList"><w:name w:val="No List"/>'
           '</w:style></w:styles>')


def _p(texto: str, num: int | None = None, ilvl: int | None = None, estilo: str | None = None) -> str:
    ppr = ""
    if estilo:
        ppr += f'<w:pStyle w:val="{estilo}"/>'
    if num is not None or ilvl is not None:
        ppr += "<w:numPr>" + (f'<w:ilvl w:val="{ilvl}"/>' if ilvl is not None else "") + \
               (f'<w:numId w:val="{num}"/>' if num is not None else "") + "</w:numPr>"
    return (f"<w:p>{'<w:pPr>' + ppr + '</w:pPr>' if ppr else ''}"
            f"<w:r><w:t>{texto}</w:t></w:r></w:p>")


#: (texto do paragrafo, numero esperado ou None). Escrito a mao.
ORACULO = [
    ("t01 Introducao", "1", dict(estilo="Heading1")),
    ("t02 texto", None, {}),
    ("t03 Escopo", "1.1", dict(estilo="Heading2")),
    ("t04 Termos", "1.2", dict(estilo="Heading2")),
    ("t05 Detalhe", "1.2.1", dict(estilo="Heading3")),
    ("t06 Requisitos", "2", dict(estilo="Heading1")),
    ("t07 Pulo do nivel 2", "2.0.1", dict(estilo="Heading3")),
    ("t08 Depois do pulo", "2.1", dict(estilo="Heading2")),
    ("m01", "1.", dict(num=2, ilvl=0)),
    ("m02", "1.1.", dict(num=2, ilvl=1)),
    ("m03", "1.1.1.", dict(num=2, ilvl=2)),
    ("m04", "1.2.", dict(num=2, ilvl=1)),
    ("m05 lvlRestart 1 nao reinicia", "1.2.2.", dict(num=2, ilvl=2)),
    ("m06", "2.", dict(num=2, ilvl=0)),
    ("m07 reinicia pelo nivel 1", "2.0.1.", dict(num=2, ilvl=2)),
    ("c01", "1.", dict(num=3, ilvl=0)),
    ("c02", "2.", dict(num=3, ilvl=0)),
    ("c03 paragrafo comum no meio", None, {}),
    ("c04 outra instancia, mesma abstrata", "3.", dict(num=4, ilvl=0)),
    ("c05 startOverride 5", "5.", dict(num=5, ilvl=0)),
    ("c06", "6.", dict(num=5, ilvl=0)),
    ("r01", "I.", dict(num=6, ilvl=0)),
    ("r02", "a)", dict(num=6, ilvl=1)),
    ("r03", "b)", dict(num=6, ilvl=1)),
    ("r04", "i.", dict(num=6, ilvl=2)),
    ("r05", "ii.", dict(num=6, ilvl=2)),
    ("r06", "iii.", dict(num=6, ilvl=2)),
    ("r07", "iv.", dict(num=6, ilvl=2)),
    ("r08", "II.", dict(num=6, ilvl=0)),
    ("r09", "a)", dict(num=6, ilvl=1)),
    ("s01", SIMBOLO, dict(num=7, ilvl=0)),
    ("s02", "o", dict(num=7, ilvl=1)),
    ("s03", QUADRADO, dict(num=7, ilvl=2)),
    ("f01 marcador de figura", SIMBOLO, dict(num=8, ilvl=0)),
    ("l01", "I.", dict(num=9, ilvl=0)),
    ("l02 isLgl", "1.1", dict(num=9, ilvl=1)),
    ("e01 sufixo espaco", "1.", dict(num=10, ilvl=0)),
    ("e02 sufixo nada", "(1)", dict(num=10, ilvl=1)),
    ("o01 lvlOverride com lvl", "a)", dict(num=11)),
    ("o02", "b)", dict(num=11)),
    ("h01 Titulo sem numero (numId 0)", None, dict(estilo="Heading1", num=0)),
    ("h02 Conclusao", "3", dict(estilo="Heading1")),
]
#: A tabela vem depois: duas celulas com lista (instancia 12).
ORACULO_TABELA = [("tb1", "1)"), ("tb2", "2)")]


def corpo_xml() -> str:
    paras = "".join(_p(texto, **args) for texto, _rot, args in ORACULO)
    tabela = ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid>'
              '<w:gridCol w:w="4500"/><w:gridCol w:w="4500"/></w:tblGrid><w:tr>'
              f'<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>{_p("tb1", 12, 0)}</w:tc>'
              f'<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>{_p("tb2", 12, 0)}</w:tc>'
              '</w:tr></w:tbl>')
    return paras + tabela + _p("fim")


def docx_de_listas(numeracao: str = NUMERACAO, corpo: str | None = None) -> bytes:
    return fx.docx_com_xml(corpo if corpo is not None else corpo_xml(), partes_extra={
        "word/numbering.xml": numeracao.encode("utf-8"),
        "word/styles.xml": ESTILOS.encode("utf-8"),
        "word/_rels/numbering.xml.rels": RELS_NUMERACAO.encode("utf-8"),
        "word/media/marcador.png": fx.png(8, 8, (20, 90, 200)),
    }, tipos_extra=[("/word/media/marcador.png", "image/png")])


def _c14n(dados: bytes) -> bytes:
    return etree.tostring(etree.fromstring(dados), method="c14n")


def _rotulos_do_modelo(doc: Documento) -> dict[str, str]:
    rot = mod.rotulos_do_documento(doc)
    saida = {}
    for p in paragrafos_de(doc.paragrafos):
        texto = "".join(r.texto for r in p.runs)
        saida[texto] = rot[id(p)].texto if id(p) in rot else None
    return saida


def _rotulos_do_qt(qdoc) -> dict[str, str]:
    rot = pl.numerador_de(qdoc).rotulos()
    saida = {}
    bloco = qdoc.begin()
    while bloco.isValid():
        if bloco.text():
            r = rot.get(bloco.blockNumber())
            saida[bloco.text()] = r.texto if r is not None else None
        bloco = bloco.next()
    return saida


ESPERADO = {texto: rot for texto, rot, _a in ORACULO} | dict(ORACULO_TABELA) | {"fim": None}


# -- formatos e calculo sem arquivo ---------------------------------------------------

def testar_formatos() -> None:
    secao("formatos de numero (w:numFmt), com os casos de borda")
    casos = [
        (7, "decimal", "7"), (7, "decimalZero", "07"), (12, "decimalZero", "12"),
        (4, "lowerRoman", "iv"), (1994, "upperRoman", "MCMXCIV"), (1, "lowerLetter", "a"),
        (27, "lowerLetter", "aa"), (28, "upperLetter", "BB"), (3, "ordinal", "3º"),
        (21, "cardinalText", "Vinte e um"), (100, "cardinalText", "Cem"),
        (1001, "cardinalText", "Mil e um"), (3, "ordinalText", "Terceiro"),
        (22, "ordinalText", "Vigésimo segundo"), (3, "decimalEnclosedCircle", "③"),
        (25, "decimalEnclosedCircle", "25"), (5, "chicago", "**"),
        (255, "hex", "FF"), (9, "none", ""), (9, "bullet", ""), (9, "japaneseCounting", "9"),
        (12, "decimalFullWidth", "１２"),
    ]
    erros = [(n, f, mod.formatar(n, f), e) for n, f, e in casos if mod.formatar(n, f) != e]
    checa_igual(erros, [], "cada formato da' o texto do Word (formato desconhecido cai em decimal)")
    checa(mod.formatar(2, "chicago") != mod.formatar(1, "chicago"),
          "contraprova: chicago muda de simbolo a cada numero")


def testar_calculo_puro() -> None:
    secao("calculo sem arquivo: reinicio por nivel, startOverride, abstrata compartilhada")
    cat = mod.Numeracao()
    a = cat.adicionar_abstrata(mod.niveis_multinivel("decimal"), "multilevel")
    n1 = cat.adicionar_instancia(a.id).id
    n2 = cat.adicionar_instancia(a.id).id
    n3 = cat.adicionar_instancia(a.id, (mod.Sobrescrita(ilvl=0, inicio=10),)).id
    c = mod.Contador(cat)
    textos = [c.proximo(n, l).texto for n, l in ((n1, 0), (n1, 1), (n1, 1), (n2, 0), (n2, 2),
                                                 (n3, 0), (n3, 1), (n1, 0))]
    checa_igual(textos, ["1.", "1.1.", "1.2.", "2.", "2.0.1.", "10.", "10.1.", "11."],
                "contadores da abstrata: continua entre instancias, reinicia o nivel de baixo, "
                "pula nivel com 0, o startOverride recomeca")
    checa(c.proximo(n1, 1).texto != "11.2.", "contraprova: o nivel 2 reiniciou depois do nivel 1")


# -- arquivo ------------------------------------------------------------------------------

def testar_leitura_e_oraculo() -> None:
    secao("numbering.xml do Word: leitura sem perda e numeros iguais ao oraculo escrito a mao")
    dados = docx_de_listas()
    doc, avisos = ler(dados)
    codigos = {a.codigo for a in avisos}
    checa(not codigos & {"LISTA", "LISTA_NIVEL", "LISTA_EM_CAIXA"},
          f"nenhum aviso de lista (avisos: {sorted(codigos)})")
    cat = doc.numeracao
    checa_igual((len(cat.abstratas), len(cat.instancias), sorted(cat.imagens)), (9, 12, [0]),
                "9 abstratas, 12 instancias e o marcador de figura no catalogo")
    checa(cat.imagens[0].dados is not None and cat.imagens[0].formato == "png",
          "a imagem do marcador de figura e' lida pelas relacoes do numbering.xml")
    obtidos = _rotulos_do_modelo(doc)
    diferentes = {k: (obtidos.get(k), v) for k, v in ESPERADO.items() if obtidos.get(k) != v}
    checa_igual(diferentes, {}, "cada paragrafo tem o numero do oraculo (modelo)")
    titulos = [p for p in doc.paragrafos if getattr(p, "estilo", None) == "Heading2"]
    checa(all(p.lista is None and p.lista_nivel is None for p in titulos),
          "titulo numerado pelo estilo nao ganha numPr direto (herda)")
    h01 = next(p for p in doc.paragrafos if "numId 0" in "".join(r.texto for r in p.runs))
    checa_igual(h01.lista, 0, "numId 0 no paragrafo desliga a lista do estilo")
    estilo = doc.estilos.obter("Heading2")
    checa_igual((estilo.lista, estilo.lista_nivel), (1, 1), "o estilo guarda o numPr (numId 1, ilvl 1)")
    nivel = cat.nivel_de(7, 0)
    checa_igual((nivel.texto, nivel.simbolo().get("fonte")), (SIMBOLO, "Symbol"),
                "marcador Symbol: o simbolo e a fonte do rPr do nivel")
    checa_igual(mod.texto_visivel(SIMBOLO + QUADRADO), "•▪", "simbolo privado vira o Unicode parecido")
    checa_igual(cat.nivel_de(11, 0).formato, "lowerLetter", "w:lvlOverride com w:lvl troca o nivel")
    checa_igual(cat.nivel_de(5, 0).inicio, 5, "w:startOverride muda o inicio do nivel")
    checa_igual(cat.tab_padrao_tw, 708, "w:defaultTabStop do settings.xml")
    # contraprova: o oraculo acusa um numero errado
    trocado = dict(obtidos)
    trocado["m05 lvlRestart 1 nao reinicia"] = "1.2.1."
    checa(trocado != ESPERADO, "contraprova: um numero trocado e' acusado pelo oraculo")


def testar_ida_e_volta_c14n() -> None:
    secao("ida e volta: numbering.xml igual em c14n, imagem do marcador e numPr de cada paragrafo")
    dados = docx_de_listas()
    doc, _ = ler(dados)
    gravado, avisos = escrever_com_avisos(doc)
    checa_igual(avisos, [], "a gravacao nao tira nada")
    partes = fx.partes_de(gravado)
    checa_igual(_c14n(partes["word/numbering.xml"]), _c14n(NUMERACAO.encode("utf-8")),
                "numbering.xml volta igual (c14n), com w15, w16cid e mc:Ignorable")
    rels = partes.get("word/_rels/numbering.xml.rels", b"")
    alvo = etree.fromstring(rels).find("{http://schemas.openxmlformats.org/package/2006/relationships}"
                                       "Relationship") if rels else None
    checa(alvo is not None and alvo.get("Id") == "rId1"
          and partes.get("word/" + alvo.get("Target")) == fx.png(8, 8, (20, 90, 200)),
          "o marcador de figura volta: relacao rId1 e a imagem com os mesmos bytes")
    estilos = etree.fromstring(partes["word/styles.xml"])
    h2 = next(s for s in estilos.iter(q("style")) if s.get(q("styleId")) == "Heading2")
    checa(h2.find(q("pPr") + "/" + q("numPr")) is not None, "o numPr continua no estilo Titulo 2")

    def numprs(xml: bytes):
        saida = []
        for p in etree.fromstring(xml).iter(q("p")):
            n = p.find(q("pPr") + "/" + q("numPr"))
            if n is None:
                saida.append(None)
                continue
            saida.append(tuple(None if n.find(q(t)) is None else n.find(q(t)).get(q("val"))
                               for t in ("numId", "ilvl")))
        return saida
    original = fx.partes_de(dados)["word/document.xml"]
    checa_igual(numprs(partes["word/document.xml"]), numprs(original),
                "o numPr (numId e ilvl) de cada paragrafo volta como veio")
    checa_igual(ordem.validar(partes), [], "o pacote gravado passa no validador")
    conferencia.conferir(gravado, doc)
    checa(True, "a conferencia pos-gravacao aceita o arquivo")
    relido, avisos2 = ler(gravado)
    checa(_rotulos_do_modelo(relido) == ESPERADO and not avisos2,
          "relido: os mesmos numeros, sem aviso")
    checa_igual(escrever(relido), gravado, "idempotente: gravar o relido da' os mesmos bytes")


def testar_validador() -> None:
    secao("validador da numeracao: referencia, ids, nivel e marcador de figura (com sabotagens)")
    doc, _ = ler(docx_de_listas())
    partes = fx.partes_de(escrever(doc))
    checa_igual(fx_numeracao.validar(partes), [], "o arquivo do EditDoc passa")
    sabotagens = {
        "numId inexistente no corpo": ("word/document.xml", b'<w:numId w:val="6"/>', b'<w:numId w:val="99"/>'),
        "abstractNumId inexistente": ("word/numbering.xml", b'<w:abstractNumId w:val="8"/>',
                                      b'<w:abstractNumId w:val="88"/>'),
        "ilvl fora de 0 a 8": ("word/document.xml", b'<w:ilvl w:val="2"/>', b'<w:ilvl w:val="9"/>'),
        "numId repetido": ("word/numbering.xml", b'w:numId="12"', b'w:numId="11"'),
        "marcador de figura sem numPicBullet": ("word/numbering.xml", b'<w:lvlPicBulletId w:val="0"/>',
                                                b'<w:lvlPicBulletId w:val="7"/>'),
        "numId do estilo inexistente": ("word/styles.xml", b'<w:numId w:val="1"/>', b'<w:numId w:val="77"/>'),
    }
    for nome, (parte, de, para) in sabotagens.items():
        copia = dict(partes)
        checa(de in copia[parte], f"a sabotagem '{nome}' acha o que trocar")
        copia[parte] = copia[parte].replace(de, para, 1)
        checa(bool(ordem.validar(copia)), f"contraprova: {nome} e' acusado")


def testar_arquivo_hostil() -> None:
    secao("arquivo hostil: limites, referencia quebrada e nivel fora da faixa")
    muitas = "".join(_abstrata(i, [_lvl(0, "decimal", "%1.")]) for i in range(2500))
    numeracao = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:numbering {NS_NUMERACAO}>'
                 f'{muitas}{_num(1, 0)}</w:numbering>')
    inicio = time.perf_counter()
    doc, avisos = ler(docx_de_listas(numeracao, _p("a", 1, 0) + _p("b", 1, 0)))
    gasto = time.perf_counter() - inicio
    codigos = {a.codigo: a.contagem for a in avisos}
    checa(doc.numeracao is None and codigos.get("LISTA") == 5 and gasto < 2,
          "2500 abstratas (limite 2000): a numeracao nao e' lida, aviso LISTA nos 2 itens e nos 3 "
          f"estilos de titulo ({gasto:.2f} s)")
    partes = fx.partes_de(escrever(doc))
    checa_igual(ordem.validar(partes), [], "...e o arquivo gravado continua valido")
    grande = NUMERACAO.replace('w:val="%1.%2.%3."', 'w:val="' + "%1." * 200 + '"')
    doc, avisos = ler(docx_de_listas(grande, _p("a", 2, 0)))
    checa(doc.numeracao is None and any(a.codigo == "LISTA" for a in avisos),
          "w:lvlText de 600 caracteres (limite 256): a numeracao nao e' lida, com aviso")
    doc, avisos = ler(docx_de_listas(corpo=_p("orfao", 99, 0) + _p("nivel", 3, 12)))
    codigos = {a.codigo: a.contagem for a in avisos}
    orfao, nivel = doc.paragrafos[0], doc.paragrafos[1]
    checa(orfao.lista == 0 and codigos.get("LISTA") == 1,
          "numId que nao existe: sem lista, aviso LISTA")
    checa(nivel.lista_nivel == 8 and codigos.get("LISTA_NIVEL") == 1,
          "ilvl 12: vai para o nivel 9 (ilvl 8), aviso LISTA_NIVEL")
    checa_igual(ordem.validar(fx.partes_de(escrever(doc))), [], "o arquivo gravado e' valido")


def testar_caixa_de_texto() -> None:
    secao("lista dentro de caixa de texto: o numPr fica (o numbering.xml volta)")
    caixa = fx.caixa_de_texto(extra='<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="3"/></w:numPr></w:pPr>')
    dados = fx.docx_com_corpo_de_objetos("<w:p>" + caixa + "</w:p>", [fx.RELACOES_OBJETOS[-1]],
                                         partes_extra={"word/numbering.xml": NUMERACAO.encode("utf-8"),
                                                       "word/_rels/numbering.xml.rels": RELS_NUMERACAO.encode("utf-8"),
                                                       "word/media/marcador.png": fx.png(8, 8)},
                                         tipos=[("/word/media/marcador.png", "image/png")])
    doc, avisos = ler(dados)
    obj = next(objetos_de(doc), None)
    checa(obj is not None and b'w:numId w:val="3"' in obj.xml and
          not any(a.codigo == "LISTA_EM_CAIXA" for a in avisos),
          "o numPr da caixa e' preservado, sem aviso de perda")
    partes = fx.partes_de(escrever(doc))
    checa(b'w:numId w:val="3"' in partes["word/document.xml"] and ordem.validar(partes) == [],
          "e volta ao arquivo, que passa no validador")


# -- tela -----------------------------------------------------------------------------------

def _painel_com(doc: Documento) -> PainelDocumento:
    painel = PainelDocumento("Calibri", 11)
    para_qt.preencher(painel.document(), doc)
    return painel


def testar_qt_numeros_e_recuos() -> None:
    secao("tela: os mesmos numeros, o texto depois do numero e a volta ao modelo")
    doc, _ = ler(docx_de_listas())
    painel = _painel_com(doc)
    qdoc = painel.document()
    obtidos = _rotulos_do_qt(qdoc)
    diferentes = {k: (obtidos.get(k), v) for k, v in ESPERADO.items() if obtidos.get(k) != v}
    checa_igual(diferentes, {}, "cada bloco tem o numero do oraculo (tela)")
    checa(not qdoc.isModified() and not qdoc.isUndoAvailable(),
          "abrir com listas nao suja o documento nem deixa desfazer")
    volta = de_qt.extrair(qdoc)
    a = [(p.lista, p.lista_nivel, p.recuo_esquerdo_tw, p.recuo_primeira_linha_tw)
         for p in paragrafos_de(volta.paragrafos)]
    b = [(p.lista, p.lista_nivel, p.recuo_esquerdo_tw, p.recuo_primeira_linha_tw)
         for p in paragrafos_de(doc.paragrafos)]
    checa_igual(a, b, "Qt -> modelo: o mesmo numPr e nenhum recuo do nivel vira formatacao direta")
    usar_fontes_do_documento()
    para_qt.concluir_listas(qdoc)
    numerador = pl.numerador_de(qdoc)
    cat = pl.catalogo(qdoc)

    def bloco(texto):
        b = qdoc.begin()
        while b.isValid() and b.text() != texto:
            b = b.next()
        return b
    b1 = bloco("c01")
    linha = b1.layout().lineAt(0)
    checa_igual(round(linha.x()), 720, "deslocamento: o texto do item comeca no recuo esquerdo (720)")
    rot = numerador.rotulos()[b1.blockNumber()]
    a, texto = pl.posicoes(b1, rot, numerador, cat)
    checa_igual((round(a), round(texto)), (360, 720), "o numero fica no recuo da primeira linha (360)")
    b2 = bloco("e01 sufixo espaco")
    rot2 = numerador.rotulos()[b2.blockNumber()]
    a2, texto2 = pl.posicoes(b2, rot2, numerador, cat)
    largura = pl.largura_do_rotulo(b2, rot2, numerador)
    checa(round(texto2 - a2 - largura) > 0 and abs(b2.layout().lineAt(0).x() - texto2) < 1,
          "w:suff space: o texto vem logo depois do numero e de um espaco")
    b3 = bloco("e02 sufixo nada")
    rot3 = numerador.rotulos()[b3.blockNumber()]
    a3, texto3 = pl.posicoes(b3, rot3, numerador, cat)
    checa(abs(texto3 - a3 - pl.largura_do_rotulo(b3, rot3, numerador)) < 0.5,
          "w:suff nothing: o texto encosta no numero")
    checa(round(b1.blockFormat().leftMargin()) == 720,
          "o recuo esquerdo fica em twips no bloco (o Qt nao escala margem horizontal)")
    texto = texto_do_documento(volta)
    checa("1.2.1\tt05 Detalhe" in texto and "•\ts01" in texto and "1. e01 sufixo espaco" in texto
          and "(1)e02 sufixo nada" in texto, "texto sem formatacao: o numero e o sufixo de cada item")


def testar_edicao_preserva_definicoes() -> None:
    secao("editar uma lista do arquivo: as definicoes que o usuario nao mexeu voltam iguais (c14n)")
    doc, _ = ler(docx_de_listas())
    painel = _painel_com(doc)
    qdoc = painel.document()
    alvo = qdoc.begin()
    while alvo.isValid() and alvo.text() != "c06":
        alvo = alvo.next()
    _sel(painel, alvo.position())
    _um_passo(painel, lambda: ed_listas.reiniciar(painel), "Reiniciar num item do arquivo e' um passo")
    ed_listas.reiniciar(painel)
    checa_igual(_rotulos_do_qt(qdoc).get("c06"), "1.", "o item reiniciado mostra 1.")
    modelo = de_qt.extrair(qdoc)
    gravado = escrever(modelo)
    partes = fx.partes_de(gravado)
    original = etree.fromstring(NUMERACAO.encode("utf-8"))
    novo = etree.fromstring(partes["word/numbering.xml"])

    def por_id(raiz, tag, atributo):
        return {el.get(q(atributo)): etree.tostring(el, method="c14n", exclusive=True)
                for el in raiz.findall(q(tag))}
    a_orig, a_novo = por_id(original, "abstractNum", "abstractNumId"), por_id(novo, "abstractNum", "abstractNumId")
    n_orig, n_novo = por_id(original, "num", "numId"), por_id(novo, "num", "numId")
    checa(all(a_novo.get(k) == v for k, v in a_orig.items()) and all(n_novo.get(k) == v for k, v in n_orig.items()),
          "cada abstractNum e num do arquivo volta igual (c14n exclusivo)")
    acrescidos = sorted(set(n_novo) - set(n_orig), key=int)
    checa(len(acrescidos) == 1 and list(novo.findall(q("num")))[-1].get(q("numId")) == acrescidos[0],
          "o reinicio e' uma instancia nova, no fim do numbering.xml")
    checa(_c14n(partes["word/numbering.xml"]) != _c14n(NUMERACAO.encode("utf-8")),
          "contraprova: o numbering.xml mudou (a instancia nova esta' la')")
    conferencia.conferir(gravado, modelo)
    relido, avisos = ler(gravado)
    checa(_rotulos_do_modelo(relido).get("c06") == "1." and not avisos and ordem.validar(partes) == [],
          "relido: o reinicio continua, sem aviso, e o arquivo e' valido")
    numerador = pl.numerador_de(qdoc)
    figura = next(b for b in (qdoc.findBlockByNumber(i) for i in range(qdoc.blockCount()))
                  if b.text() == "f01 marcador de figura")
    rot = numerador.rotulos()[figura.blockNumber()]
    checa(numerador.imagem(rot.nivel.imagem) is not None, "o marcador de figura e' desenhado com a imagem")


def testar_pdf() -> None:
    secao("PDF: os numeros calculados saem como texto")
    from leitor_pdf import ler_pdf, sem_espacos
    from editdoc.interface import impressao
    usar_fontes_do_documento()
    doc, _ = ler(docx_de_listas())
    painel = _painel_com(doc)
    layout = painel.layout_pag
    paginas = list(range(layout.numero_paginas()))
    dados = impressao.gerar_pdf(layout, paginas, impressao.Metadados(titulo="Listas", autor="Teste"))
    texto = sem_espacos(ler_pdf(dados).texto)
    # Os numeros sao pintados depois do texto da folha: saem em sequencia, na ordem dos itens.
    checa("11.11.21.2.122.0.12.1" in texto and "1.1.1.1.1.1.1.2.1.2.2.2.2.0.1." in texto
          and "I.a)b)i.ii.iii.iv.II.a)" in texto,
          "os numeros calculados (1.2.1, 2.0.1, 1.2.2., iv.) estao no PDF, na ordem dos itens")
    checa("1.1.1.1.1.1.1.2.1.2.1." not in texto,
          "contraprova: a sequencia sem o w:lvlRestart (1.2.1.) nao aparece")


# -- edicao ----------------------------------------------------------------------------------

def _novo(texto: str) -> PainelDocumento:
    painel = PainelDocumento("Calibri", 11)
    painel.setPlainText(texto)
    painel.document().clearUndoRedoStacks()
    return painel


def _sel(painel, inicio: int, fim: int | None = None) -> None:
    c = painel.textCursor()
    c.setPosition(inicio)
    if fim is not None:
        c.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
    painel.setTextCursor(c)


def _rotulos(painel) -> list:
    rot = pl.numerador_de(painel.document()).rotulos()
    saida = []
    b = painel.document().begin()
    while b.isValid():
        r = rot.get(b.blockNumber())
        saida.append(r.texto if r is not None else None)
        b = b.next()
    return saida


def _estado(painel) -> tuple:
    """O que o desfazer tem de devolver: o HTML (que nao leva as propriedades de usuario), a
    lista de cada bloco e os numeros."""
    listas = []
    b = painel.document().begin()
    while b.isValid():
        listas.append(pl.lista_do_bloco(b.blockFormat()))
        b = b.next()
    return painel.document().toHtml(), listas, _rotulos(painel)


def _um_passo(painel, comando, mensagem: str) -> None:
    cursor = painel.textCursor()
    antes = _estado(painel)
    comando()
    drenar_eventos()
    mudou = _estado(painel) != antes
    painel.undo()
    drenar_eventos()
    voltou = _estado(painel) == antes
    painel.setTextCursor(cursor)  # o desfazer move o cursor (CLAUDE.md)
    checa(mudou and voltou, f"{mensagem} (mudou: {mudou}, um desfazer voltou tudo: {voltou})")


def testar_botoes() -> None:
    secao("botoes: numeracao, marcadores e galeria, um passo de desfazer cada")
    p = _novo("um\ndois\ntres")
    _sel(p, 0, len(p.toPlainText()))
    _um_passo(p, lambda: ed_listas.alternar_numeracao(p), "Numeracao e' um passo de desfazer")
    _sel(p, 0, len(p.toPlainText()))
    ed_listas.alternar_numeracao(p)
    checa_igual(_rotulos(p), ["1.", "2.", "3."], "Numeracao: 1. 2. 3.")
    _sel(p, 0, len(p.toPlainText()))
    ed_listas.alternar_numeracao(p, "letra_minuscula")
    checa_igual(_rotulos(p), ["a.", "b.", "c."], "galeria: a. b. c. troca o formato")
    _sel(p, 0, len(p.toPlainText()))
    ed_listas.alternar_numeracao(p, "letra_minuscula")
    checa_igual(_rotulos(p), [None, None, None], "o mesmo formato de novo desliga a lista")
    _sel(p, 0, len(p.toPlainText()))
    ed_listas.alternar_marcadores(p, "quadrado")
    checa_igual([mod.texto_visivel(r) for r in _rotulos(p)], ["▪"] * 3, "galeria: marcador quadrado")
    modelo = de_qt.extrair(p.document())
    partes = fx.partes_de(escrever(modelo))
    checa(b"Wingdings" in partes["word/numbering.xml"] and ordem.validar(partes) == [],
          "o marcador vai ao numbering.xml com a fonte Wingdings, e o arquivo e' valido")
    _sel(p, 0, len(p.toPlainText()))
    ed_listas.aplicar_multinivel(p, "decimal")
    _sel(p, p.document().findBlockByNumber(1).position())
    _um_passo(p, lambda: QTest.keyClick(p, Qt.Key.Key_Tab), "Tab no item e' um passo de desfazer")
    _sel(p, p.document().findBlockByNumber(1).position())
    QTest.keyClick(p, Qt.Key.Key_Tab)
    checa_igual(_rotulos(p), ["1.", "1.1.", "2."], "varios niveis: Tab no inicio do item desce o nivel")
    _sel(p, p.document().findBlockByNumber(1).position())
    QTest.keyClick(p, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
    checa_igual(_rotulos(p), ["1.", "2.", "3."], "Shift+Tab sobe o nivel de volta")
    _sel(p, p.document().findBlockByNumber(1).position() + 1)
    QTest.keyClick(p, Qt.Key.Key_Tab)
    checa("\t" in p.document().findBlockByNumber(1).text() and _rotulos(p) == ["1.", "2.", "3."],
          "contraprova: Tab no meio do item insere tabulacao, sem mudar o nivel")


def testar_teclado() -> None:
    secao("teclado: Enter num item vazio sai da lista; Backspace no inicio tira o numero")
    p = _novo("um\ndois")
    _sel(p, 0, len(p.toPlainText()))
    ed_listas.alternar_numeracao(p)
    _sel(p, len(p.toPlainText()))
    QTest.keyClick(p, Qt.Key.Key_Return)
    drenar_eventos()
    checa_igual(_rotulos(p), ["1.", "2.", "3."], "Enter no fim do item: o item novo continua a lista")
    QTest.keyClick(p, Qt.Key.Key_Return)
    drenar_eventos()
    checa_igual((_rotulos(p), p.document().blockCount()), (["1.", "2.", None], 3),
                "Enter no item vazio: sai da lista, sem paragrafo a mais")
    p.undo()
    drenar_eventos()
    checa_igual(_rotulos(p), ["1.", "2.", "3."], "um desfazer devolve o item")
    _sel(p, p.document().findBlockByNumber(2).position())
    QTest.keyClick(p, Qt.Key.Key_Tab)
    drenar_eventos()
    checa_igual(_rotulos(p), ["1.", "2.", "a."], "Tab no item vazio desce para o nivel 2")
    QTest.keyClick(p, Qt.Key.Key_Return)
    drenar_eventos()
    checa_igual((_rotulos(p), p.document().blockCount()), (["1.", "2.", "3."], 3),
                "Enter num item vazio do nivel 2: sobe um nivel, sem paragrafo novo")
    QTest.keyClick(p, Qt.Key.Key_Return)
    drenar_eventos()
    checa_igual((_rotulos(p), p.document().blockCount()), (["1.", "2.", None], 3),
                "...e no primeiro nivel sai da lista")
    p.undo()
    drenar_eventos()
    checa_igual(_rotulos(p), ["1.", "2.", "3."], "um desfazer devolve o item no primeiro nivel")
    _sel(p, p.document().findBlockByNumber(1).position())
    bloco = p.document().findBlockByNumber(1)
    x_antes = bloco.layout().lineAt(0).x()
    QTest.keyClick(p, Qt.Key.Key_Backspace)
    drenar_eventos()
    bloco = p.document().findBlockByNumber(1)
    checa(_rotulos(p)[1] is None and p.document().blockCount() == 3
          and abs(bloco.layout().lineAt(0).x() - x_antes) < 1,
          "Backspace no inicio: o numero sai e o texto fica onde estava")
    QTest.keyClick(p, Qt.Key.Key_Backspace)
    drenar_eventos()
    bloco = p.document().findBlockByNumber(1)
    checa(round(bloco.blockFormat().leftMargin()) == 0 and p.document().blockCount() == 3,
          "Backspace de novo: sai do recuo (sem juntar com o paragrafo de cima)")
    QTest.keyClick(p, Qt.Key.Key_Backspace)
    checa_igual(p.document().blockCount(), 2, "o terceiro Backspace junta com o paragrafo de cima")


def testar_reiniciar_continuar_valor() -> None:
    secao("Reiniciar em 1, Continuar numeracao e Definir valor (um desfazer cada)")
    p = _novo("a\nb\ncomum\nc\nd")
    _sel(p, 0, 3)
    ed_listas.alternar_numeracao(p)
    _sel(p, p.document().findBlockByNumber(3).position(), len(p.toPlainText()))
    ed_listas.alternar_numeracao(p)
    checa_igual(_rotulos(p), ["1.", "2.", None, "1.", "2."], "lista nova depois de texto recomeca em 1")
    _sel(p, p.document().findBlockByNumber(3).position())
    _um_passo(p, lambda: ed_listas.continuar(p), "Continuar numeracao e' um passo de desfazer")
    ed_listas.continuar(p)
    checa_igual(_rotulos(p), ["1.", "2.", None, "3.", "4."], "Continuar: 3. e 4.")
    _sel(p, p.document().findBlockByNumber(4).position())
    ed_listas.reiniciar(p)
    checa_igual(_rotulos(p), ["1.", "2.", None, "3.", "1."], "Reiniciar em 1 no ultimo item")
    _sel(p, p.document().findBlockByNumber(1).position())
    ed_listas.definir_valor(p, 10)
    checa_igual(_rotulos(p), ["1.", "10.", None, "11.", "1."],
                "Definir valor 10: o item e os seguintes da mesma lista continuam dele")
    modelo = de_qt.extrair(p.document())
    relido, avisos = ler(escrever(modelo))
    checa(list(_rotulos_do_modelo(relido).values()) == ["1.", "10.", None, "11.", "1."] and not avisos,
          "o arquivo gravado tem os mesmos numeros (startOverride nas instancias novas)")


def testar_titulos_e_copia() -> None:
    secao("titulos numerados pelo estilo, aumentar recuo e copiar/colar com a lista")
    from editdoc.edicao import estilos as ed_estilos
    from editdoc.edicao import formatacao
    p = _novo("Capitulo\nSecao\nTexto")
    _sel(p, 0)
    ed_estilos.aplicar_estilo(p, "heading 1")
    _sel(p, p.document().findBlockByNumber(1).position())
    ed_estilos.aplicar_estilo(p, "heading 2")
    _sel(p, 0)
    ed_listas.aplicar_multinivel(p, "titulos")
    checa_igual(_rotulos(p), ["1", "1.1", None], "titulos numerados: 1 e 1.1 pelo estilo")
    modelo = de_qt.extrair(p.document())
    partes = fx.partes_de(escrever(modelo))
    raiz = etree.fromstring(partes["word/styles.xml"])
    com_num = [s.get(q("styleId")) for s in raiz.iter(q("style"))
               if s.find(q("pPr") + "/" + q("numPr")) is not None]
    checa("Heading1" in com_num and "Heading2" in com_num and b"<w:numPr>" not in partes["word/document.xml"],
          "o numPr vai para os estilos Titulo 1 e 2, nao para os paragrafos")
    checa_igual(ordem.validar(partes), [], "e o arquivo e' valido")
    _sel(p, p.document().findBlockByNumber(1).position())
    formatacao.alterar_recuo_ou_nivel(p, True)
    checa_igual(_rotulos(p), ["1", "1.0.1", None],
                "Aumentar recuo num titulo numerado: vira Titulo 3 (nivel de baixo)")
    _sel(p, p.document().findBlockByNumber(2).position())
    formatacao.alterar_recuo_ou_nivel(p, True)
    checa_igual(round(p.document().findBlockByNumber(2).blockFormat().leftMargin()), 720,
                "contraprova: fora de lista, Aumentar recuo soma 720 twips")

    q2 = _novo("x\ny\n")
    _sel(q2, 0, 3)
    ed_listas.alternar_numeracao(q2)
    _sel(q2, 0, 3)
    q2.copy()
    _sel(q2, len(q2.toPlainText()))
    q2.paste()
    drenar_eventos()
    checa_igual(_rotulos(q2), ["1.", "2.", "3.", "4."], "colar no mesmo documento mantem a lista")
    outro = _novo("")
    outro.paste()
    drenar_eventos()
    checa_igual([r for r in _rotulos(outro) if r], ["1.", "2."],
                "colar em outro documento traz a definicao da lista")
    checa(bool(fx_numeracao.validar(fx.partes_de(escrever(de_qt.extrair(outro.document())))) == []),
          "o documento colado grava valido")
    from PySide6.QtCore import QMimeData
    md = QMimeData()
    md.setHtml("<ol><li>um</li><li>dois</li></ol><ul><li>ponto</li></ul>")
    QApplication.clipboard().setMimeData(md)
    externo = _novo("")
    externo.paste()
    drenar_eventos()
    blocos = [externo.document().findBlockByNumber(i) for i in range(externo.document().blockCount())]
    checa([mod.texto_visivel(r) for r in _rotulos(externo) if r] == ["1.", "2.", "•"]
          and all(b.textList() is None for b in blocos),
          "HTML de outro programa (<ol>, <ul>) vira lista do EditDoc, sem o QTextList")
    QApplication.clipboard().clear()


def main() -> int:
    testar_formatos()
    testar_calculo_puro()
    testar_leitura_e_oraculo()
    testar_ida_e_volta_c14n()
    testar_validador()
    testar_arquivo_hostil()
    testar_caixa_de_texto()
    testar_qt_numeros_e_recuos()
    testar_edicao_preserva_definicoes()
    testar_pdf()
    testar_botoes()
    testar_teclado()
    testar_reiniciar_continuar_valor()
    testar_titulos_e_copia()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
