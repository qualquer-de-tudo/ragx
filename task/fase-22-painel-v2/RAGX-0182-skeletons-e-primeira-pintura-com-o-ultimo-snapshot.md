# RAGX-0182 — Skeletons e primeira pintura com o último snapshot

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0179 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-11) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P9) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

O painel abre numa tela cheia com "Carregando…" (`App.tsx:109-115`, classe `.boot`) até chegarem `getSettings()` **e** o primeiro snapshot (`App.tsx:82-86`), que custa um `git` por projeto. E há um defeito pior, lido no código: se `getSnapshot()` rejeitar, `useSnapshot` só faz `console.error` (`useSnapshot.ts:20-24`), o snapshot fica `null` e a rota nunca é decidida, então o "Carregando…" **não sai nunca**. Esta tarefa troca a espera por skeletons, pinta o último snapshot conhecido na hora e dá estado de erro com "Tentar de novo".

## Entregáveis

- [x] `src/components/ui/Skeleton.tsx` (`Skeleton`, `SkeletonText`, `SkeletonCard`): blocos `aria-hidden` dentro de um contêiner `aria-busy="true"` com um único `role="status"` em `sr-only` ("Carregando projetos"). Brilho em CSS; o `prefers-reduced-motion` já o desliga (`index.css:106-113`).
- [x] `src/snapshotCache.ts`: `readCachedSnapshot()` e `writeCachedSnapshot(s)` em `localStorage` (chave com versão de esquema, tudo em `try/catch`, formato validado na leitura; inválido vira `null`). Grava no máximo a cada 15 s. `connectionsHealth` **não** entra no cache (um "tudo certo" velho enganaria). Só conveniência por visualizante: o painel funciona igual sem ele.
- [x] `useSnapshot` devolve `{ snapshot, fromCache, error, retry }`: começa com o cache (`fromCache: true`), troca pelo vivo quando chega e passa a `error` se `getSnapshot()` rejeitar sem ter nada na tela. `retry` chama `getSnapshot()` de novo.
- [x] `App.tsx`: enquanto só `getSettings` é desconhecido, nada de "Carregando…" (tela de fundo vazia, para não piscar a casca antes do onboarding); com `onboardingDone === true` e sem snapshot, desenha a casca (Sidebar e TopBar) e `Skeleton` no conteúdo; com snapshot vindo do cache, mostra a faixa "Dados de HH:mm, atualizando…" (`role="status"`) até o vivo chegar.
- [x] Estado de erro: `getSnapshot()` falhou e não há cache: mensagem com o motivo e botão "Tentar de novo" (usa `ipcErrorMessage` se a RAGX-0180 já o criou; senão, `err.message`; não é dependência formal).
- [x] Skeletons nos outros pontos de espera: grade de Projetos (cards), Conexões (`connections === null`, `useConnections.ts`) e o "Verificando…" de `FreshnessSection` (`ProjectPage.tsx:152-157`).
- [x] `src/app/README.md`: parágrafo sobre a primeira pintura e o que o cache guarda (nomes, pastas e contagens dos projetos, só no armazenamento local do app).

## Fora de escopo

- Falha de **ação** (RAGX-0180). Reduzir o custo do snapshot em si (RAGX-0172 e 0175) e só reenviar o que mudou (RAGX-0175).
- Cache em disco no processo principal e novo canal IPC: o cache é do renderer, sem canal novo.
- Skeleton para `getActivity` (não há como distinguir "carregando" de "vazio").

## Critérios de aceite

- [x] Harness da RAGX-0181 (ou o roteiro de Notas) com `getSnapshot` atrasado 3 s e **sem** cache: skeleton visível em ≤ 300 ms e nenhuma ocorrência do texto "Carregando…" em tela cheia.
- [x] Com cache e o mesmo atraso: o primeiro `.project-card` aparece em ≤ 500 ms, com a faixa "atualizando…"; ao chegar o vivo, a faixa some e os dados trocam sem remontar a página.
- [x] `getSnapshot` rejeitando, sem cache: aparece o erro e o botão; clicar chama `getSnapshot` de novo e, dando certo, segue para Projetos (teste).
- [x] Cache corrompido, de outro esquema ou com `localStorage` lançando: abre como hoje, sem exceção (teste).
- [x] Do cache não vem `connectionsHealth`: o indicador de conexões diz "verificando" até a checagem real.
- [x] Bundle (hoje JS 306.822 B, gzip -9 91.745 B): registrar antes e depois.

## Testes

- [x] `src/__tests__/snapshotCache.test.ts` (novo): ida e volta, validação, limite de gravação, falha do storage.
- [x] `src/hooks/__tests__/useSnapshot.test.ts` (existente, 111 linhas): cache primeiro, vivo depois, `error`, `retry`, ordem por `generatedAt` mantida.
- [x] `src/__tests__/App.test.tsx` (existente): skeleton no lugar do "Carregando…", faixa de dado velho, tela de erro, sem piscar a casca quando o destino é o onboarding.
- [x] `src/components/ui/__tests__/skeleton.test.tsx` (novo): `aria-busy`, um só `role="status"`, blocos `aria-hidden`.

## Notas

- Confirmado em `App.tsx:82-86`: a rota só é decidida com `snapshot !== null`; sem snapshot, `route === null` para sempre e `App.tsx:109-115` devolve o "Carregando…".
- Cache velho nunca pode parecer fresco: o estado (`deriveProjectState`) e o selo vêm do dado em cache, por isso a faixa é obrigatória. As ações usam só `projectId`, validado no processo principal contra o snapshot real (a regra de IPC não muda).
- Tamanho esperado do cache: ~12 projetos com a série de 14 dias de economia (`SavingsSeries`), poucas dezenas de kB; o loop mede o tamanho real e registra.
- Como repetir sem o harness: `npm run build`, `npx vite preview --port 4173`, Playwright com `addInitScript` que define `window.ragx` com `getSnapshot: () => new Promise(r => setTimeout(() => r(snapshot), 3000))`; medir o instante do primeiro `.project-card` com `performance.now()`.
- `src/__tests__/no-em-dash.test.ts` vale para todo texto novo.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Nenhuma regressão visual nas telas afetadas (harness da 0181 a 450 e 1280 px: 20 medições, 0 problema; testes de renderização verdes)
- [x] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0182)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `src/snapshotCache.ts`, `useSnapshot` (`{ snapshot, fromCache, error, retry }`, o cache sempre cede ao vivo; entre vivos vale o mais novo por `generatedAt`; o erro só aparece sem nada na tela; usa `ipcErrorMessage` da 0180), `ui/Skeleton` (`Skeleton`, `SkeletonText`, `SkeletonCard`, `SkeletonRegion`), `App.tsx` (fundo vazio enquanto só as preferências são desconhecidas; casca com skeleton ou erro e "Tentar de novo" sem snapshot; faixa `.stale-banner` com o cache), skeleton em `PendingCard` (Conexões) e em "Verificando…" de `FreshnessSection` (a região mantém o texto "Verificando…" em `sr-only`), `formatClock`.
- **Medido** (`scripts/measure-first-paint.mjs`, Edge, `getSnapshot` atrasado em 3.000 ms): **sem cache**, o skeleton aparece em **115 ms** (critério ≤ 300) e "Carregando…" não está na tela; **com cache**, o primeiro `.project-card` aparece em **186 ms** (critério ≤ 500) com a faixa "Dados de 10:42, atualizando…", a faixa some quando o vivo chega e o cartão é o **mesmo nó** (sem remontar). Cache de 12 projetos com a série de 14 dias: **21.964 caracteres** (~22 kB, abaixo das "poucas dezenas de kB" previstas).
- Testes novos: `snapshotCache.test.ts` (12), `useSnapshotCache.test.ts` (5), `skeleton.test.tsx` (2), `first-paint.test.tsx` (5: skeleton sem "Carregando…", cache com faixa e sem remontar, "verificando" sem connectionsHealth, erro + "Tentar de novo", onboarding sem piscar a casca). Painel: 1223 testes verdes, `lint` e `tsc` limpos; harness a 450/1280 px: 0 problema.
- Achados no caminho: (1) o Node 25 coloca um `localStorage` global sem métodos que esconde o do jsdom; os testes que dependiam de armazenamento (`listPrefs` incluído) rodavam sem ele. `src/test/setup.ts` ganhou um polyfill em memória e limpa a chave do cache a cada teste. (2) O teste de propriedade de `telemetry-tail.test.ts` (RAGX-0174) falhou uma vez na suíte inteira por depender de `Date.now()` real perto da borda de 24 h; o relógio dele agora é congelado (passou 6/6 isolado antes e a suíte inteira depois).
- Bundle: JS 311.809 (0180) → 312.209 (0181) → **315.332 B** (gzip 93.917 → 94.773); CSS 39.046 → **39.620 B** (gzip 7.819 → 7.947). Sem dependência nova.
- Não feito: a barra "Verificando…" da `FreshnessSection` e o skeleton de Conexões não foram vistos em captura (só nos testes).
