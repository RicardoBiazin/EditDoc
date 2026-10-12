## 0.0.8 - 2026-10-12

Cabeçalho, rodapé e número de página (M5). O cabeçalho e o rodapé abrem do `.docx`, aparecem
em cada página, são editados no lugar e voltam ao arquivo, com o número da página certo em
cada folha.

- Cabeçalho e rodapé no `.docx`: leitura e escrita das partes `word/headerN.xml` e
  `word/footerN.xml`, com relação, referência no `sectPr` e tipo de conteúdo próprios. Três
  variantes: padrão, primeira página (`w:titlePg`) e páginas pares (`w:evenAndOddHeaders`, no
  `settings.xml`). Distâncias do cabeçalho e do rodapé (`w:pgMar`). O conteúdo é o mesmo do
  corpo: parágrafos formatados, listas, tabelas e imagens na linha (cada parte com as suas
  relações).
- Campos PAGE e NUMPAGES: lidos como campo simples (`w:fldSimple`) ou complexo (`w:fldChar` e
  `w:instrText`), no corpo, no cabeçalho e no rodapé. Gravados como campo complexo, como o
  Word grava: no Word continuam campos. Formato do número (`w:pgNumType`: 1, 2, 3; i, ii, iii;
  I, II, III; a, b, c; A, B, C), opção `\*` da instrução e número inicial (`w:start`).
- Na tela: o cabeçalho e o rodapé são pintados na margem de cada página, em cinza claro, com o
  número daquela página; o total acompanha a paginação. Se o cabeçalho (ou o rodapé) passa da
  margem, o corpo desce, como no Word.
- Edição no lugar: duplo clique no alto ou no pé da página entra na edição (o corpo esmaece, e
  uma linha tracejada com o rótulo "Cabeçalho", "Rodapé", "Primeira página", "Página par" ou
  "Página ímpar" marca a área). Clique no cabeçalho ou rodapé de outra página troca de área.
  Duplo clique no corpo, Esc ou "Fechar cabeçalho e rodapé" voltam ao corpo, com o cursor onde
  estava. Formatação, tabela, imagem e localizar funcionam dentro do cabeçalho. Desfazer e
  refazer têm uma pilha própria em cada cabeçalho e rodapé.
- Faixa: na aba Inserir, os botões Cabeçalho (editar, remover), Rodapé (editar, remover) e
  Número de Página (início ou fim da página, à esquerda, centralizado ou à direita; "Página X
  de Y"; número da página atual e total de páginas no cursor; formato; começar em...). Durante
  a edição aparece a aba "Cabeçalho e Rodapé", com "Primeira página diferente", "Páginas pares
  e ímpares diferentes", ir para o cabeçalho ou o rodapé e "Fechar cabeçalho e rodapé".
- Avisos novos: CABECALHO_SECAO (seções com cabeçalhos diferentes: fica o da última seção,
  com a herança do Word), CABECALHO_GRANDE (parte acima do limite), CABECALHO_RODAPE agora só
  para referência quebrada ou parte danificada, e NUMERO_PAGINA (formato de numeração que o
  EditDoc não mostra). O aviso CAMPO passou a valer só para os campos que não são número de
  página (data, sumário, referência), que ficam com o último valor mostrado, como texto.
- Limites contra arquivo hostil: parte de cabeçalho ou rodapé acima de 4 MB não é lida (com
  aviso); só as partes da última seção são abertas (400 seções com cabeçalho abrem em 0,01 s);
  campo aninhado mais de 8 níveis, ou com instrução acima de 255 caracteres, não é interpretado.
- O validador do pacote confere também as partes de cabeçalho e rodapé (ordem, `xml:space`,
  parágrafo final, `r:id`), a ordem dos filhos do `sectPr` e o equilíbrio dos `fldChar`. A
  conferência do arquivo gravado compara cabeçalhos, rodapés e campos.

Limites deste marco: uma seção só; a altura do cabeçalho que empurra o corpo é a mesma em
todas as páginas (a maior das variantes), ao contrário do Word, que ajusta página a página.
Copiar e colar um campo leva só o texto ao redor. Campo de página no corpo ocupa a largura do
maior número do documento. "Número de Página" acrescenta um parágrafo ao cabeçalho que já tem
texto (o Word troca o conteúdo). A abertura no Word ainda depende de conferência manual
(amostra em `tests/saida/amostra_m5_cabecalho_rodape.docx`, gerada pela suíte).

## 0.0.7 - 2026-10-12

Tabelas e imagens (M4). Tabela e imagem na linha do texto abrem do `.docx`, aparecem na visão
em páginas, são editadas e voltam ao arquivo. A aba Inserir é nova.

- Tabelas: leitura e escrita de `w:tbl` com grade (`w:tblGrid`), mescla horizontal
  (`w:gridSpan`, e o `w:hMerge` antigo) e vertical (`w:vMerge`), bordas da tabela e da célula
  (simples, dupla, pontilhada, tracejada, nenhuma), sombreamento, alinhamento vertical, linha de
  cabeçalho (repete no alto de cada página), altura da linha e tabela dentro de tabela. As
  bordas do estilo da tabela (o "Table Grid" do Word) são lidas; toda tabela sai com o estilo
  "Table Grid" e os seis lados da borda gravados nela mesma.
- Aba Inserir: botão Tabela com a grade de escolha (até 10 x 8) e o diálogo "Inserir tabela...";
  inserir linha acima e abaixo, coluna à esquerda e à direita; excluir linha, coluna e tabela;
  mesclar e dividir células. Os comandos de tabela também ficam no menu de contexto, e só
  habilitam com o cursor numa tabela.
- Teclado na tabela: Tab vai para a próxima célula e seleciona o conteúdo, Shift+Tab volta,
  Tab na última célula cria uma linha, Ctrl+Tab insere tabulação. Ctrl+Enter dentro da célula
  vira Enter comum.
- Imagens na linha do texto: PNG, JPEG, GIF e BMP, no tamanho do arquivo (`wp:extent`), com o
  texto alternativo. Os bytes da imagem voltam ao `.docx` sem recodificar, em `word/media`,
  com relação e tipo de conteúdo; imagens iguais dividem uma parte.
- Inserir imagem de arquivo (aba Inserir), colar imagem da área de transferência, clicar na
  imagem para selecioná-la, redimensionar pelas alças dos cantos ou pelo diálogo "Tamanho da
  imagem" em centímetros, com a proporção travada. Copiar a imagem leva a imagem para outros
  programas.
- Avisos novos: imagem flutuante (`wp:anchor`) vira imagem na linha, sem perder a imagem;
  formato que o EditDoc não mostra (EMF, WMF, TIFF, SVG, VML, imagem vinculada) sai com aviso;
  quebra de página dentro de célula vira quebra de linha; texto escondido em célula mesclada.
- Limites contra arquivo hostil: tabela com mais de 2000 linhas, 63 colunas ou 5000 células,
  ou aninhada mais de 4 níveis, vira parágrafos com aviso (nenhum texto se perde). Imagem acima
  de 64 megapixels (ou 30000 px num lado) não é decodificada: fica no arquivo e aparece como um
  quadro cinza. A tela recebe uma prévia de no máximo 1800 px no lado maior.
- Desfazer e refazer: cada comando de tabela, a inserção de tabela e de imagem, colar e o
  redimensionamento são um passo de desfazer.
- Defeito corrigido: equação (`m:oMath`) era descartada sem aviso, porque o leitor só olhava o
  namespace `w:`. Agora gera o aviso EQUACAO.
- O validador do pacote confere também a ordem de `tblPr`, `tcPr` e das bordas, a célula que
  não termina em parágrafo, a linha que não ocupa a grade inteira, o corpo que termina em
  tabela e o `wp:docPr` repetido. A conferência do arquivo gravado compara tabelas, células,
  mesclas e os bytes das imagens.

Limites deste marco: digitar numa tabela grande é lento, porque o Qt refaz a tabela inteira a
cada tecla (cerca de 0,06 ms por célula: 300 ms com 5000 células). A altura de linha fica no
arquivo, mas a tela não a aplica. Tabela mais larga que o corpo é cortada na tela na margem.
"Dividir células" só desfaz mescla (não divide uma célula simples em várias). Uma tabela
copiada e colada no EditDoc volta com a grade padrão (as bordas próprias se perdem na cópia).
Uma linha vazia aparece na tela antes de uma tabela no começo do documento ou entre duas
tabelas; ela não vai para o arquivo. A abertura no Word ainda depende de conferência manual
(amostra em `tests/saida/amostra_m4_tabelas_imagens.docx`, gerada pela suíte).

## 0.0.6 - 2026-10-12

Visão em páginas (M3). O documento aparece em folhas com margens, régua, quebras de página,
zoom e "Página X de Y" na barra de status. A visão deixou de ser um QTextEdit; a API de edição
continua a mesma para os comandos.

- Folhas sobre fundo cinza, com vão e sombra. O texto ocupa só o corpo, e o número de páginas é o
  mesmo entre carregar um arquivo e redigitá-lo.
- Layout (aba nova): papel A4, Carta e Ofício; retrato e paisagem; margens Normal, Estreita,
  Moderada, Larga e Personalizadas, em centímetros. Papel, orientação e margens são gravados no
  `sectPr` e lidos de volta ao abrir.
- O aviso PAGINA só aparece quando o arquivo tem mais de uma seção. Papel ou margem que não cabem
  numa página útil geram o aviso PAPEL_INVALIDO, e o arquivo sai com A4 e margens padrão.
- Régua: mostra as margens e os recuos do parágrafo do cursor. Arrastar um marcador muda o recuo, e
  o arrasto inteiro é um passo de desfazer.
- Quebra de página (Ctrl+Enter, aba Layout): vai e volta pelo `.docx` como `w:br w:type="page"`, sem
  aviso, e aparece na tela como linha tracejada.
- Zoom: Ctrl+roda, controle na barra de status e botões de menos e mais. O zoom máximo depende da
  escala da tela: 300% com DPR 1, 200% com DPR 1,5 e 150% com DPR 2. Acima disso o Qt pinta o texto
  devagar demais (medido no Gate do M3, em docs/SPIKES.md).
- Barra de status: "Página X de Y", da página onde está o cursor.
- Cache de páginas para a pintura, com invalidação por região. Trocar o zoom ou o papel refaz o
  cache; editar só refaz a parte afetada.

Limites deste marco: viúva e órfã, colunas, páginas pares e ímpares e seções com tamanhos
diferentes ficam para depois. Uma quebra no meio de um parágrafo, ao salvar, vira dois parágrafos
(a aparência não muda). Tabelas e imagens são dos M4 e M5. Com fonte de 16 pt ou mais, em 300%, a
digitação passa de 16 ms. A aparência real no Windows ainda depende de conferência manual.

## 0.0.5 - 2026-10-11

Abre e salva arquivos `.docx` de texto (M2). Tabelas, imagens, campos, cabeçalho e
rodapé ainda não são editados: quando o arquivo os tem, o programa avisa, e ao
salvar pede confirmação da perda.

- Leitura e escrita de `.docx` próprias, com lxml e zipfile, sem Word: parágrafos,
  negrito, itálico, sublinhado, tachado, subscrito, sobrescrito, tamanho, fonte,
  cor, alinhamento, recuos, espaçamento entre linhas e listas simples.
- Leitura defensiva: DOCTYPE recusado, limites de tamanho e de compressão, nomes
  de parte validados. Arquivo hostil vira mensagem em português, nunca traceback.
- Gravação atômica: o temporário (`.ewnew`) é relido do disco e conferido antes da
  troca. Falha em qualquer etapa deixa o original intacto.
- Uma janela por documento. Abrir um arquivo que já está aberto traz a janela para
  a frente. Menu Arquivo, com Abrir recente (até 15 itens).
- Barra de aviso para o que o programa não entende, com o botão Detalhes. Salvar
  com perda pede: salvar mesmo assim, salvar cópia ou cancelar.
- Fechar, ou sair, com alterações pendentes pergunta: salvar, descartar ou cancelar.
- Instância única: um segundo arquivo aberto pelo Explorer vai para a janela que já
  está aberta.
- `associar.ps1` associa `.docx` ao EditDoc em HKCU, sem trocar o programa padrão.
- `.doc`, `.docm` e `.dotx` são recusados com mensagem. Arquivo acima de 20 MB pede
  confirmação antes de abrir.

Limites deste marco: não há visão em páginas (M3). A abertura de um `.docx` gerado
pelo EditDoc no Word, sem reparo, ainda não foi verificada: não há Word nesta
máquina (pendência manual).

# Changelog

## 0.0.4 - 2026-10-11

Primeiro editor de fato (M1): edita, formata e localiza. Ainda nao abre nem
salva arquivos: isso chega no M2.

- Faixa de opcoes com a aba Pagina Inicial: Area de transferencia, Fonte,
  Paragrafo e Edicao, com desfazer e refazer no topo.
- Recolhimento responsivo: de 1920 a 820 px a faixa recolhe os grupos em ordem
  de prioridade, e nada fica cortado. A fonte e o tamanho nunca recolhem.
- Formatacao: negrito, italico, sublinhado, tachado, subscrito, sobrescrito,
  tamanho, familia, limpar formatacao, alinhamento, recuo e espacamento.
- Listas com marcadores e numeracao.
- Cada comando que muda o texto e' um passo de desfazer, mesmo em varios paragrafos.
- Localizar e substituir, com diferenciar maiusculas e palavra inteira.
- Barra de status com a contagem de palavras, atualizada depois de uma pausa.
- Atalhos no padrao do Word (Ctrl+B, Ctrl+E, Ctrl+F e outros), com a mesma
  definicao da faixa: um botao e um atalho nunca divergem.

Limites deste marco: uma aba, dois estados por grupo (o estado intermediario
chega no M6), a visao provisoria sobre QTextEdit (a visao em paginas chega no
M3) e sem icones.

## 0.0.3 - 2026-10-11

Spikes de viabilidade feitos antes do M1. Nenhuma mudança no programa: o código
novo fica em `spikes/`, fora do pacote `editdoc/`, do build e dos testes oficiais.

- Spike A, visão em páginas sobre QTextDocument: paginação, fronteiras, hit-test,
  WYSIWYG, desfazer, cabeçalho e rodapé, tabelas entre páginas, zoom e HiDPI. Passa
  com ressalvas: a pintura de um quadro fica no limite a 25% de zoom.
- Spike B, .docx com lxml: leitor e escritor próprios, ida-e-volta, validador de
  ordem e arquivos hostis. Passa com ressalvas: a abertura no Word não foi verificada.
- `docs/SPIKES.md`: resultados, decisões e pendências.

## 0.0.2 - 2026-10-11

Renomeado de EditWord para EditDoc. Nenhuma mudança de comportamento.

- Pacote Python `editdoc/`, executável `EditDoc.exe`, pasta `%APPDATA%\EditDoc` e
  identidade na barra de tarefas `RicardoBiazin.EditDoc`.
- Repositório no GitHub renomeado para `RicardoBiazin/EditDoc`. O endereço antigo
  continua redirecionando.
- Quem testou a 0.0.1 perde a configuração salva: ela ficava em
  `%APPDATA%\EditWord`, que a 0.0.2 não lê.

## 0.0.1 - 2026-10-11

Primeiro esqueleto do projeto. Ainda não edita nem abre documentos.

- Janela principal vazia, com título que traz a versão e ícone próprio.
- Pipeline de build: testes, PyInstaller, autoverificação do executável, fumaça
  (o executável abre a janela de verdade) e ZIP.
- Log em `%APPDATA%\EditDoc`, com captura de exceções não tratadas.
- Configuração JSON com gravação atômica.
