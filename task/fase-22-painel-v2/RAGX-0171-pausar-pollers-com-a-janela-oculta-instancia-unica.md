# RAGX-0171 — Pausar pollers com a janela oculta; instância única

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0177` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-04, U-14) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P1, S11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

Os três pollers do processo principal (`src/app/electron/main.ts`) rodam com a janela minimizada, escondida, com a tela bloqueada ou o computador suspendendo: snapshot a cada 5 s (`SNAPSHOT_POLL_MS`), conexões a cada 30 s e atividade a cada 1,5 s. Lido: não há `visibilitychange`, `minimize`, `powerMonitor` nem `getAppMetrics` no código (grep vazio). Com 12 projetos são **~290 processos `git` por minuto** e ~2,7 s de filhos a cada 30 s, também com o painel fora da vista (S11: meta **0** minimizado). Também não há `requestSingleInstanceLock`: uma segunda abertura sobe outra casca com os mesmos pollers.

## Entregáveis

- [ ] **Linha de base**: ler o resultado da `RAGX-0177` (`src/app/docs/medicao-runtime.md`) e copiar para Medição os filhos/min e a CPU dos estados visível, minimizada e oculta
- [ ] `electron/system/pausable-poller.ts`: `createPausablePoller({ intervalMs, run, now })` com `start()`, `stop()` e `setActive(boolean)`; reagenda com `setTimeout` **depois** que `run` termina (nunca empilha), e ao voltar a ativo dispara `run` na hora se a última execução tem mais de `intervalMs`
- [ ] `electron/system/window-activity.ts`: `watchWindowActivity(win, power, onChange)` calcula `ativo = win.isVisible() && !win.isMinimized() && !tela bloqueada && !suspenso` a partir de `show`, `hide`, `minimize`, `restore` (janela) e `suspend`, `resume`, `lock-screen`, `unlock-screen` (`powerMonitor`, só depois do `ready`); devolve a função de limpeza
- [ ] `main.ts`: `startSnapshotPolling` (linha 401), `startActivityPolling` (423) e `startConnectionsPolling` (434) viram pollers pausáveis ligados ao `watchWindowActivity`; o `setInterval` direto sai. `ACTIVITY_POLL_MS` pode ficar em 1,5 s: o `ActivityTail` lê por deslocamento (`data/activity.ts`) e recupera o atraso sem perder evento
- [ ] Fim de tarefa com a janela oculta (`pushSnapshotNow({ markDirtyIfBusy: true })`, linha 203): marca o snapshot como sujo e **não** reconstrói; a atualização acontece na volta. Tarefas e fila (`JobQueue`) **não** são pausadas
- [ ] Na volta a ativo: um snapshot imediato, uma checagem de conexões só se a última tem mais de 30 s (`createCoalescedRun`, `ipc.ts:205`), uma passada de atividade
- [ ] Corrigir o `win.on('closed')` (linha 512): também zerar `activityTimer`
- [ ] `electron/single-instance.ts`: `acquireSingleInstance(app, { headless, allowMulti })` chama `app.requestSingleInstanceLock()` antes do `whenReady`; segunda instância sai com `app.quit()` e a primeira, no `second-instance`, restaura, mostra e foca a janela. **Os modos `--bootstrap` e `--uninstall-cli` (`HEADLESS`, linha 46) não pegam a trava**: o instalador NSIS os chama com o painel possivelmente aberto. Variável `RAGX_PANEL_ALLOW_MULTI=1` desliga a trava (dev e medição)
- [ ] `webPreferences.backgroundThrottling: true` explícito em `createWindow` (linha 446) e atualizar o `README.md` do painel ("De onde vêm os dados": o polling pausa com a janela fora da vista)

## Fora de escopo

- Trocar `git` por leitura de arquivo (`RAGX-0172`) e baratear a checagem de conexões (`RAGX-0173`): quanto custa cada ciclo é deles; esta tarefa só decide **quando** o ciclo roda
- Bandeja, notificação de defasagem e "fechar para a bandeja" (`RAGX-0191`); CSP e menu (`RAGX-0194`)
- Pausar o renderer (o throttling nativo do Chromium já cuida)

## Critérios de aceite

- [ ] Janela **minimizada** por 5 minutos com 12 projetos: **0** processos filhos criados pelos pollers (S11) e CPU média do conjunto de processos do Electron abaixo de 1% (medido com o amostrador da `RAGX-0177`)
- [ ] Janela **visível**: o intervalo e o conteúdo dos snapshots não mudam (a regressão aparece no teste de integração do `ipc`)
- [ ] Restaurar a janela atualiza o snapshot em até **1 s**; reabrir um painel já aberto foca o existente e não cria segunda janela
- [ ] `RAGX Painel.exe --bootstrap` roda mesmo com o painel aberto (a trava não o bloqueia)

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Filhos/min, 12 projetos, minimizada | ≈290 (auditoria; confirmar na linha de base) | |
| Filhos/min, 12 projetos, visível | ≈290 | (inalterado; cai nas 0172/0173) |
| CPU média minimizada (%) | (0177) | |

Comando: `node scripts/measure-runtime.mjs --plan visible:5,minimized:5,hidden:5` (da `RAGX-0177`, em `src/app`)

## Testes

- [ ] `electron/system/__tests__/pausable-poller.test.ts` (timers falsos): não executa inativo; ao ativar executa na hora só se passou o intervalo; não empilha execuções lentas; `stop()` cancela
- [ ] `electron/system/__tests__/window-activity.test.ts`: `EventEmitter` no lugar da janela e do `powerMonitor`; minimizar, esconder, bloquear a tela e suspender desativam, e restaurar reativa só quando **todas** as condições voltam
- [ ] `electron/__tests__/single-instance.test.ts`: sem trava, a instância sai; `headless` e `allowMulti` não pedem a trava; `second-instance` restaura e foca
- [ ] `electron/__tests__/ipc.test.ts` continua verde (nenhum handler novo; a regra de IPC não muda)

## Notas

Confirmar na prática (com a `RAGX-0177`) se `isVisible()` devolve `false` para janela minimizada no Windows; por isso a conta usa também `isMinimized()`. O app instalado e o de desenvolvimento compartilham o `userData` (`%APPDATA%\app`), logo a trava também bloqueia `npm run dev:electron` com o instalado aberto: é o comportamento desejado, com a variável como saída. Se `powerMonitor` não emitir `lock-screen` no Windows 11 testado, registrar e manter só janela + suspensão.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Commit `tipo(escopo): descrição (RAGX-0171)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
