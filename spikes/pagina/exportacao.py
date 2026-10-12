"""Spike A: PDF e pre-visualizacao usando a MESMA funcao de pintura da tela.

A folha e pintada por vista.desenhar_conteudo_folha(). O que muda e so a
transformacao: twip -> dispositivo = dpi_do_dispositivo / 1440.
"""
import os

from PySide6.QtCore import QMarginsF, QPointF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter, QTransform
from PySide6.QtPrintSupport import QPrintPreviewWidget, QPrinter

from vista import desenhar_conteudo_folha


def _transformacao_para(dpi: float) -> QTransform:
    s = dpi / 1440.0
    return QTransform().scale(s, s)


def exportar_pdf(layout, cabecalho, caminho: str, resolucao: int = 1440) -> int:
    """Escreve o PDF e devolve o numero de paginas escritas."""
    w = QPdfWriter(caminho)
    w.setResolution(resolucao)
    w.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    w.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    w.setTitle("EditDoc spike")
    p = QPainter(w)
    n_paginas = layout.numero_paginas()
    t = _transformacao_para(resolucao)
    for n in range(n_paginas):
        if n > 0:
            w.newPage()
        desenhar_conteudo_folha(p, layout, n, t, cabecalho)
    p.end()
    return n_paginas


def pintar_pagina_em(painter, layout, cabecalho, n: int, dpi: float) -> None:
    """Pinta a pagina n com a transformacao de impressao para o dpi dado."""
    desenhar_conteudo_folha(painter, layout, n, _transformacao_para(dpi), cabecalho)


def criar_previa(layout, cabecalho, parent=None):
    """QPrintPreviewWidget cujo paintRequested usa a mesma funcao de folha."""
    prn = QPrinter(QPrinter.PrinterMode.HighResolution)
    prn.setResolution(1440)
    prn.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    prn.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    prev = QPrintPreviewWidget(prn, parent)
    # O widget guarda so um ponteiro para o QPrinter. Sem esta referencia o
    # Python coleta o printer ao sair daqui e o primeiro show() derruba o processo
    # (exit 127, sem traceback). Mesma causa do C13.
    prev._printer_ref = prn

    def pintar(printer):
        p = QPainter(printer)
        n_paginas = layout.numero_paginas()
        t = _transformacao_para(printer.resolution())
        for n in range(n_paginas):
            if n > 0:
                printer.newPage()
            desenhar_conteudo_folha(p, layout, n, t, cabecalho)
        p.end()

    prev.paintRequested.connect(pintar)
    return prev


def contar_paginas_pdf(caminho: str) -> int:
    """Conta objetos /Type /Page (sem /Pages) lendo os bytes do arquivo."""
    import re
    with open(caminho, "rb") as f:
        dados = f.read()
    return len(re.findall(rb"/Type\s*/Page(?![s\w])", dados))
