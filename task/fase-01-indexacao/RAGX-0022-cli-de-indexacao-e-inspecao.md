# RAGX-0022 — CLI de indexação e inspeção

| | |
|---|---|
| **Fase** | 1 — Indexer + Knowledge Store |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | `RAGX-0021` |
| **Bloqueia** | — |
| **Documentação** | [14-cli.md](../../docs/14-cli.md) |
| **Status** | `todo` |

## Objetivo

Expor a indexação e dar ao dev meios de inspecionar o que foi indexado.

## Entregáveis

- [ ] `ragx index [PATH]` com `--full`, `--dry-run`, `--include`, `--exclude`, `--jobs`
- [ ] `ragx status [--json]`
- [ ] `ragx documents` com filtros `--lang`, `--kind`, `--path`, `--limit`
- [ ] `ragx chunks --document PATH` e `ragx chunk <id> [--with-context]`

## Fora de escopo

- `--embed-only` (chega em RAGX-0025)

## Critérios de aceite

- [ ] Saída de `ragx index` reproduz o formato do doc 04
- [ ] `--dry-run` não escreve nada no banco
- [ ] `--json` de todos os comandos é estável e parseável
- [ ] `ragx chunk --with-context` traz o chunk pai e os vizinhos

## Testes

- [ ] E2E da sequência `init → index → status → documents → chunks`

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados
- [ ] Testes escritos e verdes em Linux e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] Documentação da fase confere com o comportamento implementado
