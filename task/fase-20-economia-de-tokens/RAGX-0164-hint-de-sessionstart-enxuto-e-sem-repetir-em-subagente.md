# RAGX-0164 — Hint de SessionStart enxuto e sem repetir em subagente

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0143, RAGX-0157 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-08, M-12, 4.1) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S7, S13) · [14-cli.md](../../docs/14-cli.md) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `todo` |

## Objetivo

O hint de SessionStart custa **~285 tokens** e, segundo a auditoria, repete em cada subagente: ~20 eventos `session_start` em 2 minutos numa sessão com subagentes. Além do token, isso infla a contagem de sessões que o painel e o S13 (adoção) usam como denominador. Esta tarefa enxuga o texto e entrega o hint **uma vez por sessão**, sem deixar de reentregá-lo depois de `/clear` ou compactação, quando o contexto de fato o perdeu.

## Entregáveis

- [ ] **Medir primeiro:** (a) `count_tokens(hint_text())` no repo (`claude_hint.py:178-190`); (b) gravar o stdin do hook de SessionStart em uma sessão com subagentes (campos `session_id`, `source`, outros) e contar os `session_start` de `.ragx/logs/cli.jsonl` por `session`. **Hipótese a testar:** os ~20 eventos podem ser sessões distintas (`claude -p` em lote), não subagentes. Registrar o que se confirmou em Andamento.
- [ ] `src/ragx/clients/claude_hint.py` `_texto_projeto` (224-256) e `_texto_pasta_pai` (259-290): reescrever em **≤ 150 tokens**. Fica: nome, "indexado", a regra (RAGX antes de `Grep`/`Glob`/`Read` para "onde", "como funciona", "o que chama o quê"), `mcp__ragx__build_context(query)`, `search_hybrid`, `get_chunk` e a linha de ToolSearch `select:` (`_FERRAMENTAS`, linha 175). Sai o resumo de documentos/data/branch do índice e a frase "Pule o RAGX só quando...". A linha sobre `refresh` sai se a 0141 (`stale_paths`) já existir.
- [ ] Os nomes de ferramenta do texto existem nos dois perfis do servidor (`full` e `slim`, da 0157).
- [ ] Uma vez por sessão: ler o JSON do stdin (via a entrada leve da 0143; sem bloquear se o stdin for terminal ou vazio, para o uso manual de `ragx claude hint` seguir igual). Marcador `.ragx/cache/hint/<session_id>` criado com `O_CREAT|O_EXCL`; `session_id` saneado (`[A-Za-z0-9_-]`, até 64). Repetição na mesma sessão: saída vazia.
- [ ] **Reentrega quando o contexto foi perdido:** se o stdin trouxer `source` igual a `clear` ou `compact`, imprimir de novo e renovar o marcador. Confirmar os valores reais no primeiro item; sem o campo, a chave é só `session_id`.
- [ ] `record_session_start` (193-213) só grava o evento quando o hint é de fato entregue pela primeira vez na sessão.
- [ ] `claude_cmd.py` `hint` (173-201) passa o stdin adiante; continua sem nunca falhar.
- [ ] `docs/14-cli.md` (linhas 347 e 388) e `docs/09-mcp.md` (307-312). CHANGELOG.

## Fora de escopo

- Latência do hook e entrada sem importar a CLI inteira (0143, S7). O lembrete no `Grep`/`Glob` (0160). O subagente explorador (0161).
- Repo map no SessionStart (0168). Trocar a regra de adoção ou o canal de entrega (stdout).
- Bloquear qualquer ferramenta (spec 4.2).

## Critérios de aceite

- [ ] `count_tokens(hint_text())` ≤ **150** num projeto indexado e na pasta-pai (`_texto_pasta_pai`), registrando qual contador estava ativo (`chars/4` e tiktoken diferem).
- [ ] Duas execuções com o mesmo `session_id`: a segunda imprime vazio e não grava `session_start`; com `source: "compact"` ou `"clear"`, imprime de novo.
- [ ] Fora de projeto RAGX continua calado; execução manual sem stdin continua imprimindo o hint.
- [ ] Nenhum nome `mcp__ragx__*` do texto falta em `full` ou `slim`.

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Tokens do hint (projeto indexado) | ~285 (auditoria, `chars/4`); 349 re-medido aqui com tiktoken cl100k | |
| Eventos `session_start` por sessão, com subagentes | ~20 em 2 min (M-08) | |
| Latência de `ragx claude hint` | 481–659 ms (S7 é da 0143) | não regredir |

Comando: `uv run python -c "from ragx.clients.claude_hint import hint_text; from ragx.tokens import count_tokens; print(count_tokens(hint_text()))"`.

## Testes

- [ ] `tests/unit/test_claude_profiles_hint.py`: ajustar `test_dica_em_projeto_indexado` (linha 151), `test_dica_na_pasta_pai_aponta_o_scope_de_cada_projeto` (164) e `test_comando_hint_escreve_no_stdout_e_nunca_falha` (182); novos: teto de 150 tokens, uma vez por sessão, reentrega com `source`, `session_id` hostil (`../x`, 500 chars) preso a `.ragx/cache/hint/`, stdin inválido.
- [ ] Mesmo arquivo: conferir os nomes `mcp__ragx__*` do texto contra `build_server(cfg, profile=...).list_tools()` nos dois perfis.
- [ ] `tests/unit/test_registro_atividade.py::test_inicio_de_sessao_do_claude_vira_evento` (linha 104): um evento por sessão.
- [ ] `tests/security`: o hint não lê arquivo do projeto além de `db_path` e do marcador; teste arquitetural de leitura de filesystem segue verde. Nada em `src/ragx/mcp` muda.

## Notas

- **Se a medição desmentir a premissa** (SessionStart não dispara em subagente, e os eventos repetidos são sessões distintas), a tarefa vira: enxugar o texto e contar sessões distintas corretamente. Não inventar detecção de subagente sem sinal confiável; registrar em Andamento.
- Confirmado: `claude_hint.py:224-256` monta o texto e lê `status.json` (`_status`, 216-221); `record_session_start` só grava quando `claude_origin()` existe (linhas 204-205).
- Cortar o resumo de data e branch tira do agente um sinal de frescor; a 0141 devolve esse sinal onde importa (`stale_paths` na busca).
- Windows: `session_id` vira nome de arquivo; o saneamento evita `:` e `\`. O stdout continua em UTF-8 por bytes (claude_cmd.py:194-199).

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0164)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
