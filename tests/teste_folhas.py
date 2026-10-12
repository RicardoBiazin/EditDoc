"""Regressao estrutural das folhas: medida em pixels do QImage, sem imagens de referencia.

Pinta a visao offscreen com a fonte do Windows e confere, em pixels:
  - a folha e' um retangulo branco no lugar que a geometria diz, com borda nitida;
  - a margem (superior, inferior, esquerda e direita) nao tem tinta nenhuma;
  - a tinta do texto fica dentro do corpo, e nao e' vazia;
  - a mesma conta vale em 100% e em 25%.
Contraprova: tinta injetada numa margem tem de ser acusada pelo mesmo detector.
"""

from __future__ import annotations

from ajudantes import checa, checa_igual, drenar_eventos, pular, preparar_qt, resumir, secao, usar_fonte_windows

QT = preparar_qt()

BRANCO = 0xFFFFFF


def cor_rgb(img, x: int, y: int) -> int:
    return img.pixel(x, y) & 0xFFFFFF


def tinta_na_faixa(img, x0: int, y0: int, x1: int, y1: int) -> int:
    """Quantos pixels da faixa [x0, x1) x [y0, y1) nao sao brancos."""
    n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if cor_rgb(img, x, y) != BRANCO:
                n += 1
    return n


def caixa_da_tinta(img, x0: int, y0: int, x1: int, y1: int):
    """(menor x, menor y, maior x, maior y) dos pixels nao brancos da faixa, ou None."""
    minx = miny = None
    maxx = maxy = None
    for y in range(y0, y1):
        for x in range(x0, x1):
            if cor_rgb(img, x, y) != BRANCO:
                minx = x if minx is None else min(minx, x)
                maxx = x if maxx is None else max(maxx, x)
                miny = y if miny is None else min(miny, y)
                maxy = y if maxy is None else max(maxy, y)
    if minx is None:
        return None
    return minx, miny, maxx, maxy


def margens_da_folha(m) -> tuple[float, float, float, float]:
    """Margens (sup, inf, esq, dir) de uma folha, em pixels logicos."""
    cfg = m.pagina
    e = m.escala
    return (cfg.margem_sup_tw * e, cfg.margem_inf_tw * e, cfg.margem_esq_tw * e, cfg.margem_dir_tw * e)


def tinta_nas_margens(img, x: int, y: int, w: int, h: int, margens) -> int:
    """Tinta nas quatro margens da folha (x, y, w, h), sem contar a borda de 1 pixel."""
    sup, inf, esq, dir_ = (round(v) for v in margens)
    total = 0
    total += tinta_na_faixa(img, x + 1, y + 1, x + w - 1, y + sup)
    total += tinta_na_faixa(img, x + 1, y + h - inf, x + w - 1, y + h - 1)
    total += tinta_na_faixa(img, x + 1, y + sup, x + esq, y + h - inf)
    total += tinta_na_faixa(img, x + w - dir_, y + sup, x + w - 1, y + h - inf)
    return total


def testar_folhas(zoom: float) -> None:
    """Confere a folha em pixels de DISPOSITIVO (a captura vem em pixels de dispositivo).

    Coordenadas logicas da geometria viram pixels de dispositivo pelo mesmo arredondamento da
    pintura (alinhar_ao_dispositivo). Assim a conta vale em DPR 1, 1,5 e 2.
    """
    from PySide6.QtGui import QColor, QPainter

    from editdoc.interface.painel_documento import PainelDocumento
    from editdoc.modelo.folhas import alinhar_ao_dispositivo

    rotulo = f"zoom {int(zoom * 100)}%"
    painel = PainelDocumento("Segoe UI", 11)
    painel.resize(1000, 1250)
    painel.show()
    drenar_eventos(2)
    painel.setPlainText("\n".join(
        f"Linha {i} de texto para aparecer dentro do corpo da folha, com acentos: ação e órgão."
        for i in range(60)))
    painel.clearFocus()
    painel.definir_zoom(zoom)
    painel.verticalScrollBar().setValue(0)
    painel.horizontalScrollBar().setValue(0)
    drenar_eventos(2)

    img = painel.viewport().grab().toImage()
    k = img.devicePixelRatio()
    m = painel.mapa()
    xl, yl, wl, hl = m.folha_na_tela(0)
    x0 = round(alinhar_ao_dispositivo(xl, k) * k)
    y0 = round(alinhar_ao_dispositivo(yl, k) * k)
    x1 = round(alinhar_ao_dispositivo(xl + wl, k) * k)
    y1 = round(alinhar_ao_dispositivo(yl + hl, k) * k)
    w, h = x1 - x0, y1 - y0
    cfg = m.pagina
    e = m.escala * k
    sup, inf = cfg.margem_sup_tw * e, cfg.margem_inf_tw * e
    esq, dir_ = cfg.margem_esq_tw * e, cfg.margem_dir_tw * e
    margens = (sup, inf, esq, dir_)
    checa(y0 >= 0 and y1 <= img.height() and x0 >= 0 and x1 <= img.width(),
          f"{rotulo}: a folha inteira cabe na captura ({img.width()}x{img.height()}, DPR {k:g})")

    # 1. retangulo: a borda do branco cai exatamente nas bordas de dispositivo da folha
    meio = y0 + h // 2
    primeiro = next(xx for xx in range(0, x0 + 40) if cor_rgb(img, xx, meio) == BRANCO)
    checa_igual(primeiro, x0, f"{rotulo}: a folha comeca em x={x0} (borda nitida, DPR {k:g})")
    checa(cor_rgb(img, x0 - 1, meio) != BRANCO, f"{rotulo}: pixel logo a esquerda da folha nao e' branco")
    checa(cor_rgb(img, x1 - 1, meio) == BRANCO and cor_rgb(img, x1, meio) != BRANCO,
          f"{rotulo}: a borda direita da folha cai em x={x1}")
    checa(cor_rgb(img, x0 + w // 2, y0) == BRANCO and cor_rgb(img, x0 + w // 2, y0 - 1) != BRANCO,
          f"{rotulo}: a borda de cima da folha cai em y={y0}")

    # 2. margens sem tinta
    tinta = tinta_nas_margens(img, x0, y0, w, h, margens)
    checa_igual(tinta, 0, f"{rotulo}: nenhuma tinta nas margens da folha")

    # 3. tinta do texto dentro do corpo, e nao vazia
    caixa = caixa_da_tinta(img, x0 + 1, y0 + 1, x1 - 1, y1 - 1)
    checa(caixa is not None, f"{rotulo}: o texto aparece na folha")
    if caixa is not None:
        cx0, cy0, cx1, cy1 = caixa
        checa(cx0 >= x0 + esq - k and cx1 <= x1 - dir_ + k and cy0 >= y0 + sup - k
              and cy1 <= y1 - inf + k,
              f"{rotulo}: a tinta do texto cabe no corpo ({caixa})")

    # 4. contraprova: uma marca na margem esquerda tem de ser acusada
    suja = img.copy()
    suja.setDevicePixelRatio(1.0)  # o painter com DPR desenha em logico: aqui, dispositivo
    p = QPainter(suja)
    p.fillRect(x0 + 2, y0 + round(sup) + 20, 3, 12, QColor(255, 0, 0))
    p.end()
    acusou = tinta_nas_margens(suja, x0, y0, w, h, margens)
    checa(acusou > 0, f"{rotulo}: contraprova, marca vermelha de 3x12 px na margem e' acusada ({acusou})")

    # 5. a segunda folha: vao e altura pelo mesmo zoom
    xl2, yl2, wl2, hl2 = m.folha_na_tela(1)
    checa_igual(round((yl2 - (yl + hl)) * 1000), round(m.vao * 1000),
                f"{rotulo}: o vao entre folhas e' o do zoom")
    checa_igual(round(hl2 * 1000), round(hl * 1000), f"{rotulo}: a segunda folha tem a mesma altura")
    painel.close()


def testar_cache_igual_ao_quadro_novo() -> None:
    """Cache de tiles: depois de cada edicao, o quadro com cache e' igual ao quadro refeito do zero.

    Contraprova: sem a invalidacao (metodo trocado por um que nao faz nada), o quadro com cache
    tem de sair diferente do quadro novo. Se nao saisse, o teste nao protegeria nada.
    """
    from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor

    from editdoc.interface.painel_documento import PainelDocumento

    secao("cache de tiles: depois de editar, o quadro e' o mesmo que sai sem cache")
    texto = chr(10).join(
        f"Linha {i} de texto para a folha, com acentos: ação e órgão, e palavras comuns."
        for i in range(120))

    def _painel():
        painel = PainelDocumento("Segoe UI", 11)
        painel.resize(1000, 1250)
        painel.show()
        drenar_eventos(2)
        painel.setPlainText(texto)
        painel.clearFocus()
        painel.definir_zoom(1.0)
        drenar_eventos(2)
        return painel

    def _ponto(painel, bloco: int, deslocamento: int = 0) -> QTextCursor:
        doc = painel.document()
        cur = QTextCursor(doc)
        cur.setPosition(doc.findBlockByNumber(bloco).position() + deslocamento)
        return cur

    def _edicoes(painel):
        """(rotulo, funcao): uma letra no meio, uma quebra de linha e uma formatacao."""
        def letra():
            painel.setTextCursor(_ponto(painel, 40))
            painel.insertPlainText("abc ")

        def quebra():
            painel.setTextCursor(_ponto(painel, 20, 3))
            painel.insertPlainText(chr(10))

        def negrito():
            cur = _ponto(painel, 10)
            cur.setPosition(cur.position() + 25, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold)
            cur.mergeCharFormat(fmt)
            painel.setTextCursor(cur)

        return [("uma letra no meio", letra), ("quebra de linha", quebra),
                ("negrito numa faixa", negrito)]

    painel = _painel()
    for rotulo, edita in _edicoes(painel):
        painel.viewport().grab()  # aquece o cache com o quadro atual
        edita()
        drenar_eventos(1)
        com_cache = painel.viewport().grab().toImage()
        painel._limpar_cache()
        novo = painel.viewport().grab().toImage()
        checa(com_cache == novo, f"depois de {rotulo}, o quadro com cache e' igual ao quadro novo")
    painel.close()

    # Contraprova: sem invalidar o cache, o quadro antigo e' mostrado e tem de divergir.
    painel = _painel()
    painel.viewport().grab()
    painel._invalidar_faixa = lambda y0, y1: None
    painel.setTextCursor(_ponto(painel, 20, 3))
    painel.viewport().grab()
    painel.insertPlainText(chr(10))
    drenar_eventos(1)
    antigo = painel.viewport().grab().toImage()
    painel._limpar_cache()
    fresco = painel.viewport().grab().toImage()
    checa(antigo != fresco, "contraprova: sem invalidar, o quadro com cache sai diferente do novo")
    painel.close()


def testar_regua_e_folhas_juntas() -> None:
    """A regua e a folha ficam juntas na janela, e a folha continua sem tinta nas margens."""
    from editdoc import configuracao
    from editdoc.interface.janela_principal import JanelaPrincipal
    from editdoc.modelo.folhas import alinhar_ao_dispositivo

    secao("regua e folhas juntas: a janela inteira continua sem tinta nas margens")
    janela = JanelaPrincipal(configuracao.padrao())
    janela.show()
    janela.resize(1000, 1600)
    drenar_eventos(2)
    janela.painel.setPlainText("texto de teste na pagina")
    janela.painel.document().setModified(False)
    drenar_eventos(2)
    img = janela.painel.viewport().grab().toImage()
    k = img.devicePixelRatio()
    m = janela.painel.mapa()
    xl, yl, wl, hl = m.folha_na_tela(0)
    x0 = round(alinhar_ao_dispositivo(xl, k) * k)
    y0 = round(alinhar_ao_dispositivo(yl, k) * k)
    w = round(alinhar_ao_dispositivo(xl + wl, k) * k) - x0
    h = round(alinhar_ao_dispositivo(yl + hl, k) * k) - y0
    cfg = m.pagina
    e = m.escala * k
    margens = (cfg.margem_sup_tw * e, cfg.margem_inf_tw * e, cfg.margem_esq_tw * e, cfg.margem_dir_tw * e)
    checa(y0 >= 0 and y0 + h <= img.height() and x0 >= 0 and x0 + w <= img.width(),
          f"na janela, a folha inteira cabe na captura ({img.width()}x{img.height()})")
    checa_igual(tinta_nas_margens(img, x0, y0, w, h, margens), 0,
                "dentro da janela, a folha continua sem tinta nas margens")
    janela.close()


def main() -> int:
    if not QT:
        return pular("PySide6 nao esta instalado neste venv")
    if not usar_fonte_windows(9):
        return pular("Segoe UI nao esta instalada: sem a fonte, a conta de pixels nao vale")
    secao("folhas: retangulo, margens sem tinta e tinta dentro do corpo")
    for zoom in (1.0, 0.25):
        testar_folhas(zoom)
    testar_cache_igual_ao_quadro_novo()
    testar_regua_e_folhas_juntas()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
