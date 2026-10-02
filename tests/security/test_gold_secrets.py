"""O conjunto-ouro derivado do git não carrega segredo de assunto de commit (RAGX-0167)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fixtures.secrets_under_test import SECRETS_UNDER_TEST, leaked
from ragx.gitinfo import Commit
from ragx.search.gold import derive_cases, render_yaml

pytestmark = pytest.mark.security


@pytest.mark.parametrize("segredo", SECRETS_UNDER_TEST)
def test_assunto_com_segredo_e_descartado_e_contado(segredo: str) -> None:
    commits = [
        Commit("s1", f"fix: troca a credencial {segredo} no deploy", ("src/a.py",), 1),
        Commit("ok", "fix: corrige o parser de markdown", ("src/a.py",), 2),
    ]
    r = derive_cases(commits, {"src/a.py": "code"})
    assert [c.commit for c in r.cases] == ["ok"]
    assert r.funnel.segredo == 1
    assert leaked(render_yaml(r, "abc1234")) == []
    assert segredo not in render_yaml(r, "abc1234")


def test_o_repo_map_nao_traz_arquivo_bloqueado_pelo_gate(tmp_path: Path) -> None:
    """O grafo só conhece documentos liberados (RAGX-0168): nada bloqueado pode aparecer no mapa, nem um segredo nele."""
    import json
    import shutil

    from fixtures.secrets_under_test import FIXTURE_ROOT, MUST_BLOCK
    from ragx.config import load_config
    from ragx.graph.rank import repo_map
    from ragx.graph.service import rebuild
    from ragx.indexing.pipeline import index_project

    raiz = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT, raiz)
    (raiz / "ragx.toml").write_text(
        '[project]\nname = "f"\nid = "f"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n', encoding="utf-8"
    )
    cfg = load_config(raiz)
    index_project(cfg)
    rebuild(cfg)
    mapa = repo_map(cfg, tokens=600)
    caminhos = {m["path"] for m in mapa}
    assert not caminhos & set(MUST_BLOCK)
    assert leaked(json.dumps(mapa, ensure_ascii=False)) == []
