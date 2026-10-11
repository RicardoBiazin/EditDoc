"""Gera os dois .ico do EditWord, sem nenhuma dependencia.

    .venv\\Scripts\\python.exe ferramentas\\gerar_icone.py

Dois icones, porque sao coisas diferentes:

    icone.ico          o APLICATIVO: quadrado arredondado, barra de tarefas e .exe
    icone_arquivo.ico  o TIPO DE ARQUIVO: pagina com canto dobrado, no Explorer

Sem Pillow de proposito: os .ico ficam versionados, e o gerador nao deve exigir
nada alem da biblioteca padrao. Um .ico e' um cabecalho mais DIBs de 32 bits (ou
PNG, a partir de 64 px), e um PNG e' uma sequencia de chunks comprimidos com zlib.

Desenho: fundo ardosia, a mesma familia visual dos outros programas do autor,
com um vinco lateral em verde-agua, que e' a cor propria deste programa. O traco
e' grosso de proposito: a 16 px uma forma de 1 px some, e um vinco fino some num
fundo escuro. A pagina do icone de arquivo e' clara, porque vive no Explorer,
que e' branco.
"""

from __future__ import annotations

import pathlib
import struct
import sys
import zlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent

FUNDO = (0x1E, 0x1F, 0x22)
VINCO = (0x3F, 0xB9, 0x9B)
TEXTO = (0xD6, 0xD8, 0xDC)

PAGINA = (0xE8, 0xEA, 0xED)
TINTA = (0x2B, 0x2D, 0x31)
BORDA = (0x8A, 0x8F, 0x98)

TAMANHOS = (16, 24, 32, 48, 64, 128, 256)

Imagem = list[list[tuple[int, int, int, int]]]


def _vazia(n: int) -> Imagem:
    return [[(0, 0, 0, 0)] * n for _ in range(n)]


def _barra(px: Imagem, n: int, topo: float, altura: float, esquerda: float,
           direita: float, cor: tuple[int, int, int],
           somente_sobre=None) -> None:
    """Retangulo em fracoes do tamanho, pintado so' sobre pixel ja' opaco.

    `somente_sobre` restringe ainda mais: impede uma barra de tinta de invadir
    a borda ou a dobra da pagina.
    """
    y0, y1 = int(topo * n), max(int(topo * n) + 1, int((topo + altura) * n))
    x0, x1 = int(esquerda * n), max(int(esquerda * n) + 1, int(direita * n))
    for y in range(max(0, y0), min(n, y1)):
        for x in range(max(0, x0), min(n, x1)):
            if not px[y][x][3]:
                continue
            if somente_sobre is not None and px[y][x][:3] != somente_sobre:
                continue
            px[y][x] = (*cor, 255)


def desenhar_app(n: int) -> Imagem:
    """O icone do programa: quadrado de cantos arredondados."""
    px = _vazia(n)
    raio = max(1, n // 7)

    def dentro(x: int, y: int) -> bool:
        for cx, cy in ((raio, raio), (n - 1 - raio, raio),
                       (raio, n - 1 - raio), (n - 1 - raio, n - 1 - raio)):
            fora_x = (x < raio and cx == raio) or (x > n - 1 - raio and cx > raio)
            fora_y = (y < raio and cy == raio) or (y > n - 1 - raio and cy > raio)
            if fora_x and fora_y:
                return (x - cx) ** 2 + (y - cy) ** 2 <= raio * raio
        return True

    for y in range(n):
        for x in range(n):
            if dentro(x, y):
                px[y][x] = (*FUNDO, 255)

    # O vinco largo da esquerda separa o icone de um fundo de barra escuro.
    _barra(px, n, 0.12, 0.76, 0.12, 0.32, VINCO)
    # Duas barras grossas, nao tres finas: a 16 px, tres barras viram borrao.
    _barra(px, n, 0.28, 0.14, 0.40, 0.86, TEXTO)
    _barra(px, n, 0.56, 0.14, 0.40, 0.68, TEXTO)
    return px


def desenhar_arquivo(n: int) -> Imagem:
    """O icone do tipo de arquivo: pagina clara com o canto dobrado em verde-agua.

    A dobra e' proporcional e nunca menor que 3 px: a 16 px uma dobra de 1 px
    some, e o icone vira um retangulo parecido com o do programa.
    """
    px = _vazia(n)
    margem = max(1, n // 10)
    dobra = max(3, n // 4)
    esquerda, direita = margem, n - margem
    topo, base = margem, n - margem

    for y in range(topo, base):
        for x in range(esquerda, direita):
            if (direita - x) + (y - topo) <= dobra:
                continue  # o canto cortado
            na_borda = (x in (esquerda, direita - 1)
                        or y in (topo, base - 1)
                        or (direita - x) + (y - topo) == dobra + 1)
            px[y][x] = (*(BORDA if na_borda else PAGINA), 255)

    for y in range(topo, topo + dobra):
        for x in range(direita - dobra, direita):
            if (direita - x) + (y - topo) > dobra and y - topo < dobra:
                px[y][x] = (*VINCO, 255)

    # Tres barras de tinta, so' sobre o miolo da pagina.
    _barra(px, n, 0.40, 0.10, 0.22, 0.74, TINTA, somente_sobre=PAGINA)
    _barra(px, n, 0.58, 0.10, 0.22, 0.60, TINTA, somente_sobre=PAGINA)
    _barra(px, n, 0.76, 0.10, 0.22, 0.70, TINTA, somente_sobre=PAGINA)
    return px


def _chunk(tipo: bytes, dados: bytes) -> bytes:
    return (struct.pack(">I", len(dados)) + tipo + dados
            + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))


def png(px: Imagem) -> bytes:
    altura, largura = len(px), len(px[0])
    bruto = bytearray()
    for linha in px:
        bruto.append(0)  # filtro 0 (None) por linha
        for r, g, b, a in linha:
            bruto += bytes((r, g, b, a))
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", largura, altura,
                                          8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(bytes(bruto), 9))
            + _chunk(b"IEND", b""))


def _dib(px: Imagem) -> bytes:
    """BITMAPINFOHEADER + pixels BGRA + mascara AND.

    Duas armadilhas do formato, e as duas fazem o icone sumir se erradas: a
    altura no cabecalho e' o DOBRO (imagem + mascara), e as linhas vao de BAIXO
    para cima.
    """
    altura, largura = len(px), len(px[0])
    cabecalho = struct.pack("<IiiHHIIiiII", 40, largura, altura * 2, 1, 32, 0,
                            0, 0, 0, 0, 0)
    corpo = bytearray()
    for linha in reversed(px):
        for r, g, b, a in linha:
            corpo += bytes((b, g, r, a))
    bytes_por_linha = ((largura + 31) // 32) * 4
    return bytes(cabecalho) + bytes(corpo) + b"\x00" * (bytes_por_linha * altura)


#: A partir deste tamanho a entrada vai como PNG. Um 256x256 em BGRA tem 256 KB;
#: comprimido, cerca de 1 KB. O Windows aceita PNG dentro do .ico desde o Vista.
TAMANHO_PARA_PNG = 64


def ico(imagens: list[Imagem]) -> bytes:
    entradas = bytearray()
    dados = bytearray()
    deslocamento = 6 + 16 * len(imagens)
    for px in imagens:
        n = len(px)
        bruto = png(px) if n >= TAMANHO_PARA_PNG else _dib(px)
        # 256 e' gravado como 0: o campo de largura/altura tem UM byte so'.
        entradas += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32,
                                len(bruto), deslocamento)
        dados += bruto
        deslocamento += len(bruto)
    return struct.pack("<HHH", 0, 1, len(imagens)) + bytes(entradas) + bytes(dados)


def main() -> int:
    pasta = RAIZ / "editword" / "recursos"
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, desenho in (("icone.ico", desenhar_app),
                          ("icone_arquivo.ico", desenhar_arquivo)):
        destino = pasta / nome
        destino.write_bytes(ico([desenho(n) for n in TAMANHOS]))
        print(f"{destino}  ({destino.stat().st_size} bytes, "
              f"{len(TAMANHOS)} tamanhos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
