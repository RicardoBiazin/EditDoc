"""O texto de um bloco do QTextDocument, repartido em trechos para o corretor (0.1.35).

Cada trecho e' um pedaco do bloco que o corretor verifica de uma vez: o mesmo idioma e a mesma
decisao de verificar. O idioma de cada pedaco, do mais forte para o mais fraco:

1. o idioma escolhido em Arquivo > Opcoes (quando nao e' "automatico"): vale para tudo;
2. o w:lang do proprio trecho (rPr nos extras, `PROP_RPR_EXTRA`);
3. o w:lang do estilo de caractere e, depois, do estilo de paragrafo (e das bases deles);
4. o w:lang do docDefaults do arquivo;
5. pt-BR.

Nao se verifica: o trecho com w:noProof (no run ou no estilo), o texto excluido por uma
alteracao controlada, e o que nao e' texto. Marcas sem largura (marcador, ancora de comentario,
inicio e fim de campo) saem do texto verificado sem partir a palavra; objeto com largura
(imagem, nota, campo simples) vira espaco. O mapa leva cada posicao do texto verificado de volta
a' posicao no bloco, para o sublinhado cair no lugar certo.

So' le o documento: nada daqui altera formato, texto ou desfazer.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QTextBlock

from editdoc.formato_docx.idioma_texto import IdiomasDeEstilos, idioma_do_run
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import marcas as pq_marcas
from editdoc.ponte_qt import propriedades as pq_props
from editdoc.ponte_qt import revisoes as pq_revisoes

#: Maior bloco verificado (caracteres): um paragrafo gigante (arquivo colado inteiro) nao trava a
#: tela, e o corretor nao e' feito para isso.
BLOCO_MAXIMO = 30000
_SEM_LARGURA = ""
_QUEBRA_DE_LINHA = " "
_OBJETO = "￼"


@dataclass
class Contexto:
    """O que decide o idioma de um trecho sem w:lang proprio."""
    forcado: str | None = None
    padrao: str = "pt-BR"
    estilos: IdiomasDeEstilos | None = None


@dataclass(frozen=True)
class Trecho:
    texto: str
    idioma: str
    #: Posicao no bloco de cada caractere do texto (None = contigua, a partir de `ini`).
    mapa: tuple | None
    ini: int

    def no_bloco(self, i: int) -> int:
        """Posicao no bloco do caractere `i` do texto verificado."""
        if self.mapa is None:
            return self.ini + i
        return self.mapa[min(max(i, 0), len(self.mapa) - 1)]

    def intervalo_no_bloco(self, a: int, b: int) -> tuple[int, int]:
        """[a, b) do texto verificado -> [ini, fim) no bloco."""
        return self.no_bloco(a), self.no_bloco(b - 1) + 1


def _chave_do_fragmento(cf, sid_par: str | None, ctx: Contexto) -> tuple[str, bool]:
    """(idioma, verificar) do trecho."""
    if pq_revisoes.exclusao_de(cf) is not None:
        return ctx.forcado or ctx.padrao, False
    li, sem = idioma_do_run(pq_props.extras_de_rpr(cf))
    ie = se = None
    if ctx.estilos is not None:
        ie, se = ctx.estilos.do_texto(sid_par, pq_estilos.estilo_do_caractere(cf))
    idioma = ctx.forcado or li or ie or ctx.padrao
    if sem is None:
        sem = se
    return idioma, not sem


def trechos_do_bloco(bloco: QTextBlock, ctx: Contexto) -> list[Trecho]:
    """Os trechos verificaveis do bloco (lista vazia se nao ha' texto)."""
    sid_par = pq_estilos.estilo_do_bloco(bloco.blockFormat()) or None
    inicio = bloco.position()
    saida: list[Trecho] = []
    chave = None
    partes: list[tuple[int, str]] = []

    def fechar() -> None:
        nonlocal partes
        if chave is not None and chave[1] and partes:
            texto = "".join(t for _o, t in partes)
            contigua = all(partes[k][0] + len(partes[k][1]) == partes[k + 1][0]
                           for k in range(len(partes) - 1))
            if contigua:
                mapa = None
            else:
                mapa = tuple(o + i for o, t in partes for i in range(len(t)))
            if texto.strip():
                saida.append(Trecho(texto, chave[0], mapa, partes[0][0]))
        partes = []

    total = 0
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        it += 1
        if not frag.isValid():
            continue
        cf = frag.charFormat()
        if pq_marcas.eh_marca(cf):
            continue  # sem largura: o texto dos dois lados continua uma palavra so'
        texto = frag.text()
        total += len(texto)
        if total > BLOCO_MAXIMO:
            return []
        objeto = cf.objectType() != 0
        if objeto or _OBJETO in texto or _QUEBRA_DE_LINHA in texto:
            texto = texto.replace(_OBJETO, " ").replace(_QUEBRA_DE_LINHA, " ")
        nova = _chave_do_fragmento(cf, sid_par, ctx)
        if nova != chave:
            fechar()
            chave = nova
        partes.append((frag.position() - inicio, texto))
    fechar()
    return saida
