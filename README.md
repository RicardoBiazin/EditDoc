# EditDoc

Editor de documentos no formato `.docx`, com a aparência de um processador de
texto de escritório: páginas A4, faixa de opções, estilos, tabelas, imagens,
cabeçalho e rodapé.

> **Versão 0.0.10: impressão e PDF.** Visão em páginas (A4, Carta e Ofício, régua,
> quebras, zoom) com tabelas, imagens, cabeçalho, rodapé, número de página e estilos
> (galeria, painel, Modificar e Criar estilo) e, agora, Arquivo > Exportar > PDF (com
> intervalo de páginas, título e autor do documento e fontes embutidas), Imprimir (Ctrl+P)
> e Visualizar impressão (Ctrl+F2): a página impressa é a mesma da tela, com o número
> certo no rodapé de cada folha. Também exporta o texto como `.txt`. A primeira versão
> completa é a 0.1.0. O plano está em
> [docs/ARQUITETURA.md](docs/ARQUITETURA.md), e os resultados dos spikes e do gate em
> [docs/SPIKES.md](docs/SPIKES.md).

O EditDoc não é afiliado à Microsoft. Word é marca registrada da Microsoft.

## Planejado para a 0.1.0

- Abrir e salvar `.docx` com fidelidade ao texto, à formatação, às listas, às
  tabelas e às imagens.
- Cabeçalho, rodapé e número de página.
- Exportar PDF, imprimir e pré-visualizar (feito na 0.0.10).

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
