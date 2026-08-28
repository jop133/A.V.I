# Jarvis local — protótipo 100% offline

Nenhuma peça sai da sua máquina. Sem API, sem cota, sem custo.

```
você fala → VAD → Whisper → contexto de tela → qwen3 → Piper → voz
```

## Como rodar

```powershell
cd C:\Users\User\Desktop\jarvis-local

# com fala sintética (não precisa do microfone) — bom para medir
.\.venv\Scripts\python.exe jarvis.py --simulado

# com o microfone de verdade
.\.venv\Scripts\python.exe jarvis.py
```

Só a leitura de tela, isolada:

```powershell
.\.venv\Scripts\python.exe percepcao.py
```

## Latência medida (28/ago/2026)

Do instante em que você **para de falar** até ouvir a primeira palavra dele:

| Etapa | Tempo |
|---|---|
| VAD + Whisper (transcrição sobreposta) | 1,95s |
| Contexto de tela (UI Automation) | 0,10s |
| qwen3:8b até o 1º token | 0,78–1,03s |
| 1ª frase pronta + Piper | 0,27–0,66s |
| **Total** | **3,43s** (3,08–3,62s) |

Antes das otimizações: **4,69s de média, variando de 3,4s a 6,6s**. O ganho
maior nem foi a média — foi a **consistência**: a variação caiu de 3,2s para
0,5s, porque a voz não espera mais a resposta inteira ficar pronta.

Referência: o Gemini na nuvem entregou 0,75s — mas com picos de 47s e cota.

## Três otimizações que estão no código

**1. Transcrição sobreposta ao silêncio do VAD.**
O VAD espera 0,8s de silêncio antes de fechar o turno. Esse tempo era ocioso.
Agora a transcrição dispara assim que sua voz cai e roda *durante* a espera.
Sem perda de precisão: o Whisper recebe o áudio inteiro, só começa antes.

**2. `/api/chat` com histórico limpo, em vez de `/api/generate` com `context`.**
Passando `context`, o Ollama reprocessava a conversa inteira a cada turno —
medido: 0,78s no turno 1, **2,16s no turno 5, crescendo sem parar**. Com
`messages` e o bloco de tela apenas na pergunta atual, estabiliza em ~1s.

**3. A voz emenda no modelo, frase a frase.**
Antes esperávamos a resposta completa para sintetizar. Numa resposta longa isso
custava **2,37s parados**. Agora a primeira frase já vai sendo falada enquanto o
modelo escreve o resto.

## Duas armadilhas de PROMPT que quebraram o comportamento

**1. Regra anti-alucinação ampla demais.**
O prompt dizia *"se a resposta não estiver no contexto, diga que não sabe"*.
A intenção era evitar invenção sobre a tela — mas o modelo generalizou e passou
a recusar TUDO. Medido:

```
sem bloco [TELA]:  "capital da França?" -> 'Paris.'
com bloco [TELA]:  "capital da França?" -> 'Não sei.'
```

A regra agora é escopada: o bloco `[TELA]` só vale para perguntas sobre a tela;
para o resto ele usa o próprio conhecimento.

**2. O Jarvis lia o próprio terminal.**
Iniciado pelo `.bat`, a janela em foco é o console dele mesmo — e o banner diz
"100% offline". O contexto vinha cheio das próprias mensagens e ele passava a
comentar o próprio log ("Ollama já está rodando"). Agora `percepcao.py` detecta
o próprio console (`GetConsoleWindow`) e devolve um contexto vazio.

## Detalhes que custam caro se esquecidos

**1. `num_ctx` precisa ser idêntico entre o pré-aquecimento e o uso.**
Se mudar, o Ollama recarrega o modelo inteiro — 18 segundos. Medido:

```
num_ctx=4096 -> 18.177ms   (recarrega)
num_ctx=8192 -> 17.448ms   (recarrega, mudou)
num_ctx=8192 ->     90ms   (bate, já carregado)
```

**2. `think: false` no qwen3.** Com o modo pensante ligado o tempo até o
primeiro token vai de 0,43s para 3,14s, e respostas curtas voltam vazias.

**3. `OLLAMA_KEEP_ALIVE=-1`** (já configurado) para o modelo não sair da VRAM.

**4. A árvore de acessibilidade do Chromium precisa ser "acordada".**
Apps Electron (VS Code, Discord, navegadores) devolvem uma árvore pobre na
primeira consulta e completa na segunda. Por isso `percepcao.contexto()` é
chamado uma vez no boot.

## Onde ainda dá para ganhar

O VAD + Whisper são **1,95s dos 3,43s** — mais da metade. Desses, 0,8s é a
espera deliberada do VAD (baixar isso corta quem fala pausado) e ~1,15s é o
que sobra da transcrição.

1. **Transcrição incremental de verdade** — hoje a sobreposição só aproveita os
   0,8s do VAD. Transcrever em pedaços *durante* a fala aproveitaria também o
   tempo em que você está falando. Custo: o Whisper erra mais nas emendas.
2. **Whisper `base` em vez de `small`** — 0,62s contra 1,64s, mas o acerto cai
   de 84% para 71%. Provavelmente não compensa.
3. **Respostas mais curtas** — o qwen3 é verboso apesar do prompt pedir brevidade.
   Isso não muda o tempo até a primeira palavra, mas muda o tempo até ele calar.

## Trocando a voz

No topo do `jarvis.py`:

```python
MOTOR_VOZ  = "edge"                            # "edge", "piper" ou "kokoro"
VOZ_EDGE   = "en-AU-WilliamMultilingualNeural"
TOM_EDGE   = "-15Hz"                           # grave = mais imponente
RITMO_EDGE = "-5%"                             # levemente pausado

SALA_REVERB     = 0.48    # 0 = seco | 0.32 = sala | 0.48 = sala grande
SALA_GRAVES     = 1.45    # 1.0 = sem reforço
SALA_COMPRESSAO = True
```

### Motor Cartesia (opcional, exige chave)

A Cartesia tem latência de modelo muito menor (~75–90 ms contra ~1.200 ms do
Edge). Camada gratuita: 20 mil créditos/mês. Para ativar:

**1.** Crie a chave em `play.cartesia.ai` → API Keys

**2.** Copie `.env.exemplo` para `.env` e preencha:

```
CARTESIA_API_KEY=sk_car_...
```

**3.** Descubra as vozes em português e ouça as amostras:

```powershell
.\.venv\Scripts\python.exe listar_vozes_cartesia.py
```

**4.** Ponha o ID escolhido no `.env` e troque o motor:

```
CARTESIA_VOICE_ID=<id da voz>
```
```python
MOTOR_VOZ = "cartesia"     # no topo do jarvis.py
```

O `.env` está no `.gitignore` — a chave nunca vai para o repositório.

### Cadeia de reserva

```
cartesia  →  edge  →  piper
```

Cada degrau só é tentado se o anterior falhar, e o Piper é local: **mesmo sem
internet o Jarvis continua falando.** Testado forçando falha em cada nível.

Detalhe que custou um bug: quando o Edge é a *reserva*, ele não pode usar o
`voz_nome` do motor principal (um UUID da Cartesia não é nome de voz válido no
Edge). O `_edge_pcm` recebe a voz explicitamente por isso.

### Tratamento de áudio (`presenca.py`)

Voz de IA em filme não soa como fone de ouvido — soa como se viesse dos
alto-falantes de uma sala. Isso é **processamento, não clonagem**: reforço de
graves, compressão suave e reverberação curta.

Custo medido: **0,001s por frase — 0,1% do total.** É gratuito na prática.

Para experimentar outras combinações de voz, tom, ritmo e sala:

```powershell
.\.venv\Scripts\python.exe afinar_jarvis.py
```

Edite a lista `COMBINACOES` no topo do arquivo. Os `.wav` saem em
`vozes/amostras/afinar_*.wav`.

### Por que não clonar uma voz específica

Clonadores (XTTS, Fish Speech, OpenVoice, RVC) todos exigem PyTorch, que não
roda com ROCm no Windows — esta máquina não treina nem executa nenhum deles.
Os números que o Fish Speech publica (RTF 0,195) são numa NVIDIA H200.

E vale lembrar: a voz do J.A.R.V.I.S. dos filmes é do ator Paul Bettany. O
personagem é fictício, a voz é de uma pessoa real.

### Os três motores, medidos nesta máquina (por frase curta)

| Motor | Mediana | Pior caso | Onde roda | Sem internet |
|---|---|---|---|---|
| **Piper** | **0,10s** | 0,17s | local | funciona |
| Kokoro | 0,54s | — | local | funciona |
| **Edge** | **1,26s** | **2,05s** | Microsoft | cai para o Piper |

O Edge é **grátis e sem chave de API**, com qualidade e pronúncia neurais muito
acima dos locais — em troca custa ~1,2s por fala e depende da rede. O ciclo
completo vai de **~3,4s (Piper) para ~4,3–6,3s (Edge)**.

Repare no *pior caso*: o Edge varia (0,95s a 2,05s para frases parecidas),
porque é viagem de rede. O Piper é sempre o mesmo.

### O que muda ao trocar Piper → Edge

Não é só um arquivo de voz — **é outro motor**:

| | Piper | Edge |
|---|---|---|
| A "voz" é | arquivo `.onnx` de 63 MB no disco | uma requisição; não há arquivo |
| Saída | PCM direto | MP3 (decodificado, custa 0,002s) |
| Taxa | 22.050 Hz | 24.000 Hz |

**O que NÃO muda:** Whisper, qwen3 e a leitura de tela continuam 100% locais.
Só a boca vai para a nuvem.

### Reserva automática

Se o Edge falhar (rede fora, serviço instável), o `jarvis.py` cai sozinho para
o Piper local e avisa no terminal. Ele nunca fica mudo.

### Vozes do Edge

Multilíngues (falam português com timbre de outro idioma) — some
`MultilingualNeural` ao final: `en-AU-William`, `en-US-Andrew`, `en-US-Brian`,
`it-IT-Giuseppe`, `fr-FR-Remy`, `de-DE-Florian`, `ko-KR-Hyunsu`.
Nativas: `pt-BR-AntonioNeural`, `pt-BR-FranciscaNeural`.

Para ouvir todas e comparar:

```powershell
.\.venv\Scripts\python.exe comparar_edge.py    # as vozes
.\.venv\Scripts\python.exe ajustar_voz.py      # tom e ritmo da escolhida
```

### Duas otimizações que o motor de rede exigiu

**Síntese adiantada.** Enquanto uma frase toca, a próxima já está sendo
preparada. Sem isso, cada frase pagava ~1,3s de rede em silêncio — medido,
11,7s de pausas numa resposta longa.

**Primeira fala cortada curta.** O custo do Edge cresce com o tamanho do texto:
uma primeira frase de ~100 caracteres custou 3,90s contra 1,18s de uma curta.
Agora ela é quebrada numa vírgula se passar de 70 caracteres.

## Por que não há modelo de visão aqui

Um VLM na RX 6600 levaria vários segundos só para "olhar" e leria interface
pequena mal. A UI Automation entrega o mesmo conteúdo em **texto exato, em
114 ms, de graça** — e acerta a posição do cursor por construção, coisa que o
Gemini acertava em 2 de 5 tentativas.

Limitação honesta: jogos não expõem árvore de acessibilidade. Para eles seria
preciso OCR local (`onnxruntime` já está instalado).
