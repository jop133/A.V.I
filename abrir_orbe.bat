@echo off
chcp 65001 > nul
title J.A.R.V.I.S. - Orbe Puro Flutuante
cls

echo ============================================================
echo   J.A.R.V.I.S. - ORBE PURO FLUTUANTE (100%% TRANSPARENTE)
echo   Esfera 3D com Constelações Coloridas no Topo do Monitor
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" orbe_desktop_tk.py
) else (
    start "" python orbe_desktop_tk.py
)

exit
