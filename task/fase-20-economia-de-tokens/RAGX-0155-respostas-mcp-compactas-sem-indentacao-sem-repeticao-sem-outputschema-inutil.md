# RAGX-0155 — Respostas MCP compactas (sem indentação, sem repetição, sem `outputSchema` inútil)

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0154 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-11, C-01) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S1, R-T2, princípio 3) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `todo` |

## Objetivo

Toda resposta MCP sai com `indent=2`, `project` repetido em cada hit, ids de 32 hex, `score` com 6 casas, nulos explícitos e ainda duplicada em `structuredContent`; `tools/list` carrega um `outputSchema` (2.576 chars) que não serve ao modelo. Medido: `search_hybrid` de 10 hits custa 2.925 tokens (1.440 de conteúdo), `tools/list` 3.450 tokens. Protótipo compacto da auditoria: −18% na busca, −41% no dicionário, −40% em `get_document`, −28% em `get_entity`.

## Entregáveis

- [ ] **Medir primeiro:** com `scripts/medir_fio.py` (criado na 0154), registrar chars e tokens de `search_hybrid` (10 hits), `get_dictionary`, `get_document`, `get_entity` e do `tools/list`. A auditoria tem dois pares para o dicionário (C-01: 8.854 indentado / 7.098 compacto; M 4.1: 8.660 / 5.100): o "Antes" deve vir desta medição.
- [ ] `src/ragx/mcp/tools.py`: `dump(payload) -> str` (`json.dumps(..., ensure_ascii=False, separators=(",", ":"))`). `cap()` (linhas 78-90) passa a medir o texto compacto (hoje usa `json.dumps` com espaços).
- [ ] `src/ragx/mcp/server.py` `build_server` (575-769): registrar as 33 ferramentas com `structured_output=False` e retorno `str` (`dump(_guarded(...))`). Confirmado em `mcpserver/utilities/func_metadata.py:652-655`: sem isso o SDK reindenta o dict (`indent=2`) e duplica em `structured_content`; hoje as 33 têm `outputSchema`. `_guarded` continua devolvendo `dict` (os testes o chamam).
- [ ] `KnowledgeAPI._hit` (169-181): sem `project` por hit (vai uma vez em `data.project`), `score` com 4 casas, e sem chaves nulas (`symbol`, `heading_path`; `degraded: null` some). Ausência significa `null`. `search_scoped` (546-572) mantém `project` por hit: é federado.
- [ ] Mesma regra de nulos em `get_document`, `get_entity`, `get_chunk` e `list_documents` via um `compact()` em `tools.py` (só remove chaves de dict com `None`; listas intactas).
- [ ] `get_playbook` devolve `response_format: 2` (princípio 3: formato versionado).
- [ ] `chunk_id` de 12 hex no fio, em todas as ferramentas; `get_chunk` (server.py:316-342) aceita prefixo único de ≥ 8 chars (`ChunkRepo.get`, repositories.py:120) e responde `invalid_id` se ambíguo. Se o loop achar arriscado, deixar por último e registrar em Notas.
- [ ] `pyproject.toml` (linhas 27 e 30): o código importa `mcp.server.mcpserver.MCPServer` (server.py:578), que existe no `mcp` 2.2.0 instalado, mas o piso declarado é `>=1.2` (provavelmente sem esse módulo: confirmar). Alinhar o piso à menor versão que tem `MCPServer` e `structured_output`.
- [ ] `docs/09-mcp.md`: seção "Formato das respostas" (compacto, nulos ausentes, `data.project`, `response_format: 2`). CHANGELOG com antes/depois.

## Fora de escopo

- Schemas de **entrada** enxutos (títulos, `anyOf null`, `default`) e o conjunto de ferramentas (0157). Descrições e `instructions` (0158).
- Conteúdo duplicado do `build_context` (0154). `response_format: concise|detailed` e snippet de 200 chars (0165).
- Campos novos de telemetria (0156). Formato tabular/TOON para listagens (fora da v2, spec 4.2).

## Critérios de aceite

- [ ] S1: `build_context(tokens=3000)` **≤ 3.200** tokens no fio (`uv run python scripts/medir_fio.py --tool build_context --tokens 3000`).
- [ ] Nenhuma ferramenta em `list_tools()` tem `output_schema`; `tools/list` cai ≥ 600 tokens.
- [ ] Reduções mínimas, vindas do protótipo da auditoria: busca −18%, `get_dictionary` −41%, `get_document` −40%, `get_entity` −28%.
- [ ] Nenhum texto de resposta contém `\n` seguido de espaços (indentação) nem `structured_content`.
- [ ] O VS Code (`vscode-plugin/src/rag/McpClient.ts:260`, que faz `JSON.parse` do texto) continua lendo `{ok, data}` sem alteração.

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| `search_hybrid`, 10 hits, tokens no fio | 2.925 (1.440 de conteúdo) | |
| `get_dictionary`, tokens no fio | 8.854 / 8.660 (C-01 / M 4.1) | |
| `tools/list`, tokens | 3.450 | |
| `outputSchema`, chars | 2.576 | |
| `build_context(3000)`, tokens no fio (S1) | 7.684 | |

## Testes

- [ ] `tests/integration/test_mcp_wire.py` (novo): `call_tool` devolve `structured_content is None`; o texto não tem indentação; `json.loads` dá `{"ok": true, ...}`; `list_tools()` sem `output_schema`. **Falha antes do conserto.**
- [ ] `tests/integration/test_mcp.py`: ajustar `test_todo_resultado_carrega_project` (linha 63) para `data.project` + hits sem `project`; teste de nulos omitidos; `get_chunk` por prefixo (único, ambíguo, curto demais).
- [ ] `tests/unit/test_mcp_tools.py` (novo): `dump` compacto e preservando acentos; `cap` mede o compacto.
- [ ] `tests/security/test_surfaces.py`: `test_superficie_mcp_no_fio`, o mesmo laço de `test_superficie_mcp` (linhas 189-216) passando por `build_server(...).call_tool`, para a serialização também ser coberta (hoje só os `dict` são).
- [ ] Teste arquitetural "MCP é casca fina" (`tests/security/test_architecture.py`) segue verde: só `json`, nenhum `os`/`io`/`open` novo em `src/ragx/mcp`.
- [ ] `tests/unit/test_documentacao_mcp.py` segue verde (a contagem de ferramentas não muda).

## Notas

- Confirmado: `server.py:169-181` (`_hit`), `tools.py:78-90` (`cap`), 33 de 33 ferramentas com `outputSchema` e texto indentado no `mcp` 2.2.0 instalado. Os "34 chars" do `chunk_id` na auditoria são os 32 hex mais as aspas (`core/ids.py:24`, `_ID_LEN = 32`).
- Nenhum cliente do repo lê `structuredContent` (grep vazio); o Claude Code usa o texto. Cliente de terceiros que valida `outputSchema` deixa de ter o que validar: registrar no CHANGELOG como mudança de formato.
- Mexer na tabela de ferramentas de `docs/09-mcp.md` é coberto por `test_documentacao_mcp.py`; a contagem "33" do README segue valendo.
- Se o `structured_output=False` mudar o comportamento do SDK em outra versão, o teste de `test_mcp_wire.py` é quem acusa.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0155)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
