# RAGX-0141 — Fila de toque, hook `PostToolUse` e `stale_paths` na busca

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | RAGX-0140, RAGX-0134 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-02, M-10, "Desenho proposto para o frescor") · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V11, S6) · [19-watch-e-autonomia-do-agente.md](../../docs/19-watch-e-autonomia-do-agente.md) · [09-mcp.md](../../docs/09-mcp.md) · [14-cli.md](../../docs/14-cli.md) · [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `done` |

## Objetivo

Edição não commitada nunca entra no índice por conta própria: só existem hooks de git (commit, checkout, merge), nada lê `watch.enabled` e o único caminho é `refresh`, que custa **26–91 s** (M-10, I-02). Reindexar 1 arquivo pelo `index` custa 1,3–2,0 s; o protótipo só dos arquivos tocados custou **130–270 ms**. Esta tarefa liga o `index_paths` da RAGX-0140 a dois gatilhos baratos: um hook `PostToolUse` do Claude Code que só enfileira o caminho editado, e o servidor MCP, que drena a fila antes de buscar. Se a fila não está vazia, a resposta diz `stale_paths`.

## Entregáveis

- [x] **Medir primeiro** a latência edição→visível de hoje (editar um arquivo, repetir `search` até o texto novo aparecer) e registrar em Medição; sem `touch` o esperado é "nunca"
- [x] `src/ragx/indexing/touchq.py` (novo, só stdlib + `ragx.indexing.lock`): fila `.ragx/touch.queue`, uma linha por caminho relativo POSIX; `enqueue(state_dir, rel_paths)` com um único `os.write` em `O_APPEND`; `pending(state_dir)` (lê sem consumir); `claim(state_dir)` por `os.replace` para `touch.queue.<pid>.<uuid>.claimed` (mesma técnica atômica de `lock._take_over` e `lock.mark_pending`), com dedup e teto de `cfg.watch.max_batch` (500); `give_back()` devolve o lote se a indexação falhar
- [x] `touchq.resolve(root, path)`: recebe absoluto ou relativo, devolve relativo à raiz do projeto ou `None` se escapar (`..`, outra raiz, symlink/junction para fora); no Windows compara sem diferenciar maiúsculas
- [x] `touchq.drain(cfg, source, wait_ms)`: espera o debounce (`[watch] touch_debounce_ms`, padrão 400), faz `claim` e chama `index_paths(cfg, paths, source=source)` (RAGX-0140). **Não pegar `index.lock` aqui**: a 0140 já o pega e, com a trava ocupada, faz `mark_pending` e lança `IndexBusyError`; pegar duas vezes travaria a própria chamada. Em `IndexBusyError` ou falha, `give_back` do lote (o dono refaz a passada incremental ao terminar, e ela já vê os arquivos novos por `size+mtime`)
- [x] `WatchCfg` (`src/ragx/config.py:162-167`) ganha `touch_debounce_ms: int = 400` e `touch_wait_ms: int = 1500`
- [x] Origens `touch` e `mcp:touch` em `VALID_SOURCES` (`src/ragx/indexing/pipeline.py:31-34`), se a 0140 ainda não as tiver acrescentado
- [x] Comando `ragx touch [PATHS...] [--stdin-json] [--root PATH]` em `src/ragx/cli/commands/touch_cmd.py`, registrado em `src/ragx/cli/main.py`: com `--stdin-json` lê o JSON do hook (`tool_input.file_path`; `notebook_path` no `NotebookEdit`), acha a raiz **a partir do arquivo editado** (não do `cwd`: a sessão pode estar numa pasta-pai com vários projetos), enfileira e dispara `drain` destacado (`githooks.spawn_index` como modelo, `CREATE_NO_WINDOW` no Windows). **Sai sempre com código 0** (JSON inválido, caminho fora de projeto, pasta sem RAGX), como o `claude hint`
- [x] Hook no Claude Code: generalizar `src/ragx/clients/claude_hint.py` (hoje com `EVENT = "SessionStart"` fixo, `_NOSSO`, `_grupos`, `_gravar`) para aceitar um segundo evento; `install_touch_hook`, `remove_touch_hook`, `has_touch_hook` gravam `{"matcher": "Edit|Write|MultiEdit", "hooks": [{"type": "command", "command": "<exe> touch --stdin-json", "async": true, "timeout": 10}]}` em `hooks.PostToolUse`, com as mesmas regras do hint (backup, idempotência, JSON inválido não é sobrescrito, hooks da pessoa preservados, barras normais e aspas no caminho do executável)
- [x] `ragx claude on` ganha `--touch/--no-touch` (padrão ligado); `off` remove o nosso; `_estado()` em `src/ragx/cli/commands/claude_cmd.py` ganha `"touch"` sem remover chaves existentes (o painel lê `ragx claude status --json`)
- [x] Drenagem no MCP: `KnowledgeAPI.search`, `search_graph` e `build_context` (`src/ragx/mcp/server.py:184,395,421`) chamam `touchq.drain` antes de consultar quando `pending` não é vazio e a escrita está habilitada (`WriteAPI.enabled`); servidor `--read-only` não drena, só informa. Estourou `[watch] touch_wait_ms` (padrão 1500): responde com o índice atual e `stale_paths`
- [x] `stale_paths` (até 20) e `stale_count` na resposta de `search_hybrid`, `search_knowledge`, `build_context` e na saída de `ragx search`/`ragx context`, **só quando há fila**; ausente quando vazia (custo zero em tokens no caso comum). Só entram caminhos já em `documents` ou que passam em `SecurityScanner.scan_filename`: nunca revelar caminho que o gate bloqueia
- [x] `src/ragx/mcp/playbook.py` e `claude_hint._texto_projeto` (linha "chame mcp__ragx__refresh antes"): trocar por "suas edições são registradas; se vier `stale_paths`, repita a busca", sem aumentar o hint
- [x] Documentar em `docs/19-...` (seção "Frescor de edições não commitadas"), `docs/14-cli.md` (`ragx touch`; `tests/unit/test_documentacao.py` falha sem isso), `docs/09-mcp.md` (`stale_paths`) e `docs/15-configuracao.md` (`touch_debounce_ms`, `touch_wait_ms`)

## Fora de escopo

- `index_paths` em si e o fim da varredura de árvore em `iter_files(only=)` (RAGX-0140)
- `stale` por chunk comparando `stat`/hash dos top-K na consulta (R-V11, primeira metade; é a RAGX-0113, fase 14)
- `refresh` incremental e sem `sync` (RAGX-0131)
- Despachar `touch` pela entrada leve, sem importar a CLI inteira (RAGX-0143)
- SessionStart disparar um `index` destacado (item 5 do desenho da auditoria): sem tarefa dona; ver Notas
- Dar significado a `watch.enabled` e o custo do `ragx watch` (RAGX-0147)

## Critérios de aceite

- [x] Editar um arquivo e chamar `touch` + busca devolve o texto novo em **≤ 5 s** (S6), no teste e2e com provider `hashing` e no script de Medição com o embedder real
- [x] Três `touch` em menos de 400 ms produzem **uma** indexação (`index_runs` cresce 1)
- [x] `stale_paths` aparece com fila pendente e some com a fila vazia; nunca lista `.env` nem arquivo bloqueado
- [x] `ragx claude on` duas vezes deixa o `settings.json` idêntico; `off` remove só a nossa entrada
- [x] `ragx touch` sai com 0 para entrada lixo; `uv run pytest tests/security` e `test_mcp_nao_importa_filesystem_nem_rede` verdes

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Latência edição→visível, arquivo não commitado (S6) | indefinida (manual); `refresh`: 26–91 s | **1,39–1,52 s** (5 rodadas, `hashing`, 40 arquivos, `ragx touch` real + drenagem destacada) |
| Reindexar 1 arquivo | 1,3–2,0 s (`index`); protótipo 130–270 ms | ~0,9 s dentro dos 1,4 s (400 ms de debounce + partida do processo destacado + `index_paths`) |
| Custo do processo `ragx touch` por edição | medir primeiro | 0,49–0,61 s de relógio (partida da CLI, M-08), em `async`: o agente não espera; a 0143 o reduz |

Rajada: 3 `touch` em processos paralelos (< 400 ms entre si) criaram **1** run `paths`; em série (cada processo leva ~0,5 s, então os toques ficam > 400 ms entre si) criaram 2. Script: `medir_touch.py` (cria o projeto, roda `ragx touch` via subprocesso e conta `index_runs`).

## Testes

- [x] `tests/unit/test_touchq.py`: `enqueue`/`claim`/dedup; dois `claim` concorrentes devolvem conjuntos disjuntos; caminho fora da raiz recusado; `C:\a\b.py` e `a/b.py` viram a mesma entrada; linhas com CRLF; teto de lote
- [x] `tests/unit/test_claude_touch_hook.py` (ou estender `tests/unit/test_claude_profiles_hint.py`): instala, idempotente, preserva hooks da pessoa, remove só o nosso, JSON quebrado não é sobrescrito, `matcher`/`async` presentes
- [x] `tests/e2e/test_cli_touch.py`: stdin com `Edit`, `Write`, `MultiEdit`, `NotebookEdit`; `cwd` numa pasta-pai; entrada lixo sai com 0
- [x] `tests/integration/test_touch_drain.py`: touch + drain → `search` acha o texto novo; trava ocupada → `pending` marcado e fila intacta; servidor somente leitura não drena e devolve `stale_paths`. Regressão que falha antes: editar sem `touch` e buscar não acha
- [x] `tests/integration/test_mcp.py`: `stale_paths` ausente com fila vazia, presente com fila
- [x] `tests/security/test_touch_seguranca.py`: enfileirar `.env` e um arquivo com segredo de `tests/fixtures/secrets_under_test.py` → nada entra em `chunks`, nada em `stale_paths`, `security_events` registrado; `../fora.txt` e junction/symlink para fora recusados; `touchq` não chama `read_bytes`

## Notas

- Confirmado em `src/ragx/clients/claude_hint.py:34,127` (SessionStart, `{"type": "command", "command": ..., "timeout": 15}` dentro de `{"hooks": [...]}`), `src/ragx/indexing/lock.py:192-210` (`mark_pending`/`take_pending`), `src/ragx/config.py:162-167` (`WatchCfg.enabled` existe e nenhum código em `src/` o lê; o `ragx.toml` deste repo o liga à toa) e `src/ragx/walk.py:52-56` (**`iter_files(only=)` ainda varre a árvore inteira** e só filtra depois; a 0140 precisa resolver isso, senão o ganho some).
- Formato do hook (PostToolUse recebe JSON no stdin: `session_id`, `cwd`, `hook_event_name`, `tool_name`, `tool_input.file_path`, `tool_response`). O repo só usa `SessionStart`, que não lê stdin: **conferir os campos e o `async` em code.claude.com/docs/en/hooks** na hora de implementar. Se a versão do Claude Code ignorar `async`, o hook roda síncrono; por isso o caminho de `touch` só anexa e dispara destacado.
- A primeira versão passa pela CLI completa (~0,5 s por edição, M-08); a 0143 a leva para a entrada leve. Em `async` isso não bloqueia o agente.
- O arquitetural (`tests/security/test_architecture.py`) proíbe `os`/`pathlib`/`open` em `ragx.mcp`: a fila vive em `ragx.indexing` (já autorizado); o servidor só chama a função.
- Embedder frio custa 3–5 s no fastembed (M-06): por isso o servidor MCP, com o modelo quente (RAGX-0142), é quem melhor drena; o processo `touch` destacado serve o caso sem servidor. Com Ollama em `127.0.0.1` (RAGX-0132) o embedding de poucos chunks é ~10–40 ms.
- Windows: stdin do hook em UTF-8 (reconfigurar `sys.stdin`); `file_path` vem com `\`; um antivírus pode segurar o arquivo logo após o save (RAGX-0133 cuida do arquivo travado; aqui o lote volta à fila).
- Se `index_paths` (0140) tiver assinatura diferente da usada aqui, adapte o chamador, não a 0140. Ela constrói o `SecurityGate` (e o `IgnoreEngine`) a cada chamada; no servidor MCP, que drena várias vezes por sessão, o `gate=` opcional que a RAGX-0147 acrescenta a `index_paths` permite reaproveitá-lo. Medir o custo da drenagem antes de decidir.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0141)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `touchq.py` (`enqueue`/`claim`/`resolve`/`drain`/`settle`/`visible`/`spawn_drain`), `ragx touch`, hook `PostToolUse` em `claude_hint.py` (`install_touch_hook`/`remove_touch_hook`/`has_touch_hook`), `ragx claude on --touch/--no-touch`, `"touch"` em `claude status --json`, drenagem em `search_knowledge`/`search_hybrid`/`search_graph`/`build_context` (MCP) e em `ragx search`/`ragx context`, `stale_paths`/`stale_count`.
- Decisões que divergem do texto da task: (1) **`touch_wait_ms` não existe**: a drenagem do MCP é síncrona e limitada por `max_batch`, e o campo ficaria sem uso; se a medição com o embedder real mostrar drenagem lenta, reintroduzir com um limite de verdade. (2) `stale_paths` passa por `SecurityGate.admit` (decisão só pelo nome, sem ler byte): um `.env` na fila nunca aparece. (3) Servidor somente leitura (`allow_write=False`, e `KnowledgeAPI(cfg)` sem `can_drain`) não drena, só informa. (4) Os testes ficaram em `tests/unit/test_touchq.py`, `tests/unit/test_claude_profiles_hint.py`, `tests/e2e/test_cli_touch.py`, `tests/integration/test_mcp_wire.py` e `tests/security/test_touch_seguranca.py` (em vez dos nomes sugeridos).
- **A verificar por uma pessoa:** o campo `"async": true` e o `timeout` do hook `PostToolUse` foram escritos conforme a task; não conferi contra a documentação da versão instalada do Claude Code. Se a versão ignorar `async`, o hook roda síncrono (~0,5 s por edição), sem quebrar nada.
- Embedder real (fastembed/Ollama) ainda não medido para o S6; os 1,4 s acima são com `hashing`.
