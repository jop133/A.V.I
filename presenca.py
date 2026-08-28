"""Tratamento de audio: da ao TTS a 'presenca' de voz de cinema.

Voz de IA em filme nao soa como fone de ouvido -- soa como se estivesse saindo
dos alto-falantes de uma sala. Isso e processamento, nao clonagem: um reforco
nos graves, um brilho controlado e uma reverberacao curta.

Custa milissegundos e nao depende de modelo nenhum.
"""

import numpy as np

# Ganho de saida fixo. Vale para TODOS os blocos, e e o que mantem o volume
# estavel entre frases quando a voz sai em pedacos.
#
# Calibrado medindo 5 frases de intensidades diferentes no Piper. O valor
# compensa a perda de volume de trocar normalizacao por ganho fixo:
#
#   ganho   pico medio   pico maximo   amostras limitadas
#   0.94       0.675        0.728            0.00%
#   1.20       0.852        0.903            0.01%   <- escolhido
#   1.45       0.914        0.922            0.34%
#
# O codigo antigo entregava 0.940 em TODA frase; 1.20 chega perto disso
# (-0,85 dB, imperceptivel) sem achatar a diferenca entre as frases.
GANHO_SAIDA = 1.20

# O import do scipy.signal custa alguns segundos e precisa acontecer no carga
# do modulo, nunca dentro da funcao -- na primeira medicao isso apareceu como
# 9.8s de "processamento" que na verdade era o import.
try:
    from scipy.signal import lfilter as _lfilter
except Exception:
    _lfilter = None


def _reverb(sinal, taxa, quantidade=0.18, cauda_ms=120):
    """Reverberacao curta, estilo sala pequena.

    Somamos copias atrasadas e atenuadas do sinal. Atrasos primos evitam que os
    ecos coincidam e criem aquele som metalico de 'lata'.

    O bloco e estendido por `cauda_ms` de silencio ANTES de somar os ecos. Sem
    isso o ultimo eco e cortado na borda do bloco: a sala some de repente em
    vez de decair. Com a voz saindo frase a frase esse corte acontece a cada
    frase, e o resultado soa picotado.
    """
    n_cauda = int(taxa * cauda_ms / 1000.0)
    base = np.concatenate([sinal, np.zeros(n_cauda, dtype=sinal.dtype)])

    saida = base.copy()
    for atraso_ms, ganho in ((23, 0.55), (37, 0.38), (53, 0.26), (71, 0.16)):
        n = int(taxa * atraso_ms / 1000.0)
        if n >= len(base):
            continue
        eco = np.zeros_like(base)
        eco[n:] = base[:-n] * ganho
        saida += eco * quantidade
    return saida


def _realce_graves(sinal, taxa, ganho=1.35, corte=220.0):
    """Reforca as frequencias baixas -- e o que da 'peito' a voz.

    Filtro passa-baixa de um polo: isola a parte grave e a soma de volta
    amplificada. Com scipy usa lfilter (vetorizado); sem ele, um laco numpy.
    """
    alfa = float(np.exp(-2.0 * np.pi * corte / taxa))

    if _lfilter is not None:
        graves = _lfilter([1 - alfa], [1, -alfa], sinal)
    else:
        graves = np.zeros_like(sinal)
        anterior = 0.0
        for i in range(len(sinal)):
            anterior = (1 - alfa) * sinal[i] + alfa * anterior
            graves[i] = anterior

    return sinal + graves * (ganho - 1.0)


def _limitar(sinal, teto=0.90):
    """Limitador de joelho suave: segura so os picos, sem mexer no corpo.

    Substitui a normalizacao por bloco. Um limitador olha para o pico
    ABSOLUTO (teto fixo); a normalizacao olhava para o pico RELATIVO daquele
    bloco, o que faz cada bloco terminar no mesmo volume independente de quao
    alto ele era de fato.
    """
    magnitude = np.abs(sinal)
    acima = magnitude > teto
    if not acima.any():
        return sinal
    saida = sinal.copy()
    excedente = magnitude[acima] - teto
    # tanh comprime o excedente para dentro da margem restante, sem corte duro.
    saida[acima] = np.sign(sinal[acima]) * (teto + np.tanh(excedente) * (1.0 - teto))
    return saida


def _comprimir(sinal, limiar=0.35, razao=2.5):
    """Compressao suave: aproxima os picos dos vales.

    Voz comprimida soa mais 'presente' e constante -- e o tratamento padrao de
    locucao. Sem isso, as silabas fortes estouram e as fracas somem.
    """
    magnitude = np.abs(sinal)
    acima = magnitude > limiar
    ganho = np.ones_like(sinal)
    ganho[acima] = (limiar + (magnitude[acima] - limiar) / razao) / magnitude[acima]
    return sinal * ganho


def tratar(pcm_int16, taxa, reverb=0.18, graves=1.35, compressao=True):
    """Aplica o tratamento a um bloco de PCM 16 bits mono.

    Devolve PCM 16 bits. Passe reverb=0 e graves=1.0 para desligar.
    """
    if not pcm_int16:
        return pcm_int16

    sinal = np.frombuffer(pcm_int16, dtype=np.int16).astype(np.float32) / 32768.0

    if graves and graves != 1.0:
        sinal = _realce_graves(sinal, taxa, graves)

    if compressao:
        sinal = _comprimir(sinal)

    if reverb:
        sinal = _reverb(sinal, taxa, reverb)

    # Ganho FIXO, nao normalizacao. A normalizacao por bloco levava todo bloco
    # ao mesmo pico: numa fala unica isso passa despercebido, mas com a voz
    # saindo frase a frase cada frase vira um bloco e o volume pulsa -- um
    # sussurro e um grito sairiam no mesmo nivel. O limitador abaixo segura os
    # picos sem achatar a diferenca entre as frases.
    sinal = _limitar(sinal * GANHO_SAIDA)

    return (sinal * 32767).astype(np.int16).tobytes()
