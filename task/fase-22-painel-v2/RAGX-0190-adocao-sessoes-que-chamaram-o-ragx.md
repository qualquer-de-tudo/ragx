# RAGX-0190 — Adoção: sessões que chamaram o RAGX e as que não

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0156, RAGX-0188 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-05) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S13) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

Hoje a adoção só se mede à mão, lendo transcripts do Claude: 3 de 38 sessões em projetos indexados chamaram o RAGX (8%, auditoria 24, M-05). O painel mostra "Sessões do Claude" e "Chamadas MCP" em 24 h, lado a lado e sem relação entre si, e não diz quantas sessões **usaram** o índice. Esta tarefa torna o S13 visível: das sessões abertas em projeto indexado, quantas chamaram o RAGX e quantas não, numa janela de 14 dias, por projeto e no total. S13 é de **medição**: a spec não fixa meta; ela se fixa depois de 2 semanas de dados.

## Entregáveis

- [ ] `src/app/electron/data/adoption.ts` (novo): função pura `computeAdoption(sessions, now, days)` que devolve `{ since, sessions, withCalls, withoutCalls, unidentified, callsWithoutStart, byProject }`. Definição, escrita no comentário do módulo: **universo** = sessões com um `session_start` em `cli.jsonl`; **usou** = existe chamada em `mcp.jsonl` com o mesmo `session` e o mesmo projeto.
- [ ] `ActivityTail` (`electron/data/activity.ts`) mantém um índice leve por sessão (`Map` chaveado por projeto + `session`, com `startedAt` e número de chamadas), alimentado pelo mesmo `parseLine`, sem reler arquivo, com janela `ADOPTION_DAYS = 14` (mesma de `SAVINGS_DAYS`). O índice é atualizado **antes** do corte de 24 h do `poll` (que descarta eventos antigos) e expõe `sessions()`.
- [ ] Degradação sem exceção: linha sem `session` conta em `unidentified` e fica fora da razão; chamada MCP de sessão sem `session_start` conta em `callsWithoutStart` (hint desligado ou sessão aberta antes da janela); zero sessões mostra "Nenhuma sessão registrada ainda", nunca "0%".
- [ ] `since` = `ts` do evento mais antigo realmente lido. A tela diz "desde 18/09" e não "14 dias" quando o log é mais curto (a primeira leitura pega só `INITIAL_TAIL_BYTES`, 512 KB).
- [ ] Canal IPC `ragx:getAdoption`, sem argumentos (ao lado de `ragx:getActivity`, em `electron/main.ts`), mais `getAdoption` em `electron/preload.ts` e em `RagxBridge` (`src/types/ragx-bridge.d.ts`), com o tipo `AdoptionSummary` em `electron/data/types.ts`.
- [ ] Hook `useAdoption(events)` em `src/hooks/` que busca no mount e de novo quando chega evento novo de tipo `session` ou `mcp`.
- [ ] `ActivityPage`: seção "Adoção pelos agentes" abaixo do bloco `stats-4`, com "3 de 38 sessões chamaram o RAGX (8%)", o período real e a lista por projeto ("projeto: x de y"). `ProjectPage`, em `UsageSection`: uma linha "Sessões que chamaram o RAGX: x de y", só quando houver sessão.

## Fora de escopo

- Fixar meta numérica de adoção (S13 pede 2 semanas de dados antes).
- Mudar o que o Python grava (`record_session_start`, `claude_origin`, `log_mcp_call`); se faltar campo, anote em Notas e abra tarefa.
- Persistir histórico em disco ou banco; a janela é a dos logs lidos.
- Mostrar a consulta do agente (o log não a tem, de propósito) e quebra por perfil do Claude.

## Critérios de aceite

- [ ] Fixture com 3 `session_start` e 1 sessão com chamada MCP resulta em "1 de 3" (teste de `computeAdoption` e de tela).
- [ ] Linha sem `session`, linha corrompida e log ausente não lançam exceção e aparecem nos contadores certos (`unidentified`, ignorada, zero).
- [ ] Medição em log real: rodar o painel (`npm run dev:electron`) num projeto com os dois logs e comparar com a contagem independente `node -e "const fs=require('fs');const r=p=>fs.readFileSync(p,'utf8').split('\n').filter(Boolean).map(l=>JSON.parse(l));const s=new Set(r('.ragx/logs/cli.jsonl').filter(e=>e.command==='session_start'&&e.session).map(e=>e.session));const u=new Set(r('.ragx/logs/mcp.jsonl').filter(e=>e.session&&s.has(e.session)).map(e=>e.session));console.log(u.size,'de',s.size)"`; os dois números batem. Registrar em Andamento.
- [ ] O resumo que sai do processo principal só tem contagens, datas e ids de projeto: nenhum campo de consulta ou argumento (teste que compara as chaves).
- [ ] Nenhum `fs.readFileSync` de log inteiro no novo caminho: a leitura continua por deslocamento (teste de `activity.test.ts` com `size` e `read` simulados).

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Sessões em projeto indexado que chamaram o RAGX (S13) | 3 de 38 (8%), contagem manual em transcripts, 24/09 em diante | o que o painel mostrar, com o período real (`since`) |

Método: o comando `node -e` do segundo critério acima, sobre os logs reais, comparado ao número da tela.

## Testes

- [ ] `src/app/electron/data/__tests__/adoption.test.ts` (novo): universo, "usou", `unidentified`, `callsWithoutStart`, janela de 14 dias, projetos diferentes com o mesmo id de sessão.
- [ ] `src/app/electron/data/__tests__/activity.test.ts` (existente): o índice por sessão sobrevive ao corte de 24 h e à primeira leitura parcial.
- [ ] `src/app/src/pages/__tests__/ActivityPage.test.tsx` e `ProjectPage.test.tsx` (existentes): texto da razão, estado vazio, período real.
- [ ] `src/app/electron/__tests__/preload.test.ts`: acrescentar `getAdoption` à lista exata de métodos; atualizar os quatro mocks completos de `RagxBridge` (`installBridge` em `src/test/snap.ts`, `src/__tests__/App.test.tsx`, `src/hooks/__tests__/useSnapshot.test.ts` e `useJobsConnections.test.ts`), senão o `tsc` quebra.

## Notas

- Confirmado em `electron/data/activity.ts:58-94`: `parseLine` já lê `client`, `profile` e `session`; em `activity.ts:122-124` o `poll` filtra a 24 h e limita a 500 eventos (por isso o índice de sessão é separado).
- Confirmado em `src/ragx/clients/claude_hint.py:193-213`: `session_start` só é gravado quando o Claude Code roda o hook e o projeto tem banco (`cfg.db_path.exists()`), ou seja, "sessão em projeto indexado". Em `src/ragx/clients/registry.py:236-253`, `session` são 8 caracteres de `CLAUDE_CODE_SESSION_ID` e só existe se a variável existir.
- Risco a validar com log real: o hint roda em cada subagente (auditoria 24, M-08). Se o subagente tiver `session` próprio, o universo infla; se compartilhar o da sessão, a chave por `session` já deduplica. A RAGX-0164 reduz a repetição. Registrar o que se observar.
- Reaproveite o agrupamento por sessão da RAGX-0188 (confira o módulo no arquivo dela) em vez de reimplementar.
- A tela de atividade só mostra texto sem travessão (`src/__tests__/no-em-dash.test.ts` falha com "—" em `src/` e `electron/`).

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0190)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
