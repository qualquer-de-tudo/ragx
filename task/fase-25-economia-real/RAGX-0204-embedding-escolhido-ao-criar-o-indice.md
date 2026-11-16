# RAGX-0204 — Embedding escolhido ao criar o índice

| | |
|---|---|
| **Fase** | 25 — Economia real |
| **Prioridade** | P2 |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [15-configuracao.md](../../docs/15-configuracao.md) · [ADR-0004](../../docs/adr/ADR-0004-embeddings.md) |
| **Status** | `review` |

## Objetivo

O provider padrão é o Ollama. Quem baixa sem Ollama, ou o fecha, fica com a busca só por palavra-chave sem perceber
(no Juriflux, 760 arquivos sem vetor num dia). O `ragx init` passa a escolher: Ollama com o modelo padrão quando o
daemon responde e o modelo existe; senão, `fastembed` (que já vem no `[all]`). A escolha é gravada no `ragx.toml` e
não muda sozinha depois (vetores de modelos diferentes não se misturam).

## Entregáveis

- [x] `ragx init` sem provider no `ragx.toml` grava o escolhido e diz por quê numa linha
- [x] `--embedding ollama|fastembed` força a escolha
- [x] Projeto que já tem `ragx.toml` não muda

## Fora de escopo

- Migrar índices existentes de um provider para outro

## Critérios de aceite

- [x] Testes com o Ollama no ar (modelo presente e ausente) e fora do ar
