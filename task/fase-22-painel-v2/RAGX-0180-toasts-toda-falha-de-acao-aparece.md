# RAGX-0180 — Toasts: toda falha de ação aparece

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0179 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-09) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P9) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

Quando enfileirar uma ação falha, a pessoa não vê nada: `enqueue()` e `enqueueConnectionAction()` só fazem `console.error` e devolvem `null` (`src/jobs.ts:4-9` e `:43-46`). Esses dois caminhos servem os botões "Atualizar agora", "Gerar embeddings", "Reindexar do zero", o interruptor dos hooks e as correções do card de conexão: 4 componentes, nenhum com feedback. Só `ProjectsPage` tem um aviso próprio (`useNotice`, `ProjectsPage.tsx:92-109`). Esta tarefa cria um toast único e faz toda falha de ação aparecer, com o motivo.

## Entregáveis

- [ ] `src/toast.ts`: store de módulo (`useSyncExternalStore`) com `notify.error/success/info(texto)`; no máximo 3 visíveis; mesmo texto em 3 s não duplica; prazos reaproveitam `NOTICE_MS = 4000` e `NOTICE_ERROR_MS = 8000` (hoje em `ProjectsPage.tsx`, mover para cá). Módulo de store porque `jobs.ts` não é componente.
- [ ] `src/components/ui/Toaster.tsx`, montado uma vez em `App.tsx` e **nos dois retornos** (shell e onboarding): região `aria-live` sempre presente no DOM, sucesso em `role="status"`, erro em `role="alert"`, "Fechar" (`IconButton` da 0179), pausa o prazo em hover e foco, `z-index: var(--z-toast)` (0178), largura total abaixo de 640 px.
- [ ] `src/ipcError.ts`: `ipcErrorMessage(err)` tira o prefixo que o Electron põe nas rejeições de `invoke` (`Error invoking remote method 'ragx:enqueueJob': Error: pedido recusado: ...`) e deixa só o motivo. Premissa a confirmar no app real; se a mensagem já vier limpa, o helper vira identidade e o teste registra isso.
- [ ] `jobs.ts`: falha de `enqueue` e de `enqueueConnectionAction` chama `notify.error("Não foi possível adicionar à fila: <motivo>")` (mantém o `console.error`). Cobre `JobButton.tsx:33`, `MaintenancePanel.tsx:44`, `ProjectPage.tsx:225` e `ConnectionCard.tsx:148`.
- [ ] Outras falhas silenciosas: `App.tsx:100` (`cancelJob`), `ConnectionCard.tsx:33` (copiar), `AddProjectFlow.tsx:103` (`pickFolder`), `Onboarding.tsx:71` (`setOnboardingDone`, que segue em frente de propósito: avisa que o assistente pode reaparecer).
- [ ] Falha de tarefa em andamento: `useJobFailureToasts(jobs)` em `src/hooks/`, ligado em `App.tsx`; ao ver um `JobView` passar a `failed` depois da primeira lista, `notify.error("<label>: falhou. <error>")`. Tarefas já `failed` na primeira lista e `cancelled` não notificam.
- [ ] `ProjectsPage`: trocar `useNotice` e `.page-notice` (`ProjectsPage.tsx:92-109,138,320-322`; `App.css:1215-1220`) por `notify`, apagando o CSS morto.

## Fora de escopo

- Falha de **leitura** (`getSnapshot`, `getConnections`, `getActivity`): estado de erro explicado é da RAGX-0182.
- Erros em linha que já aparecem e ficam (`callout-error` em `EstimatePanel` e `SecurityPanel`, o `error` do `useClaudeIntegration` no topo e em `ClaudeProfiles`).
- Notificação do sistema operacional e bandeja (RAGX-0191); novo texto de erro vindo do processo principal.

## Critérios de aceite

- [ ] Para cada um dos 7 pontos silenciosos acima, um teste faz a chamada rejeitar e confirma um `role="alert"` com "Não foi possível" e o motivo limpo.
- [ ] Nunca mais de 3 toasts na tela; erro dura 8 s, sucesso 4 s (testes com timers falsos); com o ponteiro em cima, o prazo não corre.
- [ ] A região viva existe antes do primeiro toast (leitor de tela só anuncia o que entra numa região já presente): teste confirma `aria-live` no DOM sem toast.
- [ ] `grep` por `console.error` nos caminhos de ação (`jobs.ts`, `App.tsx`, `ConnectionCard.tsx`, `AddProjectFlow.tsx`) mostra que cada um tem um `notify.error` ao lado.
- [ ] Capturas a 480 e 1280 px com os 3 toasts empilhados: não cobrem o botão que o originou nem estouram a largura (conferir com `getBoundingClientRect().right <= innerWidth`).
- [ ] `prefers-reduced-motion`: sem animação de entrada (já garantido por `index.css:106-113`; teste não precisa, só não usar `!important` novo).

## Testes

- [ ] `src/__tests__/toast.test.tsx` (novo): store, limite de 3, dedupe, prazos, pausa em hover, região viva.
- [ ] `src/__tests__/ipcError.test.ts` (novo): prefixo do Electron removido; mensagem sem prefixo intacta; valor que não é `Error`.
- [ ] `src/pages/__tests__/ProjectPage.test.tsx` (existente): `enqueueJob` rejeitando mostra o toast em `JobButton`, no interruptor de hooks e em "Reindexar do zero".
- [ ] `src/pages/__tests__/ConnectionsPage.test.tsx` e `ProjectsPage.test.tsx` (existentes): falha de ação de conexão; os testes de `useNotice` passam a olhar o toast.
- [ ] `src/__tests__/App.test.tsx` (existente): `cancelJob` rejeitando e tarefa que vira `failed` mostram toast; `failed` já presente na primeira lista, não.

## Notas

- Confirmado em `src/jobs.ts:4-9` e `:43-46` (a auditoria cita as mesmas linhas) e em `App.tsx:99-101`. `ProjectsPage.tsx:143-149` já mostrava o erro, mas só nessa tela; o resto era silêncio.
- `src/__tests__/no-em-dash.test.ts` falha com "—" em qualquer texto novo de `src/` e `electron/`.
- Toast não substitui o estado na tela: o botão continua mostrando "Na fila"/"Rodando" pela fila; o toast só cobre o que a fila nunca chegou a ver.
- O toast de erro nunca repete argumento nem caminho; só o motivo que o processo principal já devolve (a regra de IPC não muda).

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0180)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
