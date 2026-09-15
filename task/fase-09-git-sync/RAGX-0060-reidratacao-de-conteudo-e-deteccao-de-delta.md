# RAGX-0060 — Reidratação de conteúdo e detecção de delta

| | |
|---|---|
| **Fase** | 9 — Git Sync / Merge |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0059` |
| **Bloqueia** | `RAGX-0061` |
| **Documentação** | [12-git-sync.md](../../docs/12-git-sync.md) · [adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md](../../docs/adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) |
| **Status** | `todo` |

## Objetivo

Reconstruir o conteúdo dos chunks a partir do working tree (já que ele não é versionado) e descobrir o que mudou, com degradação previsível quando o Git não ajuda.

## Entregáveis

- [ ] `migrations/0007_sync.sql`: `sync_state` com `rehydrated_at` e `rehydrate_status`
- [ ] Reidratação: lê `rel_path[start:end]` do working tree e confere `content_hash`
- [ ] Três desfechos tratados e reportados: `ok` · `hash_mismatch` (re-deriva o documento) · `file_missing` (descarta e reporta)
- [ ] Reaproveitamento do embedding int8 versionado quando o hash bate
- [ ] Delta via `git diff --name-status <ultimo_sync_commit> HEAD`
- [ ] `meta.last_sync_commit` mantido a cada sync
- [ ] Fallback por comparação de `content_hash` quando não há Git ou o commit sumiu (rebase, shallow clone)

## Fora de escopo

- Aplicação do delta (RAGX-0061)

## Critérios de aceite

- [ ] Commit reescrito/ausente cai no fallback automaticamente, sem falhar
- [ ] Delta do Git lista arquivos; quais chunks mudaram continua decidido por `content_hash`
- [ ] Commit que só altera indentação não gera chunk novo
- [ ] Funciona em repositório sem Git
- [ ] Reidratação reporta status para 100% dos chunks; nenhum caso é silenciado
- [ ] `knowledge/` desatualizado converge por re-derivação, sem corromper o índice
- [ ] Reidratação de 10k chunks em menos de 30 s

## Testes

- [ ] Repositório sintético com rebase e shallow clone
- [ ] Os 3 desfechos de reidratação

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
