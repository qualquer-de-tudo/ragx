# RAGX-0091 — Dispatcher, contexto por tarefa e validação

| | |
|---|---|
| **Fase** | 13 — Task Analyzer + Orquestração |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0090`, `RAGX-0042` |
| **Bloqueia** | `RAGX-0092` |
| **Documentação** | [21-orquestracao-de-tarefas.md](../../docs/21-orquestracao-de-tarefas.md) · [ADR-0015](../../docs/adr/ADR-0015-quem-executa-a-tarefa.md) |
| **Status** | `todo` |

## Objetivo

Entregar ao agente a próxima tarefa com o contexto certo, receber o resultado, validar de forma determinística e liberar as dependentes.

## Entregáveis

- [ ] `TaskContextBuilder` reusando o Context Engine, dentro de orçamento de tokens
- [ ] Contexto inclui resultado das dependências concluídas e decisões que tocam o assunto
- [ ] Contexto gravado em `task_context` com hash e contagem de tokens
- [ ] `TaskDispatcher`: `next`, `claim`, `report`, `release`
- [ ] `TaskValidator` — checagens determinísticas, ZERO juízo sobre qualidade de código
- [ ] `ResultProcessor`: persiste, promove conhecimento, emite evento, libera dependentes
- [ ] `AgentSelector` escolhe o perfil pelo tipo da tarefa

## Fora de escopo

- Executar a tarefa — é do agente (ADR-0015)
- Avaliar se o código está bom — o RAGX não sabe, e fingir é pior que não fazer

## Critérios de aceite

- [ ] O agente NÃO recebe o projeto inteiro; recebe o contexto da tarefa
- [ ] Resultado que declara arquivo fora de `files_scope` FALHA na validação
- [ ] Resultado que declara arquivo bloqueado pelo gate FALHA
- [ ] Critério de aceite sem evidência FALHA
- [ ] Tarefa concluída libera as dependentes no mesmo ciclo

## Testes

- [ ] Contexto respeita o orçamento de tokens
- [ ] Resultado fora de escopo é recusado
- [ ] Dependência concluída libera a próxima
- [ ] Nenhum segredo aparece no contexto entregue

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes
- [ ] `ruff` limpo
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
