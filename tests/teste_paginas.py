"""Paginas: configuracao de pagina, geometria das folhas e o layout paginado.

Duas partes. A primeira (modelo e geometria) nao precisa de Qt: roda em qualquer
Python. A segunda usa o QTextDocument paginado com a fonte do Windows: contagem de
paginas estavel, nenhuma linha cruzando a fronteira e hit-test com 1000 posicoes
por zoom (25, 100 e 400%). Toda checagem tem uma contraprova que tem de ser acusada.
"""

from __future__ import annotations

import random

from ajudantes import checa, checa_igual, drenar_eventos, pular, preparar_qt, resumir, secao, usar_fonte_windows

QT = preparar_qt()

from editdoc.modelo.folhas import (Mapa, alinhar_ao_dispositivo, limitar_zoom,  # noqa: E402
                                   passo_de_zoom, teto_de_zoom)
from editdoc.modelo.pagina import CORPO_MINIMO_TW, PAPEIS, Pagina  # noqa: E402


def testar_pagina() -> None:
    secao("pagina: papel, orientacao e margens (sem Qt)")
    p = Pagina()
    checa_igual((p.largura_tw, p.altura_tw), (11906, 16838), "padrao e' A4 em retrato")
    checa_igual(p.corpo_largura_tw(), 11906 - 2880, "corpo = papel menos margens esquerda e direita")
    checa_igual(p.nome_do_papel(), "A4", "A4 reconhecido")
    checa_igual(p.nome_das_margens(), "Normal", "margens de 2,54 cm: predefinicao Normal")
    checa(p.valida(), "a pagina padrao e' valida")

    paisagem = p.com_orientacao(True)
    checa_igual((paisagem.largura_tw, paisagem.altura_tw), (16838, 11906),
                "paisagem troca largura e altura")
    checa_igual(paisagem.nome_do_papel(), "A4", "A4 em paisagem continua A4")
    checa_igual(paisagem.com_orientacao(False), p, "voltar ao retrato restaura a pagina")

    carta = p.com_papel("Carta")
    checa_igual((carta.largura_tw, carta.altura_tw), PAPEIS["Carta"], "papel Carta")
    checa_igual(carta.com_papel("A4").paisagem, False, "trocar o papel nao mexe na orientacao")
    checa_igual(p.com_papel("Ofício").altura_tw, 18720, "Oficio com 13 polegadas de altura")

    estreita = p.com_margens(720, 720, 720, 720)
    checa_igual(estreita.nome_das_margens(), "Estreita", "margens de 1,27 cm: Estreita")
    checa_igual(p.com_margens(1440, 1440, 1080, 1080).nome_das_margens(), "Moderada",
                "Moderada reconhecida")
    checa_igual(p.com_margens(1000, 1440, 1440, 1440).nome_das_margens(), "Personalizadas",
                "margem fora das predefinicoes vira Personalizadas")

    corpo_pequeno = p.com_margens(9000, 9000, 1440, 1440)
    checa(not corpo_pequeno.valida(), "margem que come o corpo deixa a pagina invalida")
    checa(CORPO_MINIMO_TW > 0, "contraprova: o corpo minimo existe e e' positivo")


def testar_zoom() -> None:
    secao("zoom: teto pela escala da tela, passos e limites")
    checa_igual(teto_de_zoom(1.0), 3.0, "DPR 1: zoom maximo 300% (escala de tela 300%)")
    checa_igual(teto_de_zoom(1.5), 2.0, "DPR 1,5: zoom maximo 200% (escala de tela 300%)")
    checa_igual(teto_de_zoom(2.0), 1.5, "DPR 2: zoom maximo 150% (escala de tela 300%)")
    checa_igual(teto_de_zoom(1.25), 2.4, "DPR 1,25: zoom maximo 240%")
    checa_igual(limitar_zoom(10.0, 1.0), 3.0, "zoom acima do teto e' cortado")
    checa_igual(limitar_zoom(0.01, 1.0), 0.25, "zoom abaixo de 25% e' elevado")
    checa_igual(limitar_zoom(3.0, 1.5), 2.0, "3,0 numa tela de DPR 1,5 cai para o teto")
    checa_igual(passo_de_zoom(1.0, True, 1.0), 1.25, "Ampliar vai ao passo seguinte")
    checa_igual(passo_de_zoom(1.0, False, 1.0), 0.75, "Reduzir vai ao passo anterior")
    checa_igual(passo_de_zoom(3.0, True, 1.0), 3.0, "no teto, Ampliar nao passa de 300%")
    checa_igual(passo_de_zoom(1.5, True, 1.5), 2.0,
                "entre 150% e o teto (200%) o proximo passo e' o teto da tela")
    checa_igual(passo_de_zoom(0.25, False, 1.0), 0.25, "no minimo, Reduzir fica em 25%")
    checa(passo_de_zoom(1.5, True, 1.5) <= 2.0,
          "contraprova: 200% e' o teto numa tela de 150%: nenhum passo passa dele")


def testar_mapa() -> None:
    secao("mapa folha <-> tela: ida e volta, pagina por altura e espacamento entre folhas")
    pagina = Pagina()
    hb = float(pagina.corpo_altura_tw())
    rng = random.Random(3)
    erro_maximo = 0.0
    for zoom in (0.25, 1.0, 2.66, 4.0):
        for _ in range(250):
            m = Mapa(pagina, zoom, 1200.0, 640.0, rng.uniform(0, 4000), rng.uniform(0, 20000))
            x = rng.uniform(0, pagina.corpo_largura_tw())
            y = rng.uniform(0, 40 * hb)
            tx, ty = m.doc_para_tela(x, y, 50)
            x2, y2 = m.tela_para_doc(tx, ty, 50)
            erro_maximo = max(erro_maximo, abs(x2 - x), abs(y2 - y))
    checa(erro_maximo < 1e-6,
          f"1000 pontos em 4 zooms voltam ao mesmo lugar (maior erro {erro_maximo:.2e} twips)")

    m = Mapa(pagina, 1.0, 1200.0, 640.0)
    ok = all(m.pagina_de_y(n * hb - 0.5, 50) == n - 1 and m.pagina_de_y(n * hb, 50) == n
             for n in range(1, 50))
    checa(ok, "a pagina n comeca exatamente em n*altura do corpo")
    checa_igual(m.pagina_de_y(-5.0, 50), 0, "antes do inicio cai na pagina 0")
    checa_igual(m.pagina_de_y(1e9, 50), 49, "depois do fim cai na ultima pagina")

    for zoom in (0.25, 1.0, 4.0):
        m = Mapa(pagina, zoom, 1200.0, 640.0)
        passo = m.passo_vertical
        espaco = passo - m.altura_folha
        checa(abs(espaco - 24.0 * zoom) < 1e-9 and espaco > 0,
              f"zoom {int(zoom * 100)}%: vao entre folhas de {24 * zoom:g} px logicos")
        y0 = m.folha_na_tela(0)[1]
        y1 = m.folha_na_tela(1)[1]
        checa(abs((y1 - y0) - passo) < 1e-9, f"zoom {int(zoom * 100)}%: folhas empilhadas no passo")

    # Contraprova: uma folha com a margem superior deslocada em 100 twips mapeia o mesmo
    # ponto a outra altura. Se isto nao acusasse, o teste de mapa nao pegaria nada.
    deslocada = pagina.com_margens(1440 + 100, 1440, 1440, 1440)
    a = Mapa(pagina, 1.0, 1200.0, 640.0).doc_para_tela(0.0, 0.0, 5)
    b = Mapa(deslocada, 1.0, 1200.0, 640.0).doc_para_tela(0.0, 0.0, 5)
    checa(abs(a[1] - b[1]) > 0.5, "contraprova: margem deslocada muda a posicao na tela")


def testar_alinhamento_hidpi() -> None:
    secao("HiDPI: bordas da folha em pixel de dispositivo inteiro, em DPR 1, 1,5 e 2")
    rng = random.Random(9)
    valores = [rng.uniform(0, 3000) for _ in range(1000)]
    for dpr in (1.0, 1.5, 2.0):
        alinhados = [alinhar_ao_dispositivo(v, dpr) for v in valores]
        ruins = [a for a in alinhados if abs(a * dpr - round(a * dpr)) > 1e-9]
        checa_igual(ruins, [], f"DPR {dpr}: 1000 bordas caem em pixel de dispositivo inteiro")
    cru = [v for v in valores if abs(v * 1.5 - round(v * 1.5)) > 1e-9]
    checa(len(cru) > 0, "contraprova: sem alinhar, as bordas caem fora do pixel em DPR 1,5")


def testar_layout_qt() -> None:
    secao("layout paginado: paginas estaveis, fronteiras e caret (Segoe UI)")
    if not usar_fonte_windows(9):
        checa(False, "a fonte Segoe UI esta' instalada (sem ela o layout nao vale)")
        return
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QTextCursor

    from editdoc.interface.layout_paginado import LayoutPaginado
    from editdoc.interface.painel_documento import PainelDocumento

    pagina = Pagina()
    texto = "\n".join(
        f"Paragrafo {i} com um texto de tamanho razoavel para ocupar mais de uma linha da pagina, "
        f"com acentuacao e palavras comuns como documento, relatorio e revisao."
        for i in range(400))

    lay = LayoutPaginado(pagina, "Segoe UI", 11)
    lay.doc.setPlainText(texto)
    paginas_carregado = lay.numero_paginas()
    checa(paginas_carregado >= 5, f"o texto de teste ocupa varias paginas ({paginas_carregado})")

    # Redigitar: esvaziar e inserir o mesmo texto em pedacos, como a digitacao faz.
    lay.doc.clear()
    cur = QTextCursor(lay.doc)
    for i, linha in enumerate(texto.split("\n")):
        if i:
            cur.insertBlock()
        cur.insertText(linha)
    checa_igual(lay.numero_paginas(), paginas_carregado,
                "o numero de paginas e' o mesmo depois de carregar e de redigitar")
    lay.fechar()

    def linhas_que_cruzam(layout, hb_extra: float = 0.0) -> int:
        """Quantas linhas do corpo passam da fronteira de uma pagina.

        hb_extra desloca a fronteira (para a contraprova): com 0, o correto e' zero.
        """
        hb = layout.hb + hb_extra
        dl = layout.doc.documentLayout()
        ruins = 0
        bloco = layout.doc.begin()
        while bloco.isValid():
            origem = layout.origem_bloco(bloco)
            lay_b = bloco.layout()
            for i in range(lay_b.lineCount()):
                linha = lay_b.lineAt(i)
                topo = origem.y() + linha.y()
                base = topo + linha.height()
                if int(topo // hb) != int((base - 1e-3) // hb):
                    ruins += 1
            bloco = bloco.next()
        del dl
        return ruins

    lay = LayoutPaginado(pagina, "Segoe UI", 11)
    lay.doc.setPlainText(texto)
    checa_igual(linhas_que_cruzam(lay), 0,
                "nenhuma linha do corpo cruza a fronteira de pagina")
    contra = linhas_que_cruzam(lay, hb_extra=73.0)
    checa(contra > 0, f"contraprova: fronteira deslocada em 73 twips acusa {contra} linhas")
    lay.fechar()

    # Hit-test: para cada zoom, 1000 posicoes sorteadas; o caret vai para a tela pelo
    # mapa e volta pelo painel. A diferenca maxima tem de ser de 1 caractere.
    painel = PainelDocumento("Segoe UI", 11)
    painel.resize(1200, 640)
    painel.show()
    drenar_eventos(2)
    painel.setPlainText(texto)
    total = len(painel.toPlainText())
    rng = random.Random(5)
    posicoes = [rng.randrange(0, total) for _ in range(1000)]
    for zoom in (0.25, 1.0, 4.0):
        painel.definir_zoom(zoom)
        m = painel.mapa()
        n_total = painel.total_de_paginas()
        maior = 0
        falhas = 0
        contra_falhas = 0
        for pos in posicoes:
            r = painel.layout_pag.retangulo_cursor(pos)
            cx, cy = r.center().x(), r.center().y()
            tx, ty = m.doc_para_tela(cx, cy, n_total)
            volta = painel.posicao_em(QPointF(tx, ty))
            diff = abs(volta - pos)
            maior = max(maior, diff)
            if diff > 1:
                falhas += 1
            # contraprova: 3 linhas abaixo do caret nao pode dar a mesma posicao
            ty_errado = ty + 3 * r.height() * zoom
            if abs(painel.posicao_em(QPointF(tx, ty_errado)) - pos) > 1:
                contra_falhas += 1
        checa(falhas == 0 and maior <= 1,
              f"zoom {int(zoom * 100)}%: 1000 posicoes ida e volta, maior diferenca {maior} caractere(s)")
        checa(contra_falhas > 800,
              f"zoom {int(zoom * 100)}%: contraprova, 3 linhas abaixo acusam {contra_falhas}/1000")
    painel.document().setModified(False)
    painel.close()


def main() -> int:
    testar_pagina()
    testar_zoom()
    testar_mapa()
    testar_alinhamento_hidpi()
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    testar_layout_qt()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
