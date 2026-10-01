# 04 — Indexação (Fase 1)

## Pipeline

```text
FileWalker  →  IgnoreEngine  →  SecurityGate  →  Parser  →  Chunker  →  Store
                     │               │
                  skipped         blocked
```

Comando:

```bash
ragx index .                 # incremental (padrão)
ragx index . --full          # ignora cache, reindexa tudo
ragx index ./src --dry-run   # só relatório, não escreve
```

## FileWalker

Responsabilidades e limites:

- Caminha a partir da raiz do projeto (a que contém `ragx.toml`).
- **Recusa symlinks e junctions que apontam para fora da raiz** (ameaça A8). Por
  padrão (`index.follow_symlinks = false`) links de pasta **não são seguidos**, nem os
  que ficam dentro da raiz; com `true`, só os que resolvem para dentro dela, uma vez
  cada (ciclos detectados por `inode`/`st_ino` visitado). No Windows, **junction**
  (`mklink /J`, o que o pnpm cria) conta como link: o Python não a chama de symlink, e
  antes dela a pasta de fora era percorrida (RAGX-0149). Só `MOUNT_POINT` é junction;
  OneDrive e outros reparse points continuam sendo percorridos.
- Pula arquivos acima de `index.max_file_bytes` (padrão **1 MiB**) → `skipped:too_large`.
- Detecta binário: se os primeiros 8 KiB contêm `\x00`, o arquivo é binário → `skipped:binary`.
- Decodifica como UTF-8; em falha, tenta `utf-8-sig`, depois `latin-1`;
  se ainda falhar → `skipped:undecodable`.
- Emite `FileCandidate(rel_path, size, mtime_ns, raw_bytes)` em streaming — não
  carrega o repositório inteiro em memória.

## Formatos suportados no MVP

Lista **fechada**. Qualquer extensão fora dela cai no `FallbackChunker` (texto) ou
é ignorada, conforme `index.include_unknown` (padrão `false`).

| Extensão | `doc_kind` | Parser | Chunking |
|----------|-----------|--------|----------|
| `.md`, `.markdown` | doc | `markdown-it-py` | por heading |
| `.txt`, `.rst` | doc | texto | por parágrafo/janela |
| `.py` | code | `ast` (stdlib) | classe → método, função |
| `.php` | code | tree-sitter | classe → método, função |
| `.js`, `.jsx`, `.ts`, `.tsx` | code | tree-sitter | classe/função/export |
| `.json` | config/data | `json` + JSONPath | por chave de topo |
| `.yaml`, `.yml` | config | `ruamel.yaml` | por documento/chave de topo |
| `.xml` | data | `lxml` | por elemento de topo |
| `.sql` | code | `sqlparse` | por statement / `CREATE TABLE` |

Não suportar 50 formatos é decisão explícita. Adicionar linguagem é um ticket
próprio, com fixture própria.

## Parsers

Interface única:

```python
class Parser(Protocol):
    name: str
    extensions: tuple[str, ...]
    def parse(self, doc: ParsedInput) -> ParseResult: ...

@dataclass
class ParseNode:
    kind: str            # class | function | method | section | statement | block
    symbol: str | None   # "AuthService.login"
    start_line: int
    end_line: int
    children: list[ParseNode]
    meta: dict[str, Any] # decorators, docstring, imports, heading level...
```

O parser devolve **estrutura**, não chunks. Quem decide o fatiamento é o chunker —
separação que permite mudar a estratégia de chunking sem tocar em parser.

Falha de parsing nunca derruba a indexação: `ParseError` → degrada para
`FallbackChunker` e registra `parse_degraded` nas métricas do run.

## Chunking

### Código

```text
arquivo
 └── classe
      └── método
```

Regras:

- Cada função/método é um chunk, com assinatura + docstring + corpo.
- A classe gera um chunk "cabeçalho" (assinatura, docstring, atributos, lista de
  métodos), sem repetir o corpo dos métodos. `parent_id` liga método → classe.
- Imports e constantes de módulo formam um chunk `file` de preâmbulo — é onde mora
  a informação de dependência usada pelo grafo (Fase 3).
- Método maior que `chunk.max_tokens` (padrão **512**) é dividido por blocos lógicos
  (`if`/`for`/`try` de topo), com overlap de 1 linha de contexto e sufixo `#part-N`
  no `symbol`.
- Função menor que `chunk.min_tokens` (padrão **24**) é fundida com a vizinha do
  mesmo pai (getters/setters triviais viram um chunk só).

### Documentação

```text
documento
 └── heading
      └── conteúdo
```

Regras:

- Corte em `h1`–`h3`; `h4`+ ficam dentro do chunk do ancestral.
- `heading_path` preenchido (`"Arquitetura > Autenticação > SSO"`) — é usado tanto
  no FTS quanto como prefixo de contexto na Fase 4.
- Bloco de código dentro do Markdown **nunca** é partido ao meio.
- Tabela nunca é partida ao meio.
- Seção acima de `max_tokens` é dividida por parágrafo, repetindo o `heading_path`.

### Enriquecimento de contexto

Cada chunk é armazenado com o texto original, mas ganha um **prefixo de contexto**
no momento de gerar o embedding (não gravado em `chunks.content`):

```text
[src/auth/AuthService.php › class AuthService › método login]
<conteúdo do chunk>
```

Isso melhora recall sem poluir o texto devolvido ao agente.

## Indexação incremental

```text
para cada arquivo candidato:
    hash = sha256(conteúdo normalizado)
    se documents.content_hash == hash e chunker_version igual:
        → unchanged (nada a fazer)
    senão:
        → reprocessa: DELETE chunks do doc (cascade), INSERT novos
            → embeddings vêm do cache quando chunk.content_hash já é conhecido

documentos presentes no banco e ausentes no disco → removed (DELETE cascade)
```

Detecção rápida antes do hash: se `size_bytes` e `mtime_ns` batem com o registrado,
pula a leitura do conteúdo. `--full` desliga esse atalho.

Cache de embeddings: `.ragx/cache/emb/<model_id>/<content_hash>.f32`. Chunk que só
mudou de lugar (arquivo renomeado, função movida) reaproveita o vetor — é o que faz
a reindexação ficar barata.

**Veredito guardado** (`file_verdicts`, RAGX-0139). Arquivo `unsupported`, binário, indecodável ou
bloqueado nunca entra em `documents`, então o atalho de tamanho+mtime não o alcançava: era relido e
reexecutado no gate a cada rodada (800 `.csv`: 800 leituras por `index` sem mudança). Agora o
resultado é guardado com o tamanho e o `mtime` e, na rodada seguinte, o arquivo nem é aberto
(**800 leituras → 0**; `stats.blocked`, `blocked_paths` e `security_events` ficam iguais, com os mesmos
ids de linha). Vale para `index_project` e para `index_paths`. O cache é descartado inteiro quando muda
qualquer coisa de que o veredito depende (regras de segurança, `[security]`, `[index]`, versão do
chunker; ver [02-seguranca.md](02-seguranca.md)) e por `--full`; `--dry-run` usa o que existe e nunca
grava. Arquivo que muda de tamanho ou `mtime`, vira documento ou some tem o veredito reavaliado ou
apagado.

**Reindexação por caminho** (`index_paths`, `ragx index --only <caminho>`). Quando só se sabe
QUAIS arquivos mudaram (uma edição feita no meio de uma sessão), a varredura do projeto inteiro e
o git são trabalho jogado fora: `index_paths` reindexa só os arquivos pedidos, numa transação, e
grava uma run `mode='paths'` (branch e commit copiados da última run completa, `git_dirty = 1`,
sem chamar o git). Medido neste repositório, com 1 arquivo alterado e o processo quente:
**703 ms (`index_project`) → 107 ms**; num processo novo o custo dominante passa a ser a partida da
CLI. **O que dispensa:** a varredura, o git e a leitura dos hooks. **O que NÃO dispensa:** o
Security Gate (é o mesmo `_examinar` da varredura, antes de qualquer byte), a poda de pastas
(`can_prune` dos ancestrais), a guarda de links para fora da raiz (A8), a recusa de caminho
absoluto, com `..` ou do conhecimento base, a trava de indexação (ocupada: pedido pendente e
`IndexBusyError`) e a regra de arquivo ilegível. Cai no incremental completo quando há mais de
`watch.max_batch` caminhos ou um arquivo de regra (`.gitignore`, `.dockerignore`, `.ragignore`,
`ragx.toml`), que muda o que é visitado. Uma run `paths` não conta como "a última indexação" para
o veredito de frescor: ela só olhou o que lhe pediram.

**Fila de toque** (`ragx touch`, `indexing/touchq.py`, RAGX-0141). Quem alimenta `index_paths` com o
que o agente editou é o hook `PostToolUse`: `ragx touch` anexa o caminho (relativo, POSIX) a
`.ragx/touch.queue` num único `write` em `O_APPEND` e dispara uma drenagem destacada. `drain` espera o
debounce, toma a fila inteira de forma atômica (`os.replace`, a mesma técnica da trava: dois
consumidores nunca recebem o mesmo caminho), deduplica (sem diferenciar maiúsculas no Windows) e chama
`index_paths`. Índice ocupado ou falha: o lote volta à fila. A fila guarda só NOMES; o conteúdo só é
lido dentro de `index_paths`, depois do Security Gate, e um caminho que escapa da raiz (`..`, outra
raiz, symlink ou junction para fora) nem entra na fila.

**Chunk com o mesmo id sobrevive à edição.** O `chunk.id` é hash de (caminho, conteúdo
normalizado, versão do chunker), então "mesmo id" quer dizer "mesmo conteúdo".
`ChunkRepo.replace_for_document` compara os ids antigos com os novos: os que ficam não são
apagados nem reinseridos (continuam com `created_at`, vetor e as pontes do grafo
`entities.chunk_id` / `relations.evidence_chunk_id`), só entram os novos e só saem os
removidos. Quem muda só de posição (`ordinal`) ou de metadado leva um `UPDATE`; se mudou o
prefixo de contexto (`kind`, `symbol`, `heading_path`, que entra no texto embutido), o vetor
daquele chunk é descartado e ele volta para a fila do embedder. Antes, editar uma linha
apagava os vetores e as pontes de TODOS os chunks do arquivo (19 vetores viravam 0 e 19
pontes viravam 0, até o próximo `sync`).

**Arquivo ilegível não é arquivo removido.** Se o arquivo existe mas não abre agora
(antivírus ou editor segurando-o logo depois do save, `PermissionError`, violação de
compartilhamento no Windows), o walker o entrega como `unreadable` e a rodada o conta
em `skip_reasons["unreadable"]` e em `unreadable`, sem regravar nada: documento,
chunks e vetores ficam como estavam, e a rodada seguinte o reavalia. Só
`FileNotFoundError`/`NotADirectoryError` significam "sumiu". Uma pasta que não pôde
ser listada também protege o que estava sob ela. O **nome** continua sendo checado
sem abrir o arquivo: um `.env` travado que ficou indexado por engano sai do índice do
mesmo jeito. Efeito aceito: um arquivo que virou sensível e está travado permanece
no índice com o conteúdo antigo (que já tinha passado pelo Gate) até a primeira
rodada em que puder ser lido.

Indexação **sem mudança não carrega o modelo de embedding**: o nome e a dimensão do
modelo saem da configuração (`embedder_id`), os chunks sem vetor são contados primeiro
e o embedder só é construído (e o Ollama só é sondado) se houver pendência. Com
`fastembed` isso evita ~2,85 s; com Ollama fora do ar e nada pendente, não há erro.
O estado do git (`commit`, `branch`, `dirty`) vem de um único
`git status --porcelain=v2 --branch`, e a pasta de hooks é consultada uma vez por
processo.

## Transacionalidade

Um `index run` = uma transação por **lote de arquivos** (padrão 200), não uma
transação gigante. Interrupção (Ctrl+C) deixa o banco consistente com os lotes já
confirmados, e o run seguinte continua de onde parou. `index_runs.error` registra
a interrupção.

## Concorrência

```text
ThreadPool(N=cpu_count)  →  leitura + gate + parse + chunk   (I/O e CPU leve)
        │
        ▼ fila
Thread única escritora   →  SQLite (evita "database is locked")
        │
        ▼ lote
Embedder.embed_batch()   →  batch de 32 chunks por chamada
```

GIL não é gargalo aqui porque o custo dominante é I/O de arquivo e chamada HTTP ao
embedder. Se o parsing com tree-sitter virar gargalo, a substituição é
`ProcessPoolExecutor` só na etapa de parse — por isso `Parser` não guarda estado.

## Observabilidade

```bash
ragx index .
```

```text
Indexando /projeto  (incremental)

  ██████████████████████████  1.263/1.263 arquivos

  Documents      120   (+8 novos, 3 modificados, 1 removido)
  Chunks       1.832   (+147)
  Embeddings   1.832   (+147, 1.685 do cache)
  Skipped         43   (32 ignore, 9 binário, 2 grandes demais)
  Blocked          7   → ragx security scan . para detalhes

  Tempo 11,4 s
```

Segunda execução sem mudanças:

```text
  Documents      120   (sem mudanças)
  Chunks       1.832
  Skipped         43
  Blocked          7
  Tempo 1,8 s
```

## Comandos de inspeção

```bash
ragx status                       # resumo do índice + último run
ragx documents                    # lista documentos indexados
ragx documents --lang python
ragx chunks --document src/auth/service.py
ragx chunk <chunk_id>             # conteúdo completo de um chunk
```

## Critério de aceite da Fase 1

1. `ragx index .` em um repositório real produz contagens coerentes e não inclui
   nenhum arquivo bloqueado.
2. Segunda execução consecutiva **não** recria documentos nem chunks
   (`+0 novos`, `+0 chunks`), e roda em fração do tempo da primeira.
3. IDs de chunk são idênticos entre Windows e Linux para a mesma fixture
   (teste roda nos dois em CI).
4. Interromper a indexação e reexecutar converge para o mesmo estado final que uma
   execução ininterrupta.
5. Todos os testes de segurança da Fase 0 continuam verdes, e o `xfail` de
   "0 chunks com segredo" vira `pass`.
