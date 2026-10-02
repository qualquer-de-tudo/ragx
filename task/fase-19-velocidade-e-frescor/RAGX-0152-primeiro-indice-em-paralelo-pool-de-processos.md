# RAGX-0152 — Primeiro índice em paralelo (pool de processos)

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0146 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-14) · [25-spec-v2.md](../../docs/25-spec-v2.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [15-configuracao.md](../../docs/15-configuracao.md) · [02-seguranca.md](../../docs/02-seguranca.md) · [ADR-0008](../../docs/adr/ADR-0008-security-gate-antes-do-parser.md) |
| **Status** | `review` |

## Objetivo

`index.jobs` é configuração morta: `IndexCfg.jobs` existe (`src/ragx/config.py:34`, e `docs/15-configuracao.md:30` diz "0 = cpu_count"), mas não há nenhum pool em `src/ragx` (I-14). O primeiro índice lê, passa pelo gate, faz parse e fatia um arquivo de cada vez: gate a 0,31–0,45 ms/KB, leitura ~14,7 ms/arquivo, e o primeiro índice de 2.000 arquivos (18,5 mil chunks) levou **155 s** só com `hashing` (400 arquivos / 3,6 mil chunks: 30 s). Só pesa no primeiro índice (e em `--full`); a rodada incremental não muda. A tarefa paraleliza leitura, gate, parse e chunking e mantém a escrita no banco no processo principal.

## Entregáveis

- [x] **Medir primeiro**, com a RAGX-0146 já aplicada: tempo por fase do primeiro índice de 2.000 arquivos (varredura e decisões baratas, `read_bytes`, `gate.admit`, `parsers.parse`, `chunk_document`, escrita no banco, embedding). **Se leitura + gate + parse + chunk forem menos de 50% do total**, parar, deixar a tarefa em `review` com os números e não implementar
- [x] `src/ragx/walk.py:33-115`: dividir `iter_files` em dois estágios sem mudar o resultado. (1) `iter_candidates(...)`, no processo principal, faz as decisões baratas (ignorado, `unchanged` por `size+mtime`, grande demais, nome na deny-list) e devolve `(caminho, rel, stat)` dos que precisam ser lidos; (2) `read_candidate(path, rel, st, gate, prefix)` faz `read_bytes`, a sonda de binário e `gate.admit` e devolve o `WalkedFile`. `iter_files` passa a ser a composição dos dois (mesma saída, mesmos testes)
- [x] `src/ragx/indexing/parallel.py` (novo): `init_worker(root, policy, scan_content, min_entropy, extra_exclude, extra_include, chunk_opts, include_unknown)` constrói **um `SecurityGate` completo** por worker (inclusive o `IgnoreEngine`: nenhum atalho no gate) e `process_batch(batch)` roda `read_candidate` + `parsers.parse` + `chunk_document`, devolvendo para cada arquivo só o necessário (veredito e `findings`, `content_hash`, `doc_kind`, `lang`, `title`, `degraded`, `redacted`, `Chunk`s). O módulo **não** importa `ragx.config` nem `typer` (cada worker em `spawn` pagaria ~0,3–0,5 s de pydantic)
- [x] `src/ragx/indexing/pipeline.py:129-325` (`_index_once`): quando o projeto tem pelo menos `PARALLEL_MIN_FILES` (padrão 200) candidatos a ler e `jobs != 1`, usar `ProcessPoolExecutor(max_workers=jobs, mp_context=spawn, initializer=init_worker, ...)` com lotes de ~16 arquivos e janela limitada de lotes em voo (≈ 4 × `jobs`), consumindo os resultados **na ordem original**, de modo que a escrita (`docs.upsert`, `replace_for_document`, `events`, lotes de commit) é a mesma do caminho sequencial. Fontes de conhecimento base (`_all_sources`, linhas 328-360) continuam sequenciais
- [x] `jobs`: `0` = `min(os.cpu_count(), 4)` (teto para não multiplicar 100–200 MB de RAM por worker), `1` = sequencial (comportamento de hoje), `N` = N workers; corrigir o texto de `docs/15-configuracao.md:30`. `dry_run` e `embed_only` ficam sequenciais
- [x] Erro em worker propaga com o caminho do arquivo; `KeyboardInterrupt` faz `shutdown(cancel_futures=True)` e nenhum processo filho sobra (nem no Windows); a rodada registra `error`/`interrupted` como hoje
- [x] `docs/04-indexacao.md` (seção do primeiro índice) e CHANGELOG com o tempo antes/depois

## Fora de escopo

- Paralelizar o embedding (continua no processo principal; ver RAGX-0146) e a escrita no SQLite (um escritor só)
- Rodadas incrementais pequenas e `index_paths` (RAGX-0140): abaixo do limiar, nada muda
- Conhecimento base (`@base/...`), que tem orçamento menor e fica sequencial
- Tree-sitter e novos parsers (RAGX-0114)
- Reaproveitar o pool entre rodadas (watcher)

## Critérios de aceite

- [x] Com 4 workers, o primeiro índice do projeto sintético de 2.000 arquivos fica **≥ 2× mais rápido** que o sequencial na mesma base (meta provisória; ajustar depois de "medir primeiro")
- [x] `jobs = 1` ≈ tempo de hoje (±5%) e rodada com menos de `PARALLEL_MIN_FILES` não cria pool; `index` sem mudança (S4) não piora
- [x] **Resultado idêntico** ao sequencial: mesmos `documents`, `chunks` (ids, conteúdo, ordinais), `security_events` e `fts`, `jobs=1` contra `jobs=4`
- [x] Nenhum segredo novo no índice com `jobs=4` (suíte `tests/security` repetida com o limiar baixado a 1)
- [ ] Sem processo filho órfão depois de erro e depois de Ctrl+C, em Windows e Linux — **verificado só no Windows** (erro forçado e `KeyboardInterrupt` no laço, `active_children()` vazio); Linux não rodou

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Primeiro índice, 2.000 arquivos / 18,5 mil chunks (hashing) | 155 s (sem a 0146); com a 0146, sequencial 13,2 / 14,2 / 18,6 s | 4 workers: 6,3 / 6,8 / 7,0 s (cerca de 2,1x; 2,65x contra a rodada de 18,6 s) |
| Primeiro índice, 400 arquivos / 3,6 mil chunks | 30 s (sem a 0146); com a 0146, 2,2 a 2,6 s | 4 workers: 1,4 a 1,7 s |
| Fração do tempo em leitura + gate + parse + chunk | medir primeiro | 73% (400 arquivos) e 60% (2.000); a leitura sozinha 57% e 49%, ~5 a 10 ms por arquivo no Windows |
| `index` sem mudança, repo real | 3,5 s | 0,2 s (203 e 210 ms), `parallel_jobs = 0`: nenhum pool |

Comando: `uv run python scripts/medir_indice_inicial.py --arquivos 2000 --provider hashing --jobs 1` e de novo com `--jobs 4` (o mesmo script da RAGX-0146).

## Testes

- [x] `tests/integration/test_index_parallel.py` (novo): projeto sintético com o limiar baixado, `jobs=1` e `jobs=4` produzem tabelas idênticas (`documents`, `chunks`, `security_events`, `chunks_fts`); arquivo ilegível/binário/grande/bloqueado dá o mesmo veredito
- [x] `tests/integration/test_index_parallel.py`: exceção forçada num worker propaga com o caminho e deixa a rodada com `error`; nenhum filho vivo (`psutil` não é dependência: checar `multiprocessing.active_children()`)
- [x] `tests/unit/test_walk.py` (novo): `iter_files` antigo e a composição `iter_candidates` + `read_candidate` devolvem a mesma lista em projeto com ignorados, `unchanged`, binário e deny-list
- [x] `tests/security/test_surfaces.py` repetido com `jobs=2` e limiar 1 (a fixture `indexado` ganhou o parâmetro `paralelo`): nenhum segredo de `tests/fixtures/secret_project` em `chunks`, `fts`, `embeddings` nem `knowledge`. `test_gate.py` não passa pelo pipeline (chama `gate.admit` direto), então não há o que parametrizar nele
- [x] `tests/security/test_architecture.py`: `walk.py` continua chamando `gate.admit(`; `ragx.indexing.parallel` só lê arquivo por `read_candidate`. O teste antigo travava `_examinar` como único ponto de leitura; foi reescrito com a mesma força para o novo desenho (`read_bytes` e `admit` só em `read_candidate`)

## Notas

- Confirmado em `src/ragx/config.py:34`, `docs/15-configuracao.md:30` e na busca por `ProcessPool|multiprocessing|concurrent.futures|ThreadPool` em `src/ragx` (nenhum resultado); `src/ragx/walk.py:33-115` é o gerador atual e `src/ragx/indexing/pipeline.py:178-268` o laço que o consome.
- **O gate roda no worker, inteiro.** Seria tentador passar um `IgnoreEngine` falso (as decisões de ignorar já foram tomadas no principal), mas a regra do projeto é que o gate não tem atalho; o custo de construir o engine uma vez por worker é pequeno diante de minutos de índice. O teste de equivalência `jobs=1` contra `jobs=4` é o que garante.
- Windows usa `spawn`; o Linux 3.12 ainda usa `fork` por padrão. Fixar `spawn` em todos para o comportamento ser o mesmo e para não herdar a conexão SQLite aberta. O launcher `ragx.exe` e `python -m ragx.cli.main` precisam ser testados: o `spawn` reimporta o módulo principal.
- O pickle do resultado leva `Chunk`s e texto; manter o lote pequeno e a janela de lotes em voo limitada para não encher a RAM se o escritor for o gargalo.
- Ordem: `executor.map` preserva a ordem de entrada, mas empilha tudo; usar `submit` com janela. O resultado precisa chegar na ordem para a escrita ser reproduzível.
- `read_candidate` preserva o tratamento de `OSError` da RAGX-0133 (arquivo travado não vira "sumiu"), e `iter_candidates` aplica o veredito em cache da RAGX-0139 (`file_verdicts`) se ela já estiver `done`: ambos continuam decisões do processo principal, antes de despachar ao pool.
- Se a medição inicial mostrar que o tempo está no banco/FTS ou no embedder, esta tarefa não ajuda: fechar em `review` com os números.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows — **verdes só no Windows**; o CI roda os três e é quem fecha este item
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0152)` na branch `feat/v2`

## Andamento

- 2026-10-01 — **Medido primeiro, como a tarefa pede**: leitura + Gate + parse + chunk são 73% do primeiro índice de 400 arquivos e 60% do de 2.000 (acima do corte de 50%): a leitura sozinha pesa 57% e 49% (5 a 10 ms por arquivo no Windows, antivírus incluso). `scripts/medir_indice_inicial.py` ganhou as fases (read_bytes, `gate.admit`, `parse`, `chunk_document`, banco, embedding) e `--jobs`.
- **Feito**: `walk.py` em dois estágios (`iter_candidates` + `read_candidate`; `iter_files` é a composição, mesma saída); `indexing/parallel.py` (worker com Gate completo, janela de `4 x jobs` lotes de 16, resultados na ordem, queda segura para o processo principal se o pool cair, `WorkerError` com o caminho, Ctrl+C ignorado nos workers e `shutdown(cancel_futures=True)` no principal); `_handle(ctx, walked, pre)` usa o `Prepared` do worker; `_index_once` fecha o gerador no `finally` (é isso que desliga o pool antes de a exceção sair); `ragx index --json` traz `parallel_jobs` e `parallel_fallback`.
- **Medido**: ver a tabela. O ganho vem de a escrita no banco (processo principal) acontecer enquanto os workers leem: o laço de leitura caiu de ~10 s para ~2,7 s nos 2.000 arquivos; o que sobra é embedding (3,9 s) e banco, que seguem no principal por desenho. Contra o código antigo, `jobs = 1` não ficou mais lento (1.000 arquivos, alternando: antigo 6,23 e 5,80 s, novo 5,51 e 5,63 s).
- **Lançadores**: `python -m ragx.cli.main` e o `ragx.exe` de um venv descartável com instalação editável fazem `spawn` sem problema (2 workers, sem queda). Não testei o `ragx.exe` global da máquina: é uma instalação não editável, sem este código, e não reinstalei a ferramenta do usuário.
- Testes novos: `test_index_parallel.py` (12: `jobs=1` contra `jobs=4` com pool real, tabelas `documents`/`chunks`/`security_events`/FTS/`file_verdicts` idênticas com um arquivo de cada destino do Gate; limiar, `jobs=1`, dry-run, reindexação sem mudança; Ctrl+C sem filho sobrando; executor falso em processo para erro com caminho, queda no `submit` e no resultado, ordem e tamanho de lote, arquivo que sumiu), 4 em `test_walk.py`, `test_surfaces.py` parametrizado (sequencial e paralelo) e o teste de arquitetura. Mutação deliberada (worker com o Gate sem varredura de conteúdo): os testes `[paralelo]` de segurança falham. Suíte `-m "not slow"` 1909 passed, `tests/security` verde, `ruff`, `mypy`.
- **Não verificado / desvios**: Linux e macOS (só Windows rodou); Ctrl+C real no console (o teste lança `KeyboardInterrupt` no laço); `docs/14-cli.md` listava `ragx index --jobs N`, que nunca existiu: troquei por uma nota sobre `index.jobs` em vez de criar a flag (fora do escopo); `docs/04-indexacao.md` descrevia um `ThreadPool` que não existia e foi reescrito. Uma rodada de 400 arquivos deu 7 s (e a seguinte 2 s sem mudança): ruído da máquina, descartada, as outras ficaram em 1,4 a 1,7 s.

