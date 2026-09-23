# 12 — Git Sync e conhecimento versionado (Fase 9)

Fecha o ciclo de colaboração: o conhecimento vive no Git junto com o código,
e cada dev reconstrói o índice local com um comando.

## O que vai e o que não vai para o Git

Versionado (texto, diffável, revisável em PR, dentro do orçamento do doc 16):

```text
knowledge/manifest.json
knowledge/documents/*.json
knowledge/chunks/*.jsonl          SEM o campo "content"
knowledge/embeddings/shard-*.i8   int8 @ 256d, shardado por prefixo de ID
knowledge/entities/shard-*.json
knowledge/relations/shard-*.json
knowledge/dictionary.json
knowledge/federation/**           superfície pública (doc 17)
agents/**
.ragignore
ragx.toml
.gitattributes
```

Nunca versionado:

```text
.ragx/                    banco local, cache, logs — derivado e descartável
~/.ragx/hub/              hub da máquina
*.rag                     pacote de distribuição, não fonte
```

`ragx init` escreve isso no `.gitignore` do projeto automaticamente.

### As duas decisões de tamanho

Detalhadas em [16 — Orçamento de tamanho](16-orcamento-de-tamanho.md) e
[ADR-0010](adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md).

**1. Conteúdo de chunk não vai para o Git.** É redundante: já está no repositório,
no caminho e nas linhas registradas. `ragx sync` reidrata do working tree e confere
`content_hash`.

```text
{"id":"a3f1…","ordinal":4,"kind":"method","symbol":"AuthService.login",
 "lines":[24,71],"content_hash":"9c2e…","tokens":183,"parent":"b7d0…"}
 ▲ sem "content" — economiza ~900 bytes por chunk
```

**2. Embeddings vão para o Git, quantizados.** A proposta inicial era deixá-los de
fora, o que obrigava todo dev a ter Ollama rodando antes da primeira busca. Em
int8 @ 256d o custo cai para **24 MB por 100k chunks**, e passa a valer a pena:

| Representação | 100k chunks | Versionado? |
|---------------|-------------|-------------|
| float32 @ 768d | 293 MB | não — fica em `.ragx/` |
| **int8 @ 256d** | **24 MB** | **sim** |

Resultado: `git clone && ragx search` já responde, offline, sem embedder.
`[embedding] versioned_dim = 0` desliga, para quem preferir sempre regerar.

## Layout dos artefatos versionados

Um arquivo por documento evita que cada mudança em um arquivo reescreva um JSON
gigante — isso é o que torna o diff legível e o merge viável.

```text
knowledge/
├── manifest.json
├── documents/
│   ├── src__Auth__AuthService.php.json
│   └── docs__auth.md.json
├── chunks/
│   ├── src__Auth__AuthService.php.jsonl
│   └── docs__auth.md.jsonl
├── embeddings/
│   ├── manifest.json          # modelo, dim, quantização, nº de shards
│   └── shard-00.i8 … shard-0f.i8
├── entities/shard-*.json
├── relations/shard-*.json
└── federation/
```

Nome do arquivo = `rel_path` com `/` → `__`. Colisão (um caminho real contendo `__`)
é resolvida com sufixo `-<hash6>`.

Agregados (embeddings, entidades, relações) são shardados **por prefixo do ID**, e
não por ordem de inserção. É isso que mantém o diff pequeno: um chunk novo cai
sempre no mesmo shard, e os outros 15 ficam byte-idênticos. Shard que passar de
`size.max_artifact_bytes` dobra a contagem de shards (16 → 32), com rebalanceamento
registrado no `embeddings/manifest.json`.

Regras de serialização — sem elas o Git vira ruído:

- JSON com `sort_keys=True`, `indent=2`, `ensure_ascii=False`, newline `\n`.
- JSONL com uma linha por chunk, ordenada por `ordinal`.
- Nenhum timestamp por chunk. Timestamps só no `manifest.json`.
- `.gitattributes`: `knowledge/** text eol=lf` — evita que o Windows transforme
  todo o diretório em diff de CRLF.

## `ragx sync`

```bash
git pull
ragx sync
```

```text
Sync — /projeto

  Git:         c4f19ab → 8a21e7f  (12 commits)
  Arquivos:    3 novos · 2 modificados · 1 removido

  Reidratando conteúdo de knowledge/...
    1.832 chunks · 1.809 ok · 21 re-derivados (hash divergente) · 2 descartados (arquivo ausente)

  Aplicando delta...
    + src/Payment/RefundService.php      (14 chunks)
    + docs/refund.md                     (6 chunks)
    ~ src/Auth/AuthService.php           (2 chunks alterados de 9)
    - src/Legacy/OldPayment.php          (11 chunks removidos)

  Embeddings:  22 novos · 18 do cache · 1.792 int8 reaproveitados do repo
  Grafo:       reconstruído (camadas 1-2) · 340 → 351 entidades
  Dictionary:  atualizado
  Federação:   provides 12 · consumes 8   → ragx hub sync para propagar
  Tamanho:     19,5 MB / 100 MB  ██░░░░░░░░

  Tempo 4,1 s
```

Os 2 descartados não são silenciados: `ragx sync --report` lista quais chunks
apontavam para arquivos que não existem mais, o que costuma indicar `knowledge/`
desatualizado em relação ao código.

Detecção do delta, em ordem de preferência:

1. **Git** — `git diff --name-status <ultimo_sync_commit> HEAD`. Rápido e exato.
2. **Fallback** — comparação de `content_hash` contra `sync_state`, quando não há
   repositório Git ou o commit anterior não existe mais (rebase, shallow clone).

O commit do último sync fica em `meta.last_sync_commit`. Se o histórico foi
reescrito e o commit sumiu, o RAGX cai no fallback automaticamente em vez de falhar.

Importante: o delta do Git diz quais **arquivos** mudaram; quais **chunks** mudaram
continua sendo decidido por `content_hash`. Um commit que só troca indentação não
gera chunk novo, porque a normalização de ID remove trailing whitespace.

## Merge

```text
Developer A                Developer B
  docs/a.md                  docs/b.md
  knowledge/documents/       knowledge/documents/
    docs__a.md.json            docs__b.md.json
       │                          │
       └──────────┬───────────────┘
                  ▼
             Git merge            ← arquivos distintos: sem conflito
                  ▼
             ragx sync             ← reconstrói .ragx/knowledge.db local
```

Arquivos diferentes → sem conflito, que é o caso comum. Quando **o mesmo** documento
é alterado dos dois lados, o conflito aparece no `.jsonl` daquele documento.

Estratégia para isso: `ragx sync --resolve` descarta o lado conflitante e **rederiva**
os chunks a partir do arquivo-fonte já mergeado pelo Git. Os artefatos em
`knowledge/` são derivados — resolver conflito neles à mão é perda de tempo,
a fonte de verdade é o código.

Merge driver opcional instalado por `ragx init --git-hooks`:

```gitattributes
knowledge/chunks/*.jsonl merge=ragx-derived
```

```ini
[merge "ragx-derived"]
    name = RAGX derived knowledge
    driver = ragx sync --resolve-file %A
```

## Hooks

`ragx init --git-hooks` (ou `ragx hooks install`) instala, com consentimento
explícito:

| Hook | Faz | Quando |
|------|-----|--------|
| `post-checkout` | `ragx index --source hook:post-checkout` destacado | só em troca de branch (flag 1) |
| `post-commit` | `ragx index --source hook:post-commit` destacado | todo commit |
| `post-merge` | `ragx index --source hook:post-merge` destacado | todo merge e pull |

Os hooks nunca rodam `ragx sync`, que regrava os arquivos versionados em
`knowledge/`; eles só disparam `ragx index` destacado, em segundo plano, para
o `.ragx/knowledge.db` local acompanhar a branch em que você está. Nenhum
hook bloqueia o git: a indexação roda destacada e o log fica em
`.ragx/logs/hooks.log`. Um `pre-commit` com
`ragx security scan --staged` ainda não existe como hook instalado por
`ragx init --git-hooks`: o comando já existe e pode ser ligado à mão no
`pre-commit` do projeto.

### O índice segue a branch atual

Cada indexação registra em `index_runs` a branch, o commit e quem disparou
(ver [03-modelo-de-dados.md](03-modelo-de-dados.md)). A decisão deste projeto é
que `.ragx/knowledge.db` reflete sempre a branch **atual** do working tree, não
um histórico por branch: trocar de branch e rodar `ragx index` (a mão ou via
hook `post-checkout`) reindexa o que mudou para a branch nova. Isso mantém o
índice simples (um banco, uma árvore de trabalho) ao custo de reindexar de
novo a cada troca, o que é aceitável porque a indexação incremental só
reprocessa o que o `content_hash` diz que mudou.

`ragx status --json` expõe `freshness.state` (`fresh` | `stale` | `unknown`) e
`freshness.reasons`, com até quatro motivos de defasagem:

- `branch_changed`: a branch atual é diferente da branch do último run.
- `commits_since_index`: o commit atual está à frente do commit do último run.
- `uncommitted_changes`: arquivos do working tree mudaram depois do último run.
- `pending_embeddings`: há chunks sem vetor.

`freshness.state` também é `unknown` quando o projeto é um repositório git mas
o último run útil não tem `git_commit` gravado (runs de antes da migração
0006, feitos por uma versão antiga do CLI): sem commit registrado não há
proveniência para comparar, então o estado não pode virar "fresh" por
omissão, só "stale" se outro motivo (por exemplo `pending_embeddings`)
disparar.

## Reidratação em detalhe

É o mecanismo que permite não versionar conteúdo. Roda no `ragx sync`, antes do delta:

```text
para cada chunk em knowledge/chunks/*.jsonl:
    lê rel_path[start_line:end_line] do working tree
        │
        ├── arquivo ausente        → descarta o chunk, registra file_missing
        ├── hash(conteúdo) != content_hash
        │                          → re-deriva o documento inteiro (o arquivo mudou)
        └── hash bate              → chunk reconstruído
                                     embedding int8 do repo reaproveitado
```

Três propriedades que isso garante:

1. **Autoverificação.** Reidratação errada é impossível de passar despercebida —
   o hash não bate e o documento é reprocessado.
2. **Convergência.** `knowledge/` desatualizado não corrompe nada: os chunks
   divergentes são simplesmente re-derivados.
3. **Offline.** Nenhuma etapa precisa de rede ou de embedder.

Limite honesto: `knowledge/` de um commit muito antigo aponta para linhas que já
mudaram, e quase tudo será re-derivado. O sync fica lento, não incorreto — e é o
comportamento certo, porque conhecimento é derivado do presente.

## CI

```yaml
- run: ragx security scan . --json --fail-on high
- run: ragx index . && ragx dictionary generate && ragx federation build
- run: ragx size --check                     # orçamento do doc 16
- run: git diff --exit-code knowledge/      # knowledge/ está atualizado?
```

O terceiro passo é o que garante que ninguém commita código sem atualizar o
conhecimento. Alternativa mais gentil: um job que abre PR com o `knowledge/` regenerado.

## Critério de aceite da Fase 9

1. `git pull && ragx sync` atualiza apenas o delta; arquivo inalterado não é reprocessado.
2. Dois devs editando documentos diferentes fazem merge sem conflito em `knowledge/`.
3. Conflito no mesmo documento é resolvido por `ragx sync --resolve` sem intervenção manual.
4. Nenhum `.db`, `.sqlite` ou vetor float32 é versionado.
5. `ragx sync` funciona em repositório **sem** Git (fallback por hash).
6. `git diff knowledge/` após reindexação sem mudanças é **vazio** — serialização estável.
7. `git clone && ragx search` responde **sem embedder e sem rede**, usando os vetores
   int8 versionados.
8. Alterar um arquivo muda os artefatos daquele documento e **1 shard** de embeddings
   entre 16 — verificado por teste de diff.
9. Reidratação reporta `ok` / `hash_mismatch` / `file_missing` para todo chunk, e
   nenhum caso é silenciado.
10. `ragx size --check` passa em repositório de referência e falha ao ultrapassar o
    orçamento.
