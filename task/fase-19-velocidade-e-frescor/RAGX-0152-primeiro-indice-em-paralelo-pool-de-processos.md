# RAGX-0152 — Primeiro índice em paralelo (pool de processos)

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0146 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-14) · [25-spec-v2.md](../../docs/25-spec-v2.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [15-configuracao.md](../../docs/15-configuracao.md) · [02-seguranca.md](../../docs/02-seguranca.md) · [ADR-0008](../../docs/adr/ADR-0008-security-gate-antes-do-parser.md) |
| **Status** | `todo` |

## Objetivo

`index.jobs` é configuração morta: `IndexCfg.jobs` existe (`src/ragx/config.py:34`, e `docs/15-configuracao.md:30` diz "0 = cpu_count"), mas não há nenhum pool em `src/ragx` (I-14). O primeiro índice lê, passa pelo gate, faz parse e fatia um arquivo de cada vez: gate a 0,31–0,45 ms/KB, leitura ~14,7 ms/arquivo, e o primeiro índice de 2.000 arquivos (18,5 mil chunks) levou **155 s** só com `hashing` (400 arquivos / 3,6 mil chunks: 30 s). Só pesa no primeiro índice (e em `--full`); a rodada incremental não muda. A tarefa paraleliza leitura, gate, parse e chunking e mantém a escrita no banco no processo principal.

## Entregáveis

- [ ] **Medir primeiro**, com a RAGX-0146 já aplicada: tempo por fase do primeiro índice de 2.000 arquivos (varredura e decisões baratas, `read_bytes`, `gate.admit`, `parsers.parse`, `chunk_document`, escrita no banco, embedding). **Se leitura + gate + parse + chunk forem menos de 50% do total**, parar, deixar a tarefa em `review` com os números e não implementar
- [ ] `src/ragx/walk.py:33-115`: dividir `iter_files` em dois estágios sem mudar o resultado. (1) `iter_candidates(...)`, no processo principal, faz as decisões baratas (ignorado, `unchanged` por `size+mtime`, grande demais, nome na deny-list) e devolve `(caminho, rel, stat)` dos que precisam ser lidos; (2) `read_candidate(path, rel, st, gate, prefix)` faz `read_bytes`, a sonda de binário e `gate.admit` e devolve o `WalkedFile`. `iter_files` passa a ser a composição dos dois (mesma saída, mesmos testes)
- [ ] `src/ragx/indexing/parallel.py` (novo): `init_worker(root, policy, scan_content, min_entropy, extra_exclude, extra_include, chunk_opts, include_unknown)` constrói **um `SecurityGate` completo** por worker (inclusive o `IgnoreEngine`: nenhum atalho no gate) e `process_batch(batch)` roda `read_candidate` + `parsers.parse` + `chunk_document`, devolvendo para cada arquivo só o necessário (veredito e `findings`, `content_hash`, `doc_kind`, `lang`, `title`, `degraded`, `redacted`, `Chunk`s). O módulo **não** importa `ragx.config` nem `typer` (cada worker em `spawn` pagaria ~0,3–0,5 s de pydantic)
- [ ] `src/ragx/indexing/pipeline.py:129-325` (`_index_once`): quando o projeto tem pelo menos `PARALLEL_MIN_FILES` (padrão 200) candidatos a ler e `jobs != 1`, usar `ProcessPoolExecutor(max_workers=jobs, mp_context=spawn, initializer=init_worker, ...)` com lotes de ~16 arquivos e janela limitada de lotes em voo (≈ 4 × `jobs`), consumindo os resultados **na ordem original**, de modo que a escrita (`docs.upsert`, `replace_for_document`, `events`, lotes de commit) é a mesma do caminho sequencial. Fontes de conhecimento base (`_all_sources`, linhas 328-360) continuam sequenciais
- [ ] `jobs`: `0` = `min(os.cpu_count(), 4)` (teto para não multiplicar 100–200 MB de RAM por worker), `1` = sequencial (comportamento de hoje), `N` = N workers; corrigir o texto de `docs/15-configuracao.md:30`. `dry_run` e `embed_only` ficam sequenciais
- [ ] Erro em worker propaga com o caminho do arquivo; `KeyboardInterrupt` faz `shutdown(cancel_futures=True)` e nenhum processo filho sobra (nem no Windows); a rodada registra `error`/`interrupted` como hoje
- [ ] `docs/04-indexacao.md` (seção do primeiro índice) e CHANGELOG com o tempo antes/depois

## Fora de escopo

- Paralelizar o embedding (continua no processo principal; ver RAGX-0146) e a escrita no SQLite (um escritor só)
- Rodadas incrementais pequenas e `index_paths` (RAGX-0140): abaixo do limiar, nada muda
- Conhecimento base (`@base/...`), que tem orçamento menor e fica sequencial
- Tree-sitter e novos parsers (RAGX-0114)
- Reaproveitar o pool entre rodadas (watcher)

## Critérios de aceite

- [ ] Com 4 workers, o primeiro índice do projeto sintético de 2.000 arquivos fica **≥ 2× mais rápido** que o sequencial na mesma base (meta provisória; ajustar depois de "medir primeiro")
- [ ] `jobs = 1` ≈ tempo de hoje (±5%) e rodada com menos de `PARALLEL_MIN_FILES` não cria pool; `index` sem mudança (S4) não piora
- [ ] **Resultado idêntico** ao sequencial: mesmos `documents`, `chunks` (ids, conteúdo, ordinais), `security_events` e `fts`, `jobs=1` contra `jobs=4`
- [ ] Nenhum segredo novo no índice com `jobs=4` (suíte `tests/security` repetida com o limiar baixado a 1)
- [ ] Sem processo filho órfão depois de erro e depois de Ctrl+C, em Windows e Linux

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Primeiro índice, 2.000 arquivos / 18,5 mil chunks (hashing) | 155 s (sem a 0146) | |
| Primeiro índice, 400 arquivos / 3,6 mil chunks | 30 s | |
| Fração do tempo em leitura + gate + parse + chunk | medir primeiro | |
| `index` sem mudança, repo real | 3,5 s | |

Comando: `uv run python scripts/medir_indice_inicial.py --arquivos 2000 --provider hashing --jobs 1` e de novo com `--jobs 4` (o mesmo script da RAGX-0146).

## Testes

- [ ] `tests/integration/test_index_parallel.py` (novo): projeto sintético com o limiar baixado, `jobs=1` e `jobs=4` produzem tabelas idênticas (`documents`, `chunks`, `security_events`, `chunks_fts`); arquivo ilegível/binário/grande/bloqueado dá o mesmo veredito
- [ ] `tests/integration/test_index_parallel.py`: exceção forçada num worker propaga com o caminho e deixa a rodada com `error`; nenhum filho vivo (`psutil` não é dependência: checar `multiprocessing.active_children()`)
- [ ] `tests/unit/test_walk.py` (novo): `iter_files` antigo e a composição `iter_candidates` + `read_candidate` devolvem a mesma lista em projeto com ignorados, `unchanged`, binário e deny-list
- [ ] `tests/security/test_surfaces.py` e `tests/security/test_gate.py` repetidos com `jobs=2` e limiar 1 (parametrizar `indexado`): nenhum segredo de `tests/fixtures/secret_project` em `chunks`, `fts`, `embeddings` nem `knowledge`
- [ ] `tests/security/test_architecture.py`: `walk.py` continua chamando `gate.admit(`; `ragx.indexing.parallel` só lê arquivo por `read_candidate`

## Notas

- Confirmado em `src/ragx/config.py:34`, `docs/15-configuracao.md:30` e na busca por `ProcessPool|multiprocessing|concurrent.futures|ThreadPool` em `src/ragx` (nenhum resultado); `src/ragx/walk.py:33-115` é o gerador atual e `src/ragx/indexing/pipeline.py:178-268` o laço que o consome.
- **O gate roda no worker, inteiro.** Seria tentador passar um `IgnoreEngine` falso (as decisões de ignorar já foram tomadas no principal), mas a regra do projeto é que o gate não tem atalho; o custo de construir o engine uma vez por worker é pequeno diante de minutos de índice. O teste de equivalência `jobs=1` contra `jobs=4` é o que garante.
- Windows usa `spawn`; o Linux 3.12 ainda usa `fork` por padrão. Fixar `spawn` em todos para o comportamento ser o mesmo e para não herdar a conexão SQLite aberta. O launcher `ragx.exe` e `python -m ragx.cli.main` precisam ser testados: o `spawn` reimporta o módulo principal.
- O pickle do resultado leva `Chunk`s e texto; manter o lote pequeno e a janela de lotes em voo limitada para não encher a RAM se o escritor for o gargalo.
- Ordem: `executor.map` preserva a ordem de entrada, mas empilha tudo; usar `submit` com janela. O resultado precisa chegar na ordem para a escrita ser reproduzível.
- `read_candidate` preserva o tratamento de `OSError` da RAGX-0133 (arquivo travado não vira "sumiu"), e `iter_candidates` aplica o veredito em cache da RAGX-0139 (`file_verdicts`) se ela já estiver `done`: ambos continuam decisões do processo principal, antes de despachar ao pool.
- Se a medição inicial mostrar que o tempo está no banco/FTS ou no embedder, esta tarefa não ajuda: fechar em `review` com os números.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0152)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
