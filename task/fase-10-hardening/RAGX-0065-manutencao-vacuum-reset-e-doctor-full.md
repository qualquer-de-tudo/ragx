# RAGX-0065 — Manutenção: vacuum, reset e doctor --full

| | |
|---|---|
| **Fase** | 10 — Hardening + Release |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0063` |
| **Bloqueia** | — |
| **Documentação** | [14-cli.md](../../docs/14-cli.md) · [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) |
| **Status** | `todo` |

## Objetivo

Dar ao usuário meios de diagnosticar e recuperar o índice.

## Entregáveis

- [ ] `ragx vacuum`: `VACUUM` + `PRAGMA optimize` + remoção de órfãos (embedding sem chunk, entidade sem documento, relação sem entidade)
- [ ] `ragx reset [--hard]` com confirmação explícita
- [ ] `ragx doctor --full` incluindo `PRAGMA integrity_check` e verificação de consistência entre tabelas

## Fora de escopo

- Reparo automático de banco corrompido

## Critérios de aceite

- [ ] `ragx vacuum` reduz o tamanho do arquivo após remoções em massa e não perde dado válido
- [ ] `ragx reset` pede confirmação e informa exatamente o que será apagado
- [ ] `ragx doctor --full` detecta inconsistência injetada artificialmente

## Testes

- [ ] Teste de órfãos injetados
- [ ] Teste de integridade

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
