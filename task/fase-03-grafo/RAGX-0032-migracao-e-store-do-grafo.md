# RAGX-0032 — Migração e store do grafo

| | |
|---|---|
| **Fase** | 3 — Graph Knowledge |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0021` |
| **Bloqueia** | `RAGX-0033` |
| **Documentação** | [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) · [06-grafo.md](../../docs/06-grafo.md) |
| **Status** | `todo` |

## Objetivo

Persistir entidades e relações com identidade determinística e sem duplicata.

## Entregáveis

- [ ] `migrations/0004_graph.sql`: `entities`, `relations` e índices
- [ ] IDs determinísticos: `sha256(type + "\0" + qualified_name)` e `sha256(src + type + dst)`
- [ ] `graph/store.py` com upsert idempotente e cascade correto

## Fora de escopo

- Extração (RAGX-0033+)

## Critérios de aceite

- [ ] `UNIQUE(type, qualified_name)` e `UNIQUE(src, dst, type)` respeitados sob reindexação repetida
- [ ] Remover documento remove entidades estruturais e as relações que as referenciam
- [ ] Upsert repetido não duplica nem altera IDs

## Testes

- [ ] Integração de ciclo de vida completo

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
