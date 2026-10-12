"""Integridade OPC: relacoes resolvidas, tipos de conteudo, partes orfas e r:id.

Cada regra tem uma sabotagem que TEM de ser acusada. Sem isso o validador podia
estar sempre dizendo "limpo" e ninguem perceberia.
"""

from __future__ import annotations

import re

from ajudantes import checa, checa_igual, resumir, secao
import fixtures_docx as fx

from editdoc.formato_docx import ordem


def _com(partes: dict[str, bytes], nome: str, dados: bytes | None) -> dict[str, bytes]:
    nova = dict(partes)
    if dados is None:
        nova.pop(nome, None)
    else:
        nova[nome] = dados
    return nova


def testar_pacote_do_escritor() -> None:
    secao("pacote do escritor: integridade OPC sem violacao")
    partes = fx.partes_de(fx.bytes_de(fx.documento_completo()))
    checa_igual(ordem.validar_pacote(partes), [], "pacote do escritor esta integro")
    checa_igual(sorted(partes), sorted([
        "[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/_rels/document.xml.rels",
        "word/styles.xml", "word/numbering.xml", "word/settings.xml",
        "docProps/core.xml", "docProps/app.xml"]), "partes do pacote minimo")


def testar_sabotagens() -> None:
    secao("contraprovas: cada defeito de pacote e' acusado")
    base = fx.partes_de(fx.bytes_de(fx.documento_completo()))

    sem_tipo = _com(base, "[Content_Types].xml",
                    re.sub(rb'<Override PartName="/word/styles.xml"[^>]*/>', b"",
                           base["[Content_Types].xml"]))
    achados = ordem.validar_pacote(sem_tipo)
    checa(any("styles.xml" in a and "tipo de conteudo" in a for a in achados)
          or any("styles.xml" in a for a in achados),
          "parte sem Override (styles.xml) e' acusada")

    relacao_quebrada = _com(base, "word/_rels/document.xml.rels",
                            base["word/_rels/document.xml.rels"].replace(
                                b'Target="styles.xml"', b'Target="estilos_nao_existe.xml"'))
    achados = ordem.validar_pacote(relacao_quebrada)
    checa(any("inexistente" in a for a in achados), "relacao para parte inexistente e' acusada")

    sem_relacao = _com(base, "word/_rels/document.xml.rels",
                       re.sub(rb'<Relationship Id="rId3"[^>]*/>', b"",
                              base["word/_rels/document.xml.rels"]))
    achados = ordem.validar_pacote(sem_relacao)
    checa(any("numbering.xml" in a and "orfa" in a for a in achados),
          "numbering.xml sem relacao e' acusado como parte orfa")

    orfa = _com(base, "word/extra.xml", b"<x/>")
    orfa = _com(orfa, "[Content_Types].xml",
                orfa["[Content_Types].xml"].replace(
                    b"</Types>", b'<Override PartName="/word/extra.xml" ContentType="application/xml"/></Types>'))
    achados = ordem.validar_pacote(orfa)
    checa(any("extra.xml" in a and "orfa" in a for a in achados), "parte orfa e' acusada")

    doc_com_rid = base["word/document.xml"].replace(
        b"<w:body>", b'<w:body><w:p xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId99"/>', 1)
    achados = ordem.validar_pacote(_com(base, "word/document.xml", doc_com_rid))
    checa(any("rId99" in a for a in achados), "r:id sem relacao no corpo e' acusado")

    sem_documento = _com(base, "word/document.xml", None)
    checa(any("inexistente" in a or "ausente" in a for a in ordem.validar_pacote(sem_documento)),
          "documento principal ausente e' acusado")

    sem_ct = _com(base, "[Content_Types].xml", None)
    checa(ordem.validar_pacote(sem_ct) == ["[Content_Types].xml ausente"],
          "pacote sem [Content_Types].xml e' acusado")


def main() -> int:
    testar_pacote_do_escritor()
    testar_sabotagens()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
