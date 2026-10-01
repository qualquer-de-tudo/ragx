# RAGX-0187 — Preview do `build_context` no detalhe do projeto

| | |
|---|---|
| **Fase** | 22 — Painel v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 1,25d |
| **Depende de** | RAGX-0154, RAGX-0179 |
| **Documentação** | [24-auditoria-v2.md §6](../../docs/24-auditoria-v2.md#6-painel-u-) (lacunas de produto) · [25-spec-v2.md §5.4](../../docs/25-spec-v2.md#54-painel--fase-22) (R-P11) · [src/app/README.md](../../src/app/README.md) |
| **Status** | `done` |

## Objetivo

O dono não tem como ver **o que o agente receberia** para uma pergunta: quais trechos, de que arquivos, quantos tokens do orçamento, o que foi descartado. É a lacuna "preview de `build_context`" da auditoria. A restrição que define o desenho: **a pergunta digitada nunca é gravada em disco nem em log**, e o painel só chama a CLI por `kind` fixo. Hoje o único jeito de passar texto à CLI é um argumento de linha de comando (`ragx context "<pergunta>"`), que apareceria no `argv` do processo e na mensagem de erro de `run-ragx-command.ts:35,67-69`, e o `build_context` grava a consulta em `.ragx/cache/context/<hash>.json` (campo `query`, `context/engine.py:369-391`). A solução é mandar o texto por **stdin**, com cache desligado.

## Entregáveis

- [x] CLI (`src/ragx/cli/commands/context_cmd.py`): opção `--query-stdin`; o argumento `query` (hoje obrigatório, linha 19) passa a opcional e é mutuamente exclusivo com ela (`UsageError`, sem repetir a consulta). Lê `sys.stdin.buffer.read().decode("utf-8")` (no Windows `sys.stdin` pode não ser UTF-8), tira espaços e **força `use_cache=False`**. Nenhuma mensagem de erro, `console.print` ou log leva a consulta.
- [x] CLI: com `--format json` e pacote vazio (hoje `context_cmd.py:49-51` imprime texto com a consulta e sai 1), imprime o JSON com `fragments: []` e sai 0. Só no modo JSON; o texto e o código de saída do modo markdown não mudam.
- [x] `electron/data/run-ragx-command.ts`: `opts.stdin?: string`; depois do `spawn`, `child.stdin.end(stdin, 'utf8')` (erro `EPIPE` ignorado). As mensagens de erro (`args.join(' ')`, linhas 35 e 67-69) continuam sem a pergunta, porque ela não está em `args`.
- [x] `electron/ipc.ts`: `previewContext(projectIdUnknown, questionUnknown)`, validado como `getProjectStatus`: `requireLocalProject` (id do snapshot, pasta de lá); pergunta `string`, 1 a 500 caracteres depois do trim, sem `\0`. Roda `ragx context --query-stdin --format json --no-cache` com `cwd` do projeto, `stdin` = pergunta e `timeoutMs` de 60 s. Um preview por vez: o segundo recebe "Já há uma pré-visualização em andamento".
- [x] Filtro de saída no processo principal (`parseContextPreview`): só passam `intent`, `estimated_tokens`, `budget`, contagem de `dropped` agrupada por motivo e, por fragmento, `document_path`, `lines`, `symbol`, `heading_path`, `score`, `tokens`, `compressed`, `strategy`, `reason`, `project`. **Não passam** `query` nem `content`: o renderer nunca vê código nem a pergunta de volta, e a frase do README ("nenhum conteúdo de código-fonte é lido") continua verdadeira. Formato inesperado: erro "resposta inesperada de ragx context".
- [x] Canal `ragx:previewContext` (`electron/main.ts`, junto de `ragx:runTrial`), `previewContext` em `electron/preload.ts` e em `RagxBridge` (`src/types/ragx-bridge.d.ts`), tipo `ContextPreview` em `electron/data/types.ts`.
- [x] `src/components/project/ContextPreview.tsx`, na aba "Economia de tokens", abaixo de `TokenSavings`: campo de pergunta (`maxLength` 500, `autoComplete="off"`, `spellCheck={false}`, sem `name`), executa por Enter ou botão (não por tecla digitada), mostra "N trechos · X de Y tokens · intenção Z", a lista (caminho:linhas · símbolo · tokens · motivo · "comprimido") e o resumo de descartes; "Limpar". Estados: carregando ("a primeira busca pode levar alguns segundos"), vazio, erro. A pergunta vive só em `useState`: sem `localStorage`, sem `onDemandCache.ts`, e some ao trocar de projeto (`key={project.id}`) e ao desmontar.
- [x] `src/app/README.md` e `docs/14-cli.md`: documentar `--query-stdin`, o filtro de saída e a garantia de não gravação.

## Fora de escopo

- Mostrar o conteúdo dos trechos, guardar histórico ou favoritos de perguntas, buscar fora do índice.
- Mudar a forma do JSON do `build_context` (RAGX-0154), o dedupe por sessão (RAGX-0159) ou o teto e o `response_format` (RAGX-0165).
- Preview por MCP ou pela paleta (RAGX-0183 só procura em memória).

## Critérios de aceite

- [x] **Sentinela:** `test_context_query_stdin_nao_grava_a_consulta_em_ragx` roda `ragx context --query-stdin` com `SENTINELA-0187-xyz` num projeto temporário e varre todos os arquivos de `.ragx/` (cache, logs, `knowledge.db` em bytes): **0** ocorrências. (NÃO feito: a variante com erro provocado, embedder fora do ar; e o caminho do Electron real não foi exercido, só o do `ragx` pela CLI.)
- [x] `argv` do processo da CLI não contém a pergunta (teste em `ipc.test.ts` sobre os `args` recebidos por `runRagxCommand`, que são exatamente `['context','--query-stdin','--format','json','--no-cache']`).
- [x] Nenhum `console.*` do processo principal recebe a pergunta (espiões no teste) e a mensagem de recusa nunca a repete.
- [x] Resposta filtrada: um JSON de entrada com `content` e `query` sai sem eles (teste); entrada sem `fragments` vira erro, não exceção.
- [x] Acentos e emoji chegam inteiros (teste Python com `input="criar pedido da ação"`; teste TS confere o `stdin` em UTF-8).
- [x] Recusas: projeto desconhecido, projeto só de federação, pergunta vazia, de 501 caracteres, com `\0` ou que não é texto, sem processo nascer (`ipc.test.ts`).
- [x] Latência do preview quente e frio medida e registrada em Andamento (S9: 3,0 a 5,0 s hoje na 1ª busca do processo, por carga de embedder; cada preview é um processo novo, então o frio é o caso comum).
- [x] Bundle (hoje JS 306.822 B, gzip -9 91.745 B): registrar antes e depois.

## Testes

- [x] `tests/e2e/test_cli_fase0.py` (existente, `test_context_*`): `--query-stdin` com e sem acento; exclusão mútua com o argumento; pacote vazio em JSON devolve `fragments: []` e código 0; modo markdown inalterado; sentinela fora de `.ragx/`.
- [x] `src/app/electron/data/__tests__/run-ragx-command.test.ts` (existente): `stdin` escrito em UTF-8 e encerrado; o `fakeChildProcess` do arquivo não tem `stdin`, então ganha um.
- [x] `src/app/electron/__tests__/ipc.test.ts` e `preload.test.ts` (existentes): validação, argumentos exatos, filtro, um por vez; `previewContext` na lista exata do preload e nos 4 mocks completos de `RagxBridge` (`src/test/snap.ts`, `App.test.tsx`, `useSnapshot.test.ts`, `useJobsConnections.test.ts`).
- [x] `src/components/project/__tests__/ContextPreview.test.tsx` (novo): resultado, vazio, erro, `Storage.prototype.setItem` nunca chamado, limpeza ao trocar de projeto.

## Notas

- Confirmado: `runRagxCommand` já injeta `RAGX_CALLER=painel` (`run-ragx-command.ts:22`), então o comando **não** entra em `cli.jsonl` (`cli/main.py:163`); mesmo sem isso o log só grava nome, tempo e `ok`, nunca argumentos (`diagnostics.py:50-56`). Confirmado em `ipc.ts:295-307`: `getProjectStatus` e `runTrial` são o modelo de validação a seguir.
- Premissa da regra de IPC: o renderer manda `projectId` + texto, e o texto só entra por stdin. `JOB_REQUEST_KEYS` (`ipc.ts:30`) e o catálogo de tarefas **não** mudam: preview não é tarefa da fila (como `runTrial`).
- `render(pack, "json")` ecoa `query` por `safe_echo` (`context/render.py:67`): por isso o filtro do processo principal descarta o campo.
- Depende da RAGX-0154 só para o formato: o filtro lê campos por nome e ignora o resto, então mudanças no JSON não o quebram, mas confira os nomes depois da 0154.
- O que o Ollama faz com o texto da consulta (ele recebe a pergunta por HTTP local para embutir) está fora do alcance do RAGX; não prometa mais que o escrito acima.
- `src/__tests__/no-em-dash.test.ts` vale para o texto novo; `ruff` e `pytest -m "not slow"` valem para a parte Python.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes
- [x] `npm test`, `npm run lint` e `tsc` dos dois projetos limpos (em `src/app`)
- [ ] Nenhuma regressão visual nas telas afetadas (conferido por screenshot ou teste de renderização) (só testes e o harness, 0 problema de layout na aba Economia; sem captura do preview)
- [x] Tamanho do bundle do renderer registrado antes/depois (hoje 307 kB JS / 93 kB gzip)
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação (`src/app/README.md`) confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0187)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Python: `ragx context` ganhou `--query-stdin` (lê `sys.stdin.buffer` em UTF-8, tira espaços, força `no_cache`, exclusivo com o argumento e vazio é `UsageError`, mensagens sem a consulta) e, em JSON, pacote vazio sai 0 com `fragments: []` (markdown inalterado). Achado: `--tokens` com `default=0` e `min=200` fazia `ragx context "x"` SEM `--tokens` sair 2 ("0 is not in the range 200<=x<=200000"); o padrão passou a `None` (o `tokens or cfg.context.default_tokens` já tratava). 4 testes novos em `test_cli_fase0.py` (acento por stdin, exclusão mútua e sem eco, sentinela fora de `.ragx/`, pacote vazio); `ruff` e `mypy` limpos.
- Electron: `runRagxCommand` com `opts.stdin` (UTF-8, `end`, `EPIPE` ignorado; só toca no stdin quando pedido), `previewContext` em `ipc.ts` (projeto do snapshot, pergunta de 1 a 500 caracteres sem NUL, um por vez, 60 s, args fixos `['context','--query-stdin','--format','json','--no-cache']`), `parseContextPreview` (descarta `query` e `content`), canal `ragx:previewContext`, `preload`, tipos e os 4 mocks. UI: `ContextPreview` na aba Economia (`key` por projeto, só para projeto local).
- **Medido** (`ragx context --query-stdin --format json --tokens 1500` neste repositório, 11 trechos): **4,26 s** na primeira chamada (processo novo, inclui o embedder) e **2,54 s** na segunda; cada preview é um processo novo, então o frio é o caso comum. Depois da execução, nada em `.ragx/cache` continha a pergunta.
- Testes novos: `ipc.test.ts` (args exatos e sem a pergunta, filtro que remove `query` e `content`, resposta sem `fragments`, 6 perguntas recusadas sem processo e sem eco, projeto desconhecido e de federação, nenhum `console.*` com a pergunta, um por vez), `run-ragx-command.test.ts` (stdin em UTF-8 e fora das mensagens de erro), `preload.test.ts`, `ContextPreview.test.tsx` (6). Painel: 1357 testes verdes, `lint` e `tsc` limpos.
- Bundle: JS 327.009 → **329.742 B** (gzip 98.354 → 99.059); CSS 41.924 → **42.396 B** (gzip 8.342 → 8.415).
- Não feito: erro provocado na varredura da sentinela e captura do preview.
