"""Configuracao de pagina: papel, orientacao e margens. Sem Qt e sem lxml.

Tudo em twips (1/1440 de polegada), a unidade do sectPr do .docx (w:pgSz e
w:pgMar). Padrao do EditDoc: A4 em retrato, com as margens Normal do Word
(2,54 cm nos quatro lados).

`paisagem` so' diz como o arquivo marca a orientacao (w:orient="landscape"); a
geometria vem de largura_tw e altura_tw, que ficam como o arquivo as diz.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: 1 cm em twips (1440 twips por polegada, 2,54 cm por polegada).
TWIPS_POR_CM = 1440 / 2.54

#: Papeis conhecidos, em retrato: nome -> (largura, altura) em twips.
PAPEIS: dict[str, tuple[int, int]] = {
    "A4": (11906, 16838),
    "Carta": (12240, 15840),
    "Ofício": (12240, 18720),
}

#: Predefinicoes de margem, na ordem do menu: nome, superior, inferior, esquerda, direita.
MARGENS_PREDEFINIDAS: tuple[tuple[str, int, int, int, int], ...] = (
    ("Normal", 1440, 1440, 1440, 1440),
    ("Estreita", 720, 720, 720, 720),
    ("Moderada", 1440, 1440, 1080, 1080),
    ("Larga", 1440, 1440, 2880, 2880),
)

#: Corpo de texto menor que 2 cm em qualquer lado nao e' pagina util.
CORPO_MINIMO_TW = 1134
#: Maior papel aceito (cada lado): 100000 twips, ou 176 cm. Acima disso e' arquivo hostil:
#: um sectPr com bilhoes de twips faria o layout alocar sem limite.
PAPEL_MAXIMO_TW = 100000
#: Maior margem aceita, em twips (cerca de 35 cm).
MARGEM_MAXIMA_TW = 20000


@dataclass
class Pagina:
    largura_tw: int = 11906
    altura_tw: int = 16838
    margem_sup_tw: int = 1440
    margem_inf_tw: int = 1440
    margem_esq_tw: int = 1440
    margem_dir_tw: int = 1440
    cabecalho_tw: int = 720
    rodape_tw: int = 720
    medianiz_tw: int = 0
    paisagem: bool = False

    def corpo_largura_tw(self) -> int:
        return self.largura_tw - self.margem_esq_tw - self.margem_dir_tw

    def corpo_altura_tw(self) -> int:
        return self.altura_tw - self.margem_sup_tw - self.margem_inf_tw

    def valida(self) -> bool:
        """Medidas positivas e corpo util. O leitor usa isto antes de aceitar o sectPr."""
        medidas = (self.margem_sup_tw, self.margem_inf_tw, self.margem_esq_tw,
                   self.margem_dir_tw, self.cabecalho_tw, self.rodape_tw, self.medianiz_tw)
        return (0 < self.largura_tw <= PAPEL_MAXIMO_TW and 0 < self.altura_tw <= PAPEL_MAXIMO_TW
                and all(0 <= m <= MARGEM_MAXIMA_TW for m in medidas)
                and self.corpo_largura_tw() >= CORPO_MINIMO_TW
                and self.corpo_altura_tw() >= CORPO_MINIMO_TW)

    def nome_do_papel(self) -> str | None:
        """Nome do papel conhecido que casa com o tamanho (em qualquer orientacao), ou None."""
        for nome, (w, h) in PAPEIS.items():
            if (self.largura_tw, self.altura_tw) in ((w, h), (h, w)):
                return nome
        return None

    def nome_das_margens(self) -> str:
        """Nome da predefinicao que casa com as quatro margens, ou 'Personalizadas'."""
        atuais = (self.margem_sup_tw, self.margem_inf_tw, self.margem_esq_tw, self.margem_dir_tw)
        for nome, sup, inf, esq, dir_ in MARGENS_PREDEFINIDAS:
            if atuais == (sup, inf, esq, dir_):
                return nome
        return "Personalizadas"

    def com_papel(self, nome: str) -> "Pagina":
        """Mesmo papel em outro tamanho, mantendo a orientacao."""
        w, h = PAPEIS[nome]
        if self.paisagem:
            w, h = h, w
        return replace(self, largura_tw=w, altura_tw=h)

    def com_orientacao(self, paisagem: bool) -> "Pagina":
        """Troca de retrato para paisagem girando largura e altura; sem troca se ja estiver."""
        if paisagem == self.paisagem:
            return replace(self)
        return replace(self, largura_tw=self.altura_tw, altura_tw=self.largura_tw,
                       paisagem=paisagem)

    def com_margens(self, sup: int, inf: int, esq: int, dir_: int) -> "Pagina":
        return replace(self, margem_sup_tw=sup, margem_inf_tw=inf,
                       margem_esq_tw=esq, margem_dir_tw=dir_)


def pagina_padrao() -> Pagina:
    """A4 em retrato, margens Normal."""
    return Pagina()
