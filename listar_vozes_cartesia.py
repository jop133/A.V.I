"""Lista as vozes da Cartesia em portugues e gera uma amostra de cada.

Precisa da chave no .env:

    CARTESIA_API_KEY=sk_car_...

Depois de escolher, ponha o ID no mesmo .env:

    CARTESIA_VOICE_ID=<id-da-voz>

E troque MOTOR_VOZ = "cartesia" no topo do jarvis.py.

    .\\.venv\\Scripts\\python.exe listar_vozes_cartesia.py
"""

import os
import sys
import time
import wave
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from jarvis import (CARTESIA_IDIOMA, CARTESIA_MODELO, CARTESIA_TAXA,  # noqa: E402
                    CARTESIA_VELOCIDADE, SALA_GRAVES, SALA_REVERB, _carregar_env)
import presenca  # noqa: E402

_carregar_env()

BASE = Path(__file__).parent
AMOSTRAS = BASE / "vozes" / "amostras"
API = "https://api.cartesia.ai"
VERSAO = "2026-08-14"

FRASE = ("Bom dia, senhor. Os sistemas estão operacionais. "
         "Encontrei três erros no seu código: quer que eu mostre?")


def cabecalhos():
    chave = os.getenv("CARTESIA_API_KEY")
    if not chave:
        print("ERRO: CARTESIA_API_KEY nao encontrada.")
        print()
        print("Crie o arquivo .env nesta pasta com:")
        print("    CARTESIA_API_KEY=sk_car_...")
        sys.exit(1)
    return {"Authorization": "Bearer %s" % chave, "Cartesia-Version": VERSAO}


def listar():
    """Todas as vozes da conta + biblioteca publica."""
    vozes, pagina = [], None
    for _ in range(20):                       # teto de seguranca
        params = {"limit": 100}
        if pagina:
            params["starting_after"] = pagina
        r = requests.get(API + "/voices", headers=cabecalhos(),
                         params=params, timeout=30)
        if r.status_code != 200:
            print("ERRO ao listar vozes: HTTP %d %s" % (r.status_code, r.text[:150]))
            sys.exit(1)
        dados = r.json()
        lote = dados.get("data", dados if isinstance(dados, list) else [])
        vozes.extend(lote)
        if not dados.get("has_more") or not lote:
            break
        pagina = lote[-1].get("id")
    return vozes


def e_portuguesa(v):
    idioma = (v.get("language") or "").lower()
    return idioma.startswith("pt")


def sintetizar(voz_id):
    r = requests.post(
        API + "/tts/bytes", headers=cabecalhos(),
        json={
            "model_id": CARTESIA_MODELO,
            "transcript": FRASE,
            "voice": {"id": voz_id,
                      "experimental_controls": {"speed": CARTESIA_VELOCIDADE}},
            "language": CARTESIA_IDIOMA,
            "output_format": {"container": "raw", "encoding": "pcm_s16le",
                              "sample_rate": CARTESIA_TAXA},
        }, timeout=60)
    if r.status_code != 200:
        raise RuntimeError("HTTP %d: %s" % (r.status_code, r.text[:120]))
    return r.content


def salvar(nome, pcm):
    AMOSTRAS.mkdir(parents=True, exist_ok=True)
    caminho = AMOSTRAS / ("cartesia_%s.wav" % nome)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(CARTESIA_TAXA)
        w.writeframes(pcm)
    return caminho


def limpar(texto):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in texto)[:40]


if __name__ == "__main__":
    print("=" * 76)
    print("  VOZES DA CARTESIA EM PORTUGUES  (modelo %s)" % CARTESIA_MODELO)
    print("=" * 76)

    todas = listar()
    pt = [v for v in todas if e_portuguesa(v)]
    print("  %d vozes na conta; %d em portugues" % (len(todas), len(pt)))
    print()

    if not pt:
        print("  Nenhuma voz marcada como portugues.")
        print("  Os modelos Sonic sao multilingues: uma voz de outro idioma")
        print("  pode falar portugues. Listando as 15 primeiras de todas:")
        pt = todas[:15]
        print()

    print("  %-38s %-22s %s" % ("id", "nome", "idioma"))
    print("  " + "-" * 72)
    for v in pt:
        print("  %-38s %-22s %s" % (v.get("id", "?"), (v.get("name") or "")[:22],
                                    v.get("language", "?")))

    print()
    print("-- gerando amostras (com o mesmo tratamento de sala do Jarvis) --")
    for v in pt[:8]:
        nome = limpar(v.get("name") or v.get("id", "voz"))
        try:
            t0 = time.perf_counter()
            pcm = sintetizar(v["id"])
            dt = time.perf_counter() - t0
            tratado = presenca.tratar(pcm, CARTESIA_TAXA,
                                      reverb=SALA_REVERB, graves=SALA_GRAVES)
            salvar(nome, tratado)
            print("  ok   %-24s %5.2fs de rede" % (nome[:24], dt))
        except Exception as e:
            print("  ERRO %-24s %s" % (nome[:24], str(e)[:40]))

    print()
    print("  amostras em: %s" % AMOSTRAS)
    print()
    print("  Escolha uma e ponha no .env:")
    print("      CARTESIA_VOICE_ID=<id da voz>")
    print("  Depois troque MOTOR_VOZ = \"cartesia\" no topo do jarvis.py")
