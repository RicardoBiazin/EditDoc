"""Pintura so' da parte velha dos tiles (0.1.15), igual a' tela refeita do zero.

Desde a 0.1.15 a tecla nao tira mais do cache os tiles inteiros que a linha digitada cruza: o
tile fica, a parte da linha e' anotada (`VistaPaginas._sujos`) e a pintura seguinte refaz so' ela,
com a mesma transformacao do tile (`VistaPaginas._repintar_partes`). Aqui:

- a tecla na celula e no item de lista do plano nao pinta tile inteiro (contraprova: sem as
  partes, 2 tiles inteiros por tecla);
- a tela com as partes e' igual a' refeita do zero, pixel a pixel, num zoom que nao da' pixel
  inteiro por twip (137%), na celula e no item de lista (o Backspace que tira o item vazio da
  lista renumera os de baixo: `_conferir_rotulos`), com entrelinha exata menor que a letra e na
  linha do sumario que desce de pagina dentro do bloco (`_extensao`); cada caso com contraprova.

Suite propria (e nao em `teste_desempenho`): as sequencias com a tela inteira conferida levam
quase um minuto, e a outra ja' chega perto do teto de 180 s por suite do `rodar_todos`.
"""

from __future__ import annotations

from ajudantes import checa, checa_igual, drenar_eventos, resumir, secao
# teste_desempenho prepara o Qt (preparar_qt) e traz as fixtures e os ajudantes de tecla.
from teste_desempenho import (_fechar, _ir, _painel, _ponto, _sequencia_confere, _tecla,  # noqa
                              documento_plano, manual_sintetico, tf)


# -- --------------------------------------------------

def _tiles_inteiros_e_partes(painel, pos: int, teclas: int = 8) -> tuple[float, float]:
    """(tiles pintados do zero, grupos de partes refeitas) por tecla."""
    from editdoc.interface import vista_paginas as vp
    _ir(painel, pos)
    _tecla(painel)
    painel.viewport().grab()
    inteiros, partes = [0], [0]
    original_tile, original_partes = vp.VistaPaginas._tile, vp.VistaPaginas._repintar_partes

    def tile(self, n, i, j, dpr, m):
        if (n, i, j, self._zoom, dpr) not in self._cache:
            inteiros[0] += 1
        return original_tile(self, n, i, j, dpr, m)

    def repintar(self, itens, n, dpr, m):
        partes[0] += 1
        return original_partes(self, itens, n, dpr, m)

    vp.VistaPaginas._tile, vp.VistaPaginas._repintar_partes = tile, repintar
    try:
        for _ in range(teclas):
            _tecla(painel)
            painel.viewport().grab()
    finally:
        vp.VistaPaginas._tile, vp.VistaPaginas._repintar_partes = original_tile, original_partes
    for _ in range(teclas + 1):
        painel.undo()
    painel.viewport().grab()
    return inteiros[0] / teclas, partes[0] / teclas


def testar_partes_dos_tiles() -> None:
    secao("0.1.15: a tecla refaz so' a parte velha dos tiles (a linha), igual a' tela refeita")
    from PySide6.QtCore import Qt
    from editdoc.interface import vista_paginas as vp
    K = Qt.Key
    V = vp.VistaPaginas
    painel = _painel(documento_plano())
    try:
        celula = _ponto(painel, "plano_celula")
        item = _ponto(painel, "plano_item")
        for nome, pos in (("celula", celula), ("item de lista", item)):
            inteiros, partes = _tiles_inteiros_e_partes(painel, pos)
            checa(inteiros == 0 and 0 < partes <= 2.0,
                  f"{nome}: {inteiros:.1f} tiles pintados do zero e {partes:.1f} pinturas de "
                  "partes por tecla (a 0.1.14 pintava 2 a 8 tiles inteiros)")
        # Contraprova: sem guardar as partes, os tiles saem inteiros do cache.
        original = V.FRACAO_PARCIAL
        V.FRACAO_PARCIAL = 0.0
        try:
            inteiros, partes = _tiles_inteiros_e_partes(painel, celula)
        finally:
            V.FRACAO_PARCIAL = original
        checa(inteiros >= 1.0 and partes == 0,
              f"contraprova: sem as partes, {inteiros:.1f} tiles inteiros por tecla")
        teclas = ([K.Key_A] * 4 + [K.Key_Space] + [K.Key_B] * 40 + [K.Key_Backspace] * 8
                  + [K.Key_Return] + [K.Key_C] * 2 + [K.Key_Backspace] * 3)
        # Zoom que nao da' pixel inteiro por twip nem por tile (a parte e' arredondada no pixel).
        zoom = painel._zoom
        painel.definir_zoom(1.37)
        try:
            ruins = _sequencia_confere(painel, celula, teclas)
            checa_igual(ruins, 0, f"celula a 137%: {len(teclas)} teclas sem nada velho na tela")
            ruins = _sequencia_confere(painel, item, teclas)
            checa_igual(ruins, 0, f"item de lista a 137%: {len(teclas)} teclas iguais a' tela "
                                  "refeita")
            # Contraprova (0.1.17): a linha que quebra no item desce os itens de baixo ate' a
            # quebra das regras do Word (viuvas e orfas) que segura o resto: a altura do documento
            # nao muda, e sem conferir o bloco de baixo eles ficavam velhos na tela.
            original_moveu = V._seguinte_moveu
            V._seguinte_moveu = lambda self, *a: False
            try:
                sabotado = _sequencia_confere(painel, item, teclas)
            finally:
                V._seguinte_moveu = original_moveu
            checa(sabotado > 0, f"contraprova: sem conferir o bloco de baixo, {sabotado} teclas "
                                "deixam itens velhos na tela")
            # Contraprova: o Backspace que tira o item vazio da lista renumera os de baixo sem
            # mudar altura; quem pede o rotulo do cursor recalcula antes da pintura.
            # 0.1.17: com a compensacao do layout do Word ligada, sair da lista refaz o formato do
            # bloco (o espaco somado volta no ajuste) e a pintura limpa o cache inteiro, o que
            # esconderia o numero velho; a contraprova mede a conferencia dos rotulos sozinha.
            original_rotulos = V._conferir_rotulos
            V._conferir_rotulos = lambda self, numerador: None
            paginacao = painel.layout_pag.paginacao
            paginacao.ligado = False
            try:
                painel.viewport().grab()
                sabotado = _sequencia_confere(painel, item, teclas)
            finally:
                V._conferir_rotulos = original_rotulos
                paginacao.ligado = True
                painel.viewport().grab()
            checa(sabotado > 0, f"contraprova: sem conferir os numeros da pintura anterior, "
                                f"{sabotado} teclas deixam numero velho na tela")
        finally:
            painel.definir_zoom(zoom)
        # Contraprova: a parte pintada um pixel ao lado do lugar dela.
        original_partes = V._repintar_partes
        original_transf = V.__dict__["_transformacao_do_tile"]

        def deslocada(self, itens, n, dpr, m):
            V._transformacao_do_tile = staticmethod(
                lambda i, j, e, dx=0.0, dy=0.0: original_transf.__func__(i, j, e, dx + 1.0, dy))
            try:
                return original_partes(self, itens, n, dpr, m)
            finally:
                V._transformacao_do_tile = original_transf

        V._repintar_partes = deslocada
        try:
            sabotado = _sequencia_confere(painel, celula, teclas[:6])
        finally:
            V._repintar_partes = original_partes
        checa(sabotado > 0, f"contraprova: a parte um pixel ao lado, {sabotado} teclas deixam a "
                            "tela diferente")
    finally:
        _fechar(painel)
        painel.deleteLater()
        drenar_eventos()
    # Entrelinha exata menor que a letra (16 pt em 9 pt): a tinta passa da caixa da linha, e a
    # das linhas vizinhas entra na parte refeita.
    texto = "Linha com entrelinha exata menor que a letra, acentuação ÁÉÍ e descendentes gjpq. "
    corpo = "".join('<w:p><w:pPr><w:spacing w:line="180" w:lineRule="exact"/></w:pPr><w:r><w:rPr>'
                    f'<w:sz w:val="32"/></w:rPr><w:t>{i} {texto * 3}</w:t></w:r></w:p>'
                    for i in range(30))
    painel = _painel(tf.doc_do_corpo(corpo))
    try:
        doc = painel.documento_corpo()
        pos = doc.findBlockByNumber(12).position() + 30
        teclas = [K.Key_A] * 6 + [K.Key_Space] + [K.Key_B] * 30 + [K.Key_Backspace] * 6
        ruins = _sequencia_confere(painel, pos, teclas)
        checa_igual(ruins, 0, f"entrelinha exata menor que a letra: {len(teclas)} teclas iguais "
                              "a' tela refeita")
        folgas = V.FOLGA_VERTICAL_TW, V.FOLGA_DE_CORTE_TW
        V.FOLGA_VERTICAL_TW = V.FOLGA_DE_CORTE_TW = 0.0
        try:
            sabotado = _sequencia_confere(painel, pos, teclas)
        finally:
            V.FOLGA_VERTICAL_TW, V.FOLGA_DE_CORTE_TW = folgas
        checa(sabotado > 0, f"contraprova: sem as folgas, {sabotado} teclas deixam tinta velha "
                            "ou cortada")
    finally:
        _fechar(painel)
        painel.deleteLater()
        drenar_eventos()
    # A linha que desce de pagina com um deslocamento dentro do bloco (o sumario do manual, no
    # topo da pagina 2): o retangulo do bloco nao a cobre, e a parte refeita tem de cobrir.
    painel = _painel(manual_sintetico())
    try:
        teclas = [K.Key_A] * 6
        ruins = _sequencia_confere(painel, _ponto(painel, "sumario"), teclas)
        checa_igual(ruins, 0, "linha do sumario que desceu de pagina: igual a' tela refeita")
        # Cada metade sozinha basta aqui: a folga vertical da parte e a extensao do bloco pelas
        # linhas. Sem a folga, a extensao cobre; sem as duas, a linha fica velha.
        original, folga = V._extensao, V.FOLGA_VERTICAL_TW

        def so_o_retangulo(self, bloco):
            r = self.layout_pag.doc.documentLayout().blockBoundingRect(bloco)
            return r.top(), r.bottom()

        V.FOLGA_VERTICAL_TW = 0.0
        try:
            sem_folga = _sequencia_confere(painel, _ponto(painel, "sumario"), teclas)
            V._extensao = so_o_retangulo
            sabotado = _sequencia_confere(painel, _ponto(painel, "sumario"), teclas)
        finally:
            V._extensao, V.FOLGA_VERTICAL_TW = original, folga
        checa_igual(sem_folga, 0, "sem a folga vertical, a extensao do bloco pelas linhas cobre")
        checa(sabotado > 0, f"contraprova: sem a folga e pelo retangulo do bloco, {sabotado} "
                            "teclas deixam a linha velha na tela")
    finally:
        _fechar(painel)
        painel.deleteLater()
        drenar_eventos()


def main() -> int:
    from ajudantes import usar_fonte_windows, usar_fontes_do_documento
    usar_fonte_windows()
    usar_fontes_do_documento()
    testar_partes_dos_tiles()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
