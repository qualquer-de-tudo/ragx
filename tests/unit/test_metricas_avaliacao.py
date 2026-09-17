"""As métricas de avaliação medem o que dizem medir.

`_ndcg` contava caminhos duplicados como acertos separados, com o denominador
ideal contado em arquivos. O resultado passava de 1,0 — medido: **2,131** — numa
métrica cuja definição tem teto 1,0.

O erro tinha direção, e é isso que o torna caro: **premiava devolver o mesmo
arquivo picado em vários chunks**. Quem otimizasse contra essa métrica estaria
otimizando para fragmentar o contexto.

Ver `task/fase-14-evolucao-do-rag/RAGX-0098-*.md`.
"""

from __future__ import annotations

import pytest

from ragx.search.evaluation import _first_hit_rank, _ndcg

pytestmark = pytest.mark.unit


# ── a regressão que dá nome ao arquivo ──────────────────────────────────
def test_chunks_repetidos_do_mesmo_arquivo_nao_passam_de_um() -> None:
    """O caso exato que media 2,131."""
    assert _ndcg(["a.py", "a.py", "a.py", "x", "y"], ("a.py",)) == pytest.approx(1.0)


def test_nunca_passa_de_um() -> None:
    casos = [
        (["a"] * 10, ("a",)),
        (["a", "b"] * 5, ("a", "b")),
        (["a", "a", "b", "b", "c"], ("a", "b", "c")),
        (["a"], ("a", "b", "c")),
    ]
    for paths, relevantes in casos:
        v = _ndcg(paths, relevantes)
        assert 0.0 <= v <= 1.0, f"nDCG fora de [0,1] para {paths} / {relevantes}: {v}"


# ── os extremos ─────────────────────────────────────────────────────────
def test_resultado_perfeito_vale_um() -> None:
    assert _ndcg(["a.py", "b.md", "z"], ("a.py", "b.md")) == pytest.approx(1.0)


def test_nenhum_acerto_vale_zero() -> None:
    assert _ndcg(["x", "y", "z"], ("a.py",)) == 0.0


def test_sem_relevantes_vale_zero_em_vez_de_dividir_por_zero() -> None:
    assert _ndcg(["x", "y"], ()) == 0.0


def test_lista_vazia_vale_zero() -> None:
    assert _ndcg([], ("a.py",)) == 0.0


# ── ordenação ───────────────────────────────────────────────────────────
def test_acerto_mais_acima_vale_mais() -> None:
    cedo = _ndcg(["a.py", "x", "y", "z"], ("a.py",))
    tarde = _ndcg(["x", "y", "z", "a.py"], ("a.py",))
    assert cedo > tarde


def test_relevante_depois_do_corte_nao_conta() -> None:
    assert _ndcg(["x"] * 10 + ["a.py"], ("a.py",), k=10) == 0.0


def test_relevante_duplicado_na_lista_de_referencia_nao_infla_o_ideal() -> None:
    """`relevant_paths` com o mesmo caminho duas vezes é erro de quem escreveu
    o caso — não pode baixar a nota de quem acertou."""
    assert _ndcg(["a.py", "x"], ("a.py", "a.py")) == pytest.approx(1.0)


# ── MRR, que não tinha o defeito e precisa continuar sem ele ────────────
def test_mrr_usa_a_primeira_ocorrencia() -> None:
    assert _first_hit_rank(["x", "a.py", "a.py"], ("a.py",)) == 2


def test_mrr_sem_acerto_e_none() -> None:
    assert _first_hit_rank(["x", "y"], ("a.py",)) is None


def test_mrr_nao_e_afetado_por_duplicatas() -> None:
    """É por isso que o MRR é o indicador citável enquanto o resto assenta."""
    assert _first_hit_rank(["a.py"] * 5, ("a.py",)) == _first_hit_rank(["a.py"], ("a.py",))


# ── intervalo de confiança ──────────────────────────────────────────────
def test_wilson_contra_valores_conhecidos() -> None:
    from ragx.search.evaluation import wilson_ci

    # 20 de 26 é o recall@5 do keyword hoje. O intervalo publicado na auditoria
    # é [0,58 – 0,89]; se este teste quebrar, o número do documento mudou.
    lo, hi = wilson_ci(20, 26)
    assert lo == pytest.approx(0.58, abs=0.01)
    assert hi == pytest.approx(0.89, abs=0.01)


def test_wilson_nunca_escapa_de_zero_um() -> None:
    """É por isso que Wilson e não o intervalo normal: com proporção em 0 ou 1,
    o normal produz limites fora de [0,1] e mente sobre a precisão."""
    from ragx.search.evaluation import wilson_ci

    for hits, n in [(0, 10), (10, 10), (0, 1), (1, 1), (1, 100)]:
        lo, hi = wilson_ci(hits, n)
        assert 0.0 <= lo <= hi <= 1.0, f"IC fora de [0,1] para {hits}/{n}"


def test_wilson_com_n_zero_nao_divide_por_zero() -> None:
    from ragx.search.evaluation import wilson_ci

    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_amostra_maior_estreita_o_intervalo() -> None:
    from ragx.search.evaluation import wilson_ci

    def largura(hits, n):
        lo, hi = wilson_ci(hits, n)
        return hi - lo

    assert largura(77, 100) < largura(20, 26)
    assert largura(116, 150) < largura(20, 26)


def test_o_conjunto_de_hoje_e_declarado_inconclusivo() -> None:
    """26 consultas não distinguem os modos, e o `ragx eval` precisa dizer isso.

    Quando o conjunto for ampliado (`RAGX-0099`), este teste vira o oposto: a
    conclusão passa a ser possível e o aviso some.
    """
    from ragx.search.evaluation import MAX_CI_WIDTH, ModeMetrics, wilson_ci

    m = ModeMetrics(mode="hybrid", cases=26, recall_ci=wilson_ci(16, 26))
    assert not m.conclusive
    assert m.ci_width > MAX_CI_WIDTH

    amplo = ModeMetrics(mode="hybrid", cases=150, recall_ci=wilson_ci(116, 150))
    assert amplo.conclusive
