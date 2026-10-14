"""Notas de rodape e de fim (0.1.10): inserir, andar, opcoes, converter, copiar e colar.

Cada comando e' um passo de desfazer do corpo: a marca no texto e o catalogo no quadro raiz
(`ponte_qt/notas.py`) mudam no mesmo bloco de edicao. Apagar a marca apaga a nota (o catalogo
continua com ela, para o desfazer; o escritor so' grava as notas com referencia).

Inserir: a referencia entra no cursor (no fim da selecao) com o estilo "FootnoteReference" (ou
"EndnoteReference"); a nota nasce com um paragrafo no estilo "FootnoteText" com o numero da
propria nota e um espaco, como o Word faz, e o cursor vai para ela (edicao no lugar). Os quatro
estilos sao criados se faltam. A nota so' entra no corpo: no cabecalho, no rodape, numa nota ou
quando o arquivo tinha a parte de notas que o EditDoc nao conseguiu ler, o comando recusa com o
motivo na barra de status.
"""

from __future__ import annotations

import os
from dataclasses import replace

from PySide6.QtGui import QTextCharFormat, QTextCursor

from editdoc.modelo.documento import MarcaNota, Paragrafo, Run
from editdoc.modelo import notas as mod_notas
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import notas as pq

#: Nome canonico do Word dos estilos de cada tipo: (texto, referencia).
ESTILOS = {"rodape": ("footnote text", "footnote reference"),
           "fim": ("endnote text", "endnote reference")}
ID_PADRAO = {"rodape": ("FootnoteText", "FootnoteReference"),
             "fim": ("EndnoteText", "EndnoteReference")}
NOMES = {"rodape": "nota de rodapé", "fim": "nota de fim"}


def _recado(editor, texto: str) -> None:
    if hasattr(editor, "mensagem"):
        editor.mensagem.emit(texto)


def _no_corpo(editor) -> bool:
    return editor.editando_faixa() is None and getattr(editor, "editando_nota", lambda: None)() \
        is None


def garantir_estilos(doc, tipo: str) -> tuple[str | None, str | None]:
    """(id do estilo do texto, id do estilo da referencia), criando os que faltam (como o Word
    cria ao inserir a primeira nota). A troca do catalogo entra no bloco de edicao aberto."""
    estilos = pq_estilos.catalogo(doc)
    nomes = ESTILOS[tipo]
    faltam = [n for sid, n in zip(ID_PADRAO[tipo], nomes)
              if estilos.obter(sid) is None and estilos.por_nome(n) is None]
    if not faltam:
        virtuais = [e for n in nomes if (e := estilos.por_nome(n)) is not None and e.virtual]
        if virtuais:
            faltam = [e.nome for e in virtuais]
    if faltam:
        novo = estilos.copia()
        for nome in faltam:
            novo.garantir(nome)
        pq_estilos.trocar_catalogo(doc, novo)
        estilos = novo
    saida = []
    for sid, nome in zip(ID_PADRAO[tipo], nomes):
        e = estilos.obter(sid) or estilos.por_nome(nome)
        saida.append(e.id if e is not None else None)
    return saida[0], saida[1]


def formato_da_referencia(doc, sid: str | None) -> QTextCharFormat:
    estilos = pq_estilos.catalogo(doc)
    if sid is None or estilos.obter(sid) is None:
        cf = QTextCharFormat()
        cf.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
        return cf
    res = pq_estilos.Resolvedor(estilos)
    return pq_estilos.formato_de_caractere(res.caractere(None, sid), sid)


def conteudo_novo(tipo: str, sid_texto: str | None, sid_ref: str | None, texto: str = "") -> tuple:
    """O paragrafo da nota nova: o numero da propria nota, um espaco e o texto."""
    return (Paragrafo(estilo=sid_texto, runs=[
        Run(marca=MarcaNota(tipo, 0, propria=True), estilo=sid_ref), Run(" " + texto)]),)


def pode_inserir(editor, tipo: str) -> str:
    """"" se pode; senao, o motivo (para a barra de status)."""
    if not _no_corpo(editor):
        return "A nota só pode ser inserida no texto do documento (não no cabeçalho, no rodapé " \
               "nem dentro de outra nota)."
    doc = editor.documento_corpo()
    if tipo in getattr(doc, "_notas_preservadas", ()):
        return (f"Este arquivo tem {NOMES[tipo]}s que o EditDoc não conseguiu ler (danificadas ou "
                "acima dos limites). Elas continuam no arquivo, mas novas não podem ser inseridas.")
    if len(pq.catalogo(doc).itens.get(tipo, [])) >= mod_notas.LIMITES["notas"]:
        return "O documento chegou ao limite de notas do EditDoc."
    return ""


def inserir(editor, tipo: str, texto: str = "", entrar: bool = True) -> int | None:
    """Insere uma nota no cursor. Um passo de desfazer. Devolve o id, ou None (com o motivo)."""
    motivo = pode_inserir(editor, tipo)
    if motivo:
        _recado(editor, motivo)
        return None
    doc = editor.documento_corpo()
    cursor = editor.textCursor()
    pos = cursor.selectionEnd()
    c = QTextCursor(doc)
    c.setPosition(pos)
    c.beginEditBlock()
    sid_texto, sid_ref = garantir_estilos(doc, tipo)
    cat = pq.catalogo(doc)
    ident = cat.proximo_id(tipo)
    pq.inserir(c, MarcaNota(tipo, ident), formato_da_referencia(doc, sid_ref))
    nota = mod_notas.Nota(tipo, ident, conteudo_novo(tipo, sid_texto, sid_ref, texto))
    itens = {t: list(cat.itens.get(t, [])) for t in mod_notas.TIPOS}
    itens[tipo].append(nota)
    pq.trocar(doc, itens)
    c.endEditBlock()
    doc._numeros_notas = pq.numeros_continuos(doc)
    cursor = QTextCursor(doc)
    cursor.setPosition(pos + 1)
    editor.setTextCursor(cursor)
    layout = editor.layout_pag
    layout.atualizar_notas()
    if entrar:
        nota_qt = layout.notas.nota_qt(tipo, ident)
        if nota_qt is not None:
            editor.entrar_na_nota(nota_qt)
    editor.viewport().update()
    return ident


# -- andar ------------------------------------------------------------------------------

def referencia(doc, tipo: str, ident: int) -> int | None:
    for pos, m in pq.referencias(doc):
        if (m.tipo, m.id) == (tipo, ident):
            return pos
    return None


def ir_para_nota(editor, tipo: str, ident: int) -> bool:
    """Leva o cursor ao texto da nota (edicao no lugar)."""
    layout = editor.layout_pag
    layout.atualizar_notas()
    nota_qt = layout.notas.nota_qt(tipo, ident)
    if nota_qt is None:
        return False
    editor.entrar_na_nota(nota_qt)
    return True


def ir_para_referencia(editor, tipo: str, ident: int) -> bool:
    """Volta ao corpo, com o cursor logo depois da marca da nota."""
    doc = editor.documento_corpo()
    pos = referencia(doc, tipo, ident)
    if pos is None:
        return False
    editor.sair_da_faixa()
    editor.ir_para_posicao(pos + 1)
    return True


def proxima(editor, anterior: bool = False, tipo: str | None = None) -> bool:
    """Proxima (ou anterior) referencia de nota depois do cursor, no corpo. Na edicao de uma
    nota, parte da referencia dela."""
    doc = editor.documento_corpo()
    nota = getattr(editor, "editando_nota", lambda: None)()
    if nota is not None:
        base = referencia(doc, nota.tipo, nota.id)
        base = (base if base is not None else 0) + (0 if anterior else 1)
    elif editor.editando_faixa() is not None:
        base = 0
    else:
        c = editor.textCursor()
        base = c.selectionStart() if anterior else c.selectionEnd()
    refs = [p for p, m in pq.referencias(doc) if tipo is None or m.tipo == tipo]
    alvo = None
    if anterior:
        antes = [p for p in refs if p < base - (0 if nota is not None else 1)]
        alvo = antes[-1] if antes else None
    else:
        depois = [p for p in refs if p >= base]
        alvo = depois[0] if depois else None
    if alvo is None:
        _recado(editor, "Não há outra nota " + ("antes." if anterior else "depois."))
        return False
    editor.sair_da_faixa()
    c = QTextCursor(doc)
    c.setPosition(alvo)
    c.setPosition(alvo + 1, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(c)
    return True


# -- opcoes ------------------------------------------------------------------------------

def propriedades(editor, tipo: str) -> mod_notas.PropriedadesNota:
    return pq.catalogo(editor.documento_corpo()).propriedades(tipo)


def aplicar_propriedades(editor, tipo: str, pr: mod_notas.PropriedadesNota) -> bool:
    """Formato, inicio, reinicio e posicao das notas do tipo (no sectPr). Um passo de desfazer.
    So' o que difere do efetivo de agora vai para o arquivo."""
    if editor.editando_faixa() is not None or getattr(editor, "editando_nota", lambda: None)():
        editor.sair_da_faixa()
    doc = editor.documento_corpo()
    cat = pq.catalogo(doc)
    if cat.propriedades(tipo) == mod_notas.efetivas(tipo, pr, cat.secao.get(tipo),
                                                     cat.configuracao.get(tipo)):
        return False
    secao = dict(cat.secao)
    atual = secao.get(tipo) or mod_notas.PropriedadesNota()
    secao[tipo] = mod_notas.PropriedadesNota(
        pr.formato if pr.formato is not None else atual.formato,
        pr.inicio if pr.inicio is not None else atual.inicio,
        pr.reinicio if pr.reinicio is not None else atual.reinicio,
        pr.posicao if pr.posicao is not None else atual.posicao)
    c = QTextCursor(doc)
    c.beginEditBlock()
    pq.trocar(doc, cat.itens, secao)
    c.endEditBlock()
    doc._numeros_notas = pq.numeros_continuos(doc)
    editor.layout_pag.notas.atualizar(forcar=True)
    editor.viewport().update()
    return True


def converter(editor, de: str) -> int:
    """Converte todas as notas do tipo `de` no outro (rodape <-> fim). Um passo de desfazer.
    Devolve quantas mudaram. Os paragrafos no estilo de texto de um tipo passam ao do outro, e a
    marca (referencia e numero proprio) ao estilo de referencia do outro."""
    para = "fim" if de == "rodape" else "rodape"
    editor.sair_da_faixa()
    motivo = pode_inserir(editor, para)
    if motivo:
        _recado(editor, motivo)
        return 0
    doc = editor.documento_corpo()
    refs = [(p, m) for p, m in pq.referencias(doc) if m.tipo == de]
    if not refs:
        return 0
    c = QTextCursor(doc)
    c.beginEditBlock()
    sid_texto_de, sid_ref_de = garantir_estilos(doc, de)
    sid_texto, sid_ref = garantir_estilos(doc, para)
    cat = pq.catalogo(doc)
    itens = {t: list(cat.itens.get(t, [])) for t in mod_notas.TIPOS}
    proximo = cat.proximo_id(para)
    for pos, m in refs:
        nota = cat.obter(de, m.id)
        if nota is None:
            continue
        novo_id = proximo
        proximo += 1
        conteudo = []
        for bloco in nota.paragrafos:
            if isinstance(bloco, Paragrafo):
                runs = [replace(r, marca=MarcaNota(para, 0, True),
                                estilo=sid_ref if r.estilo == sid_ref_de else r.estilo)
                        if isinstance(r.marca, MarcaNota) and r.marca.propria else r
                        for r in bloco.runs]
                bloco = replace(bloco, runs=runs,
                                estilo=sid_texto if bloco.estilo == sid_texto_de else bloco.estilo)
            conteudo.append(bloco)
        itens[para].append(mod_notas.Nota(para, novo_id, tuple(conteudo)))
        k = QTextCursor(doc)
        k.setPosition(pos)
        k.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat(k.charFormat())
        from editdoc.ponte_qt import links as pq_links
        fmt = pq_links.formato_em(doc, pos) or fmt
        base = formato_da_referencia(doc, sid_ref) if \
            pq_estilos.estilo_do_caractere(fmt) == sid_ref_de else QTextCharFormat(fmt)
        k.insertText(chr(0xFFFC), pq.formato_de_marca(base, replace(m, tipo=para, id=novo_id)))
    pq.trocar(doc, itens)
    c.endEditBlock()
    doc._numeros_notas = pq.numeros_continuos(doc)
    editor.layout_pag.notas.atualizar(forcar=True)
    editor.viewport().update()
    return len(refs)


# -- copiar e colar ------------------------------------------------------------------------

def _omitido(cf) -> bool:
    from editdoc.ponte_qt.propriedades import _omitido as omitido
    return omitido(cf)


def dados_para_copiar(doc, inicio: int, fim: int) -> dict | None:
    """As notas de [inicio, fim): a posicao no texto que o HTML leva (sem os objetos de tipo
    proprio) e a chave do conteudo. None se nao ha' nota. So' vale no mesmo processo."""
    cat = pq.catalogo(doc)
    refs = [(p, m) for p, m in pq.referencias(doc) if inicio <= p < fim]
    if not refs:
        return None
    bloco = doc.findBlock(inicio)
    marcas_omitidas = []
    while bloco.isValid() and bloco.position() <= max(inicio, fim - 1):
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                a = max(frag.position(), inicio)
                b = min(frag.position() + frag.length(), fim)
                if a < b and _omitido(frag.charFormat()):
                    marcas_omitidas.extend(range(a, b))
            it += 1
        bloco = bloco.next()
    marcas_omitidas.sort()
    saida = []
    for p, m in refs:
        nota = cat.obter(m.tipo, m.id)
        if nota is None:
            continue
        antes = sum(1 for x in marcas_omitidas if x < p)
        saida.append([p - inicio - antes, pq.chave(nota), m.tipo, m.personalizada,
                      m.simbolo or ""])
    if not saida:
        return None
    return {"pid": os.getpid(), "notas": saida, "tamanho": fim - inicio - len(marcas_omitidas)}


def aplicar_colado(doc, dado: dict, inicio: int, fim: int) -> int:
    """Devolve as notas ao texto colado em [inicio, fim), com ids novos e o mesmo conteudo.
    Quem chama abre o bloco de edicao. Outro processo, ou tamanho diferente (outro programa no
    meio): nada (as referencias ficam de fora, como o objeto preservado)."""
    if dado.get("pid") != os.getpid() or dado.get("tamanho") != fim - inicio:
        return 0
    itens_colados = []
    for item in dado.get("notas") or []:
        if not (isinstance(item, list) and len(item) == 5 and isinstance(item[0], int)
                and isinstance(item[1], str) and item[2] in mod_notas.TIPOS):
            continue
        nota = pq.nota_da_chave(item[1])
        if nota is None or not 0 <= item[0] <= fim - inicio:
            continue
        itens_colados.append((item[0], nota, item[2], bool(item[3]), item[4] or None))
    if not itens_colados:
        return 0
    cat = pq.catalogo(doc)
    itens = {t: list(cat.itens.get(t, [])) for t in mod_notas.TIPOS}
    proximos = {t: cat.proximo_id(t) for t in mod_notas.TIPOS}
    estilos = {t: garantir_estilos(doc, t) for t in {x[2] for x in itens_colados}}
    ordem = sorted(enumerate(itens_colados), key=lambda x: (-x[1][0], -x[0]))
    for _i, (deslocamento, nota, tipo, personalizada, simbolo) in ordem:
        ident = proximos[tipo]
        proximos[tipo] += 1
        c = QTextCursor(doc)
        c.setPosition(inicio + deslocamento)
        pq.inserir(c, MarcaNota(tipo, ident, personalizada=personalizada, simbolo=simbolo),
                   formato_da_referencia(doc, estilos[tipo][1]))
        itens[tipo].append(mod_notas.Nota(tipo, ident, nota.paragrafos))
    pq.trocar(doc, itens)
    doc._numeros_notas = pq.numeros_continuos(doc)
    return len(itens_colados)
