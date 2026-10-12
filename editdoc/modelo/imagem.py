"""Imagens: formato e dimensoes lidos do cabecalho, sem decodificar. Sem Qt.

O leitor do .docx e a insercao de imagem usam isto ANTES de entregar os bytes ao
Qt: uma imagem de 30000 x 30000 px ocuparia 3,6 GB decodificada. A decisao de
mostrar ou nao vem daqui, sem gastar memoria com a imagem.

Formatos aceitos: PNG, JPEG, GIF e BMP (os que o Word grava e que o Qt decodifica
sem plugin extra). Qualquer outro (EMF, WMF, TIFF, SVG...) e' aviso do leitor.
"""

from __future__ import annotations

import struct

#: formato -> (extensao no pacote, tipo de conteudo)
FORMATOS = {
    "png": ("png", "image/png"),
    "jpeg": ("jpeg", "image/jpeg"),
    "gif": ("gif", "image/gif"),
    "bmp": ("bmp", "image/bmp"),
}

#: Maior imagem decodificada para a tela: 64 megapixels (256 MB em ARGB32, o
#: mesmo teto de alocacao do QImageReader). Acima disso a imagem fica no arquivo
#: e aparece como um quadro cinza.
PIXELS_MAXIMOS = 64 * 1000 * 1000
#: Maior lado aceito, em pixels. Um cabecalho com 2^31 px e' arquivo hostil.
LADO_MAXIMO_PX = 30000
#: Maior arquivo de imagem aceito ao inserir (o leitor ja limita cada parte do pacote).
BYTES_MAXIMOS = 64 * 1024 * 1024


def formato_de(dados: bytes) -> str | None:
    """Formato pelo numero magico. None se nao for PNG, JPEG, GIF nem BMP."""
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if dados.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if dados[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if dados[:2] == b"BM" and len(dados) >= 26:
        return "bmp"
    return None


def _jpeg(dados: bytes) -> tuple[int, int] | None:
    """Percorre os segmentos ate o SOF. Cada passo avanca pelo tamanho declarado."""
    i = 2
    n = len(dados)
    while i + 4 <= n:
        if dados[i] != 0xFF:
            return None
        marcador = dados[i + 1]
        if marcador == 0xFF:  # preenchimento
            i += 1
            continue
        if marcador in (0xD8, 0x01) or 0xD0 <= marcador <= 0xD7:
            i += 2
            continue
        (tamanho,) = struct.unpack(">H", dados[i + 2:i + 4])
        if tamanho < 2:
            return None
        if 0xC0 <= marcador <= 0xCF and marcador not in (0xC4, 0xC8, 0xCC):
            if i + 9 > n:
                return None
            altura, largura = struct.unpack(">HH", dados[i + 5:i + 9])
            return largura, altura
        i += 2 + tamanho
    return None


def dimensoes(dados: bytes, formato: str | None = None) -> tuple[int, int] | None:
    """(largura, altura) em pixels, do cabecalho. None se o cabecalho for invalido."""
    formato = formato or formato_de(dados)
    try:
        if formato == "png":
            if dados[12:16] != b"IHDR":
                return None
            return struct.unpack(">II", dados[16:24])
        if formato == "gif":
            return struct.unpack("<HH", dados[6:10])
        if formato == "bmp":
            (tam_cabecalho,) = struct.unpack("<I", dados[14:18])
            if tam_cabecalho == 12:
                largura, altura = struct.unpack("<HH", dados[18:22])
            else:
                largura, altura = struct.unpack("<ii", dados[18:26])
            return abs(largura), abs(altura)
        if formato == "jpeg":
            return _jpeg(dados)
    except struct.error:
        return None
    return None


def decodificavel(largura: int, altura: int) -> bool:
    """True se a imagem cabe no teto de memoria da tela."""
    return (0 < largura <= LADO_MAXIMO_PX and 0 < altura <= LADO_MAXIMO_PX
            and largura * altura <= PIXELS_MAXIMOS)
