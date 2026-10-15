"""Controle de alteracoes (0.1.13): rastrear a edicao, listar, aceitar e rejeitar, navegar.

Regras do Word que valem aqui:

- com o controle ligado, digitar (e colar) cria insercao com o autor das Opcoes e a data; o Enter
  cria a marca de paragrafo inserida (a do paragrafo de cima: o de baixo fica com a marca de
  antes); apagar texto de outro autor (ou texto comum) vira exclusao, e o texto continua la',
  tachado; apagar texto inserido pelo mesmo autor e ainda nao aceito simplesmente o remove;
  formatar guarda a formatacao de antes (w:rPrChange / w:pPrChange), uma vez so' (a primeira
  formatacao de antes e' a que vale), e nao marca o texto inserido pelo proprio autor;
- com o controle desligado, o texto digitado nao herda a revisao do vizinho, e o Enter no meio de
  um paragrafo de marca inserida deixa a marca nova sem revisao;
- aceitar a insercao tira a marca; rejeitar remove o texto. Aceitar a exclusao remove o texto;
  rejeitar tira a marca. A marca de paragrafo: aceitar a excluida (ou rejeitar a inserida) junta
  o paragrafo ao seguinte. A formatacao: aceitar esquece a de antes; rejeitar a devolve. O
  movimento: as duas pontas juntas. Linha de tabela inserida/excluida: aceitar ou rejeitar
  remove a linha ou tira a marca. As revisoes de celula, de propriedades de tabela e de secao so'
  se aceitam (rejeitar exigiria refazer a grade; ficam, e a mensagem diz).

Tudo e' um passo de desfazer (um bloco de edicao no documento). O que muda o texto passa pelo
painel (`PainelDocumento._inserir`, `_apagar`, `_quebrar`, `paste`, `_remover_selecao`), que
chama daqui; a formatacao passa por `registrando_formatacao` (comandos da faixa e da fonte).
"""

from __future__ import annotations

import contextlib
import datetime
from dataclasses import dataclass, field

from PySide6.QtGui import (QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
                           QTextFormat, QTextTable)

from editdoc import log_interno
from editdoc.formato_docx import revisoes as fx_revisoes
from editdoc.modelo import revisoes as mod_revisoes
from editdoc.modelo.documento import MarcaMovimento, Revisao
from editdoc.ponte_qt import marcas as pq_marcas
from editdoc.ponte_qt import revisoes as pq
from editdoc.ponte_qt import secoes as pq_secoes
from editdoc.ponte_qt.links import formato_em

log = log_interno.obter(__name__)

M = QTextCursor.MoveOperation
Manter = QTextCursor.MoveMode.KeepAnchor
_SEPARADOR = " "
#: Caracteres de quadro (inicio e fim de celula/tabela): o controle nao os apaga.
_QUADRO = ("﷐", "﷑")
#: Revisoes que so' se aceitam (ver o topo).
SO_ACEITAR = ("celula", "tabela", "secao", "numeracao")


# -- estado ---------------------------------------------------------------------------------

def _corpo(editor) -> QTextDocument:
    corpo = getattr(editor, "documento_corpo", None)
    return corpo() if callable(corpo) else editor.document()


def controle_ligado(editor) -> bool:
    return bool(getattr(_corpo(editor), "_controlar_alteracoes", False))


def definir_controle(editor, ligado: bool) -> bool:
    """Revisao > Controlar alteracoes. Grava no settings.xml (o documento fica alterado, como no
    Word). True se mudou."""
    doc = _corpo(editor)
    if bool(getattr(doc, "_controlar_alteracoes", False)) == bool(ligado):
        return False
    doc._controlar_alteracoes = bool(ligado)
    doc.setModified(True)
    return True


def autor(editor) -> str:
    nome = getattr(editor, "autor_revisao", None)
    if callable(nome):
        nome = nome()
    return (nome or "").strip() or "Autor"


def agora() -> str:
    """A data da revisao como o Word grava (ISO 8601, segundos, Z)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")


def nova(editor, tipo: str) -> Revisao:
    return Revisao(tipo, autor(editor), agora())


def documentos(editor) -> list[QTextDocument]:
    """Os documentos da janela que tem texto revisavel ao vivo: o corpo e os cabecalhos e rodapes
    (as notas se revisam na edicao da nota: o documento editado e' o da nota)."""
    saida = [_corpo(editor)]
    layout = getattr(editor, "layout_pag", None)
    if layout is not None and getattr(layout, "faixas", None) is not None:
        saida += [f.doc for f in layout.faixas.todas()]
    atual = editor.document()
    if atual not in saida:
        saida.append(atual)
    return saida


# -- trechos do documento -------------------------------------------------------------------

def _fragmentos(doc: QTextDocument, a: int, b: int) -> list[tuple[int, int, QTextCharFormat]]:
    """(inicio, fim, formato) dos pedacos de fragmento entre `a` e `b`, em ordem."""
    saida = []
    if b <= a:
        return saida
    bloco = doc.findBlock(a)
    while bloco.isValid() and bloco.position() < b:
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            it += 1
            if not frag.isValid():
                continue
            x, y = frag.position(), frag.position() + frag.length()
            if y <= a or x >= b:
                continue
            saida.append((max(x, a), min(y, b), QTextCharFormat(frag.charFormat())))
        bloco = bloco.next()
    return saida


def _juntar_propriedade(doc: QTextDocument, a: int, b: int, prop: int, valor) -> None:
    """Acrescenta a propriedade ao trecho (merge: nao mexe no resto do formato, nem no objeto)."""
    if b <= a:
        return
    c = QTextCursor(doc)
    c.setPosition(a)
    c.setPosition(b, Manter)
    fmt = QTextCharFormat()
    fmt.setProperty(prop, valor)
    c.mergeCharFormat(fmt)


def _trocar_formato(doc: QTextDocument, a: int, b: int, cf: QTextCharFormat) -> None:
    c = QTextCursor(doc)
    c.setPosition(a)
    c.setPosition(b, Manter)
    c.setCharFormat(cf)


def _remover(doc: QTextDocument, a: int, b: int) -> None:
    c = QTextCursor(doc)
    c.setPosition(a)
    c.setPosition(b, Manter)
    c.removeSelectedText()


def _eh_marca_sem_largura(cf: QTextFormat) -> bool:
    return pq_marcas.eh_marcador(cf)


def _bloco_formato(doc: QTextDocument, bloco, bf: QTextBlockFormat) -> None:
    c = QTextCursor(doc)
    c.setPosition(bloco.position())
    c.setBlockFormat(bf)


# -- edicao com o controle ligado (ou desligado) ---------------------------------------------

def formato_para_digitar(editor, cf: QTextCharFormat) -> QTextCharFormat | None:
    """O formato do texto que vai ser digitado (ou colado em texto puro). None = o de sempre
    (sem revisao no formato e o controle desligado: o caminho rapido da digitacao)."""
    ligado = controle_ligado(editor)
    if not ligado and not pq.tem_revisao(cf):
        return None
    novo = pq.sem_revisao(QTextCharFormat(cf))
    if novo is cf:
        novo = QTextCharFormat(cf)
    if ligado:
        atual = pq.insercao_de(cf)
        if atual is None or atual.tipo != "ins" or atual.autor != autor(editor) or \
                pq.exclusao_de(cf) is not None:
            atual = nova(editor, "ins")
        novo.setProperty(pq.PROP_REV_INS, pq.json_de(atual))
        pq.marcar_revisado(editor.document())
    return novo


def apagar_intervalo(editor, doc: QTextDocument, a: int, b: int) -> None:
    """Apaga [a, b) com o controle ligado (ver o topo). Quem chama abre o bloco de edicao."""
    eu = autor(editor)
    rev = nova(editor, "del")
    texto_rev = pq.json_de(rev)
    operacoes: list[tuple] = []
    for x, y, cf in _fragmentos(doc, a, b):
        operacoes.append((x, y, "texto", cf))
    bloco = doc.findBlock(a)
    while bloco.isValid() and bloco.position() < b:
        fim = bloco.position() + bloco.length() - 1
        if a <= fim < b and bloco.next().isValid() and doc.characterAt(fim) == _SEPARADOR:
            operacoes.append((fim, fim + 1, "marca", bloco))
        bloco = bloco.next()
    operacoes.sort(key=lambda o: (o[0], o[2] == "texto"), reverse=True)
    marcou = False
    for x, y, tipo, coisa in operacoes:
        if tipo == "marca":
            m_ins, m_exc = pq.marca_de(coisa.blockFormat())
            if m_exc is not None:
                continue
            if m_ins is not None and m_ins.tipo == "ins" and m_ins.autor == eu:
                _remover(doc, x, y)  # a marca que o proprio autor inseriu: some
                continue
            bf = QTextBlockFormat(coisa.blockFormat())
            pq.definir_marca(bf, m_ins, rev)
            _bloco_formato(doc, coisa, bf)
            marcou = True
            continue
        cf = coisa
        if _eh_marca_sem_largura(cf) or pq_secoes.eh_quebra(cf):
            continue  # marcador, ancora, movimento e quebra de secao ficam
        if any(doc.characterAt(i) in _QUADRO for i in (x,)):
            continue
        ins, exc = pq.insercao_de(cf), pq.exclusao_de(cf)
        if exc is not None:
            continue
        if ins is not None and ins.tipo == "ins" and ins.autor == eu:
            _remover(doc, x, y)
        else:
            _juntar_propriedade(doc, x, y, pq.PROP_REV_DEL, texto_rev)
            marcou = True
    if marcou:
        pq.marcar_revisado(doc)


def apagar_selecao(editor, cursor: QTextCursor) -> None:
    """A selecao apagada com o controle ligado: um passo de desfazer; o cursor fica no comeco."""
    doc = cursor.document()
    a, b = cursor.selectionStart(), cursor.selectionEnd()
    cursor.beginEditBlock()
    try:
        apagar_intervalo(editor, doc, a, b)
    finally:
        cursor.endEditBlock()
    cursor.setPosition(min(a, doc.characterCount() - 1))


def _pular(doc: QTextDocument, pos: int) -> bool:
    """O caractere em `pos` nao conta para o Backspace e o Delete: marca sem largura, ja'
    excluido, escondido no modo, ou a marca de paragrafo ja' excluida."""
    if doc.characterAt(pos) == _SEPARADOR:
        bloco = doc.findBlock(pos)
        return pq.marca_de(bloco.blockFormat())[1] is not None
    cf = formato_em(doc, pos)
    if cf is None:
        return False
    if _eh_marca_sem_largura(cf):
        return True
    if pq.tem_revisao(cf) and pq.exclusao_de(cf) is not None:
        return True
    return pq.oculto_em(doc, pos)


def apagar_caractere(editor, cursor: QTextCursor, anterior: bool) -> None:
    """Backspace (anterior) ou Delete com o controle ligado, sem selecao."""
    doc = cursor.document()
    ultimo = doc.characterCount() - 1
    pos = cursor.position()
    if anterior:
        p = pos - 1
        while p >= 0 and _pular(doc, p):
            p -= 1
        if p < 0:
            cursor.setPosition(0)
            return
    else:
        p = pos
        while p < ultimo and _pular(doc, p):
            p += 1
        if p >= ultimo:
            cursor.setPosition(ultimo)
            return
    if doc.characterAt(p) in _QUADRO:
        return
    antes = doc.characterCount()
    cursor.beginEditBlock()
    try:
        apagar_intervalo(editor, doc, p, p + 1)
    finally:
        cursor.endEditBlock()
    removido = doc.characterCount() < antes
    if anterior or removido:
        cursor.setPosition(min(p, doc.characterCount() - 1))
    else:
        cursor.setPosition(min(p + 1, doc.characterCount() - 1))


def marca_antes_do_enter(cursor: QTextCursor) -> tuple:
    return pq.marca_de(cursor.block().blockFormat())


def depois_do_enter(editor, cursor: QTextCursor, marca_original: tuple) -> None:
    """Depois do insertBlock (no mesmo bloco de edicao): a marca do paragrafo de cima e' a nova
    (inserida, com o controle ligado; sem revisao, desligado); o de baixo fica com a de antes."""
    doc = cursor.document()
    bloco = cursor.block()
    anterior = bloco.previous()
    if not anterior.isValid():
        return
    ligado = controle_ligado(editor)
    nova_ins = nova(editor, "ins") if ligado else None
    if pq.marca_de(anterior.blockFormat()) != (nova_ins, None):
        bf = QTextBlockFormat(anterior.blockFormat())
        pq.definir_marca(bf, nova_ins, None)
        _bloco_formato(doc, anterior, bf)
    if pq.marca_de(bloco.blockFormat()) != tuple(marca_original):
        bf = QTextBlockFormat(bloco.blockFormat())
        pq.definir_marca(bf, *marca_original)
        _bloco_formato(doc, bloco, bf)
    if ligado:
        pq.marcar_revisado(doc)


def marcar_colado(editor, doc: QTextDocument, a: int, b: int) -> None:
    """O que foi colado com o controle ligado: insercao do autor, e as marcas de paragrafo de
    dentro, inseridas (dentro do bloco de edicao do colar)."""
    if b <= a or not controle_ligado(editor):
        return
    rev = nova(editor, "ins")
    texto = pq.json_de(rev)
    for x, y, cf in reversed(_fragmentos(doc, a, b)):
        if _eh_marca_sem_largura(cf):
            continue
        if pq.tem_revisao(cf):
            limpo = pq.sem_revisao(cf)
            limpo.setProperty(pq.PROP_REV_INS, texto)
            _trocar_formato(doc, x, y, limpo)
        else:
            _juntar_propriedade(doc, x, y, pq.PROP_REV_INS, texto)
    bloco = doc.findBlock(a)
    while bloco.isValid() and bloco.position() < b:
        fim = bloco.position() + bloco.length() - 1
        if fim < b and bloco.next().isValid():
            bf = QTextBlockFormat(bloco.blockFormat())
            pq.definir_marca(bf, rev, None)
            _bloco_formato(doc, bloco, bf)
        bloco = bloco.next()
    pq.marcar_revisado(doc)


# -- formatacao com o controle ligado ----------------------------------------------------------

def _resolvedor(doc: QTextDocument):
    from editdoc.ponte_qt import estilos as pq_estilos
    from editdoc.ponte_qt import listas as pq_listas
    return pq_estilos.Resolvedor(pq_estilos.catalogo(doc), pq_listas.catalogo(doc))


def _assinatura_caractere(cf: QTextCharFormat) -> tuple:
    from editdoc.ponte_qt import estilos as pq_estilos
    from editdoc.ponte_qt import propriedades as pq_props
    return (tuple(sorted(pq_estilos.props_de_caractere(cf).items())),
            pq_estilos.estilo_do_caractere(cf), pq_props.extras_de_rpr(cf))


def _assinatura_bloco(bf: QTextBlockFormat) -> tuple:
    from editdoc.ponte_qt import estilos as pq_estilos
    from editdoc.ponte_qt import listas as pq_listas
    from editdoc.ponte_qt import propriedades as pq_props
    return (tuple(sorted(pq_estilos.props_de_bloco(bf).items())),
            pq_estilos.estilo_do_bloco(bf), pq_listas.lista_do_bloco(bf),
            pq_props.extras_de_ppr(bf))


@contextlib.contextmanager
def registrando_formatacao(editor):
    """Em volta de um comando de formatacao: com o controle ligado, guarda a formatacao de antes
    do trecho (w:rPrChange) e dos paragrafos (w:pPrChange) que mudaram. Um passo de desfazer.
    Aninhado ou com o controle desligado, nao faz nada."""
    if not controle_ligado(editor) or getattr(editor, "_registrando_formatacao", False):
        yield
        return
    doc = editor.document()
    c = editor.textCursor()
    a, b = c.selectionStart(), c.selectionEnd()
    primeiro = doc.findBlock(a)
    ultimo = doc.findBlock(b)
    blocos = []
    bloco = primeiro
    while bloco.isValid():
        blocos.append((bloco.position(), QTextBlockFormat(bloco.blockFormat())))
        if bloco == ultimo:
            break
        bloco = bloco.next()
    trechos = _fragmentos(doc, a, b) if b > a else []
    editor._registrando_formatacao = True
    envolto = QTextCursor(doc)
    envolto.beginEditBlock()
    try:
        yield
        _registrar(editor, doc, blocos, trechos)
    except Exception:  # noqa: BLE001 - o comando ja' rodou; so' a marca da revisao falhou
        log.exception("revisao de formatacao")
    finally:
        envolto.endEditBlock()
        editor._registrando_formatacao = False


def _registrar(editor, doc: QTextDocument, blocos: list, trechos: list) -> None:
    from editdoc.ponte_qt import de_qt
    eu = autor(editor)
    data = agora()
    res = None
    marcou = False
    for x, y, antigo in reversed(trechos):
        if _eh_marca_sem_largura(antigo) or antigo.isImageFormat():
            continue
        for xa, ya, atual in reversed(_fragmentos(doc, x, y)):
            if _assinatura_caractere(atual) == _assinatura_caractere(antigo):
                continue
            if pq.mudanca_de(atual) or pq.exclusao_de(atual) is not None:
                continue  # a primeira formatacao de antes e' a que vale; excluido nao se formata
            ins = pq.insercao_de(atual)
            if ins is not None and ins.tipo == "ins" and ins.autor == eu:
                continue  # texto que o proprio autor inseriu: a insercao ja' diz tudo
            if res is None:
                res = _resolvedor(doc)
            bloco = doc.findBlock(xa)
            from editdoc.ponte_qt import estilos as pq_estilos
            sid_par = pq_estilos.estilo_do_bloco(bloco.blockFormat())
            run = de_qt._run_direto("x", antigo, sid_par, res)
            estilo = run.estilo if run.estilo and res.estilos.obter(run.estilo) is not None else None
            xml = fx_revisoes.mudanca_de_run(run, estilo, eu, data)
            _juntar_propriedade(doc, xa, ya, pq.PROP_REV_RPR, xml)
            marcou = True
    for pos, antigo in blocos:
        bloco = doc.findBlock(pos)
        atual = bloco.blockFormat()
        if _assinatura_bloco(atual) == _assinatura_bloco(antigo):
            continue
        if pq.mudanca_de_bloco(atual)[0]:
            continue
        m_ins = pq.marca_de(atual)[0]
        if m_ins is not None and m_ins.tipo == "ins" and m_ins.autor == eu:
            continue  # paragrafo novo do proprio autor
        if res is None:
            res = _resolvedor(doc)
        em_celula = QTextCursor(bloco).currentTable() is not None
        p = de_qt.paragrafo_do_formato(antigo, res, em_celula)
        estilo = p.estilo if p.estilo and p.estilo != res.estilos.id_padrao() else None
        xml = fx_revisoes.mudanca_de_paragrafo(p, estilo, eu, data)
        bf = QTextBlockFormat(atual)
        pq.definir_mudanca_de_bloco(bf, xml, pq.mudanca_de_bloco(atual)[1])
        _bloco_formato(doc, bloco, bf)
        marcou = True
    if marcou:
        pq.marcar_revisado(doc)


# -- lista de revisoes -------------------------------------------------------------------------

@dataclass
class Item:
    """Uma revisao na tela: tipo (de `mod_revisoes.NOMES_DOS_TIPOS`), autor, data, o trecho
    [inicio, fim) no documento `doc` e o texto (o comeco)."""
    tipo: str
    autor: str
    data: str | None
    inicio: int
    fim: int
    texto: str = ""
    doc: object = field(default=None, repr=False, compare=False)
    #: o que identifica a revisao (o JSON da revisao, o XML da formatacao, a linha da tabela...)
    chave: object = None
    #: nome do movimento (as duas pontas se resolvem juntas)
    movimento: str | None = None

    def nome_do_tipo(self) -> str:
        return mod_revisoes.NOMES_DOS_TIPOS.get(self.tipo, self.tipo)


def _texto_do_trecho(doc: QTextDocument, a: int, b: int, limite: int = 60) -> str:
    c = QTextCursor(doc)
    c.setPosition(a)
    c.setPosition(min(b, a + limite + 1, doc.characterCount() - 1), Manter)
    texto = c.selectedText().replace(_SEPARADOR, " ").replace(" ", " ")
    texto = texto.replace("￼", "").replace("﷐", "").replace("﷑", "")
    return texto[:limite] + ("…" if len(texto) > limite else "")


def listar(doc: QTextDocument) -> list[Item]:
    """As revisoes do documento, na ordem. Em cache pela revisao do documento."""
    if not pq.tem_revisoes(doc):
        return []
    chave = (doc.revision(), doc.characterCount(), id(pq_secoes.registro(doc)),
             str(doc.rootFrame().frameFormat().property(pq_secoes.PROP_SECAO_FINAL)))
    cache = getattr(doc, "_lista_revisoes", None)
    if cache is not None and cache[0] == chave:
        return cache[1]
    itens: list[Item] = []
    abertos: dict = {}
    movimentos = _trechos_de_movimento(doc)
    bloco = doc.begin()
    while bloco.isValid():
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            it += 1
            if not frag.isValid():
                continue
            cf = frag.charFormat()
            x, y = frag.position(), frag.position() + frag.length()
            for lado, prop in (("i", pq.PROP_REV_INS), ("e", pq.PROP_REV_DEL),
                               ("f", pq.PROP_REV_RPR)):
                valor = cf.property(prop) if cf.hasProperty(prop) else None
                valor = valor if isinstance(valor, str) and valor else None
                anterior = abertos.get(lado)
                if valor is None:
                    abertos.pop(lado, None)
                    continue
                if anterior is not None and anterior.chave == valor and anterior.fim == x:
                    anterior.fim = y
                    continue
                if lado == "f":
                    item = Item("formato", _autor_do_xml(valor), _data_do_xml(valor), x, y,
                                doc=doc, chave=valor)
                else:
                    rev = pq._revisao(valor)
                    if rev is None:
                        continue
                    item = Item(rev.tipo, rev.autor, rev.data, x, y, doc=doc, chave=valor)
                    if rev.tipo in ("moveFrom", "moveTo"):
                        item.movimento = _movimento_em(movimentos, rev.tipo, x)
                itens.append(item)
                abertos[lado] = item
        bf = bloco.blockFormat()
        fim = bloco.position() + bloco.length() - 1
        m_ins, m_exc = pq.marca_de(bf)
        for rev, tipo in ((m_ins, "marca_ins"), (m_exc, "marca_del")):
            if rev is not None:
                itens.append(Item(tipo, rev.autor, rev.data, fim, fim + 1, doc=doc,
                                  chave=pq.json_de(rev)))
        ppr, num = pq.mudanca_de_bloco(bf)
        if ppr:
            itens.append(Item("paragrafo", _autor_do_xml(ppr), _data_do_xml(ppr),
                              bloco.position(), fim, doc=doc, chave=ppr))
        if num:
            itens.append(Item("numeracao", _autor_do_xml(num), _data_do_xml(num),
                              bloco.position(), fim, doc=doc, chave=num))
        bloco = bloco.next()
    itens += _itens_de_tabelas(doc)
    itens += _itens_de_secoes(doc)
    for item in itens:
        if not item.texto:
            item.texto = _texto_do_trecho(doc, item.inicio, item.fim)
    itens.sort(key=lambda i: (i.inicio, i.fim))
    doc._lista_revisoes = (chave, itens)
    return itens


def _autor_do_xml(texto: str) -> str:
    el = fx_revisoes.elemento_canonico(texto)
    if el is None:
        return ""
    from editdoc.formato_docx.nomes import q
    alvo = el if el.get(q("author")) is not None else next(
        (x for x in el.iter() if x.get(q("author")) is not None), el)
    return alvo.get(q("author")) or ""


def _data_do_xml(texto: str) -> str | None:
    el = fx_revisoes.elemento_canonico(texto)
    if el is None:
        return None
    from editdoc.formato_docx.nomes import q
    alvo = el if el.get(q("date")) is not None else next(
        (x for x in el.iter() if x.get(q("date")) is not None), el)
    return alvo.get(q("date"))


def _marcas_de_movimento(doc: QTextDocument) -> list[tuple[int, MarcaMovimento]]:
    saida = []
    bloco = doc.begin()
    while bloco.isValid():
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            it += 1
            if frag.isValid() and pq_marcas.eh_marcador(frag.charFormat()):
                m = pq_marcas.marca_de(frag.charFormat())
                if isinstance(m, MarcaMovimento):
                    saida.extend((frag.position() + i, m) for i, ch in enumerate(frag.text())
                                 if ch == "￼")
        bloco = bloco.next()
    return saida


def _trechos_de_movimento(doc: QTextDocument) -> list[tuple]:
    """(tipo "de"/"para", nome, inicio, fim, posicoes das duas marcas) de cada trecho."""
    abertos: dict[tuple, tuple] = {}
    saida = []
    for pos, m in _marcas_de_movimento(doc):
        chave = (m.tipo, m.par)
        if not m.fim:
            abertos[chave] = (pos, m)
        elif chave in abertos or any(k[0] == m.tipo for k in abertos):
            inicio = abertos.pop(chave, None)
            if inicio is None:
                k = next(k for k in abertos if k[0] == m.tipo)
                inicio = abertos.pop(k)
            saida.append((m.tipo, inicio[1].nome, inicio[0], pos, (inicio[0], pos)))
    return saida


def _movimento_em(trechos: list, tipo: str, pos: int) -> str | None:
    grupo = "de" if tipo == "moveFrom" else "para"
    for g, nome, a, b, _pos in trechos:
        if g == grupo and a <= pos <= b:
            return nome
    return None


def _tabelas(doc: QTextDocument) -> list[QTextTable]:
    saida = []

    def visitar(quadro):
        for filho in quadro.childFrames():
            if isinstance(filho, QTextTable):
                saida.append(filho)
            visitar(filho)
    visitar(doc.rootFrame())
    return saida


def _json_celula(cel):
    from editdoc.ponte_qt.para_qt import PROP_CELULA, ler_json
    return ler_json(cel.format(), PROP_CELULA)


def _itens_de_tabelas(doc: QTextDocument) -> list[Item]:
    from editdoc.ponte_qt.para_qt import PROP_TABELA, ler_json
    itens = []
    for tabela in _tabelas(doc):
        pos_tab = tabela.firstPosition()
        dado = ler_json(tabela.format(), PROP_TABELA)
        extras = dado.get("extras") if isinstance(dado.get("extras"), str) else None
        if fx_revisoes.tem_revisao(extras) or dado.get("mudanca_grade"):
            itens.append(Item("tabela", _autor_do_xml(extras or dado.get("mudanca_grade") or ""),
                              _data_do_xml(extras or dado.get("mudanca_grade") or ""),
                              pos_tab, pos_tab, "Propriedades da tabela", doc=doc,
                              chave=("tabela", pos_tab)))
        for r in range(tabela.rows()):
            cel = tabela.cellAt(r, 0)
            linha = _json_celula(cel).get("extras_linha")
            linha = linha if isinstance(linha, str) else None
            el = fx_revisoes.elemento_canonico(linha)
            if el is not None:
                from editdoc.formato_docx.nomes import q
                for nome, tipo in (("ins", "linha_ins"), ("del", "linha_del")):
                    marca = el.find(q(nome))
                    if marca is not None:
                        a = cel.firstCursorPosition().position()
                        ult = tabela.cellAt(r, tabela.columns() - 1)
                        b = ult.lastCursorPosition().position()
                        itens.append(Item(tipo, marca.get(q("author")) or "", marca.get(q("date")),
                                          a, b, doc=doc, chave=("linha", pos_tab, r)))
            for col in range(tabela.columns()):
                c = tabela.cellAt(r, col)
                if c.row() != r or c.column() != col:
                    continue
                extras_c = _json_celula(c).get("extras")
                if isinstance(extras_c, str) and fx_revisoes.tem_revisao(extras_c):
                    a = c.firstCursorPosition().position()
                    itens.append(Item("celula", _autor_do_xml(extras_c), _data_do_xml(extras_c),
                                      a, c.lastCursorPosition().position(), doc=doc,
                                      chave=("celula", pos_tab, r, col)))
    return itens


def _itens_de_secoes(doc: QTextDocument) -> list[Item]:
    if not getattr(doc, "_corpo_com_secoes", False):
        return []
    itens = []
    reg = pq_secoes.registro(doc)
    for pos, ident in pq_secoes.quebras_de_secao(doc, fresco=True):
        secao = reg.get(ident)
        texto = (secao.original or secao.extras) if secao is not None else None
        if texto and "sectPrChange" in texto:
            itens.append(Item("secao", _autor_do_xml(texto), _data_do_xml(texto), pos, pos + 1,
                              "Quebra de seção", doc=doc, chave=("secao", ident)))
    final = pq_secoes.secao_final(doc)
    texto = final.original or final.extras
    if texto and "sectPrChange" in texto:
        fim = doc.characterCount() - 1
        itens.append(Item("secao", _autor_do_xml(texto), _data_do_xml(texto), fim, fim,
                          "Última seção", doc=doc, chave=("secao", None)))
    return itens


def no_cursor(editor) -> Item | None:
    """A revisao do cursor (ou a primeira da selecao)."""
    doc = editor.document()
    c = editor.textCursor()
    a, b = c.selectionStart(), c.selectionEnd()
    candidatos = [i for i in listar(doc)
                  if (i.inicio <= a < i.fim) or (a == b and i.inicio <= a <= i.fim and i.fim > i.inicio)
                  or (b > a and i.inicio < b and i.fim > a)]
    if not candidatos:
        candidatos = [i for i in listar(doc) if i.inicio == i.fim == a]
    return candidatos[0] if candidatos else None


def ir(editor, proxima: bool = True) -> Item | None:
    """Revisao > Proxima / Anterior: seleciona a revisao seguinte (ou a de antes), dando a volta."""
    doc = editor.document()
    itens = listar(doc)
    if not itens:
        return None
    c = editor.textCursor()
    if proxima:
        pos = c.selectionEnd() if c.hasSelection() else c.position()
        alvo = next((i for i in itens if i.inicio >= pos and (i.inicio, i.fim) != (
            c.selectionStart(), c.selectionEnd())), None) or itens[0]
    else:
        pos = c.selectionStart()
        antes = [i for i in itens if i.inicio < pos]
        alvo = antes[-1] if antes else itens[-1]
    selecionar(editor, alvo)
    return alvo


def selecionar(editor, item: Item) -> None:
    c = QTextCursor(editor.document())
    ultimo = editor.document().characterCount() - 1
    c.setPosition(min(item.inicio, ultimo))
    if item.fim > item.inicio:
        c.setPosition(min(item.fim, ultimo), Manter)
    editor.setTextCursor(c)


# -- aceitar e rejeitar ----------------------------------------------------------------------

@dataclass
class Resultado:
    resolvidas: int = 0
    so_aceitar: int = 0


def _filtro(item: Item | None, autor_: str | None):
    """Funcao (tipo, autor, chave) -> bool."""
    def vale(tipo: str, quem: str, chave) -> bool:
        if autor_ is not None and quem != autor_:
            return False
        if item is None:
            return True
        if item.tipo in ("moveFrom", "moveTo") and item.movimento is not None:
            return tipo in ("moveFrom", "moveTo")
        return tipo == item.tipo and chave == item.chave
    return vale


def resolver(editor, aceitar: bool, item: Item | None = None, autor_: str | None = None,
             intervalo: tuple[int, int] | None = None, doc: QTextDocument | None = None) -> Resultado:
    """Aceita ou rejeita: uma revisao (`item`), as de um autor, as de um intervalo (a selecao) ou
    todas (sem nada). Um passo de desfazer no documento."""
    doc = doc or (item.doc if item is not None else editor.document())
    res = Resultado()
    if not pq.tem_revisoes(doc):
        return res
    if item is not None and item.tipo in ("moveFrom", "moveTo") and item.movimento is not None:
        intervalos = [(a, b) for g, nome, a, b, _p in _trechos_de_movimento(doc)
                      if nome == item.movimento]
    elif item is not None:
        intervalos = [(item.inicio, item.fim)]
    elif intervalo is not None:
        intervalos = [intervalo]
    else:
        intervalos = [(0, doc.characterCount())]
    vale = _filtro(item, autor_)
    c = QTextCursor(doc)
    c.beginEditBlock()
    try:
        for a, b in sorted(intervalos, reverse=True):
            _resolver_tabelas(doc, aceitar, vale, a, b, res, item)
            _resolver_texto(editor, doc, aceitar, vale, a, b, res)
        if item is None or item.tipo == "secao":
            _resolver_secoes(doc, aceitar, vale, intervalos, res, item)
        _limpar_movimentos(doc)
    finally:
        c.endEditBlock()
    doc._lista_revisoes = None
    return res


def _resolver_texto(editor, doc, aceitar: bool, vale, a: int, b: int, res: Resultado) -> None:
    """Fragmentos, propriedades e marcas de paragrafo de [a, b), do ultimo bloco para o primeiro
    (e, no bloco, a marca do fim antes do texto): o que muda depois nao mexe nas posicoes de
    antes."""
    if b <= a:
        return
    numeros = []
    bloco = doc.findBlock(a)
    while bloco.isValid() and bloco.position() < b:
        numeros.append(bloco.blockNumber())
        bloco = bloco.next()
    for n in reversed(numeros):
        bloco = doc.findBlockByNumber(n)
        if not bloco.isValid():
            continue
        inicio, fim = bloco.position(), bloco.position() + bloco.length() - 1
        if a <= fim < b:
            _resolver_marca(doc, bloco, aceitar, vale, res)
        bloco = doc.findBlockByNumber(n)
        _resolver_paragrafo(doc, bloco, aceitar, vale, res)
        for x, y, cf in reversed(_fragmentos(doc, max(a, inicio), min(b, fim))):
            _resolver_fragmento(doc, x, y, cf, aceitar, vale, res)


def _resolver_fragmento(doc, x: int, y: int, cf, aceitar: bool, vale, res: Resultado) -> None:
    ins, exc = pq.insercao_de(cf), pq.exclusao_de(cf)
    ins_t = cf.property(pq.PROP_REV_INS) if ins is not None else None
    exc_t = cf.property(pq.PROP_REV_DEL) if exc is not None else None
    mudanca = pq.mudanca_de(cf)
    ins_vale = ins is not None and vale(ins.tipo, ins.autor, ins_t)
    exc_vale = exc is not None and vale(exc.tipo, exc.autor, exc_t)
    if aceitar:
        if exc_vale:
            _remover(doc, x, y)
            res.resolvidas += 1
            return
    elif ins_vale:
        _remover(doc, x, y)
        res.resolvidas += 1
        return
    novo = QTextCharFormat(cf)
    mudou = False
    if aceitar and ins_vale:
        novo.clearProperty(pq.PROP_REV_INS)
        mudou = True
    if not aceitar and exc_vale:
        novo.clearProperty(pq.PROP_REV_DEL)
        mudou = True
    if mudanca and vale("formato", _autor_do_xml(mudanca), mudanca):
        if not aceitar:
            novo = _com_formatacao_de_antes(doc, x, novo, mudanca)
        novo.clearProperty(pq.PROP_REV_RPR)
        mudou = True
    if mudou:
        _trocar_formato(doc, x, y, novo)
        res.resolvidas += 1


def _com_formatacao_de_antes(doc, x: int, cf: QTextCharFormat, mudanca: str) -> QTextCharFormat:
    """Rejeitar a formatacao: o formato com a formatacao de antes (estilo, direta, extras)."""
    from editdoc.modelo.estilos import CAMPOS_CARACTERE
    from editdoc.ponte_qt import estilos as pq_estilos
    from editdoc.ponte_qt import propriedades as pq_props
    cat = pq_estilos.catalogo(doc)
    run = fx_revisoes.run_da_mudanca(mudanca, cat)
    if run is None:
        return cf
    P = QTextFormat.Property
    for prop in (P.FontWeight, P.FontItalic, P.TextUnderlineStyle, P.FontUnderline,
                 P.FontStrikeOut, P.TextVerticalAlignment, P.FontPointSize, P.FontFamilies,
                 P.ForegroundBrush, pq_estilos.PROP_ESTILO_CAR):
        cf.clearProperty(prop)
    pq_props.tirar_rpr(cf)
    sid_par = pq_estilos.estilo_do_bloco(doc.findBlock(x).blockFormat())
    base = _resolvedor(doc).caractere(sid_par, run.estilo)
    props = {**base, **{k: getattr(run, k) for k in CAMPOS_CARACTERE if getattr(run, k) is not None}}
    pq_estilos.aplicar_caractere(cf, props)
    if run.estilo:
        cf.setProperty(pq_estilos.PROP_ESTILO_CAR, run.estilo)
    pq_props.aplicar_rpr(cf, run.extras)
    return cf


def _resolver_marca(doc, bloco, aceitar: bool, vale, res: Resultado) -> None:
    m_ins, m_exc = pq.marca_de(bloco.blockFormat())
    if m_ins is None and m_exc is None:
        return
    ins_vale = m_ins is not None and vale("marca_ins", m_ins.autor, pq.json_de(m_ins))
    exc_vale = m_exc is not None and vale("marca_del", m_exc.autor, pq.json_de(m_exc))
    fim = bloco.position() + bloco.length() - 1
    juntar = (aceitar and exc_vale) or (not aceitar and ins_vale)
    if juntar and bloco.next().isValid() and doc.characterAt(fim) == _SEPARADOR \
            and QTextCursor(bloco).currentTable() == QTextCursor(bloco.next()).currentTable():
        # Junta com o paragrafo de baixo: o texto de la' sobe, com a marca de la'.
        proximo = bloco.next()
        bf_baixo = QTextBlockFormat(proximo.blockFormat())
        _remover(doc, fim, fim + 1)
        bloco = doc.findBlock(fim)
        bf = QTextBlockFormat(bloco.blockFormat())
        pq.definir_marca(bf, *pq.marca_de(bf_baixo))
        _bloco_formato(doc, bloco, bf)
        res.resolvidas += 1
        return
    if not (ins_vale or exc_vale):
        return
    novo_ins = None if ins_vale else m_ins
    novo_exc = None if exc_vale else m_exc
    bf = QTextBlockFormat(bloco.blockFormat())
    pq.definir_marca(bf, novo_ins, novo_exc)
    _bloco_formato(doc, bloco, bf)
    res.resolvidas += 1


def _resolver_paragrafo(doc, bloco, aceitar: bool, vale, res: Resultado) -> None:
    ppr, num = pq.mudanca_de_bloco(bloco.blockFormat())
    if not ppr and not num:
        return
    novo_ppr, novo_num = ppr, num
    if ppr and vale("paragrafo", _autor_do_xml(ppr), ppr):
        novo_ppr = None
        if not aceitar:
            _devolver_paragrafo(doc, bloco, ppr)
            bloco = doc.findBlock(bloco.position())
        res.resolvidas += 1
    if num and vale("numeracao", _autor_do_xml(num), num):
        if aceitar:
            novo_num = None
            res.resolvidas += 1
        else:
            res.so_aceitar += 1
    if (novo_ppr, novo_num) != (ppr, num):
        bf = QTextBlockFormat(bloco.blockFormat())
        pq.definir_mudanca_de_bloco(bf, novo_ppr, novo_num)
        _bloco_formato(doc, bloco, bf)


#: Propriedades do bloco que nao sao do paragrafo de antes (ficam ao rejeitar a formatacao).
def _props_que_ficam():
    from editdoc.ponte_qt import estilos as pq_estilos
    from editdoc.ponte_qt import notas as pq_notas
    from editdoc.ponte_qt.para_qt import PROP_ESTRUTURAL
    return (pq.PROP_REV_MARCA, pq.PROP_REV_PPR, pq_notas.PROP_QUEBRA_NOTA,
            pq_secoes.PROP_QUEBRA_SECAO, pq_estilos.PROP_RECUO_SECAO, PROP_ESTRUTURAL)


def _devolver_paragrafo(doc, bloco, ppr: str) -> None:
    from editdoc.modelo.documento import Paragrafo
    from editdoc.ponte_qt import listas as pq_listas
    from editdoc.ponte_qt import para_qt
    res = _resolvedor(doc)
    props = fx_revisoes.paragrafo_da_mudanca(ppr, res.estilos, res.numeracao)
    if props is None:
        return
    props.pop("quebra_antes", None)
    try:
        p = Paragrafo(**props)
    except TypeError:
        return
    em_tabela = QTextCursor(bloco).currentTable() is not None
    bf = para_qt._formato_do_bloco(p, res, em_tabela)
    atual = bloco.blockFormat()
    for prop in _props_que_ficam():
        if atual.hasProperty(prop):
            bf.setProperty(prop, atual.property(prop))
    bf.setPageBreakPolicy(atual.pageBreakPolicy())
    _bloco_formato(doc, bloco, bf)
    pq_listas.numerador_de(doc).marcar_sujo()


def _resolver_tabelas(doc, aceitar: bool, vale, a: int, b: int, res: Resultado, item) -> None:
    """Linhas inseridas/excluidas, revisoes de celula e de propriedades de tabela em [a, b]."""
    from editdoc.ponte_qt.para_qt import (PROP_CELULA, PROP_TABELA, aplicar_formatos_das_celulas,
                                          ler_json)
    import json
    for tabela in reversed(_tabelas(doc)):
        if tabela.lastPosition() < a or tabela.firstPosition() > max(b, a):
            continue
        pos_tab = tabela.firstPosition()
        removida = False
        for r in reversed(range(tabela.rows())):
            if removida:
                break
            cel0 = tabela.cellAt(r, 0)
            linha = _json_celula(cel0).get("extras_linha")
            el = fx_revisoes.elemento_canonico(linha if isinstance(linha, str) else None)
            if el is None:
                continue
            ini = cel0.firstCursorPosition().position()
            if item is not None and item.chave != ("linha", pos_tab, r):
                continue
            if item is None and not (a <= ini <= b):
                continue
            from editdoc.formato_docx.nomes import q
            for nome, tipo in (("ins", "linha_ins"), ("del", "linha_del")):
                marca = el.find(q(nome))
                if marca is None or not vale(tipo, marca.get(q("author")) or "",
                                             item.chave if item is not None else None):
                    continue
                remover_linha = (aceitar and nome == "del") or (not aceitar and nome == "ins")
                if remover_linha:
                    if tabela.rows() > 1:
                        tabela.removeRows(r, 1)
                        aplicar_formatos_das_celulas(tabela)
                    else:
                        # A ultima linha: a tabela inteira sai (o QTextTable morre aqui).
                        c = QTextCursor(doc)
                        c.setPosition(tabela.firstPosition() - 1)
                        c.setPosition(tabela.lastPosition() + 1, Manter)
                        c.removeSelectedText()
                        removida = True
                    res.resolvidas += 1
                    break
                novo = fx_revisoes.sem_elementos(linha, {nome})
                for col in range(tabela.columns()):
                    c = tabela.cellAt(r, col)
                    if c.row() != r:
                        continue
                    fmt = c.format().toTableCellFormat()
                    dado = ler_json(fmt, PROP_CELULA)
                    dado["extras_linha"] = novo
                    fmt.setProperty(PROP_CELULA, json.dumps(dado, sort_keys=True))
                    c.setFormat(fmt)
                linha = novo
                el = fx_revisoes.elemento_canonico(novo)
                res.resolvidas += 1
                if el is None:
                    break
        if removida:
            continue
        # Celulas e propriedades da tabela: so' aceitar.
        for r in range(tabela.rows()):
            for col in range(tabela.columns()):
                c = tabela.cellAt(r, col)
                if c.row() != r or c.column() != col:
                    continue
                dado = _json_celula(c)
                extras_c = dado.get("extras") if isinstance(dado.get("extras"), str) else None
                if not fx_revisoes.tem_revisao(extras_c):
                    continue
                if item is not None and item.chave != ("celula", pos_tab, r, col):
                    continue
                if not vale("celula", _autor_do_xml(extras_c), item.chave if item else None):
                    continue
                if not aceitar:
                    res.so_aceitar += 1
                    continue
                fmt = c.format().toTableCellFormat()
                dado["extras"] = fx_revisoes.sem_elementos(
                    extras_c, {"cellIns", "cellDel", "cellMerge", "tcPrChange"})
                fmt.setProperty(PROP_CELULA, json.dumps(dado, sort_keys=True))
                c.setFormat(fmt)
                res.resolvidas += 1
        dado = ler_json(tabela.format(), PROP_TABELA)
        extras_t = dado.get("extras") if isinstance(dado.get("extras"), str) else None
        if (fx_revisoes.tem_revisao(extras_t) or dado.get("mudanca_grade")) and \
                (item is None or item.chave == ("tabela", pos_tab)) and \
                vale("tabela", _autor_do_xml(extras_t or dado.get("mudanca_grade") or ""),
                     item.chave if item else None):
            if not aceitar:
                res.so_aceitar += 1
            else:
                tf = tabela.format()
                dado["extras"] = fx_revisoes.sem_elementos(extras_t, {"tblPrChange"})
                dado["mudanca_grade"] = None
                tf.setProperty(PROP_TABELA, json.dumps(dado, sort_keys=True))
                tabela.setFormat(tf)
                res.resolvidas += 1


def _resolver_secoes(doc, aceitar: bool, vale, intervalos, res: Resultado, item) -> None:
    if not getattr(doc, "_corpo_com_secoes", False):
        return
    reg = pq_secoes.registro(doc)
    alvos = []
    for pos, ident in pq_secoes.quebras_de_secao(doc, fresco=True):
        if item is not None and item.chave != ("secao", ident):
            continue
        if item is None and not any(a <= pos < b for a, b in intervalos):
            continue
        alvos.append((pos, ident, reg.get(ident)))
    final = pq_secoes.secao_final(doc)
    if (item is None and any(b >= doc.characterCount() - 1 for _a, b in intervalos)) or \
            (item is not None and item.chave == ("secao", None)):
        alvos.append((None, None, final))
    for pos, ident, secao in alvos:
        if secao is None:
            continue
        texto = secao.original or secao.extras
        if not texto or "sectPrChange" not in texto or not vale(
                "secao", _autor_do_xml(texto), item.chave if item else None):
            continue
        if not aceitar:
            res.so_aceitar += 1
            continue
        nova_secao = pq_secoes.copia(secao, original=fx_revisoes.secao_sem_mudanca(secao.original),
                                     extras=fx_revisoes.secao_sem_mudanca(secao.extras))
        if pos is None:
            pq_secoes.trocar_final(doc, nova_secao)
        else:
            pq_secoes.trocar_secao_do_caractere(QTextCursor(doc), pos, nova_secao)
        res.resolvidas += 1


def _limpar_movimentos(doc: QTextDocument) -> None:
    """Tira as marcas dos trechos de movimento que nao tem mais texto movido."""
    trechos = _trechos_de_movimento(doc)
    if not trechos:
        return
    apagar: list[int] = []
    for _g, _nome, a, b, posicoes in trechos:
        tem = any(pq.insercao_de(cf) is not None and pq.insercao_de(cf).tipo == "moveTo"
                  or pq.exclusao_de(cf) is not None and pq.exclusao_de(cf).tipo == "moveFrom"
                  for _x, _y, cf in _fragmentos(doc, a, b))
        if not tem:
            apagar.extend(posicoes)
    for pos in sorted(set(apagar), reverse=True):
        _remover(doc, pos, pos + 1)


# -- texto no modo (contar, copiar, localizar) -----------------------------------------------

def texto_no_modo(doc: QTextDocument, modo: str | None = None) -> str:
    """O texto do documento como o modo mostra (o de `toPlainText` sem o que esta' escondido)."""
    texto = doc.toPlainText()
    ocultos = pq.intervalos_ocultos(doc, 0, doc.characterCount(), modo)
    if not ocultos:
        return texto
    partes = []
    anterior = 0
    for a, b in ocultos:
        partes.append(texto[anterior:a])
        anterior = b
    partes.append(texto[anterior:])
    return "".join(partes)


def modo_para_copiar(doc: QTextDocument) -> str:
    """Copiar leva o que se le: em Toda a marcacao, o texto final (como o Word)."""
    modo = pq.modo_de(doc)
    return "final" if modo == "todas" else modo
