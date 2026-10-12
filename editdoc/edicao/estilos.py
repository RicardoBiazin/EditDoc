"""Comandos de estilo (M6): aplicar, limpar, modificar, atualizar pela selecao e criar.

Cada comando que muda o texto e' UM passo de desfazer. Mudar a definicao de um estilo
troca o catalogo (guardado no quadro raiz do documento, ver ponte_qt/estilos.py) e
recompoe os paragrafos que o usam no MESMO bloco de edicao: um desfazer devolve o
catalogo e os paragrafos.

Formatacao direta e' mantida: o que o texto tinha diferente do estilo velho continua
diferente; o que era igual ao estilo velho passa a ser o estilo novo (a decisao do
docs/ARQUITETURA.md, "Atualizar estilo").

O cabecalho e o rodape usam o catalogo do corpo. Modificar um estilo atualiza tambem os
paragrafos deles, cada um no seu proprio desfazer.
"""

from __future__ import annotations

import copy

from PySide6.QtGui import QTextBlockFormat, QTextCharFormat, QTextCursor

from editdoc.modelo.estilos import (CAMPOS_CARACTERE, CAMPOS_PARAGRAFO, Estilo, Estilos,
                                    props_proprias)
from editdoc.ponte_qt import estilos as pq

#: Nome canonico do Word dos estilos que os atalhos aplicam.
NOME_NORMAL = "normal"
TITULOS = ("heading 1", "heading 2", "heading 3")


def catalogo_de(editor) -> Estilos:
    return pq.catalogo(editor.document())


def _corpo(editor):
    return editor.documento_corpo() if hasattr(editor, "documento_corpo") else editor.document()


def _blocos_da_selecao(editor) -> list:
    doc = editor.document()
    cursor = editor.textCursor()
    atual = doc.findBlock(cursor.selectionStart())
    ultimo = doc.findBlock(cursor.selectionEnd()).blockNumber()
    blocos = []
    while atual.isValid():
        blocos.append(atual)
        if atual.blockNumber() >= ultimo:
            break
        atual = atual.next()
    return blocos


def _depois(editor) -> None:
    """Avisa a faixa e a galeria (o painel emite os sinais de cursor e formato)."""
    if hasattr(editor, "_depois_de_mover"):
        editor._depois_de_mover()


# -- leitura --------------------------------------------------------------------------

def estilo_no_cursor(editor) -> tuple[str | None, str | None]:
    """(estilo de paragrafo, estilo de caractere) no cursor. O de paragrafo nunca e' None
    se o catalogo tem estilo padrao."""
    estilos = catalogo_de(editor)
    cursor = editor.textCursor()
    bloco = editor.document().findBlock(cursor.selectionStart())
    sid = pq.estilo_do_bloco(bloco.blockFormat()) or estilos.id_padrao()
    if cursor.hasSelection():
        ref = QTextCursor(editor.document())
        ref.setPosition(cursor.selectionStart())
        ref.setPosition(cursor.selectionStart() + 1, QTextCursor.MoveMode.KeepAnchor)
        cf = ref.charFormat()
    else:
        cf = editor.currentCharFormat()
    return sid, pq.estilo_do_caractere(cf)


def _efetivo_no_cursor(editor) -> tuple[dict, dict]:
    """(paragrafo, caractere) efetivos no cursor, como o Qt os tem."""
    cursor = editor.textCursor()
    doc = editor.document()
    bloco = doc.findBlock(cursor.selectionStart())
    if cursor.hasSelection():
        ref = QTextCursor(doc)
        ref.setPosition(cursor.selectionStart())
        ref.setPosition(cursor.selectionStart() + 1, QTextCursor.MoveMode.KeepAnchor)
        cf = ref.charFormat()
    elif bloco.length() <= 1:
        cf = bloco.charFormat()
    else:
        cf = editor.currentCharFormat()
    return pq.props_de_bloco(bloco.blockFormat()), pq.props_de_caractere(cf)


# -- catalogo -------------------------------------------------------------------------

def _garantido(editor, sid_ou_nome: str) -> tuple[Estilos, Estilos, str | None]:
    """(catalogo velho, catalogo novo, id). O novo ganha o estilo interno que faltava."""
    velho = catalogo_de(editor)
    if velho.obter(sid_ou_nome) is not None:
        return velho, velho, sid_ou_nome
    novo = velho.copia()
    estilo = novo.garantir(sid_ou_nome)
    if estilo is None:
        return velho, velho, None
    # O estilo padrao aplicado pelo nome ja' existia (garantir achou): sem mudanca.
    if velho.obter(estilo.id) is not None:
        return velho, velho, estilo.id
    return velho, novo, estilo.id


# -- aplicar ---------------------------------------------------------------------------

def aplicar_estilo(editor, sid_ou_nome: str) -> str | None:
    """Aplica o estilo (pelo id ou pelo nome canonico). Devolve o id aplicado."""
    velho, novo, sid = _garantido(editor, sid_ou_nome)
    if sid is None:
        return None
    if novo.obter(sid).tipo == "caractere":
        _aplicar_caractere(editor, velho, novo, sid)
    else:
        _aplicar_paragrafo(editor, velho, novo, sid)
    return sid


def aplicar_estilo_paragrafo(editor, sid_ou_nome: str) -> str | None:
    return aplicar_estilo(editor, sid_ou_nome)


def _aplicar_paragrafo(editor, velho: Estilos, novo: Estilos, sid: str) -> None:
    doc = editor.document()
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    if novo is not velho:
        pq.trocar_catalogo(doc, novo)
    pq.recompor_blocos(doc, _blocos_da_selecao(editor), pq.Resolvedor(velho),
                       pq.Resolvedor(novo), sid_novo=sid)
    cursor.endEditBlock()
    _formato_de_digitacao(editor)
    _depois(editor)


def _formato_de_digitacao(editor) -> None:
    """Sem selecao num paragrafo vazio, o que se digita segue o estilo do paragrafo."""
    cursor = editor.textCursor()
    if not cursor.hasSelection() and cursor.block().length() <= 1:
        editor.setCurrentCharFormat(QTextCharFormat(cursor.block().charFormat()))


def _aplicar_caractere(editor, velho: Estilos, novo: Estilos, sid: str | None) -> None:
    doc = editor.document()
    cursor = editor.textCursor()
    if not cursor.hasSelection():
        palavra = QTextCursor(cursor)
        palavra.select(QTextCursor.SelectionType.WordUnderCursor)
        if palavra.hasSelection() and palavra.selectionStart() < cursor.position() < palavra.selectionEnd():
            cursor = palavra
        else:
            # Fora de palavra: vale para o que se digitar.
            res_v, res_n = pq.Resolvedor(velho), pq.Resolvedor(novo)
            sid_par = pq.estilo_do_bloco(cursor.block().blockFormat())
            cf = editor.currentCharFormat()
            atual = pq.estilo_do_caractere(cf)
            ncf = pq.recompor_caractere(cf, res_v.caractere(sid_par, atual),
                                        res_n.caractere(sid_par, sid), sid)
            if novo is not velho:
                c = editor.textCursor()
                c.beginEditBlock()
                pq.trocar_catalogo(doc, novo)
                c.endEditBlock()
            editor.setCurrentCharFormat(ncf)
            _depois(editor)
            return
    inicio, fim = cursor.selectionStart(), cursor.selectionEnd()
    blocos = []
    bloco = doc.findBlock(inicio)
    while bloco.isValid() and bloco.position() < fim:
        blocos.append(bloco)
        bloco = bloco.next()
    cursor.beginEditBlock()
    if novo is not velho:
        pq.trocar_catalogo(doc, novo)
    pq.recompor_blocos(doc, blocos, pq.Resolvedor(velho), pq.Resolvedor(novo),
                       trecho=(inicio, fim), car_novo=sid, mexer_no_bloco=False)
    cursor.endEditBlock()
    _depois(editor)


# -- limpar ----------------------------------------------------------------------------

def limpar_formatacao(editor) -> None:
    """Limpar toda a formatacao: os paragrafos voltam ao Normal; o texto perde a formatacao
    direta e o estilo de caractere. Sem selecao, vale para o paragrafo do cursor e para o
    que se digitar."""
    estilos = catalogo_de(editor)
    res = pq.Resolvedor(estilos)
    padrao = estilos.id_padrao()
    doc = editor.document()
    cursor = editor.textCursor()
    trecho = (cursor.selectionStart(), cursor.selectionEnd()) if cursor.hasSelection() else (-1, -1)
    cursor.beginEditBlock()
    pq.recompor_blocos(doc, _blocos_da_selecao(editor), res, res, sid_novo=padrao,
                       manter_direto_paragrafo=False, trecho=trecho, car_novo=None,
                       limpar_direto=True)
    cursor.endEditBlock()
    if not cursor.hasSelection():
        editor.setCurrentCharFormat(pq.formato_de_caractere(res.caractere(padrao, None)))
    _depois(editor)


def limpar_caractere(editor) -> None:
    """Ctrl+Espaco do Word: o texto volta ao estilo do paragrafo (sem direta e sem estilo
    de caractere). O formato do paragrafo nao muda."""
    estilos = catalogo_de(editor)
    res = pq.Resolvedor(estilos)
    doc = editor.document()
    cursor = editor.textCursor()
    if not cursor.hasSelection():
        sid_par = pq.estilo_do_bloco(cursor.block().blockFormat())
        editor.setCurrentCharFormat(pq.formato_de_caractere(res.caractere(sid_par, None)))
        _depois(editor)
        return
    inicio, fim = cursor.selectionStart(), cursor.selectionEnd()
    blocos = []
    bloco = doc.findBlock(inicio)
    while bloco.isValid() and bloco.position() < fim:
        blocos.append(bloco)
        bloco = bloco.next()
    cursor.beginEditBlock()
    pq.recompor_blocos(doc, blocos, res, res, trecho=(inicio, fim), car_novo=None,
                       limpar_direto=True, mexer_no_bloco=False)
    cursor.endEditBlock()
    _depois(editor)


# -- modificar, atualizar e criar --------------------------------------------------------

def _afetados(estilos: Estilos, sid: str) -> set[str]:
    """O estilo e todos os que herdam dele (direta ou indiretamente)."""
    return {e.id for e in estilos.itens.values()
            if any(x.id == sid for x in estilos.cadeia(e.id))}


def redefinir_estilo(editor, estilo: Estilo, novo_id: bool = False) -> None:
    """Troca a definicao do estilo e recompoe todos os paragrafos que o usam.

    Um passo de desfazer no corpo. `novo_id`: o estilo e' novo (Criar estilo).
    """
    corpo = _corpo(editor)
    velho = pq.catalogo(corpo)
    novo = velho.copia()
    estilo = copy.deepcopy(estilo)
    if not novo_id:
        estilo.alterado = True
    novo.itens[estilo.id] = estilo
    afetados = _afetados(novo, estilo.id) | _afetados(velho, estilo.id)

    def filtro(sid_par, sid_car) -> bool:
        par = sid_par or velho.id_padrao()
        return par in afetados or (sid_car is not None and sid_car in afetados)

    rv, rn = pq.Resolvedor(velho), pq.Resolvedor(novo)
    cursor = QTextCursor(corpo)
    cursor.beginEditBlock()
    pq.trocar_catalogo(corpo, novo)
    pq.recompor_blocos(corpo, _todos_os_blocos(corpo), rv, rn, filtro=filtro)
    cursor.endEditBlock()
    for doc in _documentos_de_faixa(editor):
        c = QTextCursor(doc)
        c.beginEditBlock()
        pq.recompor_blocos(doc, _todos_os_blocos(doc), rv, rn, filtro=filtro)
        c.endEditBlock()
    _formato_de_digitacao(editor)
    _depois(editor)


def _todos_os_blocos(doc):
    bloco = doc.firstBlock()
    while bloco.isValid():
        yield bloco
        bloco = bloco.next()


def _documentos_de_faixa(editor) -> list:
    layout = getattr(editor, "layout_pag", None)
    if layout is None:
        return []
    return [f.doc for f in layout.faixas.todas()]


def estilo_da_selecao(editor, sid: str) -> Estilo | None:
    """O estilo `sid` redefinido para ficar igual a formatacao do cursor ("Atualizar")."""
    estilos = catalogo_de(editor)
    atual = estilos.obter(sid)
    if atual is None:
        return None
    par_ef, car_ef = _efetivo_no_cursor(editor)
    novo = copy.deepcopy(atual)
    fora_da_tabela = editor.textCursor().currentTable() is None
    base_par, base_car = estilos.resolver_paragrafo(atual.baseado_em, fora_da_tabela) \
        if atual.baseado_em else (_padrao(estilos, fora_da_tabela), {})
    if atual.tipo == "caractere":
        sid_par = estilo_no_cursor(editor)[0]
        base_par_car = estilos.base_de_caractere(sid_par, None)
        base = dict(base_par_car)
        base.update(estilos.resolver_caractere(atual.baseado_em))
        novo.caractere = props_proprias(car_ef, base, CAMPOS_CARACTERE)
        return novo
    novo.paragrafo = props_proprias(par_ef, base_par, CAMPOS_PARAGRAFO)
    novo.caractere = props_proprias(car_ef, base_car, CAMPOS_CARACTERE)
    return novo


def _padrao(estilos: Estilos, fora_da_tabela: bool) -> dict:
    """O docDefaults de paragrafo, que fica por baixo de tudo fora da tabela (M8)."""
    return estilos.resolver_paragrafo(None, com_padrao=True)[0] if fora_da_tabela else {}


def atualizar_pela_selecao(editor, sid: str | None = None) -> bool:
    """Atualizar o estilo para corresponder a selecao. Sem `sid`, o estilo do paragrafo."""
    sid = sid or estilo_no_cursor(editor)[0]
    novo = estilo_da_selecao(editor, sid) if sid else None
    if novo is None:
        return False
    redefinir_estilo(editor, novo)
    return True


def modelo_da_selecao(editor, nome: str, tipo: str = "paragrafo") -> Estilo | None:
    """Estilo novo (ainda fora do catalogo) com a formatacao do cursor, baseado no estilo
    do paragrafo. None se o nome for vazio ou ja' existir."""
    nome = nome.strip()
    estilos = pq.catalogo(_corpo(editor))
    if not nome or estilos.por_nome(nome) is not None:
        return None
    sid_par, _sid_car = estilo_no_cursor(editor)
    par_ef, car_ef = _efetivo_no_cursor(editor)
    sid = estilos.novo_id(nome)
    if tipo == "caractere":
        base = estilos.base_de_caractere(sid_par, None)
        return Estilo(sid, nome, tipo="caractere", rapido=True, personalizado=True,
                      caractere=props_proprias(car_ef, base, CAMPOS_CARACTERE))
    base_par, base_car = estilos.resolver_paragrafo(
        sid_par, com_padrao=editor.textCursor().currentTable() is None)
    nivel = par_ef.get("nivel")
    return Estilo(sid, nome, baseado_em=sid_par, proximo=sid, rapido=True, personalizado=True,
                  paragrafo=props_proprias(par_ef, base_par, CAMPOS_PARAGRAFO),
                  caractere=props_proprias(car_ef, base_car, CAMPOS_CARACTERE),
                  nivel=nivel if nivel != base_par.get("nivel") else None)


def adicionar_estilo(editor, estilo: Estilo) -> str | None:
    """Poe o estilo novo no catalogo e o aplica a selecao. Um passo de desfazer."""
    estilos = pq.catalogo(_corpo(editor))
    if estilo.id in estilos.itens or estilos.por_nome(estilo.nome) is not None:
        return None
    estilo = copy.deepcopy(estilo)
    estilo.no_arquivo = False
    novo = estilos.copia()
    novo.itens[estilo.id] = estilo
    if estilo.tipo == "caractere":
        _aplicar_caractere(editor, estilos, novo, estilo.id)
    else:
        _aplicar_paragrafo(editor, estilos, novo, estilo.id)
    return estilo.id


def criar_da_selecao(editor, nome: str, tipo: str = "paragrafo") -> str | None:
    """Estilo novo com a formatacao do cursor, baseado no estilo atual, e aplicado a ele."""
    estilo = modelo_da_selecao(editor, nome, tipo)
    return adicionar_estilo(editor, estilo) if estilo is not None else None


# -- Enter: o estilo seguinte ------------------------------------------------------------

def formatos_do_proximo(doc, bf_anterior: QTextBlockFormat) -> tuple | None:
    """(formato de bloco, formato de caractere) do paragrafo criado pelo Enter no fim de um
    paragrafo cujo estilo tem outro `next` (Titulo 1 -> Normal). None = sem troca."""
    estilos = pq.catalogo(doc)
    sid = pq.estilo_do_bloco(bf_anterior) or estilos.id_padrao()
    atual = estilos.obter(sid)
    if atual is None or not atual.proximo or atual.proximo == sid:
        return None
    proximo = estilos.obter(atual.proximo)
    if proximo is None or proximo.tipo != "paragrafo":
        return None
    par, car = estilos.resolver_paragrafo(proximo.id, com_padrao=True)
    bf = QTextBlockFormat()
    pq.aplicar_bloco(bf, par)
    bf.setPageBreakPolicy(bf_anterior.pageBreakPolicy())
    pq.marcar_estilo(bf, proximo.id, estilos)
    return bf, pq.formato_de_caractere(car)
