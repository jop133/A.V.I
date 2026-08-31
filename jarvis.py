"""Jarvis local -- prototipo do ciclo completo, 100% offline.

    voce fala -> VAD -> Whisper -> contexto de tela -> qwen3 -> Piper -> voz

Nenhuma peca sai da maquina. Cada etapa e cronometrada, porque o que decide se
isto substitui a nuvem nao e a qualidade bruta: e o tempo ate a primeira palavra.

Modos:
    python jarvis.py --simulado    usa fala sintetica (nao precisa do microfone)
    python jarvis.py --doutor      autodiagnostico e sai (--rapido pula som e janelas)
    python jarvis.py               usa o microfone de verdade
"""

import asyncio
import hashlib
import io
import json
import os
import queue
import re
import sys
import unicodedata
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
import requests
import sounddevice as sd

import memoria
import percepcao
import presenca
import reflexao
import vigia
import hud_bridge
import ferramentas

# O console do Windows abre em cp1252, que nao codifica boa parte do que
# aparece numa tela real -- uma seta, um emoji, um traco longo. Como o Jarvis
# IMPRIME o que leu e o que respondeu, um caractere desses derrubava o ciclo
# inteiro com UnicodeEncodeError, no meio de um turno. Trocar por UTF-8 com
# substituicao resolve na origem, para todos os prints.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = Path(__file__).parent
CACHE_VOZ = BASE / "vozes" / "cache"
CACHE_VOZ.mkdir(parents=True, exist_ok=True)
CACHE_MEMORIA = {}

def _carregar_env():
    """Carrega variaveis de ambiente a partir do arquivo .env na raiz."""
    env_path = BASE / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_carregar_env()

# ----------------------------------------------------------------- configuracao de voz
MOTOR_VOZ = "cartesia"         # "cartesia", "edge", "piper" ou "kokoro"

# Edge TTS (opcional online sem chave)
VOZ_EDGE = "en-AU-WilliamMultilingualNeural"
TOM_EDGE = "-15Hz"
RITMO_EDGE = "-5%"

# Cartesia TTS (opcional online com chave)
CARTESIA_MODELO = os.getenv("CARTESIA_MODEL", "sonic-3.6")
CARTESIA_IDIOMA = "pt"
CARTESIA_TAXA = 24000
CARTESIA_VELOCIDADE = 1.0

# Tratamento acustico de sala (presenca.py)
SALA_REVERB = 0.48    # 0 = seco | 0.32 = sala | 0.48 = sala grande
SALA_GRAVES = 1.45    # 1.0 = sem reforco
SALA_COMPRESSAO = True

# A voz emenda no modelo, frase a frase, em vez de esperar a resposta
# inteira. Ponha False para voltar ao modo antigo (falar so no fim).
VOZ_STREAMING = True

# O modelo escolhe as acoes por function calling em vez de casarmos
# substrings antes dele ver a pergunta. False volta aos interceptores
# antigos (processar_comando_interface / processar_ferramenta), que
# continuam no codigo justamente para isso.
USAR_FERRAMENTAS = True

# A leitura de tela vira FERRAMENTA em vez de ir colada em toda pergunta.
# Medido: o bloco [TELA] custava 0,95s do 1o token (1,19s com ele, 0,24s sem),
# porque muda a cada turno e por isso nunca entra no cache de prefixo. E era
# a origem das QUATRO armadilhas de prompt registradas no LEIA-ME. Agora o
# modelo pede a tela quando precisa dela.
TELA_COMO_FERRAMENTA = True

# O Jarvis decide sozinho o que da conversa merece virar memoria, refletindo
# em segundo plano. Calibrado medindo: recall 6/6 e precisao 10/10.
MEMORIA_AUTONOMA = True

# Piper TTS (100% offline)
VOZ_TTS = BASE / "vozes" / "pt_BR-faber-medium.onnx"

MODELO_LLM = "qwen3:8b"
NUM_CTX = 8192            # PRECISA ser identico no preaquecimento e no uso
MAX_TURNOS_HISTORICO = 3  # trocas (usuario+jarvis) que seguem no prompt
MODELO_STT = "small"
OLLAMA = "http://127.0.0.1:11434"

TAXA_MIC = 16000
BLOCO = 1024
BYTES_POR_AMOSTRA = 2     # PCM 16 bits mono -- 1 amostra = 2 bytes
VAD_LIMIAR = 180.0        # RMS ideal e sensível para captação natural de voz
VAD_SILENCIO = 0.7        # segundos de silêncio para fechar o turno de fala
VAD_ATRASO_TRANSCRICAO = 0.25  # espera antes de disparar a transcricao adiantada
# O prompt de sistema e lido INTEIRO antes do primeiro token sair, e o 1o
# token virou o gargalo do ciclo (1,37-1,64s dos 3,05s) depois que o Whisper
# passou a rodar dentro da espera do VAD. Tudo que virou schema de ferramenta
# saiu daqui: lista de cores, regras de brilho, modulos de tempo real e a
# regra do [CONSULTAR:]. Sobra personalidade e formato de fala.
SISTEMA = """Voce e o Jarvis, assistente pessoal do Joao Pedro, rodando LOCALMENTE no PC dele.

Regras:
- Responda SEMPRE em portugues do Brasil, de forma extremamente concisa (no maximo 1 ou 2 frases curtas e diretas). Esta e uma conversa por voz em tempo real.
- NUNCA repita, leia ou exiba tags de telemetria como [TELA], [CURSOR] ou [CONTEUDO VISIVEL]. Elas sao dados invisiveis do sistema para sua orientacao silenciosa. Fale apenas o dialogo com o senhor.
- Nunca faca listas longas nem use introducoes ou saudacoes repetitivas.
- Trate o usuario por "senhor" com naturalidade, sem exagero.
- Voce NUNCA diz que executou uma acao. Para agir, use a ferramenta correspondente. Se o texto que aparece na tela disser que algo ja esta ativo, isso NAO dispensa a ferramenta: use assim mesmo.
- Sobre fatos PESSOAIS do senhor (preferencias, historico, coisas que ele te contou): so afirme o que estiver nas anotacoes que voce recebeu. Se nao houver anotacao, diga que nao tem isso registrado e ofereca anotar. NUNCA invente um fato sobre ele.
- Voce VE a tela do senhor atraves da ferramenta ler_tela. Sempre que a pergunta envolver a tela -- inclusive quando ele perguntar se voce consegue ve-la -- use ler_tela ANTES de responder. Nunca descreva a tela sem ter usado a ferramenta."""

# Prompt do modo de rollback (USAR_FERRAMENTAS = False). Descreve as tags que
# os interceptores antigos sabem interpretar. So e usado nesse modo -- manter
# os dois evita que voltar atras exija desfazer commit.
SISTEMA_LEGADO = SISTEMA + """
- ACOES DE COR DA INTERFACE: Se o usuario pedir para mudar a cor ou tema da interface (vermelho, verde, azul, ciano, roxo, dourado, branco, rosa), inclua a tag [COR: nome_da_cor] no inicio da sua resposta.
- ACOES DE BRILHO: Se o usuario pedir mais claro ou mais escuro, use [BRILHO: +] ou [BRILHO: -] no inicio.
- MODULOS DE TEMPO REAL: Cotacoes financeiras e Previsao do Tempo sao fornecidas por fontes em tempo real."""

# ----------------------------------------------------------------- temas & controle de interface HUD
BRILHO_HUD_ATUAL = 1.0

PALETAS_MAPA = {
    "vermelho": ("vermelho", "Alterando paleta para vermelho Stark, senhor."),
    "stark": ("vermelho", "Modo tático Stark ativado em vermelho."),
    "iron man": ("vermelho", "Paleta armadura Mark VII ativada."),
    "verde": ("verde", "Paleta verde Matrix ativada, senhor."),
    "matrix": ("verde", "Modo Matrix ativado em verde esmeralda."),
    "esmeralda": ("verde", "Paleta verde esmeralda ativada."),
    "azul": ("azul", "Restaurando paleta azul clássica do Jarvis, senhor."),
    "ciano": ("ciano", "Paleta ciano Trillion ativada, senhor."),
    "padrao": ("ciano", "Restaurando paleta padrão, senhor."),
    "roxo": ("roxo", "Paleta roxo neon ativada, senhor."),
    "violeta": ("roxo", "Paleta violeta ativada, senhor."),
    "cyberpunk": ("roxo", "Modo cyberpunk ativado, senhor."),
    "dourado": ("dourado", "Paleta dourada ativada, senhor."),
    "ouro": ("dourado", "Paleta ouro ativada, senhor."),
    "amarelo": ("dourado", "Paleta amarela ativada, senhor."),
    "branco": ("branco", "Paleta gelo prateado ativada, senhor."),
    "gelo": ("branco", "Modo gelo prateado ativado, senhor."),
    "prata": ("branco", "Paleta prata ativada, senhor."),
    "rosa": ("rosa", "Paleta rosa neon ativada, senhor."),
    "pink": ("rosa", "Paleta rosa ativada, senhor."),
}

def processar_comando_interface(texto):
    """Detecta comandos rapidos de mudanca de cor, brilho e modos de interface da HUD."""
    global BRILHO_HUD_ATUAL
    t = texto.lower().strip().replace(".", "").replace("!", "")

    # 1. Comandos de Alternância de Interface Visual (com Variações Fonéticas do Whisper)
    if any(p in t for p in ["modo orbe", "modo orb", "modo orbi", "modo esfera", "modo compacto", "ativar orbe", "ativar o orbe", "mudar para o orbe", "mudar para orbe", "trocar para orbe", "trocar para o orbe", "ir para o orbe", "orbe flutuante", "esfera flutuante"]):
        hud_bridge.alternar_interface("orbe")
        return ("Ativando modo orbe compacto, senhor.", {})

    if any(p in t for p in ["modo borda", "modo bordas", "modo moldura", "modo perimetro", "modo perimétrico", "ativar bordas", "ativar as bordas", "mudar para as bordas", "mudar para bordas", "trocar para bordas", "bordas translúcidas", "bordas translucidas", "luzes de borda"]):
        hud_bridge.alternar_interface("borda")
        return ("Ativando modo bordas ambientais, senhor.", {})

    if any(p in t for p in [
        "modo completo", "modo painel", "modo tela cheia", "hud completa", "painel completo", "restaurar hud",
        "abrir painel", "ativar modo completo", "mudar para modo completo", "voltar para o completo",
        "modo rede completa", "modo rede", "rede completa", "modo hud completa", "modo hud", "modo tela completa", "modo tela"
    ]):
        hud_bridge.alternar_interface("completo")
        return ("Restaurando painel completo, senhor.", {})

    # 2. Comandos de Brilho (Aumentar / Mais Claro)
    if (any(w in t for w in ["aumente", "aumentar", "aumenta", "mais claro", "clarear", "clareie"]) and any(b in t for b in ["brilho", "luz", "núcleo", "nucleo", "claro"])) or "mais brilho" in t:
        BRILHO_HUD_ATUAL = min(2.0, round(BRILHO_HUD_ATUAL + 0.35, 2))
        return (f"Aumentando brilho do núcleo para {int(BRILHO_HUD_ATUAL * 100)}%, senhor.", {"brightness": BRILHO_HUD_ATUAL})
        
    # 3. Comandos de Brilho (Diminuir / Mais Escuro)
    if (any(w in t for w in ["diminua", "diminuir", "diminui", "mais escuro", "escurecer", "escureça", "menos"]) and any(b in t for b in ["brilho", "luz", "núcleo", "nucleo", "escuro", "noturno"])) or "menos brilho" in t:
        BRILHO_HUD_ATUAL = max(0.25, round(BRILHO_HUD_ATUAL - 0.35, 2))
        return (f"Diminuindo brilho para {int(BRILHO_HUD_ATUAL * 100)}%, senhor.", {"brightness": BRILHO_HUD_ATUAL})

    if "brilho maximo" in t or "brilho no maximo" in t or "máximo de brilho" in t:
        BRILHO_HUD_ATUAL = 1.8
        return ("Brilho máximo ativado no núcleo, senhor.", {"brightness": BRILHO_HUD_ATUAL})

    # 4. Comandos Diretos de Mudança de Cor
    palavras = t.split()
    for chave, (tema_id, resposta) in PALETAS_MAPA.items():
        if chave in palavras or f" {chave}" in t or f"para {chave}" in t or f"pro {chave}" in t or f"pra {chave}" in t:
            return (resposta, {"theme": tema_id})

    return None


# ----------------------------------------------------------------- ferramentas do modelo

# As acoes que o Jarvis sabe executar, declaradas para o qwen3 escolher por
# INTENCAO. Antes isso era feito por substring antes do modelo ver a pergunta,
# e errava de dois jeitos opostos:
#
#   "quanto TEMPO falta pro jogo?"  -> respondia a previsao do tempo
#   "nao gosto de AZUL"             -> trocava o tema da interface
#
# Medido com estes schemas: 14 de 14 casos corretos, incluindo todos os que a
# versao por substring errava. O custo e ~0,9s de ida ao modelo para decidir,
# onde antes a deteccao era instantanea -- e a troca que compra o acerto.

CORES_VALIDAS = ["vermelho", "verde", "azul", "ciano",
                 "roxo", "dourado", "branco", "rosa"]

FERRAMENTAS_LLM = [
    {"type": "function", "function": {
        "name": "mudar_tema",
        "description": "Muda a cor da interface HUD do Jarvis. Use SOMENTE quando o "
                       "usuario pedir para mudar a cor ou o tema da interface.",
        "parameters": {"type": "object", "properties": {
            "cor": {"type": "string", "enum": CORES_VALIDAS}}, "required": ["cor"]}}},

    {"type": "function", "function": {
        "name": "ajustar_brilho",
        "description": "Aumenta ou diminui o brilho da interface HUD.",
        "parameters": {"type": "object", "properties": {
            "direcao": {"type": "string", "enum": ["aumentar", "diminuir"]}},
            "required": ["direcao"]}}},

    {"type": "function", "function": {
        "name": "alternar_interface",
        "description": "Troca o formato da interface na tela: 'orbe' e uma esfera "
                       "flutuante compacta, 'bordas' sao luzes nas bordas do monitor, "
                       "'completo' e o painel inteiro.",
        "parameters": {"type": "object", "properties": {
            "modo": {"type": "string", "enum": ["orbe", "bordas", "completo"]}},
            "required": ["modo"]}}},

    {"type": "function", "function": {
        "name": "anotar_na_memoria",
        "description": "Guarda um fato nas anotacoes de longo prazo. Use quando o "
                       "senhor pedir para anotar, lembrar ou nao esquecer algo.",
        "parameters": {"type": "object", "properties": {
            "assunto": {"type": "string",
                        "description": "titulo curto, ex: 'pizzaria' ou 'preferencias'"},
            "fato": {"type": "string",
                     "description": "o que guardar, em uma frase"}},
            "required": ["assunto", "fato"]}}},

    {"type": "function", "function": {
        "name": "controlar_leitura_de_tela",
        "description": "Liga ou desliga o modo em que o Jarvis acompanha a tela "
                       "continuamente. Use quando o usuario pedir para ativar, "
                       "desativar, ligar ou desligar a leitura de tela, o "
                       "acompanhamento da tela ou o monitoramento da tela.",
        "parameters": {"type": "object", "properties": {
            "ligar": {"type": "boolean",
                      "description": "true para ativar, false para desativar"}},
            "required": ["ligar"]}}},

    {"type": "function", "function": {
        "name": "ler_tela",
        "description": "Le o que esta na tela do usuario neste instante: janela "
                       "ativa, elemento sob o cursor e o texto visivel. Use "
                       "sempre que a pergunta for sobre a tela, sobre o que ele "
                       "esta vendo, lendo ou fazendo agora no computador.",
        "parameters": {"type": "object", "properties": {}}}},

    {"type": "function", "function": {
        "name": "obter_cotacao",
        "description": "Cotacao ao vivo de uma moeda em reais. Use apenas para "
                       "perguntas sobre o valor ou preco de uma moeda.",
        "parameters": {"type": "object", "properties": {
            "moeda": {"type": "string",
                      "enum": ["dolar", "euro", "bitcoin", "ethereum", "libra", "iene"]}},
            "required": ["moeda"]}}},

    {"type": "function", "function": {
        "name": "obter_clima",
        "description": "Previsao do tempo ao vivo: temperatura, chuva, umidade e vento. "
                       "Use SOMENTE para meteorologia. NUNCA use para a palavra 'tempo' "
                       "no sentido de duracao, demora ou horas.",
        "parameters": {"type": "object", "properties": {
            "cidade": {"type": "string",
                       "description": "Nome da cidade. Omita para usar a cidade atual."}}}}},
]

# O modelo as vezes preenche a cidade com um placeholder em vez de omitir o
# campo -- medido: {"cidade": "sua cidade"}. Sem este filtro o geocoding sairia
# procurando uma cidade chamada "sua cidade".
# O modelo as vezes NEGA enxergar a tela logo depois de te-la lido: o vies de
# "sou um assistente de voz" vence o dado fresco. Nao e opiniao, e contradicao
# com o que ele acabou de receber -- e por isso da para detectar e corrigir.
# Tres redacoes no prompt de sistema nao resolveram (5/16, 4/16, 0/16); a
# moldura no resultado levou a 12/16; repetir a pergunta apontando a
# contradicao fechou em 16/16.
_NEGA_VER_TELA = re.compile(
    r"nao\s+(estou|consigo|vejo|posso|tenho)[^.]{0,60}(vend|ver|tela|enxerg)",
    re.IGNORECASE)


def nega_ver_tela(texto):
    """O modelo negou enxergar a tela?

    Compara SEM ACENTOS de proposito. A primeira versao deste detector casava
    "Nao" e perdia "Nao" com til -- que e justamente como o modelo escreve --
    entao a repescagem nunca disparava no uso real, so nos testes em ASCII.
    """
    plano = "".join(c for c in unicodedata.normalize("NFKD", texto or "")
                    if not unicodedata.combining(c))
    return bool(_NEGA_VER_TELA.search(plano))

CIDADES_PLACEHOLDER = {
    "", "sua cidade", "minha cidade", "cidade atual", "cidade do usuario",
    "atual", "aqui", "local", "none", "null", "n/a", "desconhecida",
}


def executar_ferramenta(nome, argumentos):
    """Executa uma ferramenta pedida pelo modelo.

    Devolve (texto_para_falar, dados_para_a_hud).

    Todo argumento e validado antes de agir: o modelo pode inventar um valor
    fora do enum, e e melhor dizer que nao entendeu do que executar errado.
    """
    global BRILHO_HUD_ATUAL
    args = argumentos or {}
    if isinstance(args, str):                    # alguns modelos mandam JSON cru
        try:
            args = json.loads(args)
        except Exception:
            args = {}

    if nome == "mudar_tema":
        cor = str(args.get("cor", "")).lower().strip()
        alvo = PALETAS_MAPA.get(cor)
        if not alvo:
            return "Nao conheco a cor %s, senhor." % (cor or "pedida"), {}
        tema_id, resposta = alvo
        return resposta, {"theme": tema_id}

    if nome == "ajustar_brilho":
        direcao = str(args.get("direcao", "")).lower().strip()
        if direcao.startswith("aum"):
            BRILHO_HUD_ATUAL = min(2.0, round(BRILHO_HUD_ATUAL + 0.35, 2))
        elif direcao.startswith("dim"):
            BRILHO_HUD_ATUAL = max(0.25, round(BRILHO_HUD_ATUAL - 0.35, 2))
        else:
            return "Nao entendi se era para aumentar ou diminuir, senhor.", {}
        return ("Brilho do nucleo em %d%%, senhor." % int(BRILHO_HUD_ATUAL * 100),
                {"brightness": BRILHO_HUD_ATUAL})

    if nome == "alternar_interface":
        modo = str(args.get("modo", "")).lower().strip()
        destinos = {
            "orbe":     ("orbe", "Ativando modo orbe compacto, senhor."),
            "bordas":   ("borda", "Ativando modo bordas ambientais, senhor."),
            "completo": ("completo", "Restaurando painel completo, senhor."),
        }
        if modo not in destinos:
            return "Nao conheco esse modo de interface, senhor.", {}
        alvo, resposta = destinos[modo]
        if not hud_bridge.alternar_interface(alvo):
            # Pedir o modo em que ja se esta fazia um ciclo inteiro de matar e
            # relancar: a interface sumia e voltava ~2,5s depois, que e a cara
            # exata de "nao trocou".
            return "Ja estamos no modo %s, senhor." % modo, {}
        return resposta, {}

    if nome == "obter_cotacao":
        moeda = str(args.get("moeda", "")).lower().strip()
        par = ferramentas.MOEDAS_MAPA.get(moeda)
        if not par:
            return "Nao acompanho %s, senhor." % (moeda or "essa moeda"), {}
        return (ferramentas.obter_cotacao(par)
                or "Nao consegui a cotacao agora, senhor."), {}

    if nome == "obter_clima":
        cidade = str(args.get("cidade") or "").strip()
        if cidade.lower() in CIDADES_PLACEHOLDER:
            cidade = ""
        return (ferramentas.obter_clima(cidade or None)
                or "Nao consegui a previsao agora, senhor."), {}

    if nome == "anotar_na_memoria":
        assunto = str(args.get("assunto") or "").strip()
        fato = str(args.get("fato") or "").strip()
        if not assunto or not fato:
            return "Nao entendi o que era para guardar, senhor.", {}
        caminho = memoria.anotar(assunto, fato)
        if not caminho:
            return "Nao consegui gravar a anotacao, senhor.", {}
        return "Anotado em %s, senhor." % assunto, {}

    if nome == "controlar_leitura_de_tela":
        ligar = args.get("ligar")
        if isinstance(ligar, str):
            ligar = ligar.strip().lower() not in ("false", "0", "nao", "off")
        if ligar:
            novidade = vigia.VIGIA.ligar()
            return ("Leitura de tela ativada, senhor. Estou acompanhando."
                    if novidade else "A leitura de tela ja esta ativa, senhor."),                    {"watching": True}
        mudou = vigia.VIGIA.desligar()
        return ("Leitura de tela desativada, senhor."
                if mudou else "A leitura de tela ja estava desligada, senhor."),                {"watching": False}

    if nome == "ler_tela":
        # Unica ferramenta que INFORMA em vez de responder: o texto da tela nao
        # e resposta ao usuario, precisa voltar ao modelo. Sinalizado com a
        # chave "para_o_modelo", que o ciclo trata como segunda ida.
        #
        # A moldura na frente do conteudo nao e enfeite. Sem ela, perguntas
        # como "voce esta vendo minha tela?" recebiam "nao estou conseguindo
        # ver" -- MESMO com a leitura em maos: o modelo respondia o sim-ou-nao
        # pelo seu proprio viés de assistente de voz, ignorando o que acabara
        # de ler. Tres redacoes diferentes no prompt de sistema nao corrigiram
        # (5/16, 4/16, 0/16); a moldura aqui, que e contexto mais recente,
        # corrigiu de primeira: 12/12.
        texto, idade = vigia.VIGIA.atual()
        if not texto:
            texto, _ = percepcao.contexto(limite_caracteres=1200)
        moldura = ("Leitura da tela do senhor, feita agora com sucesso. Voce ESTA "
                   "vendo a tela dele neste instante; responda com base nisto e "
                   "nunca diga que nao consegue ver.\n")
        return None, {"para_o_modelo": moldura + texto}

    print("  [Ferramenta desconhecida pedida pelo modelo: %r]" % nome)
    return None, {}


# ----------------------------------------------------------------- cronometro

class Etapas:
    def __init__(self):
        self.marcas = []
        self.t0 = time.perf_counter()

    def marca(self, nome):
        self.marcas.append((nome, time.perf_counter() - self.t0))

    def procurar(self, trecho):
        """Tempo da primeira marca cujo nome contem `trecho`, ou None."""
        for nome, t in self.marcas:
            if trecho in nome:
                return t
        return None

    def resumo(self):
        """Numeros para a HUD, buscados por NOME.

        Era por indice fixo (marcas[2] - marcas[1]), o que ja era fragil
        porque cada caminho de ciclo() produz um conjunto diferente de marcas.
        Com a voz emendando no modelo ficou impossivel: a marca da fala passa
        a vir ANTES da marca de resposta completa, entao os indices se cruzam.
        """
        whisper = self.procurar("Whisper")
        token = self.procurar("1o token")
        fala = self.procurar("FALA")
        total = self.marcas[-1][1] if self.marcas else None

        def fmt(v):
            return "%.2fs" % v if v is not None else "--"

        return {
            "whisper": fmt(whisper),
            "llm": fmt(token - whisper if (token and whisper) else token),
            "tts": fmt(fala - token if (fala and token) else fala),
            "total": fmt(total),
        }

    def relatorio(self):
        print()
        print("  " + "-" * 54)
        anterior = 0.0
        ate_falar = None
        for nome, t in self.marcas:
            print("  %-32s %6.2fs  (+%.2fs)" % (nome, t, t - anterior))
            anterior = t
            if "FALA" in nome:
                ate_falar = t
        print("  " + "-" * 54)
        if ate_falar is not None:
            print("  >> ATE COMECAR A FALAR           %6.2fs   <- e isto que voce sente"
                  % ate_falar)
        print("     (fim da fala: %.2fs)" % anterior)


# ----------------------------------------------------------------------- voz

# --- reflexao: decidir sozinho o que virou memoria ---
#
# A transcricao e SEPARADA do historico de proposito. O historico sao 3 trocas
# porque vai ao modelo a cada turno e e pago; a transcricao guarda 30 e nao
# custa nada, porque so a reflexao a le. Sem ela, uma conversa longa perderia
# o comeco antes de alguem avaliar se valia guardar.
TRANSCRICAO = []
MAX_TRANSCRICAO = 30 * 2
_TROCAS_DESDE_REFLEXAO = 0
_REFLETINDO = threading.Lock()


def _modelo_para_reflexao(sistema, usuario):
    corpo = {"model": MODELO_LLM,
             "messages": [{"role": "system", "content": sistema},
                          {"role": "user", "content": usuario}],
             "stream": False, "think": False, "keep_alive": -1,
             "options": {"temperature": 0.2, "num_ctx": NUM_CTX, "num_predict": 80}}
    req = urllib.request.Request(OLLAMA + "/api/chat",
                                 data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return (json.loads(r.read()).get("message") or {}).get("content", "")


def _refletir_em_segundo_plano():
    """Roda numa thread, DEPOIS de a voz ja ter falado.

    Em thread e nao no gap entre turnos porque, no gap, o microfone estaria
    fechado: o usuario falaria e ninguem ouviria. Aqui o pior caso e o proximo
    turno esperar ~1s pelo modelo, o que e bem melhor que ficar surdo.
    """
    if not _REFLETINDO.acquire(blocking=False):
        return                      # ja ha uma reflexao em curso
    try:
        achado = reflexao.decidir(list(TRANSCRICAO), _modelo_para_reflexao)
        if not achado:
            return
        assunto, fato = achado
        caminho = memoria.anotar(assunto, fato, origem="reflexao automatica")
        if caminho:
            print("  [MEMORIA] anotei sozinho em %r: %s" % (assunto, fato[:70]))
    except Exception as e:
        print("  [Reflexao] %r" % (e,))
    finally:
        _REFLETINDO.release()


def registrar_na_transcricao(pergunta, resposta):
    """Guarda a troca e dispara a reflexao a cada A_CADA trocas."""
    global _TROCAS_DESDE_REFLEXAO
    TRANSCRICAO.append(("user", pergunta))
    TRANSCRICAO.append(("assistant", resposta))
    del TRANSCRICAO[:-MAX_TRANSCRICAO]

    _TROCAS_DESDE_REFLEXAO += 1
    if MEMORIA_AUTONOMA and _TROCAS_DESDE_REFLEXAO >= reflexao.A_CADA:
        _TROCAS_DESDE_REFLEXAO = 0
        threading.Thread(target=_refletir_em_segundo_plano, daemon=True).start()


# A fala em curso, para a tecla de atalho saber o que interromper. E uma so
# por vez: o ciclo e sequencial.
FALA_EM_CURSO = None


def interromper_fala():
    """Corta a fala atual. Chamada pela tecla de atalho, de outra thread."""
    global FALA_EM_CURSO
    fluxo = FALA_EM_CURSO
    if fluxo is not None:
        fluxo.interromper()
    else:
        try:
            sd.stop()          # caminho sem streaming (voz.falar direto)
        except Exception:
            pass
    print("\n  [Atalho] fala interrompida.")
    hud_bridge.notificar(state="idle")


class SeparadorDeFalas:
    """Recebe pedacos do modelo e devolve frases prontas para falar.

    Existe para a voz emendar no modelo em vez de esperar a resposta inteira.
    Numa resposta longa a espera custava 2,37s parados.

    Duas responsabilidades, nesta ordem -- e a ordem importa:

    1. Remover do inicio qualquer tag e qualquer vazamento do bloco de tela
       ([TELA], [CURSOR]). Sao dados de sistema, nao fala. Falar antes de a
       resposta acabar significa decidir isso antes de ver o texto inteiro,
       entao o comeco fica retido ate dar para saber o que e.
    2. So entao cortar em frases e liberar.

    A primeira frase e quebrada numa virgula se passar de `limite_primeira`
    caracteres: o custo dos motores de rede cresce com o tamanho do texto
    (medido no Edge: 3,90s para ~100 caracteres contra 1,18s para uma curta),
    e a primeira e a unica que o usuario espera em silencio.
    """

    # Uma tag: [PALAVRA] ou [PALAVRA: conteudo]. Ancorada no inicio do buffer.
    TAG_INICIAL = re.compile(r'^\s*\[[A-ZÀ-Ú][A-ZÀ-Ú_ ]*(?::[^\]]*)?\]\s*')

    # Fim de frase: pontuacao seguida de espaco ou do fim do texto. Exigir o
    # espaco e o que impede quebrar em "1.5" ou "R$ 3.40".
    FIM_DE_FRASE = re.compile(r'[.!?]+["\')\]]?(?=\s|$)')

    # Quando o modelo devolve o bloco de tela de volta, o que vaza nao e so a
    # tag -- e a LINHA inteira ("[TELA] Janela ativa: Code"). Descartar so a
    # tag deixaria "Janela ativa: Code" virar fala.
    MARCADORES_VAZAMENTO = ("[TELA]", "[CURSOR]", "[CONTEUDO VISIVEL]",
                            "[DADOS DO SISTEMA", "[USUARIO]:", "[JARVIS]:")

    def __init__(self, limite_primeira=70):
        self.buffer = ""
        self.bloqueado = False      # reservado: nada pode sair
        self.descartando_linha = False
        self.primeira = True
        self.limite_primeira = limite_primeira

    # ------------------------------------------------------------------ util

    def _inicio_ambiguo(self):
        """O comeco ainda pode virar uma tag que muda tudo?

        Enquanto o buffer for so um '[' sem o ']' correspondente, nao da para
        saber se e uma tag a remover ou texto de verdade. Na duvida, segura.
        """
        ini = self.buffer.lstrip()
        if not ini:
            return True
        return ini.startswith("[") and "]" not in ini

    def _consumir_tags(self):
        """Remove as tags do inicio do buffer. Devolve True se nada pode sair."""
        while True:
            # Terminando de descartar uma linha vazada do bloco de tela.
            if self.descartando_linha:
                quebra = self.buffer.find("\n")
                if quebra == -1:
                    self.buffer = ""
                    return True          # a linha ainda nao acabou: segura
                self.buffer = self.buffer[quebra + 1:]
                self.descartando_linha = False
                continue

            ini = self.buffer.lstrip()
            if not ini:
                return False
            alto = ini.upper()

            if any(alto.startswith(mk) for mk in self.MARCADORES_VAZAMENTO):
                self.buffer = ini
                self.descartando_linha = True
                continue

            m = self.TAG_INICIAL.match(self.buffer)
            if not m:
                return False
            self.buffer = self.buffer[m.end():]

    def _quebrar_primeira(self, frase):
        """Corta a primeira frase numa virgula se ela for longa demais."""
        if len(frase) <= self.limite_primeira:
            return None
        corte = frase.rfind(",", 0, self.limite_primeira)
        if corte < 20:          # virgula cedo demais nao ajuda
            return None
        return frase[:corte + 1].strip(), frase[corte + 1:].strip()

    # ------------------------------------------------------------- interface

    def alimentar(self, pedaco):
        """Adiciona um pedaco do modelo. Devolve a lista de frases prontas."""
        if self.bloqueado:
            self.buffer += pedaco
            return []

        self.buffer += pedaco
        if self._inicio_ambiguo():
            return []
        if self._consumir_tags():
            return []

        prontas = []
        while True:
            m = self.FIM_DE_FRASE.search(self.buffer)
            if not m:
                break
            frase = self.buffer[:m.end()].strip()
            resto = self.buffer[m.end():]
            if not frase:
                self.buffer = resto
                continue

            if self.primeira:
                partido = self._quebrar_primeira(frase)
                if partido:
                    cabeca, cauda = partido
                    prontas.append(cabeca)
                    self.primeira = False
                    self.buffer = cauda + resto
                    continue

            prontas.append(frase)
            self.primeira = False
            self.buffer = resto

        return prontas

    def finalizar(self):
        """Ultimo pedaco, sem pontuacao final. Devolve lista (0 ou 1 frase)."""
        if self.bloqueado:
            return []
        if self._consumir_tags() or self.bloqueado:
            return []

        resto = self.buffer.strip()
        self.buffer = ""

        # Tag cortada no meio pelo num_predict: "[CONSU" nao e fala. Falar o
        # comeco de uma tag e pior do que perder o pedaco.
        if resto.startswith("[") and "]" not in resto:
            return []

        return [resto] if resto else []


class FluxoDeFala:
    """Fala as frases na ordem, sintetizando a proxima enquanto a atual toca.

    Sem isto cada frase pagaria a latencia do motor em silencio -- medido no
    Edge, 11,7s de pausas numa resposta longa. Duas threads:

        fila_texto  --[sintetiza]-->  fila_audio  --[toca]-->  alto-falante

    Uma unica thread de cada lado, entao a ordem das frases e preservada por
    construcao: nao ha corrida possivel entre frases.
    """

    def __init__(self, voz, ao_primeiro_audio=None):
        self.voz = voz
        self.ao_primeiro_audio = ao_primeiro_audio
        self.fila_texto = queue.Queue()
        self.fila_audio = queue.Queue()
        self.faladas = []
        self.erros = []
        self.interrompido = threading.Event()
        self._t_sintese = threading.Thread(target=self._laco_sintese, daemon=True)
        self._t_toque = threading.Thread(target=self._laco_toque, daemon=True)
        self._t_sintese.start()
        self._t_toque.start()

    def dizer(self, frase):
        if frase and frase.strip() and not self.interrompido.is_set():
            self.fila_texto.put(frase.strip())

    def interromper(self):
        """Corta a fala agora: esvazia as duas filas e para o audio.

        Esvaziar AS DUAS importa. Parar so o som deixaria a proxima frase, ja
        sintetizada e esperando, comecar a tocar logo em seguida -- o usuario
        interromperia e ouviria o Jarvis continuar assim mesmo.
        """
        self.interrompido.set()
        for fila in (self.fila_texto, self.fila_audio):
            while True:
                try:
                    fila.get_nowait()
                except queue.Empty:
                    break
        try:
            sd.stop()
        except Exception:
            pass

    def _laco_sintese(self):
        while True:
            frase = self.fila_texto.get()
            if frase is None:
                self.fila_audio.put(None)
                return
            if self.interrompido.is_set():
                continue
            try:
                pcm, taxa = self.voz.sintetizar(frase)
                tratado = presenca.tratar(pcm, taxa, reverb=SALA_REVERB,
                                          graves=SALA_GRAVES,
                                          compressao=SALA_COMPRESSAO)
                self.fila_audio.put((frase, tratado, taxa))
            except Exception as e:
                # Uma frase que falha nao pode derrubar o resto da resposta.
                self.erros.append(e)
                print(f"  [Voz: frase pulada -- {e}]")

    def _laco_toque(self):
        primeiro = True
        while True:
            item = self.fila_audio.get()
            if item is None:
                return
            if self.interrompido.is_set():
                continue
            frase, pcm, taxa = item
            try:
                if primeiro:
                    primeiro = False
                    if self.ao_primeiro_audio:
                        self.ao_primeiro_audio()
                sd.play(np.frombuffer(pcm, dtype=np.int16), samplerate=taxa)
                sd.wait()
                # Contabiliza a frase DEPOIS de tocar, nao ao enfileirar: se o
                # usuario interromper, o historico precisa guardar o que ele
                # ouviu, nao o que o Jarvis pretendia dizer.
                if not self.interrompido.is_set():
                    self.faladas.append(frase)
            except Exception as e:
                self.erros.append(e)
                print(f"  [Voz: falha ao reproduzir -- {e}]")

    def finalizar(self, timeout=120):
        """Espera tudo que ja foi enfileirado terminar de tocar."""
        self.fila_texto.put(None)
        self._t_sintese.join(timeout=timeout)
        self._t_toque.join(timeout=timeout)
        return " ".join(self.faladas).strip()


class Voz:
    """Motor de voz multi-backend com cache inteligente e contingencia: Cartesia -> Edge -> Piper."""

    def __init__(self):
        self.piper_voz = None

    def _obter_piper(self):
        if self.piper_voz is None:
            from piper import PiperVoice
            self.piper_voz = PiperVoice.load(str(VOZ_TTS))
        return self.piper_voz

    @staticmethod
    def _hash_cache(texto, motor):
        """Chave normalizada do cache: (texto sem espacos duplos e em minusculas, hash)."""
        texto_norm = " ".join(texto.strip().split()).lower()
        if not texto_norm:
            return None, None
        h = hashlib.md5(f"{motor}_{texto_norm}".encode("utf-8")).hexdigest()
        return texto_norm, h

    def _obter_cache(self, texto, motor):
        """Retorna (PCM, taxa) do cache se existir (RAM ou Disco). Custo < 0.2ms.

        A taxa viaja NO NOME do arquivo (`{hash}.{taxa}.pcm`). Antes ela era
        adivinhada como 24000 na leitura, o que quebrava o Piper: ele gera a
        22050 Hz, entao tudo que voltava do cache dele tocava 8,8% acelerado
        -- mais agudo e mais rapido, justamente no motor que atende quando a
        internet cai.

        Arquivos do esquema antigo (`{hash}.pcm`) continuam valendo para
        Cartesia e Edge, que sao 24000 de verdade. Para o Piper eles sao
        ignorados: ressintetizar custa 0,10s e nenhum credito, entao nao ha
        motivo para arriscar tocar um arquivo de taxa desconhecida.
        """
        texto_norm, h = self._hash_cache(texto, motor)
        if not texto_norm:
            return None

        # 1. Checa memoria RAM (< 0.01ms)
        chave_ram = (motor, texto_norm)
        if chave_ram in CACHE_MEMORIA:
            return CACHE_MEMORIA[chave_ram]

        # 2. Checa disco no esquema novo: a taxa esta no nome (< 0.3ms)
        for caminho in CACHE_VOZ.glob(f"{h}.*.pcm"):
            try:
                taxa = int(caminho.name.split(".")[-2])
            except (ValueError, IndexError):
                continue
            try:
                pcm = caminho.read_bytes()
            except Exception:
                continue
            CACHE_MEMORIA[chave_ram] = (pcm, taxa)
            return pcm, taxa

        # 3. Esquema antigo, sem taxa no nome: confiavel apenas fora do Piper.
        if motor != "piper":
            caminho = CACHE_VOZ / f"{h}.pcm"
            if caminho.exists():
                try:
                    pcm = caminho.read_bytes()
                    CACHE_MEMORIA[chave_ram] = (pcm, 24000)
                    return pcm, 24000
                except Exception:
                    pass
        return None

    def _salvar_cache(self, texto, motor, pcm, taxa):
        """Salva PCM no cache em disco e memoria RAM de forma instantanea."""
        try:
            texto_norm, h = self._hash_cache(texto, motor)
            if not texto_norm:
                return
            CACHE_MEMORIA[(motor, texto_norm)] = (pcm, taxa)
            caminho = CACHE_VOZ / f"{h}.{int(taxa)}.pcm"
            caminho.write_bytes(pcm)
        except Exception:
            pass

    def _cartesia_pcm(self, texto):
        chave = os.getenv("CARTESIA_API_KEY")
        voz_id = os.getenv("CARTESIA_VOICE_ID")
        if not chave or not voz_id:
            raise ValueError("CARTESIA_API_KEY ou CARTESIA_VOICE_ID ausente no .env")

        r = requests.post(
            "https://api.cartesia.ai/tts/bytes",
            headers={
                "Authorization": f"Bearer {chave}",
                "Cartesia-Version": "2026-08-14"
            },
            json={
                "model_id": CARTESIA_MODELO,
                "transcript": texto,
                "voice": {
                    "id": voz_id,
                    "experimental_controls": {"speed": CARTESIA_VELOCIDADE}
                },
                "language": CARTESIA_IDIOMA,
                "output_format": {
                    "container": "raw",
                    "encoding": "pcm_s16le",
                    "sample_rate": CARTESIA_TAXA
                }
            },
            timeout=30
        )
        if r.status_code != 200:
            raise RuntimeError(f"Cartesia HTTP {r.status_code}: {r.text[:100]}")
        return r.content, CARTESIA_TAXA

    def _edge_pcm(self, texto, voz=VOZ_EDGE):
        import edge_tts
        import soundfile as sf

        async def _synth():
            com = edge_tts.Communicate(texto, voz, pitch=TOM_EDGE, rate=RITMO_EDGE)
            dados = bytearray()
            async for p in com.stream():
                if p["type"] == "audio":
                    dados.extend(p["data"])
            audio, taxa = sf.read(io.BytesIO(bytes(dados)), dtype="int16")
            return audio.tobytes(), taxa

        async def _synth_com_timeout():
            return await asyncio.wait_for(_synth(), timeout=4.5)

        return asyncio.run(_synth_com_timeout())

    def _piper_pcm(self, texto):
        voz = self._obter_piper()
        pedacos, taxa = [], 22050
        for chunk in voz.synthesize(texto):
            pedacos.append(chunk.audio_int16_bytes)
            taxa = chunk.sample_rate
        return b"".join(pedacos), taxa

    def sintetizar(self, texto):
        """Tenta o cache primeiro; se nao existir, sintetiza e guarda no cache."""
        motor = (MOTOR_VOZ or "piper").lower()

        # --- Verificacao de Cache Inteligente ---
        cache_hit = self._obter_cache(texto, motor)
        if cache_hit:
            print("  [Voz: audio obtido do cache local (0 creditos gastos, latencia <1ms)]")
            return cache_hit

        pcm, taxa = None, None
        if motor == "cartesia":
            try:
                pcm, taxa = self._cartesia_pcm(texto)
            except Exception as e:
                print(f"  [Cartesia falhou: {e} -> tentando Edge...]")
                motor = "edge"
                cache_edge = self._obter_cache(texto, "edge")
                if cache_edge:
                    return cache_edge

        if motor == "edge":
            try:
                pcm, taxa = self._edge_pcm(texto)
            except Exception as e:
                print(f"  [Edge falhou: {e} -> caindo para Piper local...]")
                motor = "piper"

        if pcm is None:
            pcm, taxa = self._piper_pcm(texto)

        # Salva a resposta sintetizada no cache para reutilizacao futura
        if pcm and taxa:
            self._salvar_cache(texto, motor, pcm, taxa)

        return pcm, taxa

    def falar(self, texto, ao_primeiro=None):
        if not texto.strip():
            return
        try:
            pcm, taxa = self.sintetizar(texto)
            pcm_tratado = presenca.tratar(
                pcm, taxa,
                reverb=SALA_REVERB,
                graves=SALA_GRAVES,
                compressao=SALA_COMPRESSAO
            )
            if ao_primeiro:
                ao_primeiro()

            arr = np.frombuffer(pcm_tratado, dtype=np.int16)
            sd.play(arr, samplerate=taxa)
            sd.wait()
        except Exception as e:
            print(f"  [Erro ao reproduzir voz: {e}]")

    def gerar_pcm(self, texto):
        """Sintetiza sem tocar -- usado pelo modo simulado."""
        pcm, taxa = self.sintetizar(texto)
        return presenca.tratar(
            pcm, taxa,
            reverb=SALA_REVERB,
            graves=SALA_GRAVES,
            compressao=SALA_COMPRESSAO
        ), taxa


class Ouvido:
    """Whisper local: audio -> texto."""

    def __init__(self, tamanho=MODELO_STT):
        from faster_whisper import WhisperModel
        self.modelo = WhisperModel(tamanho, device="cpu", compute_type="int8",
                                   cpu_threads=12)
        # A transcricao adiantada roda em thread. Se o usuario voltar a falar
        # depois do disparo, a transcricao abandonada ainda pode estar viva
        # quando a definitiva comeca -- o lock impede as duas de entrarem no
        # mesmo modelo ao mesmo tempo.
        self._lock = threading.Lock()

    def transcrever(self, pcm16, taxa=TAXA_MIC):
        with self._lock:
            return self._transcrever(pcm16, taxa)

    def _transcrever(self, pcm16, taxa=TAXA_MIC):
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        if taxa != 16000:  # o Whisper espera 16 kHz
            n = int(len(audio) * 16000 / taxa)
            audio = np.interp(np.linspace(0, len(audio), n),
                              np.arange(len(audio)), audio).astype(np.float32)
        segs, _ = self.modelo.transcribe(audio, language="pt", beam_size=1,
                                         vad_filter=False,
                                         condition_on_previous_text=False)
        return " ".join(s.text for s in segs).strip()

# --------------------------------------------------------------------- cerebro

def pensar(pergunta, contexto_tela, historico, ao_primeiro_token=None,
           ao_frase_pronta=None, extras=None):
    """qwen3 local, via /api/chat com historico explicito de mensagens.

    `think:false` e essencial: com o modo pensante ligado o tempo ate a
    primeira palavra sobe de 0,4s para 3,1s.

    Por que /api/chat e nao /api/generate com `context`: passando `context`,
    o Ollama reprocessa a conversa inteira a cada turno. Medido neste projeto:
    0,78s no turno 1, 2,16s no turno 5, crescendo sem parar. Com `messages`
    o custo estabiliza em ~1s.

    Duas regras que impedem o historico de inchar:

    1. O bloco [TELA] entra SO na mensagem do turno atual e nunca e guardado.
       Ele muda a cada turno e e o que mais custa prefill -- guardar seria
       carregar o peso de todas as telas anteriores para sempre.
    2. O historico e cortado nas ultimas MAX_TURNOS_HISTORICO trocas.
    """
    # A PERGUNTA VEM PRIMEIRO, o bloco de tela depois. Nao e cosmetico:
    # com a pergunta enterrada embaixo do muro de dados, o modelo deixava de
    # chamar as ferramentas -- medido, 6 de 8 casos contra 8 de 8 nesta ordem.
    # E a mesma armadilha que o LEIA-ME ja registrava: o bloco [TELA] muda o
    # comportamento do modelo muito alem de "dar contexto".
    if contexto_tela:
        conteudo = (pergunta + "\n\n"
                    + "[DADOS DO SISTEMA - APENAS PARA CONSULTA SILENCIOSA]:\n"
                    + contexto_tela)
    else:
        conteudo = pergunta

    anteriores = list(historico or [])[-(MAX_TURNOS_HISTORICO * 2):]
    sistema = SISTEMA if USAR_FERRAMENTAS else SISTEMA_LEGADO
    # O _sempre.md e ESTAVEL entre turnos, entao entra no prefixo que o Ollama
    # cacheia: medido, 2.000 caracteres estaveis custam +0,04s, contra +0,95s
    # de um bloco do mesmo tamanho que mudasse a cada turno.
    lembretes = memoria.sempre()
    if lembretes:
        sistema += "\n\nO QUE VOCE JA SABE SOBRE O SENHOR:\n" + lembretes
    mensagens = ([{"role": "system", "content": sistema}]
                 + anteriores
                 + [{"role": "user", "content": conteudo}]
                 + list(extras or []))

    corpo = {
        "model": MODELO_LLM, "messages": mensagens,
        "stream": True, "think": False,
        "keep_alive": -1,   # keep_alive vale POR REQUISICAO: sem ele aqui, o
                            # preaquecimento perde efeito apos 5 min de ocio
        "options": {"num_predict": 100, "temperature": 0.3, "num_ctx": NUM_CTX},
    }

    if USAR_FERRAMENTAS:
        corpo["tools"] = FERRAMENTAS_LLM

    req = urllib.request.Request(OLLAMA + "/api/chat",
                                 data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    partes, chamadas = [], []
    primeiro = True
    separador = SeparadorDeFalas() if ao_frase_pronta else None

    with urllib.request.urlopen(req, timeout=300) as r:
        for linha in r:
            if not linha.strip():
                continue
            d = json.loads(linha)
            msg = d.get("message") or {}
            if msg.get("tool_calls"):
                chamadas.extend(msg["tool_calls"])
            pedaco = msg.get("content")
            if pedaco:
                if primeiro:
                    primeiro = False
                    if ao_primeiro_token:
                        ao_primeiro_token()
                partes.append(pedaco)
                if separador:
                    for frase in separador.alimentar(pedaco):
                        ao_frase_pronta(frase)

    if separador:
        for frase in separador.finalizar():
            ao_frase_pronta(frase)

    resposta = "".join(partes).strip()

    # Turno de ferramenta nao entra no historico: quem responde e a ferramenta,
    # nao o modelo, e guardar isso so gastaria prefill nos turnos seguintes.
    if chamadas:
        return resposta, anteriores, chamadas

    # O historico guarda a pergunta LIMPA, sem o bloco de tela.
    novo_historico = anteriores + [
        {"role": "user", "content": pergunta},
        {"role": "assistant", "content": resposta},
    ]
    return resposta, novo_historico[-(MAX_TURNOS_HISTORICO * 2):], chamadas


def preaquecer():
    """Carrega o modelo na VRAM ANTES do primeiro turno.

    Detalhe que custa 18 segundos se esquecido: o Ollama recarrega o modelo
    inteiro quando `num_ctx` muda entre chamadas. O preaquecimento precisa usar
    EXATAMENTE as mesmas opcoes do uso real, senao ele so aquece em vao.

    Usa /api/chat com o MESMO prompt de sistema do uso real, para aquecer
    tambem o cache do prefixo -- nao so o carregamento do modelo.
    """
    corpo = {
        "model": MODELO_LLM,
        "messages": [{"role": "system",
                      "content": SISTEMA if USAR_FERRAMENTAS else SISTEMA_LEGADO},
                     {"role": "user", "content": "oi"}],
        "stream": False, "think": False,
        "keep_alive": -1,   # nunca descarrega
        "options": {"num_predict": 1, "num_ctx": NUM_CTX},
    }
    req = urllib.request.Request(OLLAMA + "/api/chat",
                                 data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        r.read()
    return time.perf_counter() - t0


# ---------------------------------------------------------------- microfone

# ------------------------------------------------------------------ microfone

# Esta maquina tem 15 dispositivos de entrada, entre eles dois cabos virtuais
# (VB-Audio) e um celular usado como webcam (Iriun) que aparece e some. Sem
# fixar nada, o Jarvis abre o que o Windows disser ser o padrao NAQUELE
# instante -- e se o padrao virar um cabo virtual, ele escuta silencio
# absoluto. O sintoma e "as vezes ele nao capta minha voz; fecho e abro e
# volta ao normal", porque reabrir pega o padrao daquele momento.
#
# MICROFONE no .env aceita o indice ou um trecho do nome. Vazio = padrao do
# sistema, que e o comportamento antigo.
DISPOSITIVO_MIC = None          # resolvido uma vez no boot

# Quantos turnos seguidos em silencio digital antes de desconfiar do
# dispositivo. Seis turnos sao ~30s sem NADA -- nem ruido de sala.
TURNOS_MUDOS_PARA_AVISAR = 6
RMS_SILENCIO_DIGITAL = 3.0
_turnos_mudos = 0


def _listar_entradas():
    saida = []
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                saida.append((i, d["name"]))
    except Exception:
        pass
    return saida


def resolver_microfone():
    """Indice do dispositivo de entrada a usar, ou None para o padrao."""
    alvo = (os.getenv("MICROFONE") or "").strip()
    if not alvo:
        return None

    if alvo.isdigit():
        return int(alvo)

    for indice, nome in _listar_entradas():
        if alvo.lower() in nome.lower():
            return indice

    print("  [Microfone] Nada casa com %r. Entradas disponiveis:" % alvo)
    for indice, nome in _listar_entradas():
        print("      [%d] %s" % (indice, nome))
    print("  [Microfone] Usando o padrao do sistema.")
    return None


def anunciar_microfone():
    """Diz no boot QUAL dispositivo foi aberto.

    Existe para que, se o audio sumir de novo, a resposta esteja na tela em
    vez de virar adivinhacao.
    """
    global DISPOSITIVO_MIC
    DISPOSITIVO_MIC = resolver_microfone()
    try:
        d = sd.query_devices(DISPOSITIVO_MIC if DISPOSITIVO_MIC is not None
                             else sd.default.device[0])
        origem = "fixado no .env" if DISPOSITIVO_MIC is not None else "padrao do sistema"
        print("  microfone: %s  (%s)" % (d["name"], origem))
    except Exception as e:
        print("  microfone: nao consegui identificar (%s)" % e)


def _vigiar_silencio(pico_rms):
    """Avisa quando varios turnos seguidos vem em silencio digital.

    Silencio digital nao e sala quieta: e sinal ZERO, a assinatura de estar
    lendo um cabo virtual ou um dispositivo desconectado.
    """
    global _turnos_mudos
    if pico_rms > RMS_SILENCIO_DIGITAL:
        _turnos_mudos = 0
        return

    _turnos_mudos += 1
    if _turnos_mudos != TURNOS_MUDOS_PARA_AVISAR:
        return

    print()
    print("  " + "!" * 58)
    print("  [Microfone] %d turnos seguidos sem sinal nenhum (pico RMS %.1f)."
          % (_turnos_mudos, pico_rms))
    print("  Isto nao e sala silenciosa -- e sinal zero. O dispositivo aberto")
    print("  provavelmente nao e o seu microfone.")
    try:
        d = sd.query_devices(DISPOSITIVO_MIC if DISPOSITIVO_MIC is not None
                             else sd.default.device[0])
        print("  Aberto agora: %s" % d["name"])
    except Exception:
        pass
    print("  Entradas disponiveis:")
    for indice, nome in _listar_entradas():
        print("      [%d] %s" % (indice, nome))
    print("  Ponha MICROFONE=<numero ou parte do nome> no .env e reinicie.")
    print("  " + "!" * 58)
    print()


def duracao_segundos(pcm, taxa=TAXA_MIC):
    """Duracao real de um bloco de PCM 16 bits mono, em segundos.

    Existe para nao comparar bytes com amostras. O bug que motivou o helper:
    `len(pcm) < TAXA_MIC * 0.4` parece "menos de 0,4s", mas `len(pcm)` esta em
    BYTES e TAXA_MIC em AMOSTRAS -- o limiar real era a metade, 0,2s.
    """
    return len(pcm) / float(taxa * BYTES_POR_AMOSTRA)


def _transcrever_em_paralelo(ouvido, pcm, taxa):
    """Dispara a transcricao numa thread. Devolve (thread, dict de saida)."""
    saida = {}

    def alvo():
        try:
            saida["texto"] = ouvido.transcrever(pcm, taxa)
        except Exception as e:
            saida["erro"] = e

    t = threading.Thread(target=alvo, daemon=True)
    t.start()
    return t, saida


def escutar(ouvido, limite=25.0):
    """Grava do microfone ate detectar silencio.

    Devolve (PCM 16 kHz, texto ja transcrito ou None).

    O VAD espera VAD_SILENCIO segundos de silencio antes de fechar o turno, e
    esse tempo era ocioso. Agora a transcricao dispara assim que a voz cai e
    roda DURANTE a espera -- quando o turno fecha, o texto costuma estar
    pronto.

    Nao ha perda de precisao: o que vem depois do disparo e silencio, entao o
    trecho enviado ao Whisper ja contem a fala inteira. O disparo espera
    VAD_ATRASO_TRANSCRICAO para nao cortar o rabo da ultima palavra -- o RMS e
    media do bloco, entao ele cai antes de a palavra realmente acabar.

    Se o usuario voltar a falar depois do disparo, o resultado e descartado e
    a transcricao acontece normalmente no fim. Isso dispara no maximo uma vez
    por turno: duas transcricoes disputando CPU sairiam mais caro que a espera.
    """
    fila = queue.Queue()

    def cb(indata, frames, t, status):
        fila.put(bytes(indata))

    blocos, falou, ultimo_som = [], False, time.time()
    adiantada = None          # ((thread, saida), marca de ultimo_som no disparo)

    pico_rms = 0.0
    with sd.RawInputStream(samplerate=TAXA_MIC, channels=1, dtype="int16",
                           blocksize=BLOCO, callback=cb,
                           device=DISPOSITIVO_MIC):
        inicio = time.time()
        print("  (ouvindo microfone...)")
        hud_bridge.notificar(state="listening")
        while time.time() - inicio < limite:
            try:
                b = fila.get(timeout=0.15)
            except queue.Empty:
                continue
            rms = float(np.sqrt(np.mean(
                np.frombuffer(b, dtype=np.int16).astype(np.float32) ** 2)))
            pico_rms = max(pico_rms, rms)
            if rms > VAD_LIMIAR:
                falou = True
                ultimo_som = time.time()
                blocos.append(b)
            elif falou:
                blocos.append(b)
                silencio = time.time() - ultimo_som
                if adiantada is None and silencio > VAD_ATRASO_TRANSCRICAO:
                    adiantada = (_transcrever_em_paralelo(
                        ouvido, b"".join(blocos), TAXA_MIC), ultimo_som)
                if silencio > VAD_SILENCIO:
                    break
            else:
                if time.time() - inicio > 5.0:
                    break

    _vigiar_silencio(pico_rms)

    pcm = b"".join(blocos)
    texto = None
    if adiantada is not None:
        (thread, saida), marca = adiantada
        if marca == ultimo_som:     # ninguem falou depois do disparo
            thread.join(timeout=15)
            texto = saida.get("texto")
    return pcm, texto


# -------------------------------------------------------------------- ciclo

def ciclo(ouvido, voz, pcm, taxa, historico, rotulo="", texto_pronto=None):
    global BRILHO_HUD_ATUAL
    e = Etapas()
    if rotulo:
        print('  voce: %r' % rotulo)

    if texto_pronto is not None:
        texto = texto_pronto
        e.marca("1. Whisper (sobreposto ao VAD)")
    else:
        texto = ouvido.transcrever(pcm, taxa)
        e.marca("1. Whisper (fala -> texto)")
    print("  entendeu: %r" % texto)
    if not texto:
        print("  (nao entendi nada)")
        hud_bridge.notificar(state="idle")
        return historico

    # --- Interceptores por substring: SO no modo de rollback ---
    # Com USAR_FERRAMENTAS o modelo decide por intencao, e estes dois
    # ficam desligados. Continuam aqui para a flag poder voltar atras.
    cmd_interface = processar_comando_interface(texto) if not USAR_FERRAMENTAS else None
    if cmd_interface:
        msg_resposta, dados_hud = cmd_interface
        print(f"  [INTERFACE] Comando de HUD detectado: {dados_hud}")
        e.marca("2. comando de interface processado")
        hud_bridge.notificar(state="speaking", jarvisSpeech=msg_resposta, **dados_hud)
        voz.falar(msg_resposta)
        e.marca("3. Voz (confirmação da HUD) <- FALA")
        e.relatorio()
        hud_bridge.notificar(state="idle")
        return historico

    res_ferramenta = ferramentas.processar_ferramenta(texto) if not USAR_FERRAMENTAS else None
    if res_ferramenta:
        print(f"  [FERRAMENTA EM TEMPO REAL]: {res_ferramenta}")
        e.marca("2. Ferramenta Especializada (AwesomeAPI / Open-Meteo)")
        hud_bridge.notificar(state="speaking", jarvisSpeech=res_ferramenta)
        voz.falar(res_ferramenta)
        e.marca("3. Voz (resposta da ferramenta) <- FALA")
        e.relatorio()
        hud_bridge.notificar(state="idle")
        return historico

    # Leitura de contexto e envio de telemetria para a HUD
    # No modo novo a tela NAO vai colada na pergunta: o modelo pede com a
    # ferramenta ler_tela quando precisa. Isso tira 0,95s do 1o token de todo
    # turno e some com a origem das quatro armadilhas de prompt do LEIA-ME.
    if not TELA_COMO_FERRAMENTA:
        contexto_tela = percepcao.contexto(limite_caracteres=1200)[0]
    elif vigia.VIGIA.ligado:
        # Modo de acompanhamento: a leitura ja esta pronta e vai junto da
        # pergunta, sem a segunda ida ao modelo. E o que conserta a pergunta
        # encadeada ("e o que tem nela?"), que antes nao relia e inventava.
        contexto_tela = vigia.VIGIA.atual()[0]
    else:
        contexto_tela = ""
    e.marca("2. contexto de tela (UI Automation)")

    j_info = percepcao.janela_ativa()
    cur_info = percepcao.sob_o_cursor()
    win_title = j_info.get("titulo", "") if isinstance(j_info, dict) else ""
    cur_desc = f"{cur_info.get('tipo', '')} ({cur_info.get('nome', '')})" if isinstance(cur_info, dict) else ""

    hud_bridge.notificar(
        state="thinking",
        userSpeech=texto,
        windowTitle=win_title or "Área de Trabalho",
        activeTarget=cur_desc or "Cursor Ativo"
    )

    # A voz emenda no modelo: cada frase pronta ja vai sendo falada enquanto
    # ele escreve o resto. O FluxoDeFala sintetiza a proxima enquanto a atual
    # toca, entao nao ha silencio entre elas.
    global FALA_EM_CURSO
    fluxo = None
    if VOZ_STREAMING:
        fluxo = FluxoDeFala(voz, ao_primeiro_audio=lambda: e.marca("5. Voz (1o audio) <- FALA"))
    FALA_EM_CURSO = fluxo

    # A HUD recebe o texto ACUMULADO, nao a frase solta: mandando frase a
    # frase ela ficaria trocando de legenda a cada uma, em vez de mostrar a
    # resposta crescendo.
    faladas_hud = []

    def _frase(f):
        faladas_hud.append(f)
        hud_bridge.notificar(state="speaking", jarvisSpeech=" ".join(faladas_hud))
        fluxo.dizer(f)

    # --- memoria: busca automatica, nao por escolha do modelo ---
    #
    # Deixar o modelo decidir NAO funcionou: medido, 6 de 18 perguntas de
    # recordacao chamavam a ferramenta certa -- "qual e o meu monitor
    # principal?" ia para a ler_tela, porque soa como tela. O FTS5 decide
    # melhor: 5/6 acham a nota certa e 10/10 perguntas que nao sao de memoria
    # nao acham NADA. Sem falso positivo, entao nao precisa nem de limiar.
    #
    # E o custo so aparece quando ha o que lembrar: turno sem acerto nao paga
    # nada de prefill.
    achados = memoria.buscar(texto, limite=2)
    if achados:
        linhas = ["[MEMORIA] Suas anotacoes sobre isto:"]
        for titulo, _c, trecho, _n in achados:
            linhas.append("- [%s] %s" % (titulo, " ".join(trecho.split())))
        contexto_tela = ((contexto_tela + "\n\n") if contexto_tela else "")             + "\n".join(linhas)
        print("  [MEMORIA] %d trecho(s) recuperado(s)" % len(achados))

    resposta, novo_hist, chamadas = pensar(
        texto, contexto_tela, historico,
        ao_primeiro_token=lambda: e.marca("3. qwen3 (1o token)"),
        ao_frase_pronta=_frase if fluxo else None)
    e.marca("4. qwen3 (resposta completa)")

    # --- Turno de ferramenta ---
    # O modelo devolve tool_calls e NENHUM texto, entao nada foi streamado.
    # Executamos e falamos o resultado direto, sem uma segunda ida ao modelo
    # para redigir: ferramentas.py ja devolve frase pronta e as respostas de
    # cor e brilho ja existem em PALETAS_MAPA. Isso segura o custo do turno em
    # ~0,9s em vez de ~1,7s.
    if chamadas:
        if fluxo:
            fluxo.finalizar()
            fluxo = None
        falas, dados_hud, para_o_modelo = [], {}, []
        for chamada in chamadas:
            fn = chamada.get("function") or {}
            texto_fer, dados = executar_ferramenta(fn.get("name"), fn.get("arguments"))
            print("  [FERRAMENTA] %s(%s) -> %r"
                  % (fn.get("name"), fn.get("arguments"), (texto_fer or "")[:60]))
            if texto_fer:
                falas.append(texto_fer)
            if "para_o_modelo" in dados:
                para_o_modelo.append((chamada, dados.pop("para_o_modelo")))
            dados_hud.update(dados)

        # Ferramenta que INFORMA (hoje so a ler_tela): o resultado nao e
        # resposta, volta ao modelo para ele redigir. As demais falam direto,
        # que e o que segura o custo dos turnos de acao.
        if para_o_modelo:
            e.marca("5. ler_tela executada")
            extras = []
            for chamada, conteudo in para_o_modelo:
                extras.append({"role": "assistant", "content": "",
                               "tool_calls": [chamada]})
                extras.append({"role": "tool", "content": conteudo})
            fluxo = FluxoDeFala(
                voz, ao_primeiro_audio=lambda: e.marca("7. Voz (1o audio) <- FALA")
            ) if VOZ_STREAMING else None
            faladas_hud.clear()
            resposta, novo_hist, _ = pensar(
                texto, "", historico, extras=extras,
                ao_primeiro_token=lambda: e.marca("6. qwen3 (1o token, 2a ida)"),
                ao_frase_pronta=_frase if fluxo else None)
            e.marca("8. resposta completa")

            # Contradicao com a leitura que ele mesmo pediu: uma unica
            # repescagem, apontando o que acabou de acontecer.
            if nega_ver_tela(resposta):
                print("  [Tela] ele negou enxergar depois de ler; repetindo.")
                if fluxo:
                    fluxo.interromper()
                    fluxo = FluxoDeFala(voz, ao_primeiro_audio=lambda: e.marca(
                        "7. Voz (1o audio) <- FALA"))
                    faladas_hud.clear()
                repescagem = extras + [
                    {"role": "assistant", "content": resposta},
                    {"role": "user", "content": "Voce acabou de ler a tela com "
                                                "sucesso. Responda de novo, "
                                                "dizendo o que viu."}]
                resposta, novo_hist, _ = pensar(
                    texto, "", historico, extras=repescagem,
                    ao_frase_pronta=_frase if fluxo else None)
                e.marca("9. repescagem")

            if fluxo:
                falado = fluxo.finalizar()
                if falado:
                    resposta = falado
                else:
                    voz.falar(resposta)
            else:
                hud_bridge.notificar(state="speaking", jarvisSpeech=resposta)
                voz.falar(resposta)
            if novo_hist and novo_hist[-1].get("role") == "assistant":
                novo_hist[-1]["content"] = resposta
            registrar_na_transcricao(texto, resposta)
            e.relatorio()
            hud_bridge.notificar(state="idle", benchmarks=e.resumo())
            return novo_hist

        resposta = " ".join(falas).strip() or "Feito, senhor."
        e.marca("5. ferramenta executada")
        hud_bridge.notificar(state="speaking", jarvisSpeech=resposta, **dados_hud)
        voz.falar(resposta, ao_primeiro=lambda: e.marca("6. Voz (1o audio) <- FALA"))
        registrar_na_transcricao(texto, resposta)
        e.relatorio()
        hud_bridge.notificar(state="idle", benchmarks=e.resumo())
        return novo_hist
    
    # --- Tags emitidas pelo modelo: SO no modo de rollback ---
    # Com USAR_FERRAMENTAS o prompt nao pede tag nenhuma; cor e brilho vem
    # como tool_calls e ja foram tratados acima.
    dados_hud_acao = {}
    if not USAR_FERRAMENTAS and "[COR:" in resposta:
        m_cor = re.search(r'\[COR:\s*([a-zA-ZáàâãéèêíïóôõöúçñÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇÑ]+)\]', resposta)
        if m_cor:
            cor_tag = m_cor.group(1).lower().strip()
            for k, (tema_id, _) in PALETAS_MAPA.items():
                if k in cor_tag:
                    dados_hud_acao["theme"] = tema_id
                    break
            if "theme" not in dados_hud_acao:
                dados_hud_acao["theme"] = cor_tag
        resposta = re.sub(r'\[COR:[^\]]+\]', '', resposta).strip()

    if not USAR_FERRAMENTAS and "[BRILHO:" in resposta:
        if "[BRILHO: +]" in resposta:
            BRILHO_HUD_ATUAL = min(2.0, round(BRILHO_HUD_ATUAL + 0.35, 2))
            dados_hud_acao["brightness"] = BRILHO_HUD_ATUAL
        elif "[BRILHO: -]" in resposta:
            BRILHO_HUD_ATUAL = max(0.25, round(BRILHO_HUD_ATUAL - 0.35, 2))
            dados_hud_acao["brightness"] = BRILHO_HUD_ATUAL
        resposta = re.sub(r'\[BRILHO:[^\]]+\]', '', resposta).strip()

    # Limpeza rigorosa contra vazamento de metadados internos de tela
    for vazamento in ["[TELA]", "[CURSOR]", "[CONTEUDO VISIVEL]", "[DADOS DO SISTEMA", "[USUÁRIO]:", "[JARVIS]:"]:
        if vazamento in resposta:
            linhas = [l for l in resposta.split("\n") if not any(tag in l for tag in ["[TELA]", "[CURSOR]", "[CONTEUDO VISIVEL]", "[DADOS DO SISTEMA", "[USUÁRIO]:", "[JARVIS]:"])]
            resposta = " ".join(linhas).strip()

    if not resposta.strip():
        resposta = "Comandos executados, senhor."

    print("  Jarvis (Local): %r" % resposta[:150])
    if dados_hud_acao:
        hud_bridge.notificar(state="speaking", **dados_hud_acao)
    if fluxo:
        # As frases ja foram enfileiradas durante o streaming; aqui so
        # esperamos a ultima terminar de tocar.
        falado = fluxo.finalizar()
        fluxo = None
        if falado:
            resposta = falado
        else:
            # O separador nao liberou nada (resposta so de tags, por
            # exemplo). Cai no modo antigo para nao ficar mudo.
            hud_bridge.notificar(state="speaking", jarvisSpeech=resposta)
            voz.falar(resposta, ao_primeiro=lambda: e.marca("5. Voz (1o audio) <- FALA"))
    else:
        hud_bridge.notificar(state="speaking", jarvisSpeech=resposta)
        voz.falar(resposta, ao_primeiro=lambda: e.marca("5. Voz (1o audio) <- FALA"))
    e.marca("6. terminou de falar")

    # O historico guarda o que o Jarvis FALOU, nao a saida crua do modelo.
    #
    # Sem isto, qualquer tag ou vazamento que escape uma vez fica no historico
    # como fala do assistente -- e o modelo passa a IMITAR a si mesmo. Medido
    # quando ainda havia a tag [CONSULTAR:]: bastava ela aparecer no turno 2
    # para todos os turnos seguintes virarem [CONSULTAR:], mandando para a web
    # ate perguntas que ele responde sozinho ("capital da Franca").
    if novo_hist and novo_hist[-1].get("role") == "assistant":
        novo_hist[-1]["content"] = resposta

    FALA_EM_CURSO = None
    registrar_na_transcricao(texto, resposta)
    e.relatorio()
    hud_bridge.notificar(
        state="idle",
        benchmarks=e.resumo()
    )
    return novo_hist


def main():
    if "--doutor" in sys.argv:
        # Autodiagnostico: diz EM QUE CAMADA algo esta falhando, em vez de
        # deixar microfone mudo, HUD travada e modelo fora do ar produzirem
        # todos o mesmo sintoma ("ele nao respondeu").
        import doutor
        sys.exit(doutor.rodar(rapido="--rapido" in sys.argv))

    simulado = "--simulado" in sys.argv
    sem_hud = "--sem-hud" in sys.argv

    # Inicia a ponte e abre a HUD desktop completa e maximizada automaticamente
    hud_bridge.iniciar(auto_abrir=not sem_hud, modo_inicial="completo")

    print("=" * 60)
    print("  JARVIS LOCAL -- 100%% offline  (%s)"
          % ("simulado" if simulado else "escuta contínua no microfone"))
    print("=" * 60)

    if (os.getenv("LEITURA_DE_TELA") or "").strip().lower() in ("on", "1", "sim", "true"):
        vigia.VIGIA.ligar()
        print("  leitura de tela: ATIVA desde o boot (LEITURA_DE_TELA no .env)")

    # ctrl+shift+space e nao ctrl+alt+space: o segundo ja estava tomado por
    # outro programa nesta maquina, e e um dos candidatos mais disputados.
    combinacao = (os.getenv("ATALHO_INTERROMPER") or "ctrl+shift+space").strip()
    if combinacao.lower() not in ("", "off", "nenhum"):
        import atalho
        ok, usada, era_reserva = atalho.registrar_com_reserva(
            combinacao, interromper_fala)
        if ok and era_reserva:
            print("  atalho para interromper: %s  (%s ja estava em uso)"
                  % (usada, combinacao))
        elif ok:
            print("  atalho para interromper: %s" % usada)
        else:
            # Nao e motivo para nao subir, mas nao pode falhar em silencio.
            print("  [Atalho] nenhuma combinacao livre (%s); defina uma em "
                  "ATALHO_INTERROMPER no .env" % usada)

    novas, atualizadas, _ = memoria.indexar()
    est = memoria.estatisticas()
    print("  memoria: %d notas em %s%s"
          % (est["notas"], est["vault"],
             " (%d novas, %d atualizadas)" % (novas, atualizadas)
             if novas or atualizadas else ""))

    t0 = time.perf_counter()
    anunciar_microfone()
    voz = Voz()
    ouvido = Ouvido()
    percepcao.contexto()          # aquece a arvore de acessibilidade
    print("  carga local: %.1fs" % (time.perf_counter() - t0))
    print("  preaquecendo %s (num_ctx=%d)..." % (MODELO_LLM, NUM_CTX))
    print("  modelo pronto em %.1fs" % preaquecer())
    print()

    historico = []
    if simulado:
        FALAS = [
            "Bom dia! Tudo certo?",
            "O que eu estou fazendo agora na tela?",
            "Qual e a capital da Franca?",
        ]
        for f in FALAS:
            print("=" * 60)
            pcm, taxa = voz.gerar_pcm(f)
            historico = ciclo(ouvido, voz, pcm, taxa, historico, rotulo=f)
            print()
    else:
        print("Assistente pronto. Fale no microfone a qualquer momento.")
        print("Pressione Ctrl+C para encerrar.")
        while True:
            print("=" * 60)
            pcm, texto_adiantado = escutar(ouvido)
            if duracao_segundos(pcm) < 0.4:
                continue
            historico = ciclo(ouvido, voz, pcm, TAXA_MIC, historico,
                              texto_pronto=texto_adiantado)
            print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nate mais.")
