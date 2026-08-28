"""Ponte de comunicacao entre o Jarvis e a HUD desktop.

Utiliza um servidor HTTP / Server-Sent Events (SSE) nativo e ultra-leve
(sem dependencias externas como websockets ou flask) que roda em segundo plano
para transmitir o estado do Jarvis, textos e telemetria para a HUD em tempo real.
"""

import hmac
import json
import queue
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE = Path(__file__).parent
FILA_EVENTOS = queue.Queue()
CLIENTES = set()
LOCK = threading.Lock()
PORTA_HUD = 8765
PERFIL_HUD = BASE / ".hud_profile"      # o mesmo que hud_app.py usa no Edge
LOG_INTERFACE = BASE / ".interface_erros.log"

# O servidor escuta em 127.0.0.1, o que da uma falsa sensacao de seguranca:
# QUALQUER site aberto no navegador consegue abrir um EventSource para
# localhost. Com o antigo `Access-Control-Allow-Origin: *`, uma pagina hostil
# lia em tempo real tudo que o usuario fala (userSpeech) e todas as janelas
# que ele usa (windowTitle).
#
# Restringir a origem nao resolve: uma pagina consegue origem "null" por
# iframe sandbox. O que resolve e um segredo que ela nao tem como adivinhar.
# O token e sorteado a cada boot e fica em .hud_token, lido pelas interfaces
# que rodam localmente (mesmo nivel de confianca do .env).
ARQUIVO_TOKEN = BASE / ".hud_token"
TOKEN = None


def _gerar_token():
    """Sorteia o token do boot e publica em .hud_token para as interfaces."""
    global TOKEN
    TOKEN = secrets.token_urlsafe(32)
    try:
        ARQUIVO_TOKEN.write_text(TOKEN, encoding="utf-8")
    except Exception as e:
        print(f"  [HUD] Nao consegui gravar {ARQUIVO_TOKEN.name}: {e}")
    return TOKEN


def token_atual():
    """Token desta sessao. As interfaces avulsas leem do arquivo."""
    if TOKEN:
        return TOKEN
    try:
        return ARQUIVO_TOKEN.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

class ServidorHUD(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silencia logs de requisicao no console para nao poluir o terminal do Jarvis
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _token_confere(self):
        """O ?token= da requisicao bate com o desta sessao?

        Comparacao em tempo constante (compare_digest) por higiene: evita que
        o tempo de resposta revele quantos caracteres do token estao certos.
        """
        esperado = token_atual()
        if not esperado:
            return False
        enviado = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        return hmac.compare_digest(enviado, esperado)

    def do_GET(self):
        caminho = urlparse(self.path).path

        if caminho == "/events":
            if not self._token_confere():
                # Sem CORS na negativa: a pagina nem chega a ler o corpo.
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                try:
                    self.wfile.write(b'{"erro":"token ausente ou invalido"}')
                except Exception:
                    pass
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            # A HUD roda de file://, cuja origem e "null". O token e que
            # autoriza de fato -- este header so destrava a leitura no browser.
            self.send_header("Access-Control-Allow-Origin", "null")
            self.end_headers()

            q = queue.Queue()
            with LOCK:
                CLIENTES.add(q)

            try:
                # Envia mensagem inicial de conexao
                msg_init = f"data: {json.dumps({'type': 'init', 'status': 'connected'})}\n\n"
                self.wfile.write(msg_init.encode("utf-8"))
                self.wfile.flush()

                while True:
                    try:
                        evento = q.get(timeout=20.0)
                        payload = f"data: {json.dumps(evento)}\n\n"
                        self.wfile.write(payload.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        # Ping keep-alive
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
                pass
            except Exception:
                pass
            finally:
                with LOCK:
                    CLIENTES.discard(q)
        else:
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "null")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            except Exception:
                pass


class ServidorSilencioso(ThreadingHTTPServer):
    """Servidor HTTP que ignora desconexoes normais de clientes sem poluir o terminal."""
    def handle_error(self, request, client_address):
        # Ignora erros de desconexao de sockets fechados quando o usuario fecha a janela da HUD
        pass


def _rodar_servidor():
    try:
        servidor = ServidorSilencioso(("127.0.0.1", PORTA_HUD), ServidorHUD)
        servidor.serve_forever()
    except Exception as e:
        pass


PROCESSO_INTERFACE_ATUAL = None
LOCK_PROC = threading.Lock()

def fechar_interfaces_anteriores():
    """Encerra todas as janelas e processos de interfaces ativas com segurança."""
    global PROCESSO_INTERFACE_ATUAL

    # 1. Mata o processo rastreado e sua árvore de processos filhos (ex: Chromium/Edge)
    if PROCESSO_INTERFACE_ATUAL:
        try:
            pid = PROCESSO_INTERFACE_ATUAL.pid
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        PROCESSO_INTERFACE_ATUAL = None

    # 2. Envia sinal de fechamento WM_CLOSE para quaisquer janelas residuais via EnumWindows
    try:
        import ctypes
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

        def enum_close_cb(hwnd, extra):
            if not user32.IsWindowVisible(hwnd):
                return True
            
            # Protege a janela do console / terminal de ser fechada
            class_buff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_buff, 256)
            if "ConsoleWindowClass" in class_buff.value or "VirtualConsoleClass" in class_buff.value:
                return True

            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                if "100% offline" in title or "CMD" in title or "PowerShell" in title:
                    return True

                if any(k in title for k in [
                    "J.A.R.V.I.S. - Core",
                    "J.A.R.V.I.S. HUD",
                    "JARVIS_NATIVE_ORB",
                    "JARVIS_AMBIENT_EDGES",
                ]):
                    user32.PostMessageW(hwnd, 0x0010, 0, 0) # 0x0010 = WM_CLOSE
            return True

        cb = WNDENUMPROC(enum_close_cb)
        user32.EnumWindows(cb, 0)
    except Exception:
        pass


TITULO_ESPERADO = {
    "orbe": "JARVIS_NATIVE_ORB",
    "bordas": "JARVIS_AMBIENT_EDGES",
    "completo": "J.A.R.V.I.S",
}


def _janela_existe(fragmento):
    """Alguma janela VISIVEL tem esse trecho no titulo?"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        achou = [False]

        def cb(hwnd, _extra):
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if fragmento in buf.value:
                    achou[0] = True
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return achou[0]
    except Exception:
        return True          # na duvida, nao acusa falso positivo


def _matar_edge_do_perfil():
    """Mata SOMENTE os Edge que estao usando o perfil da HUD.

    O Edge normal do usuario nao e tocado: o filtro e o --user-data-dir na
    linha de comando do processo.

    Existe por causa de um comportamento do Chromium que quebrava o modo
    completo em silencio: lancado num perfil que outra instancia ja detem, o
    Edge ENTREGA a janela para ela e sai com codigo 0. O hud_app.py, que faz
    p.wait(), morre junto -- e PROCESSO_INTERFACE_ATUAL passa a apontar para
    um processo morto. O taskkill seguinte nao alcanca o Edge de verdade,
    sobra um fantasma segurando o perfil, e toda troca para o modo completo
    passa a falhar sem dizer nada. Medido: 2o lancamento devolve rc=0.
    """
    alvo = str(PERFIL_HUD).replace("'", "''")
    filtro = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | "
              "Where-Object { $_.CommandLine -like '*" + alvo + "*' }")

    def _ps(comando, saida=False):
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando],
                stdout=subprocess.PIPE if saida else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=10)
            return (r.stdout or b"").decode("utf-8", "replace").strip()
        except Exception as e:
            print(f"  [Interface] powershell falhou: {e}")
            return ""

    _ps(filtro + " | ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
                 "-ErrorAction SilentlyContinue }")

    # ESPERAR os processos sumirem de verdade antes de relancar.
    #
    # Matar e relancar em seguida nao funciona: o mutex de instancia unica do
    # Chromium ainda nao foi liberado pelo processo morrendo, o Edge novo acha
    # que ja existe outra instancia no perfil, ENTREGA a linha de comando para
    # ela e sai com codigo 0 -- sem abrir janela nenhuma. Foi exatamente o que
    # as medicoes mostraram: hud_app.py direto do terminal ficava vivo, e pelo
    # bridge (que mata logo antes) morria na hora.
    prazo = time.time() + 4.0
    while time.time() < prazo:
        restantes = _ps(filtro + " | Measure-Object | "
                                 "Select-Object -ExpandProperty Count", saida=True)
        if restantes in ("", "0"):
            break
        time.sleep(0.25)
    time.sleep(0.4)          # folga para o mutex ser liberado


def _ultimas_linhas_do_log(n=6):
    try:
        linhas = LOG_INTERFACE.read_text(encoding="utf-8", errors="replace").splitlines()
        for l in linhas[-n:]:
            if l.strip():
                print("      | " + l[:150])
    except Exception:
        pass


def _executar_alternancia(modo):
    global PROCESSO_INTERFACE_ATUAL, MODO_ATUAL
    with LOCK_PROC:
        MODO_ATUAL = CANONICO.get((modo or "").lower().strip(), "completo")
        # Se estiver alternando para o Orbe, aciona primeiro a animação de sucção/feixe na HUD
        if modo in ["orbe", "esfera", "compacto"]:
            notificar(action="transition_to_orb")
            time.sleep(0.72)
        elif modo in ["borda", "bordas", "moldura", "perimetro", "ambient", "edges"]:
            notificar(action="transition_to_edges")
            time.sleep(0.32)
        elif modo in ["completo", "painel", "hud", "full"]:
            notificar(action="transition_to_full")
            time.sleep(0.35) # Tempo para as 4 bordas convergirem no centro do monitor

        fechar_interfaces_anteriores()
        time.sleep(0.08)

        python_exe = sys.executable
        script = None

        if modo in ["orbe", "esfera", "compacto"]:
            script = BASE / "orbe_desktop_tk.py"
        elif modo in ["borda", "bordas", "moldura", "perimetro", "ambient", "edges"]:
            script = BASE / "bordas_desktop_tk.py"
        elif modo in ["completo", "painel", "hud", "full"]:
            script = BASE / "hud_app.py"
        else:
            script = BASE / "hud_app.py"

        if script and script.is_file():
            # O modo completo abre o Edge; qualquer instancia fantasma no
            # mesmo perfil faria o novo lancamento ser engolido.
            if script.name == "hud_app.py":
                _matar_edge_do_perfil()

            try:
                # stderr vai para arquivo, NAO para DEVNULL: quando uma
                # interface morre ao abrir, e a unica pista que sobra.
                log = open(LOG_INTERFACE, "a", encoding="utf-8")
                log.write("\n--- %s | abrindo %s (modo %s) ---\n"
                          % (time.strftime("%H:%M:%S"), script.name, modo))
                log.flush()
                PROCESSO_INTERFACE_ATUAL = subprocess.Popen(
                    [python_exe, str(script)],
                    stdout=subprocess.DEVNULL,
                    stderr=log
                )
                print(f"  [Interface] Modo ativado: {modo.upper()} ({script.name})")
            except Exception as e:
                print(f"  [Interface] Erro ao alternar para {modo}: {e}")
                return

            # Confere se a JANELA apareceu -- nao so se o processo sobreviveu.
            # O processo pode ficar vivo desenhando nada, que foi exatamente o
            # bug das bordas nascendo em modo de saida. Conferir so o processo
            # dava sucesso para uma tela vazia.
            alvo_titulo = TITULO_ESPERADO.get(MODO_ATUAL)
            prazo = time.time() + 5.0
            apareceu, morreu = False, False
            while time.time() < prazo:
                time.sleep(0.25)
                if PROCESSO_INTERFACE_ATUAL.poll() is not None:
                    morreu = True
                    break
                if not alvo_titulo or _janela_existe(alvo_titulo):
                    apareceu = True
                    break
                if _MODO_DESEJADO is not None:
                    return          # chegou pedido novo: nao vale mais esperar

            if morreu or not apareceu:
                motivo = ("o processo encerrou (codigo %s)" % PROCESSO_INTERFACE_ATUAL.returncode
                          if morreu else "a janela %r nao apareceu em 5s" % alvo_titulo)
                aviso = "[Interface] AVISO: %s -- %s." % (script.name, motivo)
                print("  " + aviso)
                print("  Ultimas linhas de %s:" % LOG_INTERFACE.name)
                _ultimas_linhas_do_log()
                try:
                    with open(LOG_INTERFACE, "a", encoding="utf-8") as log:
                        log.write("%s | %s\n" % (time.strftime("%H:%M:%S"), aviso))
                except Exception:
                    pass


# --- fila de troca: um pedido novo SUBSTITUI o anterior, nao entra na fila ---
#
# Antes, cada pedido virava uma thread propria e elas se enfileiravam no
# LOCK_PROC. Como a troca leva 2,4 a 3,4 segundos e a voz confirma na hora, o
# usuario naturalmente pede de novo -- e o segundo pedido DESTRUIA a janela
# que o primeiro acabara de criar. Tres pedidos = tres ciclos completos de
# matar-e-relancar, com a interface piscando. Agora tres pedidos para o mesmo
# modo custam uma troca.
MODO_ATUAL = None
_MODO_DESEJADO = None
_SINAL_TROCA = threading.Event()
_WORKER_TROCA = None

CANONICO = {
    "orbe": "orbe", "esfera": "orbe", "compacto": "orbe",
    "borda": "bordas", "bordas": "bordas", "moldura": "bordas",
    "perimetro": "bordas", "ambient": "bordas", "edges": "bordas",
    "completo": "completo", "painel": "completo", "hud": "completo",
    "full": "completo",
}


def modo_atual():
    """Modo em exibicao, ou None se nenhuma interface foi aberta ainda."""
    return MODO_ATUAL


def _laco_de_troca():
    global _MODO_DESEJADO
    while True:
        _SINAL_TROCA.wait()
        _SINAL_TROCA.clear()
        while True:
            alvo, _MODO_DESEJADO = _MODO_DESEJADO, None
            if alvo is None:
                break
            _executar_alternancia(alvo)
            # Enquanto trocavamos, chegou outro pedido? Atende sem enfileirar.
            if _MODO_DESEJADO is None:
                break


def alternar_interface(modo="completo"):
    """Pede a troca de interface. Nao bloqueia a thread que chamou.

    Devolve True se a troca foi agendada, False se ja estamos nesse modo --
    nesse caso nada e tocado, em vez de matar e relancar a mesma interface.
    """
    global _MODO_DESEJADO, _WORKER_TROCA

    alvo = CANONICO.get((modo or "").lower().strip(), "completo")
    if alvo == MODO_ATUAL and PROCESSO_INTERFACE_ATUAL is not None             and PROCESSO_INTERFACE_ATUAL.poll() is None:
        print(f"  [Interface] Ja estamos no modo {alvo.upper()}; nada a fazer.")
        return False

    _MODO_DESEJADO = alvo
    if _WORKER_TROCA is None or not _WORKER_TROCA.is_alive():
        _WORKER_TROCA = threading.Thread(target=_laco_de_troca, daemon=True)
        _WORKER_TROCA.start()
    _SINAL_TROCA.set()
    return True


def abrir_hud(modo="completo"):
    """Abre a interface inicial (Modo Completo por padrão)."""
    alternar_interface(modo)


def iniciar(auto_abrir=True, modo_inicial="completo"):
    """Inicia o servidor em segundo plano e abre a interface escolhida."""
    _gerar_token()
    t = threading.Thread(target=_rodar_servidor, daemon=True)
    t.start()
    time.sleep(0.3)
    if auto_abrir:
        abrir_hud(modo_inicial)


def notificar(**dados):
    """Envia um evento JSON para a HUD conectada."""
    with LOCK:
        for q in list(CLIENTES):
            q.put(dados)
