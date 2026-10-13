"""Previa de EMF, WMF, TIFF e SVG para a tela, o PDF e a impressao (0.1.5).

O Word grava muitos logotipos e graficos em EMF ou WMF, e alguns documentos trazem TIFF ou
SVG. Ate' a 0.1.4 eles apareciam como um quadro cinza. A previa e' so' para mostrar: os bytes
originais continuam intactos no objeto opaco e voltam iguais ao arquivo.

- TIFF: o plugin `imageformats/qtiff` do Qt (QImageReader), com o mesmo teto de pixels das
  outras imagens.
- SVG: QSvgRenderer (modulo QtSvg do PySide6-Essentials). O arquivo e' recusado antes se tiver
  DOCTYPE/ENTITY ou referencia a algo de fora (href, url() ou @import que nao seja "#..." ou
  "data:"): o documento e' dado, e nada e' lido do disco nem da rede.
- EMF e WMF: GDI do Windows por ctypes, sem dependencia nova. O WMF vira EMF
  (SetWinMetaFileBits); o EMF e' tocado registro a registro (EnumEnhMetaFile com
  PlayEnhMetaFileRecord), e o laco para em REGISTROS_MAXIMOS registros ou em TEMPO_MAXIMO_S
  segundos. O bitmap e' do tamanho que a tela pede (no maximo LADO_MAXIMO_PX no lado maior),
  nunca o que o arquivo declara. Fora do Windows: sem previa (o quadro).

`modelo/imagem.previa_possivel` ja' recusou, na leitura, o que nao passa no cabecalho
(arquivo cortado, registro de tamanho impossivel, dimensoes absurdas). Aqui, qualquer falha
devolve uma QImage nula e quem pinta cai no quadro.
"""

from __future__ import annotations

import re
import sys
import time

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter

from editdoc import log_interno
from editdoc.modelo import imagem as mod_imagem

log = log_interno.obter(__name__)

#: Lado maior do bitmap da previa, em pixels (o mesmo da previa das outras imagens).
LADO_MAXIMO_PX = 1800
#: Menor lado, para nao sumir na tela.
LADO_MINIMO_PX = 16
REGISTROS_MAXIMOS = mod_imagem.REGISTROS_MAXIMOS
TEMPO_MAXIMO_S = 2.0

_SVG_PROIBIDO = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_SVG_REFERENCIA = re.compile(rb"""(?:href\s*=\s*["']|url\(\s*["']?|@import\s+["']?)\s*([^"')\s]*)""",
                             re.IGNORECASE)


def _tamanho_alvo(largura: float, altura: float, lado_max: int) -> tuple[int, int]:
    """Tamanho do bitmap: a proporcao do arquivo, o lado maior em `lado_max`."""
    if largura <= 0 or altura <= 0:
        largura = altura = 1.0
    escala = lado_max / max(largura, altura)
    return (max(LADO_MINIMO_PX, round(largura * escala)), max(LADO_MINIMO_PX, round(altura * escala)))


def _tiff(dados: bytes, lado_max: int) -> QImage:
    buffer = QBuffer()
    buffer.setData(QByteArray(dados))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    leitor = QImageReader(buffer, b"tiff")
    leitor.setAutoTransform(False)
    tamanho = leitor.size()
    if not tamanho.isValid() or not mod_imagem.decodificavel(tamanho.width(), tamanho.height()):
        del leitor
        buffer.close()
        return QImage()
    if max(tamanho.width(), tamanho.height()) > lado_max:
        leitor.setScaledSize(tamanho.scaled(QSize(lado_max, lado_max),
                                            Qt.AspectRatioMode.KeepAspectRatio))
    img = leitor.read()
    # O leitor (o plugin do TIFF fecha o arquivo no destrutor) morre antes do buffer: na ordem
    # inversa o processo cai (medido no Qt 6.11.2).
    del leitor
    buffer.close()
    return img


def svg_seguro(dados: bytes) -> bool:
    """Sem DOCTYPE, sem entidade e sem referencia de fora do proprio arquivo."""
    if _SVG_PROIBIDO.search(dados):
        return False
    for alvo in _SVG_REFERENCIA.findall(dados):
        if alvo and not (alvo.startswith(b"#") or alvo.lower().startswith(b"data:")):
            return False
    return True


def _svg(dados: bytes, lado_max: int, tamanho_doc: tuple | None) -> QImage:
    if not svg_seguro(dados):
        log.warning("SVG com referencia externa ou DOCTYPE: sem previa")
        return QImage()
    from PySide6.QtSvg import QSvgRenderer  # import tardio: so' quem tem SVG paga o modulo
    renderizador = QSvgRenderer(QByteArray(dados))
    if not renderizador.isValid():
        return QImage()
    padrao = renderizador.defaultSize()
    largura, altura = padrao.width(), padrao.height()
    if (largura <= 0 or altura <= 0) and tamanho_doc:
        largura, altura = tamanho_doc
    w, h = _tamanho_alvo(largura, altura, lado_max)
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(img)
    renderizador.render(pintor, QRectF(0, 0, w, h))
    pintor.end()
    return img


# -- GDI (EMF e WMF) -----------------------------------------------------------------------

def _gdi(dados: bytes, formato: str, lado_max: int, tamanho_doc: tuple | None) -> QImage:
    import ctypes
    from ctypes import wintypes

    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    HENH = wintypes.HANDLE

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class METAFILEPICT(ctypes.Structure):
        _fields_ = [("mm", wintypes.LONG), ("xExt", wintypes.LONG), ("yExt", wintypes.LONG),
                    ("hMF", wintypes.HANDLE)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    gdi32.SetEnhMetaFileBits.restype = HENH
    gdi32.SetEnhMetaFileBits.argtypes = [wintypes.UINT, ctypes.c_char_p]
    gdi32.SetWinMetaFileBits.restype = HENH
    gdi32.SetWinMetaFileBits.argtypes = [wintypes.UINT, ctypes.c_char_p, wintypes.HDC,
                                         ctypes.POINTER(METAFILEPICT)]
    gdi32.DeleteEnhMetaFile.argtypes = [HENH]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.GdiFlush.restype = wintypes.BOOL
    PROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HDC, ctypes.c_void_p, ctypes.c_void_p,
                              ctypes.c_int, wintypes.LPARAM)
    gdi32.EnumEnhMetaFile.argtypes = [wintypes.HDC, HENH, PROC, ctypes.c_void_p,
                                      ctypes.POINTER(RECT)]
    gdi32.PlayEnhMetaFileRecord.argtypes = [wintypes.HDC, ctypes.c_void_p, ctypes.c_void_p,
                                            wintypes.UINT]

    import struct
    hemf = None
    largura = altura = 0.0
    if formato == "emf":
        l, t, r, b = struct.unpack("<iiii", dados[24:40])
        largura, altura = (r - l) * 96 / 2540, (b - t) * 96 / 2540
        hemf = gdi32.SetEnhMetaFileBits(len(dados), dados)
    else:
        corpo = dados
        mfp = None
        if dados[:4] == b"\xd7\xcd\xc6\x9a":
            l, t, r, b, polegada = struct.unpack("<hhhhH", dados[6:16])
            largura, altura = abs(r - l) * 96 / polegada, abs(b - t) * 96 / polegada
            corpo = dados[22:]
            mfp = METAFILEPICT(8, round(abs(r - l) * 2540 / polegada),
                               round(abs(b - t) * 2540 / polegada), None)  # MM_ANISOTROPIC
        elif tamanho_doc:
            largura, altura = tamanho_doc
            mfp = METAFILEPICT(8, round(largura * 2540 / 96), round(altura * 2540 / 96), None)
        hemf = gdi32.SetWinMetaFileBits(len(corpo), corpo, None,
                                        ctypes.byref(mfp) if mfp is not None else None)
    if not hemf:
        return QImage()
    if largura <= 0 or altura <= 0:
        largura, altura = tamanho_doc or (1.0, 1.0)
    w, h = _tamanho_alvo(largura, altura, lado_max)
    w = (w + 3) // 4 * 4  # linha da mascara de alfa sem preenchimento
    hdc = gdi32.CreateCompatibleDC(None)
    bits = ctypes.c_void_p()
    cab = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    hbmp = gdi32.CreateDIBSection(hdc, ctypes.byref(cab), 0, ctypes.byref(bits), None, 0)
    if not hdc or not hbmp or not bits.value:
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if hdc:
            gdi32.DeleteDC(hdc)
        gdi32.DeleteEnhMetaFile(hemf)
        return QImage()
    antigo = gdi32.SelectObject(hdc, hbmp)
    contagem = [0]
    limite = time.perf_counter() + TEMPO_MAXIMO_S

    def tocar(hdc_, tabela, registro, n_objetos, _dado):
        contagem[0] += 1
        if contagem[0] > REGISTROS_MAXIMOS or time.perf_counter() > limite:
            return 0  # para o laco: arquivo hostil ou lento demais
        gdi32.PlayEnhMetaFileRecord(hdc_, tabela, registro, n_objetos)
        return 1  # registro que falha nao derruba os outros

    retorno = PROC(tocar)
    retangulo = RECT(0, 0, w, h)
    brutos = []
    try:
        # Duas passadas, sobre branco e sobre preto: a diferenca da' a transparencia (o GDI
        # nao tem canal alfa, e o logotipo branco sobre a faixa colorida sumiria no branco).
        for fundo in (0xFF, 0x00):
            ctypes.memset(bits.value, fundo, w * h * 4)
            gdi32.EnumEnhMetaFile(hdc, hemf, retorno, None, ctypes.byref(retangulo))
            gdi32.GdiFlush()
            brutos.append(ctypes.string_at(bits.value, w * h * 4))
            if contagem[0] > REGISTROS_MAXIMOS or time.perf_counter() > limite:
                break
    finally:
        gdi32.SelectObject(hdc, antigo)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc)
        gdi32.DeleteEnhMetaFile(hemf)
    if contagem[0] > REGISTROS_MAXIMOS or time.perf_counter() > limite or len(brutos) != 2:
        log.warning("metafile parado no limite (%d registros)", contagem[0])
        return QImage()
    return _com_transparencia(brutos[0], brutos[1], w, h)


def _com_transparencia(branco: bytes, preto: bytes, w: int, h: int) -> QImage:
    """Sobre branco: a*C + (1-a)*255; sobre preto: a*C. Logo alfa = 255 - (branco - preto) e
    a cor pre-multiplicada e' a do preto. Tudo em operacoes do Qt e fatias de bytes."""
    # O GDI deixa no quarto byte o que estava no fundo; RGB32 exige 0xFF ali.
    opaco = bytes([0xFF]) * (w * h)
    branco, preto = bytearray(branco), bytearray(preto)
    branco[3::4] = opaco
    preto[3::4] = opaco
    img_b = QImage(bytes(branco), w, h, w * 4, QImage.Format.Format_RGB32).copy()
    img_p = QImage(bytes(preto), w, h, w * 4, QImage.Format.Format_RGB32).copy()
    pintor = QPainter(img_b)
    pintor.setCompositionMode(QPainter.CompositionMode.CompositionMode_Difference)
    pintor.drawImage(0, 0, img_p)
    pintor.end()
    img_b.invertPixels()
    alfa = img_b.convertToFormat(QImage.Format.Format_Grayscale8)
    linha = alfa.bytesPerLine()
    mascara = bytes(alfa.constBits())[:linha * h]
    if linha != w:
        mascara = b"".join(mascara[y * linha:y * linha + w] for y in range(h))
    saida = bytearray(preto)
    saida[3::4] = mascara
    # Pre-multiplicada exige cor <= alfa; o GDI sem suavizacao ja' da' isso, mas um pixel
    # fora da regra so' clareia: a conversao abaixo nao falha.
    img = QImage(bytes(saida), w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied)
    return img.copy()


def renderizar(dados: bytes, formato: str | None = None, lado_max: int = LADO_MAXIMO_PX,
               tamanho_doc: tuple | None = None) -> QImage:
    """Bitmap da previa (lado maior `lado_max`), ou QImage nula se nao der.

    `tamanho_doc`: (largura, altura) em px96 do objeto no documento, para o arquivo sem
    tamanho proprio (WMF sem cabecalho, SVG sem width/height)."""
    formato = formato or mod_imagem.formato_previa(dados)
    if formato is None or mod_imagem.previa_possivel(dados, sys.platform == "win32") != formato:
        return QImage()
    try:
        if formato == "tiff":
            return _tiff(dados, lado_max)
        if formato == "svg":
            return _svg(dados, lado_max, tamanho_doc)
        if formato in ("emf", "wmf"):
            return _gdi(dados, formato, lado_max, tamanho_doc)
    except Exception:  # noqa: BLE001 - previa nunca derruba a janela
        log.exception("previa de %s", formato)
    return QImage()


# -- amostras (autoverificacao e testes) ----------------------------------------------------

def metafile_de_exemplo(formato: str = "emf", fundo: bool = True) -> bytes:
    """Um EMF (ou WMF com cabecalho placeable) pequeno, desenhado pelo GDI agora: um
    retangulo azul (sem ele, com `fundo` falso: transparente) com uma elipse vermelha,
    4 x 2 cm. So' no Windows."""
    import ctypes
    import struct
    from ctypes import wintypes

    gdi32 = ctypes.WinDLL("gdi32")

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    for nome, res, args in (
            ("CreateEnhMetaFileW", wintypes.HDC, [wintypes.HDC, wintypes.LPCWSTR,
                                                  ctypes.POINTER(RECT), wintypes.LPCWSTR]),
            ("CloseEnhMetaFile", wintypes.HANDLE, [wintypes.HDC]),
            ("GetEnhMetaFileBits", wintypes.UINT, [wintypes.HANDLE, wintypes.UINT, ctypes.c_char_p]),
            ("DeleteEnhMetaFile", wintypes.BOOL, [wintypes.HANDLE]),
            ("CreateMetaFileW", wintypes.HDC, [wintypes.LPCWSTR]),
            ("CloseMetaFile", wintypes.HANDLE, [wintypes.HDC]),
            ("GetMetaFileBitsEx", wintypes.UINT, [wintypes.HANDLE, wintypes.UINT, ctypes.c_char_p]),
            ("DeleteMetaFile", wintypes.BOOL, [wintypes.HANDLE]),
            ("CreateSolidBrush", wintypes.HANDLE, [wintypes.DWORD]),
            ("SelectObject", wintypes.HANDLE, [wintypes.HDC, wintypes.HANDLE]),
            ("DeleteObject", wintypes.BOOL, [wintypes.HANDLE]),
            ("Rectangle", wintypes.BOOL, [wintypes.HDC] + [ctypes.c_int] * 4),
            ("Ellipse", wintypes.BOOL, [wintypes.HDC] + [ctypes.c_int] * 4),
            ("SetMapMode", ctypes.c_int, [wintypes.HDC, ctypes.c_int]),
            ("SetWindowExtEx", wintypes.BOOL, [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]),
            ("SetWindowOrgEx", wintypes.BOOL, [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p])):
        f = getattr(gdi32, nome)
        f.restype, f.argtypes = res, args

    def desenhar(hdc, w, h):
        azul = gdi32.CreateSolidBrush(0x00C04000)  # COLORREF 0x00BBGGRR
        vermelho = gdi32.CreateSolidBrush(0x000000E0)
        antigo = gdi32.SelectObject(hdc, azul)
        if fundo:
            gdi32.Rectangle(hdc, 0, 0, w, h)
        gdi32.SelectObject(hdc, vermelho)
        gdi32.Ellipse(hdc, w // 4, h // 4, 3 * w // 4, 3 * h // 4)
        gdi32.SelectObject(hdc, antigo)
        gdi32.DeleteObject(azul)
        gdi32.DeleteObject(vermelho)

    if formato == "emf":
        quadro = RECT(0, 0, 4000, 2000)  # centesimos de mm
        hdc = gdi32.CreateEnhMetaFileW(None, None, ctypes.byref(quadro), None)
        # Desenho em unidades do dispositivo de referencia: 40 x 20 mm nele.
        gdi32.GetDeviceCaps.restype = ctypes.c_int
        gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
        px_mm = gdi32.GetDeviceCaps(hdc, 8) / max(1, gdi32.GetDeviceCaps(hdc, 4))  # HORZRES/HORZSIZE
        py_mm = gdi32.GetDeviceCaps(hdc, 10) / max(1, gdi32.GetDeviceCaps(hdc, 6))  # VERTRES/VERTSIZE
        desenhar(hdc, round(40 * px_mm), round(20 * py_mm))
        hemf = gdi32.CloseEnhMetaFile(hdc)
        n = gdi32.GetEnhMetaFileBits(hemf, 0, None)
        buf = ctypes.create_string_buffer(n)
        gdi32.GetEnhMetaFileBits(hemf, n, buf)
        gdi32.DeleteEnhMetaFile(hemf)
        return buf.raw
    hdc = gdi32.CreateMetaFileW(None)
    gdi32.SetMapMode(hdc, 8)
    gdi32.SetWindowOrgEx(hdc, 0, 0, None)
    gdi32.SetWindowExtEx(hdc, 1512, 756, None)
    desenhar(hdc, 1512, 756)
    hmf = gdi32.CloseMetaFile(hdc)
    n = gdi32.GetMetaFileBitsEx(hmf, 0, None)
    buf = ctypes.create_string_buffer(n)
    gdi32.GetMetaFileBitsEx(hmf, n, buf)
    gdi32.DeleteMetaFile(hmf)
    # Cabecalho placeable: 1512 x 756 unidades a 1440 por polegada = 2,67 x 1,33 cm... (4 x 2 cm
    # a 960 por polegada). Checksum: XOR das 10 primeiras palavras.
    cab = struct.pack("<IHhhhhHI", 0x9AC6CDD7, 0, 0, 0, 1512, 756, 960, 0)
    soma = 0
    for (palavra,) in struct.iter_unpack("<H", cab):
        soma ^= palavra
    return cab + struct.pack("<H", soma) + buf.raw


def cor_dominante(img: QImage) -> QColor:
    """A cor do pixel do meio (para os testes e a autoverificacao conferirem o desenho)."""
    return img.pixelColor(img.width() // 2, img.height() // 2)
