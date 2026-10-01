# RAGX-0150 — Micro-custos: `ragx context` sem `--tokens`, MMR vetorizado, query embutida uma vez

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (C-11, C-12) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V13) · [07-context-engine.md](../../docs/07-context-engine.md) · [14-cli.md](../../docs/14-cli.md) · [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `todo` |

## Objetivo

Quatro custos pequenos que a auditoria achou no `build_context` e na CLI. **C-11:** `ragx context "q"` sem `--tokens` falha com `rc=2` (`0 is not in the range 200<=x<=200000`), porque o padrão do `typer.Option` é `0` e o intervalo começa em 200. **C-12:** o MMR roda em laço Python (**17,7 ms** contra **0,8 ms** vetorizado, seleção idêntica); a consulta é embutida **duas vezes** por `build_context` (na busca e em `_vectors_for`); e o `SecurityGate` do `dictionary.build` caminha a árvore só para usar o scanner (28–41 ms por construção).

## Entregáveis

- [ ] **Medir primeiro**: espiar `embed_query` num `build_context` real (esperado: 2 chamadas) e cronometrar `mmr` com 30 candidatos; registrar em Medição
- [ ] `src/ragx/cli/commands/context_cmd.py:20`: `--tokens` passa a `int | None = None` (mantendo `min=200, max=200_000`); `budget=tokens or cfg.context.default_tokens` (linha 42) já resolve; a ajuda diz que o padrão vem de `[context] default_tokens`. Documentar em `docs/14-cli.md`
- [ ] `src/ragx/context/dedup.py:68-108` (`mmr`): versão vetorizada com `V = vstack(vetores)`, relevância `V @ q` e redundância mantida em um vetor `max_sim` atualizado com `np.maximum(max_sim, V @ V[melhor])` a cada escolha. Preservar a semântica exata: candidato **sem vetor** usa `cand.score` como relevância e redundância 0,0; redundância sem nenhum escolhido ainda é 0,0; empate resolvido pelo **primeiro** da ordem original (`value > best_value` estrito no código atual); converter para `float64` só depois do produto, como o `float(v @ q)` faz
- [ ] Consulta embutida uma vez: `SearchOutcome` (`src/ragx/search/service.py:35-40`) ganha `query_vec` preenchido em `_semantic` (linha 123); `GraphSearchOutcome` (`src/ragx/graph/service.py:71-76`) o repassa; `_vectors_for` (`src/ragx/context/engine.py:264-300`) aceita o vetor pronto e só embute quando ele não veio (busca em modo keyword, cache de contexto, embedder indisponível). Truncar para a dimensão dos vetores do banco como hoje (`[:dim]` + `l2_normalize`, linha 297)
- [ ] `src/ragx/dictionary/builder.py:333-336` (`_scrub`): trocar `SecurityGate(cfg.root, policy=...)`, que constrói um `IgnoreEngine` e varre a árvore, por `SecurityScanner(load_ruleset(), min_entropy=3.0)` (os mesmos valores que o gate usa hoje por padrão); `_scrub` só chama `gate.scanner.scan_content`
- [ ] Atualizar `docs/07-context-engine.md` (a consulta é embutida uma vez; o MMR é vetorizado) e `docs/14-cli.md`

## Fora de escopo

- A exatidão do contador de tokens (+11% em prosa e +29% em código contra `cl100k`, `tokens.py:24-39`): é da RAGX-0154 (contar o que sai) e da RAGX-0156 (tokens reais)
- Cache do `build_context` (RAGX-0135) e `load_index` (RAGX-0134)
- Qualquer mudança de resultado: o `build_context` devolve os **mesmos** fragmentos, na mesma ordem
- Fazer `_scrub` respeitar `cfg.security.min_entropy` e `disabled_rules`: hoje ele os ignora (usa os padrões do gate) e esta tarefa mantém o comportamento; se for bug, abrir tarefa própria

## Critérios de aceite

- [ ] `uv run ragx context "como funciona o gate"` sem `--tokens` sai com código 0 e respeita `default_tokens` (antes: `rc=2`)
- [ ] `mmr` com 30 candidatos: **≤ 2 ms** (antes 17,7 ms; vetorizado de referência 0,8 ms) e **mesma seleção e mesma ordem** em 200 sementes aleatórias e nas 26 consultas de `tests/eval/queries.yaml`
- [ ] `embed_query` chamado **1 vez** por `build_context` sem cache (antes 2), com graph e sem graph
- [ ] `dictionary.build` ~30–40 ms mais rápido (a construção do gate sai); o dicionário gerado é **idêntico** byte a byte
- [ ] `uv run pytest tests/security`, `ruff` e `mypy src/ragx/core src/ragx/security` verdes

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| `ragx context "q"` sem `--tokens` | `rc=2` | |
| MMR, 30 candidatos | 17,7 ms | |
| Chamadas a `embed_query` por `build_context` | 2 | |
| `SecurityGate` construído em `dictionary.build` | 28–41 ms | |

Comando: `uv run python -c "import time; from ragx.config import load_config; from ragx.context.engine import build_context; c=load_config(); t=time.perf_counter(); p=build_context(c,'como o gate decide bloquear um arquivo',use_cache=False); print(round((time.perf_counter()-t)*1000), p.stats)"` (o `stats` traz `dedup_ms`).

## Testes

- [ ] `tests/unit/test_context_units.py`: `mmr` novo contra uma cópia da implementação antiga guardada no teste, 200 sementes aleatórias, com vetores ausentes, empates exatos (vetores repetidos), `k` maior que o conjunto e `query_vec=None`
- [ ] `tests/integration/test_context.py`: espiar `embed_query` (embedder falso) → 1 chamada com `include_graph` verdadeiro e falso; com a busca em modo keyword (`degraded`), `_vectors_for` ainda embute uma vez; os fragmentos são os mesmos de antes
- [ ] `tests/e2e/test_cli_context.py` (novo): `ragx context "q"` sem `--tokens` sai com 0 (regressão que falha hoje, `rc=2`); `--tokens 100` continua recusado
- [ ] `tests/integration/test_dictionary.py`: `build` com o scanner direto produz o mesmo dicionário que o gate completo (comparar `stable_digest` e o JSON de um projeto de fixture, construindo o gate no próprio teste como referência)
- [ ] `tests/security/test_surfaces.py` (ou novo `test_dicionario_scrub.py`): segredo plantado em nome de entidade/título é redigido para `«RAGX:REDACTED»` no dicionário, com o scanner direto, exatamente como com o gate

## Notas

- Confirmado em `src/ragx/cli/commands/context_cmd.py:20,42`, `src/ragx/context/dedup.py:86-106` (laço duplo, `float(v @ s)` por par), `src/ragx/context/engine.py:297` e `src/ragx/search/service.py:123` (as duas chamadas a `embed_query`), `src/ragx/dictionary/builder.py:333-336` e `src/ragx/security/ignore_engine.py:59-60` (`_descobrir` no `__init__`).
- O MMR é o único ponto em que `value > best_value` decide empate; `np.argmax` devolve a primeira ocorrência, que casa. A diferença possível é de arredondamento (BLAS em `gemv` contra `dot`): por isso o teste usa sementes aleatórias e a comparação com as consultas reais; se uma divergência aparecer só em empate de 1e-7, documentar em Andamento.
- Passar o `query_vec` pelos objetos de saída em vez de memoizar dentro do embedder evita estado escondido; a alternativa (memo de uma entrada no embedder) serviria também a perguntas repetidas, mas muda o protocolo `Embedder` e fica para depois.
- Windows: o teste do `typer` roda a CLI via `CliRunner`/subprocesso; `windows_expand_args=False` já é tratado em `main._invocar`.
- O `_scrub` é segurança: o teste em `tests/security` prova que trocar o gate pelo scanner não afrouxou nada. Não aceitar a mudança sem ele.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0150)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
