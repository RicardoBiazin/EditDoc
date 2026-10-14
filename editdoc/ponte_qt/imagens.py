"""Imagens no QTextDocument: registro dos bytes originais e a previa para a tela.

O Qt guarda a imagem como recurso do documento (`addResource`) e, depois de
desenhar, troca o recurso pela imagem decodificada. Por isso os bytes originais
NAO ficam no Qt: ficam aqui, num registro por conteudo (sha256), e o nome do
recurso (`editdoc-img:<hash>.<ext>`) e' a chave. Salvar le os bytes daqui, sem
recodificar: a imagem sai do .docx igual entrou.

A tela recebe uma previa: no maximo LADO_PREVIA_PX no lado maior (o bastante
para o zoom maximo numa pagina A4), e um quadro cinza para imagem acima do teto
de pixels (modelo/imagem.py). Uma foto de 48 megapixels nao ocupa 190 MB so'
para aparecer com 16 cm na pagina.

Recorte (0.1.5, a:srcRect): a imagem recortada usa outro nome de recurso, o do registro com
"#recorte=l,t,r,b" no fim. A previa desse nome e' a previa recortada; os bytes continuam os
mesmos (o nome sem o sufixo acha o registro). O recorte volta do nome, inclusive no HTML colado.

`DocumentoQt` e' o QTextDocument do editor: quando falta o recurso (imagem colada
de outra janela, ou depois de desfazer), ele o busca no registro.
"""

from __future__ import annotations

import hashlib
import itertools

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPen, QTextDocument, QTextImageFormat

from editdoc.modelo import imagem as mod_imagem

ESQUEMA = "editdoc-img"
#: Lado maior da previa, em pixels. A 300% de zoom uma imagem de 16 cm tem ~1800 px.
LADO_PREVIA_PX = 1800

#: nome do recurso -> (bytes originais, formato)
_REGISTRO: dict[str, tuple[bytes, str]] = {}


def nome_de(dados: bytes, formato: str) -> str:
    extensao = mod_imagem.FORMATOS[formato][0]
    return f"{ESQUEMA}:{hashlib.sha256(dados).hexdigest()[:40]}.{extensao}"


def registrar(dados: bytes, formato: str) -> str:
    """Guarda os bytes e devolve o nome do recurso. Mesmo conteudo, mesmo nome."""
    nome = nome_de(dados, formato)
    _REGISTRO.setdefault(nome, (bytes(dados), formato))
    return nome


_SUFIXO_RECORTE = "#recorte="


def nome_recortado(nome: str, recorte) -> str:
    """O nome do recurso da imagem com o recorte (0.1.5). Sem recorte, o proprio nome."""
    if not recorte or not any(recorte):
        return nome
    return nome + _SUFIXO_RECORTE + ",".join(str(int(v)) for v in recorte)


def separar_recorte(nome: str) -> tuple[str, tuple | None]:
    """(nome do registro, recorte) de um nome de recurso."""
    base, sep, resto = nome.partition(_SUFIXO_RECORTE)
    if not sep:
        return nome, None
    try:
        valores = tuple(int(x) for x in resto.split(","))
    except ValueError:
        return base, None
    if len(valores) != 4 or not all(-1000000 <= v <= 100000 for v in valores):
        return base, None
    return base, valores


def recortar(img: QImage, recorte) -> QImage:
    """A previa com o recorte aplicado. Recorte negativo (margem a mais) ou que nao deixa
    nada: a imagem inteira."""
    if not recorte or img.isNull():
        return img
    l, t, r, b = (max(0, v) for v in recorte)
    if l + r >= 100000 or t + b >= 100000:
        return img
    w, h = img.width(), img.height()
    x0, y0 = round(w * l / 100000), round(h * t / 100000)
    largura = max(1, round(w * (100000 - l - r) / 100000))
    altura = max(1, round(h * (100000 - t - b) / 100000))
    return img.copy(x0, y0, min(largura, w - x0), min(altura, h - y0))


def dados_de(nome: str) -> tuple[bytes, str] | None:
    return _REGISTRO.get(separar_recorte(nome)[0])


def eh_nosso(nome: str) -> bool:
    return nome.startswith(ESQUEMA + ":")


def quadro_cinza(largura: int = 64, altura: int = 64) -> QImage:
    """O que aparece no lugar de imagem que nao pode ser decodificada."""
    img = QImage(largura, altura, QImage.Format.Format_RGB32)
    img.fill(QColor(0xD0, 0xD3, 0xD8))
    pintor = QPainter(img)
    pintor.setPen(QPen(QColor(0x80, 0x86, 0x90), 2))
    pintor.drawRect(1, 1, largura - 3, altura - 3)
    pintor.drawLine(0, 0, largura, altura)
    pintor.drawLine(largura, 0, 0, altura)
    pintor.end()
    return img


def previa(dados: bytes) -> QImage:
    """Imagem para a tela: reduzida ao LADO_PREVIA_PX, ou o quadro cinza."""
    dims = mod_imagem.dimensoes(dados)
    if dims is None or not mod_imagem.decodificavel(*dims):
        return quadro_cinza()
    buffer = QBuffer()
    buffer.setData(QByteArray(dados))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    leitor = QImageReader(buffer)
    leitor.setAutoTransform(False)  # o Word nao gira pela orientacao EXIF
    tamanho = leitor.size()
    if tamanho.isValid() and max(tamanho.width(), tamanho.height()) > LADO_PREVIA_PX:
        leitor.setScaledSize(tamanho.scaled(QSize(LADO_PREVIA_PX, LADO_PREVIA_PX),
                                            Qt.AspectRatioMode.KeepAspectRatio))
    img = leitor.read()
    buffer.close()
    return img if not img.isNull() else quadro_cinza()


def adicionar_recurso(doc: QTextDocument, nome: str) -> bool:
    """Poe a previa da imagem `nome` como recurso de `doc`. False se o nome nao e' conhecido."""
    base, recorte = separar_recorte(nome)
    registro = _REGISTRO.get(base)
    if registro is None:
        return False
    doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(nome),
                    recortar(previa(registro[0]), recorte))
    return True


def formato_de_imagem(nome: str, largura_px: float, altura_px: float,
                      descricao: str = "") -> QTextImageFormat:
    fmt = QTextImageFormat()
    fmt.setName(nome)
    fmt.setWidth(float(largura_px))
    fmt.setHeight(float(altura_px))
    if descricao:
        fmt.setToolTip(descricao)
    return fmt


def png_de(img: QImage) -> bytes:
    """Bytes PNG de uma QImage (imagem colada da area de transferencia)."""
    dados = QByteArray()
    buffer = QBuffer(dados)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buffer, "PNG")
    buffer.close()
    return bytes(dados.data())


_SERIE_DOCUMENTOS = itertools.count(1)


class DocumentoQt(QTextDocument):
    """QTextDocument que acha no registro a imagem que nao esta' nos seus recursos.

    Tambem registra o manipulador dos objetos opacos (0.1.2), que pinta o marcador da
    caixa de texto, da forma ou do grafico preservado, e o das marcas de campo e de
    marcador (0.1.3).
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        from editdoc.ponte_qt import marcas, opacos  # import tardio: opacos usa a previa daqui
        self._manipulador_opacos = opacos.registrar_manipulador(self)
        # Marcas de campo e de marcador (0.1.3).
        self._manipulador_marcas = marcas.registrar_manipulador(self)
        self._chave_fonte: str | None = None
        #: Numero de serie (0.1.8): chave de cache que nao confia em id() (reusado pelo coletor).
        self.serie = next(_SERIE_DOCUMENTOS)

    def setDefaultFont(self, fonte) -> None:  # noqa: N802 - nome do Qt
        super().setDefaultFont(fonte)
        self._chave_fonte = None

    def chave_da_fonte(self) -> str:
        """`defaultFont().key()` guardada (0.1.8): o tamanho das marcas e' pedido centenas de
        vezes por tecla, e montar a QFont padrao a cada pedido pesava na pintura."""
        if self._chave_fonte is None:
            self._chave_fonte = self.defaultFont().key()
        return self._chave_fonte

    def loadResource(self, tipo, url):  # noqa: N802 - nome do Qt
        """Recurso que falta: so' as imagens do registro. Nada vem de arquivo nem de rede.

        O QTextDocument padrao le um "file:" de um HTML colado (imagem ou folha de estilo):
        aqui o documento e' dado, e o recurso de fora vira o quadro cinza ou nada.
        """
        if tipo in (QTextDocument.ResourceType.ImageResource,
                    QTextDocument.ResourceType.ImageResource.value):
            base, recorte = separar_recorte(url.toString())
            registro = _REGISTRO.get(base)
            if registro is not None:
                return recortar(previa(registro[0]), recorte)
            return quadro_cinza()
        return None
