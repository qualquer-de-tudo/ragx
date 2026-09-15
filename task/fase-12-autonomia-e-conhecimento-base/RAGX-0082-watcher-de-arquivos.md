# RAGX-0082 — Watcher: o índice acompanhando o working tree

| | |
|---|---|
| **Fase** | 12 — Autonomia + Conhecimento base |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | `RAGX-0012` |
| **Bloqueia** | `RAGX-0083` |
| **Documentação** | [19-watch-e-autonomia-do-agente.md](../../docs/19-watch-e-autonomia-do-agente.md) |
| **Status** | `done` |

## Objetivo

Eliminar a classe de falha mais perigosa do sistema: o índice desatualizado que
não dá erro, e faz o agente responder com confiança sobre código que não existe
mais.

## Entregáveis

- [x] `ragx.walk.scan_fingerprints` — enumera `{caminho: (size, mtime_ns)}` sem abrir arquivo
- [x] `ragx.watch.monitor` — `diff`, `snapshot`, `apply_changes`, `watch`
- [x] Debounce: rajada de salvamentos vira UMA reindexação
- [x] Duas velocidades — reindexa a cada mudança, consolida a cada N
- [x] `ragx watch` com painel ao vivo, `--plain` e `--once`
- [x] `[watch]` em `Config`; flags sobrepõem

## Fora de escopo

- API nativa do sistema operacional (`inotify`, `ReadDirectoryChangesW`)
- Watcher como serviço/daemon do sistema
- Observar as fontes de conhecimento base (mudam por `ragx base update`)

## Decisão registrada

Polling por `size+mtime`, não API nativa. Três motivos:

1. Zero dependência nova — `watchdog` traria árvore de pacotes e um backend por plataforma
2. É o MESMO sinal que o indexador incremental usa; watcher e indexador nunca discordam
3. Editor que salva via temporário + rename gera eventos confusos em API nativa; `stat` mostra só o resultado final

O watcher **não** é um terceiro leitor de filesystem: `scan_fingerprints` vive
em `ragx.walk`, e o watcher recebe nomes e números, nunca bytes.

## Critérios de aceite

- [x] Arquivo criado entra no índice sem intervenção
- [x] Arquivo removido sai do índice
- [x] Segredo novo é BLOQUEADO — o watcher não é atalho para dentro do gate
- [x] `.ragx/` fora do snapshot (senão o watcher se auto-dispara para sempre)
- [x] Duas mudanças em ciclos seguidos produzem UMA reindexação
- [x] Falha de indexação vira `last_error` e o laço continua

## Testes

- [x] `tests/integration/test_watch.py` — 7 testes
- [x] `watch()` aceita `sleep` injetável e `max_cycles`: laço testável sem tempo real

## Notas

"Watcher morto é pior que watcher ausente" é a regra que governa o tratamento
de erro: o agente segue consultando um índice parado sem ninguém perceber.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados
- [x] Testes escritos e verdes
- [x] `ruff` limpo
- [x] Suíte `security/` continua verde
- [x] Documentação da fase confere com o comportamento implementado
