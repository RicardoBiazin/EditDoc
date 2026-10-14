"""Comentarios (0.1.6): arquivo, validador, tela, painel, edicao, apagar texto e limites.

Fixtures geradas aqui (nenhum documento real): comentario simples; com resposta e resolvido;
aninhados e sobre o mesmo trecho; atravessando paragrafos; com hiperlink, campo e marcador
dentro; documento antigo (so' o comments.xml, sem paraId); people.xml com pessoas repetidas.

- arquivo: a leitura nao avisa nada; sem mudanca, comments.xml, commentsExtended,
  commentsIds, commentsExtensible e people.xml voltam iguais (c14n); criar, responder,
  resolver e excluir deixam as quatro partes coerentes (o validador confere), o autor novo
  entra uma vez so' no people.xml; o documento antigo ganha as partes estendidas e o paraId;
- validador: contraprovas (ancora sem comentario, comentario sem referencia, fim antes do
  inicio, paraId e durableId que nao batem);
- tela: o painel lista as conversas, clicar seleciona o trecho, o cursor destaca o cartao;
  Ctrl+Alt+M cria; responder, editar (so' leitura com campo), resolver, excluir, excluir
  todos, anterior e proximo; um desfazer volta cada comando;
- apagar texto como o Word: o trecho inteiro leva o comentario; uma ponta so', o comentario
  fica no que sobrou; o arquivo gravado e' sempre valido, com aviso quando algo sai;
- realce so' na tela (o PDF nao o tem) e o .txt sem os comentarios; nomes acessiveis;
- limites contra arquivo hostil.
"""

from __future__ import annotations

from ajudantes import checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import comentarios as fx_com  # noqa: E402
from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx.escritor import escrever, escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo import marcas as mod_marcas  # noqa: E402
from editdoc.modelo.comentarios import Comentario  # noqa: E402
from editdoc.modelo.documento import (MarcaComentario, Paragrafo, Run, normalizar,  # noqa: E402
                                      paragrafos_de)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
W15 = "http://schemas.microsoft.com/office/word/2012/wordml"
W16CID = "http://schemas.microsoft.com/office/word/2016/wordml/cid"
W16CEX = "http://schemas.microsoft.com/office/word/2018/wordml/cex"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"w": W, "w15": W15}
_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml."
PARTES = ("word/comments.xml", "word/commentsExtended.xml", "word/commentsIds.xml",
          "word/commentsExtensible.xml", "word/people.xml")


# -- fixtures -------------------------------------------------------------------------------

def t(texto: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{texto}</w:t></w:r>'


def ini(i: int) -> str:
    return f'<w:commentRangeStart w:id="{i}"/>'


def fim(i: int) -> str:
    return f'<w:commentRangeEnd w:id="{i}"/>'


def ref(i: int) -> str:
    return (f'<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
            f'<w:commentReference w:id="{i}"/></w:r>')


def comentario(i: int, autor: str, conteudo: str, para: str | None,
               data: str = "2026-06-12T16:45:59", iniciais: str = "") -> str:
    p = f' w14:paraId="{para}"' if para else ""
    return (f'<w:comment w:id="{i}" w:author="{autor}" w:date="{data}" w:initials="{iniciais}">'
            f'<w:p{p}><w:pPr><w:pStyle w:val="CommentText"/></w:pPr>'
            f'<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:annotationRef/></w:r>'
            f'{conteudo}</w:p></w:comment>')


def docx_com_comentarios(corpo: str, comentarios: list[str], estendido=None, ids=None,
                         extensivel=None, pessoas=None, rels_comentarios: str = "") -> bytes:
    partes = {"word/comments.xml": (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:comments xmlns:w="{W}" '
        f'xmlns:w14="{W14}" xmlns:r="{R}" xmlns:mc="{MC}" mc:Ignorable="w14">'
        + "".join(comentarios) + "</w:comments>").encode("utf-8")}
    rels = [("rIdC1", fx_com.RT_COMENTARIOS, "comments.xml")]
    tipos = [("/word/comments.xml", fx_com.CT_COMENTARIOS)]
    if estendido is not None:
        itens = "".join(f'<w15:commentEx w15:paraId="{p}"'
                        + (f' w15:paraIdParent="{pai}"' if pai else "")
                        + f' w15:done="{feito}"/>' for p, pai, feito in estendido)
        partes["word/commentsExtended.xml"] = (
            f'<w15:commentsEx xmlns:mc="{MC}" xmlns:w15="{W15}" mc:Ignorable="w15">{itens}'
            '</w15:commentsEx>').encode("utf-8")
        rels.append(("rIdC2", fx_com.RT_ESTENDIDO, "commentsExtended.xml"))
        tipos.append(("/word/commentsExtended.xml", fx_com.CT_ESTENDIDO))
    if ids is not None:
        itens = "".join(f'<w16cid:commentId w16cid:paraId="{p}" w16cid:durableId="{d}"/>'
                        for p, d in ids)
        partes["word/commentsIds.xml"] = (
            f'<w16cid:commentsIds xmlns:mc="{MC}" xmlns:w16cid="{W16CID}" mc:Ignorable="w16cid">'
            f'{itens}</w16cid:commentsIds>').encode("utf-8")
        rels.append(("rIdC3", fx_com.RT_IDS, "commentsIds.xml"))
        tipos.append(("/word/commentsIds.xml", fx_com.CT_IDS))
    if extensivel is not None:
        itens = "".join(f'<w16cex:commentExtensible w16cex:durableId="{d}" w16cex:dateUtc="{u}"/>'
                        for d, u in extensivel)
        partes["word/commentsExtensible.xml"] = (
            f'<w16cex:commentsExtensible xmlns:mc="{MC}" xmlns:w16cex="{W16CEX}" '
            f'mc:Ignorable="w16cex">{itens}</w16cex:commentsExtensible>').encode("utf-8")
        rels.append(("rIdC4", fx_com.RT_EXTENSIVEL, "commentsExtensible.xml"))
        tipos.append(("/word/commentsExtensible.xml", fx_com.CT_EXTENSIVEL))
    if pessoas is not None:
        itens = "".join(f'<w15:person w15:author="{a}"><w15:presenceInfo w15:providerId="AD" '
                        f'w15:userId="S::{a.lower()}@exemplo"/></w15:person>' for a in pessoas)
        partes["word/people.xml"] = (f'<w15:people xmlns:mc="{MC}" xmlns:w15="{W15}" '
                                     f'mc:Ignorable="w15">{itens}</w15:people>').encode("utf-8")
        rels.append(("rIdC5", "http://schemas.microsoft.com/office/2011/relationships/people",
                     "people.xml"))
        tipos.append(("/word/people.xml", fx_com.CT_PESSOAS))
    if rels_comentarios:
        partes["word/_rels/comments.xml.rels"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + rels_comentarios + "</Relationships>").encode("utf-8")
    return fx.docx_com_xml(corpo, partes_extra=partes, relacoes_extra=rels, tipos_extra=tipos)


def simples() -> bytes:
    corpo = f"<w:p>{t('Antes ')}{ini(0)}{t('trecho')}{fim(0)}{ref(0)}{t(' depois do trecho.')}</w:p>"
    return docx_com_comentarios(
        corpo, [comentario(0, "Ana Lima", t("Ver isto"), "10000001", iniciais="AL")],
        estendido=[("10000001", None, 0)], ids=[("10000001", "20000001")],
        extensivel=[("20000001", "2026-06-12T19:45:59.779Z")], pessoas=["Ana Lima", "Ana Lima"])


def resposta_resolvido() -> bytes:
    corpo = (f"<w:p>{t('Inicio ')}{ini(0)}{ini(1)}{t('Nucleo comentado')}{fim(0)}{ref(0)}"
             f"{fim(1)}{ref(1)}{t(' fim.')}</w:p>")
    return docx_com_comentarios(
        corpo, [comentario(0, "Ana Lima", t("Pergunta"), "10000001"),
                comentario(1, "Bruno Reis", t("Resposta"), "10000002", data="2026-06-12T17:06:44")],
        estendido=[("10000001", None, 1), ("10000002", "10000001", 1)],
        ids=[("10000001", "20000001"), ("10000002", "20000002")],
        extensivel=[("20000001", "2026-06-12T19:45:59.779Z"), ("20000002", "2026-06-12T20:06:44.482Z")],
        pessoas=["Bruno Reis", "Ana Lima", "Bruno Reis", "Ana Lima"])


def aninhados() -> bytes:
    corpo = (f"<w:p>{ini(0)}{t('um ')}{ini(1)}{t('dois')}{fim(1)}{ref(1)}{t(' tres')}"
             f"{fim(0)}{ref(0)}{t(' quatro')}</w:p>")
    return docx_com_comentarios(
        corpo, [comentario(0, "Ana", t("fora"), "10000001"), comentario(1, "Bia", t("dentro"), "10000002")],
        estendido=[("10000001", None, 0), ("10000002", None, 0)],
        ids=[("10000001", "20000001"), ("10000002", "20000002")])


def paragrafos() -> bytes:
    corpo = (f"<w:p>{t('a ')}{ini(5)}{t('b')}</w:p><w:p>{t('c')}</w:p>"
             f"<w:p>{t('d')}{fim(5)}{ref(5)}{t(' e')}</w:p>")
    return docx_com_comentarios(corpo, [comentario(5, "Ana", t("tres paragrafos"), "1000000A")],
                                estendido=[("1000000A", None, 0)])


def com_conteudo() -> bytes:
    conteudo = (f'<w:hyperlink r:id="rIdL1"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr>'
                f'<w:t>site</w:t></w:r></w:hyperlink>{t(" e ")}'
                '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> '
                'HYPERLINK "mailto:ana@exemplo"</w:instrText></w:r>'
                '<w:bookmarkStart w:name="_@_MENCAO" w:id="7"/><w:r><w:fldChar w:fldCharType="separate"/>'
                '</w:r><w:bookmarkEnd w:id="7"/><w:r><w:rPr><w:rStyle w:val="Mention"/></w:rPr>'
                '<w:t>@Ana</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>')
    corpo = f"<w:p>{ini(3)}{t('com link')}{fim(3)}{ref(3)}</w:p>"
    rels = ('<Relationship Id="rIdL1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/hyperlink" Target="https://exemplo.org/" TargetMode="External"/>')
    return docx_com_comentarios(corpo, [comentario(3, "Caio", conteudo, "10000003")],
                                estendido=[("10000003", None, 0)], rels_comentarios=rels)


def antigo() -> bytes:
    corpo = f"<w:p>{ini(0)}{t('velho')}{fim(0)}{ref(0)}</w:p>"
    return docx_com_comentarios(corpo, [comentario(0, "Ana", t("sem paraId"), None)])


FIXTURES = {"simples": simples, "resposta_resolvido": resposta_resolvido, "aninhados": aninhados,
            "paragrafos": paragrafos, "com_conteudo": com_conteudo, "antigo": antigo}


def codigos(avisos) -> dict:
    return {a.codigo: a.contagem for a in avisos}


def c14n(dados: bytes) -> bytes:
    return etree.tostring(etree.fromstring(dados), method="c14n")


def ancoras(modelo) -> list:
    return [(r.marca.tipo, r.marca.id) for p in paragrafos_de(modelo.paragrafos) for r in p.runs
            if isinstance(r.marca, MarcaComentario)]


def valido(dados: bytes, modelo) -> list:
    return ordem.validar(fx.partes_de(dados), modelo.estilos.virtuais())


# -- arquivo ------------------------------------------------------------------------------------

def testar_leitura() -> None:
    secao("leitura: comentarios, respostas, resolvido e ancoras, sem aviso")
    for nome, gerar in FIXTURES.items():
        modelo, avisos = ler(gerar())
        checa(avisos == [] and modelo.comentarios is not None,
              f"{nome}: lido sem aviso ({codigos(avisos)})")
    m, _ = ler(simples())
    c = m.comentarios.itens[0]
    checa_igual((c.id, c.autor, c.iniciais, c.data, c.para_id, c.duravel, c.data_utc, c.texto()),
                (0, "Ana Lima", "AL", "2026-06-12T16:45:59", "10000001", "20000001",
                 "2026-06-12T19:45:59.779Z", "Ver isto"), "simples: todos os campos")
    checa_igual(ancoras(m), [("inicio", 0), ("fim", 0), ("referencia", 0)], "simples: as tres ancoras")
    m, _ = ler(resposta_resolvido())
    a, b = m.comentarios.itens
    checa(b.pai == 0 and a.resolvido and b.resolvido, "resposta (paraIdParent) e resolvido (done)")
    m, _ = ler(aninhados())
    checa_igual(ancoras(m), [("inicio", 0), ("inicio", 1), ("fim", 1), ("referencia", 1),
                             ("fim", 0), ("referencia", 0)], "aninhados: a ordem das ancoras")
    m, _ = ler(paragrafos())
    pars = [p for p in paragrafos_de(m.paragrafos)]
    checa(any(isinstance(r.marca, MarcaComentario) and r.marca.tipo == "inicio" for r in pars[0].runs)
          and any(isinstance(r.marca, MarcaComentario) and r.marca.tipo == "fim" for r in pars[2].runs),
          "atravessando paragrafos: o inicio no 1o, o fim no 3o")
    m, _ = ler(com_conteudo())
    c = m.comentarios.itens[0]
    links = [r.link for p in c.paragrafos for r in p.runs if r.link is not None]
    checa(links and links[0].url == "https://exemplo.org/" and c.original is not None
          and c.relacoes and c.relacoes[0][0] == "rIdL1",
          "com link: o destino vem do comments.xml.rels, e o XML de origem fica com a relacao")
    marcas = [r.marca for p in c.paragrafos for r in p.runs if r.marca is not None]
    checa(any(getattr(x, "campo", None) is not None for x in marcas), "o campo do comentario e' lido")


def testar_ida_e_volta() -> None:
    secao("sem mudanca: as cinco partes voltam iguais (c14n)")
    for nome, gerar in FIXTURES.items():
        dados = gerar()
        modelo, _ = ler(dados)
        gravado, avisos = escrever_com_avisos(modelo)
        antes, depois = fx.partes_de(dados), fx.partes_de(gravado)
        iguais = all(c14n(antes[p]) == c14n(depois[p]) for p in PARTES if p in antes)
        if "word/_rels/comments.xml.rels" in antes:
            iguais = iguais and c14n(antes["word/_rels/comments.xml.rels"]) == c14n(
                depois.get("word/_rels/comments.xml.rels", b"<x/>"))
        checa(iguais and not [p for p in PARTES if (p in antes) != (p in depois)],
              f"{nome}: as partes de comentario voltam iguais e nenhuma sobra ou falta")
        checa(avisos == [] and valido(gravado, modelo) == [], f"{nome}: sem aviso e valido")
        conferencia.conferir(gravado, modelo)
        relido, av = ler(gravado)
        checa(av == [] and ancoras(relido) == ancoras(modelo)
              and [c.texto() for c in relido.comentarios.itens] == [c.texto() for c in modelo.comentarios.itens],
              f"{nome}: relido igual")
        checa_igual(escrever(relido), gravado, f"{nome}: idempotente")
    m, _ = ler(com_conteudo())
    c = m.comentarios.itens[0]
    m.comentarios = m.comentarios.com_itens([c, Comentario(
        id=9, autor="Novo", paragrafos=(Paragrafo(runs=[Run("x")]),), data="2026-10-13T10:00:00")])
    for p in paragrafos_de(m.paragrafos):
        p.runs.append(Run(marca=MarcaComentario("referencia", 9)))
    g = escrever(m)
    rels = fx.partes_de(g).get("word/_rels/comments.xml.rels", b"")
    xml = fx.partes_de(g)["word/comments.xml"]
    checa(b"https://exemplo.org/" in rels and b'r:id="rIdL1"' in xml and b"_@_MENCAO" in xml
          and valido(g, m) == [],
          "com outro comentario novo: o de link volta com o XML de origem, o mesmo rId e o marcador")


def _resposta_no_modelo(modelo, pai: int, autor: str) -> int:
    cat = modelo.comentarios
    novo = Comentario(id=cat.proximo_id(), autor=autor, iniciais="X", data="2026-10-13T10:00:00",
                      paragrafos=(Paragrafo(runs=[Run("ok")], estilo="CommentText"),), pai=pai)
    for p in paragrafos_de(modelo.paragrafos):
        for i, r in enumerate(list(p.runs)):
            if isinstance(r.marca, MarcaComentario) and r.marca.id == pai and r.marca.tipo == "referencia":
                p.runs[i + 1:i + 1] = [Run(marca=MarcaComentario("referencia", novo.id))]
                break
    modelo.comentarios = cat.com_itens(cat.itens + [novo])
    return novo.id


def testar_partes_coerentes() -> None:
    secao("criar resposta no modelo: as quatro partes coerentes e o people.xml sem repetir")
    modelo, _ = ler(simples())
    ident = _resposta_no_modelo(modelo, 0, "Rui Novo")
    _resposta_no_modelo(modelo, 0, "Rui Novo")
    gravado, avisos = escrever_com_avisos(modelo)
    partes = fx.partes_de(gravado)
    checa(avisos == [] and valido(gravado, modelo) == [], "gravado sem aviso e valido")
    ext = etree.fromstring(partes["word/commentsExtended.xml"])
    filhos = ext.findall("w15:commentEx", NS)
    checa(len(filhos) == 3 and all(f.get("{%s}paraIdParent" % W15) == "10000001" for f in filhos[1:]),
          "commentsExtended: as duas respostas apontam para o paraId do pai")
    ids = etree.fromstring(partes["word/commentsIds.xml"]).findall("{%s}commentId" % W16CID)
    duraveis = [x.get("{%s}durableId" % W16CID) for x in ids]
    checa(len(ids) == 3 and len(set(duraveis)) == 3, "commentsIds: um durableId unico por comentario")
    ext2 = etree.fromstring(partes["word/commentsExtensible.xml"])
    checa_igual(len(ext2), 3, "commentsExtensible: uma data UTC por comentario")
    pessoas = [p.get("{%s}author" % W15) for p in etree.fromstring(partes["word/people.xml"])]
    checa_igual(pessoas, ["Ana Lima", "Ana Lima", "Rui Novo"],
                "people.xml: as repetidas de origem ficam, o autor novo entra uma vez")
    com = etree.fromstring(partes["word/comments.xml"])
    novo_el = com.findall("w:comment", NS)[1]
    checa(novo_el.find(".//w:annotationRef", NS) is not None
          and novo_el.findall(".//w:p", NS)[-1].get("{%s}paraId" % W14),
          "o comentario novo tem o annotationRef e o w14:paraId")
    conferencia.conferir(gravado, modelo)
    relido, _ = ler(gravado)
    checa_igual([(c.id, c.pai) for c in relido.comentarios.itens], [(0, None), (ident, 0), (ident + 1, 0)],
                "relido: as respostas voltam com o pai")
    checa_igual(c14n(partes["word/comments.xml"].split(b"</w:comment>")[0] + b"</w:comment></w:comments>")
                [:10], c14n(fx.partes_de(simples())["word/comments.xml"])[:10],
                "o comentario de origem volta com o XML de origem")

    secao("documento antigo (so' comments.xml): a resposta cria as partes estendidas")
    modelo, _ = ler(antigo())
    _resposta_no_modelo(modelo, 0, "Rui")
    gravado = escrever(modelo)
    partes = fx.partes_de(gravado)
    checa(all(p in partes for p in PARTES[:4]) and valido(gravado, modelo) == [],
          "commentsExtended, commentsIds e commentsExtensible criados, e valido")
    com = etree.fromstring(partes["word/comments.xml"])
    checa(all(c.findall(".//w:p", NS)[-1].get("{%s}paraId" % W14) for c in com.findall("w:comment", NS)),
          "o comentario de origem ganha o w14:paraId")
    relido, _ = ler(gravado)
    checa_igual([c.pai for c in relido.comentarios.itens], [None, 0], "a resposta e' reconhecida")


def testar_equilibrar() -> None:
    secao("gravar sempre XML valido: ancoras incoerentes")
    modelo, _ = ler(simples())
    for p in paragrafos_de(modelo.paragrafos):
        p.runs = [r for r in p.runs if not (isinstance(r.marca, MarcaComentario)
                                            and r.marca.tipo == "referencia")]
    gravado, avisos = escrever_com_avisos(modelo)
    checa(codigos(avisos).get("COMENTARIO_INCOMPLETO") == 1 and "word/comments.xml" not in fx.partes_de(gravado)
          and valido(gravado, modelo) == [],
          "sem a referencia: o comentario sai, com aviso COMENTARIO_INCOMPLETO, e o arquivo e' valido")
    conferencia.conferir(gravado, modelo)
    modelo, _ = ler(simples())
    for p in paragrafos_de(modelo.paragrafos):
        p.runs = [r for r in p.runs if not (isinstance(r.marca, MarcaComentario) and r.marca.tipo == "fim")]
    gravado, avisos = escrever_com_avisos(modelo)
    raiz = etree.fromstring(fx.partes_de(gravado)["word/document.xml"])
    checa(avisos == [] and raiz.find(".//w:commentRangeEnd", NS) is not None
          and valido(gravado, modelo) == [], "inicio sem fim: o fim entra antes da referencia")
    eq, contagem = mod_marcas.equilibrar(modelo)
    checa_igual(contagem["comentarios"], 0, "equilibrar nao conta perda nesse caso")
    modelo, _ = ler(aninhados())
    p = next(paragrafos_de(modelo.paragrafos))
    p.runs.insert(0, Run(marca=MarcaComentario("referencia", 99)))
    gravado = escrever(modelo)
    checa(b'w:id="99"' not in fx.partes_de(gravado)["word/document.xml"] and valido(gravado, modelo) == [],
          "ancora de comentario que nao existe sai")


def testar_validador() -> None:
    secao("validador: contraprovas")
    base = fx.partes_de(escrever(ler(resposta_resolvido())[0]))
    checa_igual(fx_com.validar(base), [], "o arquivo bom passa")
    sab = dict(base)
    sab["word/document.xml"] = base["word/document.xml"].replace(
        b'<w:commentReference w:id="1"/>', b'<w:commentReference w:id="9"/>')
    problemas = fx_com.validar(sab)
    checa(any("9" in x for x in problemas) and any("sem commentReference" in x for x in problemas),
          "ancora com id inexistente e comentario sem referencia sao acusados")
    sab = dict(base)
    doc = base["word/document.xml"].decode("utf-8")
    doc = doc.replace('<w:commentRangeStart w:id="0"/>', "", 1).replace(
        '<w:commentRangeEnd w:id="0"/>', '<w:commentRangeEnd w:id="0"/><w:commentRangeStart w:id="0"/>', 1)
    sab["word/document.xml"] = doc.encode("utf-8")
    checa(any("antes do commentRangeStart" in x for x in fx_com.validar(sab)), "fim antes do inicio e' acusado")
    sab = dict(base)
    sab["word/commentsExtended.xml"] = base["word/commentsExtended.xml"].replace(b"10000002", b"0BADBAD0")
    checa(any("paraId 0BADBAD0" in x for x in fx_com.validar(sab)), "paraId sem paragrafo e' acusado")
    sab = dict(base)
    sab["word/commentsIds.xml"] = base["word/commentsIds.xml"].replace(b"20000002", b"20000001")
    checa(any("repetido" in x for x in fx_com.validar(sab)), "durableId repetido e' acusado")
    sab = dict(base)
    del sab["word/comments.xml"]
    checa(any("sem word/comments.xml" in x for x in fx_com.validar(sab)), "ancora sem comments.xml e' acusada")


def testar_limites() -> None:
    secao("limites contra arquivo hostil")
    dados = resposta_resolvido()
    modelo, avisos = ler(dados, limites={"comentarios": 1})
    checa(modelo.comentarios is None and codigos(avisos).get("COMENTARIO") == 2 and not ancoras(modelo),
          "mais comentarios que o limite: nenhum e' lido, com aviso, e as ancoras saem")
    modelo, avisos = ler(dados, limites={"comentario_bytes": 300})
    checa(codigos(avisos).get("COMENTARIO") == 2, "comentario grande demais: aviso")
    corpo = "<w:p>" + "".join(f"{ini(i)}{t(str(i))}{fim(i)}{ref(i)}" for i in range(6)) + "</w:p>"
    lista = [comentario(i, "A", t(f"c{i}"), f"1000000{i}") for i in range(6)]
    estendido = [(f"1000000{i}", f"1000000{i - 1}" if i else None, 0) for i in range(6)]
    estendido[0] = ("10000000", "10000005", 0)  # ciclo
    modelo, avisos = ler(docx_com_comentarios(corpo, lista, estendido=estendido),
                         limites={"comentario_profundidade": 3})
    pais = {c.id: c.pai for c in modelo.comentarios.itens}
    checa(avisos == [] and any(v is None for v in pais.values()),
          f"resposta em ciclo ou funda demais sobe para o topo ({pais})")
    gravado = escrever(modelo)
    checa_igual(valido(gravado, modelo), [], "e o arquivo gravado e' valido")
    cabecalho = fx.parte_faixa(f"<w:p>{ini(0)}{t('topo')}{fim(0)}{ref(0)}</w:p>")
    corpo = f"<w:p>{t('corpo')}</w:p>"
    dados = docx_com_comentarios(corpo, [comentario(0, "A", t("no cabecalho"), "10000001")])
    partes = fx.partes_de(dados)
    partes["word/header9.xml"] = cabecalho
    partes["word/_rels/document.xml.rels"] = partes["word/_rels/document.xml.rels"].replace(
        b"</Relationships>", f'<Relationship Id="rIdH9" Type="{fx.RT_HEADER}" Target="header9.xml"/>'
        "</Relationships>".encode("utf-8"))
    partes["[Content_Types].xml"] = partes["[Content_Types].xml"].replace(
        b"</Types>", f'<Override PartName="/word/header9.xml" ContentType="{fx.CT_HEADER}"/></Types>'.encode())
    partes["word/document.xml"] = partes["word/document.xml"].replace(
        b"<w:sectPr>", b'<w:sectPr><w:headerReference w:type="default" r:id="rIdH9"/>')
    modelo, avisos = ler(fx.montar(partes))
    checa(codigos(avisos).get("COMENTARIO") == 1 and modelo.comentarios is None,
          "comentario ancorado so' no cabecalho: sai, com aviso (o EditDoc comenta so' o corpo)")


# -- tela ---------------------------------------------------------------------------------------

def _janela(dados: bytes):
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    janela = JanelaPrincipal({**configuracao.padrao(), "nome_usuario": "Revisora Teste",
                              "iniciais": "RT"})
    configuracao.gravar_preferencias({"nome_usuario": "Revisora Teste", "iniciais": "RT"})
    janela.resize(1500, 900)
    janela.show()
    modelo, avisos = ler(dados)
    janela.carregar(modelo, avisos, None)
    janela.painel.setFocus()
    drenar_eventos()
    return janela


def _fechar(janela) -> None:
    janela.painel.documento_corpo().setModified(False)
    janela.close()
    drenar_eventos()


def _selecionar(janela, texto: str, inicio_extra: int = 0, tamanho: int | None = None) -> None:
    from PySide6.QtGui import QTextCursor
    doc = janela.painel.documento_corpo()
    pos = doc.toPlainText().index(texto) + inicio_extra
    c = QTextCursor(doc)
    c.setPosition(pos)
    c.setPosition(pos + (len(texto) - inicio_extra if tamanho is None else tamanho),
                  QTextCursor.MoveMode.KeepAnchor)
    janela.painel.setTextCursor(c)


def _cat(janela):
    from editdoc.edicao import comentarios as ed
    return ed.catalogo(janela.painel)


def _gravar(janela, pasta, nome: str):
    caminho = pasta / nome
    ok = janela._gravar(caminho, trocar=False)
    dados = caminho.read_bytes() if ok else b""
    return ok, dados


def testar_painel() -> None:
    secao("painel: cartoes, clicar seleciona, cursor destaca, nomes acessiveis")
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from editdoc.interface import acessibilidade
    from editdoc.interface.faixa import ABA_REVISAO
    janela = _janela(resposta_resolvido())
    painel = janela.painel_comentarios
    checa(not janela.dock_comentarios.isHidden(), "o painel aparece ao abrir documento com comentarios")
    checa_igual(list(painel.cartoes), [0], "uma conversa (a resposta fica no cartao do pai)")
    cartao = painel.cartoes[0]
    checa(len(cartao.rotulos) == 2 and cartao.resolvido and cartao.estado.text() == "Resolvido",
          "o cartao mostra a resposta e o estado resolvido")
    checa(cartao.accessibleName().startswith("Comentário de Ana Lima") and "resolvido" in cartao.accessibleName(),
          f"o cartao tem nome acessivel ({cartao.accessibleName()})")
    QTest.mouseClick(cartao, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(5, 5))
    drenar_eventos()
    checa_igual(janela.painel.textCursor().selectedText(), "Nucleo comentado",
                "clicar no cartao seleciona o trecho comentado")
    checa_igual(painel.cartao_ativo(), 0, "e o cartao fica destacado")
    _selecionar(janela, "Inicio")
    drenar_eventos()
    checa(painel.cartao_ativo() is None, "fora do trecho, nenhum cartao destacado")
    faltam = acessibilidade.sem_nome(janela)
    checa(not faltam, f"nenhum controle sem nome com o painel aberto ({[type(w).__name__ for w in faltam][:5]})")
    checa(ABA_REVISAO in janela.faixa.abas_visiveis(), "a faixa tem a aba Revisão")
    janela.faixa.abrir_aba(ABA_REVISAO)
    drenar_eventos()
    checa(not acessibilidade.sem_nome(janela.faixa), "a aba Revisão nao tem controle sem nome")
    _fechar(janela)


def testar_comandos(pasta) -> None:
    secao("Ctrl+Alt+M, responder, editar, resolver, excluir e desfazer")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from editdoc.edicao.comentarios import conteudo_de_texto
    janela = _janela(simples())
    painel = janela.painel
    janela._pedir_comentario = lambda *a, **k: conteudo_de_texto("Comentario novo")
    _selecionar(janela, "depois")
    QTest.keyClick(painel, Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
    drenar_eventos()
    cat = _cat(janela)
    novo = cat.itens[-1]
    checa(len(cat.itens) == 2 and novo.autor == "Revisora Teste" and novo.iniciais == "RT"
          and novo.texto() == "Comentario novo", "Ctrl+Alt+M cria o comentario com o autor das Opcoes")
    checa_igual(painel.textCursor().selectedText(), "depois", "o trecho novo fica selecionado")
    checa("T" in novo.data and novo.data_utc and novo.data_utc.endswith("Z"),
          f"data local no w:date e UTC no dateUtc ({novo.data}, {novo.data_utc})")
    QTest.keyClick(painel, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    drenar_eventos()
    checa(len(_cat(janela).itens) == 1 and "￼" * 1 in painel.documento_corpo().toPlainText(),
          "Ctrl+Z desfaz o comentario novo inteiro (ancoras e catalogo)")
    texto_sem = painel.documento_corpo().toPlainText()
    checa_igual(texto_sem.count("￼"), 3, "sobram so' as tres ancoras de origem")

    nova = janela.responder_comentario(0)
    cat = _cat(janela)
    checa(nova is not None and cat.obter(nova).pai == 0, "responder liga a resposta ao pai")
    janela._pedir_comentario = lambda *a, **k: conteudo_de_texto("Texto editado")
    checa(janela.editar_comentario(0) and _cat(janela).obter(0).texto() == "Texto editado",
          "editar troca o texto do comentario")
    checa(janela.resolver_comentario(nova), "resolver a resposta resolve a conversa")
    checa(all(c.resolvido for c in _cat(janela).itens), "pai e resposta resolvidos")
    ok, dados = _gravar(janela, pasta, "comandos.docx")
    modelo, _ = ler(dados)
    est = etree.fromstring(fx.partes_de(dados)["word/commentsExtended.xml"])
    checa(ok and valido(dados, modelo) == [] and all(e.get("{%s}done" % W15) == "1"
                                                     for e in est.findall("w15:commentEx", NS)),
          "gravado: valido, e o commentsExtended com done=1 nos dois")
    pessoas = [p.get("{%s}author" % W15) for p in etree.fromstring(fx.partes_de(dados)["word/people.xml"])]
    checa_igual(pessoas.count("Revisora Teste"), 1, "a autora nova entra uma vez no people.xml")
    painel.undo()
    checa(not any(c.resolvido for c in _cat(janela).itens), "um desfazer volta o resolvido")
    painel.undo()
    checa_igual(_cat(janela).obter(0).texto(), "Ver isto", "um desfazer volta o texto editado")
    janela.resolver_comentario(0)
    checa(janela.excluir_comentario(0) and not _cat(janela).itens
          and "￼" not in painel.documento_corpo().toPlainText(),
          "excluir leva o comentario, a resposta e as ancoras")
    painel.undo()
    checa_igual(len(_cat(janela).itens), 2, "um desfazer devolve o comentario e a resposta")
    checa_igual(janela.excluir_todos_comentarios(), 2, "excluir todos")
    ok, dados = _gravar(janela, pasta, "sem.docx")
    partes = fx.partes_de(dados)
    checa(ok and "word/comments.xml" not in partes and b"commentRangeStart" not in partes["word/document.xml"]
          and valido(dados, ler(dados)[0]) == [], "sem comentarios: nenhuma parte nem ancora sobra")
    _fechar(janela)

    secao("so' leitura com campo; anterior e proximo")
    janela = _janela(com_conteudo())
    vistos = []

    def capturar(titulo, conteudo=(), motivo=""):
        vistos.append(motivo)
        return conteudo_de_texto("tentativa")
    janela._pedir_comentario = capturar
    checa(not janela.editar_comentario(3) and vistos and "campo" in vistos[0],
          "comentario com campo e marcador: o editor abre so' para leitura, com o motivo")
    checa(janela.responder_comentario(3) is not None, "mas responder continua valendo")
    checa(janela.resolver_comentario(3), "e resolver tambem")
    _fechar(janela)
    janela = _janela(aninhados())
    janela.painel.moveCursor(janela.painel.textCursor().MoveOperation.Start)
    janela._comentario_vizinho(True)
    primeiro = janela.painel.textCursor().selectedText()
    janela._comentario_vizinho(True)
    segundo = janela.painel.textCursor().selectedText()
    janela._comentario_vizinho(False)
    checa(primeiro.startswith("um") and segundo == "dois" and
          janela.painel.textCursor().selectedText().startswith("um"),
          f"proximo e anterior andam pelos trechos ({primeiro!r}, {segundo!r})")
    janela.painel.editar_cabecalho = None
    janela.painel.entrar_na_faixa("cabecalho")
    drenar_eventos()
    checa(not janela.comandos.acao("novo_comentario").isEnabled(),
          "no cabecalho, Novo comentario fica desabilitado")
    janela.painel.sair_da_faixa()
    _fechar(janela)


def testar_apagar(pasta) -> None:
    secao("apagar texto como o Word")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    janela = _janela(aninhados())
    painel = janela.painel
    _selecionar(janela, "dois")
    QTest.keyClick(painel, Qt.Key.Key_Delete)
    drenar_eventos()
    checa_igual(_cat(janela).ids(), [0], "apagar todo o texto comentado leva o comentario")
    painel.undo()
    checa_igual(_cat(janela).ids(), [0, 1], "um desfazer devolve o texto e o comentario")
    _selecionar(janela, "um ", 0, 5)  # "um " e o comeco de "dois" (a ponta do inicio do 1)
    QTest.keyClick(painel, Qt.Key.Key_Delete)
    drenar_eventos()
    from editdoc.ponte_qt import comentarios as pq
    doc = painel.documento_corpo()
    t1 = pq.trecho(doc, 1)
    resto = doc.toPlainText()[t1[0]:t1[1]].replace("￼", "") if t1 else None
    checa(_cat(janela).ids() == [0, 1] and resto == "ois",
          f"apagar uma ponta: o comentario fica no que sobrou ({resto!r})")
    ok, dados = _gravar(janela, pasta, "ponta.docx")
    modelo, avisos = ler(dados)
    checa(ok and valido(dados, modelo) == [] and len(modelo.comentarios.itens) == 2,
          "o arquivo gravado e' valido, com os dois comentarios")
    _fechar(janela)

    janela = _janela(simples())
    painel = janela.painel
    _selecionar(janela, "trecho")
    QTest.keyClick(painel, Qt.Key.Key_X)
    drenar_eventos()
    checa(not _cat(janela).itens and "Antes x depois" in painel.documento_corpo().toPlainText(),
          "digitar por cima de todo o trecho comentado tira o comentario")
    painel.undo()
    checa(len(_cat(janela).itens) == 1 and "trecho" in painel.documento_corpo().toPlainText(),
          "um desfazer devolve o texto e o comentario")
    doc = painel.documento_corpo()
    pos = doc.toPlainText().index(" depois")
    from PySide6.QtGui import QTextCursor
    c = QTextCursor(doc)
    c.setPosition(pos)
    painel.setTextCursor(c)
    QTest.keyClick(painel, Qt.Key.Key_Backspace)
    drenar_eventos()
    checa(doc.toPlainText().startswith("Antes ￼trech￼￼ depois")
          and doc.toPlainText().count("￼") == 3,
          "Backspace depois da referencia apaga a letra visivel e pula as ancoras")
    _selecionar(janela, "Antes ", 0, len("Antes ") + 3)
    QTest.keyClick(painel, Qt.Key.Key_Delete)
    drenar_eventos()
    t0 = pq.trecho(doc, 0)
    checa(_cat(janela).ids() == [0] and t0 and doc.toPlainText()[t0[0]:t0[1]] == "ech",
          "apagar o comeco junto com o texto antes: o inicio vai para onde a selecao foi apagada")
    painel.selectAll()
    painel.cut()
    drenar_eventos()
    checa(not _cat(janela).itens, "recortar tudo leva o comentario")
    ok, dados = _gravar(janela, pasta, "vazio.docx")
    checa(ok and valido(dados, ler(dados)[0]) == [], "e o arquivo gravado e' valido")
    _fechar(janela)


def testar_realce_e_saidas(pasta) -> None:
    secao("realce so' na tela; PDF e .txt sem comentarios")
    from PySide6.QtGui import QImage, QPainter, QTransform
    from editdoc.interface.vista_paginas import desenhar_folha
    from editdoc.modelo.texto_plano import texto_do_documento
    from editdoc.ponte_qt import de_qt
    janela = _janela(simples())
    layout = janela.painel.layout_pag

    def amostra(comentarios: bool) -> set:
        img = QImage(800, 300, QImage.Format.Format_RGB32)
        img.fill(0xFFFFFF)
        p = QPainter(img)
        t_ = QTransform().scale(800 / layout.pagina.largura_tw, 800 / layout.pagina.largura_tw)
        desenhar_folha(p, layout, 0, t_, comentarios=comentarios)
        p.end()
        return {img.pixelColor(x, y).name() for x in range(0, 800, 2) for y in range(0, 300, 2)}
    com, sem = amostra(True), amostra(False)
    checa("#fff19c" in com and "#fff19c" not in sem,
          "o amarelo do trecho comentado aparece na tela e nao na impressao/PDF")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from editdoc.ponte_qt import comentarios as pq
    doc = janela.painel.documento_corpo()
    antes = pq.ancoras(doc)
    janela.painel.moveCursor(janela.painel.textCursor().MoveOperation.Start)
    for tecla in (Qt.Key.Key_A, Qt.Key.Key_B, Qt.Key.Key_Backspace):
        QTest.keyClick(janela.painel, tecla)
    depois = pq.ancoras(doc)
    checa(depois == pq.ancoras(doc, True) and [p for p, _m in depois] == [p + 1 for p, _m in antes],
          "digitar antes do trecho: as ancoras em cache andam junto, sem varrer o documento")
    texto = texto_do_documento(de_qt.extrair(janela.painel.documento_corpo()))
    checa("trecho" in texto and "Ver isto" not in texto and "￼" not in texto,
          "o .txt leva o texto, sem os comentarios e sem as ancoras")
    _fechar(janela)


def testar_opcoes() -> None:
    secao("Opcoes: nome de usuario e iniciais")
    from editdoc import configuracao
    from editdoc.edicao.comentarios import autor_das_preferencias, nome_do_windows
    from editdoc.interface.dialogo_opcoes import DialogoOpcoes
    checa_igual(autor_das_preferencias({"nome_usuario": "Maria da Silva", "iniciais": ""}),
                ("Maria da Silva", "MDS"), "sem iniciais: as do nome")
    checa_igual(autor_das_preferencias({})[0], nome_do_windows(), "vazio: o usuario do Windows")
    checa_igual(configuracao.validar({"nome_usuario": "x" * 300})["nome_usuario"], "",
                "nome grande demais volta ao padrao")
    dialogo = DialogoOpcoes(configuracao.padrao())
    dialogo.nome_usuario.setText("  Joana   Prado ")
    dialogo.iniciais.setText("JP")
    valores = dialogo.valores()
    checa(valores["nome_usuario"] == "Joana Prado" and valores["iniciais"] == "JP",
          "o dialogo devolve o nome e as iniciais")
    checa(dialogo.nome_usuario.placeholderText() == nome_do_windows(),
          "o campo vazio mostra o nome do Windows")
    dialogo.deleteLater()


def main() -> int:
    if not QT:
        return pular("PySide6 nao instalado")
    from ajudantes import pasta_temporaria
    testar_leitura()
    testar_ida_e_volta()
    testar_partes_coerentes()
    testar_equilibrar()
    testar_validador()
    testar_limites()
    testar_opcoes()
    with pasta_temporaria() as pasta:
        testar_painel()
        testar_comandos(pasta)
        testar_apagar(pasta)
        testar_realce_e_saidas(pasta)
    drenar_eventos()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
