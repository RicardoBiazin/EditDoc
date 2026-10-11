# Origem do código

O EditWord começa com infraestrutura copiada do TextForgeEdit v0.17.2, do mesmo
autor e na mesma licença MIT. A cópia foi adaptada, não compartilhada: os dois
repositórios são públicos e cada um precisa funcionar sozinho.

| Arquivo do EditWord | Origem no TextForgeEdit | O que mudou |
|---|---|---|
| `LICENSE` | `LICENSE` | nada |
| `editword/log_interno.py` | `tfedit/log_interno.py` | nome do app; docstring reescrita |
| `editword/recursos.py` | `tfedit/recursos.py` | nome do pacote |
| `editword/idioma.py` | `tfedit/idioma.py` | nome do pacote |
| `editword.manifest` | `textforgeedit.manifest` | nome, versão, descrição |
| `versao.txt` | `versao.txt` | nome, versão, descrição |
| `ferramentas/empacotar_zip.py` | `ferramentas/empacotar_zip.py` | nome do pacote e da pasta de saída |
| `tests/ajudantes.py` | `tests/ajudantes.py` | sem o isolamento de canal de instância única (ainda não existe); mesmo contrato de saída |
| `tests/rodar_todos.py` | `tests/rodar_todos.py` | lista de suítes própria; sem tetos por suíte |
| `build.bat` | `build.bat` | cinco etapas: inclui a fumaça que abre a janela |

Escritos do zero: `app.py`, `editword/configuracao.py`, `editword/interface/`,
`ferramentas/gerar_icone.py` (o desenho é próprio, com outra cor),
`ferramentas/fumaca_exe.py`, `EditWord.spec`, as suítes de `tests/` e a
documentação.

Quando um arquivo copiado mudar no TextForgeEdit, a diferença não chega aqui
sozinha. Conferir esta tabela antes de copiar de novo.
