# Como contribuir

Obrigado pelo interesse no EditDoc. O projeto é pequeno e tem regras firmes, porque mexe
em documentos das pessoas: uma mudança que perde texto em silêncio é pior que nenhuma.

## Antes de começar

- Leia o [CLAUDE.md](CLAUDE.md): regras inegociáveis e as armadilhas já conhecidas do Qt e do
  `.docx` (cada linha da tabela já custou um defeito).
- Leia o [docs/ARQUITETURA.md](docs/ARQUITETURA.md): camadas (`modelo`, `formato_docx`,
  `ponte_qt`, `interface`) e o que fica fora do roteiro.
- Para defeito, abra uma issue com a versão (o título da janela, ou as propriedades do
  `EditDoc.exe` no Explorer), o passo a passo e, se puder, o `%APPDATA%\EditDoc\erro.log`. Não anexe
  documentos com dados pessoais.

## Ambiente

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe tests\rodar_todos.py
```

## Regras para uma mudança

1. **O documento é dado, nunca código.** Nada de `eval`, `exec`, `pickle`, `shell=True` ou
   macros (`tests/teste_higiene.py` confere).
2. **Nunca perder conteúdo em silêncio.** O que o EditDoc não entende vira aviso; o que se
   perderia ao salvar pede confirmação. Gravação sempre atômica.
3. **Texto de tela em português do Brasil, com acentos.** Comentário e log podem ser ASCII.
4. **Teste no padrão do projeto** (sem pytest): uma suíte em `tests/`, registrada em
   `tests/rodar_todos.py`, com `checa(...)`. Toda verificação nova precisa acusar um caso
   proposital (a contraprova): uma verificação que não pode falhar não vale nada. Teste de
   tecla aperta a tecla (`QTest.keyClick`). Teste nunca grava no `%APPDATA%` ou no
   `%LOCALAPPDATA%` do usuário (`tests/ajudantes.py::preparar_qt` isola os dois).
5. **Nenhum documento real no repositório.** Fixtures são geradas por código
   (`tests/fixtures_docx.py`).
6. **Dependência nova** fixa com `==`, sem AGPL nem GPL, e registrada em
   `AVISOS_DE_TERCEIROS.md`.
7. **Acessibilidade**: botão, campo ou lista novos precisam de nome para o leitor de tela
   (`tests/teste_acessibilidade.py` varre a janela e os diálogos).
8. Ao fechar uma versão: número nos três lugares (`editdoc/__init__.py`, `versao.txt`,
   `editdoc.manifest`), `CHANGELOG.md`, `README.md`, e `build.bat` com BUILD OK.

## Enviar

Faça um fork, uma branch por assunto e um pull request com o defeito (ou a melhoria), a
causa e a prova (o teste que falhava antes e passa depois). Mensagens de commit em
português, no formato `vX.Y.Z: título` para versões e frases curtas para o resto.

Contribuições entram sob a licença MIT do projeto.
