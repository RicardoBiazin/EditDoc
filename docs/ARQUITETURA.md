# Arquitetura e plano

Este documento registra o que foi decidido e o porquê. Quando o código divergir
daqui, o documento muda junto, no mesmo commit.

## Decisões do usuário

- Desktop em Python 3.13 e PySide6, para Windows.
- Formato nativo `.docx`: abrir e salvar.
- Repositório público no GitHub, licença MIT.
- A primeira versão utilizável (0.1.0) precisa ter: visão em páginas A4 com
  margens e quebras, tabelas e imagens, cabeçalho, rodapé e número de página,
  estilos com faixa de opções, além de digitar, formatar fonte e parágrafo,
  listas, desfazer, localizar, abrir e salvar.

## Camadas

```
editdoc/modelo/        o documento, puro Python, sem Qt e sem lxml
editdoc/formato_docx/  leitura e escrita de .docx (lxml + zipfile), sem Qt
editdoc/ponte_qt/      modelo <-> QTextDocument; é o único que importa QtGui
editdoc/interface/     janelas, faixa, visão em páginas, diálogos
```

O modelo intermediário existe para duas coisas: a fidelidade do ida-e-volta é
medida sobre o modelo, não sobre XML nem sobre formatos do Qt; e a leitura
pesada roda fora da thread da interface.

## Visão em páginas

Implementada no M3 (0.0.6). Ficou assim:

- `editdoc/interface/vista_paginas.py` é um `QAbstractScrollArea` que pinta as folhas. Uma
  única função, `desenhar_folha`, pinta a página para a tela e para qualquer outro destino.
- `editdoc/interface/layout_paginado.py` guarda o `QTextDocument` com `pageSize` igual ao corpo
  da página e `documentMargin` zero. O layout roda num dispositivo de 1440 dpi: uma unidade vira
  um twip, a unidade do `.docx`.
- `editdoc/modelo/folhas.py` faz o mapeamento entre documento (twips) e tela (pixels lógicos) sem
  Qt: é testável sem janela.
- `editdoc/interface/painel_documento.py` é o editor. Mantém a API do `QTextEdit` (nomes e sinais)
  para que comandos, formatação, busca e janela não mudem. Caret, teclado, mouse, seleção, clipboard
  e desfazer são dele.

Decisão de teclado: um `QTextEdit` oculto sobre o mesmo documento não serve. Ele força
`pageSize = (largura, -1)` ao ser criado e apaga a paginação (medido: 20 páginas viram 1). A
alternativa escolhida é o controle próprio, com a API do `QTextEdit`.

Zoom: troca a escala e não refaz o layout. Tem teto pela escala da tela (zoom × DPR ≤ 3): 300% em
DPR 1, 200% em DPR 1,5 e 150% em DPR 2. Acima disso o Qt pinta texto de fonte grande por caminho, e a
digitação passa de 16 ms. Medido no Gate do M3, em docs/SPIKES.md.

Cache de páginas: a folha é cortada em tiles de 256 px lógicos, no DPR da tela. Edição só invalida a
faixa alterada, ou tudo abaixo quando a altura do documento muda. O cache tem teto de 64 MB.

Quebra de página: um atributo do parágrafo (`quebra_antes`). No `.docx` é `w:br w:type="page"` no
começo do parágrafo. Quebra no meio do texto, ao ler, vira dois parágrafos: é a única perda de
estrutura, e a aparência não muda.

Limites aceitos: o Qt não tem viúva e órfã (fora do M3); uma tabela se divide entre páginas por
linha; `` não quebra página (usa-se a política de quebra do bloco).

## Tabelas e imagens

Implementadas no M4 (0.0.7).

- Modelo: `Documento.paragrafos` passou a ser a lista de blocos do corpo, `Paragrafo` ou
  `Tabela` (o nome do campo ficou o do M2). `Tabela` tem a grade (`colunas_tw`), linhas e
  células; a célula tem os seus próprios blocos e pode ter outra tabela. A mescla segue o
  `.docx`: `colunas` é o `gridSpan`, e `mescla_vertical` é `inicio` ou `continua` (o `vMerge`).
- Imagem na linha: um `Run` com `imagem` e o texto U+FFFC (o mesmo caractere que o Qt usa). Os
  bytes são os do arquivo, sem recodificar; o tamanho fica em EMU.
- Ponte Qt: a tabela vira `QTextTable` com borda colapsada, largura fixa por coluna e
  `rowSpan`/`columnSpan`. O que o Qt não guarda (bordas do arquivo, sombreamento, altura da
  linha, largura `tblW`) vai em JSON numa propriedade de usuário do formato da tabela e da
  célula, e volta igual. A borda que aparece na tela é recalculada pela posição da célula
  (`aplicar_formatos_das_celulas`) a cada mudança na grade.
- O Qt exige um bloco antes e depois de cada tabela. O bloco que o modelo não tem (tabela no
  começo do documento ou da célula, duas tabelas seguidas) leva a marca `PROP_ESTRUTURAL` e,
  vazio, não volta para o modelo. Na tela ele aparece como uma linha vazia.
- Imagem no Qt: o recurso do documento é uma prévia (no máximo 1800 px no lado maior); os bytes
  ficam num registro por conteúdo (`ponte_qt/imagens.py`), porque o Qt troca o recurso pela
  imagem decodificada depois de desenhar. O `DocumentoQt` busca no registro a imagem colada de
  outra janela e nunca lê recurso de arquivo nem de rede.
- Escrita: toda tabela usa o estilo "Table Grid" (espaçamento zero dentro da célula, como no
  Word) e grava os seis lados da borda. Célula e corpo sempre terminam em parágrafo.

Limites: o Qt refaz o layout da tabela inteira a cada tecla (cerca de 0,06 ms por célula,
medido; ver docs/SPIKES.md). Por isso o leitor transforma em parágrafos, com aviso, a tabela
acima de 2000 linhas, 63 colunas ou 5000 células, ou aninhada mais de 4 níveis. Imagem
flutuante (`wp:anchor`) vira imagem na linha, com aviso; o posicionamento flutuante fica para
depois da 0.1.0 (formas e caixas de texto).

## Estilos e formatação

- O estilo nomeado fica numa propriedade de usuário do bloco ou do fragmento.
- A formatação efetiva é gravada nos formatos do Qt. No salvamento, o que
  difere do estilo vira formatação direta.
- "Atualizar estilo" troca, em um único passo de desfazer, o que ainda era igual
  ao estilo antigo.
- O Word grava nomes canônicos em inglês (`heading 1`); o mapeamento usa o nome,
  não o id, porque o id em pt-BR vem sem acento.

## Política de perda

Cada recurso do `.docx` é exato, aproximado ou descartado com aviso. Se algo
que se perderia ao salvar estiver presente, a primeira gravação pede
confirmação e oferece "Salvar cópia". Comentários, revisões e notas de rodapé
entram aqui até as versões que os implementam.

## Ribbon

Ribbon próprio, com `QTabBar`, grupos e botões criados a partir de `QAction`.
Não usa biblioteca de terceiros: a `pyqtribbon` encontrada é de um mantenedor
e está em beta, e o colapso e a galeria de estilos teriam de ser contornados.
Reavaliar só se o ribbon próprio estourar o marco de faixa.

## Marcos

| Marco | Versão | Entrega |
|---|---|---|
| M0 Esqueleto | 0.0.1 (renomeado em 0.0.2) | repositório, build, testes e fumaça do `.exe` |
| M1 Editor básico | 0.0.4 (feito) | visão provisória, faixa com colapso, formatação, desfazer, localizar |
| M2 `.docx` de texto | 0.0.5 (feito) | abrir e salvar parágrafos, runs, listas simples; gravação atômica |
| M3 Visão em páginas | 0.0.6 (feito) | A4, Carta, Ofício, margens, régua, quebras, zoom, Página X de Y |
| M4 Tabelas e imagens | 0.0.7 (feito) | tabela e imagem inline, no `.docx` e na visão |
| M5 Cabeçalho e rodapé | 0.0.8 | edição no lugar, número de página |
| M6 Estilos e faixa final | 0.0.9 | galeria, aba Exibir e abas contextuais de tabela e imagem |
| M7 Impressão e PDF | 0.0.10 | imprimir, pré-visualizar, exportar PDF |
| M8 Polimento | 0.1.0 | recuperação automática, preferências, acessibilidade, documentação final |

Caminho crítico: M1, M2 e M3. Antes do M3, um spike de página valida o controle
de texto próprio; se a tecla morta ou a IME falharem, o plano B é uma visão em
modo contínuo, com paginação só na impressão.

## Fora da 0.1.0

Revisão com controle de alterações, comentários, notas de rodapé, índices e
sumários, mala direta, equações, formas, caixas de texto, colunas, seções
múltiplas editáveis, ortografia (prevista para a 0.2 pela API do Windows),
`.doc`, RTF, ODT e macros (nunca).

## Riscos abertos

1. Espaçamento entre parágrafos: o Qt colapsa margens verticais para o maior
   valor, e o Word, ao que tudo indica, soma. Mede-se no M3.
2. O Word pode reclamar de um `.docx` gerado sem ser visto. Mitigação: vocabulário
   conservador, validação de ordem dos elementos, releitura antes da troca, e um
   protocolo de aceite manual com amostras.
3. Paginação diferente da do Word. Não se promete identidade de quebras.
