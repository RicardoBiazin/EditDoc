"""Gravacao atomica de bytes prontos: o original sobrevive a toda falha. Sem Qt."""

from __future__ import annotations

import contextlib
import os
import shutil
from collections import namedtuple

from ajudantes import checa, checa_igual, checa_levanta, isolar_appdata, pasta_temporaria, resumir, secao

isolar_appdata()

from editdoc.armazenamento import gravacao  # noqa: E402
from editdoc.armazenamento.gravacao import FalhaNaTroca, SemEspaco  # noqa: E402

# Sem dormir entre as tentativas: as retentativas continuam acontecendo, so'
# nao custam tempo. O teste conta essas tentativas.
gravacao.ESPERAS = (0.0, 0.0, 0.0, 0.0)

DISCO_CHEIO = namedtuple("DiscoCheio", "total used free")
ANTIGO = b"conteudo antigo do documento"


@contextlib.contextmanager
def trocado(objeto, nome: str, valor):
    """Troca um atributo e devolve no fim, mesmo se o teste estourar."""
    original = getattr(objeto, nome)
    setattr(objeto, nome, valor)
    try:
        yield
    finally:
        setattr(objeto, nome, original)


def capturar(funcao, *args, **kwargs):
    """A excecao levantada por `funcao`, ou None."""
    try:
        funcao(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 - o teste quer ver qual foi
        return exc
    return None


def original_com(pasta, conteudo: bytes = ANTIGO):
    destino = pasta / "documento.docx"
    destino.write_bytes(conteudo)
    return destino


def sem_temporario(destino) -> bool:
    return not destino.with_name(destino.name + gravacao.SUFIXO).exists()


def testar_novo_e_substituir() -> None:
    secao("novo arquivo e substituicao de um existente")
    with pasta_temporaria() as pasta:
        novo = pasta / "novo.docx"
        dados = b"PK\x03\x04 bytes prontos do novo documento"
        n = gravacao.gravar_bytes(str(novo), dados)  # aceita str, nao so' Path
        checa_igual(n, len(dados), "devolve o numero de bytes gravados")
        checa_igual(novo.read_bytes(), dados, "arquivo novo tem exatamente os bytes")
        checa(sem_temporario(novo), "nenhum .ewnew sobra depois de gravar")

        destino = original_com(pasta)
        dados_novos = b"substituido"
        gravacao.gravar_bytes(destino, dados_novos)
        checa_igual(destino.read_bytes(), dados_novos,
                    "o existente e' substituido pelos bytes novos")
        checa(sem_temporario(destino), "a substituicao nao deixa .ewnew")


def testar_conferir() -> None:
    secao("conferir: recebe o que foi para o DISCO, antes da troca")
    with pasta_temporaria() as pasta:
        destino = original_com(pasta)
        dados = b"bytes que vao para o disco" * 100
        vistos: list[tuple[bytes, bytes]] = []

        def coletor(lidos: bytes) -> None:
            # Quando conferir roda, o original AINDA e' o antigo: a troca vem depois.
            vistos.append((lidos, destino.read_bytes()))

        gravacao.gravar_bytes(destino, dados, conferir=coletor)
        checa_igual(len(vistos), 1, "conferir roda exatamente uma vez")
        checa_igual(vistos[0][0], dados, "conferir recebe os bytes RELIDOS do temporario")
        checa_igual(vistos[0][1], ANTIGO, "quando conferir roda, o original ainda esta intacto")
        checa_igual(destino.read_bytes(), dados, "depois de conferir passar, a troca acontece")

        destino2 = original_com(pasta)

        def recusa(lidos: bytes) -> None:
            raise ValueError("o que esta no disco nao confere")

        capturado = capturar(gravacao.gravar_bytes, destino2, b"novo", conferir=recusa)
        checa(isinstance(capturado, ValueError),
              "a excecao de conferir PROPAGA para quem gravou")
        checa_igual(destino2.read_bytes(), ANTIGO, "conferir que falha deixa o original intacto")
        checa(sem_temporario(destino2), "conferir que falha nao deixa .ewnew")


def testar_falha_na_troca() -> None:
    secao("falha na troca: o original fica intacto e o temporario some")
    with pasta_temporaria() as pasta:
        destino = original_com(pasta)

        def troca_falha(temporario, alvo):
            raise FalhaNaTroca("simulado")

        with trocado(gravacao, "_trocar", troca_falha):
            checa_levanta(FalhaNaTroca, gravacao.gravar_bytes,
                          "FalhaNaTroca da troca propaga", destino, b"novo")
        checa_igual(destino.read_bytes(), ANTIGO, "original intacto apos falha na troca")
        checa(sem_temporario(destino), "nenhum .ewnew sobra apos falha na troca")


def testar_falha_na_escrita() -> None:
    secao("falha no fsync: o original fica intacto e o temporario some")
    with pasta_temporaria() as pasta:
        destino = original_com(pasta)

        def fsync_falha(fd):
            raise OSError(28, "disco cheio (simulado)")

        with trocado(os, "fsync", fsync_falha):
            checa_levanta(OSError, gravacao.gravar_bytes,
                          "OSError no fsync propaga", destino, b"novo")
        checa_igual(destino.read_bytes(), ANTIGO, "original intacto apos falha na escrita")
        checa(sem_temporario(destino), "nenhum .ewnew sobra apos falha na escrita")


def testar_sem_espaco() -> None:
    secao("espaco: falta de disco e' acusada ANTES de escrever o primeiro byte")
    with pasta_temporaria() as pasta:
        destino = original_com(pasta)
        chamadas_fsync: list[int] = []
        fsync_real = os.fsync

        def fsync_espiao(fd):
            chamadas_fsync.append(fd)
            return fsync_real(fd)

        pouco = DISCO_CHEIO(total=10**12, used=10**12 - 1000, free=1000)
        with trocado(shutil, "disk_usage", lambda caminho: pouco), \
                trocado(os, "fsync", fsync_espiao):
            capturado = capturar(gravacao.gravar_bytes, destino, b"x" * 10)
        checa(isinstance(capturado, SemEspaco), "disco com 1000 bytes livres levanta SemEspaco")
        checa("Falta espaço" in str(capturado),
              "a mensagem de SemEspaco esta em portugues com acentos")
        checa_igual(chamadas_fsync, [],
                    "nenhum byte foi escrito (fsync nunca chamado): a conferencia e' ANTES")
        checa_igual(destino.read_bytes(), ANTIGO, "original intacto quando falta espaco")
        checa(sem_temporario(destino), "nenhum .ewnew criado quando falta espaco")

        folgado = DISCO_CHEIO(total=10**12, used=0, free=10**12)
        with trocado(shutil, "disk_usage", lambda caminho: folgado):
            sem_erro = capturar(gravacao.conferir_espaco, destino, 10)
        checa_igual(sem_erro, None,
                    "contraprova: com espaco de sobra conferir_espaco nao levanta")

        def disco_desconhecido(caminho):
            raise OSError("unidade sem resposta (simulado)")

        with trocado(shutil, "disk_usage", disco_desconhecido):
            checa_igual(gravacao.espaco_livre(destino), -1,
                        "espaco_livre devolve -1 quando nao da' para saber")
            sem_erro = capturar(gravacao.conferir_espaco, destino, 10**12)
        checa_igual(sem_erro, None,
                    "com espaco desconhecido (-1) conferir_espaco nao bloqueia a gravacao")


def testar_permissao_na_troca() -> None:
    secao("arquivo aberto em outro programa: mensagem clara, original intacto")
    with pasta_temporaria() as pasta:
        destino = original_com(pasta)
        tentativas: list[str] = []

        def replace_negado(origem, alvo):
            tentativas.append(str(origem))
            raise PermissionError(13, "Acesso negado (simulado)")

        with trocado(gravacao, "_replace_file_w", lambda t, d: False), \
                trocado(os, "replace", replace_negado):
            capturado = capturar(gravacao.gravar_bytes, destino, b"novo")

        checa(isinstance(capturado, FalhaNaTroca),
              "PermissionError na troca vira FalhaNaTroca")
        checa("O arquivo parece estar aberto em outro programa" in str(capturado),
              "a mensagem diz que o arquivo parece estar aberto em outro programa")
        checa("O arquivo original NÃO foi alterado" in str(capturado),
              "a mensagem garante que o original nao foi alterado")
        checa_igual(len(tentativas), len(gravacao.ESPERAS),
                    "a troca foi retentada em todas as esperas antes de desistir")
        checa_igual(destino.read_bytes(), ANTIGO, "original intacto apos PermissionError")
        checa(sem_temporario(destino), "nenhum .ewnew sobra apos PermissionError")


def testar_retentativa() -> None:
    secao("retentativa: a troca que falha duas vezes e passa na terceira")
    with pasta_temporaria() as pasta:
        destino = original_com(pasta)
        chamadas = [0]
        replace_real = os.replace

        def replace_instavel(origem, alvo):
            chamadas[0] += 1
            if chamadas[0] <= 2:
                raise PermissionError(13, "antivirus segurando (simulado)")
            return replace_real(origem, alvo)

        with trocado(gravacao, "_replace_file_w", lambda t, d: False), \
                trocado(os, "replace", replace_instavel):
            gravacao.gravar_bytes(destino, b"depois da retentativa")
        checa_igual(chamadas[0], 3, "a troca foi tentada tres vezes")
        checa_igual(destino.read_bytes(), b"depois da retentativa",
                    "a gravacao termina quando a retentativa passa")


def testar_contraprova_truncado() -> None:
    secao("sabotagem: temporario truncado no disco e' ACUSADO pela conferencia")
    with pasta_temporaria() as pasta:
        destino = original_com(pasta)
        dados = b"0123456789" * 50
        fsync_real = os.fsync

        def fsync_truncando(fd):
            # Sabotagem: o disco fica com metade dos bytes, como numa queda no meio.
            tamanho = os.fstat(fd).st_size
            os.ftruncate(fd, tamanho // 2)
            return fsync_real(fd)

        def conferir_igual(esperado: bytes):
            def conferir(lidos: bytes) -> None:
                if lidos != esperado:
                    raise ValueError(f"tamanho gravado {len(lidos)} != {len(esperado)}")
            return conferir

        with trocado(os, "fsync", fsync_truncando):
            capturado = capturar(gravacao.gravar_bytes, destino, dados,
                                 conferir=conferir_igual(dados))
        checa(isinstance(capturado, ValueError),
              "a conferencia ACUSA o temporario truncado (levanta)")
        checa_igual(destino.read_bytes(), ANTIGO,
                    "com a sabotagem acusada, o original fica intacto")
        checa(sem_temporario(destino), "e o temporario truncado e' removido")

        # Contraprova da contraprova: sem a sabotagem, a mesma conferencia passa.
        gravacao.gravar_bytes(destino, dados, conferir=conferir_igual(dados))
        checa_igual(destino.read_bytes(), dados,
                    "sem sabotagem a mesma conferencia deixa gravar")


def main() -> int:
    testar_novo_e_substituir()
    testar_conferir()
    testar_falha_na_troca()
    testar_falha_na_escrita()
    testar_sem_espaco()
    testar_permissao_na_troca()
    testar_retentativa()
    testar_contraprova_truncado()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
