# RAGX-0193 — Tema claro

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0178, RAGX-0181 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-08, lacunas de produto e do design system) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P7, R-P11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

O painel é só escuro por decisão antiga (`src/app/README.md`, linha 8: "Tema sempre escuro"; `src/index.css:4` fixa `color-scheme: dark`) e não há nenhum mecanismo de tema: uma busca por `data-theme`, `prefers-color-scheme` e `nativeTheme` em `src/` e `electron/` volta vazia. Com os tokens completos e o contraste AA da RAGX-0178 e a casca responsiva da RAGX-0181, dá para oferecer um tema claro como **preferência**, sem rebaixar o contraste (U-08). O padrão continua escuro; claro e "seguir o sistema" são opções.

## Entregáveis

- [ ] Preferência `theme` (`'dark' | 'light' | 'system'`, padrão `'dark'`) em `electron/settings.ts`, validada em `readSettings` (que monta o objeto campo a campo e descartaria um campo novo), exposta por `getSettings` e alterada por canal IPC de lista fechada (`ragx:setPreference`, valor restrito aos três literais; se a RAGX-0191 já o criou, reutilize).
- [ ] Mecanismo em `src/`: o renderer aplica `document.documentElement.dataset.theme` com o tema **resolvido** (`dark` ou `light`; `system` resolve por `matchMedia('(prefers-color-scheme: light)')` com ouvinte de mudança). Sem `<script>` inline no `index.html` (a RAGX-0194 proíbe): a aplicação acontece em `src/main.tsx`, antes de `createRoot`, com o último tema resolvido lido de `localStorage` dentro de `try/catch` para evitar o flash, e confirmada depois por `getSettings`.
- [ ] `src/index.css`: o bloco `:root` atual (linhas 3-25) segue sendo o escuro; novo bloco `:root[data-theme='light']` redefine **todos** os tokens (superfícies, tinta, linhas, acento, `--good/--warning/--critical`, os `-wash` semânticos da 0178) e `color-scheme: light`. `::selection` (linha 98) usa token.
- [ ] Zerar cor literal fora dos blocos de token. Hoje em `src/App.css`: `rgba(...)` nas linhas 813, 818, 823 (lavados de estado), 1257 (`.modal-backdrop`), 2232-2263, 2396 e 2559-2577; `#ffffff` em `.btn-danger` (1417); `--series-delivered: #3987e5` e `--series-baseline: #d95926` (1995-1996), validadas só contra a superfície escura `#0c0c0e`. Cada uma vira token com valor por tema.
- [ ] Séries do gráfico de `TokenSavings.tsx` validadas também no claro: 3:1 ou mais contra `--surface` (WCAG 1.4.11) e continuam distinguíveis sem cor (legenda e rótulos de texto, como hoje).
- [ ] `electron/main.ts`: `backgroundColor` da janela (linha 457, hoje `'#000000'` fixo) segue o tema salvo, lido com `readSettings(userDataDir())` antes de criar a janela, e `nativeTheme.themeSource` recebe a preferência (barras de rolagem, diálogos nativos e menu acompanham).
- [ ] Seletor "Tema" na página "Preferências" (`src/pages/PreferencesPage.tsx`; a primeira das tarefas 0191, 0192 e 0193 a rodar cria a página, as outras acrescentam seção; procure o arquivo antes), com texto "Escuro", "Claro", "Seguir o sistema". Setas navegam entre as opções (primitivo de grupo da RAGX-0179).
- [ ] `src/app/README.md`: trocar "Tema sempre escuro" pela descrição das três opções e do padrão.

## Fora de escopo

- Tema claro como padrão, ou trocar de tema por horário.
- Novo desenho de marca: o `RagxMark` já usa `var(--accent)` e `var(--ink)` (`RagxMark.tsx:20-21`) e acompanha o tema; `public/favicon.svg` e os ícones do `.exe` não mudam.
- Alto contraste do Windows (`forced-colors`) e temas além de claro e escuro.

## Critérios de aceite

- [ ] Teste de contraste, nos dois temas, para todos os pares texto/fundo usados (tinta e tinta secundária sobre `--bg`, `--surface`, `--surface-2`, `--surface-3`; texto do botão primário e do perigo; cada estado semântico sobre o seu `-wash`): 4,5:1 ou mais para texto normal, 3:1 para ícone e série de gráfico. Reaproveite o teste de contraste da RAGX-0178 (confira o nome no arquivo dela); se ele só cobrir o escuro, estenda.
- [ ] Teste de varredura (no estilo de `src/__tests__/no-em-dash.test.ts`, mesmo auxiliar de arquivos e de comentários): nenhum `#hex`, `rgb(` ou `rgba(` em `src/**/*.css` e `src/**/*.tsx` fora dos blocos `:root...`; o teste falha apontando o arquivo e a linha.
- [ ] Screenshot das telas Projetos, Detalhe, Atividade, Conexões e Preferências nos dois temas, a 1280 px e a 480 px, anexadas em Andamento (ou descritas), sem texto cortado nem baixo contraste visível.
- [ ] Trocar o tema na tela atualiza na hora, sem reiniciar, e a escolha sobrevive a reabrir o painel (teste de `readSettings`/`writeSettings` e de `main.tsx`).
- [ ] Padrão intocado: com `settings.json` sem o campo, o painel abre escuro, idêntico ao de hoje.

## Testes

- [ ] `src/app/src/__tests__/theme.test.ts` (novo): resolução de `system`, ouvinte de mudança, fallback quando `localStorage` lança.
- [ ] `src/app/src/__tests__/contrast.test.ts` (novo ou o da RAGX-0178 estendido) e `no-hardcoded-color.test.ts` (novo).
- [ ] `src/app/electron/__tests__/settings.test.ts` (existente): `theme` com padrão `'dark'`, valor inválido volta ao padrão, `updateSettings` não apaga os outros campos.
- [ ] `src/app/src/pages/__tests__/PreferencesPage.test.tsx`: o seletor chama `setPreference` e reflete o estado.
- [ ] `src/app/electron/__tests__/preload.test.ts` e os quatro mocks completos de `RagxBridge` (`src/test/snap.ts`, `App.test.tsx`, `useSnapshot.test.ts`, `useJobsConnections.test.ts`), se o bridge ganhou método.

## Notas

- Confirmado em `src/App.css`: 4 ocorrências de hex e 11 de `rgba(` (a quantidade de cor literal é pequena; o grosso do CSS já usa `var(--...)`, com `--ink-2`, `--line` e `--ink` entre os mais usados). Confirmado em `src/index.css:3-25` e `electron/main.ts:457`.
- O Vite constrói o CSS como arquivo externo; as larguras dinâmicas em `style={{ ... }}` (`ProjectCard.tsx:137,153`, `QueueIndicator.tsx:69`, `ProjectPage.tsx:316`, `TokenSavings.tsx:114`) não são cor e não entram aqui.
- A RAGX-0194 restringe a CSP: nada de `<script>` inline para o tema, e nada de fonte remota para o claro.
- O `jsdom` não calcula CSS de arquivo, então o contraste se testa lendo os valores dos tokens, não a tela renderizada.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0193)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
