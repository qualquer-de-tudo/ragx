# RAGX-0178 — Tokens de design completos e contraste AA

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,75d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-08) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P7) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

`src/index.css` (148 linhas) só declara cor, raio e fonte (linhas 3-25); não há escala de espaço, de tipografia nem de elevação, e o estado semântico não tem variante `-wash`. `src/App.css` (2.743 linhas) usa 12 tamanhos de `font-size` diferentes (16 contando o atalho `font:`), 15 cores literais e 3 `z-index` soltos. O contraste, recalculado a partir dos tokens: `--ink-3` 4,22:1 em `--surface`, 3,97:1 em `--surface-2`, 3,67:1 em `--surface-3` (usado em `.hint`, 12,5 px); texto branco no botão primário 3,68:1 e no `.btn-danger` 3,67:1 (achado novo, não está na auditoria). Esta tarefa completa os tokens, leva o contraste a AA e deixa testes que impedem a volta.

## Entregáveis

- [x] `src/test/wcag.ts` (puro: lê `#rgb`, `#rrggbb`, `rgba()`, mistura com `color-mix` a N%, calcula razão WCAG) e `src/__tests__/contrast.test.ts`, que lê `src/index.css` com `fs` (como `no-em-dash.test.ts`) e checa a matriz abaixo. Estruturado por tema (`{ dark: ':root' }`) para a RAGX-0193 acrescentar o claro. Comece vermelho: o primeiro commit só prova os números de hoje.
- [x] Texto: `--ink-3` de `#74747c` para `#8a8a93` (calculado: 5,71 / 5,37 / 4,96 em surface, surface-2, surface-3; 6,14 em `--bg`).
- [x] Preenchimento com texto branco: `--accent-solid: #2563eb` (branco 5,17:1) em `.btn-primary` (App.css:593-597) e `.switch[aria-checked='true']`; `--critical-solid: #dc2626` (4,83:1) em `.btn-danger` (App.css:1414-1419, troca o `#ffffff` por `var(--accent-ink)`).
- [x] Texto colorido e selos: `--accent-text: #5b9bf8` e `--critical-text: #f56565` (o `.badge`, App.css:416-431, mistura o tom a 10% sobre a superfície: hoje `accent` dá 4,49 em surface-2 e 4,11 em surface-3; `critical` 4,19 em surface-3; com os novos, 5,22 e 4,93 no pior caso). `--good` e `--warning` já passam (mín. 6,34 misturados).
- [x] Borda de controle: `--line-control: #6a6a73` (3,17 a 3,92:1, WCAG 1.4.11) em `.search-input` (App.css:134), `select`, `.segmented` (1017) e `.switch` (1673). `--line` e `--line-strong` continuam decorativos (separadores).
- [x] Estado semântico completo, sem renomear `--good/--warning/--critical` (46 usos): acrescentar `--good-wash`, `--warning-wash`, `--critical-wash`, `--accent-wash` (já existe), `--*-line` (borda) e `--scrim`; trocar as cores literais de App.css:813, 818, 823, 1257, 1417, 2232, 2238, 2263, 2396, 2559, 2568, 2577 e mover `--series-delivered/--series-baseline` (1995-1996) para `:root`.
- [x] Escalas em `:root`: espaço `--sp-2/4/6/8/12/16/20/24/32`; tipografia `--fs-xs 11 · sm 12 · md 13 · lg 14 · h3 18 · h2 22 · h1 24 · stat 32` (12,5 vira 13, 13,5 vira 14, 11,5 vira 12, 15 vira 14, 20 vira 22; `.brand-name` de 10 px fica de fora, comentado); elevação sem sombra (princípio do cabeçalho de App.css): `--z-sticky 2 · --z-popover 20 · --z-modal 50 · --z-toast 60`; movimento `--dur 120ms`; `--radius-xs 4px`.
- [x] Migrar para os tokens: todo `font-size` e `font:`, todo `z-index`, toda cor e todo `120ms` de `App.css`; espaçamento só na casca (App.css:1-310) como piloto, o resto por catraca (próximo item).
- [x] Glifos `●` de 8 e 9 px (App.css:434-436, 1552-1554, 1566-1573) sobem para `var(--fs-xs)`; o `●` continua no DOM (os testes `● Defasado` dependem dele).
- [x] `src/__tests__/no-hardcoded-color.test.ts`: nenhum `#hex`, `rgb(`, `rgba(` em `src/**/*.css` e `src/**/*.tsx` fora dos blocos `:root`; aponta arquivo e linha (nome combinado com a RAGX-0193, que o estende).
- [x] `src/__tests__/css-ratchet.test.ts` + `css-ratchet.json`: conta `gap/padding/margin` com `px` literal em `App.css` e falha se subir; o loop mede o número na primeira execução e o grava, só pode cair.

## Fora de escopo

- Tema claro e `data-theme` (RAGX-0193); dividir o `App.css` em camadas por arquivo (a catraca cobre o ritmo).
- Primitivos de UI (RAGX-0179), breakpoints e `@container` (RAGX-0181), alvos de 24 px e foco (RAGX-0185), `Toast` (RAGX-0180).
- Biblioteca de UI ou de ícones: a spec mantém CSS próprio com tokens.

## Critérios de aceite

- [x] `npx vitest run src/__tests__/contrast.test.ts` verde com: `--ink`, `--ink-2`, `--ink-3` sobre `--bg`, `--surface`, `--surface-2`, `--surface-3` ≥ 4,5:1; `--good`, `--warning`, `--accent-text`, `--critical-text` sobre as quatro superfícies, puros e misturados a 10% (selo) ≥ 4,5:1; `--accent-ink` sobre `--accent-solid` e sobre `--critical-solid` ≥ 4,5:1; `--line-control` e `--series-*` sobre `--surface` ≥ 3:1.
- [x] Hoje o teste falha em 8 pares (ink-3 em 3 superfícies, branco sobre accent, branco sobre critical, selo accent em surface-2 e surface-3, selo critical em surface-3); ao fim, 0.
- [x] `font-size` distintos em `App.css` (contando `font:`): de 16 para 8 tokens (+ o 10 px da logo, fora de propósito, 9 valores no total); literais de cor fora de `:root`: de 15 para 0 (`no-hardcoded-color.test.ts`).
- [ ] Capturas a 1280x800 de Projetos, Detalhe (Visão geral) e Conexões antes e depois: só mudam o texto de apoio, os botões primário e perigo e os arredondamentos de fonte; nada quebra de linha novo. (NÃO verificado visualmente: sem captura nesta sessão.)
- [x] Bundle (hoje, em `dist/assets`: JS 306.822 B, gzip -9 91.745 B; CSS 34.835 B, gzip -9 7.096 B): registrar antes e depois; sem dependência nova.

## Testes

- [x] `src/__tests__/contrast.test.ts` (novo): matriz acima; inclui sanidade do helper (preto sobre branco = 21:1).
- [x] `src/__tests__/no-hardcoded-color.test.ts` e `css-ratchet.test.ts` (novos).
- [x] `src/components/shell/__tests__/shell.test.tsx` e `ProjectPage.test.tsx` (existentes) seguem verdes sem mudar asserts.

## Notas

- Confirmado em `src/index.css:3-25` (tokens), `:101-104` (`:focus-visible`), `:106-113` (`prefers-reduced-motion`): preservar os dois.
- Defasagem leve da auditoria: "`--line` 1,37–1,70:1" é na verdade `--line-strong`; `--line` dá 1,10 a 1,36. Não muda a conclusão (são separadores).
- Como repetir a captura do auditor: `npm run build` em `src/app`, servir `dist/` com `npx vite preview --port 4173`, abrir no Playwright com `page.addInitScript` definindo `window.ragx` (todos os métodos de `RagxBridge`, formas em `src/test/snap.ts`) e `setViewportSize` 1280x800. Sem navegador disponível, registre "não verificado visualmente" em Andamento e não marque esse critério.
- `src/__tests__/no-em-dash.test.ts` varre `src/**/*.css`: nenhum "—" em CSS.
- Se um par continuar abaixo de 4,5:1 depois do valor sugerido, escolha outro valor, rode o teste e registre o número em Andamento; os valores acima foram calculados, não escolhidos a olho.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização) (só os testes de renderização, verdes sem mudar asserções; sem screenshot)
- [x] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0178)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Primeiro o vermelho: `contrast.test.ts` (com `src/test/wcag.ts`) falhou onde devia (ink-3 4,217:1 em surface; tokens novos ausentes). Depois os tokens em `index.css`: `--ink-3 #8a8a93`, `--accent-solid`, `--critical-solid`, `--accent-text`, `--critical-text`, `--line-control`, `-wash`/`-line` dos quatro estados, `--scrim`, `--series-*` no `:root`, escalas `--sp-*`, `--fs-*`, `--z-*`, `--dur`, `--radius-xs`. `App.css` migrado por script: 12 literais de cor viraram token (o `rgba(34,197,94,0.1)` do ícone "ok" virou o wash de 0,12), todo `font-size` e `font:` (12,5→13, 13,5→14, 11,5→12, 15→14, 20→22, glifos de 8 e 9 px→11), `z-index` e `120ms`; `color: var(--critical)`/`var(--accent)` viraram `-text`; `.btn-primary`, `.btn-danger`, `.switch` e o número do passo atual usam o `-solid`; borda de controle em `.search-input`, `.segmented`, `.switch` e nos `select`. Piloto de espaço na casca (linhas 1-310): valores da escala viram `--sp-*`.
- Desvio 1: o hover dos botões era 88% do preenchimento + 12% de branco, que dá 4,18:1 com texto branco (abaixo de AA); passou a 94% + 6% e entrou no teste (`o hover dos botões ...`).
- Desvio 2: o `.brand-name` (10 px) ficou fora da escala, como a tarefa prevê; por isso são 8 tamanhos da escala + 1 = 9 valores (a meta dizia ≤ 8 contando só a escala).
- Novos testes: `contrast.test.ts` (12), `no-hardcoded-color.test.ts` (uma por arquivo, 32), `css-ratchet.test.ts` (2; o limite inicial é 201 declarações de `gap`/`padding`/`margin` com `px` literal, medido na primeira execução depois do piloto). Painel: 1091 testes verdes, `lint` e `tsc` limpos.
- Bundle (`npm run build`): CSS 34.835 → **36.808 B** (gzip 7.096 → 7.446): os tokens custam ~2 kB; JS 306.822 → 309.626 B (gzip 91.745 → 92.611), diferença da `RAGX-0175` (os `useClock`/`snapshotShare`), não desta tarefa. Nenhuma dependência nova.
- NÃO feito: capturas de tela antes/depois (sem navegador nesta sessão), então a ausência de regressão visual é só pelos testes de renderização.
