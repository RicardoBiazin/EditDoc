"""Avisos do leitor: o que o arquivo tem e o EditDoc nao entende. Sem Qt.

Regra: nada que o arquivo contem e' descartado em silencio. Cada recurso que o
programa nao modela gera um aviso, com a contagem, e `perde_ao_salvar` diz se
gravar de volta apaga aquilo do arquivo. Os avisos com `perde_ao_salvar` pedem
confirmacao antes de salvar.

Cada codigo aparece uma vez por documento, com a soma das ocorrencias.
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
                  "em parágrafos. A grade e as células se perdem ao salvar.",
        True),
    "IMAGEM": (
        lambda n: f"{n} {_plural(n, 'imagem não é editada', 'imagens não são editadas')} "
                  "nesta versão e sai do arquivo ao salvar.",
        True),
    "CAIXA_DE_TEXTO": (
        lambda n: f"{n} {_plural(n, 'caixa de texto ou forma não é editada', 'caixas de texto ou formas não são editadas')} "
                  "nesta versão. O texto dela sai do arquivo ao salvar.",
        True),
    "OBJETO": (
        lambda n: f"{n} {_plural(n, 'objeto incorporado não é editado', 'objetos incorporados não são editados')} "
                  "nesta versão e sai do arquivo ao salvar.",
        True),
    "EQUACAO": (
        lambda n: f"{n} {_plural(n, 'equação não é editada', 'equações não são editadas')} "
                  "nesta versão e sai do arquivo ao salvar.",
        True),
    "CAMPO": (
        lambda n: f"{n} {_plural(n, 'campo (número de página, data ou outro) foi gravado', 'campos (número de página, data ou outros) foram gravados')} "
                  "como texto fixo.",
        True),
    "HIPERLINK": (
        lambda n: f"{n} {_plural(n, 'hiperlink foi mantido', 'hiperlinks foram mantidos')} "
                  "só como texto. O endereço se perde ao salvar.",
        True),
    "QUEBRA_DE_PAGINA": (
        lambda n: f"{n} {_plural(n, 'quebra de coluna não é preservada', 'quebras de coluna não são preservadas')} "
                  "ao salvar.",
        True),
    "CABECALHO_RODAPE": (
        lambda n: "O documento tem cabeçalho ou rodapé, que não é editado nesta versão "
                  "e sai do arquivo ao salvar.",
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
        lambda n: f"{n} {_plural(n, 'comentário não é editado', 'comentários não são editados')} "
                  "nesta versão e sai do arquivo ao salvar.",
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
        lambda n: f"{n} {_plural(n, 'controle de conteúdo foi achatado', 'controles de conteúdo foram achatados')}: "
                  "o texto ficou, mas o controle se perde.",
        True),
    "ESTILO": (
        lambda n: f"{n} {_plural(n, 'estilo de parágrafo ou de caractere não é aplicado', 'estilos de parágrafo ou de caractere não são aplicados')} "
                  "ao salvar. O texto fica com a formatação direta.",
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
        lambda n: f"{n} {_plural(n, 'lista tem formato de número que não é preservado', 'listas têm formato de número que não é preservado')}: "
                  "vira numeração simples.",
        True),
    "LISTA_NIVEL": (
        lambda n: f"{n} {_plural(n, 'item de lista está em nível abaixo do primeiro', 'itens de lista estão em níveis abaixo do primeiro')}. "
                  "O nível se perde ao salvar.",
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

    def avisos(self) -> list[Aviso]:
        return [construir(c, n) for c, n in self._contagens.items() if n > 0]
