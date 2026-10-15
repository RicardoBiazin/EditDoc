"""Janela principal: faixa de opcoes, documento, aviso, localizar e barra de status.

Um documento por janela. O documento vive no PainelDocumento (visao em paginas). A
janela guarda o estado do arquivo: caminho, assinatura do disco na ultima leitura
ou gravacao, e os avisos do leitor. Salvar, salvar como e fechar com alteracoes
pendentes passam por aqui.

Sem gerente (testes), a janela funciona sozinha; novo, abrir e recentes ficam sem
efeito, porque quem abre outras janelas e' o gerente.

Impressao e PDF (M7): exportar, imprimir e visualizar passam por `interface/impressao.py`,
com a mesma pintura da tela; os dialogos sao de `dialogos_modais`.

Recuperacao e preferencias (M8): cada janela tem uma GuardaRecuperacao, que grava a
copia do documento alterado de tempos em tempos; salvar apaga a copia e fechar
normalmente apaga e solta a trava. Um documento aberto da recuperacao nao tem caminho
(salvar pergunta onde) e nasce alterado. `aplicar_preferencias` leva Arquivo > Opcoes
para a janela aberta (recuperacao, regua, abrir o PDF); fonte, tamanho e papel valem
para o proximo documento novo.

Estilos e Exibir (M6): a galeria fica na faixa; o painel de estilos e o painel de
navegacao sao QDockWidget opcionais (direita e esquerda), escondidos ao abrir. A janela
mantem a galeria, o painel de estilos, os campos da aba Layout e os botoes de mostrar em
sintonia com o cursor (`_sintonizar`, chamado pelo AtualizadorDeEstado).

Comentarios (0.1.6): o painel de comentarios e' outro QDockWidget a direita (aparece sozinho
quando o documento aberto tem comentarios, como o "Mostrar comentarios" do Word). Os dialogos
(novo, responder, editar) sao da janela (`_pedir_comentario`, trocavel nos testes); o autor e
as iniciais vem das Opcoes, lidas na hora (mudar as Opcoes vale para o proximo comentario).
"""

from __future__ import annotations

import os
import pathlib

from dataclasses import replace

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDockWidget, QLabel, QMainWindow, QVBoxLayout, QWidget

from editdoc import APP, VERSAO, configuracao, log_interno, recursos
from editdoc.armazenamento import gravacao
from editdoc.edicao import busca, tabelas
from editdoc.edicao import comentarios as ed_comentarios
from editdoc.edicao import estilos as ed_estilos
from editdoc.edicao import imagens as ed_imagens
from editdoc.edicao import links as ed_links
from editdoc.edicao.busca import Opcoes
from editdoc.formato_docx import conferencia
from editdoc.formato_docx.avisos import Aviso
from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.escritor import escrever_com_avisos
from editdoc.interface import (acessibilidade, dialogo_comentario, dialogo_estilo, dialogos_modais,
                               impressao, tema)
from editdoc.interface.atualizador import AtualizadorDeEstado
from editdoc.interface.barra_aviso import BarraAviso
from editdoc.interface.barra_busca import BarraBusca
from editdoc.interface.botao_arquivo import BotaoArquivo
from editdoc.interface.comandos import (COMENTARIO, LINK, LISTA_NUMERADA, QUEBRA_DAS_ACOES, TABELA,
                                        Comandos)
from editdoc.interface.controle_zoom import ControleZoom
from editdoc.interface.faixa import BotaoAcao, Faixa
from editdoc.interface.guarda_recuperacao import GuardaRecuperacao
from editdoc.interface.navegacao import PainelNavegacao
from editdoc.interface.painel_comentarios import PainelComentarios
from editdoc.interface.painel_documento import PainelDocumento
from editdoc.interface.painel_estilos import PainelEstilos
from editdoc.interface.regua import Regua
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.documento import Documento, Paragrafo
from editdoc.modelo.estilos import catalogo_de_documento_novo
from editdoc.modelo.estatisticas import contar
from editdoc.modelo.pagina import MARGENS_PREDEFINIDAS, Pagina
from editdoc.modelo.texto_plano import texto_do_documento
from editdoc.ponte_qt import de_qt, links, marcas, para_qt
from editdoc.ponte_qt import comentarios as pq_comentarios
from editdoc.ponte_qt import estilos as pq_estilos

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
        #: Partes do pacote de origem que voltam ao arquivo (0.1.3): settings.xml original,
        #: custom.xml, customXml, fontTable, webSettings... None no documento novo.
        self._pacote = None
        self._ja_confirmou_fechamento = False
        #: Exportar PDF: lembra a escolha "abrir depois de exportar" enquanto a janela vive.
        #: Comeca pela preferencia (M8).
        self._abrir_pdf = bool(cfg.get("abrir_pdf_depois", False))
        #: Documento aberto da recuperacao (M8): nome mostrado e caminho de onde veio.
        self._nome_recuperado: str | None = None
        self._original_recuperado: str | None = None
        self._fonte_cfg = (cfg["fonte_padrao"], float(cfg["tamanho_padrao"]))
        self.setWindowIcon(recursos.icone_do_aplicativo())
        self.resize(cfg["janela_largura"], cfg["janela_altura"])

        self.painel = PainelDocumento(cfg["fonte_padrao"], cfg["tamanho_padrao"])
        # Documento novo (M8): o catalogo com a fonte da preferencia e o docDefaults do Word
        # (8 pt depois, 1,08), que o escritor grava. O primeiro paragrafo ja' nasce com ele,
        # e o Enter copia o formato: a tela mostra o que o Word mostrara' do arquivo.
        para_qt.preencher(self.painel.documento_corpo(), Documento(
            paragrafos=[Paragrafo()],
            estilos=catalogo_de_documento_novo(cfg["fonte_padrao"], cfg["tamanho_padrao"])))
        papel = cfg.get("papel_padrao", "A4")
        if papel != "A4":
            # Documento novo no papel da preferencia (M8). Nao conta como alteracao.
            self.painel.definir_configuracao_pagina(Pagina().com_papel(papel))
            self.painel.documento_corpo().setModified(False)
        self.comandos = Comandos(self, self.painel, self._abrir_localizar,
                                 self._abrir_substituir, ao_arquivo={
                                     "novo": self._novo,
                                     "abrir": self._abrir,
                                     "salvar": self.salvar,
                                     "salvar_como": self.salvar_como,
                                     "fechar": self.close,
                                     "imprimir": self.imprimir,
                                     "visualizar_impressao": self.visualizar_impressao,
                                     "exportar_pdf": self.exportar_pdf,
                                     "exportar_txt": self.exportar_txt,
                                     "opcoes": self.opcoes,
                                     "recuperar": self._recuperar,
                                 }, ao_layout={
                                     "papel": self._mudar_papel,
                                     "orientacao": self._mudar_orientacao,
                                     "margens": self._mudar_margens,
                                     "primeira_diferente": self._alternar_primeira_diferente,
                                     "pares_impares": self._alternar_pares_impares,
                                     "formato_numero": self._mudar_formato_numero,
                                     "numero_inicial": self._mudar_numero_inicial,
                                     "vincular_anterior": self._alternar_vinculo,
                                 }, ao_inserir={
                                     "tabela": self._inserir_tabela,
                                     "imagem": self._inserir_imagem,
                                     "tamanho_imagem": self._tamanho_imagem,
                                     "posicao_tamanho": self._posicao_tamanho,
                                     "link": self._inserir_link,
                                     "remover_link": self._remover_link,
                                     "abrir_link": self._abrir_link,
                                     "valor_numeracao": self._definir_valor_numeracao,
                                     "opcoes_notas": self.opcoes_notas,
                                 }, ao_exibir={
                                     "criar_estilo": self.criar_estilo,
                                     "modificar_estilo": self.modificar_estilo,
                                     "painel_estilos": self._alternar_painel_estilos,
                                     "navegacao": self._alternar_navegacao,
                                     "regua": self._alternar_regua,
                                 }, ao_revisao={
                                     "novo": self.novo_comentario,
                                     "responder": self.responder_comentario,
                                     "editar": self.editar_comentario,
                                     "resolver": self.resolver_comentario,
                                     "excluir": self.excluir_comentario,
                                     "excluir_todos": self.excluir_todos_comentarios,
                                     "anterior": lambda: self._comentario_vizinho(False),
                                     "proximo": lambda: self._comentario_vizinho(True),
                                     "mostrar": self._alternar_comentarios,
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

        # Estilos e Exibir (M6): galeria, paineis laterais e regua.
        galeria = self.faixa.galeria
        galeria.escolhido.connect(self._estilo_escolhido)
        galeria.pedido_atualizar.connect(
            lambda sid: ed_estilos.atualizar_pela_selecao(self.painel, sid))
        galeria.pedido_modificar.connect(self.modificar_estilo)
        self.painel_estilos = PainelEstilos([BotaoAcao(self.comandos.acao(i), rotulo) for i, rotulo in (
            ("criar_estilo", "Novo estilo..."), ("modificar_estilo", "Modificar..."),
            ("limpar_formatacao", "Limpar tudo"))])
        self.painel_estilos.escolhido.connect(self._estilo_escolhido)
        self.dock_estilos = QDockWidget("Estilos", self)
        self.dock_estilos.setObjectName("dock_estilos")
        self.dock_estilos.setWidget(self.painel_estilos)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_estilos)
        self.dock_estilos.hide()
        self.navegacao = PainelNavegacao(self.painel)
        self.navegacao.escolhido.connect(self.painel.ir_para_posicao)
        self.dock_navegacao = QDockWidget("Navegação", self)
        self.dock_navegacao.setObjectName("dock_navegacao")
        self.dock_navegacao.setWidget(self.navegacao)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_navegacao)
        self.dock_navegacao.hide()
        # Comentarios (0.1.6): o painel a direita, escondido ate' haver comentario.
        self.painel_comentarios = PainelComentarios()
        self.dock_comentarios = QDockWidget("Comentários", self)
        self.dock_comentarios.setObjectName("dock_comentarios")
        self.dock_comentarios.setWidget(self.painel_comentarios)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_comentarios)
        self.dock_comentarios.hide()
        self.painel_comentarios.selecionado.connect(self._comentario_escolhido)
        self.painel_comentarios.responder.connect(self.responder_comentario)
        self.painel_comentarios.editar.connect(self.editar_comentario)
        self.painel_comentarios.resolver.connect(self.resolver_comentario)
        self.painel_comentarios.excluir.connect(self.excluir_comentario)
        self.dock_estilos.visibilityChanged.connect(lambda _v: self._sintonizar())
        self.dock_navegacao.visibilityChanged.connect(lambda _v: self._sintonizar())
        self.dock_comentarios.visibilityChanged.connect(self._comentarios_visiveis)
        self._regua_visivel = True
        self.comandos.acao("mostrar_regua").setChecked(True)

        self.atualizador = AtualizadorDeEstado(self.painel, self.comandos,
                                               self.faixa.familia, self.faixa.tamanho,
                                               ao_atualizar=self._sintonizar)
        self.painel.registrar_atalhos(self.comandos.todas())
        self.painel.registrar_menu_contexto([self.comandos.acao(i) for i in (
            *TABELA, "tamanho_imagem", "inserir_link", *LINK, *LISTA_NUMERADA,
            "novo_comentario", *COMENTARIO)])
        self.painel.registrar_menu_objeto([self.comandos.acao(i) for i in QUEBRA_DAS_ACOES],
                                          self.comandos.acao("posicao_tamanho"))
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
        # Secoes (0.1.12): "Seção 2 de 3", so' com mais de uma secao.
        self._rotulo_secao = QLabel()
        self._rotulo_secao.setAccessibleName("Seção do cursor")
        self.statusBar().addWidget(self._rotulo_secao)
        self._rotulo_secao.hide()
        self._rotulo_palavras = QLabel()
        self.controle_zoom = ControleZoom(self.comandos, self.painel)
        self.statusBar().addPermanentWidget(self._rotulo_palavras)
        self.statusBar().addPermanentWidget(self.controle_zoom)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(ATRASO_ESTATISTICAS_MS)
        self._timer.timeout.connect(self.atualizar_estatisticas)
        self.painel.textChanged.connect(self._timer.start)
        self._timer_comentarios = QTimer(self)
        self._timer_comentarios.setSingleShot(True)
        self._timer_comentarios.setInterval(ATRASO_ESTATISTICAS_MS)
        self._timer_comentarios.timeout.connect(self._atualizar_comentarios)
        self.painel.textChanged.connect(self._timer_comentarios.start)
        self.painel.comentariosAlterados.connect(self._atualizar_comentarios)
        self.painel.cursorPositionChanged.connect(self._destacar_comentario)
        self.painel.documento_corpo().modificationChanged.connect(lambda _=False: self._atualizar_titulo())
        self.painel.cursorPositionChanged.connect(self._atualizar_rotulo_pagina)
        self.painel.paginaAlterada.connect(self._pagina_mudou)
        self._pagina_mudou()
        self.atualizar_estatisticas()

        # Recuperacao automatica (M8).
        self.recuperacao = GuardaRecuperacao(
            self._montar_recuperacao, self.sujo, cfg.get("recuperacao_minutos", 10),
            cfg.get("recuperacao_ligada", True), self)
        self.painel.textChanged.connect(self.recuperacao.alterou)
        self.painel.layout_pag.faixas.alterado.connect(self.recuperacao.alterou)
        self.painel.paginaAlterada.connect(self.recuperacao.alterou)
        self.regua.definir_unidade(cfg.get("unidade_regua", "cm"))
        # Acessibilidade (M8): nomes, teclado da faixa (Alt, F10) e o documento.
        self.teclado_faixa = acessibilidade.preparar_janela(self)
        self._atualizar_titulo()

    # -- preferencias e recuperacao (M8) -----------------------------------------

    def _montar_recuperacao(self) -> tuple[bytes, str | None, str, list]:
        """O .docx da copia de recuperacao, o caminho de origem, o nome e os avisos com perda."""
        dados, _avisos = escrever_com_avisos(self._modelo_atual())
        original = str(self.caminho) if self.caminho is not None else self._original_recuperado
        return dados, original, self._nome(), [a for a in self._avisos if a.perde_ao_salvar]

    def aplicar_preferencias(self, cfg: dict) -> None:
        """Preferencias que valem para a janela aberta: recuperacao, regua e abrir o PDF."""
        self.recuperacao.definir(cfg.get("recuperacao_minutos", 10),
                                 cfg.get("recuperacao_ligada", True))
        self.regua.definir_unidade(cfg.get("unidade_regua", "cm"))
        self._abrir_pdf = bool(cfg.get("abrir_pdf_depois", False))
        self._fonte_cfg = (cfg.get("fonte_padrao", self._fonte_cfg[0]),
                           float(cfg.get("tamanho_padrao", self._fonte_cfg[1])))

    def opcoes(self) -> bool:
        """Arquivo > Opções: mostra, grava e aplica as preferencias. True se mudou."""
        novas = dialogos_modais.pedir_opcoes(self, configuracao.carregar())
        if novas is None:
            return False
        limpar = bool(novas.pop("limpar_recentes", False))
        try:
            gravado = configuracao.gravar_preferencias(novas)
            if limpar:
                configuracao.limpar_recentes()
        except OSError as erro:
            log.error("preferencias nao gravadas: %s", erro)
            dialogos_modais.avisar(self, "Opções", "Não foi possível gravar as preferências. "
                                   "Elas valem até o programa fechar.")
            gravado = configuracao.validar({**configuracao.carregar(), **novas})
        if self._gerente is not None:
            self._gerente.aplicar_preferencias(gravado)
        else:
            self.aplicar_preferencias(gravado)
            tema.aplicar(gravado["tema"])
        self.statusBar().showMessage("Opções gravadas.", 4000)
        return True

    def _recuperar(self) -> None:
        if self._gerente is not None:
            self._gerente.oferecer_recuperacao(avisar_se_vazio=True)

    def carregar_recuperado(self, modelo: Documento, avisos: list[Aviso], copia, sessao) -> None:
        """Poe na janela um documento da recuperacao: sem caminho, alterado, com a copia adotada."""
        self.carregar(modelo, avisos, None)
        self._nome_recuperado = f"{copia.nome} (recuperado)"
        self._original_recuperado = copia.caminho_original
        self.recuperacao.sessao = sessao
        self.recuperacao.alteracoes = 0
        self.painel.documento_corpo().setModified(True)
        self._atualizar_titulo()

    # -- estilos e exibir (M6) ------------------------------------------------

    def _fonte_padrao(self) -> QFont:
        return QFont(self.painel.documento_corpo().defaultFont())

    def _sintonizar(self) -> None:
        """Galeria, painel de estilos, aba Layout e botoes de mostrar com o estado atual.

        Chamado pelo AtualizadorDeEstado a cada mudanca de cursor: tem de ser barato. As
        miniaturas so' sao refeitas quando o catalogo muda (a assinatura muda).
        """
        doc = self.painel.document()
        assinatura = (pq_estilos.assinatura(doc), self.painel.documento_corpo().defaultFont().key())
        estilos = None
        if assinatura != getattr(self, "_assinatura_estilos", None):
            self._assinatura_estilos = assinatura
            estilos = pq_estilos.catalogo(doc)
            fonte = self._fonte_padrao()
            self.faixa.galeria.definir_estilos(estilos, fonte, assinatura)
            self.painel_estilos.definir_estilos(estilos, fonte, assinatura)
            self.faixa.ajustar()
        sid_par, sid_car = ed_estilos.estilo_no_cursor(self.painel)
        atual = sid_car or sid_par
        self.faixa.galeria.marcar(atual)
        if self.dock_estilos.isVisible():
            self.painel_estilos.marcar(atual)
        bf = self.painel.textCursor().block().blockFormat()
        # Recuos em twips no bloco (0.1.4); espacos em px96.
        # 0.1.12: sem o recuo escondido da secao estreita.
        self.faixa.mostrar_paragrafo(round(bf.leftMargin()), round(pq_estilos.recuo_direito_real(bf)),
                                     round(bf.topMargin() * 15), round(bf.bottomMargin() * 15))
        c = self.comandos
        c.acao("marcas_formatacao").setChecked(self.painel.marcas_visiveis())
        # A regua guarda o proprio estado: antes de a janela aparecer, isHidden() da' True.
        c.acao("mostrar_regua").setChecked(self._regua_visivel)
        c.acao("painel_estilos").setChecked(not self.dock_estilos.isHidden())
        c.acao("painel_navegacao").setChecked(not self.dock_navegacao.isHidden())
        c.acao("mostrar_comentarios").setChecked(not self.dock_comentarios.isHidden())

    def _estilo_escolhido(self, sid: str) -> None:
        ed_estilos.aplicar_estilo(self.painel, sid)
        self.painel.setFocus()

    def modificar_estilo(self, sid: str | None = None) -> bool:
        """Dialogo "Modificar estilo" do estilo `sid` (padrao: o do paragrafo do cursor)."""
        estilos = pq_estilos.catalogo(self.painel.document())
        sid = sid or ed_estilos.estilo_no_cursor(self.painel)[0]
        estilo = estilos.obter(sid)
        if estilo is None:
            return False
        novo = dialogo_estilo.pedir_estilo(self, estilo, estilos, self._fonte_padrao())
        if novo is not None:
            ed_estilos.redefinir_estilo(self.painel, novo)
        self.painel.setFocus()
        return novo is not None

    def criar_estilo(self) -> str | None:
        """Dialogo "Criar um estilo", com a formatacao da selecao como ponto de partida."""
        estilos = pq_estilos.catalogo(self.painel.document())
        n = 1
        while estilos.por_nome(f"Estilo{n}") is not None:
            n += 1
        modelo = ed_estilos.modelo_da_selecao(self.painel, f"Estilo{n}")
        if modelo is None:
            return None
        escolhido = dialogo_estilo.pedir_estilo(self, modelo, estilos, self._fonte_padrao(),
                                                novo=True)
        sid = None
        if escolhido is not None:
            escolhido.id = estilos.novo_id(escolhido.nome)
            if escolhido.proximo == modelo.id:
                escolhido.proximo = escolhido.id
            sid = ed_estilos.adicionar_estilo(self.painel, escolhido)
        self.painel.setFocus()
        return sid

    def _alternar_painel_estilos(self) -> None:
        self.dock_estilos.setVisible(self.dock_estilos.isHidden())
        self._sintonizar()

    def _alternar_navegacao(self) -> None:
        self.dock_navegacao.setVisible(self.dock_navegacao.isHidden())
        if not self.dock_navegacao.isHidden():
            self.navegacao.atualizar()
        self._sintonizar()

    def _alternar_regua(self) -> None:
        self._regua_visivel = not self._regua_visivel
        self.regua.setVisible(self._regua_visivel)
        self._sintonizar()

    # -- notas (0.1.10) -------------------------------------------------------

    def _pedir_opcoes_notas(self, propriedades: dict, contagens: dict, tipo: str) -> dict | None:
        """O dialogo das opcoes de notas. Os testes trocam este metodo."""
        from editdoc.interface import dialogo_notas
        return dialogo_notas.pedir(self, propriedades, contagens, tipo)

    def opcoes_notas(self) -> bool:
        """Referencias > Opcoes de notas: formato, inicio, reinicio, posicao, ou converter."""
        from editdoc.edicao import notas as ed_notas
        from editdoc.modelo.notas import TIPOS
        from editdoc.ponte_qt import notas as pq_notas
        nota = self.painel.editando_nota()
        tipo = nota.tipo if nota is not None else "rodape"
        corpo = self.painel.documento_corpo()
        cat = pq_notas.catalogo(corpo)
        contagens = {t: sum(1 for _p, m in pq_notas.referencias(corpo) if m.tipo == t)
                     for t in TIPOS}
        escolha = self._pedir_opcoes_notas({t: cat.propriedades(t) for t in TIPOS}, contagens,
                                           tipo)
        if escolha is None:
            return False
        if escolha.get("converter"):
            n = ed_notas.converter(self.painel, escolha["converter"])
            if n:
                self.statusBar().showMessage(f"{n} nota(s) convertida(s).", 4000)
            return bool(n)
        return ed_notas.aplicar_propriedades(self.painel, escolha["tipo"], escolha["pr"])

    # -- comentarios (0.1.6) ------------------------------------------------

    def _autor_comentario(self) -> tuple[str, str]:
        """(nome, iniciais) das Opcoes; vazio = o usuario do Windows."""
        return ed_comentarios.autor_das_preferencias(configuracao.carregar())

    def _pedir_comentario(self, titulo: str, conteudo: tuple = (),
                          somente_leitura: str = "") -> tuple | None:
        """O editor do texto do comentario. Os testes trocam este metodo."""
        return dialogo_comentario.pedir(self, titulo, conteudo, somente_leitura)

    def _alvo(self, ident) -> int | None:
        if isinstance(ident, int) and not isinstance(ident, bool):
            return ident
        return ed_comentarios.no_cursor(self.painel)

    def novo_comentario(self) -> int | None:
        """Revisao > Novo comentario (Ctrl+Alt+M) sobre a selecao."""
        if self.painel.editando_faixa() is not None:
            self.statusBar().showMessage("Comentários ficam no corpo do documento. Saia do "
                                         "cabeçalho ou do rodapé (Esc) para comentar.", 6000)
            return None
        conteudo = self._pedir_comentario("Novo comentário")
        ident = None
        if conteudo is not None:
            nome, iniciais = self._autor_comentario()
            ident = ed_comentarios.novo(self.painel, conteudo, nome, iniciais)
            if ident is not None:
                self.dock_comentarios.show()
        self._atualizar_comentarios()
        self.painel.setFocus()
        return ident

    def responder_comentario(self, ident=None) -> int | None:
        alvo = self._alvo(ident)
        cat = ed_comentarios.catalogo(self.painel)
        if alvo is None or cat.obter(alvo) is None:
            return None
        conteudo = self._pedir_comentario(f"Responder a {cat.obter(alvo).autor or 'comentário'}")
        novo = None
        if conteudo is not None:
            nome, iniciais = self._autor_comentario()
            novo = ed_comentarios.responder(self.painel, alvo, conteudo, nome, iniciais)
        self._atualizar_comentarios()
        self.painel.setFocus()
        return novo

    def editar_comentario(self, ident=None) -> bool:
        alvo = self._alvo(ident)
        cat = ed_comentarios.catalogo(self.painel)
        atual = cat.obter(alvo) if alvo is not None else None
        if atual is None:
            return False
        motivo = ed_comentarios.motivo_somente_leitura(atual)
        titulo = "Comentário (somente leitura)" if motivo else "Editar comentário"
        conteudo = self._pedir_comentario(titulo, atual.paragrafos, motivo)
        mudou = conteudo is not None and ed_comentarios.editar(self.painel, alvo, conteudo)
        self._atualizar_comentarios()
        self.painel.setFocus()
        return mudou

    def resolver_comentario(self, ident=None, valor=None) -> bool:
        alvo = self._alvo(ident)
        cat = ed_comentarios.catalogo(self.painel)
        if alvo is None or cat.obter(alvo) is None:
            return False
        if valor is None:
            raiz = cat.obter(cat.raiz(alvo))
            valor = not (raiz is not None and raiz.resolvido)
        feito = ed_comentarios.resolver(self.painel, alvo, bool(valor))
        self._atualizar_comentarios()
        return feito

    def excluir_comentario(self, ident=None) -> bool:
        alvo = self._alvo(ident)
        if alvo is None:
            return False
        feito = ed_comentarios.excluir(self.painel, alvo)
        self._atualizar_comentarios()
        self.painel.setFocus()
        return feito

    def excluir_todos_comentarios(self) -> int:
        n = ed_comentarios.excluir_todos(self.painel)
        self._atualizar_comentarios()
        if n:
            self.statusBar().showMessage(
                f"{n} comentário{'s' if n != 1 else ''} excluído{'s' if n != 1 else ''}. "
                "Desfazer (Ctrl+Z) os traz de volta.", 6000)
        return n

    def _comentario_vizinho(self, proximo: bool) -> None:
        if ed_comentarios.ir(self.painel, proximo) is None:
            self.statusBar().showMessage("Não há mais comentários nessa direção.", 4000)
        self.painel.setFocus()

    def _comentario_escolhido(self, ident: int) -> None:
        ed_comentarios.selecionar(self.painel, ident)
        self._destacar_comentario()

    def _alternar_comentarios(self) -> None:
        self.dock_comentarios.setVisible(self.dock_comentarios.isHidden())
        self._sintonizar()

    def _comentarios_visiveis(self, _visivel=None) -> None:
        if not self.dock_comentarios.isHidden():
            self._atualizar_comentarios()
        self._sintonizar()

    def _atualizar_comentarios(self) -> None:
        """Refaz os cartoes do painel (so' se o catalogo ou a ordem mudou)."""
        doc = self.painel.documento_corpo()
        cat = pq_comentarios.catalogo(doc)
        ordem = pq_comentarios.ordem_no_texto(doc, cat) if cat.itens else []
        self.painel_comentarios.atualizar(cat, ordem, pq_comentarios.assinatura(doc)[:2])
        self._destacar_comentario()

    def _destacar_comentario(self) -> None:
        if self.dock_comentarios.isHidden():
            return
        self.painel_comentarios.destacar(ed_comentarios.no_cursor(self.painel),
                                         ed_comentarios.catalogo(self.painel))

    # -- pagina ------------------------------------------------------------

    def _pagina_mudou(self) -> None:
        """Papel, orientacao ou margens mudaram (por comando ou ao abrir): marca e rotulo."""
        self.comandos.atualizar_pagina(self.painel.configuracao_pagina())
        self._atualizar_rotulo_pagina()

    def _atualizar_rotulo_pagina(self) -> None:
        atual = self.painel.pagina_atual() + 1
        total = self.painel.total_de_paginas()
        self._rotulo_pagina.setText(f"Página {atual} de {total}")
        secoes = self.painel.total_de_secoes()
        if secoes > 1:
            self._rotulo_secao.setText(f"Seção {self.painel.secao_atual() + 1} de {secoes}")
            self._rotulo_secao.show()
        elif not self._rotulo_secao.isHidden():
            self._rotulo_secao.hide()

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
            if self.painel.total_de_secoes() > 1:
                # Secoes (0.1.12): "Aplicar a: Esta seção / Documento inteiro", como no Word.
                pedido = dialogos_modais.pedir_configurar_pagina(self, atual, varias_secoes=True)
                if pedido is None:
                    self.comandos.atualizar_pagina(atual)
                    return
                nova, documento_inteiro = pedido
                if documento_inteiro:
                    self.painel.definir_configuracao_pagina(nova, documento_inteiro=True)
                    self.painel.documento_corpo().setModified(True)
                    return
                self._alterar_pagina(nova)
                return
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

    def _alternar_vinculo(self) -> None:
        """Vincular ao anterior (0.1.12), na edicao do cabecalho ou do rodape."""
        if self.painel.alternar_vinculo():
            self.painel.documento_corpo().setModified(True)

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

    def _definir_valor_numeracao(self) -> None:
        """Definir valor de numeracao (0.1.4): o numero do item do cursor."""
        from editdoc.edicao import listas as ed_listas
        from editdoc.ponte_qt import listas as pq_listas
        doc = self.painel.document()
        rotulo = pq_listas.numerador_de(doc).rotulos().get(self.painel.textCursor().block().blockNumber())
        if rotulo is None:
            self.painel.setFocus()
            return
        valor = dialogos_modais.pedir_valor_numeracao(self, rotulo.valor)
        if valor is not None:
            ed_listas.definir_valor(self.painel, valor)
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

    def _posicao_tamanho(self) -> None:
        """Posicao e tamanho do objeto selecionado (0.1.9): o dialogo, num passo de desfazer."""
        from editdoc.interface import dialogo_posicao
        dados = self.painel.dados_de_posicao()
        if dados is None:
            return
        escolha = dialogo_posicao.pedir(self, dados)
        if escolha:
            self.painel.aplicar_posicao_tamanho(escolha)
        self.painel.setFocus()

    # -- hiperlinks (0.1.3) -------------------------------------------------

    def _inserir_link(self) -> None:
        """Ctrl+K: insere link no cursor, poe link na selecao ou edita o link do cursor."""
        doc = self.painel.document()
        cursor = self.painel.textCursor()
        existente = links.link_no_cursor(doc, cursor)
        link = None
        if existente is not None and (not cursor.hasSelection() or (
                existente[0] <= cursor.selectionStart() and cursor.selectionEnd() <= existente[1])):
            trecho = (existente[0], existente[1])
            link = existente[2]
        elif cursor.hasSelection():
            trecho = (cursor.selectionStart(), cursor.selectionEnd())
        else:
            trecho = None
        original = ed_links.texto_do_trecho(doc, *trecho) if trecho is not None else ""
        mostrado = original.replace("\u2029", " ").replace("\u2028", " ")
        escolha = dialogos_modais.pedir_link(self, mostrado, link,
                                             marcas.nomes_de_marcadores(self.painel.documento_corpo()),
                                             editar=link is not None)
        if escolha is not None:
            texto, novo = escolha
            if texto == mostrado:
                texto = original  # o texto nao mudou: o link vai por cima, com a formatacao
            if texto:
                ed_links.aplicar_link(self.painel, trecho, texto, novo)
        self.painel.setFocus()

    def _remover_link(self) -> None:
        trecho = links.link_no_cursor(self.painel.document(), self.painel.textCursor())
        if trecho is not None:
            ed_links.remover_link(self.painel, (trecho[0], trecho[1]))
        self.painel.setFocus()

    def _abrir_link(self) -> None:
        trecho = links.link_no_cursor(self.painel.document(), self.painel.textCursor())
        if trecho is not None:
            self.painel.abrir_link(trecho[0])

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
        if self.caminho is not None:
            return self.caminho.name
        return self._nome_recuperado or "Documento em branco"

    def _atualizar_titulo(self) -> None:
        nome = self.caminho.name if self.caminho is not None else self._nome_recuperado
        self.setWindowTitle(titulo_da_janela(nome, self.painel.documento_corpo().isModified()))
        if hasattr(self, "teclado_faixa"):
            acessibilidade.descrever_documento(self)

    def sujo(self) -> bool:
        return self.painel.documento_corpo().isModified()

    def caminho_chave(self) -> str | None:
        """Caminho resolvido, em caixa baixa: impede abrir o mesmo arquivo em duas janelas."""
        if self.caminho is None:
            return None
        return os.path.normcase(os.path.realpath(str(self.caminho)))

    def carregar(self, modelo: Documento, avisos: list[Aviso],
                 caminho: pathlib.Path | None) -> None:
        """Poe o documento lido na janela. Nao deixa o documento sujo."""
        self.painel.sair_da_faixa()
        self.painel.layout_pag.notas.limpar()
        para_qt.preencher(self.painel.documento_corpo(), modelo)
        # Notas (0.1.10): o tipo cuja parte o EditDoc nao leu (preservada so' com as
        # separadoras) nao recebe nota nova.
        sufixos = {"footnotes": "rodape", "endnotes": "fim"}
        self.painel.documento_corpo()._notas_preservadas = {
            sufixos[t.rstrip("/").rsplit("/", 1)[-1]]
            for t, _a, _e in (modelo.pacote.do_documento if modelo.pacote is not None else ())
            if t.rstrip("/").rsplit("/", 1)[-1] in sufixos}
        # Fonte do texto sem formatacao: a do docDefaults do arquivo (M6), ou a configurada.
        estilos = pq_estilos.catalogo(self.painel.documento_corpo())
        familia = estilos.padrao_caractere.get("fonte") or self._fonte_cfg[0]
        meio_pt = estilos.padrao_caractere.get("tamanho_meio_pt")
        self.painel.layout_pag.definir_fonte_padrao(familia, meio_pt / 2 if meio_pt
                                                    else self._fonte_cfg[1])
        self.painel.carregar_faixas(modelo)
        self.painel.definir_pagina_final(modelo.pagina)
        # Listas (0.1.4): o texto depois do numero, medido com a fonte padrao ja' trocada.
        para_qt.concluir_listas(self.painel.documento_corpo())
        # Notas (0.1.10): a area de notas de cada pagina (os espacadores entram antes de zerar o
        # desfazer: o documento aberto nasce sem alteracao).
        self.painel.preparar_notas_ao_abrir()
        self._titulo, self._autor, self._criado_em = modelo.titulo, modelo.autor, modelo.criado_em
        self._pacote = modelo.pacote
        self.caminho = caminho
        self._assinatura = assinatura(caminho)
        self._avisos = list(avisos)
        cursor = self.painel.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.painel.setTextCursor(cursor)
        self.barra_aviso.mostrar(self._avisos)
        self.atualizar_estatisticas()
        self._atualizar_titulo()
        if not self.dock_navegacao.isHidden():
            self.navegacao.atualizar()
        # Comentarios (0.1.6): o painel aparece quando o documento tem comentarios.
        self._atualizar_comentarios()
        if pq_comentarios.catalogo(self.painel.documento_corpo()).itens:
            self.dock_comentarios.show()
        self._sintonizar()
        self.recuperacao.alteracoes = 0

    def trazer_para_frente(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    # -- salvar ------------------------------------------------------------

    def _modelo_atual(self) -> Documento:
        # Nota em edicao (0.1.10): o texto dela vai para o catalogo antes de gravar.
        self.painel.layout_pag.notas.concluir_sessao(sair=False)
        modelo = de_qt.extrair(self.painel.documento_corpo())
        modelo.pagina = replace(self.painel.layout_pag.pagina_arquivo)
        # Secoes (0.1.12): os cabecalhos e rodapes que cada secao declara, e os da ultima.
        self.painel.completar_secoes(modelo)
        modelo.titulo = self._titulo
        modelo.autor = self._autor
        modelo.criado_em = self._criado_em
        modelo.pacote = self._pacote
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
        if self.caminho is not None:
            sugestao = self.caminho.name
        elif self._original_recuperado:
            # Documento recuperado: sugere o lugar de onde ele veio (o usuario confirma).
            sugestao = self._original_recuperado
        else:
            sugestao = "Documento.docx"
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
            return self._falha_na_conferencia(alvo, dados)
        except ErroDocx as erro:
            log.error("arquivo gravado nao pode ser lido: %s", erro.codigo)
            return self._falha_na_conferencia(alvo, dados)
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
            self._nome_recuperado = self._original_recuperado = None
            self.recuperacao.salvo()
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

    def _falha_na_conferencia(self, alvo: pathlib.Path, dados: bytes) -> bool:
        """A releitura do arquivo gravado nao bateu (0.1.11): nada foi substituido.

        Explica sem jargao (o detalhe ja' foi para o log), grava a copia de recuperacao e
        oferece salvar os mesmos bytes, sem a conferencia, em OUTRO arquivo. Devolve False:
        o documento nao foi salvo e continua "alterado".
        """
        self.recuperacao.gravar_agora()
        escolha = dialogos_modais.pedir_falha_na_conferencia(
            self, alvo.name, str(log_interno.caminho_do_log()))
        if escolha != "copia":
            return False
        sugestao = str(alvo.with_name(f"{alvo.stem} (não conferido).docx"))
        escolhido = dialogos_modais.pedir_salvar_arquivo(self, sugestao)
        if not escolhido:
            return False
        destino = pathlib.Path(escolhido)
        protegidos = {p.resolve() for p in (alvo, self.caminho) if p is not None}
        if destino.resolve() in protegidos:
            dialogos_modais.avisar(self, "Salvar", "A cópia não conferida não pode substituir o "
                                   "arquivo original. Escolha outro nome ou outra pasta.")
            return False
        try:
            gravacao.gravar_bytes(destino, dados)
        except OSError as erro:
            log.error("copia nao conferida em %s falhou: %s", destino, erro)
            dialogos_modais.avisar(self, "Salvar", "Não foi possível gravar a cópia. Verifique "
                                   "se há espaço em disco e se a pasta aceita gravação. "
                                   "O original NÃO foi alterado.")
            return False
        log.warning("copia nao conferida gravada em %s", destino)
        self.statusBar().showMessage(
            f"Cópia não conferida salva em {destino.name}. O documento continua em "
            f"{self._nome()}, ainda não salvo.", 8000)
        return False

    def pode_fechar(self) -> bool:
        """Sem alteracao, sim. Com alteracao, pergunta: salvar, descartar ou cancelar."""
        if not self.sujo():
            return True
        escolha = dialogos_modais.pedir_descartar(self, self._nome())
        if escolha == "salvar":
            return self.salvar()
        return escolha == "descartar"

    # -- impressao e PDF (M7) --------------------------------------------------

    def _sugestao(self, extensao: str) -> str:
        """Nome sugerido para exportar: o do documento, com a extensao nova, na mesma pasta."""
        if self.caminho is None:
            return f"Documento{extensao}"
        return str(self.caminho.with_suffix(extensao))

    def _metadados_pdf(self) -> impressao.Metadados:
        """Titulo e autor do docProps/core.xml; sem titulo, o nome do arquivo."""
        titulo = self._titulo or (self.caminho.stem if self.caminho is not None
                                  else "Documento em branco")
        return impressao.Metadados(titulo=titulo, autor=self._autor)

    def exportar_pdf(self) -> bool:
        """Arquivo > Exportar > PDF: paginas, destino e a gravacao, com progresso e cancelar."""
        painel = self.painel
        painel.preparar_para_impressao()
        total, atual = painel.total_de_paginas(), painel.pagina_atual()
        opcoes = dialogos_modais.pedir_opcoes_pdf(self, total, atual, self._abrir_pdf)
        if opcoes is None:
            return False
        self._abrir_pdf = opcoes.abrir
        destino = dialogos_modais.pedir_salvar_pdf(self, self._sugestao(".pdf"))
        if not destino:
            return False
        alvo = pathlib.Path(destino)
        barra = impressao.BarraDeProgresso(self, "Exportar PDF", "Gerando o PDF.",
                                           len(opcoes.paginas))
        try:
            impressao.exportar_pdf(alvo, painel.layout_pag, opcoes.paginas,
                                   self._metadados_pdf(), barra)
        except impressao.Cancelado:
            self.statusBar().showMessage("Exportação cancelada. Nenhum arquivo foi gravado.", 6000)
            return False
        except (gravacao.SemEspaco, gravacao.FalhaNaTroca) as erro:
            dialogos_modais.avisar(self, "Exportar PDF", str(erro))
            return False
        except (OSError, impressao.PdfInvalido, impressao.FalhaNaImpressao) as erro:
            log.error("exportacao de PDF para %s falhou: %s", alvo, erro)
            dialogos_modais.avisar(self, "Exportar PDF", "Não foi possível gravar o PDF. Verifique "
                                   "se ele não está aberto em outro programa e se há espaço em "
                                   "disco. Um arquivo que já existia NÃO foi alterado.")
            return False
        finally:
            barra.fechar()
        n = len(opcoes.paginas)
        self.statusBar().showMessage(
            f"PDF exportado: {alvo.name} ({n} página{'s' if n != 1 else ''})", 6000)
        if opcoes.abrir and not impressao.abrir_arquivo(alvo):
            dialogos_modais.avisar(self, "Exportar PDF", "O PDF foi gravado, mas o Windows não "
                                   "abriu um leitor de PDF para ele.")
        return True

    def exportar_txt(self) -> bool:
        """Arquivo > Exportar > Texto sem formatacao: so' o texto do corpo, em UTF-8."""
        destino = dialogos_modais.pedir_salvar_txt(self, self._sugestao(".txt"))
        if not destino:
            return False
        alvo = pathlib.Path(destino)
        self.painel.layout_pag.notas.concluir_sessao(sair=False)
        texto = texto_do_documento(de_qt.extrair(self.painel.documento_corpo()),
                                   getattr(self.painel.documento_corpo(), "_numeros_notas", None))
        try:
            gravacao.gravar_bytes(alvo, texto.encode("utf-8"))
        except (gravacao.SemEspaco, gravacao.FalhaNaTroca) as erro:
            dialogos_modais.avisar(self, "Exportar texto", str(erro))
            return False
        except OSError as erro:
            log.error("exportacao de texto para %s falhou: %s", alvo, erro)
            dialogos_modais.avisar(self, "Exportar texto", "Não foi possível gravar o arquivo de "
                                   "texto. Um arquivo que já existia NÃO foi alterado.")
            return False
        self.statusBar().showMessage(f"Texto exportado: {alvo.name}", 6000)
        return True

    def imprimir(self) -> bool:
        """Ctrl+P: dialogo do sistema, papel do documento, paginas com progresso e cancelar."""
        if not impressao.impressoras():
            dialogos_modais.avisar(self, "Imprimir", "Nenhuma impressora está instalada no "
                                   "Windows. Para ter o documento pronto para imprimir em outro "
                                   "lugar, use Arquivo > Exportar > PDF.")
            return False
        painel = self.painel
        painel.preparar_para_impressao()
        total, atual = painel.total_de_paginas(), painel.pagina_atual()
        pagina = painel.layout_pag.pagina_da_folha(0)  # 0.1.12: o papel da primeira folha
        impressora = impressao.nova_impressora()
        impressao.configurar_impressora(impressora, pagina)
        if not dialogos_modais.pedir_impressao(self, impressora, total, atual):
            return False
        # A impressora pode ter mudado no dialogo: o papel e' conferido na escolhida.
        if not impressao.configurar_impressora(impressora, pagina):
            pergunta = (f"A impressora \"{impressora.printerName()}\" não aceita o papel do "
                        f"documento, {impressao.descrever_papel(pagina)}. Imprimir no papel dela, "
                        "sem mudar o tamanho do texto? Parte da página pode ficar de fora.")
            if not dialogos_modais.confirmar(self, "Imprimir", pergunta):
                return False
        paginas = impressao.paginas_da_impressora(impressora, total, atual)
        barra = impressao.BarraDeProgresso(self, "Imprimir", "Enviando para a impressora.",
                                           len(paginas))
        try:
            enviadas = impressao.imprimir(impressora, painel.layout_pag, paginas, barra)
        except impressao.Cancelado:
            self.statusBar().showMessage("Impressão cancelada.", 6000)
            return False
        except impressao.FalhaNaImpressao as erro:
            log.error("impressao em %s falhou: %s", impressora.printerName(), erro)
            dialogos_modais.avisar(self, "Imprimir", "Não foi possível começar a impressão em "
                                   f"\"{impressora.printerName()}\". Confira se a impressora "
                                   "está ligada e disponível.")
            return False
        finally:
            barra.fechar()
        self.statusBar().showMessage(
            f"Enviado para {impressora.printerName() or 'a impressora'}: {enviadas} "
            f"página{'s' if enviadas != 1 else ''}.", 6000)
        return True

    def visualizar_impressao(self) -> None:
        """Pre-visualizacao: as folhas como saem no papel, com navegacao, zoom e Imprimir."""
        painel = self.painel
        painel.preparar_para_impressao()
        impressora = impressao.nova_impressora(pdf=not impressao.impressoras())
        # O papel da primeira folha (0.1.12: com secoes, cada folha troca para o seu).
        impressao.configurar_impressora(impressora, painel.layout_pag.pagina_da_folha(0))

        def progresso(total: int):
            return impressao.BarraDeProgresso(self, "Visualizar impressão",
                                              "Preparando as páginas.", total)

        dialogo = impressao.criar_previa(self, painel.layout_pag, impressora,
                                         painel.pagina_atual(), progresso)
        try:
            dialogos_modais.mostrar_previa(dialogo)
        finally:
            dialogo.deleteLater()
        painel.setFocus()

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
            # Fechamento normal (salvo ou descartado de proposito): a copia sai.
            self.recuperacao.encerrar()
            if self._gerente is not None:
                self._gerente.fechou(self)
            evento.accept()
        else:
            evento.ignore()
