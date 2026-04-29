@echo off
REM ============================================================================
REM  GridAnalyzer — Build Portátil
REM  
REM  Este script gera o executável portátil em duas etapas:
REM    1. Compila a aplicação em modo --onedir (payload rápido)
REM    2. Empacota o payload dentro do launcher portátil
REM
REM  Resultado final: dist\GridAnalyzer_Portable.exe
REM ============================================================================

setlocal enabledelayedexpansion

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERRO] Nenhum ambiente virtual .venv encontrado.
    echo        Crie e ative a venv com Python 3.12 antes de buildar.
    pause
    exit /b 1
)

set "PYTHON_EXE=.venv\Scripts\python.exe"
set "PYTHON_ARGS=-m PyInstaller"

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║         GridAnalyzer — Build Portátil                       ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║  Etapa 1: Compilar aplicação (payload)                     ║
echo ║  Etapa 2: Empacotar no launcher portátil                   ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Navigate to project root (parent of portable/)
cd /d "%~dp0\.."

REM ── Etapa 1: Build do Payload ──────────────────────────────────────────────
echo [1/2] Compilando a aplicação (modo --onedir)...
echo       Isso pode levar vários minutos na primeira execução.
echo.

%PYTHON_EXE% %PYTHON_ARGS% --clean --noconfirm portable\build_portable.spec

if errorlevel 1 (
    echo.
    echo [ERRO] Falha na compilação do payload.
    echo        Verifique se o PyInstaller está instalado: pip install pyinstaller
    pause
    exit /b 1
)

echo.
echo [OK] Payload compilado com sucesso em dist\GridAnalyzer_payload\
echo.

REM ── Etapa 2: Build do Launcher ─────────────────────────────────────────────
echo [2/2] Empacotando no launcher portátil...
echo.

%PYTHON_EXE% %PYTHON_ARGS% --clean --noconfirm portable\launcher.spec

if errorlevel 1 (
    echo.
    echo [ERRO] Falha na compilação do launcher.
    pause
    exit /b 1
)

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║  BUILD CONCLUÍDO COM SUCESSO!                              ║
echo ║                                                             ║
echo ║  Executável: dist\GridAnalyzer_Portable.exe                ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Show file size
for %%F in (dist\GridAnalyzer_Portable.exe) do (
    set "size=%%~zF"
    set /a "sizeMB=!size! / 1048576"
    echo Tamanho: !sizeMB! MB
)

echo.
pause
