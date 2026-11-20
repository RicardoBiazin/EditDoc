"""Legendas e referencias cruzadas como as do Word (0.1.37). Sem Qt e sem lxml.

Legenda: o paragrafo no estilo "caption" (Legenda) com o rotulo, o numero e o texto. O numero e'
o resultado de um campo `SEQ Figura \\* ARABIC`: o Word (e o EditDoc, quando o usuario manda
atualizar) o recalcula contando os campos do mesmo identificador na ordem do documento. O
identificador e' o rotulo ("Figura", "Tabela", "Equação").

SEQ entendido: o identificador, `\\* ARABIC|roman|ROMAN|alphabetic|ALPHABETIC` (e `MERGEFORMAT`,
`CHARFORMAT`, que nao mudam o numero), `\\n` (o proximo, o padrao), `\\c` (repete o ultimo),
`\\r n` (recomeca em n), `\\h` (resultado oculto) e `\\s n` (recomeca depois de cada titulo de
nivel n). Outra opcao, ou o SEQ que cita um marcador, nao e' recalculado: o campo volta ao arquivo
como veio.

Referencia cruzada: `REF _Ref123456789 \\h` (o texto do marcador) e `PAGEREF _Ref123456789 \\h` (a
pagina dele); `REF ... \\r` ou `\\w` e' o numero de lista do paragrafo do marcador. O marcador
`_Ref` + 9 digitos e' oculto, como os do Word.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from editdoc.modelo.campos import formatar_numero
from editdoc.modelo.documento import Campo, MarcaCampo, Paragrafo, Run

#: Os rotulos que o Word oferece (em portugues).
ROTULOS = ("Figura", "Tabela", "Equação")
#: Prefixo dos marcadores ocultos das referencias cruzadas.
PREFIXO_REFERENCIA = "_Ref"
#: O estilo do paragrafo da legenda (nome canonico do Word).
ESTILO_LEGENDA = "caption"
#: Maior rotulo aceito (o identificador do SEQ vai na instrucao, que tem limite).
ROTULO_MAXIMO = 40
#: Texto da legenda mais longo do que isso e' cortado.
TEXTO_MAXIMO = 500
#: O que o Word escreve na referencia cujo marcador sumiu.
SEM_MARCADOR = "Erro! Indicador não definido."

_FORMATOS = {"ARABIC": "decimal", "roman": "lowerRoman", "ROMAN": "upperRoman",
             "alphabetic": "lowerLetter", "ALPHABETIC": "upperLetter"}
_NOMES_FORMATO = {v: k for k, v in _FORMATOS.items()}
_IGNORADOS = {"MERGEFORMAT", "CHARFORMAT"}
_PEDACOS = re.compile(r'"([^"]*)"|(\S+)')


def _pedacos(instrucao: str) -> list[str]:
    return [a if a else b for a, b in _PEDACOS.findall(instrucao)]


def rotulo_valido(rotulo: str) -> str:
    """O rotulo limpo ("" se nao serve): sem aspas, barra invertida, quebra de linha ou tab (o
    identificador vai na instrucao do campo), no maximo `ROTULO_MAXIMO`."""
    texto = " ".join(rotulo.split()).replace('"', "").replace("\\", "")
    texto = "".join(c for c in texto if c.isprintable())
    return texto[:ROTULO_MAXIMO].strip()


@dataclass(frozen=True)
class Seq:
    """As opcoes de um campo `SEQ`."""
    rotulo: str
    formato: str = "decimal"
    repetir: bool = False  # \c
    reiniciar: int | None = None  # \r n
    oculto: bool = False  # \h
    nivel_titulo: int | None = None  # \s n


def instrucao_seq(rotulo: str, formato: str = "decimal") -> str:
    nome = f'"{rotulo}"' if " " in rotulo else rotulo
    return f" SEQ {nome} \\* {_NOMES_FORMATO.get(formato, 'ARABIC')} "


def campo_seq(rotulo: str, formato: str = "decimal") -> Campo:
    return Campo(codigo=(instrucao_seq(rotulo, formato),))


def ler_seq(instrucao: str) -> Seq | None:
    """As opcoes de `SEQ ...`; None se nao e' um SEQ ou se o EditDoc nao sabe recalcula-lo."""
    p = _pedacos(instrucao)
    if len(p) < 2 or p[0].upper() != "SEQ" or p[1].startswith("\\"):
        return None
    rotulo = p[1]
    formato, repetir, reiniciar, oculto, nivel = "decimal", False, None, False, None
    i = 2
    while i < len(p):
        o = p[i]
        i += 1
        if o == "\\*":
            if i >= len(p):
                return None
            nome = p[i]
            i += 1
            if nome in _IGNORADOS or nome.upper() in _IGNORADOS:
                continue
            if nome not in _FORMATOS:
                return None
            formato = _FORMATOS[nome]
        elif o.lower() == "\\c":
            repetir = True
        elif o.lower() == "\\n":
            continue
        elif o.lower() == "\\h":
            oculto = True
        elif o.lower() in ("\\r", "\\s"):
            if i >= len(p) or not p[i].isdigit():
                return None
            valor = int(p[i])
            i += 1
            if o.lower() == "\\r":
                reiniciar = valor
            elif 1 <= valor <= 9:
                nivel = valor
            else:
                return None
        else:
            return None  # outro marcador (SEQ Figura Marcador) ou opcao desconhecida
    return Seq(rotulo, formato, repetir, reiniciar, oculto, nivel)


def numerar(eventos: list) -> list[str | None]:
    """O resultado de cada SEQ, contando na ordem do documento.

    `eventos`: ("seq", Seq ou None) e ("titulo", nivel 1 a 9), na ordem do texto. Devolve uma
    lista com o resultado de cada ("seq", ...) (None quando o EditDoc nao recalcula aquele SEQ,
    e entao ele nao entra na contagem)."""
    contadores: dict[str, int] = {}
    titulos = [0] * 10  # titulos de cada nivel vistos, para o \s
    visto: dict[tuple, int] = {}
    saida: list[str | None] = []
    for tipo, dado in eventos:
        if tipo == "titulo":
            for n in range(dado, 10):
                titulos[n] += 1
            continue
        if dado is None:
            saida.append(None)
            continue
        chave = dado.rotulo
        if dado.nivel_titulo is not None:
            marca = titulos[dado.nivel_titulo]  # titulos de nivel ate' n vistos ate' aqui
            if visto.get((chave, dado.nivel_titulo), marca) != marca:
                contadores[chave] = 0
            visto[(chave, dado.nivel_titulo)] = marca
        if dado.reiniciar is not None:
            contadores[chave] = dado.reiniciar
        elif not dado.repetir:
            contadores[chave] = contadores.get(chave, 0) + 1
        else:
            contadores.setdefault(chave, 1)
        saida.append("" if dado.oculto else formatar_numero(contadores[chave], dado.formato))
    return saida


# -- o paragrafo da legenda ---------------------------------------------------------------------

_PONTUACAO_INICIAL = ":;.,-–—)!? "


def texto_depois_do_numero(texto: str) -> str:
    """O texto que vem logo depois do numero: o que o usuario escreveu, com " – " na frente
    quando ele nao comeca com pontuacao ou espaco."""
    texto = " ".join(texto.split())[:TEXTO_MAXIMO]
    if not texto:
        return ""
    return texto if texto[0] in _PONTUACAO_INICIAL else " – " + texto


def paragrafo_da_legenda(rotulo: str, numero: str, texto: str, estilo: str | None,
                         com_rotulo: bool = True, formato: str = "decimal") -> Paragrafo:
    """"Figura 1 – texto": o rotulo, o campo SEQ com o numero de agora e o texto."""
    runs: list[Run] = []
    if com_rotulo:
        runs.append(Run(texto=f"{rotulo} "))
    runs += [Run(marca=MarcaCampo("inicio", campo_seq(rotulo, formato))),
             Run(texto=numero),
             Run(marca=MarcaCampo("fim"))]
    depois = texto_depois_do_numero(texto)
    if depois:
        runs.append(Run(texto=depois))
    return Paragrafo(runs=runs, estilo=estilo)


# -- referencias cruzadas -----------------------------------------------------------------------

@dataclass(frozen=True)
class Ref:
    """As opcoes de `REF` ou `PAGEREF`."""
    tipo: str  # "REF" ou "PAGEREF"
    marcador: str
    numero: bool = False  # REF \r ou \w: o numero de lista do paragrafo do marcador
    hiperlink: bool = False  # \h


def instrucao_ref(marcador: str, tipo: str = "REF", numero: bool = False,
                  hiperlink: bool = True) -> str:
    opcoes = (" \\r" if numero and tipo == "REF" else "") + (" \\h" if hiperlink else "")
    return f" {tipo} {marcador}{opcoes} "


def campo_ref(marcador: str, tipo: str = "REF", numero: bool = False,
              hiperlink: bool = True) -> Campo:
    return Campo(codigo=(instrucao_ref(marcador, tipo, numero, hiperlink),))


def ler_ref(instrucao: str) -> Ref | None:
    """As opcoes de `REF m ...` ou `PAGEREF m ...`; None se nao e' um deles ou se tem opcao que o
    EditDoc nao recalcula (\\p, \\f, \\d, \\t, \\n...)."""
    p = _pedacos(instrucao)
    if len(p) < 2 or p[0].upper() not in ("REF", "PAGEREF") or p[1].startswith("\\"):
        return None
    tipo, marcador = p[0].upper(), p[1]
    numero = hiperlink = False
    i = 2
    while i < len(p):
        o = p[i]
        i += 1
        if o == "\\*":
            if i >= len(p) or (p[i] not in _IGNORADOS and p[i].upper() not in _IGNORADOS):
                return None
            i += 1
        elif o.lower() == "\\h":
            hiperlink = True
        elif o.lower() in ("\\r", "\\w") and tipo == "REF":
            numero = True
        else:
            return None
    return Ref(tipo, marcador, numero, hiperlink)


def numero_sem_ponto(rotulo: str) -> str:
    """O numero de lista como o REF \\r o devolve: sem o ponto final ("1.2." -> "1.2")."""
    return rotulo.strip().rstrip(".").strip()
