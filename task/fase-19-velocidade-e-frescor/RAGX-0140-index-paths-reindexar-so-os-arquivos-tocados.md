# RAGX-0140 — `index_paths`: reindexar só os arquivos tocados

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 1d |
| **Depende de** | RAGX-0129, RAGX-0133, RAGX-0138 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-02; "Desenho proposto para o frescor") · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V11, S6) · [04-indexacao.md](../../docs/04-indexacao.md) · [02-seguranca.md](../../docs/02-seguranca.md) · [19-watch-e-autonomia-do-agente.md](../../docs/19-watch-e-autonomia-do-agente.md) |
| **Status** | `todo` |

## Objetivo

Não existe reindexação por caminho: `iter_files(only=)` (`walk.py:38`) não tem chamador e, mesmo se tivesse, filtra **depois** de percorrer a árvore (`walk.py:55`). Reindexar um arquivo editado custa 1,3–2,0 s (varredura, gate, git e embedder) contra 130–270 ms de um protótipo que toca só o arquivo (mais 0,3–0,4 s de imports num processo novo). `index_paths(cfg, paths)` é a base da RAGX-0141 (fila de toque e hook de edição), do **S6** (edição visível em ≤ 5 s) e do `refresh` em ≤ 3 s.

## Entregáveis

- [ ] **Medir primeiro:** `index_project` com 1 arquivo alterado (repo real e projeto sintético de 2.000 arquivos) e o tempo de construir `SecurityGate`/`IgnoreEngine` depois da RAGX-0129.
- [ ] Extrair o corpo por arquivo de `iter_files` (`walk.py:52-115`) para uma função única, usada por `iter_files` e por `iter_paths(root, gate, rels, max_bytes, follow_symlinks)`. `iter_paths` **não enumera**: para cada caminho relativo, rejeita absoluto, `..` e prefixo `@base/`; trata como ignorado se algum ancestral for symlink (sem `follow_symlinks`) ou `gate.ignore.can_prune(ancestral)` (mesma regra do `_walk`); exige `resolve()` dentro da raiz (ameaça A8); arquivo ausente (`FileNotFoundError`) não é emitido; outro `OSError` vira `unreadable` (RAGX-0133). Ajustar o teste arquitetural `tests/security/test_architecture.py:191-210` para cobrir também `iter_paths`.
- [ ] Extrair do laço de `_index_once` (`pipeline.py:178-268`) o tratamento de um `WalkedFile` (BLOCK, parse, chunk, `upsert`, `replace_for_document` da RAGX-0138, eventos) para uma função usada pelos dois caminhos.
- [ ] `index_paths(cfg, paths, *, embed=True, source="paths", wait_s=0.0) -> IndexReport` em `indexing/pipeline.py`: mesma trava (`lock.try_acquire`; ocupada, `mark_pending` e `IndexBusyError`, como `index_project`); `"paths"` entra em `VALID_SOURCES`; uma transação; `known` só dos caminhos pedidos; **sem** `gitinfo.read_state`; `embed_pending` ao fim (embedder preguiçoso, RAGX-0130); `status_file.write_status` uma vez, no fim. Cai em `index_project` incremental se um caminho for arquivo de regra (`.gitignore`, `.dockerignore`, `.ragignore`, `ragx.toml`) ou se houver mais de `cfg.watch.max_batch` caminhos.
- [ ] A run de `index_paths` grava `index_runs` com `mode='paths'`, copiando `git_branch`/`git_commit` da última run completa e `git_dirty = 1`, sem chamar o git.
- [ ] `status_file._last_finished` (`status_file.py:40-43`) e `pipeline.status()` (`pipeline.py:409-412`) passam a excluir `mode = 'paths'` (hoje excluem só `embed-only`). Sem isso `freshness._uncommitted` (`freshness.py:23-28`) usaria o `finished_at` de uma rodada parcial e daria "em dia" para arquivos que ninguém varreu.
- [ ] `ragx index --only <caminho>` (repetível, em `cli/commands/index_cmd.py`) chama `index_paths`; é o ponto de entrada manual e do E2E.
- [ ] `docs/04-indexacao.md`: reindexação por caminho, o que a dispensa (varredura, git) e o que **não** dispensa (gate, poda, trava).
- [ ] CHANGELOG com o número antes/depois.

## Fora de escopo

- Fila `touch.queue`, hook `PostToolUse`, drenagem no MCP e `stale_paths` na busca: RAGX-0141.
- Watcher usando `index_paths`: RAGX-0147. Aquecer o embedder no MCP: RAGX-0142.
- Grafo incremental: RAGX-0151. Veredito em cache (`file_verdicts`): RAGX-0139.
- Renomeação como unidade: o caminho antigo e o novo chegam como dois caminhos (um some, outro entra).

## Critérios de aceite

- [ ] 1 arquivo alterado: `index_paths` ≤ 400 ms em processo, com provider `hashing` e o `SecurityGate` já construído pela chamada (o protótipo da auditoria mediu 130–270 ms; antes: 1,3–2,0 s).
- [ ] Não percorre a árvore nem chama o git: `iter_files`, `_walk` e `gitinfo.git` espiados com 0 chamadas.
- [ ] Equivalência: para N caminhos sorteados numa árvore sintética (com `.gitignore` aninhado, pasta podada, arquivo grande, binário, `.env`), `index_paths` e `index_project` deixam os mesmos `documents` e `chunks`.
- [ ] Segredo novo em arquivo tocado: BLOCK, documento removido se existia, banco, FTS e `knowledge/` sem o valor.
- [ ] Caminho em pasta ignorada ou podada, `..`, absoluto, symlink ou junction para fora da raiz: não indexado.
- [ ] Arquivo apagado sai do índice; arquivo travado (RAGX-0133) permanece.
- [ ] Depois de `index_paths`, `ragx status` continua `stale` por mudanças não commitadas que ele não cobriu.

## Medição

| Métrica | Antes | Depois |
|---|---|---|
| Reindexar 1 arquivo (`index_project`) | 1,3–2,0 s | |
| Protótipo só do arquivo tocado (auditoria) | 130–270 ms | |
| Chamadas ao `git` por reindexação | 7 (ver RAGX-0130) | |

Comando: `uv run python -c "import time; from ragx.config import load_config; from ragx.indexing.pipeline import index_paths; c=load_config(); t=time.perf_counter(); r=index_paths(c, ['README.md']); print(round((time.perf_counter()-t)*1000), 'ms', r.stats)"` depois de tocar o arquivo.

## Testes

- [ ] `tests/integration/test_index_paths.py` (novo): arquivo novo, alterado, apagado, renomeado, travado; lote acima do teto cai no incremental; arquivo de regra cai no incremental; trava ocupada devolve `IndexBusyError` e deixa pedido pendente.
- [ ] `tests/integration/test_index_paths.py`: equivalência com `index_project` (semente fixa) e ausência de varredura e de `git` (espiões).
- [ ] `tests/integration/test_freshness.py`: depois de `index_paths`, o veredito não vira `fresh` por engano; `test_embed_only_nao_mascara_troca_de_branch` (linha 142) continua verde.
- [ ] `tests/e2e/test_cli_fase0.py` ou novo: `ragx index --only a.py --only b.py`.
- [ ] `tests/security/test_poda_e_gate.py`: `index_paths` com `.env`, `..\x`, `/abs`, caminho dentro de `node_modules/`, symlink para fora (pular onde não houver permissão de symlink no Windows) e segredo novo em arquivo permitido; nenhum valor de `SECRETS_UNDER_TEST` no banco.
- [ ] `tests/security/test_architecture.py`: `iter_paths` só entrega bytes depois de `gate.admit`.

## Notas

- Confirmado em `walk.py:38,55`, `pipeline.py:31-35,129-325`, `status_file.py:35-44` e `freshness.py:16-36`.
- O gate precisa de `IgnoreEngine`, cuja construção varre a árvore atrás de arquivos de ignore (`ignore_engine.py:70-134`; ~0,9 s medido neste repo antes da RAGX-0129). Medir depois da 0129; se o gate ainda passar de ~100 ms, criar um `IgnoreEngine` restrito aos arquivos de ignore dos **ancestrais** dos caminhos pedidos (é o que o git faz) em vez de aceitar o custo.
- Se a RAGX-0139 já estiver `done`, `index_paths` deve respeitar e atualizar `file_verdicts` (apagar ao admitir, gravar ao bloquear).
- Windows: editores salvam por arquivo temporário e `rename`; o caminho final pode estar travado por ~100 ms (regra da 0133). Caminhos chegam com `\` do hook: normalizar com `normalize_path` (`core/ids.py`) antes de usar como chave.
- Se a equivalência com `index_project` falhar em algum caso de poda, **não** relaxar o teste: o `index_paths` deve recusar (cair no incremental completo) e anotar o caso.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0140)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
