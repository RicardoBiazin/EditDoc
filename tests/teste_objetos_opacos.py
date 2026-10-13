"""Objetos opacos (0.1.2): caixa de texto, forma, grafico, SmartArt, OLE, imagem flutuante e
equacao voltam ao arquivo como vieram, e na tela sao um marcador que se apaga inteiro.

- leitura: cada tipo vira objeto, no lugar, com o aviso sem perda; o texto em volta fica;
- ida e volta: o XML de cada objeto sai igual (comparado em C14N, com o rId trocado pelo
  conteudo que ele aponta), com as partes (grafico, planilha, estilo, SmartArt, EMF, OLE),
  as relacoes, os tipos de conteudo, o hiperlink da caixa e o relId do SmartArt; a
  gravacao e' idempotente e passa no validador; a conferencia acusa uma parte trocada;
- ids repetidos entre objetos (docPr, paraId, anchorId) sao trocados no segundo, e o
  Choice e o Fallback continuam com o mesmo id;
- limites e arquivo hostil: objeto acima do limite, relacao quebrada, parte proibida e
  ciclo de relacoes viram aviso com perda, sem erro e sem travar; nota e lista dentro da
  caixa saem com aviso;
- tela: o marcador aparece, digitar em volta e logo depois do objeto nao o estraga,
  Delete e Backspace apagam o objeto inteiro (e as partes dele saem do arquivo, sem orfas),
  Ctrl+Z traz de volta; copiar e colar nao leva o objeto nem deixa lixo;
- janela: o aviso novo diz "preservadas", e salvar nao pede a confirmacao de perda.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import posixpath
import time
import zipfile

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt, pular,
                       resumir, secao)
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import avisos as mod_avisos  # noqa: E402
from editdoc.formato_docx import conferencia, opacos, ordem  # noqa: E402
from editdoc.formato_docx.escritor import escrever, escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo.documento import (CARACTERE_OBJETO, Documento, Paragrafo, Run,  # noqa: E402
                                      objetos_de, paragrafos_de)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
PKG_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
DSP = "http://schemas.microsoft.com/office/drawing/2008/diagram"
_ITENS = {f"{{{W}}}drawing", f"{{{W}}}pict", f"{{{W}}}object", f"{{{MC}}}AlternateContent"}
_EQUACOES = {f"{{{M}}}oMath", f"{{{M}}}oMathPara"}
LIMITE_S = 2.0


def sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()[:16]


def codigos(avisos) -> dict[str, tuple[int, bool]]:
    return {a.codigo: (a.contagem, a.perde_ao_salvar) for a in avisos}


def relacoes(partes: dict, parte: str) -> dict:
    """rId -> (tipo, alvo resolvido, externo) de uma parte."""
    nome = posixpath.join(posixpath.dirname(parte), "_rels", posixpath.basename(parte) + ".rels")
    if nome not in partes:
        return {}
    saida = {}
    for rel in etree.fromstring(partes[nome]):
        externo = rel.get("TargetMode") == "External"
        alvo = rel.get("Target")
        if not externo:
            alvo = posixpath.normpath(posixpath.join(posixpath.dirname(parte), alvo))
        saida[rel.get("Id")] = (rel.get("Type"), alvo, externo)
    return saida


def tipos_de_conteudo(partes: dict) -> dict:
    ct = etree.fromstring(partes["[Content_Types].xml"])
    padroes = {d.get("Extension").lower(): d.get("ContentType") for d in ct.iter(f"{{{PKG_CT}}}Default")}
    saida = {}
    for nome in partes:
        ext = nome.rsplit(".", 1)[-1].lower()
        saida[nome] = padroes.get(ext)
    for o in ct.iter(f"{{{PKG_CT}}}Override"):
        saida[o.get("PartName").lstrip("/")] = o.get("ContentType")
    return saida


def _conteudo(partes: dict, alvo: str, vistos: frozenset = frozenset()) -> str:
    """O conteudo de uma parte e, recursivamente, o das partes que ela usa.

    Na parte de dados do SmartArt o relId do dataModelExt aponta para uma relacao do
    documento, que o escritor renumera de proposito: ele entra mascarado (o teste de ida
    e volta confere a parte, pela relacao nova, em separado)."""
    if alvo in vistos:
        return "ciclo"
    dados = partes.get(alvo, b"ausente")
    if b"dataModelExt" in dados:
        raiz = etree.fromstring(dados)
        for x in raiz.iter(f"{{{DSP}}}dataModelExt"):
            x.set("relId", "")
        dados = etree.tostring(raiz, method="c14n")
    filhos = sorted((rid, t, a if e else _conteudo(partes, a, vistos | {alvo}))
                    for rid, (t, a, e) in relacoes(partes, alvo).items())
    return sha(dados + repr(filhos).encode())


def objetos_no_xml(partes: dict, parte: str) -> list[str]:
    """C14N de cada objeto da parte (w:r com desenho, VML, OLE ou AlternateContent, e a
    equacao), com cada r:id trocado pelo tipo e pelo conteudo que ele aponta."""
    raiz = etree.fromstring(partes[parte])
    rels = relacoes(partes, parte)
    dentro = ordem.dentro_de_opacos(raiz)
    saida = []
    for el in raiz.iter():
        pai = el.getparent()
        if pai is None or pai.tag != f"{{{W}}}p" or pai in dentro:
            continue  # so' o que esta' direto num paragrafo do EditDoc (nao o de dentro da caixa)
        if el.tag == f"{{{W}}}r" and any(f.tag in _ITENS for f in el):
            if any((d.get("name") or "").startswith("Imagem ") for d in el.iter(f"{{{WP}}}docPr")):
                continue  # imagem na linha do proprio EditDoc: o escritor a refaz (M4)
            alvo = el
        elif el.tag in _EQUACOES:
            alvo = el
        else:
            continue
        copia = etree.fromstring(etree.tostring(alvo))
        for x in copia.iter():
            for chave, valor in list(x.attrib.items()):
                if chave.startswith(f"{{{R}}}"):
                    tipo, destino, externo = rels.get(valor, ("?", "?", True))
                    x.set(chave, f"{tipo}|" + (destino if externo else _conteudo(partes, destino)))
        saida.append(etree.tostring(copia, method="c14n", exclusive=True).decode("utf-8"))
    return saida


def assinaturas(modelo) -> list[str]:
    return [opacos.assinatura(o) for o in objetos_de(modelo)]


# -- leitura ----------------------------------------------------------------------------

def testar_leitura() -> None:
    secao("leitura: cada objeto no lugar, com o aviso sem perda, e o texto em volta fica")
    modelo, avisos = ler(fx.docx_com_objetos())
    objetos = list(objetos_de(modelo))
    checa_igual([(o.tipo, o.flutuante) for o in objetos], fx.OBJETOS_ESPERADOS,
                "caixa, linha, grupo, grafico, imagem flutuante, OLE, SmartArt, vinculada, "
                "duas equacoes e o retangulo do cabecalho, na ordem")
    checa_igual(codigos(avisos), {"CAIXA_DE_TEXTO": (4, False), "OBJETO": (3, False),
                                  "IMAGEM_FLUTUANTE": (1, False), "IMAGEM_FORMATO": (1, False),
                                  "EQUACAO": (2, False)},
                "avisos por tipo, todos sem perda ao salvar")
    primeiro = modelo.paragrafos[0]
    checa_igual("".join(r.texto for r in primeiro.runs),
                f"Antes da caixa {CARACTERE_OBJETO} depois da caixa.",
                "o texto em volta da caixa fica, e a caixa ocupa o U+FFFC")
    checa(objetos[0].resumo.startswith("Texto da caixa Segunda linha com link"),
          "o resumo da caixa e' o comeco do texto de dentro (txbxContent)")
    grafico = objetos[3]
    checa_igual(sorted(p.nome for p in grafico.partes),
                ["word/charts/chart1.xml", "word/charts/style1.xml", "word/embeddings/Planilha1.xlsx"],
                "o grafico leva a parte dele, o estilo e a planilha (o fecho das relacoes)")
    smart = objetos[6]
    checa("word/diagrams/drawing1.xml" in {p.nome for p in smart.partes}
          and any(r[1] == fx.RT_DGM_DESENHO for r in smart.relacoes),
          "o SmartArt leva o desenho apontado pelo relId do dataModelExt")
    checa(objetos[4].previa is not None and objetos[5].previa is None,
          "a imagem flutuante tem previa (PNG); o OLE com EMF nao")
    checa(objetos[0].largura_emu == 2743200 and objetos[0].altura_emu == 914400,
          "o tamanho da caixa vem do wp:extent")
    checa(objetos[-1] in list(objetos_de(Documento(cabecalhos=modelo.cabecalhos))),
          "o retangulo VML do cabecalho e' objeto do cabecalho")
    for codigo in ("CAIXA_DE_TEXTO", "OBJETO", "EQUACAO", "IMAGEM_FLUTUANTE", "IMAGEM_FORMATO"):
        texto = mod_avisos.construir(codigo, 6).texto
        checa("preservad" in texto and "sai do arquivo" not in texto and "perde" not in texto
              and not mod_avisos.construir(codigo, 6).perde_ao_salvar,
              f"{codigo}: o texto diz preservado e nao pede confirmacao de perda")
    checa_igual(mod_avisos.construir("CAIXA_DE_TEXTO", 6).texto,
                "6 caixas de texto ou formas são preservadas, mas não podem ser editadas nesta versão.",
                "o texto do aviso das caixas de texto")
    checa(mod_avisos.construir("OBJETO_PERDIDO", 1).perde_ao_salvar,
          "contraprova: o objeto que nao pode ser preservado continua pedindo confirmacao")


# -- ida e volta --------------------------------------------------------------------------

def testar_ida_e_volta() -> None:
    secao("ida e volta: XML igual em C14N, partes, relacoes, tipos, idempotencia e validador")
    origem = fx.docx_com_objetos()
    partes_origem = fx.partes_de(origem)
    modelo, _ = ler(origem)
    saida, avisos_gravacao = escrever_com_avisos(modelo)
    partes = fx.partes_de(saida)
    checa_igual(ordem.validar(partes), [], "o arquivo gravado passa no validador (sem parte orfa)")
    checa_igual(avisos_gravacao, [], "a gravacao nao gera aviso")
    for parte in ("word/document.xml", "word/header1.xml"):
        antes, depois = objetos_no_xml(partes_origem, parte), objetos_no_xml(partes, parte)
        checa(antes and antes == depois,
              f"{parte}: o XML de cada objeto sai igual em C14N ({len(depois)} objetos)")
    raiz = etree.fromstring(partes["word/document.xml"])
    checa_igual(raiz.get(f"{{{MC}}}Ignorable"), "w14 wp14",
                "a raiz declara o mc:Ignorable de origem (o w14:paraId da caixa precisa dele)")
    rels = relacoes(partes, "word/document.xml")
    tipos = tipos_de_conteudo(partes)
    graficos = [a for t, a, e in rels.values() if t == fx.RT_GRAFICO]
    checa(len(graficos) == 1 and partes.get(graficos[0]) == fx.GRAFICO_XML
          and tipos.get(graficos[0]) == fx.CT_GRAFICO,
          "o grafico volta com os mesmos bytes e o tipo de conteudo dele")
    sub = relacoes(partes, graficos[0]) if graficos else {}
    checa(sorted((t, partes.get(a)) for t, a, _e in sub.values())
          == sorted([(fx.RT_PACOTE, fx.PLANILHA), (fx.RT_ESTILO_GRAFICO, fx.ESTILO_GRAFICO)])
          and all(tipos.get(a) for _t, a, _e in sub.values()),
          "a planilha e o estilo do grafico voltam, pelas relacoes do grafico, com tipo")
    dados = [a for t, a, e in rels.values() if t == fx.RT_DGM_DADOS]
    rel_id = None
    if dados:
        ext = next(etree.fromstring(partes[dados[0]]).iter(f"{{{DSP}}}dataModelExt"), None)
        rel_id = ext.get("relId") if ext is not None else None
    checa(rel_id in rels and rels[rel_id][0] == fx.RT_DGM_DESENHO
          and partes.get(rels[rel_id][1]) == fx.DGM_DESENHO,
          "o relId do SmartArt aponta para a relacao nova do documento, e ela para o desenho")
    externos = sorted(a for t, a, e in rels.values() if e)
    checa_igual(externos, ["http://exemplo.invalid/vinculada.png", "https://exemplo.invalid/caixa"],
                "a imagem vinculada e o hiperlink da caixa voltam como relacoes externas")
    ole = [a for t, a, e in rels.values() if t == fx.RT_OLE]
    emf = [a for t, a, e in rels.values() if not e and partes.get(a) == fx.EMF]
    checa(ole and partes.get(ole[0]) == fx.OLE_BIN and tipos.get(ole[0]) == fx.CT_OLE
          and emf and tipos.get(emf[0]) == "image/x-emf",
          "o OLE volta com o binario e a previa EMF, com os tipos de conteudo")
    png = [n for n, d in partes.items() if d == fx.png(40, 20)]
    checa(len(png) == 2 and len(set(png)) == 2,
          "a imagem flutuante e a imagem do EditDoc tinham a mesma parte: saem em duas, sem "
          f"colidir o nome ({png})")
    ids = [d.get("id") for d in raiz.iter(f"{{{WP}}}docPr")]
    checa(len(ids) == len(set(ids)), f"wp:docPr sem id repetido ({ids})")
    relido, avisos = ler(saida)
    checa_igual(assinaturas(relido), assinaturas(modelo), "relido: os mesmos objetos, no mesmo lugar")
    checa(not any(a.perde_ao_salvar for a in avisos), "relido: nenhum aviso com perda")
    checa_igual(escrever(relido), saida, "gravar o relido da' os mesmos bytes (idempotente)")
    conferencia.conferir(saida, modelo)
    checa(True, "a conferencia pos-gravacao aceita o arquivo")

    adulterado = fx.com_parte(saida, graficos[0], fx.GRAFICO_XML.replace(b'val="col"', b'val="bar"'))
    try:
        conferencia.conferir(adulterado, modelo)
        acusou = False
    except conferencia.FalhaDeConferencia as erro:
        acusou = "objeto" in str(erro)
    checa(acusou, "contraprova: a conferencia acusa a parte do grafico trocada no arquivo gravado")
    sem_planilha = {k: v for k, v in partes.items() if not k.endswith(".xlsx")}
    checa(any("inexistente" in p for p in ordem.validar(sem_planilha)),
          "contraprova: o validador acusa a planilha do grafico que falta")
    try:
        conferencia.conferir(fx.montar(sem_planilha), modelo)
        acusou = False
    except conferencia.FalhaDeConferencia:
        acusou = True
    checa(acusou, "contraprova: a conferencia acusa o grafico que perdeu a planilha")


def testar_ids_repetidos() -> None:
    secao("ids repetidos entre objetos: o segundo ganha ids novos, o Choice e o Fallback juntos")
    corpo = ("<w:p>" + fx.caixa_de_texto() + "</w:p><w:p>" + fx.caixa_de_texto() + "</w:p>")
    origem = fx.docx_com_corpo_de_objetos(corpo, [fx.RELACOES_OBJETOS[-1]])
    checa(any("docPr" in p for p in ordem.validar(fx.partes_de(origem))),
          "contraprova: o validador acusa o wp:docPr repetido do arquivo de origem")
    modelo, _ = ler(origem)
    saida = escrever(modelo)
    partes = fx.partes_de(saida)
    checa_igual(ordem.validar(partes), [], "o arquivo gravado passa no validador")
    raiz = etree.fromstring(partes["word/document.xml"])
    ids = [d.get("id") for d in raiz.iter(f"{{{WP}}}docPr")]
    checa(len(ids) == 3 and len(set(ids)) == 3, f"tres wp:docPr, todos diferentes ({ids})")
    alternativas = list(raiz.iter(f"{{{MC}}}AlternateContent"))
    para = [[p.get(f"{{{W14}}}paraId") for p in ac.iter(f"{{{W}}}p")] for ac in alternativas]
    checa(len(para) == 2 and para[0] == ["1A2B3C4D", "1A2B3C4E"] * 2,
          "a primeira caixa fica com os paraIds de origem, no Choice e no Fallback")
    checa(len(para) == 2 and para[1][:2] == para[1][2:] and not set(para[1]) & set(para[0])
          and all(int(x, 16) < 0x80000000 for x in para[1]),
          f"a segunda ganha paraIds novos, iguais no Choice e no Fallback ({para[1] if para else []})")
    ancoras = [ac.find(f".//{{{WP}}}anchor").get("{http://schemas.microsoft.com/office/word/2010/"
                                                  "wordprocessingDrawing}anchorId") for ac in alternativas]
    checa(len(set(ancoras)) == 2, f"anchorId diferente nas duas caixas ({ancoras})")
    relido, _ = ler(saida)
    conferencia.conferir(saida, modelo)
    checa_igual(assinaturas(relido), assinaturas(modelo),
                "a conferencia nao depende dos ids renumerados")


# -- limites e arquivo hostil -----------------------------------------------------------------

def testar_limites() -> None:
    secao("limites e arquivo hostil: perda com aviso, sem erro, sem travar")
    origem = fx.docx_com_objetos()
    modelo, avisos = ler(origem, {"opacos": 3})
    checa(len(list(objetos_de(modelo))) == 3 and codigos(avisos).get("OBJETO_PERDIDO", (0, False))[1],
          "acima do limite de objetos: os 3 primeiros ficam, o resto vira OBJETO_PERDIDO com perda")
    checa_igual(ordem.validar(fx.partes_de(escrever(modelo))), [],
                "o arquivo sem os objetos que passaram do limite e' valido")
    modelo, avisos = ler(origem, {"opaco_bytes": 600})
    checa(not list(objetos_de(modelo)) and "OBJETO_PERDIDO" in codigos(avisos)
          and "IMAGEM" in codigos(avisos),
          "XML do objeto acima do limite: nada preservado, aviso com perda (IMAGEM para a imagem)")
    modelo, avisos = ler(origem, {"opaco_partes": 2})
    tipos = [o.tipo for o in objetos_de(modelo)]
    checa("grafico" not in tipos and "smartart" not in tipos and "caixa_de_texto" in tipos,
          "fecho de partes acima do limite: grafico e SmartArt nao vao; a caixa vai")

    quebrado = fx.docx_com_corpo_de_objetos("<w:p><w:r><w:t>a</w:t></w:r>" + fx.grafico(rid="rId99")
                                            + "<w:r><w:t>b</w:t></w:r></w:p>")
    modelo, avisos = ler(quebrado)
    checa(not list(objetos_de(modelo)) and codigos(avisos).get("OBJETO_PERDIDO") == (1, True)
          and "".join(r.texto for r in modelo.paragrafos[0].runs) == "ab",
          "grafico com r:id sem relacao: OBJETO_PERDIDO com perda, o texto fica")
    checa_igual(ordem.validar(fx.partes_de(escrever(modelo))), [], "e o arquivo gravado e' valido")

    proibido = fx.docx_com_corpo_de_objetos(
        "<w:p>" + fx.grafico() + "</w:p>", [("rId50", fx.RT_GRAFICO, "styles.xml")])
    modelo, avisos = ler(proibido)
    checa(not list(objetos_de(modelo)) and "OBJETO_PERDIDO" in codigos(avisos),
          "objeto que aponta para o styles.xml nao leva a parte junto (nao e' preservado)")
    sem_tipo = fx.docx_com_corpo_de_objetos(
        "<w:p>" + fx.grafico() + "</w:p>", [("rId50", fx.RT_GRAFICO, "charts/chart1.qqq")],
        {"word/charts/chart1.qqq": fx.GRAFICO_XML})
    modelo, avisos = ler(sem_tipo)
    checa(not list(objetos_de(modelo)) and "OBJETO_PERDIDO" in codigos(avisos),
          "parte sem tipo de conteudo: objeto nao preservado, com aviso")

    ciclo_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
                  f'xmlns="{PKG_REL}"><Relationship Id="rId1" Type="{fx.RT_PACOTE}" '
                  'Target="chart1.xml"/></Relationships>').encode("utf-8")
    ciclo = fx.docx_com_corpo_de_objetos(
        "<w:p>" + fx.grafico() + "</w:p>", [fx.RELACOES_OBJETOS[0]],
        {"word/charts/chart1.xml": fx.GRAFICO_XML, "word/charts/_rels/chart1.xml.rels": ciclo_rels},
        [fx.TIPOS_OBJETOS[0]])
    inicio = time.perf_counter()
    modelo, _ = ler(ciclo)
    saida = escrever(modelo)
    checa(len(list(objetos_de(modelo))) == 1 and time.perf_counter() - inicio < LIMITE_S
          and ordem.validar(fx.partes_de(saida)) == [],
          "grafico que aponta para si mesmo: preservado, sem laco infinito, arquivo valido")

    nota = fx.caixa_de_texto(extra='<w:r><w:footnoteReference w:id="1"/></w:r>'
                                   '<w:commentRangeStart w:id="0"/><w:r><w:commentReference w:id="0"/></w:r>')
    modelo, avisos = ler(fx.docx_com_corpo_de_objetos("<w:p>" + nota + "</w:p>", [fx.RELACOES_OBJETOS[-1]]))
    obj = next(objetos_de(modelo), None)
    checa(obj is not None and b"footnoteReference" not in obj.xml and b"comment" not in obj.xml
          and codigos(avisos).get("NOTA") == (2, True) and codigos(avisos).get("COMENTARIO") == (2, True),
          "nota e comentario dentro da caixa: a referencia sai (com aviso), a caixa fica")
    lista = fx.caixa_de_texto(extra='<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="7"/>'
                                    '</w:numPr></w:pPr>')
    com_lista = fx.docx_com_corpo_de_objetos("<w:p>" + lista + "</w:p>", [fx.RELACOES_OBJETOS[-1]])
    modelo, avisos = ler(com_lista)
    obj = next(objetos_de(modelo), None)
    checa(obj is not None and b"numPr" in obj.xml and "LISTA_EM_CAIXA" not in codigos(avisos),
          "numPr dentro da caixa (0.1.4: o numbering.xml de origem volta inteiro): fica, sem aviso")
    # Reescrita na 0.1.4: antes o numPr sempre saia. Agora so' sai quando a numeracao do
    # arquivo nao pode ser lida (aqui, acima do limite de definicoes).
    modelo, avisos = ler(com_lista, limites={"listas_abstratas": -1})
    obj = next(objetos_de(modelo), None)
    checa(obj is not None and b"numPr" not in obj.xml and codigos(avisos).get("LISTA_EM_CAIXA", (0,))[0] == 2,
          "numPr dentro da caixa com a numeracao ilegivel (limite): sai, com aviso")

    estrangeiro = fx.caixa_de_texto().replace(
        "<w:rPr><w:noProof/></w:rPr><mc:AlternateContent",
        '<w:rPr><w:noProof/><w14:ligatures w14:val="standard"/></w:rPr><mc:AlternateContent', 1)
    modelo, _ = ler(fx.docx_com_corpo_de_objetos("<w:p>" + estrangeiro + "</w:p>", [fx.RELACOES_OBJETOS[-1]]))
    obj = next(objetos_de(modelo), None)
    partes = fx.partes_de(escrever(modelo))
    checa(obj is not None and b"ligatures" in obj.xml and ordem.validar(partes) == [],
          "rPr do run do objeto com filho w14: volta como veio, e o validador aceita")
    checa(any("filho desconhecido" in p for p in ordem.validar_ordem(
        etree.fromstring(f'<w:r xmlns:w="{W}" xmlns:w14="{W14}"><w:rPr><w14:ligatures/></w:rPr></w:r>'))),
          "contraprova: o mesmo rPr num run comum do EditDoc e' recusado")

    muitos = "".join(f"<w:p>{fx.caixa_de_texto(ident=1000 + i)}</w:p>" for i in range(300))
    dados = fx.docx_com_corpo_de_objetos(muitos, [fx.RELACOES_OBJETOS[-1]])
    inicio = time.perf_counter()
    modelo, _ = ler(dados)
    saida = escrever(modelo)
    conferencia.conferir(saida, modelo)
    gasto = time.perf_counter() - inicio
    checa(len(list(objetos_de(modelo))) == 300 and gasto < 10,
          f"300 caixas de texto: ler, gravar e conferir em {gasto:.1f} s (limite 10 s)")


# -- tela ------------------------------------------------------------------------------------

def _painel():
    from editdoc.interface.painel_documento import PainelDocumento
    painel = PainelDocumento("Calibri", 11)
    painel.resize(1000, 800)
    painel.show()
    drenar_eventos(2)
    painel.setFocus()
    return painel


def _modelo(painel):
    from editdoc.ponte_qt import de_qt
    return de_qt.extrair(painel.documento_corpo())


def _contar_cor(img, cor: tuple[int, int, int]) -> int:
    n = 0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = img.pixelColor(x, y)
            if abs(c.red() - cor[0]) < 4 and abs(c.green() - cor[1]) < 4 and abs(c.blue() - cor[2]) < 4:
                n += 1
    return n


def testar_tela() -> None:
    secao("tela: marcador, digitar em volta, Delete e Backspace apagam o objeto inteiro")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor
    from PySide6.QtTest import QTest

    from editdoc.ponte_qt import opacos as pq_opacos
    from editdoc.ponte_qt import para_qt

    modelo, _ = ler(fx.docx_com_objetos())
    painel = _painel()
    para_qt.preencher(painel.documento_corpo(), modelo)
    painel.clearFocus()
    drenar_eventos(2)
    fundo = (0xee, 0xf1, 0xf5)
    marcas = _contar_cor(painel.viewport().grab().toImage(), fundo)
    checa(marcas > 50, f"o marcador do objeto aparece na tela ({marcas} pontos)")
    checa_igual(len(pq_opacos.posicoes_de_opacos(painel.documento_corpo())), 10,
                "os 10 objetos do corpo estao no documento do Qt")
    checa_igual(assinaturas(_modelo(painel)), assinaturas(Documento(paragrafos=modelo.paragrafos)),
                "Qt ida e volta: os mesmos objetos")

    painel.setFocus()
    cursor = painel.textCursor()
    cursor.setPosition(0)
    painel.setTextCursor(cursor)
    QTest.keyClick(painel, Qt.Key.Key_X)
    pos = pq_opacos.posicoes_de_opacos(painel.documento_corpo())[0]
    cursor.setPosition(pos + 1)
    painel.setTextCursor(cursor)
    QTest.keyClick(painel, Qt.Key.Key_A)
    QTest.keyClick(painel, Qt.Key.Key_B)
    editado = _modelo(painel)
    checa_igual("".join(r.texto for r in editado.paragrafos[0].runs),
                f"xAntes da caixa {CARACTERE_OBJETO}ab depois da caixa.",
                "digitar antes e logo depois da caixa: o texto entra em volta")
    checa_igual(assinaturas(editado), assinaturas(Documento(paragrafos=modelo.paragrafos)),
                "o texto digitado logo depois do objeto nao vira objeto e nao estraga nenhum")
    saida = escrever(editado)
    checa(ordem.validar(fx.partes_de(saida)) == [] and objetos_no_xml(fx.partes_de(saida), "word/document.xml")
          == objetos_no_xml(fx.partes_de(fx.docx_com_objetos()), "word/document.xml"),
          "gravado depois da edicao: valido, e o XML dos objetos igual ao de origem")

    grafico = pq_opacos.posicoes_de_opacos(painel.documento_corpo())[3]
    cursor.setPosition(grafico)
    painel.setTextCursor(cursor)
    QTest.keyClick(painel, Qt.Key.Key_Delete)
    sem_grafico = _modelo(painel)
    checa_igual([o.tipo for o in objetos_de(sem_grafico)].count("grafico"), 0,
                "Delete antes do grafico apaga o grafico inteiro")
    checa_igual(len(list(objetos_de(sem_grafico))), 9, "e so' ele")
    partes = fx.partes_de(escrever(sem_grafico))
    checa(ordem.validar(partes) == [] and not any("chart" in n or n.endswith(".xlsx") for n in partes),
          "sem o grafico, as partes dele saem do arquivo (sem parte orfa: o validador passa)")
    painel.undo()
    checa_igual([o.tipo for o in objetos_de(_modelo(painel))].count("grafico"), 1,
                "desfazer traz o grafico de volta")
    partes = fx.partes_de(escrever(_modelo(painel)))
    checa(any(d == fx.GRAFICO_XML for d in partes.values()) and ordem.validar(partes) == [],
          "e o grafico desfeito volta ao arquivo com a parte dele")

    smart = pq_opacos.posicoes_de_opacos(painel.documento_corpo())[6]
    cursor.setPosition(smart + 1)
    painel.setTextCursor(cursor)
    QTest.keyClick(painel, Qt.Key.Key_Backspace)
    checa_igual([o.tipo for o in objetos_de(_modelo(painel))].count("smartart"), 0,
                "Backspace depois do SmartArt apaga o SmartArt inteiro")
    partes = fx.partes_de(escrever(_modelo(painel)))
    checa(ordem.validar(partes) == [] and not any("diagrams" in n for n in partes),
          "as partes do SmartArt (dados, layout, estilo, cores, desenho) saem junto")

    painel.selectAll()
    painel.copy()
    from PySide6.QtWidgets import QApplication
    md = QApplication.clipboard().mimeData()
    checa(CARACTERE_OBJETO not in md.text() and md.hasFormat("application/x-editdoc-objetos-omitidos"),
          "copiar: o texto vai sem o caractere de objeto, com a marca dos objetos que ficaram fora")
    mensagens = []
    painel.mensagem.connect(mensagens.append)
    antes = len(pq_opacos.posicoes_de_opacos(painel.documento_corpo()))
    painel.moveCursor(QTextCursor.MoveOperation.End)
    painel.paste()
    colado = _modelo(painel)
    checa_igual(len(pq_opacos.posicoes_de_opacos(painel.documento_corpo())), antes,
                "colar nao duplica o objeto (ele fica fora do que se cola)")
    checa(colado.paragrafos and not any(r.texto == CARACTERE_OBJETO and not r.eh_objeto()
                                        for p in paragrafos_de(colado.paragrafos) for r in p.runs)
          and "Fim do documento." in "".join(r.texto for r in colado.paragrafos[-1].runs),
          "o texto colado entra sem lixo no lugar do objeto")
    checa(mensagens and "não são copiados" in mensagens[0], "e a barra de status avisa")
    partes = fx.partes_de(escrever(colado))
    checa_igual(ordem.validar(partes), [], "o documento com o texto colado grava valido")
    QApplication.clipboard().clear()
    painel.document().setModified(False)
    painel.close()


# -- janela ------------------------------------------------------------------------------

@contextlib.contextmanager
def dialogos(**substitutos):
    from editdoc.interface import dialogos_modais
    originais = {nome: getattr(dialogos_modais, nome) for nome in substitutos}
    for nome, funcao in substitutos.items():
        setattr(dialogos_modais, nome, funcao)
    try:
        yield
    finally:
        for nome, funcao in originais.items():
            setattr(dialogos_modais, nome, funcao)


def proibido(nome: str):
    def _falha(*_a, **_k):
        raise AssertionError(f"dialogo inesperado: {nome}")
    return _falha


def testar_janela() -> None:
    secao("janela: aviso novo, salvar sem confirmar perda, apagar e desfazer pelo teclado")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from editdoc import configuracao
    from editdoc.interface.gerente import GerenteDeJanelas
    from editdoc.ponte_qt import opacos as pq_opacos

    with pasta_temporaria() as tmp:
        arquivo = tmp / "objetos.docx"
        arquivo.write_bytes(fx.docx_com_objetos())
        original, _ = ler(arquivo.read_bytes())
        gerente = GerenteDeJanelas(configuracao.padrao())
        with dialogos(avisar=proibido("avisar")):
            janela = gerente.abrir(str(arquivo))
        texto = janela.barra_aviso.texto_completo()
        checa("4 caixas de texto ou formas são preservadas, mas não podem ser editadas nesta versão."
              in texto and "sai do arquivo" not in texto,
              "a barra diz que as caixas sao preservadas, e nao que saem do arquivo")
        painel = janela.painel
        painel.setFocus()
        cursor = painel.textCursor()
        cursor.setPosition(pq_opacos.posicoes_de_opacos(painel.documento_corpo())[0])
        painel.setTextCursor(cursor)
        QTest.keyClick(painel, Qt.Key.Key_Delete)
        checa_igual(len(pq_opacos.posicoes_de_opacos(painel.documento_corpo())), 9,
                    "Delete na janela apaga a caixa de texto")
        QTest.keyClick(painel, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        checa_igual(len(pq_opacos.posicoes_de_opacos(painel.documento_corpo())), 10,
                    "Ctrl+Z traz a caixa de volta")
        cursor = painel.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        painel.setTextCursor(cursor)
        QTest.keyClick(painel, Qt.Key.Key_Exclam)
        with dialogos(pedir_perda=proibido("pedir_perda"), avisar=proibido("avisar")):
            checa(janela.salvar() is True, "salvar grava sem pedir a confirmacao de perda")
        salvo, avisos = ler(arquivo.read_bytes())
        checa_igual(assinaturas(salvo), assinaturas(original),
                    "o arquivo salvo tem todos os objetos, com o mesmo XML e as mesmas partes")
        checa(not any(a.perde_ao_salvar for a in avisos), "e reabre sem aviso de perda")
        checa_igual(ordem.validar(fx.partes_de(arquivo.read_bytes())), [], "e passa no validador")
        with dialogos(pedir_descartar=lambda *_a: "descartar"):
            for j in gerente.janelas():
                j.close()
        drenar_eventos()


def main() -> int:
    testar_leitura()
    testar_ida_e_volta()
    testar_ids_repetidos()
    testar_limites()
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    testar_tela()
    testar_janela()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
