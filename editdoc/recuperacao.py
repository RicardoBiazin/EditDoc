"""Recuperacao automatica: copias do documento alterado, para depois de uma queda. Sem Qt.

Onde: `%LOCALAPPDATA%\\EditDoc\\Recuperacao` (a variavel EDITDOC_RECUPERACAO troca a
pasta: e' o que os testes e a autoverificacao usam). Nunca na pasta do documento e
nunca por cima do original: a copia e' um .docx a parte, com nome proprio.

Cada janela tem uma sessao, com um id. A sessao grava tres arquivos:

    <id>.docx    o documento, como estava na ultima gravacao de recuperacao
    <id>.json    metadados: caminho original, nome, hora, versao, pid, avisos com perda
    <id>.trava   a trava: aberta e travada (LockFile) enquanto a janela vive

A trava e' o que separa "janela aberta" de "sobra de uma queda": o Windows solta a
trava quando o processo morre, de qualquer jeito (fechado pelo Gerenciador de
Tarefas, falta de energia nao conta: ai' nem o disco ficou). Outra instancia, ou a
proxima abertura do programa, tenta travar o arquivo: se consegue, o dono morreu e a
copia e' oferecida; se nao consegue, a copia e' de uma janela viva e fica quieta. O pid
vai junto so' para o diagnostico (pid e' reaproveitado pelo Windows; a trava, nao).

Gravacao atomica nos dois arquivos (`armazenamento.gravacao` para o .docx, troca com
os.replace para o .json). O .json e' gravado por ultimo e traz o tamanho do .docx: uma
copia com .docx de outro tamanho e' de uma gravacao interrompida e nao e' oferecida
como boa.

Nada aqui pode atrapalhar o usuario: erro de disco vira log e False, nunca excecao
na cara de quem esta' digitando.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import tempfile
import uuid
from dataclasses import dataclass, field

from editdoc import APP, VERSAO, log_interno
from editdoc.armazenamento import gravacao

log = log_interno.obter(__name__)

VARIAVEL_PASTA = "EDITDOC_RECUPERACAO"
SUBPASTA = "Recuperacao"
#: Intervalo padrao entre gravacoes, em minutos (o mesmo do Word).
INTERVALO_PADRAO_MIN = 10
INTERVALO_MINIMO_MIN = 1
INTERVALO_MAXIMO_MIN = 120
#: Alem do relogio: tantas alteracoes seguidas tambem pedem uma gravacao.
ALTERACOES_PARA_GRAVAR = 300
#: Copia acima disso nao e' lida (protege a abertura contra arquivo estranho na pasta).
TAMANHO_MAXIMO_BYTES = 512 * 1024 * 1024


def pasta() -> pathlib.Path:
    """A pasta das copias, criada se preciso."""
    escolhida = os.environ.get(VARIAVEL_PASTA)
    if escolhida:
        alvo = pathlib.Path(escolhida)
    else:
        base = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
                or tempfile.gettempdir())
        alvo = pathlib.Path(base) / APP / SUBPASTA
    alvo.mkdir(parents=True, exist_ok=True)
    return alvo


def _id_valido(texto: str) -> bool:
    return len(texto) == 32 and all(c in "0123456789abcdef" for c in texto)


# -- trava -----------------------------------------------------------------------------

class Trava:
    """Trava exclusiva de um arquivo, viva enquanto o objeto (e o processo) vive."""

    def __init__(self, caminho: pathlib.Path, fd: int) -> None:
        self.caminho = caminho
        self._fd: int | None = fd

    @classmethod
    def tentar(cls, caminho: pathlib.Path) -> "Trava | None":
        """Trava o arquivo (cria se faltar). None se outro (processo ou janela) ja' trava."""
        try:
            fd = os.open(str(caminho), os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
        except OSError:
            return None
        try:
            _travar(fd)
        except OSError:
            os.close(fd)
            return None
        try:
            # O byte 0 e' o travado; o pid vai depois dele, so' para quem le o arquivo.
            texto = f"{os.getpid()}\n".encode("ascii")
            os.lseek(fd, 1, os.SEEK_SET)
            os.write(fd, texto)
            os.ftruncate(fd, 1 + len(texto))
        except OSError:
            pass
        return cls(caminho, fd)

    def ativa(self) -> bool:
        return self._fd is not None

    def soltar(self, apagar: bool = True) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            _destravar(fd)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        if apagar:
            try:
                self.caminho.unlink(missing_ok=True)
            except OSError:
                pass

    def __del__(self) -> None:  # pragma: no cover - so' quando ninguem soltou
        try:
            self.soltar(apagar=False)
        except Exception:  # noqa: BLE001 - destrutor: nada a fazer
            pass


if os.name == "nt":
    import msvcrt

    def _travar(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _destravar(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:  # pragma: no cover - o programa e' para Windows; isto so' mantem o modulo importavel
    import fcntl

    def _travar(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _destravar(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def em_uso(id_: str, base: pathlib.Path | None = None) -> bool:
    """True se alguma janela viva (deste ou de outro processo) trava a copia `id_`."""
    caminho = (base or pasta()) / f"{id_}.trava"
    if not caminho.exists():
        return False
    trava = Trava.tentar(caminho)
    if trava is None:
        return True
    trava.soltar(apagar=False)
    return False


# -- copia -----------------------------------------------------------------------------

@dataclass
class Copia:
    """Uma copia de recuperacao encontrada na pasta."""
    id: str
    docx: pathlib.Path
    meta: dict = field(default_factory=dict)

    @property
    def nome(self) -> str:
        nome = self.meta.get("nome")
        return nome if isinstance(nome, str) and nome else "Documento em branco"

    @property
    def caminho_original(self) -> str | None:
        c = self.meta.get("caminho_original")
        return c if isinstance(c, str) and c else None

    @property
    def hora(self) -> str:
        h = self.meta.get("hora")
        return h if isinstance(h, str) else ""

    def hora_legivel(self) -> str:
        try:
            quando = _dt.datetime.fromisoformat(self.hora)
        except ValueError:
            return "hora desconhecida"
        return quando.astimezone().strftime("%d/%m/%Y %H:%M")

    def avisos_com_perda(self) -> list[dict]:
        """Avisos do arquivo original que perdem conteudo ao salvar (guardados na copia)."""
        avisos = self.meta.get("avisos")
        if not isinstance(avisos, list):
            return []
        validos = []
        for a in avisos:
            if (isinstance(a, dict) and isinstance(a.get("codigo"), str)
                    and isinstance(a.get("texto"), str) and isinstance(a.get("contagem"), int)):
                validos.append({"codigo": a["codigo"], "texto": a["texto"],
                                "contagem": a["contagem"], "perde_ao_salvar": True})
        return validos

    def ler(self) -> bytes:
        tamanho = self.docx.stat().st_size
        if tamanho > TAMANHO_MAXIMO_BYTES:
            raise OSError("copia de recuperacao grande demais")
        return self.docx.read_bytes()


def _ler_meta(caminho: pathlib.Path) -> dict | None:
    try:
        if caminho.stat().st_size > 1024 * 1024:
            return None
        dado = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dado if isinstance(dado, dict) else None


def listar_orfas(base: pathlib.Path | None = None) -> list[Copia]:
    """Copias que nenhuma janela viva trava: sobras de uma queda. Mais nova primeiro.

    Uma copia sem .json legivel, ou cujo .docx nao tem o tamanho anotado (gravacao
    interrompida), nao e' oferecida; ela fica na pasta para diagnostico.
    """
    base = base or pasta()
    achadas: list[Copia] = []
    try:
        nomes = sorted(base.iterdir())
    except OSError:
        return []
    for docx in nomes:
        if docx.suffix.lower() != ".docx" or not _id_valido(docx.stem):
            continue
        id_ = docx.stem
        if em_uso(id_, base):
            continue
        meta = _ler_meta(base / f"{id_}.json")
        if meta is None:
            continue
        try:
            tamanho = docx.stat().st_size
        except OSError:
            continue
        if meta.get("tamanho") != tamanho:
            log.warning("copia de recuperacao %s incompleta: ignorada", id_)
            continue
        achadas.append(Copia(id=id_, docx=docx, meta=meta))
    achadas.sort(key=lambda c: c.hora, reverse=True)
    return achadas


def _apagar_arquivos(base: pathlib.Path, id_: str) -> None:
    for sufixo in (".json", ".docx", ".docx" + gravacao.SUFIXO, ".json.novo"):
        try:
            (base / f"{id_}{sufixo}").unlink(missing_ok=True)
        except OSError as erro:
            log.warning("nao foi possivel apagar a copia %s%s: %s", id_, sufixo, erro)


def apagar_copia(id_: str, base: pathlib.Path | None = None) -> None:
    """Apaga os arquivos de uma copia orfa (o .docx, o .json e a trava, se livre)."""
    base = base or pasta()
    _apagar_arquivos(base, id_)
    trava = base / f"{id_}.trava"
    if trava.exists() and not em_uso(id_, base):
        try:
            trava.unlink(missing_ok=True)
        except OSError:
            pass


# -- sessao ----------------------------------------------------------------------------

class Sessao:
    """As copias de uma janela. `id_` dado = adotar uma copia orfa (abrir o recuperado)."""

    def __init__(self, base: pathlib.Path | None = None, id_: str | None = None) -> None:
        self._base = base
        self.id = id_ if id_ and _id_valido(id_) else uuid.uuid4().hex
        self._trava: Trava | None = None
        self.gravacoes = 0

    def pasta(self) -> pathlib.Path:
        return self._base or pasta()

    def caminho_docx(self) -> pathlib.Path:
        return self.pasta() / f"{self.id}.docx"

    def travar(self) -> bool:
        """Trava a copia desta sessao. False se outra janela ja' a trava."""
        if self._trava is not None and self._trava.ativa():
            return True
        self._trava = Trava.tentar(self.pasta() / f"{self.id}.trava")
        return self._trava is not None

    def gravar(self, dados: bytes, caminho_original: str | None, nome: str,
               avisos: list | None = None) -> bool:
        """Grava (ou troca) a copia. True se gravou; erro vira log e False."""
        try:
            if not self.travar():
                log.warning("copia de recuperacao %s travada por outra janela", self.id)
                return False
            base = self.pasta()
            gravacao.gravar_bytes(base / f"{self.id}.docx", dados)
            meta = {
                "programa": APP,
                "versao": VERSAO,
                "id": self.id,
                "pid": os.getpid(),
                "caminho_original": caminho_original,
                "nome": nome,
                "hora": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                "tamanho": len(dados),
                "avisos": [_aviso_para_dict(a) for a in (avisos or [])],
            }
            alvo = base / f"{self.id}.json"
            novo = alvo.with_name(alvo.name + ".novo")
            with open(novo, "w", encoding="utf-8") as saida:
                json.dump(meta, saida, ensure_ascii=False, indent=1)
                saida.flush()
                os.fsync(saida.fileno())
            os.replace(novo, alvo)
        except OSError as erro:
            log.warning("gravacao de recuperacao falhou: %s", erro)
            return False
        self.gravacoes += 1
        log.info("copia de recuperacao gravada: %s (%d bytes)", self.id, len(dados))
        return True

    def existe(self) -> bool:
        return self.caminho_docx().exists()

    def descartar(self) -> None:
        """O documento foi salvo (ou descartado de proposito): a copia sai. A trava fica.

        Sessao que nunca travou (nunca gravou nem adotou) nao tem o que apagar, e nao
        cria a pasta a toa.
        """
        if self._trava is None:
            return
        _apagar_arquivos(self.pasta(), self.id)

    def encerrar(self) -> None:
        """Fechamento normal: apaga a copia e solta a trava."""
        self.descartar()
        if self._trava is not None:
            self._trava.soltar(apagar=True)
            self._trava = None


def _aviso_para_dict(aviso) -> dict:
    if isinstance(aviso, dict):
        return aviso
    return {"codigo": getattr(aviso, "codigo", ""), "texto": getattr(aviso, "texto", ""),
            "contagem": getattr(aviso, "contagem", 0),
            "perde_ao_salvar": bool(getattr(aviso, "perde_ao_salvar", False))}


def intervalo_valido(minutos) -> int:
    """O intervalo em minutos, dentro dos limites; fora deles, o padrao."""
    if isinstance(minutos, bool) or not isinstance(minutos, int):
        return INTERVALO_PADRAO_MIN
    if not INTERVALO_MINIMO_MIN <= minutos <= INTERVALO_MAXIMO_MIN:
        return INTERVALO_PADRAO_MIN
    return minutos
