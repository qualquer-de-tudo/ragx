# RAGX-0097 — Cachear o embedder por processo

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | 1 — instrumento e caminho quente |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [05-busca.md](../../docs/05-busca.md) |
| **Status** | `done` |

## Objetivo

Hoje `build_embedder()` constrói o modelo ONNX a cada busca semântica. Medido: 2537–3638 ms para construir, contra 6–27 ms para embutir a consulta. **~99% da latência da busca semântica é carregar o modelo**, não buscar.

## Entregáveis

- [x] `build_embedder(cfg)` memoiza por `(provider, model, dim, base_url)`
- [x] A memoização é por PROCESSO — o servidor MCP é persistente e é ele quem ganha
- [x] `context/engine.py:_vectors_for()` passa a reusar a mesma instância (hoje constrói a segunda)
- [x] Invalidação explícita quando a configuração de embedding muda em tempo de execução
- [ ] O cache de matriz que `docs/05-busca.md` promete em `load_index` passa a existir de fato, ou a documentação deixa de prometê-lo — **pendente**: `load_index` custa ~50 ms e a invalidação por `mtime` que o documento descreve não é confiável sob WAL; fica para tarefa própria

## Fora de escopo

- Trocar o modelo de embedding (é a `RAGX-0103`)
- Qualquer mudança no resultado da busca — este é um ganho de latência puro

## Critérios de aceite

- [x] `search --mode hybrid` abaixo de **150 ms** na segunda chamada do mesmo processo — medido: **58 ms** (antes: 2677 ms)
- [x] `build_context` sem cache abaixo de **500 ms** — medido: **287 ms** (antes: 5327 ms)
- [x] Os IDs devolvidos pela busca são **idênticos** antes e depois, nas 26 consultas do conjunto de avaliação
- [x] Nenhum vazamento entre projetos: dois `Config` com raízes diferentes não compartilham embedder indevidamente

## Testes

- [x] Teste de contrato: mesma consulta, mesmos `chunk_id` na mesma ordem, antes e depois
- [x] Teste de que a segunda chamada no mesmo processo não reconstrói (espiar contador de construção)
- [x] Benchmark registrado no CHANGELOG com número antes/depois

## Notas

É o item de maior efeito e menor risco de toda a Fase 14. Nenhum resultado muda; só o tempo. A diferença de 150× entre `search keyword` (18 ms) e `search hybrid` (2677 ms) **não é propriedade de busca vetorial** — é este defeito.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
