"""Varias secoes no mesmo documento (0.1.12).

Ate' a 0.1.11 so' a ultima secao valia: os w:sectPr dos paragrafos eram achatados (avisos SECAO,
PAGINA e CABECALHO_SECAO, com perda). Fixtures em codigo (`fixtures_docx.docx_com_secoes` e
`docx_com_secao_continua`): tres secoes (retrato, paisagem, retrato), cabecalhos proprios e
herdados, primeira pagina diferente na 2a, numeracao em romanos desde i na 1a e reiniciando em 1
na 2a, a 3a em pagina impar (com a pagina em branco antes), secao continua de duas colunas e
quebra de coluna.

- arquivo: cada w:sectPr volta em c14n (o que o modelo nao representa vai nos extras), as
  referencias apontam para partes com o mesmo conteudo, idempotencia, validador com sabotagens
  e limites contra arquivo hostil;
- tela: numero de paginas e tamanho de cada folha, cabecalho certo por folha (com a heranca),
  PAGE certo (romanos, reinicio, pagina em branco), linhas dentro do corpo da secao, PDF com
  o MediaBox de cada folha;
- edicao: inserir quebra de secao (as quatro), apagar a quebra (Backspace e Delete) fundindo as
  secoes como o Word, desfazer e refazer; orientacao so' na secao do cursor e no documento
  inteiro; Vincular ao anterior; rotulo nas marcas de formatacao; barra de status;
- janela: abrir -> salvar -> reabrir com a conferencia, sem aviso de perda.
"""

from __future__ import annotations

import time
from dataclasses import replace

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt, pular,
                       resumir, secao, usar_fonte_windows, usar_fontes_do_documento)
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx import secoes as fx_secoes  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.formato_docx.nomes import W  # noqa: E402
from editdoc.modelo.documento import Documento, MarcaQuebra, Paragrafo, Run, normalizar  # noqa: E402
from editdoc.modelo.pagina import Pagina  # noqa: E402
from editdoc.modelo.secoes import Secao, faixa_efetiva, secoes_de  # noqa: E402

R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _codigos(avisos) -> dict:
    return {a.codigo: (a.contagem, a.perde_ao_salvar) for a in avisos}


def _secoes_xml(docx: bytes) -> list:
    raiz = etree.fromstring(fx.partes_de(docx)["word/document.xml"])
    return list(raiz.iter(f"{{{W}}}sectPr"))


def _sem_refs(sect) -> str:
    """O sectPr sem as referencias de cabecalho e rodape (os rIds mudam), em c14n."""
    import copy
    copia = copy.deepcopy(sect)
    for f in list(copia):
        if f.tag in (f"{{{W}}}headerReference", f"{{{W}}}footerReference"):
            copia.remove(f)
    return etree.tostring(copia, method="c14n", exclusive=True).decode("utf-8")


def _refs(docx: bytes, sect) -> list:
    """(elemento, tipo, conteudo da parte em c14n) de cada referencia do sectPr."""
    partes = fx.partes_de(docx)
    rels = etree.fromstring(partes["word/_rels/document.xml.rels"])
    alvos = {r.get("Id"): r.get("Target") for r in rels}
    saida = []
    for f in sect:
        if f.tag in (f"{{{W}}}headerReference", f"{{{W}}}footerReference"):
            alvo = "word/" + alvos[f.get(f"{{{R}}}id")]
            raiz = etree.fromstring(partes[alvo])
            texto = "".join(raiz.itertext())
            saida.append((etree.QName(f).localname, f.get(f"{{{W}}}type"), texto))
    return saida


# -- arquivo ------------------------------------------------------------------------------------

def testar_leitura() -> None:
    secao("leitura: cada w:sectPr vira uma secao, sem aviso de perda")
    modelo, avisos = ler(fx.docx_com_secoes())
    checa_igual(_codigos(avisos), {}, "tres secoes abrem sem aviso (SECAO/PAGINA/CABECALHO_SECAO "
                                      "nao existem mais)")
    secoes = secoes_de(modelo)
    checa_igual(len(secoes), 3, "tres secoes")
    s1, s2, s3 = secoes
    checa((s1.pagina.largura_tw, s1.pagina.altura_tw, s1.pagina.paisagem) == (11906, 16838, False)
          and (s2.pagina.largura_tw, s2.pagina.altura_tw, s2.pagina.paisagem) == (16838, 11906, True)
          and (s3.pagina.largura_tw, s3.pagina.altura_tw) == (11906, 16838),
          "papel e orientacao de cada secao (retrato, paisagem, retrato)")
    checa((s1.pagina.margem_esq_tw, s2.pagina.margem_esq_tw, s3.pagina.margem_esq_tw)
          == (1701, 1134, 1440), "margens de cada secao")
    checa((s1.pagina.formato_numero, s1.pagina.numero_inicial) == ("lowerRoman", 1)
          and (s2.pagina.formato_numero, s2.pagina.numero_inicial) == ("decimal", 1)
          and s3.pagina.numero_inicial is None, "numeracao: i na 1a, 1 na 2a, continua na 3a")
    checa(not s1.pagina.primeira_diferente and s2.pagina.primeira_diferente,
          "primeira pagina diferente so' na 2a")
    checa_igual((s1.tipo, s2.tipo, s3.tipo), (None, "nextPage", "oddPage"), "w:type de cada secao")
    checa(sorted(s1.cabecalhos) == ["padrao"] and sorted(s1.rodapes) == ["padrao"]
          and sorted(s2.cabecalhos) == ["primeira"] and not s2.rodapes
          and sorted(s3.cabecalhos) == ["padrao"] and not s3.rodapes,
          "cada secao guarda so' o que declara")
    herdado = faixa_efetiva(secoes, 1, "cabecalho", "padrao")
    rodape = faixa_efetiva(secoes, 2, "rodape", "padrao")
    checa(herdado is not None and herdado[0] == 0 and rodape is not None and rodape[0] == 0,
          "heranca do Word: a 2a usa o cabecalho padrao da 1a; a 3a, o rodape da 1a")
    for nome in ("lnNumType", "vAlign", "docGrid", 'w:code="9"', "rsidSect"):
        checa(nome in (s1.extras or ""), f"extras da secao 1 guardam {nome}")
    for nome in ("pgBorders", "footnotePr", "formProt", "textDirection", "bidi", "rtlGutter"):
        checa(nome in (s2.extras or ""), f"extras da secao 2 guardam {nome}")
    checa("pgSz" not in (s3.extras or "") and "titlePg" not in (s2.extras or ""),
          "o que o modelo representa nao vai nos extras")


def testar_ida_e_volta_c14n() -> None:
    secao("ida e volta: cada sectPr em c14n, referencias com o mesmo conteudo, idempotencia")
    origem = fx.docx_com_secoes()
    modelo, _ = ler(origem)
    gravado = escrever(modelo)
    a, b = _secoes_xml(origem), _secoes_xml(gravado)
    checa_igual(len(b), 3, "o arquivo gravado tem os tres sectPr")
    for i, (x, y) in enumerate(zip(a, b)):
        checa_igual(_sem_refs(y), _sem_refs(x), f"sectPr da secao {i + 1} volta igual (c14n)")
        checa_igual(sorted(_refs(gravado, y)), sorted(_refs(origem, x)),
                    f"referencias da secao {i + 1}: mesmos tipos e mesmo conteudo")
    checa(b[0].getparent().tag == f"{{{W}}}pPr" and b[0].getparent()[-1] is b[0]
          and b[2].getparent().tag == f"{{{W}}}body" and b[2].getparent()[-1] is b[2],
          "sectPr como ultimo filho do pPr e do body")
    checa_igual(ordem.validar(fx.partes_de(gravado)), [], "o validador aceita o gravado")
    lido, avisos = ler(gravado)
    checa(not avisos and normalizar(lido) == normalizar(modelo),
          "a releitura da' o mesmo modelo, sem aviso")
    regravado = escrever(lido)
    checa_igual([etree.tostring(s, method="c14n") for s in _secoes_xml(regravado)],
                [etree.tostring(s, method="c14n") for s in _secoes_xml(gravado)],
                "segunda gravacao: os sectPr saem identicos (c14n)")
    doc1 = etree.tostring(etree.fromstring(fx.partes_de(gravado)["word/document.xml"]),
                          method="c14n")
    doc2 = etree.tostring(etree.fromstring(fx.partes_de(regravado)["word/document.xml"]),
                          method="c14n")
    checa(doc1 == doc2, "segunda gravacao: o document.xml inteiro igual (c14n)")
    conferencia.conferir(gravado, modelo)
    checa(True, "a conferencia pos-gravacao aceita")
    # Contraprova da conferencia: o sectPr da secao 2 trocado depois da gravacao.
    partes = fx.partes_de(gravado)
    partes["word/document.xml"] = partes["word/document.xml"].replace(
        b'w:orient="landscape"', b'w:orient="portrait"', 1).replace(b'w:w="16838" w:h="11906"',
                                                                    b'w:w="11906" w:h="16838"', 1)
    try:
        conferencia.conferir(fx.montar(partes), modelo)
        checa(False, "contraprova: a conferencia acusa a secao com outro papel")
    except conferencia.FalhaDeConferencia as erro:
        checa("secao" in str(erro), f"contraprova: a conferencia acusa a secao ({erro})")


def testar_continua_e_colunas() -> None:
    secao("secao continua de duas colunas e quebra de coluna: preservadas (aviso sem perda)")
    origem = fx.docx_com_secao_continua()
    modelo, avisos = ler(origem)
    checa_igual(_codigos(avisos), {"COLUNAS": (1, False)},
                "colunas: aviso COLUNAS sem perda (preservadas, mostradas em uma coluna)")
    s = secoes_de(modelo)
    checa_igual([x.tipo for x in s], [None, "continuous", "continuous"], "tipos das secoes")
    checa(s[1].colunas == (2, 567) and 'w:num="2"' in (s[1].extras or ""),
          "w:cols com duas colunas e o espaco nos extras")
    quebras = [r for p in modelo.paragrafos for r in p.runs if isinstance(r.marca, MarcaQuebra)]
    checa_igual(len(quebras), 1, "a quebra de coluna vira marca no fluxo")
    gravado = escrever(modelo)
    checa(b'<w:br w:type="column"/>' in fx.partes_de(gravado)["word/document.xml"],
          "a quebra de coluna volta ao arquivo")
    for i, (x, y) in enumerate(zip(_secoes_xml(origem), _secoes_xml(gravado))):
        checa_igual(_sem_refs(y), _sem_refs(x), f"sectPr {i + 1} da continua volta igual (c14n)")


def testar_validador() -> None:
    secao("validador: sectPr no lugar, referencia que resolve, limites; com sabotagens")
    gravado = escrever(ler(fx.docx_com_secoes())[0])
    partes = fx.partes_de(gravado)
    xml = partes["word/document.xml"].decode("utf-8")
    checa_igual(fx_secoes.validar(partes), [], "o gravado passa")

    def com(novo: str) -> list:
        p = dict(partes)
        p["word/document.xml"] = novo.encode("utf-8")
        return fx_secoes.validar(p)

    primeiro = xml.index("<w:sectPr")
    fim_ppr = xml.index("</w:pPr>", primeiro)
    sab = xml[:fim_ppr] + "<w:jc w:val=\"left\"/>" + xml[fim_ppr:]
    checa(any("ultimo filho do w:pPr" in p for p in com(sab)),
          "contraprova: sectPr que nao e' o ultimo filho do pPr")
    sab = xml.replace('r:id="', 'r:id="rIdX', 1)
    checa(any("nao resolve" in p for p in com(sab)),
          "contraprova: referencia de cabecalho sem relacao")
    rodape = next(r.get("Id") for r in etree.fromstring(partes["word/_rels/document.xml.rels"])
                  if r.get("Type").endswith("/footer"))
    inicio = xml.index('<w:headerReference w:type="default" r:id="')
    rid = xml[inicio:].split('r:id="', 1)[1].split('"', 1)[0]
    sab = xml.replace(f'<w:headerReference w:type="default" r:id="{rid}"',
                      f'<w:headerReference w:type="default" r:id="{rodape}"', 1)
    checa(any("nao resolve para uma parte de cabecalho" in p for p in com(sab)),
          "contraprova: headerReference apontando para um rodape")
    sab = xml.replace('<w:headerReference w:type="first"', '<w:headerReference w:type="estranho"', 1)
    checa(any("w:type invalido" in p for p in com(sab)), "contraprova: tipo de referencia invalido")
    sab = xml.replace('<w:cols w:space="708"/>', '<w:cols w:num="99" w:space="708"/>', 1)
    checa(any("w:cols" in p for p in com(sab)), "contraprova: 99 colunas")
    tabela = ('<w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="2000"/></w:tblGrid><w:tr><w:tc><w:p>'
              '<w:pPr><w:sectPr/></w:pPr></w:p></w:tc></w:tr></w:tbl><w:p/>')
    sab = xml.replace("<w:body>", "<w:body>" + tabela, 1)
    checa(any("fora do corpo" in p for p in com(sab)), "contraprova: sectPr dentro de tabela")
    muitas = "".join("<w:p><w:pPr><w:sectPr/></w:pPr></w:p>" for _ in range(2002))
    sab = xml.replace("<w:body>", "<w:body>" + muitas, 1)
    checa(any("secoes demais" in p for p in com(sab)), "contraprova: mais de 2000 secoes")


def testar_hostil() -> None:
    secao("arquivo hostil: milhares de secoes e colunas demais, em menos de 2 s")
    corpo = "".join("<w:p><w:pPr><w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/></w:sectPr>"
                    f"</w:pPr><w:r><w:t>{i}</w:t></w:r></w:p>" for i in range(2600))
    inicio = time.perf_counter()
    modelo, avisos = ler(fx.docx_com_xml(corpo))
    gasto = time.perf_counter() - inicio
    meio = [p for p in modelo.paragrafos if p.secao is not None]
    checa(gasto < 2.0 and len(meio) == 2000 and _codigos(avisos).get("SECAO") == (600, True),
          f"2600 secoes: 2000 ficam, 600 viram uma so' com aviso SECAO ({gasto:.2f} s)")
    checa_igual(ordem.validar(fx.partes_de(escrever(modelo))), [],
                "o arquivo gravado com 2000 secoes passa no validador")
    corpo = ("<w:p><w:pPr><w:sectPr><w:cols w:num=\"999\" w:space=\"10\"/></w:sectPr></w:pPr>"
             "<w:r><w:t>x</w:t></w:r></w:p>")
    modelo, avisos = ler(fx.docx_com_xml(corpo))
    checa(_codigos(avisos).get("FORMATACAO") and "cols" not in (modelo.paragrafos[0].secao.extras or ""),
          "w:cols com 999 colunas sai, com aviso FORMATACAO")
    papel = "<w:p><w:pPr><w:sectPr><w:pgSz w:w=\"999999999\" w:h=\"5\"/></w:sectPr></w:pPr></w:p>"
    modelo, avisos = ler(fx.docx_com_xml(papel))
    checa("PAPEL_INVALIDO" in _codigos(avisos) and modelo.paragrafos[0].secao.pagina == Pagina(),
          "papel impossivel numa secao do meio: A4 com aviso PAPEL_INVALIDO")


def testar_mudanca_no_modelo() -> None:
    secao("so' o que mudou muda: orientacao da secao 2 no modelo, o resto do sectPr igual")
    modelo, _ = ler(fx.docx_com_secoes())
    s2 = modelo.paragrafos[[i for i, p in enumerate(modelo.paragrafos) if p.secao][1]].secao
    s2.pagina = s2.pagina.com_orientacao(False)
    gravado = escrever(modelo)
    sect = _secoes_xml(gravado)[1]
    pg = sect.find(f"{{{W}}}pgSz")
    checa((pg.get(f"{{{W}}}w"), pg.get(f"{{{W}}}h"), pg.get(f"{{{W}}}orient"))
          == ("11906", "16838", None), "a secao 2 grava retrato")
    for nome in ("pgBorders", "footnotePr", "formProt", "titlePg", "textDirection"):
        checa(sect.find(f"{{{W}}}{nome}") is not None, f"{nome} continua na secao 2")
    checa_igual(ordem.validar_secao(etree.fromstring(fx.partes_de(gravado)["word/document.xml"])),
                [], "a ordem dos filhos continua a do esquema")


# -- tela -------------------------------------------------------------------------------------

def _janela(docx: bytes, largura: int = 1100, altura: int = 900):
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    modelo, avisos = ler(docx)
    janela = JanelaPrincipal(configuracao.padrao())
    janela.resize(largura, altura)
    janela.show()
    janela.carregar(modelo, avisos, None)
    janela.painel.setFocus()
    drenar_eventos()
    janela.painel.viewport().grab()
    return janela


def _fechar(janela) -> None:
    janela.painel.sair_da_faixa()
    janela.painel.documento_corpo().setModified(False)
    janela.close()
    drenar_eventos()


def _folhas(layout) -> list:
    return [(layout.efetiva_da(n).largura_tw, layout.efetiva_da(n).altura_tw)
            for n in range(layout.numero_paginas())]


def _texto_da_faixa(layout, onde: str, n: int) -> str | None:
    faixa = layout.faixa_da_folha(onde, n)
    return faixa.doc.toPlainText().strip() if faixa is not None else None


def _page(layout, n: int) -> str:
    from editdoc.modelo.campos import valor_do_campo
    indice, pagina, paginas = layout.campos_da_folha(n)
    return valor_do_campo("PAGE", indice, layout.numero_paginas(), pagina, paginas)


def _linhas_fora(layout) -> list:
    """Linhas do corpo fora do corpo da folha delas (largura ou altura da secao)."""
    doc = layout.doc
    dl = doc.documentLayout()
    ruins = []
    b = doc.begin()
    while b.isValid():
        r = dl.blockBoundingRect(b)
        lay = b.layout()
        for i in range(lay.lineCount()):
            ln = lay.lineAt(i)
            topo = r.top() + ln.y()
            n = int(topo // layout.hb)
            ef = layout.efetiva_da(n)
            direita = r.left() + ln.x() + ln.naturalTextWidth()
            if topo + ln.height() - n * layout.hb > ef.corpo_altura_tw() + 1 \
                    or direita > ef.corpo_largura_tw() + 1:
                ruins.append((b.blockNumber(), n))
        b = b.next()
    return ruins


def _vazias(layout) -> list:
    """Folhas sem nenhuma linha de texto do corpo."""
    doc = layout.doc
    dl = doc.documentLayout()
    com = set()
    b = doc.begin()
    while b.isValid():
        r = dl.blockBoundingRect(b)
        lay = b.layout()
        for i in range(lay.lineCount()):
            com.add(int((r.top() + lay.lineAt(i).y()) // layout.hb))
        b = b.next()
    return [n for n in range(layout.numero_paginas()) if n not in com]


def testar_tela() -> None:
    secao("tela: folhas de cada secao, cabecalho herdado, PAGE, pagina em branco, corpo")
    janela = _janela(fx.docx_com_secoes())
    try:
        lay = janela.painel.layout_pag
        lista = lay.secoes.lista
        checa_igual(len(lista), 3, "o layout tem tres secoes")
        folhas = _folhas(lay)
        n1, n2 = lista[1].inicio, lista[2].inicio
        checa(n1 >= 2 and all(f == (11906, 16838) for f in folhas[:n1]),
              f"secao 1: {n1} folhas em retrato")
        checa(folhas[n1] == (16838, 11906), "secao 2: a primeira folha e' paisagem")
        checa(all(f == (11906, 16838) for f in folhas[n2:]), "secao 3: folhas em retrato")
        checa_igual(_vazias(lay), [n2 - 1],
                    "a pagina em branco antes da secao 3 (oddPage) e' a unica sem texto")
        checa_igual(folhas[n2 - 1], (16838, 11906), "a pagina em branco e' da secao 2 (paisagem)")
        checa_igual(_linhas_fora(lay), [], "nenhuma linha fora do corpo da sua folha")
        # Contraprova: com o papel da secao 1 em todas as folhas, as linhas da paisagem passam.
        efetiva = lay.efetiva_da
        retrato = efetiva(0)
        lay.efetiva_da = lambda _n: retrato
        try:
            checa(_linhas_fora(lay), "contraprova: com o papel errado as linhas da paisagem "
                                     "ficam fora do corpo")
        finally:
            del lay.efetiva_da
        checa_igual([_texto_da_faixa(lay, "cabecalho", n) for n in (0, n1, n1 + 1 if n1 + 1 < n2 else n1, n2)],
                    [fx.CAB_SECAO_1, fx.CAB_SECAO_2_PRIMEIRA,
                     fx.CAB_SECAO_1 if n1 + 1 < n2 else fx.CAB_SECAO_2_PRIMEIRA, fx.CAB_SECAO_3],
                    "cabecalho de cada folha: o da secao, a primeira da 2a, o herdado da 1a")
        checa(all((_texto_da_faixa(lay, "rodape", n) is None) == (n == n1)
                  for n in range(lay.numero_paginas())),
              "o rodape da secao 1 (PAGE) vale nas outras secoes (heranca); a primeira folha da "
              "2a (titlePg, sem rodape de primeira pagina em secao nenhuma) fica sem, como no Word")
        checa_igual([_page(lay, n) for n in range(n1)], ["i", "ii", "iii", "iv"][:n1],
                    "PAGE na secao 1: romanos desde i")
        checa_igual(_page(lay, n1), "1", "PAGE na primeira folha da secao 2: 1 (reinicio)")
        checa(int(_page(lay, n2)) % 2 == 1, f"PAGE na secao 3 e' impar ({_page(lay, n2)})")
        # Os campos do rodape pintam o numero da folha (o documento da faixa preparado nela).
        faixa = lay.faixa_da_folha("rodape", n2)
        lay.preparar_faixa(faixa, n2, lay.numero_paginas())
        checa_igual(faixa.contexto.valor("PAGE", n2), _page(lay, n2),
                    "o rodape herdado mostra o numero da folha da secao 3")
        faixa = lay.faixa_da_folha("rodape", 0)
        lay.preparar_faixa(faixa, 0, lay.numero_paginas())
        checa_igual(faixa.contexto.valor("PAGE", 0), "i", "e o da secao 1 mostra i")
        janela._atualizar_rotulo_pagina()
        checa(janela._rotulo_secao.text() == "Seção 1 de 3" and not janela._rotulo_secao.isHidden(),
              "barra de status: Seção 1 de 3")
        # Mapa da tela: cada folha com o seu tamanho, e o clique volta ao lugar.
        m = janela.painel.mapa()
        x, y, w, h = m.folha_na_tela(n1)
        checa(abs(w - 16838 * m.escala) < 1 and abs(h - 11906 * m.escala) < 1,
              "na tela a folha paisagem tem o tamanho dela")
        xd, yd = m.tela_para_doc(x + 3000 * m.escala, y + 3000 * m.escala, lay.numero_paginas())
        xt, yt = m.doc_para_tela(xd, yd, lay.numero_paginas())
        checa(abs(xt - (x + 3000 * m.escala)) < 0.5 and abs(yt - (y + 3000 * m.escala)) < 0.5,
              "tela -> documento -> tela na folha paisagem")
        # Marcas de formatacao: a quebra mostra o tipo da secao seguinte.
        from editdoc.interface.vista_paginas import rotulo_da_quebra
        from editdoc.ponte_qt import secoes as pq_secoes
        quebras = pq_secoes.quebras_de_secao(lay.doc)
        checa_igual([rotulo_da_quebra(lay.doc, p, {"secao": i}) for p, i in quebras],
                    ["Quebra de seção (Próxima página)", "Quebra de seção (Página ímpar)"],
                    "rotulo das quebras nas marcas de formatacao")
        janela.painel.definir_marcas(True)
        img = janela.painel.viewport().grab()
        janela.painel.definir_marcas(False)
        checa(not img.isNull(), "a tela pinta com as marcas ligadas")
    finally:
        _fechar(janela)


def testar_continua_na_tela() -> None:
    secao("tela: secao continua comeca na mesma folha; a quebra de coluna fica no texto")
    janela = _janela(fx.docx_com_secao_continua())
    try:
        lay = janela.painel.layout_pag
        checa_igual(lay.numero_paginas(), 1, "as tres secoes cabem numa folha so'")
        doc = lay.doc
        dl = doc.documentLayout()
        from editdoc.ponte_qt import secoes as pq_secoes
        topos = [dl.blockBoundingRect(doc.findBlock(p).next()).top()
                 for p, _i in pq_secoes.quebras_de_secao(doc)]
        checa(len(topos) == 2 and all(t < lay.hb for t in topos),
              "as secoes continuas comecam na mesma folha (sem quebra de pagina)")
        checa_igual([i.paginas for i in lay.secoes.lista], [1, 0, 0],
                    "a folha e' da secao que esta' no topo dela (cabecalho e papel da 1a)")
        checa_igual(_vazias(lay), [], "e a folha tem texto")
        checa("Primeira coluna." in janela.painel.toPlainText()
              and "Segunda coluna." in janela.painel.toPlainText(), "texto das colunas na tela")
    finally:
        _fechar(janela)


def testar_pdf() -> None:
    secao("PDF: o MediaBox de cada folha e' o papel da secao dela")
    import leitor_pdf
    from editdoc.interface import impressao
    janela = _janela(fx.docx_com_secoes())
    try:
        lay = janela.painel.layout_pag
        total = lay.numero_paginas()
        meta = impressao.Metadados("Seções", "Teste", "EditDoc")
        dados = impressao.gerar_pdf(lay, list(range(total)), meta)
        pdf = leitor_pdf.ler_pdf(dados)
        esperado = [(round(w / 20), round(h / 20)) for w, h in _folhas(lay)]
        obtido = [(round(p.largura_pt), round(p.altura_pt)) for p in pdf.paginas]
        checa_igual(obtido, esperado, "MediaBox de cada folha (retrato 595x842, paisagem 842x595)")
        checa((842, 595) in obtido and (595, 842) in obtido,
              "contraprova: o PDF tem folhas dos dois tamanhos")
        n1 = lay.secoes.lista[1].inicio
        checa(fx.CAB_SECAO_2_PRIMEIRA.split()[0] in pdf.paginas[n1].texto,
              "o cabecalho da primeira folha da secao 2 sai no PDF")
    finally:
        _fechar(janela)


def testar_salvar_reabrir() -> None:
    secao("janela: abrir -> salvar como -> reabrir -> salvar, com a conferencia e sem perda")
    from editdoc.interface import dialogos_modais
    with pasta_temporaria() as tmp:
        janela = _janela(fx.docx_com_secoes())
        try:
            checa(not janela._avisos, "abre sem aviso")
            alvo = tmp / "secoes.docx"
            perdas = []
            original = dialogos_modais.pedir_perda
            dialogos_modais.pedir_perda = lambda *a: perdas.append(a) or "cancelar"
            try:
                checa(janela._gravar(alvo, trocar=True), "salvar como grava (com a conferencia)")
            finally:
                dialogos_modais.pedir_perda = original
            checa(not perdas, "nenhuma pergunta de perda")
        finally:
            _fechar(janela)
        dados = alvo.read_bytes()
        checa_igual([_sem_refs(s) for s in _secoes_xml(dados)],
                    [_sem_refs(s) for s in _secoes_xml(fx.docx_com_secoes())],
                    "os sectPr gravados pela janela sao os de origem (c14n)")
        janela = _janela(dados)
        try:
            checa_igual(len(janela.painel.layout_pag.secoes.lista), 3, "reaberto: tres secoes")
            janela.painel.documento_corpo().setModified(True)
            segundo = tmp / "secoes2.docx"
            checa(janela._gravar(segundo, trocar=True), "a segunda gravacao passa na conferencia")
        finally:
            _fechar(janela)
        a = etree.tostring(etree.fromstring(fx.partes_de(dados)["word/document.xml"]), method="c14n")
        b = etree.tostring(etree.fromstring(fx.partes_de(segundo.read_bytes())["word/document.xml"]),
                           method="c14n")
        checa(a == b, "segunda gravacao: o document.xml igual ao da primeira (c14n)")


# -- edicao ------------------------------------------------------------------------------------

def _documento_simples(n: int = 30) -> Documento:
    return Documento(paragrafos=[Paragrafo(runs=[Run(f"Parágrafo {i + 1}. " + fx.TEXTO_SECAO * 2)])
                                 for i in range(n)])


def _cursor_no_paragrafo(painel, numero: int, deslocamento: int = 0) -> None:
    from PySide6.QtGui import QTextCursor
    doc = painel.documento_corpo()
    c = QTextCursor(doc)
    c.setPosition(doc.findBlockByNumber(numero).position() + deslocamento)
    painel.setTextCursor(c)


def _estado(painel) -> tuple:
    from editdoc.ponte_qt import de_qt
    m = de_qt.extrair(painel.documento_corpo())
    return (tuple("".join(r.texto for r in p.runs) for p in m.paragrafos),
            tuple(p.secao.tipo if p.secao else "-" for p in m.paragrafos),
            painel.layout_pag.numero_paginas())


def testar_inserir_e_apagar() -> None:
    secao("edicao: inserir quebra de secao (as quatro), apagar como o Word, desfazer e refazer")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    janela = JanelaPrincipal(configuracao.padrao())
    janela.resize(1100, 900)
    janela.show()
    janela.carregar(_documento_simples(), [], None)
    drenar_eventos()
    painel = janela.painel
    try:
        lay = painel.layout_pag
        painel.viewport().grab()
        antes = _estado(painel)
        _cursor_no_paragrafo(painel, 9, 5)
        janela.comandos.acao("quebra_secao_proxima").trigger()
        painel.viewport().grab()
        texto, tipos, paginas = _estado(painel)
        checa(len(texto) == len(antes[0]) + 1 and texto[9] == antes[0][9][:5]
              and texto[10] == antes[0][9][5:], "o paragrafo se parte no cursor")
        checa(tipos[9] is None and tipos.count("-") == len(texto) - 1,
              "o paragrafo de cima termina a secao nova (tipo da secao do cursor)")
        checa_igual(painel.layout_pag.secoes.lista[-1].secao.tipo, "nextPage",
                    "a secao de baixo comeca na proxima pagina")
        checa_igual(lay.secoes.lista[1].inicio, lay.pagina_do_cursor(painel.textCursor().position()),
                    "o texto depois da quebra comeca numa folha nova")
        checa(painel.textCursor().block().blockNumber() == 10, "o cursor fica depois da quebra")
        painel.undo()
        painel.viewport().grab()
        checa_igual(_estado(painel), antes, "um desfazer devolve o documento e as paginas")
        painel.redo()
        painel.viewport().grab()
        checa_igual(_estado(painel)[1].count("-"), len(antes[0]), "refazer devolve a quebra")
        # Backspace no comeco do paragrafo de baixo: apaga a quebra e funde os dois.
        _cursor_no_paragrafo(painel, 10)
        QTest.keyClick(painel, Qt.Key.Key_Backspace)
        painel.viewport().grab()
        checa_igual(_estado(painel)[:2], antes[:2], "Backspace apaga a quebra e funde (como o Word)")
        checa_igual(len(lay.secoes.lista), 1, "volta a uma secao so'")
        painel.undo()
        painel.viewport().grab()
        checa_igual(len(lay.secoes.lista), 2, "desfazer devolve a quebra")
        # Delete antes da quebra (no fim do texto do paragrafo de cima).
        _cursor_no_paragrafo(painel, 9)
        c = painel.textCursor()
        c.movePosition(c.MoveOperation.EndOfBlock)
        painel.setTextCursor(c)
        QTest.keyClick(painel, Qt.Key.Key_End)
        checa(not painel._depois_da_quebra(painel.textCursor().position()),
              "End deixa o caret antes da quebra (ela e' a marca do paragrafo)")
        QTest.keyClick(painel, Qt.Key.Key_Delete)
        painel.viewport().grab()
        checa_igual(_estado(painel)[:2], antes[:2], "Delete antes da quebra apaga e funde")
        painel.undo()
        # A secao de cima assume as propriedades da de baixo ao apagar: muda o papel da de baixo.
        _cursor_no_paragrafo(painel, 20)
        janela._mudar_orientacao(True)
        painel.viewport().grab()
        checa(lay.secoes.lista[0].pagina.paisagem is False and lay.secoes.lista[1].pagina.paisagem,
              "orientacao so' na secao do cursor (a de baixo vira paisagem)")
        folhas = _folhas(lay)
        checa(folhas[0] == (11906, 16838) and folhas[-1] == (16838, 11906),
              "folhas da secao de cima em retrato, as de baixo em paisagem")
        checa_igual(_linhas_fora(lay), [], "as linhas refluem na largura de cada secao")
        _cursor_no_paragrafo(painel, 10)
        QTest.keyClick(painel, Qt.Key.Key_Backspace)
        painel.viewport().grab()
        checa(len(lay.secoes.lista) == 1 and lay.pagina_arquivo.paisagem
              and all(f == (16838, 11906) for f in _folhas(lay)),
              "apagar a quebra: o texto de cima passa a paisagem (as propriedades da de baixo)")
        painel.undo()
        painel.viewport().grab()
        checa(len(lay.secoes.lista) == 2 and _folhas(lay)[0] == (11906, 16838),
              "desfazer devolve as duas secoes, a de cima em retrato")
        # As outras tres quebras.
        for acao, tipo in (("quebra_secao_continua", "continuous"), ("quebra_secao_par", "evenPage"),
                           ("quebra_secao_impar", "oddPage")):
            _cursor_no_paragrafo(painel, 3)
            janela.comandos.acao(acao).trigger()
            painel.viewport().grab()
            checa_igual(lay.secoes.lista[1].secao.tipo, tipo, f"{acao}: a secao nova e' {tipo}")
            if tipo in ("evenPage", "oddPage"):
                numero = int(_page(lay, lay.secoes.lista[1].inicio))
                checa(numero % 2 == (0 if tipo == "evenPage" else 1),
                      f"{acao}: a secao comeca em pagina {'par' if tipo == 'evenPage' else 'impar'} "
                      f"({numero})")
            painel.undo()
            painel.viewport().grab()
        checa_igual(len(lay.secoes.lista), 2, "os desfazer devolvem as duas secoes")
        # Na tabela e no cabecalho nao ha' quebra de secao.
        painel.entrar_na_faixa("cabecalho", 0)
        checa(not janela.comandos.acao("quebra_secao_proxima").isEnabled()
              or painel.inserir_quebra_de_secao("nextPage") is False,
              "no cabecalho a quebra de secao nao entra")
        painel.sair_da_faixa()
    finally:
        _fechar(janela)


def testar_documento_inteiro_e_vinculo() -> None:
    secao("Configurar pagina: Aplicar a documento inteiro; Vincular ao anterior")
    from editdoc.interface import dialogos_modais
    janela = _janela(fx.docx_com_secoes())
    painel = janela.painel
    lay = painel.layout_pag
    try:
        _cursor_no_paragrafo(painel, 0)
        original = dialogos_modais.pedir_configurar_pagina
        dialogos_modais.pedir_configurar_pagina = lambda _p, atual, varias_secoes=False: (
            atual.com_margens(1000, 1000, 1000, 1000), True)
        try:
            janela._mudar_margens("Personalizadas")
        finally:
            dialogos_modais.pedir_configurar_pagina = original
        painel.viewport().grab()
        checa(all(i.pagina.margem_esq_tw == 1000 for i in lay.secoes.lista),
              "Aplicar a: Documento inteiro muda as margens das tres secoes")
        checa(lay.secoes.lista[1].pagina.paisagem, "a orientacao de cada secao fica")
        # Vincular ao anterior: a 2a usa o padrao da 1a.
        n1 = lay.secoes.lista[1].inicio
        n_padrao = n1 + 1
        if n_padrao >= lay.secoes.lista[2].inicio:
            checa(True, "secao 2 de uma folha: o vinculo e' conferido na 3a")
            n_padrao = lay.secoes.lista[2].inicio
        painel.entrar_na_faixa("cabecalho", n_padrao)
        janela.atualizador.atualizar() if hasattr(janela, "atualizador") else None
        estado = painel.estado_do_vinculo()
        esperado = n_padrao < lay.secoes.lista[2].inicio
        checa_igual(estado, esperado, "estado de Vincular ao anterior na folha editada")
        if esperado:
            checa(painel.alternar_vinculo(), "desvincular copia o cabecalho da anterior")
            faixa = painel.editando_faixa()
            from PySide6.QtGui import QTextCursor
            c = QTextCursor(faixa.doc)
            c.movePosition(c.MoveOperation.End)
            c.insertText(" (só da seção 2)")
            painel.viewport().grab()
            checa(_texto_da_faixa(lay, "cabecalho", 0) == fx.CAB_SECAO_1
                  and _texto_da_faixa(lay, "cabecalho", n_padrao).endswith("(só da seção 2)"),
                  "editar o desvinculado nao muda o da secao 1")
            original = dialogos_modais.confirmar_vincular_anterior
            dialogos_modais.confirmar_vincular_anterior = lambda _p: True
            try:
                checa(painel.alternar_vinculo(), "vincular de novo")
            finally:
                dialogos_modais.confirmar_vincular_anterior = original
            checa_igual(_texto_da_faixa(lay, "cabecalho", n_padrao), fx.CAB_SECAO_1,
                        "vinculado: a folha volta a mostrar o da secao 1")
        painel.sair_da_faixa()
    finally:
        _fechar(janela)


def _documento_com_notas_e_paisagem() -> Documento:
    """Secao 1 retrato e secao 2 paisagem (ultima), com uma nota de rodape a cada tres
    paragrafos nas duas."""
    from editdoc.modelo import notas as mn
    from editdoc.modelo.documento import MarcaNota
    pars, notas = [], []
    for i in range(70):
        runs = [Run(f"Parágrafo {i + 1}. " + fx.TEXTO_SECAO * 2)]
        if i % 3 == 0:
            nid = len(notas) + 1
            runs += [Run(marca=MarcaNota("rodape", nid)), Run(" fim.")]
            notas.append(mn.Nota("rodape", nid, (Paragrafo(runs=[
                Run(marca=MarcaNota("rodape", 0, propria=True)),
                Run(f" Nota {nid}. " + "Texto da nota de rodapé. " * 3)]),)))
        pars.append(Paragrafo(runs=runs))
    pars[29].secao = Secao(pagina=Pagina())
    cat = mn.Notas()
    cat.itens["rodape"] = notas
    doc = Documento(paragrafos=pars, pagina=Pagina().com_orientacao(True))
    doc.notas = cat
    return doc


def testar_notas_e_flutuantes() -> None:
    secao("notas de rodape e objeto flutuante na secao paisagem: a area e a posicao da secao")
    janela = _janela(escrever(_documento_com_notas_e_paisagem()))
    try:
        lay = janela.painel.layout_pag
        janela.painel.viewport().grab()
        n1 = lay.secoes.lista[1].inicio
        checa(n1 > 0 and lay.efetiva_da(n1).paisagem, "a secao 2 e' paisagem")
        ruins = []
        for n, fatias in lay.notas.paginas.items():
            pe = n * lay.hb + lay.altura_do_corpo(n)
            if fatias and max(f.y + f.altura for f in fatias) > pe + 0.5:
                ruins.append(n)
        checa(lay.notas.paginas and not ruins,
              "a area de notas de cada folha termina no pe' do corpo da secao dela")
        checa(any(n >= n1 for n in lay.notas.paginas), "ha' notas nas folhas paisagem")
        checa_igual(_linhas_fora(lay), [], "o texto nao passa do corpo (as notas empurram blocos)")
        # Contraprova: a altura de retrato nas folhas paisagem acusa a area passando do pe'.
        original = lay.altura_do_corpo
        lay.altura_do_corpo = lambda _n: 9026.0 if _n >= 0 else 0.0
        try:
            ruins = [n for n, f in lay.notas.paginas.items() if f and n < n1 and
                     max(x.y + x.altura for x in f) > n * lay.hb + 9026.0 + 0.5]
            checa(ruins, "contraprova: com a altura da paisagem no retrato, as notas passam")
        finally:
            del lay.altura_do_corpo
        del original
    finally:
        _fechar(janela)
    # Objeto flutuante relativo a' margem na secao paisagem: x = margem esquerda dela.
    import teste_flutuantes as tf
    emu = 635
    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1701" '
            'w:bottom="1440" w:left="1701" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>')
    corpo = (f"<w:p><w:pPr>{sect}</w:pPr><w:r><w:t>Retrato.</w:t></w:r></w:p>"
             + "<w:p>" + tf.ancora(95, tf.URI_FORMA, tf.forma(2000 * emu, 1000 * emu),
                                   2000 * emu, 1000 * emu, h=("margin", "posOffset", 0),
                                   v=("page", "posOffset", 2000 * emu), quebra="<wp:wrapNone/>")
             + "<w:r><w:t>Paisagem com o objeto.</w:t></w:r></w:p>")
    base = Documento(paragrafos=[Paragrafo(runs=[Run("x")])],
                     pagina=Pagina().com_orientacao(True).com_margens(1134, 1134, 1134, 1134))
    janela = _janela(fx.docx_com_corpo_de_objetos(corpo, (), {}, (), (), documento=base))
    try:
        lay = janela.painel.layout_pag
        from editdoc.ponte_qt import flutuantes as pq_flutuantes
        g = lay.flutuantes
        pos = next(p for p, *_r in g.lista())
        n, (x, y, w, h) = pq_flutuantes.retangulo_de(lay.doc, pos)
        checa(n == 1 and lay.efetiva_da(n).paisagem, "o objeto esta' na folha paisagem")
        checa(abs(x - 1134) < 1 and abs(y - 2000) < 1,
              f"posicao relativa a' margem e a' pagina da secao paisagem ({x:.0f}, {y:.0f})")
        checa(abs(x - 1701) > 100, "contraprova: nao e' a margem da secao de retrato")
    finally:
        _fechar(janela)


def testar_tabela_longa_na_paisagem() -> None:
    secao("tabela longa numa secao paisagem: as linhas que passam do pe' descem de folha")
    from editdoc.modelo.documento import Celula, Linha, Tabela
    from editdoc.ponte_qt import notas as pq_notas
    linhas = [Linha(celulas=[Celula(blocos=[Paragrafo(runs=[Run(f"linha {r} col {c} "
                                                                + "texto " * 8)])])
                             for c in range(4)]) for r in range(80)]
    pars = [Paragrafo(runs=[Run(f"Retrato {i}. " + fx.TEXTO_SECAO)]) for i in range(5)]
    pars[-1].secao = Secao(pagina=Pagina())
    doc = Documento(paragrafos=pars + [Tabela(linhas=linhas, colunas_tw=[3400] * 4),
                                       Paragrafo(runs=[Run("depois")])],
                    pagina=Pagina().com_orientacao(True))
    janela = _janela(escrever(doc))
    try:
        lay = janela.painel.layout_pag
        checa(lay.secoes_baixas(), "a secao paisagem e' mais baixa que a pagina do documento")
        checa_igual(_linhas_fora(lay), [], "nenhuma linha da tabela passa do pe' da folha paisagem")
        tabela = next(f for f in lay.doc.rootFrame().childFrames())
        empurradas = [r for r in range(tabela.rows())
                      if tabela.cellAt(r, 0).format().property(pq_notas.PROP_LINHA_EMPURRADA)]
        checa(len(empurradas) >= 3, f"linhas empurradas: {len(empurradas)} (uma por folha)")
        texto = janela.painel.toPlainText()
        checa(all(f"linha {r} col 3" in texto for r in range(80)), "todo o texto da tabela fica")
        # Contraprova: sem o acolchoamento, as linhas passam do pe' (o conteudo sumiria).
        from PySide6.QtGui import QTextCursor
        c = QTextCursor(lay.doc)
        c.beginEditBlock()
        for r in empurradas:
            for col in range(tabela.columns()):
                cel = tabela.cellAt(r, col)
                fmt = cel.format().toTableCellFormat()
                original = float(str(fmt.property(pq_notas.PROP_LINHA_EMPURRADA)).split(";")[0])
                fmt.setBottomPadding(original)
                fmt.clearProperty(pq_notas.PROP_LINHA_EMPURRADA)
                cel.setFormat(fmt)
        c.endEditBlock()
        checa(_linhas_fora(lay), "contraprova: sem o empurrao, linhas da tabela passam do pe'")
        lay.doc.undo()
        janela.painel.viewport().grab()
        checa_igual(_linhas_fora(lay), [], "desfazer devolve o empurrao (e a tela fica certa)")
    finally:
        _fechar(janela)


def testar_campos_e_copiar() -> None:
    secao("SECTIONPAGES por secao; copiar nao leva a quebra derivada nem o recuo escondido")
    from editdoc.modelo.campos import valor_do_campo
    from editdoc.ponte_qt import estilos as pq_estilos
    janela = _janela(fx.docx_com_secoes())
    try:
        lay = janela.painel.layout_pag
        n1, n2 = lay.secoes.lista[1].inicio, lay.secoes.lista[2].inicio
        indice, pagina, paginas = lay.campos_da_folha(0)
        checa_igual(valor_do_campo("SECTIONPAGES", indice, lay.numero_paginas(), pagina, paginas),
                    str(n1), "SECTIONPAGES na secao 1: as folhas dela")
        indice, pagina, paginas = lay.campos_da_folha(n1)
        checa_igual(valor_do_campo("SECTIONPAGES", indice, lay.numero_paginas(), pagina, paginas),
                    str(n2 - n1), "SECTIONPAGES na secao 2 (com a pagina em branco)")
        checa_igual(valor_do_campo("NUMPAGES", indice, lay.numero_paginas(), pagina, paginas),
                    str(lay.numero_paginas()), "NUMPAGES: o documento inteiro")
        # A secao 1 (retrato) e' mais estreita que a 2 (paisagem): recuo escondido.
        doc = lay.doc
        bloco = doc.findBlockByNumber(2)
        escondido = pq_estilos.recuo_secao(bloco.blockFormat())
        checa(escondido is not None and escondido[0] > 4000,
              "o paragrafo da secao estreita tem o recuo escondido")
        checa_igual(pq_estilos.props_de_bloco(bloco.blockFormat()).get("recuo_direito_tw"), None,
                    "o recuo escondido nao vira recuo do paragrafo")
        from PySide6.QtGui import QTextCursor, QTextDocumentFragment
        from editdoc.interface.painel_documento import _html_sem_espacador
        c = QTextCursor(doc)
        c.setPosition(bloco.position())
        c.setPosition(doc.findBlockByNumber(30).position() + 3, QTextCursor.MoveMode.KeepAnchor)
        html = _html_sem_espacador(QTextDocumentFragment(c))
        checa("margin-right:4" not in html.replace(" ", "") and "page-break-after" not in html,
              "o HTML copiado vem sem o recuo escondido e sem a quebra derivada")
        bruto = QTextDocumentFragment(c).toHtml()
        checa("margin-right" in bruto, "contraprova: o HTML cru do Qt levaria o recuo")
    finally:
        _fechar(janela)


def testar_desempenho() -> None:
    secao("p95 da digitacao num documento de tres secoes, uma paisagem (80 teclas com a pintura)")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest

    ajustes = []

    def p95(docx: bytes) -> float:
        janela = _janela(docx, 1400, 950)
        try:
            painel = janela.painel
            doc = painel.documento_corpo()
            # Na secao paisagem (a mais baixa): o ponto onde o espacador oscilava (0.1.12, antes
            # da correcao: 4,5 ajustes por tecla e 17,5 ms).
            b = doc.firstBlock()
            while b.isValid() and not b.text().startswith("Seção 2, parágrafo 10"):
                b = b.next()
            if not b.isValid():
                b = doc.findBlockByNumber(doc.blockCount() // 3)
            c = QTextCursor(doc)
            c.setPosition(b.position() + 6)
            painel.setTextCursor(c)
            painel.viewport().grab()
            for _ in range(5):
                QTest.keyClick(painel, Qt.Key.Key_A)
                painel.viewport().grab()
            antes = painel.layout_pag.notas.ajustes
            tempos = []
            for _ in range(80):
                t = time.perf_counter()
                QTest.keyClick(painel, Qt.Key.Key_A)
                painel.viewport().grab()
                tempos.append((time.perf_counter() - t) * 1000)
            ajustes.append(painel.layout_pag.notas.ajustes - antes)
            tempos.sort()
            return tempos[round(0.95 * 79)]
        finally:
            _fechar(janela)
            drenar_eventos()

    com = fx.docx_com_secoes(paragrafos_1=60, paragrafos_2=30, paragrafos_3=60)
    simples = fx.bytes_de(_documento_simples(150))
    for _tentativa in range(2):
        ref = p95(simples)
        medido = p95(com)
        limite = max(16.0, ref * 2.5 + 2.0)
        if medido <= limite:
            break
    print(f"         p95 com 3 secoes {medido:.1f} ms; uma secao {ref:.1f} ms")
    checa(ajustes[-1] <= 20, f"80 teclas na secao paisagem: {ajustes[-1]} ajustes de espacador "
                             "(oscilava: 361 antes da correcao)")
    checa(medido <= limite, f"p95 {medido:.1f} ms no gate (16 ms) ou ate' 2,5x o documento de uma "
                            f"secao ({ref:.1f} ms)")


def main() -> int:
    testar_leitura()
    testar_ida_e_volta_c14n()
    testar_continua_e_colunas()
    testar_validador()
    testar_hostil()
    testar_mudanca_no_modelo()
    if not QT:
        return pular("PySide6 nao instalado") or resumir()
    usar_fonte_windows()
    usar_fontes_do_documento()
    testar_tela()
    testar_continua_na_tela()
    testar_pdf()
    testar_salvar_reabrir()
    testar_inserir_e_apagar()
    testar_documento_inteiro_e_vinculo()
    testar_notas_e_flutuantes()
    testar_tabela_longa_na_paisagem()
    testar_campos_e_copiar()
    testar_desempenho()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
