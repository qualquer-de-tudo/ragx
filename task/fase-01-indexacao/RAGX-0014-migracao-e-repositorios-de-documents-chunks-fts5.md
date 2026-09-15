# RAGX-0014 — Migração e repositórios de documents/chunks/FTS5

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0012`, `RAGX-0003` |
| **Bloqueia** | `RAGX-0021`, `RAGX-0069`, `RAGX-0070`, `RAGX-0028` |
| **Documentação** | [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) · [17-multiprojeto-e-federacao.md](../../docs/17-multiprojeto-e-federacao.md) |
| **Status** | `todo` |

## Objetivo

Persistir documentos e chunks com busca por palavra-chave já disponível, e fixar a identidade de projeto que a Fase 11 vai exigir — adicioná-la depois custaria migrar todo o schema.

## Entregáveis

- [ ] `migrations/0002_documents.sql`: `documents`, `chunks`, índices e `chunks_fts`
- [ ] `meta` recebe `project_id`, `project_name`, `project_kind` e `visibility` — a identidade que a Fase 11 exige
- [ ] FTS5 external content com `tokenize = 'unicode61 remove_diacritics 2'` e triggers de sincronização
- [ ] `storage/repositories.py`: `DocumentRepo`, `ChunkRepo` com upsert e delete em cascata
- [ ] Escrita em lote dentro de transação

## Fora de escopo

- Consulta de busca (RAGX-0028)

## Critérios de aceite

- [ ] Deletar documento remove chunks e entradas de FTS (sem órfão)
- [ ] `autenticacao` casa com `autenticação` no FTS
- [ ] Reindexar documento modificado não duplica chunks (`UNIQUE(document_id, ordinal)`)
- [ ] Inserção de 10.000 chunks em menos de 5 s

## Testes

- [ ] Integração: inserir, atualizar, deletar, conferir contagem de FTS

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
