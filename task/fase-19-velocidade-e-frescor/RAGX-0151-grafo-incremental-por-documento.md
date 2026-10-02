# RAGX-0151 — Grafo incremental por documento

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P3 — baixa |
| **Estimativa** | 1,5d |
| **Depende de** | RAGX-0138 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-07) · [25-spec-v2.md](../../docs/25-spec-v2.md) (princípio 3) · [06-grafo.md](../../docs/06-grafo.md) · [19-watch-e-autonomia-do-agente.md](../../docs/19-watch-e-autonomia-do-agente.md) · [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) |
| **Status** | `review` |

## Objetivo

O grafo só é refeito em `sync`, sempre **completo** (`graph.service.rebuild`: `clear` + extração de todos os documentos): **1,0–1,5 s** com 2,4 mil entidades e **5,4–9,2 s** com 15 mil (I-07). Por isso, entre dois `sync`, um símbolo novo não aparece no grafo e `get_entity`, `search_graph` e a expansão do contexto raciocinam sobre o estado antigo; no watcher o grafo só é refeito a cada `full_sync_every` mudanças (50 por padrão, 25 neste repo). A tarefa atualiza o grafo só dos documentos tocados e cai no rebuild completo quando a mudança não é local.

## Entregáveis

- [x] **Medir primeiro**: em ~100 commits do próprio repo, para cada arquivo de código alterado, o conjunto de símbolos (nomes das entidades `class`/`function`/`method`) mudou ou não? Registrar a fração "não mudou" em Medição. **Se for menor que 50%**, parar, deixar a tarefa em `review` com o número e não implementar o caminho rápido
- [ ] `IndexReport` (`src/ragx/indexing/pipeline.py:41-50`) ganha `touched_documents: list[str]` (caminhos de documentos indexados, alterados ou removidos na rodada), preenchido em `_index_once` e em `index_paths` (RAGX-0140)
- [ ] `src/ragx/graph/extractors/structural.py:25-93` (`extract`) aceita `only_documents: set[str] | None` e restringe as duas consultas (`documents`, `chunks`) a esses ids; sem o argumento, o comportamento é o de hoje
- [ ] `src/ragx/graph/extractors/reference.py:62-196` (`extract`): aceitar `only_documents` e gerar entidades e relações **só dos chunks desses documentos**, mas resolvendo nomes contra o índice de **todas** as entidades (`name_index` continua global, linhas 83-89). A parte de tecnologias (`_technologies`, 199-250) fica de fora do caminho rápido (ver abaixo)
- [ ] `src/ragx/graph/service.py`: `update_documents(cfg, rel_paths) -> RebuildReport` com `fallback_full: bool`. Fluxo, numa transação: (1) entidades dos documentos tocados **antes** (nomes por tipo); (2) estrutural + referencial dos tocados, com `upsert` (**sem** apagar entidades, para não derrubar por `ON DELETE CASCADE` as relações vindas de **outros** documentos que apontam para elas); (3) apagar só as relações de origem `structural`/`reference` cujo `src_id` ou cujo `evidence_chunk_id` seja dos documentos tocados e regravá-las; (4) apagar entidades que sumiram; (5) `prune_orphans`
- [ ] Regra de queda: se o conjunto de nomes de entidades de algum documento tocado **mudou** (símbolo novo, removido ou renomeado), ou o documento é manifesto de dependências (`composer.json`, `package.json`, `pyproject.toml`, `requirements.txt`, `go.mod`, `Gemfile`), ou o documento foi removido, chamar `rebuild` completo e marcar `fallback_full`. Motivo: relações de entrada vindas de outros documentos dependem do conjunto de nomes
- [ ] Tecnologias: no caminho rápido só **acrescentar** (rodar `_technologies` sobre as linhas dos documentos tocados, com união); remover tecnologia que deixou de ser usada fica para o próximo rebuild completo (`sync`/consolidação). Documentar a defasagem
- [ ] Chamadores: `watch.monitor.apply_changes` (`src/ragx/watch/monitor.py:83-121`) e `touchq.drain` (RAGX-0141) chamam `update_documents(report.touched_documents)` depois de indexar; falha do grafo vira aviso, nunca derruba a indexação (como a consolidação hoje). A camada semântica (`source='semantic'`) nunca é tocada
- [ ] `ragx graph rebuild` e `sync` continuam fazendo o rebuild completo, que é a referência de correção
- [ ] `docs/06-grafo.md`: quando o grafo é atualizado por documento, quando cai no completo e a defasagem das tecnologias

## Fora de escopo

- Preservar `chunk_id` e `evidence_chunk_id` entre edições (RAGX-0138; esta tarefa assume que ela existe)
- Regenerar dicionário e fatia de federação a cada edição (continuam no `sync`)
- Tornar o rebuild completo mais rápido
- Camada semântica e o diff de `knowledge/` (RAGX-0148)
- Resolver relações de entrada de símbolo novo sem cair no rebuild (exigiria varrer chunks de outros documentos por FTS)

## Critérios de aceite

- [ ] **Equivalência**: depois de cada uma de 50 sequências aleatórias de edições (corpo, símbolo novo, símbolo renomeado, arquivo novo, arquivo removido), o grafo incremental é igual ao de um `rebuild` completo no mesmo banco (mesmos ids de entidade e de relação, mesmos `weight`, `confidence`, `source`, `evidence_chunk_id`), **exceto** entidades `technology` e relações `uses`, que só podem ser **superconjunto**
- [ ] Editar o corpo de uma função (nomes iguais) atualiza o grafo em **≤ 15% do tempo do rebuild completo** (meta provisória; ~1,0–1,5 s completo com 2,4 mil entidades)
- [ ] Símbolo novo aparece em `get_entity` logo após a reindexação (por queda para o completo); depois de editar uma linha, **0** entidades com `chunk_id` nulo (a auditoria mediu 7 e 27 relações sem evidência)
- [ ] Nenhuma relação vinda de outro documento é perdida ao editar o documento alvo
- [ ] `uv run pytest tests/integration/test_graph.py tests/integration/test_watch.py` verdes

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Rebuild do grafo, 2,4 mil entidades | 1,0–1,5 s | |
| Rebuild do grafo, 15 mil entidades | 5,4–9,2 s | |
| Atualização por documento, corpo editado | rebuild completo | 22 ms contra 178 ms do completo (12,4%), 2,4 mil entidades — **só na branch `wip/ragx-0151-grafo-incremental`** |
| Edições do repo que não mudam o conjunto de símbolos | medir primeiro | **47,0%** (116 de 247 edições `.py` em 100 commits) — abaixo do corte de 50%: **parou** |
| Entidades com `chunk_id` nulo após editar 1 linha | 7 (27 relações sem evidência) | 1 só com o índice (projeto sintético) e 0 depois do `update_documents` — só na branch wip |

Comando: `uv run python scripts/medir_grafo_incremental.py` (criar; imprime os quatro tempos e a fração de commits).

## Testes

- [ ] `tests/integration/test_graph_incremental.py` (novo): propriedade de equivalência com sequências aleatórias e semente fixa; arquivo removido; arquivo novo; renomear símbolo cai no completo (`fallback_full`); editar manifesto cai no completo
- [ ] Mesmo arquivo: relação de **entrada** (documento A chama símbolo de B) sobrevive à edição de B quando os nomes de B não mudam
- [ ] `tests/integration/test_graph.py`: `rebuild_preserva_camada_semantica` e `rebuild_e_idempotente` continuam verdes; `update_documents` preserva `source='semantic'`
- [ ] `tests/integration/test_watch.py`: salvar um arquivo atualiza o grafo sem `full_sync_every`; falha forçada do grafo vira aviso e a indexação conclui
- [ ] `tests/unit/test_graph_units.py`: `structural.extract(only_documents=...)` devolve exatamente o recorte do resultado completo
- [ ] Não lê arquivo do projeto (só o banco): sem teste novo em `tests/security`; rodar a suíte inteira

## Notas

- Confirmado em `src/ragx/graph/service.py:33-68` (`rebuild`: `store.clear` + extração completa + `prune_orphans`), `src/ragx/graph/extractors/reference.py:62-196` (relações `calls`, `mentions`, `imports`, `documented_by` e entidades `table`/`endpoint`, todas com `evidence_chunk_id` do chunk de origem) e `src/ragx/storage/migrations/0004_graph.sql:9,28` (`entities.chunk_id` e `relations.evidence_chunk_id` são `ON DELETE SET NULL`, `entities.document_id` é `CASCADE`).
- A armadilha central: apagar e recriar as entidades de um documento derruba, por `CASCADE`, as relações que **outros** documentos têm com elas (`relations.src_id`/`dst_id` referenciam `entities`). Por isso o passo (2) é `upsert` e só se apagam entidades que realmente sumiram.
- `documented_by` tem a direção invertida (entidade de código → trecho de doc): a "dona" da relação é a do documento do `evidence_chunk_id`, não a do `src_id`. O critério de apagar por `src_id` **ou** `evidence_chunk_id` cobre as duas.
- Sem a RAGX-0138 os chunks de um arquivo editado são todos apagados e recriados: `evidence_chunk_id` vira nulo e as relações perdem a prova. Não implementar esta tarefa antes dela.
- Determinismo: o resultado não pode depender da ordem em que os documentos tocados chegam; ordenar por caminho antes de processar.
- Se a medição inicial mostrar que o rebuild completo, com o grafo menor, já cabe em ~100 ms, registrar e fechar a tarefa em `review` sem implementar.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0151)` na branch `feat/v2`

## Andamento

- 2026-10-01 — **Parada pelo critério da própria tarefa: `review`, decisão humana.** O primeiro entregável manda medir antes e, "se for menor que 50%, parar, deixar a tarefa em `review` com o número e não implementar o caminho rápido". Medido com `scripts/medir_grafo_incremental.py` (na branch wip): nos últimos 100 commits, 247 edições de arquivo `.py` (modo `M`), com o mesmo parser e chunker do índice; em **116 (47,0%)** o conjunto de `class`/`function`/`method` ficou igual e em 131 mudou. Está abaixo de 50%, mas perto: a conta inclui arquivos de teste e commits grandes de feature, que acrescentam símbolo quase sempre; uma edição de sessão do agente (corpo de função, prosa, SQL) tende a mudar menos. Quem decide se vale é uma pessoa.
- **Erro de processo meu, registrado:** implementei o caminho rápido ANTES de rodar a medição, contra a ordem escrita da tarefa. Em vez de jogar fora o trabalho verificado, ele ficou **só na branch local `wip/ragx-0151-grafo-incremental` (commit `cab3a59`, sem push)**; a `feat/v2` não recebe nada dele.
- O que está na branch wip, verificado por execução (suíte Python `-m "not slow"` 1938 passed, `tests/security` verde, `ruff`, `mypy`): `IndexReport.touched_documents`; `only_documents` em `structural.extract` e `reference.extract` (e `ORDER BY` determinístico, `load_catalog` em cache); `graph.service.update_documents` (cai no completo se o conjunto de entidades mudou, documento novo/removido, manifesto, grafo inexistente ou mais de 50 documentos); chamado pelo `watch.monitor.apply_changes` e por `touchq.drain`, falha vira aviso; `tests/integration/test_graph_incremental.py` com 50 sequências aleatórias de 3 edições comparadas ao `rebuild` (a equivalência foi checada com uma mutação deliberada que a suíte pegou), mais 2 testes no `test_watch.py`. Medido com 2,4 mil entidades: corpo editado 22 ms contra 178 ms do completo (12,4%, dentro dos 15%); símbolo novo cai no completo (322 ms).
- **O que falta para decidir:** (a) aceitar ou não os 47,0% — se sim, `git merge wip/ragx-0151-grafo-incremental` em `feat/v2` e marcar `done` (CHANGELOG e `docs/06-grafo.md` já estão no commit); (b) o rebuild completo do repo real (1,0–1,5 s) não foi medido de novo contra o incremental, só o sintético; (c) com o grafo incremental, um símbolo novo no watcher passa a custar um rebuild completo (1–9 s) a cada edição, em vez de a cada `full_sync_every` mudanças: vale confirmar que não atrapalha o ciclo do watcher; (d) a defasagem das tecnologias (só acrescentam) ficou documentada.
- Não verificado: os 15 mil entidades (5,4–9,2 s) e o repo real; critério "Nenhuma relação vinda de outro documento é perdida" está coberto só pelo teste sintético de relação de entrada.

