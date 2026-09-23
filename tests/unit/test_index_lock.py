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
