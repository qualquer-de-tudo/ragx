# RAGX-0112 — Confiança e procedência no resultado de busca

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 6 — confiança e evidência |
| **Prioridade** | P2 — media |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0101` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [09-mcp.md](../../docs/09-mcp.md) · [06-grafo.md](../../docs/06-grafo.md) |
| **Status** | `todo` |

## Objetivo

O resultado de busca devolve `score` e `matched_by`. Não há `confidence` nem marcação de evidência. O agente não consegue separar FATO (o código diz isto) de INFERÊNCIA (dois trechos parecidos, pode ser coincidência). O grafo já resolveu isso com `confidence` e `tier`; a busca não tem o equivalente.

## Entregáveis

- [ ] `confidence` no resultado de busca, derivado de sinais existentes (`matched_by`, concordância entre motores, match exato de símbolo)
- [ ] Marcação `evidence`: `exact` (o termo literal existe) | `semantic` (parecença) | `graph` (veio por relação)
- [ ] `_hit()` do MCP expõe os campos
- [ ] O playbook explica como o agente deve usá-los

## Fora de escopo

- Inventar confiança onde não há sinal — melhor ausente que fabricada

## Critérios de aceite

- [ ] Um resultado que casou nos dois motores tem confiança maior que um que casou em um só
- [ ] Um resultado só semântico é distinguível de um com match literal
- [ ] `confidence` ausente quando não há sinal, em vez de um valor inventado

## Testes

- [ ] Teste de contrato dos campos, nos dois transportes do plugin
- [ ] Teste de que concordância entre motores eleva a confiança

## Notas

O `matched_by` já é o melhor sinal existente e é honesto; esta tarefa o formaliza em vez de substituí-lo.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
