"""Fase 11 — watcher: o índice acompanhando o working tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project
from ragx.search.service import search
from ragx.storage.db import open_db
from ragx.watch.monitor import WatchState, apply_changes, diff, snapshot, watch

pytestmark = pytest.mark.integration


@pytest.fixture()
def cfg(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "ragx.toml").write_text(
        '[project]\nname = "w"\nid = "w"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n\n'
        "[watch]\ninterval_s = 0.0\ndebounce_s = 0.0\nfull_sync_every = 3\n",
        encoding="utf-8",
    )
    (root / "app.py").write_text("def alfa():\n    return 1\n", encoding="utf-8")
    c = load_config(root)
    index_project(c)
    return c


def test_snapshot_ignora_o_proprio_estado(cfg) -> None:
    """`.ragx/` muda a cada indexação. Se entrasse no snapshot, o watcher
    veria mudança a cada ciclo e reindexaria para sempre."""
    snap = snapshot(cfg)
    assert "app.py" in snap
    assert not any(p.startswith(".ragx/") for p in snap), sorted(snap)


def test_diff_classifica_criado_alterado_removido() -> None:
    antes = {"a": (1, 1), "b": (2, 2)}
    depois = {"a": (1, 1), "b": (9, 9), "c": (3, 3)}
    d = diff(antes, depois)
    assert d.created == ("c",)
    assert d.modified == ("b",)
    assert d.deleted == ()
    assert d.total == 2


def test_arquivo_novo_entra_no_indice(cfg) -> None:
    (cfg.root / "beta.py").write_text("def beta():\n    return 2\n", encoding="utf-8")

    st = WatchState()
    apply_changes(cfg, st, consolidate=False)

    with open_db(cfg.db_path, read_only=True) as conn:
        caminhos = {r[0] for r in conn.execute("SELECT rel_path FROM documents")}
    assert "beta.py" in caminhos
    assert st.last_error is None


def test_arquivo_removido_sai_do_indice(cfg) -> None:
    (cfg.root / "app.py").unlink()
    apply_changes(cfg, WatchState(), consolidate=False)
    with open_db(cfg.db_path, read_only=True) as conn:
        caminhos = {r[0] for r in conn.execute("SELECT rel_path FROM documents")}
    assert "app.py" not in caminhos


def test_segredo_novo_e_bloqueado_pelo_watcher(cfg) -> None:
    """O watcher não é um atalho para dentro do gate."""
    (cfg.root / ".env").write_text(
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n",
        encoding="utf-8",
    )
    st = WatchState()
    apply_changes(cfg, st, consolidate=False)
    assert st.blocked >= 1
    assert not search(cfg, "wJalrXUtnFEMI", mode="keyword", limit=5).results


def test_laco_debouncia_e_consolida(cfg) -> None:
    """Salvar em rajada vira UMA reindexação; a consolidação é periódica."""
    eventos: list[str] = []
    ciclo = {"n": 0}

    def sleep(_s: float) -> None:
        # Cada "sono" é a oportunidade de mexer no disco, como um editor faria.
        ciclo["n"] += 1
        if ciclo["n"] in (1, 2):
            (cfg.root / f"m{ciclo['n']}.py").write_text(
                f"def m{ciclo['n']}():\n    return {ciclo['n']}\n", encoding="utf-8"
            )

    st = watch(
        cfg,
        on_event=lambda kind, d, s: eventos.append(kind),
        max_cycles=8,
        sleep=sleep,
    )

    assert eventos.count("change") == 2
    # Duas mudanças em ciclos seguidos, uma única aplicação depois da quietude.
    assert st.applied == 1
    with open_db(cfg.db_path, read_only=True) as conn:
        caminhos = {r[0] for r in conn.execute("SELECT rel_path FROM documents")}
    assert {"m1.py", "m2.py"} <= caminhos


def test_falha_de_indexacao_nao_derruba_o_laco(cfg, monkeypatch) -> None:
    """Watcher morto é pior que watcher ausente: o agente segue consultando um
    índice parado sem ninguém perceber."""
    import ragx.indexing.pipeline as pipeline

    def explode(*a, **k):
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(pipeline, "index_project", explode)
    st = WatchState()
    apply_changes(cfg, st, consolidate=True)
    assert st.last_error and "disco cheio" in st.last_error
    assert st.applied == 0
