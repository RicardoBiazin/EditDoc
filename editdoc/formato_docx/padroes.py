"""Padroes do documento que o EditDoc grava, e contra os quais o leitor compara. Sem Qt."""

#: A4 em twips.
PAPEL_PADRAO = (11906, 16838)
#: Margens do Word em portugues, na ordem (lado, twips).
MARGENS_PADRAO = (("top", 1417), ("right", 1701), ("bottom", 1417), ("left", 1701),
                  ("header", 708), ("footer", 708), ("gutter", 0))
#: Calibri 11 e espacamento depois de 8 pt, entre linhas 1,08 (padrao do Word 2013 em diante).
FONTE_PADRAO = "Calibri"
TAMANHO_PADRAO_MEIO_PT = 22
ESPACO_DEPOIS_PADRAO_TW = 160
LINHA_PADRAO = 259
