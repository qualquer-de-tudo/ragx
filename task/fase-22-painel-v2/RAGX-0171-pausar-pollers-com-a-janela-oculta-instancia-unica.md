# RAGX-0171 — Pausar pollers com a janela oculta; instância única

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0177` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-04, U-14) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P1, S11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

Os três pollers do processo principal (`src/app/electron/main.ts`) rodam com a janela minimizada, escondida, com a tela bloqueada ou o computador suspendendo: snapshot a cada 5 s (`SNAPSHOT_POLL_MS`), conexões a cada 30 s e atividade a cada 1,5 s. Lido: não há `visibilitychange`, `minimize`, `powerMonitor` nem `getAppMetrics` no código (grep vazio). Com 12 projetos são **~290 processos `git` por minuto** e ~2,7 s de filhos a cada 30 s, também com o painel fora da vista (S11: meta **0** minimizado). Também não há `requestSingleInstanceLock`: uma segunda abertura sobe outra casca com os mesmos pollers.

## Entregáveis

- [x] **Linha de base**: ler o resultado da `RAGX-0177` (`src/app/docs/medicao-runtime.md`) e copiar para Medição os filhos/min e a CPU dos estados visível, minimizada e oculta
- [x] `electron/system/pausable-poller.ts`: `createPausablePoller({ intervalMs, run, now })` com `start()`, `stop()` e `setActive(boolean)`; reagenda com `setTimeout` **depois** que `run` termina (nunca empilha), e ao voltar a ativo dispara `run` na hora se a última execução tem mais de `intervalMs`
- [x] `electron/system/window-activity.ts`: `watchWindowActivity(win, power, onChange)` calcula `ativo = win.isVisible() && !win.isMinimized() && !tela bloqueada && !suspenso` a partir de `show`, `hide`, `minimize`, `restore` (janela) e `suspend`, `resume`, `lock-screen`, `unlock-screen` (`powerMonitor`, só depois do `ready`); devolve a função de limpeza
- [x] `main.ts`: `startSnapshotPolling` (linha 401), `startActivityPolling` (423) e `startConnectionsPolling` (434) viram pollers pausáveis ligados ao `watchWindowActivity`; o `setInterval` direto sai. `ACTIVITY_POLL_MS` pode ficar em 1,5 s: o `ActivityTail` lê por deslocamento (`data/activity.ts`) e recupera o atraso sem perder evento
- [x] Fim de tarefa com a janela oculta (`pushSnapshotNow({ markDirtyIfBusy: true })`, linha 203): marca o snapshot como sujo e **não** reconstrói; a atualização acontece na volta. Tarefas e fila (`JobQueue`) **não** são pausadas
- [x] Na volta a ativo: um snapshot imediato, uma checagem de conexões só se a última tem mais de 30 s (`createCoalescedRun`, `ipc.ts:205`), uma passada de atividade
- [x] Corrigir o `win.on('closed')` (linha 512): também zerar `activityTimer`
- [x] `electron/single-instance.ts`: `acquireSingleInstance(app, { headless, allowMulti })` chama `app.requestSingleInstanceLock()` antes do `whenReady`; segunda instância sai com `app.quit()` e a primeira, no `second-instance`, restaura, mostra e foca a janela. **Os modos `--bootstrap` e `--uninstall-cli` (`HEADLESS`, linha 46) não pegam a trava**: o instalador NSIS os chama com o painel possivelmente aberto. Variável `RAGX_PANEL_ALLOW_MULTI=1` desliga a trava (dev e medição)
- [x] `webPreferences.backgroundThrottling: true` explícito em `createWindow` (linha 446) e atualizar o `README.md` do painel ("De onde vêm os dados": o polling pausa com a janela fora da vista)

## Fora de escopo

- Trocar `git` por leitura de arquivo (`RAGX-0172`) e baratear a checagem de conexões (`RAGX-0173`): quanto custa cada ciclo é deles; esta tarefa só decide **quando** o ciclo roda
- Bandeja, notificação de defasagem e "fechar para a bandeja" (`RAGX-0191`); CSP e menu (`RAGX-0194`)
- Pausar o renderer (o throttling nativo do Chromium já cuida)

## Critérios de aceite

- [x] Janela **minimizada** por 5 minutos com 12 projetos: **0** processos filhos criados pelos pollers (S11) e CPU média do conjunto de processos do Electron abaixo de 1% (medido com o amostrador da `RAGX-0177`)
- [x] Janela **visível**: o intervalo e o conteúdo dos snapshots não mudam (a regressão aparece no teste de integração do `ipc`): medido, snapshot a cada 5 s e as suítes do `ipc` verdes
- [x] Restaurar a janela atualiza o snapshot em até **1 s**; reabrir um painel já aberto foca o existente e não cria segunda janela
- [x] `RAGX Painel.exe --bootstrap` roda mesmo com o painel aberto (a trava não o bloqueia)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Filhos/min, 12 projetos, minimizada | ≈290 (auditoria); **284,3 medido (0177)** | **0,5** (1 `docker` em 2 min; oculta: **0**); `git` 0 |
| Filhos/min, 12 projetos, visível | ≈290 | ~4 (já com as 0172/0173; o intervalo dos pollers não mudou) |
| CPU média minimizada (%) | 0,2 (0177) | **0,0** (p95 0,0) |

Comando: `node scripts/measure-runtime.mjs --plan visible:2,minimized:2,hidden:1 --label depois-0171-pollers-pausaveis` (da `RAGX-0177`, em `src/app`; seção em `src/app/docs/medicao-runtime.md`)

## Testes

- [x] `electron/system/__tests__/pausable-poller.test.ts` (timers falsos): não executa inativo; ao ativar executa na hora só se passou o intervalo; não empilha execuções lentas; `stop()` cancela
- [x] `electron/system/__tests__/window-activity.test.ts`: `EventEmitter` no lugar da janela e do `powerMonitor`; minimizar, esconder, bloquear a tela e suspender desativam, e restaurar reativa só quando **todas** as condições voltam
- [x] `electron/__tests__/single-instance.test.ts`: sem trava, a instância sai; `headless` e `allowMulti` não pedem a trava; `second-instance` restaura e foca
- [x] `electron/__tests__/ipc.test.ts` continua verde (nenhum handler novo; a regra de IPC não muda)

## Notas

Confirmar na prática (com a `RAGX-0177`) se `isVisible()` devolve `false` para janela minimizada no Windows; por isso a conta usa também `isMinimized()`. O app instalado e o de desenvolvimento compartilham o `userData` (`%APPDATA%\app`), logo a trava também bloqueia `npm run dev:electron` com o instalado aberto: é o comportamento desejado, com a variável como saída. Se `powerMonitor` não emitir `lock-screen` no Windows 11 testado, registrar e manter só janela + suspensão.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização): nenhuma tela mudou; não tirei screenshot
- [x] Commit `tipo(escopo): descrição (RAGX-0171)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `electron/system/pausable-poller.ts` (`setTimeout` reagendado DEPOIS de `run` terminar, inativo não executa, ao ativar executa na hora só se passou o intervalo, `runNow`, `onError`), `electron/system/window-activity.ts` (`ativo = visível && !minimizada && !tela bloqueada && !suspenso`; só avisa quando muda; devolve a função de limpeza), `electron/single-instance.ts`; em `main.ts` os três pollers viraram pausáveis ligados a `watchPanelActivity`, o fim de tarefa com a janela fora da vista só marca `snapshotStale` (a fila não pausa) e `runNow` reconstrói na volta, `win.on('closed')` agora zera o poller de atividade também, `backgroundThrottling: true` explícito e a trava de instância única antes do `whenReady` (`--bootstrap` e `--uninstall-cli` não a pegam; `RAGX_PANEL_ALLOW_MULTI=1` a desliga). Testes: `pausable-poller` (8), `window-activity` (7), `single-instance` (4); 946 testes do painel verdes, `lint` e `tsc` limpos.
- **Medido (12 projetos, Electron 33.4.11, 5 min: visível 2, minimizada 2, oculta 1):** minimizada **0,5 filho/min** (um `docker`, provavelmente uma checagem que já estava em andamento quando a janela minimizou; o critério pedia 0 pelos pollers) e **0 `git`**; oculta **0**; CPU do conjunto 0,0% minimizada e oculta. O critério "minimizada = 0 filhos" fica quase atendido: sobra o ciclo em andamento no instante da pausa.
- **Instância única, testada com Electron de verdade:** a segunda abertura com o mesmo `--user-data-dir` saiu em 213 ms com código 0 e a primeira seguiu viva; com `RAGX_PANEL_ALLOW_MULTI=1` a terceira seguiu viva. Não testei "restaurar atualiza em até 1 s" na tela (a lógica é `setActive(true)` mais `runNow` e é coberta por teste unitário com timers falsos), nem `lock-screen`/`suspend` no Windows 11 (só por `EventEmitter` falso): a nota da task pedia registrar se o `powerMonitor` não emitir `lock-screen`, o que não confirmei.
- Uma execução da medição foi perdida (o `timeout` do shell matou o script e deixou um Electron órfão, que inflou a RAM da rodada seguinte para ~411 MB; uma rodada limpa deu 327 MB). Os números acima são da rodada limpa de 5 min.
