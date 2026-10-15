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
  um twip, a unidade do `.docx`. Medido na 0.1.4 (Qt 6.11.2): o layout escala as margens
  verticais do bloco (`topMargin` e `bottomMargin` em px96, × 15), mas não as horizontais
  (`leftMargin`, `rightMargin` e `textIndent` ficam na unidade do dispositivo). Por isso o
  espaço antes e depois vai em px96 e os recuos em twips (`ponte_qt/estilos.py`). Até a
  0.1.3 os recuos iam em px96 e apareciam 15 vezes menores.
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
Desde a 0.1.8 a faixa alterada é a das linhas (a anterior à da mudança e da linha da mudança até
a base do bloco, a de antes ou a de agora), não o bloco inteiro; o tile guarda a faixa do
documento cortada no corpo da página dele; e a conferência dos objetos flutuantes que refaz um
trecho tira do cache só dali para baixo.

Desde a 0.1.14, digitar numa célula não tira mais a tabela inteira do cache (numa tabela que
atravessa páginas, era a tela toda). No sinal `contentsChange` (layout ainda velho) a vista guarda
o retângulo da tabela de fora e o do bloco; na pintura, se a tabela tem o mesmo retângulo, as
outras linhas da tabela não se moveram: com o bloco do mesmo tamanho, saem só as linhas do texto
(a mesma regra do parágrafo); senão, só a linha da tabela (da base do texto da linha de cima ao
topo do texto da de baixo). Nos dois casos só os tiles que cruzam a coluna da célula (com 400
twips de folga): cada tile guarda também a faixa horizontal do documento que mostra. Tabela que
mudou de altura: a tabela inteira, como antes. Os números das listas guardam a faixa vertical
de cada item até o layout mudar (`Numerador.faixas`, pelo sinal `update` do layout): cada tile
olhava todos os itens. As bordas e tabulações (`propriedades.desenhar`) guardam o que cada bloco
tem para pintar até o documento mudar.

Desde a 0.1.15 a linha digitada não tira mais tiles inteiros do cache. A faixa da linha
(`_invalidar_linhas`, e a linha da tabela) anota no tile só a parte velha (`_sujos`, em twips do
documento, com 150 twips de folga na vertical); na pintura seguinte, antes de copiar os tiles
visíveis, cada tile com parte velha é pintado de novo num pixmap do tamanho dele, com a mesma
transformação do tile e o recorte do Qt só em volta das partes (mais 150 twips), e só os pixels
inteiros das partes são copiados por cima (`CompositionMode_Source`). A origem não pode ser
deslocada para juntar tiles vizinhos numa pintura só: o Qt arredonda a posição da letra de forma
diferente para coordenada negativa, e a letra da borda do tile mudava de pixel (medido a 137%). As
outras invalidações (altura do documento mudou, flutuantes refeitos, números de lista) tiram o
tile inteiro, como antes. Dois furos que o tile inteiro escondia: a linha que desce de página
dentro do bloco fica abaixo do `blockBoundingRect` (a faixa usa as linhas, `_extensao`), e o
número de lista recalculado fora da pintura (a janela pede o rótulo do cursor) não chegava à
pintura (a vista compara `Numerador.desenho` com o da pintura anterior). A lista dos blocos com
quebra de página do usuário, que a tela desenha a cada quadro, fica guardada até mudar o número
de blocos ou chegar uma troca de formato. Medido no plano real (máquina carregada): pintura da
célula a 1/3 de 15,9 para ~7 ms por tecla; a 1/2, 10,3 → 6,6; no item de lista, 8,9 → 7,1.

O que não dá para tirar daqui: o `insertText` do Qt, num documento paginado, refaz TODAS as
tabelas que vêm depois do ponto editado, as duas passadas de cada célula (medido e conferido no
código do Qt 6.11; docs/SPIKES.md, 0.1.14). Num documento com muitas tabelas, digitar no começo
custa dezenas de milissegundos que não são do EditDoc. O spike da 0.1.15 (docs/SPIKES.md) mediu
que isso acontece mesmo quando a altura do bloco não muda, e que nenhuma saída de baixo risco
corta a cascata: o layout preguiçoso do Qt só entra pelo layout inteiro e anda 1000 caracteres por
tecla; colapso de bordas e formato de célula valem um terço e mudariam a aparência; layout próprio
para tabelas ou um documento por trecho seriam reescritas do layout, da paginação e da edição.

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
flutuante (`wp:anchor`) virava imagem na linha, com aviso de perda da posição; desde a 0.1.2
ela é objeto opaco e volta ao arquivo com a posição (ver "Objetos opacos").

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
  `fldSimple`. Os outros campos (DATE, TOC, REF...) ficavam com o último resultado como
  texto, com o aviso CAMPO; desde a 0.1.3 são preservados (ver "Partes do pacote,
  hiperlinks e campos").
- Qt: cada variante é um `QTextDocument` próprio (`interface/cabecalhos.py`), no mesmo
  dispositivo de 1440 dpi do corpo, com a largura do corpo e sem paginação; cada um tem o seu
  desfazer. O campo é um objeto na linha (`ponte_qt/campos.py`): o manipulador do layout
  calcula o texto na hora de pintar, então o mesmo documento mostra 1 numa página e 2 na outra
  sem mudar o texto, o desfazer ou o "alterado". No cabeçalho, o contexto diz a página que está
  sendo pintada e o layout é refeito com `markContentsDirty`; no corpo, a página sai da posição
  do objeto, e a largura é a do maior valor possível.
- Visão: o cabeçalho e o rodapé não entram no cache de tiles; são pintados por cima, em cada
  folha visível (`desenhar_faixas`), esmaecidos fora da edição. Desde a 0.1.8, fora da edição,
  cada faixa de cada folha é pintada uma vez num QPixmap guardado (`VistaPaginas._faixa_da_tela`,
  chave com a revisão da faixa, a página, o total, o zoom e o DPR); na edição, direto. Na edição
  o corpo esmaece, e uma linha tracejada com rótulo ("Cabeçalho - Primeira página") marca a área.
- Corpo empurrado: se o cabeçalho passa da margem de cima (ou o rodapé da de baixo), o corpo
  desce, como no Word. `LayoutPaginado` tem a página do arquivo (`pagina_arquivo`, que se
  grava), a efetiva (`pagina`, com a maior altura de cabeçalho e de rodapé entre as variantes)
  e, desde a 0.1.8, a efetiva de cada folha (`efetiva_da(n)`, `topo_da_pagina(n)`): o topo do
  corpo da folha n é max(margem de cima, distância do cabeçalho + altura do cabeçalho DA
  PÁGINA: primeira, par ou padrão), sem o pé do corpo passar do rodapé da página. A tela
  (tiles, `Mapa.topo_da_pagina`), o PDF e a impressão (`desenhar_folha`), o clique
  (`tela_para_doc`, `zona_em`), os objetos flutuantes (`Contexto.topos`) e o rótulo da edição
  usam a efetiva da folha. Os campos não mudam (a página sai da posição no documento, que é a
  mesma). Limite: a altura do corpo (`hb`) é a mesma em todas as folhas, a da efetiva com o
  maior cabeçalho e o maior rodapé, porque o `QTextDocument` pagina com um tamanho só
  (`pageSize`). O topo por página é exato; a capacidade é a da menor página: na folha de
  cabeçalho menor o corpo termina mais acima e cabe o mesmo texto que nas outras (o Word poria
  mais). Caminhos estudados: margem do quadro raiz (vale em todas as páginas, o Qt não separa
  a primeira) e margem negativa no primeiro bloco (é conteúdo: entraria no arquivo, no
  desfazer e no Enter). Ficam para um layout próprio.
- Edição no lugar: duplo clique na margem entra; duplo clique no corpo ou Esc sai. Na edição,
  `PainelDocumento.document()` devolve o documento do cabeçalho, e os comandos (formatação,
  tabela, imagem, busca) funcionam sem mudança. O corpo é sempre `documento_corpo()`: é ele que
  a janela grava e que diz se há alteração.

Limites: até a 0.1.11, uma seção só (de várias seções, valiam os cabeçalhos da última, com o
aviso CABECALHO_SECAO); desde a 0.1.12 cada seção tem os seus (ver "Seções"); parte de
cabeçalho acima de 4 MB não é lida (aviso); campo
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
  mudaram. O `numPr` do estilo fica no estilo desde a 0.1.4 (até a 0.1.3 ele saía e a lista
  passava ao parágrafo, porque o `numbering.xml` de origem não voltava; ver "Listas e
  numeração"). O tema volta igual, para as fontes de tema.
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
  documento, folha a folha (`pagina_da_folha`, desde a 0.1.12 a da seção da folha): o laço
  troca o papel quando a folha seguinte é diferente (no PDF e, desde a 0.1.12, na impressora). Metadados: título e autor do
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

## Objetos opacos

Implementados na 0.1.2. O que o EditDoc não edita, mas consegue guardar, deixa de ser
descartado: caixa de texto, forma, grupo, tela de desenho, gráfico, SmartArt, objeto OLE,
tinta, imagem flutuante ou em formato que a tela não mostra (EMF, WMF, SVG, VML,
vinculada) e equação.

- Modelo (`modelo/documento.py`): `ObjetoOpaco` num `Run` (`Run.objeto`, texto U+FFFC,
  como a imagem). Guarda o XML original, as relações da parte hospedeira que ele usa
  (rId de origem, tipo, alvo, externo), o fecho das partes (`ParteOpaca`: nome de origem,
  tipo de conteúdo, bytes, relações próprias e o `relId` do SmartArt que aponta para a
  parte hospedeira), o tipo para a tela, o começo do texto, o tamanho, se é flutuante, a
  prévia (imagem que o Qt lê) e os prefixos do `mc:Ignorable` de origem. Objeto não funde
  com o vizinho e não tem formatação no modelo (o `rPr` vai dentro do XML).
- Leitura (`formato_docx/opacos.py`, `Capturador`): no run, `w:drawing` que não é imagem
  na linha editável, `w:pict`, `w:object` e `mc:AlternateContent` que tenha um deles (o
  AlternateContent vai inteiro, Choice e Fallback); no parágrafo, `m:oMath` e
  `m:oMathPara`. O XML guardado é um `w:r` só com o `rPr` e o objeto, com os namespaces
  da raiz declarados nele (o `mc:Choice Requires="wps"` cita o prefixo em texto). O fecho
  segue os `r:*` e o `o:relid` do XML e as relações de cada parte, com o tipo de conteúdo
  do Override ou do Default. Falha (relação quebrada, parte de tipo proibido, nome que o
  escritor usa, limite) = o objeto não é preservado e vira `OBJETO_PERDIDO` (ou `IMAGEM`),
  com perda. Referência a nota, nota de fim e comentário saem de dentro do objeto, com
  aviso: essas partes não voltam, e a referência ficaria pendurada. O `w:numPr` fica desde
  a 0.1.4 (o `numbering.xml` volta inteiro); só sai, com LISTA_EM_CAIXA, quando a
  numeração do arquivo não pôde ser lida.
- Escrita (`GravadorOpacos`): o XML volta igual, com os `r:*` e `o:relid` trocados pelos
  rIds novos da parte hospedeira; cada parte ganha o nome de origem se livre (senão um
  sufixo), as relações dela (Id mantido, alvo recalculado: o XML da parte não muda) e um
  Override. Parte sem relações e de mesmo conteúdo sai uma vez só. O `relId` do
  `dataModelExt` é a única reescrita dentro de uma parte. Ids que têm de ser únicos no
  documento (`wp:docPr`, `w14:paraId`, `anchorId`) são trocados no objeto que chega
  depois, de forma consistente dentro dele (o Choice e o Fallback repetem o id de
  propósito). As imagens do EditDoc pulam os `docPr` dos objetos. A raiz de cada parte
  declara os namespaces das raízes de origem e o `mc:Ignorable`.
- Apagar o objeto apaga as partes: o escritor só grava as partes dos objetos que estão
  no modelo. Manter parte sem referência seria parte órfã, que o validador recusa e o
  Word repara.
- Validador (`formato_docx/ordem.py`): ordem, `xml:space`, tabela, campo e estilo pulam
  o que está dentro de caixa de texto, AlternateContent, `w:pict`, `w:object` e equação
  (`dentro_de_opacos`): veio do arquivo de origem. `wp:docPr` único e `r:id` com relação
  continuam valendo lá dentro; o `r:id` é conferido também nas partes XML dos objetos
  (gráfico, SmartArt) e no `o:relid` do VML. `wp:extent` pode ter zero na forma (linha
  reta), não na figura.
- Conferência (`formato_docx/conferencia.py`): cada parágrafo leva a `opacos.assinatura`
  de cada objeto: o XML com os rIds trocados pelo conteúdo que apontam (recursivo nas
  partes) e os ids únicos mascarados. Uma parte trocada ou que falta muda a assinatura ou
  faz o objeto não ser lido.
- Conferência da formatação (0.1.16): além da estrutura, a formatação efetiva que muda o
  layout, resolvida dos dois lados com o catálogo de cada um (`_Efetivas`): parágrafo
  (docDefaults fora da tabela, estilo, recuo da lista, direta), trecho de texto caractere a
  caractere e tabela, linha e célula. O arquivo sem `styles.xml` lê o docDefaults do Word
  (`catalogo_sem_estilos`) e o escritor grava o docDefaults do catálogo ao pé da letra.
- Qt (`ponte_qt/opacos.py`): caractere de objeto com `TIPO_OPACO` (UserObject + 2) e a
  chave do registro em `PROP_OPACO`; o objeto fica no registro, como os bytes da imagem,
  para o desfazer achar de novo. O manipulador (`QPyTextObject`, registrado em todo
  `DocumentoQt`) pinta um quadro do tamanho do objeto na linha, ou uma etiqueta na equação,
  com o rótulo e o começo do texto. Desde a 0.1.7 o flutuante é pintado na posição da
  página (ver "Objetos flutuantes"). O HTML que o Qt
  gera não leva o objeto: copiar e colar omite o objeto, e uma marca na área de
  transferência faz o colar avisar na barra de status.

Limites: 2000 objetos por documento, 4 MB de XML por objeto, 64 MB somados, 64 partes e
6 níveis de relação por objeto. Desde a 0.1.5 o texto da caixa de texto se edita (ver
"Formatação preservada, controles de conteúdo, caixas de texto e imagens"); a forma em si
não.

## Partes do pacote, hiperlinks e campos

Implementados na 0.1.3.

- Partes do pacote (`formato_docx/pacote.py`, `PacoteOriginal` no `Documento.pacote`, fora
  da comparação): toda relação do documento que o texto não cita (r:id) e toda relação do
  `_rels/.rels` é classificada. O que o escritor grava (estilos, numeração, tema simples,
  core, app, settings) fica com ele; comentários, macros (vbaProject, personalizações),
  assinatura digital e miniatura não voltam, com aviso (COMENTARIO, MACROS, ASSINATURA,
  MINIATURA); o resto volta byte a byte com o fecho das relações (customXml com itemProps,
  `docProps/custom.xml`, fontTable com as fontes embutidas, webSettings, glossário,
  people.xml...). Cada parte guarda o nome de origem (renomeada só se cair num nome do
  escritor), as relações mantêm o Id e têm o alvo recalculado, e cada parte tem Override.
  Parte com relação quebrada, tipo proibido (documento principal, macros, ActiveX,
  assinatura), XML inválido ou acima dos limites (1000 partes, 6 níveis, 256 MB) não vai,
  com o aviso PARTE_PERDIDA. Parte só referenciada pelo conteúdo (imagem, cabeçalho, link,
  gráfico) que o texto não cita não aparecia no Word e não volta.
- `settings.xml`: o original volta inteiro (compat, rsids, docVars, proteção, mathPr, w14,
  w15), com as relações dele (o modelo anexado, externo). O EditDoc só muda o que controla:
  `w:evenAndOddHeaders`, inserido na ordem do `CT_Settings` (`pacote.ORDEM_SETTINGS`) ou
  tirado; e, se as notas não voltam, as referências `footnotePr/footnote` e
  `endnotePr/endnote` às separadoras. Sem mudança, sai byte a byte. Relação interna do
  settings que não pode voltar: o elemento que a cita sai, com aviso.
- Notas: até a 0.1.9, `footnotes.xml` e `endnotes.xml` voltavam só com as notas separadoras
  (separator, continuationSeparator, continuationNotice), que o settings.xml cita, e as notas
  de verdade saíam com o aviso NOTA. Desde a 0.1.10 o leitor e o escritor as tratam (ver
  "Notas de rodapé e de fim"); esse caminho ficou só para a parte que o leitor não consegue
  ler (acima dos limites, XML que não abre).
- `core.xml` e `app.xml`: os originais voltam com título, autor, criação e modificação
  reescritos (core) e o aplicativo "EditDoc" sem a AppVersion de origem (app). Assunto,
  palavras-chave, categoria, revisão, empresa e gerente ficam.
- Hiperlinks: `Run.link` (`Link`: url, âncora, dica, histórico, quadro, docLocation). O
  leitor aplica o destino do `w:hyperlink` a cada run de dentro (texto, imagem, objeto,
  campo, marca); o escritor junta os runs vizinhos de mesmo destino num `w:hyperlink`, com
  `r:id` para uma relação `TargetMode="External"` do tipo hyperlink na parte (documento,
  cabeçalho ou rodapé), alocada pelo `_Relacoes` (sem colisão com imagens e objetos; o
  mesmo endereço usa uma relação só). No Qt, `setAnchor`/`setAnchorHref` e o `Link` em
  JSON (`ponte_qt/links.py`, `PROP_LINK` = UserProperty + 21); o link sem JSON (HTML
  colado) vem do `anchorHref`. A aparência vem do estilo de caractere "Hyperlink" do
  arquivo; o link inserido recebe esse estilo (criado como latente se faltar).
- Ctrl+clique (`PainelDocumento.abrir_link`): http, https e mailto abrem pelo
  `abrir_url` (QDesktopServices; os testes trocam por um registro); qualquer outro
  esquema (file:, caminho de rede, ftp...) só com o Sim de `confirmar_abrir_link`;
  javascript:, vbscript: e data: nunca. O interno leva o cursor ao marcador.
- Marcadores: `Marcador("inicio"|"fim", nome)` no fluxo (`Run.marca`). O que está entre
  parágrafos entra no começo do parágrafo seguinte. Nome repetido sai com aviso (MARCADOR).
  O escritor numera os ids (únicos no documento). No Qt é um caractere de objeto sem
  largura e sem pintura (`ponte_qt/marcas.py`, `TIPO_MARCADOR`); as setas, o Backspace e o
  Delete passam por ele, para que não seja apagado sem ser visto.
- Campos: `MarcaCampo("inicio", Campo)` e `MarcaCampo("fim")` no fluxo, como o Word faz: o
  resultado é o texto comum entre as duas, editável, e o campo pode começar num parágrafo e
  terminar em outro (o sumário). `Campo.codigo` são os pedaços da instrução: texto
  (`instrText`) ou outro `Campo` (o PAGE de um IF), com o último resultado dele.
  `w:dirty`, `w:fldLock` e os filhos do begin (`w:ffData` do campo de formulário) voltam;
  o campo sem separate (XE, TC) volta sem separate. PAGE e NUMPAGES simples continuam
  `Run.campo` (o valor muda por página na tela). `par` liga o início ao fim do mesmo campo
  (fora da comparação). No Qt cada marca é um caractere de objeto (`TIPO_MARCA_CAMPO`)
  pintado como um colchete fino e cinza, que não sai na impressão nem no PDF
  (`marcas.sem_pintar_marcas`).
- Antes de gravar, `modelo/marcas.equilibrar` deixa as marcas em pares, história por
  história: fim sem início e início sem fim saem (o resultado fica como texto, aviso de
  gravação CAMPO_INCOMPLETO); o marcador sem fim ganha o fim logo depois dele; e o campo
  de página que ficou simples vira `Run.campo` (a mesma regra do leitor). A conferência usa
  a mesma função. O arquivo nunca sai com begin sem end.
- Decisão sobre `w:dirty`: o EditDoc mantém o `w:dirty` que o arquivo tinha e não marca o
  sumário como sujo quando o texto muda. Com `dirty`, o Word pergunta ao abrir se atualiza
  os campos "que podem se referir a outros arquivos", a cada abertura, e o usuário aprende
  a dizer não; a paginação do EditDoc também não é a do Word, então ele não sabe se os
  números mudaram. Atualizar o sumário é o F9 no Word.
- Validador: os campos são conferidos na parte inteira (begin, separate e end na ordem e
  aninhados certo; o código no parágrafo do begin; instrText só no código); marcadores com
  id e nome únicos e cada início com o seu fim; o `r:id` do `w:hyperlink` aponta para
  relação externa do tipo hyperlink. Conferência: o destino de cada trecho de link, as
  marcas (com o código) de cada parágrafo e o conteúdo das partes preservadas.
- Limites: 20.000 campos, links e marcadores por documento; instrução de 4096
  caracteres; endereço de 8192; 8 campos um dentro do outro. Acima disso, texto com aviso.

Até a 0.1.4 o controle de conteúdo (`w:sdt`) era achatado com aviso. Desde a 0.1.5 o de
bloco (o do sumário) e o de parágrafo são preservados com marcas no fluxo; o escritor sobe
o de bloco para fora dos parágrafos (ver a seção da 0.1.5).

## Listas e numeração

Implementadas na 0.1.4.

- Modelo (`modelo/numeracao.py`, sem Qt): `Numeracao` é o catálogo do `numbering.xml`
  (`Documento.numeracao`, fora da comparação, como os estilos): `Abstrata` (os 9 `Nivel`),
  `Instancia` (numId, a abstrata e as `Sobrescrita`, startOverride e/ou `w:lvl`) e
  `ImagemMarcador`. O parágrafo guarda só a referência direta: `Paragrafo.lista` (numId; 0
  desliga a lista do estilo) e `lista_nivel` (ilvl); None herda. O estilo guarda o numPr
  dele (`Estilo.lista`, `lista_nivel`). `lista_efetiva` resolve: o direto, senão o da cadeia
  de estilos; sem ilvl, o do estilo, depois o nível cujo `w:pStyle` é o estilo do
  parágrafo, depois 0. O `w:numStyleLink` leva à abstrata do estilo de numeração.
- Cálculo (`Contador`), como o Word, e o que o oráculo de `tests/teste_listas.py` fixa: os
  contadores são da abstrata (instâncias sem sobrescrita continuam umas das outras, com
  parágrafos comuns no meio); a instância com sobrescrita reinicia o nível na primeira vez
  que aparece, e o nível passa a começar no valor dela; um item no nível L reinicia os
  níveis abaixo (`w:lvlRestart` r: só quando aparece um nível acima de r; 0: nunca); o
  nível não usado desde o último reinício mostra o início menos 1 ("1.0.1"); `w:isLgl`
  mostra os níveis em decimal. O mesmo `Contador` serve a tela, o PDF, a impressão e o `.txt`.
- Arquivo (`formato_docx/numeracao.py`): leitura de tudo, com o XML guardado
  (`xml_original`) e as relações do `numbering.xml` (imagens dos marcadores de figura), cujo
  fecho é capturado como o de um objeto opaco. O que o Word não aceitaria sai na leitura,
  com aviso LISTA: id repetido, `w:num` para abstrata inexistente, `lvlPicBulletId` sem
  `numPicBullet`, marcador de figura com relação quebrada. Os filhos de pPr e rPr dos níveis
  vão para a ordem do esquema (como no `styles.xml`). Escrita: sem acréscimo, os bytes
  originais; com acréscimo, as abstratas novas depois da última abstrata e as instâncias
  novas depois da última instância, o resto do XML como veio. O EditDoc nunca altera uma
  definição do arquivo: reiniciar, continuar, definir valor e trocar o formato criam
  instâncias ou abstratas novas (a mesma abstrata da galeria é reaproveitada).
- Qt (`ponte_qt/listas.py`). Decisão: o número é pintado pelo EditDoc, não pelo QTextList.
  O QTextList conta só a posição do bloco na própria lista (um nível), tem só disco,
  círculo, quadrado e 1/a/A/i/I, e põe o número colado à esquerda do texto. O prefixo e o
  sufixo do `QTextListFormat` (`numberPrefix`) dariam "1.1." só com um QTextList por item e
  o prefixo recalculado a cada mudança, e ainda sem a fonte do símbolo, sem marcador de
  figura, sem o recuo deslocado e sem a tabulação do Word. Assim: o bloco leva o numId e o
  ilvl diretos em propriedades (`PROP_LISTA`, `PROP_LISTA_NIVEL`); o catálogo do arquivo
  fica num atributo do documento e os acréscimos em JSON no quadro raiz (entram no
  desfazer, como os estilos); o `Numerador` do documento recalcula os números só quando a
  estrutura muda (bloco a mais ou a menos, formato de bloco, catálogo), e `desenhar_rotulos`
  pinta na função única da folha. O texto da primeira linha começa onde o Word o põe (o Qt
  só sabe disso pelo `textIndent`): o recuo de verdade fica em `PROP_RECUO_REAL` e o
  `textIndent` recebe o visual (`ajustar_recuos`), que entra no mesmo passo de desfazer da
  edição (`joinPreviousEditBlock`) ou antes de o desfazer ser zerado ao abrir. Quem grava
  um recuo da primeira linha novo tira `PROP_RECUO_REAL`; `props_de_bloco` lê o de verdade.
  O recuo que o nível dá (`w:lvl/w:pPr/w:ind`) fica entre o estilo e o direto
  (`Resolvedor.paragrafo` com a lista), e não vira formatação direta ao salvar.
- Tabulação depois do número (`w:suff` tab): com recuo deslocado e o número antes do recuo
  esquerdo, o texto vai para o recuo esquerdo (ou para uma tabulação do nível antes dele);
  senão, para a próxima tabulação do nível ou a padrão do documento (`w:defaultTabStop`).
  `space`: um espaço; `nothing`: colado.
- Símbolo: a fonte do rPr do nível (Symbol, Wingdings) quando instalada e com o glifo; senão
  o caractere Unicode parecido (`texto_visivel`), que é também o do `.txt`.
- Copiar e colar: o HTML do Qt não leva propriedade de usuário. Copiar põe as listas dos
  blocos (e as definições) em `application/x-editdoc-listas`; colar devolve os blocos às
  listas, importando as definições quando o documento é outro. `<ol>` e `<ul>` de outro
  programa viram lista do EditDoc.
- Medido (offscreen, 3000 itens numerados): digitar 9 ms (sem lista, 7 ms); Enter 50 ms
  (recalcular 15 ms e ajustar os recuos 27 ms). As larguras dos números ficam em cache.

Limites: a definição de uma lista do arquivo não é editada (fonte, recuo ou texto de um
nível); a tabulação depois do número não considera as tabulações próprias do parágrafo
(`w:tabs` do pPr, guardado nos extras desde a 0.1.5, mas fora desse cálculo); o número dentro
de caixa de texto aparece desde a 0.1.5, na caixa editável.

## Formatação preservada, controles de conteúdo, caixas de texto e imagens (0.1.5)

Implementados na 0.1.5.

- Propriedades preservadas (`formato_docx/propriedades.py`): `Run.extras`,
  `Paragrafo.extras`, `Tabela.extras`, `Linha.extras` e `Celula.extras` guardam o XML original
  do que o modelo não representa, um `w:rPr`/`w:pPr`/`w:tblPr`/`w:trPr`/`w:tcPr` em forma
  canônica (c14n, só os namespaces usados). Três classes de filho: representado (o modelo
  tem o campo e o escritor gera igual: `b`, `i`, `strike`, `sz`, `rStyle`, `pStyle`,
  `outlineLvl`, `numPr`), detalhe (o modelo tem o campo mas o elemento traz mais: `u` duplo,
  `dstrike`, `color` com tema, `rFonts` com tema, `vertAlign` estranho, `jc` start, `ind` com
  `leftChars`, `spacing` com entrelinha exata; vai para os extras só se o escritor não o
  geraria igual, e volta enquanto o campo do modelo — ou, com o campo vazio, o estilo —
  der o mesmo valor) e extra (vai inteiro). `szCs` diferente de `sz` fica e o escritor não
  gera o seu. Extensões do Word (`w14`, `w15`, `w16*`) ficam; a raiz da parte as declara e
  as põe no `mc:Ignorable`, e o validador as aceita no document.xml. Revisão de
  formatação saía (REVISAO) até a 0.1.12; desde a 0.1.13 é preservada (ver "Controle de
  alterações"). Filho `w:` fora do esquema sai (FORMATACAO). A marca de parágrafo (`pPr/rPr`) é
  saneada: sem estilo inexistente, na ordem (desde a 0.1.13 o w:ins/w:del dela é lido à parte e o
  w:rPrChange fica).
  Tabela: o escritor continua impondo "Table Grid" e as bordas explícitas (`tblLook` e as
  faixas do estilo não voltam); `gridBefore`/`gridAfter` mudam a grade e continuam com aviso.
- Qt (`ponte_qt/propriedades.py`): PROP_RPR_EXTRA (UserProperty + 28) no caractere,
  PROP_PPR_EXTRA (+ 29) no bloco, e os extras da tabela, linha e célula no JSON que já
  existia. A aparência: fundo (realce, sombreamento), maiúsculas, versalete, espaçamento
  entre letras, escala, tabulações (`setTabPositions`), fundo do bloco e entrelinha exata ou
  mínima; bordas de parágrafo e de trecho e o preenchimento das tabulações são pintados por
  `desenhar`, na mesma função da folha que pinta os números das listas. Medido (Qt 6.11.2,
  1440 dpi): espaçamento entre letras, posição de tabulação e altura fixa de linha são px96
  (× 15). A tabulação do Qt conta da posição da linha, a do Word da margem: desconta-se o
  recuo esquerdo (na primeira linha com recuo próprio fica deslocada). O formato acompanha o
  texto: digitar herda, Enter copia o bloco; copiar leva `application/x-editdoc-propriedades`
  (posições contadas sem os objetos de tipo próprio, que o HTML não leva; se o tamanho colado
  não bate, os trechos não se aplicam); Limpar formatação tira. O recorte de imagem
  (`Imagem.recorte`) vai no nome do recurso (`#recorte=l,t,r,b`) e volta dele.
- Controles de conteúdo: `MarcaConteudo` no fluxo (início com o `sdtPr`/`sdtEndPr`
  canônicos, fim), como os campos. O de bloco tem o início no começo do primeiro parágrafo e
  o fim no fim do último, e o escritor (`_blocos`) abre o `w:sdt` antes do parágrafo e fecha
  depois; o de parágrafo abre e fecha dentro do `w:p` (o link recomeça dentro dele).
  `marcas.equilibrar` deixa os pares na mesma lista de blocos (ou no mesmo parágrafo), bem
  aninhados, normaliza a posição das marcas de bloco e troca o `w:id` repetido; o par
  desfeito conta CONTEUDO_INCOMPLETO. O controle vazio, que começa ou termina numa tabela,
  ou em volta de linha ou célula (`_filhos_w`), continua achatado (CONTEUDO_CONTROLADO).
- Caixa de texto (`formato_docx/caixas.py`): `analisar` lê o `w:txbxContent` de primeiro
  nível do ramo que o Word mostra com o leitor de sempre e decide se é editável: só
  parágrafos, runs de texto, tabulação, quebra de linha, links e formatação; e a trava
  final (regravar e reler na hora tem de dar o mesmo modelo). `regravar` gera o conteúdo
  com o escritor de sempre e troca o de cada `w:txbxContent` de primeiro nível (Choice e
  Fallback), com rIds novos `rIdCx*` para os links e o resumo refeito; o resto do XML fica
  igual. O diálogo (`interface/dialogo_caixa.py`) usa o `PainelDocumento`; confirmar troca o
  formato do caractere da caixa (`formato_de_opaco` com o objeto novo) num bloco de edição.
  Na tela (`ponte_qt/opacos.py`), a caixa editável é composta num `DocumentoQt` próprio a
  1440 dpi (catálogo de estilos e listas do corpo por `_doc_estilos`), do tamanho do
  `wp:extent`, crescendo se o texto passa; texto todo claro ganha fundo escuro. A flutuante,
  desde a 0.1.7, é pintada na posição da página, com o fundo e o contorno da forma.
- Imagens (`ponte_qt/vetoriais.py`): `modelo/imagem.previa_possivel` decide na leitura (sem
  Qt): formato pelo número mágico, tamanho pelo cabeçalho, registros do EMF/WMF percorridos
  até o EOF (tamanho impossível, sem EOF ou acima de 1 milhão de registros: sem prévia),
  dimensões acima do teto da tela, arquivo acima de 16 MB, EMF/WMF fora do Windows. Com
  prévia, a imagem na linha não dá aviso. A tela: TIFF pelo `qtiff`, SVG pelo `QSvgRenderer`
  (sem DOCTYPE, sem referência que não seja `#` ou `data:`), EMF/WMF pelo GDI
  (`EnumEnhMetaFile` + `PlayEnhMetaFileRecord`, parando em registros ou 2 s), duas passadas
  (fundo branco e preto) para a transparência, bitmap no máximo 1800 px. A vinculada a
  arquivo externo nunca é lida.

## Comentários e referências de estilo (0.1.6)

Implementados na 0.1.6.

- Modelo: `MarcaComentario("inicio"|"fim"|"referencia", id)` no fluxo, como as marcas de
  campo; `Documento.comentarios` (`modelo/comentarios.py`, fora da comparação) com os
  `Comentario` (imutáveis: autor, iniciais, `w:date`, conteúdo em parágrafos, pai,
  resolvido, `paraId`, `durableId`, `dateUtc`, o XML de origem e as relações externas dele)
  e os bytes das partes de origem.
- Leitura: o `comments.xml` antes do corpo (o conteúdo pelo leitor de parágrafos, com as
  relações da parte); as partes estendidas por paraId/durableId; âncora só no corpo; o
  comentário sem referência no corpo sai, com COMENTARIO.
- Escrita: sem mudança, os bytes de origem; senão, o XML de origem de cada comentário não
  mudado (rIds dos links remapeados, mantendo o Id quando livre) e o gerado para o resto.
  Partes estendidas: as de origem e, se o catálogo mudou (novo, excluído, resposta,
  resolvido), as três. `comentarios.preparar` (escritor e conferência) dá paraId/durableId
  deterministas a quem não tem e põe o autor novo no `people.xml`, que continua uma parte
  preservada do pacote.
- Qt (`ponte_qt/comentarios.py`): âncoras são marcas sem largura (`TIPO_MARCADOR`, o
  teclado pula); o catálogo vai no quadro raiz (PROP_COMENTARIOS = UserProperty + 30) como
  chaves de um registro, e entra no desfazer; o realce é uma seleção extra da pintura da
  folha, só na tela. `edicao/comentarios.py` tem os comandos e a regra de apagar do Word.
- Referências de estilo: `Estilo.virtual` (referência preservada): o leitor registra o id
  citado sem definição (`Estilos.preservar_referencia`), o escritor grava a referência e não
  a definição, o validador aceita só esses ids (`ordem.validar(..., estilos_preservados)`).
  `ESTILOS_LATENTES_WORD` dá a aparência padrão do Word; `garantir` materializa o virtual
  que o EditDoc passa a usar. Tabela: `Tabela.estilo` e o `tblLook` voltam;
  `Celula.fundo_estilo` (fora da comparação e do JSON) é o fundo condicional da tela.

Limites: até a 0.1.12 "Imprimir marcações" não existia (impressão e PDF sem comentários); desde a
0.1.13 existe (ver "Controle de alterações"). Comentário em
cabeçalho, rodapé ou caixa de texto não é preservado; copiar e colar texto comentado não
leva o comentário; da formatação condicional de tabela, só o fundo aparece na tela.

## Objetos flutuantes (0.1.7)

Até a 0.1.6 o objeto flutuante aparecia como etiqueta (ou caixa) no ponto da âncora, dentro
do texto: numa capa, o título da caixa de texto virava um bloco no meio do texto e as
imagens viravam "Imagem flutuante". O arquivo já saía certo; só a aparência mudou.

- Posição (`modelo/flutuantes.py`, sem Qt): `Ancoragem` (relativeFrom, posOffset ou
  align, `wp14:pctPosHOffset`, extent, `wp14:sizeRelH/V`, simplePos, effectExtent, quebra
  e lado, distâncias, behindDoc, relativeHeight, layoutInCell) e `retangulo(ancoragem,
  Referencia)`, em twips da folha. A `Referencia` diz onde a âncora ficou: página (a página
  0 é ímpar, para inside/outside), topo do parágrafo, topo da linha, coluna (ou a célula) e
  x do caractere. `area_de_quebra` soma effectExtent e distâncias.
- Leitura (`formato_docx/flutuantes.py`, sem Qt): do XML do objeto opaco (nada muda nele).
  No AlternateContent vale o Choice; o VML só sem DrawingML (style `position:absolute`,
  `margin-left/top`, `mso-position-*`, `mso-width-percent`, `z-index` negativo = atrás,
  `w10:wrap`). A `Figura`: imagem (rId e `a:srcRect`), forma (prstGeom, preenchimento e
  contorno, inclusive pela referência `wps:style` e pelo tema), caixa (margens do
  `bodyPr`, `anchor`, `wrap`, cor do `fontRef`), grupo (filhos pela `chOff/chExt`), resto
  (gráfico, SmartArt, tela de desenho) com rótulo. Cores com lumMod, lumOff, shade, tint e
  alpha; tema do `theme1.xml` do arquivo (o padrão do Office no que faltar).
- Quebra de texto: decidida pelo spike (docs/SPIKES.md, "0.1.7"). O layout do Qt
  (`QTextDocumentLayout`) contorna "floats" linha a linha: um caractere de objeto cujo
  formato tem `ObjectIndex` de um `QTextFrame` com posição FloatLeft/FloatRight vira um
  retângulo que as linhas seguintes evitam (o mesmo de `QTextCursor.insertImage(formato,
  FloatLeft)`). O objeto com wrapSquare, wrapTight, wrapThrough ou wrapTopAndBottom (e sem
  behindDoc) entra assim no documento ao abrir (`flutuantes.inserir_com_reserva`); o lado
  do frame é decidido com a página do arquivo. O tamanho do float é o `intrinsicSize`,
  calculado no meio do layout pela posição que o Qt já deu ao bloco (`Gerente.plano`): do
  topo da linha da âncora até o pé do objeto (cortado no pé da página), e da borda do corpo
  até o lado de dentro do objeto. Os objetos de um mesmo parágrafo viram no máximo dois
  floats (um de cada lado); se os lados se encontram, ou o objeto é wrapTopAndBottom, o
  primeiro leva a largura toda e o texto passa para baixo. wrapNone e behindDoc entram como
  caractere sem tamanho. O caractere do float não é apagado pelo `deleteChar` do Qt (o
  cursor recusa caractere com ObjectIndex): o painel apaga por seleção.
- Conferência (`Gerente.atualizar`, na pintura e antes de imprimir): o Qt só refaz os
  blocos da faixa editada e desloca os de baixo com as linhas e o float de antes. Depois de
  cada mudança, a reserva de cada objeto e a largura das linhas perto dele (por posição no
  documento, `_alcance`) são conferidas, e o que ficou velho é refeito com
  `markContentsDirty` (fora do desfazer). Os objetos são seguidos por `QTextCursor` (sem
  varrer o documento a cada tecla). Apagar o objeto deixa o frame órfão com o retângulo
  antigo na lista de floats do Qt; `Gerente.curar` desfaz e refaz a última ação com as
  reservas zeradas (o frame fica órfão de tamanho zero). O documento, a pilha de desfazer e
  o "alterado" ficam como estavam; refazer e desfazer depois disso já não precisam de cura
  (o Qt destrói o frame quando o caractere sai sem pai, dentro do grupo de desfazer).
- Pintura (`ponte_qt/flutuantes.pintar`): a mesma na tela, no PDF e na impressão. O
  `desenhar_folha` pinta os objetos da página atrás do texto, depois o corpo, depois os da
  frente, recortados na folha inteira (o objeto pode estar na margem). Cabeçalho e rodapé:
  `desenhar_faixas(parte=...)`; a impressão pinta os objetos das faixas, o corpo e só então
  o texto das faixas (o objeto do cabeçalho fica atrás do texto do corpo, como no Word). Na
  tela, com objeto em cabeçalho ou rodapé, os tiles ficam transparentes e os objetos das
  faixas são pintados antes deles. Um objeto que muda de lugar limpa o cache de tiles.
  Desde a 0.1.8 a tela pinta cada objeto uma vez num QPixmap alinhado ao pixel do
  dispositivo (`_pintar_na_tela`, chave com o objeto, o tamanho, a escala e a fração de pixel)
  e o copia nos tiles; o PDF e a impressão pintam de verdade.
- Conferência que não converge (0.1.8): a linha que não cabe no pé da página ao lado de um
  float desce para a página seguinte com a largura estreita (medido no Qt 6.11.2), e
  `markContentsDirty` não a refaz. Quando uma rodada de conferência acha as mesmas faixas da
  anterior, as linhas são aceitas como estão (`_aceitas`, pela assinatura das linhas do
  bloco) e só voltam a ser conferidas se mudarem. Antes, cada tecla refazia isso 6 vezes e
  conferia até o fim do documento.
- Blocos refeitos que voltam iguais (0.1.11): digitar antes das âncoras de uma capa que
  reserva a folha inteira põe o float na página seguinte; o Qt desloca os blocos de baixo
  com o float de antes e a conferência os refaz, a cada tecla, para o mesmo lugar de antes.
  As faixas encostadas viram uma chamada só de `markContentsDirty` (`_juntar`), e
  `Gerente.refeito_igual` diz que os blocos refeitos têm as mesmas linhas e o mesmo texto do
  fim da conferência anterior, com a mesma altura do documento: a vista não tira nada do
  cache. Limpar o cache da vista zera essa comparação (`esquecer_refeitos`).
- Interação: clique no objeto seleciona (contorno com alças); o de trás só fora do texto.
  Delete e Backspace apagam, com desfazer; duplo clique na caixa abre o editor da 0.1.5.

Limites: o texto contorna de um lado só (o maior, ou o do `wrapText`); a faixa começa na
linha da âncora (o texto acima dela não contorna, nem o de páginas anteriores);
Tight/Through seguem o retângulo; objetos de um parágrafo somam as faixas por lado (a
altura é a do mais baixo); objeto em célula de tabela não reserva espaço (mover e
redimensionar, e a seleção do objeto do cabeçalho, desde a 0.1.9); geometria
fora do conjunto básico vira retângulo; `custGeom` não é seguido; a rotação e o espelho
valem, mas a área de quebra é a do retângulo sem rotação.

## Mover e redimensionar objetos (0.1.9)

O objeto continua opaco (o XML guardado volta igual); mover, redimensionar e trocar a quebra
mudam só os elementos e atributos de posição e tamanho dentro dele.

- XML (`formato_docx/posicao.py`, sem Qt): `Mudanca` (posição por referência, simplePos,
  tamanho, quebra, relativeHeight) e `aplicar(xml, mudanca)`. DrawingML: `wp:positionH/V` com
  um `wp:posOffset` no mesmo `relativeFrom` (o `wp:align` e o `wp14:pctPos*Offset` viram
  posOffset, como o Word); `wp:extent` e o `a:ext` do desenho de cima (`pic:spPr`,
  `wps:spPr`, `wpg:grpSpPr` com `chOff/chExt` intactos); o tamanho relativo vira absoluto.
  Quebra: o `wp:wrap*` (Comprimido e Através com o `wp:wrapPolygon` retangular que o esquema
  exige) e o `behindDoc`; Alinhado ao texto converte `wp:anchor` em `wp:inline` (CT_Inline:
  extent, effectExtent, docPr, cNvGraphicFramePr, graphic) e de volta (CT_Anchor com
  distâncias, simplePos, relativeHeight único no documento, behindDoc, locked, layoutInCell,
  allowOverlap). VML (o objeto só VML e o `mc:Fallback`): os itens do `style` e o `w10:wrap`,
  os outros itens na ordem e com o texto de origem. `estado(xml)` diz como o objeto está.
- Conta (`modelo/flutuantes.py`): `deslocamento_para(eixo, rel, ref, valor)` é o caminho de
  volta de `retangulo` (o ponto da folha em posOffset relativo à referência); limites de
  posição (±55,88 cm, o que o Word aceita; ST_PositionOffset é xsd:int) e de tamanho (1 px96 a
  176 cm; ST_PositiveCoordinate não negativo; o lado zero da linha reta continua zero).
- Edição (`edicao/objetos.py`): a troca do objeto no caractere é um passo de desfazer. Se o
  caractere continua do mesmo tipo (float do Qt do mesmo lado, ou sem reserva), muda só o
  formato (`setCharFormat` com o ObjectIndex de antes); se muda (quebra que passa a reservar,
  lado do float, linha <-> flutuante), o caractere sai e entra de novo pelo caminho de
  sempre (`opacos.inserir`), e a cura do frame órfão da 0.1.7 zera o float que saiu.
  Reancorar (arraste para outra página, ou objeto relativo ao parágrafo levado a outro
  parágrafo) põe o caractere no começo do parágrafo mais perto do topo novo, em duas etapas
  no mesmo passo de desfazer: com a posição do layout de antes e, refeito o layout, com a de
  agora (`joinPreviousEditBlock`). Não reancora com a âncora travada, no cabeçalho e no
  rodapé, em tabela ou no bloco estrutural: a posição passa a ser relativa à página da âncora.
- A imagem do EditDoc (`Imagem`, na linha) que passa a flutuar vira objeto com o desenho que
  o escritor grava (`posicao.objeto_de_imagem`); a figura simples que volta para a linha
  vira `Imagem` de novo (`imagem_de_objeto`), porque é o que o leitor faz de um `wp:inline`
  com PNG, JPEG, GIF ou BMP, e a conferência pós-gravação compara isso. A figura girada,
  espelhada, com borda ou efeito não volta para a linha (recusa com o motivo).
- Tela (`interface/painel_documento.py`): oito alças (cantos e meio dos lados); arrastar o
  corpo move e as alças redimensionam, com um contorno fantasma (`_retangulo_fantasma`,
  pintado por cima, um retângulo por quadro: o objeto e o texto só mudam ao soltar). Shift
  trava a proporção (os cantos da imagem já travam) e trava o eixo ao mover. Setas: 1 px de
  tela; Ctrl+setas: um quarto de px; Esc tira a seleção. Objeto preservado na linha (caixa,
  forma) tem as alças da imagem (`LayoutPaginado.retangulo_imagem`). Na edição do
  cabeçalho e do rodapé, `flutuante_das_faixas_em` acha o objeto das faixas da página (o de
  trás só fora do texto) e tudo vale no documento da faixa. Galeria "Quebra de texto" e
  "Posição" na aba Layout (grupo Organizar) e no menu de contexto; o diálogo
  (`interface/dialogo_posicao.py`) devolve só o que mudou.
- Validador (`posicao.problemas`, chamado por `ordem.validar_estrutura`): atributos do
  `wp:anchor`, a quebra, `positionH/V`, posOffset inteiro de 32 bits e extent não negativo.

## Notas de rodapé e de fim (0.1.10)

Até a 0.1.9 a referência saía do texto e a nota do arquivo (aviso NOTA, com perda); só as
separadoras voltavam.

- Modelo: a referência é uma marca no fluxo (`MarcaNota(tipo, id)`, com `personalizada` e o
  `simbolo` do `w:customMarkFollows`), como as âncoras de comentário; o número da própria nota
  (`w:footnoteRef`) é a mesma marca com `propria`. O conteúdo fica no catálogo `Documento.notas`
  (`modelo/notas.py`, fora da comparação): `Nota` (tipo, id, parágrafos, o XML de origem e as
  relações que ele cita, com os bytes das imagens), as separadoras (`Especial`, XML de origem),
  os bytes de cada parte, as relações dela e as propriedades (`PropriedadesNota`: numFmt,
  numStart, numRestart, pos; a do sectPr vence a do settings.xml, que vence o padrão do Word).
  `numeros` calcula o número de cada referência (contínuo ou por página, no formato do
  numFmt; a marca personalizada não conta).
- Leitura (`formato_docx/leitor.py`, `_ler_notas`): as partes antes do corpo (as referências
  citam os ids); o conteúdo pelo leitor de parágrafos, com as relações da parte; referência só
  no corpo, uma por nota; a nota sem referência sai, com NOTA. O símbolo da marca personalizada
  é o run seguinte, guardado em forma canônica (`propriedades.canonico`). Limites: 5000 notas
  por tipo, 1 MB por nota, 32 MB por parte, 2000 parágrafos por nota; acima disso a parte não é
  lida e o pacote preserva só as separadoras (o caminho da 0.1.3), e o EditDoc não cria nota
  daquele tipo (`ed_notas.pode_inserir`).
- Escrita: `notas.preparar` (escritor e conferência) deixa só as notas com referência, na
  ordem do texto, e dá id novo à referência repetida. A parte sem mudança volta com os bytes de
  origem (as relações mantêm o Id; a imagem vai para a mídia do escritor, só o alvo muda); com
  mudança, a raiz de origem com as separadoras, o XML de origem das notas que não mudaram e o
  conteúdo gerado das outras. O documento que ganha a primeira nota ganha as separadoras do
  Word, e o settings.xml passa a citá-las (`pacote._citar_especiais`, ou o settings gerado). O
  footnotePr/endnotePr do sectPr volta como veio enquanto as propriedades não mudam. Ids de
  marcador e de `wp:docPr` das notas de origem ficam reservados para o que o escritor gera.
- Validador (`formato_docx/notas.py`): toda referência cita uma nota normal que existe, uma
  vez; toda nota normal tem referência; ids numéricos e únicos; o settings.xml só cita
  especiais que existem; `w:footnoteRef` só na nota; nenhuma referência dentro de nota,
  cabeçalho ou rodapé. A ordem, o `xml:space`, os campos, os marcadores, as tabelas e os estilos
  valem nas partes de notas como no corpo.
- Conferência: as marcas de cada parágrafo (com as referências) e, de cada nota, o tipo, o id e
  o conteúdo; e as propriedades efetivas.
- Qt (`ponte_qt/notas.py`): a marca é o caractere de objeto `TIPO_NOTA` (UserObject + 5) com a
  `MarcaNota` em JSON (`PROP_NOTA` = UserProperty + 31); o manipulador pinta o número
  sobrescrito, que sai do mapa do documento (`_numeros_notas`) ou, na nota, do número dela. O
  catálogo vai no quadro raiz (`PROP_NOTAS` = + 32), como o dos comentários: chaves de um
  registro de `Nota` imutáveis e as propriedades, no desfazer.

### Paginação com notas

Decidida por um spike (docs/SPIKES.md, "0.1.10"). O `QTextDocument` do corpo pagina com um
tamanho só; a área de notas tem de encolher o corpo só na página da referência. O que não é
conteúdo e mexe no layout do Qt não existe (o `intrinsicSize` dos objetos só muda a linha
deles; o float do Qt começa na linha da âncora, não no pé da página; a margem do quadro raiz
vale em todas as páginas). O caminho escolhido é um **espaçador no fluxo**: o primeiro bloco
que não cabe acima da área de notas recebe a quebra de página do Qt com uma marca
(`PROP_QUEBRA_NOTA` = UserProperty + 33) e começa na página seguinte. A marca não é quebra do
usuário: não volta ao arquivo (`de_qt`), não aparece como "Quebra de página", sai no Enter e no
copiar (`_html_sem_espacador`).

- `interface/notas.py`, `ConjuntoDeNotas.atualizar` (na pintura, antes de imprimir e ao abrir):
  página a página, a linha que não cabe com as notas das referências até ela (as anteriores
  inteiras, as da própria linha ao menos com a primeira linha) empurra o bloco (ou a tabela)
  dela; a primeira unidade da página nunca é empurrada; o bloco empurrado volta quando, no
  lugar dele (simulado com as alturas das linhas dele), tudo o que ficaria na página caberia.
  Depois, a distribuição: continuação primeiro (separador da largura toda), separador curto
  (2 polegadas, como o Word), notas inteiras ou cortadas numa linha; o que não cabe continua na
  página seguinte; notas de fim depois do texto; páginas a mais (`extras`) depois da última,
  que `LayoutPaginado.numero_paginas` conta. A distribuição nunca põe nota em cima do texto: o
  espaço é o que sobra abaixo da última linha da página.
- Só o que mudou: a conferência começa na página antes da edição e para quando uma página
  fica igual à do plano anterior (linhas, notas, continuação); as marcas são seguidas pelo
  `contentsChange` (sem varrer o documento a cada tecla).
- Desfazer: o espaçador é formato de bloco e entra no desfazer. O ajuste depois de uma edição
  do usuário é um passo próprio, anotado (`passos`); `PainelDocumento.undo/redo` passam por ele
  junto com o passo do usuário (`ConjuntoDeNotas.desfazer/refazer`), e o estado de antes já
  estava ajustado. A edição de uma nota no lugar é uma sessão: o primeiro toque cria um passo
  no corpo (o catálogo com uma chave provisória), os ajustes da sessão e o conteúdo final
  entram nele; dentro da nota, Ctrl+Z desfaz as teclas da nota (o documento dela).
- Tela, PDF e impressão: `desenhar_notas` pinta a área de cada folha (separadores e trechos dos
  documentos das notas, recortados), a mesma função nos três; na tela por cima dos tiles. Clique
  na área edita a nota (`PainelDocumento.entrar_na_nota`, `document()` passa a ser o da nota).

Limites: o bloco inteiro desce (o Word parte o parágrafo e leva só as linhas que não cabem),
então sobra branco no pé da página com parágrafo longo; tabela que começou na página anterior
não é empurrada (a nota continua na seguinte); as notas depois de uma que continua esperam a
continuação; formatos de número fora de decimal, letras, romanos e chicago aparecem em decimal;
"fim da seção" é o fim do documento; o aviso de continuação do Word não aparece; objeto
flutuante perto do pé não contorna a área de notas; desfazer no corpo depois de editar uma nota
cujo ajuste caiu fora da sessão pode perder o refazer (o ajuste novo trunca a pilha).

## Seções (0.1.12)

Até a 0.1.11 só a última seção valia: os `w:sectPr` dos parágrafos eram achatados, com os avisos
SECAO, PAGINA e CABECALHO_SECAO (perda).

- Modelo (`modelo/secoes.py`): `Secao` (página, tipo `w:type`, os cabeçalhos e rodapés que ela
  declara, `extras`, `original`, `chaves`). A seção que termina num parágrafo é
  `Paragrafo.secao`; a última são os campos de sempre do `Documento` (`pagina`, `cabecalhos`,
  `rodapes`) mais `Documento.secao` (tipo, extras, XML de origem). `secoes_de(doc)` dá a lista;
  `faixa_efetiva` faz a herança do Word (a seção que não declara um tipo usa o da anterior).
  `historias_de_faixa` (modelo/documento.py) junta os cabeçalhos de todas as seções para quem
  percorre as histórias (marcas, listas, notas).
- Arquivo (`formato_docx/secoes.py`): `ler` representa as referências, `w:type`, `w:pgSz`
  (w, h, orient), `w:pgMar`, `w:titlePg` e o `w:pgNumType` (formato que o EditDoc desenha, início
  válido); o resto (colunas, numeração de linhas, vAlign, bordas de página, grade, proteção,
  direção, bidi, rtlGutter, paperSrc, printerSettings, o footnotePr das seções do meio,
  chapStyle, o `w:code` do papel, os rsids) fica em `extras` (c14n) e volta igual. `escrever`
  parte do `original` (a ordem e os atributos que o arquivo tinha) e só troca o que o modelo
  mudou, com os atributos na ordem do Word; sem mudança, a forma canônica sai igual (conferido
  nos `.docx` reais). As referências de cabeçalho entram depois que as partes são gravadas; duas
  seções que citavam a mesma parte com o mesmo conteúdo continuam citando uma parte só (a
  chave). Revisão (`w:sectPrChange`): saía com REVISAO; desde a 0.1.13 fica nos extras e volta.
  Filho fora do esquema sai com FORMATACAO.
  Limites contra arquivo hostil: 2000 quebras de seção (as que passam se juntam à seguinte,
  aviso SECAO) e 45 colunas. Formato de número que a tela não desenha passou a ser preservado
  (NUMERO_PAGINA sem perda). O leitor lê o `w:sectPr` do parágrafo só no corpo e fora de tabela
  (SECAO no resto), e os cabeçalhos de cada seção depois do corpo (cada parte uma vez só).
- Validador e conferência: `secoes.validar` (o `w:sectPr` é o último filho do `w:body` ou do
  `w:pPr` de um parágrafo do corpo, as referências têm tipo válido, um por tipo, e resolvem para
  uma parte de cabeçalho/rodapé; limites); a conferência compara onde cada seção termina, a
  página, o tipo, os extras e os cabeçalhos que cada uma declara.
- Qt (`ponte_qt/secoes.py`): a quebra de seção é um caractere de objeto (`TIPO_QUEBRA` =
  UserObject + 6, o JSON em `PROP_QUEBRA` = UserProperty + 35) no FIM do último parágrafo da
  seção, com o id da seção num registro do documento (fora do desfazer). Como no Word, ele É a
  marca do parágrafo: Backspace no começo do parágrafo seguinte, ou Delete antes dele, apagam a
  quebra e fundem os dois parágrafos; o texto de cima passa à seção de baixo, que continua com
  as propriedades dela; o caret nunca fica depois dele. O desfazer é o do texto. Inserir a
  quebra (Layout > Quebras) cria uma seção (cópia da do cursor, com os mesmos cabeçalhos) para a
  parte de cima e muda o tipo da de baixo trocando o id do caractere dela (ou, na última, o id
  no quadro raiz, `PROP_SECAO_FINAL` = + 38): as duas trocas entram no passo de desfazer. A
  quebra de coluna é o mesmo objeto, sem largura. Papel, orientação e margens de uma seção
  mudam o registro (fora do desfazer, como a página da 0.1.11).
- Cabeçalhos (`interface/cabecalhos.py`): cada variante tem um id; as seções apontam para os ids
  que declaram (`Secao.chaves`). A mesma variante pode valer em várias seções (editar uma edita
  a outra, como o "Vincular ao anterior" do Word) e é medida e pintada com a largura do corpo da
  seção da folha. Vincular ao anterior tira a declaração da seção (com confirmação se ela tem
  texto); desvincular copia a da anterior.

### Paginação por seção

Decidida pelo spike da 0.1.12 (docs/SPIKES.md). O `QTextDocument` pagina com um `pageSize` só,
e nem a margem de um `QTextFrame` filho nem a de uma tabela valem por página (medido: só a do
quadro raiz, igual em todas). Um quadro por seção daria a largura, mas a seleção do Qt que
atravessa um quadro pega o quadro inteiro, e mover texto entre quadros (apagar a quebra entre
seções de papéis diferentes) seria copiar fragmento com objetos. Escolhido, com o menor risco: o
documento continua um só (cursor, seleção, desfazer e localizar atravessam as seções como
antes) e (`interface/secoes.py`):

- a página n do documento continua sendo a faixa [n*H, (n+1)*H), com H a maior altura de corpo
  entre as seções e a largura do documento a maior largura;
- a seção mais estreita ganha, em cada parágrafo e tabela do primeiro nível, um recuo direito
  escondido (`PROP_RECUO_SECAO` = + 37, "extra;total"): o texto reflui na largura dela. O recuo
  do usuário é o total menos o extra enquanto o recuo do bloco continua o total aplicado
  (`estilos.recuo_direito_real`); quem troca o recuo (formatação, estilo, régua) grava um valor
  novo, que passa a ser do usuário, e o extra volta na conferência seguinte. O `de_qt`, a faixa e
  o copiar não veem o extra;
- a seção mais baixa usa o espaçador das notas (`interface/notas.py`, o corpo da página termina
  em `n*H + altura da seção`): o bloco que não cabe desce inteiro; a tabela que não pode descer
  inteira desce a partir da linha que não cabe, com acolchoamento de baixo na linha de cima
  (`PROP_LINHA_EMPURRADA` = + 39 na célula), e a pintura fecha a linha de cima onde o texto dela
  acaba (`fechar_linhas_empurradas`);
- a quebra entre seções é a quebra de página do Qt, derivada (`PROP_QUEBRA_SECAO` = + 36):
  `PageBreak_AlwaysAfter` no parágrafo da quebra quando a seção seguinte começa em página nova
  (nextPage, evenPage, oddPage, nextColumn e a contínua com outro papel); a página em branco de
  evenPage/oddPage é mais uma quebra, antes da unidade seguinte (medido: as duas seguidas deixam
  uma página vazia). Ela segue a numeração que continua; com reinício, o número que a página
  teria sem ele;
- cada folha sabe a sua seção (`ConjuntoDeSecoes.secao_da_folha`, pelo topo da primeira unidade
  de cada seção; a contínua que começa no meio da folha deixa a folha para a anterior): papel,
  margens, topo e altura do corpo (`efetiva_da`), cabeçalhos com a herança (`faixa_da_folha`),
  PAGE com o número da seção (reinício e formato), SECTIONPAGES e NUMPAGES
  (`campos_da_folha`). O mapa da tela (`modelo/folhas.Mapa`, `folhas`) põe folhas de tamanhos
  diferentes uma embaixo da outra, cada uma centrada; o PDF e a impressão trocam de papel na
  folha; a régua usa a seção do cursor; os objetos flutuantes, a página e a margem da seção da
  folha (`flutuantes.Contexto.folhas`); as notas, a altura da seção.

Os formatos derivados entram no desfazer como o espaçador das notas: um passo anotado depois do
passo do usuário (`ConjuntoDeNotas.ajustar`). A conferência só olha o trecho editado, a não ser
que a estrutura mude. Documento de uma seção só: nada disso roda.

Limites: colunas são preservadas e mostradas em uma coluna (aviso COLUNAS, sem perda; o spike
da 0.1.14 em docs/SPIKES.md mostra o caminho e por que ficou para depois); o
parágrafo que não cabe numa seção mais baixa desce inteiro; o objeto flutuante à direita numa
seção mais estreita fica na largura do documento; a altura do corpo de uma seção é a da sua
variante de cabeçalho mais alta (como na 0.1.8); a área de notas usa a largura da seção mais
estreita; copiar e colar não leva a quebra de seção; desfazer não desfaz a troca de papel e
margens nem o "Vincular ao anterior".

## Controle de alterações (0.1.13)

Até a 0.1.12 as revisões eram aceitas ao abrir (aviso REVISAO, com perda): o inserido ficava como
texto comum e o excluído sumia ao salvar.

- Modelo (`modelo/documento.py`, `modelo/revisoes.py`): `Revisao` (tipo `ins`/`del`/`moveFrom`/
  `moveTo`, autor, `w:date`, `w16du:dateUtc`; o `w:id` lido fica fora da comparação). No run,
  `insercao` (w:ins ou w:moveTo) e `exclusao` (w:del ou w:moveFrom): o mesmo trecho pode ter as
  duas (inserido por um autor e apagado por outro); `mudanca_formato` é o `w:rPrChange` canônico
  sem o `w:id`. No parágrafo, `marca_insercao`/`marca_exclusao` (o w:ins/w:del do rPr do pPr),
  `mudanca_formato` (w:pPrChange) e `mudanca_numeracao` (w:numberingChange e w:ins do numPr). As
  pontas de um movimento são marcas no fluxo (`MarcaMovimento`, como os marcadores). Tabela:
  `mudanca_grade` (w:tblGridChange); as revisões de tabela, linha e célula (w:tblPrChange,
  w:trPrChange, w:tcPrChange, w:ins/w:del do trPr, w:cellIns/w:cellDel/w:cellMerge) ficam nos
  extras da 0.1.5, e o w:sectPrChange nos extras da seção da 0.1.12, todos sem o `w:id`.
  `Documento.controlar_alteracoes` é o `w:trackRevisions` do settings.xml.
- Arquivo (`formato_docx/revisoes.py`): o leitor põe a revisão dos `w:ins`/`w:del`/`w:moveFrom`/
  `w:moveTo` em cada run de dentro (texto, imagem, objeto, campo, referência de nota e de
  comentário); `w:delText` e `w:delInstrText` só valem dentro de `w:del`. O escritor agrupa os
  runs vizinhos de mesma revisão: `w:ins` (ou `w:moveTo`) por fora, `w:del` (ou `w:moveFrom`)
  por dentro, como o Word; dentro de `w:del` o texto é `w:delText` e o código de campo
  `w:delInstrText`; marcador, âncora de comentário, controle de conteúdo e as pontas de movimento
  fecham o elemento e saem por fora. O `w:rPrChange` é o último filho do rPr; a marca do parágrafo
  é o começo do rPr do pPr; o `w:pPrChange` é o último filho do pPr. Revisões em cabeçalho, rodapé,
  nota e comentário passam pelo mesmo leitor e escritor; a caixa de texto com revisão continua só
  leitura (objeto preservado, volta igual). Acima dos limites (`LIMITES`: 100 mil revisões, 500
  autores, nome de 255 caracteres, data de 64), ou com data absurda, o comportamento antigo, com
  REVISAO. As revisões dentro de um estilo continuam saindo com FORMATACAO.
- `w:id` (decisão): o esquema pede id único entre as anotações do mesmo tipo, e o Word numera
  comentários e revisões numa sequência só. Sem documento real com revisões para conferir, ficou
  a escolha mais restrita: o escritor numera as revisões no fim de cada parte
  (`revisoes.Numerador`, com as pontas do movimento ligadas por um atributo provisório) sem
  repetir NENHUM número que já existe: os dos comentários, os dos marcadores (numerados de 0 em
  diante) e todos os `w:id` do XML que volta como veio (comentários e notas que não mudaram,
  objetos preservados). O validador (`revisoes.validar`, chamado pelo `ordem.validar`) confere:
  id único entre todas as revisões das partes de texto e diferente dos de comentário e marcador
  (os ids do XML preservado podem se repetir como vieram), `w:t`/`w:instrText` nunca dentro de
  `w:del` e `w:delText`/`w:delInstrText` só dentro, cada moveFromRangeStart com o seu fim e um
  moveToRangeStart do mesmo nome. A conferência compara, por parágrafo, as revisões de cada trecho
  e as da marca e das propriedades.
- Qt (`ponte_qt/revisoes.py`): no caractere `PROP_REV_INS` (UserProperty + 40), `PROP_REV_DEL`
  (+ 41) e `PROP_REV_RPR` (+ 42); no bloco `PROP_REV_MARCA` (+ 43) e `PROP_REV_PPR` (+ 44). O texto
  excluído continua no documento, como no Word. As linhas e células revisadas, no JSON que já
  existia; a seção, no registro (aceitar troca a seção do caractere ou a final, no desfazer).
- Modos de exibição (decididos por spike, docs/SPIKES.md "0.1.13"): um `QSyntaxHighlighter` por
  documento (`RealceRevisoes`, criado quando a primeira revisão aparece) aplica formatos
  adicionais do layout, que não entram no desfazer nem no "alterado". "Toda a marcação": inserido
  sublinhado e excluído tachado na cor do autor, movido em verde (a segunda linha pintada por
  `desenhar`), barra cinza na margem esquerda; "Marcação simples": o texto final, barra vermelha;
  "Sem marcação": o final; "Original": o texto de antes, com a formatação de antes do
  `w:rPrChange`. Texto escondido: fonte de 0,01 pt, transparente (largura zero no layout de 1440
  dpi); parágrafo sem nada visível e com a marca escondida: `QTextBlock.setVisible(False)`. O modo
  vale para a janela (corpo, cabeçalhos e notas). O caret pula o texto escondido como pula as
  marcas sem largura.
- Edição (`edicao/revisoes.py`, chamada pelo `PainelDocumento` e pelos comandos): Revisão >
  Controlar alterações (Ctrl+Shift+E). Ligado: digitar e colar criam inserção do autor das Opções
  (o mesmo dos comentários, 0.1.6); apagar texto alheio (ou comum) marca a exclusão, apagar o
  próprio texto ainda não aceito remove; o Enter deixa a marca nova (inserida) no parágrafo de
  cima; formatar guarda a formatação de antes, uma vez (a primeira é a que vale), sem marcar o
  texto que o próprio autor inseriu; substituir é exclusão mais inserção. Desligado: o texto novo
  não herda a revisão do vizinho e o Enter no meio de uma marca inserida deixa a marca nova sem
  revisão. Aceitar e rejeitar: a atual (ou as da seleção), todas, todas de um autor; Anterior e
  Próxima; menu de contexto; painel lateral. Tudo num passo de desfazer.
- Painel (`interface/painel_revisoes.py`, `interface/revisoes_janela.py`): o painel lateral dos
  comentários virou "Comentários e revisões", com duas abas; a lista mostra tipo, autor, data e o
  começo do trecho; escolher uma linha seleciona o trecho; Aceitar e Rejeitar valem para ela.
- Saídas: copiar leva o texto como se lê (em "Toda a marcação", o final, como o Word); localizar
  não acha o que está escondido no modo; a contagem de palavras usa o texto do modo (o final em
  "Toda a marcação"); o `.txt` sempre o final. Impressão e PDF seguem o modo da tela com
  "Imprimir marcações" ligado (o padrão, como no Word), que também imprime o realce dos trechos
  comentados e o texto dos comentários na margem direita; desligado, o texto final, sem
  comentários.

Desde a 0.1.14 (`edicao/revisoes.py`, `formato_docx/revisoes.py`):

- Rejeitar devolve o estado de antes guardado no elemento de mudança: o `w:tblPr` do
  `w:tblPrChange` e a grade do `w:tblGridChange` (relidos pelo leitor numa tabela de mentira:
  largura, alinhamento, recuo, margens, layout, estilo e extras; das bordas, só os lados que o
  `w:tblBorders` de antes declara), o `w:trPr` do `w:trPrChange` (cabeçalho na beirada do
  `headerRowCount`, altura, extras, com as marcas de linha inserida/excluída de agora), o `w:tcPr`
  do `w:tcPrChange` (sombreamento, alinhamento vertical, bordas, extras, com as marcas de célula de
  agora; se a mescla de antes era outra, fica), o `w:sectPr` do `w:sectPrChange` (relido por
  `secoes.ler`, com os cabeçalhos de agora; o papel e as margens da última seção vão para o layout,
  fora do desfazer, como na 0.1.12) e a numeração inserida (`w:ins` no `w:numPr`: o parágrafo
  volta a não ter numeração direta). As linhas com `w:trPrChange` entram na lista ("Propriedades
  da linha").
- Célula inserida (rejeitar) ou excluída (aceitar): sai quando a coluna inteira (`removeColumns`)
  ou a linha inteira tem a mesma marca; a célula sozinha fica (a grade do Qt não fica torta).
- Excluir linha ou coluna com o controle ligado (`edicao/tabelas.py`): `w:del` no `w:trPr` da
  linha ou `w:cellDel` no `w:tcPr` de cada célula da coluna (`fx_revisoes.com_marca`), e o texto
  das células excluído, como no Word; a linha (ou a coluna inteira) que o próprio autor inseriu
  sai de verdade. Um passo de desfazer.
- Recortar e colar com o controle ligado (`lembrar_recorte`, `colar_como_movimento`): o recorte
  guarda o trecho em dois `QTextCursor` (andam com a edição; o do fim não anda com o que é
  inserido nele). Se o colado é o mesmo texto, no mesmo documento, e a origem continua inteira
  excluída pelo autor, a origem vira `moveFrom`, o colado `moveTo`, e entram as quatro pontas com
  um nome novo (`moveN`). Só trecho dentro de um parágrafo, fora de tabela e sem marcas.
- Documento que só tem revisão de tabela ou de seção (sem texto revisado) passa a ter a lista e o
  realce (`para_qt._tabela_revisada`; antes a lista ficava vazia).

Limites: rejeitar não desfaz a mescla (`w:cellMerge`), nem tira a célula inserida sozinha numa
linha, nem devolve o `w:numberingChange` (só guarda o texto do número de antes): ficam, e a
mensagem diz quantas; no modo
final, o parágrafo cuja marca foi excluída mas que ainda tem texto fica separado do de baixo, e a
tabulação e a quebra de linha dentro do texto escondido continuam ocupando espaço; imagem e objeto
excluídos não somem nos modos sem marcação; a formatação de parágrafo de antes não aparece no modo
Original; as revisões das notas se aceitam e rejeitam na edição da nota, e as de dentro de um
comentário ou de uma caixa de texto só são preservadas; mover texto (recortar e colar) com o
controle ligado vira exclusão e inserção, não movimento; o comentário na margem do PDF não é um
balão (texto pequeno ao lado do trecho, um embaixo do outro).

## Política de perda

Cada recurso do `.docx` é exato, aproximado, preservado sem edição (objeto opaco, desde a
0.1.2; partes do pacote, campos, hiperlinks e marcadores, desde a 0.1.3; definições de
numeração, desde a 0.1.4; formatação que o modelo não representa e controles de conteúdo de
parágrafo e de bloco, desde a 0.1.5; comentários editáveis e referências de estilo sem
definição, desde a 0.1.6; notas de rodapé e de fim, desde a 0.1.10; seções, com papel, cabeçalhos, numeração,
colunas e o resto do `w:sectPr`, desde a 0.1.12; alterações controladas, desde a 0.1.13) ou
descartado com aviso. Listas são exatas desde a 0.1.4: LISTA e
LISTA_NIVEL só para referência quebrada, nível fora de 0 a 8 ou numeração acima dos
limites, e LISTA_EM_CAIXA só quando a numeração do arquivo não pôde ser lida. Se algo que se perderia ao salvar estiver presente, a primeira gravação pede
confirmação e oferece "Salvar cópia". O que é preservado tem aviso sem perda (ou nenhum) e
não pede confirmação. Controles de conteúdo de linha ou célula de tabela entram aqui até a versão
que os implementar; REVISAO, desde a 0.1.13, é só a revisão que não pode ser guardada (acima dos
limites, data absurda, fora do lugar do esquema); NOTA, desde a 0.1.10, é só a nota que não pode ser lida
(sem referência no corpo, acima dos limites, referência fora do corpo). Nenhuma parte do pacote sai sem
aviso: o que não volta tem aviso próprio (PARTE_PERDIDA, MACROS, ASSINATURA, COMENTARIO,
NOTA, MINIATURA). COMENTARIO desde a 0.1.6 é só o comentário que não pode ser lido.

Conferência que falha (0.1.11): o arquivo gravado não substitui o original. A janela grava a
cópia de recuperação, explica sem jargão (`dialogos_modais.pedir_falha_na_conferencia`; o
motivo técnico vai para o log) e oferece salvar os mesmos bytes, sem a conferência, em outro
arquivo, nunca no caminho do original nem no do destino. O documento continua "alterado".

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
| Listas | 0.1.4 (feito) | numbering.xml inteiro, números como o Word, galeria, vários níveis, teclado |
| Sem perda | 0.1.5 (feito) | rPr/pPr/tabela preservados, controles de conteúdo, texto da caixa editável, EMF/WMF/TIFF/SVG na tela |
| Comentários | 0.1.6 (feito) | comments.xml e partes estendidas, painel, aba Revisão, referências de estilo preservadas |
| Flutuantes | 0.1.7 (feito) | objeto na posição da página, texto em volta, atrás e na frente, cabeçalho, PDF |
| Desempenho e cabeçalho por página | 0.1.8 (feito) | digitação ≤ 16 ms num manual pesado; topo do corpo pelo cabeçalho de cada página |
| Mover e redimensionar | 0.1.9 (feito) | arrastar, alças, setas, quebra de texto, diálogo Posição e tamanho, cabeçalho |
| Notas | 0.1.10 (feito) | footnotes.xml e endnotes.xml, numeração, área de notas na página, edição no lugar, aba Referências, PDF |
| Seções | 0.1.12 (feito) | sectPr de cada seção sem perda, papel e cabeçalhos por folha, numeração por seção, quebras de seção, Vincular ao anterior |
| Controle de alterações | 0.1.13 (feito) | w:ins, w:del, movimentos, formatação, marca de parágrafo, tabela e seção sem perda; quatro modos de exibição; edição rastreada; aceitar e rejeitar; painel; imprimir marcações |

Caminho crítico: M1, M2 e M3. Antes do M3, um spike de página valida o controle
de texto próprio; se a tecla morta ou a IME falharem, o plano B é uma visão em
modo contínuo, com paginação só na impressão.

## Fora da 0.1.0

Revisão (comentários desde a 0.1.6; notas de rodapé desde a 0.1.10; controle de alterações desde a 0.1.13), gerar e atualizar
índices e sumários (preservados como campo desde a 0.1.3), mala direta, edição de equações e formas (preservadas sem
edição desde a 0.1.2; o texto das caixas se edita desde a 0.1.5), colunas na tela (preservadas desde a 0.1.12; as seções se editam desde a 0.1.12), ortografia (prevista para a
0.2 pela API do Windows), `.doc`, RTF, ODT e macros (nunca).

## Riscos abertos

1. Espaçamento entre parágrafos: o Qt colapsa margens verticais para o maior
   valor, e o Word, ao que tudo indica, soma. Conferido no código do Qt 6.11 na 0.1.16
   (`layoutBlock`: `qMax(topMargin, bottomMargin do anterior)`); continua aberto, junto com
   viúvas e órfãs, manter com o próximo e `contextualSpacing` (docs/SPIKES.md, 0.1.16).
2. O Word pode reclamar de um `.docx` gerado sem ser visto. Mitigação: vocabulário
   conservador, validação de ordem dos elementos, releitura antes da troca, e um
   protocolo de aceite manual com amostras.
3. Paginação diferente da do Word. Não se promete identidade de quebras.
