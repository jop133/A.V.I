// O token da sessao chega pela query string da URL (ver hud_app.py). Sem ele
// o servidor devolve 403 -- e o que impede um site qualquer aberto no
// navegador de abrir este mesmo EventSource e ler o que o usuario fala.
function urlDosEventos() {
    const token = new URLSearchParams(location.search).get('token') || '';
    return 'http://127.0.0.1:8765/events?token=' + encodeURIComponent(token);
}

/**
 * J.A.R.V.I.S. COSMOS SHADER ENGINE - 100% IDÊNTICO AO TRILLION (HELLOTRILLION.AI)
 * Suporte a Temas de Cores Dinâmicos, Controle de Brilho e Modo Orbe Superior (Top Orb)
 */

// --------------------------------------------------------------------------
// Paletas de Cores Disponíveis
// --------------------------------------------------------------------------
const THEMES = {
    'ciano': {
        name: 'Ciano Trillion',
        orb: new THREE.Color(0.18, 0.83, 0.66),
        secondary: new THREE.Color(0.12, 0.75, 0.88),
        accent: '#5eead4',
        accentGlow: 'rgba(94, 234, 212, 0.35)',
        nebulaTeal: [0.0, 0.08, 0.06],
        nebulaPurple: [0.05, 0.01, 0.08]
    },
    'azul': {
        name: 'Azul Jarvis',
        orb: new THREE.Color(0.0, 0.94, 1.0),
        secondary: new THREE.Color(0.0, 0.45, 1.0),
        accent: '#00f0ff',
        accentGlow: 'rgba(0, 240, 255, 0.45)',
        nebulaTeal: [0.0, 0.08, 0.08],
        nebulaPurple: [0.01, 0.03, 0.09]
    },
    'vermelho': {
        name: 'Vermelho Stark',
        orb: new THREE.Color(0.95, 0.22, 0.22),
        secondary: new THREE.Color(0.96, 0.55, 0.1),
        accent: '#ef4444',
        accentGlow: 'rgba(239, 68, 68, 0.45)',
        nebulaTeal: [0.09, 0.01, 0.01],
        nebulaPurple: [0.07, 0.02, 0.0]
    },
    'verde': {
        name: 'Verde Matrix',
        orb: new THREE.Color(0.06, 0.92, 0.48),
        secondary: new THREE.Color(0.1, 0.95, 0.3),
        accent: '#10b981',
        accentGlow: 'rgba(16, 185, 129, 0.45)',
        nebulaTeal: [0.01, 0.09, 0.03],
        nebulaPurple: [0.0, 0.06, 0.02]
    },
    'roxo': {
        name: 'Roxo Cyberpunk',
        orb: new THREE.Color(0.68, 0.35, 0.98),
        secondary: new THREE.Color(0.92, 0.28, 0.65),
        accent: '#a855f7',
        accentGlow: 'rgba(168, 85, 247, 0.45)',
        nebulaTeal: [0.05, 0.01, 0.08],
        nebulaPurple: [0.08, 0.0, 0.07]
    },
    'dourado': {
        name: 'Dourado Solar',
        orb: new THREE.Color(0.98, 0.75, 0.14),
        secondary: new THREE.Color(0.96, 0.48, 0.08),
        accent: '#fbbf24',
        accentGlow: 'rgba(251, 191, 36, 0.45)',
        nebulaTeal: [0.08, 0.06, 0.0],
        nebulaPurple: [0.07, 0.03, 0.0]
    },
    'branco': {
        name: 'Gelo Prateado',
        orb: new THREE.Color(0.95, 0.98, 1.0),
        secondary: new THREE.Color(0.55, 0.78, 0.98),
        accent: '#ffffff',
        accentGlow: 'rgba(255, 255, 255, 0.45)',
        nebulaTeal: [0.04, 0.05, 0.07],
        nebulaPurple: [0.03, 0.04, 0.06]
    },
    'rosa': {
        name: 'Rosa Neon',
        orb: new THREE.Color(0.95, 0.25, 0.55),
        secondary: new THREE.Color(0.85, 0.2, 0.8),
        accent: '#f43f5e',
        accentGlow: 'rgba(244, 63, 94, 0.45)',
        nebulaTeal: [0.08, 0.01, 0.04],
        nebulaPurple: [0.06, 0.01, 0.07]
    }
};

// --------------------------------------------------------------------------
// Estado Global do HUD
// --------------------------------------------------------------------------
const state = {
    current: 'idle',
    theme: 'ciano',
    targetOrbColor: new THREE.Color(0.18, 0.83, 0.66),
    targetSecondaryColor: new THREE.Color(0.12, 0.75, 0.88),
    currentOrbColor: new THREE.Color(0.18, 0.83, 0.66),
    currentSecondaryColor: new THREE.Color(0.12, 0.75, 0.88),
    brightness: 1.0,
    targetBrightness: 1.0,
    audioLevel: 0.1,
    audioTarget: 0.1,
    audioBass: 0.1,
    connected: false,
    sfxEnabled: true,
    audioCtx: null,
    transitioningToOrb: false,
    vortexProgress: 0.0
};

// --------------------------------------------------------------------------
// Inicialização ao carregar
// --------------------------------------------------------------------------
window.addEventListener('DOMContentLoaded', () => {
    initTrillionCosmosEngine();
    initControls();
    initSfxToggle();
    initEventStream();
    
    document.addEventListener('click', initAudioContext, { once: true });

    setTimeout(() => {
        playSfx('boot');
    }, 500);
});

// --------------------------------------------------------------------------
// Alteração de Tema e Brilho Dinâmicos
// --------------------------------------------------------------------------
function setTheme(themeId) {
    const theme = THEMES[themeId] || THEMES['ciano'];
    state.theme = themeId;
    state.targetOrbColor = theme.orb.clone();
    state.targetSecondaryColor = theme.secondary.clone();

    // Atualiza CSS Variables dinamicamente para sincronia total
    document.documentElement.style.setProperty('--accent-teal', theme.accent);
    document.documentElement.style.setProperty('--accent-teal-glow', theme.accentGlow);

    console.log(`[HUD] Tema alterado por voz para: ${theme.name}`);
}

function setBrightness(level) {
    state.targetBrightness = Math.max(0.25, Math.min(2.0, level));
    console.log(`[HUD] Nível de brilho ajustado para: ${state.targetBrightness}`);
}

// --------------------------------------------------------------------------
// Motor de Efeitos Sonoros Sci-Fi (Web Audio API)
// --------------------------------------------------------------------------
function initAudioContext() {
    if (!state.audioCtx) {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        state.audioCtx = new AudioContext();
    }
    if (state.audioCtx.state === 'suspended') {
        state.audioCtx.resume();
    }
}

function playSfx(type) {
    if (!state.sfxEnabled) return;
    initAudioContext();
    const ctx = state.audioCtx;
    if (!ctx) return;

    const now = ctx.currentTime;

    try {
        switch (type) {
            case 'boot': {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(140, now);
                osc.frequency.exponentialRampToValueAtTime(880, now + 0.6);

                gain.gain.setValueAtTime(0.01, now);
                gain.gain.linearRampToValueAtTime(0.2, now + 0.2);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.8);

                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now);
                osc.stop(now + 0.85);

                const osc2 = ctx.createOscillator();
                const gain2 = ctx.createGain();
                osc2.type = 'triangle';
                osc2.frequency.setValueAtTime(280, now + 0.1);
                osc2.frequency.exponentialRampToValueAtTime(1320, now + 0.7);

                gain2.gain.setValueAtTime(0.01, now + 0.1);
                gain2.gain.linearRampToValueAtTime(0.15, now + 0.3);
                gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.9);

                osc2.connect(gain2);
                gain2.connect(ctx.destination);
                osc2.start(now + 0.1);
                osc2.stop(now + 0.95);
                break;
            }

            case 'listen': {
                [0, 0.12].forEach((delay, idx) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.setValueAtTime(idx === 0 ? 659 : 880, now + delay);

                    gain.gain.setValueAtTime(0.2, now + delay);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + delay + 0.15);

                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.start(now + delay);
                    osc.stop(now + delay + 0.18);
                });
                break;
            }

            case 'think': {
                const freqs = [523, 659, 784, 1046];
                freqs.forEach((freq, idx) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.type = 'sine';
                    const t = now + idx * 0.05;
                    osc.frequency.setValueAtTime(freq, t);

                    gain.gain.setValueAtTime(0.1, t);
                    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.09);

                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.start(t);
                    osc.stop(t + 0.1);
                });
                break;
            }

            case 'speak': {
                [440, 554, 659].forEach((freq) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.setValueAtTime(freq, now);

                    gain.gain.setValueAtTime(0.01, now);
                    gain.gain.linearRampToValueAtTime(0.12, now + 0.05);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);

                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.start(now);
                    osc.stop(now + 0.45);
                });
                break;
            }

            case 'web': {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(1200, now);
                osc.frequency.exponentialRampToValueAtTime(300, now + 0.35);

                gain.gain.setValueAtTime(0.12, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);

                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now);
                osc.stop(now + 0.42);
                break;
            }

            case 'click': {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'triangle';
                osc.frequency.setValueAtTime(1200, now);
                gain.gain.setValueAtTime(0.08, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now);
                osc.stop(now + 0.05);
                break;
            }
        }
    } catch (e) {
        console.warn('Erro SFX:', e);
    }
}

function initSfxToggle() {
    const btn = document.getElementById('btn-sfx-toggle');
    if (!btn) return;
    btn.addEventListener('click', () => {
        state.sfxEnabled = !state.sfxEnabled;
        if (state.sfxEnabled) {
            btn.classList.remove('muted');
            btn.textContent = '🔊';
            playSfx('click');
        } else {
            btn.classList.add('muted');
            btn.textContent = '🔇';
        }
    });
}

// --------------------------------------------------------------------------
// Gerenciador de Estados do Jarvis
// --------------------------------------------------------------------------
function setState(newState) {
    if (state.current === newState) return;
    state.current = newState;

    document.body.classList.remove('state-idle', 'state-listening', 'state-thinking', 'state-speaking', 'state-web');
    document.body.classList.add(`state-${newState}`);

    const statusLabel = document.getElementById('status-label');
    const speechRole = document.getElementById('speech-role');

    switch (newState) {
        case 'listening':
            if (statusLabel) statusLabel.textContent = 'ESCUTANDO MICROFONE · CAPTURA VAD';
            if (speechRole) speechRole.textContent = 'VOCÊ';
            state.audioTarget = 0.9;
            state.audioBass = 0.8;
            playSfx('listen');
            break;

        case 'thinking':
            if (statusLabel) statusLabel.textContent = 'PROCESSANDO NO QWEN3 LOCAL // OLLAMA';
            if (speechRole) speechRole.textContent = 'J.A.R.V.I.S.';
            state.audioTarget = 0.45;
            state.audioBass = 0.35;
            playSfx('think');
            break;

        case 'speaking':
            if (statusLabel) statusLabel.textContent = 'TRANSMITINDO ÁUDIO 24kHz · CARTESIA HD';
            if (speechRole) speechRole.textContent = 'J.A.R.V.I.S.';
            state.audioTarget = 1.0;
            state.audioBass = 0.9;
            playSfx('speak');
            break;

        case 'web':
            if (statusLabel) statusLabel.textContent = 'SCANNER WEB EM TEMPO REAL // GEMINI';
            if (speechRole) speechRole.textContent = 'GEMINI WEB';
            state.audioTarget = 0.65;
            state.audioBass = 0.5;
            playSfx('web');
            break;

        case 'idle':
        default:
            if (statusLabel) statusLabel.textContent = 'ALL SYSTEMS NORMAL · WATCHING 6 CHANNELS';
            if (speechRole) speechRole.textContent = 'J.A.R.V.I.S.';
            state.audioTarget = 0.1;
            state.audioBass = 0.08;
            break;
    }
}

// --------------------------------------------------------------------------
// Efeito de Digitação
// --------------------------------------------------------------------------
// Timer da digitacao em curso, por elemento. Sem isto, duas chamadas
// seguidas deixam DUAS cadeias de setTimeout escrevendo no mesmo elemento:
// limpar o textContent nao para a cadeia antiga, e as letras das duas se
// intercalam. O resultado e um texto com as letras certas fora de ordem.
// Aparece sempre, porque o fluxo normal ja manda userSpeech e logo depois
// jarvisSpeech -- e piorou muito quando a voz passou a sair frase a frase,
// porque cada frase virou um evento.
const timersDigitacao = {};

function typeWriter(elementId, text, speed = 18) {
    const el = document.getElementById(elementId);
    if (!el) return;

    if (timersDigitacao[elementId]) {
        clearTimeout(timersDigitacao[elementId]);
        timersDigitacao[elementId] = null;
    }

    el.textContent = '';
    let i = 0;

    function type() {
        if (i < text.length) {
            el.textContent += text.charAt(i);
            i++;
            timersDigitacao[elementId] = setTimeout(type, speed);
        } else {
            timersDigitacao[elementId] = null;
        }
    }
    type();
}

// --------------------------------------------------------------------------
// Controles Nativos de Janela
// --------------------------------------------------------------------------
function initControls() {
    document.getElementById('win-close')?.addEventListener('click', () => {
        playSfx('click');
        window.close();
    });

    document.getElementById('win-min')?.addEventListener('click', () => {
        playSfx('click');
        document.body.classList.toggle('minimized-widget');
    });
}

// --------------------------------------------------------------------------
// MOTOR 3D TRILLION COSMOS (GLSL SHADERS & THREE.JS)
// --------------------------------------------------------------------------
function initTrillionCosmosEngine() {
    const container = document.getElementById('canvas-container');
    if (!container || typeof THREE === 'undefined') return;

    // GLSL Simplex Noise
    const noiseGLSL = `
        vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
        vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
        vec4 permute(vec4 x) { return mod289(((x*34.0)+10.0)*x); }
        vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

        float snoise(vec3 v) {
            const vec2 C = vec2(1.0/6.0, 1.0/3.0);
            const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
            vec3 i = floor(v + dot(v, C.yyy));
            vec3 x0 = v - i + dot(i, C.xxx);
            vec3 g = step(x0.yzx, x0.xyz);
            vec3 l = 1.0 - g;
            vec3 i1 = min(g.xyz, l.zxy);
            vec3 i2 = max(g.xyz, l.zxy);
            vec3 x1 = x0 - i1 + C.xxx;
            vec3 x2 = x0 - i2 + C.yyy;
            vec3 x3 = x0 - D.yyy;
            i = mod289(i);
            vec4 p = permute(permute(permute(
                i.z + vec4(0.0, i1.z, i2.z, 1.0))
                + i.y + vec4(0.0, i1.y, i2.y, 1.0))
                + i.x + vec4(0.0, i1.x, i2.x, 1.0));
            float n_ = 0.142857142857;
            vec3 ns = n_ * D.wyz - D.xzx;
            vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
            vec4 x_ = floor(j * ns.z);
            vec4 y_ = floor(j - 7.0 * x_);
            vec4 x = x_ * ns.x + ns.yyyy;
            vec4 y = y_ * ns.x + ns.yyyy;
            vec4 h = 1.0 - abs(x) - abs(y);
            vec4 b0 = vec4(x.xy, y.xy);
            vec4 b1 = vec4(x.zw, y.zw);
            vec4 s0 = floor(b0)*2.0 + 1.0;
            vec4 s1 = floor(b1)*2.0 + 1.0;
            vec4 sh = -step(h, vec4(0.0));
            vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
            vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
            vec3 p0 = vec3(a0.xy,h.x);
            vec3 p1 = vec3(a0.zw,h.y);
            vec3 p2 = vec3(a1.xy,h.z);
            vec3 p3 = vec3(a1.zw,h.w);
            vec4 norm = taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
            p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
            vec4 m = max(0.6 - vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)), 0.0);
            m = m * m;
            return 42.0 * dot(m*m, vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
        }
    `;

    // Vertex Shader do Orbe
    const orbVertexShader = `
        uniform float uTime;
        uniform float uAudioLevel;
        uniform float uAudioBass;
        uniform float uNoiseSpeed;
        uniform float uDisplacementAmp;
        uniform float uBreathing;

        varying vec3 vNormal;
        varying vec3 vPosition;
        varying float vDisplacement;

        ${noiseGLSL}

        void main() {
            vNormal = normalize(normalMatrix * normal);
            float n1 = snoise(position * 1.5 + uTime * uNoiseSpeed * 0.3) * 0.5;
            float n2 = snoise(position * 3.0 + uTime * uNoiseSpeed * 0.5) * 0.3;
            float n3 = snoise(position * 6.0 + uTime * uNoiseSpeed * 1.8) * 0.2 * uAudioLevel;
            float noiseVal = n1 + n2 + n3;
            float breathDisp = uBreathing * 0.04;
            float audioDisp = uAudioLevel * uDisplacementAmp * 0.55;
            float bassDisp = uAudioBass * uDisplacementAmp * 0.35;
            float bassPush = uAudioBass * 0.08 * sin(uTime * 2.5 + length(position) * 3.0);
            float totalDisp = noiseVal * (breathDisp + audioDisp + bassDisp + 0.02) + bassPush;
            totalDisp = clamp(totalDisp, -0.45, 0.45);
            vec3 displaced = position + normal * totalDisp;
            vDisplacement = totalDisp;
            vPosition = (modelViewMatrix * vec4(displaced, 1.0)).xyz;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
        }
    `;

    // Fragment Shader do Orbe
    const orbFragmentShader = `
        uniform vec3 uColor;
        uniform vec3 uColorSecondary;
        uniform float uFresnelPower;
        uniform float uOpacity;
        uniform float uColorMix;

        varying vec3 vNormal;
        varying vec3 vPosition;
        varying float vDisplacement;

        void main() {
            vec3 viewDir = normalize(-vPosition);
            float fresnel = pow(1.0 - abs(dot(viewDir, vNormal)), uFresnelPower);
            vec3 baseColor = mix(uColor, uColorSecondary, uColorMix);
            float dispTint = smoothstep(-0.05, 0.25, vDisplacement);
            vec3 finalColor = baseColor * (0.1 + fresnel * 0.9 + dispTint * 0.25);
            float finalAlpha = uOpacity * (0.2 + fresnel * 0.8);
            gl_FragColor = vec4(finalColor, finalAlpha);
        }
    `;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);
    container.appendChild(renderer.domElement);

    // ----------------------------------------------------------------------
    // PASSADA 1: FBM Nebula & Procedural Starfield Quad
    // ----------------------------------------------------------------------
    const bgScene = new THREE.Scene();
    const bgCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

    const bgUniforms = {
        uTime: { value: 0 },
        uOrbPos: { value: new THREE.Vector2(0.5, 0.5) },
        uOrbColor: { value: new THREE.Vector3(0.18, 0.83, 0.66) },
        uOrbGlow: { value: 0.35 },
        uVoiceBright: { value: 0 },
        uNebulaBright: { value: 0.7 }
    };

    const bgMaterial = new THREE.ShaderMaterial({
        vertexShader: `
            varying vec2 vUv;
            void main() { vUv = uv; gl_Position = vec4(position.xy, 0.9999, 1.0); }
        `,
        fragmentShader: `
            precision highp float;
            varying vec2 vUv;

            uniform float uTime;
            uniform vec2  uOrbPos;
            uniform vec3  uOrbColor;
            uniform float uOrbGlow;
            uniform float uVoiceBright;
            uniform float uNebulaBright;

            float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }

            float vnoise(vec2 p){
                vec2 i=floor(p), f=fract(p);
                f=f*f*(3.-2.*f);
                return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),
                           mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);
            }

            float fbm(vec2 p){
                float v=0., a=.5;
                mat2 rot=mat2(.8,-.6,.6,.8);
                for(int i=0;i<5;i++){ v+=a*vnoise(p); p=rot*p*2.1; a*=.48; }
                return v;
            }

            void main(){
                vec2 uv = vUv;
                float edgeDist = length(uv - 0.5);
                vec3 col = mix(vec3(0.012, 0.016, 0.04), vec3(0.004, 0.006, 0.018), edgeDist);

                // Nebula wisps
                float neb1 = fbm(uv * 3.0 + vec2(uTime * 0.002, uTime * 0.001));
                col += uOrbColor * 0.12 * smoothstep(0.40, 0.68, neb1) * uNebulaBright;

                float neb2 = fbm(uv * 2.5 + vec2(50.0, 30.0) + vec2(-uTime * 0.001, uTime * 0.0015));
                col += vec3(0.05, 0.01, 0.08) * smoothstep(0.45, 0.70, neb2) * uNebulaBright * 0.7;

                // Orb radiance
                float orbDist = length((uv - uOrbPos) * vec2(1.0, 1.2));
                col += uOrbColor * exp(-orbDist*orbDist / 0.18) * uOrbGlow * 0.20;
                col += uOrbColor * exp(-orbDist*orbDist / 0.06) * uOrbGlow * 0.30;
                col += vec3(0.7, 0.95, 0.9) * exp(-orbDist*orbDist / 0.010) * uOrbGlow * 0.18;
                col += uOrbColor * exp(-orbDist*orbDist / 0.12) * uVoiceBright * 0.30;

                // Small stars
                vec2 sg1 = floor(uv * vec2(400.0, 250.0));
                float sv1 = hash(sg1);
                float star1 = step(0.992, sv1);
                star1 *= 0.3 + 0.7 * hash(sg1 + 100.0);
                star1 *= 0.5 + 0.5 * sin(uTime * (1.2 + hash(sg1 + 200.0) * 3.0) + sv1 * 40.0);
                col += vec3(0.7, 0.8, 1.0) * star1 * 0.45;

                // Medium stars
                vec2 sg2 = floor(uv * vec2(100.0, 65.0));
                float sv2 = hash(sg2 + 500.0);
                float star2 = step(0.984, sv2);
                float sd2 = length(fract(uv * vec2(100.0, 65.0)) - 0.5);
                star2 *= exp(-sd2*sd2 / 0.025);
                star2 *= 0.4 + 0.6 * hash(sg2 + 600.0);
                star2 *= 0.6 + 0.4 * sin(uTime * (0.8 + hash(sg2 + 700.0) * 2.0) + sv2 * 30.0);
                col += vec3(0.8, 0.85, 1.0) * star2 * 0.55;

                // Vignette
                col *= 1.0 - 0.40 * pow(edgeDist * 1.5, 2.0);

                gl_FragColor = vec4(col, 1.0);
            }
        `,
        uniforms: bgUniforms,
        depthWrite: false,
        depthTest: false
    });

    const bgMesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), bgMaterial);
    bgScene.add(bgMesh);

    // ----------------------------------------------------------------------
    // PASSADA 2: Constelação 3D & Nodos
    // ----------------------------------------------------------------------
    const starTexture = (() => {
        const c = document.createElement('canvas');
        c.width = c.height = 32;
        const ctx = c.getContext('2d');
        const g = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
        g.addColorStop(0, 'rgba(255,255,255,1)');
        g.addColorStop(0.3, 'rgba(255,255,255,0.5)');
        g.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, 32, 32);
        return new THREE.CanvasTexture(c);
    })();

    const constellationScene = new THREE.Scene();
    const constellationCamera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 250);
    constellationCamera.position.set(0, 0, 42);

    const dustPositions = new Float32Array(1500);
    for (let i = 0; i < 500; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const r = 20 + Math.random() * 70;
        dustPositions[3 * i] = r * Math.sin(phi) * Math.cos(theta);
        dustPositions[3 * i + 1] = r * Math.sin(phi) * Math.sin(theta);
        dustPositions[3 * i + 2] = r * Math.cos(phi);
    }
    const dustGeo = new THREE.BufferGeometry();
    dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPositions, 3));
    const dustMat = new THREE.PointsMaterial({
        map: starTexture,
        size: 1.2,
        transparent: true,
        opacity: 0.22,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        sizeAttenuation: true,
        color: 0x8898ac
    });
    constellationScene.add(new THREE.Points(dustGeo, dustMat));

    const palette = [
        [0.18, 0.83, 0.66], [0.12, 0.75, 0.88], [0.25, 0.5, 0.82], [0.5, 0.25, 0.75],
        [0.19, 0.88, 0.63], [0.35, 0.4, 0.85], [0.15, 0.65, 0.78], [0.4, 0.3, 0.8]
    ];

    const nodePositions = new Float32Array(300);
    const nodeColors = new Float32Array(300);
    const clusterCenters = [];

    for (let i = 0; i < 8; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const r = 13 + Math.random() * 12;
        clusterCenters.push([r * Math.sin(phi) * Math.cos(theta), r * Math.sin(phi) * Math.sin(theta), r * Math.cos(phi)]);
    }

    let nodeIdx = 0;
    for (let i = 0; i < 8; i++) {
        const count = 10 + Math.floor(Math.random() * 4);
        const [cx, cy, cz] = clusterCenters[i];
        const spread = 3 + Math.random() * 4;
        const col = palette[i];

        for (let j = 0; j < count && nodeIdx < 100; j++) {
            nodePositions[3 * nodeIdx] = cx + (Math.random() - 0.5) * spread * 2;
            nodePositions[3 * nodeIdx + 1] = cy + (Math.random() - 0.5) * spread * 2;
            nodePositions[3 * nodeIdx + 2] = cz + (Math.random() - 0.5) * spread * 2;
            nodeColors[3 * nodeIdx] = col[0];
            nodeColors[3 * nodeIdx + 1] = col[1];
            nodeColors[3 * nodeIdx + 2] = col[2];
            nodeIdx++;
        }
    }

    const nodeGeo = new THREE.BufferGeometry();
    nodeGeo.setAttribute('position', new THREE.BufferAttribute(nodePositions, 3));
    nodeGeo.setAttribute('color', new THREE.BufferAttribute(nodeColors, 3));

    const nodeMat = new THREE.PointsMaterial({
        map: starTexture,
        size: 2.8,
        transparent: true,
        opacity: 0.7,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        sizeAttenuation: true,
        vertexColors: true
    });

    const edges = [];
    for (let i = 0; i < 100; i++) {
        for (let j = i + 1; j < 100; j++) {
            const dx = nodePositions[3 * i] - nodePositions[3 * j];
            const dy = nodePositions[3 * i + 1] - nodePositions[3 * j + 1];
            const dz = nodePositions[3 * i + 2] - nodePositions[3 * j + 2];
            if (dx * dx + dy * dy + dz * dz < 100) {
                edges.push([i, j]);
            }
        }
    }

    const edgePositions = new Float32Array(edges.length * 6);
    const edgeColors = new Float32Array(edges.length * 6);
    for (let i = 0; i < edges.length; i++) {
        const [a, b] = edges[i];
        const idx = i * 6;
        edgePositions[idx] = nodePositions[3 * a];
        edgePositions[idx + 1] = nodePositions[3 * a + 1];
        edgePositions[idx + 2] = nodePositions[3 * a + 2];
        edgePositions[idx + 3] = nodePositions[3 * b];
        edgePositions[idx + 4] = nodePositions[3 * b + 1];
        edgePositions[idx + 5] = nodePositions[3 * b + 2];

        edgeColors[idx] = nodeColors[3 * a];
        edgeColors[idx + 1] = nodeColors[3 * a + 1];
        edgeColors[idx + 2] = nodeColors[3 * a + 2];
        edgeColors[idx + 3] = nodeColors[3 * b];
        edgeColors[idx + 4] = nodeColors[3 * b + 1];
        edgeColors[idx + 5] = nodeColors[3 * b + 2];
    }

    const edgeGeo = new THREE.BufferGeometry();
    edgeGeo.setAttribute('position', new THREE.BufferAttribute(edgePositions, 3));
    edgeGeo.setAttribute('color', new THREE.BufferAttribute(edgeColors, 3));

    const edgeMat = new THREE.LineBasicMaterial({
        transparent: true,
        opacity: 0.15,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        vertexColors: true
    });

    const constellationGroup = new THREE.Group();
    constellationGroup.add(new THREE.Points(nodeGeo, nodeMat));
    constellationGroup.add(new THREE.LineSegments(edgeGeo, edgeMat));
    constellationScene.add(constellationGroup);

    // ----------------------------------------------------------------------
    // PASSADA 3: Orbe 3D Simplex-Noise Wireframe
    // ----------------------------------------------------------------------
    const orbScene = new THREE.Scene();
    const orbCamera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100);
    orbCamera.position.set(0, 0, 4.2);

    const orbGeometry = new THREE.IcosahedronGeometry(1, 20);
    const orbUniforms = {
        uTime: { value: 0 },
        uAudioLevel: { value: 0 },
        uAudioBass: { value: 0 },
        uNoiseSpeed: { value: 0.35 },
        uDisplacementAmp: { value: 0.18 },
        uBreathing: { value: 0.5 },
        uColor: { value: state.currentOrbColor },
        uColorSecondary: { value: state.currentSecondaryColor },
        uFresnelPower: { value: 2.5 },
        uOpacity: { value: 0.85 },
        uColorMix: { value: 0 }
    };

    const orbMaterial = new THREE.ShaderMaterial({
        uniforms: orbUniforms,
        vertexShader: orbVertexShader,
        fragmentShader: orbFragmentShader,
        transparent: true,
        depthWrite: false,
        wireframe: true
    });

    const orbMesh = new THREE.Mesh(orbGeometry, orbMaterial);
    orbScene.add(orbMesh);

    const shellGeometry = new THREE.IcosahedronGeometry(1.3, 12);
    const shellMaterial = new THREE.ShaderMaterial({
        uniforms: {
            uColor: { value: state.currentOrbColor },
            uOpacity: { value: 0.1 }
        },
        vertexShader: `
            varying vec3 vNormal;
            varying vec3 vPosition;
            void main() {
                vNormal = normalize(normalMatrix * normal);
                vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
        fragmentShader: `
            uniform vec3 uColor;
            uniform float uOpacity;
            varying vec3 vNormal;
            varying vec3 vPosition;
            void main() {
                vec3 viewDir = normalize(-vPosition);
                float fresnel = pow(1.0 - abs(dot(viewDir, vNormal)), 2.5);
                gl_FragColor = vec4(uColor, uOpacity * fresnel * 0.6);
            }
        `,
        transparent: true,
        depthWrite: false,
        side: THREE.BackSide,
        blending: THREE.AdditiveBlending
    });

    const shellMesh = new THREE.Mesh(shellGeometry, shellMaterial);
    orbScene.add(shellMesh);

    // ----------------------------------------------------------------------
    // LOOP DE RENDERIZAÇÃO
    // ----------------------------------------------------------------------
    let startTime = performance.now();
    let smoothedLevel = 0;
    let smoothedBass = 0;

    function animate(now) {
        requestAnimationFrame(animate);

        const time = (now - startTime) / 1000;
        bgUniforms.uTime.value = time;
        orbUniforms.uTime.value = time;
        orbUniforms.uBreathing.value = 0.5 + 0.5 * Math.sin(0.7 * time);

        // Interpolação de Cores Suave (Transição Fluida de Tema)
        state.currentOrbColor.lerp(state.targetOrbColor, 0.08);
        state.currentSecondaryColor.lerp(state.targetSecondaryColor, 0.08);
        state.brightness += (state.targetBrightness - state.brightness) * 0.08;

        bgUniforms.uOrbColor.value.set(state.currentOrbColor.r, state.currentOrbColor.g, state.currentOrbColor.b);
        orbUniforms.uColor.value.copy(state.currentOrbColor);
        orbUniforms.uColorSecondary.value.copy(state.currentSecondaryColor);
        shellMaterial.uniforms.uColor.value.copy(state.currentOrbColor);

        // Suavização do áudio
        state.audioLevel += (state.audioTarget - state.audioLevel) * 0.15;
        smoothedLevel += (state.audioLevel - smoothedLevel) * (state.audioLevel > smoothedLevel ? 0.45 : 0.08);
        smoothedBass += (state.audioBass - smoothedBass) * (state.audioBass > smoothedBass ? 0.45 : 0.08);

        const m = smoothedLevel;
        const x = smoothedBass;

        orbUniforms.uAudioLevel.value = m;
        orbUniforms.uAudioBass.value = x;
        orbUniforms.uDisplacementAmp.value += (0.18 + 0.62 * m - orbUniforms.uDisplacementAmp.value) * 0.08;
        orbUniforms.uNoiseSpeed.value += (0.35 + 0.35 * m - orbUniforms.uNoiseSpeed.value) * 0.08;
        orbUniforms.uFresnelPower.value += (2.5 - 0.3 * m - orbUniforms.uFresnelPower.value) * 0.08;
        shellMaterial.uniforms.uOpacity.value += ((0.1 + 0.25 * m) * state.brightness - shellMaterial.uniforms.uOpacity.value) * 0.08;

        bgUniforms.uOrbGlow.value += ((0.35 + m + 0.4 * x) * state.brightness - bgUniforms.uOrbGlow.value) * 0.08;
        bgUniforms.uVoiceBright.value += (m * state.brightness - bgUniforms.uVoiceBright.value) * 0.08;
        bgUniforms.uNebulaBright.value += ((0.7 + 0.45 * m) * state.brightness - bgUniforms.uNebulaBright.value) * 0.08;

        edgeMat.opacity += ((0.15 + 0.55 * m) * state.brightness - edgeMat.opacity) * 0.08;
        nodeMat.opacity += ((0.7 + 0.35 * m) * state.brightness - nodeMat.opacity) * 0.08;
        nodeMat.size += (2.8 + 3.5 * m + 2 * x - nodeMat.size) * 0.08;
        dustMat.opacity += ((0.22 + 0.35 * m) * state.brightness - dustMat.opacity) * 0.08;

        const constScale = constellationGroup.scale.x + (1 + 0.08 * m + 0.12 * x - constellationGroup.scale.x) * 0.06;
        constellationGroup.scale.set(constScale, constScale, constScale);

        constellationGroup.rotation.y += 0.0006 + 0.004 * m;
        constellationGroup.rotation.x = 0.08 * Math.sin(0.05 * time) + m * Math.sin(1.5 * time) * 0.06;

        orbMesh.rotation.y += (1 / 60) * 0.15;
        orbMesh.rotation.x += (1 / 60) * 0.045;
        shellMesh.rotation.copy(orbMesh.rotation);

        // Dinâmica do Feixe de Plasma Laser 3D (Colapso e Disparo para o Topo)
        if (state.transitioningToOrb) {
            state.vortexProgress += (1.0 - state.vortexProgress) * 0.16;
            const p = state.vortexProgress;

            // Fase 1: Comprime lateralmente em uma lâmina/feixe estreito
            const beamScaleX = Math.max(0.005, 1.0 - p * 1.5);
            // Fase 2: Puxa o feixe em alta velocidade para o topo
            const beamScaleY = p < 0.35 ? 1.05 : Math.max(0.01, 1.0 - (p - 0.35) * 1.5);
            
            orbMesh.scale.set(beamScaleX, beamScaleY, beamScaleX);
            shellMesh.scale.set(beamScaleX * 1.4, beamScaleY * 1.4, beamScaleX * 1.4);

            if (p > 0.25) {
                orbMesh.position.y += (4.2 - orbMesh.position.y) * 0.22;
                constellationGroup.position.y += (4.2 - constellationGroup.position.y) * 0.22;
            }

            orbMesh.rotation.y += 0.45;
            constellationGroup.scale.set(beamScaleX, beamScaleY, beamScaleX);
        }

        const camX = 2 * Math.sin(0.007 * time);
        const camY = 1.5 * Math.cos(0.005 * time);
        constellationCamera.position.x = camX + m * Math.sin(8 * time) * 0.3;
        constellationCamera.position.y = camY + m * Math.cos(6.5 * time) * 0.2;
        constellationCamera.position.z += (42 - 3 * m - constellationCamera.position.z) * 0.04;

        renderer.autoClear = true;
        renderer.render(bgScene, bgCamera);

        renderer.autoClear = false;
        renderer.render(constellationScene, constellationCamera);
        renderer.render(orbScene, orbCamera);
    }

    requestAnimationFrame(animate);

    window.addEventListener('resize', () => {
        const w = window.innerWidth;
        const h = window.innerHeight;
        renderer.setSize(w, h);
        constellationCamera.aspect = w / h;
        constellationCamera.updateProjectionMatrix();
        orbCamera.aspect = w / h;
        orbCamera.updateProjectionMatrix();
    });
}

// --------------------------------------------------------------------------
// Conexão em Tempo Real com o Jarvis (Server-Sent Events)
// --------------------------------------------------------------------------
function initEventStream() {
    const eventsUrl = urlDosEventos();
    let evtSource = null;

    function connect() {
        try {
            evtSource = new EventSource(eventsUrl);

            evtSource.onopen = () => {
                state.connected = true;
                const statusLabel = document.getElementById('status-label');
                if (statusLabel) statusLabel.textContent = 'Watching 6 systems · Jarvis Live';
            };

            evtSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    handleJarvisEvent(data);
                } catch (e) {}
            };

            evtSource.onerror = () => {
                state.connected = false;
                evtSource.close();
                setTimeout(connect, 2000);
            };
        } catch (e) {
            setTimeout(connect, 2000);
        }
    }

    connect();
}

// --------------------------------------------------------------------------
// Tratamento dos Eventos Recebidos do Jarvis (Cores, Brilho, Layout, Falas)
// --------------------------------------------------------------------------
function handleJarvisEvent(data) {
    if (data.state) {
        setState(data.state);
    }

    // Mudança de Tema Dinâmica
    if (data.theme) {
        setTheme(data.theme);
    }

    // Mudança de Brilho Dinâmica
    if (typeof data.brightness === 'number') {
        setBrightness(data.brightness);
    }

    if (data.userSpeech) {
        typeWriter('speech-text', `"${data.userSpeech}"`);
    }

    if (data.jarvisSpeech) {
        typeWriter('speech-text', `"${data.jarvisSpeech}"`);
    }

    if (data.windowTitle) {
        const targetEl = document.getElementById('active-target-text');
        if (targetEl) targetEl.textContent = data.windowTitle.slice(0, 24).toUpperCase();
    }

    // Acompanhamento de tela ligado/desligado: o usuario precisa saber, sem
    // ter que perguntar, se o Jarvis esta olhando a tela dele agora.
    if (typeof data.watching === 'boolean') {
        document.body.classList.toggle('watching-screen', data.watching);
        const rotulo = document.getElementById('status-label');
        if (rotulo) {
            rotulo.textContent = data.watching
                ? 'Acompanhando sua tela · Jarvis Live'
                : 'Watching 6 systems · Jarvis Live';
        }
    }

    if (data.action === 'transition_to_orb') {
        triggerVortexTransitionToOrb();
    }

    if (data.action === 'transition_to_edges') {
        triggerDissolutionToEdges();
    }
}

function triggerVortexTransitionToOrb() {
    if (state.transitioningToOrb) return;
    state.transitioningToOrb = true;
    document.body.classList.add('beaming-to-orb');
    playSfx('warp');
}

function triggerDissolutionToEdges() {
    document.body.classList.add('dissolving-to-edges');
    playSfx('warp');
}

// Ao abrir a interface, executa o desdobramento holográfico a partir do feixe e garante tela cheia
document.addEventListener('DOMContentLoaded', () => {
    try {
        window.moveTo(0, 0);
        window.resizeTo(window.screen.availWidth, window.screen.availHeight);
    } catch (e) {}

    document.body.classList.add('expanding-from-beam');
    setTimeout(() => {
        document.body.classList.remove('expanding-from-beam');
    }, 750);
});
