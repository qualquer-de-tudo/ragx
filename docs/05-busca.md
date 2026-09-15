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
e mais precisa. A matriz é carregada uma vez por processo e cacheada por `mtime` do banco.

Assimetria de query/documento importa: `nomic-embed-text` exige os prefixos
`search_query:` e `search_document:`. Isso é responsabilidade do provider, não do
caller — ver [ADR-0004](adr/ADR-0004-embeddings.md).

## Busca keyword

```sql
SELECT c.id, bm25(chunks_fts, 1.0, 4.0, 2.0) AS score
FROM chunks_fts
JOIN chunks c ON c.rowid = chunks_fts.rowid
WHERE chunks_fts MATCH :q
ORDER BY score
LIMIT :k;
```

Pesos do BM25 por coluna: `content=1.0`, `symbol=4.0`, `heading_path=2.0` — casar no
nome do símbolo vale muito mais que casar no corpo.

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
