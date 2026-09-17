from __future__ import annotations

from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.graph.service import rebuild
from ragx.indexing.pipeline import index_project
from ragx.search.evaluation import EvalCase
from ragx.search.trial import run_trial

pytestmark = pytest.mark.integration

AUTH = '''class AuthService:
    """Autentica usuarios contra o provedor SSO corporativo."""

    def login(self, credentials):
        """Valida o token e cria a sessao no Redis com TTL de 30 minutos."""
        session = self.sso.validate(credentials)
        self.redis.setex(session.id, 1800, session.payload)
        return session
'''

LONGO = "# Manual\n\n## Detalhes\n\n" + "\n\n".join(
    f"Paragrafo {i} com bastante texto para gastar bastante espaco de contexto "
    f"e obrigar o motor a comprimir ou descartar alguma coisa." for i in range(120)
)


@pytest.fixture(scope="module")
def proj(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("trial")
    (root / "ragx.toml").write_text(
        '[project]\nname = "t"\nid = "t"\n\n'
        '[embedding]\nprovider = "hashing"\ndim = 128\nversioned_dim = 64\n',
        encoding="utf-8",
    )
    (root / "auth.py").write_text(AUTH, encoding="utf-8")
    (root / "manual.md").write_text(LONGO, encoding="utf-8")
    cfg = load_config(root)
    index_project(cfg)
    rebuild(cfg)
    return root


def test_ragx_tokens_never_exceed_budget(proj: Path) -> None:
    cases = [EvalCase(query="autenticacao sessao redis", relevant_paths=("auth.py",))]
    results = run_trial(load_config(proj), cases, budget=500)
    assert results[0].ragx_tokens <= 500


def test_baseline_is_bigger_for_long_file(proj: Path) -> None:
    """O manual grande tem que gerar baseline >> ragx_tokens quando o
    orcamento forca compressao/descarte — e exatamente o efeito que a
    ferramenta existe para medir."""
    cases = [EvalCase(query="detalhes do manual", relevant_paths=("manual.md",))]
    results = run_trial(load_config(proj), cases, budget=300)
    r = results[0]
    assert r.baseline_tokens > r.ragx_tokens
    assert r.sources_total == 1


def test_sources_hit_counts_relevant_paths_in_the_pack(proj: Path) -> None:
    cases = [EvalCase(query="autenticacao sessao redis", relevant_paths=("auth.py",))]
    results = run_trial(load_config(proj), cases, budget=2000)
    assert results[0].sources_hit == 1
