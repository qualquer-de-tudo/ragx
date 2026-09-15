# RAGX-0005 — SecurityScanner — fase 1: deny-list por nome de arquivo

| | |
|---|---|
| **Fase** | 0 — Fundação + Security Gate |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0002` |
| **Bloqueia** | `RAGX-0006` |
| **Documentação** | [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `todo` |

## Objetivo

Bloquear arquivos notoriamente sensíveis antes de qualquer leitura de conteúdo.

## Entregáveis

- [ ] `security/rules/filenames.yaml` com a deny-list completa do doc 02
- [ ] Allowlist de templates (`.env.example`, `.env.sample`, `credentials.example*`, ...)
- [ ] Avaliação por glob sobre o caminho relativo, case-insensitive no Windows
- [ ] Bloqueio de diretórios inteiros: `.ssh/`, `.aws/`, `.gnupg/`
- [ ] Retorno com `rule_id` para rastreabilidade

## Fora de escopo

- Análise de conteúdo (RAGX-0006)

## Critérios de aceite

- [ ] Os 7 arquivos sensíveis da fixture são bloqueados sem que 1 byte seja lido
- [ ] `.env.example` passa a fase 1 (e ainda será verificado na fase 2)
- [ ] Decisão depende só do caminho — verificável por teste sem tocar no disco
- [ ] Variações (`.env.local`, `prod.env`, `id_ed25519`) são cobertas

## Testes

- [ ] Tabela parametrizada de ~40 nomes com veredito esperado

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
