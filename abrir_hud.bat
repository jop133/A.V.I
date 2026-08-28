@echo off
chcp 65001 > nul
title J.A.R.V.I.S. Desktop HUD
cd /d "%~dp0"

echo ========================================================
echo   Iniciando Aplicativo Desktop J.A.R.V.I.S. (MAXIMIZADO)
echo ========================================================

set "URL=%~dp0hud\index.html"

if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    start "" /max "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" --app="file:///%URL%" --start-maximized
    exit
)

if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
    start "" /max "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" --app="file:///%URL%" --start-maximized
    exit
)

if exist "%LocalAppData%\Microsoft\Edge\Application\msedge.exe" (
    start "" /max "%LocalAppData%\Microsoft\Edge\Application\msedge.exe" --app="file:///%URL%" --start-maximized
    exit
)

start "" /max msedge.exe --app="file:///%URL%" --start-maximized
exit
