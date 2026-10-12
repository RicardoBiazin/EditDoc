"""Validador de ordem de filhos e de xml:space, com contraprovas (sabotagens)."""

from __future__ import annotations

from ajudantes import checa, checa_igual, resumir, secao
import fixtures_docx as fx

from lxml import etree

from editdoc.formato_docx import ordem
from editdoc.formato_docx.nomes import XML_NS, q


def _raiz_document(docx: bytes):
    return etree.fromstring(fx.partes_de(docx)["word/document.xml"])


def testar_writer_limpo() -> None:
    secao("escritor: nenhuma violacao de ordem, xml:space ou pacote")
    docx = fx.bytes_de(fx.documento_completo())
    partes = fx.partes_de(docx)
    checa_igual(ordem.validar_ordem(_raiz_document(docx)), [], "ordem de pPr e rPr do escritor")
    checa_igual(ordem.validar_xml_space(_raiz_document(docx)), [],
                "xml:space nos w:t com espaco nas pontas")
    checa_igual(ordem.validar(partes), [], "validador completo sobre a saida do escritor")


def testar_sabotagem_ordem() -> None:
    secao("contraprova: rPr com b depois de i, e pPr com filho desconhecido, sao acusados")
    docx = fx.bytes_de(fx.documento_completo())
    raiz = _raiz_document(docx)
    rpr = None
    for el in raiz.iter(q("rPr")):
        if el.find(q("b")) is not None and el.find(q("i")) is not None:
            rpr = el
            break
    checa(rpr is not None, "fixture tem um rPr com negrito e italico")
    if rpr is not None:
        b = rpr.find(q("b"))
        i = rpr.find(q("i"))
        rpr.remove(b)
        i.addnext(b)
        achados = ordem.validar_ordem(raiz)
        checa(len(achados) >= 1, f"b depois de i e' acusado ({len(achados)})")
    raiz2 = _raiz_document(docx)
    ppr = raiz2.find(".//" + q("pPr"))
    if ppr is not None:
        ppr.append(etree.Element(q("inventado")))
        checa(any("inventado" in a for a in ordem.validar_ordem(raiz2)),
              "filho inexistente em pPr e' acusado")


def testar_sabotagem_xml_space() -> None:
    secao("contraprova: texto com espaco nas pontas sem xml:space e' acusado")
    docx = fx.bytes_de(fx.documento_completo())
    raiz = _raiz_document(docx)
    alvo = None
    for t in raiz.iter(q("t")):
        if t.text and t.text != t.text.strip():
            alvo = t
            break
    checa(alvo is not None, "fixture tem um w:t com espaco nas pontas")
    if alvo is not None:
        alvo.attrib.pop("{%s}space" % XML_NS, None)
        achados = ordem.validar_xml_space(raiz)
        checa(len(achados) == 1, f"sem xml:space o validador acusa ({len(achados)})")


def main() -> int:
    testar_writer_limpo()
    testar_sabotagem_ordem()
    testar_sabotagem_xml_space()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
