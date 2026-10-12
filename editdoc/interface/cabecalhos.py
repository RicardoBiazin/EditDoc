"""Cabecalho e rodape na tela (M5): um QTextDocument por variante, fora do corpo.

Cada variante (cabecalho ou rodape; padrao, primeira ou par) e' um documento proprio,
com o mesmo dispositivo de 1440 dpi do corpo (unidade = twip), largura igual a do
corpo e sem paginacao. Cada um tem o seu desfazer: editar o cabecalho e desfazer
desfaz so' o cabecalho.

O conteudo nao entra no layout do corpo. A visao pinta o cabecalho da pagina na
margem de cima e o rodape na de baixo (`vista_paginas.desenhar_faixas`). Se o
cabecalho cresce alem da margem, o corpo desce: `LayoutPaginado` usa a pagina
efetiva (`modelo.pagina.pagina_efetiva`).

Variante criada so' para editar (duplo clique num cabecalho que o arquivo nao tem) e
deixada vazia nao vai para o arquivo. A que veio do arquivo volta, mesmo vazia.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QFont

from editdoc.modelo.campos import tipo_da_pagina
from editdoc.modelo.documento import TIPOS_DE_FAIXA, Documento
from editdoc.modelo.pagina import Pagina
from editdoc.ponte_qt import campos, de_qt, para_qt
from editdoc.ponte_qt.imagens import DocumentoQt

ONDES = ("cabecalho", "rodape")


class FaixaQt:
    """Uma variante de cabecalho ou rodape: o documento, o contexto dos campos e o dispositivo."""

    def __init__(self, onde: str, tipo: str, fonte: QFont, largura_tw: float,
                 do_arquivo: bool) -> None:
        # Import tardio: layout_paginado importa este modulo.
        from editdoc.interface.layout_paginado import criar_dispositivo_layout
        self.onde = onde
        self.tipo = tipo
        self.do_arquivo = do_arquivo
        self._dispositivo = criar_dispositivo_layout()
        self.doc = DocumentoQt()
        self.doc.setDocumentMargin(0)
        self.doc.setDefaultFont(fonte)
        self.doc.documentLayout().setPaintDevice(self._dispositivo)
        self.doc.setTextWidth(float(largura_tw))
        self.contexto = campos.ContextoDeCampos()
        self.contexto.indice_fixo = 0
        self._manipulador = campos.registrar(self.doc, self.contexto)
        self._preparado: tuple | None = None
        self._tem_campos: bool | None = None
        self.doc.contentsChange.connect(self._mudou)
        self.doc.setModified(False)

    def _mudou(self, *_args) -> None:
        self._tem_campos = None
        self._preparado = None

    def tem_campos(self) -> bool:
        if self._tem_campos is None:
            self._tem_campos = bool(campos.posicoes_de_campos(self.doc, limite=1))
        return self._tem_campos

    def preparar(self, indice: int, total: int, pagina: Pagina) -> None:
        """Deixa o layout com os valores dos campos da pagina `indice`.

        So' refaz o layout se a faixa tem campo e o valor pode ter mudado. O
        markContentsDirty nao entra no desfazer nem marca o documento como alterado.
        """
        ctx = self.contexto
        ctx.indice_fixo = indice
        ctx.total = total
        ctx.pagina = pagina
        chave = (indice, total, pagina.formato_numero, pagina.numero_inicial)
        if chave != self._preparado:
            self._preparado = chave
            if self.tem_campos():
                campos.refazer_campos(self.doc)

    def altura(self) -> float:
        return float(self.doc.documentLayout().documentSize().height())

    def vazia(self) -> bool:
        texto = self.doc.toPlainText()
        return (texto.strip() == "" and chr(0xFFFC) not in texto
                and not self.doc.rootFrame().childFrames())

    def definir_largura(self, largura_tw: float) -> None:
        if abs(self.doc.textWidth() - largura_tw) > 0.5:
            self.doc.setTextWidth(float(largura_tw))
            self._preparado = None

    def fechar(self) -> None:
        if self._dispositivo is not None:
            self.doc.documentLayout().setPaintDevice(None)
            self._dispositivo = None

    def __del__(self) -> None:
        try:
            self.fechar()
        except Exception:  # noqa: BLE001 - destruicao nao pode levantar
            pass


class ConjuntoDeFaixas(QObject):
    """Todas as variantes de cabecalho e rodape de um documento."""

    #: O usuario mudou o conteudo de alguma variante (nao dispara ao carregar).
    alterado = Signal()
    #: Uma variante nova foi criada (quem mostra o desfazer liga os sinais dela).
    criada = Signal(object)

    def __init__(self, fonte: QFont, largura_tw: float, pai: QObject | None = None) -> None:
        super().__init__(pai)
        self._fonte = QFont(fonte)
        self._largura = float(largura_tw)
        self._faixas: dict[tuple[str, str], FaixaQt] = {}
        self._carregando = False

    def _nova(self, onde: str, tipo: str, do_arquivo: bool) -> FaixaQt:
        faixa = FaixaQt(onde, tipo, self._fonte, self._largura, do_arquivo)
        # contentsChanged, e nao contentsChange: este vem antes do layout ser refeito, e a
        # altura lida nele seria a antiga (o corpo desceria uma tecla atrasado).
        faixa.doc.contentsChanged.connect(self._mudou_conteudo)
        self._faixas[(onde, tipo)] = faixa
        self.criada.emit(faixa)
        return faixa

    def _mudou_conteudo(self) -> None:
        if not self._carregando:
            self.alterado.emit()

    def obter(self, onde: str, tipo: str, criar: bool = False) -> FaixaQt | None:
        faixa = self._faixas.get((onde, tipo))
        if faixa is None and criar:
            faixa = self._nova(onde, tipo, do_arquivo=False)
        return faixa

    def da_pagina(self, onde: str, indice: int, pagina: Pagina) -> FaixaQt | None:
        """A variante que aparece na pagina `indice`, ou None se a pagina nao tem."""
        return self._faixas.get((onde, tipo_da_pagina(indice, pagina)))

    def todas(self) -> list[FaixaQt]:
        return list(self._faixas.values())

    def tipos_ativos(self, pagina: Pagina) -> list[str]:
        tipos = ["padrao"]
        if pagina.primeira_diferente:
            tipos.append("primeira")
        if pagina.pares_impares:
            tipos.append("par")
        return tipos

    def alturas(self, pagina: Pagina) -> tuple[float, float]:
        """Maior altura de cabecalho e de rodape entre as variantes que aparecem."""
        saida = []
        for onde in ONDES:
            alturas = [f.altura() for t in self.tipos_ativos(pagina)
                       if (f := self._faixas.get((onde, t))) is not None]
            saida.append(max(alturas, default=0.0))
        return saida[0], saida[1]

    def definir_largura(self, largura_tw: float) -> None:
        self._largura = float(largura_tw)
        for faixa in self._faixas.values():
            faixa.definir_largura(largura_tw)

    def limpar(self) -> None:
        for faixa in self._faixas.values():
            faixa.fechar()
        self._faixas.clear()

    def carregar(self, modelo: Documento) -> None:
        """Troca todas as variantes pelas do modelo. Nao marca nada como alterado."""
        self.limpar()
        self._carregando = True
        try:
            for onde, faixas in (("cabecalho", modelo.cabecalhos), ("rodape", modelo.rodapes)):
                for tipo in TIPOS_DE_FAIXA:
                    if tipo in faixas:
                        faixa = self._nova(onde, tipo, do_arquivo=True)
                        para_qt.preencher_blocos(faixa.doc, faixas[tipo])
        finally:
            self._carregando = False

    def extrair(self) -> tuple[dict, dict]:
        """(cabecalhos, rodapes) para o modelo. Variante nova e vazia nao vai."""
        saida: tuple[dict, dict] = ({}, {})
        for (onde, tipo), faixa in self._faixas.items():
            if not faixa.do_arquivo and faixa.vazia():
                continue
            blocos = de_qt.extrair_blocos(faixa.doc, round(self._largura))
            saida[ONDES.index(onde)][tipo] = blocos
        return saida
