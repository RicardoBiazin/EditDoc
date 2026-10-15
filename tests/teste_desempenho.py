"""Desempenho da digitacao num documento pesado (0.1.8): o gate do M3 num "manual" gerado em codigo.

O manual sintetico imita o real que passava do gate na 0.1.7 (fora do repositorio): capa com
imagem de pagina inteira atras do texto e caixas de texto, cabecalho da primeira pagina vazio e
o padrao com imagem, sumario com links, PAGEREF e pontilhado, e corpo comprido. As verificacoes
que nao dependem do relogio vem primeiro (sao as que pegam a regressao em qualquer maquina):

- conferencia dos floats: a linha que o Qt desce de pagina ao lado de um float nao e' refeita a
  cada tecla (era refeita 6 vezes, com o documento inteiro conferido, a cada tecla);
- tiles por tecla: digitar no paragrafo da capa (um bloco da altura da folha) refaz so' a faixa
  da linha, e nao a folha inteira;
- a tela com cache e' igual a' tela refeita do zero, tecla a tecla (letra, quebra de linha,
  Backspace que puxa palavra, Enter), na capa, no sumario e no corpo;
- objetos flutuantes e cabecalho/rodape pintados uma vez e reaproveitados na tela; o PDF e a
  impressao continuam pintando de verdade;
- pontilhado da tabulacao num drawText so'; tamanho das marcas guardado por fonte;
- antes das ancoras da capa (0.1.11, o ponto de 95 ms do manual real): capa que reserva a folha
  inteira e sumario num controle de conteudo; a conferencia refaz o sumario numa chamada por
  tecla e, quando ele volta igual, a tela pintada fica no cache;
- p95 da digitacao (80 teclas, cada uma com a pintura) na capa, no sumario, no corpo e antes da
  capa: no gate (16 ms) ou, numa maquina mais lenta, perto do p95 de um documento simples do
  mesmo tamanho. Desde a 0.1.11: mediana de 3 rodadas intercaladas com o simples (a referencia
  da mesma hora), folga relativa com teto absoluto, e so' o ponto que passou do limite mede de
  novo (ate' 2 rodadas). O criterio tem contraprovas sem relogio (`testar_criterio_do_p95`).

Cada verificacao estrutural tem a contraprova: com a correcao desligada, ela acusa.
"""

from __future__ import annotations

import statistics
import time

from ajudantes import (checa, checa_igual, drenar_eventos, preparar_qt, resumir, secao,
                       usar_fonte_windows, usar_fontes_do_documento)
import fixtures_docx as fx

preparar_qt()

import teste_flutuantes as tf  # noqa: E402  (fixtures de objeto flutuante em codigo)
from PySide6.QtGui import QTextDocument  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402
from editdoc.modelo.pagina import Pagina  # noqa: E402

EMU = 635  # EMU por twip
PAGINA_MANUAL = Pagina(margem_sup_tw=1134, margem_inf_tw=1134, margem_esq_tw=839,
                       margem_dir_tw=567, cabecalho_tw=397, rodape_tw=493,
                       primeira_diferente=True)
GATE_MS = 16.0


def _p95(valores):
    valores = sorted(valores)
    return valores[min(len(valores) - 1, round(0.95 * (len(valores) - 1)))]


def _docx(corpo_xml: str, base: Documento, relacoes, partes) -> bytes:
    return fx.docx_com_corpo_de_objetos(corpo_xml, relacoes, partes, (), (("png", "image/png"),),
                                        documento=base)


def _sumario(linhas: int, controle: bool = False) -> str:
    tab = ('<w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9000"/></w:tabs></w:pPr>')
    corpo = ('<w:p><w:r><w:t>Sumário</w:t></w:r></w:p><w:p>' + tab + fx._fld("begin")
             + fx._instr(' TOC \\o "1-3" \\h \\z \\u ') + fx._fld("separate")
             + fx._linha_do_sumario("_Toc0", "Introdução ao sistema", "3") + '</w:p>')
    for i in range(1, linhas):
        corpo += ('<w:p>' + tab + fx._linha_do_sumario(f"_Toc{i}", f"Seção {i} do manual", str(3 + i))
                  + '</w:p>')
    corpo += '<w:p>' + fx._fld("end") + '</w:p>'
    if controle:
        # Como o Word grava o sumario (0.1.11): dentro de um controle de conteudo da galeria
        # "Table of Contents".
        corpo = ('<w:sdt><w:sdtPr><w:id w:val="-1350000"/><w:docPartObj>'
                 '<w:docPartGallery w:val="Table of Contents"/><w:docPartUnique/></w:docPartObj>'
                 '</w:sdtPr><w:sdtContent>' + corpo + '</w:sdtContent></w:sdt>')
    return corpo


def manual_sintetico(paragrafos: int = 260, titulo_tw: int = 11000, controle: bool = False) -> bytes:
    """Capa com objetos, sumario e corpo; cabecalho da primeira pagina vazio.

    `titulo_tw`: altura do titulo que empurra o texto. Com 15000 a reserva passa do pe' da
    pagina e vira a folha inteira, como no manual real (`manual_capa_cheia`)."""
    texto = [Paragrafo(runs=[Run(f"Parágrafo {i}. {tf.TEXTO}")]) for i in range(paragrafos)]
    base = Documento(
        pagina=PAGINA_MANUAL, paragrafos=texto,
        cabecalhos={"primeira": [Paragrafo()],
                    "padrao": [Paragrafo(runs=[fx.run_de_imagem(fx.imagem(fx.png(80, 20), 4.0, 1.0)),
                                               Run("  Manual do sistema")]),
                               Paragrafo(runs=[Run("Documentação")])]},
        rodapes={"padrao": [Paragrafo(runs=[Run("Página "), Run("1", campo="PAGE")])]})
    w, h = PAGINA_MANUAL.largura_tw, PAGINA_MANUAL.altura_tw
    capa = ('<w:p>'
            + tf.ancora(91, tf.URI_IMAGEM, tf.figura("rId81", w * EMU, h * EMU), w * EMU, h * EMU,
                        h=("page", "posOffset", 0), v=("page", "posOffset", 0),
                        quebra="<wp:wrapNone/>", atras=True)
            # O titulo empurra o texto do paragrafo para baixo dele (wrapTopAndBottom): o bloco da
            # ancora fica quase da altura da folha, como no manual real.
            + tf.ancora(92, tf.URI_FORMA, tf.forma(8000 * EMU, titulo_tw * EMU, cor="FFFFFF",
                                                   texto="Manual do sistema"),
                        8000 * EMU, titulo_tw * EMU, h=("page", "posOffset", 3400 * EMU),
                        v=("paragraph", "posOffset", 720 * EMU), quebra="<wp:wrapTopAndBottom/>")
            + tf.ancora(93, tf.URI_FORMA, tf.forma(3400 * EMU, 900 * EMU, texto="Portal"),
                        3400 * EMU, 900 * EMU, h=("page", "posOffset", 840 * EMU),
                        v=("page", "posOffset", 15500 * EMU), quebra="<wp:wrapNone/>")
            + '</w:p>')
    rels = [("rId81", fx.RT_IMAGEM, "media/capa.png")]
    partes = {"word/media/capa.png": fx.png(600, 850, (170, 20, 60))}
    return _docx(capa + _sumario(12, controle), base, rels, partes)


def manual_capa_cheia() -> bytes:
    """O ponto que media 95 ms no manual real (0.1.11): a reserva do titulo da capa passa do pe'
    da pagina (vira a folha inteira) e o sumario, com TOC, links, PAGEREF e pontilhado, esta' num
    controle de conteudo. Digitar ANTES das ancoras da capa poe o float na pagina 2; o Qt desloca
    os blocos do sumario com o float de antes, e a conferencia os refaz a cada tecla."""
    return manual_sintetico(titulo_tw=15000, controle=True)


def documento_simples(paragrafos: int = 260) -> bytes:
    texto = [Paragrafo(runs=[Run(f"Parágrafo {i}. {tf.TEXTO}")]) for i in range(paragrafos)]
    return _docx("<w:p><w:r><w:t>Primeiro.</w:t></w:r></w:p>", Documento(paragrafos=texto),
                 (), {})


def documento_com_revisoes(paragrafos: int = 400, por_paragrafo: int = 5) -> bytes:
    """0.1.13: 2000 revisoes (400 paragrafos x 5: insercoes e exclusoes de dois autores,
    formatacao alterada e a marca de paragrafo inserida a cada 4), com Controlar alteracoes
    ligado no arquivo."""
    from editdoc.modelo.documento import Revisao
    autores = ("Ana", "Beto")
    pars = []
    for i in range(paragrafos):
        runs = [Run(f"Parágrafo {i}. {tf.TEXTO[:60]}")]
        for k in range(por_paragrafo):
            autor = autores[(i + k) % 2]
            if k % 3 == 0:
                runs.append(Run(f" novo{k}", insercao=Revisao("ins", autor, "2026-03-01T10:00:00Z")))
            elif k % 3 == 1:
                runs.append(Run(f" velho{k}", exclusao=Revisao("del", autor, "2026-03-01T11:00:00Z")))
            else:
                runs.append(Run(f" forma{k}", negrito=True, mudanca_formato=(
                    '<w:rPrChange xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
                    f'2006/main" w:author="{autor}"><w:rPr></w:rPr></w:rPrChange>')))
            runs.append(Run(" meio "))
        pars.append(Paragrafo(runs=runs))
    doc = Documento(paragrafos=pars, controlar_alteracoes=True)
    return fx.bytes_de(doc)


#: As tabelas do arquivo real de duas secoes da 0.1.12 (fora do repositorio), em linhas x colunas:
#: 16 tabelas, 362 celulas, com a linha de cabecalho repetida.
FORMAS_DO_PLANO = ((3, 4), (10, 3), (11, 2), (1, 1), (1, 1), (16, 4), (6, 3), (10, 4), (1, 1),
                   (12, 4), (4, 4), (4, 2), (9, 4), (8, 2), (12, 2), (5, 5))


def documento_plano() -> bytes:
    """0.1.14: o equivalente sintetico do "plano" real que passava do gate (48,6 ms na 0.1.11): 16
    tabelas com as formas dele (362 celulas de ~35 caracteres, cabecalho repetido, bordas de
    grade), ~150 paragrafos de corpo com 89 itens de lista numerada entre elas. O custo que o Qt
    tem a cada tecla e' refazer TODAS as tabelas que vem depois do ponto editado (ver
    docs/SPIKES.md, 0.1.14)."""
    from editdoc.modelo.documento import Borda, BordasTabela, Linha, Tabela
    grade = BordasTabela(sup=Borda(), inf=Borda(), esq=Borda(), dir=Borda(), horizontal=Borda(),
                         vertical=Borda())
    pars: list = [Paragrafo(runs=[Run("Plano de migração do sistema", negrito=True,
                                      tamanho_meio_pt=32)])]
    item = 0
    for t, (linhas, colunas) in enumerate(FORMAS_DO_PLANO):
        pars.append(Paragrafo(runs=[Run(f"Etapa {t + 1}. Descrição da etapa, com os responsáveis "
                                        "e o prazo de cada entrega prevista no cronograma.")]))
        for _ in range(6 if t % 3 else 5):
            item += 1
            pars.append(Paragrafo(runs=[Run(f"Item {item}: atividade de validação com o setor "
                                            "responsável e registro no controle.")],
                                  numeracao="numeracao"))
        w = 9638 // colunas
        pars.append(Tabela(colunas_tw=[w] * colunas, bordas=grade, linhas=[
            Linha(cabecalho=(r == 0 and linhas > 1), celulas=[
                fx._cel(f"Célula {r}.{c}: conteúdo do plano"[:35]) for c in range(colunas)])
            for r in range(linhas)]))
        pars.append(Paragrafo(runs=[Run("Observação sobre a tabela acima, com o critério de "
                                        "aceite e a referência ao anexo.")]))
    return fx.bytes_de(Documento(paragrafos=pars))


def _painel(docx: bytes):
    painel = tf._painel()
    tf._carregar(painel, docx)
    painel.show()
    drenar_eventos()
    painel.viewport().grab()
    return painel


def _fechar(painel) -> None:
    painel.documento_corpo().setModified(False)
    painel.close()
    drenar_eventos()


def _ponto(painel, nome: str) -> int:
    doc = painel.documento_corpo()
    if nome == "inicio":
        return doc.firstBlock().position()  # antes das ancoras da capa
    if nome == "capa":
        b = doc.firstBlock()
        return b.position() + b.length() - 1
    if nome.startswith("plano_"):
        # 0.1.14: a 1/3 do documento, numa celula a 1/2 e num item de lista a 1/4.
        from PySide6.QtGui import QTextCursor
        fracao = {"plano_terco": 3, "plano_celula": 2, "plano_item": 4}[nome]
        b = doc.findBlockByNumber(doc.blockCount() // fracao)
        while b.isValid():
            na_tabela = QTextCursor(b).currentTable() is not None
            if nome == "plano_terco" and len(b.text()) > 10:
                break
            if nome == "plano_celula" and na_tabela and len(b.text()) > 10:
                break
            if nome == "plano_item" and not na_tabela and b.text().startswith("Item "):
                break
            b = b.next()
        return b.position() + 6
    b = doc.firstBlock()
    alvo = "Seção 4" if nome == "sumario" else "Parágrafo 120."
    while b.isValid() and alvo not in b.text():
        b = b.next()
    return b.position() + 6


def _ir(painel, pos: int) -> None:
    c = painel.textCursor()
    c.setPosition(pos)
    painel.setTextCursor(c)
    painel.setFocus()
    painel.viewport().grab()


def _tecla(painel, tecla=None) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.keyClick(painel, tecla if tecla is not None else Qt.Key.Key_A)


# -- conferencia dos floats -------------------------------------------------------------------

def _irredutivel() -> bytes:
    """Float que ocupa a pagina quase toda a' direita: o texto corre na faixa estreita da esquerda
    e a linha que nao cabe no pe' da pagina desce com a largura estreita (o Qt nao a refaz)."""
    largura, altura = 9026 - 2500, 14500
    corpo = ("<w:p>" + tf.ancora(90, tf.URI_FORMA, tf.forma(largura * EMU, altura * EMU),
                                 largura * EMU, altura * EMU, h=("margin", "align", "right"),
                                 v=("paragraph", "posOffset", 0))
             + "<w:r><w:t>Capa.</w:t></w:r></w:p>"
             + "".join(f"<w:p><w:r><w:t>Linha {i} {tf.TEXTO}</w:t></w:r></w:p>" for i in range(30)))
    return tf.doc_do_corpo(corpo)


def _refeitos_por_tecla(painel, teclas: int = 10) -> float:
    """Quantas vezes por tecla a conferencia manda o Qt refazer um trecho (markContentsDirty)."""
    from editdoc.ponte_qt.imagens import DocumentoQt
    doc = painel.documento_corpo()
    b = doc.findBlockByNumber(20)
    _ir(painel, b.position() + 5)
    conta = [0]

    def contar(self, *a):
        conta[0] += 1
        return QTextDocument.markContentsDirty(self, *a)

    DocumentoQt.markContentsDirty = contar
    try:
        for _ in range(teclas):
            _tecla(painel)
            painel.viewport().grab()
    finally:
        del DocumentoQt.markContentsDirty
    for _ in range(teclas):
        painel.undo()
    return conta[0] / teclas


def testar_conferencia() -> None:
    secao("conferencia dos floats: a linha que o Qt nao refaz e' aceita, nao refeita a cada tecla")
    from editdoc.ponte_qt import flutuantes as pq_flutuantes
    painel = _painel(_irredutivel())
    g = painel.layout_pag.flutuantes
    checa(bool(g._aceitas), "a fixture reproduz a linha que desce de pagina com a largura estreita "
                           f"(blocos aceitos: {sorted(g._aceitas)})")
    por_tecla = _refeitos_por_tecla(painel)
    checa(por_tecla <= 0.5, f"o Qt nao refaz o trecho a cada tecla ({por_tecla:.1f} refacoes por "
                            "tecla; eram 6 na 0.1.7, com o documento inteiro conferido)")
    _fechar(painel)
    # Contraprova: a linha nunca reconhecida como aceita (assinatura sempre nova) volta a ser
    # refeita a cada tecla.
    original = pq_flutuantes._marca_das_linhas
    pq_flutuantes._marca_das_linhas = lambda bloco, r: object()
    try:
        painel = _painel(_irredutivel())
        sabotado = _refeitos_por_tecla(painel)
        _fechar(painel)
    finally:
        pq_flutuantes._marca_das_linhas = original
    checa(sabotado >= 1.0, f"contraprova: sem aceitar, {sabotado:.1f} refacoes por tecla")


# -- tiles por tecla --------------------------------------------------------------------------

def _tiles_por_tecla(painel, pos: int, teclas: int = 8) -> float:
    from editdoc.interface import vista_paginas as vp
    _ir(painel, pos)
    _tecla(painel)
    painel.viewport().grab()
    conta = [0]
    original = vp.desenhar_folha

    def contar(*a, **k):
        conta[0] += 1
        return original(*a, **k)

    vp.desenhar_folha = contar
    try:
        for _ in range(teclas):
            _tecla(painel)
            painel.viewport().grab()
    finally:
        vp.desenhar_folha = original
    for _ in range(teclas + 1):
        painel.undo()
    painel.viewport().grab()
    return conta[0] / teclas


def testar_tiles() -> None:
    secao("tiles por tecla: so' a faixa da linha sai do cache, nao o bloco inteiro")
    painel = _painel(manual_sintetico())
    capa = _tiles_por_tecla(painel, _ponto(painel, "capa"))
    corpo = _tiles_por_tecla(painel, _ponto(painel, "corpo"))
    # 1000 px de largura: 4 tiles por fileira. A linha cabe numa fileira, as vezes em duas.
    checa(capa <= 8.0, f"capa (bloco da altura da folha): {capa:.1f} tiles por tecla (a folha "
                       "inteira, 16 ou mais, na 0.1.7)")
    checa(corpo <= 8.0, f"corpo: {corpo:.1f} tiles por tecla")
    from editdoc.interface import vista_paginas as vp
    original = vp.VistaPaginas._linhas_da_mudanca
    vp.VistaPaginas._linhas_da_mudanca = lambda self, pos: None
    try:
        sabotado = _tiles_por_tecla(painel, _ponto(painel, "capa"))
    finally:
        vp.VistaPaginas._linhas_da_mudanca = original
    checa(sabotado > capa + 4, f"contraprova: invalidando o bloco inteiro, a capa refaz "
                               f"{sabotado:.1f} tiles por tecla")
    _fechar(painel)


# -- antes das ancoras da capa (0.1.11) ------------------------------------------------------

def _marcacoes_por_tecla(painel, pos: int, teclas: int = 8) -> float:
    """markContentsDirty por tecla digitando em `pos` (a conferencia refazendo trechos)."""
    from editdoc.ponte_qt.imagens import DocumentoQt
    _ir(painel, pos)
    _tecla(painel)
    painel.viewport().grab()
    conta = [0]

    def contar(self, *a):
        conta[0] += 1
        return QTextDocument.markContentsDirty(self, *a)

    DocumentoQt.markContentsDirty = contar
    try:
        for _ in range(teclas):
            _tecla(painel)
            painel.viewport().grab()
    finally:
        del DocumentoQt.markContentsDirty
    for _ in range(teclas + 1):
        painel.undo()
    painel.viewport().grab()
    return conta[0] / teclas


def testar_antes_da_capa() -> None:
    secao("antes das ancoras da capa, com o sumario num controle de conteudo (95 ms no real)")
    from editdoc.ponte_qt import flutuantes as pq_flutuantes
    painel = _painel(manual_capa_cheia())
    g = painel.layout_pag.flutuantes
    marcacoes = _marcacoes_por_tecla(painel, 0)
    tiles = _tiles_por_tecla(painel, 0)
    checa(marcacoes <= 2.0, f"a conferencia refaz o sumario numa chamada por tecla ({marcacoes:.1f}; "
                            "eram 18, uma por bloco, na 0.1.10)")
    checa(tiles <= 8.0, f"{tiles:.1f} tiles por tecla (a tela inteira, 16, na 0.1.10)")
    iguais = []
    original_comparar = pq_flutuantes.Gerente._comparar_refeitos

    def anotar(self, refeitos, altura):
        original_comparar(self, refeitos, altura)
        iguais.append(self.refeito_igual)

    pq_flutuantes.Gerente._comparar_refeitos = anotar
    try:
        from PySide6.QtCore import Qt
        K = Qt.Key
        teclas = [K.Key_A, K.Key_B, K.Key_C, K.Key_Backspace, K.Key_D, K.Key_E] * 3
        ruins = _sequencia_confere(painel, 0, teclas, a_cada=3)
    finally:
        pq_flutuantes.Gerente._comparar_refeitos = original_comparar
    checa(any(iguais), f"o sumario refeito volta igual e fica no cache ({sum(iguais)} de "
                       f"{len(iguais)} conferencias)")
    checa_igual(ruins, 0, "a tela com cache e' igual a' refeita do zero (a cada 3 teclas, com o "
                          "cache aproveitado entre elas)")
    # Contraprovas: cada metade da correcao desligada.
    original_juntar = pq_flutuantes._juntar
    pq_flutuantes._juntar = lambda faixas: list(faixas)
    try:
        separadas = _marcacoes_por_tecla(painel, 0)
    finally:
        pq_flutuantes._juntar = original_juntar
    checa(separadas >= 5.0, f"contraprova: sem juntar as faixas, {separadas:.1f} chamadas por tecla")
    pq_flutuantes.Gerente._comparar_refeitos = lambda self, r, a: None
    try:
        sem_comparar = _tiles_por_tecla(painel, 0)
    finally:
        pq_flutuantes.Gerente._comparar_refeitos = original_comparar
    checa(sem_comparar >= tiles + 6, f"contraprova: sem comparar os blocos refeitos, "
                                     f"{sem_comparar:.1f} tiles por tecla")
    checa(g is painel.layout_pag.flutuantes, "o mesmo gerente durante o teste")
    _fechar(painel)
    # A comparacao dos blocos refeitos (contraprovas sem relogio): igual so' com a conferencia
    # anterior guardada, a mesma altura do documento e as mesmas linhas e o mesmo texto.
    painel = _painel(manual_capa_cheia())
    g = painel.layout_pag.flutuantes
    doc = painel.documento_corpo()
    altura = doc.documentLayout().blockBoundingRect(doc.lastBlock()).bottom()
    blocos = {1, 2, 3, 4}
    g.esquecer_refeitos()
    g._comparar_refeitos(blocos, altura)
    checa(not g.refeito_igual, "contraprova: sem conferencia anterior guardada, nada e' igual")
    g._comparar_refeitos(blocos, altura)
    checa(g.refeito_igual, "os mesmos blocos, na mesma altura do documento: iguais")
    g._comparar_refeitos(blocos, altura + 300)
    checa(not g.refeito_igual, "contraprova: o documento mudou de altura")
    g._comparar_refeitos(blocos, altura + 300)
    linhas, _texto = g._refeitos[2]
    g._refeitos[2] = (linhas, hash("outro texto"))
    g._comparar_refeitos(blocos, altura + 300)
    checa(not g.refeito_igual, "contraprova: o texto de um bloco refeito mudou")
    g._refeitos[3] = ((-1,) + g._refeitos[3][0][1:], g._refeitos[3][1])
    g._comparar_refeitos(blocos, altura + 300)
    checa(not g.refeito_igual, "contraprova: as linhas de um bloco refeito mudaram de lugar")
    painel._limpar_cache()
    g._comparar_refeitos(blocos, altura + 300)
    checa(not g.refeito_igual, "contraprova: depois de limpar o cache da tela, a comparacao recomeca")
    _fechar(painel)


# -- cache igual ao quadro novo --------------------------------------------------------------

def _diferentes(a, b) -> int:
    if a.size() != b.size():
        return -1
    n = 0
    for y in range(0, a.height(), 2):
        for x in range(0, a.width(), 2):
            if a.pixel(x, y) != b.pixel(x, y):
                n += 1
    return n


def _sequencia_confere(painel, pos: int, teclas, a_cada: int = 1) -> int:
    """Quantas teclas deixaram a tela com cache diferente da tela refeita do zero.

    `a_cada` > 1 (0.1.11): confere so' a cada tantas teclas, e as do meio pintam com o cache
    que sobrou da anterior (limpar o cache a cada tecla nunca deixaria o cache ser reaproveitado)."""
    _ir(painel, pos)
    ruins = 0
    for i, k in enumerate(teclas):
        _tecla(painel, k)
        if (i + 1) % a_cada:
            painel.viewport().grab()
            continue
        com = painel.viewport().grab().toImage()
        painel._limpar_cache()
        sem = painel.viewport().grab().toImage()
        if _diferentes(com, sem):
            ruins += 1
    for _ in teclas:
        painel.undo()
    painel.viewport().grab()
    return ruins


def testar_cache_igual() -> None:
    secao("a tela com cache e' igual a' refeita do zero, tecla a tecla")
    from PySide6.QtCore import Qt
    K = Qt.Key
    teclas = ([K.Key_A] * 6 + [K.Key_Space] + [K.Key_B] * 24 + [K.Key_Backspace] * 6 + [K.Key_Return]
              + [K.Key_C] * 2 + [K.Key_Backspace] * 3)
    painel = _painel(manual_sintetico())
    for nome in ("capa", "sumario", "corpo"):
        ruins = _sequencia_confere(painel, _ponto(painel, nome), teclas)
        checa_igual(ruins, 0, f"{nome}: {len(teclas)} teclas (letra, quebra de linha, Backspace, "
                              "Enter) sem nada velho na tela")
    from editdoc.interface import vista_paginas as vp
    original = vp.VistaPaginas._invalidar_faixa
    vp.VistaPaginas._invalidar_faixa = lambda self, y0, y1: None
    try:
        sabotado = _sequencia_confere(painel, _ponto(painel, "corpo"), teclas[:8])
    finally:
        vp.VistaPaginas._invalidar_faixa = original
    checa(sabotado > 0, f"contraprova: sem invalidar, {sabotado} teclas deixam a tela velha")
    _fechar(painel)


# -- o plano: tabelas e listas (0.1.14) -------------------------------------------------------

def _celula_que_atravessa_pagina(painel) -> int:
    """Posicao numa celula do meio de uma tabela que atravessa a divisa de paginas."""
    from PySide6.QtGui import QTextTable
    doc = painel.documento_corpo()
    dl = doc.documentLayout()
    hb = painel.layout_pag.hb
    for quadro in doc.rootFrame().childFrames():
        if isinstance(quadro, QTextTable) and quadro.rows() >= 8:
            r = dl.frameBoundingRect(quadro)
            if int(r.top() // hb) != int(r.bottom() // hb):
                return quadro.cellAt(quadro.rows() // 2, 1).firstPosition() + 4
    return -1


def testar_plano() -> None:
    secao("0.1.14: o plano (16 tabelas, 89 itens de lista): a celula e o item refazem so' o que "
          "mudou")
    from editdoc.interface import vista_paginas as vp
    from editdoc.ponte_qt import listas as pq_listas
    painel = _painel(documento_plano())
    try:
        pos = _celula_que_atravessa_pagina(painel)
        checa(pos > 0, "a fixture tem uma tabela que atravessa a divisa de paginas")
        celula = _tiles_por_tecla(painel, pos)
        # Painel de 1000 px: 4 tiles por fileira. A celula ocupa uma ou duas colunas de tiles.
        checa(celula <= 3.0, f"digitar numa celula: {celula:.1f} tiles por tecla (a 0.1.13 tirava "
                             "a tabela inteira do cache)")
        original = vp.VistaPaginas._faixa_na_tabela
        vp.VistaPaginas._faixa_na_tabela = lambda self, *a: None
        try:
            sabotado = _tiles_por_tecla(painel, pos)
        finally:
            vp.VistaPaginas._faixa_na_tabela = original
        checa(sabotado > celula + 4, f"contraprova: com a tabela inteira, {sabotado:.1f} tiles por "
                                     "tecla")
        # A tela com cache e' igual a' refeita: letra, palavra que quebra a linha da celula,
        # Backspace, Enter na celula (a linha da tabela cresce) e Backspace de volta.
        from PySide6.QtCore import Qt
        K = Qt.Key
        teclas = ([K.Key_A] * 4 + [K.Key_Space] + [K.Key_B] * 40 + [K.Key_Backspace] * 8
                  + [K.Key_Return] + [K.Key_C] * 2 + [K.Key_Backspace] * 3)
        ruins = _sequencia_confere(painel, pos, teclas)
        checa_igual(ruins, 0, f"celula: {len(teclas)} teclas sem nada velho na tela")
        # Contraprova: a faixa horizontal errada (fora da celula) deixa a tela velha.
        original_x = vp.VistaPaginas._colunas_da_celula
        vp.VistaPaginas._colunas_da_celula = lambda self, p: (-5000.0, -4000.0)
        try:
            sabotado = _sequencia_confere(painel, pos, teclas[:6])
        finally:
            vp.VistaPaginas._colunas_da_celula = original_x
        checa(sabotado > 0, f"contraprova: fora da celula, {sabotado} teclas deixam a tela velha")
        # Listas: digitar num item nao recalcula os numeros, e cada tile nao pede mais o
        # retangulo de todos os itens (as faixas dos itens sao feitas uma vez por tecla).
        doc = painel.documento_corpo()
        numerador = pq_listas.numerador_de(doc)
        checa(len(numerador.rotulos()) >= 80, f"a fixture tem os itens de lista "
                                              f"({len(numerador.rotulos())})")
        item = _ponto(painel, "plano_item")
        versao = numerador.versao
        feitas = [0]
        original_faixas = pq_listas.Numerador.faixas

        def contar(self, d):
            antes = self._faixas
            resultado = original_faixas(self, d)
            if self._faixas is not antes:
                feitas[0] += 1
            return resultado

        pq_listas.Numerador.faixas = contar
        try:
            tiles = _tiles_por_tecla(painel, item)
            calculos = feitas[0]
            checa(numerador.versao == versao, f"digitar no item nao recalcula os numeros "
                                              f"(mudancas de estrutura: {numerador.versao - versao})")
            # Uma vez por pintura: as 8 teclas, a de antes, a ida e a volta do desfazer (11).
            checa(calculos <= 8 + 3, f"faixas dos itens refeitas {calculos} vezes em 11 pinturas "
                                     f"({tiles:.1f} tiles por tecla)")
            # Contraprova: sem o cache (a geracao do layout sobe a cada pedido), refaz por tile.
            feitas[0] = 0
            pq_listas.Numerador._layout_mudou(numerador)
            original_rotulos = pq_listas.desenhar_rotulos

            def sem_cache(painter, d, recorte):
                pq_listas.Numerador._layout_mudou(pq_listas.numerador_de(d))
                return original_rotulos(painter, d, recorte)

            pq_listas.desenhar_rotulos = sem_cache
            vp.pq_listas.desenhar_rotulos = sem_cache
            try:
                _tiles_por_tecla(painel, item)
            finally:
                pq_listas.desenhar_rotulos = original_rotulos
                vp.pq_listas.desenhar_rotulos = original_rotulos
            checa(feitas[0] > calculos + 8, f"contraprova: sem o cache, {feitas[0]} vezes")
        finally:
            pq_listas.Numerador.faixas = original_faixas
    finally:
        _fechar(painel)
        painel.deleteLater()
        drenar_eventos()


# -- objetos e faixas pintados uma vez --------------------------------------------------------

def testar_caches_de_pintura() -> None:
    secao("objetos flutuantes e cabecalho/rodape: pintados uma vez na tela; o PDF pinta de verdade")
    from PySide6.QtGui import QColor, QImage, QPainter
    from editdoc.interface import impressao
    from editdoc.interface import vista_paginas as vp
    from editdoc.ponte_qt import flutuantes as pq_flutuantes
    painel = _painel(manual_sintetico())
    pintados = [0]
    original = pq_flutuantes.pintar

    def contar(*a, **k):
        pintados[0] += 1
        return original(*a, **k)

    pq_flutuantes.pintar = contar
    faixas = [0]
    original_faixas = vp.desenhar_faixas

    def contar_faixas(*a, **k):
        faixas[0] += 1
        return original_faixas(*a, **k)

    vp.desenhar_faixas = contar_faixas
    try:
        painel._cache.clear()  # so' os tiles: os objetos e as faixas ja' pintados ficam
        painel._bytes_no_cache = 0
        painel.viewport().grab()
        checa_igual(pintados[0], 0, "refazer os tiles da capa nao pinta de novo os objetos")
        checa_igual(faixas[0], 0, "um quadro novo nao pinta de novo o cabecalho e o rodape")
        img = QImage(800, 1130, QImage.Format.Format_ARGB32)
        img.fill(QColor(255, 255, 255))
        p = QPainter(img)
        impressao.pintar_pagina(p, painel.layout_pag, 0, painel.total_de_paginas(),
                                impressao.transformacao(96, 96))
        p.end()
        checa(pintados[0] >= 3, f"a folha do PDF pinta os objetos de verdade ({pintados[0]} pinturas)")
    finally:
        pq_flutuantes.pintar = original
        vp.desenhar_faixas = original_faixas
    # O cabecalho e' refeito quando muda.
    faixa = painel.layout_pag.faixas.obter("cabecalho", "padrao")
    painel.rolar_para_pagina(1)
    antes = painel.viewport().grab().toImage()
    from PySide6.QtGui import QTextCursor
    c = QTextCursor(faixa.doc)
    c.movePosition(QTextCursor.MoveOperation.End)
    c.insertText(" MUDOU")
    depois = painel.viewport().grab().toImage()
    checa(_diferentes(antes, depois) > 0, "o cabecalho que mudou aparece mudado (a chave tem a revisao)")
    faixa.doc.undo()
    # Mesmo desenho que a pintura direta (a diferenca de meio pixel no texto nao conta).
    painel.rolar_para_pagina(0)
    painel._limpar_cache()
    com = painel.viewport().grab().toImage()
    orig_tela = pq_flutuantes._pintar_na_tela
    orig_faixa = vp.VistaPaginas._faixa_da_tela
    from PySide6.QtGui import QTransform

    def direto(self, pp, m, n, x0, y0, n_total, onde, parte):
        t = QTransform().translate(x0, y0).scale(m.escala, m.escala)
        vp.desenhar_faixas(pp, self.layout_pag, n, t, n_total, vp.OPACIDADE_FAIXA,
                           marcas=self._marcas, parte=parte, so=onde)

    pq_flutuantes._pintar_na_tela = lambda *a, **k: False
    vp.VistaPaginas._faixa_da_tela = direto
    try:
        painel._limpar_cache()
        sem = painel.viewport().grab().toImage()
    finally:
        pq_flutuantes._pintar_na_tela = orig_tela
        vp.VistaPaginas._faixa_da_tela = orig_faixa
    grandes = 0
    for y in range(0, com.height(), 2):
        for x in range(0, com.width(), 2):
            a, b = QColor(com.pixel(x, y)), QColor(sem.pixel(x, y))
            if max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())) > 40:
                grandes += 1
    total = (com.width() // 2) * (com.height() // 2)
    checa(grandes <= total * 0.002, f"a tela com os caches e' a da pintura direta ({grandes} de "
                                    f"{total} pixels diferem mais que 40 niveis)")
    _fechar(painel)


# -- pontilhado e marcas -----------------------------------------------------------------------

class _PintorDeMentira:
    """Registra as chamadas que `_preenchimentos` faz."""

    def __init__(self) -> None:
        self.textos: list[str] = []

    def setFont(self, _f) -> None:  # noqa: N802
        pass

    def setPen(self, _c) -> None:  # noqa: N802
        pass

    def drawText(self, _p, texto) -> None:  # noqa: N802
        self.textos.append(texto)


def testar_pontilhado_e_marcas() -> None:
    secao("pontilhado da tabulacao num drawText so'; tamanho das marcas guardado por fonte")
    from PySide6.QtGui import QFont
    from editdoc.formato_docx.propriedades import aparencia_paragrafo
    from editdoc.ponte_qt import marcas as pq_marcas
    from editdoc.ponte_qt import propriedades as pq_props
    painel = _painel(manual_sintetico(20))
    doc = painel.documento_corpo()
    b = doc.firstBlock()
    while b.isValid() and "Seção 4" not in b.text():
        b = b.next()
    ap = aparencia_paragrafo(pq_props.extras_de_ppr(b.blockFormat()))
    pintor = _PintorDeMentira()
    pq_props._preenchimentos(pintor, b, ap)
    checa(len(pintor.textos) == 1 and len(pintor.textos[0]) > 10 and set(pintor.textos[0]) == {"."},
          f"um drawText com o pontilhado inteiro ({[len(t) for t in pintor.textos]} pontos)")
    # Marcas: o tamanho guardado e' o calculado, e muda com a fonte padrao.
    pos = next(k for k in range(b.position(), b.position() + b.length() - 1)
               if pq_marcas.eh_marca(_formato(doc, k)))
    fmt = _formato(doc, pos)
    manipulador = doc._manipulador_marcas
    pq_marcas._TAMANHOS.clear()
    guardado = manipulador.intrinsicSize(doc, pos, fmt)
    from PySide6.QtGui import QFontMetricsF
    from editdoc.ponte_qt.campos import fonte_de
    m = QFontMetricsF(fonte_de(doc, fmt))
    checa(abs(guardado.width() - max(m.height() * 0.22, 1.0)) < 1e-6
          and abs(guardado.height() - max(m.ascent(), 1.0)) < 1e-6,
          "o tamanho da marca guardado e' o mesmo da conta direta")
    checa(manipulador.intrinsicSize(doc, pos, fmt) == guardado, "o segundo pedido vem do cache")
    fonte = QFont(doc.defaultFont())
    fonte.setPointSizeF(fonte.pointSizeF() * 2)
    doc.setDefaultFont(fonte)
    maior = manipulador.intrinsicSize(doc, pos, fmt)
    m2 = QFontMetricsF(fonte_de(doc, fmt))
    checa(abs(maior.height() - max(m2.ascent(), 1.0)) < 1e-6,
          "trocar a fonte padrao troca o tamanho (a chave tem a fonte padrao)")
    _fechar(painel)


def _formato(doc, pos):
    from editdoc.ponte_qt import links
    return links.formato_em(doc, pos)


# -- p95 --------------------------------------------------------------------------------------

def _p95_digitando(painel, pos: int, teclas: int = 80) -> float:
    _ir(painel, pos)
    for _ in range(5):
        _tecla(painel)
        painel.viewport().grab()
    tempos = []
    for _ in range(teclas):
        t = time.perf_counter()
        _tecla(painel)
        painel.viewport().grab()
        tempos.append((time.perf_counter() - t) * 1000)
    for _ in range(teclas + 5):
        painel.undo()
    painel.viewport().grab()
    return _p95(tempos)


#: Quanto o manual pode custar a mais que o documento simples medido na mesma hora, numa maquina
#: mais lenta que a do gate. Medido nesta maquina, a frio: o manual custa ~2x o simples (sumario
#: com links, PAGEREF e pontilhado; capa com objetos). Na 0.1.7 o sumario custava 20x (94 ms).
FATOR_DO_SIMPLES = 2.5
#: Teto absoluto da folga relativa (0.1.11): numa maquina tao carregada que o simples passa de
#: 23 ms, a folga relativa deixaria passar uma regressao de verdade. As regressoes que este teste
#: ja' pegou mediam 47 a 168 ms (sumario da 0.1.7; antes da capa na 0.1.10, nesta fixture).
TETO_MS = 60.0
#: Rodadas por ponto (0.1.11): simples e manual intercalados, e vale a MEDIANA de cada lado.
#: Ate' a 0.1.10 era uma medida (com uma segunda tentativa): um pico de carga numa das 80 teclas
#: da medida do manual reprovou o build (35,5 ms contra 10,8 ms do simples).
RODADAS = 3
#: Rodadas a mais, so' para o ponto que passou do limite, cada uma com o simples de novo.
RODADAS_EXTRA = 2


def avaliar(manual: list[float], simples: list[float],
            fator: float = FATOR_DO_SIMPLES) -> tuple[bool, float, float, float]:
    """(passou, mediana do manual, mediana do simples, limite). Ver as constantes acima."""
    m, s = statistics.median(manual), statistics.median(simples)
    limite = max(GATE_MS, min(TETO_MS, s * fator + 2.0))
    return m <= limite, m, s, limite


def testar_criterio_do_p95() -> None:
    secao("criterio do p95 (0.1.11): pico isolado nao reprova; regressao de verdade reprova")
    # O caso do build abortado: uma medida com pico (35,5 ms) entre medidas normais.
    checa(avaliar([35.5, 9.8, 10.4], [10.8, 4.9, 5.2])[0],
          "um pico numa das rodadas nao reprova (mediana)")
    checa(avaliar([8.0, 9.0, 7.5], [3.5, 3.8, 3.6])[0], "no gate passa, qualquer que seja o simples")
    # Contraprovas: regressao que aparece em toda rodada.
    checa(not avaliar([35.0, 36.2, 34.8], [10.8, 4.9, 5.2])[0],
          "contraprova: 35 ms em toda rodada, com o simples a 5 ms, reprova")
    checa(not avaliar([95.0, 96.1, 97.3], [30.0, 31.0, 29.5])[0],
          "contraprova: 95 ms reprova mesmo com o simples lento (teto absoluto)")
    checa(not avaliar([168.0, 170.0, 165.0], [4.0, 4.1, 4.2], FATOR_ANTES_DA_CAPA)[0],
          "contraprova: o ponto antes da capa da 0.1.10 (168 ms) reprova, mesmo com a folga dele")


#: Folga do ponto antes das ancoras da capa (0.1.11). Cada tecla ali refaz o sumario inteiro (a
#: conferencia, numa chamada) e os tiles da linha, que cruzam o sumario atras da capa: medido
#: nesta maquina, 15 ms contra 4,7 do simples (3,3x) parada, e 4x carregada. Na 0.1.10, 168 ms
#: (36x). As verificacoes sem relogio (`testar_antes_da_capa`) pegam cada metade da correcao.
FATOR_ANTES_DA_CAPA = 5.0

#: Pontos do p95: (nome, fixture, ponto da fixture, folga sobre o simples).
PONTOS_P95 = (("capa", manual_sintetico, "capa", FATOR_DO_SIMPLES),
              ("sumario", manual_sintetico, "sumario", FATOR_DO_SIMPLES),
              ("corpo", manual_sintetico, "corpo", FATOR_DO_SIMPLES),
              ("antes das ancoras da capa (sumario em controle de conteudo)", manual_capa_cheia,
               "inicio", FATOR_ANTES_DA_CAPA),
              # 0.1.13: 2000 revisoes, com Controlar alteracoes ligado (cada tecla e' insercao).
              ("2000 revisoes, controle ligado", documento_com_revisoes, "corpo",
               FATOR_DO_SIMPLES))


def testar_p95() -> None:
    secao("p95 da digitacao (80 teclas com a pintura): capa, sumario, corpo e antes da capa")
    simples = documento_simples()
    fixtures = {f: f() for f in {p[1] for p in PONTOS_P95}}

    def medir(docx: bytes, nome: str) -> float:
        # Um painel por medida, fechado e destruido depois: um segundo painel aberto (com o
        # caret piscando e pintura pendente) entra na conta do outro (medido: o dobro).
        painel = _painel(docx)
        try:
            return _p95_digitando(painel, _ponto(painel, nome))
        finally:
            _fechar(painel)
            painel.deleteLater()
            drenar_eventos()

    # Cada rodada mede o simples (a referencia da mesma hora) e todos os pontos, intercalados.
    medidas = {p[0]: [] for p in PONTOS_P95}
    referencias = {p[0]: [] for p in PONTOS_P95}
    for _rodada in range(RODADAS):
        ref = medir(simples, "corpo")
        for nome, fixture, ponto, _fator in PONTOS_P95:
            medidas[nome].append(medir(fixtures[fixture], ponto))
            referencias[nome].append(ref)
    for nome, fixture, ponto, fator in PONTOS_P95:
        passou, m, s, limite = avaliar(medidas[nome], referencias[nome], fator)
        extra = 0
        while not passou and extra < RODADAS_EXTRA:
            # So' o ponto que passou do limite mede de novo, com a referencia de novo.
            extra += 1
            referencias[nome].append(medir(simples, "corpo"))
            medidas[nome].append(medir(fixtures[fixture], ponto))
            passou, m, s, limite = avaliar(medidas[nome], referencias[nome], fator)
        print(f"         {nome}: p95 {[round(v, 1) for v in medidas[nome]]} ms, mediana {m:.1f} "
              f"(simples: mediana {s:.1f}; limite {limite:.1f}; rodadas a mais: {extra})")
        checa(passou, f"{nome}: mediana do p95 {m:.1f} ms no gate ({GATE_MS:.0f} ms) ou ate' "
                      f"{fator}x o simples ({s:.1f} ms), com teto de {TETO_MS:.0f} ms")


def _p95_em_partes(painel, pos: int, teclas: int = 80) -> tuple[float, float, float]:
    """(p95 da tecla com a pintura, p95 so' da tecla, p95 so' da pintura), em ms."""
    _ir(painel, pos)
    for _ in range(5):
        _tecla(painel)
        painel.viewport().grab()
    total, tecla, pintura = [], [], []
    for _ in range(teclas):
        t0 = time.perf_counter()
        _tecla(painel)
        t1 = time.perf_counter()
        painel.viewport().grab()
        t2 = time.perf_counter()
        total.append((t2 - t0) * 1000)
        tecla.append((t1 - t0) * 1000)
        pintura.append((t2 - t1) * 1000)
    for _ in range(teclas + 5):
        painel.undo()
    painel.viewport().grab()
    return _p95(total), _p95(tecla), _p95(pintura)


#: Folga da PINTURA do plano sobre o p95 inteiro do simples (0.1.14). Cada tile do plano tem tabela
#: e numeros de lista (medido: 0,8 ms por tile parado, ~3 ms carregado, contra ~0,4 do simples) e a
#: linha do item da fixture cruza uma fileira de tiles (8 por tecla): medido carregado, 24 a 28 ms
#: contra 9,5 a 11 do simples. Com a tabela inteira saindo do cache (a 0.1.13), a celula refaz 12
#: a 20 tiles e passa do limite (contraprova sem relogio em `testar_plano`).
FATOR_DA_PINTURA_DO_PLANO = 3.5


def testar_p95_do_plano() -> None:
    secao("0.1.14: p95 no plano (1/3, celula, item): a pintura no gate; a tecla e' do Qt")
    simples = documento_simples()
    plano = documento_plano()

    def medir(docx: bytes, nome: str):
        painel = _painel(docx)
        try:
            return _p95_em_partes(painel, _ponto(painel, nome))
        finally:
            _fechar(painel)
            painel.deleteLater()
            drenar_eventos()

    for nome in ("plano_terco", "plano_celula", "plano_item"):
        pinturas, refs = [], []
        # Uma rodada; mais duas so' se passar do limite (o teto de 180 s da suite).
        passou = False
        for _rodada in range(1 + RODADAS_EXTRA):
            refs.append(medir(simples, "corpo")[0])
            total, tecla, pintura = medir(plano, nome)
            pinturas.append(pintura)
            print(f"         {nome}: p95 {total:.1f} ms (tecla {tecla:.1f}, pintura {pintura:.1f}); "
                  f"simples {refs[-1]:.1f}")
            # A tecla e' o insertText do Qt, que refaz todas as tabelas depois do ponto editado
            # (ver docs/SPIKES.md, 0.1.14): fica fora do criterio. A pintura e' do EditDoc.
            passou, m, s, limite = avaliar(pinturas, refs, FATOR_DA_PINTURA_DO_PLANO)
            if passou:
                break
        checa(passou, f"{nome}: pintura p95 mediana {m:.1f} ms no gate ou ate' "
                      f"{FATOR_DA_PINTURA_DO_PLANO}x o simples ({s:.1f} ms; limite {limite:.1f})")


def testar_modos_com_2000_revisoes() -> None:
    secao("0.1.13: 2000 revisoes: trocar o modo de exibicao em menos de 1 s, e a lista")
    from editdoc.edicao import revisoes as ed
    from editdoc.ponte_qt import revisoes as pq
    painel = _painel(documento_com_revisoes())
    try:
        doc = painel.documento_corpo()
        t = time.perf_counter()
        itens = ed.listar(doc)
        lista_ms = (time.perf_counter() - t) * 1000
        checa(len(itens) >= 2000, f"a lista tem as revisoes ({len(itens)}, {lista_ms:.0f} ms)")
        checa(ed.controle_ligado(painel), "o controle veio ligado do arquivo")
        tempos = {}
        for modo in ("simples", "final", "original", "todas"):
            t = time.perf_counter()
            pq.definir_modo(doc, modo)
            painel._limpar_cache()
            painel._altura_doc_anterior = None
            painel._atualizar_geometria()
            painel.viewport().grab()
            tempos[modo] = (time.perf_counter() - t) * 1000
        print(f"         trocar o modo (com a pintura): {tempos} ms; lista: {lista_ms:.0f} ms")
        checa(max(tempos.values()) < 1000,
              f"cada troca de modo em menos de 1 s (pior: {max(tempos.values()):.0f} ms)")
    finally:
        _fechar(painel)
        painel.deleteLater()
        drenar_eventos()


def main() -> int:
    # As fontes do Windows antes de qualquer documento, como no gate: o fallback do offscreen e'
    # duas vezes mais largo e quebra linha a toda hora; carregadas depois, o Qt continua com o
    # fallback que ja' tinha escolhido (medido: o p95 dobra).
    usar_fonte_windows()
    usar_fontes_do_documento()
    # O relogio primeiro: as conferencias de pixel abaixo esquentam a maquina (medido: o p95 do
    # documento simples vai de 5 para 10 ms depois delas).
    testar_criterio_do_p95()
    testar_p95()
    testar_p95_do_plano()
    testar_modos_com_2000_revisoes()
    testar_conferencia()
    testar_tiles()
    testar_antes_da_capa()
    testar_cache_igual()
    testar_plano()
    testar_caches_de_pintura()
    testar_pontilhado_e_marcas()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
