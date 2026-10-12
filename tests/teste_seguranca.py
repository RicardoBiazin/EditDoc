"""Arquivos hostis: cada um vira ErroDocx com o codigo certo, sem traceback, em menos de 2 s.

Os arquivos sao gerados por codigo (tests/fixtures_docx.py). Nada e' lido do disco,
exceto o caminho inexistente de proposito.
"""

from __future__ import annotations

import time

from ajudantes import checa, checa_igual, resumir, secao
import fixtures_docx as fx

from editdoc.formato_docx import erros
from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.leitor import ler

LIMITE_S = 2.0

#: nome do caso -> codigo esperado
ESPERADOS = {
    "docx_bom": "ZIP_INVALIDO",
    "ole_doc_antigo": "FORMATO_DOC_ANTIGO",
    "doctype": "XML_DOCTYPE_PROIBIDO",
    "billion_laughs": "XML_DOCTYPE_PROIBIDO",
    "xml_malformado": "XML_MALFORMADO",
    "profundidade": "XML_PROFUNDIDADE_EXCEDIDA",
    "strict": "FORMATO_STRICT",
    "zip_com_dotdot": "ZIP_NOME_INVALIDO",
    "barra_invertida": "ZIP_NOME_INVALIDO",
    "bomba_compressao": "ZIP_RAZAO_ABSURDA",
}


def _codigo_de(dados) -> tuple[str | None, float]:
    inicio = time.perf_counter()
    try:
        ler(dados)
        codigo = None
    except ErroDocx as erro:
        codigo = erro.codigo
    except BaseException as erro:  # noqa: BLE001 - um traceback vazado e' o defeito que se procura
        codigo = f"EXCECAO:{type(erro).__name__}"
    return codigo, time.perf_counter() - inicio


def testar_casos() -> None:
    secao("arquivos hostis: codigo certo, sem traceback e em menos de 2 s")
    hostis = fx.docx_hostil()
    for nome, esperado in ESPERADOS.items():
        codigo, tempo = _codigo_de(hostis[nome])
        checa(codigo == esperado and tempo < LIMITE_S,
              f"{nome}: {codigo} em {tempo:.3f} s (esperado {esperado})")


def testar_tamanho_acima_do_limite() -> None:
    secao("parte de 129 MB declarada: recusada antes de descompactar")
    base = fx.partes_de(fx.bytes_de(fx.documento_completo()))
    grande = fx.zip_com([("_rels/.rels", base["_rels/.rels"]),
                         ("word/document.xml", b"<w:document/>" + b" " * (129 * 1024 * 1024))])
    codigo, tempo = _codigo_de(grande)
    checa(codigo == "ZIP_TAMANHO_EXCEDIDO" and tempo < LIMITE_S,
          f"document.xml acima de 128 MB: {codigo} em {tempo:.3f} s")


def testar_entradas_invalidas() -> None:
    secao("entradas que nao sao arquivo: caminho que nao existe, tipo errado")
    codigo, _ = _codigo_de(r"C:\nao\existe\nada.docx")
    checa_igual(codigo, "ARQUIVO_ILEGIVEL", "caminho inexistente vira ARQUIVO_ILEGIVEL")
    codigo, _ = _codigo_de(12345)
    checa_igual(codigo, "ENTRADA_INVALIDA", "numero no lugar do arquivo vira ENTRADA_INVALIDA")


def testar_mensagens() -> None:
    secao("mensagens: todo codigo que chega ao usuario tem texto em portugues")
    for codigo in sorted(set(ESPERADOS.values())):
        texto = erros.MENSAGENS.get(codigo, "")
        checa(len(texto) > 20 and texto.endswith("."), f"{codigo} tem mensagem em frase completa")
    checa(ErroDocx("ZIP_INVALIDO").mensagem.startswith("Este arquivo"),
          "mensagem padrao vem do catalogo quando nao ha texto proprio")


def testar_contraprova() -> None:
    secao("contraprova: um .docx valido NAO pode ser acusado como hostil")
    codigo, _ = _codigo_de(fx.bytes_de(fx.documento_completo()))
    checa_igual(codigo, None, "o documento de amostra e' lido sem erro")
    codigo, _ = _codigo_de(fx.docx_hostil()["docx_bom"])
    checa(codigo != "XML_DOCTYPE_PROIBIDO",
          "arquivo que nao e' zip nao e' confundido com DOCTYPE")


def main() -> int:
    testar_casos()
    testar_tamanho_acima_do_limite()
    testar_entradas_invalidas()
    testar_mensagens()
    testar_contraprova()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
