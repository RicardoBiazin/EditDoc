"""Hiperlinks e marcadores (0.1.3).

- leitura: link externo (r:id para relacao TargetMode=External) e interno (w:anchor) viram o
  destino do trecho (`Run.link`), com historico, dica e quadro; marcadores (inclusive entre
  paragrafos) viram marcas; relacao quebrada e marcador repetido avisam;
- gravacao: w:hyperlink com rId novo sem colisao (imagem, objeto e link na mesma parte),
  relacao externa do tipo hyperlink, w:history mantido; marcadores com id unico e pares;
  ida e volta, idempotencia, validador e conferencia, com contraprovas;
- tela: o link tem o estilo do arquivo (azul sublinhado) e o anchorHref do Qt; Ctrl+K
  insere, edita e o comando remove (um passo de desfazer cada); digitar logo depois do link
  nao o estende; Ctrl+clique abre o externo (pelo abridor injetado: nenhum navegador abre
  nos testes), pergunta antes de file:, recusa javascript: e leva o interno ao marcador;
  as setas, o Backspace e o Delete passam pela marca (invisivel) do marcador;
- limites: links demais viram texto, com aviso, sem travar.
"""

from __future__ import annotations

import contextlib
import time

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt, pular,
                       resumir, secao)
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx.escritor import escrever, escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo.documento import (Documento, Link, Marcador, Paragrafo, Run,  # noqa: E402
                                      normalizar, run_de_imagem)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
URL = "https://exemplo.invalid/pagina?a=1&b=2"


def codigos(avisos) -> dict[str, int]:
    return {a.codigo: a.contagem for a in avisos}


def trechos(modelo) -> list[tuple[str, str]]:
    """(texto, href) de cada run com link, na ordem."""
    return [(r.texto, r.link.href()) for p in modelo.paragrafos if hasattr(p, "runs")
            for r in p.runs if r.link is not None]


def marcadores(modelo) -> list[tuple[str, str]]:
    return [(r.marca.tipo, r.marca.nome) for p in modelo.paragrafos if hasattr(p, "runs")
            for r in p.runs if isinstance(r.marca, Marcador)]


def rels(partes: dict, parte: str = "word/_rels/document.xml.rels") -> dict:
    return {r.get("Id"): (r.get("Type"), r.get("Target"), r.get("TargetMode"))
            for r in etree.fromstring(partes[parte])}


def testar_leitura() -> None:
    secao("leitura: link externo e interno, marcadores, dica e historico")
    modelo, avisos = ler(fx.docx_com_links())
    checa_igual(trechos(modelo), [("site", URL), ("conclusão", "#Conclusao"),
                                  ("dica", "https://exemplo.invalid/dica"),
                                  ("e-mail", "mailto:fulano@exemplo.invalid")],
                "cada trecho de link guarda o destino (externo, marcador, e-mail)")
    links = [r.link for p in modelo.paragrafos for r in p.runs if r.link is not None]
    checa(links[0].historico is True and links[1].interno() and links[1].ancora == "Conclusao",
          "w:history e w:anchor lidos")
    checa(links[2].dica == "Dica do link" and links[2].quadro == "_blank", "w:tooltip e w:tgtFrame lidos")
    checa_igual(marcadores(modelo), [("inicio", "Entre"), ("fim", "Entre"), ("inicio", "Conclusao"),
                                     ("fim", "Conclusao")],
                "marcadores: o de entre paragrafos entra no paragrafo seguinte, na ordem")
    checa("HIPERLINK" not in codigos(avisos), "link preservado nao gera mais o aviso HIPERLINK")
    # Relacao quebrada: o texto fica, o endereco se perde, com aviso.
    quebrado = fx.docx_com_links(relacoes=fx.RELACOES_LINKS[1:])
    modelo_q, avisos_q = ler(quebrado)
    checa(codigos(avisos_q).get("HIPERLINK") == 1 and "site" in "".join(
        r.texto for r in modelo_q.paragrafos[0].runs) and modelo_q.paragrafos[0].runs[1].link is None,
          "link com relacao que nao existe: o texto fica, sem link, com o aviso HIPERLINK")
    # Relacao interna (nao externa) para link: tambem nao e' endereco.
    interna = fx.docx_com_links(relacoes=[("rId70", fx.RT_LINK, "media/x.png", "Internal")]
                                + fx.RELACOES_LINKS[1:])
    checa_igual(codigos(ler(interna)[1]).get("HIPERLINK"), 1,
                "link para relacao que nao e' externa: aviso HIPERLINK")
    # Marcador repetido.
    corpo = ('<w:p><w:bookmarkStart w:id="1" w:name="A"/><w:r><w:t>um</w:t></w:r><w:bookmarkEnd w:id="1"/>'
             '<w:bookmarkStart w:id="2" w:name="A"/><w:r><w:t>dois</w:t></w:r><w:bookmarkEnd w:id="2"/></w:p>')
    modelo_r, avisos_r = ler(fx.docx_com_links(corpo, relacoes=[]))
    checa(codigos(avisos_r).get("MARCADOR") == 1 and marcadores(modelo_r) == [("inicio", "A"), ("fim", "A")],
          "marcador com nome repetido: o segundo sai, com o aviso MARCADOR")


def testar_gravacao() -> None:
    secao("gravacao: w:hyperlink, relacao externa, rId sem colisao, marcadores")
    modelo, _ = ler(fx.docx_com_links())
    dados, avisos = escrever_com_avisos(modelo)
    partes = fx.partes_de(dados)
    checa_igual(avisos, [], "gravar links nao gera aviso")
    checa_igual(ordem.validar(partes), [], "o pacote passa no validador")
    raiz = etree.fromstring(partes["word/document.xml"])
    hs = list(raiz.iter("{%s}hyperlink" % W))
    checa_igual(len(hs), 4, "quatro w:hyperlink no arquivo")
    tabela = rels(partes)
    externos = [h for h in hs if h.get("{%s}id" % R)]
    checa(all(tabela[h.get("{%s}id" % R)][2] == "External"
              and tabela[h.get("{%s}id" % R)][0].endswith("/hyperlink") for h in externos)
          and len(externos) == 3, "cada link externo aponta para relacao External do tipo hyperlink")
    checa_igual(tabela[externos[0].get("{%s}id" % R)][1], URL, "o endereco volta igual (com &)")
    checa(all(h.get("{%s}history" % W) == "1" for h in hs), "w:history mantido")
    checa(hs[2].get("{%s}tooltip" % W) == "Dica do link" and hs[2].get("{%s}tgtFrame" % W) == "_blank",
          "dica e quadro mantidos")
    inicios = list(raiz.iter("{%s}bookmarkStart" % W))
    fins = list(raiz.iter("{%s}bookmarkEnd" % W))
    checa(len(inicios) == 2 and {i.get("{%s}id" % W) for i in inicios} == {f.get("{%s}id" % W) for f in fins}
          and len({i.get("{%s}id" % W) for i in inicios}) == 2, "marcadores com id unico, em pares")
    relido, avisos_r = ler(dados)
    checa(normalizar(relido).paragrafos == normalizar(modelo).paragrafos, "ida e volta: o modelo volta igual")
    checa_igual(avisos_r, [], "o arquivo gravado abre sem aviso")
    checa(escrever(relido) == escrever(ler(escrever(relido))[0]), "a segunda ida produz os mesmos bytes")
    conferencia.conferir(dados, modelo)
    checa(True, "a conferencia aceita os links e os marcadores")

    # rId novo sem colisao: imagem, link e link no cabecalho na mesma gravacao.
    doc = Documento(paragrafos=[Paragrafo(runs=[
        run_de_imagem(fx.imagem()), Run("a", link=Link(url="https://a.invalid", historico=True)),
        Run("b", link=Link(url="https://b.invalid")), Run("c", link=Link(url="https://a.invalid"))])],
        cabecalhos={"padrao": [Paragrafo(runs=[Run("cab", link=Link(url="https://c.invalid"))])]})
    partes = fx.partes_de(escrever(doc))
    tabela = rels(partes)
    checa(len(tabela) == len(set(tabela)) and ordem.validar(partes) == [],
          "imagem e links na mesma parte: rIds distintos e validos")
    alvos = sorted(v[1] for v in tabela.values() if v[0].endswith("/hyperlink"))
    checa_igual(alvos, ["https://a.invalid", "https://b.invalid"],
                "o mesmo endereco usa uma relacao so'; o do cabecalho fica nas relacoes do cabecalho")
    checa_igual([v[1] for v in rels(partes, "word/_rels/header1.xml.rels").values()], ["https://c.invalid"],
                "link do cabecalho: relacao na parte do cabecalho")

    # Contraprovas.
    partes = fx.partes_de(dados)
    xml = partes["word/document.xml"].decode("utf-8")
    rid = externos[0].get("{%s}id" % R)
    partes["word/_rels/document.xml.rels"] = partes["word/_rels/document.xml.rels"].replace(
        b' TargetMode="External"', b"", 1)
    checa(any("hiperlink" in p for p in ordem.validar(partes)) or any(rid in p for p in ordem.validar(partes)),
          "contraprova: hiperlink para relacao que nao e' externa e' acusado pelo validador")
    partes = fx.partes_de(dados)
    partes["word/document.xml"] = xml.replace('<w:bookmarkEnd w:id="1"/>', "", 1).encode("utf-8")
    checa(any("bookmarkStart sem bookmarkEnd" in p for p in ordem.validar(partes)),
          "contraprova: marcador sem fim e' acusado")
    partes["word/document.xml"] = xml.replace('w:id="1" w:name="Conclusao"', 'w:id="0" w:name="Conclusao"',
                                              1).encode("utf-8")
    checa(any("id repetido" in p for p in ordem.validar(partes)), "contraprova: id de marcador repetido")
    outro = Documento(paragrafos=[Paragrafo(runs=[
        Run(r.texto, link=None if r.link and r.link.url == URL else r.link, estilo=r.estilo,
            marca=r.marca) for r in p.runs]) for p in modelo.paragrafos], estilos=modelo.estilos)
    try:
        conferencia.conferir(escrever(outro), modelo)
        checa(False, "contraprova: link que sumiu passaria pela conferencia")
    except conferencia.FalhaDeConferencia as erro:
        checa("hiperlink" in str(erro), f"contraprova: a conferencia acusa o link que sumiu ({erro})")


def testar_limites() -> None:
    secao("limites: links demais viram texto com aviso, sem travar")
    corpo = "".join(f'<w:p><w:hyperlink w:anchor="m{i}"><w:r><w:t>l{i}</w:t></w:r></w:hyperlink></w:p>'
                    for i in range(60))
    inicio = time.perf_counter()
    modelo, avisos = ler(fx.docx_com_links(corpo, relacoes=[]), limites={"hiperlinks": 50})
    gasto = time.perf_counter() - inicio
    checa(codigos(avisos).get("HIPERLINK") == 10 and len(trechos(modelo)) == 50 and gasto < 2,
          f"60 links com limite 50: 10 viram texto com aviso ({gasto:.2f} s)")
    longo = ('<w:p><w:hyperlink w:anchor="' + "a" * 9000 + '"><w:r><w:t>x</w:t></w:r></w:hyperlink></w:p>')
    checa_igual(codigos(ler(fx.docx_com_links(longo, relacoes=[]))[1]).get("HIPERLINK"), 1,
                "marcador de link com 9000 caracteres: aviso, sem link")
    corpo = "".join(f'<w:p><w:bookmarkStart w:id="{i}" w:name="b{i}"/><w:r><w:t>x</w:t></w:r>'
                    f'<w:bookmarkEnd w:id="{i}"/></w:p>' for i in range(30))
    modelo, avisos = ler(fx.docx_com_links(corpo, relacoes=[]), limites={"marcadores": 20})
    checa(codigos(avisos).get("MARCADOR") == 10 and ordem.validar(fx.partes_de(escrever(modelo))) == [],
          "30 marcadores com limite 20: 10 avisam, e o arquivo gravado e' valido (sem fim solto)")


# -- tela ------------------------------------------------------------------------------

@contextlib.contextmanager
def dialogos(**substitutos):
    from editdoc.interface import dialogos_modais
    originais = {nome: getattr(dialogos_modais, nome) for nome in substitutos}
    for nome, funcao in substitutos.items():
        setattr(dialogos_modais, nome, funcao)
    try:
        yield
    finally:
        for nome, funcao in originais.items():
            setattr(dialogos_modais, nome, funcao)


def proibido(nome: str):
    def _falha(*_a, **_k):
        raise AssertionError(f"dialogo inesperado: {nome}")
    return _falha


def _posicao(painel, texto: str) -> int:
    return painel.documento_corpo().toPlainText().index(texto)


def _ponto(painel, pos: int):
    from PySide6.QtCore import QPointF
    ini = painel.layout_pag.retangulo_cursor(pos)
    fim = painel.layout_pag.retangulo_cursor(pos + 1)
    m = painel._mapa()
    x, y = m.doc_para_tela((ini.x() + fim.x()) / 2, ini.y() + ini.height() / 2, painel._paginas())
    return QPointF(x, y).toPoint()


def testar_tela() -> None:
    secao("tela: estilo do link, anchorHref, Ctrl+K inserir/editar/remover, digitar depois")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from editdoc import configuracao
    from editdoc.interface.gerente import GerenteDeJanelas
    from editdoc.ponte_qt import de_qt, links, marcas

    with pasta_temporaria() as tmp:
        arquivo = tmp / "links.docx"
        arquivo.write_bytes(fx.docx_com_links())
        gerente = GerenteDeJanelas(configuracao.padrao())
        janela = gerente.abrir(str(arquivo))
        painel = janela.painel
        doc = painel.documento_corpo()
        pos = _posicao(painel, "site")
        cf = links.formato_em(doc, pos)
        checa(cf.isAnchor() and cf.anchorHref() == URL, "o trecho do link tem isAnchor e anchorHref no Qt")
        checa(cf.foreground().color().name().upper() == "#0563C1"
              and cf.underlineStyle() != cf.UnderlineStyle.NoUnderline,
              "o link aparece com o estilo Hyperlink do arquivo (azul sublinhado)")
        volta = de_qt.extrair(doc)
        modelo, _ = ler(arquivo.read_bytes())
        checa(normalizar(volta).paragrafos == normalizar(Documento(paragrafos=modelo.paragrafos)).paragrafos,
              "Qt ida e volta: os mesmos links e marcadores")
        checa_igual(marcas.nomes_de_marcadores(doc), ["Entre", "Conclusao"],
                    "os marcadores estao no documento do Qt (para o dialogo de link)")

        # Digitar logo depois do link nao estende o link.
        painel.setFocus()
        cursor = painel.textCursor()
        cursor.setPosition(pos + len("site"))
        painel.setTextCursor(cursor)
        QTest.keyClick(painel, Qt.Key.Key_X)
        checa(links.link_em(doc, pos + 4) is None and links.link_em(doc, pos + 3) is not None,
              "digitar logo depois do link: a letra nova fica fora do link")
        fmt_x = links.formato_em(doc, pos + 4)
        checa(fmt_x.foreground().color().name().upper() != "#0563C1",
              "e sem o estilo Hyperlink (nao fica azul)")
        cursor.setPosition(pos + 2)
        painel.setTextCursor(cursor)
        QTest.keyClick(painel, Qt.Key.Key_Y)
        checa(links.link_em(doc, pos + 2) is not None, "digitar dentro do link: a letra entra no link")
        painel.undo()
        painel.undo()

        # Ctrl+K num texto selecionado: o link vai por cima, com a formatacao.
        alvo = _posicao(painel, " do texto") + 1
        cursor.setPosition(alvo)
        cursor.setPosition(alvo + 2, cursor.MoveMode.KeepAnchor)
        painel.setTextCursor(cursor)
        pedidos = []

        def responder(_pai, texto, link, marcadores, editar=False):
            pedidos.append((texto, link, list(marcadores), editar))
            return texto, Link(url="https://novo.invalid/", historico=True)
        with dialogos(pedir_link=responder):
            QTest.keyClick(painel, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
        checa(pedidos and pedidos[0][0] == "do" and pedidos[0][1] is None and not pedidos[0][3]
              and pedidos[0][2] == ["Entre", "Conclusao"],
              "Ctrl+K com selecao: o dialogo vem com o texto selecionado e os marcadores")
        checa(links.link_em(doc, alvo) == Link(url="https://novo.invalid/", historico=True)
              and links.link_em(doc, alvo + 1) is not None and links.link_em(doc, alvo + 2) is None,
              "o link novo cobre o trecho selecionado")
        checa(links.formato_em(doc, alvo).foreground().color().name().upper() == "#0563C1",
              "e recebe o estilo Hyperlink")
        painel.undo()
        checa(links.link_em(doc, alvo) is None, "Ctrl+Z desfaz o link num passo")
        painel.redo()

        # Ctrl+K num link: edita (trocar o endereco e o texto).
        cursor = painel.textCursor()
        cursor.setPosition(_posicao(painel, "site") + 1)
        painel.setTextCursor(cursor)

        def editar(_pai, texto, link, marcadores, editar=False):
            pedidos.append((texto, link, list(marcadores), editar))
            return "sítio", Link(ancora="Entre", historico=True)
        with dialogos(pedir_link=editar):
            QTest.keyClick(painel, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
        checa(pedidos[-1][0] == "site" and pedidos[-1][1].url == URL and pedidos[-1][3],
              "Ctrl+K num link: o dialogo vem com o texto e o endereco do link (editar)")
        nova = _posicao(painel, "sítio")
        checa(links.link_em(doc, nova) == Link(ancora="Entre", historico=True)
              and "site" not in doc.toPlainText()[:30], "o link passa a apontar para o marcador, com o texto novo")

        # Remover link pelo comando.
        cursor.setPosition(nova + 1)
        painel.setTextCursor(cursor)
        drenar_eventos(2)
        checa(janela.comandos.acao("remover_link").isEnabled(), "no link, Remover link fica habilitado")
        janela.comandos.acao("remover_link").trigger()
        checa(links.link_em(doc, nova) is None and links.link_em(doc, nova + 4) is None,
              "Remover link tira o link do trecho inteiro")
        checa(links.formato_em(doc, nova).foreground().color().name().upper() != "#0563C1",
              "e o estilo Hyperlink")
        painel.undo()
        checa(links.link_em(doc, nova) is not None, "Ctrl+Z traz o link de volta")
        cursor.setPosition(0)
        painel.setTextCursor(cursor)
        drenar_eventos(2)
        checa(not janela.comandos.acao("remover_link").isEnabled(), "fora de link, Remover fica desabilitado")

        # Ctrl+K sem selecao: insere o texto com o link no cursor.
        cursor = painel.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        painel.setTextCursor(cursor)
        fim = cursor.position()
        with dialogos(pedir_link=lambda *_a, **_k: ("Novo link", Link(url="https://inserido.invalid/",
                                                                       historico=True))):
            QTest.keyClick(painel, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
        checa(doc.toPlainText().endswith("Novo link") and links.link_em(doc, fim) is not None,
              "Ctrl+K sem selecao: o texto do link entra no cursor")
        with dialogos(pedir_perda=lambda *_a: "salvar", avisar=proibido("avisar")):
            checa(janela.salvar() is True, "salvar o documento com os links editados")
        salvo, avisos = ler(arquivo.read_bytes())
        hrefs = [h for _t, h in trechos(salvo)]
        checa("https://inserido.invalid/" in hrefs and "https://novo.invalid/" in hrefs and "#Entre" in hrefs,
              "o arquivo salvo tem os links inseridos e editados")
        checa(not any(a.perde_ao_salvar for a in avisos) and ordem.validar(fx.partes_de(arquivo.read_bytes())) == [],
              "e reabre sem aviso de perda e passa no validador")
        with dialogos(pedir_descartar=lambda *_a: "descartar"):
            for j in gerente.janelas():
                j.close()
        drenar_eventos()


def testar_ctrl_clique() -> None:
    secao("Ctrl+clique: externo pelo abridor injetado, confirmacao, recusa e marcador")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from editdoc.interface.painel_documento import PainelDocumento
    from editdoc.ponte_qt import para_qt

    doc = Documento(paragrafos=[
        Paragrafo(runs=[Run("web", link=Link(url="https://exemplo.invalid/a")), Run(" e "),
                        Run("arquivo", link=Link(url="file:///C:/Windows/notepad.exe")), Run(" e "),
                        Run("script", link=Link(url="javascript:alert(1)")), Run(" e "),
                        Run("interno", link=Link(ancora="Fim"))]),
        *[Paragrafo(runs=[Run(f"linha {i}")]) for i in range(40)],
        Paragrafo(runs=[Run(marca=Marcador("inicio", "Fim")), Run("Fim do documento"),
                        Run(marca=Marcador("fim", "Fim"))])])
    painel = PainelDocumento("Calibri", 11)
    painel.resize(900, 700)
    painel.show()
    drenar_eventos(2)
    para_qt.preencher(painel.documento_corpo(), doc)
    drenar_eventos(2)
    abertos: list[str] = []
    perguntas: list[str] = []
    painel.abrir_url = abertos.append
    painel.confirmar_link = lambda _p, url: perguntas.append(url) or False
    vp = painel.viewport()
    ctrl = Qt.KeyboardModifier.ControlModifier
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     _ponto(painel, _posicao(painel, "web") + 1))
    checa_igual(abertos, [], "clique sem Ctrl nao abre o link")
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, ctrl, _ponto(painel, _posicao(painel, "web") + 1))
    checa_igual(abertos, ["https://exemplo.invalid/a"], "Ctrl+clique em https abre sem perguntar")
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, ctrl, _ponto(painel, _posicao(painel, "arquivo") + 2))
    checa(perguntas == ["file:///C:/Windows/notepad.exe"] and len(abertos) == 1,
          "Ctrl+clique em file: pergunta antes, e com Nao nao abre")
    painel.confirmar_link = lambda _p, url: True
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, ctrl, _ponto(painel, _posicao(painel, "arquivo") + 2))
    checa_igual(abertos[-1], "file:///C:/Windows/notepad.exe", "com Sim explicito, abre")
    mensagens: list[str] = []
    painel.mensagem.connect(mensagens.append)
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, ctrl, _ponto(painel, _posicao(painel, "script") + 2))
    checa(len(abertos) == 2 and mensagens and "não é aberto" in mensagens[-1],
          "javascript: nunca abre, nem com a confirmacao")
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, ctrl, _ponto(painel, _posicao(painel, "interno") + 2))
    checa(len(abertos) == 2 and painel.textCursor().position() == _posicao(painel, "Fim do documento"),
          "Ctrl+clique no link interno leva o cursor ao marcador")
    painel.document().setModified(False)
    painel.close()


def testar_marcas_no_teclado() -> None:
    secao("teclado: setas, Backspace e Delete passam pela marca invisivel do marcador")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from editdoc.interface.painel_documento import PainelDocumento
    from editdoc.ponte_qt import de_qt, marcas, para_qt

    painel = PainelDocumento("Calibri", 11)
    painel.resize(900, 600)
    painel.show()
    drenar_eventos(2)
    para_qt.preencher(painel.documento_corpo(), Documento(paragrafos=[Paragrafo(runs=[
        Run("ab"), Run(marca=Marcador("inicio", "M")), Run("cd"), Run(marca=Marcador("fim", "M")),
        Run("ef")])]))
    painel.setFocus()
    cursor = painel.textCursor()
    cursor.setPosition(2)  # antes da marca de inicio
    painel.setTextCursor(cursor)
    QTest.keyClick(painel, Qt.Key.Key_Right)
    checa_igual(painel.textCursor().position(), 4, "seta para a direita passa a marca e o 'c' de uma vez")
    QTest.keyClick(painel, Qt.Key.Key_Left)
    checa_igual(painel.textCursor().position(), 3, "seta para a esquerda volta para antes do 'c'")
    QTest.keyClick(painel, Qt.Key.Key_Backspace)
    texto = "".join(r.texto for r in de_qt.extrair(painel.documento_corpo()).paragrafos[0].runs)
    checa(texto == "acdef" and len(marcas.posicoes_de_marcadores(painel.documento_corpo())) == 2,
          "Backspace logo depois da marca apaga o 'b', e o marcador fica")
    cursor = painel.textCursor()
    cursor.setPosition(4)  # entre 'd' e a marca de fim
    painel.setTextCursor(cursor)
    QTest.keyClick(painel, Qt.Key.Key_Delete)
    texto = "".join(r.texto for r in de_qt.extrair(painel.documento_corpo()).paragrafos[0].runs)
    checa(texto == "acdf" and len(marcas.posicoes_de_marcadores(painel.documento_corpo())) == 2,
          "Delete antes da marca apaga o 'e', e o marcador fica")
    # Contraprova: a marca existe mesmo, e apaga-se selecionando.
    painel.selectAll()
    QTest.keyClick(painel, Qt.Key.Key_Delete)
    checa_igual(marcas.posicoes_de_marcadores(painel.documento_corpo()), [],
                "contraprova: selecionar tudo e apagar leva as marcas junto")
    painel.document().setModified(False)
    painel.close()


def testar_dialogo() -> None:
    secao("dialogo de link: endereco normalizado, marcador, e o que volta ao comando")
    from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLineEdit, QRadioButton

    from editdoc.interface import dialogos_modais
    from editdoc.ponte_qt.links import endereco_normalizado, esquema

    checa_igual(endereco_normalizado("fulano@exemplo.invalid"), "mailto:fulano@exemplo.invalid",
                "e-mail sem esquema vira mailto")
    checa_igual(endereco_normalizado(" www.exemplo.invalid "), "https://www.exemplo.invalid",
                "www sem esquema vira https")
    checa_igual(endereco_normalizado("https://exemplo.invalid/a b"), "https://exemplo.invalid/a%20b",
                "espaco no endereco e' codificado (o Word recusa espaco cru)")
    checa(endereco_normalizado("   ") is None, "endereco vazio: nada")
    checa_igual(endereco_normalizado(r"C:\Pasta\a b.docx"), "file:///C:/Pasta/a%20b.docx",
                "caminho do Windows vira file:///")
    checa_igual([esquema(u) for u in ("HTTPS://x", "mailto:a", "file:///c", "javascript:x", "sem")],
                ["https", "mailto", "file", "javascript", ""], "esquema do endereco")

    def preencher(acao):
        def _exec(dialogo):
            acao(dialogo)
            dialogo.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
            return dialogo.result()
        return _exec

    original = QDialog.exec
    try:
        def externo(d):
            campos = d.findChildren(QLineEdit)
            campos[1].setText("exemplo.invalid/caminho")
        QDialog.exec = preencher(externo)
        texto, link = dialogos_modais.pedir_link(None, "Texto", None, ["Marca"])
        checa(texto == "Texto" and link.url == "https://exemplo.invalid/caminho" and link.historico,
              "endereco digitado: o link externo volta normalizado, com historico")

        def interno(d):
            d.findChildren(QRadioButton)[1].setChecked(True)
            d.findChild(QComboBox).setCurrentIndex(1)
        QDialog.exec = preencher(interno)
        texto, link = dialogos_modais.pedir_link(None, "Ir", None, ["A", "B"])
        checa(link == Link(ancora="B", historico=True), "marcador escolhido: o link interno volta")
        avisos = []
        original_avisar = dialogos_modais.avisar
        dialogos_modais.avisar = lambda *a: avisos.append(a)
        try:
            QDialog.exec = lambda d: (d.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Ok).click(), d.result())[1]
            checa(dialogos_modais.pedir_link(None, "x", None, []) is None and avisos,
                  "sem endereco e sem marcador: avisa e nao devolve link")
        finally:
            dialogos_modais.avisar = original_avisar
    finally:
        QDialog.exec = original


def main() -> int:
    testar_leitura()
    testar_gravacao()
    testar_limites()
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    testar_dialogo()
    testar_tela()
    testar_ctrl_clique()
    testar_marcas_no_teclado()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
