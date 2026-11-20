"""Corretor ortografico (0.1.35): idioma e w:noProof do arquivo, varredura incremental,
sublinhado so' na tela, menu de sugestoes, F7, opcoes e a API real do Windows.

Os testes NAO dependem do dicionario da maquina: o corretor e' o `CorretorFalso` (palavras dadas,
por idioma). So' a ultima secao fala com a API de verdade, e so' quando ela existe.
Cada verificacao importante tem uma contraprova (o sublinhado some com a verificacao desligada, o
idioma errado acusa, a varredura sem o cache verifica tudo de novo).
"""

from __future__ import annotations

import sys
import time

from ajudantes import (checa, checa_igual, drenar_eventos, pular, preparar_qt, resumir, secao,
                       usar_fonte_windows)

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QContextMenuEvent, QImage, QPainter, QTransform  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

import fixtures_docx as fx  # noqa: E402
from editdoc import configuracao  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.idioma_texto import idioma_do_run, idiomas_de_estilos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.interface import dialogos_modais, ortografia as ui_ort  # noqa: E402
from editdoc.interface.dialogo_opcoes import DialogoOpcoes  # noqa: E402
from editdoc.interface.faixa import BotaoAcao  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402
from editdoc.interface.painel_documento import PainelDocumento  # noqa: E402
from editdoc.interface.vista_paginas import desenhar_folha  # noqa: E402
from editdoc.ortografia import (Corretor, CorretorFalso, Erro, ErroDoCorretor,  # noqa: E402
                                normalizar_etiqueta)
from editdoc.ponte_qt import ortografia as pq_ort  # noqa: E402

Key = Qt.Key
PT = ("casa gato texto de com e um o a palavra palavras paragrafo segundo terceiro ola mundo "
      "teste testes no meio gatos").split()
EN = "house dog cat the of and text".split()


def falso(**kw) -> CorretorFalso:
    return CorretorFalso({"pt-BR": PT, "en-US": EN}, kw.pop("sugestoes", None) or
                         {"gatoo": ["gato"], "testee": ["teste", "testes"]}, **kw)


def varrer(ort) -> int:
    """A varredura inteira, fatia por fatia, sem esperar o timer. Devolve quantas fatias."""
    ort._timer.stop()
    fatias = 0
    while True:
        ort._fatia()
        fatias += 1
        ort._timer.stop()
        if ort._pos is None or fatias > 5000:
            return fatias


def painel_com(texto: str, corretor=None, largura: int = 900):
    painel = PainelDocumento("Segoe UI", 12)
    painel.resize(largura, 520)
    painel.show()
    drenar_eventos(2)
    painel.setPlainText(texto)
    painel.layout_pag.atualizar_secoes()
    painel.document().clearUndoRedoStacks()
    painel.document().setModified(False)
    painel.ortografia.definir_corretor(corretor if corretor is not None else falso())
    varrer(painel.ortografia)
    drenar_eventos(2)
    return painel


def fechar(painel) -> None:
    painel.documento_corpo().setModified(False)
    painel.close()
    drenar_eventos()


def vermelhos(imagem: QImage, x0: int, y0: int, x1: int, y1: int) -> int:
    n = 0
    for y in range(max(0, y0), min(imagem.height(), y1)):
        for x in range(max(0, x0), min(imagem.width(), x1)):
            c = imagem.pixelColor(x, y)
            # Vermelho, mesmo com a suavizacao da onda fina; o cinza do texto nunca passa.
            if c.red() - c.green() > 40 and c.red() - c.blue() > 40:
                n += 1
    return n


def faixa_da_palavra(painel, palavra: str) -> tuple[int, int, int, int]:
    """Retangulo (x0, y0, x1, y1) de tela da primeira ocorrencia da palavra."""
    texto = painel.documento_corpo().toPlainText()
    ini = texto.index(palavra)
    painel.garantir_visivel(painel.layout_pag.retangulo_cursor(ini))
    drenar_eventos(1)
    a, b = painel.layout_pag.retangulo_cursor(ini), painel.layout_pag.retangulo_cursor(ini + len(palavra))
    m, n = painel.mapa(), painel.total_de_paginas()
    xa, ya = m.doc_para_tela(a.x(), a.y(), n)
    xb, _yb = m.doc_para_tela(b.x(), b.y(), n)
    _x, yfim = m.doc_para_tela(a.x(), a.bottom(), n)
    return int(xa), int(ya), int(xb) + 1, int(yfim) + 2


def janela_com(docx: bytes, corretor=None, cfg=None):
    janela = JanelaPrincipal(cfg or configuracao.padrao())
    janela.resize(1300, 800)
    janela.show()
    drenar_eventos(2)
    modelo, avisos = ler(docx)
    janela.carregar(modelo, avisos, None)
    janela.painel.ortografia.definir_corretor(corretor if corretor is not None else falso())
    drenar_eventos(2)
    return janela


def fechar_janela(janela) -> None:
    janela.painel.documento_corpo().setModified(False)
    janela.close()
    drenar_eventos()


# -- sem Qt ------------------------------------------------------------------------------------

def testar_etiquetas_e_xml() -> None:
    secao("idioma: etiquetas, w:lang e w:noProof lidos do XML, sem Qt")
    for bruto, esperado in (("pt-br", "pt-BR"), ("PT_BR", "pt-BR"), ("en-US", "en-US"),
                            ("zh-hans-cn", "zh-Hans-CN"), ("es", "es"), ("x-none", None),
                            ("zxx", None), ("", None), (None, None), ("pt br", None),
                            ("a", None)):
        checa_igual(normalizar_etiqueta(bruto), esperado, f"etiqueta {bruto!r} -> {esperado!r}")
    r = ('<w:rPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
         '<w:noProof></w:noProof><w:lang w:val="en-us" w:eastAsia="ja-JP"></w:lang></w:rPr>')
    checa_igual(idioma_do_run(r), ("en-US", True), "run com lang en-us e noProof")
    desliga = r.replace("<w:noProof></w:noProof>", '<w:noProof w:val="0"></w:noProof>')
    checa_igual(idioma_do_run(desliga), ("en-US", False), "noProof val=0 e' falso (contraprova)")
    checa_igual(idioma_do_run(None), (None, None), "sem extras: nada")
    checa_igual(idioma_do_run("<<lixo"), (None, None), "extras ilegiveis: nada, sem erro")
    xml = (b'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           b'<w:docDefaults><w:rPrDefault><w:rPr><w:lang w:val="es-ES"/></w:rPr></w:rPrDefault>'
           b'</w:docDefaults>'
           b'<w:style w:type="paragraph" w:styleId="A"><w:name w:val="A"/>'
           b'<w:rPr><w:lang w:val="en-US"/></w:rPr></w:style>'
           b'<w:style w:type="paragraph" w:styleId="B"><w:name w:val="B"/><w:basedOn w:val="A"/>'
           b'</w:style>'
           b'<w:style w:type="character" w:styleId="C"><w:name w:val="C"/><w:rPr><w:noProof/>'
           b'<w:lang w:val="fr-FR"/></w:rPr></w:style></w:styles>')
    est = idiomas_de_estilos(xml)
    checa_igual(est.padrao, "es-ES", "docDefaults: es-ES")
    checa_igual(est.do_texto("A", None), ("en-US", None), "estilo A: en-US")
    checa_igual(est.do_texto("B", None), ("en-US", None), "estilo B herda de A por basedOn")
    checa_igual(est.do_texto("B", "C"), ("fr-FR", True), "o estilo de caractere vence o do paragrafo")
    checa_igual(est.do_texto("Z", None), (None, None), "estilo desconhecido: nada")
    checa_igual(idiomas_de_estilos(b"<<").padrao, None, "styles.xml ilegivel: sem idioma, sem erro")
    checa_igual(idiomas_de_estilos(None).estilos, {}, "sem styles.xml: vazio")
    ciclo = (b'<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
             b'<w:style w:type="paragraph" w:styleId="X"><w:name w:val="X"/><w:basedOn w:val="Y"/>'
             b'</w:style><w:style w:type="paragraph" w:styleId="Y"><w:name w:val="Y"/>'
             b'<w:basedOn w:val="X"/></w:style></w:styles>')
    checa_igual(idiomas_de_estilos(ciclo).do_texto("X", None), (None, None),
                "ciclo de basedOn nao trava")


def testar_corretor_falso() -> None:
    secao("corretor falso: a interface que a janela usa")
    c = falso(repetidas=True)
    checa(isinstance(c, Corretor), "o falso e' um Corretor")
    erros = c.verificar("casa casa gatoo", "pt-BR")
    checa_igual([(e.ini, e.fim, e.acao) for e in erros], [(5, 9, "excluir"), (10, 15, "sugerir")],
                "repetida e desconhecida")
    checa_igual(c.verificar("house gato", "en-US")[0].ini, 6, "'gato' nao e' ingles (por idioma)")
    checa(c.suporta("pt-BR") and not c.suporta("fr-FR"), "suporta so' os idiomas dados")
    c.adicionar("gatoo", "pt-BR")
    checa_igual(c.verificar("gatoo", "pt-BR"), [], "adicionada ao dicionario: deixa de errar")
    c.quebra = True
    try:
        c.verificar("x", "pt-BR")
        checa(False, "o falso quebrado levanta ErroDoCorretor")
    except ErroDoCorretor:
        checa(True, "o falso quebrado levanta ErroDoCorretor")


# -- configuracao e opcoes ---------------------------------------------------------------------

def testar_configuracao() -> None:
    secao("preferencias: ligar e o idioma, validados")
    padrao = configuracao.padrao()
    checa_igual((padrao["ortografia_ligada"], padrao["ortografia_idioma"]), (True, "auto"),
                "padrao: ligada, idioma automatico")
    v = configuracao.validar({"ortografia_ligada": False, "ortografia_idioma": "en-US"})
    checa_igual((v["ortografia_ligada"], v["ortografia_idioma"]), (False, "en-US"),
                "valores validos sao aceitos")
    for ruim in ("xx yy", "en-us", "", 5, "a", "zxx"):
        checa_igual(configuracao.validar({"ortografia_idioma": ruim})["ortografia_idioma"], "auto",
                    f"idioma {ruim!r} invalido volta ao automatico")
    checa_igual(configuracao.validar({"ortografia_ligada": "sim"})["ortografia_ligada"], True,
                "ligada que nao e' bool volta ao padrao")


def testar_dialogo() -> None:
    secao("Arquivo > Opcoes: caixa de ortografia e idioma")
    d = DialogoOpcoes(configuracao.padrao(), None, ["pt-BR", "en-US"])
    checa(d.ortografia.isChecked() and d.idioma.currentData() == "auto",
          "abre ligada, no automatico")
    dados = [d.idioma.itemData(i) for i in range(d.idioma.count())]
    checa_igual(dados, ["auto", "pt-BR", "en-US"], "automatico e os idiomas do corretor")
    checa("Português" in d.idioma.itemText(1), "o nome do idioma vem do Qt: " + d.idioma.itemText(1))
    d.idioma.setCurrentIndex(2)
    d.ortografia.setChecked(False)
    v = d.valores()
    checa_igual((v["ortografia_ligada"], v["ortografia_idioma"]), (False, "en-US"),
                "valores() devolve a escolha")
    checa(not d.idioma.isEnabled(), "desligada, o combo do idioma fica desabilitado")
    d2 = DialogoOpcoes({**configuracao.padrao(), "ortografia_idioma": "fr-FR"}, None, ["pt-BR"])
    checa("não instalado" in d2.idioma.currentText() and d2.valores()["ortografia_idioma"] == "fr-FR",
          "idioma gravado e nao instalado continua escolhido (o OK nao o troca em silencio)")
    d3 = DialogoOpcoes(configuracao.padrao(), None, [])
    checa_igual(d3.idioma.count(), 1, "sem corretor: so' o automatico")
    checa(bool(d.idioma.accessibleName()) and bool(d.ortografia.text()),
          "os controles novos tem nome para o leitor de tela")


def testar_opcoes_na_janela() -> None:
    secao("Arquivo > Opcoes na janela: ligar, desligar e o idioma valem na hora")
    configuracao.caminho().unlink(missing_ok=True)
    janela = janela_com(fx.docx_com_xml("<w:p><w:r><w:t>gatoo</w:t></w:r></w:p>"))
    ort = janela.painel.ortografia
    varrer(ort)
    checa(ort.pintando(), "com o corretor ligado a janela sublinha")
    original = dialogos_modais.pedir_opcoes
    try:
        dialogos_modais.pedir_opcoes = lambda pai, valores, idiomas=(): {
            **valores, "ortografia_ligada": False, "ortografia_idioma": "en-US",
            "limpar_recentes": False}
        checa(janela.opcoes(), "o dialogo aceito grava")
        checa(not ort.ligada and ort.idioma == "en-US", "a janela aplicou: desligada, en-US")
        checa(not ort.pintando(), "desligada: nada e' pintado")
        checa_igual(configuracao.carregar()["ortografia_idioma"], "en-US", "gravado no config")
        dialogos_modais.pedir_opcoes = lambda pai, valores, idiomas=(): {
            **valores, "ortografia_ligada": True, "ortografia_idioma": "auto",
            "limpar_recentes": False}
        janela.opcoes()
        checa(ort.ligada and ort.idioma == "auto", "religada, no automatico")
        varrer(ort)
        checa(ort.pintando(), "religada: volta a sublinhar")
    finally:
        dialogos_modais.pedir_opcoes = original
        configuracao.caminho().unlink(missing_ok=True)
    fechar_janela(janela)


# -- o idioma e o w:noProof do arquivo ---------------------------------------------------------

CORPO = (
    '<w:p><w:r><w:t>casa gatoo</w:t></w:r></w:p>'
    '<w:p><w:r><w:t xml:space="preserve">cat </w:t></w:r><w:r><w:rPr><w:lang w:val="en-US"/></w:rPr>'
    '<w:t>house dogg</w:t></w:r></w:p>'
    '<w:p><w:r><w:rPr><w:noProof/></w:rPr><w:t>xyzzy</w:t></w:r><w:r><w:t xml:space="preserve"> qwerty</w:t>'
    '</w:r></w:p>'
    '<w:p><w:r><w:rPr><w:rStyle w:val="Ingles"/></w:rPr><w:t>house</w:t></w:r><w:r><w:t xml:space="preserve"> '
    'house</w:t></w:r></w:p>'
    '<w:p><w:r><w:t>pala</w:t></w:r><w:bookmarkStart w:id="9" w:name="mk"/><w:bookmarkEnd w:id="9"/>'
    '<w:r><w:t>vra</w:t></w:r></w:p>'
    '<w:p><w:r><w:t xml:space="preserve">texto </w:t></w:r><w:del w:id="1" w:author="a" '
    'w:date="2020-01-01T00:00:00Z"><w:r><w:delText>deletadoo</w:delText></w:r></w:del></w:p>'
    '<w:p><w:proofErr w:type="spellStart"/><w:r><w:t>ola</w:t></w:r><w:proofErr w:type="spellEnd"/></w:p>'
)


def docx_de_idiomas(padrao: str = "pt-BR") -> bytes:
    base = fx.docx_com_xml(CORPO)
    partes = fx.partes_de(base)
    est = partes["word/styles.xml"].decode("utf-8")
    est = est.replace('w:val="pt-BR" w:eastAsia', f'w:val="{padrao}" w:eastAsia', 1)
    est = est.replace("</w:styles>",
                      '<w:style w:type="character" w:customStyle="1" w:styleId="Ingles">'
                      '<w:name w:val="Ingles"/><w:rPr><w:lang w:val="en-US"/></w:rPr></w:style>'
                      '</w:styles>')
    return fx.com_parte(base, "word/styles.xml", est.encode("utf-8"))


def palavras_erradas(ort) -> dict:
    """{texto do bloco: [palavra errada, ...]} de tudo o que a janela sublinharia."""
    doc = ort.painel.documento_corpo()
    saida = {}
    b = doc.begin()
    while b.isValid():
        texto = b.text()
        erros = ort._erros_conhecidos(texto)
        if erros:
            saida[texto] = [texto[e.ini:e.fim] for e in erros]
        b = b.next()
    return saida


def testar_idioma_do_arquivo() -> None:
    secao("w:lang por trecho, w:noProof, estilo, marca no meio da palavra e texto excluido")
    janela = janela_com(docx_de_idiomas())
    ort = janela.painel.ortografia
    checa_igual(ort._padrao, "pt-BR", "idioma do documento: o do docDefaults")
    varrer(ort)
    erradas = palavras_erradas(ort)
    por_linha = {t.replace("￼", ""): v for t, v in erradas.items()}
    checa_igual(por_linha.get("casa gatoo"), ["gatoo"], "texto no idioma do documento")
    checa_igual(por_linha.get("cat house dogg"), ["cat", "dogg"],
                "o trecho en-US usa o dicionario ingles: 'house' passa, 'cat' (pt) e 'dogg' erram")
    checa_igual(por_linha.get("xyzzy qwerty"), ["qwerty"], "w:noProof: 'xyzzy' nao e' verificado")
    checa_igual(por_linha.get("house house"), ["house"],
                "estilo de caractere en-US: o 'house' do estilo passa; o outro 'house' e' pt e erra")
    checa(not any("pala" in v or "vra" in v for vs in erradas.values() for v in vs),
          "marcador no meio de 'palavra' nao parte a palavra")
    checa(not any("deletadoo" in v for vs in erradas.values() for v in vs),
          "texto excluido por alteracao controlada nao e' verificado")
    checa(not any(t.startswith("ola") for t in erradas), "o w:proofErr do arquivo nao atrapalha")
    # contraprova do w:noProof: sem ele o mesmo texto erra
    janela2 = janela_com(fx.docx_com_xml('<w:p><w:r><w:t>xyzzy qwerty</w:t></w:r></w:p>'))
    varrer(janela2.painel.ortografia)
    checa_igual(list(palavras_erradas(janela2.painel.ortografia).values()), [["xyzzy", "qwerty"]],
                "contraprova: sem w:noProof as duas erram")
    fechar_janela(janela2)

    # idioma do documento en-US: o texto sem w:lang e' ingles
    ingles = janela_com(docx_de_idiomas("en-US"))
    ort2 = ingles.painel.ortografia
    checa_igual(ort2._padrao, "en-US", "docDefaults en-US vira o idioma do documento")
    varrer(ort2)
    por2 = {t.replace("￼", ""): v for t, v in palavras_erradas(ort2).items()}
    checa("casa" in por2["casa gatoo"] and "gatoo" in por2["casa gatoo"],
          "em documento en-US o texto sem w:lang e' verificado em ingles")
    # idioma escolhido nas opcoes vale para todo o texto
    ort2.aplicar_preferencias({"ortografia_ligada": True, "ortografia_idioma": "pt-BR"})
    varrer(ort2)
    por3 = {t.replace("￼", ""): v for t, v in palavras_erradas(ort2).items()}
    checa_igual(por3.get("casa gatoo"), ["gatoo"], "pt-BR escolhido: tudo em portugues")
    checa("house" in por3["cat house dogg"] and "dogg" in por3["cat house dogg"],
          "o idioma escolhido vence o w:lang do trecho: 'house' erra em pt-BR")
    fechar_janela(ingles)
    fechar_janela(janela)


def testar_trechos_e_mapa() -> None:
    secao("trechos do bloco: mapa de posicoes e limites")
    janela = janela_com(docx_de_idiomas())
    ort = janela.painel.ortografia
    doc = janela.painel.documento_corpo()
    bloco = doc.findBlockByNumber(4)
    trechos = pq_ort.trechos_do_bloco(bloco, ort._contexto())
    checa_igual([t.texto for t in trechos], ["palavra"], "as duas metades formam uma palavra so'")
    t = trechos[0]
    ini, fim = t.intervalo_no_bloco(0, 7)
    checa_igual(bloco.text()[ini:fim].replace("￼", ""), "palavra",
                "o intervalo volta ao bloco, com as marcas dentro")
    checa(t.mapa is not None and fim - ini == 9, "mapa nao contiguo: 7 letras e 2 marcas")
    bloco2 = doc.findBlockByNumber(1)
    tr2 = pq_ort.trechos_do_bloco(bloco2, ort._contexto())
    checa_igual([(x.texto, x.idioma) for x in tr2], [("cat ", "pt-BR"), ("house dogg", "en-US")],
                "dois trechos, cada um com o idioma dele")
    forcado = pq_ort.Contexto("en-US", "pt-BR", ort._estilos)
    checa_igual({x.idioma for x in pq_ort.trechos_do_bloco(bloco2, forcado)}, {"en-US"},
                "idioma forcado vale para todos os trechos")
    fechar_janela(janela)


# -- a tela ------------------------------------------------------------------------------------

def testar_sublinhado() -> None:
    secao("sublinhado ondulado: so' na tela, no lugar certo, com contraprovas")
    usar_fonte_windows()
    painel = painel_com("Este e um testee de ortografia\ncasa gato texto")
    ort = painel.ortografia
    imagem = painel.viewport().grab().toImage()
    x0, y0, x1, y1 = faixa_da_palavra(painel, "testee")
    errada = vermelhos(imagem, x0, y0, x1, y1)
    x0, y0, x1, y1 = faixa_da_palavra(painel, "casa")
    certa = vermelhos(imagem, x0, y0, x1, y1)
    checa(errada >= 8, f"a palavra errada tem o sublinhado vermelho ({errada} pixels)")
    checa_igual(certa, 0, "a palavra certa fica sem sublinhado")
    # nao passa para o documento: texto, desfazer e "alterado" intactos
    doc = painel.documento_corpo()
    checa(not doc.isModified() and not doc.isUndoAvailable(),
          "o sublinhado nao suja o documento nem entra no desfazer")
    # fora da tela (impressao e PDF): nada
    cfg = painel.layout_pag.efetiva_da(0)
    e = 0.06
    saida = {}
    for tela in (True, False):
        img = QImage(int(cfg.largura_tw * e) + 1, int(cfg.altura_tw * e) + 1,
                     QImage.Format.Format_RGB32)
        img.fill(0xFFFFFFFF)
        pintor = QPainter(img)
        desenhar_folha(pintor, painel.layout_pag, 0, QTransform().scale(e, e), tela=tela)
        pintor.end()
        saida[tela] = vermelhos(img, 0, 0, img.width(), img.height())
    checa(saida[True] > 0, "na tela (tela=True) a pagina tem sublinhado")
    checa_igual(saida[False], 0, "na impressao e no PDF (tela=False) nao ha' sublinhado")
    # contraprova: desligada, nada
    ort.aplicar_preferencias({"ortografia_ligada": False})
    drenar_eventos(2)
    img = painel.viewport().grab().toImage()
    x0, y0, x1, y1 = faixa_da_palavra(painel, "testee")
    checa_igual(vermelhos(img, x0, y0, x1, y1), 0, "contraprova: verificacao desligada, sem sublinhado")
    ort.aplicar_preferencias({"ortografia_ligada": True})
    varrer(ort)
    drenar_eventos(2)
    img = painel.viewport().grab().toImage()
    x0, y0, x1, y1 = faixa_da_palavra(painel, "testee")
    checa(vermelhos(img, x0, y0, x1, y1) >= 8, "religada, o sublinhado volta")
    fechar(painel)


def testar_colunas() -> None:
    secao("com colunas o sublinhado aparece na coluna certa")
    usar_fonte_windows()
    corpo = "".join(f"<w:p><w:r><w:t>casa gato texto {i}</w:t></w:r></w:p>" for i in range(60))
    corpo += "<w:p><w:r><w:t>gatoo no fim</w:t></w:r></w:p>"
    base = fx.docx_com_xml(corpo)
    partes = fx.partes_de(base)
    xml = partes["word/document.xml"].decode("utf-8")
    fim = xml.rindex("</w:sectPr>")
    partes["word/document.xml"] = (xml[:fim] + '<w:cols w:num="2" w:space="720"/>'
                                   + xml[fim:]).encode("utf-8")
    janela = janela_com(fx.montar(partes))
    janela.resize(1300, 900)
    drenar_eventos(2)
    painel, ort = janela.painel, janela.painel.ortografia
    checa(painel.layout_pag.mapa.tem_colunas(), "o documento tem colunas")
    varrer(ort)
    drenar_eventos(2)
    img = painel.viewport().grab().toImage()
    x0, y0, x1, y1 = faixa_da_palavra(painel, "gatoo")
    img = painel.viewport().grab().toImage()
    checa(vermelhos(img, x0, y0, x1, y1) >= 6, "a palavra errada tem o sublinhado na coluna")
    x0, y0, x1, y1 = faixa_da_palavra(painel, "casa gato texto 5")
    checa_igual(vermelhos(img, x0, y0, x1, y1), 0, "contraprova: o texto certo da outra coluna fica limpo")
    fechar_janela(janela)


def testar_zoom_e_pagina() -> None:
    secao("sublinhado acompanha o zoom")
    usar_fonte_windows()
    painel = painel_com("testee de ortografia")
    for z in (0.5, 2.0):
        painel.definir_zoom(z)
        drenar_eventos(2)
        img = painel.viewport().grab().toImage()
        x0, y0, x1, y1 = faixa_da_palavra(painel, "testee")
        checa(vermelhos(img, x0, y0, x1, y1) >= 4, f"zoom {z}: o sublinhado esta' sobre a palavra")
        x0, y0, x1, y1 = faixa_da_palavra(painel, "de")
        checa_igual(vermelhos(img, x0, y0, x1, y1), 0, f"zoom {z}: a palavra certa continua limpa")
    fechar(painel)


# -- varredura incremental ---------------------------------------------------------------------

def testar_incremental() -> None:
    secao("varredura incremental: so' o bloco mudado, fora do caminho da tecla")
    texto = "\n".join([f"casa gato texto {i}" for i in range(6)] + ["gatoo no meio"]
                      + [f"casa gato texto {i}" for i in range(6, 11)])
    painel = painel_com(texto)
    ort = painel.ortografia
    c = ort.corretor
    antes = len(c.verificados)
    # a pintura nao verifica
    painel.viewport().grab()
    painel.viewport().grab()
    checa_igual(len(c.verificados), antes, "pintar nao chama o corretor")
    # varrer de novo: tudo tem resultado
    varrer(ort)
    checa_igual(len(c.verificados), antes, "uma segunda varredura nao refaz nada (cache por texto)")
    # a tecla: so' anota e agenda; nada e' verificado na hora
    cursor = painel.textCursor()
    cursor.setPosition(2)
    painel.setTextCursor(cursor)
    QTest.keyClick(painel, Key.Key_X)
    checa_igual(len(c.verificados), antes, "a tecla nao chama o corretor")
    checa(ort._timer.isActive(), "a tecla so' reinicia o timer ocioso")
    ort._timer.stop()
    varrer(ort)
    novos = c.verificados[antes:]
    checa_igual(len(novos), 1, "depois da pausa, so' o bloco digitado e' verificado")
    checa(novos[0][0].startswith("caxsa") or "x" in novos[0][0], "e' o bloco que mudou: " + novos[0][0])
    # contraprova: sem o cache, tudo e' verificado de novo
    ort._por_bloco.clear()
    antes2 = len(c.verificados)
    varrer(ort)
    checa(len(c.verificados) - antes2 >= 10, "contraprova: sem o cache, todos os blocos de novo")
    # nada disso mexeu no documento
    checa(painel.documento_corpo().isModified(), "(a tecla alterou o texto, como esperado)")
    fechar(painel)


def testar_tile_em_cache() -> None:
    secao("o sublinhado do bloco mudado se atualiza no tile guardado, sem refazer a tela toda")
    usar_fonte_windows()
    painel = painel_com("casa gato\ncasa texto")
    ort = painel.ortografia
    painel.viewport().grab()
    guardados = len(painel._cache)
    checa(guardados >= 1, "ha' tiles no cache de pintura")
    cursor = painel.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    painel.setTextCursor(cursor)
    painel.insertPlainText("o")  # "casa textoo"
    QTest.keyClick(painel, Key.Key_Home)
    ort._timer.stop()
    img = painel.viewport().grab().toImage()
    x0, y0, x1, y1 = faixa_da_palavra(painel, "textoo")
    checa_igual(vermelhos(img, x0, y0, x1, y1), 0,
                "antes da verificacao (sem resultado do bloco novo) a palavra nova nao e' sublinhada")
    varrer(ort)
    img = painel.viewport().grab().toImage()
    x0, y0, x1, y1 = faixa_da_palavra(painel, "textoo")
    checa(vermelhos(img, x0, y0, x1, y1) >= 6, "depois da verificacao o sublinhado aparece")
    checa_igual(len(painel._cache), guardados, "sem tirar os tiles do cache (so' a parte velha)")
    fechar(painel)


def testar_fatias() -> None:
    secao("a varredura anda em fatias curtas, o resto do programa nao para")

    class Lento(CorretorFalso):
        def verificar(self, texto, idioma):
            time.sleep(0.002)
            return super().verificar(texto, idioma)

    texto = "\n".join(f"paragrafo {i} casa gato" for i in range(400))
    painel = PainelDocumento("Segoe UI", 12)
    painel.resize(900, 520)
    painel.show()
    painel.setPlainText(texto)
    drenar_eventos(2)
    ort = painel.ortografia
    ort.definir_corretor(Lento({"pt-BR": PT}))
    ort._timer.stop()
    longas = []
    fatias = 0
    while True:
        t0 = time.perf_counter()
        ort._fatia()
        ort._timer.stop()
        longas.append(time.perf_counter() - t0)
        fatias += 1
        if ort._pos is None or fatias > 2000:
            break
    checa(fatias > 20, f"400 blocos lentos viram muitas fatias ({fatias})")
    checa(max(longas) < 0.06, f"nenhuma fatia passa de 60 ms (maior: {max(longas) * 1000:.1f} ms)")
    checa_igual(len(ort._por_bloco), 400, "a varredura terminou: todos os blocos verificados")
    # a primeira fatia cobre o que esta' na tela
    painel2 = PainelDocumento("Segoe UI", 12)
    painel2.resize(900, 520)
    painel2.show()
    painel2.setPlainText(texto)
    drenar_eventos(2)
    ort2 = painel2.ortografia
    ort2.definir_corretor(Lento({"pt-BR": PT}))
    ort2._timer.stop()
    ort2._fatia()
    ort2._timer.stop()
    primeiros = sum(1 for t in ort2._por_bloco if t.startswith("paragrafo "))
    checa(0 < primeiros < 400, f"uma fatia verifica so' parte ({primeiros} blocos)")
    fechar(painel)
    fechar(painel2)


def testar_palavra_em_digitacao() -> None:
    secao("a palavra que se esta' digitando nao e' sublinhada ate' o caret sair")
    usar_fonte_windows()
    painel = painel_com("casa testee")
    ort = painel.ortografia
    doc = painel.documento_corpo()
    bloco = doc.begin()
    checa_igual(ort.erros_a_pintar(bloco), [(5, 11)], "sem digitar, a palavra errada e' sublinhada")
    cursor = painel.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    painel.setTextCursor(cursor)
    QTest.keyClick(painel, Key.Key_X)
    QTest.keyClick(painel, Key.Key_Backspace)
    ort._timer.stop()
    checa_igual(doc.toPlainText(), "casa testee", "o texto voltou ao de antes")
    checa_igual(ort.erros_a_pintar(doc.begin()), [], "com o caret na palavra recem-digitada: sem sublinhado")
    QTest.keyClick(painel, Key.Key_Home)
    checa_igual(ort.erros_a_pintar(doc.begin()), [(5, 11)],
                "o caret saiu da palavra: o sublinhado aparece")
    fechar(painel)


def testar_bloco_digitado_mantem_as_outras() -> None:
    secao("digitar num bloco nao apaga o sublinhado das outras palavras dele")
    painel = painel_com("gatoo e testee")
    ort = painel.ortografia
    cursor = painel.textCursor()
    cursor.setPosition(0)
    painel.setTextCursor(cursor)
    QTest.keyClick(painel, Key.Key_Q)
    ort._timer.stop()
    texto = painel.documento_corpo().begin().text()
    checa(texto not in ort._por_bloco, "o bloco digitado ainda nao tem resultado novo")
    erros = [(texto[a:b]) for a, b in ort.erros_a_pintar(painel.documento_corpo().begin())]
    checa("testee" in erros, "mas a palavra errada que nao mudou continua sublinhada: " + str(erros))
    fechar(painel)


# -- menu, ignorar, adicionar, F7 --------------------------------------------------------------

def textos_do_menu(menu) -> list[str]:
    return [a.text() if not a.isSeparator() else "|" for a in menu.actions()]


def testar_menu() -> None:
    secao("menu da palavra errada: sugestoes, Ignorar, Ignorar tudo, Adicionar ao dicionario")
    painel = painel_com("casa testee gato testee")
    ort = painel.ortografia
    pos = painel.documento_corpo().toPlainText().index("testee") + 2
    menu = QMenu()
    checa(ort.montar_menu(menu, pos), "palavra errada: o menu ganha itens")
    checa_igual(textos_do_menu(menu), ["teste", "testes", "|", "Ignorar", "Ignorar tudo",
                                       "Adicionar ao dicionário", "|"],
                "sugestoes (a melhor primeiro), Ignorar, Ignorar tudo e Adicionar")
    checa(menu.actions()[0].font().bold(), "a sugestao vem em negrito")
    menu2 = QMenu()
    checa(not ort.montar_menu(menu2, 1) and not menu2.actions(),
          "contraprova: palavra certa, menu intocado")
    # sem sugestao
    sem = painel_com("zzzzz", falso(sugestoes={"outra": ["x"]}))
    menu3 = QMenu()
    sem.ortografia.montar_menu(menu3, 2)
    checa(textos_do_menu(menu3)[0] == "(sem sugestões)" and not menu3.actions()[0].isEnabled(),
          "sem sugestao: item desabilitado")
    fechar(sem)
    # trocar: um passo de desfazer
    doc = painel.documento_corpo()
    menu.actions()[0].trigger()
    checa_igual(doc.toPlainText(), "casa teste gato testee", "a sugestao troca a palavra")
    painel.undo()
    checa_igual(doc.toPlainText(), "casa testee gato testee", "um Ctrl+Z desfaz a troca inteira")
    fechar(painel)


def testar_contexto_do_mouse() -> None:
    secao("botao direito do mouse na palavra errada abre o menu com as sugestoes")
    usar_fonte_windows()
    painel = painel_com("casa testee gato")
    capturados = []

    def captura(menu, ponto):
        capturados.append(textos_do_menu(menu))
        return None
    painel.exibir_menu = captura
    x0, y0, x1, y1 = faixa_da_palavra(painel, "testee")
    ponto = QPoint((x0 + x1) // 2, (y0 + y1) // 2 - 2)
    painel.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, ponto,
                                              painel.viewport().mapToGlobal(ponto)))
    x0, y0, x1, y1 = faixa_da_palavra(painel, "gato")
    ponto2 = QPoint((x0 + x1) // 2, (y0 + y1) // 2 - 2)
    painel.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, ponto2,
                                              painel.viewport().mapToGlobal(ponto2)))
    checa(capturados[0][:2] == ["teste", "testes"] and "Ignorar tudo" in capturados[0]
          and "Desfazer" in capturados[0], "na palavra errada: sugestoes no alto e o menu de sempre")
    checa(capturados[1][0] == "Desfazer", "contraprova: na palavra certa, o menu de sempre")
    fechar(painel)


def testar_ignorar() -> None:
    secao("Ignorar (uma vez), Ignorar tudo e Adicionar ao dicionario")
    painel = painel_com("testee casa testee\ngato testee")
    ort = painel.ortografia
    doc = painel.documento_corpo()
    texto = doc.toPlainText()
    primeiro = texto.index("testee")
    menu = QMenu()
    ort.montar_menu(menu, primeiro + 1)
    [a for a in menu.actions() if a.text() == "Ignorar"][0].trigger()
    b0 = doc.begin()
    checa_igual(ort.erros_a_pintar(b0), [(12, 18)],
                "Ignorar: so' esta ocorrencia some; a outra do mesmo bloco continua")
    checa(not doc.isModified() and not doc.isUndoAvailable(), "Ignorar nao entra no desfazer")
    # o bloco, se mudar, recomeca
    ort._por_bloco.clear()
    varrer(ort)
    checa_igual(ort.erros_a_pintar(b0), [(12, 18)], "Ignorar uma vez resiste a nova verificacao")
    menu = QMenu()
    ort.montar_menu(menu, texto.index("testee", 12) + 1)
    [a for a in menu.actions() if a.text() == "Ignorar tudo"][0].trigger()
    checa(all(not ort.erros_a_pintar(b) for b in (doc.begin(), doc.begin().next())),
          "Ignorar tudo: some em todo o documento")
    ort._por_bloco.clear()
    varrer(ort)
    checa(not ort.pintando() or not any(ort.erros_a_pintar(b) for b in (doc.begin(), doc.begin().next())),
          "e continua ignorada depois de verificar de novo")
    # adicionar
    painel2 = painel_com("gatoo casa")
    o2 = painel2.ortografia
    menu = QMenu()
    o2.montar_menu(menu, 1)
    [a for a in menu.actions() if a.text() == "Adicionar ao dicionário"][0].trigger()
    checa_igual(o2.corretor.adicionadas, [("gatoo", "pt-BR")], "a palavra foi ao dicionario do corretor")
    checa(not o2.erros_a_pintar(painel2.documento_corpo().begin()), "e deixou de errar")
    o2._por_bloco.clear()
    varrer(o2)
    checa(not o2.erros_a_pintar(painel2.documento_corpo().begin()), "(verificando de novo tambem)")
    fechar(painel)
    fechar(painel2)


def testar_repetida() -> None:
    secao("palavra repetida: Excluir tira a palavra e o espaco")
    painel = painel_com("casa casa gato", falso(repetidas=True))
    ort = painel.ortografia
    menu = QMenu()
    checa(ort.montar_menu(menu, 6), "a segunda 'casa' e' erro")
    checa(menu.actions()[0].text().startswith("Excluir a palavra repetida"), "oferece Excluir")
    menu.actions()[0].trigger()
    checa_igual(painel.documento_corpo().toPlainText(), "casa gato", "saiu a palavra e o espaco")
    painel.undo()
    checa_igual(painel.documento_corpo().toPlainText(), "casa casa gato", "um Ctrl+Z devolve")
    fechar(painel)


def testar_f7() -> None:
    secao("F7 e o botao Ortografia: percorrem os erros com o menu")
    janela = janela_com(fx.docx_com_xml(
        '<w:p><w:r><w:t>casa gatoo gato</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>texto</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>testee de qwerty</w:t></w:r></w:p>'))
    painel, ort = janela.painel, janela.painel.ortografia
    checa_igual(ort.proximo_erro(0), (5, 10), "o primeiro erro depois do inicio")
    doc = painel.documento_corpo()
    texto = doc.toPlainText()
    achado = ort.proximo_erro(10)
    checa_igual(texto[achado[0]:achado[1]], "testee", "depois do primeiro, o do outro paragrafo")
    ultimo = texto.index("qwerty")
    volta = ort.proximo_erro(ultimo + 6)
    checa_igual(volta, (5, 10), "depois do ultimo, volta ao primeiro (dando a volta)")
    # contraprova: sem erros, None
    limpo = janela_com(fx.docx_com_xml('<w:p><w:r><w:t>casa gato</w:t></w:r></w:p>'))
    checa(limpo.painel.ortografia.proximo_erro(0) is None, "contraprova: sem erro, nenhum achado")
    fechar_janela(limpo)
    # com "verificar enquanto digito" desligado o F7 continua valendo (como no Word), mas nada
    # fica sublinhado nem aparece no menu de contexto
    ort.aplicar_preferencias({"ortografia_ligada": False})
    checa(not ort.pintando(), "desligada: nada e' sublinhado")
    menu_off = QMenu()
    checa(not ort.montar_menu(menu_off, 7) and not menu_off.actions(),
          "desligada: o botao direito nao oferece correcao (nada esta' marcado)")
    checa_igual(ort.proximo_erro(0), (5, 10), "desligada: o F7 ainda acha o proximo erro")
    ort.aplicar_preferencias({"ortografia_ligada": True})
    # a tecla
    escolhas = []

    def escolher(menu, ponto):
        escolhas.append((textos_do_menu(menu)[:1], painel.textCursor().selectedText()))
        # a primeira acao: a sugestao, ou o "(sem sugestoes)" desabilitado -> Ignorar
        for a in menu.actions():
            if a.isEnabled() and not a.isSeparator():
                a.trigger()
                return a
        return None
    ort.escolher = escolher
    cursor = painel.textCursor()
    cursor.setPosition(0)
    painel.setTextCursor(cursor)
    painel.setFocus()
    QTest.keyClick(painel, Key.Key_F7)
    checa_igual([e[1] for e in escolhas], ["gatoo", "testee", "qwerty"],
                "F7 percorreu os tres erros, um menu para cada")
    textos = doc.toPlainText().split("\n")
    checa_igual(textos[0], "casa gato gato", "a primeira sugestao foi aplicada (gatoo -> gato)")
    checa_igual(textos[2], "teste de qwerty", "e a segunda (testee -> teste); qwerty foi ignorada")
    # Esc (menu fechado) encerra
    ort.escolher = lambda menu, ponto: None
    ort._uma_vez.clear()
    ort._por_bloco.clear()
    varrer(ort)
    mensagens = []
    painel.mensagem.connect(mensagens.append)
    n = ort.percorrer()
    checa_igual(n, 0, "menu fechado: encerra no primeiro erro")
    ort.aplicar_preferencias({"ortografia_ligada": False})
    ort.escolher = lambda menu, ponto: (menu.actions()[0].trigger() or menu.actions()[0])
    cursor = painel.textCursor()
    cursor.setPosition(0)
    painel.setTextCursor(cursor)
    n_off = ort.percorrer()
    checa(n_off >= 1, "o botao Ortografia percorre mesmo com a opcao desligada")
    ort.aplicar_preferencias({"ortografia_ligada": True})
    # botao da faixa
    botoes = [b for b in janela.faixa.findChildren(BotaoAcao) if b.text() == "Ortografia"]
    checa(len(botoes) >= 1 and botoes[0].accessibleName().startswith("Verificar a ortografia"),
          "a aba Revisao tem o botao Ortografia, com nome para o leitor de tela")
    checa("F7" in janela.comandos.acao("ortografia").toolTip(), "a dica do botao diz F7")
    fechar_janela(janela)


# -- falhas ------------------------------------------------------------------------------------

def testar_desligar_sem_erro() -> None:
    secao("idioma nao instalado ou corretor que falha: desliga com aviso, sem erro")
    avisos = []
    painel = PainelDocumento("Segoe UI", 12)
    painel.resize(800, 400)
    painel.show()
    painel.mensagem.connect(avisos.append)
    painel.setPlainText("casa gato")
    ort = painel.ortografia
    ort.definir_corretor(CorretorFalso({"en-US": EN}, idiomas=("en-US",)))
    ort._timer.stop()
    ort._passo()
    checa(not ort.pintando() and ort._desligada, "idioma do documento (pt-BR) nao instalado: desligada")
    checa(any("não está instalado" in a and "Português" in a for a in avisos),
          "aviso discreto na barra de status: " + str(avisos))
    avisos.clear()
    ort2 = painel.ortografia
    ort2.aplicar_preferencias({"ortografia_ligada": True, "ortografia_idioma": "en-US"})
    ort2.definir_corretor(CorretorFalso({"en-US": EN}, idiomas=("en-US",)))
    ort2._timer.stop()
    ort2._passo()
    checa(not ort2._desligada and ort2._conferido == "en-US",
          "contraprova: com o idioma escolhido instalado, funciona")
    # corretor que levanta
    ruim = CorretorFalso({"pt-BR": PT})
    ort2.aplicar_preferencias({"ortografia_ligada": True, "ortografia_idioma": "auto"})
    ort2.definir_corretor(ruim)
    ruim.quebra = True
    ort2._timer.stop()
    ort2._passo()
    checa(ort2._desligada and any("desligada" in a for a in avisos),
          "o corretor falhou: desligada, com aviso e sem excecao")
    ort2.aplicar_preferencias({"ortografia_ligada": False})
    ort2.aplicar_preferencias({"ortografia_ligada": True})
    checa(not ort2._desligada, "ligar de novo nas opcoes tenta outra vez")
    # sem corretor nenhum
    ort2.definir_corretor(None)
    checa_igual(ort2.percorrer(), 0, "sem corretor, F7 nao faz nada (e nao levanta)")
    checa(not ort2.pintando(), "sem corretor nada e' pintado")
    fechar(painel)


# -- o arquivo ---------------------------------------------------------------------------------

def testar_arquivo_intacto() -> None:
    secao("o arquivo salvo nao muda: nenhuma marca de erro e w:proofErr como estava")
    docx = docx_de_idiomas()
    sem = janela_com(docx)
    sem.painel.ortografia.aplicar_preferencias({"ortografia_ligada": False})
    base = fx.partes_de(escrever(sem._modelo_atual()))
    fechar_janela(sem)
    com = janela_com(docx)
    ort = com.painel.ortografia
    varrer(ort)
    com.painel.viewport().grab()
    menu = QMenu()
    ort.montar_menu(menu, 2)
    ort.ignorar_tudo("gatoo")
    saida = fx.partes_de(escrever(com._modelo_atual()))
    checa_igual(saida["word/document.xml"], base["word/document.xml"],
                "document.xml igual, com a verificacao ligada, o menu e Ignorar tudo")
    checa(b"proofErr" not in saida["word/document.xml"], "nenhum w:proofErr novo")
    checa(not com.painel.documento_corpo().isModified(), "o documento nao ficou 'alterado'")
    # contraprova: a comparacao enxerga uma mudanca de texto
    cursor = com.painel.textCursor()
    cursor.setPosition(1)
    com.painel.setTextCursor(cursor)
    QTest.keyClick(com.painel, Key.Key_Z)
    outro = fx.partes_de(escrever(com._modelo_atual()))
    checa(outro["word/document.xml"] != base["word/document.xml"],
          "contraprova: um caractere digitado muda o document.xml")
    fechar_janela(com)


def testar_teste_de_acessibilidade_da_faixa() -> None:
    secao("a aba Revisao continua com nome em todo controle")
    from ajudantes import checa as _c  # noqa: F401
    from editdoc.interface import acessibilidade
    janela = janela_com(fx.docx_com_xml("<w:p><w:r><w:t>x</w:t></w:r></w:p>"))
    janela.faixa._abas.setCurrentIndex([janela.faixa._abas.tabText(i)
                                        for i in range(janela.faixa._abas.count())].index("Revisão"))
    drenar_eventos(2)
    faltando = acessibilidade.sem_nome(janela.faixa)
    checa_igual([type(w).__name__ for w in faltando], [], "nenhum controle da faixa sem nome")
    fechar_janela(janela)


# -- a API real do Windows ---------------------------------------------------------------------

def testar_api_do_windows() -> None:
    secao("fumaca da API real do Windows (so' quando ela existe)")
    if not sys.platform.startswith("win"):
        print("  PULADO: nao e' Windows")
        return
    try:
        from editdoc.ortografia.windows import CorretorWindows
        c = CorretorWindows()
        idiomas = c.idiomas()
    except (ErroDoCorretor, OSError) as erro:
        print(f"  PULADO: a API de verificacao ortografica nao esta' disponivel ({erro})")
        return
    checa(isinstance(c, Corretor), "o corretor do Windows e' um Corretor")
    if not idiomas:
        print("  PULADO: nenhum idioma instalado")
        return
    lang = "pt-BR" if "pt-BR" in idiomas else idiomas[0]
    checa(c.suporta(lang) and not c.suporta("xx-YY"), f"suporta {lang} e nao suporta xx-YY")
    texto = "\U0001F600 asdfqwertyzz"
    erros = c.verificar(texto, lang)
    checa(erros and texto[erros[0].ini:erros[0].fim] == "asdfqwertyzz",
          "acha a palavra sem sentido, com o indice certo depois de um caractere fora do plano basico")
    checa_igual(c.verificar("", lang), [], "texto vazio: nada")
    checa(isinstance(c.sugerir("asdfqwertyzz", lang), list), "sugerir devolve lista")
    try:
        c.verificar("teste", "xx-YY")
        checa(False, "idioma sem dicionario levanta ErroDoCorretor")
    except ErroDoCorretor:
        checa(True, "idioma sem dicionario levanta ErroDoCorretor")
    c.fechar()
    try:
        c.verificar("teste", lang)
        checa(False, "corretor fechado levanta ErroDoCorretor (nunca usa o ponteiro solto)")
    except ErroDoCorretor:
        checa(True, "corretor fechado levanta ErroDoCorretor (nunca usa o ponteiro solto)")


def main() -> int:
    testar_etiquetas_e_xml()
    testar_corretor_falso()
    testar_configuracao()
    testar_dialogo()
    testar_opcoes_na_janela()
    testar_idioma_do_arquivo()
    testar_trechos_e_mapa()
    testar_sublinhado()
    testar_colunas()
    testar_zoom_e_pagina()
    testar_incremental()
    testar_tile_em_cache()
    testar_fatias()
    testar_palavra_em_digitacao()
    testar_bloco_digitado_mantem_as_outras()
    testar_menu()
    testar_contexto_do_mouse()
    testar_ignorar()
    testar_repetida()
    testar_f7()
    testar_desligar_sem_erro()
    testar_arquivo_intacto()
    testar_teste_de_acessibilidade_da_faixa()
    testar_api_do_windows()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
