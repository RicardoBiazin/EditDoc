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
  com perda. Referência a nota, nota de fim e comentário e `w:numPr` saem de dentro do
  objeto, com aviso: essas partes não voltam, e a referência ficaria pendurada.
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
  `DocumentoQt`) pinta um quadro do tamanho do objeto na linha, ou uma etiqueta no ponto
  da âncora do flutuante e da equação, com o rótulo e o começo do texto. O HTML que o Qt
  gera não leva o objeto: copiar e colar omite o objeto, e uma marca na área de
  transferência faz o colar avisar na barra de status.

Limites: 2000 objetos por documento, 4 MB de XML por objeto, 64 MB somados, 64 partes e
6 níveis de relação por objeto. O objeto não é editado por dentro; para mudar o texto de
uma caixa, só no Word.

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

Limite: o controle de conteúdo (`w:sdt`) continua achatado com aviso. O do sumário do Word
envolve parágrafos inteiros (bloco), e as marcas no fluxo ficam dentro dos parágrafos: o
escritor teria de subir o `w:sdt` para fora deles, o que não cai no mesmo mecanismo.

## Política de perda

Cada recurso do `.docx` é exato, aproximado, preservado sem edição (objeto opaco, desde a
0.1.2; partes do pacote, campos, hiperlinks e marcadores, desde a 0.1.3) ou descartado com
aviso. Se algo que se perderia ao salvar estiver presente, a primeira gravação pede
confirmação e oferece "Salvar cópia". O que é preservado tem aviso sem perda (ou nenhum) e
não pede confirmação. Comentários, revisões, notas de rodapé de verdade e controles de
conteúdo entram aqui até as versões que os implementam. Nenhuma parte do pacote sai sem
aviso: o que não volta tem aviso próprio (PARTE_PERDIDA, MACROS, ASSINATURA, COMENTARIO,
NOTA, MINIATURA).

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

Revisão com controle de alterações, comentários, notas de rodapé, gerar e atualizar
índices e sumários (preservados como campo desde a 0.1.3), mala direta, edição de equações, formas e caixas de texto (preservadas sem
edição desde a 0.1.2), colunas, seções múltiplas editáveis, ortografia (prevista para a
0.2 pela API do Windows), `.doc`, RTF, ODT e macros (nunca).

## Riscos abertos

1. Espaçamento entre parágrafos: o Qt colapsa margens verticais para o maior
   valor, e o Word, ao que tudo indica, soma. Mede-se no M3.
2. O Word pode reclamar de um `.docx` gerado sem ser visto. Mitigação: vocabulário
   conservador, validação de ordem dos elementos, releitura antes da troca, e um
   protocolo de aceite manual com amostras.
3. Paginação diferente da do Word. Não se promete identidade de quebras.
