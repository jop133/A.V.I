"""Combina voz + tom + ritmo + tratamento de audio, e gera amostras.

Tres camadas independentes:
    VOZ    -- qual timbre (edge-tts)
    TOM    -- mais grave ou mais agudo
    RITMO  -- mais pausado ou mais natural
    SALA   -- reverberacao, graves e compressao (presenca.py)

Ajuste a lista COMBINACOES e rode. Os .wav saem em vozes/amostras/afinar_*.wav
    .\\.venv\\Scripts\\python.exe afinar_jarvis.py
"""

import asyncio
import io
import time
import wave
from pathlib import Path

import edge_tts
import soundfile as sf

import presenca

BASE = Path(__file__).parent
AMOSTRAS = BASE / "vozes" / "amostras"
AMOSTRAS.mkdir(parents=True, exist_ok=True)

VOZ = "en-AU-WilliamMultilingualNeural"

# Frase com ritmo variado: afirmacao, pausa, enumeracao e pergunta.
# Frase monotona esconde problemas de cadencia.
FRASE = ("Bom dia, senhor. Os sistemas estao operacionais e a temperatura "
         "esta estavel. Encontrei tres erros no seu codigo, todos na mesma "
         "funcao. Quer que eu mostre?")

# (nome, tom, ritmo, parametros de sala, o que muda)
COMBINACOES = [
    # ponto de partida, para comparar
    ("00_atual",       "-15Hz", "-5%", dict(reverb=0.48, graves=1.45),
     "o que esta configurado hoje"),

    # menos grave, mesma velocidade -- isola o efeito do TOM
    ("01_menos_grave", "-8Hz",  "-5%", dict(reverb=0.48, graves=1.45),
     "so menos grave"),

    # mesma gravidade, mais rapida -- isola o efeito do RITMO
    ("02_mais_rapida", "-15Hz", "+5%", dict(reverb=0.48, graves=1.45),
     "so mais rapida"),

    # os dois juntos, em tres intensidades
    ("03_leve",        "-8Hz",  "+3%", dict(reverb=0.48, graves=1.45),
     "menos grave + um pouco mais rapida"),
    ("04_solta",       "-5Hz",  "+6%", dict(reverb=0.48, graves=1.45),
     "bem menos grave e mais rapida"),
    ("05_natural",     "+0Hz",  "+8%", dict(reverb=0.48, graves=1.45),
     "tom natural, ritmo acelerado"),

    # e se a SALA tambem estiver pesando na seriedade?
    ("06_sala_menor",  "-8Hz",  "+3%", dict(reverb=0.30, graves=1.30),
     "como a 03, com sala e graves menores"),
]


async def sintetizar(tom, ritmo):
    com = edge_tts.Communicate(FRASE, VOZ, pitch=tom, rate=ritmo)
    dados = bytearray()
    async for p in com.stream():
        if p["type"] == "audio":
            dados.extend(p["data"])
    audio, taxa = sf.read(io.BytesIO(bytes(dados)), dtype="int16")
    return audio.tobytes(), taxa


def salvar(nome, pcm, taxa):
    caminho = AMOSTRAS / ("afinar_%s.wav" % nome)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm)
    return caminho


async def main():
    print("=" * 78)
    print("  AFINANDO  --  %s" % VOZ)
    print("=" * 78)
    print()
    print("  %-18s %-7s %-7s %-30s %8s" % ("nome", "tom", "ritmo", "o que muda", "duracao"))
    print("  " + "-" * 74)

    # cache: a mesma combinacao tom+ritmo nao precisa ir a rede duas vezes
    cache = {}

    for nome, tom, ritmo, sala, descricao in COMBINACOES:
        chave = (tom, ritmo)
        if chave not in cache:
            cache[chave] = await sintetizar(tom, ritmo)
        pcm, taxa = cache[chave]

        tratado = presenca.tratar(pcm, taxa, **sala)
        salvar(nome, tratado, taxa)
        print("  %-18s %-7s %-7s %-30s %7.1fs"
              % (nome, tom, ritmo, descricao, len(tratado) / 2 / taxa))

    print()
    print("  amostras em: %s" % AMOSTRAS)
    print()
    print("  Sugestao de escuta: comece por a, b e c para decidir a VELOCIDADE.")
    print("  Depois compare e, f e h para decidir a SALA. Por fim, ouca g.")


if __name__ == "__main__":
    asyncio.run(main())
