# RAGX-0135 — Cache do `build_context` com chave completa e versão confiável

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0134 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (C-04) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V5, S12) · [07-context-engine.md](../../docs/07-context-engine.md) |
| **Status** | `todo` |

## Objetivo

O cache do `build_context` (`context/engine.py:318-393`) devolve o pack de outra consulta. A chave não inclui `filters`, pesos de busca e do grafo, `reserve_ratio`, `min_sources` nem `work_paths`; a versão é `MAX(id)` de `index_runs`, que já conta uma run aberta (`runs.start`, `pipeline.py:161`, e commit por lote, `pipeline.py:267`); não há despejo e a gravação não é atômica. **Demonstrado na auditoria:** `lang=markdown` e depois `lang=python`, mesma consulta, devolveram `cached=True` com o mesmo pack.

## Entregáveis

- [ ] **Teste vermelho primeiro:** a demonstração acima, em `tests/integration/test_context.py`. Registrar o resultado.
- [ ] `_cache_key` (`engine.py:318-330`) recebe `filters` e passa a incluir: `lang`, `kind`, `path_glob`, `min_score`; `cfg.context`, `cfg.search` e `cfg.graph` inteiros (`model_dump()`); `embedding.provider/model/dim/versioned_dim/rescore`; `index.work_paths` e `index.test_paths`; um `CACHE_FORMAT = 1` e o hash do `intents.yaml`; mais a versão do índice. Ao mudar qualquer coisa que altera o resultado, a chave muda.
- [ ] `_db_version` (333-342) vira `_index_version(cfg)`: uma conexão só, devolvendo `(vec_gen, MAX(id))`, onde `vec_gen` vem da RAGX-0134 (`get_meta`) e o `MAX(id)` só olha runs com `finished_at IS NOT NULL AND error IS NULL`, de qualquer modo (inclui as de caminho da RAGX-0140).
- [ ] `build_context` não **grava** no cache enquanto há indexação em curso (`lock.holder(cfg.state_dir)` com `pid_alive`, como em `indexing/status_file.py:54-56`); ler continua permitido.
- [ ] `_cache_write` (369-391) atômico (arquivo temporário no mesmo diretório e `os.replace`) e grava `format` e `key` dentro do JSON; `_cache_read` (349-366) descarta entrada cujo `format` ou `key` não bata.
- [ ] Despejo ao gravar: no máximo 200 arquivos e 32 MB em `.ragx/cache/context/` (valores iniciais, em constantes), removendo os mais antigos por `mtime`.
- [ ] `docs/07-context-engine.md`: o que entra na chave, o que invalida, o que despeja.
- [ ] CHANGELOG.

## Fora de escopo

- Honrar `scope` no MCP: RAGX-0137. Dedupe de sessão (chunk já entregue): RAGX-0159.
- Tokens que saem do `build_context`: RAGX-0154. Telemetria de acerto de cache: RAGX-0156.
- Cache de `search`. Modelo configurado em `_vectors_for`: RAGX-0136.
- Passar `filters` pelo MCP (o contrato `BuildContextRequest` não tem `lang`): decisão da RAGX-0157.

## Critérios de aceite

- [ ] **S12:** 0 acertos incorretos num teste de propriedade com 200 combinações pseudoaleatórias (semente fixa) de consulta, orçamento, filtros, `include_graph`, `depth` e pequenas alterações de `Config`: sempre que `cached=True`, `fragments` e `estimated_tokens` são idênticos ao resultado com `use_cache=False`.
- [ ] A demonstração `lang=markdown` e depois `lang=python` deixa de dar `cached=True`.
- [ ] Reindexar (`index_project`) invalida; reindexar **durante** uma run aberta não faz a run parcial entrar no cache.
- [ ] Acerto de cache continua ≤ 10 ms e o custo extra de montar a chave ≤ 1 ms; erro (miss) sem regressão (221–367 ms).
- [ ] Cache corrompido (JSON truncado, `format` velho) vira miss, nunca exceção.

## Medição

| Métrica | Antes | Depois |
|---|---|---|
| Acertos incorretos (propriedade, 200 casos) | ≥ 1 (demonstrado) | |
| `build_context` com cache hit | 5,5–7,5 ms | |
| `build_context` sem cache, quente | 221–367 ms | |
| Arquivos em `.ragx/cache/context/` após 500 consultas | sem teto | |

Comando: `uv run pytest tests/integration/test_context.py -k cache -q` e, para o tempo, 20 chamadas seguidas de `ragx.context.engine.build_context(cfg, "gate de segurança")` no mesmo processo (a 1ª é miss).

## Testes

- [ ] `tests/integration/test_context.py`: regressão do filtro (falha antes); mudar `cfg.context.dedup_threshold`, `cfg.search.weight_keyword` ou `index.work_paths` muda a chave; mudar `depth`/`include_graph` idem.
- [ ] `tests/integration/test_context.py`: propriedade com `random.Random(1234)` (não há `hypothesis` no projeto), comparando com `use_cache=False`.
- [ ] `tests/integration/test_context.py`: com run aberta (`lock.try_acquire` e `RunRepo.start` sem `finish`), `build_context` não cria arquivo no cache; depois de `finish`, cria.
- [ ] `tests/unit/test_context_units.py`: `_cache_write` atômico (nenhum `.tmp` sobra; escrita interrompida por exceção não deixa JSON parcial), despejo respeita o teto, entrada com `key` errada é descartada.
- [ ] `tests/integration/test_context.py`: `test_cache_invalida_apos_reindexar` (linha 151) continua verde.

## Notas

- Confirmado em `engine.py:96-101` (leitura antes de recuperar), `engine.py:318-342`, `pipeline.py:161` e `pipeline.py:267`.
- Windows: `os.replace` sobre arquivo aberto por outro processo pode falhar com `PermissionError`; tratar como "cache é otimização" (engolir e seguir), como o `except OSError` atual.
- `vec_gen` não muda quando só os chunks mudam sem embedding novo (`--no-embed`); por isso a versão também usa o `MAX(id)` de runs terminadas. Se a RAGX-0140 não gravar `index_runs` para indexação por caminho, esta chave precisa de outro sinal (ex.: contagem e `MAX(indexed_at)` de `documents`); conferir ao fazer.
- Não incluir a consulta em claro em nome de arquivo nem em log: o nome é o hash (`[:32]`), como hoje.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0135)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
