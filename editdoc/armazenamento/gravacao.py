"""Gravar bytes prontos no lugar do arquivo, sem nunca deixá-lo pela metade.

A ORDEM NO WINDOWS NÃO É NEGOCIÁVEL:

    conferir o espaco       <- ANTES do primeiro byte
    escrever o temporario   <- ao lado do destino, e fsync antes da troca
    reler e conferir        <- opcional: confere o que foi para o DISCO
    trocar                  <- ReplaceFileW (preserva ACL) ou os.replace
    apagar o temporario, se sobrou

A troca é ATÔMICA: enquanto o temporário é escrito, o arquivo do usuário
continua intacto no lugar. Disco cheio, queda de energia ou exceção no meio
não deixam o arquivo pela metade -- deixam o arquivo ORIGINAL, e o temporário
sai.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import time
from collections.abc import Callable

from editdoc import log_interno

log = log_interno.obter(__name__)

#: Folga exigida além do tamanho do arquivo, para o temporário caber com sobra.
FOLGA = 16 * 1024 * 1024

MEGA = 1024 * 1024

#: Sufixo do temporário, ao lado do destino. Na MESMA pasta: `os.replace` entre
#: volumes falha, e o arquivo pode estar num mapeamento de rede.
SUFIXO = ".ewnew"

#: Esperas entre tentativas de troca. Antivírus e indexador do Windows abrem o
#: arquivo por alguns milissegundos logo depois de ele ser escrito, e a troca
#: falha com "acesso negado" que some sozinho.
ESPERAS = (0.0, 0.05, 0.15, 0.40)


class SemEspaco(OSError):
    """Não há espaço para o temporário da troca atômica."""


class FalhaNaTroca(OSError):
    """O temporário foi escrito, mas não substituiu o destino."""


def espaco_livre(caminho) -> int:
    """Bytes livres na unidade do arquivo. -1 quando não dá para saber."""
    try:
        alvo = pathlib.Path(caminho)
        pasta = alvo.parent if alvo.parent.exists() else pathlib.Path(".")
        return shutil.disk_usage(pasta).free
    except OSError:
        return -1


def conferir_espaco(caminho, previsto: int) -> None:
    """Levanta `SemEspaco` ANTES de escrever o primeiro byte.

    Descobrir que faltou disco depois de escrever 200 MB é o pior momento
    possível: o temporário fica pela metade e o usuário perde a tarde.
    """
    livre = espaco_livre(caminho)
    if livre < 0:
        return
    necessario = previsto + FOLGA
    if livre < necessario:
        faltam = max(1, -(-(necessario - livre) // MEGA))
        unidade = pathlib.Path(caminho).drive or "o disco"
        raise SemEspaco(
            f"Falta espaço em {unidade}: faltam cerca de {faltam} MB. "
            "A gravação escreve primeiro um arquivo temporário do mesmo "
            "tamanho, ao lado do original. O arquivo original NÃO foi alterado.")


def gravar_bytes(caminho, dados: bytes,
                 conferir: Callable[[bytes], None] | None = None) -> int:
    """Grava `dados` no lugar de `caminho` com a troca atômica. Devolve os bytes.

    `conferir`, quando dado, recebe o conteúdo RELIDO DO DISCO do temporário,
    antes da troca. Se ele levantar qualquer exceção, a exceção propaga e o
    original não é tocado. É assim que o formato garante que o arquivo que
    vai substituir o original abre de verdade.

    Qualquer falha antes da troca remove o temporário e re-levanta.
    """
    alvo = pathlib.Path(caminho)
    conferir_espaco(alvo, len(dados))
    temporario = alvo.with_name(alvo.name + SUFIXO)
    try:
        with open(temporario, "wb") as saida:
            saida.write(dados)
            saida.flush()
            # fsync ANTES da troca: sem ele, um desligamento entre o write e o
            # replace pode deixar o temporário vazio E já trocado.
            os.fsync(saida.fileno())
        if conferir is not None:
            conferir(temporario.read_bytes())
        _trocar(temporario, alvo)
    finally:
        _remover(temporario)
    log.info("gravado %s (%d bytes, conteúdo pronto)", alvo, len(dados))
    return len(dados)


def _remover(caminho: pathlib.Path) -> None:
    try:
        caminho.unlink(missing_ok=True)
    except OSError as erro:
        log.warning("não foi possível apagar o temporário %s: %s", caminho, erro)


def _trocar(temporario: pathlib.Path, destino: pathlib.Path) -> None:
    """Substitui o destino pelo temporário, com retentativas.

    `ReplaceFileW` é preferido a `os.replace` no Windows: ele PRESERVA dono,
    ACLs, atributos e fluxos alternativos do arquivo original. O `os.replace`
    cria um arquivo novo com as permissões herdadas da pasta -- num arquivo com
    ACE explícita, salvar mudaria quem pode lê-lo.
    """
    ultimo: OSError | None = None
    for espera in ESPERAS:
        if espera:
            time.sleep(espera)
        try:
            if os.name == "nt" and _replace_file_w(temporario, destino):
                return
            os.replace(temporario, destino)
            return
        except OSError as exc:
            ultimo = exc
    raise FalhaNaTroca(_mensagem_da_falha(destino, ultimo)) from ultimo


def _mensagem_da_falha(destino: pathlib.Path, ultimo: OSError | None) -> str:
    if isinstance(ultimo, PermissionError):
        return (f"Não foi possível substituir {destino.name}. "
                "O arquivo parece estar aberto em outro programa. "
                "Feche-o e tente salvar de novo. "
                "O arquivo original NÃO foi alterado.")
    return (f"Não foi possível substituir {destino.name}: {ultimo}. "
            "O arquivo original NÃO foi alterado.")


def _replace_file_w(temporario: pathlib.Path, destino: pathlib.Path) -> bool:
    """`ReplaceFileW` do Windows. False quando não deu (quem chama tenta o resto)."""
    if not destino.exists():
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ReplaceFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
        kernel32.ReplaceFileW.restype = wintypes.BOOL
        # 0x1 = REPLACEFILE_WRITE_THROUGH
        return bool(kernel32.ReplaceFileW(str(destino), str(temporario), None,
                                          0x1, None, None))
    except (OSError, AttributeError, ImportError):
        return False
