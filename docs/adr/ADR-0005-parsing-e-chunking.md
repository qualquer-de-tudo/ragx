# ADR-0005 — Chunking estrutural com AST e tree-sitter

**Status:** aceito · 2026-09-15

## Contexto

A abordagem padrão de RAG — janela deslizante de N caracteres com overlap — funciona
razoavelmente para prosa e mal para código. Ela corta função no meio, separa
assinatura do corpo, mistura o fim de uma classe com o início de outra e produz
chunks que não significam nada sozinhos.

Para um agente que vai *usar* o resultado, um chunk truncado é pior que nenhum:
ele parece completo e não é.

## Decisão

Chunking guiado por **estrutura sintática**, com separação explícita entre parser
(extrai estrutura) e chunker (decide fatiamento).

| Linguagem | Parser | Motivo |
|-----------|--------|--------|
| Python | `ast` (stdlib) | AST correto, zero dependência |
| PHP, JS, TS, TSX | `tree-sitter-language-pack` | gramáticas mantidas, tolera código quebrado |
| Markdown | `markdown-it-py` | árvore de headings confiável |
| JSON / YAML / XML / SQL | `json`, `ruamel.yaml`, `lxml`, `sqlparse` | estrutura nativa |
| desconhecido | `FallbackChunker` | janela por parágrafo, com aviso |

Regras de fatiamento em [04 — Indexação](../04-indexacao.md). As invariantes:

1. Um chunk de código é uma unidade compilável ou quase — função, método ou classe
   completa (a classe, sem repetir o corpo dos métodos).
2. Bloco de código e tabela dentro de Markdown **nunca** são partidos.
3. `parent_id` preserva a hierarquia (método → classe → arquivo), permitindo
   expansão de contexto sem nova busca.
4. Unidade acima de `max_tokens` é dividida por blocos lógicos, não por caractere.
5. Falha de parsing degrada para o fallback e é registrada — nunca derruba a indexação.
6. `CHUNKER_VERSION` entra no ID; mudar o fatiamento invalida os IDs de propósito.

Tree-sitter é tolerante a erro sintático por construção, o que importa: código em
desenvolvimento frequentemente não compila, e ainda assim precisa ser indexável.

## Consequências

Positivas:
- Chunk de código é autocontido e citável (`arquivo:linha-linha › símbolo`).
- `symbol` alimenta o boost de BM25 na busca keyword (peso 4.0).
- A estrutura já extraída é reaproveitada de graça pelo grafo (Fase 3, camada 1).
- `heading_path` dá contexto de navegação em documentação.

Negativas:
- Uma gramática por linguagem. Mitigação: lista fechada no MVP; adicionar linguagem
  é ticket próprio com fixture própria.
- `tree-sitter-language-pack` traz binários nativos (~50 MB). Aceitável; alternativa
  seria regex, que é pior em todos os aspectos.
- Chunks têm tamanho variável, o que dificulta estimar custo de contexto —
  compensado pelo `token_count` gravado por chunk.

## Alternativas rejeitadas

- **Janela fixa com overlap** — simples, e produz exatamente o problema descrito
  no contexto.
- **Chunking semântico por embedding** (cortar onde a similaridade cai) — caro
  (exige embedar antes de fatiar) e não determinístico, o que quebraria o requisito
  de ID estável.
- **LSP para extrair símbolos** — precisão maior, mas exige um language server por
  linguagem, rodando, com o projeto configurado. Inviável para indexação em lote.
- **Regex por linguagem** — frágil; quebra em decorator, generic, closure aninhada,
  heredoc, e em qualquer código que não pareça o exemplo do tutorial.
