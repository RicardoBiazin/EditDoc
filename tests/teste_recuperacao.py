"""Recuperacao automatica (M8): copia do documento alterado, queda simulada e o dialogo.

Nada aqui grava na %LOCALAPPDATA% real: `preparar_qt` isola a pasta (EDITDOC_RECUPERACAO
aponta para dentro do %APPDATA% descartavel), e cada teste usa ainda uma pasta propria.
A queda e' de verdade num dos testes: um processo grava a copia e e' morto.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import subprocess
import sys
import time

from ajudantes import (RAIZ, checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt,
                       pular, resumir, secao)
import fixtures_docx as fx

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtTest import QTest  # noqa: E402

from editdoc import VERSAO, configuracao, recuperacao  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.interface import dialogos_modais, guarda_recuperacao  # noqa: E402
from editdoc.interface.gerente import GerenteDeJanelas  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402


@contextlib.contextmanager
def dialogos(**substitutos):
    originais = {nome: getattr(dialogos_modais, nome) for nome in substitutos}
    for nome, funcao in substitutos.items():
        setattr(dialogos_modais, nome, funcao)
    try:
        yield
    finally:
        for nome, funcao in originais.items():
            setattr(dialogos_modais, nome, funcao)


@contextlib.contextmanager
def pasta_de_recuperacao():
    """Pasta propria para o teste, pela variavel do programa; volta a anterior no fim."""
    anterior = os.environ.get(recuperacao.VARIAVEL_PASTA)
    with pasta_temporaria("editdoc-rec-") as pasta:
        os.environ[recuperacao.VARIAVEL_PASTA] = str(pasta)
        try:
            yield pasta
        finally:
            os.environ[recuperacao.VARIAVEL_PASTA] = anterior or ""


def docx(texto: str) -> bytes:
    return escrever(Documento(paragrafos=[Paragrafo(runs=[Run(texto)])]))


def texto_de(dados: bytes) -> str:
    modelo, _ = ler(dados)
    return "\n".join("".join(r.texto for r in p.runs) for p in modelo.paragrafos
                     if isinstance(p, Paragrafo))


def soltar_sem_apagar(sessao: recuperacao.Sessao) -> None:
    """O que o Windows faz quando o processo morre: a trava some, os arquivos ficam."""
    sessao._trava.soltar(apagar=False)
    sessao._trava = None


def fechar_sem_perguntar(janela) -> None:
    janela.painel.documento_corpo().setModified(False)
    janela.close()
    drenar_eventos()


def testar_pasta() -> None:
    secao("pasta: fora da pasta do usuario e, nos testes, nunca a %LOCALAPPDATA% real")
    pasta = recuperacao.pasta()
    checa(str(pasta).startswith(os.environ["APPDATA"]),
          "a pasta da suite fica dentro do %APPDATA% descartavel")
    checa(pasta.name == "Recuperacao" and pasta.parent.name == "EditDoc",
          "o nome e' EditDoc\\Recuperacao, como no programa")
    anterior = os.environ.pop(recuperacao.VARIAVEL_PASTA)
    try:
        padrao = recuperacao.pasta()
        checa_igual(padrao, pathlib.Path(os.environ["LOCALAPPDATA"]) / "EditDoc" / "Recuperacao",
                    "sem a variavel, a pasta e' %LOCALAPPDATA%\\EditDoc\\Recuperacao")
    finally:
        os.environ[recuperacao.VARIAVEL_PASTA] = anterior


def testar_gravar_e_metadados() -> None:
    secao("gravar: .docx e .json atomicos, metadados, sem sobra de temporario")
    with pasta_de_recuperacao() as pasta:
        sessao = recuperacao.Sessao()
        aviso = {"codigo": "EQUACAO", "texto": "1 equação sai do arquivo.", "contagem": 1,
                 "perde_ao_salvar": True}
        checa(sessao.gravar(docx("primeira"), r"C:\docs\relatorio.docx", "relatorio.docx",
                            [aviso]), "a primeira copia e' gravada")
        checa(sessao.gravar(docx("segunda versao"), r"C:\docs\relatorio.docx", "relatorio.docx",
                            [aviso]), "a segunda copia troca a primeira")
        nomes = sorted(p.name for p in pasta.iterdir())
        checa_igual(nomes, sorted([f"{sessao.id}.docx", f"{sessao.id}.json", f"{sessao.id}.trava"]),
                    "so' os tres arquivos da sessao: nada de .ewnew nem .novo")
        meta = json.loads((pasta / f"{sessao.id}.json").read_text(encoding="utf-8"))
        checa_igual(meta["caminho_original"], r"C:\docs\relatorio.docx", "metadado: caminho original")
        checa_igual(meta["versao"], VERSAO, "metadado: versao do programa")
        checa_igual(meta["pid"], os.getpid(), "metadado: pid de quem gravou")
        checa("T" in meta["hora"] and meta["hora"].endswith("+00:00"), "metadado: hora em ISO, UTC")
        checa_igual(meta["tamanho"], (pasta / f"{sessao.id}.docx").stat().st_size,
                    "metadado: o tamanho do .docx gravado")
        checa_igual(texto_de((pasta / f"{sessao.id}.docx").read_bytes()), "segunda versao",
                    "a copia tem o conteudo da ultima gravacao")
        sessao.encerrar()
        checa_igual(list(pasta.iterdir()), [], "encerrar apaga a copia e a trava")


def testar_trava_e_queda_simulada() -> None:
    secao("trava: copia de janela viva nao e' oferecida; depois da queda, e'")
    with pasta_de_recuperacao() as pasta:
        sessao = recuperacao.Sessao()
        sessao.gravar(docx("texto da queda"), None, "Documento em branco")
        checa(recuperacao.em_uso(sessao.id), "a copia de uma sessao viva esta' em uso")
        checa_igual(recuperacao.listar_orfas(), [], "e nao aparece como orfa")
        soltar_sem_apagar(sessao)
        orfas = recuperacao.listar_orfas()
        checa_igual([c.id for c in orfas], [sessao.id], "sem a trava, a copia vira orfa")
        checa_igual(texto_de(orfas[0].ler()), "texto da queda", "e le' de volta o texto")
        checa_igual(orfas[0].caminho_original, None, "documento novo: sem caminho original")
        adotada = recuperacao.Sessao(id_=sessao.id)
        checa(adotada.travar(), "abrir a copia adota a trava dela")
        checa_igual(recuperacao.listar_orfas(), [], "adotada, ela deixa de ser oferecida")
        outra = recuperacao.Sessao(id_=sessao.id)
        checa(not outra.travar(), "contraprova: uma segunda janela nao adota a mesma copia")
        adotada.encerrar()
        checa_igual(list(pasta.iterdir()), [], "a adotada encerrada some da pasta")


def testar_copia_incompleta() -> None:
    secao("copia incompleta: .docx de tamanho diferente do anotado nao e' oferecido")
    with pasta_de_recuperacao() as pasta:
        boa, ruim = recuperacao.Sessao(), recuperacao.Sessao()
        boa.gravar(docx("boa"), None, "boa")
        ruim.gravar(docx("ruim"), None, "ruim")
        soltar_sem_apagar(boa)
        soltar_sem_apagar(ruim)
        with open(pasta / f"{ruim.id}.docx", "ab") as f:
            f.write(b"lixo de uma gravacao interrompida")
        (pasta / "nao-e-copia.docx").write_bytes(b"PK")
        (pasta / f"{'a' * 32}.docx").write_bytes(b"PK sem json")
        checa_igual([c.nome for c in recuperacao.listar_orfas()], ["boa"],
                    "so' a copia inteira aparece (contraprova: a outra e' oferecida)")


def testar_varias_janelas() -> None:
    secao("varias janelas: cada uma com a sua copia, sem atrapalhar a outra")
    with pasta_de_recuperacao():
        a, b = JanelaPrincipal(configuracao.padrao()), JanelaPrincipal(configuracao.padrao())
        a.painel.insertPlainText("janela A")
        b.painel.insertPlainText("janela B")
        checa(a.recuperacao.gravar_agora() and b.recuperacao.gravar_agora(),
              "as duas janelas gravam a copia")
        checa(a.recuperacao.sessao.id != b.recuperacao.sessao.id, "ids diferentes")
        checa_igual(recuperacao.listar_orfas(), [], "nenhuma das duas e' orfa enquanto vivem")
        fechar_sem_perguntar(a)
        checa(not a.recuperacao.sessao.existe(), "fechar A apaga a copia de A")
        checa(b.recuperacao.sessao.existe(), "e a de B continua")
        fechar_sem_perguntar(b)


def testar_guarda_da_janela(tmp: pathlib.Path) -> None:
    secao("janela: grava so' alterado, apos N alteracoes, apaga ao salvar e ao fechar")
    with pasta_de_recuperacao() as pasta:
        original = tmp / "original.docx"
        original.write_bytes(fx.bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("original")])])))
        bytes_antes = original.read_bytes()
        gerente = GerenteDeJanelas(configuracao.padrao())
        janela = gerente.abrir(str(original))
        guarda = janela.recuperacao
        checa_igual(guarda.intervalo_ms(), 10 * 60_000, "intervalo padrao: 10 minutos")
        checa(not guarda.gravar_agora(), "documento limpo: nada a recuperar")
        janela.painel.moveCursor(janela.painel.textCursor().MoveOperation.End)
        janela.painel.insertPlainText(" alterado")
        checa(guarda.gravar_agora(), "documento alterado: a copia e' gravada")
        checa(not guarda.gravar_agora(), "sem alteracao nova, nao grava de novo")
        meta = json.loads((pasta / f"{guarda.sessao.id}.json").read_text(encoding="utf-8"))
        checa_igual(meta["caminho_original"], str(original.resolve()), "a copia sabe de onde veio")
        checa_igual(original.read_bytes(), bytes_antes, "o original nao foi tocado")
        checa(guarda.sessao.caminho_docx().parent == pasta, "a copia fica na pasta de recuperacao")

        limite, pausa = recuperacao.ALTERACOES_PARA_GRAVAR, guarda_recuperacao.PAUSA_APOS_ALTERACOES_MS
        recuperacao.ALTERACOES_PARA_GRAVAR = 5
        guarda._pausa.setInterval(50)
        try:
            gravacoes = guarda.sessao.gravacoes
            for letra in "abcdef":
                QTest.keyClick(janela.painel, letra)
            QTest.qWait(300)
            checa_igual(guarda.sessao.gravacoes, gravacoes + 1,
                        "depois de N alteracoes e de uma pausa, grava sozinha")
        finally:
            recuperacao.ALTERACOES_PARA_GRAVAR = limite
            guarda._pausa.setInterval(pausa)

        guarda.definir(1, True)
        checa_igual(guarda.intervalo_ms(), 60_000, "o intervalo muda pela preferencia")
        guarda.definir(0, True)
        checa_igual(guarda.intervalo_ms(), 10 * 60_000, "intervalo invalido volta ao padrao")
        guarda._relogio.setInterval(80)
        janela.painel.insertPlainText("x")
        gravacoes = guarda.sessao.gravacoes
        QTest.qWait(400)
        checa(guarda.sessao.gravacoes > gravacoes, "o relogio grava sozinho")
        guarda.definir(10, False)
        janela.painel.insertPlainText("y")
        checa(not guarda.gravar_agora(), "desligada pela preferencia, nao grava")
        guarda.definir(10, True)

        with dialogos(avisar=lambda *_a: None):
            checa(janela.salvar(), "salvar grava o arquivo")
        checa(not guarda.sessao.existe(), "salvar apaga a copia de recuperacao")
        janela.painel.insertPlainText("z")
        guarda.gravar_agora()
        checa(guarda.sessao.existe(), "voltou a alterar: nova copia")
        with dialogos(pedir_descartar=lambda *_a: "descartar"):
            janela.close()
        drenar_eventos()
        checa_igual(list(pasta.iterdir()), [], "fechar (descartando) apaga a copia e a trava")


SCRIPT_QUEDA = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
from editdoc import recuperacao
from editdoc.formato_docx.escritor import escrever
from editdoc.modelo.documento import Documento, Paragrafo, Run
s = recuperacao.Sessao()
s.gravar(escrever(Documento(paragrafos=[Paragrafo(runs=[Run("antes da queda")])])),
         r"C:\pasta\contrato.docx", "contrato.docx")
print(s.id, flush=True)
time.sleep(60)
"""


def testar_queda_de_verdade() -> None:
    secao("queda de verdade: um processo grava a copia e e' morto")
    with pasta_de_recuperacao() as pasta:
        proc = subprocess.Popen([sys.executable, "-c", SCRIPT_QUEDA, str(RAIZ)],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                env=dict(os.environ))
        try:
            id_ = (proc.stdout.readline() or "").strip()
            checa(recuperacao._id_valido(id_), "o outro processo gravou e disse o id")
            checa(recuperacao.em_uso(id_), "enquanto ele vive, a copia esta' travada")
            checa_igual(recuperacao.listar_orfas(), [], "e nao e' oferecida")
        finally:
            proc.kill()
            proc.wait(10)
        fim = time.monotonic() + 5
        orfas = []
        while time.monotonic() < fim and not orfas:
            orfas = recuperacao.listar_orfas()
            time.sleep(0.05)
        checa_igual([c.id for c in orfas], [id_], "morto o processo, a copia vira orfa")
        if orfas:
            checa_igual(orfas[0].nome, "contrato.docx", "com o nome do documento")
            checa_igual(texto_de(orfas[0].ler()), "antes da queda", "e o texto de antes da queda")
        recuperacao.apagar_copia(id_)
        checa_igual(list(pasta.iterdir()), [], "descartar a orfa limpa a pasta")


def criar_orfa(texto: str, original: str | None, nome: str, avisos=None) -> recuperacao.Sessao:
    sessao = recuperacao.Sessao()
    sessao.gravar(docx(texto), original, nome, avisos)
    soltar_sem_apagar(sessao)
    return sessao


def testar_dialogo_de_recuperacao(tmp: pathlib.Path) -> None:
    secao("dialogo: abrir, salvar como e descartar as copias que sobraram")
    with pasta_de_recuperacao() as pasta:
        gerente = GerenteDeJanelas(configuracao.padrao())
        checa(gerente.oferecer_recuperacao() is None, "sem copia, nao mostra nada")
        avisos_vistos = []
        with dialogos(mostrar_detalhes=lambda _p, _t, texto: avisos_vistos.append(texto)):
            gerente.oferecer_recuperacao(avisar_se_vazio=True)
        checa(avisos_vistos and "Não há cópias" in avisos_vistos[0],
              "Arquivo > Recuperar sem copia avisa que nao ha' nada")
        perda = {"codigo": "EQUACAO", "texto": "1 equação sai do arquivo.", "contagem": 1,
                 "perde_ao_salvar": True}
        a = criar_orfa("texto A", str(tmp / "a.docx"), "a.docx", [perda])
        b = criar_orfa("texto B", None, "Documento em branco")
        c = criar_orfa("texto C", None, "c.docx")
        dialogo = gerente.oferecer_recuperacao()
        checa(dialogo is not None and dialogo.isVisible(), "com copias, o dialogo aparece")
        checa_igual(sorted(x.id for x in dialogo.copias()), sorted([a.id, b.id, c.id]),
                    "as tres copias estao na lista")

        indice = [x.id for x in dialogo.copias()].index(a.id)
        dialogo.selecionar(indice)
        checa(dialogo.abrir(), "Abrir abre a copia")
        janela = gerente.janelas()[-1]
        checa("texto A" in janela.painel.toPlainText(), "a janela mostra o texto recuperado")
        checa(janela.sujo(), "o documento recuperado nasce alterado")
        checa(janela.caminho is None, "e sem caminho: salvar pergunta onde")
        checa(janela.windowTitle().startswith("*a.docx (recuperado)"),
              "o titulo diz que e' recuperado")
        checa(a.id not in [x.id for x in recuperacao.listar_orfas()],
              "aberta, a copia deixa de ser orfa (a janela tem a trava)")
        checa(any(av.codigo == "EQUACAO" and av.perde_ao_salvar for av in janela._avisos),
              "o aviso de perda do original vem junto: salvar ainda pede confirmacao")
        destino = tmp / "salvo.docx"
        pedidos, perdas = [], []
        with dialogos(pedir_salvar_arquivo=lambda _p, sug: (pedidos.append(sug), str(destino))[1],
                      pedir_perda=lambda _p, _n, linhas: (perdas.append(linhas), "salvar")[1]):
            checa(janela.salvar(), "salvar o recuperado grava")
        checa_igual(pedidos, [str(tmp / "a.docx")], "a sugestao e' o caminho de onde veio")
        checa(perdas and "1 equação sai do arquivo." in perdas[0],
              "salvar pediu a confirmacao da perda do original")
        checa(not (pasta / f"{a.id}.docx").exists(), "salvo, a copia adotada some da pasta")
        checa_igual(texto_de(destino.read_bytes()), "texto A", "o arquivo salvo tem o texto")
        fechar_sem_perguntar(janela)

        indice = [x.id for x in dialogo.copias()].index(b.id)
        dialogo.selecionar(indice)
        destino_b = tmp / "b.docx"
        with dialogos(pedir_salvar_arquivo=lambda *_a: str(destino_b)):
            checa(dialogo.salvar_como(), "Salvar como grava a copia num .docx")
        checa_igual(texto_de(destino_b.read_bytes()), "texto B", "o .docx gravado abre com o texto")
        checa(not (pasta / f"{b.id}.docx").exists(), "e a copia sai da recuperacao")

        dialogo.selecionar(0)
        with dialogos(confirmar=lambda *_a: False):
            checa(not dialogo.descartar(), "descartar pede confirmacao (Nao = fica)")
        checa((pasta / f"{c.id}.docx").exists(), "contraprova: sem confirmar, a copia fica")
        with dialogos(confirmar=lambda *_a: True):
            checa(dialogo.descartar(), "descartar confirmado apaga")
        checa_igual(list(pasta.iterdir()), [], "nada sobra na pasta")
        checa(not dialogo.isVisible(), "a lista vazia fecha o dialogo")
        for j in gerente.janelas():
            fechar_sem_perguntar(j)


def main() -> int:
    with pasta_temporaria() as tmp:
        testar_pasta()
        testar_gravar_e_metadados()
        testar_trava_e_queda_simulada()
        testar_copia_incompleta()
        testar_varias_janelas()
        testar_guarda_da_janela(tmp)
        testar_queda_de_verdade()
        testar_dialogo_de_recuperacao(tmp)
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
