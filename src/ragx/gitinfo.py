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

from ragx.procs import run_quiet

_TIMEOUT_S = 5


@dataclass(frozen=True)
class GitState:
    branch: str | None  # None com HEAD destacado
    commit: str
    dirty: bool


def git(root: Path, *args: str) -> str | None:
    try:
        out = run_quiet(
            # `--no-optional-locks`: `git status` por padrão refresca e grava
            # `.git/index`. Rodado em background (hook, watcher) ao mesmo
            # tempo que um `git rebase`/`checkout`/`commit` do usuário, essa
            # escrita pode colidir com a dele — exatamente o cenário que
            # dispara os hooks que chamam esta função. Todos os subcomandos
            # usados aqui (rev-parse, symbolic-ref, status, rev-list) se
            # comportam identicamente com a flag; sem ela, nenhum precisa da
            # trava opcional.
            ["git", "--no-optional-locks", *args],
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
    """Commit, branch e se o working tree está sujo, numa chamada só.

    `git status --porcelain=v2 --branch` traz tudo: `# branch.oid` (o commit, ou
    `(initial)` num repositório sem commit), `# branch.head` (a branch, ou
    `(detached)`) e, depois dos cabeçalhos, uma linha por arquivo alterado. Eram
    três processos (`rev-parse`, `symbolic-ref`, `status`) a cada indexação.
    """
    out = git(root, "status", "--porcelain=v2", "--branch", "--untracked-files=normal", "--", ".")
    if out is None:
        return None
    commit = ""
    branch: str | None = None
    dirty = False
    for linha in out.splitlines():
        if linha.startswith("# branch.oid "):
            commit = linha[len("# branch.oid "):]
        elif linha.startswith("# branch.head "):
            nome = linha[len("# branch.head "):]
            branch = None if nome == "(detached)" else nome
        elif linha and not linha.startswith("#"):
            dirty = True
    if not commit or commit == "(initial)":
        return None
    return GitState(branch=branch, commit=commit, dirty=dirty)


_HOOKS_DIR: dict[str, Path] = {}


def hooks_dir(root: Path) -> Path | None:
    """Pasta de hooks do repositório, respeitando `core.hooksPath`.

    Memoizado por processo e por raiz: `write_status` pergunta duas vezes por
    indexação. `None` nunca é guardado, para que um `git init` na mesma sessão
    seja visto; `hooks_dir_cache_clear` é chamado quando os hooks mudam.
    """
    chave = str(root)
    achado = _HOOKS_DIR.get(chave)
    if achado is not None:
        return achado
    out = git(root, "rev-parse", "--git-path", "hooks")
    if not out:
        return None
    p = Path(out)
    resolvido = p if p.is_absolute() else (root / p).resolve()
    _HOOKS_DIR[chave] = resolvido
    return resolvido


def hooks_dir_cache_clear() -> None:
    _HOOKS_DIR.clear()


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
