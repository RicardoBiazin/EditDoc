"""Estilos no QTextDocument (M6): onde o catalogo fica e como o formato do Qt se recompoe.

O Qt guarda a formatacao EFETIVA (estilo + direta) nos formatos de bloco e de caractere.
O id do estilo fica numa propriedade de usuario: PROP_ESTILO no bloco (estilo de
paragrafo; ausente = o estilo padrao) e PROP_ESTILO_CAR no caractere. O nivel de
estrutura efetivo (Titulo 1 = 0) fica em PROP_NIVEL no bloco: e' o que o painel de
navegacao le, sem consultar o catalogo.

Na volta (de_qt), formatacao direta = efetivo - estilo: o que difere do que o estilo daria.

O catalogo do documento fica no formato do quadro raiz (`rootFrame`), em JSON. Trocar o
formato do quadro raiz entra no desfazer do Qt, no mesmo passo do bloco de edicao aberto
(medido no Qt 6.11): por isso "Modificar estilo" desfaz o catalogo e os paragrafos juntos.
O PySide 6.11 nao exporta QAbstractUndoItem, que seria o outro caminho. O XML original e
o tema nao vao para o JSON: ficam no catalogo-base, guardado no proprio objeto do documento.

Cabecalho e rodape usam o catalogo do corpo (`_doc_estilos`).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextFormat)

from editdoc.modelo.estilos import CAMPOS_CARACTERE, CAMPOS_PARAGRAFO, Estilos, catalogo_padrao
from editdoc.modelo.unidades import px_de_twips, twips_de_px

_USUARIO = QTextFormat.Property.UserProperty.value
#: Bloco: id do estilo de paragrafo (ausente = estilo padrao).
PROP_ESTILO = _USUARIO + 4
#: Caractere: id do estilo de caractere.
PROP_ESTILO_CAR = _USUARIO + 5
#: Bloco: nivel de estrutura efetivo (0 a 8). Ausente = corpo de texto.
PROP_NIVEL = _USUARIO + 6
#: Quadro raiz: o catalogo em JSON.
PROP_CATALOGO = _USUARIO + 7

P = QTextFormat.Property
_PROPORCIONAL = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
_ALINHAMENTO = {
    "esquerda": Qt.AlignmentFlag.AlignLeft,
    "centro": Qt.AlignmentFlag.AlignHCenter,
    "direita": Qt.AlignmentFlag.AlignRight,
    "justificado": Qt.AlignmentFlag.AlignJustify,
}
#: Propriedades do Qt que a formatacao de caractere ocupa (limpas antes de recompor).
PROPS_QT_CARACTERE = (P.FontWeight, P.FontItalic, P.TextUnderlineStyle, P.FontUnderline,
                      P.FontStrikeOut, P.TextVerticalAlignment, P.FontPointSize,
                      P.FontFamilies, P.FontFamily, P.ForegroundBrush)
PROPS_QT_BLOCO = (P.BlockAlignment, P.BlockLeftMargin, P.BlockRightMargin, P.TextIndent,
                  P.BlockTopMargin, P.BlockBottomMargin, P.LineHeight, P.LineHeightType)


# -- catalogo no documento --------------------------------------------------------

def _doc_do_catalogo(doc: QTextDocument) -> QTextDocument:
    """O documento que guarda o catalogo: o corpo, mesmo para o cabecalho e o rodape."""
    return getattr(doc, "_doc_estilos", None) or doc


def catalogo(doc: QTextDocument) -> Estilos:
    """O catalogo vigente do documento (o do corpo, para cabecalho e rodape)."""
    doc = _doc_do_catalogo(doc)
    base = getattr(doc, "_estilos_base", None)
    if base is None:
        base = catalogo_padrao()
        doc._estilos_base = base
    bruto = doc.rootFrame().frameFormat().property(PROP_CATALOGO)
    if not isinstance(bruto, str) or not bruto:
        return base
    cache = getattr(doc, "_estilos_cache", None)
    if cache is not None and cache[0] == bruto:
        return cache[1]
    estilos = Estilos.de_json(bruto, base)
    doc._estilos_cache = (bruto, estilos)
    return estilos


def definir_catalogo_base(doc: QTextDocument, estilos: Estilos | None) -> None:
    """Catalogo ao abrir (ou no documento novo). Nao entra no desfazer: tira a propriedade."""
    doc._estilos_base = estilos if estilos is not None else catalogo_padrao()
    doc._estilos_cache = None
    quadro = doc.rootFrame()
    ff = quadro.frameFormat()
    if ff.hasProperty(PROP_CATALOGO):
        ff.clearProperty(PROP_CATALOGO)
        quadro.setFrameFormat(ff)


def trocar_catalogo(doc: QTextDocument, estilos: Estilos) -> None:
    """Grava o catalogo novo no quadro raiz. Dentro de um beginEditBlock, fica no mesmo passo."""
    doc = _doc_do_catalogo(doc)
    quadro = doc.rootFrame()
    ff = quadro.frameFormat()
    ff.setProperty(PROP_CATALOGO, estilos.para_json())
    quadro.setFrameFormat(ff)


def assinatura(doc: QTextDocument) -> str:
    """Muda quando o catalogo muda (para a galeria saber se redesenha)."""
    doc = _doc_do_catalogo(doc)
    bruto = doc.rootFrame().frameFormat().property(PROP_CATALOGO)
    return f"{id(getattr(doc, '_estilos_base', None))}:{bruto if isinstance(bruto, str) else ''}"


# -- leitura do formato do Qt -----------------------------------------------------

def props_de_caractere(cf: QTextCharFormat) -> dict:
    """Formatacao de caractere efetiva que o modelo entende (campos de Run)."""
    out: dict = {}
    if cf.hasProperty(P.FontWeight):
        out["negrito"] = cf.fontWeight() >= 600
    if cf.hasProperty(P.FontItalic):
        out["italico"] = cf.fontItalic()
    if cf.hasProperty(P.TextUnderlineStyle) or cf.hasProperty(P.FontUnderline):
        out["sublinhado"] = cf.underlineStyle() != QTextCharFormat.UnderlineStyle.NoUnderline
    if cf.hasProperty(P.FontStrikeOut):
        out["tachado"] = cf.fontStrikeOut()
    if cf.hasProperty(P.TextVerticalAlignment):
        va = cf.verticalAlignment()
        out["subscrito"] = va == QTextCharFormat.VerticalAlignment.AlignSubScript
        out["sobrescrito"] = va == QTextCharFormat.VerticalAlignment.AlignSuperScript
    if cf.hasProperty(P.FontPointSize):
        out["tamanho_meio_pt"] = round(cf.fontPointSize() * 2)
    if cf.hasProperty(P.FontFamilies):
        familias = cf.fontFamilies() or []
        if familias:
            out["fonte"] = familias[0]
    if cf.hasProperty(P.ForegroundBrush):
        out["cor_hex"] = cf.foreground().color().name()[1:].upper()
    return out


def _alinhamento(bf: QTextBlockFormat) -> str | None:
    if not bf.hasProperty(P.BlockAlignment):
        return None
    flags = bf.alignment()
    if flags & Qt.AlignmentFlag.AlignHCenter:
        return "centro"
    if flags & Qt.AlignmentFlag.AlignRight:
        return "direita"
    if flags & Qt.AlignmentFlag.AlignJustify:
        return "justificado"
    if flags & Qt.AlignmentFlag.AlignLeft:
        return "esquerda"
    return None


def props_de_bloco(bf: QTextBlockFormat) -> dict:
    """Formatacao de paragrafo efetiva (campos de Paragrafo) e o "nivel"."""
    out: dict = {}
    alinhamento = _alinhamento(bf)
    if alinhamento is not None:
        out["alinhamento"] = alinhamento
    if bf.hasProperty(P.BlockLeftMargin):
        out["recuo_esquerdo_tw"] = twips_de_px(bf.leftMargin())
    if bf.hasProperty(P.BlockRightMargin):
        out["recuo_direito_tw"] = twips_de_px(bf.rightMargin())
    if bf.hasProperty(P.TextIndent):
        out["recuo_primeira_linha_tw"] = twips_de_px(bf.textIndent())
    if bf.hasProperty(P.BlockTopMargin):
        out["espaco_antes_tw"] = twips_de_px(bf.topMargin())
    if bf.hasProperty(P.BlockBottomMargin):
        out["espaco_depois_tw"] = twips_de_px(bf.bottomMargin())
    if bf.hasProperty(P.LineHeight) and bf.lineHeightType() == _PROPORCIONAL:
        out["espacamento_linha_pct"] = round(bf.lineHeight())
    nivel = bf.property(PROP_NIVEL)
    if isinstance(nivel, int) and 0 <= nivel <= 8:
        out["nivel"] = nivel
    return out


def estilo_do_bloco(bf: QTextBlockFormat) -> str | None:
    sid = bf.property(PROP_ESTILO)
    return sid if isinstance(sid, str) and sid else None


def estilo_do_caractere(cf: QTextCharFormat) -> str | None:
    sid = cf.property(PROP_ESTILO_CAR)
    return sid if isinstance(sid, str) and sid else None


def nivel_do_bloco(bloco) -> int | None:
    nivel = bloco.blockFormat().property(PROP_NIVEL)
    return nivel if isinstance(nivel, int) and 0 <= nivel <= 8 else None


# -- escrita no formato do Qt -----------------------------------------------------

def aplicar_caractere(cf: QTextCharFormat, props: dict) -> None:
    """Grava no formato as propriedades de caractere (sem limpar as que nao estao em props)."""
    if props.get("negrito") is not None:
        cf.setFontWeight(QFont.Weight.Bold if props["negrito"] else QFont.Weight.Normal)
    if props.get("italico") is not None:
        cf.setFontItalic(props["italico"])
    if props.get("sublinhado") is not None:
        cf.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline if props["sublinhado"]
                             else QTextCharFormat.UnderlineStyle.NoUnderline)
    if props.get("tachado") is not None:
        cf.setFontStrikeOut(props["tachado"])
    sub, sob = props.get("subscrito"), props.get("sobrescrito")
    if sub is not None or sob is not None:
        if sub:
            va = QTextCharFormat.VerticalAlignment.AlignSubScript
        elif sob:
            va = QTextCharFormat.VerticalAlignment.AlignSuperScript
        else:
            va = QTextCharFormat.VerticalAlignment.AlignNormal
        cf.setVerticalAlignment(va)
    if props.get("tamanho_meio_pt") is not None:
        cf.setFontPointSize(props["tamanho_meio_pt"] / 2)
    if props.get("fonte"):
        cf.setFontFamilies([props["fonte"]])
    if props.get("cor_hex") is not None:
        cf.setForeground(QBrush(QColor("#" + props["cor_hex"])))


def aplicar_bloco(bf: QTextBlockFormat, props: dict) -> None:
    """Grava no formato de bloco as propriedades de paragrafo de `props`."""
    if props.get("alinhamento") is not None:
        bf.setAlignment(_ALINHAMENTO[props["alinhamento"]])
    if props.get("recuo_esquerdo_tw") is not None:
        bf.setLeftMargin(px_de_twips(props["recuo_esquerdo_tw"]))
    if props.get("recuo_direito_tw") is not None:
        bf.setRightMargin(px_de_twips(props["recuo_direito_tw"]))
    if props.get("recuo_primeira_linha_tw") is not None:
        bf.setTextIndent(px_de_twips(props["recuo_primeira_linha_tw"]))
    if props.get("espaco_antes_tw") is not None:
        bf.setTopMargin(px_de_twips(props["espaco_antes_tw"]))
    if props.get("espaco_depois_tw") is not None:
        bf.setBottomMargin(px_de_twips(props["espaco_depois_tw"]))
    if props.get("espacamento_linha_pct") is not None:
        bf.setLineHeight(float(props["espacamento_linha_pct"]), _PROPORCIONAL)
    if props.get("nivel") is not None and 0 <= props["nivel"] <= 8:
        bf.setProperty(PROP_NIVEL, int(props["nivel"]))


def formato_de_caractere(props: dict, sid_car: str | None = None) -> QTextCharFormat:
    cf = QTextCharFormat()
    aplicar_caractere(cf, props)
    if sid_car:
        cf.setProperty(PROP_ESTILO_CAR, sid_car)
    return cf


def marcar_estilo(bf: QTextBlockFormat, sid: str | None, estilos: Estilos) -> None:
    """PROP_ESTILO no bloco; o estilo padrao nao e' gravado (ausente = padrao)."""
    if sid and sid != estilos.id_padrao():
        bf.setProperty(PROP_ESTILO, sid)
    else:
        bf.clearProperty(PROP_ESTILO)


# -- recomposicao: estilo novo, formatacao direta mantida ----------------------------

def direto(efetivo: dict, base: dict, campos) -> dict:
    """Formatacao direta: o que o efetivo tem e difere da base do estilo."""
    return {k: efetivo[k] for k in campos if efetivo.get(k) is not None
            and efetivo.get(k) != base.get(k)}


def recompor_caractere(cf: QTextCharFormat, base_velha: dict, base_nova: dict,
                       sid_car: str | None | type(...) = ...) -> QTextCharFormat:
    """Formato novo: o que era igual a base velha passa a ser a base nova; o direto fica.

    `sid_car` troca o estilo de caractere (None tira); `...` mantem o do formato.
    """
    atual = props_de_caractere(cf)
    proprio = direto(atual, base_velha, CAMPOS_CARACTERE)
    novo = QTextCharFormat(cf)
    for prop in PROPS_QT_CARACTERE:
        novo.clearProperty(prop)
    aplicar_caractere(novo, {**base_nova, **proprio})
    if sid_car is not ...:
        if sid_car:
            novo.setProperty(PROP_ESTILO_CAR, sid_car)
        else:
            novo.clearProperty(PROP_ESTILO_CAR)
    return novo


def recompor_bloco(bf: QTextBlockFormat, base_velha: dict, base_nova: dict,
                   sid: str | None, estilos: Estilos, manter_direto: bool = True) -> QTextBlockFormat:
    """Formato de bloco novo com o estilo `sid`; lista, quebra e marcas do bloco ficam."""
    atual = props_de_bloco(bf)
    campos = (*CAMPOS_PARAGRAFO, "nivel")
    proprio = direto(atual, base_velha, campos) if manter_direto else {}
    novo = QTextBlockFormat(bf)
    for prop in PROPS_QT_BLOCO:
        novo.clearProperty(prop)
    novo.clearProperty(PROP_NIVEL)
    aplicar_bloco(novo, {**base_nova, **proprio})
    marcar_estilo(novo, sid, estilos)
    return novo


class Resolvedor:
    """Cache das resolucoes de um catalogo, para recompor muitos blocos de uma vez."""

    def __init__(self, estilos: Estilos) -> None:
        self.estilos = estilos
        self._par: dict = {}
        self._car: dict = {}

    def paragrafo(self, sid: str | None) -> tuple[dict, dict]:
        sid = sid or self.estilos.id_padrao()
        if sid not in self._par:
            self._par[sid] = self.estilos.resolver_paragrafo(sid)
        return self._par[sid]

    def caractere(self, sid_par: str | None, sid_car: str | None) -> dict:
        chave = (sid_par or self.estilos.id_padrao(), sid_car)
        if chave not in self._car:
            self._car[chave] = self.estilos.base_de_caractere(*chave)
        return self._car[chave]


def trechos_do_bloco(bloco) -> list[tuple[int, int, QTextCharFormat]]:
    """(inicio, fim, formato) de cada fragmento do bloco, lidos antes de mexer."""
    saida = []
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid():
            saida.append((frag.position(), frag.position() + frag.length(), frag.charFormat()))
        it += 1
    return saida


def recompor_blocos(doc: QTextDocument, blocos, velho: Resolvedor, novo: Resolvedor,
                    sid_novo=..., manter_direto_paragrafo: bool = True,
                    trecho=None, car_novo=..., limpar_direto: bool = False,
                    filtro=None, mexer_no_bloco: bool = True) -> None:
    """Recompoe os blocos (e o texto deles) do catalogo velho para o novo.

    `sid_novo`: o estilo de paragrafo que os blocos passam a ter (`...` = o que tinham).
    `trecho`: (inicio, fim) para recompor so' o texto desse trecho (o bloco, sim).
    `car_novo`: estilo de caractere do texto recomposto (`...` = o que tinha; None tira).
    `limpar_direto`: o texto perde a formatacao direta (Limpar formatacao).
    `filtro(sid_par, sid_car)`: so' recompoe o que o filtro aceita (Modificar estilo).
    `mexer_no_bloco`: False deixa o formato do bloco como esta' (estilo de caractere).
    Quem chama abre e fecha o bloco de edicao.
    """
    vazio: dict = {}
    for bloco in list(blocos):
        bf = bloco.blockFormat()
        sid_velho = estilo_do_bloco(bf)
        sid = sid_velho if sid_novo is ... else sid_novo
        if mexer_no_bloco and (filtro is None or filtro(sid_velho, None)):
            par_velho, _ = velho.paragrafo(sid_velho)
            par_novo, _ = novo.paragrafo(sid)
            nbf = recompor_bloco(bf, par_velho, par_novo, sid, novo.estilos, manter_direto_paragrafo)
            if nbf != bf:
                QTextCursor(bloco).setBlockFormat(nbf)
        # Formato do bloco vazio (altura da linha e o que se digita nele).
        bcf = bloco.charFormat()
        sid_car_b = estilo_do_caractere(bcf)
        if mexer_no_bloco and (filtro is None or filtro(sid_velho, sid_car_b)):
            nbcf = recompor_caractere(bcf, velho.caractere(sid_velho, sid_car_b),
                                      novo.caractere(sid, sid_car_b))
            if nbcf != bcf:
                QTextCursor(bloco).setBlockCharFormat(nbcf)
        for inicio, fim, cf in trechos_do_bloco(bloco):
            if trecho is not None:
                inicio, fim = max(inicio, trecho[0]), min(fim, trecho[1])
                if inicio >= fim:
                    continue
            if cf.isImageFormat():
                continue
            sid_car = estilo_do_caractere(cf)
            if filtro is not None and not filtro(sid_velho, sid_car):
                continue
            car = sid_car if car_novo is ... else car_novo
            base_velha = velho.caractere(sid_velho, sid_car)
            if limpar_direto:
                # Tudo o que o texto tinha passa a ser "igual ao estilo velho" e cai.
                base_velha = props_de_caractere(cf)
            ncf = recompor_caractere(cf, base_velha, novo.caractere(sid, car) or vazio, car)
            if ncf != cf:
                c = QTextCursor(doc)
                c.setPosition(inicio)
                c.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
                c.setCharFormat(ncf)
