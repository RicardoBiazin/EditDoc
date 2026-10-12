"""Controle de zoom da barra de status: menos, barra de porcentagem e mais.

O maximo vem da tela (`teto_de_zoom`): em DPR 1 vai a 400%; em DPR 1,5 a 266%; em DPR 2
a 200%. Ver docs/SPIKES.md, Gate do M3. Os botoes sao as acoes 'Reduzir' e 'Ampliar' do
Comandos: nenhum botao tem logica propria.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from editdoc.interface.faixa import BotaoAcao
from editdoc.interface.comandos import Comandos
from editdoc.modelo.folhas import ZOOM_MINIMO


class ControleZoom(QWidget):
    def __init__(self, comandos: Comandos, painel) -> None:
        super().__init__()
        self._painel = painel
        self._barra = QSlider(Qt.Orientation.Horizontal)
        self._barra.setFixedWidth(120)
        self._barra.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._barra.setAccessibleName("Zoom")
        self._barra.setAccessibleDescription("Zoom da página, em porcentagem")
        self._rotulo = QLabel()
        self._rotulo.setMinimumWidth(44)
        self._rotulo.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._rotulo.setAccessibleName("Porcentagem do zoom")
        linha = QHBoxLayout(self)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(2)
        linha.addWidget(BotaoAcao(comandos.acao("reduzir"), "−"))
        linha.addWidget(self._barra)
        linha.addWidget(BotaoAcao(comandos.acao("ampliar"), "+"))
        linha.addWidget(self._rotulo)
        self._barra.valueChanged.connect(self._escolhido)
        painel.zoomAlterado.connect(self._mostrar)
        self._atualizar_limites()
        self._mostrar(painel.zoom())

    def _atualizar_limites(self) -> None:
        maximo = int(round(self._painel.teto_do_zoom() * 100))
        self._barra.blockSignals(True)
        self._barra.setRange(int(ZOOM_MINIMO * 100), maximo)
        self._barra.setSingleStep(5)
        self._barra.setPageStep(25)
        self._barra.blockSignals(False)

    def _mostrar(self, zoom: float) -> None:
        self._atualizar_limites()
        self._barra.blockSignals(True)
        self._barra.setValue(int(round(zoom * 100)))
        self._barra.blockSignals(False)
        self._rotulo.setText(f"{round(zoom * 100)}%")

    def _escolhido(self, valor: int) -> None:
        self._painel.definir_zoom(valor / 100.0)
