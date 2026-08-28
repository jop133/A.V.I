"""HUD Top-Bar / Dynamic Island Nativa do J.A.R.V.I.S. (100% Nativo Tkinter)

- Fundo 100% Transparente Real no Windows (-transparentcolor #000001)
- Sem bordas, sem barra de título, sem molduras de navegador (overrideredirect)
- Always-on-Top (flutua sobre qualquer programa ou jogo)
- Mini Cérebro 3D Orgânico Holográfico (com constelações internas) na esquerda
- Ondas Sonoras Neon em Tempo Real a 60 FPS no centro
- Legendas inteligentes das falas do Jarvis e do usuário
- Sincronização via SSE com o motor local (porta 8765)
"""

import os
import sys
import math
import time
import json
import random
import threading
import urllib.request
import tkinter as tk

# Configura caminhos Tcl/Tk para ambientes virtuais Python no Windows
base_prefix = getattr(sys, 'base_prefix', sys.prefix)
tcl_path = os.path.join(base_prefix, 'tcl', 'tcl8.6')
tk_path = os.path.join(base_prefix, 'tcl', 'tk8.6')
if os.path.exists(tcl_path) and "TCL_LIBRARY" not in os.environ:
    os.environ["TCL_LIBRARY"] = tcl_path
if os.path.exists(tk_path) and "TK_LIBRARY" not in os.environ:
    os.environ["TK_LIBRARY"] = tk_path

PALETAS = {
    "ciano": {
        "primary": "#5EEAD4", "secondary": "#2DD4BF", "glow": "#0F766E",
        "deep": "#042F2E", "core": "#FFFFFF", "accent": "#00F0FF"
    },
    "azul": {
        "primary": "#00F0FF", "secondary": "#38BDF8", "glow": "#0284C7",
        "deep": "#082F49", "core": "#FFFFFF", "accent": "#60A5FA"
    },
    "vermelho": {
        "primary": "#EF4444", "secondary": "#F87171", "glow": "#B91C1C",
        "deep": "#450A0A", "core": "#FFFFFF", "accent": "#FCA5A5"
    },
    "verde": {
        "primary": "#10B981", "secondary": "#34D399", "glow": "#047857",
        "deep": "#022C22", "core": "#FFFFFF", "accent": "#6EE7B7"
    },
    "roxo": {
        "primary": "#A855F7", "secondary": "#C084FC", "glow": "#7E22CE",
        "deep": "#3B0764", "core": "#FFFFFF", "accent": "#E9D5FF"
    },
    "dourado": {
        "primary": "#FBBF24", "secondary": "#FCD34D", "glow": "#D97706",
        "deep": "#451A03", "core": "#FFFFFF", "accent": "#FEF3C7"
    },
    "branco": {
        "primary": "#FFFFFF", "secondary": "#E2E8F0", "glow": "#64748B",
        "deep": "#0F172A", "core": "#FFFFFF", "accent": "#F8FAFC"
    },
    "rosa": {
        "primary": "#F43F5E", "secondary": "#FB7185", "glow": "#BE123C",
        "deep": "#4C0519", "core": "#FFFFFF", "accent": "#FECDD3"
    }
}


class JarvisDynamicIsland:
    TRANSPARENT_KEY = "#000001"

    def __init__(self):
        self.bar_width = 820
        self.bar_height = 70
        self.pill_height = 48
        self.pill_y = 6

        self.root = tk.Tk()
        self.root.title("JARVIS_DYNAMIC_ISLAND")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        # Transparência nativa pura no Windows
        self.root.configure(bg=self.TRANSPARENT_KEY)
        try:
            self.root.wm_attributes("-transparentcolor", self.TRANSPARENT_KEY)
        except Exception:
            pass

        # Centraliza no topo da tela do monitor
        screen_w = self.root.winfo_screenwidth()
        pos_x = (screen_w - self.bar_width) // 2
        pos_y = 8
        self.root.geometry(f"{self.bar_width}x{self.bar_height}+{pos_x}+{pos_y}")

        # Canvas de Alta Performance
        self.canvas = tk.Canvas(
            self.root,
            width=self.bar_width,
            height=self.bar_height,
            bg=self.TRANSPARENT_KEY,
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Suporte a arrastar a ilha com o mouse
        self._offset_x = 0
        self._offset_y = 0
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._on_drag)

        # Estado da Aplicação
        self.current_theme = "ciano"
        self.state = "idle"
        self.status_label = "ONLINE"
        self.audio_intensity = 0.1
        self.target_audio = 0.1
        self.smoothed_audio = 0.1
        self.global_phase = 0.0
        self.speech_text = ""
        self.speech_timer = 0.0
        self.rot_y = 0.0
        self.rot_x = 0.0

        # Geometria da Mini Esfera 3D
        self._init_mini_sphere_mesh()
        self._init_mini_constellations()

        # Camadas da Onda Sonora Central
        self.wave_layers = [
            {"color": "#1E3A8A", "width": 4.5, "freq": 1.2, "speed": 0.045, "phase": 0.0, "amp_mult": 0.55},
            {"color": "#4338CA", "width": 3.0, "freq": 1.8, "speed": 0.060, "phase": 1.5, "amp_mult": 0.70},
            {"color": "#0284C7", "width": 2.2, "freq": 2.6, "speed": 0.080, "phase": 3.0, "amp_mult": 0.85},
            {"color": "#00F0FF", "width": 1.8, "freq": 3.4, "speed": 0.100, "phase": 4.5, "amp_mult": 1.00},
            {"color": "#38BDF8", "width": 1.5, "freq": 4.2, "speed": 0.075, "phase": 2.2, "amp_mult": 0.75},
            {"color": "#FFFFFF", "width": 1.0, "freq": 3.8, "speed": 0.115, "phase": 5.8, "amp_mult": 0.90},
        ]

        self._init_canvas_items()

        # Inicia escuta SSE em background
        t = threading.Thread(target=self._escutar_sse, daemon=True)
        t.start()

        # Inicia loop de renderização 60 FPS
        self.root.after(16, self._render_loop)

    def _create_rounded_rect(self, x1, y1, x2, y2, radius=25, **kwargs):
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        return self.canvas.create_polygon(points, **kwargs, smooth=True)

    def _init_mini_sphere_mesh(self):
        self.lats = 7
        self.lons = 10
        self.sphere_nodes = []
        self.sphere_lines = []

        for i in range(self.lats + 1):
            phi = math.pi * i / self.lats
            for j in range(self.lons):
                theta = 2 * math.pi * j / self.lons
                x = math.sin(phi) * math.cos(theta)
                y = math.cos(phi)
                z = math.sin(phi) * math.sin(theta)
                self.sphere_nodes.append([x, y, z])

        for i in range(1, self.lats):
            for j in range(self.lons):
                n1 = i * self.lons + j
                n2 = i * self.lons + ((j + 1) % self.lons)
                self.sphere_lines.append((n1, n2))

        for i in range(self.lats):
            for j in range(self.lons):
                n1 = i * self.lons + j
                n2 = (i + 1) * self.lons + j
                if n2 < len(self.sphere_nodes):
                    self.sphere_lines.append((n1, n2))

    def _init_mini_constellations(self):
        self.clusters = [
            {"color": "#A855F7", "glow": "#7E22CE", "nodes": [(-0.3, 0.3, -0.2), (-0.1, 0.4, -0.1), (-0.25, 0.15, -0.1)], "edges": [(0, 1), (1, 2), (2, 0)]},
            {"color": "#00F0FF", "glow": "#0284C7", "nodes": [(0.3, -0.2, 0.2), (0.1, -0.35, 0.1), (0.25, -0.1, 0.3)], "edges": [(0, 1), (1, 2)]},
        ]

    def _init_canvas_items(self):
        pad = 8
        self.pill_x1 = pad
        self.pill_y1 = self.pill_y
        self.pill_x2 = self.bar_width - pad
        self.pill_y2 = self.pill_y + self.pill_height

        self.orb_cx = self.pill_x1 + 28
        self.orb_cy = self.pill_y1 + self.pill_height // 2
        self.orb_radius = 16.0

        # 1. Feixe Laser de Nascimento da Ilha (Expansão Horizontal)
        self.island_laser_glow = self.canvas.create_line(self.bar_width // 2, self.orb_cy, self.bar_width // 2, self.orb_cy, fill="#00F0FF", width=9.0, capstyle=tk.ROUND)
        self.island_laser_core = self.canvas.create_line(self.bar_width // 2, self.orb_cy, self.bar_width // 2, self.orb_cy, fill="#FFFFFF", width=3.5, capstyle=tk.ROUND)
        self.birth_laser_start = time.time()

        # 2. Fundo da Pílula Escura Translúcida
        self.pill_glow = self._create_rounded_rect(
            self.pill_x1 - 1, self.pill_y1 - 1, self.pill_x2 + 1, self.pill_y2 + 1,
            radius=24, fill="", outline="#1E293B", width=1
        )
        self.pill_bg = self._create_rounded_rect(
            self.pill_x1, self.pill_y1, self.pill_x2, self.pill_y2,
            radius=23, fill="#080C14", outline="#0F172A", width=1.5
        )

        # 2. Mini Orbe 3D Trillion Cosmos (Esquerda)
        self.orb_cx = pill_x1 + 28
        self.orb_cy = pill_y1 + self.pill_height // 2
        self.orb_radius = 16.0

        # Halos do Orbe
        self.mini_fresnel_halo = self.canvas.create_oval(0, 0, 0, 0, fill="", outline="#0F766E", width=1.2)
        self.mini_core_glow = self.canvas.create_oval(0, 0, 0, 0, fill="#042F2E", outline="")

        # Constelações internas
        self.mini_cluster_edges = []
        self.mini_cluster_nodes = []
        for cluster in self.clusters:
            for _ in cluster["edges"]:
                lid = self.canvas.create_line(0, 0, 0, 0, fill=cluster["color"], width=1.2)
                self.mini_cluster_edges.append((lid, cluster["color"]))
            for _ in cluster["nodes"]:
                nid = self.canvas.create_oval(0, 0, 0, 0, fill=cluster["color"], outline="")
                self.mini_cluster_nodes.append(nid)

        # Linhas da malha da esfera
        self.mini_sphere_lines = []
        for _ in self.sphere_lines:
            lid = self.canvas.create_line(0, 0, 0, 0, fill="#5EEAD4", width=1.0, capstyle=tk.ROUND)
            self.mini_sphere_lines.append(lid)

        # 3. Textos de Identidade & Status
        self.brand_text = self.canvas.create_text(
            pill_x1 + 54, self.orb_cy - 7,
            text="J.A.R.V.I.S.",
            font=("Consolas", 9, "bold"),
            fill="#FFFFFF",
            anchor=tk.W
        )
        self.status_text = self.canvas.create_text(
            pill_x1 + 54, self.orb_cy + 8,
            text="STANDBY",
            font=("Segoe UI", 7, "bold"),
            fill="#5EEAD4",
            anchor=tk.W
        )

        # 4. Área da Onda Sonora (Centro)
        self.wave_start_x = pill_x1 + 160
        self.wave_end_x = pill_x2 - 120
        self.wave_center_y = pill_y1 + self.pill_height // 2
        self.wave_width = self.wave_end_x - self.wave_start_x

        self.wave_lines_ids = []
        for layer in self.wave_layers:
            lid = self.canvas.create_line(
                self.wave_start_x, self.wave_center_y, self.wave_end_x, self.wave_center_y,
                fill=layer["color"], width=layer["width"], smooth=True, capstyle=tk.ROUND
            )
            self.wave_lines_ids.append(lid)

        # 5. Legenda Flutuante
        self.subtitle_id = self.canvas.create_text(
            (self.wave_start_x + self.wave_end_x) // 2, self.wave_center_y,
            text="",
            font=("Segoe UI", 9, "bold"),
            fill="#FFFFFF",
            anchor=tk.CENTER,
            state="hidden"
        )

        # 6. Badge Direita
        right_x = pill_x2 - 18
        self.badge_bg = self._create_rounded_rect(
            right_x - 70, self.orb_cy - 12, right_x, self.orb_cy + 12,
            radius=6, fill="#0F172A", outline="#1E293B", width=1
        )
        self.badge_text = self.canvas.create_text(
            right_x - 35, self.orb_cy,
            text="LOCAL 100%",
            font=("Segoe UI", 7, "bold"),
            fill="#38BDF8",
            anchor=tk.CENTER
        )

    def _start_drag(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._offset_x)
        y = self.root.winfo_y() + (event.y - self._offset_y)
        self.root.geometry(f"+{x}+{y}")

    def _escutar_sse(self):
        while True:
            try:
                req = urllib.request.Request("http://127.0.0.1:8765/events", headers={"Accept": "text/event-stream"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    for line in resp:
                        txt = line.decode("utf-8").strip()
                        if txt.startswith("data:"):
                            payload = txt[5:].strip()
                            try:
                                data = json.loads(payload)
                                self._processar_evento(data)
                            except Exception:
                                pass
            except Exception:
                time.sleep(2)

    def _processar_evento(self, data):
        def _apply():
            if "theme" in data and data["theme"] in PALETAS:
                self.current_theme = data["theme"]
                pal = PALETAS[self.current_theme]
                self.canvas.itemconfigure(self.status_text, fill=pal["primary"])
                self.canvas.itemconfigure(self.badge_text, fill=pal["accent"])
                self.canvas.itemconfigure(self.pill_bg, outline=pal["glow"])
                self.canvas.itemconfigure(self.mini_fresnel_halo, outline=pal["glow"])

            if "state" in data:
                st = data["state"]
                self.state = st
                if st == "listening":
                    self.status_label = "ESCUTANDO"
                    self.target_audio = 0.95
                    self.canvas.itemconfigure(self.status_text, text="ESCUTANDO", fill="#38BDF8")
                elif st == "thinking":
                    self.status_label = "PROCESSANDO"
                    self.target_audio = 0.50
                    self.canvas.itemconfigure(self.status_text, text="QWEN3", fill="#FBBF24")
                elif st == "speaking":
                    self.status_label = "FALANDO"
                    self.target_audio = 1.0
                    self.canvas.itemconfigure(self.status_text, text="FALANDO", fill="#00F0FF")
                elif st == "web":
                    self.status_label = "SCANNER WEB"
                    self.target_audio = 0.70
                    self.canvas.itemconfigure(self.status_text, text="GEMINI WEB", fill="#A855F7")
                else:
                    self.status_label = "STANDBY"
                    self.target_audio = 0.10
                    self.canvas.itemconfigure(self.status_text, text="STANDBY", fill="#64748B")

            if "userSpeech" in data:
                self.speech_text = f'Você: "{data["userSpeech"]}"'
                self.speech_timer = time.time() + 4.0

            if "jarvisSpeech" in data:
                self.speech_text = f'Jarvis: "{data["jarvisSpeech"]}"'
                self.speech_timer = time.time() + 5.0

        self.root.after(0, _apply)

    def _project_point(self, x, y, z, radius, cos_y, sin_y, cos_x, sin_x, fov=3.4):
        rx = x * cos_y + z * sin_y
        rz = -x * sin_y + z * cos_y
        ry = y * cos_x - rz * sin_x
        rz2 = y * sin_x + rz * cos_x

        scale = fov / (fov + rz2)
        px = self.orb_cx + rx * radius * scale
        py = self.orb_cy + ry * radius * scale
        return px, py, rz2

    def _render_loop(self):
        now = time.time()

        # 1. Modulação Dinâmica de Áudio Conforme o Estado em Tempo Real
        if self.state == "listening":
            vocal_wobble = 0.60 + 0.35 * math.sin(now * 7.5) * math.cos(now * 4.2) + 0.12 * math.sin(now * 13.0)
            self.target_audio = max(0.45, min(1.2, vocal_wobble))
        elif self.state == "speaking":
            vocal_wobble = 0.75 + 0.25 * math.sin(now * 9.0) * math.cos(now * 3.8)
            self.target_audio = max(0.55, min(1.3, vocal_wobble))
        elif self.state == "thinking":
            self.target_audio = 0.45 + 0.15 * math.sin(now * 5.0)
        else:
            self.target_audio = 0.08 + 0.03 * math.sin(now * 2.2)

        self.audio_intensity += (self.target_audio - self.audio_intensity) * 0.22
        self.smoothed_audio += (self.audio_intensity - self.smoothed_audio) * 0.25
        m = self.smoothed_audio

        pal = PALETAS.get(self.current_theme, PALETAS["ciano"])

        # Animação de Nascimento da Ilha a partir do Feixe Laser
        birth_age = now - self.birth_laser_start
        center_x = self.bar_width // 2

        if birth_age < 0.45:
            p = birth_age / 0.45
            
            # Fase 1: Expansão do feixe laser para esquerda e direita
            if p < 0.50:
                p_exp = p / 0.50
                span = (self.bar_width // 2 - 8) * math.sin(p_exp * math.pi * 0.5)
                lx1 = center_x - span
                lx2 = center_x + span
                self.canvas.coords(self.island_laser_glow, lx1, self.orb_cy, lx2, self.orb_cy)
                self.canvas.coords(self.island_laser_core, lx1, self.orb_cy, lx2, self.orb_cy)
                self.canvas.itemconfigure(self.island_laser_glow, fill=pal["accent"], state="normal")
                self.canvas.itemconfigure(self.island_laser_core, fill="#FFFFFF", state="normal")
                
                self.canvas.itemconfigure(self.pill_bg, state="hidden")
                self.canvas.itemconfigure(self.pill_glow, state="hidden")
            else:
                # Fase 2: O laser se abre na pílula e desvanece
                p_open = (p - 0.50) / 0.50
                self.canvas.itemconfigure(self.pill_bg, state="normal")
                self.canvas.itemconfigure(self.pill_glow, state="normal")
                
                fade_alpha = max(0, 1.0 - p_open * 1.5)
                if fade_alpha <= 0.05:
                    self.canvas.itemconfigure(self.island_laser_glow, state="hidden")
                    self.canvas.itemconfigure(self.island_laser_core, state="hidden")
                else:
                    self.canvas.itemconfigure(self.island_laser_glow, width=max(1, int(9.0 * fade_alpha)))
                    self.canvas.itemconfigure(self.island_laser_core, width=max(1, int(3.5 * fade_alpha)))
        else:
            self.canvas.itemconfigure(self.pill_bg, state="normal")
            self.canvas.itemconfigure(self.pill_glow, state="normal")
            self.canvas.itemconfigure(self.island_laser_glow, state="hidden")
            self.canvas.itemconfigure(self.island_laser_core, state="hidden")

        current_rad = self.orb_radius * (1.0 + m * 0.22)

        # 2. Rotação 3D
        self.rot_y += 0.03 + m * 0.06
        self.rot_x = 0.20 * math.sin(now * 0.7)

        cos_y, sin_y = math.cos(self.rot_y), math.sin(self.rot_y)
        cos_x, sin_x = math.cos(self.rot_x), math.sin(self.rot_x)

        # Halos do Mini Orbe
        halo_r = current_rad * (1.18 + m * 0.1)
        self.canvas.coords(
            self.mini_fresnel_halo,
            self.orb_cx - halo_r, self.orb_cy - halo_r,
            self.orb_cx + halo_r, self.orb_cy + halo_r
        )
        self.canvas.itemconfigure(self.mini_fresnel_halo, outline=pal["glow"])

        core_r = current_rad * 0.5
        self.canvas.coords(
            self.mini_core_glow,
            self.orb_cx - core_r, self.orb_cy - core_r,
            self.orb_cx + core_r, self.orb_cy + core_r
        )
        self.canvas.itemconfigure(self.mini_core_glow, fill=pal["deep"])

        # Renderiza Constelações Internas
        edge_cursor = 0
        node_cursor = 0
        for cluster in self.clusters:
            proj_c = []
            for nx, ny, nz in cluster["nodes"]:
                px, py, pz = self._project_point(nx, ny, nz, current_rad * 0.8, cos_y, sin_y, cos_x, sin_x)
                proj_c.append((px, py, pz))

            for e1, e2 in cluster["edges"]:
                lid, col = self.mini_cluster_edges[edge_cursor]
                edge_cursor += 1
                p1, p2 = proj_c[e1], proj_c[e2]
                self.canvas.coords(lid, p1[0], p1[1], p2[0], p2[1])
                self.canvas.itemconfigure(lid, fill=col)

            for px, py, pz in proj_c:
                nid = self.mini_cluster_nodes[node_cursor]
                node_cursor += 1
                sz = 1.6
                self.canvas.coords(nid, px - sz, py - sz, px + sz, py + sz)
                self.canvas.itemconfigure(nid, fill=cluster["color"])

        # Renderiza Malha da Esfera
        proj_nodes = []
        for ox, oy, oz in self.sphere_nodes:
            disp = 1.0 + (math.sin(ox * 3.0 + now * 2.0) * math.cos(oy * 3.0)) * (0.06 + m * 0.15)
            px, py, pz = self._project_point(ox * disp, oy * disp, oz * disp, current_rad, cos_y, sin_y, cos_x, sin_x)
            proj_nodes.append((px, py, pz))

        for idx, (i1, i2) in enumerate(self.sphere_lines):
            p1, p2 = proj_nodes[i1], proj_nodes[i2]
            lid = self.mini_sphere_lines[idx]
            avg_z = (p1[2] + p2[2]) / 2.0

            if avg_z < -0.1:
                color = pal["primary"]
                w = 1.2
            elif avg_z < 0.3:
                color = pal["secondary"]
                w = 0.9
            else:
                color = pal["glow"]
                w = 0.7

            self.canvas.coords(lid, p1[0], p1[1], p2[0], p2[1])
            self.canvas.itemconfigure(lid, fill=color, width=w)

        # 3. Gestão de Legenda Central
        if self.speech_timer > 0 and now < self.speech_timer:
            self.canvas.itemconfigure(self.subtitle_id, text=self.speech_text[:75], state="normal")
            wave_alpha = 0.2
        else:
            self.canvas.itemconfigure(self.subtitle_id, state="hidden")
            wave_alpha = 1.0

        # 4. Renderização das Ondas Neon (Ribbon Waveform)
        num_points = 32
        step_x = self.wave_width / (num_points - 1)
        max_amp = (14.0 * m + 1.5) * wave_alpha

        self.global_phase += 0.04

        for idx, layer in enumerate(self.wave_layers):
            layer["phase"] += layer["speed"] * (1.0 + m * 2.0)
            pts = []

            for i in range(num_points):
                curr_x = self.wave_start_x + i * step_x
                norm_x = i / (num_points - 1)
                envelope = math.sin(norm_x * math.pi) ** 1.5

                f = layer["freq"]
                p = layer["phase"]
                w1 = math.sin(norm_x * math.pi * f + p)
                w2 = math.cos(norm_x * math.pi * (f * 1.5) - p * 0.8) * 0.4
                w3 = math.sin(norm_x * math.pi * (f * 0.5) + self.global_phase) * 0.25

                y = self.wave_center_y + (w1 + w2 + w3) * envelope * max_amp * layer["amp_mult"]
                pts.extend([curr_x, y])

            if len(pts) >= 4:
                self.canvas.coords(self.wave_lines_ids[idx], *pts)
                if self.state == "idle":
                    self.canvas.itemconfigure(self.wave_lines_ids[idx], fill=layer["color"])
                else:
                    self.canvas.itemconfigure(self.wave_lines_ids[idx], fill=pal["primary"] if idx == 3 else layer["color"])

        self.root.after(16, self._render_loop)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = JarvisDynamicIsland()
    app.run()
