# RAGX-0050 — Schema de perfil de agente e ragx agent create

| | |
|---|---|
| **Fase** | 7 — Agent Knowledge Training |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0049` |
| **Bloqueia** | `RAGX-0051` |
| **Documentação** | [10-agent-training.md](../../docs/10-agent-training.md) |
| **Status** | `todo` |

## Objetivo

Definir o formato versionável do perfil e o comando que cria o esqueleto.

## Entregáveis

- [ ] `agents/profile.py` com o modelo de `manifest.json` do doc 10 e JSON Schema publicado
- [ ] `migrations/0006_agents.sql`: `agent_profiles`, `agent_evaluations`
- [ ] `ragx agent create <nome> [--template] [--scope]` gerando a árvore completa
- [ ] Validação: `manifest.scope` nunca inclui caminho fora da raiz do projeto
- [ ] `ragx agent list` e `ragx agent show`

## Fora de escopo

- Compilação do conhecimento (RAGX-0051)

## Critérios de aceite

- [ ] Perfil criado valida contra o JSON Schema
- [ ] Escopo fora da raiz é recusado
- [ ] Árvore gerada é legível e revisável em PR — sem blob, sem binário

## Testes

- [ ] Validação de schema
- [ ] Teste de escopo malicioso (`../`)

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
