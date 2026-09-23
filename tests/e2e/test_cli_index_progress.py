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
