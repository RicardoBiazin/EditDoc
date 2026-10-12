"""Erro de leitura ou de escrita de .docx. Sem Qt.

Todo caminho de falha do leitor termina em `ErroDocx`, com um codigo estavel
(para os testes e o log) e uma mensagem em portugues (para o usuario). Nenhum
traceback chega a quem chama.
"""

from __future__ import annotations


class ErroDocx(Exception):
    def __init__(self, codigo: str, mensagem: str = "") -> None:
        self.codigo = codigo
        self.mensagem = mensagem or MENSAGENS.get(codigo, "Arquivo não pôde ser lido.")
        super().__init__(f"{codigo}: {self.mensagem}")


MENSAGENS = {
    "ZIP_INVALIDO": "Este arquivo não é um .docx válido: não é um pacote ZIP.",
    "ZIP_MUITAS_ENTRADAS": "Este arquivo tem mais partes do que um .docx razoável. Ele foi recusado por segurança.",
    "ZIP_NOME_INVALIDO": "Este arquivo tem um nome de parte que não é permitido. Ele foi recusado por segurança.",
    "ZIP_NOME_DUPLICADO": "Este arquivo tem partes com o mesmo nome. Ele foi recusado por segurança.",
    "ZIP_CRIPTOGRAFADO": "Este arquivo está protegido por senha ou criptografia, e o EditDoc não o abre.",
    "ZIP_COMPRESSAO_NAO_SUPORTADA": "Este arquivo usa uma compactação que o EditDoc não entende.",
    "ZIP_TAMANHO_EXCEDIDO": "Uma parte do arquivo é grande demais para um documento de texto. Ele foi recusado por segurança.",
    "ZIP_RAZAO_ABSURDA": "Uma parte do arquivo se descompacta muito além do razoável. Ele foi recusado por segurança.",
    "ZIP_TOTAL_EXCEDIDO": "O conteúdo descompactado é grande demais. Ele foi recusado por segurança.",
    "ZIP_PARTE_AUSENTE": "Falta uma parte essencial do arquivo: o documento não pode ser lido.",
    "OPC_SEM_DOCUMENTO_PRINCIPAL": "O arquivo não indica onde está o texto do documento.",
    "XML_DOCTYPE_PROIBIDO": "O arquivo declara DTD ou entidades XML, que não são aceitos por segurança.",
    "XML_CODIFICACAO_NAO_SUPORTADA": "O arquivo usa uma codificação de caracteres que o EditDoc não lê. Salve-o de novo no Word.",
    "XML_MALFORMADO": "O conteúdo do documento está danificado e não pode ser lido.",
    "XML_PROFUNDIDADE_EXCEDIDA": "O conteúdo do documento está aninhado de forma excessiva. Ele foi recusado por segurança.",
    "XML_ESTRUTURA": "O documento não tem o corpo de texto esperado.",
    "FORMATO_DOC_ANTIGO": "Este é um arquivo .doc do Word 97-2003. Abra-o no Word e salve como .docx.",
    "FORMATO_STRICT": "Este arquivo está no formato Strict do Office, que o EditDoc não abre. Salve-o como .docx padrão no Word.",
    "ARQUIVO_ILEGIVEL": "Não foi possível ler o arquivo do disco.",
    "ENTRADA_INVALIDA": "O conteúdo recebido não é um arquivo.",
    "ERRO_INTERNO": "Erro inesperado ao ler o documento.",
}
