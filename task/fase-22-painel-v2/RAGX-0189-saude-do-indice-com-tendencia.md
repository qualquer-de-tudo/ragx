# RAGX-0189 — Saúde do índice com tendência

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0184 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (lacunas de produto) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

O painel diz **agora** se o índice está em dia (`FreshnessSection`) e lista as indexações na aba Histórico (`Timeline`), mas não responde "o índice anda saudável, ou está piorando?": uma indexação que passou a levar 15 s em vez de 2 s, ou que falha duas vezes seguidas, só aparece a quem abre o Histórico e compara de cabeça. A tabela `index_runs` já guarda `duration_ms`, `files_seen`, `indexed`, `blocked`, `embedded` e `error` por indexação (`RunRepo.finish`, `repositories.py:211-222`), e o painel só lê `indexed`, `error` e as datas (`projectStatus.ts:104-117`). Esta tarefa lê o resto, resume a saúde em poucas checagens e mostra a tendência das últimas indexações.

## Entregáveis

- [ ] `projectStatus.ts`: `IndexRun` ganha `durationMs`, `filesSeen`, `blocked`, `embedded` (`duration_ms`, `files_seen`, `blocked`, `embedded` de `ragx status --json` e `ragx runs --json`), `null` quando ausentes ou inválidos, com o mesmo `count()` defensivo de hoje.
- [ ] `src/indexHealth.ts` (puro, sem React nem DOM, para poder ser portado ao processo principal pela RAGX-0191): `computeIndexHealth({ project, state, status, now })` devolve `{ level: 'ok' | 'warn' | 'bad', checks, trend }`. Checagens, cada uma com `id`, nível, texto e, quando couber, a ação (`kind` de `STATE_ACTION`): embeddings pendentes (`counts.pendingEmbeddings > 0`, aviso, ação `embed`); última indexação com erro (`runs[0].error`, ruim); duas ou mais falhas seguidas (ruim, "está falhando"); hooks de git ausentes (`hooksInstalled === false`, aviso, ação `hooks-install`, "o índice só atualiza quando você pede"). A defasagem em si continua em `FreshnessSection` e não repete aqui.
- [ ] Tendência: mediana de `durationMs` das indexações **sem mudança** (`indexed === 0`, sem erro) e das **com mudança**, número de falhas nas últimas N e a direção ("mais lenta", "estável", "mais rápida") comparando as 3 mais novas com as anteriores. Constantes nomeadas e comentadas, decisão desta tarefa e não medida: `MIN_RUNS_FOR_TREND = 6` e `TREND_RATIO = 1.5`. Com menos de 6, texto "poucos dados para tendência (N de 6 indexações)".
- [ ] `src/components/project/IndexHealth.tsx`: seção "Saúde do índice" na aba Visão geral, logo depois da faixa da RAGX-0184 e do grid "Está em dia?" / "Índice"; selo de nível em texto (`Badge`), checagens em lista, mini-gráfico de barras com a duração das últimas indexações e `<details>` "Ver em tabela" (mesma alternativa do gráfico de economia), com `aria-label` por barra. Falha de uma checagem de dado ausente diz "sem dado", nunca "ok".
- [ ] `src/app/README.md`: descrever a seção, de onde vêm os dados e o limite (as indexações que `ragx status` devolve, 10 mais recentes).

## Fora de escopo

- Tendência de **cobertura de embeddings** e de **defasagem** ao longo do tempo: não há série gravada em lugar nenhum (só o instante atual e `index_runs`); precisaria de amostragem nova.
- Alerta na bandeja e notificação (RAGX-0191, que consome `level`); nova rota ou nova aba; mudar o que a CLI grava em `index_runs`.
- Páginas além das 10 do `ragx status` (o "Carregar mais" do Histórico continua lá).

## Critérios de aceite

- [ ] Fixtures de `computeIndexHealth`: tudo certo vira `ok`; embeddings pendentes vira `warn` com ação `embed`; erro na última vira `bad`; dois erros seguidos vira "está falhando"; hooks ausentes vira `warn`; cada caso por teste.
- [ ] Tendência com 10 indexações em que as 3 mais novas levam mais de 1,5 vezes a mediana das 7 anteriores: "mais lenta"; menos de 1/1,5 da mediana: "mais rápida"; entre os dois limites: "estável"; 5 indexações: "poucos dados" (testes).
- [ ] `durationMs` ausente em todas: sem gráfico, com "sem dado de duração" (degrada, não quebra; log antigo sem a coluna ou resposta de CLI antiga).
- [ ] Estado nunca só por cor e o gráfico tem alternativa em tabela e `aria-label` por barra.
- [ ] Contra um projeto real (`npm run dev:electron`), os números da seção batem com `ragx runs --json --limit 10` dentro do projeto; registrar a comparação em Andamento.
- [ ] 480, 900 e 1280 px sem estouro horizontal (harness da RAGX-0181 ou captura manual).
- [ ] Bundle (hoje JS 306.822 B, gzip -9 91.745 B): registrar antes e depois.

## Testes

- [ ] `src/__tests__/indexHealth.test.ts` (novo): checagens, mediana, direção, limites de `MIN_RUNS_FOR_TREND` e `TREND_RATIO`, dado ausente.
- [ ] `src/__tests__/projectStatus.test.ts` (novo; hoje `parseRun` só é coberto por `ProjectPage.test.tsx`): campos novos de `parseRun`, valor inválido vira `null`.
- [ ] `src/pages/__tests__/ProjectPage.test.tsx` (existente): a seção aparece depois da faixa, com os três níveis; a aba Histórico segue igual.
- [ ] `src/components/project/__tests__/IndexHealth.test.tsx` (novo): tabela alternativa, `aria-label` das barras, estado "poucos dados".

## Notas

- Confirmado: `ragx status --json` devolve `recent_runs` com as 10 mais recentes (`pipeline.py:424`, `RunRepo.recent`) e `last_run`; `parseRun` ignora `duration_ms` hoje. Se a coluna vier ausente de uma CLI mais antiga, calcule a duração por `finishedAt - startedAt` e anote.
- Premissa que não vale: "tendência" de saúde como série temporal de cobertura. O que existe é histórico de **indexações**; a tarefa entrega a tendência dele e diz isso na tela.
- O resultado de `indexed === 0` é exatamente o custo do "índice sem mudança" que a fase 19 quer derrubar (S4 da spec 25, 7,6 a 15 s hoje): a mediana desse grupo é o termômetro. Não escreva a meta v2 na tela; ela envelhece.
- `src/__tests__/no-em-dash.test.ts` vale para todo texto novo.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0189)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
