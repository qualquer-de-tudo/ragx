# 11 — Export / Import (Fase 8)

Resolve o compartilhamento: um dev indexa, o time inteiro reaproveita — sem
reindexar e sem passar código-fonte sensível adiante.

```bash
ragx export project.rag
ragx export project.rag --include-embeddings --include-agents
ragx import project.rag
ragx import project.rag --merge          # funde com conhecimento existente
ragx inspect project.rag                 # lê o manifest sem importar
```

## Formato do pacote

`.rag` é um **ZIP** (deflate) com layout fixo. ZIP e não tar.gz porque permite ler
o `manifest.json` sem descompactar o arquivo inteiro — `ragx inspect` precisa disso.

```text
project.rag
├── manifest.json            # identidade, versões, checksums, política
├── knowledge/
│   ├── documents.jsonl      # metadados dos documentos (sem conteúdo bruto completo)
│   ├── chunks.jsonl         # chunks: id, doc, símbolo, linhas, conteúdo
│   ├── entities.json
│   ├── relations.json
│   └── dictionary.json
│   └── federation/          # superfície pública (doc 17) — sempre incluída
├── embeddings/              # opcional
│   ├── model.json           # id do modelo, dim, versioned_dim, quantização
│   └── vectors.i8           # int8 @ versioned_dim (float32 só com --full-vectors)
├── agents/                  # opcional
│   └── <nome>/...
└── CHECKSUMS.sha256
```

Duas notas de tamanho, herdadas do [16 — Orçamento](16-orcamento-de-tamanho.md):

- Embeddings no pacote são **int8** por padrão. `--full-vectors` inclui float32 e é
  opt-in, porque multiplica o tamanho por 12.
- `knowledge/chunks.jsonl` no pacote **inclui** o conteúdo, ao contrário do que vai
  para o Git: o pacote precisa ser autossuficiente para quem não tem o repositório.
  É por isso que `.rag` é um artefato de distribuição e `knowledge/` não.

## `manifest.json`

```json
{
  "schema_version": 1,
  "package_id": "018f...",
  "project": { "name": "meu-projeto", "project_id": "a91c..." },
  "created_at": "2026-09-15T13:02:00Z",
  "created_by": "ragx 0.8.0",
  "source": { "git_remote_hash": "7d2e...", "git_commit": "c4f19ab", "dirty": false },
  "versions": {
    "schema": 1,
    "chunker": "1",
    "ruleset": "builtin@1",
    "embedding_model": "ollama:nomic-embed-text",
    "embedding_dim": 768
  },
  "contents": {
    "documents": 120, "chunks": 1832, "entities": 340,
    "relations": 890, "embeddings": 1832, "agents": 1,
    "federation_provides": 12, "federation_consumes": 8
  },
  "security": {
    "policy": "strict",
    "scanned_at": "2026-09-15T13:01:58Z",
    "rules_count": 48,
    "rules_disabled": [],
    "findings": 0,
    "attestation": "9f3c..."
  },
  "checksums": { "algo": "sha256", "file": "CHECKSUMS.sha256" }
}
```

O bloco `source.git_remote_hash` é o hash do remote, não a URL — a URL pode conter
token (`https://user:token@host/repo.git`). Nunca gravar a URL crua.

## Pipeline de export

```text
Security Scan       re-scan COMPLETO do conteúdo a ser empacotado
      ↓             (não confia no scan da indexação — o ruleset pode ter mudado)
Integrity Check     IDs determinísticos conferem? chunks órfãos? embeddings sem chunk?
      ↓
Manifest            versões, contagens, atestação de segurança
      ↓
Package             ZIP + CHECKSUMS.sha256
```

O re-scan não é redundância inútil. Cenários reais que ele pega:

- O índice foi criado com uma versão antiga do ruleset, e uma regra nova detecta
  algo que passou antes.
- Um chunk foi marcado `redact` mas o placeholder falhou por bug.
- Um resumo gerado por LLM na Fase 5 vazou um valor.

**Export falha (exit 1) com qualquer achado `critical`/`high`.** Não há flag
`--force` para isso. Se o usuário quiser exportar mesmo assim, precisa corrigir a
origem e reindexar.

## O que NUNCA entra no pacote

```text
caminhos absolutos                  (vazam nome de usuário e estrutura da máquina)
conteúdo de arquivo bloqueado
security_events com preview/digest  (é metadado de incidente, não conhecimento)
.ragx/knowledge.db                  (binário; o pacote é o formato de troca)
logs
URL de remote com credencial
valores de variáveis de ambiente
```

`documents.jsonl` guarda metadados e referência; o conteúdo bruto completo do arquivo
não vai junto — o que viaja é o **chunk**, que já passou pelo gate. Quem importa o
pacote tem o repositório; o que falta é o conhecimento derivado.

## Import

```text
Verifica CHECKSUMS.sha256
      ↓
Valida manifest contra schema
      ↓
Checa compatibilidade  ── schema_version, chunker_version, embedding model/dim
      ↓
Security scan do conteúdo importado   (desconfiar de pacote de terceiro)
      ↓
Aplica em transação única   (replace | merge)
```

Matriz de compatibilidade:

| Divergência | Comportamento |
|-------------|---------------|
| `schema_version` maior que o suportado | **erro** — atualize o RAGX |
| `chunker_version` diferente | aviso: IDs não vão bater com reindexação local; conhecimento importado é marcado `foreign` |
| `embedding_model` diferente | embeddings **descartados**; busca semântica exige `ragx index --embed-only` local |
| `embedding_dim` diferente | embeddings descartados (não há como comparar dimensões distintas) |
| `ruleset` mais fraco que o local | aviso alto + re-scan obrigatório |

Modos:

- `--replace` (padrão): substitui o conhecimento do projeto.
- `--merge`: funde. Conflito de `chunk.id` idêntico → mantém o local (o local foi
  derivado do código real desta máquina). Conflito de entidade → une relações,
  mantém maior `confidence`.

Import **nunca** escreve fora de `.ragx/` e `knowledge/`. Um pacote malicioso com
`../../etc/passwd` no nome de entrada é rejeitado na validação (zip-slip).

## Fatia de federação avulsa (`.fed.json`)

Além do pacote completo, existe um formato mínimo para compartilhar **só** a
superfície pública de um projeto — o caso de "meu time não vai te dar acesso ao
repositório, mas aqui está o contrato":

```bash
ragx federation export payment.fed.json     # poucos KB
ragx project register --from-federation ./payment.fed.json
```

É `knowledge/federation/` serializado em um arquivo único, com o mesmo
`service.json` de identidade e os contratos embutidos por valor. Registrar por esse
caminho cria um projeto em estado **só-federação**: participa de `--scope all` com
seus contratos, sem busca de código. Ver [17 — Multiprojeto](17-multiprojeto-e-federacao.md).

## Critério de aceite da Fase 8

1. `ragx export` → `ragx import` em máquina limpa reproduz busca e grafo equivalentes,
   sem reindexar.
2. Export sobre a fixture de segredos falha com exit 1 e nomeia o achado.
3. Pacote exportado, descompactado e varrido por `grep` não contém **nenhum** dos
   segredos da fixture (`xfail` de "0 dados secretos no export" vira `pass`).
4. Nenhum caminho absoluto em nenhum arquivo do pacote.
5. Zip-slip e checksum corrompido são rejeitados por teste.
6. Import de pacote com modelo de embedding diferente degrada para busca keyword
   com aviso claro, sem quebrar.
