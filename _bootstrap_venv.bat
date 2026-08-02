@echo off
title Playstore_Radar_Ultra_Suite
chcp 65001 >nul
cd /d "%~dp0"

set "PY_CMD="

where py >nul 2>nul
if %errorlevel%==0 (
    py -3.11 -V >nul 2>nul
    if %errorlevel%==0 set "PY_CMD=py -3.11"
)

if not defined PY_CMD (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3.12 -V >nul 2>nul
        if %errorlevel%==0 set "PY_CMD=py -3.12"
    )
)

if not defined PY_CMD (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3 -V >nul 2>nul
        if %errorlevel%==0 set "PY_CMD=py -3"
    )
)

if not defined PY_CMD (
    where python >nul 2>nul
    if %errorlevel%==0 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo ERRO: Python nao encontrado no PATH.
    echo Instale o Python 3.11/3.12 ou marque "Add Python to PATH".
    exit /b 1
)

echo Python selecionado: %PY_CMD%

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Criando ambiente virtual .venv...
    if exist ".venv" (
        echo Aviso: .venv existe, mas esta incompleto/quebrado. Recriando...
        rmdir /s /q ".venv"
    )
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo ERRO: falha ao criar .venv.
        exit /b 1
    )
)

echo.
echo Atualizando pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERRO: falha ao atualizar pip.
    exit /b 1
)

echo.
echo Instalando dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERRO: falha ao instalar requirements.txt.
    exit /b 1
)

echo.
echo Ambiente pronto.
exit /b 0
