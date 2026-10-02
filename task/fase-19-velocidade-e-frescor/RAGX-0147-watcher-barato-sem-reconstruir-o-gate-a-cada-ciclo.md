# RAGX-0147 — Watcher barato: sem reconstruir o gate a cada ciclo

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,75d |
| **Depende de** | RAGX-0129, RAGX-0140 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-11, M-01) · [25-spec-v2.md](../../docs/25-spec-v2.md) · [19-watch-e-autonomia-do-agente.md](../../docs/19-watch-e-autonomia-do-agente.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `done` |

## Objetivo

A cada 2 s o watcher chama `snapshot()`, que reconstrói o `SecurityGate` e o `IgnoreEngine` (e este caminha a árvore atrás de `.gitignore`), e depois, quando algo muda, `index_project` caminha tudo de novo (I-11). Medido: ciclo ocioso de **170–240 ms** em 643 arquivos e **330–540 ms** em 2.000; só o gate custa 28–41 ms; `git status` 74–112 ms. Ficam ~10–25% de um núcleo parado, e a ~20 mil arquivos o ciclo estoura o intervalo de 2 s. A poda corrigida (RAGX-0129) leva a varredura de 5,3–8,6 s para 0,14–0,26 s; esta tarefa tira do ciclo o que não precisa se repetir.

## Entregáveis

- [x] **Medir primeiro**: `cProfile` de um ciclo ocioso com 643 e com 2.000 arquivos (já com a 0129), separando construção do gate, `_walk` (`scandir` + `is_*`), `path.stat()` por arquivo e `should_ignore` por arquivo (`pathspec` contra cada fonte). O perfil decide quais dos três cortes abaixo valem a pena; registrar em Medição e em Andamento
- [x] Gate único por sessão: `src/ragx/watch/monitor.py:68-80` (`_gate`) e `:79-80` (`snapshot`) passam a aceitar um gate pronto (`snapshot(cfg, gate=None)`, compatível com os testes atuais), e `watch()` (`:124-172`) o constrói **uma vez** e o reconstrói só quando o delta traz `.gitignore`, `.dockerignore` ou `.ragignore` (criado, alterado ou removido)
- [x] `src/ragx/walk.py:118-140` (`scan_fingerprints`): aceitar o `IgnoreEngine` do chamador e guardar o veredito de `should_ignore` por caminho conhecido, válido enquanto o gate for o mesmo; caminho novo calcula
- [x] Stat sem segunda chamada: `_walk` (`walk.py:143-180`) entrega também o `stat` do `DirEntry` (no Windows, tamanho e mtime vêm da enumeração, sem syscall extra; os `stat()` de pasta, que precisam de `st_ino`, continuam por `os.stat`). Só adotar se o perfil mostrar o `path.stat()` como parcela relevante **e** a comparação com `os.stat` não divergir (ver Notas)
- [x] Aplicar por caminho: `apply_changes` (`monitor.py:83-121`) recebe os caminhos do lote e chama `index_paths` (RAGX-0140) em vez de `index_project` quando o lote é de arquivos comuns e cabe em `watch.max_batch`; lote com arquivo de ignore, `ragx.toml` ou acima do teto cai em `index_project` (a 0140 já faz essa queda sozinha). Acrescentar a `index_paths` um `gate: SecurityGate | None = None` opcional, para reaproveitar o gate em cache em vez de construir outro a cada lote. Hoje o lote vira `Delta(modified=...)` para tudo (`monitor.py:165`), inclusive criado e apagado: `index_paths` precisa remover o apagado
- [x] `WatchState` ganha `last_cycle_ms` e `idle_cycle_ms_p50`; `ragx watch --once --plain` e a saída `idle` os expõem (necessário para medir sem instrumentar de fora)
- [x] `docs/19-watch-e-autonomia-do-agente.md`: custo do ciclo ocioso, o que o gate em cache invalida, e a ressalva sobre `stat` de diretório no Windows

## Fora de escopo

- Frescor de edição sem o watcher (RAGX-0141) e `index_paths` em si (RAGX-0140)
- A poda de diretórios (RAGX-0129) e o `refresh` do MCP (RAGX-0131), que continua chamando `apply_changes` sem lote
- Recarregar `ragx.toml` com o watcher rodando: `cfg` é fixo desde o início da execução, hoje e depois
- Intervalo adaptativo ou mudar `watch.interval_s`: decisão de produto sobre frescor contra CPU; registrar a proposta em Andamento se o perfil a justificar
- API nativa do sistema (inotify/ReadDirectoryChanges): o doc 19 decidiu por polling, sem dependência nova

## Critérios de aceite

- [x] Ciclo ocioso **≥ 45% mais curto** que o medido, em 643 e em 2.000 arquivos (meta provisória: ≤ 100 ms e ≤ 200 ms; ajustar depois de "medir primeiro")
- [x] `SecurityGate` construído **1 vez** em 50 ciclos ociosos (contador no teste); editar `.gitignore` faz o ciclo seguinte refletir a regra nova
- [x] Salvar 1 arquivo: o watcher reindexa por `index_paths` (espiado no teste) e o texto novo aparece na busca; salvar um `.gitignore`: cai em `index_project`
- [x] Um arquivo novo com segredo, criado no ciclo 50 com o gate em cache, é **bloqueado** e não entra no índice
- [x] `uv run pytest tests/integration/test_watch.py tests/security` verdes

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Ciclo ocioso, 643 arquivos | 126 ms (nesta máquina; 170–240 ms na da tarefa) | **48 ms** (-62%) |
| Ciclo ocioso, 2.000 arquivos | 282 ms (330–540 ms na da tarefa) | **97–101 ms** (-64%) |
| Construção do gate | 51 em 50 ciclos | **1** em 50 ciclos |
| Uso de núcleo parado (intervalo de 2 s) | ~6% (126 ms / 2 s) | **~2,4%** (48 ms / 2 s) |

Comando: `uv run python scripts/medir_watch.py --arquivos 643 --ciclos 50` (criar: gera o projeto, roda `watch(max_cycles=50)` e imprime mediana e p95 de `last_cycle_ms`).

## Testes

- [x] `tests/integration/test_watch.py`: gate construído uma vez em 50 ciclos; alteração de `.gitignore`, `.dockerignore` e `.ragignore` reconstrói; `snapshot(cfg)` sem gate continua igual (os testes atuais passam sem mudança)
- [x] `tests/integration/test_watch.py`: lote de 1 arquivo vai por `index_paths`; lote com `.gitignore` ou acima de `max_batch` vai por `index_project`; arquivo apagado sai do índice
- [x] `tests/unit/test_walk.py` (novo, ou em `test_ignore_engine.py`): `scan_fingerprints` com e sem cache de veredito devolve o mesmo dicionário; `stat` do `DirEntry` igual a `os.stat` em arquivo comum
- [x] `tests/security/test_watch_gate.py` (novo): arquivo com segredo de `tests/fixtures/secrets_under_test.py` criado depois de muitos ciclos não entra no índice (nem em `chunks`, nem em `fts`) e gera `security_events`; `.env` novo idem; `walk.py` continua chamando `gate.admit` (o arquitetural já cobre, rodar)

## Notas

- Confirmado em `src/ragx/watch/monitor.py:68-80,96,124-172` (cada ciclo: `snapshot(cfg)` → `_gate(cfg)` → `SecurityGate(...)` → `IgnoreEngine._descobrir`), `src/ragx/security/ignore_engine.py:70-134` (varredura da árvore no `__init__`) e `src/ragx/walk.py:136` (`path.stat()` depois de o `DirEntry` já ter sido consultado, e jogado fora, em `_walk`).
- Caveat do Windows: no NTFS o tamanho e o mtime da entrada de diretório podem ficar defasados enquanto outro processo mantém o arquivo aberto para escrita. Se a comparação com `os.stat` divergir no teste de estresse (arquivo em `a+` aberto), **não** usar `DirEntry.stat()`; confirmar cada candidato a mudança com `os.stat` ou manter só os outros dois cortes.
- A invalidação do gate por arquivo de ignore preserva o comportamento de hoje (que relê tudo a cada ciclo). Não invalidar nada além disso: o objetivo é custo, e o veredito de segurança continua sendo o `gate.admit` na hora de ler.
- O `git status` de 74–112 ms não está no ciclo ocioso (vem de `index_project` → `gitinfo.read_state`, RAGX-0130); `index_paths` não o chama.
- Se o perfil mostrar que o custo é quase todo `scandir` do sistema (o piso do polling), registrar o piso medido, manter o ganho do gate e do veredito em cache e propor, em outra tarefa, o intervalo adaptativo.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0147)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_

## Andamento

- 2026-10-01 — `scripts/medir_watch.py` (cronometra cada ciclo ocioso de fora, conta construções do gate, `--perfil`). Perfil de 2.000 arquivos: `stat` 37% do ciclo (5 syscalls por arquivo, das quais só 1 era necessária), `should_ignore` 26%, o resto `iterdir`/gate. Cortes aplicados: (1) gate único + refeito só com arquivo de ignore; (2) cache de veredito em `scan_fingerprints`; (3) `_walk` com `os.scandir` (tipo da entrada sem syscall); (4) lote por `index_paths` com `gate` reaproveitável; (5) `last_cycle_ms`/`idle_cycle_ms_p50` no `WatchState` e no `--once --plain`.
- **Não adotado, de propósito:** `DirEntry.stat()` para tamanho e mtime dos arquivos (a ressalva do NTFS da tarefa); sobrou 1 `stat` por arquivo, que é o piso do polling. A ordem de visita é a de `sorted(Path)` de antes.
- Medido: 643 arquivos 126→48 ms; 2.000 arquivos 282→97 ms; gate 51→1. A meta provisória (≤ 100 ms e ≤ 200 ms) vale nos dois. Propostas fora de escopo: intervalo adaptativo (não preciso: 2,4% de um núcleo parado).
- Testes: `test_watch.py` (+9: gate 1 vez em 50 ciclos, os 3 arquivos de ignore reconstroem e a regra vale, `snapshot` sem gate igual, lote por `index_paths` com o texto novo na busca, `.gitignore` cai em `index_project`, apagado sai do índice, métricas), `tests/security/test_watch_gate.py` (segredo e `.env` criados no ciclo 50 não entram em `documents`, `chunks` nem `chunks_fts`, e geram `security_events`), `tests/unit/test_walk.py` (4). Suíte Python inteira, `ruff` e `mypy` verdes.
- Achado: o lote que troca `.gitignore` constrói um 3º gate, o do `index_project` para o qual ele cai (não é o do laço).
