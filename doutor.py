"""Autodiagnostico do Jarvis.

    .\\.venv\\Scripts\\python.exe jarvis.py --doutor

Existe porque descobrir EM QUE CAMADA uma falha acontece era a parte cara.
Um microfone mudo, uma HUD que nao abre e um modelo fora do ar produzem o
mesmo sintoma para quem esta falando: "ele nao respondeu". Este relatorio
separa isso em trinta segundos.

Cada checagem diz o que mediu e, quando falha, o que fazer a respeito.

Aviso: TOCA SOM (para medir o eco) e ABRE E FECHA as interfaces.
Use --rapido para pular essas duas partes.
"""

import os
import queue
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent

OK, AVISO, FALHA = "OK", "AVISO", "FALHA"
_MARCA = {OK: "  [ ok ]  ", AVISO: "  [aviso]  ", FALHA: "  [FALHA]  "}


class Relatorio:
    def __init__(self):
        self.itens = []

    def anota(self, estado, nome, detalhe="", conserto=""):
        self.itens.append((estado, nome, detalhe, conserto))
        linha = _MARCA[estado] + nome
        if detalhe:
            linha += "  ->  " + detalhe
        print(linha, flush=True)
        if conserto and estado != OK:
            print("           conserto: " + conserto, flush=True)
        return estado == OK

    def secao(self, titulo):
        print()
        print("  " + titulo)
        print("  " + "-" * (len(titulo) + 2), flush=True)

    def resumo(self):
        falhas = [i for i in self.itens if i[0] == FALHA]
        avisos = [i for i in self.itens if i[0] == AVISO]
        print()
        print("=" * 66)
        print("  %d checagens: %d ok, %d avisos, %d falhas"
              % (len(self.itens), len(self.itens) - len(falhas) - len(avisos),
                 len(avisos), len(falhas)))
        for estado, nome, detalhe, conserto in falhas + avisos:
            print("   %-6s %s" % (estado, nome))
        print("=" * 66)
        return 1 if falhas else 0


# --------------------------------------------------------------------- ambiente

def checar_ambiente(r):
    r.secao("Ambiente")
    r.anota(OK, "Python", sys.version.split()[0])

    req = BASE / "requirements.txt"
    if not req.exists():
        r.anota(AVISO, "requirements.txt", "nao existe",
                "gere com pip freeze ou peca ao agente")
        return

    from importlib.metadata import version, PackageNotFoundError
    faltando = []
    for linha in req.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#")[0].strip()
        if not linha:
            continue
        nome = linha.split("==")[0].split(">")[0].split("<")[0].strip()
        try:
            version(nome)
        except PackageNotFoundError:
            faltando.append(nome)
    if faltando:
        r.anota(FALHA, "pacotes do requirements.txt", "faltam: " + ", ".join(faltando),
                r".\.venv\Scripts\python.exe -m pip install -r requirements.txt")
    else:
        r.anota(OK, "pacotes do requirements.txt", "todos presentes")

    # A g4f foi removida de proposito; se voltou, alguem a reintroduziu.
    try:
        version("g4f")
        r.anota(AVISO, "g4f", "instalada de novo",
                "foi removida em 28/ago/2026 por mandar a tela a terceiros")
    except Exception:
        r.anota(OK, "g4f", "ausente, como esperado")


def checar_env(r):
    r.secao("Arquivo .env")
    if not (BASE / ".env").exists():
        r.anota(FALHA, ".env", "nao existe", "copie o .env.exemplo e preencha")
        return
    esperadas = {
        "CARTESIA_API_KEY": "chave da voz principal",
        "CARTESIA_VOICE_ID": "voz escolhida",
        "MICROFONE": "microfone fixo (evita o Windows escolher um cabo virtual)",
        "CIDADE_PADRAO": "cidade do clima (evita o ip-api, que e HTTP puro)",
    }
    for chave, para_que in esperadas.items():
        valor = (os.getenv(chave) or "").strip()
        if valor:
            mostra = valor[:10] + "..." if "KEY" in chave else valor
            r.anota(OK, chave, mostra)
        else:
            r.anota(AVISO, chave, "vazia", para_que)


# -------------------------------------------------------------------- microfone

def checar_microfone(r, jarvis):
    import numpy as np
    import sounddevice as sd

    r.secao("Microfone")
    jarvis.anunciar_microfone()
    try:
        d = sd.query_devices(jarvis.DISPOSITIVO_MIC if jarvis.DISPOSITIVO_MIC is not None
                             else sd.default.device[0])
        fixo = jarvis.DISPOSITIVO_MIC is not None
        r.anota(OK if fixo else AVISO, "dispositivo", d["name"],
                "" if fixo else "ponha MICROFONE no .env; sem isso o Windows pode "
                                "escolher um cabo virtual e o Jarvis fica surdo")
    except Exception as e:
        r.anota(FALHA, "dispositivo", str(e), "verifique o MICROFONE no .env")
        return None

    print("           (fique quieto por 2s...)", flush=True)
    pico = _pico_do_microfone(2.0, jarvis)
    if pico is None:
        r.anota(FALHA, "captacao", "nao consegui abrir o microfone")
        return None
    if pico < 3.0:
        r.anota(FALHA, "captacao", "pico RMS %.1f -- silencio digital" % pico,
                "o dispositivo aberto nao e o seu microfone; rode com outro "
                "valor em MICROFONE")
    else:
        r.anota(OK, "captacao", "pico RMS %.1f em sala quieta (limiar de fala: %.0f)"
                % (pico, jarvis.VAD_LIMIAR))
    return pico


def _pico_do_microfone(segundos, jarvis):
    import numpy as np
    import sounddevice as sd
    f = queue.Queue()
    try:
        with sd.RawInputStream(samplerate=16000, channels=1, dtype="int16",
                               blocksize=1024, device=jarvis.DISPOSITIVO_MIC,
                               callback=lambda i, fr, t, s: f.put(bytes(i))):
            time.sleep(segundos)
    except Exception:
        return None
    picos = []
    while not f.empty():
        b = f.get()
        picos.append(float(np.sqrt(np.mean(
            np.frombuffer(b, dtype=np.int16).astype(np.float32) ** 2))))
    return max(picos) if picos else 0.0


def checar_eco(r, jarvis):
    """Mede se o microfone escuta os alto-falantes.

    E o que decide se barge-in por voz e possivel: se o eco passa do limiar do
    VAD, o Jarvis se interromperia sozinho, e nenhum ajuste de limiar separa os
    dois -- medido nesta maquina, o eco chega MAIS ALTO que a voz do usuario.
    """
    import numpy as np
    import threading

    r.secao("Eco acustico (decide o barge-in por voz)")
    print("           (vou falar uma frase e me ouvir; aguarde ~4s)", flush=True)
    try:
        voz = jarvis.Voz()
        pcm, taxa = voz.sintetizar("Verificando o retorno acustico dos alto falantes, senhor.")
        pcm = jarvis.presenca.tratar(pcm, taxa, reverb=jarvis.SALA_REVERB,
                                     graves=jarvis.SALA_GRAVES,
                                     compressao=jarvis.SALA_COMPRESSAO)
        arr = np.frombuffer(pcm, dtype=np.int16)
    except Exception as e:
        r.anota(AVISO, "eco", "nao consegui sintetizar: %s" % e)
        return

    resultado = {}
    t = threading.Thread(target=lambda: resultado.update(
        pico=_pico_do_microfone(3.5, jarvis)))
    t.start()
    time.sleep(0.2)
    try:
        jarvis.sd.play(arr, samplerate=taxa)
        jarvis.sd.wait()
    except Exception:
        pass
    t.join()

    eco = resultado.get("pico") or 0.0
    if eco > jarvis.VAD_LIMIAR:
        r.anota(AVISO, "retorno dos alto-falantes",
                "pico RMS %.0f, acima do limiar %.0f" % (eco, jarvis.VAD_LIMIAR),
                "barge-in por VOZ nao funciona assim: ele se interromperia "
                "sozinho. Use fones, ou a tecla de atalho")
    else:
        r.anota(OK, "retorno dos alto-falantes",
                "pico RMS %.0f, abaixo do limiar %.0f -- barge-in por voz e viavel"
                % (eco, jarvis.VAD_LIMIAR))


def checar_atalho(r):
    """O atalho de interromper consegue ser registrado nesta maquina?

    Vale checar porque RegisterHotKey e exclusivo no sistema: se outro
    programa ja tem a combinacao, o Jarvis sobe sem poder ser interrompido.
    Medido aqui, ctrl+alt+space e ctrl+shift+j -- os candidatos mais obvios --
    ja estavam tomados.
    """
    import atalho
    r.secao("Atalho para interromper a fala")
    pedida = (os.getenv("ATALHO_INTERROMPER") or "ctrl+shift+space").strip()
    if pedida.lower() in ("off", "nenhum", ""):
        r.anota(AVISO, "atalho", "desligado no .env",
                "sem ele nao ha como cortar a fala do Jarvis")
        return
    ok, usada, reserva = atalho.registrar_com_reserva(pedida, lambda: None)
    if ok and reserva:
        r.anota(AVISO, "atalho", "%s em uso; cairia para %s" % (pedida, usada),
                "escolha uma combinacao livre em ATALHO_INTERROMPER")
    elif ok:
        r.anota(OK, "atalho", usada)
    else:
        r.anota(FALHA, "atalho", "nenhuma combinacao livre (%s)" % usada,
                "defina uma que nao esteja em uso em ATALHO_INTERROMPER")


# ---------------------------------------------------------------------- cerebro

def checar_ollama(r, jarvis):
    import json
    r.secao("Cerebro (Ollama)")
    try:
        with urllib.request.urlopen(jarvis.OLLAMA + "/api/version", timeout=4) as resp:
            versao = json.loads(resp.read()).get("version", "?")
        r.anota(OK, "servico", "versao " + versao)
    except Exception as e:
        r.anota(FALHA, "servico", str(e),
                "inicie o Ollama: %LOCALAPPDATA%\\Programs\\Ollama\\ollama.exe serve")
        return

    try:
        with urllib.request.urlopen(jarvis.OLLAMA + "/api/tags", timeout=6) as resp:
            nomes = [m["name"] for m in json.loads(resp.read()).get("models", [])]
        if jarvis.MODELO_LLM in nomes:
            r.anota(OK, "modelo " + jarvis.MODELO_LLM, "instalado")
        else:
            r.anota(FALHA, "modelo " + jarvis.MODELO_LLM, "nao instalado",
                    "ollama pull " + jarvis.MODELO_LLM)
            return
    except Exception as e:
        r.anota(AVISO, "lista de modelos", str(e))

    try:
        t = jarvis.preaquecer()
        r.anota(OK if t < 20 else AVISO, "preaquecimento", "%.1fs" % t,
                "" if t < 20 else "acima de 18s costuma ser recarga do modelo; "
                                  "confira se num_ctx bate entre as chamadas")
    except Exception as e:
        r.anota(FALHA, "preaquecimento", str(e))
        return

    try:
        marca = {}
        t0 = time.perf_counter()
        resposta, _, _ = jarvis.pensar(
            "Bom dia, tudo certo?", "", [],
            ao_primeiro_token=lambda: marca.setdefault("t", time.perf_counter() - t0))
        ttft = marca.get("t", 0)
        r.anota(OK if ttft < 2.0 else AVISO, "1o token", "%.2fs" % ttft,
                "" if ttft < 2.0 else "acima de 2s: confira se algo grande entrou "
                                      "no prompt de todo turno")
        r.anota(OK if resposta else AVISO, "resposta", repr(resposta[:46]))
    except Exception as e:
        r.anota(FALHA, "geracao", str(e))


def checar_ferramentas(r, jarvis):
    r.secao("Ferramentas")
    r.anota(OK if jarvis.USAR_FERRAMENTAS else AVISO, "function calling",
            "ligado (%d ferramentas)" % len(jarvis.FERRAMENTAS_LLM)
            if jarvis.USAR_FERRAMENTAS else "DESLIGADO (modo legado por substring)",
            "" if jarvis.USAR_FERRAMENTAS else "USAR_FERRAMENTAS=True no jarvis.py")

    casos = [("Jarvis, coloca vermelho", "mudar_tema"),
             ("quanto ta o dolar?", "obter_cotacao"),
             ("bom dia, tudo certo?", None)]
    acertos = 0
    for pergunta, esperado in casos:
        try:
            _, _, chamadas = jarvis.pensar(pergunta, "", [])
            obtido = chamadas[0]["function"]["name"] if chamadas else None
        except Exception:
            obtido = "erro"
        acertos += (obtido == esperado)
    r.anota(OK if acertos == len(casos) else AVISO, "roteamento por intencao",
            "%d/%d casos" % (acertos, len(casos)),
            "" if acertos == len(casos) else "reveja as descricoes em FERRAMENTAS_LLM")


def checar_percepcao(r, percepcao):
    r.secao("Leitura de tela")
    try:
        percepcao.contexto()                      # acorda a arvore do Chromium
        texto, ms = percepcao.contexto(limite_caracteres=1200)
        propria = percepcao.e_a_propria_interface() or percepcao.e_o_proprio_console()
        r.anota(OK if ms < 500 else AVISO, "UI Automation", "%.0f ms, %d caracteres"
                % (ms, len(texto)))
        r.anota(OK, "janela em foco",
                "e do proprio Jarvis (contexto neutro, como deve ser)" if propria
                else repr(texto[:52]))
    except Exception as e:
        r.anota(FALHA, "UI Automation", str(e))


# -------------------------------------------------------------------------- voz

def checar_vozes(r, jarvis):
    r.secao("Vozes (cadeia de reserva Cartesia -> Edge -> Piper)")
    voz = jarvis.Voz()
    for nome, fn in (("cartesia", voz._cartesia_pcm),
                     ("edge", voz._edge_pcm),
                     ("piper", voz._piper_pcm)):
        try:
            t0 = time.perf_counter()
            pcm, taxa = fn("Teste de diagnostico.")
            dt = time.perf_counter() - t0
            r.anota(OK, "motor " + nome, "%d bytes a %d Hz em %.2fs" % (len(pcm), taxa, dt))
        except Exception as e:
            grave = (nome == "piper")     # o Piper e o ultimo recurso offline
            r.anota(FALHA if grave else AVISO, "motor " + nome, str(e)[:70],
                    "sem o Piper o Jarvis fica mudo se a rede cair" if grave else "")
    r.anota(OK, "motor em uso", jarvis.MOTOR_VOZ)


def checar_apis(r, ferramentas):
    r.secao("APIs externas")
    for nome, fn, arg in (("cotacao (AwesomeAPI)", ferramentas.obter_cotacao, "USD-BRL"),
                          ("clima (Open-Meteo)", ferramentas.obter_clima, None)):
        t0 = time.perf_counter()
        try:
            resposta = fn(arg)
            dt = time.perf_counter() - t0
            if not resposta:
                r.anota(AVISO, nome, "sem resposta em %.2fs" % dt,
                        "pode ser rede passageira; o Jarvis fala o dado antigo "
                        "se tiver cache")
            elif resposta.startswith("A rede falhou"):
                r.anota(AVISO, nome, "respondeu do cache (%.2fs)" % dt)
            else:
                r.anota(OK, nome, "%.2fs" % dt)
        except Exception as e:
            r.anota(FALHA, nome, str(e)[:60])


# ------------------------------------------------------------------- interfaces

def checar_ponte(r, hud_bridge):
    import json
    r.secao("Ponte da HUD")
    token = hud_bridge.token_atual()
    r.anota(OK if token else FALHA, ".hud_token",
            "%d caracteres" % len(token) if token else "ausente",
            "" if token else "o hud_bridge gera no boot; rode o Jarvis normalmente")

    base = "http://127.0.0.1:%d/events" % hud_bridge.PORTA_HUD
    try:
        urllib.request.urlopen(base, timeout=3)
        r.anota(FALHA, "acesso sem token", "CONSEGUIU CONECTAR",
                "qualquer site aberto no navegador conseguiria ler o que voce fala")
    except urllib.error.HTTPError as e:
        r.anota(OK if e.code == 403 else AVISO, "acesso sem token",
                "recusado com HTTP %d" % e.code)
    except Exception as e:
        r.anota(AVISO, "acesso sem token", str(e)[:50])

    try:
        resp = urllib.request.urlopen(base + "?token=" + token, timeout=3)
        linha = resp.readline()
        r.anota(OK if b"connected" in linha else AVISO, "acesso com token",
                "stream aberto")
        resp.close()
    except Exception as e:
        r.anota(FALHA, "acesso com token", str(e)[:60])


def checar_interfaces(r, hud_bridge):
    r.secao("Interfaces (abre e fecha cada uma)")
    for modo, titulo in (("bordas", "JARVIS_AMBIENT_EDGES"),
                         ("orbe", "JARVIS_NATIVE_ORB"),
                         ("completo", "J.A.R.V.I.S")):
        t0 = time.perf_counter()
        hud_bridge.alternar_interface(modo)
        apareceu = None
        for _ in range(60):                       # ate 15s
            time.sleep(0.25)
            if hud_bridge._janela_existe(titulo):
                apareceu = time.perf_counter() - t0
                break
        if apareceu:
            r.anota(OK, "modo " + modo, "janela em %.2fs" % apareceu)
        else:
            r.anota(FALHA, "modo " + modo, "janela nao apareceu em 15s",
                    "veja as ultimas linhas de .interface_erros.log")
    hud_bridge.fechar_interfaces_anteriores()
    hud_bridge._matar_edge_do_perfil()


# ------------------------------------------------------------------------ ponto de entrada

def rodar(rapido=False):
    print("=" * 66)
    print("  DOUTOR DO JARVIS")
    if not rapido:
        print("  (vai tocar som e abrir as interfaces; use --rapido para pular)")
    print("=" * 66)

    r = Relatorio()
    import jarvis, percepcao, ferramentas, hud_bridge

    checar_ambiente(r)
    checar_env(r)
    checar_microfone(r, jarvis)
    if not rapido:
        checar_eco(r, jarvis)
    checar_atalho(r)
    checar_ollama(r, jarvis)
    checar_ferramentas(r, jarvis)
    checar_percepcao(r, percepcao)
    checar_vozes(r, jarvis)
    checar_apis(r, ferramentas)

    hud_bridge.iniciar(auto_abrir=False)
    checar_ponte(r, hud_bridge)
    if not rapido:
        checar_interfaces(r, hud_bridge)

    return r.resumo()
