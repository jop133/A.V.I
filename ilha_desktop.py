"""Lançador Desktop da Barra / Pílula Dynamic Island do J.A.R.V.I.S.

Posiciona a barra de controle translúcida no topo central do monitor,
idêntica ao print de referência, sem molduras e com transparência nativa.
"""

import ctypes
import os
import subprocess
import sys
import time
import threading
from pathlib import Path

BASE = Path(__file__).parent
ISLAND_HTML = BASE / "hud" / "island.html"

GWL_STYLE = -16
GWL_EXSTYLE = -20

WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000

WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080

SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1

EDGE_PATHS = [
    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
]

CHROME_PATHS = [
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
]

def encontrar_executavel():
    for p in EDGE_PATHS:
        if os.path.isfile(p):
            return p
    for p in CHROME_PATHS:
        if os.path.isfile(p):
            return p
    return None

def posicionar_ilha_win32():
    user32 = ctypes.windll.user32
    
    hwnd = None
    for _ in range(40):
        time.sleep(0.1)
        h = user32.FindWindowW(None, "JARVIS_DYNAMIC_ISLAND")
        if h:
            hwnd = h
            break

    if not hwnd:
        return

    screen_w = user32.GetSystemMetrics(0)
    w = 480
    h = 60
    pos_x = (screen_w - w) // 2
    pos_y = 6

    for _ in range(12):
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        style &= ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
        style |= WS_POPUP | WS_VISIBLE
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)

        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex_style |= (WS_EX_TOPMOST | WS_EX_TOOLWINDOW)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            pos_x,
            pos_y,
            w,
            h,
            SWP_FRAMECHANGED | SWP_SHOWWINDOW
        )
        time.sleep(0.15)

def main():
    url = ISLAND_HTML.resolve().as_uri()
    exe = encontrar_executavel()

    t = threading.Thread(target=posicionar_ilha_win32, daemon=True)
    t.start()

    if exe:
        cmd = [
            exe,
            f"--app={url}",
            "--window-size=480,60",
            "--window-position=720,6",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-default-apps"
        ]
        p = subprocess.Popen(cmd)
        p.wait()
    else:
        os.system(f'start msedge --app="{url}" --window-size=480,60')

if __name__ == "__main__":
    main()
