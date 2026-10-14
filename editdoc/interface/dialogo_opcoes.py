"""Arquivo > Opções (M8): as preferencias do EditDoc.

O dialogo so' mostra e devolve os valores; quem grava (`configuracao.gravar_preferencias`,
que valida tudo de novo) e aplica nas janelas abertas e' a janela e o gerente. O que vale
para documento novo (fonte, tamanho, papel) nao muda o documento que ja' esta' aberto.

Fonte: no offscreen sem a fonte instalada, `QFontComboBox.setCurrentFont` mostra outra
(ver CLAUDE.md). A fonte so' muda se o usuario mexer no combo.
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFontComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from editdoc import APP, configuracao
from editdoc.modelo.comentarios import iniciais_de

UNIDADES = (("cm", "Centímetros"), ("pol", "Polegadas"))
TEMAS = (("sistema", "Igual ao Windows"), ("claro", "Claro"), ("escuro", "Escuro"))


class DialogoOpcoes(QDialog):
    def __init__(self, valores: dict, pai: QWidget | None = None) -> None:
        super().__init__(pai)
        self.setWindowTitle(f"Opções - {APP}")
        self.setAccessibleName("Opções do EditDoc")
        self._valores = configuracao.validar(valores)
        self._fonte_mexida = False
        self.limpar_recentes = False
        v = self._valores

        # -- documento novo
        self.fonte = QFontComboBox()
        self.fonte.setCurrentFont(QFont(v["fonte_padrao"]))
        self.fonte.currentFontChanged.connect(self._fonte_mudou)
        self.tamanho = QDoubleSpinBox()
        self.tamanho.setRange(1.0, 400.0)
        self.tamanho.setDecimals(1)
        self.tamanho.setSingleStep(0.5)
        self.tamanho.setSuffix(" pt")
        self.tamanho.setValue(float(v["tamanho_padrao"]))
        self.papel = QComboBox()
        self.papel.addItems(list(configuracao.PAPEIS))
        self.papel.setCurrentText(v["papel_padrao"])
        novo = QGroupBox("Documento novo")
        f_novo = QFormLayout(novo)
        f_novo.addRow("&Fonte:", self.fonte)
        f_novo.addRow("&Tamanho:", self.tamanho)
        f_novo.addRow("&Papel:", self.papel)

        # -- exibicao
        self.unidade = QComboBox()
        for chave, nome in UNIDADES:
            self.unidade.addItem(nome, chave)
        self.unidade.setCurrentIndex([c for c, _ in UNIDADES].index(v["unidade_regua"]))
        self.tema = QComboBox()
        for chave, nome in TEMAS:
            self.tema.addItem(nome, chave)
        self.tema.setCurrentIndex([c for c, _ in TEMAS].index(v["tema"]))
        exibir = QGroupBox("Exibição")
        f_exibir = QFormLayout(exibir)
        f_exibir.addRow("&Unidade da régua:", self.unidade)
        f_exibir.addRow("T&ema:", self.tema)

        # -- salvar
        self.recuperacao = QCheckBox("Salvar a recuperação automática a cada")
        self.recuperacao.setChecked(v["recuperacao_ligada"])
        self.minutos = QSpinBox()
        self.minutos.setRange(1, 120)
        self.minutos.setSuffix(" min")
        self.minutos.setValue(v["recuperacao_minutos"])
        self.minutos.setEnabled(v["recuperacao_ligada"])
        self.minutos.setAccessibleName("Intervalo da recuperação automática, em minutos")
        self.recuperacao.toggled.connect(self.minutos.setEnabled)
        self.abrir_pdf = QCheckBox("Abrir o PDF depois de exportar")
        self.abrir_pdf.setChecked(v["abrir_pdf_depois"])
        salvar = QGroupBox("Salvar e exportar")
        f_salvar = QVBoxLayout(salvar)
        linha = QHBoxLayout()
        linha.addWidget(self.recuperacao)
        linha.addWidget(self.minutos)
        linha.addStretch(1)
        f_salvar.addLayout(linha)
        f_salvar.addWidget(self.abrir_pdf)

        # -- usuario (0.1.6): autor e iniciais dos comentarios
        from editdoc.edicao.comentarios import nome_do_windows
        windows = nome_do_windows()
        self.nome_usuario = QLineEdit(v["nome_usuario"])
        self.nome_usuario.setMaxLength(255)
        self.nome_usuario.setPlaceholderText(windows)
        self.nome_usuario.setAccessibleName("Nome de usuário")
        self.nome_usuario.setAccessibleDescription(
            "Autor dos comentários. Vazio usa o nome do usuário do Windows")
        self.iniciais = QLineEdit(v["iniciais"])
        self.iniciais.setMaxLength(9)
        self.iniciais.setPlaceholderText(iniciais_de(windows))
        self.iniciais.setAccessibleName("Iniciais")
        self.iniciais.setAccessibleDescription(
            "Iniciais dos comentários. Vazio usa as iniciais do nome")
        usuario = QGroupBox("Usuário (comentários)")
        f_usuario = QFormLayout(usuario)
        f_usuario.addRow("&Nome de usuário:", self.nome_usuario)
        f_usuario.addRow("Inic&iais:", self.iniciais)

        # -- recentes
        self.recentes = QSpinBox()
        self.recentes.setRange(0, configuracao.LIMITE_RECENTES)
        self.recentes.setValue(v["recentes_maximo"])
        self.botao_limpar = QPushButton("&Limpar a lista")
        self.botao_limpar.setAccessibleDescription(
            "Apaga a lista de documentos recentes ao confirmar com OK")
        self.botao_limpar.clicked.connect(self._limpar)
        self._aviso_limpar = QLabel("")
        recentes = QGroupBox("Documentos recentes")
        f_recentes = QFormLayout(recentes)
        f_recentes.addRow("&Quantidade no menu Abrir recente:", self.recentes)
        f_recentes.addRow(self.botao_limpar, self._aviso_limpar)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                  | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        self.botoes = botoes

        vertical = QVBoxLayout(self)
        for grupo in (novo, exibir, usuario, salvar, recentes):
            vertical.addWidget(grupo)
        vertical.addWidget(botoes)
        self.fonte.setFocus()

    def _fonte_mudou(self, _fonte) -> None:
        self._fonte_mexida = True

    def _limpar(self) -> None:
        self.limpar_recentes = True
        self._aviso_limpar.setText("A lista será apagada ao confirmar.")
        self.botao_limpar.setEnabled(False)

    def escolher_fonte(self, familia: str) -> None:
        """Para os testes: a fonte escolhida, como se o usuario mexesse no combo."""
        self._fonte_mexida = True
        self._familia_escolhida = familia

    def valores(self) -> dict:
        """O que o usuario escolheu, no formato do config (ainda sem gravar)."""
        familia = self._valores["fonte_padrao"]
        if self._fonte_mexida:
            familia = getattr(self, "_familia_escolhida", None) or self.fonte.currentFont().family()
        tamanho = self.tamanho.value()
        return {
            "fonte_padrao": familia,
            "tamanho_padrao": int(tamanho) if float(tamanho).is_integer() else tamanho,
            "papel_padrao": self.papel.currentText(),
            "unidade_regua": self.unidade.currentData(),
            "tema": self.tema.currentData(),
            "recuperacao_ligada": self.recuperacao.isChecked(),
            "recuperacao_minutos": self.minutos.value(),
            "abrir_pdf_depois": self.abrir_pdf.isChecked(),
            "recentes_maximo": self.recentes.value(),
            "nome_usuario": " ".join(self.nome_usuario.text().split())[:255],
            "iniciais": "".join(self.iniciais.text().split())[:9],
            "limpar_recentes": self.limpar_recentes,
        }
