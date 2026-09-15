# 16 — Orçamento de tamanho (restrição de Git)

> Requisito duro: **o conhecimento versionado nunca pode estourar o que o Git aceita.**
> Isso não é uma otimização a fazer depois — é uma restrição que decide o que pode ser
> gravado em `knowledge/`.

## Os limites reais

| Limite | Valor | Consequência |
|--------|-------|--------------|
| Arquivo individual (GitHub) | > 50 MB | aviso no push |
| Arquivo individual (GitHub) | > 100 MB | **push rejeitado** |
| Repositório (GitHub) | > 1 GB | recomendação de não exceder |
| Repositório (GitHub) | > 5 GB | suporte pode entrar em contato |
| Git (qualquer) | sem limite duro | mas `clone` e `gc` degradam rápido |

Agravante que costuma ser esquecido: **o Git guarda histórico**. Um arquivo de 40 MB
reescrito a cada indexação não custa 40 MB — custa 40 MB por commit. O tamanho que
importa não é o do working tree, é o do `.git/`.

Por isso o orçamento do RAGX não é só "cabe no limite", é "**muda pouco entre commits**".

## Orçamento (padrões, configuráveis)

```toml
[size]
max_artifact_bytes = 20_971_520     # 20 MB — acima disso, shard obrigatório
warn_total_bytes   = 104_857_600    # 100 MB — aviso
fail_total_bytes   = 262_144_000    # 250 MB — recusa de escrita
max_chunks         = 500_000        # teto de chunks por projeto
```

O limite de arquivo é 20 MB e não 50 MB de propósito: margem para o pior caso
(um shard que cresce entre reindexações) sem nunca chegar perto do aviso do GitHub.

**Recusa, não truncamento.** Ao projetar que a gravação estouraria `fail_total_bytes`,
o RAGX **não escreve** e explica o que fazer. Truncar silenciosamente produziria um
índice incompleto que ninguém perceberia.

## As duas decisões que fazem caber

### 1. Conteúdo de chunk não é versionado

Insight central: para o repositório do próprio projeto, o conteúdo do chunk é
**100% redundante** — é uma fatia de um arquivo que já está versionado ali, num
caminho e num intervalo de linhas conhecidos.

```text
knowledge/chunks/src__Auth__AuthService.php.jsonl

  {"id":"a3f1…","ordinal":4,"kind":"method","symbol":"AuthService.login",
   "lines":[24,71],"content_hash":"9c2e…","tokens":183,"parent":"b7d0…"}
   ▲ sem "content"
```

Na hora do `ragx sync`, o conteúdo é **reidratado** do working tree:

```text
rel_path + [start_line, end_line]  →  lê do arquivo local
        ↓
  confere content_hash
        ↓
  bate  → chunk reconstruído, embedding versionado reaproveitado
  não bate → chunk re-derivado do arquivo (o arquivo mudou)
  arquivo ausente → chunk descartado e reportado
```

A conferência de hash é o que torna isso seguro: reidratação errada é detectada,
não silenciosa.

### 2. Embeddings versionados são quantizados

| Representação | Bytes/chunk | 100k chunks | Onde vive |
|---------------|-------------|-------------|-----------|
| float32 @ 768d | 3.072 | 293 MB | só local (`.ragx/`) |
| **int8 @ 256d** (Matryoshka) | **256** | **24 MB** | **versionado** |

`nomic-embed-text` é treinado com Matryoshka, então truncar 768 → 256 dimensões
preserva a maior parte do sinal. Sobre isso aplica-se quantização escalar int8 por
vetor (escala + offset gravados junto).

Busca em dois estágios:

```text
query
  ↓
[1] busca grosseira nos vetores int8@256    top-100
  ↓
[2] rescoring com float32@768 local          top-10     ← se disponível
  ↓
resultado
```

Sem os vetores float32 locais (logo após um `clone`), o estágio 2 é pulado: a busca
funciona com qualidade um pouco menor e o `ragx sync` regenera os vetores completos
em segundo plano quando houver embedder.

## Custo final por projeto

```text
                            10k      50k     100k     500k chunks
metadados de chunk          2 MB     9 MB    17 MB     86 MB
embeddings int8@256         2 MB    12 MB    24 MB    122 MB
grafo + dicionário          ~1 MB    ~3 MB    ~6 MB    ~25 MB
─────────────────────────────────────────────────────────────────
total versionado          ~5 MB    ~24 MB   ~47 MB   ~233 MB
                                                     ▲ aviso aos 100 MB
```

Para comparação, versionando conteúdo e float32: **396 MB com 100k chunks** — e
crescendo a cada commit.

## Sharding

Nenhum artefato versionado passa de `max_artifact_bytes`. Artefatos por documento
(`knowledge/documents/`, `knowledge/chunks/`) já são naturalmente pequenos. Os
agregados são shardados por prefixo do ID:

```text
knowledge/
├── embeddings/
│   ├── manifest.json        # modelo, dim, quantização, nº de shards
│   ├── shard-00.i8          # chunks cujo id começa com 00-0f
│   ├── shard-01.i8
│   └── …                    # 16 shards por padrão, dobra se algum estourar
├── entities/
│   ├── shard-00.json
│   └── …
└── relations/
    └── …
```

Shard por prefixo de ID (e não por ordem de inserção) é o que mantém o diff estável:
um chunk novo entra sempre no mesmo shard, e os outros 15 ficam byte-idênticos.

## Governança

```bash
ragx size                       # relatório do orçamento atual
ragx size --check               # exit 1 se estourar (uso em CI)
ragx size --projection          # projeta o tamanho antes de indexar
ragx size --history             # crescimento de knowledge/ ao longo dos commits
```

```text
ragx size

  Conhecimento versionado — knowledge/

    documents/          1.832 arquivos      3,1 MB
    chunks/             1.832 arquivos     11,4 MB
    embeddings/         16 shards           2,6 MB   int8@256 · ollama:nomic-embed-text
    entities/           4 shards            0,9 MB
    relations/          4 shards            1,2 MB
    dictionary.json     1 arquivo           0,2 MB
    federation/         6 arquivos          0,1 MB
    ─────────────────────────────────────────────
    total                                  19,5 MB   ██░░░░░░░░  20% de 100 MB

    maior artefato      chunks/src__Legacy__Bundle.js.jsonl   1,8 MB   (limite 20 MB)

  Local (não versionado) — .ragx/
    knowledge.db                           84,2 MB
    cache/                                112,7 MB

  Histórico Git de knowledge/:  +2,1 MB nos últimos 30 commits
```

Se `--projection` indicar estouro antes de uma indexação, a saída é acionável:

```text
  Projeção: 268 MB  ✗  excede fail_total_bytes (250 MB)

  Maiores contribuintes:
    vendor/bundles/**      412.000 chunks   198 MB
    data/fixtures/**        38.000 chunks    18 MB

  Sugestões:
    1. Adicionar ao .ragignore:  vendor/bundles/  data/fixtures/
    2. Reduzir dimensão: [embedding] versioned_dim = 128   (−12 MB)
    3. Elevar o teto:    [size] fail_total_bytes = 400_000_000
```

## Integração com CI

```yaml
- run: ragx index . && ragx size --check
- run: git diff --exit-code knowledge/
```

E, como proteção final, um `pre-commit` que barra qualquer arquivo versionado acima
do limite — inclusive os que não vieram do RAGX.

## Critério de aceite

1. `knowledge/` de um projeto de 100k chunks fica abaixo de 50 MB.
2. Nenhum artefato versionado passa de 20 MB; acima disso, sharding automático.
3. Reindexação sem mudanças produz `git diff` vazio — crescimento zero no histórico.
4. Uma alteração em um arquivo muda apenas 1 shard de embeddings, não os 16.
5. Projeção de estouro **recusa** a gravação com sugestões acionáveis.
6. Reidratação verifica `content_hash` e reporta toda divergência.
7. Busca funciona logo após `git clone`, sem embedder, usando só os vetores int8.
