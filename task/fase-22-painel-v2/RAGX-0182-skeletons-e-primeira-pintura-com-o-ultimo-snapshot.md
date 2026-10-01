# RAGX-0182 — Skeletons e primeira pintura com o último snapshot

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0179 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (U-11) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P9) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

O painel abre numa tela cheia com "Carregando…" (`App.tsx:109-115`, classe `.boot`) até chegarem `getSettings()` **e** o primeiro snapshot (`App.tsx:82-86`), que custa um `git` por projeto. E há um defeito pior, lido no código: se `getSnapshot()` rejeitar, `useSnapshot` só faz `console.error` (`useSnapshot.ts:20-24`), o snapshot fica `null` e a rota nunca é decidida, então o "Carregando…" **não sai nunca**. Esta tarefa troca a espera por skeletons, pinta o último snapshot conhecido na hora e dá estado de erro com "Tentar de novo".

## Entregáveis

- [ ] `src/components/ui/Skeleton.tsx` (`Skeleton`, `SkeletonText`, `SkeletonCard`): blocos `aria-hidden` dentro de um contêiner `aria-busy="true"` com um único `role="status"` em `sr-only` ("Carregando projetos"). Brilho em CSS; o `prefers-reduced-motion` já o desliga (`index.css:106-113`).
- [ ] `src/snapshotCache.ts`: `readCachedSnapshot()` e `writeCachedSnapshot(s)` em `localStorage` (chave com versão de esquema, tudo em `try/catch`, formato validado na leitura; inválido vira `null`). Grava no máximo a cada 15 s. `connectionsHealth` **não** entra no cache (um "tudo certo" velho enganaria). Só conveniência por visualizante: o painel funciona igual sem ele.
- [ ] `useSnapshot` devolve `{ snapshot, fromCache, error, retry }`: começa com o cache (`fromCache: true`), troca pelo vivo quando chega e passa a `error` se `getSnapshot()` rejeitar sem ter nada na tela. `retry` chama `getSnapshot()` de novo.
- [ ] `App.tsx`: enquanto só `getSettings` é desconhecido, nada de "Carregando…" (tela de fundo vazia, para não piscar a casca antes do onboarding); com `onboardingDone === true` e sem snapshot, desenha a casca (Sidebar e TopBar) e `Skeleton` no conteúdo; com snapshot vindo do cache, mostra a faixa "Dados de HH:mm, atualizando…" (`role="status"`) até o vivo chegar.
- [ ] Estado de erro: `getSnapshot()` falhou e não há cache: mensagem com o motivo e botão "Tentar de novo" (usa `ipcErrorMessage` se a RAGX-0180 já o criou; senão, `err.message`; não é dependência formal).
- [ ] Skeletons nos outros pontos de espera: grade de Projetos (cards), Conexões (`connections === null`, `useConnections.ts`) e o "Verificando…" de `FreshnessSection` (`ProjectPage.tsx:152-157`).
- [ ] `src/app/README.md`: parágrafo sobre a primeira pintura e o que o cache guarda (nomes, pastas e contagens dos projetos, só no armazenamento local do app).

## Fora de escopo

- Falha de **ação** (RAGX-0180). Reduzir o custo do snapshot em si (RAGX-0172 e 0175) e só reenviar o que mudou (RAGX-0175).
- Cache em disco no processo principal e novo canal IPC: o cache é do renderer, sem canal novo.
- Skeleton para `getActivity` (não há como distinguir "carregando" de "vazio").

## Critérios de aceite

- [ ] Harness da RAGX-0181 (ou o roteiro de Notas) com `getSnapshot` atrasado 3 s e **sem** cache: skeleton visível em ≤ 300 ms e nenhuma ocorrência do texto "Carregando…" em tela cheia.
- [ ] Com cache e o mesmo atraso: o primeiro `.project-card` aparece em ≤ 500 ms, com a faixa "atualizando…"; ao chegar o vivo, a faixa some e os dados trocam sem remontar a página.
- [ ] `getSnapshot` rejeitando, sem cache: aparece o erro e o botão; clicar chama `getSnapshot` de novo e, dando certo, segue para Projetos (teste).
- [ ] Cache corrompido, de outro esquema ou com `localStorage` lançando: abre como hoje, sem exceção (teste).
- [ ] Do cache não vem `connectionsHealth`: o indicador de conexões diz "verificando" até a checagem real.
- [ ] Bundle (hoje JS 306.822 B, gzip -9 91.745 B): registrar antes e depois.

## Testes

- [ ] `src/__tests__/snapshotCache.test.ts` (novo): ida e volta, validação, limite de gravação, falha do storage.
- [ ] `src/hooks/__tests__/useSnapshot.test.ts` (existente, 111 linhas): cache primeiro, vivo depois, `error`, `retry`, ordem por `generatedAt` mantida.
- [ ] `src/__tests__/App.test.tsx` (existente): skeleton no lugar do "Carregando…", faixa de dado velho, tela de erro, sem piscar a casca quando o destino é o onboarding.
- [ ] `src/components/ui/__tests__/skeleton.test.tsx` (novo): `aria-busy`, um só `role="status"`, blocos `aria-hidden`.

## Notas

- Confirmado em `App.tsx:82-86`: a rota só é decidida com `snapshot !== null`; sem snapshot, `route === null` para sempre e `App.tsx:109-115` devolve o "Carregando…".
- Cache velho nunca pode parecer fresco: o estado (`deriveProjectState`) e o selo vêm do dado em cache, por isso a faixa é obrigatória. As ações usam só `projectId`, validado no processo principal contra o snapshot real (a regra de IPC não muda).
- Tamanho esperado do cache: ~12 projetos com a série de 14 dias de economia (`SavingsSeries`), poucas dezenas de kB; o loop mede o tamanho real e registra.
- Como repetir sem o harness: `npm run build`, `npx vite preview --port 4173`, Playwright com `addInitScript` que define `window.ragx` com `getSnapshot: () => new Promise(r => setTimeout(() => r(snapshot), 3000))`; medir o instante do primeiro `.project-card` com `performance.now()`.
- `src/__tests__/no-em-dash.test.ts` vale para todo texto novo.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0182)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
