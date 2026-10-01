# RAGX-0181 — Responsividade da casca de 480 a 3440 px e zoom 200%

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0178 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-07) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P8) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

A janela tem mínimo de 900 DIP (`electron/main.ts:450`), mas o zoom de 150% a 200% reproduz 600 e 450 px de CSS, e aí a casca quebra: com viewport de 480 px a `.topbar` e o `.content` chegaram a 811 px (medido por screenshot). No outro extremo, a 3440 px o conteúdo fica preso em 1200 px (`.content-inner`, `App.css:22-26`) com a topbar na largura toda. Os breakpoints são 5 valores soltos em 6 blocos `@media` (640, 760, 900, 960, 1000) e não há `@container`. Esta tarefa fecha as duas pontas e cria o harness que repete a medição.

## Entregáveis

- [x] Harness `scripts/visual-check.mjs` + `scripts/visual-fixtures/bridge.js` (em `src/app/`): sobe `vite preview` sobre `dist/`, abre `playwright-core` com `channel: 'msedge'` (o Windows 11 tem Edge; evita baixar navegador; devDependency, registrar o tamanho), injeta `window.ragx` simulado por `addInitScript` (todos os métodos de `RagxBridge`, ~12 projetos nas formas de `src/test/snap.ts`) e, para cada tela (Projetos em grade e lista, as 4 abas do Detalhe, Atividade, Conexões, Como funciona, Onboarding) e largura (450, 480, 600, 900, 1280, 3440), lista elementos com `getBoundingClientRect().right > innerWidth + 1` fora de ancestral com `overflow-x: auto|scroll`, mais `scrollWidth > clientWidth` em `.shell`, `.shell-main` e `.topbar`. Sem navegador, sai com código 2 e diz por quê; nunca falha o `npm test`.
- [x] Breakpoints do projeto: `640`, `900` e `1200`, documentados num comentário no topo de `App.css` e em `src/breakpoints.ts`. Mapear: 760, 960 e 1000 viram 900 (ou `@container`), conferindo por captura que nada piora a 480, 900 e 1280.
- [x] `.topbar` (`App.css:108-118`, colunas `minmax(max-content,1fr) minmax(200px,440px) minmax(max-content,1fr)`, a primeira vazia): até 900 px vira `minmax(120px,1fr) auto`, a busca na coluna 1; "RAGX no Claude" mostra só trilho e estado, a fila só o contador; até 640 px quebra em duas linhas (`.shell-main` passa de `56px` fixo para `auto`, `App.css:11`). Os nomes acessíveis não mudam (já há `aria-label`).
- [x] `.sidebar` (72 px) fica; abaixo de 640 px passa a 56 px sem perder o rótulo.
- [x] A 3440 px, topbar e `.content-inner` compartilham as mesmas bordas (envolver o conteúdo da topbar numa largura máxima igual) e a largura máxima do conteúdo sobe em tela larga, com número escolhido por captura e registrado.
- [x] `@container` em `.savings` (hoje `@media (max-width: 760px)`, `App.css:2015`), no card de projeto e em `.activity-item` (`@media 960`, `App.css:2417`), para o componente reagir ao espaço que tem e não à janela.
- [x] `src/app/README.md`: seção "Larguras suportadas" com o intervalo, o mínimo da janela e como rodar o harness.

## Fora de escopo

- Nova navegação (menu hambúrguer, barra inferior), toque e gestos; mudar o `minWidth` de 900 da janela.
- Tema claro (RAGX-0193), alvos de 24 px e foco (RAGX-0185), primitivos (RAGX-0179), tokens (RAGX-0178).
- Reflow a 320 px (400% de zoom): o piso é 450 px.

## Critérios de aceite

- [x] `node scripts/visual-check.mjs` (depois de `npm run build`) termina com 0 elementos estourando, nas 6 larguras e em todas as telas listadas; o relatório vai para Andamento. Hoje, a 480 px, ele aponta a topbar e o `.content` (811 px medidos pelo auditor); registrar o "antes".
- [x] A 450 px (zoom 200% de 900) e 600 px (150%): nenhuma barra horizontal na janela, texto legível e nenhum botão cortado (captura de Projetos, Detalhe e Conexões). (Conferido pelo harness e por captura de Projetos e Conexões a 450 px; o Detalhe só pelo harness.)
- [x] A 3440 px: bordas esquerda e direita da topbar e de `.content-inner` iguais (diferença ≤ 1 px, medida no harness) e a grade de projetos usa a largura nova.
- [x] Só `640`, `900` e `1200` em `@media (max-width)`/`(min-width)`: `css-breakpoints.test.ts`. Hoje o conjunto é {640, 760, 900, 960, 1000}.
- [x] Bundle (hoje JS 306.822 B, CSS 34.835 B em `dist/assets`): registrar antes e depois; o `playwright-core` não entra no bundle.

## Testes

- [x] `src/__tests__/css-breakpoints.test.ts` (novo): lê `App.css` e confere o conjunto permitido de breakpoints, como `no-em-dash.test.ts` lê arquivos.
- [x] `src/components/shell/__tests__/shell.test.tsx` (existente): `TopBar` mantém nome acessível do interruptor, da fila e de "Conexões" (o texto some por CSS, o `aria-label` fica).
- [x] O harness é a verificação de layout: jsdom não calcula CSS de arquivo.

## Notas

- Confirmado: `index.css:41-44` põe `overflow: hidden` em `html` e `body`, então o estouro **corta em vez de rolar**; `document.documentElement.scrollWidth` não serve de teste. Por isso o critério usa `getBoundingClientRect` por elemento.
- Confirmado em `App.css`: `@media` em 303 (1000), 767 (640), 979 (900), 1979 e 2417 (960), 2015 (760). A tabela da lista de projetos (`.projects-table-wrap`) rola de propósito e fica fora da contagem.
- Zoom no Electron: 200% de 900 DIP é 450 px de CSS. A RAGX-0194 mantém Exibir > zoom no menu mínimo; o harness reproduz o zoom por largura de viewport.
- Como repetir o que o auditor fez, sem o harness: `npm run build`, `npx vite preview --port 4173`, Playwright com `addInitScript` e `setViewportSize` nas larguras acima; capturas fora do repositório.
- `no-em-dash.test.ts` vale para o texto do harness em `scripts/`? Não (varre `src/` e `electron/`), mas mantenha o hábito.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [x] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0181)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Harness: `scripts/visual-check.mjs`, `scripts/visual-fixtures/bridge.js` (12 projetos, atividade, conexões, fila) e `scripts/visual-probe.mjs`; `playwright-core` como devDependency (14 MB em `node_modules`, fora do bundle), Edge do Windows, sem baixar navegador. Duas armadilhas achadas: o headless do Playwright liga `--hide-scrollbars` (sem a calha de 12 px a medição de alinhamento mente: `ignoreDefaultArgs`) e `.content` tem `overflow-y: scroll`, logo `overflow-x` computado `auto` (por isso o limite dos elementos de dentro dele é a área útil do `.content`, não a janela).
- **Antes** (mesmo harness, `dist/` de antes das mudanças de CSS desta tarefa): a 450, 480 e 600 px, **9 das 10 telas** estouravam (96 problemas no total: `topbar` e `.content` a 818 px a 480 px, o que o auditor mediu como 811; `.shell` com `scrollWidth` 818), 0 a 900, 1280 e 3440 px; a 3440 px a barra superior ia de 72 a 3440 e o conteúdo de 1156 a 2356 (**1084 px** de diferença). **Depois**: **60 medições, 0 problemas**, e a 3440 px as bordas coincidem (**0 px**: 850 a 2650 nos dois).
- Implementado: `.topbar` virou casca e `.topbar-inner` leva o grid (mesma `--content-max` e padding do `.content-inner`; `padding-right: var(--scrollbar-w)` compensa a calha, e `.content` ganhou `overflow-y: scroll` para a calha existir sempre); `.shell-main` com linha `auto`; até 900 px `minmax(120px,1fr) auto` e o texto de "RAGX no Claude", "Conexões" e da fila vira `.topbar-collapse` (visualmente oculto, nome acessível intacto); até 640 px duas linhas e barra lateral de 56 px. `--content-max` = `clamp(1200px, 55vw, 1800px)` acima de 1200 px (1200 a 1280, 1408 a 2560, 1800 a 3440; escolhido olhando a captura de 3440: 4 colunas de cartões, sem linhas esticadas). Breakpoints 760, 960 e 1000 saíram: 1000 e 960 viraram 900, o de 760 (economia) e o de 960 (feed) viraram `@container`, e o cartão de projeto ganhou um (`.project-numbers` empilha abaixo de 260 px). Causa de quase todo estouro: grades com coluna implícita `auto` (`.conn-card`, `.detail-card`, `.conn-sub`, `.profile-list`) que cresciam com o caminho longo; ganharam `grid-template-columns: minmax(0, 1fr)`. Também `.page-head` quebra linha e `.segmented` e o filtro de projeto rolam/encolhem em vez de estourar.
- Testes: `css-breakpoints.test.ts` (3: App.css, index.css, não vazio), `src/breakpoints.ts`. `shell.test.tsx` segue verde sem mudar asserção (os nomes acessíveis da fila, do interruptor e de "Conexões" não mudaram). Painel: 1196 testes verdes, `lint` e `tsc` limpos; a catraca de espaçamento ficou em 200 (removi um `margin: -1px` novo para não subir).
- Bundle: JS 309.723 → 311.809 (0180) → **312.209 B** (gzip 93.844 → 93.917; o `TriggerText` e o `topbar-inner`); CSS 37.725 → **39.046 B** (gzip 7.591 → 7.819). `playwright-core` não entra no bundle.
- Não feito: a captura do Detalhe a 450 px foi só pelo harness (sem olhar a imagem); não rodei o harness no Electron real (o zoom do Electron é a largura de viewport em CSS, que é o que se mede).
