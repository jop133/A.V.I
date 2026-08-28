"""Módulos Especializados em Tempo Real para o J.A.R.V.I.S.

1. Cotações Financeiras em Tempo Real (AwesomeAPI - 100% gratuita, sem chave)
   - Dólar (USD), Euro (EUR), Bitcoin (BTC), Ethereum (ETH), Libra (GBP), Iene (JPY)
2. Previsão do Tempo / Meteorologia (Open-Meteo & Geocoding - 100% gratuita, sem chave)
   - Temperatura, sensação térmica, chuva/precipitação, umidade, vento e condição climática.
"""

import json
import re
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


def obter_cotacao(par_moeda="USD-BRL"):
    """Consulta a cotação exata em tempo real na AwesomeAPI."""
    try:
        url = f"https://economia.awesomeapi.com.br/last/{par_moeda}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Jarvis-Local/1.0"}
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode())

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
            return (
                f"O {nome} está cotado a {valor_fmt} no momento, operando em {tendencia} hoje. "
                f"A máxima do dia foi de {max_fmt} e a mínima de {min_fmt}."
            )
    except Exception as e:
        print(f"[ERRO COTAÇÃO]: {e}")
    return None


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


def obter_cidade_ip():
    """Detecta a cidade atual do usuário via geolocalização por IP (gratuita)."""
    try:
        req = urllib.request.Request(
            "http://ip-api.com/json/?fields=status,city,regionName,lat,lon",
            headers={"User-Agent": "Jarvis-Local/1.0"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success":
                return (
                    data.get("city", "São Paulo"),
                    data.get("lat"),
                    data.get("lon"),
                )
    except Exception:
        pass
    return ("São Paulo", -23.5505, -46.6333)


def geocodificar_cidade(nome_cidade):
    """Busca latitude e longitude de qualquer cidade do mundo pelo nome."""
    try:
        cidade_enc = urllib.parse.quote(nome_cidade)
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={cidade_enc}&count=1&language=pt&format=json"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Jarvis-Local/1.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            if data.get("results") and len(data["results"]) > 0:
                primeiro = data["results"][0]
                return (
                    primeiro.get("name", nome_cidade),
                    primeiro.get("latitude"),
                    primeiro.get("longitude"),
                )
    except Exception as e:
        print(f"[ERRO GEOCODING]: {e}")
    return None


def obter_clima(cidade_solicitada=None):
    """Obtém dados meteorológicos ao vivo do Open-Meteo."""
    try:
        if cidade_solicitada:
            geo = geocodificar_cidade(cidade_solicitada)
            if geo:
                cidade, lat, lon = geo
            else:
                cidade, lat, lon = obter_cidade_ip()
        else:
            cidade, lat, lon = obter_cidade_ip()

        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&current="
            f"temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,wind_speed_10m"
            f"&timezone=auto"
        )
        req = urllib.request.Request(
            url, headers={"User-Agent": "Jarvis-Local/1.0"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())

        if "current" in data:
            cur = data["current"]
            temp = round(cur.get("temperature_2m", 0))
            sensacao = round(cur.get("apparent_temperature", temp))
            umidade = cur.get("relative_humidity_2m", 0)
            precipitacao = cur.get("precipitation", 0)
            vento = round(cur.get("wind_speed_10m", 0))
            code = cur.get("weather_code", 0)
            condicao = WMO_WEATHER_CODES.get(code, "céu parcialmente nublado")

            chuva_str = (
                "Há chuva no momento"
                if precipitacao > 0
                else "sem chuva agora"
            )

            return (
                f"Em {cidade}, a temperatura atual é de {temp}°C com sensação térmica de {sensacao}°C e {condicao}. "
                f"A umidade do ar está em {umidade}% com ventos a {vento} km/h, {chuva_str}."
            )
    except Exception as e:
        print(f"[ERRO CLIMA]: {e}")
    return None


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
