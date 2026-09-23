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
