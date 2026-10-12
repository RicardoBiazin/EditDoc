<#
.SYNOPSIS
    Registra o EditDoc em "Abrir com" para as extensões que você escolher.

.DESCRIPTION
    Escreve APENAS em HKCU: nenhum privilégio de administrador é necessário, e
    nada fora do seu perfil é tocado.

    Usa OpenWithProgids, que ACRESCENTA o EditDoc à lista "Abrir com" da
    extensão SEM roubar o programa padrão. Abrir um .docx continua abrindo no que
    você já usava; o EditDoc passa a ser uma opção.

    O PROGRAMA PADRÃO NÃO SAI DAQUI, e não é limitação deste script. Desde o
    Windows 10 a escolha do programa padrão (a chave UserChoice de cada extensão)
    é protegida por um hash amarrado ao seu usuário, à extensão e ao horário:
    escrevê-la direto no registro é revertido pelo sistema. Para tornar o EditDoc
    padrão de uma extensão:

        Botão direito > Abrir com > Escolher outro aplicativo > Sempre

    ou Configurações > Aplicativos > Aplicativos padrão > por tipo de arquivo.

    Registra SOMENTE as extensões passadas como argumento. Não há lista embutida
    de "extensões que um editor deveria pegar" -- de propósito. Também não há
    item de menu de contexto para todos os arquivos: o EditDoc só aparece nas
    extensões pedidas.

.PARAMETER Extensoes
    As extensões, com ou sem ponto: .docx .dotx

.PARAMETER Exe
    Caminho do EditDoc.exe. Por padrão procura em dist\EditDoc\ e em dist\.

.PARAMETER TirarDaLista
    Nome de um executável a REMOVER da lista "Abrir com" das mesmas extensões,
    para trocar um editor por outro em vez de acumular os dois.
    Exemplo: -TirarDaLista TextForgeEdit.exe

.PARAMETER Remover
    Desfaz tudo o que este script criou, somente no seu perfil.

.PARAMETER Simular
    Mostra o que seria feito, sem escrever nada no registro.

.EXAMPLE
    .\associar.ps1 .docx

.EXAMPLE
    .\associar.ps1 .docx .dotx -Simular

.EXAMPLE
    .\associar.ps1 .docx -TirarDaLista TextForgeEdit.exe

.EXAMPLE
    .\associar.ps1 -Remover

.NOTES
    ESTE ARQUIVO PRECISA ESTAR EM UTF-8 COM BOM. O PowerShell 5.1 lê arquivo sem
    BOM como ANSI, e todos os acentos das mensagens viram lixo.

    SupportedTypes recebe SOMENTE as extensões pedidas, e não ".*": com ".*" o
    EditDoc apareceria em "Escolher outro aplicativo" de qualquer arquivo, que
    ele não abre.

    O executável fica em dist\, que o build.bat apaga e refaz. O caminho é o
    mesmo depois de reconstruir, então a associação continua valendo; mas se o
    executável sair do lugar, rode este script de novo.
#>

# `PositionalBinding = $false` NÃO é enfeite.
#
# Um parâmetro com `ValueFromRemainingArguments` fica DE FORA da ligação
# posicional. Sem esta linha, `$Exe` vira o primeiro posicional e um
# `.\associar.ps1 .docx .dotx` entende `.docx` como o CAMINHO DO EXECUTÁVEL --
# e o script responde "não encontrei o EditDoc.exe" sem pista de por quê. Com
# ela, só o que tem posição explícita liga por posição, e o resto cai em
# `$Extensoes`.
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Extensoes,
    [string] $Exe = "",
    [string] $TirarDaLista = "",
    [switch] $Remover,
    [switch] $Simular
)

$ErrorActionPreference = "Stop"
$ProgID = "EditDoc.Documento"
$AppExe = "EditDoc.exe"
# `$PSScriptRoot` é o jeito certo desde o PowerShell 3.0. O
# `$MyInvocation.MyCommand.Path` vem VAZIO em várias formas de invocação
# (ponto-e-vírgula, `&`, chamada de outro processo).
$Raiz = $PSScriptRoot
if (-not $Raiz) { $Raiz = Split-Path -Parent $MyInvocation.MyCommand.Definition }
if (-not $Raiz) { $Raiz = (Get-Location).Path }
$FileExts = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"

function Escrever($mensagem, $cor = "Gray") {
    Write-Host $mensagem -ForegroundColor $cor
}

# `-LiteralPath` EM TODA CHAMADA. Sem ele, um caminho com `[` ou `*` vira
# padrão de busca: o script varre o registro atrás de um casamento, parece
# travado, e a chave nunca é criada.
function Definir-Chave($caminho, $nome, $valor) {
    $rotulo = if ($nome) { $nome } else { "(padrão)" }
    if ($Simular) {
        Escrever "  [simulação] $caminho :: $rotulo = $valor"
        return
    }
    if (-not (Test-Path -LiteralPath $caminho)) {
        # `New-Item` não aceita -LiteralPath no provedor de registro. A saída é a
        # API do .NET, que trata o caminho como texto puro.
        $sub = $caminho.Replace("HKCU:\", "")
        [void][Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($sub)
    }
    if ($nome) {
        New-ItemProperty -LiteralPath $caminho -Name $nome -Value $valor -PropertyType String -Force | Out-Null
    } else {
        Set-ItemProperty -LiteralPath $caminho -Name "(default)" -Value $valor -Force
    }
}

function Remover-Chave($caminho) {
    if (-not (Test-Path -LiteralPath $caminho)) { return }
    if ($Simular) { Escrever "  [simulação] remover $caminho"; return }
    Remove-Item -LiteralPath $caminho -Recurse -Force -ErrorAction SilentlyContinue
}

function Atualizar-Explorer {
    # Sem isto o Explorer só mostra a mudança depois de reiniciar.
    # SHCNE_ASSOCCHANGED = 0x08000000, SHCNF_IDLIST = 0.
    if ($Simular) { Escrever "  [simulação] SHChangeNotify(ASSOCCHANGED)"; return }
    try {
        Add-Type -Namespace EditDocShell -Name Notificar -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("shell32.dll")]
public static extern void SHChangeNotify(int eventId, uint flags, System.IntPtr a, System.IntPtr b);
'@ -ErrorAction Stop
        [EditDocShell.Notificar]::SHChangeNotify(0x08000000, 0, [System.IntPtr]::Zero, [System.IntPtr]::Zero)
    } catch {
        Escrever "  (não foi possível avisar o Explorer: $($_.Exception.Message))" "DarkYellow"
    }
}

function Tirar-Do-OpenWithList($ext, $alvoExe) {
    <#
        Remove um programa da lista "Abrir com" que o EXPLORER mantém, em
        FileExts\<ext>\OpenWithList. Não é a mesma coisa que OpenWithProgids: esta
        é a lista de uso recente que o Explorer preenche sozinho quando você
        escolhe um programa pelo diálogo.

        O CUIDADO QUE IMPORTA: os valores são letras (a, b, c...) e o `MRUList` é
        uma string com essas letras em ordem de uso. Apagar o valor sem tirar a
        letra do MRUList deixa o Explorer apontando para uma entrada que não
        existe mais.
    #>
    $chave = "$FileExts\$ext\OpenWithList"
    if (-not (Test-Path -LiteralPath $chave)) { return $false }

    $prop = Get-ItemProperty -LiteralPath $chave -ErrorAction SilentlyContinue
    if (-not $prop) { return $false }

    $letras = $prop.PSObject.Properties |
        Where-Object { $_.Name -notlike "PS*" -and $_.Name -ne "MRUList" -and
                       $_.Value -eq $alvoExe } |
        ForEach-Object { $_.Name }
    if (-not $letras) { return $false }

    if ($Simular) {
        Escrever "  [simulação] $ext : tirar $alvoExe (valor $($letras -join ', '))"
        return $true
    }

    foreach ($letra in $letras) {
        Remove-ItemProperty -LiteralPath $chave -Name $letra -Force -ErrorAction SilentlyContinue
    }
    $mru = $prop.MRUList
    if ($mru) {
        $novo = ($mru.ToCharArray() | Where-Object { $letras -notcontains "$_" }) -join ""
        Set-ItemProperty -LiteralPath $chave -Name "MRUList" -Value $novo -Force
    }
    return $true
}

# ---------------------------------------------------------------------------
# Remover
# ---------------------------------------------------------------------------

if ($Remover) {
    Escrever "Removendo o registro do EditDoc (somente HKCU)..." "Cyan"

    Remover-Chave "HKCU:\Software\Classes\$ProgID"
    Remover-Chave "HKCU:\Software\Classes\Applications\$AppExe"

    # Tira o ProgID do OpenWithProgids de TODA extensão que o tenha. Varrer é
    # obrigatório: quem remove normalmente não lembra quais extensões registrou.
    $limpas = 0
    $extensoesNoRegistro = Get-ChildItem -LiteralPath "HKCU:\Software\Classes" -ErrorAction SilentlyContinue |
        Where-Object { $_.PSChildName -like ".*" }
    foreach ($entrada in $extensoesNoRegistro) {
        $alvo = "HKCU:\Software\Classes\$($entrada.PSChildName)\OpenWithProgids"
        if (Test-Path -LiteralPath $alvo) {
            $prop = Get-ItemProperty -LiteralPath $alvo -ErrorAction SilentlyContinue
            if ($prop -and ($prop.PSObject.Properties.Name -contains $ProgID)) {
                if ($Simular) {
                    Escrever "  [simulação] tirar $ProgID de $($entrada.PSChildName)"
                } else {
                    Remove-ItemProperty -LiteralPath $alvo -Name $ProgID -Force -ErrorAction SilentlyContinue
                }
                $limpas++
            }
        }
    }

    Atualizar-Explorer
    Escrever "Pronto. $limpas extensão(ões) desassociada(s)." "Green"
    Escrever "O programa padrão de cada extensão NÃO foi alterado (nunca foi tocado)."
    if ($Simular) { Escrever "Simulação concluída: nada foi escrito." "Yellow" }
    exit 0
}

# ---------------------------------------------------------------------------
# Localizar o executável
# ---------------------------------------------------------------------------

if (-not $Exe) {
    $candidatos = @(
        (Join-Path $Raiz "dist\EditDoc\$AppExe"),
        (Join-Path $Raiz "dist\$AppExe"),
        (Join-Path $Raiz $AppExe)
    )
    $Exe = $candidatos | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

if (-not $Exe -or -not (Test-Path -LiteralPath $Exe)) {
    Escrever "ERRO: não encontrei o EditDoc.exe." "Red"
    Escrever ""
    Escrever "Gere o executável primeiro:"
    Escrever "    .\build.bat"
    Escrever "ou informe o caminho:"
    Escrever "    .\associar.ps1 .docx -Exe C:\caminho\EditDoc.exe"
    exit 1
}
$Exe = (Resolve-Path -LiteralPath $Exe).Path

# O ícone do TIPO DE ARQUIVO é diferente do ícone do programa. Sem ele, um .docx
# associado aparece no Explorer com o símbolo do EDITOR. Procura ao lado do
# executável (build em pasta, dentro de `_internal`) e depois na árvore de fontes.
# Não achando, cai no ícone do próprio .exe.
$PastaDoExe = Split-Path -Parent $Exe
$IconeDoArquivo = @(
    (Join-Path $PastaDoExe "_internal\editdoc\recursos\icone_arquivo.ico"),
    (Join-Path $PastaDoExe "editdoc\recursos\icone_arquivo.ico"),
    (Join-Path $Raiz "editdoc\recursos\icone_arquivo.ico")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if ($IconeDoArquivo) {
    $IconeDoArquivo = (Resolve-Path -LiteralPath $IconeDoArquivo).Path
    $ExpressaoDoIcone = "`"$IconeDoArquivo`""
} else {
    $ExpressaoDoIcone = "`"$Exe`",0"
}

if (-not $Extensoes -or $Extensoes.Count -eq 0) {
    Escrever "Nenhuma extensão informada." "Yellow"
    Escrever ""
    Escrever "Uso:  .\associar.ps1 .docx .dotx [-Simular] [-TirarDaLista outro.exe]"
    Escrever "      .\associar.ps1 -Remover"
    Escrever ""
    Escrever "De propósito não há lista embutida: registra SOMENTE o que você pedir."
    exit 1
}

# Valida as extensões ANTES de escrever qualquer coisa.
$normalizadas = @()
foreach ($bruta in $Extensoes) {
    $ext = $bruta.Trim()
    if (-not $ext) { continue }
    if (-not $ext.StartsWith(".")) { $ext = ".$ext" }
    $ext = $ext.ToLower()
    if ($ext -notmatch '^\.[a-z0-9_\-\.]{1,20}$') {
        Escrever "   ignorada (não parece uma extensão): $bruta" "DarkYellow"
        continue
    }
    $normalizadas += $ext
}
$normalizadas = @($normalizadas | Select-Object -Unique)
if ($normalizadas.Count -eq 0) {
    Escrever "Nenhuma extensão válida. Nada foi alterado." "Red"
    exit 1
}

# ---------------------------------------------------------------------------
# Registrar
# ---------------------------------------------------------------------------

Escrever "EditDoc: $Exe" "Cyan"
if ($Simular) { Escrever "MODO SIMULAÇÃO: nada será escrito no registro." "Yellow" }
Escrever ""

$comando = "`"$Exe`" `"%1`""

if ($IconeDoArquivo) {
    Escrever "Ícone dos arquivos: $IconeDoArquivo" "Cyan"
} else {
    Escrever "Ícone dos arquivos: o do próprio executável (icone_arquivo.ico não encontrado)" "DarkYellow"
}
Escrever ""

# 1. O ProgID: o "tipo de arquivo" do EditDoc.
Escrever "1. Tipo de arquivo $ProgID"
Definir-Chave "HKCU:\Software\Classes\$ProgID" $null "Arquivo aberto no EditDoc"
Definir-Chave "HKCU:\Software\Classes\$ProgID\DefaultIcon" $null $ExpressaoDoIcone
Definir-Chave "HKCU:\Software\Classes\$ProgID\shell\open\command" $null $comando

# 2. O registro do aplicativo, que faz o nome aparecer no "Abrir com".
Escrever "2. Applications\$AppExe"
Definir-Chave "HKCU:\Software\Classes\Applications\$AppExe" "FriendlyAppName" "EditDoc"
Definir-Chave "HKCU:\Software\Classes\Applications\$AppExe\shell\open\command" $null $comando
foreach ($ext in $normalizadas) {
    Definir-Chave "HKCU:\Software\Classes\Applications\$AppExe\SupportedTypes" $ext ""
}

# 3. As extensões pedidas, via OpenWithProgids: ACRESCENTA sem roubar o padrão.
Escrever "3. Extensões"
foreach ($ext in $normalizadas) {
    Definir-Chave "HKCU:\Software\Classes\$ext\OpenWithProgids" $ProgID ""
    Escrever "   $ext  ->  adicionado à lista 'Abrir com'" "Green"
}

# 4. Tirar outro programa da lista, quando pedido.
if ($TirarDaLista) {
    $outro = $TirarDaLista.Trim()
    if (-not $outro.ToLower().EndsWith(".exe")) { $outro = "$outro.exe" }
    Escrever "4. Tirando $outro da lista 'Abrir com'"

    $tiradas = 0
    foreach ($ext in $normalizadas) {
        if (Tirar-Do-OpenWithList $ext $outro) {
            Escrever "   $ext  ->  $outro removido" "Green"
            $tiradas++
        }
    }
    # E o ProgID dele, se estiver registrado nessas extensões.
    $progOutro = [System.IO.Path]::GetFileNameWithoutExtension($outro) + ".arquivo"
    foreach ($ext in $normalizadas) {
        $alvo = "HKCU:\Software\Classes\$ext\OpenWithProgids"
        if (Test-Path -LiteralPath $alvo) {
            $prop = Get-ItemProperty -LiteralPath $alvo -ErrorAction SilentlyContinue
            if ($prop -and ($prop.PSObject.Properties.Name -contains $progOutro)) {
                if ($Simular) {
                    Escrever "   [simulação] $ext : tirar o ProgID $progOutro"
                } else {
                    Remove-ItemProperty -LiteralPath $alvo -Name $progOutro -Force -ErrorAction SilentlyContinue
                }
                $tiradas++
            }
        }
    }
    if ($tiradas -eq 0) {
        Escrever "   (nada a remover: $outro não estava listado nessas extensões)"
    }
}

Atualizar-Explorer

Escrever ""
if ($Simular) {
    Escrever "Simulação concluída: nada foi escrito no registro." "Yellow"
} else {
    Escrever "Pronto." "Green"
}
Escrever ""
Escrever "O programa PADRÃO de cada extensão NÃO foi alterado, e não dá para alterá-lo"
Escrever "por script: desde o Windows 10 a escolha é protegida por um hash amarrado ao"
Escrever "seu usuário. Para tornar o EditDoc padrão de uma extensão:"
Escrever ""
Escrever "    Botão direito > Abrir com > Escolher outro aplicativo > Sempre"
Escrever ""
Escrever "Para desfazer:  .\associar.ps1 -Remover"
