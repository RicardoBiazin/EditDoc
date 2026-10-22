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
e as abas Página Inicial, Inserir, Layout, Referências, Revisão e Exibir), a régua, e o documento como folhas
brancas sobre um fundo cinza, com as margens, o cabeçalho e o rodapé de cada página. Na
barra de status ficam "Página X de Y", a contagem de palavras e o zoom.

- **Abrir e salvar `.docx`**: texto, negrito, itálico, sublinhado, tachado, subscrito,
  sobrescrito, fonte, tamanho, cor, alinhamento, recuos, espaçamento, listas (ver abaixo),
  quebras de página, tabelas (com mesclas, bordas e sombreamento), imagens na linha do
  texto (PNG, JPEG, GIF e BMP), cabeçalhos e rodapés (primeira página e páginas pares
  diferentes) com os campos de número de página e total de páginas, e os estilos do
  arquivo. A gravação é atômica: o arquivo novo é escrito ao lado, relido, conferido e
  só então troca o original.
- **Caixas de texto, formas, gráficos, SmartArt, objetos OLE, equações e imagens
  flutuantes** são preservados: eles voltam ao arquivo exatamente como vieram (o XML, as
  imagens, as planilhas dos gráficos e a posição na página). Na tela o objeto na linha do
  texto aparece como um quadro com o nome ("Gráfico", "Equação: …"); Delete ou Backspace
  apagam o objeto inteiro, e Ctrl+Z o traz de volta.
- **Objetos flutuantes na posição da página** (desde a 0.1.7): a imagem, a caixa de texto,
  a forma e o grupo que o Word posiciona na página (capa, faixa colorida do cabeçalho,
  marca-d'água, logotipo) aparecem onde o Word os põe, na tela, no PDF e na impressão: a
  imagem com a figura de verdade (inclusive EMF, WMF, SVG e TIFF e o recorte), a caixa de
  texto com o fundo, o contorno e o texto dentro, a forma (retângulo, elipse, linha,
  triângulos, setas...) com as cores do arquivo, o grupo com as peças no lugar, atrás ou na
  frente do texto. O texto do corpo contorna o objeto com "Quadrado" (e "Justo" e
  "Através", tratados como Quadrado) e passa para baixo dele com "Superior e inferior"; o
  objeto do cabeçalho e do rodapé aparece em todas as páginas, atrás do texto. Clique no
  objeto para selecioná-lo (contorno azul); Delete apaga, Ctrl+Z traz de volta; duplo
  clique na caixa de texto abre o editor do texto. O arquivo não muda se você não mexe no
  objeto.
- **Mover e redimensionar objetos** (0.1.9), como no Word: clique no objeto flutuante
  (imagem, caixa de texto, forma, grupo, VML) e **arraste o corpo** para mover; um contorno
  tracejado mostra onde ele vai ficar, e o texto em volta se refaz ao soltar. As **oito
  alças** (cantos e meio de cada lado) mudam o tamanho; **Shift** trava a proporção (nos
  cantos de uma imagem ela já fica travada, como no Word). Com o objeto selecionado, as
  **setas** movem 1 pixel de tela e **Ctrl+setas** um quarto de pixel; **Esc** tira a
  seleção. Arrastar para outra página leva a âncora para o parágrafo de lá, como o Word. A
  caixa de texto e a forma **na linha do texto** ganham as alças como a imagem. No
  **cabeçalho e no rodapé**, os objetos se selecionam, movem e redimensionam durante a edição
  deles (duplo clique no alto ou no pé da página). **Layout > Organizar > Quebra de texto**
  (ou o menu de contexto do objeto) troca a disposição: Alinhado ao texto, Quadrado,
  Comprimido, Através, Superior e inferior, Atrás do texto e Na frente do texto; **Posição**
  abre o diálogo **Posição e tamanho** (posição horizontal e vertical em cm, relativa à
  página, à margem, à coluna, ao parágrafo, ao caractere ou à linha; largura e altura com a
  proporção travada; a quebra). Cada arraste, tecla ou diálogo é um passo de desfazer. No
  arquivo só muda a posição e o tamanho do objeto (o resto do XML volta igual); um objeto
  alinhado (centro, direita) passa a ter a posição em centímetros quando é arrastado, como
  no Word.
- **Controle de alterações** (0.1.13), como no Word: **Revisão > Controlar alterações**
  (**Ctrl+Shift+E**) liga e desliga, e o arquivo guarda a escolha. Ligado, o que você digita ou
  cola fica marcado como inserção (com o nome das **Opções** e a data), o que você apaga de outro
  autor fica tachado, o que você mesmo inseriu e ainda não foi aceito some de verdade, o **Enter**
  marca o parágrafo novo, e negrito, fonte, alinhamento, recuo, espaçamento, listas e estilos
  guardam a formatação de antes. **Exibir para revisão**: **Marcação simples** (o texto final com
  uma barra vermelha na margem onde houve alteração), **Toda a marcação** (inserido sublinhado e
  excluído tachado, na cor de cada autor; o texto movido em verde, duplo), **Sem marcação** (o
  texto final) e **Original** (o texto antes das alterações). **Aceitar** e **Rejeitar** a
  alteração do cursor (ou as da seleção) e ir para a próxima, **todas**, ou **todas de um
  autor**; **Anterior** e **Próxima**; também no menu de contexto. O painel lateral
  **Comentários e revisões** tem a lista das alterações (tipo, autor, data e o trecho): clique
  para ir até ela; Aceitar e Rejeitar valem para a escolhida. Ctrl+Z desfaz cada comando.
  Desde a 0.1.14 também se **rejeitam** as alterações de propriedades da tabela, da grade, da
  linha, da célula e da seção (volta o que era antes: largura, alinhamento, altura, sombreamento,
  papel, margens...), a numeração posta com o controle ligado e a célula inserida ou excluída
  quando a coluna (ou a linha) inteira tem a mesma marca; **excluir linha ou coluna** de tabela
  com o controle ligado fica marcado (como no Word), e **recortar e colar** o mesmo trecho dentro
  do documento vira **movido** (origem e destino em verde, ligados).
  Copiar leva o texto como se lê (em Toda a marcação, o final, como o Word), Localizar não acha
  o que está escondido e a contagem de palavras conta o texto final. **Imprimir marcações**
  (ligado por padrão) imprime e exporta o PDF como a tela mostra, com os **comentários na
  margem**; desligado, sai o texto final, sem comentários. As alterações do Word (inserções,
  exclusões, movimentos, formatação, parágrafos, linhas e células de tabela, seções), também no
  cabeçalho, no rodapé, nas notas e nos comentários, voltam ao arquivo como vieram.
- **Várias seções no mesmo documento** (0.1.12), como no Word: cada seção tem o seu
  **papel, orientação e margens** (uma página **paisagem** no meio de um documento em
  retrato), os seus **cabeçalhos e rodapés** (a seção que não tem usa os da anterior,
  "Vincular ao anterior"), a sua **primeira página diferente** e a sua **numeração de
  páginas** (reinício e formato: i, ii, iii na introdução e 1, 2, 3 no corpo). A seção que
  começa em **página par ou ímpar** ganha a página em branco antes, quando precisa, como no
  Word. **Layout > Quebras > Quebra de seção** (Próxima página, Contínua, Página par, Página
  ímpar) parte o parágrafo no cursor; a quebra aparece com as **marcas de formatação**
  ("Quebra de seção (Próxima página)"); **Backspace** no começo do parágrafo seguinte (ou
  **Delete** antes dela) apaga a quebra e o texto de cima passa a ser da seção de baixo; Ctrl+Z
  desfaz. Papel, orientação e margens da aba **Layout** valem para a **seção do cursor**; em
  **Margens > Personalizadas**, "Aplicar a: Documento inteiro". Na edição do cabeçalho, o rótulo
  diz a seção ("Cabeçalho - Seção 2 - Igual ao anterior") e **Vincular ao anterior** liga ou
  desliga o vínculo. A barra de status mostra "Seção 2 de 3". Tudo o que a seção do arquivo
  tem e o EditDoc não usa (colunas, numeração de linhas, alinhamento vertical, bordas de
  página, grade...) volta ao arquivo como veio. O PDF e a impressão trocam de papel na folha.
- **Notas de rodapé e de fim** (0.1.10), como no Word: a nota aparece no **pé da página**
  onde está a referência, abaixo de um separador curto, com o número sobrescrito no texto e
  na nota; o texto do corpo daquela página encolhe para dar lugar a ela. A nota que não cabe
  continua na página seguinte, abaixo de um separador da largura da página; as **notas de
  fim** vêm depois do texto, no fim do documento. **Referências > Inserir nota de rodapé**
  (**Alt+Ctrl+F**) e **Inserir nota de fim** (**Alt+Ctrl+D**) põem a marca no cursor e levam
  o cursor para a nota; **clique na nota** para editá-la no lugar (Esc, ou um clique no texto,
  volta); **duplo clique na marca** leva à nota e **duplo clique no número da nota** volta à
  marca; **Próxima** e **Anterior** andam entre as notas; **Opções** escolhe o formato do
  número (1, 2, 3; a, b, c; i, ii, iii; *, †, ‡), o número inicial, a numeração contínua ou
  reiniciada a cada página, a posição (pé da página ou logo abaixo do texto) e converte todas
  as notas de rodapé em notas de fim (ou o contrário). Apagar a marca apaga a nota; Ctrl+Z a
  traz de volta. A edição de uma nota é um passo de desfazer no texto. Copiar e colar dentro do
  EditDoc leva a nota junto (com outro número). A marca personalizada do Word ("*") é
  preservada. As notas que você não mexe voltam ao arquivo exatamente como vieram, com os
  links e as imagens; o PDF e a impressão têm as notas no pé da página, e o `.txt` as lista
  no fim, numeradas.
- **Digitação rápida em documento pesado** (0.1.8): num manual real de 51 páginas (capa com
  imagem de página inteira e caixas de texto, sumário com links e números de página,
  49 desenhos), digitar na capa, no sumário e no corpo fica abaixo de 16 ms por tecla
  (era 48 a 91 ms). E o corpo de cada página começa onde termina o cabeçalho dela: na capa
  com o cabeçalho da primeira página vazio, o título e as caixas ficam onde o Word os põe.
- **Comentários** (desde a 0.1.6): os comentários do Word aparecem no **painel de
  comentários** à direita (Revisão > Mostrar comentários), um cartão por conversa, com
  autor, data, texto, as respostas e o estado "Resolvido"; o trecho comentado fica realçado
  em amarelo claro (só na tela: não sai no PDF, na impressão nem no `.txt`). Clicar no cartão
  seleciona o trecho; o cursor num trecho comentado destaca o cartão. **Revisão > Novo
  comentário** (**Ctrl+Alt+M**) comenta a seleção (sem seleção, a palavra do cursor);
  **Responder**, **Editar** (negrito, itálico, sublinhado e links), **Resolver** ou
  **Reabrir**, **Excluir** (com as respostas), **Excluir todos**, **Anterior** e **Próximo**
  estão na aba Revisão, no cartão e no botão direito. Comentário com campo ou menção (o "@"
  do Word) abre só para leitura, com o motivo; responder e resolver continuam valendo. O
  autor e as iniciais vêm de Arquivo > Opções (vazio = o usuário do Windows). Apagar todo o
  trecho comentado leva o comentário junto, como no Word; apagar só uma ponta deixa o
  comentário no que sobrou. Tudo se desfaz com Ctrl+Z. As partes do Word (`comments.xml`,
  respostas e resolvido, ids e datas UTC, `people.xml`) voltam iguais quando você não mexe
  nelas.
- **Referências de estilo** (desde a 0.1.6): o estilo que o arquivo cita sem definir (os
  estilos internos do Word, como o da marca de comentário ou o "Sumário 2") volta como veio,
  com a aparência padrão do Word na tela; o estilo de tabela com formatação condicional
  (cabeçalho colorido, faixas alternadas) volta ao arquivo, e o fundo das faixas e do
  cabeçalho aparece na tela e no PDF.
- **Texto das caixas de texto** (desde a 0.1.5): a caixa aparece do tamanho dela, com o
  texto dentro. **Duplo clique** na caixa (ou Enter com a caixa selecionada, ou **Editar
  texto da caixa** no botão direito) abre o editor do texto, com negrito (Ctrl+B), itálico
  (Ctrl+I) e sublinhado (Ctrl+U); a formatação que o texto já tinha fica. OK grava o texto
  novo dentro da caixa (nas duas versões que o Word guarda, a moderna e a de
  compatibilidade), sem mexer na posição, no tamanho, na cor ou no contorno; um Ctrl+Z
  desfaz. A caixa que tem tabela, imagem, campo ou outro objeto dentro abre só para
  leitura, com o motivo. A forma sem texto não é editável.
- **Imagens EMF, WMF, TIFF e SVG** (desde a 0.1.5) aparecem na tela, no PDF e na impressão,
  em vez do quadro cinza. O arquivo original da imagem volta ao `.docx` sem mudança. EMF e
  WMF dependem do Windows. A imagem vinculada a um arquivo externo nunca é lida do disco
  nem da rede: continua um quadro com o nome do arquivo.
- **Formatação sem perda** (desde a 0.1.5): tudo o que o EditDoc não edita na formatação
  do texto e do parágrafo volta ao arquivo como veio (realce, sombreamento, bordas do
  parágrafo e do trecho, tabulações, espaçamento entre caracteres, maiúsculas, versalete,
  escala, idioma, quadro de texto, sublinhado duplo, cor e fonte do tema, entrelinha
  exata...), e também o da tabela, da linha e da célula (tabela flutuante, margens e
  direção do texto da célula, linha que não se parte). Na tela aparecem o realce, o
  sombreamento, as bordas, as tabulações com pontilhado, o espaçamento, as maiúsculas, o
  versalete e a entrelinha exata. O recorte de imagem do Word também volta e aparece.
  Digitar, Enter, copiar e colar levam essa formatação junto, como no Word; Limpar
  formatação a tira.
- **Controles de conteúdo** (desde a 0.1.5): o quadro "Sumário" do Word e os campos de
  formulário (texto, data, lista) voltam ao arquivo com as propriedades; na tela, colchetes
  finos azulados marcam o começo e o fim (não saem na impressão).
- **Hiperlinks** (desde a 0.1.3): o link do arquivo aparece com o estilo dele (azul
  sublinhado) e volta ao arquivo com o endereço. **Ctrl+clique** abre o link: endereço da
  Web e e-mail abrem direto no programa do Windows; arquivo, pasta de rede e outros
  endereços só abrem depois de você confirmar; link que executa código (`javascript:`)
  nunca abre. O link para um marcador do documento leva o cursor até ele. **Inserir >
  Link** (Ctrl+K) insere um link no cursor ou na seleção, para um endereço ou para um
  marcador do documento; com o cursor num link, Ctrl+K edita o link, e **Remover link**
  tira o link e deixa o texto.
- **Campos** (desde a 0.1.3): sumário, referências (REF, PAGEREF), data, autor, IF e
  qualquer outro campo do Word voltam ao arquivo como campos, que o Word atualiza (F9).
  Na tela, o último resultado aparece como texto comum, que pode ser editado, entre dois
  colchetes finos e cinza que marcam o começo e o fim do campo (eles não saem na
  impressão). Apagar só o começo ou só o fim de um campo transforma o resultado em texto
  comum ao salvar, com aviso. O EditDoc não recalcula esses campos (só o número da página
  e o total de páginas, como antes).
- **Listas e numeração** (desde a 0.1.4): marcadores e numeração do Word como o Word mostra:
  vários níveis ("1.", "1.1.", "1.1.1."), títulos numerados pelo estilo (Título 1, 2 e 3 com
  "1", "1.1", "1.1.1"), letras, romanos, números por extenso, o marcador na fonte Symbol ou
  Wingdings, o marcador de figura, numeração que continua entre listas separadas por texto
  e a que reinicia ou começa num número escolhido. O número aparece no recuo do arquivo,
  com o texto depois da tabulação, e sai igual no PDF, na impressão e no `.txt`. A
  numeração do arquivo (`numbering.xml`) volta inteira: o que você não mexeu sai idêntico.
  Na Página Inicial, **Marcadores** e **Numeração** ligam e desligam a lista; a seta ao lado
  abre a galeria (•, ○, ▪; 1., 1), a., A., i., I.), a **Lista de vários níveis** (1/1.1/1.1.1,
  Capítulo/Seção e títulos numerados) e **Reiniciar em 1**, **Continuar numeração** e
  **Definir valor de numeração** (também no menu do botão direito). No item: **Tab** e
  **Shift+Tab** no começo mudam o nível; **Enter** num item vazio sobe um nível ou sai da
  lista; **Backspace** no começo tira o número (o texto fica onde estava) e, de novo, tira o
  recuo. **Aumentar e Diminuir recuo** num item mudam o nível. Copiar e colar dentro do
  EditDoc (inclusive entre janelas) mantém a lista; a lista colada de outro programa vira
  lista do EditDoc.
- **Partes que o EditDoc não edita** voltam ao arquivo como vieram (desde a 0.1.3): as
  propriedades personalizadas, os dados do SharePoint (`customXml`), a tabela de fontes
  (com as fontes embutidas), as configurações da Web e as configurações do Word
  (compatibilidade, proteção, variáveis do documento), além das propriedades do documento
  (assunto, palavras-chave, empresa).
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
- **Salvar conferido**: o EditDoc grava um arquivo novo ao lado do original, lê de volta e
  só então troca. Desde a 0.1.16 a conferência compara também a formatação que muda o
  layout (espaços, entrelinha, recuos, fonte e tamanho de cada trecho, larguras de tabela),
  já resolvida pelo padrão do documento e pelos estilos. Se a releitura não bater com o que está na tela, o original fica como
  estava, o documento continua aberto com as alterações (e a cópia de recuperação é
  gravada), e a mensagem oferece salvar essa cópia, sem a conferência, em outro arquivo
  (nunca por cima do original) para abrir no Word. O detalhe técnico vai para o log
  (`%APPDATA%\EditDoc\editdoc.log`).
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

1. Baixe `EditDoc-0.1.19-win64.zip` da página
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
| Aumentar e diminuir recuo (no item de lista: o nível) | Ctrl+M, Ctrl+Shift+M |
| Item de lista: descer e subir o nível | Tab e Shift+Tab no começo do item |
| Alinhar à esquerda, centro, à direita, justificar | Ctrl+L, Ctrl+E, Ctrl+R, Ctrl+J |
| Espaçamento 1,0, 1,5 e 2,0 | Ctrl+1, Ctrl+5, Ctrl+2 |
| Quebra de página | Ctrl+Enter |
| Inserir ou editar link | Ctrl+K |
| Novo comentário | Ctrl+Alt+M |
| Controlar alterações (ligar e desligar) | Ctrl+Shift+E |
| Inserir nota de rodapé, nota de fim | Alt+Ctrl+F, Alt+Ctrl+D |
| Sair da edição da nota | Esc |
| Abrir o link | Ctrl+clique no link |
| Estilos Normal, Título 1, 2 e 3 | Ctrl+Shift+N, Ctrl+Alt+1, 2 e 3 |
| Painel de estilos | Ctrl+Alt+Shift+S |
| Marcas de formatação | Ctrl+Shift+8 |
| Zoom | Ctrl+roda do mouse |
| Tabela: próxima e célula anterior | Tab, Shift+Tab (Tab na última célula cria uma linha) |
| Tabulação dentro da célula | Ctrl+Tab |
| Sair da edição do cabeçalho e do rodapé | Esc |
| Objeto selecionado: mover 1 px de tela, ou um quarto de px | Setas, Ctrl+setas |
| Objeto selecionado: tirar a seleção | Esc |
| Arrastar a alça do objeto mantendo a proporção | Shift + arrastar |

**Faixa pelo teclado**, como no Word: **Alt** (apertar e soltar) ou **F10** mostra uma letra
em cada aba (P Página Inicial, N Inserir, L Layout, S Referências, R Revisão, E Exibir,
H Cabeçalho e Rodapé,
A Arquivo, 1 Desfazer, 2 Refazer). A letra da aba mostra as letras dos botões dela, e a
letra do botão executa o comando. Com o foco na faixa, as setas andam entre abas e
botões, Enter ou Espaço apertam o botão e Esc volta ao documento. **F6** e **Shift+F6**
andam entre o documento, a faixa, a barra de busca, os painéis abertos e o zoom.

## Limites conhecidos

O que o EditDoc ainda não faz, e o que acontece com o arquivo:

- **Política de perda ao abrir `.docx`**: a faixa amarela aparece só quando salvar apagaria
  alguma coisa (revisão acima dos limites, controle de conteúdo de linha de tabela, formatação
  que o EditDoc não conhece...); o primeiro Salvar pede confirmação e oferece "Salvar cópia". O
  que o arquivo tem e o EditDoc não edita, mas não perde ao salvar, não gera faixa (desde a
  0.1.19): fica na lista de **Arquivo > Objetos preservados**, que também abre pelo botão Detalhes
  da faixa. **Não** se perdem: caixas de texto, formas,
  gráficos, SmartArt, objetos OLE, equações e imagens flutuantes ou em formato que a tela
  não mostra (desde a 0.1.2); hiperlinks, marcadores, campos de qualquer tipo (sumário,
  referências, data...) e as partes do arquivo que o EditDoc não edita (desde a 0.1.3);
  a numeração de listas inteira, com os níveis, os formatos, os símbolos e a lista ligada
  ao estilo (desde a 0.1.4); a formatação de texto, parágrafo e tabela que o EditDoc não
  edita e os controles de conteúdo de parágrafo e de bloco (desde a 0.1.5); os
  comentários, com respostas, resolvido e pessoas, e as referências a estilos que o arquivo
  cita sem definir, além do estilo de tabela com formatação condicional (desde a 0.1.6); as
  notas de rodapé e de fim, com as propriedades e as notas separadoras (desde a 0.1.10); as
  seções, com papel, margens, cabeçalhos, numeração, colunas e o resto (desde a 0.1.12); as
  alterações controladas, com autores e datas (desde a 0.1.13).
  Comentário ainda avisa só quando não pode ser lido (danificado, acima de 5000, ancorado
  só no cabeçalho, no rodapé ou numa caixa de texto) ou quando a edição apagou a marca de
  referência dele sem levá-lo junto. Desde a 0.1.13 a impressão e o PDF levam os comentários
  na margem quando "Imprimir marcações" está ligado.
  Os estilos que o EditDoc não altera e o tema voltam como vieram. Ainda avisam, com
  confirmação, só o que não pode voltar inteiro: objeto, link ou campo com referência
  quebrada no arquivo, ou acima dos limites (2000 objetos; 20.000 campos, links ou
  marcadores; instrução de campo com mais de 4096 caracteres; 8 campos um dentro do
  outro; 2000 definições de lista ou 10.000 listas, texto de número com mais de 256
  caracteres), item de lista que cita numeração que não existe ou nível fora de 1 a 9, parte do arquivo com conteúdo inválido, as macros, a assinatura digital (que
  deixaria de valer) e o campo que perdeu o começo ou o fim na edição. A miniatura de
  pré-visualização do arquivo não é mantida (mostraria o conteúdo antigo), com aviso sem
  confirmação.
- Notas de rodapé e de fim (0.1.10): a nota que não pode ser lida (sem marca no texto, marca
  no cabeçalho, no rodapé ou numa caixa de texto, danificada, acima de 5000 notas ou de
  1 MB) sai do arquivo ao salvar, com aviso e confirmação. Na tela, quando a área de notas
  empurra o texto, o parágrafo inteiro vai para a página seguinte (o Word parte o parágrafo e
  leva só as linhas que não cabem): sobra um espaço em branco no pé da página. Uma tabela que
  começou na página anterior não é empurrada: a nota que não cabe abaixo dela continua na
  página seguinte. As notas que vêm depois de uma nota que continua esperam a continuação
  dela. Formatos de número fora de 1, a, A, i, I e * aparecem em algarismos (o arquivo guarda o
  do Word); a posição "fim da seção" é o fim do documento; o aviso de
  continuação ("continua na próxima página") do Word não aparece. Copiar e colar entre dois
  processos do EditDoc, ou de/para outro programa, leva o texto sem a nota.
- Seções (0.1.12): o texto em **colunas** é preservado no arquivo, mas aparece em uma
  coluna só (aviso sem confirmação); a quebra de coluna fica no texto (aparece com as marcas de
  formatação). Numa seção mais baixa que a mais alta do documento (a página paisagem num
  documento em retrato), o parágrafo que não cabe no pé da página desce inteiro para a página
  seguinte (o Word parte o parágrafo), e a tabela desce a partir da linha que não cabe. A seção
  contínua com papel diferente começa numa página nova (como o Word). A página em branco de
  "Página par/ímpar" segue a numeração que continua (com reinício de numeração, a que a página
  teria sem ele). Objeto flutuante à direita numa seção mais estreita que a mais larga fica na
  largura da mais larga. Copiar e colar não leva a quebra de seção (o texto vai). Desfazer não
  desfaz a troca de papel, orientação e margens (como antes da 0.1.12), nem "Vincular ao
  anterior".
- Controle de alterações (0.1.13; 0.1.14): rejeitar não desfaz a **mescla** de células
  (w:cellMerge), nem a célula inserida sozinha numa linha (a grade ficaria torta), nem a
  numeração antiga gravada só como texto (w:numberingChange): elas ficam, e a mensagem diz
  quantas; as bordas que vinham do estilo da tabela antes da alteração não voltam (as declaradas
  na tabela, sim); desfazer a rejeição da seção da última página não desfaz o papel e as
  margens (como na 0.1.12). Recortar e colar vira **movido** só dentro de um parágrafo, fora de
  tabela e sem marcadores no trecho; o resto continua exclusão e inserção. Em **Sem marcação**, o parágrafo cuja marca foi
  excluída e que ainda tem texto continua numa linha própria (o Word junta com o de baixo), uma
  tabulação ou quebra de linha dentro do texto excluído continua ocupando espaço, e a imagem
  excluída continua aparecendo; em **Original** a formatação de parágrafo de antes não aparece.
  As alterações dentro de um comentário ou de uma caixa de texto são preservadas, mas não se
  aceitam nem rejeitam no EditDoc; as das notas, na edição da nota. O comentário impresso na
  margem é texto pequeno ao lado do trecho, não um balão.
- Paginação (0.1.18): uma quebra de página que o Word põe porque o parágrafo não cabe deixa de
  ir e voltar a cada tecla; a página não muda de lugar sem motivo. O arquivo gravado é o mesmo.
- Imagens (0.1.18): uma imagem reduzida na página sai suavizada, sem serrilhado nas linhas finas.
- Paginação (0.1.17): mais perto da do Word, mas não idêntica. Desde a 0.1.17 a tela soma o
  espaço depois de um parágrafo e o espaço antes do seguinte, respeita "não adicionar espaço
  entre parágrafos do mesmo estilo", usa a altura de linha do Word (com o espaço externo da
  fonte: Arial e Times ficam 3 % a 4 % mais altos), mostra o parágrafo vazio junto de uma tabela
  e aplica o controle de linhas viúvas e órfãs, "manter com o próximo", "manter linhas juntas" e
  "quebra de página antes" do estilo. Ficam diferentes: a viúva de um parágrafo com três linhas ou
  mais na página de cima (o Word desce uma linha; o EditDoc deixa como está), a altura das
  linhas de tabela e o espaço no começo e no fim de uma célula, e uma quebra de página seguida de
  uma quebra de seção "próxima página" (o EditDoc mostra uma página a mais). Nada disso muda o
  arquivo gravado, que reabre com a mesma paginação de quando foi aberto.
- O sumário (e os outros campos) não são recalculados pelo EditDoc: abra no Word e
  atualize (F9) se o texto mudou. O controle de conteúdo que envolve uma linha ou uma
  célula inteira de tabela ainda é achatado, com aviso (o texto fica). Apagar só o começo
  ou só o fim de um controle de conteúdo tira o controle ao salvar, com aviso.
- Formatação: o filho de propriedade que o formato não define (arquivo de outro programa) sai,
  com aviso (as revisões de formatação são preservadas desde a 0.1.13, menos as de dentro de um
  estilo); a formatação do código de um campo (o
  texto escondido entre o começo e o separador) segue a do começo do campo. Tabulação:
  na primeira linha com recuo próprio a parada aparece deslocada desse recuo.
- Objetos flutuantes (0.1.7): o texto contorna o objeto por um lado só (o maior, ou o que
  o arquivo pede), e a faixa reservada começa na linha do parágrafo onde o objeto está
  preso (o texto acima dela não contorna); "Justo" e "Através" seguem o retângulo, não o
  desenho; dois objetos presos no mesmo parágrafo reservam juntos a faixa de cada lado.
  Formas fora do conjunto básico aparecem como retângulo com as
  cores, e o gráfico e o SmartArt como um quadro do tamanho certo (ou a imagem de
  reserva, quando o arquivo tem).
- Mover e redimensionar (0.1.9): a posição fica entre -55,88 e +55,88 cm da referência e
  o tamanho entre 1 pixel e 176 cm (o maior papel); a linha reta continua com altura zero. A
  âncora só muda de parágrafo no corpo, fora de tabela e sem a âncora travada; no cabeçalho,
  no rodapé, numa tabela, ou com a âncora travada, o objeto arrastado para outra página fica
  na página da âncora, na altura onde foi solto (relativo à página). As setas nunca mudam a
  âncora. Redimensionar um objeto de tamanho relativo (porcentagem da página) o deixa com
  tamanho fixo. "Comprimido" e "Através" gravam o polígono retangular padrão (a tela já os
  trata como Quadrado). A imagem flutuante que vai para "Alinhado ao texto" vira imagem do
  EditDoc; se ela estiver girada, espelhada, com borda ou efeito, a troca é recusada (o Word
  faz isso sem perda). A cópia VML que o Word guarda junto do desenho (para programas antigos)
  acompanha a posição e o tamanho em pontos, com duas casas.
- Objetos preservados: copiar e colar dentro do EditDoc leva o texto em volta, mas não o
  objeto (a barra de status avisa); uma nota de rodapé ou um comentário **dentro** de uma
  caixa de texto perdem a referência ao salvar (com aviso), porque o EditDoc não os lê dali. A lista numerada dentro da caixa volta (desde a 0.1.4).
- Fora desta versão: revisão com controle de alterações,
  gerar ou atualizar sumário e índices, mala direta, editar equações e formas (elas são
  preservadas, não editadas; o texto das caixas de texto se edita desde a 0.1.5), texto em colunas na tela (preservado no arquivo), ortografia, `.doc`, RTF,
  ODT e macros (nunca).
- Numeração de listas: o EditDoc não edita a definição de uma lista do arquivo (fonte,
  recuo ou texto do número de um nível); a galeria cria definições novas. A tabulação depois do número
  usa as paradas do nível e a padrão do documento, não as tabulações próprias do parágrafo.
  Num documento com milhares de itens, Enter e Backspace entre parágrafos levam mais
  (medido: 50 ms com 3000 itens), porque a numeração é recalculada.
- Tabelas: digitar numa tabela muito grande fica lento (o Qt refaz a tabela a cada tecla;
  acima de 5000 células a tabela abre como parágrafos, com aviso); a altura de linha do
  arquivo é guardada, mas a tela não a aplica; "Dividir células" só desfaz mescla.
- A quebra de página não acompanha a do Word linha a linha (não há viúva e órfã, e a
  medida das fontes é a do Qt). O número de páginas pode diferir em documentos longos.
- Cabeçalho e rodapé que passam da margem (desde a 0.1.8): o corpo de cada página começa
  onde termina o cabeçalho dela (primeira página, par ou ímpar), como no Word, na tela, no
  PDF e na impressão. O que ainda não segue o Word: a altura do corpo é a mesma em todas as
  páginas (a da página com o maior cabeçalho e o maior rodapé), então na página de
  cabeçalho menor o corpo termina mais acima e cabe a mesma quantidade de texto que nas
  outras.
- Digitação: num documento longo, digitar perto do começo custa mais que no fim (o Qt
  refaz a posição dos parágrafos de baixo a cada tecla; medido: 7 ms por tecla no 1º de
  600 parágrafos).
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
`dist\EditDoc-0.1.19-win64.zip`. Se qualquer etapa falhar, nada é entregue.

O plano e as decisões estão em [docs/ARQUITETURA.md](docs/ARQUITETURA.md), as medições em
[docs/SPIKES.md](docs/SPIKES.md), e o guia para quem quer contribuir em
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licença

MIT. Ver [LICENSE](LICENSE). Os componentes de terceiros estão listados em
[AVISOS_DE_TERCEIROS.md](AVISOS_DE_TERCEIROS.md).
