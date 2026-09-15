# RAGX-0018 — Parsers de JSON, YAML, XML e SQL

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0012` |
| **Bloqueia** | — |
| **Documentação** | [04-indexacao.md](../../docs/04-indexacao.md) |
| **Status** | `todo` |

## Objetivo

Cobrir configuração e dados estruturados, que é onde mora boa parte do conhecimento de infraestrutura — e boa parte do risco de segredo.

## Entregáveis

- [ ] JSON: nós por chave de topo, com JSONPath no `symbol`
- [ ] YAML via `ruamel.yaml`, com suporte a múltiplos documentos (`---`)
- [ ] XML via `lxml`, nós por elemento de topo
- [ ] SQL via `sqlparse`, nós por statement, com destaque para `CREATE TABLE`

## Fora de escopo

- Interpretação semântica do conteúdo (fica no grafo, RAGX-0034)

## Critérios de aceite

- [ ] `composer.json`/`package.json` reais são parseados
- [ ] YAML multi-documento gera nós separados
- [ ] `CREATE TABLE` produz nó com o nome da tabela em `symbol`
- [ ] Arquivo inválido degrada para fallback sem exceção

## Testes

- [ ] Fixtures de configuração real (docker-compose, CI, manifests)

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
