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


def test_apply_changes_ocupado_vira_aviso(tmp_path, monkeypatch) -> None:
    from ragx.config import load_config
    from ragx.core.errors import IndexBusyError
    from ragx.watch import monitor

    (tmp_path / "ragx.toml").write_text('[project]\nname = "t"\nid = "t"\n', encoding="utf-8")

    def busy(*a, **k):
        raise IndexBusyError({"pid": 1, "source": "cli"})

    monkeypatch.setattr("ragx.indexing.pipeline.index_project", busy)
    st = monitor.WatchState()
    monitor.apply_changes(load_config(tmp_path), st, consolidate=False)
    assert st.last_error is None
    assert st.warnings == ["índice ocupado; atualização agendada"]


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


def test_arquivo_travado_nao_vira_remocao_no_watcher(cfg, monkeypatch) -> None:
    """Antivírus ou editor seguram o arquivo logo depois do save; o watcher
    dispara exatamente nesse momento (RAGX-0133)."""
    original = Path.read_bytes

    def trava(self: Path) -> bytes:
        if self.name == "app.py":
            raise PermissionError(32, "violação de compartilhamento")
        return original(self)

    (cfg.root / "app.py").write_text("def alfa():\n    return 99\n", encoding="utf-8")
    monkeypatch.setattr(Path, "read_bytes", trava)
    st = WatchState()
    apply_changes(cfg, st, consolidate=False)
    with open_db(cfg.db_path, read_only=True) as conn:
        caminhos = {r[0] for r in conn.execute("SELECT rel_path FROM documents")}
    assert "app.py" in caminhos
    assert st.last_error is None


# --- RAGX-0147: gate único, vereditos em cache e aplicação por caminho ---------------------------------------------


def _conta_gates(monkeypatch):  # type: ignore[no-untyped-def]
    from ragx.security import gate as gate_mod

    n = {"gates": 0}
    original = gate_mod.SecurityGate.__init__

    def conta(self, *a, **k):  # type: ignore[no-untyped-def]
        n["gates"] += 1
        original(self, *a, **k)

    monkeypatch.setattr(gate_mod.SecurityGate, "__init__", conta)
    return n


def test_gate_e_construido_uma_vez_em_50_ciclos_ociosos(cfg, monkeypatch) -> None:
    n = _conta_gates(monkeypatch)
    watch(cfg, max_cycles=50, sleep=lambda _s: None)
    assert n["gates"] == 1


@pytest.mark.parametrize("regra", [".gitignore", ".dockerignore", ".ragignore"])
def test_arquivo_de_ignore_reconstroi_o_gate_e_a_regra_vale_no_ciclo_seguinte(cfg, monkeypatch, regra) -> None:
    (cfg.root / "log.tmp").write_text("x = 1\n", encoding="utf-8")
    n = _conta_gates(monkeypatch)
    ciclo = {"n": 0}

    def sleep(_s: float) -> None:
        ciclo["n"] += 1
        if ciclo["n"] == 2:
            (cfg.root / regra).write_text("*.tmp\n", encoding="utf-8")

    watch(cfg, max_cycles=6, sleep=sleep)
    # o do início, o refeito pelo arquivo de regra e o do `index_project` que esse lote dispara (o lote cai nele)
    assert n["gates"] == 3
    assert "log.tmp" not in snapshot(cfg)


def test_snapshot_sem_gate_continua_igual(cfg) -> None:
    assert snapshot(cfg) == snapshot(cfg, None, None)


def test_lote_de_um_arquivo_vai_por_index_paths_e_o_texto_novo_aparece(cfg, monkeypatch) -> None:
    import ragx.indexing.pipeline as pipe

    chamadas: list[str] = []
    for nome in ("index_paths", "index_project"):
        original = getattr(pipe, nome)
        monkeypatch.setattr(pipe, nome, lambda *a, _o=original, _n=nome, **k: (chamadas.append(_n), _o(*a, **k))[1])
    ciclo = {"n": 0}

    def sleep(_s: float) -> None:
        ciclo["n"] += 1
        if ciclo["n"] == 1:
            (cfg.root / "novo.py").write_text("def zeta_unico_0147():\n    return 7\n", encoding="utf-8")

    watch(cfg, max_cycles=5, sleep=sleep)
    assert chamadas[0] == "index_paths"
    assert search(cfg, "zeta_unico_0147", mode="keyword", limit=5).results


def test_lote_com_gitignore_cai_em_index_project(cfg, monkeypatch) -> None:
    import ragx.indexing.pipeline as pipe

    chamadas: list[str] = []
    original = pipe.index_project
    monkeypatch.setattr(pipe, "index_project", lambda *a, **k: (chamadas.append("index_project"), original(*a, **k))[1])
    ciclo = {"n": 0}

    def sleep(_s: float) -> None:
        ciclo["n"] += 1
        if ciclo["n"] == 1:
            (cfg.root / ".gitignore").write_text("build/\n", encoding="utf-8")

    watch(cfg, max_cycles=4, sleep=sleep)
    assert "index_project" in chamadas


def test_arquivo_apagado_sai_do_indice_pelo_lote_por_caminho(cfg) -> None:
    ciclo = {"n": 0}

    def sleep(_s: float) -> None:
        ciclo["n"] += 1
        if ciclo["n"] == 1:
            (cfg.root / "app.py").unlink()

    watch(cfg, max_cycles=4, sleep=sleep)
    with open_db(cfg.db_path, read_only=True) as conn:
        assert "app.py" not in {r[0] for r in conn.execute("SELECT rel_path FROM documents")}


def test_estado_expoe_a_duracao_do_ciclo(cfg) -> None:
    st = watch(cfg, max_cycles=5, sleep=lambda _s: None)
    assert st.last_cycle_ms is not None and st.idle_cycle_ms_p50 is not None


# ── grafo incremental (RAGX-0151) ───────────────────────────────────────
CORPO_ALFA = '''def alfa(x):
    """Soma e acumula o valor recebido."""
    total = x + {n}
    for item in range(5):
        total += item * x
    return total
'''


@pytest.fixture()
def cfg_grafo(tmp_path: Path):
    from ragx.graph.service import rebuild

    root = tmp_path / "projg"
    root.mkdir()
    (root / "ragx.toml").write_text(
        '[project]\nname = "g"\nid = "g"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n\n'
        "[watch]\ninterval_s = 0.0\ndebounce_s = 0.0\nfull_sync_every = 50\n",
        encoding="utf-8",
    )
    (root / "app.py").write_text(CORPO_ALFA.format(n=1), encoding="utf-8")
    c = load_config(root)
    index_project(c)
    rebuild(c)
    return c


def _entidade_alfa(cfg) -> dict | None:
    with open_db(cfg.db_path, read_only=True) as conn:
        row = conn.execute("SELECT * FROM entities WHERE name = 'alfa'").fetchone()
        return dict(row) if row else None


def test_salvar_arquivo_atualiza_o_grafo_sem_esperar_full_sync_every(cfg_grafo) -> None:
    cfg = cfg_grafo
    antes = _entidade_alfa(cfg)
    assert antes is not None and antes["chunk_id"] is not None
    ciclo = {"n": 0}

    def sleep(_s: float) -> None:
        ciclo["n"] += 1
        if ciclo["n"] == 1:
            (cfg.root / "app.py").write_text(CORPO_ALFA.format(n=7), encoding="utf-8")

    st = watch(cfg, max_cycles=4, sleep=sleep)
    assert st.consolidations == 0, "o grafo tem de andar sem o sync completo"
    depois = _entidade_alfa(cfg)
    # o chunk mudou de id com o corpo novo; sem o grafo incremental a ponte ficava nula
    assert depois is not None and depois["chunk_id"] is not None
    assert depois["chunk_id"] != antes["chunk_id"]


def test_falha_do_grafo_vira_aviso_e_a_indexacao_conclui(cfg_grafo, monkeypatch) -> None:
    cfg = cfg_grafo

    def quebra(*a, **k):
        raise RuntimeError("grafo quebrado")

    monkeypatch.setattr("ragx.graph.service.update_documents", quebra)
    (cfg.root / "app.py").write_text(CORPO_ALFA.format(n=9), encoding="utf-8")
    st = WatchState()
    apply_changes(cfg, st, consolidate=False, paths=("app.py",))
    assert st.last_error is None
    assert st.indexed == 1
    assert any(w.startswith("grafo: RuntimeError") for w in st.warnings), st.warnings
    with open_db(cfg.db_path, read_only=True) as conn:
        texto = conn.execute("SELECT content FROM chunks WHERE content LIKE '%+ 9%'").fetchone()
    assert texto is not None  # o texto novo foi indexado apesar do grafo
