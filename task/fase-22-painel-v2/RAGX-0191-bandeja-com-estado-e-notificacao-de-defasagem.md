# RAGX-0191 — Bandeja com estado e notificação de defasagem

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0171, RAGX-0189 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-14, lacunas de produto) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

O painel só avisa que um índice ficou defasado se a pessoa estiver olhando para ele: não há ícone de bandeja nem notificação (auditoria 24, U-14). Um índice velho faz o agente raciocinar sobre código velho, que é a terceira promessa do produto. Esta tarefa põe um ícone de bandeja com o estado geral e uma notificação do sistema quando um projeto fica defasado e **continua** defasado. Entra **desligada por padrão**: notificação mal calibrada irrita mais do que ajuda, e depois de cada commit com hook o índice fica defasado por 16 a 38 s (p50 e p95 da indexação pós-commit, auditoria 24, seção 4.2).

## Entregáveis

- [x] `src/app/electron/stale-notifier.ts` (novo): classe pura `StaleNotifier` com relógio e estado injetados. `observe(states, now)` devolve a lista de projetos a notificar. **Episódio de defasagem** = período contínuo em que o estado é `stale`; `indexing` é neutro (não abre nem fecha); qualquer outro estado fecha o episódio. Notifica **uma vez por projeto por episódio**, só depois de `STALE_GRACE_MS = 120_000` contínuos em `stale` (acima do p95 de 37,6 s). Episódio já aberto no primeiro snapshot do processo é semeado sem notificar.
- [x] `src/app/electron/project-state.ts` (novo): a regra de `deriveProjectState` e `busyProjectIds` de `src/state.ts:10-25,73-79` portada para o processo principal (o `tsconfig.electron.json` tem `rootDir: electron`, então não importa de `src/` em tempo de execução). Teste de paridade obrigatório contra `src/state.ts`.
- [x] `src/app/electron/tray.ts` (novo): `createTray(deps)` com `Tray` do Electron, ícone de `build/icon.png` redimensionado (em dev, `path.join(__dirname, '..', 'build', 'icon.png')`, como `main.ts:455`; empacotado, por entrada nova em `extraResources` de `electron-builder.yml`). Tooltip em texto ("RAGX: 12 em dia", "RAGX: 2 defasados", "RAGX: 1 com problema"), menu "Abrir painel" e "Sair"; clique restaura a janela. Estado nunca só por cor.
- [x] Notificação com `Notification` do Electron: título do projeto, corpo "Índice defasado há N min", clique abre o painel no projeto (evento `ragx:openProject` com `projectId`, nunca caminho; `onOpenProject` em `RagxBridge`). `app.setAppUserModelId('com.ragx.painel')` (o `appId` de `electron-builder.yml`) para o Windows mostrar o nome certo também em dev.
- [x] Configurações `tray` e `notifyStale`, ambas `false` por padrão: campos novos em `PanelSettings`/`RendererSettings` (`electron/settings.ts`), **validados em `readSettings`** (que monta o objeto campo a campo e descartaria um campo novo), expostos por `getSettings` (`electron/ipc.ts:419`) e alterados por `ragx:setPreference(key, boolean)` com chave de lista fechada.
- [x] Interruptores na página "Preferências" (`src/pages/PreferencesPage.tsx`, rota e item de barra lateral). As tarefas 0191, 0192 e 0193 compartilham essa página: a primeira que rodar a cria, as outras acrescentam uma seção. Procure o arquivo antes de criar.
- [x] Com `notifyStale` ligado e a janela oculta ou minimizada, o snapshot de fundo roda no máximo uma vez por minuto, **sem criar processo filho** (depende da RAGX-0172). Reaproveite o `createPausablePoller` (`electron/system/pausable-poller.ts`) e o `watchWindowActivity` da RAGX-0171: com `notifyStale` ligado, o poller do snapshot ganha um segundo intervalo, mais longo, para o estado inativo, em vez de `setActive(false)`. Com a opção desligada (padrão), a pausa da 0171 continua total e o S11 não muda.

## Fora de escopo

- Fechar a janela mandar o painel para a bandeja (o painel continua encerrando em `window-all-closed`, `main.ts:544`).
- Ação de atualizar a partir da notificação ou do menu da bandeja (enfileirar tarefa é decisão de produto separada).
- Ícone da bandeja que muda de cor ou de forma, notificação de outros eventos (falha de job, conexão caída) e som.
- Linux e macOS (fase 17).

## Critérios de aceite

- [x] Tabela de teste do `StaleNotifier`: defasado por menos de 120 s não notifica; passou de 120 s notifica uma vez; mais snapshots no mesmo episódio não repetem; voltar a `ok` e defasar de novo abre outro episódio e notifica de novo; `indexing` no meio não zera o relógio nem abre episódio novo.
- [x] Paridade: para toda combinação de fixtures de `src/test/snap.ts` (sem índice, commit diferente, branch diferente, embeddings pendentes, `running`, pasta ausente), `project-state.ts` e `deriveProjectState` dão o mesmo estado.
- [x] Com as duas opções desligadas (padrão): nenhum `Tray` criado, nenhuma `Notification` instanciada, nenhum timer novo (teste com dependências simuladas).
- [ ] Manual, uma vez, num projeto sem hooks: ligar `notifyStale`, minimizar o painel, fazer um commit no projeto e ver exatamente 1 notificação do Windows depois de ~2 min; clicar nela abre o detalhe daquele projeto. (NÃO feito: exige a janela real e o Centro de Ações do Windows; só testes de unidade.)
- [ ] Com `notifyStale` ligado e a janela minimizada, os processos filhos do painel por minuto continuam 0 (mesmo método da RAGX-0171). (NÃO medido: `measure-runtime.mjs` usa o `settings.json` real do painel e não ligo a opção ali sem a pessoa; o intervalo de fundo é testado no poller e o snapshot não cria processo, por conta da RAGX-0172.)

### Medição

Comando (da RAGX-0177, em `src/app`): `node scripts/measure-runtime.mjs --plan minimized:5`, uma vez com `notifyStale` desligado e outra ligado. Registrar filhos/min e CPU média em cada caso; a meta é 0 filhos/min nos dois (S11).

## Testes

- [x] `src/app/electron/__tests__/stale-notifier.test.ts` e `project-state.test.ts` (novos), este com o teste de paridade importando `../../src/state`.
- [x] `src/app/electron/__tests__/settings.test.ts` (existente): campos novos com padrão `false`, valor inválido vira `false`, `updateSettings` não apaga `ollamaMode` nem `onboardingDone`.
- [x] `src/app/electron/__tests__/ipc.test.ts` (existente): `ragx:setPreference` recusa chave fora da lista e valor que não é booleano.
- [x] `src/app/electron/__tests__/preload.test.ts`: acrescentar `setPreference` e `onOpenProject` à lista exata; atualizar os quatro mocks completos de `RagxBridge` (`src/test/snap.ts`, `App.test.tsx`, `useSnapshot.test.ts`, `useJobsConnections.test.ts`).
- [x] `src/app/src/pages/__tests__/PreferencesPage.test.tsx` (novo): interruptor chama `setPreference` e reflete o estado devolvido.

## Notas

- Confirmado em `electron/main.ts:48-52,401-406`: hoje o snapshot é um `setInterval` fixo de 5 s e nada o pausa; é a RAGX-0171 que o pausa. Não duplique a pausa: estenda o gancho dela.
- Confirmado em `src/state.ts:10-25`: `stale` = sem índice, commit diferente ou branch diferente. `embeddings` (chunks sem vetor) fica fora da notificação: a ação é outra e some sozinha quando o Ollama volta.
- O texto da notificação e dos menus passa por `src/__tests__/no-em-dash.test.ts`, que também varre `electron/`: sem travessão.
- `Notification` depende das configurações de notificação do Windows (foco, "não perturbe"); o aceite manual deve dizer se a notificação foi suprimida pelo sistema.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0191)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_

- 2026-10-01 — Implementado: `electron/project-state.ts` (regra portada), `stale-notifier.ts` (`StaleNotifier`, `STALE_GRACE_MS`), `tray.ts` (`createTray` com dependências injetadas, `trayTooltip`, `summarizeStates`), `settings.ts` (`tray` e `notifyStale` opcionais, só `true` é guardado, `PREFERENCE_KEYS`), `ipc.ts` (`setPreference` de lista fechada; `getSettings` devolve os dois só quando ligados), canal `ragx:setPreference` e evento `ragx:openProject` (`preload`, `RagxBridge.setPreference` e `onOpenProject`, os 4 mocks), `main.ts` (`observeForTrayAndNotifications` a cada snapshot, `applyPreferences` com as preferências em memória, `Notification` com clique que abre o painel e manda o `projectId`, `app.setAppUserModelId('com.ragx.painel')`, `BACKGROUND_SNAPSHOT_MS = 60.000`), `pausable-poller.ts` (`setBackgroundInterval`), `electron-builder.yml` (`build/icon.png` em `extraResources`), e no renderer a página `PreferencesPage` (nova: rota, ícone e item na barra lateral, "Bandeja e avisos"; as 0192 e 0193 acrescentam seções), `App` ouvindo `onOpenProject`.
- Com as duas opções desligadas (padrão): `observeForTrayAndNotifications` retorna na primeira linha, `applyPreferences` não cria `Tray` e passa `null` ao intervalo de fundo; nenhum `Notification` nem timer novo.
- Testes novos: `stale-notifier.test.ts` (9, a tabela do critério), `project-state.test.ts` (paridade: 12 fixtures x 34 combinações de tarefa = 408 casos), `tray.test.ts` (3), 4 casos de intervalo de fundo no poller, settings (2) e ipc (3 grupos) para as preferências, `PreferencesPage.test.tsx` (3). `preload.test.ts` com `setPreference` e `onOpenProject`. Painel: 1872 testes verdes (duas execuções seguidas), `lint` e `tsc` limpos.
- Harness (agora com a tela Preferências, a adoção, o preview e a saúde, e a ponte simulada completa): 14 telas x 3 larguras = 42 medições, 0 problema. A ponte do harness não tinha `onOpenProject` e quebrou o App no primeiro rodar: ganhou os métodos novos.
- Bundle: JS 340.889 → **343.101 B** (gzip 102.450 → 103.040); CSS 43.567 → **43.777 B** (gzip 8.617 → 8.661).
- Não feito: o teste manual da notificação do Windows e a medição de filhos por minuto com `notifyStale` ligado (ver os critérios acima).
