"""Avisos do leitor: o que o arquivo tem e o EditDoc nao entende. Sem Qt.

Regra: nada que o arquivo contem e' descartado em silencio. Cada recurso que o
programa nao modela gera um aviso, com a contagem, e `perde_ao_salvar` diz se
gravar de volta apaga aquilo do arquivo. Os avisos com `perde_ao_salvar` pedem
confirmacao antes de salvar.

Cada codigo aparece uma vez por documento, com a soma das ocorrencias.

Desde a 0.1.2, caixa de texto, forma, grafico, SmartArt, objeto OLE, equacao, imagem
flutuante e imagem em formato que a tela nao mostra sao preservados como objetos opacos
(`formato_docx/opacos.py`): os avisos deles sao sem perda. O que nao pode ser preservado
(referencia quebrada, limite) cai em OBJETO_PERDIDO ou IMAGEM, com perda.

Desde a 0.1.4 a numeracao de listas (numbering.xml inteiro, niveis, formatos, simbolos,
marcadores de figura, lista ligada ao estilo) volta ao arquivo: LISTA e LISTA_NIVEL so'
aparecem para referencia quebrada, nivel fora de 0 a 8 ou numeracao acima dos limites.

Desde a 0.1.6 os comentarios (comments.xml, respostas, resolvido, people.xml) e as
referencias a estilos que o styles.xml nao define voltam ao arquivo: COMENTARIO so' aparece
para comentario que nao pode ser lido (danificado, acima dos limites, sem referencia no
corpo), COMENTARIO_INCOMPLETO e' aviso de gravacao (o usuario apagou a referencia de um
comentario de um jeito que nao o levou junto), e ESTILO so' para id de estilo invalido ou
citado com outro tipo.

Desde a 0.1.3, hiperlinks, campos (DATE, REF, TOC...), marcadores e as partes do pacote
que o EditDoc nao edita (custom.xml, customXml, fontTable, webSettings, settings.xml) voltam
ao arquivo: HIPERLINK, CAMPO e PARTE_PERDIDA so' aparecem para o que nao pode voltar
(relacao quebrada, arquivo incompleto, limite). CAMPO_INCOMPLETO e' aviso de gravacao: o
usuario apagou o inicio ou o fim de um campo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Aviso:
    codigo: str
    texto: str
    contagem: int
    perde_ao_salvar: bool


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


#: codigo -> (modelo do texto com {n}, perde_ao_salvar). Texto em pt-BR, com acentos.
CATALOGO: dict[str, tuple] = {
    "TABELA": (
        lambda n: f"{n} {_plural(n, 'tabela foi convertida', 'tabelas foram convertidas')} "
                  "em parágrafos, por ser grande demais ou estar aninhada fundo demais. "
                  "A grade e as células se perdem ao salvar.",
        True),
    "IMAGEM": (
        lambda n: f"{n} {_plural(n, 'imagem não pôde ser lida', 'imagens não puderam ser lidas')} "
                  "(relação quebrada ou parte ausente no arquivo) e sai do arquivo ao salvar.",
        True),
    "IMAGEM_FORMATO": (
        lambda n: f"{n} {_plural(n, 'imagem não pode ser mostrada', 'imagens não podem ser mostradas')} "
                  "(vinculada a arquivo externo, danificada, grande demais ou em formato que o "
                  f"EditDoc não lê). {_plural(n, 'Ela é preservada', 'Elas são preservadas')} no "
                  f"arquivo e {_plural(n, 'aparece', 'aparecem')} como um quadro.",
        False),
    "IMAGEM_GRANDE": (
        lambda n: f"{n} {_plural(n, 'imagem é grande demais', 'imagens são grandes demais')} "
                  "para mostrar (mais de 64 megapixels) e aparece como um quadro cinza. "
                  "A imagem continua no arquivo ao salvar.",
        False),
    "IMAGEM_FLUTUANTE": (
        lambda n: f"{n} {_plural(n, 'imagem flutuante é preservada', 'imagens flutuantes são preservadas')} "
                  "com a posição e a disposição do texto em volta, mas não "
                  f"{_plural(n, 'pode ser editada', 'podem ser editadas')} nesta versão.",
        False),
    "QUEBRA_EM_TABELA": (
        lambda n: f"{n} {_plural(n, 'quebra de página dentro de tabela virou', 'quebras de página dentro de tabela viraram')} "
                  "quebra de linha.",
        True),
    "CELULA_ESCONDIDA": (
        lambda n: f"{n} {_plural(n, 'célula mesclada tinha', 'células mescladas tinham')} texto que o "
                  "Word esconde. Esse texto sai do arquivo ao salvar.",
        True),
    "CAIXA_DE_TEXTO": (
        lambda n: f"{n} {_plural(n, 'caixa de texto ou forma é preservada', 'caixas de texto ou formas são preservadas')}. "
                  "O texto de uma caixa de texto pode ser editado (duplo clique na caixa); "
                  "a forma em si (posição, tamanho, cor) e as formas sem texto não são editáveis nesta versão.",
        False),
    "OBJETO": (
        lambda n: f"{n} {_plural(n, 'objeto incorporado (gráfico, SmartArt ou objeto OLE) é preservado', 'objetos incorporados (gráficos, SmartArt ou objetos OLE) são preservados')}, "
                  f"mas não {_plural(n, 'pode ser editado', 'podem ser editados')} nesta versão.",
        False),
    "EQUACAO": (
        lambda n: f"{n} {_plural(n, 'equação é preservada', 'equações são preservadas')}, "
                  f"mas não {_plural(n, 'pode ser editada', 'podem ser editadas')} nesta versão.",
        False),
    "OBJETO_PERDIDO": (
        lambda n: f"{n} {_plural(n, 'caixa de texto, forma ou objeto não pôde ser preservado', 'caixas de texto, formas ou objetos não puderam ser preservados')} "
                  "(referência quebrada no arquivo ou acima dos limites do EditDoc) e "
                  f"{_plural(n, 'sai', 'saem')} do arquivo ao salvar.",
        True),
    "LISTA_EM_CAIXA": (
        lambda n: f"{n} {_plural(n, 'parágrafo numerado dentro de caixa de texto perde', 'parágrafos numerados dentro de caixas de texto perdem')} "
                  "a numeração ao salvar, porque a numeração do arquivo não pôde ser lida.",
        True),
    "CAMPO": (
        lambda n: f"{n} {_plural(n, 'campo não pôde ser preservado', 'campos não puderam ser preservados')} "
                  "(incompleto no arquivo ou acima dos limites do EditDoc) e "
                  f"{_plural(n, 'fica', 'ficam')} só com o último valor mostrado, como texto "
                  "fixo, ao salvar.",
        True),
    "CAMPO_INCOMPLETO": (
        lambda n: f"{n} {_plural(n, 'campo perdeu', 'campos perderam')} o início ou o fim na "
                  f"edição e {_plural(n, 'sai', 'saem')} do arquivo como texto comum.",
        True),
    "HIPERLINK": (
        lambda n: f"{n} {_plural(n, 'hiperlink aponta', 'hiperlinks apontam')} para endereço "
                  "que não existe no arquivo (ou acima dos limites do EditDoc). O texto fica, "
                  "mas o endereço se perde ao salvar.",
        True),
    "MARCADOR": (
        lambda n: f"{n} {_plural(n, 'marcador repetido ou acima dos limites sai', 'marcadores repetidos ou acima dos limites saem')} "
                  "do arquivo ao salvar.",
        True),
    "PARTE_PERDIDA": (
        lambda n: f"{n} {_plural(n, 'parte do arquivo (propriedades, dados ou configurações) não pôde ser preservada', 'partes do arquivo (propriedades, dados ou configurações) não puderam ser preservadas')} "
                  "(referência quebrada, conteúdo inválido ou acima dos limites) e "
                  f"{_plural(n, 'sai', 'saem')} do arquivo ao salvar.",
        True),
    "MINIATURA": (
        lambda n: "A miniatura de pré-visualização do arquivo não é mantida (mostraria o "
                  "conteúdo antigo). O Word gera outra quando salva.",
        False),
    "ASSINATURA": (
        lambda n: "O documento tem assinatura digital. Qualquer alteração a invalida, e ela "
                  "sai do arquivo ao salvar.",
        True),
    "QUEBRA_DE_PAGINA": (
        lambda n: f"{n} {_plural(n, 'quebra de coluna não é preservada', 'quebras de coluna não são preservadas')} "
                  "ao salvar.",
        True),
    "CABECALHO_RODAPE": (
        lambda n: f"{n} {_plural(n, 'cabeçalho ou rodapé não pôde ser lido', 'cabeçalhos ou rodapés não puderam ser lidos')} "
                  "(parte ausente, de tipo errado ou danificada) e sai do arquivo ao salvar.",
        True),
    "CABECALHO_SECAO": (
        lambda n: "O documento tem seções com cabeçalho ou rodapé próprios. O EditDoc mantém "
                  "só os da última seção, que passam a valer para o documento inteiro.",
        True),
    "CABECALHO_GRANDE": (
        lambda n: f"{n} {_plural(n, 'cabeçalho ou rodapé é grande demais', 'cabeçalhos ou rodapés são grandes demais')} "
                  "para abrir e sai do arquivo ao salvar.",
        True),
    "NUMERO_PAGINA": (
        lambda n: "O formato ou o número inicial da numeração de páginas não é mostrado pelo "
                  "EditDoc. A numeração sai como 1, 2, 3 ao salvar.",
        True),
    "SECAO": (
        lambda n: f"{n} {_plural(n, 'quebra de seção não é preservada', 'quebras de seção não são preservadas')}. "
                  "O arquivo sai com uma única seção.",
        True),
    "PAGINA": (
        lambda n: "O arquivo tem mais de uma seção. Cada seção tem o seu papel e as suas margens, "
                  "e o EditDoc mantém só as da última seção. O arquivo sai com uma única seção.",
        True),
    "PAPEL_INVALIDO": (
        lambda n: "O papel ou as margens do arquivo não cabem numa página útil. "
                  "O arquivo sai com o papel A4 e as margens padrão.",
        True),
    "COMENTARIO": (
        lambda n: f"{n} {_plural(n, 'comentário não pôde ser lido', 'comentários não puderam ser lidos')} "
                  "(danificado, sem referência no texto do corpo ou acima dos limites do EditDoc) e "
                  f"{_plural(n, 'sai', 'saem')} do arquivo ao salvar.",
        True),
    "COMENTARIO_INCOMPLETO": (
        lambda n: f"{n} {_plural(n, 'comentário perdeu', 'comentários perderam')} a marca de "
                  f"referência no texto e {_plural(n, 'sai', 'saem')} do arquivo ao salvar.",
        True),
    "REVISAO": (
        lambda n: f"{n} {_plural(n, 'alteração controlada foi aceita', 'alterações controladas foram aceitas')}: "
                  "as exclusões somem ao salvar.",
        True),
    "NOTA": (
        lambda n: f"{n} {_plural(n, 'nota de rodapé ou de fim não é editada', 'notas de rodapé ou de fim não são editadas')} "
                  "nesta versão e sai do arquivo ao salvar.",
        True),
    "CONTEUDO_CONTROLADO": (
        lambda n: f"{n} {_plural(n, 'controle de conteúdo não pôde ser preservado e foi achatado', 'controles de conteúdo não puderam ser preservados e foram achatados')} "
                  "(envolve linha ou célula de tabela, começa ou termina numa tabela, ou passa dos limites): "
                  "o texto ficou, mas o controle se perde.",
        True),
    "CONTEUDO_INCOMPLETO": (
        lambda n: f"{n} {_plural(n, 'controle de conteúdo perdeu', 'controles de conteúdo perderam')} "
                  f"o início ou o fim na edição e {_plural(n, 'sai', 'saem')} do arquivo; o texto "
                  "de dentro fica.",
        True),
    "ESTILO": (
        lambda n: f"{n} {_plural(n, 'referência de estilo não pôde ser aplicada', 'referências de estilo não puderam ser aplicadas')} "
                  "(nome de estilo inválido, ou um estilo citado com outro tipo). "
                  "O texto fica com o estilo Normal ao salvar.",
        True),
    "FORMATACAO": (
        lambda n: f"{n} {_plural(n, 'formatação não é preservada', 'formatações não são preservadas')} "
                  "ao salvar.",
        True),
    "PADRAO_DO_DOCUMENTO": (
        lambda n: "A fonte ou o tamanho padrão do documento são diferentes do padrão do EditDoc "
                  "(Calibri 11). O texto sem formatação própria muda de aparência ao salvar.",
        True),
    "LISTA": (
        lambda n: f"{n} {_plural(n, 'item ou definição de lista cita', 'itens ou definições de lista citam')} "
                  "numeração que não existe no arquivo ou que não pôde ser lida (danificada ou "
                  "acima dos limites do EditDoc). Esses itens ficam sem número ao salvar.",
        True),
    "LISTA_NIVEL": (
        lambda n: f"{n} {_plural(n, 'item de lista tem nível', 'itens de lista têm nível')} fora "
                  "de 1 a 9 e passa ao nível mais próximo ao salvar.",
        True),
    "ESPACAMENTO_LINHA": (
        lambda n: f"{n} {_plural(n, 'parágrafo tem espaçamento exato ou mínimo entre linhas', 'parágrafos têm espaçamento exato ou mínimo entre linhas')}. "
                  "O espaçamento sai como simples.",
        True),
    "MACROS": (
        lambda n: "O arquivo tem macros. Elas são ignoradas e saem do arquivo ao salvar.",
        True),
    "ELEMENTO_DESCONHECIDO": (
        lambda n: f"{n} {_plural(n, 'elemento de conteúdo não reconhecido foi ignorado', 'elementos de conteúdo não reconhecidos foram ignorados')}.",
        True),
    "CONTROLE_REMOVIDO": (
        lambda n: f"{n} {_plural(n, 'caractere de controle inválido foi removido', 'caracteres de controle inválidos foram removidos')} do texto.",
        True),
}


def construir(codigo: str, contagem: int) -> Aviso:
    modelo, perde = CATALOGO[codigo]
    return Aviso(codigo=codigo, texto=modelo(contagem), contagem=contagem,
                 perde_ao_salvar=perde)


class Coletor:
    """Soma as ocorrencias por codigo, na ordem em que apareceram."""

    def __init__(self) -> None:
        self._contagens: dict[str, int] = {}

    def somar(self, codigo: str, n: int = 1) -> None:
        if codigo not in CATALOGO:
            raise KeyError(f"aviso sem texto no catalogo: {codigo}")
        self._contagens[codigo] = self._contagens.get(codigo, 0) + n

    def contagem(self, codigo: str) -> int:
        return self._contagens.get(codigo, 0)

    def avisos(self) -> list[Aviso]:
        return [construir(c, n) for c, n in self._contagens.items() if n > 0]
