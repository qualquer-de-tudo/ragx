# RAGX-0052 — Skills e examples com promoção manual

| | |
|---|---|
| **Fase** | 7 — Agent Knowledge Training |
| **Prioridade** | P2 — média |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0051` |
| **Bloqueia** | — |
| **Documentação** | [10-agent-training.md](../../docs/10-agent-training.md) |
| **Status** | `todo` |

## Objetivo

Capturar procedimentos repetíveis e exemplos reais, sem deixar exemplo ruim ensinar padrão ruim.

## Entregáveis

- [ ] Formato de skill com front-matter (`name`, `triggers`) e seções do doc 10
- [ ] Inferência de skills a partir de padrões repetidos detectados no `conventions` do dicionário
- [ ] Extração de exemplos do histórico Git, gravados em `examples/_proposed/`
- [ ] `ragx agent promote-example <id>` para promoção manual
- [ ] Todo diff de commit passa pelo gate antes de virar exemplo

## Fora de escopo

- Promoção automática de exemplo

## Critérios de aceite

- [ ] Exemplo proposto nunca entra em `examples/` sem promoção explícita
- [ ] Commit antigo contendo segredo no diff não vira exemplo
- [ ] Skill gerada é legível e acionável por um humano

## Testes

- [ ] Repositório Git sintético com commit contendo segredo

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
