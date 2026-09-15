# RAGX-0007 — Redactor e persistência de SecurityEvent

| | |
|---|---|
| **Fase** | 0 — Fundação + Security Gate |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0006`, `RAGX-0003` |
| **Bloqueia** | `RAGX-0008` |
| **Documentação** | [02-seguranca.md](../../docs/02-seguranca.md) · [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) |
| **Status** | `todo` |

## Objetivo

Registrar incidentes de forma auditável sem que o valor do segredo seja gravado, logado ou impresso em lugar nenhum.

## Entregáveis

- [ ] `security/redactor.py`: `digest = sha256(valor)[:16]` e `preview` mascarado (4+4, só se `len >= 16`)
- [ ] Substituição por `«RAGX:REDACTED:<rule_id>»` na ação `redact`, aplicada antes do chunking
- [ ] Gravação em `security_events` (nunca o valor)
- [ ] Filtro de log que impede qualquer `SecurityFinding.value` de chegar a handler

## Fora de escopo

- Exibição na CLI (RAGX-0009)

## Critérios de aceite

- [ ] Nenhuma coluna TEXT de `security_events` contém o valor original (varredura por teste)
- [ ] Nenhum arquivo em `.ragx/logs/` contém o valor original
- [ ] `preview` de valor curto vira `«curto»` em vez de revelar o conteúdo
- [ ] Redação preserva o número de linhas do arquivo (não desloca `start_line`/`end_line`)

## Testes

- [ ] Teste dedicado: rodar o pipeline e varrer banco + logs + stdout contra a lista de segredos

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
