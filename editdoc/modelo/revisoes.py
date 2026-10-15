"""Alteracoes controladas (0.1.13): o que o modelo sabe das revisoes. Sem Qt e sem lxml.

As revisoes ficam nos proprios runs e paragrafos (`Run.insercao`, `Run.exclusao`,
`Run.mudanca_formato`, `Paragrafo.marca_insercao`, `marca_exclusao`, `mudanca_formato`,
`mudanca_numeracao`) e os trechos de movimento sao marcas no fluxo (`MarcaMovimento`). Aqui
ficam os limites contra arquivo hostil, a lista de revisoes de um documento (para a
conferencia e para os testes), o texto final e o original de um paragrafo e o equilibrio das
marcas de movimento antes de gravar.

Modos de exibicao (os do Word):

- "simples" (Marcacao simples): o texto final, com uma barra na margem onde houve alteracao;
- "todas" (Toda a marcacao): inserido sublinhado e excluido tachado, na cor do autor;
- "final" (Sem marcacao): o texto final, sem marca nenhuma;
- "original": o texto antes das alteracoes.
"""

from __future__ import annotations

from dataclasses import replace

from editdoc.modelo.documento import (Documento, MarcaMovimento, Paragrafo, Revisao, Tabela,
                                      faixas_das_secoes, paragrafos_de)

#: Modos de exibicao, na ordem do Word.
MODOS = ("simples", "todas", "final", "original")
NOMES_DOS_MODOS = {"simples": "Marcação simples", "todas": "Toda a marcação",
                   "final": "Sem marcação", "original": "Original"}
MODO_PADRAO = "todas"

#: Limites contra arquivo hostil. Acima deles a revisao nao e' guardada: a insercao fica como
#: texto comum e a exclusao sai (o comportamento ate' a 0.1.12), com o aviso REVISAO.
LIMITES = {
    "revisoes": 100000,       # revisoes (insercoes, exclusoes, formatacao...) por documento
    "autores_revisao": 500,   # autores distintos
    "autor_revisao": 255,     # caracteres do nome do autor
}
#: Tamanho maximo do w:date (o ISO 8601 do Word tem 20).
DATA_MAXIMA = 64

#: Tipo da revisao -> nome na tela.
NOMES_DOS_TIPOS = {"ins": "Inserção", "del": "Exclusão", "moveFrom": "Movido (origem)",
                   "moveTo": "Movido (destino)", "formato": "Formatação",
                   "paragrafo": "Formatação de parágrafo", "marca_ins": "Parágrafo inserido",
                   "marca_del": "Parágrafo excluído", "linha_ins": "Linha inserida",
                   "linha_del": "Linha excluída", "tabela": "Propriedades da tabela",
                   "secao": "Propriedades da seção", "numeracao": "Numeração",
                   "linha_prop": "Propriedades da linha", "celula": "Célula"}


def eh_insercao(rev: Revisao | None) -> bool:
    return rev is not None and rev.tipo in ("ins", "moveTo")


def eh_exclusao(rev: Revisao | None) -> bool:
    return rev is not None and rev.tipo in ("del", "moveFrom")


def visivel_no_modo(insercao: Revisao | None, exclusao: Revisao | None, modo: str) -> bool:
    """O trecho aparece no modo? Excluido some no final; inserido some no original."""
    if modo in ("final", "simples"):
        return exclusao is None
    if modo == "original":
        return insercao is None
    return True


def _historias(doc: Documento) -> list:
    """Os blocos de cada historia que o escritor grava: corpo, cabecalhos e rodapes (de todas
    as secoes), notas e comentarios."""
    listas = [doc.paragrafos]
    for faixas in (doc.cabecalhos, doc.rodapes):
        listas.extend(faixas.values())
    listas.extend(blocos for _onde, _tipo, blocos in faixas_das_secoes(doc))
    if doc.notas is not None:
        listas.extend(list(n.paragrafos) for n in doc.notas.todas())
    if doc.comentarios is not None:
        listas.extend(list(c.paragrafos) for c in doc.comentarios.itens)
    return listas


def revisoes_de(doc: Documento) -> list[tuple]:
    """(tipo, autor, data, texto) de cada revisao, na ordem do documento: o trecho inserido ou
    excluido (runs vizinhos com a mesma revisao juntos), a formatacao, a marca de paragrafo e
    as da tabela (linha). Para a conferencia e os testes."""
    saida: list[tuple] = []
    for blocos in _historias(doc):
        _revisoes_dos_blocos(blocos, saida)
    return saida


def _revisoes_dos_blocos(blocos, saida: list) -> None:
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            if bloco.mudanca_grade:
                saida.append(("tabela", "", None, ""))
            for linha in bloco.linhas:
                extras = linha.extras or ""
                if "<w:ins " in extras or "<w:ins>" in extras:
                    saida.append(("linha_ins", "", None, ""))
                if "<w:del " in extras or "<w:del>" in extras:
                    saida.append(("linha_del", "", None, ""))
                for celula in linha.celulas:
                    _revisoes_dos_blocos(celula.blocos, saida)
            continue
        abertos: dict = {}
        for r in bloco.runs:
            for lado, rev in (("i", r.insercao), ("e", r.exclusao)):
                if rev is None:
                    abertos.pop(lado, None)
                    continue
                chave = (rev.tipo, rev.autor, rev.data)
                if abertos.get(lado, (None,))[0] == chave:
                    i = abertos[lado][1]
                    saida[i] = (*chave, saida[i][3] + r.texto)
                else:
                    saida.append((*chave, r.texto))
                    abertos[lado] = (chave, len(saida) - 1)
            if r.mudanca_formato:
                saida.append(("formato", "", None, r.texto))
        if bloco.mudanca_formato:
            saida.append(("paragrafo", "", None, ""))
        if bloco.mudanca_numeracao:
            saida.append(("numeracao", "", None, ""))
        for rev, tipo in ((bloco.marca_insercao, "marca_ins"), (bloco.marca_exclusao, "marca_del")):
            if rev is not None:
                saida.append((tipo, rev.autor, rev.data, ""))


def tem_revisoes(doc: Documento) -> bool:
    return bool(revisoes_de(doc))


def autores(doc: Documento) -> list[str]:
    vistos: list[str] = []
    for _tipo, autor, _data, _texto in revisoes_de(doc):
        if autor and autor not in vistos:
            vistos.append(autor)
    return vistos


def texto_no_modo(p: Paragrafo, modo: str) -> str:
    """O texto do paragrafo como o modo mostra (marcas nao contam)."""
    return "".join(r.texto for r in p.runs if r.marca is None
                   and visivel_no_modo(r.insercao, r.exclusao, modo))


def equilibrar_movimentos(doc: Documento) -> Documento:
    """Deixa as marcas de movimento em pares (inicio e fim do mesmo tipo, na mesma historia),
    no proprio documento (quem chama passa a copia de `marcas.equilibrar`). A marca sem par
    sai: o usuario apagou a outra ponta junto com o texto. Os runs revisados ficam."""
    historias = _historias(doc)
    if not any(isinstance(r.marca, MarcaMovimento) for blocos in historias
               for p in paragrafos_de(blocos) for r in p.runs):
        return doc
    for blocos in historias:
        paragrafos = list(paragrafos_de(blocos))
        abertos: dict[str, list] = {"de": [], "para": []}
        manter: set[int] = set()
        for p in paragrafos:
            for r in p.runs:
                m = r.marca
                if not isinstance(m, MarcaMovimento):
                    continue
                if not m.fim:
                    abertos[m.tipo].append(r)
                    continue
                pilha = abertos[m.tipo]
                par = next((x for x in reversed(pilha) if m.par and x.marca.par == m.par), None)
                if par is None and pilha:
                    par = pilha[-1]
                if par is not None:
                    pilha.remove(par)
                    manter.add(id(par))
                    manter.add(id(r))
        for p in paragrafos:
            if any(isinstance(r.marca, MarcaMovimento) and id(r) not in manter for r in p.runs):
                p.runs = [r for r in p.runs
                          if not isinstance(r.marca, MarcaMovimento) or id(r) in manter]
    return doc


def sem_revisao_na_marca(run):
    """O run de marca que nao pode ficar dentro de w:ins/w:del (marcador, ancora de comentario,
    controle de conteudo, trecho de movimento) sai sem as revisoes."""
    if run.insercao is None and run.exclusao is None:
        return run
    return replace(run, insercao=None, exclusao=None)
