# SPIKE B: .docx com lxml + zipfile próprios

Data: 2026-10-11. Ambiente: Python 3.13.14, lxml 6.1.3, PySide6 6.11.2 (offscreen), python-docx 1.2.0 (só oráculo de leitura). Sem Word e sem LibreOffice nesta máquina.

## Veredito: PASSA COM RESSALVAS

Todos os critérios de passa foram atendidos (T1 a T8 sem falha; T6 com os 12 campos exatos e gaps documentados; T7 dentro da meta). Ressalvas: a abertura no Word continua pendente (PENDENTE MANUAL) e as margens verticais do Qt divergem do modelo de soma (risco R1).

## Tabela T1 a T8 (números medidos pela suíte)

| Teste | Medida | Resultado | Observação |
|---|---|---|---|
| T1 round-trip | 10 parágrafos, 15 runs, .docx de 3686 bytes | PASSA | modelo igual após ida e volta; 0 avisos; cobre negrito/itálico/sublinhado/tamanho/fonte/cor, None, acentos, emoji fora do BMP, tab, quebra, parágrafo vazio, alinhamento, recuos |
| T2 python-docx | 155 verificações de run e parágrafo, 0 divergências | PASSA | texto, bold/italic/underline (None quando None), tamanho, fonte, cor, alinhamento, recuos, espaçamentos, título e autor |
| T3 ordem e xml:space | fixture com 0 violações; lista de ordem igual à do python-docx 1.2.0 | PASSA | contraprova: `<b>` depois de `<i>` acusado (1); escritor sem xml:space acusado (9) |
| T4 pacote OPC | 8 partes, 2 .rels, 5 alvos resolvidos, 0 violações | PASSA | contraprovas: parte órfã, parte sem Content_Type e rel quebrada, todas acusadas |
| T5 hostis | 16 casos: 7 pedidos, 3 variantes de nome e 6 extras; todos com o código esperado | PASSA | maior tempo 0,026 s; nenhuma exceção vazou |
| T6 QTextDocument | 12 de 12 campos sem perda na fixture (15 runs) | PASSA com gaps | gaps listados abaixo |
| T7 desempenho | gravar 0,40 s; ler 0,15 s (meta 5 s); docx 49,5 KB | PASSA | pico RSS 80,6 MB na gravação e 79,5 MB na leitura (base 34,4 MB); document.xml comprime 60,7x |
| T8 idempotência | segunda ida com modelo igual e bytes idênticos (3684 bytes) | PASSA | exige data fixa no zip e datas preservadas no modelo |

## Contraprova geral (sabotagem)

Comando: `testes_docx.py --sabotar sem_xml_space`. Saída: `FALHA fixture sem violacao de ordem nem de xml:space (9 violacoes)`; T3 com FALHA; processo sai com código 1. T1, T2 e T8 continuam PASSA. Ou seja: round-trip e python-docx não enxergam a falta de `xml:space`; só a regra do validador enxerga.

## T6: o que mapeia e o que não mapeia

Mapeia sem perda (fixture): alinhamento, recuo esquerdo, recuo da primeira linha (positivo e suspenso), espaço antes e depois, texto, negrito, itálico, sublinhado, tamanho, fonte e cor.

- Tri-state: `hasProperty` distingue None (ausente) de False (peso 400 explícito). Não depende de HTML.
- Sublinhado: `setFontUnderline(False)` não grava "sem sublinhado" (a propriedade fica ausente), e na fixture o run seguinte herdou o sublinhado do anterior. Usar `setUnderlineStyle(NoUnderline)`, que foi a correção testada.
- Quebra interna: `\n` vira U+2028 no Qt. `toPlainText()` converte de volta, então a checagem tem de ler o texto do bloco.
- Fusão: runs vizinhos de mesma formatação viram um só (3 para 2 no teste). Não há perda de formatação, só de fronteira.
- Margens verticais: no Qt, duas margens de 16 px dão espaço de 16 px (colapso para o maior). Soma seria 32 px.
- Fora do mapeamento: título, autor, datas (o QTextDocument não os carrega), nomes de estilo, `w:lang`, bCs/iCs, cor `auto`, numeração, tabelas, campos, imagens.

## Achados que mudam o desenho

1. Qt: `setFontUnderline(False)` não grava "sem sublinhado" e o run seguinte herda o sublinhado; o colapso de margens é para o maior (16 px medidos). A ponte precisa de tabela explícita de mapeamento, com teste. Layout de espaçamento vai divergir do Word se o Word somar (risco R1).
2. `xml:space` só é pego pela regra do validador. Round-trip e python-docx passam com o defeito. A suíte de gravação precisa do validador de regras do Word, não só de round-trip.
3. `zipfile` no Windows troca `\` por `/` em `ZipInfo.filename`; o nome original fica em `orig_filename`. O leitor valida o nome bruto. Sem isso, a barra invertida passa.

Ordem OOXML: nenhuma surpresa. A lista da fato 10 é idêntica à do python-docx 1.2.0 (lida do fonte com `ast`). Libxml2 já recusa o billion laughs com "Maximum entity amplification factor exceeded", mesmo com `resolve_entities=False`.

## Riscos

- R1. Margens: Qt colapsa para o maior (medido); Word soma (hipótese ~80%, não verificada).
- R2. Espaços nas pontas sem `xml:space`: Word trima (regra da fato 13, não verificada no Word).
- R3. Razão de compressão: limite de 200x só vale acima de 10 MB. Documento real muito repetitivo pode ser recusado. Não medido em documento real.
- R4. Limite de descompactação em streaming (`read(limite+1)`) não foi testado isoladamente; o teste cobre o caminho pelo cabeçalho declarado.
- R5. Checagem de DOCTYPE é por bytes. UTF-16 é recusado por NUL e declaração de codificação. Declaração ISO-8859-1 com corpo válido não foi testada.
- R6. Perda de estrutura com aviso: `w:del` é descartado; tabelas, `w:sdt` e hyperlinks são achatados (o texto fica).
- R7. Estilos não estão no modelo. Quando entrarem, mapear por `w:name` ("heading 1"), nunca por styleId (pt-BR sem acento).
- R8. Validador cobre só pPr, rPr e xml:space. sectPr, tblPr e styles não são validados.
- R9. Pico de memória é RSS do processo (inclui lxml). Não foi usado tracemalloc, que não enxerga a memória do libxml2.

## Não verificado

- Word abrir sem reparo e sem "Modo de Compatibilidade" (compat 15 gravado, sem Word para conferir). PENDENTE MANUAL.
- Numeração, campos, imagens, cabeçalho e rodapé, notas, comentários.
- Paginação e quebra de página no Qt (ARQUITETURA prevê um spike próprio).
- Substituição de fontes e renderização real.
- Desempenho em outra máquina.

## Como reproduzir

```
C:\DEV\EditDoc\.venv\Scripts\python.exe -B C:\DEV\EditDoc\spikes\docx\testes_docx.py
C:\DEV\EditDoc\.venv\Scripts\python.exe -B C:\DEV\EditDoc\spikes\docx\testes_docx.py --sabotar sem_xml_space
```

`-B` evita `__pycache__` no repositório. Saídas (.docx e resumo.json) vão para o scratchpad `spike-docx` (variável `EDITDOC_SPIKE_SAIDAS` muda o destino).

## Arquivos

- `C:\DEV\EditDoc\spikes\docx\modelo.py`: dataclasses puras (Documento, Paragrafo, Run).
- `C:\DEV\EditDoc\spikes\docx\escritor.py`: gravação OPC com lxml e zipfile.
- `C:\DEV\EditDoc\spikes\docx\leitor.py`: leitura com limites e `ErroDocx`.
- `C:\DEV\EditDoc\spikes\docx\ponte_qt.py`: ponte para QTextDocument (só T6).
- `C:\DEV\EditDoc\spikes\docx\testes_docx.py`: suíte T1 a T8 e sabotagem.
