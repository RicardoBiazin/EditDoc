"""Comandos de tabela sobre o editor (PainelDocumento, com a API do QTextEdit).

Cada comando e' UM passo de desfazer: a mudanca na grade e o redesenho das bordas
(ver para_qt.aplicar_formatos_das_celulas) ficam no mesmo bloco de edicao.

Medidas medidas no Qt 6.11 antes de escrever isto (docs/SPIKES.md, M4):
  - insertTable no meio de um bloco parte o bloco: o texto antes fica acima da
    tabela, o depois vai para o bloco de baixo, como no Word;
  - remover a tabela inteira funde o bloco de cima com o de baixo. Excluir tabela
    parte de novo o bloco, para nao juntar dois paragrafos;
  - insertRows nao copia o formato da celula; insertColumns copia o da vizinha e
    repete a largura da coluna da esquerda.
"""

from __future__ import annotations

from PySide6.QtGui import QTextCursor, QTextLength, QTextTable, QTextTableCellFormat

from editdoc.modelo.documento import Celula, Linha, Paragrafo, Tabela
from editdoc.modelo.unidades import px_de_twips, twips_de_px
from editdoc.ponte_qt import para_qt

#: Limites da tabela criada pelo usuario: os mesmos do leitor (formato_docx/leitor.py).
LINHAS_MAXIMAS = 2000
COLUNAS_MAXIMAS = 63
CELULAS_MAXIMAS = 5000
#: Largura minima de coluna, em twips (0,2 cm), para a coluna nao sumir.
COLUNA_MINIMA_TW = 113


def tabela_do_cursor(cursor: QTextCursor) -> QTextTable | None:
    return cursor.currentTable()


def _largura_disponivel_tw(editor, cursor: QTextCursor) -> int:
    """Largura para uma tabela nova: o corpo da pagina, ou a celula onde o cursor esta'."""
    corpo = editor.configuracao_pagina().corpo_largura_tw()
    externa = cursor.currentTable()
    if externa is None:
        return corpo
    celula = externa.cellAt(cursor)
    restricoes = externa.format().columnWidthConstraints()
    inicio, span = celula.column(), celula.columnSpan()
    largura = sum(twips_de_px(r.rawValue()) for r in restricoes[inicio:inicio + span])
    margens = para_qt.margens_da_tabela_em(externa.format())
    return max(COLUNA_MINIMA_TW * span, largura - margens[1] - margens[3])


def pode_inserir(linhas: int, colunas: int) -> bool:
    return (1 <= linhas <= LINHAS_MAXIMAS and 1 <= colunas <= COLUNAS_MAXIMAS
            and linhas * colunas <= CELULAS_MAXIMAS)


def inserir_tabela(editor, linhas: int, colunas: int) -> QTextTable | None:
    """Tabela nova no cursor, com as bordas do "Table Grid" e colunas iguais.

    No meio de um paragrafo, parte o paragrafo (como o Word). Se o bloco de cima ficar
    vazio, ele vira estrutural: o arquivo nao ganha um paragrafo vazio antes da tabela.
    """
    if not pode_inserir(linhas, colunas):
        return None
    cursor = editor.textCursor()
    largura = _largura_disponivel_tw(editor, cursor)
    coluna_tw = max(COLUNA_MINIMA_TW, largura // colunas)
    modelo = Tabela(colunas_tw=[coluna_tw] * colunas, layout_fixo=True,
                    linhas=[Linha(celulas=[Celula(blocos=[Paragrafo()]) for _ in range(colunas)])
                            for _ in range(linhas)])
    cursor.beginEditBlock()
    if cursor.hasSelection():
        cursor.removeSelectedText()
    tabela = para_qt.inserir_tabela_modelo(cursor, modelo)
    antes = editor.document().findBlock(tabela.firstPosition() - 1)
    if antes.isValid() and antes.text() == "":
        QTextCursor(antes).mergeBlockFormat(para_qt.formato_estrutural())
    cursor.endEditBlock()
    editor.setTextCursor(tabela.cellAt(0, 0).firstCursorPosition())
    return tabela


def _celula_atual(editor):
    cursor = editor.textCursor()
    tabela = cursor.currentTable()
    if tabela is None:
        return None, None, cursor
    return tabela, tabela.cellAt(cursor), cursor


def _faixa_selecionada(cursor: QTextCursor, tabela: QTextTable, celula) -> tuple[int, int, int, int]:
    """(linha, n de linhas, coluna, n de colunas) da selecao de celulas, ou da celula atual."""
    if cursor.hasComplexSelection():
        r, n_r, c, n_c = cursor.selectedTableCells()
        if n_r > 0 and n_c > 0:
            return r, n_r, c, n_c
    return celula.row(), celula.rowSpan(), celula.column(), celula.columnSpan()


def _copiar_formato(origem, destino) -> None:
    """Formato de celula do modelo (JSON, fundo, alinhamento) de uma celula para outra."""
    fmt_origem = origem.format().toTableCellFormat()
    fmt = QTextTableCellFormat()
    if fmt_origem.hasProperty(para_qt.PROP_CELULA):
        fmt.setProperty(para_qt.PROP_CELULA, fmt_origem.property(para_qt.PROP_CELULA))
    if fmt_origem.hasProperty(fmt_origem.Property.BackgroundBrush):
        fmt.setBackground(fmt_origem.background())
    if fmt_origem.hasProperty(fmt_origem.Property.TextVerticalAlignment):
        fmt.setVerticalAlignment(fmt_origem.verticalAlignment())
    destino.setFormat(fmt)


def inserir_linha(editor, abaixo: bool) -> bool:
    tabela, celula, cursor = _celula_atual(editor)
    if tabela is None or tabela.rows() >= LINHAS_MAXIMAS \
            or (tabela.rows() + 1) * tabela.columns() > CELULAS_MAXIMAS:
        return False
    r, n_r, _c, _n = _faixa_selecionada(cursor, tabela, celula)
    coluna_atual = celula.column()  # a QTextTableCell fica invalida depois de mexer na grade
    nova = r + n_r if abaixo else r
    # A linha de onde o formato e' copiado: a de cima da nova, ou a que desceu uma posicao.
    linha_ref = r + n_r - 1 if abaixo else r + 1
    cursor.beginEditBlock()
    tabela.insertRows(nova, 1)
    for c in range(tabela.columns()):
        destino = tabela.cellAt(nova, c)
        if destino.row() == nova and destino.column() == c:
            _copiar_formato(tabela.cellAt(linha_ref, c), destino)
    para_qt.aplicar_formatos_das_celulas(tabela)
    cursor.endEditBlock()
    editor.setTextCursor(tabela.cellAt(nova, coluna_atual).firstCursorPosition())
    return True


def acrescentar_linha_no_fim(editor) -> bool:
    """Tab na ultima celula: linha nova no fim, e o cursor vai para a primeira celula dela."""
    tabela, _celula, cursor = _celula_atual(editor)
    if tabela is None:
        return False
    ultima = tabela.cellAt(tabela.rows() - 1, 0)
    cursor.setPosition(ultima.firstCursorPosition().position())
    editor.setTextCursor(cursor)
    if not inserir_linha(editor, abaixo=True):
        return False
    editor.setTextCursor(tabela.cellAt(tabela.rows() - 1, 0).firstCursorPosition())
    return True


def _definir_larguras(tabela: QTextTable, larguras_tw: list[int]) -> None:
    fmt = tabela.format()
    fmt.setColumnWidthConstraints([QTextLength(QTextLength.Type.FixedLength, px_de_twips(w))
                                   for w in larguras_tw])
    tabela.setFormat(fmt)


def _larguras_tw(tabela: QTextTable) -> list[int]:
    restricoes = tabela.format().columnWidthConstraints()
    larguras = [twips_de_px(r.rawValue()) if r.type() == QTextLength.Type.FixedLength else 0
                for r in restricoes]
    while len(larguras) < tabela.columns():
        larguras.append(0)
    media = round(sum(larguras) / max(1, sum(1 for w in larguras if w))) if any(larguras) else 2000
    return [w or media for w in larguras[:tabela.columns()]]


def inserir_coluna(editor, direita: bool) -> bool:
    """Coluna nova; as larguras sao reduzidas na proporcao para a tabela nao crescer."""
    tabela, celula, cursor = _celula_atual(editor)
    if tabela is None or tabela.columns() >= COLUNAS_MAXIMAS \
            or tabela.rows() * (tabela.columns() + 1) > CELULAS_MAXIMAS:
        return False
    _r, _n, c, n_c = _faixa_selecionada(cursor, tabela, celula)
    linha_atual = celula.row()  # a QTextTableCell fica invalida depois de mexer na grade
    larguras = _larguras_tw(tabela)
    total = sum(larguras)
    nova = c + n_c if direita else c
    referencia = c + n_c - 1 if direita else c
    cursor.beginEditBlock()
    tabela.insertColumns(nova, 1)
    larguras.insert(nova, larguras[referencia])
    escala = total / sum(larguras)
    _definir_larguras(tabela, [max(COLUNA_MINIMA_TW, round(w * escala)) for w in larguras])
    para_qt.aplicar_formatos_das_celulas(tabela)
    cursor.endEditBlock()
    editor.setTextCursor(tabela.cellAt(linha_atual, nova).firstCursorPosition())
    return True


def _controle(editor) -> bool:
    from editdoc.edicao import revisoes as ed_revisoes
    try:
        return ed_revisoes.controle_ligado(editor)
    except (AttributeError, RuntimeError):
        return False


def _marcar_celula(editor, tabela: QTextTable, r: int, c: int, chave: str, recipiente: str,
                   tipo: str) -> None:
    """Poe a marca `tipo` (w:del da linha ou w:cellDel da celula) no JSON da celula (chave
    "extras_linha" ou "extras") e marca o texto dela como excluido (0.1.14)."""
    import json
    from editdoc.edicao import revisoes as ed_revisoes
    from editdoc.formato_docx import revisoes as fx_revisoes
    celula = tabela.cellAt(r, c)
    fmt = celula.format().toTableCellFormat()
    dado = para_qt.ler_json(fmt, para_qt.PROP_CELULA)
    atual = dado.get(chave) if isinstance(dado.get(chave), str) else None
    dado[chave] = fx_revisoes.com_marca(atual, recipiente, ed_revisoes.nova(editor, tipo))
    fmt.setProperty(para_qt.PROP_CELULA, json.dumps(dado, sort_keys=True))
    celula.setFormat(fmt)
    from editdoc.ponte_qt import revisoes as pq_revisoes
    pq_revisoes.marcar_revisado(tabela.document())
    tabela.document()._lista_revisoes = None
    a = celula.firstCursorPosition().position()
    b = celula.lastCursorPosition().position()
    if b > a:
        ed_revisoes.apagar_intervalo(editor, tabela.document(), a, b)


def _inserida_pelo_autor(editor, extras: str | None, nome: str) -> bool:
    """A linha (w:ins no trPr) ou a celula (w:cellIns) foi inserida pelo proprio autor, com o
    controle ligado, e ainda nao aceita: excluir a remove de verdade (como o texto)."""
    from editdoc.edicao import revisoes as ed_revisoes
    from editdoc.formato_docx import revisoes as fx_revisoes
    from editdoc.formato_docx.nomes import q
    el = fx_revisoes.elemento_canonico(extras)
    marca = el.find(q(nome)) if el is not None else None
    return marca is not None and (marca.get(q("author")) or "") == ed_revisoes.autor(editor)


def _excluir_linhas_rastreando(editor, tabela: QTextTable, r: int, n_r: int,
                               cursor: QTextCursor) -> bool:
    """Excluir linha com o controle ligado (0.1.14): a linha fica, com w:del no w:trPr e o texto
    das celulas excluido, como no Word. A linha que o proprio autor inseriu sai de verdade."""
    cursor.beginEditBlock()
    try:
        for linha in reversed(range(r, r + n_r)):
            dado = para_qt.ler_json(tabela.cellAt(linha, 0).format(), para_qt.PROP_CELULA)
            extras = dado.get("extras_linha") if isinstance(dado.get("extras_linha"), str) else None
            if _inserida_pelo_autor(editor, extras, "ins"):
                if tabela.rows() > 1:
                    tabela.removeRows(linha, 1)
                continue
            for c in range(tabela.columns()):
                cel = tabela.cellAt(linha, c)
                if cel.row() == linha and cel.column() == c:
                    _marcar_celula(editor, tabela, linha, c, "extras_linha", "trPr", "del")
        para_qt.aplicar_formatos_das_celulas(tabela)
    finally:
        cursor.endEditBlock()
    editor.setTextCursor(tabela.cellAt(min(r, tabela.rows() - 1), 0).firstCursorPosition())
    return True


def _excluir_colunas_rastreando(editor, tabela: QTextTable, c: int, n_c: int,
                                linha_atual: int, cursor: QTextCursor) -> bool:
    """Excluir coluna com o controle ligado (0.1.14): as celulas ficam, com w:cellDel no w:tcPr
    e o texto excluido. A coluna que o proprio autor inseriu (todas as celulas com w:cellIns
    dele) sai de verdade."""
    larguras = _larguras_tw(tabela)
    cursor.beginEditBlock()
    try:
        for col in reversed(range(c, c + n_c)):
            todas_dele = all(_inserida_pelo_autor(
                editor, para_qt.ler_json(tabela.cellAt(x, col).format(),
                                         para_qt.PROP_CELULA).get("extras"), "cellIns")
                for x in range(tabela.rows()))
            if todas_dele and tabela.columns() > 1:
                tabela.removeColumns(col, 1)
                del larguras[col]
                _definir_larguras(tabela, larguras)
                continue
            for x in range(tabela.rows()):
                cel = tabela.cellAt(x, col)
                if cel.row() == x and cel.column() == col:
                    _marcar_celula(editor, tabela, x, col, "extras", "tcPr", "cellDel")
        para_qt.aplicar_formatos_das_celulas(tabela)
    finally:
        cursor.endEditBlock()
    editor.setTextCursor(tabela.cellAt(linha_atual, min(c, tabela.columns() - 1))
                         .firstCursorPosition())
    return True


def excluir_linhas(editor) -> bool:
    tabela, celula, cursor = _celula_atual(editor)
    if tabela is None:
        return False
    r, n_r, _c, _n = _faixa_selecionada(cursor, tabela, celula)
    if _controle(editor):
        return _excluir_linhas_rastreando(editor, tabela, r, n_r, cursor)
    if n_r >= tabela.rows():
        return excluir_tabela(editor)
    cursor.beginEditBlock()
    tabela.removeRows(r, n_r)
    para_qt.aplicar_formatos_das_celulas(tabela)
    cursor.endEditBlock()
    editor.setTextCursor(tabela.cellAt(min(r, tabela.rows() - 1), 0).firstCursorPosition())
    return True


def excluir_colunas(editor) -> bool:
    tabela, celula, cursor = _celula_atual(editor)
    if tabela is None:
        return False
    _r, _n, c, n_c = _faixa_selecionada(cursor, tabela, celula)
    if _controle(editor):
        return _excluir_colunas_rastreando(editor, tabela, c, n_c, celula.row(), cursor)
    if n_c >= tabela.columns():
        return excluir_tabela(editor)
    linha_atual = celula.row()  # a QTextTableCell fica invalida depois de mexer na grade
    larguras = _larguras_tw(tabela)
    cursor.beginEditBlock()
    tabela.removeColumns(c, n_c)
    del larguras[c:c + n_c]
    _definir_larguras(tabela, larguras)
    para_qt.aplicar_formatos_das_celulas(tabela)
    cursor.endEditBlock()
    editor.setTextCursor(tabela.cellAt(linha_atual, min(c, tabela.columns() - 1))
                         .firstCursorPosition())
    return True


def excluir_tabela(editor) -> bool:
    """Remove a tabela do cursor. Os paragrafos de cima e de baixo continuam separados."""
    tabela, _celula, cursor = _celula_atual(editor)
    if tabela is None:
        return False
    doc = editor.document()
    antes = doc.findBlock(tabela.firstPosition() - 1)
    depois = doc.findBlock(tabela.lastPosition() + 1)
    texto_antes = antes.text()
    formato_depois = depois.blockFormat()
    formato_char_depois = depois.charFormat()
    formato_depois.clearProperty(para_qt.PROP_ESTRUTURAL)
    cursor.beginEditBlock()
    cursor.setPosition(tabela.firstPosition() - 1)
    cursor.setPosition(tabela.lastPosition() + 1, QTextCursor.MoveMode.KeepAnchor)
    cursor.removeSelectedText()
    # O Qt fundiu o bloco de cima com o de baixo, no ponto do cursor.
    if texto_antes == "":
        cursor.setBlockFormat(formato_depois)
    else:
        cursor.insertBlock(formato_depois, formato_char_depois)
    cursor.endEditBlock()
    editor.setTextCursor(cursor)
    return True


def pode_mesclar(cursor: QTextCursor) -> bool:
    if cursor.currentTable() is None or not cursor.hasComplexSelection():
        return False
    _r, n_r, _c, n_c = cursor.selectedTableCells()
    return n_r * n_c > 1


def mesclar_celulas(editor) -> bool:
    tabela, _celula, cursor = _celula_atual(editor)
    if tabela is None or not pode_mesclar(cursor):
        return False
    r, _n_r, c, _n_c = cursor.selectedTableCells()
    cursor.beginEditBlock()
    tabela.mergeCells(cursor)
    para_qt.aplicar_formatos_das_celulas(tabela)
    cursor.endEditBlock()
    editor.setTextCursor(tabela.cellAt(r, c).firstCursorPosition())
    return True


def pode_dividir(cursor: QTextCursor) -> bool:
    tabela = cursor.currentTable()
    if tabela is None:
        return False
    celula = tabela.cellAt(cursor)
    return celula.rowSpan() > 1 or celula.columnSpan() > 1


def dividir_celula(editor) -> bool:
    """Desfaz a mescla da celula do cursor (o Qt so' divide celula mesclada)."""
    tabela, celula, cursor = _celula_atual(editor)
    if tabela is None or not pode_dividir(cursor):
        return False
    r, c = celula.row(), celula.column()
    altura, largura = celula.rowSpan(), celula.columnSpan()
    cursor.beginEditBlock()
    tabela.splitCell(r, c, 1, 1)
    for rr in range(r, r + altura):
        for cc in range(c, c + largura):
            if (rr, cc) != (r, c):
                _copiar_formato(tabela.cellAt(r, c), tabela.cellAt(rr, cc))
    para_qt.aplicar_formatos_das_celulas(tabela)
    cursor.endEditBlock()
    editor.setTextCursor(tabela.cellAt(r, c).firstCursorPosition())
    return True


def tabelas_do_documento(doc) -> list[QTextTable]:
    """Todas as tabelas, inclusive as aninhadas."""
    saida: list[QTextTable] = []
    pilha = [doc.rootFrame()]
    while pilha:
        quadro = pilha.pop()
        for filho in quadro.childFrames():
            if isinstance(filho, QTextTable):
                saida.append(filho)
            pilha.append(filho)
    return saida


def ajustar_tabelas_coladas(editor) -> int:
    """Tabela que entrou por HTML (colar) vira tabela do EditDoc: largura fixa, borda
    colapsada e as bordas do "Table Grid". Sem isto ela aparece com a borda dupla do
    HTML na tela e com a grade simples depois de salvar. Devolve quantas ajustou."""
    from editdoc.ponte_qt import de_qt

    corpo = editor.configuracao_pagina().corpo_largura_tw()
    ajustadas = 0
    for tabela in tabelas_do_documento(editor.document()):
        if tabela.format().hasProperty(para_qt.PROP_TABELA):
            continue
        cabecalho = tabela.format().headerRowCount()
        modelo = Tabela(colunas_tw=de_qt.larguras_tw(tabela, corpo), layout_fixo=True)
        formato = para_qt.formato_da_tabela(modelo)
        formato.setHeaderRowCount(cabecalho)
        tabela.setFormat(formato)
        for r in range(tabela.rows()):
            for c in range(tabela.columns()):
                celula = tabela.cellAt(r, c)
                if celula.row() == r and celula.column() == c and \
                        not celula.format().hasProperty(para_qt.PROP_CELULA):
                    celula.setFormat(para_qt.formato_da_celula(Celula()))
        para_qt.aplicar_formatos_das_celulas(tabela)
        ajustadas += 1
    return ajustadas


def proxima_celula(tabela: QTextTable, celula, para_tras: bool):
    """Celula seguinte (ou anterior) na ordem de leitura; None se nao houver."""
    inicios = [(r, c) for r in range(tabela.rows()) for c in range(tabela.columns())
               if tabela.cellAt(r, c).row() == r and tabela.cellAt(r, c).column() == c]
    atual = inicios.index((celula.row(), celula.column()))
    alvo = atual - 1 if para_tras else atual + 1
    if 0 <= alvo < len(inicios):
        return tabela.cellAt(*inicios[alvo])
    return None
