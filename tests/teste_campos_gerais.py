"""Campos quaisquer (0.1.3): TOC, PAGEREF, REF, DATE, AUTHOR, IF, XE e FORMTEXT voltam ao
arquivo como campos que o Word atualiza.

- leitura: o sumario de tres paragrafos vira inicio no 1o e fim no 3o, com os hiperlinks e
  os PAGEREF dentro; REF, DATE (sujo), campo simples, IF com PAGE no codigo, XE sem
  resultado e o FORMTEXT com o w:ffData viram marcas com o codigo; nenhum aviso;
- gravacao: as mesmas quantidades de begin, separate e end, as mesmas instrucoes por tipo,
  w:dirty e w:ffData mantidos, o XE sem separate; ida e volta, idempotencia, validador
  (campos equilibrados na parte inteira, codigo no paragrafo do begin) e conferencia;
- contraprovas do validador: end sem begin, begin sem end, separate em outro paragrafo e
  instrText fora do codigo;
- edicao: o resultado do campo e' texto editavel (vira o novo resultado); apagar o inicio
  (ou o fim) de um campo, inclusive o fim do sumario em outro paragrafo, grava XML valido,
  com o aviso CAMPO_INCOMPLETO; PAGE com o resultado editado continua PAGE;
- tela: os colchetes do campo aparecem na tela e nao no PDF;
- limites: campos demais, instrucao enorme e aninhamento fundo viram aviso, sem travar.
"""

from __future__ import annotations

import collections
import contextlib
import re
import time

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt, pular,
                       resumir, secao)
import fixtures_docx as fx

QT = preparar_qt()

from lxml import etree  # noqa: E402

from editdoc.formato_docx import conferencia, ordem  # noqa: E402
from editdoc.formato_docx.escritor import escrever, escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo import marcas as mod_marcas  # noqa: E402
from editdoc.modelo.documento import (Campo, Documento, MarcaCampo, Paragrafo, Run,  # noqa: E402
                                      normalizar)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def codigos(avisos) -> dict[str, int]:
    return {a.codigo: a.contagem for a in avisos}


def contagem(xml: str) -> dict:
    tipos = collections.Counter(re.findall(r'w:fldCharType="(\w+)"', xml))
    instr = collections.Counter(t.split()[0] for t in re.findall(r"<w:instrText[^>]*>([^<]*)<", xml)
                                if t.strip())
    return {"fld": dict(tipos), "instr": dict(instr), "hyperlink": xml.count("<w:hyperlink"),
            "bookmark": xml.count("<w:bookmarkStart")}


def marcas_de(paragrafo) -> list:
    saida = []
    for r in paragrafo.runs:
        if isinstance(r.marca, MarcaCampo):
            saida.append(r.marca.campo.tipo() if r.marca.tipo == "inicio" else "/")
    return saida


def testar_leitura() -> None:
    secao("leitura: sumario de varios paragrafos, REF, DATE, simples, IF, XE e FORMTEXT")
    modelo, avisos = ler(fx.docx_com_campos())
    checa_igual(codigos(avisos), {"FORMATACAO": 1}, "nenhum aviso de campo (so' o do styles.xml de teste)")
    ps = modelo.paragrafos
    checa_igual([marcas_de(p) for p in ps[:3]], [["TOC", "PAGEREF", "/"], ["PAGEREF", "/"], ["/"]],
                "TOC: inicio no 1o paragrafo, fim no 3o; os PAGEREF dentro de cada linha")
    linha = ps[0].runs
    checa(all(r.link is not None and r.link.ancora == "_Toc1" for r in linha[1:]),
          "a linha do sumario: o titulo, a tabulacao e o PAGEREF dentro do hiperlink")
    checa_igual(marcas_de(ps[4]), ["REF", "/", "DATE", "/", "AUTHOR", "/"], "REF, DATE e o campo simples (AUTHOR)")
    data = next(r.marca.campo for r in ps[4].runs if isinstance(r.marca, MarcaCampo)
                and r.marca.campo and r.marca.campo.tipo() == "DATE")
    checa(data.sujo, "o w:dirty do DATE e' lido")
    se = ps[5].runs[0].marca.campo
    checa(se.tipo() == "IF" and isinstance(se.codigo[1], Campo) and se.codigo[1].tipo() == "PAGE",
          "IF com PAGE dentro do codigo")
    xe = next(r.marca.campo for r in ps[5].runs if isinstance(r.marca, MarcaCampo)
              and r.marca.campo and r.marca.campo.tipo() == "XE")
    checa(xe.sem_resultado, "XE: campo sem separate (sem resultado)")
    formulario = ps[6].runs[1].marca.campo
    checa(formulario.tipo() == "FORMTEXT" and b"ffData" in formulario.extra,
          "FORMTEXT: o w:ffData do begin e' guardado")
    checa_igual("".join(r.texto for r in ps[4].runs), "Ver Conclusão, em 12/10/2026, por Fulana.",
                "o texto dos resultados e' o que o Word mostrava")


def testar_gravacao() -> None:
    secao("gravacao: as mesmas marcas de campo, validador, ida e volta e conferencia")
    origem = fx.docx_com_campos()
    modelo, _ = ler(origem)
    dados, avisos = escrever_com_avisos(modelo)
    partes = fx.partes_de(dados)
    xml_o = fx.partes_de(origem)["word/document.xml"].decode("utf-8")
    xml = partes["word/document.xml"].decode("utf-8")
    checa_igual(avisos, [], "gravar os campos nao gera aviso")
    checa_igual(ordem.validar(partes), [], "o pacote passa no validador")
    a, b = contagem(xml_o), contagem(xml)
    checa_igual(b["fld"], {"begin": 10, "separate": 9, "end": 10},
                "begin, separate e end: o campo simples vira complexo, o XE fica sem separate")
    checa_igual(b["instr"], {**a["instr"], "AUTHOR": 1}, "as mesmas instrucoes por tipo (mais o AUTHOR)")
    checa_igual((b["hyperlink"], b["bookmark"]), (a["hyperlink"], a["bookmark"]),
                "os hiperlinks e os marcadores do sumario tambem")
    checa('w:fldCharType="begin" w:dirty="true"' in xml, "w:dirty mantido no DATE")
    checa('<w:ffData><w:name w:val="Texto1"/>' in xml, "w:ffData mantido no FORMTEXT")
    raiz = etree.fromstring(partes["word/document.xml"])
    p1 = raiz.find("{%s}body" % W)[0]
    p3 = raiz.find("{%s}body" % W)[2]
    checa(p1.find(".//{%s}fldChar" % W).get("{%s}fldCharType" % W) == "begin"
          and [f.get("{%s}fldCharType" % W) for f in p3.iter("{%s}fldChar" % W)] == ["end"],
          "o begin do TOC fica no 1o paragrafo e o end no 3o")
    relido, avisos_r = ler(dados)
    checa(normalizar(relido).paragrafos == normalizar(modelo).paragrafos, "ida e volta: o modelo volta igual")
    checa_igual(avisos_r, [], "o arquivo gravado abre sem aviso")
    checa(escrever(relido) == escrever(ler(escrever(relido))[0]), "a segunda ida produz os mesmos bytes")
    conferencia.conferir(dados, modelo)
    checa(True, "a conferencia aceita os campos")
    # Contraprova da conferencia: o codigo do REF trocado.
    trocado = xml.replace(" REF _Toc2 ", " REF _Toc1 ")
    try:
        conferencia.conferir(fx.com_parte(dados, "word/document.xml", trocado.encode("utf-8")), modelo)
        checa(False, "contraprova: o codigo trocado passaria pela conferencia")
    except conferencia.FalhaDeConferencia as erro:
        checa("campo" in str(erro), f"contraprova: codigo de campo trocado e' acusado ({erro})")


def testar_validador() -> None:
    secao("validador: campos equilibrados na parte inteira (contraprovas)")
    dados = escrever(ler(fx.docx_com_campos())[0])
    xml = fx.partes_de(dados)["word/document.xml"].decode("utf-8")
    fim = '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    casos = {
        "begin sem end": xml.replace(fim, "", 1),
        "end sem begin": xml.replace("<w:body>", "<w:body><w:p>" + fim + "</w:p>", 1),
        "separate em outro paragrafo": xml.replace(
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:hyperlink', '</w:p><w:p>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:hyperlink', 1),
        "instrText fora do codigo": xml.replace(
            "<w:body>", '<w:body><w:p><w:r><w:instrText xml:space="preserve"> X </w:instrText></w:r></w:p>', 1),
    }
    for nome, sabotado in casos.items():
        partes = fx.partes_de(dados)
        partes["word/document.xml"] = sabotado.encode("utf-8")
        checa(any("fldChar" in p for p in ordem.validar(partes)), f"contraprova: {nome} e' acusado")


def _documento_de(painel):
    from editdoc.ponte_qt import de_qt
    return de_qt.extrair(painel.documento_corpo())


def _painel_com(modelo):
    from editdoc.interface.painel_documento import PainelDocumento
    from editdoc.ponte_qt import para_qt
    painel = PainelDocumento("Calibri", 11)
    painel.resize(1000, 800)
    painel.show()
    drenar_eventos(2)
    para_qt.preencher(painel.documento_corpo(), modelo)
    drenar_eventos(2)
    painel.setFocus()
    return painel


def testar_edicao() -> None:
    secao("edicao: resultado editavel; apagar metade do campo grava XML valido, com aviso")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    modelo, _ = ler(fx.docx_com_campos())
    painel = _painel_com(modelo)
    doc = painel.documento_corpo()
    volta = _documento_de(painel)
    checa(normalizar(volta).paragrafos == normalizar(Documento(paragrafos=modelo.paragrafos)).paragrafos,
          "Qt ida e volta: as marcas, os codigos e os resultados voltam iguais")
    total_de_marcas = len(_marcas_de_campo(doc))
    checa_igual(total_de_marcas, 18, "as 18 marcas dos 9 campos estao no documento do Qt")
    # Editar o resultado do REF: vira o novo resultado, e o campo continua.
    texto = doc.toPlainText()
    pos = texto.index("Conclusão￼,") + len("Conclusão")  # antes da marca de fim
    cursor = painel.textCursor()
    cursor.setPosition(pos)
    painel.setTextCursor(cursor)
    for letra in (Qt.Key.Key_X, Qt.Key.Key_Y):
        QTest.keyClick(painel, letra)
    editado = _documento_de(painel)
    p = editado.paragrafos[4]
    checa("Conclusãoxy" in "".join(r.texto for r in p.runs),
          "digitar no fim do resultado do REF: o texto entra no resultado")
    dados, avisos = escrever_com_avisos(editado)
    xml = fx.partes_de(dados)["word/document.xml"].decode("utf-8")
    checa(re.search(r"REF _Toc2 .*?separate.*?Conclus.o.{2}</w:t>.*?end", xml, re.S) is not None
          and avisos == [], "gravado: o resultado editado fica entre o separate e o end do REF, sem aviso")
    # Apagar o inicio do DATE (Backspace logo depois da marca).
    inicio_date = [k for k in _marcas_de_campo(doc) if _codigo(doc, k) == "DATE"][0]
    cursor.setPosition(inicio_date + 1)
    painel.setTextCursor(cursor)
    QTest.keyClick(painel, Qt.Key.Key_Backspace)
    meio = _documento_de(painel)
    dados, avisos = escrever_com_avisos(meio)
    partes = fx.partes_de(dados)
    checa(ordem.validar(partes) == [] and codigos(avisos) == {"CAMPO_INCOMPLETO": 1},
          "apagar o inicio do DATE: XML valido e o aviso CAMPO_INCOMPLETO (com perda)")
    checa(any(a.perde_ao_salvar for a in avisos), "o aviso CAMPO_INCOMPLETO pede confirmacao")
    xml = partes["word/document.xml"].decode("utf-8")
    checa("DATE" not in xml and "12/10/2026" in xml, "o DATE sai como campo; o resultado fica como texto")
    conferencia.conferir(dados, meio)
    checa(True, "a conferencia aceita o campo desfeito (compara com o documento equilibrado)")
    # Apagar o fim do sumario, que esta' em outro paragrafo.
    fim_toc = [k for k in _marcas_de_campo(doc) if _codigo(doc, k) == "/"][2]
    cursor.setPosition(fim_toc)
    cursor.setPosition(fim_toc + 1, cursor.MoveMode.KeepAnchor)
    painel.setTextCursor(cursor)
    QTest.keyClick(painel, Qt.Key.Key_Delete)
    sem_fim = _documento_de(painel)
    dados, avisos = escrever_com_avisos(sem_fim)
    partes = fx.partes_de(dados)
    xml = partes["word/document.xml"].decode("utf-8")
    checa(ordem.validar(partes) == [] and "TOC" not in xml and xml.count("PAGEREF") == 2
          and codigos(avisos).get("CAMPO_INCOMPLETO") == 2,
          "apagar o fim do TOC (outro paragrafo): o TOC sai, os PAGEREF ficam, XML valido")
    painel.undo()
    painel.undo()
    checa_igual(len(_marcas_de_campo(doc)), total_de_marcas, "Ctrl+Z traz as marcas de volta")
    # Contraprova: sem o equilibrio, o XML seria invalido.
    cru = mod_marcas.equilibrar
    try:
        mod_marcas.equilibrar = lambda d: (d, {"campos": 0, "marcadores": 0})
        import editdoc.formato_docx.escritor as esc
        esc.marcas.equilibrar = mod_marcas.equilibrar
        try:
            escrever(Documento(paragrafos=[Paragrafo(runs=[
                Run(marca=MarcaCampo("inicio", Campo(codigo=(" REF x ",)))), Run("sem fim")])]))
            checa(False, "contraprova: sem o equilibrio o escritor gravaria campo aberto")
        except Exception as erro:  # noqa: BLE001
            checa("fldChar" in str(erro) or "ESCRITA_INVALIDA" in repr(erro),
                  "contraprova: sem o equilibrio o validador recusa a gravacao (nunca um .docx corrompido)")
    finally:
        mod_marcas.equilibrar = cru
        esc.marcas.equilibrar = cru
    painel.document().setModified(False)
    painel.close()


def _marcas_de_campo(doc) -> list[int]:
    from editdoc.ponte_qt import links, marcas
    saida = []
    for k in range(doc.characterCount() - 1):
        cf = links.formato_em(doc, k)
        if cf is not None and cf.objectType() == marcas.TIPO_MARCA_CAMPO:
            saida.append(k)
    return saida


def _codigo(doc, k: int) -> str:
    from editdoc.ponte_qt import links, marcas
    m = marcas.marca_de(links.formato_em(doc, k))
    return m.campo.tipo() if m.tipo == "inicio" else "/"


def testar_pagina_editada() -> None:
    secao("PAGE e NUMPAGES continuam campo de pagina; o PAGE dentro de outro campo tambem volta")
    corpo = ('<w:p>' + fx.campo_complexo("PAGE", "3") + '</w:p>'
             '<w:p><w:hyperlink w:anchor="x">' + fx.campo_complexo("PAGE", "4") + '</w:hyperlink></w:p>')
    modelo, avisos = ler(fx.docx_com_links(corpo, relacoes=[]))
    checa(modelo.paragrafos[0].runs[0].campo == "PAGE" and modelo.paragrafos[1].runs[0].campo == "PAGE"
          and modelo.paragrafos[1].runs[0].link is not None,
          "PAGE simples e PAGE dentro de link: campo de pagina (o do link guarda o link)")
    # Campo PAGE em marcas (atravessa paragrafos) que fica simples depois da edicao: a regra do
    # leitor vale no escritor, e a conferencia passa.
    doc = Documento(paragrafos=[Paragrafo(runs=[Run(marca=MarcaCampo("inicio", Campo(codigo=(" PAGE ",)))),
                                                Run("7"), Run(marca=MarcaCampo("fim"))])])
    dados = escrever(doc)
    conferencia.conferir(dados, doc)
    relido, _ = ler(dados)
    checa_igual([(r.texto, r.campo) for r in relido.paragrafos[0].runs], [("7", "PAGE")],
                "PAGE em marcas no mesmo paragrafo grava e volta como campo de pagina (conferencia ok)")


def testar_tela() -> None:
    secao("tela: os colchetes do campo aparecem na tela e nao no PDF")
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter

    from editdoc.ponte_qt import marcas

    modelo, _ = ler(fx.docx_com_campos())
    painel = _painel_com(modelo)
    doc = painel.documento_corpo()
    k = _marcas_de_campo(doc)[0]
    from editdoc.ponte_qt import links
    fmt = links.formato_em(doc, k)
    manipulador = marcas.ManipuladorDeMarca()

    def pintar() -> int:
        img = QImage(200, 200, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 255, 255))
        p = QPainter(img)
        manipulador.drawObject(p, QRectF(50, 20, 40, 150), doc, k, fmt)
        p.end()
        return sum(1 for x in range(0, 200, 2) for y in range(0, 200, 2)
                   if img.pixelColor(x, y) != QColor(255, 255, 255))
    checa(pintar() > 0, "na tela, a marca do campo pinta um colchete")
    with marcas.sem_pintar_marcas():
        checa_igual(pintar(), 0, "na impressao e no PDF, nada")
    tamanho = manipulador.intrinsicSize(doc, k, fmt)
    checa(tamanho.width() > 0, "a marca do campo tem largura (o caret passa por ela)")
    painel.document().setModified(False)
    painel.close()


def testar_limites() -> None:
    secao("limites: campos demais, instrucao enorme e aninhamento fundo, sem travar")
    corpo = "".join("<w:p>" + fx.campo_complexo(f"REF r{i}", "x") + "</w:p>" for i in range(80))
    inicio = time.perf_counter()
    modelo, avisos = ler(fx.docx_com_links(corpo, relacoes=[]), limites={"campos": 50})
    gasto = time.perf_counter() - inicio
    checa(codigos(avisos).get("CAMPO") == 30 and gasto < 2,
          f"80 campos com limite 50: 30 viram texto com aviso ({gasto:.2f} s)")
    dados = escrever(modelo)
    checa(ordem.validar(fx.partes_de(dados)) == [], "e o arquivo gravado e' valido")
    enorme = "<w:p>" + fx.campo_complexo("REF " + "a" * 5000, "x") + "</w:p>"
    modelo, avisos = ler(fx.docx_com_links(enorme, relacoes=[]))
    checa(codigos(avisos).get("CAMPO") == 1 and "".join(r.texto for r in modelo.paragrafos[0].runs) == "x",
          "instrucao de 5000 caracteres (limite 4096): o resultado fica como texto, com aviso")
    fundo = ("<w:p>" + ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                        '<w:r><w:instrText> REF a </w:instrText></w:r>'
                        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>') * 12
             + "<w:r><w:t>fundo</w:t></w:r>" + '<w:r><w:fldChar w:fldCharType="end"/></w:r>' * 12 + "</w:p>")
    modelo, avisos = ler(fx.docx_com_links(fundo, relacoes=[]))
    dados = escrever(modelo)
    checa(codigos(avisos).get("CAMPO") == 4 and "fundo" in "".join(r.texto for r in modelo.paragrafos[0].runs)
          and ordem.validar(fx.partes_de(dados)) == [],
          "12 campos aninhados no resultado (limite 8): 4 avisam, o texto fica e o arquivo e' valido")


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
    secao("janela: abrir e salvar o sumario sem aviso de perda")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from editdoc import configuracao
    from editdoc.interface.gerente import GerenteDeJanelas

    with pasta_temporaria() as tmp:
        arquivo = tmp / "campos.docx"
        arquivo.write_bytes(fx.docx_com_campos())
        gerente = GerenteDeJanelas(configuracao.padrao())
        janela = gerente.abrir(str(arquivo))
        texto = janela.barra_aviso.texto_completo()
        checa("campo" not in texto.lower(), "a barra de aviso nao fala de campo")
        painel = janela.painel
        painel.setFocus()
        cursor = painel.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        painel.setTextCursor(cursor)
        QTest.keyClick(painel, Qt.Key.Key_Exclam)
        perdas = []
        with dialogos(pedir_perda=lambda _p, _n, linhas: perdas.append(linhas) or "salvar"):
            checa(janela.salvar() is True, "salvar grava")
        checa(all("campo" not in t for t in (perdas[0] if perdas else [])),
              "a confirmacao de perda (se houver) nao lista campo nenhum")
        salvo = fx.partes_de(arquivo.read_bytes())
        a = contagem(fx.partes_de(fx.docx_com_campos())["word/document.xml"].decode("utf-8"))
        b = contagem(salvo["word/document.xml"].decode("utf-8"))
        checa(b["instr"] == {**a["instr"], "AUTHOR": 1} and ordem.validar(salvo) == [],
              "o arquivo salvo pela janela tem os mesmos campos e passa no validador")
        with dialogos(pedir_descartar=lambda *_a: "descartar"):
            for j in gerente.janelas():
                j.close()
        drenar_eventos()


def main() -> int:
    testar_leitura()
    testar_gravacao()
    testar_validador()
    testar_pagina_editada()
    testar_limites()
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    testar_edicao()
    testar_tela()
    testar_janela()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
