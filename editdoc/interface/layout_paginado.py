"""Layout paginado: um QTextDocument cujo corpo tem o tamanho de uma pagina.

O QTextDocument quebra as linhas pela largura do corpo e empilha as paginas com
pageSize = (largura do corpo, altura do corpo) e documentMargin zero. A pagina n
ocupa, em coordenadas do documento, a faixa vertical [n*hb, (n+1)*hb).

O layout roda num dispositivo de 1440 dpi: uma unidade do Qt vira um twip, a
unidade do .docx. Qualquer outro dpi daria contagem de paginas diferente
(medido no Spike A, 3%).

O QTextEdit nao serve aqui: ele forca pageSize = (largura, -1) e apaga a
paginacao. Por isso o documento e' de um objeto proprio, e a visao e' outra.

O dispositivo fica guardado no objeto. Destrui-lo com um QPainter ativo derruba o
processo (medido no spike, C13): ele vive enquanto o layout viver.

Cabecalho e rodape (M5): ficam em `faixas` (interface/cabecalhos.py), fora do corpo.
Duas paginas: `pagina_arquivo` e' a do arquivo (o que se grava e o que a faixa de
opcoes mostra); `pagina` e' a efetiva, com o corpo empurrado pelo cabecalho ou pelo
rodape que nao cabem na margem.

Altura por pagina (0.1.8): o topo do corpo de cada folha segue o cabecalho DA PAGINA
(primeira, par ou padrao), como no Word: `efetiva_da(n)` e `topo_da_pagina(n)`. O que nao
varia e' a altura do corpo (`hb`): o QTextDocument pagina com um tamanho so', e ela continua
a da pagina efetiva com a maior altura de cabecalho e de rodape (a de menor corpo). Na folha
com cabecalho menor o corpo comeca mais acima e termina mais acima; a capacidade (quantas
linhas cabem) e' a mesma em todas. Limite registrado em docs/ARQUITETURA.md. Toda a geometria
da tela, do PDF, do clique e dos objetos flutuantes usa a efetiva da pagina.

Objetos flutuantes (0.1.7): `flutuantes` (ponte_qt/flutuantes.py) sabe onde o corpo fica na
folha (pagina do arquivo, efetiva e altura do corpo); `atualizar_flutuantes` confere a reserva
de espaco depois de cada mudanca.

Notas (0.1.10): `notas` (interface/notas.py) guarda os documentos das notas, o plano da area
de notas de cada pagina e os espacadores; `atualizar_notas` confere depois de cada mudanca. As
paginas a mais (so' notas, depois do texto) entram em `numero_paginas`.

Campos no corpo: o contexto (`contexto_campos`) diz o total de paginas e a altura do
corpo; quando o total muda, os campos sao medidos de novo (`atualizar_campos`).

Secoes (0.1.12): `secoes` (interface/secoes.py). Com mais de uma secao, cada folha tem o papel,
as margens, a altura do corpo, os cabecalhos e a numeracao da secao dela (`efetiva_da`,
`pagina_da_folha`, `faixa_da_folha`); o QTextDocument pagina na maior altura de corpo (`hb`) e
na maior largura. Com uma secao so', tudo segue o caminho de antes.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPointF, QRectF, QSizeF
from PySide6.QtGui import QFont, QImage, QTextCursor, QTextDocument

from editdoc.interface.cabecalhos import ConjuntoDeFaixas
from editdoc.modelo.campos import tipo_da_pagina
from editdoc.modelo.folhas import MapaFolhas
from editdoc.modelo.pagina import Pagina, com_desvio, pagina_efetiva
from editdoc.ponte_qt import campos
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import flutuantes as pq_flutuantes
from editdoc.ponte_qt.imagens import DocumentoQt

DPI_LAYOUT = 1440


def criar_dispositivo_layout() -> QImage:
    """QImage 1x1 usada so' como dispositivo de layout, a 1440 dpi."""
    img = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
    dpm = round(DPI_LAYOUT / 0.0254)
    img.setDotsPerMeterX(dpm)
    img.setDotsPerMeterY(dpm)
    if img.logicalDpiX() != DPI_LAYOUT:
        raise RuntimeError(f"dispositivo de layout com {img.logicalDpiX()} dpi, "
                           f"esperado {DPI_LAYOUT}")
    return img


def retangulo_cursor_em(doc: QTextDocument, pos: int) -> QRectF:
    """Caret de uma posicao, em coordenadas do documento `doc` (corpo, cabecalho ou rodape).

    Usa blockBoundingRect para a origem: QTextLayout.position() e' relativo dentro de
    celula de tabela (medido no spike, C3).
    """
    cur = QTextCursor(doc)
    cur.setPosition(min(max(pos, 0), doc.characterCount() - 1))
    bloco = cur.block()
    rel = cur.position() - bloco.position()
    lay = bloco.layout()
    linha = lay.lineForTextPosition(rel)
    if not linha.isValid():
        linha = lay.lineAt(lay.lineCount() - 1)
    if not linha.isValid():
        o = doc.documentLayout().blockBoundingRect(bloco).topLeft()
        return QRectF(o.x(), o.y(), 1.0, 1.0)
    x, _ = linha.cursorToX(rel)
    o = doc.documentLayout().blockBoundingRect(bloco).topLeft()
    return QRectF(o.x() + x, o.y() + linha.y(), 1.0, linha.height())


class LayoutPaginado:
    def __init__(self, pagina: Pagina, fonte: str, tamanho_pt: float) -> None:
        self._dispositivo: QImage | None = criar_dispositivo_layout()
        # DocumentoQt acha no registro a imagem colada de outra janela (ponte_qt/imagens.py).
        self.doc: QTextDocument = DocumentoQt()
        self.doc.setDocumentMargin(0)
        padrao = QFont(fonte)
        padrao.setPointSizeF(float(tamanho_pt))
        self.doc.setDefaultFont(padrao)
        self.doc.documentLayout().setPaintDevice(self._dispositivo)
        self.pagina_arquivo = pagina
        self.pagina = pagina
        #: topo do corpo (twips) por tipo de pagina ("primeira", "par", "padrao"), e as
        #: efetivas por tipo (0.1.8)
        self._topos: dict[str, int] = {}
        self._efetivas: dict[str, Pagina] = {}
        self.faixas = ConjuntoDeFaixas(padrao, pagina.corpo_largura_tw())
        self.faixas.doc_estilos = self.doc
        pq_estilos.definir_catalogo_base(self.doc, None)
        # Objetos flutuantes (0.1.7): onde o corpo fica na folha, para a posicao e a reserva.
        self.flutuantes = pq_flutuantes.gerente(self.doc)
        self.flutuantes.contexto = pq_flutuantes.Contexto("corpo")
        self.contexto_campos = campos.ContextoDeCampos()
        self._manipulador_campos = campos.registrar(self.doc, self.contexto_campos)
        self._chave_campos: tuple | None = None
        from editdoc.interface.notas import ConjuntoDeNotas
        self.notas = ConjuntoDeNotas(self)
        # Secoes (0.1.12): cada folha com o papel, os cabecalhos e o numero da secao dela.
        from editdoc.interface.secoes import ConjuntoDeSecoes
        self.faixas.layout = self
        self.secoes = ConjuntoDeSecoes(self)
        # Paginacao como a do Word (0.1.17): compensacao do layout e regras de quebra.
        from editdoc.interface.paginacao import ConjuntoDePaginacao
        self.paginacao = ConjuntoDePaginacao(self)
        self._hb_qt = float(pagina.corpo_altura_tw())
        # Recuo esquerdo negativo (0.1.27): o corpo comeca `desvio` twips antes da margem.
        self.desvio = 0.0
        self.doc._desvio_tw = 0.0
        from editdoc.interface.desvio import ConjuntoDeDesvio
        self.desvio_negativo = ConjuntoDeDesvio(self)
        # Folha x pagina do Qt (0.1.20): toda conversao de y, folha e faixa passa por aqui.
        self.mapa = MapaFolhas(lambda: self.hb)
        self._aplicar()
        # Ajustar fonte e margem marca o documento como alterado. Um documento novo nasce limpo.
        self.doc.setModified(False)

    def definir_fonte_padrao(self, familia: str, pontos: float) -> None:
        """Fonte do texto sem formatacao (o docDefaults do arquivo). Nao suja o documento."""
        fonte = QFont(familia)
        fonte.setPointSizeF(float(pontos))
        modificado = self.doc.isModified()
        self.doc.setDefaultFont(fonte)
        self.doc.setModified(modificado)
        self.faixas.definir_fonte(fonte)
        self.notas.definir_fonte(fonte)

    def _multiplas(self) -> bool:
        secoes = getattr(self, "secoes", None)
        return secoes is not None and secoes.multiplas()

    def _aplicar(self) -> None:
        if self._multiplas():
            largura, altura = self.secoes.dimensoes()
        else:
            largura, altura = (float(self.pagina.corpo_largura_tw()),
                               float(self.pagina.corpo_altura_tw()))
        self._hb_qt = float(altura)
        tamanho = QSizeF(largura, altura)
        if self.doc.pageSize() != tamanho:
            self.doc.setPageSize(tamanho)
        self.contexto_campos.hb = self.hb
        self.contexto_campos.pagina = self.pagina_arquivo
        self.contexto_campos.secoes = self.campos_da_folha if self._multiplas() else None
        self._chave_campos = None
        ctx = self.flutuantes.contexto
        ctx.pagina, ctx.efetiva, ctx.hb = self.pagina_arquivo, self.pagina, self.hb
        ctx.topos = self.topos()
        ctx.folhas = self._folha_para_flutuantes if self._multiplas() else None
        ctx.geracao = self.geracao_das_secoes()

    def aplicar_dimensoes(self) -> None:
        """A geometria das secoes mudou (0.1.12): largura e altura do QTextDocument de novo."""
        self._efetivas = {}
        self._aplicar()

    def geracao_das_secoes(self) -> int:
        secoes = getattr(self, "secoes", None)
        return secoes.geracao if secoes is not None else 0

    def _folha_para_flutuantes(self, n: int) -> tuple[Pagina, Pagina]:
        return self.pagina_da_folha(n), self.efetiva_da(n)

    def atualizar_secoes(self, forcar: bool = False) -> bool:
        """Secoes em dia (0.1.12): estrutura, geometria, quebras derivadas e o mapa de folhas.
        True se a tela muda (quem pinta limpa o cache).

        0.1.17: antes, a compensacao do layout (espaco somado, linha do Word, vazio junto da
        tabela); depois, as regras de quebra do Word (viuvas e orfas, manter com o proximo).
        """
        deslocou = self.desvio_negativo.atualizar()
        compensou = self.paginacao.compensar() or deslocou
        mudou = self.secoes.atualizar(forcar)
        ctx = self.flutuantes.contexto
        ctx.folhas = self._folha_para_flutuantes if self._multiplas() else None
        if ctx.geracao != self.geracao_das_secoes():
            ctx.geracao = self.geracao_das_secoes()
            mudou = True
        if mudou:
            self._chave_campos = None
            self.contexto_campos.secoes = self.campos_da_folha if self._multiplas() else None
        # As secoes mudam formatos (quebras e recuos derivados): a compensacao deles vem ja',
        # senao a pintura seguinte mudaria o layout de novo (a tela com cache ficaria velha).
        compensou = self.paginacao.compensar() or compensou
        if self.paginacao.regras(forcar):
            mudou = True
            self.secoes.atualizar()  # a quebra das regras pode mudar o mapa de folhas
            compensou = self.paginacao.compensar() or compensou
        return mudou or compensou

    def campos_da_folha(self, n: int):
        """(indice na secao, pagina numerada, paginas da secao) da folha n (0.1.12)."""
        return self.secoes.campos_da_folha(n)

    def secao_da_folha(self, n: int) -> int:
        return self.secoes.secao_da_folha(n) if self._multiplas() else 0

    def pagina_da_folha(self, n: int) -> Pagina:
        """O papel e as margens do arquivo da secao da folha n (0.1.12)."""
        if self._multiplas():
            return self.secoes.info_da_folha(n).pagina
        return self.pagina_arquivo

    def tipo_da_folha(self, n: int) -> str:
        """Qual variante de cabecalho vale na folha n: primeira, par ou padrao."""
        if self._multiplas():
            return self.secoes.tipo_da_folha(n)
        return tipo_da_pagina(max(0, int(n)), self.pagina_arquivo)

    def faixa_da_folha(self, onde: str, n: int, criar: bool = False):
        """A variante de cabecalho (ou rodape) da folha n, com a heranca entre secoes."""
        if not self._multiplas():
            return self.faixas.obter(onde, tipo_da_pagina(max(0, int(n)), self.pagina_arquivo),
                                     criar=criar)
        indice = self.secoes.secao_da_folha(n)
        tipo = self.secoes.tipo_da_folha(n)
        achada = self.secoes.faixa_efetiva(indice, onde, tipo)
        if achada is not None:
            return achada[1]
        return self.faixas.obter(onde, tipo, criar=True, secao=indice) if criar else None

    def preparar_faixa(self, faixa, n: int, total: int) -> None:
        """A variante pronta para a folha n: largura do corpo da secao (0.1.12) e campos com o
        numero da folha (com a numeracao da secao)."""
        if self._multiplas():
            ef = self.efetiva_da(n)
            faixa.definir_largura(ef.corpo_largura_tw() - ef.desvio_tw)
            faixa.contexto.secoes = self.campos_da_folha
        else:
            faixa.contexto.secoes = None
        faixa.preparar(n, total, self.pagina_da_folha(n))

    def chave_de_campos_da_folha(self, n: int):
        """O que muda os campos da faixa na folha n (para chave de cache: sem a Pagina)."""
        if not self._multiplas():
            return None
        indice, pagina, paginas = self.campos_da_folha(n)
        return (indice, pagina.numero_inicial, pagina.formato_numero, paginas,
                self.secao_da_folha(n))

    def vinculada(self, secao: int, onde: str, tipo: str) -> bool:
        """A secao usa o cabecalho (ou rodape) `tipo` da anterior ("Vincular ao anterior")."""
        if secao <= 0:
            return False
        secoes = self.secoes.secoes_atuais()
        if secao >= len(secoes):
            return False
        propria = secoes[secao].chaves.get((onde, tipo))
        if propria is None:
            return True
        anterior = self.secoes.faixa_efetiva(secao - 1, onde, tipo, secoes)
        return anterior is not None and anterior[1].ident == propria

    def altura_do_corpo(self, n: int) -> float:
        """Altura do corpo da folha n (0.1.12: a secao pode ser mais baixa que `hb`)."""
        if self._multiplas():
            return float(self.secoes.efetiva_da(n).corpo_altura_tw())
        return self.hb

    def secoes_baixas(self) -> bool:
        return self._multiplas() and self.secoes.baixa()

    def largura_das_notas(self) -> float:
        """Largura das notas de rodape: a do corpo (com secoes, a menor)."""
        if self._multiplas():
            return min(info.largura for info in self.secoes.lista)
        return float(self.pagina.corpo_largura_tw() - self.pagina.desvio_tw)

    def definir_desvio(self, desvio: float) -> None:
        """Recuo esquerdo negativo (0.1.27, `interface/desvio.py`): o corpo do layout comeca
        `desvio` twips antes da margem esquerda, e o documento fica mais largo na mesma medida."""
        self.desvio = float(desvio)
        self.doc._desvio_tw = self.desvio
        self.pagina = self._efetiva()
        self._topos = self._calcular_topos()
        self._efetivas = {}
        self.secoes.calcular(forcar=True)
        self._aplicar()

    def definir_pagina(self, pagina: Pagina) -> None:
        """Troca papel ou margens (da ultima secao, a unica num documento de uma secao): o
        documento e' refeito para o novo corpo."""
        self.pagina_arquivo = pagina
        self.desvio_negativo.conferir_tudo()  # a margem mudou: o teto do desvio tambem
        self.faixas.definir_largura(pagina.corpo_largura_tw())
        self.pagina = self._efetiva()
        self._topos = self._calcular_topos()
        self._efetivas = {}
        self.secoes.calcular(forcar=True)
        self.notas.definir_largura(self.largura_das_notas())
        self._aplicar()

    def definir_pagina_da_secao(self, indice: int, pagina: Pagina) -> None:
        """Papel, orientacao ou margens de uma secao (0.1.12). A ultima e' `definir_pagina`."""
        secoes = self.secoes.secoes_atuais()
        if indice >= len(secoes) - 1:
            self.definir_pagina(pagina)
            return
        secoes[indice].pagina = replace(pagina, pares_impares=self.pagina_arquivo.pares_impares)
        self.desvio_negativo.conferir_tudo()
        self.secoes.calcular(forcar=True)
        self.notas.definir_largura(self.largura_das_notas())
        self._efetivas = {}
        self._aplicar()

    def _efetiva(self) -> Pagina:
        cab, rod = self.faixas.alturas(self.pagina_arquivo)
        return com_desvio(pagina_efetiva(self.pagina_arquivo, cab, rod), round(self.desvio))

    def _calcular_topos(self) -> dict[str, int]:
        """Topo do corpo de cada tipo de pagina, pela altura do cabecalho e do rodape DELA.

        O corpo tem a altura `hb` em todas as folhas; o topo fica onde o Word o poria,
        max(margem de cima, distancia do cabecalho + altura do cabecalho da pagina), sem deixar
        o pe' do corpo passar do rodape da pagina."""
        arquivo = self.pagina_arquivo
        hb = self.pagina.corpo_altura_tw()
        topos = {}
        for tipo in ("primeira", "par", "padrao"):
            alturas = []
            for onde in ("cabecalho", "rodape"):
                faixa = self.faixas.obter(onde, tipo)
                alturas.append(faixa.altura() if faixa is not None else 0.0)
            ef = pagina_efetiva(arquivo, alturas[0], alturas[1])
            topo = min(ef.margem_sup_tw, arquivo.altura_tw - ef.margem_inf_tw - hb)
            topos[tipo] = max(0, topo)
        return topos

    def topos(self) -> tuple:
        """((tipo de pagina, topo do corpo em twips), ...): o que os objetos flutuantes usam."""
        return tuple(sorted(self._topos.items()))

    def efetiva_da(self, n: int) -> Pagina:
        """A pagina efetiva da folha n (0.1.8): o topo do corpo pelo cabecalho dela, a mesma
        altura de corpo (`hb`) em todas. Com secoes (0.1.12), a da secao da folha."""
        if self._multiplas():
            return self.secoes.efetiva_da(n)
        tipo = tipo_da_pagina(max(0, int(n)), self.pagina_arquivo)
        ef = self._efetivas.get(tipo)
        if ef is None:
            base = self.pagina
            topo = self._topos.get(tipo, base.margem_sup_tw)
            if topo == base.margem_sup_tw:
                ef = base
            else:
                ef = replace(base, margem_sup_tw=topo,
                             margem_inf_tw=base.altura_tw - topo - base.corpo_altura_tw())
            self._efetivas[tipo] = ef
        return ef

    def topo_da_pagina(self, n: int) -> float:
        """Y do topo do corpo na folha n, em twips (0.1.8)."""
        return float(self.efetiva_da(n).margem_sup_tw)

    def recalcular_margens(self) -> bool:
        """O cabecalho ou o rodape mudou de altura: o corpo desce ou sobe. True se mudou."""
        if self.secoes.calcular() and self._multiplas():
            self.secoes.mapear()
            self.pagina = self._efetiva()
            self._topos = self._calcular_topos()
            self._efetivas = {}
            self._aplicar()
            return True
        efetiva = self._efetiva()
        topos = None
        if efetiva == self.pagina:
            topos = self._calcular_topos()
            if topos == self._topos:
                return False
        self.pagina = efetiva
        self._topos = topos if topos is not None else self._calcular_topos()
        self._efetivas = {}
        self._aplicar()
        return True

    def atualizar_campos(self) -> bool:
        """Total de paginas ou numeracao mudaram: mede de novo os campos do corpo.

        True se algum campo foi marcado para refazer (quem pinta limpa o cache).
        """
        ctx = self.contexto_campos
        total = self.numero_paginas()
        pagina = self.pagina_arquivo
        chave = (total, self.hb, pagina.formato_numero, pagina.numero_inicial,
                 self.geracao_das_secoes(),
                 tuple((i.inicio, i.paginas, i.numero_inicial) for i in self.secoes.lista)
                 if self._multiplas() else ())
        if chave == self._chave_campos:
            return False
        self._chave_campos = chave
        ctx.total, ctx.hb, ctx.pagina = total, self.hb, pagina
        posicoes = campos.posicoes_de_campos(self.doc)
        if not posicoes:
            return False
        campos.refazer_campos(self.doc, posicoes)
        return True

    def atualizar_notas(self) -> bool:
        """Espacadores, numeros e area das notas em dia (0.1.10). True se a tela muda."""
        return self.notas.atualizar()

    def paginas_do_texto(self) -> int:
        """As paginas do corpo (sem as paginas a mais, so' de notas)."""
        return max(1, self.doc.pageCount())

    def atualizar_flutuantes(self) -> bool:
        """Reserva dos objetos flutuantes e linhas ao lado deles em dia (0.1.7). True se o
        layout mudou (quem pinta limpa o cache)."""
        return self.flutuantes.atualizar()

    @property
    def hb(self) -> float:
        """Altura de uma pagina do QTextDocument, em unidades de layout (twips): a do corpo, ou
        (0.1.12) a maior altura de corpo entre as secoes."""
        if self._multiplas():
            return self._hb_qt
        return float(self.pagina.corpo_altura_tw())

    def numero_paginas(self) -> int:
        # Paginas a mais (0.1.10): notas de fim e continuacao de notas de rodape depois do texto.
        return max(1, self.doc.pageCount()) + getattr(getattr(self, "notas", None), "extras", 0)

    def pagina_de_y(self, y: float) -> int:
        """Folha do ponto y do documento (0.1.20: pela camada `mapa`)."""
        return self.mapa.folha_de_y(y, self.numero_paginas())

    def origem_bloco(self, bloco) -> QPointF:
        """Origem absoluta do bloco em coordenadas do documento.

        Usa blockBoundingRect: QTextLayout.position() e' relativo dentro de celula
        de tabela, e daria posicoes erradas (medido no spike, C3).
        """
        return QPointF(self.doc.documentLayout().blockBoundingRect(bloco).topLeft())

    def retangulo_cursor(self, pos: int) -> QRectF:
        """Caret de uma posicao, em coordenadas do documento."""
        return retangulo_cursor_em(self.doc, pos)

    def retangulo_imagem(self, pos: int) -> QRectF | None:
        """Retangulo da imagem cujo caractere esta' em `pos`, em coordenadas do documento.

        A imagem fica na linha de base: o topo e' a base da linha menos a altura dela.
        O formato guarda o tamanho em px96; o layout e' em twips (x15).
        """
        cur = QTextCursor(self.doc)
        if pos < 0 or pos >= self.doc.characterCount() - 1:
            return None
        cur.setPosition(pos)
        cur.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
        if cur.selectedText() != chr(0xFFFC):
            return None
        # Pelo fragmento, nao pelo cursor (armadilha do charFormat com selecao no fim do bloco).
        from editdoc.ponte_qt import links as pq_links
        from editdoc.ponte_qt import opacos as pq_opacos
        fmt = pq_links.formato_em(self.doc, pos) or cur.charFormat()
        if fmt.isImageFormat():
            altura = fmt.toImageFormat().height() * 15.0
            largura_fmt = fmt.toImageFormat().width() * 15.0
        elif pq_opacos.eh_opaco(fmt) and fmt.objectIndex() < 0:
            # Objeto preservado na linha (0.1.9): caixa, forma ou objeto com tamanho tem alcas
            # como a imagem. O flutuante e a etiqueta (equacao, sem tamanho) nao.
            obj = pq_opacos.objeto_de(fmt)
            if obj is None or obj.flutuante or obj.tipo == "equacao" or not obj.largura_emu:
                return None
            tam, etiqueta = pq_opacos.tamanho(self.doc, fmt)
            if etiqueta or tam.height() <= 0:
                return None
            altura, largura_fmt = tam.height(), tam.width()
        else:
            return None
        bloco = self.doc.findBlock(pos)
        rel = pos - bloco.position()
        lay = bloco.layout()
        linha = lay.lineForTextPosition(rel)
        if not linha.isValid():
            return None
        x0, _ = linha.cursorToX(rel)
        x1, _ = linha.cursorToX(rel + 1)
        o = self.origem_bloco(bloco)
        largura = abs(x1 - x0) or largura_fmt
        topo = o.y() + linha.y() + linha.ascent() - altura
        return QRectF(o.x() + min(x0, x1), topo, largura, altura)

    def pagina_do_cursor(self, pos: int) -> int:
        return self.pagina_de_y(self.retangulo_cursor(pos).center().y())

    def ajustar_para_pagina(self, pos: int, n: int) -> int:
        """Leva uma posicao vizinha ao texto mais proximo da pagina n.

        O hit-test do Qt (FuzzyHit) manda um clique no espaco em branco do fim da
        pagina n para a primeira linha da pagina n+1 (medido, C11). Aqui andamos
        pelo texto ate cair na pagina n.
        """
        cur = QTextCursor(self.doc)
        cur.setPosition(pos)
        for _ in range(400):
            pg = self.pagina_do_cursor(cur.position())
            if pg == n:
                return cur.position()
            if pg > n:
                cur.movePosition(QTextCursor.MoveOperation.StartOfLine)
                if cur.position() == 0:
                    return 0
                cur.movePosition(QTextCursor.MoveOperation.Left)
            else:
                cur.movePosition(QTextCursor.MoveOperation.EndOfLine)
                if not cur.movePosition(QTextCursor.MoveOperation.Right):
                    return cur.position()
        return cur.position()

    def fechar(self) -> None:
        """Solta o dispositivo antes de o documento morrer."""
        if self._dispositivo is not None:
            self.faixas.limpar()
            self.notas.limpar()
            self.doc.documentLayout().setPaintDevice(None)
            self._dispositivo = None

    def __del__(self) -> None:
        # Sem isto o Python pode soltar o dispositivo antes do documento, que ainda
        # aponta para ele (ver a nota no topo do modulo).
        try:
            self.fechar()
        except Exception:  # noqa: BLE001 - destruicao nao pode levantar
            pass
