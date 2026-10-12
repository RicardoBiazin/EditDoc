# Origem do código

O EditDoc começa com infraestrutura copiada do TextForgeEdit v0.17.2, do mesmo
autor e na mesma licença MIT. A cópia foi adaptada, não compartilhada: os dois
repositórios são públicos e cada um precisa funcionar sozinho.

| Arquivo do EditDoc | Origem no TextForgeEdit | O que mudou |
|---|---|---|
| `LICENSE` | `LICENSE` | nada |
| `editdoc/log_interno.py` | `tfedit/log_interno.py` | nome do app; docstring reescrita |
| `editdoc/recursos.py` | `tfedit/recursos.py` | nome do pacote |
| `editdoc/idioma.py` | `tfedit/idioma.py` | nome do pacote |
| `editdoc.manifest` | `textforgeedit.manifest` | nome, versão, descrição |
| `versao.txt` | `versao.txt` | nome, versão, descrição |
| `ferramentas/empacotar_zip.py` | `ferramentas/empacotar_zip.py` | nome do pacote e da pasta de saída |
| `tests/ajudantes.py` | `tests/ajudantes.py` | sem o isolamento de canal de instância única (ainda não existe); mesmo contrato de saída |
| `tests/rodar_todos.py` | `tests/rodar_todos.py` | lista de suítes própria; sem tetos por suíte |
| `build.bat` | `build.bat` | cinco etapas: inclui a fumaça que abre a janela |
| `editdoc/instancia_unica.py` | `tfedit/instancia_unica.py` | variável `EDITDOC_CANAL` no lugar de `TFEDIT_CANAL`; mutex nomeado do Windows antes do `listen()` (medido: sem ele, duas instâncias abertas juntas viram duas janelas) |
| `editdoc/cli.py` | `tfedit/cli.py` | sem `--linha` e `--coluna`; motivos de recusa em pt-BR; aceita `\\.\NUL` e caminho vazio como recusados |
| `editdoc/armazenamento/gravacao.py` | `tfedit/gravacao.py` | só a parte de bytes prontos (`gravar_bytes`); conferência antes da troca; temporário `.ewnew`; sem a parte de pecas do documento |
| `associar.ps1` | `associar.ps1` | só HKCU, sem item de menu de contexto para todos os arquivos; ProgID `EditDoc.Documento`; `SupportedTypes` só com as extensões pedidas |

Escritos do zero: `app.py`, `editdoc/configuracao.py`, `editdoc/interface/`,
`editdoc/formato_docx/` (leitor, escritor e validador de ordem), `editdoc/ponte_qt/`,
`editdoc/modelo/documento.py`, `tests/fixtures_docx.py`,
`ferramentas/gerar_icone.py` (o desenho é próprio, com outra cor),
`ferramentas/fumaca_exe.py`, `EditDoc.spec`, as suítes de `tests/` e a
documentação.

Quando um arquivo copiado mudar no TextForgeEdit, a diferença não chega aqui
sozinha. Conferir esta tabela antes de copiar de novo.
