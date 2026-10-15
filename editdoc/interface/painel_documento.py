"""Painel de edicao: a API do QTextEdit que os comandos usam, sobre a visao em paginas.

Os nomes ficam os do QTextEdit (textCursor, setTextCursor, document, undo, mergeCurrentCharFormat,
...) de proposito: formatacao, estado, busca, faixa e janela chamam esses nomes, e a
troca da visao provisoria pela visao em paginas (M3) nao reescreve nenhum deles.

Quem implementa aqui o caret, o teclado, o mouse, a selecao, o clipboard e o desfazer.
A pintura e' da VistaPaginas. Decisao e numeros em docs/SPIKES.md (Gate do M3): o
QTextEdit oculto, compartilhando o documento, troca o pageSize e apaga a paginacao.

Formato de digitacao: sem selecao, mergeCurrentCharFormat e setCurrentCharFormat mudam o
formato do PROXIMO caractere digitado, nao o da palavra sob o caret (medido com
QTextEdit antes de escrever isto).

Edicao do cabecalho e do rodape (M5), no lugar, como no Word: duplo clique na margem
de cima (ou de baixo) entra; duplo clique no corpo, ou Esc, sai. Na edicao o cursor
(`_cursor`) e' do documento da variante, e `document()` devolve esse documento: os
comandos de formatacao, tabela, imagem e busca continuam iguais. O corpo e' sempre
`documento_corpo()`; e' ele que a janela grava e que diz se ha' alteracao. Cada
variante tem o proprio desfazer.

Hiperlinks (0.1.3): Ctrl+clique abre o link (`abrir_link`, com `abrir_url` e
`confirmar_link` trocaveis nos testes); digitar logo depois de um link nao o estende; as
setas, o Backspace e o Delete pulam a marca (sem largura) dos marcadores.

Listas (0.1.4, edicao/listas.py): Tab e Shift+Tab no inicio de um item mudam o nivel; Enter
num item vazio sobe um nivel ou sai da lista; Backspace no inicio do item tira o numero (e,
de novo, o recuo). Copiar leva as listas dos blocos numa marca propria da area de
transferencia (MIME_LISTAS), e colar no EditDoc devolve os blocos as listas.

Caixa de texto (0.1.5, interface/dialogo_caixa.py): duplo clique na caixa, Enter com a caixa
selecionada ou "Editar texto da caixa" no menu de contexto abrem o editor do texto dela.

Propriedades preservadas (0.1.5, ponte_qt/propriedades.py): copiar leva os extras dos trechos
e dos blocos (realce, tabulacoes, bordas...) em MIME_PROPRIEDADES, e colar no EditDoc os
devolve. Digitar herda o formato do vizinho e o Enter copia o do bloco, com os extras juntos.

Comentarios (0.1.6, edicao/comentarios.py): apagar uma selecao com ancoras segue a regra do
Word (`_remover_selecao`): o comentario cujo trecho inteiro (ou a referencia) foi apagado vai
junto; o que perdeu so' uma ponta fica ancorado no que sobrou. As ancoras nao tem largura e
o teclado as pula, como as dos marcadores. `comentariosAlterados` avisa o painel lateral.

Notas (0.1.10, interface/notas.py, edicao/notas.py): clicar na area de notas do pe' da pagina
edita a nota no lugar (`entrar_na_nota`): `document()` passa a ser o documento da nota, como no
cabecalho; Esc, clique no corpo ou duplo clique no numero da nota voltam ao corpo. A edicao da
nota e' um passo de desfazer do corpo (a sessao, ver interface/notas.py); dentro dela o
Ctrl+Z desfaz as teclas da nota. Desfazer e refazer no corpo passam pelos ajustes do
espacador da area de notas junto com o passo do usuario. Duplo clique na marca da nota leva a
nota. Copiar leva as notas da selecao (MIME_NOTAS, so' no mesmo processo); colar cria notas
novas com os mesmos conteudos.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace

from PySide6.QtCore import QMimeData, QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QDesktopServices, QImage, QKeyEvent, QKeySequence,
                           QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
                           QTextDocumentFragment, QTextFormat)
from PySide6.QtWidgets import QApplication, QMenu

from editdoc.edicao import comentarios as ed_comentarios
from editdoc.edicao import estilos as ed_estilos
from editdoc.edicao import imagens as ed_imagens
from editdoc.edicao import links as ed_links
from editdoc.edicao import listas as ed_listas
from editdoc.edicao import tabelas as ed_tabelas
from editdoc.interface.cabecalhos import FaixaQt
from editdoc.interface.vista_paginas import VistaPaginas, origem_da_faixa
from editdoc.interface.layout_paginado import LayoutPaginado, retangulo_cursor_em
from editdoc.modelo.campos import tipo_da_pagina
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.folhas import escala_do_zoom
from editdoc.modelo.pagina import Pagina


def _com_geometria(base: Pagina, fonte: Pagina) -> Pagina:
    """`base` com as margens de `fonte` (Aplicar a: Documento inteiro, no dialogo das margens;
    o papel e a orientacao de cada secao ficam)."""
    return base.com_margens(fonte.margem_sup_tw, fonte.margem_inf_tw, fonte.margem_esq_tw,
                            fonte.margem_dir_tw)
from editdoc.ponte_qt import campos as pq_campos
from editdoc.ponte_qt import comentarios as pq_comentarios
from editdoc.ponte_qt import imagens as pq_imagens
from editdoc.ponte_qt import links as pq_links
from editdoc.ponte_qt import listas as pq_listas
from editdoc.ponte_qt import marcas as pq_marcas
from editdoc.ponte_qt import notas as pq_notas
from editdoc.ponte_qt import secoes as pq_secoes
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import opacos as pq_opacos
from editdoc.ponte_qt import propriedades as pq_props
from editdoc.ponte_qt.para_qt import PROP_ESTRUTURAL

Mover = QTextCursor.MoveMode.MoveAnchor
Selecionar = QTextCursor.MoveMode.KeepAnchor
M = QTextCursor.MoveOperation
Key = Qt.Key
Ctrl = Qt.KeyboardModifier.ControlModifier
Alt = Qt.KeyboardModifier.AltModifier
Shift = Qt.KeyboardModifier.ShiftModifier
_QUEBRA = QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore
_SEM_QUEBRA = QTextFormat.PageBreakFlag.PageBreak_Auto
#: Propriedades de imagem que nao podem passar para o texto digitado depois dela.
_PROPS_IMAGEM = (QTextFormat.Property.ObjectType, QTextFormat.Property.ImageName,
                 QTextFormat.Property.ImageWidth, QTextFormat.Property.ImageHeight,
                 QTextFormat.Property.TextToolTip)
_IMG_HTML = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
#: Lado da alca de redimensionar imagem, em pixels de tela.
ALCA_PX = 8.0
#: Marca na area de transferencia: quantos objetos opacos ficaram fora da copia (0.1.2).
MIME_OPACOS_OMITIDOS = "application/x-editdoc-objetos-omitidos"
#: Marca na area de transferencia: as listas dos blocos copiados, em JSON (0.1.4).
MIME_LISTAS = "application/x-editdoc-listas"
#: Marca na area de transferencia: os extras de run e de paragrafo copiados, em JSON (0.1.5).
MIME_PROPRIEDADES = "application/x-editdoc-propriedades"
#: Marca na area de transferencia: as notas da selecao (0.1.10), chaves do registro em JSON.
MIME_NOTAS = "application/x-editdoc-notas"
#: Esquemas de endereco que o Ctrl+clique nunca abre (o link pode rodar codigo).
ESQUEMAS_PROIBIDOS = ("javascript", "vbscript", "data")


def abrir_no_sistema(url: str) -> bool:
    """Abre o endereco no programa padrao do Windows (navegador, e-mail)."""
    return QDesktopServices.openUrl(QUrl(url, QUrl.ParsingMode.TolerantMode))


def html_sem_imagens_de_fora(html: str) -> str:
    """Tira do HTML colado as imagens que nao vieram do EditDoc.

    Uma <img src="file:..."> ou "http:..." faria o Qt ler um arquivo local ou ficar
    com um quadro vazio. A imagem de fora entra pelo caminho da imagem (QImage), nao
    pelo HTML.
    """
    prefixo = f'src="{pq_imagens.ESQUEMA}:'
    return _IMG_HTML.sub(lambda m: m.group(0) if prefixo in m.group(0) else "", html)


class PainelDocumento(VistaPaginas):
    textChanged = Signal()
    cursorPositionChanged = Signal()
    currentCharFormatChanged = Signal(QTextCharFormat)
    undoAvailable = Signal(bool)
    redoAvailable = Signal(bool)
    copyAvailable = Signal(bool)
    paginaAlterada = Signal()
    #: Recado curto para a barra de status (imagem recusada ao colar, por exemplo).
    mensagem = Signal(str)
    #: Entrou ou saiu da edicao do cabecalho e do rodape (a faixa mostra a aba propria).
    modoFaixaAlterado = Signal()
    #: Os comentarios mudaram (0.1.6): o painel lateral redesenha.
    comentariosAlterados = Signal()

    def __init__(self, fonte: str, tamanho: float, parent=None) -> None:
        layout = LayoutPaginado(Pagina(), fonte, float(tamanho))
        super().__init__(layout, parent)
        self._acoes: list[QAction] = []
        self._acoes_contexto: list[QAction] = []
        self._acoes_quebra: list[QAction] = []
        self._acao_posicao: QAction | None = None
        self._cursor = QTextCursor(layout.doc)
        self._arrastando = False
        #: Arrasto de alca de imagem: (posicao, canto, retangulo inicial na tela) ou None.
        self._redim: tuple[int, str, QRectF] | None = None
        self._redim_atual: QRectF | None = None
        #: Cabecalho ou rodape em edicao (None = corpo), a pagina onde se edita, e o
        #: cursor do corpo guardado durante a edicao.
        self._edicao: FaixaQt | None = None
        #: Nota em edicao (0.1.10): a NotaQt de interface/notas.py, ou None.
        self._nota_ed = None
        self._pagina_edicao = 0
        self._cursor_corpo: QTextCursor | None = None
        #: Arraste de objeto flutuante (0.1.9): mover ou redimensionar, com o contorno fantasma.
        self._arraste: dict | None = None
        # O cursor do mouse muda sobre o objeto selecionado e as alcas (mover, redimensionar).
        self.viewport().setMouseTracking(True)
        doc = layout.doc
        doc.contentsChanged.connect(self.textChanged)
        self._ligar_desfazer(doc)
        layout.faixas.criada.connect(lambda faixa: self._ligar_desfazer(faixa.doc))
        layout.faixas.alterado.connect(self._faixa_alterada)

    # ----- API do QTextEdit usada pelos comandos -------------------------
    def document(self) -> QTextDocument:
        """O documento que o teclado edita: o corpo, ou o cabecalho (ou a nota) em edicao."""
        if self._nota_ed is not None:
            return self._nota_ed.doc
        return self._edicao.doc if self._edicao is not None else self.layout_pag.doc

    def _no_corpo(self) -> bool:
        """O teclado edita o corpo (nem cabecalho, nem rodape, nem nota)."""
        return self._edicao is None and self._nota_ed is None

    def editando_nota(self):
        """A nota em edicao (NotaQt), ou None (0.1.10)."""
        return self._nota_ed

    def documento_corpo(self) -> QTextDocument:
        """O corpo, sempre (o que se grava e o que diz se ha' alteracao)."""
        return self.layout_pag.doc

    def textCursor(self) -> QTextCursor:
        return QTextCursor(self._cursor)

    def setTextCursor(self, cursor: QTextCursor) -> None:
        self._cursor = QTextCursor(cursor)
        self._depois_de_mover()

    def moveCursor(self, operacao, modo=Mover) -> None:
        self._cursor.movePosition(operacao, modo)
        self._depois_de_mover()

    def toPlainText(self) -> str:
        return self.layout_pag.doc.toPlainText()

    def setPlainText(self, texto: str) -> None:
        """Como o QTextEdit: o cursor vai para o inicio e o desfazer e' zerado."""
        self.sair_da_faixa()
        self.layout_pag.doc.setPlainText(texto)
        self._cursor = QTextCursor(self.layout_pag.doc)
        self._depois_de_mover()

    def insertPlainText(self, texto: str) -> None:
        self._inserir(texto)

    def clear(self) -> None:
        self.sair_da_faixa()
        self.layout_pag.doc.clear()
        self._cursor = QTextCursor(self.layout_pag.doc)
        self._depois_de_mover()

    def undo(self) -> None:
        doc = self.document()
        if doc.isUndoAvailable():
            antes = self._assinatura_comentarios()
            if doc is self.layout_pag.doc:
                # Notas (0.1.10): o ajuste do espacador sai junto com o passo do usuario.
                self.layout_pag.notas.desfazer(doc, self._cursor)
            else:
                doc.undo(self._cursor)
            self._depois_do_desfazer(antes)

    def redo(self) -> None:
        doc = self.document()
        if doc.isRedoAvailable():
            antes = self._assinatura_comentarios()
            if doc is self.layout_pag.doc:
                self.layout_pag.notas.refazer(doc, self._cursor)
            else:
                doc.redo(self._cursor)
            self._depois_do_desfazer(antes)

    def _assinatura_comentarios(self):
        return (pq_comentarios.assinatura(self.documento_corpo())[:2],
                pq_notas.assinatura(self.documento_corpo()))

    def _depois_do_desfazer(self, antes) -> None:
        if self._assinatura_comentarios() != antes:
            # O catalogo de comentarios voltou (0.1.6): o realce e o painel mudam junto.
            self._limpar_cache()
            self.comentariosAlterados.emit()
        self._depois_de_mover()

    def _remover_selecao(self) -> None:
        """Apaga a selecao; com ancoras de comentario, pela regra do Word (0.1.6)."""
        if not self._no_corpo() or not ed_comentarios.remover_selecao(self._cursor):
            self._cursor.removeSelectedText()
        else:
            self._limpar_cache()
            self.comentariosAlterados.emit()

    def selectAll(self) -> None:
        self._cursor.select(QTextCursor.SelectionType.Document)
        self._depois_de_mover()

    def copy(self) -> None:
        if not self._cursor.hasSelection():
            return
        frag = QTextDocumentFragment(self._cursor)
        md = QMimeData()
        md.setHtml(_html_sem_espacador(frag))
        # O HTML do Qt nao leva o objeto opaco (caixa de texto, forma...): ele fica fora do
        # que se cola. A marca deixa o colar avisar, em vez de sumir calado.
        inicio, fim = self._cursor.selectionStart(), self._cursor.selectionEnd()
        omitidos = sum(1 for pos in pq_opacos.posicoes_de_opacos(self.document())
                       if inicio <= pos < fim)
        if omitidos:
            md.setData(MIME_OPACOS_OMITIDOS, str(omitidos).encode("ascii"))
        listas = ed_listas.dados_para_copiar(self.document(), inicio, fim)
        if listas is not None:
            import json
            md.setData(MIME_LISTAS, json.dumps(listas).encode("utf-8"))
        extras = pq_props.dados_para_copiar(self.document(), inicio, fim)
        if extras is not None:
            import json
            md.setData(MIME_PROPRIEDADES, json.dumps(extras).encode("utf-8"))
        md.setText(frag.toPlainText().replace(chr(0xFFFC), ""))
        if self._no_corpo():
            from editdoc.edicao import notas as ed_notas
            notas = ed_notas.dados_para_copiar(self.document(), inicio, fim)
            if notas is not None:
                import json
                md.setData(MIME_NOTAS, json.dumps(notas).encode("utf-8"))
        pos = ed_imagens.imagem_selecionada(self)
        if pos is not None:
            # So' a imagem selecionada: outro programa recebe a imagem, nao o HTML.
            fmt = ed_imagens.formato_em(self.document(), pos)
            registro = pq_imagens.dados_de(fmt.name()) if fmt is not None else None
            if registro is not None:
                # Resolucao cheia para o outro programa; a previa so' se nao puder decodificar.
                dims = mod_imagem.dimensoes(registro[0])
                inteira = QImage.fromData(registro[0]) if dims and mod_imagem.decodificavel(*dims) \
                    else QImage()
                md.setImageData(inteira if not inteira.isNull() else pq_imagens.previa(registro[0]))
        QApplication.clipboard().setMimeData(md)

    def cut(self) -> None:
        self.copy()
        if self._cursor.hasSelection():
            self._remover_selecao()
            self._depois_de_mover()

    def paste(self) -> None:
        md = QApplication.clipboard().mimeData()
        if md is None:
            return
        if md.hasHtml():
            html = html_sem_imagens_de_fora(md.html())
            frag = QTextDocumentFragment.fromHtml(html)
            if not frag.toPlainText().strip() and md.hasImage():
                self._colar_imagem(md)  # navegador: <img> de fora mais a propria imagem
                return
        elif md.hasImage():
            self._colar_imagem(md)
            return
        else:
            frag = QTextDocumentFragment.fromPlainText(md.text())
        self._cursor.beginEditBlock()
        if self._cursor.hasSelection():
            self._remover_selecao()
        self._limpar_estrutural()
        inicio_colado = self._cursor.position()
        no_inicio_vazio = self._cursor.block().length() <= 1
        self._cursor.insertFragment(frag)
        self._cursor.endEditBlock()
        # A tabela colada so' aparece em childFrames() depois do endEditBlock (medido). O
        # ajuste entra no mesmo passo de desfazer pelo joinPreviousEditBlock.
        self._cursor.joinPreviousEditBlock()
        ed_tabelas.ajustar_tabelas_coladas(self)
        if md.hasFormat(MIME_PROPRIEDADES):
            # Extras (0.1.5): realce, tabulacoes, bordas... voltam ao que foi colado.
            import json
            try:
                dado = json.loads(bytes(md.data(MIME_PROPRIEDADES)).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                dado = None
            if isinstance(dado, dict):
                pq_props.aplicar_colado(self.document(), dado, inicio_colado,
                                        self._cursor.position(), no_inicio_vazio)
        if not md.hasFormat(MIME_LISTAS):
            # HTML de outro programa com <ol>/<ul>: vira lista do EditDoc (0.1.4).
            ed_listas.converter_listas_coladas(self, inicio_colado, self._cursor.position())
        if md.hasFormat(MIME_LISTAS):
            # Listas (0.1.4): os blocos colados voltam para as listas que tinham.
            import json
            try:
                dado = json.loads(bytes(md.data(MIME_LISTAS)).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                dado = None
            if isinstance(dado, dict):
                ed_listas.aplicar_colado(self, dado, inicio_colado, self._cursor.position(),
                                         no_inicio_vazio)
        if md.hasFormat(MIME_NOTAS) and self._no_corpo():
            # Notas (0.1.10): as referencias voltam ao texto colado, com notas novas.
            import json
            from editdoc.edicao import notas as ed_notas
            try:
                dado = json.loads(bytes(md.data(MIME_NOTAS)).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                dado = None
            if isinstance(dado, dict):
                ed_notas.aplicar_colado(self.document(), dado, inicio_colado,
                                        self._cursor.position())
        self._cursor.endEditBlock()
        self._depois_de_mover()
        if md.hasFormat(MIME_OPACOS_OMITIDOS):
            self.mensagem.emit("Caixas de texto, formas e outros objetos preservados não são "
                               "copiados nesta versão: o texto foi colado sem eles.")

    def _colar_imagem(self, md: QMimeData) -> None:
        try:
            ed_imagens.inserir_qimage(self, md.imageData())
        except ed_imagens.ImagemRecusada as erro:
            self.mensagem.emit(str(erro))

    def mergeCurrentCharFormat(self, formato: QTextCharFormat) -> None:
        self._cursor.mergeCharFormat(formato)
        self._depois_de_formato()

    def currentCharFormat(self) -> QTextCharFormat:
        return QTextCharFormat(self._cursor.charFormat())

    def setCurrentCharFormat(self, formato: QTextCharFormat) -> None:
        self._cursor.setCharFormat(formato)
        self._depois_de_formato()

    def registrar_atalhos(self, acoes: list[QAction]) -> None:
        self._acoes = list(acoes)

    def registrar_menu_contexto(self, acoes: list[QAction]) -> None:
        """Acoes extras do menu de contexto (tabela, imagem). So' as habilitadas aparecem."""
        self._acoes_contexto = list(acoes)

    def registrar_menu_objeto(self, quebras: list[QAction], posicao: QAction) -> None:
        """Menu de contexto do objeto selecionado (0.1.9): "Quebra de texto" e "Posicao e
        tamanho"."""
        self._acoes_quebra = list(quebras)
        self._acao_posicao = posicao

    def imagem_selecionada(self) -> int | None:
        """Posicao da imagem selecionada (selecao de exatamente uma imagem), ou None."""
        return ed_imagens.imagem_selecionada(self)

    # ----- pagina ---------------------------------------------------------
    def secao_atual(self) -> int:
        """Indice da secao do cursor (0.1.12); na edicao do cabecalho, a da folha editada."""
        lay = self.layout_pag
        if not self._no_corpo():
            return lay.secao_da_folha(self._pagina_edicao)
        return lay.secoes.indice_da_posicao(self._cursor.position()) \
            if len(lay.secoes.secoes_atuais()) > 1 else 0

    def total_de_secoes(self) -> int:
        return len(self.layout_pag.secoes.secoes_atuais())

    def configuracao_pagina(self) -> Pagina:
        """A pagina do arquivo (sem o corpo empurrado pelo cabecalho) da secao do cursor (0.1.12;
        com uma secao so', a do documento)."""
        lay = self.layout_pag
        secoes = lay.secoes.secoes_atuais()
        if len(secoes) <= 1:
            return lay.pagina_arquivo
        indice = self.secao_atual()
        if indice >= len(secoes) - 1:
            return lay.pagina_arquivo
        return replace(secoes[indice].pagina, pares_impares=lay.pagina_arquivo.pares_impares)

    def definir_pagina_final(self, pagina: Pagina) -> None:
        """A pagina da ultima secao (ao abrir: a do w:sectPr do fim do corpo)."""
        self.layout_pag.definir_pagina(pagina)
        self._depois_de_mudar_pagina()

    def definir_configuracao_pagina(self, pagina: Pagina, documento_inteiro: bool = False) -> None:
        """Papel, orientacao, margens ou cabecalho da secao do cursor (0.1.12; "Aplicar a: Esta
        seção"). `documento_inteiro`: as margens em todas as secoes. Pares e
        impares vale para o documento. Refaz a paginacao; nao mexe no texto."""
        lay = self.layout_pag
        secoes = lay.secoes.secoes_atuais()
        if len(secoes) <= 1:
            lay.definir_pagina(pagina)
            self._depois_de_mudar_pagina()
            return
        final = lay.pagina_arquivo
        if pagina.pares_impares != final.pares_impares:
            final = replace(final, pares_impares=pagina.pares_impares)
        if documento_inteiro:
            for i, secao in enumerate(secoes[:-1]):
                secao.pagina = _com_geometria(secao.pagina, pagina)
            final = _com_geometria(final, pagina)
            lay.definir_pagina(final)
        else:
            indice = self.secao_atual()
            if indice >= len(secoes) - 1:
                lay.definir_pagina(replace(pagina, pares_impares=final.pares_impares))
            else:
                if final != lay.pagina_arquivo:
                    lay.definir_pagina(final)
                lay.definir_pagina_da_secao(indice, pagina)
        self._depois_de_mudar_pagina()

    def _depois_de_mudar_pagina(self) -> None:
        self.layout_pag.atualizar_secoes(forcar=True)
        self._limpar_cache()
        self._altura_doc_anterior = None
        self._atualizar_geometria()
        if self._edicao is not None:
            # "Primeira pagina diferente" ou "pares e impares" trocam a variante da pagina.
            self._trocar_faixa(self._edicao.onde, self._pagina_edicao)
        else:
            self.garantir_visivel(self.layout_pag.retangulo_cursor(self._cursor.position()))
        self.paginaAlterada.emit()
        self.viewport().update()

    def total_de_paginas(self) -> int:
        return self.layout_pag.numero_paginas()

    def pagina_atual(self) -> int:
        """Pagina do caret, a partir de 0. Na edicao do cabecalho, a pagina editada."""
        if not self._no_corpo():
            return self._pagina_edicao
        return self.layout_pag.pagina_do_cursor(self._cursor.position())

    # ----- cabecalho e rodape (M5) ----------------------------------------
    def editando_faixa(self) -> FaixaQt | None:
        """A variante de cabecalho ou rodape em edicao, ou None."""
        return self._edicao

    def carregar_faixas(self, modelo) -> None:
        """Cabecalhos e rodapes do modelo (ao abrir). Sai da edicao antes. Com secoes (0.1.12),
        cada secao do registro do corpo recebe os ids das variantes que declara."""
        self.sair_da_faixa()
        lay = self.layout_pag
        lay.faixas.carregar(modelo, lay.secoes.secoes_atuais())
        self._recalcular_margens()

    def faixas_do_modelo(self) -> tuple[dict, dict]:
        """(cabecalhos, rodapes) da ultima secao para gravar."""
        return self.layout_pag.faixas.extrair()

    def completar_secoes(self, modelo) -> None:
        """Os cabecalhos e rodapes de cada secao no modelo extraido (0.1.12): o que cada uma
        declara, pelas chaves que o `de_qt` trouxe do registro. A ultima secao vai em
        `modelo.cabecalhos`/`modelo.rodapes`/`modelo.secao.chaves`."""
        faixas = self.layout_pag.faixas
        pares = self.layout_pag.pagina_arquivo.pares_impares
        for bloco in modelo.paragrafos:
            secao = getattr(bloco, "secao", None)
            if secao is None:
                continue
            secao.cabecalhos, secao.rodapes, secao.chaves = faixas.faixas_da_secao(secao.chaves)
            secao.pagina = replace(secao.pagina, pares_impares=pares)
        modelo.cabecalhos, modelo.rodapes, modelo.secao.chaves = \
            faixas.faixas_da_secao(modelo.secao.chaves)

    def entrar_na_faixa(self, onde: str, indice: int | None = None,
                        ponto: QPointF | None = None) -> None:
        """Edita o cabecalho (ou rodape) da pagina `indice` (padrao: a do caret)."""
        if indice is None:
            indice = self.pagina_atual()
        indice = min(max(int(indice), 0), self._paginas() - 1)
        if self._no_corpo():
            self._cursor_corpo = QTextCursor(self._cursor)
        self._trocar_faixa(onde, indice, ponto)

    def estado_do_vinculo(self) -> bool | None:
        """Na edicao do cabecalho (ou rodape) de uma secao que tem anterior (0.1.12): True se ela
        usa o da anterior ("Vincular ao anterior"); None fora disso."""
        if self._edicao is None:
            return None
        lay = self.layout_pag
        if not lay.secoes.multiplas():
            return None
        secao = lay.secao_da_folha(self._pagina_edicao)
        if secao <= 0:
            return None
        return lay.vinculada(secao, self._edicao.onde, lay.tipo_da_folha(self._pagina_edicao))

    def alternar_vinculo(self) -> bool:
        """Liga ou desliga "Vincular ao anterior" no cabecalho (ou rodape) em edicao, como o
        Word: desligar copia o da anterior para a secao; ligar apaga o proprio da secao (com
        confirmacao, se ele tem texto) e passa a usar o da anterior. True se mudou."""
        estado = self.estado_do_vinculo()
        if estado is None:
            return False
        lay = self.layout_pag
        n = self._pagina_edicao
        onde = self._edicao.onde
        tipo = lay.tipo_da_folha(n)
        secao = lay.secao_da_folha(n)
        secoes = lay.secoes.secoes_atuais()
        if estado:
            atual = lay.secoes.faixa_efetiva(secao, onde, tipo, secoes)
            if atual is not None:
                nova = lay.faixas.copiar(atual[1], onde, tipo)
            else:
                nova = lay.faixas.obter(onde, tipo, criar=False) or \
                    lay.faixas._nova(onde, tipo, do_arquivo=False)
            secoes[secao].chaves[(onde, tipo)] = nova.ident
        else:
            propria = lay.faixas.por_id(secoes[secao].chaves.get((onde, tipo)))
            from editdoc.interface import dialogos_modais  # import tardio: so' quando se pergunta
            if propria is not None and not propria.vazia() and not \
                    dialogos_modais.confirmar_vincular_anterior(self):
                return False
            secoes[secao].chaves.pop((onde, tipo), None)
        lay.secoes.calcular(forcar=True)
        self._trocar_faixa(onde, n)
        self._recalcular_margens()
        self.modoFaixaAlterado.emit()
        self._limpar_cache()
        self.viewport().update()
        return True

    def _trocar_faixa(self, onde: str, indice: int, ponto: QPointF | None = None) -> None:
        self.layout_pag.atualizar_secoes()
        faixa = self.layout_pag.faixa_da_folha(onde, indice, criar=True)
        mesma = faixa is self._edicao
        self._edicao = faixa
        self._pagina_edicao = indice
        if ponto is not None:
            pos = self._posicao_na_faixa(faixa, indice, ponto)
            self._cursor = QTextCursor(faixa.doc)
            self._cursor.setPosition(pos)
        elif not mesma:
            self._cursor = QTextCursor(faixa.doc)
        self._recalcular_margens()
        self._repassar_estado_do_desfazer()
        self.modoFaixaAlterado.emit()
        self._depois_de_mover()

    def preparar_notas_ao_abrir(self) -> None:
        """Documento recem-aberto (0.1.10): area de notas e espacadores feitos, desfazer zerado e
        documento sem alteracao."""
        doc = self.layout_pag.doc
        # Secoes (0.1.12): quebras e recuos derivados antes de zerar o desfazer.
        self.layout_pag.atualizar_secoes(forcar=True)
        self.layout_pag.atualizar_notas()
        self.layout_pag.atualizar_secoes()
        doc.clearUndoRedoStacks()
        doc.setModified(False)
        self.layout_pag.notas.zerar_desfazer()
        self._limpar_cache()
        self._altura_doc_anterior = None
        self._atualizar_geometria()

    def entrar_na_nota(self, nota, pos: int | None = None) -> None:
        """Edita a nota no lugar (0.1.10), com o cursor em `pos` (padrao: o fim do texto)."""
        if self._edicao is not None:
            self.sair_da_faixa()
        if self._nota_ed is not None and self._nota_ed is not nota:
            self.layout_pag.notas.concluir_sessao()
        elif self._no_corpo():
            self._cursor_corpo = QTextCursor(self._cursor)
        if self._nota_ed is not nota:
            self.layout_pag.notas.iniciar_sessao(nota)
            if not getattr(nota.doc, "_desfazer_ligado", False):
                nota.doc._desfazer_ligado = True
                self._ligar_desfazer(nota.doc)
        self._nota_ed = nota
        self._cursor = QTextCursor(nota.doc)
        fim = nota.doc.characterCount() - 1
        self._cursor.setPosition(fim if pos is None else min(max(pos, 0), fim))
        achado = self.layout_pag.notas.caret(nota, self._cursor.position())
        if achado is not None:
            self._pagina_edicao = achado[0]
        self._repassar_estado_do_desfazer()
        self.modoFaixaAlterado.emit()
        self._depois_de_mover()

    def sair_da_faixa(self) -> None:
        """Volta ao corpo, com o cursor onde estava. Sem efeito fora da edicao."""
        if self._nota_ed is not None:
            self._nota_ed = None
            mudou = self.layout_pag.notas.concluir_sessao()
            cursor = self._cursor_corpo
            self._cursor_corpo = None
            self._cursor = QTextCursor(cursor) if cursor is not None else \
                QTextCursor(self.layout_pag.doc)
            if mudou:
                self._limpar_cache()
            self._repassar_estado_do_desfazer()
            self.modoFaixaAlterado.emit()
            self._depois_de_mover()
            return
        if self._edicao is None:
            return
        self._edicao = None
        cursor = self._cursor_corpo
        self._cursor_corpo = None
        self._cursor = QTextCursor(cursor) if cursor is not None else QTextCursor(self.layout_pag.doc)
        self._recalcular_margens()
        self._repassar_estado_do_desfazer()
        self.modoFaixaAlterado.emit()
        self._depois_de_mover()

    def _ligar_desfazer(self, doc: QTextDocument) -> None:
        """Desfazer e refazer de cada documento chegam a janela so' quando ele e' o ativo."""
        doc.undoAvailable.connect(lambda v, d=doc: d is self.document() and self.undoAvailable.emit(v))
        doc.redoAvailable.connect(lambda v, d=doc: d is self.document() and self.redoAvailable.emit(v))

    def _repassar_estado_do_desfazer(self) -> None:
        doc = self.document()
        self.undoAvailable.emit(doc.isUndoAvailable())
        self.redoAvailable.emit(doc.isRedoAvailable())

    def _faixa_alterada(self) -> None:
        """O usuario mudou um cabecalho ou rodape: o documento fica alterado, e o corpo
        pode descer (cabecalho mais alto que a margem)."""
        self.layout_pag.doc.setModified(True)
        self._recalcular_margens()
        self.viewport().update()

    def _recalcular_margens(self) -> None:
        if self.layout_pag.recalcular_margens():
            self._limpar_cache()
            self._altura_doc_anterior = None
            self._atualizar_geometria()
            self.paginaAlterada.emit()
        self.viewport().update()

    def _faixa_editada(self):
        if self._edicao is None:
            return None
        return self._edicao, self._cursor

    def _origem_da_faixa_na_tela(self, faixa: FaixaQt, n: int) -> tuple[float, float, float]:
        """(x, y, escala): o ponto (0, 0) do documento da faixa na pagina n, na tela."""
        m = self._mapa()
        x, y, _w, _h = m.folha_na_tela(n)
        self.layout_pag.preparar_faixa(faixa, n, self._paginas())
        ox, oy = origem_da_faixa(self.layout_pag.pagina_da_folha(n), faixa.onde, faixa.altura())
        return x + ox * m.escala, y + oy * m.escala, m.escala

    def _posicao_na_faixa(self, faixa: FaixaQt, n: int, p: QPointF) -> int:
        x, y, escala = self._origem_da_faixa_na_tela(faixa, n)
        pos = faixa.doc.documentLayout().hitTest(
            QPointF((p.x() - x) / escala, (p.y() - y) / escala), Qt.FuzzyHit)
        return min(max(pos, 0), faixa.doc.characterCount() - 1)

    def zona_em(self, p: QPointF) -> tuple[str, int]:
        """("cabecalho" | "rodape" | "corpo", pagina) do ponto do viewport.

        O limite e' o da pagina efetiva: o cabecalho que empurrou o corpo continua
        cabecalho ate' onde o corpo comeca.
        """
        m = self._mapa()
        n_total = self._paginas()
        n = m.pagina_no_ponto(p.x(), p.y(), n_total)
        x, y, largura, altura = m.folha_na_tela(n)
        tx, ty = (p.x() - x) / m.escala, (p.y() - y) / m.escala
        efetiva = self.layout_pag.efetiva_da(n)  # a da pagina (0.1.8): o topo varia por pagina
        if 0 <= tx <= efetiva.largura_tw and 0 <= ty <= efetiva.altura_tw:
            if ty < efetiva.margem_sup_tw:
                return "cabecalho", n
            if ty > efetiva.altura_tw - efetiva.margem_inf_tw:
                return "rodape", n
        return "corpo", n

    def _nota_editada(self):
        if self._nota_ed is None:
            return None
        return self._nota_ed, self._cursor

    def _retangulo_do_caret(self, m, n_total: int) -> QRectF | None:
        if self._nota_ed is not None:
            achado = self.layout_pag.notas.caret(self._nota_ed, self._cursor.position())
            if achado is None:
                return None
            n, r = achado
            self._pagina_edicao = n
            x, y = m.doc_para_tela(r.x(), r.y(), n_total)
            return QRectF(x, y, 1.0, r.height() * m.escala)
        if self._edicao is None:
            return super()._retangulo_do_caret(m, n_total)
        x, y, escala = self._origem_da_faixa_na_tela(self._edicao, self._pagina_edicao)
        c = retangulo_cursor_em(self._edicao.doc, self._cursor.position())
        return QRectF(x + c.x() * escala, y + c.y() * escala, 1.0, c.height() * escala)

    def _garantir_visivel_na_tela(self, r: QRectF) -> None:
        vp = self.viewport()
        vb = self.verticalScrollBar()
        if r.top() < 0:
            vb.setValue(vb.value() + math.floor(r.top()) - 16)
        elif r.bottom() > vp.height():
            vb.setValue(vb.value() + math.ceil(r.bottom() - vp.height()) + 16)
        self.viewport().update()

    def ir_para_posicao(self, pos: int) -> None:
        """Leva o caret a `pos` do corpo e rola ate' la' (painel de navegacao, M6)."""
        self.sair_da_faixa()
        doc = self.layout_pag.doc
        self._cursor = QTextCursor(doc)
        self._cursor.setPosition(min(max(int(pos), 0), doc.characterCount() - 1))
        r = self.layout_pag.retangulo_cursor(self._cursor.position())
        m = self._mapa()
        _x, y = m.doc_para_tela(r.x(), r.y(), self._paginas())
        # O titulo vai para perto do alto da tela, como no Word.
        vb = self.verticalScrollBar()
        vb.setValue(vb.value() + math.floor(y) - 24)
        self._depois_de_mover()
        self.setFocus()

    def recuos_do_paragrafo(self) -> tuple[int, int]:
        """(recuo esquerdo, recuo da primeira linha) do paragrafo do caret, em twips.

        Os recuos horizontais ficam em twips no formato do bloco (0.1.4, ponte_qt/estilos.py);
        no item de lista, a primeira linha e' a de verdade, nao a que poe o texto depois do numero.
        """
        bf = self._cursor.block().blockFormat()
        real = pq_listas.recuo_real(bf)
        return round(bf.leftMargin()), real if real is not None else 0

    def definir_recuos_do_paragrafo(self, esquerdo_tw: int, primeira_tw: int) -> None:
        """Um passo de desfazer: recuos do paragrafo do caret."""
        bf = QTextBlockFormat(self._cursor.blockFormat())
        bf.setLeftMargin(max(0.0, float(esquerdo_tw)))
        bf.setTextIndent(float(primeira_tw))
        bf.clearProperty(pq_listas.PROP_RECUO_REAL)  # o item de lista ajusta o visual depois
        self._cursor.beginEditBlock()
        self._cursor.setBlockFormat(bf)
        self._cursor.endEditBlock()
        self._depois_de_formato()

    def inserir_quebra_de_pagina(self) -> None:
        """Ctrl+Enter: o texto depois do caret comeca no topo da proxima pagina.

        Dentro de tabela, e no cabecalho e no rodape, vira Enter comum: o EditDoc nao
        quebra pagina dentro de celula, e cabecalho nao tem pagina.
        """
        self._quebrar(quebra=self._cursor.currentTable() is None and self._no_corpo())

    # ----- estado e sinais internos ----------------------------------------
    def _depois_de_mover(self) -> None:
        self.mostrar_caret_agora()
        if not self._no_corpo():
            r = self._retangulo_do_caret(self._mapa(), self._paginas())
            if r is not None:
                self._garantir_visivel_na_tela(r)
        else:
            self.garantir_visivel(self.layout_pag.retangulo_cursor(self._cursor.position()))
        self.copyAvailable.emit(self._cursor.hasSelection())
        self.cursorPositionChanged.emit()
        self.currentCharFormatChanged.emit(self.currentCharFormat())
        self.viewport().update()

    def _depois_de_formato(self) -> None:
        self.currentCharFormatChanged.emit(self.currentCharFormat())
        self.viewport().update()

    def _posicao_caret(self) -> int | None:
        return self._cursor.position()

    def _selecao_atual(self) -> QTextCursor | None:
        # Na edicao do cabecalho a selecao e' do cabecalho (desenhar_faixas a pinta).
        return self._cursor if self._no_corpo() else None

    def _posicao_imagem_selecionada(self) -> int | None:
        # As alcas de imagem sao do corpo; no cabecalho, o tamanho muda pelo dialogo.
        return self.objeto_na_linha_selecionado() if self._no_corpo() else None

    def objeto_na_linha_selecionado(self) -> int | None:
        """A imagem, ou o objeto preservado na linha com tamanho (caixa, forma: 0.1.9),
        selecionado sozinho. E' o que ganha as quatro alcas de redimensionar."""
        pos = self.imagem_selecionada()
        if pos is not None:
            return pos
        c = self._cursor
        if not self._no_corpo() or not c.hasSelection() or \
                c.selectionEnd() - c.selectionStart() != 1:
            return None
        pos = c.selectionStart()
        return pos if self.layout_pag.retangulo_imagem(pos) is not None else None

    def _retangulo_redimensionando(self) -> QRectF | None:
        return self._redim_atual

    def _estrutural(self) -> bool:
        return bool(self._cursor.blockFormat().property(PROP_ESTRUTURAL))

    def _limpar_estrutural(self) -> None:
        """O bloco estrutural (o que o Qt exige antes da tabela) que recebe conteudo vira
        paragrafo comum: sem isto, apagado de novo, ele sumiria do arquivo."""
        if self._estrutural():
            bf = QTextBlockFormat(self._cursor.blockFormat())
            bf.clearProperty(PROP_ESTRUTURAL)
            self._cursor.setBlockFormat(bf)

    def _inserir(self, texto: str) -> None:
        # Selecao com ancora de comentario (0.1.6): apagar e digitar sao um passo so'.
        estrutural = self._estrutural() or (self._cursor.hasSelection() and self._no_corpo())
        if estrutural:
            self._cursor.beginEditBlock()
        if self._cursor.hasSelection():
            self._remover_selecao()
        self._limpar_estrutural()
        formato = self._cursor.charFormat()
        # Logo depois de um link, o texto digitado nao entra no link (0.1.3).
        para_digitar = ed_links.formato_para_digitar(self.document(), self._cursor.position(),
                                                     formato)
        if pq_notas.eh_nota(formato):
            # Depois da marca da nota (0.1.10): o texto nao sai sobrescrito nem com o estilo da
            # referencia; vem o formato do texto de antes da marca.
            limpo = ed_links_formato_antes_da_nota(self.document(), self._cursor.position())
            self._cursor.insertText(texto, limpo)
        elif formato.isImageFormat() or pq_campos.eh_campo(formato) or pq_opacos.eh_opaco(formato) \
                or pq_marcas.eh_marca(formato) or pq_secoes.eh_quebra(formato):
            # Digitar logo depois de uma imagem, de um campo, de um objeto opaco ou de uma
            # marca (ou da quebra de secao, 0.1.12): o texto nao herda o formato de objeto
            # (cada letra viraria outro objeto).
            limpo = QTextCharFormat(para_digitar)
            for propriedade in (*_PROPS_IMAGEM, *pq_campos.PROPS_DE_CAMPO,
                                *pq_opacos.PROPS_DE_OPACO, *pq_marcas.PROPS_DE_MARCA,
                                *pq_secoes.PROPS_DE_QUEBRA):
                limpo.clearProperty(propriedade)
            self._cursor.insertText(texto, limpo)
        elif para_digitar is not formato:
            self._cursor.insertText(texto, para_digitar)
        else:
            self._cursor.insertText(texto)
        if estrutural:
            self._cursor.endEditBlock()
        self._depois_de_mover()

    def caixa_selecionada(self) -> int | None:
        """Posicao da caixa de texto selecionada sozinha, ou ao lado do caret (0.1.5)."""
        from editdoc.interface import dialogo_caixa
        doc = self.document()
        c = self._cursor
        if c.hasSelection():
            if c.selectionEnd() - c.selectionStart() == 1 and \
                    dialogo_caixa.caixa_em(doc, c.selectionStart()) is not None:
                return c.selectionStart()
            return None
        for k in (c.position(), c.position() - 1):
            if dialogo_caixa.caixa_em(doc, k) is not None:
                return k
        return None

    def editar_caixa(self, pos: int | None = None) -> bool:
        """Abre o editor do texto da caixa de texto (0.1.5). True se o texto mudou."""
        from editdoc.interface import dialogo_caixa
        pos = self.caixa_selecionada() if pos is None else pos
        if pos is None:
            return False
        mudou = dialogo_caixa.editar(self, pos)
        if mudou:
            self._limpar_cache()
            self._depois_de_mover()
            self.viewport().update()
        return mudou

    def _quebrar(self, quebra: bool) -> None:
        if not quebra and self._cursor.hasSelection() and \
                self._cursor.selectionEnd() - self._cursor.selectionStart() == 1 and \
                self.caixa_selecionada() is not None:
            # Enter com a caixa de texto selecionada: edita o texto dela (0.1.5).
            self.editar_caixa()
            return
        if not quebra and ed_listas.enter_em_item_vazio(self):
            # Enter num item de lista vazio: sobe um nivel ou sai da lista, como no Word.
            return
        self._cursor.beginEditBlock()
        if self._cursor.hasSelection():
            self._remover_selecao()
        self._limpar_estrutural()
        # Enter no fim de um Titulo: o paragrafo novo usa o estilo seguinte (`next`) (M6).
        no_fim = self._cursor.atBlockEnd() and self._cursor.currentTable() is None
        bf = QTextBlockFormat(self._cursor.blockFormat())
        bf.clearProperty(pq_notas.PROP_QUEBRA_NOTA)  # o espacador das notas nao passa adiante
        bf.clearProperty(pq_secoes.PROP_QUEBRA_SECAO)  # nem a quebra derivada da secao (0.1.12)
        bf.setPageBreakPolicy(_QUEBRA if quebra else _SEM_QUEBRA)
        bf.clearProperty(pq_listas.PROP_SAIU_DA_LISTA)  # a marca do Backspace nao passa adiante
        proximo = ed_estilos.formatos_do_proximo(self.document(), bf) if no_fim else None
        self._cursor.insertBlock(bf)
        if proximo is not None:
            bloco_fmt, car_fmt = proximo
            self._cursor.setBlockFormat(bloco_fmt)
            self._cursor.setBlockCharFormat(car_fmt)
            self._cursor.setCharFormat(car_fmt)
        self._cursor.endEditBlock()
        self._depois_de_mover()

    def _tab_na_tabela(self, para_tras: bool) -> None:
        """Tab vai para a proxima celula e seleciona o conteudo dela, como no Word.
        Na ultima celula, Tab cria uma linha no fim. Shift+Tab volta."""
        tabela = self._cursor.currentTable()
        celula = tabela.cellAt(self._cursor)
        alvo = ed_tabelas.proxima_celula(tabela, celula, para_tras)
        if alvo is None:
            if not para_tras:
                ed_tabelas.acrescentar_linha_no_fim(self)
            return
        inicio = alvo.firstCursorPosition().position()
        fim = alvo.lastCursorPosition().position()
        self._cursor.setPosition(inicio)
        if fim > inicio:
            self._cursor.setPosition(fim, Selecionar)
        self._depois_de_mover()

    def _tab_na_lista(self, para_tras: bool) -> bool:
        """Tab (ou Shift+Tab) no inicio de um item de lista, ou com varios itens
        selecionados: muda o nivel (0.1.4). False se nao e' o caso (a tecla segue)."""
        c = self._cursor
        doc = self.document()
        if c.hasSelection():
            primeiro = doc.findBlock(c.selectionStart())
            ultimo = doc.findBlock(c.selectionEnd())
            if primeiro == ultimo:
                return False
        elif not c.atBlockStart():
            return False
        if not ed_listas.eh_item(self, c.block() if not c.hasSelection()
                                 else doc.findBlock(c.selectionStart())):
            return False
        return ed_listas.mudar_nivel(self, -1 if para_tras else 1)

    def _marcador_em(self, pos: int) -> bool:
        """O caractere em `pos` e' a marca (sem largura) de um marcador (0.1.3)."""
        cf = pq_links.formato_em(self.document(), pos)
        return cf is not None and pq_marcas.eh_marcador(cf)

    def _objeto_com_quadro(self, pos: int) -> bool:
        """O caractere em `pos` e' um objeto flutuante que reserva espaco (float do Qt)."""
        if pos < 0 or pos >= self.document().characterCount() - 1:
            return False
        cf = pq_links.formato_em(self.document(), pos)
        return cf is not None and pq_opacos.eh_opaco(cf) and cf.objectIndex() >= 0

    def _mover_horizontal(self, direita: bool, modo) -> None:
        """Seta para os lados. A marca de marcador nao tem largura: o caret passa por ela
        junto com o caractere vizinho, senao a tecla pareceria nao fazer nada. A quebra de
        secao (0.1.12) e' a marca do paragrafo: o caret nunca fica depois dela."""
        op = M.Right if direita else M.Left
        self._cursor.movePosition(op, modo)
        for _ in range(256):
            pos = self._cursor.position()
            if not self._marcador_em(pos - 1 if direita else pos):
                break
            if not self._cursor.movePosition(op, modo):
                break
        if self._depois_da_quebra(self._cursor.position()):
            self._cursor.movePosition(op, modo)
        self._depois_de_mover()

    def _secao_em(self, pos: int) -> bool:
        """O caractere em `pos` e' a quebra de secao (0.1.12), no corpo."""
        if not self._no_corpo() or pos < 0 or pos >= self.document().characterCount() - 1:
            return False
        cf = pq_links.formato_em(self.document(), pos)
        return cf is not None and pq_secoes.id_de(cf) is not None

    def _depois_da_quebra(self, pos: int) -> bool:
        """`pos` e' o fim do paragrafo logo depois da quebra de secao: lugar onde o caret nao
        fica (seria depois da marca do paragrafo)."""
        if not self._no_corpo() or pos <= 0:
            return False
        bloco = self.document().findBlock(pos)
        return pos == bloco.position() + bloco.length() - 1 and self._secao_em(pos - 1)

    def _antes_da_quebra(self) -> None:
        """O caret (sem selecao) que caiu depois da quebra de secao volta para antes dela."""
        if not self._cursor.hasSelection() and self._depois_da_quebra(self._cursor.position()):
            self._cursor.setPosition(self._cursor.position() - 1)

    def inserir_quebra_de_secao(self, tipo: str) -> bool:
        """Layout > Quebras > Quebra de secao (0.1.12): o paragrafo se parte no cursor; a
        primeira parte termina numa secao nova com as propriedades da secao do cursor (papel,
        margens, cabecalhos: "Vincular ao anterior" ligado, como no Word), e o texto depois do
        cursor comeca como `tipo` diz (nextPage, continuous, evenPage, oddPage). Um passo de
        desfazer. Fora do corpo ou dentro de tabela nao ha' quebra de secao: False."""
        if not self._no_corpo() or self._cursor.currentTable() is not None:
            if hasattr(self, "mensagem"):
                self.mensagem.emit("A quebra de seção só pode ficar no corpo do texto, "
                                   "fora de tabela.")
            return False
        doc = self.layout_pag.doc
        secoes = self.layout_pag.secoes
        c = self._cursor
        c.beginEditBlock()
        if c.hasSelection():
            self._remover_selecao()
        self._limpar_estrutural()
        # O cursor fica antes de uma quebra de secao que o paragrafo ja' termine.
        fim_quebra = pq_secoes.posicao_da_quebra_no_bloco(c.block())
        if fim_quebra is not None and c.position() > fim_quebra:
            c.setPosition(fim_quebra)
        quebras = pq_secoes.quebras_de_secao(doc, fresco=True)
        indice = sum(1 for p, _i in quebras if p < c.position())
        reg = pq_secoes.registro(doc)
        atual = reg.get(quebras[indice][1]) if indice < len(quebras) else \
            pq_secoes.secao_final(doc)
        if indice >= len(quebras):
            atual.pagina = self.layout_pag.pagina_arquivo
        base = QTextCharFormat(c.charFormat())
        for propriedade in (*_PROPS_IMAGEM, *pq_campos.PROPS_DE_CAMPO, *pq_opacos.PROPS_DE_OPACO,
                            *pq_marcas.PROPS_DE_MARCA, *pq_secoes.PROPS_DE_QUEBRA):
            base.clearProperty(propriedade)
        bf = QTextBlockFormat(c.blockFormat())
        for propriedade in (pq_notas.PROP_QUEBRA_NOTA, pq_secoes.PROP_QUEBRA_SECAO,
                            pq_listas.PROP_SAIU_DA_LISTA):
            bf.clearProperty(propriedade)
        bf.setPageBreakPolicy(_SEM_QUEBRA)
        c.insertBlock(bf)
        novo_inicio = c.position()
        c.setPosition(novo_inicio - 1)
        # A secao de cima: copia da do cursor (mesmos cabecalhos, mesmo tipo de comeco).
        pq_secoes.inserir_secao(c, pq_secoes.copia(atual), base)
        # A de baixo continua a do cursor, mas comeca como o tipo pedido.
        nova = pq_secoes.copia(atual, tipo=tipo)
        quebras = pq_secoes.quebras_de_secao(doc, fresco=True)
        depois = [p for p, _i in quebras if p > c.position() - 1]
        if indice + 1 < len(quebras) and depois:
            pq_secoes.trocar_secao_do_caractere(c, depois[0], nova)
        else:
            pq_secoes.trocar_final(doc, nova)
        c.setPosition(min(c.position() + 1, doc.characterCount() - 1))
        c.endEditBlock()
        secoes.calcular(forcar=True)
        self.layout_pag.atualizar_secoes(forcar=True)
        self._limpar_cache()
        self._altura_doc_anterior = None
        self._atualizar_geometria()
        self.paginaAlterada.emit()
        self._depois_de_mover()
        return True

    def _apagar(self, anterior: bool, palavra: bool = False) -> None:
        if self._cursor.hasSelection():
            self._remover_selecao()
        elif palavra:
            self._cursor.movePosition(M.WordLeft if anterior else M.WordRight, Selecionar)
            self._remover_selecao()
        elif anterior and ed_listas.backspace_no_inicio(self):
            # Lista (0.1.4): no inicio do item, tira o numero (e de novo o recuo).
            pass
        elif self._apagar_quebra_de_secao(anterior):
            pass
        elif anterior:
            # Backspace e Delete pulam a marca de marcador (invisivel) e apagam o caractere
            # que se ve: o link que aponta para o marcador continua valendo (0.1.3).
            pos = self._cursor.position()
            while pos > 0 and self._marcador_em(pos - 1):
                pos -= 1
            self._cursor.setPosition(pos)
            if pos > 0 and self._objeto_com_quadro(pos - 1):
                # O objeto que reserva espaco (0.1.7) e' um float do Qt: o deletePreviousChar
                # nao o apaga (QTextCursor recusa caractere com ObjectIndex). Apaga como selecao.
                self._cursor.setPosition(pos - 1, Selecionar)
                self._remover_selecao()
            else:
                self._cursor.deletePreviousChar()
        else:
            pos = self._cursor.position()
            while self._marcador_em(pos):
                pos += 1
            self._cursor.setPosition(pos)
            if self._objeto_com_quadro(pos):
                self._cursor.setPosition(pos + 1, Selecionar)
                self._remover_selecao()
            else:
                self._cursor.deleteChar()
        self._depois_de_mover()

    def _apagar_quebra_de_secao(self, anterior: bool) -> bool:
        """Backspace no comeco do paragrafo que segue a quebra de secao, ou Delete antes dela
        (0.1.12): apaga a quebra e funde os dois paragrafos, como o Word (a quebra e' a marca do
        paragrafo). O texto de cima passa a ser da secao de baixo. Um passo de desfazer."""
        if not self._no_corpo():
            return False
        pos = self._cursor.position()
        doc = self.document()
        if anterior:
            bloco = self._cursor.block()
            if pos != bloco.position() or not bloco.previous().isValid():
                if self._depois_da_quebra(pos):
                    inicio, fim = pos - 1, pos
                else:
                    return False
            else:
                inicio, fim = pos - 2, pos
                if not self._secao_em(inicio):
                    return False
        else:
            if not self._secao_em(pos):
                return False
            bloco = doc.findBlock(pos)
            fim_bloco = bloco.position() + bloco.length() - 1
            if pos + 1 != fim_bloco:
                return False
            inicio, fim = pos, min(pos + 2, doc.characterCount() - 1)
            if not bloco.next().isValid():
                fim = pos + 1
        self._cursor.beginEditBlock()
        self._cursor.setPosition(inicio)
        self._cursor.setPosition(fim, Selecionar)
        self._remover_selecao()
        self._cursor.endEditBlock()
        self.layout_pag.atualizar_secoes(forcar=True)
        self._limpar_cache()
        self._altura_doc_anterior = None
        self._atualizar_geometria()
        self.paginaAlterada.emit()
        return True

    def _pagina_do_teclado(self, anterior: bool, modo) -> None:
        """PageUp/PageDown: anda uma altura de tela, mantendo a coluna do caret."""
        if not self._no_corpo():
            # Cabecalho nao tem paginas: vai ao inicio ou ao fim dele.
            self._cursor.movePosition(M.Start if anterior else M.End, modo)
            self._depois_de_mover()
            return
        r = self.layout_pag.retangulo_cursor(self._cursor.position())
        altura = self.viewport().height() / escala_do_zoom(self._zoom)
        alvo = QPointF(r.x(), r.y() + (-altura if anterior else altura))
        pos = self.layout_pag.doc.documentLayout().hitTest(alvo, Qt.FuzzyHit)
        self._cursor.setPosition(pos, modo)
        self._depois_de_mover()

    # ----- teclado ---------------------------------------------------------
    def keyPressEvent(self, ev: QKeyEvent) -> None:  # noqa: N802 - nome do Qt
        sequencia = QKeySequence(ev.keyCombination())
        for acao in self._acoes:
            if acao.isEnabled() and sequencia in acao.shortcuts():
                acao.trigger()
                ev.accept()
                return
        if self._tecla(ev):
            ev.accept()
            return
        super().keyPressEvent(ev)

    def _tecla(self, ev: QKeyEvent) -> bool:
        """Teclas de edicao e navegacao. True se o evento foi tratado."""
        k = ev.key()
        mod = ev.modifiers()
        ctrl = bool(mod & Ctrl)
        alt = bool(mod & Alt)
        shift = bool(mod & Shift)
        modo = Selecionar if shift else Mover

        flutuante = self._posicao_flutuante_selecionado()
        if flutuante is not None and not alt:
            # Objeto flutuante selecionado (0.1.9): Esc tira a selecao; as setas movem 1 px de
            # tela (Ctrl: um quarto de px, no minimo 1 twip), um passo de desfazer por tecla.
            if k == Key.Key_Escape:
                self._cursor.setPosition(flutuante)
                self._depois_de_mover()
                return True
            setas = {Key.Key_Left: (-1, 0), Key.Key_Right: (1, 0), Key.Key_Up: (0, -1),
                     Key.Key_Down: (0, 1)}
            if k in setas and not shift:
                passo = 1.0 / self._mapa().escala
                if ctrl:
                    passo = max(1.0, passo / 4.0)
                dx, dy = setas[k]
                self.mover_objeto_selecionado(dx * passo, dy * passo)
                return True

        if k == Key.Key_Escape and not self._no_corpo():
            self.sair_da_faixa()
            return True

        if ctrl and not alt:
            if k in (Key.Key_Return, Key.Key_Enter):
                self.inserir_quebra_de_pagina()
            elif k == Key.Key_Backspace:
                self._apagar(anterior=True, palavra=True)
            elif k == Key.Key_Delete:
                self._apagar(anterior=False, palavra=True)
            elif k == Key.Key_Home:
                self._cursor.movePosition(M.Start, modo)
                self._depois_de_mover()
            elif k == Key.Key_End:
                self._cursor.movePosition(M.End, modo)
                self._depois_de_mover()
            elif k == Key.Key_Left:
                self._cursor.movePosition(M.WordLeft, modo)
                self._depois_de_mover()
            elif k == Key.Key_Right:
                self._cursor.movePosition(M.WordRight, modo)
                self._depois_de_mover()
            elif k == Key.Key_A:
                self.selectAll()
            elif k == Key.Key_Tab:
                self._inserir("\t")  # Ctrl+Tab: tabulacao dentro da celula, como no Word
            else:
                return False
            return True

        if k in (Key.Key_Return, Key.Key_Enter):
            self._quebrar(quebra=False)
        elif k == Key.Key_Backspace:
            self._apagar(anterior=True)
        elif k == Key.Key_Delete:
            self._apagar(anterior=False)
        elif k in (Key.Key_Tab, Key.Key_Backtab) and self._tab_na_lista(
                para_tras=(k == Key.Key_Backtab or shift)):
            pass
        elif k in (Key.Key_Tab, Key.Key_Backtab) and self._cursor.currentTable() is not None:
            self._tab_na_tabela(para_tras=(k == Key.Key_Backtab or shift))
        elif k == Key.Key_Tab:
            self._inserir("\t")
        elif k == Key.Key_Left:
            self._mover_horizontal(False, modo)
        elif k == Key.Key_Right:
            self._mover_horizontal(True, modo)
        elif k == Key.Key_Up:
            self._cursor.movePosition(M.Up, modo)
            self._depois_de_mover()
        elif k == Key.Key_Down:
            self._cursor.movePosition(M.Down, modo)
            self._depois_de_mover()
        elif k == Key.Key_Home:
            self._cursor.movePosition(M.StartOfLine, modo)
            self._depois_de_mover()
        elif k == Key.Key_End:
            self._cursor.movePosition(M.EndOfLine, modo)
            self._antes_da_quebra()
            self._depois_de_mover()
        elif k in (Key.Key_PageUp, Key.Key_PageDown):
            self._pagina_do_teclado(anterior=(k == Key.Key_PageUp), modo=modo)
        else:
            texto = ev.text()
            if not texto or not texto.isprintable() or ctrl:
                return False
            self._inserir(texto)
        return True

    def inputMethodEvent(self, ev) -> None:  # noqa: N802 - nome do Qt
        # Sem pre-edicao (IME de CJK nao e' alvo do M3): so' o texto confirmado entra.
        texto = ev.commitString()
        if texto:
            self._inserir(texto)
        ev.accept()

    # ----- mouse -----------------------------------------------------------
    def posicao_em(self, p: QPointF) -> int:
        """Posicao do texto sob um ponto do viewport. Fica na pagina clicada."""
        xd, yd = self._mapa().tela_para_doc(p.x(), p.y(), self._paginas())
        n = self.layout_pag.pagina_de_y(yd)
        pos = self.layout_pag.doc.documentLayout().hitTest(QPointF(xd, yd), Qt.FuzzyHit)
        if self.layout_pag.pagina_do_cursor(pos) != n:
            pos = self.layout_pag.ajustar_para_pagina(pos, n)
        if self._depois_da_quebra(pos):
            pos -= 1  # o caret fica antes da quebra de secao (0.1.12)
        return pos

    def flutuante_em(self, p: QPointF) -> int | None:
        """Posicao do objeto flutuante do corpo sob o ponto do viewport (0.1.7), ou None.

        O da frente ganha. O que fica atras do texto so' e' pego fora do texto (clicar numa
        letra sobre uma imagem de fundo poe o cursor na letra, como no Word)."""
        if not self._no_corpo():
            return None
        g = self.layout_pag.flutuantes
        if g.contexto is None or not g.lista():
            return None
        m = self._mapa()
        n_total = self._paginas()
        i0, i1 = m.paginas_visiveis(n_total)
        for n in range(i0, i1 + 1):
            fx, fy, fw, fh = m.folha_na_tela(n)
            if not (fx <= p.x() <= fx + fw and fy <= p.y() <= fy + fh):
                continue
            sx, sy = (p.x() - fx) / m.escala, (p.y() - fy) / m.escala
            posto = g.em(n, sx, sy, atras=False)
            if posto is not None:
                return posto.posicao
            posto = g.em(n, sx, sy, atras=True)
            if posto is not None:
                cfg = self.layout_pag.efetiva_da(n)
                ponto = QPointF(sx - cfg.margem_esq_tw, sy - cfg.margem_sup_tw + n * self.layout_pag.hb)
                no_corpo = 0 <= ponto.x() <= cfg.corpo_largura_tw() and                     0 <= sy - cfg.margem_sup_tw <= cfg.corpo_altura_tw()
                exato = self.layout_pag.doc.documentLayout().hitTest(
                    ponto, Qt.HitTestAccuracy.ExactHit) if no_corpo else -1
                if exato < 0:
                    return posto.posicao
        return None

    def _posicao_flutuante_selecionado(self) -> int | None:
        """O objeto flutuante selecionado sozinho, no documento em edicao (o corpo, ou desde a
        0.1.9 o cabecalho e o rodape em edicao)."""
        if not self._cursor.hasSelection():
            return None
        c = self._cursor
        if c.selectionEnd() - c.selectionStart() != 1:
            return None
        cf = pq_links.formato_em(self.document(), c.selectionStart())
        if cf is None or not pq_opacos.eh_opaco(cf):
            return None
        from editdoc.ponte_qt import flutuantes as pq_flutuantes
        return c.selectionStart() if pq_flutuantes.eh_flutuante(cf) else None

    def flutuante_selecionado(self) -> int | None:
        """Posicao do objeto flutuante selecionado (corpo, ou cabecalho e rodape em edicao)."""
        return self._posicao_flutuante_selecionado()

    def _selecionar_objeto(self, pos: int) -> None:
        self._cursor.setPosition(pos)
        self._cursor.setPosition(pos + 1, Selecionar)
        self._arrastando = False
        self._depois_de_mover()

    # ----- mover e redimensionar objetos (0.1.9) -------------------------------
    def _gerente_atual(self):
        """(documento, gerente dos flutuantes, LayoutPaginado ou None) do que se edita."""
        if self._edicao is not None:
            faixa = self._edicao
            self._posicionar_faixa(faixa, self._pagina_edicao)
            return faixa.doc, faixa.flutuantes, None
        return self.layout_pag.doc, self.layout_pag.flutuantes, self.layout_pag

    def _posicionar_faixa(self, faixa: FaixaQt, n: int) -> None:
        pagina = self.layout_pag.pagina_da_folha(n)
        self.layout_pag.preparar_faixa(faixa, n, self._paginas())
        faixa.posicionar(pagina, self.layout_pag.efetiva_da(n), n)
        faixa.flutuantes.atualizar()

    def objeto_na_folha(self, pos: int) -> tuple[int, tuple] | None:
        """(pagina, (x, y, largura, altura) em twips da folha) do objeto flutuante em `pos` do
        documento em edicao. No cabecalho e no rodape, a pagina e' a que se edita."""
        from editdoc.ponte_qt import flutuantes as pq_flutuantes
        doc, _g, _layout = self._gerente_atual()
        return pq_flutuantes.retangulo_de(doc, pos)

    def _folha_para_tela(self, n: int, rect: tuple) -> QRectF:
        m = self._mapa()
        fx, fy, _fw, _fh = m.folha_na_tela(n)
        x, y, w, h = rect
        return QRectF(fx + x * m.escala, fy + y * m.escala, max(w * m.escala, 1.0),
                      max(h * m.escala, 1.0))

    def retangulo_flutuante_na_tela(self, pos: int) -> QRectF | None:
        """Retangulo do objeto flutuante em `pos` do documento em edicao, em px do viewport."""
        achado = self.objeto_na_folha(pos)
        if achado is None:
            return None
        return self._folha_para_tela(achado[0], achado[1])

    def alca_flutuante_em(self, p: QPointF) -> str | None:
        """Nome da alca do objeto flutuante selecionado sob o ponto ("no", "n", "ne", "e",
        "se", "s", "so", "o"), ou None."""
        from editdoc.interface.vista_paginas import alcas_do_retangulo
        pos = self._posicao_flutuante_selecionado()
        r = self.retangulo_flutuante_na_tela(pos) if pos is not None else None
        if r is None:
            return None
        for nome, ponto in alcas_do_retangulo(r).items():
            if abs(p.x() - ponto.x()) <= ALCA_PX and abs(p.y() - ponto.y()) <= ALCA_PX:
                return nome
        return None

    def _ponto_na_folha(self, p: QPointF, n: int) -> tuple[float, float]:
        m = self._mapa()
        fx, fy, _fw, _fh = m.folha_na_tela(n)
        return (p.x() - fx) / m.escala, (p.y() - fy) / m.escala

    def _iniciar_arraste(self, pos: int, p: QPointF, alca: str | None) -> None:
        achado = self.objeto_na_folha(pos)
        if achado is None:
            self._arraste = None
            return
        n, rect = achado
        from editdoc.edicao import objetos as ed_objetos
        est = ed_objetos.estado_em(self.document(), pos)
        self._arraste = {"pos": pos, "alca": alca, "n": n, "rect": tuple(rect), "inicio": QPointF(p),
                         "ativo": False, "fantasma": None,
                         "imagem": bool(est is not None and est.imagem),
                         "zero": (rect[2] <= 0.5, rect[3] <= 0.5)}

    def _geometria_do_arraste(self, p: QPointF, mods) -> tuple[int, tuple]:
        """(pagina, (x, y, w, h) em twips da folha) de onde o objeto fica se soltar em `p`."""
        a = self._arraste
        n0 = a["n"]
        x, y, w, h = a["rect"]
        ix, iy = self._ponto_na_folha(a["inicio"], n0)
        if a["alca"] is None:
            n = n0
            if self._no_corpo():
                n = self._mapa().pagina_no_ponto(p.x(), p.y(), self._paginas())
            px, py = self._ponto_na_folha(p, n)
            dx, dy = px - ix, py - iy
            if mods & Shift and n == n0:
                # Shift trava o eixo, como no Word.
                if abs(dx) >= abs(dy):
                    dy = 0.0
                else:
                    dx = 0.0
            return n, (x + dx, y + dy, w, h)
        px, py = self._ponto_na_folha(p, n0)
        dx, dy = px - ix, py - iy
        alca = a["alca"]
        esq, topo, dir_, base = x, y, x + w, y + h
        minimo_l = 0.0 if a["zero"][0] else 15.0
        minimo_a = 0.0 if a["zero"][1] else 15.0
        if "o" in alca:
            esq = min(x + dx, dir_ - minimo_l)
        if "e" in alca:
            dir_ = max(x + w + dx, esq + minimo_l)
        if alca.startswith("n"):
            topo = min(y + dy, base - minimo_a)
        if alca.startswith("s"):
            base = max(y + h + dy, topo + minimo_a)
        nw, nh = dir_ - esq, base - topo
        canto = len(alca) == 2
        travar = canto and (bool(mods & Shift) or a["imagem"]) and w > 0.5 and h > 0.5
        if travar:
            escala = max(nw / w, nh / h)
            nw, nh = w * escala, h * escala
            if "o" in alca:
                esq = dir_ - nw
            if alca.startswith("n"):
                topo = base - nh
        return n0, (esq, topo, nw, nh)

    def _retangulo_fantasma(self) -> QRectF | None:
        a = self._arraste
        if a is None or a["fantasma"] is None:
            return None
        n, rect = a["fantasma"]
        return self._folha_para_tela(n, rect)

    def _soltar_arraste(self, p: QPointF, mods) -> None:
        from editdoc.edicao import objetos as ed_objetos
        a = self._arraste
        if a is None or not a["ativo"]:
            self._arraste = None
            self.viewport().update()
            return
        n, (x, y, w, h) = self._geometria_do_arraste(p, mods)
        self._arraste = None
        doc, g, layout = self._gerente_atual()
        tamanho = (w, h) if a["alca"] is not None else None
        try:
            final = ed_objetos.mover(doc, g, a["pos"], n, x, y, tamanho, layout=layout,
                                     reancorar=a["alca"] is None)
        except Exception:  # noqa: BLE001 - o documento fica como estava
            from editdoc import log_interno
            log_interno.obter(__name__).exception("mover objeto")
            final = None
        self._depois_de_mudar_objeto(final if final is not None else a["pos"])

    def _depois_de_mudar_objeto(self, pos: int) -> None:
        """Seleciona o objeto de novo e refaz a tela (o texto em volta mudou)."""
        self._limpar_cache()
        self._altura_doc_anterior = None
        if self._no_corpo():
            self.layout_pag.atualizar_flutuantes()
        self._cursor = QTextCursor(self.document())
        self._cursor.setPosition(min(pos, self.document().characterCount() - 1))
        if pos + 1 < self.document().characterCount():
            self._cursor.setPosition(pos + 1, Selecionar)
        self._arrastando = False
        self._depois_de_mover()
        # A troca que tirou um float do documento e' curada no proximo ciclo (0.1.7: desfaz e
        # refaz com a reserva zerada), e o desfazer/refazer do Qt tira a selecao do cursor. A
        # selecao volta depois da cura (o QTimer de zero ms vem na ordem em que foi pedido).
        doc = self.document()
        QTimer.singleShot(0, lambda: self._reselecionar(doc, pos))

    def _reselecionar(self, doc, pos: int) -> None:
        if doc is not self.document() or self._cursor.hasSelection():
            return
        if pos + 1 >= doc.characterCount():
            return
        from editdoc.edicao import objetos as ed_objetos
        if ed_objetos.tem_posicao(doc, pos) and self._cursor.position() in (pos, pos + 1):
            self._cursor.setPosition(pos)
            self._cursor.setPosition(pos + 1, Selecionar)
            self._depois_de_mover()

    def mover_objeto_selecionado(self, dx_tw: float, dy_tw: float) -> bool:
        """Desloca o objeto flutuante selecionado (setas). Um passo de desfazer. Sem reancorar:
        o teclado nunca leva o objeto para outro paragrafo."""
        from editdoc.edicao import objetos as ed_objetos
        pos = self._posicao_flutuante_selecionado()
        achado = self.objeto_na_folha(pos) if pos is not None else None
        if achado is None:
            return False
        n, (x, y, _w, _h) = achado
        doc, g, layout = self._gerente_atual()
        final = ed_objetos.mover(doc, g, pos, n, x + dx_tw, y + dy_tw, layout=layout,
                                 reancorar=False)
        if final is None:
            return False
        self._depois_de_mudar_objeto(final)
        return True

    def objeto_selecionado(self) -> int | None:
        """O objeto com posicao e tamanho selecionado sozinho (flutuante, imagem ou objeto
        preservado na linha), no documento em edicao. E' o alvo da quebra de texto e do dialogo
        "Posicao e tamanho" (0.1.9)."""
        from editdoc.edicao import objetos as ed_objetos
        c = self._cursor
        if not c.hasSelection() or c.selectionEnd() - c.selectionStart() != 1:
            return None
        pos = c.selectionStart()
        return pos if ed_objetos.tem_posicao(self.document(), pos) else None

    def quebra_do_selecionado(self) -> str | None:
        """A quebra de texto do objeto selecionado ("linha", "quadrado"...), ou None."""
        from editdoc.edicao import objetos as ed_objetos
        pos = self.objeto_selecionado()
        if pos is None:
            return None
        if ed_objetos.eh_imagem_na_linha(self.document(), pos):
            return "linha"
        est = ed_objetos.estado_em(self.document(), pos)
        return est.quebra if est is not None else None

    def retangulo_do_selecionado(self, pos: int) -> tuple[int, tuple] | None:
        """(pagina, (x, y, w, h) em twips da folha) do objeto em `pos`: o flutuante pela posicao
        dele, o da linha pelo lugar na linha (so' no corpo)."""
        achado = self.objeto_na_folha(pos)
        if achado is not None:
            return achado
        if not self._no_corpo():
            return None
        r = self.layout_pag.retangulo_imagem(pos)
        if r is None:
            return None
        lay = self.layout_pag
        n = lay.pagina_de_y(r.top())
        ef = lay.efetiva_da(n)
        return n, (r.left() + ef.margem_esq_tw, r.top() - n * lay.hb + lay.topo_da_pagina(n),
                   r.width(), r.height())

    def _documentos_do_arquivo(self) -> list:
        return [self.layout_pag.doc] + [f.doc for f in self.layout_pag.faixas.todas()]

    def definir_quebra_do_selecionado(self, quebra: str) -> bool:
        """Troca a quebra de texto do objeto selecionado (galeria "Quebra de texto"). Um passo
        de desfazer. False (com recado na barra de status) se nao puder."""
        from editdoc.edicao import objetos as ed_objetos
        from editdoc.formato_docx import posicao as fx_posicao
        pos = self.objeto_selecionado()
        if pos is None or self.quebra_do_selecionado() == quebra:
            return False
        doc, g, _layout = self._gerente_atual()
        achado = self.retangulo_do_selecionado(pos)
        try:
            final = ed_objetos.definir_quebra(doc, g, pos, quebra, self._documentos_do_arquivo(),
                                              achado[1] if achado is not None else None)
        except fx_posicao.PosicaoRecusada as erro:
            self.mensagem.emit(str(erro))
            return False
        self._depois_de_mudar_objeto(final)
        return True

    def dados_de_posicao(self, pos: int | None = None) -> dict | None:
        """O que o dialogo "Posicao e tamanho" mostra do objeto selecionado: a quebra, o
        tamanho e uma funcao que da' a posicao (EMU) relativa a cada referencia."""
        from editdoc.edicao import objetos as ed_objetos
        from editdoc.modelo import flutuantes as mf
        from editdoc.modelo.unidades import EMU_POR_TWIP
        pos = self.objeto_selecionado() if pos is None else pos
        if pos is None:
            return None
        doc, g, _layout = self._gerente_atual()
        achado = self.retangulo_do_selecionado(pos)
        est = ed_objetos.estado_em(doc, pos)
        imagem = ed_objetos.eh_imagem_na_linha(doc, pos)
        if achado is None and est is None and not imagem:
            return None
        if achado is not None:
            _n, (x, y, w, h) = achado
        else:
            x = y = 0.0
            w, h = (est.largura / EMU_POR_TWIP, est.altura / EMU_POR_TWIP) if est else (0.0, 0.0)
        if est is not None and (est.largura or est.altura):
            w, h = est.largura / EMU_POR_TWIP, est.altura / EMU_POR_TWIP
        _n, ref, _d = g.referencia(pos)

        def posicao_em(eixo: str, rel: str) -> int:
            return mf.deslocamento_para(eixo, rel, ref, x if eixo == "h" else y)

        return {"pos": pos, "quebra": "linha" if imagem else est.quebra,
                "largura_emu": round(w * EMU_POR_TWIP), "altura_emu": round(h * EMU_POR_TWIP),
                "h_rel": est.h_rel if est is not None and not est.na_linha else "column",
                "v_rel": est.v_rel if est is not None and not est.na_linha else "paragraph",
                "posicao_em": posicao_em, "imagem": imagem or bool(est and est.imagem),
                "zero": (bool(est) and est.largura == 0, bool(est) and est.altura == 0)}

    def aplicar_posicao_tamanho(self, escolha: dict) -> bool:
        """Aplica o que o dialogo devolveu ao objeto selecionado. Um passo de desfazer."""
        from editdoc.edicao import objetos as ed_objetos
        from editdoc.formato_docx import posicao as fx_posicao
        pos = self.objeto_selecionado()
        if pos is None or not escolha:
            return False
        doc, g, _layout = self._gerente_atual()
        achado = self.retangulo_do_selecionado(pos)
        try:
            final = ed_objetos.aplicar_dialogo(doc, g, pos, escolha, self._documentos_do_arquivo(),
                                               achado[1] if achado is not None else None)
        except fx_posicao.PosicaoRecusada as erro:
            self.mensagem.emit(str(erro))
            return False
        self._depois_de_mudar_objeto(final)
        return True

    def _cursor_do_mouse(self, p: QPointF) -> None:
        """Cursor de mover sobre o objeto selecionado e de redimensionar sobre as alcas."""
        forma = None
        if self._posicao_flutuante_selecionado() is not None:
            alca = self.alca_flutuante_em(p)
            if alca is not None:
                forma = {"n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
                         "e": Qt.CursorShape.SizeHorCursor, "o": Qt.CursorShape.SizeHorCursor,
                         "no": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
                         "ne": Qt.CursorShape.SizeBDiagCursor,
                         "so": Qt.CursorShape.SizeBDiagCursor}[alca]
            else:
                r = self.retangulo_flutuante_na_tela(self._posicao_flutuante_selecionado())
                if r is not None and r.contains(p):
                    forma = Qt.CursorShape.SizeAllCursor
        if forma is None:
            self.viewport().unsetCursor()
        else:
            self.viewport().setCursor(forma)

    def flutuante_das_faixas_em(self, p: QPointF) -> tuple[FaixaQt, int, int] | None:
        """(faixa, posicao, pagina) do objeto do cabecalho ou do rodape sob o ponto (0.1.9), na
        edicao das faixas. A faixa em edicao primeiro; o objeto de tras so' fora do texto."""
        zona, n = self.zona_em(p)
        faixas = [self.layout_pag.faixa_da_folha(onde, n) for onde in ("cabecalho", "rodape")]
        faixas = [f for f in faixas if f is not None]
        faixas.sort(key=lambda f: f is not self._edicao)
        sx, sy = self._ponto_na_folha(p, n)
        for faixa in faixas:
            self._posicionar_faixa(faixa, n)
            g = faixa.flutuantes
            if g.contexto is None or not g.lista():
                continue
            posto = g.em(n, sx, sy, atras=False)
            if posto is None:
                posto = g.em(n, sx, sy, atras=True)
                if posto is not None:
                    ox, oy = g.contexto.origem
                    texto = faixa.doc.documentLayout().hitTest(
                        QPointF(sx - ox, sy - oy), Qt.HitTestAccuracy.ExactHit)
                    if texto >= 0:
                        posto = None
            if posto is not None:
                return faixa, posto.posicao, n
        return None

    def imagem_em(self, p: QPointF) -> int | None:
        """Posicao da imagem sob o ponto do viewport, ou None (sempre None no cabecalho)."""
        if not self._no_corpo():
            return None
        pos = self.posicao_em(p)
        for k in (pos, pos - 1):
            r = self.retangulo_imagem_na_tela(k)
            if r is not None and r.contains(p):
                return k
        return None

    def alca_em(self, p: QPointF) -> tuple[int, str, QRectF] | None:
        """(imagem, canto, retangulo) se o ponto esta' numa alca da imagem selecionada."""
        if not self._no_corpo():
            return None
        pos = self.objeto_na_linha_selecionado()
        if pos is None:
            return None
        r = self.retangulo_imagem_na_tela(pos)
        if r is None:
            return None
        for canto, ponto in (("sup_esq", r.topLeft()), ("sup_dir", r.topRight()),
                             ("inf_esq", r.bottomLeft()), ("inf_dir", r.bottomRight())):
            if abs(p.x() - ponto.x()) <= ALCA_PX and abs(p.y() - ponto.y()) <= ALCA_PX:
                return pos, canto, r
        return None

    def _retangulo_do_arrasto(self, p: QPointF, mods=None) -> QRectF:
        """Novo retangulo da imagem durante o arrasto, com a proporcao travada.

        A imagem fica na linha de base: o canto de baixo a esquerda nao se move. O objeto
        preservado na linha que nao e' figura (caixa, forma: 0.1.9) so' trava a proporcao com
        Shift, como no Word.
        """
        pos, canto, r = self._redim
        if canto.endswith("dir"):
            largura = p.x() - r.left()
        else:
            largura = r.right() - p.x()
        largura = max(largura, 4.0)
        travar = True
        if not ed_imagens.formato_em(self.document(), pos):
            obj = pq_opacos.objeto_de(pq_links.formato_em(self.document(), pos) or QTextCharFormat())
            travar = (obj is not None and obj.tipo == "imagem") or bool(
                mods is not None and mods & Shift)
        if travar:
            altura = largura * r.height() / max(r.width(), 1e-6)
        else:
            altura = max(r.bottom() - p.y() if canto.startswith("sup") else p.y() - r.top(), 4.0)
            if canto.startswith("inf"):
                # O canto de baixo desce: a base da linha acompanha (o objeto cresce para baixo).
                return QRectF(r.left(), r.top(), largura, altura)
        return QRectF(r.left(), r.bottom() - altura, largura, altura)

    def _clique_na_faixa(self, ev) -> None:
        """Clique durante a edicao do cabecalho: posiciona no cabecalho ou rodape clicado.

        Clique simples no corpo nao faz nada (como no Word): sai-se com duplo clique ou Esc.
        """
        zona, n = self.zona_em(ev.position())
        if zona == "corpo":
            self._arrastando = False
            return
        estender = bool(ev.modifiers() & Shift)
        alvo = self.layout_pag.faixa_da_folha(zona, n)
        if alvo is not self._edicao or n != self._pagina_edicao:
            self._trocar_faixa(zona, n, ev.position())
        else:
            pos = self._posicao_na_faixa(self._edicao, n, ev.position())
            self._cursor.setPosition(pos, Selecionar if estender else Mover)
            self._depois_de_mover()
        self._arrastando = True

    def nota_no_ponto(self, p: QPointF):
        """(NotaQt, posicao) da nota sob o ponto do viewport (0.1.10), ou None."""
        g = self.layout_pag.notas
        if not g.paginas:
            return None
        m = self._mapa()
        n_total = self._paginas()
        n = m.pagina_no_ponto(p.x(), p.y(), n_total)
        x, y = m.tela_para_doc(p.x(), p.y(), n_total)
        if not (0 <= x <= self.layout_pag.efetiva_da(n).corpo_largura_tw()):
            return None
        return g.nota_em(n, x, y)

    def _clique_na_nota(self, ev, achado) -> None:
        nota, pos = achado
        estender = bool(ev.modifiers() & Shift)
        if nota is not self._nota_ed:
            self.entrar_na_nota(nota, pos)
        else:
            self._cursor.setPosition(pos, Selecionar if estender else Mover)
            self._depois_de_mover()
        self._arrastando = True

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        self.setFocus()
        self._arraste = None
        if ev.button() == Qt.MouseButton.LeftButton and self._edicao is None:
            # Notas (0.1.10): clique na area de notas edita a nota; fora dela, volta ao corpo.
            achado = self.nota_no_ponto(ev.position())
            if achado is not None:
                self._clique_na_nota(ev, achado)
                ev.accept()
                return
            if self._nota_ed is not None:
                self.sair_da_faixa()
        if ev.button() == Qt.MouseButton.LeftButton and not ev.modifiers() & Ctrl:
            # Alca do objeto flutuante selecionado (0.1.9): redimensionar.
            alca = self.alca_flutuante_em(ev.position())
            if alca is not None:
                self._iniciar_arraste(self._posicao_flutuante_selecionado(), ev.position(), alca)
                self._arrastando = False
                ev.accept()
                return
        if ev.button() == Qt.MouseButton.LeftButton and self._edicao is not None:
            achado = None if ev.modifiers() & Shift else self.flutuante_das_faixas_em(ev.position())
            if achado is not None:
                # Objeto do cabecalho ou do rodape na edicao das faixas (0.1.9): seleciona, e
                # arrastar move.
                faixa, pos, n = achado
                if faixa is not self._edicao or n != self._pagina_edicao:
                    self._trocar_faixa(faixa.onde, n)
                self._selecionar_objeto(pos)
                self._iniciar_arraste(pos, ev.position(), None)
                ev.accept()
                return
            self._clique_na_faixa(ev)
            ev.accept()
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            alca = self.alca_em(ev.position())
            if alca is not None:
                self._redim = alca
                self._redim_atual = QRectF(alca[2])
                self._arrastando = False
                ev.accept()
                return
            if ev.modifiers() & Ctrl and not ev.modifiers() & Shift:
                # Ctrl+clique num link abre o link (0.1.3), como no Word.
                pos_link = self.link_em(ev.position())
                if pos_link is not None:
                    self._arrastando = False
                    self.abrir_link(pos_link)
                    ev.accept()
                    return
            flutuante = None if ev.modifiers() & Shift else self.flutuante_em(ev.position())
            if flutuante is not None:
                # Clique no objeto flutuante seleciona o objeto (0.1.7): o contorno aparece, e
                # Delete apaga (com desfazer). Arrastar move (0.1.9).
                self._selecionar_objeto(flutuante)
                self._iniciar_arraste(flutuante, ev.position(), None)
                ev.accept()
                return
            imagem = None if ev.modifiers() & Shift else self.imagem_em(ev.position())
            if imagem is not None:
                # Clique na imagem seleciona a imagem, como no Word.
                self._cursor.setPosition(imagem)
                self._cursor.setPosition(imagem + 1, Selecionar)
                self._arrastando = False
                self._depois_de_mover()
                ev.accept()
                return
            pos = self.posicao_em(ev.position())
            estender = bool(ev.modifiers() & Shift)
            self._cursor.setPosition(pos, Selecionar if estender else Mover)
            self._arrastando = True
            self._depois_de_mover()
        ev.accept()

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton and self._edicao is None:
            # Notas (0.1.10): duplo clique no numero da nota volta a referencia; na marca da
            # referencia, vai a nota.
            from editdoc.edicao import notas as ed_notas
            achado = self.nota_no_ponto(ev.position())
            if achado is not None:
                nota, pos = achado
                if nota is not self._nota_ed:
                    self.entrar_na_nota(nota, pos)
                for k in (pos, pos - 1):
                    cf = pq_links.formato_em(nota.doc, k) if k >= 0 else None
                    m = pq_notas.marca_de(cf) if cf is not None else None
                    if m is not None and m.propria:
                        ed_notas.ir_para_referencia(self, nota.tipo, nota.id)
                        self._arrastando = False
                        ev.accept()
                        return
                self._cursor.setPosition(pos)
                self._cursor.select(QTextCursor.SelectionType.WordUnderCursor)
                self._arrastando = False
                self._depois_de_mover()
                ev.accept()
                return
            if self._nota_ed is None:
                pos = self.posicao_em(ev.position())
                for k in (pos, pos - 1):
                    cf = pq_links.formato_em(self.layout_pag.doc, k) if k >= 0 else None
                    m = pq_notas.marca_de(cf) if cf is not None else None
                    if m is not None and not m.propria:
                        self._arrastando = False
                        ed_notas.ir_para_nota(self, m.tipo, m.id)
                        ev.accept()
                        return
        if ev.button() == Qt.MouseButton.LeftButton:
            zona, n = self.zona_em(ev.position())
            achado = self.flutuante_das_faixas_em(ev.position()) if self._edicao is not None \
                else None
            if achado is not None:
                # Objeto do cabecalho ou do rodape na edicao (0.1.9): a caixa abre o editor.
                from editdoc.interface import dialogo_caixa
                faixa, pos, n = achado
                if faixa is not self._edicao or n != self._pagina_edicao:
                    self._trocar_faixa(faixa.onde, n)
                self._selecionar_objeto(pos)
                if dialogo_caixa.caixa_em(self.document(), pos) is not None:
                    self.editar_caixa(pos)
                ev.accept()
                return
            if self._edicao is None and zona != "corpo":
                # Duplo clique na margem de cima ou de baixo: edita o cabecalho ou o rodape.
                self.entrar_na_faixa(zona, n, ev.position())
                self._arrastando = False
                ev.accept()
                return
            if self._edicao is not None and zona == "corpo":
                # Duplo clique no corpo: volta ao corpo, com o caret no ponto clicado.
                self.sair_da_faixa()
                self._cursor.setPosition(self.posicao_em(ev.position()))
                self._arrastando = False
                self._depois_de_mover()
                ev.accept()
                return
            if self._edicao is not None:
                self._cursor.setPosition(self._posicao_na_faixa(self._edicao, self._pagina_edicao,
                                                                ev.position()))
                self._cursor.select(QTextCursor.SelectionType.WordUnderCursor)
                self._arrastando = False
                self._depois_de_mover()
                ev.accept()
                return
            from editdoc.interface import dialogo_caixa
            flutuante = self.flutuante_em(ev.position())
            if flutuante is not None:
                # Duplo clique no objeto flutuante (0.1.7): a caixa de texto abre o editor.
                self._selecionar_objeto(flutuante)
                if dialogo_caixa.caixa_em(self.document(), flutuante) is not None:
                    self.editar_caixa(flutuante)
                ev.accept()
                return
            pos = self.posicao_em(ev.position())
            for k in (pos, pos - 1):
                if dialogo_caixa.caixa_em(self.document(), k) is not None:
                    # Duplo clique na caixa de texto: edita o texto dela (0.1.5).
                    self._arrastando = False
                    self._cursor.setPosition(k)
                    self._cursor.setPosition(k + 1, Selecionar)
                    self._depois_de_mover()
                    self.editar_caixa(k)
                    ev.accept()
                    return
            self._cursor.setPosition(pos)
            self._cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            self._arrastando = False
            self._depois_de_mover()
        ev.accept()

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._arraste is not None:
            # Arraste de objeto flutuante (0.1.9): so' o contorno fantasma acompanha; o objeto
            # e o texto em volta mudam ao soltar.
            a = self._arraste
            inicio = a["inicio"]
            if not a["ativo"] and (abs(ev.position().x() - inicio.x()) > 3
                                   or abs(ev.position().y() - inicio.y()) > 3):
                a["ativo"] = True
            if a["ativo"]:
                a["fantasma"] = self._geometria_do_arraste(ev.position(), ev.modifiers())
                self.viewport().update()
            ev.accept()
            return
        if not self._arrastando and self._redim is None:
            self._cursor_do_mouse(ev.position())
            ev.accept()
            return
        if self._redim is not None:
            self._redim_atual = self._retangulo_do_arrasto(ev.position(), ev.modifiers())
            self.viewport().update()
        elif self._arrastando and self._nota_ed is not None:
            achado = self.nota_no_ponto(ev.position())
            if achado is not None and achado[0] is self._nota_ed:
                self._cursor.setPosition(achado[1], Selecionar)
                self._depois_de_mover()
        elif self._arrastando and self._edicao is not None:
            self._cursor.setPosition(self._posicao_na_faixa(self._edicao, self._pagina_edicao,
                                                            ev.position()), Selecionar)
            self._depois_de_mover()
        elif self._arrastando:
            self._cursor.setPosition(self.posicao_em(ev.position()), Selecionar)
            self._depois_de_mover()
        ev.accept()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if self._arraste is not None:
            self._soltar_arraste(ev.position(), ev.modifiers())
            self._arrastando = False
            ev.accept()
            return
        if self._redim is not None:
            pos = self._redim[0]
            novo = self._retangulo_do_arrasto(ev.position(), ev.modifiers())
            self._redim = self._redim_atual = None
            # Pixels de tela -> px96: a tela mostra m.escala pixels por twip, e 1 px96 = 15 twips.
            por_px96 = self._mapa().escala * 15.0
            if ed_imagens.formato_em(self.document(), pos) is not None:
                ed_imagens.redimensionar(self, pos, novo.width() / por_px96,
                                         novo.height() / por_px96)
            else:
                # Objeto preservado na linha (0.1.9): wp:extent e o xfrm de dentro.
                from editdoc.edicao import objetos as ed_objetos
                escala = self._mapa().escala
                if ed_objetos.redimensionar_na_linha(self.document(), pos, novo.width() / escala,
                                                     novo.height() / escala):
                    self._depois_de_mudar_objeto(pos)
            self.viewport().update()
        self._arrastando = False
        ev.accept()

    def contextMenuEvent(self, ev) -> None:  # noqa: N802
        menu = QMenu(self)
        doc = self.document()
        menu.addAction("Desfazer", self.undo).setEnabled(doc.isUndoAvailable())
        menu.addAction("Refazer", self.redo).setEnabled(doc.isRedoAvailable())
        menu.addSeparator()
        menu.addAction("Recortar", self.cut).setEnabled(self._cursor.hasSelection())
        menu.addAction("Copiar", self.copy).setEnabled(self._cursor.hasSelection())
        menu.addAction("Colar", self.paste).setEnabled(QApplication.clipboard().mimeData() is not None)
        menu.addSeparator()
        menu.addAction("Selecionar tudo", self.selectAll)
        caixa = self.caixa_selecionada()
        if caixa is not None:
            menu.addSeparator()
            menu.addAction("Editar texto da caixa", lambda: self.editar_caixa(caixa))
        if self.objeto_selecionado() is not None and self._acoes_quebra:
            # Objeto selecionado (0.1.9): a galeria da quebra e o dialogo, como no Word.
            menu.addSeparator()
            submenu = menu.addMenu("Quebra de texto")
            for acao in self._acoes_quebra:
                submenu.addAction(acao)
            if self._acao_posicao is not None:
                menu.addAction(self._acao_posicao)
        extras = [a for a in self._acoes_contexto if a.isEnabled()]
        if extras:
            menu.addSeparator()
            for acao in extras:
                menu.addAction(acao)
        menu.exec(ev.globalPos())

    # ----- hiperlinks (0.1.3) ------------------------------------------------
    #: Quem abre o endereco externo. Os testes trocam por um registro: nunca abrem o navegador.
    abrir_url = staticmethod(abrir_no_sistema)
    #: Pergunta antes de abrir endereco que nao e' http, https ou mailto. None = o dialogo.
    confirmar_link = None

    def link_em(self, p: QPointF) -> int | None:
        """Posicao do caractere de link sob o ponto do viewport, ou None (so' no corpo)."""
        if not self._no_corpo():
            return None
        pos = self.posicao_em(p)
        doc = self.layout_pag.doc
        m = self._mapa()
        for k in (pos, pos - 1):
            if pq_links.link_em(doc, k) is None:
                continue
            ini = self.layout_pag.retangulo_cursor(k)
            fim = self.layout_pag.retangulo_cursor(k + 1)
            x0, _y0 = m.doc_para_tela(ini.x(), ini.y(), self._paginas())
            x1, _y1 = m.doc_para_tela(fim.x(), fim.y(), self._paginas())
            if abs(fim.y() - ini.y()) > 1 or min(x0, x1) - 2 <= p.x() <= max(x0, x1) + 2:
                return k
        return None

    def abrir_link(self, pos: int) -> str:
        """Ctrl+clique (ou "Abrir link"): o link interno leva ao marcador; o externo abre no
        programa do Windows. Devolve o que foi feito: "marcador", "aberto", "recusado",
        "cancelado", "sem_marcador" ou "nada"."""
        link = pq_links.link_em(self.document(), pos)
        if link is None:
            return "nada"
        if link.interno():
            achados = [k for k, m in pq_marcas.posicoes_de_marcadores(
                self.layout_pag.doc, link.ancora) if m.tipo == "inicio"]
            if not achados:
                self.mensagem.emit(f"O marcador \"{link.ancora}\" não existe neste documento.")
                return "sem_marcador"
            self.ir_para_posicao(achados[0] + 1)
            return "marcador"
        url = link.href()
        if pq_links.esquema(url) in ESQUEMAS_PROIBIDOS:
            self.mensagem.emit("Este link pode executar código e não é aberto pelo EditDoc.")
            return "recusado"
        if not pq_links.abre_sem_perguntar(url):
            confirmar = self.confirmar_link or _confirmar_abrir_link
            if not confirmar(self, url):
                return "cancelado"
        self.abrir_url(url)
        return "aberto"

    # ----- foco ------------------------------------------------------------
    def focusInEvent(self, ev) -> None:  # noqa: N802
        super().focusInEvent(ev)
        self.definir_piscar(True)

    def focusOutEvent(self, ev) -> None:  # noqa: N802
        super().focusOutEvent(ev)
        self.definir_piscar(False)


def ed_links_formato_antes_da_nota(doc, pos: int) -> QTextCharFormat:
    """O formato para o texto digitado logo depois de uma marca de nota: o do caractere antes
    das marcas (sem objeto), ou o do bloco."""
    k = pos - 1
    while k >= 0:
        cf = pq_links.formato_em(doc, k)
        if cf is None or not (pq_notas.eh_nota(cf) or pq_marcas.eh_marca(cf)):
            break
        k -= 1
    base = pq_links.formato_em(doc, k) if k >= 0 else None
    if base is None or base.objectType() >= QTextFormat.ObjectTypes.UserObject.value \
            or base.isImageFormat():
        base = doc.findBlock(pos).charFormat()
    limpo = QTextCharFormat(base)
    for propriedade in (*_PROPS_IMAGEM, *pq_campos.PROPS_DE_CAMPO, *pq_opacos.PROPS_DE_OPACO,
                        *pq_marcas.PROPS_DE_MARCA, *pq_notas.PROPS_DE_NOTA):
        limpo.clearProperty(propriedade)
    return limpo


def _html_sem_espacador(frag: QTextDocumentFragment) -> str:
    """O HTML do trecho copiado sem a quebra de pagina do espacador das notas (0.1.10): ela nao
    e' do usuario, e colar a levaria como quebra de verdade. Nem (0.1.12) a quebra derivada da
    secao e o recuo direito escondido da secao estreita: colados, virariam do usuario."""
    from editdoc.interface.secoes import ConjuntoDeSecoes
    from editdoc.ponte_qt.imagens import DocumentoQt
    tmp = DocumentoQt()
    QTextCursor(tmp).insertFragment(frag)
    tem = False
    bloco = tmp.begin()
    while bloco.isValid():
        bf = bloco.blockFormat()
        if pq_notas.eh_espacador(bf) or pq_secoes.eh_derivada(bf) or \
                pq_estilos.recuo_secao(bf) is not None:
            bf = pq_notas.sem_espacador(bf)
            ConjuntoDeSecoes._aplicar_quebra(bf, 0, tabela=False)
            ConjuntoDeSecoes._aplicar_recuo(bf, 0.0)
            QTextCursor(bloco).setBlockFormat(bf)
            tem = True
        bloco = bloco.next()
    return tmp.toHtml() if tem else frag.toHtml()


def _confirmar_abrir_link(pai, url: str) -> bool:
    """Pergunta antes de abrir endereco que nao e' de pagina da Web nem de e-mail."""
    from editdoc.interface import dialogos_modais  # import tardio: so' quando se pergunta
    return dialogos_modais.confirmar_abrir_link(pai, url)
