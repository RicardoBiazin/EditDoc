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

Preferencias (M8, Arquivo > Opcoes): alem do tipo, cada valor tem a sua faixa ou a
sua lista (`_VALIDOS`). Fora dela, volta ao padrao: um config editado a mao com
tamanho 0 ou papel "A9" nao pode quebrar o documento novo.
"""

from __future__ import annotations

import json
import os
import pathlib

from editdoc import log_interno

log = log_interno.obter(__name__)

#: Quantos arquivos o menu "Abrir recente" guarda, por padrao, e no maximo.
MAXIMO_RECENTES = 15
LIMITE_RECENTES = 50

PAPEIS = ("A4", "Carta", "Ofício")
UNIDADES = ("cm", "pol")
TEMAS = ("sistema", "claro", "escuro")


def padrao() -> dict:
    return {
        "janela_largura": 1200,
        "janela_altura": 800,
        "fonte_padrao": "Calibri",
        "tamanho_padrao": 11,
        "recentes": [],
        # Preferencias (M8)
        "papel_padrao": "A4",
        "unidade_regua": "cm",
        "recuperacao_ligada": True,
        "recuperacao_minutos": 10,
        "abrir_pdf_depois": False,
        "recentes_maximo": MAXIMO_RECENTES,
        "tema": "sistema",
        # Comentarios (0.1.6): autor e iniciais. Vazio = o usuario do Windows
        # (edicao/comentarios.autor_das_preferencias).
        "nome_usuario": "",
        "iniciais": "",
    }


def _fonte_valida(v) -> bool:
    return 0 < len(v.strip()) <= 100 and v.isprintable()


def _texto_valido(maximo: int):
    """Texto livre de uma linha (vazio vale: e' o padrao)."""
    return lambda v: len(v) <= maximo and v.isprintable()


#: chave -> funcao que diz se o valor (ja' do tipo certo) vale.
_VALIDOS = {
    "janela_largura": lambda v: 400 <= v <= 20000,
    "janela_altura": lambda v: 300 <= v <= 20000,
    "fonte_padrao": _fonte_valida,
    "tamanho_padrao": lambda v: 1 <= v <= 400,
    "papel_padrao": lambda v: v in PAPEIS,
    "unidade_regua": lambda v: v in UNIDADES,
    "recuperacao_minutos": lambda v: 1 <= v <= 120,
    "recentes_maximo": lambda v: 0 <= v <= LIMITE_RECENTES,
    "tema": lambda v: v in TEMAS,
    "nome_usuario": _texto_valido(255),
    "iniciais": _texto_valido(9),
}


def validar(valores: dict) -> dict:
    """Copia de `valores` so' com as chaves conhecidas, cada uma do tipo e na faixa certa."""
    saida = padrao()
    for chave, valor_padrao in saida.items():
        if chave not in valores:
            continue
        valor = valores[chave]
        if chave == "tamanho_padrao" and type(valor) is float:
            # Tamanho aceita meio ponto (10,5); inteiro continua inteiro no arquivo.
            valor = int(valor) if valor.is_integer() else round(valor * 2) / 2
            if type(valor) is float and 1 <= valor <= 400:
                saida[chave] = valor
                continue
        if type(valor) is not type(valor_padrao):
            continue
        teste = _VALIDOS.get(chave)
        if teste is not None and not teste(valor):
            continue
        saida[chave] = valor
    saida["recentes"] = [r for r in saida["recentes"] if isinstance(r, str)][:LIMITE_RECENTES]
    return saida


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
    # Tipo errado ou fora da faixa volta ao padrao; a lista so' guarda texto.
    valores = validar(bruto)
    valores["recentes"] = valores["recentes"][:valores["recentes_maximo"]]
    return valores


def gravar(valores: dict) -> None:
    limpos = validar(valores)
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
    """Põe o arquivo no topo da lista. Sem diferenca de caixa; no maximo `recentes_maximo`."""
    valores = carregar()
    chave = os.path.normcase(os.path.abspath(caminho))
    outros = [r for r in valores["recentes"]
              if os.path.normcase(os.path.abspath(r)) != chave]
    valores["recentes"] = ([caminho] + outros)[:valores["recentes_maximo"]]
    gravar(valores)


def limpar_recentes() -> None:
    valores = carregar()
    valores["recentes"] = []
    gravar(valores)


def gravar_preferencias(novas: dict) -> dict:
    """Grava as preferencias (sem mexer nos recentes e no tamanho da janela). Devolve o gravado."""
    valores = carregar()
    for chave in padrao():
        if chave in novas and chave not in ("recentes", "janela_largura", "janela_altura"):
            valores[chave] = novas[chave]
    valores = validar(valores)
    valores["recentes"] = valores["recentes"][:valores["recentes_maximo"]]
    gravar(valores)
    return valores
