# RAGX-0048 — Limites, rate limiting e logging com hash de query

| | |
|---|---|
| **Fase** | 6 — MCP |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0047` |
| **Bloqueia** | `RAGX-0049` |
| **Documentação** | [09-mcp.md](../../docs/09-mcp.md) |
| **Status** | `todo` |

## Objetivo

Proteger contra loop de agente e evitar que o log vire cópia do que o time pergunta sobre o próprio código.

## Entregáveis

- [ ] Limites do doc 09: `limit <= 50`, `tokens <= 32000`, resposta <= 1 MiB, 60 chamadas/min
- [ ] Validação de `path_glob` (sem `..`, sem caminho absoluto)
- [ ] `.ragx/logs/mcp.jsonl` com `query_hash`; texto só com `mcp.log_queries = true`
- [ ] Retenção de log por `log.retain_days`

## Fora de escopo

- Autenticação — não há multiusuário no MVP

## Critérios de aceite

- [ ] Estouro de limite devolve erro claro, não resposta truncada silenciosamente
- [ ] Rate limit ativa e se recupera corretamente
- [ ] Log não contém texto de query com a configuração padrão
- [ ] Resposta acima de 1 MiB é recusada com orientação de paginar

## Testes

- [ ] Teste de rate limit
- [ ] Teste de que o log não vaza query

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
