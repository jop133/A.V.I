"""Tratamento de audio: da ao TTS a 'presenca' de voz de cinema.

Voz de IA em filme nao soa como fone de ouvido -- soa como se estivesse saindo
dos alto-falantes de uma sala. Isso e processamento, nao clonagem: um reforco
nos graves, um brilho controlado e uma reverberacao curta.

Custa milissegundos e nao depende de modelo nenhum.
"""

import numpy as np

# O import do scipy.signal custa alguns segundos e precisa acontecer no carga
# do modulo, nunca dentro da funcao -- na primeira medicao isso apareceu como
# 9.8s de "processamento" que na verdade era o import.
try:
    from scipy.signal import lfilter as _lfilter
except Exception:
    _lfilter = None


def _reverb(sinal, taxa, quantidade=0.18):
    """Reverberacao curta, estilo sala pequena.

    Somamos copias atrasadas e atenuadas do sinal. Atrasos primos evitam que os
    ecos coincidam e criem aquele som metalico de 'lata'.
    """
    saida = sinal.copy()
    for atraso_ms, ganho in ((23, 0.55), (37, 0.38), (53, 0.26), (71, 0.16)):
        n = int(taxa * atraso_ms / 1000.0)
        if n >= len(sinal):
            continue
        eco = np.zeros_like(sinal)
        eco[n:] = sinal[:-n] * ganho
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

    # Normaliza para nao estourar depois de somar tudo.
    pico = float(np.max(np.abs(sinal))) or 1.0
    sinal = sinal / pico * 0.94

    return (sinal * 32767).astype(np.int16).tobytes()
