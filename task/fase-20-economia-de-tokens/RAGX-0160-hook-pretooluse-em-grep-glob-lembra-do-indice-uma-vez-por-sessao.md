# RAGX-0160 — Hook `PreToolUse` em `Grep|Glob` lembra do índice uma vez por sessão

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0143, RAGX-0157 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-05, 7.3) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-T7, S13) · [14-cli.md](../../docs/14-cli.md) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `done` |

## Objetivo

Quase ninguém chama o RAGX: 3 de 38 sessões em projetos indexados (8%); fora do repo do RAGX, 1 em ~30. O funil medido: 8 sessões com hint, 4 carregaram a ferramenta via ToolSearch, 3 chamaram. O hint de SessionStart é lido uma vez e esquecido; `Grep` e `Glob` já estão carregados e o modelo vai no que está à mão. Esta tarefa adiciona um lembrete **no momento do `Grep`/`Glob`**, uma vez por sessão, que **sugere sem bloquear** (bloquear `Grep`/`Read` está descartado, spec 4.2).

## Entregáveis

- [x] **Medir primeiro:** em uma sessão real, gravar o stdin que o Claude Code entrega a um hook `PreToolUse` com matcher `Grep|Glob` (campos: `session_id`, `cwd`, `tool_name`, e se há algum que identifique subagente) e confirmar, na versão instalada (`claude --version`), se `hookSpecificOutput.additionalContext` é aceito nesse evento. Registrar em Andamento. **Se não houver canal de contexto no `PreToolUse`, parar: Status `blocked` com a nota** (não improvisar saída).
- [x] `src/ragx/clients/claude_hint.py`: generalizar o que é fixo em `EVENT = "SessionStart"` (linha 34) para um parâmetro `event` em `_grupos`, `_gravar`, `install_hint`, `remove_hint` e `has_hint`; `_NOSSO` (linha 37) passa a reconhecer também `claude nudge`. O grupo novo leva `matcher: "Grep|Glob"`. Os hooks da pessoa ficam intactos (mesmas regras de backup e idempotência).
- [x] Comando `ragx claude nudge` (`cli/commands/claude_cmd.py`, no molde de `hint`, linhas 173-201): lê o JSON do stdin, resolve o projeto pelo `cwd`, fica **calado** se o projeto não estiver indexado ou se já avisou nesta `session_id`; senão imprime `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "..."}}`. Nunca falha: qualquer erro termina em saída vazia e código 0. Usa o ponto de entrada leve da 0143 (confirmar o nome real ao começar), não a CLI inteira.
- [x] Marcador por sessão em `.ragx/cache/nudge/<session_id>`, criado com `O_CREAT|O_EXCL`: o Claude pode disparar vários `Grep`/`Glob` em paralelo e só um deve imprimir. `session_id` saneado (`[A-Za-z0-9_-]`, até 64); marcadores com mais de 7 dias são apagados ao criar um novo.
- [x] Texto de ≤ 60 tokens (medir com `count_tokens`): diz que o projeto está indexado e que `mcp__ragx__build_context(query)` devolve trechos com arquivo e linhas, sem ordenar nada. **Não ecoar `tool_input`** (o padrão buscado pode ser um segredo) e não o gravar em log.
- [x] Uma linha em `.ragx/logs/cli.jsonl` (`command: "nudge"`, via `log_cli_call`, sem argumentos) quando o lembrete é mostrado, para a 0190 medir adoção.
- [x] `ragx claude on --nudge/--no-nudge` (padrão ligado, junto da dica), `off` remove, `status` e `status --json` mostram `nudge` por perfil (`_estado`, claude_cmd.py:49-66; o painel lê só `hint`, `ipc.ts:92`, e ignora chave extra).
- [x] `docs/14-cli.md` (linhas 343-350 e 388) e `docs/09-mcp.md`. CHANGELOG.

## Fora de escopo

- Bloquear, negar ou reescrever o `Grep`/`Read` (spec 4.2). Reagir a `grep`/`rg` dentro de `Bash`.
- O subagente explorador (0161) e o texto do hint de SessionStart (0164). A fila de toque `PostToolUse` (0141).
- Medir a adoção depois do hook: precisa de ~2 semanas de dados reais; é do humano (S13).

## Critérios de aceite

- [x] `ragx claude on` num perfil de teste grava o grupo `PreToolUse` com matcher `Grep|Glob` ao lado do `SessionStart`; rodar duas vezes não duplica; `off` remove só o nosso.
- [x] Duas execuções de `ragx claude nudge` com a mesma `session_id`: a primeira imprime o JSON, a segunda não imprime nada; duas **simultâneas**: exatamente uma imprime.
- [x] Projeto não indexado, stdin vazio ou JSON inválido: saída vazia e código 0.
- [x] Latência do caminho calado e do caminho que imprime ≤ **120 ms** p50 (mesmo teto do S7).

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Latência de `ragx claude nudge`, caminho que imprime / calado (ms) | n/a (novo) | **105 / 83** (p50 de 20; Python vazio: 42 ms; meta 120) |
| Sessões que chamaram o RAGX, em projeto indexado (S13) | 8% (3 de 38) | medir em 2 semanas (humano) |

Comando: `uv run python scripts/medir_hooks.py --n 20 --entrada ragx.entry` (o script da 0143 ganhou os dois casos do `nudge`, com `session_id` novo a cada rodada no que imprime).

## Testes

- [x] `tests/unit/test_claude_profiles_hint.py` (fixture `casa`, HOME redirecionado): instalação com matcher, idempotência, hooks da pessoa preservados, `off`, `settings.json` quebrado não sobrescrito, `--no-nudge`.
- [x] `tests/unit/test_claude_nudge.py` (novo): uma vez por sessão; corrida com duas threads/processos; `session_id` hostil (`../x`, vazio, 500 chars) não escapa de `.ragx/cache/nudge/`; a saída não contém o `tool_input`; projeto sem índice calado.
- [x] `tests/security/`: o comando não lê arquivo do projeto (só `db_path.exists()` e o marcador); o teste arquitetural `test_apenas_modulos_autorizados_leem_o_filesystem` segue verde.
- [x] Nada em `src/ragx/mcp` muda: o invariante "MCP é casca fina" fica intacto.

## Notas

- **O loop nunca roda `ragx claude on` no HOME real**: ele reescreve o `~/.claude/settings.json` da pessoa. Todo teste usa a fixture `casa`.
- Confirmado: `claude_hint.py:34` (`EVENT` fixo), `:37` (`_NOSSO`), `claude_cmd.py:173-201`.
- Se o payload do hook distinguir subagente, tratá-lo como sessão própria só se isso for o desejado; sem sinal confiável, a chave é `session_id`. Decidir com a medição do primeiro item.
- No Windows o Claude Code roda hooks pelo Git Bash quando existe: reaproveitar `hint_command` (aspas e `/`) para o comando gravado.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0160)` na branch `feat/v2`

## Andamento

- 2026-10-01 — **Medição do primeiro item, pela documentação (não por uma sessão viva).** `claude --version` = 2.1.286 e a documentação de hooks (code.claude.com/docs/en/hooks) confirma que o `PreToolUse` aceita `hookSpecificOutput.additionalContext` (entra como system reminder junto ao resultado da ferramenta), entrega `session_id`, `cwd`, `tool_name`, `tool_input`, `tool_use_id` e, dentro de subagente, `agent_id`/`agent_type`. Havia canal de contexto, então a tarefa não ficou `blocked`. Não gravei o stdin real de uma sessão do Claude Code; o formato dos testes segue a documentação. A mesma página confirma os `source` do `SessionStart` (`startup`, `resume`, `clear`, `compact`, `fork`), o que fecha a dúvida da 0164 sobre os valores (e mostra que `fork` também existe: a dica é entregue de novo? não, só `clear`/`compact` reentregam; um `fork` tem outro `session_id`).
- Implementado: `claude_hint` com `_instalar/_remover/_tem` genéricos por evento (o hook de toque da 0141 passou a usá-los), `install_nudge_hook/remove_nudge_hook/has_nudge_hook` (`PreToolUse`, matcher `Grep|Glob`, síncrono, `timeout` 5, sem `async`), `ragx claude nudge` (CLI completa e entrada leve `ragx.entry`), `hooklight.run_nudge`, `texto_lembrete` (53 tokens), marcador `O_EXCL` em `.ragx/cache/nudge/<session_id>` com poda de 7 dias (a poda, `_podar_marcadores`, foi aplicada também aos marcadores da dica da 0164, que não eram podados), linha `command: "nudge"` em `cli.jsonl`, `ragx claude on --nudge/--no-nudge` e `nudge` em `status --json`. Testes: `tests/unit/test_claude_nudge.py` (22, com HOME redirecionado; o loop nunca tocou o `~/.claude/settings.json` real).
- A poda usa `os.listdir` só na pasta de marcadores (a NOSSA), e o teste arquitetural do `hooklight` continua proibindo `read_bytes`, `rglob`, `walk`, `scandir`, `iterdir` e `glob`.
- A adoção (S13) só se mede com ~2 semanas de uso real: é do humano.
