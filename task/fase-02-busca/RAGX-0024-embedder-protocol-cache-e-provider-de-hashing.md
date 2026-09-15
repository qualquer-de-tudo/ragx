# RAGX-0024 — Embedder Protocol, cache e provider de hashing

| | |
|---|---|
| **Fase** | 2 — Semantic + Hybrid Search |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0021` |
| **Bloqueia** | `RAGX-0025`, `RAGX-0026` |
| **Documentação** | [adr/ADR-0004-embeddings.md](../../docs/adr/ADR-0004-embeddings.md) · [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) · [adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md](../../docs/adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) |
| **Status** | `todo` |

## Objetivo

Definir a abstração de embedding e ter um provider determinístico para testar o pipeline sem rede.

## Entregáveis

- [ ] `embeddings/base.py` com o Protocol `Embedder` (`embed_documents` / `embed_query` separados)
- [ ] `migrations/0003_embeddings.sql`: `embedding_models`, `embeddings`
- [ ] Serialização float32 little-endian e normalização L2 na gravação
- [ ] Duas representações por chunk: `vector` (float32@768, local) e `vector_q`+`q_scale`+`q_offset` (int8@`versioned_dim`, versionado) — ver ADR-0010
- [ ] Cache em `.ragx/cache/emb/<model_id>/<content_hash>.f32`
- [ ] `embeddings/hashing.py` — determinístico, sem rede, só para testes
- [ ] Validação de `dim` do provider contra `embedding_models.dim` na abertura

## Fora de escopo

- Providers reais (RAGX-0025, RAGX-0026)

## Critérios de aceite

- [ ] Vetores gravados têm norma L2 = 1 (tolerância 1e-6)
- [ ] Cache dispensa nova chamada para `content_hash` já visto
- [ ] Divergência de dimensão é erro na abertura, não falha silenciosa na busca
- [ ] Provider `hashing` produz o mesmo vetor para o mesmo texto, sempre

## Testes

- [ ] Round-trip de serialização
- [ ] Teste de hit/miss do cache

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
