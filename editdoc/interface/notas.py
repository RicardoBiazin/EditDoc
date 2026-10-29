"""Notas de rodape e de fim na tela, no PDF e na impressao (0.1.10).

Cada nota e' um QTextDocument proprio (`NotaQt`), no mesmo dispositivo de 1440 dpi do corpo,
com a largura do corpo e o catalogo de estilos do corpo (como o cabecalho). O conteudo vem do
catalogo do corpo (`ponte_qt/notas.py`); o documento da nota e' refeito quando a chave muda
(desfazer no corpo devolve a nota antiga).

Paginacao (decidida pelo spike, docs/SPIKES.md "0.1.10"): o QTextDocument do corpo pagina com
um tamanho so', e a area das notas tem de encolher o corpo da pagina onde esta' a referencia.
O espacador e' a quebra de pagina do Qt num bloco do corpo, com uma marca (PROP_QUEBRA_NOTA):
o primeiro bloco que nao cabe acima da area das notas comeca na pagina seguinte. `atualizar`
confere pagina a pagina, de cima para baixo:

- a linha que nao cabe com as notas das referencias ate' ela (as anteriores inteiras, as da
  propria linha pelo menos com a primeira linha, como o Word) empurra o bloco dela para a
  pagina seguinte; a primeira unidade da pagina nunca e' empurrada (a nota que nao cabe
  continua na pagina seguinte, com o separador de continuacao);
- o bloco empurrado volta quando, no lugar dele, todas as linhas que ficariam na pagina
  caberiam (simulado com as alturas das linhas dele);
- so' o bloco inteiro (ou a tabela inteira) desce: um paragrafo longo deixa a sobra do pe' da
  pagina em branco (limite registrado; o Word parte o paragrafo). Uma tabela que comecou na
  pagina anterior nao e' empurrada: a nota que nao cabe continua na pagina seguinte.

O espacador e' formato de bloco: entra no desfazer. Depois de uma edicao do usuario, o ajuste
fica num passo proprio, anotado (`passos`): o desfazer e o refazer do painel passam por ele
junto com o passo do usuario, e o documento volta ao estado de antes, ja' ajustado. Na edicao
de uma nota, o primeiro toque cria um passo no corpo (a "sessao") e os ajustes e o conteudo
final entram nele: no corpo, um desfazer devolve a nota e os espacadores de antes.

Secoes (0.1.12): a pagina k do QTextDocument continua sendo [k*hb, (k+1)*hb), com hb a maior
altura de corpo entre as secoes; numa secao mais baixa o corpo termina antes (`_pe`), e o mesmo
espacador empurra o bloco que passa dele, com ou sem notas na pagina.

Distribuicao: depois de cada pagina conferida, as notas dela (e o que continuou da anterior)
vao para a area de baixo: separador curto, notas inteiras ou cortadas numa linha; o que nao
cabe continua na pagina seguinte, depois do separador de continuacao (largura toda). As notas
de fim vem depois do texto da ultima pagina e seguem em paginas a mais (`extras`), que
`LayoutPaginado.numero_paginas` conta.
"""

from __future__ import annotations

import bisect
import itertools
import math
from dataclasses import dataclass, field, replace

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QAbstractTextDocumentLayout, QColor, QFontMetricsF, QPen,
                           QTextCharFormat, QTextCursor, QTextFormat, QTextTable)

from editdoc import log_interno
from editdoc.modelo import notas as mod_notas
from editdoc.ponte_qt import notas as pq

log = log_interno.obter(__name__)

#: Limite de mudancas de espacador por rodada e de rodadas (contra laco sem fim).
MAX_MUDANCAS_POR_PAGINA = 4
MAX_RODADAS = 4
#: Maior numero de paginas a mais (so' notas) depois do texto.
MAX_EXTRAS = 2000
#: Separador do Word: 2 polegadas (o de continuacao vai na largura do corpo).
LARGURA_SEPARADOR_TW = 2880
ESPESSURA_SEPARADOR_TW = 10
#: Folga contra arredondamento entre o simulado e o layout do Qt.
FOLGA = 0.5
_QUEBRA = QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore
_SERIE = itertools.count(1)


class NotaQt:
    """Uma nota em edicao ou na tela: o documento, o dispositivo e a chave do conteudo."""

    onde = "nota"

    def __init__(self, nota: mod_notas.Nota, chave: str, fonte, largura_tw: float,
                 doc_estilos) -> None:
        from editdoc.interface.layout_paginado import criar_dispositivo_layout
        from editdoc.ponte_qt import para_qt
        from editdoc.ponte_qt.imagens import DocumentoQt
        self.tipo = nota.tipo
        self.id = nota.id
        self.chave = chave
        self.serie = next(_SERIE)
        self._dispositivo = criar_dispositivo_layout()
        self.doc = DocumentoQt()
        self.doc.setDocumentMargin(0)
        self.doc.setDefaultFont(fonte)
        self.doc.documentLayout().setPaintDevice(self._dispositivo)
        self.doc.setTextWidth(float(largura_tw))
        self.doc._doc_estilos = doc_estilos
        self.doc._numero_da_nota = ""
        para_qt.preencher_blocos(self.doc, list(nota.paragrafos))
        self.doc.setModified(False)
        self._cortes: tuple | None = None
        self.doc.contentsChanged.connect(self._mudou)

    def _mudou(self) -> None:
        self._cortes = None

    def altura(self) -> float:
        return float(self.doc.documentLayout().documentSize().height())

    def cortes(self) -> tuple:
        """Bases das linhas (onde a nota pode ser cortada), em ordem."""
        if self._cortes is None:
            dl = self.doc.documentLayout()
            saida = set()
            bloco = self.doc.begin()
            while bloco.isValid():
                r = dl.blockBoundingRect(bloco)
                lay = bloco.layout()
                for i in range(lay.lineCount()):
                    linha = lay.lineAt(i)
                    saida.add(round(r.top() + linha.y() + linha.height(), 3))
                bloco = bloco.next()
            altura = self.altura()
            self._cortes = tuple(sorted(x for x in saida if 0 < x <= altura + 1)) or (altura,)
        return self._cortes

    def primeira_linha(self) -> float:
        return self.cortes()[0]

    def corte_ate(self, y0: float, espaco: float) -> float:
        """A maior base de linha em (y0, y0 + espaco]; y0 se nem uma linha cabe."""
        melhor = y0
        for c in self.cortes():
            if c <= y0 + FOLGA:
                continue
            if c - y0 <= espaco + FOLGA:
                melhor = c
            else:
                break
        return melhor

    def definir_numero(self, texto: str) -> None:
        if self.doc._numero_da_nota != texto:
            self.doc._numero_da_nota = texto
            pq.refazer_marcas(self.doc)
            self._cortes = None

    def definir_largura(self, largura_tw: float) -> None:
        if abs(self.doc.textWidth() - largura_tw) > 0.5:
            self.doc.setTextWidth(float(largura_tw))
            self._cortes = None

    def fechar(self) -> None:
        if self._dispositivo is not None:
            self.doc.documentLayout().setPaintDevice(None)
            self._dispositivo = None

    def __del__(self) -> None:
        try:
            self.fechar()
        except Exception:  # noqa: BLE001 - destruicao nao pode levantar
            pass


@dataclass
class Fatia:
    """Um pedaco da area de notas de uma pagina: separador ou trecho de uma nota.

    `y`: topo, em coordenadas do documento do corpo (a pagina n ocupa [n*hb, (n+1)*hb), tambem
    nas paginas a mais). `y0`/`y1`: o trecho do documento da nota (so' na nota)."""
    tipo: str  # "separador", "continuacao" ou "nota"
    y: float
    altura: float
    nota: NotaQt | None = None
    y0: float = 0.0
    y1: float = 0.0
    classe: str = "rodape"  # rodape ou fim


@dataclass
class _Unidade:
    """Bloco ou tabela do primeiro nivel do corpo, com as linhas (topo, base) absolutas."""
    indice: int
    bloco: object = None
    tabela: QTextTable | None = None
    topo: float = 0.0
    base: float = 0.0
    linhas: list = field(default_factory=list)

    def formato(self):
        return self.tabela.format() if self.tabela is not None else self.bloco.blockFormat()

    def espacador(self) -> bool:
        return pq.eh_espacador(self.formato())

    def quebra_do_usuario(self) -> bool:
        f = self.formato()
        return bool(f.pageBreakPolicy() & _QUEBRA) and not pq.eh_espacador(f)


@dataclass
class _Medida:
    """O que o plano mede do corpo numa passada (refeito depois de cada ajuste)."""
    unidades: list
    topos: list
    refs: list
    por_pagina: dict
    docs: dict


class ConjuntoDeNotas:
    """As notas do documento na tela: documentos, plano das paginas e o desfazer dos ajustes."""

    def __init__(self, layout) -> None:
        self.layout = layout
        self._docs: dict[str, NotaQt] = {}
        #: pagina -> fatias; e quantas paginas so' de notas vem depois do texto
        self.paginas: dict[int, list[Fatia]] = {}
        self.extras = 0
        self._assinatura: tuple | None = None
        #: posicoes do desfazer do corpo que sao so' ajuste de espacador (ver o topo)
        self.passos: set[int] = set()
        self.indice = 0
        self._aplicando = False
        #: nota em edicao: (NotaQt, chave antiga, ja' tem passo no corpo)
        self.sessao: dict | None = None
        #: ha' espacador no corpo (0.1.12: as secoes baixas tambem empurram blocos)
        self._espacadores_vivos = False
        #: contagem de ajustes (os testes de desempenho conferem)
        self.ajustes = 0
        self._juntar_ajuste = False
        #: conferencia so' do que mudou: a menor posicao editada desde o plano, a continuacao
        #: que entra em cada pagina e a assinatura das linhas de cada pagina no plano anterior
        self._desde: int | None = None
        self._cont: dict[int, float] = {}
        self._assinaturas: dict[int, tuple] = {}
        #: paginas conferidas no ultimo plano (os testes de desempenho olham)
        self.conferidas = 0
        layout.doc.contentsChange.connect(self._mudou_corpo)
        layout.doc.undoCommandAdded.connect(self._comando_novo)

    # -- documentos das notas -----------------------------------------------------------
    def _fonte(self):
        return self.layout.doc.defaultFont()

    def _largura(self) -> float:
        return float(self.layout.largura_das_notas())

    def _topo(self, k: int) -> float:
        """Y do topo da pagina k (0.1.20: pela camada `layout.mapa`)."""
        return self.layout.mapa.topo(k)

    def _fim(self, k: int) -> float:
        return self.layout.mapa.fim(k)

    def _pe(self, k: int) -> float:
        """Onde o corpo da pagina k termina (0.1.12: a secao da pagina pode ser mais baixa)."""
        # Colunas (passo 2): k e' a coluna; a altura e' a da folha dela.
        return self._topo(k) + self.layout.altura_do_corpo(self.layout.mapa.folha_da_pagina(k))

    def _curta(self, k: int) -> bool:
        return self._pe(k) < self._fim(k) - FOLGA

    def doc_de(self, nota: mod_notas.Nota) -> NotaQt:
        k = pq.chave(nota)
        d = self._docs.get(k)
        if d is None:
            d = NotaQt(nota, k, self._fonte(), self._largura(), self.layout.doc)
            self._docs[k] = d
        return d

    def nota_qt(self, tipo: str, ident: int) -> NotaQt | None:
        nota = pq.catalogo(self.layout.doc).obter(tipo, ident)
        return self.doc_de(nota) if nota is not None else None

    def todos(self) -> list[NotaQt]:
        return list(self._docs.values())

    def definir_fonte(self, fonte) -> None:
        for d in self._docs.values():
            d.doc.setDefaultFont(fonte)
            d.doc.setModified(False)
            d._cortes = None
        self._assinatura = None

    def definir_largura(self, largura_tw: float) -> None:
        for d in self._docs.values():
            d.definir_largura(largura_tw)
        self._assinatura = None

    def limpar(self) -> None:
        """Documento novo carregado: documentos das notas, plano e desfazer zerados."""
        if self.sessao is not None:
            self.sessao = None
        for d in self._docs.values():
            d.fechar()
        self._docs.clear()
        self.paginas = {}
        self.extras = 0
        self._assinatura = None
        self.passos.clear()
        self.indice = 0

    def _podar_docs(self, cat) -> None:
        """Documentos de chaves que o catalogo nao usa mais: no maximo 256 guardados."""
        if len(self._docs) <= 256:
            return
        vivas = {pq.chave(n) for n in cat.todas()}
        if self.sessao is not None:
            vivas.add(self.sessao["nota"].chave)
        for k in [k for k in self._docs if k not in vivas][:len(self._docs) - 256]:
            self._docs.pop(k).fechar()

    # -- desfazer --------------------------------------------------------------------------
    def _comando_novo(self) -> None:
        if self._aplicando:
            return
        n = self.layout.doc.availableUndoSteps()
        # O comando novo trunca o refazer: o que estava acima do indice de antes nao existe mais.
        self.passos = {p for p in self.passos if p <= self.indice}
        self.indice = n

    def _mudou_corpo(self, pos: int, _removidos: int, _adicionados: int) -> None:
        if not self._aplicando:
            self._desde = pos if self._desde is None else min(self._desde, pos)

    def zerar_desfazer(self) -> None:
        self.passos.clear()
        self.indice = self.layout.doc.availableUndoSteps()

    def desfazer(self, doc, cursor) -> None:
        """Desfaz o passo do usuario e os ajustes que vieram depois dele."""
        while doc.isUndoAvailable() and doc.availableUndoSteps() in self.passos:
            doc.undo(cursor)
        if doc.isUndoAvailable():
            doc.undo(cursor)
        self.indice = doc.availableUndoSteps()
        self._assinatura = None

    def refazer(self, doc, cursor) -> None:
        """Refaz o passo do usuario e os ajustes anotados logo depois dele."""
        if doc.isRedoAvailable():
            doc.redo(cursor)
        while doc.isRedoAvailable():
            doc.redo(cursor)
            if doc.availableUndoSteps() not in self.passos:
                doc.undo(cursor)
                break
        self.indice = doc.availableUndoSteps()
        self._assinatura = None

    # -- edicao de uma nota --------------------------------------------------------------
    def iniciar_sessao(self, nota: NotaQt) -> None:
        self.concluir_sessao()
        self.sessao = {"nota": nota, "passo": False}
        nota.doc.contentsChanged.connect(self._nota_mudou)

    def _nota_mudou(self) -> None:
        s = self.sessao
        if s is None or s["passo"]:
            return
        nota = s["nota"]
        if not nota.doc.isModified():
            return
        # Primeiro toque: um passo no corpo (a nota aponta para uma chave provisoria). Os ajustes
        # da sessao e o conteudo final entram nele.
        doc = self.layout.doc
        cat = pq.catalogo(doc)
        atual = cat.obter(nota.tipo, nota.id)
        if atual is None:
            return
        provisoria = replace(atual)
        self._trocar_chave(nota, provisoria)
        itens = {t: [provisoria if (n.tipo, n.id) == (nota.tipo, nota.id) else n
                     for n in cat.itens.get(t, [])] for t in mod_notas.TIPOS}
        self._aplicando = True
        try:
            c = QTextCursor(doc)
            c.beginEditBlock()
            pq.trocar(doc, itens)
            c.endEditBlock()
        finally:
            self._aplicando = False
        self.passos = {p for p in self.passos if p <= self.indice}
        self.indice = doc.availableUndoSteps()
        s["passo"] = True
        self._assinatura = None

    def _trocar_chave(self, nota: NotaQt, novo: mod_notas.Nota) -> None:
        k = pq.chave(novo)
        self._docs.pop(nota.chave, None)
        nota.chave = k
        self._docs[k] = nota

    def concluir_sessao(self, sair: bool = True) -> bool:
        """Grava o conteudo da nota em edicao no catalogo do corpo (no passo da sessao). True se
        a nota mudou. `sair` False: continua na edicao (salvar no meio)."""
        s = self.sessao
        if s is None:
            return False
        nota = s["nota"]
        mudou = False
        if s["passo"]:
            from editdoc.ponte_qt import de_qt
            doc = self.layout.doc
            cat = pq.catalogo(doc)
            if cat.obter(nota.tipo, nota.id) is not None:
                blocos = de_qt.extrair_blocos(nota.doc, round(self._largura()))
                final = mod_notas.Nota(nota.tipo, nota.id, tuple(blocos))
                self._trocar_chave(nota, final)
                itens = {t: [final if (n.tipo, n.id) == (nota.tipo, nota.id) else n
                             for n in cat.itens.get(t, [])] for t in mod_notas.TIPOS}
                self._aplicando = True
                try:
                    c = QTextCursor(doc)
                    c.joinPreviousEditBlock()
                    pq.trocar(doc, itens)
                    c.endEditBlock()
                finally:
                    self._aplicando = False
                self.indice = doc.availableUndoSteps()
                mudou = True
        nota.doc.setModified(False)
        s["passo"] = False
        if sair:
            try:
                nota.doc.contentsChanged.disconnect(self._nota_mudou)
            except (RuntimeError, TypeError):
                pass
            self.sessao = None
        self._assinatura = None
        return mudou

    # -- plano ---------------------------------------------------------------------------
    def _unidades(self) -> list[_Unidade]:
        doc = self.layout.doc
        dl = doc.documentLayout()
        saida = []
        it = doc.rootFrame().begin()
        i = 0
        while not it.atEnd():
            quadro = it.currentFrame()
            if quadro is not None:
                r = dl.frameBoundingRect(quadro)
                saida.append(_Unidade(i, tabela=quadro if isinstance(quadro, QTextTable) else None,
                                      topo=r.top(), base=r.bottom()))
            else:
                b = it.currentBlock()
                if b.isValid():
                    r = dl.blockBoundingRect(b)
                    saida.append(_Unidade(i, bloco=b, topo=r.top(), base=r.bottom()))
            i += 1
            it += 1
        return saida

    def _linhas(self, u: _Unidade) -> list:
        if u.linhas:
            return u.linhas
        dl = self.layout.doc.documentLayout()
        if u.bloco is not None:
            lay = u.bloco.layout()
            topo = u.topo
            u.linhas = [(topo + lay.lineAt(i).y(), topo + lay.lineAt(i).y() + lay.lineAt(i).height())
                        for i in range(lay.lineCount())]
        elif u.tabela is not None:
            linhas = []
            bloco = u.tabela.firstCursorPosition().block()
            fim = u.tabela.lastPosition()
            while bloco.isValid() and bloco.position() <= fim:
                lay = bloco.layout()
                topo = dl.blockBoundingRect(bloco).top()
                for i in range(lay.lineCount()):
                    ln = lay.lineAt(i)
                    linhas.append((topo + ln.y(), topo + ln.y() + ln.height()))
                bloco = bloco.next()
            u.linhas = sorted(linhas)
        if not u.linhas:
            u.linhas = [(u.topo, max(u.base, u.topo))]
        return u.linhas

    def _referencias(self) -> list:
        """(marca, topo, base da linha) de cada referencia, na ordem do texto."""
        doc = self.layout.doc
        dl = doc.documentLayout()
        saida = []
        for pos, m in pq.referencias(doc):
            bloco = doc.findBlock(pos)
            lay = bloco.layout()
            linha = lay.lineForTextPosition(pos - bloco.position())
            topo = dl.blockBoundingRect(bloco).top()
            if linha.isValid():
                saida.append((m, topo + linha.y(), topo + linha.y() + linha.height()))
            else:
                saida.append((m, topo, topo + 1))
        return saida

    def _altura_separador(self) -> float:
        fonte = self.layout.doc.defaultFont()
        pontos = fonte.pointSizeF() if fonte.pointSizeF() > 0 else 11.0
        f = type(fonte)(fonte)
        f.setPixelSize(max(1, round(pontos * 20)))
        return float(QFontMetricsF(f).lineSpacing())

    def assinatura(self) -> tuple:
        doc = self.layout.doc
        return (doc.revision(), pq.assinatura(doc), self.layout.hb,
                self.layout.largura_das_notas(), doc.pageCount(),
                self.layout.geracao_das_secoes(),
                tuple((d.serie, d.doc.revision()) for d in self._docs.values()))

    def ativo(self) -> bool:
        """Ha' o que conferir: o catalogo tem nota, ou o plano anterior tinha area de notas. Sem
        nota nenhuma nao ha' referencia nem espacador (o espacador so' nasce com nota, e o
        desfazer que tira a ultima nota tira os espacadores junto): o plano nao roda (o arquivo
        do Word com so' as separadoras nao paga nada por tecla)."""
        return not (pq.catalogo(self.layout.doc).vazia() and not self.paginas
                    and not self.extras and not self.layout.secoes_baixas()
                    and not self._espacadores_vivos)

    def atualizar(self, forcar: bool = False) -> bool:
        """Confere os espacadores, os numeros e a distribuicao das notas. True se a tela muda
        (numero de marca refeito, area de notas diferente) e o cache tem de sair."""
        if not self.ativo():
            return False
        assinatura = self.assinatura()
        if not forcar and assinatura == self._assinatura:
            return False
        doc = self.layout.doc
        cat = pq.catalogo(doc)
        antes = (self._resumo(), dict(getattr(doc, "_numeros_notas", None) or {}))
        self._juntar_ajuste = False
        # So' o texto mudou (nem catalogo, nem nota, nem pagina): as paginas antes da edicao
        # ficam como estavam; a conferencia comeca na pagina de antes da edicao.
        desde = 0
        velha = self._assinatura
        if not forcar and velha is not None and self._desde is not None and \
                velha[1:4] == assinatura[1:4] and velha[5:] == assinatura[5:]:
            bloco = doc.findBlock(min(self._desde, doc.characterCount() - 1))
            topo = doc.documentLayout().blockBoundingRect(bloco).top()
            desde = max(0, self.layout.mapa.pagina_de_y(topo) - 1)
            if desde not in self._cont:
                desde = 0
        self._desde = None
        try:
            for _ in range(MAX_RODADAS):
                if not self._rodada(cat, desde):
                    break
                desde = 0
        except Exception:  # noqa: BLE001 - o plano das notas nao pode derrubar a pintura
            log.exception("plano das notas")
        self._desde = None
        self._juntar_ajuste = False
        self._podar_docs(cat)
        self._assinatura = self.assinatura()
        return (self._resumo(), getattr(doc, "_numeros_notas", None)) != antes

    def _resumo(self) -> tuple:
        return (self.extras, tuple(sorted((n, tuple((f.tipo, f.y, f.altura, f.y0, f.y1,
                                                    f.nota.serie if f.nota else 0)
                                                   for f in fs))
                                          for n, fs in self.paginas.items())))

    def _medir(self, cat):
        unidades = self._unidades()
        refs = self._referencias()
        docs = {}
        for m, _t, _b in refs:
            if (m.tipo, m.id) not in docs:
                nota = cat.obter(m.tipo, m.id)
                if nota is not None:
                    docs[(m.tipo, m.id)] = self.doc_de(nota)
        por_pagina: dict[int, list] = {}
        for m, t, b in refs:
            if m.tipo == "rodape" and (m.tipo, m.id) in docs:
                por_pagina.setdefault(self.layout.mapa.pagina_de_y(t, 1e-6), []).append((m, t, b))
        return _Medida(unidades, [u.topo for u in unidades], refs, por_pagina, docs)

    def _rodada(self, cat, desde: int = 0) -> bool:
        """Uma passada do plano. True se algo mudou que pede outra (numero refeito)."""
        doc = self.layout.doc
        sep = self._altura_separador()
        med = self._medir(cat)
        baixas = self.layout.secoes_baixas()
        if med.por_pagina or baixas or any(u.espacador() for u in med.unidades):
            med = self._espacadores(med, sep, cat, desde)
        self._espacadores_vivos = any(u.espacador() for u in med.unidades)
        paginas_refs = {(m.tipo, m.id): self.layout.mapa.pagina_de_y(t, 1e-6)
                    for m, t, _b in med.refs}
        props = {t: cat.propriedades(t) for t in mod_notas.TIPOS}
        numeros = mod_notas.numeros([(m.tipo, m.id, m.personalizada) for m, _t, _b in med.refs],
                                    props, paginas_refs)
        refazer = False
        if numeros != getattr(doc, "_numeros_notas", None):
            doc._numeros_notas = numeros
            pq.refazer_marcas(doc)
            refazer = True
        for m, _t, _b in med.refs:
            d = med.docs.get((m.tipo, m.id))
            if d is not None:
                d.definir_numero(mod_notas.texto_do_simbolo(m.simbolo) if m.personalizada
                                 else numeros.get((m.tipo, m.id), ""))
        if refazer:
            med = self._medir(cat)
        self._distribuir(med, sep, props)
        return refazer

    # -- espacadores ------------------------------------------------------------------------
    def _linhas_da_pagina(self, med, k: int) -> list:
        """(topo, base, unidade) das linhas cujo topo cai na pagina k."""
        topo_p, pe = self._topo(k), self._fim(k)
        i = max(0, bisect.bisect_right(med.topos, topo_p + FOLGA) - 1)
        saida = []
        while i < len(med.unidades):
            u = med.unidades[i]
            if u.topo >= pe - FOLGA:
                break
            if u.base >= topo_p - FOLGA:
                for t, b in self._linhas(u):
                    if topo_p - FOLGA <= t < pe - FOLGA:
                        saida.append((t, b, u))
            i += 1
        return saida

    def _assinatura_da_pagina(self, med, k: int, continuacao: float) -> tuple:
        linhas = tuple((round(t - self._topo(k), 2), round(b - self._topo(k), 2))
                       for t, b, _u in self._linhas_da_pagina(med, k))
        refs = tuple((m.tipo, m.id, round(t - self._topo(k), 2))
                     for m, t, _b in med.por_pagina.get(k, ()))
        alturas = tuple(round(med.docs[(m.tipo, m.id)].altura(), 2)
                        for m, _t, _b in med.por_pagina.get(k, ()))
        proxima = self._espacador_da_pagina(med, k)
        return (linhas, refs, alturas, round(continuacao, 2), proxima is not None)

    def _fim_do_corpo(self, med, k: int) -> float:
        """A base da ultima linha do corpo na pagina k (o topo dela, se vazia)."""
        topo_p, pe = self._topo(k), self._fim(k)
        i = bisect.bisect_left(med.topos, pe - FOLGA) - 1
        while i >= 0:
            u = med.unidades[i]
            if u.base <= topo_p - FOLGA:
                return topo_p
            if u.base <= pe + FOLGA and u.topo >= topo_p - FOLGA and u.bloco is not None:
                return u.base if self._linhas(u)[-1][0] < pe - FOLGA else topo_p
            bases = [b for t, b in self._linhas(u) if topo_p - FOLGA <= t < pe - FOLGA]
            if bases:
                return max(bases)
            i -= 1
        return topo_p

    def _espacadores(self, med, sep, cat, desde: int = 0):
        k = desde
        continuacao = self._cont.get(k, 0.0) if k else 0.0
        if k == 0:
            self._cont = {}
            self._assinaturas = {}
        tentativas: dict[int, int] = {}
        mudancas = 0
        mudou_algo = False
        self.conferidas = 0
        while k < self.layout.paginas_do_texto() and \
                mudancas < 4 * self.layout.paginas_do_texto() + 16:
            self._cont[k] = continuacao
            if desde and not mudou_algo and k > desde + 1:
                # Pagina igual a do plano anterior (as mesmas linhas, notas e continuacao):
                # as seguintes tambem sao.
                sig = self._assinatura_da_pagina(med, k, continuacao)
                if self._assinaturas.get(k) == sig:
                    break
            self.conferidas += 1
            tem_nota = k in med.por_pagina or continuacao > 0
            proxima = self._espacador_da_pagina(med, k)
            if tem_nota or proxima is not None or self._curta(k):
                mudou = self._conferir_pagina(k, med, sep, continuacao,
                                              tentativas.get(k, 0) < MAX_MUDANCAS_POR_PAGINA)
                if mudou:
                    tentativas[k] = tentativas.get(k, 0) + 1
                    mudancas += 1
                    mudou_algo = True
                    med = self._medir(cat)
                    continue
            self._assinaturas[k] = self._assinatura_da_pagina(med, k, continuacao)
            continuacao = self._continua(k, med, sep, continuacao) if tem_nota else 0.0
            k += 1
        # Espacador no primeiro bloco do documento nao serve para nada; e o que nao segue a
        # ultima linha de uma pagina com nota (sobra de texto apagado) tambem sai na conferencia.
        if med.unidades and med.unidades[0].espacador():
            self._marcar(med.unidades[0], False)
            med = self._medir(cat)
        return med

    def _espacador_da_pagina(self, med, k: int):
        """A unidade com espacador que comeca a pagina k+1 (empurrada da pagina k), ou None."""
        pe = self._fim(k)
        i = bisect.bisect_left(med.topos, pe - FOLGA)
        while i < len(med.unidades) and med.unidades[i].topo < pe + self.layout.mapa.hb:
            u = med.unidades[i]
            if u.espacador() and i > 0 and med.unidades[i - 1].topo < pe - FOLGA:
                return u
            if u.topo >= pe - FOLGA:
                break
            i += 1
        return None

    def _notas_da_linha(self, med, k: int, t: float, b: float) -> list:
        return [(m.tipo, m.id) for m, rt, _rb in med.por_pagina.get(k, ())
                if t - FOLGA <= rt < b - FOLGA]

    @staticmethod
    def _cabe(base, pe, continuacao, sep, inteiras, da_linha, docs) -> bool:
        reserva = continuacao
        if inteiras > 0 or da_linha:
            reserva += sep
        reserva += inteiras + sum(docs[c].primeira_linha() for c in da_linha)
        return base + reserva <= pe + FOLGA

    # -- linha de tabela empurrada (0.1.12) -------------------------------------------------------
    @staticmethod
    def _celulas_da_linha(tabela, r: int) -> list:
        return [tabela.cellAt(r, c) for c in range(tabela.columns())
                if tabela.cellAt(r, c).row() == r and tabela.cellAt(r, c).column() == c]

    def _topo_da_linha(self, tabela, r: int) -> float:
        """Topo da linha r da tabela (o do primeiro bloco das celulas dela)."""
        dl = self.layout.doc.documentLayout()
        topos = [dl.blockBoundingRect(c.firstCursorPosition().block()).top()
                 for c in self._celulas_da_linha(tabela, r)]
        return min(topos) if topos else dl.frameBoundingRect(tabela).top()

    def _base_da_linha(self, tabela, r: int) -> float:
        dl = self.layout.doc.documentLayout()
        bases = [dl.blockBoundingRect(c.lastCursorPosition().block()).bottom()
                 for c in self._celulas_da_linha(tabela, r)]
        return max(bases) if bases else dl.frameBoundingRect(tabela).bottom()

    @staticmethod
    def _empurrao(cel) -> tuple[float, float] | None:
        """(acolchoamento de baixo original, acrescimo) em px96 da celula empurrada, ou None."""
        valor = cel.format().property(pq.PROP_LINHA_EMPURRADA)
        if isinstance(valor, str) and ";" in valor:
            try:
                original, extra = (float(x) for x in valor.split(";"))
                return original, extra
            except ValueError:
                return None
        return None

    def _definir_empurrao(self, tabela, r: int, extra_px: float) -> None:
        """Acolchoamento de baixo nas celulas da linha r (a linha seguinte desce para a pagina
        seguinte); extra 0 tira. Um ajuste anotado no desfazer, como o espacador."""
        def aplicar(_c) -> None:
            for cel in self._celulas_da_linha(tabela, r):
                fmt = cel.format().toTableCellFormat()
                atual = self._empurrao(cel)
                original = atual[0] if atual is not None else fmt.bottomPadding()
                if extra_px > 0.01:
                    fmt.setBottomPadding(original + extra_px)
                    fmt.setProperty(pq.PROP_LINHA_EMPURRADA, f"{original};{extra_px}")
                else:
                    fmt.setBottomPadding(original)
                    fmt.clearProperty(pq.PROP_LINHA_EMPURRADA)
                cel.setFormat(fmt)
        self.ajustar(aplicar)

    def _linhas_empurradas(self, k: int, med) -> bool:
        """Conferencia das linhas de tabela empurradas na pagina k de uma secao mais baixa:
        a linha seguinte que ja' caberia volta; o acrescimo que ficou errado (o texto de cima
        mudou) e' refeito. True se mudou."""
        pe = self._pe(k)
        alvo = self._fim(k) - 2.0
        for u in med.unidades:
            if u.tabela is None or u.topo >= self._fim(k) or u.base <= self._topo(k):
                continue
            t = u.tabela
            for r in range(t.rows() - 1):
                cels = self._celulas_da_linha(t, r)
                marcas = [m for m in (self._empurrao(c) for c in cels) if m is not None]
                if not marcas:
                    continue
                topo = self._topo_da_linha(t, r)
                if not (self._topo(k) - FOLGA <= topo < self._fim(k)):
                    continue
                extra_tw = marcas[0][1] * 15.0
                atual_tw = (cels[0].format().toTableCellFormat().bottomPadding()
                            - marcas[0][0]) * 15.0
                if atual_tw <= 0.5:
                    self._definir_empurrao(t, r, 0.0)  # a grade foi refeita: sem acrescimo
                    return True
                seguinte_topo = self._topo_da_linha(t, r + 1)
                altura = self._base_da_linha(t, r + 1) - seguinte_topo
                base_natural = self._base_da_linha(t, r) + (seguinte_topo - self._base_da_linha(t, r)) - extra_tw
                if base_natural + altura <= pe + FOLGA:
                    self._definir_empurrao(t, r, 0.0)
                    return True
                base_com = seguinte_topo
                if abs(base_com - alvo) > 1.5 and self.layout.mapa.pagina_de_y(seguinte_topo) == k:
                    novo = extra_tw + (alvo - base_com)
                    self._definir_empurrao(t, r, max(0.0, novo) / 15.0)
                    return True
        return False

    def _empurrar_linha(self, u, k: int, t_falha: float) -> bool:
        """A linha da tabela `u` com a linha de texto que passa do pe' (topo `t_falha`) desce
        para a pagina seguinte: acolchoamento de baixo na linha de antes (0.1.12, secao mais
        baixa; a tabela que comecou antes nao pode descer inteira). True se mudou."""
        tabela = u.tabela
        if tabela is None:
            return False
        linha = None
        for r in range(tabela.rows()):
            if self._topo_da_linha(tabela, r) <= t_falha + FOLGA:
                linha = r
            else:
                break
        if linha is None or linha == 0:
            return False
        anterior = linha - 1
        if self._topo_da_linha(tabela, anterior) < self._topo(k) - FOLGA:
            return False  # a linha de cima comecou na pagina anterior: linha mais alta que a pagina
        if any(self._empurrao(c) is not None for c in self._celulas_da_linha(tabela, anterior)):
            return False
        alvo = self._fim(k) - 2.0
        base = self._topo_da_linha(tabela, linha)
        extra = alvo - base
        if extra <= 0.5:
            return False
        self._definir_empurrao(tabela, anterior, extra / 15.0)
        return True

    def _conferir_pagina(self, k, med, sep, continuacao, pode_mudar: bool) -> bool:
        """Espacador da pagina k em dia. True se mudou (o layout muda; medir de novo)."""
        if not pode_mudar:
            return False
        if self._curta(k) and self._linhas_empurradas(k, med):
            return True
        pe = self._pe(k)
        docs = med.docs
        linhas = self._linhas_da_pagina(med, k)
        continuacao = min(continuacao, (pe - self._topo(k)) / 2)
        inteiras = 0.0
        falha = None
        for i, (t, b, u) in enumerate(linhas):
            da_linha = self._notas_da_linha(med, k, t, b)
            if i > 0 and not self._cabe(b, pe, continuacao, sep, inteiras, da_linha, docs):
                falha = i
                break
            inteiras += sum(docs[c].altura() for c in da_linha)
        atual = self._espacador_da_pagina(med, k)
        if falha is not None:
            u = linhas[falha][2]
            empurravel = (u is not linhas[0][2] and u.topo >= self._topo(k) - FOLGA
                          and not u.quebra_do_usuario())
            if not empurravel and u.tabela is not None and self._curta(k):
                # Secao mais baixa (0.1.12): a tabela que nao pode descer inteira desce a partir
                # da linha que passa do pe'.
                return self._empurrar_linha(u, k, linhas[falha][0])
            if not empurravel or u is atual:
                return False
            if atual is not None:
                self._marcar(atual, False)
            self._marcar(u, True)
            return True
        if atual is None or not linhas:
            return False
        # Sem falha: o empurrado volta se tudo dele que ficaria na pagina couber.
        ultima_base = max(b for _t, b, _u in linhas)
        gap = atual.topo - self._fim(k)
        delta = atual.topo - (ultima_base + max(gap, 0.0))
        k2 = k + 1
        if atual.tabela is not None:
            da_tabela = [(m.tipo, m.id) for m, rt, _rb in med.por_pagina.get(k2, ())
                         if atual.topo - FOLGA <= rt < atual.base]
            if not self._cabe(atual.base - delta, pe, continuacao, sep, inteiras, da_tabela,
                              docs):
                return False
        else:
            for t, b in self._linhas(atual):
                # 0.1.12: o Qt poe linhas ate' o fim da pagina (nao so' ate' o pe' da secao baixa).
                if t - delta >= self._fim(k) - FOLGA:
                    break
                da_linha = self._notas_da_linha(med, k2, t, b)
                if not self._cabe(b - delta, pe, continuacao, sep, inteiras, da_linha, docs):
                    return False
                inteiras += sum(docs[c].altura() for c in da_linha)
        self._marcar(atual, False)
        return True

    def _continua(self, k, med, sep, continuacao) -> float:
        """Altura das notas de rodape da pagina k (e da continuacao) que nao couberam."""
        pe = self._pe(k)
        fim_corpo = self._fim_do_corpo(med, k)
        vistos = set()
        total = continuacao
        for m, _t, _b in med.por_pagina.get(k, ()):
            if (m.tipo, m.id) not in vistos:
                vistos.add((m.tipo, m.id))
                total += med.docs[(m.tipo, m.id)].altura()
        if total <= 0:
            return 0.0
        return max(0.0, total - max(pe - fim_corpo - sep, 0.0))

    def _marcar(self, u: _Unidade, ligar: bool) -> None:
        """Liga ou desliga o espacador na unidade: um passo de desfazer anotado (os da mesma
        conferencia juntos), ou dentro do passo da sessao de edicao de uma nota."""
        doc = self.layout.doc
        sessao = self.sessao is not None and self.sessao.get("passo")
        self._aplicando = True
        try:
            c = QTextCursor(doc)
            if sessao or self._juntar_ajuste:
                c.joinPreviousEditBlock()
            else:
                c.beginEditBlock()
            if u.tabela is not None:
                fmt = u.tabela.format()
                if ligar:
                    fmt.setPageBreakPolicy(fmt.pageBreakPolicy() | _QUEBRA)
                    fmt.setProperty(pq.PROP_QUEBRA_NOTA, True)
                else:
                    fmt = pq.sem_espacador(fmt)
                u.tabela.setFormat(fmt)
            else:
                c.setPosition(u.bloco.position())
                fmt = u.bloco.blockFormat()
                if ligar:
                    # A quebra derivada da secao (0.1.12, depois do paragrafo) continua.
                    fmt.setPageBreakPolicy(fmt.pageBreakPolicy() | _QUEBRA)
                    fmt.setProperty(pq.PROP_QUEBRA_NOTA, True)
                else:
                    fmt = pq.sem_espacador(fmt)
                c.setBlockFormat(fmt)
            c.endEditBlock()
        finally:
            self._aplicando = False
        self.ajustes += 1
        if not sessao:
            n = doc.availableUndoSteps()
            if self._juntar_ajuste:
                self.passos.discard(self.indice)
            self.passos.add(n)
            self.indice = n
            self._juntar_ajuste = True

    def ajustar(self, aplicar) -> None:
        """Ajuste de formato que nao e' do usuario, feito por outro plano (as quebras e os recuos
        derivados das secoes, 0.1.12): o mesmo passo anotado do espacador. `aplicar(cursor)`
        muda os formatos com o cursor dado, dentro do bloco de edicao."""
        doc = self.layout.doc
        sessao = self.sessao is not None and self.sessao.get("passo")
        self._aplicando = True
        try:
            c = QTextCursor(doc)
            if sessao or self._juntar_ajuste:
                c.joinPreviousEditBlock()
            else:
                c.beginEditBlock()
            aplicar(c)
            c.endEditBlock()
        finally:
            self._aplicando = False
        self.ajustes += 1
        if not sessao:
            n = doc.availableUndoSteps()
            if self._juntar_ajuste:
                self.passos.discard(self.indice)
            self.passos.add(n)
            self.indice = n
            self._juntar_ajuste = True

    def separar_ajustes(self) -> None:
        """O proximo ajuste comeca um passo anotado novo (fim de uma conferencia)."""
        self._juntar_ajuste = False

    # -- distribuicao -------------------------------------------------------------------------
    def _distribuir(self, med, sep, props) -> None:
        qt_paginas = self.layout.paginas_do_texto()
        paginas: dict[int, list[Fatia]] = {}
        pendentes: list = []  # (NotaQt, y0) que continuam
        posicao = props["rodape"].posicao or "pageBottom"
        for k in range(qt_paginas):
            if k not in med.por_pagina and not pendentes:
                continue
            pe = self._pe(k)
            fim_corpo = self._fim_do_corpo(med, k)
            proprias = []
            for m, _t, _b in med.por_pagina.get(k, ()):
                d = med.docs[(m.tipo, m.id)]
                if d not in proprias:
                    proprias.append(d)
            fatias, pendentes = self._encher(pendentes, proprias, pe - fim_corpo, sep)
            if fatias:
                usado = sum(f.altura for f in fatias)
                topo = fim_corpo if posicao == "beneathText" else pe - usado
                self._posicionar(fatias, topo)
                paginas[k] = fatias
        # Notas de fim depois do texto da ultima pagina (e em paginas a mais).
        fim_docs = []
        for m, _t, _b in med.refs:
            d = med.docs.get((m.tipo, m.id))
            if m.tipo == "fim" and d is not None and d not in fim_docs:
                fim_docs.append(d)
        fila_fim = [(d, 0.0) for d in fim_docs]
        continuar_fim = False
        if fila_fim:
            k = qt_paginas - 1
            fim_corpo = self._fim_do_corpo(med, k)
            topo_rodape = min((f.y for f in paginas.get(k, [])), default=self._pe(k))
            fatias_fim, fila_fim = self._encher_fim(fila_fim, topo_rodape - fim_corpo, sep, False)
            if fatias_fim:
                self._posicionar(fatias_fim, fim_corpo)
                paginas.setdefault(k, []).extend(fatias_fim)
            continuar_fim = bool(fatias_fim)
        extras = 0
        while (pendentes or fila_fim) and extras < MAX_EXTRAS:
            n = qt_paginas + extras
            topo, pe = self._topo(n), self._pe(n)
            util = pe - topo
            fatias, pendentes = self._encher(pendentes, [], util, sep)
            usado = sum(f.altura for f in fatias)
            if fatias:
                self._posicionar(fatias, pe - usado)
            fatias_fim = []
            if fila_fim:
                fatias_fim, fila_fim = self._encher_fim(fila_fim, util - usado, sep, continuar_fim)
                if fatias_fim:
                    continuar_fim = True
                    self._posicionar(fatias_fim, topo)
            if not fatias and not fatias_fim:
                break  # nada coube nem numa pagina vazia: para (nao gera paginas sem fim)
            paginas[n] = fatias + fatias_fim
            extras += 1
        self.paginas = paginas
        self.extras = extras

    @staticmethod
    def _posicionar(fatias: list[Fatia], topo: float) -> None:
        y = topo
        for f in fatias:
            f.y = y
            y += f.altura

    def _encher(self, pendentes: list, proprias: list, espaco: float, sep: float):
        """Fatias de notas de rodape que cabem em `espaco` (a continuacao primeiro). Devolve
        (fatias, o que continua: [(NotaQt, y0)])."""
        fatias: list[Fatia] = []
        livre = espaco
        fila = list(pendentes)
        if fila:
            d, y0 = fila[0]
            if livre - sep >= d.corte_ate(y0, livre - sep) - y0 > FOLGA:
                fatias.append(Fatia("continuacao", 0, sep))
                livre -= sep
                fila, livre = self._colocar(fila, livre, fatias, "rodape")
            if fila:
                return fatias, fila + [(d, 0.0) for d in proprias]
        if proprias:
            if livre >= sep + proprias[0].primeira_linha() - FOLGA:
                fatias.append(Fatia("separador", 0, sep))
                livre -= sep
                fila, livre = self._colocar([(d, 0.0) for d in proprias], livre, fatias, "rodape")
                return fatias, fila
            return fatias, [(d, 0.0) for d in proprias]
        return fatias, []

    def _colocar(self, fila: list, livre: float, fatias: list, classe: str):
        while fila:
            d, y0 = fila[0]
            altura = d.altura()
            if altura - y0 <= livre + FOLGA:
                fatias.append(Fatia("nota", 0, altura - y0, d, y0, altura, classe))
                livre -= altura - y0
                fila = fila[1:]
                continue
            corte = d.corte_ate(y0, livre)
            if corte > y0 + FOLGA:
                fatias.append(Fatia("nota", 0, corte - y0, d, y0, corte, classe))
                livre -= corte - y0
                fila = [(d, corte)] + fila[1:]
            break
        return fila, livre

    def _encher_fim(self, fila: list, espaco: float, sep: float, continuacao: bool):
        fatias: list[Fatia] = []
        if not fila:
            return fatias, fila
        d, y0 = fila[0]
        if espaco - sep < d.corte_ate(y0, max(espaco - sep, 0)) - y0 or \
                d.corte_ate(y0, max(espaco - sep, 0)) <= y0 + FOLGA:
            return fatias, fila
        fatias.append(Fatia("continuacao" if continuacao else "separador", 0, sep, classe="fim"))
        fila, _livre = self._colocar(fila, espaco - sep, fatias, "fim")
        return fatias, fila

    # -- consulta ------------------------------------------------------------------------
    def topo_da_area(self, n: int) -> float | None:
        """Topo (coordenadas do corpo) da area de notas de rodape da pagina n, ou None."""
        fatias = [f for f in self.paginas.get(n, []) if f.classe == "rodape"]
        return min((f.y for f in fatias), default=None)

    def fatias_de(self, nota: NotaQt) -> list[tuple[int, Fatia]]:
        return [(n, f) for n, fs in sorted(self.paginas.items()) for f in fs if f.nota is nota]

    def nota_em(self, n: int, x: float, y_doc: float):
        """(NotaQt, posicao) sob o ponto (x no corpo, y em coordenadas do corpo) da pagina n."""
        x -= self._desvio(n)
        for f in self.paginas.get(n, []):
            if f.nota is None or not (f.y - FOLGA <= y_doc <= f.y + f.altura + FOLGA):
                continue
            dl = f.nota.doc.documentLayout()
            pos = dl.hitTest(QPointF(x, f.y0 + (y_doc - f.y)), Qt.HitTestAccuracy.FuzzyHit)
            return f.nota, min(max(pos, 0), f.nota.doc.characterCount() - 1)
        return None

    def na_area(self, n: int, y_doc: float) -> bool:
        fatias = self.paginas.get(n, [])
        if not fatias:
            return False
        return min(f.y for f in fatias) - FOLGA <= y_doc <= max(f.y + f.altura for f in fatias)

    def _desvio(self, n: int) -> float:
        """O deslocamento do recuo negativo (0.1.27): as notas ficam na coluna do arquivo, o x 0
        do corpo fica `desvio` antes dela."""
        return float(self.layout.efetiva_da(self.layout.mapa.folha_da_pagina(n)).desvio_tw)

    def caret(self, nota: NotaQt, pos: int):
        """(folha, QRectF em coordenadas do documento) do caret na nota, ou None. Com colunas
        (passo 2), o y fica na faixa da coluna (`doc_para_tela` acha a coluna)."""
        from editdoc.interface.layout_paginado import retangulo_cursor_em
        r = retangulo_cursor_em(nota.doc, pos)
        achados = self.fatias_de(nota)
        for n, f in achados:
            if f.y0 - FOLGA <= r.top() < f.y1 - FOLGA or (f is achados[-1][1]):
                return self.layout.mapa.folha_da_pagina(n), QRectF(
                    r.x() + self._desvio(n), f.y + (r.top() - f.y0), r.width(), r.height())
        return None


# -- pintura ----------------------------------------------------------------------------------

PALETA = None


def _paleta():
    global PALETA
    if PALETA is None:
        from PySide6.QtGui import QPalette
        PALETA = QPalette()
        PALETA.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
        PALETA.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
        PALETA.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 215))
    return PALETA


def fechar_linhas_empurradas(painter, doc, recorte) -> None:
    """A linha de tabela com acolchoamento a mais (0.1.12, a seguinte desceu de pagina numa
    secao mais baixa) termina, na folha, onde o texto dela termina: o acolchoamento e' coberto
    de branco e ganha a borda de baixo, como o Word desenha a tabela partida. Coordenadas do
    documento, no pintor ja' transformado e recortado no corpo da folha."""
    if not getattr(doc, "_tem_linhas_empurradas", True):
        return
    from PySide6.QtGui import QTextTable
    from editdoc.ponte_qt.para_qt import bordas_da_tabela_em
    from editdoc.modelo.unidades import px_de_oitavos_pt
    dl = doc.documentLayout()
    achou = False
    it = doc.rootFrame().begin()
    while not it.atEnd():
        tabela = it.currentFrame()
        it += 1
        if not isinstance(tabela, QTextTable):
            continue
        quadro = dl.frameBoundingRect(tabela)
        if recorte is not None and not quadro.intersects(recorte):
            continue
        for r in range(tabela.rows() - 1):
            cel = tabela.cellAt(r, 0)
            valor = cel.format().property(pq.PROP_LINHA_EMPURRADA)
            if not (isinstance(valor, str) and ";" in valor):
                continue
            achou = True
            try:
                original = float(valor.split(";")[0]) * 15.0
            except ValueError:
                continue
            # A base natural da linha: o fim do texto das celulas mais o acolchoamento de antes.
            base, esquerda, direita = 0.0, math.inf, -math.inf
            for c in range(tabela.columns()):
                celula = tabela.cellAt(r, c)
                if celula.row() != r or celula.column() != c:
                    continue
                fmt = celula.format().toTableCellFormat()
                fim = dl.blockBoundingRect(celula.lastCursorPosition().block())
                ini = dl.blockBoundingRect(celula.firstCursorPosition().block())
                base = max(base, fim.bottom() + original)
                esquerda = min(esquerda, ini.left() - fmt.leftPadding() * 15.0)
                direita = max(direita, ini.right() + fmt.rightPadding() * 15.0)
            if base <= 0 or esquerda > direita:
                continue
            borda = bordas_da_tabela_em(tabela.format()).horizontal
            largura = px_de_oitavos_pt(borda.oitavos_pt) * 15.0 if borda is not None else 10.0
            painter.fillRect(QRectF(esquerda - largura, base + largura / 2,
                                    direita - esquerda + 2 * largura, quadro.bottom() - base),
                             QColor(255, 255, 255))
            quadro = QRectF(esquerda, quadro.top(), direita - esquerda, quadro.height())
            if borda is not None and borda.estilo != "nenhuma":
                caneta = QPen(QColor("#" + borda.cor_hex) if borda.cor_hex else QColor(0, 0, 0))
                caneta.setWidthF(largura)
                painter.setPen(caneta)
                painter.drawLine(QPointF(quadro.left(), base), QPointF(quadro.right(), base))
    if not achou:
        try:
            doc._tem_linhas_empurradas = bool(getattr(doc, "_secoes", None))
        except AttributeError:
            pass


def desenhar_notas(painter, layout, n: int, transf, editada: NotaQt | None = None,
                   selecao: QTextCursor | None = None, tela: bool = False) -> None:
    """Pinta a area de notas da folha n (separadores e trechos). Mesma funcao para a tela, o
    PDF e a impressao. `editada`/`selecao`: a nota em edicao recebe a selecao (so' na tela).

    Colunas (passo 2): o plano das notas e' por pagina do Qt (a coluna, como o Word poe a nota
    no pe' da coluna da referencia); a folha pinta a area de cada coluna no lugar dela."""
    if layout.mapa.tem_colunas():
        for p, dx, largura_col in layout.mapa.colunas_da_folha(n):
            _desenhar_notas_da_pagina(painter, layout, n, p, dx, largura_col, transf, editada,
                                      selecao)
        return
    _desenhar_notas_da_pagina(painter, layout, n, n, 0.0, None, transf, editada, selecao)


def _desenhar_notas_da_pagina(painter, layout, n: int, p: int, dx: float, largura_col,
                              transf, editada, selecao) -> None:
    fatias = layout.notas.paginas.get(p)
    if not fatias:
        return
    ef = layout.efetiva_da(n)
    # 0.1.27: a area de notas fica na coluna do arquivo (sem o deslocamento do recuo negativo).
    largura = float(ef.corpo_largura_tw() - ef.desvio_tw) if largura_col is None \
        else float(largura_col)
    margem = float(ef.margem_esq_tw + ef.desvio_tw) + dx
    painter.save()
    painter.setWorldTransform(transf)
    painter.translate(margem, ef.margem_sup_tw - layout.mapa.topo(p))
    for f in fatias:
        if f.tipo in ("separador", "continuacao"):
            comprimento = largura if f.tipo == "continuacao" else min(LARGURA_SEPARADOR_TW,
                                                                     largura / 3.0)
            caneta = QPen(QColor(0, 0, 0))
            caneta.setWidthF(ESPESSURA_SEPARADOR_TW)
            painter.setPen(caneta)
            meio = f.y + f.altura / 2.0
            painter.drawLine(QPointF(0, meio), QPointF(comprimento, meio))
            continue
        nota = f.nota
        painter.save()
        painter.translate(0, f.y - f.y0)
        painter.setClipRect(QRectF(-margem, f.y0, float(ef.largura_tw), f.y1 - f.y0))
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette = _paleta()
        ctx.cursorPosition = -1
        ctx.clip = QRectF(-margem, f.y0, float(ef.largura_tw), f.y1 - f.y0)
        if nota is editada and selecao is not None and selecao.hasSelection():
            sel = QAbstractTextDocumentLayout.Selection()
            sel.cursor = QTextCursor(selecao)
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(0, 120, 215))
            sel.format = fmt
            ctx.selections = [sel]
        nota.doc.documentLayout().draw(painter, ctx)
        from editdoc.ponte_qt import listas as pq_listas
        from editdoc.ponte_qt import propriedades as pq_props
        pq_listas.desenhar_rotulos(painter, nota.doc, ctx.clip)
        pq_props.desenhar(painter, nota.doc, ctx.clip)
        painter.restore()
    painter.restore()
