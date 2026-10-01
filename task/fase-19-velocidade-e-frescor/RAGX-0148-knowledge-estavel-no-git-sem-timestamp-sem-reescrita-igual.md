# RAGX-0148 — `knowledge/` estável no Git: sem timestamp, sem reescrita igual

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P2 — média |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0131 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-12) · [25-spec-v2.md](../../docs/25-spec-v2.md) (princípio 3) · [12-git-sync.md](../../docs/12-git-sync.md) · [08-dictionary.md](../../docs/08-dictionary.md) · [ADR-0010](../../docs/adr/ADR-0010-conteudo-nao-versionado-e-embeddings-quantizados.md) |
| **Status** | `todo` |

## Objetivo

`knowledge/` é versionado para ser reidratado, mas não é estável: um `sync` sem nenhuma mudança deixa **3 arquivos rastreados sujos** (`manifest.json`, `dictionary.json` e `federation/service.json`, por causa do `generated_at`), e editar **1 função** mexeu em **26 arquivos** (13 de 16 shards de `relations`, 6 de 16 de `entities`) (I-12). Todo commit do projeto leva ruído de `knowledge/`, e o diff deixa de dizer o que mudou de verdade. A tarefa faz o sync gravar só o que mudou de conteúdo, mantém o `generated_at` onde há leitor e investiga por que o grafo espalha uma edição por tantos shards.

## Entregáveis

- [ ] **Medir primeiro** (`scripts/medir_knowledge_estavel.py`, em clone temporário do repo): `ragx sync` duas vezes sem mudança e `git status --porcelain knowledge/`; depois editar uma função, `sync` e listar os arquivos alterados por pasta; para os shards de `relations`, comparar campo a campo (`git diff --word-diff`) o que mudou, para saber **por que** 13 de 16 mudam. Registrar em Medição
- [ ] `src/ragx/sync/stable_write.py` (novo): `write_text_if_changed(path, body, volatile=())` e `write_bytes_if_changed`, que comparam com o que já está no disco e **não tocam o arquivo** (nem o mtime) quando o conteúdo é igual; `volatile` é a lista de chaves JSON ignoradas na comparação (`generated_at`); arquivo existente ilegível é regravado. O modelo já existe em `src/ragx/tasks/serialize.py:49-56` (`_dump`)
- [ ] Usar o helper em `src/ragx/sync/serialize.py`: `_dump_json` e `_dump_jsonl` (57-70), shards `.i8` (`write_bytes`, linha 209), `_write_manifest` (286-306, `generated_at` volátil)
- [ ] Mesma regra em `src/ragx/dictionary/builder.py:357-363` (`write`, `project.generated_at` volátil), `src/ragx/federation/slice.py:158-162` (`_write`; `service.json` com `generated_at`) e `src/ragx/tasks/serialize.py:49-56,135` (hoje compara o corpo inteiro, e o `generated_at` do manifesto o torna sempre diferente)
- [ ] O campo `generated_at` **permanece**, só deixa de forçar reescrita: o VS Code o lê como "última sincronização" (`vscode-plugin/src/rag/McpClient.ts:295`, a partir do `project.generated_at` do dicionário)
- [ ] `SerializeReport` (`serialize.py:34-44`) ganha `files_changed` (arquivos efetivamente regravados) ao lado de `files_written` (que conta o que existe em disco, linha 108); `ragx sync --json` o expõe
- [ ] Diagnóstico e correção dos shards do grafo (`serialize.py:224-260`): se, medido, uma edição tocar mais de 3 dos 16 shards, trocar a regra de `shard_of(r["id"], 16)` (linha 250) para agrupar por **documento de origem** (`document_id` da entidade, e o do `src` na relação), de modo que editar um arquivo mexa em 1 ou 2 shards. Se a causa for outra, corrigir a causa e registrar. Não há leitor desses shards no código (nenhum `read_*` de entidades/relações em `src/ragx`, nada no painel nem na extensão), então a mudança de formato não quebra consumidor
- [ ] `docs/12-git-sync.md` (estabilidade, quando o `generated_at` muda) e `docs/08-dictionary.md:155-156`

## Fora de escopo

- `sync`/`refresh` deixarem de regravar `knowledge/` quando ninguém pediu (RAGX-0131); aqui só a estabilidade do que é gravado
- Remover o `generated_at` ou mudar o formato dos manifestos
- Ler os shards de grafo ou os embeddings versionados na volta (embeddings: RAGX-0144)
- Conteúdo dos chunks no Git (ADR-0010 o proíbe) e `.gitattributes`
- O tempo de `serialize` (RAGX-0131)

## Critérios de aceite

- [ ] Dois `ragx sync` seguidos sem mudança: `git status --porcelain knowledge/` **vazio** (antes: 3 arquivos) e `files_changed == 0`; o `mtime_ns` de todo arquivo de `knowledge/` permanece
- [ ] Editar uma função e rodar `sync`: arquivos alterados em `knowledge/` **≤ 8** (antes: 26). Meta provisória: 1 de chunks, 1 de documento, 1–2 shards de embeddings, o dicionário e 2–3 de grafo; confirmar depois de "medir primeiro"
- [ ] Quando o conteúdo muda, o `generated_at` é atualizado
- [ ] Mesmos bytes em Linux, macOS e Windows (LF, sem BOM), com `core.autocrlf` ligado ou não
- [ ] `ragx dictionary generate` duas vezes sem mudança não altera `dictionary.json`

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| Arquivos rastreados sujos após `sync` sem mudança | 3 | |
| Arquivos de `knowledge/` alterados ao editar 1 função | 26 | |
| Shards de `relations` alterados | 13 de 16 | |
| Shards de `entities` alterados | 6 de 16 | |

Comando: `uv run python scripts/medir_knowledge_estavel.py <pasta-do-clone>` (criar).

## Testes

- [ ] `tests/unit/test_stable_write.py` (novo): conteúdo igual não toca o arquivo (`mtime_ns` igual); chave volátil ignorada em qualquer nível do caminho; JSON existente inválido é regravado; bytes iguais em `write_bytes_if_changed`
- [ ] `tests/integration/test_sync.py`: `sync` duas vezes → árvore de `knowledge/` byte a byte igual e `files_changed == 0`; editar um arquivo → só os esperados mudam e o manifesto ganha `generated_at` novo
- [ ] `tests/integration/test_dictionary.py` (perto de `test_generated_at_fica_fora_do_digest`, linha 135), `tests/integration/test_federation.py` e `tests/integration/test_tasks.py`: `service.json`, `dictionary.json` e `tasks/manifest.json` estáveis entre duas gerações iguais
- [ ] `tests/integration/test_graph.py` ou `test_sync.py`: editar 1 função toca no máximo o número de shards de grafo fixado pela medição (regressão que falha com a regra por `id`)
- [ ] `tests/security/test_surfaces.py`: `knowledge/dictionary.json` pré-existente com um segredo plantado é **sobrescrito** pelo `sync` (a comparação nunca preserva conteúdo diferente do novo, já limpo por `_scrub`)

## Notas

- Confirmado em `src/ragx/sync/serialize.py:57-70,209,304`, `src/ragx/dictionary/builder.py:66,357-363,366-372` (`stable_digest` já ignora `generated_at`: o digest do dicionário não muda, o **arquivo** muda), `src/ragx/federation/slice.py:72,158-162` e `src/ragx/tasks/serialize.py:135`. O `generated_at` do `serialize.py` está na linha 304, não na 247 (a auditoria apontou o comentário do grafo).
- Hipótese a verificar, não afirmada: `evidence_chunk_id` e `chunk_id` mudam quando o chunk editado muda de id (o id é função do conteúdo), e cada função é evidência de várias relações (`calls`, `mentions`) espalhadas pelos 16 shards porque o shard sai do hash do `id` da relação. Se for isso, agrupar por documento resolve; senão, seguir o diagnóstico.
- `_check_artifacts` e `files_written` fazem `rglob` do `knowledge/` inteiro a cada sync; não mexer aqui.
- Windows: comparar bytes, não texto (CRLF), e escrever sempre com `newline="\n"`, como hoje. `.gitattributes` já tem `* text=auto eol=lf`.
- A primeira `sync` depois desta mudança reescreve todos os shards de grafo uma vez (nova regra de agrupamento): avisar no CHANGELOG para ninguém estranhar o diff.

## Definition of Done

- [ ] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows
- [ ] `ruff` e `mypy` limpos
- [ ] Suíte `security/` continua verde
- [ ] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [ ] Documentação confere com o comportamento implementado
- [ ] Commit `tipo(escopo): descrição (RAGX-0148)` na branch `feat/v2`

## Andamento

_(o loop registra aqui o que fez, com datas e medições)_
