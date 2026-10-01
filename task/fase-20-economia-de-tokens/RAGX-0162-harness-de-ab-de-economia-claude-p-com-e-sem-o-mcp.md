# RAGX-0162 — Harness de A/B de economia (`claude -p` com e sem o MCP)

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P1 — alta |
| **Estimativa** | 2d |
| **Depende de** | RAGX-0156, RAGX-0157 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-03, seção 8, 7.2 #11) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S14, R-T8) · [07-context-engine.md](../../docs/07-context-engine.md) · [14-cli.md](../../docs/14-cli.md) |
| **Status** | `todo` (termina em `review`, ver Notas) |

## Objetivo

"O RAGX economiza X%" não é afirmável hoje (S14: **desconhecida**). O baseline do painel e do `ragx trial` é o arquivo inteiro (`size_bytes/4`); um agente com Grep não leria 16 arquivos inteiros, então a economia real contra Grep é um número que ninguém mediu. A única medição honesta é um A/B: as mesmas tarefas rodadas por `claude -p` com e sem o MCP, comparando o consumo que o próprio Claude Code reporta. Esta tarefa entrega o **harness**, com `--dry-run` e modo simulado, e **não o executa com chamadas reais** (gasta cota da conta).

## Entregáveis

- [ ] **Conferir os flags antes:** `claude --help` (sem chamar a API) para confirmar `-p`, `--output-format json`, `--mcp-config`, `--strict-mcp-config`, `--max-turns`, `--allowedTools`, `--model` e, se existir, um flag que isole configuração do usuário. Confirmar quais campos o JSON traz (`usage`, `total_cost_usd`, `num_turns`, `duration_ms`). Registrar em Andamento; não presumir.
- [ ] `src/ragx/search/ab.py` (novo): `AbTask` (consulta + `relevant_paths`, de `load_cases` ou `auto_cases`, `search/evaluation.py` e `search/trial.py:75`), `ArmResult`, `AbReport`, protocolo `Runner`, `ClaudeRunner` (subprocess `claude -p`, `shutil.which` para o `claude.cmd` do Windows) e `SimulatedRunner` (determinístico por semente, marca `simulated: true`).
- [ ] Braços: `without` (`--strict-mcp-config` com `mcpServers` vazio), `full` e `slim` (servidor do RAGX num JSON temporário de `--mcp-config`, perfil por `RAGX_MCP_PROFILE`, da 0157). Mesmas ferramentas nativas, mesmo modelo, mesmo `--max-turns`, ordem dos braços alternada por tarefa, `--reps` repetições.
- [ ] Acerto: cada tarefa pede os caminhos dos arquivos relevantes; `hit` = algum `relevant_paths` citado na resposta (comparação de texto, determinística). Economia sem acerto não conta (mesma lógica da cobertura de fonte do `trial`).
- [ ] Contabilidade: por braço, `input`, `output`, `cache_creation` e `cache_read` do `usage`, `cost_usd`, turnos, ferramentas chamadas. Manchete: tokens faturáveis (`input + cache_creation + output`) **e** custo; mostrar a soma bruta também. Para o braço com RAGX, cruzar com o `resp_tokens` do `mcp.jsonl` no intervalo (0156) para calibrar o contador heurístico.
- [ ] Estatística: deltas pareados por tarefa; mediana e quartis; rótulo **inconclusivo** quando houver menos de 10 tarefas ou o intervalo cruzar zero. O relatório traz o método (versão do `claude`, modelo, flags, N, reps, data, perfil, commit).
- [ ] `ragx ab` (`cli/commands/ab_cmd.py`, registrado em `cli/main.py`, junto da linha 54): `--dry-run` (padrão: imprime as chamadas planejadas e o total de chamadas, sem executar nada), `--simulate`, `--execute` (só vale com `RAGX_AB_REAL=1` e `--max-calls N`), `--arms`, `--reps`, `--model`, `--max-turns`, `--queries`, `--out`. Grava `.ragx/ab/<data>.json` e `latest.json`.
- [ ] **Não persistir o texto da resposta**: só `hit`, caminhos citados e contagens. `docs/07-context-engine.md` (A/B versus `trial`) e `docs/14-cli.md`. CHANGELOG.

## Fora de escopo

- **Rodar com chamadas reais.** Decisão humana: gasta cota. O loop entrega o harness e deixa a tarefa em `review`.
- Gerar as tarefas a partir do git (conjunto-ouro, 0167). Mostrar o resultado no painel (0163, 0190).
- Medir qualidade da resposta além do `hit`. Controlar o efeito do `CLAUDE.md`/`AGENTS.md` do projeto (ver Notas).

## Critérios de aceite

- [ ] `ragx ab --dry-run` termina com código 0, imprime as chamadas por braço e **não** inicia subprocesso (o teste troca o `Runner` por um que levanta exceção se chamado).
- [ ] `ragx ab --simulate` roda de ponta a ponta, grava o relatório com `simulated: true` e **não** imprime nenhuma economia como "real".
- [ ] `--execute` sem `RAGX_AB_REAL=1` ou sem `--max-calls` recusa, com mensagem que diz o custo planejado.
- [ ] O relatório contém os campos do método e rotula "inconclusivo" corretamente.

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Economia real contra Grep (S14) | desconhecida | medida por uma pessoa depois do `review` |
| Tarefas × braços × repetições do plano padrão | — | `ragx ab --dry-run` informa |

## Testes

- [ ] `tests/unit/test_ab.py` (novo): argv de cada braço (JSON de `--mcp-config` com espaço no caminho, aspas no Windows), alternância de ordem, `hit`, estatística pareada e rótulo inconclusivo, determinismo do `SimulatedRunner`, recusa de `--execute` sem as guardas.
- [ ] `tests/e2e/test_cli_ab.py` (novo): `ragx ab --dry-run` e `--simulate` com `typer.testing`; o relatório não contém texto de resposta.
- [ ] `tests/security/`: o harness não lê arquivo do projeto além do YAML de consultas; `test_apenas_modulos_autorizados_leem_o_filesystem` segue verde (`ragx.search` já está na lista).
- [ ] Nada em `src/ragx/mcp` muda; o invariante "MCP é casca fina" fica intacto.

## Notas

- Termina em **`review`**, não `done`. O loop entrega harness, testes e documentação. **Rodar `ragx ab --execute` é decisão e custo da pessoa.** Escrever em Andamento o comando exato e o total de chamadas que o `--dry-run` calculou.
- Confundidor: no repo do RAGX o `AGENTS.md` manda usar o RAGX; o braço `without` ficaria sem a ferramenta mas com o texto pedindo-a. Medir em um projeto cujo `CLAUDE.md`/`AGENTS.md` não cite o RAGX, ou isolar a configuração (flag a confirmar no primeiro item). O hook de SessionStart do usuário também vale nos dois braços.
- Resultados de LLM variam entre execuções; por isso `--reps` e os quartis. Não publicar uma mediana sem N.
- Tokens do `usage` são os do Claude de verdade; o contador do RAGX é estimativa (+11% em prosa, +29% em código contra cl100k, que tampouco é o do Claude, auditoria seção 8). O cruzamento com `resp_tokens` serve para saber o quanto.
- Windows: o executável costuma ser `claude.cmd`; `subprocess` sem `shell=True` precisa do caminho resolvido por `shutil.which`.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0162)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
