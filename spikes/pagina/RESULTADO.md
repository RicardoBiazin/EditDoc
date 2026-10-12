# Spike A: visao em paginas sobre QTextDocument

Data: 11/10/2026. Maquina: Windows 11, Python 3.13.14, PySide6 6.11.2, `QT_QPA_PLATFORM=offscreen`.
Numeros saem de `testes_pagina.py` (saidas das rodadas finais: DPR 1, 1.5 e 2).

## Veredito: PASSA COM RESSALVAS

A arquitetura serve: paginacao, fronteiras, hit-test, WYSIWYG (tela = previa = PDF), desfazer,
cabecalho/rodape e tabelas atravessando paginas passam, com numeros. Duas ressalvas bloqueiam
"PASSA" limpo: (1) a pintura de um quadro (C1) nao fecha de forma estavel: com escala 100%, o p95
a 25% de zoom ficou entre 13 e 19 ms entre rodadas, e em HiDPI (DPR 1,5 e 2) passa de 25 ms; (2) C5
depende de teste manual.

## Tabela

Medidas de DPR 1 (100%) salvo onde indicado. "Passa?" segue o criterio escrito; nada foi ajustado.

| Criterio | Medido | Passa? | Observacao |
|---|---|---|---|
| C1 Layout / edicao / pintura | 95 pag, 5658 linhas, 10 tabelas. Layout inicial 0,32 s (build + layout). Edicao no meio p95 13,0 ms. Pintura p95 (viewport.grab, 30 quadros): 25% = 19,4 ms, 100% = 14,7 ms, 400% = 17,8 ms. DPR 1,5: 25% = 25,0; 400% = 42,7. DPR 2: 25% = 31,8; 400% = 49,3 | FALHA (intermitente em DPR 1) | Em rodadas anteriores no mesmo DPR 1 o 25% deu 13,6 ms (passou). Benchmark de CPU da maquina variou de 95 a 155 ms na sessao. Mediana de pintura 8 a 12 ms em DPR 1 |
| C2 Fronteiras | 0 linhas cruzando nas 100 verificacoes (5690 linhas, 96 pag) | PASSA | Controle negativo (fronteira deslocada 73 twips) acusa 102 linhas |
| C3 Hit-test | 3000 ida-e-volta (1000 por zoom), origem fracionaria em todas: 0 falhas, maior diferenca 0 caracteres | PASSA | Controle negativo (deslocamento de 3 linhas) acusa 300 de 300 |
| C4 Selecao | Shift+clique pag 2 a 7: pixels azuis em 2..7 (206645, 259658, 254779, 242503, 251332, 36918), zero em 1 e 8. Ctrl+C igual ao selecionado (22890 car). Tabela colada mantem 3x3 | PASSA | |
| C5 Teclas mortas ABNT2, AltGr, Win+. | Nao automatizado | PENDENTE MANUAL | Roteiro abaixo |
| C6 Desfazer | 50 operacoes (13 digitar, 12 colar, 5 quebra, 13 negrito, 7 enter). Desfazer 52x: HTML identico ao inicial; caret volta a 141017 (= inicial). Refazer igual | PASSA | Caret volta porque a primeira operacao foi digitacao no caret inicial |
| C7 WYSIWYG | Paginas: tela 95, previa 95, PDF 95 (contagem de /Type /Page nos bytes). Pagina 1 a 150 dpi, tela x impressao: 0,00% dos pixels com diferenca > 32 (DPR 1 e 1,5); 0,06% (DPR 2) | PASSA | Limiar de diferenca fixado antes de medir (> 32 por canal). Controle: pagina 1 x pagina 2 acusa 60399 amostras |
| C8 Cabecalho / rodape | 191 checagens (antes e depois de quebra de pagina): 0 erros de texto, 0 paginas com pixel diferente. Custo por pagina: media 0,15 ms, p95 0,31 ms, max 1,1 ms | PASSA | Controle "de 96" x "de 97" acusa 121 pixels |
| C9 Zoom | Troca de zoom max 0,03 ms. Paginas 95 -> 95. Posicoes de 41 paragrafos iguais | PASSA | Medido sem paint; zoom nao refaz layout |
| C10 HiDPI (1, 1,5 e 2) | Bordas da folha em pixel inteiro: 0 violacoes em 297, 445 e 594 amostras. Hit-test ida-volta 0/300 falhas nos tres DPRs. Hash do mapeamento fixo igual: 33ee88cbb2ee063e | PASSA | Suite rodada inteira nos tres DPRs |
| C11 Tabela entre paginas | Cabecalho repete no topo da pag 3 (vermelho a 23 twips do topo do corpo). 12 celulas divididas entre paginas. Tab navega 4/4 corretamente. Clique acima da fronteira -> pag 1, abaixo -> pag 2 | PASSA | Tab automatizado via QTest |
| C12 Imagem grande | 3000x3000 px -> 605x605 px96 (limite 605x907), cabe numa pagina. Sem limite a linha mede 45000 twips (corpo 14004): estoura | PASSA | Campo (propriedade de formato): texto digitado logo depois herda sem sanitizacao e nao herda com o controle |
| C13 Ciclo de vida | 100 documentos por modo, processo isolado: modos de producao (device guardado, painter fechado, fechar()) saem 0. Modos sem dono (device local) saem 0 em 100 e 1000 ciclos. Controle "pintor_aberto" (device destruido com QPainter ativo) sai 0xC0000005 (segfault) em todas as rodadas em que foi executado, inclusive as tres rodadas finais | PASSA | Condicao do segfault: device destruido com painter ativo. Sem painter ativo nao reproduziu |

## Achados que mudam o desenho

1. **Pintura e o gargalo.** O custo cresce com os pixels de dispositivo visiveis: a 400%, o quadro
   (com uma folha inteira visivel) custa 2,8 ms em DPR 1 e 11,9 ms em DPR 2. Cabecalho e caret nao
   pesam; preenchimento de folhas 0,03 ms. Causa provavel: rasterizacao do texto na escala de
   dispositivo. Hipotese nao testada: cache de paginas rasterizadas (tiles por zoom e DPR).
2. **Hit-test e layout tem tres armadilhas.** (a) `QTextLayout.position()` e relativa dentro de
   celulas de tabela: a origem do bloco vem de `blockBoundingRect().topLeft()`. Antes, 498 de 1398
   verificacoes de posicao caiam fora. (b) O `FuzzyHit` cruza a fronteira: clique no espaco em branco
   no fim da pagina vai para a pagina seguinte. Corrigido restringindo a pagina clicada. (c) O Qt nao faz
   viuva/orfa: 15 orfas e 13 viuvas em 95 paginas. Precisa de controle proprio ou decisao de produto.
3. **Vida util de objetos Qt e ambiente de teste.** Device destruido com `QPainter` ativo derruba o
   processo. `QPrintPreviewWidget` guarda so um ponteiro para o `QPrinter`: se o Python coletar o
   printer, o primeiro `show()` derruba o processo (corrigido guardando a referencia). Com
   `QT_QPA_PLATFORM=offscreen` o banco de fontes vem VAZIO neste PC: sem carregar os .ttf do Windows,
   cada caractere vira caixa com avanco de 1 em. `QTest.keyClick` com acento insere 0xC3, e
   `QTest.keyClicks` com acento derruba o processo: acento entra por `QKeyEvent` com `text()`.

Outros: troca de zoom e relayout (C9) sao baratos. Propriedade de campo se propaga para o texto
digitado (corrigido em `_formato_digitacao`). O objeto de imagem nao se propagou nesta versao.

## Roteiro manual (C5)

Rodar `.venv\Scripts\python.exe spikes\pagina\demo_manual.py` (janela nao modal, nao e rodada pela suite).
Com teclado ABNT2 em portugues do Brasil, no corpo do documento:

1. Apertar `´` (acento agudo) e depois `a`: deve sair `á`. Repetir com `e`, `i`, `o`, `u`.
2. Apertar `~` e depois `a`: deve sair `ã`. Repetir com `o`.
3. Apertar `^` e depois `e`: deve sair `ê`.
4. Apertar `` ` `` (crase) e depois `a`: deve sair `à`.
5. Apertar `ç` (tecla ao lado do L): deve sair `ç` minusculo; com Shift, `Ç`.
6. AltGr + `q` deve sair `@`; AltGr + `2` deve sair `²`.
7. Win + `.` deve abrir o painel de emoji do Windows; escolher um emoji e ver se o texto entra no caret.
8. Conferir que cada caractere entra uma vez (nao duplicado) e no lugar do caret.

Passa se todos os itens saem certos. Falha se qualquer acento sair como dois caracteres, se o caret
nao acompanhar, ou se o emoji nao entrar.

## O que NAO da para testar automaticamente aqui

- C5 inteiro: teclas mortas e AltGr chegam pelo sistema operacional, nao por evento sintetico.
- Caret piscando e aparencia visual real (so se mediu pixel, nao se olhou com um usuario).
- Impressao em impressora real e drivers: a previa e o PDF sao testados, a impressora nao.
- Arrasto de selecao com mouse real (testado com eventos sinteticos) e rolagem suave.
- Tamanho e qualidade de fonte em outras fontes que nao Arial e Calibri.
- Pintura em hardware fixo: os tempos de C1 variam 2 vezes entre rodadas (ver referencia de CPU no log).

## Como reproduzir

```
cd C:\DEV\EditDoc
.venv\Scripts\python.exe spikes\pagina\testes_pagina.py
.venv\Scripts\python.exe spikes\pagina\testes_pagina.py C1 C10
$env:QT_SCALE_FACTOR = "1.5"; .venv\Scripts\python.exe spikes\pagina\testes_pagina.py; Remove-Item Env:QT_SCALE_FACTOR
```

Saidas (PDF, PNG, JSON) vao para a pasta de rascunho do scratchpad, nunca para o repositorio.
`SPIKE_SAIDA` muda a pasta. Os modulos ficam em `spikes\pagina\`: `layout_paginado.py`,
`vista.py`, `controle.py`, `cabecalho_rodape.py`, `exportacao.py`, `testes_pagina.py`, `demo_manual.py`.
`editdoc\`, `tests\`, `build.bat` e `EditDoc.spec` nao foram tocados.
