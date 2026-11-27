"""Sumario (Referencias > Sumario) e indice de ilustracoes: inserir no cursor e atualizar.

Inserir: o campo `TOC \\o "1-3" \\h \\z \\u` entra no cursor, em paragrafos proprios (o texto
antes e depois do cursor fica nos paragrafos de fora). Cada titulo (nivel de estrutura do bloco:
o do estilo "Titulo N" ou o direto) dentro dos niveis do campo vira uma linha no estilo "toc N"
(Sumario N, criado se o documento nao tem), com a tabulacao a direita com pontilhado na margem
direita e o numero da pagina. O titulo ganha um marcador oculto `_Toc...` (o que ja' tem um fica
com ele) e a linha aponta para ele: o hiperlink (Ctrl+clique vai ao titulo) e o PAGEREF.

0.1.37: o titulo numerado por lista leva o numero na linha ("1.2", uma tabulacao e o texto, como o
Word); o `\\t` (estilos extras) e o `\\b` (trecho de um marcador) entram nas entradas; o titulo
"Sumario" (estilo "TOC Heading") e' opcional; e o indice de ilustracoes (`TOC \\h \\z \\c
"Figura"`) usa o mesmo caminho: as entradas sao os paragrafos que tem um campo SEQ do rotulo, no
estilo "table of figures", com o marcador `_Toc` no paragrafo da legenda.

Atualizar o sumario inteiro: o resultado do campo (o que fica entre as marcas de inicio e fim) e'
refeito a partir dos titulos de agora; o codigo do campo fica como estava. Atualizar so' os
numeros: o resultado de cada PAGEREF dentro do sumario vira a pagina do marcador dele.

A pagina e' a do layout do EditDoc: a folha em que o titulo comeca, com o numero que o campo PAGE
mostraria ali (secoes com numeracao propria, formato do numero, colunas), pela mesma conta do
`ContextoDeCampos`. As linhas entram primeiro com a pagina de antes (o sumario empurra o texto);
depois do layout refeito, os numeros sao corrigidos num passo ANOTADO (`_anotar`), como os
ajustes do layout que vem no meio: o desfazer e o refazer do painel levam tudo junto com o passo
do usuario. Um Ctrl+Z devolve o documento de antes, inclusive o catalogo de estilos e os
marcadores dos titulos.

Nada disso roda sozinho: um sumario vindo do Word volta ao arquivo como veio enquanto o usuario
nao manda atualizar.
"""

from __future__ import annotations

import zlib

from PySide6.QtGui import QTextBlockFormat, QTextCharFormat, QTextCursor, QTextFormat

from editdoc.formato_docx.propriedades import W, canonico
from editdoc.modelo import legendas as mod_leg
from editdoc.modelo import sumario as mod
from editdoc.modelo.documento import CARACTERE_OBJETO, MarcaCampo, Marcador, Paragrafo, Run
from editdoc.modelo.numeracao import texto_visivel
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import links as pq_links
from editdoc.ponte_qt import listas as pq_listas
from editdoc.ponte_qt import marcas as pq_marcas
from editdoc.ponte_qt import secoes as pq_secoes

#: Rodadas de correcao dos numeros: o numero novo pode mudar a largura da linha e, raramente,
#: empurrar um titulo para a pagina seguinte.
RODADAS = 3
#: O estilo da linha do indice de ilustracoes e o do titulo do sumario (nomes do Word).
ESTILO_FIGURAS = "table of figures"
ESTILO_TITULO = "TOC Heading"
#: O texto do titulo do sumario.
TEXTO_TITULO = "Sumário"


def _recado(editor, texto: str) -> None:
    if hasattr(editor, "mensagem"):
        editor.mensagem.emit(texto)


def _no_corpo(editor) -> bool:
    faixa = editor.editando_faixa() if hasattr(editor, "editando_faixa") else None
    nota = getattr(editor, "editando_nota", lambda: None)()
    return faixa is None and nota is None


# -- leitura do documento --------------------------------------------------------------------

def marcas_de_campo(doc) -> list[tuple[int, MarcaCampo]]:
    """(posicao, marca) de cada inicio e fim de campo do documento, na ordem do texto."""
    saida = []
    bloco = doc.begin()
    while bloco.isValid():
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                fmt = frag.charFormat()
                if pq_marcas.eh_marca(fmt) and not pq_marcas.eh_marcador(fmt):
                    m = pq_marcas.marca_de(fmt)
                    if isinstance(m, MarcaCampo):
                        inicio = frag.position()
                        saida.extend((inicio + i, m) for i, c in enumerate(frag.text())
                                     if c == CARACTERE_OBJETO)
            it += 1
        bloco = bloco.next()
    return saida


def campos(doc) -> list[tuple[int, int, object]]:
    """(inicio, fim, Campo) de cada campo com as duas marcas, na ordem do inicio. O fim e' achado
    pelo aninhamento (o campo de dentro fecha antes)."""
    saida = []
    abertos: list[tuple[int, object]] = []
    for pos, m in marcas_de_campo(doc):
        if m.tipo == "inicio":
            abertos.append((pos, m.campo))
        elif abertos:
            ini, campo = abertos.pop()
            saida.append((ini, pos, campo))
    saida.sort(key=lambda x: x[0])
    return saida


def sumarios(doc, figuras: bool | None = None) -> list[tuple[int, int, object]]:
    """Os campos TOC. `figuras`: False so' os sumarios de titulos, True so' os indices de
    ilustracoes (TOC com \\c), None todos."""
    todos = [c for c in campos(doc) if mod.eh_sumario(c[2])]
    if figuras is None:
        return todos
    return [c for c in todos if mod.eh_indice_de_figuras(c[2]) == figuras]


def sumario_do_cursor(doc, pos: int, figuras: bool | None = None):
    """O sumario que contem `pos`; senao, o primeiro do documento; None se nao ha'."""
    todos = sumarios(doc, figuras)
    for ini, fim, campo in todos:
        if ini <= pos <= fim + 1:
            return ini, fim, campo
    return todos[0] if todos else None


def _marcadores(doc) -> dict[str, int]:
    """nome -> posicao do inicio do marcador."""
    saida: dict[str, int] = {}
    for pos, m in pq_marcas.posicoes_de_marcadores(doc):
        if m.tipo == "inicio" and m.nome not in saida:
            saida[m.nome] = pos
    return saida


def intervalos_de_marcadores(doc) -> dict[str, tuple[int, int]]:
    """nome -> (posicao da marca de inicio, posicao da marca de fim). O marcador sem fim fica
    de fora; o nome repetido vale o primeiro."""
    inicios: dict[str, int] = {}
    saida: dict[str, tuple[int, int]] = {}
    for pos, m in pq_marcas.posicoes_de_marcadores(doc):
        if m.tipo == "inicio":
            inicios.setdefault(m.nome, pos)
        elif m.nome in inicios and m.nome not in saida:
            saida[m.nome] = (inicios[m.nome], pos)
    return saida


def _toc_do_bloco(bloco) -> str | None:
    """O primeiro marcador `_Toc` que comeca neste bloco."""
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and pq_marcas.eh_marcador(frag.charFormat()):
            m = pq_marcas.marca_de(frag.charFormat())
            if isinstance(m, Marcador) and m.tipo == "inicio" \
                    and m.nome.startswith(mod.PREFIXO_MARCADOR):
                return m.nome
        it += 1
    return None


def blocos_com_seq(doc, rotulo: str | None = None) -> dict[int, list[tuple[int, int, str]]]:
    """numero do bloco -> [(inicio, fim, rotulo)] dos campos SEQ dele, na ordem do texto. Com
    `rotulo`, so' os SEQ dele. So' os que o EditDoc entende (`ler_seq`)."""
    saida: dict[int, list[tuple[int, int, str]]] = {}
    for ini, fim, campo in campos(doc):
        if campo.tipo() != "SEQ":
            continue
        seq = mod_leg.ler_seq(campo.instrucao())
        if seq is None or (rotulo is not None and seq.rotulo.lower() != rotulo.lower()):
            continue
        saida.setdefault(doc.findBlock(ini).blockNumber(), []).append((ini, fim, seq.rotulo))
    return saida


def numero_da_lista(doc, numero_do_bloco: int) -> str:
    """O numero de lista do bloco ("1.2"), sem marcador (bullet) e sem numero oculto; "" se o bloco
    nao e' item de lista numerada."""
    rotulo = pq_listas.numerador_de(doc).rotulos().get(numero_do_bloco)
    if rotulo is None or rotulo.nivel.oculto or rotulo.nivel.eh_marcador():
        return ""
    return texto_visivel(rotulo.texto).strip()


def _nomes_do_estilo(estilos, sid: str | None) -> tuple:
    """Os nomes (minusculas) pelos quais o \\t pode citar o estilo: nome, nome na tela e id."""
    e = estilos.itens.get(sid) if sid else None
    if e is None:
        return ()
    return tuple({e.nome.lower(), e.nome_exibido().lower(), e.id.lower()})


def titulos(doc, opcoes: mod.Opcoes, fora: tuple[int, int] | None = None) -> list:
    """(bloco, nivel 1-9, texto, numero de lista) das entradas, fora do intervalo `fora`.

    Entra o bloco que e' titulo dentro dos niveis (\\o, \\u), que tem um estilo do \\t, ou que
    tem um campo SEQ do rotulo do \\c (nivel 1, o texto e' o paragrafo inteiro). Com \\b, so' os
    blocos dentro do marcador."""
    limite = None
    if opcoes.marcador:
        limite = intervalos_de_marcadores(doc).get(opcoes.marcador)
        if limite is None:
            return []
    com_seq = blocos_com_seq(doc, opcoes.rotulo) if opcoes.rotulo else {}
    estilos = pq_estilos.catalogo(doc) if opcoes.estilos else None
    saida = []
    bloco = doc.begin()
    while bloco.isValid():
        ini, fim = bloco.position(), bloco.position() + bloco.length() - 1
        dentro = fora is not None and not (fim < fora[0] or ini > fora[1])
        fora_do_trecho = limite is not None and (fim < limite[0] or ini > limite[1])
        if not dentro and not fora_do_trecho:
            nivel = pq_estilos.nivel_do_bloco(bloco)
            entrada = None  # (nivel 1-9, com numero de lista)
            if opcoes.rotulo and bloco.blockNumber() in com_seq:
                entrada = (1, False)
            elif nivel is not None and opcoes.inclui(nivel + 1):
                entrada = (nivel + 1, True)
            elif opcoes.estilos:
                sid = pq_estilos.estilo_do_bloco(bloco.blockFormat())
                n = opcoes.nivel_do_estilo(*_nomes_do_estilo(estilos, sid))
                if n is not None:
                    entrada = (n, True)
            texto = mod.texto_do_titulo(bloco.text()) if entrada else ""
            if texto:
                numero = numero_da_lista(doc, bloco.blockNumber()) if entrada[1] else ""
                saida.append((bloco, entrada[0], texto, numero))
        if len(saida) >= mod.LINHAS_MAXIMAS:
            break
        bloco = bloco.next()
    return saida


# -- pagina -------------------------------------------------------------------------------------

def _preparar(editor) -> None:
    """Layout em dia (secoes, regras de quebra, notas, campos), como antes de imprimir."""
    if hasattr(editor, "preparar_para_impressao"):
        editor.preparar_para_impressao()


def pagina_de(editor, pos: int) -> str:
    """O numero que o campo PAGE mostraria na folha onde `pos` esta'."""
    layout = editor.layout_pag
    folha = max(0, layout.pagina_do_cursor(pos))
    return layout.contexto_campos.valor("PAGE", folha) or str(folha + 1)


# -- formatos -----------------------------------------------------------------------------------

def formato_limpo(fmt) -> QTextCharFormat:
    """Formato de caractere de um vizinho sem as propriedades de objeto (marca, campo, imagem)."""
    from editdoc.ponte_qt import campos as pq_campos
    cf = QTextCharFormat(fmt.toCharFormat() if hasattr(fmt, "toCharFormat") else fmt)
    for prop in (*pq_marcas.PROPS_DE_MARCA, *pq_campos.PROPS_DE_CAMPO,
                 QTextFormat.Property.ObjectIndex, QTextFormat.Property.ImageName,
                 QTextFormat.Property.ImageWidth, QTextFormat.Property.ImageHeight):
        cf.clearProperty(prop)
    return cf


_formato_limpo = formato_limpo


def _extras_da_tabulacao(pos_tw: int, esquerda_tw: int | None = None) -> str | None:
    """O w:pPr (forma canonica) com a tabulacao a direita com pontilhado em `pos_tw` e, se dada,
    a tabulacao a esquerda depois do numero do titulo."""
    from lxml import etree
    tabs = etree.Element(f"{{{W}}}tabs")
    if esquerda_tw is not None and 0 < esquerda_tw < pos_tw:
        tab = etree.SubElement(tabs, f"{{{W}}}tab")
        tab.set(f"{{{W}}}val", "left")
        tab.set(f"{{{W}}}pos", str(int(esquerda_tw)))
    tab = etree.SubElement(tabs, f"{{{W}}}tab")
    tab.set(f"{{{W}}}val", "right")
    tab.set(f"{{{W}}}leader", "dot")
    tab.set(f"{{{W}}}pos", str(int(pos_tw)))
    return canonico("pPr", [tabs])


def _extras_da_tabulacao_sem_pagina(esquerda_tw: int) -> str | None:
    from lxml import etree
    tabs = etree.Element(f"{{{W}}}tabs")
    tab = etree.SubElement(tabs, f"{{{W}}}tab")
    tab.set(f"{{{W}}}val", "left")
    tab.set(f"{{{W}}}pos", str(int(esquerda_tw)))
    return canonico("pPr", [tabs])


def _gerador_de_extras(largura_tw: int):
    """A funcao `(entrada, tem_pagina) -> w:pPr` das linhas: a tabulacao a direita com
    pontilhado para o numero da pagina e, no titulo numerado, a tabulacao a esquerda do nivel
    (440 twips por nivel, como o Word)."""
    memoria: dict = {}

    def extras(entrada, tem_pagina: bool):
        esquerda = mod.TAB_NUMERO_TW * entrada.nivel if entrada.numero else None
        chave = (esquerda, tem_pagina)
        if chave not in memoria:
            if tem_pagina:
                memoria[chave] = _extras_da_tabulacao(largura_tw, esquerda)
            else:
                memoria[chave] = _extras_da_tabulacao_sem_pagina(esquerda) \
                    if esquerda is not None else None
        return memoria[chave]

    return extras


def _largura_util(editor, pos: int) -> int:
    """Largura do texto (twips) da secao onde o sumario fica: a margem direita da tabulacao."""
    layout = editor.layout_pag
    try:
        pagina = layout.pagina_da_folha(max(0, layout.pagina_do_cursor(pos)))
    except (AttributeError, IndexError, ValueError):
        pagina = layout.pagina_arquivo
    return max(720, int(pagina.corpo_largura_tw()))


def garantir_nomes(doc, nomes) -> dict[str, str | None]:
    """nome canonico -> id do estilo, criando os que faltam (e a base `heading 1` do
    "TOC Heading"). A troca do catalogo entra no bloco de edicao aberto."""
    estilos = pq_estilos.catalogo(doc)
    faltam = [n for n in dict.fromkeys(nomes) if (e := estilos.por_nome(n)) is None or e.virtual]
    if faltam:
        novo = estilos.copia()
        if ESTILO_TITULO in faltam:
            novo.garantir("heading 1")
        for nome in faltam:
            novo.garantir(nome)
        pq_estilos.trocar_catalogo(doc, novo)
        estilos = novo
    saida = {}
    for n in nomes:
        e = estilos.por_nome(n)
        saida[n] = e.id if e is not None else None
    return saida


def garantir_estilos(doc, niveis) -> tuple[dict, str | None]:
    """(nivel -> id do estilo "toc N", id do Normal), criando os que faltam. A troca do catalogo
    entra no bloco de edicao aberto."""
    niveis = sorted(set(niveis))
    ids = garantir_nomes(doc, [f"toc {n}" for n in niveis])
    return ({n: ids[f"toc {n}"] for n in niveis},
            pq_estilos.catalogo(doc).id_padrao())


def _estilos_das_linhas(doc, opcoes: mod.Opcoes, entradas) -> tuple[dict, str | None]:
    """(nivel -> id do estilo da linha, id do Normal): "table of figures" no indice de
    ilustracoes, "toc N" nos outros."""
    if opcoes.rotulo is not None:
        ids = garantir_nomes(doc, [ESTILO_FIGURAS])
        return {1: ids[ESTILO_FIGURAS]}, pq_estilos.catalogo(doc).id_padrao()
    return garantir_estilos(doc, [e.nivel for e in entradas] or [1])


# -- escrita ------------------------------------------------------------------------------------

def _escrever(cursor: QTextCursor, paragrafos: list[Paragrafo], res) -> None:
    """Escreve os paragrafos a partir do cursor: o primeiro no bloco do cursor (que recebe o
    formato dele), os outros em blocos novos."""
    from editdoc.ponte_qt import para_qt
    for i, p in enumerate(paragrafos):
        if i:
            cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())
        para_qt._escrever_paragrafo(cursor, p, res)


def _entradas(editor, achados: list, usados: set) -> tuple[list, list]:
    """(entradas, [(cursor no comeco do titulo, nome novo)]): o marcador do titulo (o `_Toc` que
    ele ja' tem ou um nome novo) e a pagina de agora. O cursor acompanha as edicoes seguintes (o
    QTextBlock nao: partir o bloco no comeco do titulo deixaria a referencia no pedaco vazio, e o
    paragrafo novo criado ali empurra o cursor para o texto do titulo)."""
    entradas, marcar = [], []
    for k, (bloco, nivel, texto, numero) in enumerate(achados):
        nome = _toc_do_bloco(bloco)
        if nome is None:
            nome = mod.nome_de_marcador(usados, semente=zlib.crc32(f"{k}:{texto}".encode()))
            marcar.append((QTextCursor(bloco), nome))
        entradas.append(mod.Entrada(texto, nivel, nome, pagina_de(editor, bloco.position()),
                                    numero))
    return entradas, marcar


def _marcar_titulos(doc, marcar: list, res) -> None:
    """Poe o marcador `_Toc` novo em volta do texto de cada titulo (antes da quebra de secao)."""
    for cursor, nome in marcar:
        bloco = doc.findBlock(cursor.position())
        if not bloco.isValid():
            continue
        sid = pq_estilos.estilo_do_bloco(bloco.blockFormat())
        base = pq_estilos.formato_de_caractere(res.caractere(sid, None))
        c = QTextCursor(doc)
        fim = bloco.position() + bloco.length() - 1
        quebra = pq_secoes.posicao_da_quebra_no_bloco(bloco)
        if quebra is not None:
            fim = min(fim, quebra)
        c.setPosition(fim)
        pq_marcas.inserir(c, Marcador("fim", nome), base)
        c.setPosition(bloco.position())
        pq_marcas.inserir(c, Marcador("inicio", nome), base)


def _contexto(editor, pos: int, instrucao: str):
    doc = editor.documento_corpo()
    opcoes = mod.opcoes_da_instrucao(instrucao)
    return doc, opcoes, _gerador_de_extras(_largura_util(editor, pos))


def _sem_entradas(opcoes: mod.Opcoes) -> str:
    return mod.SEM_ENTRADAS_FIGURAS if opcoes.rotulo is not None else mod.SEM_ENTRADAS


def _primeiro_a_partir_de(doc, pos: int, figuras: bool | None):
    """O primeiro sumario que comeca em `pos` ou depois."""
    return next((c for c in sumarios(doc, figuras) if c[0] >= pos), None)


def _nome_do_indice(opcoes: mod.Opcoes) -> str:
    return "Índice de ilustrações" if opcoes.rotulo is not None else "Sumário"


def inserir(editor, rotulo: str | None = None, com_titulo: bool = False) -> bool:
    """Insere o sumario (ou, com `rotulo`, o indice de ilustracoes desse rotulo) no cursor. Um
    passo de desfazer. `com_titulo`: o paragrafo "Sumário" (estilo TOC Heading) antes do campo.
    False (com o motivo) se nao pode."""
    nome_do_campo = "índice de ilustrações" if rotulo else "sumário"
    if not _no_corpo(editor):
        _recado(editor, f"O {nome_do_campo} só pode ser inserido no texto do documento (não no "
                        "cabeçalho, no rodapé nem numa nota).")
        return False
    if rotulo is not None:
        rotulo = mod_leg.rotulo_valido(rotulo)
        if not rotulo:
            _recado(editor, "Escolha o rótulo da legenda do índice de ilustrações.")
            return False
    doc = editor.documento_corpo()
    pos = editor.textCursor().selectionStart()
    dentro = sumario_do_cursor(doc, pos)
    if dentro is not None and dentro[0] <= pos <= dentro[1]:
        _recado(editor, f"O cursor está dentro de um {nome_do_campo}. Use \"Atualizar\".")
        return False
    _preparar(editor)
    instrucao = mod.instrucao_de_figuras(rotulo) if rotulo else mod.INSTRUCAO_PADRAO
    doc, opcoes, extras = _contexto(editor, pos, instrucao)
    achados = titulos(doc, opcoes)
    usados = set(_marcadores(doc))
    entradas, marcar = _entradas(editor, achados, usados)
    c = QTextCursor(doc)
    c.setPosition(pos)
    c.beginEditBlock()
    ids, normal = _estilos_das_linhas(doc, opcoes, entradas)
    titulo = garantir_nomes(doc, [ESTILO_TITULO])[ESTILO_TITULO] if com_titulo and not rotulo \
        else None
    res = pq_estilos.Resolvedor(pq_estilos.catalogo(doc))
    paragrafos = mod.paragrafos_do_sumario(entradas, ids, extras, opcoes, normal,
                                           _sem_entradas(opcoes))
    paragrafos[0].runs.insert(0, Run(marca=MarcaCampo("inicio", mod.campo_toc(instrucao))))
    paragrafos.append(Paragrafo(runs=[Run(marca=MarcaCampo("fim"))]))
    if titulo is not None:
        paragrafos.insert(0, Paragrafo(runs=[Run(texto=TEXTO_TITULO)], estilo=titulo))
    # Paragrafos proprios: o texto antes e depois do cursor fica de fora do sumario.
    bloco = c.block()
    antes = pos > bloco.position()
    depois = pos < bloco.position() + bloco.length() - 1
    if depois:
        c.insertBlock()
        c.setPosition(pos)
    if antes:
        c.insertBlock()
    # Os marcadores antes do sumario: o cursor `c` (num bloco vazio novo) acompanha.
    _marcar_titulos(doc, marcar, res)
    inicio = c.position()
    _escrever(c, paragrafos, res)
    c.endEditBlock()
    campo = _primeiro_a_partir_de(doc, inicio, bool(rotulo))
    _corrigir_numeros(editor, campo[0] if campo else inicio, juntar=True)
    final = QTextCursor(doc)
    achado = _primeiro_a_partir_de(doc, inicio, bool(rotulo))
    final.setPosition(achado[1] + 1 if achado else min(c.position(), doc.characterCount() - 1))
    editor.setTextCursor(final)
    _depois(editor)
    _recado(editor, f"{_nome_do_indice(opcoes)} inserido com {len(entradas)} "
                    f"{'entrada' if len(entradas) == 1 else 'entradas'}.")
    return True


def _atualizar_um(editor, ini: int, fim: int, campo) -> tuple[int, int]:
    """Refaz o resultado do campo em [ini, fim] (dentro do bloco de edicao aberto pelo chamador).
    Devolve (a posicao da marca de inicio de depois, o numero de entradas)."""
    doc, opcoes, extras = _contexto(editor, ini, campo.instrucao())
    achados = titulos(doc, opcoes, fora=(ini, fim))
    usados = set(_marcadores(doc))
    entradas, marcar = _entradas(editor, achados, usados)
    bloco_ini, bloco_fim = doc.findBlock(ini), doc.findBlock(fim)
    separado = bloco_ini.blockNumber() != bloco_fim.blockNumber()
    formato_fim = QTextBlockFormat(bloco_fim.blockFormat())
    c = QTextCursor(doc)
    ids, normal = _estilos_das_linhas(doc, opcoes, entradas)
    res = pq_estilos.Resolvedor(pq_estilos.catalogo(doc))
    paragrafos = mod.paragrafos_do_sumario(entradas, ids, extras, opcoes, normal,
                                           _sem_entradas(opcoes))
    c.setPosition(ini + 1)
    c.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
    c.removeSelectedText()
    _marcar_titulos(doc, marcar, res)
    inicio = c.position() - 1  # a marca de inicio do sumario (os marcadores de cima a empurram)
    _escrever(c, paragrafos, res)
    if separado:
        # O fim do campo volta ao paragrafo proprio, com o formato que ele tinha.
        c.insertBlock(formato_fim)
    return inicio, len(entradas)


def atualizar(editor, so_numeros: bool = False, figuras: bool = False) -> bool:
    """Atualiza o sumario do cursor (ou o primeiro). Um passo de desfazer. `figuras`: o indice
    de ilustracoes (o que tem o cursor; fora de todos, todos eles)."""
    nome = "índice de ilustrações" if figuras else "sumário"
    if not _no_corpo(editor):
        _recado(editor, f"Volte ao texto do documento para atualizar o {nome}.")
        return False
    doc = editor.documento_corpo()
    pos = editor.textCursor().position()
    todos = sumarios(doc, figuras)
    if not todos:
        _recado(editor, "O documento não tem índice de ilustrações. Use Referências > Inserir "
                        "Índice de Ilustrações." if figuras
                else "O documento não tem sumário. Use Sumário > Inserir sumário.")
        return False
    achado = next((c for c in todos if c[0] <= pos <= c[1] + 1), None)
    alvos = [todos.index(achado)] if achado is not None else \
        ([0] if not figuras else list(range(len(todos))))
    if so_numeros:
        _preparar(editor)
        mudou = False
        for k in alvos:
            ini = sumarios(doc, figuras)[k][0]
            mudou = _corrigir_numeros(editor, ini, juntar=False) or mudou
        _depois(editor)
        _recado(editor, f"Números de página do {nome} atualizados." if mudou
                else f"Os números de página do {nome} já estavam certos.")
        return True
    for k in alvos:
        motivo = mod.reconstruivel(todos[k][2].instrucao())
        if motivo:
            _recado(editor, motivo)
            return False
    _preparar(editor)
    c = QTextCursor(doc)
    c.beginEditBlock()
    total = 0
    primeiro = None
    for k in reversed(alvos):  # de baixo para cima: as posicoes de cima nao mudam
        ini, fim, campo = sumarios(doc, figuras)[k]
        inicio, n = _atualizar_um(editor, ini, fim, campo)
        primeiro = inicio
        total += n
    c.endEditBlock()
    _corrigir_numeros(editor, primeiro, juntar=True, todos=len(alvos) > 1)
    _depois(editor)
    _recado(editor, f"{nome.capitalize()} atualizado: {total} "
                    f"{'entrada' if total == 1 else 'entradas'}.")
    return True


def _pagerefs(doc, ini: int | None) -> list[tuple[int, int, str]]:
    """(inicio, fim, marcador) de cada PAGEREF dentro do sumario que comeca em `ini` (ou, sem
    `ini`, de todo o documento)."""
    todos = campos(doc)
    limite = None
    if ini is not None:
        limite = next(((a, b) for a, b, campo in todos if a == ini and mod.eh_sumario(campo)),
                      None)
        if limite is None:
            return []
    saida = []
    for a, b, campo in todos:
        if limite is None or (limite[0] < a and b < limite[1]):
            nome = mod.marcador_do_pageref(campo.instrucao())
            if nome is not None:
                saida.append((a, b, nome))
    return saida


def trocar_resultados(doc, trocas: list[tuple[int, int, str]]) -> None:
    """Escreve o novo resultado de cada campo `(inicio, fim, texto)` (de baixo para cima, dentro
    do bloco de edicao do chamador), com o formato do vizinho, sem as propriedades de objeto."""
    c = QTextCursor(doc)
    for a, b, novo in sorted(trocas, reverse=True):
        vizinho = pq_links.formato_em(doc, a + 1) if b > a + 1 else None
        fmt = formato_limpo(vizinho if vizinho is not None
                            else pq_links.formato_em(doc, a) or QTextCharFormat())
        c.setPosition(a + 1)
        c.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
        c.insertText(novo, fmt)


def _corrigir_numeros(editor, ini: int | None, juntar: bool, todos: bool = False,
                     apenas: int | None = None) -> bool:
    """Escreve a pagina de cada PAGEREF do sumario (ou, com `todos`, de todo o documento).
    `juntar`: no passo de desfazer anterior (um passo anotado, `_anotar`). True se algum numero
    mudou."""
    doc = editor.documento_corpo()
    mudou = False
    for rodada in range(RODADAS):
        _preparar(editor)
        refs = _pagerefs(doc, None if (todos or apenas is not None) else ini)
        if apenas is not None:
            refs = [r for r in refs if r[0] == apenas]
        if not refs:
            return mudou
        posicoes = _marcadores(doc)
        trocas = []
        for a, b, nome in refs:
            alvo = posicoes.get(nome)
            novo = mod.SEM_MARCADOR if alvo is None else pagina_de(editor, alvo + 1)
            c = QTextCursor(doc)
            c.setPosition(a + 1)
            c.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            if c.selectedText() != novo:
                trocas.append((a, b, novo))
        if not trocas:
            return mudou
        c = QTextCursor(doc)
        c.beginEditBlock()
        trocar_resultados(doc, trocas)
        c.endEditBlock()
        if juntar or rodada:
            anotar(editor, doc)
        mudou = True
    return mudou


def anotar(editor, doc) -> None:
    """O passo que acabou de entrar vai junto com o passo do usuario de antes no desfazer e no
    refazer do painel: um passo anotado, como os ajustes do layout (`interface/notas.py`).

    Nao e' `joinPreviousEditBlock`: entre o passo do usuario e a correcao dos numeros o layout
    pode ter gravado ajustes anotados (medido: a correcao juntada ao ultimo deles ficava com um
    numero de passo que a anotacao nao conhecia, e o Ctrl+Z desfazia so' os numeros)."""
    notas = getattr(getattr(editor, "layout_pag", None), "notas", None)
    if notas is None or not hasattr(notas, "passos"):
        return
    n = doc.availableUndoSteps()
    notas.passos.add(n)
    notas.indice = n


_anotar = anotar


def _depois(editor) -> None:
    if hasattr(editor, "_depois_de_mover"):
        editor._depois_de_mover()
    if hasattr(editor, "viewport"):
        editor.viewport().update()
