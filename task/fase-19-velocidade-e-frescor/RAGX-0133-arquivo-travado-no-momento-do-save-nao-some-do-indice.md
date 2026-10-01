# RAGX-0133 — Arquivo travado no momento do save não some do índice

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (I-06) · [25-spec-v2.md](../../docs/25-spec-v2.md) · [04-indexacao.md](../../docs/04-indexacao.md) · [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `done` |

## Objetivo

Um `OSError` ao abrir um arquivo (antivírus ou editor segurando-o logo depois do save, no Windows) faz o walker simplesmente não emitir o caminho (`walk.py:57-60` no `stat`, `walk.py:100-103` no `read_bytes`). O pipeline então o trata como inexistente: `gone = [p for p in known if p not in seen_paths ...]` (`pipeline.py:271`) apaga o documento. Medido: arquivo aberto de forma exclusiva dá `removed 1` e documentos/chunks de 1/20 para 0/0 até a rodada seguinte. É exatamente o momento em que o hook de edição dispara.

## Entregáveis

- [x] **Reproduzir primeiro** com teste portátil (ver Testes): `Path.read_bytes` levantando `PermissionError` para um arquivo já indexado. Registrar o resultado vermelho.
- [x] `WalkedFile` (`walk.py:20-30`) ganha `unreadable: bool = False`. Em `iter_files`, `OSError` no `stat` (57-60) e no `read_bytes` (100-103) é separado em dois casos: `FileNotFoundError`/`NotADirectoryError` = o arquivo sumiu (não emite, como hoje); qualquer outro `OSError` emite `WalkedFile(..., GateDecision(Verdict.SKIP, rel, rule_id="unreadable", reason="unreadable"), unreadable=True)` sem abrir o arquivo de novo.
- [x] `_walk` (143-180): `iterdir` com `OSError` (156-157) e `is_file()` com `OSError` (179-180) hoje fazem a pasta inteira sumir. Registrar a pasta num conjunto opcional `unreadable_dirs` recebido de `iter_files`/`scan_fingerprints`, em vez de descartá-la em silêncio.
- [x] `pipeline._index_once` (`pipeline.py:178-195, 270-274`): `unreadable` entra em `seen_paths`, conta em `skip_reasons["unreadable"]` e em `IndexReport.unreadable` (novo); `gone` exclui os caminhos que estão sob uma pasta de `unreadable_dirs`. Nada é regravado para o arquivo: documento, chunks, embeddings e `security_events` ficam como estavam.
- [x] `ragx index --json` e o resumo da CLI mostram `unreadable`; o `docs/04-indexacao.md` ganha a regra "arquivo ilegível não é arquivo removido".
- [x] `tests/security/test_architecture.py::test_walker_passa_pelo_gate_antes_de_entregar_bytes` (linhas 191-210) continua valendo: todo `yield` de `iter_files` constrói `WalkedFile` com um `GateDecision`. Ajustar o teste só se a forma do código mudar.
- [x] CHANGELOG.

## Fora de escopo

- Reindexar só os arquivos tocados: RAGX-0140 (que herda esta regra).
- Repetir a leitura com *retry* e espera: o arquivo é reavaliado na próxima rodada, não aqui.
- Junction do Windows: RAGX-0149. Cache de veredito de arquivos não indexáveis: RAGX-0139.
- Ler só 8 KiB para sondar binário em vez do arquivo todo (`walk.py:100-105`): anotar como tarefa nova se medir ganho.

## Critérios de aceite

- [x] Arquivo já indexado que levanta `PermissionError` na leitura: `removed == 0`, `unreadable == 1`, documento e chunks intactos (antes: `removed 1`, 1/20 → 0/0).
- [x] Na rodada seguinte, com o arquivo liberado e **inalterado**, ele conta como `unchanged`; se o conteúdo mudou durante o travamento, é reindexado.
- [x] Arquivo realmente apagado continua saindo do índice (`removed == 1`).
- [x] Pasta ilegível não apaga os documentos que estavam sob ela.
- [x] Arquivo cujo **nome** cai na deny-list continua bloqueado e removido do índice mesmo se estiver travado (o nome é checado antes de abrir).

## Testes

- [x] `tests/integration/test_pipeline.py`: indexa 3 arquivos, faz `monkeypatch` de `pathlib.Path.read_bytes` para `PermissionError` em um deles (portátil; o lock exclusivo real só existe no Windows) e reindexa com `full=True`. Afirma `removed == 0`, documentos e chunks preservados. **Falha antes do conserto.**
- [x] `tests/integration/test_pipeline.py`: o mesmo com `os.stat` falhando com `PermissionError`; e com `Path.iterdir` falhando numa subpasta.
- [x] `tests/integration/test_pipeline.py`: apagar de verdade (`unlink`) continua removendo.
- [x] `tests/security/test_poda_e_gate.py`: arquivo `.env` já indexado por engano (inserido no banco na mão) e travado: a rodada o remove por nome. Arquivo ilegível nunca gera chunk novo nem `security_event` novo.
- [x] `tests/integration/test_watch.py`: o watcher não dispara remoção para arquivo travado.

## Notas

- Confirmado em `walk.py:57-60`, `walk.py:100-103`, `walk.py:156-157`, `walk.py:177-180` e `pipeline.py:271`.
- Windows: o erro típico é `PermissionError` (`WinError 32`, violação de compartilhamento) ou `WinError 5`. Não tratar `errno` específico: qualquer `OSError` que não seja "não existe" significa "não sei agora".
- Efeito colateral aceito: um arquivo que **virou sensível** e ficou travado permanece no índice com o conteúdo antigo até a próxima rodada em que puder ser lido (o conteúdo antigo já tinha passado pelo gate). Registrar isso em `docs/04-indexacao.md`.
- `scan_fingerprints` (`walk.py:118-140`, usado pelo watcher) ignora `OSError` no `stat` e faz o arquivo parecer "apagado" ao watcher; depois deste conserto isso só dispara uma rodada à toa, sem remover nada. Não precisa tratar aqui.
- Se o `FileNotFoundError` do `stat` (arquivo apagado entre a listagem e o `stat`) for confundido com travado nos testes, a regra é: sumiu = não emite.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes (Windows rodado aqui; Linux e macOS pelo CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0133)` na branch `feat/v2`

## Andamento

2026-09-30. Reproduzido primeiro (testes vermelhos: `IndexReport` sem `unreadable`; `removed` subia). Implementado:
`WalkedFile.unreadable`; `_sumiu()` separa FileNotFound/NotADirectory (sumiu) de qualquer outro `OSError` (não sei agora);
`_decisao_sem_ler()` mantém ignore e deny-list de NOME quando o `stat` falha (o nome é checado sem abrir o arquivo);
`_walk(on_unreadable_dir=)` e `iter_files(unreadable_dirs=)` registram pasta que não listou (com prefixo `@base/...`, sem barra final);
`IndexReport.unreadable`, `skip_reasons["unreadable"]`, `--json` e resumo da CLI; `gone` não inclui o que está sob pasta ilegível.
O teste arquitetural `test_walker_passa_pelo_gate_antes_de_entregar_bytes` continua valendo sem alteração: todo `yield`
de `iter_files` continua construindo `WalkedFile` (a decisão vem de helper, o yield não).
Testes: `tests/integration/test_pipeline.py` (4 novos), `tests/integration/test_watch.py` (1), `tests/security/test_poda_e_gate.py` (2).
Observação: para isolar o `stat` do walker foi preciso substituir `_walk` no teste, porque `is_dir()`/`is_file()` da listagem
também chamam `Path.stat`. Fast suite, `tests/security`, `ruff`, `mypy` verdes. Sem número antes/depois de tempo: é correção de
perda de dado (antes `removed 1` e documentos/chunks 1/20 -> 0/0; agora `removed 0`, `unreadable 1`, intactos).
