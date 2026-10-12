"""Modelo -> .docx -> modelo: ida-e-volta igual, sem aviso proprio, e idempotente.

As fixtures sao geradas por codigo (tests/fixtures_docx.py). Contraprova: um
modelo alterado de proposito tem de ser diferente do lido de volta.
"""

from __future__ import annotations

import dataclasses

from ajudantes import RAIZ, checa, checa_igual, resumir, secao  # noqa: F401 - RAIZ ajusta sys.path
import fixtures_docx as fx

from editdoc.formato_docx.escritor import escrever, escrever_com_avisos
from editdoc.formato_docx.leitor import ler
from editdoc.modelo.documento import Documento, Paragrafo, Run, normalizar


def iguais(a: Documento, b: Documento) -> bool:
    return normalizar(a).paragrafos == normalizar(b).paragrafos


def testar_ida_e_volta() -> None:
    secao("ida e volta: modelo -> bytes -> modelo, igual depois de normalizar")
    casos = {
        "amostra completa": fx.documento_completo(),
        "formatos None, False e True misturados": fx.documento_com_formatos_mistos(),
        "numeracao separada por texto": fx.documento_com_numeracao_separada(),
        "documento vazio": Documento(paragrafos=[Paragrafo()]),
    }
    for nome, doc in casos.items():
        dados, avisos_gravacao = escrever_com_avisos(doc)
        lido, avisos = ler(dados)
        checa(iguais(doc, lido), f"{nome}: modelo igual depois da volta")
        checa_igual(avisos, [], f"{nome}: o proprio arquivo nao gera aviso de leitura")
        checa_igual(avisos_gravacao, [], f"{nome}: a gravacao nao remove nada")


def testar_recursos_especificos() -> None:
    secao("recursos: emoji fora do BMP, tab, quebra, vazio, acentos, listas")
    lido, _ = ler(escrever(fx.documento_completo()))
    textos = ["".join(r.texto for r in p.runs) for p in lido.paragrafos]
    checa("emoji \U0001F600 fora do plano basico e tab\tdepois" in textos,
          "emoji fora do BMP e tab sobrevivem")
    checa("quebra\nde linha dentro do paragrafo" in textos, "quebra de linha volta como quebra")
    checa("  espaços nas pontas  " in textos, "espacos nas pontas sobrevivem")
    checa("Título: ação, coração, à vista, pão." in textos, "acentos sobrevivem")
    checa(sum(1 for t in textos if t == "") == 1, "paragrafo vazio continua vazio")
    tipos = [p.numeracao for p in lido.paragrafos]
    checa(tipos[15:17] == ["marcadores", "marcadores"], "marcadores sobrevivem")
    checa(tipos[17:19] == ["numeracao", "numeracao"], "numeracao sobrevive")
    separados, _ = ler(escrever(fx.documento_com_numeracao_separada()))
    checa(separados.paragrafos[3].numeracao == "numeracao",
          "segunda lista numerada volta como numeracao")


def testar_idempotencia() -> None:
    secao("idempotencia: a segunda ida produz os mesmos bytes")
    doc = fx.documento_completo()
    bytes1 = escrever(doc)
    lido1, _ = ler(bytes1)
    bytes2 = escrever(lido1)
    checa(bytes1 == bytes2, "bytes da segunda gravacao iguais aos da primeira")
    lido2, _ = ler(bytes2)
    checa(iguais(lido1, lido2), "modelo da segunda volta igual ao da primeira")


def testar_contraprova() -> None:
    secao("contraprova: um modelo alterado de proposito e' acusado como diferente")
    doc = fx.documento_completo()
    lido, _ = ler(escrever(doc))
    alterado = dataclasses.replace(lido, paragrafos=[dataclasses.replace(p) for p in lido.paragrafos])
    alterado.paragrafos[1].runs[0].negrito = False
    checa(not iguais(doc, alterado), "negrito trocado e' detectado")
    alterado = dataclasses.replace(lido, paragrafos=[dataclasses.replace(p) for p in lido.paragrafos])
    alterado.paragrafos[0].alinhamento = "direita"
    checa(not iguais(doc, alterado), "alinhamento trocado e' detectado")
    alterado = dataclasses.replace(lido, paragrafos=[dataclasses.replace(p) for p in lido.paragrafos])
    alterado.paragrafos[0].runs[0].texto += "x"
    checa(not iguais(doc, alterado), "uma letra a mais no texto e' detectada")


def main() -> int:
    testar_ida_e_volta()
    testar_recursos_especificos()
    testar_idempotencia()
    testar_contraprova()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
