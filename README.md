# EditDoc

Editor de documentos no formato `.docx`, com a aparência de um processador de
texto de escritório: páginas A4, faixa de opções, estilos, tabelas, imagens,
cabeçalho e rodapé.

> **Versão 0.0.4: editor básico.** Já edita, formata, localiza e substitui, mas
> ainda não abre nem salva arquivos: isso chega na 0.0.5. A primeira versão
> completa é a 0.1.0. O plano está em [docs/ARQUITETURA.md](docs/ARQUITETURA.md),
> e os resultados dos spikes em [docs/SPIKES.md](docs/SPIKES.md).

O EditDoc não é afiliado à Microsoft. Word é marca registrada da Microsoft.

## Planejado para a 0.1.0

- Abrir e salvar `.docx` com fidelidade ao texto, à formatação, às listas, às
  tabelas e às imagens.
- Visão em páginas A4 com margens, régua e quebras de página.
- Cabeçalho, rodapé e número de página.
- Estilos (Normal, Título 1 a 3...) e faixa de opções.
- Exportar PDF, imprimir e pré-visualizar.

Fica fora da 0.1.0: revisão com controle de alterações, comentários, notas de
rodapé, índices, equações, colunas e ortografia.

## Desenvolvimento

Requer Windows 10 ou 11 e Python 3.13.

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe tests\rodar_todos.py
.venv\Scripts\python.exe app.py
```

Gerar o executável e a versão para entrega:

```
build.bat
```

O `build.bat` roda os testes, empacota com PyInstaller, confere que o `.exe`
passa na autoverificação, confere que ele abre a janela e gera o ZIP em
`dist\`. Se qualquer etapa falhar, nada é entregue.

## Licença

MIT. Ver [LICENSE](LICENSE). Os componentes de terceiros estão listados em
[AVISOS_DE_TERCEIROS.md](AVISOS_DE_TERCEIROS.md).
