"""Referencia cruzada (Referencias > Referencia cruzada) e "Atualizar campos".

Referencia cruzada: um campo `REF _Ref123456789 \\h` (o texto do marcador, o numero da legenda ou o
numero de lista do titulo) ou `PAGEREF _Ref123456789 \\h` (a pagina dele) no cursor. O alvo e' um
titulo, uma legenda (campo SEQ) ou um marcador do documento. Titulo e legenda ganham um marcador
oculto `_Ref` + 9 digitos no trecho que a referencia cita (o que ja' existe com o mesmo trecho e'
reaproveitado, como o Word). Um passo de desfazer; o numero da pagina e' corrigido depois do layout.

"Atualizar campos": recalcula os campos SEQ (contando na ordem do documento), os REF (o texto do
marcador, de agora) e os PAGEREF (a pagina do marcador, no layout de agora, com o formato e o
recomeco da secao, como o PAGE). Campo com opcao que o EditDoc nao entende fica como veio. Os
sumarios e indices nao sao refeitos (so' os numeros de pagina deles): para isso, "Atualizar
Sumario". Nada disso roda sozinho.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

from PySide6.QtGui import QTextCursor

from editdoc.edicao import legendas as ed_leg
from editdoc.edicao import sumario as ed_sumario
from editdoc.modelo import legendas as mod
from editdoc.modelo import sumario as mod_sum
from editdoc.modelo.documento import MarcaCampo, Marcador
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import marcas as pq_marcas
from editdoc.ponte_qt import secoes as pq_secoes

TIPO_TITULO = "titulo"
TIPO_MARCADOR = "marcador"
#: O que a referencia mostra.
TEXTO, PAGINA, NUMERO = "texto", "pagina", "numero"
LEGENDA_INTEIRA, ROTULO_E_NUMERO, SOMENTE_NUMERO = "inteira", "rotulo_numero", "somente_numero"
#: Mais itens do que isso na lista do dialogo: o resto fica de fora.
ITENS_MAXIMOS = 2000
_TEXTO_DO_ITEM = 90


def _recado(editor, texto: str) -> None:
    ed_sumario._recado(editor, texto)


@dataclass(frozen=True)
class Alvo:
    """Um item que a referencia pode citar."""
    tipo: str  # TIPO_TITULO, TIPO_MARCADOR ou o rotulo de uma legenda ("Figura")
    descricao: str
    bloco: int  # numero do bloco (titulo e legenda)
    nome: str = ""  # marcador existente (TIPO_MARCADOR)
    seq: tuple = ()  # (inicio, fim) do campo SEQ (legenda)


def _curto(texto: str) -> str:
    return texto if len(texto) <= _TEXTO_DO_ITEM else texto[:_TEXTO_DO_ITEM - 1] + "…"


def _texto_do_titulo(bloco) -> str:
    return mod_sum.texto_do_titulo(bloco.text())


def marcadores_visiveis(doc) -> list[str]:
    """Os marcadores do usuario (sem os ocultos, que comecam com sublinhado), na ordem do texto."""
    return [n for n in pq_marcas.nomes_de_marcadores(doc) if not n.startswith("_")]


def tipos(doc) -> list[tuple[str, str]]:
    """(chave, texto) dos tipos de referencia que o documento tem: Titulo, cada rotulo de
    legenda com pelo menos uma legenda, e Marcador."""
    saida = []
    bloco = doc.begin()
    while bloco.isValid():
        if pq_estilos.nivel_do_bloco(bloco) is not None and _texto_do_titulo(bloco):
            saida.append((TIPO_TITULO, "Título"))
            break
        bloco = bloco.next()
    vistos: list[str] = []
    for leg in ed_leg.legendas(doc):
        if leg.rotulo.lower() not in (v.lower() for v in vistos):
            vistos.append(leg.rotulo)
    saida += [(r, r) for r in vistos]
    if marcadores_visiveis(doc):
        saida.append((TIPO_MARCADOR, "Marcador"))
    return saida


def alvos(doc, tipo: str) -> list[Alvo]:
    """Os itens do tipo, na ordem do documento."""
    saida: list[Alvo] = []
    if tipo == TIPO_TITULO:
        bloco = doc.begin()
        while bloco.isValid() and len(saida) < ITENS_MAXIMOS:
            texto = _texto_do_titulo(bloco)
            if pq_estilos.nivel_do_bloco(bloco) is not None and texto:
                numero = ed_sumario.numero_da_lista(doc, bloco.blockNumber())
                saida.append(Alvo(TIPO_TITULO, _curto(f"{numero} {texto}".strip()),
                                  bloco.blockNumber()))
            bloco = bloco.next()
    elif tipo == TIPO_MARCADOR:
        intervalos = ed_sumario.intervalos_de_marcadores(doc)
        for nome in marcadores_visiveis(doc)[:ITENS_MAXIMOS]:
            achado = intervalos.get(nome)
            bloco = doc.findBlock(achado[0]).blockNumber() if achado else 0
            saida.append(Alvo(TIPO_MARCADOR, nome, bloco, nome=nome))
    else:
        for leg in ed_leg.legendas(doc, tipo)[:ITENS_MAXIMOS]:
            saida.append(Alvo(tipo, _curto(leg.texto) or f"{leg.rotulo} {leg.numero}",
                              leg.bloco, seq=(leg.inicio, leg.fim)))
    return saida


def opcoes_de(tipo: str) -> list[tuple[str, str]]:
    """(chave, texto) do que a referencia pode mostrar para o tipo."""
    if tipo == TIPO_TITULO:
        return [(TEXTO, "Texto do título"), (PAGINA, "Número da página"),
                (NUMERO, "Número do título")]
    if tipo == TIPO_MARCADOR:
        return [(TEXTO, "Texto do marcador"), (PAGINA, "Número da página")]
    return [(ROTULO_E_NUMERO, "Somente rótulo e número"), (SOMENTE_NUMERO, "Somente o número"),
            (LEGENDA_INTEIRA, "Legenda inteira"), (PAGINA, "Número da página")]


# -- marcadores _Ref ------------------------------------------------------------------------------

def _fim_do_texto(bloco) -> int:
    """A posicao onde o texto do bloco acaba (antes da quebra de secao, se houver)."""
    fim = bloco.position() + bloco.length() - 1
    quebra = pq_secoes.posicao_da_quebra_no_bloco(bloco)
    return min(fim, quebra) if quebra is not None else fim


def _trecho_do_alvo(doc, alvo: Alvo, o_que: str) -> tuple[int, int] | None:
    """[a, b): onde o marcador comeca (antes do primeiro caractere citado) e termina (depois do
    ultimo). None se o alvo sumiu."""
    bloco = doc.findBlockByNumber(alvo.bloco)
    if not bloco.isValid():
        return None
    if alvo.tipo == TIPO_TITULO or (alvo.seq and o_que == LEGENDA_INTEIRA):
        return bloco.position(), _fim_do_texto(bloco)
    if alvo.seq:
        ini, fim = alvo.seq
        if o_que == SOMENTE_NUMERO:
            return ini, fim + 1
        return bloco.position(), fim + 1  # rotulo e numero (e a pagina, que cita o mesmo trecho)
    return None


def _normal(posicoes: set, a: int, b: int) -> tuple[int, int]:
    """O trecho sem as marcas de marcador das pontas (elas nao mudam o que o marcador cita)."""
    while a in posicoes:
        a += 1
    while b - 1 in posicoes and b - 1 > a:
        b -= 1
    return a, b


def _marcador_do_trecho(doc, a: int, b: int, usados: set) -> tuple[str, bool]:
    """(nome, novo): o marcador `_Ref` que ja' cita o trecho [a, b) ou um nome novo."""
    posicoes = {p for p, _m in pq_marcas.posicoes_de_marcadores(doc)}
    alvo = _normal(posicoes, a, b)
    for nome, (ini, fim) in ed_sumario.intervalos_de_marcadores(doc).items():
        if nome.startswith(mod.PREFIXO_REFERENCIA) and _normal(posicoes, ini, fim + 1) == alvo:
            return nome, False
    nome = mod_sum.nome_de_marcador(usados, zlib.crc32(f"{a}:{b}".encode()),
                                    mod.PREFIXO_REFERENCIA)
    return nome, True


def _inserir_marcador(doc, nome: str, a: int, b: int, res) -> None:
    bloco = doc.findBlock(a)
    sid = pq_estilos.estilo_do_bloco(bloco.blockFormat())
    base = pq_estilos.formato_de_caractere(res.caractere(sid, None))
    c = QTextCursor(doc)
    c.setPosition(b)
    pq_marcas.inserir(c, Marcador("fim", nome), base)
    c.setPosition(a)
    pq_marcas.inserir(c, Marcador("inicio", nome), base)


# -- o resultado de cada referencia ---------------------------------------------------------------

def _texto_do_trecho(doc, ini: int, fim: int) -> str:
    """O texto entre as marcas do marcador (ini e fim sao as posicoes das marcas), sem marcas de
    objeto, em uma linha."""
    c = QTextCursor(doc)
    c.setPosition(ini + 1)
    c.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
    texto = c.selectedText().replace("￼", "").replace(" ", " ").replace(" ", " ")
    return " ".join(texto.split())[:mod_sum.TEXTO_MAXIMO]


def _resultado(editor, doc, ref: mod.Ref, intervalos: dict) -> str:
    achado = intervalos.get(ref.marcador)
    if achado is None:
        return mod.SEM_MARCADOR
    ini, fim = achado
    if ref.tipo == "PAGEREF":
        return ed_sumario.pagina_de(editor, ini + 1)
    if ref.numero:
        bloco = doc.findBlock(ini)
        return mod.numero_sem_ponto(ed_sumario.numero_da_lista(doc, bloco.blockNumber())) or "0"
    return _texto_do_trecho(doc, ini, fim)


def _referencias(doc) -> list[tuple[int, int, mod.Ref]]:
    """(inicio, fim, Ref) dos campos REF e PAGEREF que o EditDoc recalcula."""
    saida = []
    for ini, fim, campo in ed_sumario.campos(doc):
        if campo.tipo() in ("REF", "PAGEREF"):
            ref = mod.ler_ref(campo.instrucao())
            if ref is not None:
                saida.append((ini, fim, ref))
    return saida


# -- inserir --------------------------------------------------------------------------------------

def inserir(editor, alvo: Alvo, o_que: str, hiperlink: bool = True) -> bool:
    """Insere a referencia cruzada no cursor. Um passo de desfazer."""
    if not ed_sumario._no_corpo(editor):
        _recado(editor, "A referência cruzada só pode ser inserida no texto do documento (não no "
                        "cabeçalho, no rodapé nem numa nota).")
        return False
    doc = editor.documento_corpo()
    if o_que not in dict(opcoes_de(alvo.tipo)):
        _recado(editor, "Escolha o que a referência vai mostrar.")
        return False
    trecho = None
    if alvo.tipo == TIPO_MARCADOR:
        if alvo.nome not in ed_sumario.intervalos_de_marcadores(doc):
            _recado(editor, "O marcador escolhido não existe mais.")
            return False
    else:
        trecho = _trecho_do_alvo(doc, alvo, o_que)
        if trecho is None:
            _recado(editor, "O item escolhido não existe mais.")
            return False
    posicao = editor.textCursor().selectionEnd()
    c = QTextCursor(doc)
    c.setPosition(posicao)  # acompanha as marcas do marcador novo, inseridas antes dele
    c.beginEditBlock()
    res = pq_estilos.Resolvedor(pq_estilos.catalogo(doc))
    if trecho is None:
        nome = alvo.nome
    else:
        usados = set(ed_sumario._marcadores(doc))
        nome, novo = _marcador_do_trecho(doc, *trecho, usados)
        if novo:
            _inserir_marcador(doc, nome, *trecho, res)
    tipo_do_campo = "PAGEREF" if o_que == PAGINA else "REF"
    ref = mod.Ref(tipo_do_campo, nome, o_que == NUMERO, hiperlink)
    resultado = _resultado(editor, doc, ref, ed_sumario.intervalos_de_marcadores(doc))
    vizinho = ed_sumario.formato_limpo(c.charFormat())
    campo = mod.campo_ref(nome, tipo_do_campo, o_que == NUMERO, hiperlink)
    pq_marcas.inserir(c, MarcaCampo("inicio", campo), vizinho)
    inicio = c.position() - 1
    c.insertText(resultado, vizinho)
    pq_marcas.inserir(c, MarcaCampo("fim"), vizinho)
    c.endEditBlock()
    if tipo_do_campo == "PAGEREF":
        ed_sumario._corrigir_numeros(editor, None, juntar=True, apenas=inicio)
    final = QTextCursor(doc)
    final.setPosition(c.position())
    editor.setTextCursor(final)
    ed_sumario._depois(editor)
    _recado(editor, "Referência cruzada inserida.")
    return True


# -- atualizar campos -----------------------------------------------------------------------------

def atualizar_campos(editor) -> bool:
    """Atualiza SEQ, REF e PAGEREF do corpo. Um passo de desfazer (os PAGEREF, que dependem do
    layout, entram num passo anotado junto com ele)."""
    if not ed_sumario._no_corpo(editor):
        _recado(editor, "Volte ao texto do documento para atualizar os campos.")
        return False
    doc = editor.documento_corpo()
    ed_sumario._preparar(editor)
    c = QTextCursor(doc)
    c.beginEditBlock()
    n_seq = ed_leg.renumerar_no_bloco(doc)
    intervalos = ed_sumario.intervalos_de_marcadores(doc)
    plano = doc.toPlainText()
    trocas = []
    for ini, fim, ref in _referencias(doc):
        if ref.tipo != "REF":
            continue
        novo = _resultado(editor, doc, ref, intervalos)
        if plano[ini + 1:fim].replace("￼", "") != novo:
            trocas.append((ini, fim, novo))
    if trocas:
        ed_sumario.trocar_resultados(doc, trocas)
    c.endEditBlock()
    mudou_paginas = ed_sumario._corrigir_numeros(editor, None, juntar=bool(n_seq or trocas),
                                                 todos=True)
    ed_sumario._depois(editor)
    n_ref = len(trocas)
    if not (n_seq or n_ref or mudou_paginas):
        _recado(editor, "Os campos já estavam atualizados.")
        return True
    partes = []
    if n_seq:
        partes.append(f"{n_seq} {'número de legenda' if n_seq == 1 else 'números de legenda'}")
    if n_ref:
        partes.append(f"{n_ref} {'referência' if n_ref == 1 else 'referências'}")
    if mudou_paginas:
        partes.append("números de página")
    _recado(editor, "Campos atualizados: " + ", ".join(partes) + ".")
    return True
