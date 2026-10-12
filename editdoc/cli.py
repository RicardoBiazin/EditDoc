"""Linha de comando: os arquivos pedidos e o que é recusado.

    EditDoc contrato.docx
    EditDoc a.docx b.docx
    EditDoc --autoverificacao

**Nomes de dispositivo do Windows são RECUSADOS.** `CON`, `NUL`, `PRN`, `AUX`,
`COM1`..`COM9` e `LPT1`..`LPT9` não são arquivos: abrir `CON` lê do console e
abrir `NUL` devolve vazio para sempre. Pior, isso vale mesmo com extensão e em
qualquer pasta -- `C:\\temp\\nul.docx` ainda é o dispositivo. Um editor que
mapeia o arquivo em memória travaria ou mostraria lixo, e o usuário não
entenderia por quê.

O parser é escrito à mão, e não com `argparse`, por um motivo prático: o
`argparse` chama `sys.exit()` com mensagem em inglês no `stderr`, que num
programa de janela (sem console) não vai para lugar nenhum -- o usuário veria
o programa simplesmente não abrir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Nomes reservados do Windows. A comparação é pelo nome SEM extensão e sem
#: caixa: `nul`, `NUL.docx` e `Nul.log` são todos o mesmo dispositivo.
DISPOSITIVOS = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"com{n}" for n in range(1, 10)]
    + [f"lpt{n}" for n in range(1, 10)])

AJUDA = """EditDoc -- editor de documentos .docx.

    EditDoc [arquivo ...]

    --autoverificacao  prova de vida do executável; não abre janela
    --ajuda            mostra isto
"""


@dataclass
class Pedido:
    """O que a linha de comando pediu."""

    arquivos: list[str] = field(default_factory=list)
    ajuda: bool = False
    autoverificacao: bool = False
    #: (o que foi escrito, motivo em português) -- a interface mostra o motivo.
    recusados: list[tuple[str, str]] = field(default_factory=list)


def e_dispositivo(caminho: str) -> bool:
    """O caminho aponta para um dispositivo do Windows?"""
    # Divide pelos DOIS separadores e ignora o barra final: `\\.\NUL` e `nul\`
    # são o dispositivo, e `pathlib` não separa o nome nesses casos.
    nome = re.split(r"[\\/]", caminho.rstrip("\\/"))[-1]
    # `NUL.docx` também é o dispositivo: o Windows olha só o que vem antes do
    # primeiro ponto.
    return nome.split(".")[0].strip().lower() in DISPOSITIVOS


def analisar(argumentos: list[str]) -> Pedido:
    """Interpreta os argumentos. Nunca levanta -- o que não serve vai em
    `recusados`, para a interface avisar em português."""
    pedido = Pedido()
    for bruto in argumentos:
        alvo = bruto.lower()
        if not bruto.strip():
            pedido.recusados.append((bruto, "caminho vazio"))
        elif alvo in ("--ajuda", "--help", "-h", "/?"):
            pedido.ajuda = True
        elif alvo == "--autoverificacao":
            pedido.autoverificacao = True
        elif bruto.startswith("-"):
            pedido.recusados.append((bruto, "opção desconhecida"))
        elif e_dispositivo(bruto):
            pedido.recusados.append(
                (bruto, "é um dispositivo do Windows, e não um arquivo"))
        else:
            pedido.arquivos.append(bruto)
    return pedido
