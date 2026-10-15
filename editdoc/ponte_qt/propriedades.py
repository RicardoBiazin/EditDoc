"""Propriedades preservadas de run e de paragrafo no QTextDocument (0.1.5).

O XML das propriedades que o modelo nao representa (`Run.extras`, `Paragrafo.extras`, ver
`formato_docx/propriedades.py`) vai numa propriedade de usuario do formato: PROP_RPR_EXTRA no
caractere e PROP_PPR_EXTRA no bloco. Como o resto do formato, ele acompanha o texto: o que se
digita herda o formato do vizinho, e o Enter copia o formato do bloco para o paragrafo novo
(o Word faz o mesmo com o rPr e o pPr). O desfazer volta o formato inteiro.

A tela mostra o que for de baixo risco:

- caractere: realce (w:highlight) e sombreamento (w:shd) como fundo, maiusculas (w:caps),
  versalete (w:smallCaps), espacamento entre caracteres (w:spacing), escala (w:w) e a borda
  do trecho (w:bdr, pintada por `desenhar`);
- paragrafo: sombreamento como fundo do bloco, tabulacoes proprias (w:tabs, com o
  preenchimento pintado por `desenhar`), bordas do paragrafo (w:pBdr, pintadas, juntando
  paragrafos vizinhos de mesma borda como o Word) e entrelinha exata ou minima.

Medido no Qt 6.11.2, dispositivo de 1440 dpi: o espacamento absoluto entre letras, a posicao
da tabulacao e a altura fixa da linha sao escalados como px96 (x 15), como a margem vertical;
vao em twips / 15. A tabulacao do Qt conta da posicao da linha (recuo esquerdo, e na primeira
linha tambem o recuo da primeira linha); a do Word, da margem. O EditDoc desconta o recuo
esquerdo; na primeira linha com recuo proprio a tabulacao fica deslocada desse recuo.

Copiar e colar: o HTML do Qt nao leva propriedade de usuario. `dados_para_copiar` poe os
extras dos trechos e dos blocos numa marca propria da area de transferencia, e
`aplicar_colado` os devolve ao que foi colado.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QPen, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextOption)

from editdoc import log_interno
from editdoc.formato_docx.propriedades import (AparenciaParagrafo, aparencia_paragrafo,
                                               aparencia_run)

log = log_interno.obter(__name__)

P = QTextFormat.Property
_USUARIO = P.UserProperty.value
#: Caractere: o w:rPr dos extras (texto). Numero livre (ver CLAUDE.md: o proximo era + 28).
PROP_RPR_EXTRA = _USUARIO + 28
#: Bloco: o w:pPr dos extras (texto).
PROP_PPR_EXTRA = _USUARIO + 29
#: Propriedades do Qt que a aparencia dos extras de caractere ocupa.
PROPS_APARENCIA_CARACTERE = (P.BackgroundBrush, P.FontCapitalization, P.FontLetterSpacing,
                             P.FontLetterSpacingType, P.FontStretch)
#: Propriedades do Qt que a aparencia dos extras de paragrafo ocupa.
PROPS_APARENCIA_BLOCO = (P.BackgroundBrush, P.TabPositions)
_TWIPS_POR_PX96 = 15.0
_FIXA = QTextBlockFormat.LineHeightTypes.FixedHeight.value
_MINIMA = QTextBlockFormat.LineHeightTypes.MinimumHeight.value
_TABS = {"esquerda": QTextOption.TabType.LeftTab, "centro": QTextOption.TabType.CenterTab,
         "direita": QTextOption.TabType.RightTab, "decimal": QTextOption.TabType.DelimiterTab}
_TRACOS = {"simples": Qt.PenStyle.SolidLine, "dupla": Qt.PenStyle.SolidLine,
           "pontilhada": Qt.PenStyle.DotLine, "tracejada": Qt.PenStyle.DashLine}
_PREENCHIMENTOS = {"dot": ".", "middleDot": "·", "hyphen": "-", "underscore": "_",
                   "heavy": "_"}


def _texto(valor) -> str | None:
    # setProperty(prop, "") volta como lista vazia no PySide (CLAUDE.md): so' str conta.
    return valor if isinstance(valor, str) and valor else None


# -- caractere ---------------------------------------------------------------------------

def extras_de_rpr(fmt: QTextFormat) -> str | None:
    return _texto(fmt.property(PROP_RPR_EXTRA))


def tirar_rpr(cf: QTextCharFormat) -> None:
    """Sem extras e sem a aparencia que eles davam (Limpar formatacao)."""
    if not cf.hasProperty(PROP_RPR_EXTRA):
        return
    cf.clearProperty(PROP_RPR_EXTRA)
    for prop in PROPS_APARENCIA_CARACTERE:
        cf.clearProperty(prop)


def aplicar_rpr(cf: QTextCharFormat, extras: str | None) -> None:
    """Os extras no formato, com a aparencia que a tela mostra."""
    if not extras:
        return
    cf.setProperty(PROP_RPR_EXTRA, extras)
    ap = aparencia_run(extras)
    if ap.vazio:
        return
    if ap.fundo:
        cf.setBackground(QBrush(QColor("#" + ap.fundo)))
    if ap.versalete:
        cf.setFontCapitalization(QFont.Capitalization.SmallCaps)
    if ap.maiusculas:
        cf.setFontCapitalization(QFont.Capitalization.AllUppercase)
    if ap.espacamento_tw:
        cf.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
        cf.setFontLetterSpacing(ap.espacamento_tw / _TWIPS_POR_PX96)
    if ap.escala_pct and ap.escala_pct != 100:
        cf.setFontStretch(int(ap.escala_pct))


# -- paragrafo ---------------------------------------------------------------------------

def extras_de_ppr(fmt: QTextFormat) -> str | None:
    return _texto(fmt.property(PROP_PPR_EXTRA))


def tabulacoes(ap: AparenciaParagrafo, recuo_esquerdo_tw: float) -> list:
    """QTextOption.Tab das tabulacoes do paragrafo, contadas do recuo esquerdo (em px96)."""
    saida = []
    for pos, tipo, _preenchimento in ap.tabulacoes:
        if tipo not in _TABS:
            continue  # barra: so' a linha vertical, que a tela nao desenha
        rel = (pos - recuo_esquerdo_tw) / _TWIPS_POR_PX96
        if rel <= 0:
            continue  # antes do recuo: o Word tambem nao para nela
        if tipo == "decimal":
            saida.append(QTextOption.Tab(rel, _TABS[tipo], ","))
        else:
            saida.append(QTextOption.Tab(rel, _TABS[tipo]))
    return saida


def aplicar_ppr(bf: QTextBlockFormat, extras: str | None, linha_direta: bool = False) -> None:
    """Os extras no formato do bloco, com a aparencia que a tela mostra. Chamar depois do
    recuo esquerdo (a tabulacao conta dele). `linha_direta`: o paragrafo tem entrelinha
    proporcional propria, que vence a exata dos extras."""
    if not extras:
        return
    bf.setProperty(PROP_PPR_EXTRA, extras)
    ap = aparencia_paragrafo(extras)
    if ap.vazio:
        return
    if ap.fundo:
        bf.setBackground(QBrush(QColor("#" + ap.fundo)))
    tabs = tabulacoes(ap, bf.leftMargin())
    if tabs:
        bf.setTabPositions(tabs)
    if ap.linha is not None and not linha_direta:
        regra, valor = ap.linha
        bf.setLineHeight(valor / _TWIPS_POR_PX96, _FIXA if regra == "exata" else _MINIMA)


def tirar_ppr(bf: QTextBlockFormat) -> None:
    if not bf.hasProperty(PROP_PPR_EXTRA):
        return
    bf.clearProperty(PROP_PPR_EXTRA)
    for prop in PROPS_APARENCIA_BLOCO:
        bf.clearProperty(prop)


def reajustar_tabulacoes(bf: QTextBlockFormat) -> None:
    """Depois de mudar o recuo esquerdo: as tabulacoes contam de novo a partir dele."""
    extras = extras_de_ppr(bf)
    if not extras:
        return
    tabs = tabulacoes(aparencia_paragrafo(extras), bf.leftMargin())
    if tabs:
        bf.setTabPositions(tabs)


# -- copiar e colar ----------------------------------------------------------------------

def _omitido(cf: QTextCharFormat) -> bool:
    """Caractere de objeto de tipo proprio (objeto opaco, marca, campo): o HTML nao o leva."""
    return cf.objectType() >= QTextFormat.ObjectTypes.UserObject.value


def dados_para_copiar(doc: QTextDocument, inicio: int, fim: int) -> dict | None:
    """Os extras de [inicio, fim), em posicoes do texto que o HTML leva (sem os objetos de
    tipo proprio, que o colar nao recebe). None se nao ha' extras."""
    trechos: list = []
    blocos: list = []
    omitidos = 0
    bloco = doc.findBlock(inicio)
    total = 0
    while bloco.isValid() and bloco.position() <= max(inicio, fim - 1 if fim > inicio else inicio):
        blocos.append(extras_de_ppr(bloco.blockFormat()))
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                a = max(frag.position(), inicio)
                b = min(frag.position() + frag.length(), fim)
                if a < b:
                    cf = frag.charFormat()
                    if _omitido(cf):
                        omitidos += b - a
                    else:
                        extras = extras_de_rpr(cf)
                        if extras:
                            trechos.append([a - inicio - omitidos, b - inicio - omitidos, extras])
            it += 1
        bloco = bloco.next()
    total = fim - inicio - omitidos
    if not trechos and not any(blocos):
        return None
    return {"trechos": trechos, "blocos": blocos, "tamanho": total}


def aplicar_colado(doc: QTextDocument, dado: dict, inicio: int, fim: int,
                   no_inicio_vazio: bool) -> None:
    """Devolve os extras ao que foi colado em [inicio, fim). Quem chama abre o bloco de edicao.

    Se o texto colado nao tem o tamanho do copiado (tabela, quadro, outro programa no meio),
    os trechos nao sao aplicados: aplicar fora do lugar seria pior que nao aplicar.
    """
    trechos = dado.get("trechos") or []
    if trechos and dado.get("tamanho") == fim - inicio:
        for item in trechos:
            if not (isinstance(item, list) and len(item) == 3 and isinstance(item[2], str)):
                continue
            a, b, extras = item
            if not (isinstance(a, int) and isinstance(b, int) and 0 <= a < b <= fim - inicio):
                continue
            c = QTextCursor(doc)
            c.setPosition(inicio + a)
            c.setPosition(inicio + b, QTextCursor.MoveMode.KeepAnchor)
            cf = QTextCharFormat()
            aplicar_rpr(cf, extras)
            c.mergeCharFormat(cf)
    itens = dado.get("blocos") or []
    blocos = []
    bloco = doc.findBlock(inicio)
    while bloco.isValid() and bloco.position() <= fim:
        blocos.append(bloco)
        bloco = bloco.next()
    if len(blocos) != len(itens) or not any(itens):
        return
    pares = list(zip(blocos, itens))
    if not no_inicio_vazio:
        pares = pares[1:]  # o primeiro bloco colado e' o bloco onde estava o cursor
    for b, extras in pares:
        if not isinstance(extras, str) or not extras:
            continue
        bf = b.blockFormat()
        aplicar_ppr(bf, extras)
        QTextCursor(b).setBlockFormat(bf)


# -- pintura ------------------------------------------------------------------------------

def _caneta(borda, escala: float = 1.0) -> QPen:
    cor = QColor("#" + borda.cor_hex) if borda.cor_hex else QColor(0, 0, 0)
    caneta = QPen(cor)
    caneta.setWidthF(max(borda.oitavos_pt * 2.5, 10.0) * escala)  # oitavos de ponto -> twips
    caneta.setStyle(_TRACOS.get(borda.estilo, Qt.PenStyle.SolidLine))
    caneta.setCapStyle(Qt.PenCapStyle.FlatCap)
    return caneta


def _linha(painter, borda, a: QPointF, b: QPointF, vertical: bool) -> None:
    caneta = _caneta(borda)
    if borda.estilo == "dupla":
        fina = _caneta(borda, 0.34)
        painter.setPen(fina)
        d = caneta.widthF() * 0.5
        dx, dy = (d, 0.0) if vertical else (0.0, d)
        painter.drawLine(QPointF(a.x() - dx, a.y() - dy), QPointF(b.x() - dx, b.y() - dy))
        painter.drawLine(QPointF(a.x() + dx, a.y() + dy), QPointF(b.x() + dx, b.y() + dy))
        return
    painter.setPen(caneta)
    painter.drawLine(a, b)


def _area_do_texto(bloco, dl) -> QRectF | None:
    """O retangulo das linhas do bloco, entre os recuos (coordenadas do documento)."""
    layout = bloco.layout()
    if layout is None or layout.lineCount() == 0:
        return None
    r = dl.blockBoundingRect(bloco)
    bf = bloco.blockFormat()
    primeira = layout.lineAt(0)
    ultima = layout.lineAt(layout.lineCount() - 1)
    topo = layout.position().y() + primeira.y()
    base = layout.position().y() + ultima.y() + ultima.height()
    esquerda = r.left() + bf.leftMargin()
    direita = r.right() - bf.rightMargin()
    return QRectF(esquerda, topo, max(direita - esquerda, 1.0), max(base - topo, 1.0))


def _bordas_do_bloco(painter, bloco, dl, ap, anterior_igual: bool, proximo_igual: bool) -> None:
    area = _area_do_texto(bloco, dl)
    if area is None:
        return
    b = ap.bordas
    esp = {lado: (b[lado].espaco_pt * 20.0 if lado in b else 0.0) for lado in b}
    topo = area.top() - esp.get("top", 0.0)
    base = area.bottom() + esp.get("bottom", 0.0)
    esquerda = area.left() - esp.get("left", 0.0)
    direita = area.right() + esp.get("right", 0.0)
    if proximo_igual:
        # Paragrafos vizinhos de mesma borda formam um quadro so': a de baixo vira a de entre.
        proximo = bloco.next()
        area_prox = _area_do_texto(proximo, dl)
        if area_prox is not None:
            base = (area.bottom() + area_prox.top()) / 2
    if anterior_igual:
        area_ant = _area_do_texto(bloco.previous(), dl)
        if area_ant is not None:
            topo = (area_ant.bottom() + area.top()) / 2
    if "top" in b and not anterior_igual:
        _linha(painter, b["top"], QPointF(esquerda, topo), QPointF(direita, topo), False)
    if proximo_igual:
        if "between" in b:
            _linha(painter, b["between"], QPointF(esquerda, base), QPointF(direita, base), False)
    elif "bottom" in b:
        _linha(painter, b["bottom"], QPointF(esquerda, base), QPointF(direita, base), False)
    if "left" in b:
        _linha(painter, b["left"], QPointF(esquerda, topo), QPointF(esquerda, base), True)
    if "right" in b:
        _linha(painter, b["right"], QPointF(direita, topo), QPointF(direita, base), True)


def _tabela_de(bloco) -> tuple | None:
    """(tabela, linha) do bloco, ou None fora de tabela: a borda nao junta celulas."""
    tabela = QTextCursor(bloco).currentTable()
    if tabela is None:
        return None
    celula = tabela.cellAt(bloco.position())
    return tabela.firstPosition(), celula.row(), celula.column()


def _bordas_iguais(a, b) -> bool:
    if not (a.isValid() and b.isValid()):
        return False
    ea, eb = extras_de_ppr(a.blockFormat()), extras_de_ppr(b.blockFormat())
    if not ea or not eb:
        return False
    bordas = aparencia_paragrafo(ea).bordas
    return bool(bordas) and bordas == aparencia_paragrafo(eb).bordas \
        and _tabela_de(a) == _tabela_de(b)


def _trechos_com_borda(painter, bloco) -> None:
    layout = bloco.layout()
    if layout is None or layout.lineCount() == 0:
        return
    origem = layout.position()
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        it += 1
        if not frag.isValid():
            continue
        extras = extras_de_rpr(frag.charFormat())
        if not extras:
            continue
        borda = aparencia_run(extras).borda
        if borda is None:
            continue
        ini = frag.position() - bloco.position()
        fim = ini + frag.length()
        for i in range(layout.lineCount()):
            linha = layout.lineAt(i)
            a = max(ini, linha.textStart())
            b = min(fim, linha.textStart() + linha.textLength())
            if a >= b:
                continue
            x0 = linha.cursorToX(a)[0]
            x1 = linha.cursorToX(b)[0]
            esp = borda.espaco_pt * 20.0
            r = QRectF(origem.x() + min(x0, x1) - esp, origem.y() + linha.y(),
                       abs(x1 - x0) + 2 * esp, linha.height())
            painter.setPen(_caneta(borda))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r)


def _preenchimentos(painter, bloco, ap) -> None:
    """O preenchimento (pontos, tracos) das tabulacoes, que o Qt nao desenha."""
    if not any(p in _PREENCHIMENTOS for _pos, _t, p in ap.tabulacoes):
        return
    layout = bloco.layout()
    texto = bloco.text()
    if layout is None or "\t" not in texto:
        return
    origem = layout.position()
    recuo = bloco.blockFormat().leftMargin()
    for i, c in enumerate(texto):
        if c != "\t":
            continue
        linha = layout.lineForTextPosition(i)
        if not linha.isValid():
            continue
        x0 = linha.cursorToX(i)[0]
        x1 = linha.cursorToX(i + 1)[0]
        if x1 - x0 < 60:
            continue
        # A tabulacao que este tab alcanca: a primeira depois do ponto de partida (a posicao
        # do Word conta da margem, como o x da linha).
        alvo = next((t for t in ap.tabulacoes if t[0] > x0 + 1 and t[0] > recuo), None)
        if alvo is None or alvo[2] not in _PREENCHIMENTOS:
            continue
        simbolo = _PREENCHIMENTOS[alvo[2]]
        cf = None
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.position() <= bloco.position() + i < frag.position() + frag.length():
                cf = frag.charFormat()
                break
            it += 1
        fonte = QFont(cf.font()) if cf is not None else QFont(bloco.document().defaultFont())
        if fonte.pointSizeF() > 0:
            fonte.setPixelSize(max(1, round(fonte.pointSizeF() * 20)))
        largura = max(QFontMetricsF(fonte).horizontalAdvance(simbolo), 1.0)
        passo = largura * (1.0 if simbolo in "_-" else 1.6)
        y = origem.y() + linha.y() + linha.ascent()
        x = x0 + passo * 0.5
        n = min(2000, math.floor((x1 - passo * 0.3 - largura - x) / passo) + 1)
        if n <= 0:
            continue
        # Um drawText so' (0.1.8): o espaco entre os simbolos vai no espacamento de letras.
        # Um drawText por ponto custava ate' 2 ms por tile num sumario (medido).
        fonte.setKerning(False)
        fonte.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, passo - largura)
        painter.setFont(fonte)
        painter.setPen(QColor(0, 0, 0))
        painter.drawText(QPointF(origem.x() + x, y), simbolo * n)


def _cache_de_blocos(doc: QTextDocument) -> dict:
    """O que cada bloco tem para pintar, por numero do bloco, enquanto o documento nao muda
    (0.1.14: cada tile lia e interpretava os extras de cada bloco e de cada fragmento)."""
    guardado = getattr(doc, "_cache_pintura_props", None)
    if guardado is None or guardado[0] != doc.revision() or guardado[1] != doc.blockCount():
        guardado = (doc.revision(), doc.blockCount(), {})
        try:
            doc._cache_pintura_props = guardado
        except (AttributeError, RuntimeError):
            pass
    return guardado[2]


def _info_do_bloco(cache: dict, bloco) -> tuple:
    """(aparencia com bordas ou tabulacoes, ou None; algum trecho com borda; esta' em tabela)."""
    n = bloco.blockNumber()
    info = cache.get(n)
    if info is None:
        extras = extras_de_ppr(bloco.blockFormat())
        ap = aparencia_paragrafo(extras) if extras else None
        if ap is not None and not ap.bordas and not ap.tabulacoes:
            ap = None
        com_borda = False
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            it += 1
            if frag.isValid():
                ex = extras_de_rpr(frag.charFormat())
                if ex and aparencia_run(ex).borda is not None:
                    com_borda = True
                    break
        info = (ap, com_borda, QTextCursor(bloco).currentTable() is not None)
        cache[n] = info
    return info


def desenhar(painter, doc: QTextDocument, recorte: QRectF | None) -> None:
    """Bordas de paragrafo e de trecho e preenchimento das tabulacoes, nos blocos que cruzam o
    recorte (coordenadas do documento, painter ja' transformado). A mesma funcao para a tela,
    o PDF e a impressao, como os numeros das listas."""
    dl = doc.documentLayout()
    if recorte is not None:
        bloco = doc.findBlock(dl.hitTest(QPointF(0, recorte.top()), Qt.HitTestAccuracy.FuzzyHit))
        bloco = bloco.previous() if bloco.previous().isValid() else bloco
    else:
        bloco = doc.firstBlock()
    cache = _cache_de_blocos(doc)
    painter.save()
    try:
        while bloco.isValid():
            ap, com_borda, em_tabela = _info_do_bloco(cache, bloco)
            if ap is None and not com_borda:
                if recorte is not None and not em_tabela:
                    # Bloco sem nada para pintar: so' conta para saber se ja' passou do recorte.
                    if dl.blockBoundingRect(bloco).top() > recorte.bottom() + 2000:
                        break
                bloco = bloco.next()
                continue
            r = dl.blockBoundingRect(bloco)
            if recorte is not None and r.top() > recorte.bottom() + 2000:
                if not em_tabela:
                    break
            if recorte is None or r.adjusted(-2000, -2000, 2000, 2000).intersects(recorte):
                if ap is not None:
                    if ap.bordas:
                        _bordas_do_bloco(painter, bloco, dl, ap,
                                         _bordas_iguais(bloco.previous(), bloco),
                                         _bordas_iguais(bloco, bloco.next()))
                    if ap.tabulacoes:
                        _preenchimentos(painter, bloco, ap)
                if com_borda:
                    _trechos_com_borda(painter, bloco)
            bloco = bloco.next()
    except RuntimeError as erro:  # pintura nunca derruba a janela
        log.warning("bordas e tabulacoes nao pintadas: %s", erro)
    finally:
        painter.restore()
