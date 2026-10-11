"""Empacotamento: o build tem as etapas certas, e o .spec aponta para o que existe."""

from __future__ import annotations

from ajudantes import RAIZ, checa, resumir, secao


def ler(nome: str) -> str:
    return (RAIZ / nome).read_text(encoding="utf-8")


def testar_build() -> None:
    secao("build.bat: cinco etapas, na ordem, com fim de linha CRLF")
    bruto = (RAIZ / "build.bat").read_bytes()
    checa(b"\r\n" in bruto and b"\n" not in bruto.replace(b"\r\n", b""),
          "build.bat tem fim de linha CRLF (o cmd engole linhas com LF puro)")
    texto = bruto.decode("utf-8", errors="replace")
    # Os marcadores [N/5] dividem as etapas. Procurar "PyInstaller" sozinho
    # acharia a checagem de pre-requisito, que vem antes dos testes.
    ordem = ["[1/5]", "rodar_todos.py", "[2/5]", "EditWord.spec", "[3/5]",
             "--autoverificacao", "[4/5]", "fumaca_exe.py", "[5/5]",
             "empacotar_zip.py"]
    posicoes = [texto.find(p) for p in ordem]
    checa(all(p >= 0 for p in posicoes),
          "build.bat tem as cinco etapas e chama cada ferramenta")
    checa(posicoes == sorted(posicoes), "as etapas estao na ordem certa")


def testar_spec() -> None:
    secao("EditWord.spec: o que o pacote precisa carregar")
    spec = ler("EditWord.spec")
    checa("recursos" in spec, "recursos entram no pacote")
    checa("qtbase_pt_BR.qm" in spec, "traducao do Qt entra no pacote")
    checa('collect_data_files("docx")' in spec,
          "templates do python-docx entram no pacote")
    checa("hiddenimports" in spec and "lxml" in spec,
          "lxml declarado como importacao oculta")
    checa("manifest=" in spec and "version=" in spec,
          "manifesto e recurso de versao ligados ao .exe")
    checa("console=False" in spec, "o programa e' de janela, sem console")


def testar_ferramentas() -> None:
    secao("ferramentas do build existem")
    for nome in ("ferramentas/empacotar_zip.py", "ferramentas/fumaca_exe.py",
                 "ferramentas/gerar_icone.py", ".github/workflows/testes.yml"):
        checa((RAIZ / nome).is_file(), f"{nome} existe")


def main() -> int:
    testar_build()
    testar_spec()
    testar_ferramentas()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
