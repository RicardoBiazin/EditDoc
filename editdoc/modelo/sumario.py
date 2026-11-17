"""Sumario (TOC) como o do Word: opcoes da instrucao e as linhas geradas. Sem Qt e sem lxml.

O sumario e' um campo TOC no fluxo (`MarcaCampo`, desde a 0.1.3): o inicio, com o codigo
(`TOC \\o "1-3" \\h \\z \\u`), fica no comeco da primeira linha; o fim, num paragrafo proprio
depois da ultima, como o Word grava. Cada linha e' um paragrafo no estilo "toc N" (Sumario N),
com a tabulacao a direita com pontilhado e, quando a instrucao pede `\\h`, o texto dentro de um
hiperlink interno para o marcador `_Toc...` do titulo. O numero da pagina e' o resultado de um
campo PAGEREF para o mesmo marcador: o Word atualiza esse campo sozinho, e o EditDoc o reescreve
quando o usuario manda atualizar (`edicao/sumario.py`).

Opcoes entendidas: `\\o "a-b"` (niveis de titulo), `\\u` (nivel de estrutura do paragrafo; no
EditDoc o nivel do estilo e o direto sao a mesma coisa), `\\h` (hiperlinks) e `\\n` (sem numero de
pagina; com intervalo, so' nos niveis dele). Sem `\\o` nem `\\u` o Word usa os titulos 1 a 9.
`\\t` (estilos proprios), `\\f` e `\\l` (entradas TC) e `\\c`/`\\a` (indice de ilustracoes) nao:
o campo com essas opcoes continua preservado, mas o EditDoc nao o reconstroi
(`reconstruivel` devolve o motivo).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from editdoc.modelo.documento import Campo, Link, MarcaCampo, Paragrafo, Run

#: A instrucao que o "Inserir sumario" grava: titulos 1 a 3, hiperlinks, sem tabulacao na
#: web (\z) e o nivel de estrutura do paragrafo (\u), a mesma do sumario automatico do Word.
INSTRUCAO_PADRAO = ' TOC \\o "1-3" \\h \\z \\u '
#: O que o Word escreve quando nao acha titulo nenhum.
SEM_ENTRADAS = "Nenhuma entrada de sumário foi encontrada."
#: O que o Word escreve no PAGEREF cujo marcador sumiu.
SEM_MARCADOR = "Erro! Indicador não definido."
#: Prefixo dos marcadores ocultos que o Word cria nos titulos.
PREFIXO_MARCADOR = "_Toc"
#: Mais linhas do que isso no sumario: o resto fica de fora (documento estranho).
LINHAS_MAXIMAS = 5000
#: Mais caracteres numa linha do que isso: o texto e' cortado, como o Word faz (255).
TEXTO_MAXIMO = 255

_NIVEIS = re.compile(r'\\o\s*"?\s*(\d)\s*-\s*(\d)\s*"?')
_SEM_NUMERO = re.compile(r'\\n(?:\s*"?\s*(\d)\s*-\s*(\d)\s*"?)?')
_NAO_ENTENDIDAS = re.compile(r"\\([tflcab])(?![a-z])", re.IGNORECASE)
_PAGEREF = re.compile(r"^\s*PAGEREF\s+(\"[^\"]+\"|\S+)", re.IGNORECASE)


@dataclass(frozen=True)
class Opcoes:
    """O que a instrucao do TOC pede. Niveis de 1 a 9 (o 1 e' o Titulo 1)."""
    primeiro: int = 1
    ultimo: int = 3
    links: bool = True
    sem_numero: tuple = ()  # niveis sem o numero da pagina (\n)

    def inclui(self, nivel: int) -> bool:
        return self.primeiro <= nivel <= self.ultimo

    def com_numero(self, nivel: int) -> bool:
        return nivel not in self.sem_numero


def eh_sumario(campo: Campo | None) -> bool:
    return campo is not None and campo.tipo() == "TOC"


def opcoes_da_instrucao(instrucao: str) -> Opcoes:
    """As opcoes de `TOC ...`. Intervalo invertido ou fora de 1-9 fica no padrao do Word."""
    primeiro, ultimo = 1, 9
    m = _NIVEIS.search(instrucao)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 1 <= a <= b <= 9:
            primeiro, ultimo = a, b
    links = re.search(r"\\h(?![a-z])", instrucao) is not None
    sem: tuple = ()
    n = _SEM_NUMERO.search(instrucao)
    if n:
        if n.group(1):
            a, b = int(n.group(1)), int(n.group(2))
            sem = tuple(range(min(a, b), max(a, b) + 1))
        else:
            sem = tuple(range(1, 10))
    return Opcoes(primeiro, ultimo, links, sem)


def reconstruivel(instrucao: str) -> str:
    """"" se o EditDoc sabe refazer este sumario; senao, o motivo (para a barra de status)."""
    m = _NAO_ENTENDIDAS.search(instrucao)
    if m is None:
        return ""
    opcao = m.group(1).lower()
    if opcao in ("c", "a"):
        return "Este campo é um índice de ilustrações; o EditDoc atualiza só sumários de títulos."
    return (f"Este sumário usa a opção \\{opcao} (estilos próprios, entradas TC ou um trecho "
            "marcado), que o EditDoc não reconstrói. Use \"Atualizar só os números de página\".")


def marcador_do_pageref(instrucao: str) -> str | None:
    """O marcador de `PAGEREF _Toc123 \\h`, ou None se nao for PAGEREF."""
    m = _PAGEREF.match(instrucao)
    if m is None:
        return None
    nome = m.group(1).strip('"')
    return nome or None


def nome_de_marcador(usados: set, semente: int = 0) -> str:
    """Um nome `_Toc` + 9 digitos que nao esta' em `usados` (e entra nele)."""
    numero = 100000000 + (semente % 800000000)
    while f"{PREFIXO_MARCADOR}{numero}" in usados:
        numero += 1
        if numero > 999999999:
            numero = 100000000
    nome = f"{PREFIXO_MARCADOR}{numero}"
    usados.add(nome)
    return nome


def texto_do_titulo(bruto: str) -> str:
    """O texto da linha: sem objetos e marcas (U+FFFC), quebra de linha e tabulacao viram espaco."""
    texto = bruto.replace("\ufffc", "").replace("\u2028", " ").replace("\t", " ")
    texto = texto.replace("\u2029", " ").strip()
    return texto[:TEXTO_MAXIMO]


@dataclass(frozen=True)
class Entrada:
    """Uma linha do sumario: o titulo, o nivel (1 a 9), o marcador e o numero da pagina."""
    texto: str
    nivel: int
    marcador: str
    pagina: str = ""


def campo_pageref(marcador: str) -> Campo:
    return Campo(codigo=(f" PAGEREF {marcador} \\h ",))


def campo_toc(instrucao: str = INSTRUCAO_PADRAO) -> Campo:
    return Campo(codigo=(instrucao,))


def paragrafo_da_entrada(entrada: Entrada, estilo: str | None, extras: str | None,
                         opcoes: Opcoes) -> Paragrafo:
    """O paragrafo de uma linha (sem a marca do inicio do sumario)."""
    link = Link(ancora=entrada.marcador, historico=True) if opcoes.links else None
    runs = [Run(texto=entrada.texto or " ", link=link)]
    if opcoes.com_numero(entrada.nivel):
        runs += [Run(texto="\t", link=link),
                 Run(marca=MarcaCampo("inicio", campo_pageref(entrada.marcador)), link=link),
                 Run(texto=entrada.pagina or "1", link=link),
                 Run(marca=MarcaCampo("fim"), link=link)]
    return Paragrafo(runs=runs, estilo=estilo,
                     extras=extras if opcoes.com_numero(entrada.nivel) else None)


def paragrafos_do_sumario(entradas: list[Entrada], estilos: dict, extras: str | None,
                          opcoes: Opcoes, estilo_vazio: str | None = None) -> list[Paragrafo]:
    """Os paragrafos das linhas. `estilos`: nivel -> id do estilo "toc N". Sem entrada nenhuma,
    um paragrafo com o aviso do Word."""
    if not entradas:
        return [Paragrafo(runs=[Run(texto=SEM_ENTRADAS, negrito=True)], estilo=estilo_vazio)]
    return [paragrafo_da_entrada(e, estilos.get(e.nivel), extras, opcoes)
            for e in entradas[:LINHAS_MAXIMAS]]
