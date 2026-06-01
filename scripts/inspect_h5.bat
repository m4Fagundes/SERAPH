@echo off
cd /d "%~dp0"
venv\Scripts\python.exe inspect_h5.py
if %errorlevel% neq 0 (
    echo.
    echo ERRO ao executar o script.
)
pause
