"""Referencias de estilo preservadas e formatacao condicional de tabela (0.1.6).

- rStyle e pStyle que o styles.xml nao define (o "CommentReference" latente do Word, um id
  qualquer): sem aviso ESTILO; a referencia volta igual; o styles.xml nao ganha definicao; o
  validador so' aceita com a lista de preservados (contraprova sem ela); a tela usa a
  aparencia padrao do Word para os latentes conhecidos e nada para o resto, sem virar
  formatacao direta ao salvar; o id citado com outro tipo continua com ESTILO;
- o rPr dos runs do codigo de um campo (o "Vinculo de indice" do sumario) volta;
- tabela com estilo de formatacao condicional (tblStylePr com faixas, tblLook, cnfStyle):
  sem aviso, o estilo e o tblLook voltam (c14n), o fundo condicional aparece na tela e nao
  vira sombreamento direto ao salvar; contraprova com noHBand.
"""

from __future__ import annotations

import io
import zipfile

from ajudantes import checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx.escritor import escrever, escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo.documento import Tabela, normalizar, paragrafos_de  # noqa: E402
from editdoc.modelo.estilos import ESTILOS_LATENTES_WORD  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


def codigos(avisos) -> dict:
    return {a.codigo: a.contagem for a in avisos}


def xml_de(dados: bytes, parte: str = "word/document.xml"):
    return etree.fromstring(fx.partes_de(dados)[parte])


def estilos_citados(dados: bytes, tag: str) -> list[str]:
    return [el.get("{%s}val" % W) for el in xml_de(dados).iter("{%s}%s" % (W, tag))]


CORPO_REFERENCIAS = (
    '<w:p><w:pPr><w:pStyle w:val="CommentText"/></w:pPr>'
    '<w:r><w:t xml:space="preserve">texto </w:t></w:r>'
    '<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:t>ref</w:t></w:r>'
    '<w:r><w:rPr><w:rStyle w:val="EstiloQueNaoExiste"/></w:rPr><w:t>outro</w:t></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="TOC2"/></w:pPr><w:r><w:t>item do sumario</w:t></w:r></w:p>'
    '<w:p><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr><w:t>parece link</w:t></w:r></w:p>')


def testar_referencias() -> None:
    secao("estilo citado sem definicao: a referencia volta, sem aviso")
    dados = fx.docx_com_estilos_do_word(CORPO_REFERENCIAS)
    modelo, avisos = ler(dados)
    checa("ESTILO" not in codigos(avisos), f"sem aviso ESTILO ({codigos(avisos)})")
    runs = [r for p in paragrafos_de(modelo.paragrafos) for r in p.runs]
    checa_igual([r.estilo for r in runs if r.texto in ("ref", "outro", "parece link")],
                ["CommentReference", "EstiloQueNaoExiste", "Hyperlink"],
                "o run guarda o id citado")
    paragrafos = list(paragrafos_de(modelo.paragrafos))
    checa_igual([p.estilo for p in paragrafos], ["CommentText", "TOC2", None],
                "o paragrafo guarda o pStyle citado")
    virtuais = modelo.estilos.virtuais()
    checa({"CommentReference", "CommentText", "EstiloQueNaoExiste", "TOC2", "Hyperlink"} <= virtuais,
          f"os ids citados entram como referencia preservada ({sorted(virtuais)})")
    gravado, avisos_g = escrever_com_avisos(modelo)
    checa_igual(avisos_g, [], "gravar nao avisa nada")
    checa_igual(sorted(estilos_citados(gravado, "rStyle")),
                sorted(estilos_citados(dados, "rStyle")), "os rStyle voltam iguais")
    checa_igual(sorted(estilos_citados(gravado, "pStyle")),
                sorted(estilos_citados(dados, "pStyle")), "os pStyle voltam iguais")
    definidos = {el.get("{%s}styleId" % W) for el in xml_de(gravado, "word/styles.xml").iter(
        "{%s}style" % W)}
    checa(not (virtuais & definidos), "o styles.xml nao ganha a definicao dos citados")
    partes = fx.partes_de(gravado)
    checa_igual(ordem.validar(partes, virtuais), [], "o validador aceita com os preservados")
    checa(any("CommentReference" in p for p in ordem.validar(partes)),
          "contraprova: sem a lista de preservados, a referencia sem definicao e' acusada")
    conferencia.conferir(gravado, modelo)
    checa(True, "a conferencia do arquivo gravado passa")
    relido, avisos_r = ler(gravado)
    checa(normalizar(relido) == normalizar(modelo) and "ESTILO" not in codigos(avisos_r),
          "ida e volta: o mesmo modelo, sem aviso")
    checa_igual(escrever(relido), gravado, "idempotente: gravar de novo da' os mesmos bytes")


def testar_tipo_errado() -> None:
    secao("id citado com outro tipo: continua perda de verdade (ESTILO)")
    corpo = '<w:p><w:r><w:rPr><w:rStyle w:val="Ttulo1"/></w:rPr><w:t>x</w:t></w:r></w:p>'
    modelo, avisos = ler(fx.docx_com_estilos_do_word(corpo))
    run = next(r for p in paragrafos_de(modelo.paragrafos) for r in p.runs)
    checa(codigos(avisos).get("ESTILO") == 1 and run.estilo is None,
          "rStyle que aponta para estilo de paragrafo: ESTILO, e o run fica sem estilo")
    gravado = escrever(modelo)
    checa_igual(ordem.validar(fx.partes_de(gravado), modelo.estilos.virtuais()), [],
                "e o arquivo gravado continua valido")


def testar_aparencia() -> None:
    secao("aparencia: latente do Word conhecido sim, id desconhecido nao")
    modelo, _ = ler(fx.docx_com_estilos_do_word(CORPO_REFERENCIAS))
    est = modelo.estilos
    checa_igual(est.resolver_caractere("CommentReference").get("tamanho_meio_pt"), 16,
                "CommentReference: 8 pt, como no Word")
    checa_igual(est.resolver_caractere("Hyperlink"), {"cor_hex": "0563C1", "sublinhado": True},
                "Hyperlink: azul e sublinhado")
    checa_igual(est.resolver_caractere("EstiloQueNaoExiste"), {},
                "id desconhecido: nenhuma formatacao alem do padrao")
    par, _car = est.resolver_paragrafo("TOC2")
    checa_igual(par.get("recuo_esquerdo_tw"), 220, "TOC2: recuo de 0,39 cm, como no Word")
    checa_igual(ESTILOS_LATENTES_WORD["CommentText"][4].get("tamanho_meio_pt"), 20,
                "CommentText: 10 pt")
    if not QT:
        return
    from PySide6.QtGui import QTextCursor
    from editdoc.ponte_qt import de_qt, para_qt
    from editdoc.ponte_qt.imagens import DocumentoQt
    doc = DocumentoQt()
    para_qt.preencher(doc, modelo)
    pos = doc.toPlainText().index("ref")
    c = QTextCursor(doc)
    c.setPosition(pos + 1)
    checa_igual(c.charFormat().fontPointSize(), 8.0, "na tela, a referencia sai em 8 pt")
    pos = doc.toPlainText().index("parece")
    c.setPosition(pos + 1)
    checa(c.charFormat().fontUnderline(), "o Hyperlink latente aparece sublinhado")
    volta = de_qt.extrair(doc)
    volta.pacote, volta.pagina = modelo.pacote, modelo.pagina
    runs = [r for p in paragrafos_de(volta.paragrafos) for r in p.runs]
    ref = next(r for r in runs if r.texto == "ref")
    checa(ref.estilo == "CommentReference" and ref.tamanho_meio_pt is None,
          "de volta da tela: o estilo fica e os 8 pt nao viram formatacao direta")
    gravado = escrever(volta)
    raiz = xml_de(gravado)
    checa(not raiz.findall(".//w:r/w:rPr/w:sz", NS), "o arquivo gravado nao ganha w:sz nenhum")


def testar_garantir() -> None:
    secao("estilo latente usado pelo EditDoc ganha a definicao")
    modelo, _ = ler(fx.docx_com_estilos_do_word(CORPO_REFERENCIAS))
    e = modelo.estilos.garantir("Hyperlink")
    checa(e is not None and not e.virtual and "Hyperlink" not in modelo.estilos.virtuais(),
          "garantir('Hyperlink') tira o estilo da lista de preservados")
    gravado = escrever(modelo)
    definidos = {el.get("{%s}styleId" % W) for el in xml_de(gravado, "word/styles.xml").iter(
        "{%s}style" % W)}
    checa("Hyperlink" in definidos and ordem.validar(fx.partes_de(gravado),
                                                     modelo.estilos.virtuais()) == [],
          "o styles.xml gravado tem a definicao, e o arquivo e' valido")


def testar_codigo_do_campo() -> None:
    secao("rPr dos runs do codigo de um campo (o sumario do Word)")
    corpo = ('<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
             '<w:r><w:rPr><w:rStyle w:val="Destaque"/><w:webHidden/></w:rPr>'
             '<w:instrText xml:space="preserve"> TOC \\o "1-3" \\h </w:instrText></w:r>'
             '<w:r><w:rPr><w:rStyle w:val="Destaque"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r>'
             '<w:r><w:t>Introducao</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
    dados = fx.docx_com_estilos_do_word(corpo)
    modelo, avisos = ler(dados)
    gravado = escrever(modelo)
    raiz = xml_de(gravado)
    instr = next(iter(raiz.xpath(".//w:r[w:instrText]", namespaces=NS)), None)
    sep = next(iter(raiz.xpath(".//w:r[w:fldChar/@w:fldCharType='separate']", namespaces=NS)), None)
    checa(instr is not None and instr.find("w:rPr/w:rStyle", NS) is not None
          and instr.find("w:rPr/w:webHidden", NS) is not None,
          "o run do instrText volta com o rStyle e o webHidden")
    checa(sep is not None and sep.find("w:rPr/w:rStyle", NS) is not None,
          "o run do separate volta com o rStyle")
    checa_igual(len(estilos_citados(gravado, "rStyle")), 2, "as duas ocorrencias de rStyle voltam")
    conferencia.conferir(gravado, modelo)
    checa_igual(escrever(ler(gravado)[0]), gravado, "idempotente")
    sem = fx.docx_com_estilos_do_word(corpo.replace('<w:rPr><w:rStyle w:val="Destaque"/><w:webHidden/></w:rPr>', "")
                                      .replace('<w:rPr><w:rStyle w:val="Destaque"/></w:rPr>', ""))
    checa_igual(estilos_citados(escrever(ler(sem)[0]), "rStyle"), [],
                "contraprova: sem rPr no codigo, o EditDoc nao inventa um")


ESTILO_FAIXAS = (
    '<w:style w:type="table" w:styleId="TabelaFaixas"><w:name w:val="Grid Table 4 Accent 1"/>'
    '<w:basedOn w:val="Tabelanormal"/><w:uiPriority w:val="49"/>'
    '<w:tblPr><w:tblStyleRowBandSize w:val="1"/><w:tblBorders><w:top w:val="single" w:sz="4" '
    'w:space="0" w:color="8EAADB"/></w:tblBorders></w:tblPr>'
    '<w:tblStylePr w:type="firstRow"><w:rPr><w:b/><w:color w:val="FFFFFF"/></w:rPr>'
    '<w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="4472C4"/></w:tcPr></w:tblStylePr>'
    '<w:tblStylePr w:type="band1Horz"><w:tcPr><w:shd w:val="clear" w:color="auto" '
    'w:fill="D9E2F3"/></w:tcPr></w:tblStylePr></w:style>')


def _tabela_xml(look: str) -> str:
    def linha(i):
        cnf = '<w:trPr><w:cnfStyle w:val="100000000000"/></w:trPr>' if i == 0 else ""
        return (f'<w:tr>{cnf}' + "".join(
            f'<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/>'
            f'{"<w:cnfStyle w:val=\"001000000000\"/>" if i == 1 else ""}</w:tcPr>'
            f'<w:p><w:pPr><w:cnfStyle w:val="000000100000"/></w:pPr><w:r><w:t>l{i}c{c}</w:t></w:r></w:p></w:tc>'
            for c in range(2)) + '</w:tr>')
    return ('<w:tbl><w:tblPr><w:tblStyle w:val="TabelaFaixas"/><w:tblW w:w="0" w:type="auto"/>'
            f'{look}</w:tblPr><w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid>'
            + "".join(linha(i) for i in range(4)) + '</w:tbl><w:p/>')


LOOK = ('<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="0" '
        'w:lastColumn="0" w:noHBand="0" w:noVBand="1"/>')


def testar_tabela_condicional() -> None:
    secao("tabela com formatacao condicional: estilo, tblLook e cnfStyle voltam")
    estilos = fx.ESTILOS_DO_WORD.replace("</w:styles>", ESTILO_FAIXAS + "</w:styles>")
    dados = fx.docx_com_estilos_do_word(_tabela_xml(LOOK), estilos)
    modelo, avisos = ler(dados)
    checa("ESTILO" not in codigos(avisos), f"sem aviso ESTILO ({codigos(avisos)})")
    tabela = next(b for b in modelo.paragrafos if isinstance(b, Tabela))
    checa_igual(tabela.estilo, "TabelaFaixas", "o modelo guarda o estilo da tabela")
    fundos = [linha.celulas[0].fundo_estilo for linha in tabela.linhas]
    checa_igual(fundos, ["4472C4", "D9E2F3", None, "D9E2F3"],
                "fundo da tela: cabecalho, faixa 1, faixa 2 (sem cor), faixa 1")
    gravado = escrever(modelo)
    raiz = xml_de(gravado)
    checa_igual(raiz.find(".//w:tblPr/w:tblStyle", NS).get("{%s}val" % W), "TabelaFaixas",
                "o tblStyle de origem volta (nao o Table Grid)")
    look = raiz.find(".//w:tblPr/w:tblLook", NS)
    orig = xml_de(dados).find(".//w:tblPr/w:tblLook", NS)
    checa(look is not None and etree.tostring(look, method="c14n") ==
          etree.tostring(orig, method="c14n"), "o tblLook volta igual (c14n)")
    checa_igual(len(raiz.findall(".//w:cnfStyle", NS)), len(xml_de(dados).findall(".//w:cnfStyle", NS)),
                "os cnfStyle (linha, celula e paragrafo) voltam")
    checa(not raiz.findall(".//w:tcPr/w:shd", NS), "o fundo condicional nao vira sombreamento direto")
    checa_igual(ordem.validar(fx.partes_de(gravado), modelo.estilos.virtuais()), [],
                "o arquivo gravado e' valido")
    conferencia.conferir(gravado, modelo)
    checa_igual(escrever(ler(gravado)[0]), gravado, "idempotente")

    sem_faixa = fx.docx_com_estilos_do_word(_tabela_xml(LOOK.replace('w:noHBand="0"', 'w:noHBand="1"')),
                                           estilos)
    t2 = next(b for b in ler(sem_faixa)[0].paragrafos if isinstance(b, Tabela))
    checa_igual([lin.celulas[0].fundo_estilo for lin in t2.linhas], ["4472C4", None, None, None],
                "contraprova: com noHBand as faixas nao pintam")

    if not QT:
        return
    from PySide6.QtGui import QTextCursor
    from editdoc.ponte_qt import de_qt, para_qt
    from editdoc.ponte_qt.imagens import DocumentoQt
    doc = DocumentoQt()
    para_qt.preencher(doc, modelo)
    c = QTextCursor(doc)
    c.setPosition(doc.toPlainText().index("l0c0") + 1)
    cel = c.currentTable().cellAt(c)
    cor = cel.format().background().color().name().upper()
    checa_igual(cor, "#4472C4", "na tela, a celula do cabecalho tem o fundo do estilo")
    volta = de_qt.extrair(doc)
    volta.pacote, volta.pagina = modelo.pacote, modelo.pagina
    tv = next(b for b in volta.paragrafos if isinstance(b, Tabela))
    checa(tv.estilo == "TabelaFaixas" and tv.linhas[0].celulas[0].sombreamento_hex is None,
          "de volta da tela: o estilo fica e o fundo nao vira sombreamento direto")
    gravado2 = escrever(volta)
    checa(not xml_de(gravado2).findall(".//w:tcPr/w:shd", NS)
          and ordem.validar(fx.partes_de(gravado2), volta.estilos.virtuais()) == [],
          "e o arquivo gravado a partir da tela continua sem shd e valido")


def main() -> int:
    if not QT:
        return pular("PySide6 nao instalado")
    testar_referencias()
    testar_tipo_errado()
    testar_aparencia()
    testar_garantir()
    testar_codigo_do_campo()
    testar_tabela_condicional()
    drenar_eventos()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
