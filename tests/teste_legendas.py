"""Legendas, indice de ilustracoes, referencia cruzada e o resto do sumario (0.1.37).

- modelo: SEQ (rotulo, formato, \\c \\r \\h \\s), contagem na ordem do documento, a linha da legenda,
  REF e PAGEREF, o sumario com \\t, \\b, \\c e o numero de lista na linha;
- inserir legenda acima ou abaixo da imagem, da tabela e do paragrafo: estilo Legenda criado, campo
  SEQ, numeros recontados, um Ctrl+Z desfaz tudo (inclusive o estilo), Ctrl+Y refaz;
- mover e apagar: nada se atualiza sozinho; "Atualizar campos" (F9) recontas e a contraprova
  (sem a contagem) acusa; REF e PAGEREF acompanham;
- salvar e reabrir: validador, begin/separate/end, instrText SEQ, marcadores _Ref e _Toc, estilos
  no styles.xml, a conferencia pos-gravacao, mesmos bytes ao regravar;
- documento do Word: campos SEQ complexos voltam byte a byte (c14n) sem atualizar; atualizados,
  o pacote continua valido;
- indice de ilustracoes: entradas "Figura 1 – texto", hiperlinks e PAGEREF, marcadores _Toc na
  legenda, atualizar o inteiro e so' os numeros, um desfazer;
- referencia cruzada: titulo (texto, pagina, numero), legenda (rotulo e numero, so' o numero,
  inteira, pagina) e marcador; marcador _Ref reaproveitado; atualiza com "Atualizar campos";
- sumario: numero de lista do titulo ("1" + tabulacao), \\t, \\b e o titulo "Sumario";
- faixa e dialogos: nomes de todo controle e ordem de Tab.
"""

from __future__ import annotations

import re

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt, pular,
                       resumir, secao)
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import ordem  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo import legendas as mod  # noqa: E402
from editdoc.modelo import sumario as mod_sum  # noqa: E402
from editdoc.modelo.documento import (Celula, Documento, Linha, MarcaCampo, Marcador,  # noqa: E402
                                      Paragrafo, Run, Tabela, run_de_imagem)
from editdoc.modelo.estilos import catalogo_padrao  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


# -- modelo ---------------------------------------------------------------------------------------

def testar_modelo() -> None:
    secao("modelo: SEQ, contagem, linha da legenda, REF e PAGEREF")
    s = mod.ler_seq(" SEQ Figura \\* ARABIC ")
    checa_igual((s.rotulo, s.formato, s.repetir, s.reiniciar, s.oculto, s.nivel_titulo),
                ("Figura", "decimal", False, None, False, None), "SEQ Figura \\* ARABIC")
    checa_igual(mod.instrucao_seq("Figura"), " SEQ Figura \\* ARABIC ", "a instrucao que o Word grava")
    checa_igual(mod.instrucao_seq("Minha figura", "lowerRoman"),
                ' SEQ "Minha figura" \\* roman ', "rotulo com espaco entre aspas; romano")
    checa_igual(mod.ler_seq(' SEQ "Minha figura" \\* roman ').rotulo, "Minha figura",
                "le o rotulo entre aspas")
    s = mod.ler_seq(" SEQ Tabela \\r 5 \\h \\* MERGEFORMAT ")
    checa_igual((s.reiniciar, s.oculto), (5, True), "\\r 5, \\h e MERGEFORMAT")
    checa_igual(mod.ler_seq(" SEQ Figura \\s 1 ").nivel_titulo, 1, "\\s 1")
    for ruim in (" SEQ Figura Marcador ", " SEQ Figura \\* CardText ", " SEQ Figura \\x ",
                 " SEQ Figura \\r ", " SEQ ", " PAGE "):
        checa(mod.ler_seq(ruim) is None, f"nao recalcula: {ruim.strip()}")

    seq = lambda r="Figura", **kw: ("seq", mod.Seq(r, **kw))  # noqa: E731
    checa_igual(mod.numerar([seq(), seq(), seq("Tabela"), seq()]), ["1", "2", "1", "3"],
                "um contador por rotulo, na ordem")
    checa_igual(mod.numerar([seq(), seq(repetir=True), seq()]), ["1", "1", "2"], "\\c repete")
    checa_igual(mod.numerar([seq(), seq(reiniciar=10), seq()]), ["1", "10", "11"], "\\r recomeca")
    checa_igual(mod.numerar([seq(), seq(oculto=True)]), ["1", ""], "\\h oculta o resultado")
    checa_igual(mod.numerar([seq(formato="lowerRoman"), seq(formato="lowerRoman"),
                             seq(formato="upperLetter")]), ["i", "ii", "C"], "formatos")
    checa_igual(mod.numerar([seq(nivel_titulo=1), seq(nivel_titulo=1), ("titulo", 1),
                             seq(nivel_titulo=1), seq(nivel_titulo=1), ("titulo", 2),
                             seq(nivel_titulo=1)]),
                ["1", "2", "1", "2", "3"], "\\s 1: recomeca depois de cada Titulo 1 (o 2 nao)")
    eventos = [seq(), ("seq", None), seq()]
    checa_igual(mod.numerar(eventos), ["1", None, "2"], "SEQ nao entendido: fica de fora da conta")

    checa_igual(mod.texto_depois_do_numero("legenda"), " – legenda", "texto sem pontuacao: ' – '")
    checa_igual(mod.texto_depois_do_numero(": legenda"), ": legenda", "pontuacao: como veio")
    checa_igual(mod.texto_depois_do_numero("  "), "", "vazio: nada")
    checa_igual(mod.rotulo_valido(' Fi"gu\\ra\t 2 '), "Figura 2", "rotulo limpo (aspas, barra, tab)")
    p = mod.paragrafo_da_legenda("Figura", "3", "o texto", "Caption")
    checa_igual(["".join(r.texto for r in p.runs), p.estilo], ["Figura 3 – o texto", "Caption"],
                "paragrafo da legenda: rotulo, numero e texto")
    marcas = [r.marca for r in p.runs if isinstance(r.marca, MarcaCampo)]
    checa(len(marcas) == 2 and marcas[0].campo.instrucao() == " SEQ Figura \\* ARABIC ",
          "o numero e' o resultado de um SEQ")
    p = mod.paragrafo_da_legenda("Figura", "3", "", "Caption", com_rotulo=False)
    checa_igual("".join(r.texto for r in p.runs), "3", "sem o rotulo: so' o campo")

    r = mod.ler_ref(" REF _Ref123 \\h ")
    checa_igual((r.tipo, r.marcador, r.numero, r.hiperlink), ("REF", "_Ref123", False, True), "REF \\h")
    r = mod.ler_ref(" REF _Ref123 \\r \\h \\* MERGEFORMAT ")
    checa_igual((r.numero, r.hiperlink), (True, True), "REF \\r \\h")
    checa_igual(mod.ler_ref(" PAGEREF _Ref9 \\h ").tipo, "PAGEREF", "PAGEREF")
    for ruim in (" REF _Ref1 \\p ", " REF _Ref1 \\f ", " REF _Ref1 \\n ", " PAGEREF _Ref1 \\p ",
                 " REF ", " SEQ Figura "):
        checa(mod.ler_ref(ruim) is None, f"nao recalcula: {ruim.strip()}")
    checa_igual(mod.instrucao_ref("_Ref1"), " REF _Ref1 \\h ", "instrucao do REF")
    checa_igual(mod.instrucao_ref("_Ref1", "PAGEREF"), " PAGEREF _Ref1 \\h ", "instrucao do PAGEREF")
    checa_igual(mod.instrucao_ref("_Ref1", numero=True, hiperlink=False), " REF _Ref1 \\r ",
                "REF do numero, sem hiperlink")
    checa_igual(mod.numero_sem_ponto("1.2."), "1.2", "numero de lista sem o ponto final")

    e = mod_sum.Entrada("Introdução", 2, "_Toc1", "3", "1.2")
    p = mod_sum.paragrafo_da_entrada(e, "TOC2", lambda ent, pag: f"<x{ent.nivel}{pag}/>",
                                     mod_sum.opcoes_da_instrucao(mod_sum.INSTRUCAO_PADRAO))
    checa_igual("".join(r.texto for r in p.runs), "1.2\tIntrodução\t3",
                "linha com o numero de lista: numero, tab, texto, tab, pagina")
    checa_igual(p.extras, "<x2True/>", "e as tabulacoes pedidas pelo entrada/pagina")


# -- documento de teste ---------------------------------------------------------------------------

def _filler(prefixo: str, n: int) -> list:
    return [Paragrafo(runs=[Run(f"{prefixo} {i} " + "palavra " * 14)]) for i in range(n)]


def _figura() -> Paragrafo:
    return Paragrafo(runs=[run_de_imagem(fx.imagem(largura_cm=4, altura_cm=2))])


def _tabela(rotulo: str) -> Tabela:
    return Tabela(linhas=[Linha(celulas=[Celula(blocos=[Paragrafo(runs=[Run(f"{rotulo}{i}{j}")])])
                                         for j in range(2)]) for i in range(2)],
                  colunas_tw=[4500, 4500])


def documento() -> Documento:
    """Titulo 1, tres figuras (imagem sozinha no paragrafo) entre blocos de texto, duas tabelas, um
    paragrafo para a equacao e um segundo Titulo 1 depois de uma quebra de pagina."""
    ps = [Paragrafo(runs=[Run("Introdução")], estilo="Heading1")]
    ps += _filler("intro", 4)
    ps += [_figura()] + _filler("depois da figura A", 9)
    ps += [_figura()] + _filler("depois da figura B", 9)
    ps += [_tabela("ta")] + _filler("depois da tabela A", 4)
    ps += [Paragrafo(runs=[Run("E = mc2")])] + _filler("depois da equacao", 3)
    ps += [_figura()] + _filler("depois da figura C", 6)
    ps += [_tabela("tb")] + _filler("depois da tabela B", 3)
    ps.append(Paragrafo(runs=[Run("Resultados")], estilo="Heading1", quebra_antes=True))
    ps += _filler("final", 4)
    return Documento(paragrafos=ps, estilos=catalogo_padrao())


def _blocos_com_imagem(doc) -> list:
    saida = []
    b = doc.begin()
    while b.isValid():
        it = b.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().isImageFormat():
                saida.append(b)
                break
            it += 1
        b = b.next()
    return saida


def _bloco_com_texto(doc, trecho: str):
    b = doc.begin()
    while b.isValid():
        if trecho in b.text().replace("￼", ""):
            return b
        b = b.next()
    raise AssertionError(f"sem bloco com {trecho!r}")


def _limpo(texto: str) -> str:
    return texto.replace("￼", "").replace(" ", " ")


def _legendas(doc) -> list[tuple[str, str]]:
    """(texto do paragrafo da legenda, numero do SEQ) de cada SEQ, na ordem."""
    from editdoc.edicao import legendas as ed
    return [(_limpo(x.texto), x.numero) for x in ed.legendas(doc)]


def _numeros(doc, rotulo: str | None = None) -> list[str]:
    from editdoc.edicao import legendas as ed
    return [x.numero for x in ed.legendas(doc, rotulo)]


def _abrir_janela(gerente, modelo: Documento, tmp, nome: str = "leg.docx"):
    arquivo = tmp / nome
    arquivo.write_bytes(escrever(modelo))
    return _abrir(gerente, arquivo), arquivo


def _abrir(gerente, arquivo):
    j = gerente.abrir(str(arquivo))
    drenar_eventos()
    j.painel.setFocus()
    return j


def _fechar(gerente) -> None:
    import teste_sumario as ts
    ts._fechar(gerente)


def _dialogos(**kw):
    import teste_sumario as ts
    return ts.dialogos(**kw)


def _tecla(painel, tecla, mod_=None) -> None:
    import teste_sumario as ts
    ts._tecla(painel, tecla, mod_)


def _cursor_em(painel, bloco, fim: bool = False) -> None:
    c = painel.textCursor()
    c.setPosition(bloco.position())
    if fim:
        c.movePosition(c.MoveOperation.EndOfBlock)
    painel.setTextCursor(c)


def _inserir_legenda(j, bloco, rotulo="Figura", posicao="abaixo", texto="", com_rotulo=True,
                     fim=False) -> bool:
    """Poe o cursor no bloco e usa o comando pela janela, com o dialogo trocado."""
    _cursor_em(j.painel, bloco, fim)
    escolha = {"rotulo": rotulo, "posicao": posicao, "texto": texto, "com_rotulo": com_rotulo}
    original = j._pedir_legenda
    j._pedir_legenda = lambda rotulos, proximos, r: escolha
    try:
        j.comandos.acao("inserir_legenda").trigger()
    finally:
        j._pedir_legenda = original
    drenar_eventos(2)
    return True


# -- inserir ----------------------------------------------------------------------------------------

def testar_inserir_e_desfazer() -> None:
    secao("inserir legenda: imagem, tabela e paragrafo; estilo criado; um desfazer")
    from PySide6.QtCore import Qt

    from editdoc import configuracao
    from editdoc.interface.gerente import GerenteDeJanelas
    from editdoc.ponte_qt import estilos as pq_estilos

    ctrl = Qt.KeyboardModifier.ControlModifier
    with pasta_temporaria() as tmp:
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, _arq = _abrir_janela(gerente, documento(), tmp)
        p = j.painel
        doc = p.documento_corpo()
        antes = doc.toPlainText()
        checa(pq_estilos.catalogo(doc).por_nome("caption") is None, "o documento nao tem Legenda")
        imagens = _blocos_com_imagem(doc)
        checa_igual(len(imagens), 3, "tres imagens")
        # Abaixo da segunda imagem.
        mensagens: list[str] = []
        p.mensagem.connect(mensagens.append)
        _inserir_legenda(j, imagens[1], texto="Resultado B")
        leg = _legendas(doc)
        checa_igual(leg, [("Figura 1 – Resultado B", "1")], "uma legenda: Figura 1 – Resultado B")
        bloco_leg = doc.findBlock(imagens[1].position()).next()
        checa("Figura 1" in _limpo(bloco_leg.text()), "a legenda e' o paragrafo logo abaixo da imagem")
        cat = pq_estilos.catalogo(doc)
        checa(cat.por_nome("caption") is not None, "o estilo Legenda foi criado")
        checa_igual(pq_estilos.estilo_do_bloco(bloco_leg.blockFormat()), cat.por_nome("caption").id,
                    "e a legenda usa o estilo")
        checa(mensagens and "Figura 1" in mensagens[-1], "a barra de status diz a legenda")
        # Acima da primeira imagem: vira a Figura 1 e a outra passa a 2 (inserir recontas).
        _inserir_legenda(j, _blocos_com_imagem(doc)[0], texto="Resultado A", posicao="acima")
        checa_igual(_legendas(doc), [("Figura 1 – Resultado A", "1"), ("Figura 2 – Resultado B", "2")],
                    "a nova, acima, e' a Figura 1; a de baixo foi renumerada para 2")
        bloco_a = _blocos_com_imagem(doc)[0]
        checa("Figura 1" in _limpo(bloco_a.previous().text()), "acima: a legenda e' o paragrafo antes")
        # Tabela: acima (padrao do Word para tabela) e a segunda tabela, abaixo.
        tabela_a = _bloco_com_texto(doc, "ta00")
        _cursor_em(p, tabela_a)
        _inserir_legenda_no_cursor(j, "Tabela", "acima", "Primeira tabela")
        tab = p.textCursor().currentTable()
        checa(tab is None, "depois de inserir, o cursor esta' na legenda (fora da tabela)")
        leg_t = [x for x in _legendas(doc) if x[0].startswith("Tabela")]
        checa_igual(leg_t, [("Tabela 1 – Primeira tabela", "1")], "legenda da tabela")
        tabela_b = _bloco_com_texto(doc, "tb00")
        _cursor_em(p, tabela_b)
        _inserir_legenda_no_cursor(j, "Tabela", "abaixo", "Segunda tabela")
        leg_t = [x for x in _legendas(doc) if x[0].startswith("Tabela")]
        checa_igual(leg_t, [("Tabela 1 – Primeira tabela", "1"), ("Tabela 2 – Segunda tabela", "2")],
                    "a segunda tabela, com a legenda abaixo, e' a Tabela 2")
        # A legenda de cima fica antes da tabela e a de baixo depois dela.
        plano = [_limpo(b.text()) for b in _blocos(doc)]
        i1 = next(i for i, t in enumerate(plano) if t.startswith("Tabela 1"))
        checa(plano[i1 + 1].startswith("ta00"), "Tabela 1: a legenda vem logo antes da tabela")
        i2 = next(i for i, t in enumerate(plano) if t.startswith("Tabela 2"))
        checa(plano[i2 - 1].startswith("tb"), "Tabela 2: a legenda vem logo depois da tabela")
        # Equacao no paragrafo de texto.
        _inserir_legenda(j, _bloco_com_texto(doc, "E = mc2"), rotulo="Equação", texto="Energia")
        checa(("Equação 1 – Energia", "1") in _legendas(doc), "Equação 1")
        # Um rotulo novo vale.
        _inserir_legenda(j, _bloco_com_texto(doc, "final 0"), rotulo="Gráfico", texto="", fim=True)
        checa(("Gráfico 1", "1") in _legendas(doc), "rotulo novo: Gráfico 1, sem texto")
        # Sem rotulo: so' o campo.
        _inserir_legenda(j, _bloco_com_texto(doc, "final 1"), rotulo="Figura", com_rotulo=False,
                         texto=": solta")
        checa(("3: solta", "3") in _legendas(doc), "sem o rotulo: o numero (a Figura 3) e o texto")
        _fechar(gerente)

        # Um Ctrl+Z desfaz a ultima; desfaz tudo ate' o texto e o catalogo de antes.
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, _arq = _abrir_janela(gerente, documento(), tmp, "leg2.docx")
        p = j.painel
        doc = p.documento_corpo()
        antes = doc.toPlainText()
        _inserir_legenda(j, _blocos_com_imagem(doc)[1], texto="Resultado B")
        depois = doc.toPlainText()
        _inserir_legenda(j, _blocos_com_imagem(doc)[0], texto="Resultado A", posicao="acima")
        dois = doc.toPlainText()
        checa_igual(_numeros(doc), ["1", "2"], "duas legendas")
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(doc.toPlainText(), depois, "um Ctrl+Z desfaz a ultima legenda e a renumeracao")
        checa_igual(_numeros(doc), ["1"], "e a primeira volta a ser a Figura 1")
        _tecla(p, Qt.Key.Key_Y, ctrl)
        checa_igual(doc.toPlainText(), dois, "Ctrl+Y refaz")
        _tecla(p, Qt.Key.Key_Z, ctrl)
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(doc.toPlainText(), antes, "dois Ctrl+Z devolvem o texto")
        checa(pq_estilos.catalogo(doc).por_nome("caption") is None, "e o catalogo sem Legenda")
        _fechar(gerente)


def _blocos(doc) -> list:
    saida = []
    b = doc.begin()
    while b.isValid():
        saida.append(b)
        b = b.next()
    return saida


def _inserir_legenda_no_cursor(j, rotulo, posicao, texto) -> None:
    """Como `_inserir_legenda`, mas com o cursor onde esta'."""
    escolha = {"rotulo": rotulo, "posicao": posicao, "texto": texto, "com_rotulo": True}
    original = j._pedir_legenda
    j._pedir_legenda = lambda rotulos, proximos, r: escolha
    try:
        j.comandos.acao("inserir_legenda").trigger()
    finally:
        j._pedir_legenda = original
    drenar_eventos(2)


def _com_tres_figuras(j, textos=("A", "B", "C")) -> None:
    """Uma legenda abaixo de cada figura, de baixo para cima (a renumeracao de cada insercao ja'
    deixa Figura 1, 2 e 3 na ordem)."""
    doc = j.painel.documento_corpo()
    for i in (2, 1, 0):
        _inserir_legenda(j, _blocos_com_imagem(doc)[i], texto=f"Figura {textos[i]}")
    checa_igual(_numeros(doc), ["1", "2", "3"], "tres legendas, numeradas na ordem")


def _mover_para(doc, bloco_de, bloco_ate, destino) -> None:
    """Recorta os blocos de `bloco_de` a `bloco_ate` e cola no comeco de `destino` (como o
    Ctrl+X e o Ctrl+V), num passo de desfazer."""
    from PySide6.QtGui import QTextCursor
    c = QTextCursor(doc)
    c.beginEditBlock()
    c.setPosition(bloco_de.position())
    c.setPosition(bloco_ate.position() + bloco_ate.length(), QTextCursor.MoveMode.KeepAnchor)
    fragmento = c.selection()
    c.removeSelectedText()
    alvo = QTextCursor(doc)
    alvo.setPosition(destino)
    alvo.insertFragment(fragmento)
    c.endEditBlock()


def testar_mover_apagar_e_atualizar() -> None:
    secao("mover e apagar: nada se atualiza sozinho; Atualizar campos recontas; contraprova")
    from PySide6.QtCore import Qt

    from editdoc import configuracao
    from editdoc.edicao import legendas as ed
    from editdoc.interface.gerente import GerenteDeJanelas

    ctrl = Qt.KeyboardModifier.ControlModifier
    with pasta_temporaria() as tmp:
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, _arq = _abrir_janela(gerente, documento(), tmp)
        p = j.painel
        doc = p.documento_corpo()
        _com_tres_figuras(j)
        imagens = _blocos_com_imagem(doc)
        # A Figura C (imagem e legenda) vai para antes da Figura A.
        _mover_para(doc, imagens[2], imagens[2].next(), imagens[0].position())
        drenar_eventos(2)
        ordem_dos_textos = [t.split(" – ")[1] for t, _n in _legendas(doc)]
        checa_igual(ordem_dos_textos, ["Figura C", "Figura A", "Figura B"],
                    "a figura C foi para o alto")
        checa_igual(_numeros(doc), ["3", "1", "2"], "nada se atualiza sozinho: os numeros velhos")
        checa(len(ed.contar(doc)) == 3, "e a contagem acusa os tres campos errados")
        antes = doc.toPlainText()
        # Contraprova: sem a contagem, o comando nao muda nada.
        original = ed.contar
        ed.contar = lambda _doc: []
        try:
            j.comandos.acao("atualizar_campos").trigger()
            drenar_eventos(2)
            checa_igual(_numeros(doc), ["3", "1", "2"],
                        "contraprova: sem a contagem, os numeros continuam velhos")
        finally:
            ed.contar = original
        mensagens: list[str] = []
        p.mensagem.connect(mensagens.append)
        _tecla(p, Qt.Key.Key_F9)
        checa_igual(_numeros(doc), ["1", "2", "3"], "F9: numerados na ordem do documento")
        checa(mensagens and "Campos atualizados" in mensagens[-1], "a barra de status conta")
        checa_igual([t.split(" – ")[1] for t, _n in _legendas(doc)],
                    ["Figura C", "Figura A", "Figura B"], "e o texto das legendas nao mudou")
        atualizado = doc.toPlainText()
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(doc.toPlainText(), antes, "um Ctrl+Z devolve os numeros de antes")
        _tecla(p, Qt.Key.Key_Y, ctrl)
        checa_igual(doc.toPlainText(), atualizado, "Ctrl+Y refaz")
        # Atualizar de novo nao muda nada.
        mensagens.clear()
        _tecla(p, Qt.Key.Key_F9)
        checa(mensagens and "já estavam" in mensagens[-1], "sem diferenca: o aviso diz que ja' estava")
        # Apagar a legenda do meio (a figura A, a segunda).
        from PySide6.QtGui import QTextCursor
        imagens = _blocos_com_imagem(doc)
        leg = imagens[1].next()
        c = QTextCursor(doc)
        c.setPosition(imagens[1].position())
        c.setPosition(leg.position() + leg.length(), QTextCursor.MoveMode.KeepAnchor)
        c.removeSelectedText()
        drenar_eventos(2)
        checa_igual(_numeros(doc), ["1", "3"], "apagada a 2: sobram 1 e 3 (nada se atualiza sozinho)")
        _tecla(p, Qt.Key.Key_F9)
        checa_igual(_numeros(doc), ["1", "2"], "atualizar: 1 e 2")
        _fechar(gerente)


def _partes_salvas(j, arquivo):
    perdas: list = []
    with _dialogos(pedir_perda=lambda _p, _n, linhas: perdas.append(linhas) or "salvar"):
        checa(j.salvar() is True, "salvar grava (a conferencia aceita o arquivo)")
    return fx.partes_de(arquivo.read_bytes())


def testar_salvar_e_reabrir() -> None:
    secao("salvar e reabrir: validador, begin/separate/end, SEQ, estilo e os mesmos bytes")
    from editdoc import configuracao
    from editdoc.formato_docx import conferencia
    from editdoc.interface.gerente import GerenteDeJanelas

    with pasta_temporaria() as tmp:
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, arquivo = _abrir_janela(gerente, documento(), tmp)
        doc = j.painel.documento_corpo()
        _com_tres_figuras(j)
        _inserir_legenda(j, _bloco_com_texto(doc, "ta00"), rotulo="Tabela", posicao="acima",
                         texto="Primeira")
        final = _legendas(doc)
        partes = _partes_salvas(j, arquivo)
        checa_igual(ordem.validar(partes), [], "o pacote salvo passa no validador")
        xml = partes["word/document.xml"].decode("utf-8")
        tipos = re.findall(r'w:fldCharType="(\w+)"', xml)
        checa_igual((tipos.count("begin"), tipos.count("separate"), tipos.count("end")), (4, 4, 4),
                    "begin, separate e end: um SEQ por legenda")
        instrs = re.findall(r"<w:instrText[^>]*>([^<]*)</w:instrText>", xml)
        checa_igual(sorted(instrs), [" SEQ Figura \\* ARABIC "] * 3 + [" SEQ Tabela \\* ARABIC "],
                    "as instrucoes SEQ do Word")
        checa('<w:instrText xml:space="preserve"> SEQ Figura' in xml, "com xml:space")
        raiz = etree.fromstring(partes["word/document.xml"])
        legendas = raiz.xpath("//w:p[w:pPr/w:pStyle[@w:val='Caption']]", namespaces=NS)
        checa_igual(len(legendas), 4, "quatro paragrafos no estilo Caption")
        estilos = etree.fromstring(partes["word/styles.xml"])
        checa("caption" in estilos.xpath("//w:style/w:name/@w:val", namespaces=NS),
              "styles.xml com o estilo caption")
        modelo, avisos = ler(arquivo.read_bytes())
        checa_igual(avisos, [], "o arquivo salvo abre sem aviso")
        conferencia.conferir(arquivo.read_bytes(), j._modelo_atual())
        checa(True, "a conferencia pos-gravacao aceita")
        _fechar(gerente)
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        doc = j.painel.documento_corpo()
        checa_igual(_legendas(doc), final, "reaberto: as mesmas legendas, com o mesmo numero")
        dados1 = escrever(j._modelo_atual())
        checa(dados1 == escrever(ler(dados1)[0]), "reaberto e salvo de novo: os mesmos bytes")
        _fechar(gerente)


# -- documento do Word ----------------------------------------------------------------------------

_ESTILO_LEGENDA_DO_WORD = (
    '<w:style w:type="paragraph" w:styleId="Legenda"><w:name w:val="caption"/><w:basedOn w:val="Normal"/>'
    '<w:next w:val="Normal"/><w:uiPriority w:val="35"/><w:unhideWhenUsed/><w:qFormat/><w:pPr>'
    '<w:spacing w:after="200" w:line="240" w:lineRule="auto"/></w:pPr><w:rPr><w:i/><w:iCs/>'
    '<w:color w:val="0E2841" w:themeColor="text2"/><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr></w:style>')

_CORPO_DO_WORD = (
    '<w:p><w:pPr><w:pStyle w:val="Ttulo1"/></w:pPr><w:r><w:t>Capítulo</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Legenda"/></w:pPr><w:bookmarkStart w:id="11" w:name="_Ref100000001"/>'
    '<w:r><w:t xml:space="preserve">Figura </w:t></w:r>' + fx.campo_complexo("SEQ Figura \\* ARABIC", "7")
    + '<w:bookmarkEnd w:id="11"/><w:r><w:t xml:space="preserve"> – Uma figura</w:t></w:r></w:p>'
    '<w:p><w:r><w:t xml:space="preserve">Veja a </w:t></w:r>'
    + fx.campo_complexo("REF _Ref100000001 \\h", "Figura 2")
    + '<w:r><w:t>.</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Legenda"/></w:pPr><w:r><w:t xml:space="preserve">Figura </w:t></w:r>'
    + fx.campo_complexo("SEQ Figura \\* ARABIC", "9") + '<w:r><w:t xml:space="preserve"> – Outra</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Legenda"/></w:pPr><w:r><w:t xml:space="preserve">Tabela </w:t></w:r>'
    '<w:fldSimple w:instr=" SEQ Tabela \\* ARABIC "><w:r><w:t>5</w:t></w:r></w:fldSimple>'
    '<w:r><w:t xml:space="preserve"> – Dados</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Legenda"/></w:pPr><w:r><w:t xml:space="preserve">Figura </w:t></w:r>'
    + fx.campo_complexo('SEQ Figura \\* ARABIC \\c', "9") + '<w:r><w:t xml:space="preserve"> – Repetida</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Legenda"/></w:pPr><w:r><w:t xml:space="preserve">Figura </w:t></w:r>'
    + fx.campo_complexo("SEQ Figura Marcador", "42") + '<w:r><w:t xml:space="preserve"> – Com marcador</w:t></w:r></w:p>')


def _docx_do_word() -> bytes:
    return fx.docx_com_estilos_do_word(
        _CORPO_DO_WORD, fx.ESTILOS_DO_WORD.replace("</w:styles>", _ESTILO_LEGENDA_DO_WORD + "</w:styles>"))


def _paragrafos_c14n(xml: bytes, indices: list[int]) -> list[bytes]:
    corpo = etree.fromstring(xml).find(f"{{{W}}}body")
    ps = list(corpo)
    return [re.sub(rb'w:id="\d+"', b'w:id="0"', etree.tostring(ps[i], method="c14n"))
            for i in indices]  # o escritor renumera o w:id dos marcadores (sempre fez)


def testar_documento_do_word() -> None:
    secao("documento do Word: campos SEQ preservados sem atualizar; atualizados, pacote valido")
    from PySide6.QtCore import Qt

    from editdoc import configuracao
    from editdoc.formato_docx import conferencia
    from editdoc.interface.gerente import GerenteDeJanelas

    origem = _docx_do_word()
    direto = escrever(ler(origem)[0])
    with pasta_temporaria() as tmp:
        arquivo = tmp / "word.docx"
        arquivo.write_bytes(origem)
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        doc = j.painel.documento_corpo()
        checa_igual(_numeros(doc), ["7", "9", "5", "9"],
                    "os SEQ que o EditDoc entende (o com marcador fica de fora)")
        salvo = escrever(j._modelo_atual())
        a, b = fx.partes_de(salvo)["word/document.xml"], fx.partes_de(direto)["word/document.xml"]
        checa_igual(etree.tostring(etree.fromstring(a), method="c14n"),
                    etree.tostring(etree.fromstring(b), method="c14n"),
                    "abrir e salvar sem atualizar: o document.xml do escritor, em c14n")
        o = fx.partes_de(origem)["word/document.xml"]
        checa_igual(_paragrafos_c14n(a, [1, 2, 3, 5, 6]), _paragrafos_c14n(o, [1, 2, 3, 5, 6]),
                    "as legendas e o REF (campos complexos) voltam como o Word gravou, em c14n")
        checa(fx.partes_de(salvo)["word/styles.xml"] == fx.partes_de(direto)["word/styles.xml"],
              "e o styles.xml tambem (nenhum estilo criado)")
        # Atualizar campos.
        _tecla(j.painel, Qt.Key.Key_F9)
        checa_igual(_numeros(doc), ["1", "2", "1", "2"],
                    "atualizar: Figura 1, 2 (e a repetida, \\c, mostra a 2) e Tabela 1")
        plano = _limpo(doc.toPlainText())
        checa("Veja a Figura 1." in plano, "o REF acompanhou a legenda (era Figura 2)")
        modelo = j._modelo_atual()
        dados = escrever(modelo)
        partes = fx.partes_de(dados)
        checa_igual(ordem.validar(partes), [], "o pacote atualizado passa no validador")
        xml = partes["word/document.xml"].decode("utf-8")
        checa(" SEQ Figura Marcador " in xml and " REF _Ref100000001 \\h " in xml
              and 'w:name="_Ref100000001"' in xml, "o SEQ com marcador, o REF e o marcador _Ref continuam")
        checa(' SEQ Tabela \\* ARABIC ' in xml, "o campo simples SEQ voltou como campo")
        relido, avisos = ler(dados)
        checa_igual(avisos, [], "o arquivo atualizado abre sem aviso")
        conferencia.conferir(dados, modelo)
        checa(True, "a conferencia aceita o arquivo atualizado")
        _fechar(gerente)


# -- indice de ilustracoes -----------------------------------------------------------------------------

def _indices(doc, figuras: bool = True) -> list:
    from editdoc.edicao import sumario as ed
    return ed.sumarios(doc, figuras)


def _linhas_do_indice(doc, k: int = 0) -> list[str]:
    ini, fim, _campo = _indices(doc)[k]
    texto = doc.toPlainText()[ini:fim + 1]
    return [t.replace("￼", "") for t in texto.split("\n") if t.replace("￼", "")]


def _esperado_do_indice(painel, rotulo: str) -> list[str]:
    import teste_sumario as ts
    from editdoc.edicao import legendas as ed
    doc = painel.documento_corpo()
    saida = []
    vistos = set()
    for leg in ed.legendas(doc, rotulo):
        if leg.bloco in vistos:
            continue
        vistos.add(leg.bloco)
        bloco = doc.findBlockByNumber(leg.bloco)
        saida.append(f"{mod_sum.texto_do_titulo(bloco.text())}\t{ts._pagina_esperada(painel, bloco)}")
    return saida


def _pedir_indice(j, rotulo: str) -> None:
    original = j._pedir_indice_de_figuras
    j._pedir_indice_de_figuras = lambda rotulos: rotulo
    try:
        j.comandos.acao("inserir_indice_ilustracoes").trigger()
    finally:
        j._pedir_indice_de_figuras = original
    drenar_eventos(2)


def testar_indice_de_ilustracoes() -> None:
    secao("indice de ilustracoes: inserir, atualizar, so' os numeros, um desfazer, salvar e reabrir")
    from PySide6.QtCore import Qt

    from editdoc import configuracao
    from editdoc.formato_docx import conferencia
    from editdoc.interface.gerente import GerenteDeJanelas
    from editdoc.ponte_qt import estilos as pq_estilos
    from editdoc.ponte_qt import marcas as pq_marcas

    ctrl = Qt.KeyboardModifier.ControlModifier
    with pasta_temporaria() as tmp:
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, arquivo = _abrir_janela(gerente, documento(), tmp)
        p = j.painel
        doc = p.documento_corpo()
        _com_tres_figuras(j)
        _inserir_legenda(j, _bloco_com_texto(doc, "ta00"), rotulo="Tabela", posicao="acima",
                         texto="Dados")
        texto_antes = doc.toPlainText()
        _cursor_em(p, doc.begin())
        mensagens: list[str] = []
        p.mensagem.connect(mensagens.append)
        _pedir_indice(j, "Figura")
        todos = _indices(doc)
        checa_igual(len(todos), 1, "um indice de ilustracoes")
        checa_igual(todos[0][2].instrucao(), ' TOC \\h \\z \\c "Figura" ', "a instrucao do Word")
        esperado = _esperado_do_indice(p, "Figura")
        linhas = _linhas_do_indice(doc)
        checa_igual(linhas, esperado, "uma linha por legenda de Figura, com a folha de cada uma")
        checa(len(linhas) == 3 and linhas[0].startswith("Figura 1 – Figura A\t"),
              f"Figura 1 – texto, tabulacao e pagina: {linhas[0]!r}")
        checa(mensagens and "3 entradas" in mensagens[-1] and "Índice de ilustrações" in mensagens[-1],
              "a barra de status conta as entradas")
        cat = pq_estilos.catalogo(doc)
        estilo = cat.por_nome("table of figures")
        checa(estilo is not None, "o estilo Indice de Ilustracoes foi criado")
        bloco_linha = doc.findBlock(todos[0][0])
        checa_igual(pq_estilos.estilo_do_bloco(bloco_linha.blockFormat()), estilo.id,
                    "a primeira linha usa o estilo")
        nomes_toc = [m.nome for _p, m in pq_marcas.posicoes_de_marcadores(doc)
                     if m.tipo == "inicio" and m.nome.startswith("_Toc")]
        checa_igual(len(set(nomes_toc)), 3, "cada legenda ganhou um marcador _Toc")
        # Atualizar o sumario de titulos nao toca o indice.
        mensagens.clear()
        j.comandos.acao("atualizar_sumario").trigger()
        drenar_eventos(2)
        checa(mensagens and "não tem sumário" in mensagens[-1], "Atualizar Sumario nao pega o indice")
        # Mover a Figura C para o alto, atualizar os campos e o indice.
        imagens = _blocos_com_imagem(doc)
        _mover_para(doc, imagens[2], imagens[2].next(), imagens[0].position())
        drenar_eventos(2)
        _tecla(p, Qt.Key.Key_F9)
        depois_f9 = _linhas_do_indice(doc)
        checa_igual([x.split("\t")[0] for x in depois_f9], [x.split("\t")[0] for x in linhas],
                    "o indice nao se atualiza sozinho (o F9 so' mexe nos numeros de pagina)")
        j.comandos.acao("atualizar_indice_ilustracoes").trigger()
        drenar_eventos(2)
        esperado = _esperado_do_indice(p, "Figura")
        linhas2 = _linhas_do_indice(doc)
        checa_igual(linhas2, esperado, "atualizar o inteiro: a ordem e os numeros novos")
        checa_igual([x.split("\t")[0] for x in linhas2],
                    ["Figura 1 – Figura C", "Figura 2 – Figura A", "Figura 3 – Figura B"],
                    "Figura C passou a ser a 1")
        checa_igual(len(_indices(doc)), 1, "continua um campo so'")
        atualizado = doc.toPlainText()
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(_linhas_do_indice(doc), depois_f9, "um Ctrl+Z volta ao indice de antes")
        _tecla(p, Qt.Key.Key_Y, ctrl)
        checa_igual(doc.toPlainText(), atualizado, "Ctrl+Y refaz")
        # So' os numeros: empurrar as figuras para outra pagina.
        from PySide6.QtGui import QTextCursor
        c = QTextCursor(doc)
        c.setPosition(_bloco_com_texto(doc, "intro 0").position())
        c.beginEditBlock()
        for i in range(45):
            c.insertText(f"linha extra {i} " + "palavra " * 10)
            c.insertBlock(c.blockFormat(), c.charFormat())
        c.endEditBlock()
        drenar_eventos(2)
        velhas = _linhas_do_indice(doc)
        esperado = _esperado_do_indice(p, "Figura")
        checa(velhas != esperado, "contraprova: depois de empurrar, o numero de pagina ficou velho")
        j.comandos.acao("atualizar_numeros_indice_ilustracoes").trigger()
        drenar_eventos(2)
        checa_igual(_linhas_do_indice(doc), esperado, "so' os numeros: as paginas certas de novo")
        checa_igual([x.split("\t")[0] for x in _linhas_do_indice(doc)],
                    [x.split("\t")[0] for x in velhas], "e as linhas ficaram")
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(_linhas_do_indice(doc), velhas, "um Ctrl+Z desfaz so' a troca dos numeros")
        _tecla(p, Qt.Key.Key_Y, ctrl)
        # Um segundo indice, de Tabela: o atualizar com o cursor fora atualiza os dois.
        _cursor_em(p, _bloco_com_texto(doc, "final 3"), fim=True)
        _pedir_indice(j, "Tabela")
        checa_igual(len(_indices(doc)), 2, "dois indices (Figura e Tabela)")
        checa_igual(_linhas_do_indice(doc, 1)[0].split("\t")[0], "Tabela 1 – Dados", "o de Tabela")
        _cursor_em(p, _bloco_com_texto(doc, "final 2"))
        j.comandos.acao("atualizar_indice_ilustracoes").trigger()
        drenar_eventos(2)
        checa(len(_indices(doc)) == 2 and _linhas_do_indice(doc, 0) == _esperado_do_indice(p, "Figura")
              and _linhas_do_indice(doc, 1) == _esperado_do_indice(p, "Tabela"),
              "fora dos dois, atualizar refaz os dois")
        # Salvar, validar, reabrir.
        final = [_linhas_do_indice(doc, 0), _linhas_do_indice(doc, 1)]
        partes = _partes_salvas(j, arquivo)
        checa_igual(ordem.validar(partes), [], "o pacote salvo passa no validador")
        raiz = etree.fromstring(partes["word/document.xml"])
        instrs = raiz.xpath("//w:instrText/text()", namespaces=NS)
        checa(' TOC \\h \\z \\c "Figura" ' in instrs and ' TOC \\h \\z \\c "Tabela" ' in instrs,
              "os dois TOC com \\c")
        ancoras = raiz.xpath("//w:hyperlink/@w:anchor", namespaces=NS)
        marcadores = raiz.xpath("//w:bookmarkStart/@w:name", namespaces=NS)
        checa(len(ancoras) == 4 and set(ancoras) <= set(marcadores), "cada linha: hiperlink para um _Toc que existe")
        pagerefs = [t for t in instrs if "PAGEREF" in t]
        checa_igual(len(pagerefs), 4, "um PAGEREF por linha")
        legendas = raiz.xpath("//w:p[w:bookmarkStart[starts-with(@w:name,'_Toc')]]"
                              "[w:pPr/w:pStyle[@w:val='Caption']]", namespaces=NS)
        checa_igual(len(legendas), 4, "os marcadores _Toc estao nos paragrafos de legenda")
        estilos = etree.fromstring(partes["word/styles.xml"])
        checa("table of figures" in estilos.xpath("//w:style/w:name/@w:val", namespaces=NS),
              "styles.xml com table of figures")
        modelo, avisos = ler(arquivo.read_bytes())
        checa_igual(avisos, [], "o arquivo salvo abre sem aviso")
        conferencia.conferir(arquivo.read_bytes(), j._modelo_atual())
        checa(True, "a conferencia aceita o indice")
        _fechar(gerente)
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        doc = j.painel.documento_corpo()
        checa_igual([_linhas_do_indice(doc, 0), _linhas_do_indice(doc, 1)], final,
                    "reaberto: os mesmos indices")
        dados1 = escrever(j._modelo_atual())
        checa(dados1 == escrever(ler(dados1)[0]), "reaberto e salvo de novo: os mesmos bytes")
        _fechar(gerente)


# -- referencia cruzada ------------------------------------------------------------------------------

def _refs(doc) -> list[tuple[str, str]]:
    """(instrucao, resultado) de cada REF e PAGEREF do documento, na ordem."""
    from editdoc.edicao import sumario as ed
    plano = doc.toPlainText()
    return [(c.instrucao(), plano[ini + 1:fim].replace("￼", ""))
            for ini, fim, c in ed.campos(doc) if c.tipo() in ("REF", "PAGEREF")
            and not mod_sum.eh_sumario(c)]


def _refs_cruzadas(doc) -> list[tuple[str, str]]:
    """As referencias cruzadas (o documento de teste nao tem sumario)."""
    return _refs(doc)


def _marcadores_ref(doc) -> dict[str, str]:
    """nome -> texto do trecho dos marcadores _Ref."""
    from editdoc.edicao import sumario as ed
    plano = doc.toPlainText()
    return {n: plano[a + 1:b].replace("￼", "") for n, (a, b) in ed.intervalos_de_marcadores(doc).items()
            if n.startswith("_Ref")}


def _inserir_ref(j, tipo: str, indice: int, o_que: str, onde: str = "final 2",
                 hiperlink: bool = True) -> None:
    from editdoc.edicao import referencias as ed_ref
    doc = j.painel.documento_corpo()
    alvo = ed_ref.alvos(doc, tipo)[indice]
    _cursor_em(j.painel, _bloco_com_texto(doc, onde), fim=True)
    original = j._pedir_referencia
    j._pedir_referencia = lambda _doc: (alvo, o_que, hiperlink)
    try:
        j.comandos.acao("referencia_cruzada").trigger()
    finally:
        j._pedir_referencia = original
    drenar_eventos(2)


def testar_referencia_cruzada() -> None:
    secao("referencia cruzada: titulo, legenda e marcador; _Ref reaproveitado; Atualizar campos")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor

    import teste_sumario as ts
    from editdoc import configuracao
    from editdoc.edicao import referencias as ed_ref
    from editdoc.formato_docx import conferencia
    from editdoc.interface.gerente import GerenteDeJanelas

    ctrl = Qt.KeyboardModifier.ControlModifier
    with pasta_temporaria() as tmp:
        modelo = documento()
        modelo.paragrafos[2].runs = [
            Run("intro com marcador: "), Run(marca=Marcador("inicio", "meu_marcador")),
            Run("trecho marcado"), Run(marca=Marcador("fim", "meu_marcador")), Run(" fim")]
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, arquivo = _abrir_janela(gerente, modelo, tmp)
        p = j.painel
        doc = p.documento_corpo()
        checa_igual([c for c, _t in ed_ref.tipos(doc)], ["titulo", "marcador"],
                    "sem legendas: Titulo e Marcador")
        _com_tres_figuras(j)
        checa_igual([c for c, _t in ed_ref.tipos(doc)], ["titulo", "Figura", "marcador"],
                    "com legendas de Figura: Titulo, Figura e Marcador")
        itens = ed_ref.alvos(doc, "Figura")
        checa_igual([a.descricao for a in itens],
                    ["Figura 1 – Figura A", "Figura 2 – Figura B", "Figura 3 – Figura C"],
                    "a lista de Figura")
        checa_igual([a.descricao for a in ed_ref.alvos(doc, "titulo")], ["Introdução", "Resultados"],
                    "a lista de titulos")
        checa_igual([a.descricao for a in ed_ref.alvos(doc, "marcador")], ["meu_marcador"],
                    "a lista de marcadores (sem os ocultos)")
        mensagens: list[str] = []
        p.mensagem.connect(mensagens.append)
        padrao_ref = re.compile(r" REF _Ref\d{9} \\h ")
        _inserir_ref(j, "Figura", 0, ed_ref.ROTULO_E_NUMERO)
        refs = _refs_cruzadas(doc)
        checa(len(refs) == 1 and padrao_ref.fullmatch(refs[0][0]) and refs[0][1] == "Figura 1",
              f"REF para rotulo e numero: {refs}")
        marc = _marcadores_ref(doc)
        checa_igual(list(marc.values()), ["Figura 1"], "um marcador _Ref cobrindo 'Figura 1'")
        checa(mensagens and "Referência cruzada" in mensagens[-1], "a barra de status avisa")
        _inserir_ref(j, "Figura", 0, ed_ref.SOMENTE_NUMERO)
        checa_igual(_refs_cruzadas(doc)[-1][1], "1", "so' o numero: 1")
        checa_igual(sorted(_marcadores_ref(doc).values()), ["1", "Figura 1"], "dois marcadores")
        _inserir_ref(j, "Figura", 0, ed_ref.ROTULO_E_NUMERO)
        refs = _refs_cruzadas(doc)
        checa(refs[2][0] == refs[0][0] and len(_marcadores_ref(doc)) == 2,
              "o mesmo trecho reaproveita o marcador _Ref")
        _inserir_ref(j, "Figura", 0, ed_ref.PAGINA)
        pagina = _refs_cruzadas(doc)[-1]
        caixa = _bloco_com_texto(doc, "Figura 1 – Figura A")
        checa(pagina[0].startswith(" PAGEREF _Ref") and pagina[0].endswith("\\h ")
              and pagina[1] == ts._pagina_esperada(p, caixa), f"PAGEREF: a folha da legenda: {pagina}")
        checa_igual(len(_marcadores_ref(doc)), 2, "e o PAGEREF usa o mesmo marcador (rotulo e numero)")
        _inserir_ref(j, "Figura", 2, ed_ref.LEGENDA_INTEIRA)
        checa_igual(_refs_cruzadas(doc)[-1][1], "Figura 3 – Figura C", "legenda inteira")
        _inserir_ref(j, "titulo", 0, ed_ref.TEXTO)
        checa_igual(_refs_cruzadas(doc)[-1][1], "Introdução", "titulo: o texto")
        _inserir_ref(j, "titulo", 1, ed_ref.PAGINA)
        ultimo = _refs_cruzadas(doc)[-1]
        checa(ultimo[1] == ts._pagina_esperada(p, _bloco_com_texto(doc, "Resultados"))
              and ultimo[1] != "1", f"titulo: o numero da pagina, depois da quebra: {ultimo}")
        _inserir_ref(j, "titulo", 0, ed_ref.NUMERO)
        ultimo = _refs_cruzadas(doc)[-1]
        checa(ultimo[0].endswith("\\r \\h ") and ultimo[1] == "0",
              f"titulo sem lista: \\r \\h e o resultado 0 (como o Word): {ultimo}")
        _inserir_ref(j, "marcador", 0, ed_ref.TEXTO)
        ultimo = _refs_cruzadas(doc)[-1]
        checa(ultimo[0] == " REF meu_marcador \\h " and ultimo[1] == "trecho marcado",
              f"marcador do usuario: o texto dele: {ultimo}")
        _inserir_ref(j, "marcador", 0, ed_ref.PAGINA, hiperlink=False)
        checa_igual(_refs(doc)[-1][0], " PAGEREF meu_marcador ", "sem hiperlink: sem \\h")
        # Um passo de desfazer: o campo e o marcador novo somem juntos.
        marcadores_antes = len(_marcadores_ref(doc))
        refs_antes = len(_refs(doc))
        texto_antes = doc.toPlainText()
        _inserir_ref(j, "Figura", 1, ed_ref.ROTULO_E_NUMERO)
        checa_igual((len(_refs(doc)), len(_marcadores_ref(doc))), (refs_antes + 1, marcadores_antes + 1),
                    "uma referencia e um marcador a mais")
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual((doc.toPlainText(), len(_refs(doc)), len(_marcadores_ref(doc))),
                    (texto_antes, refs_antes, marcadores_antes), "um Ctrl+Z desfaz o campo e o marcador")
        _tecla(p, Qt.Key.Key_Y, ctrl)
        checa_igual(len(_refs(doc)), refs_antes + 1, "Ctrl+Y refaz")
        _tecla(p, Qt.Key.Key_Z, ctrl)
        # Nada sozinho: mover a Figura C para o alto, mudar o titulo e atualizar os campos.
        imagens = _blocos_com_imagem(doc)
        _mover_para(doc, imagens[2], imagens[2].next(), imagens[0].position())
        titulo = _bloco_com_texto(doc, "Introdução")
        c = QTextCursor(doc)
        c.setPosition(titulo.position() + 4)
        c.insertText("XX")
        drenar_eventos(2)
        antes_f9 = _refs(doc)
        checa(antes_f9[0][1] == "Figura 1" and antes_f9[5][1] == "Introdução",
              "nenhuma referencia se atualiza sozinha")
        titulo_novo = _limpo(_bloco_com_texto(doc, "XX").text())
        _tecla(p, Qt.Key.Key_F9)
        depois = _refs(doc)
        checa_igual([depois[0][1], depois[1][1], depois[2][1]], ["Figura 2", "2", "Figura 2"],
                    "F9: a Figura A passou a ser a 2 (os tres REF dela)")
        checa_igual(depois[4][1], "Figura 1 – Figura C", "a legenda inteira da C passou a Figura 1")
        checa_igual(depois[5][1], titulo_novo, "o texto do titulo editado")
        checa_igual(depois[8][1], "trecho marcado", "o marcador do usuario nao mudou")
        checa_igual(depois[3][1], ts._pagina_esperada(p, _bloco_com_texto(doc, "Figura 2 – Figura A")),
                    "o PAGEREF da legenda A: a folha de agora")
        # Contraprova: sem a funcao que le o marcador, F9 nao muda os REF.
        c = QTextCursor(doc)
        c.setPosition(_bloco_com_texto(doc, "XX").position() + 4)
        c.insertText("YY")
        original = ed_ref._texto_do_trecho
        ed_ref._texto_do_trecho = lambda *_a: "velho"
        try:
            _tecla(p, Qt.Key.Key_F9)
            checa(_refs(doc)[5][1] == "velho", "contraprova: o resultado vem da leitura do marcador")
        finally:
            ed_ref._texto_do_trecho = original
        _tecla(p, Qt.Key.Key_F9)
        checa(_refs(doc)[5][1] == _limpo(_bloco_com_texto(doc, "YY").text()),
              "e F9 de novo traz o texto certo")
        # Salvar, validar e reabrir.
        final = _refs(doc)
        partes = _partes_salvas(j, arquivo)
        checa_igual(ordem.validar(partes), [], "o pacote salvo passa no validador")
        raiz = etree.fromstring(partes["word/document.xml"])
        instrs = raiz.xpath("//w:instrText/text()", namespaces=NS)
        usados = {re.match(r"\s*(?:REF|PAGEREF)\s+(\S+)", t).group(1) for t in instrs
                  if re.match(r"\s*(?:REF|PAGEREF)\s", t)}
        nomes = set(raiz.xpath("//w:bookmarkStart/@w:name", namespaces=NS))
        checa(usados and usados <= nomes, f"todo REF e PAGEREF cita um marcador que existe ({len(usados)})")
        checa(all(t.endswith("\\h ") for t in instrs if "meu_marcador" not in t and re.match(r"\s*(?:REF|PAGEREF)", t)),
              "com \\h")
        modelo2, avisos = ler(arquivo.read_bytes())
        checa_igual(avisos, [], "o arquivo salvo abre sem aviso")
        conferencia.conferir(arquivo.read_bytes(), j._modelo_atual())
        checa(True, "a conferencia pos-gravacao aceita")
        _fechar(gerente)
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        doc = j.painel.documento_corpo()
        checa_igual(_refs(doc), final, "reaberto: as mesmas referencias")
        dados1 = escrever(j._modelo_atual())
        checa(dados1 == escrever(ler(dados1)[0]), "reaberto e salvo de novo: os mesmos bytes")
        _fechar(gerente)


# -- sumario: numero de lista, \t, \b e o titulo ---------------------------------------------------------

def _documento_de_titulos() -> Documento:
    ps = [Paragrafo(runs=[Run("Introdução")], estilo="Heading1")] + _filler("a", 3)
    ps += [Paragrafo(runs=[Run("Contexto")], estilo="Heading2")] + _filler("b", 3)
    ps += [Paragrafo(runs=[Run("Resultados")], estilo="Heading1", quebra_antes=True)] + _filler("c", 3)
    return Documento(paragrafos=ps, estilos=catalogo_padrao())


def _linhas_do_sumario(doc) -> list[str]:
    import teste_sumario as ts
    return ts._linhas(doc)


def testar_sumario_numerado_e_titulo() -> None:
    secao("sumario: numero de lista do titulo na linha, titulo 'Sumario' opcional")
    from PySide6.QtCore import Qt

    from editdoc import configuracao
    from editdoc.edicao import sumario as ed
    from editdoc.formato_docx import conferencia
    from editdoc.interface.gerente import GerenteDeJanelas
    from editdoc.ponte_qt import estilos as pq_estilos
    from editdoc.ponte_qt import propriedades as pq_props

    ctrl = Qt.KeyboardModifier.ControlModifier
    with pasta_temporaria() as tmp:
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, arquivo = _abrir_janela(gerente, _documento_de_titulos(), tmp)
        p = j.painel
        doc = p.documento_corpo()
        # Sem lista: a linha e' so' o texto, como antes.
        _cursor_em(p, _bloco_com_texto(doc, "a 2"), fim=True)
        j.comandos.acao("inserir_sumario").trigger()
        drenar_eventos(2)
        checa(all(not x[0].isdigit() for x in _linhas_do_sumario(doc)),
              f"titulos sem lista: sem numero na linha {_linhas_do_sumario(doc)}")
        _tecla(p, Qt.Key.Key_Z, ctrl)
        # Com a lista de titulos numerados.
        _cursor_em(p, _bloco_com_texto(doc, "Introdução"))
        j.comandos.acao("multinivel_titulos").trigger()  # liga a lista aos estilos Titulo 1 a 9
        drenar_eventos(2)
        _cursor_em(p, _bloco_com_texto(doc, "a 2"), fim=True)
        j.comandos.acao("inserir_sumario").trigger()
        drenar_eventos(2)
        linhas = _linhas_do_sumario(doc)
        titulos = ed.titulos(doc, mod_sum.opcoes_da_instrucao(mod_sum.INSTRUCAO_PADRAO),
                             fora=(ed.sumarios(doc)[0][0], ed.sumarios(doc)[0][1]))
        numeros = [t[3] for t in titulos]
        checa(len(numeros) == 3 and all(numeros), f"os titulos tem numero de lista: {numeros}")
        checa_igual([x.split("\t")[:2] for x in linhas],
                    [[numeros[0], "Introdução"], [numeros[1], "Contexto"], [numeros[2], "Resultados"]],
                    f"a linha: numero, tabulacao, texto e (depois) a pagina: {linhas}")
        checa(all(len(x.split("\t")) == 3 for x in linhas), "e a pagina depois de outra tabulacao")
        bloco_linha = doc.findBlock(ed.sumarios(doc)[0][0] + 1)
        extras = pq_props.extras_de_ppr(bloco_linha.blockFormat()) or ""
        checa('w:val="left"' in extras and 'w:pos="440"' in extras and 'w:leader="dot"' in extras,
              "a primeira linha: tabulacao a esquerda em 440 e a direita com pontilhado")
        segunda = pq_props.extras_de_ppr(bloco_linha.next().blockFormat()) or ""
        checa('w:pos="880"' in segunda, "o nivel 2: a tabulacao a esquerda em 880")
        antes = doc.toPlainText()
        # Atualizar repete.
        j.comandos.acao("atualizar_sumario").trigger()
        drenar_eventos(2)
        checa_igual(_linhas_do_sumario(doc), linhas, "atualizar: as mesmas linhas, com o numero")
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(doc.toPlainText(), antes, "um Ctrl+Z devolve o sumario de antes")
        # Salvar e reabrir.
        partes = _partes_salvas(j, arquivo)
        checa_igual(ordem.validar(partes), [], "o pacote salvo passa no validador")
        raiz = etree.fromstring(partes["word/document.xml"])
        tabs = raiz.xpath("//w:p[w:pPr/w:pStyle[starts-with(@w:val,'TOC')]]/w:pPr/w:tabs", namespaces=NS)
        checa(len(tabs) == 3 and all(len(t) == 2 for t in tabs), "duas tabulacoes em cada linha")
        conferencia.conferir(arquivo.read_bytes(), j._modelo_atual())
        checa(True, "a conferencia aceita")
        _fechar(gerente)

        # Titulo "Sumario".
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, arquivo = _abrir_janela(gerente, _documento_de_titulos(), tmp, "titulo.docx")
        p = j.painel
        doc = p.documento_corpo()
        texto_antes = doc.toPlainText()
        _cursor_em(p, doc.begin())
        j.comandos.acao("inserir_sumario_com_titulo").trigger()
        drenar_eventos(2)
        primeiro = doc.begin()
        checa_igual(primeiro.text(), "Sumário", "o titulo 'Sumario' no alto")
        cat = pq_estilos.catalogo(doc)
        checa_igual(pq_estilos.estilo_do_bloco(primeiro.blockFormat()), cat.por_nome("toc heading").id,
                    "no estilo Titulo do Sumario")
        checa(pq_estilos.nivel_do_bloco(primeiro) is None,
              "o titulo do sumario nao e' titulo (outlineLvl 9): fica fora das entradas")
        linhas = _linhas_do_sumario(doc)
        checa_igual([x.split("\t")[0] for x in linhas], ["Introdução", "Contexto", "Resultados"],
                    "as entradas sao so' os tres titulos")
        j.comandos.acao("atualizar_sumario").trigger()
        drenar_eventos(2)
        checa_igual([x.split("\t")[0] for x in _linhas_do_sumario(doc)],
                    ["Introdução", "Contexto", "Resultados"], "atualizar: o titulo do sumario nao entra")
        checa_igual(doc.begin().text(), "Sumário", "e o titulo continua")
        _tecla(p, Qt.Key.Key_Z, ctrl)
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(doc.toPlainText(), texto_antes, "dois Ctrl+Z devolvem o documento (inserir e atualizar)")
        checa(pq_estilos.catalogo(doc).por_nome("toc heading") is None, "sem o estilo criado")
        _tecla(p, Qt.Key.Key_Y, ctrl)
        partes = _partes_salvas(j, arquivo)
        checa_igual(ordem.validar(partes), [], "o pacote com o titulo passa no validador")
        estilos = etree.fromstring(partes["word/styles.xml"])
        estilo = estilos.xpath("//w:style[w:name/@w:val='TOC Heading']", namespaces=NS)
        checa(len(estilo) == 1 and estilo[0].xpath("w:pPr/w:outlineLvl/@w:val", namespaces=NS) == ["9"],
              "styles.xml: TOC Heading com outlineLvl 9")
        _fechar(gerente)


def _documento_com_estilos_e_trecho() -> tuple[Documento, str]:
    """O sumario com \\t (Legenda no nivel 2) e outro com \\b (so' o trecho do marcador)."""
    cat = catalogo_padrao()
    cat.garantir("caption")
    legenda = cat.por_nome("caption").id

    def toc(instrucao: str) -> list:
        return [Paragrafo(runs=[Run(marca=MarcaCampo("inicio", mod_sum.campo_toc(instrucao))),
                                Run("velho")]),
                Paragrafo(runs=[Run(marca=MarcaCampo("fim"))])]
    ps = toc(' TOC \\o "1-1" \\t "Legenda;2" \\h \\z ')
    ps += [Paragrafo(runs=[Run("Um")], estilo="Heading1")]
    ps += [Paragrafo(runs=[Run("Legenda do primeiro")], estilo=legenda)] + _filler("a", 2)
    ps += [Paragrafo(runs=[Run("Dois")], estilo="Heading1")]
    ps += [Paragrafo(runs=[Run("Legenda do segundo")], estilo=legenda)]
    ps += [Paragrafo(runs=[Run("Titulo 2 fora do 1-1")], estilo="Heading2")]
    return Documento(paragrafos=ps, estilos=cat), legenda


def testar_t_e_b() -> None:
    secao("sumario: \\t (estilos extras com nivel) e \\b (so' o trecho de um marcador)")
    from PySide6.QtCore import Qt

    from editdoc import configuracao
    from editdoc.interface.gerente import GerenteDeJanelas
    from editdoc.ponte_qt import estilos as pq_estilos

    ctrl = Qt.KeyboardModifier.ControlModifier
    modelo, _legenda = _documento_com_estilos_e_trecho()
    with pasta_temporaria() as tmp:
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, arquivo = _abrir_janela(gerente, modelo, tmp)
        p = j.painel
        doc = p.documento_corpo()
        _cursor_em(p, doc.begin())
        j.comandos.acao("atualizar_sumario").trigger()
        drenar_eventos(2)
        linhas = _linhas_do_sumario(doc)
        checa_igual([x.split("\t")[0] for x in linhas],
                    ["Um", "Legenda do primeiro", "Dois", "Legenda do segundo"],
                    f"\\o 1-1 e \\t Legenda;2: titulos e legendas na ordem do documento: {linhas}")
        cat = pq_estilos.catalogo(doc)
        ids = [pq_estilos.estilo_do_bloco(doc.findBlockByNumber(n).blockFormat()) for n in range(4)]
        checa_igual(ids, [cat.por_nome("toc 1").id, cat.por_nome("toc 2").id, cat.por_nome("toc 1").id,
                          cat.por_nome("toc 2").id], "as linhas no estilo do nivel (toc 1, toc 2)")
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa(_linhas_do_sumario(doc) == ["velho"], "um Ctrl+Z volta ao sumario de antes")
        _fechar(gerente)

    # \b: o marcador cobre so' "Dois" e a legenda dele.
    cat = catalogo_padrao()
    cat.garantir("caption")
    ps = [Paragrafo(runs=[Run(marca=MarcaCampo("inicio", mod_sum.campo_toc(
        ' TOC \\o "1-3" \\b trecho \\h \\z '))), Run("velho")]),
        Paragrafo(runs=[Run(marca=MarcaCampo("fim"))]),
        Paragrafo(runs=[Run("Fora antes")], estilo="Heading1"),
        Paragrafo(runs=[Run(marca=Marcador("inicio", "trecho")), Run("Dentro um")], estilo="Heading1"),
        Paragrafo(runs=[Run("Dentro dois")], estilo="Heading2"),
        Paragrafo(runs=[Run("Dentro tres"), Run(marca=Marcador("fim", "trecho"))], estilo="Heading2"),
        Paragrafo(runs=[Run("Fora depois")], estilo="Heading1")]
    with pasta_temporaria() as tmp:
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, arquivo = _abrir_janela(gerente, Documento(paragrafos=ps, estilos=cat), tmp)
        p = j.painel
        doc = p.documento_corpo()
        _cursor_em(p, doc.begin())
        j.comandos.acao("atualizar_sumario").trigger()
        drenar_eventos(2)
        checa_igual([x.split("\t")[0] for x in _linhas_do_sumario(doc)],
                    ["Dentro um", "Dentro dois", "Dentro tres"], "\\b trecho: so' o que esta' no marcador")
        # Marcador que sumiu: avisa e nao mexe.
        mensagens: list[str] = []
        p.mensagem.connect(mensagens.append)
        _fechar(gerente)

    # Contraprova: sem o \b, entram os cinco titulos.
    ps[0] = Paragrafo(runs=[Run(marca=MarcaCampo("inicio", mod_sum.campo_toc(' TOC \\o "1-3" \\h \\z '))),
                            Run("velho")])
    with pasta_temporaria() as tmp:
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, arquivo = _abrir_janela(gerente, Documento(paragrafos=ps, estilos=cat), tmp)
        doc = j.painel.documento_corpo()
        _cursor_em(j.painel, doc.begin())
        j.comandos.acao("atualizar_sumario").trigger()
        drenar_eventos(2)
        checa_igual(len(_linhas_do_sumario(doc)), 5, "contraprova: sem \\b, os cinco titulos")
        _fechar(gerente)


def testar_tabela_nas_pontas() -> None:
    secao("legenda da tabela no comeco e no fim do documento (blocos estruturais do Qt)")
    from PySide6.QtCore import Qt

    from editdoc import configuracao
    from editdoc.interface.gerente import GerenteDeJanelas

    ctrl = Qt.KeyboardModifier.ControlModifier
    modelo = Documento(paragrafos=[_tabela("tc")] + _filler("meio", 2) + [_tabela("td")],
                       estilos=catalogo_padrao())
    with pasta_temporaria() as tmp:
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, arquivo = _abrir_janela(gerente, modelo, tmp)
        p = j.painel
        doc = p.documento_corpo()
        texto_antes = doc.toPlainText()
        blocos_antes = doc.blockCount()
        _inserir_legenda(j, _bloco_com_texto(doc, "tc00"), rotulo="Tabela", posicao="acima",
                         texto="No comeco")
        _inserir_legenda(j, _bloco_com_texto(doc, "td00"), rotulo="Tabela", posicao="abaixo",
                         texto="No fim")
        checa_igual(_legendas(doc), [("Tabela 1 – No comeco", "1"), ("Tabela 2 – No fim", "2")],
                    "as duas legendas, na ordem")
        checa_igual(_limpo(doc.begin().text()), "Tabela 1 – No comeco",
                    "a primeira legenda e' o primeiro bloco (usou o bloco estrutural, sem vazio sobrando)")
        ultimo = doc.lastBlock()
        checa_igual(_limpo(ultimo.text()), "Tabela 2 – No fim", "e a segunda e' o ultimo")
        checa_igual(doc.blockCount() - blocos_antes, 0,
                    "nenhum bloco a mais: as duas legendas ocuparam os blocos estruturais")
        partes = _partes_salvas(j, arquivo)
        checa_igual(ordem.validar(partes), [], "o pacote salvo passa no validador")
        raiz = etree.fromstring(partes["word/document.xml"])
        corpo = raiz.find(f"{{{W}}}body")
        filhos = [etree.QName(x).localname for x in corpo]
        checa_igual(filhos[:2], ["p", "tbl"], "no arquivo: a legenda e depois a tabela")
        checa(filhos[-2:] == ["tbl", "p"] or filhos[-3:-1] == ["tbl", "p"], "e a tabela e depois a legenda")
        _tecla(p, Qt.Key.Key_Z, ctrl)
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(doc.toPlainText(), texto_antes, "dois Ctrl+Z devolvem o documento")
        _fechar(gerente)


# -- faixa e dialogos -------------------------------------------------------------------------------

def testar_faixa_e_dialogos() -> None:
    secao("faixa e dialogos: nomes de todo controle, ordem de Tab, comandos na aba Referencias")
    from PySide6.QtWidgets import QToolButton

    import teste_acessibilidade as ta
    from editdoc import configuracao
    from editdoc.interface import dialogo_legendas
    from editdoc.interface.gerente import GerenteDeJanelas

    with pasta_temporaria() as tmp:
        modelo = documento()
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, _arq = _abrir_janela(gerente, modelo, tmp)
        _com_tres_figuras(j)
        doc = j.painel.documento_corpo()
        rotulos = [b.text() for b in j.faixa._referencias.findChildren(QToolButton)]
        for esperado in ("Inserir Legenda", "Referência Cruzada", "Atualizar Campos",
                         "Índice de Ilustrações ▾", "Sumário ▾"):
            checa(esperado in rotulos, f"a aba Referencias tem '{esperado}'")
        nomes = {b.accessibleName() for b in j.faixa._referencias.findChildren(QToolButton)}
        for inicio in ("Inserir uma legenda", "Inserir uma referência", "Atualizar os números das "
                       "legendas", "Índice de Ilustrações"):
            checa(any(n.startswith(inicio) for n in nomes), f"nome acessivel do botao: {inicio}...")
        faltam = ta.nomes_faltando(j)
        checa(not faltam, "nenhum controle da janela sem nome" + (f" ({faltam[:5]})" if faltam else ""))
        with ta.Capturador() as capt:
            dialogo_legendas.pedir_legenda(None, ["Figura", "Tabela", "Equação"], {"figura": 4}, "Figura")
            dialogo_legendas.pedir_indice_de_figuras(None, ["Figura", "Tabela"])
            dialogo_legendas.pedir_referencia(None, doc)
        checa_igual(len(capt.dialogos), 3, "os tres dialogos novos foram examinados")
        d = dialogo_legendas.DialogoLegenda(None, ["Figura", "Tabela", "Equação"], {"figura": 4},
                                            "Figura")
        checa_igual(d.exemplo.text(), "Figura 4", "o exemplo mostra o proximo numero")
        d.texto.setText("a")
        checa_igual(d.exemplo.text(), "Figura 4 – a", "e o texto depois do numero")
        d.rotulo.setCurrentText("Tabela")
        checa_igual(d.posicao.currentData(), "acima", "Tabela: a legenda em cima (padrao do Word)")
        d.rotulo.setCurrentText("Figura")
        checa_igual(d.posicao.currentData(), "abaixo", "Figura: embaixo")
        d.sem_rotulo.setChecked(True)
        checa_igual(d.escolha(), {"rotulo": "Figura", "posicao": "abaixo", "texto": "a",
                                  "com_rotulo": False}, "a escolha do dialogo")
        d.deleteLater()
        # Dialogo de referencia: trocar o tipo troca as opcoes e os itens.
        from editdoc.interface.dialogo_legendas import DialogoReferencia
        r = DialogoReferencia(None, doc)
        r.tipo.setCurrentIndex(r.tipo.findData("Figura"))
        checa_igual([r.itens.item(i).text() for i in range(r.itens.count())],
                    ["Figura 1 – Figura A", "Figura 2 – Figura B", "Figura 3 – Figura C"],
                    "os itens da Figura")
        checa_igual([r.mostrar.itemData(i) for i in range(r.mostrar.count())],
                    ["rotulo_numero", "somente_numero", "inteira", "pagina"], "e o que mostrar")
        r.tipo.setCurrentIndex(r.tipo.findData("titulo"))
        checa_igual(r.mostrar.count(), 3, "titulo: texto, pagina e numero")
        r.deleteLater()
        # Sem nada para citar, a referencia cruzada avisa.
        _fechar(gerente)
        gerente = GerenteDeJanelas(configuracao.padrao())
        j, _arq = _abrir_janela(gerente, Documento(paragrafos=[Paragrafo(runs=[Run("so' texto")])],
                                                   estilos=catalogo_padrao()), tmp, "vazio.docx")
        mensagens = []
        j.statusBar().messageChanged.connect(mensagens.append)
        j.comandos.acao("referencia_cruzada").trigger()
        drenar_eventos()
        checa(mensagens and "não tem título" in mensagens[-1], "sem alvo: a barra de status avisa")
        _fechar(gerente)


def main() -> int:
    testar_modelo()
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    testar_inserir_e_desfazer()
    testar_mover_apagar_e_atualizar()
    testar_salvar_e_reabrir()
    testar_documento_do_word()
    testar_indice_de_ilustracoes()
    testar_referencia_cruzada()
    testar_sumario_numerado_e_titulo()
    testar_t_e_b()
    testar_tabela_nas_pontas()
    testar_faixa_e_dialogos()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
