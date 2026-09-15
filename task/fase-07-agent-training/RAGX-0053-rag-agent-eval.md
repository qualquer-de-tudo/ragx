# RAGX-0053 — ragx agent eval

| | |
|---|---|
| **Fase** | 7 — Agent Knowledge Training |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0051` |
| **Bloqueia** | `RAGX-0054` |
| **Documentação** | [10-agent-training.md](../../docs/10-agent-training.md) |
| **Status** | `todo` |

## Objetivo

Medir o que o RAGX de fato controla — recuperação — e ser honesto sobre o que não mede.

## Entregáveis

- [ ] Formato `evaluation/cases.yaml` com `expect_sources`, `must_mention`, `must_not_mention`, `expect_skill`
- [ ] `agents/evaluator.py` medindo Recall@3 e ativação de skill
- [ ] Resultados versionados em `evaluation/results/`
- [ ] Saída deixando explícito que avalia recuperação, não geração

## Fora de escopo

- LLM-as-judge para qualidade de resposta — registrado como evolução pós-MVP

## Critérios de aceite

- [ ] Casos rodam e reportam aprovação/reprovação individual
- [ ] `must_not_mention` falha o caso se o termo aparecer no contexto
- [ ] Resultado é reproduzível entre execuções

## Testes

- [ ] Perfil de exemplo com casos passando e falhando

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
