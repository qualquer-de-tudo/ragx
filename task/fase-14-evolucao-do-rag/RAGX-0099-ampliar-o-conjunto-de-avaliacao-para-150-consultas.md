# RAGX-0099 — Ampliar o conjunto de avaliação para 150 consultas

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 1 — instrumento e caminho quente |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 3d |
| **Depende de** | `RAGX-0098` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [05-busca.md](../../docs/05-busca.md) |
| **Status** | `done` |

## Objetivo

O conjunto tem **26 consultas**. Com n=26, o IC95% de Wilson tem largura ~0,33: `keyword` [0,58–0,89] e `hybrid` [0,43–0,78] se sobrepõem em quase toda a extensão. **Nenhuma mudança de retrieval é falsificável** nesse tamanho — uma melhora real de 5 pontos é indistinguível de ruído, e uma piora também.

## Entregáveis

- [x] `tests/eval/queries.yaml` com **≥ 150** consultas
- [x] Cobertura das classes que hoje não existem no conjunto:
  - [x] **relacionamento** — "quem chama X", "o que depende de Y"
  - [x] **depuração** — trecho de stack trace, mensagem de erro
  - [x] **arquitetura** — "por que a decisão Z", que deve cair em ADR
  - [x] **configuração** — "onde se ajusta o limite de W"
  - [x] **sem resposta** — consultas que o corpus não responde, para medir falso positivo
- [x] Cada caso com `note` dizendo POR QUE aqueles caminhos são os relevantes
- [x] Marcação de dificuldade (`easy` | `hard`) para permitir recorte

## Fora de escopo

- Avaliar qualidade de GERAÇÃO — o RAGX controla recuperação, e é o que se mede
- Conjunto sobre outro repositório (fica como tarefa futura)

## Critérios de aceite

- [x] `ragx eval` roda o conjunto inteiro em menos de 2 minutos (depende de `RAGX-0097`): **24 s** com 152 consultas e os três modos
- [x] A largura do IC95% de recall@5 fica **abaixo de 0,20** em todos os modos (medido: 0,15 keyword, 0,17 semantic, 0,16 hybrid)
- [x] O CI falha se a largura do IC passar de 0,20 — o conjunto não pode encolher (`tests/unit/test_eval_conjunto.py` calcula a largura no PIOR caso, recall 0,5, com as consultas respondidas e exige ≥ 150 no total; o CI não tem o índice para rodar o `ragx eval` de verdade)
- [x] Consultas "sem resposta" não contam como falha de recall; entram numa métrica própria

## Testes

- [x] Teste que valida o schema de `queries.yaml` (campos obrigatórios, caminhos existentes)
- [x] Teste que falha se algum `relevant_paths` apontar para arquivo que não existe mais

## Notas

É a tarefa mais cara da fase e a que destrava todas as outras. Sem ela, as ondas 3 a 6 entregam números que ninguém pode confirmar.

Montar o conjunto é trabalho manual e deve ser feito por quem conhece o repositório. Um atalho tentador é gerar consultas com LLM a partir dos chunks — isso produz um conjunto que mede se a busca encontra o chunk de onde a pergunta saiu, que é circular e não mede nada.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração
- [x] Documentação confere com o comportamento implementado

## Andamento

- 2026-10-02 — Conjunto ampliado de 26 para **152** consultas (**132 com resposta**, 20 sem): relacionamento 20, depuração 19, arquitetura 23, configuração 24, factual 46, sem resposta 20, com `class`, `difficulty` e `note` em todos (as 26 originais ganharam os três campos). Cuidados: nenhuma consulta foi derivada de chunk; todo `relevant_paths` existe (teste); para as `sem_resposta` conferi por `git grep` que os substantivos distintivos não aparecem no repositório (troquei oito que apareciam: PostgreSQL, Kubernetes, OAuth, IPv6 e outras). `ragx eval` ganhou `by_class`, `by_difficulty` e o falso positivo das sem resposta (limiar = 10º percentil do top-1 dos acertos); `load_cases(only_answerable=True)` para `trial`, `ab` e `medir_grafo.py`, que usam os casos como tarefas.
- **Resultado** (fastembed multilíngue): keyword 0,69 [0,61–0,76], semantic 0,54 [0,45–0,62], hybrid 0,62 [0,54–0,70]; MRR 0,47, 0,43, 0,49; sem resposta com falso positivo 3/20, 1/20, 3/20. O híbrido NÃO supera o keyword em recall@5 (a diferença, 0,07, ainda cabe parcialmente nos intervalos), e relacionamento é a classe mais fraca (keyword 11/20, hybrid 9/20, semantic 4/20).
- **Ressalva importante**: eu (um agente) escrevi as consultas novas; a nota da tarefa pedia alguém que conheça o repositório. Os `relevant_paths` são o(s) arquivo(s) que eu sei que respondem; outros podem responder também, então os recalls são um piso. Recomendo uma revisão humana, principalmente das 20 de relacionamento e das 19 de depuração.
- Os números de documentos históricos (`docs/06`, `docs/07`, `docs/23`, que citam "26 consultas") continuam sendo o que foi medido naquele momento; `ragx trial` agora roda sobre as 132 respondidas e dará outro número.
