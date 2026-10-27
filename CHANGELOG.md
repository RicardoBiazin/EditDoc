## 0.1.27 - 2026-10-27

Recuo esquerdo negativo e rodapé com tabela, como no Word. Até a 0.1.26 o parágrafo (ou a tabela)
com recuo esquerdo negativo, que entra na margem, aparecia na margem e com a linha da largura do
corpo: o texto justificado quebrava em mais linhas que no Word e cada página levava menos texto.
Agora ele começa onde o Word o põe, com a largura de linha do Word, na tela, no PDF e na impressão;
o clique, o cursor, a seleção, a régua, os objetos flutuantes, as notas e o cabeçalho e rodapé
ficam no lugar. E o rodapé (ou cabeçalho) com uma tabela seguida de parágrafo vazio tinha uma linha
a menos que no Word (o Qt esconde o vazio junto da tabela): o corpo da página ficava mais alto.

As duas correções entram juntas: só a do rodapé piorava o documento medido (26 para 27 páginas),
porque o recuo ignorado compensava o rodapé curto. O arquivo salvo não muda.

Medido (docs/SPIKES.md, "0.1.27"; oráculo `lastRenderedPageBreak` dos 14 `.docx` de Downloads,
Windows):
- doc_12: 26 páginas, acerto das quebras de 1/1 para 2/2 (as duas primeiras quebras no parágrafo e
  na linha do Word; Word: 24 páginas). Os outros 13 ficam iguais, quebra por quebra.
- A margem da tabela depois do parágrafo vazio entre tabelas (entrelinha sem a compensação, 10,9
  twips) foi corrigida e medida: não muda nenhuma quebra; não entrou.
- Regressão abrir-salvar-reabrir-salvar: c14n igual à 0.1.26 nos 14; salvo1 == salvo2 em todos.
- Desempenho (p95 da digitação, rodadas intercaladas): sem piora consistente (a direção inverte em
  todos os documentos).
- Suíte: 3459 verificações ok, 0 falhas; 27 novas em `teste_paginacao_word` (posição x e largura
  da linha com recuo negativo, tabela, caret, clique, régua, gravação; altura do rodapé com tabela e
  vazio), com contraprova (deslocamento desligado; sem o vazio escondido).

## 0.1.26 - 2026-10-27

Altura da linha de tabela (`w:trHeight`) na tela, no PDF e na impressão. Até a 0.1.25 a altura que o
arquivo pede para a linha era guardada, mas a tela mostrava só a altura do texto: uma linha de
cabeçalho com "pelo menos 0,8 cm" aparecia com a altura de uma linha de texto. Agora a linha "pelo
menos" (e a "exatamente", quando o texto cabe) tem a altura do arquivo, com o texto no alto, no meio
ou embaixo, como o alinhamento vertical da célula pede; a "automática" continua com a altura do texto.

O arquivo salvo não muda nos documentos medidos. Uma correção no salvar: a linha com altura
"automática" (`hRule="auto"`) era gravada como "pelo menos" (`atLeast`); agora volta como veio.

Medido (docs/SPIKES.md, "0.1.26"; oráculo `lastRenderedPageBreak` dos 14 `.docx` de Downloads,
Windows):
- Os 14 ficam iguais à 0.1.25 em páginas e em acerto das quebras (doc_12: 26 páginas, 1/1). A altura
  das linhas não era a causa da primeira quebra do doc_12: com ela, o parágrafo da divisa ainda cabe
  na página 1 (faltam 98 twips).
- Espaço antes do primeiro e depois do último parágrafo da célula: medido e não adotado (o doc_14
  piora de 3/3 para 2/2).
- Viúva de três linhas ou mais (descer uma linha): o protótipo resolveu 5 dos 8 casos dos 14
  arquivos, mas não mudou nenhuma quebra do oráculo; não entrou.
- Regressão abrir-salvar-reabrir-salvar: c14n igual à 0.1.25 nos 14; salvo1 == salvo2 em todos.
- Desempenho (p95 da digitação, 3 rodadas intercaladas): sem piora consistente (-1,31 a +1,02 ms). A
  ressalva da 0.1.25 (documento simples +0,4 a +1 ms) era ruído: o documento simples não tem tabela,
  e a 0.1.24 contra a 0.1.25 deu -0,09 a +1,42 ms sem direção.
- Suíte: 3432 verificações ok, 0 falhas; 16 novas em `teste_paginacao_word` (`testar_altura_da_linha`),
  com contraprova (sem a altura na tela, 7 falham).

## 0.1.25 - 2026-10-24

Fidelidade de paginação em tabelas: a margem interna de cada célula (`w:tcMar`) passa a valer na
tela. Antes só valia a margem da tabela (`w:tblCellMar`), e a célula que traz a sua própria
(topo, base, esquerda, direita) ficava com a margem errada: a tabela ficava mais curta que a do
Word, e a quebra de página caía depois do ponto onde o Word a põe. Nenhuma mudança no arquivo
salvo: o `w:tcMar` continua nos extras da célula e volta como veio.

Medido (docs/SPIKES.md, "0.1.25"; oráculo `lastRenderedPageBreak` sobre os 14 `.docx` de Downloads,
Windows):
- Um arquivo (doc_14) passa de 13 para 14 páginas, igual às 14 do Word; o acerto das quebras sobe de
  1/1 para 3/3 (mesmo parágrafo / mesma linha). Os outros 13 arquivos ficam iguais, em páginas e em acerto.
- Regressão abrir-salvar-reabrir-salvar: c14n igual à 0.1.24 nos 14.
- Suíte: 6 verificações novas em `teste_paginacao_word` (margem de célula, com contraprova: sem a
  correção, 3 falham).

Não entrou (diagnosticado, fica para a próxima versão): altura mínima de linha (`w:trHeight`), que a
tela ignora; espaço antes do primeiro e depois do último parágrafo da célula, que o Qt não aplica;
e a viúva de três linhas ou mais.

## 0.1.24 - 2026-10-24

Higiene do repositório: os scripts de medição em `spikes/` apontavam para uma pasta de
rascunho com o nome de usuário do Windows no caminho. Agora usam a pasta temporária do
sistema (`tempfile.gettempdir()`). Nenhuma mudança no programa.

## 0.1.23 - 2026-10-24

Atualização de dependência: PySide6 (Essentials) de 6.11.2 para 6.12.0, fixada em `requirements.txt`.
Sem mudança de código. Nada muda no que o usuário vê, no arquivo salvo nem nas páginas.

Medido (docs/SPIKES.md, "0.1.23"):
- Suíte completa: 3411 verificações ok, 0 falhas, igual à 0.1.22.
- Build com 6.12.0: BUILD OK, autoverificação "EditDoc 0.1.23", fumaça de janela e ZIP ok.
- Páginas dos 14 .docx de Downloads (oráculo `lastRenderedPageBreak`): iguais à 0.1.22 em todos, com o mesmo
  acerto das quebras. O SIM continua em 13 páginas (o Word dá 14, pela fonte Aptos ausente nesta máquina).
- Regressão abrir-salvar-reabrir-salvar nos 14: c14n igual à 0.1.22 e mesmas páginas.
- Desempenho (p95 da digitação, 3 rodadas intercaladas): diferença de -0,52 a +0,42 ms, dentro do ruído,
  abaixo do limite de 1,5 ms.

Nenhuma armadilha nova: nada quebrou com a 6.12. O procedimento para testar outra versão do Qt está em CLAUDE.md.

## 0.1.22 - 2026-10-22

Correção da página em branco antes da quebra de seção. Um parágrafo que só tem a quebra de página
(`w:br type="page"`) seguido do parágrafo com o `w:sectPr` (quebra de seção "próxima página") gerava
duas quebras seguidas no Qt: o parágrafo da quebra começava uma página e a seção seguinte começava
na outra. O Word deixa o parágrafo da quebra e o da seção na página de cima, e a seção seguinte na
página de baixo. No documento de referência (SIM, 15 páginas na 0.1.20, com a Aptos ausente nesta
máquina) isso era a página em branco entre a capa e o sumário.

O que mudou: a quebra de página do parágrafo que só tem a quebra fica no FIM dele (`PageBreak_AlwaysAfter`,
não mais no começo). Quando o parágrafo de cima da quebra de seção é só a quebra do usuário, a quebra
derivada da seção não entra (a quebra do usuário já termina a página). Um bloco que vem depois de uma
quebra do usuário no fim do parágrafo não recebe quebra das regras do Word (senão a página em branco
voltava). O arquivo gravado não muda: o parágrafo só com a quebra continua com o `w:br type="page"`
no mesmo lugar, e a releitura dá o mesmo modelo. Texto digitado num parágrafo que tem a quebra no fim
vira dois parágrafos ao gravar (o texto e, depois, o parágrafo só com a quebra), e a tela mostra a
mesma coisa.

Medido (docs/SPIKES.md, "0.1.22"): dos 14 .docx de Downloads, só o SIM muda, de 15 para 13 páginas
(Word: 14, com a fonte Aptos ausente aqui); o acerto das quebras no SIM vai de 0/0 para 1/1. Nos
outros 13 a contagem e o acerto são os mesmos, e o arquivo salvo tem o mesmo c14n da 0.1.20 nos 14.

Testes: `teste_quebras` ganhou cinco verificações de paginação e de tela (quebra só no fim, só no
meio, antes de seção, quebra normal, Enter, copiar, colar, rótulo e digitar), com contraprovas. A
suíte tem 3411 verificações (3391 da base e 20 novas). O gate de desempenho ficou dentro do ruído
(docs/SPIKES.md, "0.1.22").

## 0.1.20 - 2026-10-22

Refatoração interna, sem mudança de comportamento. Primeiro passo do caminho para colunas de texto
(docs/SPIKES.md, "0.1.19"): a folha (a página impressa ou visível, com cabeçalho, rodapé e margens
da seção) fica separada da página do Qt (a unidade de paginação do QTextDocument). Hoje as duas são
a mesma coisa, e essa identidade mora numa única camada, `modelo/folhas.MapaFolhas`, exposta como
`LayoutPaginado.mapa`. Cursor, clique, tiles, desenho da folha, objetos flutuantes, notas, campos,
paginação (0.1.17 e 0.1.18), seção contínua, impressão e PDF passam por ela, e nenhum deles usa mais
`n * hb` ou `floor(y / hb)` direto.

Nada muda na tela, no PDF, na impressão ou no arquivo salvo. A suíte tem 3391 verificações (3384 da
base e 7 da camada, com contraprova). Os .docx de regressão abrem, salvam, reabrem e salvam com as
mesmas páginas e o mesmo c14n da 0.1.19. O gate de desempenho ficou dentro do ruído (docs/SPIKES.md,
"0.1.20").

Testes: `teste_paginas` ganhou `testar_folhas_qt`. `teste_notas` chamava `_medir`, `_linhas_da_pagina`
e `_distribuir` com o argumento `hb`, que saiu da assinatura privada (a altura vem da camada); as
verificações são as mesmas.

## 0.1.19 - 2026-10-22

A faixa amarela de avisos só aparece quando salvar faria o arquivo perder algo. Antes ela listava
tudo o que o EditDoc não edita, inclusive recursos preservados sem perda (caixas de texto, formas,
equações, imagens flutuantes, objetos opacos, revisões preservadas), e o aviso parecia um problema
a resolver. Agora a faixa mostra só os avisos com perda ao salvar, os que o Salvar já pede para
confirmar (quebra de tipo desconhecido, nota ilegível, controle de conteúdo achatado, formatação
não preservada...).

Decisão de UX: os avisos sem perda não geram faixa; ficam na lista completa, que abre pelo botão
Detalhes (quando a faixa aparece) e por Arquivo > Objetos preservados (item novo, que abre a mesma
caixa). A lista separa os dois grupos: "Sai do arquivo ao salvar" e "Não se perdem ao salvar".
Avisos de só leitura (uma caixa de texto com tabela dentro, por exemplo) seguem a mesma regra: não
perdem nada ao salvar, então ficam só na lista. Depois de um salvamento, a faixa some e a lista
mantém o que continua no arquivo (o que só era preservado).

Testes: `teste_documento` ganhou `testar_faixa_so_com_perda` (documento só com objetos preservados
não mostra faixa e o item do menu abre a lista; com perda, a faixa mostra a quebra e não a equação;
depois do salvamento, a faixa some e a equação continua na lista). Três expectativas antigas
mudaram de lugar, sem retirar verificação: a faixa não fala mais da equação (`teste_documento`), a
faixa de caixas de texto não aparece (`teste_objetos_opacos`) e o texto da lista completa é checado
no lugar da faixa.

## 0.1.18 - 2026-10-22

Histerese da quebra de página do motivo 3 ("o parágrafo começa a página por não caber"). Antes,
a quebra ligava e desligava a cada tecla quando o layout da página de cima mudava: num plano real
o mesmo parágrafo ia e voltava até 4 vezes numa tecla. Agora a quebra liga só se o parágrafo
precisa descer e desliga só com 720 twips de folga no pé da página de cima. Nada muda no arquivo
gravado; o oráculo do Word (quebras e páginas dos `.docx` de teste) fica igual.

Medido (docs/SPIKES.md, "0.1.18"): numa tecla do plano real, as mudanças de quebra caíram de 9
para 6 e o ida e volta no mesmo parágrafo sumiu. Os picos de tempo continuam acima do que a meta
pedia (16 ms): o custo por mudança é do relayout do Qt, e a saída para isso é decidir as quebras
sem o Qt (não feito nesta versão).

Qualidade de imagem: uma imagem reduzida na página saía serrilhada (listras finas viravam 0 % ou
100 % de tinta por coluna). O corpo agora pinta com `SmoothPixmapTransform`. O custo no gate ficou
dentro do ruído (SPIKES, "0.1.18"). O teste `testar_reducao_suave` (tests/teste_imagens.py) mede o
desvio na tela e tem contraprova sem a suavização.

## 0.1.17 - 2026-10-16

Paginação mais perto da do Word, medida contra o próprio Word: cada `w:lastRenderedPageBreak` que
o Word grava diz onde ele começou uma página, e o EditDoc passou a quebrar nos mesmos lugares em
mais arquivos.

Medição (12 `.docx` reais, cópias em memória, no Windows real e no offscreen; docs/SPIKES.md,
"0.1.17"): nos arquivos com as marcas do Word e com as fontes que existem na máquina, a página
do EditDoc começava no parágrafo do Word em 0 de 28 quebras; agora em 6, e o texto da quebra
está na página certa em 10 (antes, 0). Dois arquivos passam a ter as páginas do Word (3 × 3 e
4 × 4 com as quebras na mesma linha); o manual vai de 52 a 49 (o `app.xml` diz 48, de uma
gravação antiga do Word); o de 24 páginas, de 27 a 26.

Causas achadas e corrigidas (só no layout: tela, PDF e impressão; nada muda no arquivo gravado):

- altura da linha: o Qt usa a ascendente e a descendente da fonte (também na plataforma
  `windows`); o Word soma o espaço externo (o lineGap do hhea que passa da altura do OS/2): Arial
  12 tem 268 twips no Qt e 276 no Word. A entrelinha leva a razão Word/Qt da família, medida nas
  tabelas da fonte;
- a imagem na linha com entrelinha múltipla: o Qt multiplicava a linha da imagem (1,5 vez a
  imagem); o Word multiplica a linha do texto;
- o parágrafo vazio logo antes e logo depois de uma tabela, que o Qt escondia, ocupa a altura
  dele; os espaços que o Qt ignora junto da tabela (depois do parágrafo de cima, antes do de
  baixo) vão para as margens do quadro;
- o parágrafo vazio tem a altura da fonte da marca de parágrafo (`w:pPr/w:rPr`), não a do
  docDefaults;
- espaço entre parágrafos somado (o Qt usa o maior), com o `contextualSpacing` entre parágrafos
  do mesmo estilo; depois de uma quebra do usuário, só o espaço antes;
- controle de linhas viúvas e órfãs (ligado por padrão), manter linhas juntas, manter com o
  próximo (a cadeia inteira), quebra de página antes vinda do estilo e o espaço antes no alto da
  página (o Qt o perdia em parte): o parágrafo desce com uma quebra que não é do usuário
  (`PROP_QUEBRA_REGRA`), tirada quando ele voltaria a caber.

Como: `ConjuntoDePaginacao` (`interface/paginacao.py`) mantém em dia, no formato dos blocos e das
tabelas, a compensação (só o trecho editado e os vizinhos) e as regras (da página editada até a
página começar como antes), num passo anotado do desfazer como os das seções e das notas. O valor
de verdade de cada espaço e entrelinha fica numa propriedade (`ponte_qt/paginacao.py`, UserProperty
+ 45 a + 49) e é o que o `de_qt`, a faixa, a régua e o copiar leem. A tela passou a refazer tudo
abaixo quando o bloco de baixo (ou a base da tabela) se move com a altura do documento igual: uma
quebra mais abaixo segura o resto, e os itens de baixo ficavam velhos na tela.

Ficam diferentes (docs/ARQUITETURA.md): a viúva de três linhas ou mais em cima (o Word desce uma
linha), a altura das linhas de tabela e o espaço no começo e no fim da célula, a quebra de página
seguida de quebra de seção "próxima página" (uma página a mais), cabeçalho, rodapé e notas sem
compensação.

Desempenho: 0,7 a 2,5 ms por tecla (compensação e regras); uma tecla em 40 que muda uma quebra das
regras refaz o layout de baixo. Gate (p95, mediana de 3, 0.1.16 → 0.1.17): capa 15,5 → 18,3,
sumário 18,0 → 20,3, corpo 13,1 → 14,1, antes da capa 26,1 → 27,6, 2000 revisões 13,8 → 14,4; o
documento simples de referência 8,9 → 11,6; plano (pintura) 7,3 → 13,3 (a tecla do Qt continua a
exceção conhecida). Dentro do critério do teste.

Regressão nos 12 `.docx` reais (abrir → salvar como → reabrir → salvar → reabrir, no Windows):
todos gravam, conferência e validador passam, sem diferença c14n entre a 1ª e a 2ª gravação,
mesmas páginas nas três aberturas.

Testes: suíte nova `teste_paginacao_word` (fixtures geradas em código, cada regra com contraprova:
linha da fonte, espaço somado, `contextualSpacing`, viúvas e órfãs, `keepLines`, `keepNext` e a
cadeia, `pageBreakBefore` do estilo, espaço no alto da página e depois da quebra do usuário,
vazio e espaços junto da tabela, imagem com entrelinha 1,5, marca de parágrafo, arquivo gravado
igual com e sem a compensação, desfazer e copiar; oráculo com `lastRenderedPageBreak` sintético
num modelo simples do Word: 9 de 9 quebras certas, 0 sem a compensação; custo por tecla).
Contraprovas novas na vista (`teste_pintura_parcial`: o bloco de baixo; `teste_desempenho`: a base
da tabela). Verificações reescritas, sem tirar nenhuma: `teste_limites` lê o espaço depois pelo
valor de verdade (o formato tem a soma no de baixo); `teste_zoom` compara com o layout já assentado
(as regras ajustam na primeira pintura); `teste_desempenho` tira o controle de viúvas da fixture
do objeto flutuante (senão o parágrafo desceria inteiro e a linha estreita não desceria sozinha);
`teste_fidelidade` passa a acusar o arquivo do escritor antigo pelo layout do texto (a imagem da
altura da página continua cabendo, como no Word); a contraprova dos números de lista de
`teste_pintura_parcial` desliga a compensação (sair da lista refaz o formato e limpa o cache, o
que esconderia o número velho).

## 0.1.16 - 2026-10-15

O arquivo sem `styles.xml` (gerado por conversores de PDF e outros programas) volta do EditDoc
com a mesma paginação; a conferência pós-gravação passa a comparar a formatação que muda o
layout.

Defeito: um `.docx` real só com o `document.xml` (sem `styles.xml` e sem `settings.xml`) abria
com 4 páginas e, salvo pelo EditDoc, reabria com 6 (já na 0.1.14), com a conferência e o
validador passando. Causa: sem `styles.xml` o leitor deixava o docDefaults vazio (sem espaço
entre parágrafos, entrelinha simples, fonte da preferência), mas o escritor gravava para esse
catálogo o docDefaults do documento novo (8 pt depois, entrelinha 1,08, Calibri 11). Relido, todo
parágrafo fora de tabela ganhava os 8 pt e o 1,08, e a imagem da altura da página deixava de
caber. O diff c14n entre a 1ª e a 2ª gravação era vazio (o erro estava na 1ª), e a conferência
só comparava estrutura, texto, estilos e objetos, nunca a formatação efetiva.

Correção, na origem:

- sem `styles.xml`, o leitor usa o docDefaults que o Word usa nesse caso (Times New Roman 10,
  sem espaço entre parágrafos, entrelinha simples; `catalogo_sem_estilos`), e o escritor grava
  o docDefaults do catálogo ao pé da letra (`xml_base(..., paragrafo)`). O arquivo salvo traz
  `w:after="0" w:line="240"` e a fonte, e reabre igual;
- o catálogo explícito sem espaçamento vai ao arquivo sem `w:spacing` (antes: 8 pt e 1,08); o
  `Documento` sem catálogo (montado em código) continua com 8 pt e 1,08 (`catalogo_sem_catalogo`),
  e a conferência usa o mesmo catálogo;
- sem `settings.xml`, a tabulação padrão gravada é a que o leitor supôs (720, a da lista), não
  708.

Conferência fortalecida: de cada parágrafo do corpo, do cabeçalho e do rodapé, a formatação
efetiva resolvida como a tela e o escritor resolvem (docDefaults fora da tabela, cadeia do
estilo, recuo do nível da lista e formatação direta): alinhamento, recuos, espaços, entrelinha e
extras do `pPr`; de cada trecho de texto, caractere a caractere (os runs podem vir partidos de
outro jeito), negrito, itálico, sublinhado, tachado, índices, tamanho, fonte, cor e extras do
`rPr`; de cada tabela, linha e célula, larguras da grade, largura, layout fixo, margens, recuo,
alinhamento, altura e extras. Fonte e tamanho que o documento em memória não define (a tela usa
a preferência) não contam. Custo: +40 ms em 3000 parágrafos (573 → 609 ms, com a releitura);
nos 11 `.docx` reais, dentro do ruído (o manual, ~250 ms; o de 13 páginas, ~490 ms, nas duas versões). No arquivo
real do defeito, o arquivo do escritor antigo é recusado ("espaco_depois_tw 0 -> 160,
espacamento_linha_pct 100 -> 108").

Regressão nos 11 `.docx` reais (cópias temporárias; abrir → salvar como → reabrir → salvar →
reabrir, com as fontes do Windows carregadas no offscreen): todos gravam, sem falha na
conferência nem no validador, sem diferença c14n entre a 1ª e a 2ª gravação, e cada arquivo
reabre com o mesmo número de páginas (o do defeito: 4/4/4; na 0.1.15, 4/5/5 com as fontes e
4/6/6 sem). Paginação × Word (docProps/app.xml): 3×3, 4×3, 14×13, 2×2; o Manual tem 48 no
app.xml e 52 no EditDoc. As diferenças que sobram não vêm da gravação (docs/SPIKES.md, "0.1.16").

Testes: suíte nova `teste_fidelidade` (fixture gerada em código sem `styles.xml` nem
`settings.xml`, com imagem da altura da página: mesmas páginas e mesmos formatos de bloco depois
de salvar, docDefaults gravado, segunda gravação igual; contraprova com o escritor antigo, que
reabre com mais páginas e é recusado pela conferência; tabulação sem `settings.xml` com
contraprova; quatro sabotagens do XML gravado acusadas, uma por tipo de formatação, e o arquivo
sem sabotagem passa; custo da conferência em 3000 parágrafos). Nenhuma verificação existente foi
retirada nem reescrita.

## 0.1.15 - 2026-10-15

Digitar repinta só a linha nos tiles da tela, não os tiles inteiros; spike das saídas para a
tecla antes das tabelas, com a conclusão de que a parte do Qt não sai sem reescrever o layout.

Desempenho: no arquivo real de 16 tabelas, digitar antes delas passava do gate de 16 ms (p95
~50 ms na célula a 1/3, ~35 na célula a 1/2, ~40 no item de lista). Spike (docs/SPIKES.md,
"0.1.15"): a cascata do `QTextDocumentLayout` acontece a cada tecla mesmo quando a altura do
bloco não muda (26,7 × 27,4 ms); o layout preguiçoso do Qt só entra pelo layout inteiro e anda
1000 caracteres por tecla; não há como embrulhar o layout pelo PySide; tirar o colapso de bordas
e os formatos de célula vale um terço e mudaria a aparência; tabela flutuante muda a paginação;
tabela congelada, layout próprio de tabela e documento por trecho exigem tirar a tabela do
documento ou reescrever paginação e edição. **A meta de 16 ms nesses pontos não foi alcançada**:
a tecla do Qt sozinha mede 20 a 28 ms.

O que entrou, na pintura (do EditDoc):

- a linha digitada não tira mais do cache os 2 a 4 tiles inteiros que cruza: a parte da linha é
  anotada no tile e a pintura seguinte refaz só ela, com a mesma transformação do tile, e copia
  os pixels da parte (`VistaPaginas._sujos`, `_repintar_partes`). Altura que muda, objetos
  flutuantes e números de lista continuam tirando o tile inteiro;
- dois furos que o tile inteiro escondia: a linha que desce de página dentro do bloco ficava
  fora da faixa refeita (a faixa agora vai pelas linhas do bloco); e o número de lista
  recalculado fora da pintura (a janela pede o rótulo do cursor) não chegava à tela, então o
  Backspace que tira o item vazio da lista podia deixar números velhos abaixo (a vista compara os
  números com os da pintura anterior);
- a lista das quebras de página do usuário (as linhas tracejadas) fica guardada até mudar o
  número de blocos ou um formato: cada quadro olhava centenas de blocos de célula.

Pintura por tecla no plano real (máquina carregada): 15,9 → 7,2 ms a 1/3, 10,3 → 6,6 a 1/2,
8,9 → 7,1 no item. Gate (p95, mediana de 3 rodadas intercaladas, 0.1.14 → 0.1.15): plano real
47,0 → 35,7, 33,6 → 29,3 e 37,0 → 34,9; plano sintético 45,0 → 41,2, 34,3 → 30,2 e 47,0 → 34,3;
o resto da tabela melhorou ou ficou igual (simples 4,6 → 4,7, manual 9,4/8,9/5,9 → 6,7/7,3/5,4,
capa cheia 15,0 → 12,4, 2000 revisões 9,3 → 5,7).

Nada muda no arquivo salvo, na paginação, no PDF, na impressão, na edição de tabela nem no
desfazer: regressão nos 11 `.docx` reais (abrir → salvar como → reabrir → salvar) sem falha, sem
diferença c14n e com o mesmo número de páginas da 0.1.14.

Testes: suíte nova `teste_pintura_parcial` (tela com as partes igual à refeita do zero, pixel a
pixel, a 137%, na célula, no item de lista, com entrelinha exata menor que a letra e na linha que
desce de página; contraprova de cada mecanismo); `teste_quebras` confere a lista guardada das
quebras (com contraprova); o p95 da pintura do plano passa ao critério dos outros pontos (2,5 ×
o simples, era 3,5 ×). Reescrita: a contraprova do cache das faixas dos itens de lista
(`testar_plano`) agora refaz a tela inteira a cada tecla, porque a tecla no item faz uma
pintura só e o cache só aparece com vários tiles por pintura.

## 0.1.14 - 2026-10-15

Digitar em documento com muitas tabelas e listas repinta só o que mudou; rejeitar passa a valer
para as alterações de tabela, linha, célula, seção e numeração; excluir linha e coluna e mover
texto ficam marcados com o controle de alterações ligado.

Defeito 1 (desempenho): no arquivo real de duas seções com 16 tabelas e 89 itens de lista, digitar
a 1/3 do documento passava do gate de 16 ms (48,6 ms na 0.1.11; 37 a 52 ms medidos agora, com a
máquina carregada). Causa, medida e conferida no código do Qt 6.11 (docs/SPIKES.md, "0.1.14"):

- do Qt, ~20 a 30 ms por tecla: num documento paginado o `QTextDocumentLayout` refaz TODAS as
  tabelas que vêm depois do ponto editado, cada célula duas vezes e do zero. Digitar no começo do
  arquivo custa 32 ms; no fim, 2 ms. Não há como desligar isso de fora do Qt (caminhos medidos e
  descartados no SPIKES). Fica como pendência registrada;
- do EditDoc, cortado: digitar numa célula tirava a tabela inteira do cache (a do arquivo atravessa
  páginas: a tela toda, 20 tiles por tecla); agora só as linhas do texto ou a linha da tabela, e
  só na coluna da célula (3,9 tiles por tecla a 1/3, 2,1 na célula a 1/2). Os números das listas
  pediam o retângulo de todos os itens em cada tile (148 mil `blockBoundingRect` em 80 teclas):
  agora as faixas dos itens ficam em cache até o layout mudar, e o Numerador continua sem
  recalcular os números ao digitar dentro de um item (conferido: nenhuma mudança de estrutura em
  80 teclas). Bordas e tabulações guardam o que cada bloco tem para pintar. Um tile do plano: 4,5
  → 2,1 ms.

Gate (p95 em ms, mediana de 3 rodadas, 0.1.13 → 0.1.14; docs/SPIKES.md): plano real a 1/3
87,1 → 49,9, na célula a 1/2 57,6 → 35,3, no item de lista 45,6 → 40,0; plano sintético 64,8 →
50,5, 43,9 → 38,0 e 62,6 → 51,0. A meta de 16 ms nesses pontos NÃO foi alcançada (a tecla do Qt
sozinha passa dela). A tabela do gate não piorou: simples 5,5 → 5,4, manual 10,7/10,5/7,2 →
10,5/10,0/6,8, capa cheia 16,1 → 15,9, 2000 revisões 12,4 → 10,2.

Defeito 2 (controle de alterações): até a 0.1.13 as alterações de célula, de propriedades de
tabela, de linha e de seção e a numeração só podiam ser aceitas; excluir linha ou coluna com o
controle ligado não ficava marcado; recortar e colar virava exclusão e inserção; e um documento
cujas únicas alterações eram de tabela ou de seção mostrava a lista vazia.

- **Rejeitar** devolve o estado de antes guardado no elemento de mudança: `w:tblPrChange` (largura,
  alinhamento, recuo, margens, layout, estilo, os lados de borda declarados), `w:tblGridChange` (a
  grade), `w:trPrChange` (altura, linha de cabeçalho, extras; nova na lista: "Propriedades da
  linha"), `w:tcPrChange` (sombreamento, alinhamento vertical, bordas, extras), `w:sectPrChange`
  (papel, margens, colunas, numeração; os cabeçalhos de agora ficam) e a numeração inserida
  (`w:ins` no `w:numPr`: o parágrafo deixa de ser item). A célula inserida (rejeitar) ou excluída
  (aceitar) sai quando a coluna ou a linha inteira tem a mesma marca. Um passo de desfazer.
- **Excluir linha** com o controle ligado deixa a linha, com `w:del` no `w:trPr` e o texto
  excluído; **excluir coluna** marca cada célula com `w:cellDel`. Aceitar tira, rejeitar devolve.
  A linha ou coluna que o próprio autor inseriu sai de verdade.
- **Recortar e colar** o mesmo trecho no mesmo documento vira **movido**: `w:moveFrom`/`w:moveTo`
  com as pontas (`moveFromRangeStart/End`, `moveToRangeStart/End`) e um nome (`moveN`).
- Limites (README e docs/ARQUITETURA.md): rejeitar não desfaz a mescla (`w:cellMerge`), não tira a
  célula inserida sozinha numa linha e não devolve o `w:numberingChange` (só guarda o texto do
  número): ficam, e a mensagem diz quantas; mover só dentro de um parágrafo, fora de tabela e sem
  marcas; em "Sem marcação" o parágrafo com a marca excluída, a imagem excluída e a tabulação ou
  quebra de linha excluídas continuam como na 0.1.13 (medido: o realce do Qt não muda o tamanho
  de uma imagem nem de uma tabulação; ver SPIKES).

Colunas de texto (`w:cols`): spike feito (a página do Qt como uma coluna, dobrada na folha:
funciona num documento solto, com quebra de coluna e hit-test), **adiado**: mudaria o mapa folha ↔
página de toda a vista, dos campos de página, da impressão e das notas. Continuam preservadas e
mostradas em uma coluna (docs/SPIKES.md, "0.1.14").

Regressão com os 10 `.docx` reais da pasta de amostras (cópias temporárias, fora do
repositório): abrir, salvar como, reabrir e salvar de novo. Todos gravam, passam na conferência e
no validador, e a segunda gravação sai igual à primeira em c14n (só a hora de `docProps/core.xml`
muda, como sempre); os avisos são os mesmos da 0.1.13 (CAIXA_DE_TEXTO e IMAGEM_FLUTUANTE em
quatro deles).

Testes: `teste_desempenho.py` (fixture nova `documento_plano`, equivalente sintética do arquivo
real: 16 tabelas com as formas dele, 362 células, 89 itens; tiles por tecla numa célula de tabela
que atravessa páginas, com contraprova; a tela com cache igual à refeita digitando na célula, com
contraprova; listas sem recálculo e sem refazer as faixas por tile, com contraprova; p95 da pintura
a 1/3, na célula e no item, com a tecla do Qt medida à parte), `teste_revisoes.py` (rejeitar
tabela, grade, linha, célula, seção e numeração, com o arquivo gravado e o desfazer; excluir linha e
coluna rastreados; recortar e colar como movimento, com a contraprova de colar outro texto).
Reescrita, com motivo no teste: `teste_revisoes` esperava que rejeitar `w:cellIns` não fosse feito
(a revisão ficava); agora a célula inserida sai (a linha inteira, todas inseridas).

## 0.1.13 - 2026-10-15

Controle de alterações: as revisões do Word (inserções, exclusões, movimentos, formatação,
parágrafos, tabelas e seções) voltam ao arquivo, aparecem nos quatro modos do Word, se editam
com o controle ligado e se aceitam ou rejeitam.

Defeito: até a 0.1.12 o arquivo com alterações controladas perdia as revisões ao salvar (aviso
REVISAO, com perda): as inserções viravam texto comum, as exclusões sumiam, a formatação de antes
(w:rPrChange, w:pPrChange), as linhas e células inseridas ou excluídas e a revisão da seção saíam;
e o EditDoc não tinha como registrar as próprias alterações.

- Arquivo (`formato_docx/revisoes.py`, `modelo/revisoes.py`): `w:ins`, `w:del` (com `w:delText`
  e `w:delInstrText`), `w:moveFrom`/`w:moveTo` com as pontas (`moveFromRangeStart/End`,
  `moveToRangeStart/End`), `w:rPrChange`, `w:pPrChange`, a marca de parágrafo inserida ou
  excluída, `w:numberingChange`, linhas inseridas/excluídas (`w:trPr/w:ins|w:del`),
  `w:cellIns`/`w:cellDel`/`w:cellMerge`, `w:tblPrChange`, `w:trPrChange`, `w:tcPrChange`,
  `w:tblGridChange`, `w:sectPrChange`, com autor, data e `w16du:dateUtc`, no corpo, nos
  cabeçalhos e rodapés, nas notas e nos comentários; a caixa de texto com revisão volta igual
  (objeto preservado). `w:trackRevisions` do settings.xml lido e gravado. O que não é
  representado volta idêntico em c14n (sem os `w:id`, que o escritor numera); a segunda gravação
  dá os mesmos bytes. REVISAO só para a revisão que não pode ser guardada (acima dos limites:
  100 mil revisões, 500 autores, nome de 255 caracteres; data absurda; fora do lugar do esquema).
- `w:id`: único entre todas as revisões das partes de texto e diferente de todo id de comentário
  e de marcador (o Word numera comentários e revisões numa sequência só; a escolha mais restrita,
  sem documento real com revisões para conferir). Validador: id repetido, `w:t` dentro de
  `w:del`, `w:delText` fora, movimento sem par e trecho sem fim reprovam (contraprovas na suíte).
  A conferência compara as revisões de cada parágrafo.
- Tela: Revisão > Exibir: **Marcação simples** (o texto final, barra vermelha na margem), **Toda
  a marcação** (inserido sublinhado, excluído tachado, na cor de cada autor; movido em verde,
  duplo; barra na margem), **Sem marcação** e **Original** (o texto de antes, com a formatação
  de antes). Trocar o modo não mexe no documento, no desfazer nem no "alterado"
  (`QSyntaxHighlighter`, decidido por spike: docs/SPIKES.md). Painel lateral "Comentários e
  revisões" com a lista de alterações (tipo, autor, data, trecho): escolher seleciona, Aceitar e
  Rejeitar valem para a linha.
- Edição: **Revisão > Controlar alterações (Ctrl+Shift+E)** liga e desliga e vai ao settings.xml.
  Ligado: digitar e colar criam inserção do autor das Opções; apagar texto de outro autor marca a
  exclusão, apagar o próprio texto ainda não aceito remove; Enter cria a marca de parágrafo
  inserida; negrito, fonte, alinhamento, recuo, espaçamento, listas e estilos guardam a formatação
  de antes; substituir é exclusão mais inserção. Desligado: o texto novo não herda a revisão do
  vizinho. **Aceitar** e **Rejeitar** (a atual ou a seleção, todas, todas de um autor),
  **Anterior** e **Próxima**, também no menu de contexto. Um passo de desfazer em cada comando.
- Localizar não acha o texto escondido no modo; a contagem de palavras usa o texto do modo (o
  final em Toda a marcação); copiar leva o texto como se lê (o final em Toda a marcação, como o
  Word); o `.txt` leva o final.
- Impressão e PDF: **Imprimir marcações** (ligado por padrão, como no Word) segue o modo da tela e
  agora imprime também os comentários (o realce do trecho e o texto na margem direita), que a
  0.1.6 deixara de fora; desligado, sai o texto final, sem comentários.
- Achado na validação com um documento gerado pelo EditDoc (controle ligado, dois autores): a
  imagem dentro de `w:del` era relida sem a exclusão e a conferência recusava o arquivo.
  Corrigido no leitor (imagem e objeto levam a revisão do run), com teste.
- Desempenho: com 2000 revisões e o controle ligado, digitar 10,8 ms no p95 (gate de 16 ms);
  trocar o modo de exibição, 268 a 277 ms (critério: menos de 1 s).
- Limites (docs/ARQUITETURA.md): revisões de célula, de propriedades de tabela, de seção e de
  numeração só se aceitam; excluir linha ou coluna com o controle ligado não é rastreado; no modo
  final o parágrafo com a marca excluída e ainda com texto fica separado do de baixo; imagem e
  objeto excluídos continuam visíveis nos modos sem marcação; as revisões de dentro de um
  comentário ou de uma caixa de texto só são preservadas.
- Suíte: `tests/teste_revisoes.py` (nova, 181 verificações) e dois pontos novos em
  `teste_desempenho.py`. Reescrita, com motivo: `teste_formatacao_preservada` esperava o aviso
  REVISAO e a saída do w:rPrChange/w:pPrChange; agora confere que eles voltam (a verificação do
  filho fora do esquema continua igual).

## 0.1.12 - 2026-10-15

Várias seções no mesmo documento: cada uma com o seu papel, as suas margens, os seus cabeçalhos
e a sua numeração, de volta ao arquivo sem perda.

Defeito: até a 0.1.11 só a última seção valia. Os `w:sectPr` dos parágrafos eram achatados
(avisos SECAO, PAGINA e CABECALHO_SECAO, com perda): o arquivo saía com uma seção só, os
cabeçalhos das outras seções sumiam, a página paisagem no meio do documento virava retrato e a
numeração que reiniciava passava a contínua. O que a última seção tinha e o modelo não
representava (colunas, grade, numeração de linhas) também não voltava.

- Arquivo (`formato_docx/secoes.py`, `modelo/secoes.py`): cada `w:sectPr` vira uma `Secao`
  (`Paragrafo.secao` e, para a última, `Documento.secao`): tipo (`w:type`: nextPage, continuous,
  evenPage, oddPage, nextColumn), papel e orientação, margens, primeira página diferente,
  numeração (formato e início) e os cabeçalhos e rodapés que ela declara, com a herança do Word
  (a seção que não declara usa os da anterior). Colunas (`w:cols` com `w:col`), numeração de
  linhas, alinhamento vertical, bordas de página, grade, proteção de formulário, direção do
  texto, bidi, rtlGutter, footnotePr/endnotePr das seções do meio, `w:code` do papel,
  chapStyle e os rsids voltam iguais (c14n): o escritor parte do `w:sectPr` de origem e só muda
  o que o modelo mudou. Duas seções que citam a mesma parte de cabeçalho continuam citando uma
  só. A quebra de coluna (`w:br w:type="column"`), que saía do arquivo, volta (marca no fluxo).
  Formato de número que a tela não desenha passa a ser preservado (NUMERO_PAGINA sem perda).
- Validador e conferência: o `w:sectPr` como último filho do `w:pPr` (parágrafo do corpo, fora
  de tabela) ou do `w:body`; referências com tipo válido, uma por tipo, que resolvem para parte
  de cabeçalho/rodapé; limites contra arquivo hostil (2000 quebras de seção: as que passam se
  juntam à seguinte, com SECAO; 45 colunas: acima, as colunas saem com FORMATACAO). A conferência
  compara onde cada seção termina, a página, o tipo, os extras e os cabeçalhos de cada uma.
- Tela (`interface/secoes.py`, decidido por spike, docs/SPIKES.md "0.1.12"): cada folha tem o
  papel, a orientação, as margens, a altura do corpo, os cabeçalhos e rodapés (com a herança e a
  primeira página da seção) e o número da sua seção (PAGE com reinício e formato; SECTIONPAGES
  passa a ser calculado). O documento continua um só (cursor, seleção, desfazer e localizar
  atravessam as seções): a seção mais estreita tem um recuo direito escondido nos parágrafos e
  tabelas; na seção mais baixa o bloco que não cabe desce para a página seguinte (o espaçador das
  notas) e a tabela longa desce a partir da linha que não cabe; a quebra entre seções é a quebra
  de página do Qt, e evenPage/oddPage ganham a página em branco antes quando precisa. Folhas de
  tamanhos diferentes na tela, uma embaixo da outra; PDF e impressão trocam de papel na folha;
  régua da seção do cursor; objetos flutuantes relativos à página e à margem da seção; notas de
  rodapé no pé do corpo da seção; barra de status "Seção 2 de 3".
- Edição: **Layout > Quebras > Quebra de seção** (Próxima página, Contínua, Página par, Página
  ímpar) parte o parágrafo no cursor; a parte de cima vira uma seção com as propriedades e os
  cabeçalhos da do cursor, e a de baixo começa como o tipo pedido. Com as marcas de formatação, a
  quebra aparece como no Word ("Quebra de seção (Próxima página)"). Backspace no começo do
  parágrafo seguinte, ou Delete antes da quebra, apaga a quebra e funde os parágrafos: o texto de
  cima passa a ter as propriedades da seção de baixo. Um passo de desfazer em cada caso. Papel,
  orientação e margens da aba Layout valem para a seção do cursor; Margens > Personalizadas tem
  "Aplicar a: Esta seção / Documento inteiro". Na edição do cabeçalho o rótulo diz a seção ("-
  Seção 2 - Igual ao anterior") e **Vincular ao anterior** (aba Cabeçalho e Rodapé) desvincula
  (copia o da anterior) ou vincula (apaga o próprio, com confirmação se ele tem texto).
- Avisos: SECAO só para quebra de seção fora do corpo ou acima do limite; PAGINA e
  CABECALHO_SECAO deixam de existir; COLUNAS (sem perda): as colunas são preservadas, mas
  aparecem em uma coluna só.

Validação com arquivos reais (cópias temporárias, fora do repositório): o arquivo de duas seções
que na 0.1.11 abria com SECAO 1 e PAGINA 1 abre sem aviso (capa de 2 folhas, a segunda em branco
como no Word, porque a capa termina numa quebra de página antes da quebra de seção; corpo de 11
folhas com o cabeçalho e o rodapé dele, numeração continuando em 3); abrir, salvar como, reabrir
e salvar: os `w:sectPr` voltam iguais em c14n, e a segunda gravação sai igual à primeira. Os 10
`.docx` da pasta de amostras gravam, passam na conferência e no validador e regravam sem
diferença c14n.

Desempenho: gate de 16 ms em todos os pontos da tabela da 0.1.11 e na fixture de três seções
(6,0 ms digitando na seção paisagem); o arquivo real de duas seções já passava do gate na 0.1.11
(pendência, sem relação com as seções). docs/SPIKES.md "0.1.12".

Testes: `teste_secoes.py` (novo: leitura, c14n de cada `w:sectPr`, referências com o mesmo
conteúdo, idempotência, contínua com duas colunas e quebra de coluna, validador com sabotagens,
arquivo hostil, mudança só no que mudou; folhas de cada seção, página em branco do oddPage,
cabeçalho por folha com a herança, PAGE em romanos e com reinício, mapa da tela, rótulo da quebra,
PDF com o MediaBox de cada folha, salvar e reabrir pela janela; inserir as quatro quebras,
Backspace e Delete, desfazer e refazer, orientação só na seção, documento inteiro, Vincular ao
anterior; notas e objeto flutuante na seção paisagem, tabela longa na paisagem, SECTIONPAGES,
copiar sem o derivado; p95 na seção paisagem; com contraprovas). Checagens reescritas, com o
motivo no teste: `teste_layout.py` (duas seções: era "aviso PAGINA e SECAO", agora sem aviso e a
primeira seção com o papel dela), `teste_cabecalho_rodape.py` (herança: o cabeçalho herdado fica
na seção que o declara e a última o herda; seções com cabeçalhos diferentes: era o aviso
CABECALHO_SECAO, agora cada uma com o seu, sem aviso; 400 seções: era "só a última, com aviso",
agora as 400 ficam, sem aviso, ainda abaixo de 2 s), `teste_quebras.py` (a quebra de coluna
era a contraprova de "não representada"; agora volta ao arquivo, e a contraprova é a quebra de
tipo desconhecido) e `teste_documento.py` (a perda usada na pergunta "salvar mesmo assim" era a
quebra de coluna; passa a ser a quebra de tipo desconhecido). Nenhuma verificação foi retirada.

## 0.1.11 - 2026-10-14

Correções: documento que não salvava, digitação lenta no começo de um manual com capa e teste de
desempenho que reprovava o build por carga da máquina.

- **Documento que não salvava** (desde a 0.1.9, pelo menos). Num documento com estilos de id
  numérico ("1", "2"..., que o Word cria para estilos de nome numérico) e o rodapé "Página 1 de
  32" no estilo "Número de página", a conferência pós-gravação recusava o arquivo ("estilo
  diferente no rodapé") e o usuário não conseguia salvar. Causa: na ponte Qt, o resultado
  guardado do campo (`PROP_CAMPO_RESULTADO`) usava o mesmo número de propriedade do estilo de
  caractere (`PROP_ESTILO_CAR`, UserProperty + 5). O resultado "1" apagava o estilo do campo e,
  como "1" era o id de um estilo do documento, o campo voltava da tela com o estilo "1"; o
  escritor não o gravava, e a releitura não batia. Em qualquer documento, o campo PAGE/NUMPAGES
  perdia o estilo de caractere ao passar pela tela (a conferência não via, porque comparava só o
  conjunto de estilos do parágrafo). Correção na origem: `PROP_CAMPO_RESULTADO` passa a
  UserProperty + 34; a conferência compara também o estilo de cada campo; um teste varre as
  propriedades de usuário de `ponte_qt` e acusa número repetido.
- **Gravar de novo trocava ids**: as relações preservadas (webSettings, fontTable...) eram
  ordenadas pelo texto do rId ("rId10" antes de "rId9"), e cada gravação trocava os ids de duas
  delas. Agora a ordem é pelo número (`pacote.ordem_do_rid`); a segunda gravação sai igual à
  primeira (C14N) em todas as partes, menos a data de modificação no core.xml.
- **Quando a conferência falha**: a mensagem deixa de ser técnica ("A conferência do arquivo
  gravado falhou") e explica que o original não foi alterado e que o documento continua aberto
  com as alterações; a cópia de recuperação é gravada na hora; o botão "Salvar cópia não
  conferida..." grava os mesmos bytes em outro arquivo (nunca por cima do original), para abrir
  no Word. O motivo técnico continua no log, e a mensagem diz onde ele está. O mesmo vale para o
  arquivo gravado que não pode ser lido de volta.
- **Digitação no começo do manual real** (o ponto "sumário" do relatório da 0.1.10: p95 de 95
  ms). O ponto medido era a posição 0, antes das âncoras da capa (o script procurava a linha do
  sumário pelo último caractere, que é a marca do PAGEREF). Ali, cada tecla põe o float da capa,
  que reserva a folha inteira, na página seguinte; o Qt desloca os 13 blocos do sumário com o
  float de antes, a conferência dos flutuantes os refazia um a um (13 chamadas de
  `markContentsDirty`, 24 ms) e a tela inteira saía do cache (16 tiles, 60 ms), embora os
  blocos voltassem exatamente para onde estavam. Agora as faixas encostadas viram uma chamada
  só e, quando os blocos refeitos voltam iguais ao fim da conferência anterior (linhas, texto e
  altura do documento), nada sai do cache. P95: 99,4 → 7,9 ms. A linha do sumário de verdade mede
  14,2 ms (14,2 na 0.1.10). Os outros pontos da tabela do gate ficam iguais
  (docs/SPIKES.md "0.1.11").
- **Teste de desempenho estável**: `tests/teste_desempenho.py` reprovou um build com a máquina
  carregada (35,5 ms contra 10,8 ms do simples, numa medida só). Agora cada ponto vale a
  mediana de 3 rodadas, intercaladas com o documento simples (a referência da mesma hora); a
  folga relativa (2,5 vezes o simples, ou 5 vezes no ponto antes da capa) tem teto absoluto de
  60 ms; e só o ponto que passou do limite mede de novo, até 2 rodadas. O critério tem
  contraprovas sem relógio (pico isolado passa; 35 ms em toda rodada, 95 ms com o simples
  lento e os 168 ms da 0.1.10 reprovam).

Testes: `teste_campos.py` (campo com estilo de caractere num rodapé com tabela, num documento
com estilos de id numérico, gerado em código: grava pela janela, o estilo volta na releitura;
contraprova com o número repetido da 0.1.10 recusada pela conferência; contraprova da
conferência com o campo sem estilo; propriedades de usuário sem número repetido, com
contraprova), `teste_partes_pacote.py` (ordem pelo número do rId, três gravações iguais,
contraprova pela ordem do texto), `teste_desempenho.py` (ponto antes das âncoras de uma capa
que reserva a folha, com o sumário num controle de conteúdo: uma chamada de refazer por tecla,
contra 18; 5,5 tiles por tecla, contra 16; tela com cache igual à refeita com o atalho usado;
contraprovas de cada metade e da comparação; critério do p95). Checagens reescritas, com o
motivo no teste: `teste_documento.py` (a falha na conferência abre o diálogo próprio, não mais
o `avisar`; as checagens de antes ficam e o `avisar` passa a ser proibido) e
`teste_desempenho.py` (o p95 de capa, sumário e corpo passa de uma medida com segunda
tentativa para a mediana de 3 rodadas; o limite continua o gate ou 2,5 vezes o simples).

## 0.1.10 - 2026-10-14

Notas de rodapé e de fim: lidas, editadas, numeradas, no pé da página e de volta ao arquivo.

Defeito: até a 0.1.9 a referência de nota saía do texto ao abrir e a nota saía do arquivo ao
salvar (aviso NOTA, com perda); só as notas separadoras voltavam.

- Arquivo: `word/footnotes.xml` e `word/endnotes.xml` lidos e gravados (`formato_docx/notas.py`,
  `leitor._ler_notas`, `modelo/notas.py`). O conteúdo da nota passa pelo leitor e pelo escritor
  de parágrafos (formatação, links, campos, imagens); as notas separadoras (separator,
  continuationSeparator, continuationNotice) voltam com o XML de origem; a referência
  (`w:footnoteReference`/`w:endnoteReference`, com `w:customMarkFollows` e o run do símbolo) é
  uma marca no fluxo (`MarcaNota`), e o número da própria nota (`w:footnoteRef`) também. As
  propriedades (`w:footnotePr`/`w:endnotePr`: numFmt, numStart, numRestart, pos) do sectPr e do
  settings.xml são lidas; a do sectPr volta como veio enquanto não muda. Sem mudança, a parte
  volta com os bytes de origem e as relações (link e imagem) com o mesmo Id; com mudança, as
  notas que não mudaram voltam com o XML de origem (iguais em c14n) e as outras são geradas.
  Ids coerentes (`notas.preparar`: só as notas com referência, id novo para a referência
  repetida), relações, Override e o settings.xml citando as separadoras; o documento que ganha a
  primeira nota ganha as separadoras do Word e os estilos FootnoteText, FootnoteReference,
  EndnoteText e EndnoteReference.
- Numeração: contínua ou reiniciada a cada página, em 1, a, A, i, I ou * † ‡ §, a partir do
  número inicial; a marca personalizada não conta. A marca sobrescrita no texto e na nota é
  pintada com o número calculado na hora (sem mexer no desfazer).
- Tela, PDF e impressão: as notas de rodapé ficam no pé da página da referência, acima do
  rodapé, com o separador curto; a área de notas encolhe o corpo daquela página (o bloco que
  não cabe vai para a página seguinte: espaçador no fluxo, decidido por spike, docs/SPIKES.md
  "0.1.10"); a nota que não cabe continua na página seguinte, com o separador de continuação
  (largura toda); as notas de fim vêm depois do texto, em páginas a mais se preciso. Posição
  "abaixo do texto" também. Nada se sobrepõe ao texto.
- Edição: aba **Referências** (grupo Notas de Rodapé): Inserir nota de rodapé
  (**Alt+Ctrl+F**), Inserir nota de fim (**Alt+Ctrl+D**), Próxima, Anterior e Opções (formato,
  início, reinício, posição; converter todas as notas de rodapé em notas de fim e o
  contrário). Clicar na área da nota edita o texto dela no lugar (Esc ou clique no texto
  voltam); duplo clique na marca leva à nota, e no número da nota volta à marca. A edição de uma
  nota é um passo de desfazer do corpo (dentro dela, Ctrl+Z desfaz as teclas). Apagar a marca
  apaga a nota (Ctrl+Z a devolve). Copiar e colar dentro do EditDoc leva a nota (com id novo).
- Avisos: NOTA passa a ser só a nota que não pode ser lida (sem referência no corpo, referência
  no cabeçalho, no rodapé ou numa caixa de texto, danificada, acima dos limites).
- Validador e conferência pós-gravação: referências e notas coerentes (cada referência cita
  uma nota normal que existe, uma vez; cada nota tem referência; ids únicos; o settings.xml só
  cita separadoras que existem; `w:footnoteRef` só na nota). Limites contra arquivo hostil: 5000
  notas por tipo, 1 MB por nota, 32 MB por parte, 2000 parágrafos por nota e a profundidade do
  XML; acima deles a parte volta só com as separadoras, como até a 0.1.9, com aviso.
- Exportar `.txt`: a referência vira "[1]" e as notas vêm no fim, numeradas.

Limites: quando a área de notas empurra o texto, o parágrafo inteiro desce (o Word parte o
parágrafo); tabela que começou na página anterior não é empurrada (a nota continua na página
seguinte); as notas depois de uma que continua esperam a continuação; formatos fora de
decimal, letras, romanos e chicago aparecem em decimal (o arquivo guarda o do Word); "fim da
seção" é o fim do documento; o aviso de continuação do Word não aparece.

Desempenho (gate de 16 ms, docs/SPIKES.md "0.1.10"): p95 de 8,0 ms digitando no corpo e de 10,5 ms dentro de uma nota, num documento de 300 parágrafos com 100 notas; os pontos da tabela do gate sem notas ficam iguais aos da 0.1.9 (o plano das notas não roda em documento sem nota).

Testes: `teste_notas.py` (123 verificações: leitura, ida e volta c14n com link e
imagem, nota editada e nova, documento sem footnotes.xml, propriedades do sectPr, numeração
contínua, por página, romano, chicago e personalizada, validador com contraprovas, avisos e
limites com arquivo hostil, nota na página da referência e corpo encolhido com contraprova,
nota longa que continua, notas de fim depois do texto, pixels da área de notas, número por
página na tela, Alt+Ctrl+F e Alt+Ctrl+D com teclas reais, digitar na nota, desfazer e refazer,
apagar a marca, duplo clique, próxima nota, opções e converter, copiar e colar, PDF com a nota
no pé da página, `.txt` com as notas, p95 com 100 notas). Checagens reescritas, com o motivo
no teste: `teste_galeria.py` (as abas da faixa final incluem Referências) e
`teste_acessibilidade.py` (a dica S da aba Referências aparece com as outras).

## 0.1.9 - 2026-10-14

Mover e redimensionar objetos com o mouse e o teclado, e a quebra de texto, como no Word.

Pedido: até a 0.1.8 o objeto flutuante se selecionava e se apagava, mas não se movia nem mudava
de tamanho; o objeto do cabeçalho não se selecionava; a quebra de texto não se trocava; e a
caixa de texto ou a forma na linha não tinham alças.

- Arrastar o corpo do objeto flutuante (imagem, caixa, forma, grupo, VML) move; as oito alças
  (cantos e meio dos lados) redimensionam. Durante o arraste só um contorno tracejado
  acompanha o mouse; o objeto e o texto em volta mudam ao soltar (o contorno de texto é
  refeito uma vez). Shift trava a proporção (os cantos da imagem travam sem Shift, como no
  Word) e, ao mover, o eixo. Um passo de desfazer por arraste.
- No arquivo muda só a posição e o tamanho (`formato_docx/posicao.py`): `wp:posOffset` no
  mesmo `relativeFrom` (o `wp:align` e o `wp14:pctPosHOffset` viram posOffset, como o Word),
  `wp:simplePos` quando o objeto o usa, `wp:extent` e o `a:ext` do desenho de cima (no grupo o
  `chOff/chExt` fica e os filhos acompanham), e no VML o `style` (margin-left/top,
  width/height) do objeto e do `mc:Fallback`. O resto do XML do objeto fica igual em c14n.
- Arrastar para outra página leva a âncora ao parágrafo mais perto do topo novo (o caractere
  do objeto vai para o começo dele), como o Word; o objeto preso ao parágrafo arrastado para
  outro parágrafo também. Âncora travada, cabeçalho e rodapé, tabela: a âncora fica e a
  posição passa a ser relativa à página.
- Setas movem o objeto selecionado 1 px de tela; Ctrl+setas, um quarto de px (no mínimo
  1 twip); Esc tira a seleção. Um passo de desfazer por tecla.
- Objeto preservado na linha (caixa de texto, forma, objeto com tamanho): as alças da imagem
  (`wp:extent` e o xfrm de dentro; sem Shift a caixa não trava a proporção). A imagem na
  linha do M4 continua igual.
- Quebra de texto: Layout > Organizar > Quebra de texto (e o menu de contexto do objeto) com
  Alinhado ao texto, Quadrado, Comprimido, Através, Superior e inferior, Atrás do texto e Na
  frente do texto. Regrava o `wp:wrap*` (Comprimido e Através com o `wp:wrapPolygon` que o
  esquema exige) e o `behindDoc`; Alinhado ao texto converte `wp:anchor` em `wp:inline` e de
  volta, com os atributos que o esquema exige (distâncias, simplePos, relativeHeight único,
  behindDoc, locked, layoutInCell, allowOverlap). A imagem do EditDoc que passa a flutuar vira
  objeto (o desenho que o escritor grava); a figura simples que volta para a linha vira
  imagem do EditDoc (é o que o leitor lê de um `wp:inline`). A figura girada, espelhada, com
  borda ou efeito não volta para a linha: a troca é recusada com o motivo.
- Diálogo Posição e tamanho (Layout > Organizar > Posição, ou o menu de contexto): posição
  horizontal e vertical em cm relativa à página, margem, coluna ou caractere (e parágrafo ou
  linha), largura e altura com a proporção travada, e a quebra. Trocar a referência mostra o
  mesmo lugar medido da referência nova; só o que mudou vai para o arquivo. Um passo de
  desfazer.
- Cabeçalho e rodapé: na edição deles (duplo clique no alto ou no pé da página), o objeto se
  seleciona (o de trás só fora do texto), arrasta, redimensiona, anda com as setas e se
  desfaz no desfazer da faixa; duplo clique na caixa abre o editor.
- Limites: posição de -55,88 a +55,88 cm da referência (o que o Word aceita; ST_PositionOffset
  é inteiro de 32 bits) e tamanho de 1 px a 176 cm (ST_PositiveCoordinate nunca negativo); a
  linha reta continua com altura zero. O validador de gravação confere os atributos do
  `wp:anchor`, a quebra, as posições e o extent.
- Arquivo real (manual de 51 páginas, capa com 5 objetos): mover o ícone da capa 2 cm para
  cima e redimensionar a caixa do título gravam `posOffset` -939075 (era -219075, relativo à
  margem de baixo) e `extent` 5541600 x 2163150 (era 5181600 x 2343150); ao reabrir os objetos
  estão no lugar (deslocamento de -1133,9 twips e +566,9 / -283,5 twips, como pedido); das 76
  partes do pacote só o `document.xml` difere de uma gravação sem mexer, e nele só os dois
  objetos, e só na posição e no tamanho (c14n).

Testes: `teste_mover_redimensionar.py` (166 verificações: XML contra o oráculo em
EMU, c14n do resto com contraprova, grupo, linha reta, simplePos, as sete quebras, inline <->
anchor com os atributos do esquema, VML, limites, validador com contraprova, a conta de volta
de `retangulo`; arraste com QTest sobre a VistaPaginas com o contorno fantasma, o texto que
volta a contornar, desfazer e refazer; Shift, alça de lado e de canto, imagem; setas e Esc;
reancorar para a página 2 e gravar; objeto na linha; quebra pela galeria, linha <-> flutuante
da caixa e da imagem do EditDoc, com gravação, validador e conferência pós-gravação; recusa da
figura girada; diálogo; comandos da janela; cabeçalho em edição; VML; p95 do arraste no gate).
Checagem reescrita, com o motivo no teste: em `teste_flutuantes.py`, "o contorno de seleção
aparece na borda do objeto" passou a olhar a borda a um quarto da altura (o meio do lado agora
é uma alça, branca por dentro).

## 0.1.8 - 2026-10-14

Digitação abaixo de 16 ms num manual real pesado, e o corpo de cada página começa onde termina
o cabeçalho dela.

Defeito 1: num manual real de 51 páginas (capa com imagem de página inteira e caixas de texto,
sumário com links, PAGEREF e pontilhado, 49 desenhos), cada tecla levava de 48 a 91 ms (p95)
no parágrafo das âncoras, no sumário e no corpo. Causas, pelo perfil (docs/SPIKES.md, "0.1.8"):
a conferência dos objetos flutuantes nunca ficava estável (uma linha que o Qt desce de página
ao lado de um objeto guarda a largura estreita, e refazer não muda nada), então cada tecla
refazia o trecho 6 vezes e conferia até o fim do documento; o parágrafo das âncoras tem a
altura da folha, e cada tecla tirava do cache a folha inteira; o pontilhado do sumário era um
`drawText` por ponto; os objetos flutuantes, o cabeçalho e o rodapé eram pintados de novo em
cada tile e em cada quadro.

- Conferência dos floats: as linhas que o Qt não refaz são aceitas (pela assinatura delas) e
  só voltam a ser conferidas se mudarem.
- Cache de tiles: sai da tela a faixa das linhas que mudaram (a anterior e da linha da mudança
  até a base do bloco, a de antes ou a de agora), não o bloco inteiro; o tile guarda a faixa
  cortada no corpo da página dele; a conferência que refaz um trecho invalida só dali para
  baixo; a tecla depois de um cache limpo não refaz a tela inteira de novo.
- Objetos flutuantes, cabeçalho e rodapé pintados uma vez na tela (QPixmap alinhado ao pixel
  do dispositivo, copiado 1:1); o PDF e a impressão pintam de verdade.
- Pontilhado da tabulação num `drawText` só; tamanho das marcas de campo e de link guardado
  pela fonte.
- Resultado (p95, janela de produção, mesmo roteiro nas duas versões, mediana de 3 rodadas):
  âncoras 77,1 → 10,6 ms; sumário 47,9 → 9,6; corpo 91,0 → 6,8 e 90,2 → 7,0. Os outros
  cenários do gate ficam iguais ou melhores (capítulo de 4 páginas, corpo: 7,9 → 5,1); a
  tabela inteira está em docs/SPIKES.md.

Defeito 2: o corpo usava a mesma altura de cabeçalho em todas as páginas (a maior das
variantes). Na capa de um manual com o cabeçalho da primeira página vazio, o corpo, o título e
as caixas ancoradas nele ficavam 0,6 cm abaixo do Word (título em 3,89 cm; o Word mostra 3,29).

- O topo do corpo de cada folha é max(margem de cima, distância do cabeçalho + altura do
  cabeçalho da página: primeira, par ou padrão), sem o pé do corpo passar do rodapé da
  página (`LayoutPaginado.efetiva_da(n)`). A tela, o PDF, a impressão, o clique, a zona do
  cabeçalho, o rótulo da edição e os objetos flutuantes seguem. Na capa do manual: título,
  caixa vazia e "Portal Documentação" em 3,29 / 7,05 / 27,39 cm, como no Word.
- Limite: a altura do corpo continua a mesma em todas as páginas (a da página com o maior
  cabeçalho e o maior rodapé), porque o `QTextDocument` pagina com um tamanho só. Na página
  de cabeçalho menor o corpo termina mais acima; o número de páginas não muda.

Testes: `teste_desempenho.py` (22 verificações: refações por tecla na linha que não
converge, tiles por tecla, tela com cache igual à refeita tecla a tecla, objetos e faixas não
repintados, pontilhado, marcas, p95 num manual sintético; cada estrutural com contraprova) e
`teste_cabecalho_por_pagina.py` (28: topo por página no layout, no mapa da tela, nos tiles e no
PDF contra o oráculo em twips, número de páginas, objeto relativo ao parágrafo, clique, zona,
cabeçalho que cresce, contraprova). Nenhuma verificação existente foi retirada ou reescrita.

## 0.1.7 - 2026-10-14

Objetos flutuantes na posição da página, com o texto em volta.

Defeito: imagem, caixa de texto, forma e grupo flutuantes (`wp:anchor`, ou VML com
`position:absolute`) apareciam como etiqueta ou caixa no ponto da âncora, dentro do texto.
Num manual real a capa ficava deformada (o título, numa caixa de texto, virava um bloco no
meio do texto; as imagens viravam "Imagem flutuante"), e num cabeçalho real a faixa escura
atrás do logotipo não aparecia (o logotipo branco ficava invisível sobre o branco). O
arquivo salvo já estava certo: o defeito era só a aparência (tela, PDF e impressão). Causa:
a ponte desenhava o objeto como caractere do texto, sem ler a posição.

- Posição (`modelo/flutuantes.py`, sem Qt): `wp:positionH/positionV` com relativeFrom
  page, margin, column, character, paragraph, line, leftMargin, rightMargin, topMargin,
  bottomMargin, insideMargin e outsideMargin; `wp:posOffset`, `wp:align`
  (left/center/right/inside/outside, top/center/bottom), `wp14:pctPosHOffset/VOffset`,
  `wp:extent`, `wp14:sizeRelH/V` (pctWidth/pctHeight), `wp:simplePos`, `effectExtent`,
  distâncias, behindDoc e relativeHeight (ordem). VML: `margin-left/top`, `width/height`,
  `mso-position-horizontal/vertical(-relative)`, `mso-width/height-percent`, `z-index`
  (negativo = atrás) e `w10:wrap`. A página do objeto é a do parágrafo-âncora.
- Leitura do desenho (`formato_docx/flutuantes.py`): imagem (rId e recorte `a:srcRect`),
  forma (`prstGeom`: retângulo, retângulo arredondado, elipse, linha e conectores,
  triângulos, losango, paralelogramo, trapézio, polígonos, setas, divisa, mais;
  preenchimento e contorno do `spPr` ou da referência `wps:style`, com as cores do tema e
  lumMod/lumOff/shade/tint/alpha), caixa de texto (o texto, as margens do `bodyPr`, o
  alinhamento vertical e a cor do `fontRef`), grupo (filhos por `chOff/chExt`, grupo dentro
  de grupo), rotação e espelho; gráfico, SmartArt e tela de desenho com a imagem de reserva
  ou um quadro rotulado do tamanho certo. No AlternateContent vale o DrawingML; o VML só
  quando é o único.
- Quebra de texto (`ponte_qt/flutuantes.py`): wrapSquare, wrapTight e wrapThrough (os dois
  últimos como Square, pelo retângulo) fazem o texto contornar o objeto linha a linha;
  wrapTopAndBottom leva o texto para baixo dele; wrapNone e behindDoc não mexem no texto
  (o objeto fica na frente ou atrás). O caractere do objeto vira um float do layout do Qt
  (`QTextFrame` FloatLeft/FloatRight pelo `ObjectIndex`), com o tamanho calculado a cada
  layout; a conferência depois de cada mudança refaz o que o Qt deixa velho (bloco só
  deslocado, frame órfão depois de apagar). Medição e escolha em docs/SPIKES.md.
- Pintura: a mesma função na tela, no PDF e na impressão. Os objetos de trás antes do texto,
  os da frente depois, recortados na folha inteira. Os do cabeçalho e do rodapé aparecem em
  todas as páginas, atrás do texto do corpo (a impressão pinta os objetos das faixas, o
  corpo e o texto das faixas; na tela, com objeto em faixa, os tiles ficam transparentes).
- Interação: clique no objeto seleciona (contorno azul com alças; o objeto de trás só se
  pega fora do texto); Delete e Backspace apagam, com desfazer; duplo clique na caixa de
  texto abre o editor da 0.1.5.
- Nada muda no arquivo quando o objeto não é mexido: o XML guardado volta igual (c14n),
  passando pelo Qt e gravando de novo.
- Desempenho (gate do M3, p95 de 80 teclas com pintura, Segoe UI, offscreen): 600
  parágrafos sem objetos 8,5 ms (0.1.6: 8,3); com dois objetos, digitando ao lado da
  imagem, 10,3 ms (0.1.6: 9,1). Ver docs/SPIKES.md.
- Testes: `teste_flutuantes.py` (77 verificações: oráculo de posição em twips, leitura,
  página da âncora, contorno à esquerda e à direita, wrapTopAndBottom, wrapNone, behindDoc,
  pixels de trás e da frente, imagem na folha e no PDF, cabeçalho em todas as páginas,
  c14n, seleção, Delete, desfazer e refazer, desempenho). Checagens reescritas, com o
  motivo no teste: em `teste_caixas_texto.py`, "a caixa flutuante aparece com a largura do
  wp:extent" passou a conferir o tamanho do objeto na folha (antes, no texto), e "a caixa
  só de leitura continua a etiqueta" virou "a caixa só de leitura aparece na posição dela,
  com o conteúdo dentro" (ela deixou de ser etiqueta).
- Limites: o texto contorna por um lado só (o maior, ou o do `wrapText`); a faixa reservada
  começa na linha da âncora; objetos do mesmo parágrafo somam a faixa por lado; objeto em
  célula de tabela não reserva espaço; mover e redimensionar com o mouse ainda não existem;
  o objeto do cabeçalho não se seleciona na página.

## 0.1.6 - 2026-10-14

Comentários do Word editáveis e referências de estilo sem perda.

Defeito: num `.docx` real com comentários o EditDoc avisava "2 comentários ... saem do
arquivo ao salvar" e "2 referências de estilo não puderam ser aplicadas": os comentários
(`comments.xml`, respostas, resolvido, `people.xml`) sumiam ao salvar e o `rStyle`
"CommentReference" (estilo latente do Word, sem definição no `styles.xml`) virava Normal.
Noutro arquivo, o `rStyle` dos runs do código do campo TOC (2 ocorrências) sumia. Causas: o
leitor não tinha modelo para comentários (contava o aviso e descartava), só aceitava
referência de estilo que o `styles.xml` definisse, e o escritor gravava o código do campo
com o `rPr` do begin.

- Comentários (`modelo/comentarios.py`, `formato_docx/comentarios.py`): âncoras no fluxo
  (`MarcaComentario`: início, fim e referência, inclusive aninhados, sobre o mesmo trecho e
  atravessando parágrafos) e o catálogo no documento, com autor, iniciais, data, conteúdo
  (lido pelo leitor de parágrafos: formatação, links, campos, marcadores), resposta
  (`paraIdParent`), resolvido (`done`), `durableId` e `dateUtc`. Sem mudança, as cinco partes
  voltam iguais (c14n; o `comments.xml` byte a byte, com as relações dos links). O
  comentário que o EditDoc não mudou volta com o XML de origem (o link mantém o rId); o novo
  ou editado é gerado com `annotationRef` e `w14:paraId`. Criar, responder ou resolver grava
  as três partes estendidas coerentes (também num documento antigo, que só tinha o
  `comments.xml`: o comentário de origem ganha o `paraId`); o autor novo entra uma vez no
  `people.xml` (as entradas repetidas de origem ficam).
- Tela: painel de comentários (dock à direita, cartões com respostas e resolvido, nomes
  acessíveis, região do F6), realce amarelo claro do trecho (só na tela), aba **Revisão**
  com o grupo Comentários (Novo, Excluir/Excluir todos, Anterior, Próximo, Mostrar,
  Responder, Resolver; dica de tecla R). Novo comentário: **Ctrl+Alt+M**. Editor do texto
  com N/I/S e links; com campo ou marcador, só leitura com o motivo. Opções: "Nome de
  usuário" e "Iniciais" (vazio = usuário do Windows). Datas: `w:date` na hora local (como o
  Word grava) e `dateUtc` em UTC. Um desfazer por comando.
- Apagar texto com âncoras (`edicao/comentarios.remover_selecao`), como o Word: a seleção
  que leva a referência, ou todo o texto comentado, leva o comentário (e as respostas); a
  que leva só uma ponta reancora no que sobrou. Antes de gravar, `marcas.equilibrar` deixa
  início, fim e referência coerentes; o comentário sem referência sai com o aviso novo
  COMENTARIO_INCOMPLETO.
- Validador: âncora cita comentário que existe, uma referência por comentário, início antes
  do fim, ids únicos; `commentsExtended` cita `paraId` existente (e o pai), `commentsIds`
  com `durableId` único, `commentsExtensible` cita `durableId` do `commentsIds`. Conferência
  pós-gravação compara cada comentário. Limites: 5000 comentários, 1 MB por comentário,
  32 MB de `comments.xml`, 2000 parágrafos por comentário, 32 níveis de resposta (ciclo ou
  fundo demais sobe ao topo). COMENTARIO fica para o que não pode ser lido (danificado,
  acima dos limites, ancorado só no cabeçalho, rodapé ou numa caixa de texto).
- Referências de estilo (`Estilo.virtual`): `rStyle`, `pStyle` e `tblStyle` sem definição
  voltam como vieram, sem acrescentar definição ao `styles.xml`; o validador aceita só os
  ids preservados. Na tela, os latentes conhecidos do Word (`ESTILOS_LATENTES_WORD`:
  comentário, hiperlink, notas, cabeçalho, rodapé, legenda, TOC1 a TOC9, títulos, menção...)
  têm a aparência padrão do Word, sem virar formatação direta ao salvar; id desconhecido não
  muda a aparência. ESTILO só para id inválido ou citado com outro tipo.
- Campo: o `rPr` dos runs do código (`instrText`) e do `separate` volta (`Campo.rpr_codigo`,
  `rpr_separador`).
- Tabela: o estilo de origem (`Tabela.estilo`), o `tblLook` e o tamanho das faixas voltam
  (antes: "Table Grid" imposto e aviso ESTILO); os `cnfStyle` já voltavam pelos extras. O
  fundo da formatação condicional (cabeçalho, última linha, colunas, faixas, cantos,
  respeitando o `tblLook`) aparece na tela e no PDF e não vira sombreamento direto.
- Medido no Qt 6.11.2: dentro de um bloco de edição aberto a revisão do documento não muda e
  o `contentsChange` só vem no fim; a varredura das âncoras (10 ms em 3000 parágrafos) é
  acompanhada pelo sinal (1,4 ms por tecla).
- Testes: `teste_comentarios.py` (114) e `teste_estilos_referencias.py` (44). Checagens
  reescritas, com o motivo no teste: a lista de abas e de dicas de tecla ganhou "Revisão" e
  "R" (`teste_galeria`, `teste_acessibilidade`); a referência a comentário dentro de caixa de
  texto deixou de contar COMENTARIO por referência (sem `comments.xml` não há o que perder),
  e uma verificação nova prova o aviso quando o comentário existe (`teste_objetos_opacos`).
- Pendente: "Imprimir marcações" (comentários na impressão e no PDF); negrito e cor da
  linha de cabeçalho vindos da formatação condicional da tabela (viraria formatação direta
  ao salvar); bordas condicionais na tela.

## 0.1.5 - 2026-10-13

Formatação sem perda, texto das caixas de texto editável e imagens EMF, WMF, TIFF e SVG na
tela.

Defeito: num `.docx` real o EditDoc avisava "formatação não é preservada" (1, 43 e 157
ocorrências em três arquivos de uso real), "caixas de texto não podem ser editadas" e "imagem
em formato que o EditDoc não mostra". Causas: o leitor só guardava as propriedades de run e
de parágrafo que o modelo tinha campo; o resto (tabulações, bordas, sombreamento, realce,
maiúsculas, espaçamento, recorte de imagem...) saía ao salvar, com aviso, ou sem aviso
nenhum ("neutras": idioma, noProof, keepNext, a marca de parágrafo). O controle de conteúdo
(o quadro "Sumário" do Word) era achatado. A caixa de texto era um objeto opaco sem caminho
de edição. EMF, WMF, TIFF e SVG não tinham decodificador.

- Propriedades preservadas (`formato_docx/propriedades.py`, `Run.extras`,
  `Paragrafo.extras`, e desde esta versão também `Tabela`, `Linha` e `Celula`): o XML
  original do que o modelo não representa vai para os extras, em forma canônica (c14n), e
  volta ao arquivo junto com o que o escritor gera, na ordem do esquema. Os "detalhes" de
  propriedades representadas (`w:u` duplo, `w:dstrike`, `w:color` com tema, `w:rFonts` com
  fonte de tema, `w:jc start`, `w:ind` com `leftChars`, `w:spacing` com entrelinha exata) só
  voltam enquanto o campo do modelo continua com o valor que eles dão: mudar o sublinhado,
  a cor ou o alinhamento troca só aquilo. `w:szCs` diferente do `w:sz` fica. Extensões do
  Word (`w14:ligatures`, `w14:shadow`...) ficam, e a raiz declara o prefixo no
  `mc:Ignorable`. Só sai, com aviso, o que o esquema não tem (FORMATACAO) e a revisão de
  formatação (REVISAO). Num arquivo real de 58 páginas, as 157 formatações perdidas
  (124 `w:bdr`, 17 recortes de imagem, 12 `w:tabs`, 2 `w:shd`, 1 `w:spacing`, 1 `w:pBdr`)
  voltam todas; noutro, os 41 realces, a maiúscula e o versalete.
- Na tela (`ponte_qt/propriedades.py`): realce e sombreamento como fundo, maiúsculas,
  versalete, espaçamento entre letras e escala; tabulações próprias do parágrafo (com o
  pontilhado pintado), fundo e bordas do parágrafo (vizinhos de mesma borda formam um
  quadro, como no Word), borda de trecho e entrelinha exata ou mínima. Recorte de imagem
  (`Imagem.recorte`, `a:srcRect`) guardado, gravado e aplicado na prévia. Digitar herda o
  rPr do vizinho, Enter copia o pPr para o parágrafo novo, copiar e colar leva os extras
  (`application/x-editdoc-propriedades`), Limpar formatação os tira.
- Medido no Qt 6.11.2, dispositivo de 1440 dpi: o espaçamento absoluto entre letras, a
  posição da tabulação e a altura fixa da linha são escalados como px96 (× 15); vão em
  twips / 15. A tabulação do Qt conta da posição da linha; a do Word, da margem: o
  EditDoc desconta o recuo esquerdo.
- Controles de conteúdo (`MarcaConteudo`): o de bloco (sumário, `docPartObj`) e o de
  parágrafo viram marcas de início (com o `sdtPr` e o `sdtEndPr`) e de fim no fluxo, como os
  campos da 0.1.3; o escritor grava o `w:sdt` por fora dos parágrafos que o de bloco envolve.
  `marcas.equilibrar` tira o par cruzado ou sem ponta (aviso CONTEUDO_INCOMPLETO, com
  perda: o texto fica) e troca `w:id` repetido. O de linha ou célula de tabela continua
  achatado (CONTEUDO_CONTROLADO). O validador aceita a célula, o cabeçalho e o rodapé que
  terminam num controle cujo conteúdo termina em parágrafo.
- Caixa de texto editável (`formato_docx/caixas.py`, `interface/dialogo_caixa.py`): duplo
  clique na caixa, Enter com ela selecionada ou "Editar texto da caixa" no menu de contexto
  abrem o editor do próprio EditDoc (o `PainelDocumento` numa página da largura da caixa,
  com negrito, itálico e sublinhado). OK regrava o `w:txbxContent` dentro do XML do objeto,
  no Choice (`wps:txbx`) e no Fallback (`v:textbox`); o resto da forma fica idêntico, e o
  link ganha relação nova. Um passo de desfazer. Só é editável o que volta sem perda
  (conferido regravando e relendo na hora); a caixa com tabela, imagem, forma, campo,
  controle de conteúdo, marcador, nota, comentário, equação ou revisão abre só para
  leitura, com o motivo. Na tela, a caixa editável aparece do tamanho do `wp:extent` (a
  flutuante também, no ponto da âncora) com o texto composto dentro.
- Imagens (`ponte_qt/vetoriais.py`, `modelo/imagem.previa_possivel`): TIFF pelo plugin
  `qtiff`, SVG pelo `QtSvg` (recusado se tiver DOCTYPE ou referência de fora), EMF e WMF
  pelo GDI do Windows por ctypes, registro a registro, com teto de registros e de tempo, num
  bitmap do tamanho da tela (nunca do que o arquivo declara) e com transparência (duas
  passadas, fundo branco e preto). O leitor confere o cabeçalho e a estrutura dos
  registros antes (arquivo cortado, registro de tamanho impossível, dimensões absurdas: o
  quadro). A imagem que aparece não dá mais aviso; IMAGEM_FORMATO fica para a vinculada a
  arquivo externo (nunca lida; o quadro mostra o nome), a danificada e a enorme. Os bytes
  originais voltam iguais. A autoverificação do `.exe` renderiza um TIFF, um SVG, um EMF e
  um WMF.
- Avisos: CAIXA_DE_TEXTO diz que o texto da caixa se edita; ESPACAMENTO_LINHA não aparece
  mais (a entrelinha exata volta); CONTEUDO_INCOMPLETO é novo.
- Testes: `teste_formatacao_preservada.py`, `teste_caixas_texto.py` e
  `teste_imagens_vetoriais.py`. Checagens reescritas, com o motivo no próprio teste: o
  recorte de imagem deixou de ser perda (`teste_imagens`); a extensão `w14` no rPr de um
  run comum passou a ser aceita, e a contraprova usa um namespace que não é do Word
  (`teste_objetos_opacos`); o texto do aviso das caixas (`teste_objetos_opacos`, dois
  lugares).

## 0.1.4 - 2026-10-13

Numeração de listas completa: o `numbering.xml` volta inteiro, os números aparecem como no
Word e as listas se editam como no Word.

Defeito: o EditDoc regravava o `numbering.xml` do zero com duas listas (marcador e
"1, 2, 3"). Lista de vários níveis, título numerado ("1.1.1"), letra, romano, marcador da
fonte Symbol ou Wingdings, marcador de figura, início diferente de 1 e recuos do nível se
perdiam ao salvar (avisos LISTA e LISTA_NIVEL, com perda), a lista do estilo virava lista
direta do parágrafo, e a lista dentro de caixa de texto perdia a numeração
(LISTA_EM_CAIXA). Na tela a lista era um QTextList: um nível só, numeração reiniciada a
cada grupo, disco no lugar do símbolo, número colado no texto. Causa: o modelo só sabia
"marcadores" ou "numeração"; o resto do arquivo não tinha onde ficar.

Achado no caminho: o layout do Qt 6.11 no dispositivo de 1440 dpi escala as margens
verticais do bloco (px96 × 15), mas não as horizontais. Os recuos (esquerdo, direito e da
primeira linha) iam em px96 e apareciam 15 vezes menores na tela, no PDF e na impressão
(medido: `leftMargin` 96 põe a linha em x = 96 twips; `topMargin` 96 desce o bloco 1440).
Desde a 0.1.4 os recuos horizontais ficam em twips no formato do bloco; o arquivo não
mudava (a conversão era simétrica), só a aparência.

- Catálogo de numeração (`modelo/numeracao.py`, `formato_docx/numeracao.py`): cada
  `w:abstractNum` (os 9 `w:lvl`: início, formato, texto com %1..%9, alinhamento, recuos e
  tabulações do pPr, fonte e tamanho do símbolo, sufixo, `isLgl`, `lvlRestart`, estilo
  ligado, marcador de figura; `nsid`, `tmpl`, `multiLevelType`, `styleLink`,
  `numStyleLink`), cada `w:num` (com `lvlOverride`, `startOverride` e `lvl`) e cada
  `w:numPicBullet` (com a imagem e as relações do `numbering.xml`). Sem mudança, o
  `numbering.xml` volta byte a byte; com mudança, as definições novas vão para o fim e o
  resto volta igual (c14n). Formatos calculados: decimal, decimalZero, letras, romanos,
  ordinal, cardinalText e ordinalText (português), círculo, parênteses, ponto, largura
  total, hex, chicago, none e bullet; os outros voltam ao arquivo e aparecem em decimal.
- Parágrafo: `Paragrafo.lista` (numId) e `lista_nivel` (ilvl), diretos; o tipo
  (`numeracao`) passa a ser só informativo e fica fora da comparação. A lista do estilo
  (Título numerado, List Bullet) volta a ficar no estilo e o parágrafo herda: a decisão do
  M6 (passar o numPr do estilo ao parágrafo) foi revertida. numId 0 desliga a lista do
  estilo.
- Cálculo como o Word (`Contador`): contadores da abstrata, compartilhados entre
  instâncias sem sobrescrita (a numeração continua depois de parágrafos comuns e em outra
  lista da mesma definição); `startOverride` reinicia na primeira vez; o nível de cima
  reinicia os de baixo (`lvlRestart` muda a regra); nível pulado mostra 0 ("1.0.1");
  `isLgl` mostra os níveis em decimal.
- Tela: o número é pintado pela mesma função da folha (tela, PDF e impressão), na fonte
  do parágrafo com o rPr do nível (Symbol e Wingdings com a fonte; sem ela, o caractere
  Unicode parecido), ou a imagem do marcador de figura. O texto da primeira linha começa
  onde o Word o põe: no recuo deslocado, na próxima tabulação, depois de um espaço ou
  colado ao número (`w:suff`). O `.txt` leva o número e o sufixo. Decisão e alternativa
  (QTextList com prefixo, que não faz "1.1.1") em docs/ARQUITETURA.md.
- Edição (`edicao/listas.py`), cada comando um passo de desfazer: Marcadores e Numeração
  ligam e desligam; a seta abre a galeria (•, ○, ▪; 1., 1), a., A., i., I.) e a Lista de
  vários níveis (1/1.1/1.1.1, Capítulo/Seção, títulos numerados ligados a Título 1 a 3,
  com o numPr nos estilos); Reiniciar em 1, Continuar numeração e Definir valor de
  numeração (na galeria e no menu do botão direito); Tab e Shift+Tab no começo do item
  mudam o nível (no título numerado pelo estilo, troca Título 1 por Título 2); Enter num
  item vazio sobe um nível ou sai da lista; Backspace no começo tira o número sem mover o
  texto e, de novo, tira o recuo; Aumentar e Diminuir recuo num item mudam o nível.
  Copiar e colar no EditDoc mantém a lista (também entre janelas: a definição vai junto);
  `<ol>` e `<ul>` colados de outro programa viram lista do EditDoc.
- Avisos: LISTA e LISTA_NIVEL deixam de aparecer para o que é preservado; ficam para numId
  que não existe, nível fora de 0 a 8 e numeração acima dos limites. LISTA_EM_CAIXA só
  aparece quando a numeração do arquivo não pode ser lida: com ela lida, o numPr dentro da
  caixa de texto fica.
- Validador e conferência: numId citado existe (corpo, cabeçalho, rodapé e estilos),
  abstractNumId existe, ilvl de 0 a 8, ids únicos, `lvlPicBulletId` com `numPicBullet`;
  a conferência compara o numId e o nível de cada parágrafo. Limites contra arquivo hostil:
  2000 abstratas, 10.000 instâncias, 512 marcadores de figura, 32 níveis e 32 sobrescritas
  por definição, texto do número com 256 caracteres; acima disso a numeração não é lida
  (aviso LISTA).
- Testado com um manual real (não incluído no repositório), aberto e salvo como outra
  cópia pela janela: o `numbering.xml` (16 abstratas, 16 instâncias, marcadores Symbol,
  Wingdings e Courier New) volta igual em c14n; o numPr dos 19 parágrafos numerados e dos
  3 estilos com lista volta igual; a cópia passa no validador e na conferência. Avisos ao
  abrir: na 0.1.3, LISTA 10 (com perda); na 0.1.4, nenhum aviso de lista (ficam
  CONTEUDO_CONTROLADO 1 e FORMATACAO 157, com perda, e CAIXA_DE_TEXTO 6 e
  IMAGEM_FLUTUANTE 2, preservados).
- Suíte nova `tests/teste_listas.py` (100 verificações), com fixtures em código e os
  números esperados escritos à mão. Checagens reescritas, porque testavam a decisão antiga
  ou o QTextList: `teste_docx_qt.py` (listas: as mesmas verificações pela propriedade do
  bloco e pelo número pintado), `teste_formatacao.py` e `teste_estilos.py` (o item está na
  lista pela propriedade do bloco, não pelo `textList()`; o numPr fica no estilo e o
  parágrafo herda; o documento de comparação leva os catálogos), `teste_objetos_opacos.py`
  (o numPr da caixa fica; sai só com a numeração ilegível) e `teste_exibir.py` (o recuo
  esquerdo de 1 cm é 567 twips no bloco, não 567/15).

## 0.1.3 - 2026-10-13

Partes do pacote, hiperlinks e campos deixam de sair do arquivo ao salvar.

Defeito: salvar um `.docx` real pelo EditDoc tirava do arquivo, sem aviso, as propriedades
personalizadas (`docProps/custom.xml`), os itens `customXml` (metadados do SharePoint), a
tabela de fontes, as configurações da Web e as notas separadoras, e refazia o
`settings.xml` (compatibilidade, rsids, variáveis do documento e proteção sumiam). Os
hiperlinks viravam texto (aviso HIPERLINK, com perda) e todo campo que não era número de
página (sumário, PAGEREF, REF, DATE...) virava texto fixo (aviso CAMPO, com perda). Causa:
o escritor gravava só o que ele gera, e o modelo não tinha onde guardar o destino de um
link nem o código de um campo.

- Partes do pacote (`formato_docx/pacote.py`): toda relação do documento que o texto não
  cita e toda relação do pacote é classificada. O que o EditDoc não edita volta byte a
  byte, com o fecho das relações e um Override por parte: customXml (item, itemProps e
  relações), custom.xml, fontTable com as fontes embutidas, webSettings, glossário,
  people.xml. Nenhuma parte sai calada: o que não volta tem aviso próprio
  (PARTE_PERDIDA para relação quebrada, XML inválido ou limite; MACROS para vbaProject e
  personalizações; ASSINATURA para a assinatura digital, que deixaria de valer;
  COMENTARIO; NOTA; MINIATURA, sem perda, para a miniatura que mostraria o conteúdo
  antigo). Controles ActiveX também não voltam (OBJETO_PERDIDO).
- `settings.xml`: o original volta inteiro, com as relações (o modelo anexado). O EditDoc
  só muda o que controla: `w:evenAndOddHeaders`, na ordem do esquema, e as referências às
  notas separadoras quando as notas não voltam. Sem mudança, os bytes são os mesmos.
- Notas: `footnotes.xml` e `endnotes.xml` voltam com as notas separadoras; as notas de
  verdade continuam fora, com o aviso NOTA.
- `core.xml` e `app.xml`: os originais voltam (assunto, palavras-chave, categoria,
  revisão, empresa, gerente), com título, autor, datas e o aplicativo reescritos.
- Hiperlinks: o trecho do link guarda o destino (endereço externo ou marcador, com a dica,
  o histórico e o quadro); ao salvar, `w:hyperlink` com relação externa nova (sem colisão
  com imagens e objetos) ou `w:anchor`. Na tela, o link tem o estilo do arquivo (azul
  sublinhado) e o `anchorHref` do Qt. Ctrl+clique abre o link: http, https e mailto abrem
  direto; arquivo, rede e outros esquemas só com confirmação; javascript:, vbscript: e
  data: nunca; o link interno leva ao marcador. Inserir > Link (Ctrl+K) insere no cursor,
  põe o link na seleção (mantendo a formatação) ou edita o link do cursor, para um
  endereço ou um marcador; Remover link tira o link e o estilo Hyperlink. Cada comando é
  um passo de desfazer. Digitar logo depois de um link não o estende.
- Marcadores (`w:bookmarkStart`/`End`): todos voltam, inclusive os que estão entre
  parágrafos, com id único e em pares. Na tela não têm largura; as setas, o Backspace e o
  Delete passam por eles (não se apagam sem ser vistos).
- Campos: todo campo volta como campo, simples (`w:fldSimple`, gravado como complexo) ou
  complexo, inclusive aninhados (o PAGE dentro do código de um IF), o sumário de vários
  parágrafos com os hiperlinks e os PAGEREF dentro, o XE sem resultado e o campo de
  formulário com o `w:ffData`; `w:dirty` e `w:fldLock` voltam. O último resultado é texto
  editável (vira o novo resultado), entre dois colchetes finos que não saem na impressão.
  Apagar só o começo ou só o fim de um campo grava XML válido: o campo vira texto comum,
  com o aviso CAMPO_INCOMPLETO (com confirmação). O EditDoc não recalcula esses campos e
  não marca o sumário como sujo: ver docs/ARQUITETURA.md.
- Avisos: HIPERLINK e CAMPO só aparecem para o que não pode voltar (relação quebrada,
  campo sem fim no arquivo, limites), com os textos revistos; novos PARTE_PERDIDA,
  MINIATURA, ASSINATURA, MARCADOR e CAMPO_INCOMPLETO.
- Validador e conferência: campos equilibrados na parte inteira (o código no parágrafo do
  begin), marcadores com id e nome únicos e em pares, `r:id` de hiperlink para relação
  externa do tipo hyperlink, relações e Overrides das partes preservadas; a conferência
  compara o destino de cada link, as marcas de campo e de marcador de cada parágrafo e o
  conteúdo das partes preservadas.
- Limites contra arquivo hostil: 20.000 campos, links e marcadores; instrução de campo de
  4096 caracteres; endereço de 8192; 8 campos um dentro do outro; 1000 partes
  preservadas, 6 níveis de relação e 256 MB.
- Testado com um manual real (sumário num controle de conteúdo, 11 PAGEREF, 19 hiperlinks,
  6 marcadores, 4 itens customXml), aberto e salvo como outra cópia pela janela:

  | Item | Original | Salvo pela 0.1.2 | Salvo pela 0.1.3 |
  |---|---|---|---|
  | Partes do pacote | 75 | 58 (18 saíam sem aviso) | 76 (as 75 e uma cópia de imagem, como na 0.1.2) |
  | customXml, custom.xml, fontTable, webSettings, notas | presentes | fora | iguais byte a byte |
  | settings.xml | do Word | refeito | igual byte a byte |
  | `w:hyperlink` | 19 | 2 (os das caixas de texto) | 19 |
  | fldChar begin / separate / end | 13 / 13 / 13 | 1 / 1 / 1 | 13 / 13 / 13 |
  | instrText TOC / PAGEREF / PAGE | 1 / 11 / 1 | 0 / 0 / 1 | 1 / 11 / 1 |
  | bookmarkStart / bookmarkEnd | 6 / 6 | 0 / 0 | 6 / 6 |
  | txbxContent / w:drawing | 6 / 49 | 6 / 49 | 6 / 49 |
  | controle de conteúdo (`w:sdt`) | 1 | 0 (aviso) | 0 (aviso) |

  Avisos ao abrir o original: na 0.1.2, CAIXA_DE_TEXTO 6 e IMAGEM_FLUTUANTE 2
  (preservados) e, com perda, CONTEUDO_CONTROLADO 1, FORMATACAO 157, HIPERLINK 17,
  CAMPO 12 e LISTA 10; na 0.1.3, HIPERLINK e CAMPO deixam de existir. A cópia salva
  reabre só com os dois avisos sem perda, e passa no validador.
- Suítes novas: `tests/teste_partes_pacote.py`, `tests/teste_hiperlinks.py` e
  `tests/teste_campos_gerais.py`, com fixtures geradas em código
  (`fixtures_docx.docx_com_pacote_do_word`, `docx_com_links`, `docx_com_campos`).
  Checagens reescritas em `teste_campos.py` (o DATE, o campo que atravessa parágrafos e o
  IF com PAGE eram esperados como texto com o aviso CAMPO e passam a ser preservados; o
  texto que está no código de 20 campos aninhados não aparece no Word, e a checagem passa a
  exigir o aviso e o arquivo válido) e em `teste_acessibilidade.py` (o diálogo de link
  entra na lista: nove diálogos, não oito).

## 0.1.2 - 2026-10-13

Caixas de texto, formas e objetos deixam de sair do arquivo ao salvar.

Defeito: um `.docx` com caixas de texto abria com o aviso "6 caixas de texto ou formas não
são editadas nesta versão. O texto delas sai do arquivo ao salvar.", e salvar pelo
EditDoc apagava as caixas, as formas, os gráficos, o SmartArt, os objetos OLE, as equações
e a posição das imagens flutuantes. Causa: o leitor só transformava em modelo o que o
EditDoc edita, e o resto virava aviso com perda.

- Objeto opaco: o que o EditDoc não edita mas pode guardar entra no modelo como um objeto
  no lugar dele no parágrafo, com o XML original (o `w:r` com o desenho, o VML, o OLE ou o
  `mc:AlternateContent` inteiro, com o Choice e o Fallback; ou o `m:oMath`) e todas as
  partes que ele usa: imagens de dentro da forma, gráfico com a planilha e o estilo,
  partes do SmartArt (inclusive o desenho apontado pelo `relId` do `dataModelExt`),
  embeddings OLE e a prévia EMF, hiperlinks de dentro da caixa. Ao salvar, o XML volta
  igual, com os rIds renumerados, cada parte com nome livre, relações e tipo de conteúdo;
  a raiz da parte declara os namespaces e o `mc:Ignorable` de origem. Vale para o corpo,
  o cabeçalho e o rodapé.
- Imagem flutuante (`wp:anchor`) deixou de virar imagem na linha: volta ao arquivo com a
  posição e a quebra de texto intactas. Imagem EMF, WMF, SVG ou vinculada a endereço
  externo também é preservada (antes saía do arquivo).
- Na tela, o objeto é um quadro tracejado com o nome ("Caixa de texto: Texto da caixa…",
  "Gráfico", "SmartArt", "Objeto", "Equação: x=…"), do tamanho do objeto quando ele está
  na linha, ou uma etiqueta no ponto da âncora quando é flutuante; a imagem flutuante
  mostra uma miniatura. Delete e Backspace apagam o objeto inteiro (e as partes dele saem
  do arquivo, sem sobrar parte órfã), Ctrl+Z o traz de volta, e o texto digitado logo
  depois dele não vira objeto. Copiar e colar leva o texto, não o objeto, e a barra de
  status avisa.
- Avisos: caixa de texto, forma, objeto incorporado, equação, imagem flutuante e imagem em
  formato que a tela não mostra passam a dizer "são preservadas, mas não podem ser
  editadas nesta versão" e não pedem mais a confirmação de perda ao salvar. Continuam com
  perda (aviso novo): o objeto que não pode ser preservado inteiro (`OBJETO_PERDIDO`:
  referência quebrada, parte proibida ou acima dos limites), a imagem com relação
  quebrada (`IMAGEM`), e, dentro de uma caixa de texto, a referência a nota ou comentário
  e a numeração de lista (`LISTA_EM_CAIXA`), porque essas partes não voltam ao arquivo.
- Ids únicos: `wp:docPr`, `w14:paraId` e `anchorId` repetidos entre objetos ganham valor
  novo no objeto que chega depois (o Choice e o Fallback do mesmo objeto continuam com o
  mesmo id), e o id das imagens do EditDoc nunca colide com o de um objeto.
- Limites contra arquivo hostil: 2000 objetos por documento, 4 MB de XML por objeto,
  64 MB de XML somado, 64 partes e 6 níveis de relação por objeto; parte de documento,
  estilos, tema, configurações, cabeçalho ou propriedades nunca vai junto com um objeto.
- Validador e conferência: as regras de ordem, `xml:space`, tabela, campo e estilo pulam
  o conteúdo dos objetos (vem do arquivo de origem); `wp:docPr` único e `r:id` com relação
  valem também dentro deles, inclusive o `o:relid` do VML e os `r:id` das partes do
  gráfico e do SmartArt. A forma pode ter altura zero (linha reta). A conferência
  pós-gravação compara cada objeto, no lugar, pelo XML e pelo conteúdo das partes, sem
  depender dos nomes e dos ids renumerados.
- Testado com um manual real (6 caixas de texto e formas, 2 imagens
  flutuantes, 41 imagens): depois de salvar, as mesmas 49 `w:drawing`, 6 `txbxContent` com
  o mesmo texto, 6 `mc:AlternateContent`, as 42 imagens distintas, validador sem
  problema e nenhum aviso com perda ligado a objeto.
- Suíte nova `tests/teste_objetos_opacos.py` (79 verificações), com fixtures geradas em
  código (`fixtures_docx.docx_com_objetos`). Checagens reescritas: em
  `teste_imagens.py`, a imagem flutuante e o EMF eram esperados como perda e passam a ser
  preservados; em `teste_documento.py`, a perda que a confirmação lista deixou de ser a
  equação (preservada) e passou a ser a quebra de coluna, com contraprova de que a
  equação não aparece.

## 0.1.1 - 2026-10-13

Correção de legibilidade no tema escuro.

- A faixa amarela de aviso ("Este documento tem recursos que o EditDoc não edita…") ficava
  ilegível no tema escuro: o texto e os botões herdavam a cor clara da paleta sobre o fundo
  amarelo fixo (contraste 1:1). Agora o texto e os botões da faixa são sempre escuros
  (14,8:1). Teste novo em `teste_acessibilidade.py` com a paleta escura, que falha sem a
  correção.
- A mensagem de erro do diálogo de estilo usa um vermelho claro no tema escuro.

## 0.1.0 - 2026-10-12

Polimento (M8): a primeira versão completa do roteiro. Recuperação automática,
preferências, acessibilidade e a correção de limites que ficaram dos marcos anteriores.

- Recuperação automática: a cada 10 minutos (configurável de 1 a 120, ou desligada) e
  também depois de 300 alterações seguidas, com uma pausa curta, o documento alterado é
  copiado para `%LOCALAPPDATA%\EditDoc\Recuperacao`, num `.docx` próprio, com gravação
  atômica e os metadados (caminho original, nome, hora, versão, pid e os avisos de perda
  do arquivo original). Nunca na pasta do documento, nunca por cima dele. Documento limpo
  não gera cópia; salvar apaga a cópia; fechar normalmente (salvando ou descartando)
  apaga a cópia e a trava.
- Depois de uma queda, a abertura seguinte mostra "Recuperação de documentos" (não modal):
  abrir (a cópia vira uma janela alterada, sem caminho, com o título "(recuperado)"; salvar
  sugere o lugar de onde ela veio e ainda pede a confirmação das perdas do original),
  salvar como `.docx` ou descartar (com confirmação). O que ficar na lista é oferecido de
  novo. Também em Arquivo > Recuperar documentos.
- Várias janelas e várias instâncias não se atrapalham: cada janela tem a sua cópia e uma
  trava de arquivo (LockFile) que o Windows solta quando o processo morre. Só a cópia sem
  dono é oferecida, e uma cópia aberta numa janela não é oferecida em outra. Cópia gravada
  pela metade (o `.docx` não tem o tamanho anotado) não é oferecida.
- Arquivo > Opções: fonte e tamanho do documento novo, papel padrão (A4, Carta, Ofício),
  unidade da régua (centímetros ou polegadas), recuperação automática (ligada e
  intervalo), abrir o PDF depois de exportar, quantidade de documentos recentes (0 a 50) e
  limpar a lista, e o tema (claro, escuro ou igual ao Windows). Cada valor é validado
  (tipo e faixa); fora disso volta ao padrão. O documento aberto não muda; o novo usa as
  preferências, e a fonte escolhida vai para o docDefaults do arquivo gravado.
- Acessibilidade: todo botão, campo, lista e aba tem nome e descrição para o leitor de
  tela (o botão "N" é "Negrito"; as miniaturas da galeria, "Estilo Título 1"); a régua, a
  barra de status, os diálogos e os painéis também. O documento aparece para o leitor de
  tela como texto editável, com o nome do arquivo, "Página X de Y" e o parágrafo do cursor;
  trocar de página anuncia a página. Ordem de Tab de cada diálogo conferida.
- Teclado na faixa, como no Word: Alt (apertar e soltar) ou F10 mostra as dicas de tecla
  (P, N, L, E, H nas abas; A no Arquivo; 1 e 2 no Desfazer e Refazer); a letra da aba mostra
  as dos botões, e a do botão executa o comando. Setas, Tab, Enter, Espaço e Esc navegam na
  faixa; F6 e Shift+F6 andam entre o documento, a faixa, a busca, os painéis e o zoom.
  AltGr (teclado ABNT2) não abre as dicas. O Tab no documento continua sendo tabulação.
- Contraste: o título dos grupos da faixa e o aviso do painel de navegação usavam o cinza
  "mid" do Qt (1,7 para 1 sobre o fundo); agora usam a cor do texto.
- Espaçamento do docDefaults na tela: o "8 pt depois e 1,08 entre linhas" do Word passa a
  aparecer fora das tabelas (dentro delas o "Table Grid" zera, como no Word), sem virar
  formatação direta ao salvar. O documento novo nasce com ele, que é o que o EditDoc já
  gravava no arquivo: antes a tela mostrava 0 e o Word, 8 pt.
- Tabela mais larga que o corpo entra na margem direita, como no Word, na tela, na
  impressão e no PDF (antes era cortada na margem).
- Medido e travado em teste: a linha vazia antes de uma tabela no começo do documento ou
  entre duas tabelas não aparece no Qt 6.11.2 (o bloco que o Qt exige ali não ocupa
  altura). A pintura do cabeçalho e do rodapé fora do cache, num documento de 94 páginas,
  fica entre 1,1 e 11,7 ms por quadro (p95), dentro do limite de 16 ms do Gate do M3: não
  precisou de otimização (números em docs/SPIKES.md).
- A autoverificação do executável grava uma cópia de recuperação numa pasta temporária,
  simula a queda, lê a cópia de volta e a descarta.
- README completo para o usuário, CONTRIBUTING.md e a arquitetura atualizada.

Limites que ficaram: a altura de linha da tabela continua só no arquivo (a tela não a
aplica: precisaria refazer a altura a cada tecla); desfazer uma mudança de estilo feita
durante a edição do cabeçalho continua no desfazer do corpo (o catálogo de estilos mora no
corpo). O leitor de tela não navega por palavra ou linha dentro do documento: no PySide6
6.11.2, a interface de texto acessível feita em Python derruba o processo quando o UIA do
Windows lista os padrões do elemento (medido; docs/SPIKES.md). A abertura no Word e o uso
com NVDA ou Narrador dependem de conferência manual.

## 0.0.10 - 2026-10-12

Impressão e PDF (M7). O documento sai em PDF e na impressora exatamente como está na tela:
mesmas quebras de página, cabeçalho e rodapé com o número certo em cada folha, tabelas e
imagens.

- Arquivo > Exportar > PDF: escolhe todas as páginas, a página atual ou um intervalo
  ("1-3, 5"; intervalo inválido é recusado com aviso), e se o PDF abre ao terminar. O papel e
  a orientação são os do documento (A4, Carta, Ofício, paisagem ou tamanho livre), o texto
  sai como texto (pode ser selecionado e pesquisado no leitor), com as fontes embutidas, e o
  PDF leva o título e o autor do documento e "EditDoc 0.0.10" como criador. A gravação é
  atômica e conferida: um PDF que já existia só é trocado depois que o novo foi relido do
  disco.
- Arquivo > Imprimir (Ctrl+P): diálogo do Windows com impressora, intervalo, página atual,
  cópias e agrupar; a impressora recebe o papel do documento. Se ela não tem esse papel, o
  EditDoc pergunta antes de imprimir no papel dela; sem impressora instalada, avisa e sugere
  o PDF.
- Arquivo > Visualizar impressão (Ctrl+F2): as folhas como sairão no papel, com navegação,
  zoom, uma ou várias páginas e o botão Imprimir.
- Documento longo: exportar e imprimir mostram o progresso, página a página, com
  Cancelar; cancelar a exportação não grava nada.
- Arquivo > Exportar > Texto sem formatação (.txt): o texto do corpo em UTF-8, um parágrafo
  por linha, as células da tabela separadas por tabulação.
- Nada da tela vai para o papel: fundo, sombra, marcas de formatação, linha de quebra de
  página, o cabeçalho esmaecido e o rótulo da edição do cabeçalho, cursor e seleção.
- A autoverificação do executável exporta e imprime (em PDF) um documento de duas páginas e
  confere as páginas, o texto e a fonte embutida.

Limites deste marco: a imagem sai com a resolução da prévia da tela (até 1800 px no lado
maior), não com os bytes originais. A impressora com área não imprimível corta o que estiver
na borda da folha. "Salvar como" continua só `.docx`: o PDF é exportação, para que salvar
nunca troque o documento por um arquivo que não volta a abrir no EditDoc. O `.txt` leva o
último valor guardado dos campos de número de página. A impressão em impressora real
depende de conferência manual (amostra em `tests/saida/amostra_m7.pdf`, gerada pela suíte).

## 0.0.9 - 2026-10-12

Estilos e faixa final (M6). Os estilos do `.docx` abrem, aparecem na tela, são aplicados e
modificados no EditDoc e voltam ao arquivo; a faixa ganha a galeria de estilos e as abas
Inserir, Layout e Exibir completas.

- Estilos no `.docx`: o `styles.xml` vira o catálogo do documento, com `docDefaults`, estilos
  de parágrafo e de caractere, `basedOn`, `next`, `link`, `qFormat`, `uiPriority`,
  `semiHidden` e `unhideWhenUsed`. A herança (`basedOn`) é resolvida para a tela. O estilo
  que o EditDoc não muda volta byte a byte, com o `latentStyles`, os estilos de tabela, os
  que o editor não usa e as extensões do Word (`w14`, `w15`); o estilo alterado só tem
  reescrito o que mudou (a cor nova tira o `themeColor`, que venceria o valor). O tema
  (`theme1.xml`) volta igual, e a fonte de tema (`asciiTheme`) é resolvida na tela.
- Documento novo com o conjunto do Word: Normal, Título, Subtítulo, Título 1 a 3, Citação,
  Parágrafo da Lista e Sem Espaçamento (parágrafo), Ênfase e Forte (caractere), com os ids
  em inglês (`Heading1`) e os nomes em português. Estilo interno que falta num arquivo do
  Word (Título 2, por exemplo) é criado quando é usado, como o Word faz.
- Formatação direta = efetivo menos estilo: o parágrafo e o run guardam só o que difere do
  estilo. O `w:pStyle` e o `w:rStyle` são gravados só para estilo do catálogo; o validador
  do pacote recusa referência quebrada.
- Comandos: aplicar estilo de parágrafo e de caractere; Limpar toda a formatação (volta ao
  Normal) e Limpar formatação de caractere (Ctrl+Espaço, antes era o Limpar); Enter no fim
  de um Título usa o estilo seguinte (`next`); Atualizar estilo para corresponder à seleção;
  Modificar estilo (fonte, tamanho, negrito, itálico, sublinhado, cor, alinhamento,
  espaçamento antes e depois, entre linhas, recuos, baseado em e próximo estilo); Criar um
  estilo a partir da seleção. Mudar um estilo atualiza todos os parágrafos que o usam,
  inclusive no cabeçalho e no rodapé, mantendo a formatação direta, e um desfazer devolve o
  estilo e os parágrafos.
- Atalhos: Ctrl+Alt+1, 2 e 3 (Título 1 a 3), Ctrl+Shift+N (Normal), Ctrl+Alt+Shift+S
  (painel de estilos) e Ctrl+Shift+8 (marcas de formatação).
- Galeria de estilos na Página Inicial: miniaturas com a aparência do estilo, o estilo do
  cursor marcado, setas para rolar, botão para ver todos, menu de contexto (Atualizar,
  Modificar). Painel de estilos (lista completa, com visualização opcional) num painel
  lateral.
- Faixa: Fonte e Parágrafo em duas linhas; abas Inserir (Páginas, Tabelas, Ilustrações,
  Cabeçalho e Rodapé), Layout (Configurar Página; recuo esquerdo e direito e espaçamento
  antes e depois do parágrafo) e Exibir (Régua, Painel de Navegação, marcas de formatação,
  painel de estilos; zoom 100%, Uma Página, Várias Páginas e Largura da Página). Cada aba
  recolhe sozinha; a galeria tem preferência sobre o grupo Edição e vira o botão Estilos
  na janela estreita.
- Exibir: marcas de formatação (¶, · nos espaços, → nas tabulações) pintadas por cima do
  texto, sem mudar o layout; Várias Páginas põe as folhas lado a lado; painel de navegação
  com os títulos (estilos de Título e `outlineLvl` direto), em árvore, e o clique leva ao
  título.
- Listas convivem com estilos: a lista ligada por um estilo do Word (List Bullet) passa ao
  parágrafo; aplicar um Título num item de lista mantém a lista.
- Recuo à direita e nível de estrutura (`outlineLvl`) do parágrafo entram no modelo: antes
  eram perdidos (o recuo direito com aviso; o nível, sem aviso).
- A fonte e o tamanho padrão do arquivo (`docDefaults`) passam a ser os da tela, e o aviso
  PADRAO_DO_DOCUMENTO deixou de ser emitido: o `docDefaults` volta ao arquivo como veio.
- A conferência do arquivo gravado compara também o estilo de cada parágrafo e os estilos
  de caractere dele.

Limites deste marco: numeração completa (níveis, formatos, listas definidas por estilo com
o seu próprio `numbering.xml`) continua fora: a lista do estilo vira lista simples do
parágrafo. Desfazer uma mudança de estilo feita durante a edição do cabeçalho fica no
desfazer do corpo. As abas contextuais de tabela e de imagem ficam para depois. Espaçamento
do `docDefaults` (8 pt depois, 1,08 entre linhas) continua sem aparecer na tela. A abertura
no Word ainda depende de conferência manual (amostra em
`tests/saida/amostra_m6_estilos.docx`, gerada pela suíte).

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
