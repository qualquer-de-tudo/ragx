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


def test_trava_publicada_nunca_fica_vazia(tmp_path: Path) -> None:
    assert lock.try_acquire(tmp_path, "index", "cli") is True
    raw = (tmp_path / lock.LOCK_NAME).read_text(encoding="utf-8")
    assert raw  # publicação por link físico: nunca vazio no caminho final
    data = json.loads(raw)
    assert data["pid"] == os.getpid()
    assert data["source"] == "cli"
    lock.release(tmp_path)


def test_takeover_com_visao_desatualizada_nao_derruba_trava_viva(tmp_path: Path) -> None:
    """B ainda acredita que o dono é o pid morto original (visão obsoleta).

    A já assumiu a trava morta pelo caminho público (try_acquire). B tenta
    assumir a mesma trava morta diretamente pelo helper interno, usando um
    payload próprio — simula duas leituras concorrentes do mesmo holder
    morto que chegam a conclusões diferentes sobre o estado atual.
    """
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    dead_pid = p.pid
    (tmp_path / lock.LOCK_NAME).write_text(
        json.dumps({"pid": dead_pid, "op": "index", "source": "cli", "started_at": "x"}),
        encoding="utf-8",
    )

    assert lock.try_acquire(tmp_path, "index", "A") is True
    a_holder = lock.holder(tmp_path)
    assert a_holder is not None and a_holder["pid"] == os.getpid()

    payload_b = json.dumps(
        {"pid": 4_000_000, "op": "index", "source": "B", "started_at": "y"}
    )
    assert lock._take_over(tmp_path, dead_pid, payload_b) is False

    # A trava de A sobrevive intacta; B não conseguiu assumir.
    assert lock.holder(tmp_path) == a_holder
    lock.release(tmp_path)


def test_release_nao_mexe_em_trava_alheia(tmp_path: Path) -> None:
    foreign = {"pid": os.getpid() + 1, "op": "index", "source": "watch", "started_at": "x"}
    (tmp_path / lock.LOCK_NAME).write_text(json.dumps(foreign), encoding="utf-8")
    lock.release(tmp_path)
    assert lock.holder(tmp_path) == foreign
