# 06 — Grafo de conhecimento (Fase 3)

Vetores respondem "o que é parecido com isto". Grafo responde "o que está **ligado**
a isto". As duas coisas são complementares, e a segunda só entra depois que a
primeira funciona.

## Modelo

```text
AuthService  (service)
     │
     ├── uses ──────────► Redis        (technology)
     ├── calls ─────────► SsoProvider  (service)
     ├── contains ──────► login        (method)
     ├── imports ───────► TokenPolicy  (class)
     └── documented_by ► docs/auth.md  (file)
```

### Tipos de entidade

| Tipo | Origem | Exemplo |
|------|--------|---------|
| `file` | estrutural | `src/Auth/AuthService.php` |
| `class` | estrutural | `AuthService` |
| `function` / `method` | estrutural | `AuthService.login` |
| `endpoint` | referencial | `POST /api/login` |
| `table` | referencial | `users` (de `.sql`) |
| `service` | semântica | `AuthService` promovido a serviço de domínio |
| `technology` | semântica | `Redis`, `Laravel`, `PostgreSQL` |
| `concept` | semântica | `autenticação`, `rate limiting` |

### Tipos de relação

| Relação | Direção | Extraída por |
|---------|---------|--------------|
| `contains` | file → class → method | estrutural |
| `imports` | file → module | estrutural |
| `calls` | function → function | referencial |
| `implements` / `extends` | class → class | estrutural |
| `uses` | entidade → technology | referencial/semântica |
| `documented_by` | code entity → doc file | referencial |
| `depends_on` | service → service | semântica |
| `mentions` | doc section → entidade | referencial |

## Estratégia em três camadas

A ordem aqui importa: **não comece por LLM**. As duas primeiras camadas são
determinísticas, baratas e cobrem a maior parte do valor.

### Camada 1 — estrutural (determinística)

Vem direto do `ParseResult` já produzido na Fase 1. Custo ~zero, precisão ~100%.

```text
arquivo     → classe          contains
classe      → método          contains
documento   → seção           contains
arquivo     → import          imports
classe      → superclasse     extends
```

### Camada 2 — referencial (determinística, heurística)

Cruza nomes já conhecidos com o texto dos chunks. Só cria aresta para entidade que
**já existe** na camada 1 — isso evita inventar nós.

```text
chamada `AuthService::login(` em outro arquivo     → calls
`use App\Auth\AuthService;`                        → imports
heading "AuthService" em docs/auth.md              → documented_by
`Redis::get(` / `redis` em docker-compose          → uses (technology)
`CREATE TABLE users`                               → table + contains
rota `Route::post('/api/login', ...)`              → endpoint
```

Catálogo de tecnologias: lista curada em `graph/extractors/technologies.yaml`
(nome, aliases, sinais de detecção — import, arquivo de config, dependência no
`composer.json`/`package.json`/`pyproject.toml`). Reconhecer tecnologia por
dependência declarada é muito mais confiável do que por menção em texto.

### Camada 3 — semântica (opcional, com LLM)

Só depois das duas anteriores, e sempre **opt-in**:

```bash
ragx graph rebuild --semantic --model <provider:model>
```

- Entrada: apenas chunks já admitidos pelo gate (nunca o arquivo bruto).
- Saída: JSON validado por schema Pydantic; qualquer item fora do schema é descartado.
- Toda entidade/relação criada aqui grava `source = "semantic"` e `confidence < 1.0`.
- Entidade semântica que não puder ser ancorada em pelo menos um `chunk_id` é rejeitada
  — sem âncora não há como citar a fonte, e conhecimento sem fonte não entra.
- É o único ponto do sistema que envia conteúdo para um modelo generativo; respeita
  `security.allow_remote_llm` (padrão `false`).

## Consultas

```bash
ragx entities                             # lista entidades
ragx entities --type service
ragx graph show AuthService                    # vizinhança de uma entidade
ragx graph show AuthService --depth 2 --json
ragx graph-search "serviços relacionados a autenticação"
```

Saída de `ragx graph show AuthService`:

```text
AuthService  (service)  src/Auth/AuthService.php

  ← contains        App\Auth (module)
  → contains        login, logout, refresh (3 methods)
  → uses            Redis, JWT
  → calls           SsoProvider.validate
  → documented_by   docs/auth.md § Fluxo SSO
  ← calls           LoginController.store, ApiMiddleware.handle

  12 relações · profundidade 1
```

## Graph search — vetor + grafo

É aqui que o grafo paga o próprio custo:

```text
query
  ↓
busca híbrida (Fase 2)            → chunks semente
  ↓
chunks → entidades âncora          via chunk_id/document_id
  ↓
expansão BFS até `depth` saltos    com decaimento por salto
  ↓
entidades → chunks representativos
  ↓
fusão com o resultado original     (RRF novamente)
```

Decaimento: `peso_final = score_semente × (decay ** salto) × relation.weight`,
com `decay = 0.6` por padrão. Sem decaimento, dois saltos trazem o repositório inteiro.

Limites obrigatórios (senão a expansão explode):

```text
graph.max_depth        2
graph.max_nodes        200      teto absoluto de nós visitados
graph.max_fanout       25       vizinhos por nó (os de maior weight)
```

Nós de altíssimo grau (um `utils.php` importado por tudo) são despriorizados por
penalidade de grau: `weight /= log(1 + grau)`.

## Persistência e reconstrução

O grafo é **derivado**. `ragx graph rebuild` reconstrói as camadas 1 e 2 do zero a
partir de `chunks`, em segundos. A camada 3 é preservada por `source = "semantic"`
e só é refeita sob comando explícito, porque custa dinheiro.

Na indexação incremental: remover um documento remove (cascade) suas entidades
estruturais; relações que apontavam para elas caem junto. Entidades semânticas
órfãs viram lixo removido por `ragx vacuum`.

## Modelo de confiança

Toda entidade e relação carrega `confidence` (float) e `source` (a camada que
a gerou). `confidence_tier()` (`src/ragx/graph/store.py`) resume isso num
rótulo em linguagem natural, a mesma distinção que ferramentas como o
Graphify chamam de `EXTRACTED`/`INFERRED`:

| `source` | `confidence` típico | `tier` |
|---|---|---|
| `structural` (Camada 1 — hierarquia já está no chunk) | 1.0 | `extracted` |
| `reference` (Camada 2 — regex/heurística) | 0.6 – 0.8 | `inferred` |
| `semantic` (Camada 3, custa dinheiro — ver nota acima) | variável | depende |

`get_entity` (MCP) e `ragx graph show` (CLI) expõem os três campos. Um agente
que recebe `tier: "inferred"` sabe que aquela relação foi deduzida, não lida
direto da fonte — trate com a mesma cautela que trataria um `INFERRED` de
qualquer outra ferramenta de grafo.

## Critério de aceite da Fase 3

1. `ragx graph rebuild` em repositório real produz grafo sem nós órfãos e sem
   duplicata (`UNIQUE(type, qualified_name)` respeitado).
2. Uma consulta combinando **vetor + grafo** encontra conhecimento relacionado que
   a busca híbrida pura não encontra — demonstrado por pelo menos 3 casos no
   conjunto de avaliação.
3. Expansão respeita `max_depth`/`max_nodes` e termina em < 100 ms.
4. Nenhuma entidade ou relação deriva de arquivo bloqueado
   (`xfail` de "0 nós de grafo com segredo" vira `pass`).
5. Camadas 1 e 2 funcionam **sem nenhum LLM configurado**.
