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
    commit = git(root, "rev-parse", "HEAD")
    if not commit:
        return None
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    porcelain = git(root, "status", "--porcelain", "--untracked-files=normal", "--", ".")
    return GitState(branch=branch or None, commit=commit, dirty=bool(porcelain))


def hooks_dir(root: Path) -> Path | None:
    """Pasta de hooks do repositório, respeitando `core.hooksPath`."""
    out = git(root, "rev-parse", "--git-path", "hooks")
    if not out:
        return None
    p = Path(out)
    return p if p.is_absolute() else (root / p).resolve()


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
