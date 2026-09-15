from __future__ import annotations

import numpy as np
import pytest

from ragx.context.budget import allocate
from ragx.context.compress import TRUNCATED, compress
from ragx.context.dedup import dedupe_literal, dedupe_near, mmr
from ragx.context.engine import detect_intent
from ragx.core.models import ChunkKind, SearchResult
from ragx.tokens import count_tokens

pytestmark = pytest.mark.unit


def _r(cid: str, path: str, score: float, content: str = "x", **meta) -> SearchResult:
    return SearchResult(
        chunk_id=cid, document_path=path, kind=ChunkKind.SECTION,
        start_line=1, end_line=2, score=score, content=content,
        metadata={"token_count": count_tokens(content), **meta},
    )


# ── Orçamento ───────────────────────────────────────────────────────────
def test_nunca_estoura_o_orcamento() -> None:
    cands = [_r(f"c{i}", f"d{i}.md", 1.0 - i / 100, "palavra " * 200) for i in range(30)]
    plan = allocate(cands, budget=500)
    assert plan.used_tokens <= 500


def test_reserva_garante_multiplas_fontes() -> None:
    """O modo de falha clássico: todo o orçamento vindo de um arquivo só."""
    cands = [
        _r("a1", "mesmo.md", 0.99, "conteudo " * 60),
        _r("a2", "mesmo.md", 0.98, "conteudo " * 60),
        _r("a3", "mesmo.md", 0.97, "conteudo " * 60),
        _r("b1", "outro.md", 0.20, "conteudo " * 60),
        _r("c1", "terceiro.md", 0.10, "conteudo " * 60),
    ]
    plan = allocate(cands, budget=600, min_sources=3)
    fontes = {r.document_path for r in plan.selected}
    assert len(fontes) >= 3, f"contexto colapsou numa fonte só: {fontes}"


def test_densidade_prefere_valor_por_token() -> None:
    caro = _r("caro", "a.md", 0.9, "palavra " * 400)
    barato = _r("barato", "b.md", 0.8, "curto")
    plan = allocate([caro, barato], budget=200, min_sources=1)
    assert any(r.chunk_id == "barato" for r in plan.selected)


def test_orcamento_zero_nao_quebra() -> None:
    assert allocate([_r("a", "a.md", 1.0)], budget=0).selected == ()


def test_lista_vazia_nao_quebra() -> None:
    assert allocate([], budget=1000).selected == ()


def test_descartados_sao_registrados() -> None:
    cands = [_r(f"c{i}", f"d{i}.md", 1.0, "palavra " * 300) for i in range(20)]
    plan = allocate(cands, budget=400)
    assert plan.dropped and all(why == "budget" for _r_, why in plan.dropped)


# ── Dedup ───────────────────────────────────────────────────────────────
def test_duplicata_literal_mantem_a_de_maior_score() -> None:
    a = _r("a", "primeiro.py", 0.9, "mesmo corpo", content_hash="h1")
    b = _r("b", "segundo.py", 0.5, "mesmo corpo", content_hash="h1")
    res = dedupe_literal([a, b])
    assert [r.chunk_id for r in res.kept] == ["a"]
    assert "duplicate_of:primeiro.py" in res.dropped[0][1]


def test_sem_duplicata_mantem_tudo() -> None:
    res = dedupe_literal([_r("a", "a.py", 1.0, "um"), _r("b", "b.py", 1.0, "outro")])
    assert len(res.kept) == 2


def test_quase_duplicata_por_cosseno() -> None:
    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    quase = np.array([0.999, 0.04, 0.0], dtype=np.float32)
    quase /= np.linalg.norm(quase)
    res = dedupe_near(
        [_r("a", "a.md", 0.9), _r("b", "b.md", 0.5)],
        {"a": v, "b": quase}, threshold=0.93,
    )
    assert [r.chunk_id for r in res.kept] == ["a"]


def test_vetores_distantes_sao_mantidos() -> None:
    res = dedupe_near(
        [_r("a", "a.md", 0.9), _r("b", "b.md", 0.5)],
        {
            "a": np.array([1.0, 0.0], dtype=np.float32),
            "b": np.array([0.0, 1.0], dtype=np.float32),
        },
        threshold=0.93,
    )
    assert len(res.kept) == 2


def test_chunk_sem_vetor_nao_e_descartado() -> None:
    res = dedupe_near([_r("a", "a.md", 0.9)], {}, threshold=0.5)
    assert len(res.kept) == 1


def test_mmr_favorece_cobertura_com_lambda_baixo() -> None:
    vecs = {
        "a": np.array([1.0, 0.0], dtype=np.float32),
        "b": np.array([0.98, 0.2], dtype=np.float32),
        "c": np.array([0.0, 1.0], dtype=np.float32),
    }
    for k, v in vecs.items():
        vecs[k] = v / np.linalg.norm(v)
    q = np.array([1.0, 0.0], dtype=np.float32)
    rs = [_r("a", "a.md", 0.9), _r("b", "b.md", 0.8), _r("c", "c.md", 0.3)]

    relevancia = [r.chunk_id for r in mmr(rs, vecs, q, lambda_=1.0, k=2).kept]
    cobertura = [r.chunk_id for r in mmr(rs, vecs, q, lambda_=0.2, k=2).kept]
    assert relevancia == ["a", "b"]
    assert "c" in cobertura, f"lambda baixo devia trazer diversidade: {cobertura}"


def test_mmr_sem_query_vec_degrada_sem_quebrar() -> None:
    rs = [_r("a", "a.md", 0.9), _r("b", "b.md", 0.8)]
    assert len(mmr(rs, {}, None, k=2).kept) == 2


# ── Compressão ──────────────────────────────────────────────────────────
def test_conteudo_pequeno_nao_e_comprimido() -> None:
    c = compress("linha curta", target_tokens=500)
    assert not c.compressed and c.strategy == "none"


def test_poda_remove_licenca_e_imports() -> None:
    src = (
        "# Copyright 2026 Alguem\n"
        "import os\n"
        "from typing import Any\n"
        "\n\n\n"
        "def real():\n    return 1\n"
    )
    out = compress(src, target_tokens=8, is_code=True).text
    assert "Copyright" not in out and "import os" not in out
    assert "def real" in out


def test_assinatura_nunca_e_removida() -> None:
    corpo = "\n".join(f"    x{i} = {i}" for i in range(200))
    c = compress(f"def processa(a, b):\n{corpo}\n", target_tokens=30, is_code=True)
    assert "def processa(a, b):" in c.text


def test_colapso_marca_as_linhas_omitidas() -> None:
    corpo = "\n".join(f"    x{i} = {i}" for i in range(200))
    c = compress(f"def f():\n{corpo}\n", target_tokens=30, is_code=True)
    assert "linhas omitidas" in c.text or TRUNCATED in c.text


def test_selecao_de_sentencas_preserva_o_heading() -> None:
    doc = "## Autenticacao\n\n" + " ".join(
        f"Frase numero {i} sobre um assunto qualquer." for i in range(60)
    )
    c = compress(doc, target_tokens=40, query="autenticacao")
    assert c.text.startswith("## Autenticacao")


def test_truncamento_e_marcado() -> None:
    c = compress("palavra " * 800, target_tokens=20)
    assert TRUNCATED in c.text


def test_compressao_e_deterministica() -> None:
    src = "def f():\n" + "\n".join(f"    y{i} = {i}" for i in range(120))
    a = compress(src, 40, query="f", is_code=True).text
    b = compress(src, 40, query="f", is_code=True).text
    assert a == b


def test_compressao_reduz_de_fato() -> None:
    src = "def f():\n" + "\n".join(f"    y{i} = {i} * 2 + 1" for i in range(300))
    c = compress(src, 60, is_code=True)
    assert count_tokens(c.text) < count_tokens(src) * 0.6


# ── Intenção ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "query,esperado",
    [
        ("implementar autenticacao SSO", "implement"),
        ("onde fica o AuthService", "locate"),
        ("como funciona o gate", "locate"),
        ("corrigir bug no login", "fix"),
        ("revisar o parser", "review"),
        ("AuthService", "general"),
    ],
)
def test_deteccao_de_intencao(query: str, esperado: str) -> None:
    assert detect_intent(query)["id"] == esperado
