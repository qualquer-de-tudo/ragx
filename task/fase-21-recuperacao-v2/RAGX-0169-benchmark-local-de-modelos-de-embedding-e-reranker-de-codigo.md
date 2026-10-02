# RAGX-0169 — Benchmark local de modelos de embedding e reranker de código

| | |
|---|---|
| **Fase** | 21 — Recuperação v2 |
| **Prioridade** | P2 — média |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0167` · `RAGX-0132` |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (7.2 #4 e #5) · [05-busca.md](../../docs/05-busca.md) · [adr/ADR-0004-embeddings.md](../../docs/adr/ADR-0004-embeddings.md) |
| **Status** | `blocked` |

## Objetivo

Hoje o modelo do índice é o `paraphrase-multilingual-MiniLM-L12-v2` (384d, versionado a 192d), de paráfrase, e o híbrido com ele **não superou** o keyword. A auditoria aponta candidatos treinados em código (Qwen3-Embedding-0.6B, jina-code) e um reranker local no top-30, mas **não tem número nenhum** de recall nem de latência em CPU para eles ("sem fonte: medir"). Esta tarefa entrega o **harness** que mede, no corpus do próprio repo, só o que **já está em disco** (decisão humana: sem baixar modelos grandes). Ela **termina em `review`**: adotar um modelo é decisão de uma pessoa e é da `RAGX-0103`.

## Entregáveis

- [ ] **Levantar o que há em disco** e registrar em Andamento: modelos do Ollama (`GET http://127.0.0.1:11434/api/tags`; hoje só `nomic-embed-text:latest`, 274 MB) e cache do fastembed (`.ragx/cache/models`, hoje o MiniLM quantizado, 241 MB). O fastembed 0.8.0 instalado lista `jinaai/jina-embeddings-v2-base-code` (768d, apache-2.0) e `nomic-embed-text-v1.5`, mas **não** lista Qwen3-Embedding (só via Ollama) nem `jina-code-embeddings-0.5B`
- [ ] Arquivo de candidatos `tests/eval/models.yaml` (`name`, `provider`, `model`, `dim`, `kind: embedding|reranker`), com o atual, `ollama:nomic-embed-text`, `fastembed:jinaai/jina-embeddings-v2-base-code`, `ollama:qwen3-embedding:0.6b` e os rerankers do `TextCrossEncoder` do fastembed
- [ ] `src/ragx/search/bench.py`: `probe(candidate)` diz `disponivel`, `ausente` ou `incompativel` **sem baixar nada** (Ollama: nome em `/api/tags`; fastembed: carga com `HF_HUB_OFFLINE=1` e `cache_dir` do projeto; falha vira `ausente`); recusa `base_url` que não seja loopback (nenhum byte do projeto sai da máquina, ADR-0004)
- [ ] `run_embedding(cfg, candidate, cases)`: copia o índice com a API de backup do SQLite para uma raiz temporária (`.ragx/bench/<nome>/`), apaga os embeddings, reembute os chunks com o candidato (`embed_pending`) e roda `evaluate` (`search/evaluation.py:123`) em `semantic` e `hybrid` sobre `tests/eval/queries.yaml` **e** `tests/eval/gold-git.yaml` (`RAGX-0167`). O `.ragx/knowledge.db` real **nunca** é escrito
- [ ] Por candidato, medir: tempo de carga fria, chunks/s no reembed, latência de `embed_query` (p50/p95 em 20 consultas), tamanho dos vetores no banco, recall@5, MRR, nDCG@10 com IC95%
- [ ] `run_reranker(cfg, candidate, cases)`: reordena o top-30 do híbrido do índice atual com `fastembed.rerank.cross_encoder.TextCrossEncoder` e mede recall@5/MRR **e** latência de 30 pares em CPU (p50/p95). Fica só no harness: o reranker de produção é a `RAGX-0108`
- [ ] Comando `ragx bench models [--candidates tests/eval/models.yaml] [--only NOME] [--dry-run] [--out .ragx/bench/resultado.json]` em `cli/commands/bench_cmd.py`, registrado em `cli/main.py`; `--dry-run` só lista o que está em disco e estima o tempo por `chunks/s` de 64 chunks; recusa estimativa acima de 20 min sem `--force-slow`
- [ ] Tabela de resultados escrita em Andamento e linha no CHANGELOG; documentar o comando em `docs/14-cli.md` (há teste que cobra todo comando documentado) e um parágrafo em `docs/05-busca.md`

## Fora de escopo

- **Baixar** modelo (`ollama pull`, download do fastembed) ou instalar dependência: candidato ausente é só relatado, com a linha de como baixar escrita para a pessoa
- Trocar o modelo do índice ou os prefixos de consulta (`RAGX-0103`, `RAGX-0104`); integrar reranker à busca (`RAGX-0108`)
- Modelos de 7B ou mais (auditoria 24, 7.3) e GPU: o benchmark roda no que a máquina tem e registra qual processador usou
- Mudar o `ragx.toml` do projeto ou o formato do índice

## Critérios de aceite

- [ ] `uv run ragx bench models --dry-run` termina em menos de **5 s**, sem rede além de `127.0.0.1`, e imprime, por candidato, `disponivel`/`ausente`
- [ ] Depois de um `ragx bench models` completo, o `.ragx/knowledge.db` real tem os **mesmos** `embeddings` e `embedding_models` de antes (teste e conferência manual)
- [ ] O resultado mostra, para ao menos MiniLM e `nomic-embed-text`, a tabela abaixo preenchida; candidato ausente aparece como `ausente`, nunca como zero
- [ ] A latência do reranker em CPU para 30 pares tem número publicado (a auditoria declara que não existe)
- [ ] Reranker com licença não comercial (`jinaai/jina-reranker-v2-base-multilingual` é `cc-by-nc-4.0` no catálogo do fastembed) sai marcado `licenca: nao-comercial` e fora de qualquer recomendação

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| recall@5 híbrido, MiniLM atual (26 manuais) | 0,65 (`docs/05-busca.md`, n=26, IC largo) | (medir, com IC95%) |
| recall@5 híbrido, nomic-embed-text | 0,77 (RAGX-0103, n=26, medido uma vez) | (medir no ouro do git) |
| Latência de `embed_query` quente, p50 | 3 ms (MiniLM, auditoria C-08) | (medir por candidato) |
| Reranker, 30 pares em CPU | sem número | (medir) |

Comando: `uv run ragx bench models --out .ragx/bench/resultado.json`

## Testes

- [ ] `tests/unit/test_bench.py`: `probe` com `urlopen` simulado (modelo presente, ausente, daemon fora do ar) devolve o status certo; `base_url` remoto é recusado; a estimativa de tempo dispara a recusa
- [ ] `tests/integration/test_bench.py`: projeto fixture com dois candidatos `hashing` (dim 64 e 128); o relatório traz os dois, o banco original fica intacto (contagem de `embeddings`) e a raiz temporária some ao fim
- [ ] `tests/unit/test_documentacao.py` continua verde (comando `bench` e `bench models` documentados)
- [ ] `tests/security/test_architecture.py` continua verde: o harness só lê o índice, nunca arquivo do projeto

## Notas

Ao terminar, o loop marca `review` (não `done`) e escreve a recomendação **sem aplicá-la**. Armadilhas: o nome de modelo do fastembed não é o nome do repositório no Hugging Face (o MiniLM está em `models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`), então detectar pelo nome da pasta falha; use a carga offline. O `localhost` do Ollama custa ~2 s por requisição no Windows (`RAGX-0132` corrige com `127.0.0.1`); sem ela, o `chunks/s` do Ollama sai falsamente lento. A comparação só é justa com os prefixos de cada modelo (`RAGX-0104`); se ela ainda não estiver feita, registrar isso ao lado do número. Se o conjunto-ouro (`RAGX-0167`) não existir, rodar só com o manual e dizer que o IC é largo.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0169)` na branch `feat/v2`

## Andamento

- 2026-10-02 — **`blocked`, nada implementado.** depende da RAGX-0167 (agora `blocked` pelo conjunto-ouro da fase 14); além disso a tarefa só entrega o harness e fecha em `review` por regra do roteiro (baixar modelos grandes é decisão humana). Verificado nos arquivos das dependências (todas ainda com `Status = todo`/`review`). Quando a dependência fechar, voltar o status para `todo` e retomar daqui.
