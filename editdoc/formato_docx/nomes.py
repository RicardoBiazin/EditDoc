"""Namespaces, tipos de relacao e tipos de conteudo do OOXML. Sem logica."""

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
#: Formato Strict (ISO). Recusado: o programa so' le o formato padrao.
W_STRICT = "http://purl.oclc.org/ooxml/wordprocessingml/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
#: Equacoes (OMML).
MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
PKG_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC = "http://purl.org/dc/elements/1.1/"
DCT = "http://purl.org/dc/terms/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
EP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
#: DrawingML (imagens, M4).
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
#: graphicData de uma figura (pic:pic). Grafico, forma e SmartArt usam outros.
URI_IMAGEM = PIC_NS

RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
RT_STRICT = "http://purl.oclc.org/ooxml/officeDocument/relationships/"
RT_CORE = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
RT_IMAGEM = RT + "image"

CT_DOCUMENTO = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
CT_DOCUMENTO_MACRO = "application/vnd.ms-word.document.macroEnabled.main+xml"
CT_MODELO = "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"
CT_ESTILOS = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"
CT_CONFIG = "application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"
CT_NUMERACAO = "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"
CT_CORE = "application/vnd.openxmlformats-package.core-properties+xml"
CT_APP = "application/vnd.openxmlformats-officedocument.extended-properties+xml"
CT_RELS = "application/vnd.openxmlformats-package.relationships+xml"
CT_XML = "application/xml"


def q(local: str, ns: str = W) -> str:
    """Nome qualificado no formato de lxml: {ns}local."""
    return "{%s}%s" % (ns, local)

#: Cabecalho e rodape (M5).
RT_CABECALHO = RT + "header"
RT_RODAPE = RT + "footer"
RT_CONFIG = RT + "settings"
CT_CABECALHO = "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
CT_RODAPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"

#: Objetos opacos (0.1.2): formas, caixas de texto, graficos, SmartArt, OLE e VML.
WPS_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
WPG_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
WPC_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
WPI_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingInk"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
WP14_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
V_NS = "urn:schemas-microsoft-com:vml"
O_NS = "urn:schemas-microsoft-com:office:office"
URI_GRAFICO = "http://schemas.openxmlformats.org/drawingml/2006/chart"
URI_DIAGRAMA = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
#: Extensao do SmartArt: o relId do dataModelExt aponta para a relacao do documento.
DSP_NS = "http://schemas.microsoft.com/office/drawing/2008/diagram"
CT_DIAGRAMA_DADOS = "application/vnd.openxmlformats-officedocument.drawingml.diagramData+xml"

#: Extensoes do Word que podem aparecer dentro de rPr, pPr e sdtPr (0.1.5): prefixo padrao ->
#: namespace. Sao todas ignoraveis (mc:Ignorable): o leitor as guarda nos extras, e a raiz da
#: parte gravada as declara.
NS_EXTENSOES = {
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "w16du": "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
    "w16sdtfl": "http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock",
}
