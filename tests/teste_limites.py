"""Limites conhecidos corrigidos no M8, cada um com a contraprova.

- docDefaults: o espacamento do arquivo (8 pt depois, 1,08 entre linhas no Word) aparece na
  tela, fora da tabela; dentro dela, nao (o "Table Grid" zera). No arquivo ele continua no
  docDefaults, e o paragrafo nao ganha formatacao direta. O documento novo nasce com ele e
  com a fonte da preferencia, que vai para o docDefaults gravado.
- Tabela mais larga que o corpo entra na margem direita, como no Word (antes era cortada).
- Linha vazia antes da tabela: medida, nao se reproduz no Qt 6.11.2 (o bloco que o Qt exige
  antes da tabela nao ocupa altura). O teste trava isso.
"""

from __future__ import annotations

from ajudantes import (checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao,
                       usar_fonte_windows)
import fixtures_docx as fx

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QTextBlockFormat  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from editdoc import configuracao  # noqa: E402
from editdoc.edicao import tabelas as ed_tabelas  # noqa: E402
from editdoc.formato_docx.escritor import escrever  # noqa: E402
from editdoc.formato_docx.leitor import ler  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402
from editdoc.modelo.documento import Celula, Documento, Linha, Paragrafo, Run, Tabela  # noqa: E402
from editdoc.modelo.unidades import twips_de_px  # noqa: E402

_PROPORCIONAL = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value


def janela(cfg=None) -> JanelaPrincipal:
    j = JanelaPrincipal(cfg or configuracao.padrao())
    j.resize(1100, 900)
    j.show()
    drenar_eventos()
    return j


def fechar(j) -> None:
    j.painel.documento_corpo().setModified(False)
    j.close()
    drenar_eventos()


def tabela(colunas_tw: list[int], texto: str = "c") -> Tabela:
    return Tabela(colunas_tw=colunas_tw, linhas=[Linha(celulas=[
        Celula(blocos=[Paragrafo(runs=[Run(f"{texto}{i}")])]) for i in range(len(colunas_tw))])])


def blocos(doc):
    b = doc.begin()
    while b.isValid():
        yield b
        b = b.next()


def docx_com_padrao(depois: str | None, linha: str | None) -> bytes:
    """Um .docx cujo docDefaults tem o espacamento pedido (None = sem o atributo)."""
    base = fx.bytes_de(Documento(paragrafos=[Paragrafo(runs=[Run("um")]), Paragrafo(runs=[Run("dois")]),
                                             tabela([3000, 3000])] + [Paragrafo(runs=[Run("fim")])]))
    partes = fx.partes_de(base)
    estilos = partes["word/styles.xml"].decode("utf-8")
    inicio = estilos.index("<w:pPrDefault>")
    fim = estilos.index("</w:pPrDefault>") + len("</w:pPrDefault>")
    atributos = "".join(f' w:{k}="{v}"' for k, v in (("after", depois), ("line", linha)) if v)
    if linha:
        atributos += ' w:lineRule="auto"'
    novo = estilos[:inicio] + f"<w:pPrDefault><w:pPr><w:spacing{atributos}/></w:pPr></w:pPrDefault>" \
        + estilos[fim:]
    return fx.com_parte(base, "word/styles.xml", novo.encode("utf-8"))


def testar_docdefaults_na_tela() -> None:
    secao("docDefaults: 8 pt depois e 1,08 aparecem na tela, fora da tabela")
    modelo, _ = ler(docx_com_padrao("160", "259"))
    checa_igual(modelo.estilos.padrao_paragrafo,
                {"espaco_depois_tw": 160, "espacamento_linha_pct": 108},
                "o leitor guarda o docDefaults de paragrafo")
    j = janela()
    j.carregar(modelo, [], None)
    doc = j.painel.documento_corpo()
    corpo = [b for b in blocos(doc) if b.text() in ("um", "dois")]
    bf = corpo[0].blockFormat()
    checa_igual(twips_de_px(bf.bottomMargin()), 160, "o paragrafo do corpo tem 8 pt depois")
    checa(bf.lineHeightType() == _PROPORCIONAL and round(bf.lineHeight()) == 108,
          "e 108% entre linhas")
    dl = doc.documentLayout()
    distancia = dl.blockBoundingRect(corpo[1]).top() - dl.blockBoundingRect(corpo[0]).top()
    altura_linha = corpo[0].layout().lineAt(0).height()
    checa(distancia >= altura_linha + 150, f"o segundo paragrafo desce o espaco ({distancia:.0f} tw)")
    celula = next(b for b in blocos(doc) if b.text() == "c0")
    checa_igual(twips_de_px(celula.blockFormat().bottomMargin()), 0,
                "dentro da tabela, sem o espacamento (como o Table Grid do Word)")
    gravado, _ = ler(escrever(j._modelo_atual()))
    primeiro = gravado.paragrafos[0]
    checa(primeiro.espaco_depois_tw is None and primeiro.espacamento_linha_pct is None,
          "salvar nao transforma o docDefaults em formatacao direta")
    celula_gravada = gravado.paragrafos[2].linhas[0].celulas[0].blocos[0]
    checa(celula_gravada.espaco_depois_tw is None, "nem na celula")
    checa_igual(gravado.estilos.padrao_paragrafo, modelo.estilos.padrao_paragrafo,
                "o docDefaults volta igual ao arquivo")

    sem, _ = ler(docx_com_padrao(None, None))
    j.carregar(sem, [], None)
    um = next(b for b in blocos(j.painel.documento_corpo()) if b.text() == "um")
    checa_igual(twips_de_px(um.blockFormat().bottomMargin()), 0,
                "contraprova: docDefaults sem espacamento, paragrafo sem espaco")
    fechar(j)


def testar_documento_novo() -> None:
    secao("documento novo: docDefaults do Word e a fonte da preferencia no arquivo")
    cfg = {**configuracao.padrao(), "fonte_padrao": "Arial", "tamanho_padrao": 12}
    j = janela(cfg)
    painel = j.painel
    checa(not j.sujo(), "o documento novo nasce limpo")
    painel.insertPlainText("primeiro")
    QTest.keyClick(painel, Qt.Key.Key_Return)
    painel.insertPlainText("segundo")
    doc = painel.documento_corpo()
    for b in blocos(doc):
        checa_igual(twips_de_px(b.blockFormat().bottomMargin()), 160,
                    f"'{b.text()}': 8 pt depois, como o Word mostrara' o arquivo")
    dados = escrever(j._modelo_atual())
    estilos_xml = fx.partes_de(dados)["word/styles.xml"].decode("utf-8")
    checa('w:ascii="Arial"' in estilos_xml and '<w:sz w:val="24"/>' in estilos_xml,
          "o docDefaults gravado tem a fonte e o tamanho da preferencia")
    lido, _ = ler(dados)
    checa(all(p.espaco_depois_tw is None for p in lido.paragrafos),
          "o espacamento nao vira formatacao direta")
    checa_igual([p.runs[0].texto for p in lido.paragrafos], ["primeiro", "segundo"], "o texto volta")
    fechar(j)
    padrao = janela()
    estilos_xml = fx.partes_de(escrever(padrao._modelo_atual()))["word/styles.xml"].decode("utf-8")
    checa('w:ascii="Calibri"' in estilos_xml, "contraprova: sem preferencia, Calibri")
    fechar(padrao)


def _tinta(img, x: int, y0: int, y1: int) -> bool:
    for y in range(y0, y1):
        if QColor(img.pixel(x, y)).lightness() < 128:
            return True
    return False


def testar_tabela_larga() -> None:
    secao("tabela mais larga que o corpo: entra na margem direita, como no Word")
    usar_fonte_windows()
    j = janela()
    larga = Documento(paragrafos=[tabela([6000, 6000]), Paragrafo(runs=[Run("depois")])])
    j.carregar(larga, [], None)
    drenar_eventos()
    j.painel._limpar_cache()
    img = j.painel.viewport().grab().toImage()
    m = j.painel.mapa()
    pagina = j.painel.configuracao_pagina()
    corpo_fim = m.esquerda_folha - m.origem_x + (pagina.margem_esq_tw + pagina.corpo_largura_tw()) * m.escala
    folha_fim = m.esquerda_folha - m.origem_x + pagina.largura_tw * m.escala
    x = int((corpo_fim + folha_fim) / 2)  # meio da margem direita da folha
    y0, y1 = 0, int(min(img.height(), 400))  # a tabela fica no alto da primeira folha
    checa(_tinta(img, x, y0, y1), "a borda da tabela aparece na margem direita")
    estreita = Documento(paragrafos=[tabela([3000, 3000]), Paragrafo(runs=[Run("depois")])])
    j.carregar(estreita, [], None)
    drenar_eventos()
    j.painel._limpar_cache()
    img = j.painel.viewport().grab().toImage()
    checa(not _tinta(img, x, y0, y1), "contraprova: a tabela estreita deixa a margem limpa")
    fechar(j)


def testar_sem_linha_fantasma() -> None:
    secao("linha vazia antes da tabela: medida, nao aparece")
    j = janela()
    j.carregar(Documento(paragrafos=[tabela([3000]), tabela([3000]), Paragrafo(runs=[Run("x")])]),
               [], None)
    doc = j.painel.documento_corpo()
    dl = doc.documentLayout()
    quadros = doc.rootFrame().childFrames()
    checa(len(quadros) == 2, "duas tabelas")
    checa(dl.frameBoundingRect(quadros[0]).top() <= 20,
          f"a tabela do comeco fica no topo do corpo ({dl.frameBoundingRect(quadros[0]).top():.0f} tw)")
    vao = dl.frameBoundingRect(quadros[1]).top() - dl.frameBoundingRect(quadros[0]).bottom()
    checa(vao <= 20, f"duas tabelas seguidas se encostam ({vao:.0f} tw)")
    j.carregar(Documento(paragrafos=[Paragrafo(runs=[Run("")]), Paragrafo(runs=[Run("x")])]), [], None)
    cursor = j.painel.textCursor()
    cursor.movePosition(cursor.MoveOperation.Start)
    j.painel.setTextCursor(cursor)
    ed_tabelas.inserir_tabela(j.painel, 1, 2)
    quadro = doc.rootFrame().childFrames()[0]
    checa(dl.frameBoundingRect(quadro).top() <= 20, "inserir tabela na primeira linha vazia: no topo")
    linha = doc.begin().layout().lineAt(0).height() if doc.begin().layout().lineCount() else 0
    checa(linha > 100, "contraprova: uma linha de texto tem altura (o teste mede alguma coisa)")
    fechar(j)


def main() -> int:
    testar_docdefaults_na_tela()
    testar_documento_novo()
    testar_tabela_larga()
    testar_sem_linha_fantasma()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
