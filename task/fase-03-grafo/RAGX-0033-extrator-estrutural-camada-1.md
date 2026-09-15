# RAGX-0033 — Extrator estrutural (camada 1)

| | |
|---|---|
| **Fase** | 3 — Graph Knowledge |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0032` |
| **Bloqueia** | `RAGX-0034` |
| **Documentação** | [06-grafo.md](../../docs/06-grafo.md) |
| **Status** | `todo` |

## Objetivo

Aproveitar o `ParseResult` já produzido na Fase 1 para construir o esqueleto do grafo a custo praticamente zero.

## Entregáveis

- [ ] `graph/extractors/structural.py`: `contains`, `imports`, `extends`, `implements`
- [ ] Entidades `file`, `class`, `function`, `method` ancoradas em `document_id`/`chunk_id`
- [ ] `source = "structural"`, `confidence = 1.0`

## Fora de escopo

- Qualquer uso de LLM

## Critérios de aceite

- [ ] Hierarquia arquivo → classe → método reproduz a estrutura real do código
- [ ] Extração de repositório de 5.000 arquivos em menos de 10 s
- [ ] Nenhuma entidade sem âncora em documento

## Testes

- [ ] Fixture por linguagem, comparando com a estrutura esperada

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
