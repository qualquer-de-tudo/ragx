# RAGX-0020 — Chunker de documentação e fallback

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0015` |
| **Bloqueia** | `RAGX-0021` |
| **Documentação** | [04-indexacao.md](../../docs/04-indexacao.md) |
| **Status** | `todo` |

## Objetivo

Fatiar documentação por estrutura de heading e ter uma rede de segurança para o resto.

## Entregáveis

- [ ] `doc_chunker.py`: corte em h1–h3, h4+ absorvidos pelo ancestral
- [ ] `heading_path` preenchido e repetido quando uma seção é dividida
- [ ] Bloco de código e tabela nunca partidos ao meio
- [ ] `fallback_chunker.py`: janela por parágrafo, usado em falha de parsing e extensão desconhecida

## Fora de escopo

- Compressão (Fase 4)

## Critérios de aceite

- [ ] Documento longo com seção acima de `max_tokens` divide por parágrafo mantendo o `heading_path`
- [ ] Bloco de código de 200 linhas não é partido
- [ ] Fallback produz chunks estáveis e determinísticos

## Testes

- [ ] Snapshot sobre `docs/` deste próprio repositório

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
