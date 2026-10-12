"""Gerente de janelas: uma JanelaPrincipal por documento, como o Word.

Quem decide abrir, trazer para frente ou fechar as janelas e' este objeto. A janela
so' sabe do proprio documento. Abrir um arquivo ja aberto so' traz a janela para a
frente; a comparacao e' pelo caminho resolvido, em caixa baixa.

Abrir le o arquivo ANTES de criar a janela: se a leitura falha, nenhuma janela
vazia fica para tras (e fechar a ultima janela encerraria o programa).

Recuperacao (M8): na abertura, `oferecer_recuperacao` procura as copias que sobraram de
uma queda e mostra o dialogo "Recuperação de documentos". Abrir uma copia adota a trava
dela (outra instancia nao a oferece de novo); salvar como grava a copia num .docx e a
apaga; descartar apaga. Preferencias (M8): `aplicar_preferencias` leva as opcoes a todas
as janelas e ao tema do aplicativo.
"""

from __future__ import annotations

import os
import pathlib

from PySide6.QtCore import QObject

from editdoc import configuracao, log_interno, recuperacao
from editdoc.armazenamento import gravacao
from editdoc.formato_docx import leitor
from editdoc.formato_docx.avisos import Aviso
from editdoc.formato_docx.erros import ErroDocx
from editdoc.interface import dialogos_modais, tema
from editdoc.interface.dialogo_recuperacao import DialogoRecuperacao
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
        self.dialogo_recuperacao: DialogoRecuperacao | None = None

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

    # -- preferencias (M8) -------------------------------------------------------------
    def aplicar_preferencias(self, cfg: dict) -> None:
        """Opcoes novas: o documento novo usa a fonte e o papel; as janelas, o resto."""
        self._cfg.update({k: v for k, v in cfg.items() if k != "recentes"})
        for janela in self._janelas:
            janela.aplicar_preferencias(self._cfg)
        tema.aplicar(self._cfg.get("tema", "sistema"))

    # -- recuperacao (M8) --------------------------------------------------------------
    def oferecer_recuperacao(self, avisar_se_vazio: bool = False) -> DialogoRecuperacao | None:
        """Mostra as copias orfas, se houver. Devolve o dialogo (nao modal) ou None."""
        try:
            copias = recuperacao.listar_orfas()
        except OSError as erro:
            log.warning("pasta de recuperacao ilegivel: %s", erro)
            copias = []
        if not copias:
            if avisar_se_vazio:
                dialogos_modais.mostrar_detalhes(self._pai_dos_dialogos(), "Recuperar documentos",
                                                 "Não há cópias de recuperação para abrir.")
            return None
        if self.dialogo_recuperacao is not None:
            self.dialogo_recuperacao.close()
            self.dialogo_recuperacao.deleteLater()
        dialogo = DialogoRecuperacao(copias, {
            "abrir": lambda c: self.abrir_recuperado(c) is not None,
            "salvar_como": self.salvar_copia_como,
            "descartar": self.descartar_copia,
        }, self._pai_dos_dialogos())
        self.dialogo_recuperacao = dialogo
        log.info("%d copia(s) de recuperacao oferecida(s)", len(copias))
        dialogos_modais.mostrar_recuperacao(dialogo)
        return dialogo

    def _ler_copia(self, copia: recuperacao.Copia):
        """(modelo, avisos) da copia, ou None com o aviso ao usuario."""
        try:
            return leitor.ler(copia.ler())
        except (OSError, ErroDocx) as erro:
            log.warning("copia de recuperacao %s ilegivel: %s", copia.id, erro)
            dialogos_modais.avisar(self._pai_dos_dialogos(), "Recuperação de documentos",
                                   "A cópia de recuperação não pode ser lida. Ela pode ter "
                                   "sido gravada pela metade.")
            return None

    def abrir_recuperado(self, copia: recuperacao.Copia) -> JanelaPrincipal | None:
        """Abre a copia numa janela nova, alterada e sem caminho. None se nao deu."""
        sessao = recuperacao.Sessao(id_=copia.id)
        if not sessao.travar():
            dialogos_modais.avisar(self._pai_dos_dialogos(), "Recuperação de documentos",
                                   "Esta cópia já está aberta em outra janela do EditDoc.")
            return None
        lido = self._ler_copia(copia)
        if lido is None:
            sessao._trava.soltar(apagar=False)
            return None
        modelo, avisos = lido
        avisos = list(avisos) + [Aviso(**a) for a in copia.avisos_com_perda()]
        janela = self._criar()
        janela.carregar_recuperado(modelo, avisos, copia, sessao)
        janela.trazer_para_frente()
        log.info("copia de recuperacao %s aberta", copia.id)
        return janela

    def salvar_copia_como(self, copia: recuperacao.Copia) -> bool:
        """Grava a copia como .docx onde o usuario escolher; depois ela sai da recuperacao."""
        pai = self._pai_dos_dialogos()
        sessao = recuperacao.Sessao(id_=copia.id)
        if not sessao.travar():
            dialogos_modais.avisar(pai, "Recuperação de documentos",
                                   "Esta cópia já está aberta em outra janela do EditDoc.")
            return False
        try:
            if self._ler_copia(copia) is None:
                return False
            sugestao = copia.caminho_original or f"{pathlib.Path(copia.nome).stem}.docx"
            destino = dialogos_modais.pedir_salvar_arquivo(pai, sugestao)
            if not destino:
                return False
            try:
                gravacao.gravar_bytes(destino, copia.ler(), conferir=leitor.ler)
            except (OSError, ErroDocx) as erro:
                log.error("copia de recuperacao nao gravada em %s: %s", destino, erro)
                dialogos_modais.avisar(pai, "Recuperação de documentos",
                                       "Não foi possível gravar o arquivo. A cópia de "
                                       "recuperação continua guardada.")
                return False
            try:
                configuracao.registrar_recente(str(destino))
            except OSError:
                pass
            sessao.encerrar()
            sessao = None
            return True
        finally:
            if sessao is not None and sessao._trava is not None:
                sessao._trava.soltar(apagar=False)

    def descartar_copia(self, copia: recuperacao.Copia) -> bool:
        pai = self._pai_dos_dialogos()
        if not dialogos_modais.confirmar(pai, "Recuperação de documentos",
                                         f"Apagar a cópia de recuperação de \"{copia.nome}\"? "
                                         "Ela não poderá ser aberta depois."):
            return False
        sessao = recuperacao.Sessao(id_=copia.id)
        if not sessao.travar():
            dialogos_modais.avisar(pai, "Recuperação de documentos",
                                   "Esta cópia está aberta em outra janela do EditDoc.")
            return False
        sessao.encerrar()
        return True

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
