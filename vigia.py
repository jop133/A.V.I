"""Leitura de tela contínua, ligada e desligada por voz.

Com o modo desligado, o Jarvis só olha a tela quando o modelo pede
(ferramenta `ler_tela`). Isso é rápido no dia a dia, mas falha numa conversa
encadeada: perguntada a segunda vez ("e o que tem nela?"), o modelo não relia
e preenchia as lacunas com invenção.

Ligado, ele mantém uma leitura fresca e a entrega junto da pergunta. A troca
está medida no LEIA-ME: conversa comum fica ~1s mais lenta, pergunta sobre a
tela fica ~2s mais rápida (some a segunda ida ao modelo).

Custo de manter isso rodando, medido: 122 ms por amostra e **0,0% de um
núcleo** a cada 1,5s. Ficar de olho é praticamente de graça; o que custa é o
prefill de mandar a leitura ao modelo, e por isso o modo é explícito.
"""

import threading
import time

import percepcao


class VigiaDaTela:
    """Mantém uma leitura recente da tela enquanto estiver ligado."""

    def __init__(self, intervalo=1.5, limite_caracteres=1200):
        self.intervalo = intervalo
        self.limite_caracteres = limite_caracteres
        self._ligado = threading.Event()
        self._acordar = threading.Event()
        self._lock = threading.Lock()
        self._leitura = ""
        self._instante = 0.0
        self._mudou = False
        self._erros = 0
        threading.Thread(target=self._laco, daemon=True).start()

    # ------------------------------------------------------------- controle

    @property
    def ligado(self):
        return self._ligado.is_set()

    def ligar(self, esperar=2.0):
        """Liga e espera a PRIMEIRA leitura ficar pronta.

        Esperar e de proposito: quem acabou de dizer "ativar leitura de tela"
        costuma perguntar sobre a tela em seguida, e o primeiro uso cairia
        vazio ate o amostrador rodar.

        Quem le e sempre a thread do vigia, nunca esta aqui. O UI Automation
        e COM, e COM e por thread: ler daqui dava
        "CoInitialize nao foi chamado" quando a chamada vinha de uma thread
        que nao inicializou o apartamento.
        """
        ja_estava = self.ligado
        self._ligado.set()
        self._acordar.set()
        if not ja_estava:
            limite = time.time() + esperar
            while time.time() < limite and not self.atual()[0]:
                time.sleep(0.05)
        return not ja_estava

    def desligar(self):
        estava = self.ligado
        self._ligado.clear()
        with self._lock:
            self._leitura, self._instante, self._mudou = "", 0.0, False
        return estava

    # ---------------------------------------------------------------- uso

    def atual(self):
        """(texto da ultima leitura, idade em segundos). ('', None) se desligado."""
        with self._lock:
            if not self._leitura:
                return "", None
            return self._leitura, time.time() - self._instante

    def mudou_desde_a_ultima(self):
        with self._lock:
            return self._mudou

    # ------------------------------------------------------------- interno

    def _amostrar(self):
        try:
            texto, _ = percepcao.contexto(limite_caracteres=self.limite_caracteres)
        except Exception as e:
            # COM em thread de fundo pode falhar esporadicamente; nao vale
            # derrubar o vigia por uma amostra perdida.
            self._erros += 1
            if self._erros in (1, 10, 100):
                print("  [Vigia] falha ao ler a tela (%d): %r" % (self._erros, e))
            return
        with self._lock:
            self._mudou = (texto != self._leitura)
            self._leitura = texto
            self._instante = time.time()

    def _laco(self):
        # O uiautomation precisa inicializar COM em CADA thread que o usa.
        # Feito uma vez aqui, pela unica thread que le a tela no vigia.
        try:
            import uiautomation as auto
            with auto.UIAutomationInitializerInThread(debug=False):
                self._laco_interno()
        except Exception as e:
            print("  [Vigia] nao consegui inicializar a leitura de tela: %r" % (e,))

    def _laco_interno(self):
        while True:
            if not self._ligado.is_set():
                self._acordar.wait(timeout=5.0)
                self._acordar.clear()
                continue
            self._amostrar()
            time.sleep(self.intervalo)


VIGIA = VigiaDaTela()
