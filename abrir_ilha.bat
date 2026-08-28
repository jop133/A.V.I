@echo off
chcp 65001 > nul
title J.A.R.V.I.S. - Top Bar HUD
cls

echo ============================================================
echo   J.A.R.V.I.S. - TOP BAR HUD NATIVA (100%% TRANSPARENTE)
echo   Pílula no Topo do Monitor (Padrão Gemini Live / Tkinter)
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" hud_desktop_tk.py
) else (
    start "" python hud_desktop_tk.py
)

exit
