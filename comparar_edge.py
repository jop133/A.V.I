"""Amostras das vozes neurais da Microsoft (edge-tts).

Gratuitas e sem chave de API, mas ONLINE -- quebram o "100% offline". Em troca,
a qualidade e a pronuncia sao de outro patamar comparadas ao Piper/Kokoro.

Inclui vozes MULTILINGUES falando portugues: o timbre e de outro idioma, o que
pode dar o ar britanico/imponente do Jarvis do filme.
"""

import asyncio
import time
from pathlib import Path

import edge_tts

BASE = Path(__file__).parent
AMOSTRAS = BASE / "vozes" / "amostras"
AMOSTRAS.mkdir(parents=True, exist_ok=True)

FRASE = ("Bom dia, senhor. Todos os sistemas estão operacionais. "
         "Detectei uma anomalia no seu código: quer que eu investigue?")

CANDIDATAS = [
    ("pt-BR-AntonioNeural", "brasileira masculina (nativa)"),
    ("pt-BR-ThalitaMultilingualNeural", "brasileira feminina"),
    ("en-US-AndrewMultilingualNeural", "'warm, confident' falando portugues"),
    ("en-AU-WilliamMultilingualNeural", "australiana falando portugues"),
    ("en-US-BrianMultilingualNeural", "'sincere' falando portugues"),
    ("de-DE-FlorianMultilingualNeural", "alema falando portugues"),
]


async def gerar(voz, rotulo):
    destino = AMOSTRAS / ("edge_%s.mp3" % voz)
    com = edge_tts.Communicate(FRASE, voz)

    t0 = time.perf_counter()
    primeiro = None
    dados = bytearray()
    async for pedaco in com.stream():
        if pedaco["type"] == "audio":
            if primeiro is None:
                primeiro = time.perf_counter() - t0
            dados.extend(pedaco["data"])
    total = time.perf_counter() - t0

    destino.write_bytes(bytes(dados))
    print("  %-34s %-36s %6.2fs %7.2fs" % (voz, rotulo, primeiro or 0, total))
    return primeiro, total


async def main():
    print("=" * 88)
    print("  EDGE-TTS  --  vozes neurais da Microsoft, gratis e sem chave")
    print("=" * 88)
    print('  "%s"' % FRASE)
    print()
    print("  %-34s %-36s %6s %7s" % ("voz", "o que e", "1o audio", "total"))
    print("  " + "-" * 84)
    for voz, rotulo in CANDIDATAS:
        try:
            await gerar(voz, rotulo)
        except Exception as e:
            print("  %-34s %-36s ERRO: %s" % (voz, rotulo, str(e)[:26]))
    print()
    print("  amostras em: %s" % AMOSTRAS)
    print()
    print("  Lembrete: isto exige internet. Se a rede cair, o Jarvis fica mudo")
    print("  -- por isso vale manter o Piper como reserva automatica.")


if __name__ == "__main__":
    asyncio.run(main())
