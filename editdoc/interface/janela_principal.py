"""Janela principal: faixa de opcoes, documento, localizar e barra de status.

M1: um documento por janela, sem abrir nem salvar (chegam no M2). O documento
vive no painel provisorio (QTextEdit). Os comandos vem de um so' registro, e a
faixa, os atalhos e o menu usam os mesmos QAction.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from editdoc import APP, VERSAO, recursos
from editdoc.edicao import busca
from editdoc.edicao.busca import Opcoes
from editdoc.interface.atualizador import AtualizadorDeEstado
from editdoc.interface.barra_busca import BarraBusca
from editdoc.interface.comandos import Comandos
from editdoc.interface.faixa import Faixa
from editdoc.interface.painel_documento import PainelDocumento
from editdoc.modelo.estatisticas import contar

#: Pausa depois da ultima tecla antes de recontar as palavras. Contar a cada
#: tecla e' trabalho a toa num documento grande.
ATRASO_ESTATISTICAS_MS = 400


class JanelaPrincipal(QMainWindow):
    def __init__(self, cfg: dict) -> None:
        super().__init__()
        self.setWindowTitle(f"Documento em branco - {APP} {VERSAO}")
        self.setWindowIcon(recursos.icone_do_aplicativo())
        self.resize(cfg["janela_largura"], cfg["janela_altura"])

        self.painel = PainelDocumento(cfg["fonte_padrao"], cfg["tamanho_padrao"])
        self.comandos = Comandos(self, self.painel, self._abrir_localizar,
                                 self._abrir_substituir)
        self.faixa = Faixa(self.comandos, self.painel)
        self.barra_busca = BarraBusca()
        self.barra_busca.hide()
        self.barra_busca.procurar.connect(self._procurar)
        self.barra_busca.substituir_um.connect(self._substituir_um)
        self.barra_busca.substituir_tudo.connect(self._substituir_tudo)

        self.atualizador = AtualizadorDeEstado(self.painel, self.comandos,
                                               self.faixa.familia, self.faixa.tamanho)
        self.painel.registrar_atalhos(self.comandos.todas())
        # Sem isto o atalho so' funciona quando o foco esta no painel.
        for acao in self.comandos.todas():
            self.addAction(acao)

        centro = QWidget()
        vertical = QVBoxLayout(centro)
        vertical.setContentsMargins(0, 0, 0, 0)
        vertical.setSpacing(0)
        vertical.addWidget(self.faixa)
        vertical.addWidget(self.barra_busca)
        vertical.addWidget(self.painel, 1)
        self.setCentralWidget(centro)

        self._rotulo_palavras = QLabel()
        self.statusBar().addPermanentWidget(self._rotulo_palavras)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(ATRASO_ESTATISTICAS_MS)
        self._timer.timeout.connect(self.atualizar_estatisticas)
        self.painel.textChanged.connect(self._timer.start)
        self.atualizar_estatisticas()

    def atualizar_estatisticas(self) -> None:
        contagem = contar(self.painel.toPlainText())
        self._rotulo_palavras.setText(f"Palavras: {contagem.palavras}")

    # -- localizar e substituir ---------------------------------------------

    def _abrir_localizar(self) -> None:
        self.barra_busca.mostrar(substituir=False)

    def _abrir_substituir(self) -> None:
        self.barra_busca.mostrar(substituir=True)

    def _procurar(self, texto: str, maiusculas: bool, palavra: bool, para_tras: bool) -> None:
        achou = busca.localizar(self.painel, texto, Opcoes(maiusculas, palavra), para_tras)
        self.barra_busca.dizer("" if achou else "Não encontrado")

    def _substituir_um(self, texto: str, substituto: str, maiusculas: bool,
                       palavra: bool) -> None:
        achou = busca.substituir_atual(self.painel, texto, substituto,
                                       Opcoes(maiusculas, palavra))
        self.barra_busca.dizer("" if achou else "Não encontrado")

    def _substituir_tudo(self, texto: str, substituto: str, maiusculas: bool,
                         palavra: bool) -> None:
        trocas = busca.substituir_todas(self.painel, texto, substituto,
                                        Opcoes(maiusculas, palavra))
        if trocas == 1:
            self.barra_busca.dizer("1 substituição")
        else:
            self.barra_busca.dizer(f"{trocas} substituições")
