# RAGX-0057 — Importer: compatibilidade, zip-slip e merge

| | |
|---|---|
| **Fase** | 8 — Export / Import (.rag) |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0056` |
| **Bloqueia** | `RAGX-0058` |
| **Documentação** | [11-export-import.md](../../docs/11-export-import.md) |
| **Status** | `todo` |

## Objetivo

Importar com desconfiança: pacote de terceiro é entrada não confiável.

## Entregáveis

- [ ] Verificação de `CHECKSUMS.sha256` e validação do manifest antes de qualquer escrita
- [ ] Matriz de compatibilidade do doc 11 (schema, chunker, modelo e dimensão de embedding, ruleset)
- [ ] Security scan do conteúdo importado
- [ ] Proteção contra zip-slip (entrada com `..` ou caminho absoluto é rejeitada)
- [ ] Modos `--replace` (padrão) e `--merge` com as regras de conflito do doc 11
- [ ] Aplicação em transação única

## Fora de escopo

- Merge automático de perfis de agente

## Critérios de aceite

- [ ] Export → import em máquina limpa reproduz busca e grafo equivalentes, sem reindexar
- [ ] Zip-slip e checksum corrompido são rejeitados
- [ ] Modelo de embedding diferente degrada para keyword com aviso, sem quebrar
- [ ] Import nunca escreve fora de `.ragx/` e `knowledge/`

## Testes

- [ ] Pacote malicioso com `../../etc/passwd`
- [ ] Pacote com checksum alterado
- [ ] Matriz de compatibilidade completa

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
