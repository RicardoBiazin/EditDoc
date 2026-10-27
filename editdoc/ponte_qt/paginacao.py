"""Paginacao como a do Word no formato do Qt (0.1.17): a compensacao de layout e como le-la.

As regras sao de `modelo/paginacao.py`; quem as mantem em dia e' `interface/paginacao.py`. Aqui
ficam as propriedades que guardam o valor de verdade (o do paragrafo) quando o formato do bloco
tem outro, so' para o layout do Qt chegar ao do Word:

- PROP_WORD_ANTES / PROP_WORD_DEPOIS (bloco ou tabela): "real;aplicado" do topMargin e do
  bottomMargin, em px96 (a unidade do formato). O Qt usa o maior entre o espaco depois do de cima
  e o espaco antes do de baixo; o Word soma. O bloco de baixo leva a soma no espaco antes e o de
  cima fica com zero depois. Depois de uma tabela o Qt ignora o espaco antes do paragrafo, e
  antes dela o espaco depois do de cima: as margens do quadro da tabela os levam;
- PROP_WORD_LINHA (bloco): "tipo;valor;aplicado" da entrelinha. A linha do Word tem o espaco
  externo da fonte (`modelo/paginacao.unidades_da_linha_word`); a entrelinha proporcional leva a
  razao Word/Qt da familia;
- PROP_WORD_VISIVEL (bloco): o paragrafo vazio logo antes de uma tabela, que o Qt esconde
  (`isEmptyBlockBeforeTable`), ganha um fundo transparente: com fundo o Qt o mostra, como o Word;
- PROP_QUEBRA_REGRA (bloco): a quebra de pagina das regras do Word (linhas viuvas e orfas, manter
  com o proximo, manter linhas juntas, quebra antes do estilo). Nao e' quebra do usuario: o
  `de_qt`, o rotulo "Quebra de pagina", o Enter e o copiar a ignoram, como o espacador das notas.
- PROP_WORD_ALTURA (celula, 0.1.26): o acolchoamento de cima ou de baixo tem o que falta para a
  linha ter a altura do w:trHeight (`interface/paginacao._alturas_das_linhas`). O arquivo nao
  muda: o acolchoamento nao volta ao modelo (a margem da celula vem dos extras).

O valor "real" vazio quer dizer "o bloco nao tinha a propriedade". Se alguem troca o valor do
formato (formatacao, estilo), o valor novo e' do usuario: a propriedade so' vale enquanto o
formato tem o "aplicado".
"""

from __future__ import annotations

import math

from PySide6.QtGui import (QBrush, QColor, QFont, QRawFont, QTextBlockFormat, QTextCharFormat,
                           QTextDocument, QTextFormat)

from editdoc.modelo import paginacao as mod

P = QTextFormat.Property
_USUARIO = P.UserProperty.value
PROP_WORD_ANTES = _USUARIO + 45
PROP_WORD_DEPOIS = _USUARIO + 46
PROP_WORD_LINHA = _USUARIO + 47
PROP_QUEBRA_REGRA = _USUARIO + 48
PROP_WORD_VISIVEL = _USUARIO + 49
#: Celula (0.1.26): o acolchoamento tem o acrescimo da altura da linha (w:trHeight) sobre o do
#: arquivo. So' marca (o valor de verdade sai do tcMar/tblCellMar, `para_qt.acolchoamento_base`):
#: a linha sem altura e sem a marca nem e' conferida a cada tecla.
PROP_WORD_ALTURA = _USUARIO + 50
#: Todas as propriedades da compensacao (o copiar e a rejeicao de formatacao as conhecem).
PROPS_DE_PAGINACAO = (PROP_WORD_ANTES, PROP_WORD_DEPOIS, PROP_WORD_LINHA, PROP_QUEBRA_REGRA,
                      PROP_WORD_VISIVEL)
SIMPLES = QTextBlockFormat.LineHeightTypes.SingleHeight.value
PROPORCIONAL = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
FIXA = QTextBlockFormat.LineHeightTypes.FixedHeight.value
MINIMA = QTextBlockFormat.LineHeightTypes.MinimumHeight.value
DISTANCIA = QTextBlockFormat.LineHeightTypes.LineDistanceHeight.value
#: Diferenca que conta como "o mesmo valor" (px96 ou percentual).
FOLGA = 0.01
_ANTES = QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore


def _inteiro(flags) -> int:
    try:
        return int(flags.value)
    except AttributeError:
        return int(flags)


def tem_quebra_antes(fmt) -> bool:
    return bool(_inteiro(fmt.pageBreakPolicy()) & _inteiro(_ANTES))


def _texto(fmt, prop) -> str | None:
    valor = fmt.property(prop)
    return valor if isinstance(valor, str) and valor else None


def _numero(texto: str) -> float | None:
    try:
        return float(texto) if texto != "" else None
    except ValueError:
        return None


def _margem(fmt, prop_word: int, prop_qt) -> tuple[float | None, bool]:
    """(valor real em px96 ou None se ausente, compensado agora)."""
    bruto = _texto(fmt, prop_word)
    if bruto is not None and ";" in bruto:
        real, aplicado = bruto.split(";", 1)
        ap = _numero(aplicado)
        atual = fmt.doubleProperty(prop_qt) if fmt.hasProperty(prop_qt) else 0.0
        if ap is not None and abs(atual - ap) < FOLGA:
            return _numero(real), True
    if fmt.hasProperty(prop_qt):
        return fmt.doubleProperty(prop_qt), False
    return None, False


def antes_real(fmt) -> float | None:
    """O espaco antes do paragrafo (px96), sem a compensacao; None = o bloco nao tem."""
    return _margem(fmt, PROP_WORD_ANTES, P.BlockTopMargin)[0]


def depois_real(fmt) -> float | None:
    return _margem(fmt, PROP_WORD_DEPOIS, P.BlockBottomMargin)[0]


def linha_real(fmt) -> tuple[int, float] | None:
    """(tipo, valor) da entrelinha sem a compensacao; None = o bloco nao tem."""
    bruto = _texto(fmt, PROP_WORD_LINHA)
    if bruto is not None and bruto.count(";") in (2, 3):
        partes = bruto.split(";")
        tipo, valor, aplicado = partes[:3]
        tipo_aplicado = int(partes[3]) if len(partes) == 4 and partes[3].isdigit() else PROPORCIONAL
        ap = _numero(aplicado)
        if ap is not None and fmt.hasProperty(P.LineHeight) and \
                abs(fmt.doubleProperty(P.LineHeight) - ap) < FOLGA and \
                fmt.intProperty(P.LineHeightType) == tipo_aplicado:
            if tipo == "":
                return None
            v = _numero(valor)
            return int(tipo), (v if v is not None else 0.0)
    if not fmt.hasProperty(P.LineHeight) and not fmt.hasProperty(P.LineHeightType):
        return None
    return fmt.intProperty(P.LineHeightType), fmt.doubleProperty(P.LineHeight)


def _definir_margem(fmt, prop_word: int, prop_qt, real: float | None, alvo: float) -> None:
    if real is None and alvo < FOLGA:
        fmt.clearProperty(prop_qt)
        fmt.clearProperty(prop_word)
        return
    if real is not None and abs(alvo - real) < FOLGA:
        fmt.setProperty(prop_qt, float(real))
        fmt.clearProperty(prop_word)
        return
    fmt.setProperty(prop_qt, float(alvo))
    fmt.setProperty(prop_word, f"{'' if real is None else repr(float(real))};{float(alvo)!r}")


def definir_antes(fmt, real: float | None, alvo: float) -> None:
    _definir_margem(fmt, PROP_WORD_ANTES, P.BlockTopMargin, real, alvo)


def definir_depois(fmt, real: float | None, alvo: float) -> None:
    _definir_margem(fmt, PROP_WORD_DEPOIS, P.BlockBottomMargin, real, alvo)


def definir_margens_da_tabela(fmt, topo_px: float, base_px: float) -> None:
    """Margem de cima e de baixo do quadro da tabela (px96). A tabela do EditDoc nao tem margem
    vertical propria: o real e' zero."""
    for prop_word, prop_qt, alvo in ((PROP_WORD_ANTES, P.FrameTopMargin, topo_px),
                                     (PROP_WORD_DEPOIS, P.FrameBottomMargin, base_px)):
        real, _c = _margem(fmt, prop_word, prop_qt)
        real = real or 0.0
        if abs(alvo - real) < FOLGA:
            if fmt.hasProperty(prop_word):
                fmt.setProperty(prop_qt, float(real))
                fmt.clearProperty(prop_word)
            continue
        fmt.setProperty(prop_qt, float(alvo))
        fmt.setProperty(prop_word, f"{float(real)!r};{float(alvo)!r}")


def definir_linha(fmt, real: tuple[int, float] | None, fator: float,
                  linha_qt: float | None = None) -> None:
    """A entrelinha do bloco com a razao Word/Qt da fonte. Exata e minima nao mudam (o Word as
    usa ao pe' da letra).

    `linha_qt` (twips): o bloco tem objeto mais alto que a linha do texto (imagem na linha). O
    Word multiplica a linha da FONTE, nao a do objeto: medido nos arquivos do Word, a linha da
    imagem com entrelinha de 1,5 ocupa a imagem mais meia linha do texto, nao 1,5 vez a imagem.
    O tipo do Qt que faz isso e' a distancia fixa somada a cada linha (LineDistanceHeight): a
    linha do texto fica com a do Word vezes o multiplo, a do objeto com o objeto mais o resto."""
    tipo = real[0] if real is not None else SIMPLES
    if linha_qt is not None and linha_qt > 0:
        multiplo = (real[1] / 100.0 if tipo == PROPORCIONAL and real[1] > 0 else 1.0)
        if tipo in (SIMPLES, PROPORCIONAL) and multiplo > 1.0 + 1e-6:
            distancia = round((linha_qt * fator * multiplo - linha_qt) / 15.0, 4)
            fmt.setLineHeight(distancia, DISTANCIA)
            base = "" if real is None else f"{real[0]};{real[1]!r}"
            fmt.setProperty(PROP_WORD_LINHA, (base or ";") + f";{distancia!r};{DISTANCIA}")
            return
        fator = 1.0  # entrelinha simples: a linha do objeto e' o objeto
    if tipo not in (SIMPLES, PROPORCIONAL) or abs(fator - 1.0) < 0.002:
        if fmt.hasProperty(PROP_WORD_LINHA):
            fmt.clearProperty(PROP_WORD_LINHA)
            if real is None:
                fmt.clearProperty(P.LineHeight)
                fmt.clearProperty(P.LineHeightType)
            else:
                fmt.setLineHeight(real[1], real[0])
        return
    base = real[1] if tipo == PROPORCIONAL and real[1] > 0 else 100.0
    aplicado = round(base * fator, 4)
    fmt.setLineHeight(aplicado, PROPORCIONAL)
    if real is None:
        fmt.setProperty(PROP_WORD_LINHA, f";;{aplicado!r}")
    else:
        fmt.setProperty(PROP_WORD_LINHA, f"{real[0]};{real[1]!r};{aplicado!r}")


def eh_regra(fmt) -> bool:
    """Quebra de pagina das regras do Word (nao e' do usuario)."""
    return bool(fmt.property(PROP_QUEBRA_REGRA))


def definir_regra(fmt, ligar: bool, motivo: int = 1) -> None:
    """Liga ou desliga a quebra das regras (a do usuario, a da secao e a do espacador ficam)."""
    if ligar:
        fmt.setPageBreakPolicy(fmt.pageBreakPolicy() | _ANTES)
        fmt.setProperty(PROP_QUEBRA_REGRA, int(motivo))
        return
    if not fmt.property(PROP_QUEBRA_REGRA):
        return
    fmt.clearProperty(PROP_QUEBRA_REGRA)
    from editdoc.ponte_qt import notas as pq_notas
    from editdoc.ponte_qt import secoes as pq_secoes
    bits = fmt.property(pq_secoes.PROP_QUEBRA_SECAO)
    bits = bits if isinstance(bits, int) and not isinstance(bits, bool) else 0
    if not pq_notas.eh_espacador(fmt) and not bits & 2:
        fmt.setPageBreakPolicy(QTextFormat.PageBreakFlag(_inteiro(fmt.pageBreakPolicy())
                                                         & ~_inteiro(_ANTES)))


def visivel(fmt) -> bool:
    return bool(fmt.property(PROP_WORD_VISIVEL))


def definir_visivel(fmt, ligar: bool) -> None:
    """Fundo transparente no paragrafo vazio antes da tabela (o Qt so' o mostra com fundo)."""
    if ligar:
        if not fmt.hasProperty(P.BackgroundBrush):
            fmt.setBackground(QBrush(QColor(0, 0, 0, 0)))
            fmt.setProperty(PROP_WORD_VISIVEL, True)
        return
    if fmt.property(PROP_WORD_VISIVEL):
        fmt.clearProperty(PROP_WORD_VISIVEL)
        fmt.clearProperty(P.BackgroundBrush)


def sem_compensacao(fmt):
    """Copia do formato (bloco ou tabela) com os valores de verdade e sem as marcas: o que o
    paragrafo tem para o usuario (copiar, comparar)."""
    novo = type(fmt)(fmt)
    if isinstance(novo, QTextBlockFormat):
        antes, depois, linha = antes_real(novo), depois_real(novo), linha_real(novo)
        if novo.hasProperty(PROP_WORD_ANTES):
            novo.clearProperty(PROP_WORD_ANTES)
            if antes is None:
                novo.clearProperty(P.BlockTopMargin)
            else:
                novo.setTopMargin(antes)
        if novo.hasProperty(PROP_WORD_DEPOIS):
            novo.clearProperty(PROP_WORD_DEPOIS)
            if depois is None:
                novo.clearProperty(P.BlockBottomMargin)
            else:
                novo.setBottomMargin(depois)
        if novo.hasProperty(PROP_WORD_LINHA):
            novo.clearProperty(PROP_WORD_LINHA)
            if linha is None:
                novo.clearProperty(P.LineHeight)
                novo.clearProperty(P.LineHeightType)
            else:
                novo.setLineHeight(linha[1], linha[0])
        definir_visivel(novo, False)
        definir_regra(novo, False)
    else:
        for prop_word, prop_qt in ((PROP_WORD_ANTES, P.FrameTopMargin),
                                   (PROP_WORD_DEPOIS, P.FrameBottomMargin)):
            if novo.hasProperty(prop_word):
                real, _c = _margem(novo, prop_word, prop_qt)
                novo.setProperty(prop_qt, float(real or 0.0))
                novo.clearProperty(prop_word)
    return novo


def esquecer(fmt, antes: bool = False, depois: bool = False, linha: bool = False) -> None:
    """O usuario deu um valor novo: a compensacao daquele campo sai (o valor do formato e'
    o de verdade ate' a proxima conferencia)."""
    if antes:
        fmt.clearProperty(PROP_WORD_ANTES)
    if depois:
        fmt.clearProperty(PROP_WORD_DEPOIS)
    if linha:
        fmt.clearProperty(PROP_WORD_LINHA)


# -- altura da linha --------------------------------------------------------------------------

_FATORES: dict = {}


def fator_da_familia(familia: str, dispositivo) -> float:
    """Razao entre a linha do Word e a do Qt (neste dispositivo e plataforma) para a familia.

    Medida na fonte de 100 pt: a altura do Word sai das tabelas da fonte (`QRawFont`), a do Qt
    do layout de uma linha (teto da ascendente + descendente + entrelinha, como o Qt usa). Fonte
    sem as tabelas: 1 (nada muda)."""
    chave = (familia, id(dispositivo))
    if chave in _FATORES:
        return _FATORES[chave]
    fator = 1.0
    try:
        fonte = QFont(familia)
        fonte.setPointSizeF(100.0)
        bruta = QRawFont.fromFont(fonte)
        if bruta.isValid():
            unidades = mod.unidades_da_linha_word(bytes(bruta.fontTable("head")),
                                                  bytes(bruta.fontTable("hhea")),
                                                  bytes(bruta.fontTable("OS/2")))
            if unidades is not None:
                upm, _win, word = unidades
                altura_word = word / upm * 100.0 * 20.0  # twips, a unidade do dispositivo
                doc = QTextDocument()
                doc.documentLayout().setPaintDevice(dispositivo)
                doc.setDocumentMargin(0)
                doc.setDefaultFont(fonte)
                doc.setPlainText("Xg")
                doc.documentLayout().documentSize()
                linha = doc.begin().layout().lineAt(0)
                altura_qt = math.ceil(linha.ascent() + linha.descent() + linha.leading())
                if altura_qt > 0:
                    fator = altura_word / altura_qt
                doc.documentLayout().setPaintDevice(None)
    except Exception:  # noqa: BLE001 - fonte estranha: a linha fica como o Qt a faz
        fator = 1.0
    if not 0.8 <= fator <= 1.3:
        fator = 1.0  # fora do razoavel: metrica quebrada, melhor nao mexer
    _FATORES[chave] = fator
    return fator


_ALTURAS: dict = {}


def altura_qt(familia: str, pontos: float, dispositivo) -> float:
    """A altura (twips) que o layout do Qt da' a uma linha de texto nesta fonte."""
    chave = (familia, round(pontos, 2), id(dispositivo))
    if chave not in _ALTURAS:
        fonte = QFont(familia)
        fonte.setPointSizeF(max(1.0, pontos))
        doc = QTextDocument()
        doc.documentLayout().setPaintDevice(dispositivo)
        doc.setDocumentMargin(0)
        doc.setDefaultFont(fonte)
        doc.setPlainText("Xg")
        doc.documentLayout().documentSize()
        linha = doc.begin().layout().lineAt(0)
        _ALTURAS[chave] = float(math.ceil(linha.ascent() + linha.descent() + linha.leading()))
        doc.documentLayout().setPaintDevice(None)
    return _ALTURAS[chave]


def fonte_do_bloco(bloco, padrao: QFont) -> tuple[str, float]:
    """(familia, pontos) do trecho de texto de maior tamanho (no empate, o primeiro)."""
    melhor: tuple[float, str] | None = None
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid():
            cf = frag.charFormat()
            if not cf.isImageFormat() and cf.objectType() == 0:
                melhor = _comparar(melhor, cf, padrao)
        it += 1
    if melhor is None:
        melhor = _comparar(None, bloco.charFormat(), padrao)
    return melhor[1], melhor[0]


def objeto_alto(bloco, altura_texto_tw: float) -> bool:
    """O bloco tem imagem (ou objeto) mais alta que 1,5 linha do texto."""
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid():
            cf = frag.charFormat()
            if cf.isImageFormat() and cf.toImageFormat().height() * 15.0 > 1.5 * altura_texto_tw:
                return True
        it += 1
    lay = bloco.layout()
    if lay is not None:
        for i in range(lay.lineCount()):
            if lay.lineAt(i).height() > 1.5 * altura_texto_tw + 1.0:
                return True
    return False


def familia_do_bloco(bloco, padrao: QFont) -> str:
    """A familia que manda na altura das linhas do bloco (ver `fonte_do_bloco`)."""
    return fonte_do_bloco(bloco, padrao)[0]


def _comparar(melhor, cf: QTextCharFormat, padrao: QFont):
    familias = cf.fontFamilies() or []
    familia = familias[0] if familias else padrao.family()
    tamanho = cf.fontPointSize() if cf.hasProperty(P.FontPointSize) else padrao.pointSizeF()
    if melhor is None or tamanho > melhor[0] + 1e-6:
        return (tamanho, familia)
    return melhor


def avanco_e_corte(fmt: QTextBlockFormat, linha) -> tuple[float, float]:
    """(quanto a linha avanca, altura que o Qt testa no pe' da pagina), como o
    `getLineHeightParams` do Qt 6.11, no dispositivo de 1440 dpi (x 15)."""
    altura = linha.height()
    bruta = math.ceil(linha.ascent() + linha.descent() + linha.leading())
    tipo = fmt.lineHeightType()
    valor = fmt.lineHeight()
    if tipo == PROPORCIONAL:
        return bruta * valor / 100.0, altura
    if tipo == FIXA:
        return valor * 15.0, valor * 15.0
    if tipo == MINIMA:
        v = max(bruta, valor * 15.0)
        return v, max(altura, valor * 15.0)
    if tipo == DISTANCIA:
        return bruta + valor * 15.0, altura
    return float(bruta), altura


def altura_do_vazio(bloco, fmt) -> float:
    """Altura (twips) da linha do paragrafo vazio `bloco` com a entrelinha do formato `fmt`.

    O vazio que o Qt esconde junto de uma tabela pode nao ter linha no layout: a altura vem
    entao da fonte do bloco."""
    lay = bloco.layout()
    if lay is not None and lay.lineCount() > 0:
        return avanco_e_corte(fmt, lay.lineAt(0))[0]
    from PySide6.QtGui import QFontMetricsF
    fonte = bloco.charFormat().font()
    return float(QFontMetricsF(fonte).height()) * 15.0 * 72.0 / 96.0


def fonte_da_marca(extras_ppr: str | None, estilos) -> dict:
    """A formatacao de caractere da marca de paragrafo (o w:rPr dentro do w:pPr): fonte e
    tamanho que o Word usa na linha do paragrafo vazio."""
    if not extras_ppr or "rPr" not in extras_ppr:
        return {}
    from lxml import etree

    from editdoc.formato_docx import estilos as fx_estilos
    try:
        raiz = etree.fromstring(extras_ppr.encode("utf8"),
                                etree.XMLParser(resolve_entities=False, no_network=True))
    except (etree.XMLSyntaxError, ValueError):
        return {}
    rpr = raiz.find("{%s}rPr" % mod.W)
    if rpr is None:
        return {}
    tema = {}
    bruto_tema = getattr(estilos, "tema_original", None)
    if bruto_tema:
        try:
            tema = fx_estilos.fontes_do_tema(etree.fromstring(
                bruto_tema, etree.XMLParser(resolve_entities=False, no_network=True)))
        except (etree.XMLSyntaxError, ValueError):
            tema = {}
    props = fx_estilos.props_de_rpr(rpr, tema)
    return {k: props[k] for k in ("fonte", "tamanho_meio_pt") if props.get(k) is not None}
