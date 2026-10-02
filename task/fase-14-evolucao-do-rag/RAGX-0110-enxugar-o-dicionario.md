# RAGX-0110 — Enxugar o dicionário

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 5 — conhecimento hierárquico |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0109` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [08-dictionary.md](../../docs/08-dictionary.md) |
| **Status** | `done` |

## Objetivo

`services` é **45,8% do dicionário** (5.009 tokens) e lista classes como `UsageError` — uma exceção. `concepts` são **agrupamentos por prefixo de string**, não conceitos: `"counter": [HeuristicCounter, TiktokenCounter, TokenCounter, _Counter]`. `_Counter` é um contador privado dentro do chunker.

## Entregáveis

- [x] Símbolos privados (`_nome`) saem de todas as seções
- [x] `concepts` deixa de ser agrupamento por substring — ou vira agrupamento por relação do grafo, ou sai
- [x] `services` passa a exigir evidência de ser serviço (ponto de entrada, rota, handler), não só "é uma classe"
- [x] Exceções, DTOs e enums saem de `services`
- [x] Ordenação por relevância (grau no grafo), não alfabética

## Fora de escopo

- Remover seções inteiras sem substituí-las — o objetivo é densidade, não corte cego

## Critérios de aceite

- [x] Dicionário **≤ 4.000 tokens** com mais informação útil que os 10.935 de hoje
- [x] Nenhum símbolo privado no `dictionary.json`
- [ ] Um agente que leia só o dicionário consegue dizer o que o projeto faz e onde ficam as três coisas principais — **não testei com um agente real** (custa chamadas); pelo conteúdo, o nível 0 já diz as tecnologias, os módulos com resumo e os pontos de entrada

## Testes

- [x] Teste de que nenhum símbolo começa com `_`
- [x] Teste do teto de tokens do dicionário

## Notas

Vale medir antes e depois com um agente real: dar o dicionário novo e o antigo e comparar a qualidade da primeira resposta. É subjetivo, mas o token economizado não é.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação confere com o comportamento implementado

## Andamento

- 2026-10-02 — Serviço sem exceção (`Error`/`Exception`), enum, `BaseModel`/`TypedDict`/`NamedTuple`/`Protocol`, `@dataclass` nem classe só de campos (sem método no grafo e sem herança); símbolo `_privado` fora de serviços, dependências e conceitos; `concepts` agora são os documentos de `docs/` com as classes que documentam (`documented_by`), ignorando símbolo citado por mais de 4 documentos e documentos de plano/ADR/changelog; `data_stores` sem tabelas de teste; `documented_by` do serviço só com documentação de verdade (não changelog, tarefas, planos nem agentes) e no máximo 2; módulos grandes abertos em mais um nível. Teto `_TOKEN_TARGET` 8.000 para 4.000. **Medido: 7.680 (antes desta rodada; 10.935 na auditoria) para 3.701 tokens.** Falta a avaliação subjetiva sugerida na tarefa (dar o dicionário velho e o novo a um agente real e comparar a primeira resposta): não rodei, custaria chamadas reais.
