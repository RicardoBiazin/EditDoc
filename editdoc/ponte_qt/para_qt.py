"""Modelo -> QTextDocument. Preenche o documento existente, sem criar outro.

Tri-state: propriedade ausente no modelo (None) nao e' gravada no Qt, e o
`hasProperty` na volta distingue ausente de falso. Sublinhado limpa com
`NoUnderline`, explicito; texto inserido sem formato herda o vizinho.

Quebra de linha interna: "\n" no modelo vira U+2028 no Qt, e volta a "\n".
Listas (0.1.4): o numId e o ilvl diretos do paragrafo vao para propriedades do bloco, o
catalogo do numbering.xml para o documento, e o numero e' pintado (`ponte_qt/listas.py`).
O QTextList nao e' usado: ele so' conta um nivel e nao tem os formatos do Word.

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

Hiperlinks e marcas (0.1.3): o link vai no formato de caractere de cada run (`links.py`);
a marca de campo ou de marcador vira o caractere de objeto de `marcas.py`.

Propriedades preservadas (0.1.5): os extras do run e do paragrafo (o XML que o modelo nao
representa) vao em propriedades de usuario do formato, com a aparencia que a tela mostra
(`ponte_qt/propriedades.py`).

Estilos (M6): o formato do Qt recebe o efetivo, estilo resolvido (cadeia basedOn) mais a
formatacao direta do modelo, e o id do estilo numa propriedade de usuario
(`ponte_qt/estilos.py`). O catalogo vai para o documento (`definir_catalogo_base`).

Comentarios (0.1.6): as ancoras sao marcas (`marcas.py`); o catalogo vai para o documento
(`ponte_qt/comentarios.py`, `definir_base`).

Secoes (0.1.12): o paragrafo que termina uma secao ganha, no fim, o caractere da quebra de secao
(`ponte_qt/secoes.py`), e a secao vai para o registro do documento; a ultima secao tambem. A
quebra de coluna vira o mesmo objeto, sem largura.

Alteracoes controladas (0.1.13): as revisoes do run vao no formato de caractere e as da marca de
paragrafo no do bloco (`ponte_qt/revisoes.py`); o documento com revisao ganha o realce dos modos
de exibicao, e o w:trackRevisions vira `_controlar_alteracoes` no documento.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from PySide6.QtCore import Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextFormat, QTextFrameFormat, QTextLength,
                           QTextTable, QTextTableCellFormat, QTextTableFormat)

from editdoc.modelo.documento import (Borda, BordasCelula, BordasTabela, Celula, Documento,
                                      Paragrafo, Tabela, bordas_padrao)
from editdoc.modelo.estilos import CAMPOS_CARACTERE, CAMPOS_PARAGRAFO, NIVEL_CORPO
from editdoc.modelo.unidades import px_de_emu, px_de_oitavos_pt, px_de_twips
from editdoc.modelo.numeracao import materializado
from editdoc.ponte_qt import campos, imagens, links, listas, marcas, opacos
from editdoc.ponte_qt import comentarios as pq_comentarios
from editdoc.ponte_qt import notas as pq_notas
from editdoc.modelo.documento import MarcaNota, MarcaQuebra
from editdoc.ponte_qt import secoes as pq_secoes
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import propriedades as pq_props
from editdoc.ponte_qt import revisoes as pq_revisoes

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
    pq_props.aplicar_rpr(cf, getattr(r, "extras", None))
    return cf


def formato_estrutural() -> QTextBlockFormat:
    bf = QTextBlockFormat()
    bf.setProperty(PROP_ESTRUTURAL, True)
    return bf


# -- imagens --------------------------------------------------------------------

def inserir_imagem(cursor: QTextCursor, imagem, link=None, extras=None, run=None) -> None:
    """Insere o run de imagem do modelo no cursor, com o recurso no documento."""
    nome = imagens.nome_recortado(imagens.registrar(imagem.dados, imagem.formato),
                                  getattr(imagem, "recorte", None))
    imagens.adicionar_recurso(cursor.document(), nome)
    fmt = imagens.formato_de_imagem(
        nome, px_de_emu(imagem.largura_emu), px_de_emu(imagem.altura_emu), imagem.descricao)
    if link is not None:
        fmt.setAnchor(True)
        fmt.setAnchorHref(link.href())
        fmt.setProperty(links.PROP_LINK, links.com_link(QTextCharFormat(), link).property(
            links.PROP_LINK))
    if extras:
        # rPr preservado do run da imagem (0.1.5): a borda em volta, por exemplo.
        fmt.setProperty(pq_props.PROP_RPR_EXTRA, extras)
    if run is not None and pq_revisoes.run_revisado(run):
        # Imagem inserida ou excluida (0.1.13).
        pq_revisoes.aplicar_run(fmt, run)
    cursor.insertImage(fmt)


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
        "extras": tabela.extras,
        "estilo": tabela.estilo,
        "mudanca_grade": getattr(tabela, "mudanca_grade", None),
    }, sort_keys=True)


def json_da_celula(celula: Celula, linha=None) -> str:
    dado = {
        "bordas": None if celula.bordas is None else
        {c: _json_borda(getattr(celula.bordas, c)) for c in ("sup", "inf", "esq", "dir")},
        "sombreamento_hex": celula.sombreamento_hex,
        "alinhamento_vertical": celula.alinhamento_vertical,
        "extras": celula.extras,
    }
    if linha is not None:
        dado["altura_tw"] = linha.altura_tw
        dado["altura_exata"] = linha.altura_exata
        dado["extras_linha"] = linha.extras
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
    elif getattr(celula, "fundo_estilo", None):
        # Formatacao condicional do estilo da tabela (0.1.6): so' a aparencia; o JSON (o que
        # volta ao modelo) nao a leva, entao nao vira sombreamento direto ao salvar.
        fmt.setBackground(QBrush(QColor("#" + celula.fundo_estilo)))
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

def _formato_do_bloco(p: Paragrafo, res: pq_estilos.Resolvedor,
                      em_tabela: bool = False) -> QTextBlockFormat:
    """Estilo resolvido (com o recuo do nivel da lista) + formatacao direta do paragrafo, o
    id do estilo e a lista direta."""
    base, _car = res.paragrafo(p.estilo, em_tabela, (p.lista, p.lista_nivel))
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
        # 0.1.22: o paragrafo que so' tem a quebra (w:br type="page") leva a quebra no FIM dele
        # (AlwaysAfter), como o Word: ele fica na pagina de cima. Com quebra de secao no mesmo
        # w:p, ou com texto, a quebra continua antes (AlwaysBefore).
        if not p.runs and p.secao is None:
            bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysAfter)
        else:
            bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
    pq_estilos.marcar_estilo(bf, p.estilo, res.estilos)
    listas.marcar_lista(bf, p.lista, p.lista_nivel)
    # Extras (0.1.5): depois do recuo, de que as tabulacoes contam.
    pq_props.aplicar_ppr(bf, p.extras, p.espacamento_linha_pct is not None)
    if pq_revisoes.paragrafo_revisado(p):
        pq_revisoes.aplicar_paragrafo(bf, p)  # 0.1.13
    return bf


def _formato_do_run(r, sid_par: str | None, res: pq_estilos.Resolvedor) -> QTextCharFormat:
    base = res.caractere(sid_par, r.estilo)
    if not base and not r.estilo:
        cf = _formato_de_run(r)
    else:
        proprio = {k: getattr(r, k) for k in CAMPOS_CARACTERE if getattr(r, k) is not None}
        cf = pq_estilos.formato_de_caractere({**base, **proprio}, r.estilo)
        pq_props.aplicar_rpr(cf, r.extras)
    if pq_revisoes.run_revisado(r):
        pq_revisoes.aplicar_run(cf, r)  # alteracoes controladas (0.1.13)
    return cf


def _escrever_paragrafo(cursor: QTextCursor, p: Paragrafo, res: pq_estilos.Resolvedor) -> None:
    cursor.setBlockFormat(_formato_do_bloco(p, res, cursor.currentTable() is not None))
    base = res.caractere(p.estilo, None)
    if not p.runs and p.extras:
        # 0.1.17: o paragrafo vazio tem a altura da marca de paragrafo (o w:rPr do w:pPr), como
        # no Word; o texto digitado nele tambem a usa.
        from editdoc.ponte_qt import paginacao as pq_paginacao
        marca = pq_paginacao.fonte_da_marca(p.extras, res.estilos)
        if marca:
            base = {**base, **marca}
    if base:
        # Bloco vazio: a altura da linha e o texto digitado nele seguem o estilo.
        cursor.setBlockCharFormat(pq_estilos.formato_de_caractere(base))
    if pq_revisoes.paragrafo_revisado(p) or any(pq_revisoes.run_revisado(r) for r in p.runs):
        cursor.document()._tem_revisoes = True  # 0.1.13: o realce vale depois de preencher
    for r in p.runs:
        if r.imagem is not None:
            inserir_imagem(cursor, r.imagem, r.link, r.extras, r)
        elif isinstance(r.marca, MarcaNota):
            # Nota de rodape ou de fim (0.1.10): a referencia, ou o numero da propria nota.
            pq_notas.inserir(cursor, r.marca, links.com_link(_formato_do_run(r, p.estilo, res),
                                                             r.link))
        elif isinstance(r.marca, MarcaQuebra):
            # Quebra de coluna (0.1.12).
            pq_secoes.inserir_coluna(cursor, _formato_do_run(r, p.estilo, res))
        elif r.marca is not None:
            # Campo ou marcador (0.1.3): a marca leva a formatacao do run (o codigo do campo
            # e o resultado recalculado pelo Word saem com ela).
            marcas.inserir(cursor, r.marca, links.com_link(_formato_do_run(r, p.estilo, res), r.link))
        elif r.objeto is not None:
            opacos.inserir(cursor, r.objeto,
                           links.com_link(_formato_do_run(r, p.estilo, res), r.link))
        elif r.campo is not None:
            campos.inserir_campo(cursor, r.campo, r.texto,
                                 links.com_link(_formato_do_run(r, p.estilo, res), r.link))
        elif r.texto:
            cursor.insertText(r.texto.replace("\n", LINHA_SEPARADORA),
                              links.com_link(_formato_do_run(r, p.estilo, res), r.link))
    if p.secao is not None and cursor.currentTable() is None and \
            getattr(cursor.document(), "_corpo_com_secoes", False):
        # Quebra de secao (0.1.12): o ultimo caractere do paragrafo, com o formato do texto do
        # fim (a linha vazia da quebra fica com a altura do paragrafo).
        pq_secoes.inserir_secao(cursor, p.secao, QTextCharFormat(cursor.charFormat()))


def _inserir_blocos(cursor: QTextCursor, blocos: list, res: pq_estilos.Resolvedor) -> None:
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
            tabela = inserir_tabela_modelo(cursor, bloco, res)
            cursor.setPosition(tabela.lastPosition() + 1)
            cursor.setBlockFormat(QTextBlockFormat())
            cursor.setCharFormat(QTextCharFormat())
            depois_de_tabela = True
        else:
            if not primeiro and not depois_de_tabela:
                cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())
            _escrever_paragrafo(cursor, bloco, res)
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
    for (r, c), (celula, span) in sorted(inicio.items()):
        if (r, c) in consumidas:
            continue
        cel_qt = qt.cellAt(r, c)
        cel_qt.setFormat(formato_da_celula(celula, tabela.linhas[r]))
        cur = cel_qt.firstCursorPosition()
        _inserir_blocos(cur, celula.blocos, res)
    aplicar_formatos_das_celulas(qt)
    if _tabela_revisada(tabela):
        # 0.1.14: tabela so' com revisao de propriedades, de linha ou de celula (sem texto
        # revisado) tambem entra na lista de alteracoes.
        cursor.document()._tem_revisoes = True
    return qt


def _tabela_revisada(tabela: Tabela) -> bool:
    from editdoc.formato_docx import revisoes as fx_revisoes
    if getattr(tabela, "mudanca_grade", None) or fx_revisoes.tem_revisao(tabela.extras):
        return True
    return any(fx_revisoes.tem_revisao(linha.extras)
               or any(fx_revisoes.tem_revisao(c.extras) for c in linha.celulas)
               for linha in tabela.linhas)


def preencher_blocos(documento_qt: QTextDocument, blocos: list, estilos=None) -> None:
    """Substitui o conteudo pelos blocos (cabecalho ou rodape). Limpa o desfazer.

    Sem `estilos`, usa o catalogo do documento (o do corpo, no cabecalho).
    """
    documento_qt.clear()
    _reiniciar_flutuantes(documento_qt, None)
    if estilos is None:
        estilos = pq_estilos.catalogo(documento_qt)
    cursor = QTextCursor(documento_qt)
    _inserir_blocos(cursor, blocos, pq_estilos.Resolvedor(estilos))
    concluir_listas(documento_qt)
    if pq_revisoes.tem_revisoes(documento_qt):
        pq_revisoes.marcar_revisado(documento_qt)


def _reiniciar_flutuantes(documento_qt: QTextDocument, pagina) -> None:
    """Objetos flutuantes (0.1.7): o clear() apagou os frames; a pagina decide o lado do
    texto ao abrir (`flutuantes.lado_inicial`)."""
    if pagina is not None or not hasattr(documento_qt, "_pagina_flutuantes"):
        try:
            documento_qt._pagina_flutuantes = pagina
        except AttributeError:
            pass
    from editdoc.ponte_qt import flutuantes
    g = flutuantes.gerente_se_houver(documento_qt)
    if g is not None:
        g.reiniciar()


def preencher(documento_qt: QTextDocument, modelo: Documento) -> None:
    """Substitui o conteudo de `documento_qt` pelo do modelo. Limpa o desfazer.

    O catalogo de estilos do modelo (ou o padrao) passa a ser o do documento.
    """
    documento_qt.clear()
    _reiniciar_flutuantes(documento_qt, modelo.pagina)
    # Secoes (0.1.12): registro novo; a ultima secao com o tipo, os extras e os cabecalhos dela.
    pq_secoes.limpar(documento_qt)
    final = pq_secoes.sem_conteudo(getattr(modelo, "secao", None) or pq_secoes.Secao())
    final.pagina = modelo.pagina
    documento_qt._secao_final = final
    documento_qt._corpo_com_secoes = True
    # Alteracoes controladas (0.1.13): o w:trackRevisions do settings.xml.
    documento_qt._controlar_alteracoes = bool(getattr(modelo, "controlar_alteracoes", False))
    # Lista dada so' pelo tipo (documento montado em codigo): os numIds do escritor (0.1.4).
    modelo = materializado(modelo)
    listas.definir_catalogo_base(documento_qt, modelo.numeracao)
    pq_estilos.definir_catalogo_base(documento_qt, modelo.estilos)
    pq_comentarios.definir_base(documento_qt, modelo.comentarios)
    pq_notas.definir_base(documento_qt, getattr(modelo, "notas", None))
    res = pq_estilos.Resolvedor(pq_estilos.catalogo(documento_qt))
    cursor = QTextCursor(documento_qt)
    _inserir_blocos(cursor, modelo.paragrafos, res)
    # Notas (0.1.10): o numero de cada referencia antes do primeiro plano da pagina.
    documento_qt._numeros_notas = pq_notas.numeros_continuos(documento_qt)
    concluir_listas(documento_qt)
    if any("sectPrChange" in ((x.original or "") + (x.extras or ""))
           for x in [final] + list(pq_secoes.registro(documento_qt).values())):
        documento_qt._tem_revisoes = True  # 0.1.14: so' a revisao da secao tambem conta
    if pq_revisoes.tem_revisoes(documento_qt):
        pq_revisoes.marcar_revisado(documento_qt)  # 0.1.13: o realce do modo de exibicao


def concluir_listas(documento_qt: QTextDocument) -> None:
    """Ao abrir (ou depois de trocar a fonte padrao logo apos abrir): o texto dos itens de
    lista vai para depois do numero, e o documento fica sem desfazer e sem alteracao."""
    numerador = listas.numerador_de(documento_qt)
    numerador.marcar_sujo()
    numerador.larguras.clear()  # mede de novo: a fonte padrao pode ter mudado ao abrir
    listas.ajustar_recuos(documento_qt)
    documento_qt.clearUndoRedoStacks()
    documento_qt.setModified(False)
