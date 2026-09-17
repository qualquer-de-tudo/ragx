# RAGX-0110 — Enxugar o dicionário

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 5 — conhecimento hierárquico |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0109` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [08-dictionary.md](../../docs/08-dictionary.md) |
| **Status** | `todo` |

## Objetivo

`services` é **45,8% do dicionário** (5.009 tokens) e lista classes como `UsageError` — uma exceção. `concepts` são **agrupamentos por prefixo de string**, não conceitos: `"counter": [HeuristicCounter, TiktokenCounter, TokenCounter, _Counter]`. `_Counter` é um contador privado dentro do chunker.

## Entregáveis

- [ ] Símbolos privados (`_nome`) saem de todas as seções
- [ ] `concepts` deixa de ser agrupamento por substring — ou vira agrupamento por relação do grafo, ou sai
- [ ] `services` passa a exigir evidência de ser serviço (ponto de entrada, rota, handler), não só "é uma classe"
- [ ] Exceções, DTOs e enums saem de `services`
- [ ] Ordenação por relevância (grau no grafo), não alfabética

## Fora de escopo

- Remover seções inteiras sem substituí-las — o objetivo é densidade, não corte cego

## Critérios de aceite

- [ ] Dicionário **≤ 4.000 tokens** com mais informação útil que os 10.935 de hoje
- [ ] Nenhum símbolo privado no `dictionary.json`
- [ ] Um agente que leia só o dicionário consegue dizer o que o projeto faz e onde ficam as três coisas principais

## Testes

- [ ] Teste de que nenhum símbolo começa com `_`
- [ ] Teste do teto de tokens do dicionário

## Notas

Vale medir antes e depois com um agente real: dar o dicionário novo e o antigo e comparar a qualidade da primeira resposta. É subjetivo, mas o token economizado não é.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
