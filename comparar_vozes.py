"""Baixa e compara as vozes disponiveis, gerando o MESMO texto em cada uma.

Voz e escolha de ouvido -- entao o script gera os arquivos e mede a latencia,
mas quem decide e voce. Rode e ouca os .wav gerados em vozes/amostras/.

    .\\.venv\\Scripts\\python.exe comparar_vozes.py
"""

import json
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path

BASE = Path(__file__).parent
VOZES = BASE / "vozes"
AMOSTRAS = VOZES / "amostras"
CATALOGO = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

# Uma frase com pontuacao variada: mostra entonacao, pausa e pergunta.
FRASE = ("Bom dia, senhor. Todos os sistemas estao operacionais. "
         "Detectei uma anomalia no seu codigo: quer que eu investigue?")


def baixar(url, destino):
    if destino.exists() and destino.stat().st_size > 1000:
        return True
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jarvis-local"})
        with urllib.request.urlopen(req, timeout=300) as r, open(destino, "wb") as f:
            f.write(r.read())
        return True
    except Exception as e:
        print("     falhou: %s" % str(e)[:60])
        return False


def vozes_portuguesas():
    """Catalogo oficial do Piper, filtrado por portugues."""
    d = json.loads(urllib.request.urlopen(CATALOGO + "voices.json", timeout=120).read())
    return {k: v for k, v in d.items() if k.startswith("pt_")}


def preparar_piper():
    """Garante que todas as vozes em portugues estao no disco."""
    catalogo = vozes_portuguesas()
    prontas = []
    for nome, info in sorted(catalogo.items()):
        onnx = json_ = None
        for caminho in info.get("files", {}):
            if caminho.endswith(".onnx"):
                onnx = caminho
            elif caminho.endswith(".onnx.json"):
                json_ = caminho
        if not onnx:
            continue

        destino = VOZES / Path(onnx).name
        print("  %-24s" % nome, end=" ")
        ok = baixar(CATALOGO + urllib.parse.quote(onnx), destino)
        if json_:
            ok = baixar(CATALOGO + urllib.parse.quote(json_),
                        VOZES / Path(json_).name) and ok
        print("ok" if ok else "FALHOU")
        if ok:
            prontas.append((nome, destino))
    return prontas


def gerar_piper(nome, caminho_onnx):
    from piper import PiperVoice

    voz = PiperVoice.load(str(caminho_onnx))
    t0 = time.perf_counter()
    primeiro = None
    pedacos, taxa = [], 22050
    for chunk in voz.synthesize(FRASE):
        if primeiro is None:
            primeiro = time.perf_counter() - t0
        pedacos.append(chunk.audio_int16_bytes)
        taxa = chunk.sample_rate
    total = time.perf_counter() - t0

    pcm = b"".join(pedacos)
    duracao = len(pcm) / 2 / taxa
    destino = AMOSTRAS / ("piper_%s.wav" % nome)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm)
    return primeiro, total, duracao, destino


if __name__ == "__main__":
    print("=" * 70)
    print("  COMPARACAO DE VOZES  --  a mesma frase em cada uma")
    print("=" * 70)
    print('  "%s"' % FRASE)
    print()

    print("-- baixando vozes Piper --")
    prontas = preparar_piper()
    print()

    print("-- gerando amostras --")
    print("  %-26s %10s %10s %12s" % ("voz", "1o audio", "total", "vs tempo real"))
    print("  " + "-" * 62)
    for nome, caminho in prontas:
        try:
            primeiro, total, duracao, destino = gerar_piper(nome, caminho)
            print("  %-26s %9.2fs %9.2fs %11.1fx" %
                  (nome, primeiro, total, duracao / total if total else 0))
        except Exception as e:
            print("  %-26s ERRO: %s" % (nome, str(e)[:40]))

    print()
    print("  amostras salvas em: %s" % AMOSTRAS)
    print("  abra a pasta e ouca cada uma para escolher.")
