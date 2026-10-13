"""Editar o texto de uma caixa de texto preservada (0.1.5).

Duplo clique na caixa, Enter com a caixa selecionada ou "Editar texto da caixa" no menu de
contexto abrem este dialogo. Ele usa o proprio editor do EditDoc (`PainelDocumento`, com a
ponte Qt de sempre: paragrafos, runs, formatacao, propriedades preservadas, listas e links)
numa pagina da largura da caixa. Negrito, italico e sublinhado tem botao e atalho (os mesmos
da janela); o resto da formatacao que o texto ja' tinha fica como estava.

Confirmar regrava o w:txbxContent dentro do XML do objeto (`formato_docx/caixas.py`), no
Choice e no Fallback, e troca o objeto do caractere da caixa num passo so' de desfazer. A
forma (posicao, tamanho, cor, contorno) nao muda.

A caixa com o que o EditDoc nao regravaria sem perda (tabela, imagem, campo...) abre so'
para leitura, com o motivo e o texto, e nada muda no documento.
"""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence, QTextCursor
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPlainTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from editdoc import log_interno
from editdoc.edicao import formatacao as fmt
from editdoc.formato_docx import caixas
from editdoc.modelo.documento import Documento, ObjetoOpaco
from editdoc.modelo.pagina import Pagina
from editdoc.ponte_qt import de_qt, para_qt
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import links as pq_links
from editdoc.ponte_qt import listas as pq_listas
from editdoc.ponte_qt import opacos as pq_opacos

log = log_interno.obter(__name__)

#: EMU por twip (914400 por polegada, 1440 twips por polegada).
_EMU_POR_TWIP = 635
_MARGEM_TW = 360


def caixa_em(doc, pos: int) -> ObjetoOpaco | None:
    """A caixa de texto no caractere `pos`, ou None."""
    if pos < 0:
        return None
    cf = pq_links.formato_em(doc, pos)
    if cf is None or not pq_opacos.eh_opaco(cf):
        return None
    obj = pq_opacos.objeto_de(cf)
    return obj if obj is not None and obj.tipo == "caixa_de_texto" else None


class DialogoCaixa(QDialog):
    """O editor do texto da caixa (ou a leitura, com o motivo)."""

    def __init__(self, pai: QWidget | None, obj: ObjetoOpaco, analise: caixas.Analise,
                 fonte: str, tamanho: float, estilos, numeracao) -> None:
        super().__init__(pai)
        self.analise = analise
        self.painel = None
        self.setWindowTitle("Editar texto da caixa" if analise.editavel else "Texto da caixa")
        self.setAccessibleName(self.windowTitle())
        vertical = QVBoxLayout(self)
        if analise.editavel:
            from editdoc.interface.painel_documento import PainelDocumento
            barra = QHBoxLayout()
            self.painel = PainelDocumento(fonte, tamanho, self)
            self.painel.setAccessibleName("Texto da caixa")
            acoes = []
            for rotulo, atalho, nome, funcao in (
                    ("N", "Ctrl+B", "Negrito", fmt.alternar_negrito),
                    ("I", "Ctrl+I", "Itálico", fmt.alternar_italico),
                    ("S", "Ctrl+U", "Sublinhado", fmt.alternar_sublinhado)):
                acao = QAction(rotulo, self)
                acao.setShortcut(QKeySequence(atalho))
                acao.setToolTip(f"{nome} ({atalho})")
                acao.triggered.connect(lambda _c=False, f=funcao: f(self.painel))
                botao = QToolButton(self)
                botao.setDefaultAction(acao)
                botao.setAccessibleName(nome)
                barra.addWidget(botao)
                acoes.append(acao)
            barra.addStretch(1)
            vertical.addLayout(barra)
            self.painel.registrar_atalhos(acoes)
            largura = max(round((obj.largura_emu or 2743200) / _EMU_POR_TWIP), 1440)
            pagina = Pagina(largura_tw=largura + 2 * _MARGEM_TW, altura_tw=8000,
                            margem_sup_tw=_MARGEM_TW, margem_inf_tw=_MARGEM_TW,
                            margem_esq_tw=_MARGEM_TW, margem_dir_tw=_MARGEM_TW,
                            cabecalho_tw=0, rodape_tw=0)
            if not pagina.valida():
                pagina = Pagina()
            doc = self.painel.documento_corpo()
            para_qt.preencher(doc, Documento(paragrafos=analise.blocos, estilos=estilos,
                                             numeracao=numeracao))
            self.painel.definir_configuracao_pagina(pagina)
            para_qt.concluir_listas(doc)
            vertical.addWidget(self.painel, 1)
            botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                      | QDialogButtonBox.StandardButton.Cancel)
            botoes.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
            botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
            self.resize(min(900, max(480, round(pagina.largura_tw / 15 + 80))), 420)
        else:
            rotulo = QLabel(analise.motivo + " O texto continua no arquivo; para mudá-lo, "
                            "use o Word.")
            rotulo.setWordWrap(True)
            vertical.addWidget(rotulo)
            texto = QPlainTextEdit(self)
            texto.setPlainText(analise.texto)
            texto.setReadOnly(True)
            texto.setAccessibleName("Texto da caixa (somente leitura)")
            vertical.addWidget(texto, 1)
            botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            botoes.button(QDialogButtonBox.StandardButton.Close).setText("Fechar")
            self.resize(480, 300)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        vertical.addWidget(botoes)

    def blocos(self) -> list:
        """Os blocos editados (paragrafos do modelo)."""
        return de_qt.extrair(self.painel.documento_corpo()).paragrafos


def editar(painel, pos: int) -> bool:
    """Abre o dialogo da caixa no caractere `pos` do documento em edicao do painel. True se o
    texto mudou (um passo de desfazer)."""
    doc = painel.document()
    obj = caixa_em(doc, pos)
    if obj is None:
        return False
    corpo = painel.documento_corpo()
    estilos = pq_estilos.catalogo(corpo)
    numeracao = pq_listas.catalogo(corpo)
    analise = caixas.analisar(obj, estilos, numeracao)
    fonte = corpo.defaultFont()
    dialogo = DialogoCaixa(painel, obj, analise, fonte.family(),
                           fonte.pointSizeF() if fonte.pointSizeF() > 0 else 11.0,
                           estilos, numeracao)
    if dialogo.exec() != QDialog.DialogCode.Accepted or not analise.editavel:
        return False
    try:
        novo = caixas.regravar(obj, dialogo.blocos(), estilos, numeracao)
    except ValueError as erro:
        log.warning("caixa de texto nao regravada: %s", erro)
        from editdoc.interface import dialogos_modais
        dialogos_modais.avisar(painel, "Caixa de texto",
                               "A caixa de texto não aceita tabela, imagem, objeto nem campo "
                               "nesta versão. O texto da caixa não foi alterado.")
        return False
    if novo.xml == obj.xml and novo.relacoes == obj.relacoes:
        return False
    cf = pq_links.formato_em(doc, pos)
    c = QTextCursor(doc)
    c.setPosition(pos)
    c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
    c.beginEditBlock()
    c.setCharFormat(pq_opacos.formato_de_opaco(cf, novo))
    c.endEditBlock()
    return True
