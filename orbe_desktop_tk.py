"""Orbe Holográfico 3D do J.A.R.V.I.S. (com Animação Bidirecional Completa)

- 100% Nativo Tkinter com transparência real no Windows (-transparentcolor #000001)
- Recebe e emite feixes de laser em todas as direções para transições holográficas com a HUD Completa e Bordas
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


class JarvisNativeOrb:
    TRANSPARENT_KEY = "#000001"

    def __init__(self):
        self.size = 140
        self.cx = self.size // 2
        self.cy = self.size // 2
        self.base_radius = 36.0

        self.root = tk.Tk()
        self.root.title("JARVIS_NATIVE_ORB")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        self.root.configure(bg=self.TRANSPARENT_KEY)
        try:
            self.root.wm_attributes("-transparentcolor", self.TRANSPARENT_KEY)
        except Exception:
            pass

        screen_w = self.root.winfo_screenwidth()
        pos_x = (screen_w - self.size) // 2
        pos_y = 6
        self.root.geometry(f"{self.size}x{self.size}+{pos_x}+{pos_y}")

        self.canvas = tk.Canvas(
            self.root,
            width=self.size,
            height=self.size,
            bg=self.TRANSPARENT_KEY,
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self._offset_x = 0
        self._offset_y = 0
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._on_drag)

        self.current_theme = "ciano"
        self.state = "idle"
        self.audio_level = 0.1
        self.target_audio = 0.1
        self.smoothed_audio = 0.1
        self.rot_y = 0.0
        self.rot_x = 0.0

        # Transições de Saída
        self.transitioning_to_edges = False
        self.transitioning_to_full = False
        self.exit_start_time = 0.0

        self._init_sphere_mesh()
        self._init_constellation_clusters()
        self._init_stardust()
        self._init_canvas_items()

        t = threading.Thread(target=self._escutar_sse, daemon=True)
        t.start()

        self.root.after(16, self._render_loop)

    def _init_sphere_mesh(self):
        self.lats = 10
        self.lons = 16
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

    def _init_constellation_clusters(self):
        self.clusters = [
            {"color": "#A855F7", "glow": "#7E22CE", "nodes": [], "edges": []},
            {"color": "#00F0FF", "glow": "#0284C7", "nodes": [], "edges": []},
            {"color": "#10B981", "glow": "#047857", "nodes": [], "edges": []},
            {"color": "#38BDF8", "glow": "#1E3A8A", "nodes": [], "edges": []},
        ]

        centers = [
            (-0.45, 0.40, -0.2),
            (-0.55, -0.45, 0.3),
            (0.60, 0.10, -0.1),
            (0.05, -0.15, 0.4),
        ]

        for c_idx, cluster in enumerate(self.clusters):
            cx, cy, cz = centers[c_idx]
            n_points = 6
            c_nodes = []
            for _ in range(n_points):
                nx = cx + random.uniform(-0.18, 0.18)
                ny = cy + random.uniform(-0.18, 0.18)
                nz = cz + random.uniform(-0.18, 0.18)
                c_nodes.append([nx, ny, nz])
            cluster["nodes"] = c_nodes

            c_edges = []
            for i in range(n_points):
                for j in range(i + 1, n_points):
                    dx = c_nodes[i][0] - c_nodes[j][0]
                    dy = c_nodes[i][1] - c_nodes[j][1]
                    dz = c_nodes[i][2] - c_nodes[j][2]
                    if dx*dx + dy*dy + dz*dz < 0.12:
                        c_edges.append((i, j))
            cluster["edges"] = c_edges

    def _init_stardust(self):
        self.stardust = []
        for _ in range(20):
            theta = random.uniform(0, math.pi * 2)
            phi = random.uniform(0, math.pi)
            r = random.uniform(1.2, 1.6)
            x = r * math.sin(phi) * math.cos(theta)
            y = r * math.cos(phi)
            z = r * math.sin(phi) * math.sin(theta)
            self.stardust.append([x, y, z, random.uniform(0.8, 1.8)])

    def _init_canvas_items(self):
        # 1. Feixe de Entrada do Nascimento (HUD -> Orbe vindo de baixo)
        self.incoming_laser_glow = self.canvas.create_line(self.cx, self.size, self.cx, self.cy, fill="#00F0FF", width=8.0, capstyle=tk.ROUND)
        self.incoming_laser_beam = self.canvas.create_line(self.cx, self.size, self.cx, self.cy, fill="#FFFFFF", width=3.5, capstyle=tk.ROUND)
        
        # 2. Feixes Laterais de Entrada (Bordas -> Orbe vindo dos lados)
        self.incoming_lat_left_glow = self.canvas.create_line(0, 4, self.cx, 4, fill="#00F0FF", width=7.0, capstyle=tk.ROUND)
        self.incoming_lat_left_core = self.canvas.create_line(0, 4, self.cx, 4, fill="#FFFFFF", width=3.0, capstyle=tk.ROUND)
        self.incoming_lat_right_glow = self.canvas.create_line(self.size, 4, self.cx, 4, fill="#00F0FF", width=7.0, capstyle=tk.ROUND)
        self.incoming_lat_right_core = self.canvas.create_line(self.size, 4, self.cx, 4, fill="#FFFFFF", width=3.0, capstyle=tk.ROUND)

        self.birth_shockwave = self.canvas.create_oval(0, 0, 0, 0, fill="", outline="#5EEAD4", width=2.0)
        self.birth_start_time = time.time()

        # 3. Lasers de Descarga de Saída (Orbe -> Bordas nos lados)
        self.edge_laser_left_glow = self.canvas.create_line(self.cx, 4, self.cx, 4, fill="#00F0FF", width=8.0, capstyle=tk.ROUND, state="hidden")
        self.edge_laser_left_core = self.canvas.create_line(self.cx, 4, self.cx, 4, fill="#FFFFFF", width=3.5, capstyle=tk.ROUND, state="hidden")
        self.edge_laser_right_glow = self.canvas.create_line(self.cx, 4, self.cx, 4, fill="#00F0FF", width=8.0, capstyle=tk.ROUND, state="hidden")
        self.edge_laser_right_core = self.canvas.create_line(self.cx, 4, self.cx, 4, fill="#FFFFFF", width=3.5, capstyle=tk.ROUND, state="hidden")

        # 4. Laser de Descarga para HUD Completa (Disparo para Baixo)
        self.downward_laser_glow = self.canvas.create_line(self.cx, self.cy, self.cx, self.size, fill="#00F0FF", width=8.0, capstyle=tk.ROUND, state="hidden")
        self.downward_laser_core = self.canvas.create_line(self.cx, self.cy, self.cx, self.size, fill="#FFFFFF", width=3.5, capstyle=tk.ROUND, state="hidden")

        # 5. Casca de Fresnel Exterior
        self.outer_fresnel_bubble = self.canvas.create_oval(0, 0, 0, 0, fill="", outline="#0F766E", width=1.5)
        self.inner_energy_core = self.canvas.create_oval(0, 0, 0, 0, fill="#042F2E", outline="")

        # 6. Poeira Estelar
        self.stardust_ids = []
        for _ in range(len(self.stardust)):
            p = self.canvas.create_oval(0, 0, 0, 0, fill="#64748B", outline="")
            self.stardust_ids.append(p)

        # 7. Constelações
        self.cluster_edge_ids = []
        self.cluster_node_ids = []
        for cluster in self.clusters:
            e_ids = []
            for _ in cluster["edges"]:
                lid = self.canvas.create_line(0, 0, 0, 0, fill=cluster["color"], width=1.3)
                e_ids.append(lid)
            self.cluster_edge_ids.append(e_ids)

            n_ids = []
            for _ in cluster["nodes"]:
                glow_id = self.canvas.create_oval(0, 0, 0, 0, fill="", outline=cluster["glow"], width=1.5)
                point_id = self.canvas.create_oval(0, 0, 0, 0, fill=cluster["color"], outline="")
                n_ids.append((glow_id, point_id))
            self.cluster_node_ids.append(n_ids)

        # 8. Malha Wireframe
        self.sphere_line_ids = []
        for _ in self.sphere_lines:
            lid = self.canvas.create_line(0, 0, 0, 0, fill="#5EEAD4", width=1.0, capstyle=tk.ROUND)
            self.sphere_line_ids.append(lid)

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
                                if data.get("action") == "transition_to_edges":
                                    self.transitioning_to_edges = True
                                    self.exit_start_time = time.time()
                                if data.get("action") == "transition_to_full":
                                    self.transitioning_to_full = True
                                    self.exit_start_time = time.time()
                                if "theme" in data and data["theme"] in PALETAS:
                                    self.current_theme = data["theme"]
                                if "state" in data:
                                    st = data["state"]
                                    self.state = st
                                    if st == "listening":
                                        self.target_audio = 0.95
                                    elif st == "speaking":
                                        self.target_audio = 1.0
                                    elif st == "thinking":
                                        self.target_audio = 0.50
                                    elif st == "web":
                                        self.target_audio = 0.70
                                    else:
                                        self.target_audio = 0.10
                            except Exception:
                                pass
            except Exception:
                time.sleep(2)

    def _project_point(self, x, y, z, radius, cos_y, sin_y, cos_x, sin_x, fov=3.4):
        rx = x * cos_y + z * sin_y
        rz = -x * sin_y + z * cos_y
        ry = y * cos_x - rz * sin_x
        rz2 = y * sin_x + rz * cos_x

        scale = fov / (fov + rz2)
        px = self.cx + rx * radius * scale
        py = self.cy + ry * radius * scale
        return px, py, rz2

    def _render_loop(self):
        now = time.time()

        # 1. Modulação Dinâmica de Áudio
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

        self.audio_level += (self.target_audio - self.audio_level) * 0.20
        self.smoothed_audio += (self.audio_level - self.smoothed_audio) * 0.22
        m = self.smoothed_audio

        breath = 0.5 + 0.5 * math.sin(now * 2.0)
        current_rad = self.base_radius * (1.0 + 0.04 * breath + m * 0.24)

        pal = PALETAS.get(self.current_theme, PALETAS["ciano"])

        # 2. Animação de Entrada (Nascimento do Orbe)
        birth_age = now - self.birth_start_time
        if birth_age < 0.60:
            p = birth_age / 0.60
            if p < 0.40:
                p_in = p / 0.40
                
                # Feixe vertical vindo de baixo
                beam_top = self.cy + (1.0 - p_in) * (self.size - self.cy)
                self.canvas.coords(self.incoming_laser_glow, self.cx, self.size, self.cx, beam_top)
                self.canvas.coords(self.incoming_laser_beam, self.cx, self.size, self.cx, beam_top)
                self.canvas.itemconfigure(self.incoming_laser_glow, fill=pal["accent"], state="normal")
                self.canvas.itemconfigure(self.incoming_laser_beam, fill="#FFFFFF", state="normal")

                # Feixes laterais vindos dos cantos
                lat_x = (1.0 - p_in) * self.cx
                self.canvas.coords(self.incoming_lat_left_glow, 0, 4, self.cx - lat_x, 4)
                self.canvas.coords(self.incoming_lat_left_core, 0, 4, self.cx - lat_x, 4)
                self.canvas.coords(self.incoming_lat_right_glow, self.size, 4, self.cx + lat_x, 4)
                self.canvas.coords(self.incoming_lat_right_core, self.size, 4, self.cx + lat_x, 4)
                self.canvas.itemconfigure(self.incoming_lat_left_glow, fill=pal["accent"], state="normal")
                self.canvas.itemconfigure(self.incoming_lat_left_core, fill="#FFFFFF", state="normal")
                self.canvas.itemconfigure(self.incoming_lat_right_glow, fill=pal["accent"], state="normal")
                self.canvas.itemconfigure(self.incoming_lat_right_core, fill="#FFFFFF", state="normal")
            else:
                self.canvas.itemconfigure(self.incoming_laser_glow, state="hidden")
                self.canvas.itemconfigure(self.incoming_laser_beam, state="hidden")
                self.canvas.itemconfigure(self.incoming_lat_left_glow, state="hidden")
                self.canvas.itemconfigure(self.incoming_lat_left_core, state="hidden")
                self.canvas.itemconfigure(self.incoming_lat_right_glow, state="hidden")
                self.canvas.itemconfigure(self.incoming_lat_right_core, state="hidden")

            birth_scale = math.sin(p * math.pi * 0.5) + math.sin(p * math.pi * 2.0) * 0.25 * (1.0 - p)
            birth_scale = max(0.01, min(1.3, birth_scale))
            
            shock_r = self.base_radius * (0.3 + p * 2.5)
            self.canvas.coords(
                self.birth_shockwave,
                self.cx - shock_r, self.cy - shock_r,
                self.cx + shock_r, self.cy + shock_r
            )
            self.canvas.itemconfigure(self.birth_shockwave, outline=pal["primary"], width=max(1, int(3.0 * (1.0 - p))))
        else:
            birth_scale = 1.0
            self.canvas.itemconfigure(self.incoming_laser_glow, state="hidden")
            self.canvas.itemconfigure(self.incoming_laser_beam, state="hidden")
            self.canvas.itemconfigure(self.incoming_lat_left_glow, state="hidden")
            self.canvas.itemconfigure(self.incoming_lat_left_core, state="hidden")
            self.canvas.itemconfigure(self.incoming_lat_right_glow, state="hidden")
            self.canvas.itemconfigure(self.incoming_lat_right_core, state="hidden")
            self.canvas.itemconfigure(self.birth_shockwave, outline="", width=0)

        # 3. Animações de Saída
        exit_scale = 1.0

        # Saída para Bordas (Laser Lateral)
        if self.transitioning_to_edges:
            exit_age = now - self.exit_start_time
            t_exit = min(1.0, exit_age / 0.35)
            
            laser_span = (t_exit / 0.7) * self.cx
            left_x = self.cx - laser_span
            right_x = self.cx + laser_span
            
            self.canvas.coords(self.edge_laser_left_glow, self.cx, 4, left_x, 4)
            self.canvas.coords(self.edge_laser_left_core, self.cx, 4, left_x, 4)
            self.canvas.coords(self.edge_laser_right_glow, self.cx, 4, right_x, 4)
            self.canvas.coords(self.edge_laser_right_core, self.cx, 4, right_x, 4)
            
            self.canvas.itemconfigure(self.edge_laser_left_glow, fill=pal["accent"], state="normal")
            self.canvas.itemconfigure(self.edge_laser_left_core, fill="#FFFFFF", state="normal")
            self.canvas.itemconfigure(self.edge_laser_right_glow, fill=pal["accent"], state="normal")
            self.canvas.itemconfigure(self.edge_laser_right_core, fill="#FFFFFF", state="normal")

            exit_scale = max(0.01, 1.0 - t_exit * 1.2)
        else:
            self.canvas.itemconfigure(self.edge_laser_left_glow, state="hidden")
            self.canvas.itemconfigure(self.edge_laser_left_core, state="hidden")
            self.canvas.itemconfigure(self.edge_laser_right_glow, state="hidden")
            self.canvas.itemconfigure(self.edge_laser_right_core, state="hidden")

        # Saída para HUD Completa (Disparo de Laser Vertical para Baixo)
        if self.transitioning_to_full:
            exit_age = now - self.exit_start_time
            t_exit = min(1.0, exit_age / 0.35)

            beam_len = (t_exit / 0.6) * (self.size - self.cy)
            self.canvas.coords(self.downward_laser_glow, self.cx, self.cy, self.cx, self.cy + beam_len)
            self.canvas.coords(self.downward_laser_core, self.cx, self.cy, self.cx, self.cy + beam_len)

            self.canvas.itemconfigure(self.downward_laser_glow, fill=pal["accent"], state="normal")
            self.canvas.itemconfigure(self.downward_laser_core, fill="#FFFFFF", state="normal")

            exit_scale = max(0.01, 1.0 - t_exit * 1.2)
        else:
            self.canvas.itemconfigure(self.downward_laser_glow, state="hidden")
            self.canvas.itemconfigure(self.downward_laser_core, state="hidden")

        current_rad *= (birth_scale * exit_scale)

        # 4. Rotação 3D
        self.rot_y += 0.025 + m * 0.05
        self.rot_x = 0.20 * math.sin(now * 0.6) + m * 0.12 * math.sin(now * 2.5)

        cos_y, sin_y = math.cos(self.rot_y), math.sin(self.rot_y)
        cos_x, sin_x = math.cos(self.rot_x), math.sin(self.rot_x)

        # 5. Casca de Fresnel Exterior
        bubble_r = current_rad * (1.18 + m * 0.08)
        self.canvas.coords(
            self.outer_fresnel_bubble,
            self.cx - bubble_r, self.cy - bubble_r,
            self.cx + bubble_r, self.cy + bubble_r
        )
        self.canvas.itemconfigure(self.outer_fresnel_bubble, outline=pal["glow"])

        core_r = current_rad * (0.50 + m * 0.2)
        self.canvas.coords(
            self.inner_energy_core,
            self.cx - core_r, self.cy - core_r,
            self.cx + core_r, self.cy + core_r
        )
        self.canvas.itemconfigure(self.inner_energy_core, fill=pal["deep"])

        # 6. Poeira Estelar
        for i, (sx, sy, sz, sz_size) in enumerate(self.stardust):
            px, py, pz = self._project_point(sx, sy, sz, current_rad, cos_y, sin_y, cos_x, sin_x)
            pid = self.stardust_ids[i]
            if pz < 0.6 and not self.transitioning_to_edges and not self.transitioning_to_full:
                size = sz_size * (1.0 + m * 0.5)
                self.canvas.coords(pid, px - size, py - size, px + size, py + size)
                self.canvas.itemconfigure(pid, fill=pal["secondary"] if i % 3 == 0 else "#94A3B8", state="normal")
            else:
                self.canvas.itemconfigure(pid, state="hidden")

        # 7. Constelações 3D
        for c_idx, cluster in enumerate(self.clusters):
            proj_cluster = []
            for nx, ny, nz in cluster["nodes"]:
                px, py, pz = self._project_point(nx, ny, nz, current_rad * 0.85, cos_y, sin_y, cos_x, sin_x)
                proj_cluster.append((px, py, pz))

            e_ids = self.cluster_edge_ids[c_idx]
            for e_idx, (i1, i2) in enumerate(cluster["edges"]):
                p1 = proj_cluster[i1]
                p2 = proj_cluster[i2]
                lid = e_ids[e_idx]
                self.canvas.coords(lid, p1[0], p1[1], p2[0], p2[1])
                self.canvas.itemconfigure(lid, fill=cluster["color"], width=1.4 if m > 0.3 else 1.1)

            n_ids = self.cluster_node_ids[c_idx]
            for n_idx, (px, py, pz) in enumerate(proj_cluster):
                glow_id, point_id = n_ids[n_idx]
                halo_sz = (4.5 + m * 3.5) * (1.0 - pz * 0.3)
                dot_sz = 1.8 + m * 1.0

                self.canvas.coords(glow_id, px - halo_sz, py - halo_sz, px + halo_sz, py + halo_sz)
                self.canvas.itemconfigure(glow_id, outline=cluster["glow"])

                self.canvas.coords(point_id, px - dot_sz, py - dot_sz, px + dot_sz, py + dot_sz)
                self.canvas.itemconfigure(point_id, fill=cluster["color"])

        # 8. Malha Wireframe 3D
        proj_sphere = []
        for i, (ox, oy, oz) in enumerate(self.sphere_nodes):
            n1 = math.sin(ox * 3.0 + now * 2.2) * math.cos(oy * 3.0 - now * 1.5) * 0.5
            n2 = math.sin(oz * 4.0 + now * 2.8) * 0.3 * (0.2 + m)
            disp = 1.0 + (n1 + n2) * (0.07 + m * 0.20)

            vx = ox * disp
            vy = oy * disp
            vz = oz * disp

            px, py, pz = self._project_point(vx, vy, vz, current_rad, cos_y, sin_y, cos_x, sin_x)
            proj_sphere.append((px, py, pz))

        for idx, (i1, i2) in enumerate(self.sphere_lines):
            p1 = proj_sphere[i1]
            p2 = proj_sphere[i2]
            lid = self.sphere_line_ids[idx]

            avg_z = (p1[2] + p2[2]) / 2.0

            if avg_z < -0.15:
                color = pal["primary"]
                w = 1.3 if m > 0.3 else 1.0
            elif avg_z < 0.3:
                color = pal["secondary"]
                w = 0.9
            else:
                color = pal["glow"]
                w = 0.7

            self.canvas.coords(lid, p1[0], p1[1], p2[0], p2[1])
            self.canvas.itemconfigure(lid, fill=color, width=w)

        self.root.after(16, self._render_loop)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = JarvisNativeOrb()
    app.run()
