"""Modo Bordas Perimetrais do J.A.R.V.I.S. (com Animação Reversa para o Orbe)

- Linhas perfeitamente fixas coladas nas 4 beiradas do monitor (sem tremores ou movimento)
- Animação de nascimento: plasma desce pelas laterais e se fecha na base
- Animação de transição para HUD Completa: bordas convergem para o centro
- Animação de transição para Orbe: o circuito se retrai e os feixes sobem para o topo em direção ao orbe
- Efeito translúcido suave em repouso
- Brilho vibrante quando o Jarvis está respondendo
"""

import os
import sys
import math
import time
import json
import threading
import urllib.request
from urllib.parse import quote
import tkinter as tk

base_prefix = getattr(sys, 'base_prefix', sys.prefix)
tcl_path = os.path.join(base_prefix, 'tcl', 'tcl8.6')
tk_path = os.path.join(base_prefix, 'tcl', 'tk8.6')
if os.path.exists(tcl_path) and "TCL_LIBRARY" not in os.environ:
    os.environ["TCL_LIBRARY"] = tcl_path
if os.path.exists(tk_path) and "TK_LIBRARY" not in os.environ:
    os.environ["TK_LIBRARY"] = tk_path


def _url_dos_eventos():
    """URL do SSE com o token da sessao, lido de .hud_token na raiz do projeto.

    Sem token o servidor responde 403. Se o Jarvis nao estiver rodando o
    arquivo nao existe, a conexao falha e a interface fica em modo offline --
    que e o comportamento correto.
    """
    try:
        raiz = os.path.dirname(os.path.abspath(__file__))
        token = open(os.path.join(raiz, ".hud_token"), encoding="utf-8").read().strip()
    except Exception:
        token = ""
    return "http://127.0.0.1:8765/events?token=" + quote(token)

PALETAS = {
    "ciano": {
        "idle": ["#022322", "#043B38", "#064E4A", "#0D6560", "#14B8A6"],
        "speaking": ["#0F766E", "#14B8A6", "#2DD4BF", "#5EEAD4", "#A7F3D0", "#FFFFFF"],
        "accent": "#00F0FF"
    },
    "azul": {
        "idle": ["#041B2D", "#072D49", "#0B3F65", "#0F5282", "#0284C7"],
        "speaking": ["#0284C7", "#00F0FF", "#38BDF8", "#7DD3FC", "#BAE6FD", "#FFFFFF"],
        "accent": "#38BDF8"
    },
    "vermelho": {
        "idle": ["#2B0606", "#450A0A", "#5C0E0E", "#771414", "#991B1B"],
        "speaking": ["#B91C1C", "#DC2626", "#EF4444", "#F87171", "#FCA5A5", "#FFFFFF"],
        "accent": "#EF4444"
    },
    "verde": {
        "idle": ["#021E17", "#033126", "#044535", "#055B46", "#065F46"],
        "speaking": ["#047857", "#059669", "#10B981", "#34D399", "#6EE7B7", "#FFFFFF"],
        "accent": "#10B981"
    },
    "roxo": {
        "idle": ["#250440", "#3B0764", "#4E0B82", "#6310A3", "#7E22CE"],
        "speaking": ["#7E22CE", "#9333EA", "#A855F7", "#C084FC", "#E9D5FF", "#FFFFFF"],
        "accent": "#A855F7"
    },
    "dourado": {
        "idle": ["#2B1002", "#451A03", "#5C2304", "#742C06", "#92400E"],
        "speaking": ["#D97706", "#F59E0B", "#FBBF24", "#FCD34D", "#FEF3C7", "#FFFFFF"],
        "accent": "#FBBF24"
    },
    "branco": {
        "idle": ["#0B111E", "#111B2C", "#1E293B", "#334155", "#475569"],
        "speaking": ["#64748B", "#94A3B8", "#CBD5E1", "#E2E8F0", "#F8FAFC", "#FFFFFF"],
        "accent": "#FFFFFF"
    },
    "rosa": {
        "idle": ["#310310", "#4C0519", "#670823", "#830C2E", "#9F1239"],
        "speaking": ["#BE123C", "#E11D48", "#F43F5E", "#FB7185", "#FECDD3", "#FFFFFF"],
        "accent": "#F43F5E"
    }
}


class JarvisAmbientEdgeOverlay:
    TRANSPARENT_KEY = "#000001"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("JARVIS_AMBIENT_EDGES")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()

        self.root.geometry(f"{self.screen_w}x{self.screen_h}+0+0")
        self.root.configure(bg=self.TRANSPARENT_KEY)

        try:
            self.root.wm_attributes("-transparentcolor", self.TRANSPARENT_KEY)
        except Exception:
            pass

        self.canvas = tk.Canvas(
            self.root,
            width=self.screen_w,
            height=self.screen_h,
            bg=self.TRANSPARENT_KEY,
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.current_theme = "ciano"
        self.state = "idle"
        self.glow_intensity = 0.0
        self.target_glow = 0.0
        self.birth_laser_start = time.time()

        # Estados de Transição de Saída
        self.transitioning_to_full = False
        self.transitioning_to_orb = False
        self.exit_start_time = 0.0

        self._init_canvas_items()

        t = threading.Thread(target=self._escutar_sse, daemon=True)
        t.start()

        self.root.after(16, self._render_loop)

    def _init_canvas_items(self):
        w, h = self.screen_w, self.screen_h

        # 1. Camadas de degradê permanente nas 4 bordas
        self.num_layers = 5
        self.top_lines = []
        self.bottom_lines = []
        self.left_lines = []
        self.right_lines = []

        for i in range(self.num_layers):
            offset = i * 2

            tl = self.canvas.create_line(0, offset, w, offset, fill="#043B38", width=2)
            bl = self.canvas.create_line(0, h - offset, w, h - offset, fill="#043B38", width=2)
            ll = self.canvas.create_line(offset, 0, offset, h, fill="#043B38", width=2)
            rl = self.canvas.create_line(w - offset, 0, w - offset, h, fill="#043B38", width=2)

            self.top_lines.append(tl)
            self.bottom_lines.append(bl)
            self.left_lines.append(ll)
            self.right_lines.append(rl)

        # 2. Feixes Lasers de Formação
        self.laser_left_glow = self.canvas.create_line(0, 0, 0, 0, fill="#00F0FF", width=7.0, capstyle=tk.ROUND)
        self.laser_left_core = self.canvas.create_line(0, 0, 0, 0, fill="#FFFFFF", width=3.0, capstyle=tk.ROUND)

        self.laser_right_glow = self.canvas.create_line(w, 0, w, 0, fill="#00F0FF", width=7.0, capstyle=tk.ROUND)
        self.laser_right_core = self.canvas.create_line(w, 0, w, 0, fill="#FFFFFF", width=3.0, capstyle=tk.ROUND)

        self.laser_bot_left_glow = self.canvas.create_line(0, h, 0, h, fill="#00F0FF", width=7.0, capstyle=tk.ROUND)
        self.laser_bot_left_core = self.canvas.create_line(0, h, 0, h, fill="#FFFFFF", width=3.0, capstyle=tk.ROUND)

        self.laser_bot_right_glow = self.canvas.create_line(w, h, w, h, fill="#00F0FF", width=7.0, capstyle=tk.ROUND)
        self.laser_bot_right_core = self.canvas.create_line(w, h, w, h, fill="#FFFFFF", width=3.0, capstyle=tk.ROUND)

        # 3. Feixes Convergentes (para HUD Completa)
        self.converge_top_glow = self.canvas.create_line(0, 0, w, 0, fill="#00F0FF", width=7.0, state="hidden")
        self.converge_top_core = self.canvas.create_line(0, 0, w, 0, fill="#FFFFFF", width=3.0, state="hidden")
        self.converge_bot_glow = self.canvas.create_line(0, h, w, h, fill="#00F0FF", width=7.0, state="hidden")
        self.converge_bot_core = self.canvas.create_line(0, h, w, h, fill="#FFFFFF", width=3.0, state="hidden")
        self.converge_left_glow = self.canvas.create_line(0, 0, 0, h, fill="#00F0FF", width=7.0, state="hidden")
        self.converge_left_core = self.canvas.create_line(0, 0, 0, h, fill="#FFFFFF", width=3.0, state="hidden")
        self.converge_right_glow = self.canvas.create_line(w, 0, w, h, fill="#00F0FF", width=7.0, state="hidden")
        self.converge_right_core = self.canvas.create_line(w, 0, w, h, fill="#FFFFFF", width=3.0, state="hidden")

        # 4. Feixes de Subida para o Orbe (Bordas -> Topo Central)
        self.retract_top_left_glow = self.canvas.create_line(0, 0, 0, 0, fill="#00F0FF", width=8.0, state="hidden")
        self.retract_top_left_core = self.canvas.create_line(0, 0, 0, 0, fill="#FFFFFF", width=3.5, state="hidden")
        self.retract_top_right_glow = self.canvas.create_line(w, 0, w, 0, fill="#00F0FF", width=8.0, state="hidden")
        self.retract_top_right_core = self.canvas.create_line(w, 0, w, 0, fill="#FFFFFF", width=3.5, state="hidden")

    def _escutar_sse(self):
        while True:
            try:
                req = urllib.request.Request(_url_dos_eventos(), headers={"Accept": "text/event-stream"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    for line in resp:
                        txt = line.decode("utf-8").strip()
                        if txt.startswith("data:"):
                            payload = txt[5:].strip()
                            try:
                                data = json.loads(payload)
                                if data.get("action") == "transition_to_full":
                                    self.transitioning_to_full = True
                                    self.exit_start_time = time.time()
                                if data.get("action") == "transition_to_orb":
                                    self.transitioning_to_orb = True
                                    self.exit_start_time = time.time()
                                if "theme" in data and data["theme"] in PALETAS:
                                    self.current_theme = data["theme"]
                                if "state" in data:
                                    self.state = data["state"]
                            except Exception:
                                pass
            except Exception:
                time.sleep(2)

    def _render_loop(self):
        now = time.time()
        w, h = self.screen_w, self.screen_h
        pal = PALETAS.get(self.current_theme, PALETAS["ciano"])
        accent = pal.get("accent", "#00F0FF")

        # 1. Animação de Entrada
        birth_age = now - self.birth_laser_start
        if birth_age < 0.65 and not self.transitioning_to_full and not self.transitioning_to_orb:
            p = birth_age / 0.65

            if p < 0.44:
                p_vert = p / 0.44
                y_pos = h * math.sin(p_vert * math.pi * 0.5)

                self.canvas.coords(self.laser_left_glow, 1, 0, 1, y_pos)
                self.canvas.coords(self.laser_left_core, 1, 0, 1, y_pos)
                self.canvas.coords(self.laser_right_glow, w - 1, 0, w - 1, y_pos)
                self.canvas.coords(self.laser_right_core, w - 1, 0, w - 1, y_pos)

                self.canvas.itemconfigure(self.laser_left_glow, fill=accent, state="normal")
                self.canvas.itemconfigure(self.laser_left_core, fill="#FFFFFF", state="normal")
                self.canvas.itemconfigure(self.laser_right_glow, fill=accent, state="normal")
                self.canvas.itemconfigure(self.laser_right_core, fill="#FFFFFF", state="normal")
            elif p < 0.78:
                p_horiz = (p - 0.44) / 0.34
                x_span = (w // 2) * math.sin(p_horiz * math.pi * 0.5)

                self.canvas.coords(self.laser_left_glow, 1, 0, 1, h)
                self.canvas.coords(self.laser_left_core, 1, 0, 1, h)
                self.canvas.coords(self.laser_right_glow, w - 1, 0, w - 1, h)
                self.canvas.coords(self.laser_right_core, w - 1, 0, w - 1, h)

                self.canvas.coords(self.laser_bot_left_glow, 0, h - 1, x_span, h - 1)
                self.canvas.coords(self.laser_bot_left_core, 0, h - 1, x_span, h - 1)
                self.canvas.coords(self.laser_bot_right_glow, w, h - 1, w - x_span, h - 1)
                self.canvas.coords(self.laser_bot_right_core, w, h - 1, w - x_span, h - 1)

                self.canvas.itemconfigure(self.laser_bot_left_glow, fill=accent, state="normal")
                self.canvas.itemconfigure(self.laser_bot_left_core, fill="#FFFFFF", state="normal")
                self.canvas.itemconfigure(self.laser_bot_right_glow, fill=accent, state="normal")
                self.canvas.itemconfigure(self.laser_bot_right_core, fill="#FFFFFF", state="normal")
            else:
                p_fade = (p - 0.78) / 0.22
                fade_alpha = max(0.0, 1.0 - p_fade * 1.5)

                if fade_alpha <= 0.05:
                    self.canvas.itemconfigure(self.laser_left_glow, state="hidden")
                    self.canvas.itemconfigure(self.laser_left_core, state="hidden")
                    self.canvas.itemconfigure(self.laser_right_glow, state="hidden")
                    self.canvas.itemconfigure(self.laser_right_core, state="hidden")
                    self.canvas.itemconfigure(self.laser_bot_left_glow, state="hidden")
                    self.canvas.itemconfigure(self.laser_bot_left_core, state="hidden")
                    self.canvas.itemconfigure(self.laser_bot_right_glow, state="hidden")
                    self.canvas.itemconfigure(self.laser_bot_right_core, state="hidden")
        else:
            self.canvas.itemconfigure(self.laser_left_glow, state="hidden")
            self.canvas.itemconfigure(self.laser_left_core, state="hidden")
            self.canvas.itemconfigure(self.laser_right_glow, state="hidden")
            self.canvas.itemconfigure(self.laser_right_core, state="hidden")
            self.canvas.itemconfigure(self.laser_bot_left_glow, state="hidden")
            self.canvas.itemconfigure(self.laser_bot_left_core, state="hidden")
            self.canvas.itemconfigure(self.laser_bot_right_glow, state="hidden")
            self.canvas.itemconfigure(self.laser_bot_right_core, state="hidden")

        # 2. Animação de Saída para HUD Completa (Convergência para o Centro)
        if self.transitioning_to_full:
            exit_age = now - self.exit_start_time
            t_exit = min(1.0, exit_age / 0.38)
            p_conv = math.sin(t_exit * math.pi * 0.5)

            top_y = (h // 2) * p_conv
            bot_y = h - (h // 2) * p_conv
            left_x = (w // 2) * p_conv
            right_x = w - (w // 2) * p_conv

            self.canvas.coords(self.converge_top_glow, 0, top_y, w, top_y)
            self.canvas.coords(self.converge_top_core, 0, top_y, w, top_y)
            self.canvas.coords(self.converge_bot_glow, 0, bot_y, w, bot_y)
            self.canvas.coords(self.converge_bot_core, 0, bot_y, w, bot_y)
            self.canvas.coords(self.converge_left_glow, left_x, 0, left_x, h)
            self.canvas.coords(self.converge_left_core, left_x, 0, left_x, h)
            self.canvas.coords(self.converge_right_glow, right_x, 0, right_x, h)
            self.canvas.coords(self.converge_right_core, right_x, 0, right_x, h)

            self.canvas.itemconfigure(self.converge_top_glow, fill=accent, state="normal")
            self.canvas.itemconfigure(self.converge_top_core, fill="#FFFFFF", state="normal")
            self.canvas.itemconfigure(self.converge_bot_glow, fill=accent, state="normal")
            self.canvas.itemconfigure(self.converge_bot_core, fill="#FFFFFF", state="normal")
            self.canvas.itemconfigure(self.converge_left_glow, fill=accent, state="normal")
            self.canvas.itemconfigure(self.converge_left_core, fill="#FFFFFF", state="normal")
            self.canvas.itemconfigure(self.converge_right_glow, fill=accent, state="normal")
            self.canvas.itemconfigure(self.converge_right_core, fill="#FFFFFF", state="normal")

        # 3. Animação de Saída para o Modo Orbe (Retração Perimetral Reversa para o Topo)
        if self.transitioning_to_orb:
            exit_age = now - self.exit_start_time
            t_exit = min(1.0, exit_age / 0.38)

            # Fase 1: Sobe pelas laterais de h até 0
            if t_exit < 0.50:
                p_up = t_exit / 0.50
                y_reach = h - h * math.sin(p_up * math.pi * 0.5)

                self.canvas.coords(self.laser_left_glow, 1, h, 1, y_reach)
                self.canvas.coords(self.laser_left_core, 1, h, 1, y_reach)
                self.canvas.coords(self.laser_right_glow, w - 1, h, w - 1, y_reach)
                self.canvas.coords(self.laser_right_core, w - 1, h, w - 1, y_reach)

                self.canvas.itemconfigure(self.laser_left_glow, fill=accent, state="normal")
                self.canvas.itemconfigure(self.laser_left_core, fill="#FFFFFF", state="normal")
                self.canvas.itemconfigure(self.laser_right_glow, fill=accent, state="normal")
                self.canvas.itemconfigure(self.laser_right_core, fill="#FFFFFF", state="normal")

            # Fase 2: Corre pelo topo dos cantos para o centro do orbe (w/2, 0)
            else:
                p_top = (t_exit - 0.50) / 0.50
                x_conv = (w // 2) * math.sin(p_top * math.pi * 0.5)

                self.canvas.coords(self.retract_top_left_glow, 0, 2, x_conv, 2)
                self.canvas.coords(self.retract_top_left_core, 0, 2, x_conv, 2)
                self.canvas.coords(self.retract_top_right_glow, w, 2, w - x_conv, 2)
                self.canvas.coords(self.retract_top_right_core, w, 2, w - x_conv, 2)

                self.canvas.itemconfigure(self.retract_top_left_glow, fill=accent, state="normal")
                self.canvas.itemconfigure(self.retract_top_left_core, fill="#FFFFFF", state="normal")
                self.canvas.itemconfigure(self.retract_top_right_glow, fill=accent, state="normal")
                self.canvas.itemconfigure(self.retract_top_right_core, fill="#FFFFFF", state="normal")

        # 4. Modulação de Iluminação Permanente (quando falando)
        if self.state == "speaking":
            self.target_glow = 1.0
        else:
            self.target_glow = 0.0

        self.glow_intensity += (self.target_glow - self.glow_intensity) * 0.14
        g = self.glow_intensity

        idle_colors = pal["idle"]
        speaking_colors = pal["speaking"]

        for idx in range(self.num_layers):
            if g > 0.05:
                cor = speaking_colors[min(idx, len(speaking_colors) - 1)]
                w_line = 2 if idx > 0 else 3
            else:
                cor = idle_colors[min(idx, len(idle_colors) - 1)]
                w_line = 2

            self.canvas.itemconfigure(self.top_lines[idx], fill=cor, width=w_line)
            self.canvas.itemconfigure(self.bottom_lines[idx], fill=cor, width=w_line)
            self.canvas.itemconfigure(self.left_lines[idx], fill=cor, width=w_line)
            self.canvas.itemconfigure(self.right_lines[idx], fill=cor, width=w_line)

        self.root.after(16, self._render_loop)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = JarvisAmbientEdgeOverlay()
    app.run()
