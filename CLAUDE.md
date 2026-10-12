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
- `app.py`: ponto de entrada e `--autoverificacao`.
- `tests/`: suites sem pytest. `rodar_todos.py` roda cada uma em processo próprio.
- `ferramentas/`: `gerar_icone.py`, `empacotar_zip.py`, `fumaca_exe.py`.
- `docs/ARQUITETURA.md`: o plano. `docs/ORIGEM.md`: o que foi copiado do TextForgeEdit.

## Como testar

```
.venv\Scripts\python.exe tests\rodar_todos.py
```

Testes que mexem em janela rodam em `offscreen`. `tests/ajudantes.py::preparar_qt()`
isola `%APPDATA%`: nunca escrever no config do usuário. Um teste de janela não
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
| campo no `.docx` | `instrText` com espaco precisa de `xml:space="preserve"` (o validador confere, como o `w:t`), e begin/end tem de fechar no mesmo paragrafo: senao o Word engole o texto seguinte como instrucao. |
