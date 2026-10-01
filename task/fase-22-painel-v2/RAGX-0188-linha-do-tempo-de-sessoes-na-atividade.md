# RAGX-0188 — Linha do tempo de sessões na Atividade

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0156, RAGX-0179 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (lacunas de produto, M-05, M-12) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

A tela Atividade mostra um feed plano de eventos, do mais novo ao mais antigo (`ActivityPage.tsx:127-186`, "Linha do tempo de uso"). Não dá para responder "o que aquela sessão do Claude fez?": as chamadas de uma mesma conversa ficam misturadas com as de outras. O evento já traz `session` (8 caracteres do `CLAUDE_CODE_SESSION_ID`, `registry.py:249-252`), `client` e `profile` (`ActivityEvent`, `electron/data/types.ts:52-70`). Esta tarefa agrupa por sessão e mostra cada uma como uma linha do tempo, sem mostrar a consulta (o log não a tem, de propósito).

## Entregáveis

- [ ] `src/sessions.ts` (puro, sem React): `groupSessions(events, now): SessionGroup[]`, com `SessionGroup = { key, projectId, projectName, session: string | null, client, profile, startedAt, lastAt, starts, mcpCalls, cliCalls, byTool: {name, count}[], delivered, baseline, failures, usedRagx, events }`. Chave = `projectId` + `session`; eventos sem `session` formam um grupo por projeto, "Sem sessão identificada". `starts` conta os `session_start`; `usedRagx` = há chamada MCP ou comando `ragx` (que não seja `session_start`) na sessão; `failures` conta `ok === false`; ordenação por `lastAt` decrescente. É a definição que a RAGX-0190 reaproveita.
- [ ] Extrair a linha do feed (`ActivityPage.tsx:164-186`) para `src/components/activity/ActivityRow.tsx`, usada pelo feed e pela sessão expandida.
- [ ] `ActivityPage`: `Segmented` (RAGX-0179) "Eventos | Sessões" acima do feed; o padrão continua "Eventos" (comportamento atual preservado), a escolha fica lembrada enquanto o painel estiver aberto (como `listPrefs` em `projectMetrics.ts`). Os filtros de tipo e de projeto valem nas duas visões.
- [ ] Visão "Sessões": um item por sessão com cabeçalho em texto ("Claude Code · empresa · sessão 84c71544 · 22:31 a 22:35 (4 min)"), resumo ("8 chamadas MCP, 11 comandos ragx, 3,2 mil tokens entregues, usou o RAGX"), e botão com `aria-expanded` que abre os eventos em ordem cronológica. Faixa de tempo (`aria-hidden`) com um traço por evento, proporcional ao tempo; falha marcada por forma e por texto no resumo, nunca só por cor.
- [ ] Campos novos do log da RAGX-0156 no `parseLine` (`electron/data/activity.ts:58-94`): `err_code` e `resp_chars` entram em `ActivityEvent` como `errCode` e `respChars` (`null` quando ausentes) e aparecem na linha expandida só quando existirem.
- [ ] `src/app/README.md`: descrever as duas visões e o limite de 24 h e 500 eventos.

## Fora de escopo

- A razão "sessões que chamaram o RAGX / sessões abertas" em janela de 14 dias (RAGX-0190); aqui só o agrupamento das 24 h que o renderer já tem.
- Mostrar a consulta ou o conteúdo devolvido; mudar o que o Python grava (`log_mcp_call`, `log_cli_call`).
- Persistir sessões em disco; abrir transcript do Claude.

## Critérios de aceite

- [ ] Fixture com 3 sessões, `session_start` repetido (subagentes), eventos sem `session` e o mesmo id em dois projetos: agrupa em 3 + 1 grupo sem sessão por projeto, sem fundir projetos (teste de `groupSessions`).
- [ ] `starts` mostra os inícios repetidos como "N inícios de contexto (subagentes)" e **não** como N sessões. Medido neste repo (`.ragx/logs/cli.jsonl`): 59 linhas, 35 `session_start`, 55 das 59 linhas de uma única sessão (`84c71544`); uma sessão, muitos inícios.
- [ ] Degradação: log MCP sem `ok`, `err_code` e `resp_chars` (hoje é assim: nas 30 linhas de `.ragx/logs/mcp.jsonl` só `ts`, `tool`, `ms`, `project`, mais `client/profile/session` em 11 e os tokens em 8) mostra "falhas: sem dado" em vez de "0 falhas"; com os campos da RAGX-0156, mostra a contagem e o código do erro.
- [ ] Linha MCP sem `session` (11 de 30 aqui têm; as outras vêm de testes e de fora do Claude Code) cai em "Sem sessão identificada", sem inflar o número de sessões.
- [ ] Com 500 eventos (`ACTIVITY_MAX`) a tela avisa "Mostrando os 500 eventos mais recentes; sessões antigas podem estar incompletas"; o tempo de `groupSessions` com 500 eventos fica registrado em Andamento.
- [ ] Teclado: o botão de cada sessão abre e fecha com Enter e Espaço e o foco não se perde ao expandir.
- [ ] 480, 900 e 1280 px sem estouro horizontal (harness da RAGX-0181 ou captura manual).
- [ ] Bundle (hoje JS 306.822 B, gzip -9 91.745 B): registrar antes e depois.

## Testes

- [ ] `src/__tests__/sessions.test.ts` (novo): agrupamento, `usedRagx`, `starts`, `failures` com e sem `ok`, ordem, grupo sem sessão, mesmo id em projetos diferentes.
- [ ] `src/pages/__tests__/ActivityPage.test.tsx` (existente, 123 linhas): alternar a visão, expandir, filtros nas duas visões, aviso de 500 eventos; os testes do feed seguem iguais.
- [ ] `src/app/electron/data/__tests__/activity.test.ts` (existente): `errCode` e `respChars` lidos quando presentes e `null` quando não.

## Notas

- Confirmado em `src/activity.ts` (`mergeEvents`, `WINDOW_MS`, `MAX`): ordena do mais novo ao mais antigo e corta em 24 h e 500; `electron/data/activity.ts` tem a mesma janela e teto (`ACTIVITY_WINDOW_MS`, `ACTIVITY_MAX`). Sessão longa pode ser cortada: o aviso acima é obrigatório.
- O módulo é do renderer: o processo principal não importa `src/` (`tsconfig.electron.json` tem `rootDir: electron`). A RAGX-0190 calcula no processo principal com janela de 14 dias; as duas implementações têm de concordar em `usedRagx` e `starts`: reutilize as fixtures desta tarefa nos testes dela.
- `session` tem 8 caracteres: colisão é possível em teoria e a chave inclui o projeto para limitar o dano.
- `src/__tests__/no-em-dash.test.ts` vale para todo texto novo.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0188)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
