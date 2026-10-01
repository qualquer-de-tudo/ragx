# RAGX-0157 — Perfil `slim` do MCP: 6 ferramentas (`full` continua disponível)

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 2d |
| **Depende de** | RAGX-0137, RAGX-0154, RAGX-0155 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-04, 4.1) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S2, R-T3) · [09-mcp.md](../../docs/09-mcp.md) · [15-configuracao.md](../../docs/15-configuracao.md) |
| **Status** | `todo` |

## Objetivo

O servidor expõe 33 ferramentas e 28 nunca foram chamadas (só `build_context`, `search_hybrid`, `get_dictionary`, `get_playbook` e `sync` aparecem nos logs e transcripts). Custo fixo medido: **2.660 tokens** de nome+descrição+schema (3.450 no `tools/list` com `outputSchema`); quem só usa o RAGX paga isso a cada turno no modo `auto` do Claude Code. Um protótipo de 6 ferramentas mediu **419 tokens (−84%)**. Esta tarefa entrega o perfil `slim` e **não troca o padrão**.

## Entregáveis

- [ ] **Corrigir a régua antes:** `perf_cmd._footprint` (perf_cmd.py:31) e `mcp_cmd.tools` (mcp_cmd.py:63) leem `inputSchema`; no `mcp` 2.2.0 o campo é `input_schema`. Hoje `ragx perf` conta ~1.000 tokens (em vez de ~2.650) e `ragx mcp tools --json` imprime `input_schema: null`. Extrair `footprint_tokens(listed)` para `src/ragx/perf.py` e usar nos dois.
- [ ] **Medir primeiro:** registrar o footprint do `full` com a régua corrigida (esta máquina deu 2.649 contra os 2.660 da auditoria).
- [ ] `src/ragx/config.py` `McpCfg` (136-145): `profile: Literal["full", "slim"] = "full"`. `RAGX_MCP_PROFILE` já funciona via `_from_env` (config.py:244-262).
- [ ] `src/ragx/mcp/server.py` `build_server` (575-769): separar as 33 registrações em grupos (`núcleo`, `consulta extra`, `escrita de índice`, `tarefas`) e aceitar `profile`. **`slim` = `get_dictionary`, `search_hybrid`, `build_context`, `get_chunk`, `get_entity`, `refresh`.** A auditoria mediu 6 mas não lista quais; esta lista vem das chamadas reais e do fluxo que os perfis de agente ensinam (`src/ragx/agents/profile.py:182-185` cita as 4 primeiras). `get_playbook` vira as `instructions` (0158); `sync` fica na CLI.
- [ ] Schemas de entrada enxutos nas 6: sem `title`, sem `anyOf: null`, sem `default`. Pós-processar `Tool.parameters` numa função `_slim_schemas(server)` (o gerenciador de ferramentas é privado no SDK; isolar ali e cobrir com teste).
- [ ] Descrições das 6 curtas e com a função primeiro (a otimização para Tool Search é da 0158).
- [ ] `ragx mcp serve --profile` e `ragx mcp tools --profile` (mcp_cmd.py 19-74); `serve()` em server.py (772-780) repassa. Sem opção, vale `cfg.mcp.profile`.
- [ ] Mensagens de erro que citam ferramenta inexistente: `mcp/operations.py:38,59` mandam "use get_status", que não existe em perfil nenhum. Trocar pelo que existe.
- [ ] `docs/09-mcp.md`: seção "Perfis" (as 6, como ligar: `[mcp] profile = "slim"` em `ragx.toml` ou `~/.config/ragx/config.toml`, `RAGX_MCP_PROFILE=slim`, `--profile slim`). `README.md` e `install/README.md` citam "33 ferramentas": manter, dizendo que é o `full`. CHANGELOG.

## Fora de escopo

- **Trocar o padrão para `slim`.** Decisão humana (roteiro, "O que o loop NÃO decide"): só depois de a pessoa conferir os perfis de agente gerados.
- Os nomes antigos continuam existindo, com o mesmo comportamento, no `full`: nada é renomeado nem removido.
- `instructions` ≤ 2 KB e lista estável (0158). Dedupe (0159). Formato de resposta (0155).
- `ragx mcp install --profile` (gravar o argumento no cliente) e esconder as ferramentas de tarefa atrás de flag no `full`.

## Critérios de aceite

- [ ] S2: no `slim`, nome+descrição+schema **≤ 600 tokens** (`ragx mcp tools --profile slim --json`, depois a régua de `footprint_tokens`).
- [ ] `build_server(cfg)` sem perfil continua expondo as mesmas 33 ferramentas, com os mesmos nomes e argumentos.
- [ ] As 6 respondem corretamente no `slim`; `refresh` em modo leitura responde `write_disabled`.
- [ ] `McpCfg().profile == "full"`: o padrão não mudou.
- [ ] **A tarefa termina em Status `review`, não `done`:** o padrão só vira `slim` por decisão da pessoa, depois de conferir os perfis de agente gerados. Em Andamento, o loop escreve o que a pessoa precisa conferir.

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Ferramentas expostas (`full` / `slim`) | 33 / — | 33 / 6 |
| Custo fixo `full`, tokens (nome+descrição+schema) | 2.660 (2.649 re-medido) | |
| Custo fixo `slim`, tokens (S2) | protótipo 419 | |
| `tools/list` do `slim`, tokens | — | |

Comando: `uv run ragx mcp tools --profile slim --json`.

## Testes

- [ ] `tests/integration/test_mcp.py`: `test_perfil_slim_expoe_so_as_seis` e `test_perfil_padrao_e_full_com_33`. `test_servidor_registra_as_ferramentas` (linha 278) fica como está.
- [ ] `tests/unit/test_mcp_perfis.py` (novo): `RAGX_MCP_PROFILE=slim` chega ao `McpCfg`; schemas do `slim` sem `title`/`anyOf`/`default`; S2 ≤ 600; `ragx mcp tools --json` com `input_schema` não nulo (**falha antes do conserto**).
- [ ] `tests/unit/test_perf.py`: `footprint_tokens` usa `input_schema` (regressão da régua).
- [ ] `tests/unit/test_documentacao_mcp.py`: `test_o_readme_nao_promete_uma_contagem...` (linha 80) compara cada "N ferramentas" do README com a contagem de **algum** perfil.
- [ ] Teste arquitetural "MCP é casca fina" (`tests/security/test_architecture.py`): sem `os`/`open` em `src/ragx/mcp` ao separar os grupos. `tests/security/test_surfaces.py` segue verde.

## Notas

- Termina em **`review`**, não `done`. O loop entrega o perfil, os testes e a documentação; **não** muda o padrão. Para a pessoa: conferir `agents/*/instructions.md` e o texto de `ragx claude hint`, que citam `get_dictionary`, `search_hybrid`, `build_context` e `get_chunk` (todos no `slim`) e `mcp__ragx__refresh`; depois trocar `McpCfg.profile` para `"slim"`.
- Pegadinha: a regex do teste do README (`(\d+)\s+ferramentas`) casa "6 ferramentas" e comparava com 33. Por isso o item de teste acima: não escrever "6 ferramentas" no README sem ele.
- `scope`: a 0137 decide se `scope` é honrado ou recusado. Se for honrado, o `slim` mantém `scope` em `search_hybrid` e `build_context`; se for recusado fora de `current`, tirar do schema do `slim` para poupar tokens.
- O cliente VS Code chama `task_status`, `list_projects` etc. (McpClient.ts): ele continua no `full`. Não apontar o plugin para o `slim`.
- Se 6 ferramentas passarem de 600 tokens, tirar `get_entity` primeiro e registrar. Confirmado: `server.py:589-767` registra as 33; `_ORDER_HINT` (131-135) cita `get_chunk`.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0157)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
