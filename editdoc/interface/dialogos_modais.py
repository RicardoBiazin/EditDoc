"""Todo dialogo modal do programa passa por estas funcoes.

Regra do CLAUDE.md: um dialogo modal aberto numa suite trava a suite. Por isso os
testes trocam estas funcoes por respostas programadas, e a janela nunca chama
QMessageBox nem QFileDialog diretamente. O nome de cada funcao diz a pergunta.
"""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QMessageBox, QSpinBox, QWidget)

from editdoc import APP
from editdoc.modelo.pagina import CORPO_MINIMO_TW, TWIPS_POR_CM, Pagina

FILTRO_DOCX = "Documento Word (*.docx)"
EXTENSAO = ".docx"
FILTRO_IMAGEM = "Imagens (*.png *.jpg *.jpeg *.gif *.bmp)"
#: Maior lado de imagem no dialogo de tamanho, em cm (o maior papel tem 176 cm).
IMAGEM_MAXIMA_CM = 100.0


def _caixa(pai: QWidget | None, titulo: str, texto: str,
           icone=QMessageBox.Icon.Question) -> QMessageBox:
    caixa = QMessageBox(pai)
    caixa.setWindowTitle(f"{titulo} - {APP}")
    caixa.setText(texto)
    caixa.setIcon(icone)
    return caixa


def pedir_abrir_arquivo(pai: QWidget | None) -> str | None:
    caminho, _filtro = QFileDialog.getOpenFileName(pai, "Abrir documento", "", FILTRO_DOCX)
    return caminho or None


def pedir_salvar_arquivo(pai: QWidget | None, sugestao: str) -> str | None:
    caminho, _filtro = QFileDialog.getSaveFileName(pai, "Salvar como", sugestao, FILTRO_DOCX)
    if not caminho:
        return None
    if not caminho.lower().endswith(EXTENSAO):
        caminho += EXTENSAO
    return caminho


def confirmar(pai: QWidget | None, titulo: str, texto: str) -> bool:
    caixa = _caixa(pai, titulo, texto)
    sim = caixa.addButton("Sim", QMessageBox.ButtonRole.YesRole)
    caixa.addButton("Não", QMessageBox.ButtonRole.NoRole)
    caixa.setDefaultButton(sim)
    caixa.exec()
    return caixa.clickedButton() is sim


def avisar(pai: QWidget | None, titulo: str, texto: str) -> None:
    caixa = _caixa(pai, titulo, texto, QMessageBox.Icon.Warning)
    caixa.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    caixa.exec()


def mostrar_detalhes(pai: QWidget | None, titulo: str, texto: str) -> None:
    caixa = _caixa(pai, titulo, texto, QMessageBox.Icon.Information)
    caixa.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    caixa.exec()


def pedir_perda(pai: QWidget | None, nome: str, linhas: list[str]) -> str:
    """'salvar', 'copia' ou 'cancelar'. `linhas` sao os textos dos avisos com perda."""
    texto = (f"Salvar \"{nome}\" vai apagar do arquivo:\n\n- "
             + "\n- ".join(linhas)
             + "\n\nSalvar mesmo assim, salvar uma cópia em outro arquivo ou cancelar?")
    caixa = _caixa(pai, "Salvar", texto, QMessageBox.Icon.Warning)
    salvar = caixa.addButton("Salvar mesmo assim", QMessageBox.ButtonRole.AcceptRole)
    copia = caixa.addButton("Salvar cópia", QMessageBox.ButtonRole.ActionRole)
    cancelar = caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    caixa.setDefaultButton(cancelar)
    caixa.exec()
    clicado = caixa.clickedButton()
    if clicado is salvar:
        return "salvar"
    if clicado is copia:
        return "copia"
    return "cancelar"


def pedir_sobrescrever(pai: QWidget | None, nome: str) -> bool:
    """True para gravar por cima de uma alteracao feita no disco por outro programa."""
    texto = (f"\"{nome}\" foi alterado por outro programa depois de aberto aqui.\n\n"
             "Salvar por cima apaga essa alteração. Sobrescrever?")
    caixa = _caixa(pai, "Arquivo alterado", texto, QMessageBox.Icon.Warning)
    sobrescrever = caixa.addButton("Sobrescrever", QMessageBox.ButtonRole.AcceptRole)
    caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    caixa.exec()
    return caixa.clickedButton() is sobrescrever


def pedir_descartar(pai: QWidget | None, nome: str) -> str:
    """'salvar', 'descartar' ou 'cancelar', ao fechar um documento com alteracoes."""
    texto = f"\"{nome}\" tem alterações que não foram salvas."
    caixa = _caixa(pai, "Fechar documento", texto)
    salvar = caixa.addButton("Salvar", QMessageBox.ButtonRole.AcceptRole)
    descartar = caixa.addButton("Descartar", QMessageBox.ButtonRole.DestructiveRole)
    cancelar = caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    caixa.setDefaultButton(salvar)
    caixa.exec()
    clicado = caixa.clickedButton()
    if clicado is salvar:
        return "salvar"
    if clicado is descartar:
        return "descartar"
    return "cancelar"


def _botoes_ok(dialogo: QDialog) -> QDialogButtonBox:
    botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
    botoes.accepted.connect(dialogo.accept)
    botoes.rejected.connect(dialogo.reject)
    return botoes


def pedir_tamanho_tabela(pai: QWidget | None, maximo_linhas: int = 2000,
                         maximo_colunas: int = 63) -> tuple[int, int] | None:
    """(linhas, colunas) da tabela nova, ou None se cancelar."""
    dialogo = QDialog(pai)
    dialogo.setWindowTitle(f"Inserir tabela - {APP}")
    grade = QFormLayout(dialogo)
    colunas = QSpinBox()
    colunas.setRange(1, maximo_colunas)
    colunas.setValue(5)
    linhas = QSpinBox()
    linhas.setRange(1, maximo_linhas)
    linhas.setValue(2)
    grade.addRow("Número de colunas:", colunas)
    grade.addRow("Número de linhas:", linhas)
    grade.addRow(_botoes_ok(dialogo))
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return None
    return linhas.value(), colunas.value()


def pedir_arquivo_imagem(pai: QWidget | None) -> str | None:
    caminho, _filtro = QFileDialog.getOpenFileName(pai, "Inserir imagem", "", FILTRO_IMAGEM)
    return caminho or None


def pedir_tamanho_imagem(pai: QWidget | None, largura_cm: float,
                         altura_cm: float) -> tuple[float, float] | None:
    """Novo (largura, altura) em cm. Com a proporcao travada (padrao), um campo segue o outro."""
    dialogo = QDialog(pai)
    dialogo.setWindowTitle(f"Tamanho da imagem - {APP}")
    grade = QFormLayout(dialogo)
    proporcao = altura_cm / largura_cm if largura_cm > 0 else 1.0
    campos = []
    for valor in (largura_cm, altura_cm):
        spin = QDoubleSpinBox()
        spin.setRange(0.1, IMAGEM_MAXIMA_CM)
        spin.setDecimals(2)
        spin.setSingleStep(0.1)
        spin.setSuffix(" cm")
        spin.setValue(round(valor, 2))
        campos.append(spin)
    largura, altura = campos
    travar = QCheckBox("Manter a proporção")
    travar.setChecked(True)
    ocupado = [False]

    def seguir(origem: QDoubleSpinBox, destino: QDoubleSpinBox, fator: float) -> None:
        if travar.isChecked() and not ocupado[0]:
            ocupado[0] = True
            destino.setValue(origem.value() * fator)
            ocupado[0] = False

    largura.valueChanged.connect(lambda _v: seguir(largura, altura, proporcao))
    altura.valueChanged.connect(lambda _v: seguir(altura, largura, 1 / proporcao))
    grade.addRow("Largura:", largura)
    grade.addRow("Altura:", altura)
    grade.addRow(travar)
    grade.addRow(_botoes_ok(dialogo))
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return None
    return largura.value(), altura.value()


def pedir_margens(pai: QWidget | None, atual: Pagina) -> Pagina | None:
    """Margens em centimetros, para a pagina `atual`. None se cancelar ou se nao couber texto."""
    dialogo = QDialog(pai)
    dialogo.setWindowTitle(f"Margens personalizadas - {APP}")
    grade = QFormLayout(dialogo)
    campos: dict[str, QDoubleSpinBox] = {}
    valores = (("Superior", atual.margem_sup_tw), ("Inferior", atual.margem_inf_tw),
               ("Esquerda", atual.margem_esq_tw), ("Direita", atual.margem_dir_tw))
    for rotulo, twips in valores:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 10.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.1)
        spin.setSuffix(" cm")
        spin.setValue(round(twips / TWIPS_POR_CM, 2))
        grade.addRow(f"{rotulo}:", spin)
        campos[rotulo] = spin
    botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
    botoes.accepted.connect(dialogo.accept)
    botoes.rejected.connect(dialogo.reject)
    grade.addRow(botoes)
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return None

    def twips(rotulo: str) -> int:
        return round(campos[rotulo].value() * TWIPS_POR_CM)

    novo = atual.com_margens(twips("Superior"), twips("Inferior"),
                             twips("Esquerda"), twips("Direita"))
    if not novo.valida():
        avisar(pai, "Margens", "As margens deixam pouco espaço para o texto. "
               f"O corpo precisa ter pelo menos {CORPO_MINIMO_TW / TWIPS_POR_CM:.0f} cm "
               "de largura e de altura.")
        return None
    return novo


def pedir_numero_inicial(pai: QWidget | None, atual: int | None,
                         maximo: int = 32767) -> tuple[bool, int | None]:
    """Numero da primeira pagina. (False, None) se cancelar; (True, None) = comecar em 1
    sem numero fixo (continua); (True, n) = comecar em n."""
    dialogo = QDialog(pai)
    dialogo.setWindowTitle(f"Numeração de páginas - {APP}")
    grade = QFormLayout(dialogo)
    fixo = QCheckBox("Começar em:")
    fixo.setChecked(atual is not None)
    valor = QSpinBox()
    valor.setRange(0, maximo)
    valor.setValue(atual if atual is not None else 1)
    valor.setEnabled(atual is not None)
    fixo.toggled.connect(valor.setEnabled)
    grade.addRow(fixo, valor)
    grade.addRow(_botoes_ok(dialogo))
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return False, None
    return True, (valor.value() if fixo.isChecked() else None)
