"""Todo dialogo modal do programa passa por estas funcoes.

Regra do CLAUDE.md: um dialogo modal aberto numa suite trava a suite. Por isso os
testes trocam estas funcoes por respostas programadas, e a janela nunca chama
QMessageBox nem QFileDialog diretamente. O nome de cada funcao diz a pergunta.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QLineEdit, QMessageBox, QRadioButton, QSpinBox,
                               QWidget)

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


def texto_da_falha_na_conferencia(nome: str, log: str) -> str:
    """O que o usuario le quando a releitura do arquivo gravado nao bate (0.1.11)."""
    return (f"Não foi possível salvar \"{nome}\".\n\n"
            "Antes de substituir um arquivo, o EditDoc grava uma cópia e a lê de volta. "
            "Desta vez a cópia lida não ficou igual ao documento na tela, e por isso nada foi "
            "substituído: o arquivo original NÃO foi alterado, e o documento continua aberto "
            "aqui, com as suas alterações.\n\n"
            "Você pode salvar essa cópia, sem a conferência, em outro arquivo e abri-la no Word "
            "para conferir. O detalhe técnico foi registrado no log do EditDoc:\n" + log)


def pedir_falha_na_conferencia(pai: QWidget | None, nome: str, log: str) -> str:
    """'copia' (salvar a copia nao conferida em outro arquivo) ou 'fechar'."""
    caixa = _caixa(pai, "Salvar", texto_da_falha_na_conferencia(nome, log),
                   QMessageBox.Icon.Warning)
    copia = caixa.addButton("Salvar cópia não conferida...", QMessageBox.ButtonRole.ActionRole)
    fechar = caixa.addButton("Fechar", QMessageBox.ButtonRole.RejectRole)
    caixa.setDefaultButton(fechar)
    caixa.exec()
    return "copia" if caixa.clickedButton() is copia else "fechar"


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
    valor.setAccessibleName("Número da primeira página")
    fixo.toggled.connect(valor.setEnabled)
    grade.addRow(fixo, valor)
    grade.addRow(_botoes_ok(dialogo))
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return False, None
    return True, (valor.value() if fixo.isChecked() else None)


def pedir_valor_numeracao(pai: QWidget | None, atual: int, maximo: int = 32767) -> int | None:
    """Definir valor de numeracao (0.1.4): o numero deste item. None se cancelar."""
    dialogo = QDialog(pai)
    dialogo.setWindowTitle(f"Definir valor de numeração - {APP}")
    grade = QFormLayout(dialogo)
    valor = QSpinBox()
    valor.setRange(0, maximo)
    valor.setValue(max(0, min(int(atual), maximo)))
    valor.setAccessibleName("Definir valor como")
    grade.addRow("Definir valor como:", valor)
    grade.addRow(_botoes_ok(dialogo))
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return None
    return valor.value()


# -- impressao e PDF (M7) -------------------------------------------------------------

FILTRO_PDF = "Documento PDF (*.pdf)"
FILTRO_TXT = "Texto sem formatação (*.txt)"


@dataclass
class OpcoesPdf:
    #: folhas a exportar, indices a partir de 0
    paginas: list[int]
    #: abrir o PDF no leitor padrao depois de gravar
    abrir: bool = False


def _com_extensao(caminho: str, extensao: str) -> str:
    return caminho if caminho.lower().endswith(extensao) else caminho + extensao


def pedir_opcoes_pdf(pai: QWidget | None, total: int, atual: int,
                     abrir: bool = False) -> OpcoesPdf | None:
    """Paginas (todas, a atual ou um intervalo como "1-3, 5") e "abrir ao terminar"."""
    from editdoc.modelo.intervalo import analisar_intervalo

    dialogo = QDialog(pai)
    dialogo.setWindowTitle(f"Exportar PDF - {APP}")
    grade = QFormLayout(dialogo)
    todas = QRadioButton(f"Todas ({total} página{'s' if total != 1 else ''})")
    todas.setChecked(True)
    so_atual = QRadioButton(f"Página atual ({atual + 1})")
    intervalo = QRadioButton("Páginas:")
    campo = QLineEdit()
    campo.setPlaceholderText("por exemplo: 1-3, 5")
    campo.setMaxLength(200)
    campo.setAccessibleName("Intervalo de páginas")
    campo.setAccessibleDescription("Por exemplo: 1-3, 5")
    campo.textEdited.connect(lambda _t: intervalo.setChecked(True))
    grade.addRow(todas)
    grade.addRow(so_atual)
    grade.addRow(intervalo, campo)
    abrir_depois = QCheckBox("Abrir o PDF depois de exportar")
    abrir_depois.setChecked(abrir)
    grade.addRow(abrir_depois)
    escolha: list[list[int]] = []

    def aceitar() -> None:
        if todas.isChecked():
            escolha[:] = [list(range(total))]
        elif so_atual.isChecked():
            escolha[:] = [[atual]]
        else:
            paginas = analisar_intervalo(campo.text(), total)
            if paginas is None:
                avisar(dialogo, "Exportar PDF", "Intervalo de páginas inválido. Use números "
                       f"de 1 a {total}, separados por vírgula, como 1-3, 5.")
                campo.setFocus()
                return
            escolha[:] = [paginas]
        dialogo.accept()

    botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
    botoes.accepted.connect(aceitar)
    botoes.rejected.connect(dialogo.reject)
    grade.addRow(botoes)
    if dialogo.exec() != QDialog.DialogCode.Accepted or not escolha:
        return None
    return OpcoesPdf(paginas=escolha[0], abrir=abrir_depois.isChecked())


def pedir_salvar_pdf(pai: QWidget | None, sugestao: str) -> str | None:
    caminho, _filtro = QFileDialog.getSaveFileName(pai, "Exportar PDF", sugestao, FILTRO_PDF)
    return _com_extensao(caminho, ".pdf") if caminho else None


def pedir_salvar_txt(pai: QWidget | None, sugestao: str) -> str | None:
    caminho, _filtro = QFileDialog.getSaveFileName(pai, "Exportar texto", sugestao, FILTRO_TXT)
    return _com_extensao(caminho, ".txt") if caminho else None


def pedir_impressao(pai: QWidget | None, impressora, total: int, atual: int) -> bool:
    """Dialogo Imprimir do sistema: impressora, intervalo, copias e agrupar. True = imprimir."""
    from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog

    dialogo = QPrintDialog(impressora, pai)
    dialogo.setWindowTitle(f"Imprimir - {APP}")
    opcoes = QAbstractPrintDialog.PrintDialogOption
    dialogo.setOptions(opcoes.PrintPageRange | opcoes.PrintCurrentPage
                       | opcoes.PrintCollateCopies | opcoes.PrintShowPageSize)
    dialogo.setMinMax(1, max(1, total))
    return dialogo.exec() == QDialog.DialogCode.Accepted


def mostrar_previa(dialogo) -> None:
    """A pre-visualizacao e' modal: fica aberta ate' o usuario fechar ou imprimir."""
    dialogo.exec()


# -- preferencias e recuperacao (M8) -------------------------------------------------

def pedir_opcoes(pai: QWidget | None, valores: dict) -> dict | None:
    """Arquivo > Opções. As preferencias escolhidas (com "limpar_recentes"), ou None."""
    from editdoc.interface.dialogo_opcoes import DialogoOpcoes

    dialogo = DialogoOpcoes(valores, pai)
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialogo.valores()


def mostrar_recuperacao(dialogo) -> None:
    """O dialogo de recuperacao nao e' modal: aparece e o programa segue."""
    dialogo.show()
    dialogo.raise_()
    dialogo.activateWindow()


# -- hiperlinks (0.1.3) ----------------------------------------------------------------

def confirmar_abrir_link(pai: QWidget | None, url: str) -> bool:
    """Endereco que nao e' de pagina da Web nem de e-mail (arquivo, rede, outro programa):
    so' abre com o Sim do usuario. O padrao e' Nao."""
    curto = url if len(url) <= 300 else url[:300] + "…"
    caixa = _caixa(pai, "Abrir link",
                   "Este link não é de uma página da Web nem de e-mail:\n\n"
                   f"{curto}\n\nLinks assim podem abrir arquivos ou programas do computador. "
                   "Abrir mesmo assim?", QMessageBox.Icon.Warning)
    sim = caixa.addButton("Abrir", QMessageBox.ButtonRole.YesRole)
    nao = caixa.addButton("Não abrir", QMessageBox.ButtonRole.NoRole)
    caixa.setDefaultButton(nao)
    caixa.exec()
    return caixa.clickedButton() is sim


def pedir_link(pai: QWidget | None, texto: str, link=None, marcadores=(),
               editar: bool = False):
    """Inserir (ou editar) link: (texto exibido, Link) ou None se cancelar.

    O destino e' um endereco (pagina da Web, e-mail ou arquivo) ou um marcador do documento.
    """
    from PySide6.QtWidgets import QComboBox

    from editdoc.modelo.documento import Link
    from editdoc.ponte_qt.links import endereco_normalizado

    dialogo = QDialog(pai)
    dialogo.setWindowTitle(f"{'Editar' if editar else 'Inserir'} link - {APP}")
    grade = QFormLayout(dialogo)
    exibido = QLineEdit(texto.replace(" ", " ").replace(" ", " "))
    exibido.setMaxLength(4000)
    exibido.setAccessibleName("Texto para exibir")
    grade.addRow("&Texto para exibir:", exibido)
    externo = QRadioButton("&Endereço (página da Web, e-mail ou arquivo)")
    endereco = QLineEdit(link.url if link is not None and link.url else "")
    endereco.setPlaceholderText("https://... ou nome@exemplo.com")
    endereco.setMaxLength(2000)
    endereco.setAccessibleName("Endereço do link")
    interno = QRadioButton("&Lugar neste documento (marcador)")
    lista = QComboBox()
    lista.addItems(list(marcadores))
    lista.setAccessibleName("Marcador do documento")
    if link is not None and link.interno() and link.ancora in marcadores:
        lista.setCurrentIndex(list(marcadores).index(link.ancora))
    interno.setEnabled(bool(marcadores))
    lista.setEnabled(bool(marcadores))
    (interno if link is not None and link.interno() and marcadores else externo).setChecked(True)
    endereco.textEdited.connect(lambda _t: externo.setChecked(True))
    lista.activated.connect(lambda _i: interno.setChecked(True))
    grade.addRow(externo)
    grade.addRow("Endereço:", endereco)
    grade.addRow(interno)
    grade.addRow("Marcador:", lista)
    escolha: list = []

    def aceitar() -> None:
        if interno.isChecked() and lista.currentText():
            novo = Link(ancora=lista.currentText(),
                        historico=link.historico if link is not None else True)
        else:
            url = endereco_normalizado(endereco.text())
            if url is None:
                avisar(dialogo, "Link", "Digite o endereço do link ou escolha um marcador.")
                endereco.setFocus()
                return
            novo = Link(url=url, dica=link.dica if link is not None else None,
                        historico=link.historico if link is not None else True)
        mostrado = exibido.text() or (novo.url or novo.ancora or "")
        escolha[:] = [(mostrado, novo)]
        dialogo.accept()

    botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
    botoes.accepted.connect(aceitar)
    botoes.rejected.connect(dialogo.reject)
    grade.addRow(botoes)
    exibido.setFocus()
    if dialogo.exec() != QDialog.DialogCode.Accepted or not escolha:
        return None
    return escolha[0]
