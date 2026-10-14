"""Dialogo "Posicao e tamanho" do objeto selecionado (0.1.9), como o "Layout" do Word.

Tres partes: a quebra de texto (as sete do Word), a posicao horizontal e vertical em cm
relativa a uma referencia (pagina, margem, coluna ou caractere; pagina, margem, paragrafo ou
linha) e o tamanho em cm, com a proporcao travada. Trocar a referencia mostra o mesmo lugar
medido da referencia nova, como no Word: o objeto nao anda so' por trocar a referencia.

O dialogo devolve so' o que mudou ({"quebra", "h", "v", "tamanho"}, em EMU), para que o XML
do objeto so' mude no que o usuario mexeu (um objeto alinhado ao centro continua alinhado se
a posicao nao foi tocada).
"""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QVBoxLayout, QWidget)

from editdoc import APP
from editdoc.formato_docx.posicao import QUEBRAS, ROTULOS_QUEBRA
from editdoc.modelo import flutuantes as mf
from editdoc.modelo.unidades import EMU_POR_CM

#: Referencias que o dialogo oferece: (valor do relativeFrom, rotulo).
REFERENCIAS_H = (("page", "Página"), ("margin", "Margem"), ("column", "Coluna"),
                 ("character", "Caractere"))
REFERENCIAS_V = (("page", "Página"), ("margin", "Margem"), ("paragraph", "Parágrafo"),
                 ("line", "Linha"))
POSICAO_MAXIMA_CM = mf.POSICAO_MAXIMA_EMU / EMU_POR_CM
TAMANHO_MAXIMO_CM = mf.TAMANHO_MAXIMO_EMU / EMU_POR_CM
TAMANHO_MINIMO_CM = 0.03


def _spin(minimo: float, maximo: float, valor: float, nome: str) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimo, maximo)
    spin.setDecimals(2)
    spin.setSingleStep(0.1)
    spin.setSuffix(" cm")
    spin.setValue(round(valor, 2))
    spin.setAccessibleName(nome)
    return spin


def _combo(itens, atual: str, nome: str) -> QComboBox:
    combo = QComboBox()
    combo.setAccessibleName(nome)
    for valor, rotulo in itens:
        combo.addItem(rotulo, valor)
    if combo.findData(atual) < 0:
        # Referencia do arquivo que o dialogo nao lista (leftMargin...): aparece como esta'.
        combo.addItem(atual, atual)
    combo.setCurrentIndex(combo.findData(atual))
    return combo


class DialogoPosicao(QDialog):
    """O dialogo. `dados` vem de `PainelDocumento.dados_de_posicao`."""

    def __init__(self, pai: QWidget | None, dados: dict) -> None:
        super().__init__(pai)
        self.dados = dados
        self.setWindowTitle(f"Posição e tamanho - {APP}")
        self.setAccessibleName("Posição e tamanho")
        vertical = QVBoxLayout(self)

        grupo_quebra = QGroupBox("Quebra de texto")
        form = QFormLayout(grupo_quebra)
        self.quebra = QComboBox()
        self.quebra.setAccessibleName("Quebra de texto")
        for chave in QUEBRAS:
            self.quebra.addItem(ROTULOS_QUEBRA[chave], chave)
        self.quebra.setCurrentIndex(self.quebra.findData(dados["quebra"]))
        form.addRow("Disposição:", self.quebra)
        vertical.addWidget(grupo_quebra)

        grupo_pos = QGroupBox("Posição")
        form = QFormLayout(grupo_pos)
        self.h_rel = _combo(REFERENCIAS_H, dados["h_rel"], "Posição horizontal relativa a")
        self.v_rel = _combo(REFERENCIAS_V, dados["v_rel"], "Posição vertical relativa a")
        self.h = _spin(-POSICAO_MAXIMA_CM, POSICAO_MAXIMA_CM, self._cm("h", dados["h_rel"]),
                       "Posição horizontal")
        self.v = _spin(-POSICAO_MAXIMA_CM, POSICAO_MAXIMA_CM, self._cm("v", dados["v_rel"]),
                       "Posição vertical")
        for rotulo, spin, combo in (("Horizontal:", self.h, self.h_rel),
                                    ("Vertical:", self.v, self.v_rel)):
            linha = QHBoxLayout()
            linha.addWidget(spin)
            linha.addWidget(combo, 1)
            form.addRow(rotulo, linha)
        self.h_rel.currentIndexChanged.connect(lambda _i: self._referencia_trocada("h"))
        self.v_rel.currentIndexChanged.connect(lambda _i: self._referencia_trocada("v"))
        vertical.addWidget(grupo_pos)
        self._grupo_pos = grupo_pos

        grupo_tam = QGroupBox("Tamanho")
        form = QFormLayout(grupo_tam)
        largura_cm = dados["largura_emu"] / EMU_POR_CM
        altura_cm = dados["altura_emu"] / EMU_POR_CM
        zero_l, zero_a = dados.get("zero", (False, False))
        self.largura = _spin(0.0 if zero_l else TAMANHO_MINIMO_CM, TAMANHO_MAXIMO_CM, largura_cm,
                             "Largura")
        self.altura = _spin(0.0 if zero_a else TAMANHO_MINIMO_CM, TAMANHO_MAXIMO_CM, altura_cm,
                            "Altura")
        self.travar = QCheckBox("Travar a proporção")
        self.travar.setChecked(bool(dados.get("imagem")))
        self._proporcao = altura_cm / largura_cm if largura_cm > 0 else 0.0
        self._ocupado = False
        self.largura.valueChanged.connect(lambda _v: self._seguir(self.largura, self.altura,
                                                                  self._proporcao))
        self.altura.valueChanged.connect(lambda _v: self._seguir(
            self.altura, self.largura, 1 / self._proporcao if self._proporcao else 0.0))
        form.addRow("Largura:", self.largura)
        form.addRow("Altura:", self.altura)
        form.addRow(self.travar)
        vertical.addWidget(grupo_tam)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                  | QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        vertical.addWidget(botoes)
        self.quebra.currentIndexChanged.connect(lambda _i: self._quebra_trocada())
        self._iniciais = self._valores()
        self._quebra_trocada()

    def _cm(self, eixo: str, rel: str) -> float:
        return self.dados["posicao_em"](eixo, rel) / EMU_POR_CM

    def _referencia_trocada(self, eixo: str) -> None:
        combo, spin = (self.h_rel, self.h) if eixo == "h" else (self.v_rel, self.v)
        spin.setValue(round(self._cm(eixo, combo.currentData()), 2))

    def _quebra_trocada(self) -> None:
        self._grupo_pos.setEnabled(self.quebra.currentData() != "linha")

    def _seguir(self, origem: QDoubleSpinBox, destino: QDoubleSpinBox, fator: float) -> None:
        if self.travar.isChecked() and fator > 0 and not self._ocupado:
            self._ocupado = True
            destino.setValue(origem.value() * fator)
            self._ocupado = False

    def _valores(self) -> tuple:
        return (self.quebra.currentData(), self.h_rel.currentData(), self.h.value(),
                self.v_rel.currentData(), self.v.value(), self.largura.value(),
                self.altura.value())

    def escolha(self) -> dict:
        """So' o que mudou, em EMU: {"quebra", "h": (rel, emu), "v": (rel, emu), "tamanho"}."""
        quebra, h_rel, h, v_rel, v, largura, altura = self._valores()
        ini = self._iniciais
        saida: dict = {}
        if quebra != ini[0]:
            saida["quebra"] = quebra
        if quebra != "linha":
            # O objeto que passa a flutuar fica onde estava, a nao ser que se mude a posicao.
            if (h_rel, h) != (ini[1], ini[2]) or ini[0] == "linha":
                saida["h"] = (h_rel, round(h * EMU_POR_CM))
            if (v_rel, v) != (ini[3], ini[4]) or ini[0] == "linha":
                saida["v"] = (v_rel, round(v * EMU_POR_CM))
        if (largura, altura) != (ini[5], ini[6]):
            saida["tamanho"] = (round(largura * EMU_POR_CM), round(altura * EMU_POR_CM))
        return saida


def pedir(pai: QWidget | None, dados: dict) -> dict | None:
    """Abre o dialogo. None se cancelar; {} se nada mudou."""
    dialogo = DialogoPosicao(pai, dados)
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialogo.escolha()
