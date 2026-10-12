"""Gerente de janelas: uma JanelaPrincipal por documento, como o Word.

Quem decide abrir, trazer para frente ou fechar as janelas e' este objeto. A janela
so' sabe do proprio documento. Abrir um arquivo ja aberto so' traz a janela para a
frente; a comparacao e' pelo caminho resolvido, em caixa baixa.

Abrir le o arquivo ANTES de criar a janela: se a leitura falha, nenhuma janela
vazia fica para tras (e fechar a ultima janela encerraria o programa).
"""

from __future__ import annotations

import os
import pathlib

from PySide6.QtCore import QObject

from editdoc import configuracao, log_interno
from editdoc.formato_docx import leitor
from editdoc.formato_docx.erros import ErroDocx
from editdoc.interface import dialogos_modais
from editdoc.interface.janela_principal import JanelaPrincipal

log = log_interno.obter(__name__)

#: Acima disso o programa pergunta antes de abrir: um .docx grande fica lento.
LIMITE_ABRIR_BYTES = 20 * 1024 * 1024

_MENSAGENS_DE_EXTENSAO = {
    ".doc": ("Este é um arquivo do Word 97-2003 (.doc). O EditDoc abre .docx: abra o "
             "arquivo no Word e salve como .docx."),
    ".docm": ("Arquivos com macros (.docm) não são abertos. Abra no Word e salve como "
              ".docx; as macros não são copiadas."),
    ".dotx": "Modelos (.dotx) não são abertos. Abra no Word e salve como .docx.",
}


def chave_de_caminho(caminho: pathlib.Path | str) -> str:
    return os.path.normcase(os.path.realpath(str(caminho)))


class GerenteDeJanelas(QObject):
    def __init__(self, cfg: dict, pai: QObject | None = None) -> None:
        super().__init__(pai)
        self._cfg = cfg
        self._janelas: list[JanelaPrincipal] = []

    def janelas(self) -> list[JanelaPrincipal]:
        return list(self._janelas)

    def _criar(self) -> JanelaPrincipal:
        janela = JanelaPrincipal(self._cfg, self)
        self._janelas.append(janela)
        return janela

    def _pai_dos_dialogos(self):
        return self._janelas[-1] if self._janelas else None

    def novo(self) -> JanelaPrincipal:
        janela = self._criar()
        janela.trazer_para_frente()
        return janela

    def abrir(self, caminho: str) -> JanelaPrincipal | None:
        """Abre o .docx em uma janela nova, ou traz a que ja o mostra. None se recusou."""
        try:
            alvo = pathlib.Path(caminho).resolve()
        except OSError:
            alvo = pathlib.Path(caminho)
        chave = chave_de_caminho(alvo)
        for janela in self._janelas:
            if janela.caminho_chave() == chave:
                janela.trazer_para_frente()
                return janela

        pai = self._pai_dos_dialogos()
        extensao = alvo.suffix.lower()
        if extensao != ".docx":
            texto = _MENSAGENS_DE_EXTENSAO.get(
                extensao,
                f"O EditDoc abre apenas arquivos .docx nesta versão. \"{alvo.name}\" não é um deles.")
            dialogos_modais.avisar(pai, "Abrir documento", texto)
            return None
        if not alvo.is_file():
            dialogos_modais.avisar(pai, "Abrir documento",
                                   "O arquivo não foi encontrado. Ele pode ter sido movido ou apagado.")
            return None
        try:
            tamanho = alvo.stat().st_size
        except OSError:
            dialogos_modais.avisar(pai, "Abrir documento", "Não foi possível ler o arquivo.")
            return None
        if tamanho > LIMITE_ABRIR_BYTES:
            mb = tamanho / (1024 * 1024)
            if not dialogos_modais.confirmar(
                    pai, "Arquivo grande",
                    f"\"{alvo.name}\" tem {mb:.0f} MB. Arquivos grandes deixam o programa "
                    "mais lento. Abrir mesmo assim?"):
                return None

        try:
            modelo, avisos = leitor.ler(str(alvo))
        except ErroDocx as erro:
            log.warning("arquivo recusado: %s", erro.codigo)
            dialogos_modais.avisar(pai, "Abrir documento", erro.mensagem)
            return None

        janela = self._criar()
        janela.carregar(modelo, avisos, alvo)
        try:
            configuracao.registrar_recente(str(alvo))
        except OSError:
            log.warning("nao foi possivel gravar a lista de recentes")
        janela.trazer_para_frente()
        log.info("aberto %s (%d aviso(s))", alvo.name, len(avisos))
        return janela

    def receber_pedido(self, pedido: dict) -> None:
        """Pedido de outra instancia: abre os arquivos, ou um documento novo."""
        arquivos = pedido.get("arquivos")
        if isinstance(arquivos, list) and arquivos:
            for caminho in arquivos:
                if isinstance(caminho, str):
                    self.abrir(caminho)
        elif pedido.get("novo"):
            self.novo()

    def recentes(self) -> list[str]:
        return configuracao.recentes()

    def fechou(self, janela: JanelaPrincipal) -> None:
        if janela in self._janelas:
            self._janelas.remove(janela)

    def sair(self) -> bool:
        """Fecha todas as janelas. Pergunta as que tem alteracao; False se alguma ficou aberta."""
        for janela in list(self._janelas):
            if not janela.pode_fechar():
                return False
        for janela in list(self._janelas):
            janela._ja_confirmou_fechamento = True
            janela.close()
        return True
