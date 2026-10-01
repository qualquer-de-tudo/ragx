# RAGX-0177 — Medir RAM e CPU do Electron em execução (linha de base)

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (seção 8) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

A auditoria mediu só comandos isolados e screenshots do build estático: **"O Electron real não foi aberto: não há medição de RAM nem de CPU do app"** (seção 6; seção 8 repete). Todo o bloco de desempenho do painel (`RAGX-0171` a `0175`, e `0176` pela RAM) promete "menos CPU" sem número de partida, e S11 (filhos por minuto: hoje ≈290+ visível e minimizada, meta ≤ 20 / 0) vem de contagem por leitura de código. Esta tarefa entrega o **instrumento** e a **linha de base**: quanta RAM e CPU o painel gasta com 12 projetos nos estados janela visível, minimizada e oculta, e quantos processos filhos ele cria por minuto.

## Entregáveis

- [x] `electron/system/spawn-counter.ts`: contador em memória `countSpawn(file, ms?)` que agrupa por nome do executável (`git`, `ragx`, `docker`, `tasklist`, `powershell`, outro) e soma duração; `snapshot()` devolve os acumulados para o amostrador calcular diferenças
- [x] Ligar o contador aos três pontos de criação de processo: `execFileText` (`electron/system/exec.ts`, mede do `execFile` ao callback), `defaultSpawn` (`electron/jobs/queue.ts:794`, rótulo `job`) e `runRagxCommand` (`electron/data/run-ragx-command.ts:22`). Cobrem snapshot, conexões e tarefas; processos do próprio Chromium aparecem pelas métricas do Electron
- [x] `electron/system/runtime-metrics.ts`: `createRuntimeSampler({ getAppMetrics, getState, spawns, now, write })` com amostra a cada 5 s em JSONL: `t`, `state` (`visible|minimized|hidden`), por processo `{pid, type, cpu, workingSetMB, privateMB}` de `app.getAppMetrics()` (`Browser`, `Tab`, `GPU`, `Utility`), totais, filhos criados e ms de filhos desde a amostra anterior por executável, e `snapshotMs` da última reconstrução (cronometrar `refreshSnapshot`, `main.ts:85`). O CPU do Electron é medido desde a chamada anterior: a 1ª amostra é marcada `warmup` e descartada
- [x] Opt-in e só no processo principal: o amostrador existe **apenas** com `RAGX_PANEL_METRICS=<arquivo.jsonl>`; sem a variável nada é criado nem gravado. Com `RAGX_PANEL_METRICS_PLAN="visible:5,minimized:5,hidden:5"` (minutos por estado), `main.ts` leva a janela a cada estado (`show`+`restore`, `minimize`, `hide`) e chama `app.quit()` no fim. Em modo de medição `isDev` é falso (carrega `dist/index.html`, sem DevTools), para o Electron sem empacotar (`electron dist-electron/main.js`) medir a casca de produção. Nenhum canal IPC novo
- [x] `electron/system/runtime-summary.ts` (puro, testado): `parsePlan(texto)` e `summarize(amostras)` por estado: RAM total (working set e privada) média e pico, CPU média e p95 por tipo de processo, filhos por minuto por executável e ms de filhos por minuto, `snapshotMs` médio
- [x] `scripts/measure-runtime.mjs` (em `src/app`): `node scripts/measure-runtime.mjs --plan visible:5,minimized:5,hidden:5 --label baseline-1.0.0-beta.5 [--exe <caminho>] [--projects real|fixture12] [--warmup 1]`. Sobe o Electron com `--user-data-dir` temporário e as variáveis acima, espera sair, lê o JSONL (dentro de `%TEMP%`, **não** versionado) e **acrescenta** uma seção a `src/app/docs/medicao-runtime.md` (criar a pasta `src/app/docs/`). `fixture12` cria em pasta temporária 12 repositórios `git init` com `.ragx/status.json` e aponta `USERPROFILE`/`HOME` para um hub de 12 projetos; `real` usa o hub da máquina (hoje 12 projetos), somente leitura
- [x] **Rodar a linha de base** na máquina de desenvolvimento (Windows 11, com Ollama e Docker como estão) e registrar em `medicao-runtime.md`: SO, CPU, RAM, versões do painel e do Electron (33.x), nº de projetos, data, e a tabela por estado; copiar o resumo para "Andamento" abaixo
- [x] Documentar o uso em `src/app/README.md` (seção "Medindo o consumo") com a ressalva de que a medição do Electron não empacotado difere pouco do `.exe`; comando para o `.exe`: `npm run build && npm run build:electron:ts && npx electron-builder --dir`, depois `--exe "release/win-unpacked/RAGX Painel.exe"`

## Fora de escopo

- Consertar qualquer consumo (`RAGX-0171` a `0175`); esta tarefa só mede
- Métricas contínuas em produção, telemetria enviada para fora ou tela de diagnóstico no painel
- Medir o `ragx` Python, o servidor MCP ou o Ollama (só os filhos que o painel cria, por contagem e duração)
- Perfil de renderização do React (a `RAGX-0175` mede renders por contador de teste)

## Critérios de aceite

- [x] `node scripts/measure-runtime.mjs --plan visible:1,minimized:1,hidden:1 --label smoke` termina em menos de **4 min** e gera as três seções de estado com **≥ 10 amostras** cada
- [x] A linha de base de 15 min (5 por estado) está em `src/app/docs/medicao-runtime.md` com RAM, CPU e filhos por minuto **por estado**, e o texto confere se a auditoria acertou: **≈290 `git`/min** visível e minimizada com 12 projetos. Se o número diferir mais de 20%, o desvio vai explícito em "Andamento" e nas Notas das `RAGX-0171` a `0173`
- [x] Sem `RAGX_PANEL_METRICS`, nenhuma amostra é criada e nenhum arquivo é escrito (teste); o `ipc.test.ts` continua verde sem canal novo
- [x] O custo do próprio amostrador (`getAppMetrics` + gravação) fica abaixo de **5 ms** por amostra (medido e registrado)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| RAM total do painel, visível, 12 projetos | sem medição | **333 MB** working set (média; pico 337), **213 MB** privada |
| CPU média do conjunto, visível parado / minimizada / oculta | sem medição | **0,1 / 0,2 / 0,1** (p95 0,3 / 0,4 / 0,3; convenção do Electron: por núcleo) |
| Filhos criados por minuto, visível / minimizada | ≈290 (estimado do código) | **`git` 290,8 / 284,3** (oculta 287,3); total ~300/min (+ `docker` 6, `ragx` 2, `tasklist` 2) |
| Tempo de filhos por minuto (ms) | ~5,4 s só das conexões (2,7 s por ciclo de 30 s, auditoria) | **16,8 s/min visível** (`git` 13,9 s); só as conexões: ~2,8 s/min |

Comando: `node scripts/measure-runtime.mjs --plan visible:5,minimized:5,hidden:5 --label baseline-1.0.0-beta.5` (em `src/app`)

## Testes

- [x] `electron/system/__tests__/spawn-counter.test.ts`: agrupa por nome do executável (com caminho completo e `.exe`), soma duração, diferença entre duas fotografias
- [x] `electron/system/__tests__/runtime-metrics.test.ts`: amostrador com métricas, relógio e escrita simulados; 1ª amostra `warmup`; estado e diferenças de filhos corretos; `stop()` encerra; sem a variável nada é criado
- [x] `electron/system/__tests__/runtime-summary.test.ts`: `parsePlan` (válido, estado desconhecido, minutos inválidos) e `summarize` (médias, p95, filhos por minuto) com amostras fixas
- [x] `electron/system/__tests__/exec.test.ts`: `execFileText` registra no contador, inclusive em ENOENT e em lançamento síncrono

## Notas

Confirmar na primeira medição se `percentCPUUsage` é por núcleo (pode passar de 100) ou normalizado pelo total, e registrar a convenção ao lado dos números. `memory.privateBytes` existe só no Windows e no Linux. Os filhos que o próprio Chromium cria (GPU, renderer) já estão em `getAppMetrics`; os que o painel cria vêm do contador, e um processo que o painel lança destacado (`ollama serve`) conta como criação, não como consumo. Medir com o painel **sem** tarefas na fila: uma indexação em andamento distorce a CPU. Se o Electron não empacotado se comportar diferente do `.exe` por mais de 15% na RAM, anotar e refazer a linha de base com `--exe`.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [x] Commit `tipo(escopo): descrição (RAGX-0177)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `electron/system/spawn-counter.ts` (contador por executável, `countSpawn`/`addSpawnDuration`/`snapshot`/`diffSpawns`), ligado a `execFileText`, `defaultSpawn` (rótulo `job`) e `runRagxCommand`; `runtime-metrics.ts` (amostrador a cada 5 s, 1ª amostra `warmup`, custo da amostra anterior na linha seguinte); `runtime-summary.ts` (puro: `parsePlan`, `summarize`, `parseSamples`, `toMarkdownTable`); `main.ts` (`startRuntimeMeasurement` só com `RAGX_PANEL_METRICS`, leva a janela a cada estado pelo plano e chama `app.quit()`, `isDev` falso em modo de medição, `lastSnapshotMs` cronometrado em `refreshSnapshot`; nenhum canal IPC novo); `scripts/measure-runtime.mjs` (fixture de 12 repositórios + hub em pasta temporária, `USERPROFILE`/`HOME` apontados para ela); `src/app/docs/medicao-runtime.md` e a seção "Medindo o consumo" do README do painel. Testes novos: 30 (`spawn-counter` 7, `runtime-metrics` 7, `runtime-summary` 9, `exec` +1, mais os de `git` da 0172 na mesma suíte); `npm test` 901 verdes, `lint` e `tsc` limpos.
- **Linha de base (fixture de 12 projetos, Electron 33.4.11 não empacotado, i5-13600KF, 20 núcleos, 31,8 GB, 15 min).** `git`: **288/min** nos três estados (290,8 visível, 284,3 minimizada, 287,3 oculta): a auditoria (≈290) estava certa, desvio < 2%, e **o consumo não cai com a janela minimizada nem oculta** (é o que a 0171 conserta). RAM ~335 MB working set (~215 MB privada) em qualquer estado. CPU do painel ~0,1 a 0,2% de um núcleo: o custo está nos filhos, **~17 a 20 s/min** (~28 a 33% de um núcleo), 83 a 86% deles do `git`. Conexões: ~10 filhos/min e ~2,8 s/min (a auditoria estimava ~5,4 s/min). Amostrador: 0,4 a 0,7 ms por amostra (meta < 5 ms). O smoke (`--plan visible:1,minimized:1,hidden:1`) rodou em ~3,2 min com 11 a 12 amostras por estado.
- Ressalvas: fixture com projetos pequenos (o `git` real de projetos grandes custa mais); Electron não empacotado (a diferença para o `.exe` não foi medida, então "refazer com `--exe` se passar de 15% na RAM" segue em aberto); fila vazia; não rodei com `--projects real`.
- O `--warmup` do script é aceito mas não faz nada (o amostrador sempre descarta a 1ª amostra).
