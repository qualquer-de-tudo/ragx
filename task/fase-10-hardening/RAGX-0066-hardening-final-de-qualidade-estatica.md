# RAGX-0066 — Hardening final de qualidade estática

| | |
|---|---|
| **Fase** | 10 — Hardening + Release |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0064` |
| **Bloqueia** | `RAGX-0067` |
| **Documentação** | [13-testes-hardening.md](../../docs/13-testes-hardening.md) |
| **Status** | `todo` |

## Objetivo

Fechar as verificações estáticas e de dependência antes do release.

## Entregáveis

- [ ] `pip-audit` e `bandit` promovidos a jobs bloqueantes
- [ ] `mypy --strict` verde em `core/` e `security/`; `mypy` padrão no restante
- [ ] Cobertura: gate de 90% em `security/`, aviso em 80% geral
- [ ] Revisão de todos os `# type: ignore` e `# noqa` remanescentes, cada um justificado em comentário

## Fora de escopo

- Auditoria de segurança externa

## Critérios de aceite

- [ ] Nenhuma CVE de severidade alta nas dependências
- [ ] Nenhum achado de `bandit` sem justificativa registrada
- [ ] Gates de cobertura ativos no CI

## Testes

- [ ] Os próprios jobs de CI

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
