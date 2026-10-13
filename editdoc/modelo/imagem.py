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


# -- formatos que a tela so' mostra como previa (0.1.5) ---------------------------------------
#
# EMF, WMF, TIFF e SVG nao viram `Imagem` (o EditDoc nao os grava nem os redimensiona): ficam
# no objeto opaco, com os bytes intactos, e a tela mostra uma previa renderizada
# (`ponte_qt/vetoriais.py`). Aqui so' o que da' para decidir sem Qt: o formato pelo numero
# magico, o tamanho pelo cabecalho e se a estrutura dos registros fecha. Arquivo que nao
# passa (cortado, registro com tamanho impossivel, dimensoes absurdas, grande demais) nao
# tem previa: vira o quadro, com o aviso IMAGEM_FORMATO.

#: Formatos de previa.
FORMATOS_PREVIA = ("emf", "wmf", "tiff", "svg")
#: Maior arquivo vetorial ou TIFF que a tela renderiza.
BYTES_PREVIA_MAXIMOS = 16 * 1024 * 1024
#: Mais registros que isto num metafile e' arquivo hostil (o Word gera dezenas de milhares).
REGISTROS_MAXIMOS = 1_000_000
_EMR_HEADER, _EMR_EOF = 1, 14


def formato_previa(dados: bytes) -> str | None:
    """emf, wmf, tiff ou svg pelo inicio do arquivo. None se nao for nenhum deles."""
    if len(dados) >= 88 and dados[:4] == b"\x01\x00\x00\x00" and dados[40:44] == b" EMF":
        return "emf"
    if dados[:4] == b"\xd7\xcd\xc6\x9a":
        return "wmf"  # com o cabecalho "placeable" (Aldus)
    if len(dados) >= 18 and dados[:2] in (b"\x01\x00", b"\x02\x00") and dados[2:4] == b"\x09\x00" \
            and dados[4:6] in (b"\x00\x03", b"\x00\x01"):
        return "wmf"
    if dados[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    inicio = dados[:4096].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if (inicio.startswith(b"<?xml") or inicio.startswith(b"<svg") or inicio.startswith(b"<!--")) \
            and b"<svg" in inicio:
        return "svg"
    return None


def _emf(dados: bytes) -> tuple[int, int] | None:
    """Tamanho do EMF em px a 96 dpi, do rclFrame (centesimos de mm), se os registros fecham."""
    tipo, tamanho = struct.unpack("<II", dados[:8])
    l, t, r, b = struct.unpack("<iiii", dados[24:40])
    (n_bytes,) = struct.unpack("<I", dados[48:52])
    if tipo != _EMR_HEADER or tamanho < 88 or n_bytes > len(dados) or n_bytes < tamanho:
        return None
    i, n = 0, 0
    while i + 8 <= n_bytes:
        tipo, tamanho = struct.unpack("<II", dados[i:i + 8])
        if tamanho < 8 or tamanho % 4 or i + tamanho > n_bytes:
            return None
        n += 1
        if n > REGISTROS_MAXIMOS:
            return None
        if tipo == _EMR_EOF:
            break
        i += tamanho
    else:
        return None  # sem EMR_EOF: arquivo cortado
    largura = round((r - l) * 96 / 2540)
    altura = round((b - t) * 96 / 2540)
    return largura, altura


def _wmf(dados: bytes) -> tuple[int, int] | None:
    """Tamanho do WMF em px a 96 dpi (do cabecalho placeable; sem ele, (0, 0): o tamanho vem
    do documento), se os registros fecham."""
    largura = altura = 0
    if dados[:4] == b"\xd7\xcd\xc6\x9a":
        l, t, r, b, polegada = struct.unpack("<hhhhH", dados[6:16])
        if polegada <= 0:
            return None
        largura = round(abs(r - l) * 96 / polegada)
        altura = round(abs(b - t) * 96 / polegada)
        dados = dados[22:]
    tipo, cab, _versao, (total,) = dados[0:2], dados[2:4], dados[4:6], struct.unpack("<I", dados[6:10])
    if tipo not in (b"\x01\x00", b"\x02\x00") or cab != b"\x09\x00" or total * 2 > len(dados):
        return None
    i, n = 18, 0
    fim = total * 2
    while i + 6 <= fim:
        (palavras,) = struct.unpack("<I", dados[i:i + 4])
        (funcao,) = struct.unpack("<H", dados[i + 4:i + 6])
        if palavras < 3 or i + palavras * 2 > fim:
            return None
        n += 1
        if n > REGISTROS_MAXIMOS:
            return None
        if funcao == 0:
            break
        i += palavras * 2
    else:
        return None
    return largura, altura


def _tiff(dados: bytes) -> tuple[int, int] | None:
    """Largura e altura do primeiro IFD do TIFF."""
    fim = "<" if dados[:2] == b"II" else ">"
    (ifd,) = struct.unpack(fim + "I", dados[4:8])
    if ifd < 8 or ifd + 2 > len(dados):
        return None
    (n,) = struct.unpack(fim + "H", dados[ifd:ifd + 2])
    largura = altura = None
    for k in range(min(n, 4096)):
        e = ifd + 2 + k * 12
        if e + 12 > len(dados):
            return None
        tag, tipo, _conta = struct.unpack(fim + "HHI", dados[e:e + 8])
        if tag not in (256, 257):
            continue
        valor = struct.unpack(fim + ("H" if tipo == 3 else "I"), dados[e + 8:e + (10 if tipo == 3 else 12)])[0]
        if tag == 256:
            largura = valor
        else:
            altura = valor
    if largura is None or altura is None:
        return None
    return largura, altura


def dimensoes_previa(dados: bytes, formato: str) -> tuple[int, int] | None:
    """(largura, altura) em px a 96 dpi, se o arquivo passa nas conferencias. (0, 0) = sem
    tamanho proprio (WMF sem cabecalho, SVG sem width/height): vale o do documento."""
    if len(dados) > BYTES_PREVIA_MAXIMOS:
        return None
    try:
        if formato == "emf":
            return _emf(dados)
        if formato == "wmf":
            return _wmf(dados)
        if formato == "tiff":
            return _tiff(dados)
        if formato == "svg":
            return (0, 0)
    except (struct.error, IndexError):
        return None
    return None


def previa_possivel(dados: bytes, plataforma_windows: bool) -> str | None:
    """O formato de previa, se a tela consegue mostrar este arquivo; None se nao (o quadro).

    EMF e WMF so' no Windows (GDI). Dimensoes acima do teto da tela: None (arquivo hostil ou
    pôster enorme, que nao se renderiza)."""
    formato = formato_previa(dados)
    if formato is None:
        return None
    if formato in ("emf", "wmf") and not plataforma_windows:
        return None
    dims = dimensoes_previa(dados, formato)
    if dims is None:
        return None
    largura, altura = dims
    if (largura, altura) != (0, 0) and not decodificavel(largura, altura):
        return None
    return formato
