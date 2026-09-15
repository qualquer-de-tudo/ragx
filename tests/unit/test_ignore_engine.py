from __future__ import annotations

from pathlib import Path

import pytest

from ragx.security.ignore_engine import IgnoreEngine

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "sub").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".gitignore").write_text("*.log\nbuild/\n", encoding="utf-8")
    (tmp_path / "src" / ".gitignore").write_text("tmp.py\n", encoding="utf-8")
    (tmp_path / ".ragignore").write_text("docs/**\n!docs/keep.md\n", encoding="utf-8")
    return tmp_path


def test_gitignore_basico(repo: Path) -> None:
    e = IgnoreEngine(repo)
    assert e.should_ignore("app.log")[0]
    assert not e.should_ignore("app.py")[0]


def test_gitignore_aninhado_afeta_so_a_subarvore(repo: Path) -> None:
    e = IgnoreEngine(repo)
    assert e.should_ignore("src/tmp.py")[0]
    assert not e.should_ignore("tmp.py")[0], "regra de src/ vazou para a raiz"


def test_negacao_reverte(repo: Path) -> None:
    e = IgnoreEngine(repo)
    assert e.should_ignore("docs/interno.md")[0]
    assert not e.should_ignore("docs/keep.md")[0]


def test_origem_da_decisao_e_reportada(repo: Path) -> None:
    ignored, source = e_source = IgnoreEngine(repo).should_ignore("app.log")
    assert ignored and source and ".gitignore" in source
    assert e_source


def test_defaults_embutidos(repo: Path) -> None:
    e = IgnoreEngine(repo)
    for p in ("node_modules/x.js", ".git/config", "a.min.js", "img.png", "x.sqlite"):
        assert e.should_ignore(p)[0], p


def test_env_nao_e_ignorado_precisa_chegar_ao_scanner(repo: Path) -> None:
    """IgnoreEngine trata de RUÍDO. Quem protege segredo é o scanner."""
    assert not IgnoreEngine(repo).should_ignore(".env")[0]
