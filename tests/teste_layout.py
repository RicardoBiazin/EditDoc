"""Layout de pagina: papel, orientacao e margens vao e voltam pelo .docx (sectPr) e pela janela.

Regra de avisos (M3): PAGINA so' aparece com mais de uma secao; papel ou margem que nao cabe numa
pagina util vira PAPEL_INVALIDO e o arquivo sai com A4 e margens padrao (com aviso).
"""

from __future__ import annotations

import re

import fixtures_docx as fx
from ajudantes import checa, checa_igual, drenar_eventos, pasta_temporaria, pular, preparar_qt, resumir, secao, usar_fonte_windows

QT = preparar_qt()

from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.modelo.documento import Documento, Paragrafo, Run  # noqa: E402
from editdoc.modelo.pagina import Pagina  # noqa: E402


def _xml_com_corpo(corpo_xml: str) -> bytes:
    """Um .docx cujo corpo e' `corpo_xml`, seguido do sectPr final padrao do escritor."""
    base = fx.bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("x")])]))
    xml = fx.partes_de(base)["word/document.xml"].decode("utf-8")
    inicio = xml.index("<w:body>") + len("<w:body>")
    fim = xml.index("<w:sectPr")
    return fx.com_parte(base, "word/document.xml", (xml[:inicio] + corpo_xml + xml[fim:]).encode("utf-8"))


def _codigos(avisos) -> list[str]:
    return [a.codigo for a in avisos]


def testar_sectpr() -> None:
    secao("sectPr: papel, orientacao e margens vao e voltam pelo .docx")
    carta_paisagem = Pagina().com_papel("Carta").com_orientacao(True).com_margens(1134, 1000, 1417, 1701)
    doc = Documento(paragrafos=[Paragrafo(runs=[Run("texto")])], pagina=carta_paisagem)
    dados = escrever(doc)
    xml = fx.partes_de(dados)["word/document.xml"].decode("utf-8")
    checa(re.search(r'<w:pgSz w:w="15840" w:h="12240" w:orient="landscape"', xml) is not None,
          "o sectPr grava Carta em paisagem: largura e altura trocadas e orient=landscape")
    checa(re.search(r'<w:pgMar w:top="1134" w:right="1701" w:bottom="1000" w:left="1417"', xml) is not None,
          "o sectPr grava as quatro margens")
    lido, avisos = ler(dados)
    checa_igual(lido.pagina, carta_paisagem, "ao abrir, papel, orientacao e margens sao os mesmos")
    checa("PAGINA" not in _codigos(avisos) and "PAPEL_INVALIDO" not in _codigos(avisos),
          "pagina representada nao gera aviso de perda")

    retrato = escrever(Documento(paragrafos=[Paragrafo(runs=[Run("a")])]))
    xml_retrato = fx.partes_de(retrato)["word/document.xml"].decode("utf-8")
    checa(' orient="landscape"' not in xml_retrato,
          "contraprova: retrato nao grava orient=landscape")
    checa(re.search(r'<w:pgSz w:w="11906" w:h="16838"/>', xml_retrato) is not None,
          "padrao: A4 em retrato, 11906 x 16838")
    padrao, _ = ler(retrato)
    checa_igual(padrao.pagina, Pagina(), "o padrao volta como A4 com margens Normal")

    antigo = Pagina(margem_sup_tw=1417, margem_inf_tw=1417, margem_esq_tw=1701, margem_dir_tw=1701,
                    cabecalho_tw=708, rodape_tw=708)
    dados_antigos = escrever(Documento(paragrafos=[Paragrafo(runs=[Run("m2")])], pagina=antigo))
    lido2, avisos2 = ler(dados_antigos)
    checa_igual(lido2.pagina, antigo, "margens de 2,5 cm e 3 cm (padrao do M2) voltam iguais")
    checa("PAGINA" not in _codigos(avisos2),
          "o aviso PAGINA saiu para documento de uma secao, mesmo com margens diferentes do padrao")


def testar_secoes_e_pagina_invalida() -> None:
    secao("mais de uma secao (0.1.12: sem aviso, cada uma com o seu papel); papel que nao cabe avisa e sai com A4")
    sectpr_meio = ('<w:p><w:pPr><w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                   '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
                   'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr></w:pPr>'
                   '<w:r><w:t>fim da primeira secao</w:t></w:r></w:p>')
    dados = _xml_com_corpo(sectpr_meio + '<w:p><w:r><w:t>segunda</w:t></w:r></w:p>')
    lido, avisos = ler(dados)
    codigos = _codigos(avisos)
    # 0.1.12: as secoes voltam ao arquivo; os avisos PAGINA e SECAO (perda) eram da 0.1.11.
    checa(not codigos and lido.paragrafos[0].secao is not None,
          f"duas secoes: sem aviso, a primeira termina no seu paragrafo (avisos: {codigos})")
    checa_igual(lido.paragrafos[0].secao.pagina, Pagina(),
                "a primeira secao fica com o papel e as margens do seu sectPr")
    unica = _xml_com_corpo('<w:p><w:r><w:t>so uma</w:t></w:r></w:p>')
    _, avisos_unica = ler(unica)
    checa("PAGINA" not in _codigos(avisos_unica),
          "contraprova: uma secao so' nao gera PAGINA")

    invalido = fx.com_parte(
        fx.bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("x")])])), "word/document.xml",
        fx.partes_de(fx.bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("x")])])))["word/document.xml"]
        .replace(b'w:top="1440"', b'w:top="9000"').replace(b'w:bottom="1440"', b'w:bottom="9000"'))
    modelo_inv, avisos_inv = ler(invalido)
    checa("PAPEL_INVALIDO" in _codigos(avisos_inv),
          "margens que comem a pagina geram PAPEL_INVALIDO")
    checa_igual(modelo_inv.pagina, Pagina(),
                "com papel invalido, o arquivo e' lido com A4 e margens padrao")

    gigante = fx.com_parte(
        fx.bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("x")])])), "word/document.xml",
        fx.partes_de(fx.bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("x")])])))["word/document.xml"]
        .replace(b'w:w="11906"', b'w:w="999999999"'))
    modelo_gig, avisos_gig = ler(gigante)
    checa("PAPEL_INVALIDO" in _codigos(avisos_gig),
          "contraprova: papel de bilhoes de twips e' recusado, nao alocado")
    checa_igual(modelo_gig.pagina.largura_tw, 11906, "o papel gigante cai no A4 padrao")


def testar_janela() -> None:
    secao("janela: papel, orientacao, margens e o dialogo de margens personalizadas")
    from editdoc import configuracao
    from editdoc.interface import dialogos_modais
    from editdoc.interface.janela_principal import JanelaPrincipal

    janela = JanelaPrincipal(configuracao.padrao())
    janela.show()
    drenar_eventos(2)
    checa(not janela.sujo(), "documento novo nasce limpo, mesmo com a pagina montada")
    checa(janela.comandos.acao("papel_a4").isChecked(), "A4 vem marcado no menu")
    checa(janela.comandos.acao("margens_normal").isChecked(), "Normal vem marcada")

    janela.comandos.acao("papel_carta").trigger()
    checa_igual(janela.painel.configuracao_pagina().nome_do_papel(), "Carta", "Carta vale")
    checa(janela.sujo(), "trocar o papel marca o documento como alterado")
    checa(janela.comandos.acao("papel_carta").isChecked()
          and not janela.comandos.acao("papel_a4").isChecked(),
          "a marca do menu acompanha o papel")

    janela.comandos.acao("paisagem").trigger()
    checa(janela.painel.configuracao_pagina().paisagem, "paisagem vale")
    checa(janela.comandos.acao("paisagem").isChecked() and not janela.comandos.acao("retrato").isChecked(),
          "a marca de orientacao acompanha")

    janela.comandos.acao("margens_estreita").trigger()
    checa_igual(janela.painel.configuracao_pagina().margem_esq_tw, 720, "Estreita: 720 twips")

    anterior = janela.painel.configuracao_pagina()
    with _trocado(dialogos_modais, pedir_margens=lambda pai, atual: None):
        janela.comandos.acao("margens_personalizadas").trigger()
    checa_igual(janela.painel.configuracao_pagina(), anterior,
                "cancelar as margens personalizadas nao muda a pagina")
    checa(janela.comandos.acao("margens_estreita").isChecked()
          and not janela.comandos.acao("margens_personalizadas").isChecked(),
          "cancelar devolve a marca para a predefinicao que vale")

    with _trocado(dialogos_modais, pedir_margens=lambda pai, atual: atual.com_margens(1134, 1134, 1134, 1134)):
        janela.comandos.acao("margens_personalizadas").trigger()
    checa_igual(janela.painel.configuracao_pagina().margem_sup_tw, 1134, "margens personalizadas: 2 cm")
    checa(janela.comandos.acao("margens_personalizadas").isChecked(),
          "com margens fora das predefinicoes, Personalizadas fica marcada")

    # Salvar e reabrir: o que a janela mostra e' o que o arquivo leva.
    pagina_janela = janela.painel.configuracao_pagina()
    with pasta_temporaria() as tmp:
        alvo = tmp / "layout.docx"
        with _trocado(dialogos_modais, pedir_salvar_arquivo=lambda pai, sugestao: str(alvo)):
            janela.comandos.acao("salvar_como").trigger()
        checa(alvo.is_file() and not janela.sujo(), "salvar grava o arquivo e limpa o estado de alterado")
        lido, avisos = ler(alvo.read_bytes())
        checa_igual(lido.pagina, pagina_janela, "o arquivo gravado leva a pagina da janela")
        checa(not avisos, f"layout nao gera aviso ao salvar (avisos: {_codigos(avisos)})")
        outra = JanelaPrincipal(configuracao.padrao())
        outra.show()
        outra.carregar(lido, avisos, alvo)
        drenar_eventos(2)
        checa_igual(outra.painel.configuracao_pagina(), pagina_janela,
                    "ao abrir, a janela aplica a pagina lida")
        checa(not outra.sujo(), "abrir com layout nao deixa o documento sujo")
        checa(outra.comandos.acao("margens_personalizadas").isChecked(),
              "a janela aberta marca as margens do arquivo")
        outra.painel.document().setModified(False)
        outra.close()
    janela.painel.document().setModified(False)
    janela.close()


class _trocado:
    """Troca funcoes de dialogos_modais e devolve tudo ao sair do bloco."""

    def __init__(self, modulo, **substitutos) -> None:
        self._modulo = modulo
        self._substitutos = substitutos
        self._originais = {}

    def __enter__(self):
        for nome, funcao in self._substitutos.items():
            self._originais[nome] = getattr(self._modulo, nome)
            setattr(self._modulo, nome, funcao)
        return self

    def __exit__(self, *exc) -> None:
        for nome, funcao in self._originais.items():
            setattr(self._modulo, nome, funcao)


def main() -> int:
    testar_sectpr()
    testar_secoes_e_pagina_invalida()
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    if not usar_fonte_windows(9):
        return pular("Segoe UI nao esta instalada")
    testar_janela()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
