"""Linha de comando: dispositivos recusados, opcoes, arquivos comuns. Sem Qt."""

from __future__ import annotations

from ajudantes import checa, checa_igual, resumir, secao
from editdoc import cli
from editdoc.cli import Pedido, analisar, e_dispositivo

#: Um detector INGENUO, por prefixo: se a suite nao acusar este, ela deixaria
#: passar a regressao "console.txt e' dispositivo" sem perceber.
def _ingenuo(nome: str) -> bool:
    base = nome.split(".")[0].lower()
    return base.startswith(("nul", "con", "com", "lpt", "prn", "aux"))


def testar_dispositivos() -> None:
    secao("dispositivos do Windows: recusados em qualquer caixa, com ou sem extensao")
    dispositivos = ["CON", "nul.txt", "COM1", "lpt9.log", "Nul.LOG", "prn", "aux.docx",
                    "com5", "LPT3", r"C:\pasta\nul.log", r"C:\temp\NUL.txt",
                    r"\\.\NUL", "nul\\"]
    for nome in dispositivos:
        checa(e_dispositivo(nome), f"{nome!r} e' dispositivo")

    pedido = analisar(["CON", "nul.txt", "COM1", "lpt9.log", "Nul.LOG"])
    checa_igual(pedido.arquivos, [], "nenhum dispositivo entra em arquivos")
    checa_igual([bruto for bruto, _ in pedido.recusados],
                ["CON", "nul.txt", "COM1", "lpt9.log", "Nul.LOG"],
                "os cinco sao recusados, na mesma ordem")
    checa(all(motivo == "é um dispositivo do Windows, e não um arquivo"
              for _, motivo in pedido.recusados),
          "o motivo e' o de dispositivo, em portugues com acentos")


def testar_arquivos_comuns() -> None:
    secao("arquivos comuns sao aceitos; nomes parecidos NAO sao dispositivo")
    comuns = [r"C:\dados\contrato.docx", "relatorio.docx", r"C:\dados\console.txt",
              r"C:\dados\com10.txt", r"C:\dados\nulo.txt", "lpt0.txt",
              r"C:\dados\prnt.docx", "anexo_ção.docx"]
    pedido = analisar(comuns)
    checa_igual(pedido.arquivos, comuns, "arquivos comuns, inclusive os de nome parecido, sao aceitos")
    checa_igual(pedido.recusados, [], "nada e' recusado")

    def base(caminho: str) -> str:
        return caminho.replace("\\", "/").rsplit("/", 1)[-1]

    def falsos_positivos(detector) -> list[str]:
        """Nomes-base comuns que o detector trataria como dispositivo."""
        return [base(n) for n in comuns if detector(base(n))]

    checa_igual(falsos_positivos(e_dispositivo), [],
                "o detector de verdade NAO acusa nenhum nome comum")
    # Sabotagem: o detector ingenuo TEM de ser acusado. Se esta lista viesse
    # vazia, a checagem acima nao estaria discriminando nada.
    checa_igual(falsos_positivos(_ingenuo),
                ["contrato.docx", "console.txt", "com10.txt", "nulo.txt", "lpt0.txt", "prnt.docx"],
                "sabotagem: um detector por prefixo e' ACUSADO (contrato.docx inclusive)")


def testar_opcoes() -> None:
    secao("opcoes: --autoverificacao, ajuda, opcao desconhecida")
    checa(analisar(["--autoverificacao"]).autoverificacao, "--autoverificacao e' reconhecido")
    for ajuda in ["--ajuda", "--help", "-h", "/?", "--AJUDA"]:
        checa(analisar([ajuda]).ajuda, f"{ajuda} pede ajuda")

    pedido = analisar(["--linha", "148200", "-x", "--coluna", "3"])
    motivos = dict(pedido.recusados)
    checa_igual(motivos.get("--linha"), "opção desconhecida",
                "--linha foi removido do EditDoc: e' opcao desconhecida")
    checa_igual(motivos.get("--coluna"), "opção desconhecida",
                "--coluna foi removido do EditDoc: e' opcao desconhecida")
    checa_igual(motivos.get("-x"), "opção desconhecida", "-x e' opcao desconhecida")
    checa(not hasattr(Pedido(), "linha") and not hasattr(Pedido(), "coluna"),
          "o Pedido nao tem campos de linha nem coluna")

    checa_igual(dict(analisar(["", "   "]).recusados),
                {"": "caminho vazio", "   ": "caminho vazio"},
                "argumento vazio ou so' espacos e' recusado")

    texto_ajuda = cli.AJUDA
    checa("EditDoc" in texto_ajuda and "TextForgeEdit" not in texto_ajuda,
          "a ajuda fala de EditDoc, nao de TextForgeEdit")
    checa("--linha" not in texto_ajuda and "--coluna" not in texto_ajuda,
          "a ajuda nao mostra --linha nem --coluna")
    checa("--autoverificacao" in texto_ajuda and "não abre janela" in texto_ajuda,
          "a ajuda explica --autoverificacao em portugues")


def testar_nunca_levanta() -> None:
    secao("analisar nunca levanta, mesmo com lixo")
    try:
        pedido = analisar(["a" * 2000, "\x00", "--", "-", "/", "\\\\?\\C:\\x"])
        checa(isinstance(pedido, Pedido), "analisar devolve um Pedido com argumentos estranhos")
    except Exception as erro:  # noqa: BLE001 - e' exatamente o que se testa
        checa(False, f"analisar levantou {erro.__class__.__name__}")


def main() -> int:
    testar_dispositivos()
    testar_arquivos_comuns()
    testar_opcoes()
    testar_nunca_levanta()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
