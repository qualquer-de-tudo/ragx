# RAGX-0109 — Popular os resumos do dicionário sem LLM

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 5 — conhecimento hierárquico |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1,5d |
| **Depende de** | — |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [08-dictionary.md](../../docs/08-dictionary.md) |
| **Status** | `todo` |

## Objetivo

`get_dictionary` é a primeira chamada que o playbook manda o agente fazer, custa **10.935 tokens** — e **0 de 144** itens têm `summary` preenchido. O campo que justificaria o custo está vazio porque só o caminho `--semantic` (que exige LLM) o preenche.

## Entregáveis

- [ ] Resumo extrativo, sem LLM, a partir do que já está no índice:
  - [ ] docstring de classe/módulo (o parser Python já a captura em `meta`)
  - [ ] primeiro parágrafo da seção, em Markdown
  - [ ] assinatura + primeira linha de docstring, em função
- [ ] `--semantic` continua existindo, e melhora o que o extrativo produziu
- [ ] `summary` nunca fica `null` quando há docstring disponível

## Fora de escopo

- Gerar resumo por LLM por padrão — custa dinheiro e não pode ser requisito
- Mudar o schema do `dictionary.json`

## Critérios de aceite

- [ ] **≥ 80%** de `services` e `modules` com `summary` preenchido, sem LLM
- [ ] O tamanho do dicionário não cresce: o resumo ENTRA e a lista de símbolos redundante SAI (ver `RAGX-0110`)
- [ ] `dictionary generate` continua determinístico

## Testes

- [ ] Teste de extração de docstring por tipo de nó
- [ ] Teste de que ausência de docstring não produz `summary` inventado

## Notas

A camada que deveria ser o Nível 0/1 do conhecimento hierárquico existe estruturalmente e está despovoada. O agente paga 11k tokens por um despejo de símbolos.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
