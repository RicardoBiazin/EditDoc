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
