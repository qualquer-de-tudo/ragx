# RAGX-0114 — Chunking AST para TypeScript, JavaScript e PHP

| | |
|---|---|
| **Fase** | 14 — Evolução do RAG |
| **Onda** | transversal — dívida de ingestão |
| **Prioridade** | P1 — alta |
| **Estimativa** | 3d |
| **Depende de** | — |
| **Documentação** | [23-auditoria-e-evolucao-do-rag.md](../../docs/23-auditoria-e-evolucao-do-rag.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [adr/ADR-0005-parsing-e-chunking.md](../../docs/adr/ADR-0005-parsing-e-chunking.md) |
| **Status** | `todo` |

## Objetivo

`EXT_LANG` mapeia `.php`, `.js`, `.ts`, `.tsx` como `DocKind.CODE`, mas `_BY_LANG` não tem parser para nenhum deles — todos caem no `TextParser`, que divide por **linha em branco**. `tree-sitter-language-pack` está declarado no extra `[parse]` do `pyproject.toml` e **nunca é importado**.

## Entregáveis

- [ ] Parser baseado em `tree-sitter-language-pack` para TypeScript, JavaScript, TSX/JSX e PHP
- [ ] Mesma interface dos parsers atuais: extrai ESTRUTURA, não chunks (ADR-0005)
- [ ] `symbol`, `heading_path` e `parent_id` preenchidos — o BM25 pesa `symbol` em 4,0 e hoje ele vem vazio nessas linguagens
- [ ] Degradação para `TextParser` quando o parsing falha, como já acontece
- [ ] Fixture por linguagem, com arquivo real

## Fora de escopo

- Outras linguagens (Go, Rust, Java) — cada uma é ticket próprio com fixture própria, como manda o ADR-0005
- Extração de grafo para essas linguagens (tarefa separada)

## Critérios de aceite

- [ ] Um arquivo `.ts` com 5 funções produz 5 chunks com `symbol` preenchido, não N blocos por linha em branco
- [ ] Um `.php` com classe e métodos preserva a hierarquia em `parent_id`
- [ ] IDs determinísticos entre Linux, macOS e Windows
- [ ] `tree-sitter-language-pack` deixa de ser dependência paga e não usada

## Testes

- [ ] Fixture por linguagem, fixando os chunks esperados
- [ ] Teste de determinismo de ID entre plataformas
- [ ] Teste de degradação com arquivo sintaticamente inválido

## Notas

O efeito é invisível NESTE repositório (129 arquivos Python, 164 Markdown) e grande em qualquer projeto TypeScript ou PHP — que são os exemplos que o próprio README usa (`AuthService.php`).

Vale medir com um conjunto de avaliação sobre um repositório TypeScript real, não sobre o RAGX.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração
- [ ] Documentação confere com o comportamento implementado
