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
- Notas: `footnotes.xml` e `endnotes.xml` voltam só com as notas separadoras (separator,
  continuationSeparator, continuationNotice), que o settings.xml cita. As notas de verdade
  não voltam (aviso NOTA): as referências a elas já saíam do texto.
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
  formatação sai (REVISAO); filho `w:` fora do esquema sai (FORMATACAO). A marca de
  parágrafo (`pPr/rPr`) é saneada: sem revisão, sem estilo inexistente, na ordem.
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

Limites: "Imprimir marcações" não existe (impressão e PDF sem comentários); comentário em
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
- Interação: clique no objeto seleciona (contorno com alças); o de trás só fora do texto.
  Delete e Backspace apagam, com desfazer; duplo clique na caixa abre o editor da 0.1.5.

Limites: o texto contorna de um lado só (o maior, ou o do `wrapText`); a faixa começa na
linha da âncora (o texto acima dela não contorna, nem o de páginas anteriores);
Tight/Through seguem o retângulo; objetos de um parágrafo somam as faixas por lado (a
altura é a do mais baixo); objeto em célula de tabela não reserva espaço; mover e
redimensionar com o mouse não existem; o objeto do cabeçalho não se seleciona; geometria
fora do conjunto básico vira retângulo; `custGeom` não é seguido; a rotação e o espelho
valem, mas a área de quebra é a do retângulo sem rotação.

## Política de perda

Cada recurso do `.docx` é exato, aproximado, preservado sem edição (objeto opaco, desde a
0.1.2; partes do pacote, campos, hiperlinks e marcadores, desde a 0.1.3; definições de
numeração, desde a 0.1.4; formatação que o modelo não representa e controles de conteúdo de
parágrafo e de bloco, desde a 0.1.5; comentários editáveis e referências de estilo sem
definição, desde a 0.1.6) ou descartado com aviso. Listas são exatas desde a 0.1.4: LISTA e
LISTA_NIVEL só para referência quebrada, nível fora de 0 a 8 ou numeração acima dos
limites, e LISTA_EM_CAIXA só quando a numeração do arquivo não pôde ser lida. Se algo que se perderia ao salvar estiver presente, a primeira gravação pede
confirmação e oferece "Salvar cópia". O que é preservado tem aviso sem perda (ou nenhum) e
não pede confirmação. Revisões, notas de rodapé de verdade e controles de
conteúdo de linha ou célula de tabela entram aqui até as versões que os implementam. Nenhuma parte do pacote sai sem
aviso: o que não volta tem aviso próprio (PARTE_PERDIDA, MACROS, ASSINATURA, COMENTARIO,
NOTA, MINIATURA). COMENTARIO desde a 0.1.6 é só o comentário que não pode ser lido.

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

Caminho crítico: M1, M2 e M3. Antes do M3, um spike de página valida o controle
de texto próprio; se a tecla morta ou a IME falharem, o plano B é uma visão em
modo contínuo, com paginação só na impressão.

## Fora da 0.1.0

Revisão com controle de alterações, notas de rodapé (comentários desde a 0.1.6), gerar e atualizar
índices e sumários (preservados como campo desde a 0.1.3), mala direta, edição de equações e formas (preservadas sem
edição desde a 0.1.2; o texto das caixas se edita desde a 0.1.5), colunas, seções múltiplas editáveis, ortografia (prevista para a
0.2 pela API do Windows), `.doc`, RTF, ODT e macros (nunca).

## Riscos abertos

1. Espaçamento entre parágrafos: o Qt colapsa margens verticais para o maior
   valor, e o Word, ao que tudo indica, soma. Mede-se no M3.
2. O Word pode reclamar de um `.docx` gerado sem ser visto. Mitigação: vocabulário
   conservador, validação de ordem dos elementos, releitura antes da troca, e um
   protocolo de aceite manual com amostras.
3. Paginação diferente da do Word. Não se promete identidade de quebras.
