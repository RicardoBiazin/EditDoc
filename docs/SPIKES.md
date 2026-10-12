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

## Pendências

- C5 (teclas mortas ABNT2, AltGr e Win+.) pelo roteiro em `spikes/pagina/RESULTADO.md`.
- Abrir uma amostra `.docx` gerada pelo spike no Word, sem reparo. As amostras estão
  em `%TEMP%\claude\...\scratchpad\spike-docx`, fora do repositório.
- Cache de página para a pintura, a validar antes do M3.
- Fonte embutida para os testes de renderização visual.
