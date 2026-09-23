# RAGX Painel

Painel desktop (Electron) para o RAGX. Mostra os projetos registrados no hub
(`~/.ragx/hub/registry.json`), o estado de cada índice, a fila de tarefas em
andamento e o estado das três conexões de que o RAGX depende (CLI, Claude
Code, Ollama). Roda 100% local: sem login, sem telemetria enviada para fora
da máquina, só leitura de arquivos locais e execução do CLI `ragx` já
instalado no sistema. Tema sempre escuro; título da janela "RAGX Painel".

## Telas

- **Projetos**: grade de cards, um por projeto do hub. Cada card mostra o
  selo de estado ("Atualizado", "Defasado", "Embeddings faltando", "Sem
  hooks", "Com problema", "Pasta ausente" ou "Indexando…"), a pasta, a
  branch atual (com aviso quando o índice é de outra branch), há quanto
  tempo foi indexado, a cobertura de embeddings e um botão que faz o que o
  estado pede. Um filtro segmentado separa "Todos", "Defasados" e "Com
  problema"; a busca no topo ignora maiúsculas e acentos. "Adicionar
  projeto" pede uma pasta, lista os projetos do RAGX encontrados dentro
  dela e instala os hooks de git por padrão.
- **Detalhe do projeto**: responde "o índice está em dia?" com os motivos
  exatos de `ragx status --json` e mostra a linha do tempo das últimas 10
  indexações (quando, quem disparou, o modo, a branch e o commit). Também
  traz os números do índice com a cobertura de embeddings, o interruptor
  dos hooks de git, os botões "Atualizar agora", "Gerar embeddings
  faltantes" e "Reindexar do zero" (com segundo clique), as ações que
  alteram `knowledge/` versionado (sincronizar, reconstruir grafo, gerar
  dicionário), o uso pelos agentes nas últimas 24 horas, a economia
  estimada sob demanda (`ragx trial`), os achados de segurança sob demanda
  (`ragx security scan`) e "Remover do hub" (com segundo clique; nada é
  apagado no disco).
- **Conexões**: três cards (RAGX CLI, Claude Code e Ollama), cada
  um com o selo "Conectado", "Atenção" ou "Não conectado", os fatos da
  checagem e as correções de um clique ("Registrar para todos os
  projetos", "Iniciar container", "Baixar nomic-embed-text"). O card do
  Ollama mostra o modo (Docker ou local), o processador (GPU ou CPU) e a
  velocidade em chunks/s (ver "Ollama: Docker ou local"). O painel
  confere as três a cada 30 segundos, na hora com "Verificar agora" e logo
  depois que uma correção termina.
- **Como funciona**: repete a explicação do primeiro passo da configuração
  inicial e permite refazê-la.
- **Configuração inicial (onboarding)**: tela cheia, sem barra lateral, com
  quatro passos (como o RAGX funciona, conexões, escolher os projetos,
  indexar). Aparece na primeira abertura ou quando o hub está vazio;
  "Começar" enfileira a indexação dos projetos marcados, "Pular
  configuração" só marca o onboarding como feito.

Uma barra superior comum às telas (exceto onboarding) traz a busca de
projeto, o indicador da fila ("2 tarefas", com progresso, previsão e botão
"Cancelar" por tarefa) e um ponto de saúde das conexões em texto, nunca só
pela cor.

## Rodando em desenvolvimento

```bash
npm install
npm run dev:electron   # Vite (renderer) + Electron com hot reload
```

## Testes e checagens

```bash
npm test                                    # suíte vitest
npm run lint                                # eslint
npx tsc -p tsconfig.app.json --noEmit       # tipos do renderer
npx tsc -p tsconfig.electron.json --noEmit  # tipos do processo principal
```

## Empacotando

```bash
npm run package
```

Gera o instalador Windows (`.exe`, NSIS) em `release/`. O comando roda o
build do renderer, compila o processo principal e chama `electron-builder`
(config em `electron-builder.yml`).

## De onde vêm os dados

O processo principal lê, para cada projeto do hub, `.ragx/status.json`; se o
arquivo não existir, cai para contagens lidas direto de
`.ragx/knowledge.db` (SQLite, via `sql.js`) como aproximação. A branch e o
commit atuais vêm de `git --no-optional-locks`, para nunca disputar o
`.git/index` com um `git` do usuário rodando ao mesmo tempo. O painel monta
esse retrato (o "snapshot") por polling a cada 5 segundos e também logo
depois que uma tarefa termina, sem esperar o próximo tick. Um `running` em
`status.json` só conta enquanto o processo dono (`pid`) existe: um índice
cancelado ou um hook que morreu não deixam o card preso em "Indexando…".

As conexões (RAGX CLI, Claude Code, Ollama) também são checadas só pelo
processo principal: a cada 30 segundos, no startup, logo depois de uma
correção de conexão e no "Verificar agora". Cada resultado vai ao renderer
pelo evento `ragx:connections`; checagens pedidas ao mesmo tempo viram uma só.

A resposta completa de `ragx status --json` (com os motivos de defasagem e o
histórico de indexações) só é pedida para o projeto aberto no momento na
tela de Detalhe, nunca para todos de uma vez.

Leitura de arquivo do projeto do usuário fica restrita a
`.ragx/status.json`, `.ragx/knowledge.db`, `.ragx/logs/mcp.jsonl` e à
existência de `ragx.toml` e `.git` (a busca de "Adicionar projeto" também
oferece repositórios git sem `ragx.toml`, marcados "novo"); nenhum conteúdo
de código-fonte é lido. Depois de um `add-project`, `name` e `visibility`
da seção `[project]` do `ragx.toml` são lidos só para explicar por que o
projeto não entrou no hub (colisão de nome ou projeto privado).

## A regra de IPC

O renderer nunca manda caminho de disco nem argumento livre para o processo
principal. Toda ação é pedida por **tipo de tarefa (`kind`) e id de
projeto** (`enqueueJob({ kind, projectId })`); um `projectId` desconhecido é
recusado antes de qualquer processo nascer. Quando o usuário escolhe uma
pasta (diálogo nativo ou "Adicionar projeto"), o caminho vira um **token
opaco** guardado só no processo principal; o renderer só volta a ver esse
token, nunca o caminho em si. Comandos externos rodam sempre por
`spawn`/`execFile` com lista de argumentos, nunca com `shell: true`.

## A fila de tarefas

Uma fila serial: no máximo uma tarefa `running` por vez, porque o Ollama é
compartilhado entre projetos. Pedidos duplicados (mesmo tipo, projeto e,
quando faz sentido, mesmo modelo ou pasta) são deduplicados: o segundo
pedido devolve a tarefa já enfileirada em vez de empilhar outra. Uma linha
`{"phase":"busy"}` emitida por `ragx index --progress` vira uma nota na
tarefa, não um erro, e a nota diz o que de fato acontece com cada tipo (o
pedido agendado roda como indexação incremental, então "Reindexar do zero"
pede para ser repetido). O código de saída 4 (índice ocupado) também vira
nota. A linha `{"phase":"done"}` com `embed_error` marca a tarefa como
falha ("Os embeddings não foram gerados: ..."), porque `ragx index` sai com 0
mesmo quando o embedder falha. Um `add-project` que termina sem a pasta no
registro do hub também falha, com o motivo. O texto de erro vem do bloco
`erro:` do stderr (os processos rodam com `COLUMNS=500` para o Rich não
quebrar a mensagem), e comandos globais rodam na pasta do usuário.

O catálogo é fechado: só estes 16 tipos existem, e cada um sabe qual
comando roda.

| `kind`            | Comando                                                                                                                |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `add-project`     | `ragx init <pasta>`, depois `ragx index <pasta> --progress --source panel` (e `ragx hooks install <pasta>` se marcado e a pasta for um repositório git) |
| `update`          | `ragx index <pasta> --progress --source panel`                                                                         |
| `embed`           | `ragx index <pasta> --embed-only --progress --source panel`                                                            |
| `reindex-full`    | `ragx index <pasta> --full --progress --source panel`                                                                  |
| `sync`            | `ragx sync` (cwd = pasta do projeto)                                                                                    |
| `graph`           | `ragx graph rebuild` (cwd = pasta do projeto)                                                                           |
| `dictionary`      | `ragx dictionary generate` (cwd = pasta do projeto)                                                                     |
| `hooks-install`   | `ragx hooks install <pasta>`                                                                                            |
| `hooks-uninstall` | `ragx hooks uninstall <pasta>`                                                                                          |
| `remove-from-hub` | `ragx project unregister -- <nome>`                                                                                    |
| `mcp-register`    | `ragx mcp install --client claude-code`                                                                                |
| `ollama-start`    | `docker start ollama` (Docker) ou `ollama serve` destacado e espera da API (local); qual dos dois é decidido por `chooseStartMode` (ver abaixo) |
| `ollama-pull`     | segue o modo: `docker exec ollama ollama pull <modelo>` (Docker) ou `ollama pull <modelo>` (local)                     |
| `ollama-use-native` | `winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements` (se não estiver instalado), `docker stop ollama` (se estiver rodando), `ollama serve` destacado (se não estiver rodando), espera da API e `ollama pull <modelo>` para cada modelo em uso. Instala antes de parar o container: se o `winget` falhar, o Docker continua servindo |
| `ollama-use-docker` | recusa com "O Docker não está instalado nesta máquina." ou "Abra o Docker Desktop e aguarde ele iniciar." (Docker parado); senão `docker pull ollama/ollama` (se o container não existe), encerra o Ollama local (ver `ollama-stop`), `docker start ollama` (se o container existe) ou `docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama --restart unless-stopped [--gpus all] ollama/ollama` (se não existe), espera da API e `docker exec ollama ollama pull <modelo>` para cada modelo em uso. A imagem é baixada antes de encerrar o Ollama local |
| `ollama-stop`     | `docker stop ollama` (se estiver rodando) e o encerramento do Ollama local: no Windows, `powershell -NoProfile -NonInteractive -Command <script>`, que encerra só `ollama.exe` e `ollama app.exe` cujo executável fica na pasta do Ollama detectado (a pasta vai pela variável de ambiente `OLLAMA_DIR` do processo, nunca dentro do comando; sem pasta conhecida, o passo não existe); em macOS e Linux, `pkill -x ollama` |

## Ollama: Docker ou local

O RAGX fala com o Ollama em `http://localhost:11434` (`/api/embed`,
`/api/tags`), seja um container Docker ou uma instalação na máquina, então
nada muda na configuração do RAGX entre os modos. Toda a novidade fica no
painel, no processo principal (`electron/ollama/`).

**Detecção.** O painel detecta, a cada checagem de conexões, o Docker
(instalado, rodando, container `ollama` existente ou parado), a placa de
vídeo (`nvidia`, `amd`, `intel`, `apple`, `none` ou `unknown`), o Ollama
local (instalado ou respondendo) e a API na porta 11434. O modo é um fato
detectado, não uma preferência: `docker` (container rodando), `native`
(Ollama local respondendo), `none` (nada responde) ou `conflict` (os dois de
pé, disputando a porta). "Conectado" significa API respondendo e modelos
baixados, não "existe um container".

**Recomendação.** Sempre substituível, com o motivo mostrado no card:

| Situação | Recomendado |
| --- | --- |
| macOS | local (o Docker não usa a GPU no macOS) |
| GPU NVIDIA e Docker instalado | Docker (container com `--gpus all`) |
| GPU NVIDIA sem Docker | local |
| GPU AMD, em qualquer sistema | local (o Docker não repassa GPU AMD) |
| GPU Intel, nenhuma ou desconhecida | Docker se instalado, senão local |

**Tarefas.** Trocar de modo é uma tarefa da fila: `ollama-use-native` e
`ollama-use-docker` param o outro modo, instalam, criam ou iniciam o
escolhido, esperam a API e baixam os modelos que os projetos usam (cada
passo só roda se ainda for necessário, decidido na hora); `ollama-stop`
para os dois modos e não apaga nada (o container, o volume dos modelos e a
instalação local ficam). `ollama-start` e `ollama-pull`, que já existiam,
agora seguem o modo detectado. O modo escolhido por último fica guardado nas
configurações do painel. O renderer pede só o tipo de tarefa (mais o modelo,
validado por `MODEL_PATTERN`); nenhum comando ou argumento livre.

**O que o "Iniciar" liga.** Uma função só (`electron/ollama/choose-start.ts`)
decide, e tanto o texto do botão ("Iniciar container" ou "Iniciar o Ollama
local") quanto a tarefa `ollama-start` usam a mesma resposta. Ordem: o modo
escolhido por último, se existir na máquina (container criado ou Ollama
local instalado); depois o recomendado, se existir; depois o container, se
existir; depois o Ollama local, se instalado. O card também não sugere
trocar para o modo recomendado quando o modo atual é o que a pessoa escolheu.

**Encerrar o Ollama local nem sempre é definitivo.** No Windows, o app de
bandeja do Ollama se registra para abrir no login: depois de trocar para o
Docker, ele pode voltar a subir no próximo login e disputar a porta com o
container (o card mostra o conflito). Para evitar, desligue o Ollama em
Configurações > Aplicativos > Inicialização. Em macOS e Linux, um
gerenciador de serviços (launchd, o serviço `ollama` do systemd) pode
reiniciar um servidor que o `pkill` encerrou; nesse caso, pare o serviço
por ele. Durante uma troca (`ollama-use-native` ou `ollama-use-docker` na
fila ou rodando), todas as ações do card do Ollama ficam desabilitadas.

**Benchmark.** "Medir velocidade" não é tarefa da fila: manda 64 textos para
`/api/embed`, consulta `/api/ps` e mostra chunks/s e o processador (`gpu`
quando o modelo está na VRAM, `cpu` quando não, `unknown` quando não deu para
saber). Só roda quando a pessoa pede, e o painel guarda o último resultado
em memória, com o modo em que foi medido, para mostrá-lo no card. Se o modo
muda, ou quando uma troca, parada ou início do Ollama termina, o resultado é
esquecido: a velocidade do Docker não diz nada sobre o Ollama local.

O Ollama tira o modelo da VRAM sozinho depois de alguns minutos sem uso
(5 minutos por padrão, ajustável por `OLLAMA_KEEP_ALIVE`). Por isso a GPU
não fica ocupada com o painel parado. O benchmark manda um texto de
aquecimento antes de medir, então o tempo de carregar o modelo de volta não
entra na velocidade.

**Instalação automática.** Só existe no Windows: `ollama-use-native` roda
`winget install -e --id Ollama.Ollama --silent`, por usuário, sem
elevação. Em macOS e Linux o painel recusa a instalação e mostra o link
https://ollama.com/download.

## Estrutura

- `src/`: UI React (renderer process): páginas em `src/pages/`, componentes
  em `src/components/`, hooks de dados em `src/hooks/` e o tipo do bridge
  IPC em `src/types/ragx-bridge.d.ts`.
- `electron/`: processo principal: janela e IPC (`main.ts`, `ipc.ts`,
  `preload.ts`), snapshot do hub (`data/`), checagem das conexões
  (`connections/checks.ts`), catálogo e fila de tarefas (`jobs/`) e busca de
  projetos numa pasta (`projects/discovery.ts`).
