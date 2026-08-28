"""Benchmark de voz: Piper (texto->fala) e Whisper (fala->texto).

Truque do teste: o Piper gera o audio que o Whisper transcreve. Assim medimos
os dois sem precisar do microfone -- e ainda checamos se a transcricao bate com
o texto original.

O que importa para um assistente de voz:
  TTS: tempo ate o PRIMEIRO pedaco de audio (a partir dai ja da para falar)
  STT: tempo total, porque so transcrevemos depois que o usuario se cala
"""

import io
import statistics
import time
import wave
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent
VOZ = BASE / "vozes" / "pt_BR-faber-medium.onnx"

FRASES = [
    "Bom dia! Tudo certo por aqui.",
    "O arquivo live session ponto py tem um erro na linha quarenta e dois.",
    "Me lembra de comprar pao quando eu sair, por favor.",
    "Qual e a temperatura em Lisboa agora?",
]


def bench_tts():
    from piper import PiperVoice

    print("-" * 68)
    print("  PIPER TTS  (%s)" % VOZ.name)
    t0 = time.perf_counter()
    voz = PiperVoice.load(str(VOZ))
    print("     carga do modelo: %.2fs" % (time.perf_counter() - t0))

    primeiros, fatores = [], []
    audios = []
    for frase in FRASES:
        t0 = time.perf_counter()
        primeiro = None
        pedacos = []
        taxa = 22050
        for chunk in voz.synthesize(frase):
            if primeiro is None:
                primeiro = time.perf_counter() - t0
            pedacos.append(chunk.audio_int16_bytes)
            taxa = chunk.sample_rate
        total = time.perf_counter() - t0
        pcm = b"".join(pedacos)
        duracao = len(pcm) / 2 / taxa
        fator = duracao / total if total > 0 else 0
        primeiros.append(primeiro or 0)
        fatores.append(fator)
        audios.append((frase, pcm, taxa))
        print("     1o audio %5.2fs | gerou %4.1fs de fala em %4.2fs (%.1fx tempo real)"
              % (primeiro or 0, duracao, total, fator))

    print("     >> mediana: %.2fs ate a primeira palavra | %.1fx tempo real"
          % (statistics.median(primeiros), statistics.median(fatores)))
    return audios


def para_wav(pcm, taxa):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm)
    buf.seek(0)
    return buf


def normalizar(t):
    import re
    return re.sub(r"[^a-z0-9 ]", "", t.lower().replace("ã", "a").replace("á", "a")
                  .replace("é", "e").replace("ê", "e").replace("í", "i")
                  .replace("ó", "o").replace("ô", "o").replace("õ", "o")
                  .replace("ú", "u").replace("ç", "c")).split()


def parecidas(a, b):
    """Fracao de palavras do original que aparecem na transcricao."""
    pa, pb = normalizar(a), set(normalizar(b))
    if not pa:
        return 0.0
    return sum(1 for p in pa if p in pb) / len(pa)


def bench_stt(audios, tamanho):
    from faster_whisper import WhisperModel

    print("-" * 68)
    print("  FASTER-WHISPER  '%s'  (CPU, int8, 12 threads)" % tamanho)
    t0 = time.perf_counter()
    modelo = WhisperModel(tamanho, device="cpu", compute_type="int8", cpu_threads=12)
    print("     carga do modelo: %.1fs" % (time.perf_counter() - t0))

    tempos, precisoes, fatores = [], [], []
    for frase, pcm, taxa in audios:
        wav = para_wav(pcm, taxa)
        duracao = len(pcm) / 2 / taxa
        t0 = time.perf_counter()
        segmentos, _ = modelo.transcribe(wav, language="pt", beam_size=1,
                                         vad_filter=False)
        texto = " ".join(s.text for s in segmentos).strip()
        dt = time.perf_counter() - t0
        p = parecidas(frase, texto)
        tempos.append(dt)
        precisoes.append(p)
        fatores.append(duracao / dt if dt > 0 else 0)
        print("     %4.2fs para %4.1fs de audio (%.1fx) | %3.0f%% | %r"
              % (dt, duracao, duracao / dt if dt else 0, p * 100, texto[:46]))

    print("     >> mediana: %.2fs por fala | %.1fx tempo real | %.0f%% de acerto"
          % (statistics.median(tempos), statistics.median(fatores),
             statistics.mean(precisoes) * 100))
    return statistics.median(tempos), statistics.mean(precisoes)


if __name__ == "__main__":
    print("=" * 68)
    print("  VOZ LOCAL -- Piper + Whisper")
    print("=" * 68)
    audios = bench_tts()
    print()
    resultados = {}
    for tam in ("base", "small"):
        try:
            resultados[tam] = bench_stt(audios, tam)
        except Exception as e:
            print("     ERRO com '%s': %s" % (tam, str(e)[:70]))
        print()
    print("=" * 68)
    for tam, (t, p) in resultados.items():
        print("  whisper %-6s %.2fs por fala | %.0f%% de acerto" % (tam, t, p * 100))
