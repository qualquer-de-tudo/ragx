"""`ragx sync` ocupado: a mensagem não pode prometer mais do que a trava cobre.

`IndexBusyError.__str__` (genérica, usada por `ragx index`) diz "este pedido
ficou agendado" — verdade para `index_project`, mas enganoso para `sync`: só a
reindexação incremental reroda sozinha quando a trava libera, nunca
knowledge/, grafo, dicionário ou federação. Ver ruling da revisão final de
branch em .superpowers/sdd/2026-09-23-indice-acompanha-branch/progress.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragx.cli.main import app
from ragx.core.errors import IndexBusyError

runner = CliRunner()


@pytest.fixture
def proj(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _boom(*a: object, **kw: object) -> None:
    raise IndexBusyError({"source": "hook:post-merge", "pid": 999})


def test_sync_ocupado_nao_promete_o_sync_inteiro(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ragx.sync.service as sync_mod

    monkeypatch.setattr(sync_mod, "index_project", _boom)
    r = runner.invoke(app, ["sync"])
    assert r.exit_code == IndexBusyError.exit_code
    assert "999" in r.output
    # A mensagem genérica de IndexBusyError some — o texto tem que deixar
    # claro que SÓ a reindexação é reagendada, não o sync inteiro.
    assert "ficou agendado" not in r.output
    assert "knowledge" in r.output.lower() or "grafo" in r.output.lower()


def test_sync_ocupado_json_tem_forma_de_erro_estruturado(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ragx.sync.service as sync_mod

    monkeypatch.setattr(sync_mod, "index_project", _boom)
    r = runner.invoke(app, ["sync", "--json"])
    assert r.exit_code == IndexBusyError.exit_code
    payload = json.loads(r.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "busy"
    assert "999" in payload["error"]["message"]


def test_sync_ocupado_quiet_nao_imprime_nada(
    proj: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ragx.sync.service as sync_mod

    monkeypatch.setattr(sync_mod, "index_project", _boom)
    r = runner.invoke(app, ["sync", "--quiet"])
    assert r.exit_code == IndexBusyError.exit_code
    assert r.output.strip() == ""
