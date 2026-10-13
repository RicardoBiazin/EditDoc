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

Tambem aplica a regra do leitor para PAGE e NUMPAGES: o campo de pagina que ficou simples
(inicio, texto e fim no mesmo paragrafo e no mesmo link) vira o run de campo que a tela
recalcula. Sem isso, o arquivo relido teria outra forma e a conferencia acusaria diferenca.
"""

from __future__ import annotations

import copy
from dataclasses import replace

from editdoc.modelo.campos import normalizar_instrucao, tipo_do_campo
from editdoc.modelo.documento import (TIPOS_DE_FAIXA, Documento, MarcaCampo, Marcador, Run,
                                      paragrafos_de)


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


def equilibrar(doc: Documento) -> tuple[Documento, dict[str, int]]:
    """Copia do documento com as marcas em pares. Devolve (documento, contagens):
    "campos" desfeitos e "marcadores" repetidos que sairam."""
    contagem = {"campos": 0, "marcadores": 0}
    if not any(r.marca is not None for blocos in historias(doc)
               for p in paragrafos_de(blocos) for r in p.runs):
        return doc, contagem
    saida = copy.copy(doc)
    saida.paragrafos = copy.deepcopy(doc.paragrafos)
    saida.cabecalhos = copy.deepcopy(doc.cabecalhos)
    saida.rodapes = copy.deepcopy(doc.rodapes)
    for blocos in historias(saida):
        _equilibrar_historia(blocos, contagem)
    return saida, contagem


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
