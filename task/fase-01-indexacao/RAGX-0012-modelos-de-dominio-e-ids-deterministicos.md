# RAGX-0012 — Modelos de domínio e IDs determinísticos

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0010` |
| **Bloqueia** | `RAGX-0013`, `RAGX-0014`, `RAGX-0015`, `RAGX-0016`, `RAGX-0018` |
| **Documentação** | [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) |
| **Status** | `todo` |

## Objetivo

Fixar as estruturas centrais e a função de identidade da qual dependem indexação incremental e merge no Git.

## Entregáveis

- [ ] `core/models.py`: `Document`, `Chunk`, `ParseNode`, `SearchResult` como dataclasses frozen+slots
- [ ] `core/ids.py` com `normalize()` e `chunk_id()` exatamente como no doc 03
- [ ] `core/protocols.py` com `Parser`, `Chunker`, `Embedder`, `VectorIndex`
- [ ] `CHUNKER_VERSION` centralizado e citado no payload do hash

## Fora de escopo

- Persistência

## Critérios de aceite

- [ ] `chunk_id` idêntico para o mesmo conteúdo com CRLF e com LF
- [ ] `chunk_id` idêntico para o mesmo caminho escrito com `\` e com `/`
- [ ] Caminho absoluto nunca entra no payload do hash
- [ ] Alterar `CHUNKER_VERSION` altera todos os IDs (comprovado por teste)
- [ ] Nenhuma fonte de não determinismo (tempo, uuid, random, ordem de dict)

## Testes

- [ ] Unitários das 5 armadilhas listadas no doc 03
- [ ] Snapshot de IDs commitado

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
