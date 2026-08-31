"""Reflexão: decidir sozinho o que da conversa merece virar memória.

Roda **depois** de a voz já ter falado, numa thread de fundo, enquanto o
usuário está calado. Nunca no meio de um turno: ninguém espera por ela.

Olha uma JANELA de trocas, não o último turno. Uma conversa longa só faz
sentido inteira -- pedaço a pedaço, cada parte parece banal e nada seria
guardado. Por isso existe uma transcrição separada do histórico: o histórico
são 3 trocas porque é o que vai ao modelo a cada turno e é pago; a transcrição
guarda 30 e não custa nada, porque só a reflexão a lê.
"""

import re

# Quantas trocas a reflexão enxerga e de quantas em quantas ela roda.
JANELA = 12
A_CADA = 3

# Esta lista foi calibrada medindo. A versao curta ("preferencias, decisoes,
# como ele trabalha") dava recall 3/6: perdia horario de trabalho, habitos e
# nomes de pessoas proximas. Nomear as categorias levou a 6/6 SEM custar
# precisao, que ficou em 10/10 nas duas.
INSTRUCAO = """Voce analisa uma conversa e decide se algo dela merece ser guardado na memoria de longo prazo sobre o usuario.

GUARDE fatos duraveis: preferencias e manias dele, ROTINAS e HORARIOS, decisoes tomadas, como ele trabalha, detalhes dos projetos dele, nomes e datas de pessoas proximas, regras que ele estabeleceu, algo que ele pediu para lembrar, conclusoes de uma conversa longa.

NAO GUARDE: cumprimentos, despedidas, comandos de interface (cor, brilho, modo), perguntas factuais de conhecimento geral, cotacao, clima, horas, conversa fiada, nem o que o proprio assistente disse sobre si.

Na duvida, NAO guarde. Uma memoria cheia de trivialidade e pior que uma vazia.

Responda em UMA linha, em um destes dois formatos exatos:
ANOTAR: <assunto em 1 a 3 palavras> | <o fato em uma frase curta>
NADA"""

_PADRAO = re.compile(r"ANOTAR\s*:\s*(.{1,60}?)\s*\|\s*(.+)", re.IGNORECASE | re.DOTALL)


def formatar(transcricao, janela=JANELA):
    """Últimas trocas, como texto para a reflexão ler."""
    recentes = list(transcricao)[-janela:]
    linhas = []
    for papel, texto in recentes:
        quem = "SENHOR" if papel == "user" else "JARVIS"
        linhas.append("%s: %s" % (quem, " ".join((texto or "").split())))
    return "\n".join(linhas)


def decidir(transcricao, chamar_modelo, janela=JANELA):
    """Devolve (assunto, fato) se algo merecer memória, ou None.

    `chamar_modelo(sistema, usuario) -> str` fica de fora de proposito: e o que
    permite medir precisao e recall desta funcao sem subir o Jarvis inteiro.
    """
    conversa = formatar(transcricao, janela)
    if not conversa.strip():
        return None
    try:
        resposta = chamar_modelo(INSTRUCAO, "Conversa:\n" + conversa) or ""
    except Exception as e:
        print("  [Reflexao] falhou: %r" % (e,))
        return None

    resposta = resposta.strip()
    if resposta.upper().startswith("NADA"):
        return None
    m = _PADRAO.search(resposta)
    if not m:
        return None

    assunto = " ".join(m.group(1).split())[:60]
    fato = " ".join(m.group(2).split())[:300]
    # "ANOTAR: nada | nada" e outras variacoes de recusa mal formatada.
    if not assunto or not fato or fato.lower().startswith("nada"):
        return None
    return assunto, fato
