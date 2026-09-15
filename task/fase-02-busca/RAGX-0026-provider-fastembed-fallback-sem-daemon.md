# RAGX-0026 — Provider fastembed (fallback sem daemon)

| | |
|---|---|
| **Fase** | 2 — Semantic + Hybrid Search |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,25d |
| **Depende de** | `RAGX-0024` |
| **Bloqueia** | — |
| **Documentação** | [adr/ADR-0004-embeddings.md](../../docs/adr/ADR-0004-embeddings.md) |
| **Status** | `todo` |

## Objetivo

Permitir embeddings em CI e em máquinas sem Ollama.

## Entregáveis

- [ ] `embeddings/fastembed.py` com `BAAI/bge-small-en-v1.5` (384d)
- [ ] Dependência opcional (`extras = ["fastembed"]`), com erro acionável se ausente
- [ ] Download do modelo cacheado em `.ragx/cache/models/`

## Fora de escopo

- Paridade de qualidade com o provider padrão

## Critérios de aceite

- [ ] Funciona offline após o primeiro download
- [ ] Troca de provider dispara o fluxo de migração de vetores do doc 15
- [ ] CI usa este provider sem precisar de daemon

## Testes

- [ ] Integração marcada como lenta, executada só no job noturno

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
