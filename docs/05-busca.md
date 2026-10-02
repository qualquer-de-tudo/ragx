# 05 — Busca (Fase 2)

Fim da Fase 2 = RAG funcional ponta a ponta: `ragx init` → `ragx index .` → `ragx search "..."`.

## Modos

```bash
ragx search "como funciona autenticação"                  # hybrid (padrão)
ragx search "como funciona autenticação" --mode semantic
ragx search "AuthService" --mode keyword
ragx search "auth" --lang php --kind method --limit 5
ragx search "autenticação" --json
```

| Modo | Motor | Bom para |
|------|-------|----------|
| `semantic` | embeddings + cosseno | perguntas em linguagem natural, sinônimos |
| `keyword` | FTS5 / BM25 | nomes exatos de símbolo, códigos de erro, siglas |
| `hybrid` | RRF sobre os dois | padrão — cobre os dois casos |

## Busca semântica

```text
query
  ↓  prefixo de tarefa do modelo (nomic: "search_query: ")
Embedder.embed_query()
  ↓  vetor normalizado
produto escalar contra todos os vetores  (NumPy, matriz em memória)
  ↓
top-K por score
```

Implementação inicial: força bruta com NumPy, em **dois estágios** — consequência do
orçamento de tamanho ([ADR-0010](adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md)):

```python
# [1] busca grosseira nos vetores versionados (int8 @ 256d) — sempre disponível
q8 = quantize_query(query_vec, dim=256)
coarse = vectors_q @ q8                       # (n_chunks,) int32 → float
cand = np.argpartition(-coarse, 100)[:100]

# [2] rescoring exato com float32 @ 768d — só se os vetores locais existirem
if has_full_vectors:
    scores = vectors[cand] @ query_vec
    top = cand[np.argsort(-scores)[:k]]
else:
    top = cand[np.argsort(-coarse[cand])[:k]]  # logo após um clone
```

O estágio 2 é o que recupera a precisão perdida na quantização. Sem ele (logo após
`git clone`, antes de o embedder rodar), a busca continua funcionando com qualidade
um pouco menor — e `ragx eval` reporta as duas condições separadamente, para que a
diferença seja um número publicado e não uma suposição.

Custo real: 200k chunks × 768 dims × 4 bytes = ~600 MB. Por isso o limiar de upgrade
para índice aproximado (`sqlite-vec` / HNSW) é **100k chunks**, definido em
[ADR-0003](adr/ADR-0003-busca-vetorial.md). Abaixo disso, força bruta é mais simples
e mais precisa. A matriz é carregada uma vez por processo e cacheada pela **geração `vec_gen`** (`meta`), mantida por gatilhos em `embeddings`: `mtime` do banco não é confiável sob WAL. O carregamento é vetorizado (7,3 mil vetores: ~17 ms frio, ~0,01 ms com o cache quente) e o `VectorIndex` devolvido é compartilhado e somente leitura.

**Primeira busca de cada processo.** O embedder (modelo ONNX do `fastembed`) e o contador de tokens
são construídos uma vez por processo, com trava por configuração: duas threads que pedem juntas esperam
a MESMA construção. O servidor MCP faz isso em segundo plano ao subir ([09-mcp.md](09-mcp.md),
`[mcp] warmup`), de modo que a primeira busca não paga o carregamento.

Assimetria de query/documento importa: `nomic-embed-text` exige os prefixos
`search_query:` e `search_document:`. Isso é responsabilidade do provider, não do
caller — ver [ADR-0004](adr/ADR-0004-embeddings.md).

## Busca keyword

```sql
SELECT c.id, bm25(chunks_fts, 1.0, 4.0, 2.0, 0.5) AS score
FROM chunks_fts
JOIN chunks c ON c.rowid = chunks_fts.rowid
WHERE chunks_fts MATCH :q
ORDER BY score
LIMIT :k;
```

Pesos do BM25 por coluna: `content=1.0`, `symbol=4.0`, `heading_path=2.0`, `context=0.5` — casar no
nome do símbolo vale muito mais que casar no corpo, e o contexto (caminho, palavras do símbolo, assinatura, docstring; ver
[04 — Indexação](04-indexacao.md)) serve para ACHAR, não para ordenar. Varredura do peso do contexto no conjunto de 152 consultas
(keyword recall@5 / MRR): 0 → 0,705 / 0,473; 0,25 → 0,697 / 0,489; **0,5 → 0,697 / 0,503**; 1,0 → 0,682 / 0,508; 2,0 → 0,705 / 0,523.
Nenhum valor se distingue dos outros dentro do IC (±0,08); ficou o 0,5 da tarefa, que mantém o MRR do híbrido no melhor ponto.

Preparação da query (`search/keyword.py`):

- Escapa operadores FTS5 do input do usuário (`"`, `*`, `NEAR`, `-`) — input do
  usuário nunca é interpretado como sintaxe sem `--raw`.
- Divide `CamelCase` e `snake_case` em termos adicionais: `AuthService` gera também
  `auth` e `service`. Isso é o que faz `ragx search "auth service"` encontrar `AuthService`.
- Aplica `OR` entre termos com `*` de prefixo no último termo (busca incremental).

## Fusão híbrida — RRF

Reciprocal Rank Fusion, sem calibração de score entre motores heterogêneos:

```python
K = 60  # constante padrão da literatura de RRF

def rrf(rankings: dict[str, list[str]], weights: dict[str, float]) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for source, ranked_ids in rankings.items():
        w = weights.get(source, 1.0)
        for rank, chunk_id in enumerate(ranked_ids, start=1):
            scores[chunk_id] += w / (K + rank)
    return scores
```

Pesos padrão: `semantic=1.0`, `keyword=0.8`. Configuráveis em `[search]`.

**Por que RRF e não soma ponderada de scores:** cosseno vive em `[-1, 1]` e BM25 é
ilimitado e dependente do corpus. Normalizar os dois exigiria calibração por projeto.
RRF usa só a posição, é robusto e não precisa de tuning.

Cada motor contribui com `top-K × 3` candidatos antes da fusão (padrão: pede 30
para entregar 10).

## Reranking (pós-fusão)

Ajustes determinísticos, sem modelo extra no MVP:

| Sinal | Efeito |
|-------|--------|
| Match exato do símbolo com a query | ×1.5 |
| `doc_kind = doc` quando a query é pergunta (tem `?`, "como", "o que", "por que") | ×1.2 |
| `doc_kind = code` quando a query parece identificador (CamelCase, `()`, `::`) | ×1.2 |
| Chunk muito curto (< 32 tokens) | ×0.8 |
| Documento com `redacted = 1` | ×0.9 |

Diversidade de fonte: no máximo 3 chunks do mesmo documento nos top-10, para não
devolver 10 métodos do mesmo arquivo. Os excedentes descem para o fim da lista.

Rerank cross-encoder fica registrado como evolução pós-MVP; não entra na Fase 2.

## Contrato de resultado

```python
@dataclass(frozen=True)
class SearchResult:
    chunk_id: str
    document_path: str
    symbol: str | None
    heading_path: str | None
    kind: str
    start_line: int
    end_line: int
    score: float
    content: str
    matched_by: tuple[str, ...]   # ("semantic", "keyword")
    metadata: dict[str, Any]
```

Todo resultado carrega obrigatoriamente: **source, chunk, score, metadata**.
Resultado sem `document_path` é bug, não degradação — o agente precisa poder citar.

### Degradação e vetores parciais

A busca semântica usa o modelo **configurado** (`embedder_id(cfg)`), nunca "o mais recente
do banco". Quando não dá para usá-la, a busca híbrida segue só com keyword e o
`SearchOutcome.degraded` diz por quê:

| Situação | `degraded` |
|---|---|
| Nenhum vetor no banco | `sem embeddings — rode: ragx index --embed-only` |
| Há vetores, mas de **outro** modelo | `o índice vetorial é de X (N vetores), mas a configuração pede Y` |
| O embedder devolve menos dimensões que o índice pede | `o embedder devolveu N dimensões e o índice de Y pede M` |
| Embedder fora do ar | `embedder indisponível (...) — usando só keyword` |

Vetor **parcial** (o embedder caiu no meio de uma indexação) é outra coisa: o semântico
**roda**, só que sobre parte dos chunks. O resultado é válido e incompleto, então não é
`degraded`: vem em `SearchOutcome.partial` (`vetores parciais: N de M chunks`), no
`ragx search --json`, na resposta MCP (só quando existe) e em `stats.partial_vectors` do
`ContextPack`. A correção é `ragx index --embed-only`.

### Frescor: `stale_paths` (RAGX-0141)

Uma edição ainda não reindexada não pode ser invisível. O hook `PostToolUse` do Claude Code enfileira o arquivo editado
(`ragx touch`); antes de buscar, o servidor MCP reindexa a fila (`touchq.settle`). O que ainda ficou para trás (índice
ocupado, falha) volta na resposta como `stale_paths` (até 20 caminhos) e `stale_count`, em vez de a busca fingir que está
tudo em dia. Só aparecem caminhos que o Security Gate admitiria pelo nome. Detalhes e a latência medida em
[09-mcp.md](09-mcp.md#frescor-fila-de-edição-e-stale_paths-ragx-0141).

Saída da CLI:

```text
ragx search "como funciona autenticação"

  1  0.94  docs/auth.md › Autenticação > Fluxo SSO            [semantic+keyword]
         O fluxo de autenticação usa SSO corporativo. O AuthService valida o
         token contra o provedor e mantém sessão no Redis por 30 minutos...

  2  0.91  src/Auth/AuthService.php:24-71 › AuthService.login  [semantic]
         public function login(Credentials $c): Session { ... }

  3  0.87  docs/architecture.md › Camada de Serviços          [semantic]
         ...

  3 resultados em 82 ms  (semantic 41 ms · keyword 6 ms · fusion 1 ms)
```

## Filtros

```bash
--lang python|php|markdown|...
--kind file|class|function|method|section|block
--path "src/auth/**"          # glob sobre rel_path
--limit N                     # padrão 10
--min-score X
```

Filtros são aplicados **antes** do top-K em cada motor (predicado no SQL / máscara
no NumPy), não depois — senão um filtro restritivo devolve lista vazia.

## Avaliação de qualidade

Conjunto de avaliação versionado em `tests/eval/queries.yaml`:

```yaml
- query: "como funciona autenticação"
  relevant_paths: ["docs/auth.md", "src/Auth/AuthService.php"]
- query: "onde o token expira"
  relevant_paths: ["src/Auth/TokenPolicy.php"]
```

`ragx eval` reporta `Recall@5`, `MRR` e `nDCG@10` por modo:

```text
Modo       Recall@5   MRR     nDCG@10
keyword      0.77     0.48     0.79
semantic     0.62     0.44     0.68
hybrid       0.65     0.49     0.78
```

> **Medição real** no repositório do próprio RAGX (26 consultas,
> `fastembed:paraphrase-multilingual-MiniLM-L12-v2`, 1.929 chunks).
> **O híbrido NÃO supera o keyword neste corpus** — ver a análise abaixo.

Meta original da Fase 2: **hybrid > semantic > keyword** em Recall@5, com
hybrid >= 0.80. **Essa meta não foi atingida**, e a investigação apontou três
causas, todas documentadas com evidência:

### O conjunto ampliado (RAGX-0099)

O conjunto tinha 26 consultas. Hoje `tests/eval/queries.yaml` tem **152**, das quais **132 com resposta** e 20 sem, e cada
caso traz `class` (`factual`, `relacionamento`, `depuracao`, `arquitetura`, `configuracao`, `sem_resposta`), `difficulty` (`easy`:
o termo da pergunta aparece no arquivo; `hard`: paráfrase) e `note` (por que aqueles caminhos são os relevantes). As consultas
novas foram escritas à mão a partir do que cada arquivo faz, e não geradas dos chunks (isso seria circular: mede só se a busca
acha o trecho de onde a pergunta saiu). **Atenção:** quem escreveu foi um agente de IA, não uma pessoa que conhece o
repositório; os `relevant_paths` listam o(s) arquivo(s) certo(s), mas outro arquivo também pode responder, e então o recall
medido é um piso. Vale revisão humana, e o teste `tests/unit/test_eval_conjunto.py` impede o conjunto de encolher
(≥ 150 consultas, a largura do IC95% no pior caso abaixo de 0,20, cobertura mínima por classe, nota em todo caso e todo
caminho existente).

`ragx eval` calcula recall@5, MRR e nDCG@10 só sobre as consultas COM resposta, mostra o recall por classe e por dificuldade
(`--json`: `by_class`, `by_difficulty`) e dá às consultas SEM resposta uma métrica própria: a fração delas cujo melhor
resultado tem pontuação igual ou maior que o 10º percentil dos acertos de verdade (falso positivo; é uma régua relativa ao modo,
enquanto a pontuação não for calibrada, RAGX-0101). Medido em 02/10/2026 (`fastembed:paraphrase-multilingual-MiniLM-L12-v2`):

| Modo | Recall@5 | IC 95% | Largura | MRR | nDCG@10 | Sem resposta, falso positivo |
|---|---:|---|---:|---:|---:|---:|
| keyword | 0,69 | [0,61–0,76] | 0,15 | 0,47 | 0,45 | 3/20 |
| semantic | 0,54 | [0,45–0,62] | 0,17 | 0,43 | 0,38 | 1/20 |
| hybrid | 0,62 | [0,54–0,70] | 0,16 | 0,49 | 0,43 | 3/20 |

Os intervalos agora cabem em 0,20, e o resultado é mais firme que o de n=26: **`keyword` e `hybrid` ficam mais perto do que
parecia, e o `semantic` fica claramente atrás do `keyword`**; o `hybrid` tem o melhor MRR mas não o melhor recall@5. Por classe
(acertos/consultas, keyword / semantic / hybrid): relacionamento 11/20, 4/20, 9/20; depuração 14/19, 9/19, 11/19; arquitetura
20/23, 17/23, 19/23; configuração 19/24, 16/24, 19/24; factual 27/46, 25/46, 24/46. As perguntas de relacionamento ("quem chama X")
são as mais fracas em todos os modos, o que aponta para o grafo (RAGX-0145) e não para a fusão.

### O conjunto-ouro derivado do git (RAGX-0167)

Um segundo conjunto, sem mão-de-obra e que cresce sozinho: `ragx gold build` lê o histórico (`git log --no-merges --name-status -M`) e
gera `tests/eval/gold-git.yaml`, em que a **mensagem do commit é a consulta** (sem o prefixo `tipo(escopo):` e sem o sufixo
`(RAGX-0xxx)`) e os **arquivos alterados que existem hoje no índice são os documentos relevantes**. Fora do gabarito: `CHANGELOG.md`,
`knowledge/`, lockfiles e gerados; fora do conjunto: commit de release, consulta com menos de 3 palavras, commit sem arquivo indexado e
commit com mais de `--max-files` (8) arquivos relevantes. Só hash curto, assunto e caminhos saem do git: autor, e-mail e corpo do commit
nunca são lidos; um assunto que dispare o `SecurityScanner`, ou que traga uma palavra comprida com cara de segredo (letra e dígito,
entropia alta), é descartado e contado. A saída é determinística (byte-idêntica entre duas execuções). Vazamento é aceito: o índice está
no HEAD, que já contém a mudança, então o conjunto mede "dada a intenção, ache o lugar", não previsão; `commit` e `kind`
(`code`/`doc`/`mixed`) ficam em cada caso para recortar. Avalie com `ragx eval --queries tests/eval/gold-git.yaml`.

Funil neste repositório (02/10/2026, `ragx gold build --dry-run`, 1,1 s): 251 commits sem merge, 7 de release, 0 com segredo, 1 de consulta
curta, 19 sem arquivo indexado, 90 com arquivos demais, **134 casos**. Resultado do `ragx eval` sobre eles (fastembed multilíngue,
recall@5 e IC95%): keyword **0,72** [0,64–0,79], semantic 0,49 [0,40–0,57], hybrid 0,60 [0,51–0,68]; MRR 0,51, 0,34, 0,47. Os intervalos
cabem em 0,20 (conclusivo). **O mesmo padrão do conjunto manual de 152 consultas: o `keyword` vence o `hybrid`, que vence o `semantic`.** Dois
conjuntos independentes (um escrito à mão por um agente, outro derivado do git) concordando é o que faltava para tratar isso como achado e
não como ruído; é o ponto de partida da recalibração do RRF (RAGX-0105).

### Benchmark local de modelos (RAGX-0169)

`ragx bench models` mede, no corpus do próprio projeto, os modelos de embedding e de reranker que **já estão em disco**: o Ollama
(só em loopback; um `base_url` remoto é recusado, porque nenhum byte do projeto sai da máquina) e o cache do fastembed. Candidato
ausente é relatado como `ausente`, com a linha de como baixar (`tests/eval/models.yaml`), nunca baixado e nunca contado como zero.
Cada candidato roda numa CÓPIA do índice (API de backup do SQLite) em `.ragx/bench/<nome>/`: o `.ragx/knowledge.db` real nunca é
escrito (teste e conferência: 9.329 vetores do mesmo modelo antes e depois). Mede carga fria, chunks/s do reembed (sem o cache de
embedding), latência de `embed_query` (p50/p95), tamanho dos vetores e recall@5 com IC95%, MRR e nDCG@10 em `semantic` e `hybrid`,
nos DOIS conjuntos (152 manuais e 134 do git). `--dry-run` só lista o que há em disco e estima o reembed por 64 chunks reais; estimativa
acima de 20 min exige `--force-slow`. Rerankers (`TextCrossEncoder` do fastembed) reordenam o top-30 do híbrido do índice atual e dão a
latência de 30 pares em CPU; licença não comercial (`cc-by-nc`) sai marcada e fora de qualquer recomendação. **É só o harness: adotar um
modelo é decisão de uma pessoa (RAGX-0103).**

Medido em 02/10/2026 neste repositório (9.329 chunks, CPU e a GPU AMD do Ollama), recall@5 [IC95%] / MRR no modo `hybrid`:

| Candidato | Conjunto manual (132) | Conjunto do git (134) | `embed_query` p50 / p95 | Reembed | Vetores |
|---|---|---|---|---:|---:|
| MiniLM atual (fastembed, 384d) | 0,62 [0,54–0,70] / 0,52 | 0,60 [0,51–0,68] / 0,47 | 3,6 / 4,4 ms | 91,7 chunks/s (~102 s) | 14,3 MB |
| `nomic-embed-text` (Ollama, 768d, com prefixos) | **0,71** [0,63–0,78] / **0,56** | **0,65** [0,57–0,72] / 0,49 | 14,9 / 38,5 ms | 83,3 chunks/s (~112 s) | 28,7 MB |
| nomic v1.5, jina-code, qwen3-embedding, 3 rerankers | `ausente` | `ausente` | | | |

O `nomic-embed-text` melhora o `hybrid` nos dois conjuntos (+0,09 e +0,05 de recall@5, +0,04 e +0,01 de MRR) e é o primeiro modelo com o
qual o `hybrid` (0,71) passa o `keyword` (0,70) no conjunto manual. Os intervalos ainda se sobrepõem (±0,08), então é um indício
consistente nos dois conjuntos, não uma prova; o custo é ~4x a latência de consulta e o dobro do espaço dos vetores. **Latência do
reranker em CPU: sem número**, porque nenhum reranker está em disco e baixar é decisão de uma pessoa (`ragx bench models --only
rerank-minilm-l6` mede assim que o modelo estiver no cache).

### 1. RRF premia consenso

É a fraqueza conhecida do algoritmo. Rastreando a consulta
`"quantização int8 dos vetores"`:

```text
keyword   #2  docs/16-orcamento-de-tamanho.md        <- alvo rotulado
semantic  #2  src/ragx/embeddings/base.py            <- alvo rotulado
hybrid    #1  task/.../RAGX-0071-quantizacao...md    <- consenso dos dois
          #2  task/.../RAGX-0071-quantizacao...md
          #4  docs/adr/ADR-0010-...md
```

Cada motor acha um alvo diferente; nenhum dos dois entra no topo do híbrido.
O que sobe é aquilo em que os dois concordam — que aqui é o arquivo de task.

### 2. O conjunto de avaliação rotula de menos

No exemplo acima, `RAGX-0071` e `ADR-0010` **são documentos genuinamente
relevantes** sobre quantização, e não estão em `relevant_paths`. A métrica
penaliza o híbrido por achar documentos corretos porém não rotulados.
Corrigir isso exige rerrotular o conjunto — de preferência por alguém que não
esteja otimizando contra ele.

### 3. O corpus é anormalmente autossimilar

Todo documento deste repositório fala de indexação, chunks e embeddings. É um
cenário adversarial para busca semântica: o sinal se difunde e o termo exato do
BM25 fica mais nítido.

### O que foi testado e NÃO resolveu

| Hipótese | Resultado |
|----------|-----------|
| Varrer pesos do RRF (6 combinações) | platô em 0.69 — teto independente do peso |
| Fusão adaptativa por forma da consulta | 0.65 — sem ganho; código removido |
| Reduzir `max_per_document` para 1 ou 2 | 0.65–0.69 — sem ganho |

Nenhuma tentativa foi mantida: maquinário sem evidência de ganho é pior que
ausência de maquinário. Os 4 pontos de diferença entre 0.65 e 0.69 equivalem a
**uma consulta** em 26 — ruído, não sinal.

### Onde isso deixa o modo padrão

`hybrid` continua o padrão porque tem o **melhor MRR** (0.49 contra 0.48 do
keyword) e porque a vantagem do keyword aqui vem de um conjunto de avaliação
enviesado para termo exato. Quem busca por nome de símbolo deve usar
`--mode keyword` explicitamente — a documentação já recomenda isso.

Meta adicional (Fase 9): a perda do modo `int8 apenas` — o que um dev tem logo após
`git clone` — não pode passar de **5 pontos de Recall@5**. Se passar, a decisão de
`versioned_dim` precisa ser revista.

## Critério de aceite da Fase 2

1. `ragx search "como funciona autenticação"` encontra `auth.md` mesmo que o
   documento nunca use a palavra "funciona" — prova de que o semântico está ativo.
2. `ragx search "AuthService" --mode keyword` traz o símbolo exato em primeiro lugar.
3. Híbrido supera cada motor isolado no `ragx eval`.
4. Nenhum resultado, em nenhum modo, vem de arquivo bloqueado pelo gate
   (teste de segurança, agora sem `xfail` para embeddings).
5. Busca em índice de 10k chunks responde em < 300 ms na máquina de referência.
