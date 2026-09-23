from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing import lock
from ragx.indexing.pipeline import index_project
from ragx.indexing.status_file import STATUS_NAME, write_status

pytestmark = pytest.mark.integration


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "demo"\nid = "demo-id"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return tmp_path


def _read(root: Path) -> dict:
    return json.loads((root / ".ragx" / STATUS_NAME).read_text(encoding="utf-8"))


def test_indexar_grava_o_status(proj: Path) -> None:
    index_project(load_config(proj), source="panel")
    st = _read(proj)
    assert st["schema_version"] == 1
    assert st["project"] == {
        "id": "demo-id",
        "name": "demo",
        "root": load_config(proj).root.as_posix(),
    }
    assert st["index"]["source"] == "panel"
    assert st["index"]["mode"] == "incremental"
    assert st["index"]["finished_at"]
    assert st["counts"]["chunks"] > 0
    assert st["counts"]["embeddings"] == st["counts"]["chunks"]
    assert st["counts"]["pending_embeddings"] == 0
    assert st["embedding"]["provider"] == "hashing"
    assert st["running"] is None and st["pending"] is False and st["last_error"] is None


def test_sem_embeddings_conta_pendentes(proj: Path) -> None:
    index_project(load_config(proj), embed=False)
    st = _read(proj)
    assert st["counts"]["embeddings"] == 0
    assert st["counts"]["pending_embeddings"] == st["counts"]["chunks"]


def test_status_mostra_quem_esta_rodando(proj: Path) -> None:
    cfg = load_config(proj)
    index_project(cfg)
    assert lock.try_acquire(cfg.state_dir, "index", "watch")
    try:
        write_status(cfg)
        st = _read(proj)
        assert st["running"]["source"] == "watch"
    finally:
        lock.release(cfg.state_dir)


def test_status_nao_tem_caminho_de_arquivo(proj: Path) -> None:
    index_project(load_config(proj))
    assert "a.py" not in (proj / ".ragx" / STATUS_NAME).read_text(encoding="utf-8")


def test_sem_banco_nao_escreve(tmp_path: Path) -> None:
    (tmp_path / "ragx.toml").write_text('[project]\nname = "x"\nid = "x"\n', encoding="utf-8")
    assert write_status(load_config(tmp_path)) is None
    assert not (tmp_path / ".ragx" / STATUS_NAME).exists()


def test_escrita_e_atomica_nao_deixa_temporario(proj: Path) -> None:
    index_project(load_config(proj))
    leftovers = [p.name for p in (proj / ".ragx").iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
