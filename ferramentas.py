"""Módulos Especializados em Tempo Real para o J.A.R.V.I.S.

1. Cotações Financeiras em Tempo Real (AwesomeAPI - 100% gratuita, sem chave)
   - Dólar (USD), Euro (EUR), Bitcoin (BTC), Ethereum (ETH), Libra (GBP), Iene (JPY)
2. Previsão do Tempo / Meteorologia (Open-Meteo & Geocoding - 100% gratuita, sem chave)
   - Temperatura, sensação térmica, chuva/precipitação, umidade, vento e condição climática.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Módulo 1: Cotações Financeiras em Tempo Real (AwesomeAPI)
# ---------------------------------------------------------------------------

MOEDAS_MAPA = {
    "dolar": "USD-BRL",
    "dólar": "USD-BRL",
    "usd": "USD-BRL",
    "euro": "EUR-BRL",
    "eur": "EUR-BRL",
    "bitcoin": "BTC-BRL",
    "btc": "BTC-BRL",
    "ethereum": "ETH-BRL",
    "eth": "ETH-BRL",
    "libra": "GBP-BRL",
    "gbp": "GBP-BRL",
    "iene": "JPY-BRL",
    "jpy": "JPY-BRL",
}

NOMES_MOEDAS = {
    "USD-BRL": "Dólar",
    "EUR-BRL": "Euro",
    "BTC-BRL": "Bitcoin",
    "ETH-BRL": "Ethereum",
    "GBP-BRL": "Libra",
    "JPY-BRL": "Iene Japonês",
}


# ---------------------------------------------------------------------------
# Rede: uma falha passageira não pode derrubar a função inteira
# ---------------------------------------------------------------------------
#
# Medido em 28/ago/2026: `api.open-meteo.com` ficou inalcançável desta máquina
# por vários minutos — o handshake TLS estourava até com 15s de timeout — e
# voltou sozinha depois. Com timeout curto e nenhuma retentativa, isso deixava
# a previsão do tempo simplesmente morta durante todo o episódio.

TEMPO_LIMITE = 3.0        # segundos por tentativa
TENTATIVAS = 2            # a primeira mais uma repescagem
ESPERA_ENTRE = 0.3        # segundos antes de tentar de novo
ORCAMENTO = 6.0           # teto do que o usuario espera ouvindo silencio
TTL_CACHE = 600           # 10 min: por quanto tempo um dado velho ainda serve

_ULTIMO_BOM = {}          # chave -> (instante, texto)


def _pedir_json(url, prazo=None, tentativas=TENTATIVAS):
    """GET de JSON com uma retentativa, dentro de um PRAZO comum.

    O prazo existe porque a resiliencia sozinha e uma armadilha: subindo o
    timeout e somando retentativas, o pior caso medido virou 18s numa cotacao.
    Num assistente de voz isso e inaceitavel -- e melhor dizer o dado de tres
    minutos atras do que deixar o usuario esperando em silencio.

    `prazo` e um instante de time.monotonic() compartilhado por TODAS as
    chamadas de uma mesma pergunta: obter_clima faz duas (geocoding e
    previsao) e as duas cabem dentro do mesmo teto.
    """
    ultimo_erro = None
    for n in range(tentativas):
        restante = TEMPO_LIMITE if prazo is None else prazo - time.monotonic()
        if restante <= 0.3:
            ultimo_erro = "prazo esgotado"
            break
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Jarvis-Local/1.0"})
            with urllib.request.urlopen(req, timeout=min(TEMPO_LIMITE, restante)) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            ultimo_erro = e
            if n + 1 < tentativas:
                time.sleep(ESPERA_ENTRE)
    print(f"[REDE] {url.split('?')[0]} falhou: {ultimo_erro}")
    return None


def _guardar(chave, texto):
    """Registra a última leitura boa e devolve o texto sem alterá-lo."""
    if texto:
        _ULTIMO_BOM[chave] = (time.time(), texto)
    return texto


def _resgatar(chave):
    """Última leitura boa, se ainda recente, com a idade dita em voz alta.

    Um dado de seis minutos atrás, apresentado como tal, é mais útil que
    "não consegui" — e honesto, porque a idade vai junto na frase.
    """
    item = _ULTIMO_BOM.get(chave)
    if not item:
        return None
    idade = time.time() - item[0]
    if idade > TTL_CACHE:
        return None
    minutos = int(idade // 60)
    if minutos < 1:
        quando = "de instantes atrás"
    elif minutos == 1:
        quando = "de um minuto atrás"
    else:
        quando = f"de {minutos} minutos atrás"
    return f"A rede falhou agora, senhor. Pela leitura {quando}: {item[1]}"


def obter_cotacao(par_moeda="USD-BRL"):
    """Consulta a cotação exata em tempo real na AwesomeAPI."""
    prazo = time.monotonic() + ORCAMENTO
    data = _pedir_json(f"https://economia.awesomeapi.com.br/last/{par_moeda}", prazo)
    if data:
        try:
            chave = par_moeda.replace("-", "")
            if chave in data:
                item = data[chave]
                valor = float(item.get("bid", 0))
                variacao = float(item.get("pctChange", 0))
                maxima = float(item.get("high", 0))
                minima = float(item.get("low", 0))
                nome = NOMES_MOEDAS.get(par_moeda, par_moeda)

                # Formatação especial para Cripto vs Moeda Fiduciária
                if "BTC" in par_moeda:
                    valor_fmt = f"R$ {valor:,.0f}".replace(",", ".")
                    max_fmt = f"R$ {maxima:,.0f}".replace(",", ".")
                    min_fmt = f"R$ {minima:,.0f}".replace(",", ".")
                elif "ETH" in par_moeda:
                    valor_fmt = f"R$ {valor:,.2f}".replace(".", ",")
                    max_fmt = f"R$ {maxima:,.2f}".replace(".", ",")
                    min_fmt = f"R$ {minima:,.2f}".replace(".", ",")
                else:
                    valor_fmt = f"R$ {valor:.2f}".replace(".", ",")
                    max_fmt = f"R$ {maxima:.2f}".replace(".", ",")
                    min_fmt = f"R$ {minima:.2f}".replace(".", ",")

                tendencia = (
                    f"alta de {abs(variacao):.2f}%"
                    if variacao >= 0
                    else f"queda de {abs(variacao):.2f}%"
                )
                return _guardar("cotacao:" + par_moeda, (
                    f"O {nome} está cotado a {valor_fmt} no momento, operando em {tendencia} hoje. "
                    f"A máxima do dia foi de {max_fmt} e a mínima de {min_fmt}."
                ))
        except Exception as e:
            print(f"[ERRO COTAÇÃO]: {e}")

    return _resgatar("cotacao:" + par_moeda)


def detectar_cotacao(texto):
    """Detecta se o usuário perguntou sobre cotação e retorna a resposta."""
    t = texto.lower()
    gatilhos = [
        "cotação",
        "cotacao",
        "quanto está",
        "quanto tá",
        "quanto vale",
        "preço",
        "preco",
        "valor do",
        "valor da",
        "dólar",
        "dolar",
        "euro",
        "bitcoin",
        "ethereum",
        "libra",
    ]

    if not any(g in t for g in gatilhos):
        return None

    for termo, par in MOEDAS_MAPA.items():
        if re.search(r"\b" + re.escape(termo) + r"\b", t):
            return obter_cotacao(par)

    return None


# ---------------------------------------------------------------------------
# Módulo 2: Previsão do Tempo / Clima (Open-Meteo & Geocoding)
# ---------------------------------------------------------------------------

WMO_WEATHER_CODES = {
    0: "céu limpo e ensolarado",
    1: "predominantemente ensolarado",
    2: "parcialmente nublado",
    3: "encoberto por nuvens",
    45: "com neblina",
    48: "com nevoeiro denso",
    51: "com garoa leve",
    53: "com garoa moderada",
    55: "com garoa densa",
    61: "com chuva fraca",
    63: "com chuva moderada",
    65: "com chuva forte",
    71: "com neve fraca",
    73: "com neve moderada",
    75: "com neve intensa",
    80: "com pancadas de chuva leves",
    81: "com pancadas de chuva moderadas",
    82: "com temporais fortes",
    95: "com tempestade com trovoadas",
    96: "com tempestade e granizo leve",
    99: "com tempestade severa e granizo",
}


_GEO = {}                 # nome da cidade em minúsculas -> (nome, lat, lon)


def cidade_padrao():
    """Cidade configurada no `.env`, usada quando a pergunta não diz qual.

    Lida a cada chamada, não no import: o `.env` é carregado pelo `jarvis.py`
    depois de importar este módulo.
    """
    return (os.getenv("CIDADE_PADRAO") or "").strip()


def obter_cidade_ip(prazo=None):
    """Descobre a cidade pelo IP. É o ÚLTIMO recurso.

    O endpoint gratuito do ip-api só atende em **HTTP puro**: sua cidade e
    coordenadas voltam em texto claro pela rede. Configurar `CIDADE_PADRAO`
    no `.env` faz esta função nunca ser chamada.
    """
    data = _pedir_json("http://ip-api.com/json/?fields=status,city,regionName,lat,lon", prazo)
    if data and data.get("status") == "success":
        return (data.get("city", "São Paulo"), data.get("lat"), data.get("lon"))
    return ("São Paulo", -23.5505, -46.6333)


def geocodificar_cidade(nome_cidade, prazo=None):
    """Latitude e longitude de uma cidade pelo nome, com cache em memória.

    O cache importa: sem ele, toda pergunta de clima gastaria duas viagens de
    rede (geocoding + previsão). Coordenada de cidade não muda, então a
    primeira pergunta paga as duas e as seguintes pagam uma.
    """
    chave = nome_cidade.lower().strip()
    if chave in _GEO:
        return _GEO[chave]

    cidade_enc = urllib.parse.quote(nome_cidade)
    data = _pedir_json(
        f"https://geocoding-api.open-meteo.com/v1/search"
        f"?name={cidade_enc}&count=1&language=pt&format=json", prazo)
    if data and data.get("results"):
        primeiro = data["results"][0]
        achado = (primeiro.get("name", nome_cidade),
                  primeiro.get("latitude"), primeiro.get("longitude"))
        _GEO[chave] = achado
        return achado
    return None


def _localizar(cidade_solicitada, prazo):
    """Resolve (nome, lat, lon) na ordem: pedida -> padrão do .env -> IP."""
    for candidata in (cidade_solicitada, cidade_padrao()):
        if candidata:
            geo = geocodificar_cidade(candidata, prazo)
            if geo:
                return geo
    return obter_cidade_ip(prazo)


def obter_clima(cidade_solicitada=None):
    """Obtém dados meteorológicos ao vivo do Open-Meteo."""
    chave = "clima:" + (cidade_solicitada or cidade_padrao() or "ip").lower().strip()
    prazo = time.monotonic() + ORCAMENTO

    cidade, lat, lon = _localizar(cidade_solicitada, prazo)

    data = _pedir_json(
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&current="
        f"temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,"
        f"rain,weather_code,wind_speed_10m&timezone=auto", prazo)

    if data and "current" in data:
        try:
            cur = data["current"]
            temp = round(cur.get("temperature_2m", 0))
            sensacao = round(cur.get("apparent_temperature", temp))
            umidade = cur.get("relative_humidity_2m", 0)
            precipitacao = cur.get("precipitation", 0)
            vento = round(cur.get("wind_speed_10m", 0))
            code = cur.get("weather_code", 0)
            condicao = WMO_WEATHER_CODES.get(code, "céu parcialmente nublado")
            chuva_str = ("Há chuva no momento" if precipitacao > 0 else "sem chuva agora")

            return _guardar(chave, (
                f"Em {cidade}, a temperatura atual é de {temp}°C com sensação térmica "
                f"de {sensacao}°C e {condicao}. A umidade do ar está em {umidade}% "
                f"com ventos a {vento} km/h, {chuva_str}."
            ))
        except Exception as e:
            print(f"[ERRO CLIMA]: {e}")

    return _resgatar(chave)


def detectar_clima(texto):
    """Detecta perguntas sobre tempo, chuva e clima."""
    t = texto.lower()
    gatilhos_clima = [
        "clima",
        "tempo",
        "previsão",
        "previsao",
        "temperatura",
        "vai chover",
        "está chovendo",
        "chuva",
        "calor",
        "frio",
    ]

    if not any(g in t for g in gatilhos_clima):
        return None

    # Tenta extrair o nome da cidade se mencionada
    # Ex: "vai chover em curitiba", "qual o tempo no rio de janeiro", "previsão para salvador"
    m = re.search(
        r"(?:em|no|na|para|de)\s+([a-zA-ZáàâãéèêíïóôõöúçñÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇÑ\s]{3,25})(?:\?|\.|$)",
        t,
    )
    cidade = None
    if m:
        candidato = m.group(1).strip()
        palavras_ignorar = [
            "hoje",
            "amanhã",
            "agora",
            "minha cidade",
            "momento",
            "tempo",
            "clima",
            "casa",
        ]
        if candidato not in palavras_ignorar and len(candidato) > 2:
            cidade = candidato

    return obter_clima(cidade)


# ---------------------------------------------------------------------------
# Ponto Central de Roteamento de Ferramentas
# ---------------------------------------------------------------------------


def processar_ferramenta(texto):
    """Verifica se a pergunta aciona os módulos especializados de cotação ou clima."""
    if not texto:
        return None

    # 1. Checa Cotação de Moedas
    res_cotacao = detectar_cotacao(texto)
    if res_cotacao:
        return res_cotacao

    # 2. Checa Clima e Meteorologia
    res_clima = detectar_clima(texto)
    if res_clima:
        return res_clima

    return None
