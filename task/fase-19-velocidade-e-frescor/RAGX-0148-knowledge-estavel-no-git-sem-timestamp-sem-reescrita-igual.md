# RAGX-0148 — `knowledge/` estável no Git: sem timestamp, sem reescrita igual

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0131 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-12) · [25-spec-v2.md](../../docs/25-spec-v2.md) (princípio 3) · [12-git-sync.md](../../docs/12-git-sync.md) · [08-dictionary.md](../../docs/08-dictionary.md) · [ADR-0010](../../docs/adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) |
| **Status** | `done` |

## Objetivo

`knowledge/` é versionado para ser reidratado, mas não é estável: um `sync` sem nenhuma mudança deixa **3 arquivos rastreados sujos** (`manifest.json`, `dictionary.json` e `federation/service.json`, por causa do `generated_at`), e editar **1 função** mexeu em **26 arquivos** (13 de 16 shards de `relations`, 6 de 16 de `entities`) (I-12). Todo commit do projeto leva ruído de `knowledge/`, e o diff deixa de dizer o que mudou de verdade. A tarefa faz o sync gravar só o que mudou de conteúdo, mantém o `generated_at` onde há leitor e investiga por que o grafo espalha uma edição por tantos shards.

## Entregáveis

- [x] **Medir primeiro** (`scripts/medir_knowledge_estavel.py`, em clone temporário do repo): `ragx sync` duas vezes sem mudança e `git status --porcelain knowledge/`; depois editar uma função, `sync` e listar os arquivos alterados por pasta; para os shards de `relations`, comparar campo a campo (`git diff --word-diff`) o que mudou, para saber **por que** 13 de 16 mudam. Registrar em Medição
- [x] `src/ragx/sync/stable_write.py` (novo): `write_text_if_changed(path, body, volatile=())` e `write_bytes_if_changed`, que comparam com o que já está no disco e **não tocam o arquivo** (nem o mtime) quando o conteúdo é igual; `volatile` é a lista de chaves JSON ignoradas na comparação (`generated_at`); arquivo existente ilegível é regravado. O modelo já existe em `src/ragx/tasks/serialize.py:49-56` (`_dump`)
- [x] Usar o helper em `src/ragx/sync/serialize.py`: `_dump_json` e `_dump_jsonl` (57-70), shards `.i8` (`write_bytes`, linha 209), `_write_manifest` (286-306, `generated_at` volátil)
- [x] Mesma regra em `src/ragx/dictionary/builder.py:357-363` (`write`, `project.generated_at` volátil), `src/ragx/federation/slice.py:158-162` (`_write`; `service.json` com `generated_at`) e `src/ragx/tasks/serialize.py:49-56,135` (hoje compara o corpo inteiro, e o `generated_at` do manifesto o torna sempre diferente)
- [x] O campo `generated_at` **permanece**, só deixa de forçar reescrita: o VS Code o lê como "última sincronização" (`vscode-plugin/src/rag/McpClient.ts:295`, a partir do `project.generated_at` do dicionário)
- [x] `SerializeReport` (`serialize.py:34-44`) ganha `files_changed` (arquivos efetivamente regravados) ao lado de `files_written` (que conta o que existe em disco, linha 108); `ragx sync --json` o expõe
- [x] Diagnóstico e correção dos shards do grafo (`serialize.py:224-260`): se, medido, uma edição tocar mais de 3 dos 16 shards, trocar a regra de `shard_of(r["id"], 16)` (linha 250) para agrupar por **documento de origem** (`document_id` da entidade, e o do `src` na relação), de modo que editar um arquivo mexa em 1 ou 2 shards. Se a causa for outra, corrigir a causa e registrar. Não há leitor desses shards no código (nenhum `read_*` de entidades/relações em `src/ragx`, nada no painel nem na extensão), então a mudança de formato não quebra consumidor
- [x] `docs/12-git-sync.md` (estabilidade, quando o `generated_at` muda) e `docs/08-dictionary.md:155-156`

## Fora de escopo

- `sync`/`refresh` deixarem de regravar `knowledge/` quando ninguém pediu (RAGX-0131); aqui só a estabilidade do que é gravado
- Remover o `generated_at` ou mudar o formato dos manifestos
- Ler os shards de grafo ou os embeddings versionados na volta (embeddings: RAGX-0144)
- Conteúdo dos chunks no Git (ADR-0010 o proíbe) e `.gitattributes`
- O tempo de `serialize` (RAGX-0131)

## Critérios de aceite

- [x] Dois `ragx sync` seguidos sem mudança: `git status --porcelain knowledge/` **vazio** (antes: 3 arquivos) e `files_changed == 0`; o `mtime_ns` de todo arquivo de `knowledge/` permanece
- [x] Editar uma função e rodar `sync`: arquivos alterados em `knowledge/` **≤ 8** (antes: 26). Meta provisória: 1 de chunks, 1 de documento, 1–2 shards de embeddings, o dicionário e 2–3 de grafo; confirmar depois de "medir primeiro"
- [x] Quando o conteúdo muda, o `generated_at` é atualizado
- [ ] Mesmos bytes em Linux, macOS e Windows (LF, sem BOM), com `core.autocrlf` ligado ou não (LF e sem BOM por teste; Linux e macOS só a CI)
- [x] `ragx dictionary generate` duas vezes sem mudança não altera `dictionary.json`

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Arquivos rastreados sujos após `sync` sem mudança | 3 (e 134 só com mtime trocado) | **0** (e 0 com mtime trocado) |
| Arquivos de `knowledge/` alterados ao editar 1 função | 26 (medição da tarefa); 10 (sintético) e 9 (cópia de `src/ragx`) aqui | **7** (sintético) e **8** (cópia de `src/ragx`) |
| Shards de `relations` alterados | 13 de 16 (da tarefa) | **1 de 16** aqui, antes e depois: causa não reproduzida |
| Shards de `entities` alterados | 6 de 16 (da tarefa) | **1 de 16** aqui, antes e depois |

Comando: `uv run python scripts/medir_knowledge_estavel.py <pasta-do-clone>` (criar).

## Testes

- [x] `tests/unit/test_stable_write.py` (novo): conteúdo igual não toca o arquivo (`mtime_ns` igual); chave volátil ignorada em qualquer nível do caminho; JSON existente inválido é regravado; bytes iguais em `write_bytes_if_changed`
- [x] `tests/integration/test_sync.py`: `sync` duas vezes → árvore de `knowledge/` byte a byte igual e `files_changed == 0`; editar um arquivo → só os esperados mudam e o manifesto ganha `generated_at` novo
- [x] `tests/integration/test_dictionary.py` (perto de `test_generated_at_fica_fora_do_digest`, linha 135), `tests/integration/test_federation.py` e `tests/integration/test_tasks.py`: `service.json`, `dictionary.json` e `tasks/manifest.json` estáveis entre duas gerações iguais
- [x] `tests/integration/test_graph.py` ou `test_sync.py`: editar 1 função toca no máximo o número de shards de grafo fixado pela medição (regressão que falha com a regra por `id`)
- [x] `tests/security/test_surfaces.py`: `knowledge/dictionary.json` pré-existente com um segredo plantado é **sobrescrito** pelo `sync` (a comparação nunca preserva conteúdo diferente do novo, já limpo por `_scrub`)

## Notas

- Confirmado em `src/ragx/sync/serialize.py:57-70,209,304`, `src/ragx/dictionary/builder.py:66,357-363,366-372` (`stable_digest` já ignora `generated_at`: o digest do dicionário não muda, o **arquivo** muda), `src/ragx/federation/slice.py:72,158-162` e `src/ragx/tasks/serialize.py:135`. O `generated_at` do `serialize.py` está na linha 304, não na 247 (a auditoria apontou o comentário do grafo).
- Leitura do título ("sem timestamp"): o objetivo é nenhum timestamp **volátil** sujando o Git, e isso se cumpre mantendo o campo e só o atualizando quando o conteúdo muda. Remover o campo é a alternativa; se a pessoa preferir, `vscode-plugin/src/rag/McpClient.ts:295` passa a ler a data de `.ragx/status.json` (`index.finished_at`). A RAGX-0131 (Fora de escopo) cita "tirar `generated_at`" como parte desta; decidir na hora e registrar em Andamento.
- Hipótese a verificar, não afirmada: `evidence_chunk_id` e `chunk_id` mudam quando o chunk editado muda de id (o id é função do conteúdo), e cada função é evidência de várias relações (`calls`, `mentions`) espalhadas pelos 16 shards porque o shard sai do hash do `id` da relação. Se for isso, agrupar por documento resolve; senão, seguir o diagnóstico.
- `_check_artifacts` e `files_written` fazem `rglob` do `knowledge/` inteiro a cada sync; não mexer aqui.
- Windows: comparar bytes, não texto (CRLF), e escrever sempre com `newline="\n"`, como hoje. `.gitattributes` já tem `* text=auto eol=lf`.
- A primeira `sync` depois desta mudança reescreve todos os shards de grafo uma vez (nova regra de agrupamento): avisar no CHANGELOG para ninguém estranhar o diff.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0148)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_

## Andamento

- 2026-10-01 — `scripts/medir_knowledge_estavel.py` (projeto sintético ou `--copiar src/ragx`, sempre em `tempfile`; nunca toca o `knowledge/` do repositório). Implementado: `sync/stable_write.py` (`write_text_if_changed`, `write_bytes_if_changed`, `volatile`), usado em `serialize.py` (`_dump_json`, `_dump_jsonl`, shards `.i8`, manifesto com `generated_at` volátil), `dictionary/builder.py`, `federation/slice.py` e `tasks/serialize.py`; `SerializeReport.files_changed` e `knowledge_files_changed` no `ragx sync --json`.
- **Medido:** `sync` sem mudança: 3 arquivos mudavam de conteúdo (`dictionary.json`, `federation/service.json`, `manifest.json`) e 134 de 137 tinham o mtime trocado; agora **0 e 0**, `files_changed == 0`. Editar 1 função: 10 para 7 (sintético) e 9 para 8 (cópia de `src/ragx`), dentro da meta (≤ 8), o que sobra é o legítimo (chunk, documento, 2 shards de embeddings, entidades, relações e o manifesto, cujos contadores mudam).
- **Shards do grafo: regra NÃO mudada.** O critério da tarefa era trocar `shard_of(id, 16)` por agrupamento por documento só se uma edição tocasse mais de 3 dos 16 shards. Medido: 1 de `entities` e 1 de `relations` (sintético e cópia de `src/ragx`), antes e depois, então a hipótese "evidence_chunk_id espalha" não se reproduz aqui. Os 13 de 16 da auditoria podem vir de uma edição que renomeia ou altera muitos chunks; fica registrado, sem mudar o formato. Por isso o aviso de "primeira sync reescreve todos os shards" do CHANGELOG não se aplica.
- Testes: `test_stable_write.py` (7), `test_knowledge_estavel.py` (4: árvore byte a byte e mtime iguais, edição toca ≤ 8 e o `generated_at` acompanha, dicionário estável, `service.json` e manifesto de tarefas estáveis), segurança (`dictionary.json` com segredo plantado é sobrescrito). Suíte Python inteira, `ruff` e `mypy` verdes. Observação: `test_touchq.py::test_dois_claim_concorrentes...` falhou uma vez sob carga total de CPU em paralelo (`assert 0 == 50`) e passou em 4 repetições; é teste de concorrência sensível a timing, fora desta tarefa.
