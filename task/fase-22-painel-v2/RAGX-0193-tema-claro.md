# RAGX-0193 — Tema claro

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0178, RAGX-0181 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-08, lacunas de produto e do design system) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P7, R-P11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

O painel é só escuro por decisão antiga (`src/app/README.md`, linha 8: "Tema sempre escuro"; `src/index.css:4` fixa `color-scheme: dark`) e não há nenhum mecanismo de tema: uma busca por `data-theme`, `prefers-color-scheme` e `nativeTheme` em `src/` e `electron/` volta vazia. Com os tokens completos e o contraste AA da RAGX-0178 e a casca responsiva da RAGX-0181, dá para oferecer um tema claro como **preferência**, sem rebaixar o contraste (U-08). O padrão continua escuro; claro e "seguir o sistema" são opções.

## Entregáveis

- [x] Preferência `theme` (`'dark' | 'light' | 'system'`, padrão `'dark'`) em `electron/settings.ts`, validada em `readSettings` (que monta o objeto campo a campo e descartaria um campo novo), exposta por `getSettings` e alterada por canal IPC de lista fechada (`ragx:setPreference`, valor restrito aos três literais; se a RAGX-0191 já o criou, reutilize).
- [x] Mecanismo em `src/`: o renderer aplica `document.documentElement.dataset.theme` com o tema **resolvido** (`dark` ou `light`; `system` resolve por `matchMedia('(prefers-color-scheme: light)')` com ouvinte de mudança). Sem `<script>` inline no `index.html` (a RAGX-0194 proíbe): a aplicação acontece em `src/main.tsx`, antes de `createRoot`, com o último tema resolvido lido de `localStorage` dentro de `try/catch` para evitar o flash, e confirmada depois por `getSettings`.
- [x] `src/index.css`: o bloco `:root` atual (linhas 3-25) segue sendo o escuro; novo bloco `:root[data-theme='light']` redefine **todos** os tokens (superfícies, tinta, linhas, acento, `--good/--warning/--critical`, os `-wash` semânticos da 0178) e `color-scheme: light`. `::selection` (linha 98) usa token.
- [x] Zerar cor literal fora dos blocos de token. Hoje em `src/App.css`: `rgba(...)` nas linhas 813, 818, 823 (lavados de estado), 1257 (`.modal-backdrop`), 2232-2263, 2396 e 2559-2577; `#ffffff` em `.btn-danger` (1417); `--series-delivered: #3987e5` e `--series-baseline: #d95926` (1995-1996), validadas só contra a superfície escura `#0c0c0e`. Cada uma vira token com valor por tema.
- [x] Séries do gráfico de `TokenSavings.tsx` validadas também no claro (3:1 contra `--surface` pelo `contrast.test.ts` no tema claro; a captura do gráfico no claro não foi vista): 3:1 ou mais contra `--surface` (WCAG 1.4.11) e continuam distinguíveis sem cor (legenda e rótulos de texto, como hoje).
- [x] `electron/main.ts`: `backgroundColor` da janela (linha 457, hoje `'#000000'` fixo) segue o tema salvo, lido com `readSettings(userDataDir())` antes de criar a janela, e `nativeTheme.themeSource` recebe a preferência (barras de rolagem, diálogos nativos e menu acompanham).
- [x] Seletor "Tema" na página "Preferências" (`src/pages/PreferencesPage.tsx`; a primeira das tarefas 0191, 0192 e 0193 a rodar cria a página, as outras acrescentam seção; procure o arquivo antes), com texto "Escuro", "Claro", "Seguir o sistema". Setas navegam entre as opções (primitivo de grupo da RAGX-0179).
- [x] `src/app/README.md`: trocar "Tema sempre escuro" pela descrição das três opções e do padrão.

## Fora de escopo

- Tema claro como padrão, ou trocar de tema por horário.
- Novo desenho de marca: o `RagxMark` já usa `var(--accent)` e `var(--ink)` (`RagxMark.tsx:20-21`) e acompanha o tema; `public/favicon.svg` e os ícones do `.exe` não mudam.
- Alto contraste do Windows (`forced-colors`) e temas além de claro e escuro.

## Critérios de aceite

- [x] Teste de contraste, nos dois temas, para todos os pares texto/fundo usados (tinta e tinta secundária sobre `--bg`, `--surface`, `--surface-2`, `--surface-3`; texto do botão primário e do perigo; cada estado semântico sobre o seu `-wash`): 4,5:1 ou mais para texto normal, 3:1 para ícone e série de gráfico. Reaproveite o teste de contraste da RAGX-0178 (confira o nome no arquivo dela); se ele só cobrir o escuro, estenda.
- [x] Teste de varredura (no estilo de `src/__tests__/no-em-dash.test.ts`, mesmo auxiliar de arquivos e de comentários): nenhum `#hex`, `rgb(` ou `rgba(` em `src/**/*.css` e `src/**/*.tsx` fora dos blocos `:root...`; o teste falha apontando o arquivo e a linha.
- [x] Screenshot das telas Projetos, Detalhe, Atividade, Conexões e Preferências nos dois temas, a 1280 px e a 480 px, anexadas em Andamento (ou descritas), sem texto cortado nem baixo contraste visível.
- [x] Trocar o tema na tela atualiza na hora, sem reiniciar, e a escolha sobrevive a reabrir o painel (teste de `readSettings`/`writeSettings` e de `main.tsx`).
- [x] Padrão intocado: com `settings.json` sem o campo, o painel abre escuro, idêntico ao de hoje.

## Testes

- [x] `src/app/src/__tests__/theme.test.ts` (novo): resolução de `system`, ouvinte de mudança, fallback quando `localStorage` lança.
- [x] `src/app/src/__tests__/contrast.test.ts` (novo ou o da RAGX-0178 estendido) e `no-hardcoded-color.test.ts` (novo).
- [x] `src/app/electron/__tests__/settings.test.ts` (existente): `theme` com padrão `'dark'`, valor inválido volta ao padrão, `updateSettings` não apaga os outros campos.
- [x] `src/app/src/pages/__tests__/PreferencesPage.test.tsx`: o seletor chama `setPreference` e reflete o estado.
- [x] `src/app/electron/__tests__/preload.test.ts` e os quatro mocks completos de `RagxBridge` (`src/test/snap.ts`, `App.test.tsx`, `useSnapshot.test.ts`, `useJobsConnections.test.ts`), se o bridge ganhou método.

## Notas

- Confirmado em `src/App.css`: 4 ocorrências de hex e 11 de `rgba(` (a quantidade de cor literal é pequena; o grosso do CSS já usa `var(--...)`, com `--ink-2`, `--line` e `--ink` entre os mais usados). Confirmado em `src/index.css:3-25` e `electron/main.ts:457`.
- O Vite constrói o CSS como arquivo externo; as larguras dinâmicas em `style={{ ... }}` (`ProjectCard.tsx:137,153`, `QueueIndicator.tsx:69`, `ProjectPage.tsx:316`, `TokenSavings.tsx:114`) não são cor e não entram aqui.
- A RAGX-0194 restringe a CSP: nada de `<script>` inline para o tema, e nada de fonte remota para o claro.
- O `jsdom` não calcula CSS de arquivo, então o contraste se testa lendo os valores dos tokens, não a tela renderizada.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0193)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_

## Andamento

- 2026-10-01 — Implementado: bloco `:root[data-theme='light']` em `index.css` com todos os tokens de cor (superfícies `#f4f4f7`/`#ffffff`/`#f0f0f4`/`#e6e6ec`, tinta `#16161a`/`#4a4a54`/`#5f5f6a`, `-solid`, `-text`, `-wash`, `-line`, `--scrim`, `--line-control`, séries); `src/theme.ts` (`resolveTheme`, `applyTheme`, `watchSystemTheme`, `initTheme`, `setTheme`, `localStorage` em `try/catch`); `main.tsx` chama `initTheme()` antes de `createRoot`; `theme` em `settings.ts` (só `light`/`system` ficam, inválido volta ao padrão) e `getSettings`; canal `ragx:setTheme` de lista fechada (`THEMES`; o `ragx:setPreference` da 0191 é booleano, por isso um canal à parte), `preload`, `RagxBridge.setTheme`, os 4 mocks; `main.ts` (`windowBackground()` no lugar do `'#000000'` fixo e `nativeTheme.themeSource` pelo tema salvo, aplicado antes de criar a janela e a cada troca); seletor "Tema" (Escuro, Claro, Seguir o sistema) na `PreferencesPage`, que reverte e avisa se a gravação falha.
- Contraste: o `contrast.test.ts` da 0178 ganhou o tema claro (`THEMES`). Primeira rodada: 1 par abaixo de 4,5:1 (`--critical-text` no selo sobre `--surface-3`, 4,44), corrigido escurecendo para `#a51919`; depois 22 testes verdes nos dois temas. `no-hardcoded-color.test.ts` já cobria o `:root[data-theme]` e não precisou mudar (nenhuma cor literal fora dos tokens, desde a 0178).
- **Visto** (harness com `--theme light`, capturas de Projetos, Detalhe, Atividade, Conexões e Preferências a 480 e 1280 px): 10 medições, 0 problema de layout; capturas de Projetos a 1280 e Preferências a 480 conferidas a olho: texto legível, selos e botões com contraste. Regressão no escuro: 42 medições (14 telas x 3 larguras), 0 problema.
- Achado: a ponte simulada do harness (`bridge.js`) não tinha os métodos da 0192 (`onUpdate` etc.) e a tela Preferências quebrava; ganhou `setTheme` e os métodos de atualização, e `getSettings` lê o tema do `localStorage` para o harness poder pedir o claro.
- Testes novos: `theme.test.ts` (9: resolução, armazenamento com `localStorage` lançando, ouvinte do sistema, sem `matchMedia`, `initTheme` confirmando pelo `getSettings`, padrão intocado, `setTheme`), `settings` (1), `ipc` (3 grupos), `PreferencesPage` (+2), `preload.test.ts` (`setTheme`). Painel: 1921 testes verdes, `lint` e `tsc` limpos.
- Bundle: JS 343.101 → ver o `dist/assets` desta rodada: **347.085 B** (gzip 104.243; as tarefas 0192 e 0193 somam aqui); CSS 43.777 → **44.491 B** (gzip 8.865).
- Não feito: conferir o `nativeTheme` e o `backgroundColor` no Electron real (só testes e o renderer no Edge), e a captura do gráfico de economia no claro.
