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

Escritos do zero: `app.py`, `editdoc/configuracao.py`, `editdoc/interface/`,
`ferramentas/gerar_icone.py` (o desenho é próprio, com outra cor),
`ferramentas/fumaca_exe.py`, `EditDoc.spec`, as suítes de `tests/` e a
documentação.

Quando um arquivo copiado mudar no TextForgeEdit, a diferença não chega aqui
sozinha. Conferir esta tabela antes de copiar de novo.
