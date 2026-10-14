"""Notas de rodape e de fim (0.1.10): o catalogo do documento. Sem Qt e sem lxml.

No texto, cada nota e' uma referencia no fluxo (`MarcaNota`, em `modelo/documento.py`): o run
com w:footnoteReference ou w:endnoteReference, no corpo. O conteudo (paragrafos, com a marca
do numero da propria nota, w:footnoteRef) fica aqui, em `Notas` (`Documento.notas`, fora da
comparacao, como os comentarios: a conferencia compara as notas a parte).

Partes do pacote (`formato_docx/notas.py`): word/footnotes.xml e word/endnotes.xml. As notas
especiais (separator, continuationSeparator, continuationNotice) voltam com o XML de origem;
o settings.xml cita as duas primeiras. Propriedades: w:footnotePr e w:endnotePr do sectPr e do
settings.xml (formato do numero, inicio, reinicio e posicao); a do sectPr vence.

`original`: o w:footnote do arquivo (bytes). A nota que o EditDoc nao mudou volta com ele,
igual em c14n; a editada ou nova e' gerada pelo escritor de sempre.

Numeracao (`numeros`): continua ou por pagina (so' rodape), no formato do numFmt, comecando
no numStart. A nota com marca personalizada (w:customMarkFollows) nao conta.

`preparar` e' o que o escritor e a conferencia fazem antes de gravar: so' ficam as notas com
referencia no corpo (apagar a marca apaga a nota), a referencia repetida ganha uma copia da
nota com outro id, e os ids ficam unicos e fora dos das notas especiais.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace

#: Tipos do modelo -> nome local no .docx.
LOCAL = {"rodape": "footnote", "fim": "endnote"}
TIPOS = ("rodape", "fim")
#: Notas que o Word sempre tem (o settings.xml cita as duas primeiras).
ESPECIAIS = ("separator", "continuationSeparator", "continuationNotice")

#: Limites contra arquivo hostil (o leitor aplica). Acima deles as notas nao sao lidas (aviso
#: NOTA, com perda; as separadoras continuam voltando, como ate' a 0.1.9).
LIMITES = {
    #: notas de cada tipo
    "notas": 5000,
    #: bytes do w:footnote de uma nota
    "nota_bytes": 1024 * 1024,
    #: bytes do footnotes.xml (ou endnotes.xml) inteiro
    "notas_bytes": 32 * 1024 * 1024,
    #: paragrafos de uma nota
    "nota_paragrafos": 2000,
}

#: Formatos do numero que o EditDoc mostra (w:numFmt). Os outros sao preservados no arquivo e
#: aparecem em decimal na tela (limite registrado).
FORMATOS = ("decimal", "lowerRoman", "upperRoman", "lowerLetter", "upperLetter", "chicago")
REINICIOS = ("continuous", "eachSect", "eachPage")
POSICOES_RODAPE = ("pageBottom", "beneathText")
POSICOES_FIM = ("docEnd", "sectEnd")
#: Simbolos do formato "chicago" (*, adaga, adaga dupla, paragrafo), repetidos depois.
_CHICAGO = ("*", "†", "‡", "§")
NUMERO_MAXIMO = 32767


@dataclass(frozen=True)
class PropriedadesNota:
    """w:footnotePr / w:endnotePr. None = o arquivo nao diz (herda)."""
    formato: str | None = None
    inicio: int | None = None
    reinicio: str | None = None
    posicao: str | None = None


#: O padrao do Word: rodape 1, 2, 3 no pe' da pagina; fim i, ii, iii no fim do documento.
PADRAO = {"rodape": PropriedadesNota("decimal", 1, "continuous", "pageBottom"),
          "fim": PropriedadesNota("lowerRoman", 1, "continuous", "docEnd")}


def efetivas(tipo: str, *camadas: PropriedadesNota | None) -> PropriedadesNota:
    """As propriedades que valem: a primeira camada que diz, depois o padrao do Word."""
    saida = PADRAO[tipo]
    for camada in reversed([c for c in camadas if c is not None]):
        saida = PropriedadesNota(*(v if v is not None else d for v, d in zip(
            (camada.formato, camada.inicio, camada.reinicio, camada.posicao),
            (saida.formato, saida.inicio, saida.reinicio, saida.posicao))))
    return saida


@dataclass(frozen=True)
class Nota:
    """Uma nota. `paragrafos`: os blocos do conteudo (Paragrafo ou Tabela).

    `original`: o w:footnote (ou w:endnote) do arquivo de origem, quando pode voltar igual.
    `relacoes`: as relacoes da parte que o XML de origem cita: (rId, tipo, alvo, externo,
    dados), com os bytes da imagem quando interna (o alvo e' recalculado ao gravar; o Id
    fica).
    """
    tipo: str
    id: int
    paragrafos: tuple = ()
    original: bytes | None = field(default=None, compare=False, repr=False)
    relacoes: tuple = field(default=(), compare=False, repr=False)

    def texto(self) -> str:
        from editdoc.modelo.documento import Paragrafo, paragrafos_de
        partes = []
        for p in paragrafos_de(list(self.paragrafos)):
            if isinstance(p, Paragrafo):
                partes.append("".join(r.texto for r in p.runs if not r.eh_objeto()))
        return "\n".join(partes)


@dataclass(frozen=True)
class Especial:
    """Nota separadora (w:type separator, continuationSeparator ou continuationNotice)."""
    tipo_nota: str
    id: int
    xml: bytes


@dataclass
class Notas:
    """As notas do documento e as partes de origem.

    `itens[tipo]`: as notas, na ordem do arquivo. `especiais[tipo]`: as separadoras.
    `xml[tipo]`: os bytes da parte de origem (volta igual quando nada mudou). `relacoes_parte`:
    todas as relacoes da parte de origem (rId, tipo, alvo, externo, dados). `tipos_rel`: o Type
    da relacao do documento para a parte (o Word tem variantes de URI). `secao` e
    `configuracao`: o footnotePr/endnotePr do sectPr e do settings.xml; `secao_xml`: o do
    sectPr de origem em forma canonica (volta igual enquanto as propriedades nao mudam).
    `originais`: os (tipo, id) de cada nota ao abrir, na ordem.
    """
    itens: dict = field(default_factory=lambda: {"rodape": [], "fim": []})
    especiais: dict = field(default_factory=lambda: {"rodape": [], "fim": []})
    xml: dict = field(default_factory=dict)
    relacoes_parte: dict = field(default_factory=dict)
    tipos_rel: dict = field(default_factory=dict)
    secao: dict = field(default_factory=dict)
    secao_xml: dict = field(default_factory=dict)
    configuracao: dict = field(default_factory=dict)
    originais: tuple = ()
    #: a raiz de cada parte de origem, sem os filhos (namespaces e mc:Ignorable)
    raizes: dict = field(default_factory=dict)

    def obter(self, tipo: str, ident: int) -> Nota | None:
        return next((n for n in self.itens.get(tipo, []) if n.id == ident), None)

    def todas(self) -> list[Nota]:
        return [n for t in TIPOS for n in self.itens.get(t, [])]

    def vazia(self) -> bool:
        return not any(self.itens.get(t) for t in TIPOS)

    def propriedades(self, tipo: str) -> PropriedadesNota:
        """As efetivas: o sectPr, depois o settings.xml, depois o padrao do Word."""
        return efetivas(tipo, self.secao.get(tipo), self.configuracao.get(tipo))

    def proximo_id(self, tipo: str) -> int:
        usados = [n.id for n in self.itens.get(tipo, [])] + \
                 [e.id for e in self.especiais.get(tipo, [])]
        return max([0, *usados]) + 1

    def com_itens(self, itens: dict) -> "Notas":
        novo = copy.copy(self)
        novo.itens = {t: list(itens.get(t, [])) for t in TIPOS}
        return novo


# -- numeracao ----------------------------------------------------------------------------

def _romano(n: int) -> str:
    valores = ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
               (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"))
    saida = []
    for valor, simbolo in valores:
        while n >= valor:
            saida.append(simbolo)
            n -= valor
    return "".join(saida)


def formatar(n: int, formato: str | None) -> str:
    """O numero da nota no formato do w:numFmt. Fora do que o formato escreve, decimal."""
    if formato in ("lowerRoman", "upperRoman") and 0 < n <= 3999:
        texto = _romano(n)
        return texto.upper() if formato == "upperRoman" else texto
    if formato in ("lowerLetter", "upperLetter") and 0 < n <= 780:
        texto = chr(ord("a") + (n - 1) % 26) * ((n - 1) // 26 + 1)
        return texto.upper() if formato == "upperLetter" else texto
    if formato == "chicago" and 0 < n <= 400:
        return _CHICAGO[(n - 1) % 4] * ((n - 1) // 4 + 1)
    return str(n)


def numeros(referencias: list, props: dict, paginas: dict | None = None) -> dict:
    """(tipo, id) -> texto do numero de cada referencia.

    `referencias`: (tipo, id, personalizada) na ordem do texto. `props`: tipo ->
    PropriedadesNota efetivas. `paginas`: (tipo, id) -> pagina da referencia (para o reinicio
    por pagina; sem ela, continua). A referencia personalizada nao conta e nao entra no mapa.
    """
    saida: dict = {}
    contadores: dict = {}
    pagina_atual: dict = {}
    for tipo, ident, personalizada in referencias:
        if personalizada or (tipo, ident) in saida:
            continue
        pr = props.get(tipo) or PADRAO[tipo]
        inicio = pr.inicio if pr.inicio is not None else 1
        if tipo == "rodape" and pr.reinicio == "eachPage" and paginas is not None:
            pagina = paginas.get((tipo, ident))
            if pagina is not None and pagina != pagina_atual.get(tipo):
                pagina_atual[tipo] = pagina
                contadores[tipo] = inicio
        n = contadores.get(tipo, inicio)
        saida[(tipo, ident)] = formatar(n, pr.formato)
        contadores[tipo] = n + 1
    return saida


def texto_do_simbolo(simbolo: str | None) -> str:
    """O texto da marca personalizada (o w:t, ou o caractere do w:sym), sem lxml."""
    if not simbolo:
        return ""
    import re
    m = re.search(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", simbolo)
    if m:
        import html
        return html.unescape(m.group(1))
    m = re.search(r'<w:sym\b[^>]*w:char="([0-9A-Fa-f]{1,4})"', simbolo)
    if m:
        codigo = int(m.group(1), 16)
        if codigo >= 0xF000:
            codigo -= 0xF000  # fonte de simbolos: o mesmo ponto na faixa baixa
        if 0x20 <= codigo < 0xD800:
            return chr(codigo)
    return "*"


# -- preparar para gravar -------------------------------------------------------------------

def referencias_do_corpo(blocos) -> list:
    """(paragrafo, run) de cada referencia de nota no corpo, na ordem."""
    from editdoc.modelo.documento import MarcaNota, paragrafos_de
    saida = []
    for p in paragrafos_de(blocos):
        for r in p.runs:
            if isinstance(r.marca, MarcaNota) and not r.marca.propria:
                saida.append((p, r))
    return saida


def _sem_referencias(blocos) -> int:
    """Tira referencias e numeros de nota de dentro de uma historia que nao os aceita
    (cabecalho, rodape, a propria nota). Devolve quantas sairam."""
    from editdoc.modelo.documento import MarcaNota, paragrafos_de
    tiradas = 0
    for p in paragrafos_de(blocos):
        if any(isinstance(r.marca, MarcaNota) for r in p.runs):
            antes = len(p.runs)
            p.runs = [r for r in p.runs if not isinstance(r.marca, MarcaNota)]
            tiradas += antes - len(p.runs)
    return tiradas


def _sem_referencias_dentro(blocos) -> None:
    """Na nota so' vale o numero da propria nota: referencia a outra nota sai."""
    from editdoc.modelo.documento import MarcaNota, paragrafos_de
    for p in paragrafos_de(blocos):
        if any(isinstance(r.marca, MarcaNota) and not r.marca.propria for r in p.runs):
            p.runs = [r for r in p.runs if not (isinstance(r.marca, MarcaNota)
                                                and not r.marca.propria)]


def preparar(doc):
    """Copia do documento pronta para gravar (o escritor e a conferencia chamam igual).

    - no cabecalho e no rodape a referencia de nota sai (o Word nao tem nota ali);
    - a nota sem referencia no corpo sai do catalogo (apagar a marca apaga a nota);
    - referencia a nota que o catalogo nao tem sai; a referencia repetida ganha uma copia
      da nota com um id novo (colar duas vezes nao faz duas marcas apontarem para a mesma);
    - ids: o da nota fica se e' unico e nao colide com uma especial; senao, o proximo livre.
    Devolve o documento (o mesmo objeto se nao ha' nota nem referencia).
    """
    from editdoc.modelo.documento import MarcaNota, TIPOS_DE_FAIXA
    cat = doc.notas
    refs = referencias_do_corpo(doc.paragrafos)
    faixas_com = any(isinstance(r.marca, MarcaNota) for faixas in (doc.cabecalhos, doc.rodapes)
                     for t in TIPOS_DE_FAIXA if t in faixas
                     for p in _paragrafos(faixas[t]) for r in p.runs)
    if cat is None and not refs and not faixas_com:
        return doc
    saida = copy.copy(doc)
    saida.paragrafos = copy.deepcopy(doc.paragrafos)
    if faixas_com:
        saida.cabecalhos = copy.deepcopy(doc.cabecalhos)
        saida.rodapes = copy.deepcopy(doc.rodapes)
        for faixas in (saida.cabecalhos, saida.rodapes):
            for t in TIPOS_DE_FAIXA:
                if t in faixas:
                    _sem_referencias(faixas[t])
    refs = referencias_do_corpo(saida.paragrafos)
    if cat is None:
        cat = Notas()
    usados = {t: {e.id for e in cat.especiais.get(t, [])} for t in TIPOS}
    novos: dict = {t: [] for t in TIPOS}
    vistos: dict = {}
    remover = set()
    for p, r in refs:
        m = r.marca
        nota = cat.obter(m.tipo, m.id)
        if nota is None:
            remover.add(id(r))
            continue
        chave = (m.tipo, m.id)
        if chave in vistos or m.id in usados[m.tipo] or m.id < 1:
            # Repetida (ou id que colide com uma especial): copia com id novo, gerada de novo.
            ident = max([0, *usados[m.tipo], *(n.id for n in cat.itens.get(m.tipo, []))]) + 1
            while ident in usados[m.tipo]:
                ident += 1
            nota = replace(nota, id=ident, original=None)
            r.marca = replace(m, id=ident)
        vistos[(m.tipo, r.marca.id)] = True
        usados[m.tipo].add(r.marca.id)
        if nota.original is None:
            # Conteudo gerado de novo: so' o numero da propria nota, e campos e marcadores em
            # pares, como no corpo (a nota de origem volta com o XML de origem, como veio).
            from editdoc.modelo.marcas import _equilibrar_historia
            conteudo = copy.deepcopy(list(nota.paragrafos))
            _sem_referencias_dentro(conteudo)
            _equilibrar_historia(conteudo, {"campos": 0, "marcadores": 0})
            nota = replace(nota, paragrafos=tuple(conteudo))
        novos[m.tipo].append(nota)
    if remover:
        for p, r in refs:
            if id(r) in remover:
                p.runs = [x for x in p.runs if x is not r]
    # As notas ficam na ordem do texto, como o Word grava.
    saida.notas = cat.com_itens(novos)
    return saida


def _paragrafos(blocos):
    from editdoc.modelo.documento import paragrafos_de
    return paragrafos_de(blocos)


def mudou(cat: Notas, tipo: str) -> bool:
    """A parte do tipo difere da de origem: notas novas, editadas, fora de ordem ou a menos."""
    if cat.xml.get(tipo) is None:
        return True
    atuais = tuple(n.id for n in cat.itens.get(tipo, []))
    if atuais != tuple(i for t, i in cat.originais if t == tipo):
        return True
    return any(n.original is None for n in cat.itens.get(tipo, []))
