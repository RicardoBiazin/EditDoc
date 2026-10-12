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
