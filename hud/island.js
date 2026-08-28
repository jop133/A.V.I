/**
 * J.A.R.V.I.S. DYNAMIC ISLAND - LOGIC & THREE.JS ENGINE
 */

const THEMES = {
    'ciano': { orb: new THREE.Color(0.18, 0.83, 0.66), secondary: new THREE.Color(0.12, 0.75, 0.88), accent: '#5eead4', glow: 'rgba(94, 234, 212, 0.4)' },
    'azul': { orb: new THREE.Color(0.0, 0.94, 1.0), secondary: new THREE.Color(0.0, 0.45, 1.0), accent: '#00f0ff', glow: 'rgba(0, 240, 255, 0.4)' },
    'vermelho': { orb: new THREE.Color(0.95, 0.22, 0.22), secondary: new THREE.Color(0.96, 0.55, 0.1), accent: '#ef4444', glow: 'rgba(239, 68, 68, 0.4)' },
    'verde': { orb: new THREE.Color(0.06, 0.92, 0.48), secondary: new THREE.Color(0.1, 0.95, 0.3), accent: '#10b981', glow: 'rgba(16, 185, 129, 0.4)' },
    'roxo': { orb: new THREE.Color(0.68, 0.35, 0.98), secondary: new THREE.Color(0.92, 0.28, 0.65), accent: '#a855f7', glow: 'rgba(168, 85, 247, 0.4)' },
    'dourado': { orb: new THREE.Color(0.98, 0.75, 0.14), secondary: new THREE.Color(0.96, 0.48, 0.08), accent: '#fbbf24', glow: 'rgba(251, 191, 36, 0.4)' },
    'branco': { orb: new THREE.Color(0.95, 0.98, 1.0), secondary: new THREE.Color(0.55, 0.78, 0.98), accent: '#ffffff', glow: 'rgba(255, 255, 255, 0.4)' },
    'rosa': { orb: new THREE.Color(0.95, 0.25, 0.55), secondary: new THREE.Color(0.85, 0.2, 0.8), accent: '#f43f5e', glow: 'rgba(244, 63, 94, 0.4)' }
};

const state = {
    current: 'idle',
    theme: 'ciano',
    targetColor: new THREE.Color(0.18, 0.83, 0.66),
    targetSecColor: new THREE.Color(0.12, 0.75, 0.88),
    currentColor: new THREE.Color(0.18, 0.83, 0.66),
    currentSecColor: new THREE.Color(0.12, 0.75, 0.88),
    audioTarget: 0.1,
    audioLevel: 0.1,
    audioBass: 0.1,
};

window.addEventListener('DOMContentLoaded', () => {
    initMiniOrb();
    initWaveform();
    initEventStream();

    document.getElementById('btn-close-island')?.addEventListener('click', () => {
        window.close();
    });
});

function setTheme(themeId) {
    const theme = THEMES[themeId] || THEMES['ciano'];
    state.theme = themeId;
    state.targetColor = theme.orb.clone();
    state.targetSecColor = theme.secondary.clone();
    document.documentElement.style.setProperty('--accent', theme.accent);
    document.documentElement.style.setProperty('--accent-glow', theme.glow);
}

function setState(newState) {
    if (state.current === newState) return;
    state.current = newState;

    const statusEl = document.getElementById('island-status');
    const pillEl = document.getElementById('action-state-pill');

    if (pillEl) {
        pillEl.className = 'state-pill ' + newState;
        pillEl.textContent = newState.toUpperCase();
    }

    switch (newState) {
        case 'listening':
            if (statusEl) statusEl.textContent = 'ESCUTANDO';
            state.audioTarget = 0.9;
            state.audioBass = 0.8;
            break;
        case 'thinking':
            if (statusEl) statusEl.textContent = 'PROCESSANDO';
            state.audioTarget = 0.45;
            state.audioBass = 0.35;
            break;
        case 'speaking':
            if (statusEl) statusEl.textContent = 'FALANDO';
            state.audioTarget = 1.0;
            state.audioBass = 0.9;
            break;
        case 'web':
            if (statusEl) statusEl.textContent = 'WEB SCAN';
            state.audioTarget = 0.65;
            state.audioBass = 0.5;
            break;
        case 'idle':
        default:
            if (statusEl) statusEl.textContent = 'ONLINE';
            state.audioTarget = 0.1;
            state.audioBass = 0.08;
            break;
    }
}

// --------------------------------------------------------------------------
// 1. Mini Orbe 3D Three.js
// --------------------------------------------------------------------------
function initMiniOrb() {
    const container = document.getElementById('orb-canvas-container');
    if (!container || typeof THREE === 'undefined') return;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(36, 36);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 50);
    camera.position.set(0, 0, 3.4);

    const geo = new THREE.IcosahedronGeometry(1, 12);
    const mat = new THREE.MeshBasicMaterial({
        color: 0x5eead4,
        wireframe: true,
        transparent: true,
        opacity: 0.85
    });

    const mesh = new THREE.Mesh(geo, mat);
    scene.add(mesh);

    let start = performance.now();

    function anim(now) {
        requestAnimationFrame(anim);
        const t = (now - start) / 1000;

        state.currentColor.lerp(state.targetColor, 0.08);
        mat.color.copy(state.currentColor);

        mesh.rotation.y += 0.03 + state.audioLevel * 0.05;
        mesh.rotation.x += 0.01;

        const scale = 1 + state.audioLevel * 0.25;
        mesh.scale.set(scale, scale, scale);

        renderer.render(scene, camera);
    }
    requestAnimationFrame(anim);
}

// --------------------------------------------------------------------------
// 2. Visualizador de Ondas Sonoras Neon
// --------------------------------------------------------------------------
function initWaveform() {
    const canvas = document.getElementById('wave-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    let phase = 0;
    let smoothedLevel = 0.1;

    function renderWave() {
        requestAnimationFrame(renderWave);

        state.audioLevel += (state.audioTarget - state.audioLevel) * 0.15;
        smoothedLevel += (state.audioLevel - smoothedLevel) * 0.1;

        const w = canvas.width;
        const h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        const cy = h / 2;
        phase += 0.08 + smoothedLevel * 0.12;

        const theme = THEMES[state.theme] || THEMES['ciano'];

        // Linha de onda 1 (Principal Neon)
        ctx.beginPath();
        ctx.strokeStyle = theme.accent;
        ctx.lineWidth = 2.0;
        ctx.shadowColor = theme.accent;
        ctx.shadowBlur = 8;

        for (let x = 0; x < w; x++) {
            const normX = (x / w) * Math.PI * 2;
            const envelope = Math.sin(normX / 2); // diminui nas pontas
            const amp = (smoothedLevel * 14 + 2) * envelope;
            const y = cy + Math.sin(normX * 3 + phase) * amp * Math.cos(normX * 1.5 + phase * 0.5);

            if (x === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Linha de onda 2 (Harmônica translúcida)
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.lineWidth = 1.0;
        ctx.shadowBlur = 0;

        for (let x = 0; x < w; x++) {
            const normX = (x / w) * Math.PI * 2;
            const envelope = Math.sin(normX / 2);
            const amp = (smoothedLevel * 8 + 1) * envelope;
            const y = cy + Math.cos(normX * 4 - phase * 0.8) * amp;

            if (x === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }

    renderWave();
}

// --------------------------------------------------------------------------
// 3. Conexão em Tempo Real com o Jarvis
// --------------------------------------------------------------------------
function initEventStream() {
    const url = 'http://127.0.0.1:8765/events';
    let source = null;

    function connect() {
        try {
            source = new EventSource(url);

            source.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.state) setState(data.state);
                    if (data.theme) setTheme(data.theme);

                    const waveBox = document.querySelector('.wave-box');
                    const speechEl = document.getElementById('island-speech');

                    if (data.userSpeech) {
                        if (speechEl) speechEl.textContent = `"${data.userSpeech}"`;
                        waveBox?.classList.add('showing-text');
                        setTimeout(() => waveBox?.classList.remove('showing-text'), 3500);
                    } else if (data.jarvisSpeech) {
                        if (speechEl) speechEl.textContent = `"${data.jarvisSpeech}"`;
                        waveBox?.classList.add('showing-text');
                        setTimeout(() => waveBox?.classList.remove('showing-text'), 4000);
                    }
                } catch (e) {}
            };

            source.onerror = () => {
                source.close();
                setTimeout(connect, 2000);
            };
        } catch (e) {
            setTimeout(connect, 2000);
        }
    }

    connect();
}
