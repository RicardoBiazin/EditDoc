"""numbering.xml <-> catalogo de numeracao (0.1.4). Sem Qt.

Antes da 0.1.4 o EditDoc regravava o numbering.xml do zero, com duas listas (marcador e
1, 2, 3): formato, niveis, recuos e simbolos do arquivo se perdiam (avisos LISTA e
LISTA_NIVEL). Agora:

- Leitura (`ler`): cada w:abstractNum, w:num e w:numPicBullet vira definicao do modelo
  (`modelo/numeracao.py`), e o XML inteiro fica guardado. O que o Word nao aceitaria e um
  arquivo hostil poderia trazer e' tirado antes, com aviso LISTA: id repetido, w:num que
  aponta para abstrata inexistente, w:lvlPicBulletId sem w:numPicBullet, marcador de figura
  com imagem quebrada. Acima dos limites (`numeracao.LIMITES`) o numbering.xml nao e' lido.
  Os filhos de pPr e rPr dos niveis sao postos na ordem do esquema (o validador confere),
  como no styles.xml.
- Escrita (`escrever`): sem acrescimos, o XML original volta byte a byte. Com acrescimos
  (lista criada no EditDoc, reiniciar, continuar, definir valor), as abstratas novas entram
  depois da ultima abstrata e as instancias novas depois da ultima instancia; o resto do
  XML continua como veio (c14n igual).
- `validar`: numId citado existe, abstractNumId existe, ilvl de 0 a 8, ids unicos e
  w:lvlPicBulletId com w:numPicBullet. Roda antes de cada gravacao (ordem.validar).
"""

from __future__ import annotations

import copy
from dataclasses import replace

from lxml import etree

from editdoc.formato_docx import ordem
from editdoc.formato_docx.nomes import A_NS, R_NS, V_NS, W, q
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.numeracao import (LIMITES, NIVEIS, SUFIXOS, Abstrata, ImagemMarcador,
                                      Instancia, Nivel, Numeracao, Sobrescrita)

_JC = {"left": "left", "start": "left", "center": "center", "right": "right", "end": "right"}
#: Filhos de w:abstractNum na ordem do CT_AbstractNum.
ORDEM_ABSTRATA = ["nsid", "multiLevelType", "tmpl", "name", "styleLink", "numStyleLink", "lvl"]
#: Filhos de w:numbering na ordem do CT_Numbering.
ORDEM_NUMERACAO = ["numPicBullet", "abstractNum", "num", "numIdMacAtCleanup"]


class NumeracaoInvalida(Exception):
    """numbering.xml acima dos limites: nao e' lido."""


def _inteiro(valor) -> int | None:
    if valor is None:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _val(el, tag: str) -> str | None:
    filho = el.find(q(tag))
    return filho.get(q("val")) if filho is not None else None


def _onoff(el, tag: str) -> bool:
    filho = el.find(q(tag))
    if filho is None:
        return False
    v = filho.get(q("val"))
    return v is None or v.lower() not in ("0", "false", "off")


def _xml(raiz) -> bytes:
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)


# -- leitura ---------------------------------------------------------------------------

def ler_nivel(lvl, lim: dict) -> Nivel | None:
    """Um w:lvl como `Nivel`. None se o ilvl nao e' de 0 a 8 (fica so' no XML)."""
    from editdoc.formato_docx.estilos import props_de_rpr
    ilvl = _inteiro(lvl.get(q("ilvl")))
    if ilvl is None or not 0 <= ilvl < NIVEIS:
        return None
    texto = _val(lvl, "lvlText")
    if texto is not None and len(texto) > lim["lista_texto"]:
        raise NumeracaoInvalida("lvlText grande demais")
    inicio = _inteiro(_val(lvl, "start"))
    formato = _val(lvl, "numFmt") or "decimal"
    suff = _val(lvl, "suff")
    esquerdo = primeira = None
    tabs: list[int] = []
    ppr = lvl.find(q("pPr"))
    if ppr is not None:
        ind = ppr.find(q("ind"))
        if ind is not None:
            esquerdo = _inteiro(ind.get(q("left")) or ind.get(q("start")))
            if ind.get(q("hanging")) is not None:
                h = _inteiro(ind.get(q("hanging")))
                primeira = None if h is None else -h
            elif ind.get(q("firstLine")) is not None:
                primeira = _inteiro(ind.get(q("firstLine")))
        for tab in ppr.iter(q("tab")):
            pos = _inteiro(tab.get(q("pos")))
            if pos is not None and tab.get(q("val")) not in ("clear",) and len(tabs) < 64:
                tabs.append(pos)
    rpr = lvl.find(q("rPr"))
    simbolo = props_de_rpr(rpr, {}) if rpr is not None else {}
    oculto = rpr is not None and _onoff(rpr, "vanish")
    return Nivel(
        ilvl=ilvl, inicio=inicio if inicio is not None else 0, formato=formato, texto=texto,
        alinhamento=_JC.get(_val(lvl, "lvlJc") or "left", "left"),
        sufixo=suff if suff in SUFIXOS else "tab", legal=_onoff(lvl, "isLgl"),
        reinicio=_inteiro(_val(lvl, "lvlRestart")), estilo=_val(lvl, "pStyle"),
        imagem=_inteiro(_val(lvl, "lvlPicBulletId")), recuo_esquerdo_tw=esquerdo,
        recuo_primeira_linha_tw=primeira, tabulacoes=tuple(sorted(tabs)),
        caractere=tuple(sorted((k, v) for k, v in simbolo.items())), oculto=oculto)


def _imagem_do_marcador(el, relacoes: dict, partes: dict) -> tuple[bytes | None, str | None]:
    """Os bytes da imagem do w:numPicBullet (v:imagedata ou a:blip), se a tela pode mostrar."""
    for x in el.iter():
        if not isinstance(x.tag, str):
            continue
        rid = None
        if x.tag == "{%s}imagedata" % V_NS:
            rid = x.get("{%s}id" % R_NS)
        elif x.tag == "{%s}blip" % A_NS:
            rid = x.get("{%s}embed" % R_NS)
        if not rid or rid not in relacoes:
            continue
        _tipo, alvo, externo = relacoes[rid][:3]
        parte = partes.get(alvo) if not externo else None
        if parte is None:
            continue
        formato = mod_imagem.formato_de(parte.dados)
        dims = mod_imagem.dimensoes(parte.dados) if formato else None
        if formato and dims and mod_imagem.decodificavel(*dims):
            return parte.dados, formato
    return None, None


def _referencias(el) -> list[str]:
    saida = []
    for x in el.iter():
        if not isinstance(x.tag, str):
            continue
        for chave, valor in x.attrib.items():
            if chave.startswith("{%s}" % R_NS) and valor not in saida:
                saida.append(valor)
    return saida


def sanear(raiz) -> int:
    """pPr e rPr dos niveis na ordem do esquema; filho w: desconhecido sai. Devolve quantos."""
    removidos = 0
    for nome in ("pPr", "rPr"):
        lista = ordem.ORDENS[nome]
        for el in raiz.iter(q(nome)):
            conhecidos, outros = [], []
            for f in list(el):
                if not isinstance(f.tag, str):
                    el.remove(f)
                    continue
                if f.tag.startswith("{%s}" % W):
                    if etree.QName(f).localname in lista:
                        conhecidos.append(f)
                    else:
                        el.remove(f)
                        removidos += 1
                        continue
                else:
                    outros.append(f)
                el.remove(f)
            conhecidos.sort(key=lambda f: lista.index(etree.QName(f).localname))
            for f in conhecidos + outros:
                el.append(f)
    return removidos


def ler(dados: bytes, raiz, lim: dict, relacoes: dict, partes: dict,
        coletor=None) -> Numeracao:
    """O catalogo do numbering.xml. `relacoes`: rId -> (tipo, alvo, externo) da parte;
    `partes`: alvo -> ParteOpaca (o fecho que voltou inteiro). Levanta NumeracaoInvalida
    acima dos limites."""
    lim = {**LIMITES, **{k: v for k, v in (lim or {}).items() if k in LIMITES}}
    if raiz.tag != q("numbering"):
        raise NumeracaoInvalida("raiz inesperada")
    abstratas_el = raiz.findall(q("abstractNum"))
    instancias_el = raiz.findall(q("num"))
    imagens_el = raiz.findall(q("numPicBullet"))
    if (len(abstratas_el) > lim["listas_abstratas"] or len(instancias_el) > lim["listas_instancias"]
            or len(imagens_el) > lim["listas_imagens"]):
        raise NumeracaoInvalida("definicoes demais")
    mexido = False
    problemas = 0
    copia = copy.deepcopy(raiz)
    if sanear(copia):
        mexido = True
    # Marcadores de figura: a imagem tem de ter voltado inteira (o fecho das relacoes).
    imagens: dict[int, ImagemMarcador] = {}
    for el in copia.findall(q("numPicBullet")):
        ident = _inteiro(el.get(q("numPicBulletId")))
        refs = _referencias(el)
        quebrada = any(r not in relacoes or (not relacoes[r][2] and relacoes[r][1] not in partes)
                       for r in refs)
        if ident is None or ident in imagens or quebrada:
            copia.remove(el)
            mexido = True
            problemas += 1
            continue
        dados_img, formato = _imagem_do_marcador(el, relacoes, partes)
        imagens[ident] = ImagemMarcador(id=ident, dados=dados_img, formato=formato)
    abstratas: dict[int, Abstrata] = {}
    for el in copia.findall(q("abstractNum")):
        ident = _inteiro(el.get(q("abstractNumId")))
        lvls = el.findall(q("lvl"))
        if len(lvls) > lim["lista_niveis"]:
            raise NumeracaoInvalida("niveis demais")
        if ident is None or ident in abstratas:
            copia.remove(el)
            mexido = True
            problemas += 1
            continue
        niveis = []
        vistos = set()
        for lvl in lvls:
            imagem = _inteiro(_val(lvl, "lvlPicBulletId"))
            if imagem is not None and imagem not in imagens:
                lvl.remove(lvl.find(q("lvlPicBulletId")))
                mexido = True
                problemas += 1
            nivel = ler_nivel(lvl, lim)
            if nivel is not None and nivel.ilvl not in vistos:
                vistos.add(nivel.ilvl)
                niveis.append(nivel)
        abstratas[ident] = Abstrata(
            id=ident, niveis=tuple(sorted(niveis, key=lambda n: n.ilvl)),
            tipo=_val(el, "multiLevelType"), nsid=_val(el, "nsid"), modelo=_val(el, "tmpl"),
            nome=_val(el, "name"), estilo_link=_val(el, "styleLink"),
            num_estilo_link=_val(el, "numStyleLink"))
    instancias: dict[int, Instancia] = {}
    for el in copia.findall(q("num")):
        ident = _inteiro(el.get(q("numId")))
        alvo = _inteiro(_val(el, "abstractNumId"))
        sobres = el.findall(q("lvlOverride"))
        if len(sobres) > lim["lista_sobrescritas"]:
            raise NumeracaoInvalida("sobrescritas demais")
        if ident is None or ident <= 0 or ident in instancias or alvo not in abstratas:
            copia.remove(el)
            mexido = True
            problemas += 1
            continue
        sobrescritas = []
        for s in sobres:
            ilvl = _inteiro(s.get(q("ilvl")))
            if ilvl is None or not 0 <= ilvl < NIVEIS:
                continue
            lvl = s.find(q("lvl"))
            imagem = _inteiro(_val(lvl, "lvlPicBulletId")) if lvl is not None else None
            if imagem is not None and imagem not in imagens:
                lvl.remove(lvl.find(q("lvlPicBulletId")))
                mexido = True
                problemas += 1
            nivel = ler_nivel(lvl, lim) if lvl is not None else None
            if nivel is not None and nivel.ilvl != ilvl:
                nivel = replace(nivel, ilvl=ilvl)
            sobrescritas.append(Sobrescrita(ilvl=ilvl, inicio=_inteiro(_val(s, "startOverride")),
                                            nivel=nivel))
        instancias[ident] = Instancia(id=ident, abstrata=alvo, sobrescritas=tuple(sobrescritas))
    if problemas and coletor is not None:
        coletor.somar("LISTA", problemas)
    return Numeracao(abstratas=abstratas, instancias=instancias, imagens=imagens,
                     xml_original=_xml(copia) if mexido else dados,
                     ids_originais=(frozenset(abstratas), frozenset(instancias)))


# -- escrita ---------------------------------------------------------------------------

def _rfonts(rpr, fonte: str) -> None:
    rf = etree.SubElement(rpr, q("rFonts"))
    for atributo in ("ascii", "hAnsi", "cs"):
        rf.set(q(atributo), fonte)
    rf.set(q("hint"), "default")


def nivel_xml(n: Nivel):
    """O w:lvl de um nivel criado no EditDoc, na ordem do esquema."""
    lvl = etree.Element(q("lvl"))
    lvl.set(q("ilvl"), str(int(n.ilvl)))
    etree.SubElement(lvl, q("start")).set(q("val"), str(int(n.inicio)))
    etree.SubElement(lvl, q("numFmt")).set(q("val"), n.formato)
    if n.reinicio is not None:
        etree.SubElement(lvl, q("lvlRestart")).set(q("val"), str(int(n.reinicio)))
    if n.estilo:
        etree.SubElement(lvl, q("pStyle")).set(q("val"), n.estilo)
    if n.legal:
        etree.SubElement(lvl, q("isLgl"))
    if n.sufixo != "tab":
        etree.SubElement(lvl, q("suff")).set(q("val"), n.sufixo)
    if n.texto is not None:
        etree.SubElement(lvl, q("lvlText")).set(q("val"), n.texto)
    if n.imagem is not None:
        etree.SubElement(lvl, q("lvlPicBulletId")).set(q("val"), str(int(n.imagem)))
    etree.SubElement(lvl, q("lvlJc")).set(q("val"), n.alinhamento)
    if n.recuo_esquerdo_tw is not None or n.recuo_primeira_linha_tw is not None or n.tabulacoes:
        ppr = etree.SubElement(lvl, q("pPr"))
        if n.tabulacoes:
            tabs = etree.SubElement(ppr, q("tabs"))
            for pos in n.tabulacoes:
                tab = etree.SubElement(tabs, q("tab"))
                tab.set(q("val"), "num")
                tab.set(q("pos"), str(int(pos)))
        if n.recuo_esquerdo_tw is not None or n.recuo_primeira_linha_tw is not None:
            ind = etree.SubElement(ppr, q("ind"))
            if n.recuo_esquerdo_tw is not None:
                ind.set(q("left"), str(int(n.recuo_esquerdo_tw)))
            v = n.recuo_primeira_linha_tw
            if v is not None:
                ind.set(q("hanging") if v < 0 else q("firstLine"), str(abs(int(v))))
    simbolo = n.simbolo()
    if simbolo or n.oculto:
        rpr = etree.SubElement(lvl, q("rPr"))
        if simbolo.get("fonte"):
            _rfonts(rpr, simbolo["fonte"])
        for chave, tag in (("negrito", "b"), ("italico", "i")):
            if simbolo.get(chave) is not None:
                el = etree.SubElement(rpr, q(tag))
                if not simbolo[chave]:
                    el.set(q("val"), "0")
        if n.oculto:
            etree.SubElement(rpr, q("vanish"))
        if simbolo.get("cor_hex"):
            etree.SubElement(rpr, q("color")).set(q("val"), str(simbolo["cor_hex"]).upper())
        if simbolo.get("tamanho_meio_pt"):
            etree.SubElement(rpr, q("sz")).set(q("val"), str(int(simbolo["tamanho_meio_pt"])))
            etree.SubElement(rpr, q("szCs")).set(q("val"), str(int(simbolo["tamanho_meio_pt"])))
        if simbolo.get("sublinhado") is not None:
            etree.SubElement(rpr, q("u")).set(q("val"), "single" if simbolo["sublinhado"] else "none")
        ordem.ordenar_filhos(rpr, ordem.ORDEM_RPR)
    ordem.ordenar_filhos(lvl, ordem.ORDEM_LVL)
    return lvl


def abstrata_xml(a: Abstrata):
    el = etree.Element(q("abstractNum"))
    el.set(q("abstractNumId"), str(int(a.id)))
    if a.nsid:
        etree.SubElement(el, q("nsid")).set(q("val"), a.nsid)
    if a.tipo:
        etree.SubElement(el, q("multiLevelType")).set(q("val"), a.tipo)
    if a.modelo:
        etree.SubElement(el, q("tmpl")).set(q("val"), a.modelo)
    if a.nome:
        etree.SubElement(el, q("name")).set(q("val"), a.nome)
    if a.estilo_link:
        etree.SubElement(el, q("styleLink")).set(q("val"), a.estilo_link)
    if a.num_estilo_link:
        etree.SubElement(el, q("numStyleLink")).set(q("val"), a.num_estilo_link)
    for n in a.niveis:
        el.append(nivel_xml(n))
    return el


def instancia_xml(i: Instancia):
    el = etree.Element(q("num"))
    el.set(q("numId"), str(int(i.id)))
    etree.SubElement(el, q("abstractNumId")).set(q("val"), str(int(i.abstrata)))
    for s in i.sobrescritas:
        sob = etree.SubElement(el, q("lvlOverride"))
        sob.set(q("ilvl"), str(int(s.ilvl)))
        if s.inicio is not None:
            etree.SubElement(sob, q("startOverride")).set(q("val"), str(int(s.inicio)))
        if s.nivel is not None:
            sob.append(nivel_xml(s.nivel))
    return el


def _parse(dados: bytes):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                             huge_tree=False, remove_blank_text=False)
    return etree.fromstring(dados, parser)


def escrever(cat: Numeracao | None) -> bytes:
    """O numbering.xml do catalogo: o original, mais as definicoes acrescidas no fim."""
    if cat is None:
        return _xml(etree.Element(q("numbering"), nsmap={"w": W}))
    abstratas, instancias = cat.adicoes()
    if cat.xml_original and not abstratas and not instancias:
        return cat.xml_original
    raiz = _parse(cat.xml_original) if cat.xml_original else etree.Element(q("numbering"),
                                                                            nsmap={"w": W})

    def depois_de(nomes: tuple) -> int:
        indice = -1
        for i, f in enumerate(raiz):
            if isinstance(f.tag, str) and etree.QName(f).localname in nomes:
                indice = i
        return indice + 1

    posicao = depois_de(("numPicBullet", "abstractNum"))
    for a in abstratas:
        raiz.insert(posicao, abstrata_xml(a))
        posicao += 1
    posicao = depois_de(("numPicBullet", "abstractNum", "num"))
    for i in instancias:
        raiz.insert(posicao, instancia_xml(i))
        posicao += 1
    return _xml(raiz)


# -- validacao -------------------------------------------------------------------------

def _ids_da_numeracao(raiz) -> tuple[dict, list[str]]:
    problemas: list[str] = []
    abstratas: set[int] = set()
    imagens: set[int] = set()
    instancias: set[int] = set()
    for el in raiz.findall(q("numPicBullet")):
        ident = _inteiro(el.get(q("numPicBulletId")))
        if ident is None or ident in imagens:
            problemas.append(f"numPicBullet com id repetido ou invalido: {ident!r}")
        imagens.add(ident)
    for el in raiz.findall(q("abstractNum")):
        ident = _inteiro(el.get(q("abstractNumId")))
        if ident is None or ident in abstratas:
            problemas.append(f"abstractNum com id repetido ou invalido: {ident!r}")
        abstratas.add(ident)
        for lvl in el.iter(q("lvl")):
            ilvl = _inteiro(lvl.get(q("ilvl")))
            if ilvl is None or not 0 <= ilvl < NIVEIS:
                problemas.append(f"lvl com ilvl fora de 0 a 8: {ilvl!r}")
    for el in raiz.findall(q("num")):
        ident = _inteiro(el.get(q("numId")))
        if ident is None or ident <= 0 or ident in instancias:
            problemas.append(f"num com id repetido ou invalido: {ident!r}")
        instancias.add(ident)
        alvo = _inteiro(_val(el, "abstractNumId"))
        if alvo not in abstratas:
            problemas.append(f"num {ident} aponta para abstractNum inexistente: {alvo!r}")
    for lvl in raiz.iter(q("lvlPicBulletId")):
        if _inteiro(lvl.get(q("val"))) not in imagens:
            problemas.append(f"lvlPicBulletId sem numPicBullet: {lvl.get(q('val'))!r}")
    return {"instancias": instancias, "abstratas": abstratas}, problemas


def ids_de_listas(dados: bytes | None) -> set[int]:
    """numIds definidos num numbering.xml (vazio se nao ha' numeracao)."""
    if not dados:
        return set()
    return _ids_da_numeracao(_parse(dados))[0]["instancias"]


def validar(partes: dict[str, bytes]) -> list[str]:
    """numbering.xml consistente e todo numPr (corpo, cabecalho, rodape e estilos) com numId
    existente e ilvl de 0 a 8. O que esta' dentro de objeto opaco veio do arquivo de origem."""
    problemas: list[str] = []
    ids: set[int] = set()
    if "word/numbering.xml" in partes:
        raiz = _parse(partes["word/numbering.xml"])
        conjuntos, achados = _ids_da_numeracao(raiz)
        problemas += [f"word/numbering.xml: {p}" for p in achados]
        ids = conjuntos["instancias"]
    nomes = ["word/document.xml", "word/styles.xml"] + sorted(n for n in partes if ordem.eh_faixa(n))
    for nome in nomes:
        if nome not in partes:
            continue
        raiz = _parse(partes[nome])
        opacos = ordem.dentro_de_opacos(raiz) if nome != "word/styles.xml" else set()
        for num_pr in raiz.iter(q("numPr")):
            if num_pr in opacos:
                continue
            nid = num_pr.find(q("numId"))
            ilvl = num_pr.find(q("ilvl"))
            if nid is not None:
                valor = _inteiro(nid.get(q("val")))
                if valor is None or (valor != 0 and valor not in ids):
                    problemas.append(f"{nome}: numId {nid.get(q('val'))!r} sem w:num no numbering.xml")
            if ilvl is not None:
                valor = _inteiro(ilvl.get(q("val")))
                if valor is None or not 0 <= valor < NIVEIS:
                    problemas.append(f"{nome}: ilvl {ilvl.get(q('val'))!r} fora de 0 a 8")
    return problemas
