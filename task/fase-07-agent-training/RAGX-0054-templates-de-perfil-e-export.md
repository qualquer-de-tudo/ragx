# RAGX-0054 — Templates de perfil e export

| | |
|---|---|
| **Fase** | 7 — Agent Knowledge Training |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0053` |
| **Bloqueia** | — |
| **Documentação** | [10-agent-training.md](../../docs/10-agent-training.md) |
| **Status** | `todo` |

## Objetivo

Reduzir o custo de criar o primeiro perfil útil.

## Entregáveis

- [ ] Templates `backend`, `frontend`, `reviewer`, `docs` com regras e skills iniciais
- [ ] `ragx agent export <nome> --out FILE` para perfil portátil
- [ ] Documentação de como adaptar um template

## Fora de escopo

- Marketplace de perfis

## Critérios de aceite

- [ ] Cada template gera um perfil que passa no `ragx agent eval` com casos genéricos
- [ ] Perfil exportado é importável em outro projeto do mesmo stack

## Testes

- [ ] Smoke test por template

## Notas

Porta de saída da Fase 7.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
