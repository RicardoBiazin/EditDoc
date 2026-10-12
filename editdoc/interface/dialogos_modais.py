"""Todo dialogo modal do programa passa por estas funcoes.

Regra do CLAUDE.md: um dialogo modal aberto numa suite trava a suite. Por isso os
testes trocam estas funcoes por respostas programadas, e a janela nunca chama
QMessageBox nem QFileDialog diretamente. O nome de cada funcao diz a pergunta.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from editdoc import APP

FILTRO_DOCX = "Documento Word (*.docx)"
EXTENSAO = ".docx"


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
