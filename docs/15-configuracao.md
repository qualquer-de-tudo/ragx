# 15 — Configuração

## Precedência

```text
1. flags da CLI                     (maior precedência)
2. variáveis de ambiente RAGX_*
3. ragx.toml do projeto
4. ~/.config/ragx/config.toml       (usuário)
5. defaults embutidos               (menor precedência)
```

A raiz do projeto é o diretório mais próximo, subindo a partir do cwd, que contenha
`ragx.toml`. Sem ele, o cwd é a raiz e um aviso é emitido sugerindo `ragx init`.

## `ragx.toml` completo

```toml
[project]
name = "meu-projeto"
# id gerado no init; usado para nomear caches e pacotes. Não é segredo.
id = "a91c4f2e"
kind = "http-service"           # http-service | library | frontend | monorepo | other
visibility = "workspace"        # workspace | private (private fica fora do hub)

[index]
include_unknown  = false        # extensões fora da lista fechada
max_file_bytes   = 1048576      # 1 MiB
follow_symlinks  = false
jobs             = 0            # 0 = cpu_count
batch_size       = 200          # arquivos por transação
exclude = [
  "**/snapshots/**",
  "**/*.generated.*",
]

[chunk]
version     = "1"               # NÃO editar à mão; bump é feito pelo código
max_tokens  = 512
min_tokens  = 24
overlap     = 0                 # chunking estrutural não usa overlap por padrão

[security]
policy          = "strict"      # strict | balanced
min_entropy     = 3.0
allow_remote_llm = false        # bloqueia camada semântica do grafo/dictionary
ruleset         = "builtin"     # builtin | builtin+custom
custom_rules    = ".ragx/rules/*.yaml"
disabled_rules  = []            # toda regra aqui aparece em `ragx doctor` como aviso
scan_content    = true

[embedding]
provider  = "ollama"            # ollama | fastembed | hashing(testes)
model     = "nomic-embed-text"
dim       = 768                 # dimensão nativa, usada localmente (float32)
base_url  = "http://localhost:11434"
batch     = 32
timeout_s = 60
cache     = true
normalize = true
# --- representação versionada no Git (doc 16 / ADR-0010) ---
versioned_dim   = 256           # truncagem Matryoshka; 0 desliga o versionamento
versioned_quant = "int8"        # int8 | none
rescore         = true          # 2º estágio com float32 local, quando disponível

[size]
max_artifact_bytes = 20_971_520   # 20 MB — acima disso, shard obrigatório
warn_total_bytes   = 104_857_600  # 100 MB — aviso
fail_total_bytes   = 262_144_000  # 250 MB — RECUSA a gravação
max_chunks         = 500_000
shards             = 16           # dobra automaticamente se um shard estourar

[federation]
enabled      = true
auto_build   = true             # gera knowledge/federation/ ao fim do sync
manual_file  = "knowledge/federation/manual.json"   # curado, vence o derivado
detect_http  = true
detect_events = true
detect_packages = true
detect_tables = true
min_confidence = 0.6            # abaixo disso vira sugestão, não aresta

[hub]
path          = "~/.ragx/hub"
auto_sync     = false           # true sincroniza o hub ao fim do ragx sync
external_penalty = 0.85         # penalidade de score para projeto externo
max_projects  = 50

[search]
default_mode    = "hybrid"
limit           = 10
rrf_k           = 60
weight_semantic = 1.0
weight_keyword  = 0.8
candidate_factor = 3            # pede 3x o limit em cada motor antes da fusão
max_per_document = 3            # diversidade de fonte

[graph]
enabled     = true
max_depth   = 2
max_nodes   = 200
max_fanout  = 25
decay       = 0.6
semantic    = false             # camada 3 (LLM)

[context]
default_tokens   = 3000
dedup_threshold  = 0.93
mmr_lambda       = 0.7
compress         = true
reserve_ratio    = 0.05         # overhead de formatação
min_sources      = 3

[dictionary]
out_dir  = "knowledge"
semantic = false

[mcp]
read_only    = true
allow_index  = false
log_queries  = false            # true grava o texto da query no log
rate_per_min = 60
max_response_bytes = 1048576

[sync]
auto_dictionary  = true         # regenera dictionary no sync
auto_federation  = true         # regenera federation/ no sync
rehydrate_strict = false        # true: chunk com arquivo ausente falha o sync
git_hooks        = false

[log]
level  = "info"                 # debug | info | warn | error
dir    = ".ragx/logs"
retain_days = 14
```

## Variáveis de ambiente

Mapeamento direto, `RAGX_` + seção + chave em maiúsculas:

```bash
RAGX_EMBEDDING_PROVIDER=fastembed
RAGX_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RAGX_EMBEDDING_VERSIONED_DIM=128
RAGX_SECURITY_POLICY=strict
RAGX_SIZE_FAIL_TOTAL_BYTES=400000000
RAGX_HUB_PATH=/caminho/do/hub
RAGX_LOG_LEVEL=debug
RAGX_PROJECT=/caminho/do/projeto
```

Duas com tratamento especial:

| Variável | Uso |
|----------|-----|
| `OLLAMA_HOST` | respeitada se `embedding.base_url` não estiver definido |
| `OLLAMA_MODELS` | só informativa; o RAGX não lê o diretório de modelos direto |

**Nenhuma chave de API é lida de `ragx.toml`.** Credenciais de provider remoto
(usadas apenas nas camadas semânticas opt-in) vêm exclusivamente de variável de
ambiente. Um arquivo de config versionado no Git não é lugar para segredo — e o
próprio scanner bloquearia o arquivo.

## `.ragignore`

Sintaxe idêntica ao `.gitignore`, aplicada depois dele. Criado pelo `ragx init`:

```gitignore
# .ragignore — o que o RAGX não deve indexar
# (segredos já são bloqueados pelo scanner, independente deste arquivo)

# artefatos de build
dist/
build/
coverage/

# dados grandes
*.csv
*.parquet
data/dumps/

# gerado
**/*.generated.*
**/migrations/*_auto_*.py

# reindexar isto é ruído
CHANGELOG.md
```

Negação funciona:

```gitignore
docs/**
!docs/architecture/**
```

## Perfis de embedding

### Ollama (padrão)

Já existe um `nomic-embed-text` em `E:\RAGPAG\ragpag\ollama_models`. Para usá-lo:

```bash
set OLLAMA_MODELS=E:\RAGPAG\ragpag\ollama_models
ollama serve
```

```toml
[embedding]
provider = "ollama"
model    = "nomic-embed-text"
dim      = 768
```

### fastembed (sem daemon — a opção quando não há Ollama)

ONNX Runtime embarcado. Baixa o modelo uma vez para `.ragx/cache/models/` e
funciona offline a partir daí. Não exige serviço nenhum rodando.

```bash
uv pip install "ragx[embed]"
```

```toml
[embedding]
provider      = "fastembed"
model         = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
dim           = 384
versioned_dim = 192
```

Multilíngue por padrão: o corpus típico é português + código. Alternativas:

| Modelo | dim | tamanho | nota |
|--------|-----|---------|------|
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | 220 MB | **padrão** |
| `BAAI/bge-small-en-v1.5` | 384 | 70 MB | só inglês, mais leve |
| `intfloat/multilingual-e5-large` | 1024 | 2,2 GB | melhor qualidade, mais pesado |

Trocar de modelo invalida os vetores existentes — ver *Trocar de modelo de
embedding* mais abaixo.

### hashing (testes)

Determinístico, sem rede, sem modelo. Qualidade semântica nula — serve apenas para
testar o *pipeline*, nunca para medir qualidade de busca.

```toml
[embedding]
provider = "hashing"
dim      = 256
```

## Trocar de modelo de embedding

Modelos diferentes produzem espaços vetoriais incomparáveis. Ao detectar mudança em
`embedding.model` ou `embedding.dim`, o RAGX:

1. Avisa e pede confirmação (`--yes` pula).
2. Registra o novo modelo em `embedding_models`.
3. Re-embarca todos os chunks (`ragx index --embed-only`).
4. Mantém os vetores antigos até o fim, e só então remove — busca não fica quebrada
   no meio do processo.

Chunks e grafo **não** são refeitos: mudar de embedder não muda o fatiamento.

Em ambiente multiprojeto, a troca tem um efeito extra: projetos com modelos
diferentes deixam de ser comparáveis semanticamente. O hub detecta isso e mantém o
projeto divergente na consulta cross-project **apenas por keyword e federação**,
reportando a degradação em `ragx hub status`. Comparar vetores de modelos distintos
produziria ranking aleatório com aparência de resultado — por isso a degradação é
explícita, nunca silenciosa.

## Orçamento de tamanho

`[size]` é uma restrição, não uma preferência: ao projetar que a gravação de
`knowledge/` estouraria `fail_total_bytes`, o RAGX **recusa a escrita** com
sugestões acionáveis, em vez de truncar. Ver [16 — Orçamento de tamanho](16-orcamento-de-tamanho.md).

```bash
ragx size --projection          # antes de indexar um repositório grande
ragx size --check               # em CI
```

## Validação

`ragx doctor` valida a configuração inteira e reporta de forma acionável:

```text
ragx doctor

  Python            3.13.14                                  ok
  SQLite            3.45.1 (FTS5 ✓)                          ok
  Schema            v7 (atual)                               ok
  Projeto           E:\RAGPAG\meu-projeto                    ok
  Config            ragx.toml (12 overrides)                 ok
  Ruleset           builtin@1 — 48 regras, 0 desabilitadas   ok
  Embedder          ollama:nomic-embed-text (768d)           FALHA
                    → conexão recusada em http://localhost:11434
                    → inicie o daemon: ollama serve
                    → ou use: ragx config set embedding.provider fastembed
  Escrita em .ragx/                                          ok

  1 problema. Busca semântica indisponível; keyword continua funcionando.
```
