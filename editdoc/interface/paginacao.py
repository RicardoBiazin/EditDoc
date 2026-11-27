"""Paginacao como a do Word na tela (0.1.17): compensacao do layout e regras de quebra.

O `QTextDocumentLayout` do Qt 6.11 pagina de outro jeito que o Word (docs/SPIKES.md "0.1.17",
medido contra os `w:lastRenderedPageBreak` que o Word grava). Este plano mantem em dia, no formato
dos blocos e das tabelas do corpo, o que faz o Qt chegar ao layout do Word:

1. Compensacao (`compensar`), bloco a bloco, so' o trecho editado (e os vizinhos):
   - entrelinha com a razao Word/Qt da fonte (o espaco externo que o Word soma);
   - espaco entre paragrafos somado (o Qt usa o maior), com o `contextualSpacing`; o espaco
     antes do paragrafo depois de uma quebra do usuario fica; depois de uma quebra das regras
     (natural), sai, como no Word;
   - o paragrafo vazio logo DEPOIS de uma tabela, que o Qt esconde (`isEmptyBlockAfterTable`): a
     altura dele vai para o espaco antes do seguinte (ou para a margem de cima da tabela
     seguinte); o vazio logo ANTES de uma tabela ganha um fundo transparente (o Qt so' esconde
     o que nao tem fundo);
   - o espaco depois do paragrafo antes de uma tabela e o espaco antes do paragrafo depois dela,
     que o Qt ignora, vao para as margens do quadro da tabela.
2. Regras (`regras`), pagina a pagina a partir da pagina editada, ate' a pagina comecar onde
   comecava no plano anterior: controle de linhas viuvas e orfas (ligado por padrao), manter
   linhas juntas, manter com o proximo e quebra antes do estilo. O paragrafo que tem de descer
   ganha a quebra das regras (PROP_QUEBRA_REGRA); a que deixou de ser precisa sai.
3. Altura da linha de tabela (0.1.26, `_alturas_das_linhas`, parte "altura"): o w:trHeight
   (atLeast; exact quando o conteudo cabe; auto nao conta) vai no acolchoamento das celulas, sobre
   o do arquivo, num passo depois dos formatos, porque depende do layout delas.
4. Linha que nao se parte (0.1.32, w:cantSplit, parte "inteira", dentro das regras): a linha que
   o Qt partiria entre paginas desce inteira, com o arranjo que o proprio Qt usa quando nenhuma
   celula cabe (a linha de cima vai ate' o pe' da pagina): o empurrao no acolchoamento de baixo
   da linha de cima (`_linha_inteira`); a primeira linha, a do cabecalho repetido e a primeira
   depois dele levam a tabela inteira (a quebra das regras no quadro). Mais alta que a pagina:
   parte, como no Word.

Os ajustes entram no desfazer como os das secoes e das notas: um passo anotado depois do passo
do usuario (`ConjuntoDeNotas.ajustar`). Nada disso muda o arquivo gravado: o `de_qt` le' os
valores de verdade (`ponte_qt/paginacao.py`).

Limites (docs/ARQUITETURA.md): a viuva de um paragrafo com tres linhas ou mais na pagina de cima
pediria descer UMA linha, o que o layout do Qt nao faz (fica como esta'; na 0.1.26 o prototipo
pelo espaco antes nao mudou nenhuma quebra do oraculo); o espaco antes do primeiro paragrafo de
uma celula e o depois do ultimo (o Qt os ignora; medido na 0.1.26, somar piora o oraculo) e a
linha exata mais baixa que o conteudo (o Qt nao corta) nao entram; o Qt reserva no pe' (e no
alto) de cada pagina de uma tabela a margem de CIMA do quadro, o espaco depois do paragrafo de
cima (0.1.32, docs/SPIKES.md): a linha que cabe no Word pode partir no Qt; cabecalho, rodape e notas nao sao compensados (so' a altura da
faixa soma o vazio escondido logo depois da tabela, 0.1.27: `cabecalhos.FaixaQt.escondida`).
"""

from __future__ import annotations


from PySide6.QtGui import (QTextBlockFormat, QTextCharFormat, QTextCursor, QTextFormat,
                           QTextTable, QTextTableCell)

from editdoc import log_interno
from editdoc.modelo import paginacao as mod
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import notas as pq_notas
from editdoc.ponte_qt import paginacao as pq
from editdoc.ponte_qt import propriedades as pq_props
from editdoc.ponte_qt import secoes as pq_secoes
from editdoc.ponte_qt.para_qt import (PROP_CELULA, PROP_ESTRUTURAL, acolchoamento_base,
                                     ler_json)

log = log_interno.obter(__name__)

_DEPOIS = QTextFormat.PageBreakFlag.PageBreak_AlwaysAfter
#: Contra laco sem fim: quebras das regras que mudam por conferencia, e por bloco.
MAX_MUDANCAS = 64
MAX_POR_BLOCO = 3
#: Folga de arredondamento entre o simulado e o layout do Qt (twips).
FOLGA = 0.5
#: Histerese da quebra do motivo 3 (0.1.18): a quebra so' sai com esta folga (twips) sobrando no
#: pe' da pagina de cima. Zero volta ao comportamento da 0.1.17 (contraprova do teste).
HISTERESE_TW = 720.0
#: 0.1.32 (cantSplit): a quebra antes da tabela, posta para a primeira linha (ou o cabecalho)
#: descer inteira, so' sai se a linha couber com esta folga (twips) sem ela.
HISTERESE_LINHA_TW = 60.0


def _inteiro(flags) -> int:
    try:
        return int(flags.value)
    except AttributeError:
        return int(flags)


class _Unidade:
    """Bloco ou tabela do primeiro nivel do corpo, com a pagina de cada linha."""
    __slots__ = ("bloco", "tabela", "paginas", "topo")

    def __init__(self, bloco=None, tabela=None, paginas=(), topo=0.0) -> None:
        self.bloco = bloco
        self.tabela = tabela
        self.paginas = list(paginas)
        self.topo = topo

    def chave(self):
        return ("t", self.tabela.firstPosition()) if self.tabela is not None \
            else ("b", self.bloco.blockNumber())


class ConjuntoDePaginacao:
    """A compensacao e as regras de quebra do corpo do `LayoutPaginado`."""

    #: As partes (os testes e a medicao ligam uma de cada vez): entrelinha da fonte, espaco
    #: somado entre paragrafos, vazio e espacos junto da tabela, regras de quebra.
    PARTES = frozenset({"linha", "espaco", "tabela", "regras", "topo", "altura", "inteira"})

    def __init__(self, layout) -> None:
        self.layout = layout
        #: desligar (contraprova dos testes): nada e' compensado nem empurrado
        self.ligado = True
        self.partes = set(type(self).PARTES)
        self._sujo: list[int] | None = None
        self._desde: int | None = None
        self._aplicando = False
        self._chave: tuple | None = None
        self._regras: mod.RegrasDePaginacao | None = None
        #: inicio de cada pagina no ultimo plano das regras (para parar cedo)
        self._inicios: dict[int, tuple] = {}
        self._geo: tuple | None = None
        #: JSON da celula -> a linha tem w:cantSplit (0.1.32)
        self._cant: dict[str, bool] = {}
        #: contagens (os testes olham)
        self.ajustes = 0
        self.conferidas = 0
        layout.doc.contentsChange.connect(self._mudou)

    # -- estado ---------------------------------------------------------------------------------
    def _mudou(self, pos: int, removidos: int, adicionados: int) -> None:
        if self._aplicando:
            return
        fim = pos + max(adicionados, 1)
        if self._sujo is None:
            self._sujo = [pos, fim]
        else:
            self._sujo = [min(self._sujo[0], pos), max(self._sujo[1], fim)]
        self._desde = pos if self._desde is None else min(self._desde, pos)

    def _regras_do_catalogo(self) -> mod.RegrasDePaginacao:
        estilos = pq_estilos.catalogo(self.layout.doc)
        if self._regras is None or self._regras.estilos is not estilos:
            self._regras = mod.RegrasDePaginacao(estilos)
        return self._regras

    def _flag(self, fmt, nome: str) -> bool:
        return self._regras_do_catalogo().flag(pq_estilos.estilo_do_bloco(fmt),
                                               pq_props.extras_de_ppr(fmt), nome)

    def _aplicar(self, mudancas: list) -> None:
        """Grava os formatos novos num passo anotado do desfazer."""
        def aplicar(_c) -> None:
            for alvo, fmt in mudancas:
                if isinstance(alvo, (QTextTable, QTextTableCell)):
                    alvo.setFormat(fmt)
                else:
                    QTextCursor(alvo).setBlockFormat(fmt)
        self._aplicando = True
        try:
            self.layout.notas.ajustar(aplicar)
        finally:
            self._aplicando = False
        self.ajustes += 1

    # -- vizinhos ---------------------------------------------------------------------------------
    @staticmethod
    def _conteiner(bloco):
        cur = QTextCursor(bloco)
        tabela = cur.currentTable()
        if tabela is None:
            quadro = cur.currentFrame()
            return ("q", quadro.firstPosition() if quadro is not None else 0)
        cel = tabela.cellAt(cur)
        return ("c", tabela.firstPosition(), cel.row(), cel.column())

    def _irmao(self, bloco, passo: int):
        outro = bloco.previous() if passo < 0 else bloco.next()
        if not outro.isValid() or self._conteiner(outro) != self._conteiner(bloco):
            return None
        return outro

    @staticmethod
    def _estrutural(fmt) -> bool:
        return bool(fmt.property(PROP_ESTRUTURAL))

    def _tabela_antes(self, bloco):
        """A tabela que termina logo antes do bloco, no mesmo conteiner, ou None."""
        if bloco.position() == 0:
            return None
        cur = QTextCursor(self.layout.doc)
        cur.setPosition(bloco.position() - 1)
        tabela = cur.currentTable()
        if tabela is None or tabela.lastPosition() != bloco.position() - 1:
            return None
        while tabela is not None:
            pai = tabela.parentFrame()
            if pai is not None and QTextCursor(bloco).currentFrame() == pai:
                return tabela
            tabela = pai if isinstance(pai, QTextTable) else None
        return None

    def _tabela_depois(self, bloco):
        """A tabela que comeca logo depois do bloco, no mesmo conteiner, ou None."""
        doc = self.layout.doc
        pos = bloco.position() + bloco.length()
        if pos >= doc.characterCount():
            return None
        cur = QTextCursor(doc)
        cur.setPosition(pos)
        tabela = cur.currentTable()
        while tabela is not None:
            if tabela.firstPosition() == pos and \
                    tabela.parentFrame() == QTextCursor(bloco).currentFrame():
                return tabela
            pai = tabela.parentFrame()
            tabela = pai if isinstance(pai, QTextTable) else None
        return None

    def _escondido_depois_de_tabela(self, bloco) -> bool:
        """Paragrafo do modelo, vazio, logo depois de uma tabela: o Qt nao lhe da' altura."""
        return bloco.length() == 1 and not self._estrutural(bloco.blockFormat()) and \
            self._tabela_antes(bloco) is not None

    # -- compensacao --------------------------------------------------------------------------------
    def _altura_word(self, bloco, fmt) -> float:
        """Altura (twips) da linha do paragrafo vazio com a entrelinha do formato `fmt`."""
        return pq.altura_do_vazio(bloco, fmt)

    def _entre(self, a, fa, b, fb) -> float:
        """O espaco do Word entre os irmaos a e b (px96), pelos valores de verdade."""
        mesmo = pq_estilos.estilo_do_bloco(fa) == pq_estilos.estilo_do_bloco(fb)
        quebra = self._quebra_do_usuario(fb) or bool(_inteiro(fa.pageBreakPolicy())
                                                     & _inteiro(_DEPOIS))
        return mod.espaco_entre(pq.depois_real(fa) or 0.0, pq.antes_real(fb) or 0.0, mesmo,
                                mesmo and self._flag(fa, "contextualSpacing"),
                                mesmo and self._flag(fb, "contextualSpacing"), quebra)

    @staticmethod
    def _quebra_do_usuario(fmt) -> bool:
        return pq.tem_quebra_antes(fmt) and not pq.eh_regra(fmt) and \
            not pq_notas.eh_espacador(fmt) and not pq_secoes.eh_derivada(fmt)

    def _antes_desejado(self, bloco, fmt, desejados: dict, sem_regra: bool = False) -> float:
        """O topMargin (px96) que faz o Qt dar o espaco do Word antes do bloco."""
        anterior = self._irmao(bloco, -1)
        antes = pq.antes_real(fmt)
        if anterior is None:
            return antes or 0.0
        fa = anterior.blockFormat()
        if self._estrutural(fa):
            return antes or 0.0
        if "espaco" not in self.partes:
            return antes or 0.0
        if not sem_regra and pq.eh_regra(fmt):
            # Pagina nova empurrada: no alto dela o Word poe so' o espaco antes do proprio
            # paragrafo (o depois do de cima ficou na pagina anterior). O bloco empurrado pelo
            # espacador das notas fica com o espaco somado: mudar o topo dele mudaria a conta
            # das notas, que o soltaria, e o ajuste oscilaria a cada tecla (medido na secao
            # paisagem do teste_secoes: 254 ajustes em 80 teclas).
            return antes or 0.0
        espaco = self._entre(anterior, fa, bloco, fmt)
        if "tabela" in self.partes and self._escondido_depois_de_tabela(anterior):
            fa_novo = desejados.get(anterior.blockNumber(), fa)
            espaco += (pq.antes_real(fa) or 0.0) + self._altura_word(anterior, fa_novo) / 15.0
        return espaco

    def _formato_desejado(self, bloco, desejados: dict) -> QTextBlockFormat:
        bf = bloco.blockFormat()
        novo = QTextBlockFormat(bf)
        if self._estrutural(bf):
            return novo
        doc = self.layout.doc
        familia, pontos = pq.fonte_do_bloco(bloco, doc.defaultFont())
        disp = self.layout._dispositivo
        fator = pq.fator_da_familia(familia, disp) if "linha" in self.partes else 1.0
        linha_qt = None
        if "linha" in self.partes:
            altura = pq.altura_qt(familia, pontos, disp)
            if pq.objeto_alto(bloco, altura):
                linha_qt = altura
        pq.definir_linha(novo, pq.linha_real(bf), fator, linha_qt)
        desejados[bloco.blockNumber()] = novo
        pq.definir_antes(novo, pq.antes_real(bf), self._antes_desejado(bloco, bf, desejados))
        seguinte = self._irmao(bloco, 1)
        depois = pq.depois_real(bf)
        pq.definir_depois(novo, depois, 0.0 if seguinte is not None and "espaco" in self.partes
                          else (depois or 0.0))
        vazio_antes = "tabela" in self.partes and bloco.length() == 1 and \
            self._tabela_depois(bloco) is not None
        pq.definir_visivel(novo, vazio_antes)
        return novo

    def _margens_da_tabela(self, tabela) -> tuple[float, float]:
        """(margem de cima, de baixo) do quadro, px96: o espaco depois do paragrafo de cima e o
        antes do de baixo (o Qt os ignora junto de uma tabela).

        Limite medido na 0.1.27 (docs/SPIKES.md): a linha do vazio entre duas tabelas sai com a
        entrelinha ainda sem a compensacao (no doc_12, 369 twips em vez de 379,9). Usar o formato
        compensado nao mudou nenhuma quebra dos 14 arquivos medidos; nao entrou."""
        doc = self.layout.doc
        topo = 0.0
        if "tabela" not in self.partes:
            return 0.0, 0.0
        if tabela.firstPosition() > 1:
            a = doc.findBlock(tabela.firstPosition() - 1)
            fa = a.blockFormat()
            if a.isValid() and not self._estrutural(fa):
                if self._escondido_depois_de_tabela(a):
                    topo = (pq.antes_real(fa) or 0.0) + (pq.depois_real(fa) or 0.0) + \
                        self._altura_word(a, fa) / 15.0
                else:
                    topo = pq.depois_real(fa) or 0.0
        base = 0.0
        b = doc.findBlock(tabela.lastPosition() + 1)
        if b.isValid() and b.length() > 1 and not self._estrutural(b.blockFormat()):
            base = pq.antes_real(b.blockFormat()) or 0.0
        return topo, base

    def compensar(self, forcar: bool = False) -> bool:
        """Formatos compensados em dia. True se algum mudou (o layout muda)."""
        if not self.ligado:
            return self._desligar()
        doc = self.layout.doc
        chave = (pq_estilos.assinatura(doc), doc.defaultFont().key(), id(self.layout._dispositivo))
        if chave != self._chave:
            forcar = True
            self._chave = chave
            self._regras = None
        sujo, self._sujo = self._sujo, None
        if not forcar and sujo is None:
            return False
        try:
            return self._compensar(sujo if not forcar else None)
        except Exception:  # noqa: BLE001 - a compensacao nao pode derrubar a pintura
            log.exception("compensacao da paginacao")
            return False

    def _compensar(self, sujo) -> bool:
        doc = self.layout.doc
        if sujo is None:
            primeiro, ultimo = doc.begin(), doc.lastBlock()
        else:
            primeiro = doc.findBlock(max(0, sujo[0]))
            ultimo = doc.findBlock(min(sujo[1], doc.characterCount() - 1))
            for _ in range(2):
                if primeiro.previous().isValid():
                    primeiro = primeiro.previous()
                if ultimo.next().isValid():
                    ultimo = ultimo.next()
        desejados: dict = {}
        mudancas = []
        tabelas = {}
        bloco = primeiro
        while bloco.isValid():
            novo = self._formato_desejado(bloco, desejados)
            if novo != bloco.blockFormat():
                mudancas.append((bloco, novo))
            for t in (self._tabela_antes(bloco), self._tabela_depois(bloco)):
                if t is not None:
                    tabelas[t.firstPosition()] = t
            if bloco == ultimo:
                break
            bloco = bloco.next()
        for tabela in tabelas.values():
            fmt = tabela.format()
            topo, base = self._margens_da_tabela(tabela)
            novo = type(fmt)(fmt)
            pq.definir_margens_da_tabela(novo, topo, base)
            if novo != fmt:
                mudancas.append((tabela, novo))
        if mudancas:
            self._aplicar(mudancas)
        # A altura da linha (0.1.26) depende do layout das celulas com os formatos de agora: vem
        # depois, num passo a parte so' quando muda (raro: a tabela com w:trHeight editada).
        if sujo is None:
            faixa = None
        else:
            faixa = (primeiro.position(), ultimo.position() + ultimo.length())
        alturas = self._alturas_das_linhas(faixa)
        if alturas:
            self._aplicar(alturas)
        return bool(mudancas or alturas)

    # -- altura da linha de tabela (0.1.26) ------------------------------------------------------
    def _alturas_das_linhas(self, faixa) -> list:
        """O w:trHeight das linhas (atLeast; exact quando o conteudo cabe) no acolchoamento das
        celulas: o Qt nao tem altura de linha. Cada celula de uma linha so' (sem mescla vertical)
        ganha o que falta para a linha ter a altura do arquivo, embaixo (no meio: metade em cima;
        alinhada embaixo: em cima), sobre o acolchoamento do arquivo (`acolchoamento_base`). A
        linha sem altura volta ao acolchoamento do arquivo. `faixa` (posicoes): so' as linhas que a
        edicao tocou; None = todas."""
        doc = self.layout.doc
        mudancas = []
        for tabela in _tabelas(doc.rootFrame(), faixa):
            linhas = range(tabela.rows())
            if faixa is not None:
                # so' as linhas da faixa (a tecla numa tabela grande nao passa por todas)
                de = tabela.cellAt(max(faixa[0], tabela.firstPosition()))
                ate = tabela.cellAt(min(faixa[1], tabela.lastPosition()))
                if de.isValid() and ate.isValid():
                    linhas = range(de.row(), ate.row() + ate.rowSpan())
            for r in linhas:
                cels = _celulas_da_linha(tabela, r)
                if not cels:
                    continue
                if faixa is not None and (cels[-1].lastPosition() < faixa[0]
                                          or cels[0].firstPosition() > faixa[1]):
                    continue
                mudancas += self._acolchoar_linha(tabela, cels)
        return mudancas

    def _acolchoar_linha(self, tabela, cels, extra: float | None = None) -> list:
        """O acolchoamento das celulas `cels` (as que comecam numa linha): o do arquivo, mais o
        que falta para o w:trHeight, mais o empurrao da linha de baixo que nao se parte
        (`extra`, px96, embaixo; None = o que as celulas ja' tem em PROP_WORD_INTEIRA)."""
        formatos = [c.format() for c in cels]
        if any(f.hasProperty(pq_notas.PROP_LINHA_EMPURRADA) for f in formatos):
            return []  # a linha empurrada da secao (0.1.12) cuida do acolchoamento
        if extra is None:
            extra = max((pq.empurrao(f) for f in formatos), default=0.0)
        if "inteira" not in self.partes:
            extra = 0.0
        dado = ler_json(formatos[0], PROP_CELULA)
        alvo = dado.get("altura_tw")
        if not isinstance(alvo, (int, float)) or dado.get("altura_auto") or \
                "altura" not in self.partes:
            alvo = None
            if extra <= pq.FOLGA and \
                    not any(f.hasProperty(pq.PROP_WORD_ALTURA) for f in formatos):
                return []  # sem altura e sem acrescimo: nada a fazer (o caso comum)
        mudancas = []
        for cel in cels:
            fmt = cel.format().toTableCellFormat()
            base = acolchoamento_base(tabela, fmt)
            cima, baixo = base[0], base[2]
            if alvo is not None and cel.rowSpan() == 1:
                natural = self._altura_da_celula(tabela, cel, fmt, cima, baixo)
                falta = (float(alvo) - natural) / 15.0 if natural is not None else 0.0
                if falta > pq.FOLGA:
                    va = fmt.verticalAlignment()
                    if va == QTextCharFormat.VerticalAlignment.AlignMiddle:
                        cima, baixo = cima + falta / 2.0, baixo + falta / 2.0
                    elif va == QTextCharFormat.VerticalAlignment.AlignBottom:
                        cima += falta
                    else:
                        baixo += falta
            # 0.1.32 (cantSplit): o empurrao vai embaixo de todas as celulas da linha (a altura
            # dela cresce dele; a alinhada no meio ou embaixo nao sai do lugar).
            proprio = extra if extra > pq.FOLGA and cel.rowSpan() == 1 else 0.0
            baixo += proprio
            acrescimo = abs(cima - base[0]) > pq.FOLGA or abs(baixo - base[2]) > pq.FOLGA
            if abs(fmt.topPadding() - cima) > pq.FOLGA or \
                    abs(fmt.bottomPadding() - baixo) > pq.FOLGA or \
                    fmt.hasProperty(pq.PROP_WORD_ALTURA) != acrescimo or \
                    abs(pq.empurrao(fmt) - proprio) > pq.FOLGA:
                fmt.setTopPadding(cima)
                fmt.setBottomPadding(baixo)
                if acrescimo:
                    fmt.setProperty(pq.PROP_WORD_ALTURA, True)
                else:
                    fmt.clearProperty(pq.PROP_WORD_ALTURA)
                pq.definir_empurrao(fmt, proprio)
                mudancas.append((cel, fmt))
        return mudancas

    def _altura_da_celula(self, tabela, cel, fmt, cima: float, baixo: float) -> float | None:
        """Altura natural (twips) da celula no Qt com o acolchoamento `cima`/`baixo` (px96): as
        linhas dos blocos (o avanco, como o Qt soma), o maior entre o espaco depois e o antes de
        dois blocos vizinhos e meia borda de cima e de baixo (borda colapsada). None se a celula
        tem tabela dentro ou bloco ainda sem layout (fica sem acrescimo)."""
        doc = self.layout.doc
        bloco = doc.findBlock(cel.firstPosition())
        fim = cel.lastPosition()
        total = 0.0
        anterior = None
        while bloco.isValid() and bloco.position() <= fim:
            dentro = QTextCursor(bloco).currentTable()
            if dentro is None or dentro.firstPosition() != tabela.firstPosition():
                return None
            if bloco.isVisible():
                lay = bloco.layout()
                if lay is None or lay.lineCount() == 0:
                    return None
                bf = bloco.blockFormat()
                if anterior is not None:
                    total += max(anterior.bottomMargin(), bf.topMargin()) * 15.0
                total += sum(pq.avanco_e_corte(bf, lay.lineAt(i))[0]
                             for i in range(lay.lineCount()))
                anterior = bf
            bloco = bloco.next()
        borda = (fmt.topBorder() + fmt.bottomBorder()) / 2.0
        return total + (cima + baixo + borda) * 15.0

    def _desligar(self) -> bool:
        """Contraprova: tira toda compensacao e quebra das regras."""
        doc = self.layout.doc
        mudancas = []
        bloco = doc.begin()
        while bloco.isValid():
            bf = bloco.blockFormat()
            if any(bf.hasProperty(p) for p in pq.PROPS_DE_PAGINACAO):
                mudancas.append((bloco, pq.sem_compensacao(bf)))
            bloco = bloco.next()
        for quadro in _tabelas(doc.rootFrame()):
            fmt = quadro.format()
            if fmt.hasProperty(pq.PROP_WORD_ANTES) or fmt.hasProperty(pq.PROP_WORD_DEPOIS) or \
                    pq.eh_regra(fmt):
                novo = pq.sem_compensacao(fmt)
                pq.definir_regra(novo, False)
                mudancas.append((quadro, novo))
        partes, self.partes = self.partes, set()
        try:
            mudancas += self._alturas_das_linhas(None)  # sem "altura": o acolchoamento do arquivo
        finally:
            self.partes = partes
        self._sujo = None
        self._desde = None
        if not mudancas:
            return False
        self._aplicar(mudancas)
        return True

    # -- regras de quebra ---------------------------------------------------------------------------
    def _unidade_de(self, bloco=None, tabela=None) -> _Unidade:
        dl = self.layout.doc.documentLayout()
        mapa = self.layout.mapa
        if tabela is not None:
            r = dl.frameBoundingRect(tabela)
            return _Unidade(tabela=tabela, paginas=[mapa.pagina_de_y(r.top() + 1),
                                                    mapa.pagina_de_y(r.bottom() - 1)],
                            topo=r.top())
        r = dl.blockBoundingRect(bloco)
        lay = bloco.layout()
        paginas = [mapa.pagina_de_y(r.top() + lay.lineAt(i).y() + 1)
                   for i in range(lay.lineCount())]
        return _Unidade(bloco=bloco, paginas=paginas, topo=r.top())

    def _unidades_desde(self, bloco):
        """Unidades do primeiro nivel a partir do bloco (que e' do primeiro nivel)."""
        doc = self.layout.doc
        raiz = doc.rootFrame()
        while bloco.isValid():
            cur = QTextCursor(bloco)
            quadro = cur.currentFrame()
            if quadro is not None and quadro != raiz:
                tabela = cur.currentTable()
                while tabela is not None and tabela.parentFrame() != raiz:
                    tabela = tabela.parentFrame()
                if isinstance(tabela, QTextTable):
                    yield self._unidade_de(tabela=tabela)
                    bloco = doc.findBlock(tabela.lastPosition() + 1)
                    continue
            if bloco.isVisible():
                u = self._unidade_de(bloco=bloco)
                if u.paginas:
                    yield u
            bloco = bloco.next()

    def _bloco_do_primeiro_nivel(self, pos: int):
        doc = self.layout.doc
        bloco = doc.findBlock(max(0, min(pos, doc.characterCount() - 1)))
        cur = QTextCursor(bloco)
        tabela = cur.currentTable()
        raiz = doc.rootFrame()
        while tabela is not None and tabela.parentFrame() != raiz:
            tabela = tabela.parentFrame()
        if isinstance(tabela, QTextTable):
            anterior = doc.findBlock(tabela.firstPosition() - 1)
            return anterior if anterior.isValid() else doc.begin()
        return bloco

    def regras(self, forcar: bool = False) -> bool:
        """Quebras das regras do Word em dia. True se alguma mudou (o layout muda)."""
        if not self.ligado or "regras" not in self.partes:
            return False
        doc = self.layout.doc
        geo = (self.layout.hb, doc.pageSize().width(), self.layout.geracao_das_secoes())
        if geo != self._geo:
            forcar = True
            self._geo = geo
        desde, self._desde = self._desde, None
        if not forcar and desde is None:
            return False
        try:
            return self._regras_desde(0 if forcar else desde, forcar)
        except Exception:  # noqa: BLE001 - as regras nao podem derrubar a pintura
            log.exception("regras de paginacao")
            return False

    def _inicio_da_pagina(self, pagina: int):
        """Um bloco do primeiro nivel na pagina `pagina` ou antes dela (de onde comecar)."""
        doc = self.layout.doc
        if pagina <= 0:
            return doc.begin()
        from PySide6.QtCore import QPointF, Qt
        pos = doc.documentLayout().hitTest(QPointF(1.0, self.layout.mapa.topo(pagina) + 1.0),
                                           Qt.HitTestAccuracy.FuzzyHit)
        if pos < 0:
            return doc.begin()
        bloco = self._bloco_do_primeiro_nivel(pos)
        # um passo para tras: a unidade que cruza a divisa comeca na pagina de cima
        anterior = bloco.previous()
        return self._bloco_do_primeiro_nivel(anterior.position()) if anterior.isValid() else bloco

    def _assinatura(self, u: _Unidade, k: int) -> tuple:
        """Como a pagina k comeca (na unidade u): estavel quando o texto de cima muda de bloco."""
        if u.tabela is not None:
            return ("t", round(u.topo - self.layout.mapa.topo(k), 1), u.tabela.rows())
        i = u.paginas.index(k) if k in u.paginas else 0
        linha = u.bloco.layout().lineAt(i)
        return ("b", u.bloco.length(), i, round(u.topo + linha.y() - self.layout.mapa.topo(k), 1))

    def _regras_desde(self, desde: int, forcar: bool) -> bool:
        doc = self.layout.doc
        mapa = self.layout.mapa
        if forcar:
            inicio = 0
            self._inicios = {}
        else:
            bloco = self._bloco_do_primeiro_nivel(desde)
            topo = doc.documentLayout().blockBoundingRect(bloco).top()
            inicio = max(0, mapa.pagina_de_y(topo) - 1)
        pagina_editada = inicio
        mudou_algo = False
        ultima_mudanca = -10
        tentativas: dict = {}
        mudancas = 0
        self.conferidas = 0
        reiniciar = True
        while reiniciar and mudancas < MAX_MUDANCAS:
            reiniciar = False
            anterior: _Unidade | None = None
            ultima_pagina: int | None = None
            for u in self._unidades_desde(self._inicio_da_pagina(inicio)):
                p0 = u.paginas[0]
                if ultima_pagina is None:
                    # a primeira unidade: a pagina dela comecou antes (ou e' a primeira)
                    ultima_pagina = p0 if p0 > 0 or anterior is not None else -1
                novas = range(max(ultima_pagina + 1, 0), u.paginas[-1] + 1) \
                    if u.tabela is None else range(max(ultima_pagina + 1, 0), p0 + 1)
                # A unidade e' avaliada ANTES de parar: o bloco empurrado que comeca a pagina
                # pode ter deixado de precisar da quebra (ou o de cima passou a precisar), e a
                # pagina comecaria igual a do plano anterior mesmo assim.
                if u.tabela is not None:
                    # 0.1.32: a linha que nao se parte (w:cantSplit) desce inteira
                    esgotadas = {c for c, n in tentativas.items() if n >= MAX_POR_BLOCO}
                    inteira = self._linha_inteira(u, anterior, esgotadas)
                    if inteira is not None:
                        chave, muds, pagina = inteira
                        tentativas[chave] = tentativas.get(chave, 0) + 1
                        self._aplicar(muds)
                        mudancas += 1
                        mudou_algo = True
                        ultima_mudanca = pagina + 1
                        inicio = max(0, pagina - 1)
                        reiniciar = True
                        break
                acao = self._avaliar(u, anterior)
                if acao is not None:
                    alvo, ligar, motivo = acao
                    n = alvo.blockNumber()
                    if tentativas.get(n, 0) < MAX_POR_BLOCO:
                        tentativas[n] = tentativas.get(n, 0) + 1
                        fmt_alvo = alvo.blockFormat()
                        fmt = QTextBlockFormat(fmt_alvo)
                        pq.definir_regra(fmt, ligar, motivo)
                        # no alto da pagina nova, so' o espaco antes do proprio paragrafo
                        pq.definir_antes(fmt, pq.antes_real(fmt_alvo),
                                         self._antes_desejado(alvo, fmt, {}))
                        pagina = self._unidade_de(bloco=alvo).paginas
                        self._aplicar([(alvo, fmt)])
                        mudancas += 1
                        mudou_algo = True
                        ultima_mudanca = (pagina[-1] if pagina else p0) + 1
                        inicio = max(0, (pagina[0] if pagina else p0) - 1)
                        reiniciar = True
                        break
                for k in novas:
                    sig = self._assinatura(u, k)
                    if not forcar and k > max(pagina_editada, ultima_mudanca) + 1 and \
                            self._inicios.get(k) == sig:
                        return mudou_algo
                    self._inicios[k] = sig
                    self.conferidas += 1
                anterior = u
                ultima_pagina = max(ultima_pagina, u.paginas[-1])
        return mudou_algo

    def _avaliar(self, u: _Unidade, anterior: _Unidade | None):
        """(bloco, ligar, motivo) se a quebra das regras de algum bloco tem de mudar, ou None.

        Motivos (o valor de PROP_QUEBRA_REGRA): 1 = viuvas e orfas, manter linhas juntas,
        manter com o proximo; 2 = quebra antes do estilo; 3 = o paragrafo comeca a pagina por
        nao caber e tem espaco antes (o Qt o perde no alto da pagina; o Word o mantem)."""
        if u.tabela is not None:
            return self._manter_com_proximo(u, anterior)
        fmt = u.bloco.blockFormat()
        if anterior is not None and anterior.bloco is not None and \
                pq_secoes.quebra_so_depois(anterior.bloco.blockFormat()):
            # 0.1.22: o paragrafo de cima termina a pagina (a quebra do usuario fica no fim dele).
            # Este bloco ja' comeca a pagina: uma quebra das regras aqui faria pagina em branco.
            if pq.eh_regra(fmt):
                return (u.bloco, False, fmt.property(pq.PROP_QUEBRA_REGRA))
            return None
        if pq.eh_regra(fmt):
            if fmt.property(pq.PROP_QUEBRA_REGRA) == 2:
                return None if self._flag(fmt, "pageBreakBefore") else (u.bloco, False, 2)
            # 0.1.18: a quebra do motivo 3 (o paragrafo comeca a pagina por nao caber) so' sai
            # com folga: sem ela, o bloco vai e volta a cada ajuste de pagina de cima.
            margem = HISTERESE_TW if fmt.property(pq.PROP_QUEBRA_REGRA) == 3 else 0.0
            if anterior is not None and not self._precisa(u, anterior, margem):
                return (u.bloco, False, 1)
            return None
        if pq.tem_quebra_antes(fmt) or self._estrutural(fmt):
            return None
        if anterior is not None and self._flag(fmt, "pageBreakBefore"):
            return (u.bloco, True, 2)
        primeiro = anterior is None or anterior.paginas[-1] < u.paginas[0]
        if len(u.paginas) > 1 and u.paginas[-1] != u.paginas[0]:
            a = u.paginas.count(u.paginas[0])
            b = len(u.paginas) - a
            if mod.deve_empurrar(a, b, self._flag(fmt, "widowControl"),
                                 self._flag(fmt, "keepLines"), primeiro):
                return (u.bloco, True, 1)
        acao = self._manter_com_proximo(u, anterior)
        if acao is not None:
            return acao
        # 0.1.18: liga so' se o bloco precisa descer (o mesmo criterio de `_precisa` que o desliga,
        # sem folga); desliga so' com a folga HISTERESE_TW. Entre as duas, a quebra fica como esta'.
        if "topo" in self.partes and anterior is not None and primeiro and \
                (pq.antes_real(fmt) or 0.0) > pq.FOLGA and \
                (HISTERESE_TW <= 0 or self._precisa(u, anterior)):
            return (u.bloco, True, 3)
        return None

    def _manter_com_proximo(self, u: _Unidade, anterior: _Unidade | None):
        """A unidade comeca uma pagina e o paragrafo de cima tem "manter com o proximo": a cadeia
        de "manter com o proximo" desce junto (se nao comecar ela mesma a pagina)."""
        if anterior is None or anterior.bloco is None or anterior.paginas[-1] >= u.paginas[0]:
            return None
        inicio = anterior
        if not self._flag(inicio.bloco.blockFormat(), "keepNext"):
            return None
        while True:
            if inicio.paginas[0] != inicio.paginas[-1]:
                return None  # o de cima esta' partido entre paginas: fica como esta'
            if pq.tem_quebra_antes(inicio.bloco.blockFormat()):
                return None  # a cadeia ja' comeca numa quebra
            prev = self._unidade_anterior(inicio.bloco)
            if prev is None or prev.paginas[-1] < inicio.paginas[0]:
                return None  # a cadeia comeca a pagina: nao cabe em pagina nenhuma
            if prev.bloco is not None and prev.paginas[-1] == inicio.paginas[0] and \
                    prev.paginas[0] == prev.paginas[-1] and \
                    self._flag(prev.bloco.blockFormat(), "keepNext"):
                inicio = prev
                continue
            return (inicio.bloco, True, 1)

    def _unidade_anterior(self, bloco) -> _Unidade | None:
        anterior = bloco.previous()
        if not anterior.isValid():
            return None
        cur = QTextCursor(anterior)
        tabela = cur.currentTable()
        raiz = self.layout.doc.rootFrame()
        while tabela is not None and tabela.parentFrame() != raiz:
            tabela = tabela.parentFrame()
        if isinstance(tabela, QTextTable):
            return self._unidade_de(tabela=tabela)
        if not anterior.isVisible():
            return None
        u = self._unidade_de(bloco=anterior)
        return u if u.paginas else None

    # -- linha que nao se parte (w:cantSplit, 0.1.32) --------------------------------------------
    def _linha_inteira(self, u: _Unidade, anterior: _Unidade | None, esgotadas=()):
        """(chave, mudancas, pagina) da primeira linha da tabela `u` cujo arranjo para o
        w:cantSplit tem de mudar, ou None.

        O Qt parte qualquer linha de tabela entre as linhas de texto, e so' leva a linha
        inteira para a pagina seguinte quando a primeira linha de texto de TODAS as celulas
        ja' nao cabe (`layoutTable`, `dropRowToNextPage`); nesse caso a linha de cima vai ate'
        o pe' da pagina. A linha que nao se parte ganha esse arranjo do proprio Qt: a linha de
        cima ganha no acolchoamento de baixo (`PROP_WORD_INTEIRA`) o que falta para a primeira
        linha de texto de cada celula de baixo passar do pe' da pagina. Linha do cabecalho
        repetido, ou a primeira depois dele (o Qt leva a tabela inteira), e a primeira linha da
        tabela: a quebra antes da tabela (a das regras, `PROP_QUEBRA_REGRA` 4). Linha mais alta
        que a pagina: parte, como no Word."""
        if "inteira" not in self.partes:
            return None
        tabela = u.tabela
        linhas = tabela.rows()
        cab = max(0, min(tabela.format().headerRowCount(), linhas - 1))
        chave = ("q", tabela.firstPosition())
        if chave not in esgotadas:
            muds = self._quebra_da_tabela(u, anterior, cab)
            if muds:
                return chave, muds, u.paginas[0]
        celulas = _LinhasDaTabela(tabela)
        # Por tecla, o caso comum (linha sem cantSplit e sem empurrao) olha so' a celula da
        # coluna 0: o JSON da linha esta' em todas, e o empurrao em todas as da linha de cima.
        fmt_ant = tabela.cellAt(cab, 0).format()
        for r in range(cab + 1, linhas):
            fmt = tabela.cellAt(r, 0).format()
            bruto = fmt.property(PROP_CELULA)
            cant = isinstance(bruto, str) and "cantSplit" in bruto
            empurrada = pq.empurrao(fmt_ant) > pq.FOLGA
            fmt_ant = fmt
            if not cant and not empurrada:
                continue
            chave = ("l", tabela.firstPosition(), r)
            if chave in esgotadas or not celulas[r] or not celulas[r - 1]:
                continue
            if not self._nao_partir(celulas[r]) and \
                    not any(pq.empurrao(c.format()) > pq.FOLGA for c in celulas[r - 1]):
                continue  # sem cantSplit e sem empurrao
            res = self._empurrao_desejado(tabela, r, celulas, cab)
            if res is None:
                continue
            alvo, pagina = res
            atual = max(pq.empurrao(c.format()) for c in celulas[r - 1])
            if abs(alvo - atual) <= pq.FOLGA:
                continue
            muds = self._acolchoar_linha(tabela, celulas[r - 1], alvo)
            if muds:
                return chave, muds, pagina
        return None

    def _nao_partir(self, cels) -> bool:
        bruto = cels[0].format().property(PROP_CELULA)
        if not isinstance(bruto, str) or "cantSplit" not in bruto:
            return False  # sem ler o JSON (o caso comum, a cada tecla)
        if bruto not in self._cant:
            if len(self._cant) > 4096:
                self._cant.clear()
            self._cant[bruto] = pq.nao_partir(ler_json(cels[0].format(), PROP_CELULA)
                                              .get("extras_linha"))
        return self._cant[bruto]

    @staticmethod
    def _simples(tabela, r: int) -> bool:
        """Nenhuma celula mesclada na vertical comeca, termina ou passa na linha r."""
        for c in range(tabela.columns()):
            cel = tabela.cellAt(r, c)
            if cel.rowSpan() != 1:
                return False
        return True

    def _linhas_de_texto(self, cel):
        """(primeiro bloco visivel da celula com linhas, ultimo), ou None."""
        doc = self.layout.doc
        bloco = doc.findBlock(cel.firstPosition())
        fim = cel.lastPosition()
        primeiro = ultimo = None
        while bloco.isValid() and bloco.position() <= fim:
            if bloco.isVisible() and bloco.layout() is not None and \
                    bloco.layout().lineCount() > 0:
                primeiro = primeiro or bloco
                ultimo = bloco
            bloco = bloco.next()
        return None if primeiro is None else (primeiro, ultimo)

    def _partida(self, cels) -> bool:
        """A linha (as celulas `cels`) tem texto em mais de uma pagina."""
        dl = self.layout.doc.documentLayout()
        mapa = self.layout.mapa
        paginas = set()
        for cel in cels:
            par = self._linhas_de_texto(cel)
            if par is None:
                continue
            a, b = par
            ra, rb = dl.blockBoundingRect(a), dl.blockBoundingRect(b)
            lb = b.layout()
            if a.layout().lineCount() == 0 or lb.lineCount() == 0:
                continue  # bloco sem linhas (lineAt de indice invalido derruba o processo)
            paginas.add(mapa.pagina_de_y(ra.top() + a.layout().lineAt(0).y() + 1))
            paginas.add(mapa.pagina_de_y(rb.top() + lb.lineAt(lb.lineCount() - 1).y() + 1))
            if len(paginas) > 1:
                return True
        return False

    def _topo_da_linha(self, cels) -> float | None:
        """Y (twips) do alto da linha: o do primeiro bloco de cada celula menos o acolchoamento
        de cima e meia borda (a celula mais alta da linha nao tem deslocamento vertical)."""
        dl = self.layout.doc.documentLayout()
        topo = None
        for cel in cels:
            par = self._linhas_de_texto(cel)
            if par is None:
                continue
            fmt = cel.format().toTableCellFormat()
            y = dl.blockBoundingRect(par[0]).top() - \
                (fmt.topPadding() + fmt.topBorder() / 2.0) * 15.0
            topo = y if topo is None else min(topo, y)
        return topo

    def _altura_natural(self, tabela, cels) -> float | None:
        """Altura (twips) da linha sem o empurrao para a de baixo (com o do w:trHeight)."""
        maior = 0.0
        for cel in cels:
            fmt = cel.format().toTableCellFormat()
            h = self._altura_da_celula(tabela, cel, fmt, fmt.topPadding(),
                                       fmt.bottomPadding() - pq.empurrao(fmt))
            if h is None:
                return None
            maior = max(maior, h)
        return maior

    def _margens_do_qt(self, tabela) -> tuple[float, float]:
        """(acima, abaixo) twips que o Qt reserva na pagina para as linhas da tabela: a margem
        do quadro raiz e a da tabela. Abaixo, o Qt 6 soma a margem de CIMA da tabela
        (`effectiveBottomMargin` em `layoutFrame`), nao a de baixo; aqui como o Qt faz."""
        raiz = self.layout.doc.rootFrame().frameFormat()
        tf = tabela.format()
        proprio = tf.topMargin() + tf.border() + tf.padding()
        return ((raiz.topMargin() + raiz.border() + raiz.padding() + proprio) * 15.0,
                (raiz.bottomMargin() + raiz.border() + raiz.padding() + proprio) * 15.0)

    def _cabe_ou_desce(self, tabela, topo: float, cels, cab_altura: float):
        """Decide a linha que comeca em `topo` (natural): None = cabe, ou o Qt ja' a leva
        inteira, ou e' mais alta que a pagina (parte, como no Word); senao (falta em twips para
        a primeira linha de texto de cada celula passar do pe' da pagina, pagina)."""
        mapa = self.layout.mapa
        altura = self._altura_natural(tabela, cels)
        if altura is None:
            return None
        acima, abaixo = self._margens_do_qt(tabela)
        raiz = self.layout.doc.rootFrame().frameFormat()
        pagina = mapa.pagina_de_y(topo + 1.0)
        pe = mapa.fim(pagina) - abaixo
        pe_word = mapa.fim(pagina) - (raiz.bottomMargin() + raiz.border() + raiz.padding()) * 15.0
        if topo + altura <= pe_word + 1.0:
            # Cabe no Word. O Qt pode partir assim mesmo (ele reserva no pe' a margem de CIMA
            # da tabela, `_margens_do_qt`): a linha fica como o Qt a faz, uma linha de texto
            # na pagina seguinte, mais perto do Word que a linha inteira descendo (doc_14,
            # quebra 3, docs/SPIKES.md "cantSplit").
            return None
        deslocamentos = [(c.format().toTableCellFormat().topPadding()
                          + c.format().toTableCellFormat().topBorder() / 2.0) * 15.0
                         for c in cels]
        primeira = topo + min(deslocamentos)
        if primeira >= pe:
            return None  # o Qt ja' leva a linha inteira
        if altura + cab_altura > mapa.fim(pagina) - mapa.topo(pagina) - acima - abaixo:
            return None  # mais alta que a pagina: parte
        return pe - primeira + 0.5, pagina

    def _altura_do_cabecalho(self, tabela, celulas, cab: int) -> float:
        total = 0.0
        for r in range(cab):
            h = self._altura_natural(tabela, celulas[r]) if celulas[r] else None
            total += h or 0.0
        return total

    def _empurrao_desejado(self, tabela, r: int, celulas, cab: int):
        """(empurrao em px96 na linha r-1, pagina) para a linha r; None = nada a ver aqui."""
        cels, ant = celulas[r], celulas[r - 1]
        atual = max(pq.empurrao(c.format()) for c in ant)
        quer = self._nao_partir(cels) and self._simples(tabela, r) and \
            self._simples(tabela, r - 1)
        if not quer:
            return (0.0, self.layout.mapa.pagina_de_y(self._topo_da_linha(ant) or 0.0)) \
                if atual > pq.FOLGA else None
        if atual <= pq.FOLGA and not self._partida(cels):
            return None  # o caso comum: a linha nao esta' partida e nao tem empurrao
        topo_ant = self._topo_da_linha(ant)
        altura_ant = self._altura_natural(tabela, ant)
        if topo_ant is None or altura_ant is None:
            return (0.0, 0) if atual > pq.FOLGA else None
        topo = topo_ant + altura_ant
        res = self._cabe_ou_desce(tabela, topo, cels,
                                  self._altura_do_cabecalho(tabela, celulas, cab))
        pagina = self.layout.mapa.pagina_de_y(topo + 1.0)
        if res is None:
            return 0.0, pagina
        falta, pagina = res
        return falta / 15.0, pagina

    def _quebra_da_tabela(self, u: _Unidade, anterior: _Unidade | None, cab: int):
        """Mudancas na quebra antes da tabela: a linha que nao se parte e' a primeira, uma do
        cabecalho repetido ou a primeira depois dele (o Qt leva a tabela inteira quando uma
        delas desce), nao cabe na pagina e cabe numa pagina so'."""
        tabela = u.tabela
        tf = tabela.format()
        tem = pq.eh_regra(tf)
        quer = False
        if anterior is not None and not (pq.tem_quebra_antes(tf) and not tem):
            celulas = [_celulas_da_linha(tabela, r) for r in range(cab + 1)]
            if all(celulas) and any(self._nao_partir(c) for c in celulas) and \
                    all(self._simples(tabela, r) for r in range(cab + 1)) and \
                    (tem or any(self._partida(c) for c in celulas)):
                if tem:
                    # sem a quebra, a tabela comecaria logo depois da unidade de cima; a conta
                    # e' estimada: a quebra so' sai com folga (histerese de HISTERESE_LINHA_TW)
                    fa = anterior.bloco.blockFormat().bottomMargin() \
                        if anterior.bloco is not None else 0.0
                    topo = self._fim(anterior) + (fa + tf.topMargin() + tf.border()
                                                  + tf.padding()) * 15.0 + HISTERESE_LINHA_TW
                else:
                    topo = self._topo_da_linha(celulas[0])
                cab_alt = 0.0
                for r in range(cab + 1):
                    if topo is None:
                        break
                    if self._nao_partir(celulas[r]) and \
                            self._cabe_ou_desce(tabela, topo, celulas[r], cab_alt) is not None:
                        quer = True
                        break
                    h = self._altura_natural(tabela, celulas[r])
                    if h is None:
                        break
                    topo += h
                    if r < cab:
                        cab_alt += h
        if quer == tem:
            return None
        novo = type(tf)(tf)
        if quer:
            pq.definir_regra(novo, True, 4)
        else:
            pq.definir_regra(novo, False)
        return [(tabela, novo)]

    def _fim(self, u: _Unidade) -> float:
        """Onde o Qt deixa o y depois da unidade (twips)."""
        dl = self.layout.doc.documentLayout()
        if u.tabela is not None:
            return dl.frameBoundingRect(u.tabela).bottom()
        lay = u.bloco.layout()
        r = dl.blockBoundingRect(u.bloco)
        if lay.lineCount() == 0 or (u.bloco.length() == 1 and self._tabela_antes(u.bloco)):
            # o vazio depois da tabela fica no pe' dela e nao avanca o y (o Qt o esconde)
            return r.bottom()
        ultima = lay.lineAt(lay.lineCount() - 1)
        avanco, corte = pq.avanco_e_corte(u.bloco.blockFormat(), ultima)
        return r.top() + ultima.y() + max(avanco, corte)

    def _alturas(self, bloco, fmt) -> list[tuple[float, float]]:
        lay = bloco.layout()
        return [pq.avanco_e_corte(fmt, lay.lineAt(i)) for i in range(lay.lineCount())]

    def _precisa(self, u: _Unidade, anterior: _Unidade, margem_tw: float = 0.0) -> bool:
        """O bloco empurrado pelas regras ainda precisa descer? Simula o bloco sem a quebra,
        logo depois da unidade de cima, com as alturas das linhas dele.

        `margem_tw` (0.1.18, histerese): cabendo inteiro, so' conta como "nao precisa" se sobrar
        pelo menos essa folga no pe' da pagina; senao continua empurrado."""
        bloco = u.bloco
        fmt = bloco.blockFormat()
        mapa = self.layout.mapa
        fim = self._fim(anterior)
        pagina = mapa.pagina_de_y(fim - FOLGA)
        pe = mapa.fim(pagina)
        margem = max(self._antes_desejado(bloco, fmt, {}, sem_regra=True),
                     anterior.bloco.blockFormat().bottomMargin()
                     if anterior.bloco is not None else 0.0) * 15.0
        if anterior.tabela is not None:
            margem = 0.0  # depois da tabela o Qt nao poe o espaco antes (vai na margem dela)
        y0 = fim + margem
        alturas = self._alturas(bloco, fmt)
        n = len(alturas)
        a = mod.linhas_que_cabem(y0, alturas, pe)
        if a == 0:
            # nem a primeira linha caberia: desce sozinho, mas sem a quebra o Qt perderia o
            # espaco antes no alto da pagina (o Word o mantem)
            return "topo" in self.partes and (pq.antes_real(fmt) or 0.0) > pq.FOLGA
        if a < n:
            return mod.deve_empurrar(a, n - a, self._flag(fmt, "widowControl"),
                                     self._flag(fmt, "keepLines"), False)
        # cabe inteiro: o "manter com o proximo" pede a cadeia inteira e a primeira linha (duas,
        # com o controle de viuvas) do primeiro paragrafo depois dela
        y = y0 + sum(av for av, _c in alturas)
        if margem_tw and pe - y < margem_tw:
            return True
        atual, fa = bloco, fmt
        for _ in range(64):
            if not self._flag(fa, "keepNext"):
                return False
            seguinte = atual.next()
            while seguinte.isValid() and not seguinte.isVisible():
                seguinte = seguinte.next()
            if not seguinte.isValid():
                return False
            if QTextCursor(seguinte).currentTable() is not None:
                return True  # tabela logo abaixo: conservador, fica empurrado
            fs = seguinte.blockFormat()
            if pq.tem_quebra_antes(fs) and not pq.eh_regra(fs):
                return False
            alt = self._alturas(seguinte, fs)
            if not alt:
                return False
            y += max(self._antes_desejado(seguinte, fs, {}, sem_regra=True),
                     fa.bottomMargin()) * 15.0
            if self._flag(fs, "keepNext"):
                if mod.linhas_que_cabem(y, alt, pe) < len(alt):
                    return True
                y += sum(av for av, _c in alt)
                atual, fa = seguinte, fs
                continue
            precisa = min(len(alt), 2) if self._flag(fs, "widowControl") else 1
            return mod.linhas_que_cabem(y, alt[:precisa], pe) < precisa
        return True


def _celulas_da_linha(tabela, r: int) -> list:
    """As celulas que comecam na linha r (a mesclada conta uma vez, na linha e coluna dela)."""
    cels = []
    c = 0
    while c < tabela.columns():
        cel = tabela.cellAt(r, c)
        if cel.row() == r and cel.column() == c:
            cels.append(cel)
            c += max(1, cel.columnSpan())
        else:
            c += 1
    return cels


class _LinhasDaTabela:
    """As celulas de cada linha (`_celulas_da_linha`), lidas so' quando pedidas."""

    def __init__(self, tabela) -> None:
        self.tabela = tabela
        self._lidas: dict[int, list] = {}

    def __getitem__(self, r: int) -> list:
        if r not in self._lidas:
            self._lidas[r] = _celulas_da_linha(self.tabela, r)
        return self._lidas[r]


def _tabelas(quadro, faixa=None):
    """As tabelas dentro do quadro, em todos os niveis; com `faixa` (posicoes), so' as que a
    cruzam (o quadro fora dela nem e' aberto)."""
    for filho in quadro.childFrames():
        if faixa is not None and (filho.lastPosition() < faixa[0] or
                                  filho.firstPosition() > faixa[1]):
            continue
        if isinstance(filho, QTextTable):
            yield filho
        yield from _tabelas(filho, faixa)
