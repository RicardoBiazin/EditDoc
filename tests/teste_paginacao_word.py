"""Paginacao como a do Word (0.1.17): cada regra com a sua contraprova, e o oraculo.

O Word grava em cada pagina onde ela comecou na ultima vez (`w:lastRenderedPageBreak`). Os
arquivos reais da medicao (docs/SPIKES.md "0.1.17") nao entram no repositorio: aqui as fixtures
sao geradas em codigo, com o comportamento de cada regra, e cada uma tem a contraprova (a mesma
fixture com a compensacao desligada, ou sem a propriedade, da' o layout antigo).

- linha da fonte: Arial 12 avanca 276 twips (o Word soma o espaco externo), nao 268;
- espaco entre paragrafos somado; `contextualSpacing` entre paragrafos do mesmo estilo;
- espaco antes no alto da pagina: fica (quebra natural e quebra do usuario), sem o depois do de
  cima;
- linhas viuvas e orfas, manter com o proximo, manter linhas juntas, quebra antes do estilo;
- o paragrafo vazio junto da tabela (o Qt o esconde) e os espacos junto dela;
- a imagem na linha com entrelinha multipla (o multiplo vale sobre a linha do texto);
- a marca de paragrafo do paragrafo vazio (pPr/rPr);
- nada disso muda o arquivo gravado (a conferencia passa, o document.xml e' o mesmo);
- o desfazer devolve tudo; o copiar leva os valores de verdade;
- oraculo sintetico: um documento com `w:lastRenderedPageBreak` onde o Word quebraria (modelo
  simples do Word, independente do codigo) e a fracao que o EditDoc acerta;
- custo por tecla da compensacao e das regras.
"""

from __future__ import annotations

import os
import pathlib
import statistics
import time

from ajudantes import (checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao)
import fixtures_docx as fx  # noqa: E402 - depois do ajudantes (o caminho do projeto)

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFontDatabase, QTextCursor, QTextDocument, QTextDocumentFragment  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from editdoc import configuracao  # noqa: E402
from editdoc.formato_docx import conferencia  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402
from editdoc.interface.paginacao import ConjuntoDePaginacao  # noqa: E402
from editdoc.modelo import paginacao as mod  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402
from editdoc.ponte_qt import estilos as pq_estilos  # noqa: E402
from editdoc.ponte_qt import marcas as pq_marcas  # noqa: E402
from editdoc.ponte_qt import paginacao as pq  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
FONTES = pathlib.Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
#: Arial 12 no Word: (winAscent + winDescent + espaco externo) / unidades x 240 twips.
LINHA_WORD_ARIAL_12 = (1854 + 434 + 67) / 2048 * 240

ESTILOS = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="{W}">'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>'
    '<w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
    '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Lista"><w:name w:val="Lista"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:spacing w:before="120" w:after="120"/><w:contextualSpacing/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Corpo"><w:name w:val="Corpo"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:spacing w:before="120" w:after="120"/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Titulo"><w:name w:val="Titulo"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:keepNext/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Junto"><w:name w:val="Junto"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:keepLines/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Solto"><w:name w:val="Solto"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:widowControl w:val="0"/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Capitulo"><w:name w:val="Capitulo"/>'
    '<w:basedOn w:val="Normal"/><w:pPr><w:pageBreakBefore/></w:pPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Calibri"><w:name w:val="Calibri"/><w:basedOn w:val="Normal"/>'
    '<w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:style>'
    '</w:styles>')


def p(texto: str = "", estilo: str | None = None, ppr: str = "", linhas: int = 1) -> str:
    """Um paragrafo; `linhas` > 1 parte o texto em linhas com w:br (o numero de linhas fica
    exato, sem depender da largura)."""
    pstyle = f'<w:pStyle w:val="{estilo}"/>' if estilo else ""
    pr = f"<w:pPr>{pstyle}{ppr}</w:pPr>" if pstyle or ppr else ""
    if not texto:
        return f"<w:p>{pr}</w:p>"
    corpo = "<w:br/>".join(f"<w:t>{texto} {i + 1}</w:t>" for i in range(linhas))
    return f"<w:p>{pr}<w:r>{corpo}</w:r></w:p>"


def docx(corpo: str) -> bytes:
    return fx.docx_com_xml(corpo, partes_extra={"word/styles.xml": ESTILOS.encode("utf-8")})


def carregar_fontes() -> bool:
    ok = True
    for nome in ("arial.ttf", "arialbd.ttf", "calibri.ttf", "calibrib.ttf"):
        caminho = FONTES / nome
        if not caminho.is_file() or QFontDatabase.addApplicationFont(str(caminho)) < 0:
            ok = False
    return ok


def janela() -> JanelaPrincipal:
    j = JanelaPrincipal(configuracao.padrao())
    j.resize(1100, 900)
    j.show()
    drenar_eventos()
    return j


def abrir(j, dados: bytes, partes=None, ligado: bool = True):
    pag = j.painel.layout_pag.paginacao
    pag.ligado = ligado
    pag.partes = set(ConjuntoDePaginacao.PARTES if partes is None else partes)
    modelo, avisos = ler(dados)
    j.carregar(modelo, avisos, None)
    drenar_eventos()
    j.painel.layout_pag.atualizar_secoes()
    return j.painel.layout_pag


def bloco_com(lay, texto: str):
    b = lay.doc.begin()
    while b.isValid():
        if b.text().startswith(texto):
            return b
        b = b.next()
    raise AssertionError(f"bloco {texto!r} nao achado")


def paginas(lay, bloco) -> list[int]:
    r = lay.doc.documentLayout().blockBoundingRect(bloco)
    l = bloco.layout()
    return [int((r.top() + l.lineAt(i).y() + 1) // lay.hb) for i in range(l.lineCount())]


def topo_da_linha(lay, bloco, i: int = 0) -> float:
    return lay.doc.documentLayout().blockBoundingRect(bloco).top() + bloco.layout().lineAt(i).y()


def passo(lay, a: str, b: str) -> float:
    return topo_da_linha(lay, bloco_com(lay, b)) - topo_da_linha(lay, bloco_com(lay, a))


def fillers(n: int) -> str:
    return "".join(p(f"F{i:03d}") for i in range(n))


# -- modelo (sem Qt) ---------------------------------------------------------------------------

def testar_regras_puras() -> None:
    secao("modelo: espaco somado, viuvas e orfas, linhas que cabem, metricas da fonte")
    checa_igual(mod.espaco_entre(240, 360, False, True, True), 600.0,
                "estilos diferentes: o Word soma depois + antes (o contextual nao vale)")
    checa_igual(mod.espaco_entre(240, 360, True, True, True), 0.0,
                "mesmo estilo com contextualSpacing nos dois: nada")
    checa_igual(mod.espaco_entre(240, 360, True, False, True), 240.0,
                "so' o de baixo contextual: fica o depois do de cima")
    checa_igual(mod.espaco_entre(240, 360, False, False, False, quebra=True), 360.0,
                "depois de uma quebra do usuario: so' o espaco antes")
    checa(mod.deve_empurrar(1, 3, True, False, False), "orfa (1 linha embaixo) desce o paragrafo")
    checa(mod.deve_empurrar(2, 1, True, False, False), "viuva com 2 linhas em cima: desce inteiro")
    checa(not mod.deve_empurrar(3, 1, True, False, False),
          "limite: viuva com 3 linhas em cima pediria descer UMA linha (fica)")
    checa(not mod.deve_empurrar(1, 3, False, False, False), "contraprova: sem o controle, fica")
    checa(mod.deve_empurrar(2, 2, False, True, False), "manter linhas juntas: desce se partido")
    checa(not mod.deve_empurrar(1, 3, True, True, True), "o primeiro da pagina nunca desce")
    checa_igual(mod.linhas_que_cabem(0, [(276, 268)] * 5, 1000), 3, "3 linhas de 276 cabem em 1000")
    head = b"\0" * 18 + (2048).to_bytes(2, "big") + b"\0" * 40
    hhea = b"\0" * 4 + (1854).to_bytes(2, "big") + (-434).to_bytes(2, "big", signed=True) + \
        (67).to_bytes(2, "big") + b"\0" * 30
    os2 = b"\0" * 74 + (1854).to_bytes(2, "big") + (434).to_bytes(2, "big") + b"\0" * 20
    checa_igual(mod.unidades_da_linha_word(head, hhea, os2), (2048, 2288, 2355),
                "metricas do Arial: win 2288, Word 2355 (o lineGap que passa do win)")
    hhea0 = hhea[:8] + (0).to_bytes(2, "big") + hhea[10:]
    checa_igual(mod.unidades_da_linha_word(head, hhea0, os2)[2], 2288,
                "contraprova: sem lineGap, o Word usa so' o win")


def testar_flags_dos_estilos() -> None:
    secao("modelo: on/off de paginacao pela cadeia de estilos, docDefaults e paragrafo")
    modelo, _ = ler(docx(p("x")))
    regras = mod.RegrasDePaginacao(modelo.estilos)
    checa(regras.flag("Titulo", None, "keepNext"), "keepNext do estilo")
    checa(not regras.flag("Normal", None, "keepNext"), "Normal sem keepNext")
    checa(regras.flag("Normal", None, "widowControl"), "widowControl ligado por padrao (Word)")
    checa(not regras.flag("Solto", None, "widowControl"), "widowControl w:val=0 no estilo")
    checa(regras.flag("Lista", None, "contextualSpacing"), "contextualSpacing do estilo")
    extras = (f'<w:pPr xmlns:w="{W}"><w:keepNext></w:keepNext><w:pPrChange w:author="a">'
              '<w:pPr><w:keepLines></w:keepLines></w:pPr></w:pPrChange></w:pPr>')
    checa(regras.flag("Normal", extras, "keepNext"), "keepNext direto do paragrafo (c14n)")
    checa(not regras.flag("Normal", extras, "keepLines"),
          "contraprova: o keepLines de dentro do pPrChange (o de antes da revisao) nao vale")


# -- com Qt ------------------------------------------------------------------------------------

def testar_linha_da_fonte(j) -> None:
    secao("altura da linha: o Word soma o espaco externo da fonte (Arial 12: 276 twips)")
    dados = docx(p("A1") + p("A2") + p("C1", "Calibri") + p("C2", "Calibri"))
    lay = abrir(j, dados)
    checa(abs(passo(lay, "A1", "A2") - LINHA_WORD_ARIAL_12) < 1.5,
          f"Arial 12 avanca {passo(lay, 'A1', 'A2'):.1f} twips (Word {LINHA_WORD_ARIAL_12:.1f})")
    calibri = passo(lay, "C1", "C2")
    lay = abrir(j, dados, ligado=False)
    checa(abs(passo(lay, "A1", "A2") - 268) < 1.5,
          f"contraprova: sem a compensacao o Qt avanca {passo(lay, 'A1', 'A2'):.1f} (268)")
    checa(abs(calibri - passo(lay, "C1", "C2")) < 1.0,
          "Calibri nao tem espaco externo: a linha nao muda")


def testar_espaco_somado(j) -> None:
    secao("espaco entre paragrafos: o Word soma; contextualSpacing entre o mesmo estilo")
    corpo = (p("S1", ppr='<w:spacing w:after="240"/>') + p("S2", ppr='<w:spacing w:before="360"/>')
             + p("L1", "Lista") + p("L2", "Lista") + p("K1", "Corpo") + p("K2", "Corpo")
             + p("L3", "Lista") + p("N1"))
    lay = abrir(j, docx(corpo))
    linha = LINHA_WORD_ARIAL_12
    checa(abs(passo(lay, "S1", "S2") - (linha + 600)) < 2, "depois 240 + antes 360 = 600")
    checa(abs(passo(lay, "L1", "L2") - linha) < 2, "Lista + Lista (contextualSpacing): sem espaco")
    checa(abs(passo(lay, "K1", "K2") - (linha + 240)) < 2,
          "contraprova: Corpo + Corpo (mesmo espaco, sem contextual) = 120 + 120")
    checa(abs(passo(lay, "L2", "K1") - (linha + 240)) < 2,
          "estilos diferentes: o contextual nao vale (120 + 120)")
    checa(abs(passo(lay, "L3", "N1") - (linha + 120)) < 2, "Lista + Normal: so' o depois")
    bf = bloco_com(lay, "S2").blockFormat()
    checa_igual(pq_estilos.props_de_bloco(bf).get("espaco_antes_tw"), 360,
                "o paragrafo continua com 360 antes (o valor de verdade)")
    lay = abrir(j, docx(corpo), ligado=False)
    checa(abs(passo(lay, "S1", "S2") - (268 + 360)) < 2,
          "contraprova: sem a compensacao o Qt usa o maior (360)")
    checa(abs(passo(lay, "L1", "L2") - (268 + 120)) < 2,
          "contraprova: sem a compensacao o contextualSpacing nao vale")


def capacidade(j) -> int:
    """Quantas linhas de Arial 12 simples cabem numa pagina (o mesmo papel das fixtures)."""
    lay = abrir(j, docx(fillers(120)))
    n = 0
    b = lay.doc.begin()
    while b.isValid():
        if b.text().startswith("F") and paginas(lay, b) == [0]:
            n += 1
        b = b.next()
    return n


def testar_viuvas_e_orfas(j, cap: int) -> None:
    secao("linhas viuvas e orfas (ligado por padrao), manter linhas juntas")
    sem = ConjuntoDePaginacao.PARTES - {"regras"}
    orfa = docx(fillers(cap - 1) + p("T", linhas=4) + p("fim"))
    lay = abrir(j, orfa, partes=sem)
    checa_igual(paginas(lay, bloco_com(lay, "T")), [0, 1, 1, 1],
                "contraprova (sem as regras): uma linha orfa no pe' da pagina 1")
    lay = abrir(j, orfa)
    checa_igual(paginas(lay, bloco_com(lay, "T")), [1, 1, 1, 1], "orfa: o paragrafo desce inteiro")
    checa(pq.eh_regra(bloco_com(lay, "T").blockFormat()), "pela quebra das regras (nao do usuario)")
    lay = abrir(j, docx(fillers(cap - 1) + p("T", "Solto", linhas=4) + p("fim")))
    checa_igual(paginas(lay, bloco_com(lay, "T")), [0, 1, 1, 1],
                "contraprova: widowControl w:val=0 deixa a orfa")
    viuva = docx(fillers(cap - 2) + p("T", linhas=3) + p("fim"))
    lay = abrir(j, viuva, partes=sem)
    checa_igual(paginas(lay, bloco_com(lay, "T")), [0, 0, 1], "contraprova: viuva no alto da 2")
    lay = abrir(j, viuva)
    checa_igual(paginas(lay, bloco_com(lay, "T")), [1, 1, 1],
                "viuva com duas linhas em cima: o paragrafo desce inteiro")
    lay = abrir(j, docx(fillers(cap - 3) + p("T", linhas=4) + p("fim")))
    checa_igual(paginas(lay, bloco_com(lay, "T")), [0, 0, 0, 1],
                "limite registrado: a viuva de 3 + 1 fica (o Word desceria uma linha)")
    juntas = docx(fillers(cap - 2) + p("T", "Junto", linhas=4) + p("fim"))
    lay = abrir(j, juntas)
    checa_igual(paginas(lay, bloco_com(lay, "T")), [1, 1, 1, 1], "manter linhas juntas: desce")
    lay = abrir(j, docx(fillers(cap - 2) + p("T", linhas=4) + p("fim")))
    checa_igual(paginas(lay, bloco_com(lay, "T")), [0, 0, 1, 1],
                "contraprova: sem keepLines, 2 + 2 fica partido")


def testar_manter_com_o_proximo(j, cap: int) -> None:
    secao("manter com o proximo e quebra antes do estilo")
    doc = docx(fillers(cap - 1) + p("H", "Titulo") + p("P", linhas=2) + p("fim"))
    lay = abrir(j, doc)
    checa_igual((paginas(lay, bloco_com(lay, "H")), paginas(lay, bloco_com(lay, "P"))),
                ([1], [1, 1]), "o titulo com keepNext desce com o paragrafo de baixo")
    lay = abrir(j, docx(fillers(cap - 1) + p("H") + p("P", linhas=2) + p("fim")))
    checa_igual(paginas(lay, bloco_com(lay, "H")), [0], "contraprova: sem keepNext fica na 1")
    cadeia = docx(fillers(cap - 2) + p("H1", "Titulo") + p("H2", "Titulo") + p("P", linhas=2))
    lay = abrir(j, cadeia)
    checa_igual((paginas(lay, bloco_com(lay, "H1")), paginas(lay, bloco_com(lay, "H2"))),
                ([1], [1]), "a cadeia de keepNext desce inteira")
    lay = abrir(j, docx(fillers(5) + p("C", "Capitulo") + p("fim")))
    checa_igual(paginas(lay, bloco_com(lay, "C")), [1], "pageBreakBefore do estilo: pagina nova")
    lay = abrir(j, docx(fillers(5) + p("C", "Capitulo") + p("fim")), partes=set())
    checa_igual(paginas(lay, bloco_com(lay, "C")), [0], "contraprova: sem as regras, fica")
    # A quebra das regras nao e' do usuario: o arquivo gravado nao a leva.
    lay = abrir(j, doc)
    gravado = escrever(j._modelo_atual())
    checa(b"pageBreakBefore" not in fx.partes_de(gravado)["word/document.xml"]
          and b'w:type="page"' not in fx.partes_de(gravado)["word/document.xml"],
          "o arquivo gravado nao tem a quebra das regras")


def testar_espaco_no_topo(j, cap: int) -> None:
    secao("espaco antes no alto da pagina: o Word o mantem (sem o depois do de cima)")
    doc = docx(fillers(cap) + p("P", ppr='<w:spacing w:before="480"/>') + p("fim"))
    lay = abrir(j, doc)
    b = bloco_com(lay, "P")
    checa(abs(topo_da_linha(lay, b) - lay.hb - 480) < 2,
          f"pagina nova natural: o espaco antes fica ({topo_da_linha(lay, b) - lay.hb:.0f})")
    lay = abrir(j, doc, partes=ConjuntoDePaginacao.PARTES - {"topo"})
    sobra = topo_da_linha(lay, bloco_com(lay, "P")) - lay.hb
    checa(sobra < 480 - 20,
          f"contraprova: sem a regra o Qt perde (parte d)o espaco no alto da pagina ({sobra:.0f})")
    quebra = docx(p("A", ppr='<w:spacing w:after="720"/>')
                  + p("Q", ppr='<w:pageBreakBefore/><w:spacing w:before="480"/>') + p("fim"))
    lay = abrir(j, quebra)
    checa(abs(topo_da_linha(lay, bloco_com(lay, "Q")) - lay.hb - 480) < 2,
          "depois da quebra do usuario: so' o antes (480), sem o depois do de cima")
    lay = abrir(j, quebra, ligado=False)
    checa(abs(topo_da_linha(lay, bloco_com(lay, "Q")) - lay.hb - 720) < 2,
          "contraprova: sem a compensacao o Qt poe o maior (720)")


TABELA = ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid>'
          '<w:gridCol w:w="4000"/></w:tblGrid><w:tr><w:tc><w:tcPr><w:tcW w:w="4000" w:type="dxa"/>'
          '</w:tcPr><w:p><w:r><w:t>celula</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')


def _tabela(lay):
    return lay.doc.rootFrame().childFrames()[0]


def testar_tabela(j) -> None:
    secao("vazio e espacos junto da tabela (o Qt esconde o vazio e ignora os espacos)")
    corpo = p("Antes") + p() + TABELA + p() + p("Depois")
    for ligado in (True, False):
        lay = abrir(j, docx(corpo), ligado=ligado)
        dl = lay.doc.documentLayout()
        r = dl.frameBoundingRect(_tabela(lay))
        antes = topo_da_linha(lay, bloco_com(lay, "Antes"))
        celula = topo_da_linha(lay, bloco_com(lay, "celula"))
        depois = topo_da_linha(lay, bloco_com(lay, "Depois"))
        if ligado:
            checa(celula - antes > 2 * LINHA_WORD_ARIAL_12 - 30,
                  f"o vazio antes da tabela ocupa a linha dele ({celula - antes:.0f})")
            checa(depois - r.bottom() > LINHA_WORD_ARIAL_12 - 30,
                  f"o vazio depois da tabela ocupa a linha dele ({depois - r.bottom():.0f})")
        else:
            checa(celula - antes < LINHA_WORD_ARIAL_12 + 30,
                  "contraprova: sem a compensacao o Qt esconde o vazio antes da tabela")
            checa(depois - r.bottom() < 30, "contraprova: e o vazio depois dela")
    corpo = (p("P1", ppr='<w:spacing w:after="480"/>') + TABELA
             + p("P2", ppr='<w:spacing w:before="480"/>'))
    medidas = {}
    for ligado in (True, False):
        lay = abrir(j, docx(corpo), ligado=ligado)
        celula = topo_da_linha(lay, bloco_com(lay, "celula"))
        medidas[ligado] = (celula - topo_da_linha(lay, bloco_com(lay, "P1")),
                           topo_da_linha(lay, bloco_com(lay, "P2")) - celula)
    extra = LINHA_WORD_ARIAL_12 - 268
    checa(abs(medidas[True][0] - medidas[False][0] - 480 - extra) < 20,
          "o espaco depois do paragrafo de cima da tabela entra (o Qt o ignora): "
          f"{medidas[True][0] - medidas[False][0]:.0f}")
    checa(abs(medidas[True][1] - medidas[False][1] - 480 - extra) < 20,
          "o espaco antes do paragrafo de baixo da tabela entra (o Qt o ignora): "
          f"{medidas[True][1] - medidas[False][1]:.0f}")


#: Mesma tabela de TABELA, com margem interna da tabela (tblCellMar) e a da celula (tcMar) em todos
#: os lados: a celula tem de valer a sua (300/600 twips), como no Word.
TABELA_TCMAR = ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblCellMar><w:top w:w="0" '
                'w:type="dxa"/><w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/>'
                '<w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>'
                '<w:gridCol w:w="4000"/></w:tblGrid><w:tr><w:tc><w:tcPr><w:tcW w:w="4000" '
                'w:type="dxa"/><w:tcMar><w:top w:w="300" w:type="dxa"/><w:left w:w="600" '
                'w:type="dxa"/><w:bottom w:w="300" w:type="dxa"/><w:right w:w="600" '
                'w:type="dxa"/></w:tcMar></w:tcPr><w:p><w:r><w:t>celula</w:t></w:r></w:p>'
                '</w:tc></w:tr></w:tbl>')


def _quadro_tabela(lay):
    from PySide6.QtGui import QTextTable
    for f in lay.doc.rootFrame().childFrames():
        if isinstance(f, QTextTable):
            return f
    return None


def testar_margem_da_celula(j) -> None:
    secao("margem da celula (w:tcMar) vence a da tabela (w:tblCellMar), em px96")
    lay = abrir(j, docx(p("Antes") + TABELA_TCMAR + p("Depois")))
    tab = _quadro_tabela(lay)
    checa(tab is not None, "a tabela com tcMar existe no documento")
    fmt = tab.cellAt(0, 0).format().toTableCellFormat()
    lados = (fmt.topPadding(), fmt.leftPadding(), fmt.bottomPadding(), fmt.rightPadding())
    checa(lados == (20.0, 40.0, 20.0, 40.0), f"tcMar 300/600 twips = 20/40 px: {lados}")
    alto_com = lay.doc.documentLayout().frameBoundingRect(tab).height()
    lay = abrir(j, docx(p("Antes") + TABELA + p("Depois")))
    tab = _quadro_tabela(lay)
    fmt = tab.cellAt(0, 0).format().toTableCellFormat()
    sem = (fmt.topPadding(), fmt.leftPadding(), fmt.bottomPadding(), fmt.rightPadding())
    checa(sem == (0.0, 7.2, 0.0, 7.2),
          f"contraprova: sem tcMar vale a margem padrao (108 twips = 7,2 px): {sem}")
    alto_sem = lay.doc.documentLayout().frameBoundingRect(tab).height()
    # A altura do quadro sai em unidades de 1440 dpi (px96 x 15). So' o topo e a base mudam a
    # altura da linha: 300 + 300 twips = 40 px96 = 600 unidades a mais.
    unidades = 15.0
    diferenca = alto_com - alto_sem
    checa(abs(diferenca - 40 * unidades) < 2,
          f"a altura da linha cresce com o tcMar de cima e de baixo: {diferenca:.1f} unidades")
    checa(diferenca > 30 * unidades,
          f"a diferenca passa de 30 px (sem o tcMar, a tela daria 0): {diferenca:.1f}")


def testar_imagem_na_linha(j) -> None:
    secao("imagem com entrelinha 1,5: o multiplo vale sobre a linha do texto, nao a da imagem")
    img = fx.imagem(fx.png(40, 40), largura_cm=3.0, altura_cm=3.0)
    doc = Documento(paragrafos=[Paragrafo(runs=[Run("I0")]),
                                Paragrafo(runs=[Run(imagem=img)], espacamento_linha_pct=150),
                                Paragrafo(runs=[Run("I2")])])
    dados = fx.bytes_de(doc)
    lay = abrir(j, dados)
    b = lay.doc.begin().next()
    altura = b.layout().lineAt(0).height()
    passo_img = topo_da_linha(lay, b.next()) - topo_da_linha(lay, b)
    checa(passo_img < altura * 1.25,
          f"a linha da imagem avanca {passo_img:.0f} (imagem {altura:.0f}): sem 1,5 x imagem")
    lay = abrir(j, dados, ligado=False)
    b = lay.doc.begin().next()
    passo_img = topo_da_linha(lay, b.next()) - topo_da_linha(lay, b)
    checa(passo_img > altura * 1.4, f"contraprova: sem a compensacao, 1,5 x imagem ({passo_img:.0f})")


def testar_marca_de_paragrafo(j) -> None:
    secao("paragrafo vazio: a altura e' a da marca de paragrafo (pPr/rPr), como no Word")
    corpo = (p("A") + p(ppr='<w:rPr><w:sz w:val="48"/></w:rPr>') + p("B") + p() + p("C"))
    lay = abrir(j, docx(corpo))
    grande = passo(lay, "A", "B") - LINHA_WORD_ARIAL_12
    normal = passo(lay, "B", "C") - LINHA_WORD_ARIAL_12
    checa(abs(grande - 2 * LINHA_WORD_ARIAL_12) < 20,
          f"marca de 24 pt: a linha vazia tem {grande:.0f} twips (o dobro da de 12 pt)")
    checa(abs(normal - LINHA_WORD_ARIAL_12) < 5,
          f"contraprova: o vazio sem rPr na marca tem a linha do texto ({normal:.0f})")


def testar_gravacao(j) -> None:
    secao("nada muda no arquivo gravado; a conferencia passa; o salvo reabre igual")
    corpo = (p("S1", "Corpo") + p("S2", "Corpo") + p() + TABELA + p() + p("H", "Titulo")
             + p("L1", "Lista", linhas=2) + p("L2", "Lista") + p(ppr='<w:rPr><w:sz w:val="40"/></w:rPr>'))
    dados = docx(fillers(40) + corpo + fillers(40))
    lay = abrir(j, dados)
    checa(any(bloco_com(lay, "S2").blockFormat().hasProperty(x) for x in pq.PROPS_DE_PAGINACAO),
          "a fixture tem blocos compensados")
    com = escrever(j._modelo_atual())
    conferencia.conferir(com, j._modelo_atual())
    checa(True, "a conferencia aceita o arquivo gravado com a compensacao")
    paginas_com = lay.numero_paginas()
    abrir(j, dados, ligado=False)
    sem = escrever(j._modelo_atual())
    checa_igual(fx.partes_de(com)["word/document.xml"], fx.partes_de(sem)["word/document.xml"],
                "o document.xml e' o mesmo com e sem a compensacao")
    checa_igual(fx.partes_de(com)["word/styles.xml"], fx.partes_de(sem)["word/styles.xml"],
                "e o styles.xml tambem")
    lay = abrir(j, com)
    checa_igual(lay.numero_paginas(), paginas_com, "o salvo reabre com as mesmas paginas")


def testar_desfazer_e_copiar(j) -> None:
    secao("um desfazer devolve tudo; o copiar leva os valores de verdade")
    dados = docx(p("S1", "Corpo") + p("S2", "Corpo") + p("S3", "Corpo"))
    lay = abrir(j, dados)
    doc = lay.doc
    antes = [(b.blockFormat(), b.text()) for b in _blocos(doc)]
    painel = j.painel
    cur = painel.textCursor()
    cur.setPosition(bloco_com(lay, "S2").position() + 2)
    painel.setTextCursor(cur)
    painel.setFocus()
    QTest.keyClick(painel, Qt.Key.Key_Return)
    drenar_eventos()
    painel.viewport().repaint()
    drenar_eventos()
    checa(len(list(_blocos(doc))) == 4, "o Enter partiu o paragrafo")
    novos = [b for b in _blocos(doc) if b.text().startswith("S2") or b.text().startswith(" 2")]
    checa(all(pq_estilos.props_de_bloco(b.blockFormat()).get("espaco_antes_tw") == 120
              for b in novos), "os dois pedacos continuam com 120 antes (o de verdade)")
    QTest.keyClick(painel, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    drenar_eventos()
    painel.viewport().repaint()
    drenar_eventos()
    depois = [(b.blockFormat(), b.text()) for b in _blocos(doc)]
    checa(depois == antes, "um Ctrl+Z devolve texto e formatos (com a compensacao de antes)")
    cur = QTextCursor(doc)
    cur.setPosition(bloco_com(lay, "S1").position())
    cur.setPosition(bloco_com(lay, "S3").position() + 2, QTextCursor.MoveMode.KeepAnchor)
    from editdoc.interface.painel_documento import _html_sem_espacador
    html = _html_sem_espacador(QTextDocumentFragment(cur))
    tmp = QTextDocument()
    tmp.setHtml(html)
    margens = [round(b.blockFormat().topMargin() * 15) for b in _blocos(tmp)]
    checa_igual(margens, [120, 120, 120], "colado em outro lugar: 120 antes em cada um (de verdade)")
    doc.setModified(False)


def _blocos(doc):
    b = doc.begin()
    while b.isValid():
        yield b
        b = b.next()


# -- oraculo sintetico ------------------------------------------------------------------------

def modelo_do_word(itens, hb: float, linha: float) -> list[tuple[int, int]]:
    """Onde o Word comeca cada pagina, por um modelo simples e independente do codigo: linhas de
    `linha` twips, espaco somado (sem o contextual), espaco antes no alto da pagina, orfas e
    viuvas que descem o paragrafo inteiro, keepNext. `itens`: (antes, depois, linhas, keepNext).
    Devolve (indice do paragrafo, linha) de cada pagina a partir da segunda."""
    inicios = []
    y = 0.0
    depois_ant = 0.0
    i = 0
    topo_pagina = True
    while i < len(itens):
        antes, depois, n, _kn = itens[i]
        gap = antes if topo_pagina else depois_ant + antes
        cabem = 0
        yy = y + gap
        while cabem < n and yy + linha <= hb + 0.5:
            yy += linha
            cabem += 1
        desce = cabem == 0 or (cabem < n and (cabem == 1 or (n - cabem == 1 and cabem == 2)))
        if not desce and cabem == n and itens[i][3] and i + 1 < len(itens):
            prox = itens[i + 1]
            if yy + depois + prox[0] + linha > hb + 0.5:
                desce = True
        if desce and not topo_pagina:
            inicios.append((i, 0))
            y, topo_pagina = 0.0, True
            continue
        if cabem < n:
            inicios.append((i, cabem))
            y = (n - cabem) * linha + 0.0
            topo_pagina = False
        else:
            y = yy
            topo_pagina = False
        depois_ant = depois
        i += 1
    return inicios


def testar_oraculo(j) -> None:
    secao("oraculo: lastRenderedPageBreak sintetico onde o Word quebraria")
    import random
    sorteio = random.Random(17)
    itens = []
    for k in range(140):
        n = sorteio.choice((1, 1, 2, 3, 4, 5))
        kn = n == 1 and sorteio.random() < 0.15
        antes = sorteio.choice((0, 0, 120, 240))
        depois = sorteio.choice((0, 120, 240))
        itens.append((antes, depois, n, kn))
    lay = abrir(j, docx(p("x")))
    hb = lay.hb
    inicios = modelo_do_word(itens, hb, LINHA_WORD_ARIAL_12)
    marcas = {}
    for numero, (i, linha) in enumerate(inicios):
        marcas[(i, linha)] = numero

    def paragrafo(i, item):
        antes, depois, n, kn = item
        ppr = (f'{"<w:keepNext/>" if kn else ""}'
               f'<w:spacing w:before="{antes}" w:after="{depois}"/>')
        partes = []
        for li in range(n):
            lrpb = '<w:lastRenderedPageBreak/>' if (i, li) in marcas else ""
            br = "<w:br/>" if li else ""
            partes.append(f"{br}{lrpb}<w:t>P{i:03d} linha {li + 1}</w:t>")
        return f'<w:p><w:pPr>{ppr}</w:pPr><w:r>{"".join(partes)}</w:r></w:p>'

    dados = docx("".join(paragrafo(i, it) for i, it in enumerate(itens)))
    checa(len(inicios) >= 8, f"o modelo do Word da' {len(inicios) + 1} paginas")
    acertos = {}
    for ligado in (True, False):
        lay = abrir(j, oraculo_com_marcadores(dados), ligado=ligado)
        acertos[ligado] = acerto_das_quebras(lay)
    checa_igual(acertos[True], (len(inicios), len(inicios)),
                f"o EditDoc acerta todas as {len(inicios)} quebras do oraculo (paragrafo e linha)")
    checa(acertos[False][1] < len(inicios),
          f"contraprova: sem a compensacao acerta {acertos[False][1]} de {len(inicios)}")
    lay.doc.setModified(False)


def oraculo_com_marcadores(dados: bytes) -> bytes:
    """Cada w:lastRenderedPageBreak vira um marcador _lrpbN (sem largura), partindo o run: e' o
    jeito de achar no QTextDocument onde o Word comecou cada pagina."""
    import copy

    from lxml import etree
    q = lambda t: "{%s}%s" % (W, t)  # noqa: E731
    partes = fx.partes_de(dados)
    raiz = etree.fromstring(partes["word/document.xml"])
    for n, el in enumerate(list(raiz.iter(q("lastRenderedPageBreak")))):
        run = el.getparent()
        filhos = list(run)
        depois = filhos[filhos.index(el) + 1:]
        rpr = run.find(q("rPr"))
        run.remove(el)
        pai = run.getparent()
        pos = list(pai).index(run)
        bs = etree.Element(q("bookmarkStart"))
        bs.set(q("id"), str(900 + n))
        bs.set(q("name"), f"_lrpb{n}")
        be = etree.Element(q("bookmarkEnd"))
        be.set(q("id"), str(900 + n))
        r2 = etree.Element(q("r"))
        if rpr is not None:
            r2.append(copy.deepcopy(rpr))
        for f in depois:
            r2.append(f)
        pai.insert(pos + 1, bs)
        pai.insert(pos + 2, be)
        pai.insert(pos + 3, r2)
    partes["word/document.xml"] = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8",
                                                 standalone=True)
    return fx.montar(partes)


def acerto_das_quebras(lay) -> tuple[int, int]:
    """(mesmo paragrafo, mesma linha): quantas paginas do EditDoc comecam onde o Word comecou."""
    doc = lay.doc
    marcas = sorted(((pos, int(m.nome[5:])) for pos, m in pq_marcas.posicoes_de_marcadores(doc)
                     if m.nome.startswith("_lrpb") and m.tipo == "inicio"), key=lambda x: x[1])
    n = doc.characterCount()

    def primeira_da_pagina(k):
        lo, hi = 0, n - 2
        if lay.pagina_do_cursor(hi) < k:
            return None
        while lo < hi:
            meio = (lo + hi) // 2
            if lay.pagina_do_cursor(meio) >= k:
                hi = meio
            else:
                lo = meio + 1
        return lo

    par = lin = 0
    for k, (pos, _i) in enumerate(marcas, start=1):
        alvo = min(pos + 2, n - 2)
        q = primeira_da_pagina(k)
        if q is None:
            continue
        b = doc.findBlock(alvo)
        if doc.findBlock(q).blockNumber() == b.blockNumber():
            par += 1
            l1 = b.layout().lineForTextPosition(alvo - b.position()).lineNumber()
            l2 = b.layout().lineForTextPosition(q - b.position()).lineNumber()
            lin += l1 == l2
    return par, lin


def testar_histerese(j, cap: int) -> None:
    """0.1.18: a quebra do motivo 3 so' sai com folga. Na faixa em que o paragrafo ainda cabe
    na pagina de cima, mas com pouca folga, a decisao de tirar a quebra (`_precisa` com margem)
    tem de ficar com a quebra; so' com folga de sobra ela sai. Contraprova: sem a folga
    (margem 0, a 0.1.17) a mesma faixa tira a quebra, e o teste acusa."""
    secao("histerese da quebra do motivo 3 (0.1.18): a faixa estreita fica como esta'")
    from editdoc.interface import paginacao as ip
    achados = {}
    for k in range(1, 8):
        corpo = fillers(cap - k) + p("P", ppr='<w:spacing w:before="480"/>') + fillers(30)
        lay = abrir(j, docx(corpo))
        P = bloco_com(lay, "P")
        cp = lay.paginacao
        u = cp._unidade_de(bloco=P)
        ant = cp._unidade_de(bloco=P.previous())
        if u.paginas != ant.paginas or u.paginas[0] != 0:
            continue
        sem = cp._precisa(u, ant, 0.0)
        com = cp._precisa(u, ant, ip.HISTERESE_TW)
        if not sem and com:
            achados.setdefault("estreita", (k, sem, com))
        if not sem and not com:
            achados.setdefault("folga", (k, sem, com))
    checa("estreita" in achados,
          "ha uma faixa em que o paragrafo cabe e a folga de 720 twips nao cabe")
    if "estreita" in achados:
        k, sem, com = achados["estreita"]
        checa(com is True,
              f"faixa estreita (k={k}): sem sobra suficiente o paragrafo continua empurrado")
        checa(sem is False,
              f"faixa estreita (k={k}): sem folga (0 twips) a quebra sai; so' a folga a segura")
    checa("folga" in achados,
          "com folga de sobra (k maior) a quebra sai, como antes")


# -- desempenho -------------------------------------------------------------------------------

def testar_custo_por_tecla(j) -> None:
    secao("custo por tecla da compensacao e das regras (documento de 600 paragrafos)")
    corpo = "".join(p(f"Paragrafo {i} com texto", "Corpo" if i % 3 else "Lista",
                      linhas=1 + i % 3) for i in range(600))
    lay = abrir(j, docx(corpo))
    doc = lay.doc
    meio = bloco_com(lay, "Paragrafo 300 ")
    tempos = []
    for i in range(40):
        c = QTextCursor(doc)
        c.setPosition(meio.position() + 3)
        c.insertText("x")
        t0 = time.perf_counter()
        lay.atualizar_secoes()
        tempos.append((time.perf_counter() - t0) * 1000)
    mediana = statistics.median(tempos)
    checa(mediana < 4.0, f"mediana {mediana:.2f} ms por tecla (teto 4 ms)")
    checa(lay.paginacao.conferidas <= 6,
          f"as regras conferiram {lay.paginacao.conferidas} paginas na ultima tecla (para cedo)")
    doc.setModified(False)


def main() -> int:
    if not carregar_fontes():
        return pular("sem Arial e Calibri em %WINDIR%\\Fonts")
    testar_regras_puras()
    testar_flags_dos_estilos()
    j = janela()
    try:
        testar_linha_da_fonte(j)
        testar_espaco_somado(j)
        cap = capacidade(j)
        checa(cap > 20, f"capacidade da pagina: {cap} linhas de Arial 12")
        testar_viuvas_e_orfas(j, cap)
        testar_manter_com_o_proximo(j, cap)
        testar_espaco_no_topo(j, cap)
        testar_tabela(j)
        testar_margem_da_celula(j)
        testar_imagem_na_linha(j)
        testar_marca_de_paragrafo(j)
        testar_gravacao(j)
        testar_desfazer_e_copiar(j)
        testar_oraculo(j)
        testar_histerese(j, cap)
        testar_custo_por_tecla(j)
    finally:
        j.painel.documento_corpo().setModified(False)
        j.close()
        drenar_eventos()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
