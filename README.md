# EditDoc

Editor de documentos no formato `.docx` para Windows, com a aparência de um processador
de texto de escritório: páginas na tela, faixa de opções, estilos, tabelas, imagens,
cabeçalho e rodapé, impressão e PDF. Feito em Python e Qt (PySide6), sem precisar do
Word instalado.

> **Versão 0.1.0: a primeira versão completa.** Tudo o que o roteiro prometia para a
> 0.1.0 está nela: visão em páginas, tabelas e imagens, cabeçalho e rodapé com número de
> página, estilos com galeria, faixa de opções completa, impressão, PDF e, nesta versão,
> recuperação automática, preferências (Arquivo > Opções) e acessibilidade (leitor de
> tela e uso completo pelo teclado). O que mudou em cada versão está no
> [CHANGELOG.md](CHANGELOG.md).

O EditDoc não é afiliado à Microsoft. Word é marca registrada da Microsoft.

## O que ele faz

Ao abrir, aparece uma janela com a faixa de opções no alto (Arquivo, Desfazer e Refazer,
e as abas Página Inicial, Inserir, Layout e Exibir), a régua, e o documento como folhas
brancas sobre um fundo cinza, com as margens, o cabeçalho e o rodapé de cada página. Na
barra de status ficam "Página X de Y", a contagem de palavras e o zoom.

- **Abrir e salvar `.docx`**: texto, negrito, itálico, sublinhado, tachado, subscrito,
  sobrescrito, fonte, tamanho, cor, alinhamento, recuos, espaçamento, listas simples,
  quebras de página, tabelas (com mesclas, bordas e sombreamento), imagens na linha do
  texto (PNG, JPEG, GIF e BMP), cabeçalhos e rodapés (primeira página e páginas pares
  diferentes) com os campos de número de página e total de páginas, e os estilos do
  arquivo. A gravação é atômica: o arquivo novo é escrito ao lado, relido, conferido e
  só então troca o original.
- **Caixas de texto, formas, gráficos, SmartArt, objetos OLE, equações e imagens
  flutuantes** são preservados: o EditDoc não os edita, mas eles voltam ao arquivo
  exatamente como vieram (o XML, as imagens, as planilhas dos gráficos e a posição na
  página). Na tela cada um aparece como um quadro com o nome ("Caixa de texto: …",
  "Gráfico", "Equação: …") no lugar dele no texto; Delete ou Backspace apagam o objeto
  inteiro, e Ctrl+Z o traz de volta.
- **Páginas**: A4, Carta e Ofício, retrato e paisagem, margens predefinidas ou
  personalizadas, zoom de 25% a 300% (o teto depende da escala da tela), uma página,
  várias páginas lado a lado ou largura da página.
- **Estilos**: galeria na Página Inicial com a aparência de cada estilo, painel de
  estilos, Modificar estilo, Criar um estilo a partir da seleção, Atualizar estilo.
- **Exibir**: régua, painel de navegação pelos títulos, marcas de formatação.
- **Localizar e substituir**, com diferenciar maiúsculas e palavra inteira.
- **Imprimir, visualizar impressão e exportar PDF** (e texto `.txt`): a folha impressa é a
  mesma da tela.
- **Recuperação automática**: de 10 em 10 minutos (o intervalo é configurável), e também
  depois de muitas alterações seguidas, o EditDoc guarda uma cópia do documento alterado
  em `%LOCALAPPDATA%\EditDoc\Recuperacao`, nunca na pasta do documento e nunca por cima
  dele. Se o programa fechar sem salvar (queda, falta de energia com o disco intacto,
  processo encerrado), ao abrir de novo aparece "Recuperação de documentos", com as
  cópias para abrir, salvar como ou descartar. Salvar ou fechar normalmente apaga a cópia.
  Também em Arquivo > Recuperar documentos.
- **Preferências** (Arquivo > Opções): fonte e tamanho do documento novo, papel padrão,
  unidade da régua (centímetros ou polegadas), intervalo da recuperação automática,
  abrir o PDF depois de exportar, quantos documentos o menu Abrir recente mostra (e
  limpar a lista) e o tema (claro, escuro ou igual ao Windows). Ficam em
  `%APPDATA%\EditDoc\config.json`.
- **Acessibilidade**: todo botão, campo e lista tem nome para o leitor de tela (o botão
  "N" se anuncia como "Negrito"); o documento se apresenta como texto editável, com o
  nome do arquivo, a página atual e o parágrafo do cursor; trocar de página anuncia
  "Página X de Y". Tudo funciona sem mouse (ver os atalhos abaixo).
- **Uma janela por documento**, como o Word. Abrir pelo Explorer um segundo arquivo leva
  o arquivo à janela que já está aberta.

## Instalação

1. Baixe `EditDoc-0.1.2-win64.zip` da página
   [Releases](https://github.com/RicardoBiazin/EditDoc/releases) do projeto.
2. Extraia o ZIP onde quiser (por exemplo em `C:\Programas`). Ele traz a pasta
   `EditDoc\`.
3. Abra `EditDoc\EditDoc.exe`. Não há instalador nem privilégio de administrador.

Para o EditDoc aparecer em "Abrir com" dos arquivos `.docx` (sem trocar o programa
padrão), rode no PowerShell, a partir do código-fonte:

```
powershell -ExecutionPolicy Bypass -File associar.ps1 -Exe C:\Programas\EditDoc\EditDoc.exe .docx
```

Para desfazer: `associar.ps1 -Remover`. Para desinstalar, apague a pasta
`EditDoc\` e, se quiser, `%APPDATA%\EditDoc` (preferências e log) e
`%LOCALAPPDATA%\EditDoc` (cópias de recuperação).

Requer Windows 10 ou 11, 64 bits.

## Atalhos de teclado

| Ação | Atalho |
|---|---|
| Novo, Abrir, Salvar, Fechar | Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+W |
| Salvar como | F12 ou Ctrl+Shift+S |
| Imprimir, Visualizar impressão | Ctrl+P, Ctrl+F2 |
| Desfazer, Refazer | Ctrl+Z, Ctrl+Y (ou Ctrl+Shift+Z) |
| Recortar, Copiar, Colar, Selecionar tudo | Ctrl+X, Ctrl+C, Ctrl+V, Ctrl+A |
| Localizar, Substituir | Ctrl+F, Ctrl+H |
| Negrito, Itálico, Sublinhado | Ctrl+B, Ctrl+I, Ctrl+U |
| Subscrito, Sobrescrito | Ctrl+=, Ctrl+Shift+= |
| Aumentar e diminuir a fonte | Ctrl+], Ctrl+[ |
| Limpar formatação de caractere | Ctrl+Espaço |
| Marcadores | Ctrl+Shift+L |
| Aumentar e diminuir recuo | Ctrl+M, Ctrl+Shift+M |
| Alinhar à esquerda, centro, à direita, justificar | Ctrl+L, Ctrl+E, Ctrl+R, Ctrl+J |
| Espaçamento 1,0, 1,5 e 2,0 | Ctrl+1, Ctrl+5, Ctrl+2 |
| Quebra de página | Ctrl+Enter |
| Estilos Normal, Título 1, 2 e 3 | Ctrl+Shift+N, Ctrl+Alt+1, 2 e 3 |
| Painel de estilos | Ctrl+Alt+Shift+S |
| Marcas de formatação | Ctrl+Shift+8 |
| Zoom | Ctrl+roda do mouse |
| Tabela: próxima e célula anterior | Tab, Shift+Tab (Tab na última célula cria uma linha) |
| Tabulação dentro da célula | Ctrl+Tab |
| Sair da edição do cabeçalho e do rodapé | Esc |

**Faixa pelo teclado**, como no Word: **Alt** (apertar e soltar) ou **F10** mostra uma letra
em cada aba (P Página Inicial, N Inserir, L Layout, E Exibir, H Cabeçalho e Rodapé,
A Arquivo, 1 Desfazer, 2 Refazer). A letra da aba mostra as letras dos botões dela, e a
letra do botão executa o comando. Com o foco na faixa, as setas andam entre abas e
botões, Enter ou Espaço apertam o botão e Esc volta ao documento. **F6** e **Shift+F6**
andam entre o documento, a faixa, a barra de busca, os painéis abertos e o zoom.

## Limites conhecidos

O que o EditDoc ainda não faz, e o que acontece com o arquivo:

- **Política de perda ao abrir `.docx`**: tudo o que o arquivo tem e o EditDoc não edita
  gera um aviso na barra amarela, com o botão Detalhes. Se salvar apagaria alguma coisa
  (comentário, revisão, nota de rodapé, hiperlink, campo que não é número de página,
  controle de conteúdo, seções com cabeçalhos diferentes, formatação que o EditDoc não
  conhece...), o primeiro Salvar pede confirmação e oferece "Salvar cópia". Caixas de
  texto, formas, gráficos, SmartArt, objetos OLE, equações e imagens flutuantes ou em
  formato que a tela não mostra (EMF, WMF, SVG, vinculadas) **não** se perdem desde a
  0.1.2: o aviso diz que são preservados e o Salvar não pede confirmação por eles. Só o
  objeto que não pode ser preservado inteiro (referência quebrada no arquivo, ou acima
  dos limites: 2000 objetos, 4 MB de XML por objeto, 64 partes por objeto) sai do arquivo,
  com aviso e confirmação. Os estilos que o EditDoc não altera e o tema voltam ao arquivo
  como vieram.
- Partes que o EditDoc ainda não regrava e que hoje saem **sem aviso**: as propriedades
  personalizadas do documento (`docProps/custom.xml`), os dados anexados por SharePoint e
  similares (`customXml`), a tabela de fontes, as configurações da Web e as do Word
  (`settings.xml` é refeito). O texto e a aparência não dependem delas.
- Objetos preservados: copiar e colar dentro do EditDoc leva o texto em volta, mas não o
  objeto (a barra de status avisa); uma nota de rodapé, um comentário ou uma lista
  numerada **dentro** de uma caixa de texto perdem a referência ou a numeração ao salvar
  (com aviso), porque essas partes não voltam ao arquivo.
- Fora desta versão: revisão com controle de alterações, comentários, notas de rodapé,
  sumário e índices, mala direta, editar equações, formas e caixas de texto (elas são
  preservadas, não editadas), colunas, várias seções editáveis, ortografia, `.doc`, RTF,
  ODT e macros (nunca).
- Numeração de listas: só marcadores e numeração simples (um nível).
- Tabelas: digitar numa tabela muito grande fica lento (o Qt refaz a tabela a cada tecla;
  acima de 5000 células a tabela abre como parágrafos, com aviso); a altura de linha do
  arquivo é guardada, mas a tela não a aplica; "Dividir células" só desfaz mescla.
- A quebra de página não acompanha a do Word linha a linha (não há viúva e órfã, e a
  medida das fontes é a do Qt). O número de páginas pode diferir em documentos longos.
- O cabeçalho que passa da margem empurra o corpo de todas as páginas pela altura do
  maior deles (o Word ajusta página a página).
- Leitor de tela: o documento é exposto como texto editável com o parágrafo do cursor
  como valor; a navegação por palavra e por linha dentro do texto, pelo leitor de tela,
  não existe ainda (limite do PySide6 6.11, ver `docs/SPIKES.md`).
- Zoom máximo: 300% em tela normal, 200% em escala 150% e 150% em escala 200%.
- Desfazer uma mudança de estilo feita durante a edição do cabeçalho fica no desfazer do
  corpo.

## Compilar a partir do código

Requer Windows 10 ou 11 e Python 3.13.

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe tests\rodar_todos.py
.venv\Scripts\python.exe app.py
```

Gerar o executável e o ZIP de entrega:

```
build.bat
```

O `build.bat` roda os testes, empacota com PyInstaller, confere que o `.exe` passa na
autoverificação (`EditDoc.exe --autoverificacao`: módulos, `.docx`, PDF, impressão e
recuperação automática numa pasta temporária), confere que ele abre a janela e gera
`dist\EditDoc-0.1.2-win64.zip`. Se qualquer etapa falhar, nada é entregue.

O plano e as decisões estão em [docs/ARQUITETURA.md](docs/ARQUITETURA.md), as medições em
[docs/SPIKES.md](docs/SPIKES.md), e o guia para quem quer contribuir em
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licença

MIT. Ver [LICENSE](LICENSE). Os componentes de terceiros estão listados em
[AVISOS_DE_TERCEIROS.md](AVISOS_DE_TERCEIROS.md).
