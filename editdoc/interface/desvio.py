"""Recuo esquerdo negativo na tela (0.1.27).

O `QTextDocumentLayout` nao aceita recuo esquerdo negativo: medido no Qt 6.12 (plataforma
`windows`), o paragrafo com recuo de -567 twips comeca no x 0 do quadro e fica com a largura do
corpo (9638 twips no doc_12, em vez de 10205), e a tabela com `w:tblInd` negativo fica na margem.
O Word poe o texto na margem menos o recuo, com a linha mais larga; com a linha estreita o texto
justificado quebra em mais linhas, e cada pagina do EditDoc levava menos texto que a do Word.

Mecanismo (docs/SPIKES.md "0.1.27"):

- `D` (`desvio`) e' o maior recuo negativo do primeiro nivel do corpo (paragrafo: recuo esquerdo
  mais o da primeira linha, quando negativo; tabela: o `w:tblInd`), limitado pela menor margem
  esquerda das secoes (o texto nao sai da folha);
- o QTextDocument fica `D` twips mais largo e o corpo comeca `D` twips antes da margem: a pagina
  efetiva (`LayoutPaginado.pagina`, `efetiva_da`) tem `margem_esq_tw` menos `D` e
  `desvio_tw = D`. Toda a geometria que ja' usa a efetiva (pintura, clique, caret, selecao,
  flutuantes, PDF e impressao) segue sem mudar; quem precisa da coluna do arquivo (a regua, as
  notas, a referencia "coluna" dos flutuantes, a largura das faixas) soma `desvio_tw` de volta;
- cada paragrafo e tabela do primeiro nivel ganha `D` no recuo esquerdo (PROP_RECUO_DESLOCADO,
  `ponte_qt/estilos.py`): a linha tem a largura do Word e comeca onde o Word a poe. O recuo do
  usuario e' `estilos.recuo_esquerdo_real` (o `de_qt`, a regua, a faixa, as tabulacoes, as
  listas); a tabela le' o recuo do JSON dela (`recuo_tw`), como o `de_qt`.

Os formatos entram no desfazer como os das secoes: um passo anotado depois do passo do usuario
(`ConjuntoDeNotas.ajustar`). `D` so' cresce numa edicao (a conferencia so' olha o trecho
editado); ao abrir, vale o do documento inteiro. Nada disso muda o arquivo gravado.
"""

from __future__ import annotations

from PySide6.QtGui import QTextFormat

from editdoc import log_interno
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt.para_qt import PROP_TABELA, ler_json

log = log_interno.obter(__name__)

#: Diferenca (twips) que conta como o mesmo valor.
FOLGA = 0.5


class ConjuntoDeDesvio:
    """O deslocamento do recuo negativo do corpo do `LayoutPaginado`."""

    def __init__(self, layout) -> None:
        self.layout = layout
        #: desligar (contraprova dos testes): o Qt volta a ignorar o recuo negativo
        self.ligado = True
        self._sujo: list[int] | None = None
        self._aplicando = False
        #: contagem de ajustes (os testes olham)
        self.ajustes = 0
        layout.doc.contentsChange.connect(self._mudou)

    def _mudou(self, pos: int, removidos: int, adicionados: int) -> None:
        if self._aplicando:
            return
        fim = pos + max(adicionados, 1)
        if self._sujo is None:
            self._sujo = [pos, fim]
        else:
            self._sujo = [min(self._sujo[0], pos), max(self._sujo[1], fim)]

    def conferir_tudo(self) -> None:
        """A proxima conferencia olha o documento inteiro (a margem esquerda mudou)."""
        self._sujo = [0, max(1, self.layout.doc.characterCount())]

    # -- o que cada unidade pede ---------------------------------------------------------------
    @staticmethod
    def _recuo_da_tabela(tabela) -> float:
        recuo = ler_json(tabela.format(), PROP_TABELA).get("recuo_tw")
        return float(recuo) if isinstance(recuo, (int, float)) and not isinstance(recuo, bool) \
            else 0.0

    def _pedido(self, bloco, tabela) -> float:
        """Quantos twips a unidade passa da margem para a esquerda (0 se nao passa)."""
        if tabela is not None:
            return max(0.0, -self._recuo_da_tabela(tabela))
        bf = bloco.blockFormat()
        real = pq_estilos.recuo_esquerdo_real(bf)
        primeira = min(0.0, bf.textIndent())
        return max(0.0, -(real + primeira))

    def _teto(self) -> float:
        """O texto nao sai da folha: no maximo a menor margem esquerda das secoes."""
        lay = self.layout
        if lay.secoes.multiplas():
            return float(min(info.pagina.margem_esq_tw for info in lay.secoes.lista))
        return float(lay.pagina_arquivo.margem_esq_tw)

    # -- ciclo ------------------------------------------------------------------------------
    def atualizar(self) -> bool:
        """`D` e os recuos deslocados em dia. True se mudou algo (a geometria ou um formato)."""
        try:
            return self._atualizar()
        except Exception:  # noqa: BLE001 - nao pode derrubar a pintura
            log.exception("recuo negativo")
            return False

    def _atualizar(self) -> bool:
        lay = self.layout
        doc = lay.doc
        sujo, self._sujo = self._sujo, None
        atual = float(lay.desvio)
        if not self.ligado:
            mudou = False
            if atual:
                lay.definir_desvio(0.0)
                mudou = True
            if mudou or sujo is not None:
                return self._aplicar(list(lay.secoes._unidades()), 0.0) or mudou
            return False
        if sujo is None:
            return False
        tudo = sujo[0] <= 0 and sujo[1] >= doc.characterCount() - 1
        unidades = list(lay.secoes._unidades()) if tudo else \
            list(lay.secoes._unidades(sujo[0], sujo[1]))
        if not unidades and not tudo:
            return False
        pedido = max((self._pedido(b, t) for _p, b, t in unidades), default=0.0)
        novo = min(pedido, self._teto())
        if not tudo:
            novo = max(novo, atual)
        novo = float(round(novo))
        mudou = False
        if abs(novo - atual) >= FOLGA:
            lay.definir_desvio(novo)
            mudou = True
            unidades = list(lay.secoes._unidades())
        return self._aplicar(unidades, novo) or mudou

    def _aplicar(self, unidades, extra: float) -> bool:
        mudancas = []
        for _p, bloco, tabela in unidades:
            if tabela is not None:
                fmt = tabela.format()
                if self._tabela_ok(fmt, tabela, extra):
                    continue
                mudancas.append((tabela, None))
            else:
                if self._bloco_ok(bloco.blockFormat(), extra):
                    continue
                mudancas.append((None, bloco))
        if not mudancas:
            return False

        def aplicar(_c) -> None:
            from PySide6.QtGui import QTextCursor
            for tabela, bloco in mudancas:
                if tabela is not None:
                    fmt = tabela.format()
                    self.aplicar_na_tabela(fmt, self._recuo_da_tabela(tabela), extra)
                    tabela.setFormat(fmt)
                else:
                    fmt = bloco.blockFormat()
                    self.aplicar_no_bloco(fmt, extra)
                    QTextCursor(bloco).setBlockFormat(fmt)

        self._aplicando = True
        try:
            self.layout.notas.ajustar(aplicar)
        finally:
            self._aplicando = False
        self.ajustes += 1
        return True

    # -- formatos ---------------------------------------------------------------------------
    @staticmethod
    def _bloco_ok(bf, extra: float) -> bool:
        d = pq_estilos.recuo_deslocado(bf)
        if extra < FOLGA:
            return d is None
        return d is not None and abs(d[0] - extra) < FOLGA and abs(bf.leftMargin() - d[1]) < FOLGA

    def _tabela_ok(self, fmt, tabela, extra: float) -> bool:
        d = pq_estilos.recuo_deslocado(fmt)
        if extra < FOLGA:
            return d is None
        alvo = max(0.0, self._recuo_da_tabela(tabela) + extra) / 15.0
        return d is not None and abs(d[0] - extra) < FOLGA and abs(fmt.leftMargin() - alvo) < 0.01

    @staticmethod
    def aplicar_no_bloco(fmt, extra: float) -> None:
        """O recuo esquerdo do bloco com o deslocamento `extra` (0: sem deslocamento)."""
        real = pq_estilos.recuo_esquerdo_real(fmt)
        tinha = pq_estilos.tem_recuo_esquerdo(fmt)
        if extra < FOLGA:
            if fmt.hasProperty(pq_estilos.PROP_RECUO_DESLOCADO):
                fmt.clearProperty(pq_estilos.PROP_RECUO_DESLOCADO)
                if tinha:
                    fmt.setLeftMargin(real)
                else:
                    fmt.clearProperty(QTextFormat.Property.BlockLeftMargin)
            return
        total = real + extra
        fmt.setLeftMargin(total)
        fmt.setProperty(pq_estilos.PROP_RECUO_DESLOCADO, f"{extra};{total};{1 if tinha else 0}")

    @staticmethod
    def aplicar_na_tabela(fmt, recuo_tw: float, extra: float) -> None:
        """A margem esquerda do quadro da tabela (px96): o recuo do arquivo mais `extra`."""
        if extra < FOLGA:
            if fmt.hasProperty(pq_estilos.PROP_RECUO_DESLOCADO):
                fmt.clearProperty(pq_estilos.PROP_RECUO_DESLOCADO)
                fmt.setLeftMargin(max(0.0, recuo_tw) / 15.0)
            return
        total = max(0.0, recuo_tw + extra) / 15.0
        fmt.setLeftMargin(total)
        fmt.setProperty(pq_estilos.PROP_RECUO_DESLOCADO, f"{extra};{total};1")
