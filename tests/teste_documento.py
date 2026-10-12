"""Janelas e fluxo de arquivo: novo, abrir, editar, salvar, reabrir, salvar como, recentes,
barra de aviso, perda confirmada, falha de gravacao injetada, arquivo alterado no disco,
fechar com alteracao pendente e recusa de extensoes.

Todo dialogo modal e' trocado por resposta programada (dialogos_modais). Nenhuma
janela termina com alteracao pendente sem resposta: um modal aberto trava a suite.
"""

from __future__ import annotations

import contextlib
import os
import pathlib

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt,
                       pular, resumir, secao)
import fixtures_docx as fx

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from editdoc import VERSAO, configuracao  # noqa: E402
from editdoc.armazenamento import gravacao  # noqa: E402
from editdoc.formato_docx import conferencia  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.interface import dialogos_modais, gerente as modulo_gerente  # noqa: E402
from editdoc.interface.gerente import GerenteDeJanelas  # noqa: E402
from editdoc.interface.janela_principal import titulo_da_janela  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402
from editdoc.ponte_qt import de_qt  # noqa: E402

SUFIXO_TITULO = f" - EditDoc {VERSAO}"


@contextlib.contextmanager
def dialogos(**substitutos):
    """Troca dialogos_modais.<nome> pelas funcoes dadas, e devolve tudo ao fim."""
    originais = {nome: getattr(dialogos_modais, nome) for nome in substitutos}
    for nome, funcao in substitutos.items():
        setattr(dialogos_modais, nome, funcao)
    try:
        yield
    finally:
        for nome, funcao in originais.items():
            setattr(dialogos_modais, nome, funcao)


def proibido(nome: str):
    def _falha(*_a, **_k):
        raise AssertionError(f"dialogo inesperado: {nome}")
    return _falha


def documento_simples() -> Documento:
    return Documento(paragrafos=[
        Paragrafo(runs=[Run("Primeira linha", negrito=True)]),
        Paragrafo(runs=[Run("Segunda linha")]),
    ])


def docx_com_tabela_e_quebra() -> bytes:
    """Amostra com recursos que o M2 avisa e nao edita: tabela e quebra de pagina."""
    base = fx.bytes_de(documento_simples())
    xml = fx.partes_de(base)["word/document.xml"]
    tabela = (b'<w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="2000"/></w:tblGrid>'
              b'<w:tr><w:tc><w:p><w:r><w:t>celula</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
              b'<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
    novo = xml.replace(b"<w:sectPr", tabela + b"<w:sectPr", 1)
    return fx.com_parte(base, "word/document.xml", novo)


def texto_do_arquivo(caminho: pathlib.Path) -> list[str]:
    modelo, _ = ler(caminho.read_bytes())
    return ["".join(r.texto for r in p.runs) for p in modelo.paragrafos]


def gravar(caminho: pathlib.Path, dados: bytes) -> pathlib.Path:
    caminho.write_bytes(dados)
    return caminho


def janela_limpa(gerente: GerenteDeJanelas) -> None:
    """Fecha tudo, sem perguntar: so' para o fim de cada teste."""
    with dialogos(pedir_descartar=lambda *_a: "descartar"):
        for janela in gerente.janelas():
            janela.close()
    drenar_eventos()


def testar_titulo() -> None:
    secao("titulo: nome, versao e asterisco quando sujo")
    checa_igual(titulo_da_janela(None, False), f"Documento em branco{SUFIXO_TITULO}",
                "documento em branco, limpo")
    checa_igual(titulo_da_janela("a.docx", False), f"a.docx{SUFIXO_TITULO}", "com nome")
    checa_igual(titulo_da_janela("a.docx", True), f"*a.docx{SUFIXO_TITULO}", "com nome e sujo")
    checa(not titulo_da_janela(None, True).startswith("Documento em branco"),
          "contraprova: o asterisco entra antes do nome, nao substitui o nome")


def testar_novo_e_titulo() -> None:
    secao("novo: documento em branco limpo, e o asterisco aparece ao digitar")
    configuracao.caminho().unlink(missing_ok=True)
    gerente = GerenteDeJanelas(configuracao.padrao())
    janela = gerente.novo()
    checa_igual(janela.windowTitle(), f"Documento em branco{SUFIXO_TITULO}",
                "titulo do documento em branco, sem asterisco")
    checa(janela.barra_aviso.avisos() == [], "documento em branco nao mostra aviso")
    checa(janela.barra_aviso.isHidden(), "barra de aviso escondida no documento em branco")
    janela.painel.insertPlainText("x")
    checa(janela.windowTitle().startswith("*Documento em branco"),
          "digitar marca o documento como sujo")
    janela_limpa(gerente)


def testar_abrir_editar_salvar_reabrir(tmp: pathlib.Path) -> None:
    secao("abrir, editar, salvar, fechar e reabrir: texto e formato voltam iguais")
    configuracao.caminho().unlink(missing_ok=True)
    caminho = gravar(tmp / "amostra.docx", fx.bytes_de(fx.documento_completo()))
    gerente = GerenteDeJanelas(configuracao.padrao())
    with dialogos(avisar=proibido("avisar"), confirmar=proibido("confirmar")):
        janela = gerente.abrir(str(caminho))
        checa(janela is not None, "o .docx de amostra abre")
        checa("Título: ação" in janela.painel.toPlainText(), "o texto aparece na janela")
        checa_igual(janela.windowTitle(), f"amostra.docx{SUFIXO_TITULO}", "titulo com o nome")
        checa(str(caminho.resolve()) in configuracao.recentes(), "o arquivo entra nos recentes")
        janela.painel.moveCursor(janela.painel.textCursor().MoveOperation.End)
        janela.painel.insertPlainText(" EDITADO")
        checa(janela.windowTitle().startswith("*amostra.docx"), "editar marca como sujo")
        checa(janela.salvar(), "salvar grava")
        checa(not janela.sujo(), "depois de salvar nao fica sujo")
        checa_igual(janela.windowTitle(), f"amostra.docx{SUFIXO_TITULO}", "titulo sem asterisco")
        textos = texto_do_arquivo(caminho)
        checa(textos[-1].endswith("numero recomeca EDITADO") or textos[-1].endswith(" EDITADO"),
              "o arquivo tem o texto digitado")
        checa(janela.salvar() and not janela.sujo(),
              "salvar sem alteracao e' no-op e nao pergunta nada")
        janela.close()
        drenar_eventos()
        reaberta = gerente.abrir(str(caminho))
        checa(reaberta is not None and reaberta is not janela, "reabrir cria outra janela")
        modelo = de_qt.extrair(reaberta.painel.document())
        checa(modelo.paragrafos[0].runs[0].negrito is True,
              "o negrito do titulo sobrevive ao salvar e reabrir")
        checa(any("EDITADO" in "".join(r.texto for r in p.runs) for p in modelo.paragrafos),
              "o texto editado sobrevive ao salvar e reabrir")
    janela_limpa(gerente)


def testar_abrir_ja_aberto(tmp: pathlib.Path) -> None:
    secao("abrir o mesmo arquivo traz a janela que ja existe, sem duplicar")
    caminho = gravar(tmp / "unico.docx", fx.bytes_de(documento_simples()))
    gerente = GerenteDeJanelas(configuracao.padrao())
    primeira = gerente.abrir(str(caminho))
    segunda = gerente.abrir(str(caminho))
    checa(primeira is segunda, "o mesmo caminho devolve a mesma janela")
    variante = str(caminho).upper()
    checa(gerente.abrir(variante) is primeira, "caixa diferente no caminho nao duplica")
    outro = gravar(tmp / "outro.docx", fx.bytes_de(documento_simples()))
    checa(gerente.abrir(str(outro)) is not primeira, "contraprova: outro arquivo abre outra janela")
    checa_igual(len(gerente.janelas()), 2, "duas janelas, uma por arquivo")
    janela_limpa(gerente)


def testar_salvar_como(tmp: pathlib.Path) -> None:
    secao("salvar como: o caminho do documento muda e o titulo acompanha")
    gerente = GerenteDeJanelas(configuracao.padrao())
    janela = gerente.novo()
    janela.painel.setPlainText("Texto novo")
    destino = tmp / "novo.docx"
    with dialogos(pedir_salvar_arquivo=lambda _pai, _s: str(destino)):
        checa(janela.salvar_como(), "salvar como grava no destino escolhido")
    checa(janela.caminho == destino, "o caminho do documento passa a ser o escolhido")
    checa_igual(texto_do_arquivo(destino), ["Texto novo"], "o arquivo tem o texto")
    checa_igual(janela.windowTitle(), f"novo.docx{SUFIXO_TITULO}", "titulo com o novo nome")
    janela_limpa(gerente)


def testar_recusa_de_extensoes(tmp: pathlib.Path) -> None:
    secao("extensoes que o M2 nao abre: mensagem clara e nenhuma janela")
    gerente = GerenteDeJanelas(configuracao.padrao())
    esperados = {
        "antigo.doc": "97-2003",
        "macro.docm": "macros",
        "modelo.dotx": "Modelos",
        "texto.txt": "apenas arquivos .docx",
    }
    mensagens: list[str] = []
    with dialogos(avisar=lambda _p, _t, texto: mensagens.append(texto)):
        for nome, trecho in esperados.items():
            arquivo = gravar(tmp / nome, b"conteudo qualquer")
            mensagens.clear()
            checa(gerente.abrir(str(arquivo)) is None, f"{nome} e' recusado")
            checa(len(mensagens) == 1 and trecho in mensagens[0],
                  f"{nome}: mensagem cita '{trecho}'")
    checa_igual(gerente.janelas(), [], "nenhuma janela foi criada pelas recusas")


def testar_arquivo_grande_e_invalido(tmp: pathlib.Path) -> None:
    secao("arquivo acima do limite pergunta; arquivo ruim vira mensagem e nao abre janela")
    gerente = GerenteDeJanelas(configuracao.padrao())
    grande = gravar(tmp / "grande.docx", fx.bytes_de(documento_simples()))
    original = modulo_gerente.LIMITE_ABRIR_BYTES
    perguntas: list[str] = []
    try:
        modulo_gerente.LIMITE_ABRIR_BYTES = 10
        with dialogos(confirmar=lambda _p, _t, texto: perguntas.append(texto) or False):
            checa(gerente.abrir(str(grande)) is None, "acima do limite, a resposta 'nao' recusa")
        checa_igual(len(perguntas), 1, "o programa perguntou uma vez")
        with dialogos(confirmar=lambda _p, _t, _x: True):
            checa(gerente.abrir(str(grande)) is not None, "acima do limite, 'sim' abre")
    finally:
        modulo_gerente.LIMITE_ABRIR_BYTES = original
    janela_limpa(gerente)
    ruim = gravar(tmp / "ruim.docx", fx.docx_hostil()["docx_bom"])
    mensagens: list[str] = []
    with dialogos(avisar=lambda _p, _t, texto: mensagens.append(texto)):
        checa(gerente.abrir(str(ruim)) is None, "arquivo que nao e' zip nao abre")
    checa(len(mensagens) == 1 and "não é um .docx válido" in mensagens[0],
          "a mensagem do leitor chega ao usuario em portugues")
    checa_igual(gerente.janelas(), [], "nenhuma janela ficou para tras")


def testar_barra_de_aviso(tmp: pathlib.Path) -> None:
    secao("barra de aviso: aparece com avisos, tem Detalhes, e some quando o arquivo fica resolvido")
    gerente = GerenteDeJanelas(configuracao.padrao())
    arquivo = gravar(tmp / "tabela.docx", docx_com_tabela_e_quebra())
    with dialogos(avisar=proibido("avisar")):
        janela = gerente.abrir(str(arquivo))
    checa(janela is not None, "o arquivo com tabela abre")
    checa(not janela.barra_aviso.isHidden(), "a barra de aviso aparece")
    checa("tabela" in janela.barra_aviso.texto_completo().lower(), "o aviso fala da tabela")
    checa("celula" in janela.painel.toPlainText(), "o texto da tabela foi preservado como paragrafo")
    detalhes: list[str] = []
    with dialogos(mostrar_detalhes=lambda _p, _t, texto: detalhes.append(texto)):
        janela.barra_aviso._mostrar_detalhes()
    checa(len(detalhes) == 1 and "quebra" in detalhes[0].lower(),
          "Detalhes mostra a lista completa, com a quebra de pagina")
    limpa = gerente.novo()
    checa(limpa.barra_aviso.isHidden(), "contraprova: documento sem aviso nao mostra a barra")
    janela_limpa(gerente)


def testar_perda_confirmada(tmp: pathlib.Path) -> None:
    secao("perda confirmada: cancelar nao grava, copia nao troca o caminho, salvar grava")
    arquivo = gravar(tmp / "perda.docx", docx_com_tabela_e_quebra())
    original = arquivo.read_bytes()
    gerente = GerenteDeJanelas(configuracao.padrao())
    with dialogos(avisar=proibido("avisar")):
        janela = gerente.abrir(str(arquivo))
    janela.painel.moveCursor(janela.painel.textCursor().MoveOperation.End)
    janela.painel.insertPlainText(" X")
    perguntas: list[list[str]] = []

    def cancelar(_p, _n, linhas):
        perguntas.append(linhas)
        return "cancelar"

    with dialogos(pedir_perda=cancelar):
        checa(janela.salvar() is False, "cancelar a perda nao salva")
    checa(arquivo.read_bytes() == original, "o arquivo continua igual depois do cancelamento")
    checa(len(perguntas) == 1 and any("tabela" in linha for linha in perguntas[0]),
          "a pergunta lista a perda da tabela")

    copia = tmp / "copia.docx"
    with dialogos(pedir_perda=lambda *_a: "copia",
                  pedir_salvar_arquivo=lambda _p, _s: str(copia)):
        checa(janela.salvar() is True, "salvar copia grava")
    checa(copia.is_file(), "a copia existe no destino escolhido")
    checa(janela.caminho == arquivo.resolve(), "salvar copia nao troca o caminho do documento")
    checa(arquivo.read_bytes() == original, "o original continua igual depois da copia")
    checa(janela.sujo(), "o documento continua sujo depois da copia")

    with dialogos(pedir_perda=lambda *_a: "salvar"):
        checa(janela.salvar() is True, "salvar mesmo assim grava")
    checa(arquivo.read_bytes() != original, "contraprova: o original mudou ao salvar mesmo assim")
    janela_limpa(gerente)


def testar_falha_de_gravacao(tmp: pathlib.Path) -> None:
    secao("falha injetada na troca ou na conferencia: o original fica intacto e nada sobra")
    arquivo = gravar(tmp / "falha.docx", fx.bytes_de(documento_simples()))
    original = arquivo.read_bytes()
    gerente = GerenteDeJanelas(configuracao.padrao())
    with dialogos(avisar=proibido("avisar")):
        janela = gerente.abrir(str(arquivo))
    janela.painel.setPlainText("texto que nao deve ir para o disco")
    janela.painel.document().setModified(True)
    avisos: list[str] = []

    def trocar_falha(temporario, destino):
        raise gravacao.FalhaNaTroca("falha injetada na troca")

    original_trocar = gravacao._trocar
    try:
        gravacao._trocar = trocar_falha
        with dialogos(avisar=lambda _p, _t, texto: avisos.append(texto)):
            checa(janela.salvar() is False, "falha na troca: salvar retorna falso")
    finally:
        gravacao._trocar = original_trocar
    checa(arquivo.read_bytes() == original, "falha na troca: o original fica intacto")
    checa(not (tmp / "falha.docx.ewnew").exists(), "falha na troca: o temporario nao sobra")
    checa(len(avisos) == 1 and "falha injetada" in avisos[0], "a falha chega ao usuario")

    def conferir_falha(_dados, _esperado):
        raise conferencia.FalhaDeConferencia("conteudo diferente")

    original_conferir = conferencia.conferir
    try:
        conferencia.conferir = conferir_falha
        with dialogos(avisar=lambda _p, _t, texto: avisos.append(texto)):
            checa(janela.salvar() is False, "falha na conferencia: salvar retorna falso")
    finally:
        conferencia.conferir = original_conferir
    checa(arquivo.read_bytes() == original, "falha na conferencia: o original fica intacto")
    checa(janela.sujo(), "depois da falha, o documento continua sujo (nada foi perdido)")
    janela.painel.document().setModified(False)
    janela_limpa(gerente)


def testar_arquivo_alterado_no_disco(tmp: pathlib.Path) -> None:
    secao("arquivo alterado por outro programa: pergunta antes de sobrescrever")
    arquivo = gravar(tmp / "mudou.docx", fx.bytes_de(documento_simples()))
    gerente = GerenteDeJanelas(configuracao.padrao())
    with dialogos(avisar=proibido("avisar")):
        janela = gerente.abrir(str(arquivo))
    janela.painel.insertPlainText(" meu")
    externo = fx.bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("outro programa escreveu isto")])]))
    arquivo.write_bytes(externo)
    perguntas: list[str] = []
    with dialogos(pedir_sobrescrever=lambda _p, nome: perguntas.append(nome) or False):
        checa(janela.salvar() is False, "'nao' na pergunta cancela o salvamento")
    checa(arquivo.read_bytes() == externo, "o conteudo de outro programa fica no disco")
    checa(len(perguntas) == 1, "a pergunta foi feita uma vez")
    with dialogos(pedir_sobrescrever=lambda _p, _n: True):
        checa(janela.salvar() is True, "contraprova: 'sim' na pergunta grava por cima")
    checa(arquivo.read_bytes() != externo, "depois do sim, o arquivo tem o nosso conteudo")
    janela_limpa(gerente)


def testar_fechar_com_alteracao(tmp: pathlib.Path) -> None:
    secao("fechar com alteracao pendente: cancelar mantem a janela, descartar fecha sem gravar")
    arquivo = gravar(tmp / "fechar.docx", fx.bytes_de(documento_simples()))
    original = arquivo.read_bytes()
    gerente = GerenteDeJanelas(configuracao.padrao())
    with dialogos(avisar=proibido("avisar")):
        janela = gerente.abrir(str(arquivo))
    janela.painel.insertPlainText(" alterado")
    with dialogos(pedir_descartar=lambda _p, _n: "cancelar"):
        janela.close()
    checa(janela in gerente.janelas(), "cancelar mantem a janela aberta")
    with dialogos(pedir_descartar=lambda _p, _n: "descartar"):
        janela.close()
    checa(janela not in gerente.janelas(), "descartar fecha a janela")
    checa(arquivo.read_bytes() == original, "descartar nao grava nada")
    drenar_eventos()


def testar_sair(tmp: pathlib.Path) -> None:
    secao("sair: fecha tudo, pergunta as sujas, e cancelar interrompe")
    gerente = GerenteDeJanelas(configuracao.padrao())
    limpa = gerente.novo()
    suja = gerente.novo()
    suja.painel.insertPlainText("x")
    with dialogos(pedir_descartar=lambda _p, _n: "cancelar"):
        checa(gerente.sair() is False, "cancelar na suja impede a saida")
    checa(len(gerente.janelas()) == 2 and limpa in gerente.janelas(),
          "nenhuma janela foi fechada pela metade")
    with dialogos(pedir_descartar=lambda _p, _n: "descartar"):
        checa(gerente.sair() is True, "descartar deixa sair")
    drenar_eventos()
    checa_igual(gerente.janelas(), [], "saida deixa zero janelas")


def testar_recentes(tmp: pathlib.Path) -> None:
    secao("recentes: maximo 15, mais novo primeiro, arquivo apagado some")
    configuracao.caminho().unlink(missing_ok=True)
    gerente = GerenteDeJanelas(configuracao.padrao())
    arquivos = [gravar(tmp / f"r{i:02d}.docx", fx.bytes_de(documento_simples())) for i in range(17)]
    for arquivo in arquivos:
        with dialogos(avisar=proibido("avisar")):
            janela = gerente.abrir(str(arquivo))
        janela.close()
        drenar_eventos()
    recentes = configuracao.recentes()
    checa_igual(len(recentes), configuracao.MAXIMO_RECENTES, "a lista guarda no maximo 15")
    checa_igual(recentes[0], str(arquivos[-1].resolve()), "o mais recente fica no topo")
    arquivos[-1].unlink()
    checa(str(arquivos[-1].resolve()) not in configuracao.recentes(),
          "arquivo apagado some dos recentes")
    janela = gerente.novo()
    janela.botao_arquivo._montar_recentes()
    nomes = [a.text() for a in janela.botao_arquivo.menu_recentes().actions()]
    checa(nomes and nomes[0] == arquivos[-2].name, "o submenu Abrir recente lista o mais novo")
    janela_limpa(gerente)


def main() -> int:
    testar_titulo()
    with pasta_temporaria("editdoc-teste-doc-") as tmp:
        os.environ.setdefault("EDITDOC_TESTE_TMP", str(tmp))
        testar_novo_e_titulo()
        testar_abrir_editar_salvar_reabrir(tmp)
        testar_abrir_ja_aberto(tmp)
        testar_salvar_como(tmp)
        testar_recusa_de_extensoes(tmp)
        testar_arquivo_grande_e_invalido(tmp)
        testar_barra_de_aviso(tmp)
        testar_perda_confirmada(tmp)
        testar_falha_de_gravacao(tmp)
        testar_arquivo_alterado_no_disco(tmp)
        testar_fechar_com_alteracao(tmp)
        testar_sair(tmp)
        testar_recentes(tmp)
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
