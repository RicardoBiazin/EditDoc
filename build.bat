@echo off
chcp 65001 >nul
setlocal

rem ===========================================================================
rem  build.bat            gera dist\EditWord\EditWord.exe  (one-dir, entregue em ZIP)
rem  build.bat umarquivo  gera dist\EditWord.exe            (portatil)
rem
rem  SEMPRE o python do .venv, nunca o `python` do PATH.
rem ===========================================================================

cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo.
    echo ERRO: nao encontrei "%PY%"
    echo.
    echo Monte o ambiente primeiro:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    echo.
    exit /b 1
)

"%PY%" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo ERRO: pyinstaller nao esta instalado NO VENV.
    echo     "%PY%" -m pip install -r requirements-dev.txt
    exit /b 1
)

rem -- 1. A suite roda ANTES de empacotar ---------------------------------------
echo.
echo === [1/5] Rodando a suite de testes ===
"%PY%" -u tests\rodar_todos.py
if errorlevel 1 (
    echo.
    echo BUILD ABORTADO: a suite falhou. Corrija antes de empacotar.
    exit /b 1
)

rem -- 2. Empacotar -------------------------------------------------------------
echo.
if /i "%~1"=="umarquivo" (
    echo === [2/5] Empacotando ONE-FILE ===
    echo     AVISO: o modo um-arquivo descompacta o pacote em %%TEMP%% a CADA
    echo     abertura. Use-o para pendrive; para uso diario, prefira o one-dir.
    set "EDITWORD_UM_ARQUIVO=1"
) else (
    echo === [2/5] Empacotando ONE-DIR ===
    set "EDITWORD_UM_ARQUIVO="
)

rem Uma instancia rodando segura os arquivos de dist\. O PyInstaller falharia no
rem meio, e o que sobra e' um dist pela metade. A checagem usa o codigo de saida
rem do PowerShell, e nao "tasklist | find": o find fica esperando o pipe quando o
rem build roda sem console anexado, e o build trava sem imprimir nada.
powershell -NoProfile -NonInteractive -Command "if (Get-Process EditWord -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo.
    echo BUILD ABORTADO: ha um EditWord.exe em execucao.
    echo Feche o programa e rode de novo.
    echo.
    exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

rem O __pycache__ tambem sai: um .pyc antigo pode ter a versao errada.
for %%p in (editword editword\interface tests ferramentas .) do @if exist "%%p\__pycache__" rmdir /s /q "%%p\__pycache__"

if exist dist (
    echo.
    echo BUILD ABORTADO: nao foi possivel apagar dist\ por completo.
    echo Algum programa esta com arquivos de la abertos ^(antivirus, Explorer^).
    exit /b 1
)

"%PY%" -m PyInstaller --noconfirm --clean EditWord.spec
if errorlevel 1 (
    echo.
    echo BUILD ABORTADO: o PyInstaller falhou.
    exit /b 1
)

rem -- 3. Autoverificacao do executavel -----------------------------------------
echo.
echo === [3/5] Autoverificacao do executavel gerado ===
set "EXE=dist\EditWord\EditWord.exe"
if /i "%~1"=="umarquivo" set "EXE=dist\EditWord.exe"

if not exist "%EXE%" (
    echo ERRO: "%EXE%" nao foi gerado.
    exit /b 1
)

"%EXE%" --autoverificacao
if errorlevel 1 (
    echo.
    echo BUILD ABORTADO: o executavel NAO passou na autoverificacao.
    echo Causa mais provavel: um modulo em `excludes` do EditWord.spec e' usado
    echo em tempo de execucao.
    exit /b 1
)

rem -- 4. Fumaca: o executavel ABRE a janela? ------------------------------------
echo.
echo === [4/5] Fumaca: o executavel abre a janela? ===
"%PY%" ferramentas\fumaca_exe.py "%EXE%"
if errorlevel 1 (
    echo.
    echo BUILD ABORTADO: o executavel nao abriu a janela.
    exit /b 1
)

rem -- 5. ZIP, so no one-dir ---------------------------------------------------
if /i not "%~1"=="umarquivo" (
    echo.
    echo === [5/5] Gerando o ZIP ===
    "%PY%" ferramentas\empacotar_zip.py
    if errorlevel 1 (
        echo.
        echo BUILD ABORTADO: o ZIP nao foi gerado.
        exit /b 1
    )
)

echo.
echo ============================================================
echo  BUILD OK
echo  Executavel: %EXE%
for %%F in ("%EXE%") do echo  Tamanho do .exe: %%~zF bytes
echo ============================================================
endlocal
