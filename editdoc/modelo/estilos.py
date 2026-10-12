"""Estilos nomeados (M6): o catalogo do documento, a heranca e o conjunto padrao. Sem Qt e sem lxml.

Um estilo tem as suas proprias propriedades (`paragrafo` e `caractere`, com os mesmos
nomes de campo de `Paragrafo` e de `Run`) e herda o resto do estilo em que se baseia
(`baseado_em`, o `w:basedOn`). `resolver_*` sobe a cadeia e devolve o efeito final;
`docDefaults` NAO entra na resolucao: ele vira a fonte padrao do documento na tela, e o
XML dele volta ao arquivo intacto.

Formatacao direta = efetivo - estilo: o que o texto tem e o estilo nao daria. E' o que o
modelo guarda em `Paragrafo` e `Run`; o estilo fica em `Paragrafo.estilo` e `Run.estilo`.

O catalogo lido do arquivo guarda o `styles.xml` original (`xml_original`). Ao gravar,
os estilos que o EditDoc nao mexeu voltam byte a byte (latentStyles, docDefaults,
estilos de tabela, estilos que o editor nao usa); os alterados ou novos sao reescritos.

Nomes: o Word grava o nome canonico em ingles ("heading 1"), mesmo no Word em
portugues; o id pode vir sem acento ("Ttulo1"). O mapeamento para a tela usa o nome.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field, fields

#: Campos de `Run` que um estilo pode definir.
CAMPOS_CARACTERE = ("negrito", "italico", "sublinhado", "tachado", "subscrito", "sobrescrito",
                    "tamanho_meio_pt", "fonte", "cor_hex")
#: Campos de `Paragrafo` que um estilo pode definir (mais o nivel de estrutura).
CAMPOS_PARAGRAFO = ("alinhamento", "recuo_esquerdo_tw", "recuo_direito_tw",
                    "recuo_primeira_linha_tw", "espaco_antes_tw", "espaco_depois_tw",
                    "espacamento_linha_pct")
#: Maior cadeia basedOn seguida. O Word aceita bem menos; um ciclo para aqui.
PROFUNDIDADE_MAXIMA = 16
#: Nivel de estrutura de "corpo de texto" no .docx (w:outlineLvl 9).
NIVEL_CORPO = 9

TIPOS = ("paragrafo", "caractere", "tabela", "numeracao")

#: Nome canonico do Word (minusculas) -> nome na tela, em portugues.
NOMES_PT = {
    "normal": "Normal",
    "title": "Título",
    "subtitle": "Subtítulo",
    "quote": "Citação",
    "intense quote": "Citação Intensa",
    "emphasis": "Ênfase",
    "strong": "Forte",
    "subtle emphasis": "Ênfase Sutil",
    "intense emphasis": "Ênfase Intensa",
    "subtle reference": "Referência Sutil",
    "intense reference": "Referência Intensa",
    "book title": "Título do Livro",
    "list paragraph": "Parágrafo da Lista",
    "no spacing": "Sem Espaçamento",
    "caption": "Legenda",
    "header": "Cabeçalho",
    "footer": "Rodapé",
    "hyperlink": "Hiperlink",
    "default paragraph font": "Fonte parág. padrão",
    "normal table": "Tabela normal",
    "table grid": "Grade da Tabela",
    "no list": "Sem lista",
    "list bullet": "Commarcadores",
    "list number": "Numerada",
    "toc heading": "Título do Sumário",
}
for _n in range(1, 10):
    NOMES_PT[f"heading {_n}"] = f"Título {_n}"
_NOME_CANONICO = {v.lower(): k for k, v in NOMES_PT.items()}
_TITULO = re.compile(r"heading ([1-9])")


@dataclass
class Estilo:
    id: str
    nome: str
    tipo: str = "paragrafo"  # "paragrafo", "caractere", "tabela" ou "numeracao"
    baseado_em: str | None = None
    proximo: str | None = None
    vinculado: str | None = None  # w:link (estilo de caractere ligado ao de paragrafo)
    rapido: bool = False  # w:qFormat: aparece na galeria
    prioridade: int | None = None  # w:uiPriority
    oculto: bool = False  # w:semiHidden
    revelar_ao_usar: bool = False  # w:unhideWhenUsed
    padrao: bool = False  # w:default="1"
    personalizado: bool = False  # w:customStyle="1"
    #: Propriedades proprias (sem a heranca): nomes de campo de Paragrafo e de Run.
    paragrafo: dict = field(default_factory=dict)
    caractere: dict = field(default_factory=dict)
    #: w:outlineLvl proprio (0 = Titulo 1). None = herda.
    nivel: int | None = None
    #: Numeracao que o estilo liga (numPr): "marcadores" ou "numeracao". So' leitura.
    numeracao: str | None = None
    #: Elementos on/off de pPr sem lugar no modelo, para o estilo gerado pelo EditDoc
    #: (keepNext, keepLines, contextualSpacing). O estilo lido do arquivo os guarda no XML.
    extras: tuple = ()
    #: Esta' no styles.xml original (o XML dele volta igual se nao for alterado).
    no_arquivo: bool = False
    alterado: bool = False
    #: Valores lidos do arquivo, para gravar so' o que mudou: {"paragrafo": {...}, ...}.
    originais: dict = field(default_factory=dict)

    def nome_exibido(self) -> str:
        return nome_exibido(self.nome)


def nome_exibido(nome: str) -> str:
    """Nome que a tela mostra: o canonico do Word traduzido, ou o proprio nome."""
    return NOMES_PT.get(nome.lower(), nome)


def nome_canonico(nome_tela: str) -> str:
    """O inverso: 'Título 1' -> 'heading 1'. Nome que nao e' de estilo interno volta igual."""
    return _NOME_CANONICO.get(nome_tela.lower(), nome_tela)


def nivel_de_titulo(nome: str) -> int | None:
    """'heading 2' -> 1 (o outlineLvl). None se nao e' um titulo do Word."""
    m = _TITULO.fullmatch(nome.lower())
    return int(m.group(1)) - 1 if m else None


@dataclass
class Estilos:
    """Catalogo de estilos de um documento, na ordem do arquivo."""
    itens: dict[str, Estilo] = field(default_factory=dict)
    #: styles.xml original (bytes). None = documento novo: o escritor gera tudo.
    xml_original: bytes | None = None
    #: theme1.xml original (bytes), para as fontes de tema voltarem iguais. None = sem tema.
    tema_original: bytes | None = None
    #: Fontes do tema: {"major": "Calibri Light", "minor": "Calibri"}.
    fontes_tema: dict = field(default_factory=dict)
    #: docDefaults: propriedades de caractere e de paragrafo do documento.
    padrao_caractere: dict = field(default_factory=dict)
    padrao_paragrafo: dict = field(default_factory=dict)

    # -- consulta -------------------------------------------------------------
    def obter(self, sid: str | None) -> Estilo | None:
        return self.itens.get(sid) if sid else None

    def id_padrao(self, tipo: str = "paragrafo") -> str | None:
        """O estilo padrao do tipo (w:default="1"); para paragrafo, "Normal" se faltar."""
        for e in self.itens.values():
            if e.tipo == tipo and e.padrao:
                return e.id
        if tipo == "paragrafo" and "Normal" in self.itens:
            return "Normal"
        return None

    def por_nome(self, nome: str) -> Estilo | None:
        """Estilo pelo nome canonico ou pelo nome na tela, sem diferenca de caixa."""
        alvo = nome.lower()
        canon = nome_canonico(nome).lower()
        for e in self.itens.values():
            if e.nome.lower() in (alvo, canon):
                return e
        return None

    def cadeia(self, sid: str | None) -> list[Estilo]:
        """O estilo e as bases, do proprio para a raiz. Para em ciclo ou profundidade."""
        saida: list[Estilo] = []
        vistos: set[str] = set()
        while sid and sid not in vistos and len(saida) < PROFUNDIDADE_MAXIMA:
            vistos.add(sid)
            e = self.itens.get(sid)
            if e is None:
                break
            saida.append(e)
            sid = e.baseado_em
        return saida

    def resolver_paragrafo(self, sid: str | None, com_padrao: bool = False) -> tuple[dict, dict]:
        """(propriedades de paragrafo, de caractere) efetivas de um estilo de paragrafo.

        Inclui o "nivel" (outlineLvl) nas de paragrafo. `com_padrao` poe o docDefaults de
        paragrafo (8 pt depois, 1,08 no Word) por baixo da cadeia, como o Word faz fora
        das tabelas (M8). Dentro da tabela o estilo "Table Grid" zera esse espacamento:
        quem resolve um paragrafo de celula passa False.
        """
        par: dict = ({k: v for k, v in self.padrao_paragrafo.items()
                      if k in CAMPOS_PARAGRAFO and v is not None} if com_padrao else {})
        car: dict = {}
        nivel = None
        for e in reversed(self.cadeia(sid)):
            par.update({k: v for k, v in e.paragrafo.items() if v is not None})
            car.update({k: v for k, v in e.caractere.items() if v is not None})
            if e.nivel is not None:
                nivel = e.nivel
        if nivel is not None and nivel < NIVEL_CORPO:
            par["nivel"] = nivel
        return par, car

    def resolver_caractere(self, sid: str | None) -> dict:
        car: dict = {}
        for e in reversed(self.cadeia(sid)):
            car.update({k: v for k, v in e.caractere.items() if v is not None})
        return car

    def base_de_caractere(self, sid_par: str | None, sid_car: str | None) -> dict:
        """O que o texto tem sem formatacao direta: o paragrafo e, por cima, o caractere."""
        _par, car = self.resolver_paragrafo(sid_par or self.id_padrao())
        car = dict(car)
        car.update(self.resolver_caractere(sid_car))
        return car

    def numeracao_de(self, sid: str | None) -> str | None:
        for e in self.cadeia(sid):
            if e.numeracao is not None:
                return e.numeracao
        return None

    def rapidos(self) -> list[Estilo]:
        """Os da galeria (qFormat), de paragrafo e de caractere, na ordem do Word."""
        lista = [e for e in self.itens.values()
                 if e.rapido and e.tipo in ("paragrafo", "caractere") and not e.oculto]
        return sorted(lista, key=_ordem_da_galeria)

    def visiveis(self) -> list[Estilo]:
        """Todos os de paragrafo e de caractere que o painel de estilos lista."""
        lista = [e for e in self.itens.values()
                 if e.tipo in ("paragrafo", "caractere") and not e.oculto]
        return sorted(lista, key=lambda e: e.nome_exibido().lower())

    # -- alteracao ------------------------------------------------------------
    def copia(self) -> "Estilos":
        return copy.deepcopy(self)

    def novo_id(self, nome: str) -> str:
        """Id unico a partir do nome: so' letras e digitos ASCII, como o Word faz."""
        base = re.sub(r"[^A-Za-z0-9]", "", _sem_acento(nome)) or "Estilo"
        sid, n = base, 1
        while sid in self.itens:
            n += 1
            sid = f"{base}{n}"
        return sid

    def garantir(self, nome_canonico_: str) -> Estilo | None:
        """O estilo interno pelo nome ('heading 1'); se o documento nao o tem, cria o padrao.

        E' o que o Word faz com os estilos latentes: Titulo 1 passa a existir quando e' usado.
        """
        achado = self.por_nome(nome_canonico_)
        if achado is not None:
            return achado
        modelo = next((e for e in definicoes_padrao() if e.nome.lower() == nome_canonico_.lower()),
                      None)
        if modelo is None:
            return None
        novo = copy.deepcopy(modelo)
        if novo.id in self.itens:
            novo.id = self.novo_id(novo.id)
        for chave in ("baseado_em", "proximo"):
            alvo = getattr(novo, chave)
            if alvo == "Normal":
                setattr(novo, chave, self.id_padrao())
            elif alvo and alvo not in self.itens:
                setattr(novo, chave, None if chave == "baseado_em" else novo.id)
        if novo.proximo is None:
            novo.proximo = novo.id
        self.itens[novo.id] = novo
        return novo

    # -- serializacao (para o desfazer da tela) --------------------------------
    def para_json(self) -> str:
        return json.dumps([_estilo_para_dict(e) for e in self.itens.values()],
                          ensure_ascii=False, sort_keys=True)

    @classmethod
    def de_json(cls, texto: str, base: "Estilos") -> "Estilos":
        """Itens do JSON; o resto (XML original, tema, docDefaults) vem de `base`."""
        saida = cls(itens={}, xml_original=base.xml_original, tema_original=base.tema_original,
                    fontes_tema=dict(base.fontes_tema), padrao_caractere=dict(base.padrao_caractere),
                    padrao_paragrafo=dict(base.padrao_paragrafo))
        validos = {f.name for f in fields(Estilo)}
        for dado in json.loads(texto):
            dado = {k: v for k, v in dado.items() if k in validos}
            dado["extras"] = tuple(dado.get("extras") or ())
            estilo = Estilo(**dado)
            saida.itens[estilo.id] = estilo
        return saida


def _estilo_para_dict(e: Estilo) -> dict:
    d = asdict(e)
    d["extras"] = list(e.extras)
    return d


def _sem_acento(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))


def _ordem_da_galeria(e: Estilo) -> tuple:
    return (e.prioridade if e.prioridade is not None else 99, e.nome_exibido().lower())


def props_proprias(efetivo: dict, base: dict, campos: tuple) -> dict:
    """Propriedades que um estilo novo precisa ter para que, sobre `base`, de' `efetivo`."""
    return {k: efetivo.get(k) for k in campos if efetivo.get(k) is not None
            and efetivo.get(k) != base.get(k)}


# -- conjunto padrao do Word -------------------------------------------------------

#: Cores do tema Office do Word 2013 em diante, ja' resolvidas (o EditDoc nao grava tema).
_AZUL_TITULO = "2F5496"
_AZUL_ESCURO = "1F3763"


def definicoes_padrao() -> list[Estilo]:
    """O conjunto do documento novo: os estilos rapidos do Word, com os ids em ingles.

    Valores do Word 2013 em diante (tema Office), com a fonte de titulo explicita
    ("Calibri Light"), porque o documento novo nao tem parte de tema.
    """
    titulo_fonte = "Calibri Light"
    return [
        Estilo("Normal", "Normal", padrao=True, rapido=True, prioridade=0, proximo="Normal"),
        Estilo("Heading1", "heading 1", baseado_em="Normal", proximo="Normal", rapido=True,
               prioridade=9, nivel=0, extras=("keepNext", "keepLines"),
               paragrafo={"espaco_antes_tw": 240, "espaco_depois_tw": 0},
               caractere={"fonte": titulo_fonte, "cor_hex": _AZUL_TITULO, "tamanho_meio_pt": 32}),
        Estilo("Heading2", "heading 2", baseado_em="Normal", proximo="Normal", rapido=True,
               prioridade=9, revelar_ao_usar=True, nivel=1, extras=("keepNext", "keepLines"),
               paragrafo={"espaco_antes_tw": 40, "espaco_depois_tw": 0},
               caractere={"fonte": titulo_fonte, "cor_hex": _AZUL_TITULO, "tamanho_meio_pt": 26}),
        Estilo("Heading3", "heading 3", baseado_em="Normal", proximo="Normal", rapido=True,
               prioridade=9, revelar_ao_usar=True, nivel=2, extras=("keepNext", "keepLines"),
               paragrafo={"espaco_antes_tw": 40, "espaco_depois_tw": 0},
               caractere={"fonte": titulo_fonte, "cor_hex": _AZUL_ESCURO, "tamanho_meio_pt": 24}),
        Estilo("Title", "Title", baseado_em="Normal", proximo="Normal", rapido=True,
               prioridade=10, extras=("contextualSpacing",),
               paragrafo={"espaco_depois_tw": 0, "espacamento_linha_pct": 100},
               caractere={"fonte": titulo_fonte, "tamanho_meio_pt": 56}),
        Estilo("Subtitle", "Subtitle", baseado_em="Normal", proximo="Normal", rapido=True,
               prioridade=11, paragrafo={"espaco_depois_tw": 160},
               caractere={"cor_hex": "5A5A5A", "tamanho_meio_pt": 22}),
        Estilo("Quote", "Quote", baseado_em="Normal", proximo="Normal", rapido=True,
               prioridade=29,
               paragrafo={"espaco_antes_tw": 200, "espaco_depois_tw": 160, "alinhamento": "centro",
                          "recuo_esquerdo_tw": 864, "recuo_direito_tw": 864},
               caractere={"italico": True, "cor_hex": "404040"}),
        Estilo("ListParagraph", "List Paragraph", baseado_em="Normal", rapido=True,
               prioridade=34, proximo="ListParagraph", extras=("contextualSpacing",),
               paragrafo={"recuo_esquerdo_tw": 720}),
        Estilo("NoSpacing", "No Spacing", rapido=True, prioridade=1, proximo="NoSpacing",
               paragrafo={"espaco_depois_tw": 0, "espacamento_linha_pct": 100}),
        Estilo("Emphasis", "Emphasis", tipo="caractere", rapido=True, prioridade=20,
               caractere={"italico": True}),
        Estilo("Strong", "Strong", tipo="caractere", rapido=True, prioridade=22,
               caractere={"negrito": True}),
    ]


def catalogo_padrao() -> Estilos:
    """Catalogo de um documento sem styles.xml de origem (o leitor parte dele)."""
    return Estilos(itens={e.id: e for e in definicoes_padrao()})


#: docDefaults de paragrafo do documento novo, os mesmos que o escritor grava
#: (formato_docx/padroes.py): 8 pt depois e 1,08 entre linhas.
PARAGRAFO_PADRAO_NOVO = {"espaco_depois_tw": 160, "espacamento_linha_pct": 108}


def catalogo_de_documento_novo(fonte: str, tamanho_pt: float) -> Estilos:
    """Catalogo do documento novo da janela (M8): a fonte e o tamanho da preferencia e o
    espacamento do Word. O escritor grava o docDefaults daqui."""
    est = catalogo_padrao()
    est.padrao_caractere = {"fonte": fonte, "tamanho_meio_pt": round(float(tamanho_pt) * 2)}
    est.padrao_paragrafo = dict(PARAGRAFO_PADRAO_NOVO)
    return est
