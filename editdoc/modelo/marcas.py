"""Marcas de campo e de marcador em pares, antes de gravar (0.1.3). Sem Qt e sem lxml.

Na tela as marcas sao caracteres: o usuario pode apagar o inicio de um campo e deixar o
fim (ou o contrario). O arquivo nao pode ter isso: um begin sem end faz o Word engolir o
resto do documento como codigo de campo. `equilibrar` devolve uma copia em que:

- campo: cada fim fecha o inicio do mesmo campo (o `par` que o leitor numerou; sem numero,
  o inicio aberto mais recente). Fim sem inicio sai; inicio que nao fecha sai (o resultado
  fica como texto comum). Conta como campo desfeito. Assim, apagar o fim do sumario nao faz
  o fim de outro campo fechar o sumario;
- marcador: nome repetido (o segundo inicio e o fim que sobra) sai; fim sem inicio sai;
  inicio sem fim ganha o fim logo depois dele (o link que aponta para ele continua valendo).

Cada historia (corpo, cada cabecalho e cada rodape) e' equilibrada sozinha, na ordem de
leitura (inclusive dentro das tabelas). O escritor e a conferencia usam a mesma funcao.

Controle de conteudo (0.1.5, `MarcaConteudo`): o de paragrafo tem o inicio e o fim no mesmo
paragrafo; o de bloco, na mesma lista de blocos (corpo, celula, cabecalho), com o inicio no
comeco de um paragrafo e o fim no fim de outro. O par tem de estar bem aninhado com os outros
do mesmo nivel (o arquivo e' uma arvore). Ponta sem par, ou par cruzado, sai (o conteudo
fica, sem o controle) e conta como controle desfeito. O inicio do controle de bloco vai para
o comeco do paragrafo e o fim para o fim, que e' onde o escritor grava o w:sdt, e o w:id
repetido (colar duas vezes) ganha outro numero.

Tambem aplica a regra do leitor para PAGE e NUMPAGES: o campo de pagina que ficou simples
(inicio, texto e fim no mesmo paragrafo e no mesmo link) vira o run de campo que a tela
recalcula. Sem isso, o arquivo relido teria outra forma e a conferencia acusaria diferenca.

Comentarios (0.1.6, `MarcaComentario`): so' no corpo (no cabecalho e no rodape a ancora sai).
Ancora de comentario que o catalogo nao tem sai; ancora repetida sai. O comentario sem
referencia no texto sai do catalogo (o Word nao o mostraria) e conta como comentario perdido;
a resposta dele sobe para o topo. Inicio sem fim ganha o fim logo antes da referencia; fim sem
inicio sai; inicio depois do fim: os dois saem (o comentario fica no ponto da referencia). O
conteudo do comentario gerado de novo (o editado ou o novo) passa pela mesma regra de campos e
marcadores; o que volta com o XML de origem fica como veio.
"""

from __future__ import annotations

import copy
import re
from dataclasses import replace

from editdoc.modelo.campos import normalizar_instrucao, tipo_do_campo
from editdoc.modelo.documento import (TIPOS_DE_FAIXA, Documento, MarcaCampo, MarcaComentario,
                                      MarcaConteudo, Marcador, Run, Tabela, paragrafos_de)


def historias(doc: Documento) -> list[list]:
    """Os blocos de cada historia: corpo, cabecalhos e rodapes."""
    saida = [doc.paragrafos]
    for faixas in (doc.cabecalhos, doc.rodapes):
        saida.extend(faixas[t] for t in TIPOS_DE_FAIXA if t in faixas)
    return saida


def _equilibrar_historia(blocos: list, contagem: dict) -> None:
    paragrafos = list(paragrafos_de(blocos))
    remover: set[int] = set()
    abertos: list[Run] = []
    vistos: set[str] = set()
    marcadores_abertos: dict[str, Run] = {}
    for p in paragrafos:
        for r in p.runs:
            m = r.marca
            if isinstance(m, MarcaCampo):
                if m.tipo == "inicio":
                    if m.campo is None:
                        remover.add(id(r))
                        contagem["campos"] += 1
                    else:
                        abertos.append(r)
                else:
                    alvo = _inicio_do_fim(abertos, m.par)
                    if alvo is None:
                        remover.add(id(r))
                        contagem["campos"] += 1
                    else:
                        # Os abertos depois do inicio deste fim nao fecharam antes dele.
                        while abertos[-1] is not alvo:
                            remover.add(id(abertos.pop()))
                            contagem["campos"] += 1
                        abertos.pop()
            elif isinstance(m, Marcador):
                if m.tipo == "inicio":
                    if m.nome in vistos:
                        remover.add(id(r))
                        contagem["marcadores"] += 1
                    else:
                        vistos.add(m.nome)
                        marcadores_abertos[m.nome] = r
                elif m.nome in marcadores_abertos:
                    del marcadores_abertos[m.nome]
                else:
                    remover.add(id(r))
    for r in abertos:
        remover.add(id(r))
        contagem["campos"] += 1
    fechar_depois = {id(r) for r in marcadores_abertos.values()}
    for p in paragrafos:
        _colapsar_campos_de_pagina(p)
    if not remover and not fechar_depois:
        return
    for p in paragrafos:
        novos = []
        for r in p.runs:
            if id(r) in remover:
                continue
            novos.append(r)
            if id(r) in fechar_depois:
                novos.append(Run(marca=Marcador("fim", r.marca.nome)))
        p.runs = novos


def _inicio_do_fim(abertos: list, par: int):
    """O inicio que este fim fecha: o do mesmo par, ou (sem par) o mais recente."""
    if not abertos:
        return None
    if not par:
        return abertos[-1]
    for r in reversed(abertos):
        if r.marca.par == par:
            return r
        if not r.marca.par:
            return None
    return None


def _simples(r: Run) -> bool:
    return not (r.eh_objeto() or r.campo is not None or r.marca is not None)


def _colapsar_campos_de_pagina(p) -> None:
    """A mesma regra do leitor (`_vira_campo_de_pagina`), sobre o modelo."""
    runs = p.runs
    i = 0
    while i < len(runs):
        m = runs[i].marca
        campo = m.campo if isinstance(m, MarcaCampo) and m.tipo == "inicio" else None
        if campo is None or campo.sem_resultado or campo.extra or campo.travado or                 not all(isinstance(x, str) for x in campo.codigo):
            i += 1
            continue
        instrucao = normalizar_instrucao(campo.instrucao())
        if tipo_do_campo(instrucao) is None:
            i += 1
            continue
        j = i + 1
        while j < len(runs) and _simples(runs[j]):
            j += 1
        fim = runs[j] if j < len(runs) else None
        link = runs[i].link
        if fim is None or not (isinstance(fim.marca, MarcaCampo) and fim.marca.tipo == "fim")                 or any(r.link != link for r in runs[i:j + 1]):
            i += 1
            continue
        resultado = runs[i + 1:j]
        base = resultado[0] if resultado else runs[i]
        texto = "".join(r.texto for r in resultado).replace("\f", "")
        runs[i:j + 1] = [replace(base, texto=texto, campo=instrucao, marca=None, imagem=None,
                                 objeto=None, link=link)]
        i += 1


def _par_de(abertos: list, fim: Run):
    """O inicio que esta marca de fim de controle fecha: o do mesmo par, ou o mais recente."""
    if not abertos:
        return None
    par = fim.marca.par
    if not par:
        return abertos[-1]
    return next((r for r in reversed(abertos) if r.marca.par == par), None)


def _fechar(abertos: list, fim: Run, remover: set, contagem: dict) -> None:
    alvo = _par_de(abertos, fim)
    if alvo is None:
        remover.add(id(fim))
        contagem["conteudos"] += 1
    elif alvo is abertos[-1]:
        abertos.pop()
    else:
        # Par cruzado com outro controle: nao cabe na arvore do arquivo.
        abertos.remove(alvo)
        remover.update((id(alvo), id(fim)))
        contagem["conteudos"] += 1


def _eh_conteudo(r: Run, bloco: bool, tipo: str | None = None) -> bool:
    m = r.marca
    return isinstance(m, MarcaConteudo) and m.bloco == bloco and (tipo is None or m.tipo == tipo)


def _conteudos_de_bloco(blocos: list, contagem: dict) -> None:
    """Controles de bloco de uma lista de blocos (a celula e' outra lista)."""
    abertos: list[Run] = []
    remover: set[int] = set()
    paragrafos = []
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            for linha in bloco.linhas:
                for celula in linha.celulas:
                    _conteudos_de_bloco(celula.blocos, contagem)
            continue
        paragrafos.append(bloco)
        for r in bloco.runs:
            if _eh_conteudo(r, True, "inicio"):
                abertos.append(r)
        for r in bloco.runs:
            if _eh_conteudo(r, True, "fim"):
                _fechar(abertos, r, remover, contagem)
    for r in abertos:
        remover.add(id(r))
        contagem["conteudos"] += 1
    for p in paragrafos:
        if not any(isinstance(r.marca, MarcaConteudo) and r.marca.bloco for r in p.runs):
            continue
        inicios = [r for r in p.runs if _eh_conteudo(r, True, "inicio") and id(r) not in remover]
        fins = [r for r in p.runs if _eh_conteudo(r, True, "fim") and id(r) not in remover]
        meio = [r for r in p.runs if not _eh_conteudo(r, True)]
        p.runs = inicios + meio + fins


def _conteudos_de_run(p, contagem: dict) -> None:
    """Controles de paragrafo: inicio e fim no mesmo paragrafo, bem aninhados."""
    if not any(_eh_conteudo(r, False) for r in p.runs):
        return
    abertos: list[Run] = []
    remover: set[int] = set()
    for r in p.runs:
        if _eh_conteudo(r, False, "inicio"):
            abertos.append(r)
        elif _eh_conteudo(r, False, "fim"):
            _fechar(abertos, r, remover, contagem)
    for r in abertos:
        remover.add(id(r))
        contagem["conteudos"] += 1
    if remover:
        p.runs = [r for r in p.runs if id(r) not in remover]


_ID_SDT = re.compile(r'(<w:id w:val=")(-?\d+)(")')


def _ids_unicos(doc: Documento) -> None:
    """O w:id do controle tem de ser unico no documento: o repetido ganha outro numero."""
    vistos: set[int] = set()
    marcas = []
    for blocos in historias(doc):
        for p in paragrafos_de(blocos):
            for r in p.runs:
                if isinstance(r.marca, MarcaConteudo) and r.marca.tipo == "inicio"                         and r.marca.propriedades:
                    marcas.append(r)
    usados = set()
    for r in marcas:
        m = _ID_SDT.search(r.marca.propriedades.decode("utf-8", "replace"))
        if m:
            usados.add(int(m.group(2)))
    proximo = max(usados, default=0) + 1
    for r in marcas:
        texto = r.marca.propriedades.decode("utf-8", "replace")
        m = _ID_SDT.search(texto)
        if not m:
            continue
        valor = int(m.group(2))
        if valor in vistos:
            while proximo in usados:
                proximo += 1
            usados.add(proximo)
            novo = _ID_SDT.sub(lambda x: f"{x.group(1)}{proximo}{x.group(3)}", texto, count=1)
            r.marca = replace(r.marca, propriedades=novo.encode("utf-8"))
            valor = proximo
        vistos.add(valor)


def equilibrar(doc: Documento) -> tuple[Documento, dict[str, int]]:
    """Copia do documento com as marcas em pares. Devolve (documento, contagens):
    "campos" desfeitos, "marcadores" repetidos que sairam, "conteudos" (controles de
    conteudo) desfeitos e "comentarios" que perderam a referencia (0.1.6)."""
    contagem = {"campos": 0, "marcadores": 0, "conteudos": 0, "comentarios": 0}
    cat = doc.comentarios
    tem_comentarios = cat is not None and bool(getattr(cat, "itens", None))
    if not tem_comentarios and not any(r.marca is not None for blocos in historias(doc)
                                       for p in paragrafos_de(blocos) for r in p.runs):
        return doc, contagem
    saida = copy.copy(doc)
    saida.paragrafos = copy.deepcopy(doc.paragrafos)
    saida.cabecalhos = copy.deepcopy(doc.cabecalhos)
    saida.rodapes = copy.deepcopy(doc.rodapes)
    for blocos in historias(saida):
        _equilibrar_historia(blocos, contagem)
        _conteudos_de_bloco(blocos, contagem)
        for p in paragrafos_de(blocos):
            _conteudos_de_run(p, contagem)
    _ids_unicos(saida)
    _equilibrar_comentarios(saida, contagem)
    return saida, contagem


def _equilibrar_comentarios(doc: Documento, contagem: dict) -> None:
    """Ancoras de comentario coerentes com o catalogo (ver o topo do modulo)."""
    from dataclasses import replace as _replace
    cat = doc.comentarios
    validos = {c.id for c in cat.itens} if cat is not None else set()
    for blocos in historias(doc)[1:]:
        for p in paragrafos_de(blocos):
            if any(isinstance(r.marca, MarcaComentario) for r in p.runs):
                p.runs = [r for r in p.runs if not isinstance(r.marca, MarcaComentario)]
    sequencia = [(p, r) for p in paragrafos_de(doc.paragrafos) for r in p.runs
                 if isinstance(r.marca, MarcaComentario)]
    if cat is None and not sequencia:
        return
    remover: set[int] = set()
    vistos: dict = {}
    for i, (p, r) in enumerate(sequencia):
        m = r.marca
        if m.id not in validos or (m.tipo, m.id) in vistos:
            remover.add(id(r))
            continue
        vistos[(m.tipo, m.id)] = (i, p, r)
    sem_referencia = {c for c in validos if ("referencia", c) not in vistos}
    inserir: list = []  # (paragrafo, run da referencia, run do fim novo)
    for ident in validos:
        ini, fim = vistos.get(("inicio", ident)), vistos.get(("fim", ident))
        if ident in sem_referencia:
            for x in (ini, fim):
                if x is not None:
                    remover.add(id(x[2]))
            continue
        ref = vistos[("referencia", ident)]
        if ini is not None and fim is not None and ini[0] > fim[0]:
            remover.update((id(ini[2]), id(fim[2])))
        elif ini is not None and fim is None:
            if ini[0] < ref[0]:
                inserir.append((ref[1], ref[2], Run(marca=MarcaComentario("fim", ident))))
            else:
                remover.add(id(ini[2]))
        elif fim is not None and ini is None:
            remover.add(id(fim[2]))
    if remover:
        for p in {id(p): p for p, _r in sequencia}.values():
            p.runs = [r for r in p.runs if id(r) not in remover]
    for p, ref, novo in inserir:
        indice = next(i for i, r in enumerate(p.runs) if r is ref)
        p.runs.insert(indice, novo)
    if cat is None:
        return
    contagem["comentarios"] += len(sem_referencia)
    itens = []
    for c in cat.itens:
        if c.id in sem_referencia:
            continue
        mudar = {}
        if c.pai is not None and (c.pai in sem_referencia or c.pai not in validos):
            mudar["pai"] = None
        if c.original is None and c.paragrafos:
            # Conteudo gerado de novo: campos e marcadores em pares, como no corpo.
            blocos = copy.deepcopy(list(c.paragrafos))
            _equilibrar_historia(blocos, contagem)
            mudar["paragrafos"] = tuple(blocos)
        itens.append(_replace(c, **mudar) if mudar else c)
    doc.comentarios = cat.com_itens(itens)


def nomes_de_marcadores(doc: Documento) -> list[str]:
    """Os nomes dos marcadores do documento, na ordem (para o dialogo de link)."""
    nomes: list[str] = []
    for blocos in historias(doc):
        for p in paragrafos_de(blocos):
            for r in p.runs:
                if isinstance(r.marca, Marcador) and r.marca.tipo == "inicio" \
                        and r.marca.nome not in nomes:
                    nomes.append(r.marca.nome)
    return nomes
