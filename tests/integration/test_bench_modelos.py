"""O benchmark de modelos de ponta a ponta com candidatos `hashing` (RAGX-0169)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ragx.config import load_config
from ragx.indexing.pipeline import index_project
from ragx.search import bench
from ragx.search.bench import Candidate
from ragx.search.evaluation import EvalCase
from ragx.storage.db import open_db

pytestmark = pytest.mark.integration

FUNCAO = 'def {nome}(x):\n    """Calcula {nome}."""\n    total = 0\n    for k in range(x):\n        total += k * 3\n    return total\n'


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "ragx.toml").write_text(
        '[project]\nname = "b"\nid = "b"\n\n[embedding]\nprovider = "hashing"\ndim = 64\nversioned_dim = 32\n', encoding="utf-8"
    )
    for nome in ("busca_por_palavra", "gate_de_seguranca", "indexacao_incremental"):
        (tmp_path / f"{nome}.py").write_text(FUNCAO.format(nome=nome), encoding="utf-8")
    index_project(load_config(tmp_path))
    return tmp_path


def _estado(cfg) -> tuple:  # type: ignore[no-untyped-def]
    with open_db(cfg.db_path, read_only=True) as conn:
        return (
            tuple(conn.execute("SELECT COUNT(*), MAX(rowid) FROM embeddings").fetchone()),
            [tuple(r) for r in conn.execute("SELECT id, dim FROM embedding_models ORDER BY id")],
        )


def test_dois_candidatos_hashing_o_banco_real_fica_intacto_e_a_raiz_temporaria_some(proj: Path) -> None:
    cfg = load_config(proj)
    antes = _estado(cfg)
    conjuntos = {
        "manual": [
            EvalCase("busca por palavra", ("busca_por_palavra.py",)),
            EvalCase("gate de seguranca", ("gate_de_seguranca.py",)),
        ]
    }
    resultados = [
        bench.run_embedding(cfg, Candidate(f"h{d}", "hashing", "hashing", d), conjuntos, consultas_latencia=3) for d in (64, 128)
    ]
    assert [r.status for r in resultados] == ["disponivel", "disponivel"]
    for r in resultados:
        assert r.load_s is not None and r.chunks_per_s and r.chunks_per_s > 0 and r.vector_bytes and r.vector_bytes > 0
        assert r.query_p50_ms is not None and r.query_p95_ms is not None
        assert set(r.metrics["manual"]) == {"semantic", "hybrid"} and r.metrics["manual"]["hybrid"].n == 2
    assert resultados[0].vector_bytes != resultados[1].vector_bytes  # 64 e 128 dimensões ocupam espaços diferentes
    assert _estado(cfg) == antes  # o índice REAL não foi escrito
    assert not (cfg.state_dir / "bench" / "h64").exists() and not (cfg.state_dir / "bench" / "h128").exists()


def test_candidato_que_falha_vira_incompativel_e_nao_derruba_os_outros(proj: Path) -> None:
    cfg = load_config(proj)
    conjuntos = {"manual": [EvalCase("busca por palavra", ("busca_por_palavra.py",))]}
    r_ruim = bench.run_embedding(cfg, Candidate("ruim", "nuvem", "x", 8), conjuntos)  # provider que o build_embedder desconhece
    r_bom = bench.run_embedding(cfg, Candidate("bom", "hashing", "hashing", 64), conjuntos)
    assert r_ruim.status == "incompativel" and r_ruim.detail
    assert r_bom.status == "disponivel"


def test_reranker_com_funcao_injetada_mede_recall_e_latencia(proj: Path) -> None:
    cfg = load_config(proj)
    conjuntos = {
        "manual": [
            EvalCase("busca por palavra", ("busca_por_palavra.py",)),
            EvalCase("gate de seguranca", ("gate_de_seguranca.py",)),
        ]
    }
    c = Candidate("rr", "fastembed", "Xenova/ms-marco-MiniLM-L-6-v2", 0, "reranker", "apache-2.0")

    def nota(q: str, textos: list[str]) -> list[float]:
        # reranker de brinquedo: o número de palavras da consulta que aparecem no texto
        return [float(sum(w in t for w in q.split())) for t in textos]

    r = bench.run_reranker(cfg, c, conjuntos, rerank_fn=nota)
    m = r.metrics["manual"]["hybrid+rerank"]
    assert r.status == "disponivel" and m.n == 2 and m.recall_at_5 >= 0.5
    assert r.rerank_p50_ms is not None and r.rerank_p95_ms is not None


def test_reranker_ausente_vira_ausente_e_nao_zero(proj: Path) -> None:
    cfg = load_config(proj)
    c = Candidate("rr", "fastembed", "modelo/que-nao-existe", 0, "reranker")
    r = bench.run_reranker(cfg, c, {"manual": [EvalCase("x", ("a.py",))]})
    assert r.status == "ausente" and not r.metrics


def test_resultado_serializa_em_json_sem_perder_o_status(proj: Path) -> None:
    cfg = load_config(proj)
    conjuntos = {"manual": [EvalCase("busca", ("busca_por_palavra.py",))]}
    r = bench.run_embedding(cfg, Candidate("h64", "hashing", "hashing", 64), conjuntos, 2)
    ausente = bench.BenchResult(Candidate("a", "ollama", "x", 1), "ausente", "não está no Ollama")
    dados = json.loads(json.dumps(bench.to_jsonable([r, ausente])))
    assert dados[0]["status"] == "disponivel" and dados[1]["status"] == "ausente" and dados[1]["metrics"] == {}
