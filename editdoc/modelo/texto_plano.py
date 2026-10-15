"""Exportar como texto sem formatacao (M7). Sem Qt.

Um paragrafo por linha. Tabela: uma linha por linha da tabela, celulas separadas por
tabulacao (o que se cola numa planilha). Imagem e objeto opaco nao viram texto. Campo sai com o ultimo
resultado guardado, como o texto que ele mostra.

Notas (0.1.10): a referencia sai como o numero entre colchetes ("[1]"), e as notas vem no fim,
numeradas, depois do titulo "Notas de rodapé" (e "Notas de fim").

Listas (0.1.4): o item sai com o numero calculado como na tela ("1.1.", "a)", "•") e o
sufixo do nivel (tabulacao, espaco ou nada). O simbolo da fonte Symbol ou Wingdings sai como
o caractere Unicode parecido.

Alteracoes controladas (0.1.13): sai o texto final, como no Word: o excluido nao entra, e o
paragrafo cuja marca foi excluida continua na mesma linha do seguinte.
"""

from __future__ import annotations

from editdoc.modelo.documento import CARACTERE_OBJETO, Documento, MarcaNota, Paragrafo, Tabela
from editdoc.modelo.notas import numeros as numeros_das_notas
from editdoc.modelo.notas import referencias_do_corpo, texto_do_simbolo
from editdoc.modelo.numeracao import rotulos_do_documento, texto_visivel

#: Fim de linha do Windows: o Bloco de Notas antigo mostra tudo numa linha com LF puro.
FIM_DE_LINHA = "\r\n"


_SUFIXO = {"tab": "\t", "space": " ", "nothing": ""}


def _texto_do_run(r, numeros: dict | None) -> str:
    if r.exclusao is not None:
        return ""  # excluido (ou movido para outro lugar): o .txt leva o texto final
    m = r.marca
    if isinstance(m, MarcaNota) and not m.propria:
        if m.personalizada:
            return "[" + (texto_do_simbolo(m.simbolo) or "*") + "]"
        return "[" + (numeros or {}).get((m.tipo, m.id), "?") + "]"
    return "" if r.eh_objeto() else r.texto


def _texto_do_paragrafo(p: Paragrafo, rotulos: dict | None = None,
                        numeros: dict | None = None) -> str:
    texto = "".join(_texto_do_run(r, numeros) for r in p.runs)
    rotulo = (rotulos or {}).get(id(p))
    if rotulo is not None and not rotulo.nivel.oculto:
        texto = texto_visivel(rotulo.texto) + _SUFIXO.get(rotulo.nivel.sufixo, "\t") + texto
    # U+2028 (quebra de linha manual) vira quebra de linha; objeto solto nao vira nada.
    return texto.replace(" ", FIM_DE_LINHA).replace(CARACTERE_OBJETO, "")


def _linhas(blocos, rotulos: dict | None = None, numeros: dict | None = None) -> list[str]:
    saida: list[str] = []
    juntar = False  # a marca do paragrafo de cima foi excluida (0.1.13)
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            for linha in bloco.linhas:
                celulas = [" ".join(_linhas(c.blocos, rotulos, numeros)).replace("\t", " ")
                           for c in linha.celulas]
                saida.append("\t".join(celulas))
        else:
            texto = _texto_do_paragrafo(bloco, rotulos, numeros)
            if saida and juntar:
                saida[-1] += texto
            else:
                saida.append(texto)
            juntar = bloco.marca_exclusao is not None
            continue
        juntar = False
    return saida


def _notas(doc: Documento, numeros: dict) -> list[str]:
    """As notas no fim do texto, na ordem das referencias, com o numero."""
    cat = doc.notas
    if cat is None:
        return []
    saida: list[str] = []
    refs = [r.marca for _p, r in referencias_do_corpo(doc.paragrafos)]
    for tipo, titulo in (("rodape", "Notas de rodapé"), ("fim", "Notas de fim")):
        linhas = []
        vistos = set()
        for m in refs:
            if m.tipo != tipo or m.id in vistos:
                continue
            vistos.add(m.id)
            nota = cat.obter(tipo, m.id)
            if nota is None:
                continue
            marca = texto_do_simbolo(m.simbolo) if m.personalizada else numeros.get((tipo, m.id), "?")
            texto = _linhas(list(nota.paragrafos), None, numeros)
            primeira = texto[0].strip() if texto else ""
            linhas.append(f"[{marca}] {primeira}".rstrip())
            linhas.extend(texto[1:])
        if linhas:
            saida += ["", titulo] + linhas
    return saida


def texto_do_documento(doc: Documento, numeros: dict | None = None) -> str:
    """O corpo do documento como texto, com fim de linha do Windows. Notas (0.1.10) no fim;
    `numeros`: o numero de cada nota como a tela mostra (sem ele, a numeracao continua)."""
    if numeros is None and getattr(doc, "notas", None) is not None:
        cat = doc.notas
        numeros = numeros_das_notas([(r.marca.tipo, r.marca.id, r.marca.personalizada)
                                     for _p, r in referencias_do_corpo(doc.paragrafos)],
                                    {t: cat.propriedades(t) for t in ("rodape", "fim")})
    linhas = _linhas(doc.paragrafos, rotulos_do_documento(doc), numeros or {})
    linhas += _notas(doc, numeros or {})
    return FIM_DE_LINHA.join(linhas) + FIM_DE_LINHA
