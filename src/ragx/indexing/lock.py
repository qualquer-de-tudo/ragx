"""Trava entre processos para indexação.

Hooks de git, watcher, MCP, painel e CLI podem disparar indexação ao mesmo
tempo; dois escritores no mesmo banco já produziram `FOREIGN KEY constraint
failed`. Uma trava de arquivo resolve sem dependência nova, mas as duas
operações perigosas (criar e assumir uma trava morta) precisam ser atômicas
de ponta a ponta, senão dois processos podem concluir que são donos ao mesmo
tempo:

- Criar: escrever o conteúdo direto no caminho final com `O_EXCL` deixa uma
  janela em que o arquivo existe mas está vazio (`write` ainda não voltou).
  Um `holder()` concorrente nessa janela vê um arquivo ilegível, conclui
  "trava corrompida" e assume por cima. Por isso a publicação escreve num
  arquivo temporário único e só então cria um link físico (`os.link`) no
  caminho final: o link falha com `FileExistsError` se a trava já existe, e
  o caminho final nunca é observável vazio.
- Assumir uma trava de dono morto: se dois processos leem o mesmo pid morto,
  os dois decidem assumir; se ambos apagam-e-criam, o segundo apaga a trava
  nova do primeiro. Por isso a troca usa `rename` atômico para "arrancar" a
  trava do caminho antes de decidir o que fazer com ela — só um processo
  consegue mover o arquivo original por vez. Depois de mover, confere se o
  conteúdo movido é mesmo do pid que motivou a tentativa; se não for (outro
  processo já havia substituído a trava), devolve o arquivo ao lugar.

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
from uuid import uuid4

from ragx.storage.db import utcnow

LOCK_NAME = "index.lock"
PENDING_NAME = "index.pending"

if sys.platform == "win32":
    import ctypes

    _HANDLE = ctypes.c_void_p
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.restype = _HANDLE
    _kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    _kernel32.GetExitCodeProcess.restype = ctypes.c_int
    _kernel32.GetExitCodeProcess.argtypes = [_HANDLE, ctypes.POINTER(ctypes.c_ulong)]
    _kernel32.CloseHandle.restype = ctypes.c_int
    _kernel32.CloseHandle.argtypes = [_HANDLE]


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # os.kill(pid, 0) no Windows chama TerminateProcess: mataria o processo.
        handle = _kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED: existe
        try:
            code = ctypes.c_ulong()
            if not _kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            _kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def holder(state_dir: Path) -> dict[str, Any] | None:
    return _read(state_dir / LOCK_NAME)


def _publish(path: Path, payload: str) -> bool:
    """Cria a trava sem nunca deixá-la observável vazia (ver módulo)."""
    tmp = path.parent / f"{path.name}.tmp.{os.getpid()}.{uuid4().hex}"
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.link(tmp, path)
        return True
    except FileExistsError:
        return False
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


def _take_over(state_dir: Path, dead_pid: int | None, payload: str) -> bool:
    """Assume a trava de um dono morto (ou ilegível) sem corrida dupla.

    `dead_pid` é o pid que esta chamada julgou morto (ou `None`, se a trava
    estava ilegível). Ver módulo para o raciocínio do `rename` atômico.
    """
    path = state_dir / LOCK_NAME
    stale = state_dir / f"{LOCK_NAME}.stale.{os.getpid()}.{uuid4().hex}"
    try:
        os.rename(path, stale)
    except FileNotFoundError:
        # A trava sumiu entre a leitura e agora: outro processo já mexeu
        # nela. Tenta a criação normal, sem presumir quem é o dono.
        return _publish(path, payload)

    renamed = _read(stale)
    renamed_pid = renamed.get("pid") if renamed else None
    if renamed_pid != dead_pid:
        # Outro processo já havia substituído a trava por uma própria: essa
        # não era a trava morta que motivou esta tentativa. Devolve e desiste.
        with contextlib.suppress(FileExistsError):
            os.link(stale, path)
        with contextlib.suppress(FileNotFoundError):
            stale.unlink()
        return False

    # Era mesmo a trava morta (ou ilegível) que motivou a tentativa: descarta
    # e publica a nossa.
    with contextlib.suppress(FileNotFoundError):
        stale.unlink()
    return _publish(path, payload)


def try_acquire(state_dir: Path, op: str, source: str) -> bool:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / LOCK_NAME
    payload = json.dumps(
        {"pid": os.getpid(), "op": op, "source": source, "started_at": utcnow()}
    )
    if _publish(path, payload):
        return True
    current = holder(state_dir)
    pid = current.get("pid") if current else None
    if isinstance(pid, int) and pid_alive(pid):
        return False
    # Dono morto ou arquivo ilegível: assume.
    return _take_over(state_dir, pid, payload)


def release(state_dir: Path) -> None:
    current = holder(state_dir)
    if current is None or current.get("pid") != os.getpid():
        return
    with contextlib.suppress(FileNotFoundError):
        (state_dir / LOCK_NAME).unlink()


def mark_pending(state_dir: Path, source: str) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    tmp = state_dir / f"{PENDING_NAME}.{os.getpid()}.{uuid4().hex}.tmp"
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
