# 23 — Auditoria do RAG e proposta de evolução

Auditoria do mecanismo de recuperação do RAGX, feita contra o código e contra
medição — não contra a documentação. Todo número aqui foi reproduzido neste
repositório, no estado do commit em que o documento foi escrito, e os scripts
que os produziram estão descritos para que qualquer um refaça.

> **Como ler.** A seção 1 é o resumo. A 2 é o mapa do que existe. A 3 são os
> achados, ordenados por quanto valem — não pela ordem em que apareceram. A 4
> é a proposta, em ondas, com critério de aceite. A 5 lista o que eu **não**
> consegui concluir, e por quê.

---

## 1. Resumo

O RAGX tem uma arquitetura de recuperação mais completa do que a maioria dos
RAGs que se vê em produção: gate de segurança antes do parser, chunking por
AST, busca híbrida com RRF, MMR, orçamento de tokens, grafo de entidades e
dicionário de projeto. As peças estão lá.

O problema não é falta de peça. É que **três das que mais importam nunca foram
medidas**, e uma delas está custando 50× mais do que deveria.

Os cinco achados que mudam alguma coisa:

| # | Achado | Evidência | Custo de corrigir |
|---|---|---|---|
| 1 | O embedder ONNX é reconstruído a cada busca | `build_embedder()` = 2537–3638 ms; `embed_query()` reusando = 6–27 ms | Baixo |
| 2 | O conjunto de avaliação (n=26) não distingue os modos | IC95% de `keyword` [0,58–0,89] e `hybrid` [0,43–0,78] se sobrepõem | Médio |
| 3 | A métrica `nDCG@10` está errada — pode passar de 1,0 | Medido: **2,131** com 3 chunks do mesmo arquivo | Baixo |
| 4 | 22% do corpus é `task/`, e ele ganha do código na busca | `task/` 543 chunks > `docs/` 321; hit #1 de "como o gate bloqueia" é um arquivo de task | Baixo |
| 5 | O braço semântico é fraco **por escolha de modelo** | Trocando o modelo: híbrido 0,62 → **0,77** de recall, MRR 0,51 → **0,58** | Médio |

O achado 1 é o mais barato e o de maior efeito: hoje **99% da latência da busca
semântica é carregar o modelo**, não buscar. O achado 3 invalida uma das três
métricas que o projeto usa para decidir. O achado 2 significa que a afirmação
publicada no README — "a busca híbrida não supera o keyword" — **não é
sustentada pelo tamanho da amostra**, embora possa vir a ser.

A recomendação central não é trocar a arquitetura. É **consertar o instrumento
de medida e o caminho quente antes de mexer no algoritmo** — porque, do jeito
que está, nenhuma mudança de retrieval é falsificável.

Uma exceção mereceu ser medida agora, e o resultado justifica: **trocar o
modelo de embedding resolve, sozinho, a ressalva publicada no README.** Ver
3.5.1.

---

## 2. O mapa real

O fluxo canônico de um RAG, e o que o RAGX de fato faz em cada etapa:

```text
Repositório
   ↓        walk.py — streaming, nunca carrega o repo em memória
Security Gate ......... ✅ ANTES do parser (ADR-0008). Diferencial real.
   ↓
Parsing ............... ⚠️  AST só para Python. PHP/JS/TS caem em parágrafo.
   ↓
Normalização .......... ⚠️  não existe como etapa própria
   ↓
Chunking .............. ✅ hierárquico com parent_id, respeita bloco de código
   ↓
Metadados ............. ⚠️  bons para o índice, pobres para o agente
   ↓
Embedding ............. ⚠️  modelo de PARÁFRASE para tarefa de BUSCA
   ↓
Storage ............... ✅ SQLite: FTS5 + vetores, um arquivo, zero daemon
   ↓
Retrieval ............. ✅ keyword + semântica + RRF
   ↓
Filtering ............. ✅ filtro aplicado ANTES do top-K (detalhe que quase todo RAG erra)
   ↓
Ranking ............... ⚠️  heurística multiplicativa sobre score de RRF; sem cross-encoder
   ↓
Context Assembly ...... ✅ dedup literal + near + MMR + orçamento + compressão
   ↓
Agente (MCP) .......... ⚠️  33 ferramentas; `score` com 3 escalas incompatíveis
   ↓
LLM
```

### Qual é o papel do RAG aqui

Respondendo à pergunta da seção 3 do pedido: o RAGX tenta ser **quatro coisas
ao mesmo tempo**, e isso aparece no índice.

1. **Camada de conhecimento do repositório** — `src/`, `docs/`. É o propósito.
2. **Repository intelligence** — grafo de entidades, dicionário.
3. **Orquestração de trabalho** — `task/`, tarefas, DAG, worker.
4. **Memória compartilhada entre projetos** — `@base/`, federação.

As quatro dividem o **mesmo índice e o mesmo ranking**. É por isso que o achado
4 acontece: um documento de planejamento (`task/RAGX-0005-securityscanner...`)
disputa e ganha de `src/ragx/security/gate.py` numa pergunta sobre como o gate
funciona. Não é bug de ranking — é consequência de misturar registro de
trabalho com conhecimento no mesmo espaço vetorial.

---

## 3. Achados

### 3.1 O embedder é reconstruído a cada consulta 🔴

`build_embedder(cfg)` é chamado dentro de `search/service.py:_semantic()` — ou
seja, **em toda busca semântica ou híbrida** — e de novo em
`context/engine.py:_vectors_for()`. Não há cache em lugar nenhum.

Medido:

```text
build_embedder()                   2537 – 3638 ms
embed_query() com embedder novo      10 –   27 ms
embed_query() com embedder reusado    6 –   11 ms
```

Consequência, medida ponta a ponta:

```text
search keyword                18 ms
search semantic             2963 – 3992 ms
search hybrid               2677 – 2906 ms
build_context (sem cache)   5327 – 6312 ms   ← constrói o modelo DUAS vezes
build_context (com cache)     15 –   41 ms
```

**~99% da latência da busca semântica é carregar o modelo ONNX.** O servidor
MCP é um processo persistente: um cache por processo levaria a busca híbrida de
~2,7 s para ~60 ms sem alterar um único resultado.

Vale notar o contraste: `search keyword` custa 18 ms. A diferença de 150× entre
os dois braços não é propriedade de busca vetorial — é este defeito.

> A documentação de `docs/05-busca.md` afirma que "a matriz é carregada uma vez
> por processo e cacheada por `mtime` do banco". **Esse cache não existe** em
> `storage/vectors.py`. Ele custaria pouco (o `load_index` leva ~50 ms), mas a
> documentação promete algo que o código não faz — e foi isso que me fez
> procurar a latência no lugar errado por um tempo.

### 3.2 O conjunto de avaliação não consegue distinguir os modos 🔴

`tests/eval/queries.yaml` tem **26 consultas**. Com n=26, o intervalo de
confiança de Wilson para uma proporção é largo:

| Modo | recall@5 | IC 95% | largura |
|---|---:|---|---:|
| keyword | 0,77 | [0,58 – 0,89] | 0,31 |
| semantic | 0,54 | [0,35 – 0,71] | 0,36 |
| hybrid | 0,62 | [0,43 – 0,78] | 0,35 |

Os intervalos de `keyword` e `hybrid` **se sobrepõem em quase toda a extensão**.
A diferença de 0,15 entre eles são **4 consultas**. Uma única consulta vale
0,038 de recall.

O README publica: *"a busca híbrida não supera o keyword neste corpus"* e
*"o critério documentado não foi atingido"*. Isso é apresentado como resultado.
Com n=26 é uma **observação**, não uma conclusão — e serviu de base para
considerar a Fase 2 parcialmente falha.

Isto é o achado mais importante depois do 3.1, porque **torna não-falsificável
qualquer mudança de retrieval**: uma melhoria real de 5 pontos é indistinguível
de ruído, e uma piora real também.

### 3.3 A métrica nDCG@10 está incorreta 🔴

`search/evaluation.py:_ndcg()` monta os ganhos a partir da lista de
**caminhos de documento** dos chunks retornados, sem deduplicar:

```python
gains = [1.0 if p in relevant else 0.0 for p in paths[:k]]
```

Como vários chunks do mesmo arquivo aparecem no resultado, o mesmo caminho
conta várias vezes. O denominador ideal, porém, usa `min(len(relevant), k)` —
o número de **arquivos** relevantes. Ganho por chunk, ideal por arquivo.

Medido:

```python
_ndcg(['a.py','a.py','a.py','x','y'], ('a.py',))  →  2.131
_ndcg(['a.py','x','y'],               ('a.py',))  →  1.000
```

**nDCG é uma métrica normalizada: 2,131 é impossível.** E a direção do erro
importa: a métrica **premia devolver muitos chunks do mesmo arquivo**, que é
exatamente o oposto do que um contexto bom faz.

O mesmo defeito contamina `recall@5`, de outro jeito. Varrendo
`max_per_document`:

```text
max_per_doc=1   recall@5 0,69
max_per_doc=2   recall@5 0,62
max_per_doc=3   recall@5 0,62   (padrão)
max_per_doc=10  recall@5 0,62
```

Forçar **um chunk por arquivo** "melhora" o recall em 7 pontos. Não porque a
recuperação ficou melhor: porque o top-5 passa a conter 5 caminhos distintos em
vez de 2 ou 3, e a métrica é medida em caminhos. É artefato, não ganho — e se
alguém otimizar contra ela, vai otimizar para diversidade inútil.

### 3.4 O corpus compete consigo mesmo 🟠

O índice do próprio RAGX, hoje: **2473 chunks, 419 mil tokens, 294 documentos**.

| Área | chunks | % | tokens | % |
|---|---:|---:|---:|---:|
| `src/` | 836 | 33,8% | 164.582 | 39,3% |
| `task/` | 543 | **22,0%** | 62.978 | 15,0% |
| `tests/` | 384 | 15,5% | 47.349 | 11,3% |
| `@base/` | 323 | 13,1% | 57.768 | 13,8% |
| `docs/` | 321 | 13,0% | 73.390 | 17,5% |
| resto | 66 | 2,7% | 13.110 | 3,1% |

`task/` — documentos de planejamento — é **22% do corpus, mais que toda a
documentação**. E não é inofensivo: para a consulta *"como o security gate
decide bloquear um arquivo"*, o `build_context` devolve como fragmento **[1]**:

```text
task/fase-00-fundacao-seguranca/RAGX-0005-securityscanner-fase-1-deny-list-
por-nome-de-arquivo.md:13-16  ›  Objetivo

  Bloquear arquivos notoriamente sensíveis antes de qualquer leitura de conteúdo.
```

A resposta certa é `SecurityGate.admit()`. O que veio no topo foi o *enunciado
da tarefa que pediu para construir aquilo* — texto que repete o vocabulário da
pergunta sem conter a resposta.

Documento de planejamento é quase-duplicata semântica da documentação: mesmo
assunto, mesmas palavras, menos informação. Junto com `tests/`, são **37,5% do
corpus disputando as vagas do top-K** com o código e a documentação.

Nenhum reranker conserta isso de graça. É composição de corpus, e o conserto é
de configuração.

### 3.5 O braço semântico só subtrai, neste corpus 🟠

Varredura dos pesos do RRF (26 consultas, tudo o mais igual):

```text
semantic=1,0  keyword=0,8   recall@5 0,62   ← padrão atual
semantic=1,0  keyword=1,0   recall@5 0,69
semantic=0,8  keyword=1,0   recall@5 0,69
semantic=0,5  keyword=1,0   recall@5 0,69
semantic=0,3  keyword=1,0   recall@5 0,69
semantic=0,0  keyword=1,0   recall@5 0,77   ← = keyword puro
```

Duas leituras:

1. **O padrão (1,0 / 0,8) é o pior ponto da varredura.** Ele dá mais peso ao
   braço que mede pior. Trocar para 1,0/1,0 já daria +7 pontos, de graça.
2. **Os pesos são um controle fraco.** De 0,3 a 1,0 o resultado não muda
   (0,69). RRF pontua por POSIÇÃO com K=60; o peso só desempata. Para de fato
   reduzir a influência do semântico é preciso ir a zero. Quem for calibrar
   deve mexer em `rrf_k`, não nos pesos:

```text
rrf_k=10   recall@5 0,69        candidate_factor=1   0,58
rrf_k=20   recall@5 0,65        candidate_factor=3   0,62  (padrão)
rrf_k=60   recall@5 0,62 (pad.) candidate_factor=6   0,62
rrf_k=120  recall@5 0,62        candidate_factor=12  0,62
```

`candidate_factor` satura em 3: **o recall não está limitado pelo tamanho do
conjunto de candidatos**. Aumentar top-K não resolve nada aqui — o problema é
ordenação, não cobertura.

#### Por que o semântico é fraco: é o modelo, não a arquitetura

Testei a hipótese óbvia primeiro — a de que o estágio grosseiro (int8 truncado)
estragava o conjunto de candidatos — e **ela está errada**:

```text
recall@5 semântico, mesmas 26 consultas
  atual (grosseiro → rescoring)   0,54
  exato (sem prefiltro nenhum)    0,54   ← idêntico
  só grosseiro (sem rescoring)    0,62   ← melhor!

cobertura: o documento certo está entre os 100 candidatos
do estágio grosseiro em 25/26 consultas (96%)
```

O prefiltro cobre 96% dos casos; ele não é o gargalo. (Que o rescoring exato
*piore* o recall é curioso, mas são 2 consultas de 26 — dentro do ruído do
achado 3.2, e não uma conclusão.)

A causa provável é anterior: **o modelo configurado é
`paraphrase-multilingual-MiniLM-L12-v2`**. É um modelo de *paráfrase* —
treinado para dizer se duas frases dizem a mesma coisa. Busca é uma tarefa
**assimétrica**: pergunta curta em português contra trecho longo de código.
São objetivos de treino diferentes, e o modelo não tem prefixo de
consulta/documento para marcar essa assimetria.

Há um segundo efeito colateral: o índice guarda um vetor grosseiro que são os
**192 primeiros componentes** do vetor de 384. Truncar assim só preserva
semântica em modelos treinados com Matryoshka (MRL). O MiniLM não é um deles —
suas dimensões não estão ordenadas por importância. A ADR-0004 foi escrita para
`nomic-embed-text`, que **é** assimétrico e **é** Matryoshka; a configuração
atual herdou a arquitetura sem o modelo que a justificava.

Empiricamente o prefiltro não está machucando (96% de cobertura), então isto é
dívida conceitual, não incêndio. Mas é o motivo para o modelo ser o primeiro
lugar a olhar.

#### 3.5.1 Medido: trocar o modelo resolve a ressalva do README 🟢

Reembuti **os mesmos 2.473 chunks** numa cópia isolada do índice, trocando
apenas o modelo — mesmo corpus, mesmo chunking, mesmas 26 consultas, mesmo
código de busca:

| | recall@5 | MRR | nDCG@10 |
|---|---:|---:|---:|
| **MiniLM (atual)** | | | |
| keyword | 0,77 | 0,47 | 0,76 |
| semantic | 0,54 | 0,44 | 0,66 |
| hybrid | 0,62 | 0,51 | 0,76 |
| **nomic-embed-text-v1.5** | | | |
| keyword | 0,77 | 0,47 | 0,76 |
| semantic | **0,62** | **0,47** | 0,81 |
| hybrid | **0,77** | **0,58** | 0,87 |

O `keyword` é o **controle** e ficou idêntico nos três indicadores — prova de
que a única variável que mudou foi o modelo.

O que muda:

- **O híbrido empata com o keyword em recall@5** (0,77) e **passa à frente em
  MRR** (0,58 contra 0,47). O critério documentado do projeto —
  `híbrida > semântica > keyword` — passa a ser atingido **em MRR**, que é
  o único dos três indicadores em que ele pode ser afirmado hoje (ver
  abaixo).
- **MRR é o indicador limpo aqui.** Ele usa a posição do PRIMEIRO acerto, então
  não é inflado pelo defeito de caminhos duplicados do achado 3.3 — ao
  contrário do nDCG, cujo salto (0,76 → 0,87) está medido com um instrumento
  quebrado e **não deve ser citado** até 1.2 estar feito.
- O estágio grosseiro passa a ser **legítimo**: o nomic é treinado com
  Matryoshka, então truncar 768 → 256 preserva semântica. A arquitetura da
  ADR-0010 volta a fazer sentido como escrita.

Duas ressalvas que impedem chamar isto de conclusão fechada:

1. **n continua 26.** O IC95% do recall híbrido é [0,58 – 0,89] — o mesmo do
   keyword. A melhora de recall é consistente com o esperado, mas não é
   estatisticamente separável. **O ganho de MRR é o mais sólido**, por ser
   média contínua e não proporção binária.
2. **A troca tem custo** (ver a caixa em 4.3.1): `batch=32` estoura memória, o
   índice dobra de tamanho (768 contra 384 dimensões) e a indexação fica mais
   lenta.

Mesmo assim, é o achado com melhor relação entre esforço e efeito depois do
3.1 — e o único que ataca diretamente a ressalva que o projeto publica sobre
si mesmo.

### 3.6 `score` tem três escalas incompatíveis, e vaza para o agente 🟠

A mesma consulta, os mesmos três modos:

```text
keyword    scores = [17.836, 14.569, 14.521]      ← BM25 invertido, ilimitado
semantic   scores = [ 0.883,  0.714,  0.651]      ← cosseno, [-1, 1]
hybrid     scores = [ 0.029,  0.029,  0.022]      ← RRF, ~[0, 0.03]
```

Isso sai no campo `score` de toda resposta MCP (`_hit()` em `mcp/server.py`),
com o mesmo nome nos três casos. Consequências concretas:

- **O playbook instrui o agente a desconfiar de "um resultado só semântico com
  score baixo".** O agente não tem como calibrar "baixo": a escala muda por
  baixo dele, sem aviso.
- **`--min-score` / `min_score` é inutilizável em híbrido.** `min_score=0.5`
  descarta quase nada em keyword, corta pela metade em semântico, e **zera o
  resultado** em híbrido, onde o teto é ~0,03.
- O `rerank()` multiplica esse score por fatores (×1,5 para match exato de
  símbolo, ×0,8 para chunk curto). Sobre RRF, onde a diferença entre a 1ª e a
  2ª posição é ~2%, um ×1,5 salta dezenas de posições. Sobre BM25, quase não
  mexe. **O mesmo código tem força completamente diferente conforme o modo.**

### 3.7 O chunking prometido só existe para Python 🟠

`indexing/parsers/__init__.py` mapeia `.php`, `.js`, `.jsx`, `.ts`, `.tsx` como
`DocKind.CODE`, mas `_BY_LANG` só tem parser para `markdown`, `python`, `json`,
`yaml`, `toml`, `xml`, `sql`. Todo o resto cai em `TextParser` — que divide por
**linha em branco**.

Para código, isso é quase o pior fatiamento possível: uma função sem linhas em
branco vira um bloco só; uma com linhas em branco é partida no meio do corpo.
O `parent_id`, o `symbol` e o `heading_path` — de que o BM25 depende com peso
4,0 e 2,0 — ficam vazios.

`pyproject.toml` declara `tree-sitter-language-pack` no extra `[parse]`. Ele
**nunca é importado** em lugar nenhum do `src/`. A dependência está paga e não
usada.

Neste repositório o efeito é invisível (129 arquivos Python, 164 Markdown). Em
um projeto TypeScript ou PHP — os exemplos que o próprio README usa — a
qualidade de chunking cai para "dividir por parágrafo".

### 3.8 O dicionário custa 11 mil tokens e não tem um resumo 🟠

`get_dictionary` é a **primeira chamada que o playbook manda o agente fazer**
("5 a 8 mil tokens", diz o texto). Medido: **10.935 tokens**.

| Seção | tokens | % | itens |
|---|---:|---:|---:|
| `services` | 5.009 | **45,8%** | 52 |
| `data_stores` | 1.602 | 14,7% | 34 |
| `concepts` | 1.021 | 9,3% | 20 |
| `modules` | 963 | 8,8% | 32 |
| `docs` | 952 | 8,7% | 26 |
| resto | 1.388 | 12,7% | — |

E o campo que justificaria o custo está vazio:

```text
services      0/52 com summary preenchido
modules       0/32 com summary preenchido
data_stores   0/34 com summary preenchido
docs          0/26 com summary preenchido
```

**Zero de 144.** Os resumos só são gerados com `dictionary generate --semantic`,
que exige um LLM configurado. Sem isso, `services` — quase metade do orçamento —
é uma lista de nomes de classe com caminho e contagem de referências:

```json
{ "name": "UsageError", "path": "src/ragx/core/errors.py",
  "referenced_by": 30, "summary": null, "depends_on": [] }
```

`UsageError` é uma exceção, não um serviço. `concepts` é pior: são
**agrupamentos por prefixo de string**, não conceitos —

```json
"counter": ["HeuristicCounter", "TiktokenCounter", "TokenCounter", "_Counter"]
```

`_Counter` é um contador privado dentro do chunker. Ele não é um conceito do
projeto; ele casa a substring.

Ou seja: a camada que deveria ser o **Nível 0/1 do conhecimento hierárquico**
(§15 do pedido) existe estruturalmente e está **despovoada**. O agente paga 11k
tokens por um despejo de símbolos.

### 3.9 O que o agente recebe não distingue fato de inferência 🟡

`_hit()` devolve `project`, `chunk_id`, `document_path`, `symbol`,
`heading_path`, `kind`, `lines`, `score`, `content`, `matched_by`.

Não há `confidence`, nem marcação de evidência, nem data. `matched_by` é o que
mais perto chega — e é genuinamente útil ("keyword" = o termo literal existe) —
mas o agente não consegue separar:

```text
FACT        o código diz isto, eu li a linha
INFERENCE   dois trechos parecidos, pode ser coincidência
UNCERTAIN   o índice está velho em relação ao disco
```

O grafo já tem `confidence` e `tier` (`extracted`/`inferred`) e os expõe no
`get_entity`. A busca não tem o equivalente.

### 3.10 Entendimento de consulta existe, mas quase não altera a estratégia 🟡

`context/intents.yaml` declara 4 intenções (`implement`, `locate`, `fix`,
`review`) + default, por regex. É honesto e auditável — melhor que a maioria.

Mas a intenção só altera **pesos por `doc_kind`** e **`graph_depth`**. Não
altera:

- qual motor roda (sempre os dois, em híbrido);
- quantos resultados buscar (`limit` fixo);
- se vale expandir pelo grafo (sempre expande, se ligado);
- se vale uma segunda busca.

Ou seja, das classificações que o pedido sugere (§9), o sistema reconhece 4 e
**usa a classificação para 2 parâmetros**. Uma pergunta de relacionamento
("quem chama X") e uma factual ("o que é X") seguem o mesmo caminho de
recuperação.

Relacionado: a expansão por grafo trouxe **209 nós** (`graph_seeds: 209`,
`graph_nodes: 209`) para uma pergunta única — e os 50 candidatos resultantes
viraram 22 fragmentos de ~136 tokens cada. Contexto picado em 22 pedaços de
duas linhas, vindo de ~15 arquivos, é caro de ler e fácil de interpretar mal.

### 3.11 Sem reranking de verdade 🟡

Não há cross-encoder nem modelo de reranking. O `rerank()` é um conjunto de
multiplicadores declarados — o que é uma escolha defensável para um MVP
(auditável, determinístico, sem dependência). O ADR registra o cross-encoder
como evolução pós-MVP.

O que falta não é o modelo: é o **arranjo**. Hoje o pipeline é
`recuperar top-30 → fundir → heurística → cortar em 10`. O arranjo que paga é
`recuperar muitos → rerankear → ficar com poucos`, e ele só funciona se o
"recuperar muitos" for barato — o que o achado 3.1 impede hoje.

### 3.12 O que está certo, e não deve ser mexido ✅

Para que a proposta não vire reescrita:

- **Security Gate antes do parser.** É o diferencial do projeto. Nenhuma
  proposta aqui o toca.
- **Filtro antes do top-K** (`_filter_mask` no NumPy, predicado no SQL). A
  maioria dos RAGs filtra depois e devolve vazio; este acerta.
- **RRF em vez de soma de scores normalizados.** A justificativa em
  `docs/05-busca.md` está correta: calibrar BM25 contra cosseno exigiria tuning
  por corpus.
- **Chunking hierárquico com `parent_id`** e invariante de não partir bloco de
  código.
- **Orçamento de tokens com reserva por fonte** (`min_sources=3`) — impede o
  modo de falha de 3.000 tokens de um arquivo só.
- **Dedup em três níveis** (literal → near → MMR).
- **Determinismo de IDs entre plataformas**, com CI nos três sistemas.
- **O cache do `build_context` funciona**: 6312 ms → 41 ms → 15 ms.

---

## 4. Proposta

Em ondas. Cada onda tem critério de aceite mensurável, e **a onda 1 é
pré-requisito das outras** — sem ela não há como saber se as demais
funcionaram.

### Onda 1 — Consertar o instrumento e o caminho quente

Nada aqui muda o algoritmo de recuperação. Tudo aqui é pré-condição para
mexer nele com honestidade.

**1.1 Cachear o embedder por processo.**
`build_embedder(cfg)` passa a devolver instância memoizada por
`(provider, model, dim)`. O servidor MCP é persistente; o ganho é imediato e
permanente.
*Aceite:* `search --mode hybrid` abaixo de 150 ms na segunda chamada do mesmo
processo (hoje: 2677 ms). Nenhum resultado muda — teste de contrato compara os
IDs devolvidos antes e depois.

**1.2 Corrigir `_ndcg`.**
Deduplicar caminhos antes de calcular ganhos, ou — melhor — medir em chunks e
usar ideal em chunks. Adicionar teste que falha se `nDCG > 1.0` para qualquer
entrada.
*Aceite:* `_ndcg(['a','a','a'], ('a',)) <= 1.0`.

**1.3 Expandir o conjunto de avaliação para ≥ 150 consultas.**
É o item mais caro e o de maior retorno. Com n=150, a largura do IC95% cai de
~0,33 para ~0,15 — o suficiente para distinguir 5 pontos de recall.
Cobrir as classes que hoje não existem no conjunto: relacionamento ("quem chama
X"), depuração (stack trace), arquitetura ("por que a decisão Y"), e consultas
que **não têm resposta** (para medir falso positivo).
*Aceite:* `ragx eval` reporta IC95% junto de cada métrica, e o CI falha se a
largura passar de 0,20.

**1.4 Reportar intervalo de confiança no `ragx eval`.**
Enquanto o número aparecer sozinho, ele vai ser lido como preciso.
*Aceite:* a saída de `ragx eval` mostra `0,77 [0,58–0,89] n=26`.

**1.5 Separar `score` de `relevance`.**
Manter `score` bruto (útil para depurar) e adicionar `relevance` normalizado em
[0,1], comparável entre modos, mais `scale` dizendo qual motor o produziu.
`min_score` passa a operar sobre `relevance`.
*Aceite:* `min_score=0.5` devolve um subconjunto coerente nos três modos.

### Onda 2 — Composição do corpus

Barato, e provavelmente o maior ganho de precisão por linha alterada.

**2.1 Separar conhecimento de registro de trabalho.**
`task/` e `tests/` ganham um `tier` no índice (`knowledge` | `work` | `test`),
e a busca padrão pondera `work` para baixo — sem excluir, porque às vezes a
resposta está mesmo na tarefa.
*Aceite:* na consulta *"como o security gate decide bloquear um arquivo"*, o
fragmento [1] passa a ser `src/ragx/security/gate.py`. Medir recall@5 antes e
depois no conjunto ampliado.

**2.2 Tornar isso configuração, não regra do RAGX.**
`[index] knowledge_paths` / `work_paths` em `ragx.toml`. Todo projeto tem o seu
equivalente de `task/` (ADRs, RFCs, tickets exportados).

### Onda 3 — O braço semântico

Só depois das ondas 1 e 2, porque só aí a medição distingue.

**3.1 Trocar o modelo para um treinado em recuperação assimétrica.**
Candidatos disponíveis no `fastembed` já instalado:
`nomic-ai/nomic-embed-text-v1.5` (768d, assimétrico, Matryoshka — o modelo para
o qual a ADR-0004 foi escrita) e `intfloat/multilingual-e5-large` (1024d,
multilíngue, prefixos `query:`/`passage:`).

> **4.3.1 — A troca não é gratuita, e isto foi medido.** Reembutindo este repositório
> com `nomic-embed-text-v1.5` no `batch` padrão (32), o ONNX Runtime aborta:
>
> ```text
> Failed to allocate memory for requested buffer of size 15318472704
> /encoder/layers.0/attn/Add
> ```
>
> 15,3 GB para um lote. A causa é a janela de contexto do modelo (8192 tokens
> contra 512 do MiniLM): a matriz de atenção cresce com o quadrado do
> comprimento, e `batch=32` multiplica isso por 32. Modelo de janela grande
> exige `batch` pequeno e/ou teto de tokens por chunk — e o `[embedding] batch`
> default do RAGX está calibrado para o modelo atual, não para o candidato.
> Com `batch=4` os 2.473 chunks foram embutidos sem erro.
>
> Some-se a isso o índice dobrar de tamanho: 768 dimensões contra 384.
>
> Ou seja: a onda 3.1 carrega uma mudança de configuração obrigatória junto, e
> um custo de indexação maior. Não é só trocar o nome do modelo no `ragx.toml`.

**Medido (ver 3.5.1):** com `nomic-embed-text-v1.5`, o híbrido vai de 0,62 para
**0,77** de recall@5 e de 0,51 para **0,58** de MRR, com o keyword inalterado
como controle. A recomendação deixa de ser hipótese.

*Aceite:* confirmar o ganho no conjunto ampliado da onda 1.3 — com n=26 o
resultado é promissor, não conclusivo — e publicar junto o custo: tamanho do
índice, tempo de indexação e o `batch` necessário.

**3.2 Reconhecer a assimetria no código.**
O `Embedder` já tem `embed_query` separado de `embed_documents`; o provider
`fastembed` não aplica prefixo nenhum. Com um modelo assimétrico, aplicar.

**3.3 Rever a truncagem Matryoshka.**
Se o modelo novo for MRL, o estágio grosseiro passa a ser legítimo e a ADR-0010
volta a fazer sentido como escrita. Se não for, trocar a truncagem por uma
projeção treinada ou abandonar o estágio grosseiro — hoje ele funciona por
sorte, não por desenho.

**3.4 Reposicionar os pesos do RRF.**
Enquanto 3.1 não acontece, o padrão `1,0/0,8` é o pior ponto medido da
varredura. `1,0/1,0` é melhor em 7 pontos. `rrf_k` é o controle forte, não os
pesos.

### Onda 4 — Recuperação adaptativa e reranking

**4.1 Estratégia por intenção, não só peso por intenção.**
A classificação já existe; passar a decidir com ela:

```text
FACTUAL / identificador     → keyword primeiro; semântico só se vazio;  k=5
CONCEITUAL / "como funciona"→ híbrido + reranking;                      k=8
RELACIONAMENTO / "quem chama"→ grafo primeiro, texto como apoio;        k=6
ARQUITETURA / "por que"     → hierárquico: resumo → seção → trecho
DEPURAÇÃO / stack trace     → keyword exato no símbolo;                 k=10
```

`looks_like_identifier()` e `looks_like_question()` já existem em
`ranking.py` — hoje só ajustam multiplicadores.

**4.2 Cross-encoder opcional.**
Com o embedder cacheado (1.1), recuperar 50 e rerankear 50 passa a caber no
orçamento de latência. Modelo pequeno, local, atrás de flag, desligado por
padrão.
*Aceite:* ganho medido no conjunto de ≥150, com o custo de latência publicado
ao lado. Sem ganho, não entra.

**4.3 Conter a expansão do grafo.**
209 nós para uma pergunta é expansão sem freio. Limitar por orçamento de
contexto, não só por `max_nodes`.

### Onda 5 — A camada hierárquica que já existe, povoada

**5.1 Popular os resumos sem exigir LLM.**
Docstring de classe/módulo, primeiro parágrafo de seção Markdown, assinatura de
função — tudo isso já está no índice e daria um resumo extrativo decente.
Hoje `summary` fica `null` porque só o caminho `--semantic` o preenche.
*Aceite:* ≥80% de `services`/`modules` com `summary`, sem LLM.

**5.2 Cortar o que não orienta.**
`concepts` por prefixo de string e símbolos privados (`_Counter`,
`_EmbedOnlyDoneError`) saem. Alvo: **≤ 4.000 tokens** com mais informação útil
que os 11 mil de hoje.

**5.3 Entregar o dicionário em níveis.**
`get_dictionary(level=0)` — projeto, tecnologias, pontos de entrada (~800
tokens). `level=1` — módulos com resumo. `level=2` — o de hoje. O agente começa
barato e aprofunda. É o §15 do pedido, e a estrutura para isso já existe.

### Onda 6 — Confiança e evidência

**6.1 Levar `confidence`/`tier` para o resultado de busca**, como já existe no
grafo.

**6.2 Marcar frescor.** O chunk sabe seu `content_hash`; comparar com o disco
diz se o índice está atrás. Um agente que recebe `stale: true` pode chamar
`refresh` em vez de raciocinar sobre código velho.

---

## 5. O que não foi concluído

Para não passar hipótese como resultado:

- **A troca de modelo foi medida** (3.5.1), mas com n=26. O ganho de MRR é
  sólido; o de recall@5 é consistente e não separável estatisticamente. Precisa
  do conjunto ampliado (1.3) para virar decisão fechada. Não comparei outros
  candidatos (`multilingual-e5-large`, `jina-embeddings-v2-base-code`), e o de
  código pode ser melhor ainda num corpus com mais código que prosa.
- **Não medi o custo de indexação da troca.** Sei que `batch=32` estoura e que
  `batch=4` funciona, mas não cronometrei a indexação completa nem medi o
  tamanho final do índice.
- **Não avaliei qualidade de geração**, só de recuperação — que é o que o RAGX
  controla, e é a escolha certa do projeto.
- **Não medi em outro corpus.** Tudo aqui é sobre o RAGX indexando a si mesmo:
  um repositório Python + Markdown, com muita documentação em português. As
  conclusões sobre chunking de PHP/JS/TS (3.7) são leitura de código, não
  medição.
- **Não investiguei `@base/` e federação** sob a ótica de recuperação. São
  13,1% do corpus e entram no mesmo ranking; se o achado 3.4 vale para `task/`,
  provavelmente vale para conhecimento base também.
- **Os números de latência são de uma máquina** (Windows, CPU, ONNX). A ordem
  de grandeza do achado 3.1 é robusta — 2,5 s contra 10 ms não vira empate em
  outro hardware —, mas os valores exatos, não.

---

## 6. Ordem sugerida

Se só houver espaço para três coisas:

1. **Cachear o embedder** (1.1) — 50× na latência da busca, risco quase zero.
2. **Corrigir a métrica e ampliar o conjunto** (1.2 + 1.3) — sem isso, nenhuma
   decisão de retrieval é verificável.
3. **Separar `task/` do conhecimento** (2.1) — maior ganho de precisão por
   linha alterada.

E logo em seguida, porque já está medido e ataca a ressalva que o projeto
publica sobre si mesmo:

4. **Trocar o modelo de embedding** (3.1) — híbrido de 0,62 para 0,77 de
   recall, MRR de 0,51 para 0,58, com `batch` ajustado. Confirmar no conjunto
   ampliado antes de anunciar.

As ondas 4 a 6 só valem depois, e cada uma deve entrar com o número que a
justifica ao lado.
