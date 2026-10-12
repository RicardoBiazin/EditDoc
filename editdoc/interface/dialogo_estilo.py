"""Dialogo "Modificar estilo" e "Criar um estilo" (M6).

Mostra o efeito do estilo (a cadeia basedOn resolvida) e devolve um `Estilo` com as
propriedades proprias: so' o que difere do estilo em que ele se baseia. Assim mudar a
base continua mudando o que o estilo herda, como no Word.

A cor abre o QColorDialog; os testes chamam `definir_cor`, sem o dialogo modal.
"""

from __future__ import annotations

import copy

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFontComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from editdoc.modelo.estilos import CAMPOS_CARACTERE, CAMPOS_PARAGRAFO, Estilo, Estilos, NOMES_PT
from editdoc.modelo.pagina import TWIPS_POR_CM

ALINHAMENTOS = (("esquerda", "À esquerda"), ("centro", "Centralizado"), ("direita", "À direita"),
                ("justificado", "Justificado"))
SEM_BASE = "(sem estilo)"


def _espaco(sufixo: str, minimo: float, maximo: float, passo: float, decimais: int) -> QDoubleSpinBox:
    campo = QDoubleSpinBox()
    campo.setRange(minimo, maximo)
    campo.setSingleStep(passo)
    campo.setDecimals(decimais)
    campo.setSuffix(sufixo)
    return campo


class DialogoEstilo(QDialog):
    def __init__(self, estilo: Estilo, estilos: Estilos, fonte_padrao: QFont,
                 novo: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._original = copy.deepcopy(estilo)
        self._estilos = estilos
        self._fonte_padrao = QFont(fonte_padrao)
        self._novo = novo
        self._cor: str | None = None
        self.setWindowTitle("Criar um estilo" if novo else "Modificar estilo")
        paragrafo = estilo.tipo == "paragrafo"

        self.nome = QLineEdit(estilo.nome_exibido())
        interno = estilo.nome.lower() in NOMES_PT
        self.nome.setReadOnly(interno and not novo)
        self.baseado = QComboBox()
        self.proximo = QComboBox()
        proibidos = {e.id for e in estilos.itens.values()
                     if any(x.id == estilo.id for x in estilos.cadeia(e.id))}
        self.baseado.addItem(SEM_BASE, None)
        for e in sorted(estilos.itens.values(), key=lambda x: x.nome_exibido().lower()):
            if e.tipo == estilo.tipo and not e.oculto and e.id not in proibidos:
                self.baseado.addItem(e.nome_exibido(), e.id)
            if paragrafo and e.tipo == "paragrafo" and not e.oculto:
                self.proximo.addItem(e.nome_exibido(), e.id)
        if paragrafo and estilo.id not in [self.proximo.itemData(i) for i in range(self.proximo.count())]:
            self.proximo.addItem(self.nome.text(), estilo.id)
        self._selecionar(self.baseado, estilo.baseado_em)
        self._selecionar(self.proximo, estilo.proximo or estilo.id)
        self.proximo.setEnabled(paragrafo)

        self.fonte = QFontComboBox()
        self.tamanho = _espaco(" pt", 1.0, 400.0, 0.5, 1)
        self.negrito = QCheckBox("Negrito")
        self.italico = QCheckBox("Itálico")
        self.sublinhado = QCheckBox("Sublinhado")
        self.botao_cor = QPushButton("Cor...")
        self.botao_cor.clicked.connect(self._escolher_cor)
        self.cor_automatica = QPushButton("Automática")
        self.cor_automatica.clicked.connect(lambda: self.definir_cor(None))
        self.alinhamento = QComboBox()
        for valor, texto in ALINHAMENTOS:
            self.alinhamento.addItem(texto, valor)
        self.antes = _espaco(" pt", 0.0, 400.0, 6.0, 1)
        self.depois = _espaco(" pt", 0.0, 400.0, 6.0, 1)
        self.entrelinhas = _espaco("", 0.5, 5.0, 0.05, 2)
        self.entrelinhas.setToolTip("Espaçamento entre linhas: 1,0 = simples; 1,5; 2,0 = duplo")
        self.recuo_esquerdo = _espaco(" cm", -5.0, 20.0, 0.25, 2)
        self.recuo_direito = _espaco(" cm", -5.0, 20.0, 0.25, 2)
        self.primeira_linha = _espaco(" cm", -10.0, 10.0, 0.25, 2)
        self.primeira_linha.setToolTip("Positivo: recuo da primeira linha; negativo: deslocamento")
        self.galeria = QCheckBox("Adicionar à galeria de estilos")
        self.galeria.setChecked(estilo.rapido)

        geral = QFormLayout()
        geral.addRow("Nome:", self.nome)
        geral.addRow("Estilo baseado em:", self.baseado)
        geral.addRow("Estilo do parágrafo seguinte:", self.proximo)
        caixa_fonte = QGroupBox("Fonte")
        f = QFormLayout(caixa_fonte)
        linha_fonte = QHBoxLayout()
        linha_fonte.addWidget(self.fonte, 1)
        linha_fonte.addWidget(self.tamanho)
        f.addRow("Fonte e tamanho:", _caixa(linha_fonte))
        linha_estilo = QHBoxLayout()
        for w in (self.negrito, self.italico, self.sublinhado):
            linha_estilo.addWidget(w)
        f.addRow("", _caixa(linha_estilo))
        self._amostra_cor = QLabel()
        self._amostra_cor.setFixedSize(28, 16)
        linha_cor = QHBoxLayout()
        for w in (self._amostra_cor, self.botao_cor, self.cor_automatica):
            linha_cor.addWidget(w)
        linha_cor.addStretch(1)
        f.addRow("Cor:", _caixa(linha_cor))
        caixa_par = QGroupBox("Parágrafo")
        p = QFormLayout(caixa_par)
        p.addRow("Alinhamento:", self.alinhamento)
        p.addRow("Espaçamento antes:", self.antes)
        p.addRow("Espaçamento depois:", self.depois)
        p.addRow("Entre linhas:", self.entrelinhas)
        p.addRow("Recuo à esquerda:", self.recuo_esquerdo)
        p.addRow("Recuo à direita:", self.recuo_direito)
        p.addRow("Primeira linha:", self.primeira_linha)
        caixa_par.setEnabled(paragrafo)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                  | QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self._aceitar)
        botoes.rejected.connect(self.reject)
        vertical = QVBoxLayout(self)
        vertical.addLayout(geral)
        vertical.addWidget(caixa_fonte)
        vertical.addWidget(caixa_par)
        vertical.addWidget(self.galeria)
        self._erro = QLabel()
        self._erro.setStyleSheet("color: #B00020;")
        vertical.addWidget(self._erro)
        vertical.addWidget(botoes)
        self._preencher(estilo)

    @staticmethod
    def _selecionar(combo: QComboBox, valor) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == valor:
                combo.setCurrentIndex(i)
                return

    def _efetivo(self, estilo: Estilo) -> tuple[dict, dict]:
        """O que o estilo da' (proprio + base) para mostrar nos campos."""
        if estilo.tipo == "caractere":
            car = self._estilos.resolver_caractere(estilo.baseado_em)
            car.update({k: v for k, v in estilo.caractere.items() if v is not None})
            return {}, car
        par, car = self._estilos.resolver_paragrafo(estilo.baseado_em) if estilo.baseado_em \
            else ({}, {})
        par = dict(par)
        car = dict(car)
        par.update({k: v for k, v in estilo.paragrafo.items() if v is not None})
        car.update({k: v for k, v in estilo.caractere.items() if v is not None})
        return par, car

    def _preencher(self, estilo: Estilo) -> None:
        par, car = self._efetivo(estilo)
        padrao = self._fonte_padrao
        # A fonte pode nao estar instalada: o combo mostra outra. So' vale se o usuario mexer.
        self._fonte_inicial = car.get("fonte") or padrao.family()
        self.fonte.setCurrentFont(QFont(self._fonte_inicial))
        self._fonte_do_combo = self.fonte.currentFont().family()
        self.tamanho.setValue((car.get("tamanho_meio_pt") or round(padrao.pointSizeF() * 2)) / 2)
        self.negrito.setChecked(bool(car.get("negrito")))
        self.italico.setChecked(bool(car.get("italico")))
        self.sublinhado.setChecked(bool(car.get("sublinhado")))
        self.definir_cor(car.get("cor_hex"))
        self._selecionar(self.alinhamento, par.get("alinhamento") or "esquerda")
        self.antes.setValue((par.get("espaco_antes_tw") or 0) / 20)
        self.depois.setValue((par.get("espaco_depois_tw") or 0) / 20)
        self.entrelinhas.setValue((par.get("espacamento_linha_pct") or 100) / 100)
        self.recuo_esquerdo.setValue((par.get("recuo_esquerdo_tw") or 0) / TWIPS_POR_CM)
        self.recuo_direito.setValue((par.get("recuo_direito_tw") or 0) / TWIPS_POR_CM)
        self.primeira_linha.setValue((par.get("recuo_primeira_linha_tw") or 0) / TWIPS_POR_CM)

    # -- cor ----------------------------------------------------------------
    def definir_cor(self, cor_hex: str | None) -> None:
        self._cor = cor_hex.upper() if cor_hex else None
        fundo = f"#{self._cor}" if self._cor else "transparent"
        self._amostra_cor.setStyleSheet(f"background: {fundo}; border: 1px solid palette(mid);")
        self._amostra_cor.setToolTip(f"#{self._cor}" if self._cor else "Automática")

    def _escolher_cor(self) -> None:
        cor = QColorDialog.getColor(QColor("#" + self._cor) if self._cor else QColor(0, 0, 0), self,
                                    "Cor da fonte")
        if cor.isValid():
            self.definir_cor(cor.name()[1:])

    # -- resultado ------------------------------------------------------------
    def resultado(self) -> Estilo | None:
        """O Estilo com as escolhas do dialogo. None se o nome for invalido."""
        nome = self.nome.text().strip()
        if not nome:
            return None
        e = copy.deepcopy(self._original)
        if not self.nome.isReadOnly():
            e.nome = nome
        e.baseado_em = self.baseado.currentData()
        if e.tipo == "paragrafo":
            e.proximo = self.proximo.currentData() or e.id
        e.rapido = self.galeria.isChecked()
        if e.tipo == "caractere":
            base_par, base_car = {}, self._estilos.resolver_caractere(e.baseado_em)
        elif e.baseado_em:
            base_par, base_car = self._estilos.resolver_paragrafo(e.baseado_em)
        else:
            base_par, base_car = {}, {}
        padrao = self._fonte_padrao
        escolhida = self.fonte.currentFont().family()
        car = {
            "fonte": self._fonte_inicial if escolhida == self._fonte_do_combo else escolhida,
            "tamanho_meio_pt": round(self.tamanho.value() * 2),
            "negrito": self.negrito.isChecked(),
            "italico": self.italico.isChecked(),
            "sublinhado": self.sublinhado.isChecked(),
            "cor_hex": self._cor,
        }
        # O que e' igual a base (ou ao padrao do documento, sem base) nao vira propriedade.
        base_car = dict(base_car)
        base_car.setdefault("fonte", padrao.family())
        base_car.setdefault("tamanho_meio_pt", round(padrao.pointSizeF() * 2))
        for chave in ("negrito", "italico", "sublinhado"):
            base_car.setdefault(chave, False)
        e.caractere = {k: v for k, v in car.items()
                       if k in CAMPOS_CARACTERE and v is not None and v != base_car.get(k)}
        if e.tipo == "paragrafo":
            par = {
                "alinhamento": self.alinhamento.currentData(),
                "espaco_antes_tw": round(self.antes.value() * 20),
                "espaco_depois_tw": round(self.depois.value() * 20),
                "espacamento_linha_pct": round(self.entrelinhas.value() * 100),
                "recuo_esquerdo_tw": round(self.recuo_esquerdo.value() * TWIPS_POR_CM),
                "recuo_direito_tw": round(self.recuo_direito.value() * TWIPS_POR_CM),
                "recuo_primeira_linha_tw": round(self.primeira_linha.value() * TWIPS_POR_CM),
            }
            base_par = dict(base_par)
            for chave, neutro in (("alinhamento", "esquerda"), ("espaco_antes_tw", 0),
                                  ("espaco_depois_tw", 0), ("espacamento_linha_pct", 100),
                                  ("recuo_esquerdo_tw", 0), ("recuo_direito_tw", 0),
                                  ("recuo_primeira_linha_tw", 0)):
                base_par.setdefault(chave, neutro)
            # O que o estilo tinha proprio e o usuario nao mudou continua proprio.
            originais = self._efetivo(self._original)[0]
            e.paragrafo = {k: v for k, v in par.items() if k in CAMPOS_PARAGRAFO and
                           (v != base_par.get(k) or (k in self._original.paragrafo
                                                     and v == originais.get(k)))}
        return e

    def _aceitar(self) -> None:
        if self.resultado() is None:
            self._erro.setText("O estilo precisa de um nome.")
            return
        nome = self.nome.text().strip()
        outro = self._estilos.por_nome(nome)
        if self._novo and outro is not None:
            self._erro.setText("Já existe um estilo com esse nome.")
            return
        self.accept()


def pedir_estilo(pai, estilo: Estilo, estilos: Estilos, fonte_padrao: QFont,
                 novo: bool = False) -> Estilo | None:
    """Abre o dialogo (modal). None se o usuario cancelar. Os testes trocam esta funcao."""
    dlg = DialogoEstilo(estilo, estilos, fonte_padrao, novo, pai)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.resultado()
    return None


def _caixa(layout) -> QWidget:
    w = QWidget()
    layout.setContentsMargins(0, 0, 0, 0)
    w.setLayout(layout)
    return w
