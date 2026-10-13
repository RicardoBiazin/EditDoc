"""Partes do pacote que o EditDoc nao edita (0.1.3): voltam ao arquivo, e nada some calado.

- inventario: as partes de um .docx como o Word grava (customXml com itemProps, custom.xml,
  fontTable com fonte embutida, webSettings, notas, settings.xml, core e app) e as que o
  arquivo gravado tem: so' a miniatura sai, e com aviso;
- byte a byte: cada parte preservada volta igual (C14N), com as relacoes (que resolvem) e o
  Override; o settings.xml volta com compat, rsids, docVars e a relacao externa do modelo,
  e so' o w:evenAndOddHeaders muda (na ordem do esquema); o core e o app voltam com os
  campos do Word, e titulo, autor e aplicativo reescritos;
- notas: as separadoras voltam; a nota de verdade nao, com o aviso NOTA, e o settings.xml
  continua citando so' o que existe;
- o que nao pode voltar avisa: relacao quebrada (PARTE_PERDIDA), XML invalido, relacao
  interna do settings.xml quebrada (o elemento sai), macros (MACROS), assinatura;
- conferencia e validador acusam a parte preservada trocada; a janela salva sem perder.
"""

from __future__ import annotations

import contextlib
import posixpath

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt, pular,
                       resumir, secao)
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx.escritor import escrever, escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
EP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

#: Partes preservadas byte a byte (comparadas em C14N), pelo nome no pacote.
PRESERVADAS = ("customXml/item1.xml", "customXml/itemProps1.xml", "docProps/custom.xml",
               "word/fontTable.xml", "word/webSettings.xml", "word/footnotes.xml")


def c14n(dados: bytes) -> bytes:
    return etree.tostring(etree.fromstring(dados), method="c14n")


def codigos(avisos) -> dict[str, tuple[int, bool]]:
    return {a.codigo: (a.contagem, a.perde_ao_salvar) for a in avisos}


def relacoes(partes: dict, parte: str) -> dict:
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


def tipos(partes: dict) -> dict:
    raiz = etree.fromstring(partes["[Content_Types].xml"])
    return {o.get("PartName"): o.get("ContentType") for o in raiz.iter("{%s}Override" % PKG_CT)}


def filhos_settings(dados: bytes) -> list[str]:
    return [etree.QName(f).localname for f in etree.fromstring(dados)]


def testar_inventario() -> None:
    secao("inventario: o que o Word grava e o que o arquivo gravado tem")
    origem = fx.docx_com_pacote_do_word()
    modelo, avisos = ler(origem)
    dados, avisos_g = escrever_com_avisos(modelo)
    antes, depois = set(fx.partes_de(origem)), set(fx.partes_de(dados))
    checa_igual(sorted(antes - depois), ["docProps/thumbnail.jpeg"],
                "so' a miniatura sai do pacote (antes da 0.1.3 saiam 13 partes sem aviso)")
    checa_igual(sorted(depois - antes), [], "e nenhuma parte nova aparece")
    checa_igual(codigos(avisos), {"NOTA": (1, True), "MINIATURA": (1, False)},
                "avisos: a nota de verdade (perda) e a miniatura (sem perda); nada calado")
    checa_igual(avisos_g, [], "a gravacao nao gera aviso")
    checa_igual(ordem.validar(fx.partes_de(dados)), [], "o pacote gravado passa no validador")
    # Contraprova do inventario: sem a 0.1.3, o documento novo (sem pacote) nao teria as partes.
    sem = escrever(Documento(paragrafos=modelo.paragrafos, estilos=modelo.estilos))
    checa("customXml/item1.xml" not in fx.partes_de(sem),
          "contraprova: o modelo sem o pacote de origem nao inventa as partes")


def testar_byte_a_byte() -> None:
    secao("byte a byte: partes preservadas, relacoes, tipos e o settings.xml do Word")
    origem = fx.partes_de(fx.docx_com_pacote_do_word())
    modelo, _ = ler(fx.montar(origem))
    gravado = fx.partes_de(escrever(modelo))
    for nome in PRESERVADAS:
        checa(nome in gravado and c14n(gravado[nome]) == c14n(origem[nome]),
              f"{nome} volta igual (C14N)")
    checa_igual(gravado["word/fonts/font1.odttf"], fx.FONTE_EMBUTIDA, "a fonte embutida volta byte a byte")
    rels_fontes = relacoes(gravado, "word/fontTable.xml")
    checa_igual(rels_fontes.get("rId1"), (fx.RT_FONTE, "word/fonts/font1.odttf", False),
                "o r:id da fonte embutida resolve para a parte (Id mantido)")
    checa_igual(relacoes(gravado, "customXml/item1.xml").get("rId1"),
                (fx.RT_CUSTOM_XML_PROPS, "customXml/itemProps1.xml", False),
                "o item do customXml continua apontando para o itemProps")
    doc_rels = {(t, a) for t, a, _e in relacoes(gravado, "word/document.xml").values()}
    for tipo, alvo in ((fx.RT_CUSTOM_XML, "customXml/item1.xml"), (fx.RT_FONTES, "word/fontTable.xml"),
                       (fx.RT_WEB, "word/webSettings.xml"), (fx.RT_NOTAS, "word/footnotes.xml"),
                       (fx.RT_NOTAS_FIM, "word/endnotes.xml")):
        checa((tipo, alvo) in doc_rels, f"relacao do documento: {tipo.rsplit('/', 1)[1]} -> {alvo}")
    pacote = {(r.get("Type"), r.get("Target")) for r in etree.fromstring(gravado["_rels/.rels"])}
    checa((fx.RT_PROPRIEDADES, "docProps/custom.xml") in pacote, "relacao do pacote para o custom.xml")
    ct = tipos(gravado)
    for parte, tipo in (("/customXml/itemProps1.xml", fx.CT_CUSTOM_XML_PROPS),
                        ("/word/fontTable.xml", fx.CT_FONTES), ("/word/webSettings.xml", fx.CT_WEB),
                        ("/docProps/custom.xml", fx.CT_PROPRIEDADES),
                        ("/word/fonts/font1.odttf", fx.CT_FONTE),
                        ("/customXml/item1.xml", "application/xml")):
        checa_igual(ct.get(parte), tipo, f"Override de {parte}")

    # settings.xml: o original, inteiro.
    checa(c14n(gravado["word/settings.xml"]) == c14n(origem["word/settings.xml"]),
          "settings.xml volta igual quando o EditDoc nao muda nada (compat, rsids, docVars...)")
    rels_cfg = relacoes(gravado, "word/settings.xml")
    checa_igual(rels_cfg.get("rId1"), (fx.RT_MODELO, "file:///C:/Modelos/Oficio.dotx", True),
                "a relacao externa do modelo anexado volta com o settings.xml")
    # Pares e impares ligado: so' o w:evenAndOddHeaders entra, na ordem do esquema.
    modelo.pagina.pares_impares = True
    ligado = fx.partes_de(escrever(modelo))
    filhos = filhos_settings(ligado["word/settings.xml"])
    checa("evenAndOddHeaders" in filhos and
          filhos.index("hyphenationZone") < filhos.index("evenAndOddHeaders")
          < filhos.index("characterSpacingControl"),
          "evenAndOddHeaders entra entre hyphenationZone e characterSpacingControl (CT_Settings)")
    sem_ele = etree.fromstring(ligado["word/settings.xml"])
    sem_ele.remove(sem_ele.find("{%s}evenAndOddHeaders" % W))
    checa(etree.tostring(sem_ele, method="c14n") == c14n(origem["word/settings.xml"]),
          "e e' a unica mudanca no settings.xml")
    relido, _ = ler(fx.montar(ligado))
    checa(relido.pagina.pares_impares, "relido: pares e impares ligado")
    relido.pagina.pares_impares = False
    desligado = fx.partes_de(escrever(relido))
    checa(c14n(desligado["word/settings.xml"]) == c14n(origem["word/settings.xml"]),
          "desligar tira o elemento e o settings.xml volta a ser o original")

    # core.xml e app.xml: os campos do Word ficam; titulo, autor e aplicativo sao do EditDoc.
    modelo.titulo = "Título novo"
    gravado = fx.partes_de(escrever(modelo))
    core = gravado["docProps/core.xml"].decode("utf-8")
    checa("<dc:subject>Assunto do relatório</dc:subject>" in core
          and "<cp:keywords>faturamento; 2026</cp:keywords>" in core
          and "<cp:category>Interno</cp:category>" in core and "<cp:revision>7</cp:revision>" in core,
          "core.xml: assunto, palavras-chave, categoria e revisao do Word ficam")
    checa("<dc:title>Título novo</dc:title>" in core and "<dc:creator>Fulana</dc:creator>" in core
          and "2026-01-02T03:04:00Z" in core, "core.xml: titulo novo, autor e criacao do original")
    app = etree.fromstring(gravado["docProps/app.xml"])
    checa(app.findtext("{%s}Company" % EP) == "Empresa Exemplo"
          and app.findtext("{%s}Manager" % EP) == "Gerente"
          and app.findtext("{%s}Application" % EP) == "EditDoc"
          and app.find("{%s}AppVersion" % EP) is None,
          "app.xml: empresa e gerente ficam; o aplicativo passa a ser o EditDoc, sem a versao do Word")
    checa_igual(ordem.validar(gravado), [], "o pacote com tudo reescrito passa no validador")


def testar_notas() -> None:
    secao("notas: as separadoras voltam; a nota de verdade sai com aviso")
    origem = fx.partes_de(fx.docx_com_pacote_do_word())
    modelo, avisos = ler(fx.montar(origem))
    gravado = fx.partes_de(escrever(modelo))
    fim = etree.fromstring(gravado["word/endnotes.xml"])
    tipos_notas = [n.get("{%s}type" % W) for n in fim.findall("{%s}endnote" % W)]
    checa_igual(tipos_notas, ["separator", "continuationSeparator"],
                "endnotes.xml volta so' com as notas separadoras")
    checa(codigos(avisos).get("NOTA") == (1, True), "a nota de verdade tem o aviso NOTA, com perda")
    ids = [e.get("{%s}id" % W) for e in etree.fromstring(gravado["word/settings.xml"]).iter(
        "{%s}endnote" % W)]
    checa_igual(ids, ["-1", "0"], "o settings.xml cita as notas separadoras, que existem")
    # Sem a parte de notas (nao pode voltar), o settings.xml deixa de citar as separadoras.
    quebrado = fx.docx_com_pacote_do_word(extra={"word/footnotes.xml": None})
    modelo_q, avisos_q = ler(quebrado)
    gravado_q = fx.partes_de(escrever(modelo_q))
    cfg = etree.fromstring(gravado_q["word/settings.xml"])
    checa("word/footnotes.xml" not in gravado_q and cfg.find(".//{%s}footnote" % W) is None
          and cfg.find("{%s}footnotePr" % W) is not None,
          "sem footnotes.xml, o footnotePr fica sem citar nota que nao existe")
    checa("PARTE_PERDIDA" in codigos(avisos_q), "e a parte que faltava avisa (PARTE_PERDIDA)")
    checa_igual(ordem.validar(gravado_q), [], "e o pacote passa no validador")


def testar_o_que_nao_volta() -> None:
    secao("o que nao pode voltar avisa: relacao quebrada, XML invalido, macros, assinatura")
    # customXml sem o itemProps: o item nao vai (iria com relacao quebrada).
    sem_props = fx.docx_com_pacote_do_word(extra={"customXml/itemProps1.xml": None})
    modelo, avisos = ler(sem_props)
    gravado = fx.partes_de(escrever(modelo))
    checa(codigos(avisos).get("PARTE_PERDIDA", (0,))[0] >= 1 and "customXml/item1.xml" not in gravado,
          "item do customXml com relacao quebrada: nao volta, com o aviso PARTE_PERDIDA")
    checa_igual(ordem.validar(gravado), [], "e o pacote continua valido")
    # XML invalido numa parte preservada.
    invalido = fx.docx_com_pacote_do_word(extra={"word/webSettings.xml": b"<w:webSettings"})
    modelo, avisos = ler(invalido)
    gravado = fx.partes_de(escrever(modelo))
    checa("PARTE_PERDIDA" in codigos(avisos) and "word/webSettings.xml" not in gravado,
          "webSettings.xml invalido: nao volta, com aviso")
    # Relacao interna do settings.xml que nao existe: o elemento que a cita sai.
    rels = fx.SETTINGS_RELS.replace('Target="file:///C:/Modelos/Oficio.dotx" TargetMode="External"',
                                    'Target="naoexiste.dotx"')
    modelo, avisos = ler(fx.docx_com_pacote_do_word(extra={
        "word/_rels/settings.xml.rels": rels.encode("utf-8")}))
    gravado = fx.partes_de(escrever(modelo))
    checa("attachedTemplate" not in gravado["word/settings.xml"].decode("utf-8")
          and "PARTE_PERDIDA" in codigos(avisos) and ordem.validar(gravado) == [],
          "settings.xml com relacao quebrada: o attachedTemplate sai, com aviso, e o pacote fica valido")
    # Macros: a relacao vbaProject nao volta, com o aviso MACROS.
    partes = fx.partes_de(fx.docx_com_pacote_do_word())
    partes["word/vbaProject.bin"] = b"\xd0\xcf\x11\xe0 macro"
    partes["word/_rels/document.xml.rels"] = partes["word/_rels/document.xml.rels"].replace(
        b"</Relationships>", b'<Relationship Id="rId90" Type="http://schemas.microsoft.com/office/'
        b'2006/relationships/vbaProject" Target="vbaProject.bin"/></Relationships>')
    partes["[Content_Types].xml"] = partes["[Content_Types].xml"].replace(
        b"</Types>", b'<Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/>'
        b"</Types>")
    modelo, avisos = ler(fx.montar(partes))
    gravado = fx.partes_de(escrever(modelo))
    checa("MACROS" in codigos(avisos) and "word/vbaProject.bin" not in gravado,
          "vbaProject: nao volta, com o aviso MACROS")
    # Controle ActiveX (roda codigo no Word): o objeto que o usa nao e' preservado.
    corpo = ('<w:p><w:r><w:object><w:control r:id="rId95" w:name="CheckBox1" '
             'w:shapeid="_x0000_i1025"/></w:object></w:r></w:p>')
    partes = fx.partes_de(fx.docx_com_pacote_do_word(corpo_xml=corpo))
    partes["word/activeX/activeX1.xml"] = (b'<?xml version="1.0"?><ax:ocx xmlns:ax="http://schemas.'
                                           b'microsoft.com/office/2006/activeX" ax:classid="{1}"/>')
    partes["word/_rels/document.xml.rels"] = partes["word/_rels/document.xml.rels"].replace(
        b"</Relationships>", b'<Relationship Id="rId95" Type="http://schemas.openxmlformats.org/'
        b'officeDocument/2006/relationships/control" Target="activeX/activeX1.xml"/></Relationships>')
    partes["[Content_Types].xml"] = partes["[Content_Types].xml"].replace(
        b"</Types>", b'<Override PartName="/word/activeX/activeX1.xml" '
        b'ContentType="application/vnd.ms-office.activeX+xml"/></Types>')
    modelo, avisos = ler(fx.montar(partes))
    gravado = fx.partes_de(escrever(modelo))
    checa("OBJETO_PERDIDO" in codigos(avisos) and not any("activeX" in n for n in gravado)
          and ordem.validar(gravado) == [],
          "controle ActiveX: nao volta (OBJETO_PERDIDO, com perda), e o pacote fica valido")
    # Assinatura digital: deixaria de valer.
    partes = fx.partes_de(fx.docx_com_pacote_do_word())
    partes["_xmlsignatures/origin.sigs"] = b""
    partes["_rels/.rels"] = partes["_rels/.rels"].replace(
        b"</Relationships>", b'<Relationship Id="rId20" Type="http://schemas.openxmlformats.org/'
        b'package/2006/relationships/digital-signature/origin" Target="_xmlsignatures/origin.sigs"/>'
        b"</Relationships>")
    partes["[Content_Types].xml"] = partes["[Content_Types].xml"].replace(
        b"</Types>", b'<Default Extension="sigs" ContentType="application/vnd.openxmlformats-'
        b'package.digital-signature-origin"/></Types>')
    modelo, avisos = ler(fx.montar(partes))
    gravado = fx.partes_de(escrever(modelo))
    checa(codigos(avisos).get("ASSINATURA", (0, False))[1] and "_xmlsignatures/origin.sigs" not in gravado,
          "assinatura digital: sai com o aviso ASSINATURA (com perda)")
    # Parte preservada que bate com o nome de parte do escritor e' renomeada, e continua valida.
    partes = fx.partes_de(fx.docx_com_pacote_do_word())
    partes["word/_rels/document.xml.rels"] = partes["word/_rels/document.xml.rels"].replace(
        b'Target="webSettings.xml"', b'Target="header1.xml"')
    partes["word/header1.xml"] = partes.pop("word/webSettings.xml")
    partes["[Content_Types].xml"] = partes["[Content_Types].xml"].replace(
        b'PartName="/word/webSettings.xml"', b'PartName="/word/header1.xml"')
    modelo, avisos = ler(fx.montar(partes))
    gravado = fx.partes_de(escrever(modelo))
    renomeada = [n for n, d in gravado.items() if d == fx.WEB_DO_WORD.encode("utf-8")]
    checa(renomeada and renomeada[0] != "word/header1.xml" and ordem.validar(gravado) == [],
          f"parte com nome que o escritor usa volta com outro nome ({renomeada[:1]})")


def testar_conferencia() -> None:
    secao("conferencia e validador: a parte preservada trocada e' acusada")
    origem = fx.docx_com_pacote_do_word()
    modelo, _ = ler(origem)
    dados = escrever(modelo)
    conferencia.conferir(dados, modelo)
    checa(True, "a conferencia aceita o arquivo com as partes preservadas")
    trocado = fx.com_parte(dados, "docProps/custom.xml", fx.PROPRIEDADES.replace(
        "Hospital Exemplo", "Outro").encode("utf-8"))
    try:
        conferencia.conferir(trocado, modelo)
        checa(False, "contraprova: custom.xml trocado passaria pela conferencia")
    except conferencia.FalhaDeConferencia as erro:
        checa("preservadas" in str(erro), f"contraprova: custom.xml trocado e' acusado ({erro})")
    partes = fx.partes_de(dados)
    del partes["customXml/itemProps1.xml"]
    checa(any("itemProps1.xml" in p for p in ordem.validar(partes)),
          "contraprova do validador: a relacao do customXml para parte que falta e' acusada")
    partes = fx.partes_de(dados)
    partes["[Content_Types].xml"] = partes["[Content_Types].xml"].replace(
        b'<Override PartName="/word/fontTable.xml"', b'<Override PartName="/word/outra.xml"')
    checa(any("fontTable" in p for p in ordem.validar(partes)),
          "contraprova do validador: parte preservada sem Override e' acusada")


def testar_limites() -> None:
    secao("limites: muitas partes no fecho viram aviso, sem travar")
    partes = fx.partes_de(fx.docx_com_pacote_do_word())
    rels = ['<Relationship Id="rId%d" Type="%s" Target="itemProps%d.xml"/>' % (i, fx.RT_CUSTOM_XML_PROPS, i)
            for i in range(2, 1200)]
    partes["customXml/_rels/item1.xml.rels"] = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.'
                                                'openxmlformats.org/package/2006/relationships">'
                                                + "".join(rels) + "</Relationships>").encode("utf-8")
    for i in range(2, 1200):
        partes[f"customXml/itemProps{i}.xml"] = fx.ITEM_PROPS.encode("utf-8")
    partes["[Content_Types].xml"] = partes["[Content_Types].xml"].replace(
        b"</Types>", b"".join(b'<Override PartName="/customXml/itemProps%d.xml" ContentType="%s"/>'
                              % (i, fx.CT_CUSTOM_XML_PROPS.encode()) for i in range(2, 1200))
        + b"</Types>")
    modelo, avisos = ler(fx.montar(partes))
    gravado = fx.partes_de(escrever(modelo))
    checa("PARTE_PERDIDA" in codigos(avisos) and "customXml/item1.xml" not in gravado
          and ordem.validar(gravado) == [],
          "customXml com 1200 partes no fecho (limite 1000): nao volta, com aviso, e o arquivo e' valido")


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


def testar_janela() -> None:
    secao("janela: abrir, editar e salvar mantem as partes do pacote")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from editdoc import configuracao
    from editdoc.interface.gerente import GerenteDeJanelas

    with pasta_temporaria() as tmp:
        arquivo = tmp / "pacote.docx"
        arquivo.write_bytes(fx.docx_com_pacote_do_word())
        origem = fx.partes_de(arquivo.read_bytes())
        gerente = GerenteDeJanelas(configuracao.padrao())
        janela = gerente.abrir(str(arquivo))
        painel = janela.painel
        painel.setFocus()
        cursor = painel.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        painel.setTextCursor(cursor)
        QTest.keyClick(painel, Qt.Key.Key_Exclam)
        perguntas = []
        with dialogos(pedir_perda=lambda _p, _n, linhas: perguntas.append(linhas) or "salvar"):
            checa(janela.salvar() is True, "salvar pela janela grava")
        checa(perguntas and any("nota" in t for t in perguntas[0])
              and not any("parte" in t.lower() for t in perguntas[0]),
              "a confirmacao lista so' a nota de verdade (nenhuma parte do pacote se perde)")
        gravado = fx.partes_de(arquivo.read_bytes())
        checa(all(c14n(gravado[n]) == c14n(origem[n]) for n in PRESERVADAS),
              "o arquivo salvo pela janela tem as partes preservadas iguais")
        checa(c14n(gravado["word/settings.xml"]) == c14n(origem["word/settings.xml"]),
              "e o settings.xml do Word")
        checa_igual(ordem.validar(gravado), [], "e passa no validador")
        with dialogos(pedir_descartar=lambda *_a: "descartar"):
            for j in gerente.janelas():
                j.close()
        drenar_eventos()
    # Documento novo: continua sem partes inventadas.
    dados = escrever(Documento(paragrafos=[Paragrafo(runs=[Run("novo")])]))
    checa(not any(n.startswith("customXml") or n.endswith("fontTable.xml") for n in fx.partes_de(dados)),
          "documento novo nao ganha parte preservada nenhuma")


def main() -> int:
    testar_inventario()
    testar_byte_a_byte()
    testar_notas()
    testar_o_que_nao_volta()
    testar_conferencia()
    testar_limites()
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    testar_janela()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
