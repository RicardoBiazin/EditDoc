"""Gravacao periodica da copia de recuperacao de uma janela (M8).

O relogio grava a cada `intervalo` minutos, e tambem depois de
`recuperacao.ALTERACOES_PARA_GRAVAR` alteracoes (com uma pausa curta, para nao gravar
no meio de uma rajada de teclas). So' grava se o documento esta' alterado e mudou
desde a ultima copia: documento limpo nao tem o que recuperar.

Salvar apaga a copia; fechar normalmente apaga a copia e solta a trava. Uma queda
deixa a copia e a trava solta: e' isso que a proxima abertura oferece.

Quem monta o .docx e' a janela (`montar`): a copia e' o mesmo arquivo que o Salvar
gravaria, sem a conferencia (que e' cara e nao protege nada aqui: o original nao e'
tocado).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer

from editdoc import log_interno, recuperacao

log = log_interno.obter(__name__)

#: Pausa depois da enesima alteracao antes de gravar (ms).
PAUSA_APOS_ALTERACOES_MS = 1500


class GuardaRecuperacao(QObject):
    def __init__(self, montar: Callable[[], tuple[bytes, str | None, str, list]],
                 sujo: Callable[[], bool], intervalo_min: int = recuperacao.INTERVALO_PADRAO_MIN,
                 ligada: bool = True, pai: QObject | None = None,
                 sessao: recuperacao.Sessao | None = None) -> None:
        super().__init__(pai)
        self._montar = montar
        self._sujo = sujo
        self.sessao = sessao or recuperacao.Sessao()
        self._ligada = ligada
        #: Alteracoes desde a ultima copia (0 = a copia, se existe, esta' em dia).
        self.alteracoes = 0
        self._relogio = QTimer(self)
        self._relogio.timeout.connect(self.gravar_agora)
        self._pausa = QTimer(self)
        self._pausa.setSingleShot(True)
        self._pausa.setInterval(PAUSA_APOS_ALTERACOES_MS)
        self._pausa.timeout.connect(self.gravar_agora)
        self.definir(intervalo_min, ligada)

    # -- configuracao ---------------------------------------------------------------
    def definir(self, intervalo_min: int, ligada: bool) -> None:
        self._ligada = bool(ligada)
        self._relogio.setInterval(recuperacao.intervalo_valido(intervalo_min) * 60_000)
        if self._ligada:
            self._relogio.start()
        else:
            self._relogio.stop()
            self._pausa.stop()

    def intervalo_ms(self) -> int:
        return self._relogio.interval()

    def ligada(self) -> bool:
        return self._ligada

    # -- eventos do documento ---------------------------------------------------------
    def alterou(self) -> None:
        self.alteracoes += 1
        if (self._ligada and self.alteracoes >= recuperacao.ALTERACOES_PARA_GRAVAR
                and not self._pausa.isActive()):
            self._pausa.start()

    def gravar_agora(self) -> bool:
        """Grava a copia se ha' o que recuperar. True se gravou."""
        self._pausa.stop()
        if not self._ligada or self.alteracoes == 0 or not self._sujo():
            return False
        try:
            dados, original, nome, avisos = self._montar()
        except Exception as erro:  # noqa: BLE001 - a copia nunca derruba a edicao
            log.warning("copia de recuperacao nao montou: %s", erro)
            return False
        if self.sessao.gravar(dados, original, nome, avisos):
            self.alteracoes = 0
            return True
        return False

    def salvo(self) -> None:
        """O documento foi gravado no disco: a copia nao serve mais."""
        self.alteracoes = 0
        self._pausa.stop()
        self.sessao.descartar()

    def encerrar(self) -> None:
        """Fechamento normal da janela: apaga a copia e solta a trava."""
        self._relogio.stop()
        self._pausa.stop()
        self.sessao.encerrar()
