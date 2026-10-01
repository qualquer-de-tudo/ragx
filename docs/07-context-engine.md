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
overhead de formatação (cabeçalhos, rodapé)          o texto REAL, medido (ver abaixo)
reserva mínima por fonte distinta                    1 trecho de cada um dos top-3 documentos
```

O cabeçalho de cada fragmento (`## [i] caminho:linhas › nome`) custa ~33 tokens, e não os
12 que o orçamento antigo assumia: `allocate` agora conta o cabeçalho real de cada
candidato (`context/format.py`) e reserva o rodapé uma vez. Antes, um pedido de 3.000
tokens chegava ao agente com ~8.000 (o conteúdo ia duas vezes na resposta MCP e
`estimated_tokens` ignorava cabeçalhos).
A reserva por fonte existe para evitar o modo de falha clássico: 3.000 tokens todos
vindos de um único arquivo, sem a documentação que explica o porquê.

Contagem de tokens: `TokenCounter` abstrato, implementação padrão `tiktoken`
(`cl100k_base`). Contagem é **estimativa** — o `ContextPack` sempre reporta
`estimated_tokens` e garante `estimated_tokens <= budget`, com margem de 3%.

**`estimated_tokens` conta o que sai:** os tokens do markdown entregue (cabeçalhos,
conteúdo e rodapé, sem o título `# Contexto — <consulta>`, que só a CLI imprime). É um
ponto fixo, porque o rodapé traz o próprio número. `stats` separa `content_tokens` de
`overhead_tokens`.

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
    chunk_id: str        # o id do chunk de origem (necessário ao dedupe e ao plugin)

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

## Dedupe de sessão (RAGX-0159)

O `dedup` da seção [4] limpa a repetição DENTRO de um pack. Entre packs, numa mesma sessão, o agente
refaz perguntas parecidas e o `build_context` reenviava os mesmos chunks inteiros. Com
`[context] session_dedupe = true` o servidor MCP guarda um **livro-razão em memória**
(`context/session.py`, um por processo) com só o `chunk_id`, o caminho, as linhas, os tokens e a hora da
entrega, **nunca o conteúdo**, e `apply_session` (depois do cache, que guarda o pack completo) troca por
referência o fragmento que a sessão já recebeu:

```text
Já entregues nesta sessão (reabra com get_chunk): `src/a.py:3-9 [a1b2c3d4e5f6]`, ...
```

O custo da linha entra em `estimated_tokens`; se as referências custarem tanto quanto o conteúdo que
substituem (chunk minúsculo), o pack segue completo. `get_chunk` marca o chunk como entregue e **sempre**
devolve o conteúdo inteiro, nunca uma referência. A resposta traz `dedupe_refs` e `dedupe_saved_tokens`
(e `references` no formato `json`), e a telemetria registra os mesmos dois campos. O chunk editado entre
as chamadas tem id novo (o id deriva do conteúdo) e volta como conteúdo; passado o TTL
(`session_ttl_minutes`, 45) o chunk também volta. `ragx context` (CLI) não usa o dedupe: não é sessão.

**Desligado por padrão, e por quê.** No cenário medido (3 consultas sobrepostas sobre este repositório,
`scripts/medir_dedupe_sessao.py`) o ganho foi de **4,2%** (8.110 → 7.767 tokens; 3 chunks repetidos em
3 chamadas), e o risco é real: o servidor não sabe quando o cliente compactou o contexto ou deu `/clear`,
nem distingue o agente principal de um subagente (que compartilha o servidor, mas não o contexto), e
um agente nessa situação recebe uma referência a algo que não vê (recuperável com `get_chunk`, a custo
de uma chamada). O A/B da RAGX-0162 decide se vira padrão. Fora de escopo, por ora: reaproveitar o
orçamento liberado com chunks novos (a v1 só encurta a resposta).

## Cache

`ContextPack` é caro de montar (~70-80 ms quente, 2 s+ frio). O cache fica em
`.ragx/cache/context/<chave>.json`, e a chave é o `sha256` de **tudo que altera o
resultado**:

- a consulta, o orçamento, `include_graph`, `depth` e os **filtros** (`lang`, `kind`,
  `path_glob`, `min_score`);
- as seções `context`, `search` e `graph` da configuração, o modelo de embedding
  (`provider`, `model`, `dim`, `versioned_dim`, `rescore`), `index.work_paths` e
  `index.test_paths`;
- `CACHE_FORMAT` e o hash de `intents.yaml`;
- a **versão do índice**: a geração dos vetores (`meta('vec_gen')`, RAGX-0134) e a
  última indexação **terminada e sem erro** (`index_runs`). Uma run em andamento não
  conta.

Antes de RAGX-0135 a chave não tinha os filtros nem os pesos: `lang=markdown` e depois
`lang=python`, mesma consulta, devolviam o mesmo pack com `cached=True`.

**Quando não grava:** com uma indexação em curso (trava com dono vivo) ou se a versão do
índice mudou durante o cálculo, porque o pack seria parcial. Ler continua permitido.
**Como grava:** arquivo temporário e `os.replace` (ninguém lê JSON pela metade); o JSON
leva `format` e `key`, e entrada com formato ou chave diferente, truncada ou ilegível é
*miss*, nunca erro. **Despejo:** no máximo 200 arquivos e 32 MB; saem os mais antigos
por `mtime`.

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
ragx trial --grep-files 3           # quantos arquivos o "Grep" simulado lê
```

Para cada consulta do corpus de avaliação, compara números medidos com o mesmo
`TokenCounter`:

- **oráculo** (`baseline_oracle_tokens`, o antigo `baseline_tokens`) — tokens do conteúdo
  INTEIRO de cada arquivo em `relevant_paths`: os arquivos certos, de graça;
- **Grep~** (`baseline_grep_tokens`) — os `K` primeiros documentos de uma busca por
  palavra-chave, lidos inteiros: um "Grep + Read" simulado. `K` é `--grep-files`;
- **ragx** (`ragx_tokens`) — os tokens do **markdown entregue** (`estimated_tokens`, RAGX-0154).

A manchete é a economia **conservadora** (`saved_ratio_conservative`): contra o **menor** dos
dois baselines. `baseline_tokens` e `saved_ratio` continuam no JSON, por compatibilidade, e
valem o oráculo.

**Sensibilidade a `K`** (medido neste repositório, 26 consultas, `--budget 3000`; oráculo
94.996 tokens, RAGX 69.175, cobertura de fonte 58%): com `K=1` o Grep fica **abaixo** do
oráculo (91.273) e passa a valer: economia conservadora **24,2%**, 15 consultas negativas; com
`K=2` (157.395), `K=3` (267.100) ou `K=5` (502.749) ele passa do oráculo e a conservadora volta a
**27,2%**, com 8 a 9 consultas negativas. `K=1` é o padrão: é o piso, e dá a manchete menos
favorável ao RAGX. A economia **não muda de sinal** entre os valores de `K`, mas o quanto
depende dele: é exatamente por isso que o número real só pode vir de uma sessão de verdade (o A/B
da RAGX-0162).

**O que isto NÃO é**: uma sessão de agente real reproduzida com e sem RAGX. São **dois proxies**,
e nenhum é "a economia real". Medem o que o RAGX controla (o tamanho do que ele entrega), não o que o
agente teria lido sozinho. Por isso `ragx trial` sempre reporta também a **cobertura de fonte**
(`sources_hit / sources_total`): economia de token sem a fonte relevante dentro do pacote não é
economia, é perda de informação disfarçada de otimização.

**O gráfico do painel** ("Arquivos inteiros (limite superior)") usa o log do servidor
(`baseline_tokens` de cada `build_context`): a soma de `chunks.token_count` dos documentos de onde
o contexto saiu, **na mesma unidade do entregue**. Antes era `size_bytes // 4`, que em markdown erra
por ~30% (`docs/09-mcp.md`: 4.265 contra 5.993 tokens reais). Registros antigos do log seguem em
bytes/4 e não são reescritos; a ordem de grandeza é a mesma.

Um `saved_ratio` negativo é esperado, não é bug: acontece quando o arquivo
relevante já é menor que o orçamento de tokens, então "ler o arquivo inteiro"
(baseline) já é mais barato que o pacote orçado do `build_context`. No corpus
deste próprio repositório, 8 das 26 consultas mostram economia negativa contra o
oráculo por exatamente esse motivo (eram ~10 antes de o `estimated_tokens` passar a contar
o markdown entregue).
