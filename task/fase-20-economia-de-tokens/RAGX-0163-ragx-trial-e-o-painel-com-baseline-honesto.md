# RAGX-0163 — `ragx trial` e o painel com baseline honesto

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0154, RAGX-0156 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-03, seção 8) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-T6, S14) · [07-context-engine.md](../../docs/07-context-engine.md) · [14-cli.md](../../docs/14-cli.md) |
| **Status** | `todo` |

## Objetivo

O "sem RAGX" do `ragx trial` e do gráfico do painel é o **arquivo inteiro** (`size_bytes // 4` no log, `read_text` no trial). Um agente com Grep não leria 16 arquivos inteiros: a economia real contra Grep é **desconhecida** (S14, medida só pelo A/B da 0162). Pior, a economia logada hoje é 92,7% enquanto a entrega real é ~82% (M-03), e as duas pontas estão em unidades diferentes (bytes/4 contra o contador heurístico). Esta tarefa não inventa o número real: faz os dois números honestos, rotulados pelo que são.

## Entregáveis

- [ ] **Medir primeiro:** `ragx trial --json` no repo (26 consultas, `tests/eval/queries.yaml`) e registrar totais, cobertura de fonte e quantas consultas têm economia negativa (a documentação cita ~10 de 26, `docs/07-context-engine.md:207-211`). Registrar também a diferença entre `size_bytes // 4` e a soma de `chunks.token_count` dos mesmos documentos.
- [ ] `src/ragx/search/trial.py` (`TrialResult`, 20-37; `run_trial`, 40-65): `ragx_tokens` = tokens do markdown entregue (a contagem da 0154); novo `baseline_grep_tokens`: simula "Grep + Read" com os `K` primeiros documentos distintos de `search(..., mode="keyword")` lidos inteiros (`K` em `--grep-files`; escolher o padrão medindo K = 1, 3 e 5 e registrando a sensibilidade). O baseline antigo passa a se chamar **oráculo** (os `relevant_paths` inteiros).
- [ ] Manchete conservadora: `saved_ratio_conservative` = economia contra o **menor** dos dois baselines. Em `totals` e por consulta: `baseline_oracle_tokens`, `baseline_grep_tokens`, `saved_ratio_conservative`. `baseline_tokens` e `saved_ratio` ficam como estão (compatibilidade com `TrialResult` do painel, `ragx-bridge.d.ts:52-62`).
- [ ] `src/ragx/cli/commands/trial_cmd.py` (30-132): colunas Oráculo, Grep~, RAGX, Economia (conservadora), Fonte; `CAVEAT_LINES` (21-26) reescrito: são dois proxies, nenhum é uma sessão real, e o número real vem de `ragx ab` (0162).
- [ ] `_baseline_tokens` (`mcp/server.py:455-475`) sai do servidor para `src/ragx/context/baseline.py` (é lógica, não casca) e passa a somar `chunks.token_count` dos documentos-fonte, na **mesma unidade** do entregue, em vez de `size_bytes // 4`. O campo do log continua `baseline_tokens`.
- [ ] Painel: `TokenSavings.tsx` (rótulos "Sem RAGX" nas linhas 125 e 186 e o texto das linhas 232-235) passa a dizer "Arquivos inteiros (limite superior)" e "Economia estimada"; `EstimatePanel.tsx` `TrialFigures` (60-91) mostra a economia conservadora e os dois baselines; `ragx-bridge.d.ts` ganha os campos novos como opcionais (CLI antigo continua funcionando).
- [ ] Docs: `docs/07-context-engine.md` (seção "Trial", 185-211), `docs/14-cli.md` (171-174), `docs/GUIA-DE-USO.md` (211). CHANGELOG com antes/depois e a nota de que logs antigos usam bytes/4.

## Fora de escopo

- O A/B com `claude -p` (0162) e exibir o resultado dele no painel (0187/0190).
- Redesenhar o gráfico ou o card de economia (tarefas da fase 22). Mudar o tokenizer.
- Dizer "economia real" em qualquer lugar: só o A/B tem esse direito.

## Critérios de aceite

- [ ] `ragx trial --json` traz `baseline_oracle_tokens`, `baseline_grep_tokens` e `saved_ratio_conservative`, com `saved_ratio_conservative == 1 - ragx_tokens / min(baselines)` (teste).
- [ ] `ragx_tokens` é igual aos tokens do markdown entregue e ≤ `budget` em todas as consultas.
- [ ] Nenhum texto do painel chama o baseline de "economia real"; os rótulos novos têm teste.
- [ ] `ragx trial` antigo (sem os campos novos) continua legível pelo painel.

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Economia logada pelo servidor (M-03) | 92,7% | |
| Economia com a entrega real (M-03) | ~82% | |
| Economia conservadora do `trial` (26 consultas, `--budget 3000`) | medir primeiro | |
| Consultas com economia negativa | ~10 de 26 (docs/07) | |

Comando: `uv run ragx trial --budget 3000 --json`.

## Testes

- [ ] `tests/integration/test_trial.py`: `baseline_grep_tokens` calculado, `saved_ratio_conservative` usa o menor baseline, `ragx_tokens` bate com o markdown (`test_ragx_tokens_never_exceed_budget`, linha 47, segue verde).
- [ ] `tests/e2e/test_cli_trial.py`: o JSON traz as chaves novas e as antigas; a saída humana imprime os dois baselines e o aviso novo (`test_trial_human_output_prints_honesty_caveat`, linha 48, atualizado).
- [ ] `tests/integration/test_mcp_telemetry.py::test_build_context_logs_baseline_from_index` (linha 74): passa a esperar a soma de `chunks.token_count`.
- [ ] `src/app`: `ProjectPage.test.tsx` e testes de `EstimatePanel`/`TokenSavings` com os rótulos novos (`npm test`, `npm run lint`, `tsc` dos dois projetos).
- [ ] Teste arquitetural "MCP é casca fina": `ragx.mcp` perde `_baseline_tokens`, não ganha `os`/`open`; `tests/security` verde.

## Notas

- Confirmado: `server.py:455-475` usa `size_bytes // 4`; `trial.py:47-49` lê o arquivo do disco; `telemetry.ts:38-50` só soma linhas que têm as duas medidas.
- O gráfico de 14 dias vai misturar linhas antigas (bytes/4) e novas (tokens do contador); a ordem de grandeza é a mesma e a mudança fica no CHANGELOG. Não reescrever logs.
- O "Grep simulado" é um proxy declarado, não um agente: `K` e a busca por palavra-chave são escolhas. Se a sensibilidade a `K` for grande (ex.: a economia muda de sinal entre K=1 e K=5), dizer isso no `docs/07` em vez de esconder; é exatamente a razão de o A/B existir.
- Os números do painel só mudam quando o log novo existir: um projeto sem uso recente mostra o texto novo com os dados antigos. Aceitável.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0163)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
