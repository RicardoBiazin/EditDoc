"""Sumario (Referencias > Sumario): inserir, atualizar o inteiro e so' os numeros, como no Word.

- modelo: as opcoes da instrucao (\\o, \\h, \\n, \\u), o que o EditDoc nao reconstroi (\\t, \\f,
  \\c), o marcador do PAGEREF, nomes `_Toc` unicos e as linhas geradas;
- inserir: o campo TOC no cursor, em paragrafos proprios; uma linha por titulo 1 a 3 no estilo
  "toc N" (criado), com a tabulacao a direita com pontilhado, o hiperlink e o PAGEREF para o
  marcador `_Toc` que o titulo ganhou; o numero e' a folha do titulo DEPOIS de o sumario empurrar
  o texto (contraprova: sem a correcao, o numero fica o de antes e o teste acusa);
- desfazer: um Ctrl+Z devolve o texto, o catalogo de estilos e os titulos sem marcador; Ctrl+Y
  refaz;
- atualizar o inteiro depois de editar um titulo e mudar a paginacao: texto e numero novos, os
  mesmos marcadores; um Ctrl+Z volta ao sumario de antes;
- salvar e reabrir: validador do pacote, campo TOC com begin/separate/end, PAGEREF e hiperlink
  para cada marcador `_Toc` dos titulos, estilos "toc N" no styles.xml; reaberto, o mesmo sumario;
- so' os numeros: depois de empurrar um titulo, os numeros mudam e as linhas nao;
- sumario do Word: abrir e salvar sem atualizar da' o mesmo document.xml (c14n) que o escritor;
  atualizar reaproveita os marcadores do Word e grava um arquivo valido;
- Ctrl+clique na linha leva o cursor ao titulo;
- documento com tabela (layout por trechos, 0.1.31) e numeracao de secao em romanos.
"""

from __future__ import annotations

import contextlib
import re

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt, pular,
                       resumir, secao)
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import ordem  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo import sumario as mod  # noqa: E402
from editdoc.modelo.documento import (Celula, Documento, Linha, MarcaCampo, Paragrafo,  # noqa: E402
                                      Run, Tabela)
from editdoc.modelo.estilos import catalogo_padrao  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# -- modelo ---------------------------------------------------------------------------------------

def testar_modelo() -> None:
    secao("modelo: opcoes da instrucao, o que nao se reconstroi, PAGEREF e linhas")
    o = mod.opcoes_da_instrucao(mod.INSTRUCAO_PADRAO)
    checa_igual((o.primeiro, o.ultimo, o.links, o.sem_numero), (1, 3, True, ()),
                "\\o \"1-3\" \\h: niveis 1 a 3, com hiperlink, com numero")
    o = mod.opcoes_da_instrucao(' TOC \\o "2-4" \\n "3-3" ')
    checa_igual((o.primeiro, o.ultimo, o.links, o.sem_numero), (2, 4, False, (3,)),
                "\\o \"2-4\" sem \\h e com \\n \"3-3\"")
    o = mod.opcoes_da_instrucao(" TOC \\u \\n ")
    checa_igual((o.primeiro, o.ultimo, o.sem_numero), (1, 9, tuple(range(1, 10))),
                "sem \\o: titulos 1 a 9; \\n sem intervalo tira todos os numeros")
    checa_igual(mod.opcoes_da_instrucao(' TOC \\o "4-2" ').ultimo, 9, "intervalo invertido: o padrao")
    checa(mod.reconstruivel(mod.INSTRUCAO_PADRAO) == "", "o TOC padrao se reconstroi")
    for instr in (' TOC \\h \\z \\t "Meu;1" ', " TOC \\f \\h ", ' TOC \\h \\z \\c "Figura" ',
                  " TOC \\b trecho "):
        checa(mod.reconstruivel(instr) != "", f"nao reconstroi: {instr.strip()}")
    checa_igual(mod.marcador_do_pageref(" PAGEREF _Toc123 \\h "), "_Toc123", "marcador do PAGEREF")
    checa(mod.marcador_do_pageref(" REF _Toc123 \\h ") is None, "REF nao e' PAGEREF")
    usados = {"_Toc100000000"}
    nomes = {mod.nome_de_marcador(usados) for _ in range(5)}
    checa(len(nomes) == 5 and "_Toc100000000" not in nomes
          and all(re.fullmatch(r"_Toc\d{9}", n) for n in nomes), "nomes _Toc unicos de 9 digitos")
    checa_igual(mod.texto_do_titulo("￼Um titulo\tlongo￼ "), "Um titulo longo",
                "texto da linha sem marcas, quebra e tabulacao")
    entrada = mod.Entrada("Introdução", 1, "_Toc1", "3")
    p = mod.paragrafo_da_entrada(entrada, "TOC1", "<x/>", mod.opcoes_da_instrucao(mod.INSTRUCAO_PADRAO))
    checa_igual(["".join(r.texto for r in p.runs), p.estilo, p.extras], ["Introdução\t3", "TOC1", "<x/>"],
                "linha: texto, tabulacao e numero no estilo do nivel, com a tabulacao nos extras")
    checa(all(r.link is not None and r.link.ancora == "_Toc1" for r in p.runs),
          "com \\h a linha inteira fica no hiperlink para o marcador")
    marcas = [r.marca for r in p.runs if isinstance(r.marca, MarcaCampo)]
    checa(len(marcas) == 2 and marcas[0].campo.instrucao() == " PAGEREF _Toc1 \\h ",
          "o numero e' o resultado de um PAGEREF")
    p = mod.paragrafo_da_entrada(entrada, "TOC1", "<x/>", mod.opcoes_da_instrucao(" TOC \\o \"1-3\" "))
    checa(all(r.link is None for r in p.runs), "contraprova: sem \\h, sem hiperlink")
    vazio = mod.paragrafos_do_sumario([], {}, None, mod.opcoes_da_instrucao(mod.INSTRUCAO_PADRAO))
    checa_igual("".join(r.texto for r in vazio[0].runs), mod.SEM_ENTRADAS, "sem titulos: o aviso do Word")


# -- documento de teste ---------------------------------------------------------------------------

def _filler(prefixo: str, n: int) -> list:
    return [Paragrafo(runs=[Run(f"{prefixo} {i} " + "palavra " * 14)]) for i in range(n)]


def documento(com_tabela: bool = False, curtas: int = 0) -> Documento:
    """Capa curta, `curtas` linhas curtas, a Introducao, Detalhes (nivel 2), um Titulo 4 (fora do
    sumario) e a Conclusao depois de uma quebra de pagina."""
    ps = [Paragrafo(runs=[Run("Capa do relatório")])]
    ps += _filler("antes", 12)
    ps += [Paragrafo(runs=[Run(f"linha curta {i}")]) for i in range(curtas)]
    ps.append(Paragrafo(runs=[Run("Introdução")], estilo="Heading1"))
    ps += _filler("texto", 10)
    if com_tabela:
        ps.append(Tabela(linhas=[Linha(celulas=[Celula(blocos=[Paragrafo(runs=[Run(f"c{i}{j}")])])
                                                for j in range(2)]) for i in range(3)],
                         colunas_tw=[4500, 4500]))
    ps.append(Paragrafo(runs=[Run("Detalhes do método")], estilo="Heading2"))
    ps += _filler("mais", 25)
    ps.append(Paragrafo(runs=[Run("Nota técnica")], estilo="Heading3", nivel=3))
    ps.append(Paragrafo(runs=[Run("Conclusão")], estilo="Heading1", quebra_antes=True))
    ps.append(Paragrafo(runs=[Run("fim")]))
    return Documento(paragrafos=ps, estilos=catalogo_padrao())


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


def _fechar(gerente) -> None:
    with dialogos(pedir_descartar=lambda *_a: "descartar"):
        for j in gerente.janelas():
            j.painel.documento_corpo().setModified(False)
            j.close()
    drenar_eventos()


def _abrir(gerente, caminho):
    j = gerente.abrir(str(caminho))
    drenar_eventos()
    j.painel.setFocus()
    return j


def _linhas(doc) -> list[str]:
    """Texto das linhas do sumario (sem as marcas), uma por paragrafo do resultado."""
    from editdoc.edicao import sumario as ed
    achado = ed.sumario_do_cursor(doc, 0)
    if achado is None:
        return []
    ini, fim, _campo = achado
    texto = doc.toPlainText()[ini:fim + 1]
    return [t.replace("￼", "") for t in texto.split("\n") if t.replace("￼", "")]


def _blocos_de_titulo(doc, nivel_max: int = 3) -> list:
    from editdoc.ponte_qt import estilos as pq_estilos
    saida = []
    b = doc.begin()
    while b.isValid():
        n = pq_estilos.nivel_do_bloco(b)
        if n is not None and n < nivel_max and b.text().replace("￼", "").strip():
            saida.append(b)
        b = b.next()
    return saida


def _pagina_esperada(painel, bloco) -> str:
    """A folha do titulo pela origem da primeira linha (outro caminho que o do comando), +1."""
    layout = painel.layout_pag
    painel.preparar_para_impressao()
    o = layout.origem_bloco(bloco)
    linha = bloco.layout().lineAt(0)
    y = o.y() + linha.y() + linha.height() / 2
    return str(layout.pagina_de_y(y) + 1)


def _esperado(painel) -> list[str]:
    doc = painel.documento_corpo()
    from editdoc.modelo.sumario import texto_do_titulo
    return [f"{texto_do_titulo(b.text())}\t{_pagina_esperada(painel, b)}"
            for b in _blocos_de_titulo(doc)]


def _marcadores_toc(doc) -> list[str]:
    from editdoc.ponte_qt import marcas as pq_marcas
    return [m.nome for _p, m in pq_marcas.posicoes_de_marcadores(doc)
            if m.tipo == "inicio" and m.nome.startswith("_Toc")]


def _introducao_no_pe(janela, com_tabela: bool) -> None:
    """Abre de novo o documento com o maximo de linhas curtas antes da Introducao que ainda a
    deixa na mesma folha (a medida da fonte muda entre o offscreen e o Windows): o sumario
    inserido no alto a empurra para a folha seguinte. Busca binaria, cada medida num documento
    recem-aberto (sem desfazer)."""
    def pagina(curtas: int) -> str:
        janela.carregar(documento(com_tabela, curtas), [], None)
        drenar_eventos(2)
        doc = janela.painel.documento_corpo()
        return _pagina_esperada(janela.painel, _blocos_de_titulo(doc)[0])

    inicial = pagina(0)
    baixo, alto = 0, 1
    while pagina(alto) == inicial and alto < 512:
        baixo, alto = alto, alto * 2
    while alto - baixo > 1:
        meio = (baixo + alto) // 2
        if pagina(meio) == inicial:
            baixo = meio
        else:
            alto = meio
    checa_igual(pagina(baixo), inicial, f"a Introducao no pe' da folha ({baixo} linhas curtas)")
    janela.painel.setFocus()


def _cursor_no_fim_do_primeiro(painel) -> None:
    c = painel.textCursor()
    c.setPosition(0)
    c.movePosition(c.MoveOperation.EndOfBlock)
    painel.setTextCursor(c)


def _tecla(painel, tecla, mod_=None) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.keyClick(painel, tecla, mod_ if mod_ is not None else Qt.KeyboardModifier.NoModifier)
    drenar_eventos(2)


# -- inserir, desfazer, atualizar, salvar ----------------------------------------------------------

def testar_inserir_e_desfazer(com_tabela: bool = False) -> None:
    secao("inserir: campo TOC, linhas, estilos, marcadores e numeros; um Ctrl+Z desfaz"
          + (" (documento com tabela)" if com_tabela else ""))
    from PySide6.QtCore import Qt

    from editdoc import configuracao
    from editdoc.edicao import sumario as ed
    from editdoc.interface.gerente import GerenteDeJanelas
    from editdoc.ponte_qt import estilos as pq_estilos

    ctrl = Qt.KeyboardModifier.ControlModifier
    with pasta_temporaria() as tmp:
        arquivo = tmp / "sumario.docx"
        arquivo.write_bytes(escrever(documento(com_tabela)))
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        _introducao_no_pe(j, com_tabela)
        p = j.painel
        doc = p.documento_corpo()
        if com_tabela:
            from editdoc.interface import trechos
            checa(isinstance(doc.documentLayout(), trechos.LayoutPorTrechos) or
                  not trechos.ligado(), "documento com tabela: layout por trechos (se ligado)")
        texto_antes = doc.toPlainText()
        pagina_antes = _pagina_esperada(p, _blocos_de_titulo(doc)[0])
        checa(pq_estilos.catalogo(doc).por_nome("toc 1") is None, "o documento nao tem Sumario 1")
        _cursor_no_fim_do_primeiro(p)
        mensagens: list[str] = []
        p.mensagem.connect(mensagens.append)
        j.comandos.acao("inserir_sumario").trigger()
        drenar_eventos(2)
        todos = ed.sumarios(doc)
        checa_igual(len(todos), 1, "um campo TOC no documento")
        checa_igual(todos[0][2].instrucao(), mod.INSTRUCAO_PADRAO, "a instrucao do Word: 1-3, \\h \\z \\u")
        linhas = _linhas(doc)
        esperado = _esperado(p)
        checa_igual(linhas, esperado, "uma linha por titulo 1 a 3 (o Titulo 4 fica de fora), com "
                    "a folha de cada titulo depois de o sumario empurrar o texto")
        checa(pagina_antes != esperado[0].split("\t")[1],
              "a Introducao mudou de pagina com o sumario (o caso que a correcao cobre)")
        checa(texto_antes.startswith(doc.toPlainText().split("\n")[0].replace("￼", "")),
              "o texto antes do cursor fica no paragrafo de fora")
        blocos = _blocos_de_titulo(doc)
        nomes = _marcadores_toc(doc)
        checa(len(nomes) == len(blocos) == 3 and len(set(nomes)) == 3,
              "cada titulo ganhou um marcador _Toc proprio")
        cat = pq_estilos.catalogo(doc)
        checa(cat.por_nome("toc 1") is not None and cat.por_nome("toc 2") is not None,
              "os estilos Sumario 1 e Sumario 2 foram criados")
        bloco_linha = doc.findBlock(todos[0][0])
        checa_igual(pq_estilos.estilo_do_bloco(bloco_linha.blockFormat()), cat.por_nome("toc 1").id,
                    "a primeira linha no estilo Sumario 1")
        from editdoc.ponte_qt import propriedades as pq_props
        extras = pq_props.extras_de_ppr(bloco_linha.blockFormat()) or ""
        checa('w:leader="dot"' in extras and 'w:val="right"' in extras,
              "tabulacao a direita com pontilhado na linha")
        checa(mensagens and "3 entradas" in mensagens[-1], "a barra de status conta as entradas")
        depois = doc.toPlainText()
        # Desfazer pela tecla: um passo devolve tudo.
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(doc.toPlainText(), texto_antes, "um Ctrl+Z devolve o texto de antes")
        checa(ed.sumarios(doc) == [] and _marcadores_toc(doc) == [],
              "sem o campo e sem os marcadores dos titulos")
        checa(pq_estilos.catalogo(doc).por_nome("toc 1") is None, "o catalogo volta sem Sumario 1")
        _tecla(p, Qt.Key.Key_Y, ctrl)
        checa_igual(doc.toPlainText(), depois, "Ctrl+Y refaz o sumario inteiro")
        checa_igual(_linhas(doc), esperado, "com os mesmos numeros")
        # Contraprova: sem a correcao dos numeros depois do layout, o teste acusa.
        _tecla(p, Qt.Key.Key_Z, ctrl)
        original = ed.RODADAS
        ed.RODADAS = 0
        try:
            _cursor_no_fim_do_primeiro(p)
            j.comandos.acao("inserir_sumario").trigger()
            drenar_eventos(2)
            checa(_linhas(doc) != _esperado(p),
                  "contraprova: sem corrigir depois do layout, o numero da Introducao fica errado")
        finally:
            ed.RODADAS = original
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(doc.toPlainText(), texto_antes, "e o desfazer limpa a contraprova")
        _fechar(gerente)


def _selecionar_texto(painel, texto: str) -> None:
    doc = painel.documento_corpo()
    plano = doc.toPlainText()
    # O titulo, nao a linha do sumario: a ultima ocorrencia.
    pos = plano.rindex(texto)
    c = painel.textCursor()
    c.setPosition(pos)
    c.setPosition(pos + len(texto), c.MoveMode.KeepAnchor)
    painel.setTextCursor(c)


def _digitar(painel, texto: str) -> None:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication
    for ch in texto:
        for tipo in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(painel, QKeyEvent(tipo, 0, Qt.KeyboardModifier.NoModifier, ch))
    drenar_eventos(2)


def testar_atualizar_salvar_reabrir() -> None:
    secao("atualizar o inteiro e so' os numeros; salvar, validar e reabrir")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor

    from editdoc import configuracao
    from editdoc.edicao import sumario as ed
    from editdoc.interface.gerente import GerenteDeJanelas

    ctrl = Qt.KeyboardModifier.ControlModifier
    with pasta_temporaria() as tmp:
        arquivo = tmp / "sumario.docx"
        arquivo.write_bytes(escrever(documento()))
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        p = j.painel
        doc = p.documento_corpo()
        _cursor_no_fim_do_primeiro(p)
        j.comandos.acao("inserir_sumario").trigger()
        drenar_eventos(2)
        nomes_antes = _marcadores_toc(doc)
        linhas_antes = _linhas(doc)
        # Editar um titulo e empurrar a Conclusao: 40 paragrafos antes dela.
        _selecionar_texto(p, "Conclusão")
        _digitar(p, "Conclusões finais")
        c = QTextCursor(doc)
        c.setPosition(doc.toPlainText().rindex("Nota técnica"))
        c.beginEditBlock()
        for i in range(40):
            c.insertText(f"linha extra {i} " + "palavra " * 10)
            c.insertBlock(c.blockFormat(), c.charFormat())
        c.endEditBlock()
        drenar_eventos(2)
        checa_igual(_linhas(doc), linhas_antes, "o sumario nao se atualiza sozinho")
        c = p.textCursor()
        c.setPosition(5)
        p.setTextCursor(c)
        j.comandos.acao("atualizar_sumario").trigger()
        drenar_eventos(2)
        esperado = _esperado(p)
        checa_igual(_linhas(doc), esperado, "atualizar o inteiro: o titulo editado e as paginas novas")
        checa("Conclusões finais" in esperado[-1] and esperado[-1] != linhas_antes[-1].replace(
            "Conclusão", "Conclusões finais"), "o titulo e a pagina da Conclusao mudaram")
        checa_igual(_marcadores_toc(doc), nomes_antes, "os titulos continuam com os mesmos marcadores")
        checa_igual(len(ed.sumarios(doc)), 1, "continua um campo so'")
        atualizado = doc.toPlainText()
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(_linhas(doc), linhas_antes, "um Ctrl+Z volta ao sumario de antes da atualizacao")
        _tecla(p, Qt.Key.Key_Y, ctrl)
        checa_igual(doc.toPlainText(), atualizado, "Ctrl+Y refaz a atualizacao")
        # So' os numeros: empurrar a Conclusao de novo.
        c = QTextCursor(doc)
        c.setPosition(doc.toPlainText().rindex("Nota técnica"))
        c.beginEditBlock()
        for i in range(45):
            c.insertText(f"outra linha {i} " + "palavra " * 10)
            c.insertBlock(c.blockFormat(), c.charFormat())
        c.endEditBlock()
        drenar_eventos(2)
        velhas = _linhas(doc)
        esperado = _esperado(p)
        checa(velhas != esperado, "contraprova: depois de empurrar, o numero do sumario ficou velho")
        blocos = doc.blockCount()
        j.comandos.acao("atualizar_numeros_sumario").trigger()
        drenar_eventos(2)
        checa_igual(_linhas(doc), esperado, "so' os numeros: as paginas certas de novo")
        checa(doc.blockCount() == blocos and [x.split("\t")[0] for x in _linhas(doc)]
              == [x.split("\t")[0] for x in velhas], "e as linhas (texto e quantidade) ficaram")
        _tecla(p, Qt.Key.Key_Z, ctrl)
        checa_igual(_linhas(doc), velhas, "um Ctrl+Z desfaz so' a troca dos numeros")
        _tecla(p, Qt.Key.Key_Y, ctrl)
        final = _linhas(doc)
        # Salvar (com a conferencia pos-gravacao) e conferir o XML.
        perdas: list = []
        with dialogos(pedir_perda=lambda _p, _n, linhas: perdas.append(linhas) or "salvar"):
            checa(j.salvar() is True, "salvar grava (a conferencia aceita o sumario)")
        partes = fx.partes_de(arquivo.read_bytes())
        checa_igual(ordem.validar(partes), [], "o pacote salvo passa no validador")
        xml = partes["word/document.xml"].decode("utf-8")
        tipos = re.findall(r'w:fldCharType="(\w+)"', xml)
        n = len(final)
        checa_igual((tipos.count("begin"), tipos.count("separate"), tipos.count("end")),
                    (n + 1, n + 1, n + 1), "begin, separate e end: o TOC e um PAGEREF por linha")
        checa(re.search(r'<w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText>',
                        xml) is not None, "o codigo do TOC com xml:space")
        raiz = etree.fromstring(partes["word/document.xml"])
        ns = {"w": W}
        ancoras = raiz.xpath("//w:hyperlink/@w:anchor", namespaces=ns)
        pagerefs = [re.match(r"\s*PAGEREF\s+(\S+)", t).group(1)
                    for t in raiz.xpath("//w:instrText/text()", namespaces=ns) if "PAGEREF" in t]
        marcadores = raiz.xpath("//w:bookmarkStart/@w:name", namespaces=ns)
        checa(len(ancoras) == n and ancoras == pagerefs and set(ancoras) <= set(marcadores),
              "cada linha: hiperlink e PAGEREF para um marcador que existe")
        titulos_com_marca = raiz.xpath("//w:p[w:pPr/w:pStyle[starts-with(@w:val,'Heading')]]"
                                       "[w:bookmarkStart[starts-with(@w:name,'_Toc')]]", namespaces=ns)
        checa_igual(len(titulos_com_marca), n, "os marcadores _Toc estao nos paragrafos de titulo")
        tabs = raiz.xpath("//w:p[w:pPr/w:pStyle[starts-with(@w:val,'TOC')]]/w:pPr/w:tabs/w:tab",
                          namespaces=ns)
        checa(len(tabs) == n and all(t.get(f"{{{W}}}leader") == "dot"
                                     and t.get(f"{{{W}}}val") == "right" for t in tabs),
              "a tabulacao a direita com pontilhado em cada linha")
        estilos = etree.fromstring(partes["word/styles.xml"])
        nomes_estilo = estilos.xpath("//w:style/w:name/@w:val", namespaces=ns)
        checa("toc 1" in nomes_estilo and "toc 2" in nomes_estilo, "styles.xml com toc 1 e toc 2")
        _modelo, avisos = ler(arquivo.read_bytes())
        checa_igual(avisos, [], "o arquivo salvo abre sem aviso")
        _fechar(gerente)
        # Reabrir.
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        doc = j.painel.documento_corpo()
        checa_igual(_linhas(doc), final, "reaberto: o mesmo sumario")
        checa_igual(len(ed.sumarios(doc)), 1, "reaberto: o campo TOC continua campo")
        checa_igual(len(_marcadores_toc(doc)), n, "reaberto: os marcadores dos titulos")
        dados1 = escrever(j._modelo_atual())
        checa(dados1 == escrever(ler(dados1)[0]), "reaberto e salvo de novo: os mesmos bytes")
        _fechar(gerente)


def testar_ctrl_clique() -> None:
    secao("Ctrl+clique na linha do sumario leva ao titulo")
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    from editdoc import configuracao
    from editdoc.interface.gerente import GerenteDeJanelas

    with pasta_temporaria() as tmp:
        arquivo = tmp / "sumario.docx"
        arquivo.write_bytes(escrever(documento()))
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        p = j.painel
        doc = p.documento_corpo()
        _cursor_no_fim_do_primeiro(p)
        j.comandos.acao("inserir_sumario").trigger()
        drenar_eventos(2)
        plano = doc.toPlainText()
        linha = plano.index("Detalhes do método")
        titulo = plano.rindex("Detalhes do método")
        p.ir_para_posicao(linha)
        drenar_eventos(2)
        ini = p.layout_pag.retangulo_cursor(linha + 2)
        fim = p.layout_pag.retangulo_cursor(linha + 3)
        m = p._mapa()
        x, y = m.doc_para_tela((ini.x() + fim.x()) / 2, ini.y() + ini.height() / 2, p._paginas())
        vp = p.viewport()
        QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPointF(x, y).toPoint())
        checa(doc.findBlock(p.textCursor().position()).position() == doc.findBlock(linha).position(),
              "clique sem Ctrl fica na linha do sumario")
        QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                         QPointF(x, y).toPoint())
        drenar_eventos(2)
        checa_igual(p.textCursor().position(), titulo, "Ctrl+clique: o cursor vai ao titulo")
        _fechar(gerente)


# -- sumario do Word -------------------------------------------------------------------------------

def _paragrafos_c14n(xml: bytes, quantos: int) -> list[bytes]:
    corpo = etree.fromstring(xml).find(f"{{{W}}}body")
    return [etree.tostring(p, method="c14n") for p in list(corpo)[:quantos]]


def testar_sumario_do_word() -> None:
    secao("sumario do Word: preservado sem atualizar; atualizar reaproveita os marcadores")
    from editdoc import configuracao
    from editdoc.edicao import sumario as ed
    from editdoc.interface.gerente import GerenteDeJanelas

    origem = fx.docx_com_campos()
    direto = escrever(ler(origem)[0])
    with pasta_temporaria() as tmp:
        arquivo = tmp / "word.docx"
        arquivo.write_bytes(origem)
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        doc = j.painel.documento_corpo()
        checa_igual(len(ed.sumarios(doc)), 1, "o TOC do Word e' reconhecido como sumario")
        salvo = escrever(j._modelo_atual())
        a = fx.partes_de(salvo)["word/document.xml"]
        b = fx.partes_de(direto)["word/document.xml"]
        checa_igual(etree.tostring(etree.fromstring(a), method="c14n"),
                    etree.tostring(etree.fromstring(b), method="c14n"),
                    "abrir e salvar sem atualizar: o document.xml do escritor, em c14n")
        o3 = _paragrafos_c14n(fx.partes_de(origem)["word/document.xml"], 3)
        s3 = _paragrafos_c14n(a, 3)
        checa_igual(s3, o3, "os tres paragrafos do sumario voltam como o Word gravou (c14n)")
        estilos_a = fx.partes_de(salvo)["word/styles.xml"]
        estilos_b = fx.partes_de(direto)["word/styles.xml"]
        checa(estilos_a == estilos_b, "e o styles.xml tambem (nenhum estilo criado)")
        # Atualizar o inteiro.
        c = j.painel.textCursor()
        c.setPosition(3)
        j.painel.setTextCursor(c)
        j.comandos.acao("atualizar_sumario").trigger()
        drenar_eventos(2)
        linhas = _linhas(doc)
        checa_igual([x.split("\t")[0] for x in linhas], ["Introdução", "Conclusão"],
                    "as linhas a partir dos titulos (Titulo 1 do Word)")
        checa_igual(sorted(_marcadores_toc(doc)), ["_Toc1", "_Toc2"],
                    "os marcadores do Word sao reaproveitados (nenhum novo)")
        modelo = j._modelo_atual()
        dados = escrever(modelo)
        partes = fx.partes_de(dados)
        checa_igual(ordem.validar(partes), [], "o pacote atualizado passa no validador")
        xml = partes["word/document.xml"].decode("utf-8")
        checa(' TOC \\o "1-3" \\h \\z \\u ' in xml and " REF _Toc2 \\h " in xml,
              "o codigo do TOC e o REF de fora continuam")
        corpo = etree.fromstring(partes["word/document.xml"]).find(f"{{{W}}}body")
        terceiro = [f.get(f"{{{W}}}fldCharType") for f in corpo[2].iter(f"{{{W}}}fldChar")]
        checa_igual(terceiro, ["end"], "o fim do TOC continua no paragrafo proprio")
        relido, avisos = ler(dados)
        checa_igual(avisos, [], "o arquivo atualizado abre sem aviso")
        from editdoc.formato_docx import conferencia
        conferencia.conferir(dados, modelo)
        checa(True, "a conferencia aceita o sumario atualizado")
        _fechar(gerente)


def testar_secao_romana() -> None:
    secao("numero da pagina: o formato da secao (romanos) vale na linha, como o PAGE")
    from editdoc import configuracao
    from editdoc.interface.gerente import GerenteDeJanelas
    from editdoc.modelo.pagina import Pagina

    modelo = documento()
    modelo.pagina = Pagina(formato_numero="lowerRoman")
    with pasta_temporaria() as tmp:
        arquivo = tmp / "romano.docx"
        arquivo.write_bytes(escrever(modelo))
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        _cursor_no_fim_do_primeiro(j.painel)
        j.comandos.acao("inserir_sumario").trigger()
        drenar_eventos(2)
        numeros = [x.split("\t")[1] for x in _linhas(j.painel.documento_corpo())]
        checa(numeros and all(re.fullmatch(r"[ivxlc]+", n) for n in numeros),
              f"numeros em romanos minusculos: {numeros}")
        _fechar(gerente)


def testar_secao_que_recomeca() -> None:
    secao("numero da pagina: a secao que recomeca em 1 vale na linha (nao e' a folha)")
    from editdoc import configuracao
    from editdoc.interface.gerente import GerenteDeJanelas
    from editdoc.modelo.pagina import Pagina
    from editdoc.modelo.secoes import Secao

    modelo = documento()
    modelo.paragrafos[0].secao = Secao(pagina=Pagina(formato_numero="lowerRoman"))
    modelo.pagina = Pagina(numero_inicial=1)
    with pasta_temporaria() as tmp:
        arquivo = tmp / "secoes.docx"
        arquivo.write_bytes(escrever(modelo))
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        p = j.painel
        c = p.textCursor()
        c.setPosition(0)
        p.setTextCursor(c)
        j.comandos.acao("inserir_sumario").trigger()
        drenar_eventos(2)
        doc = p.documento_corpo()
        linhas = _linhas(doc)
        folha = _pagina_esperada(p, _blocos_de_titulo(doc)[0])
        checa(linhas and linhas[0] == "Introdução\t1" and folha != "1",
              f"a Introducao abre a secao 2, que recomeca em 1 (folha {folha}): {linhas}")
        checa(doc.findBlock(ed_sumarios(doc)[0][0]).blockNumber() == 0,
              "o sumario fica na secao 1, antes da capa")
        _fechar(gerente)


def ed_sumarios(doc):
    from editdoc.edicao import sumario as ed
    return ed.sumarios(doc)


def testar_fora_do_corpo_e_faixa() -> None:
    secao("faixa: grupo Sumario na aba Referencias; sem sumario, atualizar avisa")
    from editdoc import configuracao
    from editdoc.interface.gerente import GerenteDeJanelas
    from PySide6.QtWidgets import QToolButton

    with pasta_temporaria() as tmp:
        arquivo = tmp / "sem.docx"
        arquivo.write_bytes(escrever(documento()))
        gerente = GerenteDeJanelas(configuracao.padrao())
        j = _abrir(gerente, arquivo)
        rotulos = [b.text() for b in j.faixa._referencias.findChildren(QToolButton)]
        checa("Sumário ▾" in rotulos and "Atualizar Sumário" in rotulos,
              "a aba Referencias tem Sumario e Atualizar Sumario")
        mensagens: list[str] = []
        j.painel.mensagem.connect(mensagens.append)
        antes = j.painel.documento_corpo().toPlainText()
        j.comandos.acao("atualizar_sumario").trigger()
        drenar_eventos()
        checa(mensagens and "não tem sumário" in mensagens[-1]
              and j.painel.documento_corpo().toPlainText() == antes,
              "atualizar sem sumario: aviso e nada muda")
        _fechar(gerente)


def main() -> int:
    testar_modelo()
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    testar_inserir_e_desfazer()
    testar_inserir_e_desfazer(com_tabela=True)
    testar_atualizar_salvar_reabrir()
    testar_ctrl_clique()
    testar_sumario_do_word()
    testar_secao_romana()
    testar_secao_que_recomeca()
    testar_fora_do_corpo_e_faixa()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
