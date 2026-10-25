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

## 0.1.14: o arquivo "plano" (tabelas), rejeitar o resto das revisões e colunas

Feito em 15/10/2026, na máquina de desenvolvimento (Windows 11, Python 3.13, PySide6 6.11.2,
offscreen, dispositivo de 1440 dpi), com a máquina carregada (um jogo e o navegador abertos: o
documento simples, que parado mede ~5 ms, mediu 9 a 11 ms). Scripts no rascunho da sessão, fora do
repositório; o código do Qt conferido no `qtextdocumentlayout.cpp` do ramo 6.11 do qtbase.

### Por que o `insertText` custa ~27 ms no plano

O arquivo real de duas seções (13 páginas, 152 parágrafos de corpo com 89 itens de lista, 16
tabelas com 362 células e cabeçalho repetido). `insertText` puro (sem pintura), mediana de 30
teclas, conforme o ponto da tecla:

| Bloco onde digita | ms por tecla |
|---|---|
| 0 (começo) | 32,7 |
| 150 (1/4) | 26,0 |
| 194 (1/3) | ~27 |
| 300 (1/2) | 18,7 |
| 420 | 9,8 |
| 560 (fim) | 1,9 |

O custo é proporcional ao que vem DEPOIS do ponto, e só às tabelas: com as tabelas tiradas do
documento, 0,9 ms em qualquer ponto. Num documento sintético: 16 tabelas depois do ponto custam
15,8 ms com página (`pageSize` com altura) e 0,06 ms sem página. O código do Qt explica:

- `QTextDocumentLayoutPrivate::layoutFlow`, para cada quadro (tabela) no fluxo depois do trecho
  editado: `if (document->pageSize().height() > 0.0f) cd->sizeDirty = true;` e refaz o quadro
  (a tabela pode ter mudado de página). Os blocos comuns depois do trecho só são deslocados; as
  tabelas são refeitas, todas, até o fim do documento. O laço só para antes do fim no layout
  preguiçoso (`currentLazyLayoutPosition`), que só existe no layout do documento inteiro.
- `layoutTable` refaz cada célula duas vezes: uma na largura infinita (para as larguras mínima e
  máxima da coluna, mesmo com largura fixa) e uma na largura de verdade; `layoutCell` liga
  `fullLayout = true` ("we get called with different widths all the time"), e cada bloco da
  célula é refeito do zero (`QTextLayout::beginLayout` libera os glifos: o texto é moldado de
  novo). O `goto recalc_minmax_widths` (terceira passada) NÃO acontece no plano (a soma das
  larguras cabe; medido estreitando a última coluna: nada muda).

Caminhos medidos para baixar isso, de fora do Qt:

| Caminho | Medido no plano (começo) | Situação |
|---|---|---|
| tirar as bordas das células (o colapso de bordas do Qt consulta as vizinhas) | 31,3 → 30,1 ms | não resolve |
| tirar formatos de tabela, célula, bloco e caractere | 31,9 → 25,6 ms | não resolve (e perde a aparência) |
| texto de cada célula trocado por "x" | 31,7 → 22,9 ms | o custo é por célula, não só pelo texto |
| `QFont.PreferNoShaping` em tudo | 25,8 → 23,7 ms | não resolve |
| `setLayoutEnabled(False)` em volta da tecla | — | religar refaz o documento inteiro (`documentChanged(0, 0, length)`) |
| layout próprio (`QAbstractTextDocumentLayout` em Python) | — | descartado: refazer a paginação do Qt, tabelas e floats em Python |

Conclusão: com o `QTextDocumentLayout` do Qt, digitar antes de N tabelas custa O(células das N
tabelas), em C++, e não há chave para desligar. O gate de 16 ms no plano não é alcançável nesta
arquitetura enquanto o ponto tiver mais de ~150 células de tabela abaixo dele. Fica como pendência
(caminhos: um documento por trecho entre tabelas, ou adiar o relayout das tabelas de baixo com um
layout próprio — os dois são reescritas grandes).

### O que era do EditDoc, e foi cortado

Perfil da pintura (cProfile, 80 teclas a 1/3, numa célula): a tela inteira (20 tiles) saía do
cache a cada tecla, porque a mudança dentro de tabela tirava a tabela inteira (e a do plano
atravessa páginas); cada tile pedia o retângulo de todos os 89 itens de lista
(`desenhar_rotulos`: 148 mil `blockBoundingRect` em 80 teclas) e interpretava os extras de cada
bloco e fragmento (`propriedades.desenhar`).

- Célula: a tabela com o mesmo retângulo de antes tira só as linhas do texto (bloco do mesmo
  tamanho) ou só a linha da tabela, e só nos tiles da coluna da célula. Plano real a 1/3: 20 → 3,9
  tiles por tecla (na célula a 1/2, 2,1).
- Listas: a faixa vertical de cada item fica em cache até o layout mudar (sinal `update`); o
  Numerador já não recalculava os números ao digitar dentro de um item (0 mudanças de estrutura
  em 80 teclas, conferido): o custo de 11 ms da 0.1.12 era a pintura, não a contagem.
- Bordas e tabulações: o que cada bloco tem para pintar fica em cache até o documento mudar.
- Pintura de um tile do plano (tela inteira refeita, mediana de 10): 4,5 → 2,1 ms.

### Tabela do gate (p95 em ms, 80 teclas com `viewport().grab()`, um processo por ponto, mediana de 3 rodadas intercaladas 0.1.13 x 0.1.14)

Painel de 1000 × 800 da `teste_desempenho` (fixtures em código) e janela de 1400 × 950 (arquivo
real, roteiro `gate_plano.py`); a coluna 0.1.13 é o código do commit da 0.1.13 extraído do git,
medido na mesma hora (a máquina ficou parada nesta medida: o simples a 5,4 ms).

| Documento | Onde digita | 0.1.13 | 0.1.14 |
|---|---|---|---|
| documento simples (referência) | corpo | 5,5 | 5,4 |
| manual sintético | capa | 10,7 | 10,5 |
| idem | sumário | 10,5 | 10,0 |
| idem | corpo | 7,2 | 6,8 |
| capa cheia | antes das âncoras | 16,1 | 15,9 |
| 2000 revisões, controle ligado | corpo | 12,4 | 10,2 |
| **plano sintético** (novo, `documento_plano`) | 1/3 do documento | 64,8 | 50,5 |
| idem | célula a 1/2 | 43,9 | 38,0 |
| idem | item de lista a 1/4 | 62,6 | 51,0 |
| **plano real** (2 seções, 16 tabelas) | 1/3 (numa célula) | 87,1 | 49,9 |
| idem | célula a 1/2 | 57,6 | 35,3 |
| idem | item de lista a 1/4 | 45,6 | 40,0 |

Nenhum ponto da tabela do gate piorou. O plano não chega a 16 ms: no plano real a 1/3 a tecla
sozinha (o `insertText` do Qt) mede 26 a 28 ms e a pintura 10 a 13 ms (na 0.1.13 a pintura refazia
20 tiles por tecla). O gate de 16 ms continua não alcançável nesse documento, pela causa acima.

### Rejeitar (0.1.14)

O estado de antes está inteiro no elemento de mudança (`w:tblPr`, `w:trPr`, `w:tcPr`, `w:sectPr`
de antes). Escolhido: reler esse elemento com o próprio leitor (numa tabela, linha, célula ou seção
de mentira) e aplicar o resultado no Qt, em vez de interpretar cada propriedade de novo. Limites
encontrados: as bordas de tabela que vinham do estilo não são relidas (o estilo de tabela é XML do
arquivo, fora do Qt): só os lados declarados no `w:tblBorders` de antes voltam; o `w:cellMerge`
pediria partir a célula do Qt; a célula inserida sozinha deixaria a linha com uma célula a menos
(o `QTextTable` não tem linha torta).

Modo "Sem marcação" (o que a 0.1.13 deixou de limite), medido de novo: o formato adicional do
`QSyntaxHighlighter` não muda o tamanho de uma imagem (`ImageWidth`/`ImageHeight` de 0,01 no
realce: a imagem continua 200 x 100), não encolhe a tabulação nem desfaz a quebra de linha, e o Qt
não esconde o separador de bloco. Os três continuam limites (exigiriam um manipulador de imagem
próprio e mudar o texto, o que entraria no desfazer).

### Colunas de texto: spike (adiado)

Ideia testada: a página do Qt vira UMA coluna (`pageSize` com a largura da coluna e a altura do
corpo) e a pintura dobra N páginas do Qt numa folha, lado a lado. Spike num `QTextDocument` solto
(2 colunas iguais, A4, 60 parágrafos): as linhas partem entre colunas como entre páginas, a quebra
de coluna é a quebra de página do bloco, o hit-test dobrado acha a posição certa (coluna 2 da
folha 1 → parágrafo 14) e o layout leva 2 a 4 ms. PNG da folha em
`%TEMP%\editdoc_0114_png\spike_colunas_folha*.png` (fora do repositório).

Por que não entrou nesta versão (o que o mecanismo atual teria de mudar):

- o documento é um só, com uma altura de página: numa seção de colunas, cada página do Qt passa a
  ser uma coluna, e a folha passa a valer N páginas. Tudo que hoje supõe "folha n = faixa
  [n·H, (n+1)·H)" muda: o `Mapa` da tela, os tiles (um tile mostraria N faixas), o cursor, a
  seleção, o arraste de objeto, o hit-test, a régua, os objetos flutuantes relativos à página, as
  notas de rodapé por folha, PAGE/NUMPAGES/SECTIONPAGES, a impressão e o PDF;
- a seção contínua com colunas no meio da folha precisaria de páginas do Qt mais baixas que as
  outras (o espaçador das notas daria a altura, mas o balanceamento da última folha é iterativo);
- a quebra de coluna no MEIO do parágrafo (`w:br w:type="column"`, hoje um caractere de objeto) não
  quebra página no Qt: teria de partir o parágrafo, como a quebra de página;
- largura: a seção de colunas teria o recuo direito escondido da 0.1.12 (documento na largura da
  seção mais larga), o que serve; colunas desiguais pediriam larguras diferentes por página.

Risco alto para uma versão que também mexe no layout por desempenho: fica para uma versão própria,
começando pelo `Mapa` folha → páginas (sem colunas, nada muda).

## 0.1.15: digitar antes das tabelas (o plano), spike das saídas que a 0.1.14 não testou

Feito em 15/10/2026, na máquina de desenvolvimento (Windows 11, Python 3.13, PySide6 6.11.2,
offscreen, dispositivo de 1440 dpi), com a máquina carregada (dois jogos e o navegador abertos:
o documento simples, que parado mede ~5 ms, mediu 4 a 12 ms). Código do Qt conferido no
`qtextdocumentlayout.cpp`, `qtextdocument.cpp` e `qtextdocument_p.h` do ramo 6.11 do qtbase.
Scripts no rascunho da sessão (`spike_a.py`, `spike_lazy.py`, `spike_custo.py`, `spike_faixa.py`,
`etapas_pintura.py`, `gate_plano.py`, `gate_todos.py`), fora do repositório.

Meta pedida: p95 ≤ 16 ms digitando no plano real a 1/3 (célula), na célula a 1/2 e no item de
lista (0.1.14: ~50, ~35 e ~40 ms), sem piorar nada.

### Onde vai o tempo (0.1.14, plano real, médias de 80 teclas)

| Ponto | tecla (`insertText` do Qt) | pintura | da pintura: tiles (`desenhar_folha`) | linhas de quebra | resto |
|---|---|---|---|---|---|
| célula a 1/3 | 25,3 | 15,9 | 11,9 (3,9 tiles inteiros) | 1,4 | 2,6 |
| célula a 1/2 | 20,2 | 10,3 | 6,2 (2,1) | 1,5 | 2,6 |
| item de lista | 24,8 | 8,9 | 6,6 (4,0) | 0,3 | 2,0 |

Mesmo com a pintura em zero, a tecla do Qt sozinha passa de 16 ms nos três pontos.

### (a) A cascata depende da altura do bloco mudar? Dá para adiá-la?

| Medida | Resultado |
|---|---|
| tecla que NÃO muda a altura do bloco (117 de 120) × a que muda (3) | 26,7 × 27,4 ms: a cascata é a mesma. No código: `layoutFlow` liga `cd->sizeDirty = true` em todo quadro no fluxo depois do trecho sempre que `pageSize().height() > 0`, sem olhar se algo se moveu. "Absorver" a variação de altura não muda nada. |
| `markContentsDirty` do bloco, sem mudar nada | 25,5 ms (a mesma cascata) |
| layout inteiro (religar o layout + `documentSize`) | 63,2 ms |
| layout preguiçoso do Qt (`currentLazyLayoutPosition`), timers do layout presos por filtro de eventos | só entra pelo layout do documento inteiro (`documentChanged(0, 0, tamanho)`); num clone sem os sinais do EditDoc, a 1ª tecla custou 8,7 ms e a fronteira andou ~1000 caracteres por tecla (`docPos > currentLazyLayoutPosition + lazyLayoutStepSize`, e o passo volta a 1000 a cada mudança): 25 ms de novo na 10ª tecla. Na janela, os sinais pedem o tamanho do documento e o layout termina na 1ª tecla (70 ms). `pageCount` no clone preguiçoso: 10 páginas em vez de 13. **Não serve.** |
| layout próprio que delega ao `QTextDocumentLayout` | impossível pelo PySide: a classe é privada, `setDocumentLayout` apaga o layout anterior (`delete lout`) e não há como criar um segundo para o mesmo documento. |
| quadro flutuante (`FloatLeft`) para a tabela | o Qt só marca a tabela flutuante como suja se ela atravessa página (`positionFloat`), mas ela passa a não se partir entre páginas e o texto anda em volta: muda a paginação. **Não serve.** |

### De onde vem o custo de cada tabela refeita (clone solto do plano, digitando no começo)

| Variação (só no clone) | ms por tecla |
|---|---|
| como está | 32,2 |
| blocos das células escondidos (`setVisible(False)`) | 17,3: metade é a estrutura da tabela (células, bordas, `cellAt`, `row()`/`column()`), não o texto |
| sem colapso de bordas | 26,0 |
| formato de célula vazio (sem bordas nem acolchoamento próprios) | 27,1 |
| os dois juntos | 21,9 |
| célula sem o JSON do EditDoc | 31,7 (nada) |
| sem cabeçalho repetido | 30,6 |
| largura de coluna variável | 32,5 (nada) |

O que cai (um terço, no máximo) muda a geometria da célula (sem o colapso, a borda inteira entra
no acolchoamento; o acolchoamento por lado só existe no formato da célula) e a pintura das bordas
passaria a ser do EditDoc, inclusive no PDF: risco alto para uma versão estável, e a tecla ainda
passaria de 16 ms.

### (b) e (c): tabelas congeladas, layout próprio de tabela, documento por trecho

- **Tabela congelada** (pintada de um cache e com a geometria guardada): o custo está no layout
  do Qt, que roda sobre o documento inteiro; para o Qt pular a tabela ela teria de sair do
  documento ou do fluxo, e isso é conteúdo (desfazer, "alterado", gravação). Esconder os blocos
  (o que não é conteúdo) mudaria a altura de tudo abaixo: número de páginas, campos, notas.
- **Layout próprio só para tabelas** (a tabela como objeto do layout paginado, células como
  subdocumentos): um objeto na linha não se parte entre páginas; para manter as mesmas quebras
  seria preciso refazer em Python a paginação de tabela do Qt (linha que desce, célula que
  continua na página seguinte, cabeçalho repetido) e depois cursor, seleção atravessando tabela,
  localizar, copiar, desfazer, revisões de tabela (0.1.13/0.1.14), comandos de tabela e a ida e
  volta. Reescrita grande.
- **Documento por trecho entre tabelas**: o mesmo problema, maior (cursor, seleção, desfazer e
  localizar atravessando documentos).

Conclusão: com o `QTextDocumentLayout` do Qt 6.11, nenhuma saída corta a cascata das tabelas com
risco aceitável para a 0.1.15. **A meta de 16 ms nesses três pontos não é alcançável nesta
arquitetura**; a tecla do Qt (20 a 28 ms carregado) fica como está.

### O que entrou (a pintura, do EditDoc)

1. **Só a parte da linha nos tiles.** A linha digitada cruzava 2 a 4 tiles, e cada um saía
   inteiro do cache. Agora o tile fica e a parte da linha é anotada; a pintura refaz só ela, num
   pixmap do tamanho do tile com a mesma transformação, e copia os pixels da parte. Caminhos
   medidos e descartados no caminho: juntar as partes de tiles vizinhos numa pintura só, com a
   origem da folha (7,3 ms de pintura a 1/3, contra 10,2 por tile), errava a letra da borda do
   tile em um pixel a 137% (o Qt arredonda a posição de outro jeito para coordenada negativa);
   folgas de 300 twips em volta da parte custavam 10,2 ms, 150 twips ~9, nenhuma folga 7,3 (mas
   a entrelinha exata menor que a letra deixava tinta velha: contraprova no teste).
2. **Dois furos que o tile inteiro escondia**, achados pelo teste pixel a pixel: a linha que
   desce de página dentro do bloco fica abaixo do `blockBoundingRect` (a linha do sumário do
   manual sintético, 210 twips abaixo); e o número de lista recalculado fora da pintura (a janela
   pede o rótulo do cursor) não chegava à pintura, então o Backspace que tira o item vazio da
   lista deixava os números de baixo velhos fora da fileira de tiles da linha.
3. **A lista das quebras de página do usuário** (as linhas tracejadas, desenhadas a cada quadro)
   fica guardada até mudar o número de blocos ou chegar uma troca de formato: eram 1,4 a 2,8 ms
   por tecla olhando centenas de blocos de célula.

Pintura depois (médias de 80 teclas, máquina carregada): célula a 1/3 15,9 → 7,2 ms; a 1/2
10,3 → 6,6; item 8,9 → 7,1. Na fixture `documento_plano`: 7,8 → 4,7, 6,6 → 4,2, 9,4 → 6,9.

### Tabela do gate (p95 em ms, 80 teclas com `viewport().grab()`, um processo por ponto, mediana de 3 rodadas intercaladas 0.1.14 x 0.1.15)

Painel de 1000 × 800 da `teste_desempenho` (fixtures em código) e janela de 1400 × 950 (arquivo
real, `gate_plano.py`); a coluna 0.1.14 é o código do commit da 0.1.14 extraído do git, medido na
mesma hora (simples a 4,6 ms: a carga caiu durante esta medida).

| Documento | Onde digita | 0.1.14 | 0.1.15 |
|---|---|---|---|
| documento simples (referência) | corpo | 4,6 | 4,7 |
| manual sintético | capa | 9,4 | 6,7 |
| idem | sumário | 8,9 | 7,3 |
| idem | corpo | 5,9 | 5,4 |
| capa cheia | antes das âncoras | 15,0 | 12,4 |
| 2000 revisões, controle ligado | corpo | 9,3 | 5,7 |
| plano sintético | 1/3 do documento | 45,0 | 41,2 |
| idem | célula a 1/2 | 34,3 | 30,2 |
| idem | item de lista a 1/4 | 47,0 | 34,3 |
| **plano real** (2 seções, 16 tabelas) | 1/3 (numa célula) | 47,0 | **35,7** |
| idem | célula a 1/2 | 33,6 | **29,3** |
| idem | item de lista a 1/4 | 37,0 | **34,9** |

Nenhum ponto piorou; todos os da tabela de antes melhoraram (a linha digitada refaz menos
pixels em qualquer documento). **O plano continua acima de 16 ms**: o que sobra é a tecla do Qt
(20 a 28 ms nessa máquina), que nenhuma saída de baixo risco corta (acima).

Regressão nos 11 `.docx` reais da pasta Downloads (cópias temporárias, abrir → salvar como →
reabrir → salvar, 0.1.14 e 0.1.15 com o mesmo roteiro): todos gravam nas duas vezes, sem falha na
conferência nem no validador, sem diferença c14n entre a 1ª e a 2ª gravação, e o mesmo número de
páginas da 0.1.14 em cada arquivo (um deles abre com 4 páginas e o salvo reabre com 6 nas duas
versões: diferença que já existia, registrada como pendência).

## 0.1.16: o arquivo que abria com 4 páginas e reabria com 6

O arquivo da pendência da 0.1.15 é um `.docx` gerado por um conversor de PDF: só
`[Content_Types].xml`, `_rels`, `core.xml`, `document.xml` e as imagens. Sem `styles.xml`, sem
`settings.xml`, sem `app.xml`. O corpo é uma imagem da altura da página (95 % do corpo), ~70
parágrafos curtos com `w:spacing w:after="120"` e Arial de 6 a 9 pt, uma quebra de página e outra
imagem.

Diff entre a 1ª abertura (original) e a 2ª (gravado), bloco a bloco no `QTextDocument`: os 79
blocos diferiam; no gravado, todos tinham entrelinha proporcional de 108 % e o da imagem ganhava
10,67 px depois. O docDefaults do modelo era `{}` na 1ª e `{8 pt depois, 108 %, Calibri 11}` na
2ª. O diff c14n entre a 1ª e a 2ª gravação era vazio, porque o erro já estava na 1ª: o leitor
partia do `catalogo_padrao()` (docDefaults vazio, que a tela interpreta como sem espaço,
entrelinha simples e fonte da preferência) e o `xml_base` do escritor gravava, para qualquer
catálogo sem `styles.xml` de origem, o docDefaults do documento novo. Com 1,08, a linha da imagem
(95 % do corpo) passa do corpo e empurra o resto.

O que o Word usa sem `styles.xml`: espaçamento e entrelinha do esquema (ausente = 0 e simples) e,
para a fonte, Times New Roman de 10 pt (`w:sz` ausente = 20 meios-pontos). Não há Word nesta
máquina para conferir a fonte; o espaçamento é o do esquema. O arquivo não tem `app.xml`, então
não há contagem do Word gravada: pela regra acima, o Word mostraria o que o EditDoc mostra agora
na 1ª abertura (4 páginas). Correção: o leitor usa esse docDefaults (`catalogo_sem_estilos`) e o
escritor grava o docDefaults do catálogo ao pé da letra. Resultado: 4/4/4 (abrir, reabrir o
salvo, reabrir o salvo duas vezes).

A conferência não pegava porque só comparava estrutura, texto, estilos, objetos, campos, marcas,
listas e revisões. Desde a 0.1.16 compara também a formatação efetiva que muda o layout (ver
CHANGELOG). Duas decisões: fonte e tamanho que a memória não define não contam (a tela usa a
preferência, que o modelo não vê); comentários e notas continuam sem a formatação (o layout do
corpo é o que importa aqui, e o conteúdo deles continua conferido). Custo medido:

| Medida | 0.1.15 | 0.1.16 |
|---|---|---|
| `conferir` de 3000 parágrafos e 9000 runs (com a releitura), mediana de 7 | 573 ms | 609 ms |
| manual real (2 MB, 52 páginas), na gravação | 232 a 284 ms | 232 a 283 ms |
| arquivo de 13 páginas com sumário, na gravação | 470 a 483 ms | 487 a 497 ms |

Contraprova no arquivo real: o arquivo do escritor antigo é recusado ("formatacao do paragrafo
diferente no paragrafo 1 (espaco_depois_tw 0 -> 160, espacamento_linha_pct 100 -> 108)").

### Páginas: Word × EditDoc ao abrir × EditDoc depois de salvar e reabrir

Offscreen com as fontes do Windows carregadas (Calibri, Arial, Times, Verdana, Cambria...; Aptos
não existe na máquina). Sem elas, o offscreen usa o fallback e as contagens mudam (o arquivo do
defeito dava 4/6 sem as fontes e 4/5 com elas na 0.1.15). Word = `<Pages>` do `docProps/app.xml`
(o que o Word gravou na última vez; "-" = sem `app.xml` ou sem `Pages`).

| Arquivo | Word | 0.1.15 abrir/salvo | 0.1.16 abrir/salvo/salvo 2x |
|---|---|---|---|
| 1: o do defeito (conversor de PDF) | - | 4 / 5 | 4 / 4 / 4 |
| 2 a 4: três variantes de um documento | - | 5 / 5 | 5 / 5 / 5 |
| 5 e 6: o manual, duas cópias (`app.xml` de uma gravação do Word) | 48 | 52 / 52 | 52 / 52 / 52 |
| 7 | 3 | 3 / 3 | 3 / 3 / 3 |
| 8 | 4 | 3 / 3 | 3 / 3 / 3 |
| 9 (com sumário) | 14 | 13 / 13 | 13 / 13 / 13 |
| 10 | - | 27 / 27 | 27 / 27 / 27 |
| 11 | 2 | 2 / 2 | 2 / 2 / 2 |

Sem as fontes (o fallback do offscreen), a 0.1.16 dá 4/4/4, 6, 54/54, 3, 4, 14, 31 e 2 páginas,
sempre iguais nas três aberturas (o 8 e o 9 batem com o Word por acaso: o fallback é mais largo).
Todos gravam nas três vezes, sem falha na conferência nem no validador, sem diferença c14n entre
a 1ª e a 2ª gravação. A diferença que sobra em relação ao Word não vem da gravação (o salvo reabre
igual). Investigado pelas `w:lastRenderedPageBreak` (onde o Word começou cada página na última
gravação) contra a página do mesmo texto no EditDoc:

- **espaço entre parágrafos**: o `QTextDocumentLayout` do Qt 6.11 usa o MAIOR entre o
  `bottomMargin` do bloco de cima e o `topMargin` do de baixo (`layoutBlock`:
  `qMax(blockFormat.topMargin(), previousBlockFormat->bottomMargin())`); o Word soma o espaço
  depois e o espaço antes. O manual usa um estilo de corpo com 12 pt antes e 12 pt depois em 165
  parágrafos: no Word são 24 pt entre eles, no EditDoc 12. Corrigir pede margem derivada dos
  vizinhos, mantida a cada edição (como o recuo escondido da seção): não é de baixo risco;
- **controle de linhas viúvas e órfãs, manter com o próximo, manter linhas juntas** e
  **`contextualSpacing`** não entram no layout (ficam nos extras do `pPr` e voltam ao arquivo). No
  arquivo 8 o Word passa para a página seguinte um parágrafo de três linhas que no EditDoc
  ainda cabe (12 584 twips de 14 004); o EditDoc fica mais denso (3 páginas × 4);
- **entrelinha "múltipla"**: conferida no código do Qt (`getLineHeightParams`: cada linha avança
  `altura × percentual`, a 1ª também) e medida (150 % com Calibri 12: 439,5 twips por linha mais o
  espaço depois), igual ao Word. O `blockBoundingRect` mostra só a altura natural das linhas:
  medir o passo de um bloco ao seguinte, não a altura do retângulo;
- **altura natural da linha no offscreen**: o Arial de 12 pt dá 268 twips (ascendente +
  descendente, sem o `lineGap` da fonte); o Word usa 276 (13,8 pt, com o `lineGap`). Contagem de
  páginas comparável à do Word só no Windows real, não no offscreen.

Fica como pendência (abaixo). Nenhuma dessas diferenças muda entre abrir e reabrir o salvo.

## 0.1.17: paginação mais perto da do Word, medida contra o próprio Word

O oráculo: o Word grava `w:lastRenderedPageBreak` onde começou cada página na última vez que
paginou o arquivo. Cada um vira, numa cópia em memória, um marcador (`w:bookmarkStart/End`, sem
largura) partindo o run; no `QTextDocument`, a posição do marcador diz o parágrafo e a linha em que
o Word quebrou. Para cada quebra: o texto está na mesma página no EditDoc? A página do EditDoc
começa no mesmo parágrafo? Na mesma linha? (Um U+200B no lugar do marcador mudava a altura da
linha: um arquivo ia de 27 a 28 páginas.) Só 5 dos 12 arquivos têm as marcas; o manual foi salvo
pelo EditDoc depois do Word (`Application` = EditDoc no `app.xml`), sem elas: o `Pages` = 48 dele é
o de uma gravação antiga do Word e não pôde ser conferido quebra a quebra.

Medido no Windows real (plataforma `windows` do Qt, janela com `WA_DontShowOnScreen`, nada na
tela) e no offscreen com as fontes do Windows usadas carregadas. Carregar TODAS as fontes no
offscreen mudou o fallback (Arial Unicode): 10 páginas onde o Windows dá 5.

### Causas achadas (por arquivo, na primeira quebra que diverge)

- **Altura da linha.** O Qt 6.11 usa winAscent + winDescent também na plataforma `windows`
  (Arial 12: 268 twips nos dois), sem o lineGap; o Word soma o "espaço externo" (o lineGap do
  hhea que passa da altura do win): 276. Arial e Times New Roman: +3 % a +4 % por linha; Calibri,
  Verdana, Cambria e Segoe UI: nada (medido em `QTextLayout` contra as tabelas da fonte).
- **Parágrafo vazio junto da tabela.** O `QTextDocumentLayout` esconde o bloco vazio logo depois
  de uma tabela (`isEmptyBlockAfterTable`) e o logo antes (`isEmptyBlockBeforeTable`, se não tiver
  fundo). No Word é um parágrafo de verdade. Arquivo 7 (3 páginas, 10 tabelas, cada uma seguida
  de um parágrafo vazio de 1,5 linha): o EditDoc punha a página 2 do Word inteira na 1.
- **Marca de parágrafo.** O parágrafo vazio tem a altura da fonte da marca (`w:pPr/w:rPr`); o
  EditDoc usava a do docDefaults (Arial 12 em vez de Calibri 12 nas caixas vazias do arquivo 7).
- **Espaços junto da tabela.** O Qt ignora o espaço depois do parágrafo antes de uma tabela, o
  espaço antes do parágrafo depois dela e, na célula, o antes do primeiro e o depois do último.
- **Espaço entre parágrafos.** O Qt usa o maior; o Word soma (ECMA-376 17.3.1.33; o colapso é só
  da entrelinha automática do HTML). O `contextualSpacing` tira o espaço entre o mesmo estilo.
  Nos arquivos com oráculo quase não há pares com espaço depois E antes, então o oráculo não o
  separa; ficou pela especificação.
- **Linhas viúvas e órfãs.** Arquivo 8: as três quebras do Word caem no começo de um parágrafo
  que o EditDoc partia com uma linha órfã no pé da página. Ligado por padrão no Word (o arquivo
  não tem `w:widowControl` nenhum).
- **Imagem com entrelinha múltipla.** O proporcional do Qt multiplica a linha da imagem (1,5 x
  a imagem). No arquivo 10, a página 11 do Word tem duas imagens (3480 e 3390 twips), 13 linhas de
  texto (414 cada) e 7 espaços de 160: 1,5 x imagem dá 19 334 twips, mais que a página (14 334);
  a imagem sem o multiplicador dá 13 372 (ou 13 642 com meia linha de texto por imagem), e o
  parágrafo seguinte (988) não caberia: o Word multiplica a linha do texto, não a da imagem.
- **Espaço antes no alto da página.** O `newPage` do Qt faz `y = max(y, topo da página)`: o
  espaço antes que passa da divisa fica em parte na página seguinte. O Word mantém o espaço antes
  inteiro (não há `suppressTopSpacing` nem `suppressSpBfAfterPgBrk` nos arquivos).
- **Não corrigidas:** a página em branco do arquivo 9 (uma quebra de página num parágrafo
  sozinho seguida de uma quebra de seção "próxima página": o Word começa a seção na página
  seguinte à capa, o EditDoc deixa uma página a mais); a viúva de um parágrafo com três linhas ou
  mais em cima (o Word desce UMA linha, o layout do Qt não); a altura das linhas da tabela de
  cabeçalho do arquivo 10 (a primeira quebra do Word vem 1 a 2 linhas antes); o Aptos (arquivos 9
  e 11) não existe na máquina, e o fallback não serve de comparação.

### O que entrou (compensação no formato, `interface/paginacao.py`)

| Parte | Como |
|---|---|
| linha da fonte | entrelinha proporcional x razão Word/Qt da família (`QRawFont`: head, hhea, OS/2); a linha com objeto alto usa a distância somada (`LineDistanceHeight`) |
| espaço somado | o de cima com zero depois, o de baixo com a soma antes; `contextualSpacing` |
| tabela | fundo transparente no vazio de antes; a altura do vazio de depois no espaço do seguinte; os espaços em volta nas margens do quadro |
| marca de parágrafo | o paragrafo vazio com a fonte do `w:pPr/w:rPr` (`para_qt`) |
| regras | viúvas e órfãs (o parágrafo inteiro), manter linhas juntas, manter com o próximo (a cadeia), quebra antes do estilo, espaço antes no alto da página |

Cada parte foi medida contra o oráculo sozinha, numa versão intermediária (ainda sem a regra do
espaço no alto da página e sem a linha da imagem; Windows, quebras certas no mesmo parágrafo /
mesma linha; o arquivo 7 tem 2 quebras, o 8 tem 3, o 10 tem 23; "todas" é a versão final):

| Parte ligada | arq. 7 | arq. 8 | arq. 10 |
|---|---|---|---|
| nenhuma (só a marca de parágrafo) | 0 / 0 | 1 / 0 | 0 / 0 |
| linha | 0 / 0 | 1 / 0 | 1 / 0 |
| espaço | 0 / 0 | 1 / 0 | 0 / 0 |
| tabela | 0 / 0 | 1 / 0 | 2 / 0 |
| regras | 0 / 0 | 1 / 1 | 0 / 0 |
| todas | 2 / 2 | 3 / 3 | 1 / 1 |

### Páginas: Word × EditDoc (Windows e offscreen), 0.1.16 → 0.1.17

Word = `<Pages>` do `docProps/app.xml` ou, sem ele, as marcas + 1.

| Arquivo | Word | Windows 0.1.16 → 0.1.17 | offscreen 0.1.16 → 0.1.17 |
|---|---|---|---|
| 1 (o do defeito da 0.1.16) e a cópia salva pelo EditDoc | - | 4 → 4 | 4 → 4 |
| 2 a 4 | - | 5 → 5 | 5 → 5 |
| 5 e 6: o manual | 48 (gravação antiga) | 52 → 49 | 52 → 49 |
| 7 | 3 | 3 → 3 | 3 → 3 |
| 8 | 4 | 3 → 4 | 3 → 4 |
| 9 (Aptos, que falta) | 14 | 13 → 15 | 13 → 14 |
| 10 | 24 (23 marcas) | 27 → 26 | 27 → 26 |
| 11 (Aptos) | 2 | 2 → 2 | 2 → 2 |

### Acerto das quebras do Word (mesmo parágrafo / mesma linha / texto na mesma página)

| Arquivo | quebras | Windows 0.1.16 | Windows 0.1.17 | offscreen 0.1.16 | offscreen 0.1.17 |
|---|---|---|---|---|---|
| 7 | 2 | 0 / 0 / 0 | 2 / 2 / 2 | 0 / 0 / 0 | 2 / 2 / 2 |
| 8 | 3 | 0 / 0 / 0 | 3 / 3 / 3 | 0 / 0 / 0 | 3 / 3 / 3 |
| 10 | 23 | 0 / 0 / 0 | 1 / 1 / 5 | 0 / 0 / 0 | 1 / 1 / 5 |
| 9 (Aptos) | 13 | 1 / 1 / 6 | 0 / 0 / 9 | 0 / 0 / 5 | 2 / 2 / 11 |
| 11 (Aptos) | 1 | 1 / 0 / 1 | 1 / 0 / 1 | 1 / 1 / 1 | 1 / 0 / 1 |
| total | 42 | 2 / 1 / 7 | 7 / 6 / 20 | 1 / 1 / 6 | 9 / 8 / 22 |

Nos arquivos com as fontes que existem na máquina (7, 8 e 10), o parágrafo da quebra passou de
0 a 6 em 28 e o texto na página certa de 0 a 10. No 10 a primeira quebra já vem 1 a 2 linhas
antes da do Word (a tabela do cabeçalho) e o erro se acumula até o fim (a última quebra fica 46
parágrafos antes; na 0.1.16, 52).

### Desempenho

Custo por tecla (média de 40, `ConjuntoDePaginacao`): compensação 0,3 a 0,8 ms (duas chamadas
por pintura), regras 0,4 a 1,7 ms (2 páginas conferidas); uma tecla em 40 muda uma quebra das
regras e refaz o layout de baixo (até 54 ms no manual sintético e 122 ms no plano, uma vez).
Gate (`teste_desempenho`, p95, mediana de 3 rodadas, mesma máquina, 0.1.16 → 0.1.17): capa
15,5 → 18,3; sumário 18,0 → 20,3; corpo 13,1 → 14,1; antes da capa 26,1 → 27,6; 2000 revisões
13,8 → 14,4; o documento simples de referência 8,9 → 11,6; plano (pintura) 7,3 → 13,3, 6,6 →
10,8, 9,6 → 9,8 (a tecla do Qt, 35 a 38 ms, continua a exceção conhecida). Todos dentro do
critério do teste (ate' 2,5 x o simples). A vista passou a refazer tudo abaixo quando o bloco de
baixo ou a base da tabela se movem (a quebra das regras segura a altura do documento).

### Regressão

Os 12 `.docx` (cópias temporárias, plataforma `windows`): abrir → salvar como → reabrir →
salvar → reabrir: todos gravam, sem aviso, conferência e validador passando, sem diferença c14n
entre a 1ª e a 2ª gravação, mesmas páginas nas três aberturas, documento sem "alterado" ao abrir.

## 0.1.18: tirar os trancos da paginação (medição e histerese da quebra do motivo 3)

A 0.1.18 foi planejada para fazer a recomputação da paginação parar cedo. Antes de mudar código,
mediu-se onde vai o tempo de uma tecla com quebra que muda. O que entrou está em "Histerese" no
fim desta seção.

### O que já converge

`ConjuntoDePaginacao._regras_desde` já para quando a assinatura de cada página (o começo dela:
bloco, linha, topo) volta a bater com o plano anterior, a partir da página editada e da última
mudança (`_inicios`). Por tecla, o paginador confere de 1 a 14 páginas (300 teclas no plano real,
média de 1 a 2). A cadeia de "manter com o próximo" já é avaliada inteira em `_manter_com_proximo`
e `_precisa`, não só o próximo bloco. O que falta convergir não é o paginador.

### Onde vai o tempo (offscreen, `teste_desempenho` como base, janela 1000 × 800)

Medição por tecla (`medir_tecla`, scratchpad fora do repositório): `keyClick` (insertText e o
layout que o Qt refaz) e a pintura, com o paginador dentro da pintura. Uma rodada por ponto, 80 a
400 teclas; o p95 é do total (tecla + pintura).

| Documento (ponto) | teclas | p95 total | pico | teclas com quebra mudando |
|---|---|---|---|---|
| manual sintético (corpo) | 400 | 7,3 ms | 15,7 ms | 4 |
| manual sintético (início, antes da capa) | 120 | 11,0 ms | 34,4 ms | 1 |
| manual sintético (sumário) | 120 | 9,6 ms | 26,3 ms | 2 |
| manual com capa cheia (início) | 200 | 12,7 ms | 29,5 ms | 0 |
| manual real (1/3) | 300 | 7,1 ms | 15,0 ms | 1 |
| plano sintético (1/3) | 400 | 24,8 ms | 39,0 ms | 2 |
| plano sintético (célula) | 200 | 16,8 ms | 35,4 ms | 2 |
| plano sintético (início) | 200 | 24,2 ms | 32,9 ms | 0 |
| plano real (documento de referência, 1/3) | 300 | 16,6 ms | **73,3 ms** | 3 |
| plano de ação real (1/3) | 300 | 4,5 ms | 7,0 ms | 0 |

No plano real, a tecla de pico (9 mudanças de quebra) gastou 39 ms no paginador e 12 ms no
`insertText`; a de 6 mudanças gastou 33 ms. A média do paginador, sem os picos, é 1 a 3 ms por tecla
(`cProfile`: 0,88 s em 309 chamadas de `atualizar_secoes`).

Separação entre o paginador e o Qt (perfil, plano real, 300 teclas): `insertText` 4,1 s (o layout
das tabelas que o Qt refaz, como já medido em 0.1.14); `setBlockFormat` 0,5 s; `endEditBlock` 0,14 s
em 25 chamadas (cerca de 6 ms cada: é o relayout que o Qt faz quando um formato de bloco muda);
o paginador (`regras` + `compensar`) 0,8 s no total. Cada mudança de quebra custa um relayout do Qt
de ~5 ms; por isso o pico é proporcional ao número de mudanças, não ao número de blocos conferidos.

### Causa dos picos: ida e volta de quebras

O rastro das mudanças (`rastro_ajustes`, scratchpad) mostra o que o paginador faz em um pico:

- tecla 57: liga quebra no bloco 216, liga em 422, desliga em 426, liga em 446, liga em 500,
  desliga em 517, desliga em 549, liga em 549, desliga em 549: 9 mudanças, 4 delas no mesmo
  bloco 549;
- tecla 249: liga 215, liga 260, liga 379, liga em 549, desliga em 549, liga em 549: 6 mudanças.

O bloco 549 vai e volta. O motivo 3 ("o parágrafo começa a página, tem espaço antes e não cabe")
liga a quebra; na conferência seguinte, `_avaliar` pergunta por `_precisa` (o bloco ainda precisa
descer, simulado sem a quebra) e desliga, porque sem a quebra o bloco cabe no pé da página de cima;
a mudança seguinte nas páginas de cima faz de novo o bloco começar a página. Isso é um ponto fixo
que não fecha. O `MAX_POR_BLOCO = 3` limita a volta, mas cada volta custa um relayout.

### O que isso diz sobre a meta

- A convergência por assinatura de página já existe, e não é ela que custa.
- O custo que sobra é o relayout do Qt a cada mudança de quebra (~5 ms), e o número de mudanças.
  Os picos de 54 ms e 122 ms da 0.1.17 não foram reproduzidos nesta rodada; o de 73 ms no plano
  real é o maior medido, e as mudanças do mesmo bloco de ida e volta são a parte evitável.
- Para cair de 73 ms para 16 ms, a saída provável é decidir as quebras em Python (simulação sem
  o Qt) e aplicar as mudanças de uma vez num bloco de edição, com a conferência só no fim. Isso é
  reescrita do modelo de quebras, não um ajuste de parada, e mexe nos números de páginas que a
  0.1.17 mediu contra o Word: não foi feito nesta rodada.
### Histerese da quebra do motivo 3 (entrou)

A causa do ping-pong: o motivo 3 liga a quebra quando o bloco já começa a página sem ela
(`primeiro`), e `_precisa` a desliga quando o bloco caberia na página de cima. Com o layout da
página de cima mudando a cada tecla, o bloco 549 do plano real ia e voltava (liga, desliga, liga,
desliga, na tecla 57). Agora:

- liga (motivo 3) só se `_precisa(bloco, anterior)` diz que o bloco precisa descer (o mesmo
  critério de antes, sem folga);
- desliga só se `_precisa(..., margem=HISTERESE_TW)` diz que sobram 720 twips no pé da página de
  cima (`HISTERESE_TW`, `interface/paginacao.py`; zero volta ao comportamento da 0.1.17).

Entre as duas faixas a quebra fica como está. Medido (scratchpad, mesmos scripts):

| Medida | 0.1.17 (`HISTERESE_TW=0`) | 0.1.18 (720) |
|---|---|---|
| tecla 57 do plano real: mudanças de quebra | 9 (bloco 549: 4) | 6 (549: 0) |
| tecla 249 do plano real: mudanças de quebra | 6 | 3 |
| páginas do plano real depois de 300 teclas (1/3) | 16 | 15 |
| oráculo dos .docx de Downloads (páginas; par, lin de cada) | igual | igual |

O oráculo não muda em nenhum dos 15 `.docx` de Downloads (páginas e acerto por parágrafo e linha);
a contagem de páginas ao abrir, no ambiente desta rodada, dá 46 no manual (a 0.1.17 registrou 49
no Windows; não foi reproduzido aqui: sem diferença entre 0 e 720). O gate (intercalado, zero e
720, mesma rodada): manual sintético corpo 7,8 e 7,6 ms; capa cheia no início 14,0 e 14,8 ms (p95
total); sem piora fora do ruído.

Não atingido. Numa rodada tranquila, a tecla 57 do plano real gastou 73 ms no total (39 ms no
paginador); nesta rodada, com a máquina carregada, a mesma tecla gastou ~170 ms (80 a 88 ms no
paginador) com 9 mudanças e ~140 ms (80 ms) com 6. A redução de 9 para 6 mudanças deu só ~8 % no
paginador com a máquina carregada, então o custo por mudança não é só o número delas. Não há
medida tranquila do depois: as duas rodadas de 0 e 720 foram feitas carregadas. A meta de 16 ms
continua exigindo decidir as quebras sem o Qt (ver acima).

Contraprova: `testar_histerese` (tests/teste_paginacao_word.py) usa uma fixture em código com a
faixa estreita (o parágrafo cabe com pouca folga); com `HISTERESE_TW = 0` a suíte acusa. Não
consegui uma fixture sintética que oscile de verdade (as que tentei não oscilam); a oscilação
medida é a do plano real, que não entra no repositório.

### Qualidade de imagem reduzida (entrou)

O corpo (`desenhar_folha`, `interface/vista_paginas.py`) não pedia `SmoothPixmapTransform`: uma
imagem reduzida amostrava o pixel mais próximo e saía serrilhada. Agora o hint vai antes do
`draw` do corpo, dentro do save/restore. Gate (`medir_tecla`, scratchpad fora do repositório;
antes = cópia da árvore sem o hint, depois = com o hint; 3 rodadas intercaladas, 400 teclas cada;
p95 do total, em ms):

| Ponto | antes (r1, r2, r3) | depois (r1, r2, r3) | mediana antes / depois |
|---|---|---|---|
| manual sintético (corpo) | 8,6; 8,0; 7,5 | 7,9; 8,9; 7,5 | 8,0 / 7,9 |
| manual com capa cheia (início) | 16,5; 16,8; 16,3 | 16,5; 17,3; 16,2 | 16,5 / 16,5 |
| documento simples (corpo) | 6,7; 7,4; 6,5 | 6,8; 6,5; 7,7 | 6,7 / 6,8 |

Nenhum ponto passa de 1,5 ms de diferença entre as medianas: sem regressão fora do ruído.

Qualidade: `testar_reducao_suave` (tests/teste_imagens.py) pinta listras verticais de 1 px
(vermelho e branco) reduzidas a 1/4 pelo painel real. O desvio das colunas em relação à metade
de tinta (0 é o ideal) fica em 0,005 com o hint. Contraprova: a mesma imagem pelo QPainter sem o
hint dá 1,000 (0,000 com o hint), e a árvore antes da mudança reprova o teste na tela (1,000).

## 0.1.19: colunas de texto na tela, no PDF e na impressão (spike, adiado)

Spike feito em 22/10/2026, só leitura de código (nenhuma linha do EditDoc alterada, nenhuma medida
nova de tempo). Base: o spike da 0.1.14 (um `QTextDocument` com `pageSize` de uma coluna, as N
páginas do Qt dobradas numa folha, layout de 2 a 4 ms) e o código da 0.1.18.

Meta pedida: `w:cols` igual (num, space, equalWidth), quebra de coluna (`w:br type="column"`),
`w:sep`, e seção contínua com colunas no meio da página.

### Mecanismo avaliado

- Dobrar páginas do Qt em folhas (o spike da 0.1.14). O Qt continua com uma altura de página, e
  cada folha passa a ser N páginas do Qt lado a lado. O custo está em todo lugar que supõe
  "folha n = Qt page n" (ver contagem abaixo).
- Uma coluna por `QTextFrame` ou por `QTextDocument` por seção: descartado (cursor, seleção,
  desfazer e localizar atravessando colunas teriam de ser refeitos; já era o caso da 0.1.12).
- Colunas como pintura pura sobre o texto de uma coluna: não existe, o fluxo do texto é do Qt.

### Custo de integração (contagem no código da 0.1.18, `editdoc/` sem testes)

| Área | Onde o pressuposto mora | Efeito |
|---|---|---|
| Mapa e tiles | `LayoutPaginado.hb` (11 arquivos), `pagina_de_y` (4), `numero_paginas` (6), `VistaPaginas._tile`, `desenhar_folha` | Um tile passa a mostrar N faixas; o `Mapa` vira folha → páginas do Qt |
| Cursor e caret | `retangulo_cursor` (5 arquivos), `pagina_do_cursor` (3), `ajustar_para_pagina` (3), `_retangulo_do_caret` | O x do caret vem da coluna, não só do y |
| Hit-test | `painel_documento.posicao_em` e os `hitTest` de `posicao_em`, arraste e alças (4 pontos só nele), `objetos.py:185`, `notas.py:1094`, `paginacao.py:450` (que testa `pagina * hb`), `vista_paginas.py:94,1536` | Cada ponto de clique tem de virar (folha, coluna, y) e voltar |
| Seleção e arraste de objeto | `_arraste`, `_geometria_do_arraste`, `flutuante_das_faixas_em` | Dependem de hit-test e de folha |
| Objetos flutuantes | `flutuantes.Contexto.topos/folhas` e `_folha_para_flutuantes` | O relativo à página passa a ser relativo à coluna |
| Notas de rodapé | área de notas por folha (`interface/notas.py`), `paginacao.py` (compensação de notas) | A nota fica no pé da folha, não da coluna |
| Campos | `campos_da_folha`, PAGE, NUMPAGES, SECTIONPAGES (10 arquivos do pacote citam os campos) | O número de página é da folha; NUMPAGES conta folhas |
| Paginação (0.1.17/0.1.18) | `interface/paginacao.py` (694 linhas): assinatura por página, histerese do motivo 3, espaçador das notas, `_avaliar` | Toda a regra de quebra é por página do Qt; com colunas, a "página" da regra vira coluna e a altura da folha muda |
| Seção contínua no meio da folha | `ConjuntoDeSecoes.mapear`, `secao_da_folha`, `topo_da_pagina` | A seção contínua começa numa coluna, e a altura da coluna não é a da folha: precisa de páginas do Qt de alturas diferentes, e o balanceamento da última folha é iterativo |
| Quebra de coluna no meio do parágrafo | `leitor.py:533` (vira `MarcaQuebra("coluna")`), `modelo/documento.py:274` | Hoje é caractere de objeto; o Qt não quebra coluna. Teria de partir o parágrafo, como a quebra de página |
| Impressão e PDF | `impressao.py` (509 linhas), `preparar_para_impressao`, `leitor_pdf` dos testes | A folha impressa tem N colunas; o PDF e a impressão repetem o mapa |
| Desfazer | comandos de edição e `formato do quadro raiz` | Pouco afetado: colunas são formato de seção (já passam pelo `ConjuntoDeSecoes`) |
| Gravação | `formato_docx/secoes.py` (w:cols em c14n) | Já preserva w:cols; a escrita de `w:br type="column"` e de `w:sep` seria nova |

Conclusão do spike: o layout do texto em colunas do Qt funciona (a medida da 0.1.14 continua
valendo), mas o que muda é o mapa folha → página do Qt, e ele está em cursor, hit-test, tiles,
notas, campos, paginação com compensação, impressão e PDF. Não há como fazer isso como "um
ajuste na pintura".

### Veredito

Não entra na 0.1.19. Risco alto para o arquivo real (a paginação da 0.1.17/0.1.18 foi medida
página a página contra o Word; mexer no mapa a põe em risco) e sem como medir a interação com
o cursor e a impressão sem uma sessão de tela no Windows. O aviso de colunas fica como está. Caminho
para uma versão própria, na ordem: (1) separar no `ConjuntoDeSecoes` a folha da página do Qt, sem
colunas (nada muda, testes atuais passam); (2) colunas iguais só em seção de quebra de página
(folha = N páginas do Qt, sem seção contínua); (3) quebra de coluna no parágrafo e `w:sep`;
(4) seção contínua com colunas no meio da folha, por último.

## 0.1.20: folha × página do Qt (passo 1 das colunas, sem mudança de comportamento)

Primeiro passo do caminho de "0.1.19": separar a folha (página impressa ou visível, com cabeçalho,
rodapé e margens da seção) da página do Qt (unidade de paginação do QTextDocument). Hoje as duas
coincidem: a folha n é a página n do Qt, faixa [n*hb, (n+1)*hb). A identidade mora numa só camada,
`modelo/folhas.MapaFolhas` (sem Qt), exposta como `LayoutPaginado.mapa`: `topo(n)`, `fim(n)`,
`pagina_de_y(y, folga)`, `folha_de_y(y, folhas)`, `folha_da_pagina(p)`.

### O que migrou (trechos trocados, em editdoc/)

| Arquivo | Trechos | Uso |
|---|---|---|
| `modelo/folhas.py` | 6 | `Mapa` (tela/documento) passa pela camada; a própria camada |
| `interface/notas.py` | 52 | planos das notas: `_topo`/`_fim`/`_pe`, `_medir`, espaçadores, distribuição, área de notas por folha (`painter.translate`) |
| `interface/paginacao.py` | 11 | regras do Word: páginas de linha e de tabela, hit-test da pagina, assinatura, pe' da pagina |
| `interface/vista_paginas.py` | 9 | desenho da folha (`translate`, recorte), tiles (`_tile`, `_repintar_partes`), faixa de quebra, rolagem |
| `interface/secoes.py` | 3 | `mapear`: primeira folha de cada seção (a conversão página do Qt -> folha fica explícita) |
| `interface/layout_paginado.py` | 3 | criação do mapa e `pagina_de_y` (cursor, clique, caret) |
| `ponte_qt/flutuantes.py` | 3 | `Contexto.pe_da` e `folha_de` (objetos flutuantes) |
| `ponte_qt/campos.py` | 2 | `_indice` (campos PAGE e NUMPAGES: a folha de um y) |
| `interface/impressao.py` | 3 | comentários na margem da folha (impressão e PDF) |
| `interface/painel_documento.py` | 2 | clique em flutuante na folha; posição da imagem selecionada |
| `edicao/objetos.py` | 1 | ancoragem de objeto (`_bloco_para_ancora`) |

Somam 95 trechos de texto (cada um pode ser uma ou mais ocorrências). O que sobrou de `hb` é altura
da página (chave de cache, limite do corpo, `hb - 1`), não deslocamento de folha: `grep` no
`editdoc/` mostra só essas leituras.

### Ficou acoplado, e por quê

- `pagina_de_y` e `pagina_do_cursor` continuam com o nome de antes (testes e a janela usam; trocar
  o nome seria reescrever verificação). O que mudou é quem faz a conta: a camada.
- Folhas a mais (só notas de fim e de rodapé continuadas, depois do texto) não têm página do Qt. O
  plano de notas as trata como `n >= paginas_do_texto()` com a conta da identidade (`topo(n)`).
  Quando as colunas vierem, este é o ponto que precisa de resposta própria da camada.
- Paginação (0.1.17/0.1.18) continua contando páginas do Qt: é a regra certa para o passo 1, e a
  camada só converte. Com colunas, a regra passa a ser por folha; isso é o passo 2.
- `ConjuntoDeSecoes` continua com `info.hb` (altura do corpo de cada seção): é geometria da seção, não
  conversão de folha.

### Medido

- Suíte: base 3384 verificações (`git` HEAD 87959e4); depois, 3391 (7 da camada, com contraprova) e
  0 falhas. `teste_notas` chamava `_medir(cat, hb)`, `_linhas_da_pagina(med, k, hb)` e
  `_distribuir(..., hb, ...)` (assinatura privada): as chamadas passaram a usar a camada, sem retirar
  nenhuma verificação.
- Regressão: 14 `.docx` reais de uma pasta pessoal (somente leitura, nomes fora do repositório): abrir, salvar,
  reabrir, salvar, na 0.1.19 e na 0.1.20 (`QT_QPA_PLATFORM=windows`, fontes do Windows). Páginas
  abertas e reabertas iguais em todos; c14n de todas as partes (datas de criação e alteração do
  `docProps/core.xml` fora, porque são a hora do salvamento) iguais em todos; o salvo 1 e o salvo 2
  iguais nos 14. Saída JSON idêntica nas duas árvores.
- Gate de desempenho (`tests/teste_desempenho.py`, p95 de 80 teclas com a pintura, mediana por ponto,
  3 rodadas intercaladas 0.1.19 e 0.1.20, em ms):

| Ponto | 0.1.19 (rodadas 1, 2, 3) | 0.1.20 (rodadas 1, 2, 3) | Diferença máxima |
|---|---|---|---|
| capa | 8,3 · 7,7 · 8,0 | 8,0 · 7,9 · 8,0 | 0,3 |
| sumário | 9,5 · 9,0 · 9,3 | 9,1 · 8,8 · 8,8 | 0,5 (a 0.1.20 mais rápida) |
| corpo | 7,0 · 6,6 · 6,5 | 6,7 · 7,2 · 6,3 | 0,6 (sinal trocado: ruído) |
| antes das âncoras da capa | 12,8 · 12,9 · 12,6 | 12,7 · 12,7 · 12,4 | 0,2 |
| 2000 revisões | 5,8 · 6,0 · 5,9 | 5,7 · 5,9 · 5,7 | 0,2 |

Nenhum ponto passa de 1,5 ms, e o sinal da diferença troca de rodada para rodada: ruído. Os 6
gates passaram nas duas versões.

### Veredito do passo 1

Feito, sem mudança de comportamento: mesmas páginas, mesmos pixels (suíte de tela e de PDF), mesmo
arquivo salvo (c14n da regressão). O próximo passo é o 2 (colunas iguais só em quebra de página),
que é o primeiro com folha ≠ página do Qt de verdade; ele continua adiado até a sessão de tela no
Windows.

## 0.1.22: página em branco antes da quebra de seção (quebra de página no próprio parágrafo)

O defeito, na 0.1.17 já anotado como "não corrigido" (arquivo 9, "a página em branco"): um parágrafo que
só tem `w:br type="page"` seguido do parágrafo com o `w:sectPr` (quebra de seção "próxima página").
Confirmado no código e no documento de referência (SIM, Aptos ausente nesta máquina): o SIM tem o
parágrafo só-quebra (bloco 9) e o parágrafo com o `sectPr` (bloco 10), e no `w:body` o `lastRenderedPageBreak`
do Word cai no "Sumário" (o bloco 11): o Word põe a quebra e a seção na página da capa.

Causa: `formato_docx/leitor._paragrafos` lê o parágrafo só-quebra como `quebra_antes` dele mesmo, e
`ponte_qt/para_qt` grava isso como `PageBreak_AlwaysBefore`: o Qt começa uma página nesse parágrafo (vazio).
O `sectPr` vira `PageBreak_AlwaysAfter` (quebra derivada, `interface/secoes.conferir_formatos`), e a
seção seguinte começa numa página depois: a página do parágrafo só-quebra fica sozinha.

Medido na 0.1.20 (Windows, `QT_QPA_PLATFORM=windows`): SIM com 15 páginas; a página 2 contém só o
parágrafo só-quebra e o `sectPr`, e o Sumário começa na 3.

### O que mudou

- Parágrafo só-quebra (sem runs, sem `sectPr` no mesmo `w:p`): `PageBreak_AlwaysAfter` (`para_qt`).
  Ele fica na página de cima, como no Word. Com texto (digitado depois), o `de_qt` separa o texto
  e um parágrafo só-quebra depois dele, para o arquivo voltar igual.
- Quebra do usuário no fim (`ponte_qt/secoes.quebra_so_depois`): não é a quebra derivada da seção.
  `interface/secoes.conferir_formatos` não liga a quebra derivada da seção quando o parágrafo de
  cima é só-quebra (`_quebra_do_usuario_logo_antes`): a quebra do usuário já termina a página.
- Regras do Word (`interface/paginacao._avaliar`): o bloco que vem depois de uma quebra do usuário no
  fim do parágrafo não recebe quebra das regras (viúva, manter com o próximo, topo). Sem isso a
  quebra das regras entrava logo depois e a página em branco voltava (o Contrato ia de 6 a 7 páginas).
- Linha "Quebra de página" (`interface/vista_paginas._blocos_com_quebra`): para a quebra no fim, a
  linha vai no fim do parágrafo que a leva (a lista guarda o bloco seguinte, que a linha desenha acima).
- Enter, copiar e colar: o Enter tira a quebra do bloco novo (como antes). O HTML do Qt leva
  `page-break-after` e o colar devolve a quebra (medido no teste).

Nada disso muda o arquivo gravado: o `w:br type="page"` continua no mesmo parágrafo; `c14n` igual à 0.1.20
nos 14 `.docx` de Downloads (regressão abrir-salvar-reabrir-salvar).

### Páginas e acerto das quebras (oráculo `lastRenderedPageBreak`, Windows, 14 arquivos de Downloads)

Acerto = (mesmo parágrafo / mesma linha) da página que o Word começa, por marca do Word.

| Arquivo | quebras do Word | páginas antes | páginas depois | acerto antes (par/lin) | acerto depois (par/lin) |
|---|---|---|---|---|---|
| doc_01 | 0 | 4 | 4 | 0/0 | 0/0 |
| doc_02 | 0 | 4 | 4 | 0/0 | 0/0 |
| doc_03 | 0 | 5 | 5 | 0/0 | 0/0 |
| doc_04 | 0 | 5 | 5 | 0/0 | 0/0 |
| doc_05 | 0 | 5 | 5 | 0/0 | 0/0 |
| doc_06 | 0 | 6 | 6 | 0/0 | 0/0 |
| doc_07 | 0 | 49 | 49 | 0/0 | 0/0 |
| doc_08 | 0 | 49 | 49 | 0/0 | 0/0 |
| doc_09 | 0 | 49 | 49 | 0/0 | 0/0 |
| doc_10 | 2 | 3 | 3 | 2/2 | 2/2 |
| doc_11 | 3 | 4 | 4 | 3/3 | 3/3 |
| doc_12 | 23 | 26 | 26 | 1/1 | 1/1 |
| doc_13 | 1 | 2 | 2 | 1/0 | 1/0 |
| doc_14 (SIM) | 13 | 15 | 13 | 0/0 | 1/1 |

O SIM: Word = 14 páginas. Com a correção, o Qt põe a capa numa página, o sumário na 2, e o "1. Histórico" na 3
(como o Word, pelas marcas 1 e 2). A partir daí as páginas do EditDoc condensam mais texto que as do Word
(o Word começa a página 4 no bloco 109, "Anexo IV"; o EditDoc a começa no 121): a fonte Aptos não existe nesta máquina e o
fallback tem a linha mais baixa (já anotado na 0.1.17). A contagem de 13 não é a de 14 do Word por isso,
e não é só a quebra. Uma variante intermediária, sem a regra que impede a quebra das regras logo depois da quebra do
usuário, dava 14 páginas, mas com uma página em branco entre o sumário e o histórico, que o Word não tem:
foi descartada.

### Gate de desempenho (p95 da digitação, 80 teclas com pintura, uma medida por processo)

Árvore base = 0.1.20 (`git archive HEAD`), árvore nova = 0.1.22, alternadas, offscreen, um processo por medida (ms):

| Rodada | manual base | manual novo | simples base | simples novo |
|---|---|---|---|---|
| 1 | 5,93 | 5,65 | 6,81 | 6,91 |
| 2 | 6,09 | 5,65 | 6,74 | 7,37 |
| 3 | 5,65 | 5,49 | 6,60 | 7,94 |
| 4 (novo primeiro) | - | - | 7,01 | 6,47 |
| 5 (novo primeiro) | - | - | 7,31 | 7,02 |
| 6 (novo primeiro) | - | - | 6,91 | 6,65 |
| 7 (novo primeiro) | - | - | 6,45 | 6,88 |

Diferença máxima do novo sobre a base: 1,34 ms num simples (rodada 3), abaixo de 1,5 ms; nas rodadas 4 a 7
a diferença oscila de -0,54 a +0,43 ms. Manual: negativo nas três. Dentro do ruído.

### Contrapartes e limites

- Copiar só a marca de um parágrafo só-quebra (seleção de 1 caractere) não leva a quebra, nas duas árvores
  (medido: 0.1.20 e 0.1.22). Já era assim; não foi tratado.
- Ctrl+Enter num parágrafo vazio continua como antes (a quebra no bloco novo, `PageBreak_AlwaysBefore`).
  Ao salvar e reabrir, o mesmo trecho vira parágrafo só-quebra (no fim). Pode haver uma linha de diferença
  entre a tela da sessão e a tela depois de reabrir. Não medido.
- A linha "Quebra de página" de um parágrafo só-quebra fica no fim dele (o bloco seguinte começa a página).
- Não conferido no Word: abrir o SIM salvo pela 0.1.22 (esperado 14 páginas no Word, sem a página em branco) e
  o arquivo com quebra digitada no parágrafo só-quebra.

## 0.1.23: PySide6 6.12.0 (troca de dependência, sem mudança de código)

Troca de `PySide6-Essentials==6.11.2` por `==6.12.0` (`requirements.txt`; `lxml` e os demais não mudam).
O projeto usa só o Essentials: o `PySide6_Addons` não entra. O `.spec` não cita versão. Plataforma de
medição: Windows 11, Python 3.13.17, offscreen para a suíte e o gate, `windows` para o oráculo e a regressão.

Venv de teste em `%TEMP%\ed123` (fora do repo), com `PySide6-Essentials` 6.12.0, shiboken6 6.12.0, lxml 6.1.3,
python-docx 1.2.0 e pyinstaller 6.22.3. O `.venv` do repo ficou em 6.11.2 até o fim.

### Suíte e build

| Verificação | 0.1.22 (6.11.2) | 0.1.23 (6.12.0) |
|---|---|---|
| `tests/rodar_todos.py` (offscreen) | 3411 ok, 0 falhas | 3411 ok, 0 falhas (`teste_base` passou com a seção do CHANGELOG) |
| Build (suíte, PyInstaller, autoverificação, fumaça, ZIP) | BUILD OK, autoverificação "EditDoc 0.1.22" | BUILD OK, autoverificação "EditDoc 0.1.23"; a `Qt6Core.dll` embutida diz 6.12.0 |

O build da 0.1.23 foi feito com o Python do venv de teste, repetindo as cinco etapas do `build.bat`
(o `build.bat` fixa o `.venv` do repo). Nenhum `EditDoc.exe` estava aberto.

### Páginas (oráculo `lastRenderedPageBreak`, Windows, 14 `.docx` de Downloads, somente leitura)

Obs.: o enunciado falava em 15 arquivos; a pasta tem 14 `.docx`, e o oráculo e a regressão usam os 14.

| Doc | Quebras do Word | Páginas 0.1.22 | Páginas 0.1.23 | Acerto 0.1.22 (par/lin) | Acerto 0.1.23 (par/lin) |
|---|---|---|---|---|---|
| 01 | 0 | 4 | 4 | 0/0 | 0/0 |
| 02 | 0 | 4 | 4 | 0/0 | 0/0 |
| 03 | 0 | 5 | 5 | 0/0 | 0/0 |
| 04 | 0 | 5 | 5 | 0/0 | 0/0 |
| 05 | 0 | 5 | 5 | 0/0 | 0/0 |
| 06 | 0 | 6 | 6 | 0/0 | 0/0 |
| 07 | 0 | 49 | 49 | 0/0 | 0/0 |
| 08 | 0 | 49 | 49 | 0/0 | 0/0 |
| 09 | 0 | 49 | 49 | 0/0 | 0/0 |
| 10 | 2 | 3 | 3 | 2/2 | 2/2 |
| 11 | 3 | 4 | 4 | 3/3 | 3/3 |
| 12 | 23 | 26 | 26 | 1/1 | 1/1 |
| 13 | 1 | 2 | 2 | 1/0 | 1/0 |
| 14 (SIM) | 13 | 13 | 13 | 1/1 | 1/1 |

Nada piorou. A medição da 0.1.23 foi feita na árvore final; a da 6.12 sobre o código 0.1.22 deu o mesmo.

### Regressão (abrir, salvar, reabrir, salvar; 14 `.docx`)

Em todos os 14: c14n igual à 0.1.22 em todas as partes (comparação por hash da forma canônica, `core.xml`
sem a data de gravação), mesmo número de páginas na abertura e na reabertura, e salvo 1 igual ao salvo 2.

### Gate de desempenho (p95 da digitação, `gate_p95.py`, 80 teclas com pintura, um processo por medida, ms)

Três rodadas intercaladas (rodada 1 base primeiro, rodada 2 novo primeiro, rodada 3 base primeiro):

| Rodada | manual 0.1.22 | manual 0.1.23 | simples 0.1.22 | simples 0.1.23 |
|---|---|---|---|---|
| 1 | 6,42 | 6,31 | 7,88 | 8,30 |
| 2 | 6,45 | 6,25 | 8,78 | 8,17 |
| 3 | 6,61 | 6,09 | 7,79 | 7,46 |

Diferença (0.1.23 menos 0.1.22): manual -0,11, -0,20 e -0,52 ms; simples +0,42, -0,61 e -0,33 ms. A maior
diferença positiva é +0,42 ms, abaixo de 1,5 ms, e o mesmo código varia até quase 1 ms entre rodadas. Dentro do ruído.

### Limites

- Não medido no Windows com o Word: a paginação do SIM segue em 13 páginas (o Word dá 14), pela mesma causa
  de fonte ausente anotada na 0.1.22.
- A leitura de tela (limite do PySide6) não foi reavaliada na 6.12.

## Pendências

- 0.1.15: a tecla antes das tabelas do plano (20 a 28 ms do `QTextDocumentLayout`) só sai com
  uma reescrita (layout próprio para tabelas ou documento por trecho; ver "0.1.15"). O `.docx`
  real que abria com 4 páginas e reabria com 6 foi resolvido na 0.1.16.
- 0.1.16: paginação mais perto da do Word: feita na 0.1.17 (ver "0.1.17"). Conferir no Word: a
  fonte do texto sem formatação num arquivo sem `styles.xml` (Times New Roman 10).
- 0.1.22: abrir no Word, sem reparo, o SIM salvo pela 0.1.22 (esperado 14 páginas e sem página em branco
  entre a capa e o sumário) e um arquivo com texto digitado no parágrafo só com a quebra (ver "0.1.22").
- 0.1.17: a viúva de três linhas ou mais (descer uma linha só), a quebra de página seguida de
  quebra de seção "próxima página" (página a mais), a altura das linhas de tabela e o espaço no
  começo e no fim da célula; conferir no Word a soma dos espaços (o oráculo não a separou) e a
  linha da imagem com entrelinha múltipla (imagem + meia linha do texto, deduzido do arquivo 10).

- C5 (teclas mortas ABNT2, AltGr e Win+.) pelo roteiro em `spikes/pagina/RESULTADO.md`.
- 0.1.10: abrir no Word, sem reparo, um arquivo com notas gravado pelo EditDoc (nota nova,
  editada, convertida, com marca personalizada). O ponto "sumário" de 95 ms foi medido e
  corrigido na 0.1.11 (era a posição 0, antes das âncoras da capa).
- 0.1.11: abrir no Word, sem reparo, o arquivo que não salvava até a 0.1.10, gravado pela 0.1.11.
- 0.1.12: abrir no Word, sem reparo, um arquivo de três seções (uma paisagem, cabeçalhos
  herdados, página ímpar) gravado pelo EditDoc, e um com quebra de seção inserida e apagada.
- 0.1.12/0.1.14: digitação no arquivo real de duas seções a 1/3: a parte do EditDoc foi cortada
  na 0.1.14 (87 → 50 ms no roteiro da janela de 1400 × 950); o resto é o `insertText` do Qt, que
  refaz todas as tabelas abaixo do ponto (26 a 28 ms). Caminhos: um documento por trecho entre
  tabelas, ou layout próprio das tabelas de baixo (reescritas grandes).
- 0.1.14: abrir no Word, sem reparo, um arquivo com linha e coluna excluídas com o controle ligado,
  um movimento (recortar e colar) e as rejeições de tabela, célula e seção.
- 0.1.14: colunas de texto na tela e no PDF (spike feito, adiado: ver "0.1.14"; reavaliado na
  0.1.19, adiado de novo: ver "0.1.19", começando pela separação folha × página do Qt).
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

## 0.1.25: margem interna da célula (w:tcMar) na tela

Diagnóstico por quebra (scripts no scratchpad, fora do repositório; `diag.py`, `geo.py`). Para cada quebra
do Word (`w:lastRenderedPageBreak`), o bloco e a tabela onde o Word começa a página e o bloco e a tabela
onde o EditDoc começa a mesma página. O oráculo só bate com a referência na plataforma `windows`
(`QT_QPA_PLATFORM=windows`): em `offscreen`, o manual dá 46 páginas em vez de 49.

Os rótulos doc_NN seguem a ordem de nome em string (case-sensitive), não a ordem de Path do Windows.

Causa achada no doc_14: a quebra 3 do Word cai dentro de uma tabela de 10 linhas (stakeholders). 359
células trazem `w:tcMar` de 50 twips em topo e base (e 90 na esquerda e na direita). A tela usava só a
margem da tabela (`w:tblCellMar`, 10 twips), então a linha ficava mais curta que a do Word e a quebra
caía 11 blocos depois.

O que entrou: `formato_docx/propriedades.margens_da_celula_tw` lê o `w:tcMar` dos extras da célula, e
`ponte_qt/para_qt.aplicar_formatos_das_celulas` usa essa margem lado a lado, com a margem da tabela como
fallback. O `w:tcMar` continua nos extras e volta ao arquivo como veio: a gravação não muda.

Medido (oráculo, Windows, 14 arquivos de Downloads, páginas | par/lin):
- doc_14: 13 | 1/1 -> 14 | 3/3 (Word: 14 páginas).
- Os outros 13: iguais a 0.1.24.
- Regressão abrir-salvar-reabrir-salvar: c14n igual à 0.1.24 nos 14; salvo1 == salvo2 em todos.
- Suíte completa: 3416 verificações ok, 0 falhas. Novas: 6 em `teste_paginacao_word`
  (`testar_margem_da_celula`); a contraprova com a correção desligada dá 3 falhas.
- Gate p95 (offscreen, 3 rodadas intercaladas base x nova): manual dentro do ruído (-0,35 a +0,49 ms);
  simples +0,36 a +1,04 ms (abaixo de 1,5 ms); plano com dispersão grande (31 a 49 ms nos dois lados),
  a direção inverte na rodada 2 (-6,9 ms). Não consistente pelo critério; fica como ressalva, sem
  nova rodada.

Não entrou (diagnosticado, fica para a próxima versão):
- Altura mínima de linha (`w:trHeight`). A tela não aplica (`Linha.altura_tw` só é guardada). O Qt não tem
  altura de linha em `QTextTableCellFormat`; a emulação seria por preenchimento inferior da célula, com a
  altura natural da linha. O experimento de altura natural pela geometria dos blocos de célula deu valores
  inconsistentes (`blockBoundingRect` dentro de célula não serve direto), então não foi implementado. Suspeita
  para o doc_12: a quebra 1 diverge (bloco 36 no Word, 37 no EditDoc) fora de tabela, depois de uma tabela
  inicial com `trHeight` (440, 379, 413, 418, 540 twips).
- Espaço antes do primeiro e depois do último parágrafo da célula (o Qt ignora). Não medido isoladamente.
- Viúva de três linhas ou mais (o Qt desce uma linha só). Não apareceu como causa nas quebras medidas.

Experimento descartado: folga uniforme na margem de baixo de todas as tabelas (0, 150 e 300 twips). Com
folga, piora os docs 10 a 14 (doc_10 3 -> 5 páginas; doc_14 13 -> 16). O erro não é uniforme por tabela.
