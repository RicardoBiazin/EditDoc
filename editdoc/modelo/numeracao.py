"""Numeracao de listas (0.1.4): o catalogo do numbering.xml e o calculo dos numeros. Sem Qt e sem lxml.

O .docx separa a lista em tres camadas, e o modelo segue a mesma divisao:

- `Abstrata` (w:abstractNum): os 9 niveis (`Nivel`, w:lvl) com formato, texto ("%1.%2."),
  inicio, recuos, fonte do simbolo, sufixo, reinicio e o estilo ligado ao nivel.
- `Instancia` (w:num): o numId que o paragrafo cita; aponta para uma abstrata e pode
  sobrescrever o inicio (w:startOverride) ou o nivel inteiro (w:lvlOverride/w:lvl).
- `ImagemMarcador` (w:numPicBullet): a imagem do marcador de figura.

O paragrafo guarda so' a referencia (`Paragrafo.lista` = numId e `Paragrafo.lista_nivel` =
ilvl, os dois diretos; None = herda do estilo). O estilo de paragrafo pode ligar a lista
(numPr dentro do estilo, `Estilo.lista`); o nivel sem ilvl sai do nivel cujo w:pStyle e' o
estilo do paragrafo (Titulo 2 -> nivel 2 da lista de titulos).

Calculo (`Contador`), como o Word faz:
- os contadores sao da ABSTRATA: duas instancias da mesma abstrata, sem sobrescrita,
  continuam a contagem uma da outra, mesmo com paragrafos comuns no meio;
- a instancia com w:startOverride (ou w:lvlOverride com w:lvl) reinicia o nivel na primeira
  vez que aparece, e o nivel passa a comecar no valor dela;
- um item no nivel L reinicia os niveis abaixo dele; `w:lvlRestart` (base 1) muda isso:
  0 = nunca reinicia, r = so' reinicia quando aparece um nivel acima de r;
- nivel pulado (Titulo 3 logo depois do Titulo 1) mostra o inicio menos 1: "1.0.1";
- `w:isLgl` mostra todos os niveis do texto em decimal ("1.1" num nivel com romano acima).

O catalogo lido do arquivo guarda o numbering.xml original (`xml_original`): o que o usuario
nao mexeu volta igual. O EditDoc nunca altera uma definicao que veio do arquivo: reiniciar,
continuar, definir o valor e trocar o formato criam instancias ou abstratas novas
(`adicoes`), que vao para o fim do numbering.xml.
"""

from __future__ import annotations

import json
import zlib
from dataclasses import asdict, dataclass, field, fields, replace

from editdoc.modelo.campos import formatar_numero

#: Niveis de uma lista no .docx (ilvl 0 a 8).
NIVEIS = 9

#: Limites contra arquivo hostil. Acima disto o numbering.xml nao e' lido (aviso LISTA).
LIMITES = {
    "listas_abstratas": 2000,
    "listas_instancias": 10000,
    "listas_imagens": 512,
    "lista_texto": 256,       # caracteres do w:lvlText
    "lista_niveis": 32,       # w:lvl dentro de uma abstrata (o esquema pede 9)
    "lista_sobrescritas": 32,  # w:lvlOverride dentro de uma instancia
}

#: Formatos que o EditDoc calcula. Os outros (japones, chines, hebraico...) voltam ao arquivo
#: como vieram e aparecem na tela em decimal.
FORMATOS_CALCULADOS = (
    "decimal", "decimalZero", "lowerLetter", "upperLetter", "lowerRoman", "upperRoman",
    "bullet", "none", "ordinal", "cardinalText", "ordinalText", "decimalEnclosedCircle",
    "decimalEnclosedParen", "decimalEnclosedFullstop", "decimalFullWidth", "decimalFullWidth2",
    "hex", "chicago",
)

#: Sufixo do numero (w:suff).
SUFIXOS = ("tab", "space", "nothing")

#: Campos de caractere do simbolo (rPr do nivel) que a tela usa.
CAMPOS_SIMBOLO = ("fonte", "tamanho_meio_pt", "negrito", "italico", "sublinhado", "cor_hex")


# -- definicoes -----------------------------------------------------------------------

@dataclass(frozen=True)
class Nivel:
    """Um w:lvl. `recuo_primeira_linha_tw` negativo = deslocamento (w:hanging)."""
    ilvl: int
    inicio: int = 0  # w:start; ausente = 0, como o esquema
    formato: str = "decimal"  # w:numFmt
    texto: str | None = None  # w:lvlText; None = sem texto (nada aparece)
    alinhamento: str = "left"  # w:lvlJc: left, center, right
    sufixo: str = "tab"  # w:suff
    legal: bool = False  # w:isLgl
    reinicio: int | None = None  # w:lvlRestart
    estilo: str | None = None  # w:pStyle
    imagem: int | None = None  # w:lvlPicBulletId
    recuo_esquerdo_tw: int | None = None
    recuo_primeira_linha_tw: int | None = None
    tabulacoes: tuple = ()  # posicoes (twips) das tabulacoes do pPr do nivel
    caractere: tuple = ()  # (campo, valor) do rPr do nivel, campos de CAMPOS_SIMBOLO
    oculto: bool = False  # w:vanish no rPr: o numero nao aparece

    def simbolo(self) -> dict:
        return dict(self.caractere)

    def eh_marcador(self) -> bool:
        return self.formato == "bullet" or self.imagem is not None


@dataclass(frozen=True)
class Sobrescrita:
    """w:lvlOverride: o inicio novo (w:startOverride) e/ou o nivel inteiro (w:lvl)."""
    ilvl: int
    inicio: int | None = None
    nivel: Nivel | None = None


@dataclass(frozen=True)
class Abstrata:
    id: int
    niveis: tuple = ()  # Nivel, um por ilvl presente
    tipo: str | None = None  # w:multiLevelType
    nsid: str | None = None
    modelo: str | None = None  # w:tmpl
    nome: str | None = None  # w:name
    estilo_link: str | None = None  # w:styleLink (esta abstrata define o estilo de numeracao)
    num_estilo_link: str | None = None  # w:numStyleLink (os niveis estao em outra abstrata)

    def nivel(self, ilvl: int) -> Nivel | None:
        for n in self.niveis:
            if n.ilvl == ilvl:
                return n
        return None


@dataclass(frozen=True)
class Instancia:
    id: int
    abstrata: int
    sobrescritas: tuple = ()  # Sobrescrita

    def sobrescrita(self, ilvl: int) -> Sobrescrita | None:
        for s in self.sobrescritas:
            if s.ilvl == ilvl:
                return s
        return None


@dataclass(frozen=True)
class ImagemMarcador:
    """w:numPicBullet. `dados` e' a imagem para a tela (PNG, JPEG, GIF ou BMP), se houver."""
    id: int
    dados: bytes | None = None
    formato: str | None = None


@dataclass
class Numeracao:
    """O catalogo do numbering.xml. `xml_original` volta igual se nada for acrescentado.

    `relacoes` e `partes`: as relacoes do numbering.xml (as imagens dos marcadores de
    figura) e o fecho dessas partes, como nos objetos opacos. `ids_originais`: o que veio
    do arquivo; o resto e' acrescimo do EditDoc. `tab_padrao_tw` e' o w:defaultTabStop do
    settings.xml (a tabulacao depois do numero cai nele quando nao ha outra).
    """
    abstratas: dict = field(default_factory=dict)
    instancias: dict = field(default_factory=dict)
    imagens: dict = field(default_factory=dict)
    xml_original: bytes | None = None
    relacoes: tuple = ()
    partes: tuple = ()
    ids_originais: tuple = (frozenset(), frozenset())  # (abstratas, instancias)
    tab_padrao_tw: int = 708

    # -- consulta -----------------------------------------------------------------
    def copia(self) -> "Numeracao":
        return Numeracao(
            abstratas=dict(self.abstratas), instancias=dict(self.instancias),
            imagens=dict(self.imagens), xml_original=self.xml_original,
            relacoes=self.relacoes, partes=self.partes, ids_originais=self.ids_originais,
            tab_padrao_tw=self.tab_padrao_tw)

    def abstrata_de(self, num: int | None, estilos=None) -> Abstrata | None:
        """A abstrata que vale para o numId, seguindo o w:numStyleLink (estilo de numeracao)."""
        inst = self.instancias.get(num) if num is not None else None
        if inst is None:
            return None
        abstrata = self.abstratas.get(inst.abstrata)
        for _ in range(4):  # numStyleLink -> estilo -> numId -> abstrata com styleLink
            if abstrata is None or not abstrata.num_estilo_link or estilos is None:
                break
            estilo = estilos.obter(abstrata.num_estilo_link)
            alvo = getattr(estilo, "lista", None) if estilo is not None else None
            outra = self.instancias.get(alvo) if alvo is not None else None
            seguinte = self.abstratas.get(outra.abstrata) if outra is not None else None
            if seguinte is None or seguinte is abstrata:
                break
            abstrata = seguinte
        return abstrata

    def nivel_de(self, num: int | None, ilvl: int, estilos=None) -> Nivel | None:
        """O nivel efetivo: o w:lvl do lvlOverride, ou o da abstrata com o startOverride."""
        inst = self.instancias.get(num) if num is not None else None
        if inst is None:
            return None
        sob = inst.sobrescrita(ilvl)
        if sob is not None and sob.nivel is not None:
            nivel = sob.nivel
        else:
            abstrata = self.abstrata_de(num, estilos)
            nivel = abstrata.nivel(ilvl) if abstrata is not None else None
        if nivel is not None and sob is not None and sob.inicio is not None:
            nivel = replace(nivel, inicio=sob.inicio)
        return nivel

    def tipo_de(self, num: int | None, ilvl: int = 0, estilos=None) -> str | None:
        """"marcadores" ou "numeracao" (o tipo do botao da faixa); None se nao e' lista."""
        nivel = self.nivel_de(num, ilvl, estilos)
        if nivel is None:
            return None
        return "marcadores" if nivel.eh_marcador() else "numeracao"

    # -- acrescimos do EditDoc --------------------------------------------------------
    def adicoes(self) -> tuple[list, list]:
        """(abstratas, instancias) que nao vieram do arquivo, em ordem de id."""
        ab_orig, in_orig = self.ids_originais
        return ([self.abstratas[k] for k in sorted(self.abstratas) if k not in ab_orig],
                [self.instancias[k] for k in sorted(self.instancias) if k not in in_orig])

    def alterada(self) -> bool:
        a, i = self.adicoes()
        return bool(a or i)

    def _id_livre(self, ids) -> int:
        return (max(ids) + 1) if ids else 0

    def adicionar_abstrata(self, niveis: tuple, tipo: str = "hybridMultilevel",
                           estilo_link: str | None = None) -> Abstrata:
        """Abstrata nova (ou a acrescida antes com os mesmos niveis: nao duplica)."""
        for a in self.adicoes()[0]:
            if a.niveis == tuple(niveis) and a.tipo == tipo and a.estilo_link == estilo_link:
                return a
        ident = self._id_livre(self.abstratas)
        nsid = f"{zlib.crc32(repr((ident, niveis)).encode()) & 0x7FFFFFFF:08X}"
        nova = Abstrata(id=ident, niveis=tuple(niveis), tipo=tipo, nsid=nsid,
                        estilo_link=estilo_link)
        self.abstratas[ident] = nova
        return nova

    def adicionar_instancia(self, abstrata: int, sobrescritas: tuple = ()) -> Instancia:
        ident = max(1, self._id_livre(self.instancias))
        nova = Instancia(id=ident, abstrata=abstrata, sobrescritas=tuple(sobrescritas))
        self.instancias[ident] = nova
        return nova

    def instancia_simples(self, abstrata: int) -> Instancia:
        """Uma instancia sem sobrescrita da abstrata (a ja' existente, se houver)."""
        for k in sorted(self.instancias):
            inst = self.instancias[k]
            if inst.abstrata == abstrata and not inst.sobrescritas:
                return inst
        return self.adicionar_instancia(abstrata)

    # -- desfazer da tela: so' os acrescimos vao para o JSON --------------------------
    def adicoes_json(self) -> str:
        abstratas, instancias = self.adicoes()
        return json.dumps({"abstratas": [_abstrata_para_dict(a) for a in abstratas],
                           "instancias": [_instancia_para_dict(i) for i in instancias]},
                          ensure_ascii=False, sort_keys=True)

    def com_adicoes(self, texto: str) -> "Numeracao":
        """Este catalogo (o do arquivo) mais os acrescimos do JSON."""
        saida = self.copia()
        ab_orig, in_orig = self.ids_originais
        saida.abstratas = {k: v for k, v in self.abstratas.items() if k in ab_orig}
        saida.instancias = {k: v for k, v in self.instancias.items() if k in in_orig}
        try:
            dado = json.loads(texto)
        except (TypeError, ValueError):
            return saida
        for d in dado.get("abstratas", []):
            a = _abstrata_de_dict(d)
            if a is not None and a.id not in saida.abstratas:
                saida.abstratas[a.id] = a
        for d in dado.get("instancias", []):
            i = _instancia_de_dict(d)
            if i is not None and i.id not in saida.instancias:
                saida.instancias[i.id] = i
        return saida


def _nivel_para_dict(n: Nivel) -> dict:
    d = asdict(n)
    d["tabulacoes"] = list(n.tabulacoes)
    d["caractere"] = [list(par) for par in n.caractere]
    return d


def _nivel_de_dict(d: dict) -> Nivel | None:
    validos = {f.name for f in fields(Nivel)}
    try:
        d = {k: v for k, v in d.items() if k in validos}
        d["tabulacoes"] = tuple(int(x) for x in d.get("tabulacoes") or ())
        d["caractere"] = tuple((str(a), b) for a, b in d.get("caractere") or ())
        return Nivel(**d)
    except (TypeError, ValueError):
        return None


def _abstrata_para_dict(a: Abstrata) -> dict:
    d = {f.name: getattr(a, f.name) for f in fields(Abstrata) if f.name != "niveis"}
    d["niveis"] = [_nivel_para_dict(n) for n in a.niveis]
    return d


def _abstrata_de_dict(d: dict) -> Abstrata | None:
    try:
        niveis = tuple(n for n in (_nivel_de_dict(x) for x in d.get("niveis", [])) if n is not None)
        validos = {f.name for f in fields(Abstrata)} - {"niveis"}
        return Abstrata(niveis=niveis, **{k: v for k, v in d.items() if k in validos})
    except (TypeError, ValueError, AttributeError):
        return None


def _instancia_para_dict(i: Instancia) -> dict:
    return {"id": i.id, "abstrata": i.abstrata,
            "sobrescritas": [{"ilvl": s.ilvl, "inicio": s.inicio,
                              "nivel": None if s.nivel is None else _nivel_para_dict(s.nivel)}
                             for s in i.sobrescritas]}


def _instancia_de_dict(d: dict) -> Instancia | None:
    try:
        sobrescritas = tuple(Sobrescrita(ilvl=int(s["ilvl"]), inicio=s.get("inicio"),
                                         nivel=None if s.get("nivel") is None
                                         else _nivel_de_dict(s["nivel"]))
                             for s in d.get("sobrescritas", []))
        return Instancia(id=int(d["id"]), abstrata=int(d["abstrata"]), sobrescritas=sobrescritas)
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


def definicoes_para_json(cat: Numeracao, nums) -> dict:
    """As definicoes que os numIds usam (copiar e colar entre documentos)."""
    saida: dict = {"instancias": {}, "abstratas": {}}
    for num in nums:
        inst = cat.instancias.get(num)
        if inst is None:
            continue
        saida["instancias"][str(num)] = _instancia_para_dict(inst)
        abstrata = cat.abstratas.get(inst.abstrata)
        if abstrata is not None:
            saida["abstratas"][str(abstrata.id)] = _abstrata_para_dict(abstrata)
    return saida


def importar_definicoes(cat: Numeracao, dado: dict) -> dict[int, int]:
    """Acrescenta ao catalogo as definicoes de outro documento. Devolve numId de la' -> daqui.

    A abstrata igual a uma que ja' existe aqui e' reaproveitada; o marcador de figura de
    outro documento vira o marcador redondo (a imagem e' do outro pacote).
    """
    mapa: dict[int, int] = {}
    abstratas = dado.get("abstratas") or {}
    for chave, d in (dado.get("instancias") or {}).items():
        inst = _instancia_de_dict(d)
        if inst is None:
            continue
        origem = _abstrata_de_dict(abstratas.get(str(inst.abstrata)) or {})
        if origem is None:
            continue
        niveis = tuple(replace(n, imagem=None, texto=n.texto or "",
                               caractere=(("fonte", "Symbol"),)) if n.imagem is not None else n
                       for n in origem.niveis)
        abstrata = next((a for a in cat.abstratas.values()
                         if a.niveis == niveis and a.tipo == origem.tipo
                         and not a.num_estilo_link and not a.estilo_link), None)
        if abstrata is None:
            abstrata = cat.adicionar_abstrata(niveis, origem.tipo or "hybridMultilevel")
        nova = cat.adicionar_instancia(abstrata.id, inst.sobrescritas)
        try:
            mapa[int(chave)] = nova.id
        except ValueError:
            continue
    return mapa


#: Simbolos de fonte de simbolo (Symbol, Wingdings) no codigo privado F0xx, e o caractere
#: Unicode que se parece com eles: para a tela sem a fonte e para o texto exportado.
SIMBOLOS_UNICODE = {
    0xF0B7: "•", 0xF0A7: "▪", 0xF0A8: "◊", 0xF06C: "●", 0xF06E: "■", 0xF06F: "□",
    0xF071: "❑", 0xF075: "◆", 0xF076: "❖", 0xF0D8: "➢", 0xF0FC: "✓", 0xF0E8: "➔",
    0xF0F0: "⇨", 0xF0D7: "⮚", 0xF0A1: "○", 0xF09F: "•", 0xF02D: "-", 0xF0BE: "—",
}


def texto_visivel(texto: str) -> str:
    """O texto do numero com os simbolos privados trocados pelo Unicode parecido
    (a tela sem a fonte de simbolo e o texto exportado)."""
    return "".join(SIMBOLOS_UNICODE.get(ord(c), c) if 0xF000 <= ord(c) <= 0xF0FF else c
                   for c in texto)



# -- formatos de numero -------------------------------------------------------------

_UNIDADES = ("zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove",
             "dez", "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete",
             "dezoito", "dezenove")
_DEZENAS = ("", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta",
            "oitenta", "noventa")
_CENTENAS = ("", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos",
             "setecentos", "oitocentos", "novecentos")
_ORD_UNIDADES = ("", "primeiro", "segundo", "terceiro", "quarto", "quinto", "sexto", "sétimo",
                 "oitavo", "nono")
_ORD_DEZENAS = ("", "décimo", "vigésimo", "trigésimo", "quadragésimo", "quinquagésimo",
                "sexagésimo", "septuagésimo", "octogésimo", "nonagésimo")
_ORD_CENTENAS = ("", "centésimo", "ducentésimo", "trecentésimo", "quadringentésimo",
                 "quingentésimo", "sexcentésimo", "septingentésimo", "octingentésimo",
                 "noningentésimo")


def _ate_mil(n: int) -> str:
    if n < 20:
        return _UNIDADES[n]
    if n < 100:
        d, u = divmod(n, 10)
        return _DEZENAS[d] + (" e " + _UNIDADES[u] if u else "")
    if n == 100:
        return "cem"
    c, resto = divmod(n, 100)
    return _CENTENAS[c] + (" e " + _ate_mil(resto) if resto else "")


def por_extenso(n: int) -> str:
    """Cardinal em portugues, de 0 a 999.999 (acima disso, os algarismos)."""
    if n < 0 or n >= 1_000_000:
        return str(n)
    if n < 1000:
        return _ate_mil(n)
    milhar, resto = divmod(n, 1000)
    inicio = "mil" if milhar == 1 else _ate_mil(milhar) + " mil"
    if not resto:
        return inicio
    liga = " e " if resto < 100 or resto % 100 == 0 else " "
    return inicio + liga + _ate_mil(resto)


def ordinal_por_extenso(n: int) -> str:
    """Ordinal em portugues, de 1 a 1999 (acima disso, os algarismos com o indicador)."""
    if n <= 0 or n >= 2000:
        return f"{n}º"
    partes = []
    if n >= 1000:
        partes.append("milésimo")
        n -= 1000
    c, n = divmod(n, 100)
    d, u = divmod(n, 10)
    for valor, nomes in ((c, _ORD_CENTENAS), (d, _ORD_DEZENAS), (u, _ORD_UNIDADES)):
        if valor:
            partes.append(nomes[valor])
    return " ".join(partes)


def _inicial_maiuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


def formatar(n: int, formato: str) -> str:
    """O numero no formato do w:numFmt. Formato que o EditDoc nao calcula sai em decimal."""
    if formato in ("none", "bullet"):
        return ""
    if formato == "decimalZero":
        return f"0{n}" if 0 <= n < 10 else str(n)
    if formato in ("lowerRoman", "upperRoman", "lowerLetter", "upperLetter"):
        return formatar_numero(n, formato) if n > 0 else ""
    if formato == "ordinal":
        return f"{n}º"
    if formato == "cardinalText":
        return _inicial_maiuscula(por_extenso(n))
    if formato == "ordinalText":
        return _inicial_maiuscula(ordinal_por_extenso(n))
    if formato == "decimalEnclosedCircle" and 1 <= n <= 20:
        return chr(0x2460 + n - 1)
    if formato == "decimalEnclosedParen" and 1 <= n <= 20:
        return chr(0x2474 + n - 1)
    if formato == "decimalEnclosedFullstop" and 1 <= n <= 20:
        return chr(0x2488 + n - 1)
    if formato in ("decimalFullWidth", "decimalFullWidth2") and n >= 0:
        return "".join(chr(0xFF10 + int(c)) for c in str(n))
    if formato == "hex" and n >= 0:
        return format(n, "X")
    if formato == "chicago" and n > 0:
        return "*†‡§"[(n - 1) % 4] * ((n - 1) // 4 + 1)
    return str(n)


def montar_texto(nivel: Nivel, valores: list, niveis: list) -> str:
    """O texto do numero: o w:lvlText com cada %n trocado pelo valor do nivel n.

    `valores[j]` e' o contador do nivel j (None = nao usado desde o ultimo reinicio: mostra o
    inicio menos 1, como o Word). `niveis[j]` e' a definicao do nivel j (o formato dele).
    """
    if nivel.texto is None:
        return ""
    saida = []
    texto = nivel.texto
    i = 0
    while i < len(texto):
        c = texto[i]
        if c == "%" and i + 1 < len(texto) and "1" <= texto[i + 1] <= "9":
            j = int(texto[i + 1]) - 1
            definicao = niveis[j] if j < len(niveis) else None
            inicio = definicao.inicio if definicao is not None else 0
            valor = valores[j] if valores[j] is not None else inicio - 1
            formato = "decimal" if nivel.legal else (definicao.formato if definicao else "decimal")
            if formato == "bullet":
                formato = "decimal"
            saida.append(formatar(valor, formato))
            i += 2
            continue
        saida.append(c)
        i += 1
    return "".join(saida)


# -- resolucao e calculo --------------------------------------------------------------

@dataclass(frozen=True)
class Rotulo:
    """O numero (ou marcador) de um paragrafo: o texto e o nivel que diz a aparencia."""
    texto: str
    nivel: Nivel
    num: int
    ilvl: int
    valor: int = 0  # o contador do nivel do item (o "3" de "1.3.")


def lista_efetiva(lista: int | None, lista_nivel: int | None, sid: str | None, estilos,
                  numeracao: Numeracao | None) -> tuple[int, int] | None:
    """(numId, ilvl) que valem para o paragrafo: o direto, ou o do estilo (cadeia basedOn).

    numId 0 desliga a lista do estilo. Sem ilvl, vale o do estilo, depois o nivel ligado ao
    estilo do paragrafo (w:pStyle do nivel), depois 0.
    """
    if numeracao is None:
        return None
    num, nivel = lista, lista_nivel
    if estilos is not None and num is None:
        for e in estilos.cadeia(sid or estilos.id_padrao()):
            e_lista = getattr(e, "lista", None)
            if e_lista is None:
                continue
            num = e_lista
            if nivel is None:
                nivel = getattr(e, "lista_nivel", None)
            break
    if num is None or num == 0 or num not in numeracao.instancias:
        return None
    if nivel is None:
        abstrata = numeracao.abstrata_de(num, estilos)
        alvo = sid or (estilos.id_padrao() if estilos is not None else None)
        if abstrata is not None and alvo:
            nivel = next((n.ilvl for n in abstrata.niveis if n.estilo == alvo), None)
    nivel = 0 if nivel is None else min(max(int(nivel), 0), NIVEIS - 1)
    return num, nivel


def recuos_do_nivel(nivel: Nivel | None) -> dict:
    """Recuos que o nivel da' ao paragrafo (por cima do estilo, por baixo do direto)."""
    if nivel is None:
        return {}
    saida = {}
    if nivel.recuo_esquerdo_tw is not None:
        saida["recuo_esquerdo_tw"] = nivel.recuo_esquerdo_tw
    if nivel.recuo_primeira_linha_tw is not None:
        saida["recuo_primeira_linha_tw"] = nivel.recuo_primeira_linha_tw
    return saida


class Contador:
    """Conta os itens de lista na ordem do documento, como o Word."""

    def __init__(self, numeracao: Numeracao | None, estilos=None) -> None:
        self.numeracao = numeracao
        self.estilos = estilos
        #: id da abstrata -> contador de cada nivel (None = ainda nao usado)
        self._valores: dict[int, list] = {}
        self._vistas: set[int] = set()
        #: numId -> (abstrata, niveis efetivos): resolvido uma vez por instancia
        self._resolvidas: dict[int, tuple] = {}

    def _resolver(self, num: int) -> tuple:
        if num not in self._resolvidas:
            cat = self.numeracao
            self._resolvidas[num] = (cat.abstrata_de(num, self.estilos),
                                     [cat.nivel_de(num, k, self.estilos) for k in range(NIVEIS)])
        return self._resolvidas[num]

    def proximo(self, num: int, ilvl: int) -> Rotulo | None:
        cat = self.numeracao
        if cat is None or num not in cat.instancias:
            return None
        abstrata, niveis = self._resolver(num)
        nivel = niveis[ilvl] if 0 <= ilvl < NIVEIS else None
        if abstrata is None or nivel is None:
            return None
        valores = self._valores.setdefault(abstrata.id, [None] * NIVEIS)
        if num not in self._vistas:
            self._vistas.add(num)
            inst = cat.instancias[num]
            for s in inst.sobrescritas:
                if 0 <= s.ilvl < NIVEIS and (s.inicio is not None or s.nivel is not None):
                    valores[s.ilvl] = None
        for k in range(ilvl + 1, NIVEIS):
            definicao = niveis[k]
            regra = definicao.reinicio if definicao is not None else None
            if regra is None or (regra > 0 and ilvl < regra):
                valores[k] = None
        valores[ilvl] = nivel.inicio if valores[ilvl] is None else valores[ilvl] + 1
        return Rotulo(texto=montar_texto(nivel, valores, niveis), nivel=nivel, num=num, ilvl=ilvl,
                      valor=valores[ilvl])


def rotulos_do_documento(doc) -> dict[int, Rotulo]:
    """id(paragrafo) -> Rotulo, para o corpo (a ordem de leitura, tabelas por linha)."""
    from editdoc.modelo.documento import paragrafos_de
    cat = getattr(doc, "numeracao", None)
    contador = Contador(cat, doc.estilos)
    saida: dict[int, Rotulo] = {}
    for p in paragrafos_de(doc.paragrafos):
        efetiva = lista_efetiva(p.lista, p.lista_nivel, p.estilo, doc.estilos, cat)
        if efetiva is None:
            continue
        rotulo = contador.proximo(*efetiva)
        if rotulo is not None:
            saida[id(p)] = rotulo
    return saida


# -- galerias (o que os botoes da faixa criam) ------------------------------------------

#: Marcadores do Word: Symbol F0B7 (redondo), Courier New "o" (vazado), Wingdings F0A7 (quadrado).
MARCADOR_REDONDO = ("", "Symbol")
MARCADOR_VAZADO = ("o", "Courier New")
MARCADOR_QUADRADO = ("", "Wingdings")
_CICLO_MARCADORES = (MARCADOR_REDONDO, MARCADOR_VAZADO, MARCADOR_QUADRADO)

#: Galeria de marcadores: chave -> (rotulo na tela, simbolo do primeiro nivel).
GALERIA_MARCADORES = {
    "redondo": ("• Marcador redondo", MARCADOR_REDONDO),
    "vazado": ("○ Marcador vazado", MARCADOR_VAZADO),
    "quadrado": ("▪ Marcador quadrado", MARCADOR_QUADRADO),
}
#: Galeria de numeracao: chave -> (rotulo, formato do primeiro nivel, texto do primeiro nivel).
GALERIA_NUMERACAO = {
    "decimal_ponto": ("1.  2.  3.", "decimal", "%1."),
    "decimal_parentese": ("1)  2)  3)", "decimal", "%1)"),
    "letra_minuscula": ("a.  b.  c.", "lowerLetter", "%1."),
    "letra_maiuscula": ("A.  B.  C.", "upperLetter", "%1."),
    "romano_minusculo": ("i.  ii.  iii.", "lowerRoman", "%1."),
    "romano_maiusculo": ("I.  II.  III.", "upperRoman", "%1."),
}
#: Listas de varios niveis: chave -> rotulo.
GALERIA_MULTINIVEL = {
    "decimal": "1.  1.1.  1.1.1.",
    "capitulo": "Capítulo 1 / Seção 1.1",
    "titulos": "1 Título 1 / 1.1 Título 2 / 1.1.1 Título 3",
}


def niveis_de_marcadores(chave: str = "redondo") -> tuple:
    primeiro = GALERIA_MARCADORES.get(chave, GALERIA_MARCADORES["redondo"])[1]
    niveis = []
    for i in range(NIVEIS):
        texto, fonte = primeiro if i == 0 else _CICLO_MARCADORES[i % 3]
        niveis.append(Nivel(ilvl=i, inicio=1, formato="bullet", texto=texto,
                            recuo_esquerdo_tw=720 * (i + 1), recuo_primeira_linha_tw=-360,
                            caractere=(("fonte", fonte),)))
    return tuple(niveis)


def niveis_de_numeracao(chave: str = "decimal_ponto") -> tuple:
    """Como a lista numerada do Word: o formato escolhido no nivel 1, depois a., i., 1. ..."""
    _rotulo, formato0, texto0 = GALERIA_NUMERACAO.get(chave, GALERIA_NUMERACAO["decimal_ponto"])
    ciclo = (("decimal", "left", -360), ("lowerLetter", "left", -360), ("lowerRoman", "right", -180))
    niveis = []
    for i in range(NIVEIS):
        formato, jc, recuo = ciclo[i % 3]
        texto = f"%{i + 1}."
        if i == 0:
            formato, texto = formato0, texto0
            jc, recuo = "left", -360
        niveis.append(Nivel(ilvl=i, inicio=1, formato=formato, texto=texto, alinhamento=jc,
                            recuo_esquerdo_tw=720 * (i + 1), recuo_primeira_linha_tw=recuo))
    return tuple(niveis)


def niveis_multinivel(chave: str = "decimal") -> tuple:
    niveis = []
    if chave == "titulos":
        for i in range(NIVEIS):
            texto = ".".join(f"%{k + 1}" for k in range(i + 1))
            recuo = 432 + 144 * i
            niveis.append(Nivel(ilvl=i, inicio=1, formato="decimal", texto=texto,
                                estilo=f"Heading{i + 1}", recuo_esquerdo_tw=recuo,
                                recuo_primeira_linha_tw=-recuo))
        return tuple(niveis)
    if chave == "capitulo":
        textos = ("Capítulo %1", "Seção %1.%2", "%1.%2.%3")
        for i in range(NIVEIS):
            texto = textos[i] if i < 3 else ".".join(f"%{k + 1}" for k in range(i + 1))
            niveis.append(Nivel(ilvl=i, inicio=1, formato="decimal", texto=texto,
                                sufixo="space" if i < 2 else "tab",
                                recuo_esquerdo_tw=0 if i < 2 else 720 + 360 * (i - 2),
                                recuo_primeira_linha_tw=0 if i < 2 else -720))
        return tuple(niveis)
    esquerdos = (360, 792, 1224, 1728, 2232, 2736, 3240, 3744, 4320)
    deslocados = (360, 432, 504, 648, 792, 936, 1080, 1224, 1440)
    for i in range(NIVEIS):
        texto = "".join(f"%{k + 1}." for k in range(i + 1))
        niveis.append(Nivel(ilvl=i, inicio=1, formato="decimal", texto=texto,
                            recuo_esquerdo_tw=esquerdos[i], recuo_primeira_linha_tw=-deslocados[i]))
    return tuple(niveis)


# -- documentos montados em codigo (Paragrafo.numeracao sem lista) ---------------------

def materializar(doc) -> None:
    """Troca o tipo simples (`Paragrafo.numeracao` sem `lista`) por numId, no proprio `doc`.

    E' o que o escritor fazia antes da 0.1.4: um numId para todos os marcadores; um numId
    por grupo contiguo de numeracao, reiniciando em 1. Quem cria documento em codigo (testes,
    HTML colado) usa so' o tipo; o escritor, a ponte e `normalizar` chamam isto e dao os
    mesmos ids.
    """
    from editdoc.modelo.documento import TIPOS_DE_FAIXA, Tabela
    historias = [doc.paragrafos]
    for faixas in (doc.cabecalhos, doc.rodapes):
        historias.extend(faixas[t] for t in TIPOS_DE_FAIXA if t in faixas)
    precisa = []

    def coletar(blocos, grupos):
        grupo = None
        for bloco in blocos:
            if isinstance(bloco, Tabela):
                grupo = None
                for linha in bloco.linhas:
                    for celula in linha.celulas:
                        coletar(celula.blocos, grupos)
                continue
            if not _so_tipo(bloco, doc):
                grupo = None
                continue
            if bloco.numeracao == "marcadores":
                grupos.append(("marcadores", [bloco]))
                grupo = None
                continue
            if grupo is None:
                grupo = ("numeracao", [])
                grupos.append(grupo)
            grupo[1].append(bloco)

    for blocos in historias:
        coletar(blocos, precisa)
    if not precisa:
        return
    cat = doc.numeracao.copia() if doc.numeracao is not None else Numeracao()
    num_marcadores = None
    abstrata_numeros = None
    for tipo, paragrafos in precisa:
        if tipo == "marcadores":
            if num_marcadores is None:
                abstrata = cat.adicionar_abstrata(niveis_de_marcadores("redondo"))
                num_marcadores = cat.instancia_simples(abstrata.id).id
            num = num_marcadores
        else:
            if abstrata_numeros is None:
                abstrata_numeros = cat.adicionar_abstrata(niveis_de_numeracao("decimal_ponto")).id
            num = cat.adicionar_instancia(abstrata_numeros, (Sobrescrita(ilvl=0, inicio=1),)).id
        for p in paragrafos:
            p.lista = num
            p.lista_nivel = 0
    doc.numeracao = cat


def _so_tipo(p, doc) -> bool:
    """O paragrafo diz so' o tipo da lista: sem numId direto e sem lista vinda do estilo (o
    leitor preenche o tipo da lista herdada do estilo, que nao se materializa)."""
    if p.numeracao is None or p.lista is not None:
        return False
    return lista_efetiva(None, p.lista_nivel, p.estilo, doc.estilos,
                         getattr(doc, "numeracao", None)) is None


def _precisa_materializar(doc) -> bool:
    from editdoc.modelo.documento import TIPOS_DE_FAIXA, paragrafos_de
    historias = [doc.paragrafos]
    for faixas in (doc.cabecalhos, doc.rodapes):
        historias.extend(faixas[t] for t in TIPOS_DE_FAIXA if t in faixas)
    return any(_so_tipo(p, doc) for blocos in historias for p in paragrafos_de(blocos))


def materializado(doc):
    """O proprio `doc` se nao ha' lista so' com o tipo; senao uma copia materializada."""
    if not _precisa_materializar(doc):
        return doc
    import copy as _copy
    saida = _copy.copy(doc)
    saida.paragrafos = _copy.deepcopy(doc.paragrafos)
    saida.cabecalhos = _copy.deepcopy(doc.cabecalhos)
    saida.rodapes = _copy.deepcopy(doc.rodapes)
    materializar(saida)
    return saida


def tipos_dos_paragrafos(doc) -> None:
    """Preenche `Paragrafo.numeracao` (o tipo, fora da comparacao) a partir da lista efetiva."""
    from editdoc.modelo.documento import TIPOS_DE_FAIXA, paragrafos_de
    cat = getattr(doc, "numeracao", None)
    historias = [doc.paragrafos]
    for faixas in (doc.cabecalhos, doc.rodapes):
        historias.extend(faixas[t] for t in TIPOS_DE_FAIXA if t in faixas)
    for blocos in historias:
        for p in paragrafos_de(blocos):
            efetiva = lista_efetiva(p.lista, p.lista_nivel, p.estilo, doc.estilos, cat)
            if efetiva is not None:
                p.numeracao = cat.tipo_de(*efetiva, doc.estilos)
            elif p.lista is not None:
                p.numeracao = None
            # sem lista e sem numId: o tipo simples (HTML colado) fica para materializar
