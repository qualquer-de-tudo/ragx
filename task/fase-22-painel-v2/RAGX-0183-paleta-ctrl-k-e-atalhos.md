# RAGX-0183 — Paleta Ctrl+K e atalhos

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0179 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-10) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P9) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

O painel não tem atalho de teclado nem paleta de comandos. A busca da topbar só filtra projetos e, se a pessoa digita em outra tela, a manda para Projetos (`App.tsx:93-97`, `TopBar.tsx:57-70`). Para ir de um projeto a outro, ou disparar "Atualizar", são vários cliques. Esta tarefa cria uma paleta (Ctrl+K) que navega e dispara ações da fila, e um conjunto pequeno de atalhos, sem mudar a regra de IPC: a paleta só pede `kind` + `projectId`.

## Entregáveis

- [x] `src/commands.ts` (puro): monta a lista de comandos a partir de `projects`, `jobs` e do estado e filtra com `foldForSearch` (`format.ts`, sem acento nem maiúscula). Ordem: prefixo, depois trecho; no máximo 8 resultados. Comandos: ir para Projetos, Atividade, Conexões, Como funciona; "Abrir <projeto>"; "Atualizar <projeto>" (`update`, desabilitado se `!exists`); "Gerar embeddings em <projeto>" (`embed`, só com `missingEmbeddings(counts) > 0`, `state.ts:110`); "Verificar conexões agora"; "Refazer a configuração inicial".
- [x] Lista fechada de `kind` que a paleta pode enfileirar: `['update', 'embed']`, constante exportada. Nada destrutivo: "Reindexar do zero", remover do hub e hooks exigem o `ConfirmButton` e ficam fora.
- [x] `src/components/ui/CommandPalette.tsx` sobre o `Modal` da RAGX-0179: padrão combobox (`input role="combobox"`, `aria-expanded`, `aria-controls`, `aria-activedescendant`; lista `role="listbox"`, itens `role="option"`, `aria-selected`), setas com volta ao fim, Enter executa, Esc fecha e devolve o foco, contagem de resultados em região `aria-live`.
- [x] `src/hooks/useShortcuts.ts`, ligado em `App.tsx` (`keydown` em `window`): `Ctrl/Cmd+K` abre e fecha; `/` foca a busca da topbar; `?` abre a ajuda de atalhos; `Ctrl/Cmd+1..4` navega para as quatro telas. Ignora `/` e `?` com foco em `input`, `textarea`, `select` ou `contenteditable`; `Ctrl+K` vale sempre. Sem atalho no onboarding (não há barra lateral).
- [x] Ajuda de atalhos: lista dos atalhos no mesmo `Modal`, com o texto das teclas em `<kbd>`.
- [x] Dica "Ctrl K" no campo de busca da topbar (placeholder ou `kbd` ao lado), sem tirar o filtro de projetos que existe hoje.
- [x] `src/app/README.md`: seção "Atalhos" com a tabela e a lista fechada de ações da paleta.

## Fora de escopo

- Buscar no conteúdo do índice pela paleta: texto livre para a CLI é a RAGX-0187, com canal próprio; a paleta só procura em memória (páginas, projetos, ações).
- Atalhos configuráveis; menu nativo e seus aceleradores (RAGX-0194).
- Qualquer ação destrutiva ou que peça confirmação.

## Critérios de aceite

- [x] `Ctrl+K` abre a paleta de qualquer tela (menos onboarding); digitar "jur" mostra "Juriflux" (acento e caixa ignorados); Enter abre o projeto; Esc fecha e o foco volta ao elemento anterior.
- [x] "Atualizar Juriflux" chama `window.ragx.enqueueJob` com **exatamente** `{ kind: 'update', projectId: 'juriflux' }` (asserção de igualdade estrita, sem campo extra); projeto com `exists === false` aparece desabilitado e não chama nada.
- [x] A paleta nunca oferece um `kind` fora de `['update', 'embed']` (teste de propriedade sobre todos os comandos gerados).
- [x] `/` e `?` não disparam com foco em campo de texto; `Ctrl+K` dispara mesmo assim.
- [x] Leitor de tela: o nome acessível do combobox é "Buscar comando"; a opção ativa é anunciada; a contagem muda com o filtro (teste com `aria-activedescendant` e a região `aria-live`).
- [x] Captura a 480 e 1280 px com a paleta aberta: dentro da janela, rolagem só na lista (`getBoundingClientRect().right <= innerWidth`). (Harness da 0181, telas `paleta` e `atalhos` a 450, 480 e 1280 px: 6 medições, 0 problema; captura de 480 px vista.)
- [x] Bundle (hoje JS 306.822 B, gzip -9 91.745 B): registrar antes e depois; sem dependência de busca difusa.

## Testes

- [x] `src/__tests__/commands.test.ts` (novo): geração, filtro sem acento, ordem, limite de 8, desabilitados, lista fechada de `kind`.
- [x] `src/components/ui/__tests__/commandPalette.test.tsx` (novo): teclado completo, ARIA, foco devolvido, `enqueueJob` com argumentos exatos.
- [x] `src/hooks/__tests__/useShortcuts.test.tsx` (novo): foco em campo, `Ctrl` e `Meta`, onboarding sem atalhos, remoção do ouvinte ao desmontar.
- [x] `src/__tests__/App.test.tsx` (existente): `Ctrl+K` pelo `App` inteiro; a busca da topbar continua filtrando projetos.

## Notas

- Confirmado em `TopBar.tsx:57-70` (`type="search"`, `aria-label="Buscar projeto"`) e `App.tsx:93-97` (redireciona para Projetos).
- No Windows, **não use Alt** em atalho: com `autoHideMenuBar: true` (`electron/main.ts:456`) o Alt mostra a barra de menu. `Ctrl+0`, `Ctrl+=` e `Ctrl+-` são do zoom do menu Exibir (RAGX-0194 os mantém); não os reutilize.
- A regra de IPC se mantém: o catálogo é fechado no processo principal (`electron/jobs/catalog.ts`); a paleta apenas escolhe um `kind` que o catálogo já aceita para um projeto do snapshot.
- `src/__tests__/no-em-dash.test.ts` vale para todo texto novo de `src/`.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [x] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0183)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `src/commands.ts` (puro: `buildCommands`, `filterCommands`, `PALETTE_JOB_KINDS = ['update', 'embed']`, `MAX_RESULTS = 8`), `src/shortcuts.ts` (`SHORTCUTS`, `shortcutFor`), `ui/CommandPalette.tsx` (`CommandPalette` e `ShortcutsHelp` sobre o `Modal`), `hooks/useShortcuts.ts`, ligados em `App.tsx` (estado `overlay`; sem atalho no onboarding; com uma janela aberta só o `Ctrl K` age, para fechar), `id="topbar-search"` e a dica `Ctrl K` (`kbd`, some em foco e abaixo de 900 px) na busca. "Atualizar/Gerar embeddings" passam por `enqueue` de `jobs.ts` (`window.ragx.enqueueJob({ kind, projectId })`, com o aviso de falha da 0180) e dão um aviso de sucesso.
- Testes novos: `commands.test.ts` (9, com a propriedade da lista fechada e as chaves exatas `kind`/`projectId`/`type`), `commandPalette.test.tsx` (7: combobox, setas com volta ao fim, Home/End, `aria-activedescendant`, `toStrictEqual` do `update`, desabilitado, contagem `aria-live`, Esc), `useShortcuts.test.tsx` (4: foco em campo, Ctrl e Meta, desabilitado, desmontar), `app-shortcuts.test.tsx` (7, pelo `App` inteiro, inclusive `enqueueJob` com `toStrictEqual({ kind: 'update', projectId: 'juriflux' })` e o foco devolvido a quem abriu). Painel: 1259 testes verdes, `lint` e `tsc` limpos.
- Decisões: "prefixo" inclui o começo de uma palavra do rótulo ("jur" acha "Abrir Juriflux"); os atalhos moram em `src/shortcuts.ts` e não no componente por causa da regra `react-refresh/only-export-components`; o rótulo "Refazer a configuração inicial" abre o onboarding (rota), não é ação de fila.
- Bundle: JS 315.332 → **320.606 B** (gzip 94.773 → 96.336); CSS 39.620 → **40.832 B** (gzip 7.947 → 8.149). Sem dependência de busca difusa nem nenhuma outra.
- Não feito: a conferência por leitor de tela de verdade (só os atributos ARIA e os testes).
