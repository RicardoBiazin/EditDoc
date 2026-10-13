"""Campos de numero de pagina (M5): PAGE e NUMPAGES. Sem Qt e sem lxml.

O campo guarda a instrucao do .docx, normalizada ("PAGE", "NUMPAGES \\* roman").
O valor que aparece depende da pagina: a tela calcula com `valor_do_campo`, e o
arquivo leva so' o ultimo resultado (o Word recalcula ao abrir).

Formato do numero: o da secao (w:pgNumType w:fmt) vale para PAGE; uma opcao
`\\* roman`, `\\* ROMAN`, `\\* alphabetic`, `\\* ALPHABETIC` ou `\\* Arabic` na
instrucao vence. NUMPAGES conta as paginas, sem o numero inicial da secao.

Outros campos (DATE, TOC, REF...) nao sao calculados: desde a 0.1.3 eles voltam ao arquivo
como campos (marcas de inicio e fim no fluxo, `modelo/documento.py`), com o ultimo
resultado como texto editavel, e o Word os atualiza.
"""

from __future__ import annotations

import re

from editdoc.modelo.pagina import Pagina

#: Campos que o EditDoc entende e recalcula.
TIPOS_CAMPO = ("PAGE", "NUMPAGES")
#: Formatos de numero (w:pgNumType w:fmt) que o EditDoc mostra e grava.
FORMATOS_NUMERO = ("decimal", "lowerRoman", "upperRoman", "lowerLetter", "upperLetter")
#: Instrucao mais longa aceita. Instrucao maior e' arquivo estranho: vira texto, com aviso.
INSTRUCAO_MAXIMA = 255
#: Maior numero inicial aceito (w:pgNumType w:start).
NUMERO_INICIAL_MAXIMO = 32767
#: Maior numero escrito em romanos; acima disso o Word tambem cai para decimal.
_ROMANO_MAXIMO = 3999

_OPCAO_FORMATO = re.compile(r"\\\*\s*([A-Za-z]+)")
_OPCOES = {"roman": "lowerRoman", "ROMAN": "upperRoman", "alphabetic": "lowerLetter",
           "ALPHABETIC": "upperLetter", "Arabic": "decimal", "arabic": "decimal"}
_ROMANOS = ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
            (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"))


def normalizar_instrucao(texto: str) -> str:
    """Espacos repetidos viram um so', sem espaco nas pontas."""
    return " ".join(texto.split())


def tipo_do_campo(instrucao: str) -> str | None:
    """"PAGE" ou "NUMPAGES" se a instrucao for de um campo que o EditDoc entende; senao None."""
    if not instrucao or len(instrucao) > INSTRUCAO_MAXIMA:
        return None
    partes = instrucao.split()
    if not partes:
        return None
    tipo = partes[0].upper()
    return tipo if tipo in TIPOS_CAMPO else None


def formato_da_instrucao(instrucao: str) -> str | None:
    """Formato pedido pela opcao `\\*` da instrucao, ou None se ela nao pede."""
    for m in _OPCAO_FORMATO.finditer(instrucao):
        formato = _OPCOES.get(m.group(1))
        if formato is not None:
            return formato
    return None


def _romano(n: int) -> str:
    saida = []
    for valor, simbolo in _ROMANOS:
        while n >= valor:
            saida.append(simbolo)
            n -= valor
    return "".join(saida)


def _letra(n: int) -> str:
    """Como o Word: a..z, depois aa, bb... zz, depois aaa..."""
    repeticoes = (n - 1) // 26 + 1
    return chr(ord("a") + (n - 1) % 26) * repeticoes


def formatar_numero(n: int, formato: str) -> str:
    """Numero no formato do .docx. Fora do que o formato escreve, cai para decimal."""
    if formato in ("lowerRoman", "upperRoman") and 0 < n <= _ROMANO_MAXIMO:
        texto = _romano(n)
        return texto.upper() if formato == "upperRoman" else texto
    if formato in ("lowerLetter", "upperLetter") and 0 < n <= 780:  # ate' 30 letras repetidas
        texto = _letra(n)
        return texto.upper() if formato == "upperLetter" else texto
    return str(n)


def numero_da_pagina(indice: int, pagina: Pagina) -> int:
    """Numero que a pagina `indice` (a partir de 0) mostra, com o numero inicial da secao."""
    inicio = pagina.numero_inicial if pagina.numero_inicial is not None else 1
    return inicio + indice


def valor_do_campo(instrucao: str, indice: int, total: int, pagina: Pagina) -> str:
    """Texto que o campo mostra na pagina `indice` de um documento com `total` paginas."""
    tipo = tipo_do_campo(instrucao)
    pedido = formato_da_instrucao(instrucao)
    if tipo == "PAGE":
        return formatar_numero(numero_da_pagina(indice, pagina), pedido or pagina.formato_numero)
    if tipo == "NUMPAGES":
        return formatar_numero(max(1, total), pedido or "decimal")
    return ""


def tipo_da_pagina(indice: int, pagina: Pagina) -> str:
    """Qual cabecalho (e rodape) vale na pagina: "primeira", "par" ou "padrao".

    Par ou impar segue o numero mostrado na pagina (com o numero inicial), como no Word.
    """
    if indice == 0 and pagina.primeira_diferente:
        return "primeira"
    if pagina.pares_impares and numero_da_pagina(indice, pagina) % 2 == 0:
        return "par"
    return "padrao"
