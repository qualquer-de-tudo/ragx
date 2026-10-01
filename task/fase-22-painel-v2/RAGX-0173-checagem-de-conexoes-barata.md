# RAGX-0173 — Checagem de conexões barata

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,75d |
| **Depende de** | `RAGX-0177` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-03) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P3, S11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

A cada 30 s (`CONNECTIONS_POLL_MS`, `electron/main.ts:49`) o painel roda `checkAll`: `ragx --version` (`connections/checks.ts:117`) e, pela detecção do Ollama (`ollama/environment.ts`), `docker --version`, `docker info`, `docker ps -a` e `tasklist`. Medido na auditoria: `ragx --version` 0,9–1,7 s, `docker info` 0,8–1,4 s, `docker ps -a` 0,3 s, `tasklist` 0,3 s, ou **~2,7 s de processos filhos a cada 30 s** (5 spawns por ciclo, ~10 por minuto), o que consome metade do orçamento visível de S11 (≤ 20 filhos/min) antes de contar o snapshot.

## Entregáveis

- [x] **Linha de base**: com a `RAGX-0177`, registrar spawns por minuto e milissegundos de filhos por ciclo da checagem de conexões, e **medir** `http.get` a `localhost:11434` contra `127.0.0.1:11434` no Electron (o Python paga ~2 s por `localhost` no Windows, auditoria I-03; o Node/Electron 33 não foi medido)
- [x] Versão do `ragx` em cache por `(caminho, mtimeMs, tamanho)` do executável: `checkRagx` só chama `ragx --version` quando a assinatura muda ou depois de `resetRagxCache()` (`ragx-exe.ts`) e de uma tarefa `ragx-install`; só resposta com código 0 entra no cache
- [x] `detectDocker` (`ollama/environment.ts`): trocar `docker --version` + `docker info` + `docker ps -a` por **um** `docker ps -a --filter name=^ollama$ --format {{.State}}`: `notFound`/ENOENT = não instalado, código ≠ 0 = instalado e parado, código 0 = rodando (com o estado do container). `docker info` sai (era o mais caro)
- [x] Modo leve para o tick de fundo, `detectOllama(d, { depth: 'light' })`: ping HTTP da API **primeiro** (sem spawn); `docker ps` só se o Docker foi visto instalado e com o daemon de pé na última detecção completa (senão repetir no máximo a cada 5 minutos); `tasklist` só quando houver suspeita de conflito (API respondendo **e** container rodando) ou a API estiver fora do ar. Com API de pé e sem container rodando, `native.running` é inferido `true`. O modo completo (hoje) continua para "Verificar agora", início do app, fim de tarefa e condição de passo da fila
- [x] `main.ts`: o timer chama um handler **interno** de checagem leve (nenhum canal IPC novo; a regra "o renderer só manda `kind` e `projectId`" fica intacta); `getConnections()` do IPC continua completo e coalescido (`createCoalescedRun`, `ipc.ts:205`)
- [x] Trocar `localhost` por `127.0.0.1` em `TAGS_URL` (`environment.ts:28`, `wiring.ts:12`) e em `checks.ts:584` **somente se** a medição mostrar diferença ≥ 100 ms por requisição; o Ollama escuta em `127.0.0.1` por padrão e o container publica `-p 11434:11434`
- [x] Intervalo de fundo: o tick leve continua a 30 s com a janela visível; com a janela fora da vista ele já pausa pela `RAGX-0171`. Atualizar "De onde vêm os dados" em `src/app/README.md`

## Fora de escopo

- Pausar o polling com a janela oculta e a instância única (`RAGX-0171`)
- O snapshot e o `git` (`RAGX-0172`); a telemetria (`RAGX-0174`)
- Mudar o que os cards de conexão mostram, as ações de um clique e o catálogo de tarefas do Ollama
- Detectar a placa de vídeo (`queryGpuNames` já roda uma vez por processo, `onceGpuNames`)

## Critérios de aceite

- [x] Estado estável com Ollama nativo de pé e sem Docker: **0** spawns por ciclo de 30 s além de, no máximo, um `docker ps`; com Docker e container rodando: **1** spawn por ciclo (S11: o painel inteiro fica em ≤ 20 filhos/min visível)
- [x] O custo de filhos por ciclo cai de **~2,7 s** para **< 0,5 s** (medido com o amostrador da `RAGX-0177`)
- [x] "Verificar agora" ainda faz a detecção completa e o resultado de `ragx:connections` é **idêntico** ao de antes para os mesmos fatos (teste com dependências simuladas)
- [x] Os estados `docker`, `native`, `conflict` e `none` continuam corretos nos testes existentes de `ollama/__tests__/environment.test.ts`

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Spawns da checagem por ciclo (30 s) | 5 (`ragx`, `docker` x3, `tasklist`); medido: ~10/min | **1** (`docker ps`): `docker` 2/min, `tasklist` 0,3 e `ragx` 0,5 só no startup |
| Tempo de filhos por ciclo | ~2,7 s (auditoria); medido com a 0177: ~2,8 s/min de conexões | **~0,13 s** por ciclo em regime (`docker ps` ~130 ms); 1,35 s/min no total medido, com 0,8 s do PowerShell das placas de vídeo (uma vez, no startup) |
| `localhost` vs `127.0.0.1` no `http.get` do Electron | **sem diferença**: p50 2,2 a 2,5 ms nos dois (Electron 33.4.11, Node 20.18.3, 8 requisições cada, duas rodadas) | não trocado (a diferença é < 100 ms, o limiar da task) |

Comando: `node scripts/measure-runtime.mjs --plan visible:4 --label depois-0173-conexoes-leves` (da `RAGX-0177`, em `src/app`; a seção está em `src/app/docs/medicao-runtime.md`)

## Testes

- [x] `electron/connections/__tests__/checks.test.ts`: `ragx --version` roda uma vez para a mesma assinatura do executável e de novo quando o `mtime` muda
- [x] `electron/ollama/__tests__/environment.test.ts`: `detectDocker` com um único `exec` cobre não instalado, parado, container ausente, parado e rodando; modo leve não chama `tasklist` sem suspeita e chama no conflito
- [x] `electron/__tests__/ipc.test.ts`: o handler interno não aparece entre os canais registrados e `getConnections` segue coalescido
- [x] `electron/jobs/__tests__/ollama-catalog.test.ts` verde: as condições de passo usam a detecção completa

## Notas

Armadilha: `native.running` inferido só vale no modo leve; as condições da fila (`conditionFrom`, `ollama/wiring.ts`) **sempre** usam o completo, senão `ollama-use-docker` decide com dado inferido. O ENOENT do `docker` é barato mas ainda é um spawn: guardar "não instalado" por 5 minutos. Se a medição mostrar que `docker ps -a` e a API em `127.0.0.1` já bastam para todos os estados sem `tasklist`, remover o `tasklist` do tick de vez e registrar.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [x] Commit `tipo(escopo): descrição (RAGX-0173)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `checkRagx` com a versão em cache por `(caminho, mtimeMs, tamanho)` (`CheckDeps.stat` opcional, `resetRagxVersionCache()` chamado quando uma tarefa `ragx-install` termina; só código 0 entra no cache; sem `stat` o comportamento antigo); `detectDocker` com UM `docker ps` (ENOENT = não instalado, código ≠ 0 = instalado e parado, 0 = rodando com o estado do container; o `docker info` saiu); `detectOllamaLight(d, previous, state, now)` (API primeiro; `docker ps` só se o Docker estava de pé, senão a cada 5 min; `tasklist` só com suspeita de conflito ou API fora do ar com Ollama nativo instalado; `native.running` inferido com a API no ar e sem container rodando) e `createOllamaEnvCache(detect, detectLight).light()` (junta-se a uma completa em andamento, nunca a atropela); `createHandlers.getConnectionsLight()` interno (sem canal de IPC; com uma completa rodando, junta-se a ela) e o timer de 30 s do `main.ts` passou a chamá-lo. Início do app, fim de tarefa, "Verificar agora" e `conditionFrom` seguem com a detecção completa. Testes: `environment-light.test.ts` (15), `ragx-version-cache.test.ts` (5), +2 em `ipc.test.ts`, e os de `environment.test.ts` adaptados ao `docker ps` único (o padrão de comando não definido virou ENOENT); 258 testes das pastas tocadas verdes, `lint` e `tsc` limpos.
- **Medido** (`measure-runtime.mjs --plan visible:4`, 12 projetos, esta máquina tem `docker` e Ollama): filhos **~300/min → 3,1/min** no total, **~17 s/min → 1,35 s/min**. Somado à 0172 (`git` 290,8 → 0), o painel visível passa de ~300 para ~3 filhos por minuto (S11, meta ≤ 20: ✓).
- Divergência da task: o critério "a checagem completa devolve resultado IDÊNTICO ao de antes para os mesmos fatos" vale para os modos `docker`, `native`, `conflict` e `none` (testado), mas **docker instalado com o daemon parado agora responde `installed: true` também quando o `docker ps` falha por outro motivo que não ENOENT** (ex.: permissão); antes, `docker --version` com código ≠ 0 dava "não instalado". É o comportamento que a própria task pede.
- `localhost` não foi trocado por `127.0.0.1` (sem diferença medida no Electron).
