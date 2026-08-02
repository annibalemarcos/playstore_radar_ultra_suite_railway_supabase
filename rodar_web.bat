@echo off
title Playstore_Radar_Ultra_Suite
mode con: cols=68 lines=14
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo .venv nao encontrado ou quebrado. Preparando ambiente...
    call _bootstrap_venv.bat
    if errorlevel 1 goto erro
)

".venv\Scripts\python.exe" -c "import flask" >nul 2>nul
if errorlevel 1 (
    echo Flask/dependencias nao instaladas. Instalando agora...
    call _bootstrap_venv.bat
    if errorlevel 1 goto erro
)

echo Abrindo dashboard em http://127.0.0.1:5892
start "" http://127.0.0.1:5892
".venv\Scripts\python.exe" webapp.py
pause
exit /b 0

:erro
echo.
echo Nao consegui preparar o ambiente. Rode instalar.bat e veja o erro.
pause
exit /b 1
