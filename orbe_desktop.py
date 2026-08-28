"""Lançador do Orbe WebGL 3D do J.A.R.V.I.S. (100% Idêntico à Imagem do Usuário)

Executa o motor WebGL Three.js original com o shader GLSL, constelações
e casca holográfica em uma janela compacta estilo Siri (160x160) com
100% de transparência nativa no Windows.
"""

import ctypes
import os
import subprocess
import sys
import time
import threading
from pathlib import Path

BASE = Path(__file__).parent
ORBE_HTML = BASE / "hud" / "orbe_webgl.html"

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

LWA_COLORKEY = 0x1
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

def aplicar_transparencia_win32():
    user32 = ctypes.windll.user32
    
    hwnd = None
    for _ in range(40):
        time.sleep(0.1)
        h = user32.FindWindowW(None, "JARVIS_CORE_WEBGL_ORB")
        if h:
            hwnd = h
            break

    if not hwnd:
        return

    screen_w = user32.GetSystemMetrics(0)
    orb_size = 160
    pos_x = (screen_w - orb_size) // 2
    pos_y = 8

    for _ in range(15):
        # 1. Remove barra de título, bordas e botões
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        style &= ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
        style |= WS_POPUP | WS_VISIBLE
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)

        # 2. Ativa Layered Window e Topmost
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex_style |= (WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

        # 3. Chave de Transparência: Cor 0x00000001 vira 100% transparente para a tela
        user32.SetLayeredWindowAttributes(hwnd, 0x00000001, 0, LWA_COLORKEY)

        # 4. Posiciona no topo central
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            pos_x,
            pos_y,
            orb_size,
            orb_size,
            SWP_FRAMECHANGED | SWP_SHOWWINDOW
        )
        time.sleep(0.15)

def main():
    url = ORBE_HTML.resolve().as_uri()
    exe = encontrar_executavel()

    t = threading.Thread(target=aplicar_transparencia_win32, daemon=True)
    t.start()

    if exe:
        cmd = [
            exe,
            f"--app={url}",
            "--window-size=160,160",
            "--window-position=880,8",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-default-apps"
        ]
        p = subprocess.Popen(cmd)
        p.wait()
    else:
        os.system(f'start msedge --app="{url}" --window-size=160,160')

if __name__ == "__main__":
    main()
