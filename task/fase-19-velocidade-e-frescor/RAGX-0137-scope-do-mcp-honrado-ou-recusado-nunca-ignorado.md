# RAGX-0137 — `scope` do MCP honrado ou recusado, nunca ignorado

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (C-05) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V8) · [09-mcp.md](../../docs/09-mcp.md) · [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) |
| **Status** | `done` |

## Objetivo

`search_knowledge`, `search_hybrid` e `build_context` aceitam `scope` (`current|all|project:<nome>`) e o ignoram: `KnowledgeAPI.search` (`mcp/server.py:184-210`) e `KnowledgeAPI.build_context` (`421-453`) nunca olham `req.scope`, e `search_scoped` (`546-572`) existe e não é chamado por nada. Efeito medido: `scope="all"` consulta só o projeto atual e o agente acredita que consultou o conjunto. O hint de pasta-pai (`clients/claude_hint.py:278-287`) manda justamente usar `scope="project:<nome>"`, com `build_context`, a partir de uma pasta sem índice próprio.

## Entregáveis

- [x] **Reproduzir primeiro:** com hub de dois projetos (fixture de `tests/integration/test_federation.py`), `KnowledgeAPI.search(SearchRequest(query=..., scope="all"), "hybrid")` só devolve hits do projeto atual. Teste vermelho.
- [x] `KnowledgeAPI.search`: com `scope != "current"` delega a `search_scoped` (mesmo `_guard`). `search_scoped` passa a repassar `path_glob` validado (`validate_path`) em `SearchFilters`, que hoje só leva `lang` e `kind` (linha 558). A resposta ganha `scope` e `projects`; cada hit já carrega `project`.
- [x] Projeto `project:<nome>` inexistente **ou privado** devolve o mesmo `err("not_found", ...)`, indistinguíveis de propósito (ver `federation/search.py:70-73`); `scope="all"` sem hub devolve o erro que `raise_no_hub` já produz (`invalid_scope`).
- [x] `KnowledgeAPI.build_context` com `scope="project:<nome>"`: serviço novo `build_scoped_context` em `src/ragx/federation/` que resolve o projeto no hub (regras de visibilidade e `db_path` de `_search_cloned`, `search.py:113-126`) e roda `context.engine.build_context` com a `Config` dele. O servidor continua só validando e serializando. Com `scope="all"`: `err("scope_unsupported", "build_context só combina um projeto por vez; use project:<nome> ou search_hybrid(scope=\"all\")")`, porque pesos de modelos de embedding diferentes não se combinam.
- [x] Teste genérico: para toda ferramenta registrada em `build_server` que declara o parâmetro `scope`, chamar com `scope="all"` sem hub e afirmar que a resposta **não** é um resultado do projeto atual (erro explícito ou resultado marcado com `scope`).
- [x] Documentação: `docs/09-mcp.md` (linha 116 e 247) e `docs/17-multiprojeto-e-federacao.md`. A tabela da linha 319-320 afirma `scope` em `search_graph` e `get_dictionary`, e a linha 224 mostra `ragx context ... --scope all`; **nenhum dos três existe no código** (conferido em `server.py:595,649` e `cli/commands/context_cmd.py`). Corrigir o documento, não implementar.
- [x] CHANGELOG.

## Fora de escopo

- Reduzir o conjunto de ferramentas e decidir se `scope` permanece nos schemas enxutos: RAGX-0157. Reescrever o hint: RAGX-0164.
- `build_context` federado com `all` (mistura de modelos): decidido recusar.
- `search_graph`/`get_dictionary` multiprojeto e `ragx context --scope` na CLI.
- Isolamento do hub em si (RAGX-0078, já entregue): esta tarefa só **não pode regredir** nele.

## Critérios de aceite

- [x] `search_hybrid(scope="all")` com dois projetos clonados devolve hits de ambos, cada um com `project` correto; `scope="project:x"` restringe a `x`; `scope="current"` não cruza.
- [x] `build_context(scope="project:x")` devolve pack montado a partir do projeto `x`; `scope="all"` devolve `scope_unsupported`.
- [x] Projeto `visibility = "private"` é invisível em `all` e em `project:<nome>` explícito, e a mensagem é igual à de projeto inexistente.
- [x] Nenhuma ferramenta registrada aceita `scope` e o descarta (teste genérico acima).
- [x] O servidor MCP continua sem importar `os`/`pathlib`/`subprocess` (`tests/security/test_architecture.py`).

## Testes

- [x] `tests/integration/test_mcp.py`: `scope="all"` e `scope="project:x"` por `KnowledgeAPI.search` (falha antes); `build_context` com os dois escopos; `path_glob` respeitado em `scope="all"`.
- [x] `tests/integration/test_federation.py`: `build_scoped_context` com projeto clonado, não clonado (só federação: contratos, sem `build_context`: devolver `scope_unsupported` com o motivo) e privado.
- [x] `tests/security/test_scope_mcp.py` (novo): projeto privado nunca aparece por `search_hybrid`, `search_knowledge` nem `build_context`, em nenhum `scope`; resposta de `project:<privado>` é byte a byte a de `project:<inexistente>`; nenhum segredo da fixture sai por `scope="all"`.
- [x] `tests/integration/test_mcp.py`: `test_scope_invalido_e_rejeitado` (linha 218) continua verde.
- [x] Teste do hint de pasta-pai (`tests/unit/test_claude_profiles_hint.py`): a instrução que ele gera funciona com a regra nova.

## Notas

- Confirmado em `server.py:184-210`, `421-453`, `546-572`, `599-625` e `655-668`, e `grep search_scoped src/ragx` (só a definição, a CLI em `search_cmd.py:42` e `federation/search.py`).
- `_hit` (`server.py:169-181`) sempre escreve `project: self.project`; `search_scoped` sobrescreve com `r.project` (linha 568). Manter essa ordem.
- Segurança: a regra de que privado e inexistente são indistinguíveis vale para a **mensagem de erro e o tempo** (não consultar o banco do privado antes de recusar). `_search_cloned` já relê a visibilidade ao vivo do `ragx.toml` do outro projeto porque o hub pode estar velho; reaproveitar.
- Windows: `p["path"]` do hub pode vir com `\`; `load_config` aceita. Não concatenar à mão.
- Se `build_scoped_context` crescer (cache por projeto, modelo diferente por projeto), parar e abrir tarefa: o mínimo aceitável é `project:<nome>` com a config do outro projeto e recusa de `all`.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes (Windows rodado aqui; Linux e macOS pelo CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0137)` na branch `feat/v2`

## Andamento

2026-10-01. Reproduzido primeiro: 9 testes vermelhos em `tests/security/test_scope_mcp.py` (novo, 12 testes): `scope="all"` só devolvia
o projeto atual; `build_context` ignorava `scope`; `project:<privado>` e `project:<inexistente>` não davam erro. Implementado:
`KnowledgeAPI.search` delega a `_search_scoped` quando `scope != "current"` (um só `_guard`, sem consumir o limite duas vezes) e valida
`path_glob` antes; `ScopedOutcome.found` (False para projeto privado ou inexistente) vira `err("not_found", ...)` com a mesma mensagem nos dois
casos; `federation/context.py` (novo) com `build_scoped_context`, `ScopeNotFoundError` e `ScopeUnsupportedError` (nomes com sufixo `Error` por
causa do ruff N818); `KnowledgeAPI.build_context` mapeia para `not_found` / `scope_unsupported` / `invalid_scope`, usa o nome do outro projeto
em `project` e nos fragmentos, e calcula o `baseline_tokens` no banco DELE (antes usaria o do projeto atual e daria número errado).
O teste genérico `test_nenhuma_ferramenta_aceita_scope_e_o_descarta` lê o schema real das ferramentas registradas e falha se aparecer uma
ferramenta nova com `scope` sem resposta de teste correspondente. Nesta versão do SDK `mcp` o atributo é `input_schema` (não `inputSchema`).
Docs corrigidos: `09-mcp.md` (tabela do que cada ferramenta faz com `scope`) e `17-multiprojeto-e-federacao.md` (prometiam `scope` em
`search_graph`, `get_dictionary` e `ragx context --scope all`; nunca existiram). O teste arquitetural do servidor MCP (sem `os`/`pathlib`/
`subprocess`) segue verde. Fast suite, `tests/security`, `ruff`, `mypy` verdes. Não medi tempo: é correção de comportamento.
