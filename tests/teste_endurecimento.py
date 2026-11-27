"""Endurecimento contra .docx hostil ou corrompido e contra destino hostil (0.1.39).

Cada defeito achado pelo fuzz (docs/SPIKES.md, "0.1.39") tem aqui um teste de regressao com a
fixture gerada por codigo e a contraprova (o arquivo legitimo parecido continua abrindo).
Nenhum documento real: tudo e' montado em memoria.

- leitor: parte do zip corrompida, atributos em quantidade absurda (tempo quadratico do libxml2),
  elementos demais, arquivo grande demais, dispositivo no lugar do arquivo, sectPr fora de ordem,
  nota que cita nota;
- gravacao: destino que e' dispositivo, fluxo alternativo, pasta; temporario plantado (link fisico);
- recuperacao: metadados forjados; pedido da instancia unica e caminho de abrir;
- campos: uma marca so' para muitos campos;
- mini-fuzz: cortes do zip e bytes trocados nas partes XML, com semente fixa.
"""

from __future__ import annotations

import io
import os
import random
import struct
import time
import zipfile

from ajudantes import checa, checa_igual, pasta_temporaria, preparar_qt, resumir, secao
import fixtures_docx as fx

preparar_qt()

from editdoc import recuperacao  # noqa: E402
from editdoc.armazenamento import gravacao  # noqa: E402
from editdoc.formato_docx import leitor  # noqa: E402
from editdoc.formato_docx.erros import ErroDocx  # noqa: E402
from editdoc.formato_docx.escritor import escrever_com_avisos  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402

P = "<w:p><w:r><w:t>x</w:t></w:r></w:p>"
BASE = fx.docx_com_xml(P)


def codigo(dados, **kw) -> tuple[str | None, float]:
    inicio = time.perf_counter()
    try:
        ler(dados, **kw)
        cod = None
    except ErroDocx as erro:
        cod = erro.codigo
    except BaseException as erro:  # noqa: BLE001 - um traceback vazado e' o defeito
        cod = "EXCECAO:" + type(erro).__name__
    return cod, time.perf_counter() - inicio


def mexer_no_zip(docx: bytes, nome: bytes, deslocamento: int, formato: str, valor) -> bytes:
    """Troca um campo do cabecalho central da entrada `nome` (zip corrompido de proposito)."""
    z = bytearray(docx)
    pos = 0
    while True:
        i = bytes(z).find(b"PK\x01\x02", pos)
        if i < 0:
            break
        tam = struct.unpack_from("<H", z, i + 28)[0]
        if bytes(z[i + 46:i + 46 + tam]) == nome:
            struct.pack_into(formato, z, i + deslocamento, valor)
        pos = i + 4
    return bytes(z)


def testar_zip_corrompido() -> None:
    secao("parte do zip corrompida: ZIP_CORROMPIDO, nunca ERRO_INTERNO")
    nome = b"word/document.xml"
    casos = {
        "CRC que nao bate": mexer_no_zip(BASE, nome, 16, "<I", 0xDEADBEEF),
        "deslocamento fora do arquivo": mexer_no_zip(BASE, nome, 42, "<I", 0x7FFFFFF0),
        "tamanho comprimido zero": mexer_no_zip(BASE, nome, 20, "<I", 0),
    }
    z = bytearray(BASE)
    i = bytes(z).find(nome) + len(nome)
    for k in range(i + 6, i + 30):
        z[k] ^= 0xA5
    casos["fluxo deflate quebrado"] = bytes(z)
    for rotulo, dados in casos.items():
        cod, _ = codigo(dados)
        checa_igual(cod, "ZIP_CORROMPIDO", f"{rotulo}")
    checa_igual(codigo(BASE)[0], None, "contraprova: o mesmo arquivo sem o defeito abre")
    checa(len(ErroDocx("ZIP_CORROMPIDO").mensagem) > 30, "ZIP_CORROMPIDO tem mensagem em portugues")


def testar_atributos() -> None:
    secao("20 mil atributos numa tag: recusado na hora (era tempo quadratico no libxml2)")
    muitos = "<w:p><w:r><w:t " + " ".join(f'a{i}="1"' for i in range(20000)) + ">x</w:t></w:r></w:p>"
    cod, t = codigo(fx.docx_com_xml(muitos))
    checa(cod == "XML_ATRIBUTOS_EXCEDIDOS" and t < 1.5, f"20 mil atributos: {cod} em {t:.2f} s")
    # Contraprova: uma tag com 120 atributos (mais que qualquer tag do Word) abre.
    legit = "<w:p><w:r><w:t " + " ".join(f'a{i}="1"' for i in range(120)) + ">x</w:t></w:r></w:p>"
    cod, _ = codigo(fx.docx_com_xml(legit))
    checa_igual(cod, None, "contraprova: 120 atributos numa tag abre")
    checa(len(ErroDocx("XML_ATRIBUTOS_EXCEDIDOS").mensagem) > 30, "mensagem em portugues")
    # Aspas simples e espacos soltos nao escapam da contagem.
    simples = "<w:p><w:r><w:t " + "\n".join(f"b{i} = 'v'" for i in range(1500)) + ">x</w:t></w:r></w:p>"
    cod, t = codigo(fx.docx_com_xml(simples))
    checa(cod == "XML_ATRIBUTOS_EXCEDIDOS" and t < 1.5, f"aspas simples e quebras de linha: {cod}")


def testar_elementos() -> None:
    secao("elementos demais: recusado antes do parse (memoria do lxml)")
    original = leitor.ELEMENTOS_MAXIMOS
    try:
        leitor.ELEMENTOS_MAXIMOS = 300
        cod, _ = codigo(fx.docx_com_xml(P * 400))
        checa_igual(cod, "XML_ELEMENTOS_EXCEDIDOS", "400 paragrafos com o limite em 300 elementos")
        cod, _ = codigo(fx.docx_com_xml(P * 20))
        checa_igual(cod, None, "contraprova: 20 paragrafos cabem")
    finally:
        leitor.ELEMENTOS_MAXIMOS = original
    checa_igual(codigo(fx.docx_com_xml(P * 400))[0], None, "com o limite de verdade, 400 paragrafos abrem")
    checa(leitor.ELEMENTOS_MAXIMOS >= 1_000_000, "o limite padrao e' folgado para documento de verdade")
    # Paragrafos: qualquer prefixo de namespace conta, e o limite vale para a parte, nao para o arquivo.
    original = leitor.PARAGRAFOS_MAXIMOS
    try:
        leitor.PARAGRAFOS_MAXIMOS = 1000
        grande = fx.docx_com_xml("<w:p><w:r><w:t>linha de texto</w:t></w:r></w:p>" * 5000)
        checa_igual(codigo(grande)[0], "XML_PARAGRAFOS_EXCEDIDOS", "5000 paragrafos com o limite em 1000")
        outro = fx.docx_com_xml("<w:p/>" * 40000)
        checa_igual(codigo(outro)[0], "XML_PARAGRAFOS_EXCEDIDOS", "40 mil paragrafos vazios (parte pequena) tambem")
        checa_igual(codigo(fx.docx_com_xml("<w:p><w:r><w:t>x</w:t></w:r></w:p>" * 900))[0], None,
                    "contraprova: 900 paragrafos cabem")
    finally:
        leitor.PARAGRAFOS_MAXIMOS = original
    checa(original >= 50_000, "o limite padrao de paragrafos deixa passar o documento de 50 mil (1000 paginas)")
    checa(len(ErroDocx("XML_PARAGRAFOS_EXCEDIDOS").mensagem) > 30, "XML_PARAGRAFOS_EXCEDIDOS tem mensagem")


def testar_arquivo_e_dispositivo() -> None:
    secao("arquivo grande demais e dispositivo no lugar do arquivo")
    cod, _ = codigo(BASE, limites={"arquivo_bytes": 100})
    checa_igual(cod, "ARQUIVO_GRANDE", "bytes acima do limite do arquivo")
    with pasta_temporaria() as pasta:
        arq = pasta / "a.docx"
        arq.write_bytes(BASE)
        checa_igual(codigo(str(arq))[0], None, "contraprova: arquivo comum abre")
        checa_igual(codigo(str(arq), limites={"arquivo_bytes": 100})[0], "ARQUIVO_GRANDE",
                    "arquivo em disco acima do limite e' recusado sem ler")
        checa_igual(codigo(str(pasta))[0], "ARQUIVO_ILEGIVEL", "uma pasta no lugar do arquivo")
    if os.name == "nt":
        for dispositivo in ("CON", "NUL", "COM1", "nul."):
            cod, t = codigo(dispositivo)
            checa(cod == "ARQUIVO_ILEGIVEL" and t < 2, f"dispositivo {dispositivo}: {cod} em {t:.2f} s")
    checa(leitor.LIMITES_PADRAO["arquivo_bytes"] >= leitor.LIMITES_PADRAO["total_bytes"],
          "o limite do arquivo cobre o do conteudo descompactado")


def testar_secao_fora_de_ordem() -> None:
    secao("w:sectPr fora de ordem ou repetido: abre E salva (antes abria e nunca mais gravava)")
    fora = ('<w:cols w:num="2" w:space="708"/><w:pgNumType w:fmt="decimal"/>'
            '<w:pgSz w:w="12000" w:h="16000"/><w:pgSz w:w="1" w:h="1"/>')
    docx = fx.docx_com_xml(P, sect_xml=fora)
    doc, avisos = ler(docx)
    try:
        dados, _ = escrever_com_avisos(doc)
        gravou = True
    except ErroDocx as erro:
        gravou, dados = False, b""
        print("         ", erro.mensagem[:120])
    checa(gravou, "o documento com sectPr fora de ordem e' gravado")
    if gravou:
        doc2, _ = ler(dados)
        checa_igual(doc2.pagina.largura_tw, doc.pagina.largura_tw, "a pagina lida volta igual")
    checa_igual(doc.pagina.largura_tw, 12000, "vale o primeiro pgSz")
    # Contraprova: o sectPr correto continua gravando sem aviso de formatacao.
    doc_ok, avisos_ok = ler(fx.docx_com_xml(P))
    checa("FORMATACAO" not in {a.codigo for a in avisos_ok}, "contraprova: sectPr correto sem aviso")


def testar_nota_que_cita_nota() -> None:
    secao("nota de rodape que cita outra nota: abre E salva")
    docx = fx.docx_com_notas(
        '<w:p><w:r><w:t>t</w:t></w:r>' + fx.ref_nota(1) + '</w:p>',
        fx.nota_xml(1, "n") .replace("</w:p>", '<w:r><w:footnoteReference w:id="1"/></w:r></w:p>', 1),
        notas_fim_xml=None)
    doc, avisos = ler(docx)
    try:
        escrever_com_avisos(doc)
        gravou = True
    except ErroDocx as erro:
        gravou = False
        print("         ", erro.mensagem[:120])
    checa(gravou, "documento com nota que cita nota e' gravado")
    checa("NOTA" in {a.codigo for a in avisos}, "o que saiu (a referencia dentro da nota) tem aviso NOTA")
    doc_ok, av_ok = ler(fx.docx_com_notas())
    checa("NOTA" not in {a.codigo for a in av_ok}, "contraprova: notas normais sem aviso")


def testar_campos_uma_marca() -> None:
    secao("campos: uma marca so' para muitos campos (era uma por campo, quadratico)")
    from editdoc.ponte_qt import campos

    class Falso:
        def __init__(self):
            self.chamadas = []

        def markContentsDirty(self, pos, tam):  # noqa: N802 - nome do Qt
            self.chamadas.append((pos, tam))

    doc = Falso()
    campos.refazer_campos(doc, list(range(10, 600, 3)))
    checa_igual(len(doc.chamadas), 1, "197 campos: uma marca")
    checa_igual(doc.chamadas[0], (10, 589),
                "a marca cobre do primeiro ao ultimo campo")
    doc = Falso()
    campos.refazer_campos(doc, [5, 50, 500])
    checa_igual(len(doc.chamadas), 3, "contraprova: poucos campos: uma marca cada (como antes)")


def testar_destino() -> None:
    secao("gravar: destino que nao e' arquivo comum e' recusado antes de escrever")
    with pasta_temporaria() as pasta:
        recusados = {
            "dispositivo CON": "CON",
            "dispositivo com extensao": str(pasta / "nul.docx"),
            "dispositivo com ponto no fim": str(pasta / "aux."),
            "COM1 em caixa mista": str(pasta / "Com1.DOCX"),
            "LPT9": str(pasta / "lpt9"),
            "prefixo de dispositivo": "\\\\.\\NUL",
            "fluxo alternativo": str(pasta / "a.docx:oculto"),
            "caractere de controle": str(pasta / "a\x01b.docx"),
            "nome vazio": "   ",
            "pasta existente": str(pasta),
        }
        for rotulo, alvo in recusados.items():
            inicio = time.perf_counter()
            try:
                gravacao.gravar_bytes(alvo, b"dados")
                resultado = "gravou"
            except gravacao.DestinoInvalido as erro:
                resultado = "recusou" if len(str(erro)) > 15 else "mensagem curta"
            except BaseException as erro:  # noqa: BLE001
                resultado = type(erro).__name__
            checa(resultado == "recusou" and time.perf_counter() - inicio < 2,
                  f"{rotulo}: {resultado}")
        checa(not list(pasta.iterdir()), "nada foi criado na pasta")
        # Contraprova: nome comum e nome com 'con' no meio gravam.
        for nome in ("contrato.docx", "icon.docx", "a b.docx", "aux1.docx", "console.txt"):
            gravacao.gravar_bytes(str(pasta / nome), b"ok")
            checa_igual((pasta / nome).read_bytes(), b"ok", f"contraprova: {nome} grava")


def testar_temporario_plantado() -> None:
    secao("gravar: temporario plantado (link fisico, pasta, sobra) nao leva o conteudo para outro arquivo")
    with pasta_temporaria() as pasta:
        destino = pasta / "doc.docx"
        destino.write_bytes(b"ORIGINAL")
        vitima = pasta / "vitima.txt"
        vitima.write_bytes(b"NAO PODE MUDAR")
        plantado = pasta / ("doc.docx" + gravacao.SUFIXO)
        try:
            os.link(vitima, plantado)
            plantou = True
        except OSError:
            plantou = False
        checa(plantou, "o link fisico foi plantado (o teste valeria sem isto)")
        if plantou:
            gravacao.gravar_bytes(destino, b"NOVO")
            checa_igual(vitima.read_bytes(), b"NAO PODE MUDAR", "o arquivo do outro nome NAO foi truncado")
            checa_igual(destino.read_bytes(), b"NOVO", "o destino recebeu o conteudo")
            checa_igual(plantado.read_bytes(), b"NAO PODE MUDAR", "o link plantado continua como estava")
            plantado.unlink()
        # Pasta com o nome do temporario.
        (pasta / ("doc.docx" + gravacao.SUFIXO)).mkdir()
        gravacao.gravar_bytes(destino, b"OUTRO")
        checa_igual(destino.read_bytes(), b"OUTRO", "temporario com nome de pasta: grava com nome unico")
        (pasta / ("doc.docx" + gravacao.SUFIXO)).rmdir()
        # Sobra comum de uma queda anterior: apagada, e o nome comum e' reusado.
        sobra = pasta / ("doc.docx" + gravacao.SUFIXO)
        sobra.write_bytes(b"sobra de uma queda")
        gravacao.gravar_bytes(destino, b"TERCEIRO")
        checa_igual(destino.read_bytes(), b"TERCEIRO", "sobra comum: grava")
        checa(not sobra.exists(), "e a sobra nao fica na pasta")
        checa(sorted(p.name for p in pasta.iterdir()) == ["doc.docx", "vitima.txt"],
              "nenhum temporario sobrou")


ANCORA = ('<w:p><w:r><w:drawing><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" '
          'relativeHeight="1" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">'
          '<wp:simplePos x="0" y="0"/><wp:positionH relativeFrom="page"><wp:posOffset>100</wp:posOffset>'
          '</wp:positionH><wp:positionV relativeFrom="page"><wp:posOffset>100</wp:posOffset></wp:positionV>'
          '<wp:extent cx="91440" cy="91440"/><wp:wrapSquare wrapText="bothSides"/>'
          '<wp:docPr id="1" name="c"/><a:graphic><a:graphicData uri="u"/></a:graphic></wp:anchor>'
          '</w:drawing></w:r></w:p>')


def testar_flutuantes_limite() -> None:
    secao("objetos flutuantes: limite por documento (o plano deles e' quadratico: 2 000 = 105 s)")
    docx = fx.docx_com_xml(ANCORA * 12)
    _doc, avisos = ler(docx, limites={"flutuantes": 5})
    perdidos = sum(a.contagem for a in avisos if a.codigo == "OBJETO_PERDIDO")
    checa_igual(perdidos, 7, "12 ancoras com o limite em 5: 7 ficam fora, com aviso OBJETO_PERDIDO")
    _doc, avisos = ler(docx)
    checa(not any(a.codigo == "OBJETO_PERDIDO" for a in avisos), "contraprova: com o limite padrao as 12 ficam")
    checa(leitor.LIMITES_PADRAO["flutuantes"] >= 300, "o limite padrao e' folgado para documento de verdade")


def testar_somente_leitura() -> None:
    secao("gravar: destino somente leitura: mensagem certa, original e pasta intactos")
    import stat as modo
    with pasta_temporaria() as pasta:
        destino = pasta / "doc.docx"
        destino.write_bytes(b"ORIGINAL")
        os.chmod(destino, modo.S_IREAD)
        try:
            try:
                gravacao.gravar_bytes(destino, b"NOVO")
                resultado = "gravou"
            except gravacao.FalhaNaTroca as erro:
                resultado = "somente leitura" if "somente leitura" in str(erro) else str(erro)[:80]
            except OSError as erro:
                resultado = type(erro).__name__
            checa_igual(resultado, "somente leitura", "a mensagem diz que o arquivo e' somente leitura")
            checa_igual(destino.read_bytes(), b"ORIGINAL", "o original continua intacto")
            checa_igual(sorted(p.name for p in pasta.iterdir()), ["doc.docx"], "nenhum temporario sobrou")
        finally:
            os.chmod(destino, modo.S_IWRITE | modo.S_IREAD)


def testar_recuperacao_forjada() -> None:
    secao("recuperacao: metadados forjados nao quebram o dialogo")
    limpo = recuperacao.texto_limpo("a\u202eb\x00c\x07d\n" + "z" * 900)
    checa("\u202e" not in limpo and "\x00" not in limpo and "\x07" not in limpo and "\n" not in limpo,
          "sem bidi nem controle")
    checa(len(limpo) <= recuperacao.TEXTO_MAXIMO + 3, "tamanho limitado")
    checa_igual(recuperacao.texto_limpo(12345), "", "o que nao e' texto vira vazio")
    checa_igual(recuperacao.texto_limpo("Contrato (rascunho).docx"), "Contrato (rascunho).docx",
                "contraprova: nome normal passa")
    with pasta_temporaria() as base:
        copia = recuperacao.Copia(id="a" * 32, docx=base / "x.docx", meta={
            "nome": "\u202etxt.docx\u202d" + "N" * 5000,
            "caminho_original": "C:\\p\\\u202e\x01" + "X" * 5000,
            "avisos": [{"codigo": "OBJETO", "texto": "t\u202e" + "T" * 9000, "contagem": 10 ** 12}] * 300
            + [{"codigo": "X", "texto": "x", "contagem": True}]})
        checa(len(copia.nome) <= 210 and "\u202e" not in copia.nome, "nome da copia limpo e curto")
        checa(len(copia.caminho_original) <= 1010 and "\x01" not in copia.caminho_original,
              "caminho original limpo e curto")
        avisos = copia.avisos_com_perda()
        checa(len(avisos) <= 50, f"no maximo 50 avisos ({len(avisos)})")
        checa(all(len(a["texto"]) <= 510 and a["contagem"] <= 10 ** 9 for a in avisos),
              "texto e contagem dos avisos limitados")
        checa(all(not isinstance(a["contagem"], bool) for a in avisos), "contagem booleana descartada")


def testar_pedido_e_caminho() -> None:
    secao("abrir: caminho estranho e pedido forjado da instancia unica")
    from editdoc import configuracao
    from editdoc.interface import gerente as ger

    checa(ger.caminho_aceitavel("C:\\pasta\\a.docx"), "caminho comum e' aceito")
    for ruim in ("", "   ", "a\x00b.docx", "a\nb.docx", "NUL", "c:\\x\\CON", "x" * 40000, 123, None):
        checa(not ger.caminho_aceitavel(ruim), f"recusado: {str(ruim)[:20]!r}")
    g = ger.GerenteDeJanelas(configuracao.padrao())
    abertos: list[str] = []
    g.abrir = lambda caminho: abertos.append(caminho)  # type: ignore[method-assign]
    g.receber_pedido({"arquivos": [f"C:\\p\\{i}.docx" for i in range(500)]})
    checa_igual(len(abertos), ger.PEDIDO_MAXIMO_ARQUIVOS, "500 caminhos no pedido: abre so' o maximo")
    abertos.clear()
    g.receber_pedido({"arquivos": [1, None, "a.docx", {"x": 1}]})
    checa_igual(abertos, ["a.docx"], "contraprova: so' o que e' texto passa")
    abertos.clear()
    g.receber_pedido({"arquivos": "nao e lista"})
    g.receber_pedido({"arquivos": []})
    g.receber_pedido({})
    checa_igual(abertos, [], "pedido malformado nao abre nada")
    # Enxurrada de pedidos "novo": com janelas demais, nenhum abre mais uma.
    novas: list[int] = []
    g.novo = lambda: novas.append(1)  # type: ignore[method-assign]
    g._janelas = [object()] * ger.JANELAS_MAXIMAS_POR_PEDIDO
    g.receber_pedido({"novo": True})
    checa_igual(novas, [], "com 60 janelas abertas, um pedido 'novo' forjado nao abre outra")
    g._janelas = []
    g.receber_pedido({"novo": True})
    checa_igual(novas, [1], "contraprova: com poucas janelas, abre")

    # abrir() com caminho invalido nao levanta: avisa e devolve None.
    mensagens: list[str] = []
    from editdoc.interface import dialogos_modais
    anterior = dialogos_modais.avisar
    dialogos_modais.avisar = lambda pai, titulo, texto: mensagens.append(texto)
    try:
        g2 = ger.GerenteDeJanelas(configuracao.padrao())
        checa(g2.abrir("a\x00b.docx") is None and mensagens, "abrir com NUL: aviso, sem excecao")
    finally:
        dialogos_modais.avisar = anterior


def testar_conexoes_da_instancia_unica() -> None:
    secao("instancia unica: conexoes abertas e caladas tem teto")
    from PySide6.QtNetwork import QLocalSocket
    from PySide6.QtTest import QTest

    from editdoc import instancia_unica

    os.environ[instancia_unica.VARIAVEL_DO_CANAL] = f"EditDoc-teste-endurecimento-{os.getpid()}"
    servidor = instancia_unica.Servidor()
    if not servidor.escutar():
        checa(False, "o servidor de teste escuta")
        return
    soquetes = []
    try:
        for _ in range(instancia_unica.CONEXOES_MAXIMAS + 10):
            s = QLocalSocket()
            s.connectToServer(instancia_unica.nome_do_canal())
            s.waitForConnected(1000)
            soquetes.append(s)
        QTest.qWait(300)
        checa(len(servidor._parciais) <= instancia_unica.CONEXOES_MAXIMAS,
              f"no maximo {instancia_unica.CONEXOES_MAXIMAS} conexoes guardadas ({len(servidor._parciais)})")
    finally:
        servidor.parar()
        for s in soquetes:
            s.abort()
            s.deleteLater()
        QTest.qWait(100)
        os.environ.pop(instancia_unica.VARIAVEL_DO_CANAL, None)


def _variantes_xml(dados: bytes, seed: int) -> bytes:
    rnd = random.Random(seed)
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        partes = {n: z.read(n) for n in z.namelist()}
    nomes = [n for n in partes if n.endswith(".xml") and n.startswith("word/")]
    for _ in range(rnd.randint(1, 4)):
        nome = rnd.choice(nomes)
        b = bytearray(partes[nome])
        for _ in range(rnd.randint(1, 6)):
            i = rnd.randrange(len(b))
            b[i] = rnd.choice(b'<>/="\' &;0123456789-abcxyzw:\x00\xff')
        partes[nome] = bytes(b)
    return fx.montar(partes)


def testar_mini_fuzz() -> None:
    secao("mini-fuzz com semente fixa: cortes do zip e bytes trocados no XML")
    sementes = {"completo": fx.bytes_de(fx.documento_completo()), "notas": fx.docx_com_notas(),
                "secoes": fx.docx_com_secoes(), "campos": fx.docx_com_campos()}
    ruins: list[str] = []
    lentos: list[str] = []
    abertos = recusados = 0
    for nome, dados in sementes.items():
        cortes = [len(dados) * k // 25 for k in range(1, 25)]
        for corte in cortes:
            cod, t = codigo(dados[:corte])
            if cod is None or cod.startswith("EXCECAO") or cod == "ERRO_INTERNO":
                ruins.append(f"{nome} cortado em {corte}: {cod}")
            if t > 3:
                lentos.append(f"{nome}/{corte}")
        for seed in range(60):
            cod, t = codigo(_variantes_xml(dados, seed))
            if cod is None:
                abertos += 1
            else:
                recusados += 1
            if cod is not None and (cod.startswith("EXCECAO") or cod == "ERRO_INTERNO"):
                ruins.append(f"{nome} semente {seed}: {cod}")
            if t > 3:
                lentos.append(f"{nome}/semente {seed}")
    checa(not ruins, f"nenhum traceback nem ERRO_INTERNO: {ruins[:3]}")
    checa(not lentos, f"nenhum caso acima de 3 s: {lentos[:3]}")
    checa(abertos > 20 and recusados > 20, f"o fuzz exercita os dois lados ({abertos} abrem, {recusados} recusados)")


CODIGO_BLOCO_SEM_LINHAS = """
import sys
sys.path.insert(0, sys.argv[1] + "/tests"); sys.path.insert(0, sys.argv[1])
import ajudantes
ajudantes.preparar_qt()
from PySide6.QtGui import QTextDocument
from editdoc.interface.layout_paginado import retangulo_cursor_em
doc = QTextDocument()
doc.setPlainText("abc" + chr(10) + "def")
assert doc.firstBlock().layout().lineCount() == 0
r = retangulo_cursor_em(doc, 1)
print("RESULTADO", r.width() > 0, flush=True)
"""


def testar_bloco_sem_linhas() -> None:
    secao("cursor num bloco sem linhas (alem do QFIXED_MAX, ~500 paginas): nao derruba o processo")
    import subprocess
    import sys
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-c", CODIGO_BLOCO_SEM_LINHAS, raiz], capture_output=True,
                       text=True, timeout=120)
    checa(r.returncode == 0 and "RESULTADO True" in r.stdout,
          f"retangulo_cursor_em num bloco sem linhas (codigo {r.returncode}; antes: acesso invalido)")


def testar_corretor_texto_hostil() -> None:
    secao("corretor: texto com substituto UTF-16 solto, NUL e bidi nao desliga a verificacao")
    from editdoc.ortografia import windows
    solto = "abc " + chr(0xD800) + " def"
    limpo = windows._seguro(solto + "\0x")
    checa(len(limpo) == len(solto) + 2 and chr(0xD800) not in limpo and "\0" not in limpo,
          "o substituto solto e o NUL viram espaco, sem mudar as posicoes")
    checa_igual(windows._seguro("normal \U0001F600 ok"), "normal \U0001F600 ok",
                "contraprova: emoji (par valido) passa como esta")
    import subprocess
    import sys
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # A API real do Windows roda num processo a parte: o COM dela nao pode misturar com o do Qt
    # desta suite.
    r = subprocess.run([sys.executable, "-c", CODIGO_CORRETOR_REAL, raiz], capture_output=True, text=True,
                       timeout=120)
    saida = [l for l in r.stdout.splitlines() if l.startswith("CASO ") or l.startswith("PULADO")]
    if any(l.startswith("PULADO") for l in saida):
        print("         (sem corretor do Windows com pt-BR: o teste da API real foi pulado)")
        return
    checa(r.returncode == 0 and len(saida) == 5, f"a API real respondeu aos 5 textos (codigo {r.returncode})")
    for linha in saida:
        _, rotulo, resultado = linha.split("|")
        checa(resultado == "ok", f"{rotulo}: {resultado}")


CODIGO_CORRETOR_REAL = """
import sys, time
sys.path.insert(0, sys.argv[1])
from editdoc.ortografia import windows
try:
    c = windows.CorretorWindows()
    if not c.suporta("pt-BR"):
        raise RuntimeError
except Exception:
    print("PULADO"); raise SystemExit
solto = "abc " + chr(0xD800) + " def"
for rotulo, texto in (("substituto solto", solto), ("NUL", "abc" + chr(0) + "def"),
                      ("bidi", "abc " + chr(0x202e) + " errado " + chr(0x202c)),
                      ("emoji", chr(0x1F600) + " errrado"), ("30 mil caracteres", "palavra " * 3700)):
    t0 = time.perf_counter()
    try:
        c.verificar(texto, "pt-BR")
        r = "ok" if time.perf_counter() - t0 < 5 else "lento"
    except BaseException as e:
        r = type(e).__name__
    print("CASO |" + rotulo + "|" + r, flush=True)
c.fechar()
"""


def _docx_runs(n: int) -> bytes:
    return fx.docx_com_xml("<w:p>" + "<w:r><w:rPr><w:b/></w:rPr><w:t>x</w:t></w:r><w:r><w:t>y</w:t></w:r>" * (n // 2)
                           + "</w:p>")


def _docx_tabela(linhas: int) -> bytes:
    return fx.docx_com_xml('<w:tbl><w:tblGrid><w:gridCol w:w="1000"/></w:tblGrid>'
                           + ('<w:tr><w:tc>' + P + '</w:tc></w:tr>') * linhas + '</w:tbl>')


def testar_abrir_sem_custo_quadratico() -> None:
    secao("abrir: paragrafo com muitos runs, tabela grande e muitos campos nao custam N ao quadrado")
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    from ajudantes import drenar_eventos

    casos = {
        "3000 runs num paragrafo (antes: ~80 s)": (_docx_runs(3000), 12),
        "tabela de 400 linhas (antes: ~25 s)": (_docx_tabela(400), 6),
        "800 campos num paragrafo (antes: ~12 s)": (fx.docx_com_xml("<w:p>" + fx.campo_complexo(" PAGE ", "1") * 800 + "</w:p>"), 8),
    }
    for rotulo, (docx, teto) in casos.items():
        modelo, avisos = ler(docx)
        janela = JanelaPrincipal(configuracao.padrao())
        janela.resize(1000, 800)
        janela.show()
        drenar_eventos(2)
        inicio = time.perf_counter()
        janela.carregar(modelo, avisos, None)
        drenar_eventos(2)
        t = time.perf_counter() - inicio
        checa(t < teto, f"{rotulo}: {t:.1f} s (teto {teto} s)")
        janela.painel.documento_corpo().setModified(False)
        janela.close()
        drenar_eventos()


TEXTO_HOSTIL = ("‮⁦⁩‏\u0001\u0007‭" + "palavra" * 3 + " \u0085" + "Ab" * 20)


def _docx_paineis_hostis() -> bytes:
    """Comentario e revisao com texto gigante, controle e bidi no autor, nas iniciais e no corpo."""
    W = fx._NS_W
    ruim = TEXTO_HOSTIL.replace("\u0001", "").replace("\u0007", "")  # controle bruto nao e' XML valido
    gigante = ("palavra " * 40000).strip()
    comentario = (f'<w:comment w:id="0" w:author="{ruim * 200}" w:date="x" w:initials="{ruim}">'
                  f'<w:p><w:r><w:t>{gigante}</w:t></w:r></w:p></w:comment>')
    cx = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:comments xmlns:w="{W}">'
          f'{comentario}</w:comments>').encode("utf-8")
    corpo = ('<w:p><w:commentRangeStart w:id="0"/><w:r><w:t>texto comentado</w:t></w:r>'
             '<w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r></w:p>'
             f'<w:p><w:ins w:id="5" w:author="{ruim * 500}" w:date="2020-01-01T00:00:00Z"><w:r><w:t>{gigante}</w:t></w:r></w:ins>'
             f'<w:del w:id="6" w:author="{ruim}" w:date="invalida"><w:r><w:delText>{gigante[:60000]}</w:delText></w:r></w:del></w:p>')
    return fx.docx_com_xml(
        corpo, partes_extra={"word/comments.xml": cx},
        relacoes_extra=[("rIdC1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
                         "comments.xml")],
        tipos_extra=[("/word/comments.xml",
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml")])


def testar_paineis_com_texto_hostil() -> None:
    secao("paineis de comentarios e revisoes: texto gigante, bidi e controle no autor e no corpo")
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    from ajudantes import drenar_eventos

    modelo, avisos = ler(_docx_paineis_hostis())
    janela = JanelaPrincipal(configuracao.padrao())
    janela.resize(1300, 800)
    janela.show()
    drenar_eventos(2)
    inicio = time.perf_counter()
    janela.carregar(modelo, avisos, None)
    janela.dock_comentarios.show()
    janela.revisoes.abas.setCurrentWidget(janela.revisoes.lista)
    janela.revisoes.atualizar_lista()
    drenar_eventos(3)
    imagem = janela.grab()
    janela.revisoes.abas.setCurrentWidget(janela.painel_comentarios)
    drenar_eventos(3)
    imagem2 = janela.grab()
    t = time.perf_counter() - inicio
    checa(not imagem.isNull() and not imagem2.isNull(), "a janela pinta com os dois paineis")
    checa(t < 20, f"abrir e pintar os paineis em {t:.1f} s (teto 20 s)")
    checa(janela.painel_comentarios.findChildren(object) is not None, "o painel de comentarios existe")
    janela.painel.documento_corpo().setModified(False)
    janela.close()
    drenar_eventos()


def main() -> int:
    for teste in (testar_paineis_com_texto_hostil, testar_zip_corrompido, testar_atributos, testar_elementos, testar_arquivo_e_dispositivo,
                  testar_secao_fora_de_ordem, testar_nota_que_cita_nota, testar_campos_uma_marca, testar_bloco_sem_linhas,
                  testar_destino, testar_temporario_plantado, testar_somente_leitura, testar_flutuantes_limite, testar_recuperacao_forjada,
                  testar_pedido_e_caminho, testar_conexoes_da_instancia_unica, testar_corretor_texto_hostil,
                  testar_abrir_sem_custo_quadratico, testar_mini_fuzz):
        try:
            teste()
        except BaseException as erro:  # noqa: BLE001 - sem a correcao o teste estoura: isto e' FALHA, nao queda
            checa(False, f"{teste.__name__} levantou {type(erro).__name__}: {str(erro)[:100]}")
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
