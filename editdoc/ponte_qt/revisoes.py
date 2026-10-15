"""Alteracoes controladas no QTextDocument (0.1.13): as revisoes no formato e os modos de exibicao.

Onde vivem as revisoes:

- no formato de caractere de cada trecho: PROP_REV_INS (w:ins ou w:moveTo, em JSON),
  PROP_REV_DEL (w:del ou w:moveFrom) e PROP_REV_RPR (o w:rPrChange canonico, a formatacao de
  antes). O texto excluido CONTINUA no documento, como no Word: aceitar a exclusao e' apagar o
  texto; rejeitar e' tirar a propriedade. Como o resto do formato, a propriedade acompanha o
  texto no desfazer, no copiar dentro do documento e na divisao dos fragmentos;
- no formato do bloco: PROP_REV_MARCA (a marca de paragrafo inserida e/ou excluida, JSON) e
  PROP_REV_PPR (o w:pPrChange e a revisao da numeracao, JSON);
- linha, celula e tabela: no JSON dos extras que ja' existia (`extras_linha`, `extras` da
  celula e da tabela, ver `para_qt`), e a secao no registro das secoes.

Os modos de exibicao NAO mudam o documento (nem o desfazer, nem o "alterado"): sao formatos
adicionais do layout, aplicados por um `QSyntaxHighlighter` (`RealceRevisoes`), que o Qt mantem
fora do conteudo e reaplica so' no bloco que mudou. Medido no Qt 6.11.2 (docs/SPIKES.md, 0.1.13):

- "Toda a marcacao": inserido sublinhado e excluido tachado, na cor do autor; movido em verde,
  com a segunda linha (sublinhado duplo, tachado duplo) pintada por `desenhar`;
- "Marcacao simples" e "Sem marcacao": o excluido some. Fonte de 0,01 pt e cor transparente:
  a largura no layout de 1440 dpi e' zero (medido: 93 e 200 caracteres escondidos, a linha com
  a mesma largura que sem eles; 0,05 pt ainda deixava 1 twip por caractere). O paragrafo que
  fica sem nada visivel e cuja marca foi excluida some inteiro (`QTextBlock.setVisible`, que o
  QTextDocumentLayout respeita: altura zero);
- "Original": o inserido some, do mesmo jeito, e a formatacao de antes (w:rPrChange) volta.

A barra de alteracao na margem esquerda e a segunda linha dos movimentos sao pintadas por
`desenhar`, na funcao unica da folha (tela, PDF e impressao). Sem revisao no documento nada
disso roda: o realce so' e' criado quando a primeira revisao aparece (`garantir_realce`).
"""

from __future__ import annotations

import functools
import json

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QPen, QSyntaxHighlighter, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTextDocument, QTextFormat)

from editdoc import log_interno
from editdoc.modelo.documento import Revisao
from editdoc.modelo.revisoes import MODO_PADRAO, MODOS, visivel_no_modo

log = log_interno.obter(__name__)

_U = QTextFormat.Property.UserProperty.value
#: Caractere: a insercao (w:ins ou w:moveTo) em JSON. Numeros livres (ver CLAUDE.md).
PROP_REV_INS = _U + 40
#: Caractere: a exclusao (w:del ou w:moveFrom) em JSON.
PROP_REV_DEL = _U + 41
#: Caractere: o w:rPrChange canonico (a formatacao de antes, sem o w:id).
PROP_REV_RPR = _U + 42
#: Bloco: a marca de paragrafo inserida/excluida, JSON {"ins": ..., "del": ...}.
PROP_REV_MARCA = _U + 43
#: Bloco: o w:pPrChange e a revisao da numeracao, JSON {"ppr": ..., "num": ...}.
PROP_REV_PPR = _U + 44
#: Propriedades de revisao do caractere (o texto digitado com o controle desligado sai sem).
PROPS_DE_CARACTERE = (PROP_REV_INS, PROP_REV_DEL, PROP_REV_RPR)

#: Cores por autor (a ordem em que aparecem no documento), como o Word faz.
CORES_AUTORES = ("#B5082E", "#1F4E9C", "#7B2C9E", "#B85C00", "#0B6E6A", "#A0306E", "#5D4037",
                 "#2E7D32")
COR_MOVIMENTO = QColor(0x1E, 0x7B, 0x34)
COR_BARRA_SIMPLES = QColor(0xC0, 0x1C, 0x28)
COR_BARRA = QColor(0x70, 0x70, 0x70)
#: Largura da barra de alteracao e distancia da borda do texto, em twips.
BARRA_TW = 22
DISTANCIA_BARRA_TW = 200


# -- JSON ------------------------------------------------------------------------------------

def json_de(rev: Revisao) -> str:
    return json.dumps({"t": rev.tipo, "a": rev.autor, "d": rev.data, "u": rev.data_utc},
                      ensure_ascii=False, sort_keys=True)


@functools.lru_cache(maxsize=8192)
def _revisao(texto: str) -> Revisao | None:
    try:
        dado = json.loads(texto)
    except (TypeError, ValueError):
        return None
    if not isinstance(dado, dict) or dado.get("t") not in ("ins", "del", "moveFrom", "moveTo"):
        return None
    autor = dado.get("a") if isinstance(dado.get("a"), str) else ""
    data = dado.get("d") if isinstance(dado.get("d"), str) else None
    utc = dado.get("u") if isinstance(dado.get("u"), str) else None
    return Revisao(dado["t"], autor, data, utc)


def _texto(valor) -> str | None:
    return valor if isinstance(valor, str) and valor else None


def insercao_de(fmt: QTextFormat) -> Revisao | None:
    if not fmt.hasProperty(PROP_REV_INS):
        return None
    texto = _texto(fmt.property(PROP_REV_INS))
    return _revisao(texto) if texto else None


def exclusao_de(fmt: QTextFormat) -> Revisao | None:
    if not fmt.hasProperty(PROP_REV_DEL):
        return None
    texto = _texto(fmt.property(PROP_REV_DEL))
    return _revisao(texto) if texto else None


def mudanca_de(fmt: QTextFormat) -> str | None:
    return _texto(fmt.property(PROP_REV_RPR)) if fmt.hasProperty(PROP_REV_RPR) else None


def tem_revisao(fmt: QTextFormat) -> bool:
    return any(fmt.hasProperty(p) for p in PROPS_DE_CARACTERE)


@functools.lru_cache(maxsize=2048)
def _marca(texto: str) -> tuple:
    try:
        dado = json.loads(texto)
    except (TypeError, ValueError):
        return None, None
    if not isinstance(dado, dict):
        return None, None
    return (_revisao(json.dumps(dado["ins"])) if isinstance(dado.get("ins"), dict) else None,
            _revisao(json.dumps(dado["del"])) if isinstance(dado.get("del"), dict) else None)


def marca_de(bf: QTextFormat) -> tuple[Revisao | None, Revisao | None]:
    """(insercao, exclusao) da marca de paragrafo do bloco."""
    if not bf.hasProperty(PROP_REV_MARCA):
        return None, None
    texto = _texto(bf.property(PROP_REV_MARCA))
    return _marca(texto) if texto else (None, None)


def json_da_marca(insercao: Revisao | None, exclusao: Revisao | None) -> str | None:
    if insercao is None and exclusao is None:
        return None
    dado = {}
    if insercao is not None:
        dado["ins"] = json.loads(json_de(insercao))
    if exclusao is not None:
        dado["del"] = json.loads(json_de(exclusao))
    return json.dumps(dado, ensure_ascii=False, sort_keys=True)


def definir_marca(bf: QTextBlockFormat, insercao: Revisao | None, exclusao: Revisao | None) -> None:
    texto = json_da_marca(insercao, exclusao)
    if texto is None:
        bf.clearProperty(PROP_REV_MARCA)
    else:
        bf.setProperty(PROP_REV_MARCA, texto)


@functools.lru_cache(maxsize=2048)
def _ppr(texto: str) -> tuple:
    try:
        dado = json.loads(texto)
    except (TypeError, ValueError):
        return None, None
    if not isinstance(dado, dict):
        return None, None
    return _texto(dado.get("ppr")), _texto(dado.get("num"))


def mudanca_de_bloco(bf: QTextFormat) -> tuple[str | None, str | None]:
    """(w:pPrChange, revisao da numeracao) do bloco."""
    if not bf.hasProperty(PROP_REV_PPR):
        return None, None
    texto = _texto(bf.property(PROP_REV_PPR))
    return _ppr(texto) if texto else (None, None)


def definir_mudanca_de_bloco(bf: QTextBlockFormat, ppr: str | None, num: str | None) -> None:
    if not ppr and not num:
        bf.clearProperty(PROP_REV_PPR)
    else:
        bf.setProperty(PROP_REV_PPR, json.dumps({"ppr": ppr, "num": num}, sort_keys=True))


def bloco_revisado(bloco) -> bool:
    """O bloco tem alguma revisao (no texto, na marca ou nas propriedades)?"""
    bf = bloco.blockFormat()
    if bf.hasProperty(PROP_REV_MARCA) or bf.hasProperty(PROP_REV_PPR):
        return True
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and tem_revisao(frag.charFormat()):
            return True
        it += 1
    return False


# -- ponte com o modelo ------------------------------------------------------------------------

def aplicar_run(cf: QTextCharFormat, run) -> QTextCharFormat:
    """As revisoes do `Run` no formato (para_qt). Marca o documento como revisado quem chama."""
    if run.insercao is not None:
        cf.setProperty(PROP_REV_INS, json_de(run.insercao))
    if run.exclusao is not None:
        cf.setProperty(PROP_REV_DEL, json_de(run.exclusao))
    if run.mudanca_formato:
        cf.setProperty(PROP_REV_RPR, run.mudanca_formato)
    return cf


def run_revisado(run) -> bool:
    return run.insercao is not None or run.exclusao is not None or bool(run.mudanca_formato)


def paragrafo_revisado(p) -> bool:
    return (p.marca_insercao is not None or p.marca_exclusao is not None
            or bool(p.mudanca_formato) or bool(p.mudanca_numeracao))


def aplicar_paragrafo(bf: QTextBlockFormat, p) -> None:
    definir_marca(bf, p.marca_insercao, p.marca_exclusao)
    definir_mudanca_de_bloco(bf, p.mudanca_formato, p.mudanca_numeracao)


def ler_run(cf: QTextFormat, run) -> None:
    """As revisoes do formato no `Run` (de_qt)."""
    run.insercao = insercao_de(cf)
    run.exclusao = exclusao_de(cf)
    run.mudanca_formato = mudanca_de(cf)


def ler_paragrafo(bf: QTextFormat, p) -> None:
    p.marca_insercao, p.marca_exclusao = marca_de(bf)
    p.mudanca_formato, p.mudanca_numeracao = mudanca_de_bloco(bf)


def sem_revisao(cf: QTextCharFormat) -> QTextCharFormat:
    """Copia do formato sem as revisoes (o texto digitado com o controle desligado)."""
    if not tem_revisao(cf):
        return cf
    novo = QTextCharFormat(cf)
    for p in PROPS_DE_CARACTERE:
        novo.clearProperty(p)
    return novo


# -- documento: revisoes, modo, cores ---------------------------------------------------------

def tem_revisoes(doc: QTextDocument) -> bool:
    return bool(getattr(doc, "_tem_revisoes", False))


def marcar_revisado(doc: QTextDocument) -> None:
    """O documento passou a ter revisao: o realce comeca a valer."""
    if not tem_revisoes(doc):
        try:
            doc._tem_revisoes = True
        except AttributeError:
            return
    garantir_realce(doc)


def modo_de(doc: QTextDocument) -> str:
    modo = getattr(doc, "_modo_revisao", MODO_PADRAO)
    return modo if modo in MODOS else MODO_PADRAO


def definir_modo(doc: QTextDocument, modo: str) -> bool:
    """Troca o modo de exibicao do documento. True se mudou (quem chama limpa o cache)."""
    if modo not in MODOS:
        raise ValueError(f"modo de exibicao invalido: {modo!r}")
    if modo_de(doc) == modo:
        return False
    try:
        doc._modo_revisao = modo
    except AttributeError:
        return False
    realce = getattr(doc, "_realce_revisoes", None)
    if realce is not None:
        realce.rehighlight()
    elif tem_revisoes(doc):
        garantir_realce(doc)
    return True


def garantir_realce(doc: QTextDocument):
    realce = getattr(doc, "_realce_revisoes", None)
    if realce is None:
        try:
            realce = RealceRevisoes(doc)
            doc._realce_revisoes = realce
        except AttributeError:
            return None
        realce.rehighlight()
    return realce


def reaplicar(doc: QTextDocument) -> None:
    """Refaz o realce do documento inteiro (depois de mudar muitas revisoes de uma vez)."""
    realce = getattr(doc, "_realce_revisoes", None)
    if realce is not None:
        realce.rehighlight()


def cor_do_autor(doc: QTextDocument, autor: str) -> QColor:
    cores = getattr(doc, "_cores_autores", None)
    if cores is None:
        cores = {}
        try:
            doc._cores_autores = cores
        except AttributeError:
            pass
    if autor not in cores:
        cores[autor] = len(cores) % len(CORES_AUTORES)
    return QColor(CORES_AUTORES[cores[autor]])


def oculto(insercao: Revisao | None, exclusao: Revisao | None, modo: str) -> bool:
    return not visivel_no_modo(insercao, exclusao, modo)


def oculto_em(doc: QTextDocument, pos: int) -> bool:
    """O caractere em `pos` esta' escondido no modo atual do documento?"""
    if not tem_revisoes(doc) or modo_de(doc) == "todas":
        return False
    from editdoc.ponte_qt.links import formato_em
    cf = formato_em(doc, pos)
    if cf is None or not tem_revisao(cf):
        return False
    return oculto(insercao_de(cf), exclusao_de(cf), modo_de(doc))


def intervalos_ocultos(doc: QTextDocument, inicio: int, fim: int,
                       modo: str | None = None) -> list[tuple[int, int]]:
    """(inicio, fim) dos trechos escondidos no modo entre as duas posicoes."""
    modo = modo or modo_de(doc)
    if modo == "todas" or not tem_revisoes(doc):
        return []
    saida: list[tuple[int, int]] = []
    bloco = doc.findBlock(inicio)
    while bloco.isValid() and bloco.position() < fim:
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                a, b = frag.position(), frag.position() + frag.length()
                if b > inicio and a < fim and tem_revisao(frag.charFormat()):
                    cf = frag.charFormat()
                    if oculto(insercao_de(cf), exclusao_de(cf), modo):
                        a, b = max(a, inicio), min(b, fim)
                        if saida and saida[-1][1] == a:
                            saida[-1] = (saida[-1][0], b)
                        else:
                            saida.append((a, b))
            it += 1
        bloco = bloco.next()
    return saida


# -- formatos do realce ------------------------------------------------------------------------

def _formato_oculto() -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setFontPointSize(0.01)
    fmt.setForeground(QColor(0, 0, 0, 0))
    fmt.setBackground(QColor(0, 0, 0, 0))
    fmt.setFontStrikeOut(False)
    fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.NoUnderline)
    fmt.setFontLetterSpacingType(QFont.SpacingType.PercentageSpacing)
    fmt.setFontLetterSpacing(100)
    fmt.setFontWordSpacing(0)
    return fmt


_OCULTO = None


def formato_oculto() -> QTextCharFormat:
    global _OCULTO
    if _OCULTO is None:
        _OCULTO = _formato_oculto()
    return _OCULTO


def _formato_marcado(doc, insercao, exclusao) -> QTextCharFormat:
    fmt = QTextCharFormat()
    if exclusao is not None:
        cor = COR_MOVIMENTO if exclusao.tipo == "moveFrom" else cor_do_autor(doc, exclusao.autor)
        fmt.setForeground(cor)
        fmt.setFontStrikeOut(True)
    elif insercao is not None:
        cor = COR_MOVIMENTO if insercao.tipo == "moveTo" else cor_do_autor(doc, insercao.autor)
        fmt.setForeground(cor)
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
        fmt.setUnderlineColor(cor)
    return fmt


def formato_antigo(doc: QTextDocument, mudanca: str, sid_par: str | None) -> QTextCharFormat | None:
    """A formatacao de antes (w:rPrChange) como formato adicional do modo Original: o estilo e
    a formatacao direta de antes, e o que ela nao diz volta ao padrao (o negrito que a
    alteracao pos sai)."""
    cache = getattr(doc, "_formatos_antigos", None)
    if cache is None:
        cache = {}
        try:
            doc._formatos_antigos = cache
        except AttributeError:
            pass
    chave = (mudanca, sid_par)
    if chave in cache:
        return cache[chave]
    fmt = None
    try:
        from editdoc.formato_docx import revisoes as fx_revisoes
        from editdoc.modelo.estilos import CAMPOS_CARACTERE
        from editdoc.ponte_qt import estilos as pq_estilos
        cat = pq_estilos.catalogo(doc)
        run = fx_revisoes.run_da_mudanca(mudanca, cat)
        if run is not None:
            base = pq_estilos.Resolvedor(cat).caractere(sid_par, run.estilo)
            props = {**base, **{k: getattr(run, k) for k in CAMPOS_CARACTERE
                                if getattr(run, k) is not None}}
            padrao = doc.defaultFont()
            for k, v in (("negrito", False), ("italico", False), ("sublinhado", False),
                         ("tachado", False), ("subscrito", False), ("sobrescrito", False),
                         ("tamanho_meio_pt", round(padrao.pointSizeF() * 2) or 22),
                         ("fonte", padrao.family())):
                props.setdefault(k, v)
            fmt = pq_estilos.formato_de_caractere(props)
            if props.get("cor_hex") is None:
                fmt.setForeground(QColor(0, 0, 0))
    except Exception:  # noqa: BLE001 - so' aparencia
        log.exception("formatacao de antes")
        fmt = None
    if len(cache) > 512:
        cache.clear()
    cache[chave] = fmt
    return fmt


class RealceRevisoes(QSyntaxHighlighter):
    """Os formatos do modo de exibicao, bloco a bloco (ver o topo do modulo)."""

    def highlightBlock(self, _texto) -> None:  # noqa: N802 - nome do Qt
        try:
            self._realcar()
        except Exception:  # noqa: BLE001 - chamado pelo Qt no meio do layout
            log.exception("realce das revisoes")

    def _realcar(self) -> None:
        doc = self.document()
        bloco = self.currentBlock()
        modo = modo_de(doc)
        inicio = bloco.position()
        visiveis = 0
        sid_par = None
        it = bloco.begin()
        from editdoc.ponte_qt import marcas
        while not it.atEnd():
            frag = it.fragment()
            it += 1
            if not frag.isValid():
                continue
            cf = frag.charFormat()
            if not tem_revisao(cf):
                if not marcas.eh_marcador(cf):
                    visiveis += frag.length()
                continue
            ins, exc = insercao_de(cf), exclusao_de(cf)
            pos, n = frag.position() - inicio, frag.length()
            if oculto(ins, exc, modo):
                if not cf.isImageFormat():
                    self.setFormat(pos, n, formato_oculto())
                continue
            if not marcas.eh_marcador(cf):
                visiveis += n
            if modo == "todas" and (ins is not None or exc is not None):
                self.setFormat(pos, n, _formato_marcado(doc, ins, exc))
            elif modo == "original":
                mudanca = mudanca_de(cf)
                if mudanca:
                    if sid_par is None:
                        from editdoc.ponte_qt import estilos as pq_estilos
                        sid_par = pq_estilos.estilo_do_bloco(bloco.blockFormat()) or ""
                    fmt = formato_antigo(doc, mudanca, sid_par or None)
                    if fmt is not None:
                        self.setFormat(pos, n, fmt)
        m_ins, m_exc = marca_de(bloco.blockFormat())
        esconder = visiveis == 0 and bloco.next().isValid() and (
            (modo in ("final", "simples") and m_exc is not None)
            or (modo == "original" and m_ins is not None))
        if bloco.isVisible() == esconder:
            bloco.setVisible(not esconder)
            doc.markContentsDirty(bloco.position(), bloco.length())


# -- pintura: barra de alteracao e segunda linha dos movimentos --------------------------------

def _linhas_revisadas(bloco) -> tuple[list, list]:
    """(trechos revisados, trechos movidos) do bloco, em posicoes relativas ao bloco."""
    revisados, movidos = [], []
    inicio = bloco.position()
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        it += 1
        if not frag.isValid() or not tem_revisao(frag.charFormat()):
            continue
        cf = frag.charFormat()
        a, b = frag.position() - inicio, frag.position() - inicio + frag.length()
        revisados.append((a, b))
        ins, exc = insercao_de(cf), exclusao_de(cf)
        if (exc is not None and exc.tipo == "moveFrom") or (exc is None and ins is not None
                                                             and ins.tipo == "moveTo"):
            movidos.append((a, b, exc is not None))
    return revisados, movidos


def desenhar(painter, doc: QTextDocument, recorte: QRectF | None, tela: bool = True) -> None:
    """Barra de alteracao na margem esquerda (Toda a marcacao e Marcacao simples) e a segunda
    linha dos movimentos (Toda a marcacao), nos blocos que cruzam o recorte. Coordenadas do
    documento, painter ja' transformado (a mesma funcao para a tela, o PDF e a impressao)."""
    if not tem_revisoes(doc):
        return
    modo = modo_de(doc)
    if modo not in ("todas", "simples"):
        return
    dl = doc.documentLayout()
    if recorte is not None:
        bloco = doc.findBlock(dl.hitTest(QPointF(0, recorte.top()), Qt.HitTestAccuracy.FuzzyHit))
        bloco = bloco.previous() if bloco.previous().isValid() else bloco
    else:
        bloco = doc.firstBlock()
    cor = COR_BARRA_SIMPLES if modo == "simples" else COR_BARRA
    painter.save()
    try:
        painter.setPen(Qt.PenStyle.NoPen)
        while bloco.isValid():
            r = dl.blockBoundingRect(bloco)
            if recorte is not None and r.top() > recorte.bottom() + 2000:
                if QTextCursor(bloco).currentTable() is None:
                    break
            if bloco.isVisible() and (recorte is None or r.adjusted(-4000, -500, 4000, 500)
                                      .intersects(recorte)):
                _desenhar_bloco(painter, doc, bloco, r, cor, modo)
            bloco = bloco.next()
    except RuntimeError as erro:  # pintura nunca derruba a janela
        log.warning("revisoes nao pintadas: %s", erro)
    finally:
        painter.restore()


def _desenhar_bloco(painter, doc, bloco, r: QRectF, cor: QColor, modo: str) -> None:
    lay = bloco.layout()
    if lay is None or lay.lineCount() == 0:
        return
    revisados, movidos = _linhas_revisadas(bloco)
    bf = bloco.blockFormat()
    marca = bf.hasProperty(PROP_REV_MARCA)
    propriedades = bf.hasProperty(PROP_REV_PPR)
    if not revisados and not marca and not propriedades:
        return
    x_barra = -DISTANCIA_BARRA_TW - r.left()
    for i in range(lay.lineCount()):
        linha = lay.lineAt(i)
        a, b = linha.textStart(), linha.textStart() + linha.textLength()
        tocada = propriedades or (marca and i == lay.lineCount() - 1) or any(
            x < b and y > a for x, y in revisados)
        if not tocada:
            continue
        y = r.top() + linha.y()
        painter.fillRect(QRectF(r.left() + x_barra, y, BARRA_TW, linha.height()), cor)
    if modo != "todas" or not movidos:
        return
    caneta = QPen(COR_MOVIMENTO)
    for a, b, origem in movidos:
        for i in range(lay.lineCount()):
            linha = lay.lineAt(i)
            la, lb = linha.textStart(), linha.textStart() + linha.textLength()
            if b <= la or a >= lb:
                continue
            x0 = linha.cursorToX(max(a, la))[0]
            x1 = linha.cursorToX(min(b, lb))[0]
            espessura = max(linha.height() * 0.05, 8.0)
            caneta.setWidthF(espessura)
            painter.setPen(caneta)
            if origem:
                y = r.top() + linha.y() + linha.ascent() * 0.62
            else:
                y = r.top() + linha.y() + linha.ascent() + linha.descent() * 0.85
            painter.drawLine(QPointF(r.left() + x0, y), QPointF(r.left() + x1, y))
            painter.setPen(Qt.PenStyle.NoPen)
