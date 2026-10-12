"""Preferencias do usuario em `%APPDATA%\\EditDoc\\config.json`.

Regras, todas travadas por `tests/teste_base.py`:

- chave que nao existe em padrao() e' ignorada sem aviso: o arquivo pode vir de
  uma versao mais nova, e isso nao e' motivo para recusar o resto;
- valor de tipo diferente do padrao volta ao padrao (bool nao conta como int);
- JSON ilegivel, ou que nao seja um objeto, volta inteiro ao padrao, com aviso
  no log;
- a gravacao vai para um arquivo novo e so' depois troca o antigo: queda de
  energia no meio nao deixa o config pela metade.

Toda opcao nova entra em padrao() e precisa ser lida por algum codigo. Opcao
declarada e nunca lida e' uma opcao que finge existir.
"""

from __future__ import annotations

import json
import os
import pathlib

from editdoc import log_interno

log = log_interno.obter(__name__)

#: Quantos arquivos o menu "Abrir recente" guarda.
MAXIMO_RECENTES = 15


def padrao() -> dict:
    return {
        "janela_largura": 1200,
        "janela_altura": 800,
        "fonte_padrao": "Calibri",
        "tamanho_padrao": 11,
        "recentes": [],
    }


def caminho() -> pathlib.Path:
    return log_interno.pasta() / "config.json"


def carregar() -> dict:
    valores = padrao()
    try:
        bruto = json.loads(caminho().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return valores
    except (OSError, ValueError) as erro:
        log.warning("config.json ilegivel (%s): usando o padrao", erro)
        return valores
    if not isinstance(bruto, dict):
        log.warning("config.json nao e' um objeto: usando o padrao")
        return valores
    for chave, valor_padrao in valores.items():
        if chave in bruto and type(bruto[chave]) is type(valor_padrao):
            valores[chave] = bruto[chave]
    # A lista so' guarda texto: um item de outro tipo (de outra versao) some.
    valores["recentes"] = [r for r in valores["recentes"] if isinstance(r, str)][:MAXIMO_RECENTES]
    return valores


def gravar(valores: dict) -> None:
    limpos = {k: v for k, v in valores.items() if k in padrao()}
    alvo = caminho()
    novo = alvo.with_name(alvo.name + ".novo")
    novo.write_text(json.dumps(limpos, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    os.replace(novo, alvo)


def recentes() -> list[str]:
    """Arquivos recentes que ainda existem, do mais novo para o mais antigo."""
    existentes = []
    for caminho in carregar()["recentes"]:
        try:
            if os.path.isfile(caminho):
                existentes.append(caminho)
        except (OSError, ValueError):
            continue
    return existentes


def registrar_recente(caminho: str) -> None:
    """Põe o arquivo no topo da lista. Sem diferenca de caixa; no maximo MAXIMO_RECENTES."""
    valores = carregar()
    chave = os.path.normcase(os.path.abspath(caminho))
    outros = [r for r in valores["recentes"]
              if os.path.normcase(os.path.abspath(r)) != chave]
    valores["recentes"] = ([caminho] + outros)[:MAXIMO_RECENTES]
    gravar(valores)
