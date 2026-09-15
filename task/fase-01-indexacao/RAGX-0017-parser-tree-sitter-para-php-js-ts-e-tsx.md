# RAGX-0017 — Parser tree-sitter para PHP, JS, TS e TSX

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0016` |
| **Bloqueia** | `RAGX-0019` |
| **Documentação** | [04-indexacao.md](../../docs/04-indexacao.md) · [adr/ADR-0005-parsing-e-chunking.md](../../docs/adr/ADR-0005-parsing-e-chunking.md) |
| **Status** | `todo` |

## Objetivo

Cobrir as linguagens de código não-Python do MVP com AST real.

## Entregáveis

- [ ] `indexing/parsers/treesitter.py` genérico, configurado por queries por linguagem
- [ ] Queries de captura para classe, método, função, export, interface e trait
- [ ] Gramáticas via `tree-sitter-language-pack` (php, javascript, typescript, tsx)
- [ ] Mesma interface `Parser` dos demais — nenhuma ramificação especial no pipeline

## Fora de escopo

- Outras linguagens — cada uma é ticket próprio com fixture própria

## Critérios de aceite

- [ ] Classe PHP com trait e métodos é extraída corretamente
- [ ] Arrow function e componente React são reconhecidos em TS/TSX
- [ ] Arquivo sintaticamente quebrado ainda produz estrutura parcial (tolerância do tree-sitter)
- [ ] Parser não guarda estado entre arquivos (pré-requisito para paralelizar por processo)

## Testes

- [ ] Fixture por linguagem com os construtos comuns do ecossistema

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
