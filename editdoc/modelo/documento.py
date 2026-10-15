"""Modelo do documento: dados puros, sem Qt e sem lxml.

Convencao tri-state, em todos os campos opcionais: None = "herda" (o arquivo nao
diz nada); False ou 0 = "desligado" de forma explicita. None nunca vira False.

Unidades: tamanho em meio-ponto (`w:sz`); recuos e espacos em twips (1/20 de
ponto). Espacamento entre linhas em porcentagem (100 = simples). Imagens em EMU
(914400 por polegada). Bordas em oitavos de ponto (`w:sz` de borda).

Estrutura (M4): `Documento.paragrafos` e' a lista dos blocos do corpo, na ordem do
arquivo. Cada bloco e' um `Paragrafo` ou uma `Tabela` (o nome do campo vem do M2,
quando so' havia paragrafo). Uma celula de tabela tem os seus proprios blocos, e
pode conter outra tabela.

Imagem na linha do texto: um `Run` com `imagem` e o texto CARACTERE_OBJETO
(U+FFFC, o mesmo caractere que o Qt usa para o objeto). Assim o texto do
paragrafo conta a imagem, e a conferencia do arquivo gravado ve a imagem sumir.

Objeto opaco (0.1.2): um `Run` com `objeto` e o texto CARACTERE_OBJETO. Caixa de
texto, forma, grafico, SmartArt, OLE, equacao e imagem flutuante: o XML original e as
partes que ele usa ficam no `ObjetoOpaco`, e voltam iguais ao arquivo. O EditDoc nao
edita o objeto por dentro; apagar remove o objeto inteiro.

Campo (M5): um `Run` com `campo` (a instrucao, "PAGE" ou "NUMPAGES" com as opcoes)
e o texto do ultimo resultado que o arquivo mostrava. O valor real depende da
pagina e e' calculado na tela (modelo/campos.py); o texto so' vai para o arquivo
como resultado guardado, e o Word recalcula.

Cabecalho e rodape (M5): `Documento.cabecalhos` e `Documento.rodapes` levam o tipo
("padrao", "primeira", "par") aos blocos daquela parte. Tipo ausente = o arquivo
nao tem a parte. A escolha de qual aparece em cada pagina esta' em `Pagina`
(primeira_diferente, pares_impares).

Hiperlink (0.1.3): `Run.link` leva o destino (`Link`: endereco externo ou marcador do
documento). Runs vizinhos com o mesmo `Link` formam um w:hyperlink so' no arquivo.

Marcas no fluxo (0.1.3): `Run.marca` e' uma marca sem texto. `MarcaCampo` marca o inicio
(com o codigo do campo) ou o fim de um campo qualquer (DATE, REF, TOC...); o texto entre
as duas e' o ultimo resultado, editavel. O campo pode comecar num paragrafo e terminar em
outro (o sumario), como no Word. `Marcador` marca o inicio ou o fim de um w:bookmark.
`marcas.equilibrar` deixa as marcas em pares antes de gravar.

Listas (0.1.4): `Paragrafo.lista` (numId) e `lista_nivel` (ilvl) sao o w:numPr direto; o
catalogo do numbering.xml fica em `Documento.numeracao` (modelo/numeracao.py), fora da
comparacao, como os estilos. `Paragrafo.numeracao` virou so' o tipo, informativo.

Notas (0.1.10): a referencia a uma nota de rodape ou de fim e' uma marca no fluxo
(`MarcaNota`); o conteudo das notas fica no catalogo `Documento.notas` (modelo/notas.py).

Formatacao preservada (0.1.5): `Run.extras`, `Paragrafo.extras` e os de `Tabela`, `Linha` e
`Celula` guardam o XML das propriedades que o modelo nao representa (formato_docx/
propriedades.py); entram na comparacao, entao runs com extras diferentes nao fundem.
`MarcaConteudo` marca o inicio (com o sdtPr) e o fim de um controle de conteudo no fluxo.
`Imagem.recorte` e' o a:srcRect.

`normalizar` funde runs vizinhos de mesma formatacao e descarta runs vazios.
Dois documentos com o mesmo texto e a mesma formatacao so' sao iguais depois de
normalizados: o Qt e o XML podem dividir o mesmo texto em runs diferentes. Ela
tambem deixa a tabela na forma que o Word exige: toda celula termina em
paragrafo, e o corpo nao termina em tabela.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from typing import Literal, Union

from editdoc.modelo.pagina import Pagina
from editdoc.modelo.secoes import Secao

Alinhamento = Literal["esquerda", "centro", "direita", "justificado"]
Numeracao = Literal["marcadores", "numeracao"]
EstiloBorda = Literal["simples", "dupla", "pontilhada", "tracejada", "nenhuma"]

#: Caractere que ocupa o lugar da imagem no texto (o Qt usa o mesmo).
CARACTERE_OBJETO = chr(0xFFFC)


@dataclass
class Imagem:
    """Imagem na linha do texto. `dados` sao os bytes originais, intocados."""
    dados: bytes
    formato: str  # "png", "jpeg", "gif" ou "bmp" (modelo/imagem.py)
    largura_emu: int
    altura_emu: int
    descricao: str = ""  # texto alternativo (wp:docPr descr)
    # Recorte (0.1.5, a:srcRect): (esquerda, topo, direita, base) em milesimos de por cento
    # (100000 = 100%) cortados de cada lado. None = a imagem inteira.
    recorte: tuple | None = None


@dataclass(frozen=True)
class ParteOpaca:
    """Parte do pacote que um objeto opaco usa (grafico, imagem da forma, planilha...).

    `nome` e' o nome no pacote de origem: serve so' de chave entre as relacoes. O escritor
    escolhe um nome livre. `relacoes` sao as da propria parte: (Id, tipo, alvo, externo),
    com o alvo interno no nome de origem de outra parte do mesmo objeto. `refs_hospedeiro`:
    valores de atributo dentro da parte que apontam para relacoes da parte hospedeira (o
    relId do SmartArt, que o escritor reescreve com o rId novo).
    """
    nome: str
    tipo_conteudo: str
    dados: bytes
    relacoes: tuple = ()
    refs_hospedeiro: tuple = ()


@dataclass(frozen=True)
class ObjetoOpaco:
    """O que o EditDoc nao edita mas preserva: caixa de texto, forma, grafico, SmartArt,
    objeto OLE, imagem flutuante ou em formato que a tela nao mostra, equacao.

    `xml` e' o XML original (um w:r so' com o rPr e o objeto, ou o m:oMath/m:oMathPara),
    com as declaracoes de namespace. Volta ao arquivo igual, com os rIds renumerados.
    `relacoes`: as da parte hospedeira (documento, cabecalho, rodape) que o objeto usa,
    (rId de origem, tipo, alvo, externo). `partes`: o fecho das partes internas.
    `ignoraveis`: (prefixo, namespace) do mc:Ignorable da raiz de origem.
    """
    xml: bytes
    tipo: str  # ver ROTULOS_OPACOS
    resumo: str = ""  # inicio do texto da caixa (ou da equacao), para a tela
    flutuante: bool = False
    largura_emu: int | None = None
    altura_emu: int | None = None
    relacoes: tuple = ()
    partes: tuple = ()
    ignoraveis: tuple = ()
    previa: bytes | None = None  # imagem que a tela pode mostrar (PNG, JPEG, GIF, BMP)


#: Tipo do objeto opaco -> rotulo na tela.
ROTULOS_OPACOS = {
    "caixa_de_texto": "Caixa de texto",
    "forma": "Forma",
    "grupo": "Grupo de formas",
    "desenho": "Tela de desenho",
    "grafico": "Gráfico",
    "smartart": "SmartArt",
    "objeto": "Objeto",
    "tinta": "Tinta",
    "imagem": "Imagem",
    "equacao": "Equação",
}


@dataclass(frozen=True)
class Link:
    """Destino de um hiperlink (0.1.3): endereco externo (`url`) ou marcador (`ancora`).

    Os dois juntos sao um endereco com o trecho (#ancora) separado, como o Word grava.
    `historico` e' o w:history; `dica`, o w:tooltip; `quadro`, o w:tgtFrame; `local`, o
    w:docLocation. None = o arquivo nao diz.
    """
    url: str | None = None
    ancora: str | None = None
    dica: str | None = None
    historico: bool | None = None
    quadro: str | None = None
    local: str | None = None

    def interno(self) -> bool:
        return self.url is None

    def href(self) -> str:
        if self.url is None:
            return "#" + (self.ancora or "")
        return self.url + ("#" + self.ancora if self.ancora else "")


@dataclass(frozen=True)
class Campo:
    """Codigo de um campo qualquer (0.1.3): o que fica entre o begin e o separate.

    `codigo`: pedacos da instrucao, cada um texto (w:instrText) ou outro `Campo` (campo
    dentro da instrucao, como o PAGE de um IF). `sujo` e' o w:dirty; `travado`, o
    w:fldLock. `sem_resultado`: o arquivo nao tinha separate (XE, TC...). `resultado`: so'
    no campo de dentro da instrucao (o texto que ele mostrava). `extra`: o fldChar begin
    inteiro, quando ele traz filhos (w:ffData do campo de formulario), como veio.
    """
    codigo: tuple = ()
    sujo: bool = False
    travado: bool = False
    sem_resultado: bool = False
    resultado: str = ""
    extra: bytes = b""
    # 0.1.6: o w:rPr (forma canonica) dos runs do codigo (instrText) e do separate, quando
    # diferem do run do begin (o rStyle "Vinculo de indice" do sumario do Word). None = o do
    # begin. Fora da comparacao: e' aparencia do codigo, que o Word nao mostra.
    rpr_codigo: str | None = field(default=None, compare=False)
    rpr_separador: str | None = field(default=None, compare=False)

    def instrucao(self) -> str:
        """A instrucao em texto; o campo de dentro aparece entre chaves, como no Word."""
        partes = []
        for pedaco in self.codigo:
            if isinstance(pedaco, Campo):
                partes.append("{ " + pedaco.instrucao().strip() + " }")
            else:
                partes.append(str(pedaco))
        return "".join(partes)

    def tipo(self) -> str:
        """A primeira palavra da instrucao, em maiusculas ("TOC", "REF", "DATE"...)."""
        palavras = self.instrucao().split()
        return palavras[0].upper() if palavras else ""


@dataclass(frozen=True)
class MarcaCampo:
    """Inicio ou fim de um campo no fluxo do texto. So' o inicio leva o `Campo`.

    `par` liga o inicio ao fim do mesmo campo (o leitor numera; 0 = sem numero). Fica fora
    da comparacao: o arquivo relido tem outra numeracao, e o campo e' o mesmo.
    """
    tipo: Literal["inicio", "fim"]
    campo: Campo | None = None
    par: int = field(default=0, compare=False)


@dataclass(frozen=True)
class Marcador:
    """Inicio ou fim de um marcador (w:bookmarkStart / w:bookmarkEnd), pelo nome."""
    tipo: Literal["inicio", "fim"]
    nome: str


@dataclass(frozen=True)
class MarcaConteudo:
    """Inicio ou fim de um controle de conteudo (w:sdt, 0.1.5) no fluxo do texto.

    `propriedades`: o w:sdtPr e o w:sdtEndPr do controle (so' no inicio), em forma canonica
    (`formato_docx/propriedades.py`). `bloco`: o controle envolve paragrafos inteiros (o do
    sumario); o inicio fica no comeco do primeiro paragrafo e o fim no fim do ultimo, e o
    escritor grava o w:sdt por fora deles. Sem `bloco`, o controle esta' dentro do paragrafo.
    `par` liga o inicio ao fim, como na marca de campo (fora da comparacao).
    """
    tipo: Literal["inicio", "fim"]
    propriedades: bytes = b""
    bloco: bool = False
    par: int = field(default=0, compare=False)


@dataclass(frozen=True)
class MarcaComentario:
    """Ancora de um comentario no fluxo do texto (0.1.6): o inicio e o fim do trecho comentado
    (w:commentRangeStart e w:commentRangeEnd) e a referencia (o run com w:commentReference).
    `id` e' o w:id, a chave no catalogo (`Documento.comentarios`, modelo/comentarios.py)."""
    tipo: Literal["inicio", "fim", "referencia"]
    id: int


@dataclass(frozen=True)
class MarcaNota:
    """Nota de rodape ou de fim no fluxo do texto (0.1.10).

    No corpo e' a referencia (o run com w:footnoteReference ou w:endnoteReference): `id` e' o
    w:id, a chave no catalogo (`Documento.notas`, modelo/notas.py). Dentro do conteudo da nota,
    `propria` marca o w:footnoteRef/w:endnoteRef (o numero da propria nota, que o Word mostra
    no comeco dela; `id` fica 0). `personalizada` e' o w:customMarkFollows: a nota nao entra
    na numeracao e o simbolo e' o run seguinte do arquivo, guardado inteiro em `simbolo` (os
    filhos do w:r em forma canonica, `formato_docx/propriedades.py`), que volta igual.
    """
    tipo: Literal["rodape", "fim"]
    id: int = 0
    propria: bool = False
    personalizada: bool = False
    simbolo: str | None = None


@dataclass(frozen=True)
class MarcaQuebra:
    """Quebra de coluna no fluxo do texto (0.1.12, w:br w:type="column"). A tela mostra uma
    coluna so': a quebra fica no lugar (marca sem largura) e volta ao arquivo."""
    tipo: Literal["coluna"] = "coluna"


@dataclass
class Run:
    texto: str = ""
    negrito: bool | None = None
    italico: bool | None = None
    sublinhado: bool | None = None
    tachado: bool | None = None
    subscrito: bool | None = None
    sobrescrito: bool | None = None
    tamanho_meio_pt: int | None = None  # 24 = 12 pt
    fonte: str | None = None
    cor_hex: str | None = None  # "RRGGBB", sem '#', em maiusculas
    # Run de imagem: texto == CARACTERE_OBJETO e a formatacao de texto nao se aplica.
    imagem: Imagem | None = None
    # Campo (M5): instrucao normalizada ("PAGE", "NUMPAGES \* roman"...). O texto e' o
    # ultimo resultado guardado. Campo nunca funde com o vizinho.
    campo: str | None = None
    # Estilo de caractere (M6, w:rStyle): o id no catalogo. None = sem estilo de caractere.
    # Os campos acima sao a formatacao DIRETA: o que o texto tem alem do estilo.
    estilo: str | None = None
    # Objeto opaco (0.1.2): texto == CARACTERE_OBJETO; o XML original volta ao arquivo.
    objeto: ObjetoOpaco | None = None
    # Hiperlink (0.1.3): o destino do trecho. None = fora de link.
    link: Link | None = None
    # Marca sem texto (0.1.3): inicio/fim de campo ou de marcador; desde a 0.1.5 tambem de
    # controle de conteudo (MarcaConteudo). texto == "".
    marca: MarcaCampo | Marcador | MarcaConteudo | MarcaComentario | MarcaNota | MarcaQuebra | None = None
    # Propriedades de run que o modelo nao representa (0.1.5): o XML original delas (um w:rPr
    # em forma canonica, `formato_docx/propriedades.py`). None = nenhuma.
    extras: str | None = None

    def eh_objeto(self) -> bool:
        """Run que ocupa o caractere de objeto: imagem ou objeto opaco."""
        return self.imagem is not None or self.objeto is not None

    def eh_marca(self) -> bool:
        return self.marca is not None


def run_de_imagem(imagem: Imagem) -> Run:
    return Run(texto=CARACTERE_OBJETO, imagem=imagem)


def run_de_objeto(objeto: ObjetoOpaco) -> Run:
    return Run(texto=CARACTERE_OBJETO, objeto=objeto)


@dataclass
class Paragrafo:
    runs: list[Run] = field(default_factory=list)
    alinhamento: Alinhamento | None = None
    recuo_esquerdo_tw: int | None = None
    # Positivo = recuo da primeira linha; negativo = deslocamento suspenso.
    recuo_primeira_linha_tw: int | None = None
    espaco_antes_tw: int | None = None
    espaco_depois_tw: int | None = None
    # Tipo da lista ("marcadores" ou "numeracao"), so' informativo desde a 0.1.4: o leitor e a
    # ponte preenchem pela lista efetiva, e fica fora da comparacao. Documento montado em
    # codigo pode dar so' o tipo (sem `lista`): `numeracao.materializar` cria a definicao.
    numeracao: Numeracao | None = field(default=None, compare=False)
    # Porcentagem (100 = simples). Ausente no plano original; entrou no M2 porque
    # o editor ja aplica o espacamento e salvar sem ele perderia a formatacao.
    espacamento_linha_pct: int | None = None
    # Quebra de pagina antes deste paragrafo (Ctrl+Enter). No .docx ela e' um
    # w:br type="page" no inicio do paragrafo. Ausente = sem quebra.
    quebra_antes: bool = False
    # M6: estilo de paragrafo (w:pStyle, o id no catalogo). None = o estilo padrao (Normal).
    # Os campos de formatacao sao a formatacao DIRETA, o que difere do estilo.
    estilo: str | None = None
    recuo_direito_tw: int | None = None
    # Nivel de estrutura direto (w:outlineLvl): 0 = como Titulo 1; 9 = corpo de texto.
    nivel: int | None = None
    # Lista (0.1.4): w:numPr direto. `lista` e' o numId (0 = sem lista, mesmo que o estilo
    # tenha); `lista_nivel` e' o ilvl (0 a 8). None = herda do estilo (modelo/numeracao.py).
    lista: int | None = None
    lista_nivel: int | None = None
    # Propriedades de paragrafo que o modelo nao representa (0.1.5): tabulacoes, bordas,
    # sombreamento, quadro, controle de linhas... (um w:pPr em forma canonica). None = nenhuma.
    extras: str | None = None
    # Secao que termina neste paragrafo (0.1.12, o w:sectPr do w:pPr; modelo/secoes.py). So'
    # no corpo, fora de tabela. None = o paragrafo nao termina secao.
    secao: Secao | None = None


@dataclass
class Borda:
    estilo: EstiloBorda = "simples"
    oitavos_pt: int = 4  # 4 = 0,5 pt, a borda padrao do Word
    cor_hex: str | None = None  # None = automatica (preta)


@dataclass
class BordasTabela:
    """Bordas da tabela inteira: as quatro de fora e as de dentro (entre celulas)."""
    sup: Borda | None = None
    inf: Borda | None = None
    esq: Borda | None = None
    dir: Borda | None = None
    horizontal: Borda | None = None  # w:insideH
    vertical: Borda | None = None  # w:insideV


@dataclass
class BordasCelula:
    """Borda propria de uma celula, que vence a da tabela naquele lado."""
    sup: Borda | None = None
    inf: Borda | None = None
    esq: Borda | None = None
    dir: Borda | None = None


@dataclass
class Celula:
    blocos: list["Bloco"] = field(default_factory=list)
    colunas: int = 1  # w:gridSpan: quantas colunas da grade a celula ocupa
    # Mescla vertical (w:vMerge): "inicio" abre, "continua" e' coberta pela de cima.
    mescla_vertical: Literal["inicio", "continua"] | None = None
    bordas: BordasCelula | None = None
    sombreamento_hex: str | None = None  # cor de fundo, "RRGGBB"
    alinhamento_vertical: Literal["topo", "centro", "base"] | None = None
    # Propriedades da celula que o modelo nao representa (0.1.5): tcMar, textDirection,
    # noWrap... (um w:tcPr em forma canonica). None = nenhuma.
    extras: str | None = None
    # Fundo que a formatacao condicional do estilo da tabela da' a celula (0.1.6: cabecalho,
    # faixas alternadas...), "RRGGBB". So' para a tela e o PDF: o arquivo leva o estilo e o
    # tblLook, e o Word calcula de novo. Fora da comparacao.
    fundo_estilo: str | None = field(default=None, compare=False)


@dataclass
class Linha:
    celulas: list[Celula] = field(default_factory=list)
    cabecalho: bool = False  # w:tblHeader: repete no alto de cada pagina
    altura_tw: int | None = None  # w:trHeight (guardada; a tela nao aplica)
    altura_exata: bool = False  # hRule="exact"; senao, "atLeast"
    # Propriedades da linha que o modelo nao representa (0.1.5): cantSplit, jc, hidden...
    extras: str | None = None


@dataclass
class Tabela:
    linhas: list[Linha] = field(default_factory=list)
    colunas_tw: list[int] = field(default_factory=list)  # w:tblGrid
    bordas: BordasTabela | None = None
    alinhamento: Literal["esquerda", "centro", "direita"] | None = None
    recuo_tw: int | None = None  # w:tblInd
    # w:tblW como o arquivo diz: ("dxa", twips), ("pct", 50 avos de %) ou ("auto", 0).
    largura: tuple[str, int] | None = None
    layout_fixo: bool | None = None  # w:tblLayout type="fixed"
    # Margens internas padrao das celulas (w:tblCellMar), em twips: sup, esq, inf, dir.
    margens_celula_tw: tuple[int, int, int, int] | None = None
    # Propriedades da tabela que o modelo nao representa (0.1.5): tblpPr (tabela flutuante),
    # sombreamento, espacamento entre celulas, legenda... (um w:tblPr em forma canonica). Desde
    # a 0.1.6 o w:tblLook (que partes da formatacao condicional valem) tambem.
    extras: str | None = None
    # Estilo da tabela (0.1.6, w:tblStyle): o id do arquivo de origem, que volta como veio (a
    # formatacao condicional do estilo continua valendo no Word). None = "Table Grid", o da
    # tabela criada no EditDoc.
    estilo: str | None = None


Bloco = Union[Paragrafo, Tabela]


@dataclass
class Documento:
    # Blocos do corpo: Paragrafo ou Tabela (ver a nota no topo do modulo).
    paragrafos: list[Bloco] = field(default_factory=list)
    pagina: Pagina = field(default_factory=Pagina)
    titulo: str = ""
    autor: str = ""
    criado_em: str | None = None  # ISO 8601 UTC, ex. "2026-10-11T12:00:00Z"
    modificado_em: str | None = None
    # Cabecalho e rodape (M5): tipo ("padrao", "primeira", "par") -> blocos.
    cabecalhos: dict[str, list[Bloco]] = field(default_factory=dict)
    rodapes: dict[str, list[Bloco]] = field(default_factory=dict)
    # Estilos (M6): o catalogo do documento (modelo/estilos.py). None = o conjunto padrao.
    # Fica fora da comparacao: dois documentos iguais no texto e na formatacao sao iguais,
    # mesmo que um venha com o styles.xml do Word e o outro com o do EditDoc.
    estilos: object = field(default=None, compare=False, repr=False)
    # Partes do pacote de origem que voltam ao arquivo (0.1.3): PacoteOriginal ou None.
    pacote: object = field(default=None, compare=False, repr=False)
    # Numeracao de listas (0.1.4): o catalogo do numbering.xml (modelo/numeracao.py) ou None.
    # Fora da comparacao, como os estilos: o paragrafo compara o numId e o nivel.
    numeracao: object = field(default=None, compare=False, repr=False)
    # Comentarios (0.1.6): o catalogo (modelo/comentarios.py) ou None. Fora da comparacao: as
    # ancoras estao no fluxo (MarcaComentario) e a conferencia compara o conteudo a parte.
    comentarios: object = field(default=None, compare=False, repr=False)
    # Notas de rodape e de fim (0.1.10): o catalogo (modelo/notas.py) ou None. Fora da
    # comparacao, como os comentarios: as referencias estao no fluxo (MarcaNota) e a
    # conferencia compara o conteudo das notas a parte.
    notas: object = field(default=None, compare=False, repr=False)
    # A ultima secao (0.1.12): tipo, extras e XML de origem do w:sectPr do fim do corpo. O papel,
    # os cabecalhos e os rodapes dela sao `pagina`, `cabecalhos` e `rodapes` (modelo/secoes.py).
    secao: Secao = field(default_factory=Secao)


@dataclass(frozen=True)
class PacoteOriginal:
    """O que o pacote de origem tem fora do texto e volta ao arquivo (0.1.3).

    `configuracoes`: o settings.xml original (o EditDoc so' muda o que controla), com as
    relacoes dele (`relacoes_configuracoes`: Id, tipo, alvo, externo). `propriedades` e
    `aplicativo`: core.xml e app.xml originais (titulo, autor e datas sao reescritos).
    `do_documento` e `do_pacote`: (tipo, alvo) das relacoes do document.xml e do
    _rels/.rels para partes preservadas (fontTable, webSettings, customXml, custom.xml,
    notas separadoras...). `partes`: o fecho dessas partes (ParteOpaca), byte a byte.
    """
    configuracoes: bytes | None = None
    relacoes_configuracoes: tuple = ()
    propriedades: bytes | None = None
    aplicativo: bytes | None = None
    do_documento: tuple = ()
    do_pacote: tuple = ()
    partes: tuple = ()


#: Tipos de cabecalho e rodape, na ordem do .docx (default, first, even).
TIPOS_DE_FAIXA = ("padrao", "primeira", "par")


def _formato_de(run: Run) -> tuple:
    """Tudo o que define a aparencia do run, menos o texto."""
    return tuple(getattr(run, f.name) for f in fields(Run) if f.name != "texto")


def _normalizar_paragrafo(paragrafo: Paragrafo) -> None:
    fundidos: list[Run] = []
    for run in paragrafo.runs:
        if run.eh_objeto() or run.campo is not None or run.marca is not None:
            # Imagem, objeto, campo e marca nunca fundem: duas imagens iguais lado a lado sao
            # duas imagens, e o campo PAGE seguido de outro PAGE sao dois campos.
            fundidos.append(run)
            continue
        if run.texto == "":
            continue
        anterior = fundidos[-1] if fundidos else None
        if anterior is not None and not anterior.eh_objeto() and anterior.campo is None and \
                anterior.marca is None and _formato_de(anterior) == _formato_de(run):
            anterior.texto += run.texto
        else:
            fundidos.append(run)
    paragrafo.runs = fundidos


def bordas_padrao() -> BordasTabela:
    """As bordas do "Table Grid" do Word: linha simples de 0,5 pt em volta e por dentro.

    E' o que vale quando `Tabela.bordas` e' None (tabela criada no EditDoc).
    """
    return BordasTabela(sup=Borda(), inf=Borda(), esq=Borda(), dir=Borda(),
                        horizontal=Borda(), vertical=Borda())


def _normalizar_blocos(blocos: list[Bloco], em_celula: bool) -> None:
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            # Formas equivalentes no arquivo: o escritor grava sempre os seis lados da
            # borda e a largura (tblW), e so' grava o layout quando ele e' fixo.
            if bloco.bordas is None:
                bloco.bordas = bordas_padrao()
            if bloco.largura is None:
                bloco.largura = ("auto", 0)
            if not bloco.layout_fixo:
                bloco.layout_fixo = None
            for linha in bloco.linhas:
                for celula in linha.celulas:
                    _normalizar_blocos(celula.blocos, em_celula=True)
        else:
            _normalizar_paragrafo(bloco)
    # A forma que o Word exige: celula termina em paragrafo; o corpo tambem.
    if em_celula and (not blocos or isinstance(blocos[-1], Tabela)):
        blocos.append(Paragrafo())
    elif not em_celula and blocos and isinstance(blocos[-1], Tabela):
        blocos.append(Paragrafo())


def normalizar(documento: Documento) -> Documento:
    """Copia do documento com runs vizinhos fundidos, runs vazios descartados e as
    tabelas na forma canonica (celula e corpo terminam em paragrafo)."""
    saida = copy.deepcopy(documento)
    # Lista dada so' pelo tipo (documento montado em codigo): os mesmos numIds do escritor.
    from editdoc.modelo.numeracao import materializar
    materializar(saida)
    _normalizar_blocos(saida.paragrafos, em_celula=False)
    # Cabecalho e rodape terminam em paragrafo, como a celula (o Word exige ao menos um).
    for faixas in (saida.cabecalhos, saida.rodapes):
        for blocos in faixas.values():
            _normalizar_blocos(blocos, em_celula=True)
    for _onde, _tipo, blocos in faixas_das_secoes(saida):
        _normalizar_blocos(blocos, em_celula=True)
    return saida


def faixas_das_secoes(doc: "Documento"):
    """(onde, tipo, blocos) dos cabecalhos e rodapes das secoes que terminam em paragrafo
    (0.1.12). Os da ultima secao sao `doc.cabecalhos` e `doc.rodapes`."""
    from editdoc.modelo import secoes
    yield from secoes.faixas_das_secoes(doc)


def historias_de_faixa(doc: "Documento") -> list:
    """Os blocos de cada cabecalho e rodape: os da ultima secao (padrao, primeira, par) e,
    desde a 0.1.12, os das outras secoes, na ordem do corpo."""
    saida = []
    for faixas in (doc.cabecalhos, doc.rodapes):
        saida.extend(faixas[t] for t in TIPOS_DE_FAIXA if t in faixas)
    saida.extend(blocos for _onde, _tipo, blocos in faixas_das_secoes(doc))
    return saida


def paragrafos_de(blocos: list[Bloco]):
    """Todos os paragrafos, na ordem de leitura, inclusive os de dentro de tabela."""
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            for linha in bloco.linhas:
                for celula in linha.celulas:
                    yield from paragrafos_de(celula.blocos)
        else:
            yield bloco


def objetos_de(doc: Documento):
    """Todos os objetos opacos do documento, na ordem em que o escritor os grava:
    corpo, depois cabecalhos e rodapes (padrao, primeira, par)."""
    listas = [doc.paragrafos] + historias_de_faixa(doc)
    for blocos in listas:
        for p in paragrafos_de(blocos):
            for r in p.runs:
                if r.objeto is not None:
                    yield r.objeto


def tabelas_de(blocos: list[Bloco]):
    """Todas as tabelas, inclusive as aninhadas, na ordem de leitura."""
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            yield bloco
            for linha in bloco.linhas:
                for celula in linha.celulas:
                    yield from tabelas_de(celula.blocos)


def colunas_da_linha(linha: Linha) -> int:
    return sum(max(1, c.colunas) for c in linha.celulas)
