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
| `numPr` em estilo | Aponta para o `numbering.xml` de origem, que o EditDoc regrava: tirar do estilo e passar a lista ao paragrafo na leitura. |
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
| campo no `.docx` | `instrText` com espaco precisa de `xml:space="preserve"` (o validador confere, como o `w:t`), e begin/end tem de fechar no mesmo paragrafo: senao o Word engole o texto seguinte como instrucao. |
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
| propriedade de usuario repetida | `PROP_ESTILO_CAR` (estilos.py) e `PROP_CAMPO_RESULTADO` (campos.py) sao o mesmo numero (`UserProperty + 5`), no formato de caractere. Propriedade nova escolhe um numero livre de verdade (`PROP_OPACO` = + 20). |
| `\f` em docstring | O docstring do escritor tinha uma barra invertida antes de "formato_docx": virou o caractere 0x0C no texto. Em docstring nao bruto, nada de barra invertida antes de letra. |
