# RAGX-0139 — Veredito de arquivo não indexável guardado (`file_verdicts`)

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P1 — alta |
| **Estimativa** | 0,5d |
| **Depende de** | RAGX-0129 |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-05) · [25-spec-v2.md](../../docs/25-spec-v2.md) (S4) · [02-seguranca.md](../../docs/02-seguranca.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [03-modelo-de-dados.md](../../docs/03-modelo-de-dados.md) |
| **Status** | `done` |

## Objetivo

Arquivo `unsupported` ou bloqueado nunca entra em `documents`, então o atalho de tamanho+mtime (`walk.py:73-81`, alimentado por `DocumentRepo.fingerprints`) nunca vale para ele: a cada rodada o arquivo é relido inteiro (`walk.py:100-103`), passa de novo pelo gate e, se bloqueado, refaz `DELETE`+`INSERT` em `security_events` (`pipeline.py:197-206`); o `unsupported` só descobre que não serve depois de ler e passar pelo gate (`pipeline.py:222-229`). Medido: com 800 `.csv`, `index` sem mudança sobe de 0,4–1,0 s para 4,8–6,9 s; neste repositório, 20 arquivos bloqueados são reprocessados a cada rodada.

## Entregáveis

- [x] **Medir primeiro:** projeto sintético com 800 `.csv` pequenos; tempo de `index` sem mudança e número de leituras (`Path.read_bytes` espiado). E quantos arquivos bloqueados este repo reprocessa por rodada (esperado: 20).
- [x] Migração com o próximo número livre em `src/ragx/storage/migrations/`: `file_verdicts(rel_path TEXT PRIMARY KEY, verdict TEXT NOT NULL, rule_id TEXT, size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, checked_at TEXT NOT NULL)`. `verdict` em `blocked | unsupported | binary | undecodable`. Atualizar `SCHEMA_VERSION` (`core/ids.py:19`), o teste `test_schema_version_bate_com_a_migracao_mais_recente` e a tabela de `docs/03-modelo-de-dados.md`.
- [x] `VerdictRepo` em `storage/repositories.py` (`load`, `put_many`, `delete_many`, `clear`) e `verdict_context(cfg) -> str` (novo `indexing/verdicts.py`): `sha256` de `security/rules/*` (`patterns.yaml`, `filenames.yaml`, `default_ignore.txt`), `RULESET_VERSION`, `CHUNKER_VERSION`, `cfg.security` (`policy`, `scan_content`, `min_entropy`, `disabled_rules`) e `cfg.index` (`exclude`, `include`, `include_unknown`, `max_file_bytes`). Guardar em `meta('verdict_ctx')`; no início de `_index_once`, se o valor mudou, `clear()` e regravar.
- [x] `iter_files` (`walk.py:33-115`) ganha `verdicts` (dict `rel -> (size, mtime, verdict, rule_id)`). Depois de `should_ignore` e do atalho de `fingerprints`, `(size, mtime)` igual ao guardado emite um `WalkedFile` com o `GateDecision` equivalente (`BLOCK` com `rule_id` e `findings=()`, ou `SKIP`) e `cached_verdict=True`, **sem abrir o arquivo**. O cache só pode manter um arquivo **fora** do índice; nunca coloca nada dentro.
- [x] `_index_once` (`pipeline.py:197-229`): `BLOCK` em cache conta em `blocked` e em `blocked_paths`, mas não refaz `clear_for`/`record` de `security_events` (as linhas atuais ficam); grava o veredito quando o arquivo é bloqueado (nome ou conteúdo), `unsupported` (`parsed is None`), binário ou indecodável; apaga o veredito quando o arquivo vira documento ou some. `dry_run` não grava; `full=True` limpa e reavalia tudo.
- [x] `docs/02-seguranca.md` e `docs/04-indexacao.md`: o que é guardado, o que invalida, e que o cache só mantém fora.
- [x] CHANGELOG com o número antes/depois.

## Fora de escopo

- Poda de diretórios: RAGX-0129 (dependência). Reindexar só os arquivos tocados: RAGX-0140.
- Ler só 8 KiB para sondar binário em vez do arquivo todo (`walk.py:100-105`): tarefa nova se medir ganho.
- Guardar veredito de `ignore` e `too_large`: custam só `stat`, não leem o arquivo.
- Versionar `file_verdicts` em `knowledge/`: é estado local e derivado.

## Critérios de aceite

- [x] 800 `.csv` e `index` sem mudança ≤ 1,5 s (antes 4,8–6,9 s; sem os `.csv`: 0,4–1,0 s).
- [x] Na 2ª rodada, 0 leituras de arquivo `unsupported`, binário ou bloqueado inalterado (espiar `Path.read_bytes`).
- [x] `stats.blocked` e `blocked_paths` iguais na 1ª e na 2ª rodada; `security_events` idêntico (mesmos ids de linha).
- [x] Mudar `[security] policy`, `disabled_rules`, `min_entropy`, `[index] include_unknown` ou um arquivo de regras limpa o cache e reavalia: arquivo antes bloqueado que passa a ser admitido entra no índice.
- [x] Arquivo `unsupported` ou bloqueado que **muda** (tamanho ou mtime) é reavaliado: o `.csv` inofensivo que ganha um segredo vira `blocked` com `security_event`.

## Medição

| Métrica | Antes | Depois |
|---|---|---|
| `index` sem mudança, +800 `.csv` (processo quente, p50 de 5) | 629 ms, 800 leituras (nesta máquina; o 4,8–6,9 s da auditoria era outra) | **344 ms, 0 leituras** |
| `index` sem mudança, sem os `.csv` | 0,4–1,0 s | não regride: o veredito só é consultado para arquivo que já ficaria fora |
| Arquivos bloqueados reprocessados por rodada (20 `.pem` sintéticos) | 20 (`security_events` refeito) | **0**; `security_events` idêntico, mesmos ids |

Script: `medir_0139.py` (60 `.py`, 800 `.csv`, 20 `.pem`; "sem cache" apaga `file_verdicts` e `meta('verdict_ctx')` antes de cada rodada; `Path.read_bytes` espiado). Não rodei `ragx index .` neste repositório: a migração 8 mexeria no índice ao vivo do usuário, e o 20 do repo equivale aos `.pem` do sintético.

## Testes

- [x] `tests/integration/test_pipeline.py`: 2ª rodada sem leitura dos `.csv` (falha antes); contadores iguais; arquivo removido apaga a linha de `file_verdicts`.
- [x] `tests/integration/test_pipeline.py`: `full=True` e `dry_run=True` (não grava).
- [x] `tests/unit/test_verdicts.py` (novo): `verdict_context` muda com cada campo listado e com o conteúdo de um arquivo de regras; é estável entre execuções.
- [x] `tests/security/test_verdicts.py` (novo): (1) arquivo bloqueado fica fora do índice nas duas rodadas; (2) trocar a política de `strict` para `balanced` com um achado `high` isolado reavalia e o arquivo passa a entrar **redigido**, nunca com o valor do segredo (`leaked`); (3) `.csv` inofensivo em cache que ganha um segredo vira `blocked`; (4) nenhum segredo da fixture chega ao banco, a `security_events` ou a `file_verdicts` (nenhuma coluna guarda trecho do arquivo); (5) desativar uma regra em `disabled_rules` invalida o cache.
- [x] `tests/security/test_architecture.py::test_walker_passa_pelo_gate_antes_de_entregar_bytes` continua verde: o novo `yield` também constrói `WalkedFile` com `GateDecision`.

## Notas

- Confirmado em `walk.py:73-81,100-103`, `pipeline.py:158-176,197-206,222-229` e `core/ids.py:22` (`RULESET_VERSION = "builtin@1"`, sem bump manual confiável: por isso o hash dos arquivos de regra).
- O gate é o mesmo; esta tarefa só evita reexecutá-lo quando nada de que ele depende mudou. O risco real é **servir um veredito velho**; toda a seção de testes de segurança existe para isso. Na dúvida, não usar o cache.
- Conteúdo muda sem mudar tamanho e mtime (relógio manipulado) não é detectado, como já acontece com o atalho de `fingerprints`; `ragx index --full` resolve.
- Windows: `mtime_ns` tem resolução de 100 ns no NTFS e de 2 s em FAT; usar o mesmo critério do atalho existente (`walk.py:75`).
- `rule_id` de `blocked` é só o identificador da regra, nunca um trecho do arquivo (mesma regra de `security_events`).

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0139)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `0008_file_verdicts.sql` (`SCHEMA_VERSION` 8), `VerdictRepo`, `indexing/verdicts.py` (`verdict_context`, `prepare`), `WalkedFile.cached_verdict` e o parâmetro `verdicts` de `iter_files`/`iter_paths`/`_examinar` (a consulta vem depois do `ignore` e ANTES do atalho de `fingerprints`, e nunca emite ALLOW), e a gravação/limpeza em `_handle` (`_guardar`, `_sem_veredito`, `_flush_verdicts`), também no `index_paths`.
- Decisões: (1) o veredito de bloqueio por NOME também é guardado (evita o `DELETE`+`INSERT` em `security_events`, que era o custo dos 20 bloqueados). (2) Em veredito guardado `BLOCK` o `docs.delete_many` ainda roda (barato e fecha o caso de um documento perdido no índice). (3) Os testes ficaram em `tests/unit/test_verdict_context.py`, `tests/integration/test_file_verdicts.py` e `tests/security/test_file_verdicts_seguranca.py` (o pytest deste repo exige nome de módulo único, então não pode haver três `test_verdicts.py`).
- Descoberto, fora de escopo: `[security] disabled_rules` NÃO é aplicado pelo `SecurityGate` do pipeline (só `doctor` e `security scan` usam `load_ruleset(disabled)`); a regra desativada continua valendo na indexação. É o lado seguro, mas a opção é enganosa: vale uma tarefa própria. O contexto do cache já a inclui, então quando for corrigido o cache se invalida sozinho.
