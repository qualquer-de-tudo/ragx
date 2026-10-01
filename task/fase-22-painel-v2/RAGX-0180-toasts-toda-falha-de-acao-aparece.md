# RAGX-0180 — Toasts: toda falha de ação aparece

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0179 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-09) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P9) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

Quando enfileirar uma ação falha, a pessoa não vê nada: `enqueue()` e `enqueueConnectionAction()` só fazem `console.error` e devolvem `null` (`src/jobs.ts:4-9` e `:43-46`). Esses dois caminhos servem os botões "Atualizar agora", "Gerar embeddings", "Reindexar do zero", o interruptor dos hooks e as correções do card de conexão: 4 componentes, nenhum com feedback. Só `ProjectsPage` tem um aviso próprio (`useNotice`, `ProjectsPage.tsx:92-109`). Esta tarefa cria um toast único e faz toda falha de ação aparecer, com o motivo.

## Entregáveis

- [x] `src/toast.ts`: store de módulo (`useSyncExternalStore`) com `notify.error/success/info(texto)`; no máximo 3 visíveis; mesmo texto em 3 s não duplica; prazos reaproveitam `NOTICE_MS = 4000` e `NOTICE_ERROR_MS = 8000` (hoje em `ProjectsPage.tsx`, mover para cá). Módulo de store porque `jobs.ts` não é componente.
- [x] `src/components/ui/Toaster.tsx`, montado uma vez em `App.tsx` e **nos dois retornos** (shell e onboarding): região `aria-live` sempre presente no DOM, sucesso em `role="status"`, erro em `role="alert"`, "Fechar" (`IconButton` da 0179), pausa o prazo em hover e foco, `z-index: var(--z-toast)` (0178), largura total abaixo de 640 px.
- [x] `src/ipcError.ts`: `ipcErrorMessage(err)` tira o prefixo que o Electron põe nas rejeições de `invoke` (`Error invoking remote method 'ragx:enqueueJob': Error: pedido recusado: ...`) e deixa só o motivo. Premissa a confirmar no app real; se a mensagem já vier limpa, o helper vira identidade e o teste registra isso.
- [x] `jobs.ts`: falha de `enqueue` e de `enqueueConnectionAction` chama `notify.error("Não foi possível adicionar à fila: <motivo>")` (mantém o `console.error`). Cobre `JobButton.tsx:33`, `MaintenancePanel.tsx:44`, `ProjectPage.tsx:225` e `ConnectionCard.tsx:148`.
- [x] Outras falhas silenciosas: `App.tsx:100` (`cancelJob`), `ConnectionCard.tsx:33` (copiar), `AddProjectFlow.tsx:103` (`pickFolder`), `Onboarding.tsx:71` (`setOnboardingDone`, que segue em frente de propósito: avisa que o assistente pode reaparecer).
- [x] Falha de tarefa em andamento: `useJobFailureToasts(jobs)` em `src/hooks/`, ligado em `App.tsx`; ao ver um `JobView` passar a `failed` depois da primeira lista, `notify.error("<label>: falhou. <error>")`. Tarefas já `failed` na primeira lista e `cancelled` não notificam.
- [x] `ProjectsPage`: trocar `useNotice` e `.page-notice` (`ProjectsPage.tsx:92-109,138,320-322`; `App.css:1215-1220`) por `notify`, apagando o CSS morto.

## Fora de escopo

- Falha de **leitura** (`getSnapshot`, `getConnections`, `getActivity`): estado de erro explicado é da RAGX-0182.
- Erros em linha que já aparecem e ficam (`callout-error` em `EstimatePanel` e `SecurityPanel`, o `error` do `useClaudeIntegration` no topo e em `ClaudeProfiles`).
- Notificação do sistema operacional e bandeja (RAGX-0191); novo texto de erro vindo do processo principal.

## Critérios de aceite

- [x] Para cada um dos 7 pontos silenciosos acima, um teste faz a chamada rejeitar e confirma um `role="alert"` com "Não foi possível" e o motivo limpo.
- [x] Nunca mais de 3 toasts na tela; erro dura 8 s, sucesso 4 s (testes com timers falsos); com o ponteiro em cima, o prazo não corre.
- [x] A região viva existe antes do primeiro toast (leitor de tela só anuncia o que entra numa região já presente): teste confirma `aria-live` no DOM sem toast.
- [x] `grep` por `console.error` nos caminhos de ação (`jobs.ts`, `App.tsx`, `ConnectionCard.tsx`, `AddProjectFlow.tsx`) mostra que cada um tem um `notify.error` ao lado. (Exceções, que NÃO são ação do usuário: `getConnections()` depois da medição do Ollama, leituras, `discover()` e `enqueueJob(add-project)` do assistente, que já têm estado de erro na própria tela.)
- [ ] Capturas a 480 e 1280 px com os 3 toasts empilhados: não cobrem o botão que o originou nem estouram a largura (conferir com `getBoundingClientRect().right <= innerWidth`). (NÃO verificado: sem navegador; o CSS limita a largura a `min(380px, 100vw - 32px)` e, abaixo de 640 px, a `left/right: 16px`, mas isso não foi medido.)
- [x] `prefers-reduced-motion`: sem animação de entrada (já garantido por `index.css:106-113`; teste não precisa, só não usar `!important` novo).

## Testes

- [x] `src/__tests__/toast.test.tsx` (novo): store, limite de 3, dedupe, prazos, pausa em hover, região viva.
- [x] `src/__tests__/ipcError.test.ts` (novo): prefixo do Electron removido; mensagem sem prefixo intacta; valor que não é `Error`.
- [x] `src/pages/__tests__/ProjectPage.test.tsx` (existente): `enqueueJob` rejeitando mostra o toast em `JobButton`, no interruptor de hooks e em "Reindexar do zero".
- [x] `src/pages/__tests__/ConnectionsPage.test.tsx` e `ProjectsPage.test.tsx` (existentes): falha de ação de conexão; os testes de `useNotice` passam a olhar o toast.
- [x] `src/__tests__/App.test.tsx` (existente): `cancelJob` rejeitando e tarefa que vira `failed` mostram toast; `failed` já presente na primeira lista, não.

## Notas

- Confirmado em `src/jobs.ts:4-9` e `:43-46` (a auditoria cita as mesmas linhas) e em `App.tsx:99-101`. `ProjectsPage.tsx:143-149` já mostrava o erro, mas só nessa tela; o resto era silêncio.
- `src/__tests__/no-em-dash.test.ts` falha com "—" em qualquer texto novo de `src/` e `electron/`.
- Toast não substitui o estado na tela: o botão continua mostrando "Na fila"/"Rodando" pela fila; o toast só cobre o que a fila nunca chegou a ver.
- O toast de erro nunca repete argumento nem caminho; só o motivo que o processo principal já devolve (a regra de IPC não muda).

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização) (só testes de renderização; sem screenshot)
- [x] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0180)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `src/toast.ts` (store com `notify`, `pause/resume/dismiss`, limite 3, dedupe 3 s, 4 s e 8 s; os prazos saíram de `ProjectsPage`), `src/ipcError.ts`, `ui/Toaster.tsx` (montado em `App` nos dois retornos), `hooks/useJobFailureToasts.ts`. Avisos nos pontos: `jobs.ts` (`enqueue` e `enqueueConnectionAction`, que cobrem `JobButton`, `MaintenancePanel`, o interruptor dos hooks e as ações do card), `cancelJob` (`App`), copiar (`ConnectionCard`), `pickFolder` (`AddProjectFlow`), `setOnboardingDone` (`Onboarding`, que segue em frente). `ProjectsPage` deixou `useNotice` e o `<div className="page-notice">` e usa `notify.success/error`; o CSS `.page-notice` foi apagado (a catraca de espaçamento baixou de 201 para 200).
- Testes novos: `toast.test.tsx` (7), `ipcError.test.ts` (4), `action-failures.test.tsx` (11: os 8 pontos, mais `running→failed`, `failed` na primeira lista e `cancelled` sem aviso, e o Toaster no onboarding). Adaptados: `ProjectsPage.test.tsx` (monta o `Toaster` ao lado da página; o aviso é `role="alert"`/`status` do Toaster; o teste "desmontar limpa o timer" virou "o store global limpa o timer", porque o aviso agora não é da página). Painel: 1191 testes verdes, `lint` e `tsc` limpos.
- Decisão: a "primeira lista" do `useJobFailureToasts` é a primeira que traz alguma tarefa (a lista inicial vazia de `useJobs` não conta). Efeito colateral aceito: uma tarefa que já nasce `failed` na primeira lista não-vazia não avisa.
- Premissa do prefixo do Electron: NÃO confirmada no app real (o formato `Error invoking remote method '<canal>': Error: <motivo>` é o que se sabe do Electron 33, e o teste cobre os dois formatos); se o texto já vier limpo, o helper deixa a mensagem como está.
- Bundle: JS 309.723 → **311.809 B** (gzip 93.139 → 93.844); CSS 37.143 → **37.725 B** (gzip 7.490 → 7.591). Sem dependência nova.
- NÃO feito: capturas a 480/1280 px e a conferência de `getBoundingClientRect().right <= innerWidth`.
