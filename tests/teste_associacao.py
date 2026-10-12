"""associar.ps1: o texto do script (BOM, sem UserChoice, so' HKCU) e uma execucao em -Simular.

O checador de texto e' funcao pura de bytes (`achados`): o teste roda contra o
arquivo real e contra copias sabotadas, e as sabotagens TEM de ser acusadas.

A execucao usa SOMENTE -Simular. Nunca roda o script para escrever: o teste
ainda foto'grafa as chaves de HKCU antes e depois, e exige que nada mude.
"""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import winreg

from ajudantes import RAIZ, checa, checa_igual, pasta_temporaria, resumir, secao

SCRIPT = RAIZ / "associar.ps1"
BOM = b"\xef\xbb\xbf"
POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                          "System32", "WindowsPowerShell", "v1.0", "powershell.exe")

#: Chaves que o script escreveria, em HKCU. A foto antes/depois prova que -Simular nao escreve.
CAMINHOS_DE_REGISTRO = [
    r"Software\Classes\EditDoc.Documento",
    r"Software\Classes\EditDoc.Documento\shell\open\command",
    r"Software\Classes\Applications\EditDoc.exe",
    r"Software\Classes\.docx\OpenWithProgids",
    r"Software\Classes\.txt\OpenWithProgids",
]

#: Textos que TEM de estar no codigo (sem comentario).
OBRIGATORIOS_NO_CODIGO = [
    "OpenWithProgids",
    "EditDoc.Documento",
    "PositionalBinding = $false",
    "-LiteralPath",
    "FriendlyAppName",
    "SHChangeNotify",
]

#: Parametros exatos do param block (espacos normalizados antes da busca).
PARAMETROS_EXATOS = [
    "[CmdletBinding(PositionalBinding = $false)]",
    "[Parameter(ValueFromRemainingArguments = $true)]",
    "[string[]] $Extensoes",
    '[string] $Exe = ""',
    '[string] $TirarDaLista = ""',
    "[switch] $Remover",
    "[switch] $Simular",
]

#: Switches que o usuario digita: aparecem no texto (uso e exemplos).
OBRIGATORIOS_NO_TEXTO = ["-Simular", "-Remover", "-TirarDaLista"]

#: Cmdlets que tocam o registro: cada linha de codigo que os usa precisa de -LiteralPath.
CMDLETS_DE_REGISTRO = re.compile(
    r"\b(Test-Path|Get-ItemProperty|Set-ItemProperty|New-ItemProperty|"
    r"Remove-ItemProperty|Remove-Item|Get-ChildItem)\b")


def sem_comentarios(texto: str) -> str:
    """Só o que roda: tira os blocos <# #> e o comentario de linha."""
    sem_blocos = re.sub(r"<#.*?#>", "", texto, flags=re.S)
    return "\n".join(re.sub(r"(^|\s)#.*$", "", linha) for linha in sem_blocos.splitlines())


def achados(dados: bytes) -> list[str]:
    """O que esta errado no associar.ps1. Lista vazia = passa. Funcao pura, sem disco."""
    problemas: list[str] = []
    if not dados.startswith(BOM):
        problemas.append("sem BOM UTF-8 (EF BB BF): o PowerShell 5.1 le como ANSI")
    try:
        texto = dados.decode("utf-8-sig")
    except UnicodeDecodeError as erro:
        return problemas + [f"nao e' UTF-8: {erro}"]

    codigo = sem_comentarios(texto)
    if "UserChoice" in codigo:
        problemas.append("UserChoice fora de comentario: o programa padrao nao pode ser escrito")
    if "HKLM" in texto:
        problemas.append("HKLM no arquivo: o script escreve so' em HKCU")
    if "*\\shell" in codigo:
        problemas.append("item de menu de contexto para todos os arquivos (*\\shell)")
    for trecho in OBRIGATORIOS_NO_CODIGO:
        if trecho not in codigo:
            problemas.append(f"falta no codigo: {trecho}")
    for trecho in OBRIGATORIOS_NO_TEXTO:
        if trecho not in texto:
            problemas.append(f"falta no texto: {trecho}")
    for trecho in PARAMETROS_EXATOS:
        if trecho not in re.sub(r"\s+", " ", codigo):
            problemas.append(f"param block fora do exato: {trecho}")
    for numero, linha in enumerate(codigo.splitlines(), 1):
        if CMDLETS_DE_REGISTRO.search(linha) and "-LiteralPath" not in linha:
            problemas.append(f"linha {numero} usa cmdlet de registro sem -LiteralPath")
    return problemas


def testar_texto() -> None:
    secao("texto: BOM, sem UserChoice no codigo, so' HKCU, -LiteralPath em todo cmdlet")
    dados = SCRIPT.read_bytes()
    checa(dados.startswith(BOM), "o arquivo comeca com o BOM EF BB BF")
    checa(dados.count(b"\n") == dados.count(b"\r\n"),
          "todas as quebras de linha sao CRLF (o .ps1 do repo e' CRLF)")
    texto = dados.decode("utf-8-sig")
    codigo = sem_comentarios(texto)
    checa("UserChoice" not in codigo, "nenhuma linha NAO comentada contem UserChoice")
    checa("UserChoice" in texto, "o aviso sobre UserChoice existe, em comentario explicativo")
    checa("HKLM" not in texto, "nada de HKLM em nenhum lugar do arquivo")
    checa("*\\shell" not in codigo, "nenhum item de menu de contexto para todos os arquivos")
    checa_igual(achados(dados), [], "associar.ps1 passa no checador inteiro")


def testar_checador() -> None:
    secao("sabotagem: o checador ACUSA cada defeito proposital")
    real = SCRIPT.read_bytes()

    sabotagens = {
        "UserChoice escrito no codigo":
            real + b'\r\nDefinir-Chave "HKCU:\\Software\\Classes\\.docx\\UserChoice" "ProgId" "x"\r\n',
        "sem BOM":
            real[len(BOM):],
        "HKLM no arquivo":
            real + b"\r\n# nota\r\nGet-Item HKLM:\\SOFTWARE\r\n",
        "cmdlet de registro sem -LiteralPath":
            real.replace(b"Test-Path -LiteralPath $caminho", b"Test-Path $caminho", 1),
        "menu de contexto para todos os arquivos":
            real + b'\r\nDefinir-Chave "HKCU:\\Software\\Classes\\*\\shell\\EditDoc" $null "x"\r\n',
        "sem -Simular em lugar nenhum":
            real.replace(b"-Simular", b"-Simul"),
    }
    for nome, sabotado in sabotagens.items():
        checa(sabotado != real, f"a sabotagem '{nome}' de fato mudou o arquivo")
        problemas = achados(sabotado)
        checa(len(problemas) > 0,
              f"'{nome}' e' ACUSADO: {problemas[0] if problemas else 'NAO foi acusado'}")

    checa_igual(achados(real + b"\r\n# nota: UserChoice so' em comentario\r\n"), [],
                "um UserChoice so' em comentario NAO e' acusado (o checador ignora comentario)")


def foto_do_registro() -> dict:
    """Existencia e nomes de valor das chaves que o script escreveria, em HKCU."""
    foto: dict = {}
    for caminho in CAMINHOS_DE_REGISTRO:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, caminho) as chave:
                nomes: list[str] = []
                indice = 0
                while True:
                    try:
                        nomes.append(winreg.EnumValue(chave, indice)[0])
                    except OSError:
                        break
                    indice += 1
                foto[caminho] = sorted(nomes)
        except FileNotFoundError:
            foto[caminho] = None
    return foto


def executar(*argumentos: str) -> tuple[int, str]:
    """Roda o script no PowerShell 5.1. Devolve (codigo de saida, saida em texto)."""
    proc = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *argumentos],
        capture_output=True, timeout=120)
    return proc.returncode, _decodificar(proc.stdout)


def _decodificar(bruto: bytes) -> str:
    """A saida do PowerShell segue o codepage do console: UTF-8 quando o build roda
    'chcp 65001', e a tabela OEM no resto. Tenta UTF-8 primeiro e cai para a OEM."""
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode(f"cp{ctypes.windll.kernel32.GetOEMCP()}", errors="replace")


def testar_execucao() -> None:
    secao("execucao com -Simular: mostra o que faria e nao escreve nada no registro")
    antes = foto_do_registro()
    with pasta_temporaria() as pasta:
        fake = pasta / "fake" / "EditDoc.exe"
        fake.parent.mkdir()
        fake.write_bytes(b"")

        codigo, texto = executar("-Exe", str(fake), "-Simular", ".docx")
        checa_igual(codigo, 0, "-Simular com um exe e uma extensao sai com 0")
        checa("MODO SIMULAÇÃO" in texto and "Simulação concluída" in texto,
              "a saida avisa que e' simulacao, com acentos")
        checa("EditDoc.Documento" in texto and "OpenWithProgids" in texto,
              "a saida lista as chaves que seriam criadas")

        codigo, texto = executar("-Exe", str(fake), "-Simular", "-TirarDaLista", "TextForgeEdit.exe", ".docx")
        checa_igual(codigo, 0, "-TirarDaLista em simulacao sai com 0")
        checa("TextForgeEdit.exe" in texto and "Simulação concluída" in texto,
              "a simulacao de -TirarDaLista aparece na saida")

        codigo, texto = executar("-Remover", "-Simular")
        checa_igual(codigo, 0, "-Remover -Simular sai com 0")
        checa("Simulação concluída" in texto, "-Remover em simulacao avisa que nao escreveu")

        codigo, texto = executar("-Exe", r"C:\nao\existe\EditDoc.exe", "-Simular", ".docx")
        checa_igual(codigo, 1, "exe inexistente sai com 1")
        checa("não encontrei o EditDoc.exe" in texto,
              "e a mensagem diz, em portugues, que nao achou o executavel")

    # Um executavel que EXISTE, para a checagem de uso nao depender de o build ter
    # rodado: no CI nao ha EditDoc.exe, e o script para na checagem do executavel
    # antes de chegar na mensagem de uso.
    cmd_existente = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
    codigo, texto = executar("-Exe", cmd_existente)
    checa_igual(codigo, 1, "sem argumentos sai com 1")
    checa("Uso:" in texto and "-Simular" in texto,
          "sem argumentos, o script diz como usar")

    checa_igual(foto_do_registro(), antes,
                "o registro esta IDENTICO antes e depois de todas as chamadas com -Simular")


def main() -> int:
    testar_texto()
    testar_checador()
    testar_execucao()
    return resumir()


if __name__ == "__main__":
    raise SystemExit(main())
