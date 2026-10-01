# RAGX-0144 — Clone novo usa os embeddings versionados em `knowledge/`

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0136 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-04, C-10) · [25-spec-v2.md](../../docs/25-spec-v2.md) · [12-git-sync.md](../../docs/12-git-sync.md) · [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) · [ADR-0010](../../docs/adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) · [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `todo` |

## Objetivo

O projeto versiona os embeddings (int8, 1,4 MB para os 6.587 chunks deste repo) justamente para que um clone responda a buscas sem recalcular nada, e `docs/12-git-sync.md` promete "`git clone && ragx search` responde offline". Na prática `serialize.read_embeddings` **não tem nenhum chamador** (I-04): num clone novo `ragx search` e `ragx sync` falham com "banco não encontrado" e, depois de um `ragx index`, os **3.614 chunks** do caso medido são reembedados do zero. Esta tarefa faz o clone importar os vetores versionados e só embutir o que de fato falta.

## Entregáveis

- [ ] **Medir primeiro** num clone novo (`git clone` do repo em pasta temporária): comportamento de `ragx sync` e `ragx search`, tempo e número de textos enviados ao embedder no `ragx index`, e recall@10 de `ragx eval` só com int8 contra o índice completo (C-10 mediu 0,735 contra 1,000 para o MiniLM não-Matryoshka)
- [ ] Usar `embedder_id(cfg)` (criada na RAGX-0130 em `src/ragx/embeddings/__init__.py`: o id que `build_embedder(cfg)` produziria **sem construir o modelo**, com a troca do modelo padrão do fastembed de `_construir`, linhas 58-86); esta tarefa não cria outra
- [ ] `src/ragx/sync/service.py:57-76` (`detect_delta`) e `sync()`: banco ausente deixa de ser erro; abrir com `open_db(cfg.db_path)` (cria e migra) ou tratar como "sem último sync". `ragx sync` num clone novo sai com 0
- [ ] `src/ragx/sync/embeddings_import.py` (novo): `import_embeddings(cfg, conn, out_dir)` lê `knowledge/embeddings/manifest.json` e os shards (`serialize.read_embeddings`, **por shard**, sem montar tudo na memória), **recusa** se `manifest["model"] != embedder_id(cfg)` ou se o vetor não tem `versioned_dim` bytes, faz `register_model` e grava `(chunk_id, model_id, vector=NULL, vector_q, q_scale, q_offset)` **só para `chunk_id` que existem em `chunks`**, em lotes, devolvendo contagens (`imported`, `skipped_model`, `skipped_unknown_chunk`, `skipped_bad`)
- [ ] `src/ragx/storage/vectors.py`: `coarse_only_chunk_ids(conn, model_id)` (linhas com `vector IS NULL`); `src/ragx/indexing/embed.py:39-125` (`embed_pending`) ganha `upgrade_coarse: bool = True`: quando o modelo ainda não tem vetor nenhum e há `knowledge/embeddings`, importa **antes** de calcular `pending`; com `upgrade_coarse` completa o float32 das linhas só-grosseiras (cache de embedding primeiro)
- [ ] `sync()` chama `index_project(..., embed=False)`, depois `import_embeddings`, depois `embed_pending(upgrade_coarse=False)`: embute só o que falta (arquivo novo ou editado) e deixa os vetores importados grosseiros; `SyncReport` ganha `imported_embeddings` e `coarse_only`
- [ ] Busca com vetor só grosseiro avisa: a RAGX-0136 criou `SearchOutcome.partial` (texto `vetores parciais: N de M chunks`, propagado ao MCP, à CLI e ao `stats` do contexto); acrescentar o caso `not index.has_full` (`vetores só grosseiros (int8@192): N chunks sem float32; rode: ragx index --embed-only`) no mesmo campo. `degraded` continua significando "o semântico não rodou"
- [ ] `src/ragx/storage/db.py:36-38` ("banco não encontrado"): se existir `knowledge/manifest.json` ao lado, a mensagem manda rodar `ragx sync`
- [ ] Corrigir `docs/12-git-sync.md:59` ("responde, offline, sem embedder"): a consulta ainda precisa de embedder para virar vetor; sem ele a busca cai para palavra-chave. Descrever o fluxo real (`git clone && ragx sync`), e atualizar `docs/03-modelo-de-dados.md` (linhas só-grosseiras)

## Fora de escopo

- Trocar o modelo de embedding, ou adotar um Matryoshka de verdade (RAGX-0103, fase 14, decisão humana)
- Completar o float32 em segundo plano logo após o `sync` (hoje: instrução na saída e `index --embed-only`)
- Reidratar o conteúdo dos chunks a partir de `knowledge/` (hoje `sync` descarta o resultado, `service.py:95`; é a RAGX-0131)
- Fazer `ragx search` construir o índice sozinho num clone sem banco

## Critérios de aceite

- [ ] Num clone novo, `ragx sync` sai com 0 e a busca seguinte devolve resultados
- [ ] Textos enviados ao embedder durante o `sync` de um clone sem alterações locais: **0** (contador no teste; antes, todos os chunks)
- [ ] Depois de `ragx index --embed-only`, `partial` some e os IDs devolvidos nas 26 consultas de `tests/eval/queries.yaml` são **idênticos** aos de um índice construído do zero
- [ ] Modelo diferente do configurado: nada é importado, o `sync` avisa, e os vetores existentes não são apagados
- [ ] `uv run pytest tests/security` verde

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Chunks reembedados num clone novo (caso medido, 400 arquivos) | 3.614 | |
| `ragx sync` num clone novo | falha ("banco não encontrado") | |
| Tempo do `sync` até a 1ª busca útil | medir primeiro | |
| recall@10, só int8 contra completo (referência da auditoria) | 0,735 / 1,000 | |

Comando: `uv run python scripts/medir_clone_novo.py <url-ou-pasta-do-repo>` (criar; clona, roda `sync`, imprime textos enviados ao embedder, tempo e recall@10 via `ragx eval --json`).

## Testes

- [ ] `tests/integration/test_sync.py`: clone sem `.ragx/` → `sync` ok e `embeddings` com `vector IS NULL` para os chunks importados; contador do embedder falso em 0
- [ ] `tests/integration/test_sync.py`: arquivo editado depois do clone → só os chunks dele vão ao embedder; modelo diferente → 0 importados e aviso; shard com magic errado ou `vector_q` de tamanho errado → ignorado e contado
- [ ] `tests/integration/test_search.py`: busca com linhas só-grosseiras devolve `partial` (e `degraded` vazio); após `embed_pending(upgrade_coarse=True)`, `partial` some e o resultado é idêntico ao do índice do zero
- [ ] `tests/security/test_sync_embeddings_import.py`: shard que cita `chunk_id` de arquivo hoje bloqueado ou apagado → 0 linhas gravadas; contagem de `embeddings` ≤ contagem de `chunks`; o import não grava conteúdo
- [ ] Regressão que falha hoje: `ragx sync` em clone sem banco (e2e, `tests/e2e/test_cli_sync_busy.py` ou arquivo novo)

## Notas

- Confirmado em `src/ragx/sync/serialize.py:369-391` (`read_embeddings`, único uso: a definição), `src/ragx/sync/service.py:63` (`open_db(..., read_only=True)` antes de o banco existir) e `:93-95` (`_hydrated` descartado), e em `src/ragx/storage/vectors.py:93` (**uma** linha sem `vector` faz `full=None` para o índice inteiro) e `:151-161` (`missing_chunk_ids` ignora linhas só-grosseiras, por isso o upgrade precisa de função própria). `knowledge/embeddings/manifest.json` deste repo: `count 6587`, `dim 384`, `versioned_dim 192`, `fastembed:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Armadilha: `embed_pending` apaga os vetores de qualquer modelo diferente do atual (`embed.py:67-82`). Importar vetores de **outro** modelo seria desfeito na rodada seguinte; daí a igualdade com `embedder_id(cfg)` ser obrigatória.
- `serialize` grava o int8 já truncado e renormalizado (`quantize`); `load_index` renormaliza ao carregar. Não renormalizar duas vezes no import: gravar `vector_q`, `q_scale`, `q_offset` como vieram.
- A ordem das tarefas importa: a RAGX-0136 define `partial` e a escolha do modelo configurado; esta só prova o caso importado. O contador `vec_gen` da RAGX-0134 é mantido por gatilhos em `embeddings` (INSERT/UPDATE/DELETE), então o import e o upgrade invalidam o cache de `load_index` sem código extra.
- Windows: `read_bytes` dos shards com `newline` irrelevante (binário); caminhos de `knowledge/` já usam `/`.
- Se o recall só-int8 medido for bem melhor que 0,735 (outro modelo), ainda assim manter o aviso: é o texto que diz a verdade sobre o estado do índice.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0144)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
