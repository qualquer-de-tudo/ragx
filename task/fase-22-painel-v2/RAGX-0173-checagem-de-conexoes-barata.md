# RAGX-0173 — Checagem de conexões barata

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,75d |
| **Depende de** | `RAGX-0177` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-03) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P3, S11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

A cada 30 s (`CONNECTIONS_POLL_MS`, `electron/main.ts:49`) o painel roda `checkAll`: `ragx --version` (`connections/checks.ts:117`) e, pela detecção do Ollama (`ollama/environment.ts`), `docker --version`, `docker info`, `docker ps -a` e `tasklist`. Medido na auditoria: `ragx --version` 0,9–1,7 s, `docker info` 0,8–1,4 s, `docker ps -a` 0,3 s, `tasklist` 0,3 s, ou **~2,7 s de processos filhos a cada 30 s** (5 spawns por ciclo, ~10 por minuto), o que consome metade do orçamento visível de S11 (≤ 20 filhos/min) antes de contar o snapshot.

## Entregáveis

- [ ] **Linha de base**: com a `RAGX-0177`, registrar spawns por minuto e milissegundos de filhos por ciclo da checagem de conexões, e **medir** `http.get` a `localhost:11434` contra `127.0.0.1:11434` no Electron (o Python paga ~2 s por `localhost` no Windows, auditoria I-03; o Node/Electron 33 não foi medido)
- [ ] Versão do `ragx` em cache por `(caminho, mtimeMs, tamanho)` do executável: `checkRagx` só chama `ragx --version` quando a assinatura muda ou depois de `resetRagxCache()` (`ragx-exe.ts`) e de uma tarefa `ragx-install`; só resposta com código 0 entra no cache
- [ ] `detectDocker` (`ollama/environment.ts`): trocar `docker --version` + `docker info` + `docker ps -a` por **um** `docker ps -a --filter name=^ollama$ --format {{.State}}`: `notFound`/ENOENT = não instalado, código ≠ 0 = instalado e parado, código 0 = rodando (com o estado do container). `docker info` sai (era o mais caro)
- [ ] Modo leve para o tick de fundo, `detectOllama(d, { depth: 'light' })`: ping HTTP da API **primeiro** (sem spawn); `docker ps` só se o Docker foi visto instalado e com o daemon de pé na última detecção completa (senão repetir no máximo a cada 5 minutos); `tasklist` só quando houver suspeita de conflito (API respondendo **e** container rodando) ou a API estiver fora do ar. Com API de pé e sem container rodando, `native.running` é inferido `true`. O modo completo (hoje) continua para "Verificar agora", início do app, fim de tarefa e condição de passo da fila
- [ ] `main.ts`: o timer chama um handler **interno** de checagem leve (nenhum canal IPC novo; a regra "o renderer só manda `kind` e `projectId`" fica intacta); `getConnections()` do IPC continua completo e coalescido (`createCoalescedRun`, `ipc.ts:205`)
- [ ] Trocar `localhost` por `127.0.0.1` em `TAGS_URL` (`environment.ts:28`, `wiring.ts:12`) e em `checks.ts:584` **somente se** a medição mostrar diferença ≥ 100 ms por requisição; o Ollama escuta em `127.0.0.1` por padrão e o container publica `-p 11434:11434`
- [ ] Intervalo de fundo: o tick leve continua a 30 s com a janela visível; com a janela fora da vista ele já pausa pela `RAGX-0171`. Atualizar "De onde vêm os dados" em `src/app/README.md`

## Fora de escopo

- Pausar o polling com a janela oculta e a instância única (`RAGX-0171`)
- O snapshot e o `git` (`RAGX-0172`); a telemetria (`RAGX-0174`)
- Mudar o que os cards de conexão mostram, as ações de um clique e o catálogo de tarefas do Ollama
- Detectar a placa de vídeo (`queryGpuNames` já roda uma vez por processo, `onceGpuNames`)

## Critérios de aceite

- [ ] Estado estável com Ollama nativo de pé e sem Docker: **0** spawns por ciclo de 30 s além de, no máximo, um `docker ps`; com Docker e container rodando: **1** spawn por ciclo (S11: o painel inteiro fica em ≤ 20 filhos/min visível)
- [ ] O custo de filhos por ciclo cai de **~2,7 s** para **< 0,5 s** (medido com o amostrador da `RAGX-0177`)
- [ ] "Verificar agora" ainda faz a detecção completa e o resultado de `ragx:connections` é **idêntico** ao de antes para os mesmos fatos (teste com dependências simuladas)
- [ ] Os estados `docker`, `native`, `conflict` e `none` continuam corretos nos testes existentes de `ollama/__tests__/environment.test.ts`

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Spawns da checagem por ciclo (30 s) | 5 (`ragx`, `docker` x3, `tasklist`) | |
| Tempo de filhos por ciclo | ~2,7 s (auditoria) | |
| `localhost` vs `127.0.0.1` no `http.get` do Electron | (medir) | |

Comando: `node scripts/measure-runtime.mjs --plan visible:3` (da `RAGX-0177`, em `src/app`)

## Testes

- [ ] `electron/connections/__tests__/checks.test.ts`: `ragx --version` roda uma vez para a mesma assinatura do executável e de novo quando o `mtime` muda
- [ ] `electron/ollama/__tests__/environment.test.ts`: `detectDocker` com um único `exec` cobre não instalado, parado, container ausente, parado e rodando; modo leve não chama `tasklist` sem suspeita e chama no conflito
- [ ] `electron/__tests__/ipc.test.ts`: o handler interno não aparece entre os canais registrados e `getConnections` segue coalescido
- [ ] `electron/jobs/__tests__/ollama-catalog.test.ts` verde: as condições de passo usam a detecção completa

## Notas

Armadilha: `native.running` inferido só vale no modo leve; as condições da fila (`conditionFrom`, `ollama/wiring.ts`) **sempre** usam o completo, senão `ollama-use-docker` decide com dado inferido. O ENOENT do `docker` é barato mas ainda é um spawn: guardar "não instalado" por 5 minutos. Se a medição mostrar que `docker ps -a` e a API em `127.0.0.1` já bastam para todos os estados sem `tasklist`, remover o `tasklist` do tick de vez e registrar.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Commit `tipo(escopo): descrição (RAGX-0173)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
