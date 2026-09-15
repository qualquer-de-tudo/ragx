# RAGX-0095 — Tarefas versionadas e reidratação

| | |
|---|---|
| **Fase** | 13 — Task Analyzer + Orquestração |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0089`, `RAGX-0061` |
| **Bloqueia** | `RAGX-0096` |
| **Documentação** | [ADR-0014](../../docs/adr/ADR-0014-orquestracao-local-e-o-que-e-versionavel.md) · [12-git-sync.md](../../docs/12-git-sync.md) |
| **Status** | `todo` |

## Objetivo

Fazer a DEFINIÇÃO do trabalho viajar no Git e a EXECUÇÃO ficar na máquina.

## Entregáveis

- [ ] `knowledge/tasks/projects/*.json` e `knowledge/tasks/tasks/*.json`, determinísticos
- [ ] Serialização estável: regenerar sem mudança dá diff vazio
- [ ] Reidratação em `ragx sync`, reconstruindo o board a partir do Git
- [ ] Resolução de conflito de `status` por precedência declarada
- [ ] `running` vindo do Git vira `pending` na reidratação
- [ ] `.gitignore` cobre `.ragx/`, `*.sqlite`, `*.db`
- [ ] A saída do `sync` DIZ que o histórico local não voltou

## Fora de escopo

- Versionar runs, tentativas, logs, locks ou retry
- Usar o SQLite como mecanismo de merge

## Critérios de aceite

- [ ] `git pull && ragx sync` reconstrói o board íntegro
- [ ] `git diff knowledge/tasks/` vazio quando nada mudou
- [ ] `ragx reset && ragx sync` devolve board completo e histórico vazio, e AVISA
- [ ] Conflito de status resolve por precedência, sem intervenção manual

## Testes

- [ ] Round-trip: serializar → apagar banco → reidratar → estado idêntico
- [ ] Precedência de status: matriz completa
- [ ] Determinismo: serializar duas vezes dá bytes idênticos

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes
- [ ] `ruff` limpo
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
