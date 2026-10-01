# RAGX-0131 — `refresh` incremental: `sync` só sob pedido, `rehydrate` opt-in, `serialize` só se mudou

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0129 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-02, I-01) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V3, S5) · [09-mcp.md](../../docs/09-mcp.md) · [12-git-sync.md](../../docs/12-git-sync.md) · [19-watch-e-autonomia-do-agente.md](../../docs/19-watch-e-autonomia-do-agente.md) |
| **Status** | `todo` |

## Objetivo

A descrição, o playbook e o hint dizem que `refresh` é "barato quando nada mudou", mas `WriteAPI.refresh` chama `apply_changes(..., consolidate=True)` (`mcp/operations.py:210`), que roda `sync` completo (`watch/monitor.py:113-121`). Medido: `refresh` sem mudança leva 26 s em processo e 72–91 s via MCP sob carga; com 4 arquivos mudados, 34 s. O `sync` gasta 13,7 s em `rehydrate` para produzir um relatório que é descartado (`sync/service.py:95`, `_hydrated`) e ainda regrava todo o `knowledge/`: medir `refresh` sujou 155 arquivos rastreados e criou 422.

## Entregáveis

- [ ] **Medir primeiro:** `refresh` sem mudança e com 4 arquivos tocados (em processo), `ragx sync` sem mudança por etapa, e `git status --porcelain knowledge/` antes e depois. Medir depois da RAGX-0129.
- [ ] `WriteAPI.refresh` (`mcp/operations.py:196-220`) chama `apply_changes(..., consolidate=False, source="mcp:refresh")`: só indexação incremental, `knowledge/` intocado. O campo `consolidated` da resposta fica (agora sempre `false`).
- [ ] Textos que prometem "barato": descrição da ferramenta (`mcp/server.py:686`), `mcp/playbook.py:52-54`, `docs/09-mcp.md:64`, `docs/19-watch-e-autonomia-do-agente.md:112`. Dizer que `refresh` só reindexa e que consolidar é `sync`.
- [ ] `sync(...)` (`sync/service.py:79`) ganha `rehydrate: bool = False`; o passo [1] (linhas 93-105) só roda com `True`. CLI: `ragx sync --rehydrate`, e `--report` (`sync_cmd.py`) passa a implicá-lo. O `sync` do MCP e o do watcher não reidratam. `docs/12-git-sync.md` (linhas 41 e 230+) atualizado.
- [ ] Em `sync`, mover a reconstrução do grafo (passo [4], linhas 126-134) para **antes** de `serialize` (passo [3], 117-120). Hoje `knowledge/entities` e `knowledge/relations` saem um `sync` atrás, porque `serialize` lê o grafo do banco antes de ele ser refeito. O dicionário e a federação continuam depois do grafo.
- [ ] `serialize` pulado quando nada mudou: guardar em `meta` o token do último `sync` completo (`sha256` de: id da última run terminada sem erro com `indexed>0 OR removed>0 OR embedded>0` e `model_dump_json` de `cfg.graph`, `cfg.size`, `cfg.embedding.versioned_dim` e `versioned_quant`). Se o manifest existe, `write_knowledge=True`, `full=False` e o token bate, pular `serialize`. Gravar o token só ao fim de um `sync` sem avisos de erro.
- [ ] CHANGELOG com o número antes/depois.

## Fora de escopo

- Escrever arquivo a arquivo só quando o conteúdo difere, e tirar `generated_at` do `manifest.json`/`dictionary.json`: RAGX-0148.
- Pular grafo, dicionário e federação quando nada mudou (acharia ~3,3 s em `sync` sem mudança; medir antes de propor).
- Grafo incremental: RAGX-0151. Reindexar só os arquivos tocados: RAGX-0140.
- Aquecer o embedder: RAGX-0142 (a primeira indexação com chunk novo num processo frio paga 3–5 s de modelo).
- Clone novo: `sync` abrindo o banco antes de ele existir é a RAGX-0144.

## Critérios de aceite

- [ ] `refresh` com 1–4 arquivos tocados ≤ 3 s com o embedder já carregado (**S5**; a primeira chamada de um processo frio paga o modelo).
- [ ] `refresh` sem mudança ≤ 1,5 s e **não altera** `knowledge/`: `git status --porcelain knowledge/` igual antes e depois.
- [ ] `ragx sync` sem mudança não chama `rehydrate` (0 s, antes 13,7 s); com `--rehydrate` o relatório volta idêntico ao de hoje.
- [ ] Segundo `sync` seguido, sem mudança: `serialize` não roda e `knowledge/` fica byte a byte igual.
- [ ] Depois de editar um arquivo e rodar **um** `sync`, `knowledge/entities` e `knowledge/relations` já refletem o grafo novo.

## Medição

| Métrica | Antes | Depois |
|---|---|---|
| `refresh` sem mudança, em processo | 26 s | |
| `refresh` sem mudança, via MCP sob carga | 72–91 s | |
| `refresh` com 4 arquivos mudados | 34 s | |
| `rehydrate` dentro de `sync` | 13,7 s | |
| `serialize` num `sync` sem mudança | 0,95 s | |
| Arquivos de `knowledge/` sujos após `refresh` | 155 modificados, 422 novos | |

Comando: `uv run python -c "import time; from ragx.config import load_config; from ragx.mcp.operations import WriteAPI; t=time.perf_counter(); r=WriteAPI(load_config(), True).refresh(); print(round(time.perf_counter()-t, 1), r)"`, mais `uv run ragx sync --json`.

## Testes

- [ ] `tests/integration/test_mcp.py` (ou `tests/integration/test_refresh_incremental.py`): espiar `sync.service.sync`, `rehydrate`, `serialize.serialize` e `graph.service.rebuild`; `refresh` não chama nenhum. **Falha antes do conserto.** Hash da árvore `knowledge/` igual antes e depois.
- [ ] `tests/integration/test_sync.py`: `sync` padrão não chama `rehydrate`; com `rehydrate=True` chama. Segundo `sync` sem mudança não chama `serialize`; depois de uma edição chama. Ajustar o que dependia da ordem antiga.
- [ ] `tests/integration/test_sync.py`: após uma edição e **um** `sync`, o conteúdo de `knowledge/entities/*.json` bate com `SELECT * FROM entities` do banco.
- [ ] `tests/integration/test_watch.py`: o ciclo de consolidação do watcher (`full_sync_every`) continua rodando `sync`.
- [ ] `tests/security/`: arquivo novo com segredo adicionado ao working tree e `refresh` chamado; nem o banco nem `knowledge/` contêm o valor (`leaked` de `tests/fixtures/secrets_under_test.py`).

## Notas

- Confirmado em `mcp/operations.py:210`, `watch/monitor.py:113-121`, `sync/service.py:94-95,117-134` e `mcp/playbook.py:52`.
- `rehydrate` é um dos dois módulos autorizados a ler o projeto-alvo (ADR-0008); ele passa a rodar menos, não mais. O Security Gate não muda.
- Se mover o grafo para antes de `serialize` quebrar testes de ordem em `test_sync.py`, ajustar os testes, não a regra. Se o pulo de `serialize` crescer além deste escopo, entregar `refresh` e `rehydrate` opt-in e deixar o pulo em "Andamento" como pendente.
- Windows: arquivos de `knowledge/` são gravados com `newline="\n"`; o teste de hash da árvore deve comparar bytes, não texto.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0131)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
