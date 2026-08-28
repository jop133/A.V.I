@echo off
chcp 65001 > nul
title J.A.R.V.I.S. - Modo Bordas Ambientais
cls

echo ============================================================
echo   J.A.R.V.I.S. - MODO BORDAS AMBIENTAIS TRANSLÚCIDAS
echo   Iluminação Perimetral nas 4 Bordas com Vibração de Voz
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" bordas_desktop_tk.py
) else (
    start "" python bordas_desktop_tk.py
)

exit
