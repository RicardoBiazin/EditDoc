"""Exportar PDF (M7): o PDF sai do mesmo layout da tela, com texto de verdade.

- intervalo de paginas ("1-3, 5") e texto sem formatacao, sem Qt;
- PDF lido de volta por tests/leitor_pdf.py (sem biblioteca de PDF): numero de paginas
  igual ao da tela, MediaBox de A4, A4 paisagem, Carta e Oficio, texto extraivel, o
  paragrafo do alto de cada folha na folha certa, numero do rodape certo em cada folha,
  imagem do cabecalho e do corpo, fontes embutidas, metadados;
- nada da tela vai para o papel: marcas de formatacao, esmaecimento do cabecalho e o
  rotulo da edicao do cabecalho ficam fora;
- intervalo, progresso, cancelar sem tocar no arquivo que ja existia, conferencia do
  arquivo relido; o dialogo de opcoes recusa intervalo invalido;
- pela janela: Arquivo > Exportar > PDF e .txt; amostra tests/saida/amostra_m7.pdf.
"""

from __future__ import annotations

import pathlib
import time

from ajudantes import (RAIZ, checa, checa_igual, checa_levanta, drenar_eventos,
                       pasta_temporaria, preparar_qt, pular, resumir, secao, usar_fonte_windows,
                       usar_fontes_do_documento)
import fixtures_docx as fx
from leitor_pdf import ler_pdf, sem_espacos

QT = preparar_qt()

from editdoc import VERSAO  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402
from editdoc.modelo.intervalo import (analisar_intervalo, descrever_paginas,  # noqa: E402
                                      sequencia_de_copias)
from editdoc.modelo.pagina import Pagina  # noqa: E402
from editdoc.modelo.texto_plano import texto_do_documento  # noqa: E402

PASTA_AMOSTRAS = RAIZ / "tests" / "saida"


# -- sem Qt -------------------------------------------------------------------------------

def testar_intervalo() -> None:
    secao("intervalo de paginas: '1-3, 5', aberto, invalido e fora do documento")
    checa_igual(analisar_intervalo("1-3, 5", 10), [0, 1, 2, 4], "'1-3, 5' vira [0, 1, 2, 4]")
    checa_igual(analisar_intervalo("8-", 10), [7, 8, 9], "'8-' vai ate' a ultima")
    checa_igual(analisar_intervalo("-2; 2", 10), [0, 1], "'-2; 2' comeca na primeira, sem repetir")
    checa_igual(analisar_intervalo(" 4 ", 4), [3], "pagina sozinha com espacos")
    for ruim in ("", "0", "11", "3-1", "a", "1--2", "-", "1 2", "1-3-5", "9" * 600):
        checa(analisar_intervalo(ruim, 10) is None, f"{ruim[:12]!r} e' recusado")
    checa_igual(analisar_intervalo("1", 0), None, "documento sem paginas: nada")
    checa_igual(descrever_paginas([0, 1, 2, 4, 7, 8]), "1-3, 5, 8-9", "descricao do intervalo")
    checa_igual(sequencia_de_copias([0, 1], 2, True), [0, 1, 0, 1], "copias agrupadas")
    checa_igual(sequencia_de_copias([0, 1], 2, False), [0, 0, 1, 1], "copias nao agrupadas")


def testar_texto_plano() -> None:
    secao("texto sem formatacao: paragrafos, tabela com tabulacao, sem imagem")
    doc = fx.documento_com_tabela_e_imagem()
    texto = texto_do_documento(doc)
    linhas = texto.split("\r\n")
    checa_igual(linhas[0], "Tabelas e imagens", "primeira linha e' o primeiro paragrafo")
    checa_igual(linhas[1], "Imagem na linha:  e o texto continua.",
                "a imagem nao vira caractere no texto")
    checa("Título mesclado\tC1" in linhas, "linha da tabela com as celulas separadas por tabulacao")
    checa("￼" not in texto and "\n" not in texto.replace("\r\n", ""),
          "sem U+FFFC e so' CRLF")
    quebra = texto_do_documento(Documento(paragrafos=[Paragrafo(runs=[Run("a b")])]))
    checa_igual(quebra, "a\r\nb\r\n", "quebra de linha manual vira quebra de linha")


# -- com Qt -------------------------------------------------------------------------------

def _janela(modelo: Documento, caminho: str = "teste_m7.docx"):
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    janela = JanelaPrincipal(configuracao.padrao())
    janela.resize(1100, 1300)
    janela.show()
    janela.carregar(modelo, [], pathlib.Path(caminho))
    drenar_eventos()
    return janela


def _fechar(janela) -> None:
    janela.painel.documento_corpo().setModified(False)
    janela.close()
    drenar_eventos()


def _todas(layout) -> list[int]:
    return list(range(layout.numero_paginas()))


def _topos_por_pagina(layout) -> dict[int, str]:
    """Para cada folha, o comeco do primeiro "Paragrafo N:" que COMECA nela (pela tela)."""
    from PySide6.QtGui import QTextCursor
    doc = layout.doc
    dl = doc.documentLayout()
    saida: dict[int, str] = {}
    bloco = doc.begin()
    while bloco.isValid():
        texto = bloco.text()
        if texto.startswith("Parágrafo ") and QTextCursor(bloco).currentTable() is None:
            n = int(dl.blockBoundingRect(bloco).top() // layout.hb)
            saida.setdefault(n, texto.split(":")[0] + ":")
        bloco = bloco.next()
    return saida


def _sem_opacidade_parcial(dados: bytes) -> bool:
    """Nenhum ExtGState com /ca (opacidade) abaixo de 1: nada esmaecido no papel."""
    import re
    return not any(float(v) < 0.999 for v in re.findall(rb"/ca\s+([\d.]+)", dados))


def testar_pdf_da_tela() -> None:
    secao("PDF: paginas, papel, texto, numero do rodape, imagens, fontes e metadados")
    from editdoc.interface import impressao

    janela = _janela(fx.documento_m7())
    painel = janela.painel
    layout = painel.layout_pag
    total = painel.total_de_paginas()
    checa(total >= 5, f"a amostra tem varias paginas ({total})")
    inicio = time.perf_counter()
    meta = impressao.Metadados(titulo="Amostra M7", autor="Fulano de Tal")
    dados = impressao.gerar_pdf(layout, _todas(layout), meta)
    gasto = time.perf_counter() - inicio
    pdf = ler_pdf(dados)
    checa_igual(len(pdf.paginas), total, "o PDF tem o numero de paginas da tela")
    checa_igual(impressao.contar_paginas_pdf(dados), total, "contagem pelos bytes concorda")
    checa(all(p.mediabox == (0.0, 0.0, 595.0, 842.0) for p in pdf.paginas),
          f"todas as folhas em A4 retrato (MediaBox {pdf.paginas[0].mediabox})")
    checa_igual(pdf.info.get("Title"), "Amostra M7", "metadado: titulo")
    checa_igual(pdf.info.get("Author"), "Fulano de Tal", "metadado: autor")
    checa_igual(pdf.info.get("Creator"), f"EditDoc {VERSAO}", "metadado: criador com a versao")
    checa(pdf.fontes_embutidas >= 1 and pdf.fontes_sem_arquivo == [],
          f"fontes embutidas ({pdf.fontes_embutidas}), nenhuma so' por nome")
    checa(b"BT" in pdf.conteudo_bruto and b"Tj" in pdf.conteudo_bruto,
          "o texto sai como texto (BT/Tj), nao como imagem")
    checa(gasto < 10, f"{total} paginas em {gasto:.2f} s")

    textos = [sem_espacos(p.texto) for p in pdf.paginas]
    checa("Cabeçalhoerodapé(M5)" in textos[0], "titulo do documento extraivel na pagina 1")
    checa(f"Estafraseestánapágina1de{total}." in textos[0],
          "campo do corpo: 'pagina 1 de N' na folha 1")
    checa("Capa:semnúmerodepágina" in textos[0], "pagina 1: cabecalho da primeira pagina")
    topos = _topos_por_pagina(layout)
    certos = [n for n, comeco in topos.items() if sem_espacos(comeco) in textos[n]]
    checa(len(topos) >= total - 2 and len(certos) == len(topos),
          f"o paragrafo do alto de cada folha esta' na mesma folha do PDF ({len(certos)}/{len(topos)})")
    # Contraprova: a mesma conferencia acusa uma folha trocada.
    n0 = next(iter(n for n in topos if n + 1 < total))
    checa(sem_espacos(topos[n0]) not in textos[n0 + 1],
          "contraprova: o paragrafo do alto da folha nao aparece na folha seguinte")

    rodapes_ok = True
    for n in range(1, total):
        if n % 2 == 1:  # pagina par (2, 4...): rodape par, so' o numero, por ultimo
            ok = textos[n].endswith(str(n + 1)) and "Relatório" in textos[n]
        else:  # impar: "Pagina X de Y" e o cabecalho com o logotipo
            ok = (textos[n].endswith(f"Página{n + 1}de{total}")
                  and "Cabeçalhodaspáginasímpares" in textos[n] and pdf.paginas[n].imagens >= 1)
        if not ok:
            rodapes_ok = False
            print(f"         folha {n + 1}: ...{textos[n][-60:]!r}")
    checa(rodapes_ok, "cada folha tem o cabecalho e o rodape da sua variante, com o numero certo")
    checa(not textos[1].endswith("3"), "contraprova: a folha 2 nao termina com o numero 3")
    checa(pdf.paginas[0].imagens >= 1, "pagina 1: a imagem do corpo sai no PDF")
    checa("Títulomesclado" in textos[0] and "in1" in textos[0], "tabela do corpo na pagina 1")
    checa(_sem_opacidade_parcial(dados), "cabecalho e rodape sem esmaecer (opacidade 1)")

    # Nada da tela vai para o papel: marcas de formatacao ligadas e cabecalho em edicao.
    painel.definir_marcas(True)
    painel.entrar_na_faixa("cabecalho", 2)
    drenar_eventos()
    dados2 = impressao.gerar_pdf(layout, [0, 1, 2], meta)
    texto2 = ler_pdf(dados2).texto
    checa("¶" not in texto2 and "·" not in texto2, "marcas de formatacao nao vao para o PDF")
    checa("Cabeçalho - " not in texto2 and _sem_opacidade_parcial(dados2),
          "rotulo e veu da edicao do cabecalho nao vao para o PDF")
    painel.sair_da_faixa()
    painel.definir_marcas(False)

    # Contraprova das checagens de "nada da tela": a pintura da tela (esmaecida, com marcas)
    # num PDF e' acusada.
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QPainter, QPdfWriter
    from editdoc.interface.vista_paginas import desenhar_faixas, desenhar_folha
    bruto = QByteArray()
    buffer = QBuffer(bruto)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    escritor = QPdfWriter(buffer)
    escritor.setResolution(1440)
    escritor.setPageLayout(impressao.layout_de_pagina(layout.pagina_arquivo))
    p = QPainter(escritor)
    t = impressao.transformacao(1440, 1440)
    desenhar_folha(p, layout, 0, t, marcas=True)
    desenhar_faixas(p, layout, 0, t, total, 0.45)
    p.end()
    buffer.close()
    tela = bytes(bruto.data())
    checa("¶" in ler_pdf(tela).texto and not _sem_opacidade_parcial(tela),
          "contraprova: a pintura da tela (marcas, cabecalho esmaecido) e' acusada")
    _fechar(janela)


def testar_papeis() -> None:
    secao("papel e orientacao do documento: A4 paisagem, Carta, Oficio e tamanho livre")
    from editdoc.interface import impressao
    casos = (("A4 paisagem", Pagina(largura_tw=16838, altura_tw=11906, paisagem=True), (842.0, 595.0)),
             ("Carta", Pagina(largura_tw=12240, altura_tw=15840), (612.0, 792.0)),
             ("Ofício", Pagina(largura_tw=12240, altura_tw=18720), (612.0, 936.0)),
             ("livre 15 x 20 cm", Pagina(largura_tw=8504, altura_tw=11339), (425.0, 567.0)))
    for nome, pagina, esperado in casos:
        corpo = [Paragrafo(runs=[Run(f"Folha em {nome}, parágrafo {i}.")]) for i in range(60)]
        janela = _janela(Documento(pagina=pagina, paragrafos=corpo))
        layout = janela.painel.layout_pag
        pdf = ler_pdf(impressao.gerar_pdf(layout, _todas(layout), impressao.Metadados()))
        caixa = pdf.paginas[0].mediabox
        checa(abs(caixa[2] - esperado[0]) <= 1 and abs(caixa[3] - esperado[1]) <= 1
              and len(pdf.paginas) == layout.numero_paginas(),
              f"{nome}: MediaBox {caixa[2]:.0f} x {caixa[3]:.0f} pt, {len(pdf.paginas)} folha(s)")
        _fechar(janela)
    checa_igual(impressao.orientacao(Pagina()).name, "Portrait", "contraprova: A4 e' retrato")


def testar_intervalo_progresso_e_cancelar(tmp: pathlib.Path) -> None:
    secao("intervalo, progresso, cancelar sem tocar no arquivo e conferencia do arquivo relido")
    from editdoc.interface import impressao
    janela = _janela(fx.documento_m7())
    layout = janela.painel.layout_pag
    total = layout.numero_paginas()
    destino = tmp / "saida.pdf"
    chamadas: list[tuple[int, int]] = []

    def progresso(feitas: int, de: int) -> bool:
        chamadas.append((feitas, de))
        return True

    gravadas = impressao.exportar_pdf(destino, layout, [0, 2], impressao.Metadados(), progresso)
    pdf = ler_pdf(destino.read_bytes())
    checa_igual(gravadas, 2, "duas folhas exportadas")
    checa_igual(len(pdf.paginas), 2, "o PDF tem so' as folhas do intervalo")
    checa(sem_espacos(pdf.paginas[1].texto).endswith(f"Página3de{total}"),
          "a segunda folha do PDF e' a pagina 3, com o numero 3 e o total do documento")
    checa_igual(chamadas, [(0, 2), (1, 2), (2, 2)], "progresso a cada folha e no fim")

    destino.write_bytes(b"conteudo antigo")
    vistas: list[int] = []

    def cancelar_na_segunda(feitas: int, _de: int) -> bool:
        vistas.append(feitas)
        return feitas < 1

    checa_levanta(impressao.Cancelado, impressao.exportar_pdf, "cancelar levanta Cancelado",
                  destino, layout, _todas(layout), impressao.Metadados(), cancelar_na_segunda)
    checa_igual(destino.read_bytes(), b"conteudo antigo", "cancelado: o arquivo antigo fica intacto")
    checa_igual(vistas, [0, 1], "parou na segunda folha, sem pintar o resto")
    checa(not any(p.name.endswith(".ewnew") for p in tmp.iterdir()), "sem temporario sobrando")

    dados = impressao.gerar_pdf(layout, [0, 1], impressao.Metadados())
    impressao.conferir_pdf(dados, 2)
    checa(True, "conferencia aceita o PDF inteiro")
    checa_levanta(impressao.PdfInvalido, impressao.conferir_pdf, "PDF cortado e' recusado",
                  dados[: len(dados) // 2], 2)
    checa_levanta(impressao.PdfInvalido, impressao.conferir_pdf,
                  "PDF com paginas de menos e' recusado", dados, 3)
    checa_levanta(impressao.PdfInvalido, impressao.conferir_pdf, "nao-PDF e' recusado",
                  b"PK\x03\x04" + dados, 2)
    checa_levanta(ValueError, impressao.gerar_pdf, "nenhuma pagina: erro, nao PDF vazio",
                  layout, [], impressao.Metadados())
    _fechar(janela)


def testar_documento_grande() -> None:
    secao("documento grande: 200+ paginas sem travar, com progresso")
    from editdoc.interface import impressao
    corpo = [Paragrafo(runs=[Run(f"Linha {i}: " + "texto de enchimento " * 12)]) for i in range(4000)]
    janela = _janela(Documento(paragrafos=corpo))
    layout = janela.painel.layout_pag
    total = layout.numero_paginas()
    vezes = [0]

    def progresso(_f: int, _d: int) -> bool:
        vezes[0] += 1
        return True

    inicio = time.perf_counter()
    dados = impressao.gerar_pdf(layout, _todas(layout), impressao.Metadados(), progresso)
    gasto = time.perf_counter() - inicio
    checa(total >= 200, f"o documento tem {total} paginas")
    checa_igual(impressao.contar_paginas_pdf(dados), total, "todas as paginas no PDF")
    checa_igual(vezes[0], total + 1, "o progresso e' chamado a cada folha (a interface responde)")
    checa(gasto < 60, f"{total} paginas em {gasto:.1f} s ({gasto / total * 1000:.0f} ms por folha)")
    _fechar(janela)


def testar_janela(tmp: pathlib.Path) -> None:
    secao("janela: Arquivo > Exportar > PDF e .txt, abrir ao terminar, dialogo de opcoes")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLineEdit, QRadioButton
    from editdoc.interface import dialogos_modais, impressao

    janela = _janela(fx.documento_m7(), str(tmp / "relatorio.docx"))
    total = janela.painel.total_de_paginas()
    nomes = [a.text() for a in janela.botao_arquivo.menu_exportar().actions()]
    checa_igual(nomes, ["PDF...", "Texto sem formatação (.txt)..."], "submenu Exportar")
    textos_menu = [a.text() for a in janela.botao_arquivo.menu().actions()]
    checa("Imprimir..." in textos_menu and "Visualizar impressão" in textos_menu,
          "Imprimir e Visualizar impressao no menu Arquivo")

    originais = (dialogos_modais.pedir_opcoes_pdf, dialogos_modais.pedir_salvar_pdf,
                 impressao.abrir_arquivo, dialogos_modais.avisar, dialogos_modais.pedir_salvar_txt)
    abertos: list[str] = []
    sugestoes: list[str] = []
    avisos: list[str] = []
    destino = tmp / "relatorio.pdf"
    try:
        dialogos_modais.pedir_opcoes_pdf = (
            lambda _p, t, a, abrir=False: dialogos_modais.OpcoesPdf(list(range(t)), True))
        dialogos_modais.pedir_salvar_pdf = lambda _p, s: (sugestoes.append(s), str(destino))[1]
        impressao.abrir_arquivo = lambda c: (abertos.append(str(c)), True)[1]
        dialogos_modais.avisar = lambda _p, _t, texto: avisos.append(texto)
        janela.comandos.acao("exportar_pdf").trigger()
        drenar_eventos()
        checa(destino.is_file(), "o PDF foi gravado pelo menu")
        checa_igual(sugestoes, [str(tmp / "relatorio.pdf")], "sugestao: o nome do documento com .pdf")
        pdf = ler_pdf(destino.read_bytes())
        checa_igual(len(pdf.paginas), total, "todas as paginas da tela")
        checa_igual(pdf.info.get("Title"), "Amostra M7: impressão e PDF", "titulo do docProps")
        checa_igual(pdf.info.get("Author"), "Equipe EditDoc", "autor do docProps")
        checa_igual(abertos, [str(destino)], "abrir ao terminar: o PDF e' aberto")
        checa(not janela.sujo(), "exportar nao suja o documento")
        checa("relatorio.pdf" in janela.statusBar().currentMessage(), "mensagem na barra de status")

        # Destino impossivel: aviso, sem levantar.
        dialogos_modais.pedir_salvar_pdf = lambda _p, _s: str(tmp / "nao" / "existe" / "x.pdf")
        checa(not janela.exportar_pdf() and len(avisos) == 1,
              "pasta inexistente: aviso ao usuario, sem excecao")

        txt = tmp / "relatorio.txt"
        dialogos_modais.pedir_salvar_txt = lambda _p, _s: str(txt)
        janela.comandos.acao("exportar_txt").trigger()
        conteudo = txt.read_bytes().decode("utf-8")
        checa(conteudo.startswith("Cabeçalho e rodapé (M5)\r\n") and "Título mesclado\tC1" in conteudo,
              "Exportar > Texto: o texto do corpo em UTF-8")
    finally:
        (dialogos_modais.pedir_opcoes_pdf, dialogos_modais.pedir_salvar_pdf,
         impressao.abrir_arquivo, dialogos_modais.avisar, dialogos_modais.pedir_salvar_txt) = originais

    # O dialogo de opcoes de verdade: intervalo invalido e' recusado e o dialogo fica aberto.
    passos: list[str] = []
    avisos.clear()

    def responder() -> None:
        dialogo = QApplication.activeModalWidget()
        if dialogo is None:
            QTimer.singleShot(20, responder)
            return
        radios = dialogo.findChildren(QRadioButton)
        campo = dialogo.findChild(QLineEdit)
        ok = dialogo.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
        if not passos:
            passos.append("invalido")
            radios[2].setChecked(True)
            campo.setText(f"2-{total + 5}")
            ok.click()
            passos.append("aberto" if dialogo.isVisible() else "fechou")
            campo.setText("2-3, 5")
            ok.click()

    original_avisar = dialogos_modais.avisar
    dialogos_modais.avisar = lambda _p, _t, texto: avisos.append(texto)
    try:
        QTimer.singleShot(0, responder)
        opcoes = dialogos_modais.pedir_opcoes_pdf(janela, total, 0)
    finally:
        dialogos_modais.avisar = original_avisar
    checa_igual(passos, ["invalido", "aberto"], "intervalo fora do documento: o dialogo nao fecha")
    checa(len(avisos) == 1 and "inválido" in avisos[0], "e o usuario recebe o aviso")
    checa(opcoes is not None and opcoes.paginas == [1, 2, 4] and not opcoes.abrir,
          "intervalo valido '2-3, 5' volta como folhas 2, 3 e 5")
    _fechar(janela)


def testar_amostra(tmp: pathlib.Path) -> None:
    secao("amostra para conferir: tests/saida/amostra_m7.docx e amostra_m7.pdf")
    from editdoc.formato_docx.leitor import ler
    from editdoc.interface import dialogos_modais, impressao

    PASTA_AMOSTRAS.mkdir(parents=True, exist_ok=True)
    docx = PASTA_AMOSTRAS / "amostra_m7.docx"
    pdf_destino = PASTA_AMOSTRAS / "amostra_m7.pdf"
    janela = _janela(fx.documento_m7(), str(tmp / "amostra_m7.docx"))
    janela.painel.documento_corpo().setModified(True)
    originais = (dialogos_modais.pedir_salvar_arquivo, dialogos_modais.pedir_opcoes_pdf,
                 dialogos_modais.pedir_salvar_pdf)
    try:
        dialogos_modais.pedir_salvar_arquivo = lambda *_a: str(docx)
        checa(janela.salvar_como(), "a janela grava a amostra .docx")
        dialogos_modais.pedir_opcoes_pdf = (
            lambda _p, t, _a, abrir=False: dialogos_modais.OpcoesPdf(list(range(t)), False))
        dialogos_modais.pedir_salvar_pdf = lambda *_a: str(pdf_destino)
        checa(janela.exportar_pdf(), "a janela exporta a amostra .pdf")
    finally:
        (dialogos_modais.pedir_salvar_arquivo, dialogos_modais.pedir_opcoes_pdf,
         dialogos_modais.pedir_salvar_pdf) = originais
    total = janela.painel.total_de_paginas()
    pdf = ler_pdf(pdf_destino.read_bytes())
    lido, avisos = ler(docx.read_bytes())
    checa(avisos == [] and len(pdf.paginas) == total,
          f"amostras: {docx.relative_to(RAIZ)} e {pdf_destino.relative_to(RAIZ)} ({total} paginas)")
    checa_igual(impressao.contar_paginas_pdf(pdf_destino.read_bytes()), total,
                "o PDF da amostra tem as paginas da tela")
    _fechar(janela)


def testar_autoverificacao() -> None:
    secao("autoverificacao do .exe: PDF e impressao passam, e acusam PDF ruim ou sem texto")
    import app
    from PySide6.QtGui import QFontDatabase, QImage, QPainter, QPdfWriter
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from editdoc.interface import impressao

    falhas: list[str] = []
    app._pdf_e_impressao(falhas)
    checa_igual(falhas, [], "PDF e impressao em PdfFormat passam na autoverificacao")
    checa(bool(QFontDatabase.families()), "com fontes carregadas, a checagem de texto esta' ativa")

    original = impressao.gerar_pdf
    try:
        impressao.gerar_pdf = lambda *a, **k: original(*a, **k)[:-200]
        falhas = []
        app._pdf_e_impressao(falhas)
        checa(len(falhas) == 1 and "falhou" in falhas[0], "contraprova: PDF cortado e' acusado")

        def como_imagem(layout, paginas, meta, progresso=None):
            """PDF com as paginas certas, mas o texto pintado como imagem."""
            dados = QByteArray()
            buffer = QBuffer(dados)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            escritor = QPdfWriter(buffer)
            p = QPainter(escritor)
            for i, _n in enumerate(paginas):
                if i:
                    escritor.newPage()
                imagem = QImage(200, 200, QImage.Format.Format_RGB32)
                imagem.fill(0x808080)
                p.drawImage(0, 0, imagem)
            p.end()
            buffer.close()
            return bytes(dados.data())

        impressao.gerar_pdf = como_imagem
        falhas = []
        app._pdf_e_impressao(falhas)
        checa(len(falhas) == 1 and "texto" in falhas[0],
              "contraprova: PDF com o texto como imagem e' acusado")
    finally:
        impressao.gerar_pdf = original


def main() -> int:
    testar_intervalo()
    testar_texto_plano()
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    if not usar_fonte_windows(9):
        return pular("Segoe UI nao esta instalada")
    usar_fontes_do_documento()
    testar_pdf_da_tela()
    testar_papeis()
    with pasta_temporaria("editdoc-teste-pdf-") as tmp:
        testar_intervalo_progresso_e_cancelar(tmp)
        testar_janela(tmp)
        testar_amostra(tmp)
    testar_documento_grande()
    testar_autoverificacao()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
