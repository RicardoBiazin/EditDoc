"""Versao, configuracao, log e icone: o que nao precisa de janela.

Isola %APPDATA% antes de importar o programa, porque configuracao e log
escrevem la'.
"""

from __future__ import annotations

import json
import os
import re

from ajudantes import RAIZ, checa, checa_igual, isolar_appdata, resumir, secao

isolar_appdata()

from editword import VERSAO, configuracao, log_interno, recursos  # noqa: E402


def ler(nome: str) -> str:
    return (RAIZ / nome).read_text(encoding="utf-8")


def limpar_config() -> None:
    configuracao.caminho().unlink(missing_ok=True)


def testar_versao() -> None:
    secao("versao: uma so' fonte, e os arquivos de empacotamento concordam")
    texto = ler("versao.txt")
    m = re.search(r"filevers=\((\d+), (\d+), (\d+), (\d+)\)", texto)
    checa(m is not None, "versao.txt traz filevers")
    if m:
        checa_igual(".".join(m.group(1, 2, 3)), VERSAO, "filevers bate com VERSAO")
    campos = dict(re.findall(r"StringStruct\('(\w+)', '([\d.]+)'\)", texto))
    checa_igual(campos.get("FileVersion"), VERSAO, "FileVersion bate com VERSAO")
    checa_igual(campos.get("ProductVersion"), VERSAO, "ProductVersion bate com VERSAO")
    # Olha so' o assemblyIdentity: o <?xml version="1.0"?> do topo casaria antes.
    manifesto = re.search(r'<assemblyIdentity[^>]*\sversion="([\d.]+)"',
                          ler("editword.manifest"))
    checa_igual(manifesto.group(1) if manifesto else None, VERSAO + ".0",
                "manifest traz VERSAO.0")
    checa(re.search(rf"^## {re.escape(VERSAO)}\b", ler("CHANGELOG.md"), re.M)
          is not None, "CHANGELOG tem a secao da versao atual")
    checa(VERSAO in ler("README.md"), "README cita a versao atual")


def testar_configuracao() -> None:
    secao("configuracao: padrao, arquivo ruim e gravacao")
    limpar_config()
    padrao = configuracao.padrao()
    checa_igual(configuracao.carregar(), padrao, "sem arquivo, carrega o padrao")

    configuracao.caminho().write_text("{ isto nao e json", encoding="utf-8")
    checa_igual(configuracao.carregar(), padrao,
                "JSON ilegivel volta ao padrao, sem levantar")

    configuracao.caminho().write_text("[1, 2]", encoding="utf-8")
    checa_igual(configuracao.carregar(), padrao,
                "raiz que nao e' objeto volta ao padrao")

    configuracao.caminho().write_text(
        json.dumps({"janela_largura": "mil", "janela_altura": True}),
        encoding="utf-8")
    checa_igual(configuracao.carregar(), padrao,
                "tipo errado volta ao padrao (bool nao conta como int)")

    configuracao.caminho().write_text(
        json.dumps({"opcao_de_outra_versao": 1, "janela_largura": 1300}),
        encoding="utf-8")
    valores = configuracao.carregar()
    checa_igual(valores["janela_largura"], 1300, "valor valido e' lido")
    checa("opcao_de_outra_versao" not in valores, "chave desconhecida e' ignorada")

    valores["janela_altura"] = 900
    valores["lixo"] = "nao deve ir para o arquivo"
    configuracao.gravar(valores)
    gravado = json.loads(configuracao.caminho().read_text(encoding="utf-8"))
    checa("lixo" not in gravado,
          "gravar nao escreve chave que nao esta' em padrao()")
    checa_igual(configuracao.carregar()["janela_altura"], 900,
                "o que foi gravado volta igual")
    novo = configuracao.caminho().with_name(configuracao.caminho().name + ".novo")
    checa(not novo.exists(), "a gravacao atomica nao deixa o .novo para tras")
    limpar_config()


def testar_log() -> None:
    secao("log: nome do logger, pasta isolada e linha de partida")
    checa_igual(log_interno.obter("editword.teste").name, "editword.teste",
                "logger de modulo mantem o nome")
    checa_igual(log_interno.obter("teste_solto").name, "editword.teste_solto",
                "nome sem prefixo ganha editword.")
    caminho = log_interno.caminho_do_log()
    checa(str(caminho).startswith(os.environ["APPDATA"]),
          "o log fica dentro do %APPDATA% isolado")
    log_interno.registrar_partida(VERSAO)
    checa(VERSAO in caminho.read_text(encoding="utf-8"),
          "a partida grava a versao no log")


def testar_icone() -> None:
    secao("icone: o .ico esta' embutido e tem cabecalho valido")
    alvo = recursos.caminho("icone.ico")
    checa(alvo.is_file(), "editword/recursos/icone.ico existe")
    dados = alvo.read_bytes() if alvo.is_file() else b""
    checa(dados[:4] == b"\x00\x00\x01\x00", "cabecalho e' de icone (ICO)")
    checa(len(dados) > 4000, "traz os tamanhos, e nao um icone de 1 pixel")


def main() -> int:
    testar_versao()
    testar_configuracao()
    testar_log()
    testar_icone()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
