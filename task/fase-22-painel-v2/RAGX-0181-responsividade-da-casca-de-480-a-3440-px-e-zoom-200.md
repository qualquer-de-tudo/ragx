# RAGX-0181 — Responsividade da casca de 480 a 3440 px e zoom 200%

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0178 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-07) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P8) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

A janela tem mínimo de 900 DIP (`electron/main.ts:450`), mas o zoom de 150% a 200% reproduz 600 e 450 px de CSS, e aí a casca quebra: com viewport de 480 px a `.topbar` e o `.content` chegaram a 811 px (medido por screenshot). No outro extremo, a 3440 px o conteúdo fica preso em 1200 px (`.content-inner`, `App.css:22-26`) com a topbar na largura toda. Os breakpoints são 5 valores soltos em 6 blocos `@media` (640, 760, 900, 960, 1000) e não há `@container`. Esta tarefa fecha as duas pontas e cria o harness que repete a medição.

## Entregáveis

- [ ] Harness `scripts/visual-check.mjs` + `scripts/visual-fixtures/bridge.js` (em `src/app/`): sobe `vite preview` sobre `dist/`, abre `playwright-core` com `channel: 'msedge'` (o Windows 11 tem Edge; evita baixar navegador; devDependency, registrar o tamanho), injeta `window.ragx` simulado por `addInitScript` (todos os métodos de `RagxBridge`, ~12 projetos nas formas de `src/test/snap.ts`) e, para cada tela (Projetos em grade e lista, as 4 abas do Detalhe, Atividade, Conexões, Como funciona, Onboarding) e largura (450, 480, 600, 900, 1280, 3440), lista elementos com `getBoundingClientRect().right > innerWidth + 1` fora de ancestral com `overflow-x: auto|scroll`, mais `scrollWidth > clientWidth` em `.shell`, `.shell-main` e `.topbar`. Sem navegador, sai com código 2 e diz por quê; nunca falha o `npm test`.
- [ ] Breakpoints do projeto: `640`, `900` e `1200`, documentados num comentário no topo de `App.css` e em `src/breakpoints.ts`. Mapear: 760, 960 e 1000 viram 900 (ou `@container`), conferindo por captura que nada piora a 480, 900 e 1280.
- [ ] `.topbar` (`App.css:108-118`, colunas `minmax(max-content,1fr) minmax(200px,440px) minmax(max-content,1fr)`, a primeira vazia): até 900 px vira `minmax(120px,1fr) auto`, a busca na coluna 1; "RAGX no Claude" mostra só trilho e estado, a fila só o contador; até 640 px quebra em duas linhas (`.shell-main` passa de `56px` fixo para `auto`, `App.css:11`). Os nomes acessíveis não mudam (já há `aria-label`).
- [ ] `.sidebar` (72 px) fica; abaixo de 640 px passa a 56 px sem perder o rótulo.
- [ ] A 3440 px, topbar e `.content-inner` compartilham as mesmas bordas (envolver o conteúdo da topbar numa largura máxima igual) e a largura máxima do conteúdo sobe em tela larga, com número escolhido por captura e registrado.
- [ ] `@container` em `.savings` (hoje `@media (max-width: 760px)`, `App.css:2015`), no card de projeto e em `.activity-item` (`@media 960`, `App.css:2417`), para o componente reagir ao espaço que tem e não à janela.
- [ ] `src/app/README.md`: seção "Larguras suportadas" com o intervalo, o mínimo da janela e como rodar o harness.

## Fora de escopo

- Nova navegação (menu hambúrguer, barra inferior), toque e gestos; mudar o `minWidth` de 900 da janela.
- Tema claro (RAGX-0193), alvos de 24 px e foco (RAGX-0185), primitivos (RAGX-0179), tokens (RAGX-0178).
- Reflow a 320 px (400% de zoom): o piso é 450 px.

## Critérios de aceite

- [ ] `node scripts/visual-check.mjs` (depois de `npm run build`) termina com 0 elementos estourando, nas 6 larguras e em todas as telas listadas; o relatório vai para Andamento. Hoje, a 480 px, ele aponta a topbar e o `.content` (811 px medidos pelo auditor); registrar o "antes".
- [ ] A 450 px (zoom 200% de 900) e 600 px (150%): nenhuma barra horizontal na janela, texto legível e nenhum botão cortado (captura de Projetos, Detalhe e Conexões).
- [ ] A 3440 px: bordas esquerda e direita da topbar e de `.content-inner` iguais (diferença ≤ 1 px, medida no harness) e a grade de projetos usa a largura nova.
- [ ] Só `640`, `900` e `1200` em `@media (max-width)`/`(min-width)`: `css-breakpoints.test.ts`. Hoje o conjunto é {640, 760, 900, 960, 1000}.
- [ ] Bundle (hoje JS 306.822 B, CSS 34.835 B em `dist/assets`): registrar antes e depois; o `playwright-core` não entra no bundle.

## Testes

- [ ] `src/__tests__/css-breakpoints.test.ts` (novo): lê `App.css` e confere o conjunto permitido de breakpoints, como `no-em-dash.test.ts` lê arquivos.
- [ ] `src/components/shell/__tests__/shell.test.tsx` (existente): `TopBar` mantém nome acessível do interruptor, da fila e de "Conexões" (o texto some por CSS, o `aria-label` fica).
- [ ] O harness é a verificação de layout: jsdom não calcula CSS de arquivo.

## Notas

- Confirmado: `index.css:41-44` põe `overflow: hidden` em `html` e `body`, então o estouro **corta em vez de rolar**; `document.documentElement.scrollWidth` não serve de teste. Por isso o critério usa `getBoundingClientRect` por elemento.
- Confirmado em `App.css`: `@media` em 303 (1000), 767 (640), 979 (900), 1979 e 2417 (960), 2015 (760). A tabela da lista de projetos (`.projects-table-wrap`) rola de propósito e fica fora da contagem.
- Zoom no Electron: 200% de 900 DIP é 450 px de CSS. A RAGX-0194 mantém Exibir > zoom no menu mínimo; o harness reproduz o zoom por largura de viewport.
- Como repetir o que o auditor fez, sem o harness: `npm run build`, `npx vite preview --port 4173`, Playwright com `addInitScript` e `setViewportSize` nas larguras acima; capturas fora do repositório.
- `no-em-dash.test.ts` vale para o texto do harness em `scripts/`? Não (varre `src/` e `electron/`), mas mantenha o hábito.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0181)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
