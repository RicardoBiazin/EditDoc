"""Portugues do Brasil nos dialogos padrao do Qt (Salvar, Cancelar, Abrir...)."""

from __future__ import annotations

import gc

from ajudantes import checa, checa_igual, pular, preparar_qt, resumir, secao

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtCore import QLocale  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from editdoc import idioma  # noqa: E402


def testar_botoes() -> None:
    secao("botoes dos dialogos padrao saem em portugues")
    app = QApplication.instance()
    carregados = idioma.instalar(app)
    checa("qtbase_pt_BR" in carregados, f"o catalogo entra: {carregados}")
    checa_igual(QLocale().name(), "pt_BR", "locale padrao e' pt_BR")

    caixa = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save
        | QDialogButtonBox.StandardButton.Discard
        | QDialogButtonBox.StandardButton.Cancel
        | QDialogButtonBox.StandardButton.Open)
    textos = sorted(b.text().replace("&", "") for b in caixa.buttons())
    checa_igual(textos, ["Abrir", "Cancelar", "Descartar", "Salvar"],
                "Save, Discard, Cancel e Open saem em portugues")

    # Contraprova: o tradutor tem de continuar vivo. Guardado numa variavel
    # local, o coletor do Python o destroi e os textos voltam ao ingles.
    checa(bool(getattr(app, "_tradutores", None)),
          "a referencia do tradutor fica guardada na aplicacao")
    gc.collect()
    caixa2 = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    checa_igual(caixa2.buttons()[0].text().replace("&", ""), "Cancelar",
                "continua valendo depois de uma coleta de lixo")


def main() -> int:
    testar_botoes()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
