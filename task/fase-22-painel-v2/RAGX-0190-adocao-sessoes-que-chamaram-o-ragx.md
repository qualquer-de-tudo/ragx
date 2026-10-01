# RAGX-0190 — Adoção: sessões que chamaram o RAGX e as que não

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0156, RAGX-0188 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-05) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S13) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

Hoje a adoção só se mede à mão, lendo transcripts do Claude: 3 de 38 sessões em projetos indexados chamaram o RAGX (8%, auditoria 24, M-05). O painel mostra "Sessões do Claude" e "Chamadas MCP" em 24 h, lado a lado e sem relação entre si, e não diz quantas sessões **usaram** o índice. Esta tarefa torna o S13 visível: das sessões abertas em projeto indexado, quantas chamaram o RAGX e quantas não, numa janela de 14 dias, por projeto e no total. S13 é de **medição**: a spec não fixa meta; ela se fixa depois de 2 semanas de dados.

## Entregáveis

- [x] `src/app/electron/data/adoption.ts` (novo): função pura `computeAdoption(sessions, now, days)` que devolve `{ since, sessions, withCalls, withoutCalls, unidentified, callsWithoutStart, byProject }`. Definição, escrita no comentário do módulo: **universo** = sessões com um `session_start` em `cli.jsonl`; **usou** = existe chamada em `mcp.jsonl` com o mesmo `session` e o mesmo projeto.
- [x] `ActivityTail` (`electron/data/activity.ts`) mantém um índice leve por sessão (`Map` chaveado por projeto + `session`, com `startedAt` e número de chamadas), alimentado pelo mesmo `parseLine`, sem reler arquivo, com janela `ADOPTION_DAYS = 14` (mesma de `SAVINGS_DAYS`). O índice é atualizado **antes** do corte de 24 h do `poll` (que descarta eventos antigos) e expõe `sessions()`.
- [x] Degradação sem exceção: linha sem `session` conta em `unidentified` e fica fora da razão; chamada MCP de sessão sem `session_start` conta em `callsWithoutStart` (hint desligado ou sessão aberta antes da janela); zero sessões mostra "Nenhuma sessão registrada ainda", nunca "0%".
- [x] `since` = `ts` do evento mais antigo realmente lido. A tela diz "desde 18/09" e não "14 dias" quando o log é mais curto (a primeira leitura pega só `INITIAL_TAIL_BYTES`, 512 KB).
- [x] Canal IPC `ragx:getAdoption`, sem argumentos (ao lado de `ragx:getActivity`, em `electron/main.ts`), mais `getAdoption` em `electron/preload.ts` e em `RagxBridge` (`src/types/ragx-bridge.d.ts`), com o tipo `AdoptionSummary` em `electron/data/types.ts`.
- [x] Hook `useAdoption(events)` em `src/hooks/` que busca no mount e de novo quando chega evento novo de tipo `session` ou `mcp`.
- [x] `ActivityPage`: seção "Adoção pelos agentes" abaixo do bloco `stats-4`, com "3 de 38 sessões chamaram o RAGX (8%)", o período real e a lista por projeto ("projeto: x de y"). `ProjectPage`, em `UsageSection`: uma linha "Sessões que chamaram o RAGX: x de y", só quando houver sessão.

## Fora de escopo

- Fixar meta numérica de adoção (S13 pede 2 semanas de dados antes).
- Mudar o que o Python grava (`record_session_start`, `claude_origin`, `log_mcp_call`); se faltar campo, anote em Notas e abra tarefa.
- Persistir histórico em disco ou banco; a janela é a dos logs lidos.
- Mostrar a consulta do agente (o log não a tem, de propósito) e quebra por perfil do Claude.

## Critérios de aceite

- [x] Fixture com 3 `session_start` e 1 sessão com chamada MCP resulta em "1 de 3" (teste de `computeAdoption` e de tela).
- [x] Linha sem `session`, linha corrompida e log ausente não lançam exceção e aparecem nos contadores certos (`unidentified`, ignorada, zero).
- [x] Medição em log real (rodei o `ActivityTail` + `computeAdoption` compilados sobre os logs deste repositório, sem abrir o Electron): comparar com a contagem independente `node -e "const fs=require('fs');const r=p=>fs.readFileSync(p,'utf8').split('\n').filter(Boolean).map(l=>JSON.parse(l));const s=new Set(r('.ragx/logs/cli.jsonl').filter(e=>e.command==='session_start'&&e.session).map(e=>e.session));const u=new Set(r('.ragx/logs/mcp.jsonl').filter(e=>e.session&&s.has(e.session)).map(e=>e.session));console.log(u.size,'de',s.size)"`; os dois números batem. Registrar em Andamento.
- [x] O resumo que sai do processo principal só tem contagens, datas e ids de projeto: nenhum campo de consulta ou argumento (teste que compara as chaves).
- [x] Nenhum `fs.readFileSync` de log inteiro no novo caminho: a leitura continua por deslocamento (teste de `activity.test.ts` com `size` e `read` simulados).

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Sessões em projeto indexado que chamaram o RAGX (S13) | 3 de 38 (8%), contagem manual em transcripts, 24/09 em diante | neste repositório: **2 de 2** pelo `computeAdoption`, desde 29/09 (`since`); a contagem independente do `node -e` deu os mesmos **2 de 2** |

Método: o comando `node -e` do segundo critério acima, sobre os logs reais, comparado ao número da tela.

## Testes

- [x] `src/app/electron/data/__tests__/adoption.test.ts` (novo): universo, "usou", `unidentified`, `callsWithoutStart`, janela de 14 dias, projetos diferentes com o mesmo id de sessão.
- [x] `src/app/electron/data/__tests__/activity.test.ts` (existente): o índice por sessão sobrevive ao corte de 24 h e à primeira leitura parcial.
- [x] `src/app/src/pages/__tests__/ActivityPage.test.tsx` e `ProjectPage.test.tsx` (existentes): texto da razão, estado vazio, período real.
- [x] `src/app/electron/__tests__/preload.test.ts`: acrescentar `getAdoption` à lista exata de métodos; atualizar os quatro mocks completos de `RagxBridge` (`installBridge` em `src/test/snap.ts`, `src/__tests__/App.test.tsx`, `src/hooks/__tests__/useSnapshot.test.ts` e `useJobsConnections.test.ts`), senão o `tsc` quebra.

## Notas

- Confirmado em `electron/data/activity.ts:58-94`: `parseLine` já lê `client`, `profile` e `session`; em `activity.ts:122-124` o `poll` filtra a 24 h e limita a 500 eventos (por isso o índice de sessão é separado).
- Confirmado em `src/ragx/clients/claude_hint.py:193-213`: `session_start` só é gravado quando o Claude Code roda o hook e o projeto tem banco (`cfg.db_path.exists()`), ou seja, "sessão em projeto indexado". Em `src/ragx/clients/registry.py:236-253`, `session` são 8 caracteres de `CLAUDE_CODE_SESSION_ID` e só existe se a variável existir.
- Risco a validar com log real: o hint roda em cada subagente (auditoria 24, M-08). Se o subagente tiver `session` próprio, o universo infla; se compartilhar o da sessão, a chave por `session` já deduplica. A RAGX-0164 reduz a repetição. Registrar o que se observar.
- Reaproveite o agrupamento por sessão da RAGX-0188 (confira o módulo no arquivo dela) em vez de reimplementar.
- A tela de atividade só mostra texto sem travessão (`src/__tests__/no-em-dash.test.ts` falha com "—" em `src/` e `electron/`).

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0190)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_

- 2026-10-01 — Implementado: `electron/data/adoption.ts` (`computeAdoption`, `ADOPTION_DAYS = 14`, `AdoptionSession`; a definição está no comentário do módulo), `AdoptionSummary` em `types.ts`, índice por sessão no `ActivityTail` (`sessions()`, alimentado antes do corte de 24 h, poda por 14 dias), canal `ragx:getAdoption`, `preload`, `RagxBridge`, os 4 mocks, `useAdoption` (busca no mount e quando chega evento `session` ou `mcp`), `AdoptionSection` na Atividade e a linha na `UsageSection` do detalhe (a página do projeto só busca no mount).
- **Medido** (logs reais deste repositório, `.ragx/logs`): `computeAdoption` = 2 sessões, 2 com chamadas, 0 sem, `unidentified` 19, `callsWithoutStart` 1, desde 2026-09-29; o comando `node -e` independente do critério = **2 de 2**. Batem. Observação: o universo é pequeno aqui porque os logs deste repo são curtos (a primeira leitura pega só os últimos 512 KB e o hint só grava `session_start` com o hook ativo); a razão de 8% da auditoria vinha de transcripts e não se reproduz com estes logs. O risco dos subagentes (cada um rodando o hint) não deu para checar: o log só tem uma sessão com muitos `session_start`, e como a chave é por `session`, ela é uma sessão só.
- Testes novos: `adoption.test.ts` (11: os critérios de aceite de `computeAdoption`, o índice que sobrevive ao corte de 24 h, linha corrompida/sem sessão/log ausente, leitura por deslocamento, primeira leitura parcial) e `adoption-ui.test.tsx` (5: razão, período real, lista por projeto, vazio sem "0%", falha silenciosa, linha do projeto); `preload.test.ts` com `getAdoption`. Painel: 1403 testes verdes, `lint` e `tsc` limpos.
- Bundle: JS 333.568 → **335.247 B** (gzip 100.301 → 100.794); CSS 43.157 B, sem mudança.
- Não feito: abrir o painel no Electron real com `npm run dev:electron`; o critério usa o caminho compilado do mesmo código.
