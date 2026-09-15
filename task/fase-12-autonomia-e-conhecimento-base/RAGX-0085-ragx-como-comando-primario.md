# RAGX-0085 — `ragx` como comando primário

| | |
|---|---|
| **Fase** | 12 — Autonomia + Conhecimento base |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Bloqueia** | — |
| **Documentação** | [ADR-0007](../../docs/adr/ADR-0007-nome-do-binario.md) · [14-cli.md](../../docs/14-cli.md) |
| **Status** | `done` |

## Objetivo

Um nome só. Pacote `ragx`, diretório `ragx`, servidor MCP `ragx`, configuração
`ragx.toml` — e o comando era `rag`. A inconsistência aparecia em toda página
de documentação.

## Entregáveis

- [x] `pyproject.toml`: `ragx` primeiro, `rag` como alias comentado
- [x] `typer.Typer(name="ragx")`
- [x] 417 ocorrências em 68 arquivos de `docs/` e `task/`
- [x] 85 ocorrências em 34 módulos — mensagens ao usuário e docstrings
- [x] ADR-0007 revisado, com a decisão anterior preservada e o motivo da inversão

## Fora de escopo

- Remover o alias `rag`. Quebraria script, alias de shell e configuração de MCP
  já existentes, por ganho nenhum.

## Critérios de aceite

- [x] `ragx --help` funciona e se anuncia como `ragx`
- [x] `rag --help` continua funcionando
- [x] Nenhuma ocorrência de `rag <subcomando>` sobrou em `docs/`, `task/` ou `src/`
- [x] Prosa em português onde "rag" é substantivo ficou intocada
  (`o rag exportado`, `rag compartilhado`)
- [x] Suíte verde após a substituição em massa

## Notas

A substituição foi feita com lista fechada de subcomandos, não com
`s/rag /ragx /g`. A diferença importa: a busca ingênua teria corrompido quatro
frases em português e a citação histórica dentro do próprio ADR-0007 — que
precisa continuar dizendo `rag init` para descrever o plano original.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados
- [x] `ruff` limpo
- [x] Suíte verde
- [x] ADR revisado, não reescrito
