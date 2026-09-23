"""Trava entre processos para indexação.

Hooks de git, watcher, MCP, painel e CLI podem disparar indexação ao mesmo
tempo; dois escritores no mesmo banco já produziram `FOREIGN KEY constraint
failed`. Uma trava de arquivo criada com O_EXCL resolve sem dependência nova.

Quem chega com a trava ocupada deixa um pedido em `index.pending`; quem segura
a trava roda de novo ao terminar. Assim nenhum commit fica sem reindexação.
"""

from __future__ import annotations

import contextlib
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
    with contextlib.suppress(FileNotFoundError):
        (state_dir / LOCK_NAME).unlink()


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
