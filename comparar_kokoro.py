"""Gera amostras do Kokoro para comparar com o Piper.

Inclui uma aposta: as vozes BRITANICAS do Kokoro falando portugues. O sotaque
britanico e a assinatura sonora do Jarvis do filme -- pode soar imponente, ou
pode soar errado. So ouvindo para saber.
"""

import time
import wave
from pathlib import Path

import numpy as np
from kokoro_onnx import Kokoro

BASE = Path(__file__).parent
AMOSTRAS = BASE / "vozes" / "amostras"
AMOSTRAS.mkdir(parents=True, exist_ok=True)

FRASE = ("Bom dia, senhor. Todos os sistemas estao operacionais. "
         "Detectei uma anomalia no seu codigo: quer que eu investigue?")

# (voz, idioma, comentario)
CANDIDATOS = [
    ("pm_alex", "pt-br", "masculina brasileira"),
    ("pf_dora", "pt-br", "feminina brasileira"),
    ("pm_santa", "pt-br", "masculina brasileira (grave)"),
    ("bm_george", "pt-br", "BRITANICA falando portugues"),
    ("bm_daniel", "pt-br", "BRITANICA falando portugues"),
    ("bm_fable", "pt-br", "BRITANICA falando portugues"),
]


def salvar(nome, amostras, taxa):
    caminho = AMOSTRAS / ("kokoro_%s.wav" % nome)
    pcm = (np.clip(amostras, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm.tobytes())
    return caminho


if __name__ == "__main__":
    print("=" * 70)
    print("  KOKORO  --  a mesma frase, vozes diferentes")
    print("=" * 70)

    t0 = time.perf_counter()
    k = Kokoro(str(BASE / "vozes/kokoro/kokoro-v1.0.onnx"),
               str(BASE / "vozes/kokoro/voices-v1.0.bin"))
    print("  carga do modelo: %.1fs" % (time.perf_counter() - t0))
    print()

    print("  %-14s %-32s %9s %13s" % ("voz", "o que e", "tempo", "vs tempo real"))
    print("  " + "-" * 72)
    for voz, idioma, comentario in CANDIDATOS:
        try:
            t0 = time.perf_counter()
            amostras, taxa = k.create(FRASE, voice=voz, speed=1.0, lang=idioma)
            dt = time.perf_counter() - t0
            duracao = len(amostras) / taxa
            salvar(voz, amostras, taxa)
            print("  %-14s %-32s %8.2fs %12.1fx"
                  % (voz, comentario, dt, duracao / dt if dt else 0))
        except Exception as e:
            print("  %-14s %-32s ERRO: %s" % (voz, comentario, str(e)[:34]))

    print()
    print("  amostras em: %s" % AMOSTRAS)
    print()
    print("  ATENCAO a coluna 'vs tempo real': abaixo de 1.0x o Kokoro gera")
    print("  mais devagar do que a fala dura, e a voz engasgaria.")
