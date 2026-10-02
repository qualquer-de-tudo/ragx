# RAGX-0169 — Benchmark local de modelos de embedding e reranker de código

| | |
|---|---|
| **Fase** | 21 — Recuperação v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0167` · `RAGX-0132` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #4 e #5) · [05-busca.md](../../docs/05-busca.md) · [adr/ADR-0004-embeddings.md](../../docs/adr/ADR-0004-embeddings.md) |
| **Status** | `review` |

## Objetivo

Hoje o modelo do índice é o `paraphrase-multilingual-MiniLM-L12-v2` (384d, versionado a 192d), de paráfrase, e o híbrido com ele **não superou** o keyword. A auditoria aponta candidatos treinados em código (Qwen3-Embedding-0.6B, jina-code) e um reranker local no top-30, mas **não tem número nenhum** de recall nem de latência em CPU para eles ("sem fonte: medir"). Esta tarefa entrega o **harness** que mede, no corpus do próprio repo, só o que **já está em disco** (decisão humana: sem baixar modelos grandes). Ela **termina em `review`**: adotar um modelo é decisão de uma pessoa e é da `RAGX-0103`.

## Entregáveis

- [x] **Levantar o que há em disco** e registrar em Andamento: modelos do Ollama (`GET http://127.0.0.1:11434/api/tags`; hoje só `nomic-embed-text:latest`, 274 MB) e cache do fastembed (`.ragx/cache/models`, hoje o MiniLM quantizado, 241 MB). O fastembed 0.8.0 instalado lista `jinaai/jina-embeddings-v2-base-code` (768d, apache-2.0) e `nomic-embed-text-v1.5`, mas **não** lista Qwen3-Embedding (só via Ollama) nem `jina-code-embeddings-0.5B`
- [x] Arquivo de candidatos `tests/eval/models.yaml` (`name`, `provider`, `model`, `dim`, `kind: embedding|reranker`), com o atual, `ollama:nomic-embed-text`, `fastembed:jinaai/jina-embeddings-v2-base-code`, `ollama:qwen3-embedding:0.6b` e os rerankers do `TextCrossEncoder` do fastembed
- [x] `src/ragx/search/bench.py`: `probe(candidate)` diz `disponivel`, `ausente` ou `incompativel` **sem baixar nada** (Ollama: nome em `/api/tags`; fastembed: carga com `HF_HUB_OFFLINE=1` e `cache_dir` do projeto; falha vira `ausente`); recusa `base_url` que não seja loopback (nenhum byte do projeto sai da máquina, ADR-0004)
- [x] `run_embedding(cfg, candidate, cases)`: copia o índice com a API de backup do SQLite para uma raiz temporária (`.ragx/bench/<nome>/`), apaga os embeddings, reembute os chunks com o candidato (`embed_pending`) e roda `evaluate` (`search/evaluation.py:123`) em `semantic` e `hybrid` sobre `tests/eval/queries.yaml` **e** `tests/eval/gold-git.yaml` (`RAGX-0167`). O `.ragx/knowledge.db` real **nunca** é escrito
- [x] Por candidato, medir: tempo de carga fria, chunks/s no reembed, latência de `embed_query` (p50/p95 em 20 consultas), tamanho dos vetores no banco, recall@5, MRR, nDCG@10 com IC95%
- [x] `run_reranker(cfg, candidate, cases)`: reordena o top-30 do híbrido do índice atual com `fastembed.rerank.cross_encoder.TextCrossEncoder` e mede recall@5/MRR **e** latência de 30 pares em CPU (p50/p95). Fica só no harness: o reranker de produção é a `RAGX-0108`
- [x] Comando `ragx bench models [--candidates tests/eval/models.yaml] [--only NOME] [--dry-run] [--out .ragx/bench/resultado.json]` em `cli/commands/bench_cmd.py`, registrado em `cli/main.py`; `--dry-run` só lista o que está em disco e estima o tempo por `chunks/s` de 64 chunks; recusa estimativa acima de 20 min sem `--force-slow`
- [x] Tabela de resultados escrita em Andamento e linha no CHANGELOG; documentar o comando em `docs/14-cli.md` (há teste que cobra todo comando documentado) e um parágrafo em `docs/05-busca.md`

## Fora de escopo

- **Baixar** modelo (`ollama pull`, download do fastembed) ou instalar dependência: candidato ausente é só relatado, com a linha de como baixar escrita para a pessoa
- Trocar o modelo do índice ou os prefixos de consulta (`RAGX-0103`, `RAGX-0104`); integrar reranker à busca (`RAGX-0108`)
- Modelos de 7B ou mais (auditoria 24, 7.3) e GPU: o benchmark roda no que a máquina tem e registra qual processador usou
- Mudar o `ragx.toml` do projeto ou o formato do índice

## Critérios de aceite

- [x] `uv run ragx bench models --dry-run` termina em menos de **5 s**, sem rede além de `127.0.0.1`, e imprime, por candidato, `disponivel`/`ausente`
- [x] Depois de um `ragx bench models` completo, o `.ragx/knowledge.db` real tem os **mesmos** `embeddings` e `embedding_models` de antes (teste e conferência manual)
- [x] O resultado mostra, para ao menos MiniLM e `nomic-embed-text`, a tabela abaixo preenchida; candidato ausente aparece como `ausente`, nunca como zero
- [ ] **NÃO ATENDIDO**: A latência do reranker em CPU para 30 pares tem número publicado (a auditoria declara que não existe). Nenhum reranker está em disco e a tarefa proíbe baixar; o harness (`run_reranker`, com teste de função injetada) mede assim que um estiver no cache
- [x] Reranker com licença não comercial (`jinaai/jina-reranker-v2-base-multilingual` é `cc-by-nc-4.0` no catálogo do fastembed) sai marcado `licenca: nao-comercial` e fora de qualquer recomendação

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| recall@5 híbrido, MiniLM atual (26 manuais) | 0,65 (`docs/05-busca.md`, n=26, IC largo) | **0,62** [0,54–0,70] nos 132 manuais; **0,60** [0,51–0,68] nos 134 do git |
| recall@5 híbrido, nomic-embed-text | 0,77 (RAGX-0103, n=26, medido uma vez) | **0,71** [0,63–0,78] nos 132 manuais; **0,65** [0,57–0,72] nos 134 do git |
| Latência de `embed_query` quente, p50 | 3 ms (MiniLM, auditoria C-08) | MiniLM **3,6 ms** (p95 4,4); nomic via Ollama **14,9 ms** (p95 38,5) |
| Reranker, 30 pares em CPU | sem número | **ainda sem número**: nenhum reranker em disco (os três candidatos aparecem como `ausente`) |

Comando: `uv run ragx bench models --out .ragx/bench/resultado.json`

## Testes

- [x] `tests/unit/test_bench.py`: `probe` com `urlopen` simulado (modelo presente, ausente, daemon fora do ar) devolve o status certo; `base_url` remoto é recusado; a estimativa de tempo dispara a recusa
- [x] `tests/integration/test_bench.py`: projeto fixture com dois candidatos `hashing` (dim 64 e 128); o relatório traz os dois, o banco original fica intacto (contagem de `embeddings`) e a raiz temporária some ao fim
- [x] `tests/unit/test_documentacao.py` continua verde (comando `bench` e `bench models` documentados)
- [x] `tests/security/test_architecture.py` continua verde: o harness só lê o índice, nunca arquivo do projeto

## Notas

Ao terminar, o loop marca `review` (não `done`) e escreve a recomendação **sem aplicá-la**. Armadilhas: o nome de modelo do fastembed não é o nome do repositório no Hugging Face (o MiniLM está em `models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`), então detectar pelo nome da pasta falha; use a carga offline. O `localhost` do Ollama custa ~2 s por requisição no Windows (`RAGX-0132` corrige com `127.0.0.1`); sem ela, o `chunks/s` do Ollama sai falsamente lento. A comparação só é justa com os prefixos de cada modelo (`RAGX-0104`); se ela ainda não estiver feita, registrar isso ao lado do número. Se o conjunto-ouro (`RAGX-0167`) não existir, rodar só com o manual e dizer que o IC é largo.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0169)` na branch `feat/v2`

## Andamento

- 2026-10-02 — **`blocked`, nada implementado.** depende da RAGX-0167 (agora `blocked` pelo conjunto-ouro da fase 14); além disso a tarefa só entrega o harness e fecha em `review` por regra do roteiro (baixar modelos grandes é decisão humana). Verificado nos arquivos das dependências (todas ainda com `Status = todo`/`review`). Quando a dependência fechar, voltar o status para `todo` e retomar daqui.

## Andamento

- 2026-10-02 — **Levantado o que há em disco**: Ollama (`/api/tags`) só tem `nomic-embed-text:latest` (274 MB, GGUF F16, nomic-bert); o cache do fastembed tem só o MiniLM quantizado (241 MB). O fastembed instalado lista `jinaai/jina-embeddings-v2-base-code` (768d, apache-2.0), `nomic-embed-text-v1.5` e quatro rerankers (`Xenova/ms-marco-MiniLM-L-6/12`, `BAAI/bge-reranker-base`, `jinaai/jina-reranker-v1-tiny/turbo-en`), mas **não** Qwen3-Embedding.
- **Feito**: `tests/eval/models.yaml` (8 candidatos, com licença e a linha de como baixar); `search/bench.py` (`Candidate`, `probe` sem baixar nada, `assert_loopback`, `estimate_seconds`, `run_embedding` em CÓPIA do índice pela API de backup, `run_reranker`, `to_jsonable`); `ragx bench models [--candidates] [--only] [--dry-run] [--out] [--force-slow]`; docs `14-cli` e `05-busca`; CHANGELOG. `--dry-run` em 3,4 s, só loopback.
- **Medido** (tabela em `docs/05-busca.md`): MiniLM hybrid 0,62 / 0,60 (manual / git) e nomic via Ollama 0,71 / 0,65, MRR 0,52 → 0,56 e 0,47 → 0,49; nomic é ~4x mais lento por consulta (14,9 contra 3,6 ms) e usa o dobro do espaço (28,7 contra 14,3 MB). Com nomic, o híbrido passa o keyword (0,71 contra 0,70) no conjunto manual; com o MiniLM não passava.
- **Conferido**: o `.ragx/knowledge.db` real tem os mesmos 9.329 embeddings e o mesmo modelo antes e depois do benchmark completo; a raiz temporária some ao fim (teste). Um erro meu corrigido no meio: a primeira medição do MiniLM deu 9.807 chunks/s porque o cache de embedding do repositório devolveu vetores prontos; o benchmark agora roda com `embedding.cache = false` (91,7 chunks/s, o número real).
- **Para a pessoa decidir** (por isso `review`, como a tarefa manda): adotar o `nomic-embed-text` (RAGX-0103). O número a favor é consistente nos dois conjuntos, mas dentro dos intervalos; o custo é latência e espaço. Esta tarefa não trocou nenhum modelo nem mexeu no `ragx.toml`.
- **Critério NÃO atendido**: latência de reranker (acima). **Não verificado**: Linux e macOS; os candidatos que exigem download (nomic v1.5, jina-code, qwen3, rerankers) nunca rodaram.
- Testes: `tests/unit/test_bench.py` (13) e `tests/integration/test_bench_modelos.py` (5, com dois candidatos `hashing` de 64 e 128 dimensões: relatório com os dois, banco original intacto, raiz temporária removida, candidato com provider desconhecido vira `incompativel` sem derrubar o outro, reranker de brinquedo e reranker ausente). Dois arquivos com o mesmo nome base colidem no pytest, por isso o de integração se chama `test_bench_modelos.py`.
