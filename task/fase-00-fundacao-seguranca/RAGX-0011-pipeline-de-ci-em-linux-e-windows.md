# RAGX-0011 — Pipeline de CI em Linux e Windows

| | |
|---|---|
| **Fase** | 0 — Fundação + Security Gate |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0010` |
| **Bloqueia** | `RAGX-0023` |
| **Documentação** | [13-testes-hardening.md](../../docs/13-testes-hardening.md) |
| **Status** | `todo` |

## Objetivo

Automatizar a verificação em dois sistemas operacionais desde o início, porque o determinismo de IDs depende disso.

## Entregáveis

- [ ] Workflow com a ordem `lint → unit → security (bloqueante) → integration → e2e`
- [ ] Matriz `ubuntu-latest` × `windows-latest`, Python 3.11 e 3.13
- [ ] Gate de cobertura: 90% em `src/ragx/security/`
- [ ] `pip-audit` e `bandit` como jobs informativos nesta fase
- [ ] Cache de dependências via uv

## Fora de escopo

- Publicação de release (RAGX-0067)

## Critérios de aceite

- [ ] CI verde nos dois SOs
- [ ] Falha na suíte `security` interrompe o pipeline antes de `integration`
- [ ] Pipeline completo em menos de 10 minutos

## Testes

- [ ] O próprio pipeline

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
