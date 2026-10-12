"""Decide quais grupos da faixa recolher para caber na largura disponivel. Sem Qt.

Funcao pura de proposito: com as mesmas larguras, o resultado e' sempre o mesmo,
e por isso nao precisa de histerese para nao piscar ao redimensionar.
"""

from __future__ import annotations


def recolher_grupos(expandidos: list[int], recolhidos: list[int],
                    ordem: list[int], disponivel: int) -> list[bool]:
    """Devolve, para cada grupo, True se ele deve ficar recolhido.

    `expandidos[i]` e `recolhidos[i]` sao as larguras do grupo i nos dois
    estados. `ordem` diz os indices na sequencia em que os grupos podem recolher:
    o primeiro da lista e' o primeiro a recolher. Se nem recolhendo tudo cabe,
    devolve tudo recolhido, e quem chama fixa a largura minima.
    """
    recolhido = [False] * len(expandidos)
    total = sum(expandidos)
    for indice in ordem:
        if total <= disponivel:
            break
        recolhido[indice] = True
        total += recolhidos[indice] - expandidos[indice]
    return recolhido


def recolher_com_galeria(expandidos: list[int], recolhidos: list[int], ordem: list[int],
                         galeria: list[int], preferido: int, minimo: int,
                         disponivel: int) -> tuple[list[bool], int]:
    """Como `recolher_grupos`, com a galeria de estilos no meio (M6).

    `galeria[n]` e' a largura da galeria com n miniaturas (n = 0: recolhida num botao).
    A ordem das reducoes e' a do Word: o primeiro grupo da ordem recolhe antes de a
    galeria sair das `preferido` miniaturas; depois a galeria vai a `minimo`; depois do
    segundo e do terceiro grupos, vira o botao; depois os outros grupos. A sobra volta a
    galeria, uma miniatura por vez. Devolve (recolhido de cada grupo, miniaturas da galeria).
    """
    recolhido = [False] * len(expandidos)
    n = max(0, min(preferido, len(galeria) - 1))

    def total() -> int:
        return sum(recolhidos[i] if recolhido[i] else expandidos[i]
                   for i in range(len(expandidos))) + galeria[n]

    passos: list[tuple[str, int]] = []
    for k, indice in enumerate(ordem):
        passos.append(("grupo", indice))
        if k == 0:
            passos.append(("galeria", minimo))
        elif k == min(2, len(ordem) - 1):
            passos.append(("galeria", 0))
    if len(ordem) < 2:
        passos += [("galeria", minimo), ("galeria", 0)]
    for tipo, valor in passos:
        if total() <= disponivel:
            break
        if tipo == "grupo":
            recolhido[valor] = True
        else:
            n = min(n, valor)
    if n > 0:
        while n + 1 < len(galeria) and total() - galeria[n] + galeria[n + 1] <= disponivel:
            n += 1
    return recolhido, n
