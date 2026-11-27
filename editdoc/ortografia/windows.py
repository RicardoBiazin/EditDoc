"""Corretor pela API de verificacao ortografica do Windows (0.1.36): ISpellCheckerFactory.

Por ctypes puro, sem comtypes nem dicionario proprio: o Windows 8 ou mais novo traz a API, os
idiomas que o usuario instalou (Configuracoes > Hora e idioma) e o dicionario pessoal dele
(%APPDATA%\\Microsoft\\Spelling). Nada daqui sai do computador.

As interfaces (vtable, depois dos tres metodos do IUnknown):

- ISpellCheckerFactory: 3 get_SupportedLanguages(IEnumString**), 4 IsSupported(LPCWSTR, BOOL*),
  5 CreateSpellChecker(LPCWSTR, ISpellChecker**);
- ISpellChecker: 4 Check(LPCWSTR, IEnumSpellingError**), 5 Suggest(LPCWSTR, IEnumString**),
  6 Add(LPCWSTR);
- IEnumSpellingError: 3 Next(ISpellingError**) (S_OK com item, S_FALSE no fim);
- ISpellingError: 3 get_StartIndex, 4 get_Length, 5 get_CorrectiveAction, 6 get_Replacement;
- IEnumString: 3 Next(celt, LPOLESTR*, ULONG*).

Os indices que o Windows devolve sao em UTF-16: num texto com caractere fora do plano basico
(emoji) o indice do Python e' outro, e `_para_python` converte. Tudo (a fabrica, cada corretor
de idioma, as enumeracoes) so' pode ser usado na thread que o criou: o EditDoc chama da thread
da interface, a mesma em que o Qt iniciou o COM.
"""

from __future__ import annotations

import atexit
import ctypes
import re
import uuid
import weakref
from ctypes import POINTER, byref, c_int, c_long, c_ulong, c_void_p, c_wchar_p

from editdoc.ortografia import Corretor, Erro, ErroDoCorretor

_CLSID_FABRICA = "7AB36653-1796-484B-BDFA-E74F1DB7C1DC"
_IID_FABRICA = "8E018A9D-2415-4677-BF08-794EA61F94BB"
_CLSCTX_INPROC_SERVER = 1
_COINIT_APARTMENTTHREADED = 2
#: CORRECTIVE_ACTION do ISpellingError.
_ACAO_SUGERIR, _ACAO_SUBSTITUIR, _ACAO_EXCLUIR = 1, 2, 3
_ACOES = {_ACAO_SUGERIR: "sugerir", _ACAO_SUBSTITUIR: "substituir", _ACAO_EXCLUIR: "excluir"}


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16),
                ("d", ctypes.c_ubyte * 8)]


def _guid(texto: str) -> _GUID:
    u = uuid.UUID(texto)
    g = _GUID()
    g.a, g.b, g.c = u.time_low, u.time_mid, u.time_hi_version
    for i, byte in enumerate(u.bytes[8:]):
        g.d[i] = byte
    return g


_prototipos: dict = {}


def _chamada(ponteiro: c_void_p, indice: int, *tipos):
    """A funcao `indice` da vtable do objeto COM, como chamavel que ja' leva o objeto."""
    chave = tipos
    proto = _prototipos.get(chave)
    if proto is None:
        proto = ctypes.WINFUNCTYPE(c_long, c_void_p, *tipos)
        _prototipos[chave] = proto
    tabela = ctypes.cast(ctypes.cast(ponteiro, POINTER(c_void_p))[0], POINTER(c_void_p))
    funcao = proto(tabela[indice])

    def chamar(*args) -> int:
        hr = funcao(ponteiro, *args)
        if hr < 0:
            raise ErroDoCorretor(f"chamada {indice} falhou (HRESULT 0x{hr & 0xFFFFFFFF:08X})")
        return hr
    return chamar


def _liberar(ponteiro: c_void_p) -> None:
    if not ponteiro or not ponteiro.value:
        return
    try:
        tabela = ctypes.cast(ctypes.cast(ponteiro, POINTER(c_void_p))[0], POINTER(c_void_p))
        ctypes.WINFUNCTYPE(c_ulong, c_void_p)(tabela[2])(ponteiro)
    except OSError:
        pass


def _livre(ole32, valor: int | None) -> None:
    if valor:
        ole32.CoTaskMemFree(c_void_p(valor))


def _textos(ole32, enumeracao: c_void_p, limite: int = 64) -> list[str]:
    """Os textos de um IEnumString (e libera a enumeracao)."""
    saida: list[str] = []
    try:
        while len(saida) < limite:
            item, buscados = c_void_p(), c_ulong()
            hr = _chamada(enumeracao, 3, c_ulong, POINTER(c_void_p), POINTER(c_ulong))(
                1, byref(item), byref(buscados))
            if hr != 0 or not buscados.value:
                break
            try:
                saida.append(ctypes.wstring_at(item.value))
            finally:
                _livre(ole32, item.value)
    finally:
        _liberar(enumeracao)
    return saida


#: Substituto UTF-16 sem par (de 0xD800 a 0xDFFF), escrito por codigo para o arquivo ficar em ASCII.
_SUBSTITUTOS_SOLTOS = re.compile("[" + chr(0xD800) + "-" + chr(0xDFFF) + "]")


def _seguro(texto: str) -> str:
    """O texto como o corretor pode receber (0.1.39): sem NUL e sem substituto UTF-16 solto (um
    caractere da area de transferencia ou do arquivo que o Python guarda como surrogate). Cada um
    vira um espaco, de modo que as posicoes nao mudam. O `encode` estrito da conversao de
    indices estourava UnicodeEncodeError, e a verificacao era desligada no documento inteiro."""
    return _SUBSTITUTOS_SOLTOS.sub(" ", texto.replace("\0", " "))


def _para_python(texto: str):
    """Funcao que leva um indice UTF-16 do Windows ao indice do Python (identidade se o texto
    so' tem caracteres do plano basico)."""
    if len(texto.encode("utf-16-le")) // 2 == len(texto):
        return lambda i: i
    posicoes: list[int] = []  # indice UTF-16 -> indice Python
    for k, c in enumerate(texto):
        posicoes.append(k)
        if ord(c) > 0xFFFF:
            posicoes.append(k)
    posicoes.append(len(texto))
    return lambda i: posicoes[min(max(i, 0), len(posicoes) - 1)]


#: Os corretores abertos: soltos no fim do programa, antes de o Qt encerrar o COM.
_vivos: "weakref.WeakSet[CorretorWindows]" = weakref.WeakSet()


def _fechar_todos() -> None:
    for c in list(_vivos):
        try:
            c.fechar()
        except Exception:  # noqa: BLE001 - fim de processo
            pass


atexit.register(_fechar_todos)


class CorretorWindows(Corretor):
    nome = "Windows"

    def __init__(self) -> None:
        _vivos.add(self)
        self._fabrica = c_void_p()
        self._verificadores: dict[str, c_void_p] = {}
        self._ole32 = ctypes.OleDLL("ole32")
        self._ole32.CoTaskMemFree.argtypes = [c_void_p]
        self._ole32.CoTaskMemFree.restype = None
        # O Qt ja' iniciou o COM na thread da interface (S_FALSE aqui); fora dela, inicia.
        self._ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        clsid, iid = _guid(_CLSID_FABRICA), _guid(_IID_FABRICA)
        hr = self._ole32.CoCreateInstance(byref(clsid), None, _CLSCTX_INPROC_SERVER, byref(iid),
                                          byref(self._fabrica))
        if hr < 0 or not self._fabrica.value:
            raise ErroDoCorretor(f"fabrica de corretores ausente (HRESULT 0x{hr & 0xFFFFFFFF:08X})")
        self._suportados: dict[str, bool] = {}
        self._lista: list[str] | None = None

    # -- idiomas ----------------------------------------------------------------------------
    def _aberta(self) -> None:
        if not self._fabrica.value:
            raise ErroDoCorretor("corretor fechado")

    def idiomas(self) -> list[str]:
        self._aberta()
        if self._lista is None:
            enumeracao = c_void_p()
            _chamada(self._fabrica, 3, POINTER(c_void_p))(byref(enumeracao))
            self._lista = _textos(self._ole32, enumeracao)
        return list(self._lista)

    def suporta(self, idioma: str) -> bool:
        self._aberta()
        achado = self._suportados.get(idioma)
        if achado is None:
            suportado = c_int()
            _chamada(self._fabrica, 4, c_wchar_p, POINTER(c_int))(idioma, byref(suportado))
            achado = self._suportados[idioma] = bool(suportado.value)
        return achado

    def _verificador(self, idioma: str) -> c_void_p:
        self._aberta()
        v = self._verificadores.get(idioma)
        if v is None:
            if not self.suporta(idioma):
                raise ErroDoCorretor(f"idioma sem dicionario: {idioma}")
            v = c_void_p()
            _chamada(self._fabrica, 5, c_wchar_p, POINTER(c_void_p))(idioma, byref(v))
            self._verificadores[idioma] = v
        return v

    # -- verificar --------------------------------------------------------------------------
    def verificar(self, texto: str, idioma: str) -> list[Erro]:
        texto = _seguro(texto)
        if not texto.strip():
            return []
        verificador = self._verificador(idioma)
        enumeracao = c_void_p()
        _chamada(verificador, 4, c_wchar_p, POINTER(c_void_p))(texto, byref(enumeracao))
        indice = _para_python(texto)
        erros: list[Erro] = []
        try:
            while len(erros) < 5000:
                item = c_void_p()
                if _chamada(enumeracao, 3, POINTER(c_void_p))(byref(item)) != 0 or not item.value:
                    break
                try:
                    ini, tam, acao = c_ulong(), c_ulong(), c_int()
                    _chamada(item, 3, POINTER(c_ulong))(byref(ini))
                    _chamada(item, 4, POINTER(c_ulong))(byref(tam))
                    _chamada(item, 5, POINTER(c_int))(byref(acao))
                    troca = ""
                    if acao.value == _ACAO_SUBSTITUIR:
                        rep = c_void_p()
                        _chamada(item, 6, POINTER(c_void_p))(byref(rep))
                        try:
                            troca = ctypes.wstring_at(rep.value) if rep.value else ""
                        finally:
                            _livre(self._ole32, rep.value)
                    a, b = indice(ini.value), indice(ini.value + tam.value)
                    if b > a:
                        erros.append(Erro(a, b, _ACOES.get(acao.value, "sugerir"), troca))
                finally:
                    _liberar(item)
        finally:
            _liberar(enumeracao)
        return erros

    def sugerir(self, palavra: str, idioma: str) -> list[str]:
        verificador = self._verificador(idioma)
        enumeracao = c_void_p()
        _chamada(verificador, 5, c_wchar_p, POINTER(c_void_p))(_seguro(palavra),
                                                               byref(enumeracao))
        return _textos(self._ole32, enumeracao)

    def adicionar(self, palavra: str, idioma: str) -> None:
        _chamada(self._verificador(idioma), 6, c_wchar_p)(_seguro(palavra))

    # -- fim --------------------------------------------------------------------------------
    def fechar(self) -> None:
        for v in self._verificadores.values():
            _liberar(v)
        self._verificadores.clear()
        _liberar(self._fabrica)
        self._fabrica = c_void_p()

    def __del__(self) -> None:
        try:
            self.fechar()
        except Exception:  # noqa: BLE001 - destrutor
            pass
