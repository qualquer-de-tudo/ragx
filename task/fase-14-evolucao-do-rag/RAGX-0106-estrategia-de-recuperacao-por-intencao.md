# RAGX-0106 — Estratégia de recuperação por intenção

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 4 — recuperação adaptativa |
| **Prioridade** | P1 — alta |
| **Estimativa** | 2d |
| **Depende de** | `RAGX-0099` · `RAGX-0101` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [07-context-engine.md](../../docs/07-context-engine.md) |
| **Status** | `todo` |

## Objetivo

A detecção de intenção existe (`context/intents.yaml`, 4 intenções por regex) mas só altera **pesos por `doc_kind`** e **`graph_depth`**. Não altera qual motor roda, quantos resultados buscar, nem se vale expandir pelo grafo. Uma pergunta de relacionamento e uma factual seguem o mesmo caminho.

## Entregáveis

- [ ] A intenção passa a escolher ESTRATÉGIA, não só peso:
  ```text
  FACTUAL / identificador   -> keyword primeiro; semântico só se vazio;  k=5
  CONCEITUAL / "como"       -> híbrido + reranking;                      k=8
  RELACIONAMENTO / "quem"   -> grafo primeiro, texto como apoio;         k=6
  ARQUITETURA / "por que"   -> hierárquico: resumo -> seção -> trecho
  DEPURACAO / stack trace   -> keyword exato no símbolo;                 k=10
  ```
- [ ] `looks_like_identifier()` e `looks_like_question()` (já em `ranking.py`) passam a decidir rota, não multiplicador
- [ ] Novas intenções: `relationship`, `debug`
- [ ] `--explain` mostra a estratégia escolhida, não só a intenção
- [ ] Estratégia sobrescrevível por parâmetro, para o agente forçar quando souber mais que a heurística

## Fora de escopo

- Classificação por LLM — a heurística declarada é auditável e não custa inferência
- Segunda busca automática quando a primeira falha (tarefa futura)

## Critérios de aceite

- [ ] Cada classe de consulta do conjunto ampliado melhora ou empata; nenhuma piora
- [ ] Consulta de identificador puro não paga mais o custo do braço semântico
- [ ] `--explain` permite auditar a decisão

## Testes

- [ ] Teste por classe de consulta, fixando a estratégia escolhida
- [ ] Teste de que a sobrescrita manual vence a heurística

## Notas

O ganho aqui é tanto de precisão quanto de custo: uma busca por identificador que não chama o braço semântico economiza a inferência inteira.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
