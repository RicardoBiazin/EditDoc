"""Conferencia do arquivo gravado, antes da troca atomica. Sem Qt.

A gravacao escreve o temporario, le de volta o que ficou no disco e compara com
o que o usuario viu: mesma estrutura (paragrafos, tabelas, linhas, celulas e
mesclas), mesmo texto, mesmas quebras, as mesmas imagens (pelos bytes) e os
mesmos campos. Cabecalho e rodape (M5) passam pela mesma comparacao, um por tipo.
Estilos (M6): o estilo de cada paragrafo e os estilos de caractere usados nele.
O estilo de caractere de cada campo PAGE/NUMPAGES (0.1.11).
Objetos opacos (0.1.2): cada um, no lugar, pela `opacos.assinatura` (o XML e o conteudo
das partes que ele usa, sem depender dos nomes de parte e dos rIds renumerados). Uma
parte referenciada que falta faz o leitor nao preservar o objeto, e a contagem acusa.
Hiperlinks, campos e marcadores (0.1.3): o destino de cada trecho de link e as marcas de
campo (com o codigo) e de marcador de cada paragrafo, depois de `marcas.equilibrar`; e o
conteudo das partes preservadas do pacote (`pacote.assinatura`).
Listas (0.1.4): o numId e o nivel de cada paragrafo (o numbering.xml passa pelo validador).
Comentarios (0.1.6): as ancoras de cada paragrafo (com as outras marcas) e, de cada
comentario, o autor, as iniciais, a data, o pai, o resolvido, os ids das partes estendidas e
o conteudo (texto, estilos, links e marcas, paragrafo a paragrafo).
Notas (0.1.10): as referencias de cada paragrafo (com as outras marcas) e, de cada nota, o
tipo, o id e o conteudo (texto, estilos, links e marcas), depois de `notas.preparar`; e as
propriedades efetivas (formato, inicio, reinicio, posicao).
Secoes (0.1.12): onde cada uma termina, o papel, as margens, a numeracao, o tipo, os extras do
w:sectPr e os cabecalhos e rodapes que cada uma declara.
Alteracoes controladas (0.1.13): de cada trecho, a insercao, a exclusao e a formatacao de antes
(com o texto); da marca de paragrafo, a insercao e a exclusao; a formatacao de paragrafo e a
numeracao de antes; e as marcas de movimento (com as outras marcas).
Formatacao efetiva (0.1.16): de cada paragrafo do corpo, do cabecalho e do rodape, o que muda o
layout depois de resolver docDefaults, estilo, lista e formatacao direta (alinhamento, recuos,
espacos, entrelinha, extras do pPr); de cada trecho de texto, a fonte, o tamanho, negrito,
italico... e os extras do rPr; de cada tabela, linha e celula, larguras, recuo, margens, altura
e extras. Ate' a 0.1.15 nada disso era comparado: o arquivo sem styles.xml era gravado com o
docDefaults do documento novo (8 pt depois, 1,08) e reabria com 6 paginas em vez de 4, com a
conferencia passando.
Um arquivo que nao confere nao substitui o original.

Os dois lados passam por `normalizar`: o escritor completa a celula e o corpo
que terminam em tabela com um paragrafo vazio (o Word exige), e isso nao e'
diferenca.
"""

from __future__ import annotations

import hashlib

from editdoc.formato_docx import comentarios as fx_comentarios
from editdoc.formato_docx import opacos
from editdoc.formato_docx import pacote as fx_pacote
from editdoc.formato_docx.erros import ErroDocx
from editdoc.formato_docx.escritor import texto_gravavel
from editdoc.modelo import marcas
from editdoc.modelo import notas as mod_notas
from editdoc.modelo import revisoes as mod_revisoes
from editdoc.modelo.documento import CARACTERE_OBJETO, Documento, Tabela, normalizar
from editdoc.modelo.estilos import CAMPOS_CARACTERE, CAMPOS_PARAGRAFO, catalogo_sem_catalogo
from editdoc.modelo.numeracao import lista_efetiva, recuos_do_nivel
from editdoc.modelo.secoes import secoes_de


class FalhaDeConferencia(Exception):
    """O arquivo gravado nao tem o mesmo texto que o documento."""


def texto_do_paragrafo(paragrafo) -> str:
    """Texto como vai para o arquivo. Imagem e objeto opaco contam como CARACTERE_OBJETO."""
    return "".join(CARACTERE_OBJETO if r.eh_objeto() else texto_gravavel(r.texto)[0]
                   for r in paragrafo.runs)


def _imagens(paragrafo) -> list[str]:
    return [hashlib.sha256(r.imagem.dados).hexdigest()[:16] + f"@{r.imagem.largura_emu}x"
            f"{r.imagem.altura_emu}" for r in paragrafo.runs if r.imagem is not None]


def _objetos(paragrafo) -> tuple:
    return tuple(opacos.assinatura(r.objeto) for r in paragrafo.runs if r.objeto is not None)


def _campos(paragrafo) -> tuple:
    return tuple(r.campo for r in paragrafo.runs if r.campo is not None)


def _estilos(paragrafo) -> tuple:
    """Os estilos de caractere usados no paragrafo e, desde a 0.1.11, o de cada campo.

    O conjunto sozinho nao via o campo perder o estilo quando outro run do paragrafo tinha o
    mesmo (o "Pagina 1 de 3" do rodape, todo em "Numero de pagina"): a 0.1.10 perdia o estilo
    do campo na ponte Qt e a conferencia nao acusava.
    """
    return (tuple(sorted({r.estilo for r in paragrafo.runs if r.estilo})),
            tuple(r.estilo for r in paragrafo.runs if r.campo is not None))


def _links(paragrafo) -> tuple:
    """(destino, texto) de cada trecho de link, com os runs vizinhos de mesmo destino juntos."""
    saida: list[list] = []
    for r in paragrafo.runs:
        if r.marca is not None:
            continue
        texto = CARACTERE_OBJETO if r.eh_objeto() else texto_gravavel(r.texto)[0]
        if saida and saida[-1][0] == r.link:
            saida[-1][1] += texto
        else:
            saida.append([r.link, texto])
    return tuple((link, texto) for link, texto in saida if link is not None)


def _marcas(paragrafo) -> tuple:
    """As marcas de campo (com o codigo) e de marcador, na ordem."""
    return tuple(r.marca for r in paragrafo.runs if r.marca is not None)


def _revisoes(paragrafo) -> tuple:
    """As revisoes do paragrafo (0.1.13): de cada trecho revisado, (insercao, exclusao,
    formatacao de antes, texto), com os vizinhos iguais juntos; e as da marca e do paragrafo."""
    trechos: list[list] = []
    for r in paragrafo.runs:
        if r.insercao is None and r.exclusao is None and not r.mudanca_formato:
            if trechos and trechos[-1][0] is not None:
                trechos.append([None])
            continue
        chave = (r.insercao, r.exclusao, r.mudanca_formato)
        texto = CARACTERE_OBJETO if r.eh_objeto() else texto_gravavel(r.texto)[0]
        if trechos and trechos[-1][0] == chave:
            trechos[-1][1] += texto
        else:
            trechos.append([chave, texto])
    return (tuple((t[0], t[1]) for t in trechos if t[0] is not None),
            paragrafo.marca_insercao, paragrafo.marca_exclusao, paragrafo.mudanca_formato,
            paragrafo.mudanca_numeracao)


#: O que a ausencia de cada propriedade de paragrafo vale na tela e no Word (0.1.16).
_PAR_AUSENTE = {"alinhamento": "esquerda", "recuo_esquerdo_tw": 0, "recuo_direito_tw": 0,
                "recuo_primeira_linha_tw": 0, "espaco_antes_tw": 0, "espaco_depois_tw": 0,
                "espacamento_linha_pct": 100}
#: Idem, de caractere. Fonte e tamanho ausentes sao os da preferencia (a fonte padrao da tela):
#: so' se comparam quando o documento em memoria os define (`_mesma_letra`).
_CAR_AUSENTE = {"negrito": False, "italico": False, "sublinhado": False, "tachado": False,
                "subscrito": False, "sobrescrito": False}
_I_TAMANHO = CAMPOS_CARACTERE.index("tamanho_meio_pt")
_I_FONTE = CAMPOS_CARACTERE.index("fonte")


class _Efetivas:
    """Formatacao efetiva que muda o layout (0.1.16), resolvida como a ponte Qt e o escritor
    resolvem: docDefaults de paragrafo so' fora da tabela, a cadeia do estilo, o recuo do nivel
    da lista e, por cima, a formatacao direta. Cada lado usa o proprio catalogo: e' assim que o
    docDefaults diferente aparece, mesmo com a formatacao direta igual."""

    def __init__(self, doc: Documento) -> None:
        self.est = doc.estilos if doc.estilos is not None else catalogo_sem_catalogo()
        self.numeracao = doc.numeracao
        self.padrao = self.est.id_padrao()
        self.car_padrao = {k: v for k, v in self.est.padrao_caractere.items()
                           if k in CAMPOS_CARACTERE and v is not None}
        self._par: dict = {}
        self._car: dict = {}

    def paragrafo(self, p, em_tabela: bool) -> tuple:
        sid = p.estilo or self.padrao
        efetiva = (lista_efetiva(p.lista, p.lista_nivel, sid, self.est, self.numeracao)
                   if self.numeracao is not None else None)
        chave = (sid, em_tabela, efetiva)
        base = self._par.get(chave)
        if base is None:
            base, _car = self.est.resolver_paragrafo(sid, com_padrao=not em_tabela)
            if efetiva is not None:
                base = {**base, **recuos_do_nivel(self.numeracao.nivel_de(*efetiva, self.est))}
            self._par[chave] = base
        valores = []
        for k in CAMPOS_PARAGRAFO:
            v = getattr(p, k, None)
            if v is None:
                v = base.get(k)
            valores.append(_PAR_AUSENTE[k] if v is None else v)
        return tuple(valores), p.extras

    def trechos(self, p) -> tuple:
        """(quantos caracteres, formatacao) de cada run de texto, na ordem; objeto e marca
        contam sem formatacao (o objeto) ou nao contam (a marca)."""
        saida = []
        for r in p.runs:
            if r.marca is not None:
                continue
            if r.eh_objeto():
                saida.append((1, None))
                continue
            n = len(texto_gravavel(r.texto)[0])
            if not n:
                continue
            chave = (p.estilo or self.padrao, r.estilo)
            base = self._car.get(chave)
            if base is None:
                base = {**self.car_padrao, **self.est.base_de_caractere(*chave)}
                self._car[chave] = base
            valores = []
            for k in CAMPOS_CARACTERE:
                v = getattr(r, k, None)
                if v is None:
                    v = base.get(k)
                valores.append(_CAR_AUSENTE.get(k) if v is None else v)
            saida.append((n, (tuple(valores), r.extras)))
        return tuple(saida)


def _mesma_letra(a, b) -> bool:
    """Formatacao de caractere igual; fonte e tamanho que a memoria nao define nao contam."""
    if a is None or b is None:
        return a is b
    (va, ea), (vb, eb) = a, b
    if ea != eb:
        return False
    for i, (x, y) in enumerate(zip(va, vb)):
        if x != y and not (x is None and i in (_I_FONTE, _I_TAMANHO)):
            return False
    return True


def _trecho_diferente(a: tuple, b: tuple):
    """Primeira formatacao de caractere que difere, caractere a caractere (os runs podem
    estar partidos de outro jeito nos dois lados), ou None."""
    i = j = 0
    usado_a = usado_b = 0
    while i < len(a) and j < len(b):
        (na, fa), (nb, fb) = a[i], b[j]
        if not _mesma_letra(fa, fb):
            return fa, fb
        passo = min(na - usado_a, nb - usado_b)
        usado_a += passo
        usado_b += passo
        if usado_a == na:
            i, usado_a = i + 1, 0
        if usado_b == nb:
            j, usado_b = j + 1, 0
    return None


def _descrever(a, b, campos) -> str:
    """Os campos que mudaram, para o log: "espaco_depois_tw 0 -> 160"."""
    if a is None or b is None:
        return "objeto x texto"
    (va, ea), (vb, eb) = a, b
    partes = [f"{k} {x} -> {y}" for k, x, y in zip(campos, va, vb) if x != y]
    if ea != eb:
        partes.append("extras")
    return ", ".join(partes)


def _tabela_layout(t) -> tuple:
    return (tuple(t.colunas_tw), t.largura, t.layout_fixo, t.margens_celula_tw, t.recuo_tw,
            t.alinhamento, t.extras)


def _itens(blocos, saida: list, onde: str, efetivas: _Efetivas | None = None,
           em_tabela: bool = False) -> None:
    """Sequencia comparavel: um item por paragrafo, tabela, linha e celula.

    Com `efetivas` (0.1.16), cada item leva no fim a formatacao efetiva que muda o layout."""
    n_par = 0
    for bloco in blocos:
        if isinstance(bloco, Tabela):
            saida.append((f"{onde}tabela", "tabela", len(bloco.linhas), len(bloco.colunas_tw),
                          bloco.estilo, _tabela_layout(bloco) if efetivas else None))
            for i, linha in enumerate(bloco.linhas):
                saida.append((f"{onde}linha {i + 1}", "linha", len(linha.celulas), linha.cabecalho,
                              (linha.altura_tw, linha.altura_exata, linha.extras)
                              if efetivas else None))
                for j, celula in enumerate(linha.celulas):
                    lugar = f"{onde}celula {i + 1},{j + 1}: "
                    saida.append((lugar, "celula", celula.colunas, celula.mescla_vertical,
                                  (celula.alinhamento_vertical, celula.extras)
                                  if efetivas else None))
                    _itens(celula.blocos, saida, lugar, efetivas, True)
            saida.append((f"{onde}fim da tabela", "fim"))
        else:
            n_par += 1
            saida.append((f"{onde}paragrafo {n_par}", "p", texto_do_paragrafo(bloco),
                          bloco.quebra_antes, tuple(_imagens(bloco)), _campos(bloco),
                          bloco.estilo, _estilos(bloco),
                          _objetos(bloco), _links(bloco), _marcas(bloco),
                          (bloco.lista, bloco.lista_nivel), bloco.secao is not None,
                          _revisoes(bloco),
                          efetivas.paragrafo(bloco, em_tabela) if efetivas else None,
                          efetivas.trechos(bloco) if efetivas else None))


def _comentarios(doc: Documento) -> tuple:
    """O que se compara de cada comentario (0.1.6), na ordem do catalogo."""
    cat = doc.comentarios
    if cat is None:
        return ()
    saida = []
    for c in cat.itens:
        itens: list = []
        _itens(normalizar(Documento(paragrafos=list(c.paragrafos))).paragrafos, itens, "")
        saida.append((c.id, c.autor, c.iniciais, c.data, c.pai, c.resolvido, c.para_id,
                      c.duravel, c.data_utc, tuple(x[1:] for x in itens)))
    return tuple(saida)


def _notas(doc: Documento) -> tuple:
    """O que se compara de cada nota (0.1.10), na ordem do catalogo, e as propriedades."""
    cat = doc.notas
    if cat is None:
        return ()
    saida = []
    for n in cat.todas():
        itens: list = []
        _itens(normalizar(Documento(paragrafos=list(n.paragrafos))).paragrafos, itens, "")
        saida.append((n.tipo, n.id, tuple(x[1:] for x in itens)))
    props = tuple(cat.propriedades(t) for t in mod_notas.TIPOS)
    return tuple(saida), props


def conferir(dados: bytes, esperado: Documento) -> None:
    """Relê `dados` com o proprio leitor e compara estrutura, texto e imagens."""
    from editdoc.formato_docx.leitor import ler
    try:
        lido, _avisos = ler(dados)
    except ErroDocx as erro:
        raise FalhaDeConferencia(f"o arquivo gravado nao pode ser lido: {erro.codigo}") from None
    a: list = []
    b: list = []
    # O escritor grava as marcas em pares (marcas.equilibrar): e' isso que tem de voltar.
    esperado = mod_notas.preparar(fx_comentarios.preparar(
        mod_revisoes.equilibrar_movimentos(marcas.equilibrar(esperado)[0])))
    esperado_n, lido_n = normalizar(esperado), normalizar(lido)
    ef_a, ef_b = _Efetivas(esperado_n), _Efetivas(lido_n)
    _itens(esperado_n.paragrafos, a, "", ef_a)
    _itens(lido_n.paragrafos, b, "", ef_b)
    secoes_a, secoes_b = secoes_de(esperado_n), secoes_de(lido_n)
    if len(secoes_a) != len(secoes_b):
        raise FalhaDeConferencia(f"secoes: esperado {len(secoes_a)}, gravado {len(secoes_b)}")
    for i, (sa, sb) in enumerate(zip(secoes_a, secoes_b)):
        rotulo = f"secao {i + 1}" if i < len(secoes_a) - 1 else "ultima secao"
        if sa.pagina != sb.pagina:
            raise FalhaDeConferencia(f"papel, margens ou numeracao diferentes na {rotulo}")
        if (sa.tipo, sa.extras) != (sb.tipo, sb.extras):
            raise FalhaDeConferencia(f"propriedades da {rotulo} diferentes")
        prefixo = "" if i == len(secoes_a) - 1 else f"{rotulo}, "
        for nome, faixa_a, faixa_b in (("cabecalho", sa.cabecalhos, sb.cabecalhos),
                                       ("rodape", sa.rodapes, sb.rodapes)):
            if sorted(faixa_a) != sorted(faixa_b):
                raise FalhaDeConferencia(f"{prefixo}{nome}: tipos diferentes ({sorted(faixa_a)} "
                                         f"e {sorted(faixa_b)})")
            for tipo in sorted(faixa_a):
                _itens(faixa_a[tipo], a, f"{prefixo}{nome} {tipo}: ", ef_a)
                _itens(faixa_b[tipo], b, f"{prefixo}{nome} {tipo}: ", ef_b)
    n_a = sum(1 for x in a if x[1] == "p")
    n_b = sum(1 for x in b if x[1] == "p")
    if n_a != n_b:
        raise FalhaDeConferencia(f"paragrafos: esperado {n_a}, gravado {n_b}")
    for x, y in zip(a, b):
        if x[1:] == y[1:]:
            continue
        lugar = x[0]
        if x[1] == "p" and y[1] == "p":
            if x[2] != y[2]:
                raise FalhaDeConferencia(f"texto diferente no {lugar}")
            if x[3] != y[3]:
                raise FalhaDeConferencia(f"quebra de pagina diferente no {lugar}")
            if x[5] != y[5]:
                raise FalhaDeConferencia(f"campo diferente no {lugar}")
            if x[8] != y[8]:
                raise FalhaDeConferencia(f"objeto (caixa de texto, forma...) diferente no {lugar}")
            if x[9] != y[9]:
                raise FalhaDeConferencia(f"hiperlink diferente no {lugar}")
            if x[10] != y[10]:
                raise FalhaDeConferencia(f"campo ou marcador diferente no {lugar}")
            if x[11] != y[11]:
                raise FalhaDeConferencia(f"lista (numeracao) diferente no {lugar}")
            if x[12] != y[12]:
                raise FalhaDeConferencia(f"quebra de secao diferente no {lugar}")
            if x[13] != y[13]:
                raise FalhaDeConferencia(f"alteracao controlada diferente no {lugar}")
            if x[6:8] != y[6:8]:
                raise FalhaDeConferencia(f"estilo diferente no {lugar}")
            if x[4] != y[4]:
                raise FalhaDeConferencia(f"imagem diferente no {lugar}")
            if x[14] != y[14]:
                raise FalhaDeConferencia(f"formatacao do paragrafo diferente no {lugar} ("
                                         f"{_descrever(x[14], y[14], CAMPOS_PARAGRAFO)})")
            dif = _trecho_diferente(x[15], y[15])
            if dif is None:
                continue  # so' a fonte ou o tamanho que a memoria nao define
            raise FalhaDeConferencia(f"formatacao do texto diferente no {lugar} ("
                                     f"{_descrever(dif[0], dif[1], CAMPOS_CARACTERE)})")
        if x[1] == y[1] and x[1:-1] == y[1:-1]:
            raise FalhaDeConferencia(f"formatacao da {x[1]} diferente em {lugar}")
        raise FalhaDeConferencia(f"estrutura de tabela diferente em {lugar}")
    if len(a) != len(b):
        raise FalhaDeConferencia("estrutura de tabela diferente no fim do documento")
    if esperado.pagina != lido.pagina:
        raise FalhaDeConferencia("papel ou margens diferentes do documento")
    a_coment, b_coment = _comentarios(esperado), _comentarios(lido)
    if len(a_coment) != len(b_coment):
        raise FalhaDeConferencia(f"comentarios: esperado {len(a_coment)}, gravado {len(b_coment)}")
    for x, y in zip(a_coment, b_coment):
        if x != y:
            raise FalhaDeConferencia(f"comentario {x[0]} diferente no arquivo gravado")
    a_notas, b_notas = _notas(esperado), _notas(lido)
    if (a_notas[0] if a_notas else ()) != (b_notas[0] if b_notas else ()):
        raise FalhaDeConferencia("notas de rodape ou de fim diferentes no arquivo gravado")
    if a_notas and b_notas and a_notas[1] != b_notas[1]:
        raise FalhaDeConferencia("propriedades das notas diferentes no arquivo gravado")
    if fx_pacote.assinatura(esperado.pacote) != fx_pacote.assinatura(lido.pacote):
        raise FalhaDeConferencia("partes preservadas do pacote (propriedades, customXml, "
                                 "fontes...) diferentes")


def conferidor(esperado: Documento):
    """Funcao no formato que `gravacao.gravar_bytes(conferir=...)` espera."""
    def _conferir(dados: bytes) -> None:
        conferir(dados, esperado)
    return _conferir
