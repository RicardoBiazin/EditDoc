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

O `QTextEdit` não pagina: ao mostrar, força a largura e não deixa um vão entre
folhas. Por isso a visão é própria:

- um `QAbstractScrollArea` pinta as folhas;
- o `QTextDocument` tem `pageSize` igual ao **corpo** da página, com
  `documentMargin` zero, então o Qt quebra linhas pela altura do corpo;
- o caret, a seleção e o teclado são controlados por código próprio sobre o
  `QTextCursor`, porque `QWidgetTextControl` não existe no PySide6;
- o layout roda num dispositivo de referência a **1440 dpi**. Uma unidade de
  layout vira um twip, que é a unidade do `.docx`. Medido: a 96 dpi a contagem
  de páginas diverge do layout em alta resolução em cerca de 3%;
- tela, impressão, pré-visualização e PDF usam **uma** função de pintura de
  folha. O zoom é só uma escala.

Limites aceitos: o Qt não tem viúva e órfã, nem manter com o próximo; uma tabela
se divide entre páginas por linha, sem repetir a borda no corte; `\f` não quebra
página (usa-se a política de quebra do bloco).

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
| M0 Esqueleto | 0.0.1 | repositório, build, testes e fumaça do `.exe` |
| M1 Editor básico | 0.0.2 | visão provisória, faixa com colapso, formatação, desfazer, localizar |
| M2 `.docx` de texto | 0.0.3 | abrir e salvar parágrafos, runs, listas simples; gravação atômica |
| M3 Visão em páginas | 0.0.4 | A4, margens, régua, quebras, zoom |
| M4 Tabelas e imagens | 0.0.5 | tabela e imagem inline, no `.docx` e na visão |
| M5 Cabeçalho e rodapé | 0.0.6 | edição no lugar, número de página |
| M6 Estilos e faixa final | 0.0.7 | galeria, abas Inserir, Layout e Exibir |
| M7 Impressão e PDF | 0.0.8 | imprimir, pré-visualizar, exportar PDF |
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
