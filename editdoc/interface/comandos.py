"""Registro de comandos: cada acao da faixa, do atalho e do menu e' um QAction daqui.

Regra do CLAUDE.md: nenhum botao tem logica propria. A faixa referencia a acao
criada aqui, e o atalho vem da mesma definicao. Por isso um atalho e um botao
nunca divergem.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QTextListFormat
from PySide6.QtWidgets import QTextEdit

from editdoc.edicao import formatacao
from editdoc.modelo.unidades import RECUO_PADRAO_PX


@dataclass(frozen=True)
class Definicao:
    id: str
    texto: str
    atalhos: tuple[str, ...] = ()
    marcavel: bool = False
    dica: str = ""


DEFINICOES = (
    Definicao("desfazer", "Desfazer", ("Ctrl+Z",), dica="Desfazer"),
    Definicao("refazer", "Refazer", ("Ctrl+Y", "Ctrl+Shift+Z"), dica="Refazer"),
    Definicao("recortar", "Recortar", ("Ctrl+X",), dica="Recortar"),
    Definicao("copiar", "Copiar", ("Ctrl+C",), dica="Copiar"),
    Definicao("colar", "Colar", ("Ctrl+V",), dica="Colar"),
    Definicao("selecionar_tudo", "Selecionar tudo", ("Ctrl+A",), dica="Selecionar tudo"),
    Definicao("localizar", "Localizar", ("Ctrl+F",), dica="Localizar"),
    Definicao("substituir", "Substituir", ("Ctrl+H",), dica="Substituir"),
    Definicao("negrito", "N", ("Ctrl+B",), True, "Negrito"),
    Definicao("italico", "I", ("Ctrl+I",), True, "Itálico"),
    Definicao("sublinhado", "S", ("Ctrl+U",), True, "Sublinhado"),
    Definicao("tachado", "Tachado", (), True, "Tachado"),
    Definicao("subscrito", "X₂", ("Ctrl+=",), True, "Subscrito"),
    Definicao("sobrescrito", "X²", ("Ctrl+Shift+=",), True, "Sobrescrito"),
    Definicao("aumentar_fonte", "A▲", ("Ctrl+]",), dica="Aumentar fonte"),
    Definicao("diminuir_fonte", "A▼", ("Ctrl+[",), dica="Diminuir fonte"),
    Definicao("limpar_formatacao", "Limpar formatação", ("Ctrl+Space",),
              dica="Limpar formatação"),
    Definicao("marcadores", "Marcadores", ("Ctrl+Shift+L",), True, "Marcadores"),
    Definicao("numeracao", "Numeração", (), True, "Numeração"),
    Definicao("diminuir_recuo", "Diminuir recuo", ("Ctrl+Shift+M",),
              dica="Diminuir recuo"),
    Definicao("aumentar_recuo", "Aumentar recuo", ("Ctrl+M",), dica="Aumentar recuo"),
    Definicao("alinhar_esquerda", "Esquerda", ("Ctrl+L",), True, "Alinhar à esquerda"),
    Definicao("centralizar", "Centro", ("Ctrl+E",), True, "Centralizar"),
    Definicao("alinhar_direita", "Direita", ("Ctrl+R",), True, "Alinhar à direita"),
    Definicao("justificar", "Justificado", ("Ctrl+J",), True, "Justificar"),
    Definicao("espaco_1", "1,0", ("Ctrl+1",), True, "Espaçamento 1,0"),
    Definicao("espaco_115", "1,15", (), True, "Espaçamento 1,15"),
    Definicao("espaco_15", "1,5", ("Ctrl+5",), True, "Espaçamento 1,5"),
    Definicao("espaco_2", "2,0", ("Ctrl+2",), True, "Espaçamento 2,0"),
)

ALINHAMENTOS = {
    "alinhar_esquerda": Qt.AlignmentFlag.AlignLeft,
    "centralizar": Qt.AlignmentFlag.AlignHCenter,
    "alinhar_direita": Qt.AlignmentFlag.AlignRight,
    "justificar": Qt.AlignmentFlag.AlignJustify,
}

ESPACAMENTOS = {"espaco_1": 100, "espaco_115": 115, "espaco_15": 150, "espaco_2": 200}


def _executores(editor: QTextEdit, ao_localizar: Callable[[], None],
                ao_substituir: Callable[[], None]) -> dict[str, Callable[[], None]]:
    fmt = formatacao
    executores: dict[str, Callable[[], None]] = {
        "desfazer": editor.undo,
        "refazer": editor.redo,
        "recortar": editor.cut,
        "copiar": editor.copy,
        "colar": editor.paste,
        "selecionar_tudo": editor.selectAll,
        "localizar": ao_localizar,
        "substituir": ao_substituir,
        "negrito": lambda: fmt.alternar_negrito(editor),
        "italico": lambda: fmt.alternar_italico(editor),
        "sublinhado": lambda: fmt.alternar_sublinhado(editor),
        "tachado": lambda: fmt.alternar_tachado(editor),
        "subscrito": lambda: fmt.alternar_subscrito(editor),
        "sobrescrito": lambda: fmt.alternar_sobrescrito(editor),
        "aumentar_fonte": lambda: fmt.alterar_tamanho(editor, 1),
        "diminuir_fonte": lambda: fmt.alterar_tamanho(editor, -1),
        "limpar_formatacao": lambda: fmt.limpar_formatacao(editor),
        "marcadores": lambda: fmt.alternar_lista(editor, QTextListFormat.Style.ListDisc),
        "numeracao": lambda: fmt.alternar_lista(editor, QTextListFormat.Style.ListDecimal),
        "diminuir_recuo": lambda: fmt.alterar_recuo(editor, -RECUO_PADRAO_PX),
        "aumentar_recuo": lambda: fmt.alterar_recuo(editor, RECUO_PADRAO_PX),
    }
    for id_, alinhamento in ALINHAMENTOS.items():
        executores[id_] = lambda a=alinhamento: fmt.alinhar(editor, a)
    for id_, percentual in ESPACAMENTOS.items():
        executores[id_] = lambda p=percentual: fmt.definir_espacamento(editor, p)
    return executores


class Comandos(QObject):
    """Cria um QAction por definicao e liga cada um ao executor certo."""

    def __init__(self, pai: QObject, editor: QTextEdit,
                 ao_localizar: Callable[[], None],
                 ao_substituir: Callable[[], None]) -> None:
        super().__init__(pai)
        self._acoes: dict[str, QAction] = {}
        self._executores = _executores(editor, ao_localizar, ao_substituir)
        self._grupo_alinhamento = QActionGroup(self)
        self._grupo_alinhamento.setExclusive(True)
        self._grupo_espacamento = QActionGroup(self)
        self._grupo_espacamento.setExclusive(True)

        for definicao in DEFINICOES:
            acao = QAction(definicao.texto, self)
            dica = definicao.dica or definicao.texto
            if definicao.atalhos:
                acao.setShortcuts([QKeySequence(s) for s in definicao.atalhos])
                dica = f"{dica} ({definicao.atalhos[0]})"
            acao.setToolTip(dica)
            acao.setStatusTip(dica)
            acao.setCheckable(definicao.marcavel)
            acao.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            acao.triggered.connect(lambda _=False, i=definicao.id: self._executar(i))
            self._acoes[definicao.id] = acao
            if definicao.id in ALINHAMENTOS:
                self._grupo_alinhamento.addAction(acao)
            if definicao.id in ESPACAMENTOS:
                self._grupo_espacamento.addAction(acao)

    def _executar(self, id_: str) -> None:
        self._executores[id_]()

    def acao(self, id_: str) -> QAction:
        return self._acoes[id_]

    def todas(self) -> list[QAction]:
        return list(self._acoes.values())
