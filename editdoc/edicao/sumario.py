"""Sumario (Referencias > Sumario): inserir no cursor e atualizar, como no Word.

Inserir: o campo `TOC \\o "1-3" \\h \\z \\u` entra no cursor, em paragrafos proprios (o texto
antes e depois do cursor fica nos paragrafos de fora). Cada titulo (nivel de estrutura do bloco:
o do estilo "Titulo N" ou o direto) dentro dos niveis do campo vira uma linha no estilo "toc N"
(Sumario N, criado se o documento nao tem), com a tabulacao a direita com pontilhado na margem
direita e o numero da pagina. O titulo ganha um marcador oculto `_Toc...` (o que ja' tem um fica
com ele) e a linha aponta para ele: o hiperlink (Ctrl+clique vai ao titulo) e o PAGEREF.

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
from editdoc.modelo import sumario as mod
from editdoc.modelo.documento import CARACTERE_OBJETO, MarcaCampo, Marcador, Paragrafo, Run
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import links as pq_links
from editdoc.ponte_qt import marcas as pq_marcas
from editdoc.ponte_qt import secoes as pq_secoes

#: Rodadas de correcao dos numeros: o numero novo pode mudar a largura da linha e, raramente,
#: empurrar um titulo para a pagina seguinte.
RODADAS = 3


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


def sumarios(doc) -> list[tuple[int, int, object]]:
    return [c for c in campos(doc) if mod.eh_sumario(c[2])]


def sumario_do_cursor(doc, pos: int):
    """O sumario que contem `pos`; senao, o primeiro do documento; None se nao ha'."""
    todos = sumarios(doc)
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


def titulos(doc, opcoes: mod.Opcoes, fora: tuple[int, int] | None = None) -> list:
    """(bloco, nivel 1-9, texto) dos titulos dentro dos niveis, fora do intervalo `fora`."""
    saida = []
    bloco = doc.begin()
    while bloco.isValid():
        nivel = pq_estilos.nivel_do_bloco(bloco)
        if nivel is not None and opcoes.inclui(nivel + 1):
            ini, fim = bloco.position(), bloco.position() + bloco.length() - 1
            dentro = fora is not None and not (fim < fora[0] or ini > fora[1])
            texto = mod.texto_do_titulo(bloco.text())
            if texto and not dentro:
                saida.append((bloco, nivel + 1, texto))
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

def _formato_limpo(fmt) -> QTextCharFormat:
    """Formato de caractere de um vizinho sem as propriedades de objeto (marca, campo, imagem)."""
    from editdoc.ponte_qt import campos as pq_campos
    cf = QTextCharFormat(fmt.toCharFormat() if hasattr(fmt, "toCharFormat") else fmt)
    for prop in (*pq_marcas.PROPS_DE_MARCA, *pq_campos.PROPS_DE_CAMPO,
                 QTextFormat.Property.ObjectIndex, QTextFormat.Property.ImageName,
                 QTextFormat.Property.ImageWidth, QTextFormat.Property.ImageHeight):
        cf.clearProperty(prop)
    return cf


def _extras_da_tabulacao(pos_tw: int) -> str | None:
    """O w:pPr (forma canonica) com a tabulacao a direita com pontilhado em `pos_tw`."""
    from lxml import etree
    tabs = etree.Element(f"{{{W}}}tabs")
    tab = etree.SubElement(tabs, f"{{{W}}}tab")
    tab.set(f"{{{W}}}val", "right")
    tab.set(f"{{{W}}}leader", "dot")
    tab.set(f"{{{W}}}pos", str(int(pos_tw)))
    return canonico("pPr", [tabs])


def _largura_util(editor, pos: int) -> int:
    """Largura do texto (twips) da secao onde o sumario fica: a margem direita da tabulacao."""
    layout = editor.layout_pag
    try:
        pagina = layout.pagina_da_folha(max(0, layout.pagina_do_cursor(pos)))
    except (AttributeError, IndexError, ValueError):
        pagina = layout.pagina_arquivo
    return max(720, int(pagina.corpo_largura_tw()))


def garantir_estilos(doc, niveis) -> tuple[dict, str | None]:
    """(nivel -> id do estilo "toc N", id do Normal), criando os que faltam. A troca do catalogo
    entra no bloco de edicao aberto."""
    estilos = pq_estilos.catalogo(doc)
    nomes = [f"toc {n}" for n in sorted(set(niveis))]
    faltam = [n for n in nomes if (e := estilos.por_nome(n)) is None or e.virtual]
    if faltam:
        novo = estilos.copia()
        for nome in faltam:
            novo.garantir(nome)
        pq_estilos.trocar_catalogo(doc, novo)
        estilos = novo
    ids = {}
    for n in sorted(set(niveis)):
        e = estilos.por_nome(f"toc {n}")
        ids[n] = e.id if e is not None else None
    return ids, estilos.id_padrao()


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
    for k, (bloco, nivel, texto) in enumerate(achados):
        nome = _toc_do_bloco(bloco)
        if nome is None:
            nome = mod.nome_de_marcador(usados, semente=zlib.crc32(f"{k}:{texto}".encode()))
            marcar.append((QTextCursor(bloco), nome))
        entradas.append(mod.Entrada(texto, nivel, nome, pagina_de(editor, bloco.position())))
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
    return doc, opcoes, _extras_da_tabulacao(_largura_util(editor, pos))


def inserir(editor) -> bool:
    """Insere o sumario no cursor. Um passo de desfazer. False (com o motivo) se nao pode."""
    if not _no_corpo(editor):
        _recado(editor, "O sumário só pode ser inserido no texto do documento (não no cabeçalho, "
                        "no rodapé nem numa nota).")
        return False
    doc = editor.documento_corpo()
    pos = editor.textCursor().selectionStart()
    dentro = sumario_do_cursor(doc, pos)
    if dentro is not None and dentro[0] <= pos <= dentro[1]:
        _recado(editor, "O cursor está dentro de um sumário. Use \"Atualizar sumário\".")
        return False
    _preparar(editor)
    doc, opcoes, extras = _contexto(editor, pos, mod.INSTRUCAO_PADRAO)
    achados = titulos(doc, opcoes)
    usados = set(_marcadores(doc))
    entradas, marcar = _entradas(editor, achados, usados)
    c = QTextCursor(doc)
    c.setPosition(pos)
    c.beginEditBlock()
    ids, normal = garantir_estilos(doc, [e.nivel for e in entradas] or [1])
    res = pq_estilos.Resolvedor(pq_estilos.catalogo(doc))
    paragrafos = mod.paragrafos_do_sumario(entradas, ids, extras, opcoes, normal)
    paragrafos[0].runs.insert(0, Run(marca=MarcaCampo("inicio", mod.campo_toc())))
    paragrafos.append(Paragrafo(runs=[Run(marca=MarcaCampo("fim"))]))
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
    _corrigir_numeros(editor, inicio, juntar=True)
    final = QTextCursor(doc)
    achado = sumario_do_cursor(doc, inicio)
    final.setPosition(achado[1] + 1 if achado else min(c.position(), doc.characterCount() - 1))
    editor.setTextCursor(final)
    _depois(editor)
    _recado(editor, f"Sumário inserido com {len(entradas)} "
                    f"{'entrada' if len(entradas) == 1 else 'entradas'}.")
    return True


def atualizar(editor, so_numeros: bool = False) -> bool:
    """Atualiza o sumario do cursor (ou o primeiro). Um passo de desfazer."""
    if not _no_corpo(editor):
        _recado(editor, "Volte ao texto do documento para atualizar o sumário.")
        return False
    doc = editor.documento_corpo()
    pos = editor.textCursor().position()
    achado = sumario_do_cursor(doc, pos)
    if achado is None:
        _recado(editor, "O documento não tem sumário. Use Sumário > Inserir sumário.")
        return False
    ini, fim, campo = achado
    if so_numeros:
        _preparar(editor)
        mudou = _corrigir_numeros(editor, ini, juntar=False)
        _depois(editor)
        _recado(editor, "Números de página do sumário atualizados." if mudou
                else "Os números de página do sumário já estavam certos.")
        return True
    motivo = mod.reconstruivel(campo.instrucao())
    if motivo:
        _recado(editor, motivo)
        return False
    _preparar(editor)
    doc, opcoes, extras = _contexto(editor, ini, campo.instrucao())
    achados = titulos(doc, opcoes, fora=(ini, fim))
    usados = set(_marcadores(doc))
    entradas, marcar = _entradas(editor, achados, usados)
    bloco_ini, bloco_fim = doc.findBlock(ini), doc.findBlock(fim)
    separado = bloco_ini.blockNumber() != bloco_fim.blockNumber()
    formato_fim = QTextBlockFormat(bloco_fim.blockFormat())
    c = QTextCursor(doc)
    c.beginEditBlock()
    ids, normal = garantir_estilos(doc, [e.nivel for e in entradas] or [1])
    res = pq_estilos.Resolvedor(pq_estilos.catalogo(doc))
    paragrafos = mod.paragrafos_do_sumario(entradas, ids, extras, opcoes, normal)
    c.setPosition(ini + 1)
    c.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
    c.removeSelectedText()
    _marcar_titulos(doc, marcar, res)
    inicio = c.position() - 1  # a marca de inicio do sumario (os marcadores de cima a empurram)
    _escrever(c, paragrafos, res)
    if separado:
        # O fim do campo volta ao paragrafo proprio, com o formato que ele tinha.
        c.insertBlock(formato_fim)
    c.endEditBlock()
    _corrigir_numeros(editor, inicio, juntar=True)
    _depois(editor)
    _recado(editor, f"Sumário atualizado: {len(entradas)} "
                    f"{'entrada' if len(entradas) == 1 else 'entradas'}.")
    return True


def _pagerefs(doc, ini: int) -> list[tuple[int, int, str]]:
    """(inicio, fim, marcador) de cada PAGEREF dentro do sumario que comeca em `ini`."""
    todos = campos(doc)
    sumario = next(((a, b) for a, b, campo in todos if a == ini and mod.eh_sumario(campo)), None)
    if sumario is None:
        return []
    saida = []
    for a, b, campo in todos:
        if sumario[0] < a and b < sumario[1]:
            nome = mod.marcador_do_pageref(campo.instrucao())
            if nome is not None:
                saida.append((a, b, nome))
    return saida


def _corrigir_numeros(editor, ini: int, juntar: bool) -> bool:
    """Escreve a pagina de cada PAGEREF do sumario. `juntar`: no passo de desfazer anterior (um
    passo anotado, `_anotar`). True se algum numero mudou."""
    doc = editor.documento_corpo()
    mudou = False
    for rodada in range(RODADAS):
        _preparar(editor)
        refs = _pagerefs(doc, ini)
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
        for a, b, novo in reversed(trocas):
            vizinho = pq_links.formato_em(doc, a + 1) if b > a + 1 else None
            fmt = _formato_limpo(vizinho if vizinho is not None
                                 else pq_links.formato_em(doc, a) or QTextCharFormat())
            c.setPosition(a + 1)
            c.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            c.insertText(novo, fmt)
        c.endEditBlock()
        if juntar or rodada:
            _anotar(editor, doc)
        mudou = True
    return mudou


def _anotar(editor, doc) -> None:
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


def _depois(editor) -> None:
    if hasattr(editor, "_depois_de_mover"):
        editor._depois_de_mover()
    if hasattr(editor, "viewport"):
        editor.viewport().update()
