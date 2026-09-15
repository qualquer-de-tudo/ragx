# RAGX-0015 — Parser de Markdown e texto

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0012` |
| **Bloqueia** | `RAGX-0020` |
| **Documentação** | [04-indexacao.md](../../docs/04-indexacao.md) · [adr/ADR-0005-parsing-e-chunking.md](../../docs/adr/ADR-0005-parsing-e-chunking.md) |
| **Status** | `todo` |

## Objetivo

Extrair a árvore de headings de documentação, que é a espinha dorsal do `heading_path`.

## Entregáveis

- [ ] `indexing/parsers/markdown.py` com `markdown-it-py`
- [ ] Árvore h1–h6 com linha inicial e final por seção
- [ ] Preservação de blocos de código (com a linguagem) e de tabelas como nós indivisíveis
- [ ] Parser de `.txt`/`.rst` por parágrafo

## Fora de escopo

- Fatiamento (RAGX-0020)

## Critérios de aceite

- [ ] `heading_path` correto em documento com hierarquia de 4 níveis
- [ ] Bloco de código com `#` dentro não é confundido com heading
- [ ] Front-matter YAML é reconhecido como metadado, não como conteúdo
- [ ] Markdown malformado não lança exceção

## Testes

- [ ] Fixtures de Markdown real, incluindo os próprios docs deste repositório

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
