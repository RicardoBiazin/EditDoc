"""Secoes do documento (0.1.12). Sem Qt e sem lxml.

No .docx a secao termina num paragrafo: o w:sectPr dentro do w:pPr diz como e' a secao que
acaba ali (papel, margens, cabecalhos, numeracao...). A ultima secao e' o w:sectPr do fim do
w:body. No modelo e' igual: `Paragrafo.secao` (a secao que termina naquele paragrafo do
corpo) e, para a ultima, os campos de sempre do `Documento` (`pagina`, `cabecalhos`,
`rodapes`) mais `Documento.secao` (tipo, extras e o XML de origem dela).

- `tipo` e' o w:type: como a secao COMECA em relacao a anterior (nextPage, continuous,
  evenPage, oddPage, nextColumn). None = o arquivo nao diz (o Word entende nextPage).
- `cabecalhos` e `rodapes`: so' os que a secao declara (w:headerReference/w:footerReference).
  O que ela nao declara vem da secao anterior, como no Word (`faixa_efetiva`).
- `extras`: o w:sectPr de origem em forma canonica, sem o que o modelo representa
  (referencias, w:type, w:titlePg, os atributos de w:pgSz, w:pgMar e w:pgNumType que viram
  `Pagina`). Colunas, numeracao de linhas, alinhamento vertical, bordas de pagina, grade,
  protecao, direcao do texto, rsids... voltam ao arquivo iguais. Entra na comparacao.
- `original`: o w:sectPr de origem sem as referencias (forma canonica), fora da comparacao:
  o escritor parte dele (ordem dos filhos, `w:titlePg w:val="0"`, atributos que o arquivo
  omitia) e so' muda o que o modelo mudou.
- `chaves`: (onde, tipo) -> chave da parte de cabecalho ou rodape. Duas secoes com a mesma
  chave e o mesmo conteudo usam a mesma parte no arquivo (o Word aceita). Fora da comparacao.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from editdoc.modelo.pagina import Pagina

#: Valores de w:type (ST_SectionMark).
TIPOS_SECAO = ("nextPage", "continuous", "evenPage", "oddPage", "nextColumn")
#: Rotulo de cada tipo na tela ("Quebra de seção (Próxima página)").
ROTULOS_TIPO = {
    "nextPage": "Próxima página",
    "continuous": "Contínua",
    "evenPage": "Página par",
    "oddPage": "Página ímpar",
    "nextColumn": "Próxima coluna",
}
#: Mais secoes que isto num arquivo e' arquivo hostil: as que passam viram uma so' (aviso SECAO).
SECOES_MAXIMAS = 2000
#: Maior numero de colunas aceito (w:cols w:num); o Word aceita ate' 45.
COLUNAS_MAXIMAS = 45


@dataclass
class Secao:
    pagina: Pagina = field(default_factory=Pagina)
    tipo: str | None = None
    cabecalhos: dict = field(default_factory=dict)
    rodapes: dict = field(default_factory=dict)
    extras: str | None = None
    original: str | None = field(default=None, compare=False, repr=False)
    chaves: dict = field(default_factory=dict, compare=False, repr=False)
    #: Colunas (w:cols) que a secao tem: (numero, espaco em twips). So' informativo: as colunas
    #: voltam ao arquivo pelos extras e a tela mostra uma coluna. Fora da comparacao.
    colunas: tuple = field(default=(1, 0), compare=False)

    def faixas(self, onde: str) -> dict:
        return self.cabecalhos if onde == "cabecalho" else self.rodapes


def comeca_em_pagina_nova(tipo: str | None, anterior: Pagina | None, atual: Pagina) -> bool:
    """A secao comeca numa pagina nova? Continua so' quando o papel e' o mesmo (com papel ou
    orientacao diferente o Word tambem comeca outra pagina). Proxima coluna numa secao de uma
    coluna (a tela mostra uma coluna so') e' pagina nova."""
    if tipo != "continuous":
        return True
    if anterior is None:
        return False
    return (anterior.largura_tw, anterior.altura_tw) != (atual.largura_tw, atual.altura_tw)


#: Colunas (passo 2): coluna mais estreita que isto fica em uma coluna so' na tela (aviso).
COLUNA_MINIMA_TW = 360


def largura_da_coluna(corpo_tw: float, colunas: int, espaco_tw: float) -> float:
    """Largura de cada coluna igual (w:cols com num e space), em twips."""
    n = max(1, int(colunas))
    return (float(corpo_tw) - (n - 1) * float(espaco_tw)) / n


def _comeca_em_folha_nova(tipo: str | None, anterior: Pagina | None, atual: Pagina) -> bool:
    return tipo != "nextColumn" and comeca_em_pagina_nova(tipo, anterior, atual)


def colunas_na_tela(secoes) -> list[bool]:
    """Quais secoes mostram as colunas na tela (passo 2 das colunas, docs/SPIKES.md).

    `secoes`: [(tipo, Pagina, (numero, espaco) das colunas iguais, ou None se desiguais)] na
    ordem do texto. Mostra a secao com 2 ou mais colunas iguais que comeca em folha nova (ou e' a
    primeira) e cuja seguinte tambem comeca em folha nova (ou e' a ultima): a secao continua
    com colunas no meio da folha (passo 4) continua em uma coluna so', com o aviso COLUNAS."""
    saida = []
    for i, (tipo, pagina, cols) in enumerate(secoes):
        if cols is None or cols[0] < 2:
            saida.append(False)
            continue
        largura = largura_da_coluna(pagina.corpo_largura_tw(), cols[0], cols[1])
        inicio = i == 0 or _comeca_em_folha_nova(tipo, secoes[i - 1][1], pagina)
        fim = i + 1 >= len(secoes) or _comeca_em_folha_nova(secoes[i + 1][0], pagina,
                                                              secoes[i + 1][1])
        saida.append(largura >= COLUNA_MINIMA_TW and inicio and fim)
    return saida


def paridade_pedida(tipo: str | None) -> int | None:
    """1 para oddPage (comeca em pagina impar), 0 para evenPage, None para os outros."""
    if tipo == "oddPage":
        return 1
    if tipo == "evenPage":
        return 0
    return None


def secao_final(doc) -> Secao:
    """A ultima secao com os campos do documento (pagina, cabecalhos e rodapes dele)."""
    base = getattr(doc, "secao", None) or Secao()
    return replace(base, pagina=doc.pagina, cabecalhos=doc.cabecalhos, rodapes=doc.rodapes)


def secoes_de(doc) -> list[Secao]:
    """Todas as secoes, na ordem: as que terminam em paragrafo do corpo e a ultima."""
    saida = [b.secao for b in doc.paragrafos if getattr(b, "secao", None) is not None]
    saida.append(secao_final(doc))
    return saida


def faixas_das_secoes(doc):
    """(onde, tipo, blocos) de cada cabecalho e rodape declarado pelas secoes que terminam em
    paragrafo (os da ultima secao sao `doc.cabecalhos` e `doc.rodapes`)."""
    for b in doc.paragrafos:
        secao = getattr(b, "secao", None)
        if secao is None:
            continue
        for onde, faixas in (("cabecalho", secao.cabecalhos), ("rodape", secao.rodapes)):
            for tipo, blocos in faixas.items():
                yield onde, tipo, blocos


def faixa_efetiva(secoes: list, indice: int, onde: str, tipo: str):
    """(indice da secao que declara, blocos) do cabecalho/rodape `tipo` da secao `indice`, com
    a heranca do Word (a secao que nao declara usa o da anterior). None se nenhuma declara."""
    for j in range(min(indice, len(secoes) - 1), -1, -1):
        faixas = secoes[j].faixas(onde)
        if tipo in faixas:
            return j, faixas[tipo]
    return None


def numeros_iniciais(paginas_por_secao: list[int], secoes: list[Pagina]) -> list[int]:
    """Numero da primeira pagina de cada secao: o w:pgNumType w:start, ou o seguinte ao da
    ultima pagina da secao anterior (a primeira secao comeca em 1)."""
    saida = []
    proximo = 1
    for qtd, pagina in zip(paginas_por_secao, secoes):
        inicio = pagina.numero_inicial if pagina.numero_inicial is not None else proximo
        saida.append(inicio)
        proximo = inicio + max(0, qtd)
    return saida
