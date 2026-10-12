"""Janela principal: faixa de opcoes, documento, aviso, localizar e barra de status.

Um documento por janela. O documento vive no PainelDocumento (visao em paginas). A
janela guarda o estado do arquivo: caminho, assinatura do disco na ultima leitura
ou gravacao, e os avisos do leitor. Salvar, salvar como e fechar com alteracoes
pendentes passam por aqui.

Sem gerente (testes), a janela funciona sozinha; novo, abrir e recentes ficam sem
efeito, porque quem abre outras janelas e' o gerente.
"""

from __future__ import annotations

import os
import pathlib

from dataclasses import replace

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from editdoc import APP, VERSAO, configuracao, log_interno, recursos
from editdoc.armazenamento import gravacao
from editdoc.edicao import busca, tabelas
from editdoc.edicao import imagens as ed_imagens
from editdoc.edicao.busca import Opcoes
from editdoc.formato_docx import conferencia
from editdoc.formato_docx.avisos import Aviso
from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.escritor import escrever_com_avisos
from editdoc.interface import dialogos_modais
from editdoc.interface.atualizador import AtualizadorDeEstado
from editdoc.interface.barra_aviso import BarraAviso
from editdoc.interface.barra_busca import BarraBusca
from editdoc.interface.botao_arquivo import BotaoArquivo
from editdoc.interface.comandos import TABELA, Comandos
from editdoc.interface.controle_zoom import ControleZoom
from editdoc.interface.faixa import Faixa
from editdoc.interface.painel_documento import PainelDocumento
from editdoc.interface.regua import Regua
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.documento import Documento
from editdoc.modelo.estatisticas import contar
from editdoc.modelo.pagina import MARGENS_PREDEFINIDAS, Pagina
from editdoc.ponte_qt import de_qt, para_qt

log = log_interno.obter(__name__)

#: Pausa depois da ultima tecla antes de recontar as palavras.
ATRASO_ESTATISTICAS_MS = 400


def titulo_da_janela(nome: str | None, sujo: bool, versao: str = VERSAO) -> str:
    """'{nome} - EditDoc {versao}', ou 'Documento em branco - ...'. Asterisco na frente se sujo."""
    base = f"{nome or 'Documento em branco'} - {APP} {versao}"
    return f"*{base}" if sujo else base


def assinatura(caminho: pathlib.Path | None) -> tuple[int, int] | None:
    """(mtime_ns, tamanho) do arquivo no disco, ou None se ele nao existe."""
    if caminho is None:
        return None
    try:
        st = os.stat(caminho)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


class JanelaPrincipal(QMainWindow):
    def __init__(self, cfg: dict, gerente=None) -> None:
        super().__init__()
        self._gerente = gerente
        self.caminho: pathlib.Path | None = None
        self._assinatura: tuple[int, int] | None = None
        self._avisos: list[Aviso] = []
        self._titulo = ""
        self._autor = ""
        self._criado_em: str | None = None
        self._ja_confirmou_fechamento = False
        self.setWindowIcon(recursos.icone_do_aplicativo())
        self.resize(cfg["janela_largura"], cfg["janela_altura"])

        self.painel = PainelDocumento(cfg["fonte_padrao"], cfg["tamanho_padrao"])
        self.comandos = Comandos(self, self.painel, self._abrir_localizar,
                                 self._abrir_substituir, ao_arquivo={
                                     "novo": self._novo,
                                     "abrir": self._abrir,
                                     "salvar": self.salvar,
                                     "salvar_como": self.salvar_como,
                                     "fechar": self.close,
                                 }, ao_layout={
                                     "papel": self._mudar_papel,
                                     "orientacao": self._mudar_orientacao,
                                     "margens": self._mudar_margens,
                                     "primeira_diferente": self._alternar_primeira_diferente,
                                     "pares_impares": self._alternar_pares_impares,
                                     "formato_numero": self._mudar_formato_numero,
                                     "numero_inicial": self._mudar_numero_inicial,
                                 }, ao_inserir={
                                     "tabela": self._inserir_tabela,
                                     "imagem": self._inserir_imagem,
                                     "tamanho_imagem": self._tamanho_imagem,
                                 })
        self.botao_arquivo = BotaoArquivo(self.comandos, self._recentes, self._abrir_recente)
        self.faixa = Faixa(self.comandos, self.painel, self.botao_arquivo)
        self.regua = Regua(self.painel)
        self.barra_aviso = BarraAviso()
        self.barra_busca = BarraBusca()
        self.barra_busca.hide()
        self.barra_busca.procurar.connect(self._procurar)
        self.barra_busca.substituir_um.connect(self._substituir_um)
        self.barra_busca.substituir_tudo.connect(self._substituir_tudo)

        self.atualizador = AtualizadorDeEstado(self.painel, self.comandos,
                                               self.faixa.familia, self.faixa.tamanho)
        self.painel.registrar_atalhos(self.comandos.todas())
        self.painel.registrar_menu_contexto([self.comandos.acao(i) for i in (
            *TABELA, "tamanho_imagem")])
        self.painel.mensagem.connect(lambda texto: self.statusBar().showMessage(texto, 6000))
        # Sem isto o atalho so' funciona quando o foco esta no painel.
        for acao in self.comandos.todas():
            self.addAction(acao)

        centro = QWidget()
        vertical = QVBoxLayout(centro)
        vertical.setContentsMargins(0, 0, 0, 0)
        vertical.setSpacing(0)
        vertical.addWidget(self.faixa)
        vertical.addWidget(self.barra_aviso)
        vertical.addWidget(self.barra_busca)
        vertical.addWidget(self.regua)
        vertical.addWidget(self.painel, 1)
        self.setCentralWidget(centro)

        self._rotulo_pagina = QLabel()
        self.statusBar().addWidget(self._rotulo_pagina)
        self._rotulo_palavras = QLabel()
        self.controle_zoom = ControleZoom(self.comandos, self.painel)
        self.statusBar().addPermanentWidget(self._rotulo_palavras)
        self.statusBar().addPermanentWidget(self.controle_zoom)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(ATRASO_ESTATISTICAS_MS)
        self._timer.timeout.connect(self.atualizar_estatisticas)
        self.painel.textChanged.connect(self._timer.start)
        self.painel.documento_corpo().modificationChanged.connect(lambda _=False: self._atualizar_titulo())
        self.painel.cursorPositionChanged.connect(self._atualizar_rotulo_pagina)
        self.painel.paginaAlterada.connect(self._pagina_mudou)
        self._pagina_mudou()
        self.atualizar_estatisticas()
        self._atualizar_titulo()

    # -- pagina ------------------------------------------------------------

    def _pagina_mudou(self) -> None:
        """Papel, orientacao ou margens mudaram (por comando ou ao abrir): marca e rotulo."""
        self.comandos.atualizar_pagina(self.painel.configuracao_pagina())
        self._atualizar_rotulo_pagina()

    def _atualizar_rotulo_pagina(self) -> None:
        atual = self.painel.pagina_atual() + 1
        total = self.painel.total_de_paginas()
        self._rotulo_pagina.setText(f"Página {atual} de {total}")

    def _alterar_pagina(self, nova: Pagina) -> None:
        """Mudanca feita pelo usuario: e' alteracao do documento, entao deixa o arquivo sujo."""
        if nova == self.painel.configuracao_pagina():
            self.comandos.atualizar_pagina(nova)
            return
        self.painel.definir_configuracao_pagina(nova)
        self.painel.documento_corpo().setModified(True)

    def _mudar_papel(self, nome: str) -> None:
        self._alterar_pagina(self.painel.configuracao_pagina().com_papel(nome))

    def _mudar_orientacao(self, paisagem: bool) -> None:
        self._alterar_pagina(self.painel.configuracao_pagina().com_orientacao(paisagem))

    def _mudar_margens(self, nome: str) -> None:
        atual = self.painel.configuracao_pagina()
        if nome == "Personalizadas":
            nova = dialogos_modais.pedir_margens(self, atual)
            if nova is None:
                self.comandos.atualizar_pagina(atual)
                return
        else:
            predefinida = next(m for m in MARGENS_PREDEFINIDAS if m[0] == nome)
            _, sup, inf, esq, dir_ = predefinida
            nova = atual.com_margens(sup, inf, esq, dir_)
        self._alterar_pagina(nova)

    # -- cabecalho e rodape (M5) ---------------------------------------------

    def _alternar_primeira_diferente(self) -> None:
        atual = self.painel.configuracao_pagina()
        self._alterar_pagina(replace(atual, primeira_diferente=not atual.primeira_diferente))

    def _alternar_pares_impares(self) -> None:
        atual = self.painel.configuracao_pagina()
        self._alterar_pagina(replace(atual, pares_impares=not atual.pares_impares))

    def _mudar_formato_numero(self, formato: str) -> None:
        self._alterar_pagina(replace(self.painel.configuracao_pagina(), formato_numero=formato))

    def _mudar_numero_inicial(self) -> None:
        atual = self.painel.configuracao_pagina()
        ok, valor = dialogos_modais.pedir_numero_inicial(self, atual.numero_inicial)
        if ok:
            self._alterar_pagina(replace(atual, numero_inicial=valor))
        self.painel.setFocus()

    # -- inserir: tabela e imagem -------------------------------------------

    def _inserir_tabela(self) -> None:
        escolha = dialogos_modais.pedir_tamanho_tabela(self, tabelas.LINHAS_MAXIMAS,
                                                       tabelas.COLUNAS_MAXIMAS)
        if escolha is None:
            return
        linhas, colunas = escolha
        if tabelas.inserir_tabela(self.painel, linhas, colunas) is None:
            dialogos_modais.avisar(self, "Inserir tabela",
                                   f"A tabela pode ter no máximo {tabelas.CELULAS_MAXIMAS} "
                                   "células. Com mais que isso a digitação fica lenta demais.")
        self.painel.setFocus()

    def _inserir_imagem(self) -> None:
        caminho = dialogos_modais.pedir_arquivo_imagem(self)
        if not caminho:
            return
        try:
            if os.path.getsize(caminho) > mod_imagem.BYTES_MAXIMOS:
                raise ed_imagens.ImagemRecusada("A imagem tem mais de 64 MB.")
            with open(caminho, "rb") as arquivo:
                dados = arquivo.read(mod_imagem.BYTES_MAXIMOS + 1)
            ed_imagens.inserir_bytes(self.painel, dados)
        except ed_imagens.ImagemRecusada as erro:
            dialogos_modais.avisar(self, "Inserir imagem", str(erro))
        except OSError as erro:
            log.warning("imagem ilegivel %s: %s", caminho, erro)
            dialogos_modais.avisar(self, "Inserir imagem", "Não foi possível ler o arquivo de imagem.")
        self.painel.setFocus()

    def _tamanho_imagem(self) -> None:
        pos = self.painel.imagem_selecionada()
        tamanho = ed_imagens.tamanho_em_px(self.painel, pos) if pos is not None else None
        if tamanho is None:
            return
        escolha = dialogos_modais.pedir_tamanho_imagem(self, ed_imagens.cm_de_px(tamanho[0]),
                                                       ed_imagens.cm_de_px(tamanho[1]))
        if escolha is not None:
            ed_imagens.redimensionar(self.painel, pos, ed_imagens.px_de_cm(escolha[0]),
                                     ed_imagens.px_de_cm(escolha[1]))
        self.painel.setFocus()

    # -- estatisticas e busca ----------------------------------------------

    def atualizar_estatisticas(self) -> None:
        contagem = contar(self.painel.toPlainText())
        self._rotulo_palavras.setText(f"Palavras: {contagem.palavras}")

    def _abrir_localizar(self) -> None:
        self.barra_busca.mostrar(substituir=False)

    def _abrir_substituir(self) -> None:
        self.barra_busca.mostrar(substituir=True)

    def _procurar(self, texto: str, maiusculas: bool, palavra: bool, para_tras: bool) -> None:
        achou = busca.localizar(self.painel, texto, Opcoes(maiusculas, palavra), para_tras)
        self.barra_busca.dizer("" if achou else "Não encontrado")

    def _substituir_um(self, texto: str, substituto: str, maiusculas: bool,
                       palavra: bool) -> None:
        achou = busca.substituir_atual(self.painel, texto, substituto,
                                       Opcoes(maiusculas, palavra))
        self.barra_busca.dizer("" if achou else "Não encontrado")

    def _substituir_tudo(self, texto: str, substituto: str, maiusculas: bool,
                         palavra: bool) -> None:
        trocas = busca.substituir_todas(self.painel, texto, substituto,
                                        Opcoes(maiusculas, palavra))
        if trocas == 1:
            self.barra_busca.dizer("1 substituição")
        else:
            self.barra_busca.dizer(f"{trocas} substituições")

    # -- estado do documento -----------------------------------------------

    def _nome(self) -> str:
        return self.caminho.name if self.caminho is not None else "Documento em branco"

    def _atualizar_titulo(self) -> None:
        nome = self.caminho.name if self.caminho is not None else None
        self.setWindowTitle(titulo_da_janela(nome, self.painel.documento_corpo().isModified()))

    def sujo(self) -> bool:
        return self.painel.documento_corpo().isModified()

    def caminho_chave(self) -> str | None:
        """Caminho resolvido, em caixa baixa: impede abrir o mesmo arquivo em duas janelas."""
        if self.caminho is None:
            return None
        return os.path.normcase(os.path.realpath(str(self.caminho)))

    def carregar(self, modelo: Documento, avisos: list[Aviso], caminho: pathlib.Path) -> None:
        """Poe o documento lido na janela. Nao deixa o documento sujo."""
        self.painel.sair_da_faixa()
        para_qt.preencher(self.painel.documento_corpo(), modelo)
        self.painel.carregar_faixas(modelo)
        self.painel.definir_configuracao_pagina(modelo.pagina)
        self._titulo, self._autor, self._criado_em = modelo.titulo, modelo.autor, modelo.criado_em
        self.caminho = caminho
        self._assinatura = assinatura(caminho)
        self._avisos = list(avisos)
        cursor = self.painel.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.painel.setTextCursor(cursor)
        self.barra_aviso.mostrar(self._avisos)
        self.atualizar_estatisticas()
        self._atualizar_titulo()

    def trazer_para_frente(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    # -- salvar ------------------------------------------------------------

    def _modelo_atual(self) -> Documento:
        modelo = de_qt.extrair(self.painel.documento_corpo())
        modelo.pagina = replace(self.painel.configuracao_pagina())
        modelo.cabecalhos, modelo.rodapes = self.painel.faixas_do_modelo()
        modelo.titulo = self._titulo
        modelo.autor = self._autor
        modelo.criado_em = self._criado_em
        return modelo

    def _mudou_no_disco(self) -> bool:
        atual = assinatura(self.caminho)
        return atual is not None and atual != self._assinatura

    def salvar(self) -> bool:
        if self.caminho is None:
            return self.salvar_como()
        if not self.sujo():
            return True
        return self._gravar(self.caminho, trocar=True)

    def salvar_como(self) -> bool:
        sugestao = self.caminho.name if self.caminho is not None else "Documento.docx"
        escolhido = dialogos_modais.pedir_salvar_arquivo(self, sugestao)
        if not escolhido:
            return False
        return self._gravar(pathlib.Path(escolhido), trocar=True)

    def _gravar(self, alvo: pathlib.Path, trocar: bool) -> bool:
        """Grava em `alvo`. `trocar` diz se o alvo vira o caminho do documento."""
        try:
            modelo = self._modelo_atual()
            dados, avisos_gravacao = escrever_com_avisos(modelo)
        except ErroDocx as erro:
            log.error("montagem do .docx falhou: %s", erro.codigo)
            dialogos_modais.avisar(self, "Salvar", "Não foi possível montar o arquivo. "
                                   "O original NÃO foi alterado.")
            return False

        perdas = [a for a in (*self._avisos, *avisos_gravacao) if a.perde_ao_salvar]
        if perdas:
            escolha = dialogos_modais.pedir_perda(self, self._nome(),
                                                  [a.texto for a in perdas])
            if escolha == "cancelar":
                return False
            if escolha == "copia":
                sugestao = f"{pathlib.Path(self._nome()).stem} (cópia).docx"
                escolhido = dialogos_modais.pedir_salvar_arquivo(self, sugestao)
                if not escolhido:
                    return False
                alvo = pathlib.Path(escolhido)
                if self.caminho is None or alvo.resolve() != self.caminho.resolve():
                    trocar = False

        mesmo_arquivo = self.caminho is not None and alvo.resolve() == self.caminho.resolve()
        if trocar and mesmo_arquivo and self._mudou_no_disco():
            if not dialogos_modais.pedir_sobrescrever(self, alvo.name):
                return False

        try:
            gravacao.gravar_bytes(alvo, dados, conferir=conferencia.conferidor(modelo))
        except conferencia.FalhaDeConferencia as erro:
            log.error("conferencia do arquivo gravado falhou: %s", erro)
            dialogos_modais.avisar(self, "Salvar", "A conferência do arquivo gravado falhou. "
                                   "O original NÃO foi alterado.")
            return False
        except ErroDocx as erro:
            log.error("arquivo gravado nao pode ser lido: %s", erro.codigo)
            dialogos_modais.avisar(self, "Salvar", "O arquivo gravado não pode ser lido de volta. "
                                   "O original NÃO foi alterado.")
            return False
        except gravacao.SemEspaco as erro:
            dialogos_modais.avisar(self, "Salvar", str(erro))
            return False
        except gravacao.FalhaNaTroca as erro:
            dialogos_modais.avisar(self, "Salvar", str(erro))
            return False
        except OSError as erro:
            log.error("gravacao de %s falhou: %s", alvo, erro)
            dialogos_modais.avisar(self, "Salvar", "Não foi possível gravar o arquivo. Verifique "
                                   "se ele não está aberto em outro programa e se há espaço "
                                   "em disco. O original NÃO foi alterado.")
            return False

        if trocar:
            self.caminho = alvo
            self._assinatura = assinatura(alvo)
            self._avisos = []
            self.barra_aviso.mostrar([])
            self.painel.documento_corpo().setModified(False)
            self._atualizar_titulo()
            try:
                configuracao.registrar_recente(str(alvo))
            except OSError:
                log.warning("nao foi possivel gravar a lista de recentes")
            self.statusBar().showMessage(f"Salvo: {alvo.name}", 4000)
        else:
            self.statusBar().showMessage(
                f"Cópia salva em {alvo.name}. O documento continua em {self._nome()}.", 6000)
        return True

    def pode_fechar(self) -> bool:
        """Sem alteracao, sim. Com alteracao, pergunta: salvar, descartar ou cancelar."""
        if not self.sujo():
            return True
        escolha = dialogos_modais.pedir_descartar(self, self._nome())
        if escolha == "salvar":
            return self.salvar()
        return escolha == "descartar"

    # -- comandos de janela ------------------------------------------------

    def _novo(self) -> None:
        if self._gerente is not None:
            self._gerente.novo()

    def _abrir(self) -> None:
        caminho = dialogos_modais.pedir_abrir_arquivo(self)
        if caminho and self._gerente is not None:
            self._gerente.abrir(caminho)

    def _abrir_recente(self, caminho: str) -> None:
        if self._gerente is not None:
            self._gerente.abrir(caminho)

    def _recentes(self) -> list[str]:
        return configuracao.recentes()

    def closeEvent(self, evento) -> None:  # noqa: N802 - nome do Qt
        if self._ja_confirmou_fechamento or self.pode_fechar():
            if self._gerente is not None:
                self._gerente.fechou(self)
            evento.accept()
        else:
            evento.ignore()
