from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
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


def test_espera_tenta_de_novo_apos_marcar_pendencia_antes_de_desistir(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corrida em que a trava esvazia bem entre marcar a pendência e desistir.

    O primeiro `try_acquire` falha (mock), o código marca o pedido e, antes
    de lançar `IndexBusyError`, tenta mais uma vez — dessa vez com sucesso de
    verdade, porque nenhum outro processo jamais segurou a trava (a falha era
    só do mock). `index_project` roda em vez de lançar. A pendência que a
    própria chamada deixou é drenada normalmente na sequência (reexecução
    extra, incremental e idempotente).
    """
    cfg = load_config(proj)
    real_try_acquire = lock.try_acquire
    calls: list[bool] = []

    def flaky(state_dir: Path, op: str, source: str) -> bool:
        if not calls:
            calls.append(False)
            return False
        calls.append(True)
        return real_try_acquire(state_dir, op, source)

    monkeypatch.setattr(lock, "try_acquire", flaky)
    index_project(cfg, source="cli")
    assert calls == [False, True]
    assert _sources(proj) == ["cli", "cli"]
    assert lock.holder(cfg.state_dir) is None


def test_pendencia_entre_ultimo_take_pending_e_release_ainda_roda(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simula um pedido chegando entre o último `take_pending` e o `release`.

    Monkeypatcha `lock.release` para marcar uma pendência exatamente antes de
    liberar de verdade, reproduzindo a corrida sem depender de threads: o
    dono precisa reobter a trava e drenar de novo depois de liberar.
    """
    cfg = load_config(proj)
    real_release = lock.release

    def release_and_sneak_in(state_dir: Path) -> None:
        lock.mark_pending(state_dir, "watch")
        real_release(state_dir)

    monkeypatch.setattr(lock, "release", release_and_sneak_in)
    index_project(cfg, source="cli")
    assert _sources(proj) == ["cli", "watch"]


def test_espera_com_wait_s_ate_a_trava_ser_liberada(proj: Path) -> None:
    cfg = load_config(proj)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / lock.LOCK_NAME).write_text(
        json.dumps({"pid": os.getpid(), "op": "index", "source": "watch", "started_at": "x"}),
        encoding="utf-8",
    )

    def free_it_later() -> None:
        time.sleep(1.0)
        lock.release(cfg.state_dir)

    t = threading.Thread(target=free_it_later)
    t.start()
    try:
        index_project(cfg, source="cli", wait_s=5.0)
    finally:
        t.join()
    assert _sources(proj) == ["cli"]
    assert lock.holder(cfg.state_dir) is None


def test_orcamento_de_reexecucoes_pendentes_tem_teto(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ragx.indexing.pipeline as pipeline

    cfg = load_config(proj)
    original = pipeline._index_once

    def again_and_again(*a: object, **k: object) -> object:
        r = original(*a, **k)
        lock.mark_pending(cfg.state_dir, "cli")
        return r

    monkeypatch.setattr(pipeline, "_index_once", again_and_again)
    index_project(cfg, source="cli")
    assert _sources(proj) == ["cli"] * 4  # 1 inicial + 3 reexecucoes (teto)
    assert lock.is_pending(cfg.state_dir)  # sobrou 1 pedido nunca atendido
