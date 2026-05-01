@echo off
REM ============================================================================
REM  GridAnalyzer — Portable Build
REM  
REM  This script generates the portable executable in two steps:
REM    1. Compiles the application in --onedir mode (fast payload)
REM    2. Packages the payload inside the portable launcher
REM
REM  Resultado final: dist\GridAnalyzer_Portable.exe
REM ============================================================================

setlocal enabledelayedexpansion

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] No .venv virtual environment found.
    echo        Create and activate the venv with Python 3.12 before building.
    pause
    exit /b 1
)

set "PYTHON_EXE=.venv\Scripts\python.exe"
set "PYTHON_ARGS=-m PyInstaller"

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║         GridAnalyzer — Portable Build                       ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║  Step 1: Compile application (payload)                     ║
echo ║  Step 2: Package into portable launcher                   ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Navigate to project root (parent of portable/)
cd /d "%~dp0\.."

REM ── Step 1: Payload Build ──────────────────────────────────────────────
echo [1/2] Compiling application (--onedir mode)...
echo       This may take several minutes on the first run.
echo.

%PYTHON_EXE% %PYTHON_ARGS% --clean --noconfirm portable\build_portable.spec

if errorlevel 1 (
    echo.
    echo [ERROR] Payload compilation failed.
    echo        Check if PyInstaller is installed: pip install pyinstaller
    pause
    exit /b 1
)

echo.
echo [OK] Payload compiled successfully in dist\GridAnalyzer_payload\
echo.

REM ── Step 2: Launcher Build ─────────────────────────────────────────────
echo [2/2] Packaging into portable launcher...
echo.

%PYTHON_EXE% %PYTHON_ARGS% --clean --noconfirm portable\launcher.spec

if errorlevel 1 (
    echo.
    echo [ERROR] Launcher compilation failed.
    pause
    exit /b 1
)

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║  BUILD COMPLETED SUCCESSFULLY!                              ║
echo ║                                                             ║
echo ║  Executable: dist\GridAnalyzer_Portable.exe                ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Show file size
for %%F in (dist\GridAnalyzer_Portable.exe) do (
    set "size=%%~zF"
    set /a "sizeMB=!size! / 1048576"
    echo Size: !sizeMB! MB
)

echo.
pause
