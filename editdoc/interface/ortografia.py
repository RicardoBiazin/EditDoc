"""Corretor ortografico na tela (0.1.35): sublinhado ondulado, menu de sugestoes e F7.

COMO FUNCIONA

- O sublinhado e' PINTADO por cima do texto (`desenhar`, na funcao unica de pintura da folha, so'
  na tela). Nada entra no QTextDocument: nem formato, nem propriedade, nem desfazer, nem
  "alterado", nem o arquivo salvo. Impressao e PDF nao o passam.
- A verificacao e' incremental e fora do caminho da tecla: cada mudanca de texto so' reinicia um
  `QTimer` ocioso; quando o usuario para, uma varredura comeca no bloco do alto da tela e anda
  pelo documento em fatias de poucos milissegundos (`FATIA_S`), de modo que o que se ve fica
  pronto primeiro e a janela nunca para. O resultado e' guardado por TEXTO do bloco
  (`_por_bloco`): bloco que nao mudou nao e' verificado de novo, e a mudanca de um bloco nao
  depende de numero de bloco nem de posicao.
- Enquanto o bloco digitado nao tem resultado novo, vale o que se sabe das palavras ja'
  marcadas (`_erradas`), de modo que o sublinhado das outras palavras nao some a cada tecla; e a
  palavra em que o caret esta' (a que se acabou de digitar) nao e' sublinhada ate' o caret sair.
- Quem corrige e' um `editdoc.ortografia.Corretor` (o do Windows; nos testes, um falso). Sem
  corretor, ou com idioma que nao esta' instalado, a verificacao fica desligada com um aviso na
  barra de status e nada mais acontece.

O texto verificado nunca vai a servico externo: a API do Windows e' local.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPainterPath, QPen, QTextCursor
from PySide6.QtWidgets import QMenu

from editdoc import log_interno
from editdoc.formato_docx.idioma_texto import idiomas_de_estilos
from editdoc.ortografia import (IDIOMA_PADRAO, MAXIMO_DE_SUGESTOES, PALAVRA, Corretor, Erro,
                                ErroDoCorretor, corretor_desligado_de_proposito, criar_corretor,
                                normalizar_etiqueta)
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt import ortografia as pq_ortografia

log = log_interno.obter(__name__)

#: Vermelho do sublinhado (o do Word).
COR_ONDA = QColor(224, 32, 32)
#: Quanto o usuario precisa ficar parado antes de a varredura comecar (ms).
ATRASO_MS = 350
#: Pausa entre duas fatias da varredura (ms) e a duracao de cada fatia (s).
PASSO_MS = 8
FATIA_S = 0.006
#: Teto de blocos guardados; passando disso o guardado e' refeito (a varredura reverifica).
LIMITE_DO_CACHE = 30000
#: Tempo maximo (s) que F7 espera para achar o proximo erro num documento que ainda nao foi
#: varrido.
ESPERA_DO_F7_S = 6.0
IDIOMA_AUTOMATICO = "auto"


def nome_do_idioma(etiqueta: str) -> str:
    """"pt-BR" -> "Português (Brasil)" (pelo QLocale; a etiqueta se o Qt nao conhece)."""
    from PySide6.QtCore import QLocale
    loc = QLocale(etiqueta)
    if loc.language() == QLocale.Language.C:
        return etiqueta
    lingua = loc.nativeLanguageName()
    territorio = loc.nativeTerritoryName()
    if not lingua:
        return etiqueta
    lingua = lingua[:1].upper() + lingua[1:]
    return f"{lingua} ({territorio})" if territorio else lingua


class Ortografia(QObject):
    """O corretor de UM painel (o corpo do documento dele)."""

    #: Mudou se a verificacao esta' valendo (ligada, com corretor, sem falha).
    estadoAlterado = Signal()

    def __init__(self, painel) -> None:
        super().__init__(painel)
        self.painel = painel
        self.ligada = True
        self.idioma = IDIOMA_AUTOMATICO
        self._corretor: Corretor | None = None
        self._resolvido = False
        self._desligada = False
        self._conferido: str | None = None
        self._estilos = None
        self._padrao = IDIOMA_PADRAO
        self._por_bloco: dict[str, tuple] = {}
        self._erradas: set[str] = set()
        #: Memoria curta do que se pinta para texto sem resultado (sai quando `_erradas` muda).
        self._memo: dict[str, tuple] = {}
        self._ignoradas: set[str] = set()
        self._uma_vez: set[tuple] = set()
        self._editou_em: int | None = None
        self._pos: int | None = None
        self._restam = 0
        #: Quantos blocos o corretor ja' verificou (os testes conferem que so' os mudados).
        self.verificacoes = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._passo)
        #: Quem mostra o menu e devolve a acao escolhida (None = fechou). Os testes trocam.
        self.escolher = lambda menu, ponto: menu.exec(ponto)
        doc = painel.documento_corpo()
        doc._ortografia = self
        doc.contentsChange.connect(self._mudou)
        painel.cursorPositionChanged.connect(self._caret_mudou)
        painel.verticalScrollBar().valueChanged.connect(self._rolou)

    # -- estado -----------------------------------------------------------------------------
    @property
    def corretor(self) -> Corretor | None:
        return self._corretor

    def _resolver_corretor(self) -> Corretor | None:
        if not self._resolvido:
            self._resolvido = True
            self._corretor = criar_corretor()
            if self._corretor is None and not corretor_desligado_de_proposito():
                self._avisar("A verificação ortográfica não está disponível neste computador.")
        return self._corretor

    def definir_corretor(self, corretor: Corretor | None) -> None:
        """Troca o corretor (os testes usam o falso) e recomeca."""
        self._corretor = corretor
        self._resolvido = True
        self._desligada = False
        self._conferido = None
        self._reiniciar()

    def pintando(self) -> bool:
        return (self.ligada and not self._desligada and self._corretor is not None
                and bool(self._erradas))

    def disponivel(self) -> bool:
        """Ha' corretor que serve para o idioma de agora (com ou sem verificar enquanto digita:
        o F7 funciona com a opcao desligada, como no Word)."""
        return self._pronto() is not None

    def aplicar_preferencias(self, cfg: dict) -> None:
        ligada = bool(cfg.get("ortografia_ligada", True))
        idioma = cfg.get("ortografia_idioma", IDIOMA_AUTOMATICO)
        idioma = IDIOMA_AUTOMATICO if idioma == IDIOMA_AUTOMATICO else (
            normalizar_etiqueta(idioma) or IDIOMA_AUTOMATICO)
        if ligada == self.ligada and idioma == self.idioma:
            return
        self.ligada, self.idioma = ligada, idioma
        self._desligada = False
        self._conferido = None
        self._reiniciar()
        self.estadoAlterado.emit()

    def idiomas_disponiveis(self) -> list[str]:
        """Os idiomas que o corretor tem (vazio sem corretor). Resolve o corretor."""
        c = self._resolver_corretor()
        if c is None:
            return []
        try:
            return c.idiomas()
        except ErroDoCorretor as erro:
            log.warning("idiomas do corretor: %s", erro)
            return []

    def ao_carregar(self) -> None:
        """Documento novo na janela: o idioma e os estilos vem do arquivo; recomeca."""
        doc = self.painel.documento_corpo()
        xml = getattr(pq_estilos.catalogo(doc), "xml_original", None)
        self._estilos = idiomas_de_estilos(xml)
        self._padrao = self._estilos.padrao or IDIOMA_PADRAO
        self._ignoradas.clear()
        self._conferido = None
        self._desligada = False
        self._editou_em = None
        self._reiniciar()

    def _idioma_efetivo(self) -> str:
        if self.idioma != IDIOMA_AUTOMATICO:
            return self.idioma
        return self._padrao

    def _contexto(self) -> pq_ortografia.Contexto:
        forcado = None if self.idioma == IDIOMA_AUTOMATICO else self.idioma
        return pq_ortografia.Contexto(forcado, self._padrao, self._estilos)

    def _avisar(self, texto: str) -> None:
        log.info(texto)
        try:
            self.painel.mensagem.emit(texto)
        except RuntimeError:
            pass

    def _desligar(self, motivo: str) -> None:
        self._desligada = True
        self._por_bloco.clear()
        self._erradas.clear()
        self._memo.clear()
        self._pos = None
        self._avisar(motivo)
        self._atualizar_tela()
        self.estadoAlterado.emit()

    def _reiniciar(self) -> None:
        """Esquece o que sabe e verifica de novo (documento, idioma ou dicionario mudou)."""
        self._por_bloco.clear()
        self._erradas.clear()
        self._memo.clear()
        self._uma_vez.clear()
        self._pos = None
        self._atualizar_tela(tudo=True)
        self.agendar(60)

    def _atualizar_tela(self, tudo: bool = False) -> None:
        v = self.painel
        if tudo:
            v._limpar_cache()
        v.viewport().update()

    # -- agenda -----------------------------------------------------------------------------
    def agendar(self, atraso: int = ATRASO_MS) -> None:
        if self.ligada and not self._desligada:
            self._timer.start(atraso)

    def _mudou(self, pos: int, removido: int, adicionado: int) -> None:
        """Mudou o texto (o caminho da tecla: so' anota e reinicia o timer)."""
        if not self.ligada or self._desligada:
            return
        self._editou_em = pos + adicionado
        self._pos = None
        self._timer.start(ATRASO_MS)

    def _rolou(self, _valor: int) -> None:
        # Varredura em andamento: recomeca do alto da tela de agora (o que ja' foi verificado
        # fica guardado e e' pulado).
        if self.ligada and not self._desligada and self._pos is not None:
            self._pos = None
            self._timer.start(60)

    def _caret_mudou(self) -> None:
        """O caret saiu da palavra que se digitava: ela passa a ser sublinhada."""
        if self._editou_em is None:
            return
        p = self.painel
        if p._no_corpo() and not p._cursor.hasSelection() and p._cursor.position() == self._editou_em:
            return
        antes = self._editou_em
        self._editou_em = None
        if self.pintando():
            doc = p.documento_corpo()
            self._invalidar(doc.findBlock(min(antes, doc.characterCount() - 1)))
            p.viewport().update()

    # -- varredura --------------------------------------------------------------------------
    def _posicao_do_topo(self) -> int:
        p = self.painel
        try:
            vp = p.viewport()
            return max(0, p.posicao_em(QPointF(vp.width() / 2.0, 2.0)))
        except Exception:  # noqa: BLE001 - o alto da tela e' so' uma dica
            return 0

    def _passo(self) -> None:
        if not self.ligada or self._desligada:
            return
        try:
            self._fatia()
        except ErroDoCorretor as erro:
            log.warning("corretor falhou: %s", erro)
            self._desligar("A verificação ortográfica foi desligada: o corretor do Windows "
                           "não respondeu.")
        except Exception:  # noqa: BLE001 - nunca derruba a janela
            log.exception("verificacao ortografica")
            self._desligar("A verificação ortográfica foi desligada por um erro.")

    def _pronto(self) -> Corretor | None:
        """O corretor, com o idioma de agora conferido; None se nao serve (e ja' desligou, com o
        aviso do motivo na barra de status)."""
        if self._desligada:
            return None
        corretor = self._resolver_corretor()
        if corretor is None:
            self._desligada = True
            self.estadoAlterado.emit()
            return None
        idioma = self._idioma_efetivo()
        if self._conferido != idioma:
            self._conferido = idioma
            if not corretor.suporta(idioma):
                self._desligar(f"Verificação ortográfica desligada: o idioma "
                               f"{nome_do_idioma(idioma)} não está instalado no Windows.")
                return None
            self.estadoAlterado.emit()
        return corretor

    def _fatia(self) -> None:
        if self._pronto() is None:
            return
        doc = self.painel.documento_corpo()
        if self._pos is None:
            self._pos = self._posicao_do_topo()
            self._restam = doc.blockCount()
        limite = time.perf_counter() + FATIA_S
        mudou = False
        bloco = doc.findBlock(self._pos)
        while self._restam > 0:
            if not bloco.isValid():
                bloco = doc.begin()
            self._restam -= 1
            if self._conferir(bloco):
                mudou = True
            bloco = bloco.next()
            if time.perf_counter() > limite:
                break
        if self._restam > 0:
            self._pos = bloco.position() if bloco.isValid() else 0
            self._timer.start(PASSO_MS)
        else:
            self._pos = None
        if mudou:
            self.painel.viewport().update()

    def _conferir(self, bloco) -> bool:
        """Verifica o bloco se o texto dele ainda nao tem resultado. True se o que se ve mudou."""
        texto = bloco.text()
        if texto in self._por_bloco or not texto or texto.isspace() or not bloco.isVisible():
            return False
        antes = self._erros_conhecidos(texto)
        novos = self._calcular(bloco, texto)
        if len(self._por_bloco) >= LIMITE_DO_CACHE:
            self._por_bloco.clear()
        self._por_bloco[texto] = novos
        if [(e.ini, e.fim) for e in antes] == [(e.ini, e.fim) for e in novos]:
            return False
        self._invalidar(bloco)
        return True

    def _calcular(self, bloco, texto: str) -> tuple:
        """Os erros do bloco, em posicoes do bloco. Pede ao corretor trecho a trecho."""
        corretor = self._corretor
        erros: list[Erro] = []
        for tr in pq_ortografia.trechos_do_bloco(bloco, self._contexto()):
            if not corretor.suporta(tr.idioma):
                continue  # idioma de um trecho que nao esta' instalado: sem verificacao ali
            self.verificacoes += 1
            for e in corretor.verificar(tr.texto, tr.idioma):
                a, b = tr.intervalo_no_bloco(e.ini, e.fim)
                palavra = texto[a:b]
                chave = palavra.casefold()
                if chave in self._ignoradas or (texto, a, b) in self._uma_vez:
                    continue
                if palavra not in self._erradas:
                    self._erradas.add(palavra)
                    self._memo.clear()
                erros.append(Erro(a, b, e.acao, e.troca))
        return tuple(erros)

    def _erros_conhecidos(self, texto: str) -> tuple:
        """O que a tela mostraria agora para este texto de bloco (sem a regra do caret): o
        resultado guardado ou, sem ele, as palavras ja' marcadas em outro lugar."""
        achado = self._por_bloco.get(texto)
        if achado is not None:
            return achado
        if not self._erradas:
            return ()
        # Sem resultado (o bloco que se digita): so' as palavras ja' marcadas. A tecla pinta o
        # mesmo texto varias vezes (um tile por parte), entao o resultado fica numa memoria curta;
        # `findall` primeiro, porque o bloco quase nunca tem palavra marcada.
        memo = self._memo.get(texto)
        if memo is not None:
            return memo
        if self._erradas.isdisjoint(PALAVRA.findall(texto)):
            achado = ()
        else:
            achado = tuple(Erro(m.start(), m.end()) for m in PALAVRA.finditer(texto)
                           if m.group() in self._erradas)
        if len(self._memo) >= 32:
            self._memo.clear()
        self._memo[texto] = achado
        return achado

    def erros_a_pintar(self, bloco) -> list[tuple[int, int]]:
        """[(ini, fim)] no bloco que a tela sublinha: os conhecidos, menos a palavra em que o
        caret acaba de digitar."""
        erros = self._erros_conhecidos(bloco.text())
        if not erros:
            return []
        saida = [(e.ini, e.fim) for e in erros]
        if self._editou_em is not None and self.painel._no_corpo():
            c = self.painel._cursor
            if not c.hasSelection() and c.position() == self._editou_em:
                base = bloco.position()
                saida = [(a, b) for a, b in saida
                         if not (base + a <= self._editou_em <= base + b)]
        return saida

    def _invalidar(self, bloco) -> None:
        """Tira do cache de tiles so' a faixa do bloco (a tela repinta a parte)."""
        if not bloco.isValid():
            return
        v = self.painel
        try:
            topo, base = v._extensao(bloco)
            v._invalidar_linhas((None, topo), topo, base)
        except Exception:  # noqa: BLE001 - na duvida, o cache todo
            v._limpar_cache()

    # -- erros e menu -----------------------------------------------------------------------
    def _erros_do_bloco(self, bloco) -> tuple:
        """Os erros do bloco, verificando agora se preciso (menu e F7)."""
        texto = bloco.text()
        achado = self._por_bloco.get(texto)
        if achado is not None:
            return achado
        if not texto or texto.isspace() or self._corretor is None:
            return ()
        achado = self._calcular(bloco, texto)
        self._por_bloco[texto] = achado
        return achado

    def erro_em(self, pos: int, mesmo_desligada: bool = False):
        """(bloco, Erro) da palavra errada que contem a posicao `pos` do corpo, ou None. Com a
        verificacao enquanto digita desligada nada esta' sublinhado, entao nao ha' o que corrigir
        (so' o F7 pede `mesmo_desligada`)."""
        if not (self.ligada or mesmo_desligada) or not self.disponivel():
            return None
        doc = self.painel.documento_corpo()
        bloco = doc.findBlock(min(max(pos, 0), doc.characterCount() - 1))
        try:
            erros = self._erros_do_bloco(bloco)
        except (ErroDoCorretor, OSError) as erro:
            log.warning("corretor: %s", erro)
            return None
        rel = pos - bloco.position()
        for e in erros:
            if e.ini <= rel < e.fim:
                return bloco, e
        for e in erros:
            if e.ini <= rel <= e.fim:
                return bloco, e
        return None

    def _idioma_em(self, bloco, rel: int) -> str:
        for tr in pq_ortografia.trechos_do_bloco(bloco, self._contexto()):
            a, b = tr.intervalo_no_bloco(0, len(tr.texto))
            if a <= rel <= b:
                return tr.idioma
        return self._idioma_efetivo()

    def montar_menu(self, menu: QMenu, pos: int, mesmo_desligada: bool = False) -> bool:
        """Poe no alto do menu as sugestoes, Ignorar, Ignorar tudo e Adicionar ao dicionario da
        palavra errada em `pos`. False (e nada muda) se a palavra nao esta' errada."""
        achado = self.erro_em(pos, mesmo_desligada)
        if achado is None:
            return False
        bloco, erro = achado
        texto = bloco.text()
        palavra = texto[erro.ini:erro.fim]
        idioma = self._idioma_em(bloco, erro.ini)
        itens: list[QAction | None] = []
        if erro.acao == "excluir":
            itens.append(self._acao_negrito(
                f"Excluir a palavra repetida \"{palavra}\"",
                lambda: self._trocar(bloco.position(), erro, ""), menu))
        else:
            sugestoes = [erro.troca] if erro.acao == "substituir" and erro.troca else []
            try:
                for s in self._corretor.sugerir(palavra, idioma):
                    if s not in sugestoes:
                        sugestoes.append(s)
            except ErroDoCorretor as falha:
                log.warning("sugestoes: %s", falha)
            for s in sugestoes[:MAXIMO_DE_SUGESTOES]:
                itens.append(self._acao_negrito(
                    s, lambda s=s: self._trocar(bloco.position(), erro, s), menu))
            if not itens:
                vazio = QAction("(sem sugestões)", menu)
                vazio.setEnabled(False)
                itens.append(vazio)
        itens.append(None)
        base = bloco.position()
        for texto_acao, funcao in (
                ("Ignorar", lambda: self.ignorar(base, erro)),
                ("Ignorar tudo", lambda: self.ignorar_tudo(palavra)),
                ("Adicionar ao dicionário", lambda: self.adicionar(palavra, idioma))):
            a = QAction(texto_acao, menu)
            a.triggered.connect(lambda _=False, f=funcao: f())
            itens.append(a)
        itens.append(None)
        primeiro = menu.actions()[0] if menu.actions() else None
        for item in itens:
            if item is None:
                menu.insertSeparator(primeiro) if primeiro is not None else menu.addSeparator()
            elif primeiro is not None:
                menu.insertAction(primeiro, item)
            else:
                menu.addAction(item)
        return True

    @staticmethod
    def _acao_negrito(texto: str, funcao, pai) -> QAction:
        acao = QAction(texto, pai)  # sem dono, o Python a destruiria ao sair daqui
        fonte = acao.font()
        fonte.setBold(True)
        acao.setFont(fonte)
        acao.triggered.connect(lambda _=False: funcao())
        return acao

    # -- o que o usuario escolhe ------------------------------------------------------------
    def _trocar(self, base_do_bloco: int, erro: Erro, novo: str) -> None:
        """Troca a palavra errada: um passo de desfazer, com o formato da palavra."""
        from editdoc.edicao import busca
        p = self.painel
        doc = p.documento_corpo()
        ini, fim = base_do_bloco + erro.ini, base_do_bloco + erro.fim
        if novo == "":
            # Palavra repetida: sai junto o espaco que a separa da anterior (ou, no comeco do
            # paragrafo, o da seguinte).
            texto = doc.findBlock(ini).text()
            a, b = erro.ini, erro.fim
            k = a
            while k > 0 and texto[k - 1] == " ":
                k -= 1
            if k < a:
                a = k
            else:
                while b < len(texto) and texto[b] == " ":
                    b += 1
            ini, fim = base_do_bloco + a, base_do_bloco + b
        cursor = QTextCursor(doc)
        cursor.setPosition(ini)
        cursor.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
        cursor.beginEditBlock()
        busca._trocar(p, cursor, novo)
        cursor.endEditBlock()
        p.setTextCursor(cursor)

    def ignorar(self, base_do_bloco: int, erro: Erro) -> None:
        """Ignora esta ocorrencia (ate' o texto do bloco mudar)."""
        doc = self.painel.documento_corpo()
        bloco = doc.findBlock(base_do_bloco)
        texto = bloco.text()
        self._uma_vez.add((texto, erro.ini, erro.fim))
        achado = self._por_bloco.get(texto)
        if achado is not None:
            self._por_bloco[texto] = tuple(
                e for e in achado if (e.ini, e.fim) != (erro.ini, erro.fim))
        self._invalidar(bloco)
        self.painel.viewport().update()

    def ignorar_tudo(self, palavra: str) -> None:
        """Ignora a palavra em todo o documento, ate' abrir outro (ou fechar o programa)."""
        self._ignoradas.add(palavra.casefold())
        self._esquecer_palavra(palavra)

    def adicionar(self, palavra: str, idioma: str) -> None:
        """Poe a palavra no dicionario pessoal do Windows (vale para os outros programas)."""
        try:
            self._corretor.adicionar(palavra, idioma)
        except ErroDoCorretor as erro:
            log.warning("adicionar ao dicionario: %s", erro)
            self._avisar("Não foi possível adicionar a palavra ao dicionário.")
            return
        self._ignoradas.add(palavra.casefold())
        self._esquecer_palavra(palavra)
        self._avisar(f"\"{palavra}\" foi adicionada ao dicionário.")

    def _esquecer_palavra(self, palavra: str) -> None:
        chave = palavra.casefold()
        self._erradas = {w for w in self._erradas if w.casefold() != chave}
        self._memo.clear()
        for texto, erros in list(self._por_bloco.items()):
            if any(texto[e.ini:e.fim].casefold() == chave for e in erros):
                self._por_bloco[texto] = tuple(
                    e for e in erros if texto[e.ini:e.fim].casefold() != chave)
        self._atualizar_tela(tudo=True)

    # -- F7: percorrer os erros -------------------------------------------------------------
    def proximo_erro(self, desde: int | None = None) -> tuple[int, int] | None:
        """(ini, fim) no corpo do proximo erro depois de `desde` (o caret, por padrao), dando a
        volta no documento. None se nao ha' nenhum. Verifica na hora o que ainda nao foi
        verificado, por ate' `ESPERA_DO_F7_S`."""
        if not self.disponivel():
            return None
        p = self.painel
        doc = p.documento_corpo()
        if desde is None:
            c = p._cursor
            desde = c.selectionEnd() if c.hasSelection() else c.position()
        desde = min(max(desde, 0), doc.characterCount() - 1)
        primeiro = doc.findBlock(desde)
        limite = time.monotonic() + ESPERA_DO_F7_S
        bloco = primeiro
        for passo in range(doc.blockCount() + 1):
            if not bloco.isValid():
                bloco = doc.begin()
            base = bloco.position()
            erros = self._erros_do_bloco(bloco) if bloco.isVisible() else ()
            # O bloco do caret so' conta o que vem depois do caret; os outros contam inteiros
            # (a volta no documento); no fim, o bloco do caret de novo, so' o que veio antes.
            for e in erros:
                if passo == 0:
                    vale = base + e.fim > desde
                elif passo == doc.blockCount():
                    vale = base + e.fim <= desde
                else:
                    vale = True
                if vale:
                    return base + e.ini, base + e.fim
            bloco = bloco.next()
            if time.monotonic() > limite:
                self._avisar("A verificação ainda está em andamento; tente de novo em instantes.")
                return None
        return None

    def selecionar(self, ini: int, fim: int) -> None:
        p = self.painel
        cursor = QTextCursor(p.documento_corpo())
        cursor.setPosition(ini)
        cursor.setPosition(fim, QTextCursor.MoveMode.KeepAnchor)
        p.setTextCursor(cursor)

    def _ponto_do_menu(self, pos: int):
        """Ponto global logo abaixo da palavra (para o menu do F7)."""
        from PySide6.QtCore import QPoint
        p = self.painel
        r = p.layout_pag.retangulo_cursor(pos)
        x, y = p._mapa().doc_para_tela(r.x(), r.bottom(), p._paginas())
        return p.viewport().mapToGlobal(QPoint(int(x), int(y) + 2))

    def percorrer(self) -> int:
        """F7 e o botao Ortografia: vai ao proximo erro, seleciona e abre o menu de sugestoes;
        escolhida uma acao, segue para o proximo; Esc encerra. Devolve quantos tratou."""
        p = self.painel
        if not p._no_corpo():
            self._avisar("A verificação ortográfica vale para o corpo do documento.")
            return 0
        if self._desligada:
            self._avisar("A verificação ortográfica não está disponível.")
            return 0
        if not self.disponivel():
            if self._corretor is None:
                self._avisar("A verificação ortográfica não está disponível neste computador.")
            return 0  # com corretor, `_pronto` ja' avisou o motivo
        tratados = 0
        anterior = None
        while tratados < 100000:
            try:
                achado = self.proximo_erro()
            except ErroDoCorretor as erro:
                log.warning("corretor falhou no F7: %s", erro)
                self._desligar("A verificação ortográfica foi desligada: o corretor do Windows "
                               "não respondeu.")
                break
            if achado is None or achado == anterior:
                self._avisar("Verificação ortográfica concluída." if tratados
                             else "Nenhum erro de ortografia encontrado.")
                break
            anterior = achado
            self.selecionar(*achado)
            menu = QMenu(p)
            if not self.montar_menu(menu, achado[0], mesmo_desligada=True):
                break
            escolhida = self.escolher(menu, self._ponto_do_menu(achado[0]))
            menu.deleteLater()
            if escolhida is None:
                break
            tratados += 1
        return tratados


# -- pintura ---------------------------------------------------------------------------------

def _onda(painter, x0: float, x1: float, y: float, amp: float) -> None:
    """Zigue-zague de `amp` de altura entre x0 e x1, centrado em y (coordenadas do documento)."""
    caminho = QPainterPath(QPointF(x0, y))
    x, alto = x0, True
    passo = amp * 2.0
    while x < x1:
        x = min(x + passo, x1)
        caminho.lineTo(x, y - amp if alto else y + amp)
        alto = not alto
    painter.drawPath(caminho)


def desenhar(painter, doc, recorte) -> None:
    """Sublinhado ondulado das palavras erradas dos blocos que cruzam o recorte. Coordenadas do
    documento, painter ja' transformado; so' a tela chama (a impressao e o PDF nao)."""
    est = getattr(doc, "_ortografia", None)
    if est is None or not est.pintando():
        return
    dl = doc.documentLayout()
    caneta = None
    try:
        if recorte is not None:
            bloco = doc.findBlock(dl.hitTest(QPointF(0, recorte.top()),
                                             Qt.HitTestAccuracy.FuzzyHit))
            bloco = bloco.previous() if bloco.previous().isValid() else bloco
        else:
            bloco = doc.firstBlock()
        while bloco.isValid():
            r = dl.blockBoundingRect(bloco)
            # Passou do recorte: acabou, salvo dentro de tabela (as celulas de uma linha vem uma
            # depois da outra na ordem do documento, e a seguinte volta ao topo da linha).
            if recorte is not None and r.top() > recorte.bottom() + 300:
                if QTextCursor(bloco).currentTable() is None:
                    break
            if bloco.isVisible() and (recorte is None or r.adjusted(-4000, -500, 4000, 500)
                                      .intersects(recorte)):
                erros = est.erros_a_pintar(bloco)
                if erros:
                    if caneta is None:
                        # So' prepara o painter quando ha' o que pintar: a faixa que a tecla
                        # repinta quase nunca tem palavra errada.
                        painter.save()
                        caneta = QPen(COR_ONDA)
                        caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                        caneta.setCapStyle(Qt.PenCapStyle.FlatCap)
                        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    _desenhar_bloco(painter, bloco, r, caneta, recorte, erros)
            bloco = bloco.next()
    except RuntimeError as erro:  # pintura nunca derruba a janela
        log.warning("ortografia nao pintada: %s", erro)
    finally:
        if caneta is not None:
            painter.restore()


def _x(linha, pos: int) -> float:
    r = linha.cursorToX(pos)
    return float(r[0] if isinstance(r, tuple) else r)


def _desenhar_bloco(painter, bloco, r, caneta: QPen, recorte, erros) -> None:
    lay = bloco.layout()
    if lay is None or lay.lineCount() == 0:
        return
    for i in range(lay.lineCount()):
        linha = lay.lineAt(i)
        topo = r.top() + linha.y()
        # So' as linhas que cruzam o recorte (a tecla repinta uma faixa): pintar a onda das
        # outras seria trabalho jogado fora pelo clip do painter.
        if recorte is not None and (topo > recorte.bottom()
                                    or topo + linha.height() < recorte.top()):
            continue
        la, lb = linha.textStart(), linha.textStart() + linha.textLength()
        amp = max(linha.height() * 0.06, 6.0)
        caneta.setWidthF(amp * 0.75)
        painter.setPen(caneta)
        y = topo + linha.ascent() + linha.descent() * 0.55
        for a, b in erros:
            if b <= la or a >= lb:
                continue
            x0, x1 = _x(linha, max(a, la)), _x(linha, min(b, lb))
            if x1 > x0 and (recorte is None or (r.left() + x1 >= recorte.left()
                                                and r.left() + x0 <= recorte.right())):
                _onda(painter, r.left() + x0, r.left() + x1, y, amp)
