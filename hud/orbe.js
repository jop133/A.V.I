// O token da sessao chega pela query string da URL (ver hud_app.py). Sem ele
// o servidor devolve 403 -- e o que impede um site qualquer aberto no
// navegador de abrir este mesmo EventSource e ler o que o usuario fala.
function urlDosEventos() {
    const token = new URLSearchParams(location.search).get('token') || '';
    return 'http://127.0.0.1:8765/events?token=' + encodeURIComponent(token);
}

/**
 * J.A.R.V.I.S. DESKTOP CORE ORB - 100% TRANSPARENTE E SEM MOLDURAS
 * Renderiza exclusivamente o cérebro 3D com reação dinâmica ao som em tempo real
 */

const THEMES = {
    'ciano': {
        name: 'Ciano Trillion',
        orb: new THREE.Color(0.18, 0.83, 0.66),
        secondary: new THREE.Color(0.12, 0.75, 0.88),
    },
    'azul': {
        name: 'Azul Jarvis',
        orb: new THREE.Color(0.0, 0.94, 1.0),
        secondary: new THREE.Color(0.0, 0.45, 1.0),
    },
    'vermelho': {
        name: 'Vermelho Stark',
        orb: new THREE.Color(0.95, 0.22, 0.22),
        secondary: new THREE.Color(0.96, 0.55, 0.1),
    },
    'verde': {
        name: 'Verde Matrix',
        orb: new THREE.Color(0.06, 0.92, 0.48),
        secondary: new THREE.Color(0.1, 0.95, 0.3),
    },
    'roxo': {
        name: 'Roxo Cyberpunk',
        orb: new THREE.Color(0.68, 0.35, 0.98),
        secondary: new THREE.Color(0.92, 0.28, 0.65),
    },
    'dourado': {
        name: 'Dourado Solar',
        orb: new THREE.Color(0.98, 0.75, 0.14),
        secondary: new THREE.Color(0.96, 0.48, 0.08),
    },
    'branco': {
        name: 'Gelo Prateado',
        orb: new THREE.Color(0.95, 0.98, 1.0),
        secondary: new THREE.Color(0.55, 0.78, 0.98),
    },
    'rosa': {
        name: 'Rosa Neon',
        orb: new THREE.Color(0.95, 0.25, 0.55),
        secondary: new THREE.Color(0.85, 0.2, 0.8),
    }
};

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
};

window.addEventListener('DOMContentLoaded', () => {
    initDesktopOrb();
    initEventStream();
});

function setTheme(themeId) {
    const theme = THEMES[themeId] || THEMES['ciano'];
    state.theme = themeId;
    state.targetOrbColor = theme.orb.clone();
    state.targetSecondaryColor = theme.secondary.clone();
}

function setBrightness(level) {
    state.targetBrightness = Math.max(0.25, Math.min(2.0, level));
}

function setState(newState) {
    if (state.current === newState) return;
    state.current = newState;

    switch (newState) {
        case 'listening':
            state.audioTarget = 0.95;
            state.audioBass = 0.85;
            break;
        case 'thinking':
            state.audioTarget = 0.5;
            state.audioBass = 0.4;
            break;
        case 'speaking':
            state.audioTarget = 1.0;
            state.audioBass = 0.95;
            break;
        case 'web':
            state.audioTarget = 0.7;
            state.audioBass = 0.55;
            break;
        case 'idle':
        default:
            state.audioTarget = 0.1;
            state.audioBass = 0.08;
            break;
    }
}

function initDesktopOrb() {
    const container = document.getElementById('canvas-container');
    if (!container || typeof THREE === 'undefined') return;

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
            vec3 finalColor = baseColor * (0.15 + fresnel * 0.85 + dispTint * 0.25);
            float finalAlpha = uOpacity * (0.25 + fresnel * 0.75);
            gl_FragColor = vec4(finalColor, finalAlpha);
        }
    `;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setClearColor(0x010101, 1.0); // Chave de transparência do Windows
    container.appendChild(renderer.domElement);

    const orbScene = new THREE.Scene();
    const orbCamera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 100);
    orbCamera.position.set(0, 0, 3.8);

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
        uOpacity: { value: 0.95 },
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

    // Casca de Brilho Holográfico Externo
    const shellGeometry = new THREE.IcosahedronGeometry(1.25, 12);
    const shellMaterial = new THREE.ShaderMaterial({
        uniforms: {
            uColor: { value: state.currentOrbColor },
            uOpacity: { value: 0.18 }
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
                float fresnel = pow(1.0 - abs(dot(viewDir, vNormal)), 2.2);
                gl_FragColor = vec4(uColor, uOpacity * fresnel * 0.8);
            }
        `,
        transparent: true,
        depthWrite: false,
        side: THREE.BackSide,
        blending: THREE.AdditiveBlending
    });

    const shellMesh = new THREE.Mesh(shellGeometry, shellMaterial);
    orbScene.add(shellMesh);

    let startTime = performance.now();
    let smoothedLevel = 0;
    let smoothedBass = 0;

    function animate(now) {
        requestAnimationFrame(animate);

        const time = (now - startTime) / 1000;
        orbUniforms.uTime.value = time;
        orbUniforms.uBreathing.value = 0.5 + 0.5 * Math.sin(0.8 * time);

        state.currentOrbColor.lerp(state.targetOrbColor, 0.08);
        state.currentSecondaryColor.lerp(state.targetSecondaryColor, 0.08);
        state.brightness += (state.targetBrightness - state.brightness) * 0.08;

        orbUniforms.uColor.value.copy(state.currentOrbColor);
        orbUniforms.uColorSecondary.value.copy(state.currentSecondaryColor);
        shellMaterial.uniforms.uColor.value.copy(state.currentOrbColor);

        state.audioLevel += (state.audioTarget - state.audioLevel) * 0.15;
        smoothedLevel += (state.audioLevel - smoothedLevel) * (state.audioLevel > smoothedLevel ? 0.45 : 0.08);
        smoothedBass += (state.audioBass - smoothedBass) * (state.audioBass > smoothedBass ? 0.45 : 0.08);

        const m = smoothedLevel;
        const x = smoothedBass;

        orbUniforms.uAudioLevel.value = m;
        orbUniforms.uAudioBass.value = x;
        orbUniforms.uDisplacementAmp.value += (0.18 + 0.62 * m - orbUniforms.uDisplacementAmp.value) * 0.08;
        orbUniforms.uNoiseSpeed.value += (0.35 + 0.35 * m - orbUniforms.uNoiseSpeed.value) * 0.08;
        shellMaterial.uniforms.uOpacity.value += ((0.18 + 0.35 * m) * state.brightness - shellMaterial.uniforms.uOpacity.value) * 0.08;

        orbMesh.rotation.y += (1 / 60) * 0.18;
        orbMesh.rotation.x += (1 / 60) * 0.05;
        shellMesh.rotation.copy(orbMesh.rotation);

        renderer.render(orbScene, orbCamera);
    }

    requestAnimationFrame(animate);

    window.addEventListener('resize', () => {
        const w = window.innerWidth;
        const h = window.innerHeight;
        renderer.setSize(w, h);
        orbCamera.aspect = w / h;
        orbCamera.updateProjectionMatrix();
    });
}

function initEventStream() {
    const eventsUrl = urlDosEventos();
    let evtSource = null;

    function connect() {
        try {
            evtSource = new EventSource(eventsUrl);

            evtSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.state) setState(data.state);
                    if (data.theme) setTheme(data.theme);
                    if (typeof data.brightness === 'number') setBrightness(data.brightness);
                } catch (e) {}
            };

            evtSource.onerror = () => {
                evtSource.close();
                setTimeout(connect, 2000);
            };
        } catch (e) {
            setTimeout(connect, 2000);
        }
    }

    connect();
}
