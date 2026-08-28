"""Modela a voz escolhida sem trocar de modelo.

O edge-tts aceita ajuste de TOM (pitch) e RITMO (rate). Baixar o tom e falar um
pouco mais devagar costuma dar boa parte da gravidade que se associa ao Jarvis
-- de graca, sem clonagem e sem custo de processamento.
"""

import asyncio
import time
from pathlib import Path

import edge_tts

BASE = Path(__file__).parent
AMOSTRAS = BASE / "vozes" / "amostras"
AMOSTRAS.mkdir(parents=True, exist_ok=True)

VOZ = "en-AU-WilliamMultilingualNeural"

FRASE = ("Bom dia, senhor. Todos os sistemas estão operacionais. "
         "Detectei uma anomalia no seu código: quer que eu investigue?")

# (rotulo, tom, ritmo, o que muda)
VARIACOES = [
    ("original", "+0Hz", "+0%", "como voce ouviu"),
    ("grave", "-15Hz", "+0%", "tom mais baixo"),
    ("muito_grave", "-30Hz", "+0%", "tom bem mais baixo"),
    ("pausado", "+0Hz", "-12%", "mesma voz, mais devagar"),
    ("jarvis", "-15Hz", "-10%", "grave + pausado"),
    ("jarvis_forte", "-25Hz", "-15%", "grave e pausado ao maximo util"),
]


async def gerar(rotulo, tom, ritmo, descricao):
    destino = AMOSTRAS / ("william_%s.mp3" % rotulo)
    com = edge_tts.Communicate(FRASE, VOZ, pitch=tom, rate=ritmo)

    t0 = time.perf_counter()
    primeiro = None
    dados = bytearray()
    async for p in com.stream():
        if p["type"] == "audio":
            if primeiro is None:
                primeiro = time.perf_counter() - t0
            dados.extend(p["data"])
    destino.write_bytes(bytes(dados))
    print("  %-16s tom %-7s ritmo %-6s %-30s %5.2fs"
          % (rotulo, tom, ritmo, descricao, primeiro or 0))


async def main():
    print("=" * 78)
    print("  MODELANDO A VOZ  --  %s" % VOZ)
    print("=" * 78)
    print()
    for v in VARIACOES:
        try:
            await gerar(*v)
        except Exception as e:
            print("  %-16s ERRO: %s" % (v[0], str(e)[:50]))
    print()
    print("  amostras em: %s" % AMOSTRAS)


if __name__ == "__main__":
    asyncio.run(main())
