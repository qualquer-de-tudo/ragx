# Índice que acompanha a branch (Parte A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O índice de cada projeto registra de onde veio cada indexação (branch, commit, origem), publica o próprio estado em `.ragx/status.json`, sabe dizer se está defasado, se atualiza sozinho por hooks de git e nunca roda duas indexações ao mesmo tempo.

**Architecture:** Um módulo `ragx.gitinfo` concentra as chamadas ao `git`. `index_project` passa a receber `source`, grava a proveniência em `index_runs` (migração 0006), toma uma trava de arquivo (`.ragx/index.lock`) e reescreve `.ragx/status.json` no início e no fim. `ragx status --json` ganha `freshness` e `recent_runs`. `ragx hooks` instala blocos marcados nos hooks do git que chamam o comando oculto `ragx hook-run`, que dispara `ragx index --source hook:<evento>` destacado.

**Tech Stack:** Python 3.12, Typer, SQLite (migrações SQL numeradas), pytest, `git` via `subprocess`.

**Spec:** `docs/superpowers/specs/2026-09-23-painel-v2-indice-por-branch-design.md` (Parte A)

## Global Constraints

- Leia `docs/02-seguranca.md` antes de mexer em qualquer coisa que leia arquivo do projeto. Nada desta parte lê CONTEÚDO de arquivo fora do pipeline existente; `gitinfo` só lê metadados do git e `stat` (mtime).
- Nenhum caminho de arquivo sai em `freshness` nem em `status.json`: só contagens. Motivo já registrado no código (`mcp/operations.py`): a lista de arquivos é um mapa de onde estão os segredos.
- `ragx.mcp` continua casca fina (ADR-0006): nada de `os`, `pathlib`, `subprocess` em `mcp/operations.py`, `mcp/tools.py`, `mcp/orchestration.py`. Só passar strings de origem.
- Falha de embedder continua não fatal (ADR-0004).
- Toda chamada ao `git` tem `timeout=5`, `capture_output=True`, `text=True`, `encoding="utf-8"`, `errors="replace"` e nunca lança: sem git ou fora de repo devolve `None`.
- Origens válidas (valores exatos): `cli`, `panel`, `watch`, `sync`, `mcp:refresh`, `mcp:index`, `hook:post-checkout`, `hook:post-commit`, `hook:post-merge`.
- Eventos de hook (valores exatos): `post-checkout`, `post-commit`, `post-merge`.
- Marcadores de hook: `# ragx-hook-start <raiz em posix>` e `# ragx-hook-end <raiz em posix>`; opt-out por `RAGX_SKIP_HOOK=1`.
- Datas em UTC no formato de `ragx.storage.db.utcnow()` (`%Y-%m-%dT%H:%M:%SZ`).
- Textos novos em português, sem travessão (—) em mensagens novas.
- Commits `tipo(escopo): descrição` em português, terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- CHANGELOG `[Não lançado]` atualizado na mesma branch (Task 7).
- Testes: `uv run pytest -m "not slow"`, `uv run ruff check .`, `uv run mypy src/ragx/core src/ragx/security`. CI roda Windows, Linux e macOS: nada de path com `\` fixo, nada de `os.kill(pid, 0)` no Windows (mata o processo).

**Ruling registrado no plano:** a spec fala em `ragx init --hooks`; `docs/14-cli.md` já promete `ragx init --git-hooks`. Documentação é contrato neste repo (ver `cli/main.py::_root`), então a flag é `--git-hooks`.

## Review Focus

- Projeto que é subpasta de um repositório git (ex.: `hns/backend/src`): `git status --porcelain` devolve caminhos relativos à raiz do REPO; é preciso descontar o `--show-prefix` e ignorar o que está fora da raiz do projeto. Teste na Task 4.
- Raiz de projeto com espaço no caminho (comum no Windows: `C:\Users\Fulano Silva\...`): o hook precisa citar o caminho. Raiz com `"`, `` ` ``, `$` ou `\n` é recusada na instalação (injeção no shell do hook). Teste na Task 5.
- Hook já existente de outra ferramenta (husky, graphify): instalar acrescenta o bloco sem apagar nada; desinstalar remove só o bloco deste projeto e apaga o arquivo só se sobrar apenas o shebang. Teste na Task 5.
- Trava deixada por processo morto (queda, kill): a próxima indexação assume a trava em vez de ficar "ocupado" para sempre. No Windows a checagem de pid usa `OpenProcess`, nunca `os.kill`. Teste na Task 2.
- HEAD destacado (rebase, checkout de tag): `branch` vira `None`, o commit continua registrado e a defasagem não quebra. Teste na Task 1 e Task 4.

---

## File Structure

- Create `src/ragx/gitinfo.py`: estado do git de uma raiz (branch, commit, sujo), contagem de commits, alterações não commitadas, pasta de hooks.
- Create `src/ragx/storage/migrations/0006_run_provenance.sql`: colunas novas em `index_runs`.
- Modify `src/ragx/storage/repositories.py` (`RunRepo`): `start` com origem e git, `recent`.
- Create `src/ragx/indexing/lock.py`: trava de arquivo, pendência, pid vivo.
- Create `src/ragx/indexing/status_file.py`: monta e grava `.ragx/status.json` de forma atômica.
- Create `src/ragx/indexing/freshness.py`: calcula `freshness`.
- Modify `src/ragx/indexing/pipeline.py`: `index_project` com `source`, `wait_s`, `on_event`, trava, reexecução pendente, status.json; `status()` com `freshness` e `recent_runs`.
- Create `src/ragx/githooks.py`: instalar, remover e inspecionar blocos de hook; disparar indexação destacada.
- Create `src/ragx/cli/commands/hooks_cmd.py`: `ragx hooks install|uninstall|status` e `ragx hook-run`.
- Modify `src/ragx/cli/commands/index_cmd.py`: `--source`, `--progress`, espera de 30 s na origem `cli`, linha de defasagem no `ragx status`.
- Modify `src/ragx/cli/commands/init.py`: `--git-hooks`.
- Modify `src/ragx/cli/main.py`: registra `hooks` e `hook-run`.
- Modify `src/ragx/watch/monitor.py`, `src/ragx/mcp/operations.py`, `src/ragx/sync/service.py`: passam a origem.
- Modify `src/ragx/core/errors.py`: `IndexBusyError`.
- Docs: `docs/03-modelo-de-dados.md`, `docs/12-git-sync.md`, `docs/14-cli.md`, `CHANGELOG.md`.

---

### Task 1: Proveniência de cada indexação

**Files:**
- Create: `src/ragx/gitinfo.py`
- Create: `src/ragx/storage/migrations/0006_run_provenance.sql`
- Modify: `src/ragx/storage/repositories.py` (classe `RunRepo`)
- Modify: `src/ragx/indexing/pipeline.py` (`index_project`)
- Test: `tests/unit/test_gitinfo.py`, `tests/integration/test_provenance.py`

**Interfaces:**
- Produces:
  - `ragx.gitinfo.GitState` (dataclass frozen): `branch: str | None`, `commit: str`, `dirty: bool`
  - `ragx.gitinfo.read_state(root: Path) -> GitState | None`
  - `ragx.gitinfo.git(root: Path, *args: str) -> str | None` (stdout sem `\n` final; `None` em erro, exit != 0, timeout ou git ausente)
  - `ragx.indexing.pipeline.VALID_SOURCES: frozenset[str]`
  - `RunRepo.start(mode: str, source: str = "cli", git: GitState | None = None) -> int`
  - `RunRepo.recent(limit: int = 10) -> list[dict[str, Any]]` (mais novo primeiro)
  - `index_project(..., source: str = "cli")`; `mode` gravado é `"full"`, `"incremental"` ou `"embed-only"`; `embedded` gravado no run é o número real de vetores gerados.

- [ ] **Step 1: Testes do gitinfo**

`tests/unit/test_gitinfo.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ragx import gitinfo


def _repo(root: Path) -> Path:
    if subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root).returncode != 0:
        pytest.skip("git indisponível")
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "c1"], cwd=root, check=True)
    return root


def test_fora_de_repo_devolve_none(tmp_path: Path) -> None:
    assert gitinfo.read_state(tmp_path) is None


def test_estado_limpo(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    st = gitinfo.read_state(root)
    assert st is not None
    assert st.branch == "main"
    assert len(st.commit) == 40
    assert st.dirty is False


def test_estado_sujo(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "a.txt").write_text("b\n", encoding="utf-8")
    st = gitinfo.read_state(root)
    assert st is not None and st.dirty is True


def test_head_destacado_tem_branch_none(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    head = gitinfo.git(root, "rev-parse", "HEAD")
    subprocess.run(["git", "checkout", "-q", "--detach", head], cwd=root, check=True)
    st = gitinfo.read_state(root)
    assert st is not None and st.branch is None and st.commit == head


def test_repo_sem_commit_devolve_none(tmp_path: Path) -> None:
    if subprocess.run(["git", "init", "-q"], cwd=tmp_path).returncode != 0:
        pytest.skip("git indisponível")
    assert gitinfo.read_state(tmp_path) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/test_gitinfo.py -q`
Expected: FAIL com `ImportError`/`AttributeError` (módulo inexistente).

- [ ] **Step 3: Implementar `src/ragx/gitinfo.py`**

```python
"""Metadados do git de uma raiz de projeto.

Só metadados: branch, commit, estado do working tree, pasta de hooks. Nada
aqui lê conteúdo de arquivo do projeto; quem lê conteúdo é o pipeline, depois
do Security Gate (docs/02-seguranca.md).

Nenhuma função lança: sem git instalado, fora de repositório ou com timeout,
a resposta é `None`. Um índice que não sabe a branch continua funcionando.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

_TIMEOUT_S = 5


@dataclass(frozen=True)
class GitState:
    branch: str | None  # None com HEAD destacado
    commit: str
    dirty: bool


def git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.rstrip("\n")


def read_state(root: Path) -> GitState | None:
    commit = git(root, "rev-parse", "HEAD")
    if not commit:
        return None
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    porcelain = git(root, "status", "--porcelain", "--untracked-files=normal", "--", ".")
    return GitState(branch=branch or None, commit=commit, dirty=bool(porcelain))
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/test_gitinfo.py -q`
Expected: PASS (5 testes; `skip` se não houver git).

- [ ] **Step 5: Teste de integração da proveniência**

`tests/integration/test_provenance.py`:

```python
from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project

pytestmark = pytest.mark.integration


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


def _last_run(root: Path) -> sqlite3.Row:
    conn = sqlite3.connect(root / ".ragx" / "knowledge.db")
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM index_runs ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()


def test_sem_git_grava_origem_e_git_nulo(proj: Path) -> None:
    index_project(load_config(proj), source="panel")
    run = _last_run(proj)
    assert run["source"] == "panel"
    assert run["git_branch"] is None and run["git_commit"] is None and run["git_dirty"] is None


def test_com_git_grava_branch_e_commit(proj: Path) -> None:
    if subprocess.run(["git", "init", "-q", "-b", "feat/x"], cwd=proj).returncode != 0:
        pytest.skip("git indisponível")
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=proj, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=proj, check=True)
    subprocess.run(["git", "add", "-A"], cwd=proj, check=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=proj, check=True)
    index_project(load_config(proj))
    run = _last_run(proj)
    assert run["source"] == "cli"
    assert run["git_branch"] == "feat/x"
    assert len(run["git_commit"]) == 40
    assert run["git_dirty"] in (0, 1)


def test_embed_only_tem_modo_proprio_e_conta_vetores(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg, embed=False)
    index_project(cfg, embed_only=True)
    run = _last_run(proj)
    assert run["mode"] == "embed-only"
    assert run["embedded"] > 0


def test_origem_invalida_e_recusada(proj: Path) -> None:
    from ragx.core.errors import UsageError

    with pytest.raises(UsageError):
        index_project(load_config(proj), source="qualquer")


def test_recent_devolve_mais_novo_primeiro(proj: Path) -> None:
    from ragx.storage.db import open_db
    from ragx.storage.repositories import RunRepo

    cfg = load_config(proj)
    index_project(cfg, source="cli")
    index_project(cfg, source="watch")
    with open_db(cfg.db_path) as conn:
        runs = RunRepo(conn).recent(10)
    assert [r["source"] for r in runs[:2]] == ["watch", "cli"]
```

- [ ] **Step 6: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_provenance.py -q`
Expected: FAIL (`index_project() got an unexpected keyword argument 'source'`).

- [ ] **Step 7: Migração**

`src/ragx/storage/migrations/0006_run_provenance.sql`:

```sql
-- Proveniência de cada indexação: de qual branch/commit e quem disparou.
-- Ver docs/03-modelo-de-dados.md e docs/12-git-sync.md.

ALTER TABLE index_runs ADD COLUMN git_branch TEXT;
ALTER TABLE index_runs ADD COLUMN git_commit TEXT;
ALTER TABLE index_runs ADD COLUMN git_dirty  INTEGER;
ALTER TABLE index_runs ADD COLUMN source     TEXT NOT NULL DEFAULT 'cli';
```

- [ ] **Step 8: `RunRepo`**

Em `src/ragx/storage/repositories.py`, substituir `RunRepo.start` e acrescentar `recent` (import `GitState` sob `TYPE_CHECKING` para não criar ciclo):

```python
    def start(self, mode: str, source: str = "cli", git: GitState | None = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO index_runs(started_at, mode, source, git_branch, git_commit, git_dirty)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                utcnow(), mode, source,
                git.branch if git else None,
                git.commit if git else None,
                (1 if git.dirty else 0) if git else None,
            ),
        )
        return int(cur.lastrowid or 0)

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM index_runs ORDER BY id DESC LIMIT ?", (limit,)
            )
        ]
```

No topo do arquivo:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ragx.gitinfo import GitState
```

- [ ] **Step 9: `index_project` com origem**

Em `src/ragx/indexing/pipeline.py`:

1. Acrescentar abaixo dos imports:

```python
VALID_SOURCES = frozenset({
    "cli", "panel", "watch", "sync", "mcp:refresh", "mcp:index",
    "hook:post-checkout", "hook:post-commit", "hook:post-merge",
})
```

2. Nova assinatura: acrescentar `source: str = "cli"` ao final dos parâmetros de `index_project`. Primeira linha do corpo:

```python
    if source not in VALID_SOURCES:
        raise UsageError(f"origem desconhecida: {source}")
```

(`from ragx.core.errors import UsageError`, `from ragx import gitinfo`.)

3. Trocar a linha `run_id = None if dry_run else runs.start(...)` por:

```python
        mode = "embed-only" if embed_only else ("full" if full else "incremental")
        run_id = None if dry_run else runs.start(mode, source, gitinfo.read_state(cfg.root))
```

4. No `runs.finish(...)` do `finally`, trocar `"embedded": 0,` por `"embedded": report.stats.embedded,`.

- [ ] **Step 10: Rodar e ver passar, junto com a suíte do pipeline**

Run: `uv run pytest tests/integration/test_provenance.py tests/integration/test_pipeline.py tests/unit/test_gitinfo.py -q`
Expected: PASS. `test_run_e_registrado` continua passando (`mode == "incremental"`).

- [ ] **Step 11: Suíte rápida, lint, commit**

Run: `uv run pytest -m "not slow" -q && uv run ruff check .`
Expected: tudo verde.

```bash
git add src/ragx/gitinfo.py src/ragx/storage/migrations/0006_run_provenance.sql src/ragx/storage/repositories.py src/ragx/indexing/pipeline.py tests/unit/test_gitinfo.py tests/integration/test_provenance.py
git commit -m "feat(index): registra branch, commit e origem de cada indexacao

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Trava entre processos e reexecução pendente

**Files:**
- Create: `src/ragx/indexing/lock.py`
- Modify: `src/ragx/core/errors.py`
- Modify: `src/ragx/indexing/pipeline.py`
- Test: `tests/unit/test_index_lock.py`, `tests/integration/test_index_lock_pipeline.py`

**Interfaces:**
- Consumes: `index_project(..., source)` da Task 1.
- Produces:
  - `ragx.core.errors.IndexBusyError(RagxError)`, `exit_code = 3`, atributos `holder: dict[str, Any]` (conteúdo da trava) e mensagem em português.
  - `ragx.indexing.lock.LOCK_NAME = "index.lock"`, `PENDING_NAME = "index.pending"`
  - `ragx.indexing.lock.pid_alive(pid: int) -> bool`
  - `ragx.indexing.lock.try_acquire(state_dir: Path, op: str, source: str) -> bool` (cria a trava com `O_CREAT|O_EXCL`; assume trava de pid morto ou ilegível)
  - `ragx.indexing.lock.release(state_dir: Path) -> None`
  - `ragx.indexing.lock.holder(state_dir: Path) -> dict[str, Any] | None` (`{"pid", "op", "source", "started_at"}`)
  - `ragx.indexing.lock.mark_pending(state_dir: Path, source: str) -> None`
  - `ragx.indexing.lock.take_pending(state_dir: Path) -> str | None` (lê e apaga; devolve a origem pedida)
  - `ragx.indexing.lock.is_pending(state_dir: Path) -> bool`
  - `index_project(..., wait_s: float = 0.0)`: tenta a trava a cada 0,5 s até `wait_s`; sem trava, chama `mark_pending` e lança `IndexBusyError`. Com a trava, roda; ao terminar, enquanto `take_pending` devolver origem e rodadas extras < 3, roda de novo em modo incremental com aquela origem. `dry_run` não usa trava.

- [ ] **Step 1: Testes unitários da trava**

`tests/unit/test_index_lock.py`:

```python
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ragx.indexing import lock


def test_segunda_tentativa_falha_enquanto_a_primeira_segura(tmp_path: Path) -> None:
    assert lock.try_acquire(tmp_path, "index", "cli") is True
    assert lock.try_acquire(tmp_path, "index", "hook:post-commit") is False
    h = lock.holder(tmp_path)
    assert h is not None and h["pid"] == os.getpid() and h["source"] == "cli"
    lock.release(tmp_path)
    assert lock.holder(tmp_path) is None
    assert lock.try_acquire(tmp_path, "index", "panel") is True
    lock.release(tmp_path)


def test_trava_de_processo_morto_e_assumida(tmp_path: Path) -> None:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    (tmp_path / lock.LOCK_NAME).write_text(
        json.dumps({"pid": p.pid, "op": "index", "source": "cli", "started_at": "x"}),
        encoding="utf-8",
    )
    assert lock.pid_alive(p.pid) is False
    assert lock.try_acquire(tmp_path, "index", "panel") is True
    assert lock.holder(tmp_path)["pid"] == os.getpid()
    lock.release(tmp_path)


def test_trava_ilegivel_e_assumida(tmp_path: Path) -> None:
    (tmp_path / lock.LOCK_NAME).write_text("lixo", encoding="utf-8")
    assert lock.try_acquire(tmp_path, "index", "cli") is True
    lock.release(tmp_path)


def test_pid_do_proprio_processo_esta_vivo() -> None:
    assert lock.pid_alive(os.getpid()) is True


def test_pendencia_guarda_a_ultima_origem_e_e_consumida(tmp_path: Path) -> None:
    assert lock.take_pending(tmp_path) is None
    lock.mark_pending(tmp_path, "hook:post-commit")
    lock.mark_pending(tmp_path, "hook:post-checkout")
    assert lock.is_pending(tmp_path) is True
    assert lock.take_pending(tmp_path) == "hook:post-checkout"
    assert lock.is_pending(tmp_path) is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/test_index_lock.py -q`
Expected: FAIL (módulo inexistente).

- [ ] **Step 3: Implementar `src/ragx/indexing/lock.py`**

```python
"""Trava entre processos para indexação.

Hooks de git, watcher, MCP, painel e CLI podem disparar indexação ao mesmo
tempo; dois escritores no mesmo banco já produziram `FOREIGN KEY constraint
failed`. Uma trava de arquivo criada com O_EXCL resolve sem dependência nova.

Quem chega com a trava ocupada deixa um pedido em `index.pending`; quem segura
a trava roda de novo ao terminar. Assim nenhum commit fica sem reindexação.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from ragx.storage.db import utcnow

LOCK_NAME = "index.lock"
PENDING_NAME = "index.pending"


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # os.kill(pid, 0) no Windows chama TerminateProcess: mataria o processo.
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return kernel32.GetLastError() == 5  # acesso negado: existe
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def holder(state_dir: Path) -> dict[str, Any] | None:
    try:
        data = json.loads((state_dir / LOCK_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _create(path: Path, payload: str) -> bool:
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(payload)
    return True


def try_acquire(state_dir: Path, op: str, source: str) -> bool:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / LOCK_NAME
    payload = json.dumps(
        {"pid": os.getpid(), "op": op, "source": source, "started_at": utcnow()}
    )
    if _create(path, payload):
        return True
    current = holder(state_dir)
    pid = current.get("pid") if current else None
    if isinstance(pid, int) and pid_alive(pid):
        return False
    # Dono morto ou arquivo ilegível: assume.
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return _create(path, payload)


def release(state_dir: Path) -> None:
    current = holder(state_dir)
    if current and current.get("pid") not in (os.getpid(), None):
        return
    try:
        (state_dir / LOCK_NAME).unlink()
    except FileNotFoundError:
        pass


def mark_pending(state_dir: Path, source: str) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    tmp = state_dir / f"{PENDING_NAME}.{os.getpid()}.tmp"
    tmp.write_text(source, encoding="utf-8")
    os.replace(tmp, state_dir / PENDING_NAME)


def is_pending(state_dir: Path) -> bool:
    return (state_dir / PENDING_NAME).exists()


def take_pending(state_dir: Path) -> str | None:
    path = state_dir / PENDING_NAME
    try:
        source = path.read_text(encoding="utf-8").strip()
        path.unlink()
    except OSError:
        return None
    return source or "cli"
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/unit/test_index_lock.py -q`
Expected: PASS.

- [ ] **Step 5: `IndexBusyError`**

Em `src/ragx/core/errors.py`, ao final:

```python
class IndexBusyError(RagxError):
    """Outra indexação segura a trava; o pedido ficou agendado."""

    exit_code = 3

    def __init__(self, holder: dict[str, object] | None):
        self.holder = holder or {}
        who = self.holder.get("source", "outra origem")
        pid = self.holder.get("pid", "?")
        super().__init__(
            f"outra indexação está rodando (origem {who}, pid {pid}). "
            "Este pedido ficou agendado e roda quando ela terminar."
        )
```

- [ ] **Step 6: Teste de integração da trava no pipeline**

`tests/integration/test_index_lock_pipeline.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.core.errors import IndexBusyError
from ragx.indexing import lock
from ragx.indexing.pipeline import index_project

pytestmark = pytest.mark.integration


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


def _sources(root: Path) -> list[str]:
    conn = sqlite3.connect(root / ".ragx" / "knowledge.db")
    try:
        return [r[0] for r in conn.execute("SELECT source FROM index_runs ORDER BY id")]
    finally:
        conn.close()


def test_ocupado_agenda_e_lanca(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_config(proj)
    monkeypatch.setattr(lock, "pid_alive", lambda pid: True)
    (cfg.state_dir).mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / lock.LOCK_NAME).write_text(
        '{"pid": 999999, "op": "index", "source": "watch", "started_at": "x"}', encoding="utf-8"
    )
    with pytest.raises(IndexBusyError) as exc:
        index_project(cfg, source="hook:post-commit")
    assert exc.value.holder["source"] == "watch"
    assert lock.is_pending(cfg.state_dir)


def test_pendencia_faz_o_dono_rodar_de_novo(proj: Path) -> None:
    cfg = load_config(proj)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    lock.mark_pending(cfg.state_dir, "hook:post-merge")
    index_project(cfg, source="cli")
    assert _sources(proj) == ["cli", "hook:post-merge"]
    assert not lock.is_pending(cfg.state_dir)
    assert lock.holder(cfg.state_dir) is None


def test_trava_e_liberada_mesmo_com_erro(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ragx.indexing.pipeline as pipeline

    cfg = load_config(proj)

    def boom(*a: object, **k: object) -> None:
        raise RuntimeError("falhou")

    monkeypatch.setattr(pipeline, "_index_once", boom)
    with pytest.raises(RuntimeError):
        index_project(cfg)
    assert lock.holder(cfg.state_dir) is None


def test_dry_run_nao_toca_na_trava(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = load_config(proj)
    monkeypatch.setattr(lock, "try_acquire", lambda *a: pytest.fail("dry-run pegou a trava"))
    index_project(cfg, dry_run=True)
```

- [ ] **Step 7: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_index_lock_pipeline.py -q`
Expected: FAIL.

- [ ] **Step 8: Trava em `index_project`**

Em `src/ragx/indexing/pipeline.py`: renomear o corpo atual de `index_project` para `_index_once(cfg, full, dry_run, progress, embed, embed_only, source)` (mesmo código, sem a validação de origem). Escrever o novo `index_project`:

```python
MAX_PENDING_RERUNS = 3


def index_project(
    cfg: Config,
    full: bool = False,
    dry_run: bool = False,
    progress: Callable[[int, str], None] | None = None,
    embed: bool = True,
    embed_only: bool = False,
    source: str = "cli",
    wait_s: float = 0.0,
) -> IndexReport:
    if source not in VALID_SOURCES:
        raise UsageError(f"origem desconhecida: {source}")
    if dry_run:
        return _index_once(cfg, full, dry_run, progress, embed, embed_only, source)

    state_dir = cfg.state_dir
    deadline = time.monotonic() + max(wait_s, 0.0)
    while not lock.try_acquire(state_dir, "index", source):
        if time.monotonic() >= deadline:
            current = lock.holder(state_dir)
            lock.mark_pending(state_dir, source)
            raise IndexBusyError(current)
        time.sleep(0.5)

    try:
        report = _index_once(cfg, full, dry_run, progress, embed, embed_only, source)
        for _ in range(MAX_PENDING_RERUNS):
            pending = lock.take_pending(state_dir)
            if pending is None:
                break
            _index_once(cfg, False, False, None, True, False,
                        pending if pending in VALID_SOURCES else "cli")
        return report
    finally:
        lock.release(state_dir)
```

Imports: `from ragx.indexing import lock`, `from ragx.core.errors import IndexBusyError, UsageError`.

- [ ] **Step 9: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_index_lock_pipeline.py tests/integration/test_provenance.py tests/integration/test_pipeline.py tests/unit/test_index_lock.py -q`
Expected: PASS.

- [ ] **Step 10: Suíte rápida, lint, commit**

Run: `uv run pytest -m "not slow" -q && uv run ruff check .`

```bash
git add src/ragx/indexing/lock.py src/ragx/core/errors.py src/ragx/indexing/pipeline.py tests/unit/test_index_lock.py tests/integration/test_index_lock_pipeline.py
git commit -m "feat(index): trava entre processos com reexecucao do pedido pendente

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `.ragx/status.json`

**Files:**
- Create: `src/ragx/indexing/status_file.py`
- Modify: `src/ragx/indexing/pipeline.py`
- Test: `tests/integration/test_status_file.py`

**Interfaces:**
- Consumes: `lock.holder`, `lock.is_pending` (Task 2); `RunRepo.recent` (Task 1).
- Produces:
  - `ragx.indexing.status_file.STATUS_NAME = "status.json"`, `SCHEMA = 1`
  - `ragx.indexing.status_file.write_status(cfg: Config, *, last_error: str | None = None) -> Path | None` (não lança; `None` se não há banco ou se a escrita falhou)
  - `ragx.indexing.status_file.hooks_installed_probe: Callable[[Path], bool | None]` (variável de módulo, padrão devolve `None`; a Task 5 a substitui por `githooks.installed` via import tardio. Ver Step 3.)
  - Formato do arquivo (chaves exatas):

```json
{
  "schema_version": 1,
  "written_at": "2026-09-23T12:00:00Z",
  "project": {"id": "t", "name": "t", "root": "C:/x/t"},
  "index": {"finished_at": "...", "mode": "incremental", "source": "cli",
            "branch": "main", "commit": "abc...", "dirty": false},
  "counts": {"documents": 4, "chunks": 10, "embeddings": 10, "pending_embeddings": 0},
  "embedding": {"provider": "ollama", "model": "nomic-embed-text"},
  "hooks": {"installed": null},
  "running": null,
  "pending": false,
  "last_error": null
}
```

  `index` é o último run COM `finished_at` (ou `null` se não há nenhum). `running` é `lock.holder(...)` quando o pid está vivo, senão `null`. `last_error` é o argumento ou, se omitido, o `error` do último run terminado. `dirty` sai como booleano ou `null`. `root` sai em posix.

- [ ] **Step 1: Teste**

`tests/integration/test_status_file.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing import lock
from ragx.indexing.pipeline import index_project
from ragx.indexing.status_file import STATUS_NAME, write_status

pytestmark = pytest.mark.integration


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "demo"\nid = "demo-id"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


def _read(root: Path) -> dict:
    return json.loads((root / ".ragx" / STATUS_NAME).read_text(encoding="utf-8"))


def test_indexar_grava_o_status(proj: Path) -> None:
    index_project(load_config(proj), source="panel")
    st = _read(proj)
    assert st["schema_version"] == 1
    assert st["project"] == {"id": "demo-id", "name": "demo", "root": proj.as_posix()}
    assert st["index"]["source"] == "panel"
    assert st["index"]["mode"] == "incremental"
    assert st["index"]["finished_at"]
    assert st["counts"]["chunks"] > 0
    assert st["counts"]["embeddings"] == st["counts"]["chunks"]
    assert st["counts"]["pending_embeddings"] == 0
    assert st["embedding"]["provider"] == "hashing"
    assert st["running"] is None and st["pending"] is False and st["last_error"] is None


def test_sem_embeddings_conta_pendentes(proj: Path) -> None:
    index_project(load_config(proj), embed=False)
    st = _read(proj)
    assert st["counts"]["embeddings"] == 0
    assert st["counts"]["pending_embeddings"] == st["counts"]["chunks"]


def test_status_mostra_quem_esta_rodando(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    assert lock.try_acquire(cfg.state_dir, "index", "watch")
    try:
        write_status(cfg)
        st = _read(proj)
        assert st["running"]["source"] == "watch"
    finally:
        lock.release(cfg.state_dir)


def test_status_nao_tem_caminho_de_arquivo(proj: Path) -> None:
    index_project(load_config(proj))
    assert "a.py" not in (proj / ".ragx" / STATUS_NAME).read_text(encoding="utf-8")


def test_sem_banco_nao_escreve(tmp_path: Path) -> None:
    (tmp_path / "ragx.toml").write_text('[project]\nname = "x"\nid = "x"\n', encoding="utf-8")
    assert write_status(load_config(tmp_path)) is None
    assert not (tmp_path / ".ragx" / STATUS_NAME).exists()


def test_escrita_e_atomica_nao_deixa_temporario(proj: Path) -> None:
    index_project(load_config(proj))
    leftovers = [p.name for p in (proj / ".ragx").iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_status_file.py -q`
Expected: FAIL (módulo inexistente).

- [ ] **Step 3: Implementar `src/ragx/indexing/status_file.py`**

```python
"""`.ragx/status.json`: o estado do índice num arquivo que qualquer um lê.

O painel e outras ferramentas leem este arquivo em vez de abrir o SQLite.
Escrita atômica (temporário + os.replace) para ninguém ler JSON pela metade.
Só contagens e metadados: nenhum caminho de arquivo do projeto.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ragx.config import Config
from ragx.indexing import lock
from ragx.storage.db import open_db, utcnow

STATUS_NAME = "status.json"
SCHEMA = 1


def _no_probe(_root: Path) -> bool | None:
    return None


# Substituída em ragx.githooks (Task 5). Indireção para não importar o módulo
# de hooks, que conhece o shell, a partir do pipeline.
hooks_installed_probe: Callable[[Path], bool | None] = _no_probe


def _last_finished(conn: Any) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM index_runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def _build(cfg: Config, conn: Any, last_error: str | None) -> dict[str, Any]:
    run = _last_finished(conn)
    documents = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    embeddings = conn.execute(
        "SELECT COUNT(DISTINCT chunk_id) FROM embeddings"
    ).fetchone()[0]
    current = lock.holder(cfg.state_dir)
    pid = current.get("pid") if current else None
    running = current if isinstance(pid, int) and lock.pid_alive(pid) else None
    dirty = run.get("git_dirty") if run else None
    return {
        "schema_version": SCHEMA,
        "written_at": utcnow(),
        "project": {
            "id": cfg.project.id,
            "name": cfg.project.name,
            "root": cfg.root.as_posix(),
        },
        "index": None if run is None else {
            "finished_at": run["finished_at"],
            "mode": run["mode"],
            "source": run.get("source", "cli"),
            "branch": run.get("git_branch"),
            "commit": run.get("git_commit"),
            "dirty": None if dirty is None else bool(dirty),
        },
        "counts": {
            "documents": documents,
            "chunks": chunks,
            "embeddings": embeddings,
            "pending_embeddings": max(chunks - embeddings, 0),
        },
        "embedding": {"provider": cfg.embedding.provider, "model": cfg.embedding.model},
        "hooks": {"installed": hooks_installed_probe(cfg.root)},
        "running": running,
        "pending": lock.is_pending(cfg.state_dir),
        "last_error": last_error if last_error is not None else (run or {}).get("error"),
    }


def write_status(cfg: Config, *, last_error: str | None = None) -> Path | None:
    if not Path(cfg.db_path).exists():
        return None
    try:
        with open_db(cfg.db_path, read_only=True) as conn:
            data = _build(cfg, conn, last_error)
        target = cfg.state_dir / STATUS_NAME
        tmp = cfg.state_dir / f"{STATUS_NAME}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
        return target
    except Exception:
        # Status é informativo: nunca derruba uma indexação.
        return None
```

- [ ] **Step 4: Ligar no pipeline**

Em `index_project` (Task 2), logo depois de adquirir a trava e antes do `try`, e de novo no `finally` DEPOIS de `lock.release`:

```python
    status_file.write_status(cfg)          # depois do while da trava: mostra "running"
    try:
        ...
    finally:
        lock.release(state_dir)
        status_file.write_status(cfg)      # estado final, running = null
```

Em `IndexBusyError` (dentro do `while`, logo após `lock.mark_pending`), chamar `status_file.write_status(cfg)` antes do `raise`, para `pending: true` aparecer.

Import: `from ragx.indexing import lock, status_file`.

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_status_file.py tests/integration/test_index_lock_pipeline.py tests/integration/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 6: Suíte rápida, lint, mypy, commit**

Run: `uv run pytest -m "not slow" -q && uv run ruff check . && uv run mypy src/ragx/core src/ragx/security`

```bash
git add src/ragx/indexing/status_file.py src/ragx/indexing/pipeline.py tests/integration/test_status_file.py
git commit -m "feat(index): publica o estado do indice em .ragx/status.json

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Defasagem em `ragx status --json`

**Files:**
- Create: `src/ragx/indexing/freshness.py`
- Modify: `src/ragx/gitinfo.py` (duas funções novas)
- Modify: `src/ragx/indexing/pipeline.py` (`status()`)
- Modify: `src/ragx/cli/commands/index_cmd.py` (`status`, saída humana)
- Test: `tests/integration/test_freshness.py`

**Interfaces:**
- Consumes: `gitinfo.git`, `gitinfo.read_state`, `RunRepo.recent`.
- Produces:
  - `gitinfo.commits_between(root: Path, old: str, new: str) -> int | None`
  - `gitinfo.changed_paths(root: Path) -> list[str] | None`: caminhos do `git status --porcelain -z --untracked-files=all -- .` RELATIVOS À RAIZ DO PROJETO (desconta `rev-parse --show-prefix`), em posix; renomeações entram pelo nome novo; `None` fora de repo.
  - `ragx.indexing.freshness.compute(cfg: Config, conn, last_run: dict | None) -> dict[str, Any]` com o formato:

```json
{
  "state": "fresh | stale | unknown",
  "current": {"branch": "main", "commit": "abc...", "dirty": false},
  "reasons": [
    {"kind": "branch_changed", "indexed": "main", "current": "feat/x"},
    {"kind": "commits_since_index", "count": 3},
    {"kind": "uncommitted_changes", "count": 2},
    {"kind": "pending_embeddings", "count": 120}
  ]
}
```

  Regras:
  - `last_run` é o último run com `finished_at`. Sem ele: `state = "unknown"`, `reasons = []`, `current` preenchido se houver git.
  - `branch_changed` quando `indexed branch != current branch` e as duas não são `None`.
  - `commits_since_index` quando o commit indexado difere do HEAD; `count` vem de `commits_between` (pode ser `null` se o commit indexado não existe mais, por exemplo após rebase).
  - `uncommitted_changes`: dos `changed_paths`, conta os que existem no disco com `mtime` maior que `finished_at`, MAIS os que não existem no disco mas ainda estão na tabela `documents` (arquivo apagado depois da indexação). Só a contagem sai.
  - `pending_embeddings` quando `chunks - chunks com embedding > 0`.
  - `state = "stale"` se há algum motivo; `"fresh"` se não há motivo e há git; `"unknown"` se não há git e nenhum motivo.
  - `status()` em `pipeline.py` ganha `"freshness": compute(...)` e `"recent_runs": RunRepo(conn).recent(10)`.

- [ ] **Step 1: Testes**

`tests/integration/test_freshness.py`:

```python
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project, status

pytestmark = pytest.mark.integration

TOML = (
    '[project]\nname = "t"\nid = "t"\n\n'
    '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n'
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(root: Path, sub: str = "") -> Path:
    if subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root).returncode != 0:
        pytest.skip("git indisponível")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    proj = root / sub if sub else root
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "ragx.toml").write_text(TOML, encoding="utf-8")
    (proj / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "fora.txt").write_text("x\n", encoding="utf-8")
    (root / ".gitignore").write_text(".ragx/\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "c1")
    return proj


def _kinds(fr: dict) -> dict[str, dict]:
    return {r["kind"]: r for r in fr["reasons"]}


def _touch_future(p: Path) -> None:
    t = time.time() + 5
    os.utime(p, (t, t))


def test_recem_indexado_esta_em_dia(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg)
    fr = status(cfg)["freshness"]
    assert fr["state"] == "fresh" and fr["reasons"] == []
    assert fr["current"]["branch"] == "main"


def test_troca_de_branch_deixa_defasado(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg)
    _git(proj, "checkout", "-qb", "feat/x")
    fr = status(cfg)["freshness"]
    assert fr["state"] == "stale"
    assert _kinds(fr)["branch_changed"] == {
        "kind": "branch_changed", "indexed": "main", "current": "feat/x",
    }


def test_commits_depois_do_indice(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "b.py").write_text("x = 1\n", encoding="utf-8")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "c2")
    assert _kinds(status(cfg)["freshness"])["commits_since_index"]["count"] == 1


def test_arquivo_alterado_sem_commit_conta_so_se_mais_novo(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    (proj / "a.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    cfg = load_config(proj)
    index_project(cfg)
    # Alterado ANTES da indexação: o índice já tem a versão nova.
    assert "uncommitted_changes" not in _kinds(status(cfg)["freshness"])
    _touch_future(proj / "a.py")
    fr = status(cfg)["freshness"]
    assert _kinds(fr)["uncommitted_changes"]["count"] == 1
    assert "a.py" not in str(fr)


def test_arquivo_apagado_depois_do_indice_conta(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "a.py").unlink()
    assert _kinds(status(cfg)["freshness"])["uncommitted_changes"]["count"] == 1


def test_projeto_em_subpasta_ignora_o_resto_do_repo(tmp_path: Path) -> None:
    proj = _repo(tmp_path, sub="backend/src")
    cfg = load_config(proj)
    index_project(cfg)
    fora = tmp_path / "fora.txt"
    fora.write_text("mudou\n", encoding="utf-8")
    _touch_future(fora)
    assert status(cfg)["freshness"]["state"] == "fresh"


def test_head_destacado_nao_quebra(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg)
    _git(proj, "checkout", "-q", "--detach")
    fr = status(cfg)["freshness"]
    assert fr["current"]["branch"] is None
    assert "branch_changed" not in _kinds(fr)


def test_embeddings_pendentes(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg, embed=False)
    fr = status(cfg)["freshness"]
    assert fr["state"] == "stale"
    assert _kinds(fr)["pending_embeddings"]["count"] > 0


def test_sem_git_e_sem_pendencia_e_desconhecido(tmp_path: Path) -> None:
    (tmp_path / "ragx.toml").write_text(TOML, encoding="utf-8")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    index_project(cfg)
    st = status(cfg)
    assert st["freshness"]["state"] == "unknown"
    assert st["freshness"]["current"] is None


def test_recent_runs_no_status(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    for _ in range(12):
        index_project(cfg)
    runs = status(cfg)["recent_runs"]
    assert len(runs) == 10
    assert runs[0]["git_branch"] == "main"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/integration/test_freshness.py -q`
Expected: FAIL (`KeyError: 'freshness'`).

- [ ] **Step 3: `gitinfo` ganha duas funções**

```python
def commits_between(root: Path, old: str, new: str) -> int | None:
    out = git(root, "rev-list", "--count", f"{old}..{new}")
    try:
        return int(out) if out is not None else None
    except ValueError:
        return None


def changed_paths(root: Path) -> list[str] | None:
    """Caminhos alterados, novos ou apagados sob a raiz, relativos a ela."""
    prefix = git(root, "rev-parse", "--show-prefix")
    raw = git(root, "status", "--porcelain", "-z", "--untracked-files=all", "--", ".")
    if prefix is None or raw is None:
        return None
    entries = raw.split("\0")
    out: list[str] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if "R" in code or "C" in code:
            i += 1  # o próximo item é o nome antigo
        if prefix and not path.startswith(prefix):
            continue
        out.append(path[len(prefix):])
    return out
```

Nota: `git()` faz `rstrip("\n")`, e com `-z` não há `\n` final; o último item vazio é descartado pelo `len(entry) < 4`.

- [ ] **Step 4: `src/ragx/indexing/freshness.py`**

```python
"""O índice está em dia com o working tree? Só contagens, nunca caminhos."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ragx import gitinfo
from ragx.config import Config


def _epoch(ts: str) -> float:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()


def _uncommitted(cfg: Config, conn: Any, finished_at: str) -> int | None:
    paths = gitinfo.changed_paths(cfg.root)
    if paths is None:
        return None
    # finished_at tem resolução de segundo (truncado). Sem a folga de 1 s, um
    # arquivo salvo no mesmo segundo do fim da indexação, e JÁ indexado,
    # contaria como alterado depois dela.
    limit = _epoch(finished_at) + 1.0
    count = 0
    for rel in paths:
        full = cfg.root / rel
        try:
            if full.stat().st_mtime > limit:
                count += 1
        except FileNotFoundError:
            known = conn.execute(
                "SELECT 1 FROM documents WHERE rel_path = ?", (rel,)
            ).fetchone()
            if known:
                count += 1
    return count


def compute(cfg: Config, conn: Any, last_run: dict[str, Any] | None) -> dict[str, Any]:
    state = gitinfo.read_state(cfg.root)
    current = None if state is None else {
        "branch": state.branch, "commit": state.commit, "dirty": state.dirty,
    }
    if last_run is None or not last_run.get("finished_at"):
        return {"state": "unknown", "current": current, "reasons": []}

    reasons: list[dict[str, Any]] = []
    if state is not None:
        old_branch = last_run.get("git_branch")
        if old_branch and state.branch and old_branch != state.branch:
            reasons.append(
                {"kind": "branch_changed", "indexed": old_branch, "current": state.branch}
            )
        old_commit = last_run.get("git_commit")
        if old_commit and old_commit != state.commit:
            reasons.append({
                "kind": "commits_since_index",
                "count": gitinfo.commits_between(cfg.root, old_commit, state.commit),
            })
        changed = _uncommitted(cfg, conn, last_run["finished_at"])
        if changed:
            reasons.append({"kind": "uncommitted_changes", "count": changed})

    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    embedded = conn.execute("SELECT COUNT(DISTINCT chunk_id) FROM embeddings").fetchone()[0]
    if chunks > embedded:
        reasons.append({"kind": "pending_embeddings", "count": chunks - embedded})

    if reasons:
        verdict = "stale"
    else:
        verdict = "fresh" if state is not None else "unknown"
    return {"state": verdict, "current": current, "reasons": reasons}
```

Granularidade: com a folga de 1 s, um arquivo salvo até 1 s depois do fim da indexação não conta como alterado; é aceitável, e o teste usa `+5 s`.

- [ ] **Step 5: `status()` em `pipeline.py`**

Dentro do `with open_db(...)` de `status()`, antes do `return`:

```python
        last_done = conn.execute(
            "SELECT * FROM index_runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        fresh = freshness.compute(cfg, conn, dict(last_done) if last_done else None)
```

e no dicionário devolvido: `"freshness": fresh, "recent_runs": runs.recent(10),`. Import: `from ragx.indexing import freshness`.

- [ ] **Step 6: Saída humana de `ragx status`**

Em `index_cmd.status`, depois do bloco de modelo e antes de "Por linguagem":

```python
    fr = st.get("freshness") or {}
    labels = {
        "branch_changed": lambda r: f"índice da branch {r['indexed']}, você está em {r['current']}",
        "commits_since_index": lambda r: f"{r['count'] if r['count'] is not None else 'alguns'} commit(s) depois da indexação",
        "uncommitted_changes": lambda r: f"{r['count']} arquivo(s) alterado(s) depois da indexação",
        "pending_embeddings": lambda r: f"{r['count']:,} chunk(s) sem embedding",
    }
    if fr.get("state") == "fresh":
        console.print("\n  [green]Em dia[/] com o working tree")
    elif fr.get("state") == "stale":
        console.print("\n  [yellow]Defasado[/]")
        for r in fr.get("reasons", []):
            console.print(f"    {labels[r['kind']](r)}")
```

Também: trocar `console.print(f"\n[bold]Índice[/] — {cfg.root}\n")` por `console.print(f"\n[bold]Índice[/] em {cfg.root}\n")` (texto visível novo não leva travessão).

- [ ] **Step 7: Rodar e ver passar**

Run: `uv run pytest tests/integration/test_freshness.py tests/integration/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 8: Suíte rápida, lint, commit**

Run: `uv run pytest -m "not slow" -q && uv run ruff check .`

```bash
git add src/ragx/gitinfo.py src/ragx/indexing/freshness.py src/ragx/indexing/pipeline.py src/ragx/cli/commands/index_cmd.py tests/integration/test_freshness.py
git commit -m "feat(status): diz se o indice esta defasado e por que

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `ragx hooks` e `ragx hook-run`

**Files:**
- Create: `src/ragx/githooks.py`
- Create: `src/ragx/cli/commands/hooks_cmd.py`
- Modify: `src/ragx/cli/main.py`
- Modify: `src/ragx/cli/commands/init.py` (`--git-hooks`)
- Modify: `src/ragx/gitinfo.py` (`hooks_dir`)
- Test: `tests/unit/test_githooks.py`, `tests/e2e/test_cli_hooks.py`

**Interfaces:**
- Consumes: `gitinfo.git`; `status_file.hooks_installed_probe`, `status_file.write_status`.
- Produces:
  - `gitinfo.hooks_dir(root: Path) -> Path | None` (`git rev-parse --git-path hooks`, resolvido contra `root`; respeita `core.hooksPath`)
  - `githooks.EVENTS = ("post-checkout", "post-commit", "post-merge")`
  - `githooks.command_prefix() -> str`: o executável a embutir, já citado para shell. `shutil.which("ragx")` em posix entre aspas; se não achar, `"<sys.executable em posix>" -m ragx.cli.main`.
  - `githooks.install(root: Path, prefix: str | None = None) -> list[Path]` (arquivos escritos). `UsageError` se não é repo git ou se a raiz tem `"`, `` ` ``, `$`, `\n` ou `\r`.
  - `githooks.uninstall(root: Path) -> list[Path]`
  - `githooks.state(root: Path) -> dict[str, Any]`: `{"hooks_dir": str | None, "events": {evento: bool}, "installed": bool}` (`installed` = os três eventos têm o bloco desta raiz).
  - `githooks.installed(root: Path) -> bool | None` (`None` fora de repo)
  - `githooks.should_run(event: str, args: list[str]) -> bool` (`post-checkout` só com `args[2] == "1"`; os outros sempre)
  - `githooks.spawn_index(root: Path, event: str) -> None`: dispara `index <root> --quiet --source hook:<evento>` destacado, com saída anexada a `<root>/.ragx/logs/hooks.log`.
  - CLI: `ragx hooks install [PATH]`, `ragx hooks uninstall [PATH]`, `ragx hooks status [PATH] [--json]`, `ragx hook-run <evento> --root PATH [ARGS...]` (oculto), `ragx init --git-hooks`.

Bloco escrito em cada hook (com `<ROOT>` = `root.resolve().as_posix()`, `<PREFIX>` = `command_prefix()`):

```sh
# ragx-hook-start <ROOT>
if [ "$RAGX_SKIP_HOOK" != "1" ]; then
  <PREFIX> hook-run <EVENTO> --root "<ROOT>" "$@" >/dev/null 2>&1 || true
fi
# ragx-hook-end <ROOT>
```

Arquivo novo começa com `#!/bin/sh\n`. No posix, `chmod 0o755`.

- [ ] **Step 1: Testes unitários**

`tests/unit/test_githooks.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ragx import githooks
from ragx.core.errors import UsageError

PREFIX = '"/opt/ragx/bin/ragx"'


def _repo(root: Path) -> Path:
    if subprocess.run(["git", "init", "-q"], cwd=root).returncode != 0:
        pytest.skip("git indisponível")
    return root


def _hook(root: Path, event: str) -> Path:
    return root / ".git" / "hooks" / event


def test_instala_os_tres_eventos(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    written = githooks.install(root, PREFIX)
    assert sorted(p.name for p in written) == sorted(githooks.EVENTS)
    body = _hook(root, "post-checkout").read_text(encoding="utf-8")
    assert body.startswith("#!/bin/sh\n")
    assert f"# ragx-hook-start {root.resolve().as_posix()}" in body
    assert "hook-run post-checkout" in body
    assert 'RAGX_SKIP_HOOK' in body
    assert githooks.state(root)["installed"] is True


def test_instalar_duas_vezes_nao_duplica(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    githooks.install(root, PREFIX)
    githooks.install(root, '"/outro/ragx"')
    body = _hook(root, "post-commit").read_text(encoding="utf-8")
    assert body.count("ragx-hook-start") == 1
    assert "/outro/ragx" in body


def test_preserva_hook_de_outra_ferramenta(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    hook = _hook(root, "post-commit")
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho outra-ferramenta\n", encoding="utf-8")
    githooks.install(root, PREFIX)
    assert "echo outra-ferramenta" in hook.read_text(encoding="utf-8")
    githooks.uninstall(root)
    body = hook.read_text(encoding="utf-8")
    assert "echo outra-ferramenta" in body and "ragx-hook-start" not in body


def test_desinstalar_apaga_arquivo_que_so_tinha_o_bloco(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    githooks.install(root, PREFIX)
    githooks.uninstall(root)
    assert not _hook(root, "post-merge").exists()
    assert githooks.state(root)["installed"] is False


def test_dois_projetos_no_mesmo_repo(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    a, b = root / "a", root / "b"
    a.mkdir()
    b.mkdir()
    githooks.install(a, PREFIX)
    githooks.install(b, PREFIX)
    body = _hook(root, "post-commit").read_text(encoding="utf-8")
    assert body.count("ragx-hook-start") == 2
    githooks.uninstall(a)
    assert githooks.installed(a) is False
    assert githooks.installed(b) is True


def test_raiz_com_espaco_fica_entre_aspas(tmp_path: Path) -> None:
    root = tmp_path / "Fulano Silva" / "proj"
    root.mkdir(parents=True)
    _repo(root)
    githooks.install(root, PREFIX)
    body = _hook(root, "post-commit").read_text(encoding="utf-8")
    assert f'--root "{root.resolve().as_posix()}"' in body


@pytest.mark.parametrize("bad", ['a"b', "a$b", "a`b"])
def test_raiz_com_caractere_de_shell_e_recusada(tmp_path: Path, bad: str) -> None:
    root = tmp_path / bad
    try:
        root.mkdir()
    except OSError:
        pytest.skip("sistema de arquivos não aceita o nome")
    _repo(root)
    with pytest.raises(UsageError):
        githooks.install(root, PREFIX)


def test_fora_de_repo_e_erro_de_uso(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        githooks.install(tmp_path, PREFIX)
    assert githooks.installed(tmp_path) is None


def test_respeita_core_hookspath(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    subprocess.run(["git", "config", "core.hooksPath", ".husky"], cwd=root, check=True)
    githooks.install(root, PREFIX)
    assert (root / ".husky" / "post-commit").exists()


@pytest.mark.parametrize(
    ("event", "args", "expected"),
    [
        ("post-checkout", ["a", "b", "1"], True),
        ("post-checkout", ["a", "b", "0"], False),
        ("post-checkout", [], False),
        ("post-commit", [], True),
        ("post-merge", ["0"], True),
    ],
)
def test_should_run(event: str, args: list[str], expected: bool) -> None:
    assert githooks.should_run(event, args) is expected
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/unit/test_githooks.py -q`
Expected: FAIL (módulo inexistente).

- [ ] **Step 3: `gitinfo.hooks_dir`**

```python
def hooks_dir(root: Path) -> Path | None:
    out = git(root, "rev-parse", "--git-path", "hooks")
    if not out:
        return None
    p = Path(out)
    return p if p.is_absolute() else (root / p).resolve()
```

- [ ] **Step 4: `src/ragx/githooks.py`**

```python
"""Hooks de git que mantêm o índice na branch em que você está.

Cada hook ganha um bloco marcado por raiz de projeto, então convive com hooks
de outras ferramentas e com mais de um projeto RAGX no mesmo repositório. O
bloco chama `ragx hook-run`, que dispara a indexação destacada e devolve o
terminal na hora. Opt-out por RAGX_SKIP_HOOK=1.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ragx import gitinfo
from ragx.core.errors import UsageError

EVENTS = ("post-checkout", "post-commit", "post-merge")
_SHEBANG = "#!/bin/sh\n"
_FORBIDDEN = ('"', "`", "$", "\n", "\r")


def _key(root: Path) -> str:
    return root.resolve().as_posix()


def _markers(root: Path) -> tuple[str, str]:
    k = _key(root)
    return f"# ragx-hook-start {k}", f"# ragx-hook-end {k}"


def command_prefix() -> str:
    exe = shutil.which("ragx")
    if exe:
        return f'"{Path(exe).as_posix()}"'
    return f'"{Path(sys.executable).as_posix()}" -m ragx.cli.main'


def _block(root: Path, event: str, prefix: str) -> str:
    start, end = _markers(root)
    return (
        f"{start}\n"
        'if [ "$RAGX_SKIP_HOOK" != "1" ]; then\n'
        f'  {prefix} hook-run {event} --root "{_key(root)}" "$@" >/dev/null 2>&1 || true\n'
        "fi\n"
        f"{end}\n"
    )


def _strip(text: str, root: Path) -> str:
    start, end = _markers(root)
    out: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        s = line.rstrip("\r\n")
        if s == start:
            skipping = True
            continue
        if skipping and s == end:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return "".join(out)


def _dir_or_error(root: Path) -> Path:
    d = gitinfo.hooks_dir(root)
    if d is None:
        raise UsageError(f"{root} não está dentro de um repositório git")
    return d


def install(root: Path, prefix: str | None = None) -> list[Path]:
    key = _key(root)
    if any(c in key for c in _FORBIDDEN):
        raise UsageError(
            "o caminho do projeto tem caractere que o shell do hook interpretaria "
            '(" ` $ ou quebra de linha); mova o projeto para instalar hooks'
        )
    d = _dir_or_error(root)
    d.mkdir(parents=True, exist_ok=True)
    prefix = prefix or command_prefix()
    written: list[Path] = []
    for event in EVENTS:
        path = d / event
        current = path.read_text(encoding="utf-8") if path.exists() else _SHEBANG
        body = _strip(current, root)
        if not body.endswith("\n"):
            body += "\n"
        path.write_text(body + _block(root, event, prefix), encoding="utf-8", newline="\n")
        if os.name != "nt":
            path.chmod(0o755)
        written.append(path)
    _refresh_status(root)
    return written


def uninstall(root: Path) -> list[Path]:
    d = _dir_or_error(root)
    touched: list[Path] = []
    for event in EVENTS:
        path = d / event
        if not path.exists():
            continue
        current = path.read_text(encoding="utf-8")
        body = _strip(current, root)
        if body == current:
            continue
        if body.strip() in ("", _SHEBANG.strip()):
            path.unlink()
        else:
            path.write_text(body, encoding="utf-8", newline="\n")
        touched.append(path)
    _refresh_status(root)
    return touched


def state(root: Path) -> dict[str, Any]:
    d = gitinfo.hooks_dir(root)
    start, _ = _markers(root)
    events: dict[str, bool] = {}
    for event in EVENTS:
        path = d / event if d else None
        events[event] = bool(
            path and path.exists() and start in path.read_text(encoding="utf-8")
        )
    return {
        "hooks_dir": d.as_posix() if d else None,
        "events": events,
        "installed": bool(d) and all(events.values()),
    }


def installed(root: Path) -> bool | None:
    if gitinfo.hooks_dir(root) is None:
        return None
    return bool(state(root)["installed"])


def should_run(event: str, args: list[str]) -> bool:
    if event == "post-checkout":
        # args: HEAD anterior, HEAD novo, flag (1 = troca de branch, 0 = arquivo)
        return len(args) >= 3 and args[2] == "1"
    return event in EVENTS


def _index_argv(root: Path, event: str) -> list[str]:
    exe = shutil.which("ragx")
    base = [exe] if exe else [sys.executable, "-m", "ragx.cli.main"]
    return [*base, "index", str(root), "--quiet", "--source", f"hook:{event}"]


def spawn_index(root: Path, event: str) -> None:
    logs = root / ".ragx" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = (logs / "hooks.log").open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {
        "cwd": root, "stdin": subprocess.DEVNULL, "stdout": log, "stderr": log,
    }
    if sys.platform == "win32":
        # Git for Windows não tem nohup: sem DETACHED_PROCESS o hook espera a
        # indexação inteira. BREAKAWAY_FROM_JOB pode ser negado pelo job pai;
        # nesse caso tenta sem ele.
        detached = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
        try:
            subprocess.Popen(_index_argv(root, event),
                             creationflags=detached | 0x01000000, **kwargs)
        except OSError:
            subprocess.Popen(_index_argv(root, event), creationflags=detached, **kwargs)
    else:
        subprocess.Popen(_index_argv(root, event), start_new_session=True, **kwargs)
    log.close()


def _refresh_status(root: Path) -> None:
    try:
        from ragx.config import load_config
        from ragx.indexing import status_file

        status_file.write_status(load_config(root))
    except Exception:
        pass
```

Ligação com o status: em `status_file.py`, troque o padrão `_no_probe` por um import tardio (sem ciclo, porque `githooks` só importa `status_file` dentro de `_refresh_status`):

```python
def _default_probe(root: Path) -> bool | None:
    from ragx import githooks  # registra o probe real ao importar

    return githooks.installed(root)


hooks_installed_probe: Callable[[Path], bool | None] = _default_probe
```

Com isso a Task 3 continua passando (`hooks.installed` vira `None` fora de repo).

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/unit/test_githooks.py tests/integration/test_status_file.py -q`
Expected: PASS.

- [ ] **Step 6: CLI**

`src/ragx/cli/commands/hooks_cmd.py`:

```python
"""`ragx hooks install|uninstall|status` e o oculto `ragx hook-run`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ragx.config import find_root

console = Console()
app = typer.Typer(no_args_is_help=True)


def _root(path: Path) -> Path:
    root, _found = find_root(path.resolve())
    return root


@app.command("install")
def install(path: Annotated[Path, typer.Argument()] = Path(".")) -> None:
    """Instala os hooks que reindexam ao trocar de branch, commitar e fazer merge."""
    from ragx import githooks

    root = _root(path)
    written = githooks.install(root)
    console.print(f"\n[green]Hooks instalados[/] para {root}")
    for p in written:
        console.print(f"  [green]+[/] {p}")
    console.print("  [dim]Desative por um comando com RAGX_SKIP_HOOK=1[/]\n")


@app.command("uninstall")
def uninstall(path: Annotated[Path, typer.Argument()] = Path(".")) -> None:
    """Remove só os blocos do RAGX deste projeto; o resto dos hooks fica."""
    from ragx import githooks

    root = _root(path)
    touched = githooks.uninstall(root)
    if not touched:
        console.print("\n[dim]Nenhum hook do RAGX para este projeto.[/]\n")
        return
    console.print(f"\n[green]Hooks removidos[/] de {root}")
    for p in touched:
        console.print(f"  [red]-[/] {p}")
    console.print()


@app.command("status")
def status(
    path: Annotated[Path, typer.Argument()] = Path("."),
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Mostra se os hooks deste projeto estão instalados."""
    from ragx import githooks

    st = githooks.state(_root(path))
    if as_json:
        console.print_json(json.dumps(st, ensure_ascii=False))
        return
    if st["hooks_dir"] is None:
        console.print("\n[yellow]Fora de um repositório git.[/]\n")
        return
    console.print(f"\n[bold]Hooks[/] em {st['hooks_dir']}\n")
    for event, ok in st["events"].items():
        mark = "[green]instalado[/]" if ok else "[dim]ausente[/]"
        console.print(f"  {event:<14} {mark}")
    console.print()


def hook_run(
    event: Annotated[str, typer.Argument()],
    root: Annotated[Path, typer.Option("--root")],
    args: Annotated[list[str] | None, typer.Argument()] = None,
) -> None:
    """Uso interno dos hooks de git: dispara a indexação destacada e sai."""
    from ragx import githooks

    if event not in githooks.EVENTS:
        raise typer.Exit(0)
    if not githooks.should_run(event, list(args or [])):
        raise typer.Exit(0)
    if not (root / "ragx.toml").exists():
        raise typer.Exit(0)
    githooks.spawn_index(root, event)
```

Em `src/ragx/cli/main.py`: `from ragx.cli.commands import hooks_cmd` (em ordem alfabética na lista), `app.command("hook-run", hidden=True)(hooks_cmd.hook_run)` e `app.add_typer(hooks_cmd.app, name="hooks", help="Hooks de git que mantêm o índice na branch atual.")`.

Nota do Typer: `hook_run` recebe `args` extras; registrar com `context_settings={"allow_extra_args": True, "ignore_unknown_options": True}`:

```python
app.command(
    "hook-run",
    hidden=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)(hooks_cmd.hook_run)
```

Em `src/ragx/cli/commands/init.py`, parâmetro novo:

```python
    git_hooks: Annotated[
        bool, typer.Option("--git-hooks", help="Instala hooks que reindexam ao trocar de branch.")
    ] = False,
```

e, depois de criar o banco:

```python
    if git_hooks:
        from ragx import githooks

        try:
            githooks.install(root)
            created.append("hooks de git (post-checkout, post-commit, post-merge)")
        except RagxError as exc:
            console.print(f"[yellow]hooks não instalados:[/] {exc}")
```

(`from ragx.core.errors import RagxError`.)

- [ ] **Step 7: Teste e2e**

`tests/e2e/test_cli_hooks.py`:

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app

runner = CliRunner()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if subprocess.run(["git", "init", "-q"], cwd=tmp_path).returncode != 0:
        pytest.skip("git indisponível")
    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\nid = "t"\n', encoding="utf-8")
    return tmp_path


def test_install_status_uninstall(repo: Path) -> None:
    r = runner.invoke(app, ["hooks", "install", str(repo)])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["hooks", "status", str(repo), "--json"])
    assert json.loads(r.output)["installed"] is True
    r = runner.invoke(app, ["hooks", "uninstall", str(repo)])
    assert r.exit_code == 0
    r = runner.invoke(app, ["hooks", "status", str(repo), "--json"])
    assert json.loads(r.output)["installed"] is False


def test_hook_run_ignora_checkout_de_arquivo(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ragx import githooks

    calls: list[str] = []
    monkeypatch.setattr(githooks, "spawn_index", lambda root, ev: calls.append(ev))
    r = runner.invoke(app, ["hook-run", "post-checkout", "--root", str(repo), "a", "b", "0"])
    assert r.exit_code == 0 and calls == []
    r = runner.invoke(app, ["hook-run", "post-checkout", "--root", str(repo), "a", "b", "1"])
    assert r.exit_code == 0 and calls == ["post-checkout"]


def test_hook_run_evento_desconhecido_sai_quieto(repo: Path) -> None:
    r = runner.invoke(app, ["hook-run", "pre-push", "--root", str(repo)])
    assert r.exit_code == 0


def test_init_git_hooks(tmp_path: Path) -> None:
    if subprocess.run(["git", "init", "-q"], cwd=tmp_path).returncode != 0:
        pytest.skip("git indisponível")
    r = runner.invoke(app, ["init", str(tmp_path), "--git-hooks"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".git" / "hooks" / "post-commit").exists()
```

- [ ] **Step 8: Rodar e ver passar**

Run: `uv run pytest tests/unit/test_githooks.py tests/e2e/test_cli_hooks.py -q`
Expected: PASS. Se `init` registrar no hub e falhar no teste por isso, confira `tests/conftest.py` (hub isolado) antes de mexer.

- [ ] **Step 9: Documentar comandos (o teste de docs exige)**

Em `docs/14-cli.md`, logo após o bloco de `ragx init` da Fase 0, trocar a linha `--git-hooks             instala pre-commit/post-merge/post-checkout` por `--git-hooks             instala post-checkout/post-commit/post-merge (ragx hooks install)` e acrescentar:

````markdown
```bash
ragx hooks install [PATH]       hooks que reindexam ao trocar de branch, commitar e fazer merge
ragx hooks uninstall [PATH]     remove só o bloco do RAGX deste projeto
ragx hooks status [PATH] [--json]
ragx hook-run EVENTO --root PATH [ARGS]   uso interno dos hooks; não chame à mão
```

Os hooks convivem com hooks de outras ferramentas (o RAGX só mexe no bloco
entre `# ragx-hook-start` e `# ragx-hook-end`), respeitam `core.hooksPath` e
nunca bloqueiam o git: a indexação roda destacada e o log fica em
`.ragx/logs/hooks.log`. `RAGX_SKIP_HOOK=1` desliga por comando.
````

Run: `uv run pytest tests/unit/test_documentacao.py -q`
Expected: PASS.

- [ ] **Step 10: Suíte rápida, lint, commit**

Run: `uv run pytest -m "not slow" -q && uv run ruff check .`

```bash
git add src/ragx/githooks.py src/ragx/gitinfo.py src/ragx/indexing/status_file.py src/ragx/cli/commands/hooks_cmd.py src/ragx/cli/main.py src/ragx/cli/commands/init.py docs/14-cli.md tests/unit/test_githooks.py tests/e2e/test_cli_hooks.py
git commit -m "feat(hooks): ragx hooks mantem o indice na branch atual

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Origem e progresso na CLI; origens do watcher, MCP e sync

**Files:**
- Modify: `src/ragx/cli/commands/index_cmd.py` (`index`)
- Modify: `src/ragx/indexing/pipeline.py` (`on_event`)
- Modify: `src/ragx/watch/monitor.py` (`apply_changes`)
- Modify: `src/ragx/mcp/operations.py` (`reindex`, `refresh`)
- Modify: `src/ragx/sync/service.py`
- Test: `tests/e2e/test_cli_index_progress.py`, `tests/integration/test_watch.py` (acrescentar)

**Interfaces:**
- Consumes: `index_project(..., source, wait_s)`, `IndexBusyError`.
- Produces:
  - `index_project(..., on_event: Callable[[dict[str, Any]], None] | None = None)`. Eventos: `{"phase": "scan", "done": arquivos_vistos, "total": None}` por arquivo; `{"phase": "chunk", "done": arquivos_indexados, "total": None}` por arquivo chunkado; `{"phase": "embed", "done": n, "total": m}` pelo `progress` de `embed_pending`. O pipeline não limita frequência; quem limita é a CLI.
  - `ragx index --source ORIGEM` (padrão `cli`; `UsageError`, exit 2, para origem fora de `VALID_SOURCES`, que o próprio `index_project` já lança).
  - `ragx index --progress`: imprime em stdout uma linha JSON por evento, no máximo uma por segundo por fase (sempre imprime a primeira de cada fase), e uma linha final `{"phase": "done", "indexed": int, "chunks": int, "embedded": int, "blocked": int, "embed_error": str | null, "duration_ms": int}`. Ocupado: linha `{"phase": "busy", "pending": true, "holder": {...}}` e exit 0.
  - Espera pela trava: origem `cli` espera 30 s e, se continuar ocupado, a `IndexBusyError` sobe (exit 3, mensagem da Task 2). Qualquer outra origem espera 0 s, imprime a mensagem em amarelo (ou a linha `busy` com `--progress`) e sai com 0.
  - `apply_changes(cfg, state, consolidate, source: str = "watch")`; ocupado vira aviso em `state.warnings` ("índice ocupado; atualização agendada"), não `last_error`.
  - MCP: `reindex` usa `source="mcp:index"`, `refresh` chama `apply_changes(..., source="mcp:refresh")`.
  - `sync.service`: `index_project(cfg, full=full, source="sync", wait_s=30)`.

- [ ] **Step 1: Testes e2e**

`tests/e2e/test_cli_index_progress.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app

runner = CliRunner()


@pytest.fixture
def proj(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    for i in range(3):
        (tmp_path / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _lines(output: str) -> list[dict]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


def test_progress_emite_fases_e_linha_final(proj: Path) -> None:
    r = runner.invoke(app, ["index", str(proj), "--progress"])
    assert r.exit_code == 0, r.output
    events = _lines(r.output)
    phases = [e["phase"] for e in events]
    assert "scan" in phases and "embed" in phases
    assert phases[-1] == "done"
    final = events[-1]
    assert final["indexed"] == 4 and final["embedded"] > 0 and final["embed_error"] is None


def test_source_fica_registrada(proj: Path) -> None:
    import sqlite3

    r = runner.invoke(app, ["index", str(proj), "--quiet", "--source", "panel"])
    assert r.exit_code == 0, r.output
    conn = sqlite3.connect(proj / ".ragx" / "knowledge.db")
    try:
        assert conn.execute("SELECT source FROM index_runs").fetchone()[0] == "panel"
    finally:
        conn.close()


def test_source_invalida_e_erro_de_uso(proj: Path) -> None:
    from ragx.core.errors import UsageError

    r = runner.invoke(app, ["index", str(proj), "--source", "hacker"])
    # CliRunner não passa por main(), que traduz RagxError em exit code.
    assert r.exit_code != 0 and isinstance(r.exception, UsageError)


def test_ocupado_com_progress_sai_zero_e_avisa(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ragx.indexing import lock

    monkeypatch.setattr(lock, "try_acquire", lambda *a: False)
    monkeypatch.setattr(lock, "holder", lambda d: {"pid": 1, "source": "watch"})
    r = runner.invoke(app, ["index", str(proj), "--progress", "--source", "panel"])
    assert r.exit_code == 0
    assert _lines(r.output)[-1] == {"phase": "busy", "pending": True,
                                    "holder": {"pid": 1, "source": "watch"}}


def test_ocupado_na_origem_hook_sai_zero(proj: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ragx.indexing import lock

    monkeypatch.setattr(lock, "try_acquire", lambda *a: False)
    r = runner.invoke(app, ["index", str(proj), "--quiet", "--source", "hook:post-commit"])
    assert r.exit_code == 0
```

Nota: `runner.invoke` captura stdout; as linhas de progresso são escritas com `sys.stdout.write(...)` + `flush()`, não com `console.print` (o Rich quebra linha longa e injeta cor).

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/e2e/test_cli_index_progress.py -q`
Expected: FAIL (`No such option: --progress`).

- [ ] **Step 3: `on_event` no pipeline**

Em `_index_once` e `index_project`, parâmetro novo `on_event: Callable[[dict[str, Any]], None] | None = None`, repassado de `index_project` para `_index_once` (nas reexecuções pendentes, passe `None`). Dentro do laço, logo após `report.stats = _bump(report.stats, files_seen=1)`:

```python
                if on_event:
                    on_event({"phase": "scan", "done": report.stats.files_seen, "total": None})
```

logo após `report.stats = _bump(report.stats, indexed=1, chunks=len(produced))`:

```python
                if on_event:
                    on_event({"phase": "chunk", "done": report.stats.indexed, "total": None})
```

e nas duas chamadas a `embed_pending(cfg, conn)`:

```python
                er = embed_pending(cfg, conn, progress=_embed_cb(on_event))
```

com, no módulo:

```python
def _embed_cb(on_event: Callable[[dict[str, Any]], None] | None) -> Callable[[int, int], None] | None:
    if on_event is None:
        return None
    return lambda done, total: on_event({"phase": "embed", "done": done, "total": total})
```

- [ ] **Step 4: CLI `index`**

Em `index_cmd.index`, parâmetros novos:

```python
    source: Annotated[str, typer.Option("--source", help="Quem disparou (registrado no histórico).")] = "cli",
    progress_json: Annotated[bool, typer.Option("--progress", help="Progresso em linhas JSON no stdout.")] = False,
```

Funções auxiliares no módulo:

```python
def _emit(obj: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


class _Throttle:
    """No máximo uma linha por segundo por fase; a primeira de cada fase sempre sai."""

    def __init__(self) -> None:
        self.last: dict[str, float] = {}

    def __call__(self, ev: dict[str, object]) -> None:
        now = time.monotonic()
        phase = str(ev["phase"])
        if phase in self.last and now - self.last[phase] < 1.0:
            return
        self.last[phase] = now
        _emit(ev)
```

(imports `sys`, `time`, `from ragx.core.errors import IndexBusyError`.)

Corpo: `wait_s = 30.0 if source == "cli" else 0.0`. Envolver as chamadas a `index_project` num `try/except IndexBusyError as exc:`:

```python
    except IndexBusyError as exc:
        if source == "cli":
            raise
        if progress_json:
            _emit({"phase": "busy", "pending": True, "holder": exc.holder})
        elif not quiet:
            console.print(f"[yellow]{exc}[/]")
        return
```

Com `--progress` (checar antes do ramo `quiet or as_json`):

```python
    if progress_json:
        report = index_project(
            cfg, full=full, dry_run=dry_run, embed=not no_embed, embed_only=embed_only,
            source=source, wait_s=wait_s, on_event=_Throttle(),
        )
        s = report.stats
        _emit({
            "phase": "done", "indexed": s.indexed, "chunks": report.new_chunks,
            "embedded": s.embedded, "blocked": s.blocked,
            "embed_error": report.embed_error.splitlines()[0] if report.embed_error else None,
            "duration_ms": s.duration_ms,
        })
        return
```

Nas outras duas chamadas existentes, acrescentar `source=source, wait_s=wait_s`. Não imprimir o cabeçalho "Indexando" quando `progress_json`.

- [ ] **Step 5: Watcher, MCP e sync**

`src/ragx/watch/monitor.py`:

```python
def apply_changes(
    cfg: Config, state: WatchState, consolidate: bool, source: str = "watch"
) -> None:
    ...
    from ragx.core.errors import IndexBusyError
    from ragx.indexing.pipeline import index_project

    try:
        r = index_project(cfg, source=source)
        ...
    except IndexBusyError:
        state.warnings.append("índice ocupado; atualização agendada")
        return
    except Exception as exc:
        state.last_error = f"index: {exc}"
        return
```

`src/ragx/mcp/operations.py`: em `reindex`, `index_project(self.cfg, full=full, embed=embed, source="mcp:index")`; em `refresh`, `apply_changes(self.cfg, st, consolidate=True, source="mcp:refresh")`. Nenhum import novo (casca fina).

`src/ragx/sync/service.py`: `indexed = index_project(cfg, full=full, source="sync", wait_s=30)`.

Acrescentar em `tests/integration/test_watch.py`:

```python
def test_apply_changes_ocupado_vira_aviso(tmp_path, monkeypatch) -> None:
    from ragx.config import load_config
    from ragx.core.errors import IndexBusyError
    from ragx.watch import monitor

    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\nid = "t"\n', encoding="utf-8")

    def busy(*a, **k):
        raise IndexBusyError({"pid": 1, "source": "cli"})

    monkeypatch.setattr("ragx.indexing.pipeline.index_project", busy)
    st = monitor.WatchState()
    monitor.apply_changes(load_config(tmp_path), st, consolidate=False)
    assert st.last_error is None
    assert st.warnings == ["índice ocupado; atualização agendada"]
```

(Confira os imports e fixtures já existentes no topo de `test_watch.py` e siga o estilo do arquivo; se `WatchState()` exigir argumentos, use o construtor que os testes vizinhos usam.)

- [ ] **Step 6: Rodar e ver passar**

Run: `uv run pytest tests/e2e/test_cli_index_progress.py tests/integration/test_watch.py tests/integration/test_mcp.py tests/integration/test_sync.py -q`
Expected: PASS.

- [ ] **Step 7: Docs da CLI**

Em `docs/14-cli.md`, no bloco de `ragx index`, acrescentar:

```text
    --source ORIGEM         quem disparou: cli, panel, watch, sync, mcp:refresh,
                            mcp:index, hook:post-checkout, hook:post-commit, hook:post-merge
    --progress              progresso em linhas JSON no stdout (fases scan, chunk,
                            embed; linha final "done"; "busy" se outra indexação roda)
```

E, abaixo do bloco, um parágrafo:

```markdown
Só uma indexação roda por projeto (`.ragx/index.lock`). Quem chega com a trava
ocupada deixa o pedido agendado e quem está rodando repete a passada ao
terminar (até 3 vezes). Na origem `cli` o comando espera até 30 s antes de
desistir com exit 3; nas outras origens sai na hora com 0.
```

Run: `uv run pytest tests/unit/test_documentacao.py -q`

- [ ] **Step 8: Suíte rápida, lint, commit**

Run: `uv run pytest -m "not slow" -q && uv run ruff check .`

```bash
git add src/ragx/cli/commands/index_cmd.py src/ragx/indexing/pipeline.py src/ragx/watch/monitor.py src/ragx/mcp/operations.py src/ragx/sync/service.py docs/14-cli.md tests/e2e/test_cli_index_progress.py tests/integration/test_watch.py
git commit -m "feat(index): --source e --progress; watcher, MCP e sync registram a origem

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Documentação e CHANGELOG

**Files:**
- Modify: `docs/03-modelo-de-dados.md`
- Modify: `docs/12-git-sync.md`
- Modify: `docs/14-cli.md` (seção de `ragx status`)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: `docs/03-modelo-de-dados.md`**

Na descrição de `index_runs`, acrescentar as colunas `git_branch`, `git_commit`, `git_dirty` (0/1, nulo sem git) e `source` (origem, padrão `cli`), citando a migração `0006_run_provenance.sql`, e registrar que `mode` agora pode ser `embed-only`. Acrescentar uma seção curta "`.ragx/status.json`" com o exemplo de JSON da Task 3 e as regras: escrita atômica, só contagens e metadados, nenhum caminho de arquivo, reescrito no início e no fim de cada indexação e ao instalar ou remover hooks.

- [ ] **Step 2: `docs/12-git-sync.md`**

Substituir a tabela da seção que hoje promete `pre-commit` com `ragx security scan --staged` e `post-checkout` com `ragx sync --quiet` pelo que existe:

| Hook | Faz | Quando |
|---|---|---|
| `post-checkout` | `ragx index --source hook:post-checkout` destacado | só em troca de branch (flag 1) |
| `post-commit` | `ragx index --source hook:post-commit` destacado | todo commit |
| `post-merge` | `ragx index --source hook:post-merge` destacado | todo merge e pull |

Dizer em texto: os hooks nunca rodam `ragx sync` (que regrava arquivos versionados); nenhum hook bloqueia o git; um hook `pre-commit` com `ragx security scan --staged` ainda não existe (o comando existe e pode ser ligado à mão). Explicar a decisão "o índice segue a branch atual" e o que `ragx status` mostra quando está defasado (os quatro motivos da Task 4).

- [ ] **Step 3: `docs/14-cli.md`, `ragx status`**

No bloco `ragx status`, acrescentar abaixo de `--json`:

```text
    # --json inclui freshness {state, current, reasons} e recent_runs (últimas 10)
```

- [ ] **Step 4: CHANGELOG**

Em `CHANGELOG.md`, seção `[Não lançado]`, subseção de adições (siga o formato das entradas vizinhas), uma entrada:

```markdown
- **O índice acompanha a branch.** Cada indexação registra branch, commit e quem
  disparou (`cli`, `panel`, `watch`, `sync`, `mcp:*`, `hook:*`). `ragx status --json`
  diz se o índice está defasado e por quê (troca de branch, commits novos,
  arquivos alterados depois da indexação, embeddings pendentes) e traz as
  últimas 10 indexações. `ragx hooks install` (ou `ragx init --git-hooks`) liga
  hooks de `post-checkout`, `post-commit` e `post-merge` que reindexam em
  segundo plano. Só uma indexação roda por vez (`.ragx/index.lock`); pedidos
  que chegam no meio ficam agendados. O estado de cada projeto fica em
  `.ragx/status.json`, e `ragx index --progress` emite progresso em JSON.
```

- [ ] **Step 5: Verificação final e commit**

Run: `uv run pytest -m "not slow" -q && uv run pytest tests/security -q && uv run ruff check . && uv run mypy src/ragx/core src/ragx/security`
Expected: tudo verde.

```bash
git add docs/03-modelo-de-dados.md docs/12-git-sync.md docs/14-cli.md CHANGELOG.md
git commit -m "docs: indice por branch, hooks, trava e status.json

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
