"""Impressao, pre-visualizacao e PDF (M7): a pagina impressa vem do MESMO layout da tela.

Uma funcao pinta a folha n em qualquer QPainter (`pintar_pagina`): o corpo por
`desenhar_folha` e o cabecalho e o rodape por `desenhar_faixas`, as mesmas da tela. Fica
de fora o que so' a tela tem: fundo cinza, sombra, marcas de formatacao, linha de quebra
de pagina, veu e rotulo da edicao do cabecalho, caret, selecao e alcas de imagem. O
cabecalho sai com opacidade 1 (na tela, fora da edicao, ele e' esmaecido).

Escala: o layout e' em twips (1440 dpi). O dispositivo tem o seu dpi; a transformacao
e' dpi / 1440. O QPdfWriter roda a 1440 dpi: a escala e' 1 e o PDF tem as mesmas
coordenadas do layout. O texto sai como texto (Tj com fonte TrueType embutida em
subconjunto), nao como imagem.

O PDF e' montado na memoria (QBuffer) e gravado com a troca atomica de
`armazenamento/gravacao.py`, com conferencia do arquivo relido. Cancelar no meio nao
deixa arquivo pela metade: nada e' gravado.

Ciclo de vida (Spike A, C13): o QPainter termina antes de o dispositivo morrer, e a
pre-visualizacao guarda a referencia do QPrinter (o QPrintPreviewDialog guarda so' um
ponteiro; o Python coletaria o objeto e o primeiro show() derrubaria o processo).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QSizeF, QUrl
from PySide6.QtGui import (QDesktopServices, QPageLayout, QPageSize, QPainter, QPdfWriter,
                           QTransform)

from editdoc import APP, VERSAO, log_interno
from editdoc.armazenamento import gravacao
from editdoc.interface.layout_paginado import DPI_LAYOUT, LayoutPaginado
from editdoc.interface.vista_paginas import desenhar_faixas, desenhar_folha
from editdoc.modelo.intervalo import sequencia_de_copias
from editdoc.modelo.pagina import Pagina

log = log_interno.obter(__name__)

#: Resolucao do PDF: a do layout. Escala 1, sem arredondamento entre tela e PDF.
DPI_PDF = DPI_LAYOUT

#: Progresso: recebe (feitas, total) e devolve False para cancelar.
Progresso = Callable[[int, int], bool]


class Cancelado(Exception):
    """O usuario cancelou a exportacao ou a impressao no meio."""


class FalhaNaImpressao(Exception):
    """A impressora (ou o arquivo PDF) nao pode ser aberta para pintar."""


class PdfInvalido(ValueError):
    """O PDF relido do disco nao confere com o que foi pintado."""


@dataclass
class Metadados:
    titulo: str = ""
    autor: str = ""
    criador: str = f"{APP} {VERSAO}"


# -- geometria ------------------------------------------------------------------------

def tamanho_do_papel(pagina: Pagina) -> QPageSize:
    """O papel da pagina, em retrato. Casa com A4, Carta etc. quando o tamanho bate."""
    a, b = sorted((pagina.largura_tw, pagina.altura_tw))
    return QPageSize(QSizeF(a / 20.0, b / 20.0), QPageSize.Unit.Point, "",
                     QPageSize.SizeMatchPolicy.FuzzyMatch)


def orientacao(pagina: Pagina) -> QPageLayout.Orientation:
    if pagina.largura_tw > pagina.altura_tw:
        return QPageLayout.Orientation.Landscape
    return QPageLayout.Orientation.Portrait


def layout_de_pagina(pagina: Pagina) -> QPageLayout:
    """Papel e orientacao do documento, sem margem: a folha inteira e' do EditDoc."""
    return QPageLayout(tamanho_do_papel(pagina), orientacao(pagina), QMarginsF(0, 0, 0, 0),
                       QPageLayout.Unit.Point)


def transformacao(dpi_x: float, dpi_y: float) -> QTransform:
    """Leva twips da folha para pixels do dispositivo."""
    return QTransform().scale(dpi_x / DPI_LAYOUT, dpi_y / DPI_LAYOUT)


def pagina_da_folha(layout: LayoutPaginado, n: int) -> Pagina:
    """Papel da folha n. Hoje o documento tem uma secao: todas iguais. Fica por folha para
    que o PDF ja' troque de papel no meio quando houver varias secoes."""
    return layout.pagina_arquivo


def preparar(layout: LayoutPaginado) -> bool:
    """Campos do corpo com o total de paginas atual. True se o layout mudou (limpar cache)."""
    return layout.atualizar_campos()


def pintar_pagina(painter: QPainter, layout: LayoutPaginado, n: int, total: int,
                  transf: QTransform) -> None:
    """A folha n como sai no papel: corpo, cabecalho e rodape, sem nada da tela."""
    desenhar_folha(painter, layout, n, transf)
    desenhar_faixas(painter, layout, n, transf, total, 1.0)


def _pintar_sequencia(painter: QPainter, nova_pagina: Callable[[int], None],
                      layout: LayoutPaginado, sequencia: list[int],
                      progresso: Progresso | None) -> None:
    """Pinta as folhas da sequencia, uma por pagina do dispositivo. Levanta Cancelado."""
    total = layout.numero_paginas()
    dispositivo = painter.device()
    for i, n in enumerate(sequencia):
        if progresso is not None and not progresso(i, len(sequencia)):
            raise Cancelado()
        if i > 0:
            nova_pagina(n)
        transf = transformacao(dispositivo.logicalDpiX(), dispositivo.logicalDpiY())
        pintar_pagina(painter, layout, n, total, transf)
    if progresso is not None:
        progresso(len(sequencia), len(sequencia))


# -- PDF ------------------------------------------------------------------------------

def gerar_pdf(layout: LayoutPaginado, paginas: list[int], meta: Metadados,
              progresso: Progresso | None = None) -> bytes:
    """O PDF das folhas `paginas` (indices a partir de 0), na memoria."""
    if not paginas:
        raise ValueError("nenhuma pagina para exportar")
    preparar(layout)
    dados = QByteArray()
    buffer = QBuffer(dados)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    escritor = QPdfWriter(buffer)
    escritor.setResolution(DPI_PDF)
    escritor.setTitle(meta.titulo)
    escritor.setAuthor(meta.autor)
    escritor.setCreator(meta.criador)
    atual = layout_de_pagina(pagina_da_folha(layout, paginas[0]))
    escritor.setPageLayout(atual)

    def nova_pagina(n: int) -> None:
        nonlocal atual
        proximo = layout_de_pagina(pagina_da_folha(layout, n))
        if not proximo.isEquivalentTo(atual):
            escritor.setPageLayout(proximo)
            atual = proximo
        escritor.newPage()

    painter = QPainter()
    if not painter.begin(escritor):
        buffer.close()
        raise FalhaNaImpressao("o PDF nao pode ser iniciado")
    try:
        _pintar_sequencia(painter, nova_pagina, layout, paginas, progresso)
    finally:
        # O painter termina ANTES de o escritor e o buffer morrerem (C13).
        painter.end()
        buffer.close()
    return bytes(dados.data())


def contar_paginas_pdf(dados: bytes) -> int:
    """Objetos /Type /Page (sem o /Pages) nos bytes do PDF."""
    return len(re.findall(rb"/Type\s*/Page(?![s\w])", dados))


def conferir_pdf(dados: bytes, paginas: int) -> None:
    """Levanta PdfInvalido se os bytes nao sao um PDF inteiro com `paginas` paginas."""
    if not dados.startswith(b"%PDF-"):
        raise PdfInvalido("nao comeca com %PDF-")
    if b"%%EOF" not in dados[-64:]:
        raise PdfInvalido("sem %%EOF no fim: arquivo cortado")
    achadas = contar_paginas_pdf(dados)
    if achadas != paginas:
        raise PdfInvalido(f"{achadas} paginas no arquivo, {paginas} esperadas")


def exportar_pdf(caminho, layout: LayoutPaginado, paginas: list[int], meta: Metadados,
                 progresso: Progresso | None = None) -> int:
    """Gera e grava o PDF com a troca atomica. Devolve o numero de paginas gravadas.

    Cancelado, FalhaNaImpressao e os erros de gravacao (OSError, SemEspaco,
    FalhaNaTroca, PdfInvalido) propagam; em todos o arquivo de destino fica como estava.
    """
    dados = gerar_pdf(layout, paginas, meta, progresso)
    gravacao.gravar_bytes(caminho, dados, conferir=lambda relido: conferir_pdf(relido, len(paginas)))
    log.info("PDF exportado: %d pagina(s), %d bytes", len(paginas), len(dados))
    return len(paginas)


def abrir_arquivo(caminho) -> bool:
    """Abre o arquivo no programa padrao do Windows (o leitor de PDF). Sem shell."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(caminho)))


# -- impressora -----------------------------------------------------------------------

def impressoras() -> list[str]:
    """Nomes das impressoras instaladas. Vazio: nao ha onde imprimir."""
    from PySide6.QtPrintSupport import QPrinterInfo
    return [p.printerName() for p in QPrinterInfo.availablePrinters()]


def nova_impressora(pdf: bool = False):
    """QPrinter de alta resolucao. `pdf`: saida em arquivo PDF (testes, e sem impressora)."""
    from PySide6.QtPrintSupport import QPrinter
    impressora = QPrinter(QPrinter.PrinterMode.HighResolution)
    if pdf:
        impressora.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    impressora.setCreator(f"{APP} {VERSAO}")
    return impressora


def configurar_impressora(impressora, pagina: Pagina) -> bool:
    """Papel e orientacao do documento na impressora. False se ela nao tem o papel.

    A folha inteira e' do EditDoc (`setFullPage`): a origem do pintor e' o canto do papel,
    e as margens do documento ja' estao no layout. Margem zero pode ser recusada pela
    impressora (area nao imprimivel); isso nao impede a impressao.
    """
    impressora.setFullPage(True)
    papel = tamanho_do_papel(pagina)
    aceitou = impressora.setPageSize(papel)
    impressora.setPageOrientation(orientacao(pagina))
    impressora.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Point)
    obtido = impressora.pageLayout().pageSize()
    return bool(aceitou) and obtido.isEquivalentTo(papel)


def descrever_papel(pagina: Pagina) -> str:
    """'A4 (21,0 x 29,7 cm)' para as mensagens."""
    nome = pagina.nome_do_papel() or "Personalizado"
    larg = pagina.largura_tw / 1440 * 2.54
    alt = pagina.altura_tw / 1440 * 2.54
    return f"{nome} ({larg:.1f} x {alt:.1f} cm)".replace(".", ",")


def paginas_da_impressora(impressora, total: int, atual: int) -> list[int]:
    """As folhas que o dialogo de impressao escolheu (todas, a atual ou um intervalo)."""
    from PySide6.QtPrintSupport import QPrinter
    faixa = impressora.printRange()
    if faixa == QPrinter.PrintRange.CurrentPage:
        return [min(max(atual, 0), total - 1)]
    if faixa == QPrinter.PrintRange.PageRange:
        intervalos = impressora.pageRanges()
        if not intervalos.isEmpty():
            return [n for n in range(total) if intervalos.contains(n + 1)]
        de, ate = impressora.fromPage(), impressora.toPage()
        if de > 0:
            return list(range(de - 1, min(ate or total, total)))
    return list(range(total))


def imprimir(impressora, layout: LayoutPaginado, paginas: list[int],
             progresso: Progresso | None = None) -> int:
    """Pinta as folhas na impressora ja' configurada. Devolve as folhas enviadas.

    Copias: se o driver faz as copias (`supportsMultipleCopies`), manda uma vez; senao
    (PDF, por exemplo) repete as folhas, agrupadas ou nao, como o usuario pediu.
    Cancelado aborta o trabalho (`QPrinter.abort`).
    """
    if not paginas:
        return 0
    preparar(layout)
    copias = max(1, impressora.copyCount())
    if impressora.supportsMultipleCopies() or copias == 1:
        sequencia = list(paginas)
    else:
        sequencia = sequencia_de_copias(paginas, copias, impressora.collateCopies())
    painter = QPainter()
    if not painter.begin(impressora):
        raise FalhaNaImpressao("a impressora nao pode ser aberta")
    try:
        _pintar_sequencia(painter, lambda _n: impressora.newPage(), layout, sequencia,
                          progresso)
    except Cancelado:
        impressora.abort()
        raise
    finally:
        painter.end()
    log.info("impressao: %d folha(s) enviadas", len(sequencia))
    return len(sequencia)


def criar_previa(pai, layout: LayoutPaginado, impressora, atual: int = 0,
                 progresso_de: Callable[[int], Progresso | None] | None = None):
    """QPrintPreviewDialog que pinta com a mesma funcao da impressao.

    O botao Imprimir da previa chama o mesmo `paintRequested` com a impressora escolhida
    no dialogo dela; o intervalo e as copias de la' valem.
    """
    from PySide6.QtPrintSupport import QPrintPreviewDialog
    dialogo = QPrintPreviewDialog(impressora, pai)
    dialogo.setWindowTitle(f"Visualizar impressão - {APP}")
    # Sem esta referencia o Python coleta o QPrinter e o primeiro show() derruba o processo.
    dialogo._impressora = impressora

    def pintar(alvo) -> None:
        total = layout.numero_paginas()
        paginas = paginas_da_impressora(alvo, total, atual)
        progresso = progresso_de(len(paginas)) if progresso_de is not None else None
        try:
            imprimir(alvo, layout, paginas, progresso)
        except Cancelado:
            log.info("previa ou impressao cancelada")
        except FalhaNaImpressao as erro:
            log.error("previa: %s", erro)
        finally:
            fechar = getattr(progresso, "fechar", None)
            if fechar is not None:
                fechar()

    dialogo.paintRequested.connect(pintar)
    dialogo._pintar = pintar
    return dialogo


class BarraDeProgresso:
    """QProgressDialog com Cancelar, no formato de `Progresso`. So' aparece se demorar."""

    def __init__(self, pai, titulo: str, texto: str, total: int) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QProgressDialog
        self._dialogo = QProgressDialog(texto, "Cancelar", 0, max(1, total), pai)
        self._dialogo.setWindowTitle(f"{titulo} - {APP}")
        self._dialogo.setWindowModality(Qt.WindowModality.WindowModal)
        self._dialogo.setMinimumDuration(400)
        self._dialogo.setAutoClose(True)
        self._dialogo.setAutoReset(False)
        self._texto = texto

    def __call__(self, feitas: int, total: int) -> bool:
        self._dialogo.setMaximum(max(1, total))
        if feitas < total:
            self._dialogo.setLabelText(f"{self._texto} Página {feitas + 1} de {total}.")
        # setValue num dialogo modal processa eventos: a janela continua respondendo.
        self._dialogo.setValue(feitas)
        return not self._dialogo.wasCanceled()

    def fechar(self) -> None:
        self._dialogo.reset()
        self._dialogo.close()
        self._dialogo.deleteLater()

    def dialogo(self):
        return self._dialogo
