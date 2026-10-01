# RAGX-0129 — Poda de diretórios com negação em `.gitignore` aninhado

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P0 — bloqueante |
| **Estimativa** | 0,5d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-01) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V1, S4) · [02-seguranca.md](../../docs/02-seguranca.md) · [04-indexacao.md](../../docs/04-indexacao.md) |
| **Status** | `done` |

## Objetivo

`IgnoreEngine.can_prune` devolve `False` para `src/app/node_modules`, `src/app/dist` e `src/app/out` neste repositório, então o walker desce em todos. Medido na auditoria: 19.120 arquivos vistos para 643 mantidos, `iter_files` = 12,8 s dos 15 s de uma indexação sem mudança, varredura do watcher em 5,3–8,6 s (corrigida: 0,14–0,26 s). A causa é que `_prefixo_literal` guarda o diretório **pai** do alvo da negação, e a cláusula `d.startswith(prefixo + "/")` bloqueia a poda de tudo abaixo desse pai.

## Entregáveis

- [x] **Medir primeiro.** Registrar em "Andamento": `IgnoreEngine._negacoes` do repo, `files_seen` e `duration_ms` de `uv run ragx index . --dry-run --json`, e o tempo de `snapshot(cfg)` (`ragx.watch.monitor`).
- [x] Teste de regressão **vermelho antes do conserto** (ver Testes): árvore com `.gitignore` aninhado com `!.vscode/extensions.json` e `node_modules/` irmão.
- [x] `_prefixo_literal` (`src/ragx/security/ignore_engine.py:189-204`) passa a devolver o caminho literal **completo** do alvo quando o último segmento não tem curinga (`*?[`): `.vscode/extensions.json` com escopo `src/app` vira `src/app/.vscode/extensions.json`; `!src/app/build/` vira `src/app/build`. Com curinga no fim (`build/**/keep.txt`, `node_modules/pkg/**`) o prefixo continua sendo a parte fixa (`build`, `node_modules/pkg`), e padrão de um segmento só continua sendo genérico (prefixo vazio).
- [x] Os dois chamadores de `_prefixo_literal` (`extra_include`, linha 56; negações do `_descobrir`, linhas 110-114) seguem corretos; `can_prune` (175-181) não muda de estrutura. Com o prefixo igual ao alvo, as três cláusulas passam a significar: ancestral do alvo, o próprio alvo, descendente do alvo. Dizer isso no docstring.
- [x] Teste de equivalência (em `tests/security/`): o conjunto de arquivos **admitidos**, com os veredictos, é idêntico com `can_prune` ligado e com `can_prune=None`.
- [x] `docs/02-seguranca.md` (seção "Pasta ignorada é podada", linhas 107-121): negação com caminho só impede a poda do alvo, dos ancestrais e dos descendentes dele; nunca de irmãos.
- [x] CHANGELOG, seção `[Não lançado]`, com o número antes/depois.

## Fora de escopo

- Reaproveitar `SecurityGate`/`IgnoreEngine` entre ciclos do watcher: é a RAGX-0147.
- Junction do Windows tratada como symlink: RAGX-0149.
- Mudar a semântica de reinclusão (o RAGX reinclui um arquivo cujo diretório pai é ignorado quando há negação com caminho; "como sempre funcionou", e difere do git de propósito).
- Custo de `IgnoreEngine.__init__` (`_descobrir`, ~0,9 s medido nesta máquina antes do conserto): medir de novo depois; se ainda passar de 0,3 s, abrir tarefa nova.

## Critérios de aceite

- [x] `can_prune("src/app/node_modules")`, `("src/app/dist")` e `("src/app/out")` devolvem `True` neste repo; `("src/app/build")` e `("src/app/.vscode")` continuam `False` (têm negação apontando para eles).
- [x] `files_seen` de `ragx index . --dry-run --json` cai de 19.120 para a ordem de grandeza dos 643 mantidos (registrar o número exato).
- [x] Varredura do watcher (`snapshot`) ≤ 0,5 s (a auditoria mediu 0,14–0,26 s com a poda corrigida).
- [x] Indexação sem mudança contribui para o **S4** (≤ 1,5 s em ~20k arquivos); a parte do embedder é a RAGX-0130.
- [x] Conjunto admitido idêntico com e sem poda (teste de equivalência) e `uv run pytest tests/security` verde.

## Medição

| Métrica | Antes | Depois |
|---|---|---|
| Arquivos vistos (`files_seen`) numa indexação sem mudança | 19.120 (19.195 medido hoje) | **743** |
| `iter_files` numa indexação sem mudança | 12,8 s (de 15 s) | walker inteiro 17,0 s → **2,5 s**; `duration_ms` do dry-run 3.775 → **328** |
| Varredura do watcher (`snapshot`) | 5,3–8,6 s (3,49 s medido hoje) | **0,13–0,16 s** |

Comando: `uv run ragx index . --dry-run --json` e
`uv run python -c "import time; from ragx.config import load_config; from ragx.watch.monitor import snapshot; c=load_config(); t=time.perf_counter(); n=len(snapshot(c)); print(n, round(time.perf_counter()-t, 2))"`.

## Testes

- [x] `tests/unit/test_ignore_engine.py`: `.gitignore` na raiz com `node_modules/` e `!sub/keep/`, mais `sub/.gitignore` com `.vscode/` e `!.vscode/extensions.json`. Afirma `can_prune("sub/node_modules")` e `can_prune("sub/dist")` verdadeiros, `can_prune("sub/.vscode")` e `can_prune("sub/keep")` falsos. **Falha antes do conserto.** Os testes `test_negacao_com_caminho_impede_a_poda` e `test_include_explicito_so_protege_o_caminho_que_pede` continuam verdes.
- [x] `tests/unit/test_ignore_engine.py`: tabela de `_prefixo_literal` (`.vscode/extensions.json` com e sem escopo, `build/`, `build/**/keep.txt`, `**/x`, `!foo`, `/a/b.txt`).
- [x] `tests/security/test_poda_e_gate.py` (novo): árvore sintética com negações aninhadas, `.env` dentro de pasta podada e fora dela; `iter_files` com a poda real e com `can_prune` neutralizado produzem os mesmos `(rel_path, verdict)` para tudo que não for `skip`; nenhum segredo da fixture entra no índice.

## Notas

- Confirmado em `ignore_engine.py:175-181` e reproduzido: no repo, `_negacoes == [('src/app', False), ('src/app/.vscode', False)]` (de `!src/app/build/` no `.gitignore` da raiz, linha 24, e de `!.vscode/extensions.json` em `src/app/.gitignore`, linha 19).
- A mudança só **reduz** o que é visitado: pasta podada nunca teve bytes lidos. O risco é deixar de indexar algo que antes entrava; o teste de equivalência existe para provar que isso não acontece.
- Windows: comparar sempre com `as_posix()`; um alvo com `\` na negação não pode virar prefixo.
- Se a premissa não se confirmar (`can_prune` já devolver `True`), perfilar `iter_files` com `cProfile` antes de mexer e registrar onde os 12,8 s realmente vão.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [x] Testes escritos e verdes (Windows rodado aqui; Linux e macOS pelo CI)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0129)` na branch `feat/v2`

## Andamento

2026-09-30. Medido antes: `_negacoes == [('src/app', False), ('src/app/.vscode', False)]`, `files_seen` 19.195,
`duration_ms` 3.775, `snapshot` 3,49 s (718 arquivos), `IgnoreEngine.__init__` 0,35 s, `can_prune` falso para os 5 diretórios.
Medido depois: `_negacoes == [('src/app/build', False), ('src/app/.vscode/extensions.json', False)]`, `files_seen` 743,
`duration_ms` 328, `snapshot` 0,13–0,16 s (719 arquivos), `IgnoreEngine.__init__` 0,02 s; `can_prune` verdadeiro para
`node_modules`, `dist` e `out`, falso para `build` e `.vscode`. O custo de `IgnoreEngine.__init__` ficou abaixo do
limiar de 0,3 s da nota de escopo, então nenhuma tarefa nova foi aberta.
Equivalência verificada no repositório inteiro (com e sem poda): 754 arquivos não-`skip`, conjunto idêntico, diferença vazia.
Mudança em `_prefixo_literal` (`ignore_engine.py`): devolve o caminho completo do alvo quando não há curinga; padrão de um
segmento só continua genérico. Testes: `tests/unit/test_ignore_engine.py` (regressão vermelha antes, tabela de
`_prefixo_literal`) e `tests/security/test_poda_e_gate.py` (novo). Fast suite, `tests/security`, `ruff` e `mypy` verdes.
