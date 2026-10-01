# RAGX-0147 — Watcher barato: sem reconstruir o gate a cada ciclo

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,75d |
| **Depende de** | RAGX-0129, RAGX-0140 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-11, M-01) · [25-spec-v2.md](../../docs/25-spec-v2.md) · [19-watch-e-autonomia-do-agente.md](../../docs/19-watch-e-autonomia-do-agente.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `todo` |

## Objetivo

A cada 2 s o watcher chama `snapshot()`, que reconstrói o `SecurityGate` e o `IgnoreEngine` (e este caminha a árvore atrás de `.gitignore`), e depois, quando algo muda, `index_project` caminha tudo de novo (I-11). Medido: ciclo ocioso de **170–240 ms** em 643 arquivos e **330–540 ms** em 2.000; só o gate custa 28–41 ms; `git status` 74–112 ms. Ficam ~10–25% de um núcleo parado, e a ~20 mil arquivos o ciclo estoura o intervalo de 2 s. A poda corrigida (RAGX-0129) leva a varredura de 5,3–8,6 s para 0,14–0,26 s; esta tarefa tira do ciclo o que não precisa se repetir.

## Entregáveis

- [ ] **Medir primeiro**: `cProfile` de um ciclo ocioso com 643 e com 2.000 arquivos (já com a 0129), separando construção do gate, `_walk` (`scandir` + `is_*`), `path.stat()` por arquivo e `should_ignore` por arquivo (`pathspec` contra cada fonte). O perfil decide quais dos três cortes abaixo valem a pena; registrar em Medição e em Andamento
- [ ] Gate único por sessão: `src/ragx/watch/monitor.py:68-80` (`_gate`) e `:79-80` (`snapshot`) passam a aceitar um gate pronto (`snapshot(cfg, gate=None)`, compatível com os testes atuais), e `watch()` (`:124-172`) o constrói **uma vez** e o reconstrói só quando o delta traz `.gitignore`, `.dockerignore` ou `.ragignore` (criado, alterado ou removido)
- [ ] `src/ragx/walk.py:118-140` (`scan_fingerprints`): aceitar o `IgnoreEngine` do chamador e guardar o veredito de `should_ignore` por caminho conhecido, válido enquanto o gate for o mesmo; caminho novo calcula
- [ ] Stat sem segunda chamada: `_walk` (`walk.py:143-180`) entrega também o `stat` do `DirEntry` (no Windows, tamanho e mtime vêm da enumeração, sem syscall extra; os `stat()` de pasta, que precisam de `st_ino`, continuam por `os.stat`). Só adotar se o perfil mostrar o `path.stat()` como parcela relevante **e** a comparação com `os.stat` não divergir (ver Notas)
- [ ] Aplicar por caminho: `apply_changes` (`monitor.py:83-121`) recebe os caminhos do lote e chama `index_paths` (RAGX-0140) em vez de `index_project` quando o lote é de arquivos comuns e cabe em `watch.max_batch`; lote com arquivo de ignore, `ragx.toml` ou acima do teto cai em `index_project`. Hoje o lote vira `Delta(modified=...)` para tudo (`monitor.py:165`), inclusive criado e apagado: `index_paths` precisa remover o apagado
- [ ] `WatchState` ganha `last_cycle_ms` e `idle_cycle_ms_p50`; `ragx watch --once --plain` e a saída `idle` os expõem (necessário para medir sem instrumentar de fora)
- [ ] `docs/19-watch-e-autonomia-do-agente.md`: custo do ciclo ocioso, o que o gate em cache invalida, e a ressalva sobre `stat` de diretório no Windows

## Fora de escopo

- Frescor de edição sem o watcher (RAGX-0141) e `index_paths` em si (RAGX-0140)
- A poda de diretórios (RAGX-0129) e o `refresh` do MCP (RAGX-0131), que continua chamando `apply_changes` sem lote
- Recarregar `ragx.toml` com o watcher rodando: `cfg` é fixo desde o início da execução, hoje e depois
- Intervalo adaptativo ou mudar `watch.interval_s`: decisão de produto sobre frescor contra CPU; registrar a proposta em Andamento se o perfil a justificar
- API nativa do sistema (inotify/ReadDirectoryChanges): o doc 19 decidiu por polling, sem dependência nova

## Critérios de aceite

- [ ] Ciclo ocioso **≥ 45% mais curto** que o medido, em 643 e em 2.000 arquivos (meta provisória: ≤ 100 ms e ≤ 200 ms; ajustar depois de "medir primeiro")
- [ ] `SecurityGate` construído **1 vez** em 50 ciclos ociosos (contador no teste); editar `.gitignore` faz o ciclo seguinte refletir a regra nova
- [ ] Salvar 1 arquivo: o watcher reindexa por `index_paths` (espiado no teste) e o texto novo aparece na busca; salvar um `.gitignore`: cai em `index_project`
- [ ] Um arquivo novo com segredo, criado no ciclo 50 com o gate em cache, é **bloqueado** e não entra no índice
- [ ] `uv run pytest tests/integration/test_watch.py tests/security` verdes

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Ciclo ocioso, 643 arquivos | 170–240 ms | |
| Ciclo ocioso, 2.000 arquivos | 330–540 ms | |
| Construção do gate por ciclo | 28–41 ms | |
| Uso de núcleo parado (intervalo de 2 s) | ~10–25% | |

Comando: `uv run python scripts/medir_watch.py --arquivos 643 --ciclos 50` (criar: gera o projeto, roda `watch(max_cycles=50)` e imprime mediana e p95 de `last_cycle_ms`).

## Testes

- [ ] `tests/integration/test_watch.py`: gate construído uma vez em 50 ciclos; alteração de `.gitignore`, `.dockerignore` e `.ragignore` reconstrói; `snapshot(cfg)` sem gate continua igual (os testes atuais passam sem mudança)
- [ ] `tests/integration/test_watch.py`: lote de 1 arquivo vai por `index_paths`; lote com `.gitignore` ou acima de `max_batch` vai por `index_project`; arquivo apagado sai do índice
- [ ] `tests/unit/test_walk.py` (novo, ou em `test_ignore_engine.py`): `scan_fingerprints` com e sem cache de veredito devolve o mesmo dicionário; `stat` do `DirEntry` igual a `os.stat` em arquivo comum
- [ ] `tests/security/test_watch_gate.py` (novo): arquivo com segredo de `tests/fixtures/secrets_under_test.py` criado depois de muitos ciclos não entra no índice (nem em `chunks`, nem em `fts`) e gera `security_events`; `.env` novo idem; `walk.py` continua chamando `gate.admit` (o arquitetural já cobre, rodar)

## Notas

- Confirmado em `src/ragx/watch/monitor.py:68-80,96,124-172` (cada ciclo: `snapshot(cfg)` → `_gate(cfg)` → `SecurityGate(...)` → `IgnoreEngine._descobrir`), `src/ragx/security/ignore_engine.py:70-134` (varredura da árvore no `__init__`) e `src/ragx/walk.py:136` (`path.stat()` depois de o `DirEntry` já ter sido consultado, e jogado fora, em `_walk`).
- Caveat do Windows: no NTFS o tamanho e o mtime da entrada de diretório podem ficar defasados enquanto outro processo mantém o arquivo aberto para escrita. Se a comparação com `os.stat` divergir no teste de estresse (arquivo em `a+` aberto), **não** usar `DirEntry.stat()`; confirmar cada candidato a mudança com `os.stat` ou manter só os outros dois cortes.
- A invalidação do gate por arquivo de ignore preserva o comportamento de hoje (que relê tudo a cada ciclo). Não invalidar nada além disso: o objetivo é custo, e o veredito de segurança continua sendo o `gate.admit` na hora de ler.
- O `git status` de 74–112 ms não está no ciclo ocioso (vem de `index_project` → `gitinfo.read_state`, RAGX-0130); `index_paths` não o chama.
- Se o perfil mostrar que o custo é quase todo `scandir` do sistema (o piso do polling), registrar o piso medido, manter o ganho do gate e do veredito em cache e propor, em outra tarefa, o intervalo adaptativo.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0147)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
