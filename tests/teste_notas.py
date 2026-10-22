"""Notas de rodape e de fim (0.1.10): arquivo, numeracao, pagina, edicao, PDF, .txt e limites.

Fixtures geradas aqui e em `fixtures_docx.py` (nenhum documento real): duas notas de rodape,
uma de fim, uma com marca personalizada ("*") e uma com link e imagem; reinicio por pagina com
romanos; formato chicago; nota longa que passa da pagina; documento sem footnotes.xml.

- arquivo: ler sem aviso; sem mudanca, footnotes.xml, endnotes.xml e settings.xml voltam iguais
  (c14n) e a imagem da nota volta com os mesmos bytes; nota editada e nova geradas com ids
  unicos, separadoras e o settings.xml citando-as; propriedades do sectPr voltam; o validador
  confere referencias e notas (com contraprovas); conferencia pos-gravacao;
- numeracao: continua, por pagina, romano, chicago, inicio, marca personalizada fora da conta;
- pagina: a nota fica na pagina da referencia, o corpo encolhe (espacador), nada se sobrepoe;
  a nota longa continua na pagina seguinte com o separador de continuacao; nota de fim depois
  do texto; numero por pagina na tela;
- edicao: Alt+Ctrl+F e Alt+Ctrl+D com teclas reais, digitar na nota, Esc; um desfazer volta a
  nota e a marca; apagar a marca apaga a nota (e o desfazer devolve); duplo clique na marca e no
  numero; proxima nota; opcoes (reinicio e formato) e converter; copiar e colar leva a nota;
- PDF com a nota no pe' da pagina da referencia; .txt com as notas no fim;
- limites contra arquivo hostil; p95 da digitacao num documento com 100 notas.
"""

from __future__ import annotations

import time

from ajudantes import (checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao,
                       usar_fonte_windows, usar_fontes_do_documento)
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx import notas as fx_notas  # noqa: E402
from editdoc.formato_docx.escritor import escrever, escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo import notas as mn  # noqa: E402
from editdoc.modelo.documento import (Documento, MarcaNota, Paragrafo, Run,  # noqa: E402
                                      paragrafos_de)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def c14n(dados: bytes) -> bytes:
    return etree.tostring(etree.fromstring(dados), method="c14n")


def codigos(avisos) -> dict:
    return {a.codigo: (a.contagem, a.perde_ao_salvar) for a in avisos}


def _sem_ruido(problemas: list) -> list:
    """O styles.xml de exemplo do Word (fixtures) tem rPrChange e numId de proposito."""
    return [p for p in problemas if not p.startswith("word/styles.xml")]


def _marcas(doc) -> list:
    return [r.marca for p in paragrafos_de(doc.paragrafos) for r in p.runs
            if isinstance(r.marca, MarcaNota)]


# -- arquivo ----------------------------------------------------------------------------------

def testar_leitura() -> None:
    secao("leitura: notas, referencias, marca personalizada, link e imagem")
    modelo, avisos = ler(fx.docx_com_notas())
    checa("NOTA" not in codigos(avisos), f"nenhum aviso NOTA (avisos: {codigos(avisos)})")
    cat = modelo.notas
    checa_igual([n.id for n in cat.itens["rodape"]], [1, 2, 3, 4], "quatro notas de rodape lidas")
    checa_igual([n.id for n in cat.itens["fim"]], [1], "uma nota de fim lida")
    checa_igual([e.tipo_nota for e in cat.especiais["rodape"]],
                ["separator", "continuationSeparator"], "as separadoras ficam a parte")
    checa("Primeira nota de rodapé." in cat.obter("rodape", 1).texto(), "texto da nota 1")
    marcas = _marcas(modelo)
    checa_igual([(m.tipo, m.id) for m in marcas],
                [("rodape", 1), ("rodape", 2), ("fim", 1), ("rodape", 3), ("rodape", 4)],
                "as referencias ficam no fluxo, na ordem do texto")
    m3 = marcas[3]
    checa(m3.personalizada and mn.texto_do_simbolo(m3.simbolo) == "*",
          "a marca personalizada guarda o simbolo do run seguinte")
    texto = "".join(r.texto for p in paragrafos_de(modelo.paragrafos) for r in p.runs)
    checa("Marca personalizada no fim." in texto, "o run do simbolo nao vira texto solto")
    propria = [r.marca for p in paragrafos_de(list(cat.obter("rodape", 1).paragrafos))
               for r in p.runs if isinstance(r.marca, MarcaNota)]
    checa(propria and propria[0].propria, "o w:footnoteRef vira o numero da propria nota")
    n4 = cat.obter("rodape", 4)
    checa(n4.original is not None and any(r[1].endswith("/image") and r[4] for r in n4.relacoes),
          "a nota com link e imagem volta com o XML de origem e os bytes da imagem")
    checa(any(r.imagem is not None for p in paragrafos_de(list(n4.paragrafos)) for r in p.runs),
          "a imagem da nota e' lida como imagem")
    checa(any(r.link is not None and r.link.url == "https://exemplo.invalid/nota"
              for p in paragrafos_de(list(n4.paragrafos)) for r in p.runs),
          "o link da nota e' lido")


def testar_ida_e_volta() -> None:
    secao("ida e volta: sem mudanca, as partes voltam iguais (c14n)")
    origem = fx.docx_com_notas()
    modelo, _ = ler(origem)
    dados, avisos = escrever_com_avisos(modelo)
    o, g = fx.partes_de(origem), fx.partes_de(dados)
    for nome in ("word/footnotes.xml", "word/endnotes.xml", "word/settings.xml"):
        checa(c14n(o[nome]) == c14n(g[nome]), f"{nome} volta igual (c14n)")
    checa_igual(avisos, [], "a gravacao nao avisa nada")
    rels = etree.fromstring(g["word/_rels/footnotes.xml.rels"])
    alvos = {r.get("Id"): r.get("Target") for r in rels}
    checa(alvos.get("rId1") == "https://exemplo.invalid/nota", "o link mantem o Id rId1")
    checa("rId2" in alvos and g.get("word/" + alvos["rId2"]) == o["word/media/nota1.png"],
          "a imagem da nota mantem o Id e os bytes")
    checa_igual(_sem_ruido(ordem.validar(g)), [], "o pacote gravado passa no validador")
    conferencia.conferir(dados, modelo)
    checa(True, "a conferencia pos-gravacao aceita")
    relido, avisos2 = ler(dados)
    checa("NOTA" not in codigos(avisos2) and len(relido.notas.todas()) == 5,
          "relido: as cinco notas, sem aviso")
    checa_igual(_marcas(relido), _marcas(modelo), "relido: as mesmas referencias")
    # Idempotencia: a segunda gravacao e' igual a primeira.
    dados2 = escrever(relido)
    g2 = fx.partes_de(dados2)
    checa(all(c14n(g[n]) == c14n(g2[n]) for n in ("word/footnotes.xml", "word/endnotes.xml",
                                                   "word/document.xml")),
          "regravar o relido da' as mesmas partes")


def testar_editada_e_nova() -> None:
    secao("nota editada, nota nova e documento sem footnotes.xml")
    from dataclasses import replace
    modelo, _ = ler(fx.docx_com_notas())
    n2 = modelo.notas.obter("rodape", 2)
    nova = replace(n2, original=None, paragrafos=(Paragrafo(estilo="Textodenotaderodap", runs=[
        Run(marca=MarcaNota("rodape", 0, propria=True), estilo="Refdenotaderodap"),
        Run(" Editada.")]),))
    modelo.notas.itens["rodape"][1] = nova
    dados = escrever(modelo)
    g = fx.partes_de(dados)
    raiz = etree.fromstring(g["word/footnotes.xml"])
    ids = [n.get(f"{{{W}}}id") for n in raiz.findall(f"{{{W}}}footnote")]
    checa_igual(ids, ["-1", "0", "1", "2", "3", "4"], "ids unicos, separadoras primeiro")
    o = fx.partes_de(fx.docx_com_notas())
    origem = {n.get(f"{{{W}}}id"): n for n in etree.fromstring(o["word/footnotes.xml"])}
    for n in raiz.findall(f"{{{W}}}footnote"):
        ident = n.get(f"{{{W}}}id")
        if ident != "2":
            checa(etree.tostring(n, method="c14n") == etree.tostring(origem[ident], method="c14n"),
                  f"a nota {ident}, que nao mudou, volta igual (c14n)")
    checa("Editada." in "".join(raiz.find(f"{{{W}}}footnote[@{{{W}}}id='2']").itertext()),
          "a nota editada e' gerada de novo")
    checa_igual(_sem_ruido(ordem.validar(g)), [], "valido depois da edicao")
    conferencia.conferir(dados, modelo)
    checa(True, "conferencia da nota editada")

    # Documento sem footnotes.xml que ganha a primeira nota.
    doc = Documento(paragrafos=[Paragrafo(runs=[Run("Texto"), Run(marca=MarcaNota("rodape", 1)),
                                                Run(" e fim"), Run(marca=MarcaNota("fim", 1))])])
    cat = mn.Notas()
    cat.itens["rodape"] = [mn.Nota("rodape", 1, (Paragrafo(runs=[
        Run(marca=MarcaNota("rodape", 0, propria=True)), Run(" Nova de rodapé.")]),))]
    cat.itens["fim"] = [mn.Nota("fim", 1, (Paragrafo(runs=[
        Run(marca=MarcaNota("fim", 0, propria=True)), Run(" Nova de fim.")]),))]
    doc.notas = cat
    dados = escrever(doc)
    g = fx.partes_de(dados)
    checa("word/footnotes.xml" in g and "word/endnotes.xml" in g, "as duas partes sao criadas")
    ct = g["[Content_Types].xml"].decode("utf-8")
    checa(fx_notas.CT_NOTAS["rodape"] in ct and fx_notas.CT_NOTAS["fim"] in ct,
          "Override das duas partes")
    cfg = etree.fromstring(g["word/settings.xml"])
    checa_igual([e.get(f"{{{W}}}id") for e in cfg.iter(f"{{{W}}}footnote")], ["-1", "0"],
                "o settings.xml cita as separadoras criadas")
    tipos = [n.get(f"{{{W}}}type") for n in etree.fromstring(g["word/footnotes.xml"])]
    checa_igual(tipos, ["separator", "continuationSeparator", None], "separadoras e a nota")
    checa_igual(_sem_ruido(ordem.validar(g)), [], "o pacote novo passa no validador")
    relido, avisos = ler(dados)
    checa(avisos == [] and [n.texto().strip() for n in relido.notas.todas()]
          == ["Nova de rodapé.", "Nova de fim."], "relido sem aviso, com as duas notas")
    conferencia.conferir(dados, doc)
    checa(True, "conferencia do documento novo")

    # Apagar a referencia apaga a nota.
    sem = Documento(paragrafos=[Paragrafo(runs=[Run("Texto sem marca")])])
    sem.notas = cat
    g = fx.partes_de(escrever(sem))
    checa("word/footnotes.xml" not in g or etree.fromstring(g["word/footnotes.xml"]).find(
        f"{{{W}}}footnote[@{{{W}}}id='1']") is None, "a nota sem referencia nao e' gravada")


def testar_propriedades() -> None:
    secao("propriedades: footnotePr do sectPr e do settings.xml")
    sect = ('<w:footnotePr><w:pos w:val="beneathText"/><w:numFmt w:val="lowerRoman"/>'
            '<w:numStart w:val="3"/><w:numRestart w:val="eachPage"/></w:footnotePr>'
            '<w:endnotePr><w:numFmt w:val="chicago"/></w:endnotePr>')
    origem = fx.docx_com_notas(sect_xml=sect)
    modelo, avisos = ler(origem)
    pr = modelo.notas.propriedades("rodape")
    checa_igual((pr.formato, pr.inicio, pr.reinicio, pr.posicao),
                ("lowerRoman", 3, "eachPage", "beneathText"), "propriedades do rodape lidas")
    checa_igual(modelo.notas.propriedades("fim").formato, "chicago", "nota de fim em chicago")
    checa_igual(modelo.notas.propriedades("fim").posicao, "docEnd", "o resto e' o padrao do Word")
    g = fx.partes_de(escrever(modelo))
    sect_g = etree.fromstring(g["word/document.xml"]).find(f".//{{{W}}}sectPr")
    sect_o = etree.fromstring(fx.partes_de(origem)["word/document.xml"]).find(f".//{{{W}}}sectPr")
    for local in ("footnotePr", "endnotePr"):
        checa(etree.tostring(sect_g.find(f"{{{W}}}{local}"), method="c14n")
              == etree.tostring(sect_o.find(f"{{{W}}}{local}"), method="c14n"),
              f"{local} do sectPr volta igual (c14n)")
    checa_igual(_sem_ruido(ordem.validar(g)), [], "sectPr na ordem do esquema")
    modelo.notas.secao["rodape"] = mn.PropriedadesNota("upperLetter", 1, "continuous", None)
    g = fx.partes_de(escrever(modelo))
    relido, _ = ler(fx.montar(g))
    pr = relido.notas.propriedades("rodape")
    checa_igual((pr.formato, pr.inicio, pr.reinicio), ("upperLetter", 1, "continuous"),
                "a propriedade trocada volta pelo arquivo")
    ruim = fx.docx_com_notas(sect_xml='<w:footnotePr><w:numRestart w:val="sempre"/></w:footnotePr>')
    _m, av = ler(ruim)
    checa("FORMATACAO" in codigos(av), "valor fora do esquema sai com aviso FORMATACAO")


def testar_numeracao() -> None:
    secao("numeracao: continua, por pagina, romano, chicago, inicio, personalizada")
    refs = [("rodape", 1, False), ("rodape", 2, False), ("rodape", 3, True), ("rodape", 4, False),
            ("fim", 1, False), ("fim", 2, False)]
    props = {"rodape": mn.efetivas("rodape"), "fim": mn.efetivas("fim")}
    n = mn.numeros(refs, props)
    checa_igual([n.get(("rodape", i)) for i in (1, 2, 3, 4)], ["1", "2", None, "3"],
                "continua; a personalizada nao conta")
    checa_igual([n[("fim", 1)], n[("fim", 2)]], ["i", "ii"], "nota de fim em romano minusculo")
    props["rodape"] = mn.efetivas("rodape", mn.PropriedadesNota("upperRoman", 4, "eachPage"))
    n = mn.numeros(refs, props, {("rodape", 1): 0, ("rodape", 2): 0, ("rodape", 4): 1})
    checa_igual([n[("rodape", 1)], n[("rodape", 2)], n[("rodape", 4)]], ["IV", "V", "IV"],
                "reinicio por pagina, comecando em 4, romano maiusculo")
    checa_igual([mn.formatar(i, "chicago") for i in (1, 2, 4, 5, 9)],
                ["*", "†", "§", "**", "***"], "chicago: simbolos, depois dobrados")
    checa_igual([mn.formatar(i, "lowerLetter") for i in (1, 26, 27)], ["a", "z", "aa"], "letras")
    checa_igual(mn.formatar(5, "formatoQueNaoExiste"), "5", "formato desconhecido: decimal")


def testar_validador() -> None:
    secao("validador: contraprovas")
    modelo, _ = ler(fx.docx_com_notas())
    g = fx.partes_de(escrever(modelo))
    checa_igual(fx_notas.validar(g), [], "o arquivo gravado passa")

    def com(nome, de, para):
        h = dict(g)
        h[nome] = h[nome].replace(de, para)
        return fx_notas.validar(h)

    checa(any("nao e' nota normal" in p for p in com(
        "word/document.xml", b'w:footnoteReference w:id="2"', b'w:footnoteReference w:id="9"')),
        "contraprova: referencia a nota que nao existe")
    checa(any("sem footnoteReference" in p for p in com(
        "word/footnotes.xml", b"</w:footnotes>",
        b'<w:footnote w:id="7"><w:p/></w:footnote></w:footnotes>')),
        "contraprova: nota sem referencia")
    checa(any("repetido" in p for p in com(
        "word/footnotes.xml", b"</w:footnotes>",
        b'<w:footnote w:id="1"><w:p/></w:footnote></w:footnotes>')),
        "contraprova: id repetido")
    checa(any("nao existe" in p for p in com(
        "word/settings.xml", b'<w:footnote w:id="0"/>', b'<w:footnote w:id="0"/><w:footnote w:id="5"/>')),
        "contraprova: settings.xml cita especial que nao existe")
    checa(any("footnoteRef" in p for p in com(
        "word/document.xml", b"<w:t>Outra</w:t>", b"<w:t>Outra</w:t></w:r><w:r><w:footnoteRef/>")),
        "contraprova: numero de nota no corpo")
    checa(any("mais de uma referencia" in p for p in com(
        "word/document.xml", b'w:footnoteReference w:id="2"', b'w:footnoteReference w:id="1"')),
        "contraprova: duas referencias a mesma nota")


def testar_avisos_e_limites() -> None:
    secao("avisos e limites: nota sem referencia, referencia no cabecalho, arquivo hostil")
    extra = fx.nota_xml(9, "Nota sem referência.")
    modelo, avisos = ler(fx.docx_com_notas(notas_xml=fx.NOTAS_RODAPE_XML + extra))
    checa(codigos(avisos).get("NOTA") == (1, True) and modelo.notas.obter("rodape", 9) is None,
          "nota sem referencia no corpo: aviso NOTA (com perda) e sai")
    corpo_ruim = fx.CORPO_COM_NOTAS.replace(fx.ref_nota(2), fx.ref_nota(2) + fx.ref_nota(2))
    modelo, avisos = ler(fx.docx_com_notas(corpo_xml=corpo_ruim))
    checa(codigos(avisos).get("NOTA") == (1, True) and len(_marcas(modelo)) == 5,
          "segunda referencia a mesma nota: sai, com aviso")
    inicio = time.perf_counter()
    muitas = "".join(fx.nota_xml(i, f"n{i}") for i in range(1, 12))
    corpo = "<w:p>" + "".join(fx.ref_nota(i) for i in range(1, 12)) + "</w:p>"
    from editdoc.formato_docx.leitor import ler as ler_lim
    modelo, avisos = ler_lim(fx.docx_com_notas(corpo_xml=corpo, notas_xml=muitas, rels_notas=None),
                             {"notas": 10})
    g = fx.partes_de(escrever(modelo))
    tipos = [n.get(f"{{{W}}}type") for n in etree.fromstring(g["word/footnotes.xml"])]
    checa(codigos(avisos).get("NOTA", (0,))[0] >= 11 and tipos == ["separator", "continuationSeparator"]
          and time.perf_counter() - inicio < 2,
          "acima do limite de notas: a parte fica so' com as separadoras, com aviso, rapido")
    checa_igual(_sem_ruido(ordem.validar(g)), [], "e o arquivo continua valido")
    grande = fx.nota_xml(1, "x" * 2000)
    _m, avisos = ler_lim(fx.docx_com_notas(corpo_xml="<w:p>" + fx.ref_nota(1) + "</w:p>",
                                           notas_xml=grande, rels_notas=None, notas_fim_xml=None),
                         {"nota_bytes": 1000})
    checa(codigos(avisos).get("NOTA") == (2, True), "nota grande demais: nao e' lida, com aviso")
    profundo = fx.nota_xml(1, "a", extra="<w:customXml>" * 400 + "</w:customXml>" * 400)
    inicio = time.perf_counter()
    modelo, avisos = ler(fx.docx_com_notas(corpo_xml="<w:p>" + fx.ref_nota(1) + "</w:p>",
                                           notas_xml=profundo, rels_notas=None,
                                           notas_fim_xml=None))
    g = fx.partes_de(escrever(modelo))
    checa(codigos(avisos).get("NOTA", (0, False))[1] and not _marcas(modelo)
          and time.perf_counter() - inicio < 2,
          "nota aninhada fundo demais: a parte nao e' lida (aviso, sem travar)")
    checa_igual(_sem_ruido(ordem.validar(g)), [], "e o arquivo gravado continua valido")


# -- tela -------------------------------------------------------------------------------------

TEXTO = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor "
         "incididunt ut labore et dolore magna aliqua. ")


def documento_com_notas(paragrafos: int = 60, cada: int = 3, longa: int | None = None,
                        fim: int = 0) -> Documento:
    pars = []
    notas = []
    notas_fim = []
    for i in range(paragrafos):
        runs = [Run(f"Parágrafo {i}. " + TEXTO * 3)]
        if i % cada == 0:
            nid = len(notas) + 1
            runs += [Run(marca=MarcaNota("rodape", nid)), Run(" fim.")]
            repeticoes = 400 if nid == longa else 2
            notas.append(mn.Nota("rodape", nid, (Paragrafo(runs=[
                Run(marca=MarcaNota("rodape", 0, propria=True)),
                Run(f" Nota {nid}. " + "Texto da nota. " * repeticoes)]),)))
        if fim and i < fim:
            runs += [Run(marca=MarcaNota("fim", i + 1))]
            notas_fim.append(mn.Nota("fim", i + 1, (Paragrafo(runs=[
                Run(marca=MarcaNota("fim", 0, propria=True)),
                Run(f" Nota de fim {i + 1}. " + "Comentário final. " * 30)]),)))
        pars.append(Paragrafo(runs=runs))
    cat = mn.Notas()
    cat.itens["rodape"] = notas
    cat.itens["fim"] = notas_fim
    doc = Documento(paragrafos=pars)
    doc.notas = cat
    return doc


def _janela(modelo: Documento, largura: int = 1100, altura: int = 900):
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    janela = JanelaPrincipal(configuracao.padrao())
    janela.resize(largura, altura)
    janela.show()
    janela.carregar(modelo, [], None)
    janela.painel.setFocus()
    drenar_eventos()
    janela.painel.viewport().grab()
    return janela


def _fechar(janela) -> None:
    janela.painel.sair_da_faixa()
    janela.painel.documento_corpo().setModified(False)
    janela.close()
    drenar_eventos()


def _sobreposicoes(layout) -> list:
    """Paginas onde a ultima linha do corpo passa do topo da area de notas."""
    g = layout.notas
    hb = layout.hb
    from editdoc.ponte_qt import notas as pq
    med = g._medir(pq.catalogo(layout.doc))
    ruins = []
    for k, fatias in g.paginas.items():
        linhas = g._linhas_da_pagina(med, k)
        fim = max((b for _t, b, _u in linhas), default=k * hb)
        if fatias and fim > min(f.y for f in fatias) + 0.5:
            ruins.append(k)
        if fatias and max(f.y + f.altura for f in fatias) > (k + 1) * hb + 0.5:
            ruins.append(k)
    return ruins


def testar_pagina() -> None:
    secao("pagina: a nota no pe' da pagina da referencia, o corpo encolhe, nada se sobrepoe")
    from editdoc.ponte_qt import notas as pq
    janela = _janela(documento_com_notas(longa=7, fim=2))
    try:
        layout = janela.painel.layout_pag
        g = layout.notas
        hb = layout.hb
        checa(g.paginas, "ha' area de notas")
        checa_igual(_sobreposicoes(layout), [], "o corpo nunca entra na area de notas")
        med = g._medir(pq.catalogo(layout.doc))
        fora = []
        for m, t, _b in med.refs:
            # As notas depois da longa esperam a continuacao dela (como no Word).
            if m.tipo != "rodape" or m.id >= 7:
                continue
            k = int(t // hb)
            fatias = g.fatias_de(med.docs[(m.tipo, m.id)])
            if not fatias or fatias[0][0] != k:
                fora.append((m.id, k, fatias[0][0] if fatias else None))
        checa_igual(fora, [], "cada nota de rodape (antes da longa) comeca na pagina da referencia")
        espacadores = [u for u in med.unidades if u.espacador()]
        checa(espacadores, f"o corpo encolhe: {len(espacadores)} bloco(s) empurrados pela area")
        # Contraprova do encolhimento: sem as notas, o mesmo bloco caberia na pagina de antes.
        u = espacadores[0]
        k = int(u.topo // hb)
        checa(med.unidades[u.indice - 1].base < k * hb, "o bloco empurrado comeca numa pagina nova")
        d7 = med.docs[("rodape", 7)]
        partes = g.fatias_de(d7)
        checa(len(partes) >= 2 and partes[1][0] == partes[0][0] + 1,
              f"a nota longa continua na pagina seguinte ({[p[0] for p in partes]})")
        checa(any(f.tipo == "continuacao" for f in g.paginas[partes[1][0]]),
              "com o separador de continuacao (largura toda)")
        checa(abs(sum(f.altura for _n, f in partes) - d7.altura()) < 1,
              "os pedacos somam a nota inteira, cortada numa linha")
        fim_paginas = [n for n, fs in g.paginas.items() for f in fs if f.classe == "fim"]
        checa(fim_paginas and min(fim_paginas) >= layout.paginas_do_texto() - 1,
              "as notas de fim vem depois do texto")
        checa(layout.numero_paginas() >= layout.paginas_do_texto(),
              f"paginas a mais contam no total ({g.extras} a mais)")
        numeros = layout.doc._numeros_notas
        checa_igual((numeros[("rodape", 1)], numeros[("fim", 1)]), ("1", "i"),
                    "numero continuo na tela: 1 no rodape, i no fim")
        # Pixels: a area de notas tem tinta e o separador aparece na pagina da primeira nota.
        from PySide6.QtGui import QImage, QPainter, QTransform
        from editdoc.interface.notas import desenhar_notas
        ef = layout.efetiva_da(0)
        img = QImage(int(ef.largura_tw / 15), int(ef.altura_tw / 15), QImage.Format.Format_RGB32)
        img.fill(0xFFFFFFFF)
        p = QPainter(img)
        desenhar_notas(p, layout, 0, QTransform().scale(1 / 15, 1 / 15))
        p.end()
        topo = min(f.y for f in g.paginas[0])
        y_px = int((ef.margem_sup_tw + topo) / 15)
        escuros = sum(1 for y in range(y_px, img.height()) for x in range(0, img.width(), 2)
                      if img.pixelColor(x, y).lightness() < 128)
        acima = sum(1 for y in range(0, max(0, y_px - 2)) for x in range(0, img.width(), 2)
                    if img.pixelColor(x, y).lightness() < 128)
        checa(escuros > 50 and acima == 0, f"a nota e' pintada so' na area dela ({escuros} px)")
        # Contraprova: sem os espacadores, a mesma distribuicao poe a nota em cima do texto.
        from PySide6.QtGui import QTextCursor
        for u in espacadores:
            if u.bloco is not None:
                QTextCursor(u.bloco).setBlockFormat(pq.sem_espacador(u.bloco.blockFormat()))
        cat = pq.catalogo(layout.doc)
        g._distribuir(g._medir(cat), g._altura_separador(),
                      {t: cat.propriedades(t) for t in mn.TIPOS})
        med = g._medir(cat)
        adiadas = [m.id for m, t, _b in med.refs if m.tipo == "rodape" and m.id < 7
                   and (not g.fatias_de(med.docs[(m.tipo, m.id)])
                        or g.fatias_de(med.docs[(m.tipo, m.id)])[0][0] != int(t // hb))]
        checa(adiadas, f"contraprova: sem o espacador, notas saem da pagina da referencia "
                       f"({adiadas})")
        checa_igual(_sobreposicoes(layout), [], "e mesmo assim nada se sobrepoe (a nota continua)")
        k0 = min(g.paginas)
        g.paginas[k0][0].y -= hb / 2
        checa(_sobreposicoes(layout), "contraprova da conferencia: nota em cima do texto e' acusada")
        layout.doc.undo()
    finally:
        _fechar(janela)


def testar_reinicio_por_pagina_na_tela() -> None:
    secao("numero por pagina e formato na tela")
    modelo = documento_com_notas(paragrafos=30)
    modelo.notas.secao = {"rodape": mn.PropriedadesNota("lowerRoman", None, "eachPage")}
    janela = _janela(modelo)
    try:
        layout = janela.painel.layout_pag
        from editdoc.ponte_qt import notas as pq
        med = layout.notas._medir(pq.catalogo(layout.doc))
        por_pagina: dict = {}
        for m, t, _b in med.refs:
            por_pagina.setdefault(int(t // layout.hb), []).append(layout.doc._numeros_notas[
                (m.tipo, m.id)])
        checa(len(por_pagina) >= 2 and all(v[0] == "i" for v in por_pagina.values()),
              f"cada pagina recomeca em i ({por_pagina})")
        d = med.docs[med.refs[1][0].tipo, med.refs[1][0].id]
        checa_igual(d.doc._numero_da_nota, "ii", "o numero dentro da nota segue a referencia")
    finally:
        _fechar(janela)


def _teclar(painel, texto: str) -> None:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    for ch in texto:
        QApplication.sendEvent(painel, QKeyEvent(QEvent.Type.KeyPress, 0,
                                                 Qt.KeyboardModifier.NoModifier, ch))
        QApplication.sendEvent(painel, QKeyEvent(QEvent.Type.KeyRelease, 0,
                                                 Qt.KeyboardModifier.NoModifier, ch))


def testar_edicao() -> None:
    secao("edicao: Alt+Ctrl+F, digitar na nota, Esc, desfazer, apagar a marca, duplo clique")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest
    from editdoc.ponte_qt import notas as pq
    janela = _janela(Documento(paragrafos=[Paragrafo(runs=[Run("Primeiro parágrafo.")]),
                                           Paragrafo(runs=[Run("Segundo.")])]))
    try:
        painel = janela.painel
        doc = painel.documento_corpo()
        c = QTextCursor(doc)
        c.setPosition(len("Primeiro"))
        painel.setTextCursor(c)
        QTest.keyClick(painel, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.AltModifier)
        drenar_eventos()
        checa(painel.editando_nota() is not None, "Alt+Ctrl+F insere a nota e entra nela")
        _teclar(painel, "Explicação")
        painel.viewport().grab()
        QTest.keyClick(painel, Qt.Key.Key_Escape)
        drenar_eventos()
        checa(painel.editando_nota() is None, "Esc volta ao corpo")
        cat = pq.catalogo(doc)
        checa_igual([n.texto().strip() for n in cat.itens["rodape"]], ["Explicação"],
                    "o texto digitado esta' na nota")
        refs = pq.referencias(doc)
        checa_igual([(p, m.tipo, m.id) for p, m in refs], [(8, "rodape", 1)],
                    "a marca entrou no cursor")
        estilos = __import__("editdoc.ponte_qt.estilos", fromlist=["x"]).catalogo(doc)
        checa(estilos.por_nome("footnote text") is not None and
              estilos.por_nome("footnote reference") is not None,
              "os estilos de nota foram criados")
        checa("1" == doc._numeros_notas[("rodape", 1)], "a marca mostra 1")
        # Um desfazer volta o texto da nota; o outro, a nota inteira.
        painel.undo()
        drenar_eventos()
        checa_igual([n.texto().strip() for n in pq.catalogo(doc).itens["rodape"]], [""],
                    "desfazer: o texto digitado sai da nota (a edicao e' um passo)")
        painel.undo()
        drenar_eventos()
        checa(not pq.referencias(doc), "desfazer de novo: a marca sai")
        painel.redo()
        painel.redo()
        drenar_eventos()
        checa(pq.referencias(doc) and [n.texto().strip() for n in pq.catalogo(doc).itens["rodape"]]
              == ["Explicação"], "refazer duas vezes devolve a nota e o texto")
        # Alt+Ctrl+D: nota de fim.
        c = QTextCursor(doc)
        c.movePosition(QTextCursor.MoveOperation.End)
        painel.setTextCursor(c)
        QTest.keyClick(painel, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.AltModifier)
        _teclar(painel, "Fim")
        QTest.keyClick(painel, Qt.Key.Key_Escape)
        drenar_eventos()
        checa_igual(doc._numeros_notas.get(("fim", 1)), "i", "Alt+Ctrl+D: nota de fim numerada i")
        # Duplo clique na marca leva a nota; no numero da nota, de volta.
        painel.viewport().grab()
        from editdoc.edicao import notas as ed
        checa(ed.ir_para_nota(painel, "rodape", 1) and painel.editando_nota() is not None,
              "ir para a nota")
        checa(ed.ir_para_referencia(painel, "rodape", 1) and painel.editando_nota() is None
              and painel.textCursor().position() == 9, "voltar a referencia")
        r = painel.layout_pag.retangulo_cursor(8)
        m = painel.mapa()
        x, y = m.doc_para_tela(r.x() + 2, r.center().y(), painel.total_de_paginas())
        from PySide6.QtCore import QPoint
        QTest.mouseDClick(painel.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier(0),
                          QPoint(int(x), int(y)))
        drenar_eventos()
        checa(painel.editando_nota() is not None, "duplo clique na marca: edita a nota")
        painel.sair_da_faixa()
        # Proxima nota.
        c = QTextCursor(doc)
        c.setPosition(0)
        painel.setTextCursor(c)
        checa(ed.proxima(painel) and painel.textCursor().selectionStart() == 8, "proxima nota")
        checa(ed.proxima(painel) and painel.textCursor().selectionStart() > 8,
              "a seguinte (a de fim)")
        # Apagar a marca apaga a nota ao salvar; desfazer devolve.
        c = QTextCursor(doc)
        c.setPosition(9)
        painel.setTextCursor(c)
        QTest.keyClick(painel, Qt.Key.Key_Backspace)
        drenar_eventos()
        modelo = janela._modelo_atual()
        g = fx.partes_de(escrever(modelo))
        checa("word/footnotes.xml" not in g or etree.fromstring(g["word/footnotes.xml"]).find(
            f"{{{W}}}footnote[@{{{W}}}id='1']") is None, "Backspace na marca: a nota sai do arquivo")
        painel.undo()
        drenar_eventos()
        modelo = janela._modelo_atual()
        dados = escrever(modelo)
        relido, avisos = ler(dados)
        checa(relido.notas is not None and [n.texto().strip() for n in relido.notas.itens["rodape"]]
              == ["Explicação"] and not avisos, "desfazer devolve a nota, que volta a ser gravada")
        conferencia.conferir(dados, modelo)
        checa(True, "a conferencia aceita o arquivo da nota inserida")
    finally:
        _fechar(janela)


def testar_opcoes_e_converter() -> None:
    secao("opcoes (formato, reinicio) e converter rodape <-> fim")
    from editdoc.ponte_qt import notas as pq
    janela = _janela(documento_com_notas(paragrafos=9))
    try:
        doc = janela.painel.documento_corpo()
        janela._pedir_opcoes_notas = lambda props, cont, tipo: {
            "tipo": "rodape", "converter": None,
            "pr": mn.PropriedadesNota("upperLetter", 5, "continuous", "pageBottom")}
        checa(janela.opcoes_notas(), "opcoes aplicadas")
        drenar_eventos()
        checa_igual(doc._numeros_notas[("rodape", 1)], "E", "formato e inicio novos na tela")
        janela.painel.undo()
        drenar_eventos()
        janela.painel.layout_pag.atualizar_notas()
        checa_igual(doc._numeros_notas[("rodape", 1)], "1", "um desfazer volta as opcoes")
        janela._pedir_opcoes_notas = lambda props, cont, tipo: {
            "tipo": "rodape", "converter": "rodape", "pr": props["rodape"]}
        checa(janela.opcoes_notas(), "converter")
        refs = pq.referencias(doc)
        checa(refs and all(m.tipo == "fim" for _p, m in refs), "todas as notas viraram de fim")
        modelo = janela._modelo_atual()
        dados = escrever(modelo)
        relido, _ = ler(dados)
        checa(not relido.notas.itens["rodape"] and len(relido.notas.itens["fim"]) == 3,
              "o arquivo grava as notas de fim")
        conferencia.conferir(dados, modelo)
        checa(True, "conferencia depois de converter")
    finally:
        _fechar(janela)


def testar_copiar_colar() -> None:
    secao("copiar e colar dentro do EditDoc leva a nota (com id novo)")
    from PySide6.QtGui import QTextCursor
    from editdoc.ponte_qt import notas as pq
    modelo, _ = ler(fx.docx_com_notas())
    janela = _janela(modelo)
    try:
        painel = janela.painel
        doc = painel.documento_corpo()
        texto = doc.toPlainText()
        inicio = texto.index("Outra")
        c = QTextCursor(doc)
        c.setPosition(inicio)
        c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        painel.setTextCursor(c)
        painel.copy()
        c = QTextCursor(doc)
        c.movePosition(QTextCursor.MoveOperation.End)
        painel.setTextCursor(c)
        painel.paste()
        drenar_eventos()
        marca = next(m for _p, m in pq.referencias(doc) if m.personalizada)
        checa(pq.texto_da_marca(doc, marca) == "*" and ("rodape", 3) not in doc._numeros_notas
              and doc._numeros_notas[("rodape", 4)] == "3",
              "a marca personalizada mostra o simbolo e nao conta na numeracao")
        refs = [(m.tipo, m.id) for _p, m in pq.referencias(doc)]
        checa_igual(refs[-2:], [("rodape", 5), ("fim", 2)], "as notas coladas tem ids novos")
        cat = pq.catalogo(doc)
        checa(cat.obter("rodape", 5).texto() == cat.obter("rodape", 2).texto(),
              "com o mesmo conteudo")
        dados = escrever(janela._modelo_atual())
        relido, avisos = ler(dados)
        checa(len(relido.notas.itens["rodape"]) == 5 and not avisos, "e voltam do arquivo")
        painel.undo()
        drenar_eventos()
        checa_igual(len(pq.referencias(doc)), 5, "um desfazer tira o colado e as notas")
    finally:
        _fechar(janela)


def testar_pdf_e_txt() -> None:
    secao("PDF com a nota no pe' da pagina e .txt com as notas no fim")
    from editdoc.interface import impressao
    from leitor_pdf import ler_pdf
    from editdoc.modelo.texto_plano import texto_do_documento
    janela = _janela(documento_com_notas(paragrafos=12, fim=1))
    try:
        layout = janela.painel.layout_pag
        janela.painel.preparar_para_impressao()
        dados = impressao.gerar_pdf(layout, list(range(layout.numero_paginas())),
                                    impressao.Metadados(titulo="Notas"))
        pdf = ler_pdf(dados)
        checa_igual(len(pdf.paginas), layout.numero_paginas(), "paginas do PDF = da tela")
        # O leitor do PDF devolve a ligadura (fi) como um caractere so'.
        pagina0 = " ".join(pdf.paginas[0].texto.replace("ﬁ", "fi").split())
        checa("Nota 1." in pagina0 and "Parágrafo 0." in pagina0,
              "a nota 1 esta' na pagina da referencia")
        checa(pagina0.index("Parágrafo 0.") < pagina0.index("Nota 1."),
              "depois do texto do corpo (no pe' da pagina)")
        checa("Nota de fim 1." in " ".join(pdf.texto.replace("ﬁ", "fi").split()),
              "a nota de fim esta' no PDF")
        texto = texto_do_documento(janela._modelo_atual(), layout.doc._numeros_notas)
        checa("[1]" in texto.split("\r\n")[0], "no .txt a referencia vira [1]")
        checa("Notas de rodapé" in texto and "[1] Nota 1." in texto and "[i] Nota de fim 1." in texto,
              "as notas vem no fim, numeradas")
    finally:
        _fechar(janela)


def testar_desempenho() -> None:
    secao("p95 da digitacao num documento com 100 notas (80 teclas com a pintura)")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest

    def p95(modelo) -> float:
        janela = _janela(modelo, 1400, 950)
        try:
            painel = janela.painel
            doc = painel.documento_corpo()
            b = doc.findBlockByNumber(len(modelo.paragrafos) // 3)
            c = QTextCursor(doc)
            c.setPosition(b.position() + 6)
            painel.setTextCursor(c)
            painel.viewport().grab()
            for _ in range(5):
                QTest.keyClick(painel, Qt.Key.Key_A)
                painel.viewport().grab()
            tempos = []
            for _ in range(80):
                t = time.perf_counter()
                QTest.keyClick(painel, Qt.Key.Key_A)
                painel.viewport().grab()
                tempos.append((time.perf_counter() - t) * 1000)
            tempos.sort()
            return tempos[round(0.95 * 79)]
        finally:
            _fechar(janela)
            drenar_eventos()

    com = documento_com_notas(paragrafos=300, cada=3)
    checa_igual(len(com.notas.itens["rodape"]), 100, "o documento tem 100 notas")
    for tentativa in range(2):
        simples = Documento(paragrafos=[Paragrafo(runs=[Run(f"Parágrafo {i}. " + TEXTO * 3)])
                                        for i in range(300)])
        ref = p95(simples)
        medido = p95(com)
        limite = max(16.0, ref * 2.5 + 2.0)
        if medido <= limite:
            break
    print(f"         p95 com 100 notas {medido:.1f} ms; sem notas {ref:.1f} ms")
    checa(medido <= limite, f"p95 {medido:.1f} ms no gate (16 ms) ou ate' 2,5x o documento sem "
                            f"notas ({ref:.1f} ms)")


def main() -> int:
    if not QT:
        return pular("PySide6 nao instalado")
    usar_fonte_windows()
    usar_fontes_do_documento()
    testar_desempenho()
    testar_leitura()
    testar_ida_e_volta()
    testar_editada_e_nova()
    testar_propriedades()
    testar_numeracao()
    testar_validador()
    testar_avisos_e_limites()
    testar_pagina()
    testar_reinicio_por_pagina_na_tela()
    testar_edicao()
    testar_opcoes_e_converter()
    testar_copiar_colar()
    testar_pdf_e_txt()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
