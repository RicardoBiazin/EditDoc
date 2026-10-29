"""Objetos flutuantes na tela, no PDF e na impressao (0.1.7).

Ate' a 0.1.6 o objeto flutuante (imagem, caixa de texto, forma, grupo com wp:anchor, ou VML
com position:absolute) aparecia como uma etiqueta no ponto da ancora, dentro do texto. Agora:

Posicao: `modelo/flutuantes.py` faz a conta (relativeFrom, posOffset, align, extent, sizeRel,
simplePos), a partir de onde a ancora ficou no layout (`Gerente.referencia`). A pagina do
objeto e' a do paragrafo-ancora. O caractere do objeto no texto nao ocupa lugar (tamanho zero).

Quebra de texto: o layout do Qt (QTextDocumentLayout) sabe contornar "floats": um caractere de
objeto cujo formato aponta (ObjectIndex) para um QTextFrame com posicao FloatLeft ou FloatRight
vira um retangulo que as linhas seguintes evitam, linha a linha (o mesmo que o
`QTextCursor.insertImage(formato, FloatLeft)`). O objeto que reserva espaco (wrapSquare,
wrapTight, wrapThrough, wrapTopAndBottom; nunca o behindDoc) entra assim no documento
(`inserir_com_reserva`). O tamanho desse retangulo e' o `intrinsicSize` do objeto, calculado
aqui (`Gerente.reserva`): do topo da linha da ancora ate' o pe' do objeto (mais as
distancias), e da borda do corpo ate' o lado de dentro do objeto. wrapTopAndBottom reserva a
largura inteira: o texto passa para baixo. Limites (registrados em docs/ARQUITETURA.md): o
texto fica de um lado so' (o maior, ou o do wrapText); a faixa reservada comeca na linha da
ancora (o que fica acima dela nao contorna); Tight e Through sao tratados como Square.

Duas armadilhas do Qt 6.11 (medidas no spike, docs/SPIKES.md):
- o layout so' refaz os blocos da faixa editada; o bloco de baixo e' so' deslocado e guarda
  as linhas e o float de antes. `Gerente.atualizar` confere, depois de cada mudanca, a
  reserva de cada objeto e a largura das linhas perto dele, e marca para refazer
  (`markContentsDirty`, que nao entra no desfazer) o que ficou velho;
- apagar o caractere do objeto deixa o QTextFrame orfao, e o layout continua usando o
  retangulo antigo (QTBUG: o frame so' sai da lista de floats se for destruido, e o Qt so' o
  destroi quando o caractere sai sem o pai). `Gerente._curar` desfaz e refaz a ultima acao
  com as reservas zeradas: o frame fica orfao com tamanho zero, que nao afeta nada, e o
  documento, o desfazer e o "alterado" ficam como estavam.

Pintura (`pintar`): a imagem real (recorte a:srcRect, EMF/WMF/SVG/TIFF pela previa da 0.1.5),
a forma (geometria, preenchimento, contorno, rotacao e espelho), a caixa de texto (o texto
composto num QTextDocument proprio, com as margens internas e o alinhamento vertical), o grupo
(filhos pela chOff/chExt) e o resto (grafico, SmartArt) pela previa ou um quadro rotulado do
tamanho certo. A mesma funcao serve a tela, o PDF e a impressao.
"""

from __future__ import annotations

import math
from collections import OrderedDict

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, QTimer
from PySide6.QtGui import (QAbstractTextDocumentLayout, QBrush, QColor, QFont, QFontMetricsF,
                           QImage, QPainterPath, QPen, QPolygonF, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextFormat, QTextFrameFormat,
                           QTextImageFormat)

from editdoc import log_interno
from editdoc.formato_docx import flutuantes as fx
from editdoc.modelo import flutuantes as mf
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.documento import ROTULOS_OPACOS, ObjetoOpaco
from editdoc.modelo.folhas import MapaFolhas
from editdoc.modelo.pagina import Pagina
from editdoc.modelo.unidades import EMU_POR_PX, EMU_POR_TWIP

log = log_interno.obter(__name__)

#: chave do objeto -> Flutuante (ou None: o objeto nao flutua / nao se le)
_INFO: dict = {}
#: (chave, rid) -> QImage
_IMAGENS: dict = {}
#: (chave, indice, largura, corpo, fonte) -> (documento, altura)
_TEXTOS: dict = {}
#: id(bytes do tema) -> {nome: RRGGBB}
_TEMAS: dict = {}
_A4 = Pagina()


def info(obj: ObjetoOpaco | None, chave: str | None = None) -> fx.Flutuante | None:
    """A posicao e o desenho do objeto, se ele flutua (cache pela chave do registro)."""
    if obj is None or not obj.flutuante or obj.tipo == "equacao":
        return None
    if chave is None:
        from editdoc.ponte_qt import opacos  # import tardio: opacos importa este
        chave = opacos.chave_de(obj)
    if chave not in _INFO:
        if len(_INFO) > 4096:
            _INFO.clear()
        try:
            _INFO[chave] = fx.ler(obj.xml)
        except Exception:  # noqa: BLE001 - XML estranho: volta a etiqueta
            log.exception("posicao do objeto flutuante")
            _INFO[chave] = None
    return _INFO[chave]


# -- reserva de espaco no layout --------------------------------------------------------

def lado_inicial(fl: fx.Flutuante, pagina: Pagina | None) -> QTextFrameFormat.Position:
    """FloatLeft (texto a direita do objeto) ou FloatRight, com a pagina do arquivo.

    Decidido ao abrir: a posicao do QTextFrame nao muda depois (mudar o formato do frame
    entraria no desfazer)."""
    anc = fl.ancoragem
    if anc.quebra == "topbottom":
        return QTextFrameFormat.Position.FloatLeft
    p = pagina or _A4
    ref = mf.Referencia(pagina=p, indice=0, paragrafo_y=float(p.margem_sup_tw),
                        linha_y=float(p.margem_sup_tw))
    x0, _y0, x1, _y1 = mf.area_de_quebra(anc, mf.retangulo(anc, ref))
    lado = anc.lado_da_reserva(x0, x1, float(p.margem_esq_tw),
                               float(p.largura_tw - p.margem_dir_tw))
    return (QTextFrameFormat.Position.FloatLeft if lado == "esquerda"
            else QTextFrameFormat.Position.FloatRight)


def inserir_com_reserva(cursor: QTextCursor, fmt: QTextCharFormat, obj: ObjetoOpaco,
                        chave: str) -> bool:
    """Insere o caractere do objeto como float do Qt, se ele reserva espaco. False se nao."""
    fl = info(obj, chave)
    if fl is None or not fl.ancoragem.reserva_espaco() or cursor.currentTable() is not None:
        return False
    pagina = getattr(cursor.document(), "_pagina_flutuantes", None)
    img = QTextImageFormat()
    img.merge(fmt)
    img.setObjectType(fmt.objectType())
    cursor.insertImage(img, lado_inicial(fl, pagina))
    return True


def quadro_de(doc: QTextDocument, fmt: QTextFormat):
    """O QTextFrame do float (ou None: o objeto nao reserva espaco)."""
    if fmt.objectIndex() < 0:
        return None
    obj = doc.objectForFormat(fmt)
    from PySide6.QtGui import QTextFrame
    return obj if isinstance(obj, QTextFrame) else None


class Contexto:
    """Onde o documento fica na folha. Corpo: paginado (hb); cabecalho e rodape: nao."""

    def __init__(self, historia: str = "corpo") -> None:
        self.historia = historia
        self.pagina: Pagina = _A4  # a do arquivo (margens, papel)
        self.efetiva: Pagina = _A4  # a do layout (corpo empurrado pelo cabecalho)
        self.hb: float | None = None
        #: cabecalho e rodape: canto do documento na folha (twips), e a pagina pintada.
        self.origem: tuple[float, float] = (0.0, 0.0)
        self.indice = 0
        #: corpo (0.1.8): ((tipo de pagina, topo do corpo), ...), de `LayoutPaginado.topos()`.
        self.topos: tuple | None = None
        #: corpo com secoes (0.1.12): folha -> (pagina do arquivo, efetiva) da secao da folha;
        #: e a geracao da geometria das secoes (entra na chave)
        self.folhas = None
        self.geracao = 0
        #: colunas (passo 2): a camada folha x pagina do Qt do layout (None: identidade)
        self.mapa = None

    def chave(self) -> tuple:
        p, e = self.pagina, self.efetiva
        return (self.historia, self.hb, self.origem, self.indice % 2,
                p.largura_tw, p.altura_tw, p.margem_esq_tw, p.margem_dir_tw, p.margem_sup_tw,
                p.margem_inf_tw, e.margem_sup_tw, e.margem_esq_tw, e.corpo_largura_tw(),
                self.topos, self.geracao if self.folhas is not None else 0)

    def pagina_da(self, n: int) -> Pagina:
        return self.folhas(n)[0] if self.folhas is not None else self.pagina

    def efetiva_da(self, n: int) -> Pagina:
        return self.folhas(n)[1] if self.folhas is not None else self.efetiva

    def pe_da(self, n: int) -> float:
        """Onde o corpo da folha n termina, em y do documento (0.1.12: a secao pode ser mais
        baixa que hb)."""
        mapa = MapaFolhas.de_altura(self.hb)
        if self.folhas is not None:
            return mapa.topo(n) + float(self.efetiva_da(n).corpo_altura_tw())
        return mapa.fim(n)

    def _colunas(self):
        mapa = self.mapa
        return mapa if mapa is not None and mapa.tem_colunas() and self.hb else None

    def pe_do_y(self, y_doc: float) -> float:
        """Onde o corpo da pagina do Qt do ponto y termina (com colunas, a da coluna)."""
        mapa = self._colunas()
        if mapa is None:
            return self.pe_da(max(0, MapaFolhas.de_altura(self.hb).pagina_de_y(y_doc)))
        p = max(0, mapa.pagina_de_y(y_doc))
        return mapa.topo(p) + float(self.efetiva_da(mapa.folha_da_pagina(p)).corpo_altura_tw())

    def topo_da_pagina(self, n: int) -> float:
        """Topo do corpo na folha n (0.1.8): o do tipo da pagina (primeira, par, padrao)."""
        if self.folhas is not None and self.historia == "corpo":
            return float(self.efetiva_da(n).margem_sup_tw)
        if self.topos:
            from editdoc.modelo.campos import tipo_da_pagina
            topo = dict(self.topos).get(tipo_da_pagina(max(0, n), self.pagina))
            if topo is not None:
                return float(topo)
        return float(self.efetiva.margem_sup_tw)

    def corpo_largura(self, n: int | None = None) -> float:
        if n is not None and self.folhas is not None and self.hb:
            return float(self.efetiva_da(n).corpo_largura_tw())
        return float(self.efetiva.corpo_largura_tw())

    def folha_de(self, y_doc: float) -> tuple[int, float, float]:
        """(pagina, dx, dy): somar (dx, dy) leva um ponto do documento para a folha."""
        mapa = self._colunas()
        if mapa is not None:
            # Colunas (passo 2): a folha da pagina do Qt, deslocada para a coluna dela.
            p = max(0, mapa.pagina_de_y(y_doc))
            n = mapa.folha_da_pagina(p)
            return (n, float(self.efetiva_da(n).margem_esq_tw) + mapa.deslocamento(p),
                    self.topo_da_pagina(n) - mapa.topo(p))
        if self.hb:
            mapa = MapaFolhas.de_altura(self.hb)
            n = max(0, mapa.pagina_de_y(y_doc))
            return n, float(self.efetiva_da(n).margem_esq_tw), self.topo_da_pagina(n) - mapa.topo(n)
        return self.indice, self.origem[0], self.origem[1]


class Gerente:
    """Os objetos flutuantes de um QTextDocument: reserva, posicao, conferencia e cura."""

    def __init__(self, doc: QTextDocument) -> None:
        self.doc = doc
        self.contexto: Contexto | None = None
        #: objectIndex -> (topo, largura, altura) da ultima reserva entregue ao Qt
        self.reservas: dict[int, tuple] = {}
        #: objectIndex -> posicao do fim do ultimo bloco ao lado do float (ultima conferencia)
        self._alcance: dict[int, int] = {}
        #: numero do bloco -> assinatura das linhas que o Qt nao refaz (0.1.8, ver `atualizar`)
        self._aceitas: dict[int, tuple] = {}
        self._linhas_falhas: dict[int, tuple] = {}
        self._alcances_conferidos: dict[int, int] = {}
        self.zerar = False
        #: primeira posicao refeita pela ultima conferencia (None = nada refeito)
        self.refeito_desde: int | None = None
        #: a ultima conferencia refez blocos que voltaram exatamente como estavam no fim da
        #: anterior (0.1.11): o que esta' pintado continua certo, nada sai do cache
        self.refeito_igual = False
        #: numero do bloco -> (linhas, texto) no fim da ultima conferencia que o refez, e a
        #: altura do documento naquele momento
        self._refeitos: dict[int, tuple] = {}
        self._altura_refeitos: float | None = None
        self._lista_chave = None
        self._lista: list = []
        self._quadros: dict[int, object] = {}
        #: planos de reserva por bloco (ver `reserva`) e a geracao das reservas
        self._planos: dict = {}
        self._geracao = 0
        self._assinatura_chave = None
        self._assinatura: tuple = ()
        #: objeto -> QTextCursor na posicao dele (o Qt desloca o cursor nas edicoes)
        self._cursores: dict = {}
        self._varrido = False
        self._contador = 0
        self._estavel = None
        self._postos_chave = None
        self._postos: dict[int, list] = {}
        self._curando = False
        self._cura_marcada = False
        self._pos_cura = 0
        self._passos = (doc.availableUndoSteps(), doc.availableRedoSteps())
        self.curados = 0
        #: chamado quando o layout mudou por conta propria (a vista limpa o cache)
        self.ao_mudar = None
        doc.contentsChange.connect(self._mudou)

    def reiniciar(self) -> None:
        """O documento foi esvaziado (clear): os frames e os indices de objeto sao outros."""
        self.reservas.clear()
        self._alcance.clear()
        self._aceitas.clear()
        self._quadros.clear()
        self._cursores.clear()
        self._planos.clear()
        self._geracao += 1
        self._assinatura_chave = None
        self._varrido = False
        self._lista_chave = None
        self._estavel = None
        self._postos_chave = None
        self._passos = (self.doc.availableUndoSteps(), self.doc.availableRedoSteps())

    def assinatura(self) -> tuple:
        """Onde estao todos os objetos: muda quando algum se move (a vista limpa o cache)."""
        ctx = self.contexto
        if ctx is None or not self.lista():
            return ()
        doc = self.doc
        altura = doc.documentLayout().blockBoundingRect(doc.lastBlock()).bottom()
        chave = (doc.revision(), round(altura), ctx.chave(), self._geracao)
        if chave == self._assinatura_chave:
            return self._assinatura
        saida = []
        for pos, _fmt, _obj, _ch, fl in self.lista():
            try:
                n, ref, _d = self.referencia(pos)
                x, y, w, h = mf.retangulo(fl.ancoragem, ref)
            except Exception:  # noqa: BLE001
                continue
            # Sem a posicao no texto: digitar antes do objeto muda a posicao, nao o lugar.
            saida.append((n, round(x), round(y), round(w), round(h)))
        self._assinatura_chave, self._assinatura = chave, tuple(saida)
        return self._assinatura

    # ----- lista dos objetos ------------------------------------------------------
    def lista(self) -> list:
        """[(posicao, formato, objeto, chave, Flutuante)] dos flutuantes do documento.

        Sem varrer o documento a cada tecla: um QTextCursor por objeto acompanha a posicao
        (o Qt o desloca nas edicoes), e so' o trecho inserido e' examinado (`_mudou`)."""
        chave = self.doc.revision()
        if chave == self._lista_chave:
            return self._lista
        if not self._varrido:
            self._varrer(0, self.doc.characterCount())
            self._varrido = True
        saida = []
        vivos = {}
        vistos = set()
        for idx, cursor in self._cursores.items():
            item = self._item_em(cursor.position())
            if item is None or item[0] in vistos:
                continue
            atual = self._indice(item[1])
            if atual != idx and not (atual is None and isinstance(idx, tuple)):
                continue  # o objeto do cursor saiu; o caractere de agora e' outro
            vistos.add(item[0])
            vivos[idx] = cursor
            saida.append(item)
        self._cursores = vivos
        saida.sort(key=lambda x: x[0])
        self._lista_chave, self._lista = chave, saida
        return saida

    @staticmethod
    def _indice(fmt) -> object:
        """Chave do objeto no documento: o ObjectIndex do float, ou a chave do registro e a
        ordem de chegada para o objeto sem float (que nao tem ObjectIndex)."""
        return fmt.objectIndex() if fmt.objectIndex() >= 0 else None

    def _item_em(self, pos: int):
        from editdoc.ponte_qt import opacos
        fmt = _formato_em(self.doc, pos)
        if fmt is None or not opacos.eh_opaco(fmt):
            return None
        obj = opacos.objeto_de(fmt)
        ch = fmt.property(opacos.PROP_OPACO)
        fl = info(obj, ch if isinstance(ch, str) else None)
        if fl is None:
            return None
        return (pos, fmt, obj, ch, fl)

    def _varrer(self, inicio: int, fim: int) -> None:
        """Acha os objetos flutuantes no trecho [inicio, fim) e poe um cursor em cada um."""
        from editdoc.ponte_qt import opacos
        doc = self.doc
        fim = min(fim, doc.characterCount())
        bloco = doc.findBlock(max(0, inicio))
        while bloco.isValid() and bloco.position() < fim:
            it = bloco.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.position() + frag.length() > inicio \
                        and frag.position() < fim and opacos.eh_opaco(frag.charFormat()):
                    for i, c in enumerate(frag.text()):
                        if c != "\ufffc":
                            continue
                        item = self._item_em(frag.position() + i)
                        if item is None:
                            continue
                        idx = self._indice(item[1])
                        if idx is None:
                            idx = ("sem_float", self._contador)
                            self._contador += 1
                        cursor = QTextCursor(doc)
                        cursor.setPosition(item[0])
                        self._cursores[idx] = cursor
                        quadro = quadro_de(doc, item[1])
                        if quadro is not None:
                            self._quadros[item[1].objectIndex()] = quadro
                it += 1
            bloco = bloco.next()

    # ----- geometria ------------------------------------------------------------------
    def referencia(self, pos: int, topo_doc: float | None = None,
                   indice: int | None = None) -> tuple[int, mf.Referencia, tuple]:
        """(pagina, Referencia, (dx, dy)) da ancora em `pos`. `topo_doc`: o topo do bloco ja'
        conhecido (no meio do layout, o blockBoundingRect ainda nao vale)."""
        ctx = self.contexto or Contexto()
        doc = self.doc
        bloco = doc.findBlock(pos)
        if topo_doc is None:
            r = doc.documentLayout().blockBoundingRect(bloco)
        else:
            # No meio do layout (intrinsicSize): so' a posicao que o Qt ja' deu ao bloco.
            lay0 = bloco.layout()
            x0 = lay0.position().x() if lay0 is not None else 0.0
            r = QRectF(x0, topo_doc, ctx.corpo_largura(ctx.folha_de(topo_doc)[0]), 0.0)
        topo = r.top() if topo_doc is None else topo_doc
        n, dx, dy = ctx.folha_de(topo)
        if indice is not None and not ctx.hb:
            n = indice
        linha_y = None
        car_x = None
        lay = bloco.layout()
        if topo_doc is None and lay is not None and lay.lineCount():
            linha = lay.lineForTextPosition(max(0, pos - bloco.position()))
            if linha.isValid():
                linha_y = topo + linha.y() + dy
                car_x = r.left() + linha.cursorToX(pos - bloco.position())[0] + dx
        coluna_x = coluna_w = None
        if QTextCursor(bloco).currentTable() is not None:
            coluna_x, coluna_w = r.left() + dx, r.width()
        else:
            # A coluna e' a do arquivo (0.1.27: sem o deslocamento do recuo negativo).
            ef = ctx.efetiva_da(n)
            coluna_x = float(ef.margem_esq_tw + ef.desvio_tw)
            coluna_w = ctx.corpo_largura(n) - ef.desvio_tw
        ref = mf.Referencia(pagina=ctx.pagina_da(n), indice=n, paragrafo_y=topo + dy,
                            linha_y=linha_y if linha_y is not None else topo + dy,
                            coluna_x=coluna_x, coluna_w=coluna_w, caractere_x=car_x)
        return n, ref, (dx, dy)

    def _flutuantes_do_bloco(self, bloco) -> list:
        """[(pos, fmt, Flutuante, quadro)] dos objetos com float do Qt no bloco, em ordem."""
        from editdoc.ponte_qt import opacos
        saida = []
        it = bloco.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                cf = frag.charFormat()
                if cf.objectIndex() >= 0 and opacos.eh_opaco(cf):
                    quadro = quadro_de(self.doc, cf)
                    obj = opacos.objeto_de(cf)
                    ch = cf.property(opacos.PROP_OPACO)
                    fl = info(obj, ch if isinstance(ch, str) else None)
                    if quadro is not None and fl is not None:
                        saida.append((frag.position(), cf, fl, quadro))
            it += 1
        return saida

    def _ocupado(self, antes_de: int, topo: float, largura: float) -> tuple[float, float]:
        """(esquerda, direita) livres no topo `topo`, pelos floats de blocos anteriores."""
        esq, dir_ = 0.0, largura
        # A posicao guardada na reserva envelhece quando se digita antes do objeto: vale a
        # de agora (a lista e' refeita a cada revisao do documento).
        agora = {fmt.objectIndex(): pos for pos, fmt, _o, _c, _f in self.lista()}
        for idx, (t, w, h, _p, lado, borda) in self.reservas.items():
            p = agora.get(idx)
            if p is None or p >= antes_de or w <= 0 or h <= 0 or not (t - 0.5 <= topo < t + h):
                continue
            if lado == "E":
                esq = max(esq, borda)
            else:
                dir_ = min(dir_, borda)
        return esq, dir_

    def plano(self, bloco, topo: float) -> dict:
        """objectIndex -> (topo, largura, altura, posicao, lado, borda) dos floats do bloco.

        O Qt poe os floats um ao lado do outro, na ordem do texto, e empurra para baixo o que
        nao cabe (findY). Para a soma dos objetos de um paragrafo dar o retangulo certo, o
        paragrafo vira no maximo dois floats: o primeiro do lado esquerdo leva a reserva de
        todos os da esquerda, o primeiro da direita a de todos os da direita. Se a esquerda e
        a direita se encontram (o objeto ocupa a largura toda, ou wrapTopAndBottom), o
        primeiro float do paragrafo leva a largura toda, e o texto passa para baixo."""
        ctx = self.contexto
        itens = self._flutuantes_do_bloco(bloco)
        if not itens:
            return {}
        if ctx is not None and ctx.folhas is not None:
            # Secoes (0.1.12): o Qt poe o float na largura do documento (a da secao mais larga);
            # a secao mais estreita tem o recuo escondido nos paragrafos, nao no float.
            largura = float(self.doc.pageSize().width())
        elif ctx is not None:
            largura = ctx.corpo_largura()
        else:
            largura = max(self.doc.textWidth(), 1.0)
        direita = QTextFrameFormat.Position.FloatRight
        zero = {}
        for pos, cf, _fl, q in itens:
            lado = "D" if q.frameFormat().position() == direita else "E"
            zero[cf.objectIndex()] = (round(topo, 2), 0.0, 0.0, pos, lado,
                                      largura if lado == "D" else 0.0)
        if ctx is None or self.zerar:
            return zero
        borda_e, fundo_e = 0.0, topo
        borda_d, fundo_d = largura, topo
        cheio = False
        for pos, cf, fl, _q in itens:
            anc = fl.ancoragem
            if not anc.reserva_espaco():
                continue
            n, ref, (dx, dy) = self.referencia(pos, topo_doc=topo)
            x0, y0, x1, y1 = mf.area_de_quebra(anc, mf.retangulo(anc, ref))
            x0, x1, y0, y1 = x0 - dx, x1 - dx, y0 - dy, y1 - dy
            if ctx.hb:
                limite = ctx.pe_do_y(topo) - 1
                if y0 >= limite:
                    continue
                y1 = min(y1, limite)
            if y1 <= topo or x1 <= 0 or x0 >= largura:
                continue  # acima da linha da ancora, ou todo na margem: o texto nao muda
            if anc.quebra == "topbottom" or (x0 <= 0 and x1 >= largura):
                cheio = True
                fundo_e = max(fundo_e, y1)
            elif zero[cf.objectIndex()][4] == "D":
                borda_d, fundo_d = min(borda_d, max(x0, 0.0)), max(fundo_d, y1)
            else:
                borda_e, fundo_e = max(borda_e, min(x1, largura)), max(fundo_e, y1)
        if borda_e >= borda_d and fundo_e > topo and fundo_d > topo:
            cheio = True
        esq, dir_ = self._ocupado(itens[0][0], topo, largura)
        saida = dict(zero)
        if cheio:
            pos, cf, _fl, _q = itens[0]
            fundo = max(fundo_e, fundo_d)
            lado = zero[cf.objectIndex()][4]
            w = max(0.0, dir_ - esq)
            borda = esq + w if lado == "E" else dir_ - w
            saida[cf.objectIndex()] = (round(topo, 2), round(w, 2), round(fundo - topo, 2), pos,
                                       lado, borda)
            return saida
        feitos = set()
        for pos, cf, _fl, _q in itens:
            lado = zero[cf.objectIndex()][4]
            if lado in feitos:
                continue
            feitos.add(lado)
            if lado == "E":
                w = min(max(borda_e - esq, 0.0), max(dir_ - esq, 0.0))
                h = fundo_e - topo
                borda = esq + w
            else:
                w = min(max(dir_ - borda_d, 0.0), max(dir_ - esq, 0.0))
                h = fundo_d - topo
                borda = dir_ - w
            if w <= 0 or h <= 0:
                continue
            if lado == "E":
                esq = borda
            else:
                dir_ = borda
            saida[cf.objectIndex()] = (round(topo, 2), round(w, 2), round(h, 2), pos, lado, borda)
        return saida

    def reserva(self, pos: int, fmt: QTextFormat) -> QSizeF:
        """O intrinsicSize do float: chamado pelo layout do Qt no meio do layout do bloco."""
        if quadro_de(self.doc, fmt) is None:
            return QSizeF(0.0, 0.0)
        bloco = self.doc.findBlock(pos)
        lay = bloco.layout()
        topo = lay.position().y() if lay is not None else 0.0
        # O Qt pede o tamanho muitas vezes (a cada pintura do bloco, nao so' no layout):
        # o plano do bloco fica guardado enquanto nada que o muda mudar.
        chave = (bloco.blockNumber(), round(topo, 2), self.doc.revision(), self._geracao,
                 self.zerar, self.contexto.chave() if self.contexto is not None else None)
        plano = self._planos.get(chave)
        if plano is None:
            try:
                plano = self.plano(bloco, topo)
            except Exception:  # noqa: BLE001 - chamado no meio do layout
                log.exception("reserva do objeto flutuante")
                plano = {}
            if len(self._planos) > 256:
                self._planos.clear()
            self._planos[chave] = plano
        item = plano.get(fmt.objectIndex())
        if item is None:
            return QSizeF(0.0, 0.0)
        if self.reservas.get(fmt.objectIndex()) != item:
            self.reservas[fmt.objectIndex()] = item
            self._geracao += 1
        return QSizeF(item[1], item[2])

    # ----- conferencia depois do layout -----------------------------------------------
    def atualizar(self) -> bool:
        """Refaz o que o layout deixou velho (reserva ou linhas ao lado de um float que
        mudou). True se algo foi refeito: `refeito_desde` diz a primeira posicao refeita (quem
        pinta tira do cache dali para baixo, 0.1.8)."""
        self.refeito_desde = None
        self.refeito_igual = False
        if self.contexto is None or self._curando:
            return False
        doc = self.doc
        dl = doc.documentLayout()
        altura = dl.blockBoundingRect(doc.lastBlock()).bottom()
        chave = (doc.revision(), round(altura), self.contexto.chave())
        if chave == self._estavel:
            return False
        mudou = False
        anteriores = None
        refeitos: set[int] = set()
        for _rodada in range(6):
            faixas = self._conferir()
            if not faixas:
                break
            if faixas == anteriores and self._linhas_falhas:
                # Refazer nao mudou nada (0.1.8): a linha que o Qt desce para a pagina seguinte
                # guarda a largura que tinha ao lado do float (medido no Qt 6.11.2). Sem aceitar,
                # cada tecla refazia isso 6 vezes e conferia ate' o fim do documento.
                self._aceitas.update(self._linhas_falhas)
                self._alcance.update(self._alcances_conferidos)
                break
            anteriores = faixas
            # Faixas encostadas viram uma chamada so' (0.1.11): cada markContentsDirty refaz o
            # trecho e reposiciona o resto do documento (medido no manual real: 13 blocos
            # seguidos ao lado da reserva da capa, 1,5 ms por chamada).
            for ini, fim in _juntar(faixas):
                doc.markContentsDirty(ini, max(1, fim - ini))
                self.refeito_desde = ini if self.refeito_desde is None \
                    else min(self.refeito_desde, ini)
                refeitos.update(_numeros_dos_blocos(doc, ini, fim))
            dl.blockBoundingRect(doc.lastBlock())
            mudou = True
        altura = dl.blockBoundingRect(doc.lastBlock()).bottom()
        self._estavel = (doc.revision(), round(altura), self.contexto.chave())
        if mudou:
            self._postos_chave = None
            self._comparar_refeitos(refeitos, altura)
        return mudou

    def _comparar_refeitos(self, refeitos: set[int], altura: float) -> None:
        """`refeito_igual` (0.1.11): os blocos refeitos voltaram como no fim da conferencia
        anterior, com a mesma altura do documento, e por isso a tela pintada continua certa.

        Digitar antes das ancoras da capa do manual real empurra o float para a pagina 2; o
        Qt desloca os blocos de baixo com o float de antes, a conferencia os refaz, e eles
        voltam ao mesmo lugar de antes da tecla. Sem esta comparacao cada tecla refazia a tela
        inteira (16 tiles, 60 de 95 ms por tecla)."""
        doc = self.doc
        dl = doc.documentLayout()
        agora: dict[int, tuple] = {}
        for n in refeitos:
            bloco = doc.findBlockByNumber(n)
            if bloco.isValid():
                agora[n] = (_marca_das_linhas(bloco, dl.blockBoundingRect(bloco)),
                            hash(bloco.text()))
        self.refeito_igual = bool(agora) and self._altura_refeitos is not None \
            and abs(altura - self._altura_refeitos) < 0.5 \
            and all(self._refeitos.get(n) == chave for n, chave in agora.items())
        if len(self._refeitos) > 4096:
            self._refeitos.clear()
        self._refeitos.update(agora)
        self._altura_refeitos = altura

    def esquecer_refeitos(self) -> None:
        """A tela foi pintada de novo do zero (cache limpo): a comparacao recomeca."""
        self._refeitos.clear()
        self._altura_refeitos = None

    def _conferir(self) -> list[tuple[int, int]]:
        """Faixas (posicao inicial, final) do documento a refazer.

        `_alcance` guarda, por float, ate' onde (posicao no documento) iam os blocos ao lado
        dele na ultima conferencia: e' por posicao, nao por altura, que se acham as linhas que
        ficaram estreitas num bloco que o Qt so' deslocou. Sem registro (logo depois de abrir),
        a faixa vai ate' o fim do documento (o layout inteiro, uma vez)."""
        doc = self.doc
        dl = doc.documentLayout()
        fim_doc = max(1, doc.characterCount() - 1)
        faixas: list[tuple[int, int]] = []
        retangulos = []
        verificar: list[tuple[int, int]] = []
        planos: dict = {}
        alcances: dict = {}
        for pos, fmt, _obj, _ch, _fl in self.lista():
            quadro = quadro_de(doc, fmt)
            if quadro is None:
                continue
            idx = fmt.objectIndex()
            bloco = doc.findBlock(pos)
            topo = round(dl.blockBoundingRect(bloco).top(), 2)
            if bloco.blockNumber() not in planos:
                planos[bloco.blockNumber()] = self.plano(bloco, topo)
            esperado = planos[bloco.blockNumber()].get(idx)
            atual = self.reservas.get(idx)
            if esperado is None:
                continue
            ate_novo = self._posicao_ate(bloco, esperado[0] + esperado[2] + 1)
            antes = self._alcance.get(idx, fim_doc)
            if atual is None or any(abs(a - b) > 0.5 for a, b in zip(atual[:3], esperado[:3])):
                faixas.append((bloco.position(), min(fim_doc, max(ate_novo, antes))))
                continue
            r = dl.frameBoundingRect(quadro)
            if r.height() > 0 and r.width() > 0:
                retangulos.append(((r.x(), r.y(), r.width(), r.height()),
                                   quadro.frameFormat().position()))
            verificar.append((bloco.position(), min(fim_doc, max(ate_novo, antes))))
            alcances[idx] = ate_novo
        if faixas:
            return faixas
        if self.contexto is not None and self.contexto.folhas is not None:
            largura = float(doc.pageSize().width())  # secoes (0.1.12): a largura do documento
        else:
            largura = self.contexto.corpo_largura() if self.contexto else doc.textWidth()
        vistos = set()
        self._linhas_falhas = {}
        self._alcances_conferidos = alcances
        for ini, fim in verificar:
            bloco = doc.findBlock(ini)
            while bloco.isValid() and bloco.position() < fim:
                if bloco.blockNumber() not in vistos and \
                        QTextCursor(bloco).currentTable() is None:
                    vistos.add(bloco.blockNumber())
                    r = dl.blockBoundingRect(bloco)
                    if not self._linhas_certas(bloco, r, retangulos, largura):
                        marca = _marca_das_linhas(bloco, r)
                        if self._aceitas.get(bloco.blockNumber()) != marca:
                            self._linhas_falhas[bloco.blockNumber()] = marca
                            faixas.append((bloco.position(), bloco.position() + bloco.length()))
                bloco = bloco.next()
        if not faixas:
            self._alcance.update(alcances)
        return faixas

    def _posicao_ate(self, bloco, y: float) -> int:
        dl = self.doc.documentLayout()
        fim = bloco
        while fim.next().isValid() and dl.blockBoundingRect(fim.next()).top() < y:
            fim = fim.next()
        return fim.position() + fim.length()

    @staticmethod
    def _linhas_certas(bloco, r: QRectF, retangulos: list, largura: float) -> bool:
        """As linhas do bloco tem a largura que os floats de agora dao? (o bloco so'
        deslocado guarda as linhas de antes)."""
        lay = bloco.layout()
        if lay is None:
            return True
        bf = bloco.blockFormat()
        esq0, dir0 = bf.leftMargin(), largura - bf.rightMargin()
        for i in range(lay.lineCount()):
            linha = lay.lineAt(i)
            y = r.top() + linha.y()
            esq, dir_ = 0.0, largura
            afetada = False
            for (x, fy, fw, fh), lado in retangulos:
                if fy <= y < fy + fh:
                    afetada = True
                    if lado == QTextFrameFormat.Position.FloatLeft:
                        esq = max(esq, x + fw)
                    else:
                        dir_ = min(dir_, x)
            esq, dir_ = max(esq, esq0), min(dir_, dir0)
            if i == 0:
                esq += bf.textIndent()
            esperado = dir_ - esq
            if esperado < linha.naturalTextWidth() - 1:
                # Texto que nao cabe ao lado do objeto: o Qt desce a linha para baixo dele
                # (findY). Linha com texto ali e' velha.
                if afetada and linha.naturalTextWidth() > 1.0:
                    return False
                continue
            # O Qt so' refaz a linha da ancora quando o texto nao cabe no que sobrou: a linha
            # curta pode ficar com a largura de antes do float. Velha de verdade e' a linha
            # mais estreita que o espaco (bloco que saiu de perto do objeto) ou a que passa
            # dele com texto (bloco que chegou perto do objeto).
            if linha.width() < esperado - 2.0:
                return False
            if linha.width() > esperado + 2.0 and linha.naturalTextWidth() > esperado + 2.0:
                return False
        return True

    # ----- cura do frame orfao ----------------------------------------------------------
    def _mudou(self, pos: int, removidos: int, adicionados: int) -> None:
        if adicionados > 0 and self._varrido:
            # Objeto que volta (desfazer) ou chega (abrir): so' o trecho novo e' examinado.
            self._varrer(pos, pos + adicionados)
        passos = (self.doc.availableUndoSteps(), self.doc.availableRedoSteps())
        desfez = passos[1] > self._passos[1]
        self._passos = passos
        self._postos_chave = None
        if self._curando or removidos <= 0 or not self._quadros:
            return
        if self._orfaos():
            self._desfez = desfez
            self._pos_cura = max(0, pos)
            if not self._cura_marcada:
                self._cura_marcada = True
                QTimer.singleShot(0, self.curar)

    def _orfaos(self) -> list[int]:
        import shiboken6
        saida = []
        for idx, quadro in list(self._quadros.items()):
            if not shiboken6.isValid(quadro):
                self._quadros.pop(idx, None)
                continue
            if quadro.firstPosition() == 0:
                reserva = self.reservas.get(idx)
                if reserva is not None and reserva[1] > 0 and reserva[2] > 0:
                    saida.append(idx)
                else:
                    self._quadros.pop(idx, None)
        return saida

    def curar(self) -> bool:
        """Zera o retangulo do float cujo caractere saiu (ver a nota no topo). True se curou."""
        self._cura_marcada = False
        orfaos = self._orfaos()
        if not orfaos or self._curando:
            return False
        doc = self.doc
        desfez = getattr(self, "_desfez", False)
        if (not desfez and not doc.isUndoAvailable()) or (desfez and not doc.isRedoAvailable()):
            return False
        self._curando = True
        self.zerar = True
        try:
            if desfez:
                doc.redo()
                doc.documentLayout().blockBoundingRect(doc.lastBlock())
                doc.undo()
            else:
                doc.undo()
                doc.documentLayout().blockBoundingRect(doc.lastBlock())
                doc.redo()
            doc.documentLayout().blockBoundingRect(doc.lastBlock())
        finally:
            self.zerar = False
            self._curando = False
        fim_doc = max(1, doc.characterCount() - 1)
        for idx in orfaos:
            self.reservas.pop(idx, None)
            self._quadros.pop(idx, None)
            # As linhas que estavam ao lado do objeto apagado voltam a largura toda.
            ate = min(fim_doc, self._alcance.pop(idx, fim_doc))
            ini = min(self._pos_cura, ate)
            doc.markContentsDirty(ini, max(1, ate - ini))
        self._passos = (doc.availableUndoSteps(), doc.availableRedoSteps())
        self._estavel = None
        self._lista_chave = None
        self._postos_chave = None
        self.curados += 1
        self.atualizar()
        if self.ao_mudar is not None:
            self.ao_mudar()
        return True

    # ----- objetos posicionados -----------------------------------------------------------
    def postos(self, indice: int) -> list[mf.Posto]:
        """Os objetos da pagina `indice`, na ordem de pintura (atras primeiro)."""
        ctx = self.contexto
        if ctx is None:
            return []
        doc = self.doc
        altura = doc.documentLayout().blockBoundingRect(doc.lastBlock()).bottom()
        chave = (doc.revision(), round(altura), ctx.chave(), self._geracao,
                 None if ctx.hb else indice)
        if chave != self._postos_chave:
            por_pagina: dict[int, list] = {}
            for pos, _fmt, obj, ch, fl in self.lista():
                try:
                    n, ref, _d = self.referencia(pos, indice=None if ctx.hb else indice)
                    rect = mf.retangulo(fl.ancoragem, ref)
                except Exception:  # noqa: BLE001 - um objeto estranho nao derruba a pintura
                    log.exception("posicao do objeto flutuante")
                    continue
                por_pagina.setdefault(n, []).append(mf.Posto(
                    posicao=pos, chave=ch, indice=n, rect=rect, z=fl.ancoragem.z,
                    atras=fl.ancoragem.atras, historia=ctx.historia,
                    extra={"obj": obj, "fl": fl}))
            self._postos = {n: mf.ordem_de_pintura(v) for n, v in por_pagina.items()}
            self._postos_chave = chave
        return self._postos.get(indice, [])

    def em(self, indice: int, x: float, y: float, atras: bool | None = None) -> mf.Posto | None:
        """O objeto sob o ponto (twips da folha), o da frente primeiro."""
        for posto in reversed(self.postos(indice)):
            if atras is not None and posto.atras != atras:
                continue
            rx, ry, rw, rh = posto.rect
            folga = 40.0
            if rx - folga <= x <= rx + max(rw, 1) + folga and \
                    ry - folga <= y <= ry + max(rh, 1) + folga:
                return posto
        return None


def _juntar(faixas: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Faixas (inicio, fim) ordenadas, com as que se tocam ou se cruzam juntas."""
    saida: list[list[int]] = []
    for ini, fim in sorted(faixas):
        if saida and ini <= saida[-1][1]:
            saida[-1][1] = max(saida[-1][1], fim)
        else:
            saida.append([ini, fim])
    return [(a, b) for a, b in saida]


def _numeros_dos_blocos(doc: QTextDocument, ini: int, fim: int) -> list[int]:
    """Numeros dos blocos do quadro raiz entre as posicoes `ini` e `fim`."""
    primeiro = doc.findBlock(ini).blockNumber()
    ultimo = doc.findBlock(max(ini, fim - 1)).blockNumber()
    return list(range(primeiro, ultimo + 1)) if primeiro >= 0 and ultimo >= primeiro else []


def _marca_das_linhas(bloco, r: QRectF) -> tuple:
    """Assinatura das linhas de um bloco (topo, texto, largura e posicao de cada linha): a
    linha aceita como esta' (que o Qt nao refaz) so' volta a ser conferida se mudar."""
    lay = bloco.layout()
    linhas = tuple((round(lay.lineAt(i).y()), round(lay.lineAt(i).width()),
                    lay.lineAt(i).textStart(), lay.lineAt(i).textLength())
                   for i in range(lay.lineCount())) if lay is not None else ()
    return (round(r.top()), round(r.left()), bloco.length(), linhas)


def _formato_em(doc: QTextDocument, pos: int):
    bloco = doc.findBlock(pos)
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and frag.position() <= pos < frag.position() + frag.length():
            return frag.charFormat()
        it += 1
    return None


def gerente(doc: QTextDocument) -> Gerente:
    g = getattr(doc, "_gerente_flutuantes", None)
    if g is None:
        g = Gerente(doc)
        doc._gerente_flutuantes = g
    return g


def gerente_se_houver(doc: QTextDocument) -> Gerente | None:
    return getattr(doc, "_gerente_flutuantes", None)


# -- pintura ------------------------------------------------------------------------------

def _tema(doc: QTextDocument) -> dict:
    from editdoc.ponte_qt import estilos as pq_estilos
    corpo = getattr(doc, "_doc_estilos", None) or doc
    try:
        tema = pq_estilos.catalogo(corpo).tema_original
    except Exception:  # noqa: BLE001
        tema = None
    chave = id(tema) if tema else 0
    if chave not in _TEMAS:
        if len(_TEMAS) > 16:
            _TEMAS.clear()
        _TEMAS[chave] = fx.cores_do_tema(tema)
    return _TEMAS[chave]


def _qcor(cor, tema) -> QColor | None:
    rgba = fx.resolver(cor, tema)
    if rgba is None:
        return None
    return QColor(*rgba)


def _imagem(obj: ObjetoOpaco, chave: str, rid: str | None, w_tw: float, h_tw: float):
    """A imagem do rId (pela parte do objeto), ou a previa do objeto."""
    item = (chave, rid)
    if item not in _IMAGENS:
        if len(_IMAGENS) > 64:
            _IMAGENS.clear()
        dados = None
        if rid:
            alvo = next((a for r, _t, a, ext in obj.relacoes if r == rid and not ext), None)
            parte = next((p for p in obj.partes if p.nome == alvo), None) if alvo else None
            dados = parte.dados if parte is not None else None
        if dados is None:
            dados = obj.previa
        img = QImage()
        if dados:
            from editdoc.ponte_qt import imagens, vetoriais
            if mod_imagem.formato_de(dados):
                img = imagens.previa(dados)
            else:
                img = vetoriais.renderizar(dados, tamanho_doc=(w_tw / 15.0, h_tw / 15.0))
        _IMAGENS[item] = None if img.isNull() else img
    return _IMAGENS[item]


def _caminho(fig: fx.Figura, r: QRectF) -> QPainterPath:
    g = fig.geometria
    p = QPainterPath()
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    menor = min(w, h)

    def poligono(pontos):
        p.addPolygon(QPolygonF([QPointF(x + a * w, y + b * h) for a, b in pontos]))
        p.closeSubpath()

    if g == "ellipse":
        p.addEllipse(r)
    elif g in ("roundRect", "flowChartAlternateProcess", "round2SameRect", "round1Rect"):
        raio = menor * fig.ajustes.get("adj", 16667) / 100000.0
        p.addRoundedRect(r, raio, raio)
    elif g == "flowChartTerminator":
        p.addRoundedRect(r, menor / 2, menor / 2)
    elif g in ("triangle",):
        adj = fig.ajustes.get("adj", 50000) / 100000.0
        poligono([(adj, 0), (1, 1), (0, 1)])
    elif g == "rtTriangle":
        poligono([(0, 0), (1, 1), (0, 1)])
    elif g in ("diamond", "flowChartDecision"):
        poligono([(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)])
    elif g == "parallelogram":
        poligono([(0.25, 0), (1, 0), (0.75, 1), (0, 1)])
    elif g == "trapezoid":
        poligono([(0.25, 0), (0.75, 0), (1, 1), (0, 1)])
    elif g == "pentagon":
        poligono([(0.5, 0), (1, 0.38), (0.81, 1), (0.19, 1), (0, 0.38)])
    elif g == "hexagon":
        poligono([(0.25, 0), (0.75, 0), (1, 0.5), (0.75, 1), (0.25, 1), (0, 0.5)])
    elif g == "octagon":
        poligono([(0.29, 0), (0.71, 0), (1, 0.29), (1, 0.71), (0.71, 1), (0.29, 1), (0, 0.71),
                  (0, 0.29)])
    elif g == "rightArrow":
        poligono([(0, 0.25), (0.6, 0.25), (0.6, 0), (1, 0.5), (0.6, 1), (0.6, 0.75), (0, 0.75)])
    elif g == "leftArrow":
        poligono([(1, 0.25), (0.4, 0.25), (0.4, 0), (0, 0.5), (0.4, 1), (0.4, 0.75), (1, 0.75)])
    elif g == "upArrow":
        poligono([(0.25, 1), (0.25, 0.4), (0, 0.4), (0.5, 0), (1, 0.4), (0.75, 0.4), (0.75, 1)])
    elif g == "downArrow":
        poligono([(0.25, 0), (0.25, 0.6), (0, 0.6), (0.5, 1), (1, 0.6), (0.75, 0.6), (0.75, 0)])
    elif g == "leftRightArrow":
        poligono([(0, 0.5), (0.2, 0), (0.2, 0.25), (0.8, 0.25), (0.8, 0), (1, 0.5), (0.8, 1),
                  (0.8, 0.75), (0.2, 0.75), (0.2, 1)])
    elif g == "chevron":
        poligono([(0, 0), (0.75, 0), (1, 0.5), (0.75, 1), (0, 1), (0.25, 0.5)])
    elif g == "homePlate":
        poligono([(0, 0), (0.75, 0), (1, 0.5), (0.75, 1), (0, 1)])
    elif g == "plus":
        poligono([(0.25, 0), (0.75, 0), (0.75, 0.25), (1, 0.25), (1, 0.75), (0.75, 0.75),
                  (0.75, 1), (0.25, 1), (0.25, 0.75), (0, 0.75), (0, 0.25), (0.25, 0.25)])
    elif g == "snip1Rect":
        poligono([(0, 0), (0.83, 0), (1, 0.17), (1, 1), (0, 1)])
    else:
        p.addRect(r)
    return p


def _eh_linha(fig: fx.Figura) -> bool:
    return fig.geometria in ("line", "straightConnector1", "bentConnector3", "curvedConnector3")


def _caneta(fig: fx.Figura, tema, escala: float) -> QPen | None:
    cor = _qcor(fig.linha, tema)
    if cor is None:
        return None
    caneta = QPen(cor)
    caneta.setWidthF(max(fig.linha_larg / EMU_POR_TWIP * escala, 0.5 if escala else 0.5))
    if fig.linha_tracejada in ("dash", "lgDash", "sysDash", "dashDot", "lgDashDot"):
        caneta.setStyle(Qt.PenStyle.DashLine)
    elif fig.linha_tracejada in ("dot", "sysDot"):
        caneta.setStyle(Qt.PenStyle.DotLine)
    caneta.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    return caneta


def _texto(doc: QTextDocument, obj: ObjetoOpaco, chave: str, indice: int, largura: float,
           quebra: bool):
    """(documento composto, altura) do w:txbxContent `indice` do objeto, ou None."""
    corpo = getattr(doc, "_doc_estilos", None) or doc
    item = (chave, indice, round(largura), id(corpo), doc.defaultFont().toString(), quebra)
    if item in _TEXTOS:
        return _TEXTOS[item]
    if len(_TEXTOS) > 48:
        _TEXTOS.clear()
    _TEXTOS[item] = None
    try:
        from editdoc.formato_docx import caixas
        from editdoc.ponte_qt import estilos as pq_estilos
        from editdoc.ponte_qt import listas as pq_listas
        from editdoc.ponte_qt import para_qt
        from editdoc.ponte_qt.imagens import DocumentoQt
        from editdoc.ponte_qt.opacos import _dispositivo_1440
        conteudos = fx.caixas_de_texto(obj.xml)
        if indice >= len(conteudos):
            return None
        estilos = pq_estilos.catalogo(corpo)
        numeracao = pq_listas.catalogo(corpo)
        blocos, _c = caixas._ler_blocos(caixas._sem_goback(conteudos[indice]), obj, estilos,
                                        numeracao)
        mini = DocumentoQt()
        mini._doc_estilos = corpo
        mini._dispositivo = _dispositivo_1440()
        mini.documentLayout().setPaintDevice(mini._dispositivo)
        mini.setDocumentMargin(0)
        mini.setDefaultFont(doc.defaultFont())
        mini.setTextWidth(max(largura, 100.0))
        para_qt.preencher_blocos(mini, blocos)
        if not quebra:
            mini.setTextWidth(-1)
            natural = mini.idealWidth()
            mini.setTextWidth(max(largura, natural + 1.0, 100.0))
        altura = mini.documentLayout().documentSize().height()
        _TEXTOS[item] = (mini, altura)
    except Exception:  # noqa: BLE001 - texto estranho: a forma sai sem o texto
        log.exception("texto do objeto flutuante")
    return _TEXTOS[item]


def _pintar_texto(painter, doc, obj, chave, fig: fx.Figura, r: QRectF, tema) -> None:
    ml, mt, mr, mb = (v / EMU_POR_TWIP * r.width() / max(fig.w / EMU_POR_TWIP, 1e-6)
                      for v in fig.margens) if fig.w else (0, 0, 0, 0)
    interna = r.adjusted(ml, mt, -mr, -mb)
    composto = _texto(doc, obj, chave, fig.indice_texto, interna.width(), fig.quebra_texto)
    if composto is None:
        return
    mini, altura = composto
    dy = 0.0
    if fig.ancora_texto == "ctr":
        dy = (interna.height() - altura) / 2.0
    elif fig.ancora_texto == "b":
        dy = interna.height() - altura
    from editdoc.ponte_qt import listas as pq_listas
    from editdoc.ponte_qt import propriedades as pq_props
    painter.save()
    painter.translate(interna.left(), interna.top() + dy)
    contexto = QAbstractTextDocumentLayout.PaintContext()
    contexto.cursorPosition = -1
    padrao = _qcor(fig.cor_texto, tema) if fig.cor_texto is not None else None
    contexto.palette.setColor(contexto.palette.ColorRole.Text, padrao or QColor(0, 0, 0))
    mini.documentLayout().draw(painter, contexto)
    pq_listas.desenhar_rotulos(painter, mini, None)
    pq_props.desenhar(painter, mini, None)
    painter.restore()


def _quadro_rotulado(painter, r: QRectF, rotulo: str, img: QImage | None) -> None:
    painter.save()
    caneta = QPen(QColor(0x5f, 0x6b, 0x7a))
    caneta.setStyle(Qt.PenStyle.DashLine)
    caneta.setWidthF(max(1.0, min(r.width(), r.height()) * 0.01, 10.0))
    painter.setPen(caneta)
    painter.setBrush(QColor(0xee, 0xf1, 0xf5))
    painter.drawRect(r)
    if img is not None:
        painter.drawImage(r, img)
    else:
        fonte = QFont()
        fonte.setPixelSize(max(1, min(200, round(r.height() * 0.3))))
        painter.setFont(fonte)
        painter.setPen(QColor(0x2b, 0x33, 0x3d))
        metrica = QFontMetricsF(fonte)
        painter.drawText(r, int(Qt.AlignmentFlag.AlignCenter),
                         metrica.elidedText(rotulo, Qt.TextElideMode.ElideRight, r.width()))
    painter.restore()


def _pintar_figura(painter, doc, obj, chave, fig: fx.Figura, r: QRectF, tema) -> None:
    if r.width() <= 0 and r.height() <= 0:
        return
    painter.save()
    if fig.rot or fig.flip_h or fig.flip_v:
        c = r.center()
        painter.translate(c)
        if fig.rot:
            painter.rotate(fig.rot / 60000.0)
        painter.scale(-1.0 if fig.flip_h else 1.0, -1.0 if fig.flip_v else 1.0)
        painter.translate(-c)
    escala = 1.0
    if fig.tipo == "imagem":
        img = _imagem(obj, chave, fig.rid, r.width(), r.height())
        if img is not None:
            from editdoc.ponte_qt.imagens import recortar
            painter.drawImage(r, recortar(img, fig.recorte) if any(fig.recorte) else img)
            caneta = _caneta(fig, tema, escala)
            if caneta is not None:
                painter.setPen(caneta)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(r)
        else:
            _quadro_rotulado(painter, r, "Imagem", None)
    elif fig.tipo == "forma":
        caneta = _caneta(fig, tema, escala)
        if _eh_linha(fig):
            if caneta is not None:
                painter.setPen(caneta)
                painter.drawLine(r.topLeft(), r.bottomRight())
        else:
            preench = _qcor(fig.preenchimento, tema)
            painter.setBrush(QBrush(preench) if preench is not None else Qt.BrushStyle.NoBrush)
            painter.setPen(caneta if caneta is not None else Qt.PenStyle.NoPen)
            if preench is not None or caneta is not None:
                painter.drawPath(_caminho(fig, r))
        if fig.texto:
            _pintar_texto(painter, doc, obj, chave, fig, r, tema)
    elif fig.tipo == "grupo":
        cw = fig.ch_ext[0] or fig.w or 1
        ch = fig.ch_ext[1] or fig.h or 1
        ex = r.width() / cw
        ey = r.height() / ch
        for filho in fig.filhos:
            fr = QRectF(r.x() + (filho.x - fig.ch_off[0]) * ex, r.y() + (filho.y - fig.ch_off[1]) * ey,
                        filho.w * ex, filho.h * ey)
            _pintar_figura(painter, doc, obj, chave, filho, fr, tema)
    else:
        img = _imagem(obj, chave, None, r.width(), r.height()) if obj.previa else None
        rotulo = fig.rotulo or ROTULOS_OPACOS.get(obj.tipo, "Objeto")
        _quadro_rotulado(painter, r, rotulo, img)
    painter.restore()


def pintar(painter, doc: QTextDocument, posto: mf.Posto) -> None:
    """Pinta o objeto no retangulo dele. `painter` em twips da folha."""
    try:
        obj = posto.extra.get("obj")
        fl = posto.extra.get("fl")
        if obj is None or fl is None:
            return
        x, y, w, h = posto.rect
        r = QRectF(x, y, w, h)
        fig = fl.figura
        if fig.w == 0 and fig.h == 0:
            fig.w, fig.h = round(w * EMU_POR_TWIP), round(h * EMU_POR_TWIP)
        _pintar_figura(painter, doc, obj, posto.chave, fig, r, _tema(doc))
    except Exception:  # noqa: BLE001 - chamado no meio da pintura
        log.exception("pintura do objeto flutuante")


#: Objetos ja' pintados na escala da tela (0.1.8): chave -> QPixmap, com teto de memoria.
_PINTADOS: "OrderedDict[tuple, object]" = OrderedDict()
_PINTADOS_BYTES = [0]
#: Teto do cache de objetos pintados, e o maior objeto que entra nele (bytes).
LIMITE_PINTADOS_BYTES = 48 * 1024 * 1024
MAIOR_PINTADO_BYTES = 16 * 1024 * 1024


def _folga_de_pintura(posto: mf.Posto) -> float:
    """Quanto a tinta do objeto pode passar do retangulo (twips): contorno, e o giro."""
    _x, _y, w, h = posto.rect
    fl = posto.extra.get("fl")
    fig = fl.figura if fl is not None else None
    folga = 60.0
    if fig is not None and fig.rot:
        folga += (math.hypot(w, h) - min(w, h)) / 2.0
    return folga


def _pintar_na_tela(painter, doc: QTextDocument, posto: mf.Posto) -> bool:
    """Pinta o objeto por um QPixmap ja' na escala da tela. False se o objeto e' grande demais
    para o cache, ou o pintor esta' girado (quem chama pinta direto).

    Medido no manual real: a imagem da capa (a folha inteira) e as caixas de texto eram
    pintadas de novo em cada tile refeito, a cada tecla. O QPixmap fica alinhado ao pixel do
    dispositivo (copia 1:1, sem reamostrar: o texto da caixa sai tao nitido quanto direto). A
    impressao e o PDF nao passam por aqui: pintam o objeto de verdade."""
    from PySide6.QtGui import QPainter, QPixmap
    t = painter.worldTransform()
    if t.isRotating() or t.m11() <= 0 or abs(t.m11() - t.m22()) > 1e-9:
        return False
    dpr = painter.device().devicePixelRatioF() or 1.0
    x, y, w, h = posto.rect
    folga = _folga_de_pintura(posto)
    area = QRectF(x - folga, y - folga, w + 2 * folga, h + 2 * folga)
    tela = t.mapRect(area)
    x0, y0 = math.floor(tela.x() * dpr), math.floor(tela.y() * dpr)
    pw, ph = math.ceil(tela.right() * dpr) - x0, math.ceil(tela.bottom() * dpr) - y0
    if pw <= 0 or ph <= 0 or pw * ph * 4 > MAIOR_PINTADO_BYTES:
        return False
    escala = t.m11() * dpr
    # A fracao de pixel do canto entra na chave: o objeto pintado e' o mesmo em todos os tiles
    # (o tile comeca em pixel inteiro), e muda so' se o objeto andar.
    dx, dy = tela.x() * dpr - x0, tela.y() * dpr - y0
    chave = (posto.chave, round(w, 1), round(h, 1), round(escala, 6), round(dx, 2), round(dy, 2),
             getattr(doc, "serie", id(doc)), doc.defaultFont().toString())
    pm = _PINTADOS.get(chave)
    if pm is None:
        img = QImage(pw, ph, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p2 = QPainter(img)
        p2.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p2.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p2.translate(dx, dy)
        p2.scale(escala, escala)
        p2.translate(-area.x(), -area.y())
        pintar(p2, doc, posto)
        p2.end()
        pm = QPixmap.fromImage(img)
        _PINTADOS[chave] = pm
        _PINTADOS_BYTES[0] += pw * ph * 4
        while _PINTADOS_BYTES[0] > LIMITE_PINTADOS_BYTES and len(_PINTADOS) > 1:
            _k, velho = _PINTADOS.popitem(last=False)
            _PINTADOS_BYTES[0] -= velho.width() * velho.height() * 4
    else:
        _PINTADOS.move_to_end(chave)
    pm.setDevicePixelRatio(dpr)
    painter.save()
    painter.resetTransform()
    painter.drawPixmap(QPointF(x0 / dpr, y0 / dpr), pm)
    painter.restore()
    return True


def desenhar_pagina(painter, doc: QTextDocument, indice: int, atras: bool,
                    recorte: QRectF | None = None, tela: bool = False) -> None:
    """Os objetos da pagina `indice` (atras do texto ou na frente). `painter` em twips da
    folha. `recorte`: so' os que cruzam o retangulo (twips da folha). `tela` (0.1.8): so' na
    tela, o objeto vem do cache ja' pintado na escala do pintor."""
    g = gerente_se_houver(doc)
    if g is None or g.contexto is None:
        return
    for posto in g.postos(indice):
        if posto.atras != atras:
            continue
        if recorte is not None:
            x, y, w, h = posto.rect
            if not QRectF(x - 200, y - 200, w + 400, h + 400).intersects(recorte):
                continue
        if tela and _pintar_na_tela(painter, doc, posto):
            continue
        pintar(painter, doc, posto)


def retangulo_de(doc: QTextDocument, pos: int) -> tuple[int, tuple] | None:
    """(pagina, retangulo na folha) do flutuante cujo caractere esta' em `pos`."""
    g = gerente_se_houver(doc)
    if g is None or g.contexto is None:
        return None
    for _p, _fmt, _obj, _ch, fl in g.lista():
        if _p == pos:
            n, ref, _d = g.referencia(pos)
            return n, mf.retangulo(fl.ancoragem, ref)
    return None


def eh_flutuante(fmt: QTextFormat) -> bool:
    """O caractere e' de um objeto que a tela posiciona fora do texto (0.1.7)."""
    from editdoc.ponte_qt import opacos
    obj = opacos.objeto_de(fmt)
    ch = fmt.property(opacos.PROP_OPACO)
    return info(obj, ch if isinstance(ch, str) else None) is not None


__all__ = ["Gerente", "Contexto", "gerente", "info", "pintar", "desenhar_pagina",
           "eh_flutuante", "inserir_com_reserva", "EMU_POR_PX"]
