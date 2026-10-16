"""Visao em folhas A4: desenha as paginas, faz a rolagem e o zoom. Nao edita.

A edicao (caret, teclado, mouse, desfazer) e' de PainelDocumento, que herda desta
classe. Aqui fica o que e' so' de pintura e de geometria.

Cada folha e' pintada pela mesma funcao (`desenhar_folha`) que o PDF e a impressora
usam (`interface/impressao.py`, M7), e o zoom so' muda a escala: nunca refaz o layout.

Cache de tiles (medido no Gate do M3, docs/SPIKES.md):
  - a folha e' cortada em tiles de TILE_PX pixels logicos, na coordenada da propria
    pagina; cada tile e' um QPixmap no DPR da tela;
  - uma mudanca no texto invalida so' os tiles tocados pela altura alterada; se a
    altura total do documento mudou, invalida tudo abaixo do ponto da mudanca;
  - o cache tem teto de memoria; zoom, DPR e configuracao de pagina limpam tudo;
  - com selecao, a folha e' pintada direto (a selecao nao e' cacheada).

Cabecalho e rodape (M5) nao entram no cache: sao pintados por cima dos tiles, em cada
pagina visivel (`desenhar_faixas`), porque o numero da pagina muda de folha para
folha. Fora da edicao saem esmaecidos (cinza claro), como no Word; na edicao, o
corpo e' que esmaece, e uma linha tracejada com rotulo marca a area.

Exibir (M6): marcas de formatacao (pilcrow, ponto no espaco, seta na tabulacao) sao
pintadas por cima do texto, na mesma funcao da folha, e entram no cache; ligar ou
desligar limpa o cache. Nao mudam o layout: o QTextOption do Qt com as marcas trocaria
a largura do texto e refaria a paginacao. "Varias paginas" poe as folhas lado a lado
(`Mapa.colunas`); os outros modos voltam a uma coluna.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import astuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QAbstractTextDocumentLayout, QColor, QPainter, QPalette,
                           QPen, QPixmap, QTextCharFormat, QTextCursor, QTextFormat, QTextTable,
                           QTransform)
from PySide6.QtWidgets import QAbstractScrollArea

from editdoc.interface.layout_paginado import LayoutPaginado
from editdoc.modelo.unidades import TWIPS_POR_PX
from editdoc.modelo.campos import tipo_da_pagina
from editdoc.modelo.pagina import Pagina
from editdoc.ponte_qt import comentarios as pq_comentarios
from editdoc.ponte_qt import notas as pq_notas
from editdoc.ponte_qt import paginacao as pq_paginacao
from editdoc.ponte_qt import flutuantes as pq_flutuantes
from editdoc.ponte_qt import listas as pq_listas
from editdoc.ponte_qt import propriedades as pq_props
from editdoc.ponte_qt import revisoes as pq_revisoes
from editdoc.ponte_qt import secoes as pq_secoes
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.modelo.secoes import ROTULOS_TIPO
from editdoc.modelo.folhas import (MARGEM_DO_PAINEL_PX, PASSO_DA_RODA_PX,
                                   VAO_ENTRE_FOLHAS_PX, Mapa, alinhar_ao_dispositivo,
                                   limitar_zoom, passo_de_zoom, teto_de_zoom)

TILE_PX = 256
LIMITE_DO_CACHE_BYTES = 64 * 1024 * 1024
#: Cabecalho e rodape ja' pintados (0.1.8): teto do cache e a maior faixa que entra nele.
LIMITE_FAIXAS_BYTES = 24 * 1024 * 1024
MAIOR_FAIXA_BYTES = 8 * 1024 * 1024
PERIODO_DO_CARET_MS = 530

COR_FUNDO = QColor(0xB9, 0xBE, 0xC6)
COR_SOMBRA = QColor(0x80, 0x86, 0x90)
COR_FOLHA = QColor(255, 255, 255)
COR_SELECAO = QColor(0, 120, 215)
COR_CARET = QColor(0, 0, 0)
COR_QUEBRA = QColor(0x70, 0x76, 0x80)
#: Cabecalho e rodape fora da edicao: pintados com esta opacidade (cinza claro).
OPACIDADE_FAIXA = 0.45
#: Corpo durante a edicao do cabecalho: um veu branco por cima.
COR_VEU = QColor(255, 255, 255, 140)
COR_ROTULO_FAIXA = QColor(0x2B, 0x57, 0x9A)
#: Lado da alca de imagem desenhada, em px logicos.
ALCA_TELA_PX = 7.0
_QUEBRA_ANTES = QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore
#: Marcas de formatacao: a cor do Word.
COR_MARCAS = QColor(0x2B, 0x57, 0x9A)
#: Caracteres que ganham marca: espaco, espaco inseparavel, tabulacao e quebra de linha.
_MARCA_DO_CARACTERE = {" ": "·", "\u00a0": "°", "\t": "→", "\u2028": "↵"}


def desenhar_marcas(painter, doc, recorte: QRectF | None) -> None:
    """Pilcrow no fim de cada paragrafo, ponto em cada espaco e seta em cada tabulacao.

    Coordenadas do documento (twips), no painter ja' transformado. `recorte`: so' os
    blocos que cruzam esse retangulo (None = todos).
    """
    dl = doc.documentLayout()
    if recorte is not None:
        bloco = doc.findBlock(dl.hitTest(QPointF(0, recorte.top()), Qt.FuzzyHit))
        bloco = bloco.previous() if bloco.previous().isValid() else bloco
    else:
        bloco = doc.firstBlock()
    painter.save()
    painter.setPen(COR_MARCAS)
    fontes: dict[int, object] = {}
    while bloco.isValid():
        r = dl.blockBoundingRect(bloco)
        if recorte is not None and r.top() > recorte.bottom():
            # Dentro de tabela a ordem dos blocos nao e' a vertical: segue ate' o fim da tabela.
            if QTextCursor(bloco).currentTable() is None:
                break
        if recorte is None or r.intersects(recorte) or r.isEmpty():
            _marcas_do_bloco(painter, bloco, r, fontes)
        bloco = bloco.next()
    painter.restore()


def _fonte_da_marca(fontes: dict, cf, padrao) -> object:
    from PySide6.QtGui import QFont
    pontos = cf.fontPointSize() or padrao.pointSizeF() or 11.0
    chave = round(pontos * 2)
    fonte = fontes.get(chave)
    if fonte is None:
        fonte = QFont(padrao)
        # O layout e' em twips (1440 dpi): o corpo da letra em "pixels" e' pontos x 20.
        fonte.setPixelSize(max(1, round(pontos * 20)))
        fonte.setBold(False)
        fonte.setItalic(False)
        fontes[chave] = fonte
    return fonte


def rotulo_da_quebra(doc, pos: int, dado: dict) -> str:
    """"Quebra de seção (Próxima página)" (0.1.12): o tipo e' o da secao que comeca depois da
    quebra, como o Word mostra. Quebra de coluna: "Quebra de coluna"."""
    if dado.get("coluna"):
        return "Quebra de coluna"
    quebras = pq_secoes.quebras_de_secao(doc)
    reg = pq_secoes.registro(doc)
    seguinte = None
    for i, (p, _ident) in enumerate(quebras):
        if p == pos:
            seguinte = reg.get(quebras[i + 1][1]) if i + 1 < len(quebras) \
                else pq_secoes.secao_final(doc)
            break
    tipo = (seguinte.tipo if seguinte is not None else None) or "nextPage"
    return f"Quebra de seção ({ROTULOS_TIPO.get(tipo, ROTULOS_TIPO['nextPage'])})"


def _marcas_de_quebra(painter, bloco, r: QRectF, fontes: dict, padrao) -> bool:
    """A linha dupla pontilhada com o rotulo da quebra de secao (ou a simples da quebra de
    coluna) no lugar do caractere, ate' a margem direita do corpo. True se o bloco tem quebra
    de secao (o pilcrow nao aparece: a quebra e' a marca de paragrafo, como no Word)."""
    lay = bloco.layout()
    doc = bloco.document()
    secao = False
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and pq_secoes.eh_quebra(frag.charFormat()):
            dado = pq_secoes.dado_de(frag.charFormat()) or {}
            for i, c in enumerate(frag.text()):
                if c != "￼":
                    continue
                pos = frag.position() + i
                rel = pos - bloco.position()
                linha = lay.lineForTextPosition(rel)
                if not linha.isValid():
                    continue
                x0 = r.left() + linha.cursorToX(rel)[0] + 20
                # Ate' a margem direita do corpo da secao (sem o recuo escondido da estreita).
                escondido = pq_estilos.recuo_secao(bloco.blockFormat())
                x1 = max(r.right() - (escondido[0] if escondido else 0.0), x0 + 600)
                y = r.top() + linha.y() + linha.height() / 2.0
                rotulo = rotulo_da_quebra(doc, pos, dado)
                fonte = _fonte_da_marca(fontes, frag.charFormat(), padrao)
                fonte = type(fonte)(fonte)
                fonte.setPixelSize(max(1, round(fonte.pixelSize() * 0.75)))
                painter.save()
                painter.setFont(fonte)
                metrica = painter.fontMetrics()
                larg = metrica.horizontalAdvance(rotulo) + 80
                meio = (x0 + x1) / 2.0
                caneta = QPen(COR_MARCAS, 10, Qt.PenStyle.DotLine)
                painter.setPen(caneta)
                for dy in ((-18, 18) if not dado.get("coluna") else (0,)):
                    painter.drawLine(QPointF(x0, y + dy), QPointF(meio - larg / 2, y + dy))
                    painter.drawLine(QPointF(meio + larg / 2, y + dy), QPointF(x1, y + dy))
                painter.setPen(COR_MARCAS)
                painter.drawText(QRectF(meio - larg / 2, y - metrica.height() / 2, larg,
                                        metrica.height()), Qt.AlignmentFlag.AlignCenter, rotulo)
                painter.restore()
                secao = secao or not dado.get("coluna")
        it += 1
    return secao


def _marcas_do_bloco(painter, bloco, r: QRectF, fontes: dict) -> None:
    lay = bloco.layout()
    if lay is None or lay.lineCount() == 0:
        return
    padrao = bloco.document().defaultFont()
    texto = bloco.text()
    if "￼" in texto and _marcas_de_quebra(painter, bloco, r, fontes, padrao):
        texto_sem = None
    else:
        texto_sem = texto
    for i, caractere in enumerate(texto):
        marca = _MARCA_DO_CARACTERE.get(caractere)
        if marca is None:
            continue
        linha = lay.lineForTextPosition(i)
        if not linha.isValid():
            continue
        x0, _ = linha.cursorToX(i)
        x1, _ = linha.cursorToX(i + 1)
        fonte = _fonte_da_marca(fontes, _formato_em(bloco, i), padrao)
        painter.setFont(fonte)
        meio = (x0 + x1) / 2.0
        larg = painter.fontMetrics().horizontalAdvance(marca)
        base = r.top() + linha.y() + linha.ascent()
        x = meio - larg / 2.0 if caractere != "\t" else min(x0, x1) + 20
        painter.drawText(QPointF(x, base), marca)
    if texto_sem is None:
        return  # a quebra de secao e' a marca do paragrafo
    linha = lay.lineAt(lay.lineCount() - 1)
    x, _ = linha.cursorToX(len(texto))
    cf = bloco.charFormat() if not texto else _formato_em(bloco, len(texto) - 1)
    painter.setFont(_fonte_da_marca(fontes, cf, padrao))
    painter.drawText(QPointF(r.left() + x + 20, r.top() + linha.y() + linha.ascent()), "¶")


def _formato_em(bloco, i: int):
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid():
            ini = frag.position() - bloco.position()
            if ini <= i < ini + frag.length():
                return frag.charFormat()
        it += 1
    return bloco.charFormat()

PALETA_TEXTO = QPalette()
PALETA_TEXTO.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
PALETA_TEXTO.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
PALETA_TEXTO.setColor(QPalette.ColorRole.Highlight, COR_SELECAO)


def desenhar_folha(painter, layout: LayoutPaginado, n: int, transf: QTransform,
                   corpo_recorte=None, selecao=None, marcas: bool = False,
                   comentarios: bool = False, tela: bool = False) -> None:
    """Pinta o corpo da pagina n. Funcao unica de pintura de folha.

    transf leva twips da folha (origem no canto superior esquerdo da folha) para o
    painter. corpo_recorte: (x, y, w, h) em twips do corpo, para pintar so' um tile;
    None pinta o corpo inteiro. selecao: QTextCursor com selecao, ou None.
    comentarios (0.1.6): o realce dos trechos comentados, so' na tela (a impressao e o PDF
    nao o passam). tela (0.1.8): so' na tela, os objetos flutuantes vem do cache ja' pintados
    na escala do pintor (ponte_qt/flutuantes.py).
    """
    # A efetiva da pagina n (0.1.8): o topo do corpo segue o cabecalho dela.
    cfg = layout.efetiva_da(n)
    hb = layout.hb
    corpo_h = cfg.corpo_altura_tw()
    # Objetos flutuantes (0.1.7): pintados na folha inteira (podem estar na margem), os de
    # tras antes do texto e os da frente depois.
    folha = QRectF(0, 0, float(cfg.largura_tw), float(cfg.altura_tw))
    if corpo_recorte is not None:
        folha = QRectF(corpo_recorte[0] + cfg.margem_esq_tw, corpo_recorte[1] + cfg.margem_sup_tw,
                       corpo_recorte[2], corpo_recorte[3]).intersected(folha)
    postos = layout.flutuantes.postos(n) if not folha.isEmpty() else []
    if postos:
        _desenhar_flutuantes(painter, layout.doc, n, transf, folha, atras=True,
                             tela=tela)
    # Na horizontal o recorte e' a folha inteira, nao so' o corpo (M8): a tabela mais larga
    # que o corpo (e o recuo negativo) entra na margem, como no Word. Na vertical continua
    # o corpo, que e' o que separa uma pagina da outra.
    permitido = QRectF(-cfg.margem_esq_tw, 0, float(cfg.largura_tw), corpo_h)
    if corpo_recorte is None:
        recorte = permitido
    else:
        recorte = QRectF(*corpo_recorte).intersected(permitido)
        if recorte.isEmpty():
            # Recorte fora do corpo (margem): nada a pintar. Um setClipRect vazio NAO recorta
            # nada, e o Qt pintaria a pagina inteira para jogar fora (medido: 45 ms por tile).
            if postos:
                _desenhar_flutuantes(painter, layout.doc, n, transf, folha, atras=False,
                                     tela=tela)
            return
    painter.save()
    painter.setWorldTransform(transf)
    painter.translate(cfg.margem_esq_tw, cfg.margem_sup_tw)
    painter.setClipRect(recorte)
    painter.translate(0, -n * hb)

    ctx = QAbstractTextDocumentLayout.PaintContext()
    ctx.clip = QRectF(recorte.x(), n * hb + recorte.y(), recorte.width(), recorte.height())
    ctx.palette = PALETA_TEXTO
    ctx.cursorPosition = -1
    selecoes = pq_comentarios.selecoes_de_realce(layout.doc) if comentarios else []
    if selecao is not None and selecao.hasSelection():
        sel = QAbstractTextDocumentLayout.Selection()
        sel.cursor = QTextCursor(selecao)
        fmt = QTextCharFormat()
        fmt.setBackground(COR_SELECAO)
        sel.format = fmt
        selecoes.append(sel)
    if selecoes:
        ctx.selections = selecoes
    layout.doc.documentLayout().draw(painter, ctx)
    # Numeros e marcadores das listas (0.1.4): pintados aqui, na funcao unica da folha.
    pq_listas.desenhar_rotulos(painter, layout.doc, ctx.clip)
    # Bordas de paragrafo e de trecho e preenchimento das tabulacoes (0.1.5).
    pq_props.desenhar(painter, layout.doc, ctx.clip)
    # Alteracoes controladas (0.1.13): barra na margem e a segunda linha dos movimentos.
    pq_revisoes.desenhar(painter, layout.doc, ctx.clip)
    if layout.secoes_baixas():
        # Tabela partida numa secao mais baixa (0.1.12): a linha de cima fecha onde o texto acaba.
        from editdoc.interface.notas import fechar_linhas_empurradas
        fechar_linhas_empurradas(painter, layout.doc, ctx.clip)
    if marcas:
        desenhar_marcas(painter, layout.doc, ctx.clip)
    painter.restore()
    if postos:
        _desenhar_flutuantes(painter, layout.doc, n, transf, folha, atras=False,
                             tela=tela)


def _desenhar_flutuantes(painter, doc, n: int, transf: QTransform, folha: QRectF,
                         atras: bool, tela: bool = False) -> None:
    """Objetos flutuantes da pagina n (0.1.7), recortados em `folha` (twips da folha)."""
    if folha.isEmpty():
        return
    painter.save()
    painter.setWorldTransform(transf)
    painter.setClipRect(folha)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    pq_flutuantes.desenhar_pagina(painter, doc, n, atras, folha, tela)
    painter.restore()


def origem_da_faixa(pagina: Pagina, onde: str, altura_tw: float) -> tuple[float, float]:
    """Canto superior esquerdo do cabecalho (ou rodape) na folha, em twips.

    O cabecalho comeca a `cabecalho_tw` do alto da folha. O rodape termina a `rodape_tw`
    do pe' da folha e cresce para cima, como no Word.
    """
    if onde == "cabecalho":
        return float(pagina.margem_esq_tw), float(pagina.cabecalho_tw)
    return float(pagina.margem_esq_tw), float(pagina.altura_tw - pagina.rodape_tw - altura_tw)


def rotulo_da_faixa(onde: str, indice: int, pagina: Pagina, layout=None) -> str:
    """O rotulo da area na edicao: "Cabeçalho", "Rodapé - Primeira página"... Com secoes
    (0.1.12): "Cabeçalho - Seção 2" e, se a secao usa o da anterior, "- Igual ao anterior"."""
    nome = "Cabeçalho" if onde == "cabecalho" else "Rodapé"
    multiplas = layout is not None and layout.secoes.multiplas()
    tipo = layout.tipo_da_folha(indice) if multiplas else tipo_da_pagina(indice, pagina)
    if tipo == "primeira":
        texto = f"{nome} - Primeira página"
    elif pagina.pares_impares:
        texto = f"{nome} - Página par" if tipo == "par" else f"{nome} - Página ímpar"
    else:
        texto = nome
    if multiplas:
        secao = layout.secao_da_folha(indice)
        texto += f" - Seção {secao + 1}"
        if secao > 0 and layout.vinculada(secao, onde, tipo):
            texto += " - Igual ao anterior"
    return texto


def desenhar_faixas(painter, layout: LayoutPaginado, n: int, transf: QTransform, total: int,
                    opacidade: float = 1.0, editada=None, selecao=None,
                    marcas: bool = False, parte: str = "tudo",
                    tela: bool = False, so: str | None = None) -> None:
    """Pinta o cabecalho e o rodape da pagina n. Mesma funcao para a tela e para o PDF.

    transf leva twips da folha para o painter (como em desenhar_folha). `editada` e' a
    FaixaQt em edicao: ela recebe a selecao. Os campos ganham o numero da pagina n.
    `parte` (0.1.7): "objetos" pinta so' os objetos flutuantes da faixa (atras e na frente),
    "texto" so' o texto, "tudo" os dois. Como no Word, os objetos do cabecalho ficam atras do
    texto do corpo: a impressao pinta "objetos", depois o corpo, depois "texto".
    `so` (0.1.8): "cabecalho" ou "rodape" pinta so' aquela faixa (o cache da tela).
    """
    pagina = layout.pagina_da_folha(n)
    for onde in ("cabecalho", "rodape"):
        if so is not None and onde != so:
            continue
        faixa = layout.faixa_da_folha(onde, n)
        if faixa is None:
            continue
        layout.preparar_faixa(faixa, n, total)
        x, y = origem_da_faixa(pagina, onde, faixa.altura())
        # Objetos flutuantes da faixa (0.1.7): referencia na folha, e os de tras antes do texto.
        faixa.posicionar(pagina, layout.efetiva_da(n), n)
        faixa.flutuantes.atualizar()
        postos = faixa.flutuantes.postos(n) if parte != "texto" else []
        folha = QRectF(0, 0, float(pagina.largura_tw), float(pagina.altura_tw))
        if postos:
            painter.save()
            painter.setOpacity(opacidade)
            _desenhar_flutuantes(painter, faixa.doc, n, transf, folha, atras=True,
                                 tela=tela)
            if parte == "objetos":
                _desenhar_flutuantes(painter, faixa.doc, n, transf, folha, atras=False,
                                     tela=tela)
            painter.restore()
        if parte == "objetos":
            continue
        painter.save()
        painter.setWorldTransform(transf)
        painter.translate(x, y)
        painter.setOpacity(opacidade)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette = PALETA_TEXTO
        ctx.cursorPosition = -1
        if faixa is editada and selecao is not None and selecao.hasSelection():
            sel = QAbstractTextDocumentLayout.Selection()
            sel.cursor = QTextCursor(selecao)
            fmt = QTextCharFormat()
            fmt.setBackground(COR_SELECAO)
            sel.format = fmt
            ctx.selections = [sel]
        faixa.doc.documentLayout().draw(painter, ctx)
        pq_listas.desenhar_rotulos(painter, faixa.doc, None)
        pq_props.desenhar(painter, faixa.doc, None)
        if marcas:
            desenhar_marcas(painter, faixa.doc, None)
        painter.restore()
        if postos and parte == "tudo":
            painter.save()
            painter.setOpacity(opacidade)
            _desenhar_flutuantes(painter, faixa.doc, n, transf, folha, atras=False,
                                 tela=tela)
            painter.restore()


def alcas_do_retangulo(r: QRectF) -> dict:
    """As oito alcas do objeto flutuante selecionado (0.1.9): nome -> ponto."""
    cx, cy = r.center().x(), r.center().y()
    return {"no": r.topLeft(), "n": QPointF(cx, r.top()), "ne": r.topRight(),
            "e": QPointF(r.right(), cy), "se": r.bottomRight(), "s": QPointF(cx, r.bottom()),
            "so": r.bottomLeft(), "o": QPointF(r.left(), cy)}


class VistaPaginas(QAbstractScrollArea):
    zoomAlterado = Signal(float)

    def __init__(self, layout: LayoutPaginado, parent=None) -> None:
        super().__init__(parent)
        self.layout_pag = layout
        self._zoom = 1.0
        self._cache: OrderedDict = OrderedDict()
        self._bytes_no_cache = 0
        #: Partes velhas de tiles que ficam no cache (0.1.15): chave -> [(y0, y1, x0, x1)] em
        #: twips do documento (x contado da margem esquerda). Na pintura seguinte so' essas partes
        #: sao refeitas no pixmap guardado (`_repintar_partes`), nao o tile inteiro.
        self._sujos: dict = {}
        #: Os numeros de lista da pintura anterior (0.1.15, `_conferir_rotulos`).
        self._desenho_listas: tuple | None = None
        #: Blocos com quebra de pagina do usuario (0.1.15, `_blocos_com_quebra`).
        self._quebras: tuple | None = None
        self._altura_doc_anterior: float | None = None
        self._pendencias: list[tuple] = []
        #: Objetos flutuantes (0.1.7): onde estavam (se algum muda, o cache sai inteiro) e se
        #: os tiles tem fundo transparente (ha' objeto no cabecalho ou rodape, pintado antes).
        self._assinatura_flutuantes: tuple | None = None
        self._tiles_transparentes = False
        #: Cabecalho e rodape pintados por folha (0.1.8): chave -> (QPixmap, x, y) em px logicos
        #: da folha. Antes eram pintados (e os campos refeitos) em cada quadro, em cada folha.
        self._faixas_pintadas: OrderedDict = OrderedDict()
        self._bytes_faixas = 0
        self._caret_ligado = True
        #: Exibir (M6): marcas de formatacao e folhas lado a lado.
        self._marcas = False
        self._colunas = 1
        self._timer_caret = QTimer(self)
        self._timer_caret.timeout.connect(self._alternar_caret)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.verticalScrollBar().setSingleStep(PASSO_DA_RODA_PX)
        self.horizontalScrollBar().setSingleStep(PASSO_DA_RODA_PX)
        self.layout_pag.doc.contentsChange.connect(self._mudou_texto)
        # A cura do float orfao (0.1.7) refaz o layout fora da pintura: o cache sai inteiro.
        self.layout_pag.flutuantes.ao_mudar = self._flutuantes_mudaram
        self._atualizar_geometria()

    # ----- escala ---------------------------------------------------------
    def zoom(self) -> float:
        return self._zoom

    def dpr(self) -> float:
        return self.viewport().devicePixelRatioF()

    def teto_do_zoom(self) -> float:
        return teto_de_zoom(self.dpr())

    def definir_zoom(self, zoom: float, manter: QPointF | None = None) -> None:
        """Troca a escala. Nao refaz o layout. `manter`: ponto do viewport que fica parado."""
        novo = limitar_zoom(zoom, self.dpr())
        if abs(novo - self._zoom) < 1e-9:
            return
        ancora = None
        if manter is not None:
            ancora = self.mapa().tela_para_doc(manter.x(), manter.y(), self._paginas())
        self._zoom = novo
        self._limpar_cache()
        self._atualizar_geometria()
        if ancora is not None:
            x, y = self.mapa().doc_para_tela(ancora[0], ancora[1], self._paginas())
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() + round(x - manter.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() + round(y - manter.y()))
        self.viewport().update()
        self.zoomAlterado.emit(self._zoom)

    def _paginas(self) -> int:
        return self.layout_pag.numero_paginas()

    # ----- Exibir (M6) ----------------------------------------------------
    def marcas_visiveis(self) -> bool:
        return self._marcas

    def definir_marcas(self, ligado: bool) -> None:
        """Mostra ou esconde as marcas de formatacao. O cache de tiles e' refeito."""
        if bool(ligado) == self._marcas:
            return
        self._marcas = bool(ligado)
        self._limpar_cache()
        self.viewport().update()

    def colunas(self) -> int:
        return self._colunas

    def definir_colunas(self, colunas: int) -> None:
        colunas = max(1, int(colunas))
        if colunas == self._colunas:
            return
        self._colunas = colunas
        self._limpar_cache()
        self._atualizar_geometria()
        self.viewport().update()

    def _zoom_que_cabe(self, colunas: int, altura: bool) -> float:
        """Zoom em que `colunas` folhas cabem na largura (e, se `altura`, uma na altura)."""
        vp = self.viewport()
        cfg = self.layout_pag.pagina
        largura_px = cfg.largura_tw / TWIPS_POR_PX
        altura_px = cfg.altura_tw / TWIPS_POR_PX
        util = max(1.0, vp.width() - 2 * MARGEM_DO_PAINEL_PX)
        zoom = util / (colunas * largura_px + (colunas - 1) * VAO_ENTRE_FOLHAS_PX)
        if altura:
            zoom = min(zoom, max(1.0, float(vp.height())) / (altura_px + 2 * VAO_ENTRE_FOLHAS_PX))
        return zoom

    def zoom_modo(self, modo: str) -> None:
        """Exibir > Zoom: "100", "pagina" (uma pagina inteira), "varias" (duas lado a lado)
        ou "largura" (largura da pagina)."""
        pagina = self.pagina_atual() if hasattr(self, "pagina_atual") else 0
        if modo == "varias":
            self.definir_colunas(2)
            self.definir_zoom(self._zoom_que_cabe(2, altura=True))
        else:
            self.definir_colunas(1)
            if modo == "100":
                self.definir_zoom(1.0)
            elif modo == "pagina":
                self.definir_zoom(self._zoom_que_cabe(1, altura=True))
            else:
                self.definir_zoom(self._zoom_que_cabe(1, altura=False))
        self._atualizar_geometria()
        if modo in ("pagina", "varias"):
            self.rolar_para_pagina(pagina, folga=0)
        self.viewport().update()

    def mapa(self) -> Mapa:
        """Mapeamento atual entre documento e viewport (ver modelo/folhas.py)."""
        return self._mapa()

    def _mapa(self) -> Mapa:
        vp = self.viewport()
        lay = self.layout_pag
        multiplas = lay.secoes.multiplas()
        m = Mapa(pagina=lay.pagina, zoom=self._zoom,
                 largura_viewport=float(vp.width()), altura_viewport=float(vp.height()),
                 origem_x=float(self.horizontalScrollBar().value()),
                 origem_y=float(self.verticalScrollBar().value()),
                 colunas=self._colunas, topo_da_pagina=lay.topo_da_pagina,
                 folhas=lay.efetiva_da if multiplas else None,
                 hb_documento=lay.hb if multiplas else None)
        return m.preparar(self._paginas()) if multiplas else m

    def _atualizar_geometria(self) -> None:
        vp = self.viewport()
        m = self.mapa()
        largura = max(m.largura_conteudo + 2 * MARGEM_DO_PAINEL_PX, float(vp.width()))
        altura = m.altura_total(self._paginas())
        hb = self.horizontalScrollBar()
        vb = self.verticalScrollBar()
        hb.setRange(0, max(0, math.ceil(largura - vp.width())))
        hb.setPageStep(max(1, vp.width()))
        vb.setRange(0, max(0, math.ceil(altura - vp.height())))
        vb.setPageStep(max(1, vp.height()))

    # ----- cache de tiles -------------------------------------------------
    def _limpar_cache(self) -> None:
        # O que for pintado agora sai do layout de agora: a comparacao dos blocos refeitos
        # pela conferencia dos flutuantes (0.1.11) recomeca daqui.
        layout = getattr(self, "layout_pag", None)
        if layout is not None and getattr(layout, "flutuantes", None) is not None:
            layout.flutuantes.esquecer_refeitos()
        self._cache.clear()
        self._bytes_no_cache = 0
        self._sujos.clear()
        self._faixas_pintadas.clear()
        self._bytes_faixas = 0
        self._pendencias = []

    def _invalidar_faixa(self, y0: float, y1: float, x0: float = -math.inf,
                         x1: float = math.inf) -> None:
        """Tira do cache os tiles que mostram a faixa [y0, y1) do documento (twips) e, desde a
        0.1.14, so' os que cruzam [x0, x1) na horizontal (a celula editada).

        Desde a 0.1.15, so' para a faixa da LINHA digitada (`_invalidar_linhas` e a linha da
        tabela, que ligam `_so_a_parte`), o tile em que ela cobre uma parte pequena fica no cache
        com a parte anotada como velha (`_sujos`): a pintura seguinte refaz so' essa parte. A
        linha digitada cruzava 2 a 4 tiles inteiros (cada um com tabela e numeros de lista: 2 a
        3 ms). As outras invalidacoes (altura mudou, flutuantes, numeros de lista) continuam
        tirando o tile inteiro."""
        for chave in [k for k, v in self._cache.items()
                      if v[2] > y0 and v[1] < y1 and v[5] > x0 and v[4] < x1]:
            _pm, dy0, dy1, _nb, dx0, dx1 = self._cache[chave]
            if not self._so_a_parte:
                self._sujos.pop(chave, None)
                self._bytes_no_cache -= self._cache.pop(chave)[3]
                continue
            # Folga vertical: a tinta da letra pode passar da caixa da linha (entrelinha exata,
            # acento). O tile inteiro escondia esse excesso; a parte refeita tem de cobri-lo.
            folga = self.FOLGA_VERTICAL_TW
            parte = (max(y0 - folga, dy0), min(y1 + folga, dy1), max(x0, dx0), min(x1, dx1))
            partes = self._sujos.get(chave, []) + [parte]
            area = sum((p[1] - p[0]) * (p[3] - p[2]) for p in partes)
            if len(partes) <= self.PARTES_POR_TILE and \
                    area <= self.FRACAO_PARCIAL * (dy1 - dy0) * (dx1 - dx0):
                self._sujos[chave] = partes
                continue
            self._sujos.pop(chave, None)
            nbytes = self._cache.pop(chave)[3]
            self._bytes_no_cache -= nbytes

    #: Ate' quantas partes velhas um tile guarda, e ate' que fracao da area dele, antes de sair
    #: inteiro do cache (0.1.15).
    PARTES_POR_TILE = 4
    FRACAO_PARCIAL = 0.5
    #: Ligado so' durante a invalidacao da linha digitada (0.1.15, ver `_invalidar_faixa`).
    _so_a_parte = False
    #: Folga vertical (twips) da parte refeita, acima e abaixo da faixa: a tinta de 7,5 pt alem
    #: da caixa da linha (entrelinha exata menor que a letra). Medido no plano: com 300 e 300, a
    #: pintura da celula a 1/3 media 10,2 ms; com 150 e 150, ~9; sem folga, 7,3 (inseguro).
    FOLGA_VERTICAL_TW = 150.0
    #: Folga (twips) do recorte do Qt em volta das partes: a linha vizinha cuja caixa fica fora
    #: da parte, mas cuja tinta entra nela, tambem e' pintada.
    FOLGA_DE_CORTE_TW = 150.0

    def _mudou_texto(self, pos: int, removido: int, adicionado: int) -> None:
        """Anota a mudanca. A invalidacao e' feita na proxima pintura.

        Nao se pode ler a altura do documento aqui: no sinal o layout ainda nao foi refeito, e a
        altura lida seria a antiga (medido: a quebra de linha deixava tiles velhos na tela).
        """
        if removido and adicionado:
            # Troca de formato (ou texto trocado): a quebra de pagina de um bloco pode ter mudado.
            # So' inserir ou so' apagar nao muda formato de bloco; bloco a mais ou a menos muda a
            # chave da lista (0.1.15, `_blocos_com_quebra`).
            self._quebras = None
        # A base do bloco ANTES da mudanca (o layout ainda e' o velho aqui): uma linha que sai do
        # bloco deixa tinta abaixo da base nova, e a faixa invalidada tem de chegar ate' la'.
        doc = self.layout_pag.doc
        dl = doc.documentLayout()
        r = dl.blockBoundingRect(doc.findBlock(pos))
        base_antiga = self._extensao(doc.findBlock(pos))[1]
        # Dentro de tabela (0.1.14): o retangulo da tabela e do bloco ANTES da mudanca. Se os dois
        # nao mudam, so' a linha da tabela (ou so' as linhas do texto) sai do cache.
        tabela = self._tabela_externa(pos)
        antes = None
        if tabela is not None:
            rt = dl.frameBoundingRect(tabela)
            antes = (rt.top(), rt.bottom(), r.top(), r.bottom())
        # 0.1.17: o topo do bloco de baixo ANTES da mudanca (ver `_aplicar_pendencias`).
        # O bloco recem-criado (Enter) ainda nao tem layout: perguntar o retangulo dele aqui
        # derruba o processo (medido). Sem o topo, a pintura refaz tudo dali para baixo.
        seguinte = doc.findBlock(pos + adicionado).next()
        topo_seguinte = None
        if seguinte.isValid():
            lay_seguinte = seguinte.layout()
            topo_seguinte = dl.blockBoundingRect(seguinte).top() \
                if lay_seguinte is not None and lay_seguinte.lineCount() > 0 else math.nan
        self._pendencias.append((pos, adicionado, base_antiga, antes, topo_seguinte))
        self.viewport().update()

    def _extensao(self, bloco) -> tuple[float, float]:
        """(topo, base) do bloco em twips do documento, com as linhas (0.1.15).

        A linha que nao cabe no pe' da pagina desce para a seguinte com um deslocamento dentro
        do bloco, e o `blockBoundingRect` nao a cobre inteira (medido: a linha do sumario no
        topo da pagina 2, 210 twips abaixo da base do retangulo). Com o tile inteiro refeito o
        excesso nao aparecia; com a parte refeita (`_repintar_partes`), sim."""
        r = self.layout_pag.doc.documentLayout().blockBoundingRect(bloco)
        topo, base = r.top(), r.bottom()
        lay = bloco.layout()
        if lay is not None and lay.lineCount():
            primeira, ultima = lay.lineAt(0), lay.lineAt(lay.lineCount() - 1)
            topo = min(topo, r.top() + primeira.y())
            base = max(base, r.top() + ultima.y() + ultima.height())
        return topo, base

    def _tabela_externa(self, pos: int):
        """O quadro de primeiro nivel (a tabela de fora, se aninhada) que contem `pos`, ou None."""
        doc = self.layout_pag.doc
        cursor = QTextCursor(doc)
        cursor.setPosition(min(max(pos, 0), doc.characterCount() - 1))
        quadro = cursor.currentFrame()
        externo = None
        while quadro is not None and quadro.parentFrame() is not None:
            externo = quadro
            quadro = quadro.parentFrame()
        return externo

    def _aplicar_pendencias(self) -> None:
        """Invalida os tiles afetados pelas mudancas anotadas, com o layout ja refeito.

        Se a altura total mudou, tudo a partir da primeira linha alterada sai do cache (o
        texto de baixo se moveu). Se nao mudou, so' a faixa da linha alterada sai. Mais de
        uma mudanca na mesma pintura: vale o caso conservador, de cima para baixo.
        """
        doc = self.layout_pag.doc
        dl = doc.documentLayout()
        if not self._pendencias:
            if self._altura_doc_anterior is None:
                # Cache recem-limpo (0.1.8): a altura de agora e' a dos tiles que vao ser feitos.
                # Sem isto a tecla seguinte achava "altura mudou" e refazia a tela inteira de novo.
                self._altura_doc_anterior = dl.blockBoundingRect(doc.lastBlock()).bottom()
            return
        pendencias, self._pendencias = self._pendencias, []
        altura = dl.blockBoundingRect(doc.lastBlock()).bottom()
        anterior, self._altura_doc_anterior = self._altura_doc_anterior, altura
        if anterior is None or abs(altura - anterior) >= 0.5 or len(pendencias) > 1:
            topo = min(self._faixa_de(p[0], p[0])[0] for p in pendencias)
            self._invalidar_faixa(topo, math.inf)
            return
        pos, adicionado, base_antiga, antes, topo_seguinte = pendencias[0]
        if antes is not None:
            faixa = self._faixa_na_tabela(pos, adicionado, antes)
            if faixa is not None:
                xs = self._colunas_da_celula(pos)
                if faixa == "linhas":
                    linhas = self._linhas_da_mudanca(pos, na_tabela=True)
                    if linhas is not None:
                        topo, base = self._faixa_do_bloco(pos, pos + adicionado)
                        self._invalidar_linhas(linhas, topo, max(base, base_antiga), xs)
                        return
                faixa = self._faixa_da_linha_da_tabela(pos)
                if faixa is not None:
                    self._so_a_parte = True
                    try:
                        self._invalidar_faixa(*faixa, *xs)
                    finally:
                        self._so_a_parte = False
                    return
        topo, base = self._faixa_de(pos, pos + adicionado)
        if self._tabela_moveu(pos, antes) or \
                (antes is None and self._seguinte_moveu(pos, adicionado, topo_seguinte)):
            # O bloco de baixo se moveu (0.1.17), mesmo com a altura do documento igual: uma
            # quebra de pagina mais abaixo (do usuario ou das regras do Word) segura o resto no
            # lugar. Medido: a linha que quebra num item de lista do plano deixava os itens de
            # baixo velhos na tela.
            self._invalidar_faixa(topo, math.inf)
            return
        # So' as linhas que podem ter mudado (0.1.8): da linha anterior a' da mudanca (apagar
        # pode puxar uma palavra para cima) ate' a base do bloco, a de antes ou a de agora. Num
        # paragrafo alto (a ancora da capa, com objetos que reservam a pagina inteira) o bloco
        # todo era a folha inteira, refeita a cada tecla.
        linhas = self._linhas_da_mudanca(pos)
        if linhas is None:
            self._invalidar_faixa(topo, max(base, base_antiga))
            return
        self._invalidar_linhas(linhas, topo, max(base, base_antiga))

    def _tabela_moveu(self, pos: int, antes) -> bool:
        """A base da tabela editada saiu do lugar (0.1.17): o que vem abaixo dela se moveu."""
        if antes is None:
            return False
        tabela = self._tabela_externa(pos)
        return tabela is not None and \
            abs(self.layout_pag.doc.documentLayout().frameBoundingRect(tabela).bottom()
                - antes[1]) >= 0.5

    def _seguinte_moveu(self, pos: int, adicionado: int, topo_seguinte) -> bool:
        """O bloco logo abaixo do trecho mudado saiu do lugar (0.1.17)? `topo_seguinte`: o topo
        dele antes da mudanca (NaN: bloco sem layout ainda, conta como movido)."""
        doc = self.layout_pag.doc
        seguinte = doc.findBlock(pos + adicionado).next()
        if topo_seguinte is None or not seguinte.isValid():
            return False
        if math.isnan(topo_seguinte):
            return True
        return abs(doc.documentLayout().blockBoundingRect(seguinte).top() - topo_seguinte) >= 0.5

    def _invalidar_linhas(self, linhas, topo: float, base: float,
                          xs: tuple = ()) -> None:
        anterior, atual = linhas
        # A linha digitada (0.1.15): o tile fica no cache, so' a parte da linha e' refeita.
        self._so_a_parte = True
        try:
            if anterior is not None:
                self._invalidar_faixa(max(topo, anterior[0]), anterior[1], *xs)
            self._invalidar_faixa(max(topo, atual), base, *xs)
        finally:
            self._so_a_parte = False

    #: Folga horizontal (twips) em volta do texto da celula: acolchoamento, borda e a tinta da
    #: letra que passa da caixa (italico).
    FOLGA_DA_CELULA_TW = 400.0

    def _colunas_da_celula(self, pos: int) -> tuple[float, float]:
        """(x0, x1) da celula da tabela de fora que contem `pos`, com folga; sem limite se a
        celula nao e' achada."""
        doc = self.layout_pag.doc
        dl = doc.documentLayout()
        tabela = self._tabela_externa(pos)
        if not isinstance(tabela, QTextTable):
            return -math.inf, math.inf
        celula = tabela.cellAt(pos)
        if not celula.isValid():
            return -math.inf, math.inf
        a = dl.blockBoundingRect(doc.findBlock(celula.firstPosition()))
        b = dl.blockBoundingRect(doc.findBlock(celula.lastPosition()))
        folga = self.FOLGA_DA_CELULA_TW
        return min(a.left(), b.left()) - folga, max(a.right(), b.right()) + folga

    def _faixa_do_bloco(self, inicio: int, fim: int) -> tuple[float, float]:
        doc = self.layout_pag.doc
        return (self._extensao(doc.findBlock(inicio))[0], self._extensao(doc.findBlock(fim))[1])

    def _faixa_na_tabela(self, pos: int, adicionado: int, antes):
        """Digitar numa celula (0.1.14). Ate' a 0.1.13 a tabela inteira saia do cache a cada
        tecla (numa tabela que atravessa paginas, a tela toda). Se a tabela tem o mesmo retangulo
        de antes, as outras linhas da tabela nao se moveram: "linhas" quando o bloco editado
        tambem tem o mesmo retangulo (so' as linhas do texto mudam), True quando so' a linha da
        tabela pode ter mudado, None para o caso conservador (a tabela inteira)."""
        doc = self.layout_pag.doc
        dl = doc.documentLayout()
        tabela = self._tabela_externa(pos)
        if tabela is None:
            return None
        rt = dl.frameBoundingRect(tabela)
        t0, t1, b0, b1 = antes
        if abs(rt.top() - t0) >= 0.5 or abs(rt.bottom() - t1) >= 0.5:
            return None
        fim = doc.findBlock(pos + adicionado)
        if fim != doc.findBlock(pos):
            return True
        r = dl.blockBoundingRect(fim)
        if abs(r.top() - b0) < 0.5 and abs(r.bottom() - b1) < 0.5:
            return "linhas"
        return True

    def _faixa_da_linha_da_tabela(self, pos: int):
        """(topo, base) da linha da tabela da celula de `pos` (a da tabela de fora, se
        aninhada), com as bordas: da base do texto da linha de cima ao topo do texto da linha de
        baixo (ou a borda da tabela). None se a celula nao e' achada."""
        doc = self.layout_pag.doc
        dl = doc.documentLayout()
        tabela = self._tabela_externa(pos)
        if not isinstance(tabela, QTextTable):
            return None
        celula = tabela.cellAt(pos)
        if not celula.isValid():
            return None
        r0 = celula.row()
        r1 = r0 + celula.rowSpan() - 1
        rt = dl.frameBoundingRect(tabela)

        def blocos_da_linha(r: int):
            for c in range(tabela.columns()):
                cel = tabela.cellAt(r, c)
                if cel.isValid():
                    yield (doc.findBlock(cel.firstPosition()), doc.findBlock(cel.lastPosition()))

        if r0 == 0:
            topo = rt.top()
        else:
            topo = max(dl.blockBoundingRect(b).bottom() for _a, b in blocos_da_linha(r0 - 1))
            topo = min(topo, min(self._extensao(a)[0] for a, _b in blocos_da_linha(r0)))
        if r1 >= tabela.rows() - 1:
            base = rt.bottom()
        else:
            base = min(dl.blockBoundingRect(a).top() for a, _b in blocos_da_linha(r1 + 1))
            # Pelas linhas (0.1.15, `_extensao`): a linha da celula que desce de pagina passa
            # da base do retangulo do bloco.
            base = max(base, max(self._extensao(b)[1] for _a, b in blocos_da_linha(r1)))
        return topo, base

    def _linhas_da_mudanca(self, pos: int, na_tabela: bool = False):
        """((topo, base) da linha anterior, topo da linha de `pos`), em twips do documento, ou
        None dentro de tabela ou sem layout (vale o bloco inteiro). A linha anterior vai a' parte:
        entre ela e a da mudanca pode haver uma pagina inteira (a linha que desceu para baixo de
        um objeto), e nada ali muda. `na_tabela` (0.1.14): quem chama ja' conferiu que a tabela
        e o bloco tem o mesmo retangulo de antes da mudanca."""
        doc = self.layout_pag.doc
        bloco = doc.findBlock(pos)
        lay = bloco.layout()
        if lay is None or lay.lineCount() == 0 or (
                not na_tabela and QTextCursor(bloco).currentTable() is not None):
            return None
        linha = lay.lineForTextPosition(max(0, pos - bloco.position()))
        if not linha.isValid():
            return None
        topo_bloco = doc.documentLayout().blockBoundingRect(bloco).top()
        # Folga de meia linha: a tinta da letra pode passar um pouco da caixa da linha.
        topo_linha = topo_bloco + linha.y()
        hb = self.layout_pag.hb
        # A folga nao passa para a pagina de cima: cada pagina recorta o proprio corpo.
        atual = max(topo_linha - linha.height() / 2.0, math.floor(topo_linha / hb + 1e-6) * hb)
        anterior = lay.lineAt(linha.lineNumber() - 1) if linha.lineNumber() > 0 else None
        if anterior is None or anterior.height() <= 0:
            # Linha de altura zero (so' objetos que flutuam) nao tem tinta; nem antes: digitar e
            # apagar na linha de baixo nao descem texto para ela.
            return None, atual
        folga = anterior.height() / 2.0
        return ((topo_bloco + anterior.y() - folga,
                 topo_bloco + anterior.y() + anterior.height() + folga), atual)

    def _faixa_de(self, inicio: int, fim: int) -> tuple[float, float]:
        """Faixa vertical (twips) afetada por uma mudanca entre `inicio` e `fim`.

        Dentro de tabela vale a tabela inteira (a de fora, se aninhada): a altura de uma
        linha muda as celulas vizinhas, e uma borda redesenhada muda a grade toda.
        """
        doc = self.layout_pag.doc
        dl = doc.documentLayout()
        topo = self._extensao(doc.findBlock(inicio))[0]
        base = self._extensao(doc.findBlock(fim))[1]
        cursor = QTextCursor(doc)
        cursor.setPosition(min(max(inicio, 0), doc.characterCount() - 1))
        quadro = cursor.currentFrame()
        externo = None
        while quadro is not None and quadro.parentFrame() is not None:
            externo = quadro
            quadro = quadro.parentFrame()
        if externo is not None:
            r = dl.frameBoundingRect(externo)
            topo, base = min(topo, r.top()), max(base, r.bottom())
        return topo, base

    def _tile(self, n: int, i: int, j: int, dpr: float, m: Mapa) -> QPixmap:
        chave = (n, i, j, self._zoom, dpr)
        entrada = self._cache.get(chave)
        if entrada is not None:
            self._cache.move_to_end(chave)
            partes = self._sujos.pop(chave, None)
            if partes:
                self._repintar_partes([(entrada[0], i, j, partes)], n, dpr, m)
            return entrada[0]
        self._sujos.pop(chave, None)
        cfg = self.layout_pag.efetiva_da(n)
        e = m.escala
        tw = TILE_PX / e
        lado = round(TILE_PX * dpr)
        pm = QPixmap(lado, lado)
        pm.setDevicePixelRatio(dpr)
        # Com objeto flutuante no cabecalho ou rodape (0.1.7), a faixa e' pintada antes do
        # corpo (como no Word, ela fica atras do texto): o tile nao pode ter fundo.
        pm.fill(Qt.GlobalColor.transparent if self._tiles_transparentes else COR_FOLHA)
        pintor = QPainter(pm)
        desenhar_folha(pintor, self.layout_pag, n, self._transformacao_do_tile(i, j, e),
                       corpo_recorte=(i * tw - cfg.margem_esq_tw, j * tw - cfg.margem_sup_tw,
                                      tw, tw), marcas=self._marcas, comentarios=True,
                       tela=True)
        pintor.end()
        # Faixa do documento que o tile mostra, cortada no corpo da pagina (0.1.8): o texto de
        # uma pagina nunca e' pintado fora do corpo dela, entao o tile da margem de baixo nao
        # sai do cache por uma mudanca no alto da pagina seguinte.
        hb = self.layout_pag.hb
        dy0 = n * hb + (j * tw - cfg.margem_sup_tw)
        dy1 = min(dy0 + tw, (n + 1) * hb)
        dy0 = max(dy0, n * hb)
        nbytes = lado * lado * 4
        # Faixa horizontal do documento que o tile mostra (0.1.14), contada da margem esquerda.
        dx0 = i * tw - cfg.margem_esq_tw
        self._cache[chave] = (pm, dy0, dy1, nbytes, dx0, dx0 + tw)
        self._bytes_no_cache += nbytes
        while self._bytes_no_cache > LIMITE_DO_CACHE_BYTES and self._cache:
            velha, valor = self._cache.popitem(last=False)
            self._sujos.pop(velha, None)
            self._bytes_no_cache -= valor[3]
        return pm

    @staticmethod
    def _transformacao_do_tile(i: int, j: int, e: float, dx: float = 0.0,
                               dy: float = 0.0) -> QTransform:
        """Twips da folha -> pixels logicos do tile (i, j); (dx, dy) desloca a origem (px
        logicos) para um pedaco do tile. O MESMO calculo para o tile inteiro e para a parte."""
        t = QTransform()
        t.translate(-i * TILE_PX - dx, -j * TILE_PX - dy)
        t.scale(e, e)
        return t

    def _repintar_partes(self, itens, n: int, dpr: float, m: Mapa) -> None:
        """Refaz nos pixmaps guardados so' as partes velhas dos tiles da folha n (0.1.15).

        `itens`: [(pixmap, i, j, partes)]. Cada tile e' pintado de novo num pixmap do tamanho
        dele, com a MESMA transformacao do tile (o Qt arredonda a posicao da letra de um jeito
        para coordenada positiva e de outro para negativa: deslocar a origem, mesmo por pixels
        inteiros, mudou a letra da borda de lugar num zoom de 137%), mas so' com o que cruza as
        partes, com folga (`FOLGA_DE_CORTE_TW`); so' os pixels inteiros das partes sao copiados
        por cima do tile (sem mistura). O resultado e' o do tile pintado do zero;
        `teste_desempenho` confere pixel a pixel."""
        cfg = self.layout_pag.efetiva_da(n)
        hb = self.layout_pag.hb
        e = m.escala
        tw = TILE_PX / e
        lado = round(TILE_PX * dpr)
        corte = self.FOLGA_DE_CORTE_TW
        fundo = Qt.GlobalColor.transparent if self._tiles_transparentes else COR_FOLHA
        # O que o tile mostra, em twips do corpo (o recorte do tile pintado do zero).
        for pm, i, j, partes in itens:
            tx0, ty0 = i * tw - cfg.margem_esq_tw, j * tw - cfg.margem_sup_tw
            alvos = []
            cy0 = cx0 = math.inf
            cy1 = cx1 = -math.inf
            for y0, y1, x0, x1 in partes:
                # Twips do documento -> twips do corpo da pagina; o recorte do Qt com folga.
                by0, by1 = y0 - n * hb, y1 - n * hb
                cy0, cy1 = min(cy0, by0 - corte), max(cy1, by1 + corte)
                cx0 = min(cx0, x0 - corte if x0 > -math.inf else tx0)
                cx1 = max(cx1, x1 + corte if x1 < math.inf else tx0 + tw)
                # Pixels inteiros do dispositivo dentro do tile (a parte copiada).
                py0 = math.floor(((by0 + cfg.margem_sup_tw) * e - j * TILE_PX) * dpr) - 1
                py1 = math.ceil(((by1 + cfg.margem_sup_tw) * e - j * TILE_PX) * dpr) + 1
                px0 = math.floor(((x0 + cfg.margem_esq_tw) * e - i * TILE_PX) * dpr) - 1 \
                    if x0 > -math.inf else 0
                px1 = math.ceil(((x1 + cfg.margem_esq_tw) * e - i * TILE_PX) * dpr) + 1 \
                    if x1 < math.inf else lado
                px0, py0, px1, py1 = max(0, px0), max(0, py0), min(lado, px1), min(lado, py1)
                if px1 > px0 and py1 > py0:
                    alvos.append((px0, py0, px1, py1))
            if not alvos:
                continue
            # O recorte do Qt: as partes com folga, dentro do recorte do tile.
            rx0, ry0 = max(cx0, tx0), max(cy0, ty0)
            rx1, ry1 = min(cx1, tx0 + tw), min(cy1, ty0 + tw)
            novo = QPixmap(lado, lado)
            novo.setDevicePixelRatio(dpr)
            novo.fill(fundo)
            if rx1 > rx0 and ry1 > ry0:
                pintor = QPainter(novo)
                desenhar_folha(pintor, self.layout_pag, n, self._transformacao_do_tile(i, j, e),
                               corpo_recorte=(rx0, ry0, rx1 - rx0, ry1 - ry0),
                               marcas=self._marcas, comentarios=True, tela=True)
                pintor.end()
            pintor = QPainter(pm)
            pintor.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            for px0, py0, px1, py1 in alvos:
                # Copia 1:1 em pixels do dispositivo (os dois pixmaps no mesmo DPR).
                pintor.drawPixmap(QRectF(px0 / dpr, py0 / dpr, (px1 - px0) / dpr,
                                         (py1 - py0) / dpr), novo,
                                  QRectF(px0, py0, px1 - px0, py1 - py0))
            pintor.end()

    def _repintar_sujos(self, n: int, tiles, dpr: float, m: Mapa) -> None:
        """Antes de copiar os tiles visiveis da folha n: as partes velhas de todos eles de uma
        vez (0.1.15). `tiles`: [(i, j)] que vao ser copiados."""
        itens = []
        for i, j in tiles:
            chave = (n, i, j, self._zoom, dpr)
            partes = self._sujos.get(chave)
            entrada = self._cache.get(chave)
            if partes and entrada is not None:
                itens.append((entrada[0], i, j, partes))
                del self._sujos[chave]
        if itens:
            self._repintar_partes(itens, n, dpr, m)

    # ----- caret e selecao (o painel informa) ------------------------------
    def _posicao_caret(self) -> int | None:
        """Posicao onde desenhar o caret, ou None para nao desenhar."""
        return None

    def _selecao_atual(self) -> QTextCursor | None:
        return None

    def _posicao_imagem_selecionada(self) -> int | None:
        """Imagem selecionada, para desenhar o quadro e as alcas (o painel informa)."""
        return None

    def _retangulo_redimensionando(self) -> QRectF | None:
        """Retangulo do arrasto de alca em andamento, em px do viewport (o painel informa)."""
        return None

    def retangulo_imagem_na_tela(self, pos: int) -> QRectF | None:
        """Retangulo da imagem em `pos`, em pixels do viewport."""
        r = self.layout_pag.retangulo_imagem(pos)
        if r is None:
            return None
        m = self._mapa()
        # Pelo canto de cima: a base da imagem pode cair exatamente na divisa da pagina.
        x0, y0 = m.doc_para_tela(r.left(), r.top(), self._paginas())
        return QRectF(x0, y0, r.width() * m.escala, r.height() * m.escala)

    def _faixa_editada(self):
        """(FaixaQt em edicao, cursor dela), ou None. O painel informa."""
        return None

    def _retangulo_do_caret(self, m: Mapa, n_total: int) -> QRectF | None:
        """Caret em px do viewport, ou None. O painel troca isto na edicao do cabecalho."""
        pos = self._posicao_caret()
        if pos is None:
            return None
        c = self.layout_pag.retangulo_cursor(pos)
        x, y = m.doc_para_tela(c.x(), c.y(), n_total)
        return QRectF(x, y, 1.0, c.height() * m.escala)

    def _alternar_caret(self) -> None:
        self._caret_ligado = not self._caret_ligado
        self.viewport().update()

    def definir_piscar(self, ligado: bool) -> None:
        if ligado:
            self._timer_caret.start(PERIODO_DO_CARET_MS)
        else:
            self._timer_caret.stop()
        self._caret_ligado = True
        self.viewport().update()

    def mostrar_caret_agora(self) -> None:
        """Caret aceso logo apos um movimento, como o QTextEdit faz."""
        self._caret_ligado = True
        if self._timer_caret.isActive():
            self._timer_caret.start(PERIODO_DO_CARET_MS)

    # ----- rolagem --------------------------------------------------------
    def garantir_visivel(self, r: QRectF) -> None:
        """Rola o minimo para que o retangulo (documento) apareca no viewport."""
        m = self.mapa()
        n = self._paginas()
        tl = m.doc_para_tela(r.left(), r.top(), n)
        br = m.doc_para_tela(r.right(), r.bottom(), n)
        vp = self.viewport()
        vb = self.verticalScrollBar()
        hb = self.horizontalScrollBar()
        if tl[1] < 0:
            vb.setValue(vb.value() + math.floor(tl[1]) - 16)
        elif br[1] > vp.height():
            vb.setValue(vb.value() + math.ceil(br[1] - vp.height()) + 16)
        if tl[0] < 0:
            hb.setValue(hb.value() + math.floor(tl[0]) - 16)
        elif br[0] > vp.width():
            hb.setValue(hb.value() + math.ceil(br[0] - vp.width()) + 16)
        self.viewport().update()

    def rolar_para_pagina(self, n: int, folga: float = 8) -> None:
        m = self.mapa()
        linha = max(0, int(n)) // max(1, m.colunas)
        self.verticalScrollBar().setValue(int(m.y_da_linha(linha) - folga))

    # ----- pintura --------------------------------------------------------
    def _conferir_rotulos(self, numerador) -> None:
        """Numeros de lista que mudaram desde a pintura anterior (0.1.15), mesmo que outro tenha
        recalculado antes (a janela pede o rotulo do cursor depois da tecla, e o `atualizar` da
        pintura entao devolvia "nada mudou"): do primeiro item diferente para baixo sai do
        cache. Apagar a marca de lista de um item vazio (Backspace) renumera os de baixo sem
        mudar a altura de nada; o tile inteiro escondia os da mesma fileira, a parte nao."""
        desenho = numerador.desenho
        anterior, self._desenho_listas = self._desenho_listas, desenho
        if anterior is None or anterior is desenho or anterior == desenho:
            return
        i = next((k for k, (a, b) in enumerate(zip(anterior, desenho)) if a != b),
                 min(len(anterior), len(desenho)))
        numeros = [d[i][0] for d in (anterior, desenho) if i < len(d)]
        doc = self.layout_pag.doc
        bloco = doc.findBlockByNumber(min(numeros)) if numeros else doc.lastBlock()
        if not bloco.isValid():
            bloco = doc.lastBlock()
        self._invalidar_faixa(self._extensao(bloco)[0], math.inf)

    def preparar_para_impressao(self) -> None:
        """Campos do corpo com o total atual antes de imprimir ou exportar (M7).

        Mesma conta da pintura: se os campos mudaram, o cache de tiles sai junto, senao a
        tela ficaria com o numero velho depois que a impressao refez o layout.
        """
        listas_mudaram = pq_listas.numerador_de(self.layout_pag.doc).atualizar()
        if self.layout_pag.atualizar_secoes():
            listas_mudaram = True
            self._atualizar_geometria()
        if self.layout_pag.atualizar_notas():
            listas_mudaram = True
            self._atualizar_geometria()
        if self.layout_pag.atualizar_flutuantes():
            listas_mudaram = True
        if self.layout_pag.atualizar_campos() or listas_mudaram:
            self._limpar_cache()
            self._altura_doc_anterior = None
            self.viewport().update()

    def paintEvent(self, ev) -> None:
        if self.layout_pag.atualizar_campos():
            # Total de paginas mudou e o corpo tem campo: o numero na tela muda.
            self._limpar_cache()
            self._altura_doc_anterior = None
        numerador = pq_listas.numerador_de(self.layout_pag.doc)
        if numerador.atualizar():
            # Um numero de lista mudou longe da edicao (Tab num item renumera os de baixo).
            self._limpar_cache()
            self._altura_doc_anterior = None
        self._conferir_rotulos(numerador)
        paginas_antes = self._paginas()
        if self.layout_pag.atualizar_secoes():
            # Secoes (0.1.12): papel, quebras derivadas ou numeracao das folhas mudaram.
            self._limpar_cache()
            self._altura_doc_anterior = None
            self._atualizar_geometria()
        if self.layout_pag.atualizar_notas():
            # Notas (0.1.10): numero de marca refeito (sem contentsChange) ou area diferente.
            self._limpar_cache()
            self._altura_doc_anterior = None
            if self._paginas() != paginas_antes:
                self._atualizar_geometria()
        self._conferir_flutuantes()
        self._aplicar_pendencias()
        vp = self.viewport()
        p = QPainter(vp)
        p.fillRect(vp.rect(), COR_FUNDO)
        dpr = vp.devicePixelRatioF()
        m = self.mapa()
        n_total = self._paginas()
        i0, i1 = m.paginas_visiveis(n_total)
        selecao = self._selecao_atual()
        com_selecao = selecao is not None and selecao.hasSelection()
        visivel = QRectF(0, 0, vp.width(), vp.height())
        for n in range(i0, i1 + 1):
            x, y, w, h = m.folha_na_tela(n)
            # bordas em pixel de dispositivo inteiro: o Qt nao pinta meio pixel
            x0, y0 = alinhar_ao_dispositivo(x, dpr), alinhar_ao_dispositivo(y, dpr)
            x1 = alinhar_ao_dispositivo(x + w, dpr)
            y1 = alinhar_ao_dispositivo(y + h, dpr)
            folha = QRectF(x0, y0, x1 - x0, y1 - y0)
            sombra = 2.0 / dpr
            p.fillRect(folha.translated(sombra, sombra), COR_SOMBRA)
            p.fillRect(folha, COR_FOLHA)
            p.save()
            p.setClipRect(folha)
            if self._tiles_transparentes and self._faixa_editada() is None:
                # Objetos do cabecalho e do rodape atras do corpo (0.1.7): os tiles sao
                # transparentes, e o texto da faixa vem depois, por cima, como antes.
                for onde in ("cabecalho", "rodape"):
                    self._faixa_da_tela(p, m, n, x0, y0, n_total, onde, "objetos")
            if com_selecao:
                t = QTransform().translate(x0, y0).scale(m.escala, m.escala)
                desenhar_folha(p, self.layout_pag, n, t, selecao=selecao, marcas=self._marcas,
                               comentarios=True, tela=True)
            else:
                nx = math.ceil(w / TILE_PX)
                ny = math.ceil(h / TILE_PX)
                tiles = [(i, j) for j in range(ny) for i in range(nx)
                         if QRectF(x0 + i * TILE_PX, y0 + j * TILE_PX, TILE_PX,
                                   TILE_PX).intersects(visivel)]
                if self._sujos:
                    self._repintar_sujos(n, tiles, dpr, m)
                for i, j in tiles:
                    p.drawPixmap(QPointF(x0 + i * TILE_PX, y0 + j * TILE_PX),
                                 self._tile(n, i, j, dpr, m))
            self._pintar_notas(p, m, n, x0, y0)
            self._pintar_faixas(p, m, n, x0, y0, n_total, w)
            p.restore()
        self._desenhar_quebras(p, m, i0, i1, n_total)
        self._desenhar_caret(p, m, dpr, n_total)
        self._desenhar_imagem_selecionada(p)
        self._desenhar_flutuante_selecionado(p, m)
        self._desenhar_fantasma(p)
        p.end()

    def _nota_editada(self):
        """(NotaQt em edicao, cursor dela), ou None. O painel informa."""
        return None

    def _pintar_notas(self, p: QPainter, m: Mapa, n: int, x0: float, y0: float) -> None:
        """Area de notas da folha n (0.1.10), por cima dos tiles (o corpo nunca entra nela)."""
        if not self.layout_pag.notas.paginas.get(n):
            return
        from editdoc.interface.notas import desenhar_notas
        editada = self._nota_editada()
        t = QTransform().translate(x0, y0).scale(m.escala, m.escala)
        desenhar_notas(p, self.layout_pag, n, t, editada[0] if editada else None,
                       editada[1] if editada else None, tela=True)

    def _faixa_da_tela(self, p: QPainter, m: Mapa, n: int, x0: float, y0: float, n_total: int,
                       onde: str, parte: str) -> None:
        """Cabecalho (ou rodape) da folha n fora da edicao, por um QPixmap guardado (0.1.8).

        A chave tem tudo o que muda o desenho: a faixa e a revisao dela, a fonte padrao, a
        pagina (numero e total, para os campos), o papel, o topo do corpo, o zoom, o DPR, as
        marcas e a parte. A faixa grande demais (objeto de pagina inteira) e' pintada direto."""
        layout = self.layout_pag
        pagina = layout.pagina_da_folha(n)
        faixa = layout.faixa_da_folha(onde, n)
        if faixa is None:
            return
        dpr = p.device().devicePixelRatioF() or 1.0
        e = m.escala
        t = QTransform().translate(x0, y0).scale(e, e)
        chave = (onde, n, n_total, parte, self._zoom, dpr, self._marcas, faixa.serie,
                 faixa.doc.revision(), faixa.doc.chave_da_fonte(), astuple(pagina),
                 layout.topo_da_pagina(n), layout.chave_de_campos_da_folha(n))
        guardado = self._faixas_pintadas.get(chave)
        if guardado is None:
            regiao = self._regiao_da_faixa(faixa, n, n_total, onde, parte)
            if regiao is None:
                return
            # Canto e tamanho em pixel inteiro do dispositivo: o QPixmap e' copiado 1:1.
            px0, py0 = math.floor(regiao.x() * e * dpr), math.floor(regiao.y() * e * dpr)
            pw = math.ceil(regiao.right() * e * dpr) - px0
            ph = math.ceil(regiao.bottom() * e * dpr) - py0
            if pw <= 0 or ph <= 0 or pw * ph * 4 > MAIOR_FAIXA_BYTES:
                desenhar_faixas(p, layout, n, t, n_total, OPACIDADE_FAIXA, marcas=self._marcas,
                                parte=parte, tela=True, so=onde)
                return
            pm = QPixmap(pw, ph)
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            pintor = QPainter(pm)
            ft = QTransform().translate(-px0 / dpr, -py0 / dpr).scale(e, e)
            desenhar_faixas(pintor, layout, n, ft, n_total, OPACIDADE_FAIXA, marcas=self._marcas,
                            parte=parte, tela=True, so=onde)
            pintor.end()
            guardado = (pm, px0 / dpr, py0 / dpr)
            self._faixas_pintadas[chave] = guardado
            self._bytes_faixas += pw * ph * 4
            while self._bytes_faixas > LIMITE_FAIXAS_BYTES and len(self._faixas_pintadas) > 1:
                _k, velho = self._faixas_pintadas.popitem(last=False)
                self._bytes_faixas -= velho[0].width() * velho[0].height() * 4
        else:
            self._faixas_pintadas.move_to_end(chave)
        pm, fx, fy = guardado
        p.drawPixmap(QPointF(x0 + fx, y0 + fy), pm)

    def _regiao_da_faixa(self, faixa, n: int, n_total: int, onde: str, parte: str):
        """Retangulo (twips da folha) onde a faixa pinta: o texto (com folga para a tinta e os
        numeros de lista na margem) e os objetos flutuantes dela. None se nada a pintar."""
        layout = self.layout_pag
        pagina = layout.pagina_da_folha(n)
        layout.preparar_faixa(faixa, n, n_total)
        folha = QRectF(0, 0, float(pagina.largura_tw), float(pagina.altura_tw))
        regiao = QRectF()
        if parte != "objetos":
            _x, y = origem_da_faixa(pagina, onde, faixa.altura())
            regiao = QRectF(0.0, y - 240.0, float(pagina.largura_tw), faixa.altura() + 480.0)
        faixa.posicionar(pagina, layout.efetiva_da(n), n)
        faixa.flutuantes.atualizar()
        if parte != "texto":
            for posto in faixa.flutuantes.postos(n):
                rx, ry, rw, rh = posto.rect
                folga = 240.0 + max(rw, rh)  # giro e contorno
                novo = QRectF(rx - folga, ry - folga, rw + 2 * folga, rh + 2 * folga)
                regiao = novo if regiao.isEmpty() else regiao.united(novo)
        regiao = regiao.intersected(folha)
        return None if regiao.isEmpty() else regiao

    def _flutuantes_mudaram(self) -> None:
        self._limpar_cache()
        self._altura_doc_anterior = None
        self.viewport().update()

    def _conferir_flutuantes(self) -> None:
        """Objetos flutuantes (0.1.7): reserva e linhas em dia; se algum objeto mudou de lugar,
        o cache inteiro sai (o objeto pode estar longe do texto que mudou, ate' na margem)."""
        layout = self.layout_pag
        if layout.atualizar_flutuantes():
            desde = layout.flutuantes.refeito_desde
            if layout.flutuantes.refeito_igual:
                # Os blocos refeitos voltaram como estavam pintados (0.1.11): nada sai.
                pass
            elif desde is None:
                self._limpar_cache()
                self._altura_doc_anterior = None
            else:
                # So' dali para baixo (0.1.8): o que esta' acima do primeiro bloco refeito nao
                # mudou. Os objetos que mudam de lugar limpam tudo pela assinatura, abaixo.
                doc = layout.doc
                topo = doc.documentLayout().blockBoundingRect(doc.findBlock(desde)).top()
                self._invalidar_faixa(topo, math.inf)
        assinatura = layout.flutuantes.assinatura()
        if assinatura != self._assinatura_flutuantes:
            if self._assinatura_flutuantes is not None or assinatura:
                self._limpar_cache()
            self._assinatura_flutuantes = assinatura
        transparente = any(f.flutuantes.lista() for f in layout.faixas.todas())
        if transparente != self._tiles_transparentes:
            self._tiles_transparentes = transparente
            self._limpar_cache()

    def _posicao_flutuante_selecionado(self) -> int | None:
        """O objeto flutuante selecionado sozinho (o painel informa)."""
        return None

    def _retangulo_fantasma(self) -> QRectF | None:
        """Contorno do objeto durante o arraste (0.1.9), em px do viewport (o painel informa)."""
        return None

    def _desenhar_fantasma(self, p: QPainter) -> None:
        """O contorno tracejado de onde o objeto vai ficar. Barato: um retangulo por quadro;
        o objeto e o texto em volta so' mudam ao soltar."""
        r = self._retangulo_fantasma()
        if r is None:
            return
        p.save()
        p.setPen(QPen(COR_SELECAO, 1, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        p.restore()

    def retangulo_flutuante_na_tela(self, pos: int) -> QRectF | None:
        """Retangulo do objeto flutuante do corpo em `pos`, em pixels do viewport (0.1.7)."""
        achado = pq_flutuantes.retangulo_de(self.layout_pag.doc, pos)
        if achado is None:
            return None
        n, (x, y, w, h) = achado
        m = self._mapa()
        fx, fy, _fw, _fh = m.folha_na_tela(n)
        return QRectF(fx + x * m.escala, fy + y * m.escala, max(w * m.escala, 1.0),
                      max(h * m.escala, 1.0))

    def _desenhar_flutuante_selecionado(self, p: QPainter, m: Mapa) -> None:
        pos = self._posicao_flutuante_selecionado()
        if pos is None:
            return
        r = self.retangulo_flutuante_na_tela(pos)
        if r is None:
            return
        p.save()
        p.setPen(QPen(COR_SELECAO, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        lado = ALCA_TELA_PX
        # Oito alcas (0.1.9): os cantos e o meio de cada lado, como no Word.
        for ponto in alcas_do_retangulo(r).values():
            alca = QRectF(ponto.x() - lado / 2, ponto.y() - lado / 2, lado, lado)
            p.fillRect(alca, COR_FOLHA)
            p.drawRect(alca)
        p.restore()

    def _pintar_faixas(self, p: QPainter, m: Mapa, n: int, x0: float, y0: float,
                       n_total: int, largura_folha: float | None = None) -> None:
        """Cabecalho e rodape da folha n, por cima dos tiles. Na edicao, o corpo esmaece."""
        editada = self._faixa_editada()
        t = QTransform().translate(x0, y0).scale(m.escala, m.escala)
        if editada is None:
            parte = "texto" if self._tiles_transparentes else "tudo"
            for onde in ("cabecalho", "rodape"):
                self._faixa_da_tela(p, m, n, x0, y0, n_total, onde, parte)
            return
        faixa, cursor = editada
        efetiva = self.layout_pag.efetiva_da(n)
        corpo = QRectF(x0 + efetiva.margem_esq_tw * m.escala, y0 + efetiva.margem_sup_tw * m.escala,
                       efetiva.corpo_largura_tw() * m.escala, efetiva.corpo_altura_tw() * m.escala)
        p.fillRect(corpo, COR_VEU)
        desenhar_faixas(p, self.layout_pag, n, t, n_total, 1.0, faixa, cursor,
                        marcas=self._marcas, tela=True)
        # Linha tracejada e rotulo no limite de cada area, em todas as paginas.
        p.save()
        fonte = p.font()
        fonte.setPointSizeF(8.0)
        p.setFont(fonte)
        metrica = p.fontMetrics()
        for onde, y_tw in (("cabecalho", efetiva.margem_sup_tw),
                           ("rodape", efetiva.altura_tw - efetiva.margem_inf_tw)):
            y = y0 + y_tw * m.escala
            p.setPen(QPen(COR_ROTULO_FAIXA, 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x0, y), QPointF(x0 + (largura_folha or m.largura_folha), y))
            rotulo = rotulo_da_faixa(onde, n, self.layout_pag.pagina_da_folha(n),
                                     self.layout_pag)
            larg = metrica.horizontalAdvance(rotulo) + 10
            alto = metrica.height() + 2
            caixa = QRectF(x0 + 4, y if onde == "cabecalho" else y - alto, larg, alto)
            p.fillRect(caixa, QColor(0xDD, 0xE6, 0xF4))
            p.setPen(COR_ROTULO_FAIXA)
            p.drawText(caixa, Qt.AlignmentFlag.AlignCenter, rotulo)
        p.restore()

    def _desenhar_imagem_selecionada(self, p: QPainter) -> None:
        """Quadro e alcas nos quatro cantos da imagem selecionada; tracejado durante o arrasto."""
        pos = self._posicao_imagem_selecionada()
        if pos is None:
            return
        r = self.retangulo_imagem_na_tela(pos)
        if r is None:
            return
        p.save()
        p.setPen(QPen(COR_SELECAO, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        lado = ALCA_TELA_PX
        for canto in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
            alca = QRectF(canto.x() - lado / 2, canto.y() - lado / 2, lado, lado)
            p.fillRect(alca, COR_FOLHA)
            p.drawRect(alca)
        novo = self._retangulo_redimensionando()
        if novo is not None:
            p.setPen(QPen(COR_SELECAO, 1, Qt.PenStyle.DashLine))
            p.drawRect(novo)
        p.restore()

    def _desenhar_caret(self, p: QPainter, m: Mapa, dpr: float, n_total: int) -> None:
        if not self._caret_ligado or not self.hasFocus():
            return
        r = self._retangulo_do_caret(m, n_total)
        if r is None:
            return
        x, y = alinhar_ao_dispositivo(r.x(), dpr), alinhar_ao_dispositivo(r.y(), dpr)
        p.fillRect(QRectF(x, y, 1.0 / dpr, r.height()), COR_CARET)

    def _desenhar_quebras(self, p: QPainter, m: Mapa, i0: int, i1: int, n_total: int) -> None:
        """Linha tracejada 'Quebra de pagina' onde um paragrafo comeca numa pagina nova.

        A linha vai no fim do paragrafo anterior, que e' onde a quebra acontece. Fica
        dentro do corpo: nada e' pintado nas margens.
        """
        doc = self.layout_pag.doc
        dl = doc.documentLayout()
        quebras = self._blocos_com_quebra()
        if not quebras:
            return
        topo = i0 * self.layout_pag.hb
        inicio = doc.findBlock(dl.hitTest(QPointF(0, topo), Qt.FuzzyHit)).blockNumber()
        limite = (i1 + 1) * self.layout_pag.hb
        fonte = p.font()
        fonte.setPointSizeF(8.0)
        p.save()
        p.setFont(fonte)
        for numero in quebras:
            if numero < inicio:
                continue
            bloco = doc.findBlockByNumber(numero)
            if not bloco.isValid() or dl.blockBoundingRect(bloco).top() >= limite:
                break
            anterior = bloco.previous()
            if anterior.isValid():
                y = dl.blockBoundingRect(anterior).bottom()
                corpo_w = float(self.layout_pag.efetiva_da(
                    self.layout_pag.pagina_de_y(max(0.0, y - 1.0))).corpo_largura_tw())
                xa, ya = m.doc_para_tela(0.0, y, n_total)
                xb, _ = m.doc_para_tela(corpo_w, y, n_total)
                p.setPen(QPen(COR_QUEBRA, 1, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(xa, ya), QPointF(xb, ya))
                rotulo = "Quebra de página"
                metrica = p.fontMetrics()
                larg = metrica.horizontalAdvance(rotulo) + 12
                meio = (xa + xb) / 2.0
                p.fillRect(QRectF(meio - larg / 2, ya - metrica.height() / 2, larg,
                                  metrica.height()), COR_FOLHA)
                p.setPen(COR_QUEBRA)
                p.drawText(QRectF(meio - larg / 2, ya - metrica.height() / 2, larg,
                                  metrica.height()), Qt.AlignmentFlag.AlignCenter, rotulo)
        p.restore()

    def _blocos_com_quebra(self) -> list[int]:
        """Numeros dos blocos com quebra de pagina do usuario, em ordem (0.1.15).

        Ate' a 0.1.14 cada pintura olhava o formato e o retangulo de todos os blocos das folhas
        visiveis (no plano, centenas de blocos de celula: 1,5 a 2,8 ms por tecla). A lista vale
        enquanto o numero de blocos nao muda e nenhuma mudanca troca formato (`_mudou_texto`:
        digitar so' insere ou so' apaga dentro dos blocos)."""
        doc = self.layout_pag.doc
        chave = (getattr(doc, "serie", id(doc)), doc.blockCount())
        if self._quebras is None or self._quebras[0] != chave:
            lista = []
            bloco = doc.begin()
            while bloco.isValid():
                # O espacador da area das notas (0.1.10) nao e' quebra do usuario: sem rotulo.
                # Nem a quebra derivada da secao (0.1.12): a quebra de secao tem o seu rotulo.
                bf = bloco.blockFormat()
                if bool(bf.pageBreakPolicy() & _QUEBRA_ANTES) and \
                        not pq_notas.eh_espacador(bf) and not pq_secoes.eh_derivada(bf) and                         not pq_paginacao.eh_regra(bf):  # 0.1.17: nem a das regras do Word
                    lista.append(bloco.blockNumber())
                bloco = bloco.next()
            self._quebras = (chave, lista)
        return self._quebras[1]

    # ----- eventos de tela ------------------------------------------------
    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        if self._zoom > self.teto_do_zoom() + 1e-9:
            self._zoom = self.teto_do_zoom()
            self._limpar_cache()
            self.zoomAlterado.emit(self._zoom)
        self._atualizar_geometria()

    def scrollContentsBy(self, dx, dy) -> None:
        self.viewport().update()

    def focusNextPrevChild(self, proximo) -> bool:
        # Tab e' do editor (caractere de tabulacao), nao do foco da janela.
        return False

    def focusInEvent(self, ev) -> None:
        super().focusInEvent(ev)
        self.viewport().update()

    def focusOutEvent(self, ev) -> None:
        super().focusOutEvent(ev)
        self.viewport().update()

    def wheelEvent(self, ev) -> None:
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            aumentar = ev.angleDelta().y() > 0
            ancora = QPointF(ev.position())
            self.definir_zoom(passo_de_zoom(self._zoom, aumentar, self.dpr()), manter=ancora)
            ev.accept()
            return
        super().wheelEvent(ev)

