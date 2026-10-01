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
no caminho e nas linhas registradas. `ragx sync --rehydrate` reidrata do working tree e confere
`content_hash` (opt-in: o `sync` comum não reidrata, porque relê o projeto inteiro).

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

Resultado: depois de `git clone && ragx sync` a busca responde **sem recalcular os vetores** dos chunks
que já estão em `knowledge/embeddings/`. A consulta ainda precisa de um embedder para virar vetor; sem
ele a busca cai para palavra-chave (`degraded`). `[embedding] versioned_dim = 0` desliga, para quem
preferir sempre regerar.

**O fluxo de um clone novo (RAGX-0144).** `ragx sync` não exige banco prévio: indexa o working tree
(que já existe), **importa** o int8 versionado para os chunks que continuam iguais
(`sync/embeddings_import.py`) e embute só o que falta (arquivo novo ou editado depois do commit).
Os vetores importados ficam **só grosseiros** (`vector` nulo, busca em int8@`versioned_dim`); a busca
avisa em `partial` ("vetores só grosseiros (int8@192): N chunks sem float32") e
`ragx index --embed-only` completa o float32. O import é seguro por construção: só o **mesmo modelo**
(o manifesto precisa citar `embedder_id` e a mesma `versioned_dim`; senão nada é importado, e o `sync`
avisa), só `chunk_id` que existe em `chunks` (já passou pelo Security Gate), só vetor com o tamanho
certo e escala finita, shard com magic ou tamanho incoerente é descartado e contado, e nunca
sobrescreve um vetor completo. Hooks, `watch`, `touch` e o `refresh` do agente não completam o float32
em segundo plano; só `ragx index` (e `--embed-only`) o fazem.

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
| `post-checkout` | `ragx index --source hook:post-checkout` destacado | só em troca de branch (flag 1), decidido **no shell do hook** (`[ "$3" = "1" ]`): `git checkout -- arquivo` não sobe Python nenhum |
| `post-commit` | `ragx index --source hook:post-commit` destacado | todo commit |
| `post-merge` | `ragx index --source hook:post-merge` destacado | todo merge e pull |

O bloco chama `ragx hook-run`, que entra pelo ponto de entrada leve (`ragx.entry`, só stdlib): a parte
síncrona do hook (disparar a indexação destacada e devolver o terminal) leva **~110 ms** em vez de
**~510 ms**, e o commit deixa de esperar a CLI inteira. Hooks instalados antes dessa mudança continuam
funcionando, mas sem a guarda de shell do `post-checkout`: `ragx hooks status` avisa e `ragx hooks
install` reescreve o bloco.

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

É o mecanismo que permite não versionar conteúdo. Roda no `ragx sync --rehydrate` (e `--report`, que o implica), antes do delta. **Não** roda no `sync` comum nem no `refresh` do MCP: relê, passa pelo gate e rechunka o projeto inteiro para produzir um relatório, 13,7 s no repo do RAGX (RAGX-0131). Também no `sync`, o grafo é refeito **antes** de `knowledge/` ser regravado, e a regravação é pulada quando nada mudou desde o último `sync` completo (token em `meta('knowledge_token')`):

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
