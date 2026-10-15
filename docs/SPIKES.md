# Spikes de viabilidade (antes do M1)

Feitos em 11/10/2026, na máquina de desenvolvimento (Windows 11, Python 3.13.14,
PySide6 6.11.2). O código está em `spikes/`, fora do pacote `editdoc/`: não entra
no `.exe` nem nos testes oficiais. Cada spike tem o seu `RESULTADO.md` com a tabela
completa e o roteiro das pendências manuais.

Reproduzir (a partir da raiz do repositório):

```
.venv\Scripts\python.exe -B spikes\pagina\testes_pagina.py
.venv\Scripts\python.exe -B spikes\docx\testes_docx.py
```

## Spike A: visão em páginas sobre QTextDocument

**Veredito: passa com ressalvas.** A arquitetura serve para paginar, medir fronteiras,
fazer hit-test, exportar, pré-visualizar e desfazer, com números. A pintura de um
quadro não fecha de forma estável.

| Critério | Resultado | Situação |
|---|---|---|
| C1 layout, edição e pintura | layout inicial 0,32 s (95 páginas); edição p95 13 a 26 ms; pintura p95 a 25% de 17 a 19 ms (limite 16) | **falha no limite**, varia entre rodadas |
| C2 fronteiras | 0 linhas cruzando em 100 edições; controle acusa 102 | passa |
| C3 hit-test | 3000 ida-e-volta, maior diferença 0 | passa |
| C4 seleção entre páginas | pixels azuis nas páginas 2 a 7; Ctrl+C igual; tabela colada mantém 3x3 | passa |
| C5 teclas mortas ABNT2, AltGr | não automatizável | **pendente manual** (roteiro em `spikes/pagina/RESULTADO.md`) |
| C6 desfazer | 50 operações; desfazer tudo gera HTML idêntico | passa |
| C7 WYSIWYG | 95 páginas na tela, na prévia e no PDF; 0,00% de pixels diferentes | passa |
| C8 cabeçalho e rodapé | 191 checagens sem erro; 0,21 ms por página | passa |
| C9 zoom | 0,04 ms, sem relayout | passa |
| C10 HiDPI | bordas em pixel inteiro; hit-test idêntico em DPR 1, 1,5 e 2 | passa |
| C11 tabela entre páginas | cabeçalho repete; 12 células divididas; Tab e clique na fronteira corretos | passa |
| C12 imagem grande | 3000 x 3000 px limitada a 605 x 605 px96 | passa |
| C13 ciclo de vida | 100 documentos por modo, sem falha nos modos de produção | passa |

### O que o spike mudou no desenho

1. **Pintura.** O custo cresce com os pixels visíveis, sobretudo em zoom alto e
   HiDPI. Um cache de imagem por página (invalidado na edição) é a saída provável,
   mas **não foi testado**. Fica como condição para o início do M3.
2. **Hit-test.** `QTextLayout.position()` é relativa dentro de célula de tabela:
   usar `blockBoundingRect` para as coordenadas. O `FuzzyHit` atravessa a fronteira
   de página, então o clique precisa ser restrito à página em que caiu.
3. **Qt não faz viúva nem órfã.** Medido: 15 órfãs e 13 viúvas em 95 páginas.
4. **Dispositivo destruído com `QPainter` ativo derruba o processo.** O dispositivo de
   layout precisa viver mais que o painel.
5. **Teclado de teste.** `QTest.keyClick` com acento insere o byte errado, e
   `keyClicks` com acento derruba o processo. Acento entra por `QKeyEvent` com `text()`.
6. **Testes de renderização de texto.** Em offscreen não há famílias de fonte (0
   contra 238 no Windows), e o texto vira caixas. Os testes visuais precisam carregar
   uma fonte com `QFontDatabase.addApplicationFont`.

### Decisão

Arquitetura aprovada para o M3, com a condição do cache de página. O M1 usa a visão
provisória sobre `QTextEdit`, como já estava no roteiro, então a falha de C1 não bloqueia o M1.

## Spike B: ida-e-volta .docx com lxml

**Veredito: passa com ressalvas.** Leitor e escritor próprios sobre `zipfile` e
`lxml` funcionam, com ida-e-volta exata do modelo e validação de ordem. A abertura
no Word não foi verificada, porque não há Word nesta máquina.

| Teste | Resultado |
|---|---|
| T1 ida-e-volta do modelo | 10 parágrafos, 15 runs, 0 avisos |
| T2 python-docx como oráculo (só leitura) | 155 verificações, 0 divergências |
| T3 ordem de filhos e `xml:space` | 0 violações; contraprovas acusam os dois defeitos sabotados |
| T4 integridade do pacote OPC | 8 partes, 5 alvos resolvidos; 3 contraprovas acusadas |
| T5 arquivos hostis | 16 casos com o código esperado; maior tempo 0,026 s |
| T6 QTextDocument | 12 de 12 campos sem perda na fixture |
| T7 desempenho | gravar 0,40 s, ler 0,15 s (meta 5 s); pico de RSS 80 MB sobre base de 34 MB |
| T8 idempotência | modelo e bytes idênticos na segunda ida |

Reexecutei a suíte: 39 verificações, 0 falhas, código 0.

### O que o spike mudou no desenho

1. **Qt não limpa sublinhado com `setFontUnderline(False)`.** O correto é
   `setUnderlineStyle(NoUnderline)`. O negrito em três estados (ligado, desligado,
   indefinido) sai de `hasProperty`, sem passar por HTML.
2. **Qt colapsa margens verticais para o maior valor** (16 px medidos). Se o Word
   soma, o layout diverge. Hipótese não verificada: fica como risco registrado.
3. **`xml:space` só é pego pelo validador de regras do Word.** Sabotado, o round-trip
   e o python-docx continuam passando. Por isso a suíte de gravação precisa do validador.
4. **No Windows, `zipfile` troca `\` por `/` em `ZipInfo.filename`.** O leitor valida
   `orig_filename`; sem isso uma barra invertida passaria.
5. **Runs vizinhos com a mesma formatação se fundem no Qt** (3 viram 2). A ida-e-volta
   compara o modelo normalizado, não a contagem de runs.

Não verificado: Word abrir sem reparo e sem Modo de Compatibilidade; numeração;
campos; imagens; paginação; estilos (fora do modelo ainda); `sectPr`, `tblPr` e styles.

### Decisão

Escritor e leitor próprios, como previsto, a partir do M2. Abrir a amostra no Word
continua como aceite manual.

## Correção feita no M2

A afirmação de que `setFontUnderline(False)` não limpa o sublinhado não se
reproduziu no PySide6 6.11.2: o merge com esse formato limpa o estilo. O que se
reproduz é outra coisa: texto inserido sem formato herda o sublinhado do vizinho.
A ponte usa `setUnderlineStyle(NoUnderline)` de forma explícita, o que vale nos
dois casos. Ver `tests/teste_docx_qt.py`.

## Gate do M3: cache de página e teto de zoom

Feito em 12/10/2026, na mesma máquina dos spikes (Windows 11, Python 3.13.14, PySide6 6.11.2,
`QT_QPA_PLATFORM=offscreen`, fonte Segoe UI, sem cabeçalho). Documento de 582 parágrafos, 95 páginas
A4 com margens Normal. O quadro é `viewport().grab()` do `PainelDocumento` de produção, um processo por
caso, DPR definido por `QT_SCALE_FACTOR`. Gate: p95 ≤ 16 ms em todos os cenários com cache.

**Veredito: PASSA, com o teto de zoom.** Com cache e teto, todos os cenários medidos ficam com p95 ≤ 16 ms
(pior caso: 12,2 ms, DPR 2 a 150%, troca de zoom, fonte de 14 pt). O que faz o gate passar é o teto; o
cache reduz o quadro quente de 3 a 13 ms para 0,2 a 5 ms e dá margem em DPR 2.

### O que foi medido e a decisão

1. **Sem teto, 400% não fecha.** Protótipo, pintura direta sem cache, sem teto: DPR 1,5 a 400% tem quadro
   quente p95 de 29,6 ms, rolagem de 54,3 ms e troca de zoom de 36,6 ms; DPR 2 a 400% tem quadro quente de
   69,7 ms. A causa: acima de uma certa escala de dispositivo, o Qt pinta o texto por caminho, e isso é
   muito mais caro que pelo cache de glifos. Com 11 pt, 400% em DPR 1 ainda passa (p95 de 2,6 a 6,7 ms, com cache e sem, medido antes do ajuste do teto).
2. **Teto de zoom = 300% de escala de dispositivo** (zoom × DPR ≤ 3). Em DPR 1, o zoom vai a 300%; em
   DPR 1,5, a 200%; em DPR 2, a 150%. Fonte de até 14 pt passa em todos os cenários. Fonte de 16 pt já
   não passa: digitação em 300% chega a 24 ms (p95), e 18 pt piora (81 ms). **Redução de escopo:** o
   pedido era 25% a 400%. O teto é o que o gate permite; a alternativa (400% com fonte de 14 pt) mede
   23 a 25 ms de digitação, e o plano pede explicitamente que o escopo seja reduzido e não o número
   maquiado.
3. **Cache de tiles: adotado.** Tiles de 256 px lógicos na coordenada da própria página, no DPR da tela,
   teto de 64 MB, LRU. Na edição, só sai do cache a faixa da linha alterada; se a altura total do
   documento mudou (Enter, quebra de linha, paginação), sai tudo de baixo. A invalidação roda na próxima
   pintura, com o layout já refeito (ver achado 5).
4. **Com teto, o cache não é o que decide o gate, mas melhora tudo que é quadro quente.** Em DPR 1 a 300%,
   o quadro quente cai de 5,6 para 0,7 ms. A digitação com cache fica igual ou um pouco pior em alguns
   casos (300%, 11 pt: 5,5 contra 4,7 ms), porque o tile da linha editada é refeito inteiro.

### Tabela (p95 em ms, 80 quadros por cenário; troca de zoom: 20 amostras)

| Tela | Zoom | Fonte | Cenário | Sem cache (p95, ms) | Com cache (p95, ms) |
|---|---|---|---|---|---|
| DPR 1 | 25% | 11 pt | quadro quente | 3.0 | 0.3 |
| DPR 1 | 25% | 11 pt | rolagem, 120 px por quadro | 3.9 | 1.2 |
| DPR 1 | 25% | 11 pt | digitar, uma letra por quadro | 2.9 | 1.9 |
| DPR 1 | 25% | 11 pt | digitar, Enter a cada 10 letras | 3.2 | 2.7 |
| DPR 1 | 25% | 11 pt | quadro frio, logo apos trocar o zoom | 2.9 | 2.8 |
| DPR 1 | 100% | 11 pt | quadro quente | 4.3 | 0.5 |
| DPR 1 | 100% | 11 pt | rolagem, 120 px por quadro | 4.0 | 0.5 |
| DPR 1 | 100% | 11 pt | digitar, uma letra por quadro | 4.2 | 0.8 |
| DPR 1 | 100% | 11 pt | digitar, Enter a cada 10 letras | 4.7 | 0.7 |
| DPR 1 | 100% | 11 pt | quadro frio, logo apos trocar o zoom | 3.6 | 3.9 |
| DPR 1 | 300% | 11 pt | quadro quente | 5.6 | 0.7 |
| DPR 1 | 300% | 11 pt | rolagem, 120 px por quadro | 5.6 | 2.2 |
| DPR 1 | 300% | 11 pt | digitar, uma letra por quadro | 4.7 | 5.5 |
| DPR 1 | 300% | 11 pt | digitar, Enter a cada 10 letras | 3.5 | 3.3 |
| DPR 1 | 300% | 11 pt | quadro frio, logo apos trocar o zoom | 3.2 | 3.2 |
| DPR 1 | 25% | 14 pt | quadro quente | 3.0 | 0.2 |
| DPR 1 | 25% | 14 pt | rolagem, 120 px por quadro | 3.2 | 1.1 |
| DPR 1 | 25% | 14 pt | digitar, uma letra por quadro | 2.6 | 1.9 |
| DPR 1 | 25% | 14 pt | digitar, Enter a cada 10 letras | 2.5 | 2.1 |
| DPR 1 | 25% | 14 pt | quadro frio, logo apos trocar o zoom | 2.9 | 2.4 |
| DPR 1 | 100% | 14 pt | quadro quente | 3.4 | 0.5 |
| DPR 1 | 100% | 14 pt | rolagem, 120 px por quadro | 3.8 | 0.5 |
| DPR 1 | 100% | 14 pt | digitar, uma letra por quadro | 4.0 | 0.8 |
| DPR 1 | 100% | 14 pt | digitar, Enter a cada 10 letras | 4.5 | 0.8 |
| DPR 1 | 100% | 14 pt | quadro frio, logo apos trocar o zoom | 3.7 | 4.0 |
| DPR 1 | 300% | 14 pt | quadro quente | 3.5 | 0.8 |
| DPR 1 | 300% | 14 pt | rolagem, 120 px por quadro | 3.7 | 1.9 |
| DPR 1 | 300% | 14 pt | digitar, uma letra por quadro | 4.5 | 6.4 |
| DPR 1 | 300% | 14 pt | digitar, Enter a cada 10 letras | 3.6 | 3.3 |
| DPR 1 | 300% | 14 pt | quadro frio, logo apos trocar o zoom | 3.1 | 3.1 |
| DPR 1,5 | 25% | 14 pt | quadro quente | 2.9 | 0.5 |
| DPR 1,5 | 25% | 14 pt | rolagem, 120 px por quadro | 3.5 | 1.5 |
| DPR 1,5 | 25% | 14 pt | digitar, uma letra por quadro | 3.3 | 1.8 |
| DPR 1,5 | 25% | 14 pt | digitar, Enter a cada 10 letras | 3.1 | 2.6 |
| DPR 1,5 | 25% | 14 pt | quadro frio, logo apos trocar o zoom | 3.2 | 3.1 |
| DPR 1,5 | 100% | 14 pt | quadro quente | 7.5 | 1.0 |
| DPR 1,5 | 100% | 14 pt | rolagem, 120 px por quadro | 7.3 | 1.2 |
| DPR 1,5 | 100% | 14 pt | digitar, uma letra por quadro | 7.9 | 1.7 |
| DPR 1,5 | 100% | 14 pt | digitar, Enter a cada 10 letras | 8.0 | 1.7 |
| DPR 1,5 | 100% | 14 pt | quadro frio, logo apos trocar o zoom | 7.1 | 7.2 |
| DPR 1,5 | 200% | 14 pt | quadro quente | 9.0 | 1.4 |
| DPR 1,5 | 200% | 14 pt | rolagem, 120 px por quadro | 7.8 | 3.2 |
| DPR 1,5 | 200% | 14 pt | digitar, uma letra por quadro | 9.5 | 7.2 |
| DPR 1,5 | 200% | 14 pt | digitar, Enter a cada 10 letras | 8.9 | 6.1 |
| DPR 1,5 | 200% | 14 pt | quadro frio, logo apos trocar o zoom | 7.0 | 6.9 |
| DPR 2 | 25% | 14 pt | quadro quente | 6.4 | 3.6 |
| DPR 2 | 25% | 14 pt | rolagem, 120 px por quadro | 6.8 | 5.0 |
| DPR 2 | 25% | 14 pt | digitar, uma letra por quadro | 6.4 | 4.5 |
| DPR 2 | 25% | 14 pt | digitar, Enter a cada 10 letras | 6.3 | 5.6 |
| DPR 2 | 25% | 14 pt | quadro frio, logo apos trocar o zoom | 7.0 | 6.8 |
| DPR 2 | 100% | 14 pt | quadro quente | 13.2 | 5.0 |
| DPR 2 | 100% | 14 pt | rolagem, 120 px por quadro | 12.3 | 4.6 |
| DPR 2 | 100% | 14 pt | digitar, uma letra por quadro | 12.2 | 4.8 |
| DPR 2 | 100% | 14 pt | digitar, Enter a cada 10 letras | 12.2 | 4.7 |
| DPR 2 | 100% | 14 pt | quadro frio, logo apos trocar o zoom | 11.8 | 12.0 |
| DPR 2 | 150% | 14 pt | quadro quente | 12.4 | 5.5 |
| DPR 2 | 150% | 14 pt | rolagem, 120 px por quadro | 14.9 | 7.5 |
| DPR 2 | 150% | 14 pt | digitar, uma letra por quadro | 14.3 | 11.7 |
| DPR 2 | 150% | 14 pt | digitar, Enter a cada 10 letras | 12.6 | 11.9 |
| DPR 2 | 150% | 14 pt | quadro frio, logo apos trocar o zoom | 11.5 | 12.2 |

Cenários: quadro quente (nada muda), rolagem com um passo de roda por quadro (120 px de tela, fixo),
digitar uma letra por quadro, digitar com Enter a cada 10 letras (muda a altura), e quadro frio logo após
trocar o zoom. A rolagem por passo fixo de 120 px é a da roda do Windows (3 linhas de 40 px, sem escala).

### Achados que mudaram o desenho

1. **Pintura de tile fora do corpo.** Um tile que cai só na margem tinha recorte vazio. `setClipRect` com
   retângulo vazio não recorta nada, e o Qt pintava a página inteira para descartar: 45 ms por tile, 140 ms
   por quadro frio em 100%. Corrigido: `desenhar_folha` sai sem pintar quando o recorte é vazio.
2. **Invalidação lia a altura antes do layout.** O sinal `contentsChange` dispara antes de o
   `QTextDocumentLayout` refazer o layout. Lida ali, a altura era a antiga, e a quebra de linha deixava tiles
   velhos na tela (medido: 15 mil pixels diferentes). Corrigido: a mudança é anotada e a invalidação roda na
   pintura seguinte. Teste: `tests/teste_folhas.py`, com contraprova.
3. **O protótipo do gate tinha esse erro**, então a primeira rodada do gate (feita no protótipo do spike)
   subestimou o custo do Enter. Por isso esta tabela é a refeita sobre o produto, e os números do protótipo
   não entram nela, salvo o item 1 (pintura direta sem cache, que não usa tiles).
4. **Teclado: o QTextEdit oculto não serve (opção a rejeitada).** Compartilhando o `QTextDocument`, o
   QTextEdit oculto troca o `pageSize` de (9072 × 14004) para (624 × -1) ao ser criado: o documento de 20
   páginas vira 1 página. A opção de teclado é a (b): controle próprio, com a API do QTextEdit (nomes e
   sinais), o que mantém as suítes M1 e M2 sem reescrever os comandos. Latência de tecla não foi o problema:
   300 teclas num QTextEdit oculto custam 0,21 ms cada.
5. **Quadro quente sem cache é barato em 11 pt** (3 a 6 ms com teto). O cache foi decidido pelo quadro
   quente e pela margem em DPR 2: a 100%, a digitação cai de 12,2 para 4,8 ms (p95).

### Limites registrados

- Fonte de 16 pt ou mais: em 300% a digitação passa de 16 ms (p95). O teto cobre fonte de até 14 pt. Um
  documento com 16 pt ou mais digita mais devagar em escalas altas: é o limite do Qt, não um defeito do
  cache.
- Medidas em offscreen, com a fonte Segoe UI. O custo de pintura no monitor real (com o DWM e a
  composição) não foi medido; a aparência final é pendência manual.
- A 400% com 11 pt, em DPR 1, o pior p95 é 6,7 ms (digitação): o teto não é necessário para esse caso. Se o orquestrador
  quiser 400% de volta para DPR 1 com 11 pt, a mudança é só `ESCALA_DISPOSITIVO_MAXIMA` em
  `editdoc/modelo/folhas.py`, com o aviso de fonte de 14 pt ou mais.

Dados brutos (JSON e log): pasta de rascunho do scratchpad, fora do repositório.

## Medições do M4 (tabelas e imagens)

Feitas no Qt 6.11.2, com o layout a 1440 dpi do produto, antes de fixar os limites.

| Medida | Resultado |
|---|---|
| Digitar numa célula, 50 x 5 | 5,8 ms por tecla (só o layout) |
| Digitar numa célula, 100 x 5 / 200 x 5 / 400 x 5 | 12,7 / 31,4 / 64,3 ms |
| Digitar numa célula, 100 x 20 (2000 células) | 85 ms |
| Digitar numa célula, 2000 x 5 (10000 células) | 731 ms |
| Digitar num parágrafo depois de tabela de 400 x 5 | 8 ms |

O custo é linear no número de células (cerca de 0,06 ms por célula): o Qt refaz a tabela
inteira a cada mudança. Daí o limite de 5000 células do leitor (cerca de 300 ms por tecla no
pior caso) e a pendência abaixo.

Outros fatos medidos, que decidiram o desenho:

- `insertTable` no meio de um bloco parte o bloco: o texto de antes fica acima e o de depois
  vai para o bloco que o Qt cria abaixo da tabela. Sempre há um bloco antes e um depois de cada
  tabela (inclusive entre duas tabelas seguidas e no começo de uma célula).
- Remover a tabela inteira (seleção do quadro) funde o bloco de cima com o de baixo.
- `insertRows` não copia o formato da célula; `insertColumns` copia o da vizinha e repete a
  largura da coluna da esquerda. Todos os comandos de grade entram no desfazer do documento.
- Depois de mudar a grade, a `QTextTableCell` antiga fica inválida: chamar `row()` nela derruba
  o processo (acesso inválido).
- Linha mais alta que a página: o Qt divide o conteúdo da célula entre as páginas; a linha de
  texto que não cabe desce com um deslocamento dentro do bloco (o retângulo do bloco cruza a
  divisa, a linha não).
- O Qt troca o recurso de imagem (bytes) pela imagem decodificada depois de desenhar: os bytes
  originais não podem ficar só no documento.
- `QTextDocument.loadResource` pode ser sobrescrito no PySide6 e é chamado para o recurso que
  falta (imagem colada de outra janela).
- A tabela colada só aparece em `rootFrame().childFrames()` depois do `endEditBlock`.

## Medições do M8 (polimento)

Feitas em 12/10/2026, Windows 11, Python 3.13, PySide6 6.11.2.

### Interface de texto acessível em Python

A ideia era expor a VistaPaginas ao leitor de tela como texto navegável:
`QAccessible.installFactory` com uma classe que herda de `QAccessibleWidget` e de
`QAccessibleTextInterface`, e `interface_cast(TextInterface)` devolvendo o ponteiro C++ da
parte de texto (`shiboken6.getCppPointer(self)[1]`: o Shiboken cria dois objetos C++
separados para a herança dupla, e devolver `self` daria o ponteiro errado). Conferido pelo
UIA de verdade (PowerShell com `System.Windows.Automation`, plataforma `windows`):

| Chamada do cliente UIA | Resultado |
|---|---|
| Nome, papel, `ValuePattern.Value` | funcionam |
| `TextPattern.DocumentRange.GetText(-1)` | funciona: devolve o texto do Python |
| `GetSupportedPatterns()` | **o processo cai**: "Fatal Python error: _PyThreadState_Attach: non-NULL old thread state" |

A causa: o PySide6 6.11.2 não exporta `QAccessibleTextInterface.selection()` nem
`attributes()` (puros no C++, com parâmetros de saída por ponteiro), nem `textAtOffset`. O
UIA chama esses métodos ao montar os padrões, a chamada cai no método puro sem implementação
em Python, e o interpretador quebra. Um leitor de tela (NVDA, Narrador) lista os padrões o
tempo todo. Decisão: sem `QAccessibleTextInterface`. O `PainelDocumento` é exposto por um
`QAccessibleWidget` em Python (sem a parte de texto) com papel `EditableText`, nome
"Documento: <arquivo>", descrição "Página X de Y" e valor = o parágrafo do cursor. Conferido
pelo mesmo UIA: aparece como `ControlType.Edit` com `ValuePattern`, o valor é o parágrafo,
`GetSupportedPatterns()` não derruba nada, e entre os 67 elementos da janela nenhum botão
ficou sem nome. Caminho para depois: um módulo em C++ (fora do escopo do projeto em Python)
ou uma versão do PySide que exporte os dois métodos.

### Pintura do cabeçalho e do rodapé fora do cache

O cabeçalho e o rodapé não entram no cache de tiles: são pintados em cada quadro, em cada
folha visível. Medido pelos critérios do Gate do M3 (p95 de 80 quadros, `viewport().grab()`
da janela de produção, Segoe UI, offscreen, `QT_SCALE_FACTOR` para o DPR), com a amostra do
M5 (capa, pares e ímpares, imagem e tabela no cabeçalho, "Página X de Y" no rodapé) de
2200 parágrafos, 94 páginas:

| Tela | Zoom | Faixas | Quadro quente | Rolagem | Digitar |
|---|---|---|---|---|---|
| DPR 1 | 25% | sem / com | 0,7 / 2,1 | 1,3 / 3,0 | 2,3 / 4,0 |
| DPR 1 | 100% | sem / com | 0,8 / 1,2 | 1,8 / 2,4 | 3,5 / 3,6 |
| DPR 1 | 300% (500 parágrafos) | sem / com | 1,2 / 1,6 | 2,1 / 2,8 | 5,0 / 4,7 |
| DPR 2 | 25% | sem / com | 6,5 / 6,9 | 6,8 / 7,5 | 6,9 / 7,8 |
| DPR 2 | 150% | sem / com | 8,8 / 8,7 | 9,4 / 10,4 | 10,0 / 11,7 |

(ms, p95.) O cabeçalho e o rodapé custam de 0 a 1,7 ms por quadro; o pior caso (DPR 2,
150%, digitando) fica em 11,7 ms, abaixo dos 16 ms. **Passa sem otimização.** O script de
medição ficou no rascunho, fora do repositório.

### Linha vazia antes da tabela

O limite registrado no M4 ("uma linha vazia aparece na tela antes de uma tabela no começo do
documento ou entre duas tabelas") não se reproduz no Qt 6.11.2: o bloco estrutural antes da
tabela informa altura de linha em `blockBoundingRect`, mas a tabela começa em y = 10 twips
(a borda) e duas tabelas seguidas se encostam (vão de 0 twip), tanto ao abrir quanto ao
inserir pela faixa. Travado em `tests/teste_limites.py`.

### docDefaults

O EditDoc gravava no `docDefaults` de todo documento novo o espaçamento do Word (8 pt depois,
1,08), mas a tela não o aplicava: o mesmo arquivo tinha parágrafos colados no EditDoc e
separados no Word. Desde a 0.1.0 a tela aplica o `docDefaults` fora das tabelas (no Word, o
"Table Grid" zera o espaçamento dentro da célula). A suíte inteira continuou passando com a
mudança (1665 verificações na hora da troca).

### O que ficou medido e não foi feito

- Altura de linha da tabela (`w:trHeight`): o Qt não tem altura mínima de linha. Aplicar
  exigiria preencher a célula (padding inferior) depois de cada layout, de novo a cada tecla:
  não é de baixo risco. Fica no arquivo, não na tela.
- Desfazer de estilo durante a edição do cabeçalho: o catálogo de estilos mora no formato do
  quadro raiz do corpo (o PySide não exporta `QAbstractUndoItem`), então o passo vai para a
  pilha do corpo e o parágrafo do cabeçalho para a pilha do cabeçalho. Juntar as pilhas é
  reescrever o desfazer; fica para depois.

## 0.1.7: objetos flutuantes e quebra de texto

Pergunta: como fazer o texto do corpo contornar um objeto flutuante no layout paginado sobre
`QTextDocument`, sem perder o gate do M3 (p95 de digitação ≤ 16 ms)?

### Caminhos considerados

| Caminho | Resultado |
|---|---|
| Layout próprio (`QAbstractTextDocumentLayout` em Python, linhas com `setLineWidth`) | Descartado: refazer tabelas, quadros, quebras e pintura em Python, com o gate em risco. |
| Recuos temporários por bloco (margem esquerda/direita e espaço antes) | Por bloco, não por linha (o parágrafo inteiro fica estreito), e a troca de formato entra no desfazer e no "alterado" (o mesmo arranjo frágil das listas da 0.1.4). |
| `QTextFrame` de verdade com FloatLeft/FloatRight | O quadro é conteúdo: muda posições, entra no texto extraído, no cursor, na busca e no desfazer. |
| **Float de objeto na linha** (`QTextCursor.insertImage(formato, FloatLeft)`): o caractere de objeto aponta, pelo `ObjectIndex`, para um `QTextFrame` sem conteúdo | **Escolhido.** É o mecanismo do próprio `QTextDocumentLayout` (C++): as linhas seguintes evitam o retângulo, linha a linha, e as que não cabem descem (`findY`). O tamanho é o `intrinsicSize` do nosso manipulador. |

### Medido (spike no Qt 6.11.2, 1440 dpi, documento de 40 parágrafos)

- Float de 3000 × 2000 twips no começo do parágrafo: as 8 primeiras linhas começam em
  x = 3000 com largura 6000; as seguintes voltam a x = 0 e 9000. Float da largura toda:
  a linha da âncora fica com largura 0 e o texto recomeça no pé do objeto.
- Digitar com o float no documento: 0,58 ms (p50) e 0,64 ms (p95) por tecla, sem pintura.
- Armadilha 1: escrever acima do parágrafo-âncora desloca o bloco sem refazer as linhas nem
  o float (o float ficou em y = 6526 com o bloco já em 8534). Por isso a conferência depois
  do layout (`Gerente.atualizar`).
- Armadilha 2: apagar o caractere do float deixa o retângulo antigo valendo, mesmo depois de
  refazer o layout inteiro (`markContentsDirty` do documento todo): o frame não é destruído
  porque o pai ainda estava ligado na hora da remoção. Inserir de novo um caractere com o
  `ObjectIndex` não é possível pelo `QTextCursor` (`insertText` o tira). Só o desfazer
  reinsere com o mesmo índice; dentro do grupo de desfazer o pai não está ligado e o Qt
  destrói o frame. Daí a cura: desfazer e refazer a última ação com a reserva zerada.
- Armadilha 3: dois floats no mesmo trecho não se somam; o segundo é empurrado para baixo
  (até de página) se não cabe na largura livre. Os objetos de um parágrafo viram no máximo
  dois floats, um por lado; se os lados se encontram, um só com a largura toda.
- Armadilha 4: `deleteChar` recusa o caractere com `ObjectIndex` (não é imagem): o painel
  apaga por seleção.

### Gate do M3 com objetos flutuantes

p95 de 80 teclas, cada uma com `viewport().grab()`, janela de produção, Segoe UI,
offscreen, DPR 1, 100%. A coluna 0.1.6 é o mesmo script sobre o código da 0.1.6 (extraído do
git para uma pasta temporária). Os dois documentos reais (um manual de 54 páginas com capa de
caixas de texto e imagens, e um capítulo de 4 páginas com faixa no cabeçalho) ficam fora do
repositório.

| Documento | Onde digita | 0.1.6 (ms) | 0.1.7 (ms) |
|---|---|---|---|
| 600 parágrafos, sem objetos | 1º parágrafo | 8,3 | 8,5 |
| 600 parágrafos, imagem à esquerda e caixa à direita | ao lado da imagem | 9,1 | 10,3 |
| idem | longe dos objetos | 5,9 | 6,1 |
| capítulo de 4 páginas (faixa e caixa no cabeçalho) | capa | 3,6 | 4,0 |
| idem | corpo | 3,5 | 4,1 |
| manual de 54 páginas (capa com 5 objetos) | parágrafo das âncoras | 24,4 | 27,8 |
| idem | sumário (página 2) | 29,4 | 27,2 |

O manual já passava do gate na 0.1.6 (o sumário com preenchimento de tabulação e o corpo
pesado); a 0.1.7 não muda isso (a diferença na capa é repintar a imagem da página inteira
nos tiles invalidados). O gate continua valendo para os documentos que passavam. Antes do
cache do plano de reserva, o Qt pedia o `intrinsicSize` 130 vezes por tecla (a cada
pintura do bloco) e o manual chegava a 46 ms.

## 0.1.8: digitação num documento real pesado e cabeçalho por página

Feito em 14/10/2026, na máquina de desenvolvimento (Windows 11, Python 3.13, PySide6 6.11.2,
offscreen, Segoe UI e Calibri carregadas). Documento real (fora do repositório): manual de 51
páginas no EditDoc (58 no Word), 4260 palavras, capa com imagem de página inteira e caixas de
texto, sumário com 11 PAGEREF dentro de links e pontilhado, 49 desenhos, 19 hiperlinks,
controles de conteúdo. Método do gate: janela de produção (1400 × 950), p95 de 80 teclas, cada
uma com `viewport().grab()`; um processo por ponto; a coluna 0.1.7 é o mesmo script sobre o
código da 0.1.7 extraído do git. Mediana de 3 rodadas. Os scripts (`medir.py`, `etapas.py`,
`medir_gate.py`, `matriz.py`) ficaram no rascunho, fora do repositório.

### Perfil (cProfile e cronômetro por etapa, ms por tecla, média de 80)

| Etapa | âncoras 0.1.7 | âncoras 0.1.8 | sumário 0.1.7 | sumário 0.1.8 | corpo 0.1.7 | corpo 0.1.8 |
|---|---|---|---|---|---|---|
| Tecla (texto, relayout do Qt, sinais) | 1,9 | 1,7 | 2,5 | 1,5 | 1,2 | 0,8 |
| Estado da faixa e da galeria (timer de 0 ms) | 0,3 | 0,3 | 1,4 | 0,7 | 0,3 | 0,3 |
| Conferência dos floats (`markContentsDirty`) | 0,7 | 0,6 | 13,9 | 0,9 | 32,7 | 0,8 |
| Tiles refeitos (corpo) | 23,5 | 5,8 | 20,6 | 3,7 | 7,7 | 1,6 |
| dos quais: objetos flutuantes | 1,3 | 0,0 | 6,2 | 0,7 | 0,4 | 0,0 |
| Cabeçalho e rodapé (com os campos refeitos) | 1,9 | 0,1 | 1,3 | 0,1 | 3,1 | 0,1 |
| Total por tecla | 30,6 | 9,6 | 41,8 | 7,9 | 47,8 | 4,7 |

O que o perfil mostrou, por ordem de peso:

1. **Conferência dos floats que nunca converge.** Uma linha do sumário que não cabia no pé da
   página 1 ao lado da reserva da capa desce para a página 2 com a largura estreita (o Qt mede
   a linha ao lado do float e só depois a muda de página). `markContentsDirty` não muda nada, e a
   conferência refazia o trecho 6 vezes por tecla e, como nunca ficava estável, conferia até o
   fim do documento (139 mil chamadas de `_linhas_certas` em 80 teclas). Correção: quando duas
   rodadas seguidas acham as mesmas faixas, as linhas são aceitas (`Gerente._aceitas`, pela
   assinatura das linhas do bloco) e só voltam a ser conferidas se mudarem.
2. **O bloco inteiro saía do cache.** O parágrafo das âncoras tem a altura da folha (o texto
   dele desce para baixo dos objetos): cada tecla refazia 12 a 16 tiles, e cada tile repintava a
   imagem de página inteira, as caixas de texto e o sumário por trás. Agora sai a faixa das
   linhas (a anterior e da linha da mudança até a base do bloco, a de antes ou a de agora; a
   linha de altura zero, só com objetos, não conta), o tile guarda a faixa cortada no corpo da
   página dele, a conferência que refaz um trecho invalida só dali para baixo, e a tecla seguinte
   a um cache limpo já não acha "altura mudou". Âncoras: 16 → 4 tiles por tecla.
3. **Pontilhado ponto a ponto.** O preenchimento da tabulação do sumário era um `drawText` por
   ponto (190 mil em 80 teclas, 2 ms por tile). Agora é um `drawText` com o espaçamento entre
   letras.
4. **Objetos e faixas pintados em cada tile e em cada quadro.** Na tela, cada objeto flutuante é
   pintado uma vez num QPixmap alinhado ao pixel do dispositivo e copiado 1:1 nos tiles (cache
   de 48 MB, objeto até 16 MB); o cabeçalho e o rodapé de cada folha também (24 MB), e com isso
   os campos do cabeçalho já não são refeitos a cada quadro. O PDF e a impressão pintam de
   verdade. A tela com os caches é a da pintura direta (meio pixel no texto, nenhum pixel com
   mais de 40 níveis de diferença).
5. **Tamanho das marcas.** O Qt pede o `intrinsicSize` das marcas de campo e de link a cada
   pintura do bloco (570 vezes por tecla no sumário). Fica guardado pela fonte.

O que foi medido e não precisou de adiamento: os sinais síncronos da tecla (barra de status,
acessibilidade, rótulo da página) somam 0,2 ms; a faixa e a galeria (timer de 0 ms, roda antes
do quadro seguinte) 0,3 a 0,7 ms; a contagem de palavras, os comentários e o painel de navegação
já esperam 300 a 400 ms. A numeração de listas custa 0,1 ms.

### Tabela do gate (p95 em ms, mediana de 3 rodadas)

| Documento | Onde digita | 0.1.7 | 0.1.8 |
|---|---|---|---|
| manual real | parágrafo das âncoras (capa) | 77,1 | 10,6 |
| idem | sumário (página 1, atrás da capa) | 47,9 | 9,6 |
| idem | corpo, 1/3 do documento (página 13) | 91,0 | 6,8 |
| idem | corpo, 2/3 do documento (página 31) | 90,2 | 7,0 |
| 600 parágrafos, sem objetos | 1º parágrafo | 10,9 | 10,4 |
| 600 parágrafos, imagem à esquerda e caixa à direita | ao lado da imagem | 13,7 | 13,9 |
| idem | longe dos objetos | 8,0 | 8,0 |
| capítulo real de 4 páginas (faixa e caixa no cabeçalho) | capa | 4,8 | 4,6 |
| idem | corpo | 7,9 | 5,1 |
| 600 parágrafos, sem objetos, DPR 1 a 300% | 1º parágrafo | 12,1 | 11,3 |
| 600 parágrafos, sem objetos, DPR 2 a 150% | 1º parágrafo | 18,3 | 18,7 |

Os números da 0.1.7 do manual são maiores que os da tabela da 0.1.7 (27 ms): aquela tabela
saiu de outro roteiro (outra janela e outros pontos de digitação), e não se compara com esta;
as duas colunas acima são o mesmo roteiro nas duas versões. A linha de DPR 2 a 150% passa de 16 ms nas
duas versões nesta medida (janela grande, digitando no 1º de 600 parágrafos): 7,7 ms são o Qt
refazendo a posição dos parágrafos de baixo no `insertText` (cresce com o que vem depois do
cursor); repetida 4 vezes, a mediana é 18,2 na 0.1.7 e 18,3 na 0.1.8 (ruído). No gate do M3 o
mesmo caso media 11,7 ms, com a janela menor.

Teste de regressão: `tests/teste_desempenho.py`, com um manual sintético (capa com imagem de
página inteira atrás do texto, título que empurra o parágrafo, sumário com links, PAGEREF e
pontilhado, cabeçalho da primeira página vazio). As verificações que não dependem do relógio
pegam cada correção (com contraprova): refações por tecla na fixture que não converge (0 contra
1 sem aceitar; eram 6), tiles por tecla na capa (4 contra 16 invalidando o bloco), tela com cache
igual à refeita tecla a tecla, objetos e faixas não repintados num quadro novo, pontilhado num
`drawText`. O p95 (capa, sumário e corpo) passa se ficar no gate ou até 2,5× o de um documento
simples medido na mesma hora (a 0.1.7 media 94 ms no sumário sintético contra 4,6 do simples).

### Altura do cabeçalho por página

O corpo usava a mesma altura de cabeçalho em todas as páginas (a maior das variantes). Na capa
do manual (cabeçalho da primeira página vazio, de 706 twips, contra 1080 do padrão), o corpo
começava em 1477 twips em vez de 1134: o título, a caixa vazia e "Portal Documentação" ficavam
em 3,89 / 7,65 / 28,00 cm. Com a 0.1.8: 3,29 / 7,05 / 27,39 cm (o Word mostra 3,29 / 7,05 /
27,4).

Caminhos estudados para a altura variável:

| Caminho | Resultado |
|---|---|
| `pageSize` por página | Não existe: o `QTextDocumentLayout` pagina com um tamanho só. |
| Margem de cima e de baixo do quadro raiz | Vale em todas as páginas (o Qt usa a mesma `pageTopMargin` na primeira e nas outras): só desloca. |
| Margem negativa no primeiro bloco | Daria mais altura só à primeira página, mas é conteúdo: entraria no arquivo, no desfazer, no Enter, e o primeiro bloco pode ser uma tabela. |
| **Topo por página, altura do corpo única** | **Escolhido.** O documento do Qt não muda (os campos, o hit-test no documento e a paginação ficam iguais); muda onde o corpo de cada folha começa. |

Limite registrado: a altura do corpo é a da página efetiva com o maior cabeçalho e o maior rodapé.
Na página com cabeçalho menor o corpo termina mais acima e cabe o mesmo texto que nas outras
(no manual, a capa do Word tem 2 cm a mais de corpo). O número de páginas é o mesmo da 0.1.7.
Teste: `tests/teste_cabecalho_por_pagina.py` (primeira com cabeçalho vazio, par e ímpar com
alturas diferentes, rodapés diferentes; topo por página no layout, no mapa da tela, no PDF e nos
tiles contra o oráculo em twips; número de páginas igual ao do layout com o cabeçalho alto em
todas; objeto relativo ao parágrafo na página 1; clique e zona; contraprova com a altura única).

## 0.1.10: notas de rodapé e de fim no layout paginado

Feito em 14/10/2026, na máquina de desenvolvimento (Windows 11, Python 3.13, PySide6 6.11.2,
offscreen, Segoe UI e Calibri carregadas). Pergunta: o `QTextDocument` do corpo pagina com um
tamanho só (`pageSize`, o limite da 0.1.8); a área de notas tem de encolher o corpo só na
página onde está a referência. Os scripts do spike e da medição ficaram no rascunho, fora do
repositório.

### Caminhos considerados

| Caminho | Resultado |
|---|---|
| Altura do corpo por página | Não existe no Qt (0.1.8). |
| Margem do quadro raiz | Vale em todas as páginas (0.1.8). |
| Float do Qt na referência (o mecanismo da 0.1.7) | O retângulo do float começa na linha da âncora, não no pé da página: bloquearia o texto entre a referência e a área de notas. A margem do quadro do float entra no retângulo. Descartado. |
| `intrinsicSize` de um objeto do EditDoc | Muda só a altura da linha do objeto; não empurra a linha de outro parágrafo. Descartado. |
| Formato fora do desfazer | `setUndoRedoEnabled(False)` zera as pilhas (medido); `QTextBlock.setVisible` esconde, não empurra. Não há propriedade de layout que não seja conteúdo. |
| Paginação própria sobre um layout contínuo | Mudaria toda a geometria (tiles, clique, objetos flutuantes, campos, tabela entre páginas, impressão). Risco alto para 0.1.7 a 0.1.9. Descartado. |
| **Espaçador no fluxo** | **Escolhido.** `PageBreak_AlwaysBefore` com uma marca (`PROP_QUEBRA_NOTA`) no primeiro bloco que não cabe acima da área de notas. Medido: o Qt respeita também no formato da tabela; o bloco vai ao topo da página seguinte com a mesma margem de antes (a distância entre blocos é a maior das duas margens, colapsada, mesmo depois da quebra), então a volta do bloco é simulada sem tirar a quebra. |

Medido no spike (A4, Calibri 11, 600 parágrafos de 6 linhas, 77 páginas): trocar o formato de
um bloco refaz o layout dali para baixo dentro do `setBlockFormat` (6 ms no 10º bloco; 28 trocas
em sequência, com o layout refeito entre elas, 80 ms); trocar o formato do quadro raiz refaz o
documento inteiro (30 ms). Desfazer: `joinPreviousEditBlock` só junta a um comando de bloco de
edição; depois do `insertText` sem bloco (digitação) o ajuste vira um passo próprio
(`availableUndoSteps` conta comandos). Por isso o ajuste do espaçador é um passo anotado que o
desfazer do painel atravessa junto com o passo do usuário (ver docs/ARQUITETURA.md).

Limite registrado: o espaçador move o bloco inteiro. O Word parte o parágrafo e leva só as
linhas que não cabem; aqui, um parágrafo longo que encontra a área de notas deixa o resto do
pé da página em branco. Tabela que começou na página anterior não é empurrada (a nota que não
cabe continua na página seguinte). Nada se sobrepõe: a distribuição só usa o espaço abaixo da
última linha do corpo da página (teste com contraprova em `tests/teste_notas.py`).

### Desempenho

O plano das notas roda na pintura. Primeira versão: 24 ms por tecla num documento de 300
parágrafos e 100 notas (perfil: varrer as marcas a cada tecla, 3 ms; conferir as 30 páginas
com notas, 9 ms; achar o fim do corpo de cada página na distribuição, 5 ms). Depois: as marcas
seguidas pelo `contentsChange`, a conferência começando na página antes da edição e parando
quando uma página fica igual à do plano anterior, e o fim do corpo pela última unidade da página
(busca binária). Documento sem nota nenhuma (inclusive o do Word com só as separadoras) não
roda o plano.

### Tabela do gate (p95 em ms, 80 teclas com `viewport().grab()`, janela 1400 × 950, um processo por ponto, mediana de 3 rodadas)

| Documento | Onde digita | 0.1.9 | 0.1.10 |
|---|---|---|---|
| manual real | parágrafo das âncoras (capa) | 10,3 | 10,1 |
| idem | sumário (ver a nota abaixo) | 95,7 | 95,4 |
| idem | corpo, 1/3 do documento | 5,3 | 5,1 |
| idem | corpo, 2/3 do documento | 5,2 | 5,1 |
| capítulo real de 4 páginas | capa | 3,7 | 3,5 |
| idem | corpo | 4,6 | 4,4 |
| 600 parágrafos, sem objetos | 1º parágrafo | 3,6 | 3,8 |
| 600 parágrafos, DPR 1 a 300% | 1º parágrafo | 4,6 | 4,6 |
| 600 parágrafos, DPR 2 a 150% | 1º parágrafo | 12,6 | 12,5 |
| 300 parágrafos com 100 notas de rodapé | corpo, 1/3 do documento | — | 8,0 |
| idem | digitando dentro de uma nota | — | 10,5 |

O roteiro desta tabela não é o da 0.1.8 (outro script, outros pontos): as duas colunas são o
mesmo roteiro nas duas versões. O ponto "sumário" deste script (o primeiro parágrafo com
tabulação e número no fim) mede 95 ms nas duas versões: é um ponto diferente do sumário da
tabela da 0.1.8 e não muda com as notas; fica como pendência de medição. O gate com notas
(8,0 e 10,5 ms) passa. Teste de regressão: `teste_notas.py` mede o p95 com 100 notas contra um
documento sem notas na mesma hora (gate de 16 ms ou até 2,5 vezes o sem notas).

## 0.1.11: o ponto "sumário" de 95 ms e o teste de tempo

Feito em 14/10/2026, na máquina de desenvolvimento (Windows 11, Python 3.13, PySide6 6.11.2,
offscreen, Segoe UI e Calibri carregadas), com o roteiro da 0.1.10 (`gate.py` e
`gate_todos.py`, no rascunho, fora do repositório): janela 1400 × 950, p95 de 80 teclas com
`viewport().grab()`, um processo por ponto, mediana de 3 rodadas; a coluna 0.1.10 é o código
da 0.1.10 extraído do git.

### O ponto medido

O cenário "sumário" do script procurava o primeiro bloco com tabulação cujo último caractere é
um dígito. A linha do sumário termina na marca de fim do PAGEREF (U+FFFC), então nenhuma
servia e o cursor ia para a posição 0: o começo do primeiro parágrafo, ANTES das âncoras da
capa. Os 95 ms eram desse ponto. O script ganhou o cenário "linha do sumário" (tira as marcas
antes de olhar o dígito): 14,2 ms nas duas versões.

### Perfil (cProfile, 80 teclas na posição 0, 0.1.10)

| Etapa | ms por tecla |
|---|---|
| Tiles refeitos (16 por tecla, a tela inteira) | 60 |
| Conferência dos flutuantes (13 `markContentsDirty`, 1,5 ms cada) | 24 |
| Tecla (texto e relayout do Qt) | 6 |

A capa reserva a folha inteira (a reserva que passa do pé da página é cortada nele). Com texto
antes das âncoras, o Qt põe o float na página 2; o layout incremental desloca os 13 blocos do
sumário (dentro de um controle de conteúdo) com o float de antes (topo 13674, dentro do
retângulo do float), a conferência acha as linhas erradas e os refaz um a um, e eles voltam a
533, exatamente onde estavam antes da tecla. A tela inteira saía do cache por
`refeito_desde`. Correção: as faixas encostadas viram uma chamada só (`flutuantes._juntar`) e,
se os blocos refeitos têm as mesmas linhas e o mesmo texto do fim da conferência anterior, com a
mesma altura do documento (`Gerente.refeito_igual`), a vista não tira nada do cache. Medido:
1 chamada e 5,5 tiles por tecla na fixture (eram 18 e 16); a tela com cache é igual à refeita do
zero (teste com o atalho usado e contraprovas).

### Tabela do gate (p95 em ms)

| Documento | Onde digita | 0.1.10 | 0.1.11 |
|---|---|---|---|
| manual real | parágrafo das âncoras (capa, fim) | 11,2 | 10,6 |
| idem | ponto "sumário" da 0.1.10 (posição 0, antes das âncoras) | 99,4 | 7,9 |
| idem | linha do sumário (de verdade) | 14,2 | 14,2 |
| idem | corpo, 1/3 do documento | 5,0 | 5,2 |
| idem | corpo, 2/3 do documento | 5,1 | 5,1 |
| capítulo real de 4 páginas | capa | 3,7 | 3,7 |
| idem | corpo | 4,5 | 4,5 |
| 600 parágrafos, sem objetos | 1º parágrafo | 3,6 | 3,7 |
| 600 parágrafos, DPR 1 a 300% | 1º parágrafo | 4,5 | 5,0 |
| 600 parágrafos, DPR 2 a 150% | 1º parágrafo | 11,9 | 12,0 |
| 300 parágrafos com 100 notas de rodapé | corpo, 1/3 do documento | 8,4 | 8,7 |
| idem | digitando dentro de uma nota | 10,3 | 10,5 |

A linha do sumário (14,2 ms) passa no gate com pouca folga: a tecla que muda o número de linhas
do parágrafo refaz da linha para baixo (uns 7 tiles); não mudou nesta versão.

Fixture do teste (`teste_desempenho.manual_capa_cheia`): o manual sintético com o título da
capa de 15000 twips (a reserva vira a folha) e o sumário num `w:sdt` da galeria "Table of
Contents". Na 0.1.10: 168 ms, 18 chamadas e 16 tiles por tecla; na 0.1.11, parada, 15 ms (3,3
vezes o documento simples: o sumário refeito e os tiles da linha, que cruzam o sumário). Por
isso a folga desse ponto no teste é 5 vezes o simples, com o teto absoluto.

### Teste de tempo estável

Na máquina carregada (jogos e navegador abertos), o simples vai de 4,7 a 12 ms e o manual
acompanha; uma medida só reprovou o build (35,5 ms contra 10,8). `testar_p95`: 3 rodadas, cada
uma com o simples e todos os pontos intercalados; vale a mediana de cada lado; limite = o gate
(16 ms) ou a folga relativa (2,5 vezes o simples, mais 2 ms), com teto absoluto de 60 ms; o
ponto que passou do limite mede de novo (simples e ponto), até 2 rodadas. Medido nesta máquina,
carregada: capa 25,8, sumário 24,6, corpo 14,6 e antes da capa 39,9 ms, com o simples a 11,5
(todos passam); parada, todos abaixo de 16. O teste leva cerca de 65 s (o teto da suíte é 180).

## 0.1.12: várias seções, cada uma com o seu papel

Feito em 14 e 15/10/2026, na máquina de desenvolvimento (Windows 11, Python 3.13, PySide6
6.11.2, offscreen, dispositivo de 1440 dpi). Scripts no rascunho da sessão, fora do repositório.

### Caminhos considerados

O `QTextDocument` pagina com um `pageSize` só. Para uma página paisagem no meio de um documento em
retrato, o texto tem de refluir com a largura da seção e quebrar de página na altura dela.

| Caminho | Medido | Situação |
|---|---|---|
| Um `QTextDocument` por seção | — | descartado: cursor, seleção, desfazer e localizar atravessando seções teriam de ser refeitos |
| `QTextFrame` filho por seção, largura própria | a largura fixa vale (13000 twips num documento de 9000, o texto quebra em 13000); `PageBreak_AlwaysBefore/After` do quadro valem; a largura e as margens do quadro são px96 (× 15) | serve para a largura |
| margem de baixo do quadro filho como reserva por página | não vale por página: as linhas do quadro vão até a altura da página do documento em todas as folhas (a margem só conta no fim do quadro) | **não serve** para a altura |
| margem de baixo da tabela | também não vale por página | não serve |
| `PageBreak_AlwaysBefore` no primeiro bloco das células de uma linha de tabela | cada célula quebra por conta própria (a linha fica partida em páginas diferentes; com as três células a linha pulou duas páginas) | não serve |
| acolchoamento de baixo na linha anterior | a linha seguinte desce para a página seguinte (o Qt desce a linha que cruza a divisa) | serve, para a tabela |
| `AlwaysAfter` num bloco e `AlwaysBefore` no seguinte | página vazia no meio (bloco B em 28000, páginas de 14000) | serve, para a página em branco |

Escolhido, com o menor risco: o documento continua um só, na maior largura e na maior altura de
corpo entre as seções. A seção mais estreita ganha um recuo direito escondido em cada bloco e
tabela do primeiro nível (o quadro filho daria a largura, mas a seleção do Qt que atravessa um
quadro pega o quadro inteiro, e apagar a quebra entre seções de papéis diferentes exigiria mover
texto entre quadros); a seção mais baixa usa o espaçador das notas da 0.1.10 (bloco inteiro) e,
para a tabela que não pode descer inteira, o acolchoamento da linha anterior; a quebra entre
seções é a quebra de página do Qt, derivada. Detalhes em docs/ARQUITETURA.md, "Seções".

Achados:

- O topo do primeiro bloco depois de uma quebra de página fica ~160 twips abaixo do topo da folha:
  decidir "seção contínua que começa no meio da folha" pelo topo marcava toda seção nova como
  contínua. Vale o fim do parágrafo da quebra na mesma folha.
- O espaçador oscilava na seção mais baixa (361 ajustes em 80 teclas, p95 de 17,5 ms): a volta
  do bloco empurrado simulava só as linhas até o pé da seção, e o Qt põe linhas até o fim da
  página do documento. Corrigido: simular até o fim da página; 6,0 ms.
- `efetiva_da(n)` era pedida ~80 vezes por tecla e montava a página da seção a cada vez (1,7 ms
  por tecla no perfil): em cache por folha até a geometria ou o mapa mudarem.

### Tabela do gate (p95 em ms, 80 teclas com `viewport().grab()`, janela 1400 × 950, um processo por ponto, mediana de 3 rodadas)

O roteiro da 0.1.11 (`gate.py`, `gate_todos.py`); a coluna 0.1.11 é o código do commit da 0.1.11
extraído do git. As três últimas linhas são novas: a fixture de três seções (retrato, paisagem,
retrato; `fixtures_docx.docx_com_secoes(60, 30, 60)`) e o arquivo real de duas seções.

| Documento | Onde digita | 0.1.11 | 0.1.12 |
|---|---|---|---|
| manual real | parágrafo das âncoras (capa, fim) | 10,6 | 10,8 |
| idem | ponto "sumário" da 0.1.10 (posição 0) | 7,8 | 7,5 |
| idem | linha do sumário | 14,5 | 14,7 |
| idem | corpo, 1/3 do documento | 5,2 | 6,0 |
| idem | corpo, 2/3 do documento | 6,6 | 5,5 |
| capítulo real de 4 páginas | capa | 3,7 | 3,8 |
| idem | corpo | 4,8 | 6,2 |
| 600 parágrafos, sem objetos | 1º parágrafo | 4,0 | 4,1 |
| 600 parágrafos, DPR 1 a 300% | 1º parágrafo | 4,7 | 4,8 |
| 600 parágrafos, DPR 2 a 150% | 1º parágrafo | 12,0 | 12,6 |
| 300 parágrafos com 100 notas de rodapé | corpo, 1/3 do documento | 8,6 | 8,5 |
| idem | digitando dentro de uma nota | 10,7 | 10,9 |
| 3 seções (retrato, paisagem, retrato) | corpo, 1/3 do documento | 4,3 | 6,0 |
| idem | na seção paisagem (a mais baixa) | 4,3 | 6,0 |
| arquivo real de 2 seções (13 páginas) | corpo, 1/3 do documento | 48,6 | 51,6 |

Gate (16 ms) passa em todos os pontos da tabela da 0.1.11 e na fixture de três seções. A 0.1.11
lia a fixture como uma seção só (sem a paisagem), por isso o número dela é mais baixo. O arquivo
real de duas seções já passava do gate na 0.1.11 (48,6 ms), sem relação com as seções: no perfil,
o próprio `insertText` do Qt leva 27 ms por tecla e a pintura dos números de lista 11 ms; fica
como pendência. Teste de regressão: `teste_secoes.testar_desempenho` mede o p95 na seção paisagem
contra um documento de uma seção na mesma hora (16 ms ou até 2,5 vezes) e conta os ajustes do
espaçador (no máximo 20 em 80 teclas).

## 0.1.13: controle de alterações (os modos de exibição)

Feito em 15/10/2026, na máquina de desenvolvimento (Windows 11, Python 3.13, PySide6 6.11.2,
offscreen, dispositivo de 1440 dpi). Scripts no rascunho da sessão, fora do repositório.

### Como mostrar e esconder texto sem mexer no documento

Os modos "Sem marcação" e "Original" escondem texto (o excluído, o inserido) e "Toda a marcação"
pinta sublinhado e tachado na cor do autor. Mudar o formato de caractere entraria no desfazer e no
"alterado"; um segundo documento para cada modo exigiria refazer seções, notas e flutuantes.

| Caminho | Medido | Situação |
|---|---|---|
| `QSyntaxHighlighter` (formatos adicionais do layout) | não muda `isModified`, nem o desfazer, nem `revision()`; só o bloco que muda é refeito; refazer tudo (`rehighlight`) com 9 parágrafos: 0,4 a 0,9 ms | **escolhido** |
| texto escondido com fonte de 0,05 pt | ainda 1 twip por caractere (93 escondidos: +93 twips na linha) | não serve |
| espaçamento absoluto negativo | depende do glifo: -1 dá largura negativa (a linha anda para trás) | não serve |
| espaçamento percentual 0 | o Qt trata como "sem espaçamento" (a largura fica) | não serve |
| fonte de 0,01 pt, cor transparente | largura exatamente zero (93 e 200 caracteres escondidos: 1540 twips com e sem eles) | **escolhido** |
| parágrafo inteiro escondido: `QTextBlock.setVisible(False)` + `markContentsDirty` | o `QTextDocumentLayout` respeita: altura 0, o de baixo sobe | **escolhido** |

Achados:

- O tachado e o sublinhado da marcação vêm do mesmo realce; a segunda linha dos movimentos
  (verde, dupla: o Qt não tem sublinhado nem tachado duplo) é pintada à parte, na função da folha.
- Tabulação e quebra de linha manual (U+2028) dentro do texto escondido continuam ocupando
  espaço (a tabulação vai até a próxima parada; a quebra quebra a linha): limite registrado.
- O parágrafo cuja marca foi excluída mas que ainda tem texto continua separado do de baixo no
  modo final (o Word junta os dois): o Qt não esconde o separador de bloco.

### Gate (p95 em ms, 80 teclas com `viewport().grab()`, mediana de 3 rodadas, `teste_desempenho`)

Fixture nova: 400 parágrafos com 5 revisões cada (2000: inserções e exclusões de dois autores e
formatação alterada), Controlar alterações ligado no arquivo: cada tecla é inserção da autora.

| Documento | Onde digita | 0.1.13 |
|---|---|---|
| documento simples (referência) | corpo | 5,0 |
| manual sintético | capa | 9,8 |
| idem | sumário | 9,4 |
| idem | corpo | 6,8 |
| capa cheia | antes das âncoras | 15,7 |
| **2000 revisões, controle ligado** | corpo (parágrafo 120) | **10,8** |

Trocar o modo de exibição no documento de 2000 revisões, com o realce refeito, o layout e a
pintura da tela: 268 a 277 ms em cada um dos quatro modos (critério: menos de 1 s). A lista do
painel de revisões (2000 itens): 51 ms, em cache pela revisão do documento. Teste de regressão:
`teste_desempenho` (o ponto "2000 revisoes, controle ligado" no p95 e
`testar_modos_com_2000_revisoes`).

## Pendências

- C5 (teclas mortas ABNT2, AltGr e Win+.) pelo roteiro em `spikes/pagina/RESULTADO.md`.
- 0.1.10: abrir no Word, sem reparo, um arquivo com notas gravado pelo EditDoc (nota nova,
  editada, convertida, com marca personalizada). O ponto "sumário" de 95 ms foi medido e
  corrigido na 0.1.11 (era a posição 0, antes das âncoras da capa).
- 0.1.11: abrir no Word, sem reparo, o arquivo que não salvava até a 0.1.10, gravado pela 0.1.11.
- 0.1.12: abrir no Word, sem reparo, um arquivo de três seções (uma paisagem, cabeçalhos
  herdados, página ímpar) gravado pelo EditDoc, e um com quebra de seção inserida e apagada.
- 0.1.12: digitação no arquivo real de duas seções a 1/3 (48,6 ms já na 0.1.11): o `insertText`
  do Qt (27 ms) e os números das listas (11 ms).
- 0.1.13: abrir no Word, sem reparo, um arquivo com alterações controladas gravado pelo EditDoc
  (digitar, apagar, formatar e Enter com o controle ligado, dois autores; aceitar e rejeitar
  parte delas) e conferir que o Word mostra as mesmas revisões, autores e datas.
- Abrir uma amostra `.docx` gerada pelo spike no Word, sem reparo. As amostras estão
  em `%TEMP%\claude\...\scratchpad\spike-docx`, fora do repositório.
- Cache de página: medido no Gate do M3 (acima). Adotado com teto de zoom.
- Fonte embutida para os testes de renderização visual.
- M4: abrir no Word, sem reparo, a amostra `tests/saida/amostra_m4_tabelas_imagens.docx` (gerada
  pela suíte, fora do repositório) e um arquivo salvo pelo EditDoc com tabela e imagem.
- M4: digitação em tabela grande (acima de ~250 células passa de 16 ms por tecla). Caminhos:
  layout incremental próprio da tabela, ou adiar o relayout para depois da tecla.
- M8: usar o EditDoc com NVDA e com o Narrador (nomes, "Página X de Y", dicas de tecla) e
  conferir o tema escuro na tela real (no offscreen o esquema de cores não muda).
