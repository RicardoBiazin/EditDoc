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
import secrets
import shutil
import stat
import time
from collections.abc import Callable

from editdoc import log_interno
from editdoc.cli import DISPOSITIVOS

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


class DestinoInvalido(OSError):
    """O destino não é um arquivo comum que se possa gravar (0.1.39)."""


def validar_destino(caminho) -> None:
    """Recusa, ANTES de escrever, o destino que não é um arquivo comum.

    - dispositivo do Windows (`CON`, `NUL`, `COM1`, `LPT1`...), com ou sem extensão, com ponto
      ou espaço no fim (o Windows os ignora: `nul.` e `nul ` são o `NUL`), e o prefixo de
      dispositivos e pipes (barra invertida dupla, ponto, barra invertida): gravar nele não
      grava arquivo, e reler o temporário trava;
    - fluxo alternativo de dados (`arquivo.docx:oculto`): o conteúdo iria para um fluxo
      escondido, e o arquivo visível ficaria como estava;
    - caractere de controle no nome;
    - destino que já existe e é uma pasta ou outro tipo de objeto.
    """
    texto = os.fspath(caminho)
    if not isinstance(texto, str) or not texto.strip():
        raise DestinoInvalido("O nome do arquivo está vazio.")
    if any(ord(c) < 32 for c in texto):
        raise DestinoInvalido("O nome do arquivo tem caracteres inválidos.")
    normal = texto.replace(chr(92), "/")
    if normal.startswith("//./"):
        raise DestinoInvalido("Este destino é um dispositivo do Windows, e não um arquivo.")
    sem_prefixo = normal[4:] if normal.startswith("//?/") else normal
    _unidade, resto = os.path.splitdrive(sem_prefixo)
    if ":" in resto:
        raise DestinoInvalido("O nome do arquivo não pode ter dois-pontos (fluxo alternativo "
                              "de dados do Windows).")
    nome = sem_prefixo.rstrip("/").rsplit("/", 1)[-1]
    if nome.rstrip(" .").split(".")[0].strip().lower() in DISPOSITIVOS:
        raise DestinoInvalido("Este nome é reservado pelo Windows (dispositivo): escolha outro.")
    try:
        existente = os.stat(texto)
    except OSError:
        return  # nao existe (ou nao da' para ver): a gravacao acusa o que for
    if not stat.S_ISREG(existente.st_mode):
        raise DestinoInvalido("O destino existe, mas não é um arquivo comum (é uma pasta ou "
                              "um dispositivo).")


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
    validar_destino(caminho)
    alvo = pathlib.Path(caminho)
    conferir_espaco(alvo, len(dados))
    temporario, saida = _criar_temporario(alvo)
    try:
        with saida:
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


def _criar_temporario(alvo: pathlib.Path):
    """(caminho, arquivo aberto) do temporário, criado com exclusividade (0.1.39).

    Aberto com "xb": se o nome já existe, NÃO se escreve nele. Um `documento.docx.ewnew`
    plantado na pasta (link físico para outro arquivo, atalho de pasta, link simbólico) seria
    seguido pelo "wb" e truncaria o arquivo da vítima. Sobra de uma queda do próprio programa
    (arquivo comum, um só nome, sem ponto de reanálise) é apagada e o nome é reusado; o resto
    fica onde está e o temporário ganha um nome único.
    """
    base = alvo.name + SUFIXO
    for tentativa in range(20):
        nome = base if tentativa == 0 else f"{alvo.name}.{secrets.token_hex(4)}{SUFIXO}"
        caminho = alvo.with_name(nome)
        try:
            return caminho, open(caminho, "xb")
        except FileExistsError:
            if tentativa == 0 and _sobra_nossa(caminho):
                _remover(caminho)
                try:
                    return caminho, open(caminho, "xb")
                except FileExistsError:
                    pass
        except PermissionError:
            if not caminho.exists():
                raise  # pasta sem permissao de escrita: a retentativa nao muda nada
    raise FileExistsError("Não foi possível criar o arquivo temporário ao lado do destino.")


def _sobra_nossa(caminho: pathlib.Path) -> bool:
    """O temporário que existe é uma sobra comum nossa: arquivo regular, de um só nome."""
    try:
        info = os.lstat(caminho)
    except OSError:
        return False
    ponto_de_reanalise = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    atributos = getattr(info, "st_file_attributes", 0)
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and not atributos & ponto_de_reanalise)


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


def _somente_leitura(destino: pathlib.Path) -> bool:
    """O destino tem a marca de somente leitura (a falha da troca nao e' 'aberto em outro
    programa', e a mensagem certa muda o que o usuario faz)."""
    try:
        return not os.access(destino, os.W_OK)
    except OSError:
        return False


def _mensagem_da_falha(destino: pathlib.Path, ultimo: OSError | None) -> str:
    if isinstance(ultimo, PermissionError) and _somente_leitura(destino):
        return (f"{destino.name} é um arquivo somente leitura. Tire a marca de somente leitura "
                "nas propriedades do arquivo, ou salve com outro nome. "
                "O arquivo original NÃO foi alterado.")
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
