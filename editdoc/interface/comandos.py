"""Registro de comandos: cada acao da faixa, do atalho e do menu e' um QAction daqui.

Regra do CLAUDE.md: nenhum botao tem logica propria. A faixa referencia a acao
criada aqui, e o atalho vem da mesma definicao. Por isso um atalho e um botao
nunca divergem.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QTextListFormat
from PySide6.QtWidgets import QTextEdit

from editdoc.edicao import cabecalhos as ed_cabecalhos
from editdoc.edicao import estilos as ed_estilos
from editdoc.edicao import formatacao, tabelas
from editdoc.edicao import listas as ed_listas
from editdoc.edicao import notas as ed_notas
from editdoc.modelo.folhas import passo_de_zoom


@dataclass(frozen=True)
class Definicao:
    id: str
    texto: str
    atalhos: tuple[str, ...] = ()
    marcavel: bool = False
    dica: str = ""


DEFINICOES = (
    Definicao("novo", "Novo", ("Ctrl+N",), dica="Novo documento"),
    Definicao("abrir", "Abrir", ("Ctrl+O",), dica="Abrir"),
    Definicao("salvar", "Salvar", ("Ctrl+S",), dica="Salvar"),
    Definicao("salvar_como", "Salvar como", ("F12", "Ctrl+Shift+S"), dica="Salvar como"),
    Definicao("fechar", "Fechar", ("Ctrl+W",), dica="Fechar documento"),
    # Impressao e PDF (M7).
    Definicao("imprimir", "Imprimir...", ("Ctrl+P",), dica="Imprimir"),
    Definicao("visualizar_impressao", "Visualizar impressão", ("Ctrl+F2",),
              dica="Ver as páginas como serão impressas"),
    Definicao("exportar_pdf", "PDF...", (), dica="Exportar o documento como PDF"),
    Definicao("exportar_txt", "Texto sem formatação (.txt)...", (),
              dica="Exportar só o texto do documento"),
    # Recursos que o documento tem e o EditDoc nao edita (0.1.19): a faixa so' mostra a perda.
    Definicao("objetos_preservados", "Objetos preservados...", (),
              dica="Lista dos recursos do documento que o EditDoc não edita"),
    # Preferencias e recuperacao (M8).
    Definicao("opcoes", "Opções...", (), dica="Preferências do EditDoc"),
    Definicao("recuperar", "Recuperar documentos...", (),
              dica="Abrir as cópias da recuperação automática que sobraram de uma queda"),
    Definicao("desfazer", "Desfazer", ("Ctrl+Z",), dica="Desfazer"),
    Definicao("refazer", "Refazer", ("Ctrl+Y", "Ctrl+Shift+Z"), dica="Refazer"),
    Definicao("recortar", "Recortar", ("Ctrl+X",), dica="Recortar"),
    Definicao("copiar", "Copiar", ("Ctrl+C",), dica="Copiar"),
    Definicao("colar", "Colar", ("Ctrl+V",), dica="Colar"),
    Definicao("selecionar_tudo", "Selecionar tudo", ("Ctrl+A",), dica="Selecionar tudo"),
    Definicao("localizar", "Localizar", ("Ctrl+F",), dica="Localizar"),
    Definicao("substituir", "Substituir", ("Ctrl+H",), dica="Substituir"),
    Definicao("negrito", "N", ("Ctrl+B",), True, "Negrito"),
    Definicao("italico", "I", ("Ctrl+I",), True, "Itálico"),
    Definicao("sublinhado", "S", ("Ctrl+U",), True, "Sublinhado"),
    Definicao("tachado", "Tachado", (), True, "Tachado"),
    Definicao("subscrito", "X₂", ("Ctrl+=",), True, "Subscrito"),
    Definicao("sobrescrito", "X²", ("Ctrl+Shift+=",), True, "Sobrescrito"),
    Definicao("aumentar_fonte", "A▲", ("Ctrl+]",), dica="Aumentar fonte"),
    Definicao("diminuir_fonte", "A▼", ("Ctrl+[",), dica="Diminuir fonte"),
    Definicao("limpar_formatacao", "Limpar toda a formatação", (),
              dica="Limpar toda a formatação: o parágrafo volta ao estilo Normal"),
    Definicao("limpar_caractere", "Limpar formatação de caractere", ("Ctrl+Space",),
              dica="O texto volta ao estilo do parágrafo"),
    Definicao("marcadores", "Marcadores", ("Ctrl+Shift+L",), True, "Marcadores"),
    Definicao("numeracao", "Numeração", (), True, "Numeração"),
    # Listas (0.1.4): galerias, varios niveis e o valor do numero.
    Definicao("marcador_redondo", "•  Redondo", (), dica="Marcador redondo"),
    Definicao("marcador_vazado", "○  Vazado", (), dica="Marcador vazado"),
    Definicao("marcador_quadrado", "▪  Quadrado", (), dica="Marcador quadrado"),
    Definicao("numero_decimal_ponto", "1.  2.  3.", (), dica="Numeração 1. 2. 3."),
    Definicao("numero_decimal_parentese", "1)  2)  3)", (), dica="Numeração 1) 2) 3)"),
    Definicao("numero_letra_minuscula", "a.  b.  c.", (), dica="Numeração a. b. c."),
    Definicao("numero_letra_maiuscula", "A.  B.  C.", (), dica="Numeração A. B. C."),
    Definicao("numero_romano_minusculo", "i.  ii.  iii.", (), dica="Numeração i. ii. iii."),
    Definicao("numero_romano_maiusculo", "I.  II.  III.", (), dica="Numeração I. II. III."),
    Definicao("multinivel_decimal", "1.  1.1.  1.1.1.", (), dica="Lista de vários níveis 1. 1.1. 1.1.1."),
    Definicao("multinivel_capitulo", "Capítulo 1 / Seção 1.1", (),
              dica="Lista de vários níveis Capítulo e Seção"),
    Definicao("multinivel_titulos", "Títulos numerados (1 / 1.1 / 1.1.1)", (),
              dica="Numerar os títulos: Título 1, Título 2 e Título 3 ligados à lista"),
    Definicao("reiniciar_numeracao", "Reiniciar em 1", (),
              dica="A numeração recomeça neste item"),
    Definicao("continuar_numeracao", "Continuar numeração", (),
              dica="Este item continua a numeração da lista anterior"),
    Definicao("definir_valor_numeracao", "Definir valor de numeração...", (),
              dica="Escolher o número deste item"),
    Definicao("diminuir_recuo", "Diminuir recuo", ("Ctrl+Shift+M",),
              dica="Diminuir recuo"),
    Definicao("aumentar_recuo", "Aumentar recuo", ("Ctrl+M",), dica="Aumentar recuo"),
    Definicao("alinhar_esquerda", "Esquerda", ("Ctrl+L",), True, "Alinhar à esquerda"),
    Definicao("centralizar", "Centro", ("Ctrl+E",), True, "Centralizar"),
    Definicao("alinhar_direita", "Direita", ("Ctrl+R",), True, "Alinhar à direita"),
    Definicao("justificar", "Justificado", ("Ctrl+J",), True, "Justificar"),
    Definicao("espaco_1", "1,0", ("Ctrl+1",), True, "Espaçamento 1,0"),
    Definicao("espaco_115", "1,15", (), True, "Espaçamento 1,15"),
    Definicao("espaco_15", "1,5", ("Ctrl+5",), True, "Espaçamento 1,5"),
    Definicao("espaco_2", "2,0", ("Ctrl+2",), True, "Espaçamento 2,0"),
    Definicao("quebra_pagina", "Quebra de página", ("Ctrl+Return", "Ctrl+Enter"),
              dica="Quebra de página"),
    # Secoes (0.1.12): Layout > Quebras > Quebra de secao.
    Definicao("quebra_secao_proxima", "Próxima página", (),
              dica="Quebra de seção: a nova seção começa na próxima página"),
    Definicao("quebra_secao_continua", "Contínua", (),
              dica="Quebra de seção contínua: a nova seção começa na mesma página"),
    Definicao("quebra_secao_par", "Página par", (),
              dica="Quebra de seção: a nova seção começa na próxima página par"),
    Definicao("quebra_secao_impar", "Página ímpar", (),
              dica="Quebra de seção: a nova seção começa na próxima página ímpar"),
    Definicao("ampliar", "Ampliar", (), dica="Ampliar o zoom"),
    Definicao("reduzir", "Reduzir", (), dica="Reduzir o zoom"),
    Definicao("papel_a4", "A4", (), True, "Papel A4"),
    Definicao("papel_carta", "Carta", (), True, "Papel Carta"),
    Definicao("papel_oficio", "Ofício", (), True, "Papel Ofício"),
    Definicao("retrato", "Retrato", (), True, "Orientação retrato"),
    Definicao("paisagem", "Paisagem", (), True, "Orientação paisagem"),
    Definicao("margens_normal", "Normal", (), True, "Margens normais (2,54 cm)"),
    Definicao("margens_estreita", "Estreita", (), True, "Margens estreitas (1,27 cm)"),
    Definicao("margens_moderada", "Moderada", (), True, "Margens moderadas"),
    Definicao("margens_larga", "Larga", (), True, "Margens largas"),
    Definicao("margens_personalizadas", "Personalizadas...", (), True,
              "Margens personalizadas"),
    # Inserir (M4): tabela e imagem.
    Definicao("inserir_tabela", "Inserir tabela...", (), dica="Inserir tabela"),
    Definicao("inserir_linha_acima", "Inserir linha acima", (), dica="Inserir linha acima"),
    Definicao("inserir_linha_abaixo", "Inserir linha abaixo", (), dica="Inserir linha abaixo"),
    Definicao("inserir_coluna_esquerda", "Inserir coluna à esquerda", (),
              dica="Inserir coluna à esquerda"),
    Definicao("inserir_coluna_direita", "Inserir coluna à direita", (),
              dica="Inserir coluna à direita"),
    Definicao("excluir_linha", "Excluir linha", (), dica="Excluir as linhas da seleção"),
    Definicao("excluir_coluna", "Excluir coluna", (), dica="Excluir as colunas da seleção"),
    Definicao("excluir_tabela", "Excluir tabela", (), dica="Excluir a tabela inteira"),
    Definicao("mesclar_celulas", "Mesclar células", (), dica="Mesclar as células selecionadas"),
    Definicao("dividir_celula", "Dividir células", (), dica="Desfazer a mescla da célula"),
    Definicao("inserir_imagem", "Imagem...", (), dica="Inserir imagem de um arquivo"),
    Definicao("tamanho_imagem", "Tamanho da imagem...", (), dica="Tamanho da imagem em centímetros"),
    # Objetos (0.1.9): posicao, tamanho e quebra de texto do objeto selecionado.
    Definicao("posicao_tamanho", "Posição e tamanho...", (),
              dica="Posição na página, tamanho e quebra de texto do objeto selecionado"),
    Definicao("quebra_linha", "Alinhado ao texto", (), True,
              "O objeto fica na linha do texto, como uma letra"),
    Definicao("quebra_quadrado", "Quadrado", (), True, "O texto contorna o objeto pelo retângulo"),
    Definicao("quebra_comprimido", "Comprimido", (), True,
              "O texto contorna o objeto bem perto (como Quadrado nesta versão)"),
    Definicao("quebra_atraves", "Através", (), True,
              "O texto passa pelos vãos do objeto (como Quadrado nesta versão)"),
    Definicao("quebra_superior_inferior", "Superior e inferior", (), True,
              "O texto fica acima e abaixo do objeto, nunca ao lado"),
    Definicao("quebra_atras", "Atrás do texto", (), True, "O objeto fica atrás do texto"),
    Definicao("quebra_frente", "Na frente do texto", (), True, "O objeto fica na frente do texto"),
    # Hiperlinks (0.1.3).
    Definicao("inserir_link", "Link...", ("Ctrl+K",),
              dica="Inserir ou editar link (endereço ou marcador do documento)"),
    Definicao("remover_link", "Remover link", (), dica="Tirar o link do texto, que fica"),
    Definicao("abrir_link", "Abrir link", (), dica="Abrir o link do cursor (ou Ctrl+clique)"),
    # Cabecalho, rodape e numero de pagina (M5).
    Definicao("editar_cabecalho", "Editar cabeçalho", (),
              dica="Editar o cabeçalho (ou dê um duplo clique no alto da página)"),
    Definicao("editar_rodape", "Editar rodapé", (),
              dica="Editar o rodapé (ou dê um duplo clique no pé da página)"),
    Definicao("remover_cabecalho", "Remover cabeçalho", (), dica="Apagar o conteúdo do cabeçalho"),
    Definicao("remover_rodape", "Remover rodapé", (), dica="Apagar o conteúdo do rodapé"),
    Definicao("numero_topo_esquerda", "Início da página, à esquerda", (),
              dica="Número da página no cabeçalho, à esquerda"),
    Definicao("numero_topo_centro", "Início da página, centralizado", (),
              dica="Número da página no cabeçalho, centralizado"),
    Definicao("numero_topo_direita", "Início da página, à direita", (),
              dica="Número da página no cabeçalho, à direita"),
    Definicao("numero_rodape_esquerda", "Fim da página, à esquerda", (),
              dica="Número da página no rodapé, à esquerda"),
    Definicao("numero_rodape_centro", "Fim da página, centralizado", (),
              dica="Número da página no rodapé, centralizado"),
    Definicao("numero_rodape_direita", "Fim da página, à direita", (),
              dica="Número da página no rodapé, à direita"),
    Definicao("numero_x_de_y", "Página X de Y (fim da página, centralizado)", (),
              dica="\"Página 1 de 5\" no rodapé"),
    Definicao("campo_pagina", "Número da página atual, no cursor", (),
              dica="Inserir o número da página no ponto do cursor"),
    Definicao("campo_total", "Total de páginas, no cursor", (),
              dica="Inserir o total de páginas no ponto do cursor"),
    Definicao("formato_decimal", "1, 2, 3", (), True, "Números arábicos"),
    Definicao("formato_romano", "i, ii, iii", (), True, "Romanos minúsculos"),
    Definicao("formato_romano_maiusculo", "I, II, III", (), True, "Romanos maiúsculos"),
    Definicao("formato_letra", "a, b, c", (), True, "Letras minúsculas"),
    Definicao("formato_letra_maiuscula", "A, B, C", (), True, "Letras maiúsculas"),
    Definicao("numero_inicial", "Começar a numeração em...", (),
              dica="Número da primeira página"),
    Definicao("primeira_diferente", "Primeira página diferente", (), True,
              "Cabeçalho e rodapé próprios na primeira página"),
    Definicao("pares_impares", "Páginas pares e ímpares diferentes", (), True,
              "Cabeçalho e rodapé próprios nas páginas pares"),
    Definicao("vincular_anterior", "Vincular ao anterior", (), True,
              "Usar o cabeçalho (ou rodapé) da seção anterior nesta seção"),
    Definicao("ir_cabecalho", "Ir para o cabeçalho", (), dica="Ir para o cabeçalho"),
    Definicao("ir_rodape", "Ir para o rodapé", (), dica="Ir para o rodapé"),
    Definicao("fechar_cabecalho", "Fechar cabeçalho e rodapé", (),
              dica="Voltar ao corpo do documento (Esc)"),
    # Estilos (M6).
    Definicao("estilo_normal", "Normal", ("Ctrl+Shift+N",), dica="Aplicar o estilo Normal"),
    Definicao("estilo_titulo1", "Título 1", ("Ctrl+Alt+1",), dica="Aplicar o estilo Título 1"),
    Definicao("estilo_titulo2", "Título 2", ("Ctrl+Alt+2",), dica="Aplicar o estilo Título 2"),
    Definicao("estilo_titulo3", "Título 3", ("Ctrl+Alt+3",), dica="Aplicar o estilo Título 3"),
    Definicao("criar_estilo", "Criar um estilo...", (),
              dica="Criar um estilo com a formatação da seleção"),
    Definicao("modificar_estilo", "Modificar estilo...", (),
              dica="Modificar o estilo do parágrafo atual"),
    Definicao("atualizar_estilo", "Atualizar estilo para corresponder à seleção", (),
              dica="O estilo do parágrafo passa a ter a formatação da seleção"),
    Definicao("painel_estilos", "Painel de estilos", ("Ctrl+Alt+Shift+S",), True,
              "Mostrar a lista completa de estilos"),
    # Exibir (M6).
    Definicao("mostrar_regua", "Régua", (), True, "Mostrar a régua"),
    Definicao("painel_navegacao", "Painel de Navegação", (), True,
              "Mostrar os títulos do documento"),
    Definicao("marcas_formatacao", "¶", ("Ctrl+Shift+8", "Ctrl+*", "Ctrl+Shift+*"), True,
              "Mostrar marcas de formatação (¶, espaços e tabulações)"),
    Definicao("zoom_100", "100%", (), dica="Zoom em 100%"),
    Definicao("zoom_pagina", "Uma Página", (), dica="A página inteira na janela"),
    Definicao("zoom_varias", "Várias Páginas", (), dica="Duas páginas lado a lado"),
    Definicao("zoom_largura", "Largura da Página", (), dica="A largura da página na janela"),
    # Revisao: comentarios (0.1.6).
    Definicao("novo_comentario", "Novo comentário", ("Ctrl+Alt+M",),
              dica="Novo comentário sobre a seleção"),
    Definicao("responder_comentario", "Responder", (),
              dica="Responder ao comentário do cursor"),
    Definicao("editar_comentario", "Editar comentário...", (),
              dica="Editar o texto do comentário do cursor"),
    Definicao("resolver_comentario", "Resolver", (), True,
              "Marcar a conversa do comentário como resolvida (ou reabrir)"),
    Definicao("excluir_comentario", "Excluir", (),
              dica="Excluir o comentário do cursor e as respostas"),
    Definicao("excluir_todos_comentarios", "Excluir todos os comentários", (),
              dica="Excluir todos os comentários do documento"),
    Definicao("comentario_anterior", "Anterior", (), dica="Ir para o comentário anterior"),
    Definicao("comentario_proximo", "Próximo", (), dica="Ir para o próximo comentário"),
    Definicao("mostrar_comentarios", "Mostrar comentários", (), True,
              "Mostrar o painel de comentários"),
    # Revisao: controle de alteracoes (0.1.13).
    Definicao("controlar_alteracoes", "Controlar alterações", ("Ctrl+Shift+E",), True,
              "Controlar alterações: registrar inserções, exclusões e formatação"),
    Definicao("modo_simples", "Marcação simples", (), True,
              "Mostrar o texto final com uma barra onde houve alteração"),
    Definicao("modo_todas", "Toda a marcação", (), True,
              "Mostrar inserções sublinhadas e exclusões tachadas, na cor de cada autor"),
    Definicao("modo_sem", "Sem marcação", (), True,
              "Mostrar o texto final, sem as marcas das alterações"),
    Definicao("modo_original", "Original", (), True,
              "Mostrar o texto como era antes das alterações"),
    Definicao("imprimir_marcacoes", "Imprimir marcações", (), True,
              "Imprimir e exportar o PDF com as alterações e os comentários"),
    Definicao("aceitar_revisao", "Aceitar", (),
              dica="Aceitar a alteração do cursor (ou as da seleção) e ir para a próxima"),
    Definicao("aceitar_todas", "Aceitar todas as alterações", (),
              dica="Aceitar todas as alterações do documento"),
    Definicao("aceitar_do_autor", "Aceitar todas de um autor...", (),
              dica="Aceitar todas as alterações de um autor"),
    Definicao("rejeitar_revisao", "Rejeitar", (),
              dica="Rejeitar a alteração do cursor (ou as da seleção) e ir para a próxima"),
    Definicao("rejeitar_todas", "Rejeitar todas as alterações", (),
              dica="Rejeitar todas as alterações do documento"),
    Definicao("rejeitar_do_autor", "Rejeitar todas de um autor...", (),
              dica="Rejeitar todas as alterações de um autor"),
    Definicao("revisao_anterior", "Anterior", (), dica="Ir para a alteração anterior"),
    Definicao("revisao_proxima", "Próxima", (), dica="Ir para a próxima alteração"),
    Definicao("painel_revisoes", "Painel de revisões", (), True,
              "Mostrar a lista de alterações do documento"),
    # Referencias: notas de rodape e de fim (0.1.10).
    Definicao("inserir_nota_rodape", "Inserir nota de rodapé", ("Ctrl+Alt+F",),
              dica="Inserir nota de rodapé no cursor"),
    Definicao("inserir_nota_fim", "Inserir nota de fim", ("Ctrl+Alt+D",),
              dica="Inserir nota de fim no cursor"),
    Definicao("proxima_nota", "Próxima nota", (), dica="Ir para a próxima nota de rodapé ou de fim"),
    Definicao("nota_anterior", "Nota anterior", (),
              dica="Ir para a nota de rodapé ou de fim anterior"),
    Definicao("opcoes_notas", "Opções de notas...", (),
              dica="Formato, início, reinício e posição das notas; converter rodapé e fim"),
)

#: Estilos que os atalhos aplicam: id da acao -> nome canonico do Word.
ESTILO_DAS_ACOES = {"estilo_normal": "normal", "estilo_titulo1": "heading 1",
                    "estilo_titulo2": "heading 2", "estilo_titulo3": "heading 3"}
#: Zoom do Exibir: id da acao -> modo de VistaPaginas.zoom_modo.
ZOOM_DAS_ACOES = {"zoom_100": "100", "zoom_pagina": "pagina", "zoom_varias": "varias",
                  "zoom_largura": "largura"}

#: Numero de pagina: id da acao -> (onde, alinhamento, "Pagina X de Y").
NUMERO_DAS_ACOES = {
    "numero_topo_esquerda": ("cabecalho", "esquerda", False),
    "numero_topo_centro": ("cabecalho", "centro", False),
    "numero_topo_direita": ("cabecalho", "direita", False),
    "numero_rodape_esquerda": ("rodape", "esquerda", False),
    "numero_rodape_centro": ("rodape", "centro", False),
    "numero_rodape_direita": ("rodape", "direita", False),
    "numero_x_de_y": ("rodape", "centro", True),
}
#: Formato do numero da pagina: id da acao -> w:pgNumType w:fmt.
FORMATO_DAS_ACOES = {"formato_decimal": "decimal", "formato_romano": "lowerRoman",
                     "formato_romano_maiusculo": "upperRoman", "formato_letra": "lowerLetter",
                     "formato_letra_maiuscula": "upperLetter"}
#: Comandos que so' valem durante a edicao do cabecalho e do rodape.
EDICAO_DE_FAIXA = ("ir_cabecalho", "ir_rodape", "fechar_cabecalho")

#: Comandos que so' valem com o cursor numa tabela (o atualizador os habilita).
TABELA = ("inserir_linha_acima", "inserir_linha_abaixo", "inserir_coluna_esquerda",
          "inserir_coluna_direita", "excluir_linha", "excluir_coluna", "excluir_tabela",
          "mesclar_celulas", "dividir_celula")

#: Quebra de texto (0.1.9): id da acao -> quebra de `formato_docx/posicao.py`.
QUEBRA_DAS_ACOES = {"quebra_linha": "linha", "quebra_quadrado": "quadrado",
                    "quebra_comprimido": "comprimido", "quebra_atraves": "atraves",
                    "quebra_superior_inferior": "superior_inferior", "quebra_atras": "atras",
                    "quebra_frente": "frente"}
#: Comandos que so' valem com um objeto selecionado (o atualizador os habilita).
OBJETO = ("posicao_tamanho", *QUEBRA_DAS_ACOES)

#: Comandos que so' valem com o cursor num link (o atualizador os habilita).
LINK = ("remover_link", "abrir_link")

#: Comandos que so' valem com o cursor num trecho comentado (0.1.6, o atualizador os habilita).
COMENTARIO = ("responder_comentario", "editar_comentario", "resolver_comentario",
              "excluir_comentario")
#: Comentarios (0.1.6): id da acao -> gancho da janela (os dialogos sao dela).
REVISAO_DAS_ACOES = {"novo_comentario": "novo", "responder_comentario": "responder",
                     "editar_comentario": "editar", "resolver_comentario": "resolver",
                     "excluir_comentario": "excluir", "excluir_todos_comentarios": "excluir_todos",
                     "comentario_anterior": "anterior", "comentario_proximo": "proximo",
                     "mostrar_comentarios": "mostrar",
                     # Controle de alteracoes (0.1.13).
                     "controlar_alteracoes": "controlar", "imprimir_marcacoes": "imprimir_marcas",
                     "aceitar_revisao": "aceitar", "aceitar_todas": "aceitar_todas",
                     "aceitar_do_autor": "aceitar_autor", "rejeitar_revisao": "rejeitar",
                     "rejeitar_todas": "rejeitar_todas", "rejeitar_do_autor": "rejeitar_autor",
                     "revisao_anterior": "revisao_anterior", "revisao_proxima": "revisao_proxima",
                     "painel_revisoes": "painel_revisoes"}
#: Modos de exibicao das revisoes (0.1.13): id da acao -> modo de `modelo/revisoes.py`.
MODO_DAS_ACOES = {"modo_simples": "simples", "modo_todas": "todas", "modo_sem": "final",
                  "modo_original": "original"}
#: Comandos que so' valem com o cursor numa alteracao (o atualizador os habilita).
REVISAO = ("aceitar_revisao", "rejeitar_revisao")

#: Comandos que so' valem com o cursor num item numerado (o atualizador os habilita).
LISTA_NUMERADA = ("reiniciar_numeracao", "continuar_numeracao", "definir_valor_numeracao")
#: Galerias de lista (0.1.4): id da acao -> (funcao de edicao/listas, chave da galeria).
GALERIA_DAS_ACOES = {
    "marcador_redondo": ("alternar_marcadores", "redondo"),
    "marcador_vazado": ("alternar_marcadores", "vazado"),
    "marcador_quadrado": ("alternar_marcadores", "quadrado"),
    "numero_decimal_ponto": ("alternar_numeracao", "decimal_ponto"),
    "numero_decimal_parentese": ("alternar_numeracao", "decimal_parentese"),
    "numero_letra_minuscula": ("alternar_numeracao", "letra_minuscula"),
    "numero_letra_maiuscula": ("alternar_numeracao", "letra_maiuscula"),
    "numero_romano_minusculo": ("alternar_numeracao", "romano_minusculo"),
    "numero_romano_maiusculo": ("alternar_numeracao", "romano_maiusculo"),
    "multinivel_decimal": ("aplicar_multinivel", "decimal"),
    "multinivel_capitulo": ("aplicar_multinivel", "capitulo"),
    "multinivel_titulos": ("aplicar_multinivel", "titulos"),
}

#: Quebra de secao (0.1.12): id da acao -> w:type da secao que comeca depois da quebra.
QUEBRA_DE_SECAO_DAS_ACOES = {"quebra_secao_proxima": "nextPage",
                             "quebra_secao_continua": "continuous",
                             "quebra_secao_par": "evenPage", "quebra_secao_impar": "oddPage"}
#: Papel: id da acao -> nome do papel em editdoc/modelo/pagina.py (PAPEIS).
PAPEL_DAS_ACOES = {"papel_a4": "A4", "papel_carta": "Carta", "papel_oficio": "Ofício"}
#: Margens: id da acao -> predefinicao. "personalizadas" abre o dialogo.
MARGENS_DAS_ACOES = {"margens_normal": "Normal", "margens_estreita": "Estreita",
                     "margens_moderada": "Moderada", "margens_larga": "Larga",
                     "margens_personalizadas": "Personalizadas"}

ALINHAMENTOS = {
    "alinhar_esquerda": Qt.AlignmentFlag.AlignLeft,
    "centralizar": Qt.AlignmentFlag.AlignHCenter,
    "alinhar_direita": Qt.AlignmentFlag.AlignRight,
    "justificar": Qt.AlignmentFlag.AlignJustify,
}

ESPACAMENTOS = {"espaco_1": 100, "espaco_115": 115, "espaco_15": 150, "espaco_2": 200}


#: Comandos de formatacao que, com o controle de alteracoes ligado (0.1.13), guardam a
#: formatacao de antes (w:rPrChange e w:pPrChange). A fonte e o tamanho passam pela
#: `formatacao._aplicar_caractere`, que faz o mesmo.
FORMATACAO_RASTREADA = {
    "negrito", "italico", "sublinhado", "tachado", "subscrito", "sobrescrito", "aumentar_fonte",
    "diminuir_fonte", "limpar_formatacao", "limpar_caractere", "marcadores", "numeracao",
    "diminuir_recuo", "aumentar_recuo", "alinhar_esquerda", "centralizar", "alinhar_direita",
    "justificar", "espaco_1", "espaco_115", "espaco_15", "espaco_2", "marcador_redondo",
    "marcador_vazado", "marcador_quadrado", "numero_decimal_ponto", "numero_decimal_parentese",
    "numero_letra_minuscula", "numero_letra_maiuscula", "numero_romano_minusculo",
    "numero_romano_maiusculo", "multinivel_decimal", "multinivel_capitulo", "multinivel_titulos",
    "estilo_normal", "estilo_titulo1", "estilo_titulo2", "estilo_titulo3",
}

#: Comandos de arquivo: quem os executa e' a janela. Ver `ao_arquivo` em Comandos.
ARQUIVO = ("novo", "abrir", "salvar", "salvar_como", "fechar", "imprimir",
           "visualizar_impressao", "exportar_pdf", "exportar_txt", "objetos_preservados",
           "opcoes", "recuperar")


def _nada() -> None:
    return None


def _chamar(ganchos: dict[str, Callable], chave: str, *args) -> None:
    """Chama o gancho da janela, se houver. Sem janela (testes), nao faz nada."""
    gancho = ganchos.get(chave)
    if gancho is not None:
        gancho(*args)


def _quebra(editor, quebra: str) -> None:
    """Quebra de texto do objeto selecionado (0.1.9). Sem objeto (ou editor sem o recurso), nada."""
    definir = getattr(editor, "definir_quebra_do_selecionado", None)
    if definir is not None:
        definir(quebra)


def _continuar(editor) -> None:
    if not ed_listas.continuar(editor) and hasattr(editor, "mensagem"):
        editor.mensagem.emit("Não há lista anterior com o mesmo formato para continuar.")


def _executores(editor: QTextEdit, ao_localizar: Callable[[], None],
                ao_substituir: Callable[[], None],
                ao_arquivo: dict[str, Callable[[], None]],
                ao_layout: dict[str, Callable] | None = None,
                ao_inserir: dict[str, Callable] | None = None,
                ao_exibir: dict[str, Callable] | None = None,
                ao_revisao: dict[str, Callable] | None = None) -> dict[str, Callable[[], None]]:
    fmt = formatacao
    layout = ao_layout or {}
    inserir = ao_inserir or {}
    exibir = ao_exibir or {}
    revisao = ao_revisao or {}
    executores_inserir: dict[str, Callable[[], None]] = {
        # Os dialogos (tamanho da tabela, arquivo de imagem, tamanho da imagem) sao da janela.
        "inserir_tabela": lambda: _chamar(inserir, "tabela"),
        "inserir_imagem": lambda: _chamar(inserir, "imagem"),
        "tamanho_imagem": lambda: _chamar(inserir, "tamanho_imagem"),
        "posicao_tamanho": lambda: _chamar(inserir, "posicao_tamanho"),
        "inserir_link": lambda: _chamar(inserir, "link"),
        "remover_link": lambda: _chamar(inserir, "remover_link"),
        "abrir_link": lambda: _chamar(inserir, "abrir_link"),
        "inserir_linha_acima": lambda: tabelas.inserir_linha(editor, abaixo=False),
        "inserir_linha_abaixo": lambda: tabelas.inserir_linha(editor, abaixo=True),
        "inserir_coluna_esquerda": lambda: tabelas.inserir_coluna(editor, direita=False),
        "inserir_coluna_direita": lambda: tabelas.inserir_coluna(editor, direita=True),
        "excluir_linha": lambda: tabelas.excluir_linhas(editor),
        "excluir_coluna": lambda: tabelas.excluir_colunas(editor),
        "excluir_tabela": lambda: tabelas.excluir_tabela(editor),
        "mesclar_celulas": lambda: tabelas.mesclar_celulas(editor),
        "dividir_celula": lambda: tabelas.dividir_celula(editor),
        # Cabecalho e rodape (M5).
        "editar_cabecalho": lambda: editor.entrar_na_faixa("cabecalho"),
        "editar_rodape": lambda: editor.entrar_na_faixa("rodape"),
        "ir_cabecalho": lambda: editor.entrar_na_faixa("cabecalho", editor.pagina_atual()),
        "ir_rodape": lambda: editor.entrar_na_faixa("rodape", editor.pagina_atual()),
        "fechar_cabecalho": editor.sair_da_faixa,
        "remover_cabecalho": lambda: ed_cabecalhos.remover(editor, "cabecalho"),
        "remover_rodape": lambda: ed_cabecalhos.remover(editor, "rodape"),
        "campo_pagina": lambda: ed_cabecalhos.inserir_campo_no_cursor(editor, "PAGE"),
        "campo_total": lambda: ed_cabecalhos.inserir_campo_no_cursor(editor, "NUMPAGES"),
        "numero_inicial": lambda: _chamar(layout, "numero_inicial"),
        "primeira_diferente": lambda: _chamar(layout, "primeira_diferente"),
        "pares_impares": lambda: _chamar(layout, "pares_impares"),
    }
    for id_, (onde, alinhamento, total) in NUMERO_DAS_ACOES.items():
        executores_inserir[id_] = (lambda o=onde, a=alinhamento, t=total:
                                   ed_cabecalhos.inserir_numero_de_pagina(editor, o, a, t))
    for id_, formato in FORMATO_DAS_ACOES.items():
        executores_inserir[id_] = lambda f=formato: _chamar(layout, "formato_numero", f)
    for id_, quebra in QUEBRA_DAS_ACOES.items():
        executores_inserir[id_] = lambda q=quebra: _quebra(editor, q)
    executores_layout: dict[str, Callable[[], None]] = {
        "quebra_pagina": editor.inserir_quebra_de_pagina,
        "ampliar": lambda: editor.definir_zoom(
            passo_de_zoom(editor.zoom(), True, editor.dpr())),
        "reduzir": lambda: editor.definir_zoom(
            passo_de_zoom(editor.zoom(), False, editor.dpr())),
        "retrato": lambda: _chamar(layout, "orientacao", False),
        "paisagem": lambda: _chamar(layout, "orientacao", True),
    }
    for id_, tipo in QUEBRA_DE_SECAO_DAS_ACOES.items():
        executores_layout[id_] = lambda t=tipo: editor.inserir_quebra_de_secao(t)
    executores_inserir["vincular_anterior"] = lambda: _chamar(layout, "vincular_anterior")
    for id_, nome in PAPEL_DAS_ACOES.items():
        executores_layout[id_] = lambda n=nome: _chamar(layout, "papel", n)
    for id_, nome in MARGENS_DAS_ACOES.items():
        executores_layout[id_] = lambda n=nome: _chamar(layout, "margens", n)
    executores: dict[str, Callable[[], None]] = {
        "desfazer": editor.undo,
        "refazer": editor.redo,
        "recortar": editor.cut,
        "copiar": editor.copy,
        "colar": editor.paste,
        "selecionar_tudo": editor.selectAll,
        "localizar": ao_localizar,
        "substituir": ao_substituir,
        "negrito": lambda: fmt.alternar_negrito(editor),
        "italico": lambda: fmt.alternar_italico(editor),
        "sublinhado": lambda: fmt.alternar_sublinhado(editor),
        "tachado": lambda: fmt.alternar_tachado(editor),
        "subscrito": lambda: fmt.alternar_subscrito(editor),
        "sobrescrito": lambda: fmt.alternar_sobrescrito(editor),
        "aumentar_fonte": lambda: fmt.alterar_tamanho(editor, 1),
        "diminuir_fonte": lambda: fmt.alterar_tamanho(editor, -1),
        "limpar_formatacao": lambda: fmt.limpar_formatacao(editor),
        "limpar_caractere": lambda: fmt.limpar_caractere(editor),
        # Estilos e Exibir (M6): dialogos, paineis e regua sao da janela.
        "criar_estilo": lambda: _chamar(exibir, "criar_estilo"),
        "modificar_estilo": lambda: _chamar(exibir, "modificar_estilo"),
        "atualizar_estilo": lambda: ed_estilos.atualizar_pela_selecao(editor),
        "painel_estilos": lambda: _chamar(exibir, "painel_estilos"),
        "mostrar_regua": lambda: _chamar(exibir, "regua"),
        "painel_navegacao": lambda: _chamar(exibir, "navegacao"),
        "marcas_formatacao": lambda: editor.definir_marcas(not editor.marcas_visiveis()),
        "marcadores": lambda: fmt.alternar_lista(editor, QTextListFormat.Style.ListDisc),
        "numeracao": lambda: fmt.alternar_lista(editor, QTextListFormat.Style.ListDecimal),
        # Num item de lista, o recuo muda o nivel (0.1.4).
        "diminuir_recuo": lambda: fmt.alterar_recuo_ou_nivel(editor, False),
        "aumentar_recuo": lambda: fmt.alterar_recuo_ou_nivel(editor, True),
        "reiniciar_numeracao": lambda: ed_listas.reiniciar(editor),
        "continuar_numeracao": lambda: _continuar(editor),
        "definir_valor_numeracao": lambda: _chamar(inserir, "valor_numeracao"),
    }
    for id_, (funcao, chave) in GALERIA_DAS_ACOES.items():
        executores[id_] = lambda f=funcao, c=chave: getattr(ed_listas, f)(editor, c)
    for id_, alinhamento in ALINHAMENTOS.items():
        executores[id_] = lambda a=alinhamento: fmt.alinhar(editor, a)
    for id_, percentual in ESPACAMENTOS.items():
        executores[id_] = lambda p=percentual: fmt.definir_espacamento(editor, p)
    for id_ in ARQUIVO:
        executores[id_] = ao_arquivo.get(id_, _nada)
    for id_, nome in ESTILO_DAS_ACOES.items():
        executores[id_] = lambda n=nome: ed_estilos.aplicar_estilo(editor, n)
    for id_, modo in ZOOM_DAS_ACOES.items():
        executores[id_] = lambda m=modo: editor.zoom_modo(m)
    executores.update(executores_layout)
    executores.update(executores_inserir)
    for id_, gancho in REVISAO_DAS_ACOES.items():
        executores[id_] = lambda g=gancho: _chamar(revisao, g)
    for id_, modo in MODO_DAS_ACOES.items():
        executores[id_] = lambda m=modo: _chamar(revisao, "modo", m)
    # Notas (0.1.10): o dialogo das opcoes e' da janela.
    executores["inserir_nota_rodape"] = lambda: ed_notas.inserir(editor, "rodape")
    executores["inserir_nota_fim"] = lambda: ed_notas.inserir(editor, "fim")
    executores["proxima_nota"] = lambda: ed_notas.proxima(editor)
    executores["nota_anterior"] = lambda: ed_notas.proxima(editor, anterior=True)
    executores["opcoes_notas"] = lambda: _chamar(inserir, "opcoes_notas")
    return executores


class Comandos(QObject):
    """Cria um QAction por definicao e liga cada um ao executor certo."""

    def __init__(self, pai: QObject, editor: QTextEdit,
                 ao_localizar: Callable[[], None],
                 ao_substituir: Callable[[], None],
                 ao_arquivo: dict[str, Callable[[], None]] | None = None,
                 ao_layout: dict[str, Callable] | None = None,
                 ao_inserir: dict[str, Callable] | None = None,
                 ao_exibir: dict[str, Callable] | None = None,
                 ao_revisao: dict[str, Callable] | None = None) -> None:
        super().__init__(pai)
        self._acoes: dict[str, QAction] = {}
        self._executores = _executores(editor, ao_localizar, ao_substituir, ao_arquivo or {},
                                       ao_layout, ao_inserir, ao_exibir, ao_revisao)
        self._editor = editor
        self._grupo_alinhamento = QActionGroup(self)
        self._grupo_alinhamento.setExclusive(True)
        self._grupo_espacamento = QActionGroup(self)
        self._grupo_espacamento.setExclusive(True)
        self._grupo_modo = QActionGroup(self)
        self._grupo_modo.setExclusive(True)

        for definicao in DEFINICOES:
            acao = QAction(definicao.texto, self)
            dica = definicao.dica or definicao.texto
            if definicao.atalhos:
                acao.setShortcuts([QKeySequence(s) for s in definicao.atalhos])
                dica = f"{dica} ({definicao.atalhos[0]})"
            acao.setToolTip(dica)
            acao.setStatusTip(dica)
            # Nome para o leitor de tela (M8): a dica sem o atalho, nunca o rotulo curto.
            acao.setProperty("nome_acessivel", definicao.dica or definicao.texto)
            acao.setCheckable(definicao.marcavel)
            acao.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            acao.triggered.connect(lambda _=False, i=definicao.id: self._executar(i))
            self._acoes[definicao.id] = acao
            if definicao.id in ALINHAMENTOS:
                self._grupo_alinhamento.addAction(acao)
            if definicao.id in ESPACAMENTOS:
                self._grupo_espacamento.addAction(acao)
            if definicao.id in MODO_DAS_ACOES:
                self._grupo_modo.addAction(acao)

    def _executar(self, id_: str) -> None:
        if id_ in FORMATACAO_RASTREADA:
            from editdoc.edicao.revisoes import registrando_formatacao
            with registrando_formatacao(self._editor):
                self._executores[id_]()
            return
        self._executores[id_]()

    def acao(self, id_: str) -> QAction:
        return self._acoes[id_]

    def todas(self) -> list[QAction]:
        return list(self._acoes.values())

    def atualizar_pagina(self, pagina) -> None:
        """Marca papel, orientacao e margens que valem para a pagina dada.

        Os grupos nao sao exclusivos: cada acao recebe o seu estado, para que um
        papel fora da lista (tamanho livre) nao deixe o anterior marcado.
        """
        nome_papel = pagina.nome_do_papel()
        for id_, nome in PAPEL_DAS_ACOES.items():
            self._acoes[id_].setChecked(nome == nome_papel)
        self._acoes["paisagem"].setChecked(pagina.paisagem)
        self._acoes["retrato"].setChecked(not pagina.paisagem)
        predefinicao = pagina.nome_das_margens()
        for id_, nome in MARGENS_DAS_ACOES.items():
            self._acoes[id_].setChecked(nome == predefinicao)
        self._acoes["primeira_diferente"].setChecked(pagina.primeira_diferente)
        self._acoes["pares_impares"].setChecked(pagina.pares_impares)
        for id_, formato in FORMATO_DAS_ACOES.items():
            self._acoes[id_].setChecked(formato == pagina.formato_numero)
