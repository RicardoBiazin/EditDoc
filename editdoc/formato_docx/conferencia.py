"""Conferencia do arquivo gravado, antes da troca atomica. Sem Qt.

A gravacao escreve o temporario, le de volta o que ficou no disco e compara com
o que o usuario viu: mesma estrutura (paragrafos, tabelas, linhas, celulas e
mesclas), mesmo texto, mesmas quebras, as mesmas imagens (pelos bytes) e os
mesmos campos. Cabecalho e rodape (M5) passam pela mesma comparacao, um por tipo.
Estilos (M6): o estilo de cada paragrafo e os estilos de caractere usados nele.
Objetos opacos (0.1.2): cada um, no lugar, pela `opacos.assinatura` (o XML e o conteudo
das partes que ele usa, sem depender dos nomes de parte e dos rIds renumerados). Uma
parte referenciada que falta faz o leitor nao preservar o objeto, e a contagem acusa.
Hiperlinks, campos e marcadores (0.1.3): o destino de cada trecho de link e as marcas de
campo (com o codigo) e de marcador de cada paragrafo, depois de `marcas.equilibrar`; e o
conteudo das partes preservadas do pacote (`pacote.assinatura`).
Listas (0.1.4): o numId e o nivel de cada paragrafo (o numbering.xml passa pelo validador).
Comentarios (0.1.6): as ancoras de cada paragrafo (com as outras marcas) e, de cada
comentario, o autor, as iniciais, a data, o pai, o resolvido, os ids das partes estendidas e
o conteudo (texto, estilos, links e marcas, paragrafo a paragrafo).
Um arquivo que nao confere nao substitui o original.

Os dois lados passam por `normalizar`: o escritor completa a celula e o corpo
que terminam em tabela com um paragrafo vazio (o Word exige), e isso nao e'
diferenca.
"""

from __future__ import annotations

import hashlib

from editdoc.formato_docx import comentarios as fx_comentarios
from editdoc.formato_docx import opacos
from editdoc.formato_docx import pacote as fx_pacote
from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.escritor import texto_gravavel
from editdoc.modelo import marcas
from editdoc.modelo.documento import CARACTERE_OBJETO, Documento, Tabela, normalizar


class FalhaDeConferencia(Exception):
    """O arquivo gravado nao tem o mesmo texto que o documento."""


def texto_do_paragrafo(paragrafo) -> str:
    """Texto como vai para o arquivo. Imagem e objeto opaco contam como CARACTERE_OBJETO."""
    return "".join(CARACTERE_OBJETO if r.eh_objeto() else texto_gravavel(r.texto)[0]
                   for r in paragrafo.runs)


def _imagens(paragrafo) -> list[str]:
    return [hashlib.sha256(r.imagem.dados).hexdigest()[:16] + f"@{r.imagem.largura_emu}x"
            f"{r.imagem.altura_emu}" for r in paragrafo.runs if r.imagem is not None]


def _objetos(paragrafo) -> tuple:
    return tuple(opacos.assinatura(r.objeto) for r in paragrafo.runs if r.objeto is not None)


def _campos(paragrafo) -> tuple:
    return tuple(r.campo for r in paragrafo.runs if r.campo is not None)


def _links(paragrafo) -> tuple:
    """(destino, texto) de cada trecho de link, com os runs vizinhos de mesmo destino juntos."""
    saida: list[list] = []
    for r in paragrafo.runs:
        if r.marca is not None:
            continue
        texto = CARACTERE_OBJETO if r.eh_objeto() else texto_gravavel(r.texto)[0]
        if saida and saida[-1][0] == r.link:
            saida[-1][1] += texto
        else:
            saida.append([r.link, texto])
    return tuple((link, texto) for link, texto in saida if link is not None)


def _marcas(paragrafo) -> tuple:
    """As marcas de campo (com o codigo) e de marcador, na ordem."""
    return tuple(r.marca for r in paragrafo.runs if r.marca is not None)


def _itens(blocos, saida: list, onde: str) -> None:
    """Sequencia comparavel: um item por paragrafo, tabela, linha e celula."""
    n_par = 0
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            saida.append((f"{onde}tabela", "tabela", len(bloco.linhas), len(bloco.colunas_tw),
                          bloco.estilo))
            for i, linha in enumerate(bloco.linhas):
                saida.append((f"{onde}linha {i + 1}", "linha", len(linha.celulas), linha.cabecalho))
                for j, celula in enumerate(linha.celulas):
                    lugar = f"{onde}celula {i + 1},{j + 1}: "
                    saida.append((lugar, "celula", celula.colunas, celula.mescla_vertical))
                    _itens(celula.blocos, saida, lugar)
            saida.append((f"{onde}fim da tabela", "fim"))
        else:
            n_par += 1
            saida.append((f"{onde}paragrafo {n_par}", "p", texto_do_paragrafo(bloco),
                          bloco.quebra_antes, tuple(_imagens(bloco)), _campos(bloco),
                          bloco.estilo, tuple(sorted({r.estilo for r in bloco.runs if r.estilo})),
                          _objetos(bloco), _links(bloco), _marcas(bloco),
                          (bloco.lista, bloco.lista_nivel)))


def _comentarios(doc: Documento) -> tuple:
    """O que se compara de cada comentario (0.1.6), na ordem do catalogo."""
    cat = doc.comentarios
    if cat is None:
        return ()
    saida = []
    for c in cat.itens:
        itens: list = []
        _itens(normalizar(Documento(paragrafos=list(c.paragrafos))).paragrafos, itens, "")
        saida.append((c.id, c.autor, c.iniciais, c.data, c.pai, c.resolvido, c.para_id,
                      c.duravel, c.data_utc, tuple(x[1:] for x in itens)))
    return tuple(saida)


def conferir(dados: bytes, esperado: Documento) -> None:
    """Relê `dados` com o proprio leitor e compara estrutura, texto e imagens."""
    from editdoc.formato_docx.leitor import ler
    try:
        lido, _avisos = ler(dados)
    except ErroDocx as erro:
        raise FalhaDeConferencia(f"o arquivo gravado nao pode ser lido: {erro.codigo}") from None
    a: list = []
    b: list = []
    # O escritor grava as marcas em pares (marcas.equilibrar): e' isso que tem de voltar.
    esperado = fx_comentarios.preparar(marcas.equilibrar(esperado)[0])
    esperado_n, lido_n = normalizar(esperado), normalizar(lido)
    _itens(esperado_n.paragrafos, a, "")
    _itens(lido_n.paragrafos, b, "")
    for nome, faixa_a, faixa_b in (("cabecalho", esperado_n.cabecalhos, lido_n.cabecalhos),
                                   ("rodape", esperado_n.rodapes, lido_n.rodapes)):
        if sorted(faixa_a) != sorted(faixa_b):
            raise FalhaDeConferencia(f"{nome}: tipos diferentes ({sorted(faixa_a)} e {sorted(faixa_b)})")
        for tipo in sorted(faixa_a):
            _itens(faixa_a[tipo], a, f"{nome} {tipo}: ")
            _itens(faixa_b[tipo], b, f"{nome} {tipo}: ")
    n_a = sum(1 for x in a if x[1] == "p")
    n_b = sum(1 for x in b if x[1] == "p")
    if n_a != n_b:
        raise FalhaDeConferencia(f"paragrafos: esperado {n_a}, gravado {n_b}")
    for x, y in zip(a, b):
        if x[1:] == y[1:]:
            continue
        lugar = x[0]
        if x[1] == "p" and y[1] == "p":
            if x[2] != y[2]:
                raise FalhaDeConferencia(f"texto diferente no {lugar}")
            if x[3] != y[3]:
                raise FalhaDeConferencia(f"quebra de pagina diferente no {lugar}")
            if x[5] != y[5]:
                raise FalhaDeConferencia(f"campo diferente no {lugar}")
            if x[8] != y[8]:
                raise FalhaDeConferencia(f"objeto (caixa de texto, forma...) diferente no {lugar}")
            if x[9] != y[9]:
                raise FalhaDeConferencia(f"hiperlink diferente no {lugar}")
            if x[10] != y[10]:
                raise FalhaDeConferencia(f"campo ou marcador diferente no {lugar}")
            if x[11] != y[11]:
                raise FalhaDeConferencia(f"lista (numeracao) diferente no {lugar}")
            if x[6:8] != y[6:8]:
                raise FalhaDeConferencia(f"estilo diferente no {lugar}")
            raise FalhaDeConferencia(f"imagem diferente no {lugar}")
        raise FalhaDeConferencia(f"estrutura de tabela diferente em {lugar}")
    if len(a) != len(b):
        raise FalhaDeConferencia("estrutura de tabela diferente no fim do documento")
    if esperado.pagina != lido.pagina:
        raise FalhaDeConferencia("papel ou margens diferentes do documento")
    a_coment, b_coment = _comentarios(esperado), _comentarios(lido)
    if len(a_coment) != len(b_coment):
        raise FalhaDeConferencia(f"comentarios: esperado {len(a_coment)}, gravado {len(b_coment)}")
    for x, y in zip(a_coment, b_coment):
        if x != y:
            raise FalhaDeConferencia(f"comentario {x[0]} diferente no arquivo gravado")
    if fx_pacote.assinatura(esperado.pacote) != fx_pacote.assinatura(lido.pacote):
        raise FalhaDeConferencia("partes preservadas do pacote (propriedades, customXml, "
                                 "fontes...) diferentes")


def conferidor(esperado: Documento):
    """Funcao no formato que `gravacao.gravar_bytes(conferir=...)` espera."""
    def _conferir(dados: bytes) -> None:
        conferir(dados, esperado)
    return _conferir
