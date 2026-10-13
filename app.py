"""Ponto de entrada do EditDoc.

    python app.py
    python app.py arquivo.docx outro.docx
    python app.py --autoverificacao

Com arquivos na linha de comando, a instancia que ja esta aberta recebe os
caminhos e esta' sai; se nao ha nenhuma aberta, o programa abre uma janela por
arquivo.

--autoverificacao nao mostra janela para o usuario: importa os modulos
obrigatorios, carrega a traducao, faz uma ida-e-volta de .docx e constroi a janela
principal, exporta um PDF (M7) e grava e le uma copia de recuperacao numa pasta temporaria
(M8). O build.bat o roda dentro do .exe antes de entregar; se algo faltou no
empacotamento, aparece aqui. Sai com 0 quando passa e com 1 quando falha.

Na abertura normal, depois das janelas, o programa oferece as copias de recuperacao que
sobraram de uma queda (M8) e aplica o tema das preferencias.
"""

from __future__ import annotations

import importlib
import os
import sys

from editdoc import APP, VERSAO, configuracao, idioma, log_interno, recursos

#: O que o executavel precisa ter embutido. Um modulo esquecido no `.spec` some
#: sem erro de empacotamento e so' quebra quando o programa usa essa parte.
OBRIGATORIOS = (
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtPrintSupport",
    "PySide6.QtSvg",
    "lxml.etree",
    "editdoc.configuracao",
    "editdoc.idioma",
    "editdoc.cli",
    "editdoc.instancia_unica",
    "editdoc.armazenamento.gravacao",
    "editdoc.formato_docx.leitor",
    "editdoc.formato_docx.escritor",
    "editdoc.formato_docx.conferencia",
    "editdoc.ponte_qt.para_qt",
    "editdoc.ponte_qt.de_qt",
    "editdoc.interface.janela_principal",
    "editdoc.interface.gerente",
    "editdoc.interface.vista_paginas",
    "editdoc.interface.painel_documento",
    "editdoc.interface.regua",
    "editdoc.interface.controle_zoom",
    "editdoc.modelo.pagina",
    "editdoc.modelo.folhas",
    "editdoc.modelo.imagem",
    "editdoc.ponte_qt.imagens",
    "editdoc.ponte_qt.vetoriais",
    "editdoc.ponte_qt.propriedades",
    "editdoc.formato_docx.propriedades",
    "editdoc.edicao.tabelas",
    "editdoc.edicao.imagens",
    "editdoc.interface.seletor_grade",
    "editdoc.interface.impressao",
    "editdoc.modelo.intervalo",
    "editdoc.modelo.texto_plano",
    "editdoc.recuperacao",
    "editdoc.interface.guarda_recuperacao",
    "editdoc.interface.dialogo_recuperacao",
    "editdoc.interface.dialogo_opcoes",
    "editdoc.interface.acessibilidade",
    "editdoc.interface.dicas_teclas",
    "editdoc.interface.tema",
)

#: Formatos de imagem que o .docx traz e o Qt precisa decodificar. JPEG, GIF e TIFF vem de
#: plugins (imageformats/qjpeg.dll, qgif.dll, qtiff.dll): sem eles a imagem vira quadro cinza.
#: O SVG (0.1.5) vem do QtSvg (Qt6Svg.dll), conferido renderizando um.
FORMATOS_DE_IMAGEM = ("png", "jpeg", "gif", "bmp", "tiff")

AUMID = "RicardoBiazin.EditDoc"


def _identidade_na_barra_de_tarefas() -> None:
    """Sem um AppUserModelID proprio, o Windows pode agrupar o programa sob o
    python.exe e mostrar o icone errado na barra de tarefas."""
    if sys.platform != "win32":
        return
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(AUMID)


def _ida_e_volta_docx(falhas: list[str]) -> None:
    """Escreve um .docx e le de volta, sem Qt: pega lxml ou zipfile ausentes no .exe.

    Desde o M4 a ida-e-volta leva uma tabela, que precisa voltar como tabela.
    """
    from editdoc.formato_docx.escritor import escrever
    from editdoc.formato_docx.leitor import ler
    from editdoc.modelo.documento import Celula, Documento, Linha, Paragrafo, Run, Tabela

    try:
        tabela = Tabela(colunas_tw=[2000], linhas=[Linha(celulas=[Celula(
            blocos=[Paragrafo(runs=[Run("celula")])])])])
        ida = Documento(paragrafos=[Paragrafo(runs=[Run("autoverificacao", negrito=True)]),
                                    tabela])
        lido, _avisos = ler(escrever(ida))
        if [p.runs[0].texto for p in lido.paragrafos
                if isinstance(p, Paragrafo) and p.runs] != ["autoverificacao"]:
            falhas.append("ida-e-volta do .docx nao confere")
        if not any(isinstance(b, Tabela) for b in lido.paragrafos):
            falhas.append("a tabela nao voltou do .docx como tabela")
    except Exception as erro:  # noqa: BLE001 - interessa o motivo, qualquer um
        falhas.append(f"ida-e-volta do .docx falhou: {erro}")


def _formatos_de_imagem(falhas: list[str]) -> None:
    """Os plugins de imagem do Qt estao no pacote (JPEG e GIF sao plugins)."""
    from PySide6.QtGui import QImageReader

    suportados = {bytes(f).decode("ascii", "replace").lower()
                  for f in QImageReader.supportedImageFormats()}
    for formato in FORMATOS_DE_IMAGEM:
        if formato not in suportados:
            falhas.append(f"o Qt nao decodifica {formato}: falta o plugin de imagem no pacote")
    _previas_vetoriais(falhas)


def _previas_vetoriais(falhas: list[str]) -> None:
    """0.1.5: TIFF (plugin), SVG (QtSvg) e, no Windows, EMF e WMF (GDI) viram previa."""
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QColor, QImage

        from editdoc.ponte_qt import vetoriais
        amostra = QImage(24, 12, QImage.Format.Format_RGB32)
        amostra.fill(QColor("#204080"))
        dados = QByteArray()
        buffer = QBuffer(dados)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        amostra.save(buffer, "TIFF")
        buffer.close()
        casos = [("TIFF", bytes(dados.data()), "#204080"),
                 ("SVG", b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
                         b'<rect width="20" height="10" fill="#00a000"/></svg>', "#00a000")]
        if sys.platform == "win32":
            casos += [("EMF", vetoriais.metafile_de_exemplo("emf"), "#e00000"),
                      ("WMF", vetoriais.metafile_de_exemplo("wmf"), "#e00000")]
        for nome, bruto, cor in casos:
            img = vetoriais.renderizar(bruto)
            if img.isNull() or vetoriais.cor_dominante(img).name() != cor:
                falhas.append(f"a previa de {nome} nao foi renderizada (plugin ou modulo faltando)")
    except Exception as erro:  # noqa: BLE001 - interessa o motivo, qualquer um
        falhas.append(f"previa de imagem vetorial falhou: {erro}")


def _pdf_e_impressao(falhas: list[str]) -> None:
    """Exporta um PDF de duas paginas e imprime numa impressora PDF, sem mostrar nada.

    Pega o que so' o executavel congelado pode perder: o QtPrintSupport, o motor de PDF
    do QtGui e as fontes. Com fontes no sistema (o .exe de verdade), exige texto como
    texto e fonte embutida; no offscreen da suite, sem fontes, confere so' as paginas.
    """
    import re
    import tempfile

    from PySide6.QtGui import QFontDatabase

    from editdoc.interface import impressao
    from editdoc.interface.layout_paginado import LayoutPaginado
    from editdoc.modelo.documento import Documento, Paragrafo, Run
    from editdoc.modelo.pagina import Pagina
    from editdoc.ponte_qt import para_qt

    layout = None
    try:
        modelo = Documento(paragrafos=[Paragrafo(runs=[Run("autoverificacao do PDF")]),
                                       Paragrafo(runs=[Run("segunda pagina")], quebra_antes=True)],
                           rodapes={"padrao": [Paragrafo(runs=[Run("1", campo="PAGE")])]})
        layout = LayoutPaginado(Pagina(), "Arial", 11)
        para_qt.preencher(layout.doc, modelo)
        layout.faixas.carregar(modelo)
        paginas = list(range(layout.numero_paginas()))
        dados = impressao.gerar_pdf(layout, paginas, impressao.Metadados("autoverificacao"))
        impressao.conferir_pdf(dados, 2)
        if QFontDatabase.families():
            conteudo = b"".join(_inflar(m) for m in re.findall(
                rb"/FlateDecode\s*>>\s*stream\r?\n(.*?)endstream", dados, re.S))
            if b"Tj" not in conteudo or b"/FontFile2" not in dados:
                falhas.append("o PDF nao traz texto com fonte embutida")
        with tempfile.TemporaryDirectory(prefix="editdoc-autoverificacao-") as pasta:
            destino = f"{pasta}/impressao.pdf"
            impressora = impressao.nova_impressora(pdf=True)
            impressora.setOutputFileName(destino)
            impressao.configurar_impressora(impressora, Pagina())
            impressao.imprimir(impressora, layout, paginas)
            with open(destino, "rb") as arquivo:
                impressao.conferir_pdf(arquivo.read(), 2)
    except Exception as erro:  # noqa: BLE001 - interessa o motivo, qualquer um
        falhas.append(f"exportar PDF ou imprimir falhou: {erro}")
    finally:
        if layout is not None:
            layout.fechar()


def _recuperacao(falhas: list[str], pasta: str) -> None:
    """Grava uma copia de recuperacao na pasta temporaria, simula a queda e le de volta.

    A queda e' soltar a trava sem apagar a copia: e' o que o Windows faz quando o processo
    morre. Pega o msvcrt (trava) e a gravacao atomica no executavel congelado.
    """
    import pathlib

    from editdoc import recuperacao
    from editdoc.formato_docx.escritor import escrever
    from editdoc.formato_docx.leitor import ler
    from editdoc.modelo.documento import Documento, Paragrafo, Run

    try:
        base = pathlib.Path(pasta)
        sessao = recuperacao.Sessao(base=base)
        dados = escrever(Documento(paragrafos=[Paragrafo(runs=[Run("texto recuperado")])]))
        if not sessao.gravar(dados, None, "Autoverificacao.docx"):
            falhas.append("a recuperacao automatica nao gravou a copia")
            return
        if recuperacao.listar_orfas(base):
            falhas.append("a copia de uma janela viva foi oferecida como orfa")
        sessao._trava.soltar(apagar=False)  # a "queda"
        orfas = recuperacao.listar_orfas(base)
        if [c.id for c in orfas] != [sessao.id]:
            falhas.append("a copia que sobrou da queda nao foi encontrada")
            return
        lido, _ = ler(orfas[0].ler())
        if [r.texto for p in lido.paragrafos for r in p.runs] != ["texto recuperado"]:
            falhas.append("a copia de recuperacao nao le de volta o texto gravado")
        recuperacao.apagar_copia(sessao.id, base)
        if any(base.iterdir()):
            falhas.append("descartar a copia deixou arquivos na pasta de recuperacao")
    except Exception as erro:  # noqa: BLE001 - interessa o motivo, qualquer um
        falhas.append(f"recuperacao automatica falhou: {erro}")


def _inflar(bruto: bytes) -> bytes:
    """Descomprime o que der: o corte pelo "endstream" pode levar um byte a mais."""
    import zlib
    try:
        return zlib.decompressobj().decompress(bruto)
    except zlib.error:
        return b""


def autoverificacao() -> int:
    import shutil
    import tempfile

    from editdoc import recuperacao

    # A recuperacao da autoverificacao vai para uma pasta temporaria, nunca para a do usuario.
    pasta_rec = tempfile.mkdtemp(prefix="editdoc-autoverificacao-rec-")
    anterior = os.environ.get(recuperacao.VARIAVEL_PASTA)
    os.environ[recuperacao.VARIAVEL_PASTA] = pasta_rec
    try:
        return _autoverificacao(pasta_rec)
    finally:
        if anterior is None:
            os.environ.pop(recuperacao.VARIAVEL_PASTA, None)
        else:
            os.environ[recuperacao.VARIAVEL_PASTA] = anterior
        shutil.rmtree(pasta_rec, ignore_errors=True)


def _autoverificacao(pasta_rec: str) -> int:
    log = log_interno.obter("autoverificacao")
    falhas: list[str] = []

    for modulo in OBRIGATORIOS:
        try:
            importlib.import_module(modulo)
        except Exception as erro:  # noqa: BLE001 - interessa o motivo, qualquer um
            falhas.append(f"modulo {modulo} nao importa: {erro}")

    if not recursos.caminho("icone.ico").is_file():
        falhas.append("icone.ico nao esta' em editdoc/recursos")

    _ida_e_volta_docx(falhas)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    if "qtbase_pt_BR" not in idioma.instalar(app):
        falhas.append("traducao qtbase_pt_BR nao carregou: botoes sairiam em ingles")

    _formatos_de_imagem(falhas)
    _pdf_e_impressao(falhas)
    _recuperacao(falhas, pasta_rec)

    try:
        from editdoc.interface.janela_principal import JanelaPrincipal
        JanelaPrincipal(configuracao.carregar()).close()
    except Exception as erro:  # noqa: BLE001
        falhas.append(f"janela principal nao constroi: {erro}")

    for falha in falhas:
        log.error("AUTOVERIFICACAO: %s", falha)
    if falhas:
        log.error("autoverificacao FALHOU (%d problema(s))", len(falhas))
        return 1
    log.info("autoverificacao OK: %s %s", APP, VERSAO)
    return 0


def main(argv: list[str]) -> int:
    if "--autoverificacao" in argv:
        return autoverificacao()

    from editdoc import cli
    pedido = cli.analisar(argv)
    if pedido.ajuda:
        print(cli.AJUDA)
        return 0

    log_interno.configurar()
    log_interno.instalar_captura_de_erros()
    log_interno.registrar_partida(VERSAO)
    _identidade_na_barra_de_tarefas()
    log = log_interno.obter("app")
    for argumento, motivo in pedido.recusados:
        log.warning("argumento recusado: %r (%s)", argumento, motivo)

    from PySide6.QtWidgets import QApplication

    from editdoc import instancia_unica
    from editdoc.interface.gerente import GerenteDeJanelas

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP)
    app.setApplicationVersion(VERSAO)
    idioma.instalar(app)

    caminhos = [os.path.abspath(a) for a in pedido.arquivos]
    pedido_para_outra = {"arquivos": caminhos} if caminhos else {"novo": True}
    if instancia_unica.entregar(pedido_para_outra):
        log.info("pedido entregue a uma instancia ja aberta: saindo")
        return 0

    cfg = configuracao.carregar()
    gerente = GerenteDeJanelas(cfg, app)
    servidor = instancia_unica.Servidor(app)
    servidor.pedido_recebido.connect(gerente.receber_pedido)
    if not servidor.escutar():
        log.warning("outra instancia tem o canal: esta abre como janela comum")

    from editdoc.interface import tema
    tema.aplicar(cfg.get("tema", "sistema"), app)

    for caminho in caminhos:
        gerente.abrir(caminho)
    if not gerente.janelas():
        gerente.novo()
    # Copias de recuperacao que sobraram de uma queda (M8): o dialogo nao e' modal.
    gerente.oferecer_recuperacao()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
