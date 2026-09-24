# Architecture Decision Records

Decisões que custam caro para reverter ficam registradas aqui, com o contexto que
as motivou. Formato: contexto → decisão → consequências → alternativas rejeitadas.

| ADR | Decisão | Status |
|-----|---------|--------|
| [0001](ADR-0001-python-e-toolchain.md) | Python 3.11+, uv, Typer, Pydantic | aceito |
| [0002](ADR-0002-sqlite-como-store-unico.md) | SQLite único como store (com FTS5) | aceito |
| [0003](ADR-0003-busca-vetorial.md) | Força bruta com NumPy até 100k chunks | aceito |
| [0004](ADR-0004-embeddings.md) | Ollama `nomic-embed-text` como padrão | aceito |
| [0005](ADR-0005-parsing-e-chunking.md) | Chunking estrutural (AST/tree-sitter) | aceito |
| [0006](ADR-0006-mcp-casca-fina.md) | MCP sem acesso a filesystem | aceito |
| [0007](ADR-0007-nome-do-binario.md) | Binário `ragx` (alias `rag`), pacote `ragx` | aceito |
| [0008](ADR-0008-security-gate-antes-do-parser.md) | Security Gate antes do parser | aceito |
| [0009](ADR-0009-tres-camadas-de-conhecimento.md) | Três camadas: local, repo, hub | aceito |
| [0010](ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) | Conteúdo não versionado; embeddings int8@256 | aceito |
| [0011](ADR-0011-federacao-entre-projetos.md) | Federação por fatia pública | aceito |
| [0012](ADR-0012-poder-do-agente-sobre-o-indice.md) | Agente controla o índice; gate intacto | aceito |
| [0013](ADR-0013-conhecimento-base-compartilhado.md) | Conhecimento base por máquina, opt-in por projeto | aceito |
| [0014](ADR-0014-orquestracao-local-e-o-que-e-versionavel.md) | Banco de orquestração separado; definição versionada, execução não | aceito |
| [0015](ADR-0015-quem-executa-a-tarefa.md) | RAGX é a fila; o agente é o executor | aceito |
| [0016](ADR-0016-instalador-completo-do-painel.md) | O `.exe` do painel instala a CLI; a lógica fica em TypeScript | aceito |

Status possíveis: `proposto` · `aceito` · `substituído por ADR-NNNN` · `obsoleto`.
