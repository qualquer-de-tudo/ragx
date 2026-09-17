# 07 — Context Engine (Fase 4)

É aqui que o RAGX deixa de ser "um buscador" e vira infraestrutura de agente.
A busca devolve *resultados*; o Context Engine devolve **um contexto pronto para ser
colado num prompt, dentro de um orçamento**.

## Fluxo

```text
Query  +  budget (tokens)
  │
  ▼
[1] Hybrid Search          top-N candidatos (N = 5× o que cabe)
  ▼
[2] Graph Expansion        vizinhança das entidades âncora
  ▼
[3] Ranking                score final + sinais de tarefa
  ▼
[4] Deduplication          near-duplicate + MMR (diversidade)
  ▼
[5] Compression            extrativa, preservando estrutura
  ▼
[6] Budget Allocation      knapsack por valor/token
  ▼
Context Pack
```

Comando:

```bash
ragx context "implementar autenticação SSO" --tokens 3000
ragx context "..." --tokens 3000 --format markdown|json|xml
ragx context "..." --include-graph --depth 2
ragx context "..." --explain            # mostra por que cada trecho entrou
```

## [4] Deduplicação

Dois problemas distintos:

**Duplicata literal** — o mesmo trecho aparece em dois arquivos (código copiado,
doc espelhada). Detecção por `content_hash`; se igual, mantém o de maior score e
registra o outro como `duplicate_of`.

**Quase-duplicata** — trechos que dizem a mesma coisa com palavras diferentes.
Detecção por similaridade de cosseno entre embeddings já armazenados: acima de
`context.dedup_threshold` (padrão **0.93**), mantém só o melhor.

**Redundância de conteúdo** — resolvida por MMR (Maximal Marginal Relevance), que
troca um pouco de relevância por cobertura:

```python
def mmr(candidates, query_vec, lambda_=0.7, k=20):
    selected = []
    while candidates and len(selected) < k:
        best = max(
            candidates,
            key=lambda c: lambda_ * sim(c.vec, query_vec)
                          - (1 - lambda_) * max((sim(c.vec, s.vec) for s in selected), default=0.0),
        )
        selected.append(best)
        candidates.remove(best)
    return selected
```

`lambda_ = 0.7` favorece relevância; `0.5` favorece cobertura. Configurável.

## [5] Compressão

Compressão **extrativa** e determinística. Nada de resumo gerado por LLM no MVP:
resumo alucinado dentro do contexto é pior que contexto truncado.

Estratégias, aplicadas em ordem até caber no orçamento:

1. **Poda de ruído** — remove imports irrelevantes, licenças de cabeçalho, linhas
   em branco repetidas, comentários gerados automaticamente.
2. **Colapso de corpo** — em chunk de código de baixa prioridade, mantém assinatura
   + docstring e substitui o corpo por `# ... (N linhas omitidas)`.
3. **Seleção de sentenças** — em chunk de documentação, mantém as sentenças de maior
   similaridade com a query (mínimo: a primeira sentença da seção, que carrega o tema).
4. **Truncamento com marca** — último recurso, sempre com `…(truncado)` explícito.

Invariante: **a fonte nunca é perdida**. Todo trecho, comprimido ou não, mantém
`document_path` e intervalo de linhas — o agente precisa poder abrir o arquivo real.

## [6] Orçamento de tokens

O orçamento não é dividido igualmente. É um *knapsack* aproximado por densidade
de valor:

```python
densidade = score_final / max(token_count, 1)
```

Reservas fixas antes da alocação:

```text
overhead de formatação (cabeçalhos, separadores)     ~5%
reserva mínima por fonte distinta                    1 trecho de cada um dos top-3 documentos
```

A reserva por fonte existe para evitar o modo de falha clássico: 3.000 tokens todos
vindos de um único arquivo, sem a documentação que explica o porquê.

Contagem de tokens: `TokenCounter` abstrato, implementação padrão `tiktoken`
(`cl100k_base`). Contagem é **estimativa** — o `ContextPack` sempre reporta
`estimated_tokens` e garante `estimated_tokens <= budget`, com margem de 3%.

## Contrato de saída

```python
@dataclass(frozen=True)
class ContextFragment:
    document_path: str
    symbol: str | None
    heading_path: str | None
    start_line: int
    end_line: int
    content: str
    score: float
    compressed: bool
    reason: str          # "hybrid" | "graph:calls" | "graph:documented_by"

@dataclass(frozen=True)
class ContextPack:
    query: str
    fragments: tuple[ContextFragment, ...]
    estimated_tokens: int
    budget: int
    sources: tuple[str, ...]
    dropped: tuple[str, ...]      # o que foi descartado e por quê
    stats: dict[str, Any]
```

Formato Markdown (padrão):

```text
# Contexto — implementar autenticação SSO

## [1] docs/auth.md § Autenticação > Fluxo SSO
<conteúdo>

## [2] src/Auth/AuthService.php:24-71 › AuthService.login
<conteúdo>

## [3] docs/architecture.md § Camada de Serviços  (comprimido)
<conteúdo>

---
3 fontes · ~2.847 / 3.000 tokens · 14 candidatos descartados
```

## Sinais de tarefa

A query não é só uma pergunta — costuma ser uma *tarefa*. O engine detecta intenção
e ajusta a mistura:

| Intenção detectada | Mistura preferida |
|--------------------|-------------------|
| "implementar X", "criar X" | código de exemplo + regras/padrões + doc de arquitetura |
| "onde fica X", "como funciona X" | documentação primeiro, código depois |
| "corrigir bug em X" | o código exato + testes relacionados + chamadores (grafo) |
| "revisar X" | o código + padrões de codificação + regras |

Detecção por padrões léxicos simples (lista em `context/intents.yaml`). É heurística
declarada, não mágica — e o `--explain` mostra qual intenção foi inferida.

## Cache

`ContextPack` é caro de montar. Cache por
`sha256(query + budget + config_fingerprint + db_version)` em `.ragx/cache/context/`.
Invalida automaticamente quando o índice muda (`index_runs.id` mais recente entra
no `db_version`).

## Critério de aceite da Fase 4

1. Recuperação bruta de ~10.000 tokens resulta em pack de **<= 3.000 tokens**,
   mantendo os trechos-chave do conjunto de avaliação.
2. Nenhuma duplicata literal no pack (teste: `content_hash` único entre fragmentos).
3. Todo fragmento tem `document_path` e intervalo de linhas válidos.
4. `estimated_tokens <= budget` em 100% dos casos do conjunto de avaliação.
5. Pelo menos 2 documentos distintos representados quando existem 2 relevantes.
6. `--explain` justifica cada fragmento incluído e cada descartado.

## Trial — economia de tokens (honesta)

```bash
ragx trial                          # usa tests/eval/queries.yaml
ragx trial --budget 1500 --json
```

Para cada consulta do corpus de avaliação, compara dois números medidos com o
mesmo `TokenCounter`:

- **baseline** — tokens do conteúdo INTEIRO de cada arquivo em `relevant_paths`
  (o que um agente leria sem o RAGX);
- **ragx** — `estimated_tokens` do `ContextPack` que o `build_context` entrega
  para o mesmo orçamento.

**O que isto NÃO é**: uma sessão de agente real reproduzida com e sem RAGX.
É um proxy — mede o que o RAGX controla (o tamanho do que ele entrega), não o
que o agente realmente teria lido sozinho. Por isso `ragx trial` sempre reporta
também a **cobertura de fonte** (`sources_hit / sources_total`): economia de
token sem a fonte relevante dentro do pacote não é economia, é perda de
informação disfarçada de otimização.
