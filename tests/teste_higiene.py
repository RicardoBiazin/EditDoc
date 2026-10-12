"""Higiene: o que o codigo NAO pode fazer, e o que os arquivos do projeto precisam ter.

A checagem usa AST e nao grep: uma linha que cita `eval` num comentario ou numa
string nao e' chamada. So' conta o que o interpretador executaria.
"""

from __future__ import annotations

import ast
import pathlib
import re

from ajudantes import RAIZ, checa, checa_igual, resumir, secao

PROIBIDAS_COMO_FUNCAO = {"eval", "exec"}
PROIBIDOS_MODULOS = {"pickle", "marshal", "shelve"}
PROIBIDOS_COMO_ATRIBUTO = {("os", "system"), ("os", "popen")}


def achados(texto: str, origem: str) -> list[str]:
    """O que e' proibido no fonte. Lista vazia quando esta limpo."""
    saida: list[str] = []
    for no in ast.walk(ast.parse(texto, filename=origem)):
        linha = getattr(no, "lineno", "?")
        if isinstance(no, ast.Call):
            alvo = no.func
            if isinstance(alvo, ast.Name) and alvo.id in PROIBIDAS_COMO_FUNCAO:
                saida.append(f"{origem}:{linha} chamada a {alvo.id}()")
            if (isinstance(alvo, ast.Attribute)
                    and isinstance(alvo.value, ast.Name)
                    and (alvo.value.id, alvo.attr) in PROIBIDOS_COMO_ATRIBUTO):
                saida.append(f"{origem}:{linha} chamada a "
                             f"{alvo.value.id}.{alvo.attr}()")
            for kw in no.keywords:
                if (kw.arg == "shell" and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True):
                    saida.append(f"{origem}:{linha} shell=True")
        elif isinstance(no, ast.Import):
            for nome in no.names:
                if nome.name.split(".")[0] in PROIBIDOS_MODULOS:
                    saida.append(f"{origem}:{linha} importa {nome.name}")
        elif isinstance(no, ast.ImportFrom) and no.module:
            if no.module.split(".")[0] in PROIBIDOS_MODULOS:
                saida.append(f"{origem}:{linha} importa de {no.module}")
    return saida


def fontes() -> list[pathlib.Path]:
    arquivos = sorted((RAIZ / "editdoc").rglob("*.py")) + [RAIZ / "app.py"]
    return [a for a in arquivos if "__pycache__" not in a.parts]


def testar_codigo() -> None:
    secao("codigo: nada de eval, exec, pickle nem shell=True")
    # Contraprova: o detector TEM de pegar um caso proposital. Sem isto, um
    # detector quebrado diria "limpo" para sempre.
    amostra = "import pickle\nx = eval('1')\nsubprocess.run('dir', shell=True)\n"
    checa_igual(len(achados(amostra, "amostra.py")), 3,
                "o detector pega os tres casos da amostra")
    encontrados: list[str] = []
    for arq in fontes():
        encontrados += achados(arq.read_text(encoding="utf-8"),
                               str(arq.relative_to(RAIZ)))
    checa_igual(encontrados, [], "o programa inteiro esta limpo")


def testar_arquivos() -> None:
    secao("arquivos do projeto: dependencias fixas, licenca, ignorados")
    requisitos = [
        linha.strip()
        for linha in (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if linha.strip() and not linha.lstrip().startswith("#")
    ]
    checa(bool(requisitos), "requirements.txt tem dependencias")
    checa(all("==" in linha for linha in requisitos),
          "toda dependencia de execucao tem versao exata (==)")
    checa(not any(re.search(r"pymupdf|fitz", linha, re.I) for linha in requisitos),
          "PyMuPDF (AGPL) fora do pacote")
    checa(not any("python-docx" in linha for linha in requisitos),
          "python-docx fora das dependencias de execucao")
    dev = (RAIZ / "requirements-dev.txt").read_text(encoding="utf-8")
    checa(re.search(r"^python-docx==[\d.]+$", dev, re.M) is not None,
          "python-docx em requirements-dev.txt, com versao exata (so' oraculo de teste)")
    licenca = (RAIZ / "LICENSE").read_text(encoding="utf-8")
    checa(licenca.startswith("MIT License"), "a licenca e' MIT")
    ignorados = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    checa("*.docx" in ignorados,
          ".gitignore ignora *.docx: documento real nunca entra por engano")
    checa(".venv/" in ignorados, ".gitignore ignora .venv/")
    checa((RAIZ / "AVISOS_DE_TERCEIROS.md").is_file(),
          "AVISOS_DE_TERCEIROS.md existe")


def main() -> int:
    testar_codigo()
    testar_arquivos()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
