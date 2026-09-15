# RAGX-0083 — Escrita no índice via MCP + playbook

| | |
|---|---|
| **Fase** | 12 — Autonomia + Conhecimento base |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0082`, `RAGX-0044` |
| **Bloqueia** | — |
| **Documentação** | [19-watch-e-autonomia-do-agente.md](../../docs/19-watch-e-autonomia-do-agente.md) · [ADR-0012](../../docs/adr/ADR-0012-poder-do-agente-sobre-o-indice.md) |
| **Status** | `done` |

## Objetivo

Dar ao agente controle sobre o índice — sem dar controle sobre o filesystem e
sem afrouxar o Security Gate.

## Entregáveis

- [x] `ragx.mcp.operations.WriteAPI` — `refresh`, `reindex`, `sync`, `rebuild_graph`, `generate_dictionary`, `base_sync`, `publish_contract`
- [x] Lock exclusivo + `write_timeout_s`: reindexação concorrente espera, não duplica
- [x] `list_base_sources` (leitura)
- [x] `ragx.mcp.playbook` — `get_playbook` e as instruções do servidor
- [x] `ragx mcp serve --write/--read-only`, padrão `--write`
- [x] `[mcp] allow_write`, `write_timeout_s` em `Config`
- [x] Ferramentas de escrita listadas MESMO em modo leitura, respondendo `write_disabled`
- [x] ADR-0012

## Fora de escopo

- `run_command` genérico — seria poder sobre a máquina, não sobre o RAG
- Escrita em arquivo do projeto pelo MCP
- Afrouxar qualquer regra do gate

## Critérios de aceite

- [x] `reindex` via MCP atualiza o índice de verdade
- [x] Modo leitura responde `write_disabled` com a instrução de como habilitar
- [x] `reindex` devolve a CONTAGEM de bloqueados, nunca os caminhos
- [x] `get_playbook` ensina ordem das ferramentas e os limites
- [x] Playbook sem escrita não instrui a reindexar

## Invariantes que NÃO podem quebrar

- [x] `ragx.mcp` não importa `os`, `subprocess`, `pathlib`, `shutil`, rede
- [x] `ragx.mcp` não chama `open`, `exec`, `eval`
- [x] `ragx.mcp` só abre o banco com `read_only=True`
- [x] Segredo continua inacessível por qualquer ferramenta

## Testes

- [x] `tests/integration/test_mcp.py` — 4 testes novos
- [x] `tests/security/test_architecture.py` — as três invariantes acima, inalteradas

## Notas

Durante a implementação, `operations.py` chegou a ler `knowledge/base.json`
direto. O teste arquitetural barrou — `read_text` em `ragx.mcp` — e a leitura
foi para `ragx.base.declared_for`. O teste **não** foi relaxado. É a segunda
vez que ele pega uma violação real (a primeira foi o log de erro, que virou
`ragx.diagnostics`).

O playbook vive em Python, não num `.md`: um playbook lido do disco abriria
exatamente o buraco que o resto do módulo fecha.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados
- [x] Testes escritos e verdes
- [x] `ruff` limpo
- [x] Suíte `security/` continua verde
- [x] ADR registrado
