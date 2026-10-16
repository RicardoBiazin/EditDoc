"""Paginacao como a do Word (0.1.17): regras sem Qt.

O `QTextDocumentLayout` do Qt 6.11 pagina de outro jeito que o Word. Medido contra o que o
proprio Word gravou nos arquivos (`w:lastRenderedPageBreak`, docs/SPIKES.md "0.1.17"):

- altura da linha: o Qt usa a ascendente e a descendente da fonte (no Windows, as do OS/2
  winAscent/winDescent); o Word soma ainda o "espaco externo" (o lineGap do hhea que passa da
  altura do win): Arial e Times New Roman de 12 pt dao 268 twips no Qt e 276 no Word. Calibri,
  Verdana e Cambria nao tem espaco externo. A razao Word/Qt e' da familia, nao do tamanho:
  `altura_word` mede a da fonte;
- espaco entre paragrafos: o Qt usa o MAIOR entre o espaco depois do de cima e o espaco antes
  do de baixo; o Word SOMA os dois, menos o que o `w:contextualSpacing` manda ignorar entre
  paragrafos do mesmo estilo (`espaco_entre`). Depois de uma quebra de pagina do usuario so'
  vale o espaco antes;
- controle de linhas viuvas e orfas (ligado por padrao no Word), manter com o proximo e manter
  linhas juntas: `deve_empurrar` diz se o paragrafo partido entre duas paginas desce inteiro.

Tudo isso e' so' de layout (tela, PDF, impressao): nada muda no arquivo gravado.

`RegrasDePaginacao` le os elementos on/off do `w:pPr` (keepNext, keepLines, widowControl,
contextualSpacing, pageBreakBefore) na cadeia de estilos do `styles.xml` original, no docDefaults e
nos estilos que o EditDoc gera (`Estilo.extras`). O do paragrafo vem dos extras do `w:pPr` dele.
"""

from __future__ import annotations

import functools
import struct

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
#: Elementos on/off de pPr que a paginacao usa.
FLAGS = ("keepNext", "keepLines", "widowControl", "contextualSpacing", "pageBreakBefore")
#: O que vale quando nada na cadeia diz (o Word liga o controle de viuvas e orfas por padrao).
PADROES = {"widowControl": True}
_FALSO = {"0", "false", "off"}


def _ligado(valor: str | None) -> bool:
    return valor is None or valor.strip().lower() not in _FALSO


@functools.lru_cache(maxsize=512)
def _flags_do_texto(xml: str) -> dict:
    try:
        raiz = etree.fromstring(xml.encode("utf8"), etree.XMLParser(resolve_entities=False,
                                                                    no_network=True))
    except (etree.XMLSyntaxError, ValueError):
        return {}
    return _flags_do_ppr(raiz)


def flag_do_xml(xml: str | None, nome: str) -> bool | None:
    """O valor de um on/off nos extras do w:pPr de um paragrafo (so' os filhos diretos: o
    pPrChange tem o de antes da revisao), ou None se ausente."""
    if not xml or nome not in xml:
        return None
    return _flags_do_texto(xml).get(nome)


def _flags_do_ppr(ppr) -> dict:
    saida = {}
    if ppr is None:
        return saida
    for f in ppr:
        if not isinstance(f.tag, str) or not f.tag.startswith("{%s}" % W):
            continue
        nome = etree.QName(f).localname
        if nome in FLAGS:
            saida[nome] = _ligado(f.get("{%s}val" % W))
    return saida


class RegrasDePaginacao:
    """Os on/off de paginacao de cada estilo de paragrafo de um catalogo."""

    def __init__(self, estilos) -> None:
        self.estilos = estilos
        self._xml: dict[str, tuple[str | None, dict]] = {}
        self._padrao: dict = {}
        self._cache: dict = {}
        bruto = getattr(estilos, "xml_original", None)
        if bruto:
            try:
                raiz = etree.fromstring(bruto, etree.XMLParser(resolve_entities=False,
                                                               no_network=True, huge_tree=False))
            except etree.XMLSyntaxError:
                raiz = None
            if raiz is not None:
                dd = raiz.find("{%s}docDefaults/{%s}pPrDefault/{%s}pPr" % (W, W, W))
                self._padrao = _flags_do_ppr(dd)
                for st in raiz.iter("{%s}style" % W):
                    if st.get("{%s}type" % W) not in (None, "paragraph"):
                        continue
                    sid = st.get("{%s}styleId" % W)
                    if not sid:
                        continue
                    base = st.find("{%s}basedOn" % W)
                    self._xml[sid] = (base.get("{%s}val" % W) if base is not None else None,
                                      _flags_do_ppr(st.find("{%s}pPr" % W)))

    def _do_estilo(self, sid: str | None, nome: str) -> bool | None:
        vistos = set()
        while sid and sid not in vistos:
            vistos.add(sid)
            estilo = self.estilos.obter(sid) if self.estilos is not None else None
            if sid in self._xml:
                base, flags = self._xml[sid]
                if nome in flags:
                    return flags[nome]
                sid = base
                continue
            if estilo is None:
                return None
            if nome in (estilo.extras or ()):
                return True
            sid = estilo.baseado_em
        return None

    def flag(self, sid: str | None, extras_ppr: str | None, nome: str) -> bool:
        """On/off efetivo: o do paragrafo, o da cadeia do estilo, o do docDefaults, o padrao."""
        proprio = flag_do_xml(extras_ppr, nome)
        if proprio is not None:
            return proprio
        sid = sid or (self.estilos.id_padrao() if self.estilos is not None else None)
        chave = (sid, nome)
        if chave not in self._cache:
            valor = self._do_estilo(sid, nome)
            if valor is None:
                valor = self._padrao.get(nome, PADROES.get(nome, False))
            self._cache[chave] = valor
        return self._cache[chave]


def espaco_entre(depois_a: float, antes_b: float, mesmo_estilo: bool, contextual_a: bool,
                 contextual_b: bool, quebra: bool = False) -> float:
    """O espaco do Word entre dois paragrafos seguidos (twips ou px, a mesma unidade).

    O Word soma o espaco depois do de cima e o espaco antes do de baixo. Entre paragrafos do
    mesmo estilo, o que tem `contextualSpacing` perde o seu. Depois de uma quebra de pagina do
    usuario (o de cima termina a pagina), so' o espaco antes do de baixo."""
    if mesmo_estilo:
        if contextual_a:
            depois_a = 0.0
        if contextual_b:
            antes_b = 0.0
    if quebra:
        return max(0.0, antes_b)
    return max(0.0, depois_a) + max(0.0, antes_b)


def deve_empurrar(linhas_antes: int, linhas_depois: int, viuvas: bool, juntas: bool,
                  primeiro_da_pagina: bool) -> bool:
    """O paragrafo partido (linhas na pagina de cima e na de baixo) desce inteiro?

    - manter linhas juntas: sim, se esta' partido;
    - controle de viuvas e orfas: uma linha so' embaixo da pagina (orfa) desce o paragrafo; uma
      linha so' no alto da pagina seguinte (viuva) puxa outra, e se em cima ficaria uma so', o
      paragrafo desce inteiro. A viuva de um paragrafo com tres linhas ou mais em cima pediria
      descer UMA linha, o que o layout do Qt nao faz (limite: fica como esta').
    O primeiro paragrafo da pagina nunca desce (nao caberia em pagina nenhuma)."""
    if primeiro_da_pagina or linhas_antes <= 0 or linhas_depois <= 0:
        return False
    if juntas:
        return True
    if viuvas:
        if linhas_antes == 1:
            return True
        if linhas_depois == 1 and linhas_antes == 2:
            return True
    return False


def linhas_que_cabem(y0: float, alturas: list[tuple[float, float]], pe: float) -> int:
    """Quantas linhas, a partir de `y0`, cabem antes de `pe`. `alturas`: (avanco, altura de
    corte) de cada linha, como o Qt testa (o topo da linha mais a altura de corte <= pe)."""
    y = y0
    n = 0
    for avanco, corte in alturas:
        if y + corte > pe + 0.5:
            break
        y += avanco
        n += 1
    return n


# -- altura da linha ---------------------------------------------------------------------------

def unidades_da_linha_word(head: bytes, hhea: bytes, os2: bytes) -> tuple[int, int, int] | None:
    """(unidades por eme, altura do Qt no Windows, altura do Word), em unidades da fonte.

    Qt no Windows: winAscent + winDescent (o OS/2). Word: o mesmo mais o espaco externo, o lineGap
    do hhea que passa dessa altura: max(0, ascendente - descendente + lineGap do hhea - win)."""
    try:
        upm = struct.unpack(">H", head[18:20])[0]
        asc, desc, gap = struct.unpack(">hhh", hhea[4:10])
        win_asc, win_desc = struct.unpack(">HH", os2[74:78])
    except (struct.error, TypeError):
        return None
    if upm <= 0 or win_asc + win_desc <= 0:
        return None
    win = win_asc + win_desc
    externo = max(0, (asc - desc + gap) - win)
    return upm, win, win + externo
