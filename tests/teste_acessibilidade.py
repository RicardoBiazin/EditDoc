"""Acessibilidade (M8): nomes, ordem de Tab, teclado da faixa, documento e contraste.

A varredura passa por todos os controles interativos da janela (todas as abas, os
paineis, a barra de busca e a de aviso) e de cada dialogo do programa, e falha se algum
nao tiver nome que o leitor de tela consiga dizer. Os dialogos sao montados com o `exec`
trocado: o teste olha o dialogo pronto e responde "cancelar", sem modal na suite.
"""

from __future__ import annotations

from ajudantes import checa, checa_igual, drenar_eventos, preparar_qt, pular, resumir, secao

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QAccessible, QColor, QFont, QKeyEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QDialog,  # noqa: E402
                               QLineEdit, QMenu, QToolButton, QWidget)

from editdoc import configuracao  # noqa: E402
from editdoc.formato_docx.avisos import Aviso  # noqa: E402
from editdoc.interface import acessibilidade, dialogo_estilo, dialogos_modais  # noqa: E402
from editdoc.interface.dialogo_recuperacao import DialogoRecuperacao  # noqa: E402
from editdoc.interface.dicas_teclas import atribuir_codigos  # noqa: E402
from editdoc.interface.faixa import ABAS, BotaoAcao  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402
from editdoc.interface.vista_paginas import COR_ROTULO_FAIXA  # noqa: E402
from editdoc.modelo.estilos import catalogo_padrao  # noqa: E402
from editdoc.modelo.pagina import Pagina  # noqa: E402
from editdoc.recuperacao import Copia  # noqa: E402

Key = Qt.Key


def janela_pronta() -> JanelaPrincipal:
    janela = JanelaPrincipal(configuracao.padrao())
    janela.resize(1600, 900)
    janela.show()
    janela.activateWindow()
    QApplication.setActiveWindow(janela) if hasattr(QApplication, "setActiveWindow") else None
    janela.painel.setFocus()
    drenar_eventos()
    return janela


def fechar(janela) -> None:
    janela.painel.documento_corpo().setModified(False)
    janela.close()
    drenar_eventos()


def nomes_faltando(raiz: QWidget) -> list[str]:
    return [f"{type(w).__name__} {w.objectName() or ''} '{getattr(w, 'text', lambda: '')()}'"
            for w in acessibilidade.sem_nome(raiz)]


# -- contraste (WCAG 2.1) -----------------------------------------------------------------

def _luminancia(cor: QColor) -> float:
    def canal(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * canal(cor.red()) + 0.7152 * canal(cor.green()) + 0.0722 * canal(cor.blue())


def contraste(a: QColor, b: QColor) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# -- testes -------------------------------------------------------------------------------

def testar_varredura_da_janela() -> None:
    secao("varredura: todo controle interativo da janela tem nome legivel")
    falso = QToolButton()
    falso.setText("¶")
    sem = QLineEdit()
    caixa = QWidget()
    falso.setParent(caixa)
    sem.setParent(caixa)
    checa_igual(len(acessibilidade.sem_nome(caixa)), 2,
                "contraprova: botao so' com '¶' e campo sem nome sao acusados")
    falso.setAccessibleName("Marcas de formatação")
    sem.setAccessibleName("Texto")
    checa_igual(acessibilidade.sem_nome(caixa), [], "com nome, deixam de ser acusados")
    caixa.deleteLater()

    janela = janela_pronta()
    janela.barra_busca.mostrar(substituir=True)
    janela.barra_aviso.mostrar([Aviso("EQUACAO", "1 equação.", 1, True)])
    janela.dock_estilos.show()
    janela.dock_navegacao.show()
    janela.painel.entrar_na_faixa("cabecalho")
    drenar_eventos()
    for aba in ABAS:
        janela.faixa.abrir_aba(aba)
        drenar_eventos()
        faltam = nomes_faltando(janela)
        checa(not faltam, f"aba {aba}: nenhum controle sem nome" + (f" ({faltam[:5]})" if faltam else ""))
    janela.painel.sair_da_faixa()
    botoes = [b for b in janela.faixa.findChildren(BotaoAcao)]
    checa(len(botoes) > 40, f"a faixa tem os botoes de comando ({len(botoes)})")
    curtos = {b.text(): b.accessibleName() for b in botoes if b.text() in ("N", "I", "S", "¶", "A▲")}
    checa_igual(curtos.get("N"), "Negrito", "o botao 'N' se chama Negrito para o leitor de tela")
    checa_igual(curtos.get("¶"), "Mostrar marcas de formatação (¶, espaços e tabulações)",
                "o botao '¶' diz o que faz")
    checa(all(b.accessibleDescription() for b in botoes), "todo botao de comando tem descricao")
    miniaturas = janela.faixa.galeria._botoes
    checa(miniaturas and all(b.accessibleName().startswith("Estilo ") for b in miniaturas),
          "cada miniatura da galeria se chama 'Estilo <nome>'")
    checa_igual(janela.regua.accessibleName(), "Régua", "a regua tem nome")
    checa("centímetros" in janela.regua.accessibleDescription(), "e diz a unidade")
    checa_igual(janela._rotulo_pagina.accessibleName(), "Página atual",
                "o 'Página X de Y' da barra de status tem nome")
    janela.barra_aviso.fechar()
    janela.barra_busca.fechar()
    fechar(janela)


class Capturador:
    """Troca QDialog.exec: guarda o dialogo montado e responde Rejected."""

    def __init__(self) -> None:
        self.dialogos: list[QDialog] = []

    def __enter__(self):
        self._original = QDialog.exec
        capt = self

        def exec_falso(dialogo):
            dialogo.show()
            drenar_eventos(2)
            capt.dialogos.append(dialogo)
            capt.examinar(dialogo)
            dialogo.hide()
            return QDialog.DialogCode.Rejected

        QDialog.exec = exec_falso
        return self

    def __exit__(self, *_exc):
        QDialog.exec = self._original

    def examinar(self, dialogo: QDialog) -> None:
        titulo = dialogo.windowTitle()
        faltam = nomes_faltando(dialogo)
        checa(not faltam, f"dialogo '{titulo}': todos os controles tem nome"
              + (f" ({faltam[:5]})" if faltam else ""))
        ordem = ordem_de_tab(dialogo)
        checa(len(ordem) >= 2, f"dialogo '{titulo}': o Tab percorre os controles ({len(ordem)})")
        fora = ordem_fora_de_leitura(dialogo, ordem)
        checa(not fora, f"dialogo '{titulo}': a ordem de Tab segue a leitura"
              + (f" (fora: {fora[:3]})" if fora else ""))


def _focavel(w: QWidget, dialogo: QDialog) -> bool:
    if w is dialogo or w.window() is not dialogo:
        return False
    if isinstance(w.parentWidget(), (QComboBox, QAbstractSpinBox)):
        return False
    return (w.isVisible() and w.isEnabled() and bool(w.focusPolicy() & Qt.FocusPolicy.TabFocus)
            and w.focusProxy() is None)


def ordem_de_tab(dialogo: QDialog) -> list[QWidget]:
    vistos, ordem = set(), []
    w = dialogo.nextInFocusChain()
    while w is not None and w is not dialogo and id(w) not in vistos:
        vistos.add(id(w))
        if _focavel(w, dialogo):
            ordem.append(w)
        w = w.nextInFocusChain()
    return ordem


def ordem_fora_de_leitura(dialogo: QDialog, ordem: list[QWidget]) -> list[str]:
    """Pares consecutivos em que o Tab volta para cima, ou para a esquerda na mesma linha."""
    fora = []
    for a, b in zip(ordem, ordem[1:]):
        pa = a.mapTo(dialogo, QPoint(0, a.height() // 2))
        pb = b.mapTo(dialogo, QPoint(0, b.height() // 2))
        mesma_linha = abs(pa.y() - pb.y()) <= max(a.height(), b.height()) // 2
        if (mesma_linha and pb.x() < pa.x()) or (not mesma_linha and pb.y() < pa.y()):
            fora.append(f"{type(a).__name__}->{type(b).__name__}")
    return fora


def testar_dialogos() -> None:
    secao("dialogos: nomes e ordem de Tab de cada um")
    estilos = catalogo_padrao()
    with Capturador() as capt:
        dialogos_modais.pedir_tamanho_tabela(None)
        dialogos_modais.pedir_tamanho_imagem(None, 5.0, 3.0)
        dialogos_modais.pedir_margens(None, Pagina())
        dialogos_modais.pedir_numero_inicial(None, 3)
        dialogos_modais.pedir_opcoes_pdf(None, 4, 0)
        dialogos_modais.pedir_opcoes(None, configuracao.padrao())
        # 0.1.3: o dialogo de link (Ctrl+K). A contagem abaixo passou de oito para nove.
        dialogos_modais.pedir_link(None, "texto", None, ["Marcador1", "Marcador2"])
        dialogo_estilo.pedir_estilo(None, estilos.obter("Normal"), estilos, QFont("Arial", 11))
        dialogo_estilo.pedir_estilo(None, estilos.obter("Normal"), estilos, QFont("Arial", 11),
                                    novo=True)
    checa_igual(len(capt.dialogos), 9, "os nove dialogos do programa foram examinados")
    for d in capt.dialogos:
        d.deleteLater()
    copia = Copia(id="0" * 32, docx=None, meta={"nome": "a.docx", "hora": "2026-10-12T10:00:00+00:00"})
    rec = DialogoRecuperacao([copia], {"abrir": lambda c: False, "salvar_como": lambda c: False,
                                       "descartar": lambda c: False})
    rec.show()
    drenar_eventos(2)
    capt.examinar(rec)
    checa_igual(ordem_de_tab(rec)[0], rec.lista, "o Tab comeca na lista de copias")
    rec.close()
    rec.deleteLater()
    drenar_eventos()


def _tecla(tecla, mods=Qt.KeyboardModifier.NoModifier, texto: str = "") -> None:
    alvo = QApplication.focusWidget()
    QTest.keyClick(alvo, tecla, mods) if not texto else \
        QApplication.sendEvent(alvo, QKeyEvent(QKeyEvent.Type.KeyPress, tecla, mods, texto))


def _letra(letra: str) -> None:
    alvo = QApplication.focusWidget()
    tecla = getattr(Key, f"Key_{letra.upper()}") if letra.isalpha() else getattr(Key, f"Key_{letra}")
    QApplication.sendEvent(alvo, QKeyEvent(QKeyEvent.Type.KeyPress, tecla,
                                           Qt.KeyboardModifier.NoModifier, letra))


def _alt_sozinho() -> None:
    alvo = QApplication.focusWidget()
    QApplication.sendEvent(alvo, QKeyEvent(QKeyEvent.Type.KeyPress, Key.Key_Alt,
                                           Qt.KeyboardModifier.AltModifier))
    QApplication.sendEvent(QApplication.focusWidget(),
                           QKeyEvent(QKeyEvent.Type.KeyRelease, Key.Key_Alt,
                                     Qt.KeyboardModifier.NoModifier))


def testar_teclado_da_faixa() -> None:
    secao("teclado: F10 e Alt levam a faixa; setas, Enter, dicas de tecla e Esc")
    janela = janela_pronta()
    teclado = janela.teclado_faixa
    barra = janela.faixa._abas
    checa(janela.painel.hasFocus(), "o foco comeca no documento")
    QTest.keyClick(janela.painel, Key.Key_F10)
    checa(barra.hasFocus() and teclado.ativo, "F10 leva o foco as abas da faixa")
    # 0.1.6: a aba Revisao (comentarios) entrou, com a letra R do Word.
    checa_igual(sorted(teclado.dicas_visiveis()), sorted(["A", "1", "2", "P", "N", "L", "R", "E"]),
                "as dicas das abas e do topo aparecem")
    _tecla(Key.Key_Right)
    checa_igual(janela.faixa.aba_atual(), "Inserir", "seta para a direita troca de aba")
    _tecla(Key.Key_Left)
    checa_igual(janela.faixa.aba_atual(), "Página Inicial", "seta para a esquerda volta")
    _tecla(Key.Key_Down)
    primeiro = QApplication.focusWidget()
    checa(primeiro is teclado.focaveis()[0], "seta para baixo entra no primeiro botao")
    _tecla(Key.Key_Right)
    checa(QApplication.focusWidget() is teclado.focaveis()[1], "seta para a direita anda nos botoes")
    _tecla(Key.Key_Left)
    _tecla(Key.Key_Up)
    checa(barra.hasFocus(), "seta para cima, da primeira linha, volta as abas")
    _tecla(Key.Key_Escape)
    checa(janela.painel.hasFocus() and not teclado.ativo, "Esc devolve o foco ao documento")

    _alt_sozinho()
    checa(barra.hasFocus() and teclado.ativo, "Alt sozinho tambem leva a faixa")
    _letra("N")
    checa_igual(janela.faixa.aba_atual(), "Inserir", "a letra N abre a aba Inserir")
    dicas = teclado.dicas_visiveis()
    checa(len(dicas) >= 5, f"e mostra as dicas dos botoes da aba ({len(dicas)})")
    codigo_quebra = next((c for c, w in dicas.items()
                          if acessibilidade.nome_acessivel(w) == "Quebra de página"), None)
    checa(codigo_quebra is not None, "o botao Quebra tem uma dica")
    paginas = janela.painel.total_de_paginas()
    for letra in codigo_quebra or "":
        _letra(letra)
    drenar_eventos()
    checa_igual(janela.painel.total_de_paginas(), paginas + 1,
                "a dica do botao executa o comando (quebra de pagina)")
    checa(janela.painel.hasFocus() and not teclado.ativo, "e o foco volta ao documento")

    QTest.keyClick(janela.painel, Key.Key_F10)
    _tecla(Key.Key_Escape)
    _alt_sozinho()
    _letra("P")
    _tecla(Key.Key_Escape)
    checa(barra.hasFocus() and teclado.dicas_visiveis().get("P") is not None,
          "Esc nos botoes volta as dicas das abas")
    _tecla(Key.Key_Escape)
    checa(janela.painel.hasFocus(), "outro Esc volta ao documento")

    QTest.keyClick(janela.painel, Key.Key_F10)
    _tecla(Key.Key_Down)
    botao = QApplication.focusWidget()
    nome = acessibilidade.nome_acessivel(botao)
    checa(isinstance(botao, QToolButton), f"o primeiro da Pagina Inicial e' um botao ({nome})")
    _tecla(Key.Key_Escape)

    # AltGr (Ctrl+Alt) nao abre as dicas: no ABNT2 ele digita.
    alvo = janela.painel
    QApplication.sendEvent(alvo, QKeyEvent(QKeyEvent.Type.KeyPress, Key.Key_Alt,
                                           Qt.KeyboardModifier.AltModifier
                                           | Qt.KeyboardModifier.ControlModifier))
    QApplication.sendEvent(alvo, QKeyEvent(QKeyEvent.Type.KeyRelease, Key.Key_Alt,
                                           Qt.KeyboardModifier.ControlModifier))
    checa(not teclado.ativo and janela.painel.hasFocus(), "AltGr nao leva a faixa")
    QApplication.sendEvent(alvo, QKeyEvent(QKeyEvent.Type.KeyPress, Key.Key_Alt,
                                           Qt.KeyboardModifier.AltModifier))
    QTest.keyClick(alvo, Key.Key_Z, Qt.KeyboardModifier.AltModifier)
    QApplication.sendEvent(alvo, QKeyEvent(QKeyEvent.Type.KeyRelease, Key.Key_Alt,
                                           Qt.KeyboardModifier.NoModifier))
    checa(not teclado.ativo, "Alt com outra tecla no meio nao leva a faixa")
    antes = janela.painel.toPlainText()
    QTest.keyClick(janela.painel, Key.Key_Tab)
    checa_igual(janela.painel.toPlainText(), antes + "\t",
                "Tab no documento continua sendo tabulacao (o foco nao sai)")
    checa(janela.painel.hasFocus(), "e o foco continua no documento")

    janela.dock_navegacao.show()
    drenar_eventos()
    QTest.keyClick(janela.painel, Key.Key_F6)
    checa(barra.hasFocus(), "F6 do documento vai para a faixa")
    _tecla(Key.Key_F6)
    checa(janela.navegacao.arvore.hasFocus(), "F6 de novo vai para o painel de navegacao aberto")
    _tecla(Key.Key_F6, Qt.KeyboardModifier.ShiftModifier)
    checa(barra.hasFocus(), "Shift+F6 volta para a faixa")
    for _ in range(len(teclado.regioes()) - 1):
        _tecla(Key.Key_F6)
    checa(janela.painel.hasFocus(), "o F6 da' a volta e chega ao documento")
    janela.dock_navegacao.hide()
    fechar(janela)


def testar_codigos() -> None:
    secao("dicas de tecla: codigos unicos, sem acento")
    codigos = atribuir_codigos(["Negrito", "Numeração", "Itálico", "Ímpar", "N", "", "Novo"],
                               usados={"A"})
    checa_igual(len(set(codigos)), len(codigos), "nenhum codigo repetido")
    checa_igual(codigos[:2], ["N", "U"], "a primeira letra livre do nome")
    checa(all(c.isascii() and c == c.upper() for c in codigos), "maiusculas sem acento")
    checa("A" not in codigos, "nao repete o que ja' esta' em uso no nivel")


def testar_documento_acessivel() -> None:
    secao("documento: texto editavel com nome, pagina e o paragrafo do cursor")
    janela = janela_pronta()
    interface = QAccessible.queryAccessibleInterface(janela.painel)
    checa(interface is not None and interface.isValid(), "o painel tem interface acessivel")
    checa_igual(interface.role(), QAccessible.Role.EditableText, "papel: texto editavel")
    checa_igual(interface.text(QAccessible.Text.Name), "Documento: Documento em branco",
                "nome: Documento e o nome do arquivo")
    checa_igual(interface.text(QAccessible.Text.Description), "Página 1 de 1",
                "descricao: a pagina do cursor")
    janela.painel.insertPlainText("Primeiro parágrafo")
    checa_igual(interface.text(QAccessible.Text.Value), "Primeiro parágrafo",
                "valor: o texto do paragrafo do cursor")
    QTest.keyClick(janela.painel, Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    janela.painel.insertPlainText("Segunda página")
    drenar_eventos()
    checa_igual(interface.text(QAccessible.Text.Description), "Página 2 de 2",
                "a descricao acompanha a pagina")
    checa_igual(janela.painel.property("editdoc_ultimo_anuncio"), "Página 2 de 2",
                "trocar de pagina anuncia 'Página 2 de 2'")
    checa_igual(interface.text(QAccessible.Text.Value), "Segunda página", "e o paragrafo novo")
    janela.painel.entrar_na_faixa("cabecalho")
    checa(interface.text(QAccessible.Text.Description).startswith("Editando o cabeçalho"),
          "na edicao do cabecalho a descricao avisa")
    janela.painel.sair_da_faixa()
    fechar(janela)


def testar_contraste() -> None:
    secao("contraste: texto da interface com 4,5 para 1 ou mais")
    janela = janela_pronta()
    paleta = janela.palette()
    fundo = paleta.window().color()
    texto = paleta.windowText().color()
    titulo = janela.faixa._pagina_inicial.grupos[0]._titulo
    cor_titulo = titulo.palette().windowText().color()
    checa(contraste(cor_titulo, fundo) >= 4.5,
          f"titulo dos grupos da faixa: {contraste(cor_titulo, fundo):.1f}:1")
    checa(contraste(paleta.mid().color(), fundo) < 4.5,
          f"contraprova: o cinza 'mid' de antes nao passa ({contraste(paleta.mid().color(), fundo):.1f}:1)")
    checa(contraste(texto, fundo) >= 4.5, "texto da janela sobre o fundo")
    checa(contraste(QColor(0, 0, 0), QColor("#fff8d0")) >= 4.5, "dica de tecla")
    checa(contraste(QColor(0, 0, 0), QColor("#fff3c4")) >= 4.5, "barra de aviso")
    checa(contraste(COR_ROTULO_FAIXA, QColor(255, 255, 255)) >= 4.5,
          "rotulo da edicao do cabecalho sobre a folha")
    fechar(janela)

    # Tema escuro: a paleta da texto claro. A barra de aviso tem fundo amarelo
    # fixo, entao o rotulo e os botoes tem de ignorar a paleta (bug relatado em
    # 13/10/2026: o aviso ficava ilegivel, branco sobre amarelo).
    from PySide6.QtGui import QPalette
    app = QApplication.instance()
    paleta_antes = app.palette()
    escura = QPalette(paleta_antes)
    for papel, cor in ((QPalette.ColorRole.Window, "#202020"),
                       (QPalette.ColorRole.WindowText, "#f0f0f0"),
                       (QPalette.ColorRole.Text, "#f0f0f0"),
                       (QPalette.ColorRole.Button, "#2d2d2d"),
                       (QPalette.ColorRole.ButtonText, "#f0f0f0")):
        escura.setColor(papel, QColor(cor))
    app.setPalette(escura)
    try:
        janela = janela_pronta()
        barra = janela.barra_aviso
        barra.mostrar([Aviso("EQUACAO", "1 equação.", 1, True)])
        drenar_eventos()
        amarelo = QColor("#fff3c4")
        cor_rotulo = barra._rotulo.palette().color(barra._rotulo.foregroundRole())
        checa(contraste(cor_rotulo, amarelo) >= 4.5,
              f"tema escuro: texto da barra de aviso legivel ({contraste(cor_rotulo, amarelo):.1f}:1)")
        for botao in (barra._detalhes, barra._fechar):
            cor = botao.palette().color(botao.foregroundRole())
            fundo_botao = QColor("#fffaf0")
            checa(contraste(cor, fundo_botao) >= 4.5,
                  f"tema escuro: botao '{botao.text()}' da barra legivel ({contraste(cor, fundo_botao):.1f}:1)")
        checa(contraste(QColor("#f0f0f0"), amarelo) < 4.5,
              "contraprova: o texto claro da paleta escura sobre o amarelo nao passa")
        fechar(janela)
    finally:
        app.setPalette(paleta_antes)


def _acoes_de_menu(menu: QMenu, saida: set) -> None:
    for acao in menu.actions():
        saida.add(acao)
        if acao.menu() is not None:
            _acoes_de_menu(acao.menu(), saida)


def testar_tudo_pelo_teclado() -> None:
    secao("sem mouse: todo comando tem atalho ou esta' num botao ou menu alcancavel")
    janela = janela_pronta()
    alcancadas: set = set()
    for botao in janela.findChildren(BotaoAcao):
        if botao.focusPolicy() & Qt.FocusPolicy.TabFocus:
            alcancadas.add(botao._acao)
    for botao in janela.faixa.findChildren(QToolButton):
        if botao.menu() is not None and botao.focusPolicy() & Qt.FocusPolicy.TabFocus:
            _acoes_de_menu(botao.menu(), alcancadas)
    _acoes_de_menu(janela.botao_arquivo.menu(), alcancadas)
    galeria = janela.faixa.galeria
    if galeria._mais.focusPolicy() & Qt.FocusPolicy.TabFocus:
        # A seta "Mais estilos" da galeria abre o menu com todos os estilos e os comandos.
        _acoes_de_menu(galeria.menu_tudo(), alcancadas)
    sem = [a.text() for a in janela.comandos.todas()
           if a not in alcancadas and not a.shortcuts()]
    checa(not sem, "todo comando e' alcancado pelo teclado" + (f" (faltam: {sem})" if sem else ""))
    fechar(janela)


def main() -> int:
    testar_varredura_da_janela()
    testar_dialogos()
    testar_codigos()
    testar_teclado_da_faixa()
    testar_documento_acessivel()
    testar_contraste()
    testar_tudo_pelo_teclado()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
