"""Secoes na tela (0.1.12): papel, margens, cabecalhos e numeracao de cada secao.

Decidido pelo spike da 0.1.12 (docs/SPIKES.md): o QTextDocument pagina com um tamanho so'
(`pageSize`), e nem a margem de um QTextFrame filho nem a de uma tabela valem por pagina
(medido no Qt 6.11.2: so' a do quadro raiz, igual em todas). Entao o documento continua um so'
(o cursor, a selecao, o desfazer e o localizar atravessam as secoes como antes) e:

- a pagina n do QTextDocument continua sendo a faixa [n*H, (n+1)*H); H e' a MAIOR altura de
  corpo entre as secoes e W, a maior largura;
- a secao mais estreita que W ganha, em cada paragrafo e tabela do primeiro nivel, um recuo
  direito escondido (PROP_RECUO_SECAO, `ponte_qt/estilos.py`): o texto reflui na largura dela;
- a secao mais baixa que H usa o espacador das notas (`interface/notas.py`: a pagina termina em
  `n*H + altura do corpo da secao`): o bloco que nao cabe desce para a pagina seguinte;
- a quebra entre secoes e' a quebra de pagina do Qt, derivada (PROP_QUEBRA_SECAO): depois do
  paragrafo da quebra (PageBreak_AlwaysAfter) quando a secao seguinte comeca em pagina nova; a
  pagina em branco de evenPage/oddPage e' mais uma quebra, antes da unidade seguinte (medido: as
  duas quebras seguidas deixam uma pagina vazia no meio);
- cada folha sabe a sua secao (`secao_da_folha`): o papel e as margens dela, a altura do corpo,
  os cabecalhos (com a heranca do Word) e o numero (reinicio e formato da secao).

Os formatos derivados entram no desfazer como os espacadores das notas: um passo anotado depois
do passo do usuario (`ConjuntoDeNotas.ajustar`), desfeito junto com ele.

Documento de uma secao so': nada disso roda; o layout segue o caminho de antes.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field, replace

from PySide6.QtGui import QTextCursor, QTextFormat, QTextTable

from editdoc import log_interno
from editdoc.modelo import secoes as mod_secoes
from editdoc.modelo.campos import tipo_da_pagina
from editdoc.modelo.pagina import Pagina, com_desvio, pagina_efetiva
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import secoes as pq
from editdoc.ponte_qt.notas import PROP_QUEBRA_NOTA
from editdoc.ponte_qt.paginacao import PROP_QUEBRA_REGRA as _PROP_QUEBRA_REGRA

log = log_interno.obter(__name__)

_DEPOIS = QTextFormat.PageBreakFlag.PageBreak_AlwaysAfter
_ANTES = QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore
#: Bits de PROP_QUEBRA_SECAO: a quebra depois do paragrafo e a da pagina em branco.
BIT_DEPOIS = 1
BIT_ANTES = 2
FOLGA = 0.5
#: Rodadas de conferencia da pagina em branco (cada uma refaz o layout).
MAX_RODADAS = 4
ONDES = ("cabecalho", "rodape")


@dataclass
class InfoSecao:
    """Uma secao como a tela a usa."""
    ident: str | None  # None = a ultima secao
    pos: int | None  # posicao do caractere da quebra (None na ultima)
    secao: mod_secoes.Secao
    pagina: Pagina  # a do arquivo
    efetiva: Pagina  # corpo empurrado pelo maior cabecalho e rodape da secao
    topos: dict = field(default_factory=dict)
    inicio: int = 0
    paginas: int = 1
    numero_inicial: int = 1

    @property
    def hb(self) -> float:
        return float(self.efetiva.corpo_altura_tw())

    @property
    def largura(self) -> float:
        return float(self.pagina.corpo_largura_tw())

    def pagina_numerada(self) -> Pagina:
        """A pagina da secao com o numero da primeira folha dela (para PAGE e o tipo da folha)."""
        return replace(self.pagina, numero_inicial=self.numero_inicial)


def _bits(fmt) -> int:
    valor = fmt.property(pq.PROP_QUEBRA_SECAO)
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else 0


def _inteiro(flags) -> int:
    try:
        return int(flags.value)
    except AttributeError:
        return int(flags)


class ConjuntoDeSecoes:
    """As secoes do corpo do `LayoutPaginado`: estrutura, geometria, mapa de folhas e formatos
    derivados."""

    def __init__(self, layout) -> None:
        self.layout = layout
        self.lista: list[InfoSecao] = []
        #: geracao da geometria e do mapa (chave dos caches de pintura)
        self.geracao = 0
        self._chave_calculo: tuple | None = None
        self._assinatura: tuple | None = None
        self._efetivas: dict = {}
        self._por_folha: dict = {}
        self._inicios: list[int] = [0]
        #: secoes (indice) que comecam depois de uma pagina em branco (evenPage/oddPage)
        self._branco: set[int] = set()
        #: conferencia dos formatos so' do que mudou
        self._conferido: tuple | None = None
        self._sujo: list[int] | None = None
        self._blocos = -1
        self._tem_derivados = False
        #: contagem de ajustes (os testes olham)
        self.ajustes = 0
        layout.doc.contentsChange.connect(self._mudou)

    def _mudou(self, pos: int, removidos: int, adicionados: int) -> None:
        fim = pos + max(adicionados, 1)
        if self._sujo is None:
            self._sujo = [pos, fim]
        else:
            self._sujo = [min(self._sujo[0], pos), max(self._sujo[1], fim)]

    def multiplas(self) -> bool:
        return len(self.lista) > 1

    # -- estrutura ---------------------------------------------------------------------------
    def _secoes_do_documento(self) -> list[tuple[str | None, int | None, mod_secoes.Secao]]:
        doc = self.layout.doc
        reg = pq.registro(doc)
        saida = []
        for pos, ident in pq.quebras_de_secao(doc):
            secao = reg.get(ident)
            if secao is not None:
                saida.append((ident, pos, secao))
        final = pq.secao_final(doc)
        final.pagina = self.layout.pagina_arquivo
        saida.append((None, None, final))
        return saida

    def secoes_atuais(self) -> list[mod_secoes.Secao]:
        """As secoes na ordem do texto agora (a ultima no fim), sem esperar a pintura."""
        return [s for _i, _p, s in self._secoes_do_documento()]

    def indice_da_posicao(self, pos: int) -> int:
        """Indice da secao do texto na posicao `pos` (do corpo)."""
        posicoes = [p for p, _i in pq.quebras_de_secao(self.layout.doc)]
        bloco = self.layout.doc.findBlock(max(0, pos))
        return bisect.bisect_left(posicoes, bloco.position())

    # -- faixas (cabecalho e rodape) ---------------------------------------------------------
    def faixa_efetiva(self, indice: int, onde: str, tipo: str, secoes=None):
        """(indice da secao que declara, FaixaQt) com a heranca do Word, ou None."""
        faixas = self.layout.faixas
        if secoes is None:
            secoes = [info.secao for info in self.lista] if self.lista else self.secoes_atuais()
        for j in range(min(indice, len(secoes) - 1), -1, -1):
            fid = secoes[j].chaves.get((onde, tipo))
            if fid is not None:
                faixa = faixas.por_id(fid)
                if faixa is not None:
                    return j, faixa
        return None

    @staticmethod
    def tipos_ativos(pagina: Pagina) -> list[str]:
        tipos = ["padrao"]
        if pagina.primeira_diferente:
            tipos.append("primeira")
        if pagina.pares_impares:
            tipos.append("par")
        return tipos

    def _chave_do_calculo(self, brutas) -> tuple:
        faixas = tuple((f.ident, f.serie, f.doc.revision()) for f in self.layout.faixas.todas())
        return (tuple((ident, s.pagina, s.tipo, tuple(sorted(s.chaves.items())))
                      for ident, _p, s in brutas), self.layout.pagina_arquivo, faixas)

    def calcular(self, forcar: bool = False) -> bool:
        """Estrutura e geometria das secoes (sem o mapa de folhas). True se a geometria mudou."""
        brutas = self._secoes_do_documento()
        chave = self._chave_do_calculo(brutas)
        if not forcar and chave == self._chave_calculo and len(brutas) == len(self.lista):
            for info, (ident, pos, _s) in zip(self.lista, brutas):
                info.pos = pos
            return False
        self._chave_calculo = chave
        pares = self.layout.pagina_arquivo.pares_impares
        lista: list[InfoSecao] = []
        for ident, pos, secao in brutas:
            pagina = replace(secao.pagina, pares_impares=pares) if ident is not None \
                else self.layout.pagina_arquivo
            lista.append(InfoSecao(ident, pos, secao, pagina, pagina))
        secoes = [info.secao for info in lista]
        for i, info in enumerate(lista):
            largura = info.pagina.corpo_largura_tw()
            ativos = self.tipos_ativos(info.pagina)
            maiores = [0.0, 0.0]
            por_tipo = {}
            for tipo in ("primeira", "par", "padrao"):
                alt = []
                for k, onde in enumerate(ONDES):
                    achada = self.faixa_efetiva(i, onde, tipo, secoes)
                    h = achada[1].altura_na_largura(largura) if achada is not None else 0.0
                    alt.append(h)
                    if tipo in ativos:
                        maiores[k] = max(maiores[k], h)
                por_tipo[tipo] = alt
            # 0.1.27: o corpo comeca `desvio` antes da margem (recuo negativo, desvio.py).
            info.efetiva = com_desvio(pagina_efetiva(info.pagina, maiores[0], maiores[1]),
                                      round(getattr(self.layout, "desvio", 0.0)))
            hb = info.efetiva.corpo_altura_tw()
            for tipo, (hc, hr) in por_tipo.items():
                ef = pagina_efetiva(info.pagina, hc, hr)
                topo = min(ef.margem_sup_tw, info.pagina.altura_tw - ef.margem_inf_tw - hb)
                info.topos[tipo] = max(0, topo)
        # O mapa de antes vale ate' o proximo `mapear` (a secao nova comeca no fim).
        antigos = {info.ident: (info.inicio, info.paginas, info.numero_inicial)
                   for info in self.lista}
        for info in lista:
            if info.ident in antigos:
                info.inicio, info.paginas, info.numero_inicial = antigos[info.ident]
        self.lista = lista
        assinatura = tuple((info.ident, info.pagina, info.efetiva,
                            tuple(sorted(info.topos.items()))) for info in lista)
        mudou = assinatura != self._assinatura
        self._assinatura = assinatura
        self._efetivas = {}
        self._por_folha = {}
        self._branco = {i for i in self._branco if i < len(lista)}
        if mudou:
            self.geracao += 1
        return mudou

    def dimensoes(self) -> tuple[float, float]:
        """(W, H): a maior largura e a maior altura de corpo entre as secoes. W tem o
        deslocamento do recuo negativo (0.1.27)."""
        return (max(info.largura for info in self.lista) + self._desvio(),
                max(info.hb for info in self.lista))

    def _desvio(self) -> float:
        return float(round(getattr(self.layout, "desvio", 0.0)))

    # -- mapa de folhas -----------------------------------------------------------------------
    def _unidade_depois(self, pos: int):
        """(posicao inicial, bloco ou None, tabela ou None) da unidade do primeiro nivel que vem
        depois do paragrafo da posicao `pos`; (None, None, None) no fim do documento."""
        doc = self.layout.doc
        bloco = doc.findBlock(pos).next()
        if not bloco.isValid():
            return None, None, None
        tabela = QTextCursor(bloco).currentTable()
        if tabela is not None:
            while tabela.parentFrame() is not None and isinstance(tabela.parentFrame(), QTextTable):
                tabela = tabela.parentFrame()
            return tabela.firstPosition(), None, tabela
        return bloco.position(), bloco, None

    def mapear(self) -> None:
        """Primeira folha, numero de folhas e numero inicial de cada secao."""
        lay = self.layout
        dl = lay.doc.documentLayout()
        total = lay.numero_paginas()
        inicios = [0]
        for i in range(1, len(self.lista)):
            anterior = self.lista[i - 1]
            _p, bloco, tabela = self._unidade_depois(anterior.pos) if anterior.pos is not None \
                else (None, None, None)
            if bloco is None and tabela is None:
                inicio = total
            else:
                topo = dl.frameBoundingRect(tabela).top() if tabela is not None \
                    else dl.blockBoundingRect(bloco).top()
                inicio = lay.mapa.folha_da_pagina(lay.mapa.pagina_de_y(topo, 1e-6))
                base = dl.blockBoundingRect(lay.doc.findBlock(anterior.pos)).bottom()
                if lay.mapa.pagina_de_y(max(0.0, base - 1.0), 1e-6) >= inicio:
                    # Secao continua que comeca no meio da folha (o fim da anterior esta' na
                    # mesma folha): a folha e' da anterior.
                    inicio += 1
            inicios.append(min(max(inicio, inicios[-1]), max(total, inicios[-1])))
        for i, info in enumerate(self.lista):
            info.inicio = inicios[i]
            fim = inicios[i + 1] if i + 1 < len(inicios) else max(total, inicios[i] + (i == 0))
            info.paginas = max(0, fim - inicios[i])
        numeros = mod_secoes.numeros_iniciais([info.paginas for info in self.lista],
                                              [info.pagina for info in self.lista])
        for info, numero in zip(self.lista, numeros):
            info.numero_inicial = numero
        mudou = inicios != self._inicios or \
            [i.numero_inicial for i in self.lista] != getattr(self, "_numeros", None)
        if mudou:
            self._efetivas = {}
            self._por_folha = {}
        self._numeros = [i.numero_inicial for i in self.lista]
        self._inicios = inicios

    def secao_da_folha(self, n: int) -> int:
        if len(self.lista) <= 1:
            return 0
        return min(len(self.lista) - 1,
                   max(0, bisect.bisect_right(self._inicios, max(0, int(n))) - 1))

    def info_da_folha(self, n: int) -> InfoSecao:
        return self.lista[self.secao_da_folha(n)]

    def tipo_da_folha(self, n: int) -> str:
        info = self.info_da_folha(n)
        return tipo_da_pagina(max(0, int(n) - info.inicio), info.pagina_numerada())

    def efetiva_da(self, n: int) -> Pagina:
        # Pedida milhares de vezes por quadro (a tela, os campos, as notas): por folha, em cache
        # ate' a geometria ou o mapa mudarem.
        ef = self._por_folha.get(n)
        if ef is not None:
            return ef
        ef = self._efetiva_calculada(n)
        if len(self._por_folha) > 20000:
            self._por_folha.clear()
        self._por_folha[n] = ef
        return ef

    def _efetiva_calculada(self, n: int) -> Pagina:
        i = self.secao_da_folha(n)
        info = self.lista[i]
        tipo = self.tipo_da_folha(n)
        chave = (i, tipo)
        ef = self._efetivas.get(chave)
        if ef is None:
            base = info.efetiva
            topo = info.topos.get(tipo, base.margem_sup_tw)
            if topo == base.margem_sup_tw:
                ef = base
            else:
                ef = replace(base, margem_sup_tw=topo,
                             margem_inf_tw=base.altura_tw - topo - base.corpo_altura_tw())
            self._efetivas[chave] = ef
        return ef

    def campos_da_folha(self, n: int) -> tuple[int, Pagina, int]:
        """(indice na secao, pagina numerada da secao, paginas da secao): o que PAGE e
        SECTIONPAGES pedem."""
        info = self.info_da_folha(n)
        return max(0, int(n) - info.inicio), info.pagina_numerada(), max(1, info.paginas)

    def baixa(self) -> bool:
        """Alguma secao tem corpo mais baixo que H (o espacador das notas trabalha)."""
        if not self.multiplas():
            return False
        H = max(info.hb for info in self.lista)
        return any(info.hb < H - FOLGA for info in self.lista)

    # -- formatos derivados ---------------------------------------------------------------------
    def _unidades(self, desde: int | None = None, ate: int | None = None):
        """(posicao inicial, bloco ou None, tabela ou None) do primeiro nivel do corpo, so' as que
        tocam [desde, ate] se dados."""
        doc = self.layout.doc
        if desde is None:
            it = doc.rootFrame().begin()
            while not it.atEnd():
                quadro = it.currentFrame()
                if quadro is not None:
                    if isinstance(quadro, QTextTable):
                        yield quadro.firstPosition(), None, quadro
                else:
                    bloco = it.currentBlock()
                    if bloco.isValid():
                        yield bloco.position(), bloco, None
                it += 1
            return
        bloco = doc.findBlock(max(0, desde))
        vistas = set()
        while bloco.isValid() and bloco.position() <= ate:
            tabela = QTextCursor(bloco).currentTable()
            if tabela is not None:
                while isinstance(tabela.parentFrame(), QTextTable):
                    tabela = tabela.parentFrame()
                if tabela.firstPosition() not in vistas:
                    vistas.add(tabela.firstPosition())
                    yield tabela.firstPosition(), None, tabela
                bloco = doc.findBlock(tabela.lastPosition() + 1)
                continue
            yield bloco.position(), bloco, None
            bloco = bloco.next()

    def _quebra_do_usuario_logo_antes(self, pos: int) -> bool:
        """True quando o paragrafo de cima da quebra de secao so' tem a quebra de pagina do
        usuario (0.1.22). Essa quebra fica no fim dele, e a pagina seguinte ja' comeca ali: a
        quebra derivada da secao (no paragrafo da secao) nao entra, senao a pagina em branco
        (o Word poe o paragrafo so' com a quebra e a quebra de secao na mesma pagina)."""
        doc = self.layout.doc
        anterior = doc.findBlock(pos).previous()
        return anterior.isValid() and anterior.length() <= 1 \
            and pq.quebra_so_depois(anterior.blockFormat())

    def conferir_formatos(self, forcar: bool = False) -> bool:
        """Quebras de pagina, pagina em branco e recuos escondidos em dia. True se mudou algum
        formato (o layout muda). So' confere o trecho editado, a nao ser que a estrutura mude."""
        doc = self.layout.doc
        estrutura = (tuple((info.ident, info.pos) for info in self.lista), self.geracao,
                     tuple(sorted(self._branco)), doc.blockCount())
        sujo, self._sujo = self._sujo, None
        if not self.multiplas() and not self._tem_derivados:
            self._conferido = estrutura
            return False
        tudo = forcar or self._conferido is None or estrutura[1:] != self._conferido[1:] \
            or len(estrutura[0]) != len(self._conferido[0]) \
            or [i for i, _p in estrutura[0]] != [i for i, _p in self._conferido[0]]
        self._conferido = estrutura
        if not tudo and sujo is None:
            return False
        W, _H = self.dimensoes()
        posicoes = [info.pos for info in self.lista[:-1]]
        quebras_depois = set()
        branco = set()
        for i, info in enumerate(self.lista[:-1]):
            seguinte = self.lista[i + 1]
            if mod_secoes.comeca_em_pagina_nova(seguinte.secao.tipo, info.pagina, seguinte.pagina) \
                    and not self._quebra_do_usuario_logo_antes(info.pos):
                quebras_depois.add(doc.findBlock(info.pos).position())
            if i + 1 in self._branco:
                inicio, _b, _t = self._unidade_depois(info.pos)
                if inicio is not None:
                    branco.add(inicio)
        if tudo:
            unidades = self._unidades()
        else:
            # O trecho editado e os paragrafos das quebras (a quebra pode ter mudado de bloco).
            alvo = {doc.findBlock(p).position() for p in posicoes}
            unidades = list(self._unidades(sujo[0], sujo[1]))
            ja = {u[0] for u in unidades}
            for p in sorted(alvo - ja):
                bloco = doc.findBlock(p)
                unidades.append((bloco.position(), bloco, None))
            for p in sorted(branco - ja):
                bloco = doc.findBlock(p)
                tabela = QTextCursor(bloco).currentTable()
                unidades.append((p, None if tabela is not None else bloco, tabela))
        mudancas = []
        tem = self._tem_derivados if not tudo else False
        multiplas = self.multiplas()
        for inicio, bloco, tabela in unidades:
            fmt = tabela.format() if tabela is not None else bloco.blockFormat()
            bits = _bits(fmt)
            indice = bisect.bisect_left(posicoes, inicio)
            info = self.lista[min(indice, len(self.lista) - 1)]
            quer = 0
            if bloco is not None and inicio in quebras_depois:
                quer |= BIT_DEPOIS
            if inicio in branco:
                quer |= BIT_ANTES
            extra = max(0.0, W - self._desvio() - info.largura) if multiplas else 0.0
            atual = pq_estilos.recuo_secao(fmt)
            if atual is None:
                recuo_ok = extra < FOLGA
            else:
                margem = fmt.rightMargin() * (15.0 if tabela is not None else 1.0)
                recuo_ok = (extra >= FOLGA and abs(atual[0] - extra) < FOLGA
                            and abs(margem - atual[1]) < FOLGA)
            politica = _inteiro(fmt.pageBreakPolicy())
            quebra_ok = bits == quer and (
                not quer & BIT_DEPOIS or tabela is not None or politica & _inteiro(_DEPOIS)) and (
                not quer & BIT_ANTES or politica & _inteiro(_ANTES))
            if not quebra_ok or not recuo_ok:
                mudancas.append((bloco, tabela, quer, extra))
            if quer or extra >= FOLGA:
                tem = True
        self._tem_derivados = tem
        if not mudancas:
            return False

        def aplicar(_c) -> None:
            for bloco, tabela, quer, extra in mudancas:
                if tabela is not None:
                    fmt = tabela.format()
                    self._aplicar_quebra(fmt, quer, tabela=True)
                    self._aplicar_recuo_tabela(fmt, extra)
                    tabela.setFormat(fmt)
                else:
                    fmt = bloco.blockFormat()
                    self._aplicar_quebra(fmt, quer, tabela=False)
                    self._aplicar_recuo(fmt, extra)
                    QTextCursor(bloco).setBlockFormat(fmt)

        self.layout.notas.ajustar(aplicar)
        self._sujo = None
        self.ajustes += 1
        return True

    @staticmethod
    def _aplicar_quebra(fmt, quer: int, tabela: bool) -> None:
        bits = _bits(fmt)
        valor = _inteiro(fmt.pageBreakPolicy())
        depois, antes = _inteiro(_DEPOIS), _inteiro(_ANTES)
        if bits & BIT_DEPOIS and not quer & BIT_DEPOIS:
            valor &= ~depois
        if bits & BIT_ANTES and not quer & BIT_ANTES and not fmt.property(PROP_QUEBRA_NOTA) \
                and not fmt.property(_PROP_QUEBRA_REGRA):
            valor &= ~antes
        if quer & BIT_DEPOIS and not tabela:
            valor |= depois
        if quer & BIT_ANTES:
            valor |= antes
        fmt.setPageBreakPolicy(QTextFormat.PageBreakFlag(valor))
        if quer:
            fmt.setProperty(pq.PROP_QUEBRA_SECAO, int(quer))
        else:
            fmt.clearProperty(pq.PROP_QUEBRA_SECAO)

    @staticmethod
    def _aplicar_recuo(fmt, extra: float) -> None:
        real = pq_estilos.recuo_direito_real(fmt)
        tinha = pq_estilos.recuo_secao(fmt) is not None
        if extra < FOLGA:
            if tinha:
                if abs(real) < FOLGA:
                    fmt.clearProperty(QTextFormat.Property.BlockRightMargin)
                else:
                    fmt.setRightMargin(real)
                fmt.clearProperty(pq_estilos.PROP_RECUO_SECAO)
            return
        total = real + extra
        fmt.setRightMargin(total)
        fmt.setProperty(pq_estilos.PROP_RECUO_SECAO, f"{extra};{total}")

    @staticmethod
    def _aplicar_recuo_tabela(fmt, extra: float) -> None:
        # Margem do quadro da tabela em px96 (o Qt escala, como a largura da coluna).
        if extra < FOLGA:
            if pq_estilos.recuo_secao(fmt) is not None:
                fmt.setRightMargin(0.0)
                fmt.clearProperty(pq_estilos.PROP_RECUO_SECAO)
            return
        fmt.setRightMargin(extra / 15.0)
        fmt.setProperty(pq_estilos.PROP_RECUO_SECAO, f"{extra};{extra}")

    def conferir_branco(self) -> bool:
        """Pagina em branco de evenPage/oddPage: o Word poe uma para a secao comecar na pagina de
        numero par (ou impar). Decidida pela numeracao que continua; com reinicio, pelo numero
        que a pagina teria sem ele (senao a pagina em branco nao mudaria nada e o plano nao
        pararia). True se a escolha mudou (os formatos precisam de outra conferencia)."""
        novo: set[int] = set()
        if self.multiplas():
            primeira = self.lista[0].pagina.numero_inicial
            inicio_num = primeira if primeira is not None else 1
            for i in range(1, len(self.lista)):
                anterior, info = self.lista[i - 1], self.lista[i]
                paginas_sem = anterior.paginas - (1 if i in self._branco else 0)
                continuo = inicio_num + max(0, paginas_sem)
                paridade = mod_secoes.paridade_pedida(info.secao.tipo)
                if paridade is not None and continuo % 2 != paridade:
                    novo.add(i)
                    continuo += 1
                proprio = info.pagina.numero_inicial
                inicio_num = proprio if proprio is not None else continuo
        mudou = novo != self._branco
        self._branco = novo
        return mudou

    def tem_pagina_em_branco(self, indice: int) -> bool:
        return indice in self._branco

    # -- ciclo ------------------------------------------------------------------------------
    def atualizar(self, forcar: bool = False) -> bool:
        """Estrutura, geometria, formatos derivados e mapa em dia. True se a tela muda."""
        antes = (self.geracao, tuple((i.ident, i.inicio, i.paginas, i.numero_inicial)
                                     for i in self.lista))
        try:
            self.layout.notas.separar_ajustes()
            mudou_geo = self.calcular(forcar)
            if mudou_geo:
                self.layout.aplicar_dimensoes()
            for rodada in range(MAX_RODADAS):
                self.conferir_formatos(forcar=forcar or mudou_geo or rodada > 0)
                self.mapear()
                if not self.conferir_branco():
                    break
            self.layout.notas.separar_ajustes()
        except Exception:  # noqa: BLE001 - as secoes nao podem derrubar a pintura
            log.exception("secoes")
        depois = (self.geracao, tuple((i.ident, i.inicio, i.paginas, i.numero_inicial)
                                      for i in self.lista))
        return antes != depois
