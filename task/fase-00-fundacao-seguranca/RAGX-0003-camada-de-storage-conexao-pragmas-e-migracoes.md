# RAGX-0003 — Camada de storage: conexão, pragmas e migrações

| | |
|---|---|
| **Fase** | 0 — Fundação + Security Gate |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0001` |
| **Bloqueia** | `RAGX-0007`, `RAGX-0009`, `RAGX-0014` |
| **Documentação** | [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) · [adr/ADR-0002-sqlite-como-store-unico.md](../../docs/adr/ADR-0002-sqlite-como-store-unico.md) |
| **Status** | `todo` |

## Objetivo

Ter um SQLite aberto corretamente e um mecanismo de migração simples e auditável.

## Entregáveis

- [ ] `storage/db.py`: abertura com WAL, `foreign_keys=ON`, `busy_timeout`, `mmap_size`
- [ ] Runner de migrações via `PRAGMA user_version`, cada arquivo em uma transação
- [ ] `migrations/0001_init.sql` com `meta`, `index_runs`, `security_events`
- [ ] Modo somente leitura (`file:...?mode=ro`) para uso do MCP
- [ ] Detecção de FTS5 disponível na abertura, com erro claro se ausente

## Fora de escopo

- Tabelas de documentos/chunks (RAGX-0014) e de grafo (RAGX-0032)

## Critérios de aceite

- [ ] Migração aplica do zero e é idempotente na segunda execução
- [ ] Banco com `user_version` maior que o suportado gera erro claro (exit 3), não corrupção
- [ ] Interrupção no meio de uma migração deixa o banco no estado anterior
- [ ] Abertura em modo ro recusa escrita

## Testes

- [ ] Integração: migrar do zero, reabrir, migrar de novo
- [ ] Banco corrompido → mensagem acionável

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
