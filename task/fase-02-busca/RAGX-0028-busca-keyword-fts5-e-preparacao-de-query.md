# RAGX-0028 — Busca keyword FTS5 e preparação de query

| | |
|---|---|
| **Fase** | 2 — Semantic + Hybrid Search |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0014` |
| **Bloqueia** | `RAGX-0029` |
| **Documentação** | [05-busca.md](../../docs/05-busca.md) |
| **Status** | `todo` |

## Objetivo

Busca exata por símbolo e termo, com tratamento seguro do input do usuário.

## Entregáveis

- [ ] `search/keyword.py` com BM25 ponderado (`content=1.0`, `symbol=4.0`, `heading_path=2.0`)
- [ ] Escape de operadores FTS5 no input; sintaxe crua só com `--raw`
- [ ] Divisão de `CamelCase` e `snake_case` em termos adicionais
- [ ] `OR` entre termos com prefixo `*` no último

## Fora de escopo

- Fusão (RAGX-0029)

## Critérios de aceite

- [ ] `ragx search "AuthService" --mode keyword` traz o símbolo exato em primeiro lugar
- [ ] `auth service` encontra `AuthService`
- [ ] Aspas e operadores no input não quebram a query nem alteram a semântica sem `--raw`
- [ ] Busca acentuada casa com não acentuada

## Testes

- [ ] Fuzzing de input com caracteres especiais
- [ ] Casos de CamelCase/snake_case

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
