"""Listas no QTextDocument (0.1.4): referencia no bloco, catalogo no documento, numero pintado.

Decisao: o EditDoc NAO usa o QTextList. O QTextList so' conta um nivel (o numero e' a
posicao do bloco na lista) e so' tem disco, circulo e quadrado; nao faz "1.1.1", nao
continua a contagem entre listas separadas, nao reinicia por nivel, nao mostra o simbolo
na fonte Symbol ou Wingdings, nem o marcador de figura, e poe o numero sempre colado a
esquerda do texto, sem o recuo deslocado e a tabulacao do Word. Em vez disso:

- o bloco guarda a referencia do arquivo: PROP_LISTA (numId direto; 0 = sem lista) e
  PROP_LISTA_NIVEL (ilvl direto). Ausente = herda do estilo, como o paragrafo do modelo;
- o catalogo (modelo/numeracao.py) fica como os estilos: o do arquivo num atributo do
  documento, e os acrescimos do EditDoc em JSON no formato do quadro raiz, que entra no
  desfazer junto com o bloco de edicao aberto (PROP_NUMERACAO);
- o `Numerador` do documento calcula o texto de cada item com o `Contador` do modelo (o
  mesmo da exportacao em texto), e `desenhar_rotulos` pinta o numero na folha, na funcao
  unica de pintura: tela, PDF e impressao mostram o mesmo;
- o texto da primeira linha comeca onde o Word o poria: depois do numero e da tabulacao
  (w:suff), no recuo deslocado ou na proxima parada de tabulacao. O Qt so' sabe disso pelo
  recuo da primeira linha do bloco: o recuo de verdade (o do arquivo) fica em
  PROP_RECUO_REAL, e o `textIndent` do bloco recebe o recuo visual (`ajustar_recuos`).
  Quem escreve um recuo da primeira linha novo tira PROP_RECUO_REAL; `props_de_bloco`
  (ponte_qt/estilos.py) le o de verdade.

O ajuste do recuo visual muda o formato do bloco: depois de uma edicao ele entra no mesmo
passo de desfazer (joinPreviousEditBlock), e ao abrir o documento vem antes de o desfazer
ser zerado. Num estado ja' ajustado (depois de um desfazer, por exemplo) nao muda nada.
"""

from __future__ import annotations

import math
import weakref

from PySide6.QtCore import QPointF, QRectF, QTimer
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QTextBlockFormat,
                           QTextCursor, QTextDocument, QTextFormat)

from editdoc import log_interno
from editdoc.modelo.numeracao import (Contador, Numeracao, Rotulo, lista_efetiva,
                                      texto_visivel)

log = log_interno.obter(__name__)

_USUARIO = QTextFormat.Property.UserProperty.value
#: Bloco: numId direto (int; 0 = sem lista, mesmo que o estilo tenha).
PROP_LISTA = _USUARIO + 23
#: Bloco: ilvl direto (0 a 8).
PROP_LISTA_NIVEL = _USUARIO + 24
#: Bloco: o recuo da primeira linha de verdade (twips, int) ou SEM_RECUO (o bloco nao tem).
PROP_RECUO_REAL = _USUARIO + 25
#: Valor de PROP_RECUO_REAL sem recuo. Nao pode ser "": o PySide devolve a string vazia como
#: lista vazia (ver CLAUDE.md), e a comparacao nunca bateria.
SEM_RECUO = "nenhum"
#: Bloco: o Backspace tirou o numero; o proximo Backspace no inicio tira o recuo.
PROP_SAIU_DA_LISTA = _USUARIO + 26
#: Quadro raiz: os acrescimos ao catalogo de numeracao (JSON).
PROP_NUMERACAO = _USUARIO + 27
#: Propriedades de lista do bloco (o Enter as copia para o bloco novo, como o Word).
PROPS_DE_LISTA = (PROP_LISTA, PROP_LISTA_NIVEL, PROP_RECUO_REAL, PROP_SAIU_DA_LISTA)
#: Bloco estrutural (o que o Qt exige antes da tabela): mesmo numero de para_qt.
_PROP_ESTRUTURAL = _USUARIO + 3

# -- catalogo no documento ----------------------------------------------------------

def _doc_do_catalogo(doc: QTextDocument) -> QTextDocument:
    """O documento que guarda o catalogo: o corpo, mesmo para o cabecalho e o rodape."""
    return getattr(doc, "_doc_estilos", None) or doc


def catalogo(doc: QTextDocument) -> Numeracao | None:
    """O catalogo vigente: o do arquivo e os acrescimos do EditDoc (que se desfazem)."""
    doc = _doc_do_catalogo(doc)
    base = getattr(doc, "_numeracao_base", None)
    bruto = doc.rootFrame().frameFormat().property(PROP_NUMERACAO)
    if not isinstance(bruto, str) or not bruto:
        return base
    cache = getattr(doc, "_numeracao_cache", None)
    if cache is not None and cache[0] == bruto and cache[1] is base:
        return cache[2]
    cat = (base if base is not None else Numeracao()).com_adicoes(bruto)
    doc._numeracao_cache = (bruto, base, cat)
    return cat


def definir_catalogo_base(doc: QTextDocument, cat: Numeracao | None) -> None:
    """Catalogo ao abrir. Nao entra no desfazer: tira a propriedade do quadro raiz."""
    doc._numeracao_base = cat
    doc._numeracao_cache = None
    quadro = doc.rootFrame()
    ff = quadro.frameFormat()
    if ff.hasProperty(PROP_NUMERACAO):
        ff.clearProperty(PROP_NUMERACAO)
        quadro.setFrameFormat(ff)


def trocar_catalogo(doc: QTextDocument, cat: Numeracao) -> None:
    """Grava os acrescimos no quadro raiz. Dentro de um beginEditBlock, fica no mesmo passo."""
    doc = _doc_do_catalogo(doc)
    if getattr(doc, "_numeracao_base", None) is None:
        base = Numeracao(tab_padrao_tw=cat.tab_padrao_tw)
        doc._numeracao_base = base
    quadro = doc.rootFrame()
    ff = quadro.frameFormat()
    ff.setProperty(PROP_NUMERACAO, cat.adicoes_json())
    quadro.setFrameFormat(ff)


def assinatura(doc: QTextDocument) -> tuple:
    doc = _doc_do_catalogo(doc)
    bruto = doc.rootFrame().frameFormat().property(PROP_NUMERACAO)
    return (id(getattr(doc, "_numeracao_base", None)), bruto if isinstance(bruto, str) else "")


# -- referencia no bloco ---------------------------------------------------------------

def _inteiro(valor) -> int | None:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


def lista_do_bloco(bf: QTextBlockFormat) -> tuple[int | None, int | None]:
    """(numId, ilvl) diretos do bloco; None = herda do estilo."""
    return _inteiro(bf.property(PROP_LISTA)), _inteiro(bf.property(PROP_LISTA_NIVEL))


def marcar_lista(bf: QTextBlockFormat, num: int | None, nivel: int | None) -> None:
    for prop, valor in ((PROP_LISTA, num), (PROP_LISTA_NIVEL, nivel)):
        if valor is None:
            bf.clearProperty(prop)
        else:
            bf.setProperty(prop, int(valor))


def recuo_real(bf: QTextBlockFormat) -> int | None:
    """O recuo da primeira linha de verdade (twips), ou None se o bloco nao tem."""
    if bf.hasProperty(PROP_RECUO_REAL):
        valor = bf.property(PROP_RECUO_REAL)
        return _inteiro(valor)
    if bf.hasProperty(QTextFormat.Property.TextIndent):
        return round(bf.textIndent())
    return None


def efetiva_do_bloco(bloco, estilos, cat) -> tuple[int, int] | None:
    from editdoc.ponte_qt.estilos import estilo_do_bloco
    bf = bloco.blockFormat()
    num, nivel = lista_do_bloco(bf)
    return lista_efetiva(num, nivel, estilo_do_bloco(bf), estilos, cat)


# -- calculo -------------------------------------------------------------------------

class Numerador:
    """Os numeros dos itens de lista de um QTextDocument, recalculados so' quando a estrutura
    muda (blocos a mais ou a menos, formato de bloco, catalogo). Digitar dentro de um
    paragrafo nao recalcula."""

    def __init__(self, doc: QTextDocument) -> None:
        self._doc = weakref.ref(doc)
        self._rotulos: dict[int, Rotulo] = {}
        self._sujo = True
        self._blocos = doc.blockCount()
        self._assinatura: tuple | None = None
        self._ajuste_pendente = False
        self._chave_desenho: tuple = ()
        self._imagens: dict[int, QImage | None] = {}
        #: largura do numero (twips) por (texto, nivel, fonte do paragrafo): medir a fonte e' o
        #: que mais custa no ajuste dos recuos
        self.larguras: dict[tuple, float] = {}
        #: mudancas de estrutura contadas, e a ultima ja' ajustada (o ajuste adiado que chega
        #: depois de um ajuste feito na hora, ao abrir, nao percorre o documento de novo)
        self.versao = 0
        self.versao_ajustada = -1
        #: geracao do layout (0.1.14): sobe a cada `update` do layout do documento. As faixas
        #: verticais dos itens (`faixas`) valem enquanto ela e os rotulos nao mudam: a pintura
        #: de cada tile olhava todos os itens (blockBoundingRect de cada um, por tile).
        self.geracao_layout = 0
        self._faixas: tuple | None = None
        self._serie_rotulos = 0
        doc.contentsChange.connect(self._mudou)
        doc.documentLayout().update.connect(self._layout_mudou)

    def _layout_mudou(self, *_args) -> None:
        self.geracao_layout += 1

    @property
    def desenho(self) -> tuple:
        """((numero do bloco, texto, nivel), ...) dos rotulos do ultimo calculo (0.1.15): a vista
        compara com o da pintura anterior. O `atualizar` chamado fora da pintura (a janela pede o
        rotulo do cursor) devolvia "mudou" a quem chamou, e a pintura seguinte nao via a mudanca."""
        return self._chave_desenho

    def faixas(self, doc: QTextDocument) -> list[tuple[float, float, int]]:
        """(topo, base, numero do bloco) de cada item com layout, na ordem do documento."""
        rotulos = self.rotulos()
        dl = doc.documentLayout()
        chave = (self.geracao_layout, self._serie_rotulos, doc.revision(), id(dl))
        if self._faixas is not None and self._faixas[0] == chave:
            return self._faixas[1]
        lista = []
        for numero in rotulos:
            bloco = doc.findBlockByNumber(numero)
            if not bloco.isValid() or bloco.layout() is None or bloco.layout().lineCount() == 0:
                continue
            r = dl.blockBoundingRect(bloco)
            lista.append((r.top(), r.bottom(), numero))
        # O blockBoundingRect pode ter completado um layout preguicoso (sobe a geracao): a chave
        # e' a de depois.
        chave = (self.geracao_layout, self._serie_rotulos, doc.revision(), id(dl))
        self._faixas = (chave, lista)
        return lista

    def _mudou(self, _pos: int, removidos: int, adicionados: int) -> None:
        doc = self._doc()
        if doc is None:
            return
        blocos = doc.blockCount()
        if blocos != self._blocos or (removidos == adicionados and adicionados > 0):
            self._blocos = blocos
            self._sujo = True
            self.versao += 1
            self._agendar_ajuste()

    def _agendar_ajuste(self) -> None:
        if self._ajuste_pendente:
            return
        self._ajuste_pendente = True
        QTimer.singleShot(0, self._ajustar_adiado)

    def _ajustar_adiado(self) -> None:
        self._ajuste_pendente = False
        doc = self._doc()
        if doc is None or self.versao == self.versao_ajustada:
            return
        try:
            ajustar_recuos(doc, juntar=True)
        except RuntimeError:  # documento destruido entre a edicao e o ajuste
            return

    def marcar_sujo(self) -> None:
        self._sujo = True

    def rotulos(self) -> dict[int, Rotulo]:
        """numero do bloco -> Rotulo."""
        self.atualizar()
        return self._rotulos

    def atualizar(self) -> bool:
        """Recalcula se preciso. True se algum numero (ou a posicao de um) mudou."""
        doc = self._doc()
        if doc is None:
            return False
        from editdoc.ponte_qt import estilos as pq_estilos
        chave = (assinatura(doc), pq_estilos.assinatura(doc))
        if not self._sujo and chave == self._assinatura:
            return False
        self._sujo = False
        self._assinatura = chave
        self._blocos = doc.blockCount()
        estilos = pq_estilos.catalogo(doc)
        cat = catalogo(doc)
        novos: dict[int, Rotulo] = {}
        if cat is not None and (cat.instancias or any(
                getattr(e, "lista", None) for e in estilos.itens.values())):
            from editdoc.ponte_qt.estilos import estilo_do_bloco
            contador = Contador(cat, estilos)
            # Estilos cuja cadeia liga uma lista: o bloco sem numPr direto e com outro estilo
            # nao e' item (o caminho rapido do documento grande).
            com_lista = {sid for sid in estilos.itens
                         if any(getattr(e, "lista", None) for e in estilos.cadeia(sid))}
            padrao_tem = (estilos.id_padrao() in com_lista)
            bloco = doc.begin()
            while bloco.isValid():
                bf = bloco.blockFormat()
                num, nivel = lista_do_bloco(bf)
                sid = estilo_do_bloco(bf)
                if num is not None or (sid in com_lista if sid else padrao_tem):
                    efetiva = lista_efetiva(num, nivel, sid, estilos, cat)
                    if efetiva is not None:
                        rotulo = contador.proximo(*efetiva)
                        if rotulo is not None:
                            novos[bloco.blockNumber()] = rotulo
                bloco = bloco.next()
        desenho = tuple((n, r.texto, r.nivel) for n, r in sorted(novos.items()))
        mudou = desenho != self._chave_desenho
        self._chave_desenho = desenho
        self._rotulos = novos
        self._serie_rotulos += 1
        return mudou

    def imagem(self, ident: int | None) -> QImage | None:
        """A imagem do marcador de figura (decodificada uma vez)."""
        if ident is None:
            return None
        if ident not in self._imagens:
            doc = self._doc()
            cat = catalogo(doc) if doc is not None else None
            marcador = cat.imagens.get(ident) if cat is not None else None
            img = None
            if marcador is not None and marcador.dados:
                img = QImage.fromData(marcador.dados)
                img = None if img.isNull() else img
            self._imagens[ident] = img
        return self._imagens[ident]


def numerador_de(doc: QTextDocument) -> Numerador:
    numerador = getattr(doc, "_numerador_listas", None)
    if numerador is None:
        numerador = Numerador(doc)
        doc._numerador_listas = numerador
    return numerador


def texto_do_bloco(doc: QTextDocument, numero_do_bloco: int) -> str:
    """O numero do bloco como texto (sem os simbolos privados), ou ""."""
    rotulo = numerador_de(doc).rotulos().get(numero_do_bloco)
    if rotulo is None or rotulo.nivel.oculto:
        return ""
    return texto_visivel(rotulo.texto)


# -- aparencia do numero ----------------------------------------------------------------

def _tem_familia(familia: str) -> bool:
    """A fonte esta' instalada (ou carregada pelo aplicativo). Sem cache: uma fonte carregada
    depois (os testes carregam a Calibri) passa a valer."""
    return QFontDatabase.hasFamily(familia)


def fonte_do_rotulo(bloco, rotulo: Rotulo) -> tuple[QFont, QColor, str]:
    """(fonte em pixels de layout, cor, texto a desenhar). A fonte e' a do paragrafo (a marca
    de paragrafo, como no Word) com o rPr do nivel por cima."""
    from editdoc.ponte_qt.campos import fonte_de
    doc = bloco.document()
    cf = bloco.charFormat()
    fonte = fonte_de(doc, cf)
    simbolo = rotulo.nivel.simbolo()
    pontos = fonte.pixelSize() / 20.0
    if simbolo.get("tamanho_meio_pt"):
        pontos = simbolo["tamanho_meio_pt"] / 2.0
    texto = rotulo.texto
    familia = simbolo.get("fonte")
    if familia:
        tem_privado = any(0xF000 <= ord(c) <= 0xF0FF for c in texto)
        if _tem_familia(familia):
            candidata = QFont(familia)
            candidata.setPixelSize(max(1, round(pontos * 20)))
            metrica = QFontMetricsF(candidata)
            if all(metrica.inFontUcs4(ord(c)) for c in texto if not c.isspace()):
                fonte = candidata
            else:
                texto = texto_visivel(texto)
        elif tem_privado:
            texto = texto_visivel(texto)  # sem a fonte de simbolo: o caractere parecido
        else:
            fonte.setFamilies([familia])
    elif any(0xF000 <= ord(c) <= 0xF0FF for c in texto):
        texto = texto_visivel(texto)
    fonte.setPixelSize(max(1, round(pontos * 20)))
    if simbolo.get("negrito") is not None:
        fonte.setBold(bool(simbolo["negrito"]))
    if simbolo.get("italico") is not None:
        fonte.setItalic(bool(simbolo["italico"]))
    if simbolo.get("sublinhado") is not None:
        fonte.setUnderline(bool(simbolo["sublinhado"]))
    if simbolo.get("cor_hex"):
        cor = QColor("#" + str(simbolo["cor_hex"]))
    elif cf.hasProperty(QTextFormat.Property.ForegroundBrush):
        cor = cf.foreground().color()
    else:
        cor = QColor(0, 0, 0)
    return fonte, cor, texto


def largura_do_rotulo(bloco, rotulo: Rotulo, numerador: Numerador) -> float:
    """Largura do numero em twips (unidade do layout). Guardada por texto, nivel e fonte."""
    if rotulo.nivel.oculto:
        return 0.0
    cf = bloco.charFormat()
    chave = (rotulo.texto, rotulo.nivel, tuple(cf.fontFamilies() or ()), cf.fontPointSize(),
             cf.fontWeight(), cf.fontItalic(), bloco.document().defaultFont().key())
    largura = numerador.larguras.get(chave)
    if largura is not None:
        return largura
    fonte, _cor, texto = fonte_do_rotulo(bloco, rotulo)
    img = numerador.imagem(rotulo.nivel.imagem)
    if img is not None:
        alto = QFontMetricsF(fonte).ascent()
        largura = alto * img.width() / max(1, img.height())
    else:
        largura = QFontMetricsF(fonte).horizontalAdvance(texto)
    if len(numerador.larguras) > 4096:
        numerador.larguras.clear()
    numerador.larguras[chave] = largura
    return largura


def posicoes(bloco, rotulo: Rotulo, numerador: Numerador, cat: Numeracao) -> tuple[float, float]:
    """(inicio do numero, inicio do texto), em twips a partir da margem do conteiner.

    O numero comeca no recuo da primeira linha (esquerdo menos o deslocamento), alinhado
    pelo w:lvlJc; depois vem o w:suff: tabulacao (o recuo deslocado e' uma parada, como no
    Word; senao a tabulacao do nivel ou a padrao do documento), espaco ou nada.
    """
    bf = bloco.blockFormat()
    esquerdo = bf.leftMargin()
    real = recuo_real(bf) or 0
    inicio = esquerdo + real
    largura = largura_do_rotulo(bloco, rotulo, numerador)
    nivel = rotulo.nivel
    if nivel.alinhamento == "center":
        a = inicio - largura / 2
    elif nivel.alinhamento == "right":
        a = inicio - largura
    else:
        a = inicio
    if nivel.oculto:
        return a, inicio
    fim = a + largura
    if nivel.sufixo == "nothing":
        return a, fim
    if nivel.sufixo == "space":
        espaco = largura_do_rotulo(bloco, Rotulo(texto=" ", nivel=nivel, num=rotulo.num,
                                                 ilvl=rotulo.ilvl), numerador)
        return a, fim + espaco
    paradas = [t for t in nivel.tabulacoes if t > fim + 0.5]
    if inicio < esquerdo and fim < esquerdo - 0.5:
        # Recuo deslocado: o recuo esquerdo e' a parada (as tabulacoes padrao antes dele
        # nao contam), a nao ser que uma tabulacao do nivel venha antes.
        return a, float(min([t for t in paradas if t <= esquerdo] + [esquerdo]))
    passo = max(1, int(cat.tab_padrao_tw or 720)) if cat is not None else 720
    paradas.append((math.floor(fim / passo) + 1) * passo)
    return a, float(min(paradas))


# -- recuo visual ---------------------------------------------------------------------

def ajustar_recuos(doc: QTextDocument, juntar: bool = False) -> bool:
    """Poe no textIndent de cada item o recuo visual (texto depois do numero) e guarda o de
    verdade em PROP_RECUO_REAL; tira o ajuste de quem deixou de ser item. True se mudou.

    `juntar`: o ajuste entra no ultimo passo de desfazer (depois de uma edicao).
    """
    numerador = numerador_de(doc)
    rotulos = numerador.rotulos()
    numerador.versao_ajustada = numerador.versao
    if not rotulos and not getattr(doc, "_listas_ajustadas", False):
        return False  # documento sem lista: nada a percorrer a cada Enter
    if rotulos:
        doc._listas_ajustadas = True
    cat = catalogo(doc)
    mudancas: list[tuple] = []
    bloco = doc.begin()
    while bloco.isValid():
        bf = bloco.blockFormat()
        tem_real = bf.hasProperty(PROP_RECUO_REAL)
        rotulo = rotulos.get(bloco.blockNumber())
        if rotulo is None:
            if tem_real:
                novo = QTextBlockFormat(bf)
                real = _inteiro(bf.property(PROP_RECUO_REAL))
                novo.clearProperty(PROP_RECUO_REAL)
                if real is None:
                    novo.clearProperty(QTextFormat.Property.TextIndent)
                else:
                    novo.setTextIndent(float(real))
                mudancas.append((bloco, novo))
        else:
            real = recuo_real(bf)
            a, texto = posicoes(bloco, rotulo, numerador, cat)
            visual = texto - bf.leftMargin()
            guardado = bf.property(PROP_RECUO_REAL) if tem_real else None
            alvo_real = real if real is not None else SEM_RECUO
            if not tem_real or abs(bf.textIndent() - visual) > 0.25 or guardado != alvo_real:
                novo = QTextBlockFormat(bf)
                novo.setTextIndent(visual)
                novo.setProperty(PROP_RECUO_REAL, alvo_real)
                mudancas.append((bloco, novo))
        bloco = bloco.next()
    if not mudancas:
        return False
    cursor = QTextCursor(doc)
    pode_juntar = juntar and doc.isUndoRedoEnabled() and doc.isUndoAvailable()
    if pode_juntar:
        cursor.joinPreviousEditBlock()
    else:
        cursor.beginEditBlock()
    try:
        for bloco, novo in mudancas:
            QTextCursor(bloco).setBlockFormat(novo)
    finally:
        cursor.endEditBlock()
    # As trocas de formato daqui tambem contam como mudanca; ja' estao ajustadas.
    numerador.versao_ajustada = numerador.versao
    return True


# -- pintura -------------------------------------------------------------------------

def desenhar_rotulos(painter, doc: QTextDocument, recorte: QRectF | None) -> None:
    """Pinta o numero de cada item de lista que cruza o recorte (coordenadas do documento,
    em twips, no painter ja' transformado). Mesma funcao para a tela, o PDF e a impressao."""
    numerador = numerador_de(doc)
    rotulos = numerador.rotulos()
    if not rotulos:
        return
    cat = catalogo(doc)
    dl = doc.documentLayout()
    # 0.1.14: so' os itens cuja faixa vertical cruza o recorte (as faixas ficam em cache ate' o
    # layout mudar); ate' a 0.1.13 cada tile pedia o retangulo de todos os itens.
    faixas = numerador.faixas(doc)
    if recorte is not None:
        r0, r1 = recorte.top(), recorte.bottom()
        faixas = [f for f in faixas if f[0] < r1 and f[1] > r0]
    painter.save()
    try:
        for _topo, _base, numero in faixas:
            rotulo = rotulos.get(numero)
            if rotulo is None or rotulo.nivel.oculto:
                continue
            bloco = doc.findBlockByNumber(numero)
            if not bloco.isValid() or bloco.layout() is None or bloco.layout().lineCount() == 0:
                continue
            r = dl.blockBoundingRect(bloco)
            if recorte is not None and not r.adjusted(-20000, 0, 20000, 0).intersects(recorte):
                continue
            linha = bloco.layout().lineAt(0)
            a, texto = posicoes(bloco, rotulo, numerador, cat)
            x_texto, _ = linha.cursorToX(0)
            x = r.left() + x_texto - (texto - a)
            base = r.top() + linha.y() + linha.ascent()
            fonte, cor, visivel = fonte_do_rotulo(bloco, rotulo)
            img = numerador.imagem(rotulo.nivel.imagem)
            if img is not None:
                alto = QFontMetricsF(fonte).ascent()
                largo = alto * img.width() / max(1, img.height())
                painter.drawImage(QRectF(x, base - alto, largo, alto), img)
                continue
            painter.setFont(fonte)
            painter.setPen(cor)
            painter.drawText(QPointF(x, base), visivel)
    except RuntimeError as erro:  # pintura nunca derruba a janela
        log.warning("numero de lista nao pintado: %s", erro)
    finally:
        painter.restore()
