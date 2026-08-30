"""Leitura de tela SEM modelo de visao.

A ideia central deste prototipo: para saber o que esta na tela, um modelo de
visao e a ferramenta errada numa GPU modesta. O Windows ja entrega o conteudo
em TEXTO EXATO pela arvore de acessibilidade (UI Automation) -- de graca, em
milissegundos, sem erro de OCR e sem limite de resolucao.

O dump cru e ruidoso (medido: 210 linhas, ~1.720 tokens, cheio de "Minimizar"
e "Fechar"). Este modulo filtra isso para o que de fato interessa.
"""

import ctypes
import ctypes.wintypes
import time

import uiautomation as auto

# Controles que carregam CONTEUDO. O resto e moldura de janela.
TIPOS_UTEIS = {
    "TextControl", "EditControl", "DocumentControl", "ListItemControl",
    "TreeItemControl", "TabItemControl", "HyperlinkControl", "ComboBoxControl",
    "CheckBoxControl", "RadioButtonControl", "DataItemControl",
}

# Rotulos de moldura que aparecem em toda janela e nao dizem nada.
RUIDO = {
    "minimizar", "maximizar", "fechar", "restaurar", "menu", "voltar",
    "encaminhar", "avancar", "procurar", "pesquisar", "barra lateral",
    "ocultar barra lateral", "redimensionar barra lateral", "mais",
    "aplicativo", "system", "abrir", "novo", "recolher", "expandir",
}


def _limpar(texto):
    if not texto:
        return None
    t = " ".join(texto.split())
    if len(t) < 3 or t.lower() in RUIDO:
        return None
    return t


# Titulos das janelas do proprio Jarvis. Ler qualquer uma delas como "a tela
# do usuario" e se olhar no espelho.
TITULOS_PROPRIOS = (
    "J.A.R.V.I.S",            # HUD completa, no navegador
    "JARVIS_NATIVE_ORB",      # orbe
    "JARVIS_AMBIENT_EDGES",   # bordas
    "trillion // jarvis",
)

_DWMWA_CLOAKED = 14
_GW_HWNDNEXT = 2
_GA_ROOT = 2


def _titulo_da_janela(hwnd):
    try:
        n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
    except Exception:
        return ""


def _e_encoberta(hwnd):
    """Janela 'visivel' para o Windows mas que ninguem esta vendo.

    Aplicativos UWP deixam janelas encobertas (cloaked) na lista do
    EnumWindows: Configuracoes, Reprodutor Multimidia e afins aparecem mesmo
    fechados. Sem este filtro, a "janela atras da HUD" seria uma delas.
    """
    try:
        valor = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            ctypes.c_void_p(hwnd), _DWMWA_CLOAKED,
            ctypes.byref(valor), ctypes.sizeof(valor))
        return valor.value != 0
    except Exception:
        return False


def _e_nossa(hwnd):
    """Esta janela e do proprio Jarvis (interface ou console)?"""
    try:
        if hwnd == ctypes.windll.kernel32.GetConsoleWindow():
            return True
    except Exception:
        pass
    titulo = _titulo_da_janela(hwnd)
    return any(t in titulo for t in TITULOS_PROPRIOS)


def e_o_proprio_console() -> bool:
    """A janela em foco e o console onde o Jarvis esta rodando?"""
    try:
        console = ctypes.windll.kernel32.GetConsoleWindow()
        frente = ctypes.windll.user32.GetForegroundWindow()
        return bool(console) and console == frente
    except Exception:
        return False


def e_a_propria_interface() -> bool:
    """A janela em foco e uma das interfaces do proprio Jarvis?"""
    try:
        return _e_nossa(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        return False


def hwnd_do_usuario():
    """A janela que o USUARIO esta usando. Zero se nao houver nenhuma.

    Normalmente e a janela em foco. Mas quando o proprio Jarvis esta na
    frente -- o que acontece o tempo todo, porque a HUD e trazida para frente
    depois de cada troca de modo -- ele olha ATRAS dela.

    Antes esse caso simplesmente desistia e devolvia "nao ha nada relevante
    para ver". Isso fazia sentido quando o bloco de tela ia colado em toda
    pergunta, onde era so ruido. Com a ler_tela, o modelo pede a tela DE
    PROPOSITO -- e responder "so vejo a tela do Jarvis" e inutil: o usuario
    esta perguntando pela tela DELE, que continua ali atras.

    O que NAO muda: nunca lemos o conteudo das nossas proprias janelas.
    """
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if hwnd and not _e_nossa(hwnd) and not _e_encoberta(hwnd):
            return hwnd

        # EnumWindows devolve em ordem Z, da frente para tras: a primeira que
        # nao for nossa e a que esta logo atras.
        achado = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def cb(h, _extra):
            if achado:
                return False
            if not user32.IsWindowVisible(h):
                return True
            if len(_titulo_da_janela(h)) < 2:
                return True
            if _e_nossa(h) or _e_encoberta(h):
                return True
            achado.append(h)
            return False

        user32.EnumWindows(WNDENUMPROC(cb), None)
        return achado[0] if achado else 0
    except Exception:
        return 0


def janela_ativa():
    """Titulo e classe da janela do usuario. Custa menos de 1 ms."""
    try:
        hwnd = hwnd_do_usuario()
        if not hwnd:
            return {"titulo": "", "classe": ""}
        j = auto.ControlFromHandle(hwnd)
        return {"titulo": j.Name or "", "classe": j.ClassName or ""}
    except Exception:
        return {"titulo": "", "classe": ""}


def sob_o_cursor():
    """O elemento EXATO sob o mouse, com o pai para dar contexto.

    E o dado que o modelo de visao errava: medido, ele acertava a posicao do
    cursor em apenas 2 de 5 tentativas. Aqui e exato por construcao.

    Devolve None quando o cursor esta sobre uma janela nossa -- reportar o
    proprio orbe como "o que o usuario esta olhando" nao ajuda ninguem.
    """
    try:
        x, y = auto.GetCursorPos()
        raiz = ctypes.windll.user32.GetAncestor(
            ctypes.windll.user32.WindowFromPoint(ctypes.wintypes.POINT(x, y)), _GA_ROOT)
        if raiz and _e_nossa(raiz):
            return None
        el = auto.ControlFromPoint(x, y)
        if el is None:
            return None
        pai = el.GetParentControl()
        return {
            "x": x, "y": y,
            "tipo": el.ControlTypeName.replace("Control", ""),
            "nome": _limpar(el.Name) or "",
            "pai": _limpar(pai.Name) if pai else "",
        }
    except Exception:
        return None


def texto_da_janela(limite_caracteres=600, profundidade=25, max_linhas=10):
    """Conteudo textual da janela do usuario, filtrado e ORDENADO por densidade.

    O corte agressivo aqui e proposital. Cada token novo enviado ao modelo custa
    tempo de leitura (prefill), e medimos que na RX 6600 isso sai caro:
    218 tokens -> 0.48s, mas 1051 tokens -> 4.71s.

    Rotulos de uma palavra ("Novo", "Code", "Pro") ocupam token e quase nao
    informam. Frases longas informam muito mais pelo mesmo preco. Entao
    ordenamos por quantidade de palavras e ficamos com as melhores.

    Apps Electron/Chromium (VS Code, Discord, navegadores) so expoem a arvore
    depois de serem consultados uma vez -- por isso a primeira leitura vem
    pobre e a seguinte vem completa.
    """
    linhas, vistos = [], set()
    try:
        hwnd = hwnd_do_usuario()
        if not hwnd:
            return []
        janela = auto.ControlFromHandle(hwnd)
        vistos_total = 0
        for el, _ in auto.WalkControl(janela, includeTop=True, maxDepth=profundidade):
            vistos_total += 1
            if vistos_total > 1500:   # teto de seguranca contra arvores enormes
                break
            if el.ControlTypeName not in TIPOS_UTEIS:
                continue
            t = _limpar(el.Name)
            if not t or t in vistos:
                continue
            vistos.add(t)
            linhas.append(t)
    except Exception:
        pass

    ranqueadas = sorted(linhas, key=lambda t: -len(t.split()))[:max_linhas]
    escolhidas, total = [], 0
    for t in linhas:
        if t not in ranqueadas:
            continue
        if total + len(t) > limite_caracteres:
            break
        escolhidas.append(t)
        total += len(t)
    return escolhidas


def contexto(limite_caracteres=600):
    """Bloco de contexto pronto para entrar no prompt do modelo."""
    t0 = time.perf_counter()

    j = janela_ativa()
    if not j["titulo"]:
        return ("[TELA] Nao consegui identificar nenhuma janela do usuario neste "
                "momento."), (time.perf_counter() - t0) * 1000

    cursor = sob_o_cursor()
    linhas = texto_da_janela(limite_caracteres)
    ms = (time.perf_counter() - t0) * 1000

    partes = ["[TELA] Janela ativa: %s" % j["titulo"]]
    if cursor:
        alvo = cursor["nome"] or cursor["pai"] or cursor["tipo"]
        partes.append("[CURSOR] sobre %s %r em (%d, %d)"
                      % (cursor["tipo"], alvo, cursor["x"], cursor["y"]))
    if linhas:
        partes.append("[CONTEUDO VISIVEL]\n" + "\n".join("- %s" % l for l in linhas))

    return "\n".join(partes), ms


if __name__ == "__main__":
    print("Aquecendo a arvore de acessibilidade...")
    contexto()
    time.sleep(2.0)

    texto, ms = contexto()
    print()
    print("=" * 70)
    print(texto[:1800])
    print("=" * 70)
    print("  tempo: %.0f ms | %d caracteres | ~%d tokens"
          % (ms, len(texto), len(texto) // 4))
