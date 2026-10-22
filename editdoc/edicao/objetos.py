"""Mover, redimensionar e trocar a quebra de texto de um objeto (0.1.9), como no Word.

Quem chama (o painel, o dialogo "Posicao e tamanho", a galeria de quebra) diz o objeto (o
caractere dele no documento em edicao: corpo, cabecalho ou rodape) e o que quer: o retangulo
novo na folha, em twips, ou a quebra. Aqui se faz a conta da posicao no referencial do arquivo
(`modelo/flutuantes.deslocamento_para`), se regrava o XML do objeto (`formato_docx/posicao.py`)
e se troca o objeto do caractere num passo so' de desfazer.

- Mesmo tipo de caractere (o float do Qt continua float, do mesmo lado; o que nao reserva
  continua sem reservar): troca o formato do caractere (`setCharFormat` com o ObjectIndex de
  antes), como a edicao da caixa de texto (0.1.5).
- Muda o tipo (quebra que passa a reservar espaco ou deixa de reservar, lado do float, linha
  <-> flutuante): o caractere sai e entra de novo pelo caminho de sempre (`opacos.inserir`, que
  cria o float pelo `insertImage`). O float que sai fica orfao, e a cura da 0.1.7 o zera.
- Reancorar (arraste para outra pagina, ou objeto preso ao paragrafo arrastado para outro
  paragrafo): o caractere vai para o comeco do paragrafo mais proximo do topo novo, como no
  Word. Em duas etapas: o caractere muda de lugar com a posicao calculada no layout de antes, e
  depois do layout refeito a posicao e' recalculada e regravada no mesmo passo de desfazer
  (`joinPreviousEditBlock`). Nao reancora (e so' muda o deslocamento) quando seria arriscado:
  ancora travada (`locked`), cabecalho e rodape, tabela de um dos lados, bloco estrutural.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextFormat

from editdoc import log_interno
from editdoc.formato_docx import posicao
from editdoc.modelo import flutuantes as mf
from editdoc.modelo.unidades import EMU_POR_TWIP
from editdoc.ponte_qt import flutuantes as pq_flutuantes
from editdoc.ponte_qt import links as pq_links
from editdoc.ponte_qt import opacos as pq_opacos

log = log_interno.obter(__name__)

#: Menor lado que o arraste deixa (twips): 1 px96.
LADO_MINIMO_TW = 15.0


def formato_em(doc, pos: int) -> QTextCharFormat | None:
    return pq_links.formato_em(doc, pos)


def objeto_em(doc, pos: int):
    """O objeto opaco do caractere em `pos`, ou None."""
    cf = formato_em(doc, pos)
    if cf is None or not pq_opacos.eh_opaco(cf):
        return None
    return pq_opacos.objeto_de(cf)


def estado_em(doc, pos: int) -> posicao.Estado | None:
    obj = objeto_em(doc, pos)
    return posicao.estado(obj.xml) if obj is not None else None


def eh_imagem_na_linha(doc, pos: int) -> bool:
    cf = formato_em(doc, pos)
    return cf is not None and cf.isImageFormat()


def tem_posicao(doc, pos: int) -> bool:
    """O caractere e' um objeto que tem posicao e tamanho (imagem, forma, caixa, grupo...)."""
    if eh_imagem_na_linha(doc, pos):
        return True
    obj = objeto_em(doc, pos)
    return obj is not None and obj.tipo != "equacao" and posicao.estado(obj.xml) is not None


# -- troca do objeto no caractere ----------------------------------------------------------

def _precisa_quadro(doc, cursor_pos: int, obj) -> bool:
    fl = pq_flutuantes.info(obj, pq_opacos.registrar(obj))
    if fl is None or not fl.ancoragem.reserva_espaco():
        return False
    c = QTextCursor(doc)
    c.setPosition(cursor_pos)
    return c.currentTable() is None


def _base_sem_objeto(cf: QTextCharFormat) -> QTextCharFormat:
    base = QTextCharFormat(cf)
    base.clearProperty(QTextFormat.Property.ObjectIndex)
    for prop in (QTextFormat.Property.ImageName, QTextFormat.Property.ImageWidth,
                 QTextFormat.Property.ImageHeight):
        base.clearProperty(prop)
    return base


def _inserir(c: QTextCursor, novo, base: QTextCharFormat) -> None:
    from editdoc.modelo.documento import Imagem
    from editdoc.ponte_qt import para_qt
    if isinstance(novo, Imagem):
        para_qt.inserir_imagem(c, novo)
    else:
        pq_opacos.inserir(c, novo, base)


def trocar(doc, pos: int, novo, destino: int | None = None, juntar: bool = False) -> int:
    """Poe `novo` (ObjetoOpaco ou Imagem) no lugar do objeto em `pos`, num passo de desfazer.
    `destino`: posicao (no documento de agora) para onde o caractere vai (reancorar). Devolve a
    posicao do caractere depois da troca."""
    from editdoc.modelo.documento import Imagem
    cf = formato_em(doc, pos)
    if cf is None:
        return pos
    reinserir = destino is not None and destino != pos
    if not reinserir:
        if isinstance(novo, Imagem) or cf.isImageFormat():
            reinserir = True
        else:
            tem = cf.objectIndex() >= 0
            precisa = _precisa_quadro(doc, pos, novo)
            if tem != precisa:
                reinserir = True
            elif tem:
                quadro = pq_flutuantes.quadro_de(doc, cf)
                fl = pq_flutuantes.info(novo, pq_opacos.registrar(novo))
                lado = pq_flutuantes.lado_inicial(fl, getattr(doc, "_pagina_flutuantes", None))
                if quadro is None or quadro.frameFormat().position() != lado:
                    reinserir = True
    c = QTextCursor(doc)
    if juntar:
        c.joinPreviousEditBlock()
    else:
        c.beginEditBlock()
    try:
        if not reinserir:
            c.setPosition(pos)
            c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
            c.setCharFormat(pq_opacos.formato_de_opaco(cf, novo))
            final = pos
        else:
            base = _base_sem_objeto(cf)
            alvo = pos if destino is None else destino
            if alvo > pos:
                alvo -= 1  # o caractere sai antes de entrar
            c.setPosition(pos)
            c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
            c.removeSelectedText()
            c.setPosition(alvo)
            _inserir(c, novo, base)
            final = alvo
    finally:
        c.endEditBlock()
    return final


# -- conta da posicao ----------------------------------------------------------------------

def z_novo(docs) -> int:
    """relativeHeight unico para o objeto que passa a flutuar: o maior dos documentos + 1."""
    maior = None
    for doc in docs:
        for p in pq_opacos.posicoes_de_opacos(doc):
            obj = objeto_em(doc, p)
            z = posicao.z_de(obj.xml) if obj is not None else None
            if z is not None and (maior is None or z > maior):
                maior = z
    return posicao.Z_INICIAL if maior is None else min(maior + 1, 2 ** 32 - 1)


def _mudanca(est: posicao.Estado, ref: mf.Referencia, x_tw: float, y_tw: float,
             tamanho_tw: tuple | None, v_rel: str | None = None) -> posicao.Mudanca:
    tamanho = None
    if tamanho_tw is not None:
        tamanho = (round(tamanho_tw[0] * EMU_POR_TWIP), round(tamanho_tw[1] * EMU_POR_TWIP))
    if est.simples:
        return posicao.Mudanca(simples=(round(x_tw * EMU_POR_TWIP), round(y_tw * EMU_POR_TWIP)),
                               tamanho=tamanho)
    v_rel = v_rel or est.v_rel
    return posicao.Mudanca(h=(est.h_rel, mf.deslocamento_para("h", est.h_rel, ref, x_tw)),
                           v=(v_rel, mf.deslocamento_para("v", v_rel, ref, y_tw)),
                           tamanho=tamanho)


def _bloco_para_ancora(layout, n: int, y_tw: float):
    """O paragrafo do corpo mais perto do topo `y_tw` (twips da folha n), ou None."""
    doc = layout.doc
    hb = layout.hb
    topo = layout.topo_da_pagina(n)
    y_doc = layout.mapa.topo(n) + min(max(y_tw - topo, 0.0), hb - 1.0)
    pos = doc.documentLayout().hitTest(QPointF(1.0, y_doc), Qt.HitTestAccuracy.FuzzyHit)
    pos = layout.ajustar_para_pagina(max(0, pos), n)
    return doc.findBlock(pos)


def _reancoravel(doc, bloco, pos_atual: int) -> bool:
    from editdoc.ponte_qt.para_qt import PROP_ESTRUTURAL
    if not bloco.isValid() or bloco == doc.findBlock(pos_atual):
        return False
    if QTextCursor(bloco).currentTable() is not None:
        return False
    c = QTextCursor(doc)
    c.setPosition(pos_atual)
    if c.currentTable() is not None:
        return False
    return not bool(bloco.blockFormat().property(PROP_ESTRUTURAL))


def mover(doc, g, pos: int, n: int, x_tw: float, y_tw: float, tamanho_tw: tuple | None = None,
          layout=None, reancorar: bool = True) -> int | None:
    """Poe o objeto flutuante de `pos` com o canto em (x_tw, y_tw) da folha n, e com o tamanho
    `tamanho_tw` (largura, altura em twips), se dado. `layout`: o LayoutPaginado do corpo (None
    no cabecalho e no rodape, onde o objeto fica na folha que se edita). Devolve a posicao do
    caractere (muda se reancorou), ou None se nao e' um objeto flutuante."""
    obj = objeto_em(doc, pos)
    est = posicao.estado(obj.xml) if obj is not None else None
    if est is None or est.na_linha:
        return None
    n_atual, ref, _d = g.referencia(pos)
    destino = None
    v_rel = None
    if layout is not None and n != n_atual:
        bloco = _bloco_para_ancora(layout, n, y_tw) if reancorar and not est.travado else None
        if bloco is not None and _reancoravel(doc, bloco, pos):
            destino = bloco.position()
        elif not est.simples:
            # Sem reancorar (limite registrado): o objeto fica na pagina da ancora, na mesma
            # altura da folha, relativo a' pagina.
            v_rel = "page"
    elif layout is not None and reancorar and not est.travado and \
            est.v_rel in ("paragraph", "line") and not est.simples:
        bloco = _bloco_para_ancora(layout, n, y_tw)
        if bloco is not None and _reancoravel(doc, bloco, pos):
            destino = bloco.position()
    if destino is not None:
        _n, ref, _d = g.referencia(destino)
    mud = _mudanca(est, ref, x_tw, y_tw, tamanho_tw, v_rel)
    novo = posicao.objeto_com(obj, mud)
    if novo.xml == obj.xml and destino is None:
        return pos
    final = trocar(doc, pos, novo, destino)
    if destino is None:
        return final
    # Segunda etapa: com o layout refeito, a posicao no paragrafo novo.
    doc.documentLayout().blockBoundingRect(doc.lastBlock())
    g.atualizar()
    _n, ref, _d = g.referencia(final)
    mud = _mudanca(est, ref, x_tw, y_tw, tamanho_tw, v_rel)
    novo2 = posicao.objeto_com(obj, mud)
    if novo2.xml != novo.xml:
        final = trocar(doc, final, novo2, juntar=True)
    return final


def redimensionar_na_linha(doc, pos: int, largura_tw: float, altura_tw: float) -> bool:
    """Tamanho novo do objeto preservado na linha (caixa, forma, objeto): wp:extent e o xfrm de
    dentro, ou o width/height do VML. Um passo de desfazer."""
    obj = objeto_em(doc, pos)
    est = posicao.estado(obj.xml) if obj is not None else None
    if est is None or not est.na_linha:
        return False
    mud = posicao.Mudanca(tamanho=(round(largura_tw * EMU_POR_TWIP),
                                   round(altura_tw * EMU_POR_TWIP)))
    novo = posicao.objeto_com(obj, mud)
    if novo.xml == obj.xml:
        return False
    trocar(doc, pos, novo)
    return True


def definir_quebra(doc, g, pos: int, quebra: str, docs_z=(), retangulo_tw=None,
                   n: int | None = None) -> int:
    """Troca a quebra de texto do objeto (ou da imagem na linha) em `pos`. `retangulo_tw`: onde
    o objeto esta' agora na folha n (x, y, w, h), para o objeto que passa a flutuar ficar no
    mesmo lugar. Devolve a posicao do caractere. PosicaoRecusada se nao der sem perda."""
    from editdoc.ponte_qt import de_qt
    if quebra not in posicao.QUEBRAS:
        raise ValueError(quebra)
    cf = formato_em(doc, pos)
    if cf is None:
        return pos
    if cf.isImageFormat():
        if quebra == "linha":
            return pos
        imagem = de_qt.imagem_do_formato(doc, cf)
        if imagem is None:
            raise posicao.PosicaoRecusada("A imagem não pôde ser lida.")
        obj = posicao.objeto_de_imagem(imagem)
    else:
        obj = pq_opacos.objeto_de(cf)
    est = posicao.estado(obj.xml) if obj is not None else None
    if est is None:
        raise posicao.PosicaoRecusada("Este objeto não tem posição na página.")
    if est.quebra == quebra and not cf.isImageFormat():
        return pos
    if quebra == "linha":
        if posicao.vira_imagem_na_linha(obj):
            # O leitor le' a figura simples na linha como imagem do EditDoc: tem de virar isso.
            return trocar(doc, pos, posicao.imagem_de_objeto(obj))
        return trocar(doc, pos, posicao.objeto_com(obj, posicao.Mudanca(quebra="linha")))
    h = v = None
    if est.na_linha:
        # Passa a flutuar no lugar onde estava: relativo a' coluna e ao paragrafo.
        _n, ref, _d = g.referencia(pos)
        if retangulo_tw is not None:
            x, y = retangulo_tw[0], retangulo_tw[1]
            h = ("column", mf.deslocamento_para("h", "column", ref, x))
            v = ("paragraph", mf.deslocamento_para("v", "paragraph", ref, y))
    mud = posicao.Mudanca(quebra=quebra, h=h, v=v,
                          z=z_novo(docs_z or (doc,)) if est.na_linha else None)
    return trocar(doc, pos, posicao.objeto_com(obj, mud))


def aplicar_dialogo(doc, g, pos: int, escolha: dict, docs_z=(), retangulo_tw=None) -> int:
    """O que o dialogo "Posicao e tamanho" devolveu: quebra, posicao (rel, EMU) e tamanho
    (EMU). Um passo de desfazer para tudo."""
    quebra = escolha.get("quebra")
    final = pos
    mudou_quebra = False
    est = estado_em(doc, pos)
    atual = "linha" if eh_imagem_na_linha(doc, pos) else (est.quebra if est else None)
    if quebra is not None and quebra != atual:
        final = definir_quebra(doc, g, pos, quebra, docs_z, retangulo_tw)
        mudou_quebra = True
    tamanho = escolha.get("tamanho")
    if eh_imagem_na_linha(doc, final):
        if tamanho is not None:
            cf = formato_em(doc, final)
            fmt = cf.toImageFormat()
            from editdoc.modelo.unidades import EMU_POR_PX
            novo = QTextCharFormat(cf).toImageFormat()
            novo.setWidth(max(1.0, tamanho[0] / EMU_POR_PX))
            novo.setHeight(max(1.0, tamanho[1] / EMU_POR_PX))
            if abs(novo.width() - fmt.width()) > 0.01 or abs(novo.height() - fmt.height()) > 0.01:
                c = QTextCursor(doc)
                c.joinPreviousEditBlock() if mudou_quebra else c.beginEditBlock()
                c.setPosition(final)
                c.setPosition(final + 1, QTextCursor.MoveMode.KeepAnchor)
                c.setCharFormat(novo)
                c.endEditBlock()
        return final
    obj = objeto_em(doc, final)
    est = posicao.estado(obj.xml) if obj is not None else None
    if est is None:
        return final
    h = escolha.get("h") if not est.na_linha else None
    v = escolha.get("v") if not est.na_linha else None
    if h is None and v is None and tamanho is None:
        return final
    mud = posicao.Mudanca(h=h, v=v, tamanho=tamanho)
    novo = posicao.objeto_com(obj, mud)
    if novo.xml != obj.xml:
        final = trocar(doc, final, novo, juntar=mudou_quebra)
    return final


__all__ = ["mover", "trocar", "redimensionar_na_linha", "definir_quebra", "aplicar_dialogo",
           "objeto_em", "estado_em", "tem_posicao", "z_novo"]
