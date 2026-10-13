"""Modelo -> QTextDocument. Preenche o documento existente, sem criar outro.

Tri-state: propriedade ausente no modelo (None) nao e' gravada no Qt, e o
`hasProperty` na volta distingue ausente de falso. Sublinhado limpa com
`NoUnderline`, explicito; texto inserido sem formato herda o vizinho.

Quebra de linha interna: "\n" no modelo vira U+2028 no Qt, e volta a "\n".
Listas: cada grupo contiguo de marcadores ou de numeracao vira um QTextList.

Tabelas (M4): cada `Tabela` vira um QTextTable com borda colapsada, largura fixa
por coluna e as mesclas do modelo (gridSpan e vMerge viram columnSpan e rowSpan).
O Qt exige um bloco antes e depois de cada tabela; o bloco que o modelo nao tem
(tabela no comeco do documento ou da celula, duas tabelas seguidas) leva a marca
PROP_ESTRUTURAL e, vazio, nao volta para o modelo. O que o Qt nao guarda (bordas
do arquivo, sombreamento, altura da linha) vai em propriedades de usuario do
formato, em JSON, e volta igual.

Imagens (M4): o run de imagem vira o caractere de objeto com QTextImageFormat; os
bytes ficam no registro de `imagens.py`.

Campos (M5): o run de campo vira o caractere de objeto com o formato de campo de
`campos.py`, que o manipulador do layout pinta com o numero da pagina.

Objetos opacos (0.1.2): o run de objeto vira o caractere de objeto com o formato de
`opacos.py`; o XML e as partes ficam no registro de la'.

Estilos (M6): o formato do Qt recebe o efetivo, estilo resolvido (cadeia basedOn) mais a
formatacao direta do modelo, e o id do estilo numa propriedade de usuario
(`ponte_qt/estilos.py`). O catalogo vai para o documento (`definir_catalogo_base`).
"""

from __future__ import annotations

import json
from dataclasses import asdict

from PySide6.QtCore import Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextFormat, QTextFrameFormat, QTextLength,
                           QTextListFormat, QTextTable, QTextTableCellFormat, QTextTableFormat)

from editdoc.modelo.documento import (Borda, BordasCelula, BordasTabela, Celula, Documento,
                                      Paragrafo, Tabela, bordas_padrao)
from editdoc.modelo.estilos import CAMPOS_CARACTERE, CAMPOS_PARAGRAFO, NIVEL_CORPO
from editdoc.modelo.unidades import px_de_emu, px_de_oitavos_pt, px_de_twips
from editdoc.ponte_qt import campos, imagens, opacos
from editdoc.ponte_qt import estilos as pq_estilos

LINHA_SEPARADORA = chr(0x2028)

_USUARIO = QTextFormat.Property.UserProperty.value
#: Formato da tabela: o que o Qt nao guarda da Tabela (JSON).
PROP_TABELA = _USUARIO + 1
#: Formato da celula: bordas, sombreamento e alinhamento da Celula, e a altura da linha (JSON).
PROP_CELULA = _USUARIO + 2
#: Formato do bloco: bloco que o Qt exige e o modelo nao tem (ver o topo do modulo).
PROP_ESTRUTURAL = _USUARIO + 3

#: Margem interna padrao da celula no Word (tblCellMar do "Normal Table"): 108 twips.
MARGEM_CELULA_PADRAO_TW = (0, 108, 0, 108)

_ALINHAMENTO = {
    "esquerda": Qt.AlignmentFlag.AlignLeft,
    "centro": Qt.AlignmentFlag.AlignHCenter,
    "direita": Qt.AlignmentFlag.AlignRight,
    "justificado": Qt.AlignmentFlag.AlignJustify,
}
_VALIGN = {
    "topo": QTextCharFormat.VerticalAlignment.AlignTop,
    "centro": QTextCharFormat.VerticalAlignment.AlignMiddle,
    "base": QTextCharFormat.VerticalAlignment.AlignBottom,
}
_ESTILO_BORDA = {
    "simples": QTextFrameFormat.BorderStyle.BorderStyle_Solid,
    "dupla": QTextFrameFormat.BorderStyle.BorderStyle_Double,
    "pontilhada": QTextFrameFormat.BorderStyle.BorderStyle_Dotted,
    "tracejada": QTextFrameFormat.BorderStyle.BorderStyle_Dashed,
    "nenhuma": QTextFrameFormat.BorderStyle.BorderStyle_None,
}
_PROPORCIONAL = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value


def _formato_de_run(r) -> QTextCharFormat:
    cf = QTextCharFormat()
    if r.negrito is not None:
        cf.setFontWeight(QFont.Weight.Bold if r.negrito else QFont.Weight.Normal)
    if r.italico is not None:
        cf.setFontItalic(r.italico)
    if r.sublinhado is not None:
        cf.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline if r.sublinhado
                             else QTextCharFormat.UnderlineStyle.NoUnderline)
    if r.tachado is not None:
        cf.setFontStrikeOut(r.tachado)
    if r.subscrito is not None or r.sobrescrito is not None:
        if r.subscrito:
            va = QTextCharFormat.VerticalAlignment.AlignSubScript
        elif r.sobrescrito:
            va = QTextCharFormat.VerticalAlignment.AlignSuperScript
        else:
            va = QTextCharFormat.VerticalAlignment.AlignNormal
        cf.setVerticalAlignment(va)
    if r.tamanho_meio_pt is not None:
        cf.setFontPointSize(r.tamanho_meio_pt / 2)
    if r.fonte:
        cf.setFontFamilies([r.fonte])
    if r.cor_hex is not None:
        cf.setForeground(QBrush(QColor("#" + r.cor_hex)))
    return cf


def formato_estrutural() -> QTextBlockFormat:
    bf = QTextBlockFormat()
    bf.setProperty(PROP_ESTRUTURAL, True)
    return bf


# -- imagens --------------------------------------------------------------------

def inserir_imagem(cursor: QTextCursor, imagem) -> None:
    """Insere o run de imagem do modelo no cursor, com o recurso no documento."""
    nome = imagens.registrar(imagem.dados, imagem.formato)
    imagens.adicionar_recurso(cursor.document(), nome)
    cursor.insertImage(imagens.formato_de_imagem(
        nome, px_de_emu(imagem.largura_emu), px_de_emu(imagem.altura_emu), imagem.descricao))


# -- bordas -----------------------------------------------------------------------

def _json_borda(borda: Borda | None):
    return None if borda is None else asdict(borda)


def _borda_de_json(dado) -> Borda | None:
    return None if dado is None else Borda(**dado)


def json_da_tabela(tabela: Tabela) -> str:
    return json.dumps({
        "bordas": None if tabela.bordas is None else
        {c: _json_borda(getattr(tabela.bordas, c))
         for c in ("sup", "inf", "esq", "dir", "horizontal", "vertical")},
        "alinhamento": tabela.alinhamento,
        "recuo_tw": tabela.recuo_tw,
        "largura": list(tabela.largura) if tabela.largura is not None else None,
        "layout_fixo": tabela.layout_fixo,
        "margens_celula_tw": list(tabela.margens_celula_tw)
        if tabela.margens_celula_tw is not None else None,
    }, sort_keys=True)


def json_da_celula(celula: Celula, linha=None) -> str:
    dado = {
        "bordas": None if celula.bordas is None else
        {c: _json_borda(getattr(celula.bordas, c)) for c in ("sup", "inf", "esq", "dir")},
        "sombreamento_hex": celula.sombreamento_hex,
        "alinhamento_vertical": celula.alinhamento_vertical,
    }
    if linha is not None:
        dado["altura_tw"] = linha.altura_tw
        dado["altura_exata"] = linha.altura_exata
    return json.dumps(dado, sort_keys=True)


def ler_json(fmt: QTextFormat, prop: int) -> dict:
    """O JSON de uma propriedade de usuario; {} se ausente ou invalido."""
    if not fmt.hasProperty(prop):
        return {}
    try:
        dado = json.loads(str(fmt.property(prop)))
    except (ValueError, TypeError):
        return {}
    return dado if isinstance(dado, dict) else {}


def bordas_da_tabela_em(fmt: QTextFormat) -> BordasTabela:
    dado = ler_json(fmt, PROP_TABELA).get("bordas")
    if not isinstance(dado, dict):
        return bordas_padrao()
    try:
        return BordasTabela(**{k: _borda_de_json(v) for k, v in dado.items()})
    except TypeError:
        return bordas_padrao()


def bordas_da_celula_em(fmt: QTextFormat) -> BordasCelula | None:
    dado = ler_json(fmt, PROP_CELULA).get("bordas")
    if not isinstance(dado, dict):
        return None
    try:
        return BordasCelula(**{k: _borda_de_json(v) for k, v in dado.items()})
    except TypeError:
        return None


def margens_da_tabela_em(fmt: QTextFormat) -> tuple[int, int, int, int]:
    dado = ler_json(fmt, PROP_TABELA).get("margens_celula_tw")
    if isinstance(dado, list) and len(dado) == 4 and all(isinstance(x, int) for x in dado):
        return tuple(dado)
    return MARGEM_CELULA_PADRAO_TW


def _aplicar_borda(fmt: QTextTableCellFormat, lado: str, borda: Borda | None) -> None:
    if borda is None or borda.estilo == "nenhuma":
        largura, estilo, cor = 0.0, QTextFrameFormat.BorderStyle.BorderStyle_None, QColor(0, 0, 0)
    else:
        largura = max(px_de_oitavos_pt(borda.oitavos_pt), 0.5)
        if borda.estilo == "dupla":
            largura = max(largura * 3, 2.0)  # o Qt desenha a dupla dentro da espessura
        estilo = _ESTILO_BORDA[borda.estilo]
        cor = QColor("#" + borda.cor_hex) if borda.cor_hex else QColor(0, 0, 0)
    getattr(fmt, f"set{lado}Border")(largura)
    getattr(fmt, f"set{lado}BorderStyle")(estilo)
    getattr(fmt, f"set{lado}BorderBrush")(QBrush(cor))


def aplicar_formatos_das_celulas(tabela: QTextTable) -> None:
    """Refaz o desenho das bordas e das margens de todas as celulas.

    A borda de um lado depende da posicao da celula (beirada da tabela usa a borda
    de fora; o meio usa a de dentro) e da borda propria da celula. Inserir, excluir
    ou mesclar muda posicoes: quem muda a grade chama isto, no mesmo passo de desfazer.
    """
    tf = tabela.format()
    bordas = bordas_da_tabela_em(tf)
    sup, esq, inf, dir_ = (px_de_twips(v) for v in margens_da_tabela_em(tf))
    linhas, colunas = tabela.rows(), tabela.columns()
    for r in range(linhas):
        for c in range(colunas):
            celula = tabela.cellAt(r, c)
            if celula.row() != r or celula.column() != c:
                continue
            fmt = celula.format().toTableCellFormat()
            propria = bordas_da_celula_em(fmt) or BordasCelula()
            fim_r = r + celula.rowSpan() >= linhas
            fim_c = c + celula.columnSpan() >= colunas
            _aplicar_borda(fmt, "Top", propria.sup or (bordas.sup if r == 0 else bordas.horizontal))
            _aplicar_borda(fmt, "Bottom", propria.inf or (bordas.inf if fim_r else bordas.horizontal))
            _aplicar_borda(fmt, "Left", propria.esq or (bordas.esq if c == 0 else bordas.vertical))
            _aplicar_borda(fmt, "Right", propria.dir or (bordas.dir if fim_c else bordas.vertical))
            fmt.setTopPadding(sup)
            fmt.setLeftPadding(esq)
            fmt.setBottomPadding(inf)
            fmt.setRightPadding(dir_)
            celula.setFormat(fmt)


def formato_da_celula(celula: Celula, linha=None) -> QTextTableCellFormat:
    fmt = QTextTableCellFormat()
    if celula.sombreamento_hex is not None:
        fmt.setBackground(QBrush(QColor("#" + celula.sombreamento_hex)))
    if celula.alinhamento_vertical is not None:
        fmt.setVerticalAlignment(_VALIGN[celula.alinhamento_vertical])
    fmt.setProperty(PROP_CELULA, json_da_celula(celula, linha))
    return fmt


def formato_da_tabela(tabela: Tabela) -> QTextTableFormat:
    tf = QTextTableFormat()
    tf.setBorderCollapse(True)
    tf.setBorder(0)
    tf.setCellSpacing(0)
    tf.setCellPadding(0)
    tf.setMargin(0)
    tf.setColumnWidthConstraints([QTextLength(QTextLength.Type.FixedLength, px_de_twips(w))
                                  for w in tabela.colunas_tw])
    if tabela.alinhamento is not None:
        tf.setAlignment(_ALINHAMENTO[tabela.alinhamento])
    if tabela.recuo_tw:
        tf.setLeftMargin(px_de_twips(max(0, tabela.recuo_tw)))
    cabecalho = 0
    for linha in tabela.linhas:
        if not linha.cabecalho:
            break
        cabecalho += 1
    tf.setHeaderRowCount(cabecalho)
    tf.setProperty(PROP_TABELA, json_da_tabela(tabela))
    return tf


# -- insercao ---------------------------------------------------------------------

class _Listas:
    """Grupo de lista contiguo, dentro de um mesmo conteiner (corpo ou celula)."""

    def __init__(self) -> None:
        self.lista = None
        self.estilo = None

    def encerrar(self) -> None:
        self.lista = self.estilo = None

    def aplicar(self, cursor: QTextCursor, numeracao: str | None) -> None:
        if numeracao is None:
            self.encerrar()
            return
        estilo = (QTextListFormat.Style.ListDisc if numeracao == "marcadores"
                  else QTextListFormat.Style.ListDecimal)
        if self.lista is None or estilo != self.estilo:
            formato = QTextListFormat()
            formato.setStyle(estilo)
            self.lista = cursor.createList(formato)
            self.estilo = estilo
        else:
            self.lista.add(cursor.block())


def _formato_do_bloco(p: Paragrafo, res: pq_estilos.Resolvedor,
                      em_tabela: bool = False) -> QTextBlockFormat:
    """Estilo resolvido + formatacao direta do paragrafo, e o id do estilo."""
    base, _car = res.paragrafo(p.estilo, em_tabela)
    proprio = {k: getattr(p, k) for k in CAMPOS_PARAGRAFO if getattr(p, k) is not None}
    efetivo = {**base, **proprio}
    if p.nivel is not None:
        if p.nivel >= NIVEL_CORPO:
            efetivo.pop("nivel", None)  # corpo de texto, mesmo num estilo de titulo
        else:
            efetivo["nivel"] = p.nivel
    bf = QTextBlockFormat()
    pq_estilos.aplicar_bloco(bf, efetivo)
    if p.quebra_antes:
        bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
    pq_estilos.marcar_estilo(bf, p.estilo, res.estilos)
    return bf


def _formato_do_run(r, sid_par: str | None, res: pq_estilos.Resolvedor) -> QTextCharFormat:
    base = res.caractere(sid_par, r.estilo)
    if not base and not r.estilo:
        return _formato_de_run(r)
    proprio = {k: getattr(r, k) for k in CAMPOS_CARACTERE if getattr(r, k) is not None}
    return pq_estilos.formato_de_caractere({**base, **proprio}, r.estilo)


def _escrever_paragrafo(cursor: QTextCursor, p: Paragrafo, listas: _Listas,
                        res: pq_estilos.Resolvedor) -> None:
    cursor.setBlockFormat(_formato_do_bloco(p, res, cursor.currentTable() is not None))
    base = res.caractere(p.estilo, None)
    if base:
        # Bloco vazio: a altura da linha e o texto digitado nele seguem o estilo.
        cursor.setBlockCharFormat(pq_estilos.formato_de_caractere(base))
    for r in p.runs:
        if r.imagem is not None:
            inserir_imagem(cursor, r.imagem)
        elif r.objeto is not None:
            opacos.inserir(cursor, r.objeto, _formato_do_run(r, p.estilo, res))
        elif r.campo is not None:
            campos.inserir_campo(cursor, r.campo, r.texto, _formato_do_run(r, p.estilo, res))
        elif r.texto:
            cursor.insertText(r.texto.replace("\n", LINHA_SEPARADORA),
                              _formato_do_run(r, p.estilo, res))
    listas.aplicar(cursor, p.numeracao)


def _inserir_blocos(cursor: QTextCursor, blocos: list, listas: _Listas,
                    res: pq_estilos.Resolvedor) -> None:
    """Escreve os blocos a partir do cursor, que esta' num bloco vazio, o primeiro do conteiner.

    O Qt poe a tabela depois do bloco do cursor, e cria um bloco vazio depois dela. O
    bloco antes da tabela que o modelo nao tem e' marcado como estrutural.
    """
    primeiro = True
    depois_de_tabela = False
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            if primeiro or depois_de_tabela:
                cursor.setBlockFormat(formato_estrutural())
            listas.encerrar()
            tabela = inserir_tabela_modelo(cursor, bloco, res)
            cursor.setPosition(tabela.lastPosition() + 1)
            cursor.setBlockFormat(QTextBlockFormat())
            cursor.setCharFormat(QTextCharFormat())
            depois_de_tabela = True
        else:
            if not primeiro and not depois_de_tabela:
                cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())
            _escrever_paragrafo(cursor, bloco, listas, res)
            depois_de_tabela = False
        primeiro = False
    if depois_de_tabela:
        # Tabela no fim do conteiner: o bloco que o Qt pos depois dela nao esta' no modelo.
        cursor.setBlockFormat(formato_estrutural())


def inserir_tabela_modelo(cursor: QTextCursor, tabela: Tabela,
                          res: pq_estilos.Resolvedor | None = None) -> QTextTable:
    """Insere a Tabela do modelo depois do bloco do cursor (o Qt parte o bloco no cursor)."""
    if res is None:
        res = pq_estilos.Resolvedor(pq_estilos.catalogo(cursor.document()))
    linhas = len(tabela.linhas)
    colunas = max(1, len(tabela.colunas_tw))
    if len(tabela.colunas_tw) != colunas:
        tabela.colunas_tw = [9026 // colunas] * colunas
    qt = cursor.insertTable(max(1, linhas), colunas, formato_da_tabela(tabela))
    # Onde comeca cada celula do modelo: (linha, coluna da grade) -> (celula, colunas)
    inicio: dict[tuple[int, int], tuple[Celula, int]] = {}
    for r, linha in enumerate(tabela.linhas):
        c = 0
        for celula in linha.celulas:
            if c >= colunas:
                break
            span = min(max(1, celula.colunas), colunas - c)
            inicio[(r, c)] = (celula, span)
            c += span
    # Mescla vertical: "inicio" absorve as "continua" logo abaixo, de mesma largura.
    consumidas: set[tuple[int, int]] = set()
    mesclas: list[tuple[int, int, int, int]] = []
    for (r, c), (celula, span) in sorted(inicio.items()):
        if (r, c) in consumidas:
            continue
        altura = 1
        if celula.mescla_vertical == "inicio":
            while True:
                abaixo = inicio.get((r + altura, c))
                if abaixo is None or abaixo[0].mescla_vertical != "continua" or abaixo[1] != span:
                    break
                consumidas.add((r + altura, c))
                altura += 1
        if altura > 1 or span > 1:
            mesclas.append((r, c, altura, span))
    for r, c, altura, span in mesclas:
        qt.mergeCells(r, c, altura, span)
    listas = _Listas()
    for (r, c), (celula, span) in sorted(inicio.items()):
        if (r, c) in consumidas:
            continue
        cel_qt = qt.cellAt(r, c)
        cel_qt.setFormat(formato_da_celula(celula, tabela.linhas[r]))
        cur = cel_qt.firstCursorPosition()
        listas.encerrar()
        _inserir_blocos(cur, celula.blocos, listas, res)
    aplicar_formatos_das_celulas(qt)
    return qt


def preencher_blocos(documento_qt: QTextDocument, blocos: list, estilos=None) -> None:
    """Substitui o conteudo pelos blocos (cabecalho ou rodape). Limpa o desfazer.

    Sem `estilos`, usa o catalogo do documento (o do corpo, no cabecalho).
    """
    documento_qt.clear()
    if estilos is None:
        estilos = pq_estilos.catalogo(documento_qt)
    cursor = QTextCursor(documento_qt)
    _inserir_blocos(cursor, blocos, _Listas(), pq_estilos.Resolvedor(estilos))
    documento_qt.clearUndoRedoStacks()
    documento_qt.setModified(False)


def preencher(documento_qt: QTextDocument, modelo: Documento) -> None:
    """Substitui o conteudo de `documento_qt` pelo do modelo. Limpa o desfazer.

    O catalogo de estilos do modelo (ou o padrao) passa a ser o do documento.
    """
    documento_qt.clear()
    pq_estilos.definir_catalogo_base(documento_qt, modelo.estilos)
    res = pq_estilos.Resolvedor(pq_estilos.catalogo(documento_qt))
    cursor = QTextCursor(documento_qt)
    _inserir_blocos(cursor, modelo.paragrafos, _Listas(), res)
    documento_qt.clearUndoRedoStacks()
    documento_qt.setModified(False)
