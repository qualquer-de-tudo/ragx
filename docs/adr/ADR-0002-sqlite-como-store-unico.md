# ADR-0002 — SQLite como store único

**Status:** aceito · 2026-09-15

## Contexto

O RAGX precisa guardar documentos, chunks, índice de texto, vetores e um grafo.
A tentação natural é usar uma ferramenta especializada para cada um: Chroma/Qdrant
para vetores, Neo4j para grafo, Elasticsearch para texto. Cada uma delas é um
serviço a instalar, subir, versionar e manter — em um produto cujo requisito
central é **local-first, um projeto = um diretório**.

## Decisão

Um único arquivo SQLite (`.ragx/knowledge.db`) guarda tudo:

| Necessidade | Solução no SQLite |
|-------------|-------------------|
| Documentos e chunks | tabelas relacionais |
| Busca por palavra-chave | FTS5 com BM25 (built-in) |
| Vetores | `BLOB` float32 + busca em NumPy (ver [ADR-0003](ADR-0003-busca-vetorial.md)) |
| Grafo | `entities` + `relations`, travessia por CTE recursiva ou BFS em Python |
| Metadados de run e segurança | tabelas relacionais |

Modo WAL, para que a CLI escreva enquanto o servidor MCP lê.

## Consequências

Positivas:
- Zero infraestrutura. `ragx init` e está pronto.
- Transacionalidade real entre chunk, embedding e entidade — um `INSERT` de chunk
  com falha no embedding não deixa estado inconsistente.
- Backup, cópia e descarte são operações de arquivo.
- `ON DELETE CASCADE` resolve a limpeza que, em três bancos separados, viraria uma
  rotina de reconciliação.
- Um arquivo apagável: `ragx reset` é `rm -rf .ragx/`.

Negativas:
- Busca vetorial não escala indefinidamente — tratado no ADR-0003, com limiar
  explícito e caminho de upgrade.
- Travessia de grafo profunda é mais lenta que em banco de grafo nativo.
  Mitigação: `max_depth = 2` e `max_nodes = 200`, limites que o caso de uso real
  (contexto para agente) não precisa ultrapassar.
- Um único escritor. Mitigação: thread escritora dedicada na indexação; MCP abre
  em modo somente leitura.

## Alternativas rejeitadas

- **Chroma / Qdrant / LanceDB** — melhores em busca vetorial, mas adicionam
  dependência pesada e um segundo lugar onde o dado pode divergir. LanceDB é a
  alternativa mais próxima (também embarcada) e fica registrada como opção caso o
  limiar do ADR-0003 seja ultrapassado com frequência.
- **Neo4j / Kùzu** — grafo nativo é atraente, mas o grafo aqui é pequeno (milhares
  de nós) e sempre consultado a partir de sementes vindas da busca vetorial.
- **DuckDB** — excelente analiticamente, mas FTS e concorrência de escrita são mais
  fracos para este padrão de uso, e o ganho analítico não é necessário.
- **Arquivos JSON no disco** (como o `.index/` do indexador anterior) — simples de
  ler, mas sem transação, sem índice e com custo de I/O proporcional ao repositório
  em toda consulta.
