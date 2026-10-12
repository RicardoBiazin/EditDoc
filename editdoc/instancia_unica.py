"""Uma janela só: o segundo processo entrega o pedido ao primeiro e sai.

Sem isto, selecionar 12 arquivos no Explorer e mandar "Abrir com" dispara **12
processos**, cada um com seu Qt e sua janela. Com a janela já aberta, o certo
é o contrário: o pedido vai para ela, que decide o que fazer com os arquivos.

Como funciona: o primeiro processo abre um `QLocalServer` -- um *named pipe* no
Windows -- com um nome derivado do usuário. Quem vier depois tenta se conectar;
conseguindo, manda o pedido e **sai sem abrir janela**.

TRÊS DETALHES QUE JÁ CUSTARAM DEFEITO EM PROJETOS ASSIM:

**O canal é POR USUÁRIO.** Dois usuários na mesma máquina (ou uma sessão de
área de trabalho remota) têm processos separados e não devem se atropelar --
entregar o arquivo de um na janela do outro seria vazamento de conteúdo.

**Um pipe órfão não pode travar a abertura.** Se o programa morreu sem fechar o
canal, o nome continua registrado e o `listen()` falha. Nesse caso o servidor
remove o nome e tenta de novo; se ainda assim não der, o programa **abre
normalmente** como instância comum. Ficar sem abrir por causa de um pipe é
desproporcional.

**O pedido chega em pedaços.** Um named pipe não garante que a mensagem venha
inteira num `readyRead`. Sem um cabeçalho de tamanho, abrir 12 arquivos com
caminhos longos entregaria o último caminho cortado ao meio -- e o editor
tentaria abrir um arquivo que não existe.
"""

from __future__ import annotations

import getpass
import json
import os

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from editdoc import log_interno

log = log_interno.obter(__name__)

APP = "EditDoc"

#: Espera de CADA tentativa de conexão, em milissegundos.
ESPERA_MS = 700

#: Quantas tentativas antes de desistir e abrir janela própria.
#:
#: Mais de uma porque a outra instância pode estar OCUPADA -- salvando um
#: documento grande, por exemplo -- e demorar para voltar à fila de eventos, que
#: é onde o `QLocalServer` aceita a conexão. Com uma tentativa só, o segundo
#: processo desistia e abria uma janela paralela, que é justamente o que este
#: módulo existe para evitar.
TENTATIVAS = 3

#: Variável de ambiente que TROCA o nome do canal.
#:
#: Existe para os TESTES. Sem ela a suíte usaria o canal de produção -- o mesmo
#: do programa que o usuário pode ter aberto neste instante --, e um teste de
#: "ninguém escutando" falharia só porque HÁ alguém: a janela de verdade.
VARIAVEL_DO_CANAL = "EDITDOC_CANAL"


def nome_do_canal() -> str:
    """Canal por usuário. Ver o cabeçalho."""
    forcado = os.environ.get(VARIAVEL_DO_CANAL)
    if forcado:
        return forcado
    try:
        usuario = getpass.getuser()
    except Exception:                     # noqa: BLE001 - depende do ambiente
        usuario = "desconhecido"
    seguro = "".join(c if c.isalnum() else "_" for c in usuario)
    return f"{APP}-{seguro}"


#: Erro do Windows: o mutex JA existia, isto e', outro processo o criou antes.
_ERRO_JA_EXISTE = 183


def _kernel32():
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    return k32


def _criar_mutex(nome: str) -> tuple[int, bool]:
    """Mutex nomeado do Windows. Devolve (handle, ja_existia).

    O mutex morre junto com o processo que o segura: um processo que caiu não
    deixa o canal preso, então o pipe órfão deixa de ser um caso a tratar aqui.
    """
    import ctypes

    k32 = _kernel32()
    handle = k32.CreateMutexW(None, False, nome)
    erro = ctypes.get_last_error()   # capturado logo apos a chamada
    if not handle:
        raise OSError(erro, "CreateMutexW falhou")
    return handle, erro == _ERRO_JA_EXISTE


def _fechar_mutex(handle: int) -> None:
    _kernel32().CloseHandle(handle)


def _empacotar(pedido: dict) -> bytes:
    """Mensagem com cabeçalho de tamanho (4 bytes, big-endian) e corpo JSON."""
    corpo = json.dumps(pedido, ensure_ascii=False).encode("utf-8")
    return len(corpo).to_bytes(4, "big") + corpo


def entregar(pedido: dict) -> bool:
    """Entrega o pedido a uma instância já aberta. False se não havia nenhuma.

    Tenta `TENTATIVAS` vezes: a outra instância pode estar ocupada e demorar a
    voltar à fila de eventos. Desistir cedo abriria uma segunda janela --
    exatamente o que este módulo evita.
    """
    for tentativa in range(1, TENTATIVAS + 1):
        soquete = QLocalSocket()
        soquete.connectToServer(nome_do_canal())
        if not soquete.waitForConnected(ESPERA_MS):
            soquete.abort()
            if tentativa < TENTATIVAS:
                # Espera curta e crescente: se ninguém estiver escutando, a
                # conexão falha na hora e as três tentativas custam quase nada.
                QThread.msleep(120 * tentativa)
                continue
            return False

        soquete.write(_empacotar(pedido))
        soquete.flush()
        entregue = soquete.waitForBytesWritten(ESPERA_MS)
        soquete.disconnectFromServer()
        if entregue:
            log.info("pedido entregue a uma instância já aberta (tentativa %d)",
                     tentativa)
            return True
        if tentativa >= TENTATIVAS:
            return False
    return False


class Servidor(QObject):
    """Escuta pedidos de outras instâncias e os repassa para a janela."""

    #: O pedido recebido: {"arquivos": [...]}
    pedido_recebido = Signal(dict)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._servidor: QLocalServer | None = None
        self._mutex: int | None = None
        self._parciais: dict[QLocalSocket, bytearray] = {}

    def _reservar(self) -> bool:
        """Assume o canal entre processos. False se outro processo já o tem.

        O `listen()` SOZINHO não basta: medido com o Qt 6.11 no Windows, um
        segundo `QLocalServer.listen()` no mesmo nome devolve True enquanto o
        primeiro vive. Sem este mutex, duas instâncias que abrissem ao mesmo
        tempo seriam duas janelas. Se o Windows não der o mutex, o programa
        segue sem essa proteção, em vez de não abrir.
        """
        if os.name != "nt":
            return True
        try:
            handle, ja_existia = _criar_mutex(f"Local\\{nome_do_canal()}")
        except OSError as erro:
            log.warning("sem mutex do canal (%s); o programa segue sem essa "
                        "proteção", erro)
            return True
        if ja_existia:
            _fechar_mutex(handle)
            return False
        self._mutex = handle
        return True

    def _soltar_mutex(self) -> None:
        if self._mutex is not None:
            _fechar_mutex(self._mutex)
            self._mutex = None

    def escutar(self) -> bool:
        """Assume o canal. False quando outra instância já o tem."""
        if not self._reservar():
            log.info("outra instância já tem o canal %r", nome_do_canal())
            return False
        servidor = QLocalServer(self)
        # `WorldAccess` NÃO: o canal é por usuário, e abri-lo para todo mundo
        # deixaria outra conta entregar arquivos nesta janela.
        servidor.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)

        if not servidor.listen(nome_do_canal()):
            # Pipe órfão de um processo que morreu sem fechar. Remover o nome e
            # tentar de novo é seguro: se houvesse alguém escutando de verdade,
            # `entregar()` teria funcionado antes de chegarmos aqui.
            QLocalServer.removeServer(nome_do_canal())
            if not servidor.listen(nome_do_canal()):
                log.warning("não foi possível assumir o canal %r: %s. O "
                            "programa abre como instância comum.",
                            nome_do_canal(), servidor.errorString())
                self._soltar_mutex()
                return False
            log.info("canal órfão removido e reassumido")

        servidor.newConnection.connect(self._ao_conectar)
        self._servidor = servidor
        log.info("escutando em %s", nome_do_canal())
        return True

    def parar(self) -> None:
        if self._servidor is not None:
            self._servidor.close()
            self._servidor = None
        self._soltar_mutex()

    # ==================================================================

    def _ao_conectar(self) -> None:
        while self._servidor and self._servidor.hasPendingConnections():
            soquete = self._servidor.nextPendingConnection()
            if soquete is None:
                continue
            self._parciais[soquete] = bytearray()
            soquete.readyRead.connect(lambda s=soquete: self._ao_ler(s))
            soquete.disconnected.connect(lambda s=soquete: self._descartar(s))

    def _ao_ler(self, soquete: QLocalSocket) -> None:
        buffer = self._parciais.get(soquete)
        if buffer is None:
            return
        buffer.extend(bytes(soquete.readAll().data()))

        # Enquanto não chegou o cabeçalho inteiro, ou o corpo que ele anuncia,
        # não há mensagem completa: esperar é o certo.
        if len(buffer) < 4:
            return
        tamanho = int.from_bytes(buffer[:4], "big")
        if tamanho <= 0 or tamanho > 1_000_000:
            log.warning("pedido com tamanho implausível (%d); descartado",
                        tamanho)
            self._descartar(soquete)
            return
        if len(buffer) < 4 + tamanho:
            return

        corpo = bytes(buffer[4:4 + tamanho])
        self._descartar(soquete)
        try:
            pedido = json.loads(corpo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as erro:
            # Lixo no canal não pode derrubar o editor: outro programa pode ter
            # se conectado por engano a um pipe de nome parecido.
            log.warning("pedido ilegível no canal: %s", erro)
            return
        if isinstance(pedido, dict):
            log.info("pedido recebido de outra instância: %s",
                     pedido.get("arquivos"))
            self.pedido_recebido.emit(pedido)
        else:
            log.warning("pedido que não é objeto JSON; descartado")

    def _descartar(self, soquete: QLocalSocket) -> None:
        self._parciais.pop(soquete, None)
        soquete.close()
        soquete.deleteLater()
