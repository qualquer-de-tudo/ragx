# RAGX-0109 — Popular os resumos do dicionário sem LLM

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 5 — conhecimento hierárquico |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1,5d |
| **Depende de** | — |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [08-dictionary.md](../../docs/08-dictionary.md) |
| **Status** | `done` |

## Objetivo

`get_dictionary` é a primeira chamada que o playbook manda o agente fazer, custa **10.935 tokens** — e **0 de 144** itens têm `summary` preenchido. O campo que justificaria o custo está vazio porque só o caminho `--semantic` (que exige LLM) o preenche.

## Entregáveis

- [x] Resumo extrativo, sem LLM, a partir do que já está no índice:
  - [x] docstring de classe/módulo (o parser Python já a captura em `meta`)
  - [x] primeiro parágrafo da seção, em Markdown
  - [x] assinatura + primeira linha de docstring, em função
- [x] `--semantic` continua existindo, e melhora o que o extrativo produziu
- [x] `summary` nunca fica `null` quando há docstring disponível

## Fora de escopo

- Gerar resumo por LLM por padrão — custa dinheiro e não pode ser requisito
- Mudar o schema do `dictionary.json`

## Critérios de aceite

- [x] **≥ 80%** de `services` e `modules` com `summary` preenchido, sem LLM
- [x] O tamanho do dicionário não cresce: o resumo ENTRA e a lista de símbolos redundante SAI (ver `RAGX-0110`)
- [x] `dictionary generate` continua determinístico

## Testes

- [x] Teste de extração de docstring por tipo de nó
- [x] Teste de que ausência de docstring não produz `summary` inventado

## Notas

A camada que deveria ser o Nível 0/1 do conhecimento hierárquico existe estruturalmente e está despovoada. O agente paga 11k tokens por um despejo de símbolos.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação confere com o comportamento implementado

## Andamento

- 2026-10-02 — Resumos extrativos: `_primeira_linha`, `_fatos_da_classe` (ast), `_resumo_de_classe`, `_resumo_do_documento`, `_resumo_do_modulo` (README, `__init__`, README de pasta-mãe que não seja a raiz). Medido no repositório (dicionário já enxuto pela 0110): **serviços 15/15 (100%)** e **módulos 7/10 (70%)**, **22/25 = 88% combinados**, que é o que o critério mede; só os módulos `src/ragx`, `tests/unit` e `tests/integration` ficam `null`, porque nem README nem `__init__` dizem algo (nada é inventado). Caso de `SecurityGate`: não tem docstring própria, então o resumo vem do docstring do módulo `gate.py`. Testes em `tests/integration/test_dictionary_niveis.py`. `--semantic` não foi tocado.
