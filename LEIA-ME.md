# Jarvis local — protótipo

```
você fala → VAD → Whisper → contexto de tela → qwen3 → voz
```

**O cérebro é 100% local.** Whisper, qwen3 e a leitura de tela não saem da
máquina, não têm cota e não custam nada. Isso é o núcleo do projeto e não
depende de rede nenhuma.

**A boca, não.** Duas coisas saem daqui, e as duas são só voz:

| Peça | Para onde vai | Quando |
|---|---|---|
| Voz (Cartesia) | `api.cartesia.ai`, com chave | motor padrão hoje |
| Voz (Edge) | Microsoft, sem chave | reserva da Cartesia |

Trocando `MOTOR_VOZ` para `"piper"`, o ciclo volta a ser inteiramente offline.

Duas ferramentas consultam APIs públicas quando você pergunta por elas —
cotação (AwesomeAPI) e clima (Open-Meteo) — e mandam só o parâmetro, nunca a
sua tela.

**Configure `CIDADE_PADRAO` no `.env`.** Sem ela, perguntar o clima sem dizer
a cidade faz o Jarvis descobrir onde você está batendo no `ip-api.com`, que no
plano gratuito só atende em **HTTP puro** — sua cidade e coordenadas voltam em
texto claro pela rede. Com a cidade configurada essa chamada deixa de existir,
e de quebra a previsão fica mais rápida: as coordenadas ficam em cache, então
da segunda pergunta em diante sobra uma requisição só (medido: 1,62s na
primeira, 0,74s nas seguintes).

> **O que saiu daqui em 28/ago/2026.** Existia um caminho `[CONSULTAR:]` que
> mandava perguntas para "o Gemini" via `g4f`. Não era o Google: a `g4f` fala
> com endpoints de engenharia reversa de terceiros. E mandava junto **o texto
> da janela em foco** — email, WhatsApp Web, gerenciador de senhas, o que
> estivesse na frente. Disparava demais: medido, 4 de 6 turnos, até para
> "capital da França". Foi removido inteiro.

## Como rodar

As dependencias estao no `requirements.txt` -- so as diretas, com um
comentario dizendo por que cada uma existe. Para recriar o ambiente do zero:

```powershell
python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
```

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

## Memória entre sessões

As notas ficam em `VAULT` (`.env`), fora do projeto: arquivos `.md` comuns, que
você edita à mão ou no Obsidian — **opcional**, porque o Jarvis fala com a
pasta, não com o aplicativo.

```
vault/
  _sempre.md      ← vai no prompt de TODA conversa. curto, você cura
  jarvis/         ← única pasta onde ele escreve
```

**A busca é automática, não uma ferramenta.** Isso foi decidido medindo:

```
o modelo escolhendo a ferramenta     6/18 perguntas de recordação
busca por FTS5 na pergunta           5/6, e 10/10 ignoradas corretamente
```

"Qual é o meu monitor principal?" ia para a `ler_tela` — "monitor" soa como
tela. O índice não se confunde com isso. E como não houve **nenhum** falso
positivo em 10 perguntas comuns, não precisa nem de limiar de relevância: se o
FTS5 achou algo, entra; senão, o turno não paga nada.

**Por que FTS5 e não busca simples.** Além de ~240× mais rápida no mesmo
volume, ela ordena por relevância (BM25) e devolve **um trecho**, não a nota
inteira — e tudo que entra no prompt é pago a cada turno.

**Duas armadilhas que a medição pegou:**

O `_sempre.md` **não** entra no índice. Ele já vai no prompt sempre; buscá-lo
devolvia o que o modelo já tinha e era a causa dos únicos falsos positivos
("que horas são?" casava com ele).

E o modelo **inventava** fatos pessoais quando não havia anotação: *"sua cor
favorita é o rosa"*, sobre alguém que nunca disse isso. Uma regra explícita no
prompt levou de **2/15 para 12/15** de respostas honestas, sem perder nada na
recordação (6/6).

### Ele anota sozinho

Depois de cada 3 trocas, uma reflexão roda **em segundo plano** sobre as
últimas 12 e decide se algo mereceu virar memória. Nunca no meio de um turno:
a voz já falou, ninguém está esperando.

Ela roda em thread, e não no intervalo entre turnos, por um motivo específico:
no intervalo o microfone está fechado. Refletir ali deixaria o Jarvis surdo
por ~1s. Em thread, o pior caso é o próximo turno esperar um pouco pelo modelo.

**Calibrado medindo**, antes de ligar:

```
recall    (conversas que deviam virar nota)   6/6
precisão  (conversas que NÃO deviam)         10/10
```

A precisão é a metade que importa — uma memória cheia de "bom dia" é pior que
uma vazia. Nas 10 conversas triviais testadas (cumprimento, cor, cotação,
clima, horas, curiosidade), nenhuma virou nota.

E a lista de categorias foi calibrada: a versão curta ("preferências, decisões,
como ele trabalha") dava recall 3/6 — perdia horário de trabalho, hábitos e
nomes de pessoas próximas. Nomear as categorias explicitamente levou a 6/6 sem
custar precisão.

Tudo que ele escreve vai para `vault/jarvis/`, carimbado com data e a origem.
Você lê, corrige e apaga à vontade — é a sua pasta.

## Acompanhar a tela continuamente

Diga **"ativar leitura de tela"**. Ele passa a reamostrar a tela a cada 1,5s e
manda a leitura junto de toda pergunta. **"desativar leitura de tela"** volta
ao normal. `LEITURA_DE_TELA=on` no `.env` já sobe ligado.

Existe porque a leitura sob demanda falha em conversa encadeada: perguntada a
segunda vez ("e o que tem nela?"), o modelo não relia e preenchia as lacunas
com invenção.

**Ficar de olho é praticamente de graça** — 122 ms por amostra e **0,0% de um
núcleo** a cada 1,5s. O que custa é mandar a leitura ao modelo, e por isso o
modo é explícito e desligado por padrão:

| | desligado | ligado |
|---|---|---|
| conversa comum | 2,1s | ~3,1s |
| pergunta sobre a tela | 4,6s | **~2,5s** |
| 1º token | 0,24s | 1,42s |

Perguntas sobre a tela ficam **mais rápidas** ligado, porque some a segunda ida
ao modelo. Conversa comum fica ~1s mais lenta, porque o bloco volta a ser
prefill de todo turno — é o custo que a `ler_tela` tinha eliminado, e você
decide quando pagá-lo.

Verificado com o modo ligado: **15/15** no roteamento das ferramentas (a
ordem "pergunta antes, tela depois" segura) e **7/7** nas frases de voz que
ligam e desligam.

A HUD mostra "Acompanhando sua tela" enquanto estiver ativo, para você nunca
ficar em dúvida se ele está olhando.

## Interromper a fala

`Ctrl+Shift+Espaço` corta a fala na hora. Configurável em `ATALHO_INTERROMPER`
no `.env`; `off` desliga.

O histórico guarda **só o que você chegou a ouvir**, não a resposta que ele
pretendia dar — senão, no turno seguinte, ele acharia que disse coisas que
você nunca ouviu.

**Por que atalho e não barge-in por voz.** O caminho natural seria manter o
microfone aberto durante a fala e cortar quando você falasse por cima. Medido
nesta máquina:

```
sala em silêncio        pico RMS   142
você falando            pico RMS   263
ELE falando (retorno
dos alto-falantes)      pico RMS  1131      ← limiar de fala: 180
```

O microfone escuta os alto-falantes **mais alto que você**. Nenhum ajuste de
limiar separa os dois, então barge-in por voz faria ele se interromper sozinho
a cada frase. Com fones o problema não existe — `--doutor` mede o retorno da
sua máquina e diz o veredito.

Resolver isso de verdade com alto-falantes exige cancelamento de eco acústico:
filtro adaptativo com alinhamento de latência contra o sinal de referência. É
um projeto próprio, não um item de roteiro.

**Se a combinação estiver ocupada**, ele avisa e cai para uma reserva. Vale
saber que os candidatos "óbvios" costumam estar tomados — nesta máquina,
`ctrl+alt+space` e `ctrl+shift+j` já pertenciam a outros programas.

## Quando algo parecer quebrado, rode o doutor primeiro

```powershell
.\.venv\Scripts\python.exe jarvis.py --doutor
```

Microfone mudo, HUD travada e modelo fora do ar produzem **o mesmo sintoma**
para quem está falando: "ele não respondeu". O doutor separa isso em ~30s, em
31 checagens: dispositivo de áudio e nível captado, retorno acústico dos
alto-falantes, Ollama e tempo até o 1º token, roteamento das ferramentas,
leitura de tela, os três motores de voz, as APIs externas, o token da ponte e
as três interfaces abrindo de fato.

Cada falha vem com o conserto ao lado. `--rapido` pula as duas partes barulhentas
(o teste de eco toca som, o de interfaces abre e fecha janelas).

## Latência medida (28/ago/2026)

Do instante em que você **para de falar** até ouvir a primeira palavra dele,
com o Piper, medido em 3 turnos locais seguidos:

| Etapa | Tempo |
|---|---|
| Espera do VAD (deliberada) | 0,70s |
| Whisper | **0,00s** — roda dentro da espera acima |
| qwen3:8b até o 1º token | 0,23–0,25s |
| 1ª frase pronta + Piper | 0,07–0,18s |
| **Total** | **2,10s** (1,98–2,20s) |

Duas coisas somem da conta. O Whisper, porque acontece durante um silêncio que
já ia existir de qualquer jeito. E o contexto de tela, porque deixou de ir em
toda pergunta — virou a ferramenta `ler_tela`.

**A medição que mudou tudo.** Eu atribuía a lentidão do 1º token às ferramentas
declaradas. Errado:

| | 1º token |
|---|---|
| sem tela, sem ferramentas | 0,20s |
| sem tela, **com** ferramentas | 0,24s |
| **com tela**, sem ferramentas | 0,91s |
| com tela, com ferramentas | 1,19s |

As ferramentas ficam no prefixo, que o Ollama cacheia, e custam **+0,04s**.
Quem pagava o pedágio era o bloco `[TELA]`: ele muda a cada turno, então nunca
é cacheado, e custava **+0,95s em toda pergunta** — inclusive em "bom dia".

**O que custa mais agora.** Perguntas sobre a tela passaram de 3,9s para 4,6s,
porque exigem duas idas ao modelo: ele pede `ler_tela`, lê, e só então responde.
É a troca consciente — a maioria dos turnos não é sobre a tela.

E o efeito colateral é o melhor: **as quatro armadilhas de prompt abaixo são
todas o bloco `[TELA]`.** Fora do caminho padrão, nenhuma delas pode acontecer.
Só existe risco quando o modelo pede a tela de propósito.

Medido com 5 repetições em 6 frases sobre a tela e 4 que não são:
**30/30 pedem `ler_tela` quando devem, 20/20 não pedem quando não devem.**
Essa segunda coluna importa tanto quanto a primeira: uma ferramenta que dispara
à toa devolveria o custo que acabamos de eliminar.

`TELA_COMO_FERRAMENTA = False` no topo do `jarvis.py` volta ao comportamento
antigo.

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
significa decidir o que é fala antes de ver o texto inteiro. O
`SeparadorDeFalas` segura o começo enquanto houver um `[` sem `]`: até fechar
o colchete não dá para saber se aquilo é tag ou texto. Sem essa trava o Jarvis
leria as próprias tags em voz alta. Vazamentos do bloco de tela (`[TELA]`,
`[CURSOR]`) têm a **linha inteira** descartada, não só a tag — senão sobraria
"Janela ativa: Code" para ser falado.

Uma tag cortada no meio pelo `num_predict` (`"[CONSU"`) também é descartada:
falar o começo de uma tag é pior que perder o pedaço.

## As ações são ferramentas, não substrings

As cinco coisas que o Jarvis sabe *fazer* — mudar tema, ajustar brilho,
alternar interface, cotação e clima — são declaradas ao qwen3 como ferramentas,
e ele escolhe por intenção.

Antes eram detectadas por substring **antes de o modelo ver a pergunta**, e
isso errava nos dois sentidos:

```
"quanto TEMPO falta pro jogo?"   ->  respondia a previsão do tempo
"não gosto de AZUL"              ->  trocava o tema da interface
```

Não era um caso raro: "tempo" é uma das palavras mais comuns do idioma, e o
gatilho estava em `ferramentas.py`. Medido no ciclo real com ferramentas: **15
de 16 casos corretos**, incluindo todos os que a versão por substring errava.

Havia também duas fontes de verdade para cor — uma por substring, outra pela
tag `[COR:]` que o próprio modelo emitia — com regras de casamento diferentes.
Agora é uma só, o schema.

**Todo argumento é validado antes de agir.** O modelo pode inventar valor fora
do `enum`, e é melhor dizer que não entendeu do que executar errado:

```
{"cor": "turquesa"}    ->  "Não conheço a cor turquesa, senhor."
{"moeda": "dogecoin"}  ->  "Não acompanho dogecoin, senhor."
{"cidade": "sua cidade"}  ->  tratado como "cidade não informada"
```

O último é real: o modelo às vezes preenche a cidade com um placeholder
inventado em vez de omitir o campo. Sem o filtro, o geocoding sairia procurando
uma cidade chamada "sua cidade".

`USAR_FERRAMENTAS = False` volta aos interceptores por substring e ao prompt
antigo (`SISTEMA_LEGADO`). Os dois continuam no código para isso.

## Quatro armadilhas de PROMPT que quebraram o comportamento

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

**3. O bloco de tela desligava as ferramentas.**
Colar o contexto de tela **antes** da pergunta fazia o modelo parar de chamar
as ferramentas: a pergunta ficava enterrada embaixo de um muro de dados de
sistema. Medido, só invertendo a ordem:

```
[DADOS DO SISTEMA]... + pergunta   ->  6 de 8 corretos
pergunta + [DADOS DO SISTEMA]...   ->  8 de 8 corretos
```

Pior: o turno que falhava virava texto no histórico ("Mudando o tema para
vermelho"), e o modelo passava a **imitar a si mesmo** nos turnos seguintes.
Um turno ruim contaminava os próximos em cascata — 6 de 12 falhando numa
conversa contínua contra 1 de 12 depois da inversão.

É a terceira vez que o bloco `[TELA]` muda o comportamento do modelo muito
além de "dar contexto". Se algo estranho começar a acontecer, suspeite dele.

**4. O Jarvis lia a própria HUD — e parava de agir.**
Pedir "modo orbe" às vezes só recebia uma confirmação falada, sem a interface
mudar. Ele não executava: **narrava** que tinha executado. Medido, 15
repetições por contexto:

```
janela em foco = HUD do Jarvis     3/15 executaram a ferramenta
qualquer outra janela             15/15 executaram
```

O texto narrado entregou o mecanismo: *"Modo Orbe **já está** ativado, senhor."*
A HUD mostra na legenda a última fala dele; com ela em foco, isso entra no
bloco `[TELA]` e o modelo lê a própria fala como estado do mundo.

E acontecia na hora errada: depois de trocar de modo, a interface é trazida
para a frente (`SetForegroundWindow`), então o comando **seguinte** caía
exatamente nesse caso. Por isso funcionava "às vezes".

É a armadilha nº 2 de novo, um nível acima: `e_o_proprio_console()` só
detectava o console. Agora `e_a_propria_interface()` reconhece a HUD, o orbe e
as bordas pelo título. E o prompt ganhou uma regra explícita: *nunca diga que
executou uma ação; para agir, use a ferramenta.* Cada uma resolve sozinha; as
duas juntas dão 48 de 48.

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
5. **Os 439 tokens de schema em toda pergunta** — hoje as cinco ferramentas
   são enviadas mesmo quando a pergunta é "bom dia". Um filtro permissivo, que
   só decidisse *se* vale anexar os schemas (nunca *qual* chamar, que continua
   sendo do modelo), devolveria os 0,33s na maioria dos turnos. O risco é o
   filtro esconder uma ferramenta de uma frase que precisava dela.

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
