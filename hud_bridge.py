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


def _executar_alternancia(modo):
    global PROCESSO_INTERFACE_ATUAL
    with LOCK_PROC:
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
            try:
                PROCESSO_INTERFACE_ATUAL = subprocess.Popen(
                    [python_exe, str(script)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print(f"  [Interface] Modo ativado: {modo.upper()} ({script.name})")
            except Exception as e:
                print(f"  [Interface] Erro ao alternar para {modo}: {e}")


def alternar_interface(modo="completo"):
    """Alterna dinamicamente entre as interfaces visuais do Jarvis sem travar a thread principal."""
    t = threading.Thread(target=_executar_alternancia, args=(modo,), daemon=True)
    t.start()


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
