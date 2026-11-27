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
0.1.37: `\\t "Estilo;nivel;..."` (estilos proprios), `\\b marcador` (so' o trecho do marcador) e
`\\c "Rotulo"` (o indice de ilustracoes: os paragrafos com um campo SEQ do rotulo, no estilo
"table of figures"). `\\f` e `\\l` (entradas TC) e `\\a` (indice sem rotulo e numero) nao: o campo
com essas opcoes continua preservado, mas o EditDoc nao o reconstroi (`reconstruivel` devolve o
motivo).
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
#: O mesmo no indice de ilustracoes (o Word escreve "Nenhuma entrada de ... foi encontrada").
SEM_ENTRADAS_FIGURAS = "Nenhuma entrada de índice de ilustrações foi encontrada."
#: O que o Word escreve no PAGEREF cujo marcador sumiu.
SEM_MARCADOR = "Erro! Indicador não definido."
#: Prefixo dos marcadores ocultos que o Word cria nos titulos.
PREFIXO_MARCADOR = "_Toc"
#: Mais linhas do que isso no sumario: o resto fica de fora (documento estranho).
LINHAS_MAXIMAS = 5000
#: Mais caracteres numa linha do que isso: o texto e' cortado, como o Word faz (255).
TEXTO_MAXIMO = 255
#: Tabulacao a esquerda depois do numero do titulo ("1.2" + tab): 440 twips por nivel, como o Word.
TAB_NUMERO_TW = 440

_NIVEIS = re.compile(r'\\o\s*"?\s*(\d)\s*-\s*(\d)\s*"?')
_SEM_NUMERO = re.compile(r'\\n(?:\s*"?\s*(\d)\s*-\s*(\d)\s*"?)?')
_NAO_ENTENDIDAS = re.compile(r"\\([fla])(?![a-z])", re.IGNORECASE)
_ROTULO = re.compile(r'\\c\s*(?:"([^"]+)"|([^\s\\"]+))')
_ESTILOS = re.compile(r'\\t\s*"([^"]*)"')
_MARCADOR = re.compile(r'\\b\s*(?:"([^"]+)"|([^\s\\"]+))')
_PAGEREF = re.compile(r"^\s*PAGEREF\s+(\"[^\"]+\"|\S+)", re.IGNORECASE)


@dataclass(frozen=True)
class Opcoes:
    """O que a instrucao do TOC pede. Niveis de 1 a 9 (o 1 e' o Titulo 1)."""
    primeiro: int = 1
    ultimo: int = 3
    links: bool = True
    sem_numero: tuple = ()  # niveis sem o numero da pagina (\n)
    #: \o e \u: entram os titulos pelo nivel. False com so' \t ou \c (so' o que eles pedem).
    titulos: bool = True
    #: \t: ((nome do estilo em minusculas, nivel 1 a 9), ...)
    estilos: tuple = ()
    #: \c: o rotulo do indice de ilustracoes ("Figura"); None = e' um sumario de titulos.
    rotulo: str | None = None
    #: \b: o marcador que limita o sumario a um trecho; None = o documento todo.
    marcador: str | None = None

    def inclui(self, nivel: int) -> bool:
        return self.titulos and self.primeiro <= nivel <= self.ultimo

    def nivel_do_estilo(self, *nomes: str) -> int | None:
        """O nivel que o \\t da' ao estilo (por qualquer um dos nomes dele), ou None."""
        for estilo, nivel in self.estilos:
            if estilo in nomes:
                return nivel
        return None

    def com_numero(self, nivel: int) -> bool:
        return nivel not in self.sem_numero


def eh_sumario(campo: Campo | None) -> bool:
    return campo is not None and campo.tipo() == "TOC"


def eh_indice_de_figuras(campo: Campo | None) -> bool:
    """TOC com \\c: o indice de ilustracoes (ou de tabelas, de equacoes...)."""
    return eh_sumario(campo) and _ROTULO.search(campo.instrucao()) is not None


def _lista_de_estilos(texto: str) -> tuple:
    """`"Meu estilo;1;Outro;2"` -> (("meu estilo", 1), ("outro", 2)). O Word separa pelo
    separador de lista do Windows: ponto e virgula ou virgula."""
    partes = [p.strip() for p in re.split(r"[;,]", texto)]
    saida = []
    for nome, nivel in zip(partes[0::2], partes[1::2]):
        if nome and nivel.isdigit() and 1 <= int(nivel) <= 9:
            saida.append((nome.lower(), int(nivel)))
    return tuple(saida)


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
    e = _ESTILOS.search(instrucao)
    estilos = _lista_de_estilos(e.group(1)) if e else ()
    r = _ROTULO.search(instrucao)
    rotulo = (r.group(1) or r.group(2)) if r else None
    b = _MARCADOR.search(instrucao)
    marcador = (b.group(1) or b.group(2)) if b else None
    pede_titulos = m is not None or re.search(r"\\u(?![a-z])", instrucao) is not None
    titulos = pede_titulos or not (e or r)
    return Opcoes(primeiro, ultimo, links, sem, titulos, estilos, rotulo, marcador)


def reconstruivel(instrucao: str) -> str:
    """"" se o EditDoc sabe refazer este sumario; senao, o motivo (para a barra de status)."""
    m = _NAO_ENTENDIDAS.search(instrucao)
    if m is None:
        return ""
    opcao = m.group(1).lower()
    if opcao == "a":
        return ("Este índice de ilustrações usa a opção \\a (sem rótulo e número), que o EditDoc "
                "não reconstrói. Use \"Atualizar só os números de página\".")
    return (f"Este sumário usa a opção \\{opcao} (entradas TC), que o EditDoc não reconstrói. "
            "Use \"Atualizar só os números de página\".")


def marcador_do_pageref(instrucao: str) -> str | None:
    """O marcador de `PAGEREF _Toc123 \\h`, ou None se nao for PAGEREF."""
    m = _PAGEREF.match(instrucao)
    if m is None:
        return None
    nome = m.group(1).strip('"')
    return nome or None


def nome_de_marcador(usados: set, semente: int = 0, prefixo: str = PREFIXO_MARCADOR) -> str:
    """Um nome `_Toc` (ou outro `prefixo`) + 9 digitos que nao esta' em `usados` (e entra nele)."""
    numero = 100000000 + (semente % 800000000)
    while f"{prefixo}{numero}" in usados:
        numero += 1
        if numero > 999999999:
            numero = 100000000
    nome = f"{prefixo}{numero}"
    usados.add(nome)
    return nome


def texto_do_titulo(bruto: str) -> str:
    """O texto da linha: sem objetos e marcas (U+FFFC), quebra de linha e tabulacao viram espaco."""
    texto = bruto.replace("\ufffc", "").replace("\u2028", " ").replace("\t", " ")
    texto = texto.replace("\u2029", " ").strip()
    return texto[:TEXTO_MAXIMO]


@dataclass(frozen=True)
class Entrada:
    """Uma linha do sumario: o titulo, o nivel (1 a 9), o marcador e o numero da pagina.
    `numero` e' o numero de lista do titulo ("1.2"), que o Word poe antes do texto, com uma
    tabulacao (0.1.37)."""
    texto: str
    nivel: int
    marcador: str
    pagina: str = ""
    numero: str = ""


def campo_pageref(marcador: str) -> Campo:
    return Campo(codigo=(f" PAGEREF {marcador} \\h ",))


def campo_toc(instrucao: str = INSTRUCAO_PADRAO) -> Campo:
    return Campo(codigo=(instrucao,))


def instrucao_de_figuras(rotulo: str) -> str:
    """O codigo do indice de ilustracoes do rotulo: `TOC \\h \\z \\c "Figura"`."""
    return f' TOC \\h \\z \\c "{rotulo}" '


def _extras_de(extras, entrada: "Entrada", tem_pagina: bool) -> str | None:
    """`extras` e' o w:pPr da tabulacao, ou uma funcao (entrada, tem numero de pagina) que
    escolhe um."""
    if callable(extras):
        return extras(entrada, tem_pagina)
    return extras if tem_pagina else None


def paragrafo_da_entrada(entrada: Entrada, estilo: str | None, extras, opcoes: Opcoes) -> Paragrafo:
    """O paragrafo de uma linha (sem a marca do inicio do sumario)."""
    link = Link(ancora=entrada.marcador, historico=True) if opcoes.links else None
    runs: list[Run] = []
    if entrada.numero:
        runs += [Run(texto=entrada.numero, link=link), Run(texto="\t", link=link)]
    runs.append(Run(texto=entrada.texto or " ", link=link))
    com_pagina = opcoes.com_numero(entrada.nivel)
    if com_pagina:
        runs += [Run(texto="\t", link=link),
                 Run(marca=MarcaCampo("inicio", campo_pageref(entrada.marcador)), link=link),
                 Run(texto=entrada.pagina or "1", link=link),
                 Run(marca=MarcaCampo("fim"), link=link)]
    return Paragrafo(runs=runs, estilo=estilo,
                     extras=_extras_de(extras, entrada, com_pagina))


def paragrafos_do_sumario(entradas: list[Entrada], estilos: dict, extras,
                          opcoes: Opcoes, estilo_vazio: str | None = None,
                          sem_entradas: str = SEM_ENTRADAS) -> list[Paragrafo]:
    """Os paragrafos das linhas. `estilos`: nivel -> id do estilo "toc N". Sem entrada nenhuma,
    um paragrafo com o aviso do Word."""
    if not entradas:
        return [Paragrafo(runs=[Run(texto=sem_entradas, negrito=True)], estilo=estilo_vazio)]
    return [paragrafo_da_entrada(e, estilos.get(e.nivel), extras, opcoes)
            for e in entradas[:LINHAS_MAXIMAS]]
