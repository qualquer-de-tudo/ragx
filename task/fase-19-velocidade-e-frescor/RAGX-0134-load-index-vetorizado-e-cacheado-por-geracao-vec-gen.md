# RAGX-0134 — `load_index` vetorizado e cacheado por geração (`vec_gen`)

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (C-02) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V4, S10) · [05-busca.md](../../docs/05-busca.md) · [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) |
| **Status** | `todo` |

## Objetivo

`load_index` (`storage/vectors.py:75-99`) roda em toda busca (`search/service.py:118`) e faz `dequantize` e `l2_normalize` linha a linha em laço Python; a docstring de `VectorIndex` e o `docs/05-busca.md:58` prometem um cache que não existe. Medido: 69–80 ms, cerca de 75% do `search_hybrid` quente (104–172 ms); vetorizado, 18,7 ms (diferença máxima 6e-8). Extrapolado, não medido: 500 mil chunks ≈ 6 s e 1,1 GB.

## Entregáveis

- [ ] **Medir primeiro:** `load_index` e `search_hybrid` quente (10 execuções, p50/p95) no repo real.
- [ ] Migração com o próximo número livre em `src/ragx/storage/migrations/` (hoje o último é `0006_run_provenance.sql`): semeia `meta('vec_gen','0')` e cria três gatilhos `AFTER INSERT/UPDATE/DELETE ON embeddings` que fazem `UPDATE meta SET value = CAST(value AS INTEGER)+1 WHERE key='vec_gen'`. Gatilho, e não código nos escritores, porque há vários (`store_vectors`, `embed.py:77-81`, exclusão em cascata por `chunks`/`documents`, `portability/importer.py:241`, `maintenance_cmd.py`). Confirmado em experimento com `sqlite3`: a exclusão em cascata e o `INSERT OR REPLACE` disparam os gatilhos.
- [ ] Atualizar `SCHEMA_VERSION` (`core/ids.py:19`), a tabela de migrações de `docs/03-modelo-de-dados.md` e o teste `test_schema_version_bate_com_a_migracao_mais_recente` (`tests/unit/test_ids.py:92`).
- [ ] `load_index` vetorizado: `vector_q` empilhado em uma matriz `uint8` (`np.frombuffer(b"".join(...))` e `reshape`), `coarse = q * scale[:, None] + offset[:, None]` e `l2_normalize` da matriz; `full` por `np.frombuffer` sem renormalizar (como hoje). Se os tamanhos das linhas divergirem, cair no caminho por linha.
- [ ] `vec_generation(conn)` em `vectors.py` e cache por processo `(caminho do banco via PRAGMA database_list, model_id) -> (vec_gen, VectorIndex)`: até 4 bancos (descarta o mais antigo), um modelo por banco. **Ler `vec_gen` antes das linhas, na mesma transação de leitura**; se mudar no meio, o pior caso é recarregar.
- [ ] `reset_vector_cache()` para testes; o `VectorIndex` devolvido é compartilhado, então documentar que ninguém o altera.
- [ ] `docs/05-busca.md:58` e a docstring de `VectorIndex` trocam "cacheada por `mtime`" por "pela geração `vec_gen`, porque `mtime` não é confiável sob WAL".
- [ ] CHANGELOG com o número antes/depois.

## Fora de escopo

- Escolher o modelo configurado e avisar vetor parcial: RAGX-0136.
- Cache do `build_context`: RAGX-0135. Vetorizar o MMR e a expansão do grafo: RAGX-0150 e RAGX-0145.
- `sqlite-vec`/ANN (decidido fora, auditoria 7.3). Custo de `_filter_mask` (`service.py:132-150`): medir depois; se passar de 10 ms, tarefa nova.

## Critérios de aceite

- [ ] `load_index` frio ≤ 20 ms no repo real (antes 69–80 ms) e ≤ 1 ms com o cache quente.
- [ ] `search_hybrid` quente ≤ 60 ms (**S10**; antes 104–172 ms). Se não chegar, registrar quanto sobra e em quê.
- [ ] Resultado idêntico: mesmos `ids`, `np.allclose(coarse, coarse_antigo, atol=1e-6)` e mesmo top-k nas 26 consultas de `tests/eval/queries.yaml`.
- [ ] Indexar ou apagar um documento, ou embutir chunks, invalida o cache na busca seguinte (0 resultados velhos).

## Medição

| Métrica | Antes | Depois |
|---|---|---|
| `load_index`, frio | 69–80 ms | |
| `load_index`, cache quente | 69–80 ms (sem cache) | |
| `search_hybrid` quente | 104–172 ms | |

Comando (script temporário fora do repo, rodado com `uv run python`):

```python
import time
from ragx.config import load_config
from ragx.search.service import search
from ragx.storage.db import open_db
from ragx.storage.vectors import load_index

cfg = load_config()
with open_db(cfg.db_path, read_only=True) as conn:
    for _ in range(5):
        t = time.perf_counter(); load_index(conn)
        print("load_index", round((time.perf_counter() - t) * 1000, 1), "ms")
for _ in range(10):  # a 1ª paga o embedder; ignorar
    t = time.perf_counter(); search(cfg, "gate de segurança")
    print("search_hybrid", round((time.perf_counter() - t) * 1000, 1), "ms")
```

## Testes

- [ ] `tests/unit/test_vector_index.py` (novo): `load_index` novo igual ao antigo (copiar a versão por linha para dentro do teste como referência) em dados aleatórios, com e sem `vector` float32 (clone sem vetores locais).
- [ ] O mesmo arquivo: 2ª chamada devolve o **mesmo objeto**; `store_vectors`, `DELETE FROM documents` (cascata) e `INSERT OR REPLACE` mudam `vec_gen` e o próximo `load_index` devolve outro objeto. **Falha antes do conserto.**
- [ ] `tests/integration/test_search.py`: busca, reindexa um arquivo com texto novo, busca de novo: o texto novo aparece (cache não serve índice velho).
- [ ] `tests/integration/test_pipeline.py`: migração aplica sobre banco `0006` existente sem perder dados; `PRAGMA user_version` bate com `SCHEMA_VERSION`.
- [ ] Teste de banco aberto em `mode=ro` (como a busca faz): `vec_gen` legível, cache funciona.

## Notas

- Confirmado em `vectors.py:75-99` e `service.py:118`. O banco do painel e do hub não usam `load_index`.
- WAL: `mtime` do arquivo principal não muda a cada commit; por isso contador, não `mtime` (a RAGX-0097 já registrou essa pendência).
- Migração é irreversível para versões antigas do RAGX: um banco com `user_version` maior é recusado ("atualize o RAGX", `storage/db.py:100-104`). Registrar no CHANGELOG.
- O `INSERT` do primeiro índice dispara um gatilho por linha (≈6,6 mil `UPDATE` em `meta` dentro da mesma transação); medir o custo no primeiro índice e registrar. Se pesar mais de 3%, trocar por incremento explícito em `store_vectors` mais os poucos pontos de exclusão.
- Memória: o cache segura a matriz inteira por banco. Aceitável abaixo do limiar de 100 mil chunks (`ANN_THRESHOLD`).

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0134)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
