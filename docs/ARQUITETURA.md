# Arquitetura e plano

Este documento registra o que foi decidido e o porquê. Quando o código divergir
daqui, o documento muda junto, no mesmo commit.

## Decisões do usuário

- Desktop em Python 3.13 e PySide6, para Windows.
- Formato nativo `.docx`: abrir e salvar.
- Repositório público no GitHub, licença MIT.
- A primeira versão utilizável (0.1.0) precisa ter: visão em páginas A4 com
  margens e quebras, tabelas e imagens, cabeçalho, rodapé e número de página,
  estilos com faixa de opções, além de digitar, formatar fonte e parágrafo,
  listas, desfazer, localizar, abrir e salvar. Feita: é a 0.1.0 (M8).
- Uma janela por documento, como o Word (desde o M2).
- A recuperação automática guarda o CONTEÚDO (uma cópia `.docx` do documento alterado),
  não o estado da sessão (janelas, cursor, desfazer). Decidido antes do M8.

## Camadas

```
editdoc/modelo/        o documento, puro Python, sem Qt e sem lxml
editdoc/formato_docx/  leitura e escrita de .docx (lxml + zipfile), sem Qt
editdoc/ponte_qt/      modelo <-> QTextDocument; é o único que importa QtGui
editdoc/interface/     janelas, faixa, visão em páginas, diálogos
```

O modelo intermediário existe para duas coisas: a fidelidade do ida-e-volta é
medida sobre o modelo, não sobre XML nem sobre formatos do Qt; e a leitura
pesada roda fora da thread da interface.

## Visão em páginas

Implementada no M3 (0.0.6). Ficou assim:

- `editdoc/interface/vista_paginas.py` é um `QAbstractScrollArea` que pinta as folhas. Uma
  única função, `desenhar_folha`, pinta a página para a tela e para qualquer outro destino
  (o PDF e a impressora usam a mesma, desde o M7).
- `editdoc/interface/layout_paginado.py` guarda o `QTextDocument` com `pageSize` igual ao corpo
  da página e `documentMargin` zero. O layout roda num dispositivo de 1440 dpi: uma unidade vira
  um twip, a unidade do `.docx`.
- `editdoc/modelo/folhas.py` faz o mapeamento entre documento (twips) e tela (pixels lógicos) sem
  Qt: é testável sem janela.
- `editdoc/interface/painel_documento.py` é o editor. Mantém a API do `QTextEdit` (nomes e sinais)
  para que comandos, formatação, busca e janela não mudem. Caret, teclado, mouse, seleção, clipboard
  e desfazer são dele.

Decisão de teclado: um `QTextEdit` oculto sobre o mesmo documento não serve. Ele força
`pageSize = (largura, -1)` ao ser criado e apaga a paginação (medido: 20 páginas viram 1). A
alternativa escolhida é o controle próprio, com a API do `QTextEdit`.

Zoom: troca a escala e não refaz o layout. Tem teto pela escala da tela (zoom × DPR ≤ 3): 300% em
DPR 1, 200% em DPR 1,5 e 150% em DPR 2. Acima disso o Qt pinta texto de fonte grande por caminho, e a
digitação passa de 16 ms. Medido no Gate do M3, em docs/SPIKES.md.

Cache de páginas: a folha é cortada em tiles de 256 px lógicos, no DPR da tela. Edição só invalida a
faixa alterada, ou tudo abaixo quando a altura do documento muda. O cache tem teto de 64 MB.

Quebra de página: um atributo do parágrafo (`quebra_antes`). No `.docx` é `w:br w:type="page"` no
começo do parágrafo. Quebra no meio do texto, ao ler, vira dois parágrafos: é a única perda de
estrutura, e a aparência não muda.

Limites aceitos: o Qt não tem viúva e órfã (fora do M3); uma tabela se divide entre páginas por
linha; `` não quebra página (usa-se a política de quebra do bloco).

## Tabelas e imagens

Implementadas no M4 (0.0.7).

- Modelo: `Documento.paragrafos` passou a ser a lista de blocos do corpo, `Paragrafo` ou
  `Tabela` (o nome do campo ficou o do M2). `Tabela` tem a grade (`colunas_tw`), linhas e
  células; a célula tem os seus próprios blocos e pode ter outra tabela. A mescla segue o
  `.docx`: `colunas` é o `gridSpan`, e `mescla_vertical` é `inicio` ou `continua` (o `vMerge`).
- Imagem na linha: um `Run` com `imagem` e o texto U+FFFC (o mesmo caractere que o Qt usa). Os
  bytes são os do arquivo, sem recodificar; o tamanho fica em EMU.
- Ponte Qt: a tabela vira `QTextTable` com borda colapsada, largura fixa por coluna e
  `rowSpan`/`columnSpan`. O que o Qt não guarda (bordas do arquivo, sombreamento, altura da
  linha, largura `tblW`) vai em JSON numa propriedade de usuário do formato da tabela e da
  célula, e volta igual. A borda que aparece na tela é recalculada pela posição da célula
  (`aplicar_formatos_das_celulas`) a cada mudança na grade.
- O Qt exige um bloco antes e depois de cada tabela. O bloco que o modelo não tem (tabela no
  começo do documento ou da célula, duas tabelas seguidas) leva a marca `PROP_ESTRUTURAL` e,
  vazio, não volta para o modelo. Medido no M8 (Qt 6.11.2): o bloco antes da tabela não ocupa
  altura, a tabela começa no topo do corpo e duas tabelas seguidas se encostam
  (`tests/teste_limites.py`).
- Tabela mais larga que o corpo (M8): a pintura recorta pela largura da folha, não pela do
  corpo, e a tabela entra na margem direita, como no Word.
- Imagem no Qt: o recurso do documento é uma prévia (no máximo 1800 px no lado maior); os bytes
  ficam num registro por conteúdo (`ponte_qt/imagens.py`), porque o Qt troca o recurso pela
  imagem decodificada depois de desenhar. O `DocumentoQt` busca no registro a imagem colada de
  outra janela e nunca lê recurso de arquivo nem de rede.
- Escrita: toda tabela usa o estilo "Table Grid" (espaçamento zero dentro da célula, como no
  Word) e grava os seis lados da borda. Célula e corpo sempre terminam em parágrafo.

Limites: o Qt refaz o layout da tabela inteira a cada tecla (cerca de 0,06 ms por célula,
medido; ver docs/SPIKES.md). Por isso o leitor transforma em parágrafos, com aviso, a tabela
acima de 2000 linhas, 63 colunas ou 5000 células, ou aninhada mais de 4 níveis. Imagem
flutuante (`wp:anchor`) vira imagem na linha, com aviso; o posicionamento flutuante fica para
depois da 0.1.0 (formas e caixas de texto).

## Cabeçalho, rodapé e número de página

Implementados no M5 (0.0.8).

- Modelo: `Documento.cabecalhos` e `Documento.rodapes` levam o tipo (`padrao`, `primeira`,
  `par`) aos blocos daquela parte (parágrafos, tabelas e imagens, como no corpo). Tipo ausente =
  o arquivo não tem a parte. `Pagina` ganhou `primeira_diferente` (`w:titlePg`),
  `pares_impares` (`w:evenAndOddHeaders`, no `settings.xml`), `formato_numero` e
  `numero_inicial` (`w:pgNumType`). Distâncias: `cabecalho_tw` e `rodape_tw` (`w:pgMar`).
- Campo: um `Run` com `campo` (a instrução, `PAGE` ou `NUMPAGES` com as opções) e o texto do
  último resultado. `modelo/campos.py` calcula o valor de cada página (decimal, romanos, letras,
  número inicial) e qual variante vale em cada página. No `.docx` o campo sai como campo
  complexo (`fldChar` begin/separate/end), como o Word grava; o leitor aceita também
  `fldSimple`. Outros campos (DATE, TOC, REF) ficam com o último resultado como texto, com o
  aviso CAMPO.
- Qt: cada variante é um `QTextDocument` próprio (`interface/cabecalhos.py`), no mesmo
  dispositivo de 1440 dpi do corpo, com a largura do corpo e sem paginação; cada um tem o seu
  desfazer. O campo é um objeto na linha (`ponte_qt/campos.py`): o manipulador do layout
  calcula o texto na hora de pintar, então o mesmo documento mostra 1 numa página e 2 na outra
  sem mudar o texto, o desfazer ou o "alterado". No cabeçalho, o contexto diz a página que está
  sendo pintada e o layout é refeito com `markContentsDirty`; no corpo, a página sai da posição
  do objeto, e a largura é a do maior valor possível.
- Visão: o cabeçalho e o rodapé não entram no cache de tiles; são pintados por cima, em cada
  folha visível (`desenhar_faixas`), esmaecidos fora da edição. Na edição o corpo esmaece, e
  uma linha tracejada com rótulo ("Cabeçalho - Primeira página") marca a área.
- Corpo empurrado: se o cabeçalho passa da margem de cima (ou o rodapé da de baixo), o corpo
  desce, como no Word. `LayoutPaginado` tem duas páginas: a do arquivo (`pagina_arquivo`, que
  se grava) e a efetiva (`pagina`, que a tela usa). Diferença do Word: a altura é a mesma em
  todas as páginas (a maior das variantes em uso), porque o corpo de cada página tem o mesmo
  tamanho no layout do Qt.
- Edição no lugar: duplo clique na margem entra; duplo clique no corpo ou Esc sai. Na edição,
  `PainelDocumento.document()` devolve o documento do cabeçalho, e os comandos (formatação,
  tabela, imagem, busca) funcionam sem mudança. O corpo é sempre `documento_corpo()`: é ele que
  a janela grava e que diz se há alteração.

Limites: uma seção só (de várias seções, valem os cabeçalhos da última, com a herança do Word,
e o aviso CABECALHO_SECAO); parte de cabeçalho acima de 4 MB não é lida (aviso); campo
aninhado mais de 8 níveis não é interpretado. Copiar e colar um campo leva só o texto ao
redor (o HTML do Qt não carrega o objeto).

## Estilos e formatação

Implementados no M6 (0.0.9).

- O estilo nomeado fica numa propriedade de usuário do bloco (`PROP_ESTILO`) ou do
  fragmento (`PROP_ESTILO_CAR`), em `ponte_qt/estilos.py`. O nível de estrutura efetivo
  (Título 1 = 0) fica em `PROP_NIVEL`: é o que o painel de navegação lê.
- A formatação efetiva é gravada nos formatos do Qt. No salvamento, o que
  difere do estilo vira formatação direta (`Paragrafo` e `Run` guardam só a direta).
- "Atualizar estilo" troca, em um único passo de desfazer, o que ainda era igual
  ao estilo antigo. Modificar um estilo recompõe os parágrafos que o usam (e os que herdam
  dele) do mesmo jeito.
- O Word grava nomes canônicos em inglês (`heading 1`); o mapeamento usa o nome,
  não o id, porque o id em pt-BR vem sem acento.
- Modelo: `modelo/estilos.py` (catálogo, herança `basedOn`, conjunto padrão), puro Python.
  `Documento.estilos` leva o catálogo, fora da comparação de documentos.
- Arquivo: `formato_docx/estilos.py`. O catálogo guarda o `styles.xml` original; ao gravar,
  o estilo não alterado volta byte a byte, e o alterado só tem reescritos os atributos que
  mudaram. O `numPr` sai dos estilos (o `numbering.xml` de origem não volta): a lista do
  estilo passa ao parágrafo na leitura. O tema volta igual, para as fontes de tema.
- Desfazer: o catálogo vigente fica em JSON no formato do quadro raiz do documento. Trocar
  esse formato entra no desfazer do Qt, no mesmo passo do bloco de edição aberto (medido no
  Qt 6.11); o PySide 6.11 não exporta `QAbstractUndoItem`. O XML original fica no
  catálogo-base, num atributo do objeto do documento. Cabeçalho e rodapé usam o catálogo
  do corpo.
- `docDefaults`: a fonte e o tamanho viram a fonte padrão do `QTextDocument`. Desde o M8 o
  parágrafo do `docDefaults` (8 pt depois, 1,08 no Word) fica por baixo da cadeia de estilos
  fora das tabelas (`Estilos.resolver_paragrafo(com_padrao=True)`, `Resolvedor.paragrafo(sid,
  em_tabela)`); na célula não, porque o "Table Grid" do Word zera esse espaçamento. A tela e
  a extração usam a mesma regra, então o espaçamento não vira formatação direta ao salvar. O
  documento novo da janela nasce com `catalogo_de_documento_novo` (fonte e tamanho da
  preferência, espaçamento do Word), o mesmo `docDefaults` que o escritor grava.

## Faixa e Exibir

Implementadas no M6 (0.0.9). Cada aba é uma `LinhaDeGrupos` com a sua ordem de
recolhimento; Fonte e Parágrafo ficam em duas linhas. A galeria de estilos tem preferência
sobre o grupo Edição (`planejamento.recolher_com_galeria`). As marcas de formatação são
pintadas por `desenhar_marcas`, na função da folha, e entram no cache de tiles: o
`QTextOption` do Qt com marcas mudaria a largura do texto e a paginação. "Várias páginas"
põe as folhas lado a lado (`Mapa.colunas`).

## Impressão e PDF

Implementados no M7 (0.0.10), em `editdoc/interface/impressao.py`.

- Uma função pinta a folha n em qualquer `QPainter` (`pintar_pagina`): o corpo por
  `desenhar_folha` e o cabeçalho e o rodapé por `desenhar_faixas`, as mesmas da tela, a
  partir do mesmo `LayoutPaginado`. Por isso a paginação impressa é a da tela. Fica fora o
  que só a tela tem: fundo, sombra, marcas de formatação, linha de quebra, véu e rótulo da
  edição do cabeçalho, caret, seleção e alças. O cabeçalho sai com opacidade 1.
- Escala: dpi do dispositivo / 1440. O PDF roda a 1440 dpi (escala 1). O texto sai como
  texto, com a fonte TrueType embutida em subconjunto pelo `QPdfWriter`.
- PDF: montado na memória (`QBuffer`) e gravado com a troca atômica, com conferência do
  arquivo relido (começa com `%PDF-`, termina com `%%EOF`, tem o número de páginas
  pedido). Cancelar no meio não grava nada. Papel e orientação vêm da página do
  documento, folha a folha (`pagina_da_folha`): com uma seção, todas iguais; o laço já
  troca o papel quando a folha seguinte for diferente. Metadados: título e autor do
  `docProps/core.xml` (sem título, o nome do arquivo) e criador "EditDoc x.y.z".
- Impressora: `QPrintDialog` com intervalo, página atual, cópias e agrupar; papel e
  orientação do documento com `setFullPage` (a origem é o canto do papel). Se a
  impressora não aceita o papel, o usuário escolhe se imprime no papel dela. Se o driver
  não faz as cópias, o EditDoc repete as folhas, agrupadas ou não. Sem impressora
  instalada, um aviso sugere o PDF.
- Pré-visualização: `QPrintPreviewDialog` com o mesmo `paintRequested`; o Imprimir de
  lá usa o intervalo e as cópias do diálogo dele.
- Trabalho longo: `QProgressDialog` com Cancelar, chamado a cada folha (a janela continua
  respondendo); medido: cerca de 2 ms por folha no PDF.
- Testes sem impressora real: `QPrinter` em `PdfFormat`, e o PDF lido de volta por um
  leitor mínimo (`tests/leitor_pdf.py`, só `re` e `zlib`; o PySide6-Essentials não traz o
  QtPdf). A autoverificação do `.exe` exporta e imprime um PDF de duas páginas.

Limites: a imagem sai na prévia do documento (no máximo 1800 px no lado maior), não nos
bytes originais; a impressora com área não imprimível corta o que estiver na borda (como
no Word); o `.txt` leva o último resultado guardado dos campos de página.

## Recuperação, preferências e acessibilidade

Implementadas no M8 (0.1.0).

- Recuperação automática (`editdoc/recuperacao.py`, sem Qt; `interface/guarda_recuperacao.py`
  por janela). Cada janela tem uma sessão com id próprio e grava `<id>.docx` (o mesmo `.docx`
  do Salvar, sem a conferência) e `<id>.json` (caminho original, nome, hora, versão, pid,
  tamanho e os avisos com perda do original) em `%LOCALAPPDATA%\EditDoc\Recuperacao`
  (`EDITDOC_RECUPERACAO` troca a pasta: testes e autoverificação). Grava pelo relógio
  (preferência, padrão 10 min) e depois de 300 alterações, com pausa de 1,5 s; só documento
  alterado e mudado desde a última cópia. Salvar apaga a cópia; fechar normalmente apaga e
  solta a trava.
- Trava: `<id>.trava` aberto com `LockFile` (msvcrt) enquanto a janela vive. O Windows solta a
  trava quando o processo morre, de qualquer jeito; o pid fica no arquivo só para
  diagnóstico (pid é reaproveitado, a trava não). A trava é por handle: outra janela do mesmo
  processo também não consegue travar, e isso é o que impede duas janelas de adotarem a
  mesma cópia. Na abertura do programa (instância principal), as cópias sem dono e inteiras
  (o `.docx` com o tamanho anotado no `.json`) são oferecidas no diálogo não modal
  "Recuperação de documentos". Abrir adota a trava da cópia (a janela continua gravando no
  mesmo id); o documento aberto não tem caminho, e salvar sugere o original.
- Preferências: `configuracao.py` valida tipo e faixa de cada chave (`validar`); fora disso, o
  padrão. Arquivo > Opções (`interface/dialogo_opcoes.py`) devolve o dicionário; a janela
  grava (`gravar_preferencias`, que não mexe nos recentes) e o gerente aplica a todas as
  janelas (recuperação, régua, abrir o PDF) e ao tema (`interface/tema.py`, por
  `QStyleHints.setColorScheme`). Fonte, tamanho e papel valem para o documento novo.
- Acessibilidade (`interface/acessibilidade.py`, `interface/dicas_teclas.py`). Nomes: o
  `BotaoAcao` usa a dica do comando, nunca o rótulo curto; `nomear_tudo` cobre o resto pela
  dica ou pelo texto; `sem_nome` é a mesma regra no teste. O documento: uma fábrica de
  interfaces acessíveis expõe o `PainelDocumento` como `EditableText`, com nome, descrição
  ("Página X de Y") e o parágrafo do cursor como valor; trocar de página anuncia
  (`QAccessibleAnnouncementEvent`). Teclado: os botões da faixa pegam foco só pelo teclado
  (`Qt.TabFocus`); um filtro de eventos do aplicativo, por janela, trata Alt sozinho, F10,
  F6, setas, Tab, Enter e as dicas de tecla.
- Limite medido: a `QAccessibleTextInterface` completa não é viável em Python no PySide6
  6.11.2 (`selection()` e `attributes()` não são exportados, e o UIA do Windows os chama ao
  listar os padrões: o processo cai). O valor com o parágrafo é o que dá para expor sem esse
  risco. Ver docs/SPIKES.md, M8.

## Política de perda

Cada recurso do `.docx` é exato, aproximado ou descartado com aviso. Se algo
que se perderia ao salvar estiver presente, a primeira gravação pede
confirmação e oferece "Salvar cópia". Comentários, revisões e notas de rodapé
entram aqui até as versões que os implementam.

## Ribbon

Ribbon próprio, com `QTabBar`, grupos e botões criados a partir de `QAction`.
Não usa biblioteca de terceiros: a `pyqtribbon` encontrada é de um mantenedor
e está em beta, e o colapso e a galeria de estilos teriam de ser contornados.
Reavaliar só se o ribbon próprio estourar o marco de faixa.

## Marcos

| Marco | Versão | Entrega |
|---|---|---|
| M0 Esqueleto | 0.0.1 (renomeado em 0.0.2) | repositório, build, testes e fumaça do `.exe` |
| M1 Editor básico | 0.0.4 (feito) | visão provisória, faixa com colapso, formatação, desfazer, localizar |
| M2 `.docx` de texto | 0.0.5 (feito) | abrir e salvar parágrafos, runs, listas simples; gravação atômica |
| M3 Visão em páginas | 0.0.6 (feito) | A4, Carta, Ofício, margens, régua, quebras, zoom, Página X de Y |
| M4 Tabelas e imagens | 0.0.7 (feito) | tabela e imagem inline, no `.docx` e na visão |
| M5 Cabeçalho e rodapé | 0.0.8 (feito) | edição no lugar, número de página |
| M6 Estilos e faixa final | 0.0.9 (feito) | galeria, abas Inserir, Layout e Exibir (abas contextuais de tabela e imagem ficaram para depois) |
| M7 Impressão e PDF | 0.0.10 (feito) | imprimir, pré-visualizar, exportar PDF (e texto `.txt`) |
| M8 Polimento | 0.1.0 (feito) | recuperação automática, preferências, acessibilidade, documentação final |

Caminho crítico: M1, M2 e M3. Antes do M3, um spike de página valida o controle
de texto próprio; se a tecla morta ou a IME falharem, o plano B é uma visão em
modo contínuo, com paginação só na impressão.

## Fora da 0.1.0

Revisão com controle de alterações, comentários, notas de rodapé, índices e
sumários, mala direta, equações, formas, caixas de texto, colunas, seções
múltiplas editáveis, ortografia (prevista para a 0.2 pela API do Windows),
`.doc`, RTF, ODT e macros (nunca).

## Riscos abertos

1. Espaçamento entre parágrafos: o Qt colapsa margens verticais para o maior
   valor, e o Word, ao que tudo indica, soma. Mede-se no M3.
2. O Word pode reclamar de um `.docx` gerado sem ser visto. Mitigação: vocabulário
   conservador, validação de ordem dos elementos, releitura antes da troca, e um
   protocolo de aceite manual com amostras.
3. Paginação diferente da do Word. Não se promete identidade de quebras.
