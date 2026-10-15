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

Secoes (0.1.12): cada variante tem um id (`FaixaQt.ident`) e as secoes apontam para os ids que
declaram (`Secao.chaves`, no registro do corpo, `ponte_qt/secoes.py`). A secao que nao declara
usa a da anterior (`ConjuntoDeSecoes.faixa_efetiva`), como no Word; duas secoes que citam a
mesma parte do arquivo apontam para a mesma variante (editar uma edita a outra, "Vincular ao
anterior"). A largura da variante e' a do corpo da secao da folha pintada.
"""

from __future__ import annotations

import itertools

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QFont

from editdoc.modelo.campos import tipo_da_pagina
from editdoc.modelo.documento import TIPOS_DE_FAIXA, Documento
from editdoc.modelo.pagina import Pagina
from editdoc.ponte_qt import campos, de_qt, para_qt
from editdoc.ponte_qt import flutuantes as pq_flutuantes
from editdoc.ponte_qt.imagens import DocumentoQt

ONDES = ("cabecalho", "rodape")
#: Numero de serie de cada FaixaQt (0.1.8): a chave do cache da tela nao confia em id().
_SERIE = itertools.count(1)


class FaixaQt:
    """Uma variante de cabecalho ou rodape: o documento, o contexto dos campos e o dispositivo."""

    def __init__(self, onde: str, tipo: str, fonte: QFont, largura_tw: float,
                 do_arquivo: bool, ident: str = "") -> None:
        # Import tardio: layout_paginado importa este modulo.
        from editdoc.interface.layout_paginado import criar_dispositivo_layout
        self.onde = onde
        self.tipo = tipo
        self.do_arquivo = do_arquivo
        self.ident = ident
        self._alturas: dict = {}
        self.serie = next(_SERIE)
        self._dispositivo = criar_dispositivo_layout()
        self.doc = DocumentoQt()
        self.doc.setDocumentMargin(0)
        self.doc.setDefaultFont(fonte)
        self.doc.documentLayout().setPaintDevice(self._dispositivo)
        self.doc.setTextWidth(float(largura_tw))
        self.contexto = campos.ContextoDeCampos()
        self.contexto.indice_fixo = 0
        self._manipulador = campos.registrar(self.doc, self.contexto)
        # Objetos flutuantes (0.1.7): a origem na folha muda com a altura e a pagina pintada.
        self.flutuantes = pq_flutuantes.gerente(self.doc)
        self.flutuantes.contexto = pq_flutuantes.Contexto(onde)
        self._preparado: tuple | None = None
        self._tem_campos: bool | None = None
        self.doc.contentsChange.connect(self._mudou)
        self.doc.setModified(False)

    def _mudou(self, *_args) -> None:
        self._tem_campos = None
        self._preparado = None
        self._alturas = {}

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
        chave = (indice, total, pagina.formato_numero, pagina.numero_inicial,
                 ctx.secoes(indice) if ctx.secoes is not None else None)
        if chave != self._preparado:
            self._preparado = chave
            if self.tem_campos():
                campos.refazer_campos(self.doc)

    def posicionar(self, pagina: Pagina, efetiva: Pagina, indice: int) -> None:
        """Onde a faixa fica na folha (0.1.7): a referencia dos objetos flutuantes dela."""
        ctx = self.flutuantes.contexto
        ctx.pagina, ctx.efetiva, ctx.indice = pagina, efetiva, indice
        x = float(pagina.margem_esq_tw)
        if self.onde == "cabecalho":
            y = float(pagina.cabecalho_tw)
        else:
            y = float(pagina.altura_tw - pagina.rodape_tw - self.altura())
        ctx.origem = (x, y)

    def altura(self) -> float:
        return float(self.doc.documentLayout().documentSize().height())

    def altura_na_largura(self, largura_tw: float) -> float:
        """Altura com a largura do corpo de uma secao (0.1.12): a mesma variante pode valer em
        secoes de larguras diferentes. Em cache pela revisao do documento."""
        largura = float(largura_tw)
        if abs(self.doc.textWidth() - largura) <= 0.5:
            return self.altura()
        chave = (self.doc.revision(), round(largura))
        h = self._alturas.get(chave)
        if h is None:
            anterior = self.doc.textWidth()
            self.doc.setTextWidth(largura)
            h = self.altura()
            self.doc.setTextWidth(anterior)
            if len(self._alturas) > 16:
                self._alturas.clear()
            self._alturas[chave] = h
        return h

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
        #: id -> variante (0.1.12; ate' a 0.1.11 a chave era (onde, tipo), uma secao so')
        self._faixas: dict[str, FaixaQt] = {}
        self._ids = itertools.count(1)
        self._carregando = False
        #: O documento do corpo: cabecalho e rodape usam o catalogo de estilos dele (M6).
        self.doc_estilos = None
        #: O layout do corpo (0.1.12): as secoes dizem qual variante vale em cada folha.
        self.layout = None

    def _nova(self, onde: str, tipo: str, do_arquivo: bool) -> FaixaQt:
        ident = f"f{next(self._ids)}"
        faixa = FaixaQt(onde, tipo, self._fonte, self._largura, do_arquivo, ident)
        if self.doc_estilos is not None:
            faixa.doc._doc_estilos = self.doc_estilos
        # contentsChanged, e nao contentsChange: este vem antes do layout ser refeito, e a
        # altura lida nele seria a antiga (o corpo desceria uma tecla atrasado).
        faixa.doc.contentsChanged.connect(self._mudou_conteudo)
        self._faixas[ident] = faixa
        self.criada.emit(faixa)
        return faixa

    def _mudou_conteudo(self) -> None:
        if not self._carregando:
            self.alterado.emit()

    def por_id(self, ident: str | None) -> FaixaQt | None:
        return self._faixas.get(ident) if ident else None

    def _secoes(self) -> list:
        if self.layout is None:
            return []
        return self.layout.secoes.secoes_atuais()

    def obter(self, onde: str, tipo: str, criar: bool = False,
              secao: int | None = None) -> FaixaQt | None:
        """A variante (onde, tipo) que vale na secao `secao` (padrao: a ultima), com a heranca.

        `criar`: se nenhuma secao ate' ali declara, cria e declara na primeira secao (como o
        Word: com "Vincular ao anterior", o cabecalho novo e' o da primeira secao da cadeia)."""
        secoes = self._secoes()
        if not secoes:
            achada = next((f for f in self._faixas.values()
                           if f.onde == onde and f.tipo == tipo), None)
            return achada if achada is not None or not criar else \
                self._nova(onde, tipo, do_arquivo=False)
        indice = len(secoes) - 1 if secao is None else min(max(0, secao), len(secoes) - 1)
        achada = self.layout.secoes.faixa_efetiva(indice, onde, tipo, secoes)
        if achada is not None:
            return achada[1]
        if not criar:
            return None
        faixa = self._nova(onde, tipo, do_arquivo=False)
        secoes[0].chaves[(onde, tipo)] = faixa.ident
        return faixa

    def da_pagina(self, onde: str, indice: int, pagina: Pagina = None) -> FaixaQt | None:
        """A variante que aparece na folha `indice`, ou None se a folha nao tem."""
        if self.layout is not None:
            return self.layout.faixa_da_folha(onde, indice)
        return self.obter(onde, tipo_da_pagina(indice, pagina))

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
        """Maior altura de cabecalho e de rodape entre as variantes que aparecem na ultima
        secao."""
        saida = []
        for onde in ONDES:
            alturas = [f.altura() for t in self.tipos_ativos(pagina)
                       if (f := self.obter(onde, t)) is not None]
            saida.append(max(alturas, default=0.0))
        return saida[0], saida[1]

    def definir_fonte(self, fonte: QFont) -> None:
        """Fonte padrao do documento (docDefaults): vale para as variantes novas e as que existem."""
        self._fonte = QFont(fonte)
        for faixa in self._faixas.values():
            faixa.doc.setDefaultFont(self._fonte)
            faixa.doc.setModified(False)

    def definir_largura(self, largura_tw: float) -> None:
        self._largura = float(largura_tw)
        for faixa in self._faixas.values():
            faixa.definir_largura(largura_tw)

    def limpar(self) -> None:
        for faixa in self._faixas.values():
            faixa.fechar()
        self._faixas.clear()

    def carregar(self, modelo: Documento, secoes_qt: list | None = None) -> None:
        """Troca todas as variantes pelas do modelo. Nao marca nada como alterado.

        `secoes_qt` (0.1.12): as secoes do registro do corpo, na ordem das do modelo (a ultima no
        fim); recebem em `chaves` os ids das variantes que declaram. Duas secoes que citam a
        mesma parte (a mesma chave do arquivo) com o mesmo conteudo ficam com a mesma variante."""
        from editdoc.modelo.secoes import secoes_de
        self.limpar()
        self._carregando = True
        feitas: list[tuple] = []  # (onde, chave do arquivo, blocos, id)
        try:
            secoes = secoes_de(modelo)
            for i, secao in enumerate(secoes):
                destino = secoes_qt[i] if secoes_qt is not None and i < len(secoes_qt) else None
                novas = {}
                for onde, faixas in (("cabecalho", secao.cabecalhos), ("rodape", secao.rodapes)):
                    for tipo in TIPOS_DE_FAIXA:
                        if tipo not in faixas:
                            continue
                        chave = secao.chaves.get((onde, tipo))
                        repetida = next((fid for o, c, b, fid in feitas if o == onde and
                                         chave is not None and c == chave and b == faixas[tipo]),
                                        None)
                        if repetida is not None:
                            novas[(onde, tipo)] = repetida
                            continue
                        faixa = self._nova(onde, tipo, do_arquivo=True)
                        faixa.doc._pagina_flutuantes = secao.pagina
                        faixa.definir_largura(secao.pagina.corpo_largura_tw())
                        faixa.posicionar(secao.pagina, secao.pagina, 0)
                        para_qt.preencher_blocos(faixa.doc, faixas[tipo])
                        feitas.append((onde, chave, faixas[tipo], faixa.ident))
                        novas[(onde, tipo)] = faixa.ident
                if destino is not None:
                    destino.chaves = novas
        finally:
            self._carregando = False

    def blocos_de(self, ident: str):
        """Os blocos da variante para o modelo; None se e' nova e ficou vazia (nao vai)."""
        faixa = self._faixas.get(ident)
        if faixa is None or (not faixa.do_arquivo and faixa.vazia()):
            return None
        return de_qt.extrair_blocos(faixa.doc, round(faixa.doc.textWidth() or self._largura))

    def faixas_da_secao(self, chaves: dict) -> tuple[dict, dict, dict]:
        """(cabecalhos, rodapes, chaves) que uma secao declara, para o modelo."""
        cabecalhos: dict = {}
        rodapes: dict = {}
        saida_chaves: dict = {}
        for (onde, tipo), fid in chaves.items():
            blocos = self.blocos_de(fid)
            if blocos is None:
                continue
            (cabecalhos if onde == "cabecalho" else rodapes)[tipo] = blocos
            saida_chaves[(onde, tipo)] = fid
        return cabecalhos, rodapes, saida_chaves

    def extrair(self) -> tuple[dict, dict]:
        """(cabecalhos, rodapes) que a ultima secao declara (sem a heranca). Variante nova e
        vazia nao vai."""
        secoes = self._secoes()
        if secoes:
            cab, rod, _c = self.faixas_da_secao(secoes[-1].chaves)
            return cab, rod
        saida: tuple[dict, dict] = ({}, {})
        for faixa in self._faixas.values():
            blocos = self.blocos_de(faixa.ident)
            if blocos is not None:
                saida[ONDES.index(faixa.onde)][faixa.tipo] = blocos
        return saida

    def copiar(self, faixa: FaixaQt, onde: str, tipo: str) -> FaixaQt:
        """Variante nova com o conteudo de `faixa` (desvincular do anterior, como o Word)."""
        nova = self._nova(onde, tipo, do_arquivo=False)
        blocos = de_qt.extrair_blocos(faixa.doc, round(faixa.doc.textWidth() or self._largura))
        self._carregando = True
        try:
            nova.definir_largura(faixa.doc.textWidth())
            para_qt.preencher_blocos(nova.doc, blocos)
        finally:
            self._carregando = False
        return nova
