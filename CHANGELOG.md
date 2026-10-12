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
