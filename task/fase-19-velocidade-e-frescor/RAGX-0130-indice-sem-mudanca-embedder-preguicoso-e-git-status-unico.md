# RAGX-0130 — Índice sem mudança: embedder preguiçoso e `git status` único

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-07, I-08) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V2, S4) · [04-indexacao.md](../../docs/04-indexacao.md) |
| **Status** | `todo` |

## Objetivo

`ragx index` sem nenhuma mudança custa 3,5 s no repo real: 2,85 s para carregar o modelo de embedding, que `embed_pending` constrói (`indexing/embed.py:46`) **antes** de saber se há chunk pendente (`missing_chunk_ids`, linha 84), e 1,0 s em 7 chamadas ao `git`. As 7 são: `read_state` com 3 (`gitinfo.py:55-61`) e `write_status` rodando 2× (`pipeline.py:87,94`), cada uma com 2 chamadas a `hooks_dir` (`githooks.installed` e `githooks.state`, `githooks.py:168-192`).

## Entregáveis

- [ ] **Medir primeiro:** contar construções do embedder (espiar `_construir` em `embeddings/__init__.py:58`) e chamadas a `gitinfo.git` numa indexação sem mudança, e registrar o tempo.
- [ ] `embedder_id(cfg) -> str` em `src/ragx/embeddings/__init__.py`, **sem construir** o provider: `hashing:{dim}`, `ollama:{model}`, `fastembed:{model}` com a mesma substituição do modelo padrão de `_construir` (linhas 75-77). `build_embedder(cfg).id` e `embedder_id(cfg)` nunca divergem (teste de paridade). A RAGX-0136 reutiliza esta função.
- [ ] `embed_pending` (`indexing/embed.py:39-125`) reordenado: `model_id = embedder_id(cfg)` e `dim = cfg.embedding.dim`; `register_model`, limpeza de vetores de outro modelo (69-82) e `missing_chunk_ids` rodam **antes** de qualquer construção. Sem pendência, retorna com `report.model_id` preenchido, sem construir o embedder e sem a sondagem `available()` (que no Ollama custa até 2 s). Só com `pending` não vazio constrói o embedder e sonda.
- [ ] `gitinfo.read_state` (`gitinfo.py:55-61`) com **uma** chamada: `git status --porcelain=v2 --branch --untracked-files=normal -- .`. `# branch.oid` dá o commit, `# branch.head` a branch (`(detached)` vira `None`), qualquer linha que não comece com `#` marca `dirty`. Repo sem commit (`(initial)`) continua devolvendo `None`.
- [ ] `githooks.installed` (`githooks.py:189-192`) deixa de chamar `hooks_dir` duas vezes (usar só o resultado de `state`), e `gitinfo.hooks_dir` é memoizado por processo e por raiz, **sem guardar `None`**, com `cache_clear()` em `install`/`uninstall`.
- [ ] `docs/04-indexacao.md`: indexação sem mudança não carrega o modelo.
- [ ] CHANGELOG com o número antes/depois.

## Fora de escopo

- Poda de diretórios: RAGX-0129. Indexação por caminho sem `git` nem varredura: RAGX-0140.
- Aquecer o embedder em segundo plano no servidor MCP: RAGX-0142.
- Entrada leve para `hook-run` (hoje bloqueia o commit 0,72–1,09 s): RAGX-0143.
- `freshness.compute` (5–6 subprocessos `git`): RAGX-0141.
- Cache de embedding em SQLite: RAGX-0146.

## Critérios de aceite

- [ ] Indexação sem mudança com `provider = "fastembed"` constrói o embedder **0** vezes (antes: 1) e não chama `available()` com `ollama`.
- [ ] No máximo **2** chamadas a `gitinfo.git` por `index_project` sem mudança (antes: 7).
- [ ] Com pendência, o resultado é idêntico: mesmos `embedded`, mesmos vetores gravados.
- [ ] Ollama fora do ar e nada pendente: `embed_error is None` (antes: erro de "indisponível").
- [ ] Tempo de `ragx index .` sem mudança no repo real ≤ 1,0 s (meta; o S4 completo ainda depende da RAGX-0129).

## Medição

| Métrica | Antes | Depois |
|---|---|---|
| `ragx index .` sem mudança, repo real | 3,5 s | |
| Tempo de modelo dentro dele | 2,85 s | |
| Chamadas ao `git` | 7 (1,0 s) | |

Comando: `uv run ragx index . --json` duas vezes seguidas; ler `duration_ms` da segunda.

## Testes

- [ ] `tests/integration/test_pipeline.py`: indexa, indexa de novo com `_construir` espiado (monkeypatch em `ragx.embeddings._construir`); afirma 0 construções na segunda. **Falha antes do conserto.**
- [ ] `tests/integration/test_pipeline.py`: espiar `ragx.gitinfo.run_quiet` e afirmar `<= 2` chamadas numa indexação sem mudança, em repo git de `tmp_path`.
- [ ] `tests/unit/test_embeddings.py`: `embedder_id(cfg) == build_embedder(cfg).id` e `.dim == cfg.embedding.dim` para `hashing` e `ollama` (e `fastembed` com `pytest.importorskip`).
- [ ] `tests/unit/test_gitinfo.py`: `read_state` com porcelain v2 em repo limpo, sujo, HEAD destacado e sem commit.
- [ ] `tests/integration/test_pipeline.py`: com chunk pendente e `ollama` inalcançável, `embed_error` continua preenchido.
- [ ] `tests/security/` verde sem alteração: o caminho de leitura de arquivo não muda.

## Notas

- Confirmado em `embed.py:46` (construção) e `embed.py:84` (pendência), `pipeline.py:87,94,161` e `githooks.py:189-192`. A conta das 7 chamadas fecha: 3 + 2 × 2.
- `dim` vem de `cfg.embedding.dim` em todos os providers (`_construir`, linhas 58-86); o teste de paridade existe para pegar o dia em que isso mudar.
- `git status --porcelain=v2 --branch` existe desde o git 2.11. A saída é só para ler `oid`, `head` e se há linha de alteração; não analisar caminhos (ver `changed_paths`, que é outra função).
- Memoizar `hooks_dir` sem guardar `None` evita o cache de "fora de repositório" depois de um `git init` na mesma sessão.
- Se o tempo final não chegar a 1,0 s, registrar o que domina com `cProfile` (provável: a varredura, RAGX-0129) em vez de declarar o critério cumprido.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0130)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
