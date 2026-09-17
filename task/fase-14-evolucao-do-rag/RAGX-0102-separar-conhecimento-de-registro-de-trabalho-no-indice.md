# RAGX-0102 — Separar conhecimento de registro de trabalho no índice

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 2 — composição do corpus |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | — |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [15-configuracao.md](../../docs/15-configuracao.md) |
| **Status** | `todo` |

## Objetivo

`task/` é **22% do corpus** (543 chunks, mais que toda a documentação) e vence o código na busca. Para *"como o security gate decide bloquear um arquivo"*, o fragmento [1] do `build_context` é o enunciado da TAREFA que pediu para construir o gate — não o `admit()`. Documento de planejamento é quase-duplicata semântica da documentação: mesmo vocabulário, menos informação.

## Entregáveis

- [ ] Coluna `tier` em `documents`: `knowledge` | `work` | `test`
- [ ] Classificação por caminho, configurável em `ragx.toml`:
  ```toml
  [index]
  knowledge_paths = ["src/", "docs/"]
  work_paths      = ["task/", "adr-drafts/"]
  test_paths      = ["tests/"]
  ```
- [ ] Defaults sensatos que funcionem sem configuração (`task/`, `tests/`, `spec/`, `.github/`)
- [ ] O ranking pondera `work` e `test` para BAIXO — sem excluir, porque às vezes a resposta está mesmo na tarefa
- [ ] O peso é configurável e o default fica registrado na documentação
- [ ] `matched_by`/metadados expõem o `tier`, para o agente saber o que recebeu
- [ ] Migração de schema, com reindexação não obrigatória (default aplicado na leitura)

## Fora de escopo

- Excluir `task/` do índice — a informação é legítima, o PESO é que está errado
- Classificação semântica do conteúdo; a classificação é por caminho, declarada e auditável

## Critérios de aceite

- [ ] Na consulta *"como o security gate decide bloquear um arquivo"*, o fragmento [1] passa a ser `src/ragx/security/gate.py`
- [ ] recall@5 medido antes/depois no conjunto ampliado (`RAGX-0099`), com o número publicado
- [ ] Um projeto sem `[index] tier` configurado continua funcionando, com os defaults
- [ ] Uma consulta cuja resposta REALMENTE está numa task ainda a encontra

## Testes

- [ ] Teste de que o peso muda a ordem, sem remover resultados
- [ ] Teste dos defaults de classificação
- [ ] Teste de que `tier` sobrevive a export/import (`.rag`)

## Notas

Este é o maior ganho de precisão por linha alterada de toda a fase, e não envolve modelo nem algoritmo.

Vale para qualquer projeto: todo repositório tem seu equivalente de `task/` — ADRs em rascunho, RFCs, tickets exportados, notas de sprint.

**Ironia registrada:** a própria Fase 14 acrescenta ~19 arquivos a `task/`, piorando o problema que esta tarefa corrige. Mais um motivo para ela vir cedo.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
