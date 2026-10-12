# Avisos de terceiros

Componentes que o EditDoc usa, com a licença de cada um. Atualizar a cada
dependência nova.

## Dentro do programa

| Componente | Versão | Licença | Observação |
|---|---|---|---|
| PySide6 (Essentials) | 6.11.2 | LGPL-3.0 | Qt for Python. Distribuído em pasta, para que as DLLs possam ser substituídas. |
| Qt (dentro do PySide6) | 6.11 | LGPL-3.0 | Traduções `qtbase_pt_BR.qm` e `qt_pt_BR.qm` embutidas. |
| python-docx | 1.2.0 | MIT | Leitura e escrita de `.docx`. |
| lxml | 6.1.3 | BSD-3-Clause | Leitura e escrita de XML. |

## Só para gerar o executável

| Componente | Versão | Licença | Observação |
|---|---|---|---|
| PyInstaller | 6.22.3 | GPL-2.0 com exceção para o bootloader | Monta o pacote. Não entra no programa como biblioteca. |

## Fora do pacote

Nenhum componente AGPL ou GPL entra no programa. PyMuPDF (AGPL) foi avaliado e
não é usado.
