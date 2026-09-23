from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project, status

pytestmark = pytest.mark.integration

TOML = (
    '[project]\nname = "t"\nid = "t"\n\n'
    '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n'
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(root: Path, sub: str = "") -> Path:
    if subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root).returncode != 0:
        pytest.skip("git indisponível")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    proj = root / sub if sub else root
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "ragx.toml").write_text(TOML, encoding="utf-8")
    (proj / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "fora.txt").write_text("x\n", encoding="utf-8")
    (root / ".gitignore").write_text(".ragx/\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "c1")
    return proj


def _kinds(fr: dict) -> dict[str, dict]:
    return {r["kind"]: r for r in fr["reasons"]}


def _touch_future(p: Path) -> None:
    t = time.time() + 5
    os.utime(p, (t, t))


def test_recem_indexado_esta_em_dia(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg)
    fr = status(cfg)["freshness"]
    assert fr["state"] == "fresh" and fr["reasons"] == []
    assert fr["current"]["branch"] == "main"


def test_troca_de_branch_deixa_defasado(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg)
    _git(proj, "checkout", "-qb", "feat/x")
    fr = status(cfg)["freshness"]
    assert fr["state"] == "stale"
    assert _kinds(fr)["branch_changed"] == {
        "kind": "branch_changed", "indexed": "main", "current": "feat/x",
    }


def test_commits_depois_do_indice(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "b.py").write_text("x = 1\n", encoding="utf-8")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "c2")
    assert _kinds(status(cfg)["freshness"])["commits_since_index"]["count"] == 1


def test_arquivo_alterado_sem_commit_conta_so_se_mais_novo(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    (proj / "a.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    cfg = load_config(proj)
    index_project(cfg)
    # Alterado ANTES da indexação: o índice já tem a versão nova.
    assert "uncommitted_changes" not in _kinds(status(cfg)["freshness"])
    _touch_future(proj / "a.py")
    fr = status(cfg)["freshness"]
    assert _kinds(fr)["uncommitted_changes"]["count"] == 1
    assert "a.py" not in str(fr)


def test_arquivo_apagado_depois_do_indice_conta(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg)
    (proj / "a.py").unlink()
    assert _kinds(status(cfg)["freshness"])["uncommitted_changes"]["count"] == 1


def test_projeto_em_subpasta_ignora_o_resto_do_repo(tmp_path: Path) -> None:
    proj = _repo(tmp_path, sub="backend/src")
    cfg = load_config(proj)
    index_project(cfg)
    fora = tmp_path / "fora.txt"
    fora.write_text("mudou\n", encoding="utf-8")
    _touch_future(fora)
    assert status(cfg)["freshness"]["state"] == "fresh"


def test_head_destacado_nao_quebra(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg)
    _git(proj, "checkout", "-q", "--detach")
    fr = status(cfg)["freshness"]
    assert fr["current"]["branch"] is None
    assert "branch_changed" not in _kinds(fr)


def test_embeddings_pendentes(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg, embed=False)
    fr = status(cfg)["freshness"]
    assert fr["state"] == "stale"
    assert _kinds(fr)["pending_embeddings"]["count"] > 0


def test_sem_git_e_sem_pendencia_e_desconhecido(tmp_path: Path) -> None:
    (tmp_path / "ragx.toml").write_text(TOML, encoding="utf-8")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    index_project(cfg)
    st = status(cfg)
    assert st["freshness"]["state"] == "unknown"
    assert st["freshness"]["current"] is None


def test_embed_only_nao_mascara_troca_de_branch(tmp_path: Path) -> None:
    """Reproduzido pelo revisor: indexa na branch A, troca pra B, roda só
    `--embed-only` — sem a correção, essa corrida virava "a última indexação
    útil" e a árvore de B (na verdade não reindexada) passava por em dia."""
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    index_project(cfg)
    _git(proj, "checkout", "-qb", "feat/x")
    (proj / "a.py").write_text("def f():\n    return 999\n", encoding="utf-8")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "c2")

    index_project(cfg, embed_only=True)

    fr = status(cfg)["freshness"]
    assert fr["state"] == "stale"
    assert _kinds(fr)["branch_changed"] == {
        "kind": "branch_changed", "indexed": "main", "current": "feat/x",
    }


def test_recent_runs_no_status(tmp_path: Path) -> None:
    proj = _repo(tmp_path)
    cfg = load_config(proj)
    for _ in range(12):
        index_project(cfg)
    runs = status(cfg)["recent_runs"]
    assert len(runs) == 10
    assert runs[0]["git_branch"] == "main"
