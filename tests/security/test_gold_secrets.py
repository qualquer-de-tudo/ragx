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
