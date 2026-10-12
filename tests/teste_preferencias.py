"""Preferencias (M8, Arquivo > Opções): validacao, gravacao, dialogo e efeito nas janelas.

O config e' o do %APPDATA% isolado pela suite (`preparar_qt`): nada vai para o do usuario.
"""

from __future__ import annotations

import contextlib
import json
import os

from ajudantes import (checa, checa_igual, drenar_eventos, pasta_temporaria, preparar_qt, pular,
                       resumir, secao)

if not preparar_qt():
    raise SystemExit(pular("PySide6 nao esta instalado neste venv"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from editdoc import configuracao  # noqa: E402
from editdoc.interface import dialogos_modais, tema  # noqa: E402
from editdoc.interface.dialogo_opcoes import DialogoOpcoes  # noqa: E402
from editdoc.interface.gerente import GerenteDeJanelas  # noqa: E402
from editdoc.interface.janela_principal import JanelaPrincipal  # noqa: E402


@contextlib.contextmanager
def dialogos(**substitutos):
    originais = {nome: getattr(dialogos_modais, nome) for nome in substitutos}
    for nome, funcao in substitutos.items():
        setattr(dialogos_modais, nome, funcao)
    try:
        yield
    finally:
        for nome, funcao in originais.items():
            setattr(dialogos_modais, nome, funcao)


def limpar_config() -> None:
    configuracao.caminho().unlink(missing_ok=True)


def fechar(janela) -> None:
    janela.painel.documento_corpo().setModified(False)
    janela.close()
    drenar_eventos()


def testar_isolamento() -> None:
    secao("isolamento: o config dos testes nao e' o do usuario")
    checa(str(configuracao.caminho()).startswith(os.environ["APPDATA"])
          and "editdoc-appdata-suite-" in str(configuracao.caminho()),
          "config.json fica no %APPDATA% descartavel da suite")


def testar_validacao() -> None:
    secao("validacao: tipo e faixa; fora disso, o padrao")
    padrao = configuracao.padrao()
    for chave, esperado in (("papel_padrao", "A4"), ("unidade_regua", "cm"),
                            ("recuperacao_ligada", True), ("recuperacao_minutos", 10),
                            ("abrir_pdf_depois", False), ("recentes_maximo", 15),
                            ("tema", "sistema"), ("fonte_padrao", "Calibri"),
                            ("tamanho_padrao", 11)):
        checa_igual(padrao[chave], esperado, f"padrao seguro de {chave}")
    ruins = {"tamanho_padrao": 0, "papel_padrao": "A9", "recuperacao_minutos": 0,
             "recentes_maximo": 99, "tema": "roxo", "fonte_padrao": "   ",
             "unidade_regua": "furlong", "recuperacao_ligada": "sim", "janela_largura": 5}
    validado = configuracao.validar(ruins)
    for chave in ruins:
        checa_igual(validado[chave], padrao[chave], f"{chave} invalido volta ao padrao")
    bons = {"tamanho_padrao": 10.5, "papel_padrao": "Carta", "recuperacao_minutos": 3,
            "recentes_maximo": 0, "tema": "escuro", "fonte_padrao": "Arial",
            "unidade_regua": "pol", "recuperacao_ligada": False, "abrir_pdf_depois": True}
    validado = configuracao.validar(bons)
    for chave, valor in bons.items():
        checa_igual(validado[chave], valor, f"contraprova: {chave} valido e' aceito")
    checa_igual(configuracao.validar({"tamanho_padrao": 12.0})["tamanho_padrao"], 12,
                "12.0 vira o inteiro 12")
    checa_igual(configuracao.validar({"tamanho_padrao": True})["tamanho_padrao"], 11,
                "bool nao conta como numero")

    limpar_config()
    configuracao.caminho().write_text(json.dumps({"papel_padrao": "Ofício", "tema": 3}),
                                      encoding="utf-8")
    lido = configuracao.carregar()
    checa_igual((lido["papel_padrao"], lido["tema"]), ("Ofício", "sistema"),
                "carregar valida o arquivo: o bom fica, o ruim volta ao padrao")
    limpar_config()


def testar_recentes(tmp) -> None:
    secao("recentes: quantidade da preferencia e limpar a lista")
    limpar_config()
    arquivos = []
    for i in range(6):
        caminho = tmp / f"r{i}.docx"
        caminho.write_bytes(b"x")
        arquivos.append(str(caminho))
        configuracao.registrar_recente(str(caminho))
    checa_igual(len(configuracao.recentes()), 6, "com o padrao (15), os seis ficam")
    configuracao.gravar_preferencias({"recentes_maximo": 3})
    checa_igual(configuracao.recentes(), list(reversed(arquivos))[:3],
                "com 3, ficam os tres mais novos")
    configuracao.registrar_recente(arquivos[0])
    checa_igual(len(configuracao.recentes()), 3, "registrar mais um nao passa de 3")
    configuracao.gravar_preferencias({"recentes_maximo": 0})
    configuracao.registrar_recente(arquivos[1])
    checa_igual(configuracao.recentes(), [], "com 0, a lista fica vazia")
    configuracao.gravar_preferencias({"recentes_maximo": 15})
    for caminho in arquivos:
        configuracao.registrar_recente(caminho)
    checa(configuracao.recentes(), "contraprova: de volta a 15, a lista enche")
    configuracao.gravar_preferencias({"tema": "claro"})
    checa_igual(len(configuracao.recentes()), 6, "gravar preferencias nao mexe nos recentes")
    configuracao.limpar_recentes()
    checa_igual(configuracao.recentes(), [], "limpar apaga a lista")
    checa_igual(configuracao.carregar()["tema"], "claro", "e mantem as preferencias")
    limpar_config()


def testar_dialogo() -> None:
    secao("dialogo Opções: mostra o config e devolve o que mudou")
    valores = configuracao.padrao()
    valores.update({"papel_padrao": "Carta", "unidade_regua": "pol", "recuperacao_minutos": 5,
                    "abrir_pdf_depois": True, "recentes_maximo": 7, "tema": "escuro"})
    dialogo = DialogoOpcoes(valores)
    devolvido = dialogo.valores()
    for chave in ("papel_padrao", "unidade_regua", "recuperacao_minutos", "abrir_pdf_depois",
                  "recentes_maximo", "tema", "fonte_padrao", "tamanho_padrao"):
        checa_igual(devolvido[chave], valores[chave], f"o dialogo mostra {chave} do config")
    checa(not devolvido["limpar_recentes"], "limpar a lista comeca desligado")
    dialogo.papel.setCurrentText("A4")
    dialogo.tamanho.setValue(12.5)
    dialogo.recuperacao.setChecked(False)
    checa(not dialogo.minutos.isEnabled(), "desligar a recuperacao desabilita o intervalo")
    dialogo.botao_limpar.click()
    dialogo.escolher_fonte("Arial")
    devolvido = dialogo.valores()
    checa_igual((devolvido["papel_padrao"], devolvido["tamanho_padrao"],
                 devolvido["recuperacao_ligada"], devolvido["limpar_recentes"],
                 devolvido["fonte_padrao"]), ("A4", 12.5, False, True, "Arial"),
                "o que o usuario mexe volta no dicionario")
    sem_mexer = DialogoOpcoes({**configuracao.padrao(), "fonte_padrao": "FonteQueNaoExiste"})
    checa_igual(sem_mexer.valores()["fonte_padrao"], "FonteQueNaoExiste",
                "sem mexer no combo, a fonte do config fica (o offscreen mostra outra)")
    dialogo.deleteLater()
    sem_mexer.deleteLater()


def testar_janela_e_gerente() -> None:
    secao("janela: Opções grava e aplica; documento novo usa fonte e papel")
    limpar_config()
    gerente = GerenteDeJanelas(configuracao.carregar())
    janela = gerente.novo()
    checa_igual(janela.painel.configuracao_pagina().nome_do_papel(), "A4", "documento novo em A4")
    novas = {**configuracao.padrao(), "papel_padrao": "Carta", "unidade_regua": "pol",
             "recuperacao_minutos": 2, "abrir_pdf_depois": True, "fonte_padrao": "Arial",
             "tamanho_padrao": 14, "tema": "escuro", "limpar_recentes": False}
    with dialogos(pedir_opcoes=lambda _p, _v: dict(novas)):
        checa(janela.opcoes(), "Arquivo > Opções confirmado grava")
    gravado = configuracao.carregar()
    checa_igual((gravado["papel_padrao"], gravado["unidade_regua"], gravado["tema"]),
                ("Carta", "pol", "escuro"), "as preferencias estao no config.json")
    checa_igual(janela.regua.unidade(), "pol", "a regua da janela aberta muda de unidade")
    checa_igual(janela.recuperacao.intervalo_ms(), 2 * 60_000,
                "o intervalo da recuperacao da janela aberta muda")
    checa(janela._abrir_pdf, "abrir o PDF depois de exportar passa a ser o padrao")
    checa_igual(janela.painel.configuracao_pagina().nome_do_papel(), "A4",
                "o documento aberto nao muda de papel")
    checa(not janela.sujo(), "nem fica alterado")
    checa_igual(QApplication.instance().property("editdoc_tema"), "escuro", "o tema e' aplicado")
    outra = gerente.novo()
    checa_igual(outra.painel.configuracao_pagina().nome_do_papel(), "Carta",
                "o documento novo seguinte nasce em Carta")
    fonte = outra.painel.documento_corpo().defaultFont()
    checa_igual((fonte.family(), fonte.pointSizeF()), ("Arial", 14.0),
                "e com a fonte e o tamanho da preferencia")
    checa(not outra.sujo(), "o documento novo em Carta nasce limpo")
    checa_igual(outra.regua.unidade(), "pol", "a janela nova ja' nasce com a regua em polegadas")

    capturado = []
    with dialogos(pedir_opcoes_pdf=lambda _p, _t, _a, abrir=False: capturado.append(abrir)):
        outra.exportar_pdf()
    checa_igual(capturado, [True], "Exportar PDF ja' vem com 'abrir depois' marcado")

    with dialogos(pedir_opcoes=lambda *_a: None):
        checa(not janela.opcoes(), "cancelar o dialogo nao grava nada")
    checa_igual(configuracao.carregar()["papel_padrao"], "Carta", "contraprova: ficou o de antes")

    with dialogos(pedir_opcoes=lambda *_a: {**novas, "limpar_recentes": True}):
        configuracao.registrar_recente(__file__)
        janela.opcoes()
    janela.botao_arquivo._montar_recentes()
    checa_igual([a.text() for a in janela.botao_arquivo.menu_recentes().actions()], ["(nenhum)"],
                "Limpar a lista esvazia o menu Abrir recente")
    for j in gerente.janelas():
        fechar(j)
    tema.aplicar("sistema")
    limpar_config()


def testar_tema() -> None:
    secao("tema: claro, escuro, sistema; nome estranho vira sistema")
    for nome in ("claro", "escuro", "sistema"):
        checa_igual(tema.aplicar(nome), nome, f"tema {nome} aplicado")
    checa_igual(tema.aplicar("neon"), "sistema", "tema desconhecido vira o do sistema")


def testar_menu_arquivo() -> None:
    secao("menu Arquivo: Opções e Recuperar documentos")
    janela = JanelaPrincipal(configuracao.padrao())
    textos = [a.text() for a in janela.botao_arquivo.menu().actions()]
    checa("Opções..." in textos, "Arquivo tem Opções...")
    checa("Recuperar documentos..." in textos, "Arquivo tem Recuperar documentos...")
    fechar(janela)


def main() -> int:
    testar_isolamento()
    testar_validacao()
    with pasta_temporaria() as tmp:
        testar_recentes(tmp)
    testar_dialogo()
    testar_janela_e_gerente()
    testar_tema()
    testar_menu_arquivo()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
