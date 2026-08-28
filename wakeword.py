"""Módulo de Ativação Contínua por Palavra-Chave (Wake-Word: 'Hey Jarvis' / 'Jarvis')

Permite que o assistente fique em repouso silencioso (Standby) consumindo quase 0% de CPU
e acorde instantaneamente ao ouvir o nome 'Jarvis'.

Possui suporte a:
1. OpenWakeWord (ONNX 'hey_jarvis' se instalado)
2. Micro-buffer VAD com Whisper Tiny/Small (Fallback robusto e nativo sem dependências extras)
3. Janela de Diálogo Contínuo (Follow-up de 5 segundos após a resposta do Jarvis)
"""

import queue
import re
import time
import numpy as np
import sounddevice as sd

# ---------------------------------------------------------------------------
# Configurações do Wake-Word
# ---------------------------------------------------------------------------
TAXA_AMOSTRAGEM = 16000
BLOCO_AMOSTRAS = 1024
LIMIAR_VAD_STANDBY = 550.0   # RMS mínimo para iniciar detecção no standby
TEMPO_FOLLOWUP = 6.0         # Segundos de escuta contínua após uma resposta


class DetectorWakeWord:
    def __init__(self, ouvido_stt=None):
        self.ouvido_stt = ouvido_stt
        self.motor_onnx = None
        self.ultimo_uso = 0.0
        self.em_followup = False

        self._tentar_carregar_openwakeword()

    def _tentar_carregar_openwakeword(self):
        """Tenta carregar o modelo ONNX do openwakeword se disponível."""
        try:
            import openwakeword
            from openwakeword.model import Model
            self.motor_onnx = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            print("  [WAKE-WORD] Motor neural OpenWakeWord (ONNX) carregado com sucesso!")
        except Exception:
            self.motor_onnx = None
            print("  [WAKE-WORD] Motor nativo de escuta contínua ativo (Zero dependências extras).")

    def esperar_wake_word(self, callback_wake=None):
        """Bloqueia e escuta o microfone silenciosamente até detectar 'Jarvis'.
        
        Retorna:
            (acordou: bool, pcm_capturado: bytes)
        """
        # Se estiver dentro da janela de follow-up (conversa recente), já acorda direto!
        if self.em_followup and (time.time() - self.ultimo_uso < TEMPO_FOLLOWUP):
            return True, b""

        self.em_followup = False
        fila_audio = queue.Queue()

        def audio_cb(indata, frames, time_info, status):
            fila_audio.put(bytes(indata))

        buffer_recente = []
        blocos_fala = []
        falando = False
        tempo_silencio = time.time()

        with sd.RawInputStream(samplerate=TAXA_AMOSTRAGEM, channels=1, dtype="int16",
                               blocksize=BLOCO_AMOSTRAS, callback=audio_cb):
            while True:
                try:
                    bloco = fila_audio.get(timeout=0.15)
                except queue.Empty:
                    continue

                buffer_recente.append(bloco)
                if len(buffer_recente) > 16:  # Mantém ~1 segundo de áudio recente
                    buffer_recente.pop(0)

                # Cálculo de Energia RMS
                amostras = np.frombuffer(bloco, dtype=np.int16).astype(np.float32)
                rms = float(np.sqrt(np.mean(amostras ** 2)))

                # 1. Se possuir motor OpenWakeWord ONNX
                if self.motor_onnx:
                    if len(bloco) >= 1280 * 2:
                        dados_int16 = np.frombuffer(bloco, dtype=np.int16)
                        pred = self.motor_onnx.predict(dados_int16)
                        score = pred.get("hey_jarvis", 0.0)
                        if score > 0.5:
                            print(f"\n  [WAKE-WORD] 'Hey Jarvis' detectado! (Confiança: {score:.2f})")
                            if callback_wake:
                                callback_wake()
                            self.ultimo_uso = time.time()
                            return True, b""

                # 2. Motor Nativo Contínuo (VAD + Keyword Spotting)
                if rms > LIMIAR_VAD_STANDBY:
                    if not falando:
                        falando = True
                        blocos_fala = list(buffer_recente)
                    else:
                        blocos_fala.append(bloco)
                    tempo_silencio = time.time()
                elif falando:
                    blocos_fala.append(bloco)
                    # Silêncio de 0.6s após falar algo no standby
                    if time.time() - tempo_silencio > 0.6:
                        pcm_total = b"".join(blocos_fala)
                        falando = False
                        blocos_fala = []

                        # Transcreve apenas este pequeno trecho
                        if self.ouvido_stt and len(pcm_total) > TAXA_AMOSTRAGEM * 0.4:
                            texto = self.ouvido_stt.transcrever(pcm_total, TAXA_AMOSTRAGEM)
                            texto_limpo = texto.lower().strip()

                            # Verifica se chamou "Jarvis" ou "Hey Jarvis"
                            if any(k in texto_limpo for k in ["jarvis", "jarvis.", "e aí jarvis", "hey jarvis", "oi jarvis", "olá jarvis"]):
                                print(f"\n  [WAKE-WORD] Acordado por voz: '{texto}'")
                                if callback_wake:
                                    callback_wake()
                                self.ultimo_uso = time.time()
                                
                                # Se o usuário já falou o comando na mesma frase (ex: "Jarvis que horas são?")
                                # passamos o PCM ou texto para processar de imediato sem pedir de novo!
                                return True, pcm_total

    def registrar_atividade(self):
        """Registra que o Jarvis acabou de responder, iniciando a janela de follow-up."""
        self.ultimo_uso = time.time()
        self.em_followup = True

    def resetar_followup(self):
        """Fecha a janela de follow-up forçando retorno ao Wake-Word."""
        self.em_followup = False
