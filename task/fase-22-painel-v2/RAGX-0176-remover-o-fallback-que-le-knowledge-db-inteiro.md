# RAGX-0176 — Remover o fallback que lê `knowledge.db` inteiro

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,25d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-06) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P6) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

Quando um projeto não tem `.ragx/status.json`, o snapshot cai para `readProjectStats` (`src/app/electron/data/project-stats.ts:43`), que faz `fs.readFileSync` do `knowledge.db` **inteiro** para a memória e o abre no `sql.js` só para três `COUNT(*)`. Neste hub há bancos de até **150 MB**; a cada 5 s, por projeto sem `status.json`, isso seria um pico de memória do tamanho do banco (ou mais, com a cópia do WASM). Hoje o caminho não dispara porque os 12 projetos têm `status.json`, mas qualquer projeto indexado antes dele (ou com o arquivo apagado) ativa o problema. O `sql.js` ainda custa 24 MB em `node_modules`, 2,7 MB de `.wasm` desempacotado e uma inicialização no `app.whenReady()` que só existe para esse fallback.

## Entregáveis

- [x] **Medir primeiro**: tamanho do `app.asar` (30,3 MB na beta.4) e quanto dele é `sql.js` (`npx asar list release/win-unpacked/resources/app.asar | grep sql.js`), tamanho do instalador (102,3 MB na beta.4), e a RAM do processo principal logo após o início com a linha de base da `RAGX-0177`; registrar em Andamento
- [x] `electron/data/snapshot.ts`: remover `readStats` de `SnapshotDeps` (linha 17) e de `REAL_DEPS` (linha 47), e o ramo `else` que o chama (linhas ~136–153). Sem `status.json`, `counts` fica `null` e `countsUnavailableReason` explica: "Sem .ragx/status.json: reindexe este projeto (Atualizar agora) para o painel mostrar os números."; pasta sem `.ragx/knowledge.db` mantém o motivo "projeto ainda não foi indexado"
- [x] `src/state.ts` (`deriveProjectState`, linha 13): `counts === null` sem `status.json` deixa de ser `error` ("Com problema", só "Ver detalhes") e passa a `stale` ("Defasado", ação "Atualizar agora", que enfileira `update` e gera o `status.json`); `error` fica para `lastError !== null`. Conferir `ProjectPage.tsx:78,117` e `ProjectsPage.tsx:266` ("sem dados") com o texto novo
- [x] Apagar `electron/data/project-stats.ts` e `electron/data/__tests__/project-stats.test.ts`; remover `initSqlWasm` e o `import` em `electron/main.ts` (linhas 6 e 523–529), os tipos `ProjectStats`/`ProjectStatsUnavailable` de `electron/data/types.ts:19` quando ficarem sem uso, e `readStats` dos testes de `snapshot.test.ts` (casos b e b2 viram o caso "sem status.json")
- [x] `npm uninstall sql.js @types/sql.js` em `src/app` (atualiza `package.json` e `package-lock.json`); remover o `asarUnpack` de `node_modules/sql.js/dist/*.wasm` e o comentário de `electron-builder.yml` (linhas 14–21)
- [x] `src/app/README.md` ("De onde vêm os dados" e a lista de arquivos lidos): sai `.ragx/knowledge.db` e o "cai para contagens lidas direto"; entra a regra de que o painel **nunca** abre o banco

## Fora de escopo

- Gerar o `status.json` por outro caminho ou ler o banco por outro meio (o painel lê `status.json`, ponto)
- Mudar o conteúdo do `status.json` ou a CLI que o escreve (`src/ragx/indexing/status_file.py`)
- Pausar pollers (`RAGX-0171`), `git` sem spawn (`RAGX-0172`), telemetria (`RAGX-0174`)
- Reempacotar e publicar o instalador (release é decisão humana)

## Critérios de aceite

- [x] `grep -rn "sql.js\|readProjectStats\|initSqlWasm" src/app --include=*.ts --include=*.tsx --include=*.yml --include=*.json` (fora de `node_modules` e `dist`) não encontra nada
- [x] Projeto sem `status.json` aparece como "Defasado" com o botão "Atualizar agora" e o texto do motivo; clicar enfileira `update` (teste de renderização)
- [x] Nenhuma leitura de `knowledge.db` pelo painel: o snapshot de um projeto com banco de 150 MB sem `status.json` não aloca o arquivo (por teste que falha se um arquivo do processo principal importar leitor de SQLite ou citar `knowledge.db` e ler arquivo; RSS não medido)
- [x] `npm run build`/`npm run package` seguem funcionando (o `electron-builder` não referencia mais o `sql.js`); o `app.asar` encolhe o medido na linha de base

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| `app.asar` | 30,3 MB (30.263.087 B, beta.4; 33 entradas de `sql.js`; wasm em `app.asar.unpacked`) | **9,0 MB** (8.959.358 B; 0 entradas de `sql.js`; sem `app.asar.unpacked`): **-21,3 MB** |
| Instalador | 102,3 MB (beta.4) | não reconstruído (só `electron-builder --dir`); a queda esperada é a do asar, comprimida |
| Pico de RSS com projeto de 150 MB sem `status.json` | não medido (o código lia o arquivo inteiro com `readFileSync`) | sem leitura: a regra é garantida por teste, não por RSS |
| Dependências de runtime do painel | `react`, `react-dom`, `sql.js` | `react`, `react-dom` |

Comando: `npx asar list release/win-unpacked/resources/app.asar | grep -c sql.js` e `node scripts/measure-runtime.mjs --plan visible:2` (da `RAGX-0177`, em `src/app`)

## Testes

- [x] `electron/data/__tests__/snapshot.test.ts`: sem `status.json` devolve `counts: null`, `hasStatusFile: false` e o motivo novo; com `status.json` nada muda; pasta ausente e `.ragx` ausente mantêm os motivos
- [x] `src/__tests__/state.test.ts`: `deriveProjectState` devolve `stale` para `counts: null` sem `status.json` e `error` para `lastError`
- [x] `src/pages/__tests__/ProjectsPage.test.tsx` e `ProjectPage.test.tsx`: o card e o detalhe mostram o motivo e a ação "Atualizar agora"
- [x] `electron/__tests__/ipc.test.ts` e demais testes do painel verdes sem `sql.js` instalado

## Notas

Risco aceito: projeto indexado por uma versão antiga do RAGX, sem `status.json`, passa a mostrar "Defasado" até a próxima indexação em vez de mostrar números aproximados; a ação de um clique resolve. O `pendingEmbeddings` aproximado (`chunks - embeddings`) some junto com o fallback. Se houver teste que dependa de `sql.js` como fixture (`project-stats.test.ts` importa `sql.js` para montar o banco), ele sai com o arquivo. Confirmar que nenhum script de `scripts/` (`prepare-bundle.mjs`, `after-pack.cjs`) cita `sql.js` antes de apagar a dependência.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Nenhuma regressão visual nas telas afetadas (teste de renderização; sem screenshot)
- [x] Commit `tipo(escopo): descrição (RAGX-0176)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Medido antes: `release/win-unpacked/resources/app.asar` 30.263.087 B com 33 entradas de `sql.js` e os `.wasm` em `app.asar.unpacked`; instalador beta.4 102.301.840 B; `node_modules/sql.js` 24 MB.
- Implementado: `snapshot.ts` sem `readStats` (sem `status.json`, `counts: null` e `countsUnavailableReason` = `NO_STATUS_REASON` quando há banco, ou "projeto ainda não foi indexado" quando não há; só um `existsSync` do banco, nenhuma leitura); `state.ts` (`counts === null` sem erro vira `stale`, `error` só com `lastError`); apagados `project-stats.ts` e o teste dele, `initSqlWasm` do `main.ts`, `ProjectStats`/`ProjectStatsUnavailable` de `types.ts`, o `asarUnpack` do `electron-builder.yml`; `npm uninstall sql.js @types/sql.js` (dependências de runtime: `react`, `react-dom`). Testes: `snapshot.test.ts` (b, b2), `state.test.ts`, `ProjectsPage.test.tsx` (card "Defasado" + "Atualizar agora" enfileira `update`), `ProjectPage.test.tsx` (o motivo no detalhe) e `electron/__tests__/no-knowledge-db.test.ts` (nada no processo principal importa leitor de SQLite nem lê arquivo junto de `knowledge.db`).
- **Depois**: `npm run build` e `electron-builder --dir` funcionam sem `sql.js`; `app.asar` 8.959.358 B (-21,3 MB), 0 entradas de `sql.js`. Painel: 983+ testes verdes, `lint` e `tsc` dos dois projetos limpos.
- Mudança de comportamento (já prevista em Notas): o projeto sem `status.json` deixa de mostrar contagens aproximadas e de aparecer como "Com problema"; aparece "Defasado" até a próxima indexação. O texto de "pendingEmbeddings = chunks - embeddings" some junto.
- Não feito: instalador `.exe` reconstruído (release é decisão humana) e medição de RSS com banco de 150 MB.
