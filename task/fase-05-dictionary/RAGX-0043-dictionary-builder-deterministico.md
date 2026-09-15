# RAGX-0043 — Dictionary builder determinístico

| | |
|---|---|
| **Fase** | 5 — Knowledge Dictionary |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0034` |
| **Bloqueia** | `RAGX-0044`, `RAGX-0045` |
| **Documentação** | [08-dictionary.md](../../docs/08-dictionary.md) |
| **Status** | `todo` |

## Objetivo

Gerar o mapa barato do projeto sem depender de nenhum LLM.

## Entregáveis

- [ ] `dictionary/builder.py` cobrindo `technologies`, `services`, `modules`, `entrypoints`, `data_stores`, `conventions`, `docs`, `stats`
- [ ] `dictionary/schemas.py` com os modelos Pydantic e `schema_version`
- [ ] `evidence` obrigatório em todo item (lista de caminhos, nunca conteúdo)
- [ ] Detecção de convenção por padrão repetido (>= 3 ocorrências)
- [ ] Agregação automática quando a listagem exaustiva estouraria o limite de tamanho

## Fora de escopo

- `concepts`, `glossary` e `summaries` enriquecidos por LLM (RAGX-0044)

## Critérios de aceite

- [ ] Roda sem nenhum LLM configurado
- [ ] Todo item tem `evidence` não vazio
- [ ] `dictionary.json` completo <= 8.000 tokens em repositório de ~5k arquivos
- [ ] Variável de ambiente aparece por nome, valor nunca

## Testes

- [ ] Fixtures de projeto Laravel, Node e Python
- [ ] Validação contra o JSON Schema

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
