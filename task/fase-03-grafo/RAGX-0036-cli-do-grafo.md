# RAGX-0036 — CLI do grafo

| | |
|---|---|
| **Fase** | 3 — Graph Knowledge |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0035` |
| **Bloqueia** | `RAGX-0037` |
| **Documentação** | [06-grafo.md](../../docs/06-grafo.md) · [14-cli.md](../../docs/14-cli.md) |
| **Status** | `todo` |

## Objetivo

Expor inspeção e reconstrução do grafo.

## Entregáveis

- [ ] `ragx entities [--type --name --limit]`
- [ ] `ragx graph show <entidade> [--depth --relations --json]` com a saída do doc 06
- [ ] `ragx graph-search "<query>" [--depth --limit]`
- [ ] `ragx graph rebuild [--layers 1,2] [--semantic]`

## Fora de escopo

- Visualização gráfica

## Critérios de aceite

- [ ] `ragx graph rebuild` reconstrói as camadas 1-2 do zero em segundos, sem órfão e sem duplicata
- [ ] Saída de `ragx graph` reproduz o formato do doc 06, com direção das arestas explícita
- [ ] Entidade inexistente produz mensagem útil com sugestões próximas

## Testes

- [ ] E2E de reconstrução e consulta

## Notas

Porta de saída da Fase 3, junto com RAGX-0035.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
