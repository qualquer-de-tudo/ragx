# RAGX-0184 — Detalhe do projeto: em dia, economia, agente usando

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0179 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-13) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P10) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

O dono abre o detalhe de um projeto para saber três coisas: o índice está em dia?, o RAGX está economizando?, o agente está usando? Hoje a primeira resposta é a **segunda** coisa da página (`ProjectPage.tsx:424-427`: "Índice" à esquerda, na coluna larga; "Está em dia?" na estreita, `App.css:1974-1977`), a economia está noutra aba (`PROJECT_TABS`, `ProjectPage.tsx:463-468`) e o uso pelo agente vem abaixo. A auditoria mediu por captura a 900 px que "está em dia?" é a segunda pergunta da página. Esta tarefa põe as três respostas no topo, sem tocar no que o detalhe já faz.

## Entregáveis

- [ ] `src/components/project/ProjectGlance.tsx`: faixa de três blocos entre o cabeçalho (`detail-head`) e as abas, visível em todas as abas, a partir de `ProjectSnapshot` e do estado de `useProjectStatus` (já existe, `ProjectPage.tsx:43-81`):
  - **Está em dia?**: `STATE_LABEL`/`STATE_TONE` (`state.ts`), uma linha com o primeiro motivo (`reasonText`, `projectStatus.ts`) e o botão do estado (`STATE_ACTION`; reaproveita `ProjectActionButton`, `ProjectBits.tsx:11`). Enquanto `status` carrega: "Verificando…".
  - **Economia (14 dias)**: `savingsRatio` e `tokensSaved` (`projectMetrics.ts`) e o botão "Ver gráfico" que abre a aba Economia (`chooseTab`). Sem medição: "sem medição ainda", nunca "0%".
  - **Agente usando?**: `live` ("Em uso agora"), senão `telemetry.lastCallAt` ("Última chamada há 3 h") com as chamadas de 24 h (`totalCalls`); sem nada: "Nenhuma chamada registrada. Confira em Conexões se o RAGX está ligado no Claude Code."
- [ ] Ordem da aba Visão geral (`ProjectPage.tsx:424-427`): `FreshnessSection` antes de `IndexSection`, e as colunas de `.detail-grid-top` (`App.css:1974-1977`) invertidas para `minmax(280px,1fr) minmax(0,2fr)`.
- [ ] Cada bloco é uma entrada de um array (`id`, `title`, `body`), para a RAGX-0186 (moeda no bloco de economia) e a RAGX-0189 (saúde do índice) acrescentarem sem reescrever o componente.
- [ ] O selo do cabeçalho (`Badge`) e o `LivePill` permanecem; a faixa não os substitui.
- [ ] `src/app/README.md`: atualizar a descrição do "Detalhe do projeto" (a faixa e a nova ordem).

## Fora de escopo

- Gráfico e acessibilidade dele (RAGX-0185); valor em moeda (RAGX-0186); tendência e checagens de saúde (RAGX-0189); preview do contexto (RAGX-0187).
- Novo campo de telemetria ou novo IPC: tudo vem do snapshot e do `ragx status --json` que a tela já pede.
- Reordenar ou renomear as abas.

## Critérios de aceite

- [ ] A 900 px de largura e 600 de altura, as três respostas estão visíveis sem rolar (captura via harness da RAGX-0181 ou Playwright com bridge simulado; registrar a captura em Andamento).
- [ ] No DOM, a faixa vem antes das abas e "Está em dia?" é o primeiro bloco da aba Visão geral (teste de ordem por `compareDocumentPosition`).
- [ ] Os quatro casos de cada bloco têm teste: em dia / defasado / verificando / erro; com economia / sem medição; em uso agora / última chamada / nenhuma chamada.
- [ ] Estado nunca só por cor: cada bloco diz o estado em texto (conferido no teste por `getByText`).
- [ ] 480, 900 e 1280 px sem estouro horizontal e sem texto cortado (harness da RAGX-0181 ou captura manual).
- [ ] `ProjectPage.test.tsx` (769 linhas) segue verde; só mudam asserts que dependiam da ordem antiga.
- [ ] Bundle (hoje JS 306.822 B, gzip -9 91.745 B): registrar antes e depois.

## Testes

- [ ] `src/pages/__tests__/ProjectPage.test.tsx` (existente): novo `describe('ProjectPage: de relance')` com os casos acima.
- [ ] `src/components/project/__tests__/ProjectGlance.test.tsx` (novo): cada bloco isolado, com `snap()` de `src/test/snap.ts`.
- [ ] `src/__tests__/state.test.ts` (existente): sem mudança de lógica, só rodar.

## Notas

- Premissa da auditoria confirmada por leitura: U-13 ("o índice está em dia?" é a segunda pergunta). `FreshnessSection` (`ProjectPage.tsx:150-195`) já tem tudo que o bloco precisa; não duplique a regra, importe-a.
- A faixa chama o mesmo `useProjectStatus`, que dispara `getProjectStatus` (um `ragx status --json`); suba o hook para `ProjectPage` e passe o resultado para a faixa e para a seção, em vez de abrir um segundo processo.
- "Agente usando?" vem de `telemetry.lastCallAt` e `liveProjectIds` (`activity.ts`, "em uso agora" = evento no último minuto). Não sabe se o Claude Code está ligado **neste projeto**; por isso o texto manda conferir em Conexões.
- `src/__tests__/no-em-dash.test.ts` falha com "—" em texto novo de `src/`.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0184)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
