# RAGX-0061 — ragx sync e resolução de conflito

| | |
|---|---|
| **Fase** | 9 — Git Sync / Merge |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0060` |
| **Bloqueia** | `RAGX-0062`, `RAGX-0074` |
| **Documentação** | [12-git-sync.md](../../docs/12-git-sync.md) |
| **Status** | `todo` |

## Objetivo

Reconstruir o índice local a partir do conhecimento versionado, aplicando só o delta.

## Entregáveis

- [ ] `ragx sync [--quiet] [--from-commit] [--full]` com o relatório do doc 12
- [ ] Reconstrução de `.ragx/knowledge.db` a partir de `knowledge/` + repositório
- [ ] Re-scan de segurança no sync (arquivo já indexado pode ter virado sensível)
- [ ] `--resolve` e `--resolve-file PATH`: descarta o lado conflitante e rederiva do arquivo-fonte mergeado
- [ ] Regeneração do dicionário quando `sync.auto_dictionary = true` e da fatia de federação quando `sync.auto_federation = true`

## Fora de escopo

- Merge de embeddings

## Critérios de aceite

- [ ] `git pull && ragx sync` atualiza só o delta; arquivo inalterado não é reprocessado
- [ ] Onboarding: `git clone && ragx sync` reconstrói tudo sem reindexar do zero o que já está versionado
- [ ] `git clone && ragx search` responde SEM embedder e SEM rede, usando os vetores int8 versionados
- [ ] Conflito no mesmo documento é resolvido por `--resolve` sem intervenção manual
- [ ] Arquivo que virou sensível é removido do índice pelo re-scan

## Testes

- [ ] Cenário de dois devs do doc 12
- [ ] Teste de onboarding em clone limpo

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
