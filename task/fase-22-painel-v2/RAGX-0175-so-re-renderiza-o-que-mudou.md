# RAGX-0175 — Só re-renderiza o que mudou

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0177` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-05) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P5) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

O renderer re-renderiza **tudo** a cada 5 s mesmo sem nada novo, por três causas lidas no código: (1) o snapshot chega por IPC com `generatedAt` novo e objetos novos (a serialização cria identidades novas), e `useSnapshot` o grava como está (`src/hooks/useSnapshot.ts:26`), refazendo `projects` em `App.tsx` (`useMemo` sobre `snapshot`); (2) `useNow(5000)` (`App.tsx:41`) faz o `App` inteiro renderizar a cada tick, e `liveProjectIds` (`activity.ts:23`) devolve um `Set` **novo** sempre; (3) nenhum componente usa `React.memo`, e `onOpen`/`onAction` são funções inline (`App.tsx` `onOpen={(id) => setRoute(...)}`, `ProjectsPage.tsx:307`). Com 12 projetos são ~24 renders do `App` por minuto e ~288 de `ProjectCard`, com os dados parados.

## Entregáveis

- [x] **Linha de base**: contar renderizações de `ProjectCard` em 60 s parado com 12 projetos (teste com contador, abaixo) e a CPU do processo de renderização da janela visível pelo amostrador da `RAGX-0177`; registrar em Andamento
- [x] `src/snapshotShare.ts`: `shareSnapshot(prev, next)` devolve `prev` quando `next` é igual a ele **ignorando `generatedAt`**, e senão um objeto novo que **reaproveita a referência** de cada `ProjectSnapshot` inalterado (comparação estrutural pequena, sem biblioteca). `useSnapshot` (linha 26 e a resposta inicial) passa por ela
- [x] Processo principal: `pushSnapshotNow` (`electron/main.ts:208`) não faz `webContents.send('ragx:snapshot', ...)` quando o snapshot (sem `generatedAt`) é igual ao último enviado; `latestSnapshot` e o handler `getSnapshot` seguem atualizados. Nenhum canal novo
- [x] Relógio único e compartilhado: trocar `useNow(5000)` do `App` por `useClock(intervalMs)` baseado em `useSyncExternalStore` com **um** `setInterval` para o app inteiro; o `App` deixa de assinar o relógio. `liveIds` passa a vir de `useLiveIds(activity)`, que recalcula a cada 5 s mas **devolve o mesmo `Set`** quando a pertença não mudou
- [x] Rótulos relativos não podem congelar: hoje "há 3 min" só atualiza porque tudo renderiza a cada 5 s (`formatRelative` usa `new Date()` no render, `format.ts:25`). Criar `<RelativeTime iso>` (folha que assina `useClock(60_000)`) e usá-lo em `ProjectCard.tsx:122`, na linha da lista (`ProjectsPage.tsx:267`) e em `ProjectPage.tsx:190`; só a folha re-renderiza por minuto
- [x] `React.memo` em `ProjectCard`, nas linhas da lista e nos cards de `ConnectionCard`; handlers estáveis: `onOpen` do `App` e `onAction` do `ProjectsPage` com `useCallback` e o id/projeto passados como argumento (`onAction(project, kind)`), sem closure por linha
- [x] Fila (`useJobs`) e conexões: `setJobs`/`setConnections` só quando o conteúdo mudou (mesma comparação estrutural)

## Fora de escopo

- Ler menos dados no processo principal (`RAGX-0172`, `RAGX-0174`) e pausar com a janela oculta (`RAGX-0171`)
- Virtualização de listas, biblioteca de estado ou de UI (decisão da spec: CSS e estado próprios)
- Skeletons e primeira pintura com o último snapshot (`RAGX-0182`), toasts (`RAGX-0180`)
- Mudar o formato de `Snapshot` ou o contrato de IPC

## Critérios de aceite

- [x] Com 12 projetos e **dados parados** por 60 s, `ProjectCard` renderiza **≤ 12** vezes no total (só a montagem; antes ≈ 288) e o `App`, **≤ 1** (o relógio de 60 s não o atinge)
- [x] Quando muda **um** projeto, só o card dele re-renderiza (os outros 11 mantêm a referência)
- [x] "há N min" continua avançando sozinho: depois de 60 s simulados o texto do card muda (teste), sem snapshot novo
- [x] "Em uso agora" continua apagando 1 minuto após o último evento
- [x] Nenhuma mudança visual: os testes de página (`ProjectsPage`, `ProjectPage`, `ActivityPage`) seguem verdes sem alterar asserções de texto

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Renders de `ProjectCard` em 60 s parado, 12 projetos | **300** (12 da montagem + 288) | **12** (só a montagem) |
| Renders do `App` em 60 s parado | **24** | **0** |
| CPU média do renderer, janela visível e parada | não medida (exige o Electron real; ver Andamento) | não medida |

Comando: `npx vitest run src/__tests__/render-count.test.tsx` e `node scripts/measure-runtime.mjs --plan visible:3` (da `RAGX-0177`, em `src/app`)

## Testes

- [x] `src/__tests__/snapshotShare.test.ts`: mesmo conteúdo com `generatedAt` diferente devolve `prev`; um projeto alterado troca só a referência dele; projeto removido/novo; ordem preservada
- [x] `src/__tests__/render-count.test.tsx`: `App` com a ponte falsa (como `App.test.tsx`), 12 projetos de `src/test/snap.ts`, `vi.useFakeTimers`; empurra o mesmo snapshot 12 vezes e avança 60 s contando renders de `ProjectCard` por `vi.mock` que envolve o componente real. Falha antes da correção
- [x] `src/hooks/__tests__/useSnapshot.test.ts`: o teste existente de ordem (`isNewer`) segue verde; novo caso de referência estável
- [x] `src/components/shell/__tests__/shell.test.tsx` e `src/pages/__tests__/ProjectsPage.test.tsx` verdes
- [x] `electron/__tests__/ipc.test.ts` verde (nenhum handler novo)

## Notas

Armadilha central: tirar o re-render periódico **sem** a folha `<RelativeTime>` congela os rótulos de tempo e a idade dos erros, uma regressão silenciosa que nenhum teste de snapshot pega; por isso o teste de "há N min avançando" é obrigatório. O `memo` só vale com props estáveis: `job`, `active` e `failure` vêm de `activeJobFor`/`lastFailureFor` (`state.ts`) e precisam devolver a mesma referência enquanto o conteúdo não muda; se devolverem objetos novos, memoizá-los em `ProjectsPage` por `useMemo` com a lista de jobs. Se a medição mostrar que o custo de render já é desprezível (menos de 1% de CPU), manter a supressão no processo principal (menos IPC) e a folha de tempo, e registrar o número.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Nenhuma regressão visual nas telas afetadas (teste de renderização: os testes de página seguem verdes sem mudar asserção; sem screenshot)
- [x] Commit `tipo(escopo): descrição (RAGX-0175)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Linha de base medida pelo próprio `render-count.test.tsx` antes de mexer (conta `ProjectNumbers`, filho sem memo do card, e `Sidebar`, filho do `App`): 12 projetos, 12 pushes iguais de 5 s e 60 s simulados = **300** renders de card (12 + 288) e **24** do `App`, como o código indicava.
- Implementado: `src/snapshotShare.ts` (`sameData`, `shareById`, `shareSnapshot`; `useSnapshot`, `useJobs` e `useConnections` passam por ela e mantêm a referência quando nada mudou); `electron/data/snapshot-gate.ts` (`createSnapshotGate`, ligado em `pushSnapshotNow`, zerado ao criar a janela; nenhum canal novo); `src/hooks/useClock.ts` (`useClock` com um `setInterval` por intervalo e só enquanto há assinante, `useLiveIds` devolvendo o mesmo `Set`); `<RelativeTime>` em `ProjectCard`, linha da lista, `ProjectPage`, `Timeline` e na "Última chamada MCP" do `ConnectionCard`; `memo` em `ProjectCard`, `ProjectRow` (nova, extraída da tabela) e `ConnectionCard`; `onOpen`/`onAction(project, kind)` estáveis (`queueAction` lê a fila por ref). `ActivityPage` assina o próprio relógio de 5 s (a prop `now` virou opcional, usada só nos testes).
- **Depois**: o mesmo teste dá **12** renders de card e **0** do `App` em 60 s; mudando um só projeto, **1** card renderiza (`telemetry.totalCalls`); "Indexado há 2 min" vira "há 3 min" em 60 s simulados sem snapshot novo; "em uso agora" some depois de 1 min. Painel: 983 testes verdes, `lint` e `tsc` dos dois projetos limpos; `tests/security` verde (nada de Python mudou).
- Desvio: `useSnapshot.test.ts` comparava `toBe(newer)` com dois snapshots de projetos vazios que só diferiam em `generatedAt`; com a regra nova isso devolve o objeto anterior (é o objetivo). O fixture `newer` ganhou `connectionsHealth: 'ok'` (conteúdo diferente) e as três asserções viraram `toEqual`; um caso novo cobre a referência estável.
- Não medido: a CPU do renderer pelo `measure-runtime.mjs` (Electron real). Os números acima são contagem de renders em jsdom com dados fixos; o ganho de CPU real não foi registrado, e o rótulo "há N min" agora avança a cada 60 s (antes, 5 s).
