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
"""

from __future__ import annotations

import math
from dataclasses import replace

from PySide6.QtCore import QPointF, QRectF, QSizeF
from PySide6.QtGui import QFont, QImage, QTextCursor, QTextDocument

from editdoc.interface.cabecalhos import ConjuntoDeFaixas
from editdoc.modelo.campos import tipo_da_pagina
from editdoc.modelo.pagina import Pagina, pagina_efetiva
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

    def _aplicar(self) -> None:
        self.doc.setPageSize(QSizeF(self.pagina.corpo_largura_tw(),
                                    self.pagina.corpo_altura_tw()))
        self.contexto_campos.hb = self.hb
        self.contexto_campos.pagina = self.pagina_arquivo
        self._chave_campos = None
        ctx = self.flutuantes.contexto
        ctx.pagina, ctx.efetiva, ctx.hb = self.pagina_arquivo, self.pagina, self.hb
        ctx.topos = self.topos()

    def definir_pagina(self, pagina: Pagina) -> None:
        """Troca papel ou margens: o documento e' refeito para o novo corpo."""
        self.pagina_arquivo = pagina
        self.faixas.definir_largura(pagina.corpo_largura_tw())
        self.notas.definir_largura(pagina.corpo_largura_tw())
        self.pagina = self._efetiva()
        self._topos = self._calcular_topos()
        self._efetivas = {}
        self._aplicar()

    def _efetiva(self) -> Pagina:
        cab, rod = self.faixas.alturas(self.pagina_arquivo)
        return pagina_efetiva(self.pagina_arquivo, cab, rod)

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
        altura de corpo (`hb`) em todas."""
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
        chave = (total, self.hb, pagina.formato_numero, pagina.numero_inicial)
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
        """Altura de uma pagina de corpo, em unidades de layout (twips)."""
        return float(self.pagina.corpo_altura_tw())

    def numero_paginas(self) -> int:
        # Paginas a mais (0.1.10): notas de fim e continuacao de notas de rodape depois do texto.
        return max(1, self.doc.pageCount()) + getattr(getattr(self, "notas", None), "extras", 0)

    def pagina_de_y(self, y: float) -> int:
        n = math.floor(y / self.hb)
        return min(max(n, 0), self.numero_paginas() - 1)

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
