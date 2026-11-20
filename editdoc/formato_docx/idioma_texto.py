"""Idioma e "nao verificar" do texto, lidos do XML do arquivo (0.1.36). Sem Qt.

So' a tela usa: o corretor ortografico precisa saber, para cada trecho, em que idioma ele esta
(w:lang) e se o autor mandou nao verificar (w:noProof). Nada daqui volta ao arquivo, e nada e'
gravado: o XML continua sendo a fonte, como em `Estilo.aparencia`.

Onde o w:lang e o w:noProof moram:

- no w:rPr do run: ja' vao para `Run.extras` (formatacao preservada, 0.1.5), que a ponte poe na
  propriedade `PROP_RPR_EXTRA` do caractere. `idioma_do_run` le' daquele texto;
- no w:rPr de um estilo (paragrafo ou caractere) e no docDefaults do styles.xml:
  `IdiomasDeEstilos` le' o `xml_original` do catalogo, uma vez ao abrir. A heranca segue
  w:basedOn; o estilo de caractere vence o de paragrafo, e o run vence os dois.

O `w:lang` tem tres atributos (val, eastAsia, bidi): o texto latino usa o `val`.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field

from lxml import etree

from editdoc import log_interno
from editdoc.formato_docx.nomes import W, q
from editdoc.formato_docx.propriedades import _local, _onoff, filhos_de, parser_seguro
from editdoc.ortografia import normalizar_etiqueta

log = log_interno.obter(__name__)

#: Teto de estilos lidos (um styles.xml de lixo nao pode pesar).
_MAXIMO_DE_ESTILOS = 20000


@functools.lru_cache(maxsize=2048)
def idioma_do_run(extras: str | None) -> tuple[str | None, bool | None]:
    """(idioma, sem_verificacao) do w:rPr guardado nos extras do run: o idioma ja' normalizado
    ("pt-BR") ou None se o run nao diz; sem_verificacao True/False se ha' w:noProof (False com
    w:val="0"), None se nao ha'."""
    if not extras:
        return None, None
    idioma = None
    sem = None
    for f in filhos_de(extras):
        ns, loc = _local(f)
        if ns != W:
            continue
        if loc == "lang":
            idioma = normalizar_etiqueta(f.get(q("val")))
        elif loc == "noProof":
            sem = _onoff(f)
    return idioma, sem


@dataclass
class _Estilo:
    base: str | None = None
    idioma: str | None = None
    sem: bool | None = None


@dataclass
class IdiomasDeEstilos:
    """w:lang e w:noProof dos estilos do arquivo e o idioma do docDefaults."""
    padrao: str | None = None
    estilos: dict = field(default_factory=dict)
    _cache: dict = field(default_factory=dict, repr=False)

    def _do_estilo(self, sid: str | None) -> tuple[str | None, bool | None]:
        """(idioma, sem_verificacao) efetivos do estilo, com a heranca de w:basedOn."""
        if not sid:
            return None, None
        achado = self._cache.get(sid)
        if achado is not None:
            return achado
        idioma = sem = None
        visto: set = set()
        atual = sid
        while atual and atual not in visto and len(visto) < 32:
            visto.add(atual)
            e = self.estilos.get(atual)
            if e is None:
                break
            if idioma is None:
                idioma = e.idioma
            if sem is None:
                sem = e.sem
            atual = e.base
        self._cache[sid] = (idioma, sem)
        return idioma, sem

    def do_texto(self, sid_par: str | None, sid_car: str | None) -> tuple[str | None, bool | None]:
        """(idioma, sem_verificacao) que o texto herda sem formatacao direta: o estilo de
        caractere vence o de paragrafo."""
        ip, sp = self._do_estilo(sid_par)
        ic, sc = self._do_estilo(sid_car)
        return (ic if ic is not None else ip), (sc if sc is not None else sp)


def idiomas_de_estilos(xml: bytes | None) -> IdiomasDeEstilos:
    """Le o styles.xml (bytes). Ilegivel ou ausente: sem nada (o padrao do programa vale)."""
    saida = IdiomasDeEstilos()
    if not xml:
        return saida
    try:
        raiz = etree.fromstring(xml, parser_seguro())
    except (etree.LxmlError, ValueError) as erro:
        log.warning("styles.xml ilegivel para o idioma: %s", erro)
        return saida
    padrao = raiz.find(q("docDefaults") + "/" + q("rPrDefault") + "/" + q("rPr"))
    if padrao is not None:
        lang = padrao.find(q("lang"))
        if lang is not None:
            saida.padrao = normalizar_etiqueta(lang.get(q("val")))
    for estilo in raiz.findall(q("style"))[:_MAXIMO_DE_ESTILOS]:
        sid = estilo.get(q("styleId"))
        if not sid:
            continue
        item = _Estilo()
        base = estilo.find(q("basedOn"))
        if base is not None:
            item.base = base.get(q("val"))
        rpr = estilo.find(q("rPr"))
        if rpr is not None:
            lang = rpr.find(q("lang"))
            if lang is not None:
                item.idioma = normalizar_etiqueta(lang.get(q("val")))
            sem = rpr.find(q("noProof"))
            if sem is not None:
                item.sem = _onoff(sem)
        saida.estilos[sid] = item
    return saida
