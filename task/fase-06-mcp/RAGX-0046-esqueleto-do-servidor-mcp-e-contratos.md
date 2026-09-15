# RAGX-0046 — Esqueleto do servidor MCP e contratos

| | |
|---|---|
| **Fase** | 6 — MCP |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0042`, `RAGX-0045` |
| **Bloqueia** | `RAGX-0047` |
| **Documentação** | [09-mcp.md](../../docs/09-mcp.md) · [adr/ADR-0006-mcp-casca-fina.md](../../docs/adr/ADR-0006-mcp-casca-fina.md) |
| **Status** | `todo` |

## Objetivo

Subir o servidor com os contratos tipados, sem nenhuma lógica de negócio dentro dele.

## Entregáveis

- [ ] `mcp/server.py` com o SDK oficial (FastMCP), transporte stdio
- [ ] `mcp/tools.py` com os modelos Pydantic de request/response do doc 09
- [ ] Envelope padronizado `{ok, data}` / `{ok, error:{code,message}}`
- [ ] Erro interno vira `code = "internal"`; detalhe vai só para `.ragx/logs/`
- [ ] Abertura do banco em modo somente leitura por padrão
- [ ] `ragx mcp serve` e `ragx mcp tools [--json]`

## Fora de escopo

- Implementação das ferramentas (RAGX-0047)

## Critérios de aceite

- [ ] Servidor sobe em menos de 1 s e lista as ferramentas
- [ ] Nenhum stack trace chega ao cliente
- [ ] Banco aberto em modo ro recusa escrita
- [ ] JSON Schema de cada ferramenta é exportável

## Testes

- [ ] Cliente MCP de teste conectando via stdio

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
