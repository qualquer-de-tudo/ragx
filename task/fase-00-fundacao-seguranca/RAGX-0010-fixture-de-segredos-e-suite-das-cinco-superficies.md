# RAGX-0010 — Fixture de segredos e suíte das cinco superfícies

| | |
|---|---|
| **Fase** | 0 — Fundação + Security Gate |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0009` |
| **Bloqueia** | `RAGX-0011`, `RAGX-0012` |
| **Documentação** | [13-testes-hardening.md](../../docs/13-testes-hardening.md) · [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `todo` |

## Objetivo

Construir o artefato de teste mais importante do repositório e a suíte que, a partir daqui, governa o avanço de todas as fases.

## Entregáveis

- [ ] `tests/fixtures/secret_project/` completo conforme doc 13, com segredos falsos de formato válido
- [ ] `SECRETS_UNDER_TEST.py` como lista única consumida pelos testes
- [ ] Suíte parametrizada nas 5 superfícies (database, embeddings, graph, mcp, export) com `xfail` nas ainda inexistentes
- [ ] Teste de ausência de falso negativo: `.env.example`, `src/app.py` e `docs/setup.md` PRECISAM ser indexados
- [ ] Teste de vazamento no próprio relatório (eventos, logs, stdout)
- [ ] Exceção documentada e comentada do pre-commit do RAGX para essa pasta

## Fora de escopo

- Implementar as superfícies — cada fase posterior vira seu próprio xfail

## Critérios de aceite

- [ ] Superfície `database` passa agora; as outras 4 estão `xfail` com motivo explícito
- [ ] Suíte roda em menos de 30 s
- [ ] Nenhum segredo real; todos com formato válido para acionar as regras
- [ ] Está documentado, no README de `task/`, que virar cada `xfail` é DoD da fase correspondente

## Testes

- [ ] A própria suíte é o entregável

## Notas

Esta tarefa é a porta de saída da Fase 0. Enquanto ela não estiver verde, nenhuma tarefa da Fase 1 começa.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
