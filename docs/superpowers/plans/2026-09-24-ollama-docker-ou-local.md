# Ollama no Docker ou local Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O painel detecta como o Ollama está rodando (Docker, local ou nada), diz se usa GPU ou CPU e a que velocidade, recomenda o modo certo para a máquina e troca de modo por uma tarefa da fila. Junto, o card de projeto passa a confirmar visualmente que a ação entrou na fila.

**Architecture:** Módulos novos e injetáveis no processo principal (`electron/ollama/`), extensão do catálogo fechado e da fila de tarefas com passos condicionais, IPC somente leitura para ambiente e benchmark, `checkOllama` reescrito sobre o ambiente e cards de interface. O RAGX (Python) não muda de configuração: container e instalação nativa respondem em `http://localhost:11434`.

**Tech Stack:** Electron 33, TypeScript 6, React 19, Vitest 2, Node `child_process`/`http`. Núcleo: Python, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-09-24-ollama-docker-ou-local-design.md`

## Global Constraints

- Trabalho no painel em `src/app`: `cd src/app && npm test && npm run lint && npx tsc -p tsconfig.app.json --noEmit && npx tsc -p tsconfig.electron.json --noEmit`. Núcleo: `uv run pytest -m "not slow" -rN` (sem `-q`, que esconde o resumo nesta máquina) e `uv run ruff check .`.
- **Nenhum teste toca Docker, winget, Ollama, a rede ou o `~/.claude.json` de verdade.** Tudo por dependências injetadas. Nenhum passo de subagente instala software, para container ou mexe no Ollama da máquina: isso é feito pelo controlador depois.
- IPC: o renderer pede tipo de tarefa (mais `model`, validado por `MODEL_PATTERN`); nunca comando, caminho ou argumento livre. Sem `shell: true`. O código do renderer nunca importa valor de `electron/`; o do `electron/` só importa TIPOS de `../src/types/ragx-bridge`.
- Tipos de tarefa novos (valores exatos): `ollama-use-native`, `ollama-use-docker`, `ollama-stop`. Os já existentes `ollama-start` e `ollama-pull` continuam, agora seguindo o modo detectado.
- Modos (valores exatos): `docker`, `native`, `none`, `conflict`. Fabricantes de GPU: `nvidia`, `amd`, `intel`, `apple`, `none`, `unknown`. Processador do benchmark: `gpu`, `cpu`, `unknown`.
- Winget: `winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements`. Container: nome `ollama`, imagem `ollama/ollama`, porta `11434:11434`, volume `ollama:/root/.ollama`, `--restart unless-stopped`, mais `--gpus all` só com GPU NVIDIA.
- Textos visíveis em português, sem travessão (—), voz ativa. O teste `no-em-dash` cobre `src/app/src` e `src/app/electron`.
- Commits `tipo(escopo): descrição` em português, terminando com `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- CHANGELOG `[Não lançado]` na mesma alteração que muda algo visível (Task 9 consolida).

## Review Focus

- Docker instalado mas parado, ou container que existe e está parado: a recomendação e as ações do card não podem tratar isso como "sem Docker". Teste na Task 1.
- Os dois modos de pé ao mesmo tempo (`conflict`): o card avisa e a tarefa de trocar para o modo escolhido para o outro primeiro. Teste nas Tasks 1 e 3.
- Passo `taskkill`/`docker stop` de algo que já não está rodando: não pode falhar a tarefa inteira. Teste na Task 4.
- Modelo inválido (`x; rm -rf /`, `--help`) em `ollama-pull` continua recusado nos dois modos. Teste na Task 3.
- Benchmark com Ollama fora do ar ou modelo ausente: devolve erro legível, nunca lança para o renderer. Teste na Task 2.

---

## File Structure

- Create `src/app/electron/ollama/environment.ts`: `detectOllama`, `recommend`, `classifyGpu`.
- Create `src/app/electron/ollama/benchmark.ts`: `runOllamaBenchmark`.
- Create `src/app/electron/ollama/paths.ts`: `resolveOllama` (executável nativo, com cache e reset).
- Modify `src/app/electron/jobs/catalog.ts`, `queue.ts`, `src/app/src/types/ragx-bridge.d.ts`.
- Modify `src/app/electron/ipc.ts`, `main.ts`, `preload.ts`, `connections/checks.ts`.
- Modify `src/app/src/components/connections/ConnectionCard.tsx`, `src/app/src/pages/ConnectionsPage.tsx`, `src/app/src/components/project/ProjectCard.tsx`, `src/app/src/pages/ProjectsPage.tsx`.
- Modify `src/ragx/cli/commands/doctor.py`, `CHANGELOG.md`, `src/app/README.md`, `task/fase-15-painel-desktop/*`.

---

### Task 1: Detecção do ambiente e recomendação

**Files:**
- Create: `src/app/electron/ollama/environment.ts`, `src/app/electron/ollama/paths.ts`
- Modify: `src/app/src/types/ragx-bridge.d.ts` (tipos)
- Test: `src/app/electron/ollama/__tests__/environment.test.ts`, `src/app/electron/ollama/__tests__/paths.test.ts`

**Interfaces:**
- Consumes: `ExecFn` (`electron/system/exec.ts`).
- Produces, no `ragx-bridge.d.ts`:

```ts
export type OllamaMode = 'docker' | 'native' | 'none' | 'conflict'
export type GpuVendor = 'nvidia' | 'amd' | 'intel' | 'apple' | 'none' | 'unknown'
export interface OllamaEnvironment {
  platform: 'win32' | 'darwin' | 'linux'
  gpu: { vendor: GpuVendor; name: string | null }
  docker: { installed: boolean; running: boolean }
  container: { exists: boolean; running: boolean }
  native: { installed: boolean; path: string | null; running: boolean }
  canInstallNative: boolean          // platform === 'win32'
  apiUp: boolean
  models: string[]                   // nomes de /api/tags (sem sufixo tratado)
  mode: OllamaMode
  recommendation: { mode: 'docker' | 'native'; reason: string }
}
export interface OllamaBenchmark {
  ok: boolean
  chunksPerSecond: number | null
  processor: 'gpu' | 'cpu' | 'unknown'
  vramMB: number | null
  model: string | null
  measuredAt: string
  error: string | null
}
```

- Produces em `environment.ts`:

```ts
export interface EnvDeps {
  exec: ExecFn
  httpGetJson: (url: string, timeoutMs: number) => Promise<unknown | null>
  platform: NodeJS.Platform
  arch: string
  resolveNativePath: () => string | null      // executável nativo, mesmo fora do PATH
}
export function classifyGpu(names: string[], platform: NodeJS.Platform, arch: string): { vendor: GpuVendor; name: string | null }
export function recommend(env: Omit<OllamaEnvironment, 'recommendation'>): { mode: 'docker' | 'native'; reason: string }
export async function detectOllama(d: EnvDeps): Promise<OllamaEnvironment>   // nunca lança
export function defaultEnvDeps(): EnvDeps
```

- `paths.ts`: `resolveOllama(deps?: { env?, exists?, platform? }): string | null` e `resetOllamaCache()`. No Windows procura `ollama.exe` no PATH e em `%LOCALAPPDATA%\Programs\Ollama\ollama.exe` (o app aberto pelo menu Iniciar pode não ter o PATH novo); em posix, no PATH e em `/usr/local/bin/ollama`, `/opt/homebrew/bin/ollama`. Segue o padrão de `system/ragx-exe.ts` (só `.exe` no Windows, segmentos do PATH sem aspas). `ollamaCommand(): string` devolve o caminho resolvido ou `'ollama'`.

Regras de `detectOllama` (tudo tolerante a falha; qualquer exceção vira o campo "ausente"):
- GPU: Windows, `exec('powershell', ['-NoProfile','-NonInteractive','-Command','(Get-CimInstance Win32_VideoController).Name'])`, uma placa por linha; Linux, `exec('lspci', [])` filtrando linhas com `VGA`, `3D` ou `Display`; macOS, `apple` quando `arch === 'arm64'`, senão `unknown`. `classifyGpu` escolhe por prioridade `nvidia` (geforce, rtx, gtx, quadro, nvidia), `amd` (amd, radeon), `apple`, `intel`; nenhum nome reconhecido com lista vazia: `none`; lista sem correspondência: `unknown`. `name` é o nome da placa escolhida.
- Docker: `docker.installed` quando `exec('docker', ['--version'])` sai 0; `docker.running` quando `exec('docker', ['info','--format','{{.ServerVersion}}'])` sai 0.
- Container: só consulta se `docker.running`: `exec('docker', ['ps','-a','--filter','name=^ollama$','--format','{{.State}}'])`; saída vazia = `exists: false`; `running` quando o estado é `running`.
- Nativo: `native.path = resolveNativePath()`, `installed = path !== null`; `running` quando (Windows) `exec('tasklist', ['/FI','IMAGENAME eq ollama.exe','/FO','CSV','/NH'])` contém `ollama.exe`, (posix) `exec('pgrep', ['-x','ollama'])` sai 0.
- API: `httpGetJson('http://localhost:11434/api/tags', 3000)`; `apiUp` quando não é `null`; `models` = `models[].name`.
- Modo: `container.running && native.running` = `conflict`; `container.running` = `docker`; `native.running` = `native`; `apiUp` sem nenhum dos dois (ex.: outro processo) = `native`; senão `none`.
- Recomendação: a tabela da spec. `reason` (textos exatos): macOS: "No macOS o Docker não usa a GPU. O Ollama local usa a GPU do Mac."; NVIDIA com Docker instalado: "O container consegue usar sua GPU NVIDIA."; NVIDIA sem Docker: "Sem Docker instalado, o Ollama local usa sua GPU NVIDIA."; AMD: "O Docker não repassa GPU AMD. O Ollama local usa a sua placa."; demais com Docker instalado: "Sem GPU compatível com o Docker, o container resolve e isola o Ollama."; demais sem Docker: "Sem Docker instalado, use o Ollama local."

- [ ] **Step 1: Testes.** `environment.test.ts` com `EnvDeps` falsos (mapa de `argv juntado` para resposta): (a) `classifyGpu` para `['NVIDIA GeForce RTX 4070']`, `['AMD Radeon RX 7700 XT']`, `['Intel(R) UHD Graphics','NVIDIA GeForce GTX 1650']` (nvidia vence), `['Intel(R) UHD Graphics']`, lista vazia (`none`), `['Microsoft Basic Display Adapter']` (`unknown`), macOS arm64 (`apple`) e macOS x64 (`unknown`); (b) `recommend` para cada linha da tabela, com os textos exatos; (c) `detectOllama`: Docker ausente (`docker --version` falha), Docker instalado mas parado, container inexistente, container parado, container rodando com API no ar (`docker`), nativo rodando (`native`), os dois rodando (`conflict`), nada (`none`), API no ar sem container e sem processo nativo detectado (`native`), `exec` que lança para tudo (devolve ambiente com tudo ausente, sem rejeitar). `paths.test.ts`: PATH, `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`, macOS/Linux, `null`, e `.cmd` ignorado no Windows.

- [ ] **Step 2: Ver falhar.** `cd src/app && npx vitest run electron/ollama`; esperado FAIL (módulos inexistentes).

- [ ] **Step 3: Implementar** `environment.ts` (com `defaultEnvDeps()` usando `execFileText`, `resolveOllama` e o mesmo `httpGetJson` de `connections/checks.ts`: extraia esse helper para `electron/system/http.ts` e reuse nos dois) e `paths.ts`, e os tipos.

- [ ] **Step 4: Ver passar e commit.** `npm test`, lint, os dois `tsc`.

```bash
git add src/app
git commit -m "feat(app): detecta como o Ollama roda (docker, local ou nada) e recomenda o modo

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Benchmark de embeddings

**Files:**
- Create: `src/app/electron/ollama/benchmark.ts`
- Test: `src/app/electron/ollama/__tests__/benchmark.test.ts`

**Interfaces:**
- Consumes: `OllamaBenchmark` (Task 1).
- Produces:

```ts
export interface BenchDeps {
  httpPostJson: (url: string, body: unknown, timeoutMs: number) => Promise<{ status: number; json: unknown | null } | null>
  httpGetJson: (url: string, timeoutMs: number) => Promise<unknown | null>
  now: () => number            // ms
  model: string | null         // primeiro modelo em uso pelos projetos, ou null
}
export async function runOllamaBenchmark(d: BenchDeps): Promise<OllamaBenchmark>   // nunca lança
export function defaultBenchDeps(model: string | null): BenchDeps
```

Regras: modelo = `d.model ?? 'nomic-embed-text'`. 1) aquecimento: `POST http://localhost:11434/api/embed` com `{model, input: ['aquecimento']}` (timeout 120 s, porque a primeira chamada carrega o modelo); resposta nula, status diferente de 200 ou corpo com `error` vira `ok: false` com `error` legível ("O Ollama não respondeu em localhost:11434." / "O modelo X não está baixado neste Ollama." quando o corpo diz que não achou / "Falha ao gerar embeddings: {mensagem}"). 2) medição: 64 textos de ~80 palavras geradas de forma determinística (ex.: `Array.from({length: 64}, (_, i) => \`trecho ${i} \` + 'lorem ipsum dolor sit amet '.repeat(16))`) em lotes de 32 (duas chamadas, como o RAGX usa), tempo total pelo `d.now()`. 3) `GET /api/ps`: procura o modelo em `models[]`; `size_vram > 0` = `gpu` (com `vramMB = round(size_vram/1048576)`), `size_vram === 0` = `cpu`, modelo ausente ou resposta inesperada = `unknown`. `chunksPerSecond = 64 / segundos`, arredondado a uma casa. `measuredAt` em ISO.

- [ ] **Step 1: Testes** com `BenchDeps` falsos e relógio controlado: caminho GPU (`size_vram` positivo, taxa calculada: 64 textos em 2 s = 32,0/s), caminho CPU (`size_vram: 0`), modelo ausente em `/api/ps` (`unknown`), Ollama fora (`httpPostJson` devolve `null`), modelo não baixado (status 404 com `{"error":"model \"x\" not found"}`), corpo com `error`, exceção nos deps (não rejeita), o modelo escolhido é o passado ou o padrão, dois POSTs de 32 na medição.
- [ ] **Step 2: Ver falhar; Step 3: Implementar** (`defaultBenchDeps` usa `node:http` com `request`, `POST`, `JSON.stringify`, timeout, `null` em erro).
- [ ] **Step 4: Verificar e commit**

```bash
git add src/app
git commit -m "feat(app): benchmark de embeddings do Ollama (velocidade e GPU ou CPU)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Catálogo de tarefas do Ollama

**Files:**
- Modify: `src/app/electron/jobs/catalog.ts`, `src/app/src/types/ragx-bridge.d.ts` (`JobKind`)
- Test: `src/app/electron/jobs/__tests__/catalog.test.ts`

**Interfaces:**
- Consumes: `OllamaEnvironment` (Task 1).
- Produces:

```ts
export type StepCondition =
  | 'container-running' | 'container-exists' | 'container-missing'
  | 'native-running' | 'native-missing' | 'native-not-running'

export interface Step {
  cmd: 'ragx' | 'docker' | 'ollama' | 'winget' | 'taskkill' | 'pkill'
  args: string[]
  cwd: string | null
  progress: boolean
  onlyIfGitRepo?: string
  /** Só roda se a condição for verdadeira NA HORA (avaliada pela fila). Falsa: passo pulado. */
  when?: StepCondition
  /** Processo de longa vida (ex.: `ollama serve`): a fila só confirma que nasceu e segue. */
  detached?: boolean
  /** Passo sem processo: espera `GET /api/tags` responder (até `timeoutMs`). */
  waitForOllamaApi?: { timeoutMs: number }
  /** Códigos de saída que contam como sucesso além de 0 (ex.: `taskkill` 128 = nada a encerrar). */
  okExitCodes?: number[]
  /** Nota registrada no job quando o passo é pulado por `when`. */
  skipNote?: string
}

export interface CatalogContext {
  projectById: ...
  folderByToken: ...
  /** Último ambiente detectado (o painel atualiza a cada checagem); `null` antes da primeira. */
  ollamaEnv?: () => OllamaEnvironment | null
  /** Modelos de embedding em uso pelos projetos com provider ollama, sem repetição. */
  requiredModels?: () => string[]
}
```

Novos kinds em `KNOWN_KINDS` e no `JobKind`: `ollama-use-native`, `ollama-use-docker`, `ollama-stop`.

Regras (kind → label → passos, todos sem `progress`):

- **`ollama-use-native`**, label "Usar o Ollama local":
  1. `docker stop ollama`, `when: 'container-running'`, `okExitCodes: []`.
  2. `winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements`, `when: 'native-missing'`.
  3. `ollama serve`, `detached: true`, `when: 'native-not-running'`, `skipNote: 'O Ollama local já estava rodando.'`.
  4. `waitForOllamaApi: { timeoutMs: 60000 }` (passo sem processo: `cmd` fica `'ollama'`, `args: []`).
  5. um `ollama pull <modelo>` por modelo de `ctx.requiredModels()` (cada um validado por `MODEL_PATTERN`; modelo inválido é ignorado com nota, nunca vira argumento).
  Recusa (`JobRejected`) quando `ctx.ollamaEnv?.()` existe e `canInstallNative === false` e `native.installed === false`: "A instalação automática do Ollama só existe no Windows. Baixe em https://ollama.com/download e abra o painel de novo."
- **`ollama-use-docker`**, label "Usar o Ollama no Docker":
  1. `taskkill /IM "ollama app.exe" /T /F`, `when: 'native-running'`, `okExitCodes: [128]` (só quando a plataforma do ambiente é `win32`; em posix, `pkill -x ollama` com `okExitCodes: [1]`).
  2. `taskkill /IM ollama.exe /T /F`, `when: 'native-running'`, `okExitCodes: [128]` (só Windows).
  3. `docker start ollama`, `when: 'container-exists'` (cobre o container parado; se já roda, `docker start` é inofensivo).
  4. `docker run -d --name ollama -p 11434:11434 -v ollama:/root/.ollama --restart unless-stopped [--gpus all] ollama/ollama`, `when: 'container-missing'` (`--gpus all` só se `env.gpu.vendor === 'nvidia'`, antes de `ollama/ollama`).
  5. `waitForOllamaApi: { timeoutMs: 60000 }`.
  6. um `docker exec ollama ollama pull <modelo>` por modelo requerido.
  Recusa quando `ollamaEnv()` diz `docker.installed === false`: "O Docker não está instalado nesta máquina."
- **`ollama-stop`**, label "Parar o Ollama": `docker stop ollama` (`when: 'container-running'`), e no Windows `taskkill` das duas imagens (`when: 'native-running'`, `okExitCodes: [128]`), em posix `pkill -x ollama`.
- **`ollama-start`** (existente) passa a seguir o ambiente: container existente e parado, `docker start ollama` (`when: 'container-exists'`); senão, nativo instalado: `ollama serve` destacado (`when: 'native-not-running'`) e `waitForOllamaApi`. Sem `ollamaEnv`, mantém o comportamento antigo (`docker start ollama`).
- **`ollama-pull`** (existente): `model` continua obrigatório e validado por `MODEL_PATTERN`; o comando segue o modo do ambiente: `mode === 'native'` usa `ollama pull <modelo>`, senão `docker exec ollama ollama pull <modelo>` (padrão, e comportamento antigo sem `ollamaEnv`).
- `dedupeKey` desses kinds: `${kind}||` (um por vez, sem projeto). `ResolvedJob.model` continua só para `ollama-pull`.

- [ ] **Step 1: Testes** em `catalog.test.ts` (argv exatos, um caso por passo): `ollama-use-native` com ambiente `docker` em uso (passos 1 a 5 na ordem, `when` corretos), com dois modelos requeridos (dois `pull`), com modelo inválido na lista (ignorado), recusa fora do Windows sem nativo instalado, aceita fora do Windows com nativo instalado; `ollama-use-docker` no Windows (dois `taskkill`) e em Linux (`pkill`), com NVIDIA (`--gpus all` presente e antes da imagem) e com AMD (ausente), recusa sem Docker instalado; `ollama-stop` nos dois sistemas; `ollama-start` com container existente, só com nativo, sem `ollamaEnv`; `ollama-pull` em `native`, em `docker` e sem ambiente, e as recusas antigas (`x; rm -rf /`, `--help`) nos dois modos; kinds novos aparecem em `KNOWN_KINDS` (pedido com kind novo passa, kind inventado é recusado).
- [ ] **Step 2: Ver falhar; Step 3: Implementar; Step 4: Verificar e commit**

```bash
git add src/app
git commit -m "feat(app): catalogo de tarefas para trocar, parar e iniciar o Ollama (docker ou local)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Fila executa passos condicionais, destacados e de espera

**Files:**
- Modify: `src/app/electron/jobs/queue.ts`
- Test: `src/app/electron/jobs/__tests__/queue.test.ts`

**Interfaces:**
- Consumes: `Step`, `StepCondition` (Task 3).
- Produces em `QueueDeps` (todos opcionais, como `isGitRepo`):

```ts
/** Avalia, NA HORA, a condição de um passo (o main re-detecta o ambiente). */
stepCondition?: (c: StepCondition) => Promise<boolean>
/** Espera a API do Ollama responder; `true` quando respondeu dentro do prazo. */
waitForOllamaApi?: (timeoutMs: number) => Promise<boolean>
```

- `SpawnFn` ganha um quarto parâmetro opcional: `(cmd, args, cwd, opts?: { detached?: boolean }) => ChildLike`. `defaultSpawn` resolve `cmd`: `'ragx'` por `ragxCommand()`, `'ollama'` por `ollamaCommand()` (Task 1), demais como estão. Para `detached: true`: `spawn(..., { detached: true, stdio: 'ignore', windowsHide: true })` e `child.unref()`; o `ChildLike` avisa `onExit(0)` assim que o evento `spawn` dispara (ou `onExit(null, mensagem)` no `error`), sem esperar o processo terminar.

Regras da fila:
- `when` definido e `deps.stepCondition` presente: avalia antes do passo; falso pula o passo, registra `skipNote` (se houver) em `note` sem apagar nota existente, e segue. Sem `deps.stepCondition`, o passo roda (compatibilidade).
- `waitForOllamaApi`: sem processo; chama `deps.waitForOllamaApi(timeoutMs)`; `false` falha o job com "O Ollama não respondeu em localhost:11434 a tempo."; sem a dependência, o passo é pulado.
- `okExitCodes`: saída 0 ou algum desses códigos conta como sucesso do passo.
- Cancelar durante `when`/espera funciona (o passo seguinte não roda); `cancel` de passo destacado não mata o processo destacado (ele é intencionalmente independente).
- Erros de spawn de `ollama`/`winget`/`taskkill` usam `spawnErrorText` existente ("Comando não encontrado: ollama").

- [ ] **Step 1: Testes** com `SpawnFn` falso: passo com `when` falso é pulado com a nota; com `when` verdadeiro roda; `stepCondition` é chamada uma vez por passo condicional e antes do passo (ordem observável); passo destacado conclui sem esperar saída e o passo seguinte roda; `waitForOllamaApi` verdadeiro segue, falso falha com a mensagem, ausente é pulado; `okExitCodes: [128]` com saída 128 continua e com 1 falha; uma tarefa `ollama-use-native` completa de ponta a ponta com o catálogo real (ambiente `docker` rodando: os passos executam na ordem esperada com condições simuladas); cancelar entre passos.
- [ ] **Step 2: Ver falhar; Step 3: Implementar; Step 4: Verificar e commit**

```bash
git add src/app
git commit -m "feat(app): fila executa passos condicionais, destacados e de espera pela API

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: IPC, ligação no processo principal e ponte

**Files:**
- Modify: `src/app/electron/ipc.ts`, `src/app/electron/main.ts`, `src/app/electron/preload.ts`, `src/app/src/types/ragx-bridge.d.ts` (`RagxBridge`)
- Test: `src/app/electron/__tests__/ipc.test.ts`

**Interfaces:**
- Consumes: `detectOllama` (Task 1), `runOllamaBenchmark` (Task 2), catálogo e fila (Tasks 3 e 4).
- Produces na ponte (`window.ragx`): `getOllamaEnvironment(): Promise<OllamaEnvironment>` e `runOllamaBenchmark(): Promise<OllamaBenchmark>`. Sem argumentos vindos do renderer.
- `HandlerDeps` ganha `detectOllama: () => Promise<OllamaEnvironment>`, `runOllamaBenchmark: (model: string | null) => Promise<OllamaBenchmark>`. O handler do benchmark escolhe o modelo no servidor (o primeiro de `requiredModels()`), guarda o resultado em memória (`lastBenchmark`) e o disponibiliza para `checkOllama` (Task 6) via `getLastBenchmark()`.
- No `main.ts`: guarda o último `OllamaEnvironment` (atualizado a cada `getConnections` e a cada checagem de 30 s; uma detecção por ciclo, compartilhada com `checkOllama`), monta `CatalogContext.ollamaEnv` e `requiredModels` (de `distinct(embeddingModel)` dos projetos do último snapshot com provider ollama), e `QueueDeps.stepCondition` (re-detecta o ambiente na hora e mapeia: `container-running` = `env.container.running`, `container-exists` = `env.container.exists`, `container-missing` = `!env.container.exists`, `native-running` = `env.native.running`, `native-missing` = `!env.native.installed`, `native-not-running` = `!env.native.running`) e `waitForOllamaApi` (sondagem de `/api/tags` a cada 1 s até o prazo). Depois de uma tarefa `ollama-*` terminar, dispara nova checagem de conexões (a lista `CONNECTION_JOB_KINDS` de `jobs/transitions.ts` ganha os três kinds novos) e `resetOllamaCache()`.

- [ ] **Step 1: Testes** em `ipc.test.ts`: os dois handlers existem e devolvem o que os deps devolvem; `runOllamaBenchmark` guarda o resultado; nenhum dos dois aceita argumento (argumentos passados são ignorados, e `enqueueJob({kind:'ollama-use-native', model:'x; rm -rf /'})` continua recusado por chave/tipo); `enqueueJob` aceita os três kinds novos e recusa com chave extra. `preload`/ponte: os dois métodos expostos e nenhum vazamento de `ipcRenderer`.
- [ ] **Step 2: Ver falhar; Step 3: Implementar; Step 4: Verificar (inclui `npm run build:electron:ts`) e commit**

```bash
git add src/app
git commit -m "feat(app): IPC de ambiente e benchmark do Ollama e ligacao das condicoes da fila

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: `checkOllama` sobre o ambiente

**Files:**
- Modify: `src/app/electron/connections/checks.ts`, `src/app/src/types/ragx-bridge.d.ts` (`ConnectionAction`)
- Modify: `src/app/electron/ipc.ts` e `src/app/electron/main.ts` (o ponto que chama `checkAll` passa o último `OllamaEnvironment` e o último benchmark guardados na Task 5)
- Test: `src/app/electron/connections/__tests__/checks.test.ts`, `src/app/electron/__tests__/ipc.test.ts`

**Interfaces:**
- Consumes: `OllamaEnvironment`, `OllamaBenchmark` (Tasks 1 e 2).
- `ConnectionAction` ganha `secondary?: boolean` e o `kind` passa a ser `'mcp-register' | 'ollama-start' | 'ollama-pull' | 'ollama-use-native' | 'ollama-use-docker' | 'ollama-stop' | 'ollama-benchmark'`.
- `checkOllama(d, snapshot, env, lastBenchmark)` (assinatura estendida; `checkAll` recebe `env` e `lastBenchmark` opcionais, `null` mantém o comportamento por `docker ps`/HTTP de hoje, para não quebrar chamadas antigas). Regras novas quando `env` existe:
  - **API fora do ar**: `error`, "O Ollama não está respondendo em localhost:11434." Ações: se `container.exists` (parado): `ollama-start` "Iniciar container"; senão, se `native.installed`: `ollama-start` "Iniciar o Ollama local"; senão, a recomendação: `ollama-use-native` "Instalar e usar o Ollama local" (quando `canInstallNative`) ou `ollama-use-docker` "Usar o Ollama no Docker" (quando a recomendação é Docker e Docker instalado); sem ação automática possível, `help` com o link `https://ollama.com/download`. Docker instalado mas parado e sem nativo: `help` "Abra o Docker Desktop e aguarde ele iniciar." além da ação local quando existir.
  - **`conflict`**: `warn`, "O Ollama está rodando no Docker e no computador ao mesmo tempo. Os dois disputam a mesma porta." Ação: a recomendada (`ollama-use-native` ou `ollama-use-docker`).
  - **API no ar**: as regras atuais de modelos (faltando: `warn` com `ollama-pull`; tudo presente: `ok`), com `summary` "Rodando no Docker, com os modelos que os projetos usam." ou "Rodando no computador (local), com os modelos que os projetos usam." conforme o modo.
  - **Facts** (ordem): "Modo" (`Docker` ou `Local`), "Processador" (`GPU (N GB de VRAM)`, `CPU` ou `ainda não medido`, vindo de `lastBenchmark`), "Velocidade" (`N chunks/s`, só com benchmark ok), "Placa de vídeo" (nome, se conhecido), depois os fatos atuais (modelos instalados, projetos que dependem).
  - **Ações extras com API no ar**: `ollama-benchmark` "Medir velocidade" (`secondary`), `ollama-stop` "Parar o Ollama" (`secondary`), e, quando o modo atual difere da recomendação **e** o processador é `cpu` ou `unknown`, a troca recomendada como ação principal: `ollama-use-native` "Trocar para o Ollama local (usa sua GPU)" ou `ollama-use-docker` "Trocar para o Ollama no Docker". `help` traz a `recommendation.reason` quando há troca sugerida.
  - "Conectado" nunca depende de existir container.

- [ ] **Step 1: Testes** para cada estado acima (API fora com container parado, com nativo instalado, sem nada no Windows, sem nada no macOS, Docker parado; `conflict`; `ok` em Docker e em local; `warn` por modelo faltando; facts na ordem com e sem benchmark; troca sugerida só quando difere e o processador é CPU/desconhecido; nenhuma ação de troca quando já está em GPU; textos sem travessão; `env` `null` mantém o comportamento antigo (os testes existentes continuam passando).
- [ ] **Step 2: Ver falhar; Step 3: Implementar; Step 4: Verificar e commit**

```bash
git add src/app
git commit -m "feat(app): card de Ollama mostra modo, processador e velocidade e sugere a troca certa

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Interface do card de Ollama

**Files:**
- Modify: `src/app/src/components/connections/ConnectionCard.tsx`, `src/app/src/pages/ConnectionsPage.tsx`, `src/app/src/state.ts` (`activeConnectionJob`), CSS em `src/app/src/App.css`
- Test: `src/app/src/pages/__tests__/ConnectionsPage.test.tsx`, `src/app/src/pages/__tests__/Onboarding.test.tsx`

**Interfaces:**
- Consumes: `ConnectionAction` (Task 6), `window.ragx.enqueueJob`, `window.ragx.runOllamaBenchmark`, `window.ragx.getConnections`.
- Regras:
  - Ações `secondary` renderizam como botão neutro (`btn`), abaixo das principais; principais como hoje (`btn-primary`).
  - `ollama-use-native`, `ollama-use-docker`, `ollama-stop`, `ollama-start`: `enqueueJob({ kind })`; `ollama-pull`: com `model`.
  - `ollama-benchmark`: não é tarefa; chama `runOllamaBenchmark()`, mostra "Medindo…" e desabilita o botão até terminar, e em seguida `getConnections()` (o processo principal já guardou o resultado); erro do benchmark aparece no card ("Não foi possível medir: {mensagem}").
  - Botão com tarefa ativa do mesmo `kind` (e mesmo `model` no pull): desabilitado com `jobStateLabel`; `activeConnectionJob` passa a reconhecer os kinds novos.
  - Tarefa de troca em andamento mostra, no card, o rótulo da tarefa ativa ("Usar o Ollama local") e o texto "A troca leva alguns minutos; acompanhe pela fila no topo."
  - O passo 2 do onboarding usa o mesmo componente, então herda tudo.

- [ ] **Step 1: Testes** (ponte falsa): ação secundária é neutra e a principal não; clicar em "Trocar para o Ollama local" enfileira `{kind:'ollama-use-native'}`; "Parar o Ollama" enfileira `{kind:'ollama-stop'}`; "Medir velocidade" chama `runOllamaBenchmark`, desabilita durante a chamada, depois chama `getConnections`; erro do benchmark é mostrado; tarefa ativa desabilita o botão e mostra o aviso; onboarding mostra as mesmas ações no passo 2; nenhum travessão em texto visível (o teste global cobre).
- [ ] **Step 2: Ver falhar; Step 3: Implementar; Step 4: Verificar e commit**

```bash
git add src/app
git commit -m "feat(app): acoes de trocar, parar e medir o Ollama no card de conexoes

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Feedback de fila no card de projeto (RAGX-0115)

**Files:**
- Modify: `src/app/src/components/project/ProjectCard.tsx`, `src/app/src/pages/ProjectsPage.tsx`, CSS
- Test: `src/app/src/pages/__tests__/ProjectsPage.test.tsx`

**Regras:**
- O botão principal do card fica desabilitado enquanto existe tarefa **ativa do mesmo tipo** para o projeto (`activeJobFor(jobs, projectId, [kind])`), com o texto de `jobStateLabel` ("Na fila" ou "Rodando") no lugar do rótulo. O selo do card continua vindo de `deriveProjectState` (só tarefas de indexação mudam o selo).
- Ao clicar numa ação que enfileira, `ProjectsPage` mostra por 4 s, numa região `role="status"` (`aria-live="polite"`), "Adicionado à fila: {label da ação} em {projeto}" (ex.: "Adicionado à fila: Instalar hooks em Bigbot-Workspace"). Falha ao enfileirar (`enqueueJob` rejeita): "Não foi possível adicionar à fila: {mensagem}" na mesma região, sem sumir sozinha por 8 s.
- Tarefa do mesmo projeto que terminou com erro: o card mostra uma linha discreta com o erro (`view.error`) até o próximo snapshot/tarefa, com o rótulo "Última tarefa falhou:".
- Tarefa de outro projeto, ou de outro tipo, não afeta o botão.

- [ ] **Step 1: Testes** (com `jobs` falsos): com `hooks-install` `queued` para o projeto, o botão principal ("Instalar hooks") está desabilitado com o texto "Na fila"; `running` mostra "Rodando"; tarefa de outro projeto não desabilita; tarefa de outro tipo (ex.: `graph`) não desabilita; clique enfileira e mostra o aviso exato; `enqueueJob` rejeitando mostra o erro; tarefa `failed` mostra "Última tarefa falhou:" com o erro.
- [ ] **Step 2: Ver falhar; Step 3: Implementar; Step 4: Verificar e commit**

```bash
git add src/app
git commit -m "fix(app): card de projeto confirma que a acao entrou na fila e mostra falha da tarefa

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: `ragx doctor`, documentação e backlog

**Files:**
- Modify: `src/ragx/cli/commands/doctor.py` (ou o módulo que monta a linha do embedder), `tests/e2e/` ou `tests/unit/` do doctor, `CHANGELOG.md`, `src/app/README.md`, `docs/14-cli.md` (se o doctor for documentado ali), `task/fase-15-painel-desktop/RAGX-0115-*.md` e `RAGX-0116-*.md` (status)

**Regras:**
- `ragx doctor`: quando o Ollama responde, além da linha atual do embedder, acrescenta a linha "Ollama: GPU (N MB de VRAM)" ou "Ollama: CPU" quando `GET /api/ps` lista o modelo do projeto com `size_vram`, e "Ollama: processador ainda não medido (nenhum modelo carregado)" quando a lista está vazia. Nunca falha o doctor por causa disso (erro de rede vira a linha "Ollama: não foi possível consultar o processador"). Testes com o HTTP simulado (`monkeypatch` de `urllib.request.urlopen`): GPU, CPU, lista vazia, erro.
- `src/app/README.md`: seção "Ollama: Docker ou local" (detecção, recomendação, as três tarefas novas e as duas existentes que seguem o modo, benchmark, o que a instalação automática faz e só no Windows) e a tabela de tarefas com os três kinds novos.
- `CHANGELOG.md` `[Não lançado]`: entrada do painel para o card de Ollama (modo, processador, velocidade, trocar/parar/medir) e para o feedback de fila no card, e entrada do núcleo para o doctor. Sem travessão.
- Backlog: `RAGX-0115` e `RAGX-0116` com `Status` `done` e os critérios de aceite marcados apenas se verificados de fato (a verificação real na máquina é do controlador: deixe marcados só os cobertos por teste e escreva na nota o que falta verificar no app real).

- [ ] **Step 1: Testes do doctor** (RED), **Step 2: implementar**, **Step 3: docs**, **Step 4: `uv run pytest tests/unit/test_documentacao.py -q -rN` e a suíte rápida (`uv run pytest -m "not slow" -rN`), `uv run ruff check .`, commit.

```bash
git add -A src/ragx tests docs task CHANGELOG.md src/app/README.md
git commit -m "feat(doctor): informa se o Ollama usa GPU ou CPU; docs e backlog do Ollama docker/local

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```
