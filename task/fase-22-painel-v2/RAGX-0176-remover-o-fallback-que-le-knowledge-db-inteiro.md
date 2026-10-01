# RAGX-0176 — Remover o fallback que lê `knowledge.db` inteiro

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,25d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (U-06) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-P6) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `todo` |

## Objetivo

Quando um projeto não tem `.ragx/status.json`, o snapshot cai para `readProjectStats` (`src/app/electron/data/project-stats.ts:43`), que faz `fs.readFileSync` do `knowledge.db` **inteiro** para a memória e o abre no `sql.js` só para três `COUNT(*)`. Neste hub há bancos de até **150 MB**; a cada 5 s, por projeto sem `status.json`, isso seria um pico de memória do tamanho do banco (ou mais, com a cópia do WASM). Hoje o caminho não dispara porque os 12 projetos têm `status.json`, mas qualquer projeto indexado antes dele (ou com o arquivo apagado) ativa o problema. O `sql.js` ainda custa 24 MB em `node_modules`, 2,7 MB de `.wasm` desempacotado e uma inicialização no `app.whenReady()` que só existe para esse fallback.

## Entregáveis

- [ ] **Medir primeiro**: tamanho do `app.asar` (30,3 MB na beta.4) e quanto dele é `sql.js` (`npx asar list release/win-unpacked/resources/app.asar | grep sql.js`), tamanho do instalador (102,3 MB na beta.4), e a RAM do processo principal logo após o início com a linha de base da `RAGX-0177`; registrar em Andamento
- [ ] `electron/data/snapshot.ts`: remover `readStats` de `SnapshotDeps` (linha 17) e de `REAL_DEPS` (linha 47), e o ramo `else` que o chama (linhas ~136–153). Sem `status.json`, `counts` fica `null` e `countsUnavailableReason` explica: "Sem .ragx/status.json: reindexe este projeto (Atualizar agora) para o painel mostrar os números."; pasta sem `.ragx/knowledge.db` mantém o motivo "projeto ainda não foi indexado"
- [ ] `src/state.ts` (`deriveProjectState`, linha 13): `counts === null` sem `status.json` deixa de ser `error` ("Com problema", só "Ver detalhes") e passa a `stale` ("Defasado", ação "Atualizar agora", que enfileira `update` e gera o `status.json`); `error` fica para `lastError !== null`. Conferir `ProjectPage.tsx:78,117` e `ProjectsPage.tsx:266` ("sem dados") com o texto novo
- [ ] Apagar `electron/data/project-stats.ts` e `electron/data/__tests__/project-stats.test.ts`; remover `initSqlWasm` e o `import` em `electron/main.ts` (linhas 6 e 523–529), os tipos `ProjectStats`/`ProjectStatsUnavailable` de `electron/data/types.ts:19` quando ficarem sem uso, e `readStats` dos testes de `snapshot.test.ts` (casos b e b2 viram o caso "sem status.json")
- [ ] `npm uninstall sql.js @types/sql.js` em `src/app` (atualiza `package.json` e `package-lock.json`); remover o `asarUnpack` de `node_modules/sql.js/dist/*.wasm` e o comentário de `electron-builder.yml` (linhas 14–21)
- [ ] `src/app/README.md` ("De onde vêm os dados" e a lista de arquivos lidos): sai `.ragx/knowledge.db` e o "cai para contagens lidas direto"; entra a regra de que o painel **nunca** abre o banco

## Fora de escopo

- Gerar o `status.json` por outro caminho ou ler o banco por outro meio (o painel lê `status.json`, ponto)
- Mudar o conteúdo do `status.json` ou a CLI que o escreve (`src/ragx/indexing/status_file.py`)
- Pausar pollers (`RAGX-0171`), `git` sem spawn (`RAGX-0172`), telemetria (`RAGX-0174`)
- Reempacotar e publicar o instalador (release é decisão humana)

## Critérios de aceite

- [ ] `grep -rn "sql.js\|readProjectStats\|initSqlWasm" src/app --include=*.ts --include=*.tsx --include=*.yml --include=*.json` (fora de `node_modules` e `dist`) não encontra nada
- [ ] Projeto sem `status.json` aparece como "Defasado" com o botão "Atualizar agora" e o texto do motivo; clicar enfileira `update` (teste de renderização)
- [ ] Nenhuma leitura de `knowledge.db` pelo painel: o snapshot de um projeto com banco de 150 MB sem `status.json` não aloca o arquivo (medido por RSS do processo principal antes/depois, ou por teste que falha se `readFileSync` tocar `knowledge.db`)
- [ ] `npm run build`/`npm run package` seguem funcionando (o `electron-builder` não referencia mais o `sql.js`); o `app.asar` encolhe o medido na linha de base

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| `app.asar` | 30,3 MB (beta.4) | (medir) |
| Instalador | 102,3 MB (beta.4) | (medir; só se houver empacotamento local) |
| Pico de RSS com projeto de 150 MB sem `status.json` | (medir) | sem pico |
| Dependências de runtime do painel | `react`, `react-dom`, `sql.js` | `react`, `react-dom` |

Comando: `npx asar list release/win-unpacked/resources/app.asar | grep -c sql.js` e `node scripts/measure-runtime.mjs --plan visible:2` (da `RAGX-0177`, em `src/app`)

## Testes

- [ ] `electron/data/__tests__/snapshot.test.ts`: sem `status.json` devolve `counts: null`, `hasStatusFile: false` e o motivo novo; com `status.json` nada muda; pasta ausente e `.ragx` ausente mantêm os motivos
- [ ] `src/__tests__/state.test.ts`: `deriveProjectState` devolve `stale` para `counts: null` sem `status.json` e `error` para `lastError`
- [ ] `src/pages/__tests__/ProjectsPage.test.tsx` e `ProjectPage.test.tsx`: o card e o detalhe mostram o motivo e a ação "Atualizar agora"
- [ ] `electron/__tests__/ipc.test.ts` e demais testes do painel verdes sem `sql.js` instalado

## Notas

Risco aceito: projeto indexado por uma versão antiga do RAGX, sem `status.json`, passa a mostrar "Defasado" até a próxima indexação em vez de mostrar números aproximados; a ação de um clique resolve. O `pendingEmbeddings` aproximado (`chunks - embeddings`) some junto com o fallback. Se houver teste que dependa de `sql.js` como fixture (`project-stats.test.ts` importa `sql.js` para montar o banco), ele sai com o arquivo. Confirmar que nenhum script de `scripts/` (`prepare-bundle.mjs`, `after-pack.cjs`) cita `sql.js` antes de apagar a dependência.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização)
- [ ] Commit `tipo(escopo): descrição (RAGX-0176)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
