"""Regras puras do modelo: contagem de palavras, unidades. Sem Qt."""

from __future__ import annotations

from ajudantes import checa, checa_igual, resumir, secao
from editdoc.modelo.estatisticas import contar
from editdoc.modelo.unidades import RECUO_PADRAO_PX, px_de_twips, twips_de_px


def testar_contagem() -> None:
    secao("contagem de palavras e caracteres")
    vazio = contar("")
    checa_igual((vazio.palavras, vazio.caracteres), (0, 0), "texto vazio conta zero")

    c = contar("um dois  tres\n\nquatro")
    checa_igual(c.palavras, 4, "espacos repetidos e quebras separam palavras")
    checa_igual(c.caracteres, len("um dois  tres\n\nquatro") - 2,
                "quebras de linha nao entram em caracteres")

    qt = contar("Olá mundo Segundo linha")
    checa_igual(qt.palavras, 4, "U+2029 e U+2028 do Qt contam como separador")
    checa_igual(qt.caracteres, len("Olá mundo Segundo linha") - 2,
                "U+2029 e U+2028 nao entram em caracteres")

    sem = contar("a b\tc")
    checa_igual(sem.caracteres_sem_espacos, 3, "caracteres sem espacos ignora tab e espaco")

    # Contraprova: a contagem tem de mudar quando o texto muda.
    checa(contar("um dois").palavras != contar("um dois tres").palavras,
          "contagem muda quando o texto muda (nao e' constante)")


def testar_unidades() -> None:
    secao("unidades: twips, px a 96 dpi e o recuo padrao")
    checa_igual(px_de_twips(1440), 96.0, "1440 twips = 1 polegada = 96 px")
    checa_igual(twips_de_px(96), 1440, "96 px = 1440 twips")
    checa_igual(twips_de_px(RECUO_PADRAO_PX), 720,
                "o recuo padrao e' 0,5 polegada, ou 720 twips")
    checa_igual(twips_de_px(px_de_twips(1417)), 1417,
                "ida e volta px/twips e' exata nos valores de margem")


def main() -> int:
    testar_contagem()
    testar_unidades()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
