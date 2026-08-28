"""Iniciador da HUD do Jarvis como Aplicativo Desktop Nativo Maximizado em Tela Cheia.

Garante via perfil isolado, flags Chromium e chamadas nativas do Windows Win32
(ShowWindow SW_MAXIMIZE) que a HUD Completa abra SEMPRE em tela cheia maximizada,
tanto na inicialização do Jarvis quanto ao alternar de outros modos.
"""

import ctypes
import os
import subprocess
import sys
import time
import threading
from pathlib import Path

BASE = Path(__file__).parent
HUD_HTML = BASE / "hud" / "index.html"
PROFILE_DIR = BASE / ".hud_profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

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

def forcar_maximizacao_confiavel(target_pid=None):
    """Monitora e garante que a janela da HUD seja imediatamente e continuamente maximizada."""
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

    SW_MAXIMIZE = 3
    SW_RESTORE = 9

    def enum_cb(hwnd, extra):
        if not user32.IsWindowVisible(hwnd):
            return True
        class_buff = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buff, 256)
        c_name = class_buff.value

        if "ConsoleWindowClass" in c_name or "VirtualConsoleClass" in c_name:
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value

            if any(k in title for k in ["100% offline", "cmd.exe", "PowerShell"]):
                return True

            if any(k in title for k in ["J.A.R.V.I.S. - Core", "J.A.R.V.I.S. HUD", "trillion // jarvis", "J.A.R.V.I.S"]):
                user32.ShowWindow(hwnd, SW_MAXIMIZE)
                user32.SetForegroundWindow(hwnd)
        return True

    cb = WNDENUMPROC(enum_cb)
    # Roda uma checagem contínua durante os primeiros 4 segundos para assegurar maximização total
    for _ in range(25):
        time.sleep(0.12)
        try:
            user32.EnumWindows(cb, 0)
        except Exception:
            pass

def _url_com_token():
    """URI file:// da HUD com o token da sessao.

    O app.js roda de file:// e nao consegue ler .hud_token do disco (fetch em
    file:// e bloqueado), entao o token chega pela query string da propria URL.
    """
    url = HUD_HTML.resolve().as_uri()
    try:
        token = (BASE / ".hud_token").read_text(encoding="utf-8").strip()
    except Exception:
        token = ""
    return f"{url}?token={token}" if token else url


def main():
    url = _url_com_token()
    exe = encontrar_executavel()

    t = threading.Thread(target=forcar_maximizacao_confiavel, daemon=True)
    t.start()

    if exe:
        cmd = [
            exe,
            f"--app={url}",
            f"--user-data-dir={PROFILE_DIR}",
            "--start-maximized",
            "--window-position=0,0",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-default-apps"
        ]
        try:
            p = subprocess.Popen(cmd)
            p.wait()
        except Exception:
            os.system(f'start "" /max msedge --app="{url}" --start-maximized')
    else:
        os.system(f'start "" /max msedge --app="{url}" --start-maximized')

if __name__ == "__main__":
    main()
