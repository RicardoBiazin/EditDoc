"""Namespaces, tipos de relacao e tipos de conteudo do OOXML. Sem logica."""

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
#: Formato Strict (ISO). Recusado: o programa so' le o formato padrao.
W_STRICT = "http://purl.oclc.org/ooxml/wordprocessingml/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
PKG_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC = "http://purl.org/dc/elements/1.1/"
DCT = "http://purl.org/dc/terms/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
EP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
RT_STRICT = "http://purl.oclc.org/ooxml/officeDocument/relationships/"
RT_CORE = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"

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
