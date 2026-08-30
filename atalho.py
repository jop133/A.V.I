"""Tecla de atalho global para interromper a fala do Jarvis.

Por que atalho e nao voz: o microfone escuta os alto-falantes. Medido nesta
maquina, com ele falando o retorno chega a **1131 de RMS** contra um limiar de
fala de 180 -- mais alto que a propria voz do usuario (263). Nenhum ajuste de
limiar separa os dois, entao barge-in por voz faria o Jarvis se interromper
sozinho. `jarvis.py --doutor` mede isso na sua maquina e diz o veredito.

O atalho nao tem esse problema: e explicito, instantaneo e imune a eco.

Usa RegisterHotKey do Win32 via ctypes -- sem dependencia nova. O registro e
exclusivo no sistema: se outro programa ja tiver a combinacao, o registro
falha e nos avisamos, em vez de ficar sem funcionar em silencio.
"""

import ctypes
import threading
from ctypes import wintypes

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

_MODIFICADORES = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN,
}

# Teclas nao alfanumericas mais provaveis num atalho de "calar".
_TECLAS = {
    "space": 0x20, "espaco": 0x20, "esc": 0x1B, "escape": 0x1B,
    "tab": 0x09, "enter": 0x0D, "backspace": 0x08, "pause": 0x13,
}
for _i in range(1, 13):
    _TECLAS["f%d" % _i] = 0x6F + _i          # F1 = 0x70


def traduzir(combinacao):
    """'ctrl+alt+espaco' -> (modificadores, codigo da tecla). None se invalida."""
    partes = [p.strip().lower() for p in (combinacao or "").split("+") if p.strip()]
    if not partes:
        return None
    mods, tecla = 0, None
    for p in partes:
        if p in _MODIFICADORES:
            mods |= _MODIFICADORES[p]
        elif p in _TECLAS:
            tecla = _TECLAS[p]
        elif len(p) == 1:
            tecla = ord(p.upper())
        else:
            return None
    if tecla is None:
        return None
    return mods | MOD_NOREPEAT, tecla


def registrar(combinacao, ao_acionar):
    """Registra o atalho e chama `ao_acionar` a cada vez que ele for apertado.

    Devolve (True, descricao) ou (False, motivo). Nunca levanta excecao: um
    atalho que nao pode ser registrado nao pode derrubar o Jarvis.

    A thread e daemon e roda seu proprio laco de mensagens, porque
    RegisterHotKey entrega o evento na fila da THREAD que registrou.
    """
    traduzido = traduzir(combinacao)
    if not traduzido:
        return False, "combinacao invalida: %r" % combinacao
    mods, tecla = traduzido

    pronto = threading.Event()
    resultado = {}

    def laco():
        # WinDLL com use_last_error e argtypes explicitos: sem isso o hWnd NULL
        # e marshalado errado e o RegisterHotKey falha reportando "erro 0",
        # que nao diz nada.
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                          wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG),
                                       wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int

        if not user32.RegisterHotKey(None, 1, mods, tecla):
            erro = ctypes.get_last_error()
            resultado["erro"] = ("ja esta em uso por outro programa"
                                 if erro == 1409 else "erro %d do Windows" % erro)
            pronto.set()
            return
        resultado["ok"] = True
        pronto.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                try:
                    ao_acionar()
                except Exception as e:
                    print("  [Atalho] falhou ao interromper: %r" % (e,))

    threading.Thread(target=laco, daemon=True).start()
    pronto.wait(timeout=3.0)

    if resultado.get("ok"):
        return True, combinacao
    return False, resultado.get("erro", "nao respondeu a tempo")


# Combinacoes de reserva, tentadas quando a preferida ja pertence a outro
# programa. Medido nesta maquina: ctrl+alt+space e ctrl+shift+j ja estavam
# tomados, e sao justamente os candidatos "obvios" -- por isso a reserva
# existe, em vez de o Jarvis subir sem atalho nenhum.
RESERVAS = ["ctrl+shift+space", "ctrl+alt+j", "ctrl+shift+f9",
            "ctrl+alt+pause", "alt+f9"]


def registrar_com_reserva(preferida, ao_acionar):
    """Tenta a combinacao pedida e, se estiver tomada, as reservas.

    Devolve (ok, combinacao_em_uso, era_reserva).
    """
    tentativas = [preferida] + [r for r in RESERVAS if r != preferida]
    motivo = ""
    for i, c in enumerate(tentativas):
        ok, detalhe = registrar(c, ao_acionar)
        if ok:
            return True, c, i > 0
        if i == 0:
            motivo = detalhe
    return False, motivo, False
