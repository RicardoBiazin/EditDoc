"""Legendas (Referencias > Inserir Legenda): "Figura 1", "Tabela 1", "Equacao 1" com campo SEQ.

Inserir: o paragrafo da legenda (estilo "caption", criado se faltar) entra acima ou abaixo da
tabela do cursor ou do paragrafo do cursor (a imagem, a equacao). O numero e' o resultado de um
campo `SEQ Figura \\* ARABIC`. Depois de inserir, os campos SEQ do mesmo rotulo sao recontados
na ordem do documento (como o Word faz ao inserir), tudo num passo de desfazer.

Atualizar (`renumerar`, e "Atualizar campos" em `edicao/referencias.py`): os campos SEQ sao
recontados na ordem do documento (`modelo/legendas.numerar`) e so' o resultado que difere do
contado e' reescrito. Apagar ou mover uma legenda nao muda os outros numeros sozinho, como no
Word: o usuario manda atualizar. Campo SEQ que o EditDoc nao entende (opcao desconhecida, SEQ
que cita marcador) fica como veio. Um arquivo sem legendas nao muda ao salvar.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QTextCursor

from editdoc.edicao import sumario as ed_sumario
from editdoc.modelo import legendas as mod
from editdoc.modelo.documento import CARACTERE_OBJETO
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import secoes as pq_secoes
from editdoc.ponte_qt.para_qt import PROP_ESTRUTURAL

POSICOES = ("acima", "abaixo")


def _recado(editor, texto: str) -> None:
    ed_sumario._recado(editor, texto)


# -- leitura ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Legenda:
    """Um campo SEQ do documento: onde esta', o rotulo, o numero que mostra e o texto do paragrafo."""
    inicio: int
    fim: int
    rotulo: str
    numero: str
    bloco: int
    texto: str


def _seqs(doc) -> list[tuple[int, int, object]]:
    """(inicio, fim, Seq ou None) de cada campo SEQ do documento, na ordem do texto. None: o
    EditDoc nao entende a instrucao (o campo e' preservado)."""
    return [(ini, fim, mod.ler_seq(campo.instrucao()))
            for ini, fim, campo in ed_sumario.campos(doc) if campo.tipo() == "SEQ"]


def legendas(doc, rotulo: str | None = None) -> list[Legenda]:
    """Os campos SEQ que o EditDoc entende (de um rotulo, se dado), na ordem do texto, com o
    numero que mostram agora e o texto do paragrafo."""
    plano = doc.toPlainText()
    saida = []
    for ini, fim, seq in _seqs(doc):
        if seq is None or (rotulo is not None and seq.rotulo.lower() != rotulo.lower()):
            continue
        bloco = doc.findBlock(ini)
        saida.append(Legenda(ini, fim, seq.rotulo, plano[ini + 1:fim].replace("￼", ""),
                             bloco.blockNumber(), _texto_do_bloco(bloco)))
    return saida


def _texto_do_bloco(bloco) -> str:
    return " ".join(bloco.text().replace("￼", "").replace(" ", " ").split())


def rotulos_do_documento(doc) -> list[str]:
    """Os rotulos pedidos pelo dialogo: os tres do Word e os que ja' tem campo SEQ no
    documento (na ordem em que aparecem)."""
    saida = list(mod.ROTULOS)
    for ini, fim, seq in _seqs(doc):
        if seq is not None and seq.rotulo.lower() not in (r.lower() for r in saida):
            saida.append(seq.rotulo)
    return saida


def proximos(doc) -> dict[str, int]:
    """rotulo (minusculas) -> o numero que a proxima legenda tera' (so' para mostrar no dialogo:
    uma a mais que as que o documento tem)."""
    saida: dict[str, int] = {}
    for leg in legendas(doc):
        saida[leg.rotulo.lower()] = saida.get(leg.rotulo.lower(), 0) + 1
    return {k: v + 1 for k, v in saida.items()}


# -- contagem -----------------------------------------------------------------------------------

def _eventos(doc, seqs: list) -> list:
    """("seq", Seq) e, para o \\s, ("titulo", nivel) na ordem do texto."""
    eventos = []
    if any(s is not None and s.nivel_titulo is not None for _i, _f, s in seqs):
        titulos = []
        bloco = doc.begin()
        while bloco.isValid():
            nivel = pq_estilos.nivel_do_bloco(bloco)
            if nivel is not None:
                titulos.append((bloco.position(), nivel + 1))
            bloco = bloco.next()
        eventos = [(pos, 0, "titulo", nivel) for pos, nivel in titulos]
    eventos += [(ini, 1, "seq", seq) for ini, _f, seq in seqs]
    eventos.sort(key=lambda e: (e[0], e[1]))
    return [(tipo, dado) for _p, _o, tipo, dado in eventos]


def contar(doc) -> list[tuple[int, int, str]]:
    """(inicio, fim, numero certo) de cada campo SEQ que o EditDoc recalcula e que hoje mostra
    outro numero."""
    seqs = _seqs(doc)
    if not seqs:
        return []
    certos = mod.numerar(_eventos(doc, seqs))
    plano = doc.toPlainText()
    trocas = []
    entendidos = [(ini, fim) for ini, fim, seq in seqs if seq is not None]
    resultados = [r for r in certos if r is not None]
    for (ini, fim), certo in zip(entendidos, resultados):
        if plano[ini + 1:fim] != certo:
            trocas.append((ini, fim, certo))
    return trocas


def renumerar_no_bloco(doc) -> int:
    """Recontagem dentro do bloco de edicao aberto do chamador. Devolve quantos numeros mudaram."""
    trocas = contar(doc)
    if trocas:
        ed_sumario.trocar_resultados(doc, trocas)
    return len(trocas)


def renumerar(editor) -> int:
    """Atualiza os numeros de todos os campos SEQ do corpo, num passo de desfazer. Devolve
    quantos mudaram (-1 se fora do corpo)."""
    if not ed_sumario._no_corpo(editor):
        _recado(editor, "Volte ao texto do documento para atualizar as legendas.")
        return -1
    doc = editor.documento_corpo()
    if not contar(doc):
        _recado(editor, "As legendas já estavam numeradas na ordem do documento.")
        return 0
    c = QTextCursor(doc)
    c.beginEditBlock()
    n = renumerar_no_bloco(doc)
    c.endEditBlock()
    ed_sumario._depois(editor)
    _recado(editor, f"Legendas atualizadas: {n} {'número' if n == 1 else 'números'}.")
    return n


# -- onde a legenda entra -------------------------------------------------------------------------

def _vazio_comum(bloco) -> bool:
    """Bloco sem texto e sem objeto, que nao e' o bloco que o Qt exige antes ou depois da tabela
    e que o modelo nao tem."""
    return bloco.text() == "" and not bloco.blockFormat().property(PROP_ESTRUTURAL)


def _estrutural(bloco) -> bool:
    return bloco.text() == "" and bool(bloco.blockFormat().property(PROP_ESTRUTURAL))


def _alvo(editor, posicao: str):
    """(contexto, motivo): `contexto` = ("tabela", tabela) ou ("paragrafo", bloco do cursor);
    sem contexto, o motivo para a barra de status."""
    cursor = editor.textCursor()
    doc = editor.documento_corpo()
    tabela = cursor.currentTable()
    if tabela is not None:
        if tabela.parentFrame().firstPosition() != doc.rootFrame().firstPosition():
            return None, "A legenda de uma tabela dentro de outra tabela não é suportada."
        return ("tabela", tabela), ""
    if posicao == "abaixo":
        fim = cursor.selectionEnd()
        bloco = doc.findBlock(fim)
        if cursor.hasSelection() and fim == bloco.position() and bloco.blockNumber() > 0:
            bloco = bloco.previous()
    else:
        bloco = doc.findBlock(cursor.selectionStart())
    if pq_secoes.posicao_da_quebra_no_bloco(bloco) is not None:
        return None, "O parágrafo termina uma seção: ponha a legenda no parágrafo de dentro dela."
    return ("paragrafo", bloco), ""


def inserir(editor, rotulo: str = "Figura", posicao: str = "abaixo", texto: str = "",
            com_rotulo: bool = True) -> bool:
    """Insere a legenda acima ou abaixo da tabela do cursor ou do paragrafo do cursor. Um passo
    de desfazer. False (com o motivo) se nao pode."""
    if not ed_sumario._no_corpo(editor):
        _recado(editor, "A legenda só pode ser inserida no texto do documento (não no cabeçalho, "
                        "no rodapé nem numa nota).")
        return False
    rotulo = mod.rotulo_valido(rotulo)
    if not rotulo:
        _recado(editor, "Escreva o rótulo da legenda (por exemplo, Figura).")
        return False
    if posicao not in POSICOES:
        posicao = "abaixo"
    contexto, motivo = _alvo(editor, posicao)
    if contexto is None:
        _recado(editor, motivo)
        return False
    doc = editor.documento_corpo()
    c = QTextCursor(doc)
    c.beginEditBlock()
    garantido = ed_sumario.garantir_nomes(doc, [mod.ESTILO_LEGENDA])
    res = pq_estilos.Resolvedor(pq_estilos.catalogo(doc))
    paragrafo = mod.paragrafo_da_legenda(rotulo, "1", texto, garantido[mod.ESTILO_LEGENDA],
                                         com_rotulo)
    tipo, alvo = contexto
    if tipo == "tabela":
        if posicao == "acima":
            vizinho = doc.findBlock(alvo.firstPosition() - 1)
            _preparar_bloco_novo(c, vizinho, fim=True, aproveitar=_estrutural(vizinho))
        else:
            vizinho = doc.findBlock(alvo.lastPosition() + 1)
            # O bloco vazio que fecha o documento depois da ultima tabela e' do Qt (o modelo termina
            # na tabela): a legenda o ocupa, como ocupa o estrutural.
            ultimo_vazio = vizinho.text() == "" and not vizinho.next().isValid()
            _preparar_bloco_novo(c, vizinho, fim=False,
                                 aproveitar=_estrutural(vizinho) or ultimo_vazio)
    else:
        if posicao == "acima":
            _preparar_bloco_novo(c, alvo, fim=False, aproveitar=_vazio_comum(alvo))
        else:
            _preparar_bloco_novo(c, alvo, fim=True, aproveitar=_vazio_comum(alvo))
    ed_sumario._escrever(c, [paragrafo], res)
    renumerar_no_bloco(doc)
    c.endEditBlock()
    final = QTextCursor(doc)
    final.setPosition(c.position())
    final.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    editor.setTextCursor(final)
    ed_sumario._depois(editor)
    n = _numero_do_bloco(doc, final.block())
    _recado(editor, f"Legenda inserida: {rotulo} {n}." if com_rotulo and n else "Legenda inserida.")
    return True


def _numero_do_bloco(doc, bloco) -> str:
    for leg in legendas(doc):
        if leg.bloco == bloco.blockNumber():
            return leg.numero
    return ""


def _preparar_bloco_novo(c: QTextCursor, bloco, fim: bool, aproveitar: bool) -> None:
    """Deixa `c` num bloco vazio pronto para receber a legenda: o proprio `bloco` (se vazio, ou o
    bloco estrutural do Qt ao lado da tabela) ou um bloco novo antes (`fim` falso) ou depois
    (`fim` verdadeiro) dele."""
    if aproveitar:
        c.setPosition(bloco.position())
        return
    if fim:
        c.setPosition(bloco.position() + bloco.length() - 1)
        c.insertBlock()
    else:
        pos = bloco.position()
        c.setPosition(pos)
        c.insertBlock()
        c.setPosition(pos)
