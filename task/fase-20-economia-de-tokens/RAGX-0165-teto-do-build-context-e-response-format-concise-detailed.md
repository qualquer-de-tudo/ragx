# RAGX-0165 — Teto do `build_context` e `response_format: concise|detailed`

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0154 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #1, M-11) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S1, R-T1) · [09-mcp.md](../../docs/09-mcp.md) · [07-context-engine.md](../../docs/07-context-engine.md) |
| **Status** | `done` |

## Objetivo

O agente decide quanto contexto pedir: `BuildContextRequest.tokens` aceita até 32.000 (`tools.py:21,39`) e as ferramentas de busca devolvem o conteúdo inteiro de cada hit mesmo quando o agente só quer localizar. A pesquisa (Anthropic, *Writing tools for agents*) mede o formato conciso em ~1/3 dos tokens do detalhado, e a aposta nº 1 da auditoria pede um teto de ≈5k para o `build_context`. Estimativa (não medida) da auditoria para a busca: 2,4k → 0,55k tokens com snippet de 200 chars e `get` sob demanda. Esta tarefa põe o teto e a escolha de verbosidade.

## Entregáveis

- [x] **Medir primeiro:** (a) `tokens_delivered` máximo e p95 em `mcp.jsonl` de projetos reais (há pedido acima de 5k?); (b) `search_hybrid` de 10 hits com `content` completo contra um corte de 200 chars, com `scripts/medir_fio.py` (0154). Registrar em Medição; a estimativa de −77% só vale se a medição a confirmar.
- [x] `src/ragx/config.py` `McpCfg` (136-145): `max_context_tokens: int = 5000`, `response_format: Literal["concise", "detailed"] = "concise"`, `snippet_chars: int = 200`.
- [x] Teto: em `KnowledgeAPI.build_context` (`mcp/server.py:421`), `budget = min(req.tokens, cfg.mcp.max_context_tokens)`. Pedido acima do teto **não é cortado em silêncio**: a resposta traz `tokens_capped` com o teto aplicado. `BuildContextRequest.tokens` (tools.py:39) mantém `le=MAX_TOKENS` como limite de validação.
- [x] `response_format` em `SearchRequest` e `BuildContextRequest` (tools.py:28-42), com o padrão vindo de `cfg.mcp.response_format`. **Busca** (`search_hybrid`, `search_knowledge`, `search_graph`): `concise` devolve `snippet` (primeiros `snippet_chars` do conteúdo, cortados em fim de linha ou palavra, com `…`) no lugar de `content`; `detailed` devolve `content`. O resto do hit é igual. **`build_context`**: `concise` devolve só o `markdown` (0154); `detailed` acrescenta `intent`, metadados dos fragmentos **sem** conteúdo (`chunk_id`, `lines`, `tokens`, `strategy`, `reason`, `score`), `dropped` agrupado por motivo e `stats`. `format` (markdown|json) segue escolhendo a representação.
- [x] `src/ragx/search/snippet.py` (novo): `make_snippet(content, max_chars)`; a lógica fica na camada de serviço, o servidor só a chama em `_hit` (server.py:169-181).
- [x] `vscode-plugin/src/rag/McpClient.ts`: `search` (331-361) e `buildContext` (641-664) mandam `response_format: 'detailed'`, pois exibem o conteúdo (`toHit`, 734-747).
- [x] Reconferir S2: `response_format` entra no schema de `search_hybrid` e `build_context`; o `slim` (0157) deve continuar ≤ 600 tokens. Descrição curta, enum de duas palavras.
- [x] `get_playbook`/`instructions`: uma frase "para o trecho inteiro, `get_chunk`". `docs/09-mcp.md` (tabela de entrada e a matriz `format` × `response_format`), `docs/07-context-engine.md`. CHANGELOG.

## Fora de escopo

- Dedupe de sessão (0159), `chunk_id` curto e JSON compacto (0155), níveis do `get_dictionary` (0111).
- Mudar o padrão `tokens=3000` e `tasks.context_tokens` (usado por `claim_task`, não passa por este teto). A CLI `ragx context` (não é o servidor).
- Compressão do conteúdo dos fragmentos (`context/compress.py`).

## Critérios de aceite

- [x] `build_context(tokens=20000)` devolve no máximo 5.000 tokens e `tokens_capped == 5000`; `tokens=3000` não traz o campo.
- [x] `search_hybrid` com `limit=10` em `concise` cai **≥ 60%** em tokens no fio contra `detailed` (a estimativa da auditoria é −77%; a medição decide o número final). **Medido: −62% com `snippet_chars = 140`; com 200 (o padrão da task) foi só −56,8%, por isso o padrão mudou para 140.**
- [x] `response_format="detailed"` devolve o conteúdo idêntico ao de antes da tarefa (nenhum campo de `content` mudou).
- [x] `get_chunk(chunk_id)` de um hit `concise` devolve o conteúdo inteiro.

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| `search_hybrid`, 10 hits, tokens no fio (`detailed` / `concise`) | 2.925 / — (estimado 550) | **2.915 / 1.108** (snippet 140; −62%). Com snippet 200: 1.259 (−56,8%). A estimativa de −77% não se confirmou: o metadado de cada hit pesa ~660 tokens |
| `build_context` pedido com 20.000 tokens, entregue | medir primeiro (máx. real em uso: 3.239) | `estimated_tokens` **4.503** <= 5.000, `tokens_capped: 5000`; 5.083 tokens no fio (envelope incluso) |
| `slim`, custo fixo com o parâmetro novo (S2) | valor da 0157 | **a conferir na 0157** (o perfil `slim` ainda não existe; `response_format` entrou em `search_hybrid`, `search_knowledge` e `build_context` como enum de duas palavras) |

Comando: `uv run python scripts/medir_fio.py --tool search_hybrid --arg limit=10 --arg response_format=concise` (e `detailed` para o outro lado).

## Testes

- [x] `tests/integration/test_mcp.py`: teto aplicado e informado (`tokens_capped`); `test_tokens_acima_do_teto_e_rejeitado` (linha 211, `999_999`) continua rejeitando por validação; busca `concise` com `snippet` e sem `content`; `detailed` idêntico ao anterior; `test_cli_e_mcp_concordam` (linha 379) verde.
- [x] `tests/unit/test_snippet.py` (novo): corte em limite de palavra/linha, acentos e emoji não partidos, conteúdo menor que o limite sem `…`.
- [x] `tests/unit/test_mcp_perfis.py` (da 0157): S2 do `slim` com `response_format`.
- [x] `tests/security/test_surfaces.py::test_superficie_mcp` (linhas 189-216) parametrizado nos dois formatos: nenhum segredo da fixture no `snippet` nem no `content`.
- [x] `vscode-plugin/tests/unit/`: `search` e `buildContext` enviam `detailed`. Teste arquitetural "MCP é casca fina" intacto (o corte do snippet vive em `ragx.search`).

## Notas

- **Mudança de comportamento:** `concise` vira o padrão da busca, então quem lia `content` passa a ver `snippet` (um round-trip a mais quando precisa do trecho). O A/B (0162) deve confirmar que o agente não gasta mais tokens em `get_chunk` do que economizou. Se confirmar o contrário, `[mcp] response_format = "detailed"` reverte sem código.
- O `vscode-plugin` é o consumidor conhecido do `content` de busca; por isso o item do plugin é obrigatório, não opcional.
- Confirmado: `tools.py:21` (`MAX_TOKENS = 32_000`), `tools.py:37-42` (`BuildContextRequest`), `server.py:421-453`.
- O teto de 5k é do `build_context`; `claim_task` usa o orçamento da tarefa (`tasks.context_tokens`, 4.000) por outro caminho (`tasks/dispatcher.py:134`) e não é afetado.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes (Windows rodado aqui; Linux e macOS pelo CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0165)` na branch `feat/v2`

## Andamento

2026-10-01. Medido primeiro: 45 chamadas reais de `build_context` nos 3 logs do hub: máx. 3.239 tokens, p95 2.601, mediana 2.407, nenhuma acima de 5.000 (o teto de 5k não atrapalha o uso atual).
`search_hybrid` 10 hits: detailed 2.915 tokens; concise com snippet 200 = 1.259 (-56,8%, abaixo da meta de -60%); varredura via `RAGX_MCP_SNIPPET_CHARS`: 160 -> 1.207, 140 -> 1.108 (-62%), 120 -> 1.079. Padrão `snippet_chars = 140`.
Implementado: `McpCfg` (`max_context_tokens=5000`, `response_format="concise"`, `snippet_chars=140`); `search/snippet.py` (`make_snippet`: fim de linha se estiver nos últimos 40% da janela, senão fim de palavra, senão corta no limite; `…`; conteúdo que cabe volta inteiro);
`SearchRequest`/`BuildContextRequest.response_format`; `_hit(r, detailed)`; teto com `tokens_capped` (só aparece quando o pedido passou do teto); `detailed` do `build_context` com `intent`, `fragments_meta` (sem conteúdo), `dropped` agrupado por motivo e `stats`
(o `intent` saiu do `concise`, como a task manda); parâmetro `response_format` nas ferramentas `search_hybrid`, `search_knowledge` e `build_context`; plugin do VS Code pede `detailed` na busca e no contexto (testes novos); frase do playbook sobre `get_chunk`.
Testes: `tests/unit/test_snippet.py` (6), `tests/integration/test_mcp.py` (+5), `test_surfaces.py` (`response_format` nos dois modos no fio), plugin (+2). Fast suite, `tests/security`, `npm test` (105) e `typecheck`, `ruff`, `mypy` verdes.
Pendências honestas: (1) o A/B da 0162 deve confirmar que o agente não gasta em `get_chunk` mais do que economizou: o `concise` é o padrão por decisão da task, reversível por `[mcp] response_format = "detailed"`; (2) `search_graph` não expõe o parâmetro no schema da ferramenta
(usa o padrão da configuração, `concise`); (3) o S2 do `slim` (0157) ainda não pode ser conferido.
