"""Referencias > Opcoes de notas (0.1.10): formato, inicio, reinicio, posicao e converter.

Como o "Nota de Rodape e Nota de Fim" do Word: escolhe-se o tipo (rodape ou fim), e os campos
mostram as propriedades efetivas dele. Devolve so' o que o usuario escolheu (`pedir`); quem
aplica e' `edicao/notas.py`, num passo de desfazer.
"""

from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QPushButton, QSpinBox, QVBoxLayout)

from editdoc.modelo.notas import NUMERO_MAXIMO, PropriedadesNota, formatar

#: Formatos do numero que o dialogo oferece (os do Word mais usados).
FORMATOS = (("decimal", "1, 2, 3"), ("lowerLetter", "a, b, c"), ("upperLetter", "A, B, C"),
            ("lowerRoman", "i, ii, iii"), ("upperRoman", "I, II, III"),
            ("chicago", "*, †, ‡, §"))
POSICOES = {"rodape": (("pageBottom", "Fim da página"), ("beneathText", "Abaixo do texto")),
            "fim": (("docEnd", "Fim do documento"), ("sectEnd", "Fim da seção"))}
REINICIOS = {"rodape": (("continuous", "Contínua"), ("eachPage", "Reiniciar a cada página"),
                        ("eachSect", "Reiniciar a cada seção")),
             "fim": (("continuous", "Contínua"), ("eachSect", "Reiniciar a cada seção"))}
TIPOS = (("rodape", "Notas de rodapé"), ("fim", "Notas de fim"))


class DialogoNotas(QDialog):
    def __init__(self, pai, propriedades: dict, contagens: dict, tipo: str = "rodape") -> None:
        super().__init__(pai)
        self.setWindowTitle("Nota de Rodapé e Nota de Fim")
        self._props = propriedades
        self.converter: str | None = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.tipo = QComboBox()
        self.tipo.setAccessibleName("Tipo de nota")
        for chave, texto in TIPOS:
            self.tipo.addItem(texto, chave)
        form.addRow("&Tipo:", self.tipo)
        self.posicao = QComboBox()
        self.posicao.setAccessibleName("Posição das notas")
        form.addRow("&Posição:", self.posicao)
        self.formato = QComboBox()
        self.formato.setAccessibleName("Formato do número")
        for chave, texto in FORMATOS:
            self.formato.addItem(texto, chave)
        form.addRow("&Formato do número:", self.formato)
        self.inicio = QSpinBox()
        self.inicio.setAccessibleName("Iniciar em")
        self.inicio.setRange(0, NUMERO_MAXIMO)
        form.addRow("&Iniciar em:", self.inicio)
        self.reinicio = QComboBox()
        self.reinicio.setAccessibleName("Numeração")
        form.addRow("&Numeração:", self.reinicio)
        layout.addLayout(form)
        self.exemplo = QLabel()
        self.exemplo.setAccessibleName("Exemplo da numeração")
        layout.addWidget(self.exemplo)
        self.botao_converter = QPushButton()
        self.botao_converter.setAccessibleName("Converter as notas")
        self.botao_converter.clicked.connect(self._converter)
        layout.addWidget(self.botao_converter)
        self._contagens = contagens
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                  QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Aplicar")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)
        self.tipo.currentIndexChanged.connect(self._mostrar_tipo)
        self.formato.currentIndexChanged.connect(self._exemplo)
        self.inicio.valueChanged.connect(self._exemplo)
        self.tipo.setCurrentIndex(0 if tipo == "rodape" else 1)
        self._mostrar_tipo()

    def tipo_atual(self) -> str:
        return self.tipo.currentData()

    def _mostrar_tipo(self) -> None:
        tipo = self.tipo_atual()
        pr = self._props[tipo]
        for combo, opcoes, valor in ((self.posicao, POSICOES[tipo], pr.posicao),
                                     (self.reinicio, REINICIOS[tipo], pr.reinicio)):
            combo.blockSignals(True)
            combo.clear()
            for chave, texto in opcoes:
                combo.addItem(texto, chave)
            i = combo.findData(valor)
            combo.setCurrentIndex(max(i, 0))
            combo.blockSignals(False)
        i = self.formato.findData(pr.formato)
        self.formato.setCurrentIndex(max(i, 0))
        self.inicio.setValue(pr.inicio if pr.inicio is not None else 1)
        outro = "fim" if tipo == "rodape" else "rodape"
        n = self._contagens.get(tipo, 0)
        self.botao_converter.setText(
            "Converter todas as notas de rodapé em notas de fim" if tipo == "rodape"
            else "Converter todas as notas de fim em notas de rodapé")
        self.botao_converter.setEnabled(n > 0)
        self.botao_converter.setToolTip(f"{n} nota(s) passam a ser do outro tipo ({outro}).")
        self._exemplo()

    def _exemplo(self) -> None:
        inicio = self.inicio.value()
        formato = self.formato.currentData()
        self.exemplo.setText("Exemplo: " + ", ".join(formatar(inicio + i, formato) or "0"
                                                     for i in range(3)))

    def _converter(self) -> None:
        self.converter = self.tipo_atual()
        self.accept()

    def escolha(self) -> dict:
        return {"tipo": self.tipo_atual(), "converter": self.converter,
                "pr": PropriedadesNota(self.formato.currentData(), self.inicio.value(),
                                       self.reinicio.currentData(), self.posicao.currentData())}


def pedir(pai, propriedades: dict, contagens: dict, tipo: str = "rodape") -> dict | None:
    dialogo = DialogoNotas(pai, propriedades, contagens, tipo)
    try:
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialogo.escolha()
    finally:
        dialogo.deleteLater()
