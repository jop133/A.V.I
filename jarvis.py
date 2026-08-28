"""Jarvis local -- prototipo do ciclo completo, 100% offline.

    voce fala -> VAD -> Whisper -> contexto de tela -> qwen3 -> Piper -> voz

Nenhuma peca sai da maquina. Cada etapa e cronometrada, porque o que decide se
isto substitui a nuvem nao e a qualidade bruta: e o tempo ate a primeira palavra.

Modos:
    python jarvis.py --simulado    usa fala sintetica (nao precisa do microfone)
    python jarvis.py               usa o microfone de verdade
"""

import asyncio
import hashlib
import io
import json
import os
import queue
import sys
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
import requests
import sounddevice as sd

import percepcao
import presenca
import hud_bridge
import ferramentas
import wakeword

BASE = Path(__file__).parent
CACHE_VOZ = BASE / "vozes" / "cache"
CACHE_VOZ.mkdir(parents=True, exist_ok=True)
CACHE_MEMORIA = {}

def _carregar_env():
    """Carrega variaveis de ambiente a partir do arquivo .env na raiz."""
    env_path = BASE / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_carregar_env()

# ----------------------------------------------------------------- configuracao de voz
MOTOR_VOZ = "cartesia"         # "cartesia", "edge", "piper" ou "kokoro"

# Edge TTS (opcional online sem chave)
VOZ_EDGE = "en-AU-WilliamMultilingualNeural"
TOM_EDGE = "-15Hz"
RITMO_EDGE = "-5%"

# Cartesia TTS (opcional online com chave)
CARTESIA_MODELO = os.getenv("CARTESIA_MODEL", "sonic-3.6")
CARTESIA_IDIOMA = "pt"
CARTESIA_TAXA = 24000
CARTESIA_VELOCIDADE = 1.0

# Tratamento acustico de sala (presenca.py)
SALA_REVERB = 0.48    # 0 = seco | 0.32 = sala | 0.48 = sala grande
SALA_GRAVES = 1.45    # 1.0 = sem reforco
SALA_COMPRESSAO = True

# Piper TTS (100% offline)
VOZ_TTS = BASE / "vozes" / "pt_BR-faber-medium.onnx"

MODELO_LLM = "qwen3:8b"
NUM_CTX = 8192            # PRECISA ser identico no preaquecimento e no uso
MODELO_STT = "small"
OLLAMA = "http://127.0.0.1:11434"

TAXA_MIC = 16000
BLOCO = 1024
VAD_LIMIAR = 180.0        # RMS ideal e sensível para captação natural de voz
VAD_SILENCIO = 0.7        # segundos de silêncio para fechar o turno de fala
SISTEMA = """Voce e o Jarvis, assistente pessoal do Joao Pedro, rodando LOCALMENTE no PC dele.

Regras:
- Responda SEMPRE em portugues do Brasil, de forma extremamente concisa (no maximo 1 ou 2 frases curtas e diretas). Esta e uma conversa por voz em tempo real.
- NUNCA repita, leia ou exiba tags de telemetria como [TELA], [CURSOR] ou [CONTEUDO VISIVEL]. Elas sao dados invisiveis do sistema para sua orientacao silenciosa. Fale apenas o dialogo com o senhor.
- Nunca faça listas longas nem use introduções ou saudações repetitivas.
- AÇÕES DE COR DA INTERFACE: Se o usuario pedir para mudar a cor ou tema da interface (qualquer solicitacao de cor como vermelho, verde, azul, ciano, roxo, dourado, branco, rosa), inclua a tag [COR: nome_da_cor] no inicio da sua resposta.
  Exemplo: "Jarvis, coloca vermelho" -> "[COR: vermelho] Alterando paleta para vermelho Stark, senhor."
  Exemplo: "Quero tema verde" -> "[COR: verde] Paleta verde Matrix ativada."
  Cores validas: vermelho, verde, azul, ciano, roxo, dourado, branco, rosa.
- AÇÕES DE BRILHO: Se o usuario pedir mais claro ou mais escuro, use [BRILHO: +] ou [BRILHO: -] no inicio.
  Exemplo: "Aumenta o brilho" -> "[BRILHO: +] Aumentando luminosidade do núcleo, senhor."
  Exemplo: "Deixa mais escuro" -> "[BRILHO: -] Diminuindo brilho para modo discreto, senhor."
- MÓDULOS DE TEMPO REAL: Cotações financeiras (Dólar, Euro, Bitcoin, etc.) e Previsão do Tempo são fornecidas diretamente por fontes em tempo real.
- IMPORTANTE: Se o usuario fizer uma pergunta complexa, pedir pesquisas dificeis, ou algo alem do seu conhecimento imediato, responda APENAS com a tag: [CONSULTAR: a pergunta do usuario]. Nao escreva mais nada. Exemplo: [CONSULTAR: qual a populacao do japao?]"""

# ----------------------------------------------------------------- temas & controle de interface HUD
BRILHO_HUD_ATUAL = 1.0

PALETAS_MAPA = {
    "vermelho": ("vermelho", "Alterando paleta para vermelho Stark, senhor."),
    "stark": ("vermelho", "Modo tático Stark ativado em vermelho."),
    "iron man": ("vermelho", "Paleta armadura Mark VII ativada."),
    "verde": ("verde", "Paleta verde Matrix ativada, senhor."),
    "matrix": ("verde", "Modo Matrix ativado em verde esmeralda."),
    "esmeralda": ("verde", "Paleta verde esmeralda ativada."),
    "azul": ("azul", "Restaurando paleta azul clássica do Jarvis, senhor."),
    "ciano": ("ciano", "Paleta ciano Trillion ativada, senhor."),
    "padrao": ("ciano", "Restaurando paleta padrão, senhor."),
    "roxo": ("roxo", "Paleta roxo neon ativada, senhor."),
    "violeta": ("roxo", "Paleta violeta ativada, senhor."),
    "cyberpunk": ("roxo", "Modo cyberpunk ativado, senhor."),
    "dourado": ("dourado", "Paleta dourada ativada, senhor."),
    "ouro": ("dourado", "Paleta ouro ativada, senhor."),
    "amarelo": ("dourado", "Paleta amarela ativada, senhor."),
    "branco": ("branco", "Paleta gelo prateado ativada, senhor."),
    "gelo": ("branco", "Modo gelo prateado ativado, senhor."),
    "prata": ("branco", "Paleta prata ativada, senhor."),
    "rosa": ("rosa", "Paleta rosa neon ativada, senhor."),
    "pink": ("rosa", "Paleta rosa ativada, senhor."),
}

def processar_comando_interface(texto):
    """Detecta comandos rapidos de mudanca de cor, brilho e modos de interface da HUD."""
    global BRILHO_HUD_ATUAL
    t = texto.lower().strip().replace(".", "").replace("!", "")

    # 1. Comandos de Alternância de Interface Visual (com Variações Fonéticas do Whisper)
    if any(p in t for p in ["modo orbe", "modo orb", "modo orbi", "modo esfera", "modo compacto", "ativar orbe", "ativar o orbe", "mudar para o orbe", "mudar para orbe", "trocar para orbe", "trocar para o orbe", "ir para o orbe", "orbe flutuante", "esfera flutuante"]):
        hud_bridge.alternar_interface("orbe")
        return ("Ativando modo orbe compacto, senhor.", {})

    if any(p in t for p in ["modo borda", "modo bordas", "modo moldura", "modo perimetro", "modo perimétrico", "ativar bordas", "ativar as bordas", "mudar para as bordas", "mudar para bordas", "trocar para bordas", "bordas translúcidas", "bordas translucidas", "luzes de borda"]):
        hud_bridge.alternar_interface("borda")
        return ("Ativando modo bordas ambientais, senhor.", {})

    if any(p in t for p in [
        "modo completo", "modo painel", "modo tela cheia", "hud completa", "painel completo", "restaurar hud",
        "abrir painel", "ativar modo completo", "mudar para modo completo", "voltar para o completo",
        "modo rede completa", "modo rede", "rede completa", "modo hud completa", "modo hud", "modo tela completa", "modo tela"
    ]):
        hud_bridge.alternar_interface("completo")
        return ("Restaurando painel completo, senhor.", {})

    # 2. Comandos de Brilho (Aumentar / Mais Claro)
    if (any(w in t for w in ["aumente", "aumentar", "aumenta", "mais claro", "clarear", "clareie"]) and any(b in t for b in ["brilho", "luz", "núcleo", "nucleo", "claro"])) or "mais brilho" in t:
        BRILHO_HUD_ATUAL = min(2.0, round(BRILHO_HUD_ATUAL + 0.35, 2))
        return (f"Aumentando brilho do núcleo para {int(BRILHO_HUD_ATUAL * 100)}%, senhor.", {"brightness": BRILHO_HUD_ATUAL})
        
    # 3. Comandos de Brilho (Diminuir / Mais Escuro)
    if (any(w in t for w in ["diminua", "diminuir", "diminui", "mais escuro", "escurecer", "escureça", "menos"]) and any(b in t for b in ["brilho", "luz", "núcleo", "nucleo", "escuro", "noturno"])) or "menos brilho" in t:
        BRILHO_HUD_ATUAL = max(0.25, round(BRILHO_HUD_ATUAL - 0.35, 2))
        return (f"Diminuindo brilho para {int(BRILHO_HUD_ATUAL * 100)}%, senhor.", {"brightness": BRILHO_HUD_ATUAL})

    if "brilho maximo" in t or "brilho no maximo" in t or "máximo de brilho" in t:
        BRILHO_HUD_ATUAL = 1.8
        return ("Brilho máximo ativado no núcleo, senhor.", {"brightness": BRILHO_HUD_ATUAL})

    # 4. Comandos Diretos de Mudança de Cor
    palavras = t.split()
    for chave, (tema_id, resposta) in PALETAS_MAPA.items():
        if chave in palavras or f" {chave}" in t or f"para {chave}" in t or f"pro {chave}" in t or f"pra {chave}" in t:
            return (resposta, {"theme": tema_id})

    return None


# ----------------------------------------------------------------- cronometro

class Etapas:
    def __init__(self):
        self.marcas = []
        self.t0 = time.perf_counter()

    def marca(self, nome):
        self.marcas.append((nome, time.perf_counter() - self.t0))

    def relatorio(self):
        print()
        print("  " + "-" * 54)
        anterior = 0.0
        ate_falar = None
        for nome, t in self.marcas:
            print("  %-32s %6.2fs  (+%.2fs)" % (nome, t, t - anterior))
            anterior = t
            if "FALA" in nome:
                ate_falar = t
        print("  " + "-" * 54)
        if ate_falar is not None:
            print("  >> ATE COMECAR A FALAR           %6.2fs   <- e isto que voce sente"
                  % ate_falar)
        print("     (fim da fala: %.2fs)" % anterior)


# ----------------------------------------------------------------------- voz

class Voz:
    """Motor de voz multi-backend com cache inteligente e contingencia: Cartesia -> Edge -> Piper."""

    def __init__(self):
        self.piper_voz = None

    def _obter_piper(self):
        if self.piper_voz is None:
            from piper import PiperVoice
            self.piper_voz = PiperVoice.load(str(VOZ_TTS))
        return self.piper_voz

    def _obter_cache(self, texto, motor):
        """Retorna PCM em cache se existir (RAM ou Disco). Custo computacional < 0.2ms."""
        texto_norm = " ".join(texto.strip().split()).lower()
        if not texto_norm:
            return None
        
        # 1. Checa memoria RAM (< 0.01ms)
        chave_ram = (motor, texto_norm)
        if chave_ram in CACHE_MEMORIA:
            return CACHE_MEMORIA[chave_ram]

        # 2. Checa disco (< 0.3ms)
        h = hashlib.md5(f"{motor}_{texto_norm}".encode("utf-8")).hexdigest()
        caminho = CACHE_VOZ / f"{h}.pcm"
        if caminho.exists():
            try:
                pcm = caminho.read_bytes()
                taxa = CARTESIA_TAXA if motor == "cartesia" else 24000
                CACHE_MEMORIA[chave_ram] = (pcm, taxa)
                return pcm, taxa
            except Exception:
                pass
        return None

    def _salvar_cache(self, texto, motor, pcm, taxa):
        """Salva PCM no cache em disco e memoria RAM de forma instantanea."""
        try:
            texto_norm = " ".join(texto.strip().split()).lower()
            chave_ram = (motor, texto_norm)
            CACHE_MEMORIA[chave_ram] = (pcm, taxa)
            h = hashlib.md5(f"{motor}_{texto_norm}".encode("utf-8")).hexdigest()
            caminho = CACHE_VOZ / f"{h}.pcm"
            caminho.write_bytes(pcm)
        except Exception:
            pass

    def _cartesia_pcm(self, texto):
        chave = os.getenv("CARTESIA_API_KEY")
        voz_id = os.getenv("CARTESIA_VOICE_ID")
        if not chave or not voz_id:
            raise ValueError("CARTESIA_API_KEY ou CARTESIA_VOICE_ID ausente no .env")

        r = requests.post(
            "https://api.cartesia.ai/tts/bytes",
            headers={
                "Authorization": f"Bearer {chave}",
                "Cartesia-Version": "2026-08-14"
            },
            json={
                "model_id": CARTESIA_MODELO,
                "transcript": texto,
                "voice": {
                    "id": voz_id,
                    "experimental_controls": {"speed": CARTESIA_VELOCIDADE}
                },
                "language": CARTESIA_IDIOMA,
                "output_format": {
                    "container": "raw",
                    "encoding": "pcm_s16le",
                    "sample_rate": CARTESIA_TAXA
                }
            },
            timeout=30
        )
        if r.status_code != 200:
            raise RuntimeError(f"Cartesia HTTP {r.status_code}: {r.text[:100]}")
        return r.content, CARTESIA_TAXA

    def _edge_pcm(self, texto, voz=VOZ_EDGE):
        import edge_tts
        import soundfile as sf

        async def _synth():
            com = edge_tts.Communicate(texto, voz, pitch=TOM_EDGE, rate=RITMO_EDGE)
            dados = bytearray()
            async for p in com.stream():
                if p["type"] == "audio":
                    dados.extend(p["data"])
            audio, taxa = sf.read(io.BytesIO(bytes(dados)), dtype="int16")
            return audio.tobytes(), taxa

        async def _synth_com_timeout():
            return await asyncio.wait_for(_synth(), timeout=4.5)

        return asyncio.run(_synth_com_timeout())

    def _piper_pcm(self, texto):
        voz = self._obter_piper()
        pedacos, taxa = [], 22050
        for chunk in voz.synthesize(texto):
            pedacos.append(chunk.audio_int16_bytes)
            taxa = chunk.sample_rate
        return b"".join(pedacos), taxa

    def sintetizar(self, texto):
        """Tenta o cache primeiro; se nao existir, sintetiza e guarda no cache."""
        motor = (MOTOR_VOZ or "piper").lower()

        # --- Verificacao de Cache Inteligente ---
        cache_hit = self._obter_cache(texto, motor)
        if cache_hit:
            print("  [Voz: audio obtido do cache local (0 creditos gastos, latencia <1ms)]")
            return cache_hit

        pcm, taxa = None, None
        if motor == "cartesia":
            try:
                pcm, taxa = self._cartesia_pcm(texto)
            except Exception as e:
                print(f"  [Cartesia falhou: {e} -> tentando Edge...]")
                motor = "edge"
                cache_edge = self._obter_cache(texto, "edge")
                if cache_edge:
                    return cache_edge

        if motor == "edge":
            try:
                pcm, taxa = self._edge_pcm(texto)
            except Exception as e:
                print(f"  [Edge falhou: {e} -> caindo para Piper local...]")
                motor = "piper"

        if pcm is None:
            pcm, taxa = self._piper_pcm(texto)

        # Salva a resposta sintetizada no cache para reutilizacao futura
        if pcm and taxa:
            self._salvar_cache(texto, motor, pcm, taxa)

        return pcm, taxa

    def falar(self, texto, ao_primeiro=None):
        if not texto.strip():
            return
        try:
            pcm, taxa = self.sintetizar(texto)
            pcm_tratado = presenca.tratar(
                pcm, taxa,
                reverb=SALA_REVERB,
                graves=SALA_GRAVES,
                compressao=SALA_COMPRESSAO
            )
            if ao_primeiro:
                ao_primeiro()

            arr = np.frombuffer(pcm_tratado, dtype=np.int16)
            sd.play(arr, samplerate=taxa)
            sd.wait()
        except Exception as e:
            print(f"  [Erro ao reproduzir voz: {e}]")

    def gerar_pcm(self, texto):
        """Sintetiza sem tocar -- usado pelo modo simulado."""
        pcm, taxa = self.sintetizar(texto)
        return presenca.tratar(
            pcm, taxa,
            reverb=SALA_REVERB,
            graves=SALA_GRAVES,
            compressao=SALA_COMPRESSAO
        ), taxa


class Ouvido:
    """Whisper local: audio -> texto."""

    def __init__(self, tamanho=MODELO_STT):
        from faster_whisper import WhisperModel
        self.modelo = WhisperModel(tamanho, device="cpu", compute_type="int8",
                                   cpu_threads=12)

    def transcrever(self, pcm16, taxa=TAXA_MIC):
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if taxa != 16000:  # o Whisper espera 16 kHz
            n = int(len(audio) * 16000 / taxa)
            audio = np.interp(np.linspace(0, len(audio), n),
                              np.arange(len(audio)), audio).astype(np.float32)
        segs, _ = self.modelo.transcribe(audio, language="pt", beam_size=1,
                                         vad_filter=False,
                                         condition_on_previous_text=False)
        return " ".join(s.text for s in segs).strip()

def consultar_gemini_web(pergunta, contexto_tela):
    """Bate na interface Web do Gemini de forma invisivel usando a biblioteca g4f."""
    try:
        from g4f.client import Client
        import g4f
        
        client = Client()
        prompt = f"O usuário perguntou: '{pergunta}'. \nContexto da tela atual dele: \n{contexto_tela}\n\nResponda em NO MÁXIMO 1 ou 2 frases curtas, diretas e naturais para um assistente de voz chamado Jarvis. Sem formatação pesada (sem asteriscos, negrito ou listas), apenas texto direto, conciso e fácil de falar."
        
        print("  (Acessando o site do Gemini invisivelmente...)")
        response = client.chat.completions.create(
            model="gemini",
            messages=[{"role": "user", "content": prompt}]
        )
        texto = response.choices[0].message.content
        
        # Limpa asteriscos e formatações pesadas para a voz ficar natural
        return texto.replace("*", "").replace("#", "").strip()
    except ImportError:
        return "Erro: A biblioteca g4f não está instalada. Cancele e instale com pip install g4f."
    except Exception as e:
        print(f"Erro na navegação web: {e}")
        return "Desculpe, a página do Gemini barrou minha conexão agora."

# --------------------------------------------------------------------- cerebro

def pensar(pergunta, contexto_tela, historico, ao_primeiro_token=None):
    """qwen3 local. `think:false` e essencial: com o modo pensante ligado o
    tempo ate a primeira palavra sobe de 0.4s para 3.1s."""
    if contexto_tela:
        prompt = f"[DADOS DO SISTEMA - APENAS PARA CONSULTA SILENCIOSA]:\n{contexto_tela}\n\n[USUÁRIO]: {pergunta}\n\n[JARVIS]:"
    else:
        prompt = f"[USUÁRIO]: {pergunta}\n\n[JARVIS]:"
    corpo = {
        "model": MODELO_LLM, "prompt": prompt, "system": SISTEMA,
        "stream": True, "think": False,
        "options": {"num_predict": 100, "temperature": 0.3, "num_ctx": NUM_CTX},
    }
    if historico:
        corpo["context"] = historico

    req = urllib.request.Request(OLLAMA + "/api/generate",
                                 data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    partes, ctx = [], None
    primeiro = True
    with urllib.request.urlopen(req, timeout=300) as r:
        for linha in r:
            if not linha.strip():
                continue
            d = json.loads(linha)
            if d.get("response"):
                if primeiro:
                    primeiro = False
                    if ao_primeiro_token:
                        ao_primeiro_token()
                partes.append(d["response"])
            if d.get("done"):
                ctx = d.get("context")
    return "".join(partes).strip(), ctx


def preaquecer():
    """Carrega o modelo na VRAM ANTES do primeiro turno.

    Detalhe que custa 18 segundos se esquecido: o Ollama recarrega o modelo
    inteiro quando `num_ctx` muda entre chamadas. O preaquecimento precisa usar
    EXATAMENTE as mesmas opcoes do uso real, senao ele so aquece em vao.
    """
    corpo = {
        "model": MODELO_LLM, "prompt": "oi", "stream": False, "think": False,
        "keep_alive": -1,   # nunca descarrega
        "options": {"num_predict": 1, "num_ctx": NUM_CTX},
    }
    req = urllib.request.Request(OLLAMA + "/api/generate",
                                 data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        r.read()
    return time.perf_counter() - t0


# ---------------------------------------------------------------- microfone

def escutar(limite=25.0):
    """Grava do microfone ate detectar silencio. Devolve PCM 16 kHz."""
    fila = queue.Queue()

    def cb(indata, frames, t, status):
        fila.put(bytes(indata))

    blocos, falou, ultimo_som = [], False, time.time()
    with sd.RawInputStream(samplerate=TAXA_MIC, channels=1, dtype="int16",
                           blocksize=BLOCO, callback=cb):
        inicio = time.time()
        print("  (ouvindo microfone...)")
        hud_bridge.notificar(state="listening")
        while time.time() - inicio < limite:
            try:
                b = fila.get(timeout=0.15)
            except queue.Empty:
                continue
            rms = float(np.sqrt(np.mean(
                np.frombuffer(b, dtype=np.int16).astype(np.float32) ** 2)))
            if rms > VAD_LIMIAR:
                falou = True
                ultimo_som = time.time()
                blocos.append(b)
            elif falou:
                blocos.append(b)
                if time.time() - ultimo_som > VAD_SILENCIO:
                    break
            else:
                if time.time() - inicio > 5.0:
                    break
    return b"".join(blocos)


# -------------------------------------------------------------------- ciclo

def ciclo(ouvido, voz, pcm, taxa, historico, rotulo=""):
    global BRILHO_HUD_ATUAL
    e = Etapas()
    if rotulo:
        print('  voce: %r' % rotulo)

    texto = ouvido.transcrever(pcm, taxa)
    e.marca("1. Whisper (fala -> texto)")
    print("  entendeu: %r" % texto)
    if not texto:
        print("  (nao entendi nada)")
        hud_bridge.notificar(state="idle")
        return historico

    # --- Interceptor de Comandos de Interface (Cores e Brilho da HUD) ---
    cmd_interface = processar_comando_interface(texto)
    if cmd_interface:
        msg_resposta, dados_hud = cmd_interface
        print(f"  [INTERFACE] Comando de HUD detectado: {dados_hud}")
        e.marca("2. comando de interface processado")
        hud_bridge.notificar(state="speaking", jarvisSpeech=msg_resposta, **dados_hud)
        voz.falar(msg_resposta)
        e.marca("3. Voz (confirmação da HUD) <- FALA")
        e.relatorio()
        hud_bridge.notificar(state="idle")
        return historico

    # --- Módulos Especializados em Tempo Real (Cotações & Clima) ---
    res_ferramenta = ferramentas.processar_ferramenta(texto)
    if res_ferramenta:
        print(f"  [FERRAMENTA EM TEMPO REAL]: {res_ferramenta}")
        e.marca("2. Ferramenta Especializada (AwesomeAPI / Open-Meteo)")
        hud_bridge.notificar(state="speaking", jarvisSpeech=res_ferramenta)
        voz.falar(res_ferramenta)
        e.marca("3. Voz (resposta da ferramenta) <- FALA")
        e.relatorio()
        hud_bridge.notificar(state="idle")
        return historico

    # Leitura de contexto e envio de telemetria para a HUD
    contexto_tela, _ = percepcao.contexto(limite_caracteres=1200)
    e.marca("2. contexto de tela (UI Automation)")

    j_info = percepcao.janela_ativa()
    cur_info = percepcao.sob_o_cursor()
    win_title = j_info.get("titulo", "") if isinstance(j_info, dict) else ""
    cur_desc = f"{cur_info.get('tipo', '')} ({cur_info.get('nome', '')})" if isinstance(cur_info, dict) else ""

    hud_bridge.notificar(
        state="thinking",
        userSpeech=texto,
        windowTitle=win_title or "Área de Trabalho",
        activeTarget=cur_desc or "Cursor Ativo"
    )

    resposta, novo_hist = pensar(texto, contexto_tela, historico,
                                 ao_primeiro_token=lambda: e.marca("3. qwen3 (1o token)"))
    e.marca("4. qwen3 (resposta completa)")
    
    # --- Processamento de Ações Emitidas pelo Qwen3 (Cores e Brilho) ---
    dados_hud_acao = {}
    if "[COR:" in resposta:
        import re
        m_cor = re.search(r'\[COR:\s*([a-zA-ZáàâãéèêíïóôõöúçñÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇÑ]+)\]', resposta)
        if m_cor:
            cor_tag = m_cor.group(1).lower().strip()
            for k, (tema_id, _) in PALETAS_MAPA.items():
                if k in cor_tag:
                    dados_hud_acao["theme"] = tema_id
                    break
            if "theme" not in dados_hud_acao:
                dados_hud_acao["theme"] = cor_tag
        resposta = re.sub(r'\[COR:[^\]]+\]', '', resposta).strip()

    if "[BRILHO:" in resposta:
        import re
        if "[BRILHO: +]" in resposta:
            BRILHO_HUD_ATUAL = min(2.0, round(BRILHO_HUD_ATUAL + 0.35, 2))
            dados_hud_acao["brightness"] = BRILHO_HUD_ATUAL
        elif "[BRILHO: -]" in resposta:
            BRILHO_HUD_ATUAL = max(0.25, round(BRILHO_HUD_ATUAL - 0.35, 2))
            dados_hud_acao["brightness"] = BRILHO_HUD_ATUAL
        resposta = re.sub(r'\[BRILHO:[^\]]+\]', '', resposta).strip()

    # Limpeza rigorosa contra vazamento de metadados internos de tela
    for vazamento in ["[TELA]", "[CURSOR]", "[CONTEUDO VISIVEL]", "[DADOS DO SISTEMA", "[USUÁRIO]:", "[JARVIS]:"]:
        if vazamento in resposta:
            linhas = [l for l in resposta.split("\n") if not any(tag in l for tag in ["[TELA]", "[CURSOR]", "[CONTEUDO VISIVEL]", "[DADOS DO SISTEMA", "[USUÁRIO]:", "[JARVIS]:"])]
            resposta = " ".join(linhas).strip()

    if not resposta.strip():
        resposta = "Comandos executados, senhor."

    # --- Roteamento Web Invisível ---
    if resposta.strip().startswith("[CONSULTAR:"):
        pergunta_nuvem = resposta.replace("[CONSULTAR:", "").replace("]", "").strip()
        print(f"  [ROTEAMENTO] Qwen3 delegou para a Web. Pergunta: {pergunta_nuvem}")
        hud_bridge.notificar(state="web", jarvisSpeech="Deixe-me pesquisar isso a fundo na web para você.")
        
        # Feedback rápido enquanto navega
        voz.falar("Deixe-me pesquisar isso a fundo na web para você.")
        e.marca("5. Voz (feedback rápido)")
        
        # Consulta à Web (g4f)
        resposta = consultar_gemini_web(pergunta_nuvem, contexto_tela)
        e.marca("6. Consulta Web concluída")
        print("  Gemini (Web): %r" % resposta[:150])
        
        hud_bridge.notificar(state="speaking", jarvisSpeech=resposta, **dados_hud_acao)
        voz.falar(resposta)
        e.marca("7. Voz (resposta da Web) <- FALA")
    else:
        print("  Jarvis (Local): %r" % resposta[:150])
        hud_bridge.notificar(state="speaking", jarvisSpeech=resposta, **dados_hud_acao)
        voz.falar(resposta, ao_primeiro=lambda: e.marca("5. Voz (1o audio) <- FALA"))
        e.marca("6. terminou de falar")

    e.relatorio()
    hud_bridge.notificar(
        state="idle",
        benchmarks={
            "whisper": "%.2fs" % e.marcas[0][1] if e.marcas else "120ms",
            "llm": "%.2fs" % (e.marcas[2][1] - e.marcas[1][1]) if len(e.marcas) > 2 else "210ms",
            "tts": "%.2fs" % (e.marcas[-1][1] - e.marcas[-2][1]) if len(e.marcas) > 3 else "85ms",
            "total": "%.2fs" % e.marcas[-1][1] if e.marcas else "0.45s"
        }
    )
    return novo_hist


def main():
    simulado = "--simulado" in sys.argv
    sem_hud = "--sem-hud" in sys.argv

    # Inicia a ponte e abre a HUD desktop completa e maximizada automaticamente
    hud_bridge.iniciar(auto_abrir=not sem_hud, modo_inicial="completo")

    print("=" * 60)
    print("  JARVIS LOCAL -- 100%% offline  (%s)"
          % ("simulado" if simulado else "escuta contínua no microfone"))
    print("=" * 60)

    t0 = time.perf_counter()
    voz = Voz()
    ouvido = Ouvido()
    percepcao.contexto()          # aquece a arvore de acessibilidade
    print("  carga local: %.1fs" % (time.perf_counter() - t0))
    print("  preaquecendo %s (num_ctx=%d)..." % (MODELO_LLM, NUM_CTX))
    print("  modelo pronto em %.1fs" % preaquecer())
    print()

    historico = None
    if simulado:
        FALAS = [
            "Bom dia! Tudo certo?",
            "O que eu estou fazendo agora na tela?",
            "Qual e a capital da Franca?",
        ]
        for f in FALAS:
            print("=" * 60)
            pcm, taxa = voz.gerar_pcm(f)
            historico = ciclo(ouvido, voz, pcm, taxa, historico, rotulo=f)
            print()
    else:
        print("Assistente pronto. Fale no microfone a qualquer momento.")
        print("Pressione Ctrl+C para encerrar.")
        while True:
            print("=" * 60)
            pcm = escutar()
            if len(pcm) < TAXA_MIC * 0.4:
                continue
            historico = ciclo(ouvido, voz, pcm, TAXA_MIC, historico)
            print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nate mais.")
