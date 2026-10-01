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


def test_missing_relevant_path_is_flagged_not_counted_as_zero_tokens(proj: Path) -> None:
    """Regressão: um `relevant_paths` desatualizado (arquivo renomeado/apagado)
    não pode virar 0 tokens de baseline silenciosos — isso se lê como "RAGX
    descartou a resposta" quando na verdade é o corpus que está podre."""
    cases = [
        EvalCase(
            query="autenticacao sessao redis",
            relevant_paths=("auth.py", "nao-existe.py"),
        )
    ]
    results = run_trial(load_config(proj), cases, budget=2000)
    r = results[0]
    assert r.missing_paths == 1
    only_auth = run_trial(
        load_config(proj),
        [EvalCase(query="autenticacao sessao redis", relevant_paths=("auth.py",))],
        budget=2000,
    )[0]
    assert r.baseline_tokens == only_auth.baseline_tokens


# ── RAGX-0163: dois baselines honestos, com a economia conservadora ─────
def test_trial_traz_os_dois_baselines_e_a_economia_conservadora(proj: Path) -> None:
    cases = [EvalCase(query="detalhes do manual", relevant_paths=("manual.md",))]
    r = run_trial(load_config(proj), cases, budget=300)[0]
    assert r.baseline_oracle_tokens > 0 and r.baseline_grep_tokens > 0
    assert r.baseline_tokens == r.baseline_oracle_tokens  # compatibilidade: o antigo é o oráculo
    menor = min(r.baseline_oracle_tokens, r.baseline_grep_tokens)
    assert r.saved_ratio_conservative == pytest.approx(1 - r.ragx_tokens / menor)
    assert r.saved_ratio_conservative <= r.saved_ratio + 1e-9


def test_ragx_tokens_do_trial_e_o_markdown_entregue(proj: Path) -> None:
    from ragx.context.engine import build_context
    from ragx.context.render import render
    from ragx.tokens import count_tokens

    cfg = load_config(proj)
    r = run_trial(cfg, [EvalCase(query="autenticacao sessao redis", relevant_paths=("auth.py",))],
                  budget=900)[0]
    pack = build_context(cfg, "autenticacao sessao redis", budget=900, use_cache=False)
    assert r.ragx_tokens == count_tokens(render(pack, "markdown", title=False))


def test_grep_files_muda_o_baseline_do_grep(proj: Path) -> None:
    cfg = load_config(proj)
    cases = [EvalCase(query="paragrafo manual detalhes autenticacao", relevant_paths=("manual.md",))]
    k1 = run_trial(cfg, cases, budget=500, grep_files=1)[0].baseline_grep_tokens
    k5 = run_trial(cfg, cases, budget=500, grep_files=5)[0].baseline_grep_tokens
    assert k5 >= k1 > 0
