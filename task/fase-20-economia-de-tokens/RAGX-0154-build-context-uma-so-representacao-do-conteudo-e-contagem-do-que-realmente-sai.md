# RAGX-0154 — `build_context`: uma só representação do conteúdo e contagem do que realmente sai

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (C-01, M-03) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S1, R-T1) · [07-context-engine.md](../../docs/07-context-engine.md) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `todo` |

## Objetivo

Um `build_context` pedido com 3.000 tokens entrega **7.684 tokens no fio** (2,6×; 26.735 chars contra 2.401 declarados em M-03). O conteúdo sai duas vezes (`fragments[].content` e `markdown`), e `estimated_tokens` conta só o `content`, ignorando cabeçalhos (~33 tokens cada, contra os 12 que `allocate` assume). A economia que o painel mostra está superestimada porque o "entregue" é o número declarado, não o que saiu. Esta tarefa faz o orçamento, o `estimated_tokens` e a resposta falarem do **mesmo texto**.

## Entregáveis

- [ ] **Medir primeiro:** criar `scripts/medir_fio.py` (reutilizado por 0155, 0157 e 0165). Sobe `build_server(cfg)` em processo e, com `--tool <nome> [--tokens N] [--query ...] [--arg chave=valor ...]` (ou `--tool tools_list`), chama a ferramenta por `call_tool` e imprime chars e tokens do texto que o cliente recebe (heurístico e, se instalado, tiktoken). Registrar o "Antes" em Medição.
- [ ] `src/ragx/context/engine.py`: `ContextFragment` (linhas 37-50) ganha `chunk_id: str = ""`, preenchido em `_to_fragments` (220-261). Necessário para o dedupe (0159) e para o `vscode-plugin`, que hoje recebe `chunkId` vazio. `_cache_read`/`_cache_write` (349-394) seguem compatíveis por causa do padrão.
- [ ] `src/ragx/context/render.py`: extrair `fragment_header(...)` (hoje inline em `_markdown`, linhas 24-34) e `rendered_tokens(pack)`; `render(pack, "markdown", title=True)` ganha `title`. O título `# Contexto — <consulta>` só a CLI imprime; o MCP usa `title=False` (o agente já sabe a consulta, que pode ter 2.000 chars).
- [ ] `src/ragx/context/budget.py`: em `allocate` (linha 32), trocar `per_fragment_overhead=12` (linha 37) pelo custo real `count_tokens(cabeçalho)` de cada candidato (derivável de `SearchResult`: caminho, linhas, `heading_path`/`symbol`), mais o custo do rodapé.
- [ ] `engine.build_context`: o laço de garantia (linhas 151-157) e `pack.estimated_tokens` (linha 160) passam a medir o markdown completo (`rendered_tokens`). Gravar `stats["content_tokens"]` e `stats["overhead_tokens"]` à parte.
- [ ] `src/ragx/mcp/server.py` `KnowledgeAPI.build_context` (421-453): **uma** representação. `format="markdown"` (padrão) devolve `{project, intent, estimated_tokens, budget, sources, markdown}`, sem `fragments`. `format="json"` devolve `fragments` (com `chunk_id`, `tokens`, `content`) e **não** `markdown`.
- [ ] `render._json` (render.py:73-88) passa a incluir `chunk_id` por fragmento.
- [ ] `vscode-plugin/src/rag/McpClient.ts` `buildContext` (641-664): pedir `format: 'json'`, pois lê `fragments`. `CliClient.ts` já usa `--format json`.
- [ ] `engine._cache_key` (318-330): incluir uma constante `_CACHE_SCHEMA = 2` no fingerprint, para não servir pack com a contagem antiga. A chave completa é da 0135; aqui só o bump.
- [ ] Docs: `docs/07-context-engine.md` (contrato `ContextFragment.chunk_id`; "`estimated_tokens` conta o que sai"), `docs/09-mcp.md` (linha de `build_context`: uma representação por `format`). CHANGELOG com antes/depois.

## Fora de escopo

- JSON compacto, `outputSchema` e `structuredContent` (0155).
- `ok`/`err_code`/`resp_chars` e mover `baseline_tokens` do payload para o log (0156; ele continua no payload, ~8 tokens, até lá).
- Teto de 5k e `response_format` (0165). Dedupe de sessão (0159).
- Chave do cache com filtros e versão confiável (0135). Trocar o contador de tokens.

## Critérios de aceite

- [ ] `estimated_tokens` == `count_tokens(markdown devolvido)` e ≤ `budget`, em 500, 1.000 e 3.000.
- [ ] S1: tokens no fio de `build_context(tokens=3000)` **≤ 3.200** (`uv run python scripts/medir_fio.py --tool build_context --tokens 3000`; com `indent=2` ainda vigente, a confirmação final de S1 é após a 0155).
- [ ] Nenhuma resposta MCP de `build_context` carrega conteúdo em dois lugares.
- [ ] `ragx context` (CLI) continua imprimindo o título e o rodapé como hoje.

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Tokens no fio, `build_context` com `tokens=3000` (S1) | 7.684 (C-01) | |
| Chars no fio (mesmo pedido) | 26.735 (M-03) | |
| `estimated_tokens` declarado | 2.401 (M-03) | |
| Cabeçalho de fragmento, tokens (real / assumido) | ~33 / 12 | |

## Testes

- [ ] `tests/integration/test_context.py::test_estimated_tokens_conta_o_que_sai` (parametrizado em 500/1000/3000, usa a fixture `proj`): recontar o markdown renderizado e comparar. **Falha antes do conserto** (hoje `estimated_tokens` ignora cabeçalhos).
- [ ] `tests/unit/test_context_units.py`: `allocate` com caminhos longos seleciona menos fragmentos do que com caminhos curtos, mesmo orçamento.
- [ ] `tests/integration/test_mcp.py`: `test_build_context_uma_representacao` (`format="markdown"` sem `fragments`; `format="json"` sem `markdown`). Ajustar `test_build_context_respeita_orcamento` (linhas 189-195), que hoje itera `fragments`.
- [ ] `tests/security/test_surfaces.py::test_superficie_mcp` continua verde sem alteração. O invariante "MCP é casca fina" (`tests/security/test_architecture.py`) segue intacto: nenhum `os`/`open` novo em `src/ragx/mcp`.
- [ ] `vscode-plugin/tests/unit/`: teste de `McpClient.buildContext` com resposta `format: json` simulada (`npm test` e `npm run typecheck` em `vscode-plugin/`).

## Notas

- Confirmado em `mcp/server.py:431-453` (fragments e markdown juntos), `engine.py:151,160` (`estimated_tokens` = soma de `f.tokens`), `budget.py:37` (overhead 12).
- Os dois números da auditoria (7.684 tokens e 26.735 chars) são medidas diferentes do mesmo pedido; registrar ambos e dizer qual contador usou. A auditoria mediu tokens de ferramenta com `chars/4` (sem `tiktoken`); o `.venv` do repo tem `tiktoken` (cl100k) e `count_tokens` o usa. Rodar o script com os dois contadores e registrar qual produziu cada número.
- Armadilha: `vscode-plugin` hoje manda `format: 'markdown'` e lê `fragments`; sem o ajuste do `McpClient.ts`, o Context Builder do VS Code fica vazio. O `get_playbook` e os perfis em `agents/` falam de `build_context` sem citar o formato: nada a mudar.
- `claim_task` (`tasks/dispatcher.py:134-141`) monta o próprio markdown a partir de `pack.fragments`; não é afetado.
- Se o markdown sozinho já passar de 3.200 no corpus, o culpado é a margem do `allocate`, não o JSON: ajustar `SAFETY_MARGIN` (budget.py:20) e registrar.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0154)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
