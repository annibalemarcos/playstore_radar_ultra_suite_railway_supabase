@echo off
title Playstore_Radar_Ultra_Suite
mode con: cols=68 lines=14
chcp 65001 >nul
cd /d "%~dp0"
echo Instalando PlayStore Radar Ultra...
call _bootstrap_venv.bat
if errorlevel 1 (
    echo.
    echo Instalacao falhou. Veja o erro acima.
    pause
    exit /b 1
)
echo.
echo OK. Agora rode rodar_terminal.bat ou rodar_web.bat
pause
