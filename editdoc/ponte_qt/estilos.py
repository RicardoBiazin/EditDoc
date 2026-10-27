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

Unidades (0.1.4): o layout do Qt 6.11, no dispositivo de 1440 dpi, escala as margens
VERTICAIS do bloco (px96 x 15), mas NAO as horizontais (medido: leftMargin 96 poe a linha
em x = 96; topMargin 96 desce o bloco 1440). Por isso recuo esquerdo, direito e da primeira
linha ficam no formato do bloco em twips (a unidade do dispositivo), e espaco antes e
depois em px96. Antes da 0.1.4 os recuos iam em px96 e apareciam 15 vezes menores.

Listas (0.1.4): o recuo do nivel da lista (w:lvl/w:pPr/w:ind) fica entre o estilo e a
formatacao direta (`Resolvedor.paragrafo` com a lista); o recuo da primeira linha de um item
de lista e' o de verdade em PROP_RECUO_REAL (`ponte_qt/listas.py`), nao o textIndent.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextFormat)

from editdoc.modelo.estilos import CAMPOS_CARACTERE, CAMPOS_PARAGRAFO, Estilos, catalogo_padrao
from editdoc.modelo.numeracao import lista_efetiva, recuos_do_nivel
from editdoc.modelo.unidades import px_de_twips, twips_de_px

_USUARIO = QTextFormat.Property.UserProperty.value
#: Tipo do objeto opaco (o mesmo de ponte_qt/opacos.py, sem importar o modulo).
TIPO_OPACO = QTextFormat.ObjectTypes.UserObject.value + 2
#: Bloco: id do estilo de paragrafo (ausente = estilo padrao).
PROP_ESTILO = _USUARIO + 4
#: Caractere: id do estilo de caractere.
PROP_ESTILO_CAR = _USUARIO + 5
#: Bloco: nivel de estrutura efetivo (0 a 8). Ausente = corpo de texto.
PROP_NIVEL = _USUARIO + 6
#: Quadro raiz: o catalogo em JSON.
PROP_CATALOGO = _USUARIO + 7
#: Listas (0.1.4, ponte_qt/listas.py): numId e ilvl diretos e o recuo de verdade do item.
PROP_LISTA = _USUARIO + 23
PROP_LISTA_NIVEL = _USUARIO + 24
PROP_RECUO_REAL = _USUARIO + 25


def _inteiro(valor) -> int | None:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None

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
    from editdoc.ponte_qt import listas  # import tardio: listas usa este modulo
    numeracao = listas.catalogo(doc)
    bruto = doc.rootFrame().frameFormat().property(PROP_CATALOGO)
    if not isinstance(bruto, str) or not bruto:
        base.numeracao_doc = numeracao
        return base
    cache = getattr(doc, "_estilos_cache", None)
    if cache is not None and cache[0] == bruto:
        cache[1].numeracao_doc = numeracao
        return cache[1]
    estilos = Estilos.de_json(bruto, base)
    estilos.numeracao_doc = numeracao
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


#: Bloco ou tabela (0.1.12): o recuo direito escondido de uma secao mais estreita que a mais larga
#: (o QTextDocument tem uma largura so'), em JSON [extra, recuo total aplicado]. O recuo do
#: usuario e' o total menos o extra, enquanto o recuo do bloco continuar o total aplicado; se
#: alguem trocou o recuo (formatacao, estilo), o valor novo e' do usuario.
PROP_RECUO_SECAO = QTextFormat.Property.UserProperty.value + 37


def recuo_secao(fmt) -> tuple[float, float] | None:
    """(extra, total aplicado) do recuo escondido da secao, ou None."""
    valor = fmt.property(PROP_RECUO_SECAO)
    if isinstance(valor, str) and valor:
        try:
            extra, total = (float(x) for x in valor.split(";"))
            return extra, total
        except ValueError:
            return None
    return None


def recuo_direito_real(bf) -> float:
    """O recuo direito do usuario: o do bloco sem o extra escondido da secao (0.1.12)."""
    atual = bf.rightMargin()
    escondido = recuo_secao(bf)
    if escondido is not None and abs(atual - escondido[1]) < 0.5:
        return atual - escondido[0]
    return atual


#: Bloco ou tabela do primeiro nivel (0.1.27): o deslocamento que leva o recuo esquerdo negativo
#: para dentro do documento. O Qt nao aceita recuo esquerdo negativo (a linha comeca no x 0 do
#: quadro e fica com a largura do corpo); o documento fica `D` twips mais largo, com o corpo
#: comecando `D` twips antes da margem (`LayoutPaginado.desvio`), e todo bloco e tabela do
#: primeiro nivel ganha `D` no recuo esquerdo. Texto "extra;total;tinha": o extra (D), o recuo
#: total aplicado (twips no bloco, px96 na tabela) e se o bloco tinha o recuo esquerdo antes
#: (1/0). Como no PROP_RECUO_SECAO: o recuo do usuario e' o total menos o extra enquanto o
#: formato tiver o total; se alguem trocou o recuo, o valor novo e' do usuario.
PROP_RECUO_DESLOCADO = QTextFormat.Property.UserProperty.value + 51


def recuo_deslocado(fmt) -> tuple[float, float, bool] | None:
    """(extra, total aplicado, tinha o recuo) do deslocamento do recuo negativo, ou None."""
    valor = fmt.property(PROP_RECUO_DESLOCADO)
    if isinstance(valor, str) and valor.count(";") == 2:
        try:
            extra, total, tinha = valor.split(";")
            return float(extra), float(total), tinha == "1"
        except ValueError:
            return None
    return None


def _deslocamento_valido(bf) -> tuple[float, float, bool] | None:
    d = recuo_deslocado(bf)
    if d is not None and bf.hasProperty(P.BlockLeftMargin) and abs(bf.leftMargin() - d[1]) < 0.5:
        return d
    return None


def deslocamento_esquerdo(bf) -> float:
    """O extra do recuo negativo no recuo esquerdo do bloco (0.1.27), ou 0."""
    d = _deslocamento_valido(bf)
    return d[0] if d is not None else 0.0


def recuo_esquerdo_real(bf) -> float:
    """O recuo esquerdo do usuario (twips): o do bloco sem o deslocamento do recuo negativo."""
    return bf.leftMargin() - deslocamento_esquerdo(bf)


def tem_recuo_esquerdo(bf) -> bool:
    """O bloco tem recuo esquerdo do usuario (o deslocamento sozinho nao conta)."""
    d = _deslocamento_valido(bf)
    if d is not None:
        return d[2] or abs(bf.leftMargin() - d[0]) >= 0.5
    return bf.hasProperty(P.BlockLeftMargin)


def definir_recuo_esquerdo(bf, real_tw: float) -> None:
    """Grava o recuo esquerdo do usuario mantendo o deslocamento do recuo negativo, se houver."""
    d = _deslocamento_valido(bf)
    if d is None:
        if bf.hasProperty(PROP_RECUO_DESLOCADO):
            bf.clearProperty(PROP_RECUO_DESLOCADO)
        bf.setLeftMargin(float(real_tw))
        return
    total = float(real_tw) + d[0]
    bf.setLeftMargin(total)
    bf.setProperty(PROP_RECUO_DESLOCADO, f"{d[0]};{total};1")


def props_de_bloco(bf: QTextBlockFormat) -> dict:
    """Formatacao de paragrafo efetiva (campos de Paragrafo) e o "nivel"."""
    out: dict = {}
    alinhamento = _alinhamento(bf)
    if alinhamento is not None:
        out["alinhamento"] = alinhamento
    if tem_recuo_esquerdo(bf):
        out["recuo_esquerdo_tw"] = round(recuo_esquerdo_real(bf))
    if bf.hasProperty(P.BlockRightMargin):
        real = recuo_direito_real(bf)
        if real != 0 or recuo_secao(bf) is None:
            out["recuo_direito_tw"] = round(real)
    if bf.hasProperty(PROP_RECUO_REAL):
        # Item de lista (0.1.4): o textIndent e' o visual (texto depois do numero).
        real = bf.property(PROP_RECUO_REAL)
        if isinstance(real, int) and not isinstance(real, bool):
            out["recuo_primeira_linha_tw"] = real
    elif bf.hasProperty(P.TextIndent):
        out["recuo_primeira_linha_tw"] = round(bf.textIndent())
    # 0.1.17: os valores de verdade, sem a compensacao do layout do Word (ponte_qt/paginacao.py).
    from editdoc.ponte_qt import paginacao as pq_paginacao  # import tardio: ele usa o modelo
    antes, depois = pq_paginacao.antes_real(bf), pq_paginacao.depois_real(bf)
    if antes is not None:
        out["espaco_antes_tw"] = twips_de_px(antes)
    if depois is not None:
        out["espaco_depois_tw"] = twips_de_px(depois)
    linha = pq_paginacao.linha_real(bf)
    if linha is not None and linha[0] == _PROPORCIONAL:
        out["espacamento_linha_pct"] = round(linha[1])
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
        definir_recuo_esquerdo(bf, float(props["recuo_esquerdo_tw"]))
    if props.get("recuo_direito_tw") is not None:
        bf.setRightMargin(float(props["recuo_direito_tw"]))
    if props.get("recuo_primeira_linha_tw") is not None:
        bf.setTextIndent(float(props["recuo_primeira_linha_tw"]))
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
    # 0.1.27: o deslocamento do recuo negativo volta na conferencia seguinte (desvio.py).
    novo.clearProperty(PROP_RECUO_DESLOCADO)
    # 0.1.17: espaco e entrelinha vem do zero; a compensacao do layout e' refeita depois.
    from editdoc.ponte_qt import paginacao as pq_paginacao
    pq_paginacao.esquecer(novo, antes=True, depois=True, linha=True)
    # O recuo da primeira linha passa a ser o de verdade; o visual da lista volta no ajuste.
    novo.clearProperty(PROP_RECUO_REAL)
    aplicar_bloco(novo, {**base_nova, **proprio})
    marcar_estilo(novo, sid, estilos)
    return novo


class Resolvedor:
    """Cache das resolucoes de um catalogo, para recompor muitos blocos de uma vez."""

    def __init__(self, estilos: Estilos, numeracao=None) -> None:
        self.estilos = estilos
        #: catalogo de numeracao (0.1.4): o do documento, que `catalogo(doc)` pendura no estilo
        self.numeracao = numeracao if numeracao is not None else getattr(estilos, "numeracao_doc", None)
        self._par: dict = {}
        self._car: dict = {}

    def paragrafo(self, sid: str | None, em_tabela: bool = False,
                  lista: tuple = (None, None)) -> tuple[dict, dict]:
        """O estilo resolvido; fora da tabela, com o docDefaults por baixo (M8). Com a lista
        do bloco (numId e ilvl diretos), o recuo do nivel fica por cima do estilo (0.1.4)."""
        sid = sid or self.estilos.id_padrao()
        chave = (sid, bool(em_tabela))
        if chave not in self._par:
            self._par[chave] = self.estilos.resolver_paragrafo(sid, com_padrao=not em_tabela)
        if self.numeracao is None:
            return self._par[chave]
        chave_lista = (sid, bool(em_tabela), tuple(lista))
        if chave_lista not in self._par:
            efetiva = lista_efetiva(lista[0], lista[1], sid, self.estilos, self.numeracao)
            extra = recuos_do_nivel(self.numeracao.nivel_de(*efetiva, self.estilos)) \
                if efetiva is not None else {}
            par, car = self._par[chave]
            self._par[chave_lista] = ({**par, **extra}, car) if extra else (par, car)
        return self._par[chave_lista]

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
            em_tabela = QTextCursor(bloco).currentTable() is not None
            lista = (_inteiro(bf.property(PROP_LISTA)), _inteiro(bf.property(PROP_LISTA_NIVEL)))
            par_velho, _ = velho.paragrafo(sid_velho, em_tabela, lista)
            par_novo, _ = novo.paragrafo(sid, em_tabela, lista)
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
            if cf.isImageFormat() or cf.objectType() == TIPO_OPACO:
                continue  # imagem e objeto opaco (0.1.2) nao recebem a fonte do estilo
            sid_car = estilo_do_caractere(cf)
            if filtro is not None and not filtro(sid_velho, sid_car):
                continue
            car = sid_car if car_novo is ... else car_novo
            base_velha = velho.caractere(sid_velho, sid_car)
            if limpar_direto:
                # Tudo o que o texto tinha passa a ser "igual ao estilo velho" e cai.
                base_velha = props_de_caractere(cf)
            ncf = recompor_caractere(cf, base_velha, novo.caractere(sid, car) or vazio, car)
            if limpar_direto:
                # As propriedades preservadas (realce, versalete... 0.1.5) tambem saem.
                from editdoc.ponte_qt import propriedades as pq_props  # import tardio
                pq_props.tirar_rpr(ncf)
            if ncf != cf:
                c = QTextCursor(doc)
                c.setPosition(inicio)
                c.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
                c.setCharFormat(ncf)
