"""Instancia unica: o segundo processo entrega o pedido ao primeiro e sai.

Usa um canal de teste PROPRIO (EDITDOC_CANAL), para nunca falar com uma janela
de EditDoc que o usuario tenha aberta neste instante.

Entregas e quadros crus saem de PROCESSOS FILHOS. O servidor deste processo so'
aceita conexao dentro do laco de eventos do Qt; um cliente no mesmo thread
ficaria esperando um servidor surdo e daria falso defeito. Por isso o pai
processa eventos enquanto o filho roda (`rodar_filho`).

Ordem: preparar_qt() isola o %APPDATA% e cria o QApplication ANTES de qualquer
import do programa (o log_interno escreve no %APPDATA% ao ser importado).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid

from ajudantes import RAIZ, checa, checa_igual, pasta_temporaria, pular, preparar_qt, resumir, secao

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado no venv"))

CANAL_A = f"EditDocTeste-{uuid.uuid4().hex[:8]}"
os.environ["EDITDOC_CANAL"] = CANAL_A

from PySide6.QtTest import QTest  # noqa: E402

from editdoc import instancia_unica as iu  # noqa: E402

# ---------------------------------------------------------------------------
# Codigo dos processos filhos (sempre texto fixo do teste, nunca dado do usuario)
# ---------------------------------------------------------------------------

_PREAMBULO = (
    "import sys, json\n"
    f"sys.path.insert(0, {str(RAIZ)!r})\n"
    "from PySide6.QtCore import QCoreApplication\n"
    "app = QCoreApplication([])\n"
    "from editdoc import instancia_unica as iu\n"
)

#: Entrega um pedido (JSON em argv[1]) e imprime True/False.
CODIGO_ENTREGAR = _PREAMBULO + "print(iu.entregar(json.loads(sys.argv[1])), flush=True)\n"

#: Escreve os bytes do arquivo argv[2] crus no canal argv[1]. Imprime se conectou.
CODIGO_ESCREVER_BRUTO = (
    "import sys, time\n"
    "from PySide6.QtCore import QCoreApplication\n"
    "from PySide6.QtNetwork import QLocalSocket\n"
    "app = QCoreApplication([])\n"
    "dados = open(sys.argv[2], 'rb').read()\n"
    "soq = QLocalSocket()\n"
    "soq.connectToServer(sys.argv[1])\n"
    "ok = soq.waitForConnected(5000)\n"
    "if ok:\n"
    "    soq.write(dados)\n"
    "    fim = time.monotonic() + 30\n"
    "    while soq.bytesToWrite() > 0 and time.monotonic() < fim:\n"
    "        if soq.state() == QLocalSocket.LocalSocketState.UnconnectedState:\n"
    "            break\n"
    "        soq.waitForBytesWritten(200)\n"
    "print(ok, flush=True)\n"
)

#: Assume o canal e o segura ate' a entrada padrao fechar. Imprime ASSUMIU/NEGADO.
CODIGO_SEGURAR = _PREAMBULO + (
    "servidor = iu.Servidor()\n"
    "if not servidor.escutar():\n"
    "    print('NEGADO', flush=True)\n"
    "    sys.exit(0)\n"
    "print('ASSUMIU', flush=True)\n"
    "sys.stdin.read()\n"
)


def _ambiente(canal: str) -> dict:
    ambiente = dict(os.environ)
    ambiente["EDITDOC_CANAL"] = canal
    ambiente["QT_QPA_PLATFORM"] = "offscreen"
    return ambiente


def rodar_filho(codigo: str, *argumentos: str, canal: str = CANAL_A,
                prazo: float = 40.0) -> tuple[int, str]:
    """Roda um filho e processa eventos enquanto ele vive. (codigo, saida)."""
    proc = subprocess.Popen([sys.executable, "-c", codigo, *argumentos],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env=_ambiente(canal))
    fim = time.monotonic() + prazo
    while proc.poll() is None and time.monotonic() < fim:
        QTest.qWait(10)
    if proc.poll() is None:
        proc.kill()
    saida, _ = proc.communicate()
    return proc.returncode, saida.decode("utf-8", errors="replace").strip()


def esperar(condicao, prazo: float = 5.0) -> bool:
    """Processa eventos ate' a condicao valer, ou o prazo acabar."""
    fim = time.monotonic() + prazo
    while not condicao():
        if time.monotonic() >= fim:
            return False
        QTest.qWait(10)
    return True


def deixar_passar(segundos: float) -> None:
    """Processa eventos durante um tempo. Pedido negativo precisa desta janela."""
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        QTest.qWait(10)


def _linha(filho: subprocess.Popen) -> str:
    """A primeira linha que o filho imprimiu, como texto."""
    return filho.stdout.readline().decode("utf-8", errors="replace").strip()


def entregar_de_outro_processo(pedido: dict, canal: str = CANAL_A) -> tuple[int, str]:
    return rodar_filho(CODIGO_ENTREGAR, json.dumps(pedido, ensure_ascii=False),
                       canal=canal)


def quadro(corpo: bytes, tamanho: int | None = None) -> bytes:
    """Cabecalho de 4 bytes big-endian + corpo. `tamanho` forca um cabecalho mentiroso."""
    n = len(corpo) if tamanho is None else tamanho
    return n.to_bytes(4, "big") + corpo


def corpo_com_tamanho(alvo: int) -> bytes:
    """Objeto JSON valido com exatamente `alvo` bytes (preenchimento ASCII)."""
    base = {"arquivos": ["C:\\grande.docx"], "preenchimento": ""}
    minimo = len(json.dumps(base, ensure_ascii=False).encode("utf-8"))
    base["preenchimento"] = "x" * (alvo - minimo)
    return json.dumps(base, ensure_ascii=False).encode("utf-8")


def enviar_quadro(pasta, dados: bytes, canal: str = CANAL_A) -> bool:
    """Um filho conecta e escreve os bytes crus. True se a conexao abriu."""
    arquivo = pasta / f"quadro-{uuid.uuid4().hex[:6]}.bin"
    arquivo.write_bytes(dados)
    codigo, saida = rodar_filho(CODIGO_ESCREVER_BRUTO, canal, str(arquivo), canal=canal)
    return codigo == 0 and saida == "True"


def canais_com_pedido_indevido(recebidos_por_canal: dict[str, list], destino: str) -> list[str]:
    """Canais, que NAO o de destino, que receberam algum pedido. Funcao pura."""
    return sorted(canal for canal, lista in recebidos_por_canal.items()
                  if canal != destino and lista)


# ---------------------------------------------------------------------------
# Cenarios
# ---------------------------------------------------------------------------

def testar_sem_servidor() -> None:
    secao("sem servidor: ninguem no canal, entregar devolve False")
    checa_igual(iu.entregar({"arquivos": ["C:\\nada.docx"]}), False,
                "entregar sem instancia aberta devolve False")


def testar_guarda_no_processo(servidor: iu.Servidor) -> None:
    secao("guarda: a primeira instancia assume; a segunda, no mesmo processo, nao")
    checa(servidor.escutar(), "o primeiro Servidor assume o canal")
    outro = iu.Servidor()
    checa_igual(outro.escutar(), False,
                "um segundo Servidor no mesmo canal devolve False enquanto o primeiro vive")


def testar_guarda_entre_processos(recebidos_a: list[dict]) -> None:
    secao("guarda entre PROCESSOS: o canal ocupado por este processo nao e' assumido")
    filho = subprocess.Popen([sys.executable, "-c", CODIGO_SEGURAR], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             env=_ambiente(CANAL_A))
    resposta = _linha(filho)
    checa_igual(resposta, "NEGADO",
                "um processo filho NAO assume o canal enquanto este processo o tem")
    filho.wait(timeout=20)


def testar_entrega_de_outro_processo(recebidos_a: list[dict]) -> None:
    secao("entrega de outro PROCESSO: os caminhos chegam inteiros e identicos")
    with pasta_temporaria() as tmp:
        # Caminhos LONGOS de proposito: o defeito classico e' a mensagem chegar em
        # pedacos, e com caminhos curtos ela cabe num pacote so' e o defeito some.
        nomes = [str(tmp / (f"arquivo_com_nome_bem_longo_{n:03d}_" + "x" * 60 + ".docx"))
                 for n in range(12)]
        pedido = {"arquivos": nomes}
        codigo, saida = entregar_de_outro_processo(pedido)
        checa_igual(saida, "True", "o outro processo entregou e devolveu True")
        checa(esperar(lambda: len(recebidos_a) >= 1), "o sinal pedido_recebido chega aqui")
        checa_igual(recebidos_a[-1] if recebidos_a else None, pedido,
                    "o pedido chegou INTEIRO: os 12 caminhos, identicos")

    checa_igual(entregar_de_outro_processo({"arquivos": ["C:\\x.docx"]}, canal=CANAL_A + "-SEM-DONO")[1],
                "False", "canal sem ninguem escutando: o outro processo recebe False")


def testar_tamanho(pasta, recebidos: list[dict]) -> None:
    secao("tamanho: acima de 1 MB e descartado; exatamente 1 MB passa")
    base = len(recebidos)
    checa(enviar_quadro(pasta, quadro(corpo_com_tamanho(1_000_001))),
          "quadro de 1.000.001 bytes foi enviado")
    deixar_passar(0.8)
    checa_igual(len(recebidos), base, "pedido de 1.000.001 bytes NAO chega ao sinal")
    checa(enviar_quadro(pasta, quadro(corpo_com_tamanho(1_000_000))),
          "quadro de 1.000.000 bytes foi enviado")
    # Contraprova: o mesmo caminho ENTREGA dentro do teto. Sem isto, o silencio
    # acima poderia ser um servidor morto.
    checa(esperar(lambda: len(recebidos) == base + 1, prazo=10.0),
          "pedido de exatamente 1.000.000 bytes CHEGA (o teto e' esse)")


def testar_corpo_invalido(pasta, recebidos: list[dict]) -> None:
    secao("corpo: o que nao e' objeto JSON, ou nao e' JSON, e' descartado")
    casos = [
        ("lista JSON", quadro(b"[1, 2]")),
        ("texto JSON", quadro(b'"so texto"')),
        ("JSON truncado", quadro(b'{"arquivos": ')),
        ("bytes que nao sao UTF-8", quadro(b"\xff\xfe\x00")),
        ("cabecalho zero", quadro(b"", tamanho=0)),
    ]
    for rotulo, dados in casos:
        base = len(recebidos)
        enviar_quadro(pasta, dados)
        deixar_passar(0.6)
        checa_igual(len(recebidos), base, f"{rotulo} e' descartado")

    depois = {"arquivos": ["C:\\depois.docx"]}
    checa(enviar_quadro(pasta, quadro(json.dumps(depois).encode("utf-8")))
          and esperar(lambda: bool(recebidos) and recebidos[-1] == depois, prazo=10.0),
          "depois de todos os descartes, o servidor ainda entrega um pedido valido")


def testar_canais(servidor_a: iu.Servidor, recebidos_a: list[dict]) -> None:
    secao("canais: cada pedido chega so' ao canal para o qual foi entregue")
    canal_b = CANAL_A + "-B"
    recebidos_b: list[dict] = []
    servidor_b = iu.Servidor()
    servidor_b.pedido_recebido.connect(recebidos_b.append)
    try:
        os.environ["EDITDOC_CANAL"] = canal_b
        checa(servidor_b.escutar(), "um segundo canal, com outro nome, pode ser assumido")
        os.environ["EDITDOC_CANAL"] = CANAL_A

        para_a = {"arquivos": ["C:\\so_para_a.docx"]}
        checa_igual(entregar_de_outro_processo(para_a, canal=CANAL_A)[1], "True",
                    "entregar ao canal A devolve True")
        checa(esperar(lambda: para_a in recebidos_a), "o servidor A recebe o pedido dele")
        deixar_passar(0.3)
        checa_igual(recebidos_b, [], "o servidor do canal B NAO recebe o que foi para A")

        para_b = {"arquivos": ["C:\\so_para_b.docx"]}
        checa_igual(entregar_de_outro_processo(para_b, canal=canal_b)[1], "True",
                    "entregar ao canal B devolve True")
        checa(esperar(lambda: para_b in recebidos_b), "o servidor B recebe o pedido dele")
        checa(para_b not in recebidos_a, "o servidor A NAO recebe o que foi para B")
    finally:
        os.environ["EDITDOC_CANAL"] = CANAL_A
        servidor_b.parar()

    secao("sabotagem: o checador de canal ACUSA um pedido no canal errado")
    checa_igual(canais_com_pedido_indevido({CANAL_A: [para_a], canal_b: []}, CANAL_A), [],
                "o caso correto passa no checador")
    checa_igual(canais_com_pedido_indevido({CANAL_A: [], canal_b: [para_a]}, CANAL_A),
                [canal_b], "um pedido que caiu no canal B, com destino A, e' ACUSADO")


def testar_sabotagem_do_mutex() -> None:
    secao("sabotagem: sem o mutex, o segundo escutar VIRA True (o defeito existe)")
    canal = CANAL_A + "-SABOTAGEM"
    original = iu.Servidor._reservar
    iu.Servidor._reservar = lambda self: True
    os.environ["EDITDOC_CANAL"] = canal
    primeiro = iu.Servidor()
    segundo = iu.Servidor()
    try:
        primeiro.escutar()
        obtido = segundo.escutar()
    finally:
        iu.Servidor._reservar = original
        os.environ["EDITDOC_CANAL"] = CANAL_A
        primeiro.parar()
        segundo.parar()
    checa_igual(obtido, True,
                "sem o mutex o Qt aceita o segundo listen: a checagem de guarda TEM o que acusar")


def testar_parar_e_retomar(servidor_a: iu.Servidor) -> None:
    secao("parar() libera o canal, e o mutex vai junto com o processo que o segurava")
    servidor_a.parar()
    filho = subprocess.Popen([sys.executable, "-c", CODIGO_SEGURAR], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             env=_ambiente(CANAL_A))
    checa_igual(_linha(filho), "ASSUMIU",
                "depois de parar(), outro processo assume o canal")
    outro = iu.Servidor()
    checa_igual(outro.escutar(), False,
                "com o filho segurando o canal, este processo NAO assume")
    filho.stdin.close()
    filho.wait(timeout=20)
    checa_igual(outro.escutar(), True,
                "quando o filho sai, o canal fica livre e este processo assume")
    outro.parar()


def main() -> int:
    testar_sem_servidor()

    servidor = iu.Servidor()
    recebidos: list[dict] = []
    servidor.pedido_recebido.connect(recebidos.append)

    testar_guarda_no_processo(servidor)
    testar_guarda_entre_processos(recebidos)
    testar_entrega_de_outro_processo(recebidos)
    with pasta_temporaria() as pasta:
        testar_tamanho(pasta, recebidos)
        testar_corpo_invalido(pasta, recebidos)
    testar_canais(servidor, recebidos)
    testar_sabotagem_do_mutex()
    testar_parar_e_retomar(servidor)
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
