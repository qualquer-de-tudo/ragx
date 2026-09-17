# RAGX-0099 — Ampliar o conjunto de avaliação para 150 consultas

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 1 — instrumento e caminho quente |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 3d |
| **Depende de** | `RAGX-0098` |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [05-busca.md](../../docs/05-busca.md) |
| **Status** | `todo` |

## Objetivo

O conjunto tem **26 consultas**. Com n=26, o IC95% de Wilson tem largura ~0,33: `keyword` [0,58–0,89] e `hybrid` [0,43–0,78] se sobrepõem em quase toda a extensão. **Nenhuma mudança de retrieval é falsificável** nesse tamanho — uma melhora real de 5 pontos é indistinguível de ruído, e uma piora também.

## Entregáveis

- [ ] `tests/eval/queries.yaml` com **≥ 150** consultas
- [ ] Cobertura das classes que hoje não existem no conjunto:
  - [ ] **relacionamento** — "quem chama X", "o que depende de Y"
  - [ ] **depuração** — trecho de stack trace, mensagem de erro
  - [ ] **arquitetura** — "por que a decisão Z", que deve cair em ADR
  - [ ] **configuração** — "onde se ajusta o limite de W"
  - [ ] **sem resposta** — consultas que o corpus não responde, para medir falso positivo
- [ ] Cada caso com `note` dizendo POR QUE aqueles caminhos são os relevantes
- [ ] Marcação de dificuldade (`easy` | `hard`) para permitir recorte

## Fora de escopo

- Avaliar qualidade de GERAÇÃO — o RAGX controla recuperação, e é o que se mede
- Conjunto sobre outro repositório (fica como tarefa futura)

## Critérios de aceite

- [ ] `ragx eval` roda o conjunto inteiro em menos de 2 minutos (depende de `RAGX-0097`)
- [ ] A largura do IC95% de recall@5 fica **abaixo de 0,20** em todos os modos
- [ ] O CI falha se a largura do IC passar de 0,20 — o conjunto não pode encolher
- [ ] Consultas "sem resposta" não contam como falha de recall; entram numa métrica própria

## Testes

- [ ] Teste que valida o schema de `queries.yaml` (campos obrigatórios, caminhos existentes)
- [ ] Teste que falha se algum `relevant_paths` apontar para arquivo que não existe mais

## Notas

É a tarefa mais cara da fase e a que destrava todas as outras. Sem ela, as ondas 3 a 6 entregam números que ninguém pode confirmar.

Montar o conjunto é trabalho manual e deve ser feito por quem conhece o repositório. Um atalho tentador é gerar consultas com LLM a partir dos chunks — isso produz um conjunto que mede se a busca encontra o chunk de onde a pergunta saiu, que é circular e não mede nada.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
