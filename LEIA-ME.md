# Jarvis local — protótipo

```
você fala → VAD → Whisper → contexto de tela → qwen3 → voz
```

**O cérebro é 100% local.** Whisper, qwen3 e a leitura de tela não saem da
máquina, não têm cota e não custam nada. Isso é o núcleo do projeto e não
depende de rede nenhuma.

**A boca e a pesquisa, não.** Três coisas saem daqui, e vale saber quais:

| Peça | Para onde vai | Quando |
|---|---|---|
| Voz (Cartesia) | `api.cartesia.ai`, com chave | motor padrão hoje |
| Voz (Edge) | Microsoft, sem chave | reserva da Cartesia |
| `[CONSULTAR:]` | endpoints de terceiros via `g4f` | perguntas que o qwen3 delega |

O terceiro merece atenção: `consultar_gemini_web()` manda junto o **texto da
janela em foco**. Se for seu email ou seu gerenciador de senhas, vai junto.
Trocando `MOTOR_VOZ` para `"piper"` e não usando o `[CONSULTAR:]`, o ciclo
volta a ser inteiramente offline.

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

Do instante em que você **para de falar** até ouvir a primeira palavra dele,
com o Piper, medido em 3 turnos locais seguidos:

| Etapa | Tempo |
|---|---|
| Espera do VAD (deliberada) | 0,70s |
| Whisper | **0,00s** — roda dentro da espera acima |
| Contexto de tela (UI Automation) | 0,10s |
| qwen3:8b até o 1º token | 1,37–1,64s |
| 1ª frase pronta + Piper | 0,07–0,18s |
| **Total** | **3,05s** (2,92–3,10s) |

O ganho maior não é a média — é a **consistência**: a variação ficou em
**0,18s**. A voz não espera mais a resposta inteira, e o Whisper não aparece
na conta porque acontece durante um silêncio que já ia existir de qualquer
jeito.

Referência: o Gemini na nuvem entregou 0,75s — mas com picos de 47s e cota.

> **Aviso de honestidade.** Uma versão anterior deste arquivo anunciava 3,43s
> e descrevia as três otimizações abaixo como "estão no código". Elas não
> estavam — em lugar nenhum, nem nos backups. Foram reimplementadas em
> 28/ago/2026 e os números acima foram medidos de novo, com o código atual.
> Se você mexer no ciclo, meça de novo antes de editar esta tabela.

## Três otimizações que estão no código

**1. Transcrição sobreposta ao silêncio do VAD.**
O VAD espera 0,7s de silêncio antes de fechar o turno. Esse tempo era ocioso.
Agora a transcrição dispara assim que sua voz cai e roda *durante* a espera.
Sem perda de precisão: o que vem depois do disparo é silêncio, então o trecho
enviado ao Whisper já contém a fala inteira.

Medido com microfone simulado (2,60s de fala + 1,40s de silêncio):
**5,67s → 4,13s até ter o texto em mãos, 1,53s a menos.**

Dois detalhes que o teste cobriu: o disparo espera 0,25s antes de começar,
porque o RMS é média do bloco e cai um pouco *antes* de a palavra terminar —
sem essa margem o rabo da última palavra some. E se você só pausou e volta a
falar, o resultado adiantado é descartado.

**2. `/api/chat` com histórico limpo, em vez de `/api/generate` com `context`.**
Passando `context`, o Ollama reprocessava a conversa inteira a cada turno —
medido: 0,78s no turno 1, **2,16s no turno 5, crescendo sem parar**. Com
`messages` e o bloco de tela apenas na pergunta atual:

**turno 1 = 0,50s → turno 6 = 0,84s, e estabiliza** (o histórico é cortado
nas últimas 3 trocas).

**3. A voz emenda no modelo, frase a frase.**
Antes esperávamos a resposta completa para sintetizar. Numa resposta longa isso
custava **2,37s parados**. Agora a primeira frase já vai sendo falada enquanto o
modelo escreve o resto.

Medido com o Piper, que é o motor **mais rápido** (0,10s/frase):
**1º áudio em 0,60s → 0,09s, 83% menos.** Com Edge ou Cartesia, onde cada
frase custa uma viagem de rede, o ganho é bem maior.

No ciclo completo isso fica visível no relatório de etapas: a marca
`Voz (1o audio)` passa a aparecer **antes** de `qwen3 (resposta completa)`.

`VOZ_STREAMING = False` no topo do `jarvis.py` volta ao comportamento antigo.

**Uma armadilha que essa otimização criou.** Falar antes de a resposta acabar
significa falar antes de saber se ela era uma tag. O `SeparadorDeFalas`
segura o começo até ter certeza: se vier `[CONSULTAR:`, nada é falado — quem
responde é o caminho web. Sem essa trava o Jarvis leria a própria tag em voz
alta. Vale para `[COR:]`, `[BRILHO:]` e para vazamentos do bloco de tela, onde
o descarte é da **linha inteira**, não só da tag.

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

**3. `keep_alive` vale por requisição, não por sessão.**
`OLLAMA_KEEP_ALIVE=-1` no ambiente ajuda, mas o pré-aquecimento mandava
`keep_alive: -1` e as chamadas seguintes não mandavam nada — então voltavam ao
padrão de 5 minutos e o modelo saía da VRAM em conversa espaçada. Agora **toda**
requisição manda `keep_alive: -1`.

**4. A árvore de acessibilidade do Chromium precisa ser "acordada".**
Apps Electron (VS Code, Discord, navegadores) devolvem uma árvore pobre na
primeira consulta e completa na segunda. Por isso `percepcao.contexto()` é
chamado uma vez no boot.

## Onde ainda dá para ganhar

Com o Whisper escondido dentro da espera do VAD, o gargalo mudou de lugar: o
**qwen3 até o 1º token agora é 1,37–1,64s dos 3,05s** — metade do total. O
resto se divide entre a espera do VAD (0,70s, deliberada) e migalhas.

1. **O 1º token do qwen3** — é o alvo agora. O prompt de sistema cresceu
   muito (personalidade + tags de cor + brilho + roteamento web), e tudo isso
   é lido antes do primeiro token sair. Encolher o prompt encolhe esse tempo.
2. **Transcrição incremental de verdade** — a sobreposição já aproveita os
   0,70s do VAD, mas transcrever em pedaços *durante* a fala aproveitaria
   também o tempo em que você está falando. Custo: o Whisper erra mais nas
   emendas. Ganho menor agora do que era antes, já que o Whisper saiu da conta.
3. **Whisper `base` em vez de `small`** — 0,62s contra 1,64s, mas o acerto cai
   de 84% para 71%. Depois da sobreposição isso deixou de compensar: o tempo
   que economizaria já está escondido na espera do VAD.
4. **Respostas mais curtas** — o qwen3 é verboso apesar do prompt pedir brevidade.
   Isso não muda o tempo até a primeira palavra, mas muda o tempo até ele calar.
5. **A regra do `[CONSULTAR:]` dispara cedo demais** — medido: ele delega para
   a web até "capital da França", que responde sozinho em 0,5s. Cada delegação
   indevida custa segundos e manda o texto da sua tela para terceiros.

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

## A HUD exige um token

O `hud_bridge` sobe um servidor SSE em `127.0.0.1:8765` para falar com a
interface. Escutar em localhost **não** é proteção: qualquer site aberto no
seu navegador consegue abrir um `EventSource` para lá. Enquanto a ponte
respondia com `Access-Control-Allow-Origin: *`, uma página qualquer podia ler
em tempo real tudo que você fala e todas as janelas que você usa.

Restringir a origem não resolveria — uma página consegue origem `null` por
iframe sandbox. O que resolve é um segredo que ela não tem como adivinhar:

- a cada boot, o `hud_bridge` sorteia um token e grava em `.hud_token`
  (no `.gitignore`, junto do `.env`);
- `/events` exige `?token=` e devolve **403 sem nenhum header de CORS** para
  quem não tiver;
- a HUD do navegador recebe o token pela URL; as interfaces Tk leem o arquivo.

**Consequência prática:** abrir `abrir_orbe.bat` ou `abrir_bordas.bat` com o
Jarvis desligado agora mostra a interface desconectada, porque não existe
`.hud_token`. É o comportamento correto — sem o Jarvis rodando não há nada
para receber.

## O cache de voz guarda a taxa no nome

Os `.pcm` em `vozes/cache/` seguem o formato `{hash}.{taxa}.pcm`. A taxa
precisa viajar junto porque os motores não concordam: o Piper gera a
**22.050 Hz** e Cartesia e Edge a **24.000 Hz**.

Antes o arquivo era só `{hash}.pcm` e a leitura assumia 24.000 sempre —
então toda fala do Piper vinda do cache tocava **8,8% acelerada e mais
aguda**, justamente no motor que atende quando a internet cai.

Arquivos do formato antigo continuam valendo para Cartesia e Edge. Para o
Piper eles são ignorados: ressintetizar custa 0,10s e nenhum crédito, então
não vale o risco de tocar um arquivo de taxa desconhecida.

## Por que não há modelo de visão aqui

Um VLM na RX 6600 levaria vários segundos só para "olhar" e leria interface
pequena mal. A UI Automation entrega o mesmo conteúdo em **texto exato, em
114 ms, de graça** — e acerta a posição do cursor por construção, coisa que o
Gemini acertava em 2 de 5 tentativas.

Limitação honesta: jogos não expõem árvore de acessibilidade. Para eles seria
preciso OCR local (`onnxruntime` já está instalado).
