"""Controle de alteracoes (0.1.13): arquivo, validador, limites, tela, modos, edicao, aceitar e
rejeitar, desfazer, PDF, copiar, localizar, contar, .txt, comentarios e notas.

Fixtures geradas aqui (nenhum documento real): insercao e exclusao de dois autores, insercao
apagada por outro autor (w:ins com w:del dentro), formatacao alterada (w:rPrChange), propriedades
de paragrafo alteradas (w:pPrChange), marca de paragrafo inserida e excluida, movimento com os
quatro trechos (moveFrom/moveTo e as pontas), campo excluido (w:delInstrText), tabela com linha
inserida e excluida, celula inserida (w:cellIns) e propriedades da tabela alteradas
(w:tblPrChange), revisao da grade (w:tblGridChange), numeracao alterada (w:numberingChange),
revisao das propriedades da secao (w:sectPrChange), cabecalho com insercao, nota de rodape e
comentario com revisao, caixa de texto com revisao (objeto preservado) e o w16du:dateUtc.

- arquivo: ler sem aviso; cada tipo vira o que o modelo diz; gravar e reler da' o mesmo modelo;
  o que nao e' representado volta igual em c14n (sem os w:id, que o escritor numera); a 2a
  gravacao da' os mesmos bytes; w:id unicos e diferentes dos de comentario e marcador;
  w:trackRevisions do settings.xml;
- validador: contraprovas (id repetido, w:t dentro de w:del, w:delText fora, movimento sem par,
  trecho sem fim, id de revisao igual ao de comentario);
- limites: revisoes e autores acima do limite viram o comportamento antigo, com REVISAO;
- tela: os quatro modos (texto do PDF em cada um, largura e visibilidade do paragrafo), a barra
  na margem, o painel de revisoes;
- aceitar e rejeitar cada tipo e o XML resultante; a atual, a selecao, todas, as de um autor;
- edicao com o controle ligado (teclas de verdade): digitar, apagar o proprio e o alheio,
  Delete, Enter, colar, formatar caractere e paragrafo; desfazer volta cada passo; com o
  controle desligado o texto novo nao herda a revisao;
- copiar, localizar, contar palavras e o .txt usam a visao do modo;
- PDF com e sem "Imprimir marcacoes" (comentarios na margem incluidos).
"""

from __future__ import annotations

import re

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt, pular,
                       resumir, secao, usar_fontes_do_documento)
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx import revisoes as fx_rev  # noqa: E402
from editdoc.formato_docx.escritor import escrever, escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo import revisoes as mr  # noqa: E402
from editdoc.modelo.documento import (Documento, MarcaMovimento, Paragrafo, Revisao, Run,  # noqa: E402
                                      normalizar)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W16DU = "http://schemas.microsoft.com/office/word/2023/wordml/word16du"
NS = {"w": W}
A = 'w:author="Ana" w:date="2026-01-02T03:04:05Z"'
B = 'w:author="Beto" w:date="2026-02-03T04:05:06Z"'
DA = "2026-01-02T03:04:05Z"


def t(texto: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{texto}</w:t></w:r>'


def dt(texto: str) -> str:
    return f'<w:r><w:delText xml:space="preserve">{texto}</w:delText></w:r>'


#: Os paragrafos e a tabela da fixture principal (cada um com o seu papel nos testes).
P_INS_DEL = (f'<w:p>{t("Antes ")}<w:ins w:id="1" {A}><w:r><w:rPr><w:b/></w:rPr><w:t>inserido</w:t>'
             f'</w:r></w:ins><w:del w:id="2" {B}>{dt(" apagado")}</w:del>'
             f'<w:ins w:id="3" {A}><w:del w:id="4" {B}>{dt("dupla")}</w:del></w:ins>'
             f'<w:r><w:rPr><w:i/><w:rPrChange w:id="5" {B}><w:rPr><w:b/></w:rPr></w:rPrChange>'
             f'</w:rPr><w:t xml:space="preserve"> formatado</w:t></w:r>{t(" fim1.")}</w:p>')
P_MARCA_INS = (f'<w:p><w:pPr><w:jc w:val="center"/><w:rPr><w:ins w:id="6" {A}/></w:rPr>'
               f'<w:pPrChange w:id="7" {B}><w:pPr><w:jc w:val="left"/></w:pPr></w:pPrChange>'
               f'</w:pPr>{t("Marca inserida")}</w:p>')
P_SEGUE = f'<w:p>{t("Segue a marca.")}</w:p>'
P_MARCA_DEL = (f'<w:p><w:pPr><w:rPr><w:del w:id="8" {B}/></w:rPr></w:pPr>'
               f'<w:del w:id="9" {B}>{dt("Apagado inteiro")}</w:del></w:p>')
P_MOVE_DE = (f'<w:p><w:moveFromRangeStart w:id="10" w:name="move1" {A}/><w:moveFrom w:id="11" {A}>'
             f'{t("Movido")}</w:moveFrom><w:moveFromRangeEnd w:id="10"/>{t(" origem.")}</w:p>')
P_MOVE_PARA = (f'<w:p>{t("Destino: ")}<w:moveToRangeStart w:id="12" w:name="move1" {A}/>'
               f'<w:moveTo w:id="13" {A}>{t("Movido")}</w:moveTo><w:moveToRangeEnd w:id="12"/></w:p>')
P_CAMPO = (f'<w:p>{t("Data: ")}<w:del w:id="14" {B}><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
           '<w:r><w:delInstrText xml:space="preserve"> DATE </w:delInstrText></w:r>'
           f'<w:r><w:fldChar w:fldCharType="separate"/></w:r>{dt("1/1/2026")}'
           '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:del></w:p>')
TABELA = ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:tblPrChange w:id="15" ' + A + '>'
          '<w:tblPr><w:tblW w:w="5000" w:type="dxa"/></w:tblPr></w:tblPrChange></w:tblPr>'
          '<w:tblGrid><w:gridCol w:w="4000"/><w:tblGridChange w:id="22"><w:tblGrid>'
          '<w:gridCol w:w="3000"/></w:tblGrid></w:tblGridChange></w:tblGrid>'
          '<w:tr><w:trPr><w:ins w:id="16" ' + A + '/></w:trPr><w:tc><w:tcPr><w:tcW w:w="4000" '
          'w:type="dxa"/><w:cellIns w:id="17" ' + A + '/></w:tcPr><w:p><w:ins w:id="18" ' + A
          + '>' + t("linha nova") + '</w:ins></w:p></w:tc></w:tr>'
          '<w:tr><w:trPr><w:del w:id="19" ' + B + '/></w:trPr><w:tc><w:tcPr><w:tcW w:w="4000" '
          'w:type="dxa"/></w:tcPr><w:p><w:del w:id="20" ' + B + '>' + dt("linha velha")
          + '</w:del></w:p></w:tc></w:tr>'
          '<w:tr><w:tc><w:tcPr><w:tcW w:w="4000" w:type="dxa"/></w:tcPr><w:p>' + t("linha fixa")
          + '</w:p></w:tc></w:tr></w:tbl>')
P_FIM = (f'<w:p><w:bookmarkStart w:id="0" w:name="marcador"/>{t("Final ")}'
         f'<w:ins w:id="23" {B} w16du:dateUtc="2026-02-03T07:05:06Z" xmlns:w16du="{W16DU}">'
         f'{t("utc")}</w:ins><w:bookmarkEnd w:id="0"/></w:p>')
CORPO = (P_INS_DEL + P_MARCA_INS + P_SEGUE + P_MARCA_DEL + P_MOVE_DE + P_MOVE_PARA + P_CAMPO
         + TABELA + P_FIM)
SECT = f'<w:sectPrChange w:id="21" {A}><w:sectPr><w:pgSz w:w="12240" w:h="15840"/></w:sectPr></w:sectPrChange>'
CABECALHO = f'<w:p>{t("Topo ")}<w:ins w:id="40" {B}>{t("novo no topo")}</w:ins></w:p>'


def docx_principal(controlar: bool = True, cabecalho: bool = True) -> bytes:
    partes_extra = {}
    relacoes, tipos, sect = [], [], ""
    if cabecalho:
        partes_extra["word/header7.xml"] = fx.parte_faixa(CABECALHO)
        relacoes = [("rIdH7", fx.RT_HEADER, "header7.xml")]
        tipos = [("/word/header7.xml", fx.CT_HEADER)]
        sect = '<w:headerReference w:type="default" r:id="rIdH7"/>'
    dados = fx.docx_com_xml(CORPO, sect, partes_extra, relacoes, tipos,
                            settings_extra="<w:trackRevisions/>" if controlar else "")
    partes = fx.partes_de(dados)
    xml = partes["word/document.xml"].decode("utf-8")
    i = xml.rindex("</w:sectPr>")
    partes["word/document.xml"] = (xml[:i] + SECT + xml[i:]).encode("utf-8")
    return fx.montar(partes)


def codigos(avisos) -> dict:
    return {a.codigo: a.contagem for a in avisos}


def corpo_xml(dados: bytes):
    return etree.fromstring(fx.partes_de(dados)["word/document.xml"])


def c14n(el) -> bytes:
    return etree.tostring(el, method="c14n", exclusive=True) if el is not None else b""


def sem_id(el):
    """Copia do elemento sem os w:id das revisoes (o escritor numera de novo)."""
    import copy
    return fx_rev.sem_ids(copy.deepcopy(el))


def origem(xml: str, caminho: str):
    raiz = etree.fromstring(f'<w:body xmlns:w="{W}" xmlns:w16du="{W16DU}" '
                            f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
                            f'relationships">{xml}</w:body>')
    return raiz.findall(caminho, NS)


def ids_de_revisao(partes: dict) -> list[str]:
    saida = []
    for nome, dados in partes.items():
        if not nome.endswith(".xml") or not nome.startswith("word/"):
            continue
        raiz = etree.fromstring(dados)
        for el in raiz.iter():
            if isinstance(el.tag, str) and etree.QName(el).localname in fx_rev.TAGS_REVISAO \
                    and el.tag.startswith("{%s}" % W):
                saida.append(el.get(f"{{{W}}}id"))
    return saida


# -- arquivo ---------------------------------------------------------------------------------

def testar_arquivo() -> None:
    secao("arquivo: cada tipo de revisao lido, gravado e relido igual, sem aviso")
    dados = docx_principal()
    checa_igual(ordem.validar(fx.partes_de(dados)), [], "a fixture e' um .docx valido")
    modelo, avisos = ler(dados)
    checa_igual(codigos(avisos), {}, "ler nao da' aviso nenhum (REVISAO deixou de ser perda)")
    checa(modelo.controlar_alteracoes, "w:trackRevisions vira controlar_alteracoes")
    p0, p1, _p2, p3, p4, p5, p6, tab, p8 = modelo.paragrafos
    runs = {r.texto: r for r in p0.runs}
    checa(runs["inserido"].insercao == Revisao("ins", "Ana", DA) and runs["inserido"].negrito,
          "w:ins: insercao de Ana no run (com a formatacao do run)")
    checa(runs[" apagado"].exclusao is not None and runs[" apagado"].exclusao.autor == "Beto",
          "w:del com w:delText: exclusao de Beto, o texto continua no modelo")
    checa(runs["dupla"].insercao.autor == "Ana" and runs["dupla"].exclusao.autor == "Beto",
          "w:ins com w:del dentro: o trecho tem as duas revisoes")
    checa(runs[" formatado"].mudanca_formato is not None and "<w:b" in runs[" formatado"].mudanca_formato
          and 'w:id=' not in runs[" formatado"].mudanca_formato,
          "w:rPrChange: a formatacao de antes, canonica e sem o w:id")
    checa(p1.marca_insercao is not None and p1.mudanca_formato is not None
          and 'w:jc w:val="left"' in p1.mudanca_formato,
          "marca de paragrafo inserida e w:pPrChange (o alinhamento de antes)")
    checa(p3.marca_exclusao is not None and p3.runs[0].exclusao is not None,
          "paragrafo inteiro excluido: a marca e o texto")
    checa([type(r.marca).__name__ if r.marca else r.texto for r in p4.runs] ==
          ["MarcaMovimento", "Movido", "MarcaMovimento", " origem."]
          and p4.runs[1].exclusao.tipo == "moveFrom" and p4.runs[0].marca.nome == "move1",
          "moveFrom com as pontas do trecho (moveFromRangeStart/End) como marcas")
    checa(p5.runs[-2].insercao.tipo == "moveTo" and p5.runs[-1].marca.fim,
          "moveTo com as pontas")
    checa(any(r.marca is not None and r.exclusao is not None for r in p6.runs)
          and any(r.texto == "1/1/2026" and r.exclusao is not None for r in p6.runs),
          "campo excluido: as marcas do campo e o resultado levam a exclusao (delInstrText lido)")
    checa(tab.mudanca_grade is not None and "tblPrChange" in (tab.extras or "")
          and "<w:ins" in (tab.linhas[0].extras or "") and "cellIns" in (tab.linhas[0].celulas[0].extras or "")
          and "<w:del" in (tab.linhas[1].extras or ""),
          "tabela: tblPrChange, tblGridChange, linha inserida/excluida e cellIns guardados")
    checa(p8.runs[2].insercao.data_utc == "2026-02-03T07:05:06Z", "w16du:dateUtc guardado")
    checa("sectPrChange" in (modelo.secao.original or ""), "w:sectPrChange fica na secao")
    checa(modelo.cabecalhos["padrao"][0].runs[-1].insercao is not None,
          "revisao no cabecalho tambem")
    tipos = [x[0] for x in mr.revisoes_de(modelo)]
    for tipo in ("ins", "del", "formato", "paragrafo", "marca_ins", "marca_del", "moveFrom",
                 "moveTo", "linha_ins", "linha_del"):
        checa(tipo in tipos, f"revisoes_de lista {tipo}")

    secao("arquivo: gravar, conferir, validar, reler, c14n e a 2a gravacao")
    gravado, avisos_g = escrever_com_avisos(modelo)
    checa_igual(avisos_g, [], "gravar nao da' aviso")
    checa_igual(ordem.validar(fx.partes_de(gravado)), [], "o validador aceita o arquivo gravado")
    conferencia.conferir(gravado, modelo)
    checa(True, "a conferencia aceita o arquivo gravado")
    relido, avisos2 = ler(gravado)
    checa_igual(codigos(avisos2), {}, "o gravado reabre sem aviso")
    checa_igual(normalizar(relido).paragrafos[:7], normalizar(modelo).paragrafos[:7],
                "releitura: os paragrafos com revisao iguais ao modelo")
    tab_a, tab_b = normalizar(modelo).paragrafos[7], normalizar(relido).paragrafos[7]
    checa_igual([(lin.extras, [c.extras for c in lin.celulas], [c.blocos for c in lin.celulas])
                 for lin in tab_b.linhas],
                [(lin.extras, [c.extras for c in lin.celulas], [c.blocos for c in lin.celulas])
                 for lin in tab_a.linhas], "releitura: linhas e celulas revisadas iguais")
    checa_igual((tab_b.extras, tab_b.mudanca_grade), (tab_a.extras, tab_a.mudanca_grade),
                "releitura: propriedades e grade da tabela revisadas iguais")
    checa_igual(mr.revisoes_de(relido), mr.revisoes_de(modelo), "a lista de revisoes e' a mesma")
    checa_igual(escrever(relido), escrever(ler(escrever(relido))[0]),
                "gravar, ler e gravar de novo da' os mesmos bytes")
    corpo = corpo_xml(gravado)
    for caminho, nome in ((".//w:rPrChange", "w:rPrChange"), (".//w:pPrChange", "w:pPrChange"),
                          (".//w:tblPrChange", "w:tblPrChange"), (".//w:tblGridChange", "w:tblGridChange"),
                          (".//w:trPr", "w:trPr (linha inserida)"), (".//w:cellIns", "w:cellIns"),
                          (".//w:sectPrChange", "w:sectPrChange")):
            g = corpo.find(caminho, NS)
            o = origem(CORPO + f"<w:sectPr>{SECT}</w:sectPr>", caminho)
            checa(g is not None and o and c14n(sem_id(g)) == c14n(sem_id(o[0])),
                  f"{nome} volta identico em c14n (sem o w:id)")
    del_ = corpo.findall(".//w:del", NS)
    checa(del_ and all(not d.findall(".//w:t", NS) and not d.findall(".//w:instrText", NS)
                       for d in del_) and corpo.find(".//w:delInstrText", NS) is not None,
          "dentro de w:del so' w:delText e w:delInstrText")
    ins = corpo.find(".//w:ins/w:del", NS)
    checa(ins is not None, "w:ins por fora e w:del por dentro, como o Word grava")
    for nome in ("moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd"):
        checa(corpo.find(f".//w:{nome}", NS) is not None, f"w:{nome} gravado")
    de = corpo.find(".//w:moveFromRangeStart", NS)
    de_fim = corpo.find(".//w:moveFromRangeEnd", NS)
    checa(de.get(f"{{{W}}}id") == de_fim.get(f"{{{W}}}id") and de.get(f"{{{W}}}name") == "move1"
          and "editdoc" not in etree.tostring(de).decode(),
          "as pontas do movimento com o mesmo w:id, sem o atributo provisorio")
    utc = corpo.find(".//w:ins[@w16du:dateUtc]", {**NS, "w16du": W16DU})
    checa(utc is not None and "w16du" in fx.partes_de(gravado)["word/document.xml"].decode()[:3000],
          "w16du:dateUtc volta, e a raiz declara o w16du")
    partes = fx.partes_de(gravado)
    ids = ids_de_revisao(partes)
    checa(len(ids) == len(set(ids)) and all(i and i.isdigit() for i in ids),
          f"w:id das revisoes unicos em todas as partes ({len(ids)})")
    marcadores = {b.get(f"{{{W}}}id") for b in corpo.iter(f"{{{W}}}bookmarkStart")}
    checa(not (set(ids) & marcadores), "nenhum w:id de revisao igual ao de um marcador")
    checa(b"<w:trackRevisions/>" in partes["word/settings.xml"], "w:trackRevisions continua ligado")
    checa(b"header" in b"".join(n.encode() for n in partes) and any(
        b"<w:ins" in d for n, d in partes.items() if "header" in n), "o cabecalho volta com a insercao")

    secao("arquivo: Controlar alteracoes ligado e desligado no settings.xml")
    modelo.controlar_alteracoes = False
    sem = fx.partes_de(escrever(modelo))["word/settings.xml"]
    checa(b"trackRevisions" not in sem, "desligado: o w:trackRevisions sai")
    novo = Documento(paragrafos=[Paragrafo(runs=[Run("x")])], controlar_alteracoes=True)
    cfg = fx.partes_de(escrever(novo))["word/settings.xml"]
    checa(b"<w:trackRevisions/>" in cfg and cfg.index(b"trackRevisions") < cfg.index(b"defaultTabStop"),
          "documento novo com o controle: w:trackRevisions na ordem do esquema")


def testar_validador() -> None:
    secao("validador: contraprovas")
    base = fx.partes_de(escrever(ler(docx_principal(cabecalho=False))[0]))
    checa_igual(fx_rev.validar(base), [], "o arquivo gravado passa")
    doc = base["word/document.xml"].decode("utf-8")
    ids = re.findall(r'<w:ins w:id="(\d+)"', doc)

    def com(trocado: str) -> list:
        return fx_rev.validar({**base, "word/document.xml": trocado.encode("utf-8")})

    checa(any("repetido" in p for p in com(doc.replace(f'<w:ins w:id="{ids[1]}"', f'<w:ins w:id="{ids[0]}"', 1))),
          "acusa w:id repetido entre revisoes")
    checa(any("w:t dentro de w:del" in p for p in com(doc.replace("<w:delText", "<w:t", 1)
                                                          .replace("</w:delText>", "</w:t>", 1))),
          "acusa w:t dentro de w:del")
    checa(any("fora de w:del" in p for p in com(doc.replace("Antes </w:t>", "Antes </w:delText>")
                                                   .replace('<w:t xml:space="preserve">Antes',
                                                            '<w:delText xml:space="preserve">Antes'))),
          "acusa w:delText fora de w:del")
    checa(any("sem par" in p or "sem o inicio" in p or "sem fim" in p
              for p in com(re.sub(r"<w:moveToRangeStart[^>]*/>", "", doc))),
          "acusa movimento sem par (o destino sem o inicio do trecho)")
    checa(any("sem fim" in p for p in com(re.sub(r"<w:moveFromRangeEnd[^>]*/>", "", doc))),
          "acusa trecho de movimento sem fim")
    marcador = re.search(r'<w:bookmarkStart w:id="(\d+)"', doc).group(1)
    checa(any("comentario ou marcador" in p for p in com(doc.replace(
        f'<w:ins w:id="{ids[0]}"', f'<w:ins w:id="{marcador}"', 1))),
          "acusa w:id de revisao igual ao de um marcador")
    checa(any("sem w:id" in p for p in com(doc.replace(f'<w:ins w:id="{ids[0]}"', "<w:ins", 1))),
          "acusa revisao sem w:id")
    checa_igual(fx_rev.validar({**base, "word/document.xml": doc.replace(
        f'<w:ins w:id="{ids[1]}"', f'<w:ins w:id="{ids[0]}"', 1).encode()}, preservados={ids[0]}), [],
                "id que veio do XML preservado pode se repetir (como veio)")


def testar_limites() -> None:
    secao("limites contra arquivo hostil")
    muitos = "".join(f'<w:ins w:id="{i}" {A}>{t("x")}</w:ins><w:del w:id="{i + 50000}" {A}>{dt("y")}</w:del>'
                     for i in range(1, 31))
    dados = fx.docx_com_xml(f"<w:p>{muitos}</w:p>")
    modelo, avisos = ler(dados, {"revisoes": 20})
    texto = "".join(r.texto for r in modelo.paragrafos[0].runs)
    checa(codigos(avisos).get("REVISAO") == 40 and texto.count("x") == 30 and texto.count("y") == 10,
          "acima do limite de revisoes: a insercao fica como texto e a exclusao sai, com REVISAO")
    checa(ordem.validar(fx.partes_de(escrever(modelo))) == [], "e o arquivo gravado e' valido")
    autores = "".join(f'<w:ins w:id="{i}" w:author="Autor {i}">{t("a")}</w:ins>' for i in range(1, 11))
    modelo, avisos = ler(fx.docx_com_xml(f"<w:p>{autores}</w:p>"), {"autores_revisao": 4})
    checa(codigos(avisos).get("REVISAO") == 6 and len(mr.autores(modelo)) == 4,
          "acima do limite de autores: as revisoes dos outros autores ficam como texto, com aviso")
    longo = "N" * 300
    modelo, avisos = ler(fx.docx_com_xml(f'<w:p><w:ins w:id="1" w:author="{longo}">{t("z")}</w:ins></w:p>'))
    checa(codigos(avisos).get("REVISAO") == 1 and modelo.paragrafos[0].runs[0].insercao is None,
          "nome de autor longo demais: a revisao nao e' guardada, com aviso")
    data = "9" * 200
    modelo, avisos = ler(fx.docx_com_xml(f'<w:p><w:del w:id="1" w:author="A" w:date="{data}">{dt("q")}</w:del></w:p>'))
    checa(codigos(avisos).get("REVISAO") == 1 and not modelo.paragrafos[0].runs,
          "data absurda: o comportamento antigo (exclusao fora), com aviso")


def testar_notas_comentarios_caixas() -> None:
    secao("revisoes em nota de rodape, comentario e caixa de texto")
    from editdoc.modelo import notas as mn
    from editdoc.modelo.documento import MarcaNota
    nota = mn.Nota("rodape", 1, (Paragrafo(runs=[
        Run(marca=MarcaNota("rodape", 0, propria=True)), Run(" Nota "),
        Run("nova", insercao=Revisao("ins", "Ana", DA)),
        Run(" velha", exclusao=Revisao("del", "Beto", DA))]),))
    cat = mn.Notas()
    cat.itens["rodape"] = [nota]
    doc = Documento(paragrafos=[Paragrafo(runs=[Run("Texto"), Run(marca=MarcaNota("rodape", 1)),
                                                Run(" mais", insercao=Revisao("ins", "Ana", DA))])])
    doc.notas = cat
    gravado = escrever(doc)
    partes = fx.partes_de(gravado)
    checa(b"<w:ins" in partes["word/footnotes.xml"] and b"<w:delText" in partes["word/footnotes.xml"],
          "a nota de rodape grava w:ins e w:del (com w:delText)")
    checa_igual(ordem.validar(partes), [], "e o arquivo e' valido")
    relido = ler(gravado)[0]
    runs = relido.notas.obter("rodape", 1).paragrafos[0].runs
    checa(any(r.texto == "nova" and r.insercao is not None for r in runs)
          and any(r.texto == " velha" and r.exclusao is not None for r in runs),
          "a releitura tem as revisoes da nota")
    ids = ids_de_revisao(partes)
    checa(len(ids) == len(set(ids)), "w:id unicos entre o corpo e a nota")
    # Comentario com revisao no conteudo, e ids de revisao diferentes dos do comentario.
    import teste_comentarios as tc
    corpo = (f"<w:p>{tc.ini(0)}{t('comentado')}{tc.fim(0)}{tc.ref(0)}"
             f'<w:ins w:id="0" {A}>{t(" novo")}</w:ins></w:p>')
    conteudo = f'<w:ins w:id="5" {B}>{t("Veja")}</w:ins>'
    dados = tc.docx_com_comentarios(corpo, [tc.comentario(0, "Ana", conteudo, "10000001")])
    modelo, avisos = ler(dados)
    checa_igual(codigos(avisos), {}, "comentario com revisao: sem aviso")
    c = modelo.comentarios.itens[0]
    checa(any(r.insercao is not None for p in c.paragrafos for r in p.runs),
          "a revisao do conteudo do comentario e' lida")
    gravado = escrever(modelo)
    partes = fx.partes_de(gravado)
    checa_igual(ordem.validar(partes, modelo.estilos.virtuais()), [], "e volta valida")
    corpo_g = corpo_xml(gravado)
    ins_corpo = corpo_g.find(".//w:ins", NS).get(f"{{{W}}}id")
    checa(ins_corpo != "0", f"o w:ins do corpo nao repete o id do comentario (0 -> {ins_corpo})")
    checa(b'w:id="5"' in partes["word/comments.xml"],
          "o comentario que nao mudou volta com o XML de origem (a revisao dentro, igual)")
    # Caixa de texto com revisao: objeto preservado (so' leitura), volta igual.
    extra = f'<w:ins w:id="77" {A}>{t(" incluido")}</w:ins>'
    dados = fx.docx_com_corpo_de_objetos(
        f"<w:p>{fx.caixa_de_texto(extra=extra)}</w:p>", fx.RELACOES_OBJETOS, fx.PARTES_OBJETOS,
        fx.TIPOS_OBJETOS, fx.PADROES_OBJETOS)
    modelo, avisos = ler(dados)
    gravado = escrever(modelo)
    doc_g = fx.partes_de(gravado)["word/document.xml"]
    checa(doc_g.count(b'w:id="77"') == 2 and b"incluido" in doc_g,
          "caixa de texto com revisao: o objeto volta com a revisao (Choice e Fallback, o mesmo id)")
    checa_igual(ordem.validar(fx.partes_de(gravado)), [], "e o arquivo e' valido")
    # Imagem excluida (achado na validacao com um documento gerado pelo EditDoc: a releitura
    # perdia a revisao do run da imagem e a conferencia recusava o arquivo).
    img = Run(texto="￼", imagem=fx.imagem(), exclusao=Revisao("del", "Beto", DA))
    doc = Documento(paragrafos=[Paragrafo(runs=[Run("Foto: "), img])])
    gravado = escrever(doc)
    conferencia.conferir(gravado, doc)
    relido = ler(gravado)[0].paragrafos[0].runs[-1]
    checa(relido.imagem is not None and relido.exclusao is not None,
          "imagem dentro de w:del: a releitura tem a exclusao (e a conferencia aceita)")


# -- tela --------------------------------------------------------------------------------------

#: O que os dialogos modais disseram (nenhum pode abrir de verdade: travaria a suite).
FALHAS_DE_DIALOGO: list = []


def _sem_modais() -> None:
    from editdoc.interface import dialogos_modais
    dialogos_modais.avisar = lambda _p, _t, texto: FALHAS_DE_DIALOGO.append(texto)
    dialogos_modais.pedir_falha_na_conferencia = \
        lambda _p, nome, _l: FALHAS_DE_DIALOGO.append(nome) or "fechar"


def _janela(dados: bytes):
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    _sem_modais()
    configuracao.gravar_preferencias({"nome_usuario": "Revisora Teste", "iniciais": "RT"})
    janela = JanelaPrincipal({**configuracao.padrao(), "nome_usuario": "Revisora Teste",
                              "iniciais": "RT"})
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


def _ir_para(janela, texto: str, depois: int = 0, selecionar: int = 0) -> None:
    from PySide6.QtGui import QTextCursor
    doc = janela.painel.documento_corpo()
    pos = doc.toPlainText().index(texto) + depois
    c = QTextCursor(doc)
    c.setPosition(pos)
    if selecionar:
        c.setPosition(pos + selecionar, QTextCursor.MoveMode.KeepAnchor)
    janela.painel.setTextCursor(c)


def _gravado(janela, pasta, nome: str) -> bytes:
    caminho = pasta / nome
    ok = janela._gravar(caminho, trocar=False)
    checa(ok, f"{nome}: a janela grava (conferencia e validador)")
    return caminho.read_bytes() if ok else b""


def _texto_pdf(janela) -> str:
    from editdoc.interface import impressao
    from leitor_pdf import ler_pdf
    layout = janela.painel.layout_pag
    janela.painel.preparar_para_impressao()
    dados = impressao.gerar_pdf(layout, list(range(layout.numero_paginas())), impressao.Metadados())
    return re.sub(r"\s+", " ", ler_pdf(dados).texto.replace("ﬁ", "fi"))


def testar_modos() -> None:
    secao("tela: os quatro modos (PDF, largura e paragrafo escondido) sem mexer no documento")
    from editdoc.edicao import revisoes as ed
    from editdoc.ponte_qt import revisoes as pq
    usar_fontes_do_documento()
    janela = _janela(docx_principal())
    painel = janela.painel
    doc = painel.documento_corpo()
    checa(pq.tem_revisoes(doc) and getattr(doc, "_realce_revisoes", None) is not None,
          "documento com revisao: o realce dos modos existe")
    checa(not janela.dock_comentarios.isHidden() and janela.revisoes.abas.currentWidget()
          is janela.revisoes.lista, "o painel lateral abre na aba Revisoes")
    checa(janela.revisoes.lista.lista.count() >= 10, "a lista mostra as revisoes")
    checa(janela.comandos.acao("controlar_alteracoes").isChecked(),
          "Controlar alteracoes aparece ligado (o arquivo tinha w:trackRevisions)")
    undo_antes = doc.availableUndoSteps()
    textos = {}
    alturas = {}
    bloco_apagado = doc.findBlockByNumber(3)
    for modo, acao in (("todas", "modo_todas"), ("simples", "modo_simples"),
                       ("final", "modo_sem"), ("original", "modo_original")):
        janela.comandos.acao(acao).trigger()
        drenar_eventos()
        textos[modo] = _texto_pdf(janela)
        alturas[modo] = doc.documentLayout().blockBoundingRect(bloco_apagado).height()
        checa(pq.modo_de(doc) == modo, f"{modo}: o modo vale para o corpo")
    checa("inserido" in textos["todas"] and "apagado" in textos["todas"]
          and "dupla" in textos["todas"], "Toda a marcacao: inserido e excluido no PDF")
    checa("inserido" in textos["final"] and "apagado" not in textos["final"]
          and "Apagado inteiro" not in textos["final"], "Sem marcacao: so' o texto final")
    checa("apagado" not in textos["simples"] and "inserido" in textos["simples"],
          "Marcacao simples: o texto final")
    checa("inserido" not in textos["original"] and "apagado" in textos["original"]
          and "linha nova" not in textos["original"] and "dupla" not in textos["original"],
          "Original: o texto de antes (sem o inserido nem o inserido-e-apagado)")
    checa(alturas["todas"] > 0 and alturas["final"] == 0 and alturas["original"] > 0,
          f"o paragrafo excluido inteiro some no final ({alturas})")
    checa(not doc.isModified() and doc.availableUndoSteps() == undo_antes,
          "trocar de modo nao mexe no desfazer nem no alterado")
    janela.comandos.acao("modo_todas").trigger()
    # Largura: no final, o excluido nao ocupa espaco na linha.
    bloco = doc.firstBlock()
    janela.comandos.acao("modo_todas").trigger()
    larga = bloco.layout().lineAt(0).naturalTextWidth()
    janela.comandos.acao("modo_sem").trigger()
    estreita = bloco.layout().lineAt(0).naturalTextWidth()
    checa(estreita < larga * 0.9, f"Sem marcacao: a linha fica mais curta ({larga:.0f} -> {estreita:.0f})")
    janela.comandos.acao("modo_todas").trigger()
    # Barra na margem esquerda (Toda a marcacao) na tela.
    from PySide6.QtGui import QImage, QPainter, QTransform
    from editdoc.interface.vista_paginas import desenhar_folha
    layout = painel.layout_pag
    img = QImage(900, 400, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFF)
    p = QPainter(img)
    escala = 900 / layout.pagina.largura_tw
    desenhar_folha(p, layout, 0, QTransform().scale(escala, escala))
    p.end()
    x = round((layout.pagina.margem_esq_tw - pq.DISTANCIA_BARRA_TW + 10) * escala)
    y = round((layout.pagina.margem_sup_tw + 120) * escala)
    cor = img.pixelColor(x, y)
    checa(cor.red() < 200, f"a barra de alteracao aparece na margem esquerda ({cor.name()})")
    checa("inserido" in ed.texto_no_modo(doc, "todas") and "apagado" not in ed.texto_no_modo(doc, "final"),
          "texto do modo (para contar e copiar)")
    # Cabecalho: o realce vale la' tambem.
    faixa = layout.faixas.todas()[0]
    checa(pq.tem_revisoes(faixa.doc), "o cabecalho com insercao tambem tem o realce")
    _fechar(janela)


def testar_aceitar_rejeitar(pasta) -> None:
    secao("aceitar e rejeitar cada tipo, e o XML resultante")
    from editdoc.edicao import revisoes as ed

    def janela_e_item(tipo: str, ordem_: int = 0):
        janela = _janela(docx_principal(cabecalho=False))
        itens = [i for i in ed.listar(janela.painel.documento_corpo()) if i.tipo == tipo]
        return janela, itens[ordem_]

    def resolver(tipo, aceitar, ordem_=0):
        # Pelo painel de revisoes: escolher a linha e clicar Aceitar ou Rejeitar.
        janela, item = janela_e_item(tipo, ordem_)
        controle = janela.revisoes
        controle.atualizar_lista()
        indice = next(i for i, x in enumerate(controle._itens)
                      if (x.tipo, x.inicio, x.fim, x.chave) == (item.tipo, item.inicio, item.fim,
                                                                 item.chave))
        antes = len(ed.listar(janela.painel.documento_corpo()))
        controle.lista.lista.setCurrentRow(indice)
        (controle.lista.botao_aceitar if aceitar else controle.lista.botao_rejeitar).click()
        drenar_eventos(1)
        res = len(ed.listar(janela.painel.documento_corpo())) < antes
        dados = _gravado(janela, pasta, f"{tipo}_{aceitar}.docx")
        modelo = ler(dados)[0] if dados else None
        texto = "".join(r.texto for p in (modelo.paragrafos if modelo else []) if isinstance(p, Paragrafo)
                        for r in p.runs)
        return janela, res, dados, modelo, texto

    j, ok, dados, m, texto = resolver("ins", True)
    corpo = corpo_xml(dados)
    checa(ok and "inserido" in texto and not any(r.insercao for r in m.paragrafos[0].runs
                                                  if r.texto == "inserido"),
          "aceitar insercao: o texto fica, sem w:ins")
    _fechar(j)
    j, ok, dados, m, texto = resolver("ins", False)
    checa(ok and "inserido" not in texto, "rejeitar insercao: o texto sai")
    _fechar(j)
    j, ok, dados, m, texto = resolver("del", True)
    checa(ok and " apagado" not in texto, "aceitar exclusao: o texto sai")
    _fechar(j)
    j, ok, dados, m, texto = resolver("del", False)
    corpo = corpo_xml(dados)
    checa(ok and " apagado" in texto and "apagado" in "".join(corpo.xpath(".//w:t/text()", namespaces=NS)),
          "rejeitar exclusao: volta como w:t")
    _fechar(j)
    j, ok, dados, m, texto = resolver("formato", True)
    r = next(r for r in m.paragrafos[0].runs if r.texto == " formatado")
    checa(ok and r.mudanca_formato is None and r.italico, "aceitar formatacao: italico fica, sem rPrChange")
    _fechar(j)
    j, ok, dados, m, texto = resolver("formato", False)
    r = next(r for r in m.paragrafos[0].runs if r.texto == " formatado")
    checa(ok and r.mudanca_formato is None and r.negrito and not r.italico,
          "rejeitar formatacao: volta a de antes (negrito, sem italico)")
    _fechar(j)
    j, ok, dados, m, texto = resolver("paragrafo", False)
    checa(ok and m.paragrafos[1].mudanca_formato is None and m.paragrafos[1].alinhamento in (None, "esquerda"),
          "rejeitar formatacao de paragrafo: o alinhamento de antes")
    _fechar(j)
    j, ok, dados, m, texto = resolver("paragrafo", True)
    checa(ok and m.paragrafos[1].mudanca_formato is None and m.paragrafos[1].alinhamento == "centro",
          "aceitar formatacao de paragrafo: fica o centralizado, sem pPrChange")
    _fechar(j)
    j, ok, dados, m, texto = resolver("marca_ins", True)
    checa(ok and m.paragrafos[1].marca_insercao is None and m.paragrafos[1].runs[0].texto == "Marca inserida",
          "aceitar marca de paragrafo inserida: os paragrafos continuam separados")
    _fechar(j)
    j, ok, dados, m, texto = resolver("marca_ins", False)
    checa(ok and "Marca inseridaSegue a marca." in [
        "".join(r.texto for r in p.runs) for p in m.paragrafos if isinstance(p, Paragrafo)],
          "rejeitar marca inserida: o paragrafo junta com o de baixo")
    _fechar(j)
    j, ok, dados, m, texto = resolver("marca_del", True)
    checa(ok and not any(p.marca_exclusao for p in m.paragrafos if isinstance(p, Paragrafo)),
          "aceitar marca excluida: junta com o seguinte, sem w:del no rPr")
    _fechar(j)
    j, ok, dados, m, texto = resolver("moveTo", True)
    corpo = corpo_xml(dados)
    checa(ok and corpo.find(".//w:moveFrom", NS) is None and corpo.find(".//w:moveTo", NS) is None
          and corpo.find(".//w:moveFromRangeStart", NS) is None and texto.count("Movido") == 1,
          "aceitar o movimento: as duas pontas (a origem sai, o destino fica), sem as marcas")
    _fechar(j)
    j, ok, dados, m, texto = resolver("moveFrom", False)
    corpo = corpo_xml(dados)
    checa(ok and corpo.find(".//w:moveFrom", NS) is None and corpo.find(".//w:moveTo", NS) is None
          and texto.count("Movido") == 1 and "Destino: Movido" not in texto,
          "rejeitar o movimento: volta para a origem")
    _fechar(j)
    j, ok, dados, m, texto = resolver("linha_ins", False)
    tab = next(b for b in m.paragrafos if not isinstance(b, Paragrafo))
    checa(ok and len(tab.linhas) == 2 and "linha nova" not in texto, "rejeitar linha inserida: a linha sai")
    _fechar(j)
    j, ok, dados, m, texto = resolver("linha_del", True)
    tab = next(b for b in m.paragrafos if not isinstance(b, Paragrafo))
    checa(ok and len(tab.linhas) == 2 and "linha velha" not in texto, "aceitar linha excluida: a linha sai")
    _fechar(j)
    j, ok, dados, m, texto = resolver("linha_ins", True)
    tab = next(b for b in m.paragrafos if not isinstance(b, Paragrafo))
    checa(ok and len(tab.linhas) == 3 and "<w:ins" not in (tab.linhas[0].extras or ""),
          "aceitar linha inserida: a linha fica, sem w:ins no trPr")
    _fechar(j)
    j, ok, dados, m, texto = resolver("celula", True)
    tab = next(b for b in m.paragrafos if not isinstance(b, Paragrafo))
    checa(ok and "cellIns" not in (tab.linhas[0].celulas[0].extras or ""), "aceitar w:cellIns")
    _fechar(j)
    j, ok, dados, m, texto = resolver("celula", False)
    tab = next(b for b in m.paragrafos if not isinstance(b, Paragrafo))
    checa(not ok and "cellIns" in (tab.linhas[0].celulas[0].extras or ""),
          "rejeitar w:cellIns nao e' feito (so' aceitar), e a revisao fica")
    _fechar(j)
    j, ok, dados, m, texto = resolver("tabela", True)
    tab = next(b for b in m.paragrafos if not isinstance(b, Paragrafo))
    checa(ok and "tblPrChange" not in (tab.extras or "") and tab.mudanca_grade is None,
          "aceitar propriedades da tabela: sem tblPrChange e tblGridChange")
    _fechar(j)
    j, ok, dados, m, texto = resolver("secao", True)
    checa(ok and "sectPrChange" not in (m.secao.original or ""), "aceitar a revisao da secao")
    _fechar(j)

    secao("aceitar e rejeitar: selecao, todas, de um autor, desfazer, proxima")
    janela = _janela(docx_principal(cabecalho=False))
    painel = janela.painel
    doc = painel.documento_corpo()
    antes = doc.toPlainText()
    _ir_para(janela, "Antes ", 0, len("Antes inserido apagadodupla"))
    drenar_eventos()
    checa(janela.comandos.acao("aceitar_revisao").isEnabled(),
          "com a selecao numa alteracao, Aceitar fica habilitado")
    janela.comandos.acao("aceitar_revisao").trigger()
    checa("apagado" not in doc.toPlainText() and "inserido" in doc.toPlainText(),
          "aceitar a selecao: as revisoes dela (o excluido sai)")
    janela.comandos.acao("desfazer").trigger()
    checa_igual(doc.toPlainText(), antes, "um desfazer devolve tudo")
    janela._escolher_autor = lambda autores, verbo: "Beto" if "Beto" in autores else None
    janela.comandos.acao("rejeitar_do_autor").trigger()
    beto = [i for i in ed.listar(doc) if i.autor == "Beto" and i.tipo in ("ins", "del")]
    checa(not beto and "inserido" in doc.toPlainText() and "apagado" in doc.toPlainText(),
          "rejeitar todas de Beto: as exclusoes dele voltam, as insercoes de Ana ficam")
    janela.comandos.acao("desfazer").trigger()
    janela.comandos.acao("aceitar_todas").trigger()
    restam = [i.tipo for i in ed.listar(doc)]
    checa(set(restam) <= set(ed.SO_ACEITAR) and not [i for i in restam if i in ("ins", "del")],
          f"aceitar todas: nao sobra revisao de texto ({restam})")
    dados = _gravado(janela, pasta, "todas.docx")
    corpo = corpo_xml(dados)
    checa(corpo.find(".//w:ins", NS) is None and corpo.find(".//w:del", NS) is None
          and corpo.find(".//w:rPrChange", NS) is None and corpo.find(".//w:pPrChange", NS) is None,
          "o arquivo depois de aceitar todas nao tem w:ins, w:del, rPrChange nem pPrChange")
    janela.comandos.acao("desfazer").trigger()
    checa_igual(doc.toPlainText(), antes, "desfazer o aceitar todas devolve o documento")
    c = painel.textCursor()
    c.setPosition(0)
    painel.setTextCursor(c)
    janela.comandos.acao("revisao_proxima").trigger()
    checa_igual(painel.textCursor().selectedText(), "inserido", "Proxima seleciona a primeira alteracao")
    janela.comandos.acao("revisao_proxima").trigger()
    checa_igual(painel.textCursor().selectedText(), " apagadodupla",
                "Proxima de novo, a seguinte (a exclusao de Beto, os dois trechos vizinhos juntos)")
    janela.comandos.acao("revisao_anterior").trigger()
    checa_igual(painel.textCursor().selectedText(), "inserido", "Anterior volta")
    janela.revisoes.atualizar_lista()
    lista = janela.revisoes.lista
    lista.lista.setCurrentRow(1)
    drenar_eventos()
    checa(painel.textCursor().hasSelection(), "clicar numa linha do painel seleciona o trecho")
    _fechar(janela)


def _tecla(painel, tecla, mods=None, texto: str = "") -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.keyClick(painel, tecla, mods or Qt.KeyboardModifier.NoModifier)
    drenar_eventos(1)


def testar_edicao(pasta) -> None:
    secao("edicao com o controle ligado: digitar, apagar, Enter, colar, formatar e desfazer")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from editdoc.edicao import revisoes as ed
    from editdoc.ponte_qt import revisoes as pq
    simples = fx.docx_com_xml(f'<w:p>{t("Base ")}<w:ins w:id="1" {B}>{t("alheio")}</w:ins>{t(" fim")}</w:p>')
    janela = _janela(simples)
    painel = janela.painel
    doc = painel.documento_corpo()
    checa(not janela.comandos.acao("controlar_alteracoes").isChecked(), "comeca desligado")
    QTest.keyClick(painel, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    drenar_eventos()
    checa(ed.controle_ligado(painel) and janela.comandos.acao("controlar_alteracoes").isChecked()
          and doc.isModified(), "Ctrl+Shift+E liga (e o documento fica alterado: vai ao settings)")
    antes = doc.toPlainText()
    _ir_para(janela, " fim", 4)
    QTest.keyClicks(painel, "xyz")
    drenar_eventos()
    item = [i for i in ed.listar(doc) if i.tipo == "ins" and i.autor == "Revisora Teste"]
    checa(item and item[0].texto == "xyz", "digitar cria insercao da autora das Opcoes")
    _tecla(painel, Qt.Key.Key_Backspace)
    checa(doc.toPlainText().endswith("fimxy"), "Backspace no texto proprio ainda nao aceito: o caractere sai")
    _ir_para(janela, "alheio", 6)
    _tecla(painel, Qt.Key.Key_Backspace)
    from editdoc.ponte_qt.links import formato_em
    pos = doc.toPlainText().index("alheio") + 5
    checa("alheio" in doc.toPlainText() and pq.exclusao_de(formato_em(doc, pos)) is not None,
          "Backspace no texto de outro autor: fica, marcado como excluido")
    _ir_para(janela, "Base", 0)
    _tecla(painel, Qt.Key.Key_Delete)
    checa(pq.exclusao_de(formato_em(doc, 0)) is not None and painel.textCursor().position() == 1,
          "Delete marca o caractere e o cursor passa por ele")
    _ir_para(janela, "Base ", 2)
    _tecla(painel, Qt.Key.Key_Return)
    checa(pq.marca_de(doc.firstBlock().blockFormat())[0] is not None
          and pq.marca_de(doc.firstBlock().next().blockFormat())[0] is None,
          "Enter: a marca do paragrafo de cima e' a nova (inserida)")
    _tecla(painel, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    checa(doc.blockCount() == 1, "Ctrl+Z desfaz o Enter")
    # Formatar: negrito na selecao e alinhamento.
    _ir_para(janela, "Base", 0, 4)
    QTest.keyClick(painel, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    drenar_eventos()
    checa(pq.mudanca_de(formato_em(doc, 1)) is not None, "Ctrl+B na selecao guarda a formatacao de antes")
    QTest.keyClick(painel, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
    drenar_eventos()
    checa(pq.mudanca_de_bloco(doc.firstBlock().blockFormat())[0] is not None,
          "centralizar guarda as propriedades de paragrafo de antes")
    _tecla(painel, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    checa(pq.mudanca_de_bloco(doc.firstBlock().blockFormat())[0] is None,
          "um desfazer tira a centralizacao e a revisao dela juntas")
    # Colar.
    from PySide6.QtCore import QMimeData
    from PySide6.QtWidgets import QApplication
    md = QMimeData()
    md.setText("colado")
    QApplication.clipboard().setMimeData(md)
    _ir_para(janela, " fim", 0)
    QTest.keyClick(painel, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    drenar_eventos()
    item = [i for i in ed.listar(doc) if i.tipo == "ins" and i.texto == "colado"]
    checa(bool(item), "colar com o controle ligado: insercao")
    QApplication.clipboard().clear()
    dados = _gravado(janela, pasta, "editado.docx")
    corpo = corpo_xml(dados)
    autores = {el.get(f"{{{W}}}author") for el in corpo.iter(f"{{{W}}}ins")}
    checa({"Revisora Teste", "Beto"} <= autores, f"o arquivo tem os dois autores ({autores})")
    checa(corpo.find(".//w:rPrChange", NS) is not None and corpo.find(".//w:del", NS) is not None,
          "o arquivo tem a exclusao e a formatacao alterada")
    checa(b"<w:trackRevisions/>" in fx.partes_de(dados)["word/settings.xml"],
          "e o w:trackRevisions ligado")
    # Desligado: o texto novo nao herda a revisao do vizinho.
    QTest.keyClick(painel, Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    drenar_eventos()
    _ir_para(janela, "colado", 3)
    QTest.keyClicks(painel, "QQ")
    drenar_eventos()
    pos = doc.toPlainText().index("QQ")
    checa(not ed.controle_ligado(painel) and pq.insercao_de(formato_em(doc, pos)) is None,
          "controle desligado: digitar no meio de uma insercao nao herda a revisao")
    _ir_para(janela, "QQ", 0, 2)
    _tecla(painel, Qt.Key.Key_Delete)
    checa("QQ" not in doc.toPlainText(), "controle desligado: apagar remove de verdade")
    # Desfazer volta tudo, passo a passo, ate' o documento de antes.
    for _ in range(40):
        if not doc.isUndoAvailable():
            break
        painel.undo()
    checa_igual(doc.toPlainText(), antes, "desfazer tudo devolve o texto de antes")
    _fechar(janela)


def testar_saidas(pasta) -> None:
    secao("copiar, localizar, contar palavras e .txt na visao do modo")
    from PySide6.QtWidgets import QApplication
    from editdoc.edicao import busca
    from editdoc.modelo.texto_plano import texto_do_documento
    from editdoc.ponte_qt import de_qt
    janela = _janela(docx_principal(cabecalho=False))
    painel = janela.painel
    _ir_para(janela, "Antes", 0, len("Antes inserido apagadodupla formatado"))
    painel.copy()
    checa_igual(QApplication.clipboard().text(), "Antes inserido formatado",
                "Toda a marcacao: copiar leva o texto final (como o Word)")
    janela.comandos.acao("modo_original").trigger()
    painel.copy()
    checa_igual(QApplication.clipboard().text(), "Antes  apagado formatado",
                "Original: copiar leva o texto de antes")
    QApplication.clipboard().clear()
    janela.comandos.acao("modo_sem").trigger()
    c = painel.textCursor()
    c.setPosition(0)
    painel.setTextCursor(c)
    checa(not busca.localizar(painel, "apagado", busca.Opcoes()),
          "Sem marcacao: localizar nao acha o texto excluido (escondido)")
    janela.comandos.acao("modo_todas").trigger()
    checa(busca.localizar(painel, "apagado", busca.Opcoes()),
          "Toda a marcacao: localizar acha o excluido (aparece tachado)")
    janela.atualizar_estatisticas()
    palavras = int(janela._rotulo_palavras.text().split()[-1])
    checa("apagado" not in janela.revisoes.texto_para_contar() and palavras > 5,
          f"a contagem de palavras usa o texto final ({palavras})")
    texto = texto_do_documento(de_qt.extrair(painel.documento_corpo()))
    checa("inserido" in texto and "apagado" not in texto and "Apagado inteiro" not in texto
          and "linha velha" not in texto, "o .txt leva o texto final")
    _fechar(janela)


def testar_pdf_marcacoes() -> None:
    secao("PDF com e sem Imprimir marcacoes (comentarios incluidos)")
    import teste_comentarios as tc
    usar_fontes_do_documento()
    corpo = (f"<w:p>{tc.ini(0)}{t('Trecho comentado ')}{tc.fim(0)}{tc.ref(0)}"
             f'<w:del w:id="9" {B}>{dt("excluido")}</w:del>{t(" resto.")}</w:p>')
    dados = tc.docx_com_comentarios(corpo, [tc.comentario(0, "Ana", t("Opiniao da revisora"), "10000001")])
    janela = _janela(dados)
    checa(janela.comandos.acao("imprimir_marcacoes").isChecked(), "Imprimir marcacoes comeca ligado")
    com = _texto_pdf(janela)
    checa("excluido" in com and "Opiniao da revisora" in com,
          "com marcacoes: o PDF tem o excluido (Toda a marcacao) e o comentario na margem")
    janela.comandos.acao("imprimir_marcacoes").trigger()
    sem = _texto_pdf(janela)
    checa("excluido" not in sem and "Opiniao da revisora" not in sem and "resto" in sem,
          "sem marcacoes: o texto final, sem comentario")
    from editdoc.ponte_qt import revisoes as pq
    checa(pq.modo_de(janela.painel.documento_corpo()) == "todas",
          "depois de imprimir, a tela volta ao modo de antes")
    _fechar(janela)


def main() -> int:
    if not QT:
        return pular("PySide6 nao instalado")
    testar_arquivo()
    testar_validador()
    testar_limites()
    testar_notas_comentarios_caixas()
    with pasta_temporaria() as pasta:
        testar_modos()
        testar_aceitar_rejeitar(pasta)
        testar_edicao(pasta)
        testar_saidas(pasta)
        testar_pdf_marcacoes()
    drenar_eventos()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
