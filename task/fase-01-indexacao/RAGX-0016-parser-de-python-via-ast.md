# RAGX-0016 — Parser de Python via ast

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0012` |
| **Bloqueia** | `RAGX-0017`, `RAGX-0019` |
| **Documentação** | [04-indexacao.md](../../docs/04-indexacao.md) |
| **Status** | `todo` |

## Objetivo

Extrair estrutura de código Python com precisão total e zero dependência.

## Entregáveis

- [ ] `indexing/parsers/python.py` usando `ast` da stdlib
- [ ] Nós para módulo, classe, função, método, incluindo `async def`
- [ ] Metadados: decorators, docstring, bases, imports do módulo
- [ ] Linhas exatas via `lineno`/`end_lineno`
- [ ] `SyntaxError` → `ParseError` (degrada para fallback, não derruba a indexação)

## Fora de escopo

- Resolução de imports entre arquivos (RAGX-0034)

## Critérios de aceite

- [ ] Classe aninhada e função aninhada geram hierarquia correta
- [ ] Decorator é atribuído à função certa e não vira nó solto
- [ ] Arquivo com erro de sintaxe degrada para fallback e registra `parse_degraded`
- [ ] Intervalo de linhas inclui decorators

## Testes

- [ ] Parser aplicado ao próprio `src/ragx/` como fixture viva

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
