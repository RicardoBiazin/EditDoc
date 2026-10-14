"""Comentarios (0.1.6): o catalogo do documento. Sem Qt e sem lxml.

No texto, cada comentario e' ancorado por tres marcas no fluxo (`MarcaComentario`, em
`modelo/documento.py`): o inicio e o fim do trecho comentado (w:commentRangeStart e
w:commentRangeEnd) e a referencia (o run com w:commentReference, que o Word poe logo depois
do fim). O conteudo do comentario, o autor, a data, a resposta e o estado "resolvido" ficam
aqui, no `Comentarios` do documento (`Documento.comentarios`, fora da comparacao, como os
estilos: a conferencia compara os comentarios a parte).

Partes do pacote (`formato_docx/comentarios.py`):

- word/comments.xml: w:comment com w:id, w:author, w:date, w:initials e os paragrafos;
- word/commentsExtended.xml (w15): por w14:paraId do ultimo paragrafo, o pai (resposta) e o
  "done" (resolvido);
- word/commentsIds.xml (w16cid): paraId -> durableId;
- word/commentsExtensible.xml (w16cex): durableId -> dateUtc;
- word/people.xml (w15:person): fica nas partes preservadas do pacote; o autor novo entra
  la' (sem repetir quem ja' esta').

`original`: o w:comment do arquivo (bytes). Comentario que o EditDoc nao mudou volta com
ele, igual; o editado ou novo e' gerado pelo escritor de sempre. Responder e resolver nao
mexem no comments.xml (mudam o commentsExtended), entao o original fica.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, field, replace

#: Limites contra arquivo hostil (o leitor aplica). Acima deles os comentarios nao sao lidos
#: (aviso COMENTARIO, com perda).
LIMITES = {
    "comentarios": 5000,
    #: bytes do w:comment de um comentario (o conteudo)
    "comentario_bytes": 1024 * 1024,
    #: bytes do comments.xml inteiro
    "comentarios_bytes": 32 * 1024 * 1024,
    #: paragrafos de um comentario
    "comentario_paragrafos": 2000,
    #: resposta de resposta de resposta...: acima disso, a resposta sobe para o topo da conversa
    "comentario_profundidade": 32,
}


@dataclass(frozen=True)
class Comentario:
    """Um comentario. `paragrafos`: os blocos do conteudo (Paragrafo; Tabela e' rara mas vale).

    `data` e' o w:date como o arquivo traz (o Word grava a hora local sem fuso, "2026-06-12T
    16:45:59"); `data_utc` e' o w16cex:dateUtc. `pai` e' o id do comentario respondido.
    `para_id` e' o w14:paraId do ultimo paragrafo (a chave do commentsExtended e do
    commentsIds); `duravel`, o w16cid:durableId (a chave do commentsExtensible).
    """
    id: int
    autor: str = ""
    iniciais: str = ""
    data: str = ""
    paragrafos: tuple = ()
    pai: int | None = None
    resolvido: bool = False
    para_id: str | None = None
    duravel: str | None = None
    data_utc: str | None = None
    #: o w:comment do arquivo de origem (bytes) quando pode voltar igual; None = gerar
    original: bytes | None = field(default=None, compare=False, repr=False)
    #: as relacoes externas (links) que o XML de origem cita: (rId, tipo, alvo). Voltam com o
    #: mesmo rId quando possivel.
    relacoes: tuple = field(default=(), compare=False, repr=False)

    def texto(self) -> str:
        """O conteudo em texto (paragrafos separados por quebra de linha)."""
        from editdoc.modelo.documento import Paragrafo, paragrafos_de
        partes = []
        for p in paragrafos_de(list(self.paragrafos)):
            if isinstance(p, Paragrafo):
                partes.append("".join(r.texto for r in p.runs if not r.eh_objeto()))
        return "\n".join(partes)


@dataclass
class Comentarios:
    """Os comentarios do documento, na ordem do comments.xml, e as partes de origem.

    `xml_*`: os bytes de origem de cada parte, para voltarem iguais quando nada mudou.
    `originais`: o estado de cada comentario ao abrir (para saber se o commentsExtended,
    o commentsIds e o commentsExtensible mudaram). `tipos_rel`: o Type de cada relacao de
    origem (o Word tem variantes de URI), por parte.
    """
    itens: list[Comentario] = field(default_factory=list)
    xml_comentarios: bytes | None = None
    xml_estendido: bytes | None = None
    xml_ids: bytes | None = None
    xml_extensivel: bytes | None = None
    originais: tuple = ()
    tipos_rel: dict = field(default_factory=dict)

    def obter(self, ident: int) -> Comentario | None:
        return next((c for c in self.itens if c.id == ident), None)

    def ids(self) -> list[int]:
        return [c.id for c in self.itens]

    def respostas(self, ident: int) -> list[Comentario]:
        """As respostas diretas de `ident`, na ordem."""
        return [c for c in self.itens if c.pai == ident]

    def descendentes(self, ident: int) -> list[int]:
        """`ident` e todas as respostas (a conversa abaixo dele), sem repetir."""
        saida = [ident]
        i = 0
        while i < len(saida):
            for c in self.itens:
                if c.pai == saida[i] and c.id not in saida:
                    saida.append(c.id)
            i += 1
        return saida

    def raiz(self, ident: int) -> int:
        """O comentario do topo da conversa de `ident`."""
        vistos = set()
        atual = self.obter(ident)
        while atual is not None and atual.pai is not None and atual.id not in vistos:
            vistos.add(atual.id)
            pai = self.obter(atual.pai)
            if pai is None:
                break
            atual = pai
        return atual.id if atual is not None else ident

    def proximo_id(self) -> int:
        return max((c.id for c in self.itens), default=-1) + 1

    def com_itens(self, itens: list[Comentario]) -> "Comentarios":
        return replace(self, itens=list(itens))


def estado(c: Comentario) -> tuple:
    """O que vai para as partes estendidas: muda o commentsExtended/Ids/Extensible."""
    return (c.id, c.pai, c.resolvido, c.para_id, c.duravel, c.data_utc)


def agora_local() -> str:
    """A data no formato do w:date que o Word grava: hora local, sem fuso nem fracao."""
    return _dt.datetime.now().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def agora_utc() -> str:
    """O w16cex:dateUtc: UTC, com milissegundos e "Z", como o Word grava."""
    agora = _dt.datetime.now(_dt.timezone.utc)
    return agora.strftime("%Y-%m-%dT%H:%M:%S.") + f"{agora.microsecond // 1000:03d}Z"


def data_para_tela(data: str) -> str:
    """'2026-06-12T16:45:59' -> '12/06/2026 16:45'. Data que nao se le volta como veio."""
    texto = (data or "").strip()
    if not texto:
        return ""
    base = texto.rstrip("Z")
    for formato in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            d = _dt.datetime.strptime(base[:19] if "T" in base else base[:10], formato)
        except ValueError:
            continue
        if texto.endswith("Z") or "+" in texto[10:]:
            d = d.replace(tzinfo=_dt.timezone.utc).astimezone().replace(tzinfo=None)
        return d.strftime("%d/%m/%Y %H:%M") if "T" in base else d.strftime("%d/%m/%Y")
    return texto


def iniciais_de(nome: str) -> str:
    """'Erika Rocha' -> 'ER'. No maximo 9 letras, como o Word."""
    letras = "".join(p[0] for p in nome.replace(".", " ").split() if p and p[0].isalpha())
    return letras.upper()[:9] or (nome[:2].upper() if nome else "")


def hex_unico(semente: str, usados: set[str], teto: int) -> str:
    """8 digitos hexa maiusculos, abaixo de `teto`, fora de `usados`, a partir da semente.

    Determinista: o escritor e a conferencia chegam ao mesmo valor para o mesmo documento.
    """
    n = 0
    while True:
        h = hashlib.sha256(f"{semente}|{n}".encode("utf-8")).digest()
        valor = int.from_bytes(h[:4], "big") % teto
        texto = f"{max(valor, 1):08X}"
        if texto not in usados:
            usados.add(texto)
            return texto
        n += 1


#: paraId e' menor que 0x80000000; durableId, menor que 0x7FFFFFFF (como o Word gera).
TETO_PARA_ID = 0x80000000
TETO_DURAVEL = 0x7FFFFFFF


def completar(cat: Comentarios, para: bool, duravel: bool = False,
              utc: bool = False) -> Comentarios:
    """paraId (se alguma parte estendida vai ser gravada), durableId (commentsIds) e dateUtc
    (commentsExtensible) de quem nao tem. Determinista (ver `hex_unico`)."""
    if not cat.itens:
        return cat
    para_usados = {c.para_id for c in cat.itens if c.para_id}
    dur_usados = {c.duravel for c in cat.itens if c.duravel}
    itens = []
    vistos_para: set[str] = set()
    vistos_dur: set[str] = set()
    for c in cat.itens:
        mudar = {}
        pid = c.para_id
        if para and (not pid or pid in vistos_para):
            pid = hex_unico(f"p{c.id}|{c.autor}|{c.data}", para_usados, TETO_PARA_ID)
            mudar["para_id"] = pid
        if pid:
            vistos_para.add(pid)
        dur = c.duravel
        if duravel and (not dur or dur in vistos_dur):
            dur = hex_unico(f"d{c.id}|{c.autor}|{c.data}", dur_usados, TETO_DURAVEL)
            mudar["duravel"] = dur
        if dur:
            vistos_dur.add(dur)
        if utc and not c.data_utc and c.data:
            utc = _utc_de(c.data)
            if utc:
                mudar["data_utc"] = utc
        itens.append(replace(c, **mudar) if mudar else c)
    return cat.com_itens(itens)


def _utc_de(data: str) -> str | None:
    """A data local do w:date em UTC, no formato do dateUtc. None se a data nao se le."""
    try:
        d = _dt.datetime.strptime(data.rstrip("Z")[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    if data.endswith("Z"):
        d = d.replace(tzinfo=_dt.timezone.utc)
    else:
        d = d.astimezone(_dt.timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.000Z")
