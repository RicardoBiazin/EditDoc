"""Leitura e escrita de .docx com lxml e zipfile. Sem Qt.

`leitor.ler` e `escritor.escrever` sao a entrada e a saida. `ordem` guarda as
regras que o Word exige (ordem dos filhos, xml:space, pacote OPC) e serve de
validador nos testes e antes de cada gravacao.
"""
