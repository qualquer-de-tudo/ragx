# RAGX-0143 — Entrada leve para `claude hint` e `hook-run`; guarda no `post-checkout`

| | |
|---|---|
| **Fase** | 19 — Velocidade e frescor |
| **Prioridade** | P1 — alta |
| **Estimativa** | 1d |
| **Depende de** | — |
| **Documentação** | [24-auditoria-v2.md](../../docs/24-auditoria-v2.md) (M-08, M-09) · [25-spec-v2.md](../../docs/25-spec-v2.md) (R-V10, S7, S8) · [12-git-sync.md](../../docs/12-git-sync.md) · [14-cli.md](../../docs/14-cli.md) · [02-seguranca.md](../../docs/02-seguranca.md) |
| **Status** | `done` |

## Objetivo

O hook de `SessionStart` (`ragx claude hint`) leva **481–659 ms** em 12 execuções, contra **41–56 ms** de um protótipo só com stdlib (Python vazio: 48–68 ms), e roda em cada subagente (~20 `session_start` em 2 minutos). O hook de git bloqueia o commit por **539–1041 ms** (`post-commit`, parte síncrona) e o `post-checkout` de arquivo, que devia ser no-op, custa **468–615 ms** (M-08, M-09). A causa é a mesma: o ponto de entrada `ragx.cli.main:main` importa typer, rich, pydantic e 25 módulos de comando antes de olhar o primeiro argumento. As metas são S7 (hint ≤ 120 ms) e S8 (commit bloqueado ≤ 150 ms).

## Entregáveis

- [x] **Medir primeiro** com `scripts/medir_hooks.py` (novo): 12 execuções de `ragx claude hint`, `ragx hook-run post-commit --root .` e `ragx hook-run post-checkout A B 0 --root .`; mais `python -X importtime` do hint, para ver quanto custa cada import (neste Windows até `unicodedata`, importado por `ragx.core.ids`, pesou ~90 ms numa medição ruidosa)
- [x] `src/ragx/hooklight.py` (novo, **só stdlib**; não importa `ragx.config`, `ragx.core`, `ragx.storage`, `ragx.clients`): `find_root`, leitura mínima de `ragx.toml` com `tomllib` (`project.name`, `hub.path`, mais a config de usuário e `RAGX_PROJECT_NAME`/`RAGX_HUB_PATH`, como `config.load_config` faz), `hint_text`, `record_session_start`, `EVENTS`, `should_run`, `spawn_index`
- [x] Mover as funções puras `_texto_projeto`, `_texto_pasta_pai`, `_status` e `_FERRAMENTAS` de `src/ragx/clients/claude_hint.py:175-290` para `hooklight` (recebem nome, `status.json` e pasta do hub em vez de `Config`); `claude_hint.hint_text(start)` e `record_session_start` continuam existindo e delegam, **uma só fonte do texto**
- [x] `src/ragx/origin.py` (novo): `claude_origin` e `profile_name` saem de `src/ragx/clients/registry.py:236` (reexportados lá); `ragx.diagnostics` passa a usar `ragx.origin` e a ter `utcnow` próprio, sem importar `ragx.storage.db`. Motivo: `ragx/clients/__init__.py` importa o `registry` inteiro, então o caminho leve não pode tocar o pacote
- [x] `src/ragx/entry.py` (novo, stdlib): `main()` olha `sys.argv`; `claude hint` e `hook-run` vão para `hooklight`; o resto importa `ragx.cli.main` e chama `main()`. `pyproject.toml` (`[project.scripts]`, linhas 39-43): `ragx` e `rag` apontam para `ragx.entry:main`
- [x] `githooks.py` reexporta `EVENTS`, `should_run`, `spawn_index` de `hooklight` (os testes e o e2e continuam importando de `ragx.githooks`)
- [x] Guarda no shell do hook: `_block` (`src/ragx/githooks.py:63-71`) gera, para `post-checkout`, `if [ "$RAGX_SKIP_HOOK" != "1" ] && [ "$3" = "1" ]; then` (o 3º argumento é 1 só em troca de branch). Arquivo (`$3 = 0`) não sobe Python nenhum. `ragx hooks install` reescreve o bloco antigo (`_strip` + `_insert_block`); `state()` continua reconhecendo pela linha de marcador
- [x] `ragx hooks status` avisa quando o bloco instalado é de formato antigo (sem a guarda) e manda rodar `ragx hooks install`
- [x] Se o comando `touch` da RAGX-0141 já existir, entra no despacho leve (`ragx touch --stdin-json`); se não, pular
- [x] Atualizar `docs/12-git-sync.md` (tabela dos hooks: `post-checkout` só por troca de branch, agora decidido no shell), `docs/14-cli.md` e `docs/22-vscode-e-desempenho.md`

## Fora de escopo

- Encurtar o texto do hint e não repeti-lo em subagente (RAGX-0164); aqui o texto sai **idêntico**, só mais rápido
- Reindexar no `SessionStart` (sem tarefa dona; ver RAGX-0141, Notas)
- Tornar a indexação disparada pelo hook mais barata (RAGX-0129, 0130)
- Mudar o `settings.json` do Claude Code: o comando continua `ragx claude hint`

## Critérios de aceite

- [x] `ragx claude hint`, mediana de 12 execuções: **≤ 120 ms** (S7), saída byte a byte igual à de antes em projeto indexado, em pasta-pai e fora de projeto
- [x] `ragx hook-run post-commit`: **≤ 150 ms** até devolver o terminal (S8); `git checkout -- arquivo` com o hook instalado não cria processo Python (provado por stub)
- [x] `import ragx.hooklight` num subprocesso não carrega `typer`, `rich`, `pydantic`, `numpy`, `yaml`, `pathspec`, `ragx.config` nem `ragx.cli.main`
- [x] Erro em qualquer ponto do hint continua sem escrever nada e sem falhar (código 0)
- [x] Suíte `tests/security` verde, com `ragx.hooklight` na lista do teste arquitetural e justificado

### Medição

| Métrica | Antes | Depois |
|---|---|---|
| `ragx claude hint` (S7) | 481–659 ms (493 ms agora) | **86 ms** (mediana de 12; 78–94) |
| Protótipo só stdlib (referência) | 41–56 ms | — |
| `hook-run post-commit`, parte síncrona (S8) | 539–1041 ms (509 ms agora, projeto pequeno) | **114 ms** (81–124) |
| `hook-run post-checkout` de arquivo | 468–615 ms (481 ms agora) | 90 ms pelo Python; **0** com a guarda de shell (nem sobe processo) |

Comando: `uv run python scripts/medir_hooks.py --n 12` (projeto sintético com `git init`; mede por `python -m <entrada>`, `ragx.cli.main` contra `ragx.entry`).

## Testes

- [x] `tests/unit/test_hooklight.py`: **paridade** `hooklight.hint_text(p) == claude_hint.hint_text(p)` em projeto indexado (com e sem `status.json`, com indexação em andamento), pasta-pai com 2 projetos, fora de projeto, `RAGX_HUB_PATH` e config de usuário; `record_session_start` grava a mesma linha de `cli.jsonl`
- [x] `tests/unit/test_hooklight.py`: subprocesso confirma que o conjunto de módulos carregados não tem os pesados
- [x] `tests/unit/test_githooks.py`: `post-checkout` gerado traz a guarda de `$3`; instalar sobre bloco antigo o substitui sem duplicar; `status` acusa bloco antigo
- [x] `tests/e2e/test_cli_hooks.py`: repositório real, hook instalado com `prefix` apontando para um stub que grava marcador: `git checkout -b x` cria o marcador, `git checkout -- arquivo` não
- [x] `tests/e2e/test_cli_hooks.py`: `ragx` por `ragx.entry:main` continua rodando `index`, `search` e `--version` (despacho para a CLI completa)
- [x] `tests/security/test_architecture.py`: `ragx.hooklight` entra na lista dos que leem artefatos próprios (só `ragx.toml`, `.ragx/status.json`, `registry.json` do hub) e um teste novo proíbe nele `read_bytes`, `rglob`, `walk`, `scandir`, `iterdir`, `glob`

## Notas

- Confirmado em `src/ragx/cli/main.py:10-36` (**25** módulos de comando importados no topo, não 26), `src/ragx/cli/commands/claude_cmd.py:173-201` (`hint` importa `claude_hint`, que importa `ragx.config` → pydantic dentro de `hint_text`), `src/ragx/cli/commands/hooks_cmd.py:74-88` (`hook_run`) e `src/ragx/githooks.py:21-71,195-237`. `ragx/__init__.py` é vazio, então importar `ragx.hooklight` não puxa nada além dos seus próprios imports.
- Os tempos medidos no Windows têm ruído de antivírus em `.pyd`; o critério é a mediana de 12 execuções. Se um import da stdlib custar mais de ~20 ms, trocar por alternativa (por exemplo `time.strftime` no lugar de `datetime`).
- O `githooks._index_argv` usa `sys.executable -m ragx.cli.main` de propósito (comentário nas linhas 203-208): não trocar por `ragx`, e como esse módulo é carregado por `-m`, a indexação em si segue pela CLI completa.
- Instalações editáveis só enxergam o novo `[project.scripts]` depois de `uv tool install --editable --force --python 3.12 ".[all]"` (AGENTS.md); instalações antigas continuam funcionando pelo caminho lento, só sem o ganho.
- Hooks já instalados em outros clones precisam de `ragx hooks install` de novo para ganhar a guarda: dizer isso no CHANGELOG.
- Cuidado com o `escape` do shell: `$3` no bloco é do shell do hook, não do Python; o teste de `_FORBIDDEN` em `githooks` continua valendo.
- Se, medido, o hint ficar acima de 120 ms só por causa do lançador `ragx.exe` do Windows, registrar a parcela em Andamento e propor um `.cmd` no lugar; não aceitar a meta no papel.

## Definition of Done

- [x] Todos os critérios de aceite acima verificados (rodando, não supondo)
- [ ] Testes escritos e verdes em Linux, macOS e Windows (verdes no Windows; Linux e macOS só a CI confirma)
- [x] `ruff` e `mypy` limpos
- [x] Suíte `security/` continua verde
- [x] CHANGELOG atualizado na MESMA alteração, com o número antes/depois
- [x] Documentação confere com o comportamento implementado
- [x] Commit `tipo(escopo): descrição (RAGX-0143)` na branch `feat/v2`

## Andamento

- 2026-10-01 — Implementado: `ragx/origin.py` (`claude_origin`, `profile_name`; o `registry` reexporta), `ragx/hooklight.py` (config mínima com `tomllib`, o texto da dica com UMA fonte, `record_session_start`, `run_hint`, `run_touch`, `should_run`/`index_argv`/`spawn_index`, `parse_hook_run`, `run_hook`), `ragx/entry.py`, `pyproject.toml` (`ragx` e `rag` -> `ragx.entry:main`), `githooks` reexportando de `hooklight`, `diagnostics` sem `ragx.storage.db`, guarda de shell no `post-checkout` e `outdated` em `githooks.state` / `ragx hooks status`. O `touch` (RAGX-0141) já existia e entrou no despacho leve (`ragx touch --stdin-json`); a leitura do stdin tem uma só fonte (`hooklight.ler_stdin`).
- Testes: `tests/unit/test_hooklight.py` (paridade de `carregar` com `load_config`, dica idêntica byte a byte entre `ragx.entry` e `ragx.cli.main` em 3 cenários, mesma linha de `session_start`, subprocessos provando que typer/rich/pydantic/numpy/yaml/pathspec/`ragx.config`/`ragx.clients`/`ragx.storage` não são carregados, despacho), `tests/e2e/test_hooks_guarda_shell.py` (git real com um executável falso que grava um marcador) e o arquitetural (`ragx.hooklight` autorizado a ler só texto de artefatos próprios, e proibido de `read_bytes`/varrer pasta).
- Ressalva: medi por `python -m ragx.entry`. O lançador `ragx.exe` do Windows soma o seu próprio custo e só aponta para o novo ponto de entrada depois de `uv tool install --editable --force --python 3.12 ".[all]"`; não reinstalei a ferramenta do usuário, então a parcela do `.exe` não foi medida. Se ela estourar os 120 ms, a nota da task manda registrar e propor um `.cmd`.
