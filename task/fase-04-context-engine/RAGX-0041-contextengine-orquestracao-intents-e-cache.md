# RAGX-0041 — ContextEngine: orquestração, intents e cache

| | |
|---|---|
| **Fase** | 4 — Context Engine |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0040`, `RAGX-0035` |
| **Bloqueia** | `RAGX-0042`, `RAGX-0076` |
| **Documentação** | [07-context-engine.md](../../docs/07-context-engine.md) |
| **Status** | `todo` |

## Objetivo

Juntar as etapas no fluxo de 6 passos e produzir o `ContextPack`.

## Entregáveis

- [ ] `context/engine.py` com o fluxo busca → grafo → ranking → dedup → compressão → orçamento
- [ ] `context/intents.yaml` com os padrões léxicos das 4 intenções do doc 07
- [ ] Mistura de fontes ajustada pela intenção detectada
- [ ] `ContextPack` com `fragments`, `estimated_tokens`, `sources`, `dropped`, `stats`
- [ ] Cache por `sha256(query + budget + config_fingerprint + db_version)`, invalidado pelo `index_runs.id`
- [ ] Expansão de grafo opcional — o engine funciona sem a Fase 3

## Fora de escopo

- Formatação de saída (RAGX-0042)

## Critérios de aceite

- [ ] 10.000 tokens recuperados resultam em pack de no máximo 3.000, mantendo os trechos-chave
- [ ] Todo fragmento tem `document_path` e intervalo de linhas válidos
- [ ] Pelo menos 2 documentos distintos quando existem 2 relevantes
- [ ] Cache invalida corretamente após reindexação
- [ ] Pack de 3k tokens montado em menos de 1,5 s

## Testes

- [ ] Casos de avaliação com trechos-chave anotados
- [ ] Teste de invalidação de cache

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
