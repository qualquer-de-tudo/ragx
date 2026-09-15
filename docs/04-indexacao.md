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
- **Recusa symlinks que apontam para fora da raiz** (ameaça A8). Symlink interno é
  seguido uma vez; ciclos detectados por `inode`/`st_ino` visitado.
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
