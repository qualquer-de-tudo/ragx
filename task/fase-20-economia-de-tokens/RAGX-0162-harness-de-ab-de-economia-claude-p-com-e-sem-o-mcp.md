# RAGX-0162 — Harness de A/B de economia (`claude -p` com e sem o MCP)

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P1 — alta |
| **Estimativa** | 2d |
| **Depende de** | RAGX-0156, RAGX-0157 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-03, seção 8, 7.2 #11) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S14, R-T8) · [07-context-engine.md](../../docs/07-context-engine.md) · [14-cli.md](../../docs/14-cli.md) |
| **Status** | `review` |

## Objetivo

"O RAGX economiza X%" não é afirmável hoje (S14: **desconhecida**). O baseline do painel e do `ragx trial` é o arquivo inteiro (`size_bytes/4`); um agente com Grep não leria 16 arquivos inteiros, então a economia real contra Grep é um número que ninguém mediu. A única medição honesta é um A/B: as mesmas tarefas rodadas por `claude -p` com e sem o MCP, comparando o consumo que o próprio Claude Code reporta. Esta tarefa entrega o **harness**, com `--dry-run` e modo simulado, e **não o executa com chamadas reais** (gasta cota da conta).

## Entregáveis

- [x] **Conferir os flags antes:** `claude --help` (sem chamar a API) para confirmar `-p`, `--output-format json`, `--mcp-config`, `--strict-mcp-config`, `--max-turns`, `--allowedTools`, `--model` e, se existir, um flag que isole configuração do usuário. Confirmar quais campos o JSON traz (`usage`, `total_cost_usd`, `num_turns`, `duration_ms`). Registrar em Andamento; não presumir.
- [x] `src/ragx/search/ab.py` (novo): `AbTask` (consulta + `relevant_paths`, de `load_cases` ou `auto_cases`, `search/evaluation.py` e `search/trial.py:75`), `ArmResult`, `AbReport`, protocolo `Runner`, `ClaudeRunner` (subprocess `claude -p`, `shutil.which` para o `claude.cmd` do Windows) e `SimulatedRunner` (determinístico por semente, marca `simulated: true`).
- [x] Braços: `without` (`--strict-mcp-config` com `mcpServers` vazio), `full` e `slim` (servidor do RAGX num JSON temporário de `--mcp-config`, perfil por `RAGX_MCP_PROFILE`, da 0157). Mesmas ferramentas nativas, mesmo modelo, mesmo `--max-turns`, ordem dos braços alternada por tarefa, `--reps` repetições.
- [x] Acerto: cada tarefa pede os caminhos dos arquivos relevantes; `hit` = algum `relevant_paths` citado na resposta (comparação de texto, determinística). Economia sem acerto não conta (mesma lógica da cobertura de fonte do `trial`).
- [x] Contabilidade: por braço, `input`, `output`, `cache_creation` e `cache_read` do `usage`, `cost_usd`, turnos, ferramentas chamadas. Manchete: tokens faturáveis (`input + cache_creation + output`) **e** custo; mostrar a soma bruta também. Para o braço com RAGX, cruzar com o `resp_tokens` do `mcp.jsonl` no intervalo (0156) para calibrar o contador heurístico.
- [x] Estatística: deltas pareados por tarefa; mediana e quartis; rótulo **inconclusivo** quando houver menos de 10 tarefas ou o intervalo cruzar zero. O relatório traz o método (versão do `claude`, modelo, flags, N, reps, data, perfil, commit).
- [x] `ragx ab` (`cli/commands/ab_cmd.py`, registrado em `cli/main.py`, junto da linha 54): `--dry-run` (padrão: imprime as chamadas planejadas e o total de chamadas, sem executar nada), `--simulate`, `--execute` (só vale com `RAGX_AB_REAL=1` e `--max-calls N`), `--arms`, `--reps`, `--model`, `--max-turns`, `--queries`, `--out`. Grava `.ragx/ab/<data>.json` e `latest.json`.
- [x] **Não persistir o texto da resposta**: só `hit`, caminhos citados e contagens. `docs/07-context-engine.md` (A/B versus `trial`) e `docs/14-cli.md`. CHANGELOG.

## Fora de escopo

- **Rodar com chamadas reais.** Decisão humana: gasta cota. O loop entrega o harness e deixa a tarefa em `review`.
- Gerar as tarefas a partir do git (conjunto-ouro, 0167). Mostrar o resultado no painel (0163, 0190).
- Medir qualidade da resposta além do `hit`. Controlar o efeito do `CLAUDE.md`/`AGENTS.md` do projeto (ver Notas).

## Critérios de aceite

- [x] `ragx ab --dry-run` termina com código 0, imprime as chamadas por braço e **não** inicia subprocesso (o teste troca o `Runner` por um que levanta exceção se chamado).
- [x] `ragx ab --simulate` roda de ponta a ponta, grava o relatório com `simulated: true` e **não** imprime nenhuma economia como "real".
- [x] `--execute` sem `RAGX_AB_REAL=1` ou sem `--max-calls` recusa, com mensagem que diz o custo planejado.
- [x] O relatório contém os campos do método e rotula "inconclusivo" corretamente.
- [x] **A tarefa termina em Status `review`, não `done`:** o loop nunca roda com chamadas reais (gasta cota da conta). Em Andamento, deixa o comando exato de `--execute` e o total de chamadas do `--dry-run` para a pessoa.

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Economia real contra Grep (S14) | desconhecida | **medida em 02/10/2026, inconclusiva em tokens faturáveis** (27,6 mil → 26,0 mil, IC95% −1,8% a +15,0%); custo −18%, turnos 6 → 3; ver `docs/26-resultados-v2.md` |
| Tarefas × braços × repetições do plano padrão | — | 12 × 3 × 1 = **36 chamadas** (`ragx ab`, neste repo com `tests/eval/queries.yaml`) |

## Testes

- [x] `tests/unit/test_ab.py` (novo): argv de cada braço (JSON de `--mcp-config` com espaço no caminho, aspas no Windows), alternância de ordem, `hit`, estatística pareada e rótulo inconclusivo, determinismo do `SimulatedRunner`, recusa de `--execute` sem as guardas.
- [x] `tests/e2e/test_cli_ab.py` (novo): `ragx ab --dry-run` e `--simulate` com `typer.testing`; o relatório não contém texto de resposta.
- [x] `tests/security/`: o harness não lê arquivo do projeto além do YAML de consultas; `test_apenas_modulos_autorizados_leem_o_filesystem` segue verde (`ragx.search` já está na lista).
- [x] Nada em `src/ragx/mcp` muda; o invariante "MCP é casca fina" fica intacto.

## Notas

- Termina em **`review`**, não `done`. O loop entrega harness, testes e documentação. **Rodar `ragx ab --execute` é decisão e custo da pessoa.** Escrever em Andamento o comando exato e o total de chamadas que o `--dry-run` calculou.
- Confundidor: no repo do RAGX o `AGENTS.md` manda usar o RAGX; o braço `without` ficaria sem a ferramenta mas com o texto pedindo-a. Medir em um projeto cujo `CLAUDE.md`/`AGENTS.md` não cite o RAGX, ou isolar a configuração (flag a confirmar no primeiro item). O hook de SessionStart do usuário também vale nos dois braços.
- Resultados de LLM variam entre execuções; por isso `--reps` e os quartis. Não publicar uma mediana sem N.
- Tokens do `usage` são os do Claude de verdade; o contador do RAGX é estimativa (+11% em prosa, +29% em código contra cl100k, que tampouco é o do Claude, auditoria seção 8). O cruzamento com `resp_tokens` serve para saber o quanto.
- Windows: o executável costuma ser `claude.cmd`; `subprocess` sem `shell=True` precisa do caminho resolvido por `shutil.which`.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo): o harness está verificado; a economia real NÃO (exige chamadas reais)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0162)` na branch `feat/v2`

## Andamento

- 2026-10-01 — **Flags conferidos com `claude --help` (2.1.286, sem chamar a API):** `-p/--print`, `--output-format`, `--mcp-config`, `--strict-mcp-config`, `--allowedTools`, `--model`, `--setting-sources`, `--settings`, `--no-session-persistence`, `--bare` ("mínimo: sem hooks, `CLAUDE.md`, auto-memory...; exige `ANTHROPIC_API_KEY`"). **`--max-turns` NÃO aparece no `--help`** desta versão: o harness só o repassa se a pessoa pedir (`--max-turns N`), e se o `claude` o recusar a chamada real falha com erro registrado. **O formato do JSON de `--output-format json` NÃO foi confirmado** (não chamei a API): `ClaudeRunner` lê `result`, `usage.{input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens}`, `total_cost_usd`, `num_turns`, `duration_ms` e `is_error`, que são os campos esperados; a primeira execução real deve conferir (`--json` do `ragx ab` mostra o que veio).
- Implementado: `search/ab.py` (`AbTask`, `Call`, `ArmResult`, `Runner`, `ClaudeRunner` via `run_quiet`, `SimulatedRunner` por semente, `plan`/`build_argv`/`mcp_config`, `is_hit`/`cited_paths`, `paired_savings`, `quartiles`, `bootstrap_ci`, `summarize`, `run_ab`) e `ragx ab` (`cli/commands/ab_cmd.py`). Testes: `tests/unit/test_ab.py` (17) e `tests/e2e/test_cli_ab.py` (10), com o subprocesso proibido por um stub nos testes de plano, simulado e guardas.
- Decisões: o prompt vai pelo stdin (não no argv); cada tarefa pede os caminhos e o `hit` é busca de texto dos `relevant_paths`; o cruzamento com `resp_tokens` do `mcp.jsonl` guarda `ragx_calls` e `ragx_resp_tokens` por chamada; o commit do projeto só é lido na execução real (o simulado não toca no git); a contagem de "ferramentas chamadas" não existe no JSON simples (só no `stream-json`), então ficou `ragx_calls` do log.
- **Para a pessoa rodar (decisão e custo seus).** Plano padrão deste repositório: 12 tarefas × 3 braços × 1 repetição = **36 chamadas** a `claude -p`. Comando exato: `RAGX_AB_REAL=1 ragx ab --execute --max-calls 36 --reps 1` (acrescente `--model <modelo>` e `--max-turns N` se quiser fixá-los; use `--reps 3` para o intervalo de confiança ficar útil: 108 chamadas, `--max-calls 108`). Antes: (1) este repo tem `AGENTS.md` mandando usar o RAGX, o que contamina o braço `without`; prefira um projeto cujo `CLAUDE.md` não cite o RAGX, ou `--isolate` (exige `ANTHROPIC_API_KEY`); (2) com menos de 10 tarefas ou um intervalo que cruza zero o relatório diz "inconclusivo", e é isso que deve ser publicado; (3) ligue o dedupe de sessão (`[context] session_dedupe = true`) só num braço extra se quiser medir a 0159, que hoje vem desligado.
- 2026-10-02 — **Rodado com chamadas reais (a pessoa autorizou e arcou com o custo): 36 chamadas, 18 tarefas do conjunto-ouro do git × 2 braços, no projeto dela.** Duas falhas do harness achadas pelas chamadas de fumaça, antes de gastar as 36: (1) em `claude -p` ninguém aprova permissão, então toda chamada ao RAGX era **negada** (`permission_denials`) e o braço com RAGX media "sem RAGX" (0 chamadas em 12 e 8 turnos); corrigido com `--allowedTools mcp__ragx`, `permission_denials` no relatório e aviso no comando; (2) sem a dica de início o agente prefere o `Grep`: novas opções `--with-hooks` e `--setting-sources`. Resultado em `docs/26-resultados-v2.md` (S14): inconclusivo em tokens faturáveis, custo −18%, turnos 6 → 3. Continua em `review`: uma pessoa decide se mede de novo com tarefas de entendimento amplo.
