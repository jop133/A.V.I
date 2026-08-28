"""Leitura de tela SEM modelo de visao.

A ideia central deste prototipo: para saber o que esta na tela, um modelo de
visao e a ferramenta errada numa GPU modesta. O Windows ja entrega o conteudo
em TEXTO EXATO pela arvore de acessibilidade (UI Automation) -- de graca, em
milissegundos, sem erro de OCR e sem limite de resolucao.

O dump cru e ruidoso (medido: 210 linhas, ~1.720 tokens, cheio de "Minimizar"
e "Fechar"). Este modulo filtra isso para o que de fato interessa.
"""

import ctypes
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


def e_o_proprio_console() -> bool:
    """A janela em foco e o console onde o Jarvis esta rodando?

    Ao ser iniciado pelo .bat, o console dele fica em primeiro plano. Ler esse
    console como "a tela do usuario" enche o contexto com as proprias mensagens
    do Jarvis, e o modelo passa a comentar o proprio log.
    """
    try:
        console = ctypes.windll.kernel32.GetConsoleWindow()
        frente = ctypes.windll.user32.GetForegroundWindow()
        return bool(console) and console == frente
    except Exception:
        return False


def e_a_propria_interface() -> bool:
    """A janela em foco e uma das interfaces do proprio Jarvis?

    Mesmo problema do console, com consequencia pior: a HUD mostra na legenda
    a ULTIMA FALA dele. Lendo isso como tela do usuario, o modelo ve escrito
    "Modo Orbe ativado, senhor" e conclui que a acao ja foi feita -- entao
    responde "ja esta ativado" em vez de CHAMAR a ferramenta.

    Medido: com a HUD em foco, o pedido de trocar de modo virava narracao em
    8 de 10 tentativas; com qualquer outra janela, 10 de 10 executavam.

    E acontece justamente na hora errada: depois de trocar de modo, a propria
    interface e trazida para frente (SetForegroundWindow), entao o comando
    seguinte cai exatamente neste caso.
    """
    try:
        j = auto.GetForegroundControl()
        titulo = (j.Name or "")
    except Exception:
        return False
    return any(t in titulo for t in TITULOS_PROPRIOS)


def janela_ativa():
    """Titulo e classe da janela em foco. Custa menos de 1 ms.

    GetForegroundControl ja devolve a janela; subir na arvore a partir dela
    chega na AREA DE TRABALHO, nao no que o usuario esta usando.
    """
    try:
        j = auto.GetForegroundControl()
        return {"titulo": j.Name or "", "classe": j.ClassName or ""}
    except Exception:
        return {"titulo": "", "classe": ""}


def sob_o_cursor():
    """O elemento EXATO sob o mouse, com o pai para dar contexto.

    E o dado que o modelo de visao errava: medido, ele acertava a posicao do
    cursor em apenas 2 de 5 tentativas. Aqui e exato por construcao.
    """
    try:
        x, y = auto.GetCursorPos()
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
    """Conteudo textual da janela em foco, filtrado e ORDENADO por densidade.

    O corte agressivo aqui e proposital. Cada token novo enviado ao modelo custa
    tempo de leitura (prefill), e medimos que na RX 6600 isso sai caro:
    218 tokens -> 0.48s, mas 1051 tokens -> 4.71s. O prompt de sistema e o
    historico ficam em cache e nao custam nada; o que pesa e justamente este
    bloco, que muda a cada turno.

    Rotulos de uma palavra ("Novo", "Code", "Pro") ocupam token e quase nao
    informam. Frases longas informam muito mais pelo mesmo preco. Entao
    ordenamos por quantidade de palavras e ficamos com as melhores.

    Apps Electron/Chromium (VS Code, Discord, navegadores) so expoem a arvore
    depois de serem consultados uma vez -- por isso a primeira leitura vem
    pobre e a seguinte vem completa.
    """
    linhas, vistos = [], set()
    try:
        janela = auto.GetForegroundControl()
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

    # Prioriza densidade: mais palavras = mais informacao pelo mesmo custo.
    # A ordem original e preservada dentro do que sobrou, para o texto continuar
    # fazendo sentido de cima para baixo.
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

    if e_o_proprio_console() or e_a_propria_interface():
        # Nada util aqui, e ainda confunde o modelo. Melhor dizer so isso.
        return ("[TELA] O usuario esta com a janela do proprio Jarvis em foco; "
                "nao ha nada relevante para ver."), (time.perf_counter() - t0) * 1000

    j = janela_ativa()
    cursor = sob_o_cursor()
    linhas = texto_da_janela(limite_caracteres)
    ms = (time.perf_counter() - t0) * 1000

    partes = ["[TELA] Janela ativa: %s" % (j["titulo"] or "?")]
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
