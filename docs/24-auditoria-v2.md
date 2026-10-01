# 24 — Auditoria para a v2: velocidade, tokens, frescor e painel

Segunda auditoria do RAGX, feita em 2026-09-30, depois da primeira
([23](23-auditoria-e-evolucao-do-rag.md)). A 23 olhou **a qualidade da
recuperação**; esta olha o que o produto promete: **economizar tokens, não
deixar o Claude lento e manter o índice sempre atualizado**, mais o painel.

> **Como ler.** A seção 1 é o resumo. A 2 diz o que a auditoria anterior já
> cobria. As seções 3 a 6 são os achados, por área, com o ID que as tarefas
> citam (`C-` core de leitura, `M-` integração com o Claude, `I-` indexação e
> frescor, `U-` painel). A 7 é a pesquisa de mercado. A 8 diz o que **não** foi
> medido.
>
> **Convenção.** *Medido* = número reproduzido nesta máquina (Windows, CPU,
> ~12 projetos no hub, carga variável de outros processos: tempos são limites
> superiores). *Lido* = leitura de código, sem execução. Onde só há o segundo,
> o texto diz.

---

## 1. Resumo

O RAGX já tem as peças certas. O problema desta rodada não é arquitetura: é
que **três promessas do produto são quebradas por defeitos pequenos e
localizados**.

| Promessa | O que acontece | Causa |
|---|---|---|
| **Economizar tokens** | Um `build_context` de 3.000 tokens entrega **7.684** (2,6×). A economia que o painel mostra está superestimada. | O conteúdo sai duas vezes (`fragments` e `markdown`), com JSON indentado (C-01, M-03). |
| **Não deixar lento** | A indexação sem mudança leva 15 s, o `refresh` 26–91 s, o hook de sessão 0,5 s, a primeira busca de cada sessão 3–5 s. | A poda de diretórios fica desligada (M-01), `refresh` roda `sync` completo (M-02), o hook carrega a CLI inteira (M-08), o embedder é carregado sob demanda (M-06). |
| **Sempre atualizado** | Edição não commitada nunca entra no índice por conta própria. O caminho que o hint manda usar custa de meio minuto a um minuto e meio. O cache do `build_context` pode servir resultado de outro filtro. | Só há hooks de git (M-10); o cache ignora filtros (C-04). |

E por cima disso: **o agente quase não chama o RAGX** (3 de 38 sessões, M-05).
Economia que não é usada é zero. O conjunto de 33 ferramentas, das quais 28
nunca foram chamadas, é parte da causa (M-04).

### Os dez achados que mais valem

| # | Achado | Número | Esforço |
|---|---|---|---|
| 1 | Poda de diretórios desligada em subárvore com `.gitignore` aninhado e negação (M-01) | 19.120 arquivos vistos para 643 mantidos; 12,8 s de 15 s. Varredura corrigida: 0,14–0,26 s | 3 h |
| 2 | `build_context` entrega o conteúdo duas vezes (C-01, M-03) | 7.684 tokens para um pedido de 3.000; só `markdown`: −60% | 4–6 h |
| 3 | `refresh` roda índice + `sync` e regrava `knowledge/` (M-02) | 26 s (processo) a 91 s (MCP sob carga) | 5 h |
| 4 | 33 ferramentas MCP, 28 sem uso (M-04) | 6 ferramentas: 419 tokens contra 2.660 (−84%) | 10–12 h |
| 5 | `load_index` por busca, em laço Python (C-02) | 70–80 ms = ~75% da busca quente; vetorizado 18,7 ms | 3 h |
| 6 | Cache do `build_context` ignora filtros e versão parcial (C-04) | demonstrado: `lang=markdown` e depois `lang=python` devolveram o mesmo pack | 2 h |
| 7 | Hook de sessão e de git carregam a CLI inteira (M-08, M-09) | 481–659 ms contra 41–56 ms (stdlib) | 4 h + 2 h |
| 8 | Embedder frio por processo (M-06, C-08) | 3–5 s e ~680 MB por servidor | 1 h (aquecer) |
| 9 | Painel: polling de `git`, conexões e telemetria sem pausar (U-01..U-04) | ~290 processos `git`/min com 12 projetos; ~2,7 s de filhos a cada 30 s; log relido inteiro a cada 5 s | 14 h |
| 10 | Adoção: ferramenta deferred que exige ToolSearch (M-05) | 3 de 38 sessões chamaram | 5 h |

---

## 2. O que a auditoria 23 já cobria (não repetir)

A fase 14 (RAGX-0097..0114) tem 18 tarefas; **4 estão `done`** (0097 cache do
embedder, 0098 nDCG, 0100 IC95%, 0102 separar `task/`). As outras 14 seguem
`todo` e continuam válidas: trocar o modelo (0103), prefixos de consulta
(0104), RRF (0105), estratégia por intenção (0106), cross-encoder (0108),
resumos do dicionário (0109), enxugar (0110), níveis (0111), confiança (0112),
frescor no resultado (0113), chunking AST TS/JS/PHP (0114), conjunto de
avaliação ampliado (0099), `relevance` (0101), expansão do grafo por orçamento
(0107).

Esta auditoria **corrige** dois pontos da 23:

- A tarefa 0107 diagnosticou "209 nós de expansão". Medido de novo: eram
  **sementes** (158 a 533), e a BFS para em ≤6 nós visitados. O problema é a
  semeadura e o filtro ignorado (C-03), não o tamanho da expansão.
- A 0097 deixou pendente o cache de matriz de `load_index`. Aqui ele ganha
  tarefa própria (C-02) com invalidação por contador, não por `mtime`.

A v2 **não substitui** a fase 14: ela herda as 14 pendentes como
pré-requisito de qualidade e acrescenta velocidade, tokens, frescor e painel.

---

## 3. Core de leitura (`C-`)

Corpus: o próprio repo, 6.587 chunks, 598 documentos, 31 MB, MiniLM 384d
(versionado a 192d). Não há N+1 em `search_hybrid`: 1 conexão, 5 `SELECT`s
úteis, hidratação em um único `IN (...)`. O único laço SQL real é a BFS do
grafo. O desperdício está em outro lugar.

| ID | Sev. | Achado | Evidência | Medido |
|---|---|---|---|---|
| **C-01** | alta | `build_context` devolve `fragments[].content` **e** `markdown`, em JSON com `indent=2`; `estimated_tokens` só conta o `content`; o cabeçalho de fragmento custa ~33 tokens e o orçamento assume 12 | `mcp/server.py:431-453`, `context/engine.py:151`, `budget.py:37` | pedido 3.000 → **7.684** no fio (markdown sozinho: 3.068). `search_hybrid` de 10 hits: 2.925 tokens, 1.440 de conteúdo. `get_dictionary`: 8.854 no fio contra 7.098 compacto |
| **C-02** | alta | `load_index` roda em toda busca, com `dequantize` e `l2_normalize` linha a linha; a docstring promete cache que não existe | `storage/vectors.py:75-99`, `search/service.py:118` | 69–80 ms (≈75% do `search_hybrid` quente de 104–172 ms); vetorizado 18,7 ms (diff máx. 6e-8). Extrapolado, não medido: 500k chunks ≈ 6 s e 1,1 GB |
| **C-03** | alta | A expansão do grafo semeia **todas** as entidades dos documentos dos 100 melhores chunks e ignora `SearchFilters` | `graph/service.py:105-111,153`, `traversal.py:62,66`, `store.py:241` | 12 de 12 consultas: 158–533 sementes, `truncated`, ≤6 visitados; chunks adicionados pelo grafo: 0 em 9 consultas, 1–3 nas outras 3; com `path_glob`, 27 de 50 resultados fora do filtro; ~160 ms de custo |
| **C-04** | alta | O cache do `build_context` não inclui `filters`, pesos, `reserve_ratio`, `min_sources` nem `work_paths`; a versão é `MAX(index_runs.id)`, visível antes de a indexação acabar; sem despejo | `context/engine.py:318-333`, `indexing/pipeline.py:161,267` | **demonstrado**: `lang=markdown` e depois `lang=python`, mesma query → `cached=True`, mesmo pack |
| **C-05** | média | `scope` é aceito e ignorado em `search_hybrid`, `search_knowledge` e `build_context`; `search_scoped` existe e nunca é registrado | `mcp/server.py:421-429,546,605-625`, `claude_hint.py:285` | `scope="all"` consulta só o projeto atual, e o agente acredita que consultou o conjunto |
| **C-06** | média | Editar um arquivo apaga todos os embeddings dele e as pontes entidade→chunk | `storage/repositories.py:89`, `0003_embeddings.sql:15`, `0004_graph.sql:9` | 19 chunks idênticos reinseridos: embeddings 19 → 0, pontes 18 → 0 até a próxima consolidação (`watch.full_sync_every=25`) |
| **C-07** | média | `load_index` escolhe o modelo mais recente do banco, não o configurado | `storage/vectors.py:102-109`, `search/service.py:121-129` | `hashing dim=64` contra índice 192d: `ValueError: matmul`; mesma dimensão e outro modelo: resultado aleatório, em silêncio |
| **C-08** | média | Estado frio pesado; cache de embedder com `state_dir` na chave; teto de 4 instâncias com FIFO | `embeddings/__init__.py:28-36`, `tokens.py:56-63` | 1ª busca 1,5 s; 1º `build_context` 2,3 s; tiktoken 0,9 s; `ragx --version` 0,63–0,67 s |
| **C-09** | média | Dicionário grande e fixo | — | 7.098 tokens compactos (`services` = 3.031); já na fase 14 (0109/0110/0111) |
| **C-10** | baixa | Sem vetores locais (clone novo) a busca perde 26% do top-10 | coarse int8@192 de um modelo não-Matryoshka | recall@10: 1,000 (dois estágios) → 0,735 (só coarse); já parcial na 0103 |
| **C-11** | baixa | `ragx context "q"` sem `--tokens` falha | `cli/context_cmd.py:20` | `rc=2`, `0 is not in the range 200<=x<=200000` |
| **C-12** | baixa | Micro-custos: MMR em laço Python (17,7 ms contra 0,8 ms vetorizado, seleção idêntica); contador heurístico (+11% em prosa e +29% em código contra cl100k); query embutida 2× em `build_context`; `SecurityGate` caminha a árvore no `dictionary.build` | `context/dedup.py:86-106`, `tokens.py:24-39` | ver coluna Achado |

**Latência medida por operação**

| Operação | Medido |
|---|---|
| Abrir conexão SQLite (ro) | 0,3 ms |
| FTS5 keyword (SQL) | 0,6–6 ms |
| `load_index` atual / vetorizado | 69–80 ms / 18,7 ms |
| `embed_query` quente / carga fria | 3 ms / 1,5–1,6 s |
| `search_hybrid` quente / frio | 104–172 ms / 2,5 s |
| `build_context` quente sem cache / frio / cache hit | 221–367 ms / 2,3 s / 5,5–7,5 ms |
| Grafo `degrees()` / `expand` | 8 ms / 10–11 ms |
| `dictionary.build` | 1,0 s |

**O que está bom e não deve mudar:** índices e planos SQL (`EXPLAIN` com
`SEARCH` em tudo que é quente), PRAGMAs (WAL, `synchronous=NORMAL`,
`mmap_size` 256 MB), busca vetorial em dois estágios (recall@10 = 1,000), filtro
antes do top-K, hidratação em um `IN`, escape de query FTS5, RRF, diversificação
por documento, cache de embedder por processo, dedup/MMR sem re-embeddar,
orçamento por densidade com reserva de fontes, `cap()` que recusa em vez de
truncar em silêncio, conexão `mode=ro`.

---

## 4. Integração com o Claude (`M-`)

Medido com a máquina carregada por outros processos e três servidores
`ragx mcp serve` vivos: tempos são limites superiores. `tiktoken` não estava
instalado, então tokens de ferramenta são `chars/4`.

### 4.1 Custo fixo em tokens por sessão

| Item | Tokens (~) | Quando |
|---|---:|---|
| `instructions` do servidor | 130 | toda sessão com o servidor registrado |
| Lista de nomes deferred (33 ferramentas) | 200 | idem |
| Hint de SessionStart | 285 | projeto indexado; **repete em cada subagente** |
| ToolSearch das 3 ferramentas do hint | 343 | mais uma ida e volta ao modelo |
| **Total, caminho deferred, sessão que usa** | **~960** | |
| Se não fosse deferred: 33 ferramentas (nome+descrição+schema) | **2.660** | todo turno |
| `tools/list` completo no fio, com `outputSchema` | 3.450 | `outputSchema` (2.576 chars) não serve ao modelo |
| `get_playbook` | 885 | sob demanda |
| `get_dictionary` (indentado; compacto 5.100) | 8.660 | sob demanda |

*Lido, não medido:* o modo `auto` do Claude Code só adia as ferramentas quando
passam de ~10% do contexto; quem usa só o RAGX pagaria os 2,66k a cada turno.

### 4.2 Latência

| Operação | Medido |
|---|---|
| Python vazio | 48–68 ms |
| `ragx claude hint` (SessionStart) | **481–659 ms** (12 execuções) |
| Protótipo do hint só com stdlib | 41–56 ms |
| `post-commit`, parte síncrona | 539–1041 ms |
| `post-checkout` de arquivo (deveria ser no-op) | 468–615 ms |
| Indexação em segundo plano pós-commit | p50 15,6 s · p95 37,6 s · máx 56,8 s (n=53) |
| Indexação sem nenhuma mudança | 7,6–8,8 s |
| `ragx mcp serve` até `initialize` | 0,96–1,28 s |
| 1ª `search_hybrid` do processo | 3,0–3,3 s (logs reais 3,0–5,0 s) |
| `search_hybrid` seguintes | 0,14–0,55 s |
| `refresh` com 4 arquivos mudados | 34 s |
| `refresh` sem mudança (em processo / via MCP sob carga) | 26 s / 72–91 s |
| Varredura do watcher: hoje / com a poda corrigida | 5,3–8,6 s / **0,14–0,26 s** |

### 4.3 Achados

| ID | Sev. | Achado | Evidência | Medido |
|---|---|---|---|---|
| **M-01** | crítica | A poda de diretórios fica desligada em qualquer subárvore com `.gitignore` aninhado que tenha negação. `_negacoes` = `[('src/app',False),('src/app/.vscode',False)]` (de `!.vscode/extensions.json`) e a cláusula `d.startswith(prefixo+"/")` bloqueia a poda de tudo abaixo de `src/app` | `security/ignore_engine.py:175-181` | `can_prune("src/app/node_modules")` e `("src/app/dist")` → `False`; 19.120 arquivos vistos, 643 mantidos; `iter_files` = 12,8 s dos 15 s. O watcher consome um núcleo (2 s de intervalo, varredura de 5–8 s) |
| **M-02** | alta | `refresh` roda índice **e** `sync` completo e regrava `knowledge/`; a descrição, o playbook e o hint dizem "barato quando nada mudou" | `mcp/operations.py:206-210`, `sync/service.py` | `rehydrate` 13,7 s (relê tudo só para um relatório descartado), `index_project` 9,1 s, `serialize` 0,95 s, grafo 0,93 s, dicionário 0,58 s, federação 0,81 s; 26 s em processo, 72–91 s via MCP. **Efeito comprovado:** medir `refresh` nesta auditoria sujou `knowledge/` (155 modificados, 422 novos) |
| **M-03** | alta | `build_context` entrega ~2,5× o orçamento e a telemetria grava `estimated_tokens` como `tokens_delivered` | `mcp/server.py:101-128,431-453` | 26.735 chars (~6,7k tokens) contra 2.401 declarados; economia logada 92,7%, com a entrega real ~82%. O baseline é o arquivo inteiro (`size_bytes/4`): um agente com Grep não leria 16 arquivos inteiros, então a economia real contra Grep é **desconhecida** |
| **M-04** | alta | 33 ferramentas, 28 sem nenhuma chamada nos logs e transcripts; schemas com títulos, `anyOf null`, `default` e `outputSchema` | `mcp/server.py:589-767` | só `build_context`, `search_hybrid`, `get_dictionary`, `get_playbook` e `sync` foram chamadas. Proposta de 6 ferramentas medida em protótipo: **419 tokens contra 2.660 (−84%)** |
| **M-05** | alta | Quase ninguém chama o RAGX | transcripts do Claude desde 24/09 | 38 sessões em projetos indexados, 3 chamaram (8%); fora deste repo, 1 em ~30. Funil: 8 sessões com hint → 4 carregaram via ToolSearch → 3 chamaram. A ferramenta chega deferred e exige ToolSearch; Grep e Read já estão carregados |
| **M-06** | alta | A 1ª busca semântica de cada processo custa 3–5 s e ~680 MB; cada sessão ou perfil sobe um servidor novo | `embeddings/__init__.py` | construção do `FastEmbedEmbedder` 3,98 s (ONNX 1,8 + tokenizer 0,95 + imports 1,05); `build_context` real 3,2–8,5 s; cada servidor roda 3 processos |
| **M-07** | média | A indexação sem mudança carrega o modelo de embedding antes de saber se há algo pendente | `indexing/embed.py:46` (antes de `missing_chunk_ids`, linha 84) | o no-op custa 7,6–8,8 s; parte é o modelo (2–4 s), o resto é M-01 |
| **M-08** | média | O hook de SessionStart carrega a CLI inteira (26 módulos, typer, pydantic) e roda em cada subagente | `cli/main.py:10-36` | 481–659 ms contra 41–56 ms; ~20 `session_start` em 2 minutos de uma sessão com subagentes |
| **M-09** | média | O hook de git é síncrono e dispara até quando não faz nada | `githooks.py:63-71`, `cli/hooks_cmd.py:84` | 539–1041 ms de bloqueio por commit; 468–615 ms por checkout de arquivo. A indexação em si roda destacada |
| **M-10** | média | Edições não commitadas ficam fora do índice e o único caminho (`refresh`) custa 26–91 s | `githooks.py`, `claude_hint.py:255` | com M-01 e M-02 corrigidos o `refresh` incremental deve cair para ~1–2 s (**estimativa, não medido**) |
| **M-11** | média | Formato das respostas: `indent=2`, `project` repetido por hit, `chunk_id` com 34 chars, `score` com 6 casas, nulos, `structuredContent` além do texto | `mcp/server.py:169-181` | compacto: −18% na busca, −41% no dicionário, −40% em `get_document`, −28% em `get_entity`. Busca com snippet de 200 chars e `get` sob demanda: 2,4k → 0,55k (−77%, **estimado**) |
| **M-12** | baixa | A telemetria não permite medir erro nem consumo real: sem `ok`/`err_code`/`resp_chars`; 22 registros no total, 11 sem `session` | `mcp/server.py:101-128` | taxa de erro não calculável; p50/p95 por ferramenta com amostra de 1 a 8 |
| **M-13** | baixa | Concorrência é sólida (WAL, `busy_timeout=5000`, `index.lock` com pedido pendente; 3 buscadores + 1 indexador em paralelo: 0 erros). Sobram: modelo ONNX por servidor, cache de modelos por projeto (251 MB neste repo), `pid_alive` com PID reutilizado no Windows | `storage/db.py:21-28`, `indexing/lock.py:57-78` | — |

---

## 5. Indexação e frescor (`I-`)

Medido em cópias do repo e em projetos sintéticos (2.000 arquivos, 18,5 mil
chunks); o `.ragx/` real não foi tocado. No Windows, cada `open` custou ~2,7 ms
(provável antivírus) e os tempos oscilam 2–3× entre rodadas. A fase 14 só toca
esta área em 0113 (`todo`, só informa `stale`) e 0114 (chunking AST).

| ID | Sev. | Achado | Evidência | Medido |
|---|---|---|---|---|
| **I-01** | crítica | `refresh` do MCP roda `run_sync` completo; o playbook e a descrição dizem "barato". O `sync` relê, passa pelo gate e rechunka **todos** os arquivos só para contar `ok/missing` e descarta o resultado; `serialize` reescreve todo `knowledge/` | `mcp/operations.py:210`, `watch/monitor.py:113`, `sync/service.py:95`, `mcp/playbook.py:52` | `refresh` sem mudança: 11,4–21,3 s (repo real) contra 1,0 s do `index` puro; 2.000 arquivos: `sync` 70,6 s, dos quais `rehydrate` 57 s |
| **I-02** | alta | **Frescor sem dono**: nada lê `watch.enabled` (config morta); o watcher só roda se a pessoa abrir `ragx watch`; hooks são opt-in e só cobrem commit/merge/troca de branch; não existe reindexação por caminho (`iter_files(only=)` existe e não é usado); `freshness.compute` custa 1,0–1,6 s por chamada (5–6 subprocessos git) | `walk.py:38`, `githooks.py:195`, `pipeline.py` | reindexar 1 arquivo: 1,3–2,0 s; protótipo só dos arquivos tocados: **130–270 ms** (+0,3–0,4 s de imports em processo novo); `python -c pass` = 0,097 s |
| **I-03** | alta | `localhost` do Ollama custa ~2 s por requisição no Windows | `config.py:62`, `embeddings/ollama.py:52,83` | `/api/tags`: 2,05–2,1 s contra 6–12 ms em `127.0.0.1`; `/api/embed` de 1 texto 2,06 s contra 23–44 ms; por chunk: 87,5 ms (batch 32) a 2.085 ms (batch 1) contra 9,8–12,3 ms em `127.0.0.1` |
| **I-04** | alta | Os embeddings versionados em `knowledge/` **nunca são lidos** (`read_embeddings` sem chamador); `sync` abre o banco em modo leitura antes de ele existir | `sync/serialize.py:369`, `sync/service.py:63` | num clone novo `ragx search` e `ragx sync` falham ("banco não encontrado"); depois de `ragx index`, os 3.614 chunks são reembedados. `docs/12-git-sync.md` promete "`git clone && ragx search` responde offline" |
| **I-05** | alta | Arquivo `unsupported` ou BLOQUEADO nunca entra em `documents`, então é relido e passa pelo gate **a cada rodada** (e o BLOCK refaz DELETE+INSERT de `security_events`) | `indexing/pipeline.py:158-176,197,225-229` | com 800 `.csv`, `index` sem mudança: 0,4–1,0 s → 4,8–6,9 s; neste repo, 20 arquivos bloqueados reprocessados por rodada |
| **I-06** | alta | Arquivo momentaneamente travado (`OSError`) cai em `gone` e o documento é **apagado** do índice | `walk.py:57-60,100-103`, `pipeline.py:271` | arquivo aberto de forma exclusiva: `removed 1`, documentos e chunks 1/20 → 0/0 até a rodada seguinte. No Windows, antivírus e editor seguram o arquivo logo após o save: é quando o hook dispara |
| **I-07** | média-alta | Reindexar um arquivo apaga todos os chunks dele; `entities.chunk_id` e `relations.evidence_chunk_id` são `ON DELETE SET NULL`; o grafo só é refeito em `sync`, sempre completo | `storage/repositories.py:89`, `0004_graph.sql:9,28`, `graph/service.py:33` | editar 1 arquivo: 7 entidades com `chunk_id` NULL e 27 relações sem evidência; símbolo novo não aparece no grafo; editar 1 linha reescreveu 9 chunks (só 1 texto foi ao embedder) |
| **I-08** | média | Custo fixo de ~3 s em todo `index`: o embedder é construído antes de checar chunks pendentes; `write_status` roda 2× e chama o git; `read_state` usa 3 chamadas git | `indexing/embed.py:46`, `status_file.py`, `gitinfo.py` | `index` sem mudança, repo real: 3,5 s (2,85 s de modelo, 1,0 s de git em 7 chamadas); `hook-run` bloqueia o commit 0,72–1,09 s |
| **I-09** | média | Cache de embedding em **um arquivo por chunk** (`mkdir`+`open`+`write`); `_prefixed` faz um SELECT por chunk; `store_vectors` só grava no fim (kill no meio perde tudo que não foi ao cache de disco) | `embeddings/base.py:97-105`, `indexing/embed.py:144` | primeiro índice de 3.614 chunks: `put` = 10,4 s de 30,5 s (34%), 2,9 ms/chunk; SQL é só ~5% do tempo |
| **I-10** | média | Vetor parcial degrada a busca sem aviso: `degraded` só marca 0 embeddings | `search/service.py:119` | `load_index`: 56 ms (5,9 mil vetores), 155 ms (18 mil) a cada busca |
| **I-11** | média | O watcher roda `snapshot()` a cada 2 s, reconstruindo `SecurityGate` e `IgnoreEngine`, e depois `index_project` caminha a árvore de novo | `watch/monitor.py:68,79` | ciclo ocioso: 170–240 ms (643 arquivos), 330–540 ms (2.000); gate 28–41 ms; `git status` 74–112 ms. ~10–25% de um núcleo parado; a ~20 mil arquivos estoura o intervalo de 2 s |
| **I-12** | média | `knowledge/` instável no Git: `generated_at` em `manifest.json` e `dictionary.json`; shards do grafo por hash de id | `sync/serialize.py:247` | `sync` sem mudança deixa 3 arquivos rastreados sujos; editar 1 função mexeu em 26 arquivos (13 de 16 shards de relations, 6 de 16 de entities) |
| **I-13** | média-baixa | **Junction do Windows** apontando para fora da raiz é percorrida: a guarda anti-escape só vale para `is_symlink()` (adjacente a segurança; o conteúdo ainda passa pelo gate) | `walk.py:161-167`, `security/ignore_engine.py:121` | `linkout/notes.md` fora do projeto foi indexado |
| **I-14** | baixa | `index.jobs` é configuração morta; não há paralelismo | nenhum pool em `src/ragx` | gate 0,31–0,45 ms/KB; leitura ~14,7 ms/arquivo; só pesa no primeiro índice |
| **I-15** | baixa | `importer` usa `execute` por linha; `detect_delta` calcula um diff que só alimenta o relatório | `portability/importer.py:171-240` | operação rara |

**Respostas diretas.** *N+1:* ~4 SQLs por arquivo e ~3 por chunk (2.000
arquivos ≈ 63 mil SQLs reais, 19 commits em lotes de 200); SQL é só ~5% do
tempo, o gargalo não é SQL. *Incremental:* size+mtime com hash de fallback; um
`touch` não reindexa; CRLF/LF não reindexa; BOM novo reindexa. *Renomear:* os
ids de chunk incluem o caminho, então todos os chunks são regravados, mas o
cache por `content_hash` evita o embedder (0 textos). *Apagar:* chunks,
entidades, FTS e vetores somem, 0 órfãos, `integrity-check` do FTS ok.
*Mudar uma função:* 1 de 9 textos vai ao embedder. *Troca de modelo:* apaga os
vetores do modelo anterior; reembedar o repo real custaria ~65–76 s
(estimativa).

**Tempo por operação de escrita**

| Operação | Tempo |
|---|---|
| Primeiro índice, 2.000 arq./18,5 mil chunks (hashing) | 155 s (com embedder real, +~200 s, estimativa) |
| Primeiro índice, 400 arq./3,6 mil chunks | 30 s |
| `index` sem mudança, repo real | 3,5 s |
| `index` sem mudança, 2.000 arq. | 0,95–3,2 s |
| `index` sem mudança, +800 csv | 4,8–6,9 s |
| `index` com 1 arquivo mudado, 2.000 arq. | 1,3–2,0 s |
| Protótipo `touch` de 1 arquivo | 130–270 ms |
| `refresh` MCP sem mudança, repo real | 11,4–21,3 s |
| `sync` sem mudança, 2.000 arq. | 70,6 s |
| Grafo completo | 1,0–1,5 s (2,4 mil entidades) / 5,4–9,2 s (15 mil) |
| Embedding por chunk | 9,8–12,3 ms (Ollama em 127.0.0.1) / 13 ms (fastembed) |
| Ollama em `localhost` | +2,05 s por requisição |
| Ciclo ocioso do watch | 170–240 ms / 330–540 ms |
| `hook-run` (bloqueia o commit) | 0,72–1,09 s |

**Desenho proposto para o frescor (I-02, M-10).** (1) `index_paths(cfg,
paths)` no pipeline, reaproveitando `only=`: uma transação, sem varredura de
árvore, sem git, `status.json` gravado uma vez. (2) `ragx touch` para o hook
`PostToolUse` em `Edit|Write|MultiEdit`: só anexa o caminho a
`.ragx/touch.queue` e retorna (~100 ms). (3) Fila única, reaproveitando
`index.lock`/`index.pending`: quem pega a trava vira o drenador, espera
300–500 ms de debounce e indexa só os arquivos tocados. (4) O servidor MCP,
que vive a sessão inteira, drena a fila antes de cada `search`/`context`
(~0,15–0,3 s só quando algo mudou, com o embedder quente). (5) SessionStart
dispara um `index` destacado. (6) A busca devolve `stale_paths` quando a fila
não está vazia.

**O que já está bom:** atalho size+mtime com hash de fallback (~0,25 ms por
arquivo); ids por conteúdo e cache por `content_hash`; remoção em cascata sem
órfãos; hash normalizado (CRLF/LF); morte forçada no meio do embedding deixa o
banco íntegro e a trava morta é recuperada; 4 indexadores simultâneos saem com
código 0 e o pedido pendente é drenado; indisponibilidade do embedder não
derruba o índice; caminhos longos funcionam com `LongPathsEnabled=1`; arquivo
que vira sensível sai do índice.

---

## 6. Painel (`U-`)

Renderer com 307 kB de JS (93 kB gzip), React 19 e `sql.js` como únicas
dependências; um `App.css` de 2.743 linhas; sem biblioteca de UI, de ícones, de
gráficos, de roteamento nem de estado. Medido: build do renderer, cronometragem
de comandos nesta máquina e screenshots do build estático com bridge simulado
em 1280, 900, 480 e 3440 px. Lido: o resto. **O Electron real não foi aberto:
não há medição de RAM nem de CPU do app.**

| ID | Sev. | Achado | Evidência | Medido / lido |
|---|---|---|---|---|
| **U-01** | alta | A telemetria relê o `mcp.jsonl` inteiro a cada 5 s por projeto; o log não rotaciona | `electron/data/telemetry.ts:70`, `diagnostics.py:47` | lido; hoje os logs têm 0–1 kB, mas crescem sem limite |
| **U-02** | alta | O snapshot dispara 2 `git` por projeto a cada 5 s | `electron/data/git.ts:10-12` | 24 processos por ciclo (12 projetos) ≈ 290/min; 50–120 ms em lote, 440–550 ms isolados |
| **U-03** | alta | A checagem de conexões gasta ~2,7 s de processos filhos a cada 30 s | `electron/connections/checks.ts` | `ragx --version` 0,9–1,7 s, `docker info` 0,8–1,4 s, `docker ps -a` 0,3 s, `tasklist` 0,3 s |
| **U-04** | alta | Os pollers rodam com a janela minimizada ou escondida | `electron/main.ts:401-442,513-518` | lido: nenhum `visibilitychange`, `minimize` ou `powerMonitor` |
| **U-05** | média | O renderer re-renderiza tudo a cada 5 s, sem mudança (`generatedAt` muda; `useNow(5000)` recria `liveIds`; sem `React.memo`) | `src/hooks/useSnapshot.ts:26`, `src/App.tsx:41` | lido |
| **U-06** | média | O fallback de contagem lê `knowledge.db` inteiro na memória | `electron/data/project-stats.ts:43` | bancos de até 150 MB neste hub; hoje não dispara porque todos têm `status.json` |
| **U-07** | média | Janela estreita ou com zoom quebra a casca (topbar e `.content` a 811 px com viewport de 480) | `App.css` (`.topbar`, `.shell`) | medido por screenshot; o mínimo de 900 DIP esconde, mas zoom de 150–200% reproduz 600/450 px de CSS. A 3440 px o conteúdo fica em 1200 px com a topbar a largura toda |
| **U-08** | média | Contraste abaixo de AA: `--ink-3` 4,22:1 (surface), 3,97:1 (surface-2), 3,67:1 (surface-3); botão primário 3,68:1; glifos de 8–9 px; `--line` 1,37–1,70:1 | `src/index.css` | calculado a partir dos tokens |
| **U-09** | média | Falha ao enfileirar ação é silenciosa (só `console.error`) | `src/jobs.ts:4-9,43-46` | lido |
| **U-10** | média | Sem atalhos nem paleta de comandos; a busca da topbar só filtra projetos e redireciona ao digitar | `src/App.tsx:93` | lido |
| **U-11** | média | Sem skeletons; "Carregando…" em tela cheia até o `getSettings` + primeiro snapshot | `src/App.tsx:111` | lido |
| **U-12** | baixa | Acessibilidade pontual: gráfico só com mouse; radiogroups sem setas (3 duplicações) | `src/components/project/TokenSavings.tsx` | lido |
| **U-13** | baixa | Hierarquia: "o índice está em dia?" é a segunda pergunta do detalhe | `src/pages/` | medido por screenshot a 900 px |
| **U-14** | baixa | Sem `requestSingleInstanceLock`, CSP, tray, notificações, auto-update; Electron 33 | `electron/main.ts`, `index.html` | lido (grep vazio) |

**Lacunas de produto** (o dono não vê ou não faz hoje): economia em R$/US$,
linha do tempo por sessão, preview de `build_context`, busca ao vivo (paleta),
saúde do índice com tendência, visão com/sem RAGX acumulada, alerta de
defasagem (bandeja + notificação), auto-update, tema claro. **Não propor:**
mostrar a consulta do agente (o log não a tem, de propósito).

**Lacunas do design system:** faltam escalas de espaço, tipografia e elevação;
um conjunto semântico `--ok/--warn/--err` com `-wash`; primitivos `Segmented`
(duplicado em 3 lugares), `Toast`, `Skeleton`, `EmptyState`, `Modal`
reutilizável, `Tooltip`, `IconButton`; um `Icon` com sprite; breakpoints de
projeto (hoje 640/760/900/960/1000 soltos) e `@container`; CSS dividido por
camada com lint de token.

**Preservar:** bundle leve, contrato de IPC (o renderer só envia `kind` e
`projectId`), disciplina de efeitos (unsubscribe em tudo, `createCoalescedRun`,
`git --no-optional-locks`), `ActivityTail` (leitura incremental por offset: é
o modelo para consertar U-01), estado nunca só por cor, `prefers-reduced-motion`,
`ConfirmButton` em dois cliques, microcopy PT-BR.

---

## 7. Pesquisa de mercado

Fatos de fonte marcados **[F]**, inferência **[I]**. Números de fornecedor
(Augment, Zilliz, Windsurf) são autodeclarados. Dos papers do arXiv li apenas
os abstracts: tratar como sinal, não como prova.

### 7.1 O que mudou desde a auditoria 23

- **[F]** O Claude Code não usa índice vetorial por padrão: a Anthropic migrou
  de RAG local para busca agêntica (grep/glob) por simplicidade, segurança,
  frescor e confiabilidade. O Cursor, ao contrário, mede **+12,5%** de acerto
  somando busca semântica ao grep (cursor.com/blog/semsearch, 06/11/2025).
- **[I]** O RAGX só ganha se devolver contexto **mais preciso e mais barato**
  que o loop grep+Read do agente. Busca ruidosa piora o agente: no CodeGrep,
  BM25 de precisão 0,375 degradou a resolução, e um retriever de precisão 0,677
  cortou 19% dos tokens (arxiv 2608.05886, 06/08/2026). Compatível com o que se
  viu aqui: o híbrido com MiniLM não superou o keyword.
- **[F]** Tool Search é o padrão no Claude Code: reduz o custo das definições
  em ~85% (77K → 8,7K) e subiu a acurácia de 49% para 74%
  (anthropic.com/engineering/advanced-tool-use, 24/11/2025). As
  `instructions` do servidor são truncadas em ~2 KB (code.claude.com/docs/en/mcp).
  Logo o custo real do RAGX está no **tamanho das respostas** e na **adoção**,
  não só nos schemas.

### 7.2 Apostas ordenadas por impacto ÷ esforço

| # | Aposta | Evidência | Esforço |
|---|---|---|---|
| 1 | Dedupe de sessão: não reenviar chunk já entregue (`já entregue: path#id`); teto de `build_context` ≈5k tokens; `response_format: concise\|detailed` | Anthropic, *Writing tools for agents* (11/09/2025): formato conciso ≈1/3 dos tokens. Cache de prompt lê a 0,1× | 1–2 d |
| 2 | `instructions` ≤2 KB, descrições otimizadas para Tool Search, lista de ferramentas **estável** (mudar definições invalida o cache de prompt) | docs MCP e prompt caching | 0,5 d |
| 3 | Chunking tree-sitter multilíngue (6–8 linguagens) | cAST: +4,3 pt de Recall@5 (RepoEval), +2,67 Pass@1 (SWE-bench) (arxiv 2506.15655) | 3–4 d |
| 4 | Embedding treinado em código: Qwen3-Embedding-0.6B (no Ollama; MTEB-Code 75,41; Matryoshka) ou jina-code-embeddings-0.5B (média 78,41 em 25 benchmarks; exige `--pooling last`); medir no `ragx trial` antes de adotar | Hugging Face / jina.ai, 2025 | 0,5–1 d |
| 5 | Reranker local no top-30 (Qwen3-Reranker-0.6B, Apache 2.0); **conferir a licença do jina-reranker-v3 antes de embutir**; latência em CPU **sem fonte: medir** | Contextual Retrieval: −49% de falhas no top-20, −67% com rerank | 2–3 d |
| 6 | Prefixo contextual **determinístico** (caminho, classe, assinatura, docstring) antes de embutir e indexar no FTS; sem LLM | Anthropic, Contextual Retrieval (2024) | 1 d |
| 7 | Merkle de hashes + cache de embedding por hash de chunk | Cursor, 27/01/2026 | 1–2 d |
| 8 | Checar `mtime`+tamanho dos arquivos dos top-k na consulta e reindexar só os alterados; `PostToolUse` assíncrono em `Edit\|Write\|MultiEdit` | docs de hooks do Claude Code (`async: true`) | 1 d |
| 9 | Repo map compacto (PageRank sobre o grafo, ~1k tokens) injetado no SessionStart | Aider repo-map; no Agent Retrieval Bench, o melhor rendimento a 8K tokens (arxiv 2607.24882) | 2–3 d |
| 10 | Subagente explorador (`ragx-explorer.md`) e kit de hooks prontos | Windsurf SWE-grep; isolamento de contexto | 0,3–1 d |
| 11 | Conjunto-ouro do próprio git (mensagem do commit = consulta, arquivos alterados = gabarito) e A/B com `claude -p` com e sem o MCP | ContextBench (arxiv 2602.05892): recall/precisão em nível de arquivo, bloco e linha | 4 d |
| 12 | Índice por worktree/branch, com chunks compartilhados por hash | sem fonte consolidada **[I]** | 2 d |

### 7.3 Hype, ou não vale para este produto

- **Trocar NumPy por sqlite-vec/ANN:** o sqlite-vec é força bruta; NumPy int8
  já responde em dezenas de ms nesse porte.
- **LSP/Serena como núcleo:** estudo de 06/2026 mediu o custo de tokens
  **aumentando** em localização de símbolos (+6% a +118%) (arxiv 2608.13568).
  SCIP exige toolchain por linguagem.
- **Code execution com MCP (sandbox):** −98,7% de tokens num caso, mas custo de
  segurança incompatível com um produto local simples.
- **ColBERT/SPLADE/late chunking:** armazenamento e complexidade sem evidência
  pública forte em código local.
- **LLMLingua e TOON em tudo:** em código a 5×, a correção cai de 78,5% para
  72,3%; um paper de 02/2026 achou que o ganho do TOON some em contexto curto
  (arxiv 2603.03306). Reservar formato tabular para listagens.
- **Contextual retrieval com LLM:** o custo de ~US$ 1,02/M tokens assume a API
  em nuvem; vai contra "rápido e sem nuvem".
- **Modelos de 7B+ para embedding:** peso e latência atrapalham a meta de não
  deixar o Claude lento.
- **Bloquear Grep/Read por hook:** frágil e irritante. Sugerir via
  `additionalContext`.

### 7.4 Painel

shadcn/ui v4 + Tailwind v4 (React 19) é uma base de tokens plausível, mas o
painel hoje não tem **nenhuma** dependência de UI e 93 kB gzip; adotar uma
biblioteca é decisão a pesar contra o peso (a spec da v2 mantém CSS próprio
com tokens). WCAG 2.2 AA: alvos de 24×24 px, foco não oculto, alternativa a
arrastar. `electron-updater` com GitHub Releases (conferir a versão por causa
da CVE-2024-39698, corrigida a partir da 6.3.0-alpha.6); **o executável não é
assinado**, então o auto-update no Windows precisa de teste cuidadoso.

---

## 8. O que não foi medido

- **A economia real contra um agente que usa Grep.** O baseline atual é o
  arquivo inteiro. Sem A/B, "economiza X%" não é afirmável. Vira tarefa (fase
  20).
- **RAM e CPU do Electron em execução.** Só comandos isolados e screenshots do
  build estático.
- **O ganho de latência esperado das correções M-01/M-02/M-07.** São
  estimativas; cada tarefa traz a medição antes/depois como critério de aceite.
- **Latência do reranker em CPU** e o **efeito dos modelos de embedding**
  candidatos neste corpus.
- **Tokenizador do Claude.** O contador heurístico erra +11% (prosa) a +29%
  (código) contra cl100k, que também não é o do Claude.
- **Máquinas diferentes.** Tudo é de uma máquina Windows com GPU AMD e carga
  variável; a ordem de grandeza é robusta, os valores exatos não.
- **Outro corpus.** Tudo é o RAGX indexando a si mesmo.
