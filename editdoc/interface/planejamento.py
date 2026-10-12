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
