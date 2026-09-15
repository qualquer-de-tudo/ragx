# RAGX-0021 — Pipeline de indexação incremental

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1,5d |
| **Depende de** | `RAGX-0013`, `RAGX-0014`, `RAGX-0019`, `RAGX-0020`, `RAGX-0008` |
| **Bloqueia** | `RAGX-0022`, `RAGX-0023`, `RAGX-0024`, `RAGX-0032` |
| **Documentação** | [04-indexacao.md](../../docs/04-indexacao.md) |
| **Status** | `todo` |

## Objetivo

Orquestrar o fluxo completo, com incrementalidade real, transacionalidade por lote e o gate de segurança no lugar certo.

## Entregáveis

- [ ] `indexing/pipeline.py`: walker → gate → parser → chunker → store
- [ ] Atalho por `size`+`mtime_ns`, e comparação de `content_hash` quando necessário
- [ ] Remoção de documentos ausentes do disco, com cascade
- [ ] Transação por lote (padrão 200 arquivos); Ctrl+C deixa o banco consistente
- [ ] `ThreadPoolExecutor` para leitura/parse e thread única escritora
- [ ] Registro em `index_runs` com todas as contagens
- [ ] Barra de progresso Rich e relatório final conforme doc 04

## Fora de escopo

- Embeddings (RAGX-0024+); o pipeline grava chunks sem vetor nesta fase

## Critérios de aceite

- [ ] Segunda execução sem mudanças reporta `+0 novos`, `+0 chunks` e roda em fração do tempo
- [ ] Arquivo removido do disco some do índice junto com seus chunks
- [ ] Ctrl+C e reexecução convergem para o mesmo estado final que uma execução ininterrupta
- [ ] Nenhum arquivo bloqueado gera documento ou chunk
- [ ] Duas instâncias simultâneas no mesmo projeto: lock, não corrupção

## Testes

- [ ] E2E sobre repositório sintético
- [ ] Teste de interrupção
- [ ] Teste de concorrência

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
