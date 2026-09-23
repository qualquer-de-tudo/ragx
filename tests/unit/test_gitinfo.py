from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ragx import gitinfo


def _repo(root: Path) -> Path:
    if subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root).returncode != 0:
        pytest.skip("git indisponível")
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "c1"], cwd=root, check=True)
    return root


def test_fora_de_repo_devolve_none(tmp_path: Path) -> None:
    assert gitinfo.read_state(tmp_path) is None


def test_estado_limpo(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    st = gitinfo.read_state(root)
    assert st is not None
    assert st.branch == "main"
    assert len(st.commit) == 40
    assert st.dirty is False


def test_estado_sujo(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "a.txt").write_text("b\n", encoding="utf-8")
    st = gitinfo.read_state(root)
    assert st is not None and st.dirty is True


def test_head_destacado_tem_branch_none(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    head = gitinfo.git(root, "rev-parse", "HEAD")
    subprocess.run(["git", "checkout", "-q", "--detach", head], cwd=root, check=True)
    st = gitinfo.read_state(root)
    assert st is not None and st.branch is None and st.commit == head


def test_repo_sem_commit_devolve_none(tmp_path: Path) -> None:
    if subprocess.run(["git", "init", "-q"], cwd=tmp_path).returncode != 0:
        pytest.skip("git indisponível")
    assert gitinfo.read_state(tmp_path) is None
