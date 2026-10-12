"""Imprimir e visualizar impressao (M7), sem impressora real: QPrinter em PdfFormat.

- impressao direta: folhas, papel do documento, intervalo, pagina atual, copias
  agrupadas e nao agrupadas (lidas pelo numero do rodape de cada folha do PDF);
- Ctrl+P com a tecla de verdade: dialogo do sistema trocado por resposta programada,
  impressora em PdfFormat; sem impressora instalada: aviso, nada mais; impressora que
  nao aceita o papel: pergunta, e "nao" nao imprime; cancelar no meio: nada enviado;
- pre-visualizacao (Ctrl+F2): as folhas da tela, navegacao e zoom; o papel e' o do
  documento; a pintura e' a mesma do PDF.

Nenhum teste aqui manda trabalho para impressora instalada.
"""

from __future__ import annotations

import pathlib

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt, pular,
                       resumir, secao, usar_fonte_windows, usar_fontes_do_documento)
import fixtures_docx as fx
from leitor_pdf import ler_pdf, sem_espacos

QT = preparar_qt()

from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402
from editdoc.modelo.pagina import Pagina  # noqa: E402


def _janela(modelo: Documento):
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    janela = JanelaPrincipal(configuracao.padrao())
    janela.resize(1100, 1300)
    janela.show()
    janela.carregar(modelo, [], pathlib.Path("teste_m7.docx"))
    drenar_eventos()
    return janela


def _fechar(janela) -> None:
    janela.painel.documento_corpo().setModified(False)
    janela.close()
    drenar_eventos()


def _impressora_pdf(caminho: pathlib.Path):
    from editdoc.interface import impressao
    impressora = impressao.nova_impressora(pdf=True)
    impressora.setOutputFileName(str(caminho))
    return impressora


def _numeros_do_rodape(dados: bytes, total: int) -> list[str]:
    """O numero de cada folha impressa, lido do fim do texto (o rodape e' pintado por ultimo).

    Pagina 1 (capa) nao tem rodape: vale "capa". Impar: "Pagina X de Y". Par: so' o numero.
    """
    saida = []
    for p in ler_pdf(dados).paginas:
        t = sem_espacos(p.texto)
        if t.endswith("Capa:semnúmerodepágina"):
            saida.append("capa")
            continue
        sufixo = f"de{total}"
        if t.endswith(sufixo):
            t = t[: -len(sufixo)]
        num = ""
        while t and t[-1].isdigit():
            num = t[-1] + num
            t = t[:-1]
        saida.append(num or "?")
    return saida


def testar_impressao_direta(tmp: pathlib.Path) -> None:
    secao("impressao em PdfFormat: folhas, papel, intervalo, pagina atual e copias")
    from PySide6.QtGui import QPageRanges
    from PySide6.QtPrintSupport import QPrinter
    from editdoc.interface import impressao

    janela = _janela(fx.documento_m7())
    layout = janela.painel.layout_pag
    total = layout.numero_paginas()
    todas = list(range(total))
    esperado = ["capa"] + [str(n + 1) for n in range(1, total)]

    destino = tmp / "tudo.pdf"
    impressora = _impressora_pdf(destino)
    checa(impressao.configurar_impressora(impressora, layout.pagina_arquivo),
          "a impressora PDF aceita o papel do documento (A4)")
    checa_igual(impressao.paginas_da_impressora(impressora, total, 3), todas,
                "sem escolha no dialogo: todas as folhas")
    checa_igual(impressao.imprimir(impressora, layout, todas), total, "todas as folhas enviadas")
    dados = destino.read_bytes()
    checa_igual(impressao.contar_paginas_pdf(dados), total, "o trabalho tem as folhas da tela")
    checa(all(p.mediabox == (0.0, 0.0, 595.0, 842.0) for p in ler_pdf(dados).paginas),
          "papel A4 em todas as folhas")
    checa_igual(_numeros_do_rodape(dados, total), esperado, "cada folha com o seu numero")
    checa(_numeros_do_rodape(dados, total) != esperado[::-1],
          "contraprova: a leitura do rodape distingue a ordem")
    gerado = impressao.gerar_pdf(layout, todas, impressao.Metadados())
    checa_igual([sem_espacos(p.texto) for p in ler_pdf(dados).paginas],
                [sem_espacos(p.texto) for p in ler_pdf(gerado).paginas],
                "impressao e exportacao pintam o mesmo texto em cada folha")

    impressora = _impressora_pdf(tmp / "intervalo.pdf")
    impressao.configurar_impressora(impressora, layout.pagina_arquivo)
    impressora.setPrintRange(QPrinter.PrintRange.PageRange)
    faixas = QPageRanges()
    faixas.addRange(2, 3)
    faixas.addPage(5)
    impressora.setPageRanges(faixas)
    paginas = impressao.paginas_da_impressora(impressora, total, 0)
    checa_igual(paginas, [1, 2, 4], "intervalo '2-3, 5' do dialogo")
    impressao.imprimir(impressora, layout, paginas)
    checa_igual(_numeros_do_rodape((tmp / "intervalo.pdf").read_bytes(), total), ["2", "3", "5"],
                "so' as folhas do intervalo, com o numero delas")

    impressora = _impressora_pdf(tmp / "atual.pdf")
    impressora.setPrintRange(QPrinter.PrintRange.CurrentPage)
    checa_igual(impressao.paginas_da_impressora(impressora, total, 3), [3], "pagina atual")

    for agrupar, nome, ordem in ((True, "agrupadas", ["2", "3", "2", "3"]),
                                 (False, "nao agrupadas", ["2", "2", "3", "3"])):
        caminho = tmp / f"copias_{agrupar}.pdf"
        impressora = _impressora_pdf(caminho)
        impressao.configurar_impressora(impressora, layout.pagina_arquivo)
        impressora.setCopyCount(2)
        impressora.setCollateCopies(agrupar)
        checa(not impressora.supportsMultipleCopies(), "o PDF nao faz copias sozinho")
        impressao.imprimir(impressora, layout, [1, 2])
        checa_igual(_numeros_do_rodape(caminho.read_bytes(), total), ordem, f"2 copias {nome}")

    paisagem = Pagina(largura_tw=16838, altura_tw=11906, paisagem=True)
    impressora = _impressora_pdf(tmp / "paisagem.pdf")
    impressao.configurar_impressora(impressora, paisagem)
    checa_igual(impressora.pageLayout().orientation().name, "Landscape",
                "documento em paisagem: impressora em paisagem")
    checa_igual(impressao.descrever_papel(Pagina()), "A4 (21,0 x 29,7 cm)", "descricao do papel")
    _fechar(janela)


class _Barra:
    """BarraDeProgresso de mentira: cancela na folha `parar`."""

    def __init__(self, *_a, parar: int | None = None) -> None:
        self.parar = parar
        self.fechada = False
        self.vistas: list[int] = []

    def __call__(self, feitas: int, _total: int) -> bool:
        self.vistas.append(feitas)
        return self.parar is None or feitas < self.parar

    def fechar(self) -> None:
        self.fechada = True


def testar_janela(tmp: pathlib.Path) -> None:
    secao("Ctrl+P: dialogo, papel, sem impressora e cancelar; Ctrl+F2: pre-visualizacao")
    from PySide6.QtCore import Qt
    from PySide6.QtPrintSupport import QPrinter, QPrintPreviewWidget
    from PySide6.QtTest import QTest
    from editdoc.interface import dialogos_modais, impressao

    janela = _janela(fx.documento_m7())
    painel = janela.painel
    total = painel.total_de_paginas()
    destino = tmp / "ctrl_p.pdf"
    pedidos: list[tuple] = []
    avisos: list[str] = []
    perguntas: list[str] = []
    respostas = {"confirmar": True}
    barras: list[_Barra] = []
    originais = (impressao.impressoras, impressao.nova_impressora, dialogos_modais.pedir_impressao,
                 dialogos_modais.avisar, dialogos_modais.confirmar, impressao.configurar_impressora,
                 impressao.BarraDeProgresso, dialogos_modais.mostrar_previa)
    configurar_de_verdade = impressao.configurar_impressora

    def pedir(_pai, impressora, total_, atual) -> bool:
        pedidos.append((total_, atual, impressora.pageLayout().pageSize().name()))
        impressora.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        impressora.setOutputFileName(str(destino))
        return True

    def nova_barra(*args, **_kw):
        barra = _Barra(*args)
        barras.append(barra)
        return barra

    try:
        impressao.impressoras = lambda: ["Impressora de teste"]
        impressao.nova_impressora = lambda pdf=False: originais[1](pdf=True)
        dialogos_modais.pedir_impressao = pedir
        dialogos_modais.avisar = lambda _p, _t, texto: avisos.append(texto)
        dialogos_modais.confirmar = lambda _p, _t, texto: (perguntas.append(texto),
                                                           respostas["confirmar"])[1]
        impressao.BarraDeProgresso = nova_barra

        QTest.keyClick(painel, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier)
        drenar_eventos()
        checa_igual(len(pedidos), 1, "Ctrl+P abre o dialogo de impressao")
        checa(pedidos and pedidos[0][0] == total and pedidos[0][2] == "A4",
              "o dialogo recebe o total de paginas e a impressora ja' com A4")
        checa(destino.is_file() and impressao.contar_paginas_pdf(destino.read_bytes()) == total,
              "Ctrl+P imprime todas as folhas")
        checa(barras and barras[-1].fechada and barras[-1].vistas[-1] == total,
              "a barra de progresso acompanha e fecha no fim")
        checa("Enviado para" in janela.statusBar().currentMessage(), "mensagem de envio")
        checa(not janela.sujo(), "imprimir nao suja o documento")

        # Impressora que nao aceita o papel: pergunta; "nao" nao imprime nada.
        destino.unlink()
        impressao.configurar_impressora = lambda imp, pag: (configurar_de_verdade(imp, pag), False)[1]
        respostas["confirmar"] = False
        checa(not janela.imprimir(), "papel recusado e usuario diz nao: nao imprime")
        checa(len(perguntas) == 1 and "A4 (21,0 x 29,7 cm)" in perguntas[0],
              "a pergunta diz o papel do documento")
        checa(not destino.exists(), "nada foi enviado")
        respostas["confirmar"] = True
        checa(janela.imprimir() and destino.is_file(), "papel recusado e usuario diz sim: imprime")
        impressao.configurar_impressora = configurar_de_verdade

        # Cancelar no meio.
        destino.unlink()
        impressao.BarraDeProgresso = lambda *a, **_k: (barras.append(_Barra(*a, parar=2)), barras[-1])[1]
        checa(not janela.imprimir(), "cancelar na barra: imprimir devolve False")
        checa(barras[-1].vistas == [0, 1, 2] and barras[-1].fechada,
              "parou na terceira folha e fechou a barra")
        checa("cancelada" in janela.statusBar().currentMessage(), "mensagem de cancelado")
        impressao.BarraDeProgresso = nova_barra

        # Sem impressora instalada: aviso claro e nada mais.
        pedidos.clear()
        avisos.clear()
        impressao.impressoras = lambda: []
        QTest.keyClick(painel, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier)
        drenar_eventos()
        checa(len(avisos) == 1 and "Nenhuma impressora" in avisos[0] and "PDF" in avisos[0],
              "sem impressora: aviso que sugere o PDF")
        checa_igual(pedidos, [], "sem impressora: o dialogo de impressao nem abre")

        # Pre-visualizacao.
        vistas: list[dict] = []

        def espiar(dialogo) -> None:
            previa = dialogo.findChild(QPrintPreviewWidget)
            previa.updatePreview()
            info = {"paginas": previa.pageCount(), "papel": dialogo._impressora.pageLayout()}
            previa.setCurrentPage(3)
            info["atual"] = previa.currentPage()
            zoom = previa.zoomFactor()
            previa.zoomIn(1.5)
            info["zoom"] = previa.zoomFactor() > zoom
            info["titulo"] = dialogo.windowTitle()
            vistas.append(info)

        dialogos_modais.mostrar_previa = espiar
        QTest.keyClick(painel, Qt.Key.Key_F2, Qt.KeyboardModifier.ControlModifier)
        drenar_eventos()
        checa_igual(len(vistas), 1, "Ctrl+F2 abre a pre-visualizacao")
        if vistas:
            checa_igual(vistas[0]["paginas"], total, "a previa tem as folhas da tela")
            checa_igual(vistas[0]["papel"].pageSize().name(), "A4", "papel da previa: A4")
            checa_igual(vistas[0]["atual"], 3, "navegar para a pagina 3")
            checa(vistas[0]["zoom"], "zoom na previa")
            checa("Visualizar impressão" in vistas[0]["titulo"], "titulo em portugues")
    finally:
        (impressao.impressoras, impressao.nova_impressora, dialogos_modais.pedir_impressao,
         dialogos_modais.avisar, dialogos_modais.confirmar, impressao.configurar_impressora,
         impressao.BarraDeProgresso, dialogos_modais.mostrar_previa) = originais
    _fechar(janela)


def testar_dialogo_do_sistema() -> None:
    secao("dialogo Imprimir: intervalo, pagina atual, copias agrupadas e limite de paginas")
    from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog
    from editdoc.interface import dialogos_modais, impressao

    vistos: list = []
    original = QPrintDialog.exec
    QPrintDialog.exec = lambda self: (vistos.append(
        (self.options(), self.minPage(), self.maxPage(), self.windowTitle())), 0)[1]
    try:
        aceito = dialogos_modais.pedir_impressao(None, impressao.nova_impressora(pdf=True), 7, 2)
    finally:
        QPrintDialog.exec = original
    opcao = QAbstractPrintDialog.PrintDialogOption
    checa(not aceito and len(vistos) == 1, "cancelar o dialogo devolve False")
    if vistos:
        opcoes, minimo, maximo, titulo = vistos[0]
        checa(all(opcoes & o for o in (opcao.PrintPageRange, opcao.PrintCurrentPage,
                                       opcao.PrintCollateCopies)),
              "o dialogo oferece intervalo, pagina atual e agrupar copias")
        checa_igual((minimo, maximo), (1, 7), "intervalo limitado as paginas do documento")
        checa_igual(titulo, "Imprimir - EditDoc", "titulo em portugues")


def testar_previa_em_paisagem() -> None:
    secao("pre-visualizacao de documento em paisagem: papel e folhas")
    from PySide6.QtPrintSupport import QPrintPreviewWidget
    from editdoc.interface import impressao

    corpo = [Paragrafo(runs=[Run(f"Paisagem {i}.")]) for i in range(80)]
    janela = _janela(Documento(pagina=Pagina(largura_tw=16838, altura_tw=11906, paisagem=True),
                               paragrafos=corpo))
    layout = janela.painel.layout_pag
    impressora = impressao.nova_impressora(pdf=True)
    impressao.configurar_impressora(impressora, layout.pagina_arquivo)
    dialogo = impressao.criar_previa(janela, layout, impressora)
    previa = dialogo.findChild(QPrintPreviewWidget)
    previa.updatePreview()
    checa_igual(previa.pageCount(), layout.numero_paginas(), "folhas da previa = folhas da tela")
    checa_igual(impressora.pageLayout().orientation().name, "Landscape", "previa em paisagem")
    dialogo.deleteLater()
    drenar_eventos()
    _fechar(janela)


def main() -> int:
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    if not usar_fonte_windows(9):
        return pular("Segoe UI nao esta instalada")
    usar_fontes_do_documento()
    with pasta_temporaria("editdoc-teste-impressao-") as tmp:
        testar_impressao_direta(tmp)
        testar_janela(tmp)
    testar_dialogo_do_sistema()
    testar_previa_em_paisagem()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
