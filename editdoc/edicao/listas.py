"""Comandos de lista (0.1.4): marcadores, numeracao, varios niveis, nivel e valor, como no Word.

Cada comando e' UM passo de desfazer: o catalogo de numeracao (acrescimos no quadro raiz,
`ponte_qt/listas.py`), os blocos e o recuo visual do texto depois do numero mudam no mesmo
bloco de edicao. Uma definicao que veio do arquivo nunca e' alterada: reiniciar, continuar,
definir o valor e trocar o formato criam instancias (w:num) ou abstratas novas.

Trocar a lista de um bloco recompoe o formato dele: o recuo que o nivel velho dava sai, o do
nivel novo entra, e a formatacao direta do paragrafo fica (`pq_estilos.recompor_bloco`).

Teclado (o painel chama): Tab e Shift+Tab no inicio do item mudam o nivel; Enter num item
vazio sobe um nivel ou sai da lista; Backspace no inicio do item tira o numero e mantem o
texto onde estava, e de novo tira o recuo.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtGui import QTextBlockFormat, QTextCursor, QTextFormat

from editdoc.modelo import numeracao as mod
from editdoc.modelo.estilos import nivel_de_titulo
from editdoc.ponte_qt import estilos as pq
from editdoc.ponte_qt import listas as pl


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
    if hasattr(editor, "_depois_de_mover"):
        editor._depois_de_mover()


def _catalogo(doc) -> mod.Numeracao:
    cat = pl.catalogo(doc)
    return cat.copia() if cat is not None else mod.Numeracao()


def efetiva(doc, bloco) -> tuple[int, int] | None:
    """(numId, ilvl) que valem para o bloco (direto ou do estilo)."""
    return pl.efetiva_do_bloco(bloco, pq.catalogo(doc), pl.catalogo(doc))


def tipo_no_cursor(editor) -> str | None:
    """"marcadores", "numeracao" ou None: o que a faixa mostra marcado."""
    doc = editor.document()
    bloco = doc.findBlock(editor.textCursor().selectionStart())
    ef = efetiva(doc, bloco)
    cat = pl.catalogo(doc)
    return cat.tipo_de(*ef, pq.catalogo(doc)) if ef is not None and cat is not None else None


class _Edicao:
    """Uma troca de listas em blocos: abre o bloco de edicao, guarda o catalogo novo e ajusta
    o recuo visual no fim, tudo no mesmo passo de desfazer."""

    def __init__(self, editor) -> None:
        self.editor = editor
        self.doc = editor.document()
        self.estilos = pq.catalogo(self.doc)
        self.cat_velho = pl.catalogo(self.doc)
        self.cat = _catalogo(self.doc)
        self.cursor = editor.textCursor()

    def __enter__(self):
        self.cursor.beginEditBlock()
        return self

    def __exit__(self, *_erro) -> None:
        try:
            if self.cat.adicoes_json() != (self.cat_velho.adicoes_json()
                                           if self.cat_velho is not None else None):
                pl.trocar_catalogo(self.doc, self.cat)
            for bloco, num, nivel, extra in getattr(self, "_pendentes", []):
                self._aplicar(bloco, num, nivel, extra)
            pl.numerador_de(self.doc).marcar_sujo()
            pl.ajustar_recuos(self.doc)
        finally:
            self.cursor.endEditBlock()
        _depois(self.editor)

    def trocar(self, bloco, num: int | None, nivel: int | None, extra: dict | None = None) -> None:
        """Anota a lista nova do bloco (aplicada no fim, com o catalogo novo ja' gravado)."""
        if not hasattr(self, "_pendentes"):
            self._pendentes = []
        self._pendentes.append((bloco, num, nivel, extra))

    def _aplicar(self, bloco, num, nivel, extra) -> None:
        bf = bloco.blockFormat()
        sid = pq.estilo_do_bloco(bf)
        em_tabela = QTextCursor(bloco).currentTable() is not None
        velho = pl.lista_do_bloco(bf)
        res_v = pq.Resolvedor(self.estilos, self.cat_velho)
        res_n = pq.Resolvedor(self.estilos, self.cat)
        par_v, _ = res_v.paragrafo(sid, em_tabela, velho)
        par_n, _ = res_n.paragrafo(sid, em_tabela, (num, nivel))
        nbf = pq.recompor_bloco(bf, par_v, par_n, sid, self.estilos)
        pl.marcar_lista(nbf, num, nivel)
        nbf.clearProperty(pl.PROP_SAIU_DA_LISTA)
        if extra:
            if "esquerdo" in extra:
                nbf.setLeftMargin(float(extra["esquerdo"]))
            if "primeira" in extra:
                nbf.setTextIndent(float(extra["primeira"]))
            if extra.get("saiu"):
                nbf.setProperty(pl.PROP_SAIU_DA_LISTA, True)
        QTextCursor(bloco).setBlockFormat(nbf)


def _sem_lista(estilos, bloco) -> tuple[int | None, int | None]:
    """A referencia que tira a lista do bloco: 0 se o estilo tem lista, senao nada."""
    sid = pq.estilo_do_bloco(bloco.blockFormat())
    for e in estilos.cadeia(sid or estilos.id_padrao()):
        if getattr(e, "lista", None):
            return 0, None
    return None, None


def _vizinho_anterior(bloco):
    """O bloco de texto antes deste no mesmo conteiner (corpo ou celula), ou None."""
    anterior = bloco.previous()
    if not anterior.isValid():
        return None
    if QTextCursor(anterior).currentTable() != QTextCursor(bloco).currentTable():
        return None
    return anterior


# -- marcadores e numeracao -------------------------------------------------------------

def _aplicar_definicao(editor, niveis: tuple, tipo: str, chave_tipo: str,
                       reiniciar: bool, multinivel: bool = False) -> None:
    """Liga a lista nos paragrafos da selecao, ou desliga se ja' estao numa lista do mesmo
    tipo (o mesmo botao liga e desliga, como no Word)."""
    doc = editor.document()
    blocos = _blocos_da_selecao(editor)
    estilos = pq.catalogo(doc)
    cat = pl.catalogo(doc)
    atuais = [efetiva(doc, b) for b in blocos]
    mesma = all(a is not None and cat is not None and cat.tipo_de(*a, estilos) == chave_tipo
                for a in atuais)
    with _Edicao(editor) as ed:
        abstrata = ed.cat.adicionar_abstrata(niveis, tipo)
        if mesma and not multinivel and all(
                ed.cat.abstrata_de(a[0], estilos) is not None
                and ed.cat.abstrata_de(a[0], estilos).niveis == abstrata.niveis for a in atuais):
            for b in blocos:
                ed.trocar(b, *_sem_lista(estilos, b))
            return
        anterior = _vizinho_anterior(blocos[0])
        num = None
        if anterior is not None:
            ef_ant = efetiva(doc, anterior)
            if ef_ant is not None and ed.cat.abstrata_de(ef_ant[0], estilos) is not None and \
                    ed.cat.abstrata_de(ef_ant[0], estilos).niveis == abstrata.niveis:
                num = ef_ant[0]  # continua a lista logo acima
        if num is None:
            if reiniciar:
                num = ed.cat.adicionar_instancia(abstrata.id, (mod.Sobrescrita(ilvl=0, inicio=1),)).id
            else:
                num = ed.cat.instancia_simples(abstrata.id).id
        for b, atual in zip(blocos, atuais):
            ed.trocar(b, num, atual[1] if atual is not None else 0)


def alternar_marcadores(editor, chave: str = "redondo") -> None:
    _aplicar_definicao(editor, mod.niveis_de_marcadores(chave), "hybridMultilevel",
                       "marcadores", reiniciar=False)


def alternar_numeracao(editor, chave: str = "decimal_ponto") -> None:
    _aplicar_definicao(editor, mod.niveis_de_numeracao(chave), "hybridMultilevel",
                       "numeracao", reiniciar=True)


def aplicar_multinivel(editor, chave: str = "decimal") -> None:
    """Lista de varios niveis. "titulos" liga os niveis aos estilos Titulo 1 a 9 (o numPr
    vai para os estilos, e os paragrafos de titulo herdam), como a lista de titulos do Word."""
    if chave == "titulos":
        _titulos_numerados(editor)
        return
    _aplicar_definicao(editor, mod.niveis_multinivel(chave), "multilevel", "numeracao",
                       reiniciar=True, multinivel=True)


def _titulos_numerados(editor) -> None:
    doc = editor.document()
    velho = pq.catalogo(doc)
    novo = velho.copia()
    ids = []
    for i in range(1, 10):
        estilo = novo.por_nome(f"heading {i}")
        if estilo is None and i <= 3:
            estilo = novo.garantir(f"heading {i}")
        ids.append(estilo.id if estilo is not None else None)
    niveis = tuple(
        replace(n, estilo=ids[n.ilvl]) for n in mod.niveis_multinivel("titulos"))
    blocos = _blocos_da_selecao(editor)
    with _Edicao(editor) as ed:
        abstrata = ed.cat.adicionar_abstrata(niveis, "multilevel")
        num = ed.cat.adicionar_instancia(abstrata.id).id
        alterados = set()
        for i, sid in enumerate(ids):
            if sid is None:
                continue
            e = novo.obter(sid)
            e.lista, e.lista_nivel = num, i
            e.alterado = True
            alterados.add(sid)
        ed.estilos = novo
        pq.trocar_catalogo(doc, novo)
        # Os paragrafos de titulo recompoem com o recuo do nivel; os outros da selecao viram
        # Titulo 1 (a lista e' de titulos).
        rv = pq.Resolvedor(velho, ed.cat_velho)
        rn = pq.Resolvedor(novo, ed.cat)
        todos = []
        bloco = doc.begin()
        while bloco.isValid():
            todos.append(bloco)
            bloco = bloco.next()
        selecionados = {b.blockNumber() for b in blocos}
        for b in todos:
            sid = pq.estilo_do_bloco(b.blockFormat())
            if b.blockNumber() in selecionados and (sid is None or nivel_de_titulo(
                    novo.obter(sid).nome if novo.obter(sid) else "") is None):
                pq.recompor_blocos(doc, [b], rv, rn, sid_novo=ids[0])
            elif sid in alterados:
                pq.recompor_blocos(doc, [b], rv, rn, filtro=lambda sp, sc: sc is None)
        ed.estilos = novo


# -- nivel ------------------------------------------------------------------------------

def mudar_nivel(editor, delta: int, blocos: list | None = None) -> bool:
    """Aumenta (delta > 0) ou diminui o nivel dos itens. False se nenhum bloco e' item.

    Titulo numerado pela lista de titulos troca de estilo (Titulo 1 -> Titulo 2), como o Word.
    """
    doc = editor.document()
    blocos = blocos if blocos is not None else _blocos_da_selecao(editor)
    estilos = pq.catalogo(doc)
    cat = pl.catalogo(doc)
    itens = [(b, efetiva(doc, b)) for b in blocos]
    itens = [(b, e) for b, e in itens if e is not None]
    if not itens or cat is None:
        return False
    with _Edicao(editor) as ed:
        for b, (num, ilvl) in itens:
            novo = min(max(ilvl + delta, 0), mod.NIVEIS - 1)
            if novo == ilvl:
                continue
            direto = pl.lista_do_bloco(b.blockFormat())
            nivel_novo = cat.nivel_de(num, novo, estilos)
            if direto[0] is None and nivel_novo is not None and nivel_novo.estilo and \
                    estilos.obter(nivel_novo.estilo) is not None:
                # Lista do estilo com o nivel ligado a outro estilo: troca o estilo.
                pq.recompor_blocos(doc, [b], pq.Resolvedor(estilos), pq.Resolvedor(estilos),
                                   sid_novo=nivel_novo.estilo)
                continue
            ed.trocar(b, num, novo)
    return True


def eh_item(editor, bloco=None) -> bool:
    doc = editor.document()
    bloco = bloco if bloco is not None else editor.textCursor().block()
    return efetiva(doc, bloco) is not None


def remover_lista(editor, blocos: list | None = None) -> None:
    doc = editor.document()
    blocos = blocos if blocos is not None else _blocos_da_selecao(editor)
    estilos = pq.catalogo(doc)
    with _Edicao(editor) as ed:
        for b in blocos:
            if efetiva(doc, b) is not None:
                ed.trocar(b, *_sem_lista(estilos, b))


def enter_em_item_vazio(editor) -> bool:
    """Enter num item vazio: sobe um nivel, ou sai da lista no primeiro nivel. True se tratou."""
    cursor = editor.textCursor()
    bloco = cursor.block()
    if cursor.hasSelection() or bloco.text() != "":
        return False
    ef = efetiva(editor.document(), bloco)
    if ef is None:
        return False
    if ef[1] > 0:
        return mudar_nivel(editor, -1, [bloco])
    remover_lista(editor, [bloco])
    return True


def backspace_no_inicio(editor) -> bool:
    """Backspace no inicio do item: tira o numero e deixa o texto onde estava (recuo esquerdo
    no texto, primeira linha sem deslocamento). De novo: tira esse recuo. True se tratou."""
    cursor = editor.textCursor()
    if cursor.hasSelection() or not cursor.atBlockStart():
        return False
    doc = editor.document()
    bloco = cursor.block()
    bf = bloco.blockFormat()
    estilos = pq.catalogo(doc)
    ef = efetiva(doc, bloco)
    if ef is not None:
        texto_x = bf.leftMargin() + bf.textIndent()
        with _Edicao(editor) as ed:
            ed.trocar(bloco, *_sem_lista(estilos, bloco),
                      {"esquerdo": max(0.0, texto_x), "primeira": 0.0, "saiu": True})
        return True
    if bf.property(pl.PROP_SAIU_DA_LISTA):
        sid = pq.estilo_do_bloco(bf)
        em_tabela = QTextCursor(bloco).currentTable() is not None
        res = pq.Resolvedor(estilos)
        base, _ = res.paragrafo(sid, em_tabela, pl.lista_do_bloco(bf))
        nbf = QTextBlockFormat(bf)
        nbf.clearProperty(pl.PROP_SAIU_DA_LISTA)
        nbf.setLeftMargin(float(base.get("recuo_esquerdo_tw") or 0))
        if base.get("recuo_primeira_linha_tw") is not None:
            nbf.setTextIndent(float(base["recuo_primeira_linha_tw"]))
        else:
            nbf.clearProperty(QTextFormat.Property.TextIndent)
        c = QTextCursor(bloco)
        c.beginEditBlock()
        c.setBlockFormat(nbf)
        c.endEditBlock()
        _depois(editor)
        return True
    return False


# -- reiniciar, continuar e definir valor ---------------------------------------------------

def _seguintes(doc, bloco, num: int) -> list:
    """O bloco e os blocos depois dele que usam o mesmo numId (direto ou herdado)."""
    saida = []
    b = bloco
    estilos = pq.catalogo(doc)
    cat = pl.catalogo(doc)
    while b.isValid():
        ef = pl.efetiva_do_bloco(b, estilos, cat)
        if ef is not None and ef[0] == num:
            saida.append((b, ef[1]))
        b = b.next()
    return saida


def definir_valor(editor, valor: int) -> bool:
    """O item do cursor passa a ter o numero `valor`, e os seguintes da mesma lista continuam
    dele (uma instancia nova com w:startOverride no nivel do item). False se nao e' item."""
    doc = editor.document()
    bloco = editor.textCursor().block()
    ef = efetiva(doc, bloco)
    if ef is None:
        return False
    num, ilvl = ef
    cat = pl.catalogo(doc)
    inst = cat.instancias.get(num)
    if inst is None:
        return False
    seguintes = _seguintes(doc, bloco, num)
    with _Edicao(editor) as ed:
        novo = ed.cat.adicionar_instancia(inst.abstrata,
                                          (mod.Sobrescrita(ilvl=ilvl, inicio=int(valor)),))
        for b, nivel in seguintes:
            ed.trocar(b, novo.id, nivel)
    return True


def reiniciar(editor) -> bool:
    """Reiniciar em 1 (o inicio do nivel, na verdade, como o Word)."""
    doc = editor.document()
    bloco = editor.textCursor().block()
    ef = efetiva(doc, bloco)
    if ef is None:
        return False
    # O inicio do nivel na abstrata (sem o startOverride da instancia), como o Word.
    abstrata = pl.catalogo(doc).abstrata_de(ef[0], pq.catalogo(doc))
    nivel = abstrata.nivel(ef[1]) if abstrata is not None else None
    return definir_valor(editor, nivel.inicio if nivel is not None and nivel.inicio > 0 else 1)


def continuar(editor) -> bool:
    """Continuar numeracao: o item e os seguintes da mesma lista passam para a lista anterior
    de mesma definicao. False se nao ha' lista anterior para continuar."""
    doc = editor.document()
    bloco = editor.textCursor().block()
    ef = efetiva(doc, bloco)
    if ef is None:
        return False
    estilos = pq.catalogo(doc)
    cat = pl.catalogo(doc)
    abstrata = cat.abstrata_de(ef[0], estilos)
    alvo = None
    b = bloco.previous()
    while b.isValid():
        ant = pl.efetiva_do_bloco(b, estilos, cat)
        if ant is not None and ant[0] != ef[0]:
            outra = cat.abstrata_de(ant[0], estilos)
            if outra is not None and abstrata is not None and (
                    outra.id == abstrata.id or outra.niveis == abstrata.niveis):
                alvo = ant[0]
                break
        b = b.previous()
    if alvo is None:
        return False
    seguintes = _seguintes(doc, bloco, ef[0])
    with _Edicao(editor) as ed:
        for item, nivel in seguintes:
            ed.trocar(item, alvo, nivel)
    return True


# -- copiar e colar --------------------------------------------------------------------------

def dados_para_copiar(doc, inicio: int, fim: int) -> dict | None:
    """As listas dos blocos de [inicio, fim): para colar no EditDoc com a lista."""
    cat = pl.catalogo(doc)
    bloco = doc.findBlock(inicio)
    ultimo = doc.findBlock(max(inicio, fim - 1) if fim > inicio else inicio).blockNumber()
    itens = []
    nums = set()
    while bloco.isValid() and bloco.blockNumber() <= ultimo:
        bf = bloco.blockFormat()
        num, nivel = pl.lista_do_bloco(bf)
        real = pl.recuo_real(bf) if bf.hasProperty(pl.PROP_RECUO_REAL) else None
        itens.append([num, nivel, real])
        if num:
            nums.add(num)
        bloco = bloco.next()
    if not nums and not any(i[1] is not None for i in itens):
        return None
    return {"documento": id(getattr(pl._doc_do_catalogo(doc), "_numeracao_base", None)),
            "blocos": itens,
            "definicoes": mod.definicoes_para_json(cat, nums) if cat is not None else {}}


def aplicar_colado(editor, dado: dict, inicio: int, fim: int, no_inicio_vazio: bool) -> None:
    """Depois do colar: os blocos colados voltam para as listas que tinham."""
    doc = editor.document()
    itens = dado.get("blocos") or []
    blocos = []
    bloco = doc.findBlock(inicio)
    while bloco.isValid() and bloco.position() <= fim:
        blocos.append(bloco)
        bloco = bloco.next()
    if len(blocos) != len(itens) or (len(itens) < 2 and not no_inicio_vazio):
        return
    pares = list(zip(blocos, itens))
    if not no_inicio_vazio:
        pares = pares[1:]  # o primeiro bloco colado e' o bloco onde estava o cursor
    with _Edicao(editor) as ed:
        mesmo = dado.get("documento") == id(getattr(pl._doc_do_catalogo(doc), "_numeracao_base", None))
        mapa = {}
        if not mesmo:
            mapa = mod.importar_definicoes(ed.cat, dado.get("definicoes") or {})
        for b, (num, nivel, real) in pares:
            if num and not mesmo:
                num = mapa.get(num)
            if num and num not in ed.cat.instancias:
                num = None
            # O HTML trouxe o recuo visual da primeira linha; o de verdade vem do JSON.
            ed.trocar(b, num, nivel, {"primeira": float(real)} if real is not None else None)


def converter_listas_coladas(editor, inicio: int, fim: int) -> None:
    """HTML colado de outro programa traz QTextList (<ol>, <ul>): vira lista do EditDoc, com o
    marcador ou o numero pintados como os outros (o QTextList sairia com o desenho do Qt)."""
    from PySide6.QtGui import QTextListFormat
    marcas = (QTextListFormat.Style.ListDisc, QTextListFormat.Style.ListCircle,
              QTextListFormat.Style.ListSquare)
    formatos = {QTextListFormat.Style.ListLowerAlpha: "letra_minuscula",
                QTextListFormat.Style.ListUpperAlpha: "letra_maiuscula",
                QTextListFormat.Style.ListLowerRoman: "romano_minusculo",
                QTextListFormat.Style.ListUpperRoman: "romano_maiusculo"}
    doc = editor.document()
    itens = []
    bloco = doc.findBlock(inicio)
    while bloco.isValid() and bloco.position() <= fim:
        lista = bloco.textList()
        if lista is not None and pl.lista_do_bloco(bloco.blockFormat())[0] is None:
            fmt = lista.format()
            itens.append((bloco, lista.objectIndex(), fmt.style(),
                          max(0, min(fmt.indent() - 1, mod.NIVEIS - 1))))
        bloco = bloco.next()
    if not itens:
        return
    with _Edicao(editor) as ed:
        nums: dict[int, int] = {}
        for bloco, chave, estilo, nivel in itens:
            if chave not in nums:
                if estilo in marcas:
                    abstrata = ed.cat.adicionar_abstrata(mod.niveis_de_marcadores(
                        {marcas[1]: "vazado", marcas[2]: "quadrado"}.get(estilo, "redondo")))
                    nums[chave] = ed.cat.instancia_simples(abstrata.id).id
                else:
                    abstrata = ed.cat.adicionar_abstrata(mod.niveis_de_numeracao(
                        formatos.get(estilo, "decimal_ponto")))
                    nums[chave] = ed.cat.adicionar_instancia(
                        abstrata.id, (mod.Sobrescrita(ilvl=0, inicio=1),)).id
        for bloco, _chave, _estilo, _nivel in itens:
            # Fora do QTextList (o que QTextList.remove faz), sem guardar o objeto do Qt.
            bf = QTextBlockFormat(bloco.blockFormat())
            bf.setObjectIndex(-1)
            bf.clearProperty(QTextFormat.Property.BlockIndent)
            QTextCursor(bloco).setBlockFormat(bf)
        for bloco, chave, _estilo, nivel in itens:
            ed.trocar(bloco, nums[chave], nivel)
