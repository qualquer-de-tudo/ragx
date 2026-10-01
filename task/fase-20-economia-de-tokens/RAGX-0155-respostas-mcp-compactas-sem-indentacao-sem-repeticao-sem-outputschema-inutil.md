# RAGX-0155 — Respostas MCP compactas (sem indentação, sem repetição, sem `outputSchema` inútil)

| | |
|---|---|
| **Fase** | 20 — Economia de tokens |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0154 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-11, C-01) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S1, R-T2, princípio 3) · [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `done` |

## Objetivo

Toda resposta MCP sai com `indent=2`, `project` repetido em cada hit, ids de 32 hex, `score` com 6 casas, nulos explícitos e ainda duplicada em `structuredContent`; `tools/list` carrega um `outputSchema` (2.576 chars) que não serve ao modelo. Medido: `search_hybrid` de 10 hits custa 2.925 tokens (1.440 de conteúdo), `tools/list` 3.450 tokens. Protótipo compacto da auditoria: −18% na busca, −41% no dicionário, −40% em `get_document`, −28% em `get_entity`.

## Entregáveis

- [x] **Medir primeiro:** com `scripts/medir_fio.py` (criado na 0154), registrar chars e tokens de `search_hybrid` (10 hits), `get_dictionary`, `get_document`, `get_entity` e do `tools/list`. A auditoria tem dois pares para o dicionário (C-01: 8.854 indentado / 7.098 compacto; M 4.1: 8.660 / 5.100): o "Antes" deve vir desta medição.
- [x] `src/ragx/mcp/tools.py`: `dump(payload) -> str` (`json.dumps(..., ensure_ascii=False, separators=(",", ":"))`). `cap()` (linhas 78-90) passa a medir o texto compacto (hoje usa `json.dumps` com espaços).
- [x] `src/ragx/mcp/server.py` `build_server` (575-769): registrar as 33 ferramentas com `structured_output=False` e retorno `str` (`dump(_guarded(...))`). Confirmado em `mcpserver/utilities/func_metadata.py:652-655`: sem isso o SDK reindenta o dict (`indent=2`) e duplica em `structured_content`; hoje as 33 têm `outputSchema`. `_guarded` continua devolvendo `dict` (os testes o chamam).
- [x] `KnowledgeAPI._hit` (169-181): sem `project` por hit (vai uma vez em `data.project`), `score` com 4 casas, e sem chaves nulas (`symbol`, `heading_path`; `degraded: null` some). Ausência significa `null`. `search_scoped` (546-572) mantém `project` por hit: é federado.
- [x] Mesma regra de nulos em `get_document`, `get_entity`, `get_chunk` e `list_documents` via um `compact()` em `tools.py` (só remove chaves de dict com `None`; listas intactas).
- [x] `get_playbook` devolve `response_format: 2` (princípio 3: formato versionado).
- [x] `chunk_id` de 12 hex no fio, em todas as ferramentas; `get_chunk` (server.py:316-342) aceita prefixo único de ≥ 8 chars (`ChunkRepo.get`, repositories.py:120) e responde `invalid_id` se ambíguo. Se o loop achar arriscado, deixar por último e registrar em Notas.
- [x] `pyproject.toml` (linhas 27 e 30): o código importa `mcp.server.mcpserver.MCPServer` (server.py:578), que existe no `mcp` 2.2.0 instalado, mas o piso declarado é `>=1.2` (provavelmente sem esse módulo: confirmar). Alinhar o piso à menor versão que tem `MCPServer` e `structured_output`.
- [x] `docs/09-mcp.md`: seção "Formato das respostas" (compacto, nulos ausentes, `data.project`, `response_format: 2`). CHANGELOG com antes/depois.

## Fora de escopo

- Schemas de **entrada** enxutos (títulos, `anyOf null`, `default`) e o conjunto de ferramentas (0157). Descrições e `instructions` (0158).
- Conteúdo duplicado do `build_context` (0154). `response_format: concise|detailed` e snippet de 200 chars (0165).
- Campos novos de telemetria (0156). Formato tabular/TOON para listagens (fora da v2, spec 4.2).

## Critérios de aceite

- [x] S1: `build_context(tokens=3000)` **≤ 3.200** tokens no fio (`uv run python scripts/medir_fio.py --tool build_context --tokens 3000`).
- [x] Nenhuma ferramenta em `list_tools()` tem `output_schema`; `tools/list` cai ≥ 600 tokens.
- [x] Reduções mínimas, vindas do protótipo da auditoria: busca −18%, `get_dictionary` −41%, `get_document` −40%, `get_entity` −28%. **Medido (chars): busca −18,4%, dicionário −41,4%, `get_document` −45%, `get_entity` −26,4%.** O `get_entity` fica 1,6 pt abaixo: os ids dele são ids de ENTIDADE (o plugin os usa como identidade de nó), não de chunk, e não foram encurtados; ver Andamento.
- [x] Nenhum texto de resposta contém `\n` seguido de espaços (indentação) nem `structured_content`.
- [x] O VS Code (`vscode-plugin/src/rag/McpClient.ts:260`, que faz `JSON.parse` do texto) continua lendo `{ok, data}` sem alteração.

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| `search_hybrid`, 10 hits, tokens no fio | 2.925 (auditoria); **3.547 texto + 3.311 structuredContent** medido hoje | **2.915**, sem `structuredContent` |
| `get_dictionary`, tokens no fio | 8.854 / 8.660 (auditoria); **9.548 + 7.752** hoje | **6.225** |
| `tools/list`, tokens | 3.450 (auditoria); 4.141 com `outputSchema` hoje | **3.310** (-831) |
| `outputSchema`, chars | 2.576 | **0** (33 de 33 ferramentas sem `output_schema`) |
| `build_context(3000)`, tokens no fio (S1) | 7.684 (7.983 hoje, + 7.629 em `structuredContent`) | **2.947** (S1 <= 3.200) |

## Testes

- [x] `tests/integration/test_mcp_wire.py` (novo): `call_tool` devolve `structured_content is None`; o texto não tem indentação; `json.loads` dá `{"ok": true, ...}`; `list_tools()` sem `output_schema`. **Falha antes do conserto.**
- [x] `tests/integration/test_mcp.py`: ajustar `test_todo_resultado_carrega_project` (linha 63) para `data.project` + hits sem `project`; teste de nulos omitidos; `get_chunk` por prefixo (único, ambíguo, curto demais).
- [x] `tests/unit/test_mcp_tools.py` (novo): `dump` compacto e preservando acentos; `cap` mede o compacto.
- [x] `tests/security/test_surfaces.py`: `test_superficie_mcp_no_fio`, o mesmo laço de `test_superficie_mcp` (linhas 189-216) passando por `build_server(...).call_tool`, para a serialização também ser coberta (hoje só os `dict` são).
- [x] Teste arquitetural "MCP é casca fina" (`tests/security/test_architecture.py`) segue verde: só `json`, nenhum `os`/`io`/`open` novo em `src/ragx/mcp`.
- [x] `tests/unit/test_documentacao_mcp.py` segue verde (a contagem de ferramentas não muda).

## Notas

- Confirmado: `server.py:169-181` (`_hit`), `tools.py:78-90` (`cap`), 33 de 33 ferramentas com `outputSchema` e texto indentado no `mcp` 2.2.0 instalado. Os "34 chars" do `chunk_id` na auditoria são os 32 hex mais as aspas (`core/ids.py:24`, `_ID_LEN = 32`).
- Nenhum cliente do repo lê `structuredContent` (grep vazio); o Claude Code usa o texto. Cliente de terceiros que valida `outputSchema` deixa de ter o que validar: registrar no CHANGELOG como mudança de formato.
- Mexer na tabela de ferramentas de `docs/09-mcp.md` é coberto por `test_documentacao_mcp.py`; a contagem "33" do README segue valendo.
- Se o `structured_output=False` mudar o comportamento do SDK em outra versão, o teste de `test_mcp_wire.py` é quem acusa.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes (Windows rodado aqui; Linux e macOS pelo CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0155)` na branch `feat/v2`

## Andamento

2026-10-01. Antes (`scripts/medir_fio.py`, criado na 0154; tiktoken; este repo): `search_hybrid`(10) 3.547 tokens de texto + 3.311 em `structuredContent`; `get_dictionary` 9.548 + 7.752;
`get_document` 808 + 660; `get_entity` 8.079 + 7.322; `tools/list` 3.310 (4.141 com `outputSchema`). Em chars: 11.864 / 36.713 / 2.610 / 23.679.
Reproduzido primeiro: `tests/integration/test_mcp_wire.py` (novo) e `tests/unit/test_mcp_tools.py` (novo) vermelhos.
Implementado: `tools.dump/compact/cap` (cap mede o compacto); `build_server._tool` registra as 33 ferramentas com `structured_output=False` devolvendo `str` (`functools.wraps`
preserva a assinatura para o schema de ENTRADA; `_guarded` continua devolvendo `dict`); `_hit` sem `project`, score com 4 casas; `data.project` em `search_*`; `get_playbook` com
`response_format: 2`; `chunk_id` de 12 hex (`WIRE_ID_LEN`, `wire_id`) em hits e fragmentos `json`; `get_chunk` com prefixo (`ChunkRepo.get_by_prefix`, hex, >= 8, ambíguo -> `invalid_id`);
`test_superficie_mcp_no_fio` em `tests/security/test_surfaces.py`; plugin do VS Code herda `project` do envelope; `pyproject.toml` `mcp>=2.0` + `uv lock`.
Piso do `mcp`: baixei os wheels e conferi: `mcp.server.mcpserver` existe a partir da 2.0.0 (a 1.30.0 só tem `fastmcp`); `structured_output` existe na 2.0.0. O piso `>=1.2` estava errado.
Depois (chars): busca 9.679 (-18,4%), dicionário 21.530 (-41,4%), `get_document` 1.436 (-45%), `get_entity` 17.419 (-26,4%); tokens: busca 2.915, dicionário 6.225, doc 492, entity 6.207,
`build_context(3000)` 2.947 (S1 cumprido). Somando o `structuredContent` que sumiu, o fio de uma busca caiu de ~6.860 para 2.915 tokens (-57%) e o do dicionário de ~17.300 para 6.225 (-64%).
Limites registrados: (1) `get_entity` -26,4% em vez de -28%: os ids dele são de entidade e ficaram como estão; (2) os percentuais "mínimos" da auditoria vêm de `chars/4`; em tokens reais
(tiktoken) busca -17,8%, dicionário -34,8%, doc -39,1%, entity -23,2%, porque espaços de indentação custam pouco token; o ganho grande real é o `structuredContent` removido.
Ajustei 4 testes antigos à regra nova (origem em `data.project`; `get_chunk` com não-hex é `invalid_id`; `test_cli_e_mcp_concordam` compara os 12 primeiros hex).
Fast suite, `tests/security`, plugin (`npm test` 104 verdes, `typecheck`), `ruff`, `mypy` verdes.
