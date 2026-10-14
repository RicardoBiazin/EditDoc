"""Comentarios (0.1.6): criar, responder, editar, resolver, excluir e andar entre eles.

Cada comando e' um passo de desfazer: as ancoras no texto e o catalogo no quadro raiz mudam
no mesmo bloco de edicao (`ponte_qt/comentarios.py`). Os comandos valem para o corpo (o Word
nao tem comentario no cabecalho e no rodape).

Apagar texto que tem ancoras (`remover_selecao`), como o Word:

- se a selecao leva a referencia do comentario, ou o trecho comentado inteiro (o inicio e o
  fim, ou todo o texto entre eles), o comentario vai junto, com as respostas;
- se leva so' uma ponta, o comentario fica ancorado no que sobrou: a marca da ponta volta no
  ponto onde a selecao foi apagada (fins antes, inicios depois, para o trecho nao virar do
  avesso).

Conteudo: o texto do comentario sao paragrafos do modelo (`Paragrafo`/`Run`), com o estilo
"CommentText" quando o catalogo o tem. `editavel` diz se o editor simples (negrito, italico,
sublinhado e links) regrava o conteudo sem perda; o resto (campo, marcador, imagem, objeto,
tabela) abre so' para leitura, com o motivo, e responder e resolver continuam valendo.
"""

from __future__ import annotations

import getpass
import os
from dataclasses import replace

from PySide6.QtGui import QTextCharFormat, QTextCursor

from editdoc.modelo.comentarios import Comentario, Comentarios, agora_local, agora_utc, iniciais_de
from editdoc.modelo.documento import MarcaComentario, Paragrafo, Run, Tabela
from editdoc.ponte_qt import comentarios as pq
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import marcas

#: Limite de comentarios que o EditDoc cria (o mesmo do leitor).
MAXIMO = 5000


def nome_do_windows() -> str:
    """O nome do usuario do Windows (o padrao da preferencia "Nome de usuario")."""
    try:
        nome = getpass.getuser()
    except Exception:  # noqa: BLE001 - sem usuario no ambiente
        nome = os.environ.get("USERNAME", "")
    return (nome or "Usuário").strip()[:255]


def autor_das_preferencias(cfg: dict) -> tuple[str, str]:
    """(nome, iniciais) das Opcoes; vazio = o usuario do Windows e as iniciais dele."""
    nome = (cfg.get("nome_usuario") or "").strip() or nome_do_windows()
    iniciais = (cfg.get("iniciais") or "").strip() or iniciais_de(nome)
    return nome, iniciais[:9]


def conteudo_de_texto(texto: str, estilo: str | None = "CommentText") -> tuple:
    """Paragrafos de um texto simples (cada linha um paragrafo)."""
    linhas = (texto or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return tuple(Paragrafo(runs=[Run(linha)] if linha else [], estilo=estilo) for linha in linhas)


def motivo_somente_leitura(c: Comentario) -> str:
    """Por que o conteudo nao se edita sem perda ("" = editavel)."""
    for bloco in c.paragrafos:
        if isinstance(bloco, Tabela):
            return "O comentário tem uma tabela, que o editor de comentários não regrava."
        for r in bloco.runs:
            if r.marca is not None:
                return ("O comentário tem um campo ou um marcador (uma menção, por exemplo), "
                        "que o editor de comentários não regrava sem perda.")
            if r.imagem is not None or r.objeto is not None:
                return "O comentário tem uma imagem ou um objeto, que o editor não regrava."
            if r.campo is not None:
                return "O comentário tem um campo de página, que o editor não regrava."
    return ""


# -- consulta -----------------------------------------------------------------------------

def catalogo(editor) -> Comentarios:
    return pq.catalogo(editor.documento_corpo())


def no_cursor(editor) -> int | None:
    """O comentario do cursor (o trecho mais interno, ou a referencia vizinha)."""
    if editor.editando_faixa() is not None:
        return None
    doc = editor.documento_corpo()
    cat = pq.catalogo(doc)
    if not cat.itens:
        return None  # sem comentarios, nada a varrer (o atualizador roda a cada tecla)
    return pq.no_cursor(doc, cat, editor.textCursor().position())


def ancorados(editor) -> list[int]:
    doc = editor.documento_corpo()
    return pq.ordem_no_texto(doc, pq.catalogo(doc))


def selecionar(editor, ident: int) -> bool:
    """Seleciona o trecho do comentario (ou poe o cursor na referencia)."""
    if editor.editando_faixa() is not None:
        editor.sair_da_faixa()
    doc = editor.documento_corpo()
    t = pq.trecho(doc, ident)
    if t is None:
        return False
    inicio, fim = t
    # As ancoras de outros comentarios nas pontas ficam fora da selecao.
    marcas_ = {pos for pos, _m in pq.ancoras(doc)}
    while inicio < fim and inicio in marcas_:
        inicio += 1
    while fim > inicio and fim - 1 in marcas_:
        fim -= 1
    c = QTextCursor(doc)
    c.setPosition(inicio)
    if fim > inicio:
        c.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(c)
    return True


def ir(editor, proximo: bool) -> int | None:
    """Anterior ou proximo comentario a partir do cursor. Seleciona e devolve o id."""
    doc = editor.documento_corpo()
    ordem = ancorados(editor)
    if not ordem:
        return None
    p = pq.posicoes(doc)
    pos = editor.textCursor().selectionStart() if editor.editando_faixa() is None else 0
    atual = no_cursor(editor)
    chave = lambda i: p[i].get("inicio", p[i].get("referencia", 0))  # noqa: E731
    if proximo:
        candidatos = [i for i in ordem if chave(i) >= pos and i != atual]
        alvo = candidatos[0] if candidatos else None
    else:
        candidatos = [i for i in ordem if chave(i) < pos and i != atual]
        if atual is not None and atual in ordem:
            candidatos = [i for i in ordem[:ordem.index(atual)]]
        alvo = candidatos[-1] if candidatos else None
    if alvo is None:
        return None
    selecionar(editor, alvo)
    return alvo


# -- edicao ---------------------------------------------------------------------------------

def _formato_da_referencia(doc) -> QTextCharFormat:
    """O formato do caractere da marca de referencia: o estilo "CommentReference", se houver."""
    estilos = pq_estilos.catalogo(doc)
    if estilos.obter("CommentReference") is None:
        return QTextCharFormat()
    res = pq_estilos.Resolvedor(estilos)
    return pq_estilos.formato_de_caractere(res.caractere(None, "CommentReference"),
                                           "CommentReference")


def _garantir_estilos(doc) -> str | None:
    """Os estilos do comentario no catalogo, como o Word cria (so' se faltam: a referencia
    preservada de um arquivo continua sem definicao). Devolve o estilo do texto."""
    estilos = pq_estilos.catalogo(doc)
    faltam = [n for sid, n in (("CommentReference", "annotation reference"),
                               ("CommentText", "annotation text"))
              if estilos.obter(sid) is None and estilos.por_nome(n) is None]
    if faltam:
        novo = estilos.copia()
        for nome in faltam:
            novo.garantir(nome)
        pq_estilos.trocar_catalogo(doc, novo)
        estilos = novo
    texto = estilos.obter("CommentText") or estilos.por_nome("annotation text")
    return texto.id if texto is not None else None


def _com_estilo(conteudo: tuple, estilo: str | None) -> tuple:
    saida = []
    for p in conteudo:
        if isinstance(p, Paragrafo) and p.estilo is None and estilo is not None:
            p = replace(p, estilo=estilo)
        saida.append(p)
    return tuple(saida) or (Paragrafo(estilo=estilo),)


def _inserir(doc, pos: int, marca: MarcaComentario, formato: QTextCharFormat | None = None) -> None:
    c = QTextCursor(doc)
    c.setPosition(pos)
    marcas.inserir(c, marca, formato)


def novo(editor, conteudo: tuple, autor: str, iniciais: str) -> int | None:
    """Comentario novo sobre a selecao (sem selecao, sobre a palavra do cursor; sem palavra,
    no ponto). Um passo de desfazer. None se nao da' (cabecalho em edicao, limite)."""
    if editor.editando_faixa() is not None:
        return None
    doc = editor.documento_corpo()
    cat = pq.catalogo(doc)
    if len(cat.itens) >= MAXIMO:
        return None
    cursor = editor.textCursor()
    inicio, fim = cursor.selectionStart(), cursor.selectionEnd()
    if inicio == fim:
        palavra = QTextCursor(doc)
        palavra.setPosition(inicio)
        palavra.select(QTextCursor.SelectionType.WordUnderCursor)
        if palavra.hasSelection() and palavra.selectedText().strip():
            inicio, fim = palavra.selectionStart(), palavra.selectionEnd()
    ident = cat.proximo_id()
    c = QTextCursor(doc)
    c.beginEditBlock()
    try:
        estilo = _garantir_estilos(doc)
        _inserir(doc, fim, MarcaComentario("referencia", ident), _formato_da_referencia(doc))
        _inserir(doc, fim, MarcaComentario("fim", ident))
        _inserir(doc, inicio, MarcaComentario("inicio", ident))
        comentario = Comentario(id=ident, autor=autor, iniciais=iniciais, data=agora_local(),
                                paragrafos=_com_estilo(conteudo, estilo), data_utc=agora_utc())
        pq.trocar(doc, cat.itens + [comentario])
    finally:
        c.endEditBlock()
    _depois(editor)
    selecionar(editor, ident)
    return ident


def responder(editor, pai: int, conteudo: tuple, autor: str, iniciais: str) -> int | None:
    """Resposta ao comentario `pai` (a conversa fica com o comentario do topo, como no Word).
    As ancoras ficam junto das do pai. Um passo de desfazer."""
    doc = editor.documento_corpo()
    cat = pq.catalogo(doc)
    if cat.obter(pai) is None or len(cat.itens) >= MAXIMO:
        return None
    raiz = cat.raiz(pai)
    p = pq.posicoes(doc, True).get(raiz) or pq.posicoes(doc, True).get(pai)
    if not p or "referencia" not in p:
        return None
    ident = cat.proximo_id()
    c = QTextCursor(doc)
    c.beginEditBlock()
    try:
        estilo = _garantir_estilos(doc)
        depois_ref = p["referencia"] + 1
        _inserir(doc, depois_ref, MarcaComentario("referencia", ident), _formato_da_referencia(doc))
        if "inicio" in p and "fim" in p:
            _inserir(doc, depois_ref, MarcaComentario("fim", ident))
            _inserir(doc, p["inicio"] + 1, MarcaComentario("inicio", ident))
        comentario = Comentario(id=ident, autor=autor, iniciais=iniciais, data=agora_local(),
                                paragrafos=_com_estilo(conteudo, estilo), pai=raiz,
                                data_utc=agora_utc())
        pq.trocar(doc, cat.itens + [comentario])
    finally:
        c.endEditBlock()
    _depois(editor)
    return ident


def editar(editor, ident: int, conteudo: tuple) -> bool:
    """Troca o texto do comentario. Recusa (False) o que o editor nao regrava sem perda."""
    doc = editor.documento_corpo()
    cat = pq.catalogo(doc)
    atual = cat.obter(ident)
    if atual is None or motivo_somente_leitura(atual):
        return False
    estilo = next((p.estilo for p in atual.paragrafos if isinstance(p, Paragrafo) and p.estilo),
                  None)
    novo_c = replace(atual, paragrafos=_com_estilo(conteudo, estilo), original=None)
    if novo_c == atual:
        return False
    _trocar_itens(doc, [novo_c if c.id == ident else c for c in cat.itens])
    _depois(editor)
    return True


def resolver(editor, ident: int, valor: bool = True) -> bool:
    """Resolve (ou reabre) a conversa inteira do comentario. Um passo de desfazer."""
    doc = editor.documento_corpo()
    cat = pq.catalogo(doc)
    if cat.obter(ident) is None:
        return False
    conversa = set(cat.descendentes(cat.raiz(ident)))
    itens = [replace(c, resolvido=valor) if c.id in conversa and c.resolvido != valor else c
             for c in cat.itens]
    if itens == cat.itens:
        return False
    _trocar_itens(doc, itens)
    _depois(editor)
    return True


def excluir(editor, ident: int) -> bool:
    """Exclui o comentario e as respostas (as ancoras saem do texto). Um passo de desfazer."""
    doc = editor.documento_corpo()
    cat = pq.catalogo(doc)
    if cat.obter(ident) is None:
        return False
    _excluir_ids(doc, set(cat.descendentes(ident)))
    _depois(editor)
    return True


def excluir_todos(editor) -> int:
    doc = editor.documento_corpo()
    cat = pq.catalogo(doc)
    if not cat.itens:
        return 0
    n = len(cat.itens)
    _excluir_ids(doc, set(cat.ids()))
    _depois(editor)
    return n


def _trocar_itens(doc, itens: list) -> None:
    c = QTextCursor(doc)
    c.beginEditBlock()
    try:
        pq.trocar(doc, itens)
    finally:
        c.endEditBlock()


def _excluir_ids(doc, ids: set[int]) -> None:
    cat = pq.catalogo(doc)
    c = QTextCursor(doc)
    c.beginEditBlock()
    try:
        _tirar_ancoras(doc, ids)
        pq.trocar(doc, [x for x in cat.itens if x.id not in ids])
    finally:
        c.endEditBlock()


def _tirar_ancoras(doc, ids: set[int]) -> None:
    for pos, m in sorted(pq.ancoras(doc, True), key=lambda x: -x[0]):
        if m.id in ids:
            c = QTextCursor(doc)
            c.setPosition(pos)
            c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
            c.removeSelectedText()


def _depois(editor) -> None:
    if hasattr(editor, "_limpar_cache"):
        editor._limpar_cache()
    editor.viewport().update()
    sinal = getattr(editor, "comentariosAlterados", None)
    if sinal is not None:
        sinal.emit()


# -- apagar texto com ancoras -----------------------------------------------------------

def _texto_entre(doc, a: int, b: int) -> int:
    """Quantos caracteres que nao sao ancoras ha' entre as posicoes a e b."""
    if b <= a:
        return 0
    c = QTextCursor(doc)
    c.setPosition(a)
    c.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
    texto = c.selectedText()
    ancoras = sum(1 for pos, _m in pq.ancoras(doc, True) if a <= pos < b)
    return len(texto) - ancoras


def remover_selecao(cursor: QTextCursor) -> bool:
    """Apaga a selecao do cursor com a regra do Word para os comentarios (ver o topo).

    Devolve True se havia ancora na selecao (e o trabalho foi feito aqui, num passo so');
    False se nao havia, sem fazer nada (quem chama apaga do jeito de sempre)."""
    if not cursor.hasSelection():
        return False
    doc = cursor.document()
    if getattr(doc, "_comentarios_base", None) is None and not pq.catalogo(doc).itens:
        return False
    a, b = cursor.selectionStart(), cursor.selectionEnd()
    todas = pq.ancoras(doc, True)
    dentro = [(pos, m) for pos, m in todas if a <= pos < b]
    cat = pq.catalogo(doc)
    if not cat.itens:
        return False
    posicoes = pq.posicoes(doc, True)
    apagar: set[int] = set()
    for _pos, m in dentro:
        if m.tipo == "referencia":
            apagar.add(m.id)
    for ident, p in posicoes.items():
        if "inicio" in p and "fim" in p and p["inicio"] < p["fim"]:
            if a <= p["inicio"] and p["fim"] < b:
                apagar.add(ident)  # o trecho comentado inteiro, com as duas pontas
                continue
            total = _texto_entre(doc, p["inicio"] + 1, p["fim"])
            if total > 0 and total == _texto_entre(doc, max(a, p["inicio"] + 1), min(b, p["fim"])):
                apagar.add(ident)  # todo o texto comentado (as pontas ficam de fora)
    conversa: set[int] = set()
    for ident in apagar:
        if cat.obter(ident) is not None:
            conversa |= set(cat.descendentes(ident))
    apagar |= conversa
    if not dentro and not apagar:
        return False
    ficam = [m for _pos, m in dentro if m.id not in apagar]
    fins = [m for m in ficam if m.tipo == "fim" and not any(
        x.tipo == "inicio" and x.id == m.id for x in ficam)]
    pares = [m for m in ficam if m.tipo in ("inicio", "fim") and any(
        x.tipo != m.tipo and x.id == m.id and x.tipo in ("inicio", "fim") for x in ficam)]
    pares.sort(key=lambda m: (m.id, 0 if m.tipo == "inicio" else 1))
    inicios = [m for m in ficam if m.tipo == "inicio" and m not in pares]
    reinserir = fins + pares + inicios
    cursor.beginEditBlock()
    try:
        cursor.removeSelectedText()
        ponto = QTextCursor(doc)
        ponto.setPosition(cursor.position())
        if apagar:
            _tirar_ancoras(doc, apagar)
            pq.trocar(doc, [x for x in cat.itens if x.id not in apagar])
        destino = ponto.position()
        for m in reinserir:
            _inserir(doc, destino, m)
            destino += 1
        cursor.setPosition(destino)
    finally:
        cursor.endEditBlock()
    return True
