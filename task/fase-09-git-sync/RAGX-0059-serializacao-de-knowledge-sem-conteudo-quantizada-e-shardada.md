# RAGX-0059 — Serialização de knowledge/ sem conteúdo, quantizada e shardada

| | |
|---|---|
| **Fase** | 9 — Git Sync / Merge |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0045`, `RAGX-0070`, `RAGX-0071` |
| **Bloqueia** | `RAGX-0060` |
| **Documentação** | [12-git-sync.md](../../docs/12-git-sync.md) · [16-orcamento-de-tamanho.md](../../docs/16-orcamento-de-tamanho.md) · [adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md](../../docs/adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) |
| **Status** | `todo` |

## Objetivo

Gravar o conhecimento em texto de forma que o Git produza diff legível, merge viável e tamanho dentro do orçamento — o que exige NÃO versionar conteúdo de chunk.

## Entregáveis

- [ ] Um arquivo por documento: `knowledge/documents/<rel_path com __>.json` e `chunks/<...>.jsonl`
- [ ] `chunks/*.jsonl` SEM o campo `content` — só `rel_path`, `lines`, `symbol`, `kind`, `content_hash`, `tokens`, `parent`
- [ ] `knowledge/embeddings/` com vetores int8@`versioned_dim`, shardados por prefixo de ID (16 shards) + `manifest.json`
- [ ] `entities/` e `relations/` shardados pelo mesmo critério
- [ ] Resolução de colisão de nome com sufixo `-<hash6>`
- [ ] JSON com `sort_keys=True`, `indent=2`, `ensure_ascii=False`, newline LF; JSONL ordenado por `ordinal`, sem timestamp por chunk
- [ ] Rebalanceamento automático (16 para 32 shards) quando um shard passa de `size.max_artifact_bytes`
- [ ] `.gitattributes` com `knowledge/** text eol=lf`; `ragx init` escreve as regras corretas no `.gitignore`

## Fora de escopo

- Reidratação (RAGX-0060)
- Versionar float32 — fica só em `.ragx/`

## Critérios de aceite

- [ ] `git diff knowledge/` após reindexação sem mudanças é vazio
- [ ] Arquivos idênticos entre Windows e Linux (sem CRLF)
- [ ] Alterar um arquivo muda os artefatos daquele documento e **1 shard** de embeddings entre 16
- [ ] `knowledge/` de repositório com 100k chunks fica abaixo de 50 MB
- [ ] Nenhum artefato versionado passa de `size.max_artifact_bytes`
- [ ] Nenhum `.db`, `.sqlite` ou vetor float32 versionado

## Testes

- [ ] Idempotência byte a byte
- [ ] Diff mínimo por alteração
- [ ] Cross-platform no CI

## Notas

A proposta original deixava embeddings fora do Git, o que obrigava todo dev a ter Ollama antes da primeira busca. Em int8@256 o custo cai para 24 MB por 100k chunks e passa a valer a pena versionar — ver ADR-0010.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
