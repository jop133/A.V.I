@echo off
title J.A.R.V.I.S. Local - 100%% offline
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   J.A.R.V.I.S. LOCAL  (sem internet)
echo ========================================
echo.

rem O cerebro roda no Ollama. Se o servico nao estiver de pe, nada funciona.
curl -s -o nul http://127.0.0.1:11434/api/version 2>nul
if errorlevel 1 (
    echo [1/2] Ollama nao esta rodando. Iniciando...
    start "" /min "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
    timeout /t 5 /nobreak >nul
) else (
    echo [1/2] Ollama ja esta rodando.
)

echo [2/2] Carregando modelos na memoria...
echo.

rem --simulado usa fala sintetica em vez do microfone (util para testar)
".\.venv\Scripts\python.exe" jarvis.py %*

echo.
pause
