# Avisos de terceiros

Componentes que o EditDoc usa, com a licença de cada um. Atualizar a cada
dependência nova.

## Dentro do programa

| Componente | Versão | Licença | Observação |
|---|---|---|---|
| PySide6 (Essentials) | 6.12.0 | LGPL-3.0 | Qt for Python. Distribuído em pasta, para que as DLLs possam ser substituídas. |
| Qt (dentro do PySide6) | 6.12 | LGPL-3.0 | Traduções `qtbase_pt_BR.qm` e `qt_pt_BR.qm` embutidas. Desde a 0.0.7 os plugins de imagem do Qt (`imageformats`: JPEG com libjpeg-turbo, licença IJG/BSD; GIF) decodificam as imagens do documento. Já vinham no pacote. |
| lxml | 6.1.3 | BSD-3-Clause | Leitura e escrita de XML. |
| Qt SVG e plugin TIFF (dentro do PySide6) | 6.12 | LGPL-3.0; libtiff (licença libtiff, estilo BSD) dentro do `qtiff` | Desde a 0.1.5 o módulo `QtSvg` (`Qt6Svg.dll`, plugin `qsvg`) e o plugin `imageformats/qtiff` mostram as imagens SVG e TIFF do documento. Já vinham no PySide6-Essentials; o `.spec` passa a incluir o `QtSvg`. EMF e WMF usam o GDI do Windows (sistema), sem componente novo. |

## Só para desenvolvimento e testes

| Componente | Versão | Licença | Observação |
|---|---|---|---|
| python-docx | 1.2.0 | MIT | Oráculo de leitura nos testes. Não entra no programa. |

## Só para gerar o executável

| Componente | Versão | Licença | Observação |
|---|---|---|---|
| PyInstaller | 6.22.3 | GPL-2.0 com exceção para o bootloader | Monta o pacote. Não entra no programa como biblioteca. |

## Fora do pacote

Nenhum componente AGPL ou GPL entra no programa. PyMuPDF (AGPL) foi avaliado e
não é usado.
