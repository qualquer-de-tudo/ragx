# RAGX-0049 — Testes arquiteturais e de segurança do MCP

| | |
|---|---|
| **Fase** | 6 — MCP |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0048` |
| **Bloqueia** | `RAGX-0050`, `RAGX-0077` |
| **Documentação** | [09-mcp.md](../../docs/09-mcp.md) · [13-testes-hardening.md](../../docs/13-testes-hardening.md) |
| **Status** | `todo` |

## Objetivo

Provar por teste — não por revisão de código — que a fronteira do MCP é real.

## Entregáveis

- [ ] Teste de import graph: `ragx.mcp` não importa `os`, `subprocess`, `pathlib`, `open`, `socket`, `requests`, `httpx`
- [ ] Teste das 8 ferramentas chamadas com cada segredo da fixture como query
- [ ] Teste das 8 ferramentas chamadas com o caminho de cada arquivo bloqueado
- [ ] Virar o `xfail` da superfície `mcp` em `pass`

## Fora de escopo

- Pentest externo

## Critérios de aceite

- [ ] Zero ocorrência de segredo em qualquer resposta de qualquer ferramenta
- [ ] Teste arquitetural falha se alguém adicionar um import proibido
- [ ] `get_document(".env")` devolve `not_found`, sem tocar no disco
- [ ] Superfície `mcp` sem `xfail`

## Testes

- [ ] A própria suíte é o entregável

## Notas

Porta de saída da Fase 6.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
