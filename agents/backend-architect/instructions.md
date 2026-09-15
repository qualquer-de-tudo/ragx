# backend-architect

Desenho e implementação de serviços backend neste projeto.

## Como se orientar neste projeto

Você tem acesso ao conhecimento indexado via MCP. **Não peça "me explique o
projeto"** — isso é caro e impreciso. Em vez disso:

1. `get_dictionary` — tecnologias, serviços, módulos e convenções (barato).
2. `search_hybrid` — localize o que interessa.
3. `build_context` — monte o contexto da tarefa dentro de um orçamento.
4. `get_chunk` — aprofunde em um trecho específico.

### Serviços neste escopo

- **Config** — `src/ragx/config.py`
- **ChunkKind** — `src/ragx/core/models.py`
- **Budget** — `src/ragx/sizing/budget.py`
- **Chunk** — `src/ragx/core/models.py`
- **GraphStore** — `src/ragx/graph/store.py`
- **ParseNode** — `src/ragx/core/models.py`
- **SearchFilters** — `src/ragx/search/service.py`
- **SearchRequest** — `src/ragx/mcp/tools.py`
- **Severity** — `src/ragx/core/models.py`
- **UsageError** — `src/ragx/core/errors.py`

## Escopo

- `**`

## Regras

- `rules/architecture.md`
- `rules/coding-standards.md`
- `rules/security.md`

## Skills disponíveis

- `exemplo.md` — Skill de exemplo

## O que este projeto usa

NumPy, Pydantic, Rich, Typer, pytest, SQLite

---

*Perfil gerado por `rag agent train`. Arquivos em `rules/` e `skills/` editados
à mão são preservados no retreino.*
