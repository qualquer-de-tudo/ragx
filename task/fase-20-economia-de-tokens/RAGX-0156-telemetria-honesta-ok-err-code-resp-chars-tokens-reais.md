# RAGX-0156 — Telemetria honesta: `ok`, `err_code`, `resp_chars`, tokens reais

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0154 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-12, M-03) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-T6, S13) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `todo` |

## Objetivo

A telemetria do servidor não deixa medir erro nem consumo: a linha de `mcp.jsonl` não tem `ok`, `err_code` nem tamanho da resposta. Uma chamada que devolve `ok: false` (`not_found`, `rate_limited`) é gravada como sucesso, e as que falham gravam sem resultado. Medido na auditoria: 22 registros no total, 11 sem `session`, p50/p95 por ferramenta com amostra de 1 a 8. A taxa de erro não é calculável e `tokens_delivered` é o número declarado, não o que saiu.

## Entregáveis

- [ ] **Medir primeiro:** (a) `ragx perf --json` e a contagem de linhas de `.ragx/logs/mcp.jsonl` sem `session` hoje; (b) o custo, em ms, de `count_tokens` sobre uma resposta de ~30 KB (`src/ragx/tokens.py:69`). Se passar de 10 ms, registrar só `resp_chars` e `resp_tokens` estimado por `chars/4`, rotulado.
- [ ] `src/ragx/diagnostics.py`: `mcp_entry(tool, ms, project, result, text)` monta a linha (a lógica fica aqui, fora de `ragx.mcp`). Campos novos: `v: 2`, `ok`, `err_code` (só quando `ok` é falso; vem de `result["error"]["code"]`), `resp_chars`, `resp_tokens`, `proc` (8 hex por processo do servidor, sempre presente: agrupa quando `session` não existe). Nunca a consulta nem a mensagem de erro, que pode ecoar o argumento.
- [ ] `src/ragx/mcp/server.py` `_guarded` (53-98) e `_log_call` (101-128): passar o resultado em **todos** os caminhos. Hoje `ValidationError` e exceção chamam `_log_call(..., None)` (linhas 77 e 93) e `ok: false` devolvido normalmente é gravado como sucesso.
- [ ] Gravar depois de serializar: o registro usa o texto exato que o cliente recebe (`dump` da 0155; se a 0155 não estiver `done`, `json.dumps` compacto do envelope). `resp_chars = len(texto)`.
- [ ] `tokens_delivered` de `build_context` = `estimated_tokens` da 0154 (tokens do markdown entregue); documentar que `resp_tokens` é a resposta inteira e `tokens_delivered` só o conteúdo.
- [ ] `src/ragx/perf.py` `server_stats` (197-212): contar `n`, `errors` e `error_rate` por ferramenta, tratando linha antiga (sem `ok`) como "desconhecida", não como erro. `src/ragx/cli/commands/perf_cmd.py`: coluna `erros` na tabela e os campos no `--json`.
- [ ] Painel (só o parser, sem tela nova): `src/app/electron/data/telemetry.ts` (`LogLine`, linhas 5-12) e `activity.ts` (`parseLine`, 58-94) leem `err_code`, `resp_chars`, `resp_tokens`; `ActivityEvent` (`types.ts:52-70`) ganha `errCode`, `respChars`, `respTokens`. A tela é da 0188/0190.
- [ ] `docs/09-mcp.md`, seção Observabilidade (linhas 284-312): linha de exemplo nova e a definição de cada campo. CHANGELOG.

## Fora de escopo

- Baseline honesto do gráfico de economia e do `ragx trial` (0163).
- Qualquer tela nova do painel: linha do tempo de sessões (0188), adoção (0190). Rotação e leitura incremental dos logs (0174).
- Registrar a consulta ou os argumentos (proibido, por desenho: `McpCfg.log_queries` fica `False`).
- Contar tokens com o tokenizer do Claude (não existe localmente; o contador é estimativa declarada).

## Critérios de aceite

- [ ] Toda linha nova de `mcp.jsonl` tem `v: 2`, `ok` (bool), `resp_chars` e `proc`; as com `ok: false` têm `err_code`.
- [ ] `resp_chars` é igual ao tamanho do texto que `call_tool` devolve, nos casos de sucesso, `not_found`, `invalid_argument` e `rate_limited`.
- [ ] `ragx perf --json` mostra `error_rate` e `n` por ferramenta; linhas antigas não derrubam nada.
- [ ] O custo da gravação (contagem incluída) fica registrado na Medição; chamada de 30 KB não ganha mais de 10 ms.

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Registros sem `session` (M-12) | 11 de 22 | |
| Registros sem nenhum agrupador (`session` ou `proc`) | 11 de 22 | |
| Taxa de erro por ferramenta calculável? | não | |
| Custo da contagem de tokens, resposta de 30 KB (ms) | medir primeiro | |

Comando: `ragx perf --json` e `python -c "import json;[print(l) for l in open('.ragx/logs/mcp.jsonl')]"`.

## Testes

- [ ] `tests/integration/test_mcp_telemetry.py`: `test_successful_call_logs_tool_and_ms` passa a afirmar `ok is True`, `v == 2`, `resp_chars > 0`; `test_failed_call_still_logs` (get_chunk inexistente) afirma `ok is False` e `err_code == "not_found"`; `test_validation_error_still_logs` afirma `err_code == "invalid_argument"`; novo teste de `rate_limited`. **Os de falha falham antes do conserto** (hoje não há `ok`).
- [ ] Mesmo arquivo: `resp_chars == len(texto devolvido)` e a linha não contém a consulta (`login sso`).
- [ ] `tests/unit/test_registro_atividade.py`: `proc` presente com e sem `CLAUDECODE`; `session` continua só dentro do Claude Code.
- [ ] `tests/unit/test_perf.py`: `server_stats` com linhas novas e antigas misturadas calcula `error_rate`.
- [ ] `src/app/electron/data/__tests__/activity.test.ts` e `telemetry.test.ts`: campos novos lidos; linha v1 continua válida (`npm test`, `npm run lint`, `tsc` dos dois projetos).
- [ ] Teste arquitetural "MCP é casca fina": `ragx.mcp` não ganha `os`/`open`; a escrita do log continua em `ragx.diagnostics`.

## Notas

- Confirmado: `server.py:77,93` passam `None`; `activity.ts:87` já aceita `ok` (o log da CLI já grava, `cli/main.py:177`), então só o log do MCP está atrás.
- `session` vem de `claude_origin` (`clients/registry.py:236-253`), que depende de `CLAUDECODE=1` e `CLAUDE_CODE_SESSION_ID`; versões do Claude Code sem a variável ficam sem `session`. Por isso o `proc`: ele agrupa por servidor, que é uma sessão na prática (cada sessão sobe o seu).
- O painel soma `tokens_delivered` de todas as linhas da janela (`telemetry.ts:96`); como só `build_context` o grava, a soma não muda de significado.
- Compatibilidade: campos novos são aditivos; `mcp.jsonl` já gravado segue legível. Não reescrever logs antigos.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0156)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
