# RAGX-0009 — CLI da Fase 0: init, doctor, security scan, security rules

| | |
|---|---|
| **Fase** | 0 — Fundação + Security Gate |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0008`, `RAGX-0003` |
| **Bloqueia** | `RAGX-0010` |
| **Documentação** | [14-cli.md](../../docs/14-cli.md) · [15-configuracao.md](../../docs/15-configuracao.md) |
| **Status** | `todo` |

## Objetivo

Entregar os primeiros comandos utilizáveis, incluindo o relatório de segurança que o dev roda antes de confiar no sistema.

## Entregáveis

- [ ] `ragx init`: cria `.ragx/`, `ragx.toml`, `.ragignore` e atualiza o `.gitignore` do projeto
- [ ] `ragx doctor`: valida python, sqlite+FTS5, schema, config, ruleset, embedder e permissão de escrita — com sugestão acionável por falha
- [ ] `ragx security scan [PATH]` com `--json`, `--fail-on`, `--staged`, `--rule`
- [ ] `ragx security rules [--show-disabled]`
- [ ] Exit codes padronizados (0/1/2/3/130) conforme doc 14
- [ ] Saída Rich agrupada em BLOCKED / REDACTED / SKIPPED, como no doc 02

## Fora de escopo

- Indexação

## Critérios de aceite

- [ ] `ragx security scan .` na fixture reproduz a saída do doc 02 e retorna exit 1
- [ ] `--json` produz saída estável e parseável, sem cor nem barra de progresso
- [ ] `--staged` lê a lista do stage do Git e serve para uso em `pre-commit`
- [ ] `ragx doctor` com Ollama fora do ar aponta exatamente o que fazer
- [ ] `ragx init` é idempotente e não sobrescreve `ragx.toml` sem `--force`

## Testes

- [ ] E2E do scan sobre a fixture
- [ ] Snapshot da saída `--json`

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
