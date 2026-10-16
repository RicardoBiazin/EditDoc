# CLAUDE.md: EditDoc

Editor de documentos `.docx` em Python 3.13 + PySide6 6.11.2. Este arquivo é lido
antes de qualquer alteração. As regras abaixo existem porque a alternativa já
causou defeito.

## Regras inegociáveis

1. **O documento aberto é dado, nunca código.** Nada de `eval`, `exec`,
   `pickle`, `marshal`, `shell=True`, `os.system` ou macros. `tests/teste_higiene.py`
   varre o código e falha se algum aparecer.
2. **Nunca perder conteúdo em silêncio.** Gravação atômica (arquivo novo, depois
   troca). O original fica intacto se qualquer etapa falhar.
3. **Texto de tela é pt-BR com acentos.** Comentário, docstring e log podem ser
   ASCII. Strings de interface, não.
4. **Versão em três lugares, que têm de bater:** `editdoc/__init__.py`
   (`VERSAO`), `versao.txt` e `editdoc.manifest`. `tests/teste_base.py` confere.
5. **Dependência de execução fixa com `==`.** Nada de PyMuPDF ou outra AGPL/GPL
   dentro do pacote. Toda dependência nova entra em `AVISOS_DE_TERCEIROS.md`.
6. **Nenhum documento real no repositório.** `.gitignore` bloqueia `*.docx`;
   fixtures públicas são geradas por código ou têm licença clara.

## Estrutura

- `editdoc/`: pacote. `configuracao.py`, `log_interno.py`, `idioma.py`,
  `recursos.py` são infraestrutura.
- `editdoc/interface/`: tudo que importa Qt. `janela_principal.py` é a casca.
- `editdoc/formato_docx/propriedades.py` e `ponte_qt/propriedades.py`: formatação preservada
  (0.1.5); `formato_docx/caixas.py` e `interface/dialogo_caixa.py`: texto da caixa de texto;
  `ponte_qt/vetoriais.py`: prévia de EMF, WMF, TIFF e SVG.
- Objetos flutuantes (0.1.7): `modelo/flutuantes.py` (posição, sem Qt),
  `formato_docx/flutuantes.py` (ancoragem e desenho lidos do XML do objeto) e
  `ponte_qt/flutuantes.py` (reserva no layout, conferência, cura do frame órfão, pintura).
- Comentários (0.1.6): `modelo/comentarios.py`, `formato_docx/comentarios.py` (partes
  estendidas, people.xml, validador), `ponte_qt/comentarios.py`, `edicao/comentarios.py`,
  `interface/painel_comentarios.py` e `interface/dialogo_comentario.py`.
- Altura por página (0.1.8): `LayoutPaginado.efetiva_da(n)` e `topo_da_pagina(n)` (o topo do corpo
  pelo cabeçalho da página); `Mapa.topo_da_pagina` e `flutuantes.Contexto.topos` seguem. Desempenho
  (0.1.8): `tests/teste_desempenho.py`, scripts de medição fora do repositório (docs/SPIKES.md).
- Mover e redimensionar (0.1.9): `formato_docx/posicao.py` (XML de posicao, tamanho e quebra,
  sem Qt), `modelo/flutuantes.deslocamento_para` (a volta de `retangulo`), `edicao/objetos.py`
  (troca do objeto no caractere, reancorar), `interface/dialogo_posicao.py`; o mouse e as setas
  no `PainelDocumento` (`_arraste`, `_geometria_do_arraste`, `flutuante_das_faixas_em`).
- Notas de rodapé e de fim (0.1.10): `modelo/notas.py` (catálogo, numeração, `preparar`),
  `formato_docx/notas.py` (propriedades, separadoras, validador; a leitura em
  `leitor._ler_notas`), `ponte_qt/notas.py` (marca TIPO_NOTA, catálogo no quadro raiz,
  espaçador), `interface/notas.py` (documento de cada nota, plano da área de notas por página,
  desfazer dos ajustes, `desenhar_notas`), `edicao/notas.py` (comandos, copiar e colar),
  `interface/dialogo_notas.py`; a edição no lugar em `PainelDocumento.entrar_na_nota`.
- Seções (0.1.12): `modelo/secoes.py` (`Secao`, herança, numeração inicial), `formato_docx/secoes.py`
  (ler e gravar cada `w:sectPr`, extras em c14n, validador), `ponte_qt/secoes.py` (caractere da
  quebra, registro), `interface/secoes.py` (`ConjuntoDeSecoes`: geometria por seção, mapa de
  folhas, quebras e recuos derivados); `LayoutPaginado.efetiva_da/pagina_da_folha/faixa_da_folha/
  campos_da_folha`; a linha de tabela empurrada da seção mais baixa em `interface/notas.py`.
- Controle de alterações (0.1.13): `modelo/revisoes.py` (modos, limites, lista, equilibrar os
  movimentos), `formato_docx/revisoes.py` (ler/gravar, `Numerador` dos w:id, validador),
  `ponte_qt/revisoes.py` (propriedades, `RealceRevisoes` dos modos, barra na margem),
  `edicao/revisoes.py` (edicao rastreada, aceitar/rejeitar, lista, navegar),
  `interface/revisoes_janela.py` (ganchos da aba Revisao, modo da janela) e
  `interface/painel_revisoes.py`. Rejeitar o estado de antes (0.1.14): `formato_docx/revisoes`
  (`tabela_da_mudanca`, `linha_da_mudanca`, `celula_da_mudanca`, `secao_da_mudanca`, `com_marca`);
  excluir linha/coluna rastreado em `edicao/tabelas.py`; mover (recortar e colar) em
  `edicao/revisoes.lembrar_recorte`/`colar_como_movimento`.
- Conferencia pos-gravacao: `formato_docx/conferencia.py` (desde a 0.1.16 tambem a formatacao
  efetiva, `_Efetivas`); fidelidade da gravacao em `tests/teste_fidelidade.py`.
- Paginacao como a do Word (0.1.17): `modelo/paginacao.py` (regras sem Qt: espaco somado,
  viuvas e orfas, on/off da cadeia de estilos, metricas da fonte), `ponte_qt/paginacao.py`
  (compensacao no formato e como ler o valor de verdade) e `interface/paginacao.py`
  (`ConjuntoDePaginacao`: compensacao e regras de quebra, chamado por
  `LayoutPaginado.atualizar_secoes`); testes em `tests/teste_paginacao_word.py`.
- `editdoc/recuperacao.py`: cópias de recuperação e trava, sem Qt (M8). Acessibilidade em
  `interface/acessibilidade.py` e `interface/dicas_teclas.py`; preferências em
  `configuracao.py` (validação) e `interface/dialogo_opcoes.py`.
- `app.py`: ponto de entrada e `--autoverificacao`.
- `tests/`: suites sem pytest. `rodar_todos.py` roda cada uma em processo próprio.
- `ferramentas/`: `gerar_icone.py`, `empacotar_zip.py`, `fumaca_exe.py`.
- `docs/ARQUITETURA.md`: o plano. `docs/ORIGEM.md`: o que foi copiado do TextForgeEdit.

## Como testar

```
.venv\Scripts\python.exe tests\rodar_todos.py
```

Testes que mexem em janela rodam em `offscreen`. `tests/ajudantes.py::preparar_qt()`
isola `%APPDATA%` e `%LOCALAPPDATA%` (e aponta `EDITDOC_RECUPERACAO` para dentro): nunca
escrever no config nem nas cópias de recuperação do usuário. Um teste de janela não
pode terminar com `close()` numa janela com alteração pendente, porque o diálogo
modal trava a suíte.

Testar uma tecla é apertar a tecla (`QTest.keyClick`), não chamar o método.

## Ao alterar

1. Rodar a suíte. Uma verificação que não pode falhar não vale nada: quando
   criar uma, exigir também que ela acuse um caso proposital.
2. Subir a versão nos três lugares da regra 4 e atualizar `CHANGELOG.md` e
   `README.md`.
3. `build.bat`. O executável tem de passar na autoverificação e abrir a janela.
4. Commit `vX.Y.Z: título em português sem acento`, com corpo explicando o
   defeito, a causa e a prova. Push, tag anotada e GitHub Release com notas em
   português.

## Armadilhas já conhecidas

| Onde | Armadilha |
|---|---|
| `idioma.py` | O `QTranslator` precisa de referência viva, senão o coletor o destrói e os textos voltam ao inglês. Guardado em `app._tradutores`. |
| `EditDoc.spec` | Os `.qm` vão em `datas` para a pasta `traducoes`; o PyInstaller não os inclui sozinho. |
| `build.bat` | Fim de linha CRLF. Com LF o `cmd` executa a linha seguinte pela metade. |
| `build.bat` | `tasklist \| find` trava o build sem console anexado. Usar o código de saída do PowerShell. |
| `gerar_icone.py` | Forma de 1 px some a 16 px. O traço é grosso de propósito. |
| `ícone da janela` | O `.ico` do executável só vale para o shell. A janela precisa de `setWindowIcon` própria. |
| `estado.py` | `QTextCharFormat.fontFamily()` está depreciado e **derruba o processo** (acesso inválido) num formato vazio. Usar `fontFamilies() or []`. |
| testes de layout | O offscreen não tem fontes e usa um fallback ~2x mais largo. Medir largura sem `usar_fonte_windows()` dá números que não valem para o usuário. |
| testes de desfazer | `availableUndoSteps()` conta comandos internos do Qt (cada bloco e cada troca de formato), não ações do usuário. Checar pelo comportamento: um desfazer devolve tudo. |
| `QTest.keyClicks` | Acento entra como byte errado, e `keyClicks` com acento derruba o processo. Acento vem por `QKeyEvent` com `text()`. |
| `QTextEdit` | Consome `ShortcutOverride` das teclas de edição. O `PainelDocumento` procura o atalho no `keyPressEvent`. |
| `setPlainText` | Deixa o cursor no início. Antes de digitar num teste, mover para o fim. |
| `QToolButton.setDefaultAction` | Copia o texto da ação e não deixa encurtar o rótulo. A faixa usa `BotaoAcao`, que sincroniza por sinal. |
| janela e largura mínima | A janela não encolhe abaixo do mínimo dos filhos. Para testar faixa estreita, forçar a própria faixa. |
| `zipfile` no Windows | `ZipInfo(nome)` troca `\` por `/` ao criar. O nome bruto fica em `orig_filename`: o leitor valida esse, e um teste que quer uma barra invertida fixa `info.filename` depois de criar o `ZipInfo`. |
| `w:sz` | Tamanho em meio-ponto: 24 = 12 pt. O modelo guarda `tamanho_meio_pt`, e a ponte converte com `pontos * 2`. |
| `setFontUnderline` | Texto inserido **sem formato** herda o sublinhado do vizinho. A ponte sempre passa um formato explícito; para limpar, `setUnderlineStyle(NoUnderline)`. |
| `QTextDocument.toPlainText` | Troca o separador de linha U+2028 por `\n`. Para ver a quebra real, ler `bloco.text()`. |
| `.docx` e o Word | Round-trip e python-docx não veem `xml:space` nem a ordem de `pPr`/`rPr`, e o Word abre com reparo. O validador de `formato_docx/ordem.py` roda antes de cada gravação. |
| `[Content_Types]` | Um `Default` genérico (`application/xml`) cobre a parte, mas com tipo errado: o Word não acha o conteúdo. Exigir `Override` para cada parte. |
| `QLocalServer.listen` | Medido no Windows com Qt 6.11: um segundo `listen()` com o mesmo nome devolve True enquanto o primeiro vive. Por isso a instância única usa um mutex nomeado. |
| `QTextDocument.setPlainText` | Não marca o documento como sujo. Um teste que espera o aviso de "alterado" precisa de `setModified(True)`. |
| `QTextCursor.createList` | Cria a lista só no bloco atual. Os blocos seguintes entram com `QTextList.add`, senão cada um vira uma lista nova. |
| `QTextEdit` sobre o mesmo documento | Um QTextEdit, mesmo oculto, ligado ao QTextDocument da visao em paginas forca `pageSize = (largura, -1)` e apaga a paginacao (medido: 20 paginas viram 1). A visao em paginas nao pode ter QTextEdit ligado ao documento. |
| `QTextDocument` novo | Ajustar fonte ou margem marca `isModified()`. `LayoutPaginado` zera isso no fim da construcao. Sem isso a janela nasce suja, e um teste que fecha com alteracao pendente trava no dialogo modal. |
| `contentsChange` | No sinal o layout ainda nao foi refeito: `blockBoundingRect` devolve a altura antiga. A invalidacao do cache de tiles roda na pintura seguinte (`_aplicar_pendencias`). Medido: a quebra de linha deixava tiles velhos. |
| `QPainter.setClipRect` | Retangulo vazio nao recorta nada: o Qt pinta a pagina inteira para descartar (45 ms por tile). `desenhar_folha` sai antes quando o recorte esta fora do corpo. |
| `QWidget.grab()` | Pixel fora da imagem le' como 0 (preto): uma folha que passa da altura da captura conta como tinta na margem. O teste de folhas precisa caber a folha inteira na captura. |
| `QTextCursor.mergeCharFormat` | Sem selecao, muda o formato do proximo caractere digitado, nao a palavra sob o caret. O `mergeCurrentCharFormat` do QTextEdit faz o mesmo; o `PainelDocumento` usa o cursor. |
| `PageBreak_AlwaysBefore` | A quebra e' uma propriedade do bloco. O Enter precisa zerar o bloco novo para `PageBreak_Auto`, senao a quebra se copia para o paragrafo seguinte. |
| escala da tela | Quando o corpo da fonte passa de 56 a 64 px no dispositivo (tamanho x 4/3 x zoom x DPR), o Qt pinta o texto por caminho e a digitacao passa de 16 ms. Medido: 14 pt a 300% (56 px) passa; 16 pt a 300% (64 px) nao. Por isso o zoom tem teto (`ESCALA_DISPOSITIVO_MAXIMA`, em `editdoc/modelo/folhas.py`). |
| `docx` `w:br type="page"` | Um `` e' a sentinela do leitor para a quebra de pagina. XML 1.0 nao aceita `` em `w:t`, entao so' vem dali. A quebra no meio do texto parte o paragrafo. |
| `QTextTableCell` | Depois de `insertRows`, `removeColumns`, `mergeCells` ou `splitCell`, a celula guardada fica invalida: `row()` nela **derruba o processo**. Guardar linha e coluna em inteiros antes de mexer na grade. |
| `insertTable` | O Qt sempre tem um bloco antes e um depois de cada tabela, e parte o bloco no cursor. O bloco que o modelo nao tem leva `PROP_ESTRUTURAL` (`ponte_qt/para_qt.py`) e, vazio, nao volta ao salvar. Enter e digitacao nele tiram a marca. |
| remover tabela | Selecionar o quadro inteiro e `removeSelectedText` funde o paragrafo de cima com o de baixo. `excluir_tabela` parte o bloco de novo. |
| recurso de imagem | Depois de desenhar, o Qt troca o recurso (bytes) pela imagem decodificada. Os bytes originais ficam no registro de `ponte_qt/imagens.py`, nunca so' no documento. |
| `QTextDocument.loadResource` | O padrao le `file:` de um HTML colado. O `DocumentoQt` so' entrega imagem do registro; o resto vira quadro cinza ou nada. |
| tabela colada | So' aparece em `rootFrame().childFrames()` depois do `endEditBlock`. O ajuste da tabela colada usa `joinPreviousEditBlock` para ficar no mesmo desfazer. |
| linha de tabela entre paginas | O retangulo do bloco na celula pode cruzar a divisa: o Qt desce a LINHA com um deslocamento dentro do bloco. Testar corte pela linha (`lineAt`), nao pelo `blockBoundingRect`. |
| tabela grande | O Qt refaz a tabela inteira a cada tecla (~0,06 ms por celula). Os limites do leitor (`tabela_celulas` etc.) e dos comandos (`edicao/tabelas.py`) existem por isso. |
| leitor e namespace | Elemento fora do `w:` (equacao `m:oMath`) era pulado pelo `if ns != W` sem aviso. Conferir o namespace ANTES de descartar. |
| area de transferencia no offscreen | Sair do processo com algo na area de transferencia derruba o processo (codigo 139) so' no offscreen. `ajudantes.preparar_qt` limpa no `atexit`. |
| `QTextObjectInterface` | Com `class X(QObject, QTextObjectInterface)` o PySide 6.11 aceita o `registerHandler`, mas `handlerForObject` devolve None e o objeto some sem erro. O manipulador do campo herda de `QPyTextObject` (`ponte_qt/campos.py`). |
| propriedade de formato com `""` | `setProperty(prop, "")` volta do PySide como lista vazia, e `str()` dela da' `"[]"`. `campos.resultado_de` so' aceita `str`. |
| `markContentsDirty` | Refaz o layout sem emitir `contentsChange`/`contentsChanged`, sem desfazer e sem `isModified`. E' assim que o campo muda de valor por pagina. Mas nao invalida o cache de tiles: quem chama limpa (`atualizar_campos` -> `_limpar_cache`). |
| altura do cabecalho | Ler `documentSize()` no `contentsChange` da' a altura de ANTES da tecla (o layout e' refeito depois do sinal). O conjunto de cabecalhos escuta `contentsChanged`, que vem depois do layout; senao o corpo desce uma tecla atrasado. |
| `PainelDocumento.document()` | Na edicao do cabecalho devolve o documento do cabecalho. Gravar, carregar e "alterado" usam `documento_corpo()`. Um `document()` novo na janela grava o cabecalho como corpo. |
| teste de campo no corpo | O corpo vem dos tiles: um segundo `grab()` nao chama `drawObject`. Para espiar o valor do campo, `_limpar_cache()` antes. |
| `QAbstractUndoItem` | O PySide 6.11 nao exporta. Para o catalogo de estilos entrar no desfazer, ele fica em JSON no formato do quadro raiz (`rootFrame().setFrameFormat`), que o Qt desfaz junto com o bloco de edicao aberto. `clear()`/`setPlainText` apagam esse formato: volta o catalogo-base. |
| desfazer e cursor | `doc.undo(cursor)` move o cursor para o ponto desfeito e tira a selecao. Teste que aplica um comando depois de um desfazer seleciona de novo. |
| estilo no `.docx` | `w:pStyle`/`w:rStyle` para estilo inexistente: o Word cai no Normal sem avisar. O escritor so' grava id do catalogo e `ordem.validar_estilos` confere. |
| `styles.xml` do Word | Tem `w14:ligatures` dentro do `rPr` do `docDefaults` e `w:rsid` nos estilos. O validador de ordem aceita filho de outro namespace so' no `styles.xml`; filho `w:` desconhecido (`rPrChange`) e' tirado com aviso FORMATACAO. |
| cor de estilo | `w:color` com `themeColor`: o Word usa o tema, nao o `val`. Ao trocar a cor, apagar o elemento inteiro. |
| `numPr` em estilo | Desde a 0.1.4 fica no estilo (o `numbering.xml` de origem volta inteiro) e o paragrafo herda. Ate' a 0.1.3 saia do estilo e passava ao paragrafo. Paragrafo com o tipo da lista herdada do estilo NAO e' materializado: `numeracao._so_tipo` confere a lista efetiva. |
| `QFontComboBox` no offscreen | Sem a fonte instalada, `setCurrentFont` mostra outra. O dialogo de estilo so' troca a fonte se o usuario mexer no combo. |
| `isHidden()` antes do `show()` | Um filho de janela que ainda nao apareceu responde `isHidden() == True`. Estado de "mostrar regua" fica num atributo, nao no widget. |
| faixa e larguras | `teste_faixa` exige: tudo expandido em 1920, so' Edicao recolhida em 1400, Fonte expandida em 820. A galeria tem preferencia sobre Edicao e encolhe antes dos outros grupos (`recolher_com_galeria`); mudar largura de grupo pede medir de novo com Segoe UI 9. |
| `pathlib.write_text` no Windows | Grava em modo texto e troca `\n` por `\r\n`. Script que edita fonte do repositório usa `read_bytes`/`write_bytes` (o `.gitattributes` pede LF). |
| PDF no offscreen | Sem fonte carregada, o `QPdfWriter` nao escreve texto nenhum (nem caixa). Sem a variante negrito, o Qt simula o negrito pintando duas vezes, e o PDF traz cada glifo em dobro ("22"). As suites de impressao chamam `usar_fontes_do_documento()`. |
| `QPrintPreviewDialog` | Guarda so' um ponteiro para o `QPrinter`: sem referencia no Python o primeiro `show()` derruba o processo. `criar_previa` guarda em `dialogo._impressora`. |
| impressao e cache | `atualizar_campos` antes de imprimir refaz o layout dos campos do corpo sem invalidar os tiles. Quem imprime chama `preparar_para_impressao()` da vista, que limpa o cache junto. |
| `QPrinter.setPageLayout` | Com margem zero numa impressora de verdade, a margem e' ajustada ao minimo e a chamada devolve False. Papel e orientacao vao separados (`setPageSize`, `setPageOrientation`) com `setFullPage(True)`. |
| PDF e copias | `QPrinter` em `PdfFormat` tem `supportsMultipleCopies() == False`: as copias sao repetidas pelo EditDoc, senao sai uma so'. |
| leitor de PDF dos testes | Cortar o stream no `endstream` estraga o dado comprimido que termina em byte de fim de linha. `tests/leitor_pdf.py` usa o `/Length` (indireto no QPdfWriter). |
| campo no `.docx` | `instrText` com espaco precisa de `xml:space="preserve"` (o validador confere, como o `w:t`). Desde a 0.1.3 o campo pode atravessar paragrafos (o sumario), mas begin/separate/end tem de estar equilibrados na PARTE inteira e o codigo (begin, instrText, separate) no paragrafo do begin: senao o Word engole o texto seguinte como instrucao. `marcas.equilibrar` roda antes de gravar. |
| `QAccessibleTextInterface` em Python | O PySide 6.11 nao exporta `selection()` nem `attributes()`. O UIA do Windows chama os dois ao listar os padroes e o processo cai ("_PyThreadState_Attach"). O documento e' exposto por `QAccessibleWidget` com o paragrafo como valor (`interface/acessibilidade.py`). Herdar de duas classes do Qt cria dois objetos C++: `interface_cast` devolve `getCppPointer(self)[1]`, nunca `self`. |
| `QKeyEvent.modifiers()` na tecla Alt | O Qt 6 inverte o bit do proprio modificador: o KeyPress do Alt chega sem `AltModifier` e o KeyRelease com. "Alt sozinho" e' a ausencia de Ctrl, Shift e Win, nao `mods == Alt`. AltGr chega como Ctrl+Alt. |
| filtro de eventos do aplicativo | Um evento de tecla ignorado sobe pela cadeia e passa no filtro uma vez por widget. O `TecladoFaixa` so' trata quando `obj is QApplication.focusWidget()`. |
| botoes da faixa | `Qt.TabFocus`, nao `NoFocus`: o clique nao rouba o foco do documento, e o teclado (Alt, F10, setas) alcanca o botao. `NoFocus` deixa a faixa inacessivel sem mouse. |
| trava da recuperacao | `msvcrt.locking` e' por handle: outra janela do MESMO processo tambem nao trava a copia. E' isso que impede duas janelas de adotarem a mesma copia. A trava some com o processo; o pid no arquivo e' so' diagnostico. |
| bloco estrutural antes da tabela | Medido no Qt 6.11.2: nao ocupa altura (a tabela comeca no topo, duas tabelas se encostam), embora `blockBoundingRect` dele informe uma linha inteira. Nao "corrigir" o que nao aparece. |
| `docDefaults` de paragrafo | Entra por baixo da cadeia de estilos so' FORA da tabela (`Resolvedor.paragrafo(sid, em_tabela)`). Quem resolve um paragrafo tem de passar o mesmo `em_tabela` na tela e na extracao, senao o espacamento vira formatacao direta no arquivo. |
| documento novo da janela | Nasce por `para_qt.preencher` com `catalogo_de_documento_novo` (fonte da preferencia, 8 pt depois). Sem isso o primeiro bloco nao tem o espacamento, e o Enter copia o bloco sem ele. |
| teste de dialogo | Para olhar um dialogo sem modal, trocar `QDialog.exec` pela funcao do teste (`teste_acessibilidade.Capturador`), mostrar, examinar e devolver Rejected. |
| objeto opaco e namespace | O `mc:Choice Requires="wps"` cita o prefixo em texto: copiar so' o elemento perde a declaracao. O XML guardado e' um `w:r` criado com `nsmap=item.nsmap` (todos os namespaces em escopo), e a raiz de cada parte gravada declara os da raiz de origem e o `mc:Ignorable`. Nunca chamar `cleanup_namespaces` no documento: ele apaga o prefixo que so' o Ignorable usa. |
| objeto opaco e ids | O Choice e o Fallback do mesmo AlternateContent repetem `w14:paraId` e `anchorId` de proposito. Id repetido so' e' trocado ENTRE objetos, e de forma consistente dentro do objeto (`GravadorOpacos._ids_unicos`). |
| SmartArt | O `dsp:dataModelExt relId` na parte de dados aponta para uma relacao do DOCUMENTO (o desenho do diagrama), nao da parte. O fecho segue esse relId, e o escritor reescreve o valor (a unica mudanca dentro de uma parte de objeto). |
| relacoes repetidas | Dois rIds de origem para o mesmo alvo externo viram um rId so' (`_Relacoes.adicionar`). A assinatura do objeto compara o conjunto de destinos, nao a lista, senao a conferencia acusa diferenca que nao existe. |
| `posixpath.relpath` no Windows | Passa pelo `os.getcwd()`, que tem barra invertida. Caminho de parte do pacote usa `opacos.relativo`. |
| validador e objeto opaco | Ordem, `xml:space`, tabela, campo e estilo valem para o que o EditDoc escreve: pulam `ordem.dentro_de_opacos` (caixa de texto, AlternateContent, `w:pict`, `w:object`, equacao), que traz `w14:ligatures` no `rPr` e outras coisas do Word. `docPr` unico e `r:id` com relacao valem dentro tambem. Linha reta tem `wp:extent cy="0"`: zero so' e' erro na figura. |
| HTML do Qt e objeto | `QTextDocumentFragment.toHtml()` nao leva o caractere de objeto de tipo proprio (medido no 6.11): colar sai sem o objeto, sem lixo. A marca `MIME_OPACOS_OMITIDOS` da' o aviso. |
| propriedade de usuario repetida | Ate' a 0.1.10 `PROP_ESTILO_CAR` (estilos.py) e `PROP_CAMPO_RESULTADO` (campos.py) eram o mesmo numero (`UserProperty + 5`) no formato de caractere: o resultado do campo apagava o estilo de caractere dele e, quando o resultado ("1") era o id de um estilo do documento, virava esse estilo e a conferencia recusava o arquivo (o documento nao salvava). Desde a 0.1.11 `PROP_CAMPO_RESULTADO` = + 34. `teste_campos.testar_propriedades_unicas` varre `ponte_qt` e acusa numero repetido (so' `PROP_ESTILO`/`PROP_CAMPO`, bloco e caractere, dividem o + 4). |
| `QTextCursor.charFormat()` com selecao | Selecionar `[pos, pos+1]` no fim de um paragrafo devolve o formato do primeiro caractere do paragrafo SEGUINTE (medido no Qt 6.11): a marca de la' parecia estar no separador. Formato de um caractere vem do fragmento do bloco (`ponte_qt/links.formato_em`). |
| marca de campo e o `par` | Parear o fim com o inicio aberto mais recente faz o fim de um DATE fechar o sumario cujo fim foi apagado. O leitor numera inicio e fim do mesmo campo (`MarcaCampo.par`, fora da comparacao) e `equilibrar` pareia por ele. |
| PAGE em marcas | O leitor transforma PAGE/NUMPAGES simples em `Run.campo`. Um PAGE que estava em marcas (dentro de link, atravessando paragrafo) e ficou simples na edicao seria relido em outra forma e a conferencia recusaria o arquivo: `equilibrar` aplica a mesma regra antes de gravar. |
| texto no codigo do campo | `w:t` entre o begin e o separate nao aparece no Word. O leitor o poe no fluxo provisoriamente e tira quando o codigo fecha; se o campo nunca fecha (arquivo cortado), o texto fica. |
| marca de marcador | Caractere de objeto sem largura: a seta pareceria nao andar e o Backspace apagaria o marcador sem o usuario ver. O painel pula a marca nas setas, no Backspace e no Delete. |
| `customXml/item1.xml` | O Word usa o Default `xml` (`application/xml`), que o validador recusa como tipo generico. A parte preservada sempre ganha Override com o tipo de origem, mesmo que seja `application/xml`. |
| `settings.xml` preservado | Os filhos tem ordem (CT_Settings). `w:evenAndOddHeaders` entra pela lista `pacote.ORDEM_SETTINGS`; e se as notas nao voltam, `footnotePr/footnote` (a separadora) tem de sair, senao cita nota que nao existe. Sem mudanca, os bytes voltam iguais. |
| heredoc no Bash da ferramenta | Texto longo com aspas e barras dentro de `<<'EOF'` foi cortado no meio, sem erro claro: o arquivo recebeu so' metade do trecho. Patch de codigo vai num .py escrito com a ferramenta Write, numa pasta propria da sessao (a scratchpad tem arquivos de sessoes antigas com o mesmo nome). |
| propriedade de usuario (0.1.3) | `PROP_LINK` = UserProperty + 21 e `PROP_MARCA` = + 22; `TIPO_MARCA_CAMPO` = UserObject + 3 e `TIPO_MARCADOR` = + 4. UserObject + 5 continua livre (as listas da 0.1.4 usam + 23 a + 27). |
| recuo horizontal no Qt (0.1.4) | Medido no Qt 6.11.2, dispositivo de 1440 dpi: `topMargin`/`bottomMargin` do bloco sao escalados (px96 x 15), `leftMargin`/`rightMargin`/`textIndent` NAO (ficam em twips). Recuo vai em twips no formato do bloco; espaco antes e depois em px96. Ate' a 0.1.3 o recuo aparecia 15 vezes menor. |
| QTextList (0.1.4) | Nao e' usado para lista: conta um nivel so', nao tem os formatos e simbolos do Word e cola o numero no texto. A lista e' PROP_LISTA/PROP_LISTA_NIVEL no bloco e o numero e' pintado por `ponte_qt/listas.desenhar_rotulos`. QTextList so' aparece em HTML colado de fora, e o colar o converte. |
| item de lista e `textIndent` (0.1.4) | O `textIndent` do item e' o VISUAL (texto depois do numero e da tabulacao); o de verdade fica em PROP_RECUO_REAL. Quem grava recuo da primeira linha tira PROP_RECUO_REAL (`recompor_bloco`, regua, aba Layout); `props_de_bloco` le o de verdade. O ajuste e' troca de formato: depois de editar entra com `joinPreviousEditBlock`; ao abrir, antes de `clearUndoRedoStacks` (`para_qt.concluir_listas`). |
| `setProperty` com `""` e lista | O PySide devolve a string vazia como lista vazia (ver acima): PROP_RECUO_REAL sem recuo e' "nenhum", senao a comparacao nunca bate e o ajuste roda para sempre. |
| `toHtml()` e propriedade de usuario | O HTML nao leva PROP_LISTA (nem outra propriedade de usuario): teste de "um desfazer devolve tudo" em lista compara tambem a lista de cada bloco. Copiar leva as listas em `application/x-editdoc-listas`. |
| tipo da lista (0.1.4) | `Paragrafo.numeracao` e' informativo e fora da comparacao; quem manda e' `lista`/`lista_nivel`. Documento montado em codigo so' com o tipo e' materializado (`numeracao.materializar`) do mesmo jeito no escritor, na ponte e no `normalizar`, entao os numIds batem. Documento de comparacao sem os catalogos (`Documento(paragrafos=...)`) faz a lista do estilo parecer lista a criar. |
| contador da lista (0.1.4) | Os contadores sao da ABSTRATA, nao da instancia (`w:num`): duas instancias sem sobrescrita continuam a contagem. Lista nova do EditDoc que deve comecar em 1 leva `startOverride`. |
| propriedade de usuario (0.1.4) | Bloco: `PROP_LISTA` = UserProperty + 23, `PROP_LISTA_NIVEL` + 24, `PROP_RECUO_REAL` + 25, `PROP_SAIU_DA_LISTA` + 26; quadro raiz: `PROP_NUMERACAO` + 27. O proximo livre e' + 28. |
| `\f` em docstring | O docstring do escritor tinha uma barra invertida antes de "formato_docx": virou o caractere 0x0C no texto. Em docstring nao bruto, nada de barra invertida antes de letra. |
| propriedade de usuario (0.1.5) | Caractere: `PROP_RPR_EXTRA` = UserProperty + 28; bloco: `PROP_PPR_EXTRA` + 29 (`ponte_qt/propriedades.py`). O proximo livre e' + 30. A marca de controle de conteudo usa o `TIPO_MARCA_CAMPO`; UserObject + 5 continua livre. |
| extras de rPr/pPr (0.1.5) | Sao texto em forma canonica (c14n, `propriedades.canonico`): a releitura do arquivo gravado da' os mesmos bytes. Comparar extras so' pela forma canonica, nunca por `tostring` (a ordem dos atributos e as declaracoes mudam). O leitor so' guarda o "detalhe" (u duplo, cor de tema, ind com leftChars...) se o escritor nao o geraria igual: senao todo documento montado em codigo ganharia extras na releitura. |
| detalhe e formatacao direta (0.1.5) | O `de_qt` tira a formatacao direta igual a do estilo (o campo volta None). O escritor confere o detalhe contra o modelo OU, com o campo None, contra a base do estilo (`bases_de_caractere`/`bases_de_paragrafo`); sem isso a cor de tema e a entrelinha exata caiam depois de passar pelo Qt. |
| unidades no Qt (0.1.5) | Medido no Qt 6.11.2, 1440 dpi: espacamento absoluto entre letras, posicao de tabulacao (`QTextOption.Tab`) e altura fixa/minima de linha sao px96 (x 15), como a margem vertical. A tabulacao conta da posicao da linha (recuo esquerdo, e na 1a linha o recuo dela); a do Word, da margem. |
| `QImageReader` do TIFF (0.1.5) | O leitor tem de morrer ANTES do `QBuffer` (`del leitor`): na ordem inversa o plugin do TIFF fecha o arquivo no destrutor e o processo cai (codigo 139, medido). |
| SVG no PySide6 (0.1.5) | O plugin `imageformats/qsvg` nao carrega sem o `Qt6Svg.dll` no caminho: so' aparece depois de `import PySide6.QtSvg`. A previa usa `QSvgRenderer` direto e o `.spec` tem `PySide6.QtSvg` em hiddenimports. |
| GDI e QImage RGB32 (0.1.5) | O DIB do GDI deixa no quarto byte o valor do fundo (0 sobre preto). `Format_RGB32` exige 0xFF ali: sem forcar, o `CompositionMode_Difference` da' cores erradas. A transparencia do EMF sai de duas passadas (branco e preto): alfa = 255 - (branco - preto), cor pre-multiplicada = a do preto. |
| controle de conteudo de bloco (0.1.5) | A marca de inicio fica no COMECO do primeiro paragrafo e a de fim no FIM do ultimo; o escritor abre o `w:sdt` antes do paragrafo. `marcas.equilibrar` move as marcas para la' e tira par cruzado: sem isso a releitura teria as marcas em outro lugar e a conferencia recusaria o arquivo. O `w:id` repetido e' trocado no equilibrar (regex na forma canonica), nao no escritor, pelo mesmo motivo. |
| celula terminando em sdt (0.1.5) | O Word grava o controle que envolve o paragrafo da celula como o ultimo filho do `w:tc`. O validador olha o ultimo bloco DENTRO do `w:sdtContent` (`ordem._ultimo_bloco`). |
| caixa de texto editavel (0.1.5) | A edicao troca o objeto do caractere (`formato_de_opaco` com o objeto novo) num bloco de edicao: um passo de desfazer. `caixas.regravar` confere relendo: so' grava o que volta igual. A caixa com conteudo que o EditDoc nao regravaria (tabela, imagem, campo, sdt, marcador que nao seja `_GoBack`) e' so' leitura. |
| propriedade de usuario (0.1.6) | Quadro raiz: `PROP_COMENTARIOS` = UserProperty + 30 (`ponte_qt/comentarios.py`). O proximo livre e' + 31. As ancoras de comentario usam o `TIPO_MARCADOR`; UserObject + 5 continua livre. |
| revisao dentro do bloco de edicao (0.1.6) | Medido no Qt 6.11.2: com `beginEditBlock` aberto, `doc.revision()` nao muda a cada passo e o `contentsChange` so' vem no `endEditBlock`. Cache por revisao fica velho no meio do bloco: quem edita ali pede `ancoras(doc, fresco=True)` (sem isso a ancora era apagada pela posicao antiga e levava letras do texto). |
| `self._autor` na janela (0.1.6) | E' o autor do documento (string do core.xml). O autor do comentario e' `_autor_comentario()`; um metodo `_autor` sombreado deu "str object is not callable". |
| estilo sem definicao (0.1.6) | `Estilo.virtual`: referencia preservada. Nao entra no styles.xml e o validador so' a aceita pela lista `estilos_preservados` (`Estilos.virtuais()`). Teste que valida arquivo gravado com essas referencias passa a lista. "Table Grid" lido vira `Tabela.estilo = None` (o padrao do escritor), senao a releitura diferia. |
| comentario e XML de origem (0.1.6) | O w:comment nao mudado volta com o XML de origem: o leitor descarta marcador dentro do codigo de campo (a mencao "@" do Word), e so' o original o preserva. Equilibrar so' o conteudo gerado (`original is None`); equilibrar o original faria a conferencia recusar o arquivo. |
| `lxml` find com predicado (0.1.6) | `find(".//w:r[w:fldChar[@...]]")` da' "invalid predicate": usar `xpath`. |
| float do Qt (0.1.7) | Caractere de objeto com `ObjectIndex` de um `QTextFrame` FloatLeft/FloatRight e' um "float": o `QTextDocumentLayout` faz as linhas seguintes contornarem, linha a linha (o tamanho e' o `intrinsicSize`). Criar so' por `QTextCursor.insertImage(formato, posicao)`: `insertText` e `setCharFormat` tiram o `ObjectIndex` (o `setCharFormat` mantem o indice antigo do caractere). |
| float e bloco deslocado (0.1.7) | Medido no Qt 6.11.2: o layout so' refaz os blocos da faixa editada; os de baixo sao deslocados com as linhas e o float de antes (texto em volta de um objeto que ja' saiu dali). `flutuantes.Gerente.atualizar` confere reserva e largura das linhas e refaz com `markContentsDirty`; quem pinta limpa o cache. |
| float orfao (0.1.7) | Apagar o caractere do float deixa o `QTextFrame` vivo na lista de floats do layout, com o retangulo antigo, mesmo depois de refazer o layout inteiro: o Qt so' destroi o frame quando o caractere sai sem o pai (dentro de um grupo de desfazer). `Gerente.curar` desfaz e refaz a ultima acao com as reservas zeradas; o desfazer e o "alterado" ficam iguais. |
| `deleteChar` e float (0.1.7) | `QTextCursor.deleteChar`/`deletePreviousChar` nao apagam caractere com `ObjectIndex` que nao seja imagem (`canDelete`): a tecla nao fazia nada. O painel apaga o float como selecao (`_objeto_com_quadro`). |
| float que nao cabe (0.1.7) | O Qt poe floats um ao lado do outro e empurra para baixo (`findY`) o que nao cabe na largura livre, ate' para a pagina seguinte; float que passa do pe' da pagina tambem desce de pagina. A reserva e' cortada no pe' da pagina e os objetos de um paragrafo viram no maximo dois floats (`Gerente.plano`). |
| `intrinsicSize` (0.1.7) | O Qt chama a cada pintura do bloco, nao so' no layout (medido: 130 vezes por tecla num documento real). O plano de reserva fica em cache por bloco, revisao e geracao das reservas. |
| linha da ancora (0.1.7) | A linha onde o float nasce so' e' refeita se o texto nao cabe no que sobrou: a linha curta fica com a largura de antes do float. A conferencia so' acusa linha mais estreita que o espaco, ou mais larga com texto passando. |
| cabecalho com objeto (0.1.7) | O objeto do cabecalho fica atras do texto do corpo: a impressao pinta `desenhar_faixas(parte="objetos")`, o corpo e `parte="texto"`. Mudar a ordem do texto no PDF quebra os testes que leem o numero da pagina (o rodape tem de vir depois do corpo). Na tela, com objeto em faixa, os tiles sao transparentes. |
| linha que desce de pagina ao lado do float (0.1.8) | Medido no Qt 6.11.2: a linha que nao cabe no pe' da pagina ao lado de um float desce para a pagina seguinte com a largura estreita, e `markContentsDirty` nao a refaz. A conferencia que acha as mesmas faixas duas rodadas seguidas aceita as linhas (`Gerente._aceitas`, pela assinatura); sem isso cada tecla refazia 6 vezes e conferia ate' o fim do documento (no manual real, 36 dos 52 ms de cada tecla no corpo). |
| topo do corpo por pagina (0.1.8) | `layout.pagina` e' a efetiva com o MAIOR cabecalho (da' o `hb`); a folha n usa `layout.efetiva_da(n)`. Codigo novo que poe o corpo na folha (`margem_sup_tw`) usa a da pagina, senao a capa com cabecalho vazio fica 0,6 cm abaixo. A altura do corpo e' a mesma em todas: o `QTextDocument` pagina com um `pageSize` so'. |
| cache de pintura e `id()` (0.1.8) | `id()` de documento ou faixa fechados volta para o objeto seguinte: chave de cache usa `DocumentoQt.serie` e `FaixaQt.serie`. A revisao (`doc.revision()`) recomeca baixa num documento novo e nao serve sozinha. |
| `QTextFormat` sem hash (0.1.8) | O PySide 6.11 nao deixa usar `QTextFormat` como chave (`unhashable`). O tamanho da marca e' guardado pelas propriedades de fonte e por `DocumentoQt.chave_da_fonte()`, que `setDefaultFont` (sobrescrito em Python) zera: trocar a fonte padrao sem passar por ele deixaria o tamanho velho. |
| fontes nos testes de tempo (0.1.8) | Fonte carregada (`addApplicationFont`) DEPOIS de um documento aberto no processo nao substitui o fallback que o Qt ja' escolheu: o p95 dobra. `teste_desempenho` carrega as fontes no inicio e mede o relogio antes das conferencias de pixel (que esquentam a maquina) e com um painel por medida (um segundo painel aberto entra na conta). |
| objeto que muda de tipo (0.1.9) | Trocar a quebra (reserva <-> sem reserva, lado do float, linha <-> flutuante) tira o caractere e insere de novo (`edicao/objetos.trocar`): so' o `insertImage` cria o float. O float que saiu fica orfao e a cura (undo/redo) roda no proximo ciclo; o undo/redo do Qt tira a selecao do cursor do painel, que e' refeita por um `QTimer` de zero ms pedido DEPOIS (`_reselecionar`). |
| reancorar e o layout (0.1.9) | Dentro do bloco de edicao o layout nao e' refeito (`blockBoundingRect` velho). Reancorar e' em duas etapas: troca com a posicao do layout de antes, `endEditBlock`, e regrava a posicao certa com `joinPreviousEditBlock` (um desfazer so'). |
| imagem flutuante para a linha (0.1.9) | O leitor le' `wp:inline` com figura PNG/JPEG/GIF/BMP como `Imagem`, nao como objeto. Objeto opaco na linha com essa figura faria a conferencia pos-gravacao recusar o arquivo: a troca gera `Imagem` (`posicao.imagem_de_objeto`) e recusa a figura com rotacao, borda ou efeito (perderia em silencio). |
| VML em pt (0.1.9) | `style` do VML com duas casas em pt: o valor relido difere ate' 127 EMU do pedido. Teste de VML compara com essa folga. |
| `_selecionar_objeto` e rolagem (0.1.9) | Selecionar move o caret e `garantir_visivel` rola a tela: retangulo de tela calculado antes de selecionar fica velho. Teste pega o retangulo depois. |
| oito alcas (0.1.9) | O meio de cada lado do objeto selecionado e' uma alca branca: conferir a cor do contorno no meio da borda acha o branco da alca. `teste_flutuantes` confere a 1/4 da altura. |
| propriedade de usuario (0.1.10) | Caractere: `PROP_NOTA` = UserProperty + 31; quadro raiz: `PROP_NOTAS` + 32; bloco e tabela: `PROP_QUEBRA_NOTA` + 33. Objeto: `TIPO_NOTA` = UserObject + 5. Os proximos livres eram UserProperty + 34 (usado pela 0.1.11: `PROP_CAMPO_RESULTADO`) e UserObject + 6. |
| `setUndoRedoEnabled(False)` (0.1.10) | Medido no Qt 6.11.2: zera as pilhas de desfazer e refazer. Nao serve para fazer um ajuste "fora do desfazer". |
| `joinPreviousEditBlock` depois de digitar (0.1.10) | So' junta a um comando de bloco de edicao. Depois do `insertText` sem bloco (a digitacao), o ajuste juntado vira um passo proprio: o Ctrl+Z desfaria so' o ajuste. O espacador das notas e' um passo anotado (`ConjuntoDeNotas.passos`) e o `PainelDocumento.undo/redo` passa por ele. `availableUndoSteps()` conta comandos e `undoCommandAdded` vem tambem no join. |
| formato do quadro raiz (0.1.10) | Trocar (`rootFrame().setFrameFormat`) refaz o layout do documento inteiro: medido, 30 ms em 600 paragrafos. A sessao de edicao da nota troca o catalogo duas vezes (comeco e fim), nunca por tecla. |
| espacador das notas (0.1.10) | E' `PageBreak_AlwaysBefore` com `PROP_QUEBRA_NOTA` no bloco (ou no formato da tabela, que o Qt tambem respeita). Tudo que le a quebra do bloco tem de ignorar a marca: `de_qt` (nao vira `quebra_antes`), o rotulo "Quebra de pagina", o Enter (`_quebrar` tira a marca do bloco novo) e o copiar (`_html_sem_espacador`: o HTML levaria a quebra como do usuario). |
| leitor de PDF e ligadura (0.1.10) | `tests/leitor_pdf.py` devolve a ligadura "fi" como U+FB01 e separa palavras com tabulacao. Teste que procura texto no PDF normaliza os dois. |
| dialogo modal em script (0.1.10) | `JanelaPrincipal._gravar` abre um dialogo modal quando a conferencia falha (desde a 0.1.11 `dialogos_modais.pedir_falha_na_conferencia`, nao mais `avisar`): num script offscreen sem trocar a funcao, o processo fica parado para sempre. |
| pontilhado da tabulacao (0.1.8) | Um `drawText` com os pontos e o espaco no `letterSpacing` absoluto; um `drawText` por ponto custava ate' 2 ms por tile num sumario. |
| conferencia e estilo de caractere (0.1.11) | Comparava so' o CONJUNTO de estilos de caractere do paragrafo: o campo que perdia o estilo passava se outro run do paragrafo tinha o mesmo ("Pagina 1 de 3" todo em "Numero de pagina"). Agora compara tambem o estilo de cada campo (`conferencia._estilos`). |
| ordem das relacoes (0.1.11) | `sorted(rels.items())` ordena o rId pelo TEXTO ("rId10" < "rId9"): a parte preservada que a gravacao numerava rId10 passava na frente na seguinte, e cada gravacao trocava os ids de webSettings e fontTable. As relacoes preservadas usam `pacote.ordem_do_rid` (pelo numero). |
| float que muda de pagina a cada tecla (0.1.11) | Digitar ANTES das ancoras de uma capa que reserva a folha inteira poe o float na pagina seguinte; o Qt desloca os blocos de baixo com o float de antes e a conferencia os refaz para o mesmo lugar, a cada tecla (manual real: 13 blocos, 95 ms). `_juntar` faz uma chamada so' de `markContentsDirty`; `Gerente.refeito_igual` (linhas e texto iguais ao fim da conferencia anterior, mesma altura) deixa o cache. Quem limpa o cache da vista chama `esquecer_refeitos` (`_limpar_cache` ja' chama). |
| ponto "sumario" do script de gate (0.1.11) | O script da 0.1.10 procurava a linha do sumario pelo ultimo caractere ser digito; a linha do sumario termina na marca de fim do PAGEREF (U+FFFC), entao o ponto caia na posicao 0 (antes das ancoras da capa). A linha do sumario de verdade tira as marcas antes de olhar o digito. |
| `QTextFrame` filho (0.1.12) | Medido no Qt 6.11.2: a largura fixa do quadro filho vale (pode ser maior que a do documento), mas a margem de baixo dele (e a de uma tabela) NAO vale por pagina: so' a do quadro raiz, igual em todas. Largura, margem e acolchoamento de quadro, tabela e celula sao px96 (x 15) no dispositivo de 1440 dpi. A altura por secao e' feita pelo espacador das notas, nao por quadro. |
| duas quebras seguidas (0.1.12) | `PageBreak_AlwaysAfter` num bloco e `PageBreak_AlwaysBefore` no seguinte deixam uma pagina vazia no meio (medido): e' a pagina em branco de evenPage/oddPage. Por isso o espacador das notas e a quebra derivada da secao somam a politica (`fmt.pageBreakPolicy() | ...`) e `sem_espacador` devolve a quebra da secao: trocar a politica inteira apagava a do outro. |
| propriedade de usuario (0.1.12) | Caractere: `PROP_QUEBRA` = UserProperty + 35; bloco/tabela: `PROP_QUEBRA_SECAO` + 36 e `PROP_RECUO_SECAO` + 37; quadro raiz: `PROP_SECAO_FINAL` + 38; celula: `PROP_LINHA_EMPURRADA` + 39. Objeto: `TIPO_QUEBRA` = UserObject + 6. Os proximos livres: UserProperty + 40 e UserObject + 7. |
| quebra de secao e o caret (0.1.12) | O caractere da quebra e' a marca do paragrafo: o caret nunca fica depois dele (End, setas, clique), senao o texto digitado iria depois da quebra. `QTextCursor.charFormat()` no comeco de um bloco que so' tem a quebra devolve o formato do OBJETO: digitar ali limpa `PROPS_DE_QUEBRA` (senao cada letra vira uma quebra). |
| `w:type` da secao (0.1.12) | Diz como a secao COMECA. A quebra no fim da secao 1 mostra o tipo da secao 2 ("Quebra de secao (Pagina impar)" vem da secao seguinte), e inserir uma quebra muda o tipo da secao DE BAIXO (a do cursor), por um id novo no caractere dela (ou no quadro raiz, na ultima): mudar o registro no lugar nao entraria no desfazer. |
| recuo escondido da secao (0.1.12) | O documento tem a largura da secao mais larga; a mais estreita ganha recuo direito em cada bloco e tabela do primeiro nivel ("extra;total" em `PROP_RECUO_SECAO`). Quem le o recuo do usuario usa `estilos.recuo_direito_real` (o `de_qt`, a faixa, a janela); o copiar tira o extra do HTML (`_html_sem_espacador`). |
| pagina de uma secao continua (0.1.12) | O topo do primeiro bloco depois de uma quebra de pagina fica uns 160 twips abaixo do topo da folha (medido): decidir "comeca no meio da folha" pelo topo com folga marcava toda secao como continua. A folha e' da secao anterior quando o fim do paragrafo da quebra esta' na mesma folha. |
| carregar com secoes (0.1.12) | `definir_configuracao_pagina` vale para a secao do CURSOR. Ao abrir, a pagina do modelo e' a da ultima secao: `definir_pagina_final`. Um teste que carrega documento de varias secoes com o ajudante antigo (`_carregar` de teste_flutuantes) poria o papel da ultima na primeira. |
| c14n e atributos (0.1.12) | A forma canonica ordena os atributos: o `w:sectPr` gravado a partir do `original` sairia com `w:h` antes de `w:w`. Igual em c14n, mas diferente do Word: o escritor devolve a ordem do Word em pgSz, pgMar e pgNumType. |
| teste de tempo (0.1.11) | Uma medida por ponto reprovava o build num pico de carga (a maquina de desenvolvimento roda jogos e navegador). `teste_desempenho.testar_p95` usa a mediana de 3 rodadas intercaladas com o documento simples, folga relativa com teto absoluto (`TETO_MS`) e repete so' o ponto que passou (ate' 2 rodadas). Mudar o criterio pede mudar `testar_criterio_do_p95` (contraprovas sem relogio). |
| propriedade de usuario (0.1.13) | Caractere: `PROP_REV_INS` = UserProperty + 40, `PROP_REV_DEL` + 41, `PROP_REV_RPR` + 42; bloco: `PROP_REV_MARCA` + 43 e `PROP_REV_PPR` + 44 (`ponte_qt/revisoes.py`). Nenhum UserObject novo (as pontas do movimento usam o `TIPO_MARCADOR`). Os proximos livres: UserProperty + 45 e UserObject + 7. |
| modo de exibicao das revisoes (0.1.13) | Mudar o formato de caractere para esconder ou pintar texto entraria no desfazer e no "alterado". Os modos sao formatos adicionais de um `QSyntaxHighlighter` (`RealceRevisoes`): o Qt refaz so' o bloco que muda. Texto escondido: fonte de 0,01 pt (0,05 pt ainda deixa 1 twip por caractere no layout de 1440 dpi; espacamento negativo da' largura negativa; percentual 0 e' ignorado). Paragrafo inteiro: `QTextBlock.setVisible(False)` + `markContentsDirty`. |
| "alterado" ao trocar o modo (0.1.13) | Medido na janela: trocar o modo deixava o documento como alterado, sem passo de desfazer (num QTextDocument solto nao acontece; a causa exata na janela nao foi isolada). `ControleDeRevisoes.definir_modo`, `_depois_de_mudar` e `impressao.modo_de_impressao` guardam e devolvem o `isModified()` de cada documento. |
| texto excluido continua no documento (0.1.13) | Como no Word: `toPlainText()` tem o texto excluido. Quem conta, copia, localiza ou exporta usa a visao do modo (`edicao/revisoes.texto_no_modo`, `pq_revisoes.intervalos_ocultos`); o `.txt` sai do modelo, sem os runs com `exclusao`. |
| w:id das revisoes (0.1.13) | O leitor guarda as revisoes SEM o w:id (nos extras tambem) e o escritor numera tudo no fim de cada parte (`revisoes.Numerador`), pulando os ids de comentario, de marcador e todo `w:id` do XML que volta como veio (comentario e nota sem mudanca, objeto preservado). Guardar o id faria a conferencia e o c14n dependerem da numeracao. As pontas do movimento sao ligadas por um atributo provisorio sem namespace (`editdoc-par`): com namespace, o `xmlns` ficava no elemento depois de tirar o atributo. |
| imagem e objeto dentro de w:del (0.1.13) | `run_de_imagem`/`run_de_objeto` criam um `Run` novo: sem copiar a revisao do run de origem (`_Pedacos._revisoes`), a releitura perdia a exclusao e a conferencia recusava o arquivo (achado com um documento gerado pelo proprio EditDoc). |
| marca de intervalo e revisao (0.1.13) | Marcador, ancora de comentario (inicio e fim), controle de conteudo e pontas de movimento NAO ficam dentro de w:ins/w:del: o escritor fecha o elemento e grava a marca por fora, e o `de_qt` tira a revisao delas (o caractere da marca herda o formato do texto digitado em volta). Campo, referencia de comentario e de nota e quebra de coluna sao `w:r` e ficam dentro. |
| `sectPr` dentro do `w:sectPrChange` (0.1.13) | E' a secao de antes, nao uma secao: o validador de secoes reprovava ("sectPr fora do lugar") ate' pular o filho de `w:sectPrChange`. |
| revisoes no estilo (0.1.13) | O `ORDEM_RPR` passou a conhecer `w:ins`, `w:del`, `w:moveFrom`, `w:moveTo` (no comeco, a marca de paragrafo) e `w:rPrChange` (no fim). O saneamento do styles.xml continua tirando as revisoes de dentro de um estilo (`estilos._REVISOES_NO_ESTILO`, aviso FORMATACAO), como antes. |
| duas revisoes no mesmo trecho (0.1.13) | A linha de tabela inserida e o texto inserido nela tem o mesmo intervalo: o "item do cursor" e' o do texto. O painel guarda a linha escolhida (`_escolhendo`) para o cursor que muda nao destacar a outra; os testes aceitam e rejeitam pelo painel. |
| tabelas depois do ponto editado (0.1.14) | Num documento paginado, o `QTextDocumentLayout` do Qt 6.11 refaz TODAS as tabelas depois do ponto editado a cada tecla (`layoutFlow`: `if (document->pageSize().height() > 0.0f) cd->sizeDirty = true;`), e cada celula duas vezes, do zero (`layoutCell`: `fullLayout = true`, uma passada na largura infinita para a largura minima). Medido no arquivo real de 16 tabelas: 32 ms digitando no comeco, 2 ms no fim. Nao ha' como desligar de fora (o layout preguicoso so' vale no layout inteiro). Nao "otimizar" o EditDoc procurando esses milissegundos: ver docs/SPIKES.md, 0.1.14 e 0.1.15 (a cascata acontece mesmo quando a altura do bloco nao muda; layout preguicoso, colapso de bordas, formato de celula, quadro flutuante, layout proprio e documento por trecho medidos ou avaliados). |
| perfil com cProfile (0.1.14) | O `tottime` de `insertText` e' so' o C++ (os slots Python do `contentsChange` aparecem a parte). Mas o p95 da pintura sob o perfil fica 3 a 5 vezes maior: tempo de verdade so' sem o perfil, e com a maquina parada (jogos abertos dobram tudo). |
| cache de tiles (0.1.14) | A entrada e' `(pixmap, dy0, dy1, bytes, dx0, dx1)`: a faixa horizontal do documento entra para a celula editada tirar so' os tiles da coluna dela. Sabotagem em teste que troca `_invalidar_faixa` aceita `*args` (a chamada da celula passa x0, x1). |
| moveFrom e w:t (0.1.14) | Dentro de `w:moveFrom` o texto e' `w:t` (o `w:delText` e' so' do `w:del`). |
| realce e imagem (0.1.14) | O formato adicional do `QSyntaxHighlighter` nao muda o tamanho de um objeto de imagem (medido: `ImageWidth`/`ImageHeight` de 0,01 no realce, a imagem fica 200 x 100). A imagem excluida nao some em "Sem marcacao" por ai; exigiria um manipulador de imagem proprio. |
| `python3 -`, `cat >` sem entrada (0.1.14) | No Bash da ferramenta, `python3` e o `.venv\Scripts\python.exe -` sem heredoc abrem o REPL e esperam (um encheu 64 MB de saida em loop de erro); `cat > arquivo` sem heredoc espera para sempre. Patch vai num .py escrito com a ferramenta Write e rodado com `< /dev/null`. `str.replace` troca TODAS as ocorrencias: conferir `count == 1` antes. |
| propriedade de usuario (0.1.14) | Nenhuma nova. Os proximos livres continuam UserProperty + 45 e UserObject + 7. |
| layout preguicoso do Qt (0.1.15) | So' entra pelo layout do documento inteiro (`documentChanged(0, 0, tamanho)`, ex.: `setLayoutEnabled(True)`), e cada tecla empurra a fronteira ~1000 caracteres (medido no plano: 8,7 ms na 1a tecla, 25 ms de novo na 10a). `pageCount` num clone em modo preguicoso deu 10 paginas em vez de 13. Nao serve para adiar as tabelas de baixo (docs/SPIKES.md, 0.1.15). |
| parte do tile (0.1.15) | A tecla nao tira mais os tiles inteiros que a LINHA cruza: anota a parte (`VistaPaginas._sujos`) e a pintura refaz so' ela (`_repintar_partes`). So' a faixa da linha (`_invalidar_linhas`, linha da tabela: `_so_a_parte`); altura que muda, flutuantes e numeros de lista tiram o tile inteiro, como antes. Sabotagem que troca `_invalidar_faixa` continua valendo (o modo vem de um atributo, nao de argumento). |
| origem da parte refeita (0.1.15) | O Qt arredonda a posicao da letra de um jeito para coordenada positiva e de outro para negativa: pintar a parte com a origem deslocada, mesmo por pixels inteiros (a origem da folha, para juntar tiles vizinhos), pos a letra da borda do tile um pixel ao lado num zoom de 137%. A parte e' pintada num pixmap do tamanho do tile, com a MESMA transformacao dele, e so' os pixels da parte sao copiados (`CompositionMode_Source`). |
| faixa da linha e o tile inteiro (0.1.15) | O tile inteiro escondia faixas curtas demais: a linha que desce de pagina dentro do bloco fica abaixo da base do `blockBoundingRect` (`_extensao` usa as linhas), e a tinta de entrelinha exata menor que a letra passa da caixa (`FOLGA_VERTICAL_TW` e `FOLGA_DE_CORTE_TW`, 150 twips). `teste_pintura_parcial` confere pixel a pixel, com contraprova de cada folga. |
| `Numerador.atualizar` fora da pintura (0.1.15) | A janela pede o rotulo do cursor depois da tecla (`rotulos()` -> `atualizar()`), e o "mudou" ficava com ela: a pintura via "nada mudou". O Backspace que tira o item vazio da lista renumera os de baixo sem mudar altura; o tile inteiro escondia os da mesma fileira. A vista compara `Numerador.desenho` com o da pintura anterior (`_conferir_rotulos`) e tira do primeiro item diferente para baixo. |
| `python.exe -` com heredoc E `< /dev/null` (0.1.15) | O `< /dev/null` depois do heredoc troca a entrada: o Python abre o REPL e entra em loop de erro (856 MB de saida em 6 minutos). Patch e' arquivo .py escrito com a ferramenta Write. |
| propriedade de usuario (0.1.15) | Nenhuma nova. Os proximos livres continuam UserProperty + 45 e UserObject + 7. |
| arquivo sem styles.xml (0.1.16) | O leitor partia do catalogo com docDefaults vazio (tela: sem espaco, entrelinha simples, fonte da preferencia) e o escritor gravava para ele o docDefaults do documento novo (8 pt, 1,08): o salvo reabria com 6 paginas em vez de 4, com conferencia e c14n da 2a gravacao limpos. Agora o leitor usa `catalogo_sem_estilos` (o do Word: Times New Roman 10, 0, simples) e o `xml_base` grava o docDefaults do catalogo ao pe' da letra. So' o `Documento(estilos=None)` grava 8 pt e 1,08 (`catalogo_sem_catalogo`, o mesmo na conferencia): as fixtures de `bytes_de` dependem disso. |
| conferencia da formatacao (0.1.16) | Compara a formatacao EFETIVA (docDefaults, estilo, recuo da lista, direta) de paragrafo, trecho (caractere a caractere: os runs vem partidos de outro jeito) e tabela, cada lado com o proprio catalogo. Fonte e tamanho que a memoria nao define (None: a tela usa a preferencia) nao contam. Mudar o que o escritor omite por ser igual ao estilo pede mudar `_Efetivas` junto, senao a conferencia recusa o arquivo (o documento nao salva). |
| espaco entre paragrafos no Qt (0.1.16) | O `QTextDocumentLayout` usa `qMax(topMargin, bottomMargin do anterior)`; o Word soma espaco depois e espaco antes. Viuvas/orfas, keepNext, keepLines e contextualSpacing tambem nao entram no layout: a paginacao difere da do Word (docs/SPIKES.md, 0.1.16), mas e' a mesma ao reabrir o salvo. |
| altura do bloco (0.1.16) | `blockBoundingRect` da' so' a altura natural das linhas: com entrelinha proporcional, o quanto o bloco ocupa e' o passo ate' o topo do bloco seguinte. No offscreen a linha nao tem o `lineGap` da fonte (Arial 12: 268 twips; Word 276) e, sem as fontes carregadas, usa o fallback: contar paginas para comparar com o Word so' no Windows real. |
| propriedade de usuario (0.1.16) | Nenhuma nova. Os proximos livres continuam UserProperty + 45 e UserObject + 7. |
| altura da linha no Windows (0.1.17) | Medido no Qt 6.11.2 na plataforma `windows`: a linha e' winAscent + winDescent do OS/2, SEM o lineGap, como no offscreen (Arial 12: 268 twips nos dois; o Word usa 276, com o "espaco externo" = o lineGap do hhea que passa do win). A razao Word/Qt e' da familia (`ponte_qt/paginacao.fator_da_familia`, pelas tabelas da fonte via `QRawFont`); Calibri, Verdana e Cambria dao 1. |
| tabela e paragrafo vazio no Qt (0.1.17) | `QTextDocumentLayout` esconde o bloco vazio logo depois de uma tabela (sempre) e o logo antes (se nao tiver fundo); ignora o topMargin do bloco depois da tabela, o bottomMargin do bloco antes dela e, na celula, o topo do primeiro bloco e a base do ultimo (medido). A compensacao poe fundo transparente no vazio de antes (`PROP_WORD_VISIVEL`), a altura do vazio de depois no espaco antes do seguinte e os espacos em volta nas margens do quadro da tabela. O vazio estrutural (`PROP_ESTRUTURAL`) continua escondido. |
| `newPage` do Qt (0.1.17) | `y = max(y, topo da pagina seguinte)`: o espaco antes que passa da divisa fica EM PARTE no alto da pagina seguinte (nao some inteiro). A regra "topo" (motivo 3 da quebra das regras) poe o espaco antes inteiro, como o Word. |
| formato compensado (0.1.17) | `topMargin`, `bottomMargin` e `lineHeight` do bloco (e as margens do quadro da tabela) NAO sao os do paragrafo: levam a compensacao do layout do Word ("real;aplicado" em `PROP_WORD_ANTES/DEPOIS/LINHA`). Quem le usa `ponte_qt/paginacao.antes_real/depois_real/linha_real` (`props_de_bloco` ja' usa); quem grava valor do usuario chama `esquecer` da parte (`definir_paragrafo`, `definir_espacamento`, `recompor_bloco`). Ler `bf.topMargin()` direto da' o espaco somado. |
| quebra das regras (0.1.17) | `PROP_QUEBRA_REGRA` (viuvas e orfas, manter com o proximo, manter linhas juntas, quebra antes do estilo, espaco no alto da pagina) e' `PageBreak_AlwaysBefore` que nao e' do usuario, como o espacador das notas: `de_qt`, rotulo "Quebra de pagina", Enter, copiar e rejeitar a ignoram; `sem_espacador` e a pagina em branco da secao a preservam. |
| espacador das notas e o topo (0.1.17) | O topo do bloco empurrado pelo espacador das notas fica com o espaco somado: mudar o topo dele muda a conta das notas, que solta o bloco, e o ajuste oscila a cada tecla (medido: 254 ajustes em 80 teclas na secao paisagem do `teste_secoes`). |
| regras e parada antecipada (0.1.17) | A unidade e' avaliada ANTES de comparar a assinatura da pagina: o bloco empurrado que comeca a pagina pode ter deixado de precisar da quebra com a pagina comecando igual (medido: o ajuste vinha uma tecla atrasado). E a primeira unidade da conferencia nao conta as paginas de antes dela (conferia 18 paginas por tecla). |
| altura igual do documento (0.1.17) | A quebra de pagina mais abaixo (do usuario ou das regras) segura o resto no lugar: o documento fica com a mesma altura e os blocos entre a edicao e a quebra se movem. A vista confere o topo do bloco de baixo (`_seguinte_moveu`) e a base da tabela (`_tabela_moveu`). No `contentsChange`, `blockBoundingRect` de bloco recem-criado (Enter, sem layout) derrubou o processo: so' com `layout().lineCount() > 0`. |
| imagem com entrelinha multipla (0.1.17) | O proporcional do Qt multiplica a linha da imagem (1,5 x imagem); o Word multiplica a linha do texto (conferido no oraculo: a pagina do Word nao caberia com 1,5 x imagem). O bloco com objeto alto usa `LineDistanceHeight` com a distancia da linha do texto (`definir_linha(..., linha_qt)`). |
| marca de paragrafo (0.1.17) | O paragrafo vazio tem a altura da fonte da marca (o `w:rPr` do `w:pPr`, nos extras): `para_qt._escrever_paragrafo` poe essa fonte no formato do bloco. Antes a linha vazia usava a fonte do docDefaults. |
| oraculo `lastRenderedPageBreak` (0.1.17) | O leitor ignora o elemento. Para medir, trocar cada um por um marcador (`w:bookmarkStart/End`, sem largura) partindo o run: um U+200B no lugar mudava a altura da linha (27 -> 28 paginas num arquivo). A contagem do Word em `docProps/app.xml` so' vale se o arquivo veio do Word (Application); salvo pelo EditDoc, o `Pages` e' o que veio do Word antes. |
| medir no Windows (0.1.17) | Plataforma `windows` com `WA_DontShowOnScreen` na janela: o layout e' o real e nada aparece na tela. No offscreen, carregar TODAS as fontes do Windows mudou o fallback (Arial Unicode entra no lugar de fontes que faltam): 10 paginas onde a tela tem 5. Carregar so' as familias usadas. |
| patch com barra invertida (0.1.17) | Um patch em Python dentro de heredoc no Bash com `\` seguido de quebra de linha gravou `\n` literal no codigo (SyntaxError so' na suite). Patch so' em .py escrito com a ferramenta Write. |
| propriedade de usuario (0.1.17) | Bloco: `PROP_WORD_ANTES` = UserProperty + 45, `PROP_WORD_DEPOIS` + 46 (tambem no formato da tabela), `PROP_WORD_LINHA` + 47, `PROP_QUEBRA_REGRA` + 48, `PROP_WORD_VISIVEL` + 49 (`ponte_qt/paginacao.py`). Os proximos livres: UserProperty + 50 e UserObject + 7. |
