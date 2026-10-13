"""QTextDocument -> modelo. A volta de `para_qt`, sem perda do que o modelo guarda.

Runs vizinhos com a mesma formatacao ficam fundidos (o Qt ja os funde); quem
compara ida-e-volta usa `modelo.documento.normalizar` nos dois lados.

Tabelas: percorre os quadros do documento (QTextFrame.iterator), e cada
QTextTable vira `Tabela`. Celula coberta por mescla vertical volta como celula
"continua", vazia, como o Word grava. Bloco estrutural vazio (ver para_qt) nao
volta. Largura da coluna vem da restricao fixa; uma tabela colada de HTML, sem
largura fixa, divide a largura do corpo.

Estilos (M6): o id do estilo sai da propriedade de usuario do bloco e do caractere; a
formatacao que volta ao modelo e' so' a direta, o efetivo menos o estilo resolvido.

Hiperlinks e marcas (0.1.3): o link de cada fragmento (`links.link_de`) e as marcas de
campo e de marcador (`marcas.marca_de`), uma por caractere de objeto.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import (QImage, QTextBlockFormat, QTextCharFormat, QTextDocument, QTextFormat,
                           QTextLength, QTextListFormat, QTextTable)

from editdoc import log_interno
from editdoc.modelo import imagem as mod_imagem
from editdoc.modelo.campos import tipo_do_campo
from editdoc.modelo.documento import (CARACTERE_OBJETO, Celula, Documento, Imagem, Linha,
                                      Paragrafo, Run, Tabela)
from editdoc.modelo.estilos import CAMPOS_CARACTERE, CAMPOS_PARAGRAFO, NIVEL_CORPO
from editdoc.modelo.unidades import EMU_POR_PX, twips_de_px
from editdoc.ponte_qt import campos, imagens, links, marcas, opacos
from editdoc.ponte_qt import estilos as pq_estilos
from editdoc.ponte_qt.para_qt import (LINHA_SEPARADORA, PROP_CELULA, PROP_ESTRUTURAL,
                                      PROP_TABELA, bordas_da_celula_em, bordas_da_tabela_em,
                                      ler_json)

log = log_interno.obter(__name__)

P = QTextFormat.Property
_PROPORCIONAL = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
_MARCAS = {
    QTextListFormat.Style.ListDisc,
    QTextListFormat.Style.ListCircle,
    QTextListFormat.Style.ListSquare,
}
_VALIGN = {"topo", "centro", "base"}
#: Largura do corpo A4 com margens Normal, para tabela sem largura fixa num documento sem pagina.
_CORPO_PADRAO_TW = 9026


def _alinhamento(bf: QTextBlockFormat) -> str | None:
    if not bf.hasProperty(P.BlockAlignment):
        return None
    from PySide6.QtCore import Qt
    flags = bf.alignment()
    if flags & Qt.AlignmentFlag.AlignHCenter:
        return "centro"
    if flags & Qt.AlignmentFlag.AlignRight:
        return "direita"
    if flags & Qt.AlignmentFlag.AlignJustify:
        return "justificado"
    if flags & Qt.AlignmentFlag.AlignLeft:
        return "esquerda"
    return None


def _run(frag_texto: str, cf: QTextCharFormat) -> Run:
    run = Run(texto=frag_texto.replace(LINHA_SEPARADORA, "\n"))
    if cf.hasProperty(P.FontWeight):
        run.negrito = cf.fontWeight() >= 600
    if cf.hasProperty(P.FontItalic):
        run.italico = cf.fontItalic()
    if cf.hasProperty(P.TextUnderlineStyle) or cf.hasProperty(P.FontUnderline):
        run.sublinhado = (cf.underlineStyle()
                          != QTextCharFormat.UnderlineStyle.NoUnderline)
    if cf.hasProperty(P.FontStrikeOut):
        run.tachado = cf.fontStrikeOut()
    if cf.hasProperty(P.TextVerticalAlignment):
        va = cf.verticalAlignment()
        run.subscrito = va == QTextCharFormat.VerticalAlignment.AlignSubScript
        run.sobrescrito = va == QTextCharFormat.VerticalAlignment.AlignSuperScript
    if cf.hasProperty(P.FontPointSize):
        run.tamanho_meio_pt = round(cf.fontPointSize() * 2)
    if cf.hasProperty(P.FontFamilies):
        fams = cf.fontFamilies()
        run.fonte = fams[0] if fams else None
    if cf.hasProperty(P.ForegroundBrush):
        run.cor_hex = cf.foreground().color().name()[1:].upper()
    return run


def imagem_do_formato(doc: QTextDocument, cf: QTextCharFormat) -> Imagem | None:
    """O run de imagem de um fragmento com QTextImageFormat. None se a imagem nao e' conhecida."""
    fmt = cf.toImageFormat()
    nome = fmt.name()
    registro = imagens.dados_de(nome)
    if registro is None:
        # Imagem que nao veio do EditDoc: so' se o recurso estiver no documento.
        recurso = doc.resource(QTextDocument.ResourceType.ImageResource, QUrl(nome))
        if not isinstance(recurso, QImage) or recurso.isNull():
            log.warning("imagem sem dados descartada ao salvar: %s", nome[:60])
            return None
        dados = imagens.png_de(recurso)
        registro = (dados, "png")
        nome = imagens.registrar(dados, "png")
    dados, formato = registro
    largura, altura = fmt.width(), fmt.height()
    if largura <= 0 or altura <= 0:
        dims = mod_imagem.dimensoes(dados, formato) or (96, 96)
        largura, altura = (largura if largura > 0 else dims[0],
                           altura if altura > 0 else dims[1])
    return Imagem(dados=dados, formato=formato,
                  largura_emu=max(1, round(largura * EMU_POR_PX)),
                  altura_emu=max(1, round(altura * EMU_POR_PX)),
                  descricao=fmt.toolTip() or "")


def _run_direto(texto: str, cf: QTextCharFormat, sid_par, res) -> Run:
    """Run com a formatacao direta: o efetivo do Qt menos o estilo resolvido."""
    run = _run(texto, cf)
    sid_car = pq_estilos.estilo_do_caractere(cf)
    if sid_car is not None and res.estilos.obter(sid_car) is not None:
        run.estilo = sid_car
    base = res.caractere(sid_par, run.estilo)
    for k in CAMPOS_CARACTERE:
        valor = getattr(run, k)
        if valor is not None and valor == base.get(k):
            setattr(run, k, None)
    return run


def _paragrafo(bloco, res, em_celula: bool = False) -> Paragrafo:
    bf = bloco.blockFormat()
    p = Paragrafo()
    sid = pq_estilos.estilo_do_bloco(bf)
    if sid is not None and sid != res.estilos.id_padrao() and res.estilos.obter(sid) is not None:
        p.estilo = sid
    base, _car = res.paragrafo(p.estilo, em_celula)
    efetivo = pq_estilos.props_de_bloco(bf)
    for k in CAMPOS_PARAGRAFO:
        valor = efetivo.get(k)
        if valor is not None and valor != base.get(k):
            setattr(p, k, valor)
    nivel = efetivo.get("nivel")
    if nivel != base.get("nivel"):
        p.nivel = NIVEL_CORPO if nivel is None else nivel
    p.quebra_antes = bool(bf.pageBreakPolicy() & QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
    lista = bloco.textList()
    if lista is not None:
        p.numeracao = ("marcadores" if lista.format().style() in _MARCAS
                       else "numeracao")
    doc = bloco.document()
    it = bloco.begin()
    while not it.atEnd():
        frag = it.fragment()
        if frag.isValid() and frag.text():
            cf = frag.charFormat()
            # Hiperlink (0.1.3): vale para texto, imagem, objeto, campo e marca.
            link = links.link_de(cf)
            if campos.eh_campo(cf):
                # Campo (M5): um run por caractere de objeto, com o resultado guardado.
                for caractere in frag.text():
                    if caractere == CARACTERE_OBJETO:
                        run = _run_direto(campos.resultado_de(cf), cf, p.estilo, res)
                        instrucao = campos.instrucao_de(cf)
                        # Instrucao estranha (formato montado a mao): fica o texto, sem campo.
                        run.campo = instrucao if tipo_do_campo(instrucao) else None
                        run.link = link
                        p.runs.append(run)
            elif marcas.eh_marca(cf):
                # Campo ou marcador (0.1.3): uma marca por caractere, sem texto.
                marca = marcas.marca_de(cf)
                for caractere in frag.text():
                    if caractere != CARACTERE_OBJETO:
                        continue
                    if marca is None:
                        log.warning("marca de campo ilegivel descartada ao salvar")
                        continue
                    run = _run_direto("", cf, p.estilo, res)
                    run.marca = marca
                    run.link = link
                    p.runs.append(run)
            elif opacos.eh_opaco(cf):
                # Objetos opacos iguais lado a lado viram um fragmento so': um por caractere.
                obj = opacos.objeto_de(cf)
                for caractere in frag.text():
                    if caractere != CARACTERE_OBJETO:
                        continue
                    if obj is not None:
                        p.runs.append(Run(texto=CARACTERE_OBJETO, objeto=obj, link=link))
                    else:
                        log.warning("objeto opaco sem registro descartado ao salvar")
            elif cf.isImageFormat():
                # Imagens iguais lado a lado viram um fragmento so': uma por caractere.
                for caractere in frag.text():
                    if caractere != CARACTERE_OBJETO:
                        continue
                    imagem = imagem_do_formato(doc, cf)
                    if imagem is not None:
                        p.runs.append(Run(texto=CARACTERE_OBJETO, imagem=imagem, link=link))
            else:
                run = _run_direto(frag.text(), cf, p.estilo, res)
                run.link = link
                p.runs.append(run)
        it += 1
    return p


def _estrutural_vazio(bloco) -> bool:
    return bloco.text() == "" and bool(bloco.blockFormat().property(PROP_ESTRUTURAL))


def _blocos(iterador, largura_corpo_tw: int, em_celula: bool = False, res=None) -> list:
    """Blocos de um quadro ou de uma celula, a partir do iterador do Qt.

    Dentro de celula a quebra de pagina nao vale (o EditDoc nao quebra pagina na tabela):
    um paragrafo colado com quebra perde a quebra, como o leitor faz com o arquivo.
    """
    saida: list = []
    it = iterador
    while not it.atEnd():
        quadro = it.currentFrame()
        if quadro is not None:
            if isinstance(quadro, QTextTable):
                saida.append(_tabela(quadro, largura_corpo_tw, res))
            else:
                # Quadro generico (HTML colado): o conteudo entra como blocos.
                saida.extend(_blocos(quadro.begin(), largura_corpo_tw, em_celula, res))
        else:
            bloco = it.currentBlock()
            if bloco.isValid() and not _estrutural_vazio(bloco):
                paragrafo = _paragrafo(bloco, res, em_celula)
                if em_celula:
                    paragrafo.quebra_antes = False
                saida.append(paragrafo)
        it += 1
    return saida


def larguras_tw(tabela: QTextTable, largura_corpo_tw: int) -> list[int]:
    """Largura de cada coluna em twips. Sem largura fixa (HTML colado), divide o corpo."""
    colunas = tabela.columns()
    restricoes = tabela.format().columnWidthConstraints()
    if len(restricoes) == colunas and all(
            r.type() == QTextLength.Type.FixedLength for r in restricoes):
        return [max(1, twips_de_px(r.rawValue())) for r in restricoes]
    larguras = []
    for i in range(colunas):
        r = restricoes[i] if i < len(restricoes) else None
        if r is not None and r.type() == QTextLength.Type.FixedLength:
            larguras.append(max(1, twips_de_px(r.rawValue())))
        elif r is not None and r.type() == QTextLength.Type.PercentageLength:
            larguras.append(max(1, round(largura_corpo_tw * r.rawValue() / 100)))
        else:
            larguras.append(max(1, largura_corpo_tw // max(1, colunas)))
    return larguras


def _celula_de_formato(celula: Celula, fmt) -> dict:
    """Preenche os atributos guardados no JSON da celula. Devolve o JSON, para a linha."""
    dado = ler_json(fmt, PROP_CELULA)
    celula.bordas = bordas_da_celula_em(fmt)
    sombra = dado.get("sombreamento_hex")
    celula.sombreamento_hex = sombra if isinstance(sombra, str) else None
    valign = dado.get("alinhamento_vertical")
    celula.alinhamento_vertical = valign if valign in _VALIGN else None
    return dado


def _tabela(qt: QTextTable, largura_corpo_tw: int, res) -> Tabela:
    tf = qt.format()
    dado = ler_json(tf, PROP_TABELA)
    tabela = Tabela(colunas_tw=larguras_tw(qt, largura_corpo_tw))
    tabela.bordas = bordas_da_tabela_em(tf) if dado.get("bordas") is not None else None
    alinhamento = dado.get("alinhamento")
    tabela.alinhamento = alinhamento if alinhamento in ("esquerda", "centro", "direita") else None
    recuo = dado.get("recuo_tw")
    tabela.recuo_tw = recuo if isinstance(recuo, int) else None
    largura = dado.get("largura")
    if isinstance(largura, list) and len(largura) == 2:
        tabela.largura = (str(largura[0]), int(largura[1]))
    fixo = dado.get("layout_fixo")
    tabela.layout_fixo = fixo if isinstance(fixo, bool) else None
    margens = dado.get("margens_celula_tw")
    if isinstance(margens, list) and len(margens) == 4:
        tabela.margens_celula_tw = tuple(int(m) for m in margens)
    cabecalho = tf.headerRowCount()
    linhas, colunas = qt.rows(), qt.columns()
    for r in range(linhas):
        linha = Linha(cabecalho=r < cabecalho)
        dado_linha = None
        c = 0
        while c < colunas:
            cel_qt = qt.cellAt(r, c)
            span = max(1, cel_qt.columnSpan())
            if cel_qt.column() != c:
                c += 1
                continue
            if cel_qt.row() == r:
                celula = Celula(blocos=_blocos(cel_qt.begin(), largura_corpo_tw, True, res),
                                colunas=span,
                                mescla_vertical="inicio" if cel_qt.rowSpan() > 1 else None)
                dado_cel = _celula_de_formato(celula, cel_qt.format())
                if dado_linha is None:
                    dado_linha = dado_cel
            else:
                celula = Celula(blocos=[Paragrafo()], colunas=span, mescla_vertical="continua")
            if not celula.blocos:
                celula.blocos.append(Paragrafo())
            linha.celulas.append(celula)
            c += span
        if dado_linha:
            altura = dado_linha.get("altura_tw")
            linha.altura_tw = altura if isinstance(altura, int) else None
            linha.altura_exata = bool(dado_linha.get("altura_exata"))
        tabela.linhas.append(linha)
    return tabela


def extrair_blocos(documento_qt: QTextDocument, largura_corpo_tw: int = _CORPO_PADRAO_TW) -> list:
    """Blocos de um documento de cabecalho ou rodape."""
    res = pq_estilos.Resolvedor(pq_estilos.catalogo(documento_qt))
    return _blocos(documento_qt.rootFrame().begin(), largura_corpo_tw, res=res)


def extrair(documento_qt: QTextDocument) -> Documento:
    largura = documento_qt.pageSize().width()
    # No layout paginado a unidade e' o twip; fora dele (testes), usa o corpo A4.
    largura_corpo = round(largura) if 1000 < largura <= 100000 else _CORPO_PADRAO_TW
    estilos = pq_estilos.catalogo(documento_qt)
    paragrafos = _blocos(documento_qt.rootFrame().begin(), largura_corpo,
                         res=pq_estilos.Resolvedor(estilos))
    return Documento(paragrafos=paragrafos, estilos=estilos)
